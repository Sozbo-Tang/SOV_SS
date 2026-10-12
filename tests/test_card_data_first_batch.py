"""首批最小卡组数据测试（CSV 五表：P-13 空降两卡＋六类代表卡，共 10 张）。

〔2026-10-12 GP-01 M1 迁移批注〕数据源由 data/ 五表改指 **data/legacy_csv/ 归档**
（DATA-03 §4.1：CSV 退役留档保审计面——本测试＝归档 CSV 自洽性回归锚：build_cards
仍可从归档重建并可加载；数据面权威已让位 data/yaml/（tests/test_yaml_pipeline.py
承载迁移逐字节相等锚，含「10 卡 YAML 编译产物 cards/pending 与本归档产物相等」）。
归档产物 data/legacy_csv/gen/ 冻结于 schema 1.3；同源重建随 card_schema 当前值 1.4
（航空入库 minor 升版——GP-01 §1.3），cards/pending 数组值不受版本影响〕。

覆盖（任务验收①③③）：
① P-13 两卡（SU_PARATROOP/GER_PARATROOP）存在于卡库且其元素为冻结
   ElementTemplate 实例，卡记录字段与 air_data.PARATROOP_CARDS 对表
   （cost 60/65、RESERVE、LI2/JU52——GDD-02 v1.9 :326/:335）；
② 全部 10 卡 → card_loader.load_library 构造冻结 dataclass
   （UnitTemplate/ElementTemplate/WeaponTemplate，DATA-01 §9 映射表）；
③ 代表卡卡组（su_min/ger_min）通过 D032 同型限份＋D011 类别配额＋R-13 子配额
   ＋D038 点数全量校验（card_loader.validate_deck，阈值注入——DATA-01 §12 D-1）。
"""
import json
import tempfile
import unittest
from pathlib import Path

from sovs.sim import card_loader as cl
from sovs.sim import card_schema as cs
from sovs.sim.air_data import JU52, LI2, PARATROOP_CARDS
from sovs.sim.types import (AltProfile, ElementTemplate, UnitTemplate,
                            WeaponTemplate)
from tools import build_cards as bc

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "legacy_csv"   # CSV 归档（DATA-03 §4.1）
GEN_LIBRARY = DATA_DIR / "gen" / "cards_ground.v1.json"  # CSV 时代冻结产物（1.3）

#: 首批 10 卡（六类：侦察/步兵/装甲/火支×2子类/防空后勤/指挥班组＋空降两卡）
FIRST_BATCH = (
    "SU_RECON", "SU_RIFLE", "SU_PARATROOP", "SU_COMMISSAR", "SU_T3485",
    "SU_ZIS3", "SU_TRUCK", "GER_GRENADIER", "GER_PARATROOP", "GER_PAK40",
)
#: 类别覆盖（category int → 令牌，card_loader.VALUE_TOKEN §4.2）
CATEGORY_OF = {
    "SU_RECON": "RECON", "SU_RIFLE": "INFANTRY", "SU_PARATROOP": "INFANTRY",
    "SU_COMMISSAR": "INFANTRY", "SU_T3485": "ARMOR", "SU_ZIS3": "FIRE_SUPPORT",
    "SU_TRUCK": "AA_LOGISTICS", "GER_GRENADIER": "INFANTRY",
    "GER_PARATROOP": "INFANTRY", "GER_PAK40": "FIRE_SUPPORT",
}


class FirstBatchData(unittest.TestCase):
    """加载生成的 JSON（data/gen）并断言首批数据契约。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / "gen"
        cls.written = bc.build_all(DATA_DIR, cls.out)  # 同输入重建（不触仓库 gen/）
        cls.lib_path = cls.written["library"]
        cls.lib = cl.load_library(cls.lib_path)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _quota_kwargs(self):
        """阈值显式注入（唯一权威 card_schema——DATA-01 §12 D-1，无双轨）。"""
        return dict(
            per_card_limit_by_category=cs.PER_CARD_LIMIT_BY_CATEGORY,
            category_quota=cs.CATEGORY_QUOTA,
            fire_support_subquota=cs.FIRE_SUPPORT_SUBQUOTA,
            points_main_cap=cs.POINTS_MAIN_CAP,
            points_reserve_cap=cs.POINTS_RESERVE_CAP,
        )

    def test_generated_json_matches_rebuild(self):
        """归档产物在位；同源（legacy_csv）重建 cards/pending 数组与归档一致（§E.2-4
        确定性锚——版本根键随 schema 当前值 1.4，归档冻结 1.3，数组面不受影响）。"""
        self.assertTrue(GEN_LIBRARY.is_file(), f"缺归档产物 {GEN_LIBRARY}")
        archived = json.loads(GEN_LIBRARY.read_text(encoding="utf-8"))
        rebuilt = json.loads(self.lib_path.read_text(encoding="utf-8"))
        self.assertEqual(archived["schema_version"], "1.3")   # 归档冻结
        self.assertEqual(rebuilt["schema_version"], cs.SCHEMA_VERSION)
        self.assertEqual(rebuilt["cards"], archived["cards"])
        self.assertEqual(rebuilt["pending"], archived["pending"])

    def test_first_batch_card_set(self):
        self.assertEqual(set(self.lib), set(FIRST_BATCH))
        doc = json.loads(self.lib_path.read_text(encoding="utf-8"))
        self.assertEqual(len(doc["cards"]), 10)

    def test_p13_paratroop_cards_are_frozen_templates(self):
        """P-13 两卡存在、为 ElementTemplate 实例、与 air_data 对表。"""
        by_key = {s.card_key: s for s in PARATROOP_CARDS}
        delivery_of = {"SU_PARATROOP": "LI2", "GER_PARATROOP": "JU52"}
        delivery_ac = {"SU_PARATROOP": LI2, "GER_PARATROOP": JU52}
        for key, spec in by_key.items():
            self.assertIn(key, self.lib)
            rec = self.lib[key]
            self.assertIsInstance(rec.unit_template, UnitTemplate)
            for et in rec.unit_template.element_templates:
                self.assertIsInstance(et, ElementTemplate)
            # 卡记录层对表（loader 加载期 _check_paratroop_alignment 已强制，
            # 此处再显式断言：GDD-02 :326/:335；air_data.py:368-381）
            self.assertEqual(rec.unit_template.name, spec.name)
            self.assertEqual(rec.unit_template.cost, spec.cost_points)
            self.assertEqual(rec.pool, "RESERVE")
            self.assertEqual(rec.pool, spec.pool)
            self.assertEqual(rec.delivery, delivery_of[key])
            self.assertIs(delivery_ac[key], spec.delivery)  # 投送机型对象同一（C.3）

    def test_all_cards_build_frozen_weapon_templates(self):
        """10 卡全部元素/武器构造为冻结 dataclass（DATA-01 §9）。"""
        for key in FIRST_BATCH:
            rec = self.lib[key]
            self.assertIsInstance(rec.unit_template, UnitTemplate)
            self.assertGreaterEqual(len(rec.unit_template.element_templates), 1)
            for et in rec.unit_template.element_templates:
                self.assertIsInstance(et, ElementTemplate)
                for w in et.weapons:
                    self.assertIsInstance(w, WeaponTemplate)
            self.assertEqual(
                cl.VALUE_TOKEN["category"][rec.unit_template.category],
                CATEGORY_OF[key])

    def test_six_categories_and_fire_support_subclasses(self):
        """六类全覆盖＋火支两子类（榴 HOWITZER／反坦克 AT_GUN）。"""
        cats = {CATEGORY_OF[k] for k in FIRST_BATCH}
        self.assertEqual(cats, {"RECON", "INFANTRY", "ARMOR", "FIRE_SUPPORT",
                                "AA_LOGISTICS"})
        self.assertEqual(self.lib["SU_ZIS3"].quota_group, "HOWITZER")
        self.assertEqual(self.lib["GER_PAK40"].quota_group, "AT_GUN")

    def test_representative_decks_pass_quota_validation(self):
        """su_min/ger_min 通过 D032/D011/R-13/D038 全量校验（任务验收③）。"""
        for deck_key in ("su_min", "ger_min"):
            deck = cl.load_deck(self.written[f"deck/{deck_key}"])
            cl.validate_deck(deck, self.lib,
                             library_schema_version=cs.SCHEMA_VERSION,
                             **self._quota_kwargs())  # 合法即不抛

    def test_deck_over_d032_rejected(self):
        """负例：装甲 3 份超 D032 默认 2——运行期校验拒绝。"""
        over = cl.DeckData(schema_version=cs.SCHEMA_VERSION, deck_key="bad_armor",
                           faction="SOVIET", cards=(("SU_T3485", 3),))
        with self.assertRaises(cl.CardLoaderError) as ctx:
            cl.validate_deck(over, self.lib, **self._quota_kwargs())
        self.assertIn("D032", str(ctx.exception))

    def test_command_card_limit_one_and_melee_aura(self):
        """指挥班组代表卡：per_card_limit=1（D032）＋MELEE 光环+15%（D034）。"""
        rec = self.lib["SU_COMMISSAR"]
        self.assertEqual(rec.per_card_limit, 1)
        aura = rec.unit_template.aura
        self.assertIsNotNone(aura)
        self.assertEqual(aura.kind.name, "MELEE")   # 政委突击光环"跟我上"
        self.assertEqual(aura.bonus_bp, 1500)       # +15%（GDD-02 :388）

    def test_tonnage_and_p13_key_anchors(self):
        """吨位 0.1t 刻度（DATA-01 §7）与 T-34/85 基准价/三模式关键锚。"""
        self.assertEqual(self.lib["SU_TRUCK"].unit_template.tow_tonnage, 15)
        self.assertEqual(self.lib["GER_PAK40"].unit_template.own_weight_tons, 15)
        self.assertEqual(self.lib["SU_ZIS3"].unit_template.own_weight_tons, 13)
        self.assertEqual(self.lib["SU_T3485"].unit_template.cost, 100)  # D038 基准
        self.assertEqual(self.lib["SU_T3485"].unit_template.own_weight_tons, 300)
        # 卡车三模式 TOW|CARGO|TRANSPORT（D065）＝位 4|8|16
        self.assertEqual(self.lib["SU_TRUCK"].unit_template.mode_set, (1 << 2) | (1 << 3) | (1 << 4))
        # T-34/85 主炮 HE 档（R-11 alt_profile）
        gun = self.lib["SU_T3485"].unit_template.element_templates[0].weapons[0]
        self.assertEqual(gun.alt_profile, AltProfile(damage=6, blast_radius_cm=1200))

    def test_pending_registry_present(self):
        """P-xx 待定登记随库内嵌（DATA-01 §4.7/§6.3）。"""
        doc = json.loads(self.lib_path.read_text(encoding="utf-8"))
        ids = {p["pending_id"] for p in doc["pending"]}
        self.assertGreaterEqual(len(ids), 19)  # P-101..P-119
        self.assertTrue({"P-101", "P-103", "P-107"} <= ids)  # 空降/HP口径/换算

    def test_pb52_unit_level_terrain_overrides(self):
        """PB-52 单位级地形数值（2026-10-04 拍板落地——推翻 MV-B-01 defer，改
        「单位级覆盖、类级缺省回退」）：schema 1.0→1.1（DATA-01 §2.3-1 加可选字段＝
        minor；后 PB-53 复加元素级字段再 minor 至 1.2）；示例值两卡占位（P-120 待定
        登记——机制验证用，全量定标归数值章节）；
        其余 8 卡三列全空=0 → 回退类级缺省（N11 步兵路=野 → FOOT 卡天然留空）。"""
        doc = json.loads(self.lib_path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], cs.SCHEMA_VERSION)  # minor 演进锁当前值（PB-52 1.1→PB-53 1.2→PB-55 1.3）
        t34 = self.lib["SU_T3485"].unit_template                # 三值全示例
        self.assertEqual((t34.terrain_speed_override_bp,
                          t34.reverse_speed_override_bp,
                          t34.road_bonus_override_cm), (6500, 2500, 55))
        truck = self.lib["SU_TRUCK"].unit_template              # 单值示例（混合填充）
        self.assertEqual(truck.terrain_speed_override_bp, 5500)
        self.assertEqual(truck.reverse_speed_override_bp, 0)    # 空=回退类级
        self.assertEqual(truck.road_bonus_override_cm, 0)
        for key in FIRST_BATCH:                                 # 空值回退批量锚
            if key in ("SU_T3485", "SU_TRUCK"):
                continue
            ut = self.lib[key].unit_template
            self.assertEqual((ut.terrain_speed_override_bp,
                              ut.reverse_speed_override_bp,
                              ut.road_bonus_override_cm), (0, 0, 0), key)
        self.assertIn("P-120", {p["pending_id"] for p in doc["pending"]})
        prov_paths = {(entry["card_key"], entry["field_path"])
                      for card in doc["cards"]
                      for entry in card["_provenance"]}
        for col in ("terrain_speed_override_bp", "reverse_speed_override_bp",
                    "road_bonus_override_cm"):
            self.assertIn(("SU_T3485", col), prov_paths)        # provenance 留痕

    def test_pb53_self_smoke_charges_calibrated(self):
        """PB-53 载具自卫烟幕（2026-10-04 拍板落地——断箭 N32/映射 §五.19）：元素级
        可选字段 self_smoke_charges 加列（schema 1.1→1.2 minor——DATA-01 §2.3-1；
        ElementModel 16→17 字段）。
        〔2026-10-07 数据定标块重锚〕原「10 卡全默认 0」锚随 v1 定标翻转为两卡配属：
        SU_TRUCK=2（ask 字面点名——补给车高价值软目标）+SU_T34=2（勘察默认——史实锚
        T-34 BDSh 发烟罐、N32 载具自卫字面；ask 字面仅点名 SU_TRUCK，此项可撤销——
        P-121 更新在册），余 8 卡维持 0=无能力；发数与 cfg.self_smoke_default_charges=2
        同值。行为面：cmd_smoke 玩家令入口，HeadlessAI 不发 SmokeCmd=整局零扰动。"""
        doc = json.loads(self.lib_path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], cs.SCHEMA_VERSION)  # minor 演进锁当前值（PB-55 1.3→航空入库 1.4）
        self.assertEqual(cs.SUPPORTED_CARD_SCHEMA, {1: 4})
        self.assertEqual(cl.SUPPORTED_CARD_SCHEMA, cs.SUPPORTED_CARD_SCHEMA)
        for key in FIRST_BATCH:
            expect = 2 if key in ("SU_TRUCK", "SU_T3485") else 0   # v1 定标两卡配属
            for et in self.lib[key].unit_template.element_templates:
                self.assertEqual(et.self_smoke_charges, expect,
                                 (key, et.element_type))
        self.assertIn("P-121", {p["pending_id"] for p in doc["pending"]})
        prov = {(entry["card_key"], entry["field_path"])
                for card in doc["cards"] for entry in card["_provenance"]}
        self.assertIn(("SU_TRUCK", "elements[E_SU_TRUCK]"), prov)   # provenance 留痕
        self.assertIn(("SU_T3485", "elements[E_SU_T34]"), prov)


if __name__ == "__main__":
    unittest.main()
