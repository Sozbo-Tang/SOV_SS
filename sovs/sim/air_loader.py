"""航空卡 JSON 加载入口（GP-01 §1.2 / DATA-03 §2.4——仿 card_loader，stdlib-only）。

数据流：data/gen/cards_air.v1.json（tools/build_yaml.py 编译产物）→ WeaponTemplate
（空射武器档案）/AircraftTemplate（§D.1 静态 20）/ParatroopCardSpec（空降对表锚）。
运行时信任 JSON＋冻结构造器 TypeError 兜底（card_loader.py:3-5 同款纪律——
pydantic 校验在构建期完成，本模块不得 import pydantic）。

版本门/整型纪律与 card_loader 同款：SUPPORTED_CARD_SCHEMA 双写同值
（tests/test_card_pipeline 锁死互检）；_int() 以 type(v) is int 白名单放行
（拒 float/bool/str）。机型 weapons 按 [weapon_key, 弹量] 对引用档案池
（编译期已解引用校验——card_schema.AirLibraryModel；运行期共享同一 WeaponTemplate
实例，air_data.CARD_KWARGS 的元组结构同源）。

ParatroopCardSpec 自 air_data 迁入本模块（类与数据同源；air_data 薄壳再出口，
既有导入面零改）。空降 spec 三键（价/池/投送机型）由构建期自地面卡 delivery≠NONE
推导（build_yaml.build_air_library——不双写）；本模块构造时投送机型取机型池对象
（与 AIR_CARDS 同池——card_loader._check_paratroop_alignment 的 is 判定依赖同一性）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .air import AirRole, AircraftTemplate
from .types import (AltTier, DamageType, TargetDomain, Trajectory,
                    WeaponTemplate)

__all__ = [
    "AirLibrary", "AirLoaderError", "ParatroopCardSpec",
    "DEFAULT_AIR_LIBRARY_PATH", "load_air_library", "schema_version_supported",
]

#: 默认产物路径（仓库 data/gen；air_data 薄壳经此加载）
DEFAULT_AIR_LIBRARY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "gen" / "cards_air.v1.json")


class AirLoaderError(ValueError):
    """加载期错误（版本门/结构缺键/类型/枚举域/引用闭合）。"""


# ── 版本门（与 card_loader/card_schema 同值双写——tests 锁死互检）──
SUPPORTED_CARD_SCHEMA: dict[int, int] = {1: 6}


def schema_version_supported(version: str) -> bool:
    try:
        major_s, _, minor_s = version.partition(".")
        major, minor = int(major_s), int(minor_s)
    except ValueError:
        return False
    return major in SUPPORTED_CARD_SCHEMA and minor <= SUPPORTED_CARD_SCHEMA[major]


@dataclass(frozen=True, slots=True)
class ParatroopCardSpec:
    """空降卡 GDD 卡面字段记录（价/池/投送限定）——非 AircraftTemplate：
    落地 instantiate 走地面卡管线（air.py:8-15 自登记规划内增量；§A :688/:695）。
    地面侧全字段由地面卡管线承载（data/yaml/units/{su,ger}_infantry.yaml 空降两卡
    → data/gen/cards_ground.v1.json；card_loader._check_paratroop_alignment 加载期
    与本记录逐字段对表——C.3）。〔2026-10-12 GP-01 M1 起数据源＝cards_air.v1.json
    paratroops 段（构建期自地面卡推导）；原 air_data 内联两记录退役，冻结声明由
    DATA-03 接管。〕"""
    card_key: str
    name: str
    cost_points: int                 # 占预备队池（D017——不走空军预算）
    pool: str                        # "RESERVE"（预备队 5,000 分编制，GDD-00 D017）
    delivery: AircraftTemplate       # 唯一投送机型（"仅Li-2投送"/"仅Ju 52投送"）


@dataclass(frozen=True, slots=True)
class AirLibrary:
    """航空库运行期表示（三段：档案池/机型池/空降对表锚）。"""
    schema_version: str
    weapons: dict[str, WeaponTemplate]          # weapon_key → 档案（机型共享实例）
    aircraft: dict[str, AircraftTemplate]       # card_key → 机型
    paratroops: dict[str, ParatroopCardSpec]    # card_key → 空降卡记录


# ── 原始取值 helpers（card_loader 同款：缺键容旧＋类型严格 int/bool/str）──

def _int(d: dict, key: str, path: str, *, required: bool, default: int | None = None) -> int | None:
    if key not in d or d[key] is None:
        if required:
            raise AirLoaderError(f"{path}.{key} 缺失（必填键）")
        return default
    v = d[key]
    if type(v) is not int:  # 拒 float/bool/str——bool 为 int 子类须显式排除
        raise AirLoaderError(f"{path}.{key} 必须为 int（拒 float/bool/str）: {v!r}")
    return v


def _str(d: dict, key: str, path: str, *, required: bool, default: str | None = None) -> str | None:
    if key not in d or d[key] is None:
        if required:
            raise AirLoaderError(f"{path}.{key} 缺失（必填键）")
        return default
    v = d[key]
    if not isinstance(v, str):
        raise AirLoaderError(f"{path}.{key} 必须为 str: {v!r}")
    return v


def _bool(d: dict, key: str, path: str, *, required: bool, default: bool) -> bool:
    if key not in d or d[key] is None:
        if required:
            raise AirLoaderError(f"{path}.{key} 缺失（必填键）")
        return default
    v = d[key]
    if type(v) is not bool:
        raise AirLoaderError(f"{path}.{key} 必须为 bool: {v!r}")
    return v


def _enum(v: int, enum_cls: type, path: str, key: str):
    try:
        return enum_cls(v)
    except ValueError:
        raise AirLoaderError(
            f"{path}.{key}={v} 不在 {enum_cls.__name__} 枚举域") from None


# ── 冻结 dataclass 构造（缺一即 TypeError——完备性由构造承担）──

def _build_weapon(wd: dict, path: str) -> WeaponTemplate:
    """空射武器档案 JSON（int 表示）→ WeaponTemplate（air_data 七档同构）。"""
    return WeaponTemplate(
        name=_str(wd, "name", path, required=True),
        target_mask=_int(wd, "target_mask", path, required=False, default=1),
        damage_type=_enum(_int(wd, "damage_type", path, required=False, default=0),
                          DamageType, path, "damage_type"),
        pen_min=_int(wd, "pen_min", path, required=False, default=0),
        pen_max=_int(wd, "pen_max", path, required=False, default=0),
        damage=_int(wd, "damage", path, required=False, default=0),
        blast_radius_cm=_int(wd, "blast_radius_cm", path, required=False, default=0),
        max_range_cm=_int(wd, "max_range_cm", path, required=False, default=0),
        min_range_cm=_int(wd, "min_range_cm", path, required=False, default=0),
        dispersion_cm=_int(wd, "dispersion_cm", path, required=False, default=0),
        accuracy_base_bp=_int(wd, "accuracy_base_bp", path, required=False,
                              default=10000),
        aim_time_ticks=_int(wd, "aim_time_ticks", path, required=False, default=0),
        reload_time_ticks=_int(wd, "reload_time_ticks", path, required=False,
                               default=0),
        salvo=_int(wd, "salvo", path, required=False, default=1),
        ammo_base=_int(wd, "ammo_base", path, required=False, default=0),
        ammo_weight=_int(wd, "ammo_weight", path, required=False, default=1),
        projectile_speed_cm_tick=_int(wd, "projectile_speed_cm_tick", path,
                                      required=False, default=0),
        trajectory=_enum(_int(wd, "trajectory", path, required=False, default=0),
                         Trajectory, path, "trajectory"),
        suppression_power=_int(wd, "suppression_power", path, required=False,
                               default=0),
        crit_mod_permille=_int(wd, "crit_mod_permille", path, required=False,
                               default=1000),
        vs_fort_mult_permille=_int(wd, "vs_fort_mult_permille", path,
                                   required=False, default=1000),
        needs_deployed=_bool(wd, "needs_deployed", path, required=False,
                             default=False),
        combat_style=_int(wd, "combat_style", path, required=False, default=0),
        reveal_time_ticks=_int(wd, "reveal_time_ticks", path, required=False,
                               default=0),
    )


def _build_aircraft(ad: dict, path: str, archive: dict[str, WeaponTemplate]
                    ) -> AircraftTemplate:
    """机型卡 JSON → AircraftTemplate（§D.1 静态 20；weapons 档案池解引用）。"""
    refs = ad.get("weapons") or []
    if not isinstance(refs, list):
        raise AirLoaderError(f"{path}.weapons 必须为 list: {refs!r}")
    weapons: tuple = ()
    for i, pair in enumerate(refs):
        if not (isinstance(pair, list) and len(pair) == 2):
            raise AirLoaderError(
                f"{path}.weapons[{i}] 须为 [weapon_key, 弹量] 对: {pair!r}")
        wkey, ammo = pair
        if not isinstance(wkey, str) or wkey not in archive:
            raise AirLoaderError(
                f"{path}.weapons[{i}] 引用 {wkey!r} 不在空射武器档案池")
        if type(ammo) is not int or ammo < 1:
            raise AirLoaderError(f"{path}.weapons[{i}] 弹量须 ≥1: {ammo!r}")
        weapons += ((archive[wkey], ammo),)
    price_raw = ad.get("payload_price") or {}
    if not isinstance(price_raw, dict):
        raise AirLoaderError(f"{path}.payload_price 必须为对象: {price_raw!r}")
    payload_price: dict[str, int] = {}
    for k, v in price_raw.items():
        if type(v) is not int or v < 1:
            raise AirLoaderError(f"{path}.payload_price[{k}] 须为 ≥1 int: {v!r}")
        payload_price[k] = v
    return AircraftTemplate(
        template_id=_int(ad, "template_id", path, required=True),
        name=_str(ad, "name", path, required=True),
        role=_enum(_int(ad, "role", path, required=True), AirRole, path, "role"),
        cost_body=_int(ad, "cost_body", path, required=True),
        hp_max=_int(ad, "hp_max", path, required=True),
        armor_aa=_int(ad, "armor_aa", path, required=True),
        speed_cm_tick=_int(ad, "speed_cm_tick", path, required=True),
        dogfight_power=_int(ad, "dogfight_power", path, required=True),
        maneuver=_int(ad, "maneuver", path, required=True),
        alt_ceiling=_enum(_int(ad, "alt_ceiling", path, required=True),
                          AltTier, path, "alt_ceiling"),
        optics_air_cm=_int(ad, "optics_air_cm", path, required=False, default=0),
        recon_mark_base_bp=_int(ad, "recon_mark_base_bp", path, required=False,
                                default=0),
        weapons=weapons,
        payload_max_bombs=_int(ad, "payload_max_bombs", path, required=False,
                               default=0),
        payload_max_supply=_int(ad, "payload_max_supply", path, required=False,
                                default=0),
        paratroop_seats=_int(ad, "paratroop_seats", path, required=False,
                             default=0),
        turret_damage=_int(ad, "turret_damage", path, required=False, default=0),
        can_engage_air=_bool(ad, "can_engage_air", path, required=False,
                             default=False),
        has_dive=_bool(ad, "has_dive", path, required=False, default=False),
        payload_price=payload_price,
        can_afterburner=_bool(ad, "can_afterburner", path, required=False,
                              default=False),          # P1 机制块（schema 1.5）
        decoy_charges=_int(ad, "decoy_charges", path, required=False,
                           default=0),
        passive_evade_bp=_int(ad, "passive_evade_bp", path, required=False,
                              default=0),
    )


#: paratroops.pool int→令牌反查（card_schema.AirParatroopSpecModel.pool 恒 Literal
#  ["RESERVE"]＝D017 预备队池——单值域无漂移面；card_loader.VALUE_TOKEN["pool"] 同值）
_POOL_TOKEN = {1: "RESERVE"}


def _build_paratroop(pd: dict, path: str,
                     aircraft: dict[str, AircraftTemplate]) -> ParatroopCardSpec:
    delivery = _str(pd, "delivery", path, required=True)
    if delivery not in aircraft:
        raise AirLoaderError(f"{path}.delivery {delivery!r} 不在机型池")
    pool_v = _int(pd, "pool", path, required=True)
    pool = _POOL_TOKEN.get(pool_v)
    if pool is None:
        raise AirLoaderError(
            f"{path}.pool={pool_v} 不在 pool int 表示域（空降卡恒 RESERVE——D017）")
    return ParatroopCardSpec(
        card_key=_str(pd, "card_key", path, required=True),
        name=_str(pd, "name", path, required=True),
        cost_points=_int(pd, "cost_points", path, required=True),
        pool=pool,
        delivery=aircraft[delivery],
    )


def load_air_library(path: str | Path = DEFAULT_AIR_LIBRARY_PATH) -> AirLibrary:
    """航空库 JSON → AirLibrary（版本门 fail-fast/键类型/引用闭合/唯一性）。"""
    with open(path, encoding="utf-8") as f:
        root = json.load(f)
    if not isinstance(root, dict):
        raise AirLoaderError("航空库 JSON 根必须为对象")
    version = root.get("schema_version")
    if not isinstance(version, str) or not schema_version_supported(version):
        raise AirLoaderError(
            f"schema_version {version!r} 不在支持表 {SUPPORTED_CARD_SCHEMA}")
    weapons_raw = root.get("weapons")
    if not isinstance(weapons_raw, list) or not weapons_raw:
        raise AirLoaderError("weapons 必须为非空列表")
    archive: dict[str, WeaponTemplate] = {}
    for i, wd in enumerate(weapons_raw):
        wkey = _str(wd, "weapon_key", f"weapons[{i}]", required=True)
        if wkey in archive:
            raise AirLoaderError(f"weapon_key {wkey!r} 重复")
        archive[wkey] = _build_weapon(wd, f"weapons[{i}]")
    aircraft_raw = root.get("aircraft")
    if not isinstance(aircraft_raw, list) or not aircraft_raw:
        raise AirLoaderError("aircraft 必须为非空列表")
    aircraft: dict[str, AircraftTemplate] = {}
    seen_tids: dict[int, str] = {}
    for i, ad in enumerate(aircraft_raw):
        path_i = f"aircraft[{i}]"
        ckey = _str(ad, "card_key", path_i, required=True)
        if ckey in aircraft:
            raise AirLoaderError(f"card_key {ckey!r} 重复")
        tid = _int(ad, "template_id", path_i, required=True)
        if tid in seen_tids:
            raise AirLoaderError(
                f"template_id={tid} 重复（{seen_tids[tid]!r} 与 {ckey!r}）")
        seen_tids[tid] = ckey
        aircraft[ckey] = _build_aircraft(ad, path_i, archive)
    paratroops: dict[str, ParatroopCardSpec] = {}
    for i, pd in enumerate(root.get("paratroops") or []):
        pkey = _str(pd, "card_key", f"paratroops[{i}]", required=True)
        if pkey in paratroops:
            raise AirLoaderError(f"paratroops card_key {pkey!r} 重复")
        paratroops[pkey] = _build_paratroop(pd, f"paratroops[{i}]", aircraft)
    return AirLibrary(schema_version=version, weapons=archive,
                      aircraft=aircraft, paratroops=paratroops)
