"""B1 面板互斥几何门禁（2026-10-13）——**鸭子窗驱动**，无头沙箱常驻可跑。

结论先行：呼援轨地面卡压进选中卡面板、fm 参数条盖编组列/命令格两缺陷的
回归护栏。不建 arcade.Window（无显示环境建窗在 pyglet cocoa get_default_screen
处 IndexError——tests/test_shell_window.py:19-27 头注自证的失败模式），只以
SimpleNamespace 鸭子窗调 layout_*/几何纯算术函数（arcade 模块级 import 无
显示依赖——探针实证：无头沙箱 arcade 可导入、建窗才炸）。

判据（修前实跑 /tmp/qa_b1b2.py 复现锚）：①air:/buy: 按钮∩panel_geom==∅
（修前 buy:101..buy:107 六钮全部落入选中面板）；②fm_panel_geom∩grp: 按钮
==∅（修前 ∩ grp:7/8/9）；③CREEP 满配 fm 按钮串右缘≤x0+912 且⊆面板；④
fm_panel_geom∩order_grid_rect(rows 1..6)==∅（修前 12px 微叠）；⑤五处截宽点
fit_text 后实测宽≤容器宽（超长卡名样例）。
"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.ui import hud_top as _hud_top                               # noqa: E402
from sovs.ui.fm_panel import fm_panel_geom, layout_fm_panel          # noqa: E402
from sovs.ui.hud_bottom import (layout_air_rail, layout_battle_buttons,  # noqa: E402
                                layout_deploy_panel, layout_group_bar,
                                order_grid_rect)
from sovs.ui.hud_top import fit_text                                  # noqa: E402
from sovs.ui.palette import (LEFT_W, MARGIN, RAIL_W)                 # noqa: E402
from sovs.ui.selection_panel import layout_selection_panel, panel_geom  # noqa: E402
from sovs.ui.shell_fsm import ShellFsm                               # noqa: E402


def _est_width(text: str, size: float) -> float:
    """无头文本量尺（真 arcade.Text 需活动窗——本门禁不建窗）：CJK 双宽/ASCII
    单宽的确定性估算。截宽界在**本量尺**下断言（fit_text 契约=量尺宽≤容器宽，
    量尺换真字体时同式成立；真字体渲染面由 GL 类截图/视觉剧本承载）。"""
    return size * sum(2 if ord(ch) > 0x2E7F else 1 for ch in str(text))


class _HeadlessRulerTestCase(unittest.TestCase):
    """共用基类：patch hud_top.text_width 为无头估算量尺（fit_text 经模块
    globals 解析——patch 生效于全部布局层截宽点）。"""

    def setUp(self):
        import unittest.mock as mock
        self._ruler = mock.patch.object(_hud_top, "text_width", _est_width)
        self._ruler.start()
        self.addCleanup(self._ruler.stop)

    @staticmethod
    def width(text, size):
        return _est_width(text, size)


_W, _H = 1280, 800


def _duck_frame(*, deck=(), units=(), view=0):
    return {"players": [{"deck": list(deck)}], "units": list(units),
            "aircraft": [], "view": view, "lasers": []}


def _duck_win(*, page="battle", frame=None, roster=()):
    fsm = ShellFsm()
    fsm.page = page
    return SimpleNamespace(width=_W, height=_H,
                           frame=frame if frame is not None else _duck_frame(),
                           fsm=fsm,
                           session=SimpleNamespace(air_roster=lambda: list(roster)),
                           _buttons=[])


def _deck_slots(n=7):
    """su_min 同构卡组槽（n 卡非空降——修前 7 卡减空降 103=6 buy 钮复现锚）。"""
    return [{"template_id": 101 + i, "name": "卡组单位%02d" % i,
             "copies_left": 1, "airdrop": i == 2} for i in range(n)]


def _rect(btn_or_rect):
    if hasattr(btn_or_rect, "x0"):
        b = btn_or_rect
        return (b.x0, b.yb, b.x1, b.yt)
    x0, y0, x1, y1 = btn_or_rect
    return (x0, y0, x1, y1)


def _overlap(a, b) -> bool:
    ax0, ay0, ax1, ay1 = _rect(a)
    bx0, by0, bx1, by1 = _rect(b)
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


class TestSelectionClusterRightBottom(_HeadlessRulerTestCase):
    """〔BA 布局复刻轮 2026-10-15，用户拍板「完全复刻断箭战斗界面布局」〕
    选中反馈三件套进右下集群（官方指南七组件 5/6/7）：命令格=右下角、
    多选摘要行=格顶+12 右对齐、状态主卡=摘要行顶+12；**底中无任何面板**
    （strip x0 全在右半屏）。旧底中竖卡/底中长条两形态废止（§11.4 被
    本轮推翻——连续两轮翻案留痕）。"""

    def test_strip_above_grid_right_aligned_bottom_center_empty(self):
        from sovs.ui.hud_bottom import order_panel_rect
        win = _duck_win()
        x0, y0, x1, y1 = panel_geom(win)
        gx0, gy0, gx1, gy1 = order_panel_rect(win)
        self.assertAlmostEqual(y0, gy1 + 12, places=6)    # 摘要行=格顶+12
        self.assertEqual(y1 - y0, 64)                     # 行高 64
        self.assertAlmostEqual(x1, _W - 10, places=6)     # 与格右对齐
        self.assertEqual(x1 - x0, 600)                    # 行宽 600
        self.assertGreater(x0, _W / 2)                    # 全在右半屏=底中空

    def test_chips_single_row_inside_strip_capped(self):
        from sovs.ui.selection_panel import _chip_cap
        win = _duck_win()
        win.fsm.selected = tuple(range(101, 113))         # 12 单位（超容量截断）
        layout_selection_panel(win)
        chips = [b for b in win._buttons if b.key.startswith("sel:")]
        x0, y0, x1, y1 = panel_geom(win)
        self.assertTrue(chips)
        self.assertEqual(len(chips), _chip_cap(x1 - x0))  # 截断到容量
        for b in chips:                                   # 全含于行内
            self.assertGreaterEqual(b.x0, x0)
            self.assertLessEqual(b.x1, x1)
            self.assertGreaterEqual(b.yb, y0)
            self.assertLessEqual(b.yt, y1)
        self.assertEqual(len({b.yb for b in chips}), 1)   # 单行
        for a, b in zip(chips, chips[1:]):                # 小卡间互不重叠
            self.assertLessEqual(a.x1, b.x0)

    def test_cluster_stack_grid_strip_card_spacing(self):
        # 三件套垂直堆叠间距：格顶+12=摘要行底、摘要行顶+12=状态主卡底
        from sovs.ui.hud_bottom import order_panel_rect
        from sovs.ui.selection_panel import air_panel_geom
        win = _duck_win()
        grid_top = order_panel_rect(win)[3]
        strip = panel_geom(win)
        card = air_panel_geom(win)
        self.assertAlmostEqual(strip[1], grid_top + 12, places=6)
        self.assertAlmostEqual(card[1], strip[3] + 12, places=6)
        self.assertGreater(card[3], strip[3])             # 主卡在摘要行上方

    def test_panel_disjoint_from_five_hud_regions(self):
        # 摘要行 × 小地图/编组列(新位)/命令格(6 行满配)/呼援轨/fm 参数条——两两互斥
        win = _duck_win(frame=_duck_frame(deck=_deck_slots(7)))
        layout_battle_buttons(win)                  # 含 layout_air_rail（记 _rail_bottom）
        layout_selection_panel(win)
        layout_group_bar(win)
        panel = panel_geom(win)
        grp = [b for b in win._buttons if b.key.startswith("grp:")]
        self.assertTrue(grp)
        rail = [b for b in win._buttons
                if b.key.startswith("air:") or b.key.startswith("buy:")]
        self.assertTrue(rail)                       # 呼援卡在册（复现锚沿用）
        regions = {"小地图": (MARGIN, MARGIN, MARGIN + 220, MARGIN + 150),
                   "命令格6行满配": order_grid_rect(win, 6, 8),
                   "fm参数条": fm_panel_geom(win),
                   "呼援轨带": (MARGIN, min(b.yb for b in rail),
                                MARGIN + RAIL_W, max(b.yt for b in rail))}
        for name, r in regions.items():
            self.assertFalse(_overlap(panel, r), "摘要行 ∩ %s" % name)
        for b in grp + rail:
            self.assertFalse(_overlap(b, panel), "%s ∩ 摘要行" % b.key)

    def test_panel_geometry_static_across_rail_lengths(self):
        # 几何静态：呼援轨短（空 deck）/长（40 卡下探）摘要行矩形不变
        rects = []
        for deck in ((), _deck_slots(40)):
            win = _duck_win(frame=_duck_frame(deck=deck))
            layout_battle_buttons(win)
            layout_selection_panel(win)
            rects.append(panel_geom(win))
        self.assertEqual(rects[0], rects[1])


class TestGroupBarAlignsMinimap(_HeadlessRulerTestCase):
    """〔问题4·2026-10-15〕编组列 1..9 与小地图对齐式：x 缝 8、列底=小地图底、
    列顶=小地图顶（(150-14)/8=17 整除——钮高留实现自由度，测试只锚顶底齐平＋
    x 间距）。"""

    def test_group_bar_top_bottom_align_minimap(self):
        win = _duck_win()
        layout_group_bar(win)
        btns = sorted((b for b in win._buttons if b.key.startswith("grp:")),
                      key=lambda b: b.yb)
        self.assertEqual(len(btns), 9)
        self.assertAlmostEqual(btns[0].x0, MARGIN + 220 + 8, places=6)  # x 缝 8
        self.assertAlmostEqual(btns[0].yb, MARGIN, places=6)            # 列底=图底
        self.assertAlmostEqual(btns[-1].yt, MARGIN + 150, places=6)     # 列顶=图顶
        for b in btns:                      # 全列在小地图高度带内（不冒出不缩进）
            self.assertGreaterEqual(b.yb, MARGIN - 1e-9)
            self.assertLessEqual(b.yt, MARGIN + 150 + 1e-9)

    def test_group_bar_disjoint_from_fm_and_order_grid(self):
        # 既有互斥维持（TestFmPanelClearsGroupBarAndOrderGrid 同族——新位右界
        # 238+26=264 < fm x0=320、< 命令格 x0）
        win = _duck_win()
        layout_group_bar(win)
        fx0, fy0, fx1, fy1 = fm_panel_geom(win)
        for rows in range(1, 7):
            g = order_grid_rect(win, rows)
            for b in win._buttons:
                if b.key.startswith("grp:"):
                    self.assertFalse(_overlap(b, (fx0, fy0, fx1, fy1)))
                    self.assertFalse(_overlap(b, g), "rows=%d" % rows)


class TestOrderPanelEmptyFootprint(_HeadlessRulerTestCase):
    """〔问题5·2026-10-15〕命令面板空选区常驻（B3 勘注——原「空选区不绘命令格
    （basics.txt:62）」推读被用户拍板推翻）：order_panel_rect 空态=满配 6×8
    足印；draw_order_panel 空态绘底板＋提示文案（三态过滤行为保留——空选区仍
    无钮可下达）。"""

    def test_order_panel_rect_empty_is_full_footprint(self):
        win = _duck_win()                       # 空选区（fsm.selected/air 均 ()
        from sovs.ui.hud_bottom import order_panel_rect
        self.assertEqual(order_panel_rect(win), order_grid_rect(win, 6, 8))
        # 有行选区=实足印（与现状公式一致）
        units = [{"id": 1, "team": 0, "category": 1, "name": "步"}]
        win2 = _duck_win(frame=_duck_frame(units=units))
        win2.fsm.selected = (1,)
        rows = __import__("sovs.ui.hud_bottom", fromlist=["_battle_rows"]) \
            ._battle_rows(win2)
        self.assertTrue(rows)
        self.assertEqual(order_panel_rect(win2),
                         order_grid_rect(win2, len(rows),
                                         max(len(r) for r in rows)))

    def test_draw_order_panel_empty_draws_hint_only(self):
        # 空选区绘制：底板+描边+居中提示文案；无命令钮（三态过滤保留）
        import unittest.mock as mock
        from sovs.ui.hud_bottom import draw_order_panel, order_panel_rect
        win = _duck_win()
        with mock.patch("arcade.draw_lrbt_rectangle_filled") as rf, \
                mock.patch("arcade.draw_lrbt_rectangle_outline") as ro, \
                mock.patch("arcade.draw_text") as dt:
            draw_order_panel(win)
        rect = order_panel_rect(win)
        self.assertEqual(rf.call_count, 1)
        # arcade 参数序 (x0,x1,y0,y1) ← rect (x0,y0,x1,y1)
        self.assertEqual(rf.call_args.args[:4], (rect[0], rect[2], rect[1], rect[3]))
        self.assertEqual(ro.call_count, 1)
        self.assertTrue(dt.called)                        # 提示文案在册
        texts = [c.args[0] for c in dt.call_args_list if c.args]
        self.assertTrue(any("点选单位" in str(t) for t in texts), texts)
        self.assertFalse([b for b in win._buttons
                          if not (b.key.startswith(("railtab_", "air:", "buy:")))])

    def test_order_panel_footprint_disjoint_from_selection_panel(self):
        # 空态足印 × 底中选中卡互斥（满配 x0=906 > 面板 x1=748）
        from sovs.ui.hud_bottom import order_panel_rect
        win = _duck_win()
        units = [{"id": 1, "team": 0, "category": 1, "name": "步"}]
        win.fsm.selected = (1,)
        self.assertFalse(_overlap(panel_geom(win), order_panel_rect(win)))


class TestFmPanelClearsGroupBarAndOrderGrid(_HeadlessRulerTestCase):
    """②fm 参数条让开编组列与右下命令格（修前 ∩ grp:7/8/9＋12px 微叠）。"""

    def test_fm_panel_disjoint_from_group_slots(self):
        win = _duck_win()
        layout_group_bar(win)
        gx0, gy0, gx1, gy1 = fm_panel_geom(win)
        for b in win._buttons:
            if b.key.startswith("grp:"):
                self.assertFalse(_overlap(b, (gx0, gy0, gx1, gy1)),
                                 "%s ∩ fm %s" % (b.key, _rect(b)))

    def test_fm_panel_disjoint_from_order_grid_all_row_counts(self):
        win = _duck_win()
        fx0, fy0, fx1, fy1 = fm_panel_geom(win)
        for rows in range(1, 7):                    # 1..6 行（满配=航空+四常+补给）
            g = order_grid_rect(win, rows)
            self.assertFalse(_overlap((fx0, fy0, fx1, fy1), g),
                             "rows=%d fm=%s grid=%s" % (rows, (fx0, fy0, fx1, fy1), g))

    def test_creep_full_config_buttons_inside_panel(self):
        """③CREEP 满配（form=CREEP 三速档）按钮串右缘≤x0+912 且⊆面板矩形。"""
        win = _duck_win()
        win.fsm.arm_order("fire_mission")
        win.fsm.set_fm_param("form", "CREEP")
        layout_fm_panel(win)
        fm_btns = [b for b in win._buttons if b.key.startswith("fm_")]
        self.assertGreaterEqual(len(fm_btns), 14)   # 3形+3弹+3档+2齐射+3徐进
        x0, y0, x1, y1 = fm_panel_geom(win)
        for b in fm_btns:
            self.assertLessEqual(b.x1, x0 + 912 + 1e-9,
                                 "%s 右缘 %f 超 x0+912" % (b.key, b.x1))
            self.assertGreaterEqual(b.x0, x0 - 1e-9)
            self.assertGreaterEqual(b.yb, y0 - 1e-9)
            self.assertLessEqual(b.yt, y1 + 1e-9)


class TestFitTextFiveContainers(_HeadlessRulerTestCase):
    """⑤五处截宽点：fit_text 后实测宽 ≤ 容器宽（超长卡名样例——「…」收尾）。"""

    def test_five_fit_points_width_bounded(self):
        long_name = "第3近卫机械化军直属独立重火箭炮营（1944年编制·满编）"
        cases = (
            ("呼援轨标签", "%s（在空2）" % long_name, RAIL_W - 8, 12),
            ("部署卡槽标签", "%s ×2（空投）" % long_name, LEFT_W - 2 * MARGIN - 8, 12),
            ("编辑器汇总行", "· %s ×3（270分）" % long_name, 226, 11),
            ("config 卡组钮", "卡组：%s" % long_name, 200 - 8, 12),
            ("trail 标签", "fire_mission/CREEP" + long_name, 140, 9),
        )
        for where, label, w, size in cases:
            with self.subTest(where=where):
                fitted = fit_text(label, w, size)
                self.assertLessEqual(self.width(fitted, size), w,
                                     "%s 截宽后 %f > %f" % (where, self.width(fitted, size), w))
                self.assertTrue(fitted.endswith("…"))

    def test_deploy_slot_label_fitted_in_layout(self):
        """布局面实证：deploy 卡槽按钮 label 经 fit_text（超长名「…」收尾）。
        2026-10-14 呼援轨页签块：部署页卡槽=同款六页签轨（RAIL_W 宽）。"""
        deck = [{"template_id": 501, "name": "超长卡名" * 12, "copies_left": 2,
                 "airdrop": False}]
        win = _duck_win(page="deploy", frame=_duck_frame(deck=deck))
        layout_deploy_panel(win)
        btn = next(b for b in win._buttons if b.key.startswith("buy:"))
        self.assertTrue(btn.label.endswith("…"))
        self.assertLessEqual(self.width(btn.label, 12), RAIL_W - 8)

    def test_rail_label_fitted_in_layout(self):
        roster = [{"key": "call_bomber", "label": "呼IL-2M强击机×2弹" + "（长后缀）" * 8,
                   "affordable": True}]
        win = _duck_win(frame=_duck_frame(), roster=roster)
        win._rail_tab = "AIR"           # 2026-10-14 页签块：空援卡在 AIR 页签
        layout_air_rail(win)
        btn = next(b for b in win._buttons if b.key.startswith("air:"))
        self.assertLessEqual(self.width(btn.label, 12), RAIL_W - 8)


class TestAirCardOrderGridMutualExclusion(_HeadlessRulerTestCase):
    """空中选中卡（右下）×右下命令格互斥（2026-10-14 空中卡迁右下——卡底=
    命令格顶+12，严格在格上方）。2026-10-15：帧补飞机条目使 AIR 行真实在册
    （空帧=命令格退化，锚位语义由 TestAirCardThreeStates 的贴角锚覆盖）。"""

    def test_air_card_never_overlaps_order_grid(self):
        from sovs.ui.selection_panel import air_panel_geom
        air = [{"id": 101, "team": 0, "name": "Il-2M", "state": "patrol",
                "alt_tier": "mid", "hp": 10, "hp_max": 10, "ammo": {"BOMB": 2},
                "engage_air": False, "fuel_pct": 100, "afterburner": False,
                "template_id": 3, "pos_cm": [0, 0]}]
        win = _duck_win(frame={"players": [{"deck": []}], "units": [],
                        "aircraft": air, "view": 0, "lasers": []})
        win.fsm.selected_air = (101,)
        layout_battle_buttons(win)
        layout_selection_panel(win)
        card = air_panel_geom(win)
        rows = [r for r in
                __import__("sovs.ui.hud_bottom", fromlist=["_battle_rows"])
                ._battle_rows(win)]
        self.assertTrue(rows)                         # AIR 行在册（前提锚）
        cols = max((len(r) for r in rows), default=0)
        grid = order_grid_rect(win, len(rows), cols)
        overlap = (card[0] < grid[2] and card[2] > grid[0]
                   and card[1] < grid[3] and card[3] > grid[1])
        self.assertFalse(overlap, "空中卡 %s ∩ 命令格 %s" % (card, grid))
        # BA 复刻轮：三件套堆叠——摘要行=格顶+12、状态主卡=摘要行顶+12
        from sovs.ui.selection_panel import panel_geom
        self.assertAlmostEqual(panel_geom(win)[1], grid[3] + 12, places=6)
        self.assertAlmostEqual(card[1], panel_geom(win)[3] + 12, places=6)


class TestRailTabPhaseVisibility(_HeadlessRulerTestCase):
    """两处修正·其一（2026-10-15）：呼援轨页签按阶段与可放置性收敛——deploy 无
    AIR／无可放置卡的类别整签不渲染（余量尽/纯空降/无旋翼机）／残留页签回退。"""

    def test_deploy_hides_air_tab_and_cards(self):
        roster = [{"key": "call_bomber", "label": "呼IL-2M", "affordable": True}]
        win = _duck_win(page="deploy", frame=_duck_frame(deck=_deck_slots(3)),
                        roster=roster)
        win._rail_tab = "AIR"                    # 上局实战残留——须回退
        layout_deploy_panel(win)
        tabs = {b.key for b in win._buttons if b.key.startswith("railtab_")}
        self.assertNotIn("railtab_AIR", tabs)    # 部署期无航空类别（阶段差分）
        self.assertNotIn("railtab_HEL", tabs)    # 无旋翼机数据不渲染
        self.assertIn("railtab_ALL", tabs)       # 地面类别照常
        self.assertFalse([b for b in win._buttons if b.key.startswith("air:")])
        from sovs.ui.hud_bottom import rail_tab_of
        self.assertEqual(rail_tab_of(win), "ALL")

    def test_battle_shows_air_tab_when_roster(self):
        roster = [{"key": "call_bomber", "label": "呼IL-2M", "affordable": True}]
        win = _duck_win(frame=_duck_frame(deck=_deck_slots(3)), roster=roster)
        layout_air_rail(win)
        tabs = {b.key for b in win._buttons if b.key.startswith("railtab_")}
        self.assertIn("railtab_AIR", tabs)
        self.assertTrue([b for b in win._buttons if b.key.startswith("air:")])
        self.assertNotIn("railtab_HEL", tabs)

    def test_battle_empty_roster_hides_air(self):
        win = _duck_win(frame=_duck_frame(deck=_deck_slots(3)))
        layout_air_rail(win)
        self.assertEqual({b.key for b in win._buttons
                          if b.key.startswith("railtab_")},
                         {"railtab_ALL", "railtab_REC", "railtab_INF",
                          "railtab_VEH", "railtab_SUP"})  # duck 兜底=地面全类别

    def test_category_without_placeable_cards_hidden(self):
        meta = {301: {"category": 1, "supply": False}}       # 仅 1 张步兵卡
        deck = [{"template_id": 301, "name": "步兵班", "copies_left": 2,
                 "airdrop": False}]
        win = _duck_win(frame=_duck_frame(deck=deck))
        win.session = SimpleNamespace(air_roster=lambda: [],
                                      deck_slot_meta=lambda: meta)
        layout_air_rail(win)
        self.assertEqual({b.key for b in win._buttons
                          if b.key.startswith("railtab_")},
                         {"railtab_ALL", "railtab_INF"})
        self.assertEqual(len([b for b in win._buttons
                              if b.key.startswith("buy:")]), 1)

    def test_exhausted_and_airdrop_only_categories_hidden(self):
        # 余量尽（×0）与纯空降类别=无法放置→整签不出现；ALL 亦不混入其 ×0 卡
        meta = {301: {"category": 1, "supply": False},
                302: {"category": 0, "supply": False},
                303: {"category": 4, "supply": True}}
        deck = [{"template_id": 301, "name": "步兵班", "copies_left": 0,
                 "airdrop": False},
                {"template_id": 302, "name": "侦察队", "copies_left": 1,
                 "airdrop": True},
                {"template_id": 303, "name": "补给卡车", "copies_left": 0,
                 "airdrop": False}]
        win = _duck_win(frame=_duck_frame(deck=deck))
        win.session = SimpleNamespace(air_roster=lambda: [],
                                      deck_slot_meta=lambda: meta)
        layout_air_rail(win)
        self.assertEqual({b.key for b in win._buttons
                          if b.key.startswith("railtab_")}, set())
        self.assertFalse([b for b in win._buttons if b.key.startswith("buy:")])

    def test_hidden_category_cards_not_in_all_tab(self):
        # 混合余量：INF 有可放置卡→签在；REC 仅 ×0 卡→签不在且 ALL 不列其卡
        meta = {301: {"category": 1, "supply": False},
                302: {"category": 0, "supply": False}}
        deck = [{"template_id": 301, "name": "步兵班", "copies_left": 2,
                 "airdrop": False},
                {"template_id": 302, "name": "侦察队", "copies_left": 0,
                 "airdrop": False}]
        win = _duck_win(frame=_duck_frame(deck=deck))
        win.session = SimpleNamespace(air_roster=lambda: [],
                                      deck_slot_meta=lambda: meta)
        layout_air_rail(win)                       # 缺省 ALL
        buys = [b.key for b in win._buttons if b.key.startswith("buy:")]
        self.assertEqual(len(buys), 1)             # REC ×0 卡不进 ALL


class TestAirCardThreeStates(_HeadlessRulerTestCase):
    """两处修正·其二（2026-10-15）：对战页空中单位信息三态统一右下命令界面
    上方——无选区在空列表（贴右下角）/纯空中/混合选区（地面左卡＋空中右卡）。"""

    @staticmethod
    def _frame_with_air(*, units=(), aircraft=()):
        return {"players": [{"deck": []}], "units": list(units),
                "aircraft": list(aircraft), "view": 0, "lasers": []}

    @staticmethod
    def _air(**kw):
        d = {"id": 9, "team": 0, "name": "Il-2M", "state": "patrol",
             "alt_tier": "mid", "hp": 10, "hp_max": 10, "ammo": {"BOMB": 2},
             "engage_air": False, "fuel_pct": 100, "afterburner": False,
             "template_id": 3, "pos_cm": [0, 0]}
        d.update(kw)
        return d

    def test_no_selection_lists_inflight_at_corner(self):
        from sovs.ui.selection_panel import air_panel_geom
        win = _duck_win(frame=self._frame_with_air(
            aircraft=[self._air(), self._air(id=11, team=1)]))
        layout_battle_buttons(win)
        layout_selection_panel(win)
        rows_btns = [b for b in win._buttons if b.key.startswith("airsel:")]
        self.assertEqual([b.key for b in rows_btns], ["airsel:9"])  # 仅己方机
        card = air_panel_geom(win)
        for b in rows_btns:                    # 行落在空中卡区内
            self.assertTrue(card[0] - 1 <= b.x0 and b.x1 <= card[2] + 1
                            and card[1] - 1 <= b.yb and b.yt <= card[3] + 1)
        # 〔BA 复刻轮 2026-10-15 勘锚：空选区命令面板常驻满配足印（B3 勘注）
        # ——状态主卡底=摘要行顶+12（摘要行底=足印顶+12），恒不跳位。〕
        from sovs.ui.hud_bottom import order_grid_rect, order_panel_rect
        from sovs.ui.selection_panel import panel_geom
        self.assertEqual(order_panel_rect(win), order_grid_rect(win, 6, 8))
        self.assertAlmostEqual(panel_geom(win)[1],
                               order_grid_rect(win, 6, 8)[3] + 12, places=6)
        self.assertAlmostEqual(card[1], panel_geom(win)[3] + 12, places=6)
        self.assertFalse([b for b in win._buttons if b.key.startswith("sel:")])

    def test_mixed_selection_strip_below_air_card(self):
        from sovs.ui.selection_panel import air_panel_geom, panel_geom
        units = [{"id": 1, "team": 0, "category": 1, "name": "步"},
                 {"id": 2, "team": 0, "category": 1, "name": "步"}]
        win = _duck_win(frame=self._frame_with_air(
            units=units, aircraft=[self._air()]))
        win.fsm.selected = (1, 2)
        win.fsm.selected_air = (9,)
        layout_battle_buttons(win)
        layout_selection_panel(win)
        sel_btns = [b for b in win._buttons if b.key.startswith("sel:")]
        air_btns = [b for b in win._buttons if b.key.startswith("airsel:")]
        self.assertEqual(len(sel_btns), 2)
        self.assertEqual(len(air_btns), 1)
        card = air_panel_geom(win)
        strip = panel_geom(win)
        for b in sel_btns:            # 地面小卡在摘要行带内（状态主卡下方）
            self.assertLessEqual(b.yt, strip[3] + 1)
        for b in air_btns:            # 空中行在状态主卡内（摘要行上方）
            self.assertGreaterEqual(b.yb, card[1] - 1)

    def test_ground_only_selection_no_air_card(self):
        units = [{"id": 1, "team": 0, "category": 1, "name": "步"}]
        win = _duck_win(frame=self._frame_with_air(units=units))
        win.fsm.selected = (1,)
        layout_battle_buttons(win)
        layout_selection_panel(win)
        self.assertFalse([b for b in win._buttons if b.key.startswith("airsel:")])
        self.assertTrue([b for b in win._buttons if b.key.startswith("sel:")])

    def test_deploy_page_never_draws_air_card(self):
        win = _duck_win(page="deploy",
                        frame=self._frame_with_air(aircraft=[self._air()]))
        layout_selection_panel(win)
        self.assertFalse([b for b in win._buttons if b.key.startswith("airsel:")])


if __name__ == "__main__":
    unittest.main()
