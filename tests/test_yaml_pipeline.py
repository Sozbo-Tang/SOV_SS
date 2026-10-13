"""YAML 配置层管线测试（tools/build_yaml.py × card_schema 1.4 × card_loader/air_loader
——GP-01 §1.2 迁移验收锚，DATA-03 §4）。

锚族：
① 迁移逐字节相等（强）：data/yaml 编译产物中「现存 10 卡的 cards 子数组（按 CSV 产物
   原序）＋pending 旧 23 条子序列」与 CSV 时代归档产物（data/legacy_csv/gen/
   cards_ground.v1.json）逐字节相等（仅 source_sha256 允许异）——数据搬家零行为漂移；
② 字节稳定重建：同输入两次构建三类产物逐字节相等＋与仓库 data/gen 在位产物一致；
③ 全卡加载（数量＝策划全集）：地面 67 卡（苏 33/德 34＝表格行数全录＋表外空降两卡，
   不以凑满 40/阵营为验收——差额 P-201/202/203 pending 在案）逐卡 load_library 构造
   冻结 dataclass 无 TypeError；航空 10 机型＋7 武器档案＋2 空降对表记录 air_load；
④ 文件划分：data/yaml/units 十地面文件卡数＝GP-01 §1.1 拍板（6/10/7/5/5×2）；
⑤ schema 纪律：严格 int（YAML 手写 1.0 被 StrictInt 拒）＋extra=forbid＋版本门；
⑥ 双写互检：card_schema/card_loader/air_loader 三处版本表同值；air 空降对表
   spec.delivery 与机型池同一性（card_loader._check_paratroop_alignment 依赖）。

引用：docs/GP-01-断箭玩法对照与改造方案-v1.md §1；docs/DATA-03-配置层YAML拍板-v1.md。
"""
import json
import tempfile
import unittest
from pathlib import Path

from sovs.sim import air_loader as al
from sovs.sim import card_loader as cl
from sovs.sim import card_schema as cs
from sovs.sim.air import AircraftTemplate
from sovs.sim.types import ElementTemplate, UnitTemplate, WeaponTemplate
from tools import build_yaml as by

REPO_ROOT = Path(__file__).resolve().parents[1]
YAML_DIR = REPO_ROOT / "data" / "yaml"
GEN_DIR = REPO_ROOT / "data" / "gen"
LEGACY_GEN = REPO_ROOT / "data" / "legacy_csv" / "gen" / "cards_ground.v1.json"

#: CSV 时代首批 10 卡（六类代表——迁移子集；顺序＝CSV 产物 cards 原序）
LEGACY_KEYS = (
    "SU_RECON", "SU_RIFLE", "SU_PARATROOP", "SU_COMMISSAR", "SU_T3485",
    "SU_ZIS3", "SU_TRUCK", "GER_GRENADIER", "GER_PARATROOP", "GER_PAK40",
)

#: GP-01 §1.1 文件划分拍板：文件名 → 卡数（地面十文件；air_* 三文件另计）
FILE_CARD_COUNTS = {
    "su_recon.yaml": 6, "su_infantry.yaml": 10, "su_armor.yaml": 7,
    "su_fire_support.yaml": 5, "su_aa_logistics.yaml": 5,
    "ger_recon.yaml": 6, "ger_infantry.yaml": 10, "ger_armor.yaml": 7,
    "ger_fire_support.yaml": 6, "ger_aa_logistics.yaml": 5,
}
AIR_FILE_COUNTS = {"air_weapons.yaml": 7, "air_su.yaml": 5, "air_ger.yaml": 5}


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


class MigrationByteAnchor(unittest.TestCase):
    """① 迁移逐字节相等（DATA-03 §4.1 强锚——承 test_card_pipeline §E.2-4 先例）。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / "gen"
        cls.written = by.build_all(YAML_DIR, cls.out)  # 同输入重建（不触仓库 gen/）
        cls.new_doc = json.loads(cls.written["library"].read_text(encoding="utf-8"))
        cls.old_doc = json.loads(LEGACY_GEN.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @staticmethod
    def _strip_post_freeze_edits(cards: list) -> list:
        """〔终审修复块 2026-10-13〕迁移后首例地面数据变更的显式归一（改判先改这里）：
        ① 武器行剥 crit_guaranteed（schema 1.6 新序列化键——归档 1.3 无此键，
          False≡缺省值面无漂移）；
        ② SU_TRUCK/GER_TRUCK 舱位 4000→归档值 600（basics:198-200 手册刻度落地
          ——卡车舱位 600→4000，仅此两卡两字段）。除这两处外仍逐字节相等。"""
        out = []
        for c in cards:
            c = json.loads(json.dumps(c))            # 深拷贝（不改 gen 原文）
            if c["card_key"] in ("SU_TRUCK", "GER_TRUCK"):
                for e in c["elements"]:
                    for f in ("cargo_rounds_max", "cargo_weight_max"):
                        if e.get(f) == 4000:
                            e[f] = 600
            for e in c["elements"]:
                for w in e.get("weapons", ()):
                    w.pop("crit_guaranteed", None)
            out.append(c)
        return out

    def test_legacy_cards_subset_byte_equal(self):
        """10 卡 cards 子数组（CSV 原序）逐字节相等——YAML/CSV 两管线零行为漂移
        （迁移后地面数据变更经 _strip_post_freeze_edits 显式归一在册）。"""
        new_by_key = {c["card_key"]: c for c in self.new_doc["cards"]}
        missing = [k for k in LEGACY_KEYS if k not in new_by_key]
        self.assertEqual(missing, [])
        subset = [new_by_key[k] for k in LEGACY_KEYS]
        self.assertEqual(_dumps(self._strip_post_freeze_edits(subset)),
                         _dumps(self.old_doc["cards"]))

    def test_legacy_pending_subsequence_byte_equal(self):
        """旧 23 条 pending 子序列逐字节相等（新登记 P-201~P-314 只增不改）。"""
        old_ids = {p["pending_id"] for p in self.old_doc["pending"]}
        self.assertEqual(len(old_ids), len(self.old_doc["pending"]))  # 原库编号唯一
        kept = [p for p in self.new_doc["pending"] if p["pending_id"] in old_ids]
        self.assertEqual(_dumps(kept), _dumps(self.old_doc["pending"]))

    def test_only_source_sha_may_differ_at_root(self):
        """根层差异白名单＝source_sha256＋本轮拍板的 minor 升版（GP-01 §1.3：航空入库
        1.3→1.4——归档 CSV 产物恒 1.3，YAML 产物随 cs.SCHEMA_VERSION；数组面不受影响）。"""
        self.assertEqual(self.new_doc["schema_version"], cs.SCHEMA_VERSION)
        self.assertEqual(self.old_doc["schema_version"], "1.3")  # 归档冻结
        self.assertNotEqual(self.new_doc["source_sha256"],
                            self.old_doc["source_sha256"])  # 源文本哈希口径不同（CSV vs YAML）

    def test_legacy_deck_products_equivalent_modulo_version(self):
        """卡组产物：卡集/份数/阵营 int 表示不变（schema_version 随库 1.3→1.4）。"""
        for deck_key in ("su_min", "ger_min"):
            new = json.loads(
                (self.out / "decks" / f"{deck_key}.json").read_text(encoding="utf-8"))
            old = json.loads(
                (REPO_ROOT / "data/legacy_csv/gen/decks" / f"{deck_key}.json")
                .read_text(encoding="utf-8"))
            new.pop("schema_version"), old.pop("schema_version")
            self.assertEqual(new, old, deck_key)


class ByteStableRebuild(unittest.TestCase):
    """② 同输入两次构建字节相等＋在位产物一致（方案 §E.2-4 锚平移）。"""

    def test_two_builds_and_repo_gen_identical(self):
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            w1 = by.build_all(YAML_DIR, Path(tmp1))
            w2 = by.build_all(YAML_DIR, Path(tmp2))
            for key, path in w1.items():
                self.assertEqual(path.read_bytes(), w2[key].read_bytes(), key)
                repo = GEN_DIR / path.relative_to(w1["library"].parent)
                self.assertTrue(repo.is_file(), f"缺在位产物 {repo}")
                self.assertEqual(path.read_bytes(), repo.read_bytes(), key)


class FullLibraryLoad(unittest.TestCase):
    """③ 全卡加载 smoke（数量＝策划全集——GP-01 §8 M1 验收）。"""

    @classmethod
    def setUpClass(cls):
        cls.lib = cl.load_library(GEN_DIR / "cards_ground.v1.json")
        cls.air = al.load_air_library(GEN_DIR / "cards_air.v1.json")

    def test_ground_counts_match_gdd_tables(self):
        """苏 33/德 34＝表格行数全录＋表外空降两卡（不以凑满 40 为验收——§1.4）。"""
        su = [k for k, r in self.lib.items() if r.faction == "SOVIET"]
        ger = [k for k, r in self.lib.items() if r.faction == "GERMAN"]
        self.assertEqual(len(su), 33)
        self.assertEqual(len(ger), 34)
        self.assertEqual(len(self.lib), 67)
        for key in LEGACY_KEYS:  # 首批 10 卡键全在
            self.assertIn(key, self.lib)

    def test_category_distribution(self):
        """类别分布＝GDD-01 表结构（侦察 6/步兵 10[含空降]/装甲 7/火支 5|6/防空后勤 5）。"""
        cat = {(r.faction, cl.VALUE_TOKEN["category"][r.unit_template.category])
               for r in self.lib.values()}
        expected = {
            ("SOVIET", "RECON"), ("SOVIET", "INFANTRY"), ("SOVIET", "ARMOR"),
            ("SOVIET", "FIRE_SUPPORT"), ("SOVIET", "AA_LOGISTICS"),
            ("GERMAN", "RECON"), ("GERMAN", "INFANTRY"), ("GERMAN", "ARMOR"),
            ("GERMAN", "FIRE_SUPPORT"), ("GERMAN", "AA_LOGISTICS"),
        }
        self.assertEqual(cat, expected)
        counts = {}
        for r in self.lib.values():
            key = (r.faction, cl.VALUE_TOKEN["category"][r.unit_template.category])
            counts[key] = counts.get(key, 0) + 1
        self.assertEqual(counts, {
            ("SOVIET", "RECON"): 6, ("SOVIET", "INFANTRY"): 10, ("SOVIET", "ARMOR"): 7,
            ("SOVIET", "FIRE_SUPPORT"): 5, ("SOVIET", "AA_LOGISTICS"): 5,
            ("GERMAN", "RECON"): 6, ("GERMAN", "INFANTRY"): 10, ("GERMAN", "ARMOR"): 7,
            ("GERMAN", "FIRE_SUPPORT"): 6, ("GERMAN", "AA_LOGISTICS"): 5})

    def test_every_card_builds_frozen_templates(self):
        """67 卡逐卡 smoke：构造无 TypeError（M1 验收「全卡可 load_library」）。"""
        for key, rec in self.lib.items():
            self.assertIsInstance(rec.unit_template, UnitTemplate, key)
            self.assertGreaterEqual(len(rec.unit_template.element_templates), 1, key)
            for et in rec.unit_template.element_templates:
                self.assertIsInstance(et, ElementTemplate, key)
                for w in et.weapons:
                    self.assertIsInstance(w, WeaponTemplate, key)

    def test_paratroop_and_air_pool(self):
        """航空 10 机型＋7 档＋2 空降对表；spec.delivery 与机型池对象同一（C.3）。"""
        self.assertEqual(len(self.air.aircraft), 10)
        self.assertEqual(len(self.air.weapons), 7)
        self.assertEqual(set(self.air.paratroops), {"SU_PARATROOP", "GER_PARATROOP"})
        for t in self.air.aircraft.values():
            self.assertIsInstance(t, AircraftTemplate)
        spec = self.air.paratroops["SU_PARATROOP"]
        self.assertIs(spec.delivery, self.air.aircraft["LI2"])
        self.assertEqual((spec.cost_points, spec.pool), (60, "RESERVE"))
        spec_g = self.air.paratroops["GER_PARATROOP"]
        self.assertIs(spec_g.delivery, self.air.aircraft["JU52"])

    def test_decks_load_and_validate(self):
        for deck_key in ("su_min", "ger_min"):
            deck = cl.load_deck(GEN_DIR / "decks" / f"{deck_key}.json")
            cl.validate_deck(deck, self.lib,
                             library_schema_version=cs.SCHEMA_VERSION,
                             per_card_limit_by_category=cs.PER_CARD_LIMIT_BY_CATEGORY,
                             category_quota=cs.CATEGORY_QUOTA,
                             fire_support_subquota=cs.FIRE_SUPPORT_SUBQUOTA,
                             points_main_cap=cs.POINTS_MAIN_CAP,
                             points_reserve_cap=cs.POINTS_RESERVE_CAP)

    def test_pending_registry_covers_gp01_gaps(self):
        """P-201/202/203（GDD-01 卡数差额）与新卡插值 P-301+ 在案。"""
        doc = json.loads((GEN_DIR / "cards_ground.v1.json").read_text(encoding="utf-8"))
        ids = {p["pending_id"] for p in doc["pending"]}
        self.assertTrue({"P-101", "P-123"} <= ids)      # 旧 23 条全量在库
        self.assertTrue({"P-201", "P-202", "P-203"} <= ids)  # GP-01 §1.4 三差额
        self.assertIn("P-303", ids)                     # 新卡插值总纲


class FileLayout(unittest.TestCase):
    """④ 文件划分（GP-01 §1.1 拍板——units 十地面文件＋air 三文件）。"""

    def test_unit_file_card_counts(self):
        import yaml  # 构建期依赖（tests 面——DATA-03 §6）
        for name, expect in {**FILE_CARD_COUNTS, **AIR_FILE_COUNTS}.items():
            doc = yaml.safe_load((YAML_DIR / "units" / name).read_text(encoding="utf-8"))
            section = "cards" if "cards" in doc else "weapons"
            self.assertEqual(len(doc[section]), expect, name)
            self.assertEqual(doc["schema_version"], cs.SCHEMA_VERSION, name)


class SchemaDiscipline(unittest.TestCase):
    """⑤ schema 纪律负例（严格 int/extra=forbid/版本门——DATA-03 §2）。"""

    def _write_min_yaml(self, tmp: Path, cards_yaml: str) -> Path:
        src = tmp / "yaml"
        for sub in ("units", "decks", "sidecar"):
            (src / sub).mkdir(parents=True)
        for name in by.GROUND_UNIT_FILES:
            (src / "units" / name).write_text(
                'schema_version: "1.6"\ncards: []\n', encoding="utf-8")
        (src / "units" / "su_recon.yaml").write_text(cards_yaml, encoding="utf-8")
        for name in by.AIR_FILES:
            (src / "units" / name).write_text(
                'schema_version: "1.6"\n' + ("weapons: []" if "weapons" in name else "cards: []"),
                encoding="utf-8")
        (src / "sidecar" / "provenance.yaml").write_text(
            'schema_version: "1.6"\nentries: []\n', encoding="utf-8")
        (src / "sidecar" / "pending.yaml").write_text(
            'schema_version: "1.6"\nentries: []\n', encoding="utf-8")
        return src

    _CARD = """schema_version: "1.6"
cards:
  - card_key: SU_FLOAT
    template_id: 901
    name: 浮点卡
    faction: SOVIET
    category: RECON
    cost: 10
    pool: MAIN
    optics_ground_cm: %s
    stealth_base: 5
    speed_tier: 1
    movement_class: FOOT
    elements:
      - element_key: E_X
        count: 1
        element_type: SQUAD
        unit_type: INFANTRY
        hp_max: 5
        weapons: []
"""

    def test_yaml_float_rejected_by_strict_int(self):
        """YAML 手写 1.0 → safe_load 出 float → StrictInt 拒（与 CSV 拒 "7.5" 同强度）。"""
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write_min_yaml(Path(tmp), self._CARD % "6000.0")
            with self.assertRaises(ValueError) as ctx:
                by.build_ground_library(src)
            self.assertIn("optics_ground_cm", str(ctx.exception))

    def test_unknown_card_key_rejected_by_extra_forbid(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = self._CARD.replace("    pool: MAIN\n", "    pool: MAIN\n    bogus_field: 1\n") % "6000"
            src = self._write_min_yaml(Path(tmp), bad)
            with self.assertRaises(ValueError):
                by.build_ground_library(src)

    def test_air_price_zero_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write_min_yaml(Path(tmp), self._CARD % "6000")
            (src / "units" / "air_su.yaml").write_text(
                'schema_version: "1.6"\ncards:\n'
                '  - card_key: X1\n    template_id: 91\n    name: 零价机\n    faction: SOVIET\n'
                '    role: BOMBER\n    cost_body: 10\n    hp_max: 60\n    armor_aa: 0\n'
                '    speed_cm_tick: 100\n    dogfight_power: 1\n    maneuver: 1\n'
                '    alt_ceiling: MID\n    weapons: [{ref: W_BOMB_FAB100, ammo: 4}]\n'
                '    payload_max_bombs: 4\n    turret_damage: 2\n'
                '    payload_price: {BOMB: 0}\n', encoding="utf-8")
            lib, _ = by.build_ground_library(src)
            with self.assertRaises(ValueError):
                by.build_air_library(src, lib)


class VersionInterlock(unittest.TestCase):
    """⑥ 三处版本表双写互检＋air JSON 版本门。"""

    def test_supported_tables_in_lockstep(self):
        self.assertEqual(cs.SUPPORTED_CARD_SCHEMA, {1: 6})       # minor 演进锁当前值（1.5→1.6 终审修复块武器行 crit_guaranteed）
        self.assertEqual(cl.SUPPORTED_CARD_SCHEMA, cs.SUPPORTED_CARD_SCHEMA)
        self.assertEqual(al.SUPPORTED_CARD_SCHEMA, cs.SUPPORTED_CARD_SCHEMA)
        self.assertFalse(cs.schema_version_supported("1.7"))  # 上界 1.6（终审修复块）
        self.assertTrue(cs.schema_version_supported("1.3"))     # 旧产物（归档 CSV 重建）仍可加载

    def test_air_product_version_gate(self):
        doc = json.loads((GEN_DIR / "cards_air.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], cs.SCHEMA_VERSION)
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({**doc, "schema_version": "2.0"}), encoding="utf-8")
            with self.assertRaises(al.AirLoaderError):
                al.load_air_library(bad)


if __name__ == "__main__":
    unittest.main()
