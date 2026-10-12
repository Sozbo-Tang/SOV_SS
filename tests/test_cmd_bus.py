"""FE-T07 命令通道（sovs/ui/cmd_bus.py）测试：UI 意图 → queue_command 全链。

「生效」判据（FE-01 §5 FE-T07 验收原文）：命令经 queue_command **入队** 且被
consume_commands **消费**（world_tick 后队列清空 + 引擎状态落点变化）+ World
状态产生对应**可断言变化**（位移/开火/烟区/任务体/飞机spawn/扣点扣份）。

分层锚：cmd_bus 是 sovs/ui 唯一允许 import sovs.sim 的模块（限 tick/types 命令
类+queue_command——tests/test_arch_constraints.py ②）；本测试用真实卡库
（data/gen/cards_ground.v1.json 现役 10 卡）驱动，覆盖首批五组：
移动族（Move/Stop/Cancel/Reverse+Sprint）/攻击/炮击任务/空军呼叫（含
PARATROOP 载荷 deck 槽换装——actions.py:131-137 同款口径）/烟幕冲刺姿态三令。
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.sim import card_loader as cl  # noqa: E402
from sovs.sim.air_data import CARD_OBJECTS  # noqa: E402
from sovs.sim.air import PHASE_COMBAT, PHASE_DEPLOY  # noqa: E402
from sovs.sim.tables import CONFIG  # noqa: E402
from sovs.sim.tick import (DeckSlot, add_unit, make_unit, make_world,  # noqa: E402
                           world_tick)
from sovs.sim.types import Stance  # noqa: E402
from sovs.ui.cmd_bus import CmdBus  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = cl.load_library(os.path.join(_ROOT, "data", "gen", "cards_ground.v1.json"))
_TPL = {k: rec.unit_template for k, rec in _LIB.items()}


def _deck_world(phase: int = PHASE_COMBAT):
    """player0 挂 su_min 现役卡组的最小世界（壳同款装配，测试内联不引 tools）。"""
    w = make_world(11, phase=phase, size_cm=(200000, 100000))
    for key, copies in (("SU_RECON", 1), ("SU_RIFLE", 2), ("SU_PARATROOP", 1),
                        ("SU_COMMISSAR", 1), ("SU_T3485", 2), ("SU_ZIS3", 1),
                        ("SU_TRUCK", 1)):
        w.players[0].deck_slots.append(DeckSlot(_TPL[key], copies))
    return w


def _spawn(w, key: str, team: int, pos, player_index: int = 0):
    return add_unit(w, make_unit(w, _TPL[key], team, player_index, pos))


class TestChannelIdentity(unittest.TestCase):
    """通道唯一性：一切意图经 cmd_bus 命名空间的 queue_command 入队。"""

    def test_intents_route_through_queue_command(self):
        import sovs.ui.cmd_bus as cb
        w = _deck_world(PHASE_COMBAT)
        u = _spawn(w, "SU_RIFLE", 0, (50000, 50000))
        bus = CmdBus(w, 0)
        with mock.patch.object(cb, "queue_command", wraps=cb.queue_command) as m:
            bus.move([u.id], (60000, 50000))
            self.assertEqual(m.call_count, 1)          # MoveCmd 一令一入队


class TestDeployPurchases(unittest.TestCase):
    """购卡：入队→消费→扣点/扣份/入 spawn_queue（spawn_step 出牌另见整局）。"""

    def setUp(self):
        self.w = _deck_world(PHASE_DEPLOY)
        self.bus = CmdBus(self.w, 0)

    def test_purchase_enqueued_consumed_and_charged(self):
        cmd = self.bus.purchase(102)                   # SU_RIFLE 45 点 ×2 份
        self.assertEqual(type(cmd).__name__, "PurchaseCmd")
        self.assertEqual(len(self.w.command_queue), 1)  # 入队判据
        world_tick(self.w)
        self.assertEqual(self.w.command_queue, [])      # consume_commands 消费判据
        p = self.w.players[0]
        self.assertEqual(p.points, 1000 - 45)           # 扣点
        slot = next(s for s in p.deck_slots
                    if s.template.template_id == 102)
        self.assertEqual(slot.copies_left, 1)           # 扣 deck 份
        self.assertEqual(p.spawn_queue[-1].template_id, 102)   # 入出牌队列

    def test_airdrop_only_card_not_queued(self):
        """空降投送限定卡（空裁8 购买门恒拒）——查活对象阶段即拦，不入队。"""
        self.assertIsNone(self.bus.purchase(103))       # SU_PARATROOP
        self.assertEqual(self.w.command_queue, [])

    def test_unknown_template_returns_none(self):
        self.assertIsNone(self.bus.purchase(99999))
        self.assertEqual(self.w.command_queue, [])


class TestMoveFamily(unittest.TestCase):
    """移动族五令：Move/Stop/Cancel/Reverse+Sprint（位移=生效证据）。"""

    def setUp(self):
        self.w = _deck_world(PHASE_COMBAT)
        self.bus = CmdBus(self.w, 0)
        self.u = _spawn(self.w, "SU_T3485", 0, (50000, 50000))

    def test_move_displaces_unit(self):
        cmds = self.bus.move([self.u.id], (70000, 50000))
        self.assertEqual([type(c).__name__ for c in cmds], ["MoveCmd"])
        self.assertEqual(len(self.w.command_queue), 1)
        for _ in range(30):
            world_tick(self.w)
        self.assertNotEqual(self.u.pos, (50000, 50000))   # 位移判据（生效）

    def test_stop_cancel_reverse_sprint_enqueued(self):
        self.bus.stop([self.u.id])
        self.bus.cancel([self.u.id])
        self.bus.reverse([self.u.id], (40000, 50000))
        self.bus.sprint([self.u.id])
        names = [type(c).__name__ for c in self.w.command_queue]
        self.assertEqual(names, ["StopCmd", "CancelCmd", "ReverseCmd", "SprintCmd"])
        world_tick(self.w)
        self.assertEqual(self.w.command_queue, [])         # 全部消费
        self.assertGreater(self.u.sprint_until, 0)         # sprint_until 写点（生效）

    def test_move_unknown_unit_skipped(self):
        self.assertEqual(self.bus.move([424242], (0, 0)), [])


class TestAttack(unittest.TestCase):
    """攻击：入队→消费→begin_aim 开火链启动（ws.target 落点）。"""

    def test_attack_begins_aim(self):
        w = _deck_world(PHASE_COMBAT)
        shooter = _spawn(w, "SU_RIFLE", 0, (50000, 50000))
        foe = _spawn(w, "SU_RIFLE", 1, (53000, 50000), player_index=1)
        foe.spotted_mask |= 1 << 0                        # M5/B01 发现门（测试供给）
        bus = CmdBus(w, 0)
        cmds = bus.attack(shooter.id, foe.id)
        self.assertEqual([type(c).__name__ for c in cmds], ["AttackCmd"])
        world_tick(w)
        aiming = [ws for e in shooter.elements for ws in e.weapon_states
                  if ws.target is not None]
        self.assertTrue(aiming)                           # 开火链启动（生效判据）

    def test_attack_unknown_units_returns_empty(self):
        w = _deck_world(PHASE_COMBAT)
        bus = CmdBus(w, 0)
        self.assertEqual(bus.attack(111, 222), [])


class TestFireMission(unittest.TestCase):
    """炮击任务：SetMode 预置 + FireMissionCmd → 任务体安装。"""

    def test_fire_mission_installs_mission(self):
        w = _deck_world(PHASE_COMBAT)
        gun = _spawn(w, "SU_ZIS3", 0, (50000, 50000))     # mode_set 含 INDIRECT 位
        bus = CmdBus(w, 0)
        cmds = bus.fire_mission(gun.id, (100000, 50000))
        self.assertTrue(any(type(c).__name__ == "SetModeCmd" for c in cmds))
        self.assertTrue(any(type(c).__name__ == "FireMissionCmd" for c in cmds))
        world_tick(w)
        self.assertIsNotNone(gun.fire_mission)            # 任务体安装（生效判据）
        self.assertGreater(gun.fire_mission.shots_left, 0)

    def test_cancel_fire_mission_clears(self):
        w = _deck_world(PHASE_COMBAT)
        gun = _spawn(w, "SU_ZIS3", 0, (50000, 50000))
        bus = CmdBus(w, 0)
        bus.fire_mission(gun.id, (100000, 50000))
        world_tick(w)
        self.assertIsNotNone(gun.fire_mission)
        bus.cancel_fire_mission([gun.id])
        world_tick(w)
        self.assertIsNone(gun.fire_mission)               # 任务体销毁

    def test_non_indirect_unit_returns_empty(self):
        w = _deck_world(PHASE_COMBAT)
        rifle = _spawn(w, "SU_RIFLE", 0, (50000, 50000))
        bus = CmdBus(w, 0)
        self.assertEqual(bus.fire_mission(rifle.id, (100000, 50000)), [])


class TestAirCalls(unittest.TestCase):
    """空军呼叫：AirCallCmd→AirStrikeCmd/AirAirdropCmd + PARATROOP deck 槽换装。"""

    def test_air_call_bomber_spawns_aircraft(self):
        w = _deck_world(PHASE_COMBAT)
        bus = CmdBus(w, 0)
        tpl = CARD_OBJECTS["IL2M"]
        cmds = bus.air_call(tpl, {"BOMB": 2})
        self.assertEqual([type(c).__name__ for c in cmds], ["AirCallCmd"])
        world_tick(w)
        self.assertEqual(len(w.aircraft), 1)              # INBOUND spawn（生效判据）
        self.assertEqual(w.aircraft[0].ammo_left["BOMB"], 2)

    def test_air_call_paratroop_swaps_deck_slot_template(self):
        """payload['PARATROOP']=True → deck 槽活模板换装+装机扣份（actions.py:131-137）。"""
        w = _deck_world(PHASE_COMBAT)
        bus = CmdBus(w, 0)
        cmds = bus.air_call(CARD_OBJECTS["LI2"], {"PARATROOP": True})
        cmd = cmds[0]
        self.assertIs(cmd.payload["PARATROOP"], _TPL["SU_PARATROOP"])   # 换装后活引用
        world_tick(w)
        slot = next(s for s in w.players[0].deck_slots
                    if s.template.template_id == 103)
        self.assertEqual(slot.copies_left, 0)             # 装机扣份（B-06）
        self.assertIsNotNone(w.aircraft[0].paratroop_cargo)
        self.assertEqual(w.aircraft[0].paratroop_cargo.template_id, 103)

    def test_air_call_paratroop_without_reserve_returns_empty(self):
        w = _deck_world(PHASE_COMBAT)
        w.players[0].deck_slots = [s for s in w.players[0].deck_slots
                                   if s.template.template_id != 103]
        bus = CmdBus(w, 0)
        self.assertEqual(bus.air_call(CARD_OBJECTS["LI2"], {"PARATROOP": True}), [])

    def test_air_strike_and_airdrop_enqueued_by_aircraft_id(self):
        w = _deck_world(PHASE_COMBAT)
        bus = CmdBus(w, 0)
        bus.air_call(CARD_OBJECTS["IL2M"], {"BOMB": 1})
        world_tick(w)
        aid = w.aircraft[0].id
        strike = bus.air_strike(aid, (100000, 50000))
        self.assertEqual(type(strike).__name__, "AirStrikeCmd")
        drop = bus.air_airdrop(aid, (100000, 50000))
        self.assertEqual(type(drop).__name__, "AirAirdropCmd")
        self.assertEqual(len(w.command_queue), 2)         # 两令入队
        world_tick(w)
        self.assertEqual(w.command_queue, [])             # 消费（引擎门另行裁决）

    def test_air_strike_unknown_aircraft_returns_none(self):
        w = _deck_world(PHASE_COMBAT)
        self.assertIsNone(CmdBus(w, 0).air_strike(99, (0, 0)))


class TestSmokeSprintStance(unittest.TestCase):
    """烟幕冲刺姿态三令一键：SmokeCmd+SprintCmd+SetStanceCmd → 烟区+姿态+疾跑。"""

    def test_combo_three_commands_and_effects(self):
        w = _deck_world(PHASE_COMBAT)
        tank = _spawn(w, "SU_T3485", 0, (50000, 50000))   # 自卫烟幕 2 发
        bus = CmdBus(w, 0)
        cmds = bus.smoke_sprint_stance([tank.id])
        self.assertEqual([type(c).__name__ for c in cmds],
                         ["SmokeCmd", "SprintCmd", "SetStanceCmd"])
        world_tick(w)
        self.assertEqual(w.command_queue, [])             # 消费判据
        self.assertIs(tank.stance, Stance.HOLD_FIRE)      # 姿态落点（生效）
        self.assertGreater(tank.sprint_until, 0)          # 疾跑写点（生效）
        for _ in range(CONFIG.self_smoke_delay_ticks + 1):
            world_tick(w)
        self.assertGreaterEqual(len(w.smoke_zones), 1)    # 烟区落点（生效判据）

    def test_combo_without_smoke_charges_still_sprint_and_stance(self):
        """无烟弹单位（P-121 现役多数卡 0 发）：SmokeCmd 缺席，余两令照发。"""
        w = _deck_world(PHASE_COMBAT)
        rifle = _spawn(w, "SU_RIFLE", 0, (50000, 50000))
        bus = CmdBus(w, 0)
        cmds = bus.smoke_sprint_stance([rifle.id])
        self.assertEqual([type(c).__name__ for c in cmds],
                         ["SprintCmd", "SetStanceCmd"])


class TestTrail(unittest.TestCase):
    """已发令轨迹（UI 播报面）：意图落 trail、条数封顶防膨胀。"""

    def test_trail_records_and_caps(self):
        w = _deck_world(PHASE_COMBAT)
        u = _spawn(w, "SU_T3485", 0, (50000, 50000))
        bus = CmdBus(w, 0)
        bus.move([u.id], (60000, 50000))
        self.assertEqual(len(bus.trail), 1)
        self.assertEqual(bus.trail[0]["kind"], "move")
        self.assertEqual(bus.trail[0]["point_cm"], [60000, 50000])
        for i in range(120):
            bus.stop([u.id])
        self.assertLessEqual(len(bus.trail), bus.TRAIL_CAP)


if __name__ == "__main__":
    unittest.main()
