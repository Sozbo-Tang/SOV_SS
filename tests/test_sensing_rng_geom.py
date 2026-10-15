"""测试：侦察公式、PCG32 确定性、整型几何。"""
import unittest

from sovs.sim.geom import (angle_diff, dist_cm, facing_of, octant_deg,
                           round_div, step_toward)
from sovs.sim.rng import PCG32, Channels
from sovs.sim.sensing import (detection_range_cm, effective_stealth_x10,
                              keep_range_cm)
from sovs.sim.tables import CONFIG
from sovs.sim.types import (ElementInstance, ElementTemplate, UnitInstance,
                            UnitTemplate, Facing, MovementClass, UnitFlag,
                            UnitType)


def make_unit(stealth=6, optics=1400, moving=False, category=1, flags=0):
    et = ElementTemplate(element_type=2, unit_type=UnitType.INFANTRY, hp_max=10)
    ut = UnitTemplate(template_id=1, name="t", category=category, cost=50,
                      element_templates=(et,), optics_ground_cm=optics,
                      stealth_base=stealth, speed_tier=3,
                      movement_class=MovementClass.FOOT, flags=flags)
    u = UnitInstance(id=1, team=0, template=ut, pos=(0, 0))
    e = ElementInstance(id=1, unit=u, template=et, pos=(0, 0), hp_current=10)
    u.elements.append(e)
    if moving:
        u.move_path = [(100000, 0)]
    return u


class TestRngDeterminism(unittest.TestCase):
    def test_same_seed_same_sequence(self):
        a = PCG32(42, 0)
        b = PCG32(42, 0)
        self.assertEqual([a.next() for _ in range(100)], [b.next() for _ in range(100)])

    def test_channels_independent(self):
        c1 = Channels(7)
        c2 = Channels(7)
        self.assertEqual(c1.hit().next(), c2.hit().next())
        # 消耗 HIT 通道不影响 SCATTER
        c1.hit().next()
        self.assertEqual(c1.scatter().next(), c2.scatter().next())

    def test_chance_bp_bounds(self):
        r = PCG32(1)
        self.assertTrue(r.chance_bp(10000))   # 必真
        self.assertFalse(r.chance_bp(0))      # 必假


class TestGeom(unittest.TestCase):
    def test_dist(self):
        self.assertEqual(dist_cm((0, 0), (300, 400)), 500)

    def test_angle_diff(self):
        self.assertEqual(angle_diff(350, 10), -20)
        self.assertEqual(angle_diff(10, 350), 20)

    def test_facing_front_side_rear(self):
        self.assertIs(facing_of(0, 30), Facing.FRONT)
        self.assertIs(facing_of(0, 90), Facing.SIDE)
        self.assertIs(facing_of(0, 180), Facing.REAR)

    def test_octant(self):
        self.assertEqual(octant_deg(0, 100), 0)
        self.assertEqual(octant_deg(100, 0), 90)
        self.assertEqual(octant_deg(100, 100), 45)

    def test_round_div(self):
        # §T 字面式 (2n+d)//(2d)（v1.7 GAP-15：向 +∞ 半舍入）
        self.assertEqual(round_div(5, 2), 3)
        self.assertEqual(round_div(-5, 2), -2)
        self.assertEqual(round_div(-1, 2), 0)
        self.assertEqual(round_div(4, 2), 2)

    def test_step_toward(self):
        p, arrived = step_toward((0, 0), (300, 400), 500)
        self.assertTrue(arrived)
        self.assertEqual(p, (300, 400))
        p, arrived = step_toward((0, 0), (3000, 4000), 250)
        self.assertFalse(arrived)
        self.assertEqual(dist_cm((0, 0), p), 250)


class TestSensing(unittest.TestCase):
    def test_base_detection(self):
        obs = make_unit(optics=1400, category=1)
        tgt = make_unit(stealth=5)  # 因子 10000 → 全距离
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt), 1400)

    def test_moving_halves(self):
        obs = make_unit(optics=1400)
        obs.move_path = [(1, 0)]  # moving
        tgt = make_unit(stealth=5)
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt), 700)

    def test_ambush_halves(self):
        obs = make_unit(optics=1400)
        obs.ambush_active = True
        tgt = make_unit(stealth=5)
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt), 700)

    def test_high_stealth_shrinks(self):
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=10)  # 因子 5000
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt), 1400 * 5000 // 10000)

    def test_forest_attenuation(self):
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=5)
        r = detection_range_cm(CONFIG, obs, tgt, forest_m=3)  # 3 米林
        self.assertEqual(r, 1400 - CONFIG.detect_atten_per_m * 3)

    def test_effective_stealth_cover_add_after_mult(self):
        u = make_unit(stealth=5, moving=True)
        # 移动 ×0.5：(5×10)×5000//10000 = 25；林地 +20 → 45
        self.assertEqual(effective_stealth_x10(CONFIG, u, in_forest=True), 45)

    def test_keep_range_undamped(self):
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=5)
        self.assertEqual(keep_range_cm(CONFIG, obs, tgt), 1400)

    def test_sen_crit_shrinks_detection(self):
        # GAP-22：SEN 暴击消费点——观察窗 MINOR 碎裂视野 ×0.6（1400→840）
        from sovs.sim.types import CritLevel, CritSlot
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=5)
        obs.elements[0].crit[CritSlot.SEN] = CritLevel.MINOR
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt), 1400 * 6000 // 10000)

    def test_target_in_forest_stealth_up(self):
        # GAP-27：目标林内 +2 档——隐蔽 7 蹲林 → 有效隐蔽 90（查表 idx 9 = 6500bp；
        # 未蹲林 70 → idx 7 = 9000bp。注：审查文档 GAP-27 行文"9 档 8000bp"为笔误，表值以 tables 为准）
        # 2026-10-14 探测增量块（basics:239）：林内另吃掩体减半乘区 → 910×5000//10000=455
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=7)
        self.assertEqual(effective_stealth_x10(CONFIG, tgt, in_forest=True), 90)
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt, tgt_in_forest=True),
                         1400 * CONFIG.stealth_factor_bp[9] // 10000
                         * CONFIG.cover_detect_mult_bp // 10000)
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt, tgt_in_forest=False),
                         1400 * CONFIG.stealth_factor_bp[7] // 10000)


class TestCoverAndMarked(unittest.TestCase):
    """探测增量块 2026-10-14（basics:239 掩体减半 / basics:245-246 已发现更难隐藏）。

    手推锚：obs optics=1400，tgt stealth=5（未标记 50 → idx5=10000 → 基线 1400）。
    掩体减半在隐蔽因子乘区之后、穿林烟衰减之前；marked 隐蔽乘区在表查之前。"""

    def test_constants_pinned(self):
        # 钉值锚（同 TestManualSilentPlaceholders 纪律）：改值=有意推翻定标，先改登记面
        self.assertEqual(CONFIG.cover_detect_mult_bp, 5000)
        self.assertEqual(CONFIG.marked_stealth_mult_bp, 5000)

    def test_cover_forest_halves(self):
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=5)
        # 林内：eff 70 → idx7=9000 → 1260；掩体减半 → 630
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt, tgt_in_forest=True),
                         1400 * 9000 // 10000 * 5000 // 10000)

    def test_cover_garrison_halves(self):
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=5, flags=UnitFlag.CAN_GARRISON)
        tgt.elements[0].garrison_in = 7
        # 驻楼：eff 80 → idx8=8000 → 1120；掩体减半 → 560
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt),
                         1400 * 8000 // 10000 * 5000 // 10000)

    def test_cover_forest_plus_garrison(self):
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=5, flags=UnitFlag.CAN_GARRISON)
        tgt.elements[0].garrison_in = 7
        # 林内+驻楼：eff 100 钳顶 → idx10=5000 → 700；减半 → 350
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt, tgt_in_forest=True),
                         1400 * 5000 // 10000 * 5000 // 10000)

    def test_marked_stealth_penalty(self):
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=5)
        # 上一帧被标记：隐蔽 50×5000//10000=25 → idx2=12000 → 1680（隐蔽减半经
        # 档位表非线性放大——表距 10000→12000bp，非字面 ×2）
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt, tgt_marked=True),
                         1400 * 12000 // 10000)

    def test_unmarked_uncovered_unchanged(self):
        obs = make_unit(optics=1400)
        tgt = make_unit(stealth=5)
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt), 1400)


if __name__ == "__main__":
    unittest.main()
