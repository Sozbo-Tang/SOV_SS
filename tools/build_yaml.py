r"""YAML 配置层编译管线 CLI（GP-01 §1.2 / DATA-03 §1——取代 tools/build_cards.py，后者退役留档不删行）。

数据流：
  data/yaml/units/*.yaml ──(pyyaml safe_load，仅构建期)──> dict
    ├── 地面：UnitCardModel/ElementModel/WeaponRowModel（复用，39 字段零演进）
    ├── 航空：AirWeaponModel/AirCardModel/AirLibraryModel（schema 1.4 新增可选域）
    ├── 令牌→int 单点映射 TOKEN_VALUE（card_schema.py 既有——DATA-01 §2.4 口径）
    └── 键排序字节稳定 JSON：
        data/gen/cards_ground.v1.json   地面全库（67 卡＝表格行数全录＋表外空降两卡；
                                        #   与「合计40/阵营」差额 P-201/202/203 pending）
        data/gen/cards_air.v1.json      航空十卡＋武器档案＋空降对表记录（新产物）
        data/gen/decks/<deck_key>.json  卡组（card_loader.load_deck 兼容口径不变）

纪律：YAML 读入仅本文件（与 sovs/app/deck_editor.py 侧）发生，sovs/sim 永不 import yaml
（DATA-03 §1）；严格 int（YAML 手写 1.0 被 safe_load 解析为 float 再被 StrictInt 拒——
与 CSV 时代拒 "7.5" 同强度）；source_sha256＝拼接 YAML 源文本哈希（固定序＋文件名定界，
审计口径平移）；同输入两次构建产物逐字节相等（承 build_cards §E.2-4 先例）。

序列化/对账复用 tools/build_cards.py 纯函数（dump_stable_json/_mask/library_to_json_dict/
deck_to_json_dict/reconcile_provenance——int 表示单点无双轨）。CLI：
  python3 tools/build_yaml.py [--src data/yaml] [--out data/gen]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

if __package__ in (None, ""):  # 直跑自举：仓库根入 sys.path（sovs/tools 包可见）
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # 构建期依赖（pyyaml>=6——pyproject [project.dependencies] 构建期校验链）

from sovs.sim import card_schema as cs  # noqa: E402 （构建期校验层）
from tools import build_cards as bc  # noqa: E402 （序列化纯函数复用——单点无双轨）

SRC_DEFAULT = Path(__file__).resolve().parents[1] / "data" / "yaml"
OUT_DEFAULT = Path(__file__).resolve().parents[1] / "data" / "gen"
LIBRARY_JSON_NAME = "cards_ground.v1.json"     # 与 CSV 时代产物同名（加载面零改）
AIR_JSON_NAME = "cards_air.v1.json"            # GP-01 §1.2 新产物

#: 地面单位文件编译序（GDD-01 §1/§2 布局序：苏五表→德五表；全库 card 顺序由此定）
GROUND_UNIT_FILES = (
    "su_recon.yaml", "su_infantry.yaml", "su_armor.yaml",
    "su_fire_support.yaml", "su_aa_logistics.yaml",
    "ger_recon.yaml", "ger_infantry.yaml", "ger_armor.yaml",
    "ger_fire_support.yaml", "ger_aa_logistics.yaml",
)
AIR_FILES = ("air_weapons.yaml", "air_su.yaml", "air_ger.yaml")
PROVENANCE_FILE = "provenance.yaml"   # sidecar/ 下（DATA-01 §6.2 → YAML 化）
PENDING_FILE = "pending.yaml"         # sidecar/ 下（§6.3）


class BuildError(ValueError):
    """管线构建期错误（YAML 层/对账层；pydantic ValidationError 另行冒泡）。"""


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        raise BuildError(f"缺源文件 {path}")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise BuildError(f"{path.name} 根必须为对象")
    return doc


def _check_file_version(doc: dict, name: str) -> None:
    version = doc.get("schema_version")
    if version != cs.SCHEMA_VERSION:
        raise BuildError(
            f"{name} schema_version {version!r} 与构建器支持值 {cs.SCHEMA_VERSION!r} "
            f"不一致（三版本绑定——DATA-01 §3）")


def _source_sha256(paths: list[Path]) -> str:
    """拼接 YAML 源文本哈希（文件名定界防拼接歧义——build_cards §E 审计口径平移）。"""
    hasher = hashlib.sha256()
    for p in paths:
        hasher.update(p.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(p.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


# ── 地面卡库 ──

def load_ground_cards(src: Path) -> list[cs.UnitCardModel]:
    """units/ 地面十文件 → UnitCardModel 列表（GROUND_UNIT_FILES 序）。"""
    cards: list[cs.UnitCardModel] = []
    for name in GROUND_UNIT_FILES:
        doc = _load_yaml(src / "units" / name)
        _check_file_version(doc, name)
        raw = doc.get("cards")
        if not isinstance(raw, list):
            raise BuildError(f"{name} cards 必须为列表")
        # 单文件空表合法（编辑器增量/差额表 pending 后补场景）；全库 ≥1 卡由
        # CardLibraryModel.cards min_length=1 兜底
        for i, cd in enumerate(raw):
            cards.append(cs.UnitCardModel.model_validate(cd))  # 字段级报错冒泡
    return cards


def load_sidecar(src: Path) -> tuple[list[dict], list[cs.PendingItemModel]]:
    """sidecar/{provenance,pending}.yaml → (provenance 行, pending 模型)。"""
    prov_doc = _load_yaml(src / "sidecar" / PROVENANCE_FILE)
    _check_file_version(prov_doc, PROVENANCE_FILE)
    prov_rows = prov_doc.get("entries", [])
    pend_doc = _load_yaml(src / "sidecar" / PENDING_FILE)
    _check_file_version(pend_doc, PENDING_FILE)
    pending = [cs.PendingItemModel.model_validate(e)
               for e in pend_doc.get("entries", [])]
    return prov_rows, pending


def build_ground_library(src: Path) -> tuple[cs.CardLibraryModel, dict[str, list[dict]]]:
    """地面全库装配（对账复用 build_cards.reconcile_provenance——DATA-01 §6.3 子集）。"""
    unit_paths = [src / "units" / n for n in GROUND_UNIT_FILES]
    side_paths = sorted((src / "sidecar").glob("*.yaml"))
    deck_paths = sorted((src / "decks").glob("*.yaml"))
    sha = _source_sha256(unit_paths + side_paths + deck_paths)
    cards = load_ground_cards(src)
    prov_rows, pending = load_sidecar(src)
    lib = cs.CardLibraryModel.model_validate({
        "schema_version": cs.SCHEMA_VERSION, "source_sha256": sha,
        "cards": cards, "pending": pending})
    prov_by_card = bc.reconcile_provenance(prov_rows, lib)
    return lib, prov_by_card


# ── 航空库 ──

def _air_weapon_int_json(w: cs.AirWeaponModel) -> dict:
    raw = w.model_dump(mode="json")
    d = dict(raw)
    d["target_mask"] = bc._mask(w.target_mask, "target_mask")
    for f in ("damage_type", "trajectory", "combat_style"):
        d[f] = cs.TOKEN_VALUE[f][raw[f]]
    return d


def _air_card_int_json(a: cs.AirCardModel) -> dict:
    d = a.model_dump(mode="json")
    d["faction"] = cs.TOKEN_VALUE["faction"][d["faction"]]
    d["role"] = cs.TOKEN_VALUE["air_role"][d["role"]]
    d["alt_ceiling"] = cs.TOKEN_VALUE["air_ceiling"][d["alt_ceiling"]]
    d["weapons"] = [[w["ref"], w["ammo"]] for w in d["weapons"]]  # [weapon_key, 弹量]
    return d


def build_air_library(src: Path, ground: cs.CardLibraryModel) -> cs.AirLibraryModel:
    """航空三文件＋空降对表推导（delivery≠NONE 地面卡→AirParatroopSpecModel——不双写）。"""
    docs = {}
    for name in AIR_FILES:
        doc = _load_yaml(src / "units" / name)
        _check_file_version(doc, name)
        docs[name] = doc
    weapons = [cs.AirWeaponModel.model_validate(w)
               for w in docs["air_weapons.yaml"].get("weapons", [])]
    aircraft = [cs.AirCardModel.model_validate(a) for a in (
        docs["air_su.yaml"].get("cards", []) + docs["air_ger.yaml"].get("cards", []))]
    paratroops = [
        cs.AirParatroopSpecModel.model_validate({
            "card_key": c.card_key, "name": c.name, "cost_points": c.cost,
            "pool": "RESERVE", "delivery": c.delivery,
        }) for c in ground.cards if c.delivery != "NONE"]
    air_paths = [src / "units" / n for n in AIR_FILES]
    ground_paths = [src / "units" / n for n in GROUND_UNIT_FILES]
    return cs.AirLibraryModel.model_validate({
        "schema_version": cs.SCHEMA_VERSION,
        "source_sha256": _source_sha256(air_paths + ground_paths),
        "weapons": weapons, "aircraft": aircraft, "paratroops": paratroops})


def air_library_to_json_dict(lib: cs.AirLibraryModel) -> dict:
    """AirLibraryModel → JSON dict（枚举 int 表示；weapons/aircraft/paratroops 三段）。"""
    return {
        "schema_version": lib.schema_version,
        "source_sha256": lib.source_sha256,
        "weapons": [_air_weapon_int_json(w) for w in lib.weapons],
        "aircraft": [_air_card_int_json(a) for a in lib.aircraft],
        "paratroops": [
            {**p.model_dump(mode="json"),
             "pool": cs.TOKEN_VALUE["pool"][p.pool]} for p in lib.paratroops],
    }


# ── 卡组 ──

def build_deck(src: Path, path: Path, lib: cs.CardLibraryModel) -> cs.DeckModel:
    """decks/*.yaml → DeckModel（YAML 显式携带 schema_version/faction；全量校验）。"""
    doc = _load_yaml(path)
    _check_file_version(doc, path.name)
    deck = cs.DeckModel.model_validate(doc)
    cs.validate_deck(deck, lib)  # D032/D011/R-13/D038/阵营/版本绑定——构建期 fail-fast
    return deck


# ── 主流程 ──

def build_all(src: Path, out: Path) -> dict[str, Path]:
    """data/yaml → 三类 JSON 产物。非法数据一律冒泡 fail-fast，不落部分产物。"""
    src, out = Path(src), Path(out)
    lib, prov_by_card = build_ground_library(src)
    air = build_air_library(src, lib)

    written: dict[str, Path] = {}
    out.mkdir(parents=True, exist_ok=True)
    lib_path = out / LIBRARY_JSON_NAME
    lib_path.write_text(bc.dump_stable_json(bc.library_to_json_dict(lib, prov_by_card)),
                        encoding="utf-8")
    written["library"] = lib_path
    air_path = out / AIR_JSON_NAME
    air_path.write_text(bc.dump_stable_json(air_library_to_json_dict(air)),
                        encoding="utf-8")
    written["air"] = air_path
    for deck_yaml in sorted((src / "decks").glob("*.yaml")):
        deck = build_deck(src, deck_yaml, lib)
        deck_out = out / "decks"
        deck_out.mkdir(parents=True, exist_ok=True)
        deck_path = deck_out / f"{deck.deck_key}.json"
        deck_path.write_text(bc.dump_stable_json(bc.deck_to_json_dict(deck)),
                             encoding="utf-8")
        written[f"deck/{deck.deck_key}"] = deck_path
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="配置层管线：YAML → pydantic 校验 → JSON")
    parser.add_argument("--src", type=Path, default=SRC_DEFAULT,
                        help="data/yaml 配置目录（units/decks/sidecar 三段）")
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT,
                        help="JSON 产物目录（默认 data/gen）")
    args = parser.parse_args(argv)
    try:
        written = build_all(args.src, args.out)
    except ValueError as exc:  # BuildError/ValidationError 均为 ValueError 子类
        print(f"build_yaml: 构建失败——{exc}", file=sys.stderr)
        return 1
    for key, path in sorted(written.items()):
        print(f"build_yaml: 写入 {key} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
