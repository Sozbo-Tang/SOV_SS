"""卡组编辑器后端（GP-01 §7）：YAML 读写/校验/就地编译——会话胶水层。

结论先行：编辑器与构建期/运行期**同一权威无双轨**——校验复用
sovs/sim/card_schema.validate_deck（D032 同型限份/faction 一致/D011 类别×池
配额/R-13 火支子配额/D038 点数上限，构建期＝运行期同规则）；序列化复用
tools/build_cards 纯函数（dump_stable_json/deck_to_json_dict——int 表示单点）；
卡池目录自 data/yaml 编译面（build_ground_library 的 CardLibraryModel——
M1 表格行数全录 67 卡）。

存取流（GP-01 §7 拍板）：保存＝写 data/yaml/decks/<deck_key>.yaml → 就地编译
data/gen/decks/<deck_key>.json → config 页卡组清单即时可选（session.deck_list
扫 data/gen/decks）；克隆＝读入改 deck_key 另存；删除＝删 YAML＋JSON（内置
su_min/ger_min 受删保护——数据源非编辑器产出面）；卡组文件本身即可分享
（本地文件互换——断箭 Decks 目录同款定位，Deck Code 后置）。

航空卡不入 deck（独立 750 分空点数池，D038 方案A）——catalog 只取地面库，
航空限份入册列为 deck 2.0 后置项（登记 GP-01 §7/§9.11）。

分层纪律：本模块属 sovs/app 会话胶水层（可 import sovs.sim 与 tools 构建面
——tests/test_arch_constraints.py ② 守卫只涉 sovs/ui）；pyyaml 为构建期
依赖（pyproject [project.dependencies]），sovs/sim 运行时仍 stdlib-only。
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml                                     # 构建期依赖（DATA-03 §6 口径）

from sovs.sim import card_schema as cs          # pydantic 校验层（构建期白名单面）
from tools import build_cards as bc             # 序列化纯函数复用（单点无双轨）
from tools import build_yaml as by              # 卡池目录/DeckModel 构建面复用

_ROOT = Path(__file__).resolve().parents[2]
YAML_DIR_DEFAULT = _ROOT / "data" / "yaml" / "decks"
GEN_DIR_DEFAULT = _ROOT / "data" / "gen" / "decks"
UNIT_SRC_DEFAULT = _ROOT / "data" / "yaml"

# 内置卡组（CSV 迁移面——DATA-03 §3）：编辑器只删自制面，防误删数据源。
PROTECTED_DECKS = frozenset({"su_min", "ger_min"})

# deck_key 文件名安全域（小写字母/数字/下划线——克隆/新建自动生成域同约束）。
_DECK_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# 类别页签序（GDD-01 §1/§2 五类——编辑器左栏页签与卡池过滤共用）。
CATEGORY_TABS: tuple[str, ...] = ("RECON", "INFANTRY", "ARMOR",
                                  "FIRE_SUPPORT", "AA_LOGISTICS")
CATEGORY_CN: dict[str, str] = {"RECON": "侦察", "INFANTRY": "步兵",
                               "ARMOR": "装甲", "FIRE_SUPPORT": "火力支援",
                               "AA_LOGISTICS": "防空后勤"}


class DeckEditor:
    """编辑器数据面（窗口层经鸭子面调用；fsm 只持纯数据态——见 shell_fsm）。"""

    def __init__(self, *, yaml_dir: Path = YAML_DIR_DEFAULT,
                 gen_dir: Path = GEN_DIR_DEFAULT,
                 unit_src: Path = UNIT_SRC_DEFAULT):
        self.yaml_dir = Path(yaml_dir)
        self.gen_dir = Path(gen_dir)
        lib, _prov = by.build_ground_library(Path(unit_src))   # 卡池目录（全库）
        self._lib = lib
        self._by_key = {c.card_key: c for c in lib.cards}

    # ── 路径面 ──

    def yaml_path(self, deck_key: str) -> Path:
        return self.yaml_dir / ("%s.yaml" % deck_key)

    def json_path(self, deck_key: str) -> Path:
        return self.gen_dir / ("%s.json" % deck_key)

    # ── 目录/卡池 ──

    def list_decks(self) -> list[str]:
        """卡组清单（data/yaml/decks 源面——config 页下拉/编辑器返回页共用）。"""
        if not self.yaml_dir.is_dir():
            return []
        return sorted(p.stem for p in self.yaml_dir.glob("*.yaml"))

    def catalog(self) -> list[dict]:
        """卡池目录（全库卡面：名/价/限份/配额组/类别/池/阵营——中栏数据源）。"""
        out = []
        for c in self._lib.cards:
            limit = (c.per_card_limit if c.per_card_limit is not None
                     else cs.PER_CARD_LIMIT_BY_CATEGORY[c.category])
            out.append({"card_key": c.card_key, "template_id": c.template_id,
                        "name": c.name, "cost": c.cost, "faction": c.faction,
                        "category": c.category, "pool": c.pool,
                        "per_card_limit": limit,
                        "quota_group": c.quota_group})
        return out

    # ── 读 ──

    def load_deck(self, deck_key: str) -> dict:
        """读卡组 YAML → {deck_key, faction, cards:[(key,copies)...]}（键缺省
        fail-fast——编辑器读面与构建面同一文件）。"""
        path = self.yaml_path(deck_key)
        if not path.is_file():
            raise FileNotFoundError("卡组源不存在：%s" % path)
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("卡组 YAML 根必须为对象：%s" % path.name)
        return {"deck_key": doc.get("deck_key", deck_key),
                "faction": str(doc.get("faction", "")),
                "cards": [(e["card_key"], int(e["copies"]))
                          for e in doc.get("cards", ())],
                "points_main_cap": int(doc.get(
                    "points_main_cap", cs.POINTS_MAIN_CAP)),
                "points_reserve_cap": int(doc.get(
                    "points_reserve_cap", cs.POINTS_RESERVE_CAP))}

    # ── 校验/汇总（与构建期/运行期同一权威——card_schema.validate_deck）──

    def validate(self, faction: str, entries) -> list[str]:
        """构筑校验 → 违规文案列表（空=可保存）；pydantic/ValueError 统一转
        内联红字（编辑器「违规条目内联红字＋保存禁用」的数据面）。"""
        try:
            self._build_model("draft", faction, entries)
        except ValueError as exc:                  # pydantic ValidationError 同基
            return [str(exc)]
        return []

    def summary(self, entries, faction: str) -> dict:
        """实时汇总（右栏数据源）：两池点数/类别×池份数/火支子配额份数。"""
        cat_pool: dict[tuple[str, str], int] = {}
        subquota: dict[str, int] = {}
        points = {"MAIN": 0, "RESERVE": 0}
        for card_key, copies in entries:
            card = self._by_key.get(card_key)
            if card is None:
                continue
            cat_pool[(card.category, card.pool)] = (
                cat_pool.get((card.category, card.pool), 0) + int(copies))
            if card.quota_group != "NONE":
                subquota[card.quota_group] = (subquota.get(card.quota_group, 0)
                                              + int(copies))
            points[card.pool] += card.cost * int(copies)
        return {"points_main": points["MAIN"], "cap_main": cs.POINTS_MAIN_CAP,
                "points_reserve": points["RESERVE"],
                "cap_reserve": cs.POINTS_RESERVE_CAP,
                "cat_pool": {"%s×%s" % kv: n for kv, n in sorted(cat_pool.items())},
                "subquota": dict(sorted(subquota.items()))}

    # ── 写 ──

    def save(self, deck_key: str, faction: str, entries) -> None:
        """保存：校验（同权威）→ 写 YAML → 就地编译 JSON（config 页即时可选）。
        非法数据冒泡 ValueError 且**不落任何产物**（fail-fast，不写半截）。"""
        model = self._build_model(deck_key, faction, entries)   # 校验门（抛=拒存）
        self.yaml_dir.mkdir(parents=True, exist_ok=True)
        self.gen_dir.mkdir(parents=True, exist_ok=True)
        self.yaml_path(deck_key).write_text(
            yaml.safe_dump({"schema_version": model.schema_version,
                            "deck_key": model.deck_key,
                            "faction": model.faction,
                            "cards": [{"card_key": e.card_key,
                                       "copies": e.copies}
                                      for e in model.cards]},
                           allow_unicode=True, sort_keys=False),
            encoding="utf-8", newline="\n")
        self.json_path(deck_key).write_text(
            bc.dump_stable_json(bc.deck_to_json_dict(model)), encoding="utf-8",
            newline="\n")

    def clone(self, src_key: str, new_key: str) -> None:
        """克隆＝读入改 deck_key 另存（断箭 duplicate 对齐）。"""
        deck = self.load_deck(src_key)
        self.save(new_key, deck["faction"], deck["cards"])

    def delete(self, deck_key: str) -> None:
        """删除 YAML＋JSON（内置两卡组受删保护——见 PROTECTED_DECKS）。"""
        if deck_key in PROTECTED_DECKS:
            raise ValueError("内置卡组 %s 受删保护（数据源非编辑器产出面）"
                             % deck_key)
        removed = False
        for path in (self.yaml_path(deck_key), self.json_path(deck_key)):
            if path.exists():
                path.unlink()
                removed = True
        if not removed:
            raise FileNotFoundError("卡组不存在：%s" % deck_key)

    def new_key(self) -> str:
        """自动生成新卡组键（custom_1..N——改名可覆盖，键域见 _DECK_KEY_RE）。"""
        n = 1
        while self.yaml_path("custom_%d" % n).exists():
            n += 1
        return "custom_%d" % n

    # ── 内部 ──

    def _build_model(self, deck_key: str, faction: str, entries):
        """entries → DeckModel（pydantic 模型校验＋validate_deck 构筑校验）。"""
        if not _DECK_KEY_RE.match(deck_key or ""):
            raise ValueError("deck_key %r 非法（小写字母开头+小写字母/数字/"
                             "下划线）" % deck_key)
        cards = [cs.DeckEntryModel(card_key=k, copies=int(n)) for k, n in entries]
        deck = cs.DeckModel(schema_version=cs.SCHEMA_VERSION,
                            deck_key=deck_key, faction=faction, cards=cards)
        cs.validate_deck(deck, self._lib)
        return deck
