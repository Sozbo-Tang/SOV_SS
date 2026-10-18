"""FE-05 F0 资产基建测试：asset_index 完整性 / assets.py 查询与回退 / 九宫格。

门禁面：①索引规模（units 67/air 10/orders 39/ui≥50/missing 空）；②全部
path 落盘非空；③load 缺文件 None；④unit/air/order/ui 查询命中与未命中；
⑤索引构建确定性（两次字节一致＋磁盘同步）；⑥draw_nine_patch 双档不抛
（需 GL 隐藏窗）；⑦AST 守卫（assets.py 禁 sovs.sim/sovs.ai/PIL）。
"""
from __future__ import annotations

import ast
import json
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


class TestAssetIndex(unittest.TestCase):
    """data/gen/asset_index.json 规模与路径完整性（构建器产物）。"""

    def test_index_complete_units_air_orders_ui(self):
        from sovs.ui import assets
        idx = assets.index()
        self.assertEqual(len(idx["units"]), 67)
        self.assertEqual(len(idx["air"]), 10)
        self.assertEqual(len(idx["orders"]), 39)
        self.assertGreaterEqual(len(idx["ui"]), 50)
        self.assertEqual(idx["missing"], [])

    def test_all_paths_exist_nonempty(self):
        from sovs.ui import assets
        idx = assets.index()
        paths = []
        for section in ("units", "air"):
            paths += [e["path"] for e in idx[section].values()]
        for section in ("orders", "ui", "settle", "cursor", "terrain",
                        "bg", "objectives"):
            paths += list(idx[section].values())
        self.assertGreater(len(paths), 150)
        for p in paths:
            self.assertTrue(p.startswith("assets/fe/"), p)
            self.assertNotIn("\\", p)
            full = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), p)
            self.assertTrue(os.path.isfile(full), "缺文件：%s" % p)
            self.assertGreater(os.path.getsize(full), 0, "空文件：%s" % p)

    def test_index_build_deterministic_and_disk_synced(self):
        from tools.build_asset_index import build_index, main
        self.assertEqual(main(), 0)                    # 落盘（幂等）
        a = json.dumps(build_index(), sort_keys=True, ensure_ascii=False,
                       indent=1) + "\n"
        b = json.dumps(build_index(), sort_keys=True, ensure_ascii=False,
                       indent=1) + "\n"
        self.assertEqual(a, b)                          # 两次生成字节一致
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "data", "gen", "asset_index.json"),
                  encoding="utf-8") as f:
            self.assertEqual(f.read(), a)               # 磁盘与构建同步
        self.assertTrue(a.endswith("}\n"))              # 末尾单 LF


class TestAssetsQueries(unittest.TestCase):
    """sovs/ui/assets.py 查询命中/未命中与缺文件回退（无需 GL——load 纯加载）。"""

    def test_load_missing_returns_none(self):
        from sovs.ui import assets
        self.assertIsNone(assets.load("assets/fe/units/__nope__.png"))
        self.assertIsNone(assets.load(""))

    def test_lookup_hits_and_misses(self):
        from sovs.ui import assets
        self.assertIsNotNone(assets.unit_tex("SU_RIFLE"))
        self.assertIsNone(assets.unit_tex("__NOPE__"))
        self.assertIsNotNone(assets.unit_tex_by_id(101))    # SU_RECON
        self.assertIsNone(assets.unit_tex_by_id(999999))
        self.assertIsNotNone(assets.air_tex(1))             # PO2（苏 1~5）
        self.assertIsNone(assets.air_tex(999999))
        self.assertIsNotNone(assets.order_tex("attack"))
        self.assertIsNotNone(assets.order_tex("sup_ammo"))
        self.assertIsNone(assets.order_tex("__nope__"))
        self.assertIsNotNone(assets.ui_tex("panel_topbar"))
        self.assertIsNotNone(assets.ui_tex("cmd_tile"))
        self.assertIsNotNone(assets.settle_tex("badge_victory"))
        self.assertIsNotNone(assets.cursor_tex("cur_default"))
        self.assertIsNotNone(assets.bg_tex("bg_mainmenu"))
        self.assertIsNotNone(assets.terrain_tex("minimap_terrain"))
        self.assertIsNotNone(assets.objective_tex("obj_flag_red"))

    def test_ast_no_sim_no_pil(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "sovs", "ui", "assets.py"),
                   encoding="utf-8").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                tops = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                tops = {node.module.split(".")[0]}
            else:
                continue
            self.assertNotIn("PIL", tops)
            self.assertNotIn("sovs", tops)


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestNinePatchDrawing(unittest.TestCase):
    """draw_nine_patch 双档不抛（GL 隐藏窗承载上下文）。"""

    @classmethod
    def setUpClass(cls):
        import arcade
        cls.win = arcade.Window(640, 200, "test-ninepatch", visible=False)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def test_two_rect_sizes_no_throw(self):
        import arcade
        from sovs.ui import assets
        self.assertIsNone(assets.draw_nine_patch((0, 0, 40, 40), None))
        tex = assets.ui_tex("panel_topbar")
        if tex is None:                                # 皮肤缺图=环境异常，跳过
            self.skipTest("panel_topbar 皮肤缺失")
        self.win.switch_to()                             # 隐藏窗 GL 上下文置当前
        self.win.clear()
        assets.draw_nine_patch((10, 80, 50, 120), tex)     # 40×40 退化档
        assets.draw_nine_patch((0, 10, 1280, 66), tex)     # 顶栏档
        assets.draw_nine_patch((0, 140, 640, 200), tex, corner=16)
        self.win.flip()


if __name__ == "__main__":
    unittest.main()
