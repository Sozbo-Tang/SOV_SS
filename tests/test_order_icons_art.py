"""FE-05 F4 命令图标贴图化测试：39 键全映射 / 缺图不抛（mock 面）/ AST 守卫
/ 命令格区域基线差分 ≥0.05（实渲染）。"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import arcade                                    # noqa: F401（探针）
    from tests._gl_probe import gl_window_available
    HAS_GL_WINDOW = gl_window_available()
except Exception:                                    # noqa: BLE001
    HAS_GL_WINDOW = False

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BASELINE = os.path.join(_ROOT, "out", "qa_fe05_baseline", "battle.png")


class TestOrderIconMapping(unittest.TestCase):

    def test_39_keys_all_mapped(self):
        from sovs.ui import assets
        from sovs.ui.order_icons import ICON_FUNCS
        self.assertEqual(len(ICON_FUNCS), 39)
        for key in ICON_FUNCS:
            self.assertIsNotNone(assets.order_tex(key), key)

    def test_tile_states_mapped(self):
        from sovs.ui import assets
        for name in ("cmd_tile", "cmd_tile_hover", "cmd_tile_armed",
                     "cmd_tile_disabled"):
            self.assertIsNotNone(assets.ui_tex(name), name)


class TestDrawOrderTileMocked(unittest.TestCase):
    """mock arcade/assets：贴图路径 32px；缺图回退矢量不抛。"""

    def _btn(self, key="attack", tone="normal"):
        from sovs.ui.hud_bottom import Btn
        return Btn(100, 200, 40, 40, key, "攻击(Q)", tone=tone)

    def test_texture_path_32px(self):
        import arcade as real_arcade
        from sovs.ui import order_icons
        with mock.patch.object(order_icons, "arcade") as arc, \
                mock.patch.object(order_icons.assets, "order_tex") as ot, \
                mock.patch.object(order_icons.assets, "ui_tex",
                                  return_value=None), \
                mock.patch.object(order_icons.assets, "draw_nine_patch") as np9:
            arc.XYWH.side_effect = real_arcade.XYWH   # 真矩形（宽高可断言）
            ot.return_value = mock.MagicMock()
            order_icons.draw_order_tile(self._btn(), armed=False, hovered=False)
        self.assertFalse(np9.called)                 # 无底砖=纯色路径
        rects = [c.args[1] for c in arc.draw_texture_rect.call_args_list
                 if len(c.args) >= 2 and hasattr(c.args[1], "width")]
        self.assertTrue(rects)
        self.assertIn((32, 32), [(r.width, r.height) for r in rects])

    def test_missing_icon_falls_back_no_throw(self):
        from sovs.ui import order_icons
        with mock.patch.object(order_icons, "arcade") as arc, \
                mock.patch.object(order_icons.assets, "order_tex",
                                  return_value=None), \
                mock.patch.object(order_icons.assets, "ui_tex",
                                  return_value=None):
            order_icons.draw_order_tile(self._btn(key="__nope"),
                                        armed=False, hovered=False)
            order_icons.draw_order_tile(self._btn(key="attack",
                                                  tone="disabled"),
                                        armed=True, hovered=True)
        self.assertFalse(arc.draw_texture_rect.called)   # 矢量回退零贴图

    def test_disabled_alpha_90_gray(self):
        from sovs.ui import order_icons
        with mock.patch.object(order_icons, "arcade") as arc, \
                mock.patch.object(order_icons.assets, "order_tex") as ot, \
                mock.patch.object(order_icons.assets, "ui_tex",
                                  return_value=None):
            ot.return_value = mock.MagicMock()
            order_icons.draw_order_tile(self._btn(tone="disabled"),
                                        armed=False, hovered=False)
        kw = arc.draw_texture_rect.call_args_list[-1].kwargs
        self.assertEqual(kw.get("alpha"), 90)

    def test_ast_no_sim_no_pil(self):
        src = open(os.path.join(_ROOT, "sovs", "ui", "order_icons.py"),
                   encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                tops = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                tops = {node.module.split(".")[0]}
            else:
                continue
            self.assertNotIn("PIL", tops)
            self.assertNotIn("sovs", tops)


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestOrderGridDiff(unittest.TestCase):
    """battle 页实渲染 vs F0 基线：命令格 (940,550,1270,790) diff ≥0.05。"""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(_BASELINE):
            raise unittest.SkipTest("基线图缺失：%s" % _BASELINE)
        from sovs.app.scripts import ScriptedPilot
        from sovs.app.session import SkirmishSession
        from sovs.ui.shell_window import ShellWindow
        cls.session = SkirmishSession(seed=42)
        cls.pilot = ScriptedPilot(cls.session)
        cls.win = ShellWindow(cls.session, visible=False)
        cls.win.fsm.start_deploy()
        while cls.session.world.tick < 2165:
            cls.pilot.step()
            cls.session.advance(1)
        cls.win.refresh()
        mine = [u for u in cls.win.frame["units"] if u["team"] == 0]
        plain = next(u for u in mine
                     if not (u.get("caps") or {}).get("indirect"))
        cls.win.fsm.select_units([plain["id"]])
        cls.tmp = tempfile.mkdtemp()
        cls.shot = os.path.join(cls.tmp, "battle_grid.png")
        cls.win.snapshot(cls.shot)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def test_order_grid_region_changed_vs_baseline(self):
        from tools.qa_visual import diff_ratio
        ratio = diff_ratio(self.shot, _BASELINE, (940, 550, 1270, 790))
        self.assertGreaterEqual(ratio, 0.05, "命令格 diff=%r 未达 0.05" % ratio)


if __name__ == "__main__":
    unittest.main()
