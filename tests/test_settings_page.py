"""设置改键块测试（2026-10-14——manual.txt:91,544-545 翻面 done 的门禁面）。

覆盖面：keybinds 存取/校验（保留键/非字母/占用拒绝/containment 越界拒）、
fsm settings 页门（自 config 进出/战斗键拦截）、settings_page 鸭子窗布局与
改键捕获流（无 GL——仿 test_hud_geometry 鸭子窗；通知走真 ShellFsm）。"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import arcade

from sovs.ui import keybinds, settings_page
from sovs.ui.shell_fsm import ShellFsm


class _TmpSettings:
    """SETTINGS_PATH/ALLOWED_DIR 两常量同步注入 tmp（keybinds._settings_path
    containment 契约——只换路径不换允许目录会被越界拒）。"""

    def __init__(self, tmp: str):
        self._patchers = [
            mock.patch.object(keybinds, "ALLOWED_DIR", Path(tmp)),
            mock.patch.object(keybinds, "SETTINGS_PATH",
                              Path(tmp) / "keybinds.json"),
        ]

    def __enter__(self):
        for p in self._patchers:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patchers:
            p.stop()


class _TmpSettingsCase(unittest.TestCase):
    """keybinds 路径注入基类（逐用例隔离 tmp，防污染仓库 data/gen）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._ctx = _TmpSettings(self._tmp.name)
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)
        self._tmp.cleanup()


class TestKeybindsStore(_TmpSettingsCase):
    def test_load_missing_is_empty(self):
        self.assertEqual(keybinds.load_overrides(), {})

    def test_assign_roundtrip_and_display(self):
        ok, msg = keybinds.assign("Q", ord("I"))
        self.assertTrue(ok, msg)
        self.assertEqual(keybinds.load_overrides(), {"Q": ord("I")})
        self.assertEqual(keybinds.display_map()["Q"], "I")
        self.assertEqual(keybinds.sub("{Q}+点 攻击"), "I+点 攻击")
        # 未改绑槽位=槽位名本身
        self.assertEqual(keybinds.display_map()["T"], "T")

    def test_assign_rejects_reserved_and_nonletter(self):
        self.assertFalse(keybinds.assign("Q", arcade.key.W)[0])      # 相机保留键
        self.assertFalse(keybinds.assign("Q", arcade.key.KEY_5)[0])  # 数字保留
        self.assertFalse(keybinds.assign("Q", arcade.key.SPACE)[0])  # 系统保留
        self.assertEqual(keybinds.load_overrides(), {})              # 失败不落盘

    def test_assign_rejects_collision(self):
        self.assertTrue(keybinds.assign("Q", ord("I"))[0])
        ok, msg = keybinds.assign("T", ord("I"))
        self.assertFalse(ok)
        self.assertIn("占用", msg)
        self.assertEqual(sorted(keybinds.load_overrides().items()),
                         [("Q", ord("I"))])                    # T 未写入

    def test_rebind_same_slot_twice_replaces(self):
        self.assertTrue(keybinds.assign("Q", ord("I"))[0])
        self.assertTrue(keybinds.assign("Q", ord("U"))[0])
        self.assertEqual(keybinds.load_overrides(), {"Q": ord("U")})

    def test_reset_all_restores_default(self):
        keybinds.assign("Q", ord("I"))
        keybinds.reset_all()
        self.assertEqual(keybinds.load_overrides(), {})
        self.assertEqual(keybinds.display_map()["Q"], "Q")

    def test_containment_guard_rejects_escape(self):
        outside = Path(self._tmp.name) / "nested"
        outside.mkdir()
        with mock.patch.object(keybinds, "ALLOWED_DIR",
                               Path(self._tmp.name)), \
             mock.patch.object(keybinds, "SETTINGS_PATH",
                               outside / "kb.json"):
            with self.assertRaises(ValueError):
                keybinds.load_overrides()


class TestSettingsPageFsm(unittest.TestCase):
    def test_open_close_settings_roundtrip(self):
        f = ShellFsm()
        f.open_settings()
        self.assertEqual(f.page, "settings")
        f.close_settings()
        self.assertEqual(f.page, "config")

    def test_open_settings_only_from_config(self):
        f = ShellFsm()
        f.start_deploy()
        with self.assertRaises(AssertionError):
            f.open_settings()

    def test_combat_keys_blocked_on_settings(self):
        f = ShellFsm()
        f.open_settings()
        self.assertEqual(f.key("Q"), "blocked")
        f.close_settings()


class _DuckWin:
    """鸭子窗（无 GL）：layout/click/key 面测试——仿 test_hud_geometry 口径。"""

    def __init__(self):
        self.fsm = ShellFsm()
        self.width, self.height = 1280, 720
        self._buttons = []
        self._settings_armed = None
        self.rebuilds = 0

    def _rebuild_key_names(self):
        self.rebuilds += 1

    def _layout_buttons(self):
        self._buttons = []
        settings_page.layout_settings_page(self)

    def buttons_by_key(self):
        return {b.key: b for b in self._buttons}


class TestSettingsPageLayoutAndFlow(_TmpSettingsCase):
    def setUp(self):
        super().setUp()
        self.win = _DuckWin()
        self.win.fsm.open_settings()
        settings_page.layout_settings_page(self.win)

    def _btn_xy(self, key):
        b = self.win.buttons_by_key()[key]
        return ((b.x0 + b.x1) / 2, (b.yb + b.yt) / 2)

    def test_layout_has_22_rebind_buttons_and_actions(self):
        keys = self.win.buttons_by_key()
        rebinds = [k for k in keys if k.startswith("st_rebind_")]
        self.assertEqual(len(rebinds), 22)              # COMBAT_KEYS 全槽
        self.assertIn("st_reset", keys)
        self.assertIn("st_back", keys)

    def test_rebind_capture_flow_assigns_and_rebuilds(self):
        settings_page.handle_settings_click(
            self.win, *self._btn_xy("st_rebind_Q"))
        self.assertEqual(self.win._settings_armed, "Q")
        settings_page.handle_settings_key(self.win, ord("I"))
        self.assertIsNone(self.win._settings_armed)     # 捕获态消费即清
        self.assertEqual(self.win.rebuilds, 1)          # 键名映射即时重建
        self.assertEqual(keybinds.load_overrides(), {"Q": ord("I")})

    def test_capture_collision_rejects_without_rebuild(self):
        keybinds.assign("T", ord("I"))
        settings_page.handle_settings_click(
            self.win, *self._btn_xy("st_rebind_Q"))
        settings_page.handle_settings_key(self.win, ord("I"))
        self.assertIsNone(self.win._settings_armed)
        self.assertEqual(self.win.rebuilds, 0)          # 失败不重建映射
        self.assertNotIn("Q", keybinds.load_overrides())

    def test_capture_esc_cancels_without_assign(self):
        settings_page.handle_settings_click(
            self.win, *self._btn_xy("st_rebind_Q"))
        settings_page.handle_settings_key(self.win, arcade.key.ESCAPE)
        self.assertIsNone(self.win._settings_armed)
        self.assertEqual(self.win.fsm.page, "settings")  # 只取消捕获不退页
        self.assertEqual(keybinds.load_overrides(), {})

    def test_back_button_closes_to_config(self):
        settings_page.handle_settings_click(self.win, *self._btn_xy("st_back"))
        self.assertEqual(self.win.fsm.page, "config")
        self.assertIsNone(self.win._settings_armed)

    def test_reset_button_clears_overrides(self):
        keybinds.assign("Q", ord("I"))
        settings_page.handle_settings_click(
            self.win, *self._btn_xy("st_reset"))
        self.assertEqual(keybinds.load_overrides(), {})
        self.assertEqual(self.win.rebuilds, 1)


class TestSettingsPageRouting(unittest.TestCase):
    """〔2026-10-15 六条修正·问题1〕窗口点击分流源码锚：on_mouse_press 页面
    分流元组须含 "settings"——修前 settings 不入元组，st_* 命中落入 _panel_click
    即被吞（含返回钮 st_back），设置页点击全无反应（先例=test_manual_conformance
    HOTKEYS 源码解析锚）。"""

    def test_on_mouse_press_routes_settings_page(self):
        import re
        src = Path("sovs/ui/shell_window.py").read_text(encoding="utf-8")
        m = re.search(r'if page in \(([^)]*)\):\s*\n\s*self\._config_click',
                      src)
        self.assertIsNotNone(m, "on_mouse_press 页面分流元组未找到")
        pages = [p.strip().strip('"\'') for p in m.group(1).split(",")]
        self.assertIn("settings", pages,
                      "settings 不在 _config_click 分流元组（点击被吞）")


if __name__ == "__main__":
    unittest.main()
