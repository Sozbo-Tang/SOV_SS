"""断箭设定数值落地测试（2026-10-04 设定数值块；docs/断箭移动机制映射_v1.md
§三 gapFills / §四 conflicts + §二 N10/N12 对齐锚）：
- 类级地形 bp 四值行为锚（N10/GAP-07：FOOT 8000/WHEEL 5000/TRACK 7000/HORSE 9000
  ——与断箭实测轮式 ~50%/履带 ~70% 同向，GAP-07 已核）；
- reverse_speed_bp 数据 pin（N12/MV-B-13：轮 2500/履带 3000 落断箭实测倒/前比
  22~50% 区间下沿；速度乘区消费者=§2.3 增量②随速度链块落地——本块只 pin 表值，
  不测未落地行为）；
- gapFill 占位 pin（sprint_cooldown_ticks=600：社区 60s 低置信、官方仅 recharge
  定性——冷却门是否建模待发起人拍板，未接线；water_speed_bp=5000：两栖≈类级
  越野一半，条件性条目随 MV-B-02 改B 生效，未接线）——零消费者常数仅锚表值
  防漂移，不冒充行为；
- 映射冲突3 裁决 B（默认裁决可推翻）：移动×感知三乘区出表后 consumer 真读
  cfg——cfg 覆盖即改变行为（stealth_move_mult_bp/forest_walk_silent_mult_bp/
  move_vision_mult_bp，默认值位级不变——5000 ≡ //2 等价性穷举锚）；
- 疾跑加速/道路取 max/重伤减速既有行为锚在
  test_movement.py（test_sprint_plus_one_tier/test_road_takes_max/
  test_crippled_threshold_replaces_mob〔原 test_mob_minor_halves——MOB 消费
  已随 GAP-14 拆除，2026-10-06 速度链块改写为重伤阈值版〕——本块复核不重复）；
- PB-52 单位级地形数值（2026-10-04 拍板纳入——断箭 N10/映射 §五.6；推翻 MV-B-01
  defer 的类级系数口径，改「单位级覆盖、类级缺省回退」；水域仍随 MV-B-02 延期）：
  野三级回退（瓦片注入>单位级>类级）/路下限单位级覆盖（契约⑦ max 形态不动）/
  倒车 bp 求值函数（门4 资格+未来 §2.3 增量② 乘区同读）+门4 单位级开口活行为。
"""
import unittest
from dataclasses import replace

from sovs.sim.movement import move_speed_cm_tick, reverse_speed_bp
from sovs.sim.sensing import detection_range_cm, effective_stealth_x10
from sovs.sim.tables import CONFIG
from sovs.sim.tick import MoveCmd
from sovs.sim.types import (ElementInstance, ElementTemplate, MovementClass,
                            MoveMode, UnitFlag, UnitInstance, UnitTemplate,
                            UnitType)


def mk_unit(cls=MovementClass.TRACK, tier=4, *, stealth=5, optics=1400,
            moving=False, flags=UnitFlag(0), terrain_ov=0, reverse_ov=0,
            road_ov=0):
    et = ElementTemplate(element_type=2, unit_type=UnitType.INFANTRY, hp_max=10)
    ut = UnitTemplate(template_id=1, name="t", category=1, cost=50,
                      element_templates=(et,), optics_ground_cm=optics,
                      stealth_base=stealth, speed_tier=tier,
                      movement_class=cls, flags=flags,
                      terrain_speed_override_bp=terrain_ov,
                      reverse_speed_override_bp=reverse_ov,
                      road_bonus_override_cm=road_ov)
    u = UnitInstance(id=1, team=0, template=ut, pos=(0, 0))
    e = ElementInstance(id=1, unit=u, template=et, pos=(0, 0), hp_current=10)
    u.elements.append(e)
    if moving:
        u.move_path = [(100000, 0)]
    return u


# ── N10：类级 terrain_speed_bp 四值（行为可见——move_speed 消费）──

class TestTerrainClassDefaults(unittest.TestCase):
    def test_four_class_defaults_via_move_speed(self):
        # 档×类级 bp（映射 §二 N10 / GAP-07 已核——断箭实测同向）：
        # FOOT 8000 / WHEEL 5000 / TRACK 7000 / HORSE 9000
        for cls, tier, expect in (
                (MovementClass.FOOT, 1, 25 * 8000 // 10000),    # =20
                (MovementClass.WHEEL, 4, 100 * 5000 // 10000),  # =50
                (MovementClass.TRACK, 4, 100 * 7000 // 10000),  # =70
                (MovementClass.HORSE, 2, 45 * 9000 // 10000)):  # =40
            u = mk_unit(cls=cls, tier=tier)
            self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), expect,
                             "%s tier%d" % (cls.name, tier))

    def test_terrain_speed_bp_table_pins(self):
        for cls, bp in ((MovementClass.FOOT, 8000), (MovementClass.WHEEL, 5000),
                        (MovementClass.TRACK, 7000), (MovementClass.HORSE, 9000)):
            self.assertEqual(CONFIG.terrain_speed_bp(cls, None), bp, cls.name)


# ── N12：reverse_speed_bp 表值 pin（速度乘区消费者=速度链块，不测未落地行为）──

class TestReverseSpeedDataPin(unittest.TestCase):
    def test_reverse_tuple_pinned(self):
        # FOOT/WHEEL/TRACK/HORSE 序（§4/MV-B-13）：轮 2500/履带 3000 落断箭实测
        # 倒/前比 22~50% 区间下沿；FOOT/HORSE=0 → issue_move 门 4 拒令（行为锚=
        # test_move_commands.test_gate4_reverse_eligibility）
        self.assertEqual(CONFIG.reverse_speed_bp, (0, 2500, 3000, 0))


# ── §三 gapFills：占位常数 pin（未接线——只锚表值，不冒充行为）──

class TestGapFillPlaceholders(unittest.TestCase):
    def test_sprint_cooldown_placeholder(self):
        # 占位 600（社区"约 60 秒"低置信；官方仅 recharge 定性——核证 v1 N22+
        # §三未确证#6）。冷却门（now<sprint_until+cooldown→REJECT）是否建模待
        # 发起人拍板——当前零消费者（cmd_sprint 无冷却门），落地时不改 sprint_until
        # 语义与契约⑧速度式
        self.assertEqual(CONFIG.sprint_cooldown_ticks, 600)

    def test_water_speed_placeholder(self):
        # 占位 5000（两栖水上瓦片注入值=类级越野 bp×此值//10000——断箭步兵水上
        # 9/越野 18 折算 ≈50%；两栖载具水上数值未公布=未确证#10）。条件性条目仅随
        # MV-B-02 改B 生效（MovementClass 扩枚举/两栖旗标——契约②）；当前零消费者
        self.assertEqual(CONFIG.water_speed_bp, 5000)
        # 占位算式自证（示例推导，非行为）：轮式水上 5000×5000//10000=2500
        self.assertEqual(CONFIG.terrain_speed_bp(MovementClass.WHEEL)
                         * CONFIG.water_speed_bp // 10000, 2500)


# ── 映射冲突3 裁决 B：三乘区出表后 consumer 真读 cfg ──

class TestMoveSenseMultipliersFromConfig(unittest.TestCase):
    def test_stealth_move_mult_bp_override(self):
        # 默认：移动隐蔽 ×5000bp（5×10×5000//10000=25）；出表后改 cfg 即改行为
        u = mk_unit(stealth=5, moving=True)
        self.assertEqual(effective_stealth_x10(CONFIG, u), 25)
        cfg2 = replace(CONFIG, stealth_move_mult_bp=10000)
        self.assertEqual(effective_stealth_x10(cfg2, u), 50)   # 无惩罚

    def test_forest_walk_silent_mult_bp_override(self):
        # 默认：静默行军林中 ×20000bp 抵回移动惩罚（m 回 10000 → 50；林地加成
        # 后置 +20 → 70）；改 cfg=10000 不抵回（m 停 5000 → 25+20=45）
        u = mk_unit(stealth=5, moving=True,
                    flags=UnitFlag.FOREST_WALK_SILENT)
        self.assertEqual(effective_stealth_x10(CONFIG, u, in_forest=True), 70)
        cfg2 = replace(CONFIG, forest_walk_silent_mult_bp=10000)
        self.assertEqual(effective_stealth_x10(cfg2, u, in_forest=True), 45)

    def test_move_vision_mult_bp_override_and_halving_equivalence(self):
        obs = mk_unit(optics=1400, moving=True)
        tgt = mk_unit(stealth=5)              # 因子 10000 → 全距离
        # 默认 ≡ //2（1400//2=700）——r×5000//10000 与 r//2 位级一致
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt), 700)
        cfg2 = replace(CONFIG, move_vision_mult_bp=10000)
        self.assertEqual(detection_range_cm(cfg2, obs, tgt), 1400)  # 无惩罚
        for r in range(0, 5000):              # 等价性穷举（非负整数域）
            self.assertEqual(r * 5000 // 10000, r // 2, r)

    def test_no_move_vision_penalty_flag_exemption(self):
        # 豁免旗（D066 侦察车族前提）：移动观察者不吃视野减半
        obs = mk_unit(optics=1400, moving=True,
                      flags=UnitFlag.NO_MOVE_VISION_PENALTY)
        tgt = mk_unit(stealth=5)
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt), 1400)


# ── PB-52：单位级地形数值（单位级覆盖→类级缺省回退；断箭 N10/映射 §五.6）──

class _StubWorld:
    """issue_move 门4 测试用最小 world（find_path stub=直线直填——AMB-8 同口径）。"""

    def find_path(self, frm, to, movement_class, prefer_road):
        return [to]


class TestUnitLevelTerrainOverrides(unittest.TestCase):
    """2026-10-04 拍板落地（推翻 MV-B-01 defer）：野=三级回退（瓦片>单位级>类级）、
    路=下限单位级覆盖（契约⑦ max 形态不动）、倒=求值函数单一口径（门4+未来乘区）。"""

    def test_terrain_override_effective_via_move_speed(self):
        # 覆盖生效：TRACK tier4 类级 7000→70；单位级 6500 → 100×6500//10000=65
        # WHEEL tier4 类级 5000→50；单位级 6000 → 60（数据示例 SU_T3485=6500 同式）
        u = mk_unit(cls=MovementClass.TRACK, tier=4, terrain_ov=6500)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 65)
        u = mk_unit(cls=MovementClass.WHEEL, tier=4, terrain_ov=6000)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 60)

    def test_terrain_empty_falls_back_to_class(self):
        # 空值回退：terrain_ov=0 → 类级缺省逐位保持（FOOT 8000/TRACK 7000）
        u = mk_unit(cls=MovementClass.FOOT, tier=1)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 20)   # 25×8000//10000
        u = mk_unit(cls=MovementClass.TRACK, tier=4)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 70)   # 100×7000//10000

    def test_terrain_three_level_resolution_pinned(self):
        # tables.terrain_speed_bp 三级回退单点裁决：瓦片注入>单位级>类级
        # （GAP-19 瓦片优先语义保持——地形层在场时按瓦片值权威）
        self.assertEqual(CONFIG.terrain_speed_bp(MovementClass.TRACK), 7000)
        self.assertEqual(CONFIG.terrain_speed_bp(MovementClass.TRACK, None, 6500), 6500)
        self.assertEqual(CONFIG.terrain_speed_bp(MovementClass.TRACK, 3000, 6500), 3000)

    def test_tile_injection_beats_unit_override(self):
        # move_speed 消费链同序：terrain_bp=3000 瓦片注入压过单位级 6500 → 30
        u = mk_unit(cls=MovementClass.TRACK, tier=4, terrain_ov=6500)
        self.assertEqual(
            move_speed_cm_tick(CONFIG, u, 0, terrain_bp=3000), 30)

    def test_road_override_floor(self):
        # 路下限单位级覆盖（契约⑦ max 形态不动、仅下限常数可覆盖）：
        # TRACK tier4+野 6500 → v=65；road_ov=80 → max(65,80)=80；
        # road_ov=50（低于 v）→ 65 不动；road_ov=0 → 回退类级 170
        u = mk_unit(cls=MovementClass.TRACK, tier=4, terrain_ov=6500, road_ov=80)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0, on_road=True), 80)
        u = mk_unit(cls=MovementClass.TRACK, tier=4, terrain_ov=6500, road_ov=50)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0, on_road=True), 65)
        u = mk_unit(cls=MovementClass.TRACK, tier=4, terrain_ov=6500)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0, on_road=True), 170)
        # FOOT 恒不吃路（冻结谓词不因覆盖列改变）：road_ov 再高也无道路档
        u = mk_unit(cls=MovementClass.FOOT, tier=1, road_ov=999)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0, on_road=True), 20)

    def test_reverse_bp_resolution(self):
        # 倒车 bp 求值函数：单位级>0 → 覆盖；0 → 类级缺省（FOOT/HORSE 类级恒 0）
        for cls, ov, expect in (
                (MovementClass.FOOT, 0, 0), (MovementClass.FOOT, 2000, 2000),
                (MovementClass.WHEEL, 0, 2500), (MovementClass.WHEEL, 4000, 4000),
                (MovementClass.TRACK, 0, 3000), (MovementClass.TRACK, 2500, 2500),
                (MovementClass.HORSE, 0, 0)):
            u = mk_unit(cls=cls, reverse_ov=ov)
            self.assertEqual(reverse_speed_bp(CONFIG, u.template), expect,
                             "%s ov=%d" % (cls.name, ov))

    def test_gate4_reverse_unit_level_live(self):
        # 门4 活行为（AMB-9 资格门读单位级求值）：FOOT 类级 0 → 拒令；
        # 单位级覆盖 2000 → 显式开口（1944 语境差异化史实承载位，现役数据未用）
        from sovs.sim.movement import issue_move
        w = _StubWorld()
        u = mk_unit(cls=MovementClass.FOOT, reverse_ov=0)
        self.assertFalse(issue_move(w, CONFIG, MoveCmd(
            unit=u, path=[(7000, 0)], mode=MoveMode.REVERSE)))
        self.assertEqual(u.move_mode, MoveMode.NORMAL)
        u = mk_unit(cls=MovementClass.FOOT, reverse_ov=2000)
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(
            unit=u, path=[(7000, 0)], mode=MoveMode.REVERSE)))
        self.assertEqual(u.move_mode, MoveMode.REVERSE)
        # 注：REVERSE 速度乘区消费者（§2.3 增量②）随速度链块落地——门4 与乘区
        # 同读 reverse_speed_bp 求值函数，乘区接线后单位级值自动生效（不冒装）


if __name__ == "__main__":
    unittest.main()
