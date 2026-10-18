"""FE-05 F6 视线测试：los_probe 四例（可见/树后/楼后/超程）＋敌方未知 None
＋帧契约；ALT 事件与绘制面（GL 类）；AST 守卫。"""
from __future__ import annotations

import ast
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

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _session_with_own_unit():
    from sovs.app.scripts import ScriptedPilot
    from sovs.app.session import SkirmishSession
    session = SkirmishSession(seed=42)
    pilot = ScriptedPilot(session)
    for _ in range(80):
        pilot.step()
        session.advance(1)
    return session


def _find_forest_pair(world, unit_optics_cm):
    """在演示图上找 (起点, 目标)：直线穿 ≥4 森林格、起点不在林内、目标距离
    在光学范围内且衰减后必遮断（forest_m ≥ 100）。"""
    from sovs.sim.sensing import (forest_m_between, in_forest_at)
    tiles = world.forest_tiles
    tile_cm = world.terrain.tile_cm
    rng = unit_optics_cm
    for sx in range(5000, 195000, 10000):
        for sy in range(5000, 95000, 10000):
            a = (sx, sy)
            if in_forest_at(tiles, tile_cm, a):
                continue
            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1), (-1, 1)):
                b = (sx + dx * rng * 3 // 5, sy + dy * rng * 3 // 5)
                if not (0 <= b[0] < 200000 and 0 <= b[1] < 100000):
                    continue
                if forest_m_between(tiles, tile_cm, a, b) >= 100:
                    return a, b
    return None, None


class TestLosProbe(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.session = _session_with_own_unit()
        cls.unit = next(u for u in cls.session.world.units
                        if u.team == 0 and u.alive)

    def test_visible_open_ground(self):
        u = self.unit
        old = u.pos
        u.pos = (20000, 20000)                       # 开阔地（非林格）
        try:
            res = self.session.los_probe(u.id, (25000, 22000))
        finally:
            u.pos = old
        self.assertIsNotNone(res)
        self.assertTrue(res["visible"])
        self.assertFalse(res["blocked"])
        self.assertIsNone(res["reason"])
        self.assertEqual(res["range_cm"], u.template.optics_ground_cm)

    def test_behind_forest_blocks(self):
        a, b = _find_forest_pair(self.session.world,
                                 self.unit.template.optics_ground_cm)
        if a is None:
            self.skipTest("演示图未找到 ≥4 格直线穿林样例")
        old = self.unit.pos
        self.unit.pos = a
        try:
            res = self.session.los_probe(self.unit.id, b)
        finally:
            self.unit.pos = old
        self.assertIsNotNone(res)
        self.assertFalse(res["visible"])
        self.assertTrue(res["blocked"])
        self.assertEqual(res["reason"], "terrain")

    def test_behind_building_blocks(self):
        w = self.session.world
        self.assertTrue(w.buildings)
        b = next(x for x in w.buildings if x.hp > 0)
        d = 6000                                      # 楼两侧 60m 共线
        a = (b.pos[0] - d, b.pos[1])
        t = (b.pos[0] + d, b.pos[1])
        old = self.unit.pos
        self.unit.pos = a
        try:
            res = self.session.los_probe(self.unit.id, t)
        finally:
            self.unit.pos = old
        self.assertIsNotNone(res)
        self.assertTrue(res["blocked"])
        self.assertEqual(res["reason"], "terrain")

    def test_out_of_range(self):
        res = self.session.los_probe(self.unit.id, (199999, 99999))
        self.assertIsNotNone(res)
        self.assertFalse(res["visible"])
        self.assertTrue(res["blocked"])
        self.assertEqual(res["reason"], "range")

    def test_enemy_or_unknown_returns_none(self):
        foe = next(u for u in self.session.world.units
                   if u.team != 0 and u.alive)
        self.assertIsNone(self.session.los_probe(foe.id, (50000, 50000)))
        self.assertIsNone(self.session.los_probe(999999, (50000, 50000)))


class TestLosOverlayAst(unittest.TestCase):

    def test_los_overlay_no_sim_no_pil(self):
        src = open(os.path.join(_ROOT, "sovs", "ui", "los_overlay.py"),
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

    def test_los_active_gate(self):
        from types import SimpleNamespace
        from sovs.ui.los_overlay import los_active
        from sovs.ui.shell_fsm import ShellFsm
        fsm = ShellFsm()
        fsm.page = "battle"
        fsm.selected = [1]
        win = SimpleNamespace(fsm=fsm)
        self.assertFalse(los_active(win))            # 未按 ALT
        win._los_hold = True
        self.assertTrue(los_active(win))
        fsm.selected = []
        self.assertFalse(los_active(win))            # 切页/清选区消隐
        fsm.selected = [1]
        fsm.page = "config"
        self.assertFalse(los_active(win))


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestLosAltEvents(unittest.TestCase):
    """ALT 按下/松开事件链＋绘制面烟测（真实事件层）。"""

    @classmethod
    def setUpClass(cls):
        from sovs.app.scripts import ScriptedPilot
        from sovs.app.session import SkirmishSession
        from sovs.ui.shell_window import ShellWindow
        cls.session = SkirmishSession(seed=42)
        cls.pilot = ScriptedPilot(cls.session)
        cls.win = ShellWindow(cls.session, visible=False)
        cls.win.fsm.start_deploy()
        for _ in range(80):
            cls.pilot.step()
            cls.session.advance(1)
        cls.win.refresh()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def test_alt_press_release_and_draw(self):
        mine = [u for u in self.win.frame["units"] if u["team"] == 0]
        self.assertTrue(mine)
        self.win.fsm.select_units([mine[0]["id"]])
        self.win._mouse_xy = (640, 400)
        self.win.on_key_press(arcade.key.LALT, 0)
        self.assertTrue(self.win._los_hold)
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "los_probe.png")
            self.win.snapshot(path)                  # 绘制面不抛
            from PIL import Image
            img = Image.open(path).convert("RGB")
            self.assertGreater(
                len(img.getcolors(maxcolors=1_000_000)), 8)
        self.win.on_key_release(arcade.key.LALT, 0)
        self.assertFalse(self.win._los_hold)
        self.win.on_key_press(arcade.key.RALT, 0)
        self.assertTrue(self.win._los_hold)
        self.win.on_key_press(arcade.key.ESCAPE, 0)  # ESC 分层取消含视线
        self.assertFalse(self.win._los_hold)


if __name__ == "__main__":
    unittest.main()
