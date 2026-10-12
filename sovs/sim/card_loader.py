"""仿真侧 JSON 加载入口（TECH-00 §9 M0「JSON 加载」；DATA-01 §9 映射表逐参数对齐）。

stdlib-only（硬约束 5：仿真核心运行时零第三方依赖——pydantic 校验在构建期
tools/build_cards.py 完成，运行时信任 JSON＋冻结构造器 TypeError 兜底，
air_data.py:126-127「缺一键即 TypeError，完备性由构造承担」先例）。

JSON 口径（DATA-01 §2.4）：枚举一律 int 值；令牌反查表 VALUE_TOKEN（int→str）为
card_schema.TOKEN_VALUE 的反向、版本门 SUPPORTED_CARD_SCHEMA 与
card_schema.SUPPORTED_CARD_SCHEMA 同值——两处双写皆因本模块不得 import pydantic
（DATA-01 §12 D-1 同类约束），由 tests/test_card_pipeline.py 锁死互检防漂移。

deck 阈值（D032 类别默认/D011 配额/R-13 子配额/D038 点数）本模块一律不自带——
DATA-01 §12 D-1：tables.py 归口完成前唯一权威＝card_schema.py，本模块不得另抄一份
（无双轨）；validate_deck 显式注入（调用方自 card_schema，归口迁移后自
tables.BalanceConfig 取值——机制就位、数值可配）。

整型纪律：_int() 以 type(v) is int 白名单放行（拒 float/bool/str——bool 是 int
子类必须显式排除）；无 float/random/math 超越函数。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .air_data import JU52, LI2, PARATROOP_CARDS
from .types import (AltProfile, AltTier, Armor, Aura, AuraKind, DamageType,
                    ElementType, ElementTemplate, MovementClass,
                    SelfDefenseProfile, Trajectory, UnitFlag, UnitTemplate,
                    UnitType, WeaponTemplate)

__all__ = [
    "CardLoaderError", "CardRecord", "DeckData", "load_deck", "load_library",
    "schema_version_supported", "validate_deck",
]


class CardLoaderError(ValueError):
    """加载期错误（版本门/结构缺键/类型/枚举域/唯一性/空降对表）。"""


# ── 版本门（与 card_schema.SUPPORTED_CARD_SCHEMA 同值双写——tests 锁死互检；
#    1.3→1.4＝2026-10-12 GP-01 §1.3 航空入库 minor，card_schema.py:48 同步）──
SUPPORTED_CARD_SCHEMA: dict[int, int] = {1: 4}


def schema_version_supported(version: str) -> bool:
    """major 在支持表内且 minor ≤ 上界（DATA-01 §2.2——与 card_schema 同判定）。"""
    try:
        major_s, _, minor_s = version.partition(".")
        major, minor = int(major_s), int(minor_s)
    except ValueError:
        return False
    return major in SUPPORTED_CARD_SCHEMA and minor <= SUPPORTED_CARD_SCHEMA[major]


# ── int→令牌反查（JSON int 表示——DATA-01 §4.2；card_schema.TOKEN_VALUE 反向表）──
VALUE_TOKEN: dict[str, dict[int, str]] = {
    "faction": {0: "SOVIET", 1: "GERMAN"},
    "category": {0: "RECON", 1: "INFANTRY", 2: "ARMOR", 3: "FIRE_SUPPORT",
                 4: "AA_LOGISTICS"},
    "pool": {0: "MAIN", 1: "RESERVE"},
    "quota_group": {0: "NONE", 1: "HOWITZER", 2: "AT_GUN", 3: "ROCKET"},
    "delivery": {0: "NONE", 1: "LI2", 2: "JU52"},
}

#: 空降投送机型对表（DATA-01 §8 空降两卡行/C.3——air_data.ParatroopCardSpec.delivery）
_DELIVERY_AIRCRAFT = {"LI2": LI2, "JU52": JU52}


@dataclass(frozen=True, slots=True)
class CardRecord:
    """卡记录（DATA-01 §9）：UnitTemplate＋卡记录层字段（不进冻结 dataclass 的 8 键）。"""
    card_key: str
    unit_template: UnitTemplate
    faction: str            # 令牌（SOVIET/GERMAN）
    pool: str               # 令牌（MAIN/RESERVE）
    per_card_limit: int | None   # None＝按类别默认（D032——由 validate_deck 注入表解析）
    quota_group: str        # 令牌（NONE/HOWITZER/AT_GUN/ROCKET）
    unlock_by: str
    delivery: str           # 令牌（NONE/LI2/JU52）
    provenance: tuple[dict, ...] = ()  # DATA-01 §6.2 旁键透传（构造 dataclass 时忽略映射）


@dataclass(frozen=True, slots=True)
class DeckData:
    """deck JSON 运行期表示（schema_version/faction 已令牌化）。"""
    schema_version: str
    deck_key: str
    faction: str
    cards: tuple[tuple[str, int], ...]   # (card_key, copies)
    points_main_cap: int | None = None       # JSON 缺省→validate_deck 用注入值
    points_reserve_cap: int | None = None


# ── 原始取值 helpers（缺键容旧（DATA-01 §2.3-1 演进兼容）；类型严格 int）──

def _int(d: dict, key: str, path: str, *, required: bool, default: int | None = None) -> int | None:
    if key not in d or d[key] is None:
        if required:
            raise CardLoaderError(f"{path}.{key} 缺失（必填键）")
        return default
    v = d[key]
    if type(v) is not int:  # 拒 float/bool/str——bool 为 int 子类须显式排除
        raise CardLoaderError(f"{path}.{key} 必须为 int（拒 float/bool/str）: {v!r}")
    return v


def _str(d: dict, key: str, path: str, *, required: bool, default: str | None = None) -> str | None:
    if key not in d or d[key] is None:
        if required:
            raise CardLoaderError(f"{path}.{key} 缺失（必填键）")
        return default
    v = d[key]
    if not isinstance(v, str):
        raise CardLoaderError(f"{path}.{key} 必须为 str: {v!r}")
    return v


def _bool(d: dict, key: str, path: str, *, required: bool, default: bool) -> bool:
    if key not in d or d[key] is None:
        if required:
            raise CardLoaderError(f"{path}.{key} 缺失（必填键）")
        return default
    v = d[key]
    if type(v) is not bool:
        raise CardLoaderError(f"{path}.{key} 必须为 bool: {v!r}")
    return v


def _list(d: dict, key: str, path: str, *, required: bool, default: list | None = None) -> list | None:
    if key not in d or d[key] is None:
        if required:
            raise CardLoaderError(f"{path}.{key} 缺失（必填键）")
        return default
    v = d[key]
    if not isinstance(v, list):
        raise CardLoaderError(f"{path}.{key} 必须为 list: {v!r}")
    return v


def _enum(d: dict, key: str, enum_cls: type, path: str, *, required: bool, default=None):
    v = _int(d, key, path, required=required, default=default)
    if v is None:
        return None
    try:
        return enum_cls(v)
    except ValueError:
        raise CardLoaderError(
            f"{path}.{key}={v} 不在 {enum_cls.__name__} 枚举域") from None


def _token(d: dict, key: str, domain: str, path: str) -> str:
    """管线自编域（faction/pool/quota_group/delivery——无 types 枚举）int→令牌反查。"""
    v = _int(d, key, path, required=True)
    tok = VALUE_TOKEN[domain].get(v)  # type: ignore[arg-type]
    if tok is None:
        raise CardLoaderError(
            f"{path}.{key}={v} 不在 {domain} int 表示域 {sorted(VALUE_TOKEN[domain])}")
    return tok


def _dict_of(d: dict, key: str, path: str) -> dict:
    v = d.get(key)
    if not isinstance(v, dict):
        raise CardLoaderError(f"{path}.{key} 必须为对象: {v!r}")
    return v


def _category_token(category: int | None) -> str:
    """UnitTemplate.category（int 0..4）→ 令牌（deck 分桶与注入配额表键对齐）。"""
    tok = VALUE_TOKEN["category"].get(category)  # type: ignore[arg-type]
    if tok is None:
        raise CardLoaderError(
            f"category={category} 不在 category int 表示域 {sorted(VALUE_TOKEN['category'])}")
    return tok


# ── 冻结 dataclass 构造（DATA-01 §9 映射表——逐参数显式 kwarg，缺一即 TypeError）──

def _build_weapon(wd: dict, path: str) -> WeaponTemplate:
    """WeaponRowModel JSON（int 表示）→ WeaponTemplate（27 模板字段；2 管线键丢弃）。"""
    rp_raw = _list(wd, "restricted_profiles", path, required=False, default=[]) or []
    restricted = tuple(
        (_int(p, "count", f"{path}.restricted_profiles[{i}]", required=True),
         _int(p, "pen_bonus", f"{path}.restricted_profiles[{i}]", required=True))
        for i, p in enumerate(rp_raw))
    alt_raw = wd.get("alt_profile")
    alt = None
    if alt_raw is not None:
        alt_d = _dict_of(wd, "alt_profile", path)
        alt = AltProfile(
            damage=_int(alt_d, "damage", f"{path}.alt_profile", required=True),
            blast_radius_cm=_int(alt_d, "blast_radius_cm", f"{path}.alt_profile",
                                 required=True))
    sd_raw = wd.get("self_defense")
    self_def = None
    if sd_raw is not None:
        sd_d = _dict_of(wd, "self_defense", path)
        self_def = SelfDefenseProfile(
            max_range_cm=_int(sd_d, "max_range_cm", f"{path}.self_defense", required=True),
            accuracy_mult_bp=_int(sd_d, "accuracy_mult_bp", f"{path}.self_defense",
                                  required=True))
    return WeaponTemplate(
        name=_str(wd, "name", path, required=True),
        target_mask=_int(wd, "target_mask", path, required=False,
                         default=1),  # types 默认 TargetDomain.GROUND=1
        damage_type=_enum(wd, "damage_type", DamageType, path,
                          required=False, default=0),
        pen_min=_int(wd, "pen_min", path, required=False, default=0),
        pen_max=_int(wd, "pen_max", path, required=False, default=0),
        damage=_int(wd, "damage", path, required=False, default=0),
        blast_radius_cm=_int(wd, "blast_radius_cm", path, required=False, default=0),
        max_range_cm=_int(wd, "max_range_cm", path, required=True),
        min_range_cm=_int(wd, "min_range_cm", path, required=False, default=0),
        dispersion_cm=_int(wd, "dispersion_cm", path, required=False, default=0),
        accuracy_base_bp=_int(wd, "accuracy_base_bp", path, required=False, default=10000),
        aim_time_ticks=_int(wd, "aim_time_ticks", path, required=False, default=0),
        reload_time_ticks=_int(wd, "reload_time_ticks", path, required=False, default=0),
        salvo=_int(wd, "salvo", path, required=False, default=1),
        ammo_base=_int(wd, "ammo_base", path, required=False, default=0),
        ammo_weight=_int(wd, "ammo_weight", path, required=False, default=0),
        projectile_speed_cm_tick=_int(wd, "projectile_speed_cm_tick", path,
                                      required=False, default=0),
        trajectory=_enum(wd, "trajectory", Trajectory, path,
                         required=False, default=0),
        suppression_power=_int(wd, "suppression_power", path, required=False, default=0),
        crit_mod_permille=_int(wd, "crit_mod_permille", path, required=False, default=1000),
        vs_fort_mult_permille=_int(wd, "vs_fort_mult_permille", path,
                                   required=False, default=1000),
        needs_deployed=_bool(wd, "needs_deployed", path, required=False, default=False),
        combat_style=_int(wd, "combat_style", path, required=False, default=0),
        reveal_time_ticks=_int(wd, "reveal_time_ticks", path, required=False, default=0),
        restricted_profiles=restricted,
        alt_profile=alt,
        self_defense=self_def,
    )


def _build_armor(d: dict, path: str) -> Armor:
    return Armor(
        front=_int(d, "front", path, required=True),
        side=_int(d, "side", path, required=True),
        rear=_int(d, "rear", path, required=True),
        top=_int(d, "top", path, required=True),
    )


def _build_element(ed: dict, path: str) -> ElementTemplate:
    """ElementModel JSON → ElementTemplate（15 参数；count 用于上层展开、element_key 丢弃）。"""
    weapons_raw = _list(ed, "weapons", path, required=False, default=[]) or []
    weapons = tuple(_build_weapon(w, f"{path}.weapons[{i}]")
                    for i, w in enumerate(weapons_raw))
    by_key = {}
    for i, w in enumerate(weapons_raw):
        wkey = _str(w, "weapon_key", f"{path}.weapons[{i}]", required=True)
        if wkey in by_key:
            raise CardLoaderError(f"{path}.weapons 内 weapon_key {wkey!r} 重复")
        by_key[wkey] = weapons[i]
    mounted_raw = _list(ed, "mounted_armament", path, required=False)
    mounted = None
    if mounted_raw is not None:
        mounted = tuple()
        for i, wkey in enumerate(mounted_raw):
            if not isinstance(wkey, str) or wkey not in by_key:
                raise CardLoaderError(
                    f"{path}.mounted_armament[{i}]={wkey!r} 不在本元素 weapons 键集")
            mounted += (by_key[wkey],)
    ak = ed.get("armor_ke")
    ah = ed.get("armor_he")
    return ElementTemplate(
        element_type=_enum(ed, "element_type", ElementType, path, required=True),
        unit_type=_enum(ed, "unit_type", UnitType, path, required=True),
        hp_max=_int(ed, "hp_max", path, required=True),
        armor_ke=_build_armor(_dict_of(ed, "armor_ke", path), f"{path}.armor_ke")
        if ak is not None else None,
        armor_he=_build_armor(_dict_of(ed, "armor_he", path), f"{path}.armor_he")
        if ah is not None else None,
        fire_arc_deg=_int(ed, "fire_arc_deg", path, required=False, default=360),
        suppression_vuln_permille=_int(ed, "suppression_vuln_permille", path,
                                       required=False, default=1000),
        squad_quality_bp=_int(ed, "squad_quality_bp", path, required=False, default=10000),
        weapons=weapons,
        seats=_int(ed, "seats", path, required=False, default=0),
        mounted_armament=mounted,
        cargo_rounds_max=_int(ed, "cargo_rounds_max", path, required=False, default=0),
        cargo_medical_max=_int(ed, "cargo_medical_max", path, required=False, default=0),
        cargo_weight_max=_int(ed, "cargo_weight_max", path, required=False, default=0),
        self_smoke_charges=_int(ed, "self_smoke_charges", path,
                                required=False, default=0),  # PB-53（0=无自卫烟幕能力）
    )


def _build_unit(cd: dict, path: str) -> UnitTemplate:
    """UnitCardModel JSON → UnitTemplate（25 参数全显式——DATA-01 §9 映射总表）。

    size_factor_bp 不映射（DATA-01 §10 G-1：无消费点，loader 丢弃——不 log，
    零渲染依赖纪律下以本注释登记）；elements 经 count 展开为扁平元组（D.1#5）。
    """
    elements_raw = _list(cd, "elements", path, required=False, default=[]) or []
    if not elements_raw:
        raise CardLoaderError(f"{path}.elements 不得为空（min_length=1）")
    element_templates: tuple[ElementTemplate, ...] = ()
    for i, ed in enumerate(elements_raw):
        et = _build_element(ed, f"{path}.elements[{i}]")
        count = _int(ed, "count", f"{path}.elements[{i}]", required=True)
        if count is None or count < 1:
            raise CardLoaderError(f"{path}.elements[{i}].count 须 ≥1")
        element_templates += (et,) * count  # count 展开（IMPL-地面 D.1#5 → 扁平元组）
    aura_raw = cd.get("aura")
    aura = None
    if aura_raw is not None:
        aura_d = _dict_of(cd, "aura", path)
        aura = Aura(
            kind=_enum(aura_d, "kind", AuraKind, f"{path}.aura", required=True),
            bonus_bp=_int(aura_d, "bonus_bp", f"{path}.aura", required=True),
            radius_cm=_int(aura_d, "radius_cm", f"{path}.aura", required=True))
    air_ceiling_raw = _int(cd, "air_ceiling", path, required=False, default=-1)
    air_ceiling = None  # -1＝不可及（DATA-01 §4.2——NONE→types 的 None）
    if air_ceiling_raw != -1:
        try:
            air_ceiling = AltTier(air_ceiling_raw)
        except ValueError:
            raise CardLoaderError(
                f"{path}.air_ceiling={air_ceiling_raw} 不在 AltTier 域（-1/0/1/2）") from None
    flags_raw = _int(cd, "flags", path, required=False, default=0)
    return UnitTemplate(
        template_id=_int(cd, "template_id", path, required=True),
        name=_str(cd, "name", path, required=True),
        category=_int(cd, "category", path, required=True),
        cost=_int(cd, "cost", path, required=True),
        element_templates=element_templates,
        optics_ground_cm=_int(cd, "optics_ground_cm", path, required=True),
        stealth_base=_int(cd, "stealth_base", path, required=True),
        speed_tier=_int(cd, "speed_tier", path, required=True),
        movement_class=_enum(cd, "movement_class", MovementClass, path, required=True),
        turn_rate_deg=_int(cd, "turn_rate_deg", path, required=False, default=1),
        terrain_speed_override_bp=_int(cd, "terrain_speed_override_bp", path,
                                       required=False, default=0),  # PB-52（0=回退类级）
        reverse_speed_override_bp=_int(cd, "reverse_speed_override_bp", path,
                                       required=False, default=0),  # PB-52（0=回退类级）
        road_bonus_override_cm=_int(cd, "road_bonus_override_cm", path,
                                    required=False, default=0),    # PB-52（0=回退类级常数）
        morale_sup_th=_int(cd, "morale_sup_th", path,
                           required=False, default=0),   # PB-55（0=回退 cfg.morale_sup_th）
        morale_pin_th=_int(cd, "morale_pin_th", path,
                           required=False, default=0),   # PB-55（0=回退 cfg.morale_pin_th）
        morale_rout_th=_int(cd, "morale_rout_th", path,
                            required=False, default=0),  # PB-55（0=回退 cfg.morale_rout_th）
        deploy_time_ticks=_int(cd, "deploy_time_ticks", path, required=False, default=0),
        pack_time_ticks=_int(cd, "pack_time_ticks", path, required=False, default=0),
        flags=UnitFlag(flags_raw),
        supply_radius_cm=_int(cd, "supply_radius_cm", path, required=False, default=8000),
        sonar_radius_cm=_int(cd, "sonar_radius_cm", path, required=False, default=0),
        sonar_rate=_int(cd, "sonar_rate", path, required=False, default=0),
        acoustic_signature=_int(cd, "acoustic_signature", path, required=False, default=1),
        mode_set=_int(cd, "mode_set", path, required=False, default=1),  # 1<<Mode.DIRECT
        optics_air_cm=_int(cd, "optics_air_cm", path, required=False, default=0),
        air_ceiling=air_ceiling,
        tow_tonnage=_int(cd, "tow_tonnage", path, required=False, default=0),
        own_weight_tons=_int(cd, "own_weight_tons", path, required=False, default=0),
        repair_power_hp_per_tick=_int(cd, "repair_power_hp_per_tick", path,
                                      required=False, default=0),
        close_combat_bonus_permille=_int(cd, "close_combat_bonus_permille", path,
                                         required=False, default=1000),
        aura=aura,
    )


def _check_paratroop_alignment(cd: dict, card_key: str, path: str) -> None:
    """空降对表（DATA-01 §8/C.3）：delivery≠NONE 须与 air_data.ParatroopCardSpec 一致。"""
    delivery_v = _int(cd, "delivery", path, required=True)
    delivery = VALUE_TOKEN["delivery"].get(delivery_v)
    if delivery is None:
        raise CardLoaderError(
            f"{path}.delivery={delivery_v} 不在 delivery int 表示域")
    if delivery == "NONE":
        return
    spec = next((s for s in PARATROOP_CARDS if s.card_key == card_key), None)
    if spec is None:
        raise CardLoaderError(
            f"{path} 空降卡 {card_key!r} 未在 air_data.PARATROOP_CARDS 登记（C.3 对表）")
    pool_v = _int(cd, "pool", path, required=True)
    pool = VALUE_TOKEN["pool"].get(pool_v)
    if pool is None:
        raise CardLoaderError(f"{path}.pool={pool_v} 不在 pool int 表示域")
    cost = _int(cd, "cost", path, required=True)
    if pool != "RESERVE" or spec.pool != "RESERVE":
        raise CardLoaderError(
            f"{path} 空降卡 {card_key!r} 必须占预备队池（D017——spec.pool={spec.pool!r}）")
    if _DELIVERY_AIRCRAFT[delivery] is not spec.delivery:
        raise CardLoaderError(
            f"{path} 空降卡 {card_key!r} 投送机型 {delivery} 与 "
            f"air_data 登记 {spec.delivery.name!r} 不一致（P-13）")
    if cost != spec.cost_points:
        raise CardLoaderError(
            f"{path} 空降卡 {card_key!r} cost={cost} 与 air_data "
            f"cost_points={spec.cost_points} 不一致（P-13）")


def load_library(path: str | Path) -> dict[str, CardRecord]:
    """卡库 JSON → {card_key: CardRecord}（方案 §E.3 签名钉死 dict 返回）。

    校验：版本门（fail-fast）／根键与类型／template_id 全库唯一（DATA-01 §3——
    回放校验前置条件）／空降对表（C.3）。未知键忽略（DATA-01 §2.3-1 演进兼容）。
    """
    with open(path, encoding="utf-8") as f:
        root = json.load(f)
    if not isinstance(root, dict):
        raise CardLoaderError("卡库 JSON 根必须为对象")
    version = root.get("schema_version")
    if not isinstance(version, str) or not schema_version_supported(version):
        raise CardLoaderError(
            f"schema_version {version!r} 不在支持表 {SUPPORTED_CARD_SCHEMA}"
            f"（major 不在表或 minor 超上界——DATA-01 §2.2）")
    cards_raw = _list(root, "cards", "library", required=True)
    records: dict[str, CardRecord] = {}
    seen_tids: dict[int, str] = {}
    for i, cd in enumerate(cards_raw):  # type: ignore[arg-type]
        path = f"library.cards[{i}]"
        card_key = _str(cd, "card_key", path, required=True)
        if card_key in records:
            raise CardLoaderError(f"card_key {card_key!r} 全库重复")
        tid = _int(cd, "template_id", path, required=True)
        if tid in seen_tids:
            raise CardLoaderError(
                f"template_id={tid} 全库重复（{seen_tids[tid]!r} 与 {card_key!r}）")
        seen_tids[tid] = card_key
        _check_paratroop_alignment(cd, card_key, path)
        provenance = tuple(p for p in (_list(cd, "_provenance", path,
                                             required=False, default=[]) or [])
                           if isinstance(p, dict))
        records[card_key] = CardRecord(
            card_key=card_key,
            unit_template=_build_unit(cd, path),
            faction=_token(cd, "faction", "faction", path),
            pool=_token(cd, "pool", "pool", path),
            per_card_limit=_int(cd, "per_card_limit", path,
                                required=False, default=None),
            quota_group=_token(cd, "quota_group", "quota_group", path),
            unlock_by=_str(cd, "unlock_by", path, required=False, default=""),
            delivery=_token(cd, "delivery", "delivery", path),
            provenance=provenance,
        )
    return records


def load_deck(path: str | Path) -> DeckData:
    """deck JSON → DeckData（版本门＋键类型校验；阈值全量校验在 validate_deck）。"""
    with open(path, encoding="utf-8") as f:
        root = json.load(f)
    if not isinstance(root, dict):
        raise CardLoaderError("deck JSON 根必须为对象")
    version = root.get("schema_version")
    if not isinstance(version, str) or not schema_version_supported(version):
        raise CardLoaderError(
            f"schema_version {version!r} 不在支持表 {SUPPORTED_CARD_SCHEMA}（DATA-01 §2.2）")
    faction_v = _int(root, "faction", "deck", required=True)
    faction = VALUE_TOKEN["faction"].get(faction_v)
    if faction is None:
        raise CardLoaderError(f"deck.faction={faction_v} 不在 faction int 表示域")
    entries_raw = _list(root, "cards", "deck", required=True) or []
    entries: list[tuple[str, int]] = []
    for i, e in enumerate(entries_raw):
        copies = _int(e, "copies", f"deck.cards[{i}]", required=True)
        if copies is None or copies < 1:
            raise CardLoaderError(f"deck.cards[{i}].copies 须 ≥1")
        entries.append((_str(e, "card_key", f"deck.cards[{i}]", required=True), copies))
    return DeckData(
        schema_version=version,
        deck_key=_str(root, "deck_key", "deck", required=True),
        faction=faction,
        cards=tuple(entries),
        points_main_cap=_int(root, "points_main_cap", "deck", required=False),
        points_reserve_cap=_int(root, "points_reserve_cap", "deck", required=False),
    )


def validate_deck(deck: DeckData, library: dict[str, CardRecord], *,
                  per_card_limit_by_category: dict[str, int],
                  category_quota: dict[str, dict[str, int]],
                  fire_support_subquota: dict[str, int],
                  points_main_cap: int,
                  points_reserve_cap: int,
                  library_schema_version: str | None = None) -> None:
    """deck 构筑校验（运行期复用 DATA-01 §8；与构建期 card_schema.validate_deck 同规则）。

    阈值全部显式注入——单一权威在 card_schema（迁移前，DATA-01 §12 D-1）/
    tables.BalanceConfig（归口后），本模块不落常量数值（无双轨）。
    违规抛 CardLoaderError（fail-fast，不静默截断）。
    """
    if library_schema_version is not None and deck.schema_version != library_schema_version:
        raise CardLoaderError(
            f"deck schema_version {deck.schema_version!r} 与卡库 "
            f"{library_schema_version!r} 不一致（三版本绑定——DATA-01 §3）")
    cat_pool: dict[tuple[str, str], int] = {}
    subquota: dict[str, int] = {}
    points: dict[str, int] = {"MAIN": 0, "RESERVE": 0}
    for card_key, copies in deck.cards:
        rec = library.get(card_key)
        if rec is None:
            raise CardLoaderError(f"deck 引用卡 {card_key!r} 不在卡库")
        if rec.faction != deck.faction:
            raise CardLoaderError(
                f"卡 {card_key!r} 阵营 {rec.faction} 与 deck {deck.faction} 不一致")
        category = _category_token(rec.unit_template.category)
        limit = (rec.per_card_limit if rec.per_card_limit is not None
                 else per_card_limit_by_category[category])
        if copies > limit:  # D032 同型限份
            raise CardLoaderError(
                f"{card_key} 份数 {copies} 超 D032 同型限份 {limit}")
        cat_pool[(category, rec.pool)] = (
            cat_pool.get((category, rec.pool), 0) + copies)
        if rec.quota_group != "NONE":  # R-13 子配额（两池总和）
            subquota[rec.quota_group] = subquota.get(rec.quota_group, 0) + copies
        points[rec.pool] += rec.unit_template.cost * copies
    for (cat, pool), n in cat_pool.items():  # D011 类别配额
        cap = category_quota[cat][pool]
        if n > cap:
            raise CardLoaderError(f"{cat}×{pool} 配额 {n} 超 D011 上限 {cap}")
    for group, n in subquota.items():
        cap = fire_support_subquota[group]
        if n > cap:
            raise CardLoaderError(
                f"火支子配额 {group} 共 {n} 份超上限 {cap}（两池总和）")
    main_cap = deck.points_main_cap if deck.points_main_cap is not None else points_main_cap
    reserve_cap = (deck.points_reserve_cap if deck.points_reserve_cap is not None
                   else points_reserve_cap)
    if points["MAIN"] > main_cap:
        raise CardLoaderError(f"主力池点数 {points['MAIN']} 超上限 {main_cap}（D038）")
    if points["RESERVE"] > reserve_cap:
        raise CardLoaderError(f"预备队池点数 {points['RESERVE']} 超上限 {reserve_cap}（D038）")
