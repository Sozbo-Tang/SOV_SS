"""GP-01 §4/§5/§6 前端层测试（M3）：飞机可选可控全链 + 炮击参数态 + §6 UI 入口。

headless（零 arcade）——覆盖 sovs/ui/shell_fsm 选区双通道/待令新组/页面门/
炮击参数态/拒绝 toast，sovs/ui/cmd_bus 六空令包装与 fire_mission 全参透传，
sovs/app SkirmishSession 卡组泛化（deck_list/自制卡组开局）。GL 窗口面
（布局重排/面板绘制）由 --screenshot/--coldstart 门禁与 test_shell_window 承载。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.sim import card_loader as cl  # noqa: E402
from sovs.sim.air_data import CARD_OBJECTS  # noqa: E402
from sovs.sim.air import PHASE_COMBAT, TaskKind  # noqa: E402
from sovs.sim.tick import (DeckSlot, add_unit, make_unit, make_world,  # noqa: E402
                           world_tick)
from sovs.sim.types import FireMissionForm, MoveMode, SalvoMode  # noqa: E402
from sovs.ui.cmd_bus import CmdBus  # noqa: E402
from sovs.ui.shell_fsm import (CREEP_SPEEDS_CM, ShellFsm,  # noqa: E402
                               STATE_CN)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = cl.load_library(os.path.join(_ROOT, "data", "gen", "cards_ground.v1.json"))
_TPL = {k: rec.unit_template for k, rec in _LIB.items()}


def _frame(phase: str, tick: int, *, units=(), aircraft=(), team: int = 0,
           players=(), rejections=(), result=None) -> dict:
    return {"schema_version": "1.1", "tick": tick, "phase": phase, "view": team,
            "map_cm": [200000, 100000], "units": list(units),
            "aircraft": list(aircraft), "objectives": [], "players": list(players),
            "smoke_zones": [], "projectiles": [], "buildings": [],
            "rejections": list(rejections), "result": result}


def _unit(uid: int, team: int, x: int, y: int, **kw) -> dict:
    entry = {"id": uid, "team": team, "pos_cm": [x, y], "hp": 10, "hp_max": 10,
             "category": 1, "name": "u%d" % uid, "stance": "weapons_free",
             "smoke_left": 0}
    entry.update(kw)
    return entry


def _air(aid: int, team: int, x: int, y: int, **kw) -> dict:
    entry = {"id": aid, "team": team, "name": "a%d" % aid, "state": "patrol",
             "alt_tier": "mid", "pos_cm": [x, y], "facing": 90, "hp": 10,
             "hp_max": 10, "ammo": {"BOMB": 2}, "paratroop": None,
             "spotted": False, "engage_air": None, "task": None,
             "alt_pending": None}
    entry.update(kw)
    return entry


class _AirCmdSpy:
    """命令记录桩（fsm 空令分发的调用面断言——calls=[(名, args, kwargs)]）。"""

    def __init__(self):
        self.calls = []

    def _log(self, name, *a, **kw):
        self.calls.append((name, a, kw))
        return [object()]

    # 空令族
    def air_move(self, ids, dest):
        return self._log("air_move", tuple(ids), tuple(dest))

    def air_patrol(self, ids, center, radius=None):
        return self._log("air_patrol", tuple(ids), tuple(center))

    def air_reset(self, ids):
        return self._log("air_reset", tuple(ids))

    def air_alt(self, ids, tier):
        return self._log("air_alt", tuple(ids), tier)

    def air_engage_air(self, ids, engage):
        return self._log("air_engage_air", tuple(ids), engage)

    def air_disengage(self, ids):
        return self._log("air_disengage", tuple(ids))

    def air_rtb(self, ids):
        return self._log("air_rtb", tuple(ids))

    def air_strike(self, aid, target, weapon="BOMB", axis=None):
        return self._log("air_strike", aid, tuple(target), weapon=weapon,
                         axis=axis)

    def air_airdrop(self, aid, point):
        return self._log("air_airdrop", aid, tuple(point))

    # 地面族
    def stop(self, ids):
        return self._log("stop", tuple(ids))

    def cancel(self, ids):
        return self._log("cancel", tuple(ids))

    def move(self, ids, dest, mode="NORMAL", queue=False):
        return self._log("move", tuple(ids), tuple(dest), mode=mode)

    def smoke(self, ids):
        return self._log("smoke", tuple(ids))

    def sprint(self, ids):
        return self._log("sprint", tuple(ids))

    def stance(self, ids, s):
        return self._log("stance", tuple(ids), s)

    def smoke_sprint_stance(self, ids, stance="HOLD_FIRE"):
        return self._log("smoke_sprint_stance", tuple(ids))

    def reverse(self, ids, dest):
        return self._log("reverse", tuple(ids), tuple(dest))

    def fire_mission(self, uid, point, **kw):
        return self._log("fire_mission", uid, tuple(point), **kw)

    def attack(self, uid, foe, queue=False):
        return self._log("attack", uid, foe, queue=queue)

    def unload(self, ids, cm=None, building_id=None, queue=False):
        return self._log("unload", tuple(ids), cm, building_id)

    def sniper_cover(self, ids, foe):
        return self._log("sniper_cover", tuple(ids), foe)

    def supply_dock(self, ids, truck):
        return self._log("supply_dock", tuple(ids), truck)


# ── §4 ②段：选区双通道 ──


class TestAirSelection(unittest.TestCase):
    """selected_air 双通道：点选/框选并集/TAB 跨池/编组二元组。"""

    def _fsm(self, units=(), aircraft=()):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("combat", 700, units=units, aircraft=aircraft))
        return f

    def test_click_aircraft_selects_air_channel(self):
        f = self._fsm(aircraft=[_air(1, 0, 50000, 60000)])
        f.click_aircraft(1)
        self.assertEqual(f.selected_air, (1,))
        self.assertEqual(f.selected, ())            # 单位通道不受染

    def test_click_aircraft_shift_toggles(self):
        f = self._fsm(aircraft=[_air(1, 0, 0, 0), _air(2, 0, 100, 0)])
        f.click_aircraft(1)
        f.click_aircraft(2, shift=True)
        self.assertEqual(f.selected_air, (1, 2))
        f.click_aircraft(1, shift=True)             # 再点=移除
        self.assertEqual(f.selected_air, (2,))

    def test_box_select_union_units_and_aircraft(self):
        f = self._fsm(units=[_unit(1, 0, 10000, 20000)],
                      aircraft=[_air(1, 0, 12000, 21000), _air(2, 1, 12000, 21000)])
        f.box_select((0, 0), (60000, 60000))
        self.assertEqual(f.selected, (1,))           # 敌机不入选（视角过滤）
        self.assertEqual(f.selected_air, (1,))

    def test_clear_selection_clears_both_channels(self):
        f = self._fsm(units=[_unit(1, 0, 0, 0)], aircraft=[_air(1, 0, 0, 0)])
        f.select_units([1])
        f.select_aircraft([1])
        f.clear_selection()
        self.assertEqual((f.selected, f.selected_air), ((), ()))

    def test_tab_cycles_across_both_pools(self):
        f = self._fsm(units=[_unit(7, 0, 0, 0)], aircraft=[_air(3, 0, 0, 0)])
        f.select_units([7])
        f.select_aircraft([3])
        self.assertEqual(f.focus_unit, 7)
        f.cycle_focus()
        self.assertEqual(f.focus_aircraft, 3)        # 跨池循环
        f.cycle_focus()
        self.assertEqual(f.focus_unit, 7)

    def test_group_stores_unit_air_two_tuple(self):
        """§4 ②段：编组 Ctrl+1..9 存 (unit_ids, air_ids) 二元组（id 两空间独立
        ——tick.py next_unit_id/next_aircraft_id 双计数器实证，并存需二元组）。"""
        f = self._fsm(units=[_unit(1, 0, 0, 0), _unit(2, 0, 100, 0)],
                      aircraft=[_air(1, 0, 50, 50)])
        f.select_units([1, 2])
        f.select_aircraft([1])
        self.assertEqual(f.key("1", ctrl=True), "group_assign")
        self.assertEqual(f.groups[1], ((1, 2), (1,)))

    def test_recall_group_restores_both_channels_with_pruning(self):
        f = self._fsm(units=[_unit(1, 0, 0, 0)], aircraft=[_air(1, 0, 0, 0),
                                                           _air(2, 0, 99, 99)])
        f.select_units([1])
        f.select_aircraft([1, 2])
        f.key("1", ctrl=True)
        f.clear_selection()
        f.on_frame(_frame("combat", 800, units=[_unit(1, 0, 5, 5)],
                          aircraft=[_air(1, 0, 5, 5)]))   # 单位 1 在、飞机 2 已失
        self.assertEqual(f.key("1"), "group_recall")
        self.assertEqual(f.selected, (1,))
        self.assertEqual(f.selected_air, (1,))       # 剪尸跨两池

    def test_air_only_group_all_dead_toasts(self):
        f = self._fsm(aircraft=[_air(1, 0, 0, 0)])
        f.select_aircraft([1])
        f.key("1", ctrl=True)
        f.on_frame(_frame("combat", 800, aircraft=[]))
        self.assertEqual(f.key("1"), "group_recall")
        self.assertTrue(any("已全灭" in n["text"] for n in f.notifications))
        self.assertIn(1, f.groups)                   # 不清号


# ── §4 ③段：飞机命令键位 ──


class TestAirHotkeys(unittest.TestCase):

    def _fsm(self, aircraft=(), units=()):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("combat", 700, aircraft=aircraft, units=units))
        return f

    def test_V_alt_cycle_per_aircraft_from_frame(self):
        f = self._fsm(aircraft=[_air(1, 0, 0, 0, alt_tier="low"),
                                _air(2, 0, 0, 0, alt_tier="high")])
        f.select_aircraft([1, 2])
        cmd = _AirCmdSpy()
        self.assertEqual(f.key("V", cmd=cmd), "air_alt")
        tiers = [c[1][1] for c in cmd.calls if c[0] == "air_alt"]
        self.assertEqual(tiers, ["MID", "LOW"])      # 逐机循环取帧内现值

    def test_B_rtb_with_irreversible_toast(self):
        # 〔P1 机制块 2026-10-13：B 双通道（manual ORDERS/RTB 通用令）——返回动作
        # 名 rtb；飞机通道走 air_rtb 令（地面支锚另见 test_p1_mechanics）。〕
        f = self._fsm(aircraft=[_air(1, 0, 0, 0)])
        f.select_aircraft([1])
        cmd = _AirCmdSpy()
        self.assertEqual(f.key("B", cmd=cmd), "rtb")
        self.assertTrue(any(c[0] == "air_rtb" for c in cmd.calls))
        self.assertTrue(any("不可逆" in n["text"] for n in f.notifications))

    def test_J_engage_toggle_from_frame(self):
        f = self._fsm(aircraft=[_air(1, 0, 0, 0, engage_air=False)])
        f.select_aircraft([1])
        cmd = _AirCmdSpy()
        self.assertEqual(f.key("J", cmd=cmd), "air_engage")
        call = next(c for c in cmd.calls if c[0] == "air_engage_air")
        self.assertIs(call[1][1], True)

    def test_Y_disengage(self):
        f = self._fsm(aircraft=[_air(1, 0, 0, 0)])
        f.select_aircraft([1])
        cmd = _AirCmdSpy()
        self.assertEqual(f.key("Y", cmd=cmd), "air_disengage")

    def test_E_with_air_selection_resets_in_place(self):
        f = self._fsm(units=[_unit(1, 0, 0, 0)], aircraft=[_air(1, 0, 0, 0)])
        f.select_units([1])
        f.select_aircraft([1])
        cmd = _AirCmdSpy()
        self.assertEqual(f.key("E", cmd=cmd), "cancel")
        kinds = [c[0] for c in cmd.calls]
        self.assertIn("cancel", kinds)               # 地面通道照旧
        self.assertIn("air_reset", kinds)            # 空选区=原地重置（E 映射）

    def test_strike_uses_selected_aircraft_first(self):
        f = self._fsm(aircraft=[_air(9, 0, 0, 0, ammo={"BOMB": 1})])
        f.select_aircraft([9])
        f.arm_order("strike")
        cmd = _AirCmdSpy()
        self.assertTrue(f.execute_armed_ground((100000, 50000), cmd))
        call = next(c for c in cmd.calls if c[0] == "air_strike")
        self.assertEqual(call[1][0], 9)              # 选中机优先（不再自动代选）
        self.assertIsNone(f.armed_order)

    def test_strike_fallback_auto_pick_with_toast(self):
        f = self._fsm(aircraft=[_air(5, 0, 0, 0, state="inbound",
                                     ammo={"BOMB": 2})])
        f.arm_order("strike")
        cmd = _AirCmdSpy()
        self.assertTrue(f.execute_armed_ground((100000, 50000), cmd))
        call = next(c for c in cmd.calls if c[0] == "air_strike")
        self.assertEqual(call[1][0], 5)              # 无空选区=兜底代选
        self.assertTrue(any("代选" in n["text"] for n in f.notifications))

    def test_strike_drag_line_axis(self):
        """K+拖拽画线（评审②补）：axis=(起点,终点) 透传 AirStrikeCmd。"""
        f = self._fsm(aircraft=[_air(1, 0, 0, 0)])
        f.select_aircraft([1])
        f.arm_order("strike")
        cmd = _AirCmdSpy()
        self.assertTrue(f.execute_armed_strike_line((100000, 40000),
                                                    (100000, 60000), cmd))
        call = next(c for c in cmd.calls if c[0] == "air_strike")
        self.assertEqual(call[2]["axis"],
                         ((100000, 40000), (100000, 60000)))
        self.assertIsNone(f.armed_order)

    def test_air_pages_gates(self):
        f = ShellFsm()                               # config 页
        for name in ("V", "B", "J", "Y", "F", "U", "N"):
            f.notifications.clear()
            self.assertEqual(f.key(name, cmd=_AirCmdSpy()), "blocked", name)
        f.start_deploy()
        f.on_frame(_frame("deploy", 10))
        f.notifications.clear()
        self.assertEqual(f.key("V", cmd=_AirCmdSpy()), "blocked")   # 空令实战页
        self.assertEqual(f.key("F", cmd=_AirCmdSpy()), "arm:march")  # 行军=移动族


# ── §3：炮击参数态 ──


class TestFireMissionParams(unittest.TestCase):

    def _fsm(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("combat", 700))
        return f

    def test_fm_param_value_gates(self):
        f = self._fsm()
        f.set_fm_param("form", "LINE")
        self.assertEqual(f.fm_params["form"], "LINE")
        with self.assertRaises(ValueError):
            f.set_fm_param("form", "NUCLEAR")
        # 〔P1 机制块 2026-10-13：PRECISION=第三弹药位（manual.txt:456-458）——
        # 合法值不再拒；域外值照拒。〕
        f.set_fm_param("ammo", "PRECISION")
        self.assertEqual(f.fm_params["ammo"], "PRECISION")
        with self.assertRaises(ValueError):
            f.set_fm_param("ammo", "NUCLEAR")
        with self.assertRaises(ValueError):
            f.set_fm_param("ammo_mult", 4)           # 1..3
        with self.assertRaises(ValueError):
            f.set_fm_param("salvo", "QUARTER")

    def test_fm_kwargs_translate(self):
        f = self._fsm()
        f.set_fm_param("form", "CREEP")
        f.set_fm_param("ammo", "SMOKE")
        f.set_fm_param("ammo_mult", 2)
        f.set_fm_param("salvo", "HALF")
        f.set_fm_param("creep_idx", 1)
        kw = f.fm_kwargs()
        self.assertEqual(kw["form"], "CREEP")
        self.assertEqual(kw["ammo"], "SMOKE")
        self.assertEqual(kw["ammo_mult"], 2)
        self.assertEqual(kw["salvo_mode"], "HALF")
        self.assertEqual(kw["creep_speed"], CREEP_SPEEDS_CM[1])

    def test_fm_line_execution_passes_params(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("combat", 700, units=[_unit(5, 0, 0, 0)]))
        f.select_units([5])                           # 炮击载体（资格门在后端）
        f.set_fm_param("form", "LINE")
        f.arm_order("fire_mission")
        cmd = _AirCmdSpy()
        self.assertTrue(f.execute_armed_fm_line((100000, 40000),
                                                (120000, 40000), cmd))
        call = next(c for c in cmd.calls if c[0] == "fire_mission")
        self.assertEqual(call[1][1], ((100000, 40000), (120000, 40000)))
        self.assertEqual(call[2].get("form"), "LINE")


# ── §6：新增 UI 入口待令组 ──


class TestSection6Entries(unittest.TestCase):

    def _fsm(self, units=()):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("combat", 700, units=units))
        return f

    def test_march_arm_and_execute(self):
        f = self._fsm(units=[_unit(1, 0, 0, 0)])
        f.select_units([1])
        self.assertEqual(f.key("F"), "arm:march")
        cmd = _AirCmdSpy()
        self.assertTrue(f.execute_armed_ground((70000, 50000), cmd))
        call = next(c for c in cmd.calls if c[0] == "move")
        self.assertEqual(call[2], {"mode": "MARCH"})

    def test_unload_arm_and_execute(self):
        f = self._fsm(units=[_unit(1, 0, 0, 0)])
        f.select_units([1])
        self.assertEqual(f.key("U"), "arm:unload")
        cmd = _AirCmdSpy()
        self.assertTrue(f.execute_armed_ground((70000, 50000), cmd))
        self.assertTrue(any(c[0] == "unload" for c in cmd.calls))

    def test_sniper_arm_requires_enemy_click(self):
        # 〔P1 机制块 2026-10-13：狙击观测挪 L 键（N 让位给手册激光照射键，
        # 留痕 shell_fsm.ORDER_GROUPS_ARMABLE 注）。〕
        f = self._fsm(units=[_unit(1, 0, 0, 0)])
        f.select_units([1])
        self.assertEqual(f.key("L"), "arm:sniper")
        cmd = _AirCmdSpy()
        self.assertTrue(f.execute_armed_unit(8, cmd, enemy=True))
        self.assertTrue(any(c[0] == "sniper_cover" for c in cmd.calls))
        self.assertIsNone(f.armed_order)

    def test_supply_arm_clicks_own_truck(self):
        f = self._fsm(units=[_unit(1, 0, 0, 0)])
        f.select_units([1])
        f.arm_order("supply")
        cmd = _AirCmdSpy()
        self.assertTrue(f.execute_armed_unit(4, cmd, enemy=False))
        self.assertTrue(any(c[0] == "supply_dock" for c in cmd.calls))


# ── §4 ④段：拒绝 toast ──


class TestRejectionToasts(unittest.TestCase):

    def test_own_rejection_becomes_toast_without_duplication(self):
        f = ShellFsm()
        f.start_deploy()
        rej = {"tick": 700, "cmd": "AirAltCmd", "ref_id": 1}
        f.on_frame(_frame("combat", 700, aircraft=[_air(1, 0, 0, 0)],
                          rejections=[rej]))
        self.assertTrue(any("高度" in n["text"] for n in f.notifications))
        n0 = len([n for n in f.notifications if "高度" in n["text"]])
        f.on_frame(_frame("combat", 701, aircraft=[_air(1, 0, 0, 0)],
                          rejections=[rej]))          # 同条重放不重复 toast
        self.assertEqual(len([n for n in f.notifications
                              if "高度" in n["text"]]), n0)

    def test_foreign_rejection_silent(self):
        """敌实体拒绝（可见敌）不进 toast——操作情报噪音过滤。"""
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("combat", 700, aircraft=[
            _air(1, 1, 0, 0)],                        # 敌机（视角内可见）
            rejections=[{"tick": 700, "cmd": "MoveCmd", "ref_id": 1}]))
        self.assertFalse(f.notifications)


# ── cmd_bus：六空令包装 + fire_mission 全参（真实世界生效面）──


class TestCmdBusAirWrappers(unittest.TestCase):

    def setUp(self):
        self.w = make_world(11, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        self.bus = CmdBus(self.w, 0)
        self.bus.air_call(CARD_OBJECTS["IL2M"], {"BOMB": 2})
        world_tick(self.w)
        self.a = self.w.aircraft[0]
        self.assertEqual(self.a.team, 0)

    def test_move_patrol_alt_rtb_enqueued_and_effective(self):
        self.assertTrue(self.bus.air_move([self.a.id], (120000, 60000)))
        world_tick(self.w)
        self.assertFalse(self.a.patrol_loop)          # 直飞航路（转场）
        self.assertTrue(self.bus.air_patrol([self.a.id], (110000, 50000)))
        world_tick(self.w)
        self.assertTrue(self.a.patrol_loop)           # CAP 盘旋
        self.assertIs(self.a.task.kind, TaskKind.PATROL)
        self.assertTrue(self.bus.air_alt([self.a.id], "LOW"))
        world_tick(self.w)
        self.assertIsNotNone(self.a.alt_pending)      # 换层在途（B-29）
        self.assertTrue(self.bus.air_rtb([self.a.id]))
        world_tick(self.w)
        self.assertEqual(self.a.state.name, "RTB")

    def test_engage_air_on_fighter_flips_slot(self):
        """PE2（BOMBER 无对空槽 can_engage_air=False）引擎门拒；YAK9 槽位翻真。"""
        self.bus.air_call(CARD_OBJECTS["PE2"], {"BOMB": 1})
        world_tick(self.w)
        p2 = next(x for x in self.w.aircraft if x is not self.a)
        self.assertIsNone(p2.engage_air)              # 无槽（cards_air 实证）
        self.assertTrue(self.bus.air_engage_air([p2.id], True))
        world_tick(self.w)
        self.assertIsNone(p2.engage_air)              # B-21 门（无槽不写）
        self.bus.air_call(CARD_OBJECTS["YAK9"], {})
        world_tick(self.w)
        y = next(x for x in self.w.aircraft if x not in (self.a, p2))
        self.assertFalse(y.engage_air)                # 槽位初值 False
        self.assertTrue(self.bus.air_engage_air([y.id], True))
        world_tick(self.w)
        self.assertTrue(y.engage_air)

    def test_air_reset_interrupts_ingress_to_patrol(self):
        """E 键映射：AirPatrolCmd 原地重置（中断 INGRESS 段任务回盘旋）。"""
        self.bus.air_strike(self.a.id, (100000, 50000))
        world_tick(self.w)
        self.assertIsNotNone(self.a.task)
        self.assertIs(self.a.task.kind, TaskKind.STRIKE)
        self.assertTrue(self.bus.air_reset([self.a.id]))
        world_tick(self.w)
        self.assertIs(self.a.task.kind, TaskKind.PATROL)

    def test_air_strike_axis_passthrough(self):
        axis = ((100000, 40000), (100000, 60000))
        cmd = self.bus.air_strike(self.a.id, (100000, 40000), axis=axis)
        self.assertEqual(cmd.axis, ((100000, 40000), (100000, 60000)))
        self.assertIsInstance(cmd.axis[0], tuple)   # 整型化元组（wire 编码面）

    def test_air_patrol_radius_defaults_to_tables_value(self):
        """AIR_PATROL_RADIUS_CM 镜像 tables.py patrol_orbit_radius_cm 现值
        （cmd_bus 禁 import tables——AST 守卫②；同值由本锚锁死防漂移）。"""
        from sovs.sim.tables import CONFIG
        from sovs.ui.cmd_bus import AIR_PATROL_RADIUS_CM
        self.assertEqual(AIR_PATROL_RADIUS_CM, CONFIG.patrol_orbit_radius_cm)

    def test_trail_kinds_recorded(self):
        self.bus.air_patrol([self.a.id], (0, 0))
        self.bus.air_alt([self.a.id], "HIGH")
        kinds = {t["kind"] for t in self.bus.trail}
        self.assertTrue({"air_patrol", "air_alt"} <= kinds)


class TestTrailMarkTransient(unittest.TestCase):
    """痕迹呈现层短暂显示语义（2026-10-15 排障轮——用户报障「改了路线后
    旧途径点还保留/变位」）：移动族标记=断箭「下令后短暂显示」——同单位更晚
    移动族令即时取代旧标＋TTL 自隐；战斗类标记（attack/fire_mission 等）不
    受限；cmd_bus 数据面零扰动（visible_trail_entries 纯函数锚）。"""

    def test_reroute_supersedes_old_move_mark(self):
        from sovs.ui.scene import visible_trail_entries
        trail = [{"kind": "move", "unit_ids": [1], "point_cm": [1, 1],
                  "tick": 10},
                 {"kind": "move", "unit_ids": [1], "point_cm": [2, 2],
                  "tick": 20}]
        vis = visible_trail_entries(trail, 25)
        self.assertEqual([t["point_cm"] for t in vis], [[2, 2]])  # 只剩新落点

    def test_other_units_marks_not_eaten(self):
        from sovs.ui.scene import visible_trail_entries
        trail = [{"kind": "move", "unit_ids": [1], "point_cm": [1, 1],
                  "tick": 10},
                 {"kind": "move", "unit_ids": [2], "point_cm": [3, 3],
                  "tick": 20}]
        vis = visible_trail_entries(trail, 25)
        self.assertEqual(len(vis), 2)                 # 不同单位互不取代

    def test_move_family_ttl_and_air_family(self):
        from sovs.ui.scene import visible_trail_entries
        trail = [{"kind": "move", "unit_ids": [1], "point_cm": [1, 1],
                  "tick": 0},
                 {"kind": "air_move", "unit_ids": [7], "point_cm": [2, 2],
                  "tick": 0}]
        self.assertEqual(visible_trail_entries(trail, 61), [])   # 双双超时
        self.assertEqual(len(visible_trail_entries(trail, 60)), 2)  # 边界在册

    def test_combat_marks_not_ttl_limited(self):
        from sovs.ui.scene import visible_trail_entries
        trail = [{"kind": "fire_mission", "unit_ids": [1], "point_cm": [1, 1],
                  "tick": 0},
                 {"kind": "attack", "unit_ids": [1], "point_cm": [2, 2],
                  "tick": 0},
                 {"kind": "smoke", "unit_ids": [1], "point_cm": [3, 3],
                  "tick": 0}]
        vis = visible_trail_entries(trail, 500)      # 远超 TTL 仍在册
        self.assertEqual({t["kind"] for t in vis},
                         {"fire_mission", "attack", "smoke"})


class TestCmdBusFireMissionFullParams(unittest.TestCase):

    def setUp(self):
        self.w = make_world(11, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        self.w.players[0].deck_slots.append(DeckSlot(_TPL["SU_MORTAR82"], 1))
        self.gun = add_unit(self.w, make_unit(self.w, _TPL["SU_MORTAR82"], 0, 0,
                                              (50000, 50000)))
        self.bus = CmdBus(self.w, 0)

    def test_line_form_passthrough(self):
        line = ((100000, 40000), (120000, 40000))
        cmds = self.bus.fire_mission(self.gun.id, line, form="LINE",
                                     ammo_mult=2)
        fm = next(c for c in cmds if type(c).__name__ == "FireMissionCmd")
        self.assertIs(fm.form, FireMissionForm.LINE)
        self.assertEqual(fm.line, line)
        self.assertEqual(fm.ammo_mult, 2)
        world_tick(self.w)
        self.assertIs(self.gun.fire_mission.form, FireMissionForm.LINE)
        self.assertEqual(self.gun.fire_mission.target_line, line)

    def test_creep_form_with_speed_and_half_salvo(self):
        line = ((100000, 40000), (100000, 60000))
        self.bus.fire_mission(self.gun.id, line, form="CREEP",
                              salvo_mode="HALF", creep_speed=CREEP_SPEEDS_CM[0])
        world_tick(self.w)
        m = self.gun.fire_mission
        self.assertIs(m.form, FireMissionForm.CREEP)
        self.assertEqual(m.creep_speed_cm_tick, CREEP_SPEEDS_CM[0])
        self.assertIs(m.salvo_mode, SalvoMode.HALF)

    def test_smoke_ammo_passthrough(self):
        """SU_MORTAR82 带烟弹武器行（data/yaml/units/su_infantry.yaml
        W_SU_M82_SMOKE）——SMOKE 弹药位经引擎烟档门。"""
        self.bus.fire_mission(self.gun.id, (100000, 50000), ammo="SMOKE")
        world_tick(self.w)
        self.assertIsNotNone(self.gun.fire_mission)
        self.assertEqual(self.gun.fire_mission.ammo, "SMOKE")


class TestCmdBusSection6Wrappers(unittest.TestCase):

    def setUp(self):
        self.w = make_world(11, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        for key in ("SU_RIFLE", "SU_TRUCK"):
            self.w.players[0].deck_slots.append(DeckSlot(_TPL[key], 1))
        self.rifle = add_unit(self.w, make_unit(self.w, _TPL["SU_RIFLE"], 0, 0,
                                                (50000, 50000)))
        self.truck = add_unit(self.w, make_unit(self.w, _TPL["SU_TRUCK"], 0, 0,
                                                (60000, 50000)))
        self.bus = CmdBus(self.w, 0)

    def test_march_uses_move_mode_march(self):
        cmds = self.bus.move([self.rifle.id], (70000, 50000), mode="MARCH")
        self.assertIs(cmds[0].mode, MoveMode.MARCH)

    def test_unload_dismount_then_move(self):
        cmds = self.bus.unload([self.rifle.id], (65000, 50000))
        names = [type(c).__name__ for c in cmds]
        self.assertIn("DismountCmd", names)
        self.assertIn("MoveCmd", names)

    def test_sniper_cover_enqueued(self):
        foe = add_unit(self.w, make_unit(self.w, _TPL["SU_RIFLE"], 1, 1,
                                         (52000, 50000)))
        cmds = self.bus.sniper_cover([self.rifle.id], foe.id)
        self.assertEqual([type(c).__name__ for c in cmds], ["SetSniperCoverCmd"])

    def test_ambush_deploy_pack_formation(self):
        self.bus.ambush([self.rifle.id])
        self.bus.deploy_gun([self.rifle.id])
        self.bus.pack_gun([self.rifle.id])
        self.bus.formation([self.rifle.id], "LINE")
        names = [type(c).__name__ for c in self.w.command_queue]
        self.assertEqual(names, ["ToggleAmbushCmd", "DeployCmd", "PackCmd",
                                 "FormationCmd"])

    def test_supply_dock_moves_into_truck(self):
        cmds = self.bus.supply_dock([self.rifle.id], self.truck.id)
        self.assertTrue(any(type(c).__name__ == "MoveCmd" for c in cmds))
        move = next(c for c in cmds if type(c).__name__ == "MoveCmd")
        self.assertEqual(move.path[0], self.truck.pos)


# ── §7/会话：卡组泛化（自制卡组开局）──


class TestSessionDeckGeneralization(unittest.TestCase):

    def test_deck_list_contains_builtin_decks(self):
        from sovs.app.session import SkirmishSession
        session = SkirmishSession(seed=42)
        decks = session.deck_list()
        self.assertIn("su_min", decks)
        self.assertIn("ger_min", decks)

    def test_new_game_with_custom_deck(self):
        from sovs.app.deck_editor import DeckEditor
        from sovs.app.session import SkirmishSession
        editor = DeckEditor()
        self.addCleanup(editor.delete, "gp01_fe_tmp")
        editor.save("gp01_fe_tmp", "SOVIET",
                    [("SU_RECON", 1), ("SU_RIFLE", 2), ("SU_MORTAR82", 1),
                     ("SU_T3485", 1), ("SU_ZIS3", 1)])
        session = SkirmishSession(seed=42, human_deck="gp01_fe_tmp")
        w = session.world
        ids = [s.template.template_id for s in w.players[0].deck_slots]
        self.assertIn(_TPL["SU_MORTAR82"].template_id, ids)  # 自制卡组真挂上
        kev_ids = [s.template.template_id for s in w.players[1].deck_slots]
        self.assertTrue(all(tid >= 201 for tid in kev_ids),
                        "对手按阵营镜像换德军面：%s" % kev_ids)


class TestStateCn(unittest.TestCase):
    """飞机状态中文名（selection_panel/hud 消费的共享词面）。"""

    def test_state_cn_covers_aircraft_states(self):
        for s in ("inbound", "patrol", "strike", "rtb", "dogfight"):
            self.assertIn(s, STATE_CN)


if __name__ == "__main__":
    unittest.main()
