"""航空锚点测试：AIR_UNITS_PSEUDOCODE_IMPL_v1.1 官方锚点逐一验证（纯函数层）。

覆盖：§T DIR8/PERP8 几何（GAP-03 重建）、§F1 冷却式（D015/B-04 梯度）、
§F3 散布/精度/走廊（R-22/R-23/D026/B-09 斯图卡锚点）、§F4 缠斗概率（R-20/GAP-25 钳制）、
§F5 侦察标记链（R-23/B-11/B-15）、§F6 空投散布/信标（R-21/契约⑤/B-16）、
§D.3 AirShooterView（契约⑥/GAP-17）、§D.1 entry_tier（AMB-03）、AIR 通道独立。
"""
import unittest

from sovs.sim.air import (DIR8, DIR_NORM, PERP8, airdrop_beacon_mult,
                          airdrop_scatter_cm, air_shooter_view, bomb_scatter_major_cm,
                          dir_index, dogfight_kill_prob_bp, entry_tier,
                          in_strafe_corridor, is_aircraft_alive,
                          nearest_friendly_beacon, point_segment_dist_cm,
                          recon_mark_prob_bp, recon_radius_cm,
                          recovery_cooldown_ticks, scale, strafe_acc_bp,
                          tail_prob_bp, downed_cooldown_ticks)
from sovs.sim.combat import squad_hp_factor_bp
from sovs.sim.geom import octant_deg
from sovs.sim.rng import Channels
from sovs.sim.tables import CONFIG
from sovs.sim.types import AltTier, UnitType


class TestDir8Geometry(unittest.TestCase):
    """§T DIR8 重建（GAP-03）：全圆覆盖 / 模长一致 / 索引正确 / 正交。"""

    def test_full_circle_coverage(self):
        # 锚点：x 与 y 分量必须正负全覆盖（v1 表 x 全 ≥0 的半平面缺陷不复存在）
        xs = [v[0] for v in DIR8]
        ys = [v[1] for v in DIR8]
        self.assertTrue(any(x > 0 for x in xs) and any(x < 0 for x in xs))
        self.assertTrue(any(y > 0 for y in ys) and any(y < 0 for y in ys))

    def test_norm_lengths_within_one_percent(self):
        # 锚点：模长² ∈ {49, 50}——7 与 √50≈7.071，各向异性 ≤1%（v1 为 1/√2/√5 三种）
        for v in DIR8:
            self.assertIn(v[0] * v[0] + v[1] * v[1], (49, 50))

    def test_index_matches_octant(self):
        # 锚点：西向 270° → 索引 6 → (-7,0)；北 0° → (0,7)；东 90° → (7,0)；西南 225° → (-5,-5)
        self.assertEqual(octant_deg(-1, 0), 270)
        self.assertEqual(dir_index(-1, 0), 6)
        self.assertEqual(DIR8[dir_index(-1, 0)], (-7, 0))
        self.assertEqual(DIR8[dir_index(0, 1)], (0, 7))
        self.assertEqual(DIR8[dir_index(1, 0)], (7, 0))
        self.assertEqual(DIR8[dir_index(-2, -2)], (-5, -5))  # 225° 西南

    def test_perp_orthogonal(self):
        for u, w in zip(DIR8, PERP8):
            self.assertEqual(u[0] * w[0] + u[1] * w[1], 0)  # 点积=0（旋转 90°）

    def test_scale(self):
        self.assertEqual(scale((7, 0), 100), (100, 0))
        self.assertEqual(scale((5, 5), 70), (50, 50))  # 5×70//7=50


class TestCooldownEconomy(unittest.TestCase):
    """§F1 冷却式（D015：冷却随受损增长；B-04 击落≫返场梯度）。"""

    def test_full_hp_recovery(self):
        # 锚点：满血返场 = base = 600
        self.assertEqual(recovery_cooldown_ticks(CONFIG, 30, 30), 600)

    def test_damaged_recovery_scales(self):
        # 锚点：损 10 HP = 600 + 10×30 = 900
        self.assertEqual(recovery_cooldown_ticks(CONFIG, 30, 20), 900)

    def test_downed_exceeds_worst_recovery(self):
        # 锚点：击落 =（600 + 30×30）×3 = 4500 ≫ 满损返场 1500（AIR-00 梯度）
        self.assertEqual(downed_cooldown_ticks(CONFIG, 30), 4500)
        self.assertGreater(downed_cooldown_ticks(CONFIG, 30),
                           recovery_cooldown_ticks(CONFIG, 30, 0))


class TestBombScatter(unittest.TestCase):
    """§F3 散布乘区链（R-23 高度系数 / D015 速度 / D026 云层 / B-09 俯冲）。"""

    def test_level_bombing_altitude(self):
        # 锚点：中空 ×1.0（1000→1000）；低空 ×0.6；高空 ×1.5（R-23 散布中/小/大）
        self.assertEqual(bomb_scatter_major_cm(CONFIG, 1000, 100, AltTier.MID), 1000)
        self.assertEqual(bomb_scatter_major_cm(CONFIG, 1000, 100, AltTier.LOW), 600)
        self.assertEqual(bomb_scatter_major_cm(CONFIG, 1000, 100, AltTier.HIGH), 1500)

    def test_speed_widens(self):
        # 锚点：两倍基准速散布×2（D015 精度×飞行速度）
        self.assertEqual(bomb_scatter_major_cm(CONFIG, 1000, 200, AltTier.MID), 2000)

    def test_cloud_widens_high_tier(self):
        # 锚点：厚云（cloud=2）中空投弹 ×1.3（D026/GAP-18）
        self.assertEqual(bomb_scatter_major_cm(CONFIG, 1000, 100, AltTier.MID,
                                               cloud_tier=2), 1300)

    def test_stuka_dive_anchor(self):
        # 锚点（卡面承诺）：斯图卡俯冲投弹 = 低空系数 ×0.5 俯冲乘区 = ×0.3 全场最低
        self.assertEqual(bomb_scatter_major_cm(CONFIG, 1000, 100, AltTier.HIGH,
                                               has_dive=True), 300)

    def test_dump_scatter_doubled(self):
        # 锚点：转对空丢弹（应急抛投）散布 ×2（低空：600×2=1200）
        self.assertEqual(bomb_scatter_major_cm(CONFIG, 1000, 100, AltTier.LOW,
                                               dump=True), 1200)


class TestStrafeAndDogfight(unittest.TestCase):
    """§F3 扫射精度/走廊 + §F4 缠斗概率（R-20：战力/机动）。"""

    def test_strafe_acc_altitude(self):
        # 锚点：低空 ×1.3 钳制 10000（R-23 低空扫射精度最高=基础必中）；高空 ×0.7
        self.assertEqual(strafe_acc_bp(CONFIG, 8000, AltTier.LOW), 10000)
        self.assertEqual(strafe_acc_bp(CONFIG, 8000, AltTier.HIGH), 5600)
        self.assertEqual(strafe_acc_bp(CONFIG, 5000, AltTier.LOW), 6500)

    def test_corridor_distance(self):
        # 走廊 = 线段两侧 1500cm：线上点距 0；垂距 1400 在内、1600 在外
        run = ((0, 0), (10000, 0))
        self.assertEqual(point_segment_dist_cm((5000, 0), *run), 0)
        self.assertTrue(in_strafe_corridor((5000, 1400), *run))
        self.assertFalse(in_strafe_corridor((5000, 1600), *run))

    def test_segment_end_clamped(self):
        # 线段外垂足钳到端点
        self.assertEqual(point_segment_dist_cm((-3000, 4000), (0, 0), (0, 10000)), 3000)

    def test_dogfight_kill_prob(self):
        # 锚点：base=3000，攻 10 vs 守(10+5) → 3000×10//15 = 2000bp
        self.assertEqual(dogfight_kill_prob_bp(CONFIG, 10, 10, 5), 2000)
        # 钳制族锚点（GAP-25 根因联立）：atk=99 vs dfn=(1+0) → 297000 → 钳 10000
        self.assertEqual(dogfight_kill_prob_bp(CONFIG, 99, 1, 0), 10000)

    def test_tail_prob_clamped(self):
        # 锚点（GAP-25）：4000×80//10=32000 → 钳制 10000
        self.assertEqual(tail_prob_bp(CONFIG, 80, 10), 10000)
        self.assertEqual(tail_prob_bp(CONFIG, 10, 10), 4000)


class TestReconChain(unittest.TestCase):
    """§F5 侦察标记链（R-23 高度两支 / D015 速度 / D026 云层只削高空）。"""

    def test_radius_altitude_split(self):
        # 锚点（R-23）：低空半径小（×0.6）、高空大（×1.4）
        self.assertEqual(recon_radius_cm(CONFIG, 8000, AltTier.LOW), 4800)
        self.assertEqual(recon_radius_cm(CONFIG, 8000, AltTier.HIGH), 11200)

    def test_cloud_high_only(self):
        # 锚点（B-11）：低云（tier=1）只削高空（×0.6），低空不受云影响
        self.assertEqual(recon_radius_cm(CONFIG, 8000, AltTier.HIGH, cloud_tier=1), 6720)
        self.assertEqual(recon_radius_cm(CONFIG, 8000, AltTier.LOW, cloud_tier=1), 4800)

    def test_mark_prob_speed_and_altitude(self):
        # 锚点：低空 ×1.2 标记高、高空 ×0.6 低（R-23）；Po-2 慢速(≤ref)速度因子=10000
        self.assertEqual(recon_mark_prob_bp(CONFIG, 4000, AltTier.LOW, 100), 4800)
        self.assertEqual(recon_mark_prob_bp(CONFIG, 4000, AltTier.HIGH, 100), 2400)
        # 两倍基准速 → 速度因子 5000（慢速易标/快速难标）
        self.assertEqual(recon_mark_prob_bp(CONFIG, 4000, AltTier.LOW, 200), 2400)


class TestAirdropChain(unittest.TestCase):
    """§F6 空投散布/信标（R-21/D015 高度×速度；契约⑤ ×0.5；B-16 最近吸附）。"""

    def test_scatter_formula(self):
        # 锚点：低空 ×0.8 → 2400；速度 ×2 → 4800
        self.assertEqual(airdrop_scatter_cm(CONFIG, AltTier.LOW, 100), 2400)
        self.assertEqual(airdrop_scatter_cm(CONFIG, AltTier.LOW, 200), 4800)

    def test_beacon_mult_is_frozen_contract(self):
        # 契约⑤冻结值：×5000bp（散布 −50%）
        self.assertEqual(airdrop_beacon_mult(CONFIG), 5000)

    def test_nearest_beacon_within_radius(self):
        class U:
            def __init__(self, team):
                self.team = team

        far, near, enemy = 1, 2, 3                     # 键=unit.id（2026-10-06 键型适配）
        beacons = {far: (0, (9000, 0)), near: (0, (1500, 0)), enemy: (1, (100, 0))}
        drop = (0, 0)
        # 最近己方信标 near@1500 在吸附半径 2500 内 → 生效；far 超半径；敌方不计
        self.assertEqual(nearest_friendly_beacon(beacons, 0, drop), (1500, 0))
        self.assertIsNone(nearest_friendly_beacon(beacons, 1, (50000, 0)))


class TestContracts(unittest.TestCase):
    """契约⑥ AirShooterView / AMB-03 entry_tier / AMB-02 alive 谓词 / AIR 通道。"""

    def test_shooter_view_satisfies_hp_factor(self):
        # GAP-17：适配器使地面冻结 squad_hp_factor_bp 可求值（非步兵恒 10000bp）
        class FakeAircraft:
            hp_current = 17

        view = air_shooter_view(FakeAircraft())
        self.assertIs(view.template.unit_type, UnitType.MECH)
        self.assertEqual(squad_hp_factor_bp(view), 10000)

    def test_entry_tier_derivation(self):
        # AMB-03：MIN(MID, ceiling)——战斗机 HIGH→进场 MID；Po-2 LOW→LOW
        self.assertEqual(entry_tier(AltTier.HIGH), AltTier.MID)
        self.assertEqual(entry_tier(AltTier.LOW), AltTier.LOW)
        self.assertEqual(entry_tier(AltTier.MID), AltTier.MID)

    def test_alive_predicate(self):
        class World:
            aircraft = []

        class A:
            pass

        a = A()
        World.aircraft.append(a)
        self.assertTrue(is_aircraft_alive(a, World()))
        World.aircraft.remove(a)
        self.assertFalse(is_aircraft_alive(a, World()))  # 移出即除名（§D.2）

    def test_air_channel_independent(self):
        # AIR=7 独立通道：与 HIT 通道同种子序列不同（不复用地面序列）
        self.assertEqual(Channels.AIR, 7)
        ch = Channels(1234)
        seq_air = [ch.air().below(10000) for _ in range(8)]
        seq_hit = [ch.hit().below(10000) for _ in range(8)]
        self.assertNotEqual(seq_air, seq_hit)


if __name__ == "__main__":
    unittest.main()
