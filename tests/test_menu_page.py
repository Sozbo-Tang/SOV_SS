"""FE-05 F7 主菜单测试：页面迁移/页签切换/灰显只 toast（无头鸭子面）＋
menu→config→deploy 全链与快照（GL 类）。"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.ui.menu_page import MENU_TABS, layout_menu_page          # noqa: E402
from sovs.ui.shell_fsm import ShellFsm                              # noqa: E402

try:
    import arcade                                    # noqa: F401（探针）
    from tests._gl_probe import gl_window_available
    HAS_GL_WINDOW = gl_window_available()
except Exception:                                    # noqa: BLE001
    HAS_GL_WINDOW = False

_W, _H = 1280, 800


def _duck_win():
    fsm = ShellFsm()
    fsm.open_menu()
    return SimpleNamespace(width=_W, height=_H, fsm=fsm,
                           frame={"players": [], "units": [], "aircraft": []},
                           session=SimpleNamespace(),
                           _layout_buttons=lambda: None, _buttons=[])


class TestMenuPageLogic(unittest.TestCase):

    def test_page_transitions(self):
        fsm = ShellFsm()
        self.assertEqual(fsm.page, "config")        # 默认页不动（既有测试零扰）
        fsm.open_menu()
        self.assertEqual(fsm.page, "menu")
        self.assertEqual(fsm.menu_tab, "HOME")
        fsm.open_config()
        self.assertEqual(fsm.page, "config")
        fsm.open_menu()
        fsm.close_menu()
        self.assertEqual(fsm.page, "config")

    def test_layout_tabs_and_actions(self):
        win = _duck_win()
        layout_menu_page(win)
        tabs = [b for b in win._buttons if b.key.startswith("menutab_")]
        acts = [b for b in win._buttons if b.key.startswith("menu_")
                and not b.key.startswith("menutab_")]
        self.assertEqual(len(tabs), 4)              # 四页签
        self.assertEqual([b.key[8:] for b in tabs],
                         [k for k, _l in MENU_TABS])
        self.assertTrue(acts)                       # HOME 动作钮在场
        for t, a in zip(tabs, acts):                # 动作区在页签列右侧
            self.assertGreater(a.x0, t.x1)

    def test_tab_switch_reroutes_actions(self):
        from sovs.ui.menu_page import handle_menu_click, menu_tab_of
        win = _duck_win()
        layout_menu_page(win)
        tab_btn = next(b for b in win._buttons if b.key == "menutab_PLAY")
        handle_menu_click(win, (tab_btn.x0 + tab_btn.x1) / 2,
                          (tab_btn.yb + tab_btn.yt) / 2)
        self.assertEqual(menu_tab_of(win), "PLAY")
        win._buttons = []
        layout_menu_page(win)
        keys = {b.key for b in win._buttons}
        self.assertIn("menu_multi", keys)
        self.assertNotIn("menu_solo", keys)         # HOME 钮不残留

    def test_grey_actions_toast_only(self):
        from sovs.ui.menu_page import handle_menu_click
        win = _duck_win()
        layout_menu_page(win)
        cont = next(b for b in win._buttons if b.key == "menu_continue")
        handle_menu_click(win, (cont.x0 + cont.x1) / 2,
                          (cont.yb + cont.yt) / 2)
        self.assertEqual(win.fsm.page, "menu")       # 不跳页
        self.assertTrue(win.fsm.notifications)       # 只 toast
        win.fsm.menu_tab = "PLAY"
        win._buttons = []
        layout_menu_page(win)
        multi = next(b for b in win._buttons if b.key == "menu_multi")
        handle_menu_click(win, (multi.x0 + multi.x1) / 2,
                          (multi.yb + multi.yt) / 2)
        self.assertEqual(win.fsm.page, "menu")
        self.assertIn("单人版本未开放",
                      win.fsm.notifications[-1]["text"])

    def test_solo_enters_config(self):
        from sovs.ui.menu_page import handle_menu_click
        win = _duck_win()
        layout_menu_page(win)
        solo = next(b for b in win._buttons if b.key == "menu_solo")
        handle_menu_click(win, (solo.x0 + solo.x1) / 2,
                          (solo.yb + solo.yt) / 2)
        self.assertEqual(win.fsm.page, "config")

    def test_combat_keys_blocked_on_menu(self):
        fsm = ShellFsm()
        fsm.open_menu()
        self.assertEqual(fsm.key("Q"), "blocked")
        fsm.notify = lambda *a, **k: None            # toast 依赖解耦


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestMenuFullChain(unittest.TestCase):
    """menu→config→deploy 全链（真实事件层）＋主菜单快照非空。"""

    @classmethod
    def setUpClass(cls):
        from sovs.app.session import SkirmishSession
        from sovs.ui.shell_window import ShellWindow
        cls.session = SkirmishSession(seed=42)
        cls.win = ShellWindow(cls.session, visible=False)
        cls.win.fsm.open_menu()
        cls.win.refresh()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def test_menu_config_deploy_chain(self):
        w = self.win
        self.assertEqual(w.fsm.page, "menu")
        solo = next(b for b in w._buttons if b.key == "menu_solo")
        w.on_mouse_press((solo.x0 + solo.x1) / 2, (solo.yb + solo.yt) / 2,
                         arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertEqual(w.fsm.page, "config")
        w.on_key_press(arcade.key.ENTER, 0)          # config 起局
        self.assertEqual(w.fsm.page, "deploy")

    def test_menu_snapshot_nonblank(self):
        import tempfile
        from PIL import Image
        w = self.win
        w.fsm.page = "config"                        # 链上测试可能已到 deploy
        w.fsm.open_menu()
        w.refresh()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "menu.png")
            w.snapshot(path)
            img = Image.open(path).convert("RGB")
            self.assertEqual(img.size, (w.width, w.height))
            self.assertGreaterEqual(
                len(img.getcolors(maxcolors=1_000_000)), 8)
        w.fsm.open_config()
        w.refresh()


if __name__ == "__main__":
    unittest.main()
