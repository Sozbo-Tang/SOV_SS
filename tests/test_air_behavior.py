"""航空行为层锚点测试：AIR_UNITS_PSEUDOCODE_IMPL_v1.2 行为层（air.py 第二批）。

覆盖三轮修复的行为验证：GAP2-03 非实战期挂起回 INGRESS、GAP2-04 STRAFE 弹药来源、
GAP2-05/11 弹尽自动 RTB 资格门与 STRIKE 豁免、GAP2-06 patrol 门 AIRDROP 变体、
GAP2-08 engage 开拨实战门、GAP2-13 容量门、B-22 RTB 不可逆、B-24 在空≤2、
B-25 冷却 MAX、B-27② 返场退份、AMB-08 到达回收、缠斗族（进入/击落对偶清理/脱离）、
空投链（补给箱/投放费/丢弹不分敌我）。
"""
import unittest
from types import SimpleNamespace

from sovs.sim.air import (PHASE_COMBAT, PHASE_DEPLOY, PHASE_SETTLE,
                          AircraftInstance,
                          AircraftTemplate, AirRole, AirState, StrikePhase,
                          TaskKind, _weapon_of, aircraft_tick, air_recovery,
                          air_recon_step, air_shooter_view, cmd_air_airdrop,
                          cmd_air_call, cmd_air_engage_air, cmd_air_move,
                          cmd_air_patrol, cmd_air_rtb, cmd_air_strike,
                          dogfight_check, dump_bombs, enter_dogfight,
                          exit_dogfight, resolve_strafe)
from sovs.sim.rng import Channels
from sovs.sim.tables import CONFIG
from sovs.sim.types import (AltTier, DamageType, ElementInstance, ElementTemplate,
                            ElementType, Trajectory, UnitType, WeaponTemplate)

STRAFE_W = WeaponTemplate(name="STRAFE", damage_type=DamageType.KE,
                          target_mask=1, trajectory=Trajectory.DIRECT,
                          damage=4, pen_max=8, salvo=4, max_range_cm=100000)
BOMB_W = WeaponTemplate(name="BOMB", damage_type=DamageType.HE,
                        target_mask=1, trajectory=Trajectory.BALLISTIC,
                        damage=20, blast_radius_cm=2500, salvo=2,
                        dispersion_cm=1000, projectile_speed_cm_tick=500)
VYA_W = WeaponTemplate(name="VYa-23", damage_type=DamageType.KE,
                       target_mask=1, trajectory=Trajectory.DIRECT,
                       damage=4, pen_max=8, salvo=4, max_range_cm=100000)
STRAFE_HE_W = WeaponTemplate(name="STRAFE", damage_type=DamageType.HE,
                             target_mask=1, trajectory=Trajectory.DIRECT,
                             damage=4, blast_radius_cm=1000, salvo=2,
                             max_range_cm=100000)


def tpl(role, **kw):
    d = dict(template_id=1, name="T", role=role, cost_body=70, hp_max=30,
             armor_aa=4, speed_cm_tick=100, dogfight_power=10, maneuver=8,
             alt_ceiling=AltTier.HIGH, weapons=(), payload_max_bombs=4,
             payload_max_supply=600, paratroop_seats=0, turret_damage=0,
             can_engage_air=False, has_dive=False, payload_price={"BOMB": 5})
    d.update(kw)
    return AircraftTemplate(**d)


def mkworld(phase=PHASE_COMBAT, tick=0):
    w = SimpleNamespace(
        aircraft=[], projectiles=[], units=[], players=[], tick=tick, phase=phase,
        map_center=(500000, 500000), beacon_by_unit={}, cloud_tier=0,
        # ⑤块（2026-10-02）地面伤害链消费面：resolve_strafe→apply_damage→
        # destroy_element 读 await_resupply/tow_pairs/mount_requests/cover_by_target
        # （对齐 tick.World 字段——空表/None 即惰性无行为）
        await_resupply=[], tow_pairs=[], mount_requests=None, cover_by_target={},
        next_aircraft_id=1, rng=Channels(42),
        spawn_paratroop=lambda *a: setattr(w, "paratroop_calls", getattr(w, "paratroop_calls", []) + [a]),
        spawn_airdrop_crate=lambda *a: setattr(w, "crate_calls", getattr(w, "crate_calls", []) + [a]),
    )
    w.air_entry_point = lambda team: (500000, -40000 if team == 0 else 1040000)
    w.rtb_exit_point = lambda team: (500000, -40000 if team == 0 else 1040000)
    p0 = SimpleNamespace(index=0, team=0, air_points=1000, air_cooldowns={}, deck_slots=[])
    p1 = SimpleNamespace(index=1, team=1, air_points=1000, air_cooldowns={}, deck_slots=[])
    w.players = [p0, p1]
    return w


def inst(w, t, team=0, pos=(500000, 500000)):
    a = AircraftInstance(id=w.next_aircraft_id, team=team, player_index=team,
                         template=t, pos=pos, alt_tier=AltTier.MID,
                         hp_current=t.hp_max, state=AirState.PATROL)
    w.next_aircraft_id += 1
    a.ammo_left = {"BOMB": 0, "STRAFE": 0, "SUPPLY": 0}
    w.aircraft.append(a)
    return a


class TestCallGates(unittest.TestCase):
    def test_strafe_ammo_from_weapons(self):
        # GAP2-04：STRAFE 弹药 ← weapons[] 弹量（FIGHTER 呼叫即有弹）
        w = mkworld()
        t = tpl(AirRole.FIGHTER, weapons=((STRAFE_W, 12),))
        a = cmd_air_call(w, w.players[0], t, {})
        self.assertIsNotNone(a)
        self.assertEqual(a.ammo_left["STRAFE"], 12)
        self.assertEqual(a.state, AirState.INBOUND)  # 进场航点在（GAP-04）
        self.assertTrue(a.flight_plan)

    def test_capacity_gate(self):
        # GAP2-13：超容量载荷 REJECT
        w = mkworld()
        t = tpl(AirRole.BOMBER, weapons=((BOMB_W, 2),))
        self.assertIsNone(cmd_air_call(w, w.players[0], t, {"BOMB": 5}))
        self.assertIsNotNone(cmd_air_call(w, w.players[0], t, {"BOMB": 4}))

    def test_same_type_max_two(self):
        # B-24：同型在空 ≤2
        w = mkworld()
        t = tpl(AirRole.FIGHTER, template_id=9)
        for _ in range(2):
            self.assertIsNotNone(cmd_air_call(w, w.players[0], t, {}))
        self.assertIsNone(cmd_air_call(w, w.players[0], t, {}))

    def test_slot_ok_gate(self):
        # GAP2-26：FIGHTER 不可挂炸弹
        w = mkworld()
        self.assertIsNone(cmd_air_call(w, w.players[0], tpl(AirRole.FIGHTER), {"BOMB": 1}))


class TestNonCombatSuspend(unittest.TestCase):
    def test_strike_suspends_outside_combat_and_resumes(self):
        # GAP2-03：非实战期（盲部署/结算）飞到 run_start 保持 INGRESS（不结算不转
        # RUN）；实战即转 RUN。2026-10-03 拍板：禁火相位取消，本测试改用盲部署期锚定
        w = mkworld(phase=PHASE_DEPLOY)
        a = inst(w, tpl(AirRole.ATTACK, weapons=((STRAFE_W, 12),)))
        a.ammo_left["STRAFE"] = 12
        self.assertTrue(cmd_air_strike(w, a, (600000, 500000), "STRAFE"))
        self.assertEqual(a.task.phase, StrikePhase.INGRESS)
        a.pos = a.task.run_start  # 直达 run_start
        aircraft_tick(w)
        self.assertEqual(a.task.phase, StrikePhase.INGRESS)  # 非实战期悬停
        w.phase = PHASE_COMBAT
        aircraft_tick(w)
        self.assertEqual(a.task.phase, StrikePhase.RUN)  # 实战即扫射结算（弹已耗）


class TestAutoRtb(unittest.TestCase):
    def test_recon_never_auto_rtb(self):
        # GAP2-05：无武器且无载荷舱机型（侦察机）空弹药表不触发"进场即返场"
        # （payload_max_supply=0——RECON 数据侧无补给舱，§D.1）
        w = mkworld()
        a = inst(w, tpl(AirRole.RECON, weapons=(), payload_max_supply=0))
        aircraft_tick(w)
        self.assertEqual(a.state, AirState.PATROL)

    def test_transport_auto_rtb_after_delivery(self):
        # GAP3-02（v1.3 回归修复）：运输机（无 weapons、有补给舱资格）投完自动 RTB
        w = mkworld()
        t = tpl(AirRole.TRANSPORT, weapons=(), payload_max_supply=600, payload_price={})
        a = inst(w, t)
        a.ammo_left["SUPPLY"] = 0
        a.paratroop_cargo = None
        aircraft_tick(w)
        self.assertEqual(a.state, AirState.RTB)

    def test_fighter_rtb_when_dry_but_not_in_strike(self):
        # GAP2-05/11：FIGHTER 弹尽自动 RTB；STRIKE 态（RUN）豁免
        w = mkworld()
        a = inst(w, tpl(AirRole.FIGHTER, weapons=((STRAFE_W, 0),)))
        a.ammo_left["STRAFE"] = 0
        aircraft_tick(w)
        self.assertEqual(a.state, AirState.RTB)  # PATROL 弹尽→RTB
        b = inst(w, tpl(AirRole.ATTACK, weapons=((STRAFE_W, 4),)))
        b.ammo_left["STRAFE"] = 4
        self.assertTrue(cmd_air_strike(w, b, (600000, 500000), "STRAFE"))
        b.task.phase = StrikePhase.RUN  # 模拟 RUN 中
        b.ammo_left["STRAFE"] = 0
        aircraft_tick(w)
        self.assertEqual(b.state, AirState.STRIKE)  # RUN 不截断走廊


class TestCommandGates(unittest.TestCase):
    def test_patrol_gate_blocks_airdrop_egress(self):
        # GAP2-06：AIRDROP RUN/EGRESS 不可被巡逻令中断
        w = mkworld()
        t = tpl(AirRole.TRANSPORT, payload_price={})
        a = inst(w, t)
        a.ammo_left["SUPPLY"] = 100
        self.assertTrue(cmd_air_airdrop(w, a, (600000, 500000)))
        a.task.phase = StrikePhase.EGRESS
        self.assertFalse(cmd_air_patrol(w, a, (0, 0), 1000))
        a.task.phase = StrikePhase.INGRESS
        self.assertTrue(cmd_air_patrol(w, a, (0, 0), 1000))  # INGRESS 可改

    def test_rtb_irreversible(self):
        # B-22/AMB2-05：RTB 态拒 strike/patrol/move/engage 全族
        w = mkworld()
        a = inst(w, tpl(AirRole.FIGHTER, weapons=((STRAFE_W, 12),), can_engage_air=True))
        cmd_air_rtb(w, a)
        self.assertFalse(cmd_air_strike(w, a, (600000, 500000), "STRAFE"))
        self.assertFalse(cmd_air_patrol(w, a, (0, 0), 1000))
        self.assertFalse(cmd_air_move(w, a, [(0, 0)]))
        self.assertFalse(cmd_air_engage_air(w, a, True))

    def test_engage_air_noncombat_reject_and_dump(self):
        # GAP2-08：非实战期开拨 REJECT；实战开拨触发丢弹（BOMB 清零+BALLISTIC 弹丸）
        w = mkworld(phase=PHASE_DEPLOY)
        a = inst(w, tpl(AirRole.ATTACK, can_engage_air=True, weapons=((BOMB_W, 2),)))
        a.engage_air = False
        a.ammo_left["BOMB"] = 2
        self.assertFalse(cmd_air_engage_air(w, a, True))
        w.phase = PHASE_COMBAT
        self.assertTrue(cmd_air_engage_air(w, a, True))
        self.assertEqual(a.ammo_left["BOMB"], 0)
        self.assertEqual(len(w.projectiles), 2)
        for p in w.projectiles:
            self.assertIsNone(p.hit_target)  # 不分敌我
            self.assertIs(p.trajectory, Trajectory.BALLISTIC)


class TestEconomy(unittest.TestCase):
    def test_recovery_refund_and_paratroop_return(self):
        # AMB-08/B-27②：到达 RTB 航点回收——退本体价、舱内班退 deck 份
        w = mkworld()
        deck_tpl = object()
        slot = SimpleNamespace(template=deck_tpl, copies_left=1)
        w.players[0].deck_slots = [slot]
        t = tpl(AirRole.TRANSPORT, cost_body=40, paratroop_seats=1, payload_price={})
        a = cmd_air_call(w, w.players[0], t, {"PARATROOP": deck_tpl})
        self.assertEqual(slot.copies_left, 0)  # 装机扣份
        self.assertEqual(w.players[0].air_points, 1000 - 40)
        a.state = AirState.RTB
        a.flight_plan = []
        aircraft_tick(w)  # RTB 到达→回收
        self.assertNotIn(a, w.aircraft)
        self.assertEqual(w.players[0].air_points, 1000)  # 本体价回收
        self.assertEqual(slot.copies_left, 1)  # 班退份（B-27②）
        self.assertGreater(w.players[0].air_cooldowns[1], w.tick)

    def test_downed_cooldown_max_not_overwritten(self):
        # B-25/GAP-06：击落长冷却不被后返场短冷却覆写
        w = mkworld()
        t = tpl(AirRole.FIGHTER, template_id=5)
        a1 = inst(w, t)
        a1.hp_current = 0
        aircraft_tick(w)  # 击落
        long_cd = w.players[0].air_cooldowns[5]
        a2 = inst(w, t)
        a2.hp_current = t.hp_max
        air_recovery(w, a2)  # 满血返场短冷却
        self.assertEqual(w.players[0].air_cooldowns[5], long_cd)  # MAX 保持


class TestDogfight(unittest.TestCase):
    def test_pair_and_survivor_release(self):
        # GAP-16：驱动方被击落→幸存方同拍对偶清理回 PATROL
        w = mkworld()
        fa = tpl(AirRole.FIGHTER, dogfight_power=99, maneuver=20, payload_max_supply=0)
        fb = tpl(AirRole.FIGHTER, dogfight_power=1, maneuver=1, payload_max_supply=0)
        a = inst(w, fa, team=0)
        b = inst(w, fb, team=1)
        enter_dogfight(w, a, b)
        # 驱动 40 回合（id 小侧 a 驱动；power 99 vs 1+1 → p=MIN(10000,3000×99//2)=10000 必杀 b）
        for _ in range(45):
            aircraft_tick(w)
            if b not in w.aircraft:
                break
        self.assertNotIn(b, w.aircraft)  # b 被击落
        self.assertEqual(a.state, AirState.PATROL)  # 幸存方解锁（remove_aircraft 对偶清理）
        self.assertIsNone(a.dogfight)

    def test_third_fighter_cannot_hijack(self):
        # GAP-09：一对一成对——第三机不可对已缠斗目标发起
        w = mkworld()
        a = inst(w, tpl(AirRole.FIGHTER, dogfight_power=1, maneuver=20), team=0)
        b = inst(w, tpl(AirRole.FIGHTER, dogfight_power=1, maneuver=20), team=1)
        c = inst(w, tpl(AirRole.FIGHTER, dogfight_power=1, maneuver=20), team=0)
        enter_dogfight(w, a, b)
        dogfight_check(w)
        self.assertIsNone(c.dogfight)  # c 未被牵入
        self.assertIsNotNone(a.dogfight)


class TestAirdropChain(unittest.TestCase):
    def test_supply_drop_calls_crate_and_fee(self):
        # 空投补给：world.spawn_airdrop_crate 回调（契约④，一池重量）+ 载荷清零
        w = mkworld()
        t = tpl(AirRole.TRANSPORT, paratroop_seats=1, payload_price={})
        a = inst(w, t)
        a.ammo_left["SUPPLY"] = 120
        self.assertTrue(cmd_air_airdrop(w, a, (600000, 500000)))
        a.pos = a.task.run_start
        aircraft_tick(w)  # INGRESS→RUN（实战）→……需越线；直接调内部
        from sovs.sim.air import resolve_airdrop
        resolve_airdrop(w, a, a.task)
        self.assertEqual(len(w.crate_calls), 1)
        team, land, weight = w.crate_calls[0]
        self.assertEqual((team, weight), (0, 120))
        self.assertEqual(a.ammo_left["SUPPLY"], 0)

    def test_paratroop_drop_and_fee(self):
        # D017：空降兵落地走地面管线回调 + 投放费
        w = mkworld()
        deck_tpl = object()
        t = tpl(AirRole.TRANSPORT, paratroop_seats=1, payload_price={})
        a = inst(w, t)
        a.paratroop_cargo = deck_tpl
        self.assertTrue(cmd_air_airdrop(w, a, (600000, 500000)))
        from sovs.sim.air import resolve_airdrop
        points_before = w.players[0].air_points
        resolve_airdrop(w, a, a.task)
        self.assertEqual(len(w.paratroop_calls), 1)
        self.assertIsNone(a.paratroop_cargo)
        self.assertEqual(w.players[0].air_points, points_before - CONFIG.airdrop_fee_points)


class TestReconSensing(unittest.TestCase):
    def test_recon_marks_ground_unit(self):
        # GAP2-01/B-23：recon 独立挂点（sensing 后、交战前）写 spotted/mark_level
        from sovs.sim.types import MarkLevel
        w = mkworld()
        a = inst(w, tpl(AirRole.RECON, optics_air_cm=8000, recon_mark_base_bp=10000))
        u = SimpleNamespace(team=1, alive=True, pos=(500000, 500000),
                            spotted_mask=0, mark_level=MarkLevel.NONE)
        w.units = [u]
        air_recon_step(w)  # mark_base 10000 → 必标记（发现者 team=0 → 置位 1<<0）
        self.assertEqual(u.spotted_mask, 0b01)
        self.assertEqual(u.mark_level, MarkLevel.SPOTTED)

    def test_recon_marks_outside_settle_phase(self):
        # B-30①（AMB3-04）：相位门=结算门——盲部署期航空侦察照常标记（与地面 sensing 同门）
        from sovs.sim.types import MarkLevel
        w = mkworld(phase=PHASE_DEPLOY)
        a = inst(w, tpl(AirRole.RECON, optics_air_cm=8000, recon_mark_base_bp=10000))
        u = SimpleNamespace(team=1, alive=True, pos=(500000, 500000),
                            spotted_mask=0, mark_level=MarkLevel.NONE)
        w.units = [u]
        air_recon_step(w)
        self.assertEqual(u.spotted_mask, 0b01)
        w.phase = PHASE_SETTLE  # 结算期停止
        u.spotted_mask = 0
        air_recon_step(w)
        self.assertEqual(u.spotted_mask, 0)


class TestWeaponSlotIdentity(unittest.TestCase):
    def test_weapon_slot_by_config_not_name(self):
        # 复检①：§D.3 档身份按配置判定（weapon_slot 统一口径），与 name 无关——
        # name='VYa-23' 的合规 DIRECT/KE/GROUND 档：弹药入账 + _weapon_of 可寻 +
        # resolve_strafe 实际消耗（修复前 name 匹配找不到档 → 静默不射）
        w = mkworld()
        a = cmd_air_call(w, w.players[0],
                         tpl(AirRole.FIGHTER, weapons=((VYA_W, 12),)), {})
        self.assertIsNotNone(a)
        self.assertEqual(a.ammo_left["STRAFE"], 12)              # 配置合规 → 弹药入账
        self.assertIs(_weapon_of(a, "STRAFE"), VYA_W)            # 档身份可寻（不再按 name）
        # 地面靶单位（⑤块起 strafe 命中走 apply_damage→destroy_element 完整链——
        # SimpleNamespace 缺 weapon_states/条件槽字段，改用真实 ElementInstance 载体）
        u = SimpleNamespace(id=901, team=1, alive=True, pos=(600000, 500000),
                            elements=[])
        gtpl = ElementTemplate(element_type=ElementType.SQUAD,
                               unit_type=UnitType.INFANTRY, hp_max=10)
        # 〔P1 机制块 2026-10-13：resolve_strafe 改「沿全航道无差别落点」
        # （manual.txt:413-416）——单靶不再必然中，靶面改沿走廊密集铺（每
        # 1000cm 一枚单元素单位，走廊半宽 1500cm 内落点恒有最近靶），断言
        # 口径=全靶面聚合伤害（acc 10000 → salvo×damage 恒中）。〕
        targets = []
        for i in range(-8, 9):
            tu = SimpleNamespace(id=901 + i, team=1, alive=True,
                                 pos=(600000, 500000 + i * 1000), elements=[])
            tx = ElementInstance(id=1, unit=tu, template=gtpl,
                                 pos=(600000, 500000 + i * 1000), hp_current=10)
            tu.elements = [tx]
            targets.append((tu, tx))
        w.units = [tu for tu, _ in targets]
        self.assertTrue(cmd_air_strike(w, a, (600000, 500000), "STRAFE"))
        resolve_strafe(w, a, a.task)
        self.assertEqual(a.ammo_left["STRAFE"], 12 - VYA_W.salvo)  # 无差别落点照耗弹
        self.assertEqual(sum(10 - tx.hp_current for _tu, tx in targets),
                         VYA_W.salvo * VYA_W.damage)               # 恒命中（acc 10000）
        # name='STRAFE' 的非合规档（HE 非 KE）不被误认：弹药不入账、_weapon_of 不可寻
        b = cmd_air_call(w, w.players[0],
                         tpl(AirRole.FIGHTER, template_id=2,
                             weapons=((STRAFE_HE_W, 5),)), {})
        self.assertIsNotNone(b)
        self.assertEqual(b.ammo_left["STRAFE"], 0)
        self.assertIsNone(_weapon_of(b, "STRAFE"))

    def test_air_shooter_view_hp_is_template_hp_max(self):
        # 复检②（§D.3 GAP-17 成文）：shooter.hp_current=hp_max 语义——飞机已受损仍取模板满值
        w = mkworld()
        a = inst(w, tpl(AirRole.FIGHTER))
        a.hp_current = a.template.hp_max - 7                     # 已受损
        v = air_shooter_view(a)
        self.assertEqual(v.hp_current, a.template.hp_max)
        self.assertNotEqual(v.hp_current, a.hp_current)


if __name__ == "__main__":
    unittest.main()
