"""寻路层（MOVEMENT_PSEUDOCODE_v1.2 §2.14 :404-417——MV-B-09 改B：本作自带整型 A*；
运行发起人 2026-10-02 裁决执行）。承载 World 三谓词 road_at / terrain_speed_tile_bp /
find_path 的算法本体（tick.py World 方法委托本模块）。零掷骰（契约⑰：移动零掷骰——
本模块不触碰任何 PCG32 通道）；全整型、零 float、零 math 超越函数。

§2.14 已定标（照写不动）：
  - tile_cost = INF                IF 瓦片 speed_bp == 0     # bp=0 防护=不可通行（水域/建筑）
  - tile_cost = round_div(100000000, bp)  OTHERWISE          # bp=10000 → 基准 10000（倒数取式）
  - IF prefer_road AND 瓦片 on_road: tile_cost = MAX(1, tile_cost // 2)   # 道路偏好=代价减半
  - 输出做共线航点化简（DIR8 段合并）；全遍历插入序确定
  - stub（TERRAIN 表未接入，World.terrain=None）：road_at=False /
    terrain_speed_tile_bp=None / find_path=直线直填 RETURN [to]（AMB-8）

发起人裁定的补充定标（§2.14/TECH-00:137 未规定——均记登记表 discrepancies）：
  - 瓦片边长=TerrainLayer.tile_cm（地图数据属性，默认 2500cm）
  - 对角步代价=入格 tile_cost × cfg.pathfind_diag_cost_bp // 10000（14142=√2 整型近似）
  - 启发式 h=octile 按代价模型自身取整折算：(M−k)×min_cost + k×(min_cost×
    pathfind_diag_cost_bp//10000)（min_cost=本次查询地形层内该 (class, prefer_road)
    下最小可行 tile_cost，缺省瓦片按类级缺省折算计入——纯数据推导；对角乘子与
    真实步代价同式 floor ⇒ admissible+consistent——评审修复 2026-10-02，原半舍入
    版本两性质俱失，见 find_path 内 h 注释）
  - 终点格 bp==0 或不可达 → 兜底 RETURN [to]（直线直填，同 AMB-8 stub 口径）
  - 展开限幅（PB-58 拍板「限幅」——PB-50 前置门，2026-10-06）：真实展开数（done 集
    增量）超 cfg.pathfind_max_expansions 即中止 → 同款兜底 RETURN [to]——最坏单查询
    耗时上界=cap×单展开成本（注：仅覆盖 A* 循环项——缓存未命中查询另有
    terrain_fingerprint（O(T log T)）与 _min_step_cost（O(T)）前置费用随列置瓦片数
    T 线性、不在 cap 内，致密大图档位评估总耗时须计入——PB-58 评审留痕）；
    0=不限幅。成功 ⇔ 展开数 ≤ cap（判定在 goal 命中前——
    目标作为第 cap+1 次展开同样熔断，纯计数零掷骰）
  - 禁切角：对角步要求两正交邻格皆可通行
  - 输出=DIR8 共线段合并后的转向格中心航点，末点替换为精确 to，不含起点
实现闭合规则（终止性必需，亦记 discrepancies）：地面寻路限定 world.map_extent 图内
瓦片（图外=不可通行）；起点格自身豁免通行检查（单位立足格必可达——离开即可）。

路径缓存（PB-10「缓存随消费侧接线再落」——2026-10-04 寻路接线块落地，消费侧=
movement.issue_move/_resolve_move_path 已真调用 find_path）：find_path 结果按
键存 world.path_cache（§D.6 未列实现记账槽；LRU 有界=cfg.pathfind_cache_entries，
0=禁用）。键含地形内容指纹（tiles 逐块内容+tile_cm+layer 身份+map_extent）——
地形层任何突变（增/删/原地改值/换层/改图界）天然换键失效，零行为差；cap
（pathfind_max_expansions）亦入键——cap 同为影响输出的 cfg 值（超限兜底 vs 真路径），
cap 变更=全量换键（与 diag_bp 同款机制，零特判）：cap 调大后旧「超限兜底」条目天然
失效、不冒充真路径结果。超限兜底与不可达兜底同形 RETURN [to] 且同入缓存（超限是
次贵分支——cap 内全图扫描，不缓存则每查询重付）。输出按
tuple 快照缓存、命中返回新 list（调用方 pop/extend 不腐蚀缓存）。缓存判定在
三处 O(1) 早退（terrain=None stub / 终点格不可通行 / 起终点同格）之后——
廉价分支不入缓存。frm 仅经起点格进键（find_path 体内 frm 唯一消费=
_tile_index——同格不同点输出恒等，按格入键提高命中且不失真）。零掷骰。
"""
from __future__ import annotations

import heapq

from .geom import round_div
from .tables import BalanceConfig, CONFIG
from .types import MovementClass

# DIR8 环序=geom.octant_deg 扇区 0°/45°/90°/.../315°（(0,1) 起）——固定遍历序保确定
# （勘察⑦：堆须 (f, 插入序号) 决胜；邻格遍历序同理冻结）。
DIR8 = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))

BASE_COST_NUMERATOR = 100000000   # §2.14 字面：round_div(100000000, bp)
_UNREACHABLE = 1 << 62            # g 初值哨兵（图界有限——任何真实 g 远小于此）


class TerrainTile:
    """§2.14 TERRAIN[tile]：on_road + speed_bp[class]（类缺席=类级缺省，读 None）。"""

    __slots__ = ("on_road", "speed_bp")

    def __init__(self, on_road: bool = False, speed_bp=None):
        self.on_road = on_road
        self.speed_bp = dict(speed_bp) if speed_bp else {}


class TerrainLayer:
    """地图层载体（挂 World.terrain；None=未接入→三谓词走 §2.14 stub 口径）。

    tile_cm=瓦片边长（发起人裁定：地图数据属性，默认 2500cm——TECH-00:134
    「20~50m 网格」带内取 25m）。tiles={(ix, iy): TerrainTile} 旁表：缺席瓦片=
    类级缺省（谓词 None→tables 缺省；寻路按缺省代价通行）。"""

    def __init__(self, tile_cm: int = 2500, tiles=None):
        self.tile_cm = tile_cm
        self.tiles = dict(tiles) if tiles else {}


# ── §2.14 三谓词本体（World 方法委托；world 鸭子消费面=terrain/map_extent）──

def road_at(world, pos) -> bool:
    """world.road_at(pos) → BOOL——TERRAIN[tile].on_road（§2.14 stub: False）。"""
    layer = world.terrain
    if layer is None:
        return False
    tile = layer.tiles.get((pos[0] // layer.tile_cm, pos[1] // layer.tile_cm))
    return tile is not None and tile.on_road


def terrain_speed_tile_bp(world, pos, movement_class: MovementClass):
    """world.terrain_speed_tile_bp(pos, class) → int|None——TERRAIN[tile].speed_bp[class]
    （§2.14 stub: None→类级缺省——tables.terrain_speed_bp(cls, None)）。"""
    layer = world.terrain
    if layer is None:
        return None
    tile = layer.tiles.get((pos[0] // layer.tile_cm, pos[1] // layer.tile_cm))
    if tile is None:
        return None
    return tile.speed_bp.get(movement_class)


def tile_cost(world, layer: TerrainLayer, cfg: BalanceConfig, ix: int, iy: int,
              movement_class: MovementClass, prefer_road: bool):
    """§2.14 瓦片代价定标式（逐字面照写）。返回 None=不可通行（INF 的实现承载：
    该瓦片不入开放集）。图外瓦片=不可通行（终止性闭合——见模块 docstring）。"""
    ext = world.map_extent
    t = layer.tile_cm
    if not (0 <= ix < (ext[0] + t - 1) // t and 0 <= iy < (ext[1] + t - 1) // t):
        return None                                   # 图外（含 ceil 半格）
    tile = layer.tiles.get((ix, iy))
    if tile is None:
        bp = cfg.terrain_speed_bp(movement_class)     # 缺席瓦片=类级缺省
        on_road = False
    else:
        bp = tile.speed_bp.get(movement_class)
        if bp is None:
            bp = cfg.terrain_speed_bp(movement_class)  # 类缺席=类级缺省
        on_road = tile.on_road
    if bp == 0:
        return None                                   # §2.14：bp==0 → INF 不可通行
    cost = round_div(BASE_COST_NUMERATOR, bp)
    if prefer_road and on_road:
        cost = max(1, cost // 2)                      # §2.14：道路偏好=代价减半
    return cost


def _min_step_cost(world, layer: TerrainLayer, cfg: BalanceConfig,
                   movement_class: MovementClass, prefer_road: bool) -> int:
    """启发式定标尺（发起人裁定③）：本次查询下最小可行单格代价——缺省瓦片按类级
    缺省折算计入，列置瓦片逐块算（bp==0 跳过；prefer_road 减半照 tile_cost 口径）。
    纯数据推导（零魔数）；h=octile×此值 ⇒ admissible+consistent（每步代价≥此值，
    octile 单调——证明见登记表）。"""
    default_bp = cfg.terrain_speed_bp(movement_class)
    if default_bp == 0:
        best = None                                   # 缺省瓦片全不可通行的退化守卫
    else:
        best = round_div(BASE_COST_NUMERATOR, default_bp)
    for tile in layer.tiles.values():
        bp = tile.speed_bp.get(movement_class)
        if bp is None:
            bp = default_bp
        if bp == 0:
            continue
        cost = round_div(BASE_COST_NUMERATOR, bp)
        if prefer_road and tile.on_road:
            cost = max(1, cost // 2)
        if best is None or cost < best:
            best = cost
    return best if best is not None else 0            # 全图无可行瓦片：h=0（Dijkstra 退化）


def _tile_index(layer: TerrainLayer, pos) -> tuple[int, int]:
    return (pos[0] // layer.tile_cm, pos[1] // layer.tile_cm)


def _tile_center(layer: TerrainLayer, ix: int, iy: int) -> tuple[int, int]:
    t = layer.tile_cm
    return (ix * t + t // 2, iy * t + t // 2)


def terrain_fingerprint(world, layer: TerrainLayer) -> tuple:
    """路径缓存键的地形内容指纹（PB-10 随消费侧落地）：逐块走 tiles 全内容
    （on_road + speed_bp 按枚举名排序）+ tile_cm + layer 身份 + world.map_extent。
    任何影响 find_path 输出的地形/图界状态突变均改变指纹 ⇒ 缓存天然失效——
    零行为差的正确性承载（排序后与 tiles 插入序无关——确定性）。O(列置瓦片数)，
    恒 ≤ 一次 A* 展开面，稀疏层近零开销。"""
    items = sorted(
        (((ix, iy), t.on_road,
          tuple(sorted((mc.name, v) for mc, v in t.speed_bp.items())))
         for (ix, iy), t in layer.tiles.items()))
    return (id(layer), layer.tile_cm, tuple(items), world.map_extent)


def find_path(world, frm, to, movement_class: MovementClass, prefer_road: bool,
              cfg: BalanceConfig = CONFIG) -> list:
    """§2.14 world.find_path(from, to, class, prefer_road) → list[(cm,cm)]
    （from 为 Python 关键字——形参名 frm，同 geom.approach_deg_of 适配先例）。

    - 地形层未接入（World.terrain=None）→ 直线直填 RETURN [to]（AMB-8 stub，不丢）；
    - 终点格不可通行（bp==0/图外）或全图不可达 → 同兜底 RETURN [to]（裁定④；
      §2.15 无物理碰撞，直线兜底不穿模）；
    - 真实展开数超 cfg.pathfind_max_expansions → 同兜底 RETURN [to]（PB-58 限幅
      保险丝——PB-50 前置门；0=不限幅；成功 ⇔ 展开数 ≤ cap）；
    - 否则整型 A*：开放堆 (f, 插入序号) 决胜、DIR8 固定序展开、禁切角、对角步
      ×cfg.pathfind_diag_cost_bp//10000；输出 DIR8 共线段合并后的转向格中心航点，
      末点替换为精确 to、不含起点（裁定⑥）；
    - A* 结果经 world.path_cache LRU 缓存（PB-10——键含 terrain_fingerprint 与
      pathfind_max_expansions，见模块 docstring；命中返回快照的新 list）。零掷骰。"""
    layer = world.terrain
    to_t = (to[0], to[1])
    if layer is None:
        return [to_t]                                 # AMB-8 stub：直线直填
    start = _tile_index(layer, frm)
    goal = _tile_index(layer, to)
    if tile_cost(world, layer, cfg, goal[0], goal[1], movement_class, prefer_road) is None:
        return [to_t]                                 # 裁决④：终点格不可通行→兜底
    if start == goal:
        return [to_t]
    cache = getattr(world, "path_cache", None)        # 防御：非 World 鸭子对象直通无缓存
    key = None
    if cache is not None and cfg.pathfind_cache_entries > 0:
        key = (start, goal, to_t, movement_class, prefer_road,
               cfg.pathfind_diag_cost_bp, cfg.pathfind_max_expansions,
               terrain_fingerprint(world, layer))
        cached = cache.get(key)
        if cached is not None:
            cache[key] = cache.pop(key)               # LRU 触碰（插入序=最近使用序）
            return list(cached)                       # 快照出新 list——调用方可变不腐蚀
    min_cost = _min_step_cost(world, layer, cfg, movement_class, prefer_road)
    diag_min_cost = min_cost * cfg.pathfind_diag_cost_bp // 10000

    def h(node: tuple[int, int]) -> int:
        # octile 按代价模型自身取整折算（评审修复 2026-10-02）：短轴腿乘子与真实
        # 对角步同式（min_cost×diag_bp//10000——floor 单调，c≥min_cost ⇒ 实步对角
        # 代价 ≥ diag_min_cost），故 h 逐边成立 h(n) ≤ cost(n,n') + h(n')（consistent）
        # 且沿最优路径归纳 h ≤ 真最优代价（admissible）。原 round_div(4142·k) 半舍入
        # 版本短轴项可上取整——均匀 WHEEL dx=dy=2 处 h=60000 > 真最优 56568，两性质
        # 俱失，A* 可返回次优路径（已由独立 Dijkstra 交叉验证测试复现并回归覆盖）。
        dx = abs(node[0] - goal[0])
        dy = abs(node[1] - goal[1])
        k = dx if dx < dy else dy
        return (max(dx, dy) - k) * min_cost + k * diag_min_cost

    g = {start: 0}
    parent = {}
    done = set()
    seq = 0
    cap = cfg.pathfind_max_expansions                    # PB-58 保险丝：0=不限幅
    open_heap = [(h(start), seq, start)]              # (f, 插入序号) 决胜——勘察⑦
    found = False
    while open_heap:
        _f, _s, node = heapq.heappop(open_heap)
        if node in done:
            continue
        done.add(node)
        if cap > 0 and len(done) > cap:
            break                                     # 超限熔断：found 保持 False →
                                                       # 落入下方兜底分支（同不可达口径）
        if node == goal:
            found = True
            break
        x0, y0 = node
        for dx, dy in DIR8:
            if dx != 0 and dy != 0:                   # 禁切角（裁定⑤）
                if (tile_cost(world, layer, cfg, x0 + dx, y0, movement_class,
                              prefer_road) is None
                        or tile_cost(world, layer, cfg, x0, y0 + dy, movement_class,
                                     prefer_road) is None):
                    continue
            step = tile_cost(world, layer, cfg, x0 + dx, y0 + dy,
                             movement_class, prefer_road)
            if step is None:
                continue
            if dx != 0 and dy != 0:                   # 对角步（裁定②）
                step = step * cfg.pathfind_diag_cost_bp // 10000
            nxt = (x0 + dx, y0 + dy)
            ng = g[node] + step
            if ng < g.get(nxt, _UNREACHABLE):
                g[nxt] = ng
                parent[nxt] = node
                seq += 1
                heapq.heappush(open_heap, (ng + h(nxt), seq, nxt))
    if not found:
        if key is not None:                           # 不可达/超限=最贵分支（近 Dijkstra
            cache[key] = (to_t,)                      # 全图扫描/cap 内全扫）——兜底结果同键
            while len(cache) > cfg.pathfind_cache_entries:  # 缓存（cap 已入键——见 docstring）
                cache.pop(next(iter(cache)))
        return [to_t]                                 # 裁决④/PB-58：全图不可达或超限→兜底
    chain = [goal]
    while chain[-1] != start:
        chain.append(parent[chain[-1]])
    chain.reverse()                                   # [start, ..., goal]
    out = []                                          # DIR8 共线段合并（§2.14）
    i = 1
    while i < len(chain):
        d0 = (chain[i][0] - chain[i - 1][0], chain[i][1] - chain[i - 1][1])
        j = i
        while j + 1 < len(chain):
            if (chain[j + 1][0] - chain[j][0], chain[j + 1][1] - chain[j][1]) != d0:
                break
            j += 1
        out.append(_tile_center(layer, chain[j][0], chain[j][1]))
        i = j + 1
    out[-1] = to_t                                    # 末点替换为精确 to（裁定⑥）
    if key is not None:
        cache[key] = tuple(out)                       # 不可变快照入缓存
        while len(cache) > cfg.pathfind_cache_entries:
            cache.pop(next(iter(cache)))              # LRU 驱逐最旧（插入序首键）
    return out
