"""锚点测试：KE/HE 穿甲曲线（伪代码 v1.6 §F1 官方锚点逐一验证）。"""
import unittest

from sovs.sim.combat import (damage_mult_permille, penetration_at,
                             squad_hp_factor_bp, aim_factor_bp)
from sovs.sim.tables import CONFIG
from sovs.sim.types import (Armor, DamageType, ElementInstance,
                            ElementTemplate, UnitType, WeaponTemplate)


class TestKineticCurve(unittest.TestCase):
    def test_full_pen_at_equal(self):
        # 锚点：pen == armor → 1000‰（全额）
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.KE, 10, 10), 1000)

    def test_ten_percent_at_half(self):
        # 锚点：pen = ½armor → 100‰
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.KE, 5, 10), 100)

    def test_ricochet_below_half(self):
        # 锚点：pen < ½armor → 跳弹 0
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.KE, 4, 10), 0)
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.KE, 0, 10), 0)

    def test_midpoint_value(self):
        # pen=9, armor=10：(81−40)×1000÷50 = 820‰
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.KE, 9, 10), 820)

    def test_overmatch(self):
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.KE, 20, 10), 1000)


class TestHECurve(unittest.TestCase):
    def test_half_armor_two_hundred(self):
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.HE, 5, 10), 200)

    def test_equal_five_hundred(self):
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.HE, 10, 10), 500)

    def test_double_eight_hundred(self):
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.HE, 20, 10), 800)

    def test_infantry_always_he_curve(self):
        # 对步兵，动能弹也走爆破曲线（官方规则）
        self.assertEqual(damage_mult_permille(UnitType.INFANTRY, DamageType.KE, 5, 10), 200)
        self.assertEqual(damage_mult_permille(UnitType.INFANTRY, DamageType.KE, 10, 10), 500)


class TestSpecialRules(unittest.TestCase):
    def test_unarmored_full_damage(self):
        # 装甲 0（卡车）→ 无甲守卫 → 1000‰，不进除法（B10）
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.KE, 3, 0), 1000)
        self.assertEqual(damage_mult_permille(UnitType.MECH, DamageType.HE, 3, 0), 1000)

    def test_smoke_zero(self):
        self.assertEqual(damage_mult_permille(UnitType.INFANTRY, DamageType.SMOKE, 10, 10), 0)


class TestPenetrationDistance(unittest.TestCase):
    W = WeaponTemplate(name="125mm", damage_type=DamageType.KE,
                       pen_min=4, pen_max=10, max_range_cm=140000)

    def test_point_blank(self):
        self.assertEqual(penetration_at(self.W, 0), 10)

    def test_max_range(self):
        self.assertEqual(penetration_at(self.W, 140000), 4)

    def test_midpoint(self):
        # 半程：10 − 6×0.5 = 7
        self.assertEqual(penetration_at(self.W, 70000), 7)

    def test_he_constant(self):
        w = WeaponTemplate(name="HE", damage_type=DamageType.HE,
                           pen_min=2, pen_max=6, max_range_cm=100000)
        self.assertEqual(penetration_at(w, 0), 6)
        self.assertEqual(penetration_at(w, 100000), 6)


class TestArmorFacing(unittest.TestCase):
    def test_facing_lookup(self):
        a = Armor(front=10, side=6, rear=3, top=2)
        self.assertEqual(a.of(0), 10)   # FRONT
        self.assertEqual(a.of(1), 6)    # SIDE
        self.assertEqual(a.of(2), 3)    # REAR
        self.assertEqual(a.of(3), 2)    # TOP


class TestHitFacingRotatingGate(unittest.TestCase):
    """GAP-08：转向 SIDE 判定仅对 fire_arc<360 生效（方案6 双保险）。"""

    def _elem(self, fire_arc):
        et = ElementTemplate(element_type=0, unit_type=UnitType.MECH, hp_max=16,
                             fire_arc_deg=fire_arc)
        holder = type("U", (), {"elements": []})()
        e = ElementInstance(id=1, unit=holder, template=et, pos=(0, 0), hp_current=16)
        holder.elements.append(e)
        return e

    def test_turret_rotating_still_front(self):
        # 炮塔车（fire_arc=360）rotating 误置位 → 仍按正面（不误判 SIDE）
        from sovs.sim.combat import compute_hit_facing
        from sovs.sim.types import Facing
        e = self._elem(360)
        e.rotating = True
        self.assertIs(compute_hit_facing(e, 30, CONFIG), Facing.FRONT)

    def test_casemate_rotating_side(self):
        from sovs.sim.combat import compute_hit_facing
        from sovs.sim.types import Facing
        e = self._elem(90)
        e.rotating = True
        self.assertIs(compute_hit_facing(e, 90, CONFIG), Facing.SIDE)


class TestModifierMultiplicative(unittest.TestCase):
    """GAP-29：crit × 压制 乘法复合（§F1 :414-419 逐字对齐）。"""

    def _elem(self, slot, level):
        from sovs.sim.types import CritLevel, CritSlot
        et = ElementTemplate(element_type=0, unit_type=UnitType.MECH, hp_max=16)
        holder = type("U", (), {"elements": []})()
        e = ElementInstance(id=1, unit=holder, template=et, pos=(0, 0), hp_current=16)
        holder.elements.append(e)
        if slot is not None:
            e.crit[slot] = level
        return e

    def test_fc_minor_full_sup(self):
        from sovs.sim.combat import aim_factor_bp
        from sovs.sim.types import CritLevel, CritSlot
        e = self._elem(CritSlot.FC, CritLevel.MINOR)
        e.suppression = 100
        # 7500 × (10000−6000) ÷ 10000 = 3000
        self.assertEqual(aim_factor_bp(e, CONFIG), 3000)

    def test_rld_major_full_sup(self):
        from sovs.sim.combat import reload_factor_bp
        from sovs.sim.types import CritLevel, CritSlot
        e = self._elem(CritSlot.RLD, CritLevel.MAJOR)
        e.suppression = 100
        # 16000 × (10000+6000) ÷ 10000 = 25600
        self.assertEqual(reload_factor_bp(e, CONFIG), 25600)

    def test_no_crit_no_sup_neutral(self):
        from sovs.sim.combat import aim_factor_bp, reload_factor_bp
        e = self._elem(None, None)
        self.assertEqual(aim_factor_bp(e, CONFIG), 10000)
        self.assertEqual(reload_factor_bp(e, CONFIG), 10000)


class TestSuppressionFalloff(unittest.TestCase):
    """AMB-01 拍板：衰减跨度 = 2×弹半径（随弹径插值，大口径压制圈大）。"""

    def _world(self):
        from sovs.sim.types import ElementInstance, ElementTemplate
        et = ElementTemplate(element_type=0, unit_type=UnitType.INFANTRY, hp_max=10)
        holder = type("U", (), {"elements": [], "units": []})()
        u = type("Unit", (), {"elements": [], "alive": True})()
        e = ElementInstance(id=1, unit=u, template=et, pos=(0, 0), hp_current=10)
        u.elements.append(e)
        holder.units.append(u)
        return holder, e

    def test_falloff_scales_with_blast_radius(self):
        from sovs.sim.combat import inject_suppression_area
        world, e = self._world()
        inject_suppression_area(world, (0, 0), 3000, 100)  # 30m 弹半径
        self.assertEqual(e.suppression, 100)               # 圆心全额
        # 同距离 2000cm（20m）：大弹径（30m 跨度 60m）仍 7333bp，小弹径（7.5m 跨度 15m）已到底线 2000bp
        world2, e2 = self._world()
        e2.pos = (2000, 0)
        inject_suppression_area(world2, (0, 0), 3000, 100)
        self.assertEqual(e2.suppression, 100 * (10000 - 2000 * 8000 // 6000) // 10000)
        world3, e3 = self._world()
        e3.pos = (2000, 0)
        inject_suppression_area(world3, (0, 0), 750, 100)
        self.assertEqual(e3.suppression, 100 * 2000 // 10000)


if __name__ == "__main__":
    unittest.main()
