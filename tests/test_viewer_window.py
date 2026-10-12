"""FE-T06 观战器窗口层测试（需 fe 渲染栈——未装 arcade 全类跳过，CI 零渲染栈空转）。

覆盖面（隐藏窗离屏，不依赖可见 GUI 会话的项）：
- 三视角迷雾不对称（同拍 ref 全知 ≥ 单视角可见——经 session 状态帧断言，
  非 PNG 像素比对）；
- 按键→PlaybackController/视角状态机（SPACE/方向/倍速/1-2-3/Tab——直接调
  on_key_press，无需事件循环）；
- 时间轴点击/拖动=seek（on_mouse_press/on_mouse_drag 命中带）；
- snapshot 离屏落盘非空非白屏（PIL 色数 ≥8——知情确认项验收判据同口径）。

接线纪律自证：本测试只经 tools 胶水（ViewerSession）驱动窗口；窗口层自身
不 import sovs.sim（tests/test_arch_constraints.py 另有 AST 守卫）。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import arcade                                    # noqa: F401（探针）
    import pyglet.display
    # 显示会话探针：arcade 可导入但 WindowServer 不可达（合盖/无头）时，建窗会在
    # pyglet cocoa get_default_screen 处 IndexError——以屏幕枚举预判并整类跳过。
    # （探针修复：pyglet 2.x 删 pyglet.canvas——pyglet.display.get_display() 现行 API。）
    HAS_GL_WINDOW = len(pyglet.display.get_display().get_screens()) > 0
    HAS_ARCADE = True
except Exception:                                    # noqa: BLE001（缺渲染栈或无显示会话=跳过）
    HAS_ARCADE = False
    HAS_GL_WINDOW = False

REPLAY = os.path.join("data", "gen", "replays", "golden_air_seed42.jsonl")


def _have_replay() -> bool:
    return os.path.exists(REPLAY)


@unittest.skipUnless(HAS_GL_WINDOW and _have_replay(),
                     "需 fe 渲染栈 + 显示会话 + 黄金回放（pip install -e \".[fe]\"；"
                     "tools/record_golden.py）")
class TestViewerWindow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from tools.replay_viewer import ViewerSession
        from sovs.ui.viewer_window import ViewerWindow
        cls.session = ViewerSession(REPLAY)
        cls.session.seek(cls.session.total // 2)      # 代表拍（先定位后建窗）
        cls.win = ViewerWindow(cls.session, visible=False)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    # ── 三视角迷雾不对称 ──

    def test_three_views_fog_asymmetry(self):
        ref = self.session.frame("ref")
        blue = self.session.frame("blue")
        red = self.session.frame("red")
        self.assertIsNone(ref["view"])                # 裁判=全知（帧头契约）
        self.assertEqual(blue["view"], 1)             # blue→team1（录制标签口径）
        self.assertEqual(red["view"], 0)
        self.assertGreaterEqual(len(ref["units"]),
                                max(len(blue["units"]), len(red["units"])))
        # 黄金回放代表拍（total//2=6900）实测：blue u0/a2 vs ref u1/a7——严格
        # 不对称成立（黄金回放确定性冻结，断言可写死量级）
        self.assertLess(len(blue["units"]), len(ref["units"]))
        self.assertLess(len(blue["aircraft"]), len(ref["aircraft"]))
        # 队视角只见本队玩家经济（私有信息边界）
        self.assertEqual({p["team"] for p in blue["players"]}, {1})

    def test_set_view_switches_frame_source(self):
        self.win.set_view("red")
        self.assertEqual(self.win.frame["view"], 0)
        self.win.set_view("ref")
        self.assertIsNone(self.win.frame["view"])

    # ── 按键状态机 ──

    def test_keys_play_step_speed_views(self):
        w, c = self.win, self.win.ctrl
        w._seek_ctrl(0)                               # 从 0 拍起算（setUpClass 在代表拍）
        w.on_key_press(arcade.key.SPACE, 0)
        self.assertTrue(c.playing)
        w.on_update(0.12)                             # 1x×0.12s≈1 拍（现场推导）
        self.assertEqual(c.tick, 1)
        w.on_key_press(arcade.key.LEFT, 0)            # 步进先暂停
        self.assertEqual(c.tick, 0)
        self.assertFalse(c.playing)
        w.on_key_press(arcade.key.RIGHT, arcade.key.MOD_SHIFT)   # Shift=+10 拍
        self.assertEqual(c.tick, 10)
        w.on_key_press(arcade.key.UP, 0)              # 1x→2x
        self.assertEqual(c.speed, 2.0)
        w.on_key_press(arcade.key.MINUS, 0)           # +/- 同效降档
        self.assertEqual(c.speed, 1.0)
        w.on_key_press(arcade.key.KEY_2, 0)              # 2=红方视角
        self.assertEqual(w.view_key, "red")
        w.on_key_press(arcade.key.TAB, 0)             # Tab 循环 red→ref
        self.assertEqual(w.view_key, "ref")

    def test_timeline_click_and_drag_seek(self):
        c = self.win.ctrl
        left, right, cy, _h = self.win._timeline_geom()
        self.win.on_mouse_press((left + right) // 2, cy, 0, 0)
        self.assertEqual(c.tick, self.session.total // 2)
        self.win.on_mouse_drag(right - 1, cy, 5, 0, 0, 0)
        expect = int((right - 1 - left) / (right - left) * self.session.total)
        self.assertEqual(c.tick, expect)              # 像素几何→拍数换算即所求
        self.win.on_mouse_release(0, 0, 0, 0)
        self.assertEqual(self.session.cursor, c.tick)  # 会话游标同步

    # ── 离屏截帧 ──

    def test_snapshot_offscreen_nonblank(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "probe.png")
            self.win.set_view("ref")
            self.win.snapshot(path)
            img = Image.open(path).convert("RGB")
            colors = img.getcolors(maxcolors=1_000_000)
        self.assertGreaterEqual(len(colors), 8)       # 非空非白屏
        self.assertEqual(img.size, (self.win.width, self.win.height))

    def test_settle_frame_renders_panel_data(self):
        self.session.seek(self.session.total)
        self.win._refresh()
        self.win.on_draw()                            # 结算面板绘制路径无异常
        self.assertIsNotNone(self.win.frame["result"])
        self.session.seek(self.session.total // 2)    # 复位（后续用例秩序无关）
        self.win._refresh()


if __name__ == "__main__":
    unittest.main()
