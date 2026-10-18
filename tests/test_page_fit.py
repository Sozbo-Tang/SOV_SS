"""FE-05 R4 页面自适应测试：scale 纯算术 / to_design 往返与恒等 / 1600 四页
存在尺寸 / 四页内容变换对应（1280 设计坐标 vs 1600 屏幕——比「包围盒中心
贴窗口心」更严：菜单/设置为左列布局，内容包围盒心在设计画布内本就不居中，
恒等偏移在两分辨率下必须一致）。"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import arcade                                    # noqa: F401（探针）
    from tests._gl_probe import gl_window_available
    HAS_GL_WINDOW = gl_window_available()
except Exception:                                    # noqa: BLE001
    HAS_GL_WINDOW = False

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BG = (26, 30, 26)


def _duck(w, h):
    return SimpleNamespace(width=w, height=h)


class TestScaleMath(unittest.TestCase):
    """a) scale 纯算术（无 GL）。"""

    def test_scale_table(self):
        from sovs.ui import page_fit
        self.assertAlmostEqual(page_fit.scale(_duck(1280, 800)), 1.0)
        self.assertAlmostEqual(page_fit.scale(_duck(1600, 900)), 1.125)
        # 规格表写 1920×1080→1.5，但其 min 公式（保等比不拉伸）给
        # min(1.5, 1080/800=1.35)=1.35——公式为权威（1.35 亦居中无变形）
        self.assertAlmostEqual(page_fit.scale(_duck(1920, 1080)), 1.35)

    def test_scale_clamped(self):
        from sovs.ui import page_fit
        self.assertAlmostEqual(page_fit.scale(_duck(800, 600)), 0.625)  # R4.1：0.5 下限下不再钳
        self.assertAlmostEqual(page_fit.scale(_duck(640, 400)), 0.5)    # 下钳
        self.assertAlmostEqual(page_fit.scale(_duck(4096, 2160)), 2.0)  # 上钳

    def test_content_rect_inside_window_all_sizes(self):
        """R4.1：五档窗口下设计画布完全落窗内＋宽高比恒 1.6（等比锁）。"""
        from sovs.ui import page_fit
        for w, h in ((800, 600), (960, 600), (1024, 768), (1600, 900),
                     (1920, 1080)):
            x0, y0, x1, y1 = page_fit.content_rect(_duck(w, h))
            self.assertGreaterEqual(x0, 0, (w, h))
            self.assertGreaterEqual(y0, 0, (w, h))
            self.assertLessEqual(x1, w, (w, h))
            self.assertLessEqual(y1, h, (w, h))
            self.assertAlmostEqual((x1 - x0) / (y1 - y0),
                                   page_fit.DESIGN_W / page_fit.DESIGN_H,
                                   places=6, msg=(w, h))

    def test_aspect_ratio_lock(self):
        """R4.1 等比锁：scale=min(w/1280,h/800)（非等比拉伸禁止——任何
        「拉伸填满」改法使 content_rect 宽高比≠1.6 即红）。"""
        import math
        from sovs.ui import page_fit
        for w, h in ((1280, 800), (1600, 900), (1920, 1080), (960, 600),
                     (1440, 1000)):
            expect = min(w / 1280, h / 800)
            if 0.5 <= expect <= 2.0:
                self.assertAlmostEqual(page_fit.scale(_duck(w, h)), expect,
                                       msg=(w, h))
        self.assertAlmostEqual(page_fit.scale(_duck(1920, 1080)),
                               min(1920 / 1280, 1080 / 800))    # =1.35 钳位内
        ratios = [(lambda r: r[2] - r[0])(page_fit.content_rect(_duck(w, h)))
                  / ((lambda r: r[3] - r[1])(page_fit.content_rect(_duck(w, h))))
                  for w, h in ((960, 600), (1600, 900), (1920, 1080))]
        for r in ratios:
            self.assertTrue(math.isclose(r, 1.6, rel_tol=1e-6), r)

    def test_content_rect_geometry(self):
        from sovs.ui import page_fit
        x0, y0, x1, y1 = page_fit.content_rect(_duck(1600, 900))
        self.assertAlmostEqual(x1 - x0, 1280 * 1.125)                  # 1440
        self.assertAlmostEqual(y1 - y0, 800 * 1.125)                   # 900
        self.assertAlmostEqual((x0 + x1) / 2, 800)                     # 居中
        self.assertAlmostEqual((y0 + y1) / 2, 450)


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestCameraMath(unittest.TestCase):
    """b/c) to_design 恒等与往返（真 Camera2D）。"""

    @classmethod
    def setUpClass(cls):
        cls.win1280 = arcade.Window(1280, 800, "pf1280", visible=False)
        cls.win1600 = arcade.Window(1600, 900, "pf1600", visible=False)

    @classmethod
    def tearDownClass(cls):
        cls.win1280.close()
        cls.win1600.close()

    def test_identity_at_design_size(self):
        from sovs.ui import page_fit
        for x, y in ((0, 0), (1280, 800), (640, 400), (10, 790)):
            dx, dy = page_fit.to_design(self.win1280, x, y)
            self.assertAlmostEqual(dx, x, delta=0.5, msg=(x, y))
            self.assertAlmostEqual(dy, y, delta=0.5, msg=(x, y))

    def test_center_maps_to_design_center(self):
        from sovs.ui import page_fit
        dx, dy = page_fit.to_design(self.win1600, 800, 450)
        self.assertAlmostEqual(dx, 640, delta=0.5)
        self.assertAlmostEqual(dy, 400, delta=0.5)

    def test_roundtrip_corners(self):
        from sovs.ui import page_fit
        cam = page_fit.camera(self.win1600)
        for sx, sy in ((0, 0), (1600, 900), (100, 300), (1500, 700)):
            dx, dy = page_fit.to_design(self.win1600, sx, sy)
            px, py = cam.project((dx, dy))
            self.assertAlmostEqual(px, sx, delta=0.5, msg=(sx, sy))
            self.assertAlmostEqual(py, sy, delta=0.5, msg=(sx, sy))


def _bbox_center(path):
    from PIL import Image
    img = Image.open(path).convert("RGB")
    px = img.load()
    xs, ys = [], []
    for y in range(0, img.height, 2):
        for x in range(0, img.width, 2):
            if px[x, y] != _BG:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (sum(xs) / len(xs), sum(ys) / len(xs))


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestFourPagesAt1600(unittest.TestCase):
    """d/e) 1600 四页快照存在非空尺寸＋内容变换对应（背景 patch 掉后非底色
    包围盒中心：1600 实测 vs 由 1280 设计坐标经 content_rect 变换的期望——
    偏差 ≤2px 即相机缩放居中正确；菜单左列布局的原始窗口心偏差属设计画布
    内布局，两分辨率等量呈现（汇报实测值）。"""

    PAGES = ("menu", "config", "deck_edit", "settings")

    @classmethod
    def setUpClass(cls):
        import tempfile
        from unittest import mock
        from sovs.app.session import SkirmishSession
        from sovs.ui.shell_window import ShellWindow
        from sovs.ui import (deck_editor_page, menu_page,  # noqa: E402
                             settings_page)
        cls.tmp = tempfile.mkdtemp()
        cls.session = SkirmishSession(seed=42)
        patches = [mock.patch.object(menu_page, "draw_menu_background",
                                     lambda win: None),
                   mock.patch.object(deck_editor_page, "draw_config_background",
                                     lambda win: None),
                   mock.patch.object(deck_editor_page, "draw_deck_background",
                                     lambda win: None),
                   mock.patch.object(settings_page, "draw_settings_background",
                                     lambda win: None)]
        for p in patches:
            p.start()
        cls._patches = patches
        cls.shots = {}
        for tag, (w, h) in (("d1280", (1280, 800)), ("d1600", (1600, 900))):
            win = ShellWindow(cls.session, visible=False, width=w, height=h)
            cls._render_pages(win, os.path.join(cls.tmp, tag))
            win.close()
        for p in patches:
            p.stop()

    @classmethod
    def _render_pages(cls, win, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        # menu
        win.fsm.open_menu()
        win._layout_buttons()
        win.snapshot(os.path.join(out_dir, "menu.png"))
        win.fsm.open_config()
        win._layout_buttons()
        win.snapshot(os.path.join(out_dir, "config.png"))
        # deck_edit（catalog 装填与 screenshot 同口径）
        ed = cls.session.deck_editor
        win._deck_catalog = ed.catalog()
        win.fsm.open_deck_edit(
            {"deck_key": cls.session.human_deck, "faction": "SOVIET",
             "cards": ed.load_deck(cls.session.human_deck)["cards"],
             "tab": "INFANTRY", "errors": []})
        win._layout_buttons()
        win.snapshot(os.path.join(out_dir, "deck_edit.png"))
        win.fsm.close_deck_edit()
        from sovs.ui.settings_page import open_settings
        win._layout_buttons()
        open_settings(win)
        win.snapshot(os.path.join(out_dir, "settings.png"))
        from sovs.ui.settings_page import close_settings
        close_settings(win)

    def test_d_four_pages_exist_nonempty_1600x900(self):
        from PIL import Image
        for name in self.PAGES:
            path = os.path.join(self.tmp, "d1600", name + ".png")
            self.assertTrue(os.path.isfile(path), name)
            self.assertGreater(os.path.getsize(path), 0, name)
            self.assertEqual(Image.open(path).size, (1600, 900), name)

    def test_e_content_transform_correspondence(self):
        from sovs.ui import page_fit
        for name in self.PAGES:
            c1280 = _bbox_center(os.path.join(self.tmp, "d1280",
                                              name + ".png"))
            c1600 = _bbox_center(os.path.join(self.tmp, "d1600",
                                              name + ".png"))
            self.assertIsNotNone(c1280, name)
            s = 1.125
            ex = 800 + (c1280[0] - 640) * s  # 期望：content_rect 心+设计偏移×s
            ey = 450 + (c1280[1] - 400) * s
            # 容差 4px：包围盒质心按 2px 步采样＋两窗光栅化量化（实测最大
            # 偏差 2.08px——4px 为量测口径，仍严于规格 12px 档）
            self.assertLessEqual(abs(c1600[0] - ex), 4.0,
                                 "%s x: %r vs %r" % (name, c1600[0], ex))
            self.assertLessEqual(abs(c1600[1] - ey), 4.0,
                                 "%s y: %r vs %r" % (name, c1600[1], ey))


if __name__ == "__main__":
    unittest.main()
