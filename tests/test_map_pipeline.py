"""地形图数据管线端到端测试（PB-58 块②，2026-10-06）。

覆盖面：
  - 构建原语手推锚（Bresenham 整型线/方形笔刷偏移/画家后绘覆盖）；
  - CSV 层构建门（行类型/未用列留空/越界/整除/公式注入/float 文本/verts 结构……
    ——tools/build_map.py fail-fast，照 test_card_pipeline.IllegalAtBuildTime 范式）；
  - 仓库工件确定性（提交 JSON==重构建字节、双构建字节稳定、瓦片 int 表示、
    源 sha256==CSV 实际哈希、瓦片类型计数指纹）；
  - loader 门（版本门/float/bool/越界/重复/类型域/hp=0——card_loader.LoaderGates
    范式；SUPPORTED_MAP_SCHEMA 与 build_map.SCHEMA_VERSION 双写锁死互检）；
  - 三类瓦片×三谓词（ROAD=on_road 零注入/FOREST=旁挂不入 tiles 恒等旷野/
    RUIN=四类同值 cfg.ruin_speed_bp 注入）＋ apply_map 挂点对齐；
  - 示范图真实寻路：V2 横带废墟三类别全绕行（航点重走零废墟格+独立 Dijkstra
    最优仲裁）；V1 穿村对比查询（WHEEL 直穿废墟 vs FOOT 绕行——类别分档可观测）；
    prefer_road 真上路（59/70 格）；SOUTH 部署锚点可通行护栏；零掷骰。

Dijkstra/航点重走助手为 test_pathfinding.py:300-354 同款测试侧独立仲裁
（与实现无共享代码路径）。
"""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from sovs.sim import map_loader as ml
from sovs.sim.combat import hit_building
from sovs.sim.pathfind import DIR8, find_path, tile_cost
from sovs.sim.tables import CONFIG
from sovs.sim.tick import make_world
from sovs.sim.types import Building, MovementClass
from tools import build_map as bm

REPO_DATA = Path(__file__).resolve().parents[1] / "data"
COMMITTED_JSON = REPO_DATA / "gen" / "map_demo_2km.v1.json"
MAP_CSV = REPO_DATA / "map_demo_2km.csv"

FOOT, WHEEL, TRACK, HORSE = (MovementClass.FOOT, MovementClass.WHEEL,
                             MovementClass.TRACK, MovementClass.HORSE)

# 示范图图幅/瓦片锚（B 图幅=200000×100000、tile 2500 → 80×40 格）
NX, NY = 80, 40
TC = 2500


def tc_center(ix, iy):
    """瓦片中心 cm 坐标（find_path 航点口径）。"""
    return (ix * TC + TC // 2, iy * TC + TC // 2)


# ── 测试侧独立仲裁助手（test_pathfinding.py 同款，无共享代码路径）──

def route_tiles(w, cls, pref, frm, waypoints):
    """沿返回航点逐格重走收集途经格（DIR8 对齐段）。"""
    t = w.terrain.tile_cm
    cur = (frm[0] // t, frm[1] // t)
    seen = []
    for wp in waypoints:
        nxt = (wp[0] // t, wp[1] // t)
        while cur != nxt:
            dx = (nxt[0] > cur[0]) - (nxt[0] < cur[0])
            dy = (nxt[1] > cur[1]) - (nxt[1] < cur[1])
            cur = (cur[0] + dx, cur[1] + dy)
            seen.append(cur)
    return seen


def route_cost(w, cls, pref, frm, waypoints):
    """独立代价核算：逐入格累加 tile_cost（对角步 ×14142//10000 与实现同式）。"""
    layer = w.terrain
    t = layer.tile_cm
    cur = (frm[0] // t, frm[1] // t)
    total = 0
    for wp in waypoints:
        nxt = (wp[0] // t, wp[1] // t)
        while cur != nxt:
            dx = (nxt[0] > cur[0]) - (nxt[0] < cur[0])
            dy = (nxt[1] > cur[1]) - (nxt[1] < cur[1])
            cur = (cur[0] + dx, cur[1] + dy)
            c = tile_cost(w, layer, CONFIG, cur[0], cur[1], cls, pref)
            total += c if (dx == 0 or dy == 0) \
                else c * CONFIG.pathfind_diag_cost_bp // 10000
    return total


def dijkstra_cost(w, cls, pref, frm, to):
    """独立最优性仲裁：测试内 Dijkstra（同代价模型：入格代价/对角乘子/禁切角/图界）。"""
    import heapq
    layer = w.terrain
    t = layer.tile_cm
    ext = w.map_extent
    nx_max, ny_max = (ext[0] + t - 1) // t, (ext[1] + t - 1) // t
    start = (frm[0] // t, frm[1] // t)
    goal = (to[0] // t, to[1] // t)
    g = {start: 0}
    heap = [(0, 0, start)]
    done = set()
    while heap:
        _f, _s, node = heapq.heappop(heap)
        if node in done:
            continue
        done.add(node)
        if node == goal:
            return g[node]
        x0, y0 = node
        for dx, dy in DIR8:
            if dx != 0 and dy != 0:
                if (tile_cost(w, layer, CONFIG, x0 + dx, y0, cls, pref) is None
                        or tile_cost(w, layer, CONFIG, x0, y0 + dy, cls, pref) is None):
                    continue
            c = tile_cost(w, layer, CONFIG, x0 + dx, y0 + dy, cls, pref)
            if c is None or not (0 <= x0 + dx < nx_max and 0 <= y0 + dy < ny_max):
                continue
            step = c if (dx == 0 or dy == 0) \
                else c * CONFIG.pathfind_diag_cost_bp // 10000
            ng = g[node] + step
            if ng < g.get((x0 + dx, y0 + dy), 1 << 62):
                g[(x0 + dx, y0 + dy)] = ng
                heapq.heappush(heap, (ng, 0, (x0 + dx, y0 + dy)))
    return None


def demo_world(seed=7):
    """加载正式示范图并挂载（apply_map 挂点=块③整局接入同一路径）。"""
    md = ml.load_demo_map()
    w = make_world(seed, size_cm=(999999, 999999))   # 故意错图幅——挂点负责对齐
    ml.apply_map(w, md)
    return w, md


def is_ruin(md, tile):
    t = md.layer.tiles.get(tile)
    return t is not None and bool(t.speed_bp)


def is_road(md, tile):
    t = md.layer.tiles.get(tile)
    return t is not None and t.on_road


# ── CSV 写入助手（合法最小集 + 单点变异——test_card_pipeline 范式）──

COLS = list(bm.COLUMNS)


def write_map_csv(path, rows):
    # 2026-10-07：写入改 Path.write_text（等价换写——utf-8-sig BOM+\n 行尾字节不变；
    # 原 open(path,"w") 写模式变量路径为 Mimosa 路径穿越规则 sink，夹具写点收口）
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in COLS})
    Path(path).write_text(buf.getvalue(), encoding="utf-8-sig", newline="")


def legal_rows():
    """合法最小集：4×2 格小图（10000×5000/tile 2500）+ 林矩形 + 路折线 + 建筑行。"""
    return [
        {"kind": "map", "map_key": "t", "extent_x_cm": "10000",
         "extent_y_cm": "5000", "tile_cm": "2500"},
        {"kind": "rect", "type": "FOREST", "x0": "1", "y0": "1",
         "x1": "2", "y1": "1"},
        {"kind": "polyline", "type": "ROAD", "width": "1",
         "verts": "0:0;3:1"},
        {"kind": "building", "building_key": "B1", "x_cm": "1250",
         "y_cm": "1250", "footprint_cm": "2500", "hp": "100"},
    ]


class TestRasterizerPrimitives(unittest.TestCase):
    """构建原语手推锚（纯整数 Bresenham/笔刷偏移/画家序）。"""

    def test_bresenham_axis_lines(self):
        self.assertEqual(bm.line_tiles((0, 0), (4, 0)),
                         [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)])
        self.assertEqual(bm.line_tiles((2, 1), (2, 3)),
                         [(2, 1), (2, 2), (2, 3)])

    def test_bresenham_diagonal(self):
        self.assertEqual(bm.line_tiles((0, 0), (3, 3)),
                         [(0, 0), (1, 1), (2, 2), (3, 3)])

    def test_bresenham_shallow_slope_hand_traced(self):
        # (0,0)→(4,2) 手推：dx=4 dy=−2 err=2 → (1,1)(2,1)(3,2)(4,2)
        # （逐步 err=2→0/4→2→0/4→2；e2=4 与 dx=4 的 ≤ 判定两次双步）
        self.assertEqual(bm.line_tiles((0, 0), (4, 2)),
                         [(0, 0), (1, 1), (2, 1), (3, 2), (4, 2)])

    def test_bresenham_reverse_direction_pinned(self):
        # 标准整型 Bresenham 的中点取整方向随行进向翻转——反向浅斜率格子集与
        # 正向不对称（正向经 (1,1)/(3,2)，反向经 (1,0)/(3,1)）：逐方向确定性成立
        # （verts 声明序即栅格化序——CSV 冻结），非集合对称。反向手推：
        self.assertEqual(bm.line_tiles((4, 2), (0, 0)),
                         [(4, 2), (3, 1), (2, 1), (1, 0), (0, 0)])

    def test_brush_offsets(self):
        self.assertEqual(bm.brush_offsets(1), (0,))
        self.assertEqual(bm.brush_offsets(2), (0, 1))
        self.assertEqual(bm.brush_offsets(3), (-1, 0, 1))
        self.assertEqual(bm.brush_offsets(4), (-1, 0, 1, 2))

    def test_painter_later_overwrites(self):
        # 4×2 图：先林后路 → 交叠格成路（穿林车道）；先路后林 → 交叠格成林
        def full(rows):                     # 补全 17 列（parse_rows 吃全列 dict）
            return [{c: r.get(c, "") for c in COLS} for r in rows]

        base_map = {"kind": "map", "map_key": "t", "extent_x_cm": "10000",
                    "extent_y_cm": "5000", "tile_cm": "2500"}
        decl = bm.parse_rows(full([
            base_map,
            {"kind": "rect", "type": "FOREST", "x0": "0", "y0": "0",
             "x1": "3", "y1": "1"},
            {"kind": "rect", "type": "ROAD", "x0": "1", "y0": "0",
             "x1": "2", "y1": "1"},
        ]))
        canvas = bm.rasterize(decl, 4, 2)
        self.assertEqual(canvas[(1, 0)], bm.TYPE_TOKEN["ROAD"])
        self.assertEqual(canvas[(0, 0)], bm.TYPE_TOKEN["FOREST"])
        decl2 = bm.parse_rows(full([
            base_map,
            {"kind": "rect", "type": "ROAD", "x0": "0", "y0": "0",
             "x1": "3", "y1": "1"},
            {"kind": "rect", "type": "FOREST", "x0": "1", "y0": "0",
             "x1": "2", "y1": "1"},
        ]))
        canvas2 = bm.rasterize(decl2, 4, 2)
        self.assertEqual(canvas2[(1, 0)], bm.TYPE_TOKEN["FOREST"])   # 后绘林覆盖路
        self.assertEqual(canvas2[(0, 0)], bm.TYPE_TOKEN["ROAD"])


class TestBuildGates(unittest.TestCase):
    """CSV 层构建门（fail-fast——非法数据不落产物）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _build(self, rows):
        write_map_csv(self.data / bm.MAP_CSV_NAME, rows)
        return bm.build_map(self.data, self.root / "gen")

    def _fail(self, rows, needle):
        with self.assertRaises(ValueError) as ctx:
            self._build(rows)
        self.assertIn(needle, str(ctx.exception))

    def test_legal_minimal_builds(self):
        out = self._build(legal_rows())
        self.assertTrue(out.is_file())

    def test_unknown_kind_rejected(self):
        rows = legal_rows() + [{"kind": "hexagon", "type": "FOREST",
                                "x0": "0", "y0": "0", "x1": "1", "y1": "1"}]
        self._fail(rows, "kind")

    def test_missing_map_row_rejected(self):
        rows = legal_rows()[1:]
        self._fail(rows, "map 行")

    def test_duplicate_map_row_rejected(self):
        rows = legal_rows() + [legal_rows()[0]]
        self._fail(rows, "重复")

    def test_unused_column_nonempty_rejected(self):
        rows = legal_rows()
        rows[1]["width"] = "2"          # rect 行不使用 width 列
        self._fail(rows, "未用列")

    def test_unknown_column_rejected(self):
        path = self.data / bm.MAP_CSV_NAME
        path.write_text(                      # 2026-10-07：同上 write_text 等价换写
            ",".join(COLS + ["zzz"]) + "\nmap,t,10000,5000,2500,,,,,,,,,,,,,\n",
            encoding="utf-8-sig", newline="")
        with self.assertRaises(ValueError) as ctx:
            bm.build_map(self.data, self.root / "gen")
        self.assertIn("未知列", str(ctx.exception))

    def test_float_coord_rejected(self):
        rows = legal_rows()
        rows[1]["x1"] = "2.5"
        self._fail(rows, "x1")

    def test_rect_out_of_bounds_rejected(self):
        rows = legal_rows()
        rows[1]["x1"] = "4"             # 图内域 [0..3]
        self._fail(rows, "越界")

    def test_rect_corner_order_rejected(self):
        rows = legal_rows()
        rows[1].update(x0="2", y0="1", x1="1", y1="0")
        self._fail(rows, "角点逆序")

    def test_extent_not_divisible_rejected(self):
        rows = legal_rows()
        rows[0]["extent_x_cm"] = "11000"
        self._fail(rows, "整除")

    def test_verts_single_point_rejected(self):
        rows = legal_rows()
        rows[2]["verts"] = "0:0"
        self._fail(rows, "≥2 顶点")

    def test_verts_malformed_rejected(self):
        rows = legal_rows()
        rows[2]["verts"] = "0:0;1"      # 缺 y 段
        self._fail(rows, "x:y")

    def test_verts_consecutive_duplicate_rejected(self):
        rows = legal_rows()
        rows[2]["verts"] = "0:0;0:0;3:1"
        self._fail(rows, "连续重复顶点")

    def test_verts_out_of_bounds_rejected(self):
        rows = legal_rows()
        rows[2]["verts"] = "0:0;4:0"    # ix=4 越界（图内 [0..3]）
        self._fail(rows, "越界")

    def test_width_zero_rejected(self):
        rows = legal_rows()
        rows[2]["width"] = "0"
        self._fail(rows, "width")

    def test_formula_prefix_rejected(self):
        rows = legal_rows()
        rows[3]["building_key"] = "=CMD()"
        self._fail(rows, "公式注入")

    def test_bad_type_token_rejected(self):
        rows = legal_rows()
        rows[1]["type"] = "WATER"
        self._fail(rows, "令牌集")

    def test_building_hp_zero_rejected(self):
        rows = legal_rows()
        rows[3]["hp"] = "0"             # combat.hit_building：hp<=0 即塌
        self._fail(rows, "hp 须 ≥1")

    def test_building_dup_key_rejected(self):
        rows = legal_rows() + [dict(legal_rows()[3])]
        self._fail(rows, "重复")

    def test_building_out_of_bounds_rejected(self):
        rows = legal_rows()
        rows[3]["x_cm"] = "10000"
        self._fail(rows, "越界")


class TestBuildArtifacts(unittest.TestCase):
    """仓库工件确定性：提交 JSON==重构建、双构建字节稳定、int 表示、源指纹。"""

    def test_committed_json_matches_rebuild(self):
        """防手改漂移：仓库 gen JSON 必须恰等于从提交 CSV 重构建的字节。"""
        with tempfile.TemporaryDirectory() as tmp:
            out = bm.build_map(REPO_DATA, Path(tmp))
            self.assertEqual(COMMITTED_JSON.read_bytes(), out.read_bytes())

    def test_build_byte_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = bm.build_map(REPO_DATA, Path(tmp) / "a")
            b = bm.build_map(REPO_DATA, Path(tmp) / "b")
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_cli_zero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                bm.main(["--data-dir", str(REPO_DATA), "--out-dir", tmp]), 0)

    def test_json_shape_and_source_fingerprint(self):
        import hashlib
        doc = json.loads(COMMITTED_JSON.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], bm.SCHEMA_VERSION)
        self.assertEqual(doc["map_key"], "demo_2km")
        self.assertEqual((doc["extent_x_cm"], doc["extent_y_cm"], doc["tile_cm"]),
                         (200000, 100000, 2500))          # B 图幅（DATA-02 §2）
        self.assertEqual(doc["source_sha256"],
                         hashlib.sha256(MAP_CSV.read_bytes()).hexdigest())
        self.assertEqual(len(doc["source_sha256"]), 64)
        # int 表示门：瓦片三元组全 int（拒 float/bool）、类型域 {0,1,2}、排序唯一
        coords = []
        for entry in doc["tiles"]:
            self.assertEqual([type(v) for v in entry], [int, int, int])
            self.assertIn(entry[2], (0, 1, 2))
            coords.append((entry[0], entry[1]))
        self.assertEqual(coords, sorted(coords))
        self.assertEqual(len(coords), len(set(coords)))
        # 图幅闭合：全部瓦片在 80×40 图内
        self.assertTrue(all(0 <= ix < NX and 0 <= iy < NY for ix, iy in coords))
        # 瓦片类型计数指纹（冻结示范图内容锚——改动 CSV 须连同此锚有意更新）
        from collections import Counter
        counts = Counter(e[2] for e in doc["tiles"])
        self.assertEqual(dict(counts), {0: 213, 1: 648, 2: 256})
        self.assertEqual([b["building_key"] for b in doc["buildings"]],
                         ["V1_HOUSE_A", "V1_HOUSE_B", "V2_HOUSE_A",
                          "V2_HOUSE_B", "V3_HOUSE_A"])


class TestLoaderGates(unittest.TestCase):
    """加载器门（结构/类型/图界/重复/枚举域——card_loader.LoaderGates 范式）。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.doc = json.loads(COMMITTED_JSON.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _mutated(self, mutate) -> Path:
        import copy
        doc = copy.deepcopy(self.doc)
        mutate(doc)
        path = Path(self._tmp.name) / "mutated.json"
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return path

    def test_committed_json_loads(self):
        md = ml.load_map(COMMITTED_JSON)
        self.assertEqual(md.map_key, "demo_2km")

    def test_version_gate_major(self):
        path = self._mutated(lambda d: d.update(schema_version="2.0"))
        with self.assertRaises(ml.MapLoaderError):
            ml.load_map(path)

    def test_version_gate_minor(self):
        path = self._mutated(lambda d: d.update(schema_version="1.99"))
        with self.assertRaises(ml.MapLoaderError):
            ml.load_map(path)

    def test_float_tile_rejected(self):
        def mutate(d):
            d["tiles"][0][0] = 1.5
        with self.assertRaises(ml.MapLoaderError) as ctx:
            ml.load_map(self._mutated(mutate))
        self.assertIn("int", str(ctx.exception))

    def test_bool_tile_rejected(self):
        def mutate(d):
            d["tiles"][0][1] = True
        with self.assertRaises(ml.MapLoaderError):
            ml.load_map(self._mutated(mutate))

    def test_tile_out_of_range_rejected(self):
        def mutate(d):
            d["tiles"][0] = [80, 0, 0]
        with self.assertRaises(ml.MapLoaderError) as ctx:
            ml.load_map(self._mutated(mutate))
        self.assertIn("越界", str(ctx.exception))

    def test_tile_bad_type_domain_rejected(self):
        def mutate(d):
            d["tiles"][0][2] = 3
        with self.assertRaises(ml.MapLoaderError) as ctx:
            ml.load_map(self._mutated(mutate))
        self.assertIn("int 表示域", str(ctx.exception))

    def test_tile_duplicate_rejected(self):
        def mutate(d):
            d["tiles"][1] = list(d["tiles"][0])
        with self.assertRaises(ml.MapLoaderError) as ctx:
            ml.load_map(self._mutated(mutate))
        self.assertIn("重复", str(ctx.exception))

    def test_building_hp_zero_rejected(self):
        def mutate(d):
            d["buildings"][0]["hp"] = 0
        with self.assertRaises(ml.MapLoaderError) as ctx:
            ml.load_map(self._mutated(mutate))
        self.assertIn("hp", str(ctx.exception))

    def test_building_dup_key_rejected(self):
        def mutate(d):
            d["buildings"][1]["building_key"] = d["buildings"][0]["building_key"]
        with self.assertRaises(ml.MapLoaderError):
            ml.load_map(self._mutated(mutate))

    # ── 字符串键门（PB-57 建筑实体块，2026-10-06——PB-58 评审遗留补齐：
    #    构建期 build_map._to_str 拦截可被手改 gen JSON 绕过，加载期收口
    #    DATA-02 §2 :56「禁 ;/:/公式前缀」+必填非空）──

    def test_map_key_empty_rejected(self):
        path = self._mutated(lambda d: d.update(map_key=""))
        with self.assertRaises(ml.MapLoaderError) as ctx:
            ml.load_map(path)
        self.assertIn("空串", str(ctx.exception))

    def test_map_key_formula_prefix_rejected(self):
        for bad in ("=x", "+x", "-x", "@x"):
            path = self._mutated(lambda d, b=bad: d.update(map_key=b))
            with self.assertRaises(ml.MapLoaderError) as ctx:
                ml.load_map(path)
            self.assertIn("公式注入", str(ctx.exception))

    def test_map_key_semicolon_colon_rejected(self):
        for bad in ("a;b", "a:b"):
            path = self._mutated(lambda d, b=bad: d.update(map_key=b))
            with self.assertRaises(ml.MapLoaderError) as ctx:
                ml.load_map(path)
            self.assertIn("分隔符", str(ctx.exception))

    def test_building_key_empty_rejected(self):
        def mutate(d):
            d["buildings"][0]["building_key"] = ""
        with self.assertRaises(ml.MapLoaderError) as ctx:
            ml.load_map(self._mutated(mutate))
        self.assertIn("空串", str(ctx.exception))

    def test_building_key_formula_prefix_rejected(self):
        for bad in ("=B", "+B", "-B", "@B"):
            def mutate(d, b=bad):
                d["buildings"][0]["building_key"] = b
            with self.assertRaises(ml.MapLoaderError) as ctx:
                ml.load_map(self._mutated(mutate))
            self.assertIn("公式注入", str(ctx.exception))

    def test_building_key_semicolon_colon_rejected(self):
        for bad in ("V1;HOUSE", "V1:HOUSE"):
            def mutate(d, b=bad):
                d["buildings"][0]["building_key"] = b
            with self.assertRaises(ml.MapLoaderError) as ctx:
                ml.load_map(self._mutated(mutate))
            self.assertIn("分隔符", str(ctx.exception))

    def test_building_key_non_str_rejected(self):
        def mutate(d):
            d["buildings"][0]["building_key"] = 7
        with self.assertRaises(ml.MapLoaderError) as ctx:
            ml.load_map(self._mutated(mutate))
        self.assertIn("str", str(ctx.exception))

    def test_missing_key_rejected(self):
        path = self._mutated(lambda d: d.pop("tile_cm"))
        with self.assertRaises(ml.MapLoaderError) as ctx:
            ml.load_map(path)
        self.assertIn("tile_cm", str(ctx.exception))

    def test_no_drift_lock_against_build(self):
        """双轨锁死：loader 支持表与 build 侧 SCHEMA_VERSION 单点双写一致。"""
        self.assertTrue(ml._map_schema_supported(bm.SCHEMA_VERSION))
        self.assertFalse(ml._map_schema_supported("1.99"))
        major, _, minor = bm.SCHEMA_VERSION.partition(".")
        self.assertEqual(ml.SUPPORTED_MAP_SCHEMA[int(major)], int(minor))

    def test_two_loads_identical_content(self):
        md1, md2 = ml.load_demo_map(), ml.load_demo_map()
        self.assertEqual(md1.forest_tiles, md2.forest_tiles)
        snap = lambda md: sorted(
            ((k, t.on_road, tuple(sorted(t.speed_bp.items())))
             for k, t in md.layer.tiles.items()))
        self.assertEqual(snap(md1), snap(md2))


class TestDemoMapSemantics(unittest.TestCase):
    """三类瓦片×三谓词＋旁挂面＋挂点对齐（正式示范图加载后行为）。"""

    @classmethod
    def setUpClass(cls):
        cls.w, cls.md = demo_world()

    def test_apply_map_aligns_world(self):
        self.assertIs(self.w.terrain, self.md.layer)
        self.assertEqual(self.w.map_extent, (200000, 100000))
        self.assertEqual(self.w.map_center, (100000, 50000))

    def test_road_tiles(self):
        # 干道起点瓦片 (2,22)：on_road 且零速度注入（路不吃 bp——MARCH 地板/
        # prefer_road 既有机制承载）
        pos = tc_center(2, 22)
        self.assertTrue(self.w.road_at(pos))
        self.assertIsNone(self.w.terrain_speed_tile_bp(pos, FOOT))
        self.assertIsNone(self.w.terrain_speed_tile_bp(pos, WHEEL))
        tile = self.md.layer.tiles[(2, 22)]
        self.assertTrue(tile.on_road)
        self.assertEqual(tile.speed_bp, {})

    def test_ruin_tiles(self):
        # V2 内部瓦片 (35,34)：四类同值 cfg.ruin_speed_bp、非路
        pos = tc_center(35, 34)
        self.assertFalse(self.w.road_at(pos))
        for cls in (FOOT, WHEEL, TRACK, HORSE):
            self.assertEqual(self.w.terrain_speed_tile_bp(pos, cls),
                             CONFIG.ruin_speed_bp)
        self.assertEqual(CONFIG.ruin_speed_bp, 4000)    # 占位值 pin（tables.py）

    def test_forest_tiles_side_set_only(self):
        # F1 内部 (8,30)：只入 forest_tiles 旁挂——不入 layer.tiles ⇒ 寻路侧
        # 三谓词与旷野恒等（§2.12：森林不减速只喂 sensing）
        pos = tc_center(8, 30)
        self.assertIn((8, 30), self.md.forest_tiles)
        self.assertNotIn((8, 30), self.md.layer.tiles)
        self.assertFalse(self.w.road_at(pos))
        self.assertIsNone(self.w.terrain_speed_tile_bp(pos, FOOT))
        self.assertIsNone(self.w.terrain_speed_tile_bp(pos, TRACK))

    def test_open_wilderness(self):
        pos = tc_center(60, 5)                           # 无声明区
        self.assertNotIn((60, 5), self.md.layer.tiles)
        self.assertNotIn((60, 5), self.md.forest_tiles)
        self.assertFalse(self.w.road_at(pos))
        self.assertIsNone(self.w.terrain_speed_tile_bp(pos, WHEEL))

    def test_painter_artifacts_on_demo_map(self):
        md = self.md
        # 干道穿 V1 成街：(40,20)=ROAD 且不在 forest；R4 切 F1 林道 (12,28)=ROAD
        # 且已从 forest 旁挂除名（后绘覆盖）
        self.assertTrue(is_road(md, (40, 20)))
        self.assertNotIn((40, 20), md.forest_tiles)
        self.assertTrue(is_road(md, (12, 28)))
        self.assertNotIn((12, 28), md.forest_tiles)
        self.assertIn((11, 28), md.forest_tiles)         # 邻格仍是林
        self.assertTrue(is_ruin(md, (37, 17)))           # V1 街外废墟
        self.assertTrue(is_ruin(md, (35, 34)))           # V2 内部
        # 本图结构性护栏：无非 0 bp 注入（废墟=可通行减速占位——无实体屏障瓦片）
        bad = [k for k, v in md.layer.tiles.items()
               if any(bv == 0 for bv in v.speed_bp.values())]
        self.assertEqual(bad, [])

    def test_south_deploy_anchor_passable(self):
        # 勘察③护栏：部署锚点瓦片不得落 bp==0（tile_cost 非 None 即可通行）
        for ix, iy in ((40, 0), (39, 0), (41, 0)):
            self.assertIsNotNone(tile_cost(self.w, self.md.layer, CONFIG,
                                           ix, iy, TRACK, False))

    def test_buildings_passthrough(self):
        self.assertEqual(len(self.md.buildings), 5)
        for b in self.md.buildings:
            self.assertGreaterEqual(b.hp, 1)
            self.assertTrue(0 <= b.x_cm < 200000 and 0 <= b.y_cm < 100000)
        keys = {b.building_key for b in self.md.buildings}
        self.assertEqual(len(keys), 5)

    def test_apply_map_instantiates_buildings(self):
        # PB-57 建筑实体块：apply_map 装配——5 锚入 world.buildings，id=1 起文件序
        # （指纹 B 段 b.id 消费确定性）、pos/hp=BuildingSpec 透传（CSV building 行）、
        # garrison_slots=楼型派生（2026-10-06 拍板：小/中/大楼=1/2/3 排按 footprint）
        w, md = self.w, self.md
        self.assertEqual(len(w.buildings), 5)
        self.assertTrue(all(isinstance(b, Building) for b in w.buildings))
        self.assertEqual([b.id for b in w.buildings], [1, 2, 3, 4, 5])
        for b, spec in zip(w.buildings, md.buildings):
            self.assertEqual(b.pos, (spec.x_cm, spec.y_cm))       # 文件序一一对应
            self.assertEqual(b.hp, spec.hp)
            self.assertEqual(b.garrison_slots, CONFIG.building_garrison_slots_small)  # footprint 2500<5000=小楼
            self.assertEqual(b.garrisoned, [])
        self.assertEqual([b.hp for b in w.buildings], [100] * 5)  # gen JSON 占位值 pin
        # 合成建筑并存口径：extend 追加不替换
        w2 = make_world(8, size_cm=(999999, 999999))
        synth = Building(id=99, pos=(1, 1), hp=5, garrison_slots=3)
        w2.buildings.append(synth)
        ml.apply_map(w2, md)
        self.assertIs(w2.buildings[0], synth)
        self.assertEqual([b.id for b in w2.buildings[1:]], [1, 2, 3, 4, 5])
        # 装配建筑与合成建筑身份等价进塌楼链（combat.hit_building 既有消费）——
        # 独立 world（类级共享 self.w 不污染他锚）
        w3, _ = demo_world()
        victim = w3.buildings[0]
        hit_building(w3, victim, victim.hp, CONFIG)
        self.assertNotIn(victim, w3.buildings)                   # hp<=0 即塌出表
        self.assertEqual(len(w3.buildings), 4)


class TestDemoMapPathfinding(unittest.TestCase):
    """示范图真实寻路：绕障/穿行对比/prefer_road 上路/最优性仲裁/零掷骰。"""

    @classmethod
    def setUpClass(cls):
        cls.w, cls.md = demo_world()

    def test_detour_around_v2_strip_all_classes(self):
        """V2 横带废墟（[28..49]×[31..36]）东西横穿：三类别全部绕行——
        航点重走零废墟格、多航点（≠直线直填）、代价==独立 Dijkstra 最优。"""
        a, b = tc_center(24, 34), tc_center(53, 34)
        for cls in (FOOT, WHEEL, TRACK):
            with self.subTest(cls=cls.name):
                path = self.w.find_path(a, b, cls, False)
                self.assertNotEqual(path, [b])           # 非直线直填
                tiles = route_tiles(self.w, cls, False, a, path)
                self.assertFalse([t for t in tiles if is_ruin(self.md, t)])
                self.assertEqual(
                    route_cost(self.w, cls, False, a, path),
                    dijkstra_cost(self.w, cls, False, a, b))

    def test_foot_detour_cost_anchor(self):
        # FOOT 绕行代价定锚（独立 Dijkstra 复核过——地图改动须有意重锚）
        a, b = tc_center(24, 34), tc_center(53, 34)
        path = self.w.find_path(a, b, FOOT, False)
        self.assertEqual(route_cost(self.w, FOOT, False, a, path), 393562)

    def test_wheel_crosses_ruin_contrast(self):
        """对比查询：V1 村庄（[34..46]×[15..24]）南北穿行 col=36 非街道列——
        WHEEL（1.25× 代价比）直穿废墟最省 vs FOOT（2×）绕行：类别分档可观测。"""
        a, b = tc_center(36, 28), tc_center(36, 12)
        p_wheel = self.w.find_path(a, b, WHEEL, False)
        wheel_tiles = route_tiles(self.w, WHEEL, False, a, p_wheel)
        self.assertTrue(any(is_ruin(self.md, t) for t in wheel_tiles))
        self.assertEqual(
            route_cost(self.w, WHEEL, False, a, p_wheel),
            dijkstra_cost(self.w, WHEEL, False, a, b))
        p_foot = self.w.find_path(a, b, FOOT, False)
        foot_tiles = route_tiles(self.w, FOOT, False, a, p_foot)
        self.assertFalse([t for t in foot_tiles if is_ruin(self.md, t)])
        self.assertEqual(
            route_cost(self.w, FOOT, False, a, p_foot),
            dijkstra_cost(self.w, FOOT, False, a, b))

    def test_prefer_road_routes_onto_trunk(self):
        """prefer_road=True：平行干道长程查询 (5,16)→(75,16) 真上路（路面代价减半
        pathfind.py:127-128）——上路格占多数、与无偏好路径分岔、两向均最优。"""
        a, b = tc_center(5, 16), tc_center(75, 16)
        p_pref = self.w.find_path(a, b, WHEEL, True)
        p_flat = self.w.find_path(a, b, WHEEL, False)
        self.assertNotEqual(p_pref, p_flat)
        on_road = [t for t in route_tiles(self.w, WHEEL, True, a, p_pref)
                   if is_road(self.md, t)]
        total = len(route_tiles(self.w, WHEEL, True, a, p_pref))
        self.assertGreater(len(on_road), total // 2)     # 大半程在路面
        flat_road = [t for t in route_tiles(self.w, WHEEL, False, a, p_flat)
                     if is_road(self.md, t)]
        self.assertLessEqual(len(flat_road), total // 10)
        self.assertEqual(route_cost(self.w, WHEEL, True, a, p_pref),
                         dijkstra_cost(self.w, WHEEL, True, a, b))
        self.assertEqual(route_cost(self.w, WHEEL, False, a, p_flat),
                         dijkstra_cost(self.w, WHEEL, False, a, b))
        self.assertLess(route_cost(self.w, WHEEL, True, a, p_pref),
                        route_cost(self.w, WHEEL, False, a, p_flat))

    def test_same_seed_deterministic_and_zero_dice(self):
        w2, _ = demo_world(seed=7)
        before = [(self.w.rng.rng(i).state, self.w.rng.rng(i).inc)
                  for i in range(8)]
        queries = [(tc_center(24, 34), tc_center(53, 34), FOOT, False),
                   (tc_center(5, 16), tc_center(75, 16), WHEEL, True),
                   (tc_center(36, 28), tc_center(36, 12), TRACK, False)]
        for a, b, cls, pref in queries:
            self.assertEqual(self.w.find_path(a, b, cls, pref),
                             w2.find_path(a, b, cls, pref))
        after = [(self.w.rng.rng(i).state, self.w.rng.rng(i).inc)
                 for i in range(8)]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
