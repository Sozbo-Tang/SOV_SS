"""FE-T07 可玩壳门禁（tools/skirmish_shell.py）：--smoke 整局 / --screenshot 四页。

- --smoke：默认配置（su_min vs 规则兜底 KEV）自动跑一局到结算，五组命令
  「入队+消费+World 可断言变化」证据逐条核对，全绿 exit 0；
- --screenshot：隐藏窗离屏渲染四页各一张 PNG（config/deploy/battle/result；
  battle 页须有单位+一处框选+一条已下达命令痕迹——本测试对截图前的窗口态
  断言 + PNG 非空白双重核对）；
- CLI 参数面：零旗标=交互观战（mock 断言，不开窗）。
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import skirmish_shell  # noqa: E402

try:
    import arcade                                    # noqa: F401（探针）
    # 显示会话探针：仅 GL 窗口/截图类需要；逻辑类（build_world/smoke/cli）无显示也可跑。
    # （探针修复：pyglet 2.x 删 pyglet.canvas；2026-10-13 加固——共享 _gl_probe
    #  双检：屏幕枚举＋隐藏窗实试，建不起来=整类跳过而非 setUpClass ERROR。）
    from tests._gl_probe import gl_window_available
    HAS_GL_WINDOW = gl_window_available()
    HAS_ARCADE = HAS_GL_WINDOW
except Exception:                                    # noqa: BLE001（缺渲染栈或无显示会话=跳过）
    HAS_ARCADE = False
    HAS_GL_WINDOW = False


class TestBuildWorld(unittest.TestCase):
    """默认配置世界装配：挂图/占点/双方卡组/部署相位。"""

    def test_default_world_wiring(self):
        w = skirmish_shell.build_world(42, "su_min")
        self.assertEqual(w.phase.__int__(), 0)        # PHASE_DEPLOY（60s 盲部署）
        self.assertIsNotNone(w.terrain)               # apply_map 挂 2km 演示图
        self.assertEqual(w.map_extent, (200000, 100000))
        self.assertEqual(len(w.objectives), 1)        # 中央占点
        human_ids = [s.template.template_id for s in w.players[0].deck_slots]
        self.assertIn(102, human_ids)                 # su_min 现役卡（SU_RIFLE）
        self.assertIn(103, human_ids)                 # 预备队空降卡随卡组挂载
        kev_ids = [s.template.template_id for s in w.players[1].deck_slots]
        self.assertIn(201, kev_ids)                   # 对手=另一套 ger_min


class TestSmokeGate(unittest.TestCase):
    """--smoke 整局门禁：到结算 + 五组命令生效证据 + 返回 0。"""

    def test_smoke_runs_full_game_to_settle(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = skirmish_shell.smoke()
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("OK", out)
        self.assertIn("结算", out)
        for group in ("move", "attack", "fire_mission", "air", "smoke_sprint"):
            self.assertIn(group, out)                 # 五组命令证据逐组落档


class TestCliSurface(unittest.TestCase):
    """参数面：--smoke/--screenshot/缺省交互三分支（mock 重操作）。"""

    def test_smoke_flag_calls_smoke(self):
        with mock.patch.object(skirmish_shell, "smoke", return_value=0) as m:
            rc = skirmish_shell.main(["--smoke"])
        m.assert_called_once_with(seed=42, deck="su_min", kev="rule", beat=10)
        self.assertEqual(rc, 0)

    def test_screenshot_flag_calls_screenshot(self):
        with mock.patch.object(skirmish_shell, "screenshot",
                               return_value=0) as m:
            rc = skirmish_shell.main(["--screenshot", "out/qa/"])
        m.assert_called_once_with("out/qa/", seed=42, deck="su_min", kev="rule")
        self.assertEqual(rc, 0)

    def test_default_calls_interactive(self):
        with mock.patch.object(skirmish_shell, "interactive",
                               return_value=0) as inter, \
             mock.patch.object(skirmish_shell, "smoke", return_value=1) as ms:
            rc = skirmish_shell.main([])
        ms.assert_not_called()
        inter.assert_called_once_with(seed=42, deck="su_min", kev="rule", beat=10)
        self.assertEqual(rc, 0)

    def test_explicit_options_forwarded(self):
        """--deck/--kev/--seed 透传 smoke（默认档位外的人工复核入口）。"""
        with mock.patch.object(skirmish_shell, "smoke", return_value=0) as m:
            skirmish_shell.main(["--smoke", "--deck", "ger_min",
                                 "--kev", "rule", "--seed", "7"])
        self.assertEqual(m.call_args.kwargs.get("deck"), "ger_min")
        self.assertEqual(m.call_args.kwargs.get("kev"), "rule")
        self.assertEqual(m.call_args.kwargs.get("seed"), 7)

    def test_coldstart_flag_calls_coldstart(self):
        with mock.patch.object(skirmish_shell, "coldstart",
                               return_value=0) as m:
            rc = skirmish_shell.main(["--coldstart"])
        m.assert_called_once_with(seed=42, deck="su_min", kev="rule")
        self.assertEqual(rc, 0)


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用（pip install -e \".[fe]\"）")
class TestScreenshotGate(unittest.TestCase):
    """--screenshot 四页门禁：四张 PNG 存在且非空白；battle 页三要素前置断言。"""

    def test_screenshot_four_pages(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            rc = skirmish_shell.screenshot(td)
            self.assertEqual(rc, 0)
            for name in ("config.png", "deploy.png", "battle.png", "result.png"):
                path = os.path.join(td, name)
                self.assertTrue(os.path.exists(path), name)
                img = Image.open(path).convert("RGB")
                colors = img.getcolors(maxcolors=1_000_000)
                self.assertGreaterEqual(len(colors), 8,
                                        "%s 疑似空白（色数 %d）" % (name, len(colors)))

    def test_coldstart_event_layer_gate(self):
        """交互重设计 A11：隐藏窗经真实事件层走完四页，逐项断言 exit 0。"""
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = skirmish_shell.coldstart()
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("OK", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
