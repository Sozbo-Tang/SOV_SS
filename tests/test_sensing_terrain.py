"""感知接线块测试（2026-10-07——PB-53 留待项②收口/GAP-27/§2.12「森林只喂 sensing
两侧」实装）：烟幕与森林对感知的实效通道。

覆盖面（锚点全部手推写死+python 复算核对，不自证）：
  - 纯几何锚：smoke_m_between（线段×圆弦长——全径/离线/相切/端点夹逼/线后圆/
    双烟区求和/零长线段/r=0）、forest_m_between（tile 步进采样——逐格计数×
    tile_cm//100、空集/同点/不足一步）、in_forest_at（落格判定）；
  - 通道装配：terrain_sensing_channels 在 lean/stub 世界（terrain None/空集）
    森林两通道 None（sensing None→0/False 恒等分支=既有场景逐位不变）、烟通道
    恒为读 world.smoke_zones 的活闭包；
  - system_sensing 整链：穿烟探测距离缩（r−=detect_atten_per_m×smoke_m 手推
    31000）+烟区 ttl 尽恢复（world_tick 生命周期：tick5/10 拍仍遮、tick15 恢复）；
  - 森林穿行衰减整链（6 林格=150m×150=22500 → r 17500<30000 隐蔽，空林对照
    可见）+逐 tile 150/m 公式锚；
  - GAP-27 目标林内 +2 隐蔽档整链（stealth 7 林内 eff 90→6500bp：远 30000 隐/
    近 22000 可见——路径衰减与林内加成双计的两侧锚）；
  - FOREST_WALK_SILENT 林中静默豁免首次整链（原 in_forest 恒 False=死分支，
    接线后激活：普通移动者林内 eff 45→38250≥35000 可见 vs 静默移动者 eff 70→
    32250<35000 隐蔽；林外无豁免 48000 可见）；
  - 自卫烟幕遮蔽实效整链（cmd_smoke→system_timers 落烟→system_sensing 探测
    降→ttl 尽恢复，PB-53「自卫烟幕遮蔽实效」闭环）；
  - 校射视线通道（point_in_friendly_vision 喂 smoke_m_fn：烟上视线 40000−9000
    =31000<35000 不可见、无烟恢复）——fire_at 调用点同通道（穿烟校射阻断锚
    另落 tests/test_ground_combat.py TestFireMission）。

零掷骰：全链不触碰任何 PCG32 通道（几何函数纯整数——math.isqrt 精确开方）。"""
import unittest

from sovs.sim.pathfind import TerrainLayer
from sovs.sim.sensing import (detection_range_cm, forest_m_between,
                              in_forest_at, smoke_m_between, system_sensing,
                              terrain_sensing_channels, point_in_friendly_vision)
from sovs.sim.tables import CONFIG, BalanceConfig
from sovs.sim.tick import (add_unit, cmd_smoke, make_unit, make_world,
                           world_tick)
from sovs.sim.types import (ElementType, ElementTemplate, MovementClass,
                            SmokeZone, UnitFlag, UnitTemplate, UnitType)

TILE = 2500   # 示范图瓦片边长（map_demo_2km tile_cm 同值）


def _mk(world, team, pos, *, optics=40000, stealth=5, flags=0, moving_to=None):
    """合成单元素单位（test_sensing_rng_geom.make_unit 同款最小面+世界注册）。"""
    et = ElementTemplate(element_type=2, unit_type=UnitType.INFANTRY, hp_max=10)
    ut = UnitTemplate(template_id=531, name="probe", category=1, cost=10,
                      element_templates=(et,), optics_ground_cm=optics,
                      stealth_base=stealth, speed_tier=3,
                      movement_class=MovementClass.FOOT, flags=flags)
    u = add_unit(world, make_unit(world, ut, team, 0, pos))
    if moving_to is not None:
        u.move_path = [moving_to]     # moving()=True（直接 system_sensing 不位移）
    return u


def _forest_world(seed, forest_tiles, tile_cm=TILE):
    """挂空瓦片层+森林旁挂集的世界（apply_map 挂图后同构：terrain.tile_cm 达）。"""
    w = make_world(seed)
    w.terrain = TerrainLayer(tile_cm=tile_cm)
    w.forest_tiles = frozenset(forest_tiles)
    return w


def _sense(w, cfg=CONFIG):
    """按 world_tick ③ 同款装配喂三通道后扫描（接线面单点=terrain_sensing_channels）。"""
    ffn, sfn, ifn = terrain_sensing_channels(w)
    system_sensing(cfg, w, forest_m_fn=ffn, smoke_m_fn=sfn, in_forest_fn=ifn)


def _zone(cx, cy, r=3000, ttl=600):
    return SmokeZone(center=(cx, cy), ttl_ticks=ttl, radius_cm=r)


class TestGeometryAnchors(unittest.TestCase):
    """纯几何函数手推锚（python 复算核对 2026-10-07，逐位与注释一致）。"""

    def test_smoke_chord_full_diameter(self):
        # 线过圆心：弦=直径 6000cm → 60m（自卫烟幕 r=cfg.smoke_radius_cm=3000 同径）
        self.assertEqual(smoke_m_between([_zone(17500, 0)], (0, 0), (35000, 0)), 60)

    def test_smoke_off_line_and_tangent(self):
        # 垂距 3100>r=3000 → 0；相切（垂距==r，边界含等号跳过）→ 0
        self.assertEqual(smoke_m_between([_zone(17500, 3100)], (0, 0), (35000, 0)), 0)
        self.assertEqual(smoke_m_between([_zone(17500, 3000)], (0, 0), (35000, 0)), 0)

    def test_smoke_clipped_at_segment_ends(self):
        # 圆心在线段延长线上：区间 [9000,15000] 夹逼 [0,10000] → 1000cm=10m
        self.assertEqual(smoke_m_between([_zone(12000, 0)], (0, 0), (10000, 0)), 10)
        # 圆心在线段起点后方：区间 [-5000,1000] 夹逼 [0,1000] → 10m
        self.assertEqual(smoke_m_between([_zone(-2000, 0)], (0, 0), (10000, 0)), 10)

    def test_smoke_multiple_zones_sum(self):
        # 双烟区弦长累计：6000+4000=10000cm → 100m（先累计后 //100）
        self.assertEqual(smoke_m_between([_zone(17500, 0), _zone(30000, 0, 2000)],
                                         (0, 0), (35000, 0)), 100)

    def test_smoke_degenerate_cases(self):
        self.assertEqual(smoke_m_between([_zone(0, 0)], (5, 5), (5, 5)), 0)   # 零长线段
        self.assertEqual(smoke_m_between([_zone(17500, 0, 0)], (0, 0), (35000, 0)), 0)  # r=0

    def test_forest_tile_stepping(self):
        # n=5 采样 2500..12500 → 落格 (1,0)/(2,0) 命中 → 2×2500//100=50m
        self.assertEqual(forest_m_between(frozenset({(1, 0), (2, 0)}), TILE,
                                          (0, 0), (12500, 0)), 50)
        # 6 连续林格 (5..10,0)：采样 12 点（2500..30000）命中 6 → 150m
        self.assertEqual(forest_m_between(frozenset({(i, 0) for i in range(5, 11)}),
                                          TILE, (0, 0), (30000, 0)), 150)
        # 单林格在终点：(0,0)→(30000,0) 采样含 30000 → 命中 (12,0) → 25m
        self.assertEqual(forest_m_between(frozenset({(12, 0)}), TILE,
                                          (0, 0), (30000, 0)), 25)

    def test_forest_degenerate_cases(self):
        self.assertEqual(forest_m_between(frozenset(), TILE, (0, 0), (12500, 0)), 0)
        self.assertEqual(forest_m_between(frozenset({(1, 0)}), TILE, (3000, 0), (3000, 0)), 0)
        # 不足一步（同格内短段）：n=0 → 0（目标自身林内走 in_forest 通道不双算）
        self.assertEqual(forest_m_between(frozenset({(1, 0)}), TILE,
                                          (2600, 0), (4000, 0)), 0)

    def test_in_forest_at(self):
        tiles = frozenset({(2, 3)})
        self.assertTrue(in_forest_at(tiles, TILE, (5000, 7500)))
        self.assertFalse(in_forest_at(tiles, TILE, (4999, 7500)))
        self.assertFalse(in_forest_at(frozenset(), TILE, (5000, 7500)))


class TestChannelAssembly(unittest.TestCase):
    def test_stub_world_forest_channels_none(self):
        # lean/stub 场景（terrain=None/空集）：森林两通道 None（None→0/False 恒等
        # 分支=既有场景逐位不变）；烟通道恒为活闭包
        w = make_world(1)
        ffn, sfn, ifn = terrain_sensing_channels(w)
        self.assertIsNone(ffn)
        self.assertIsNone(ifn)
        self.assertEqual(sfn((0, 0), (35000, 0)), 0)          # 空表自然 0
        w.smoke_zones.append(_zone(17500, 0))                 # 运行时落烟即生效
        self.assertEqual(sfn((0, 0), (35000, 0)), 60)

    def test_forest_world_channels_live(self):
        w = _forest_world(2, {(12, 0)})
        ffn, sfn, ifn = terrain_sensing_channels(w)
        self.assertIsNotNone(ffn)
        self.assertIsNotNone(ifn)
        self.assertEqual(ffn((0, 0), (30000, 0)), 25)
        self.assertTrue(ifn((30000, 0)))
        self.assertFalse(ifn((0, 0)))


class TestSmokeBlocksSensing(unittest.TestCase):
    """穿烟探测距离缩 + ttl 尽恢复（system_sensing 整链——观察者 (0,0) 光学
    40000/目标 stealth 5（idx5 10000bp）→ 基线 r=40000；线中点烟区弦 60m×
    detect_atten_per_m=150 → r'=31000）。"""

    def test_detection_range_formula_anchor(self):
        # 公式锚：r −= 150×(forest_m+smoke_m)（sensing.py 既有式——通道喂入后可达）
        w = make_world(3)
        obs = _mk(w, 0, (0, 0))
        tgt = _mk(w, 1, (35000, 0))
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt, smoke_m=60), 31000)
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt, forest_m=25), 36250)  # 逐 tile 150/m

    def test_smoke_blocks_then_ttl_recovery(self):
        # 手挂烟区 ttl=10：tick5/10 拍扫描仍遮（tick10 拍 ttl 已归零但尾部才过滤
        # ——system_timers ① 先于 ③，烟区当拍仍在表）；tail(tick10) 过滤后
        # tick15 拍恢复可见
        w = make_world(4)
        obs = _mk(w, 0, (0, 0))
        tgt = _mk(w, 1, (35000, 0))
        w.smoke_zones.append(_zone(17500, 0, ttl=10))
        for _ in range(5):
            world_tick(w)
        self.assertEqual(w.tick, 5)
        self.assertEqual(tgt.spotted_mask, 0)                 # 31000<35000 遮蔽中
        for _ in range(5):
            world_tick(w)
        self.assertEqual(w.tick, 10)
        self.assertEqual(tgt.spotted_mask, 0)                 # 末拍仍在表=仍遮
        for _ in range(5):
            world_tick(w)
        self.assertEqual(w.tick, 15)
        self.assertEqual(tgt.spotted_mask, 0b1)               # ttl 尽恢复（队0 位）
        self.assertEqual(w.smoke_zones, [])

    def test_no_smoke_control_spots(self):
        w = make_world(5)
        _mk(w, 0, (0, 0))
        tgt = _mk(w, 1, (35000, 0))
        for _ in range(5):
            world_tick(w)
        self.assertEqual(tgt.spotted_mask, 0b1)               # 基线 40000≥35000


class TestForestBlocksSensing(unittest.TestCase):
    """森林穿行衰减整链：6 连续林格 (5..10,0) → forest_m=150 → r=40000−22500
    =17500<30000 隐蔽；空林对照可见。"""

    def test_forest_path_attenuation_chain(self):
        w = _forest_world(6, {(i, 0) for i in range(5, 11)})
        _mk(w, 0, (0, 0))
        tgt = _mk(w, 1, (30000, 0))
        _sense(w)
        self.assertEqual(tgt.spotted_mask, 0)                 # 17500<30000

    def test_empty_forest_control_spots(self):
        w = _forest_world(7, set())
        _mk(w, 0, (0, 0))
        tgt = _mk(w, 1, (30000, 0))
        _sense(w)
        self.assertEqual(tgt.spotted_mask, 0b1)               # 空集→通道 None→40000


class TestTargetInForestStealth(unittest.TestCase):
    """GAP-27 目标林内 +2 档整链（forest_stealth_add_x10=20）：stealth 7 林内
    eff 90（idx9 6500bp）→ 40000×6500//10000=26000，再减路径穿林 25m×150=3750
    → 22250——路径衰减与林内加成双计的两侧锚（远 30000 隐/近 22000 可见；
    同世界两目标路径分别命中 (8,0)/(12,0) 与 (8,0)）。"""

    def test_in_forest_plus_two_chain(self):
        w = _forest_world(8, {(8, 0), (12, 0)})
        _mk(w, 0, (0, 0))
        near = _mk(w, 1, (22000, 0), stealth=7)
        far = _mk(w, 1, (30000, 0), stealth=7)
        _sense(w)
        self.assertEqual(near.spotted_mask, 0b1)              # 22250≥22000 可见
        self.assertEqual(far.spotted_mask, 0)                 # 18500<30000 隐蔽

    def test_open_ground_control_spots_both(self):
        w = _forest_world(9, set())
        _mk(w, 0, (0, 0))
        near = _mk(w, 1, (22000, 0), stealth=7)
        far = _mk(w, 1, (30000, 0), stealth=7)
        _sense(w)
        # 旷野：eff 70（idx7 9000bp）→ 36000 两目标均可见
        self.assertEqual((near.spotted_mask, far.spotted_mask), (0b1, 0b1))


class TestForestWalkSilentChain(unittest.TestCase):
    """FOREST_WALK_SILENT 林中静默豁免首次整链（sensing.py 移动乘区分支原
    in_forest 恒 False=死分支，接线后激活；forest_walk_silent_mult_bp=20000
    ×2 抵回移动惩罚 5000）。目标 stealth 5 移动中、林格 (14,0)、观察距离 35000：
      普通移动者林内 eff 45（idx4 10500bp）→ 42000−3750=38250 ≥35000 可见；
      静默移动者林内 eff 70（idx7 9000bp）→ 36000−3750=32250 <35000 隐蔽；
      静默移动者林外 eff 25（idx2 12000bp）→ 48000 ≥35000 可见（豁免仅林内）。"""

    def test_silent_walker_concealed_in_forest(self):
        w = _forest_world(10, {(14, 0)})
        _mk(w, 0, (0, 0))
        tgt = _mk(w, 1, (35000, 0), flags=UnitFlag.FOREST_WALK_SILENT,
                  moving_to=(999999, 0))
        _sense(w)
        self.assertEqual(tgt.spotted_mask, 0)                 # 32250<35000

    def test_normal_walker_spotted_in_forest(self):
        w = _forest_world(11, {(14, 0)})
        _mk(w, 0, (0, 0))
        tgt = _mk(w, 1, (35000, 0), moving_to=(999999, 0))
        _sense(w)
        self.assertEqual(tgt.spotted_mask, 0b1)               # 38250≥35000

    def test_silent_walker_spotted_in_open(self):
        w = _forest_world(12, set())
        _mk(w, 0, (0, 0))
        tgt = _mk(w, 1, (35000, 0), flags=UnitFlag.FOREST_WALK_SILENT,
                  moving_to=(999999, 0))
        _sense(w)
        self.assertEqual(tgt.spotted_mask, 0b1)               # 48000≥35000（无豁免）


class TestSelfSmokeConcealmentChain(unittest.TestCase):
    """自卫烟幕遮蔽实效整链（PB-53② 收口闭环）：cmd_smoke 受令（delay=0）→
    world_tick tick1 system_timers 以元素位置为心落烟（r=3000/ttl=600）→
    tick5 拍扫描：烟区圆心=目标位——视线段只穿**半**烟区（区间夹逼于线段末点，
    30m×150=4500）→ r'=35500<36000 不可见 → ttl 尽（tick601 尾部过滤）→
    tick605 拍恢复可见。控制组（不发烟）tick5 即可见（基线 40000≥36000）。"""

    def _vehicle_tpl(self):
        return UnitTemplate(
            template_id=598, name="smoke target", category=2, cost=50,
            element_templates=(ElementTemplate(
                element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                hp_max=10, self_smoke_charges=1),),
            optics_ground_cm=5000, stealth_base=5, speed_tier=2,
            movement_class=MovementClass.TRACK)

    def _setup(self, seed):
        cfg = BalanceConfig(self_smoke_cooldown_ticks=0,
                            self_smoke_delay_ticks=0)
        w = make_world(seed)
        _mk(w, 0, (0, 0))                                    # 观察者光学 40000
        veh = add_unit(w, make_unit(w, self._vehicle_tpl(), 1, 0, (36000, 0)))
        return w, cfg, veh

    def test_self_smoke_blocks_detection_until_ttl(self):
        w, cfg, veh = self._setup(13)
        self.assertTrue(cmd_smoke(w, veh.elements[0], (0, 0), cfg))   # point 不消费
        for _ in range(5):
            world_tick(w, cfg)
        self.assertEqual(w.tick, 5)
        self.assertEqual(len(w.smoke_zones), 1)                       # tick1 落烟
        z = w.smoke_zones[0]
        self.assertEqual((z.center, z.radius_cm), ((36000, 0), 3000))  # 落点车锚定
        self.assertEqual(veh.spotted_mask, 0)                         # 35500<36000
        for _ in range(595):
            world_tick(w, cfg)                                         # tick6..600
        self.assertEqual(w.tick, 600)
        self.assertEqual(veh.spotted_mask, 0)                         # 末拍仍遮
        for _ in range(5):
            world_tick(w, cfg)                                         # tick601 过滤/605 恢复
        self.assertEqual(w.tick, 605)
        self.assertEqual(w.smoke_zones, [])
        self.assertEqual(veh.spotted_mask, 0b1)                       # ttl 尽恢复

    def test_no_smoke_control_spots_at_first_scan(self):
        w, cfg, veh = self._setup(14)
        for _ in range(5):
            world_tick(w, cfg)
        self.assertEqual(veh.spotted_mask, 0b1)                       # 基线 40000≥36000


class TestCalibrationVisionChannel(unittest.TestCase):
    """校射视线通道（fire_at 内 point_in_friendly_vision 同装配喂两 fn）：点目标
    (35000,0)、观察者 (0,0) 光学 40000×档位中值 idx5 10000bp=40000——无烟
    40000≥35000 可见；线中点烟区 60m → 31000<35000 不可见。"""

    def test_vision_blocked_by_smoke_and_restored(self):
        w = make_world(15)
        _mk(w, 0, (0, 0))
        ffn, sfn, _ = terrain_sensing_channels(w)
        pt = (35000, 0)
        self.assertTrue(point_in_friendly_vision(
            CONFIG, w, 0, pt, forest_m_fn=ffn, smoke_m_fn=sfn))
        w.smoke_zones.append(_zone(17500, 0))
        self.assertFalse(point_in_friendly_vision(
            CONFIG, w, 0, pt, forest_m_fn=ffn, smoke_m_fn=sfn))
        w.smoke_zones.clear()
        self.assertTrue(point_in_friendly_vision(
            CONFIG, w, 0, pt, forest_m_fn=ffn, smoke_m_fn=sfn))


if __name__ == "__main__":
    unittest.main()
