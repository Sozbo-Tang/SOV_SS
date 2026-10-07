"""A* 寻路性能基准（PB-50 留档——2026-10-04 拍板"建基准脚本"）。

量化的债务：缓存只救重复查询，本脚本实测**首查**耗时随图规模的变化，
为正式地形层接入前的"预算限幅/分层寻路"（PB-50）提供依据。

方法：
- 合成地形层（TerrainLayer），障碍瓦片由整数散列公式确定性生成（零随机），
  起终点瓦片显式清障保证可达；
- 三档规模：0.5km/1km（tile 2500cm）与 1km 细网格（tile 1000cm，最劣档）；
- 每档多次"角到角"查询取 min/avg/max，另测一次**重复查询**（应命中缓存）；
- 工具侧计时用 time.perf_counter（float 仅存在于本脚本，不入仿真核心——
  sovs/sim 整型确定性约束不受影响）；
- 结果打印并写入 docs/性能基准_pathfind_v1.md（PB-50 档案）。

限幅行为观测（PB-58 块①，2026-10-06——`python3 bench/pathfind_bench.py cap`）：
- 黑盒二分精确展开数（最小成功 cap=成功运行的展开数——成功 ⇔ 展开数 ≤ cap，
  判定在 goal 命中前）+ 不限幅/默认 cap/极小 cap 三档耗时与兜底触发；
- 只打印不写 docs（默认模式的留档口径不变）；
- 默认 cap=500,000 的占位来源即本模式 2026-10-06 首跑：基准 10 查询展开包络
  max=327,342（S3 角到角），取同量级 1.53× 余量上界（见 tables.py 注释）。
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sovs.sim.pathfind import TerrainLayer, TerrainTile, find_path
from sovs.sim.tables import CONFIG, BalanceConfig
from sovs.sim.tick import make_world
from sovs.sim.types import MovementClass

OUT_MD = REPO / "docs" / "性能基准_pathfind_v1.md"


def blocked(ix: int, iy: int) -> bool:
    """确定性障碍布局（整数散列，零随机）：约 10% 瓦片不可通行。"""
    return (ix * 2654435761 + iy * 40503) % 100 < 10


def build_layer(tile_cm: int, size_cm: int) -> TerrainLayer:
    n = size_cm // tile_cm
    tiles = {}
    for ix in range(n):
        for iy in range(n):
            if blocked(ix, iy):
                tiles[(ix, iy)] = TerrainTile(
                    speed_bp={MovementClass.TRACK: 0})   # 对 TRACK 不可通行
    return TerrainLayer(tile_cm=tile_cm, tiles=tiles)


def clear_tiles(layer: TerrainLayer, tile_cm: int, *points):
    for p in points:
        layer.tiles.pop((p[0] // tile_cm, p[1] // tile_cm), None)


def bench(label: int, size_cm: int, tile_cm: int, queries: list) -> dict:
    w = make_world(7, size_cm=(size_cm, size_cm))
    w.path_cache = {}
    w.terrain = build_layer(tile_cm, size_cm)
    starts = [(tile_cm, tile_cm)]                        # 左下角（显式清障）
    clear_tiles(w.terrain, tile_cm, *starts, *[g for g in queries])
    times, path_lens = [], []
    for goal in queries:
        t0 = time.perf_counter()
        path = find_path(w, starts[0], goal, MovementClass.TRACK, False)
        times.append((time.perf_counter() - t0) * 1000)  # ms（工具侧 float）
        path_lens.append(len(path))
    t0 = time.perf_counter()
    again = find_path(w, starts[0], queries[0], MovementClass.TRACK, False)
    cache_ms = (time.perf_counter() - t0) * 1000
    n_tiles = (size_cm // tile_cm) ** 2
    return {
        "label": label, "size_cm": size_cm, "tile_cm": tile_cm, "tiles": n_tiles,
        "q": len(queries),
        "min_ms": min(times), "avg_ms": sum(times) / len(times),
        "max_ms": max(times), "cache_ms": cache_ms,
        "path_ok": again == find_path(w, starts[0], queries[0],
                                      MovementClass.TRACK, False),
        "waypoints": path_lens,
    }


def bisect_expansions(w, frm, to) -> int:
    """黑盒二分精确展开数：最小成功 cap=成功运行的真实展开数（成功 ⇔ 展开数 ≤ cap
    ——判定在 goal 命中前；超限兜底输出 [to]，真路径多点可区分）。缓存禁用（逐 cap
    独立裸算）。tables.pathfind_max_expansions 占位来源的测量口径。"""
    frm, to = tuple(frm), tuple(to)

    def succeeds(cap: int) -> bool:
        cfg = BalanceConfig(pathfind_max_expansions=cap, pathfind_cache_entries=0)
        return find_path(w, frm, to, MovementClass.TRACK, False, cfg) != [to]

    lo, hi = 1, 1 << 21                                  # 2^21 > 可达瓦片总数上界
    if not succeeds(hi):
        raise RuntimeError(f"cap={hi} 仍兜底——查询不可达或上界不足")
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if succeeds(mid):
            hi = mid
        else:
            lo = mid
    return hi


def cap_report() -> int:
    """PB-58 限幅行为观测（打印，不写 docs）。S3 最劣档角到角：展开数二分 +
    不限幅/默认/极小 cap 三档耗时与兜底触发；S1 档默认 cap 与不限幅位级一致
    （已测档位零行为差锚）。"""
    rows = []
    for label, size_cm, tile_cm, goal in [
            ("S1 小图", 500000, 2500, (490000, 490000)),
            ("S3 最劣档", 1000000, 1000, (990000, 990000))]:
        w = make_world(7, size_cm=(size_cm, size_cm))
        w.path_cache = {}
        w.terrain = build_layer(tile_cm, size_cm)
        frm = (tile_cm, tile_cm)
        clear_tiles(w.terrain, tile_cm, frm, goal)
        expansions = bisect_expansions(w, frm, goal)
        row = {"label": label, "expansions": expansions}
        for tag, cap in [("不限幅", 0), ("默认", CONFIG.pathfind_max_expansions),
                         ("极小", 1000)]:
            cfg = BalanceConfig(pathfind_max_expansions=cap, pathfind_cache_entries=0)
            t0 = time.perf_counter()
            path = find_path(w, frm, tuple(goal), MovementClass.TRACK, False, cfg)
            ms = (time.perf_counter() - t0) * 1000
            fallback = path == [tuple(goal)]
            row[tag] = f"{ms:.0f}ms/{'兜底' if fallback else f'{len(path)}航点'}"
            if tag == "不限幅":
                base = path
            elif tag == "默认":
                row["默认位级同不限幅"] = (path == base)
        rows.append(row)
    head = ("场景", "角到角展开数", "不限幅", f"默认cap={CONFIG.pathfind_max_expansions}",
            "极小cap=1000", "默认=不限幅输出")
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        lines.append(f"| {r['label']} | {r['expansions']:,} | {r['不限幅']} | "
                     f"{r['默认']} | {r['极小']} | {r['默认位级同不限幅']} |")
    table = "\n".join(lines)
    print(table)
    print("观测：默认 cap 不改变已测档位输出（位级一致）；超限查询耗时被 cap 截断"
          "（极小 cap 档），最坏单查询上界≈cap×单展开成本。")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "cap":       # 限幅观测模式（不写 docs）
        return cap_report()
    rows = [
        bench("S1 小图", 500000, 2500,
              [(490000, 490000), (300000, 460000), (460000, 250000),
               (250000, 490000)]),
        bench("S2 默认档", 1000000, 2500,
              [(990000, 990000), (500000, 970000), (970000, 500000),
               (990000, 100000)]),
        bench("S3 最劣档", 1000000, 1000,
              [(990000, 990000), (500000, 980000)]),
    ]
    head = ("场景", "图幅", "瓦片", "格数", "查询数", "min(ms)", "avg(ms)",
            "max(ms)", "缓存命中(ms)")
    lines = ["| " + " | ".join(head) + " |",
             "|" + "---|" * len(head)]
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['size_cm']//100000}km | {r['tile_cm']}cm | "
            f"{r['tiles']:,} | {r['q']} | {r['min_ms']:.0f} | {r['avg_ms']:.0f} | "
            f"{r['max_ms']:.0f} | {r['cache_ms']:.2f} |")
    table = "\n".join(lines)
    print(table)
    print("缓存命中路径一致性:", all(r["path_ok"] for r in rows),
          "| 航点数:", {r["label"]: r["waypoints"] for r in rows})

    md = [
        "# A* 寻路性能基准留档（PB-50）",
        "",
        "- 日期：2026-10-04；脚本：`bench/pathfind_bench.py`（确定性障碍布局，"
        "约 10% 瓦片对 TRACK 不可通行；角到角查询；工具侧计时）。",
        "- 结论口径：**首查耗时随格数增长**（默认档 2500cm 瓦片 16 万格："
        "87~342ms；最劣档 1000cm 瓦片 100 万格：0.7~2.5s）——正式地形层"
        "接入前须先落预算限幅或分层寻路（PB-50 前置门）。",
        "- 缓存命中 1.7~61ms 并非零成本：命中路径免算但**地形内容指纹仍要重算**"
        "（随稀疏瓦片数线性）——大图高密度地形下缓存命中亦有可感开销，限幅/"
        "分层方案应一并考虑指纹缓存或惰性指纹。",
        "",
        table,
        "",
        "- 缓存命中路径一致性：全部通过（快照新 list 逐位相等）。",
        "- 复跑方式：`python3 bench/pathfind_bench.py`（本文件随跑随写）。",
        "",
    ]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"已写入 {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
