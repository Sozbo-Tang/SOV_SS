"""管线端到端测试（tools/build_cards.py × sovs/sim/card_loader.py——方案 §H 子集）。

任务三类法定用例（构建期报错）：
① 超 D032 限份的卡组（装甲卡 3 份 > 默认 2）；
② 缺必填字段（ground_cards.csv optics_ground_cm 留空）；
③ 类型错误含 float（CSV "4.5"/"1.5" 文本——读取器 int() 白名单拒；
   JSON 侧 float/bool 注入——loader type(v) is int 白名单拒）。

合法端到端：CSV → pydantic → JSON（键排序/枚举 int 表示/字节稳定/_provenance 旁键）
→ card_loader.load_library → 冻结 dataclass（UnitTemplate/ElementTemplate/
WeaponTemplate/Armor/Aura 子模型逐字段对齐——DATA-01 §9 映射表）。
另覆盖：运行期 validate_deck（阈值注入——D-1 无双轨）、版本门两分支、
空降对表（C.3）、双轨锁死互检（SUPPORTED_CARD_SCHEMA/VALUE_TOKEN/版本判定）。

引用：out/card-schema-plan.md §E/§H；docs/DATA-01-地面数据卡schema冻结-v1.md。
"""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from sovs.sim import card_loader as cl
from sovs.sim import card_schema as cs
from sovs.sim.types import (AltProfile, AltTier, Armor, ElementTemplate,
                            MovementClass, SelfDefenseProfile, UnitFlag,
                            UnitTemplate, WeaponTemplate)
from tools import build_cards as bc

CARDS_COLS = list(bc.CARDS_COLUMNS)
ELEMENTS_COLS = list(bc.ELEMENTS_COLUMNS)
WEAPONS_COLS = list(bc.WEAPONS_COLUMNS)


def _rows_to_csv(columns: list[str], rows: list[dict]) -> str:
    """dict 行 → CSV 文本（`\n` 行尾；空值列＝空串＝默认值哨兵——方案 §E.2-2）。"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n",
                            extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buf.getvalue()


def _card_row(**over) -> dict:
    base = {c: "" for c in CARDS_COLS}
    base.update(dict(
        card_key="SU_RIFLE", template_id="101", name="步枪排",
        faction="SOVIET", category="INFANTRY", cost="45", pool="MAIN",
        optics_ground_cm="1400", stealth_base="1", speed_tier="1",
        movement_class="FOOT",
    ))
    base.update(over)
    return base


def _element_row(**over) -> dict:
    base = {c: "" for c in ELEMENTS_COLS}
    base.update(dict(
        card_key="SU_RIFLE", element_key="E_RIFLE", count="3",
        element_type="SQUAD", unit_type="INFANTRY", hp_max="8",
    ))
    base.update(over)
    return base


def _weapon_row(**over) -> dict:
    base = {c: "" for c in WEAPONS_COLS}
    base.update(dict(
        weapon_key="W_SVT", element_key="E_RIFLE", name="SVT-40步枪",
        target_mask="GROUND", damage_type="KE", pen_min="2", pen_max="4",
        damage="3", max_range_cm="5000", salvo="2", ammo_base="60",
        trajectory="DIRECT", suppression_power="3", needs_deployed="false",
        combat_style="NORMAL", reveal_time_ticks="0",
    ))
    base.update(over)
    return base


def card_rows() -> list[dict]:
    return [
        _card_row(
            flags="CAN_SPRINT;CAN_GARRISON",
            delivery="NONE",
        ),
        _card_row(  # 装甲：MECH 元素＋主炮（mounted/受限档/HE 档/自卫档全覆盖）
            card_key="SU_T3485", template_id="120", name="T-34/85坦克排",
            category="ARMOR", cost="100", optics_ground_cm="2200",
            optics_air_cm="6000", air_ceiling="MID", stealth_base="3",
            speed_tier="4", movement_class="TRACK", own_weight_tons="320",
        ),
        _card_row(  # 空降：delivery=LI2＋预备队池（C.3 对表样例）
            card_key="SU_PARATROOP", template_id="102", name="空降近卫步枪排",
            cost="60", pool="RESERVE", delivery="LI2", optics_ground_cm="1600",
            stealth_base="2", speed_tier="1", movement_class="FOOT",
        ),
        _card_row(  # 卡车：三模式＋吨位 0.1t 刻度（DATA-01 §7 数锚 ZiS-5=15）
            card_key="SU_TRUCK", template_id="103", name="卡车队（ZiS-5）",
            category="AA_LOGISTICS", cost="40", optics_ground_cm="1800",
            stealth_base="4", speed_tier="3", movement_class="WHEEL",
            mode_set="TOW;CARGO;TRANSPORT", tow_tonnage="15",
            own_weight_tons="30",
        ),
    ]


def element_rows() -> list[dict]:
    return [
        _element_row(),
        _element_row(
            card_key="SU_T3485", element_key="E_T34", count="3",
            element_type="VEHICLE", unit_type="MECH", hp_max="16",
            armor_ke="12;9;7;4", armor_he="8;6;5;3", fire_arc_deg="360",
            mounted_armament="W_D85",
        ),
        _element_row(
            card_key="SU_PARATROOP", element_key="E_PARA", count="2",
            element_type="SQUAD", unit_type="INFANTRY", hp_max="9",
        ),
        _element_row(
            card_key="SU_TRUCK", element_key="E_TRUCK", count="3",
            element_type="VEHICLE", unit_type="MECH", hp_max="12",
            armor_ke="0;0;0;0", armor_he="0;0;0;0", seats="3",
            cargo_rounds_max="600", cargo_medical_max="120",
            cargo_weight_max="500",
        ),
    ]


def weapon_rows() -> list[dict]:
    return [
        _weapon_row(),
        _weapon_row(  # D-85T：受限档/HE 档/自卫档三子模型
            weapon_key="W_D85", element_key="E_T34", name="D-85T坦克炮",
            pen_min="8", pen_max="12", damage="10", max_range_cm="12000",
            dispersion_cm="150", accuracy_base_bp="9500", aim_time_ticks="8",
            reload_time_ticks="50", salvo="1", ammo_base="28",
            projectile_speed_cm_tick="1600", suppression_power="8",
            crit_mod_permille="1100", vs_fort_mult_permille="1000",
            reveal_time_ticks="60", restricted_profiles="2:4",
            alt_profile="6;1500", self_defense="2000;5000",
        ),
        _weapon_row(  # 空降冲锋枪
            weapon_key="W_PPS", element_key="E_PARA", name="PPS-43冲锋枪",
            pen_min="1", pen_max="2", damage="2", max_range_cm="3000",
            salvo="3", ammo_base="90", suppression_power="2",
        ),
    ]


PROVENANCE_CSV = (
    "card_key,field_path,grade,source_ref,pending_id\n"
    "SU_T3485,tow_tonnage,数锚,GDD-03 §1.7,\n"
    "SU_T3485,elements[E_T34].W_D85,待定,GDD-03 §2.1,P-01\n"
)
PENDING_CSV = (
    "pending_id,scope,field,filled_value,resolve_plan\n"
    "P-01,D-85T,damage/pen,10/8-12,数值章节：mm→0-20 换算细则（O-02）\n"
)


def deck_csv(copies_t3485: str = "2") -> str:
    return (
        "deck_key,card_key,copies\n"
        f"su_min,SU_T3485,{copies_t3485}\n"
        "su_min,SU_RIFLE,2\n"
        "su_min,SU_PARATROOP,1\n"
        "su_min,SU_TRUCK,1\n"
    )


def write_dataset(root: Path, *, cards: list[dict] | None = None,
                  elements: list[dict] | None = None,
                  weapons: list[dict] | None = None,
                  provenance: str | None = PROVENANCE_CSV,
                  pending: str | None = PENDING_CSV,
                  decks: dict[str, str] | None = None) -> Path:
    """写全套源表（utf-8-sig 带 BOM——DATA-01 §1.3）；返回 data 目录路径。"""
    data = root / "data"
    data.mkdir(parents=True)
    (data / "ground_cards.csv").write_text(
        _rows_to_csv(CARDS_COLS, card_rows() if cards is None else cards),
        encoding="utf-8-sig")
    (data / "ground_elements.csv").write_text(
        _rows_to_csv(ELEMENTS_COLS, element_rows() if elements is None else elements),
        encoding="utf-8-sig")
    (data / "ground_weapons.csv").write_text(
        _rows_to_csv(WEAPONS_COLS, weapon_rows() if weapons is None else weapons),
        encoding="utf-8-sig")
    if provenance is not None:
        (data / "ground_provenance.csv").write_text(provenance, encoding="utf-8-sig")
    if pending is not None:
        (data / "ground_pending.csv").write_text(pending, encoding="utf-8-sig")
    if decks is not None:
        decks_dir = data / "decks"
        decks_dir.mkdir()
        for name, text in decks.items():
            (decks_dir / name).write_text(text, encoding="utf-8-sig")
    return data


class LegalEndToEnd(unittest.TestCase):
    """合法卡：CSV → pydantic → JSON → 冻结 dataclass（H.2-1 端到端）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.data = write_dataset(root, decks={"su_min.csv": deck_csv()})
        self.out = root / "gen"
        self.written = bc.build_all(self.data, self.out)
        self.lib_path = self.written["library"]

    def tearDown(self):
        self._tmp.cleanup()

    def test_outputs_written_and_cli_zero(self):
        self.assertEqual(self.lib_path.name, "cards_ground.v1.json")
        self.assertTrue((self.out / "decks" / "su_min.json").is_file())
        self.assertEqual(
            bc.main(["--data-dir", str(self.data), "--out-dir", str(self.out)]), 0)

    def test_build_byte_stable(self):
        """同输入两次构建 JSON 字节相等（方案 §E.2-4 / H.2-5 确定性锚）。"""
        other = self.out.parent / "gen2"
        bc.build_all(self.data, other)
        self.assertEqual(self.lib_path.read_bytes(),
                         (other / "cards_ground.v1.json").read_bytes())
        self.assertEqual((self.out / "decks" / "su_min.json").read_bytes(),
                         (other / "decks" / "su_min.json").read_bytes())

    def test_json_int_representation_and_provenance(self):
        """枚举一律 int 表示（DATA-01 §2.4）＋_provenance 旁键＋键排序。"""
        doc = json.loads(self.lib_path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], cs.SCHEMA_VERSION)
        self.assertEqual(len(doc["source_sha256"]), 64)
        by_key = {c["card_key"]: c for c in doc["cards"]}
        rifle = by_key["SU_RIFLE"]
        self.assertEqual(rifle["faction"], 0)          # SOVIET
        self.assertEqual(rifle["category"], 1)         # INFANTRY
        self.assertEqual(rifle["delivery"], 0)         # NONE
        self.assertEqual(rifle["movement_class"], 0)   # FOOT
        self.assertEqual(rifle["flags"], (1 << 0) | (1 << 1))  # CAN_SPRINT;CAN_GARRISON
        self.assertEqual(rifle["mode_set"], 1)         # DIRECT
        self.assertEqual(rifle["air_ceiling"], -1)     # NONE→-1（§4.2）
        self.assertEqual(by_key["SU_T3485"]["category"], 2)
        self.assertEqual(by_key["SU_T3485"]["air_ceiling"], int(AltTier.MID))
        self.assertEqual(by_key["SU_T3485"]["own_weight_tons"], 320)  # 0.1t 刻度
        truck = by_key["SU_TRUCK"]
        self.assertEqual(truck["mode_set"], (1 << 2) | (1 << 3) | (1 << 4))  # TOW;CARGO;TRANSPORT
        self.assertEqual(truck["tow_tonnage"], 15)
        self.assertEqual(truck["_provenance"], [])      # 无偏离条目→空旁键
        t34_w = by_key["SU_T3485"]["elements"][0]["weapons"][0]
        self.assertEqual(t34_w["damage_type"], 0)       # KE
        self.assertEqual(t34_w["trajectory"], 0)        # DIRECT
        self.assertEqual(t34_w["target_mask"], 1)       # GROUND
        self.assertEqual(t34_w["restricted_profiles"],
                         [{"count": 2, "pen_bonus": 4}])
        self.assertEqual(t34_w["alt_profile"],
                         {"damage": 6, "blast_radius_cm": 1500})
        self.assertEqual(t34_w["self_defense"],
                         {"max_range_cm": 2000, "accuracy_mult_bp": 5000})
        self.assertEqual(by_key["SU_T3485"]["_provenance"][1]["field_path"],
                         "elements[E_T34].W_D85")
        self.assertEqual([p["pending_id"] for p in doc["pending"]], ["P-01"])
        deck_doc = json.loads(
            (self.out / "decks" / "su_min.json").read_text(encoding="utf-8"))
        self.assertEqual(deck_doc["faction"], 0)        # SOVIET——deck 亦 int 表示
        self.assertEqual(deck_doc["schema_version"], cs.SCHEMA_VERSION)

    def test_load_library_builds_frozen_dataclasses(self):
        lib = cl.load_library(self.lib_path)
        self.assertEqual(set(lib), {"SU_RIFLE", "SU_T3485",
                                    "SU_PARATROOP", "SU_TRUCK"})
        # ── 步兵卡：SQUAD/INFANTRY、count 展开、flags 位或 ──
        rifle = lib["SU_RIFLE"]
        ut = rifle.unit_template
        self.assertIsInstance(ut, UnitTemplate)
        self.assertEqual((ut.template_id, ut.name, ut.category, ut.cost),
                         (101, "步枪排", 1, 45))
        self.assertEqual(len(ut.element_templates), 3)  # count=3 展开（D.1#5）
        et = ut.element_templates[0]
        self.assertIsInstance(et, ElementTemplate)
        self.assertIsNone(et.armor_ke)                  # SOFT 为 None
        self.assertEqual(et.fire_arc_deg, 360)
        self.assertEqual(len(et.weapons), 1)
        wt = et.weapons[0]
        self.assertIsInstance(wt, WeaponTemplate)
        self.assertEqual((wt.name, wt.pen_min, wt.pen_max, wt.damage,
                          wt.max_range_cm, wt.salvo, wt.ammo_base,
                          wt.suppression_power),
                         ("SVT-40步枪", 2, 4, 3, 5000, 2, 60, 3))
        self.assertIsNone(wt.alt_profile)
        self.assertIsNone(wt.self_defense)
        self.assertEqual(wt.restricted_profiles, ())
        self.assertEqual(ut.flags, UnitFlag((1 << 0) | (1 << 1)))
        self.assertIsNone(ut.aura)
        self.assertIsNone(ut.air_ceiling)               # -1 → None
        # ── 装甲卡：Armor/Aura 子链＋mounted 解引用＋三条件槽 ──
        armor_ut = lib["SU_T3485"].unit_template
        aet = armor_ut.element_templates[0]
        self.assertEqual(aet.armor_ke, Armor(12, 9, 7, 4))
        self.assertEqual(aet.armor_he, Armor(8, 6, 5, 3))
        self.assertEqual(aet.element_type.name, "VEHICLE")
        self.assertEqual(aet.unit_type.name, "MECH")
        gun = aet.weapons[0]
        self.assertEqual(gun.alt_profile, AltProfile(damage=6, blast_radius_cm=1500))
        self.assertEqual(gun.self_defense,
                         SelfDefenseProfile(max_range_cm=2000, accuracy_mult_bp=5000))
        self.assertEqual(gun.restricted_profiles, ((2, 4),))  # types.py:199 形态
        self.assertEqual(aet.mounted_armament, (gun,))  # weapon_key 解引用→模板元组
        self.assertIs(aet.mounted_armament[0], gun)     # 同一实例（非复制）
        self.assertEqual(armor_ut.air_ceiling, AltTier.MID)
        self.assertEqual(armor_ut.movement_class, MovementClass.TRACK)
        self.assertEqual(armor_ut.own_weight_tons, 320)
        self.assertEqual(armor_ut.flags, UnitFlag(0))
        # ── 卡车：三模式位或＋吨位（DATA-01 §7：15≥13 ZiS-3 可拖、30≥25 M-30 可拖）──
        truck_ut = lib["SU_TRUCK"].unit_template
        self.assertEqual(truck_ut.mode_set, (1 << 2) | (1 << 3) | (1 << 4))
        self.assertEqual(truck_ut.tow_tonnage, 15)
        tet = truck_ut.element_templates[0]
        self.assertEqual((tet.seats, tet.cargo_rounds_max, tet.cargo_medical_max,
                          tet.cargo_weight_max), (3, 600, 120, 500))
        self.assertEqual(tet.armor_ke, Armor(0, 0, 0, 0))
        # ── 卡记录层（DATA-01 §9：不进 UnitTemplate 的 8 键）──
        self.assertEqual((rifle.faction, rifle.pool, rifle.per_card_limit,
                          rifle.quota_group, rifle.unlock_by, rifle.delivery),
                         ("SOVIET", "MAIN", None, "NONE", "", "NONE"))
        para = lib["SU_PARATROOP"]
        self.assertEqual((para.pool, para.delivery, para.unit_template.cost),
                         ("RESERVE", "LI2", 60))        # C.3 对表通过
        self.assertEqual(len(lib["SU_T3485"].provenance), 2)  # 旁键透传

    def test_load_deck_and_runtime_validate_deck(self):
        lib = cl.load_library(self.lib_path)
        deck = cl.load_deck(self.out / "decks" / "su_min.json")
        self.assertEqual(deck.deck_key, "su_min")
        self.assertEqual(deck.faction, "SOVIET")
        self.assertEqual(deck.cards,
                         (("SU_T3485", 2), ("SU_RIFLE", 2),
                          ("SU_PARATROOP", 1), ("SU_TRUCK", 1)))
        kwargs = dict(  # 阈值显式注入——唯一权威 card_schema（DATA-01 §12 D-1）
            per_card_limit_by_category=cs.PER_CARD_LIMIT_BY_CATEGORY,
            category_quota=cs.CATEGORY_QUOTA,
            fire_support_subquota=cs.FIRE_SUPPORT_SUBQUOTA,
            points_main_cap=cs.POINTS_MAIN_CAP,
            points_reserve_cap=cs.POINTS_RESERVE_CAP,
        )
        cl.validate_deck(deck, lib, library_schema_version=cs.SCHEMA_VERSION,
                         **kwargs)  # 合法即不抛
        over = cl.DeckData(schema_version=cs.SCHEMA_VERSION, deck_key="bad",
                           faction="SOVIET", cards=(("SU_T3485", 3),))
        with self.assertRaises(cl.CardLoaderError) as ctx:
            cl.validate_deck(over, lib, **kwargs)  # D032 装甲默认 2
        self.assertIn("D032", str(ctx.exception))


class IllegalAtBuildTime(unittest.TestCase):
    """三类非法卡在管线构建期报错（任务验收①②③）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_deck_over_d032_limit(self):
        """① 超 D032：装甲卡 3 份 > 默认限 2——deck 构建期 ValueError（H.1）。"""
        data = write_dataset(self.root,
                             decks={"su_min.csv": deck_csv(copies_t3485="3")})
        with self.assertRaises(ValueError) as ctx:
            bc.build_all(data, self.root / "gen")
        self.assertIn("D032", str(ctx.exception))

    def test_missing_required_field(self):
        """② 缺必填：optics_ground_cm 留空——读取器必填门报错（A.1#12）。"""
        rows = card_rows()
        rows[0]["optics_ground_cm"] = ""
        data = write_dataset(self.root, cards=rows,
                             decks={"su_min.csv": deck_csv()})
        with self.assertRaises(ValueError) as ctx:
            bc.build_all(data, self.root / "gen")
        self.assertIn("optics_ground_cm", str(ctx.exception))

    def test_float_weapon_pen(self):
        """③ 类型错误（float 文本）：pen_max="4.5"——int() 白名单拒（H.1）。"""
        rows = weapon_rows()
        rows[0]["pen_max"] = "4.5"
        data = write_dataset(self.root, weapons=rows,
                             decks={"su_min.csv": deck_csv()})
        with self.assertRaises(ValueError) as ctx:
            bc.build_all(data, self.root / "gen")
        self.assertIn("pen_max", str(ctx.exception))

    def test_float_card_cost(self):
        """③ 类型错误（float 文本）：cost="1.5"——同上（CSV 层拦，未到 pydantic）。"""
        rows = card_rows()
        rows[0]["cost"] = "1.5"
        data = write_dataset(self.root, cards=rows,
                             decks={"su_min.csv": deck_csv()})
        with self.assertRaises(ValueError) as ctx:
            bc.build_all(data, self.root / "gen")
        self.assertIn("cost", str(ctx.exception))

    def test_float_via_memory_dict_rejected_by_pydantic(self):
        """③ 补充（内存注入路径）：float 值直投 pydantic——StrictInt 拒（双保险）。"""
        payload = {
            "card_key": "SU_X", "template_id": 199, "name": "x",
            "faction": "SOVIET", "category": "INFANTRY", "cost": 1.5,
            "pool": "MAIN", "optics_ground_cm": 1400, "stealth_base": 1,
            "speed_tier": 1, "movement_class": "FOOT",
            "elements": [{"element_key": "E1", "count": 1,
                          "element_type": "SQUAD", "unit_type": "INFANTRY",
                          "hp_max": 8}],
        }
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(payload)

    def test_provenance_dangling_pending_id(self):
        """对账（DATA-01 §6.3 引用子集）：pending_id 悬挂即报错。"""
        provenance = PROVENANCE_CSV.replace("P-01\n", "P-XX\n")
        data = write_dataset(self.root, provenance=provenance,
                             decks={"su_min.csv": deck_csv()})
        with self.assertRaises(ValueError) as ctx:
            bc.build_all(data, self.root / "gen")
        self.assertIn("P-XX", str(ctx.exception))


class LoaderGates(unittest.TestCase):
    """加载器门：版本门两分支、类型白名单、空降对表、双轨锁死互检。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        cls.data = write_dataset(root, decks={"su_min.csv": deck_csv()})
        cls.out = root / "gen"
        bc.build_all(cls.data, cls.out)
        cls.lib_path = cls.out / "cards_ground.v1.json"
        cls.doc = json.loads(cls.lib_path.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _rewrite(self, mutate) -> Path:
        import copy
        doc = copy.deepcopy(self.doc)
        mutate(doc)
        tmp = Path(self._tmp.name) / "mutated.json"
        tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return tmp

    def test_version_gate_major_unsupported(self):
        path = self._rewrite(lambda d: d.update(schema_version="2.0"))
        with self.assertRaises(cl.CardLoaderError):
            cl.load_library(path)

    def test_version_gate_minor_over_bound(self):
        path = self._rewrite(lambda d: d.update(schema_version="1.99"))
        with self.assertRaises(cl.CardLoaderError):
            cl.load_library(path)

    def test_float_value_in_json_rejected(self):
        def mutate(d):
            d["cards"][0]["cost"] = 1.5
        with self.assertRaises(cl.CardLoaderError) as ctx:
            cl.load_library(self._rewrite(mutate))
        self.assertIn("cost", str(ctx.exception))

    def test_bool_value_in_json_rejected(self):
        """bool 是 int 子类——type(v) is int 白名单必须显式拒。"""
        def mutate(d):
            d["cards"][0]["cost"] = True
        with self.assertRaises(cl.CardLoaderError):
            cl.load_library(self._rewrite(mutate))

    def test_paratroop_unknown_card_rejected(self):
        """空降对表（C.3）：delivery=LI2 但 card_key 未在 PARATROOP_CARDS 登记。"""
        def mutate(d):
            for c in d["cards"]:
                if c["card_key"] == "SU_PARATROOP":
                    c["card_key"] = "SU_FAKE_DROP"
        with self.assertRaises(cl.CardLoaderError) as ctx:
            cl.load_library(self._rewrite(mutate))
        self.assertIn("PARATROOP", str(ctx.exception))

    def test_duplicate_template_id_rejected(self):
        def mutate(d):
            d["cards"][1]["template_id"] = d["cards"][0]["template_id"]
        with self.assertRaises(cl.CardLoaderError) as ctx:
            cl.load_library(self._rewrite(mutate))
        self.assertIn("template_id", str(ctx.exception))

    def test_deck_version_gate(self):
        path = self.out / "decks" / "su_min.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["schema_version"] = "2.0"
        tmp = Path(self._tmp.name) / "deck2.json"
        tmp.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(cl.CardLoaderError):
            cl.load_deck(tmp)

    def test_no_drift_lock_against_card_schema(self):
        """双轨锁死：loader 侧双写表与 card_schema 单点权威逐值一致（防漂移）。"""
        self.assertEqual(cl.SUPPORTED_CARD_SCHEMA,
                         cs.SUPPORTED_CARD_SCHEMA)
        for domain, table in cl.VALUE_TOKEN.items():
            self.assertEqual(
                table, {v: k for k, v in cs.TOKEN_VALUE[domain].items()},
                f"VALUE_TOKEN[{domain!r}] 与 TOKEN_VALUE 反向不一致")
        for version in ("1.0", "1.1", "1.99", "2.0", "0.9", "x.y", "1"):
            self.assertEqual(cl.schema_version_supported(version),
                             cs.schema_version_supported(version),
                             f"版本判定漂移: {version!r}")


if __name__ == "__main__":
    unittest.main()
