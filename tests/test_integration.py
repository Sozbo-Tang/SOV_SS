"""集成测试：world_tick 主循环 × 地面防空链 × 航空挂点（sovs/sim/tick.py 接线验收）。

锚点全部写死（配置表值 / combat 曲线锚点 / 管线时序推演），不自证：
- ① 确定性双跑：同 seed 构造两个相同 world，各跑 300 tick，逐 tick 比较全状态指纹
  （单位/元素/武器态/弹丸/航空器/玩家/PCG32 八通道内部 state），断言位级相等；
- ② 防空链全程：sense_air 置位 → aa_try_engage（begin_aim 5 tick）→ finish_aim →
  fire_aa（HIT/SCATTER 通道）→ system_projectiles 推进（弹速 20000 cm/tick ×
  距离 50000 → 第 12 tick 落弹）→ resolve_hit_aa：HE 曲线锚点 pen=8 / armor_aa=4
  → mult=800‰ → damage 10 → 每命中 -8 HP（combat.damage_mult_permille HE 支：
  pen²·1000//(pen²+armor²) = 64·1000//80 = 800）；
- ③ M17 对偶清位：超出该队全部探测者（aa_roster 名单支 + 低空目视支）范围即清
  spotted_mask 对应位；低空目视支独立锚点（不入名单的普通单位可目视发现 LOW 层机）；
- ④ AIR 通道与 HIT 通道独立性：航空段（缠斗掷骰/侦察标记/投弹散布——全部
  world.rng.air()）不扰动 HIT/SCATTER；防空链（fire_aa）不扰动 AIR（联立断言
  "被消费通道 state 变化"证非平凡）；
- ⑤ 瑕疵① 修复锚点：air.py 头部与 tables.py 航空段注释版本引用 v1.4；
- ⑥ rotating 每 tick 复位（GROUND IMPL v1.7 GAP-25：fire_arc<360 元素）。
"""
import pathlib
import unittest

from sovs.sim.air import (AircraftInstance, AircraftTemplate, AirRole, AirState,
                          cmd_air_strike)
from sovs.sim.tick import (SmokeZone, add_unit, make_unit, make_world,
                           world_tick)
from sovs.sim.types import (AltTier, DamageType, ElementTemplate, ElementType,
                            MovementClass, TargetDomain, Trajectory, UnitType,
                            WeaponTemplate, UnitTemplate, WState)

ROOT = pathlib.Path(__file__).resolve().parents[1]

# ── 地面模板（防空链锚点数值载体）──
# AA 高炮：必中（accuracy_base_bp=10000 且无压制/crit → acc 链恒 10000bp
# 〔D071 全拆 2026-10-07 勘正：crit 项已随生产端退役=恒等——acc 链结论不变〕）、
# pen_min=pen_max=8（KE 距离插值恒 8）、aim 5 tick、reload 100 tick、弹速 20000。
AA_GUN = WeaponTemplate(
    name="AA", target_mask=TargetDomain.AIR, damage_type=DamageType.KE,
    pen_min=8, pen_max=8, damage=10, salvo=1, aim_time_ticks=5,
    reload_time_ticks=100, ammo_base=50, max_range_cm=80000,
    dispersion_cm=200, accuracy_base_bp=10000, projectile_speed_cm_tick=20000,
    trajectory=Trajectory.DIRECT)
AA_ELEM = ElementTemplate(element_type=ElementType.GUN, unit_type=UnitType.MECH,
                          hp_max=10, weapons=(AA_GUN,))
AA_TPL = UnitTemplate(
    template_id=101, name="AA gun", category=4, cost=60, element_templates=(AA_ELEM,),
    optics_ground_cm=20000, optics_air_cm=60000, air_ceiling=AltTier.HIGH,
    stealth_base=5, speed_tier=1, movement_class=MovementClass.TRACK)
AA_TPL_MID_CEILING = UnitTemplate(
    template_id=104, name="AA mid only", category=4, cost=60, element_templates=(AA_ELEM,),
    optics_ground_cm=20000, optics_air_cm=60000, air_ceiling=AltTier.MID,
    stealth_base=5, speed_tier=1, movement_class=MovementClass.TRACK)

# 普通步兵（无 AIR 武器、optics_air_cm=0 → 不入 aa_roster；低空目视支载体）
INF_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                           unit_type=UnitType.INFANTRY, hp_max=10)
INF_TPL = UnitTemplate(
    template_id=102, name="INF", category=1, cost=20, element_templates=(INF_ELEM,),
    optics_ground_cm=80000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)

# 窄射界炮（fire_arc 60°<360 → rotating 复位扫描集）
AT_GUN = WeaponTemplate(name="AT", target_mask=TargetDomain.GROUND,
                        max_range_cm=60000, aim_time_ticks=3,
                        reload_time_ticks=50, ammo_base=10)
AT_ELEM = ElementTemplate(element_type=ElementType.GUN, unit_type=UnitType.MECH,
                          hp_max=8, fire_arc_deg=60, weapons=(AT_GUN,))
AT_TPL = UnitTemplate(
    template_id=103, name="AT gun", category=3, cost=45, element_templates=(AT_ELEM,),
    optics_ground_cm=20000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.TRACK)

# ── 航空模板（惯例同 tests/test_air_behavior.py）──
BOMB_W = WeaponTemplate(name="BOMB", damage_type=DamageType.HE, target_mask=1,
                        trajectory=Trajectory.BALLISTIC, damage=20,
                        blast_radius_cm=2500, salvo=2, dispersion_cm=1000,
                        projectile_speed_cm_tick=500)


def atpl(role, **kw):
    d = dict(template_id=1, name="T", role=role, cost_body=70, hp_max=30,
             armor_aa=4, speed_cm_tick=100, dogfight_power=5, maneuver=5,
             alt_ceiling=AltTier.HIGH, weapons=(), payload_max_bombs=4,
             payload_max_supply=600, paratroop_seats=0, turret_damage=0,
             can_engage_air=False, has_dive=False, payload_price={"BOMB": 5})
    d.update(kw)
    return AircraftTemplate(**d)


FIGHTER_T = atpl(AirRole.FIGHTER, dogfight_power=5, maneuver=5,
                 payload_max_supply=0)
BOMBER_T = atpl(AirRole.BOMBER, weapons=((BOMB_W, 4),), dogfight_power=2,
                maneuver=3)
RECON_T = atpl(AirRole.RECON, optics_air_cm=8000, recon_mark_base_bp=10000,
               payload_max_supply=0)


def inst(w, t, team=0, pos=(500000, 500000), alt=AltTier.MID):
    """悬停航空器（PATROL + 空 flight_plan + 无 task → aircraft_move_step 不位移）。"""
    a = AircraftInstance(id=w.next_aircraft_id, team=team, player_index=team,
                         template=t, pos=pos, alt_tier=alt,
                         hp_current=t.hp_max, state=AirState.PATROL)
    w.next_aircraft_id += 1
    a.ammo_left = {"BOMB": 0, "STRAFE": 0, "SUPPLY_ROUNDS": 0, "SUPPLY_MEDICAL": 0}
    w.aircraft.append(a)
    return a


def fingerprint(w):
    """全状态指纹：单位/元素/武器态/弹丸/航空器/玩家/八通道 PCG32 内部 state。
    返工补全（2026-10-01，验收 nit）：单位段 +deploy_state/deploy_timer/
    infiltration_timer（system_timers 消费面）、元素段 +garrison_in/mounted_in
    引用（id 或 -）、烟区逐区 center/ttl（原仅 S%d 计数—— SmokeZone 两字段均
    入指纹，ttl 递减漂移不再漏检）。"""
    parts = ["t%d:p%d:r%s" % (w.tick, w.phase,
                              ",".join(str(r.state) for r in w.rng._rngs))]
    for u in w.units:
        parts.append("U%d,%d,%s,%d,%d,%d,%d,%d,%d,%d" % (
            u.id, u.team, u.pos, int(u.alive), u.spotted_mask,
            int(u.mark_level), len(u.move_path),
            int(u.deploy_state), u.deploy_timer, u.infiltration_timer))
        for e in u.elements:
            gref = "-" if e.garrison_in is None else \
                "G%d" % getattr(e.garrison_in, "id", -1)
            mref = "-" if e.mounted_in is None else "M%d" % e.mounted_in.id
            parts.append("E%d,%s,%d,%d,%d,%d,%d,%s,%s" % (
                e.id, e.pos, e.hp_current, e.facing, e.suppression,
                e.reveal_timer, int(e.rotating), gref, mref))
            for ws in e.weapon_states:
                t = ws.target
                tref = "-" if t is None else (
                    "A%d" % t.id if isinstance(t, AircraftInstance) else "E%d" % t.id)
                parts.append("W%d,%d,%d,%s" % (int(ws.state), ws.timer,
                                               ws.ammo_left, tref))
    for a in w.aircraft:
        d = a.dogfight
        parts.append("A%d,%d,%s,%d,%d,%d,%d,%d,%d,%s,%r,%s,%d,%d,%d,%s" % (
            a.id, a.team, a.pos, int(a.alt_tier), a.hp_current, a.spotted_mask,
            int(a.state), a.facing, a.no_engage_until, a.flight_plan, a.task,
            sorted(a.ammo_left.items()), a.alt_pending is not None,
            int(a.patrol_loop), a.paratroop_cargo is not None,
            ("%d/%d/%d" % (d.opponent.id, d.round_timer, d.rounds)) if d else "-"))
    for p in w.projectiles:
        ht = p.hit_target
        parts.append("P%s,%s,%d,%d,%s" % (
            p.pos, p.dest, p.will_hit, p.speed_cm_tick,
            ("A%d" % ht.id) if isinstance(ht, AircraftInstance) else "-"))
    for pl in w.players:
        parts.append("PL%d,%d,%s,%d" % (pl.index, pl.air_points,
                                        sorted(pl.air_cooldowns.items()),
                                        len(pl.deck_slots)))
    for z in w.smoke_zones:                                          # 逐区 center/ttl（返工补全）
        parts.append("S%s,%d" % (z.center, z.ttl_ticks))
    return "|".join(parts)


def rich_world(seed):
    """① 确定性双跑场景：防空交战 + 攻击航线投弹 + 自动缠斗 + 侦察标记 + 地面移动 + 烟雾。"""
    w = make_world(seed)
    add_unit(w, make_unit(w, AA_TPL, 0, 0, (380000, 380000)))
    inf0 = add_unit(w, make_unit(w, INF_TPL, 0, 0, (215000, 211000)))
    inf0.move_path = [(230000, 230000)]
    add_unit(w, make_unit(w, INF_TPL, 1, 1, (600000, 600000)))
    inst(w, FIGHTER_T, 0, (500000, 500000))            # 缠斗对（同点 → dist 0 ≤ 8000）
    inst(w, FIGHTER_T, 1, (500000, 500000))
    b1 = inst(w, BOMBER_T, 1, (390000, 390000))        # strike 靶：inf0 方向的假想点
    b1.ammo_left["BOMB"] = 4
    inst(w, RECON_T, 1, (210000, 210000))              # 标记 inf0（dist≈5099 ≤ 8000）
    w.smoke_zones.append(SmokeZone((300000, 300000), 150))
    cmd_air_strike(w, b1, (400000, 400000), "BOMB")
    return w


class TestDeterminismDualRun(unittest.TestCase):
    def test_dual_run_300_ticks_bit_identical(self):
        # ① 同 seed 两 world 各 300 tick，逐 tick 全状态指纹位级相等
        w1, w2 = rich_world(42), rich_world(42)
        for _ in range(300):
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(fingerprint(w1), fingerprint(w2))
        # 末态锚点（手推时序：AA 第 5/110/215 tick 瞄准、10/115/220 开火、
        # 12/116-117/221-222 落弹——每发 -8 HP；bomber 全程 3 次被命中 30→6）
        b1 = next(a for a in w1.aircraft if a.template is BOMBER_T)
        self.assertEqual(b1.ammo_left["BOMB"], 2)      # salvo=2 × 1 次投放
        aa_ws = w1.units[0].elements[0].weapon_states[0]
        self.assertEqual(aa_ws.ammo_left, 50 - 3)      # 3 轮单发（reload 100 tick）
        self.assertEqual(b1.hp_current, 30 - 3 * 8)    # HE 曲线 800‰ × damage 10
        self.assertEqual(len(w1.smoke_zones), 0)       # ttl 150 < 300 已过滤


class TestAirDefenseChain(unittest.TestCase):
    def _world(self):
        w = make_world(7)
        add_unit(w, make_unit(w, AA_TPL, 0, 0, (0, 0)))
        return w

    def test_spot_aim_fire_hit_sequence(self):
        # ② 防空链全程 + 数值锚点：sense_air（tick5 置位）→ begin_aim（5 tick）→
        # fire_aa（tick10，HIT 通道必中 acc=10000bp）→ 弹丸 3 tick 推进 →
        # resolve_hit_aa（tick12：pen 8/armor_aa 4 → 800‰ → damage 10 → -8 HP）
        w = self._world()
        a = inst(w, atpl(AirRole.BOMBER), team=1, pos=(50000, 0))
        for _ in range(4):
            world_tick(w)
        self.assertEqual(a.spotted_mask, 0)            # 周期门：tick1-4 非 5 倍数不扫
        ws = w.units[0].elements[0].weapon_states[0]
        self.assertIs(ws.state, WState.READY)
        for _ in range(6):                             # 跑到 tick10
            world_tick(w)
        self.assertEqual(a.spotted_mask, 1)            # tick5 sense_air 置位（1<<0）
        self.assertIs(ws.state, WState.RELOADING)      # tick10 fire_aa 已发射
        self.assertEqual(ws.ammo_left, 49)             # 单发耗弹
        self.assertEqual(a.hp_current, 30)             # 弹在途未结算
        self.assertEqual(len(w.projectiles), 1)
        p = w.projectiles[0]
        self.assertIs(p.hit_target, a)
        self.assertTrue(p.will_hit)                    # acc 10000bp → chance_bp 必真
        for _ in range(2):                             # 跑到 tick12：弹到达
            world_tick(w)
        self.assertEqual(len(w.projectiles), 0)
        self.assertEqual(a.hp_current, 30 - 8)         # 10 × 800‰ = 8（HE 曲线锚点）
        self.assertIs(a, w.aircraft[0])                # 未击落（hp>0，击落判定归航空）

    def test_unspotted_aircraft_not_engaged(self):
        # 探测半径外（100000 > 60000）：不置位、不瞄准、不耗弹
        w = self._world()
        a = inst(w, atpl(AirRole.BOMBER), team=1, pos=(100000, 0))
        for _ in range(10):
            world_tick(w)
        self.assertEqual(a.spotted_mask, 0)
        ws = w.units[0].elements[0].weapon_states[0]
        self.assertIs(ws.state, WState.READY)
        self.assertEqual(ws.ammo_left, 50)
        self.assertEqual(len(w.projectiles), 0)

    def test_ceiling_gate_blocks_engagement(self):
        # alt_tier > air_ceiling 不可及（§D.1#8）：HIGH 层机不入 MID 顶防空视野
        w = make_world(7)
        add_unit(w, make_unit(w, AA_TPL_MID_CEILING, 0, 0, (0, 0)))
        a = inst(w, atpl(AirRole.BOMBER), team=1, pos=(50000, 0), alt=AltTier.HIGH)
        for _ in range(10):
            world_tick(w)
        self.assertEqual(a.spotted_mask, 0)            # 名单支 ceiling 门 + 非 LOW 无目视支
        self.assertEqual(len(w.projectiles), 0)


class TestDualClear(unittest.TestCase):
    def test_spot_then_clear_when_out_of_range(self):
        # ③ M17 对偶清位：60000 内置位 → 移出 70000 → 清位 → 移回可续标
        w = make_world(9)
        add_unit(w, make_unit(w, AA_TPL, 0, 0, (0, 0)))
        a = inst(w, atpl(AirRole.BOMBER), team=1, pos=(50000, 0))
        for _ in range(5):
            world_tick(w)
        self.assertEqual(a.spotted_mask, 1)
        a.pos = (70000, 0)                             # 探测半径外（非 LOW：目视支不救）
        for _ in range(5):
            world_tick(w)
        self.assertEqual(a.spotted_mask, 0)            # tick10 sense_air 对偶清位
        a.pos = (50000, 0)
        for _ in range(5):
            world_tick(w)
        self.assertEqual(a.spotted_mask, 1)            # 可续标（非棘轮式永久标记）

    def test_low_altitude_visual_branch(self):
        # 低空目视支（方案2 保留分支）：不入 aa_roster 的普通单位 optics_ground_cm
        # 可目视发现 LOW 层机；抬升到 MID 后目视支失效 → 对偶清位
        w = make_world(9)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        self.assertNotIn(u, w.aa_roster)               # 名单条件锚点（无 AIR 武器且 optics_air=0）
        a = inst(w, atpl(AirRole.BOMBER), team=1, pos=(70000, 0), alt=AltTier.LOW)
        for _ in range(5):
            world_tick(w)
        self.assertEqual(a.spotted_mask, 1)            # 目视支（70000 ≤ optics_ground 80000）
        a.alt_tier = AltTier.MID
        for _ in range(5):
            world_tick(w)
        self.assertEqual(a.spotted_mask, 0)            # 仅 LOW 层可目视


class TestChannelIndependence(unittest.TestCase):
    def test_air_segment_leaves_ground_channels_untouched(self):
        # ④A 航空段（缠斗掷骰/侦察标记/AIR 散布）只消费 AIR 通道
        w = make_world(11)
        inst(w, FIGHTER_T, 0, (500000, 500000))
        inst(w, FIGHTER_T, 1, (500000, 500000))        # dist 0 ≤ dogfight_engage_cm 8000
        r1 = inst(w, RECON_T, 1, (210000, 210000))
        add_unit(w, make_unit(w, INF_TPL, 0, 0, (215000, 211000)))  # 标记靶 dist≈5099 ≤ 8000
        hit0, scat0, air0 = (w.rng.hit().state, w.rng.scatter().state,
                             w.rng.air().state)
        for _ in range(60):
            world_tick(w)
        self.assertEqual(w.rng.hit().state, hit0)      # HIT 通道未被航空段触碰
        self.assertEqual(w.rng.scatter().state, scat0)  # SCATTER 同
        self.assertNotEqual(w.rng.air().state, air0)   # AIR 真被消费（缠斗/标记掷骰）——非平凡前提

    def test_aa_chain_leaves_air_channel_untouched(self):
        # ④B 防空链（fire_aa 命中/散布）只消费 HIT/SCATTER，不扰动 AIR
        w = make_world(13)
        add_unit(w, make_unit(w, AA_TPL, 0, 0, (0, 0)))
        inst(w, atpl(AirRole.BOMBER), team=1, pos=(50000, 0))
        air0, hit0, scat0 = (w.rng.air().state, w.rng.hit().state,
                             w.rng.scatter().state)
        for _ in range(15):                            # tick5 置位→tick10 开火
            world_tick(w)
        self.assertEqual(w.rng.air().state, air0)      # AIR 通道未被防空链触碰
        self.assertNotEqual(w.rng.hit().state, hit0)   # HIT 真被消费
        self.assertNotEqual(w.rng.scatter().state, scat0)  # SCATTER 真被消费（散布 sym×2）


class TestRotatingReset(unittest.TestCase):
    def test_narrow_arc_rotating_reset_each_tick(self):
        # ⑥ v1.7 GAP-25：fire_arc<360 元素每 tick 复位（rotate_step 置位由后续增量承载）
        w = make_world(3)
        u = add_unit(w, make_unit(w, AT_TPL, 0, 0, (100000, 100000)))
        e = u.elements[0]
        e.rotating = True
        world_tick(w)
        self.assertFalse(e.rotating)


class TestVersionPins(unittest.TestCase):
    def test_version_strings_reference_v14(self):
        # ⑤ 瑕疵①（终检报告第九章）：air.py 头部与 tables.py 航空段注释版本引用 v1.4
        air_head = (ROOT / "sovs" / "sim" / "air.py").read_text(encoding="utf-8")[:600]
        self.assertIn("AIR_UNITS_PSEUDOCODE_IMPL_v1.4", air_head)
        tables_src = (ROOT / "sovs" / "sim" / "tables.py").read_text(encoding="utf-8")
        self.assertIn("AIR_UNITS_PSEUDOCODE_IMPL_v1.4", tables_src)
        self.assertNotIn("AIR_UNITS_PSEUDOCODE_IMPL_v1.3", tables_src)


if __name__ == "__main__":
    unittest.main()
