"""B3 命令格三态过滤矩阵测试（2026-10-13）——纯逻辑，无 GL，无头可跑。

手册锚：manual.txt:344-346「A menu of icons shows all possible orders a unit
can be given…located at the bottom right」＋manual.txt:482-485（专项能力出自
特定单位）＋basics.txt:62（空选区无 Action panel）。三态 show/grey/hide 判据
逐门对表 order_filter.eligible_orders；布局面集成=鸭子窗驱动
layout_battle_buttons（同 B1 几何门禁法——ShellWindow 构造在无显示环境必炸，
tests/test_shell_window.py:19-27 头注自证）；热键宽容=真引擎链（make_world/
CmdBus/consume_commands→rejections→fsm toast）。
"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.sim.air import PHASE_COMBAT                                # noqa: E402
from sovs.sim.state_frame import state_frame                         # noqa: E402
from sovs.sim.tick import (consume_commands, make_unit, make_world,  # noqa: E402
                           add_unit)
from sovs.sim.types import (ElementTemplate, ElementType,            # noqa: E402
                            MovementClass, UnitTemplate, UnitType,
                            WeaponTemplate)
from sovs.ui.hud_bottom import PANEL_KEY_MIRROR, layout_battle_buttons  # noqa: E402
from sovs.ui.order_filter import eligible_orders                     # noqa: E402
from sovs.ui.shell_fsm import ShellFsm                               # noqa: E402


def _caps(**kw):
    base = {"squad": False, "smoke": False, "reverse": False, "ambush": False,
            "sniper": False, "seats": 0, "deploy_gun": False, "indirect": False,
            "tow": False, "transport": False, "radar": False}
    base.update(kw)
    return base


def _unit(uid, caps=None, team=0, **kw):
    entry = {"id": uid, "team": team, "pos_cm": [100000, 30000],
             "smoke_left": 0, "mounted": False, "towed": False}
    if caps is not None:
        entry["caps"] = caps
    entry.update(kw)
    return entry


def _air(aid, team=0, **kw):
    entry = {"id": aid, "team": team, "state": "patrol", "alt_tier": "mid",
             "ammo": {}, "paratroop": None, "engage_air": None,
             "alt_ceiling": "mid", "can_afterburner": False, "can_decoy": False,
             "decoy_left": 0}
    entry.update(kw)
    return entry


def _frame(units=(), aircraft=(), lasers=()):
    return {"view": 0, "units": list(units), "aircraft": list(aircraft),
            "lasers": list(lasers)}


# ── 真实卡判据样例（cards_ground/cards_air v1 实测事实——见 B3 方案 manualBasis）──
_RIFLE = _caps(squad=True)                                  # 步枪排：班元素
_ZIS3 = _caps(indirect=True)                                # ZiS-3：曲射位
_TRUCK = _caps(transport=True, seats=1)                     # 卡车队：运兵舱
_FLAK = _caps(radar=True)                                   # 高炮：对空资格（_aa_eligible 同源）


class TestEligibleOrdersMatrix(unittest.TestCase):
    """三态矩阵逐门断言（acceptance ①-⑧）。"""

    def test_01_empty_selection_all_hidden(self):
        states = eligible_orders(_frame(units=[_unit(1, _RIFLE)]), (), ())
        self.assertTrue(all(v == "hide" for v in states.values()),
                        [k for k, v in states.items() if v != "hide"])

    def test_02_rifle_squad_shows_move_hides_specialists(self):
        states = eligible_orders(_frame(units=[_unit(1, _RIFLE)]), (1,), ())
        for key in ("fm", "precision", "laser", "sniper", "ambush", "smoke_x"):
            self.assertEqual(states[key], "hide", key)
        for key in ("stop", "march", "attack", "cancel", "sprint"):
            self.assertEqual(states[key], "show", key)

    def test_03_zis3_fm_shows_precision_grey_without_laser(self):
        states = eligible_orders(_frame(units=[_unit(1, _ZIS3)]), (1,), ())
        self.assertEqual(states["fm"], "show")
        self.assertEqual(states["precision"], "grey")     # 帧无 lasers
        lit = eligible_orders(_frame(units=[_unit(1, _ZIS3)],
                                     lasers=[{"pos_cm": [1, 2], "team": 0}]),
                              (1,), ())
        self.assertEqual(lit["precision"], "show")

    def test_04_truck_mount_hidden_unload_shown(self):
        states = eligible_orders(_frame(units=[_unit(1, _TRUCK)]), (1,), ())
        self.assertEqual(states["mount"], "hide")          # 无 SQUAD 元素
        self.assertEqual(states["unload"], "show")         # seats>0

    def test_05_rifle_mount_shown_when_seats_on_field(self):
        states = eligible_orders(_frame(units=[_unit(1, _RIFLE),
                                               _unit(2, _TRUCK)]), (1,), ())
        self.assertEqual(states["mount"], "show")          # 场上存在座位载具

    def test_06_yak9_afterburner_and_decoy(self):
        yak = _air(11, alt_ceiling="high", can_afterburner=True,
                   can_decoy=True, decoy_left=2, engage_air=True)
        states = eligible_orders(_frame(aircraft=[yak]), (), (11,))
        self.assertEqual(states["air_ab"], "show")
        self.assertEqual(states["decoy"], "show")
        self.assertEqual(states["air_alt"], "show")        # high 有换层余量
        spent = eligible_orders(
            _frame(aircraft=[_air(11, can_decoy=True, decoy_left=0)]), (), (11,))
        self.assertEqual(spent["decoy"], "grey")           # 余 0=灰显不隐藏

    def test_07_il2m_no_afterburner_no_decoy(self):
        il2m = _air(12, can_afterburner=False, can_decoy=False, decoy_left=0)
        states = eligible_orders(_frame(aircraft=[il2m]), (), (12,))
        self.assertEqual(states["air_ab"], "hide")
        self.assertEqual(states["decoy"], "hide")

    def test_08_po2_single_tier_no_alt_room(self):
        po2 = _air(13, alt_ceiling="low")                  # 单层机 basics:316-318
        states = eligible_orders(_frame(aircraft=[po2]), (), (13,))
        self.assertEqual(states["decoy"], "hide")
        self.assertEqual(states["air_alt"], "hide")

    def test_09_strike_drop_follow_frame_aircraft(self):
        # 无在空带弹/载伞机→hide；有→show（有选区承载）
        no_air = eligible_orders(_frame(units=[_unit(1, _RIFLE)]), (1,), ())
        self.assertEqual(no_air["strike"], "hide")
        self.assertEqual(no_air["drop"], "hide")
        bomber = _air(21, ammo={"BOMB": 2})
        troop = _air(22, paratroop=922, paratroop_count=1)
        has = eligible_orders(_frame(units=[_unit(1, _RIFLE)],
                                     aircraft=[bomber, troop]), (1,), ())
        self.assertEqual(has["strike"], "show")
        self.assertEqual(has["drop"], "show")

    def test_10_smoke_grey_when_charges_spent(self):
        smoker = _unit(1, _caps(smoke=True), smoke_left=0)
        states = eligible_orders(_frame(units=[smoker]), (1,), ())
        self.assertEqual(states["smoke_x"], "grey")
        self.assertEqual(states["smoke_sprint"], "show")
        full = _unit(1, _caps(smoke=True), smoke_left=2)
        self.assertEqual(eligible_orders(_frame(units=[full]), (1,), ())
                         ["smoke_x"], "show")

    def test_11_radar_menu_path_for_pure_aa_selection(self):
        """终审第四批漏一处收口：ABILITIES Radar（manual.txt:534-539＋482-485
        「orders menu」）——纯高炮选区（非班单位）雷达钮 show；冲刺钮仍 hide
        （SQUAD 元素判据不变——修前雷达无任何命令格钮，菜单对雷达不可达）。"""
        states = eligible_orders(_frame(units=[_unit(1, _FLAK)]), (1,), ())
        self.assertEqual(states["radar"], "show")           # 菜单可达性收口
        self.assertEqual(states["sprint"], "hide")          # 高炮非班单位
        self.assertEqual(
            eligible_orders(_frame(units=[_unit(1, _RIFLE)]), (1,), ())
            ["radar"], "hide")                              # 步枪排无对空资格
        mixed = eligible_orders(_frame(units=[_unit(1, _FLAK),
                                              _unit(2, _RIFLE)]), (1, 2), ())
        self.assertEqual(mixed["radar"], "show")            # 混编=任一满足
        self.assertEqual(mixed["sprint"], "show")


def _duck_win(frame):
    fsm = ShellFsm()
    fsm.page = "battle"
    return SimpleNamespace(width=1280, height=800, frame=frame, fsm=fsm,
                           session=SimpleNamespace(air_roster=lambda: []),
                           _buttons=[])


class TestLayoutIntegrationDuckWindow(unittest.TestCase):
    """布局面集成（鸭子窗——B3 集成断言）：空选区无任何镜像键；步枪选区无
    fm/sniper、有 stop/sprint。"""

    def test_empty_selection_no_mirror_keys(self):
        win = _duck_win(_frame(units=[_unit(1, _RIFLE)]))
        layout_battle_buttons(win)
        mirror = set(PANEL_KEY_MIRROR)
        self.assertFalse([b.key for b in win._buttons if b.key in mirror])

    def test_rifle_selection_filtered_buttons(self):
        win = _duck_win(_frame(units=[_unit(1, _RIFLE)]))
        win.fsm.select_units([1])
        layout_battle_buttons(win)
        keys = {b.key for b in win._buttons}
        self.assertNotIn("fm", keys)
        self.assertNotIn("sniper", keys)
        self.assertIn("stop", keys)
        self.assertIn("sprint", keys)

    def test_grey_state_lays_out_disabled_tone(self):
        smoker = _unit(1, _caps(smoke=True), smoke_left=0)
        win = _duck_win(_frame(units=[smoker]))
        win.fsm.select_units([1])
        layout_battle_buttons(win)
        btn = next(b for b in win._buttons if b.key == "smoke_x")
        self.assertEqual(btn.tone, "disabled")             # grey=布局灰显

    def test_aa_selection_gets_radar_button_mirroring_z(self):
        """终审第四批：纯高炮选区布局出雷达(Z)钮（作战行第 8 键=ORDER_GRID_COLS
        恰满格）＋镜像 Z 同门同令；冲刺钮不布局（菜单过滤面与热键宽容并存）。"""
        win = _duck_win(_frame(units=[_unit(1, _FLAK)]))
        win.fsm.select_units([1])
        layout_battle_buttons(win)
        keys = {b.key for b in win._buttons}
        self.assertIn("radar", keys)
        self.assertNotIn("sprint", keys)                   # 非班单位 hide
        btn = next(b for b in win._buttons if b.key == "radar")
        self.assertEqual(btn.label, "雷达(Z)")
        self.assertEqual(PANEL_KEY_MIRROR["radar"], "Z")   # 按钮=按键同门同令


# ── 热键宽容（真引擎链）：热键全量通道不经过滤——按钮隐藏的命令仍可经键盘
#    下达，引擎门裁决并经 rejections→toast 反馈（manual_silent 拍板留痕）──

def _mk_rifle_tpl():
    return UnitTemplate(
        template_id=631, name="mc rifle", category=1, cost=30,
        element_templates=(ElementTemplate(
            element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
            hp_max=10, weapons=(WeaponTemplate(
                name="mc rifle gun", damage=2, max_range_cm=30000,
                ammo_base=100, salvo=1),),),),
        optics_ground_cm=30000, stealth_base=5, speed_tier=1,
        movement_class=MovementClass.FOOT)


def _mk_gun_tpl():
    return UnitTemplate(
        template_id=632, name="mc gun", category=3, cost=70,
        element_templates=(ElementTemplate(
            element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=8,
            weapons=(WeaponTemplate(
                name="mc howitzer", damage=30, max_range_cm=100000,
                blast_radius_cm=2500, ammo_base=60, salvo=2),),),),
        optics_ground_cm=30000, stealth_base=5, speed_tier=1,
        movement_class=MovementClass.WHEEL,
        mode_set=(1 << 0) | (1 << 1))                       # DIRECT|INDIRECT


class TestHotkeyToleranceRealEngine(unittest.TestCase):
    """热键宽容回归：无曲射选区 T 仍可待令/确认（非静默）；有曲射位但引擎门
    拒（PRECISION 无激光位）→rejections→toast 含「炮击任务被拒」。"""

    def test_T_hotkey_still_arms_and_reports_without_indirect(self):
        from sovs.ui.cmd_bus import CmdBus
        w = make_world(71, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        u = add_unit(w, make_unit(w, _mk_rifle_tpl(), 0, 0, (50000, 30000)))
        bus = CmdBus(w, 0)
        fsm = ShellFsm()
        fsm.start_deploy()
        fsm.on_frame(state_frame(w, 0))                     # phase=combat→battle
        self.assertEqual(fsm.page, "battle")
        fsm.select_units([u.id])
        self.assertEqual(fsm.key("T", cmd=bus), "arm:fire_mission")  # 热键不滤
        self.assertTrue(fsm.execute_armed_ground((100000, 50000), bus))
        self.assertEqual(fsm.armed_order, "fire_mission")   # 待令保留（反馈不散）
        self.assertTrue(any("曲射火力" in n["text"] for n in fsm.notifications))

    def test_engine_rejection_reaches_toast(self):
        from sovs.ui.cmd_bus import CmdBus
        w = make_world(72, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        gun = add_unit(w, make_unit(w, _mk_gun_tpl(), 0, 0, (50000, 30000)))
        bus = CmdBus(w, 0)
        fsm = ShellFsm()
        fsm.start_deploy()
        fsm.on_frame(state_frame(w, 0))
        fsm.select_units([gun.id])
        fsm.key("T", cmd=bus)
        fsm.set_fm_param("ammo", "PRECISION")               # 引擎门：无激光位拒
        self.assertTrue(fsm.execute_armed_ground((100000, 50000), bus))
        consume_commands(w)                                 # 引擎裁决
        self.assertTrue(any(r["cmd"] == "FireMissionCmd" for r in w.rejection_log))
        fsm.on_frame(state_frame(w, 0))                     # rejections→toast
        self.assertTrue(any("炮击任务被拒" in n["text"]
                            for n in fsm.notifications))


class TestIconCoverage(unittest.TestCase):
    """断箭式图标格覆盖（2026-10-14）：命令格全部行键必须有图标与 tooltip
    ——新增命令漏登记即红（manual.txt:344「menu of icons」）。"""

    def test_all_row_keys_have_icon_and_tooltip(self):
        from sovs.ui import hud_bottom, order_icons
        row_sets = (hud_bottom._ORDER_ROW_AIR, hud_bottom._ORDER_ROW_COMBAT,
                    hud_bottom._ORDER_ROW_MANEUVER, hud_bottom._ORDER_ROW_SUPPORT,
                    hud_bottom._ORDER_ROW_SUPPLY, hud_bottom._ORDER_ROW_AUX)
        keys = {key for row in row_sets for key, _ in row}
        missing_icon = keys - set(order_icons.ICON_FUNCS)
        missing_tip = keys - set(order_icons.TOOLTIPS)
        self.assertEqual(missing_icon, set(),
                         "缺图标：%s" % sorted(missing_icon))
        self.assertEqual(missing_tip, set(),
                         "缺 tooltip：%s" % sorted(missing_tip))

    def test_hotkey_of_label(self):
        from sovs.ui.order_icons import hotkey_of
        self.assertEqual(hotkey_of("雷达(Z)"), "Z")
        self.assertEqual(hotkey_of("高度(V)"), "V")
        self.assertIsNone(hotkey_of("伏击"))
        self.assertIsNone(hotkey_of("买1t"))


class TestOrderTileFilter(unittest.TestCase):
    """图标格按钮四边全含判定（2026-10-14 崩溃回归锚）：实机复现=炮击待令态
    参数条「fm_salvo_HALF」按钮（格上方 y≈320）被旧三边判定漏进 draw_order_tile
    →键不在 ICON_FUNCS→fallback 崩 tilt_angle。纯逻辑无 GL。"""

    def test_grid_buttons_exclude_above_grid(self):
        from sovs.ui.hud_bottom import Btn, order_tile_buttons
        w = SimpleNamespace(_buttons=[
            Btn(1000, 20, 40, 40, "fm", "炮击(T)"),            # 格内
            Btn(1006, 320, 60, 24, "fm_salvo_HALF", "半齐射"),  # 格正上方（崩点位）
            Btn(940, 20, 40, 40, "edge_x", "越左界"),           # x 越界
            Btn(1000, 20, 40, 300, "tall", "越上界"),           # yt 越上界
        ])
        got = order_tile_buttons(w, (950, 10, 1270, 242))
        self.assertEqual([b.key for b in got], ["fm"])


if __name__ == "__main__":
    unittest.main()
