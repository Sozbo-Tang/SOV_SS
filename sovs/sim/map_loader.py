"""地形图 gen JSON 加载入口（PB-58 块②，2026-10-06；tools/build_map.py 的消费侧）。

stdlib-only（硬约束 5 同款：仿真核心运行时零第三方依赖——构建期校验在
tools/build_map.py 完成，运行时信任 JSON＋此处结构/类型/图界门兜底，
card_loader.py「缺一键即报错」同款纪律）。

整型纪律：_int() 以 type(v) is int 白名单放行（拒 float/bool/str——bool 是 int
子类必须显式排除）；无 float/random/math 超越函数。瓦片类型 JSON 一律 int 表示
（DATA-01 §2.4 同口径）：0=ROAD / 1=FOREST / 2=RUIN。

瓦片语义装配（数值注入归本模块单点——gen JSON 只携带类型标记，故
BalanceConfig.ruin_speed_bp 调值无需重建数据）：
  ROAD(0)  → TerrainTile(on_road=True)——不注入 speed_bp（速度吃既有 MARCH
             道路地板 movement.py:84-89 与 prefer_road 减半 pathfind.py:127-128）
  RUIN(2)  → TerrainTile(speed_bp=四类同值 cfg.ruin_speed_bp)——可通行减速占位
             （tables.py 无据占位待数值章节定标；bp==0 即不可通行——§2.14 口径）
  FOREST(1)→ 不入 layer.tiles（§2.12 拍板：森林不减速只喂 sensing——寻路侧与
             缺席瓦片恒等），旁挂 MapData.forest_tiles 集合；sensing 侧
             遮蔽通道已接（2026-10-07 感知接线块——apply_map 挂 world.
             forest_tiles，sensing.terrain_sensing_channels 装配 in_forest/
             forest_m 两通道喂 system_sensing/校射；原「待接不冒充」留痕就此
             收口，见 tick.py 登记表）
  缺席瓦片 = 旷野（三谓词走类级缺省——pathfind.py:107-109/115-118）

挂点（块③整局接入消费）：apply_map(world, md, cfg) 对齐 terrain/map_extent/
map_center（勘察③「场景工厂构造后赋 w.terrain」先例；make_world 本体不动）；
PB-57 建筑实体块（2026-10-06）增：md.buildings → Building 实体装配入
world.buildings（id=1 起文件序、garrison_slots=cfg 占位——见 apply_map docstring）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .pathfind import TerrainLayer, TerrainTile
from .tables import BalanceConfig, CONFIG
from .types import Building, MovementClass

__all__ = [
    "MapLoaderError", "BuildingSpec", "MapData", "load_map", "load_demo_map",
    "load_map_by_key", "apply_map", "SUPPORTED_MAP_SCHEMA",
]


class MapLoaderError(ValueError):
    """加载期错误（版本门/结构缺键/类型/枚举域/图界/重复键）。"""


# 版本门（schema "major.minor"——card_loader.SUPPORTED_CARD_SCHEMA 同判定式；
# 与 tools/build_map.SCHEMA_VERSION 单点双写，tests 锁死互检防漂移）
SUPPORTED_MAP_SCHEMA: dict[int, int] = {1: 0}

TYPE_ROAD, TYPE_FOREST, TYPE_RUIN = 0, 1, 2     # JSON int 表示（build_map.TYPE_TOKEN 值域）


def _map_schema_supported(version) -> bool:
    if not isinstance(version, str):
        return False
    major_s, _, minor_s = version.partition(".")
    try:
        major, minor = int(major_s), int(minor_s)
    except ValueError:
        return False
    return major in SUPPORTED_MAP_SCHEMA and minor <= SUPPORTED_MAP_SCHEMA[major]


def _int(v, path: str) -> int:
    if type(v) is not int:    # 拒 float/bool/str（card_loader._int 同款白名单）
        raise MapLoaderError(f"{path} 必须为 int（拒 float/bool/str）: {v!r}")
    return v


def _str(v, path: str) -> str:
    if not isinstance(v, str):
        raise MapLoaderError(f"{path} 必须为 str: {v!r}")
    return v


# 公式注入拦截前缀（build_map._FORMULA_PREFIXES 同款——DATA-01 §1.5/§2 :56 口径）
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _key_str(v, path: str) -> str:
    """字符串键门（PB-57 建筑实体块，2026-10-06——PB-58 评审遗留补齐）：map_key/
    building_key 拒空串/公式前缀(=,+,-,@)/含结构化分隔符 ';'/':'。规格=DATA-02
    §2 :56「building_key 禁 ;/:/公式前缀」；构建期 build_map._to_str 同款拦截
    可被手改 gen JSON 绕过——加载期消费 building_key 前收口（card_loader「缺一键
    即报错」同族 fail-fast）。"""
    s = _str(v, path)
    if s == "":
        raise MapLoaderError(f"{path} 不得为空串（必填键）")
    if s[0] in _FORMULA_PREFIXES:
        raise MapLoaderError(f"{path} 以 {s[0]!r} 开头（公式注入拦截——DATA-02 §2）")
    if ";" in s or ":" in s:
        raise MapLoaderError(f"{path} 含结构化分隔符 ';'/':'（DATA-02 §2）")
    return s


@dataclass(frozen=True, slots=True)
class BuildingSpec:
    """PB-57 建筑锚数据位透传记录（非 Building 实体——id 分配/驻楼槽归
    PB-57 集成侧；footprint_cm/hp=占位待数值章节定标，见 DATA-02 §5）。"""
    building_key: str
    x_cm: int
    y_cm: int
    footprint_cm: int
    hp: int


@dataclass(frozen=True, slots=True)
class MapData:
    """加载产物：TerrainLayer（可直挂 World.terrain）＋图幅/旁挂面。"""
    map_key: str
    extent: tuple[int, int]           # (extent_x_cm, extent_y_cm)
    tile_cm: int
    layer: TerrainLayer               # ROAD→on_road；RUIN→speed_bp；FOREST 不入
    forest_tiles: frozenset           # {(ix,iy)}——sensing 侧已接（§2.12；2026-10-07
                                       #   感知接线块：apply_map 挂 world.forest_tiles）
    buildings: tuple[BuildingSpec, ...]   # PB-57 数据位（文件序）


def _build_map_data(doc: dict, cfg: BalanceConfig) -> MapData:
    version = doc.get("schema_version")
    if not _map_schema_supported(version):
        raise MapLoaderError(
            f"schema_version {version!r} 不在支持表 {SUPPORTED_MAP_SCHEMA}"
            f"（major 不在表或 minor 超上界——DATA-02 §2）")
    ex = _int(doc.get("extent_x_cm"), "map.extent_x_cm")
    ey = _int(doc.get("extent_y_cm"), "map.extent_y_cm")
    t = _int(doc.get("tile_cm"), "map.tile_cm")
    if ex <= 0 or ey <= 0 or t <= 0:
        raise MapLoaderError(f"map 图幅/瓦片边长须为正（得 {ex}×{ey}, tile={t}）")
    if ex % t != 0 or ey % t != 0:
        raise MapLoaderError(f"map 图幅 {ex}×{ey} 须被 tile_cm={t} 整除（DATA-02 §3）")
    nx, ny = ex // t, ey // t
    tiles_raw = doc.get("tiles")
    if not isinstance(tiles_raw, list):
        raise MapLoaderError(f"map.tiles 必须为 list: {tiles_raw!r}")
    ruin_bp = cfg.ruin_speed_bp
    layer = TerrainLayer(tile_cm=t)
    forest: set[tuple[int, int]] = set()
    seen: set[tuple[int, int]] = set()
    for i, entry in enumerate(tiles_raw):
        path = f"map.tiles[{i}]"
        if not isinstance(entry, list) or len(entry) != 3:
            raise MapLoaderError(f"{path} 必须为 [ix, iy, type] 三元组: {entry!r}")
        ix = _int(entry[0], f"{path}[0]")
        iy = _int(entry[1], f"{path}[1]")
        tt = _int(entry[2], f"{path}[2]")
        if not (0 <= ix < nx and 0 <= iy < ny):
            raise MapLoaderError(
                f"{path} 瓦片 ({ix},{iy}) 越界（图内域 [0..{nx - 1}]×[0..{ny - 1}]）")
        if (ix, iy) in seen:
            raise MapLoaderError(f"{path} 瓦片 ({ix},{iy}) 重复（类型并列未定序）")
        seen.add((ix, iy))
        if tt == TYPE_ROAD:
            layer.tiles[(ix, iy)] = TerrainTile(on_road=True)
        elif tt == TYPE_RUIN:
            layer.tiles[(ix, iy)] = TerrainTile(speed_bp={
                MovementClass.FOOT: ruin_bp,
                MovementClass.WHEEL: ruin_bp,
                MovementClass.TRACK: ruin_bp,
                MovementClass.HORSE: ruin_bp,
            })
        elif tt == TYPE_FOREST:
            forest.add((ix, iy))
        else:
            raise MapLoaderError(f"{path} 瓦片类型 {tt} 不在 int 表示域 {{0,1,2}}")
    buildings_raw = doc.get("buildings")
    if not isinstance(buildings_raw, list):
        raise MapLoaderError(f"map.buildings 必须为 list: {buildings_raw!r}")
    specs: list[BuildingSpec] = []
    keys: set[str] = set()
    for i, b in enumerate(buildings_raw):
        path = f"map.buildings[{i}]"
        if not isinstance(b, dict):
            raise MapLoaderError(f"{path} 必须为对象: {b!r}")
        key = _key_str(b.get("building_key"), f"{path}.building_key")
        if key in keys:
            raise MapLoaderError(f"{path} building_key {key!r} 重复")
        keys.add(key)
        x = _int(b.get("x_cm"), f"{path}.x_cm")
        y = _int(b.get("y_cm"), f"{path}.y_cm")
        fp = _int(b.get("footprint_cm"), f"{path}.footprint_cm")
        hp = _int(b.get("hp"), f"{path}.hp")
        if not (0 <= x < ex and 0 <= y < ey):
            raise MapLoaderError(f"{path} 坐标 ({x},{y}) 越界（图内 [0..{ex})×[0..{ey})）")
        if fp < 1 or hp < 1:
            raise MapLoaderError(f"{path} footprint_cm/hp 须 ≥1（hp=0 即塌——combat.hit_building）")
        specs.append(BuildingSpec(building_key=key, x_cm=x, y_cm=y,
                                  footprint_cm=fp, hp=hp))
    return MapData(
        map_key=_key_str(doc.get("map_key"), "map.map_key"),
        extent=(ex, ey),
        tile_cm=t,
        layer=layer,
        forest_tiles=frozenset(forest),
        buildings=tuple(specs),
    )


def load_map(path: str | Path, cfg: BalanceConfig = CONFIG) -> MapData:
    """gen JSON → MapData（版本门＋结构/类型/图界/重复键校验；fail-fast）。"""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        raise MapLoaderError("地图 JSON 根必须为对象")
    return _build_map_data(doc, cfg)


def load_map_by_key(map_key: str, cfg: BalanceConfig = CONFIG) -> MapData:
    """按 map_key 读 data/gen/<key>.v1.json（R5 场景骨架——多图消费入口；
    map_key 经 _key_str 同款门（公式前缀/结构化分隔符拒）。"""
    import re as _re
    if (not isinstance(map_key, str) or map_key == ""
            or map_key[0] in _FORMULA_PREFIXES
            or not _re.fullmatch(r"[A-Za-z0-9_]+", map_key)):
        raise MapLoaderError(f"map_key {map_key!r} 非法（空/公式前缀/非法字符）")
    return load_map(Path(__file__).resolve().parents[2] / "data" / "gen"
                    / f"{map_key}.v1.json", cfg)


def load_demo_map(cfg: BalanceConfig = CONFIG) -> MapData:
    """正式示范图便捷入口（R5 起委托 load_map_by_key——行为不变；
    data/gen/map_demo_2km.v1.json，B 图幅 200000×100000=80×40 瓦片，
    2026-10-05 发起人默认裁决留痕见 DATA-02 §2）。"""
    return load_map_by_key("demo_2km", cfg)


def garrison_slots_for(footprint_cm: int, cfg: BalanceConfig = CONFIG) -> int:
    """楼型分级派生驻楼容量（2026-10-06 发起人拍板：小/中/大楼=1/2/3 个步兵排，
    容量按排=单位数计）：footprint < 小阈值→1 排、< 中阈值→2 排、否则 3 排。
    阈值 cfg.building_size_footprint_max_cm 占位（无文档锚，数值章节定标）。"""
    if footprint_cm < cfg.building_size_footprint_max_cm[0]:
        return cfg.building_garrison_slots_small
    if footprint_cm < cfg.building_size_footprint_max_cm[1]:
        return cfg.building_garrison_slots_medium
    return cfg.building_garrison_slots_large


def apply_map(world, md: MapData, cfg: BalanceConfig = CONFIG) -> None:
    """地图挂载（勘察③接入面：make_world 构造后赋 w.terrain＋对齐图界/中心——
    test_pathfinding.world_with_layer / bench/pathfind_bench.py 先例；
    make_world 本体不动、缺省 terrain=None stub 口径保持）。
    感知接线块（2026-10-07）：＋挂 world.forest_tiles=md.forest_tiles（§2.12
    森林旁挂集——sensing 遮蔽通道数据源，PB-53 留待项②/GAP-27 收口；纯地形
    用户无行为差口径随接线失效：林区自此真实喂探测衰减）。

    PB-57 建筑实体块（2026-10-06）：md.buildings（BuildingSpec 文件序）→ Building
    实体入 world.buildings——「数据后接」闭环（拍板清单:229）：id=1 起文件序
    （确定性必需：整局指纹 B 段消费 b.id；元素 id 单位内 enumerate 同款先例
    make_unit）、hp=spec.hp（CSV building 行，PB-58 数据位占位）、garrison_slots=
    garrison_slots_for(spec.footprint_cm, cfg)（2026-10-06 发起人拍板：小/中/大楼=
    1/2/3 排按 footprint 派生——阈值占位见 tables.py 注）。建筑不入瓦片层——pathfind/sensing 零扰动（纯
    terrain 用户无行为差）；extend 追加不替换（合成建筑并存供单测；重复挂图=
    调用方纪律，同 terrain 重复赋值口径）。"""
    world.terrain = md.layer
    world.forest_tiles = md.forest_tiles   # §2.12 森林旁挂集→World（sensing 遮蔽通道
                                           # 数据源——2026-10-07 感知接线块：PB-53 留待
                                           # 项②/GAP-27 收口，消费=sensing.
                                           # terrain_sensing_channels 单点装配）
    world.map_extent = md.extent
    world.map_center = (md.extent[0] // 2, md.extent[1] // 2)
    world.buildings.extend(
        Building(id=i, pos=(spec.x_cm, spec.y_cm), hp=spec.hp,
                 garrison_slots=garrison_slots_for(spec.footprint_cm, cfg))
        for i, spec in enumerate(md.buildings, start=1))
