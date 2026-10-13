"""士气效果接线测试（2026-10-04 士气效果接线块——GDD-00 D014 受压=命中/性能下降、
钉住=火力大减、溃逃=失控后撤；D023 命中率式「×士气惩罚」项 + GDD-05 下篇 B4:149
moraleFactor 按态乘区（受压×0.7/钉住×0.3）双锚；拍板清单 PB-55）：
- 命中乘区 morale_acc_factor_bp：按态取值 + fire_direct acc 链乘区（记录式 RNG 桩
  逐拍录取 chance_bp 实参——锚定与元素级连续项 aim_factor_bp 的叠乘组合值；整数
  乘除对操作数顺序不敏感，插位本身不可判别——2026-10-04 评审遗留⑥如实化）；
- 溃逃禁射 fire_permitted ⑨ 门：新 AIMING 不开 + 在途 AIMING 到期转 READY 不耗弹
  （⑦⑧ 同款双拦形态；SUPPRESSED/PINNED 不走许可门=乘区承载非禁射）；
- 冲刺破压跨阈值降档（PB-49 ×morale 链交叉验证：60→30 跨受压档、79→39 两档直落
  ——80→40 单档锚已在 tests/test_morale.py TestPB49FullChain）；
- 卡级士气阈值三级回退（D027:174 三列）：模板覆盖/单档覆盖（rout_th>100=永不溃逃
  差异化位）/0=回退 cfg 缺省 + 管线端到端（CSV→schema→JSON→UnitTemplate→
  system_morale）+ 现役 10 卡全空回退锚；
- 受压移动惩罚：无据不落（D014:97 受压=命中/性能下降，无移动项；行为锚在
  tests/test_morale.py test_stable_suppressed_no_slowdown=56 全速——本文件不重复）。

锚点算术（手推不自证）：
- acc 链（accuracy_base=10000、sup=50）：aim_factor=10000−6000×50//100=7000；
  STABLE=7000；SUPPRESSED=7000×7000//10000=4900；PINNED=7000×3000//10000=2100；
- 冲刺减半整除：60×5000//10000=30（<40 → STABLE）；79×5000//10000=39（<40 →
  两档直落 PINNED→STABLE）。
"""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from sovs.sim import card_loader as cl
from sovs.sim import card_schema as cs
from sovs.sim.combat import morale_acc_factor_bp
from sovs.sim.tables import CONFIG
from sovs.sim.tick import (add_unit, cmd_sprint, fire_direct, fire_permitted,
                           make_unit, make_world, system_morale, world_tick)
from sovs.sim.types import (DamageType, ElementTemplate, ElementType,
                            MoraleState, MovementClass, TargetDomain,
                            UnitTemplate, UnitType, WeaponTemplate, WState)
from tools import build_cards as bc

REPO_ROOT = Path(__file__).resolve().parents[1]


# ── 合成模板（template_id 96x 段——效果链载体，不对应真实卡）──

GUN = WeaponTemplate(name="GUN", damage_type=DamageType.KE, pen_max=5,
                     damage=10, max_range_cm=50000, aim_time_ticks=2,
                     reload_time_ticks=20, ammo_base=10, salvo=1,
                     dispersion_cm=100, accuracy_base_bp=10000,
                     projectile_speed_cm_tick=100)
GUN_ELEM = ElementTemplate(element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                           hp_max=20, weapons=(GUN,))
INF_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                           unit_type=UnitType.INFANTRY, hp_max=10)


def gun_tpl(template_id=960, **over):
    """可带士气阈值覆盖的效果链模板（覆盖槽 kwargs 直传 UnitTemplate）。"""
    return UnitTemplate(template_id=template_id, name="gun plt", category=2,
                        cost=50, element_templates=(GUN_ELEM,),
                        optics_ground_cm=20000, stealth_base=5, speed_tier=3,
                        movement_class=MovementClass.TRACK, **over)


def inf_tpl(template_id=961):
    return UnitTemplate(template_id=template_id, name="inf plt", category=1,
                        cost=40, element_templates=(INF_ELEM,),
                        optics_ground_cm=20000, stealth_base=5, speed_tier=3,
                        movement_class=MovementClass.FOOT)


def mk_pair(seed):
    """返回 (world, 射手单位, 靶单位)——靶已 spotted、射程内（30km）。"""
    w = make_world(seed)
    shooter = add_unit(w, make_unit(w, gun_tpl(), 0, 0, (100000, 100000)))
    tgt_unit = add_unit(w, make_unit(w, inf_tpl(), 1, 1, (130000, 100000)))
    tgt_unit.spotted_mask = 1
    return w, shooter, tgt_unit


# ── 记录式 RNG 桩（只录取 chance_bp 实参；不触 PCG32 通道——链路确定性锚）──

class _RecHit:
    def __init__(self):
        self.bps = []

    def chance_bp(self, bp):
        self.bps.append(bp)
        return True


class _RecScatter:
    def sym(self, n):
        return 0


class _RecRng:
    def __init__(self):
        self.hit_ch = _RecHit()

    def hit(self):
        return self.hit_ch

    def scatter(self):
        return _RecScatter()


class TestMoraleAccFactor(unittest.TestCase):
    """B4:149 moraleFactor 按态乘区（受压×0.7/钉住×0.3）——D023「×士气惩罚」项。"""

    def test_constants_pin(self):
        # 表 pin（低置信占位待定标：B4:149 字面值；断箭瞄准时间×2/×3 杠杆未采）
        self.assertEqual((CONFIG.morale_acc_factor_sup_bp,
                          CONFIG.morale_acc_factor_pin_bp), (7000, 3000))

    def test_factor_by_state(self):
        w = make_world(3)
        u = add_unit(w, make_unit(w, gun_tpl(), 0, 0, (0, 0)))
        for morale, expect in [(MoraleState.STABLE, 10000),
                               (MoraleState.SUPPRESSED, 7000),
                               (MoraleState.PINNED, 3000),
                               (MoraleState.ROUTED, 0)]:   # 防御值（⑨ 门已拦）
            u.morale = morale
            self.assertEqual(morale_acc_factor_bp(u, CONFIG), expect, morale)

    def test_fire_direct_acc_chain_multiplier(self):
        # acc 链组合值锚（非书写序锚——整数乘除对操作数顺序不敏感，本组取值下
        # morale 乘区插位前/后不可判别，插位留痕在 tick.fire_direct acc_bp 注释）：
        # base × aim_factor(元素级连续) × morale_acc(单位级态) 的按态组合值与
        # 状态映射；sup=50 → aim_factor=7000：STABLE 7000 / SUPPRESSED 4900 / PINNED 2100
        for morale, expect in [(MoraleState.STABLE, 7000),
                               (MoraleState.SUPPRESSED, 4900),
                               (MoraleState.PINNED, 2100)]:
            w, shooter, tgt_unit = mk_pair(5)
            shooter.morale = morale                        # 直设真槽（链路隔离）
            shooter.elements[0].suppression = 50
            rec = _RecRng()
            w.rng = rec
            ws = shooter.elements[0].weapon_states[0]
            fire_direct(w, shooter.elements[0], ws, tgt_unit.elements[0], CONFIG)
            self.assertEqual(rec.hit_ch.bps, [expect], morale)
            self.assertEqual(ws.state, WState.RELOADING)   # 发射流程照常走完

    def test_suppressed_pinned_still_fire_permitted(self):
        # 受压/钉住=乘区承载非禁射（D014「命中/性能下降」≠禁射；仅溃逃禁射⑨）
        for morale in (MoraleState.STABLE, MoraleState.SUPPRESSED,
                       MoraleState.PINNED):
            w, shooter, tgt_unit = mk_pair(7)
            shooter.morale = morale
            ws = shooter.elements[0].weapon_states[0]
            self.assertTrue(fire_permitted(w, shooter, shooter.elements[0],
                                           ws, CONFIG), morale)


class TestRoutedFireBan(unittest.TestCase):
    """fire_permitted ⑨（PB-55 溃逃禁射）：D014「向后方失控移动」——溃逃不作战。"""

    def test_fire_permitted_routed_false(self):
        w, shooter, tgt_unit = mk_pair(9)
        shooter.morale = MoraleState.ROUTED
        ws = shooter.elements[0].weapon_states[0]
        self.assertFalse(fire_permitted(w, shooter, shooter.elements[0], ws,
                                        CONFIG))

    def test_world_tick_no_new_aiming_while_routed(self):
        # 索敌门：READY + 靶 spotted + 射程内——ROUTED 期间不开新 AIMING、零弹丸
        w, shooter, tgt_unit = mk_pair(11)
        shooter.morale = MoraleState.ROUTED
        shooter.routed_until = w.tick + 300
        for _ in range(3):
            world_tick(w, CONFIG)
        ws = shooter.elements[0].weapon_states[0]
        self.assertIs(ws.state, WState.READY)              # 未开瞄（⑨ 索敌门拦）
        self.assertEqual(ws.ammo_left, ws.template.ammo_base)
        self.assertEqual(w.projectiles, [])

    def test_inflight_aiming_discarded_at_expiry_no_ammo(self):
        # 出口复核双拦（⑦⑧ 同款）：在途 AIMING 到期 → fire_permitted 复核 False
        # → 转 READY 不耗弹不发射
        w, shooter, tgt_unit = mk_pair(13)
        ws = shooter.elements[0].weapon_states[0]
        ws.state = WState.AIMING
        ws.timer = 1
        ws.target = tgt_unit.elements[0]
        shooter.morale = MoraleState.ROUTED
        shooter.routed_until = w.tick + 300
        ammo_before = ws.ammo_left
        world_tick(w, CONFIG)                              # timer 归零 → finish_aim
        self.assertIs(ws.state, WState.READY)              # ⑨ 复核拦发射
        self.assertEqual(ws.ammo_left, ammo_before)        # 不耗弹
        self.assertEqual(w.projectiles, [])

    def test_fire_resumes_after_rally(self):
        # 重整回 SUPPRESSED 后恢复开火（禁射=溃逃期专属；SUPPRESSED 走乘区）
        w, shooter, tgt_unit = mk_pair(15)
        shooter.morale = MoraleState.ROUTED
        shooter.routed_until = w.tick + 2
        for _ in range(3):
            world_tick(w, CONFIG)
        self.assertIsNot(shooter.morale, MoraleState.ROUTED)
        ws = shooter.elements[0].weapon_states[0]
        self.assertTrue(fire_permitted(w, shooter, shooter.elements[0], ws,
                                       CONFIG))


class TestSprintThresholdCrossing(unittest.TestCase):
    """PB-49 冲刺破压 × morale 迁移交叉验证（开跑减压制是否足以跨阈值降档）。"""

    def setUp(self):
        self.w = make_world(17)
        tpl = inf_tpl()
        self.u = add_unit(self.w, make_unit(self.w, tpl, 0, 0, (500000, 400000)))
        self.e = self.u.elements[0]

    def _state_after_sprint(self, sup):
        self.e.suppression = sup
        system_morale(self.w, CONFIG)
        before = self.u.morale
        cmd_sprint(self.w, self.u)
        system_morale(self.w, CONFIG)
        return before, self.u.morale, self.e.suppression

    def test_sprint_suppressed_to_stable(self):
        # 60（SUPPRESSED）→×5000//10000→ 30（<40 → STABLE）：跨受压档降档成立
        before, after, sup = self._state_after_sprint(60)
        self.assertIs(before, MoraleState.SUPPRESSED)
        self.assertEqual(sup, 30)
        self.assertIs(after, MoraleState.STABLE)

    def test_sprint_two_tier_drop_pinned_to_stable(self):
        # 79（PINNED）→ 39（<40）：一跳跨受压+钉住两档直落 STABLE（整数地板效应）
        before, after, sup = self._state_after_sprint(79)
        self.assertIs(before, MoraleState.PINNED)
        self.assertEqual(sup, 39)
        self.assertIs(after, MoraleState.STABLE)

    def test_sprint_cannot_rescue_routed(self):
        # ROUTED 期冲刺拒令（PB-54 失控门族）：压制不减半、不脱离溃逃
        self.e.suppression = 100
        system_morale(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.ROUTED)
        cmd_sprint(self.w, self.u)
        self.assertEqual(self.e.suppression, 100)
        self.assertIs(self.u.morale, MoraleState.ROUTED)


class TestUnitThresholdOverride(unittest.TestCase):
    """D027:174 卡级士气阈值三级回退（template>0 覆盖，0=回退 cfg 缺省）。"""

    def setUp(self):
        self.w = make_world(19)

    def _mk(self, **over):
        tpl = gun_tpl(template_id=962, **over)
        return add_unit(self.w, make_unit(self.w, tpl, 0, 0, (0, 0)))

    def _eval(self, u, sup):
        u.elements[0].suppression = sup
        system_morale(self.w, CONFIG)
        return u.morale

    def test_all_three_overridden(self):
        # 覆盖 60/80/95：55=STABLE（cfg 40 会判 SUPPRESSED——覆盖生效锚）、
        # 60=SUPPRESSED、79=SUPPRESSED、80=PINNED、94=PINNED、95=ROUTED
        u = self._mk(morale_sup_th=60, morale_pin_th=80, morale_rout_th=95)
        for sup, expect in [(55, MoraleState.STABLE), (60, MoraleState.SUPPRESSED),
                            (79, MoraleState.SUPPRESSED), (80, MoraleState.PINNED),
                            (94, MoraleState.PINNED), (95, MoraleState.ROUTED)]:
            self.assertIs(self._eval(u, sup), expect, sup)

    def test_partial_override_single_tier(self):
        # 仅溃逃档覆盖 120（>压制封顶 100=永不溃逃差异化位）：100=PINNED 非 ROUTED；
        # 受压/钉住档仍走 cfg 40/70
        u = self._mk(morale_rout_th=120)
        self.assertIs(self._eval(u, 100), MoraleState.PINNED)
        self.assertIs(self._eval(u, 70), MoraleState.PINNED)
        self.assertIs(self._eval(u, 40), MoraleState.SUPPRESSED)

    def test_zero_sentinel_falls_back_to_cfg(self):
        u = self._mk(morale_sup_th=0, morale_pin_th=0, morale_rout_th=0)
        for sup, expect in [(39, MoraleState.STABLE), (40, MoraleState.SUPPRESSED),
                            (70, MoraleState.PINNED), (100, MoraleState.ROUTED)]:
            self.assertIs(self._eval(u, sup), expect, sup)

    def test_template_slots_defaults(self):
        # 直构模板缺省=0（回退哨兵）——dataclass 默认值锚
        tpl = gun_tpl()
        self.assertEqual((tpl.morale_sup_th, tpl.morale_pin_th,
                          tpl.morale_rout_th), (0, 0, 0))

    def test_effective_threshold_monotonic_guard(self):
        # 运行期防御断言（2026-10-04 评审遗留⑤）：card_schema 构建期只拦双双侧
        # 显式的错序对（0 哨兵跨列不判）——单侧显式+单侧回退 cfg 的非单调组合在
        # system_morale 拼出有效阈值后抛错（elif 阶梯下非单调=存在不可达档）
        # 合法：双双侧显式严格递增（60/80/95）正常判态
        u = self._mk(morale_sup_th=60, morale_pin_th=80, morale_rout_th=95)
        self.assertIs(self._eval(u, 80), MoraleState.PINNED)
        # 非法：单侧回退拼出非单调——各破一对（sup≥pin ×2 / pin≥rout ×2）。
        # 每组换新 world（复核 2026-10-05：共用 world 时 system_morale 按插入序
        # 遍历全体单位，第 1 组的非法单位会替后组先抛错——后组未被因果验证）
        for over in ({"morale_sup_th": 80},    # 有效 (80,70,100)：sup≥pin，受压档不可达
                     {"morale_pin_th": 35},    # 有效 (40,35,100)：pin≤sup，受压档不可达
                     {"morale_pin_th": 120},   # 有效 (40,120,100)：pin≥rout，钉住档不可达
                     {"morale_rout_th": 50}):  # 有效 (40,70,50)：rout 阶梯先判，钉住档不可达
            with self.subTest(over=over):
                self.setUp()                  # fresh world：隔离前组残留单位
                with self.assertRaises(ValueError, msg=str(over)):
                    self._eval(self._mk(**over), 0)


class _Pipe:
    """最小三表数据集（CSV 文本——管线端到端载体；模板取自 test_card_pipeline 范式）。"""

    @staticmethod
    def cards_csv(morale: str) -> str:
        base = {c: "" for c in bc.CARDS_COLUMNS}
        base.update(dict(
            card_key="SU_TEST", template_id="196", name="测试卡", faction="SOVIET",
            category="ARMOR", cost="50", pool="MAIN", optics_ground_cm="20000",
            stealth_base="5", speed_tier="3", movement_class="TRACK",
        ))
        base.update(dict(zip(("morale_sup_th", "morale_pin_th", "morale_rout_th"),
                             morale)))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(bc.CARDS_COLUMNS),
                           lineterminator="\n")
        w.writeheader()
        w.writerow(base)
        return buf.getvalue()

    @staticmethod
    def elements_csv() -> str:
        base = {c: "" for c in bc.ELEMENTS_COLUMNS}
        base.update(dict(card_key="SU_TEST", element_key="E_TEST", count="1",
                         element_type="SQUAD", unit_type="INFANTRY", hp_max="10"))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(bc.ELEMENTS_COLUMNS),
                           lineterminator="\n")
        w.writeheader()
        w.writerow(base)
        return buf.getvalue()

    @staticmethod
    def weapons_csv() -> str:
        base = {c: "" for c in bc.WEAPONS_COLUMNS}
        base.update(dict(weapon_key="W_TEST", element_key="E_TEST", name="炮",
                         damage_type="KE", max_range_cm="50000"))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(bc.WEAPONS_COLUMNS),
                           lineterminator="\n")
        w.writeheader()
        w.writerow(base)
        return buf.getvalue()

    @classmethod
    def build(cls, morale: str):
        tmp = tempfile.TemporaryDirectory()
        data = Path(tmp.name)
        (data / "ground_cards.csv").write_text(cls.cards_csv(morale),
                                               encoding="utf-8-sig")
        (data / "ground_elements.csv").write_text(cls.elements_csv(),
                                                  encoding="utf-8-sig")
        (data / "ground_weapons.csv").write_text(cls.weapons_csv(),
                                                 encoding="utf-8-sig")
        out = data / "gen"
        bc.build_all(data, out)
        return tmp, out / bc.LIBRARY_JSON_NAME


class TestMoraleColumnsPipeline(unittest.TestCase):
    """PB-52 五步先例管线端到端：CSV 列→schema 1.3→JSON→UnitTemplate→system_morale。"""

    def test_csv_override_lands_in_template_and_morale(self):
        tmp, lib_path = _Pipe.build(("60", "80", "95"))
        try:
            doc = json.loads(lib_path.read_text(encoding="utf-8"))
            self.assertEqual(doc["schema_version"], cs.SCHEMA_VERSION)  # minor 演进锁当前值（PB-55 1.3→航空入库 1.4）
            self.assertEqual(doc["cards"][0]["morale_sup_th"], 60)
            self.assertEqual(doc["cards"][0]["morale_pin_th"], 80)
            self.assertEqual(doc["cards"][0]["morale_rout_th"], 95)
            rec = cl.load_library(lib_path)["SU_TEST"]
            tpl = rec.unit_template
            self.assertEqual((tpl.morale_sup_th, tpl.morale_pin_th,
                              tpl.morale_rout_th), (60, 80, 95))
            w = make_world(21)
            u = add_unit(w, make_unit(w, tpl, 0, 0, (0, 0)))
            u.elements[0].suppression = 55
            system_morale(w, CONFIG)
            self.assertIs(u.morale, MoraleState.STABLE)        # 覆盖档 60 生效
            u.elements[0].suppression = 80
            system_morale(w, CONFIG)
            self.assertIs(u.morale, MoraleState.PINNED)
        finally:
            tmp.cleanup()

    def test_csv_empty_columns_fallback(self):
        # 空串=默认值哨兵（0）→ 回退 cfg 缺省
        tmp, lib_path = _Pipe.build(("", "", ""))
        try:
            rec = cl.load_library(lib_path)["SU_TEST"]
            self.assertEqual((rec.unit_template.morale_sup_th,
                              rec.unit_template.morale_pin_th,
                              rec.unit_template.morale_rout_th), (0, 0, 0))
        finally:
            tmp.cleanup()

    def test_schema_rejects_non_increasing_explicit(self):
        # 构建期拦错序三档（显式设定值间须严格递增；0=回退哨兵的对不校验）
        for bad in (("80", "60", ""), ("", "50", "50"), ("40", "", "30")):
            with self.assertRaises(ValueError, msg=bad):     # BuildError/ValidationError
                _Pipe.build(bad)[1]

    def test_schema_accepts_partial_explicit_pairs(self):
        # 单档/双档显式（其余 0 回退）合法——rout_th>100 永不溃逃位
        tmp, lib_path = _Pipe.build(("", "", "120"))
        try:
            self.assertEqual(
                cl.load_library(lib_path)["SU_TEST"].unit_template.morale_rout_th,
                120)
        finally:
            tmp.cleanup()

    def test_repo_data_all_cards_fallback_zero(self):
        # 现役 10 卡三列全空=0（回退 cfg 40/70/100）——数值定标归数值章节，不冒充
        lib = cl.load_library(REPO_ROOT / "data" / "gen" / "cards_ground.v1.json")
        for key, rec in lib.items():
            self.assertEqual((rec.unit_template.morale_sup_th,
                              rec.unit_template.morale_pin_th,
                              rec.unit_template.morale_rout_th), (0, 0, 0), key)

    def test_schema_model_fields_and_version_gate(self):
        self.assertIn("morale_sup_th", cs.UnitCardModel.model_fields)
        self.assertIn("morale_pin_th", cs.UnitCardModel.model_fields)
        self.assertIn("morale_rout_th", cs.UnitCardModel.model_fields)
        self.assertEqual(len(cs.UnitCardModel.model_fields), 39)  # 36→39（PB-55 +3）
        self.assertEqual(cs.SCHEMA_VERSION, "1.6")  # minor 演进锁当前值（终审修复块
        # 1.5→1.6 武器行 +crit_guaranteed 步兵轻 AT 必暴击位——manual.txt:339-341）
        self.assertEqual(cs.SUPPORTED_CARD_SCHEMA, {1: 6})
        self.assertTrue(cs.schema_version_supported("1.2"))   # 旧版本仍受支持
        self.assertFalse(cs.schema_version_supported("1.7"))  # 上界 1.6


if __name__ == "__main__":
    unittest.main()
