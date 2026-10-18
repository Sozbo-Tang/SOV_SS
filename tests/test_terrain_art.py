"""R6 地形表现测试：底图产物/确定性/抽样语义/朝向；接入面（无头 mock）。
截图级断言（battle 非底色/minimap 色数/R5 diff/hero）由截图产物类承载。"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BASE = os.path.join(_ROOT, "assets", "fe", "terrain",
                     "bagration_field_base.png")
_MINI = os.path.join(_ROOT, "assets", "fe", "terrain",
                     "bagration_field_minimap.png")
_MAP_DOC = os.path.join(_ROOT, "data", "gen", "bagration_field.v1.json")
_SCENARIO_DOC = os.path.join(_ROOT, "data", "scenarios",
                             "bagration_field.json")

TILE = 32
NX, NY = 80, 40


def _tile_center_px(ix, iy):
    """瓦片中心像素（iy=0 最南→最下行；PNG 第 0 行=最北）。"""
    return (ix * TILE + TILE // 2, (NY - 1 - iy) * TILE + TILE // 2)


def _map_doc():
    return json.loads(open(_MAP_DOC, encoding="utf-8").read())


_MARKER = os.path.join(_ROOT, "assets", "fe", "terrain",
                       "bagration_field_base.source")


def _painted() -> bool:
    try:
        return open(_MARKER, encoding="utf-8").read().strip() == "img_gen"
    except OSError:
        return False


@unittest.skipUnless(HAS_PIL, "需 PIL（构建期栈）")
@unittest.skipIf(_painted(), "IMG-GEN 绘景底图：R6 程序化语义不适用")
class TestTerrainArtifacts(unittest.TestCase):

    def test_a_sizes_and_richness(self):
        base = Image.open(_BASE).convert("RGB")
        self.assertEqual(base.size, (2560, 1280))
        colors = base.getcolors(maxcolors=2_000_000)
        self.assertGreaterEqual(len(colors), 300, "颜色数 %d" % len(colors))
        px = list(base.resize((64, 32)).getdata())
        mean = tuple(sum(c[i] for c in px) // len(px) for i in range(3))
        self.assertGreater(sum(mean), 150, mean)              # 非全黑
        mini = Image.open(_MINI).convert("RGB")
        self.assertEqual(mini.size, (512, 256))

    def test_b_deterministic_rebuild(self):
        """重构建 sha256 一致＋gen_base 纯函数两次内存构建逐字节一致
        （seed=sha256(map_key) 确定性锁——进程内调用，无子进程）。"""
        before = hashlib.sha256(open(_BASE, "rb").read()).hexdigest()
        from tools import gen_terrain
        self.assertEqual(gen_terrain.main(), 0)
        after = hashlib.sha256(open(_BASE, "rb").read()).hexdigest()
        self.assertEqual(before, after)
        doc = _map_doc()
        decor = json.loads(open(_SCENARIO_DOC, encoding="utf-8").read())["decor"]
        b1, b2 = io.BytesIO(), io.BytesIO()
        gen_terrain.gen_base(doc, decor).save(b1, format="PNG")
        gen_terrain.gen_base(doc, decor).save(b2, format="PNG")
        self.assertEqual(b1.getvalue(), b2.getvalue())

    def test_c_tile_semantics_sampling(self):
        """抽样瓦片中心色语义：森林暗绿/道路土色/麦田金黄/溪流蓝灰/废墟灰褐。"""
        tiles = {(t[0], t[1]): t[2] for t in _map_doc()["tiles"]}
        base = Image.open(_BASE).convert("RGB")

        def px(ix, iy):
            return base.getpixel(_tile_center_px(ix, iy))

        forest = next((ix, iy) for (ix, iy), t in tiles.items() if t == 1)
        r, g, b = px(*forest)
        self.assertLess(r, 90, (forest, (r, g, b)))          # 暗绿
        self.assertGreater(g, r, (forest, (r, g, b)))
        road = next((ix, iy) for (ix, iy), t in tiles.items()
                    if t == 0 and iy in (18, 19, 20, 21))
        r, g, b = px(*road)
        self.assertGreater(r, 100, (road, (r, g, b)))        # 土色偏暖
        self.assertGreater(r, b, (road, (r, g, b)))
        ruin = next((ix, iy) for (ix, iy), t in tiles.items() if t == 2)
        r, g, b = px(*ruin)
        self.assertTrue(abs(r - g) < 30 and r < 140, (ruin, (r, g, b)))  # 灰褐
        r, g, b = px(24, 4)                                   # 麦田金黄
        self.assertGreater(r, 100, ((r, g, b)))
        self.assertGreater(r, b, ((r, g, b)))
        # 溪流：折线顶点 (80000,16000) 邻域 7×7 内存在蓝灰水色（b>r——
        # 顶点恰在线上，瓦片中心采样会漏 13px 线宽）
        vx = int(80000 * 32 / 2500)
        vy = int((100000 - 16000) * 32 / 2500)
        found_water = any(
            base.getpixel((vx + dx, vy + dy))[2] > base.getpixel((vx + dx,
                                                                 vy + dy))[0]
            for dx in range(-3, 4) for dy in range(-3, 4))
        self.assertTrue(found_water, "溪流顶点邻域无水色")

    def test_d_orientation_north_up(self):
        """最北森林格像素行 < 640（上半部——PNG 第 0 行=最北）。"""
        forests = [(t[0], t[1]) for t in _map_doc()["tiles"] if t[2] == 1]
        north_iy = max(iy for _, iy in forests)
        row = (NY - 1 - north_iy) * TILE
        self.assertLess(row, 640, "最北森林格行 %d ≥640（朝向翻转？）" % row)

    def test_e_village_yard_not_grass(self):
        """村庄场院色：目标 1 瓦片 (43,25) 非深绿草地（底图不画屋顶——
        屋顶由代码层画；此断言=场院/废墟灰褐色域）。"""
        base = Image.open(_BASE).convert("RGB")
        r, g, b = base.getpixel(_tile_center_px(43, 25))
        self.assertFalse(g > r + 10 and g < 90, ((r, g, b)))


@unittest.skipUnless(HAS_PIL, "需 PIL")
class TestTerrainWiring(unittest.TestCase):
    """接入面（无头）：资产 API/建筑元数据/绘制面不抛（mock arcade）。"""

    def test_assets_apis(self):
        from sovs.ui import assets
        t = assets.terrain_map_tex("bagration_field")
        self.assertIsNotNone(t)
        self.assertEqual(t.size, (2560, 1280))
        m = assets.terrain_minimap_tex("bagration_field")
        self.assertEqual(m.size, (512, 256))
        self.assertIsNone(assets.terrain_map_tex("__nope__"))
        meta = assets.map_meta("bagration_field")
        self.assertEqual(len(meta["buildings"]), 8)
        self.assertEqual(meta["extent"], (200000, 100000))

    def test_buildings_draw_no_throw(self):
        import unittest.mock as mock
        from types import SimpleNamespace
        from sovs.ui import scene
        from sovs.app.session import SkirmishSession
        s = SkirmishSession(seed=42)
        win = SimpleNamespace(frame=s.frame(), session=s, cam_scale=0.012,
                              cam_cx=108000, cam_cy=64000, width=1600,
                              height=900,
                              fsm=SimpleNamespace(page="battle"))
        win.cm_to_px = lambda x, y: scene.cm_to_px(win, x, y)
        with mock.patch.object(scene, "arcade"):
            scene.draw_buildings(win)
            scene.draw_stream_bridge(win)
            scene.draw_terrain_base(win)

    def test_scenario_config_line_updated(self):
        """R6 §1-1：config 胜利裁决末行=三要点（源锚）。"""
        src = open(os.path.join(_ROOT, "sovs", "ui", "deck_editor_page.py"),
                   encoding="utf-8").read()
        self.assertIn("目标：夺取三处要点（村庄/十字路口/集体农庄）", src)
        self.assertNotIn("目标：中央占点（2km 图心）", src)


if __name__ == "__main__":
    unittest.main()
