r"""地形图数据管线 CLI（PB-58 块②「CSV 手写 2km 正式示范图」，2026-10-06；
docs/DATA-02-地形图数据格式冻结-v1.md 为格式规格权威）。

数据流（照 tools/build_cards.py 先例）：CSV（utf-8-sig，stdlib csv）→ 类型转换
（数值列显式 int 白名单 `-?\d+`——拒 "7.5"/"1_000"/公式注入；str 列拦 =,+,-,@
前缀）→ 确定性栅格化（矩形直填 + 折线 Bresenham 整型线 + 方形笔刷膨胀，文件序
画家算法后绘覆盖先绘）→ JSON（键排序、瓦片类型一律落 int 表示 0/1/2；同输入
两次构建字节相等）。

源表（单文件、一行一声明、kind 列分派——异构行不拆多表）：
  data/map_demo_2km.csv → data/gen/map_demo_2km.v1.json

行类型（列集=COLUMNS 并集；各行未用列必须留空——防错位手写）：
  map       map_key,extent_x_cm,extent_y_cm,tile_cm（全文件唯一必备行；图幅须被
            tile_cm 整除——图幅无关设计：换 2×2km 方形图零格式改动）
  rect      type,x0,y0,x1,y1（瓦片坐标含端点；type∈{ROAD,FOREST,RUIN}）
  polyline  type,width,verts（width=笔刷宽≥1 瓦片；verts="x:y;x:y;..."——
            build_cards 结构化列 `;` 分隔先例，顶点内 `:` 对；栅格化=逐段
            Bresenham 整型线（纯整数运算）+ width 方形笔刷）
  building  building_key,x_cm,y_cm,footprint_cm,hp（PB-57 建筑锚数据位占位——
            拍板清单:229「正式建筑布局随 PB-58 地图数据格式后接」；hp≥1
            [combat.hit_building hp<=0 即塌]，footprint/hp 均占位待数值章节定标）

瓦片语义（数值注入约定在 loader 侧、不在此处烘焙——gen JSON 只携带类型标记，
BalanceConfig.ruin_speed_bp 调值无需重建数据）：
  ROAD=0    on_road 瓦片（速度吃既有 MARCH 道路地板/prefer_road 减半，零注入）
  FOREST=1  旁挂 forest 集合（§2.12 拍板：森林不减速只喂 sensing——不入
            TerrainLayer.tiles，寻路侧与缺席瓦片恒等）
  RUIN=2    可通行减速占位（loader 注入 cfg.ruin_speed_bp——tables.py 占位
            待数值章节定标）
  缺席瓦片=旷野（类级缺省）

重叠语义：文件序画家算法——后绘覆盖先绘（FOREST 后绘抹掉瓦片表条目、ROAD/RUIN
后绘抹掉 forest 旁挂；路网在 CSV 中置于林区/废墟之后=道路穿林/穿村成街）。

纪律：数值一律严格 int；无 float/random/math 超越函数（Bresenham 纯整数）；
sha256 走 hashlib（审计哈希，非随机源）。CLI 可直跑：
python3 tools/build_map.py [--data-dir data] [--out-dir data/gen]。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

DATA_DIR_DEFAULT = Path(__file__).resolve().parents[1] / "data"
MAP_CSV_NAME = "map_demo_2km.csv"
MAP_JSON_NAME = "map_demo_2km.v1.json"
SCHEMA_VERSION = "1.0"
_INT_RE = re.compile(r"-?\d+")                 # 数值列白名单（build_cards 同款）
_FORMULA_PREFIXES = ("=", "+", "-", "@")       # 公式注入拦截（DATA-01 §1.5 同款）

# 瓦片类型令牌 → JSON int 表示（DATA-01 §2.4「JSON 一律落 int」同口径）
TYPE_TOKEN: dict[str, int] = {"ROAD": 0, "FOREST": 1, "RUIN": 2}

COLUMNS: tuple[str, ...] = (
    "kind", "map_key", "extent_x_cm", "extent_y_cm", "tile_cm",
    "type", "x0", "y0", "x1", "y1", "width", "verts",
    "building_key", "x_cm", "y_cm", "footprint_cm", "hp",
)
# 各 kind 的必填列分派（tok=瓦片类型令牌列；verts=结构化顶点列；其余列必须留空）
KIND_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "map": {"str": ("map_key",), "int": ("extent_x_cm", "extent_y_cm", "tile_cm")},
    "rect": {"tok": ("type",), "int": ("x0", "y0", "x1", "y1")},
    "polyline": {"tok": ("type",), "int": ("width",), "verts": ("verts",)},
    "building": {"str": ("building_key",),
                 "int": ("x_cm", "y_cm", "footprint_cm", "hp")},
}


class BuildError(ValueError):
    """地图管线构建期错误（CSV 层/栅格化层；一律 fail-fast 不落部分产物）。"""


# ── 原始转换 helpers（表/行/列上下文——build_cards 同款纪律）──

def _cell(table: str, rowno: int, row: dict[str, str], col: str) -> str:
    v = row.get(col)
    if v is None:
        raise BuildError(f"{table} 第 {rowno} 行缺列 {col}（表头未含）")
    return v.strip()


def _to_int(table: str, rowno: int, col: str, raw: str) -> int:
    if not _INT_RE.fullmatch(raw):
        raise BuildError(
            f"{table} 第 {rowno} 行 {col}={raw!r} 不是合法 int"
            f"（拒小数/下划线/公式——DATA-01 §1 同款）")
    return int(raw)


def _to_str(table: str, rowno: int, col: str, raw: str) -> str:
    if raw == "":
        raise BuildError(f"{table} 第 {rowno} 行 {col} 为空（必填列不得留空）")
    if raw[0] in _FORMULA_PREFIXES:
        raise BuildError(
            f"{table} 第 {rowno} 行 {col} 以 {raw[0]!r} 开头（公式注入拦截）")
    if ";" in raw or ":" in raw:
        raise BuildError(f"{table} 第 {rowno} 行 {col} 含结构化分隔符 ';'/':'")
    return raw


def _to_type_token(table: str, rowno: int, raw: str) -> int:
    if raw not in TYPE_TOKEN:
        raise BuildError(
            f"{table} 第 {rowno} 行 type={raw!r} 不在瓦片类型令牌集 "
            f"{sorted(TYPE_TOKEN)}")
    return TYPE_TOKEN[raw]


def _to_verts(table: str, rowno: int, raw: str) -> list[tuple[int, int]]:
    """结构化顶点列："x:y;x:y;..."（≥2 顶点；段内 `:` 恰 1 个、两段全 int）。"""
    parts = raw.split(";")
    if len(parts) < 2:
        raise BuildError(
            f"{table} 第 {rowno} 行 verts={raw!r} 须 ≥2 顶点（';' 分隔）")
    out: list[tuple[int, int]] = []
    for p in parts:
        p = p.strip()
        xs, sep, ys = p.partition(":")
        if not sep or not _INT_RE.fullmatch(xs) or not _INT_RE.fullmatch(ys):
            raise BuildError(f"{table} 第 {rowno} 行 verts 段 {p!r} 须为 x:y 两 int")
        out.append((int(xs), int(ys)))
    for i in range(1, len(out)):
        if out[i] == out[i - 1]:
            raise BuildError(
                f"{table} 第 {rowno} 行 verts 连续重复顶点 {out[i]}（剔除重言段）")
    return out


# ── CSV 读取（utf-8-sig；未知列拒；行内多余单元格拒；全空行=留白跳过）──

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        unknown = [c for c in fieldnames if c not in COLUMNS]
        if unknown:
            raise BuildError(f"{path.name} 表头未知列 {unknown}（extra=forbid 口径）")
        missing = [c for c in COLUMNS if c not in fieldnames]
        if missing:
            raise BuildError(f"{path.name} 表头缺列 {missing}")
        rows = []
        for i, row in enumerate(reader):
            if None in row:
                raise BuildError(f"{path.name} 第 {i + 2} 行单元格数多于表头列")
            if any(v is None for v in row.values()):
                raise BuildError(f"{path.name} 第 {i + 2} 行单元格数少于表头列")
            if not any((v or "").strip() for v in row.values()):
                continue
            rows.append(row)
    return rows


# ── 声明解析（kind 分派 + 未用列必须留空）──

def parse_rows(rows: list[dict[str, str]],
               table: str = MAP_CSV_NAME) -> dict:
    """原始行 → {'map': dict, 'shapes': [dict...], 'buildings': [dict...]}。

    shapes/地图声明保文件序（画家算法依赖）；类型转换与未用列检查逐行完成。
    table=错误消息里的源表名（R5 泛化：多图扫描时传各 CSV 文件名）。
    """
    decl: dict = {"map": None, "shapes": [], "buildings": []}
    for rowno, row in enumerate(rows, start=2):   # CSV 数据行号（表头=第 1 行）
        kind = _cell(table, rowno, row, "kind")
        if kind not in KIND_FIELDS:
            raise BuildError(
                f"{table} 第 {rowno} 行 kind={kind!r} 不在行类型集 "
                f"{sorted(KIND_FIELDS)}")
        fields = KIND_FIELDS[kind]
        used = {"kind"}
        for group in fields.values():
            used.update(group)
        for col in COLUMNS:                        # 未用列留空门（防错位手写）
            if col not in used and _cell(table, rowno, row, col) != "":
                raise BuildError(
                    f"{table} 第 {rowno} 行 {col}={row[col]!r} 非本行类型 "
                    f"{kind} 的列（未用列必须留空）")
        if kind == "map":
            if decl["map"] is not None:
                raise BuildError(f"{table} 第 {rowno} 行 map 行重复（全文件唯一）")
            decl["map"] = {
                "map_key": _to_str(table, rowno, "map_key",
                                   _cell(table, rowno, row, "map_key")),
                "extent_x_cm": _to_int(table, rowno, "extent_x_cm",
                                       _cell(table, rowno, row, "extent_x_cm")),
                "extent_y_cm": _to_int(table, rowno, "extent_y_cm",
                                       _cell(table, rowno, row, "extent_y_cm")),
                "tile_cm": _to_int(table, rowno, "tile_cm",
                                   _cell(table, rowno, row, "tile_cm")),
            }
        elif kind == "rect":
            decl["shapes"].append({
                "shape": "rect",
                "type": _to_type_token(table, rowno,
                                       _cell(table, rowno, row, "type")),
                "x0": _to_int(table, rowno, "x0", _cell(table, rowno, row, "x0")),
                "y0": _to_int(table, rowno, "y0", _cell(table, rowno, row, "y0")),
                "x1": _to_int(table, rowno, "x1", _cell(table, rowno, row, "x1")),
                "y1": _to_int(table, rowno, "y1", _cell(table, rowno, row, "y1")),
            })
        elif kind == "polyline":
            decl["shapes"].append({
                "shape": "polyline",
                "type": _to_type_token(table, rowno,
                                       _cell(table, rowno, row, "type")),
                "width": _to_int(table, rowno, "width",
                                 _cell(table, rowno, row, "width")),
                "verts": _to_verts(table, rowno, _cell(table, rowno, row, "verts")),
            })
        else:                                      # building
            decl["buildings"].append({
                "building_key": _to_str(table, rowno, "building_key",
                                        _cell(table, rowno, row, "building_key")),
                "x_cm": _to_int(table, rowno, "x_cm",
                                _cell(table, rowno, row, "x_cm")),
                "y_cm": _to_int(table, rowno, "y_cm",
                                _cell(table, rowno, row, "y_cm")),
                "footprint_cm": _to_int(table, rowno, "footprint_cm",
                                        _cell(table, rowno, row, "footprint_cm")),
                "hp": _to_int(table, rowno, "hp", _cell(table, rowno, row, "hp")),
            })
    if decl["map"] is None:
        raise BuildError(f"{table} 缺 map 行（全文件唯一必备行）")
    return decl


# ── 图界/坐标域校验（decl 归一后统一执行）──

def _check_decl(decl: dict, table: str = MAP_CSV_NAME) -> tuple[int, int]:
    m = decl["map"]
    ex, ey, t = m["extent_x_cm"], m["extent_y_cm"], m["tile_cm"]
    if ex <= 0 or ey <= 0 or t <= 0:
        raise BuildError(f"map 行图幅/瓦片边长须为正（得 {ex}×{ey}, tile={t}）")
    if ex % t != 0 or ey % t != 0:
        raise BuildError(
            f"map 行图幅 {ex}×{ey} 须被 tile_cm={t} 整除（瓦片覆盖无半格——"
            f"图界闭合=pathfind.tile_cost 的 (ext+t-1)//t 口径）")
    nx, ny = ex // t, ey // t
    for i, s in enumerate(decl["shapes"], start=2):
        where = f"{table} 第 {i} 行起声明的 {s['shape']}"
        if s["shape"] == "rect":
            x0, y0, x1, y1 = s["x0"], s["y0"], s["x1"], s["y1"]
            if x0 > x1 or y0 > y1:
                raise BuildError(f"{where} 角点逆序 ({x0},{y0})>({x1},{y1})")
            if not (0 <= x1 < nx and 0 <= y1 < ny and x0 >= 0 and y0 >= 0):
                raise BuildError(
                    f"{where} 越界 [{x0}..{x1}]×[{y0}..{y1}]（图内域 "
                    f"[0..{nx - 1}]×[0..{ny - 1}]）")
        else:
            if s["width"] < 1:
                raise BuildError(f"{where} width={s['width']} 须 ≥1（瓦片）")
            for vx, vy in s["verts"]:
                if not (0 <= vx < nx and 0 <= vy < ny):
                    raise BuildError(
                        f"{where} 顶点 ({vx},{vy}) 越界（图内域 "
                        f"[0..{nx - 1}]×[0..{ny - 1}]）")
    keys = set()
    for b in decl["buildings"]:
        if b["building_key"] in keys:
            raise BuildError(f"building_key {b['building_key']!r} 重复")
        keys.add(b["building_key"])
        if not (0 <= b["x_cm"] < ex and 0 <= b["y_cm"] < ey):
            raise BuildError(
                f"building {b['building_key']!r} 坐标 ({b['x_cm']},{b['y_cm']}) "
                f"越界（图内 [0..{ex})×[0..{ey})）")
        if b["footprint_cm"] < 1:
            raise BuildError(f"building {b['building_key']!r} footprint_cm 须 ≥1")
        if b["hp"] < 1:      # combat.hit_building：hp<=0 即塌——占位值不得选 0
            raise BuildError(f"building {b['building_key']!r} hp 须 ≥1")
    return nx, ny


# ── 确定性栅格化（Bresenham 整型线 + 方形笔刷 + 文件序画家）──

def line_tiles(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """整型 Bresenham 线（8 连通、纯整数运算、端点含；确定性锚=测试手推）。"""
    x0, y0 = a
    x1, y1 = b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    out = [(x, y)]
    while (x, y) != (x1, y1):
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
        out.append((x, y))
    return out


def brush_offsets(width: int) -> tuple[int, ...]:
    """方形笔刷单轴偏移：w=1→(0,)；w=2→(0,1)（向 +轴向延展）；w=3→(-1,0,1)。"""
    return tuple(range(-((width - 1) // 2), width // 2 + 1))


def rasterize(decl: dict, nx: int, ny: int) -> dict[tuple[int, int], int]:
    """声明 → {(ix,iy): 类型 int} 画布。文件序画家：后绘覆盖先绘（含跨类型
    抹除——FOREST 后绘抹掉瓦片表条目、ROAD/RUIN 后绘抹掉 forest 旁挂）。
    笔刷膨胀越图界裁剪（线本体必在界内——_check_decl 已拦）。"""
    canvas: dict[tuple[int, int], int] = {}
    for s in decl["shapes"]:
        paint: list[tuple[int, int]] = []
        if s["shape"] == "rect":
            paint = [(ix, iy)
                     for ix in range(s["x0"], s["x1"] + 1)
                     for iy in range(s["y0"], s["y1"] + 1)]
        else:
            offs = brush_offsets(s["width"])
            for a, b in zip(s["verts"], s["verts"][1:]):
                for cx, cy in line_tiles(a, b):
                    for dx in offs:
                        for dy in offs:
                            ix, iy = cx + dx, cy + dy
                            if 0 <= ix < nx and 0 <= iy < ny:
                                paint.append((ix, iy))
        for tile in paint:
            canvas[tile] = s["type"]
    return canvas


# ── 序列化（类型标记 int 表示；瓦片按 (ix,iy) 排序——字节稳定）──

def map_to_json_dict(decl: dict, canvas: dict, source_sha256: str) -> dict:
    tiles = sorted((ix, iy, tt) for (ix, iy), tt in canvas.items())
    return {
        "schema_version": SCHEMA_VERSION,
        "map_key": decl["map"]["map_key"],
        "source_sha256": source_sha256,
        "extent_x_cm": decl["map"]["extent_x_cm"],
        "extent_y_cm": decl["map"]["extent_y_cm"],
        "tile_cm": decl["map"]["tile_cm"],
        "tiles": [[ix, iy, tt] for ix, iy, tt in tiles],
        "buildings": [dict(b) for b in decl["buildings"]],   # 文件序（PB-57 数据位）
    }


def dump_stable_json(obj) -> str:
    """稳定序列化（build_cards.dump_stable_json 同式：键排序＋ensure_ascii=False
    ＋indent=2＋尾换行；同输入字节相等）。本模块零 pydantic 依赖——不 import
    build_cards（其顶部拖入 card_schema/pydantic），三行双写系刻意、测试锁死。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


# ── 主流程 ──

def build_map_csv(csv_path: Path, out_dir: Path) -> Path:
    """单图构建（R5 泛化）：任意 map_*.csv → data/gen/<map_key>.v1.json
    （产物名取 map 行的 map_key——fail-fast；返回写入路径）。"""
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise BuildError(f"缺源表 {csv_path.name}（{csv_path}）")
    decl = parse_rows(read_csv_rows(csv_path), table=csv_path.name)
    nx, ny = _check_decl(decl, table=csv_path.name)
    canvas = rasterize(decl, nx, ny)
    doc = map_to_json_dict(
        decl, canvas,
        hashlib.sha256(csv_path.read_bytes()).hexdigest())   # 源指纹（审计可复算）
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{decl['map']['map_key']}.v1.json"
    out.write_text(dump_stable_json(doc), encoding="utf-8", newline="\n")
    return out


def build_all(data_dir: Path, out_dir: Path) -> list[Path]:
    """多图扫描构建（R5）：data/map_*.csv 逐个 → gen JSON（文件名序确定）。"""
    data_dir = Path(data_dir)
    csvs = sorted(data_dir.glob("map_*.csv"))
    if not csvs:
        raise BuildError(f"{data_dir} 下无 map_*.csv 源表")
    return [build_map_csv(c, out_dir) for c in csvs]


def build_map(data_dir: Path, out_dir: Path) -> Path:
    """map CSV → gen JSON（fail-fast；返回写入路径）。
    （R5 泛化后保留的**单图 demo 入口**——tests/test_map_pipeline 契约面：
    固定读 MAP_CSV_NAME；多图扫描走 build_all/CLI 默认。）"""
    data_dir = Path(data_dir)
    return build_map_csv(data_dir / MAP_CSV_NAME, out_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="地形图数据管线：声明式 CSV → 确定性栅格化 → gen JSON")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR_DEFAULT,
                        help=f"源表所在目录（默认仓库 data/，含 {MAP_CSV_NAME}）")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="JSON 产物目录（默认 <data-dir>/gen）")
    parser.add_argument("--csv", type=Path, default=None,
                        help="单图构建（R5：指定某个 map_*.csv；缺省扫描全部）")
    args = parser.parse_args(argv)
    out_dir = args.out_dir or (args.data_dir / "gen")
    try:
        outs = ([build_map_csv(args.csv, out_dir)] if args.csv
                else build_all(args.data_dir, out_dir))
    except ValueError as exc:
        print(f"build_map: 构建失败——{exc}", file=sys.stderr)
        return 1
    for out in outs:
        print(f"build_map: 写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
