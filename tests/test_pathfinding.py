"""测试：§2.14 寻路层（pathfind.py——整型 A*/三谓词 stub/定标式/确定性/零掷骰）。
锚点全部手推写死：瓦片代价按 §2.14 公式直算；路径按唯一最优路线手推
（并列最优处按 (f,插入序号)+DIR8 固定序完整手推 A* 时序）。
PB-10 路径缓存（2026-10-04 寻路接线块）：TestPathCache——命中零行为差/地形与
图界突变天然失效（内容指纹键）/frm 起点格粒度/LRU 触碰与有界/禁用位/
不可达兜底缓存/零掷骰。A* 体执行次数以 _min_step_cost 计（每次 A* 恰一次、
位于缓存判定之后——命中不计）。
PB-58 展开限幅保险丝（2026-10-06 块①，PB-50 前置门）：TestExpansionCap——
超限直线兜底 [to]（同不可达口径）/成功 ⇔ 展开数 ≤ cap（goal 命中前判定）/
cap=0 不限幅/兜底入缓存但 cap 入键（双向不冒充）/纯计数零掷骰。"""
import unittest

from sovs.sim.movement import system_move
from sovs.sim.pathfind import (DIR8, TerrainLayer, TerrainTile, find_path,
                               road_at, terrain_speed_tile_bp, tile_cost)
from sovs.sim.tables import CONFIG, BalanceConfig
from sovs.sim.tick import make_world
from sovs.sim.types import (ElementInstance, ElementTemplate, MovementClass,
                            UnitInstance, UnitTemplate, UnitType)


def world_with_layer(seed=7, tile_cm=1000, tiles=None, size=(1000000, 1000000)):
    w = make_world(seed, size_cm=size)
    w.terrain = TerrainLayer(tile_cm=tile_cm, tiles=tiles)
    return w


def wall(tiles_xy, cls=MovementClass.WHEEL, bp=0):
    return {(x, y): TerrainTile(speed_bp={cls: bp}) for x, y in tiles_xy}


class TestStubSemantics(unittest.TestCase):
    """terrain=None（TERRAIN 表未接入）——§2.14 stub 三口径（AMB-8 不丢）。"""

    def test_find_path_stub_straight_fill(self):
        w = make_world(3)
        self.assertEqual(w.find_path((0, 0), (123456, 789),
                                     MovementClass.TRACK, False), [(123456, 789)])
        self.assertEqual(w.find_path((123456, 789), (0, 0),
                                     MovementClass.FOOT, True), [(0, 0)])

    def test_road_at_stub_false(self):
        w = make_world(3)
        self.assertFalse(w.road_at((500000, 500000)))
        self.assertFalse(road_at(w, (0, 0)))

    def test_tile_bp_stub_none(self):
        w = make_world(3)
        self.assertIsNone(w.terrain_speed_tile_bp((500000, 500000),
                                                  MovementClass.WHEEL))
        self.assertIsNone(terrain_speed_tile_bp(w, (0, 0), MovementClass.FOOT))

    def test_start_equals_goal(self):
        w = world_with_layer()
        self.assertEqual(w.find_path((500, 500), (500, 500),
                                     MovementClass.WHEEL, False), [(500, 500)])


class TestTileCostFormula(unittest.TestCase):
    """§2.14 定标式逐条（bp=10000→10000 基准/倒数取式/道路减半 MAX(1,·//2)/bp==0→INF）。"""

    def setUp(self):
        self.w = world_with_layer(tile_cm=1000)
        self.layer = self.w.terrain

    def test_missing_tile_class_default(self):
        # 缺席瓦片=类级缺省：WHEEL 5000bp → round_div(1e8,5000)=20000
        self.assertEqual(tile_cost(self.w, self.layer, CONFIG, 5, 5,
                                   MovementClass.WHEEL, False), 20000)

    def test_base_reference_cost(self):
        self.layer.tiles[(5, 5)] = TerrainTile(speed_bp={MovementClass.WHEEL: 10000})
        self.assertEqual(tile_cost(self.w, self.layer, CONFIG, 5, 5,
                                   MovementClass.WHEEL, False), 10000)

    def test_reciprocal_scaling(self):
        # 倒数取式：bp=2500 → round_div(1e8,2500)=40000
        self.layer.tiles[(5, 5)] = TerrainTile(speed_bp={MovementClass.WHEEL: 2500})
        self.assertEqual(tile_cost(self.w, self.layer, CONFIG, 5, 5,
                                   MovementClass.WHEEL, False), 40000)

    def test_road_halving(self):
        self.layer.tiles[(5, 5)] = TerrainTile(on_road=True,
                                               speed_bp={MovementClass.WHEEL: 10000})
        self.assertEqual(tile_cost(self.w, self.layer, CONFIG, 5, 5,
                                   MovementClass.WHEEL, True), 5000)   # MAX(1,10000//2)
        self.assertEqual(tile_cost(self.w, self.layer, CONFIG, 5, 5,
                                   MovementClass.WHEEL, False), 10000)  # 无偏好不减半

    def test_road_halving_floor_one(self):
        # bp=2e8 → round_div(1e8,2e8)=1 → //2=0 → MAX(1,·)=1
        self.layer.tiles[(5, 5)] = TerrainTile(on_road=True,
                                               speed_bp={MovementClass.WHEEL: 200000000})
        self.assertEqual(tile_cost(self.w, self.layer, CONFIG, 5, 5,
                                   MovementClass.WHEEL, True), 1)

    def test_bp_zero_impassable(self):
        self.layer.tiles[(5, 5)] = TerrainTile(speed_bp={MovementClass.WHEEL: 0})
        self.assertIsNone(tile_cost(self.w, self.layer, CONFIG, 5, 5,
                                    MovementClass.WHEEL, False))

    def test_out_of_map_impassable(self):
        # 图界闭合：map 1e6/tile 1000 → 合法 ix∈[0,1000)；图外与负格不可通行
        self.assertIsNone(tile_cost(self.w, self.layer, CONFIG, 1000, 0,
                                    MovementClass.WHEEL, False))
        self.assertIsNone(tile_cost(self.w, self.layer, CONFIG, -1, 0,
                                    MovementClass.WHEEL, False))
        self.assertIsNotNone(tile_cost(self.w, self.layer, CONFIG, 999, 999,
                                       MovementClass.WHEEL, False))


class TestPredicatesWithLayer(unittest.TestCase):
    def setUp(self):
        self.w = world_with_layer(tiles={
            (2, 2): TerrainTile(on_road=True, speed_bp={MovementClass.WHEEL: 6000}),
            (3, 3): TerrainTile(speed_bp={MovementClass.WHEEL: 0}),
            (4, 4): TerrainTile(speed_bp={MovementClass.FOOT: 9000}),
        })

    def test_road_at(self):
        self.assertTrue(self.w.road_at((2500, 2500)))    # (2,2) 路瓦片内任一点
        self.assertFalse(self.w.road_at((1500, 1500)))   # 缺席瓦片
        self.assertFalse(self.w.road_at((3500, 3500)))   # 在编非路瓦片

    def test_tile_bp(self):
        self.assertEqual(self.w.terrain_speed_tile_bp((2500, 2500),
                                                     MovementClass.WHEEL), 6000)
        self.assertEqual(self.w.terrain_speed_tile_bp((3500, 3500),
                                                     MovementClass.WHEEL), 0)  # bp=0 是真值
        self.assertIsNone(self.w.terrain_speed_tile_bp((4500, 4500),
                                                       MovementClass.WHEEL))     # 类缺席→缺省
        self.assertEqual(self.w.terrain_speed_tile_bp((4500, 4500),
                                                     MovementClass.FOOT), 9000)
        self.assertIsNone(self.w.terrain_speed_tile_bp((500, 500),
                                                       MovementClass.TRACK))    # 瓦片缺席


class TestFindPathUniform(unittest.TestCase):
    """空瓦片表=全域类级缺省（WHEEL：card 20000 / diag 20000×14142//10000=28284）。"""

    def setUp(self):
        self.w = world_with_layer()

    def test_straight_east_single_waypoint(self):
        # (0,0)→(3,0)：E,E,E 共线一段 → 单航点=精确 to（与 stub 输出同形）
        self.assertEqual(self.w.find_path((500, 500), (3500, 500),
                                          MovementClass.WHEEL, False),
                         [(3500, 500)])

    def test_pure_diagonal_single_waypoint(self):
        # (0,0)→(2,2)：纯对角 2×28284=56568 < 4×20000（唯一最优）→ 单航点
        self.assertEqual(self.w.find_path((500, 500), (2500, 2500),
                                          MovementClass.WHEEL, False),
                         [(2500, 2500)])

    def test_mixed_route_hand_traced(self):
        # (0,0)→(3,1) 手推 A* 时序（修复后 h=(M−k)×20000+k×28284）：
        # 起始 h=68284；弹出 (0,0) 后堆内 f=68284 者 (1,1)seq2 先于 (1,0)seq3，
        # 继而 (1,0)f68284→(2,1)f68284→(2,0)f68284→命中 (3,1)（父链经 (2,1)）；
        # 路径 NE,E,E（与 E,E,NE 同价 68284——并列最优，tie-break 取此形）→
        # 共线合并 [center(1,1), 精确 to]。
        self.assertEqual(self.w.find_path((500, 500), (3500, 1500),
                                          MovementClass.WHEEL, False),
                         [(1500, 1500), (3500, 1500)])


class TestFindPathObstacle(unittest.TestCase):
    def setUp(self):
        # 竖墙 (1,0..3) bp=0；绕行唯一最优=上方 j=4 越墙（6 card=120000，
        # 下方 8 card=160000；贴墙对角全部被禁切角规则封锁）。
        self.w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))

    def test_detour_around_wall(self):
        # N,N,E,E,S,S → 转向格中心 (0,4)/(2,4) + 精确 to
        self.assertEqual(self.w.find_path((500, 2500), (2500, 2500),
                                          MovementClass.WHEEL, False),
                         [(500, 4500), (2500, 4500), (2500, 2500)])

    def test_goal_blocked_falls_back(self):
        # 终点格 bp==0 → 兜底 RETURN [to]（裁定④）
        self.assertEqual(self.w.find_path((500, 2500), (1500, 2500),
                                          MovementClass.WHEEL, False),
                         [(1500, 2500)])

    def test_enclosed_goal_falls_back(self):
        # 小图（4×4 格）：(2,0) 被西/北/东墙+图外南缘围死 → 不可达兜底
        w = world_with_layer(size=(4000, 4000),
                             tiles=wall([(1, 0), (1, 1), (2, 1), (3, 0), (3, 1)]))
        self.assertEqual(w.find_path((500, 500), (2500, 500),
                                     MovementClass.WHEEL, False),
                         [(2500, 500)])


class TestRoadPreference(unittest.TestCase):
    """WHEEL（缺省 20000）；路排 y=1：(0..4,1) on_road bp=5000——
    无偏好路瓦 20000=缺省（直穿更快）；有偏好路瓦 10000（下路更省）。"""

    def setUp(self):
        road = {(x, 1): TerrainTile(on_road=True,
                                    speed_bp={MovementClass.WHEEL: 5000})
                for x in range(5)}
        self.w = world_with_layer(tiles=road)

    def test_without_preference_direct(self):
        # 直线 E,E,E,E=80000 唯一最优 → 单航点 [to]
        self.assertEqual(self.w.find_path((500, 500), (4500, 500),
                                          MovementClass.WHEEL, False),
                         [(4500, 500)])

    def test_with_preference_detour(self):
        # 有偏好最优=对角上路(1,1)14142+顺路 E,E 20000+对角下路 (4,0)28284=62426
        # （贴路对角 (0,1)/(3,0) 变体均更贵——手推唯一最优）；
        # 步序 DIAG,E,E,DIAG → [center(1,1), center(3,1), 精确 to]
        self.assertEqual(self.w.find_path((500, 500), (4500, 500),
                                          MovementClass.WHEEL, True),
                         [(1500, 1500), (3500, 1500), (4500, 500)])

    def test_preference_changes_route(self):
        a = self.w.find_path((500, 500), (4500, 500), MovementClass.WHEEL, True)
        b = self.w.find_path((500, 500), (4500, 500), MovementClass.WHEEL, False)
        self.assertNotEqual(a, b)


class TestDeterminism(unittest.TestCase):
    def _layer(self, reverse=False):
        items = [(x, 1) for x in range(5)]
        road = {(x, y): TerrainTile(on_road=(y == 1),
                                    speed_bp={MovementClass.WHEEL: 5000})
                for x, y in (reversed(items) if reverse else items)}
        for x, y in [(1, 3), (2, 3)]:                      # 加两块阻挡
            road[(x, y)] = TerrainTile(speed_bp={MovementClass.WHEEL: 0})
        return road

    def test_same_seed_identical_output(self):
        w1 = world_with_layer(seed=42, tiles=self._layer())
        w2 = world_with_layer(seed=42, tiles=self._layer())
        queries = [((500, 500), (4500, 1500), False),
                   ((500, 500), (4500, 1500), True),
                   ((500, 4500), (2500, 500), False),
                   ((4500, 4500), (500, 500), True)]
        for frm, to, pref in queries:
            self.assertEqual(w1.find_path(frm, to, MovementClass.WHEEL, pref),
                             w2.find_path(frm, to, MovementClass.WHEEL, pref))

    def test_tile_insertion_order_irrelevant(self):
        # tiles 旁表仅 min 扫描遍历（取 min 序无关）+ get 查表——插入序不影响输出
        w1 = world_with_layer(tiles=self._layer(reverse=False))
        w2 = world_with_layer(tiles=self._layer(reverse=True))
        for frm, to, pref in [((500, 500), (4500, 1500), True),
                              ((500, 4500), (2500, 500), False)]:
            self.assertEqual(w1.find_path(frm, to, MovementClass.WHEEL, pref),
                             w2.find_path(frm, to, MovementClass.WHEEL, pref))

    def test_zero_dice_all_channels_untouched(self):
        # 契约⑰：移动零掷骰——寻路后 8 通道 PCG32 内部 state/inc 逐位不变
        # （小图跑对角长路：1km 图 1000cm 网格对角扫 ~8s——性能特征见登记表，此处
        # 不重复全图扫描）
        w = world_with_layer(seed=13, tiles=self._layer(), size=(50000, 50000))
        before = [(w.rng.rng(i).state, w.rng.rng(i).inc) for i in range(8)]
        for frm, to, pref in [((0, 0), (49999, 49999), True),
                              ((500, 4500), (2500, 500), False)]:
            w.find_path(frm, to, MovementClass.WHEEL, pref)
        after = [(w.rng.rng(i).state, w.rng.rng(i).inc) for i in range(8)]
        self.assertEqual(before, after)


class TestMovementConsumption(unittest.TestCase):
    """find_path 输出喂 system_move.move_path（消费端兼容性冒烟——
    dispatch 接线未落地，此处直调 movement.system_move）。"""

    def test_unit_walks_path_to_destination(self):
        w = world_with_layer()
        et = ElementTemplate(element_type=0, unit_type=UnitType.MECH, hp_max=16)
        ut = UnitTemplate(template_id=1, name="tank", category=2, cost=200,
                          element_templates=(et,), optics_ground_cm=1400,
                          stealth_base=1, speed_tier=4,
                          movement_class=MovementClass.TRACK)
        u = UnitInstance(id=1, team=0, template=ut, pos=(500, 500))
        e = ElementInstance(id=1, unit=u, template=et, pos=(500, 500), hp_current=16)
        u.elements.append(e)
        u.move_path = w.find_path((500, 500), (3500, 1500),
                                  MovementClass.TRACK, False)
        self.assertEqual(u.move_path, [(1500, 1500), (3500, 1500)])   # 手推锚点
        for _ in range(200):                                          # v=70cm/tick，全程 3414cm
            if not u.move_path:
                break
            system_move(CONFIG, u, 0)
        self.assertEqual(u.pos, (3500, 1500))
        self.assertEqual(u.move_path, [])


class TestDir8Order(unittest.TestCase):
    def test_dir8_octant_ring(self):
        # DIR8 环序=geom.octant_deg 扇区 0/45/.../315（固定遍历序——确定性锚）
        from sovs.sim.geom import octant_deg
        self.assertEqual([octant_deg(dx, dy) for dx, dy in DIR8],
                         [0, 45, 90, 135, 180, 225, 270, 315])


def _route_cost(w, cls, pref, frm, waypoints):
    """独立代价核算：沿返回航点逐格重走（DIR8 对齐段——测试取格中心为端点），
    逐入格累加 tile_cost（对角步 ×14142//10000 与实现同式）。"""
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


def _dijkstra_cost(w, cls, pref, frm, to):
    """独立最优性仲裁：测试内 Dijkstra（同一代价模型：入格代价/对角乘子/禁切角/
    图界），返回起点格→终点格最优代价。与 A* 无共享代码路径。"""
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


class TestOptimalityVsDijkstra(unittest.TestCase):
    """评审修复回归（2026-10-02）：原 round_div(4142·k) 半舍入启发式高估短轴项
    （均匀 WHEEL dx=dy=2：h=60000 > 真实最优 56568）→ A* 可返回次优路径。
    修复后 h 与步代价同式同取整（对角乘子 floor 单调）→ 逐查询与独立 Dijkstra
    最优代价恒等。混合地速取现实地速表值族（bp 9091/10000/4762）。"""

    def setUp(self):
        tiles = {}
        grid = [[10000, 4762, 10000, 9091, 10000],
                [9091, 10000, 4762, 10000, 9091],
                [10000, 0,    10000, 4762, 10000],   # (1,2)=不可通行
                [4762, 10000, 9091, 10000, 4762],
                [10000, 9091, 10000, 0,    10000]]   # (3,4)=不可通行
        for y, row in enumerate(grid):
            for x, v in enumerate(row):
                tiles[(x, y)] = TerrainTile(on_road=(y == 4),
                                            speed_bp={MovementClass.WHEEL: v})
        self.w = world_with_layer(size=(5000, 5000), tiles=tiles)
        self.queries = [((500, 500), (4500, 4500), False),
                        ((500, 500), (4500, 4500), True),
                        ((4500, 500), (500, 4500), False),
                        ((4500, 500), (500, 4500), True),
                        ((2500, 2500), (4500, 500), False),
                        ((500, 3500), (4500, 1500), True),
                        ((1500, 500), (2500, 4500), False)]

    def test_find_path_cost_equals_dijkstra_optimum(self):
        for frm, to, pref in self.queries:
            with self.subTest(frm=frm, to=to, pref=pref):
                path = self.w.find_path(frm, to, MovementClass.WHEEL, pref)
                best = _dijkstra_cost(self.w, MovementClass.WHEEL, pref, frm, to)
                self.assertEqual(_route_cost(self.w, MovementClass.WHEEL,
                                             pref, frm, path), best)

    def test_uniform_diagonal_admissible_regression(self):
        # 均匀 WHEEL：dx=dy=2 最优=2 对角步 2×28284=56568（原缺陷 h=60000 高估）
        w = world_with_layer()
        path = w.find_path((500, 500), (2500, 2500), MovementClass.WHEEL, False)
        self.assertEqual(_route_cost(w, MovementClass.WHEEL, False,
                                     (500, 500), path), 56568)

    def test_mixed_bp_hand_computed_optimum(self):
        # 3×2 混合图手推：(0,0)→(2,0) 最优=对角(1,1)15556+对角(2,0)14142=29698
        # （直穿 10000+21000=31000；沿 y=1 绕 15556+11000+10000=36556 均更贵）
        tiles = {(0, 0): TerrainTile(speed_bp={MovementClass.WHEEL: 10000}),
                 (1, 0): TerrainTile(speed_bp={MovementClass.WHEEL: 4762}),
                 (2, 0): TerrainTile(speed_bp={MovementClass.WHEEL: 10000}),
                 (0, 1): TerrainTile(speed_bp={MovementClass.WHEEL: 9091}),
                 (1, 1): TerrainTile(speed_bp={MovementClass.WHEEL: 9091}),
                 (2, 1): TerrainTile(speed_bp={MovementClass.WHEEL: 9091})}
        w = world_with_layer(size=(3000, 2000), tiles=tiles)
        path = w.find_path((500, 500), (2500, 500), MovementClass.WHEEL, False)
        self.assertEqual(_route_cost(w, MovementClass.WHEEL, False,
                                     (500, 500), path), 29698)


# ── PB-10 路径缓存（2026-10-04 寻路接线块：随消费侧落地——issue_move 已真调用
#    find_path；缓存=World.path_cache LRU 有界，键含地形内容指纹）──


class TestPathCache(unittest.TestCase):
    """缓存命中=零行为差（输出位级一致+每次新 list）；地形/图界任何突变天然换键
    失效；frm 仅经起点格入键；LRU 触碰驱逐；0=禁用；不可达兜底同键缓存。"""

    def _astar_runs(self, w, queries, cfg=CONFIG):
        """执行 queries 并计数 A* 体真实执行次数（_min_step_cost 每次 A* 恰一次、
        位于缓存判定之后——命中不计；mock 仅包计数不改行为）。"""
        import sovs.sim.pathfind as pf
        from unittest import mock
        calls = []
        orig = pf._min_step_cost

        def wrapper(*a, **k):
            calls.append(1)
            return orig(*a, **k)

        with mock.patch.object(pf, "_min_step_cost", wrapper):
            out = [find_path(w, frm, to, MovementClass.WHEEL, pref, cfg)
                   for frm, to, pref in queries]
        return out, len(calls)

    def test_hit_zero_behavior_diff_and_fresh_list(self):
        # 同查询两次：A* 只跑一次；输出位级一致；返回新 list——调用方 pop 不腐蚀缓存
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        q = ((500, 2500), (2500, 2500), False)
        (first, second), runs = self._astar_runs(w, [q, q])
        self.assertEqual(runs, 1)                        # 第二次命中
        self.assertEqual(first, second)
        second.pop()                                     # 调用方可变（system_move pop 同款）
        third = find_path(w, q[0], q[1], MovementClass.WHEEL, False)
        self.assertEqual(first, third)                    # 缓存未被腐蚀

    def test_terrain_mutation_invalidates(self):
        # tiles 增键（墙）→ 内容指纹变 → 换键重算（绕行输出随之更新）
        w = world_with_layer()
        q = ((500, 500), (3500, 1500), False)
        (p1,), runs1 = self._astar_runs(w, [q])
        self.assertEqual(runs1, 1)
        self.assertEqual(p1, [(1500, 1500), (3500, 1500)])   # 均匀图手推锚点
        w.terrain.tiles[(2, 1)] = TerrainTile(speed_bp={MovementClass.WHEEL: 0})
        (p2,), runs2 = self._astar_runs(w, [q])
        self.assertEqual(runs2, 1)                        # 未吃旧缓存
        self.assertNotEqual(p1, p2)                       # (2,1) 在原链上——必改道

    def test_in_place_tile_replacement_invalidates(self):
        # 同键改值（len 不变）：内容指纹仍捕获——仅 len 的弱校验会漏此面
        w = world_with_layer(tiles={(2, 1): TerrainTile(
            speed_bp={MovementClass.WHEEL: 10000})})
        q = ((500, 500), (3500, 1500), False)
        (p1,), _ = self._astar_runs(w, [q])
        w.terrain.tiles[(2, 1)] = TerrainTile(speed_bp={MovementClass.WHEEL: 0})
        (p2,), runs2 = self._astar_runs(w, [q])
        self.assertEqual(runs2, 1)
        self.assertNotEqual(p1, p2)                       # 原链经 (2,1)——封死必改道

    def test_map_extent_in_key(self):
        # 图界收缩把唯一缺口推出图外 → 同查询换键重算、兜底 [to]
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        q = ((500, 500), (2500, 500), False)
        (p1,), _ = self._astar_runs(w, [q])
        self.assertEqual(p1, [(500, 4500), (2500, 4500), (2500, 500)])  # 越墙锚点
        w.map_extent = (1000000, 4000)                    # iy∈[0,4)：缺口 iy=4 出图
        (p2,), runs2 = self._astar_runs(w, [q])
        self.assertEqual(runs2, 1)                        # map_extent 在键内——重算
        self.assertEqual(p2, [(2500, 500)])               # 不可达兜底（同裁决④）

    def test_same_start_tile_different_frm_hits(self):
        # frm 仅经起点格入键（find_path 体内 frm 唯一消费=_tile_index）：
        # 同格不同点 → 命中且输出恒等
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        (p1, p2), runs = self._astar_runs(
            w, [((500, 500), (2500, 2500), False),
                ((900, 900), (2500, 2500), False)])       # 两 frm 同属格 (0,0)
        self.assertEqual(runs, 1)
        self.assertEqual(p1, p2)

    def test_exact_to_in_key(self):
        # 同起终格不同精确 to → 不同键（末航点=精确 to）
        w = world_with_layer()
        (pa, pb), runs = self._astar_runs(
            w, [((500, 500), (3500, 1500), False),
                ((500, 500), (3900, 1900), False)])       # 同终格 (3,1)
        self.assertEqual(runs, 2)
        self.assertEqual(pa[-1], (3500, 1500))
        self.assertEqual(pb[-1], (3900, 1900))

    def test_lru_touch_and_bound(self):
        # 容量 2：a,b 入缓 → 命中 a 触碰（序移末）→ c 入缓驱逐 b（非 a）→
        # a 仍命中、b 重算
        cfg = BalanceConfig(pathfind_cache_entries=2)
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        a = ((500, 500), (2500, 2500), False)
        b = ((500, 500), (4500, 4500), False)
        c = ((500, 2500), (2500, 2500), False)
        _, runs = self._astar_runs(w, [a, b, a, c, a], cfg)
        self.assertEqual(runs, 3)                         # a,b,c 各算一次；两度 a 命中
        self.assertLessEqual(len(w.path_cache), 2)
        _, runs_b = self._astar_runs(w, [b], cfg)
        self.assertEqual(runs_b, 1)                       # b 已被驱逐

    def test_zero_entries_disables_cache(self):
        cfg = BalanceConfig(pathfind_cache_entries=0)
        w = world_with_layer()
        q = ((500, 500), (3500, 1500), False)
        (p1, p2), runs = self._astar_runs(w, [q, q], cfg)
        self.assertEqual(runs, 2)                         # 每次都真算
        self.assertEqual(p1, p2)                          # 结果仍一致（禁用≠变行为）
        self.assertEqual(w.path_cache, {})

    def test_unreachable_fallback_cached(self):
        # 不可达兜底（最贵分支——近 Dijkstra 全图扫描）同键缓存
        w = world_with_layer(size=(4000, 4000),
                             tiles=wall([(1, 0), (1, 1), (2, 1), (3, 0), (3, 1)]))
        q = ((500, 500), (2500, 500), False)
        (p1, p2), runs = self._astar_runs(w, [q, q])
        self.assertEqual(runs, 1)
        self.assertEqual(p1, [(2500, 500)])
        self.assertEqual(p1, p2)

    def test_cache_zero_dice(self):
        # 契约⑰：缓存命中/写缓路径不触碰任何 PCG32 通道
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        before = [(w.rng.rng(i).state, w.rng.rng(i).inc) for i in range(8)]
        q = ((500, 2500), (2500, 2500), False)
        self.assertEqual(find_path(w, q[0], q[1], MovementClass.WHEEL, False),
                         find_path(w, q[0], q[1], MovementClass.WHEEL, False))
        after = [(w.rng.rng(i).state, w.rng.rng(i).inc) for i in range(8)]
        self.assertEqual(before, after)


# ── PB-58 展开限幅保险丝（2026-10-06 块①——PB-50 前置门：max-expansions 常数入
#    BalanceConfig、超限直线兜底、cap 入缓存键）──


class TestExpansionCap(unittest.TestCase):
    """超限→直线兜底 [to]（同不可达/AMB-8 口径）；成功 ⇔ 展开数 ≤ cap（判定在
    goal 命中前）；cap=0=不限幅；超限兜底入缓存（次贵分支不重付）但 cap 入键
    （cap 变更=全量换键——调大后旧兜底条目不冒充真路径，真路径条目亦不被
    小 cap 键命中）；限幅判定纯计数零掷骰。"""

    def _astar_runs(self, w, queries, cfg=CONFIG):
        """A* 体真实执行次数计数（TestPathCache._astar_runs 同款——_min_step_cost
        每次 A* 恰一次、位于缓存判定之后；mock 仅包计数不改行为）。"""
        import sovs.sim.pathfind as pf
        from unittest import mock
        calls = []
        orig = pf._min_step_cost

        def wrapper(*a, **k):
            calls.append(1)
            return orig(*a, **k)

        with mock.patch.object(pf, "_min_step_cost", wrapper):
            out = [find_path(w, frm, to, MovementClass.WHEEL, pref, cfg)
                   for frm, to, pref in queries]
        return out, len(calls)

    def test_default_cap_small_maps_unaffected(self):
        # 默认 cap=500,000 ≫ 小图展开数——既有手推锚点原样成立（已测档位零行为差）
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        self.assertEqual(w.find_path((500, 2500), (2500, 2500),
                                     MovementClass.WHEEL, False),
                         [(500, 4500), (2500, 4500), (2500, 2500)])  # 越墙锚点
        self.assertEqual(world_with_layer().find_path((500, 500), (3500, 1500),
                                                      MovementClass.WHEEL, False),
                         [(1500, 1500), (3500, 1500)])  # 均匀图锚（TestFindPathUniform）

    def test_tiny_cap_falls_back_straight(self):
        # 极小 cap：绕墙查询必超限 → 兜底 [to]（真路径=3 航点，两者可区分）
        cfg = BalanceConfig(pathfind_max_expansions=1)
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        (p,), runs = self._astar_runs(w, [((500, 2500), (2500, 2500), False)], cfg)
        self.assertEqual(p, [(2500, 2500)])
        self.assertEqual(runs, 1)

    def test_boundary_success_iff_expansions_le_cap(self):
        # 成功 ⇔ 展开数 ≤ cap（判定在 goal 命中前）：扫描最小成功 cap=E——
        # cap=E 得真路径、cap=E−1 必兜底、cap<E 全兜底（E 落在 (2,40] 墙图量级自锚）
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        q = ((500, 2500), (2500, 2500), False)
        real = [(500, 4500), (2500, 4500), (2500, 2500)]
        e = None
        for cap in range(1, 41):
            cfg = BalanceConfig(pathfind_max_expansions=cap, pathfind_cache_entries=0)
            p = find_path(w, q[0], q[1], MovementClass.WHEEL, False, cfg)
            if p == real:
                e = cap
                break
            self.assertEqual(p, [(2500, 2500)])          # 未达 E 前一律直线兜底
        self.assertIsNotNone(e)
        self.assertGreater(e, 2)                         # 多步查询——首展开=起点格非 goal
        cfg_below = BalanceConfig(pathfind_max_expansions=e - 1, pathfind_cache_entries=0)
        self.assertEqual(find_path(w, q[0], q[1], MovementClass.WHEEL, False, cfg_below),
                         [(2500, 2500)])

    def test_cap_zero_means_unlimited(self):
        # 0=不限幅：绕墙照常真路径（与默认 cfg 位级一致）；不可达小图全图扫描照常兜底
        cfg0 = BalanceConfig(pathfind_max_expansions=0)
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        q = ((500, 2500), (2500, 2500), False)
        self.assertEqual(find_path(w, q[0], q[1], MovementClass.WHEEL, False, cfg0),
                         w.find_path(q[0], q[1], MovementClass.WHEEL, False))  # vs CONFIG
        small = world_with_layer(size=(4000, 4000),
                                 tiles=wall([(1, 0), (1, 1), (2, 1), (3, 0), (3, 1)]))
        self.assertEqual(find_path(small, (500, 500), (2500, 500),
                                   MovementClass.WHEEL, False, cfg0),
                         [(2500, 500)])                  # 全图扫描不被 cap=0 截断
                                                          # （注：本子句从输出不可观测——不可达
                                                          # 目标无论截断与否都返回 [to]，任何 cap
                                                          # 取值同果；本测试鉴别力在上方 cap=0 与
                                                          # 默认 cfg 位级一致子句，此句为无害补充——
                                                          # 2026-10-06 评审留痕）

    def test_over_limit_fallback_cached_same_cap(self):
        # 超限兜底入缓存（次贵分支不重付）：同 cfg 同查询两次 A* 只跑一次
        cfg = BalanceConfig(pathfind_max_expansions=1)
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        q = ((500, 2500), (2500, 2500), False)
        (p1, p2), runs = self._astar_runs(w, [q, q], cfg)
        self.assertEqual(runs, 1)
        self.assertEqual(p1, [(2500, 2500)])
        self.assertEqual(p1, p2)

    def test_cap_in_cache_key_no_masquerade(self):
        # cap 入键双向不冒充：小 cap 兜底入缓后调大 cap 同查询重算真路径；
        # 调回小 cap 再命中小 cap 旧条目（真路径条目不被小 cap 键命中）——两键并存
        w = world_with_layer(tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        q = ((500, 2500), (2500, 2500), False)
        real = [(500, 4500), (2500, 4500), (2500, 2500)]
        tiny = BalanceConfig(pathfind_max_expansions=1)
        big = BalanceConfig(pathfind_max_expansions=100000)
        (p_tiny,), runs1 = self._astar_runs(w, [q], tiny)
        self.assertEqual(p_tiny, [(2500, 2500)])
        (p_big,), runs2 = self._astar_runs(w, [q], big)  # 未吃小 cap 旧兜底条目
        self.assertEqual(runs2, 1)
        self.assertEqual(p_big, real)
        (p_again,), runs3 = self._astar_runs(w, [q], big)
        self.assertEqual(runs3, 0)                        # big 键命中
        (p_back,), runs4 = self._astar_runs(w, [q], tiny)
        self.assertEqual(runs4, 0)                        # tiny 旧条目仍在（容量内）
        self.assertEqual(p_back, [(2500, 2500)])
        self.assertEqual(len(w.path_cache), 2)            # 双 cap 键并存

    def test_cap_fallback_deterministic_zero_dice(self):
        # 限幅判定纯计数零掷骰：同 seed 双 world 同 cap 位级一致 + 8 通道 PCG32 不动
        cfg = BalanceConfig(pathfind_max_expansions=2)
        tiles = wall([(1, 0), (1, 1), (1, 2), (1, 3)])
        w1 = world_with_layer(seed=21, tiles=tiles)
        w2 = world_with_layer(seed=21, tiles=wall([(1, 0), (1, 1), (1, 2), (1, 3)]))
        before = [(w1.rng.rng(i).state, w1.rng.rng(i).inc) for i in range(8)]
        q = ((500, 2500), (2500, 2500), False)
        p1 = find_path(w1, q[0], q[1], MovementClass.WHEEL, False, cfg)
        p2 = find_path(w2, q[0], q[1], MovementClass.WHEEL, False, cfg)
        after = [(w1.rng.rng(i).state, w1.rng.rng(i).inc) for i in range(8)]
        self.assertEqual(p1, p2)
        self.assertEqual(p1, [(2500, 2500)])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
