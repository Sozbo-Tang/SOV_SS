"""航空命令层锚点测试（AIR_UNITS_PSEUDOCODE_IMPL_v1.4 §D.5 九命令——2026-10-07
空中闭环·块1）：命令类+分派支真调用（queue_command→consume_commands 命令流路径，
契约⑦"AI 虚拟玩家走同一接口"）；处理体 air.py cmd_air_* 族行为面锚点既有
（tests/test_air_behavior.py 直调口径），本文件锚定**命令流可达性**与
**命令层零掷骰**（分派不触任何 PCG32 通道——AirDisengageCmd 的 tail 掷骰属
§F4 处理体掷 AIR 通道，非命令层掷骰）。

块1 连带规格对齐（§F3 字面——resolve_strafe 命中支切 combat.resolve_hit）：
命中面压制注入 + compute_hit_facing 覆盖序（驻楼 REAR/转向 SIDE/顶攻 TOP）——
原直扣实现恒 TOP 且零压制，与地面 TOP 分支不等价（air.py 头注预留切换点执行）。
"""
import unittest
from dataclasses import replace

from sovs.sim.air import (AirRole, AirState, AircraftInstance, AircraftTemplate,
                          TaskKind, cmd_air_call, enter_dogfight, resolve_strafe)
from sovs.sim.air_data import IL2M, LI2, YAK9
from sovs.sim.geom import dist_cm
from sovs.sim.tables import CONFIG
from sovs.sim.tick import (AirAirdropCmd, AirAltCmd, AirCallCmd, AirDisengageCmd,
                           AirEngageAirCmd, AirMoveCmd, AirPatrolCmd, AirRTBCmd,
                           AirStrikeCmd, DeckSlot, add_unit, consume_commands,
                           make_unit, make_world, queue_command)
from sovs.sim.types import (AltTier, DamageType, ElementTemplate, ElementType,
                            MovementClass, TargetDomain, Trajectory, UnitTemplate,
                            UnitType, WeaponTemplate)

# 合成扫射档（锚点服务：acc 10000=恒命中可手推；acc 0=恒未命中走 jitter 支）
SURE_STRAFE_W = WeaponTemplate(
    name="sure strafe", target_mask=TargetDomain.GROUND,
    damage_type=DamageType.KE, damage=3, pen_max=20, salvo=2,
    accuracy_base_bp=10000, max_range_cm=100000, blast_radius_cm=0,
    projectile_speed_cm_tick=2000, trajectory=Trajectory.DIRECT,
    suppression_power=40)
MISS_STRAFE_W = WeaponTemplate(
    name="miss strafe", target_mask=TargetDomain.GROUND,
    damage_type=DamageType.KE, damage=3, pen_max=20, salvo=2,
    accuracy_base_bp=0, max_range_cm=100000, blast_radius_cm=0,
    projectile_speed_cm_tick=2000, trajectory=Trajectory.DIRECT,
    suppression_power=40)
TARGET_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                              unit_type=UnitType.INFANTRY, hp_max=20)
TARGET_TPL = UnitTemplate(
    template_id=380, name="strafe target", category=1, cost=50,
    element_templates=(TARGET_ELEM,), optics_ground_cm=100000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)


def mk_tpl(role, **kw):
    d = dict(template_id=99, name="T", role=role, cost_body=70, hp_max=30,
             armor_aa=4, speed_cm_tick=100, dogfight_power=0, maneuver=5,
             alt_ceiling=AltTier.HIGH, weapons=(), payload_max_bombs=4,
             payload_max_supply=0, paratroop_seats=0, turret_damage=0,
             can_engage_air=False, has_dive=False, payload_price={})
    d.update(kw)
    return AircraftTemplate(**d)


def call(w, player, template, payload):
    """经命令流呼叫（TestAirCommandDispatch 全链惯例：写点走
    queue_command→consume_commands；TestStrafeResolveHit 直调处理体——
    其锚定目标是 resolve_strafe 结算面而非命令流）。"""
    queue_command(w, AirCallCmd(player=player, template=template, payload=payload))
    consume_commands(w)
    return w.aircraft[-1] if w.aircraft else None


def _rng_states(w):
    return [r.state for r in w.rng._rngs]


class TestAirCommandDispatch(unittest.TestCase):
    def test_air_call_cmd(self):
        # §F1 呼叫经命令流：扣费（本体+载荷价）/INBOUND/弹药初始化（GAP2-04）
        w = make_world(42)
        p = w.players[0]
        before = p.air_points
        a = call(w, p, IL2M, {"BOMB": 2})
        self.assertIsNotNone(a)
        self.assertIs(a.state, AirState.INBOUND)
        self.assertEqual(p.air_points,
                         before - (IL2M.cost_body + IL2M.payload_price["BOMB"] * 2))
        self.assertEqual(a.ammo_left["BOMB"], 2)
        self.assertEqual(a.ammo_left["STRAFE"], 24)   # weapons[] STRAFE 档弹量

    def test_air_call_cmd_paratroop_deck_slot(self):
        # D017/B-12：装机即扣 deck 份（命令流路径）
        w = make_world(42)
        p = w.players[0]
        ground_tpl = object()                          # 身份对表（slot.template is tpl）
        p.deck_slots = [DeckSlot(ground_tpl, 1)]
        a = call(w, p, LI2, {"PARATROOP": ground_tpl})
        self.assertIsNotNone(a)
        self.assertEqual(p.deck_slots[0].copies_left, 0)
        self.assertIs(a.paratroop_cargo, ground_tpl)

    def test_air_move_cmd(self):
        # §F2 改航：task 清空/盘旋旗落/航点替换
        w = make_world(42)
        a = call(w, w.players[0], YAK9, {})
        path = [(400000, 400000), (300000, 300000)]
        queue_command(w, AirMoveCmd(aircraft=a, path=path))
        consume_commands(w)
        self.assertIsNone(a.task)
        self.assertFalse(a.patrol_loop)
        self.assertEqual(a.flight_plan, path)

    def test_air_patrol_cmd(self):
        # §F2/B-20 CAP 入口：PATROL 任务槽+方形环路航点
        w = make_world(42)
        a = call(w, w.players[0], YAK9, {})
        queue_command(w, AirPatrolCmd(aircraft=a, center=(400000, 400000),
                                      radius=3000))
        consume_commands(w)
        self.assertIs(a.task.kind, TaskKind.PATROL)
        self.assertEqual((a.task.center, a.task.radius), ((400000, 400000), 3000))
        self.assertTrue(a.patrol_loop)
        self.assertEqual(a.flight_plan[0], (397000, 397000))

    def test_air_alt_cmd(self):
        # §F2/B-08 高度过渡：alt_pending 写入
        w = make_world(42)
        a = call(w, w.players[0], YAK9, {})            # entry_tier=MIN(MID, HIGH)=MID
        self.assertIs(a.alt_tier, AltTier.MID)
        queue_command(w, AirAltCmd(aircraft=a, tier=AltTier.HIGH))
        consume_commands(w)
        self.assertEqual(a.alt_pending, (AltTier.HIGH, CONFIG.alt_transition_ticks))

    def test_air_strike_cmd(self):
        # §F3 attack run 建立：STRIKE 任务槽/INGRESS/航点=run_start
        w = make_world(42)
        a = call(w, w.players[0], IL2M, {"BOMB": 2})
        queue_command(w, AirStrikeCmd(aircraft=a, target=(600000, 600000),
                                      weapon="BOMB"))
        consume_commands(w)
        self.assertIs(a.state, AirState.STRIKE)
        self.assertIs(a.task.kind, TaskKind.STRIKE)
        self.assertEqual(a.task.weapon, "BOMB")
        self.assertEqual(a.task.phase, 0)              # StrikePhase.INGRESS
        self.assertEqual(a.flight_plan, [a.task.run_start])

    def test_air_airdrop_cmd(self):
        # §F3 空投任务建立（TRANSPORT+载荷门）
        w = make_world(42)
        a = call(w, w.players[0], LI2, {"SUPPLY": 100})
        queue_command(w, AirAirdropCmd(aircraft=a, drop_point=(600000, 600000)))
        consume_commands(w)
        self.assertIs(a.state, AirState.STRIKE)
        self.assertIs(a.task.kind, TaskKind.AIRDROP)
        self.assertEqual(a.task.drop, (600000, 600000))

    def test_air_engage_air_cmd(self):
        # §F4 转对空开关（FIGHTER 槽就位、实战期开拨）
        w = make_world(42)
        a = call(w, w.players[0], YAK9, {})
        self.assertFalse(a.engage_air)                 # AMB2-02 构造默认 False
        queue_command(w, AirEngageAirCmd(aircraft=a, engage=True))
        consume_commands(w)
        self.assertTrue(a.engage_air)

    def test_air_rtb_cmd(self):
        # §F2/B-22 RTB 不可逆：state=RTB、航点=己方场外点
        w = make_world(42)
        a = call(w, w.players[0], YAK9, {})
        queue_command(w, AirRTBCmd(aircraft=a))
        consume_commands(w)
        self.assertIs(a.state, AirState.RTB)
        self.assertEqual(a.flight_plan, [w.rtb_exit_point(a.team)])

    def test_air_disengage_cmd(self):
        # §F4 缠斗脱离经命令流：tail 掷骰（dogfight_power=0 → tail_p=0 恒成功）→
        # 双方同拍解缠（GAP-08）+免咬窗（world_tick 全链不重咬）
        from sovs.sim.tick import world_tick
        w = make_world(42)
        t0 = mk_tpl(AirRole.FIGHTER)                   # power=0 → 对手 tail_p=0
        t1 = mk_tpl(AirRole.FIGHTER, template_id=98, maneuver=5)
        a = call(w, w.players[0], t0, {})
        b = call(w, w.players[1], t1, {})
        enter_dogfight(w, a, b)
        self.assertIs(a.state, AirState.DOGFIGHT)
        queue_command(w, AirDisengageCmd(aircraft=a))
        world_tick(w)
        self.assertIsNone(a.dogfight)
        self.assertIsNone(b.dogfight)                  # OPPONENT_LEFT 同拍解缠
        self.assertIs(a.state, AirState.PATROL)        # exit→enter_patrol_hold
        self.assertGreaterEqual(a.no_engage_until, w.tick)

    def test_command_layer_zero_dice(self):
        # 命令分派零掷骰：非 disengage 八命令批量落地、八通道 state 全不动
        w = make_world(42)
        p = w.players[0]
        s0 = _rng_states(w)
        a = call(w, p, IL2M, {"BOMB": 2})
        for cmd in (AirMoveCmd(aircraft=a, path=[(400000, 400000)]),
                    AirPatrolCmd(aircraft=a, center=(400000, 400000), radius=3000),
                    AirAltCmd(aircraft=a, tier=AltTier.HIGH),
                    AirStrikeCmd(aircraft=a, target=(600000, 600000), weapon="STRAFE"),
                    AirAirdropCmd(aircraft=a, drop_point=(600000, 600000)),
                    AirEngageAirCmd(aircraft=a, engage=False),
                    AirRTBCmd(aircraft=a)):
            queue_command(w, cmd)
        consume_commands(w)
        self.assertEqual(_rng_states(w), s0)           # 分派本体不触任何通道


class TestStrafeResolveHit(unittest.TestCase):
    """块1 规格对齐锚：§F3 命中支走 combat.resolve_hit（Projectile{top_attack=TRUE}
    即时结算 B-13）——命中面压制注入（原直扣实现缺失的行为面）+伤害照常。"""

    def _world_with_target(self):
        w = make_world(7)
        u = add_unit(w, make_unit(w, TARGET_TPL, 1, 0, (500000, 500000)))
        return w, u.elements[0]

    def _strike(self, w, weapon):
        a = cmd_air_call(w, w.players[0],
                         mk_tpl(AirRole.ATTACK, template_id=97,
                                weapons=((weapon, 10),), payload_max_bombs=0,
                                payload_price={}), {})
        self.assertIsNotNone(a)
        from sovs.sim.air import cmd_air_strike
        self.assertTrue(cmd_air_strike(w, a, (500000, 500000), "STRAFE"))
        resolve_strafe(w, a, a.task)
        return a

    def test_hit_injects_suppression_and_damage(self):
        # 恒命中（acc 10000）：2 发×3 伤 → hp 20→14；每发命中注入 40 压制
        # （falloff(d=0)=10000 满衰减）→ suppression=80——切换前该值为 0（判别锚）
        w, x = self._world_with_target()
        a = self._strike(w, SURE_STRAFE_W)
        self.assertEqual(a.ammo_left["STRAFE"], 10 - SURE_STRAFE_W.salvo)
        self.assertEqual(x.hp_current, 20 - 2 * 3)
        self.assertEqual(x.suppression, 80)

    def test_miss_jitter_suppression_no_damage(self):
        # 恒未命中（acc 0）：jitter 近失压制（>0 可判别）+零伤害
        w, x = self._world_with_target()
        a = self._strike(w, MISS_STRAFE_W)
        self.assertEqual(x.hp_current, 20)
        self.assertGreater(x.suppression, 0)
        self.assertEqual(a.ammo_left["STRAFE"], 10 - MISS_STRAFE_W.salvo)


class TestCfgThreading(unittest.TestCase):
    """空裁6 cfg 穿线锚（2026-10-07 发起人拍板采纳补齐）：cmd_air_alt/strike/
    airdrop 三处理体补 cfg 形参（原直读全局 CONFIG——块1 评审留档③）+分派支
    补传。覆写 cfg 经命令流落地（consume_commands cfg 实参→_dispatch_command→
    处理体），三支各断言取覆写值。异值 77/13000 ≠ 全局 30/8000：「实现读 cfg」
    与「实现读全局 CONFIG」两种实现可判别——任一支回退读全局/分派支漏传 cfg，
    三锚即崩（77≠30、13000≠8000 均可整除无损判读）。"""

    ALT_OV = 77          # 覆写 alt_transition_ticks（全局 30）
    LEAD_OV = 13000      # 覆写 strafe_run_lead_cm（全局 8000）

    def _ov_cfg(self):
        # 异值前提自证：覆写值确异于全局现值（判别力成立条件随全局值漂移仍守恒）
        self.assertNotEqual(self.ALT_OV, CONFIG.alt_transition_ticks)
        self.assertNotEqual(self.LEAD_OV, CONFIG.strafe_run_lead_cm)
        return replace(CONFIG, alt_transition_ticks=self.ALT_OV,
                       strafe_run_lead_cm=self.LEAD_OV)

    def test_alt_pending_ticks_reads_override_cfg(self):
        # cmd_air_alt：alt_pending=(tier, 覆写 77)——读全局则 30
        w = make_world(42)
        a = call(w, w.players[0], YAK9, {})            # alt_ceiling=HIGH、当前 MID
        queue_command(w, AirAltCmd(aircraft=a, tier=AltTier.HIGH))
        consume_commands(w, self._ov_cfg())
        self.assertEqual(a.alt_pending, (AltTier.HIGH, self.ALT_OV))

    def test_strike_run_start_reads_override_cfg(self):
        # cmd_air_strike：run_start 距 target=覆写 lead 13000——读全局则 8000。
        # 正北攻击线（dx=0/dy>0→octant 0°→DIR8[0]=(0,7)，scale 无整除损耗：
        # run_start=target-(0,lead)，距离=lead 原值）
        w = make_world(42)
        a = call(w, w.players[0], IL2M, {"BOMB": 2})
        a.pos = (500000, 500000)
        target = (500000, 600000)
        queue_command(w, AirStrikeCmd(aircraft=a, target=target, weapon="BOMB"))
        consume_commands(w, self._ov_cfg())
        self.assertIs(a.state, AirState.STRIKE)
        self.assertEqual(a.task.run_start, (500000, 600000 - self.LEAD_OV))
        self.assertEqual(dist_cm(a.task.run_start, target), self.LEAD_OV)

    def test_airdrop_run_start_reads_override_cfg(self):
        # cmd_air_airdrop：run_start 距 drop_point=覆写 lead 13000——读全局则 8000
        w = make_world(42)
        a = call(w, w.players[0], LI2, {"SUPPLY": 100})   # TRANSPORT+补给载荷过门
        a.pos = (500000, 500000)
        drop = (500000, 600000)
        queue_command(w, AirAirdropCmd(aircraft=a, drop_point=drop))
        consume_commands(w, self._ov_cfg())
        self.assertIs(a.task.kind, TaskKind.AIRDROP)
        self.assertEqual(a.task.run_start, (500000, 600000 - self.LEAD_OV))
        self.assertEqual(dist_cm(a.task.run_start, drop), self.LEAD_OV)


if __name__ == "__main__":
    unittest.main()
