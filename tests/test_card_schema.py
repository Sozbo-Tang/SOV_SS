"""地面数据卡 schema 测试（card_schema.py——DATA-01 冻结文档 §5 校验规则的镜像）。

任务三类法定用例：
① 合法最小卡通过（卡/元素/武器行三层＋库＋deck 全链）；
② 缺必填字段报错（卡级/元素级/武器级/库级）；
③ 类型错误（含 float 值）报错——StrictInt 拒 1.5 与 1.0（整值 float 同拒）、
   StrictBool 拒 int、str 数值拒（读取器显式 int() 前的字符串不得混入）。

另覆盖 DATA-01 §5 跨字段校验器、§2 版本门（SUPPORTED_CARD_SCHEMA 两分支）、
§8 deck 校验（D032 限份/D011 配额/R-13 子配额/D038 点数/阵营/版本绑定）。

引用：out/card-schema-plan.md §H 测试计划；docs/DATA-01-地面数据卡schema冻结-v1.md。
"""
import unittest

from pydantic import ValidationError

from sovs.sim import card_schema as cs


def weapon(**over) -> dict:
    """最小合法武器行（element_key 默认随元素基准）。"""
    base = dict(weapon_key="W1", element_key="E1", name="机枪", damage_type="KE",
                max_range_cm=3000)
    base.update(over)
    return base


def element(**over) -> dict:
    """最小合法元素（SQUAD/INFANTRY、无甲、无武器）。"""
    base = dict(element_key="E1", count=1, element_type="SQUAD",
                unit_type="INFANTRY", hp_max=8)
    base.update(over)
    return base


def card(**over) -> dict:
    """最小合法卡（苏军步枪排级：步兵/主力池/单元素）。"""
    base = dict(card_key="SU_RIFLE", template_id=101, name="步枪排",
                faction="SOVIET", category="INFANTRY", cost=45, pool="MAIN",
                optics_ground_cm=1400, stealth_base=1, speed_tier=1,
                movement_class="FOOT", elements=[element()])
    base.update(over)
    return base


def mech_element(**over) -> dict:
    base = dict(element_key="EV1", count=1, element_type="VEHICLE",
                unit_type="MECH", hp_max=16,
                armor_ke=dict(front=10, side=8, rear=6, top=3),
                armor_he=dict(front=6, side=4, rear=3, top=2))
    base.update(over)
    return base


def library(**over) -> dict:
    base = dict(schema_version=cs.SCHEMA_VERSION, source_sha256="0" * 64,
                cards=[card()], pending=[])
    base.update(over)
    return base


def deck(**over) -> dict:
    base = dict(schema_version=cs.SCHEMA_VERSION, deck_key="su_min",
                faction="SOVIET",
                cards=[dict(card_key="SU_RIFLE", copies=1)])
    base.update(over)
    return base


class TestValidMinimalCard(unittest.TestCase):
    """① 合法最小卡通过。"""

    def test_minimal_card(self):
        m = cs.UnitCardModel.model_validate(card())
        self.assertEqual(m.card_key, "SU_RIFLE")
        self.assertIsNone(m.per_card_limit)      # None=按类别默认（D032）
        self.assertEqual(m.supply_radius_cm, 8000)  # types.py 冻结默认一致
        self.assertEqual(m.mode_set, ["DIRECT"])
        self.assertEqual(m.tow_tonnage, 0)       # 0.1t 刻度默认 0（不可牵引）

    def test_full_weapon_row_and_mech(self):
        """武器行 29 字段含三子模型＋MECH 元素全分支。"""
        m = cs.UnitCardModel.model_validate(card(
            card_key="SU_T3485", template_id=120, category="ARMOR", cost=100,
            movement_class="TRACK", speed_tier=4, elements=[mech_element(
                weapons=[weapon(
                    weapon_key="W_D85", element_key="EV1", name="D-85T",
                    target_mask=["GROUND"], pen_min=8, pen_max=12, damage=10,
                    salvo=1, ammo_base=5, needs_deployed=False,
                    restricted_profiles=[dict(count=2, pen_bonus=4)],
                    alt_profile=dict(damage=6, blast_radius_cm=1500),
                    self_defense=dict(max_range_cm=2000, accuracy_mult_bp=5000),
                )],
                mounted_armament=["W_D85"],
            )]))
        w = m.elements[0].weapons[0]
        self.assertEqual(w.pen_max, 12)
        self.assertEqual(w.restricted_profiles[0].count, 2)
        self.assertEqual(w.alt_profile.blast_radius_cm, 1500)
        self.assertEqual(w.self_defense.accuracy_mult_bp, 5000)
        self.assertEqual(m.elements[0].armor_ke.front, 10)

    def test_library_and_deck_roundtrip(self):
        lib = cs.CardLibraryModel.model_validate(library())
        dk = cs.DeckModel.model_validate(deck())
        cs.validate_deck(dk, lib)  # 合法即不抛


class TestMissingRequired(unittest.TestCase):
    """② 缺必填字段报错。"""

    def test_card_missing_optics(self):
        payload = card()
        del payload["optics_ground_cm"]
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(payload)

    def test_card_missing_elements(self):
        payload = card()
        del payload["elements"]
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(payload)

    def test_element_missing_hp_max(self):
        e = element()
        del e["hp_max"]
        with self.assertRaises(ValidationError):
            cs.ElementModel.model_validate(e)

    def test_weapon_missing_max_range(self):
        w = weapon()
        del w["max_range_cm"]
        with self.assertRaises(ValidationError):
            cs.WeaponRowModel.model_validate(w)

    def test_library_missing_source_sha256(self):
        payload = library()
        del payload["source_sha256"]
        with self.assertRaises(ValidationError):
            cs.CardLibraryModel.model_validate(payload)


class TestTypeErrors(unittest.TestCase):
    """③ 类型错误（含 float 值）报错——StrictInt/StrictBool 双保险的 pydantic 侧。"""

    def test_float_cost(self):
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(card(cost=1.5))

    def test_float_integral_value_also_rejected(self):
        """整值 float（100.0）同样被拒——StrictInt 无隐式收窄。"""
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(card(cost=100.0))

    def test_float_weapon_pen(self):
        with self.assertRaises(ValidationError):
            cs.WeaponRowModel.model_validate(weapon(pen_max=7.5))

    def test_float_stealth_base(self):
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(card(stealth_base=3.0))

    def test_string_number_rejected(self):
        """str 数值拒（CSV 读取器显式 int() 前的字符串不得混入）。"""
        with self.assertRaises(ValidationError):
            cs.ElementModel.model_validate(element(hp_max="8"))

    def test_int_for_bool_rejected(self):
        with self.assertRaises(ValidationError):
            cs.WeaponRowModel.model_validate(weapon(needs_deployed=1))

    def test_unknown_field_forbidden(self):
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(card(unknown_col=7))


class TestFieldDomainsAndValidators(unittest.TestCase):
    """DATA-01 §5 跨字段校验器与取值域。"""

    def test_pen_max_below_pen_min(self):
        with self.assertRaises(ValidationError):
            cs.WeaponRowModel.model_validate(weapon(pen_min=5, pen_max=3))

    def test_min_range_above_max(self):
        with self.assertRaises(ValidationError):
            cs.WeaponRowModel.model_validate(
                weapon(max_range_cm=3000, min_range_cm=4000))

    def test_mech_requires_armor(self):
        e = mech_element()
        e["armor_ke"] = None
        with self.assertRaises(ValidationError):
            cs.ElementModel.model_validate(e)

    def test_infantry_armor_must_be_null(self):
        with self.assertRaises(ValidationError):
            cs.ElementModel.model_validate(element(
                armor_ke=dict(front=1, side=1, rear=1, top=1)))

    def test_fire_arc_whitelist(self):
        with self.assertRaises(ValidationError):
            cs.ElementModel.model_validate(element(fire_arc_deg=90))

    def test_mounted_armament_dangling_ref(self):
        with self.assertRaises(ValidationError):
            cs.ElementModel.model_validate(
                element(weapons=[weapon()], mounted_armament=["NOPE"]))

    def test_weapon_key_duplicate(self):
        with self.assertRaises(ValidationError):
            cs.ElementModel.model_validate(
                element(weapons=[weapon(), weapon()]))

    def test_weapon_element_key_mismatch(self):
        with self.assertRaises(ValidationError):
            cs.ElementModel.model_validate(element(
                weapons=[weapon(element_key="OTHER")]))

    def test_aura_only_infantry(self):
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(card(
                category="ARMOR", movement_class="TRACK",
                aura=dict(kind="MELEE", bonus_bp=11500, radius_cm=2000)))

    def test_quota_group_only_fire_support(self):
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(card(quota_group="HOWITZER"))

    def test_delivery_requires_reserve_pool(self):
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(card(delivery="LI2", pool="MAIN"))

    def test_card_key_pattern(self):
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(card(card_key="su-rifle"))

    def test_duplicate_flags_token(self):
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(
                card(flags=["CAN_SPRINT", "CAN_SPRINT"]))

    def test_speed_tier_domain(self):
        with self.assertRaises(ValidationError):
            cs.UnitCardModel.model_validate(card(speed_tier=6))

    def test_armor_out_of_scale(self):
        with self.assertRaises(ValidationError):
            cs.ArmorModel.model_validate(dict(front=25, side=8, rear=6, top=3))


class TestLibraryUniquenessAndVersion(unittest.TestCase):
    """DATA-01 §2.2 版本门（两分支）与库级唯一性。"""

    def test_duplicate_card_key(self):
        with self.assertRaises(ValidationError):
            cs.CardLibraryModel.model_validate(library(cards=[card(), card()]))

    def test_duplicate_template_id(self):
        other = card(card_key="SU_OTHER")
        with self.assertRaises(ValidationError):
            cs.CardLibraryModel.model_validate(
                library(cards=[card(), other]))

    def test_version_major_unsupported(self):
        with self.assertRaises(ValidationError):
            cs.CardLibraryModel.model_validate(
                library(schema_version="2.0"))

    def test_version_minor_over_bound(self):
        with self.assertRaises(ValidationError):
            cs.CardLibraryModel.model_validate(
                library(schema_version="1.99"))

    def test_version_helper(self):
        self.assertTrue(cs.schema_version_supported("1.0"))
        self.assertFalse(cs.schema_version_supported("1.99"))
        self.assertFalse(cs.schema_version_supported("2.0"))
        self.assertFalse(cs.schema_version_supported("x.y"))


class TestDeckValidation(unittest.TestCase):
    """DATA-01 §8 deck 校验（构建期规则；运行期 card_loader 同规则复用）。"""

    def test_per_card_limit_class_default_d032(self):
        """per_card_limit=None → 装甲默认 2：2 份过、3 份拒。"""
        armor = card(card_key="SU_T3485", template_id=120, category="ARMOR",
                     movement_class="TRACK", elements=[mech_element()])
        lib = cs.CardLibraryModel.model_validate(library(cards=[armor]))
        ok = cs.DeckModel.model_validate(
            deck(cards=[dict(card_key="SU_T3485", copies=2)]))
        cs.validate_deck(ok, lib)
        bad = cs.DeckModel.model_validate(
            deck(cards=[dict(card_key="SU_T3485", copies=3)]))
        with self.assertRaises(ValueError):
            cs.validate_deck(bad, lib)

    def test_per_card_limit_card_override(self):
        """卡级显式 per_card_limit=1 覆盖类别默认 3：默认下 4 份拒、覆盖后 2 份即拒。"""
        lib = cs.CardLibraryModel.model_validate(library())  # None→步兵默认 3
        dk4 = cs.DeckModel.model_validate(
            deck(cards=[dict(card_key="SU_RIFLE", copies=4)]))
        with self.assertRaises(ValueError):  # 4 > 默认 3（未超 D011 配额 9/点数 4000）
            cs.validate_deck(dk4, lib)
        lib2 = cs.CardLibraryModel.model_validate(library(
            cards=[card(per_card_limit=1)]))
        dk2 = cs.DeckModel.model_validate(
            deck(cards=[dict(card_key="SU_RIFLE", copies=2)]))
        with self.assertRaises(ValueError):  # 覆盖为 1 后 2 份拒
            cs.validate_deck(dk2, lib2)

    def test_category_quota_d011(self):
        """步兵主力默认 ≤9：10 份拒。"""
        lib = cs.CardLibraryModel.model_validate(library())
        dk = cs.DeckModel.model_validate(
            deck(cards=[dict(card_key="SU_RIFLE", copies=10)]))
        with self.assertRaises(ValueError):
            cs.validate_deck(dk, lib)

    def test_fire_support_subquota(self):
        """榴弹炮子配额两池总和 ≤3：4 份拒（未超类别配额 6 也拒）。"""
        guns = [card(card_key=f"SU_H{i}", template_id=130 + i,
                     category="FIRE_SUPPORT", quota_group="HOWITZER", cost=10,
                     elements=[element()])
                for i in range(4)]
        lib = cs.CardLibraryModel.model_validate(library(cards=guns))
        dk = cs.DeckModel.model_validate(deck(cards=[
            dict(card_key=f"SU_H{i}", copies=1) for i in range(4)]))
        with self.assertRaises(ValueError):
            cs.validate_deck(dk, lib)

    def test_points_cap_d038(self):
        """主力点数超 4000 拒（cost=45×89 份=4005；同时卡在步兵配额 9 之下不成立，
        故直接调低类别约束外的小成本多卡：cost=500×8=4000 边界过、加 1 份拒）。"""
        unit = card(card_key="SU_BIG", template_id=150, cost=500,
                    per_card_limit=9)
        lib = cs.CardLibraryModel.model_validate(library(cards=[unit]))
        ok = cs.DeckModel.model_validate(
            deck(cards=[dict(card_key="SU_BIG", copies=8)]))  # 4000=cap
        cs.validate_deck(ok, lib)
        bad = cs.DeckModel.model_validate(
            deck(cards=[dict(card_key="SU_BIG", copies=9)]))  # 4500>4000
        with self.assertRaises(ValueError):
            cs.validate_deck(bad, lib)

    def test_faction_mismatch(self):
        lib = cs.CardLibraryModel.model_validate(library())
        dk = cs.DeckModel.model_validate(deck(faction="GERMAN"))
        with self.assertRaises(ValueError):
            cs.validate_deck(dk, lib)

    def test_dangling_deck_card(self):
        lib = cs.CardLibraryModel.model_validate(library())
        dk = cs.DeckModel.model_validate(
            deck(cards=[dict(card_key="NOPE", copies=1)]))
        with self.assertRaises(ValueError):
            cs.validate_deck(dk, lib)

    def test_deck_library_version_binding(self):
        """三版本绑定：deck 与卡库 schema_version 必须一致（不一致拒）。

        当前支持表 {1:0} 下「两版本都合法但不相等」不可经模型门构造，
        故用 model_construct（绕过校验器）直接造实例测 validate_deck 绑定分支。"""
        lib = cs.CardLibraryModel.model_validate(library())
        dk = cs.DeckModel.model_validate(deck())
        self.assertEqual(dk.schema_version, lib.schema_version)
        cs.validate_deck(dk, lib)
        stale = cs.DeckModel.model_construct(
            **{**deck(), "cards": [cs.DeckEntryModel.model_validate(
                dict(card_key="SU_RIFLE", copies=1))]})
        object.__setattr__(stale, "schema_version", "0.9")  # 绕门注入旧版本
        with self.assertRaises(ValueError):
            cs.validate_deck(stale, lib)

    def test_deck_duplicate_entry_rejected(self):
        with self.assertRaises(ValidationError):
            cs.DeckModel.model_validate(deck(cards=[
                dict(card_key="SU_RIFLE", copies=1),
                dict(card_key="SU_RIFLE", copies=2)]))


class TestTokenIntMap(unittest.TestCase):
    """DATA-01 §2.4：令牌→int 映射与 types.py IntEnum 值一致（JSON int 表示单点）。"""

    def test_values_align_with_types(self):
        from sovs.sim.types import (AltTier, AuraKind, DamageType,
                                    MovementClass, TargetDomain, Trajectory)
        self.assertEqual(cs.TOKEN_VALUE["movement_class"]["TRACK"],
                         int(MovementClass.TRACK))
        self.assertEqual(cs.TOKEN_VALUE["damage_type"]["HE"], int(DamageType.HE))
        self.assertEqual(cs.TOKEN_VALUE["trajectory"]["BALLISTIC"],
                         int(Trajectory.BALLISTIC))
        self.assertEqual(cs.TOKEN_VALUE["aura_kind"]["PRECISION"],
                         int(AuraKind.PRECISION))
        self.assertEqual(cs.TOKEN_VALUE["air_ceiling"]["MID"], int(AltTier.MID))
        self.assertEqual(cs.TOKEN_VALUE["target_mask"]["AIR_HIGH"],
                         int(TargetDomain.AIR_HIGH))
        self.assertEqual(cs.TOKEN_VALUE["category"]["ARMOR"], 2)  # types.py:227


if __name__ == "__main__":
    unittest.main()
