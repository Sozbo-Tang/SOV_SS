"""GP-01 §7 卡组编辑器测试（M4）：后端 YAML↔JSON 往返 + 校验同权威 + fsm 页流转。

- sovs/app/deck_editor.py：卡池目录（自 data/yaml 编译面全 67 卡）、保存
  （YAML 落盘→就地编译 data/gen/decks/<key>.json→config 页即时可选）、读取/
  克隆/删除、validate（card_schema.validate_deck 同规则——与构建期/运行期
  同一权威无双轨）；
- sovs/ui/shell_fsm.py deck_edit 页：config→deck_edit→ESC 返回流转、战斗键
  全拦、加卡/调份数/页签态。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.app.deck_editor import DeckEditor  # noqa: E402
from sovs.sim import card_loader as cl  # noqa: E402
from sovs.ui.shell_fsm import ShellFsm  # noqa: E402

try:
    import arcade                                    # noqa: F401（探针）
    from tests._gl_probe import gl_window_available
    HAS_GL_WINDOW = gl_window_available()
except Exception:                                    # noqa: BLE001
    HAS_GL_WINDOW = False

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = cl.load_library(os.path.join(_ROOT, "data", "gen", "cards_ground.v1.json"))
_TPL = {k: rec.unit_template for k, rec in _LIB.items()}

_TMP_KEY = "unit_test_deck"


class TestDeckEditorBackend(unittest.TestCase):

    def setUp(self):
        self.ed = DeckEditor()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        try:
            self.ed.delete(_TMP_KEY)
        except FileNotFoundError:
            pass

    def test_list_decks_has_builtins(self):
        decks = self.ed.list_decks()
        self.assertIn("su_min", decks)
        self.assertIn("ger_min", decks)

    def test_catalog_covers_full_ground_library(self):
        """卡池=全库（M1 表格行数全录 67 卡——编辑器「全卡浏览」的数据面；
        精确数由 test_yaml_pipeline.py 同锚锁定，此处等值断言）。"""
        catalog = self.ed.catalog()
        self.assertEqual(len(catalog), 67)
        sample = next(c for c in catalog if c["card_key"] == "SU_MORTAR82")
        for field in ("name", "cost", "category", "pool", "per_card_limit",
                      "quota_group", "faction"):
            self.assertIn(field, sample)

    def test_load_deck_reads_yaml_entries(self):
        deck = self.ed.load_deck("su_min")
        self.assertEqual(deck["deck_key"], "su_min")
        self.assertEqual(deck["faction"], "SOVIET")
        entries = {k: n for k, n in deck["cards"]}
        self.assertEqual(entries.get("SU_RIFLE"), 2)

    def test_save_roundtrip_yaml_and_compiled_json(self):
        entries = [("SU_RECON", 1), ("SU_RIFLE", 2), ("SU_MORTAR82", 1),
                   ("SU_T3485", 1), ("SU_ZIS3", 1)]
        self.ed.save(_TMP_KEY, "SOVIET", entries)
        yaml_path = self.ed.yaml_path(_TMP_KEY)
        json_path = self.ed.json_path(_TMP_KEY)
        self.assertTrue(yaml_path.is_file())
        self.assertTrue(json_path.is_file())
        # 运行期加载面（card_loader——与 config 页/开局同一消费口）读得回
        deck = cl.load_deck(json_path)
        self.assertEqual(deck.deck_key, _TMP_KEY)
        self.assertEqual(dict(deck.cards)["SU_MORTAR82"], 1)
        # 编辑器读回同一份
        again = self.ed.load_deck(_TMP_KEY)
        self.assertEqual([tuple(e) for e in again["cards"]], entries)

    def test_save_rejects_invalid_deck_and_writes_nothing(self):
        """校验同权威（validate_deck）：D032 超限份拒绝且不落盘。"""
        with self.assertRaises(ValueError):
            self.ed.save(_TMP_KEY, "SOVIET", [("SU_RIFLE", 99)])
        self.assertFalse(self.ed.yaml_path(_TMP_KEY).is_file())
        self.assertFalse(self.ed.json_path(_TMP_KEY).is_file())

    def test_validate_returns_inline_errors(self):
        errors = self.ed.validate("SOVIET", [("SU_RIFLE", 99)])
        self.assertTrue(errors and "D032" in errors[0])
        self.assertEqual(self.ed.validate("SOVIET", [("SU_RIFLE", 1)]), [])
        # 阵营不一致
        errors = self.ed.validate("SOVIET", [("GER_RIFLE", 1)])
        self.assertTrue(errors)

    def test_clone_copies_under_new_key(self):
        self.ed.save(_TMP_KEY, "SOVIET", [("SU_RIFLE", 1)])
        self.ed.clone(_TMP_KEY, _TMP_KEY + "_c")
        self.addCleanup(self.ed.delete, _TMP_KEY + "_c")
        cloned = self.ed.load_deck(_TMP_KEY + "_c")
        self.assertEqual(cloned["cards"], [("SU_RIFLE", 1)])
        self.assertTrue(self.ed.json_path(_TMP_KEY + "_c").is_file())

    def test_delete_removes_yaml_and_json(self):
        self.ed.save(_TMP_KEY, "SOVIET", [("SU_RIFLE", 1)])
        self.ed.delete(_TMP_KEY)
        self.assertFalse(self.ed.yaml_path(_TMP_KEY).exists())
        self.assertFalse(self.ed.json_path(_TMP_KEY).exists())

    def test_delete_builtins_guarded(self):
        """内置两卡组受删保护（编辑器只删自制面——防误删数据源）。"""
        with self.assertRaises(ValueError):
            self.ed.delete("su_min")

    def test_points_summary(self):
        self.ed.save(_TMP_KEY, "SOVIET", [("SU_RIFLE", 2), ("SU_MORTAR82", 1)])
        summary = self.ed.summary([("SU_RIFLE", 2), ("SU_MORTAR82", 1)],
                                  "SOVIET")
        self.assertEqual(summary["points_main"],
                         _TPL["SU_RIFLE"].cost * 2 + _TPL["SU_MORTAR82"].cost)
        self.assertGreater(summary["cap_main"], summary["points_main"])


class TestDeckEditPageFsm(unittest.TestCase):

    def _open(self):
        f = ShellFsm()
        state = {"deck_key": "su_min", "faction": "SOVIET",
                 "cards": [("SU_RIFLE", 2)], "tab": "INFANTRY", "errors": []}
        f.open_deck_edit(state)
        return f

    def test_page_flow_config_to_deck_edit_and_back(self):
        f = self._open()
        self.assertEqual(f.page, "deck_edit")
        with self.assertRaises(AssertionError):
            f.start_deploy()                        # 起局必须先回 config
        f.close_deck_edit()
        self.assertEqual(f.page, "config")
        f.start_deploy()                            # 回 config 后可起局
        self.assertEqual(f.page, "deploy")

    def test_combat_keys_blocked_with_toast(self):
        f = self._open()
        for name in ("Q", "T", "K", "V", "B", "TAB"):
            f.notifications.clear()
            self.assertEqual(f.key(name, cmd=None), "blocked", name)
        self.assertTrue(any("编辑器" in n["text"] for n in f.notifications))

    def test_add_card_and_copies_delta(self):
        f = self._open()
        f.deck_edit_add("SU_MORTAR82")              # 新卡入组一份
        f.deck_edit_add("SU_MORTAR82")              # 再点=+1 份
        self.assertIn(("SU_MORTAR82", 2), f.deck_edit["cards"])
        f.deck_edit_delta("SU_MORTAR82", -1)
        self.assertIn(("SU_MORTAR82", 1), f.deck_edit["cards"])
        f.deck_edit_delta("SU_MORTAR82", -1)        # 减到 0=移出
        self.assertNotIn("SU_MORTAR82",
                         [k for k, _ in f.deck_edit["cards"]])

    def test_tab_switch_and_rename_state(self):
        f = self._open()
        f.deck_edit_set_tab("ARMOR")
        self.assertEqual(f.deck_edit["tab"], "ARMOR")
        f.deck_edit_start_rename()
        self.assertTrue(f.deck_edit["renaming"])
        f.deck_edit_rename_key("x")                 # 逐字符编辑
        f.deck_edit_rename_backspace()
        f.deck_edit_start_rename()                  # 再进=确认退出改名字态
        self.assertFalse(f.deck_edit["renaming"])


class TestDeckEditorNewCloneReload(unittest.TestCase):
    """2026-10-19 修复回归：编辑器页内点 dk_new/dk_clone 必须有反应。

    旧实现两钮走 fsm.open_deck_edit（config 入口断言），在 deck_edit 页点即
    AssertionError——真窗事件循环里被 pyglet 吞＝玩家「点击没反应」，且克隆
    在断言炸之前已落盘、每点一次留一个孤儿卡组。修后经 fsm.deck_edit_reload
    页内热切换：状态切换可见、克隆落盘与界面同步。"""

    def _win(self):
        from types import SimpleNamespace
        from sovs.ui.deck_editor_page import open_deck_editor
        win = SimpleNamespace(fsm=ShellFsm(),
                              session=SimpleNamespace(deck_editor=DeckEditor()),
                              _buttons=[],
                              _layout_buttons=lambda: None)
        open_deck_editor(win)                      # 默认页 config→deck_edit
        return win

    def test_new_button_resets_to_blank_deck(self):
        from sovs.ui.deck_editor_page import handle_deck_edit_button
        win = self._win()
        old_key = win.fsm.deck_edit["deck_key"]
        handle_deck_edit_button(win, "dk_new")
        state = win.fsm.deck_edit
        self.assertEqual(win.fsm.page, "deck_edit")       # 不换页不炸断言
        self.assertNotEqual(state["deck_key"], old_key)
        self.assertEqual(state["cards"], [])             # 新建=空卡组
        self.assertEqual(state["faction"], "SOVIET")     # 阵营/页签携带
        self.assertFalse(state["renaming"])

    def test_clone_button_reloads_copy_and_files_synced(self):
        from sovs.ui.deck_editor_page import handle_deck_edit_button
        win = self._win()
        old_key = win.fsm.deck_edit["deck_key"]
        handle_deck_edit_button(win, "dk_clone")
        state = win.fsm.deck_edit
        self.assertEqual(win.fsm.page, "deck_edit")
        self.assertNotEqual(state["deck_key"], old_key)
        ed = win.session.deck_editor
        self.assertTrue(ed.json_path(state["deck_key"]).is_file())
        self.assertEqual(state["cards"], ed.load_deck(old_key)["cards"])
        self.assertTrue(any("已克隆" in n["text"]
                            for n in win.fsm.notifications))
        self.addCleanup(ed.delete, state["deck_key"])    # 界面态与磁盘同步


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话（pip install -e \".[fe]\"）")
class TestDeckEditorEventLayer(unittest.TestCase):
    """真实事件层编辑器流（M4 验收锚「编辑器编辑→保存→config 页即时可选」）：
    config 点『编辑卡组』→页签→加卡→超限红字+保存禁用→退回限内→改名→保存
    →ESC 返回——dk_* 键前缀解析/换页命中域重排两处回归护栏（首版实测双 bug）。"""

    def test_full_editor_flow_via_real_events(self):
        import arcade
        from sovs.app.session import SkirmishSession
        from sovs.ui.shell_window import ShellWindow

        session = SkirmishSession(seed=42)
        win = ShellWindow(session, visible=False)
        L = arcade.MOUSE_BUTTON_LEFT

        def click(btn):
            win.on_mouse_press((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2,
                               L, 0)

        try:
            click(next(b for b in win._buttons if b.key == "deck_edit"))
            self.assertEqual(win.fsm.page, "deck_edit")
            click(next(b for b in win._buttons if b.key == "dk_tab_INFANTRY"))
            self.assertEqual(win.fsm.deck_edit["tab"], "INFANTRY")
            add = next(b for b in win._buttons if b.key.startswith("dk_add_"))
            card_key = add.key[7:]                 # 前缀 7 字符（card_key 含下划线）
            n0 = dict(win.fsm.deck_edit["cards"]).get(card_key, 0)
            click(add)
            self.assertEqual(dict(win.fsm.deck_edit["cards"]).get(card_key),
                             n0 + 1)
            click(next(b for b in win._buttons
                       if b.key == "dk_inc_%s" % card_key))
            errors = win.fsm.deck_edit["errors"]
            self.assertTrue(errors and "D032" in errors[0], errors[:1])
            self.assertEqual(next(b.tone for b in win._buttons
                                  if b.key == "dk_save"), "disabled")
            click(next(b for b in win._buttons
                       if b.key == "dk_dec_%s" % card_key))
            self.assertFalse(win.fsm.deck_edit["errors"])
            click(next(b for b in win._buttons if b.key == "dk_rename"))
            win.fsm.deck_edit_rename_key("deck_edit_evt")
            click(next(b for b in win._buttons if b.key == "dk_rename"))
            self.assertEqual(win.fsm.deck_edit["deck_key"], "deck_edit_evt")
            click(next(b for b in win._buttons if b.key == "dk_save"))
            ed = session.deck_editor
            self.assertTrue(ed.yaml_path("deck_edit_evt").is_file())
            self.assertTrue(ed.json_path("deck_edit_evt").is_file())
            self.assertIn("deck_edit_evt", session.deck_list())  # 即时可选
            win.on_key_press(arcade.key.ESCAPE, 0)
            self.assertEqual(win.fsm.page, "config")
        finally:
            win.close()
            try:
                session.deck_editor.delete("deck_edit_evt")
            except (FileNotFoundError, ValueError):
                pass


if __name__ == "__main__":
    unittest.main()
