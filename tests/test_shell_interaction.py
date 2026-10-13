"""交互重设计 v2 交互流测试（无显示可跑——交互逻辑不依赖开窗）。

覆盖面（shell_fsm 语义层 + cmd_bus 扩展 + 胶水层 pending 展开队列 + StandardPlay
标准玩法剧本；纯逻辑零 arcade——键位映射/页面门/编组/ESC 分层全部在 fsm 收敛，
窗口层只做 GL 事件翻译故此处直调语义层即为同一代码路径）：
- A2 待令组登记面扩容（reverse/strike/drop 不再 ValueError）；
- A4 点地放卡目标生效（pending 展开队列→trail point_cm==点击点+物理收敛）；
- A5 多选齐射（trail 逐单位 attack 条目、unit_ids 并集==选中全集）；
- A6 攻击移动入口（trail move 条目 mode=ATTACK）；
- A7 编组+剪尸（全灭 toast 不清号；config 页数字键不取组）；
- A9 无效操作反馈（曲射资格/无在空飞机 toast+trail 不变；空呼点数预判）；
- A10 ESC 分层链；A14 页面门（config/deploy 拦截+toast 文案）；
- Shift 排队（MoveCmd queue 透传）；
- StandardPlay 标准玩法剧本（框选→右键移动→Q 攻击移动→烟幕→编组→切组）。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.sim import card_loader as cl  # noqa: E402
from sovs.sim.air_data import CARD_OBJECTS  # noqa: E402
from sovs.sim.air import PHASE_COMBAT, PHASE_DEPLOY  # noqa: E402
from sovs.sim.tick import (DeckSlot, add_unit, make_unit, make_world,  # noqa: E402
                           world_tick)
from sovs.sim.types import MoveMode, Stance, UnitFlag  # noqa: E402
from sovs.ui.cmd_bus import CmdBus  # noqa: E402
from sovs.ui.shell_fsm import ShellFsm  # noqa: E402
from tools.skirmish_shell import SkirmishSession, StandardPlay  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = cl.load_library(os.path.join(_ROOT, "data", "gen", "cards_ground.v1.json"))
_TPL = {k: rec.unit_template for k, rec in _LIB.items()}


def _frame(phase: str, tick: int, *, units=(), aircraft=(), team: int = 0,
           result=None) -> dict:
    return {"schema_version": "1.0", "tick": tick, "phase": phase, "view": team,
            "map_cm": [200000, 100000], "units": list(units),
            "aircraft": list(aircraft), "objectives": [], "players": [],
            "smoke_zones": [], "projectiles": [], "buildings": [], "result": result}


def _unit(uid: int, team: int, x: int, y: int, **kw) -> dict:
    entry = {"id": uid, "team": team, "pos_cm": [x, y], "hp": 10, "hp_max": 10,
             "category": 1, "name": "u%d" % uid, "stance": "weapons_free",
             "smoke_left": 0}
    entry.update(kw)
    return entry


class _FakeCmd:
    """命令记录桩（纯 fsm 测试——不碰真实世界，只记调用面）。"""

    def __init__(self):
        self.calls = []

    def _log(self, name, *args, **kw):
        self.calls.append((name, args, kw))
        return [object()]

    def move(self, ids, dest, mode="NORMAL", queue=False):
        return self._log("move", tuple(ids), tuple(dest), mode=mode, queue=queue)

    def stop(self, ids):
        return self._log("stop", tuple(ids))

    def cancel(self, ids):
        return self._log("cancel", tuple(ids))

    def reverse(self, ids, dest):
        return self._log("reverse", tuple(ids), tuple(dest))

    def sprint(self, ids):
        return self._log("sprint", tuple(ids))

    def radar(self, ids, engage):
        return self._log("radar", tuple(ids), engage=engage)

    def smoke(self, ids):
        return self._log("smoke", tuple(ids))

    def stance(self, ids, stance):
        return self._log("stance", tuple(ids), stance)

    def smoke_sprint_stance(self, ids, stance="HOLD_FIRE"):
        return self._log("smoke_sprint_stance", tuple(ids))

    def attack(self, uid, foe, queue=False):
        return self._log("attack", uid, foe, queue=queue)

    def fire_mission(self, uid, point, **kw):
        return self._log("fire_mission", uid, tuple(point), **kw)

    def unload(self, ids, cm=None, building_id=None, queue=False):
        return self._log("unload", tuple(ids),
                         None if cm is None else tuple(cm),
                         building_id=building_id, queue=queue)

    def air_strike(self, aid, point):
        return self._log("air_strike", aid, tuple(point))

    def air_airdrop(self, aid, point):
        return self._log("air_airdrop", aid, tuple(point))


class TestArmableRegistry(unittest.TestCase):
    """A2：待令组登记面扩容——reverse/strike/drop 入册不再 ValueError。"""

    def test_arm_order_expanded_groups(self):
        f = ShellFsm()
        for group in ("reverse", "strike", "drop"):
            f.arm_order(group)
            self.assertEqual(f.armed_order, group)

    def test_unknown_group_still_rejected(self):
        with self.assertRaises(ValueError):
            ShellFsm().arm_order("nuclear_launch")


class TestPageGates(unittest.TestCase):
    """A14：页面门键位完备性——每页可用/拦截二归属+toast 文案。"""

    def _deploy_fsm(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("deploy", 10))
        return f

    def test_config_blocks_all_combat_keys_with_toast(self):
        f = ShellFsm()                              # config 页
        cmd = _FakeCmd()
        for name in ("Q", "S", "E", "Z", "X", "R", "T", "G", "H", "K", "O", "TAB"):
            f.notifications.clear()
            cmd.calls.clear()
            self.assertEqual(f.key(name, cmd=cmd), "blocked", name)
            self.assertFalse(cmd.calls)             # 零发令
            self.assertTrue(any("战斗令在部署/实战页可用" in n["text"]
                                for n in f.notifications), name)

    def test_deploy_allows_move_family(self):
        f = self._deploy_fsm()
        cmd = _FakeCmd()
        f.select_units([1])
        self.assertEqual(f.key("S", cmd=cmd), "stop")
        self.assertEqual(f.key("E", cmd=cmd), "cancel")
        # 〔P1 2026-10-13：Z 地面分流——雷达令先行（无对空资格由引擎门拒）+
        # 冲刺；返回动作名 z_dispatch（radar/sprint 双发）。〕
        self.assertEqual(f.key("Z", cmd=cmd), "z_dispatch")
        self.assertIn("sprint", [c[0] for c in cmd.calls])
        self.assertEqual(f.key("R", cmd=cmd), "arm:reverse")
        self.assertTrue(cmd.calls)

    def test_deploy_blocks_attack_family_with_toast(self):
        f = self._deploy_fsm()
        cmd = _FakeCmd()
        for name in ("Q", "T", "K", "O", "H", "X"):
            f.notifications.clear()
            cmd.calls.clear()
            self.assertEqual(f.key(name, cmd=cmd), "blocked", name)
            self.assertFalse(cmd.calls)
            self.assertTrue(any("战斗令在实战页可用" in n["text"]
                                for n in f.notifications), name)

    def test_deploy_G_gets_dedicated_toast(self):
        f = self._deploy_fsm()
        f.key("G", cmd=_FakeCmd())
        self.assertTrue(any("烟幕/姿态令在实战页可用（部署期冲刺用 Z）"
                            in n["text"] for n in f.notifications))

    def test_battle_allows_all_combat_keys(self):
        f = self._deploy_fsm()
        f.on_frame(_frame("combat", 700))
        cmd = _FakeCmd()
        f.select_units([1])
        # 〔P1 2026-10-13：Z=z_dispatch（雷达+冲刺分流）；+C/L/M/N/P 新键锚另见
        # test_p1_mechanics。〕
        expect = {"Q": "arm:attack", "S": "stop", "E": "cancel", "Z": "z_dispatch",
                  "X": "smoke", "R": "arm:reverse", "T": "arm:fire_mission",
                  "G": "combo", "H": "stance", "K": "arm:strike", "O": "arm:drop"}
        for name, action in expect.items():
            self.assertEqual(f.key(name, cmd=cmd), action, name)

    def test_settle_silent_block(self):
        f = self._deploy_fsm()
        f.on_frame(_frame("settle", 13800, result={"winner": 0}))
        cmd = _FakeCmd()
        for name in ("Q", "S", "G", "1"):
            self.assertIsNone(f.key(name, cmd=cmd), name)
        self.assertFalse(cmd.calls)
        self.assertFalse(f.notifications)


class TestGroups(unittest.TestCase):
    """A7：编组+取组剪尸+全灭 toast 不清号+config 页数字键不取组。"""

    def _fsm_with_units(self, units):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("deploy", 10, units=units))
        return f

    def test_assign_and_recall(self):
        f = self._fsm_with_units([_unit(1, 0, 0, 0), _unit(2, 0, 100, 0)])
        f.select_units([1, 2])
        self.assertEqual(f.key("1", ctrl=True), "group_assign")
        self.assertEqual(f.groups[1], ((1, 2), ()))  # (unit_ids, air_ids) 二元组快照
        f.clear_selection()
        self.assertEqual(f.key("1"), "group_recall")
        self.assertEqual(f.selected, (1, 2))

    def test_recall_filters_dead_ids(self):
        f = self._fsm_with_units([_unit(1, 0, 0, 0), _unit(2, 0, 100, 0),
                                  _unit(3, 0, 200, 0)])
        f.box_select((-10, -10), (300, 100))
        f.key("2", ctrl=True)
        f.clear_selection()
        # 编组内 1/3 阵亡（当前帧只剩 2）——取组即过滤
        f.on_frame(_frame("deploy", 20, units=[_unit(2, 0, 100, 50)]))
        self.assertEqual(f.key("2"), "group_recall")
        self.assertEqual(f.selected, (2,))
        self.assertEqual(f.groups[2], ((1, 2, 3), ()))  # 死 id 保留供 HUD 灰显

    def test_all_dead_group_toasts_and_keeps_slot(self):
        f = self._fsm_with_units([_unit(1, 0, 0, 0)])
        f.select_units([1])
        f.key("1", ctrl=True)
        f.on_frame(_frame("combat", 700, units=[]))     # 组全灭
        self.assertEqual(f.key("1"), "group_recall")
        self.assertEqual(f.selected, ())
        self.assertTrue(any("编组 1 已全灭" in n["text"]
                            for n in f.notifications))
        self.assertIn(1, f.groups)                  # 不清组号
        self.assertEqual(f.group_alive_count(1), 0) # 灰显数据源

    def test_config_digit_does_not_recall(self):
        f = ShellFsm()
        f.groups[1] = (7, 8)
        self.assertIsNone(f.key("1"))               # config 页数字键不取组
        self.assertEqual(f.selected, ())


class TestEscChain(unittest.TestCase):
    """A10：ESC 分层优先级链（F1>待令>待放卡>选区>退出确认）。"""

    def _fsm(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("deploy", 10, units=[_unit(1, 0, 0, 0)]))
        return f

    def test_help_closes_first_without_touching_rest(self):
        f = self._fsm()
        f.help_open = True
        f.arm_order("attack")
        f.select_units([1])
        self.assertEqual(f.esc(), "help_closed")
        self.assertFalse(f.help_open)
        self.assertEqual(f.armed_order, "attack")   # 后续链未触发
        self.assertEqual(f.selected, (1,))

    def test_armed_order_cleared(self):
        f = self._fsm()
        f.arm_order("attack")
        self.assertEqual(f.esc(), "order_cleared")
        self.assertIsNone(f.armed_order)

    def test_armed_purchase_canceled(self):
        f = self._fsm()
        f.arm_purchase(102, "步枪排")
        self.assertEqual(f.esc(), "purchase_canceled")
        self.assertIsNone(f.armed_purchase)

    def test_selection_cleared(self):
        f = self._fsm()
        f.select_units([1])
        self.assertEqual(f.esc(), "selection_cleared")
        self.assertEqual(f.selected, ())

    def test_exit_confirm_then_exit(self):
        f = self._fsm()
        self.assertEqual(f.esc(), "exit_confirm")
        self.assertTrue(f.exit_confirm)
        self.assertEqual(f.esc(), "exit")           # 窗口层据此关闭
        self.assertFalse(f.exit_confirm)

    def test_any_key_cancels_exit_confirm(self):
        f = self._fsm()
        f.esc()
        f.key("S", cmd=_FakeCmd())
        self.assertFalse(f.exit_confirm)

    def test_reset_clears_all_layers(self):
        f = self._fsm()
        f.arm_purchase(102, "x")
        f.groups[1] = (1,)
        f.help_open = True
        f.reset()
        self.assertFalse(f.help_open)
        self.assertIsNone(f.armed_purchase)
        self.assertEqual(f.groups, {})
        self.assertEqual(f.page, "config")


class TestToasts(unittest.TestCase):
    """toast 队列：error 计数（被拒统计）+ ttl 泵衰减。"""

    def test_error_toast_counts_and_ttl(self):
        f = ShellFsm()
        f.notify("点数不足", tone="error")
        f.notify("提示")
        self.assertEqual(f.rejected_count, 1)
        self.assertEqual(len(f.notifications), 2)
        f.pump_notifications(2.6)
        self.assertEqual(f.notifications, [])       # 2.5s 过期出队

    def test_consecutive_same_text_aggregates(self):
        """battle.png 复检②：同文同调的连续重复聚合为「×N」单条——8 连拒
        不再铺 8 行同文红字压字；error 计数仍逐条累加。"""
        f = ShellFsm()
        for _ in range(8):
            f.notify("移动令被拒（状态机门）", tone="error")
        self.assertEqual(len(f.notifications), 1)   # 单条聚合
        self.assertEqual(f.notifications[0]["text"],
                         "移动令被拒（状态机门） ×8")
        self.assertEqual(f.rejected_count, 8)        # 计数不聚合
        # 聚合条目照常随 ttl 泵出队
        f.pump_notifications(2.6)
        self.assertEqual(f.notifications, [])

    def test_distinct_or_alternating_notes_not_merged(self):
        """不同文/不同调不聚合；同文但中间隔了别的 toast 也不并条（时序可见）。"""
        f = ShellFsm()
        f.notify("甲", tone="error")
        f.notify("甲")                               # 同文不同调=两条
        self.assertEqual(len(f.notifications), 2)
        f.notify("乙", tone="error")
        f.notify("甲", tone="error")                 # 非连续=追加（第 4 条）
        self.assertEqual(len(f.notifications), 4)
        self.assertEqual([n["text"] for n in f.notifications],
                         ["甲", "甲", "乙", "甲"])


class TestArmedExecution(unittest.TestCase):
    """待令执行语义层：齐射/攻击移动/倒车/炮击拒/无在空（A5/A6/A9）。"""

    def setUp(self):
        self.w = make_world(11, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        for key, copies in (("SU_RIFLE", 2), ("SU_T3485", 1), ("SU_ZIS3", 1)):
            self.w.players[0].deck_slots.append(DeckSlot(_TPL[key], copies))
        self.r1 = add_unit(self.w, make_unit(self.w, _TPL["SU_RIFLE"], 0, 0,
                                             (50000, 50000)))
        self.r2 = add_unit(self.w, make_unit(self.w, _TPL["SU_RIFLE"], 0, 0,
                                             (52000, 50000)))
        self.tk = add_unit(self.w, make_unit(self.w, _TPL["SU_T3485"], 0, 0,
                                             (54000, 50000)))
        self.gun = add_unit(self.w, make_unit(self.w, _TPL["SU_ZIS3"], 0, 0,
                                              (56000, 50000)))
        self.foe = add_unit(self.w, make_unit(self.w, _TPL["SU_RIFLE"], 1, 1,
                                              (60000, 50000)))
        self.foe.spotted_mask |= 1
        self.bus = CmdBus(self.w, 0)
        self.fsm = ShellFsm()
        self.fsm.start_deploy()
        self.fsm.on_frame(_frame("combat", 700))
        self.fsm.select_units([self.r1.id, self.r2.id, self.tk.id])

    def test_A5_volley_fires_every_selected_unit(self):
        self.fsm.arm_order("attack")
        self.assertTrue(self.fsm.execute_armed_unit(self.foe.id, self.bus,
                                                    enemy=True))
        entries = [t for t in self.bus.trail if t["kind"] == "attack"]
        self.assertGreaterEqual(len(entries), 3)    # 每单位一条
        union = set()
        for t in entries:
            self.assertEqual(len(t["unit_ids"]), 1)  # cmd_bus 每条单元素
            union.update(t["unit_ids"])
        self.assertEqual(union, {self.r1.id, self.r2.id, self.tk.id})
        self.assertIsNone(self.fsm.armed_order)      # 齐射后清待令

    def test_A5_volley_on_own_unit_keeps_armed_with_toast(self):
        self.fsm.arm_order("attack")
        self.assertTrue(self.fsm.execute_armed_unit(self.r1.id, self.bus,
                                                    enemy=False))
        self.assertEqual(self.fsm.armed_order, "attack")   # 待令保留
        self.assertTrue(any("攻击需要敌方目标" in n["text"]
                            for n in self.fsm.notifications))

    def test_A6_attack_move_mode(self):
        self.fsm.arm_order("attack")
        self.assertTrue(self.fsm.execute_armed_ground((70000, 50000), self.bus))
        moves = [t for t in self.bus.trail if t["kind"] == "move"]
        self.assertTrue(moves)
        self.assertEqual(moves[-1]["mode"], "ATTACK")     # trail 条目含 mode
        for cmd in self.w.command_queue:
            if type(cmd).__name__ == "MoveCmd":
                self.assertIs(cmd.mode, MoveMode.ATTACK)  # 引擎命令面生效

    def test_reverse_armed_ground(self):
        self.fsm.arm_order("reverse")
        self.assertTrue(self.fsm.execute_armed_ground((40000, 50000), self.bus))
        self.assertTrue(any(t["kind"] == "reverse" for t in self.bus.trail))

    def test_A9_fire_mission_without_indirect_toast(self):
        self.fsm.select_units([self.r1.id])               # 步枪班无 INDIRECT
        self.fsm.arm_order("fire_mission")
        n0 = len([t for t in self.bus.trail if t["kind"] == "fire_mission"])
        self.assertTrue(self.fsm.execute_armed_ground((100000, 50000), self.bus))
        self.assertEqual(len([t for t in self.bus.trail
                              if t["kind"] == "fire_mission"]), n0)  # trail 不变
        self.assertTrue(any("无曲射火力" in n["text"]
                            for n in self.fsm.notifications))
        self.assertEqual(self.fsm.armed_order, "fire_mission")  # 待令保留

    def test_fire_mission_with_zis3(self):
        self.fsm.select_units([self.gun.id])
        self.fsm.arm_order("fire_mission")
        self.assertTrue(self.fsm.execute_armed_ground((100000, 50000), self.bus))
        self.assertTrue(any(t["kind"] == "fire_mission" for t in self.bus.trail))
        self.assertIsNone(self.fsm.armed_order)

    def test_A9_strike_without_aircraft_toast(self):
        self.fsm.arm_order("strike")
        self.assertTrue(self.fsm.execute_armed_ground((100000, 50000), self.bus))
        self.assertTrue(any("无在空飞机" in n["text"]
                            for n in self.fsm.notifications))
        self.assertEqual(self.fsm.armed_order, "strike")

    def test_strike_with_bomber(self):
        self.bus.air_call(CARD_OBJECTS["IL2M"], {"BOMB": 2})
        world_tick(self.w)
        self.fsm.on_frame(_frame(
            "combat", 701, aircraft=[{"id": self.w.aircraft[0].id, "team": 0,
                                     "state": "patrol", "ammo": {"BOMB": 2},
                                     "paratroop": None}]))
        self.fsm.arm_order("strike")
        self.assertTrue(self.fsm.execute_armed_ground((100000, 50000), self.bus))
        self.assertTrue(any(t["kind"] == "air_strike" for t in self.bus.trail))

    def test_shift_queue_passthrough(self):
        cmds = self.bus.move([self.r1.id], (60000, 50000), queue=True)
        self.assertTrue(cmds[0].queue)               # MoveCmd queue 形参透传


class TestP0ManualAlignment(unittest.TestCase):
    """P0 键位纠偏块（2026-10-13）——手册 HOTKEYS/Hold Fire/SHIFT 语义锚：
    - Q=Attack Move（manual.txt:560-562，A 退役）；
    - U 双击=就地立即卸载（manual.txt:566-568「(Press U twice to unload
      immediately)」）；
    - SHIFT=Queue orders（manual.txt:551）：待令态 Shift+确认=入队不清待令；
    - O 空投拖拽画区：区心投放（与 T/K 画线态同构）。"""

    def setUp(self):
        self.w = make_world(31, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        for key, copies in (("SU_RIFLE", 2), ("SU_ZIS3", 1)):
            self.w.players[0].deck_slots.append(DeckSlot(_TPL[key], copies))
        self.r1 = add_unit(self.w, make_unit(self.w, _TPL["SU_RIFLE"], 0, 0,
                                             (50000, 50000)))
        self.gun = add_unit(self.w, make_unit(self.w, _TPL["SU_ZIS3"], 0, 0,
                                              (56000, 50000)))
        self.foe = add_unit(self.w, make_unit(self.w, _TPL["SU_RIFLE"], 1, 1,
                                              (60000, 50000)))
        self.foe.spotted_mask |= 1
        self.bus = CmdBus(self.w, 0)
        self.fsm = ShellFsm()
        self.fsm.start_deploy()
        self.fsm.on_frame(_frame("combat", 700))
        self.fsm.select_units([self.r1.id, self.gun.id])

    def test_Q_arms_attack_A_is_retired(self):
        # 手册 Q=Attack Move；A 无战斗语义（WASD 相机占用——manual.txt:579-580）
        self.assertEqual(self.fsm.key("Q", cmd=self.bus), "arm:attack")
        self.assertIsNone(self.fsm.key("A", cmd=self.bus))   # A 退役（无别名）

    def test_U_double_press_unloads_in_place(self):
        self.assertEqual(self.fsm.key("U", cmd=self.bus), "arm:unload")
        self.assertEqual(self.fsm.armed_order, "unload")
        moves0 = len([t for t in self.bus.trail if t["kind"] == "move"])
        self.assertEqual(self.fsm.key("U", cmd=self.bus), "unload_now")
        self.assertIsNone(self.fsm.armed_order)               # 就地卸载后清待令
        unloads = [t for t in self.bus.trail if t["kind"] == "unload"]
        self.assertTrue(unloads)
        self.assertIsNone(unloads[-1]["point_cm"])            # 无目标点=就地
        self.assertEqual(                                      # 未附带开进移动令
            len([t for t in self.bus.trail if t["kind"] == "move"]), moves0)

    def test_shift_confirm_queues_and_keeps_armed(self):
        # 手册 SHIFT=Queue orders：待令态 Shift+确认=入队不清待令（移动/攻击/
        # 炮击/卸载四族）；非 Shift 确认=即发清待令
        self.fsm.arm_order("attack")
        self.assertTrue(self.fsm.execute_armed_ground((70000, 50000),
                                                     self.bus, shift=True))
        self.assertEqual(self.fsm.armed_order, "attack")      # 不清待令
        mv = next(c for c in self.w.command_queue
                  if type(c).__name__ == "MoveCmd")
        self.assertTrue(mv.queue)                             # 引擎排队位生效
        self.assertIs(mv.mode, MoveMode.ATTACK)
        # 卸载族：DismountCmd+MoveCmd 全排队
        self.fsm.arm_order("unload")
        self.assertTrue(self.fsm.execute_armed_ground((70000, 50000),
                                                     self.bus, shift=True))
        self.assertEqual(self.fsm.armed_order, "unload")
        dis = [c for c in self.w.command_queue
               if type(c).__name__ == "DismountCmd"]
        self.assertTrue(dis and all(c.queue for c in dis))
        # 炮击族：FireMissionCmd 排队、待令保留
        self.fsm.arm_order("fire_mission")
        self.assertTrue(self.fsm.execute_armed_ground((100000, 50000),
                                                     self.bus, shift=True))
        self.assertEqual(self.fsm.armed_order, "fire_mission")
        fm = next(c for c in self.w.command_queue
                  if type(c).__name__ == "FireMissionCmd")
        self.assertTrue(fm.queue)
        # 攻击族（点敌齐射）：AttackCmd 排队、待令保留
        self.fsm.arm_order("attack")
        self.assertTrue(self.fsm.execute_armed_unit(self.foe.id, self.bus,
                                                   enemy=True, shift=True))
        self.assertEqual(self.fsm.armed_order, "attack")
        atk = [c for c in self.w.command_queue
               if type(c).__name__ == "AttackCmd"]
        self.assertTrue(atk and all(c.queue for c in atk))
        # 非 Shift 收尾确认=即发清待令（旧行为不变）
        self.assertTrue(self.fsm.execute_armed_ground((70000, 50000),
                                                     self.bus))
        self.assertIsNone(self.fsm.armed_order)

    def test_drop_area_center_and_short_drag_point(self):
        # O 拖拽画区=区心投放（AirAirdropCmd 点 API——区=区心单点留痕）；
        # 短拖回落点投（finish_line_drag 阈值语义在 fm_panel 测）
        frame = _frame("combat", 700, aircraft=[
            {"id": 5, "team": 0, "state": "patrol", "ammo": {},
             "paratroop": {"n": 4}}])
        self.fsm.on_frame(frame)
        self.fsm.arm_order("drop")
        cmd = _FakeCmd()
        self.assertTrue(self.fsm.execute_armed_drop_area((60000, 40000),
                                                         (80000, 60000), cmd))
        drops = [c for c in cmd.calls if c[0] == "air_airdrop"]
        self.assertEqual(drops, [("air_airdrop", (5, (70000, 50000)), {})])
        self.assertIsNone(self.fsm.armed_order)               # 投放后清待令


class TestHStanceToggle(unittest.TestCase):
    """H 交战纪律切换：逐单位按帧内当前姿态取反（SetStanceCmd 包装）。"""

    def test_toggle_per_unit_stance(self):
        w = make_world(11, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        w.players[0].deck_slots.append(DeckSlot(_TPL["SU_RIFLE"], 2))
        u1 = add_unit(w, make_unit(w, _TPL["SU_RIFLE"], 0, 0, (0, 0)))
        u2 = add_unit(w, make_unit(w, _TPL["SU_RIFLE"], 0, 0, (100, 0)))
        u2.stance = Stance.HOLD_FIRE
        bus = CmdBus(w, 0)
        fsm = ShellFsm()
        fsm.start_deploy()
        fsm.on_frame(_frame("combat", 700, units=[
            _unit(u1.id, 0, 0, 0, stance="weapons_free"),
            _unit(u2.id, 0, 100, 0, stance="hold_fire")]))
        fsm.select_units([u1.id, u2.id])
        self.assertEqual(fsm.key("H", cmd=bus), "stance")
        stances = [c.stance.name for c in w.command_queue
                   if type(c).__name__ == "SetStanceCmd"]
        self.assertEqual(stances, ["HOLD_FIRE", "WEAPONS_FREE"])  # 各自取反


class TestPendingExpand(unittest.TestCase):
    """A4：点地放卡目标生效——pending 展开队列（胶水层，位置意图经 MoveCmd）。"""

    def test_deploy_click_target_reaches_trail_and_converges(self):
        session = SkirmishSession(seed=42)
        click = (180000, 90000)                      # 开阔地点击（距锚点>0 可达）
        session.cmd.purchase(102)                    # SU_RIFLE
        session.queue_expand(102, click)
        guard = 0
        while not any(u.team == 0 for u in session.world.units):
            session.advance(1)
            guard += 1
            self.assertLess(guard, 600, "部署期单位未出场")
        spawn_tick = session.world.tick
        spawned = next(u for u in session.world.units if u.team == 0)
        d0 = (abs(spawned.pos[0] - click[0]) ** 2
              + abs(spawned.pos[1] - click[1]) ** 2) ** 0.5
        self.assertEqual(session.pending_expands, [])   # 展开意图已消化
        # 主判据（零掷骰）：pending 触发的 move 落 point_cm==点击 cm 的 trail 记录
        self.assertTrue(any(t["kind"] == "move"
                            and t["point_cm"] == [click[0], click[1]]
                            for t in session.cmd.trail))
        # 辅助判据（物理收敛）：出场 100t 后与目标距离严格小于出场时刻距离
        while session.world.tick < spawn_tick + 100:
            session.advance(1)
        target = next((u for u in session.world.units if u.team == 0), None)
        self.assertIsNotNone(target)
        d1 = (abs(target.pos[0] - click[0]) ** 2
              + abs(target.pos[1] - click[1]) ** 2) ** 0.5
        self.assertLess(d1, d0)


class TestAirRosterAffordability(unittest.TestCase):
    """A9：空呼点数预判（air_roster 生成处——修 max(1,..) 缺陷）。"""

    def test_low_air_points_marks_unaffordable(self):
        session = SkirmishSession(seed=42)
        p = session.world.players[0]
        p.air_points = 10                            # 低于机身价
        roster = {e["key"]: e for e in session.air_roster()}
        attack = next(e for k, e in roster.items() if "BOMB" in e["payload"])
        self.assertFalse(attack["affordable"])       # 灰显
        self.assertGreater(attack["cost"], 10)
        self.assertEqual(attack["payload"]["BOMB"], 0)   # 不再虚标 1 弹

    def test_ample_air_points_affordable(self):
        session = SkirmishSession(seed=42)
        p = session.world.players[0]
        p.air_points = 750
        roster = {e["key"]: e for e in session.air_roster()}
        attack = next(e for k, e in roster.items() if "BOMB" in e["payload"])
        self.assertTrue(attack["affordable"])
        self.assertGreater(attack["payload"]["BOMB"], 0)
        self.assertLessEqual(attack["cost"], 750)


class TestStandardPlayScript(unittest.TestCase):
    """附加要求③/④：标准玩法剧本（框选→右键移动→Q 攻击移动→烟幕→编组→切组）
    逐条断言（选中集合/入队/世界响应）——headless 复用同一 fsm 语义层。"""

    def test_script_checks_all_pass_on_full_game(self):
        session = SkirmishSession(seed=42)
        script = StandardPlay(session)
        airdrop = UnitFlag.DELIVERY_AIRDROP_ONLY
        # 盲部署全程推进（600t——终审：原 for range(480) 提前收束，下方 while
        # 在 deploy 相位即判假、battle_beat 零执行，94 条 checks 全为部署期断言）
        while session.world.phase == PHASE_DEPLOY:
            p = session.world.players[0]
            for slot in p.deck_slots:
                if (slot.copies_left > 0 and p.points >= slot.template.cost
                        and not (slot.template.flags & airdrop)):
                    session.cmd.purchase(slot.template.template_id)
                    break
            if session.world.tick % 10 == 0:
                script.deploy_beat()
            session.advance(1)
        n_battle = 0
        while session.world.phase == PHASE_COMBAT:
            if session.world.tick % 100 == 0:
                script.battle_beat()
                n_battle += 1
            session.advance(1)
        self.assertGreater(n_battle, 0, "battle_beat 零执行（未真正进入实战段）")
        names = {c[0] for c in script.checks}
        self.assertIn("Q+点地=攻击移动（mode=ATTACK）", names,
                      "实战段剧本断言未产生（仅部署期断言）")
        self.assertTrue(script.checks, "剧本断言未产生")
        bad = [c for c in script.checks if not c[1]]
        self.assertEqual(bad, [], "未通过断言：%s" % (bad[:4],))


if __name__ == "__main__":
    unittest.main()
