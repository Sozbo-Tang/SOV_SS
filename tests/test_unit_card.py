"""FE-05 F3 单位详细卡测试：几何 320×236/12px 缝/与集群面板不相交/武器表
+N 截断/互斥裁决（鸭子窗——test_hud_geometry 同款无头面）。"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.ui.hud_bottom import order_panel_rect                       # noqa: E402
from sovs.ui.selection_panel import panel_geom                        # noqa: E402
from sovs.ui.shell_fsm import ShellFsm                                # noqa: E402
from sovs.ui.unit_card import (_weapon_rows, CARD_W, _COL,            # noqa: E402
                               col_spans, hp_bar_rect, hp_text_rect,
                               unit_card_active, unit_card_geom)

_W, _H = 1280, 800


def _duck_win(*, selected=(7,), aircraft=()):
    fsm = ShellFsm()
    fsm.page = "battle"
    fsm.selected = list(selected)
    return SimpleNamespace(width=_W, height=_H,
                           frame={"players": [{"deck": []}],
                                  "units": [], "aircraft": list(aircraft),
                                  "view": 0, "lasers": []},
                           fsm=fsm,
                           session=SimpleNamespace(air_roster=lambda: []),
                           _buttons=[])


class TestUnitCardGeometry(unittest.TestCase):

    def test_geometry_320x236_gap12_right_aligned(self):
        win = _duck_win()
        x0, y0, x1, y1 = unit_card_geom(win)
        self.assertEqual(x1 - x0, CARD_W)                # R1：宽 340（原 320）
        self.assertEqual(CARD_W, 340)
        self.assertAlmostEqual(y1 - y0, 236)             # 高 236
        self.assertAlmostEqual(x1, order_panel_rect(win)[2])   # 右缘对齐格右
        self.assertAlmostEqual(y0, panel_geom(win)[3] + 12)    # 摘要行顶+12

    def test_last_column_fits_card_width(self):
        """R2 升级（全文可容纳——非 fit 后测宽的恒真式）：末列 span 下
        "SMOKE" 完整显示、不出现「…」；列锚+列宽不越 CARD_W-8。无头量尺
        （ASCII 单宽/CJK 双宽——test_hud_geometry 同款；真字体证明在
        tests/test_skin.py test_e 的 GL 类）。"""
        import unittest.mock as mock
        from sovs.ui import hud_top
        from sovs.ui.hud_top import fit_text

        def est(text, size):
            return size * sum(2 if ord(ch) > 0x2E7F else 1 for ch in str(text))

        with mock.patch.object(hud_top, "text_width", est):
            spans = col_spans()
            self.assertEqual(len(spans), 5)
            self.assertLessEqual(_COL[4] + spans[4], CARD_W - 8)
            self.assertEqual(fit_text("SMOKE", spans[4] - 4, 10), "SMOKE",
                             "末列 span=%r 容不下 SMOKE 全文" % spans[4])
            self.assertLessEqual(est("SMOKE", 10), spans[4] - 4)

    def test_hp_text_disjoint_from_bar(self):
        """R1：HP 文本带与血条带零重叠（自 y1 向下偏移矩形）。"""
        bar = hp_bar_rect()
        text = hp_text_rect()
        self.assertLessEqual(bar[3], text[1])            # bar[36..42] text[46..56]
        self.assertGreater(text[1], bar[3])

    def test_disjoint_from_summary_and_grid(self):
        win = _duck_win()
        cx0, cy0, cx1, cy1 = unit_card_geom(win)
        sx0, sy0, sx1, sy1 = panel_geom(win)              # 摘要行
        self.assertGreaterEqual(cy0, sy1)                 # 卡在摘要行上方
        gx0, gy0, gx1, gy1 = order_panel_rect(win)        # 命令格
        self.assertGreaterEqual(cy0, gy1)
        self.assertEqual(cx1, gx1)
        self.assertLessEqual(cy1, _H - 56 - 8)            # 不溢顶栏

    def test_mutual_exclusion_with_air_card(self):
        win = _duck_win()
        self.assertTrue(unit_card_active(win))            # 纯地面选区=绘
        air_win = _duck_win(selected=(),                  # 空选区+在空机=在空
                            aircraft=[{"id": 1, "team": 0}])   # 列表卡占位
        self.assertFalse(unit_card_active(air_win))
        sel_air = _duck_win(selected=())                  # 纯空中选区→不绘
        sel_air.fsm.selected_air = [1]
        self.assertFalse(unit_card_active(sel_air))
        none_win = _duck_win(selected=())
        self.assertFalse(unit_card_active(none_win))      # 无选区不绘

    def test_weapon_rows_truncation_marker(self):
        data = {"elements": [
            {"weapons": [
                {"name": "w%d" % i, "ammo_left": 1, "ammo_base": 2,
                 "max_range_cm": 30000, "pen_min": 0, "pen_max": 0,
                 "damage_type": "he", "reload_ticks": 10}
                for i in range(6)]}]}
        rows = _weapon_rows(data)
        self.assertEqual(len(rows), 6)                    # 平铺全量
        # 绘制面截断到 4 行＋「+2」（绘制经 _MAX_WEAPON_ROWS 常量裁决）
        from sovs.ui.unit_card import _MAX_WEAPON_ROWS
        self.assertEqual(len(rows[:_MAX_WEAPON_ROWS]), 4)
        self.assertEqual(len(rows) - _MAX_WEAPON_ROWS, 2)

    def test_weapon_rows_pen_formats(self):
        def _w(pmin, pmax):
            return {"name": "x", "ammo_left": 0, "ammo_base": 0,
                    "max_range_cm": 0, "pen_min": pmin, "pen_max": pmax,
                    "damage_type": "ke", "reload_ticks": 0}
        rows = _weapon_rows({"elements": [
            {"weapons": [_w(0, 0), _w(50, 50), _w(40, 90)]}]})
        self.assertEqual([r[3] for r in rows], ["-", "50", "40~90"])
        self.assertEqual([r[4] for r in rows], ["KE", "KE", "KE"])


if __name__ == "__main__":
    unittest.main()
