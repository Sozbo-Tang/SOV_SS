"""FE-05 F5 卡面缩略图测试：67 卡缩略图可查 / 卡行命中矩形不变 / 卡池缩略
图几何（40×40 左置不压行）/ 差分（GL 类：deck_edit/deploy 区域 ≥0.01）。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.ui.hud_bottom import layout_air_rail                         # noqa: E402
from sovs.ui.palette import MARGIN, RAIL_W                             # noqa: E402
from sovs.ui.shell_fsm import ShellFsm                                 # noqa: E402

try:
    import arcade                                    # noqa: F401（探针）
    from tests._gl_probe import gl_window_available
    HAS_GL_WINDOW = gl_window_available()
except Exception:                                    # noqa: BLE001
    HAS_GL_WINDOW = False

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BASE_DECK = os.path.join(_ROOT, "out", "qa_fe05_baseline", "deck_edit.png")
_BASE_DEPLOY = os.path.join(_ROOT, "out", "qa_fe05_baseline", "deploy.png")
_W, _H = 1280, 800


def _duck_win(*, page="battle", deck=(), roster=()):
    fsm = ShellFsm()
    fsm.page = page
    return SimpleNamespace(width=_W, height=_H,
                           frame={"players": [{"deck": list(deck)}],
                                  "units": [], "aircraft": [], "view": 0,
                                  "lasers": []},
                           fsm=fsm,
                           session=SimpleNamespace(air_roster=lambda: list(roster)),
                           _buttons=[])


class TestCardThumbnails(unittest.TestCase):

    def setUp(self):
        """无头量尺（真 arcade.Text 需活动窗——test_hud_geometry 同款补丁）。"""
        import unittest.mock as mock
        from sovs.ui import hud_top

        def est(text, size):
            return size * sum(2 if ord(ch) > 0x2E7F else 1 for ch in str(text))

        self._ruler = mock.patch.object(hud_top, "text_width", est)
        self._ruler.start()
        self.addCleanup(self._ruler.stop)

    def test_all_67_card_keys_have_thumbnail(self):
        from sovs.ui import assets
        idx = assets.index()
        keys = {e["card_key"] for e in idx["units"].values()}
        self.assertGreaterEqual(len(keys), 67)
        for k in sorted(keys):
            self.assertIsNotNone(assets.unit_tex(k), k)

    def test_rail_card_hit_rects_unchanged(self):
        """F5 只换画面不换几何：buy: 卡 Btn 矩形与旧口径一致（x=MARGIN、
        宽 RAIL_W、竖距 28）。"""
        deck = [{"template_id": 101 + i, "name": "单位%02d" % i,
                 "copies_left": 2, "airdrop": False} for i in range(4)]
        win = _duck_win(deck=deck)
        layout_air_rail(win)
        buys = [b for b in win._buttons if b.key.startswith("buy:")]
        self.assertGreaterEqual(len(buys), 4)
        for b in buys:
            self.assertAlmostEqual(b.x0, MARGIN)
            self.assertAlmostEqual(b.x1 - b.x0, RAIL_W)
            self.assertAlmostEqual(b.yt - b.yb, 24)
        for a, b in zip(buys, buys[1:]):
            self.assertAlmostEqual(a.yb - b.yb, 28)      # 竖距不变

    def test_deck_thumb_rect_geometry(self):
        """R1：卡池缩略图**行内左端** 24×24（原行外 40×40 压「卡池」标题）；
        与标题带零重叠断言。"""
        from sovs.ui.deck_editor_page import (deck_thumb_rect,
                                              pool_title_rect, _THUMB_PX)
        from sovs.ui.hud_bottom import Btn
        btn = Btn(140, 400.0, 300, 24, "dk_add_SU_RIFLE", "x")
        r = deck_thumb_rect(btn)
        self.assertEqual(_THUMB_PX, 24)
        self.assertAlmostEqual(r[2] - r[0], 24)          # 行内 24×24
        self.assertAlmostEqual(r[3] - r[1], 24)
        self.assertAlmostEqual(r[0], btn.x0 + 2)        # 行内左端
        self.assertGreaterEqual(r[1], btn.yb - 0.5)     # 不越行界
        self.assertLessEqual(r[3], btn.yt + 0.5)
        # 标题带（top-58..top-42 文字带）与首行（top-84 起）缩略图零重叠
        win = SimpleNamespace(width=_W, height=_H)
        title = pool_title_rect(win)
        first_row_btn = Btn(140, _H - 56 - 84, 300, 24, "dk_add_X", "x")
        first = deck_thumb_rect(first_row_btn)
        self.assertLessEqual(first[3], title[1],
                             "首行缩略图上缘 %r 侵入标题带 %r" % (first[3], title))


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestCardArtDiff(unittest.TestCase):
    """deck_edit / deploy 页实渲染 vs F0 基线：对应缩略图区 diff ≥0.01。"""

    @classmethod
    def setUpClass(cls):
        need = (_BASE_DECK, _BASE_DEPLOY)
        if not all(os.path.isfile(p) for p in need):
            raise unittest.SkipTest("基线图缺失")
        from sovs.app.screenshot import screenshot
        from sovs.app.session import SkirmishSession
        from sovs.ui.deck_editor_page import deck_revalidate
        from sovs.ui.shell_window import ShellWindow
        cls.session = SkirmishSession(seed=42)
        win = ShellWindow(cls.session, visible=False)
        ed = cls.session.deck_editor
        win._deck_catalog = ed.catalog()
        win.fsm.open_deck_edit({"deck_key": cls.session.human_deck,
                                "faction": "SOVIET",
                                "cards": ed.load_deck(cls.session.human_deck)["cards"],
                                "tab": "INFANTRY", "errors": []})
        deck_revalidate(win)
        win._layout_buttons()
        cls.tmp = tempfile.mkdtemp()
        cls.deck_shot = os.path.join(cls.tmp, "deck_edit.png")
        win.snapshot(cls.deck_shot)
        win.fsm.close_deck_edit()
        win.fsm.start_deploy()
        for _ in range(480):
            cls.session.advance(1)
        win.refresh()
        cls.deploy_shot = os.path.join(cls.tmp, "deploy.png")
        win.snapshot(cls.deploy_shot)
        win.close()

    def test_deck_pool_region_diff(self):
        from tools.qa_visual import diff_ratio
        # 卡池行缩略图带：x 84..140（行左 40px 框）、y 顶带向下 11 行
        ratio = diff_ratio(self.deck_shot, _BASE_DECK, (80, 70, 145, 420))
        self.assertGreaterEqual(ratio, 0.01,
                                "deck_edit 缩略图区 diff=%r" % ratio)

    def test_deploy_rail_region_diff(self):
        from tools.qa_visual import diff_ratio
        ratio = diff_ratio(self.deploy_shot, _BASE_DEPLOY, (8, 60, 230, 400))
        self.assertGreaterEqual(ratio, 0.01,
                                "deploy 呼援轨区 diff=%r" % ratio)


if __name__ == "__main__":
    unittest.main()
