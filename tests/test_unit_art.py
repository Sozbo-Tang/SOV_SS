"""FE-05 F1 单位贴图测试：帧 template_id 键 / 67+10 全映射 / 回退不抛 /
mock 尺寸断言 / battle.png 单位区基线差分（≥0.02——贴图相对字形的实变化）。
"""
from __future__ import annotations

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


class TestFrameTemplateId(unittest.TestCase):
    """帧契约：units 条目带 template_id 且与 world 模板一致（加键不 bump）。"""

    def test_frame_units_have_template_id(self):
        from sovs.app.scripts import ScriptedPilot
        from sovs.app.session import SkirmishSession
        session = SkirmishSession(seed=42)
        pilot = ScriptedPilot(session)
        for _ in range(80):                     # 部署期购卡出牌（screenshot 同款）
            pilot.step()
            session.advance(1)
        frame = session.frame()
        self.assertTrue(frame["units"])
        by_id = {u.id: u for u in session.world.units}
        for entry in frame["units"]:
            self.assertIn("template_id", entry)
            self.assertEqual(entry["template_id"],
                             by_id[entry["id"]].template.template_id)


class TestFullMapping(unittest.TestCase):
    """67 地面 + 10 航空全映射（贴图加载无需 GL）。"""

    def test_all_templates_have_texture(self):
        from sovs.ui import assets
        idx = assets.index()
        self.assertEqual(len(idx["units"]), 67)
        self.assertEqual(len(idx["air"]), 10)
        for tid in idx["units"]:
            self.assertIsNotNone(assets.unit_tex_by_id(int(tid)), tid)
        for tid in idx["air"]:
            self.assertIsNotNone(assets.air_tex(int(tid)), tid)
        for name in ("overlay_selected", "overlay_moving",
                     "overlay_suppressed", "hp_bar"):
            self.assertIsNotNone(assets.overlay_tex(name))


def _duck_u(**over):
    u = {"id": 7, "template_id": 101, "team": 0, "category": 1,
         "hp": 8, "hp_max": 10, "suppressed": False, "moving": False}
    u.update(over)
    return u


class TestDrawMocked(unittest.TestCase):
    """mock draw_texture_rect：真模板=48px 贴图路径；伪模板=字形回退零贴图。"""

    def _win(self):
        win = mock.MagicMock()
        win.fsm.selected = ()
        win.cam_rot = 0.0
        return win

    def test_ground_texture_48px_called(self):
        from sovs.ui import unit_render
        with mock.patch.object(unit_render.arcade, "draw_texture_rect") as dt, \
                mock.patch.object(unit_render, "draw_unit_glyph") as glyph, \
                mock.patch.object(unit_render, "draw_nameplate"):
            unit_render.draw_ground_unit(self._win(), _duck_u(), 100.0, 200.0)
        self.assertTrue(dt.called)
        sizes = [(r.width, r.height) for (_, r), _ in
                 [(c.args, c) for c in dt.call_args_list
                  if len(c.args) >= 2 and hasattr(c.args[1], "width")]]
        self.assertIn((48, 48), sizes)               # 本体 48px（54 底衬并存）
        self.assertFalse(glyph.called)               # 有图不走回退

    def test_ground_fake_template_falls_back(self):
        from sovs.ui import unit_render
        with mock.patch.object(unit_render.arcade, "draw_texture_rect") as dt, \
                mock.patch.object(unit_render, "draw_unit_glyph") as glyph, \
                mock.patch.object(unit_render, "draw_nameplate"):
            unit_render.draw_ground_unit(self._win(),
                                         _duck_u(template_id=999999),
                                         100.0, 200.0)
        self.assertFalse(dt.called)                  # 零贴图调用
        self.assertTrue(glyph.called)                # 字形回退在场

    def test_air_texture_and_fallback(self):
        from sovs.ui import unit_render
        air = {"id": 3, "template_id": 1, "team": 0, "alt_tier": "mid",
               "spotted": False, "facing": 90}
        with mock.patch.object(unit_render.arcade, "draw_texture_rect") as dt, \
                mock.patch.object(unit_render, "draw_aircraft_glyph") as glyph:
            unit_render.draw_air_unit(self._win(), air, 50.0, 60.0)
        self.assertTrue(dt.called)
        self.assertEqual(dt.call_args_list[0].args[1].width, 40)
        self.assertFalse(glyph.called)
        with mock.patch.object(unit_render.arcade, "draw_texture_rect") as dt, \
                mock.patch.object(unit_render, "draw_aircraft_glyph") as glyph:
            unit_render.draw_air_unit(self._win(),
                                      dict(air, template_id=999999),
                                      50.0, 60.0)
        self.assertFalse(dt.called)
        self.assertTrue(glyph.called)


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestBattleUnitRegionDiff(unittest.TestCase):
    """battle 页实渲染 vs F0 基线：单位区 (560,380,860,700) diff ≥0.02。"""

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
        while cls.session.world.tick < 2165:         # screenshot battle 同款
            cls.pilot.step()
            cls.session.advance(1)
        cls.win.refresh()
        mine = [u for u in cls.win.frame["units"] if u["team"] == 0]
        cls.win.fsm.clear_selection()
        anchor = mine[0]["pos_cm"]
        x0, y0 = cls.win.cm_to_px(anchor[0] - 4000, anchor[1] - 4000)
        x1, y1 = cls.win.cm_to_px(anchor[0] + 4000, anchor[1] + 4000)
        cls.win.select_box_px(x0, y0, x1, y1)
        cls.session.cmd.move(list(cls.win.fsm.selected), (100000, 50000))
        cls.tmp = tempfile.mkdtemp()
        cls.shot = os.path.join(cls.tmp, "battle.png")
        cls.win.snapshot(cls.shot)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def test_unit_region_changed_vs_baseline(self):
        from tools.qa_visual import diff_ratio
        ratio = diff_ratio(self.shot, _BASELINE, (560, 380, 860, 700))
        self.assertGreaterEqual(ratio, 0.02, "单位区 diff=%r 未达 0.02" % ratio)


if __name__ == "__main__":
    unittest.main()
