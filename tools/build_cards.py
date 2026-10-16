r"""地面数据卡管线 CLI（out/card-schema-plan.md §E；消解 DATA-01 §12 偏离 D-2/D-3）。

⚠️ **已退役留档（2026-10-12）**：本 CLI 被 tools/build_yaml.py 取代（GP-01 §1.2 /
DATA-03 §1——配置面交换格式由 CSV 改 YAML，源＝data/yaml/，CSV 已归档
data/legacy_csv/）。保留不删行：①序列化纯函数（dump_stable_json/_mask/
library_to_json_dict/deck_to_json_dict/reconcile_provenance）被 build_yaml 复用
（int 表示单点无双轨）；②归档 CSV 的审计重建入口（python3 tools/build_cards.py
--data-dir data/legacy_csv --out-dir <tmp>）。同输入行为不变，schema 版本随
card_schema.py 单点（现 1.4）。

数据流（TECH-00 §8 :148）：CSV（utf-8-sig，stdlib csv——拍板 DATA-01 §1，DATA-03 废止）→ 类型转换
（数值列显式 int()，白名单正则 `-?\d+`——拦 "7.5"/"1_000"/公式注入）→ pydantic 校验
（sovs/sim/card_schema.py，DATA-01 冻结）→ JSON（键排序、枚举一律落 int 表示
——DATA-01 §2.4；同输入两次构建字节相等——方案 §E.2-4）。

五表结构（方案 §E.1）：
  data/ground_cards.csv      卡级，一卡一行（38 列＝39 字段减 elements——元素走外键表；
                             38＝35＋PB-52 三覆盖列＋PB-55 三士气阈值列 2026-10-04）
  data/ground_elements.csv   元素级（18 列＝17 字段＋card_key 外键；17＝16＋PB-53
                             self_smoke_charges 列 2026-10-04）
  data/ground_weapons.csv    武器级（29 列；element_key 外键——读取器强制其全库唯一，
                             严于 schema 的「卡内唯一」，防跨卡同名元素装配歧义）
  data/ground_provenance.csv 值级偏离 sidecar（DATA-01 §6.2；可缺失＝空表）
  data/ground_pending.csv    P-xx 待定登记 sidecar（§6.3；可缺失＝空表）
  data/decks/*.csv           卡组（三列 deck_key,card_key,copies；faction 由所含卡推导
                             并校验一致，schema_version 构建期注入——deck CSV 不携带）

结构化列编码（管线拍板：`;` 分隔、值内禁 `;`——DATA-01 §1.5）：
  aura               KIND;bonus_bp;radius_cm（空＝无 aura）
  armor_ke/armor_he  front;side;rear;top（空＝null）
  mounted_armament   key1;key2（空＝null；键须在本元素 weapons 内——schema V4 拦）
  restricted_profiles count:pen_bonus;count:pen_bonus（空＝[]）
  alt_profile        damage;blast_radius_cm（空＝null）
  self_defense       max_range_cm;accuracy_mult_bp（空＝null）

对账范围（DATA-01 §6.3 强制闭环的引用完整性子集）：provenance.card_key → 卡存在、
provenance.field_path → 卡/元素/武器真实字段、provenance.pending_id → pending 表存在。
分级强制闭环（〔待定〕字段必挂 pending）仍欠——字段分级元数据尚未挂
Field(json_schema_extra)（DATA-01 §6.1 演进项），本轮不实现、不伪造。

纪律：数值一律严格 int；无 float/random/math 超越函数；sha256 走 hashlib（审计哈希，
确定性，非随机源）。CLI 可直跑：python3 tools/build_cards.py [--data-dir data] [--out-dir data/gen]。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # 直跑自举：仓库根入 sys.path（sovs 包可见）
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sovs.sim import card_schema as cs  # noqa: E402 （构建期校验层——pydantic 仅此一 import）

DATA_DIR_DEFAULT = Path(__file__).resolve().parents[1] / "data"
LIBRARY_JSON_NAME = "cards_ground.v1.json"  # 方案 §E.1 生成产物名

_INT_RE = re.compile(r"-?\d+")  # 数值列白名单：拒 "7.5"/"1_000"/公式（含 "+7"——pydantic 域再兜底）
_FORMULA_PREFIXES = ("=", "+", "-", "@")  # DATA-01 §1.5 公式注入拦截（str 列）

_OMIT = object()  # 「空串＝默认值哨兵」——组装 dict 不放该键，走 pydantic 默认


class BuildError(ValueError):
    """管线构建期错误（CSV 层/外键层/对账层；pydantic ValidationError 另行冒泡）。"""


# ── 列规格（表头白名单；粗体行为必填列——缺列时行级报错）──

CARDS_COLUMNS: dict[str, str] = {
    "card_key": "str", "template_id": "int_req", "name": "str",
    "faction": "tok", "category": "tok", "cost": "int_req", "pool": "tok",
    "per_card_limit": "int_opt", "quota_group": "tok", "unlock_by": "str",
    "delivery": "tok", "optics_ground_cm": "int_req", "optics_air_cm": "int_def",
    "air_ceiling": "tok", "stealth_base": "int_req", "speed_tier": "int_req",
    "movement_class": "tok", "turn_rate_deg": "int_def",
    "terrain_speed_override_bp": "int_def",   # PB-52 单位级越野 bp（2026-10-04；0=回退类级）
    "reverse_speed_override_bp": "int_def",   # PB-52 单位级倒车 bp（同上）
    "road_bonus_override_cm": "int_def",      # PB-52 单位级道路下限 cm/tick（同上）
    "morale_sup_th": "int_def",   # PB-55 卡级受压阈值（2026-10-04；0=回退 cfg.morale_sup_th）
    "morale_pin_th": "int_def",   # PB-55 卡级钉住阈值（同上）
    "morale_rout_th": "int_def",  # PB-55 卡级溃逃阈值（同上；三列显式值须严格递增——schema 拦）
    "deploy_time_ticks": "int_def", "pack_time_ticks": "int_def",
    "flags": "tok_list", "mode_set": "tok_list", "supply_radius_cm": "int_def",
    "sonar_radius_cm": "int_def", "sonar_rate": "int_def",
    "acoustic_signature": "int_def", "tow_tonnage": "int_def",
    "own_weight_tons": "int_def", "repair_power_hp_per_tick": "int_def",
    "close_combat_bonus_permille": "int_def", "size_factor_bp": "int_def",
    "aura": "aura",
}
CARDS_REQUIRED = ("card_key", "template_id", "name", "faction", "category",
                  "cost", "pool", "optics_ground_cm", "stealth_base",
                  "speed_tier", "movement_class")
CARD_TOKEN_FIELDS = ("faction", "category", "pool", "quota_group", "delivery",
                     "air_ceiling", "movement_class")

ELEMENTS_COLUMNS: dict[str, str] = {
    "card_key": "str", "element_key": "str", "count": "int_req",
    "element_type": "tok", "unit_type": "tok", "hp_max": "int_req",
    "armor_ke": "armor", "armor_he": "armor", "fire_arc_deg": "int_def",
    "suppression_vuln_permille": "int_def", "squad_quality_bp": "int_def",
    "seats": "int_def", "mounted_armament": "key_list",
    "cargo_rounds_max": "int_def", "cargo_medical_max": "int_def",
    "cargo_weight_max": "int_def",
    "self_smoke_charges": "int_def",   # PB-53 自卫烟幕发数（2026-10-04；0=无能力）
}  # 武器不设列（走 ground_weapons.csv 外键表——表头带 weapons 列按未知列拒）
ELEMENTS_REQUIRED = ("card_key", "element_key", "count", "element_type",
                     "unit_type", "hp_max")
ELEMENT_TOKEN_FIELDS = ("element_type", "unit_type")

WEAPONS_COLUMNS: dict[str, str] = {
    "weapon_key": "str", "element_key": "str", "name": "str",
    "target_mask": "tok_list", "damage_type": "tok", "pen_min": "int_def",
    "pen_max": "int_def", "damage": "int_def", "blast_radius_cm": "int_def",
    "max_range_cm": "int_req", "min_range_cm": "int_def",
    "dispersion_cm": "int_def", "accuracy_base_bp": "int_def",
    "aim_time_ticks": "int_def", "reload_time_ticks": "int_def",
    "salvo": "int_def", "ammo_base": "int_def", "ammo_weight": "int_def",
    "projectile_speed_cm_tick": "int_def", "trajectory": "tok",
    "suppression_power": "int_def", "crit_mod_permille": "int_def",
    "vs_fort_mult_permille": "int_def", "needs_deployed": "bool",
    "combat_style": "tok", "reveal_time_ticks": "int_def",
    "restricted_profiles": "profiles", "alt_profile": "alt",
    "self_defense": "selfdef",
}
WEAPONS_REQUIRED = ("weapon_key", "element_key", "name", "damage_type",
                    "max_range_cm")
WEAPON_TOKEN_FIELDS = ("damage_type", "trajectory", "combat_style")

PROVENANCE_COLUMNS = ("card_key", "field_path", "grade", "source_ref", "pending_id")
PENDING_COLUMNS = ("pending_id", "scope", "field", "filled_value", "resolve_plan")
DECK_COLUMNS = ("deck_key", "card_key", "copies")


# ── 原始转换 helpers（全部给出「表/行/列」上下文）──

def _to_int(table: str, rowno: int, col: str, raw: str, *, required: bool):
    raw = raw.strip()
    if raw == "":
        if required:
            raise BuildError(f"{table} 第 {rowno} 行 {col} 为空（必填列不得留空）")
        return _OMIT  # 空串＝默认值哨兵
    if not _INT_RE.fullmatch(raw):
        raise BuildError(
            f"{table} 第 {rowno} 行 {col}={raw!r} 不是合法 int（拒小数/下划线/公式——DATA-01 §1）")
    return int(raw)


def _to_str(table: str, rowno: int, col: str, raw: str, *, required: bool):
    raw = raw.strip()
    if raw == "":
        if required:
            raise BuildError(f"{table} 第 {rowno} 行 {col} 为空（必填列不得留空）")
        return _OMIT if col != "unlock_by" else ""
    if raw[0] in _FORMULA_PREFIXES:
        raise BuildError(
            f"{table} 第 {rowno} 行 {col} 以 {raw[0]!r} 开头（公式注入拦截——DATA-01 §1.5）")
    if ";" in raw:
        raise BuildError(f"{table} 第 {rowno} 行 {col} 含分隔符 ';'（值内禁分号）")
    return raw


def _to_token(table: str, rowno: int, col: str, raw: str, *, required: bool):
    raw = raw.strip()
    domain = col if col != "aura" else "aura_kind"
    if raw == "":
        if required:
            raise BuildError(f"{table} 第 {rowno} 行 {col} 为空（必填列不得留空）")
        return _OMIT
    if raw not in cs.TOKEN_VALUE[domain]:
        raise BuildError(
            f"{table} 第 {rowno} 行 {col}={raw!r} 不在令牌集 "
            f"{sorted(cs.TOKEN_VALUE[domain])}")
    return raw


def _to_token_list(table: str, rowno: int, col: str, raw: str, *, required: bool):
    raw = raw.strip()
    if raw == "":
        if required:
            raise BuildError(f"{table} 第 {rowno} 行 {col} 为空（必填列不得留空）")
        return _OMIT
    domain = col
    out = []
    for tok in raw.split(";"):
        if tok == "":
            raise BuildError(f"{table} 第 {rowno} 行 {col} 含空令牌（{raw!r}）")
        if tok not in cs.TOKEN_VALUE[domain]:
            raise BuildError(
                f"{table} 第 {rowno} 行 {col} 令牌 {tok!r} 不在令牌集 "
                f"{sorted(cs.TOKEN_VALUE[domain])}")
        out.append(tok)
    return out


def _to_bool(table: str, rowno: int, col: str, raw: str, *, required: bool):
    raw = raw.strip()
    if raw == "":
        if required:
            raise BuildError(f"{table} 第 {rowno} 行 {col} 为空（必填列不得留空）")
        return _OMIT
    if raw not in ("true", "false"):
        raise BuildError(
            f"{table} 第 {rowno} 行 {col}={raw!r} 布尔列仅接受 true/false")
    return raw == "true"


def _split_struct(table: str, rowno: int, col: str, raw: str, n: int):
    """结构化列切段（空＝None；段数必须恰为 n，全段禁空禁公式前缀）。"""
    raw = raw.strip()
    if raw == "":
        return None
    parts = raw.split(";")
    if len(parts) != n:
        raise BuildError(f"{table} 第 {rowno} 行 {col}={raw!r} 须为 {n} 段（';' 分隔）")
    out = []
    for p in parts:
        p = p.strip()
        if p == "" or p[0] in _FORMULA_PREFIXES:
            raise BuildError(f"{table} 第 {rowno} 行 {col} 段 {p!r} 非法（空/公式前缀）")
        out.append(p)
    return out


def _struct_int(table: str, rowno: int, col: str, part: str) -> int:
    if not _INT_RE.fullmatch(part):
        raise BuildError(
            f"{table} 第 {rowno} 行 {col} 段 {part!r} 不是合法 int（DATA-01 §1）")
    return int(part)


def _to_armor(table: str, rowno: int, col: str, raw: str, *, required: bool):
    parts = _split_struct(table, rowno, col, raw, 4)
    if parts is None:
        return _OMIT if not required else None  # 空＝null（INFANTRY）；required 恒 False
    return {k: _struct_int(table, rowno, col, p)
            for k, p in zip(("front", "side", "rear", "top"), parts)}


def _to_key_list(table: str, rowno: int, col: str, raw: str, *, required: bool):
    """`;` 分隔的键列表（mounted_armament——空＝null；键须在 weapons 内由 schema V4 拦）。"""
    raw = raw.strip()
    if raw == "":
        return _OMIT
    keys = [k.strip() for k in raw.split(";")]
    for k in keys:
        if k == "" or k[0] in _FORMULA_PREFIXES:
            raise BuildError(f"{table} 第 {rowno} 行 {col} 键 {k!r} 非法（空/公式前缀）")
    return keys


def _to_aura(table: str, rowno: int, col: str, raw: str, *, required: bool):
    parts = _split_struct(table, rowno, col, raw, 3)
    if parts is None:
        return _OMIT  # 空＝无 aura
    kind = parts[0]
    if kind not in cs.TOKEN_VALUE["aura_kind"]:
        raise BuildError(
            f"{table} 第 {rowno} 行 {col} 段 {kind!r} 不在 aura_kind 令牌集")
    return {"kind": kind,
            "bonus_bp": _struct_int(table, rowno, col, parts[1]),
            "radius_cm": _struct_int(table, rowno, col, parts[2])}


def _to_profiles(table: str, rowno: int, col: str, raw: str, *, required: bool):
    raw = raw.strip()
    if raw == "":
        return _OMIT  # 空＝[]
    out = []
    for pair in raw.split(";"):
        cnt, _, bonus = pair.partition(":")
        cnt, bonus = cnt.strip(), bonus.strip()
        if ":" not in pair or not _INT_RE.fullmatch(cnt) or not _INT_RE.fullmatch(bonus):
            raise BuildError(
                f"{table} 第 {rowno} 行 {col} 档 {pair!r} 须为 count:pen_bonus 两 int")
        out.append({"count": int(cnt), "pen_bonus": int(bonus)})
    return out


def _to_alt(table: str, rowno: int, col: str, raw: str, *, required: bool):
    parts = _split_struct(table, rowno, col, raw, 2)
    if parts is None:
        return _OMIT  # 空＝null
    return {"damage": _struct_int(table, rowno, col, parts[0]),
            "blast_radius_cm": _struct_int(table, rowno, col, parts[1])}


def _to_selfdef(table: str, rowno: int, col: str, raw: str, *, required: bool):
    parts = _split_struct(table, rowno, col, raw, 2)
    if parts is None:
        return _OMIT  # 空＝null
    return {"max_range_cm": _struct_int(table, rowno, col, parts[0]),
            "accuracy_mult_bp": _struct_int(table, rowno, col, parts[1])}


_CONVERTERS = {
    "int_req": lambda t, r, c, v, req: _to_int(t, r, c, v, required=req),
    "int_def": lambda t, r, c, v, req: _to_int(t, r, c, v, required=req),
    "int_opt": lambda t, r, c, v, req: _to_int(t, r, c, v, required=req),
    "str": lambda t, r, c, v, req: _to_str(t, r, c, v, required=req),
    "tok": lambda t, r, c, v, req: _to_token(t, r, c, v, required=req),
    "tok_list": lambda t, r, c, v, req: _to_token_list(t, r, c, v, required=req),
    "bool": lambda t, r, c, v, req: _to_bool(t, r, c, v, required=req),
    "aura": lambda t, r, c, v, req: _to_aura(t, r, c, v, required=req),
    "armor": lambda t, r, c, v, req: _to_armor(t, r, c, v, required=req),
    "key_list": lambda t, r, c, v, req: _to_key_list(t, r, c, v, required=req),
    "profiles": lambda t, r, c, v, req: _to_profiles(t, r, c, v, required=req),
    "alt": lambda t, r, c, v, req: _to_alt(t, r, c, v, required=req),
    "selfdef": lambda t, r, c, v, req: _to_selfdef(t, r, c, v, required=req),
}


def _convert_row(table: str, rowno: int, row: dict[str, str],
                 columns: dict[str, str], required: tuple[str, ...]) -> dict:
    """一行原始 str → 类型化 dict（_OMIT 键剔除；必填列缺表头/空值报错）。"""
    out: dict = {}
    for col, kind in columns.items():
        if kind == "omit":
            continue
        if col not in row:
            if col in required:
                raise BuildError(f"{table} 第 {rowno} 行缺必填列 {col}（表头未含）")
            continue
        raw = row[col]
        if raw is None:  # DictReader restkey 之外的行短读
            raise BuildError(f"{table} 第 {rowno} 行 {col} 值缺失（列短读）")
        v = _CONVERTERS[kind](table, rowno, col, raw, col in required)
        if v is not _OMIT:
            out[col] = v
    return out


# ── CSV 读取（utf-8-sig；未知列拒）──

def read_csv_rows(path: Path, table: str, allowed: set[str]) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        unknown = [c for c in fieldnames if c not in allowed]
        if unknown:
            raise BuildError(f"{table} {path.name} 表头未知列 {unknown}（extra=forbid 口径）")
        rows = []
        for i, row in enumerate(reader):
            if None in row:  # 行内多余单元格（超出表头）
                raise BuildError(f"{table} 第 {i + 2} 行单元格数多于表头列")
            rows.append(row)
    return rows


# ── 组装（外键装配 → pydantic 校验）──

def assemble_library(cards_rows: list[dict[str, str]],
                     elements_rows: list[dict[str, str]],
                     weapons_rows: list[dict[str, str]],
                     pending_rows: list[dict[str, str]],
                     source_sha256: str) -> cs.CardLibraryModel:
    """三表原始行 → CardLibraryModel（悬挂外键/重复键在装配层报错）。"""
    table = "ground_pending"
    pending = []
    for i, row in enumerate(pending_rows):
        missing = [c for c in PENDING_COLUMNS if not row.get(c, "").strip()]
        if missing:
            raise BuildError(f"{table} 第 {i + 2} 行缺必填列 {missing}")
        pending.append(cs.PendingItemModel.model_validate({
            c: row[c].strip() for c in PENDING_COLUMNS}))

    # 武器行：转换＋按 element_key 分组（element_key 全库唯一由下方元素装配层强制）
    weapons_by_element: dict[str, list[dict]] = {}
    for i, row in enumerate(weapons_rows):
        wd = _convert_row("ground_weapons", i + 2, row, WEAPONS_COLUMNS, WEAPONS_REQUIRED)
        weapons_by_element.setdefault(wd["element_key"], []).append(wd)

    # 元素行：转换＋挂武器（悬挂 weapon element_key 在此暴露）
    claimed_elements: dict[str, str] = {}  # element_key -> card_key
    elements_by_card: dict[str, list[cs.ElementModel]] = {}
    for i, row in enumerate(elements_rows):
        ed = _convert_row("ground_elements", i + 2, row, ELEMENTS_COLUMNS, ELEMENTS_REQUIRED)
        card_key, ekey = ed.pop("card_key"), ed["element_key"]  # card_key=管线外键（非 schema 字段）
        if ekey in claimed_elements:
            raise BuildError(
                f"ground_elements element_key {ekey!r} 重复（读取器要求全库唯一——"
                f"weapons 表 element_key 外键无 card_key，跨卡同名即装配歧义）")
        claimed_elements[ekey] = card_key
        ed["weapons"] = weapons_by_element.pop(ekey, [])
        elements_by_card.setdefault(card_key, []).append(
            cs.ElementModel.model_validate(ed))

    dangling = sorted(weapons_by_element)  # 悬挂武器行（无元素认领）
    if dangling:
        raise BuildError(f"ground_weapons 悬挂 element_key {dangling}（无对应元素行）")

    # 卡行：转换＋挂元素 → UnitCardModel
    cards: list[cs.UnitCardModel] = []
    for i, row in enumerate(cards_rows):
        cd = _convert_row("ground_cards", i + 2, row, CARDS_COLUMNS, CARDS_REQUIRED)
        card_key = cd["card_key"]
        elems = elements_by_card.pop(card_key, None)
        if elems is None:
            raise BuildError(f"ground_cards 第 {i + 2} 行 {card_key!r} 无元素行（外键悬挂）")
        cd["elements"] = elems
        cards.append(cs.UnitCardModel.model_validate(cd))

    dangling = sorted(elements_by_card)  # 悬挂元素行（无卡认领）
    if dangling:
        raise BuildError(f"ground_elements 悬挂 card_key {dangling}（无对应卡行）")

    lib = cs.CardLibraryModel.model_validate({
        "schema_version": cs.SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "cards": cards,
        "pending": pending,
    })
    return lib  # claimed_elements 仅装配期使用（跨卡同名即歧义，已在上文报错）


def reconcile_provenance(provenance_rows: list[dict[str, str]],
                         lib: cs.CardLibraryModel) -> dict[str, list[dict]]:
    """对账（DATA-01 §6.2/§6.3 引用完整性子集）→ 内存旁表 {card_key: [条目]}。

    强制闭环仅覆盖引用侧；〔待定〕分级强制挂 pending 的闭环未实现（字段分级
    元数据未挂 json_schema_extra——见模块 docstring），不伪造。
    """
    pending_ids = {p.pending_id for p in lib.pending}
    card_keys = {c.card_key for c in lib.cards}
    card_field_names = set(cs.UnitCardModel.model_fields)
    field_paths: set[str] = set(card_field_names)
    for c in lib.cards:
        for e in c.elements:
            field_paths.add(f"elements[{e.element_key}]")
            field_paths.update(
                f"elements[{e.element_key}].{w.weapon_key}" for w in e.weapons)
    by_card: dict[str, list[dict]] = {}
    for i, row in enumerate(provenance_rows):
        entry = {c: row.get(c, "").strip() for c in PROVENANCE_COLUMNS}
        missing = [c for c in ("card_key", "field_path", "grade") if not entry[c]]
        if missing:
            raise BuildError(f"ground_provenance 第 {i + 2} 行缺必填列 {missing}")
        if entry["card_key"] not in card_keys:
            raise BuildError(
                f"ground_provenance 第 {i + 2} 行 card_key {entry['card_key']!r} 不在卡库")
        if entry["field_path"] not in field_paths:
            raise BuildError(
                f"ground_provenance 第 {i + 2} 行 field_path {entry['field_path']!r} "
                f"不是真实字段路径")
        if entry["pending_id"] and entry["pending_id"] not in pending_ids:
            raise BuildError(
                f"ground_provenance 第 {i + 2} 行 pending_id {entry['pending_id']!r} "
                f"未在 ground_pending 登记")
        by_card.setdefault(entry["card_key"], []).append(entry)
    return by_card


# ── 序列化（令牌→int——DATA-01 §2.4「JSON 一律落 int」单点转换）──

def _mask(tokens: list[str], domain: str) -> int:
    """令牌列表 → 位或 int（DATA-01 §4.2）。

    flags/target_mask：TOKEN_VALUE 值即位（UnitFlag/TargetDomain 均为 IntFlag 位值）；
    mode_set：TOKEN_VALUE 值＝Mode 枚举序号，位表示须 1<<序号（types.py:242
    默认 1 << Mode.DIRECT 同一口径）。
    """
    if domain == "mode_set":
        value = 0
        for tok in tokens:
            value |= 1 << cs.TOKEN_VALUE[domain][tok]
        return value
    value = 0
    for tok in tokens:
        value |= cs.TOKEN_VALUE[domain][tok]
    return value


def _weapon_to_int_json(w: dict) -> dict:
    d = dict(w)
    d["target_mask"] = _mask(w["target_mask"], "target_mask")
    for f in WEAPON_TOKEN_FIELDS:
        d[f] = cs.TOKEN_VALUE[f][w[f]]
    return d


def _element_to_int_json(e: dict) -> dict:
    d = dict(e)
    for f in ELEMENT_TOKEN_FIELDS:
        d[f] = cs.TOKEN_VALUE[f][d[f]]
    d["weapons"] = [_weapon_to_int_json(w) for w in e["weapons"]]
    return d


def _card_to_int_json(c: dict, provenance: list[dict] | None) -> dict:
    d = dict(c)
    for f in CARD_TOKEN_FIELDS:
        d[f] = cs.TOKEN_VALUE[f][d[f]]
    d["flags"] = _mask(d["flags"], "flags") if d["flags"] else 0
    d["mode_set"] = _mask(d["mode_set"], "mode_set") if d["mode_set"] else 0
    if d.get("aura") is not None:
        d["aura"] = {**d["aura"],
                     "kind": cs.TOKEN_VALUE["aura_kind"][d["aura"]["kind"]]}
    d["elements"] = [_element_to_int_json(e) for e in c["elements"]]
    d["_provenance"] = provenance or []  # 旁键恒注入（DATA-01 §6.2——loader 仅透传不映射）
    return d


def library_to_json_dict(lib: cs.CardLibraryModel,
                         provenance_by_card: dict[str, list[dict]]) -> dict:
    """CardLibraryModel → JSON dict（枚举 int 表示＋_provenance 旁键；键序由 dumps 排序）。"""
    return {
        "schema_version": lib.schema_version,
        "source_sha256": lib.source_sha256,
        "cards": [_card_to_int_json(c.model_dump(mode="json"),
                                    provenance_by_card.get(c.card_key))
                  for c in lib.cards],
        "pending": [p.model_dump(mode="json") for p in lib.pending],
    }


def deck_to_json_dict(deck: cs.DeckModel) -> dict:
    d = deck.model_dump(mode="json")
    d["faction"] = cs.TOKEN_VALUE["faction"][d["faction"]]
    return d


def dump_stable_json(obj) -> str:
    """稳定序列化（方案 §E.2-4：键排序＋ensure_ascii=False＋indent=2；同输入字节相等）。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


# ── deck 构建（faction 推导＋schema_version 注入＋全量校验）──

def build_deck_model(deck_key: str, entries: list[tuple[str, int]],
                     lib: cs.CardLibraryModel) -> cs.DeckModel:
    """三列 deck 行 → DeckModel（faction 由所含卡推导；cs.validate_deck 全量校验）。"""
    by_key = {c.card_key: c for c in lib.cards}
    factions = {by_key[k].faction for k, _ in entries if k in by_key}
    unknown = [k for k, _ in entries if k not in by_key]
    if unknown:
        raise BuildError(f"deck {deck_key!r} 引用卡 {unknown} 不在卡库")
    if len(factions) != 1:
        raise BuildError(
            f"deck {deck_key!r} 所含卡阵营不一致 {sorted(factions)}（三列拍板下 faction 须可推导）")
    deck = cs.DeckModel.model_validate({
        "schema_version": cs.SCHEMA_VERSION,  # 构建期注入（B.1——deck CSV 不携带）
        "deck_key": deck_key,
        "faction": factions.pop(),
        "cards": [{"card_key": k, "copies": n} for k, n in entries],
    })
    cs.validate_deck(deck, lib)  # D032/D011/R-13/D038/阵营/版本绑定——构建期 fail-fast
    return deck


# ── 主流程 ──

def _read_deck_csv(path: Path) -> tuple[str, list[tuple[str, int]]]:
    rows = read_csv_rows(path, "decks", set(DECK_COLUMNS))
    if not rows:
        raise BuildError(f"decks/{path.stem}.csv 无数据行（faction 无从推导——DATA-01 §4.6）")
    entries: list[tuple[str, int]] = []
    deck_keys: set[str] = set()
    for i, row in enumerate(rows):
        missing = [c for c in DECK_COLUMNS if not row.get(c, "").strip()]
        if missing:
            raise BuildError(f"decks 第 {i + 2} 行缺必填列 {missing}")
        deck_keys.add(row["deck_key"].strip())
        copies = _to_int("decks", i + 2, "copies", row["copies"], required=True)
        entries.append((row["card_key"].strip(), copies))
    if len(deck_keys) != 1:
        raise BuildError(
            f"decks/{path.stem}.csv 混装多个 deck_key {sorted(deck_keys)}（一文件一卡组）")
    return deck_keys.pop(), entries


def build_all(data_dir: Path, out_dir: Path) -> dict[str, Path]:
    """五表＋decks/ → 卡库 JSON＋deck JSON。返回写入路径（键：library/deck/<deck_key>）。

    非法数据（CSV 层/外键层/对账层 BuildError、pydantic ValidationError、
    deck 校验 ValueError）一律冒泡 fail-fast，不落部分产物。
    """
    data_dir = Path(data_dir)
    cards_path = data_dir / "ground_cards.csv"
    elements_path = data_dir / "ground_elements.csv"
    weapons_path = data_dir / "ground_weapons.csv"
    provenance_path = data_dir / "ground_provenance.csv"
    pending_path = data_dir / "ground_pending.csv"
    decks_dir = data_dir / "decks"
    for p, name in ((cards_path, "ground_cards.csv"), (elements_path, "ground_elements.csv"),
                    (weapons_path, "ground_weapons.csv")):
        if not p.is_file():
            raise BuildError(f"缺源表 {name}（{p}）")

    # source_sha256：全部源文件内容拼接哈希（固定序——审计可复算；含文件名定界防拼接歧义）
    sources = [cards_path, elements_path, weapons_path]
    for p in (provenance_path, pending_path):
        if p.is_file():
            sources.append(p)
    if decks_dir.is_dir():
        sources.extend(sorted(decks_dir.glob("*.csv")))
    hasher = hashlib.sha256()
    for p in sources:
        hasher.update(p.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(p.read_bytes())
        hasher.update(b"\0")

    cards_rows = read_csv_rows(cards_path, "ground_cards", set(CARDS_COLUMNS))
    elements_rows = read_csv_rows(elements_path, "ground_elements", set(ELEMENTS_COLUMNS))
    weapons_rows = read_csv_rows(weapons_path, "ground_weapons", set(WEAPONS_COLUMNS))
    provenance_rows = (read_csv_rows(provenance_path, "ground_provenance", set(PROVENANCE_COLUMNS))
                       if provenance_path.is_file() else [])
    pending_rows = (read_csv_rows(pending_path, "ground_pending", set(PENDING_COLUMNS))
                    if pending_path.is_file() else [])

    lib = assemble_library(cards_rows, elements_rows, weapons_rows,
                           pending_rows, hasher.hexdigest())
    prov_by_card = reconcile_provenance(provenance_rows, lib)

    written: dict[str, Path] = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    lib_json = dump_stable_json(library_to_json_dict(lib, prov_by_card))
    lib_path = out_dir / LIBRARY_JSON_NAME
    lib_path.write_text(lib_json, encoding="utf-8", newline="\n")
    written["library"] = lib_path

    if decks_dir.is_dir():
        for deck_csv in sorted(decks_dir.glob("*.csv")):
            deck_key, entries = _read_deck_csv(deck_csv)
            deck = build_deck_model(deck_key, entries, lib)
            deck_out = out_dir / "decks"
            deck_out.mkdir(parents=True, exist_ok=True)
            deck_path = deck_out / f"{deck_key}.json"
            deck_path.write_text(dump_stable_json(deck_to_json_dict(deck)),
                                 encoding="utf-8", newline="\n")
            written[f"deck/{deck_key}"] = deck_path
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="地面数据卡管线：CSV → pydantic 校验 → JSON")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR_DEFAULT,
                        help="五表＋decks/ 所在目录（默认仓库 data/）")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="JSON 产物目录（默认 <data-dir>/gen）")
    args = parser.parse_args(argv)
    out_dir = args.out_dir or (args.data_dir / "gen")
    try:
        written = build_all(args.data_dir, out_dir)
    except ValueError as exc:  # BuildError/ValidationError 均为 ValueError 子类
        print(f"build_cards: 构建失败——{exc}", file=sys.stderr)
        return 1
    for key, path in sorted(written.items()):
        print(f"build_cards: 写入 {key} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
