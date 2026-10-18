"""FE-05 F2 铭牌测试：三档缩放开关 / 角标优先级截断 / 五边形下尖 / 缺字段
不抛 / 宽度不随 hp 变 / GL 绘制烟测。几何面=nameplate_geom 纯函数直断言。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import arcade                                    # noqa: F401（探针）
    from tests._gl_probe import gl_window_available
    HAS_GL_WINDOW = gl_window_available()
except Exception:                                    # noqa: BLE001
    HAS_GL_WINDOW = False

_FULL = {"hp": 8, "hp_max": 10, "team": 0, "selected": False,
         "suppressed": True, "stance": "hold_fire", "radar_on": True,
         "rtb": True, "garrisoned": True, "towed": True}


class TestNameplateGeom(unittest.TestCase):

    def test_zoom_tiers(self):
        """R2 分档（2026-10-17 拍板翻新——对齐默认相机量尺 fit≈0.006）：
        <0.0040 只血条；0.0040~0.0050 铭牌+血条无人数；≥0.0050 全量。"""
        from sovs.ui.nameplate import nameplate_geom
        g_far = nameplate_geom(100, 200, 0.002, _FULL)     # <0.0040 只血条
        self.assertIsNone(g_far["poly"])
        self.assertIsNotNone(g_far["hp_rect"])
        self.assertIsNone(g_far["count_pos"])
        self.assertEqual(g_far["badges"], [])
        g_mid = nameplate_geom(100, 200, 0.0045, _FULL)     # 0.0040~0.0050 无人数
        self.assertIsNotNone(g_mid["poly"])
        self.assertIsNotNone(g_mid["hp_rect"])
        self.assertIsNone(g_mid["count_pos"])
        self.assertEqual(g_mid["badges"], [])               # 角标随全量档
        g_near = nameplate_geom(100, 200, 0.006, _FULL)     # ≥0.0050 全量（默认档）
        self.assertIsNotNone(g_near["poly"])
        self.assertIsNotNone(g_near["count_pos"])
        self.assertTrue(g_near["badges"])

    def test_default_camera_scale_shows_full_nameplate(self):
        """R2 主断言：默认视角（scene.fit_scale 实算）下铭牌全量在场。"""
        from types import SimpleNamespace
        from sovs.ui import scene
        from sovs.ui.nameplate import nameplate_geom
        win = SimpleNamespace(width=1280, height=800, fsm=SimpleNamespace(
            page="battle"),
            frame={"map_cm": [200000, 100000], "units": [], "aircraft": [],
                   "players": [], "view": 0})
        fit = scene.fit_scale(win)
        self.assertGreaterEqual(fit, 0.0050)                # 默认档 ≥ 全量线
        g = nameplate_geom(100, 200, fit, _FULL)
        self.assertIsNotNone(g["poly"], "默认视角铭牌缺——fit=%r" % fit)
        self.assertIsNotNone(g["count_pos"])
        self.assertTrue(g["badges"])

    def test_min_camera_scale_keeps_plate(self):
        """R2 下界：min_scale（fit×0.8）仍 ≥0.0040——缩小下限可见铭牌。"""
        from types import SimpleNamespace
        from sovs.ui import scene
        from sovs.ui.nameplate import nameplate_geom
        win = SimpleNamespace(width=1280, height=800, fsm=SimpleNamespace(
            page="battle"),
            frame={"map_cm": [200000, 100000], "units": [], "aircraft": [],
                   "players": [], "view": 0})
        low = scene.min_scale(win)
        self.assertGreaterEqual(low, 0.0040)
        g = nameplate_geom(100, 200, low, _FULL)
        self.assertIsNotNone(g["poly"], "min_scale=%r 下铭牌缺" % low)

    def test_below_floor_blood_bar_only(self):
        from sovs.ui.nameplate import nameplate_geom
        g = nameplate_geom(100, 200, 0.002, _FULL)
        self.assertIsNone(g["poly"])

    def test_count_only_for_infantry(self):
        """R3 1-1：人数只挂步兵——载具/火炮/防空/侦察车 count_pos=None；
        缺 category 按步兵（兼容口径）。"""
        from sovs.ui.nameplate import nameplate_geom
        inf = nameplate_geom(100, 200, 0.006,
                             dict(_FULL, hp=30, hp_max=30, category=1))
        self.assertIsNotNone(inf["count_pos"])
        veh = nameplate_geom(100, 200, 0.006,
                             dict(_FULL, hp=30, hp_max=30, category=2))
        self.assertIsNone(veh["count_pos"])
        for cat in (0, 2, 3, 4):                      # 侦察/装甲/火支/防空后勤
            self.assertIsNone(nameplate_geom(
                100, 200, 0.006, dict(_FULL, category=cat))["count_pos"])
        missing = nameplate_geom(100, 200, 0.006,
                                 {k: v for k, v in _FULL.items()
                                  if k != "category"})
        self.assertIsNotNone(missing["count_pos"])    # 缺 category=步兵

    def test_count_text_hp_slash_hpmax(self):
        """R3 1-1：步兵人数文本=「30/30」（hp/hp_max）；载具不画数字。"""
        import unittest.mock as mock
        from sovs.ui import nameplate as np_mod
        with mock.patch.object(np_mod, "arcade") as arc:
            np_mod.draw_nameplate(100, 200, 0.006,
                                  dict(_FULL, hp=30, hp_max=30, category=1))
        texts = [c.args[0] for c in arc.draw_text.call_args_list]
        self.assertIn("30/30", texts)
        with mock.patch.object(np_mod, "arcade") as arc:
            np_mod.draw_nameplate(100, 200, 0.006,
                                  dict(_FULL, hp=30, hp_max=30, category=2))
        texts = [c.args[0] for c in arc.draw_text.call_args_list]
        self.assertFalse(any("/" in str(t) for t in texts))   # 载具无数字
        self.assertTrue(texts)                                 # 角标字母仍在

    def test_badges_priority_truncated_at_4(self):
        from sovs.ui.nameplate import nameplate_geom
        g = nameplate_geom(100, 200, 0.5, _FULL)           # 六标志全开
        self.assertEqual(len(g["badges"]), 4)              # 截断到 4
        letters = [b[0] for b in g["badges"]]
        self.assertEqual(letters, ["压", "禁", "雷", "R"])  # 优先序前四

    def test_pentagon_five_points_tip_down(self):
        from sovs.ui.nameplate import nameplate_geom
        g = nameplate_geom(100, 200, 0.5, _FULL)
        poly = g["poly"]
        self.assertEqual(len(poly), 5)
        ys = [p[1] for p in poly]
        tip = poly[3]
        self.assertEqual(min(ys), tip[1])                  # 下尖=最低点
        self.assertAlmostEqual(tip[0], 100.0)              # 尖在中央
        top = poly[0][1]
        self.assertAlmostEqual(top - min(ys), 12.0)        # 高 12
        self.assertAlmostEqual(poly[1][0] - poly[0][0], 44.0)  # 宽 44

    def test_missing_fields_no_throw(self):
        from sovs.ui.nameplate import nameplate_geom
        for state in ({}, None, {"hp": 3}):
            g = nameplate_geom(0, 0, 0.5, state)           # 不抛即过
            self.assertIsNotNone(g["hp_rect"])

    def test_width_independent_of_hp(self):
        from sovs.ui.nameplate import nameplate_geom
        a = nameplate_geom(100, 200, 0.5, dict(_FULL, hp=1))
        b = nameplate_geom(100, 200, 0.5, dict(_FULL, hp=10))
        self.assertEqual(a["poly"], b["poly"])             # 五边形不随 hp 变
        self.assertEqual(a["hp_rect"], b["hp_rect"])      # 血条槽同宽 40


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestNameplateDrawing(unittest.TestCase):
    """绘制面烟测（真 GL 上下文——三档缩放各画一次不抛）。"""

    @classmethod
    def setUpClass(cls):
        cls.win = arcade.Window(240, 160, "test-nameplate", visible=False)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def test_draw_three_tiers_no_throw(self):
        from sovs.ui.nameplate import draw_nameplate
        self.win.switch_to()
        self.win.clear()
        for zoom in (0.05, 0.10, 0.5):
            draw_nameplate(120, 100, zoom, _FULL)
            draw_nameplate(120, 100, zoom, {})
        self.win.flip()


if __name__ == "__main__":
    unittest.main()
