"""测试：移动速度（档位×地形×道路×拖曳×疾跑×重伤×倒车）——预期值含地形系数。
MOB 暴击两例（test_mob_major_immobilized/test_mob_minor_halves）已随 GAP-14 拆除
改写为重伤阈值版（MOVEMENT v1.2 §9 tests 行；2026-10-06 速度链块）——§2.3 求值
链 v2：编组钳制→疾跑升档→拖曳锁档→地形 bp→倒车乘区→重伤乘区→PINNED→道路 max。
增量⑨/MV-B-22 拖曳随动偏移基向已落地（2026-10-07 PB-60 随批——按 elements[0].
facing 反向恒取车尾正后方，AMB-6 修复；前进锚不变+新增倒车×拖曳车尾侧锚）。"""
import unittest

from dataclasses import replace

from sovs.sim.movement import move_speed_cm_tick, system_move
from sovs.sim.tables import CONFIG
from sovs.sim.types import (CritLevel, CritSlot, DeployState,
                            ElementInstance, ElementTemplate, MovementClass,
                            MoveMode, TowState, UnitInstance, UnitTemplate,
                            UnitType)


def make_tank(speed_tier=4, cls=MovementClass.TRACK, reverse_bp=0):
    et = ElementTemplate(element_type=0, unit_type=UnitType.MECH, hp_max=16)
    ut = UnitTemplate(template_id=1, name="tank", category=2, cost=200,
                      element_templates=(et,), optics_ground_cm=1400,
                      stealth_base=1, speed_tier=speed_tier, movement_class=cls,
                      reverse_speed_override_bp=reverse_bp)
    u = UnitInstance(id=1, team=0, template=ut, pos=(0, 0))
    e = ElementInstance(id=1, unit=u, template=et, pos=(0, 0), hp_current=16)
    u.elements.append(e)
    return u, e


class TestMoveSpeed(unittest.TestCase):
    def test_base_with_terrain(self):
        # 档4=100 × 越野履带 7000‰ = 70
        u, _ = make_tank(speed_tier=4, cls=MovementClass.TRACK)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 70)

    def test_road_takes_max(self):
        # 档2=45 越野 < 道路 170（取 max）
        u, _ = make_tank(speed_tier=2, cls=MovementClass.TRACK)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0, on_road=True), 170)

    def test_sprint_plus_one_tier(self):
        u, _ = make_tank(speed_tier=3, cls=MovementClass.TRACK)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 49)   # 档3=70×0.7
        u.sprint_until = 100  # GAP-18：单位级归口（§D.4#16）
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 50), 70)  # 升档4=100×0.7

    def test_tow_locks_tier1_with_terrain(self):
        u, e = make_tank(speed_tier=5, cls=MovementClass.TRACK)
        e.towed = TowState.TOWED
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 25 * 7000 // 10000)
        e.towed = TowState.TOWING  # v1.5 双态：牵引侧同样锁 1 档
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 25 * 7000 // 10000)

    def test_crippled_threshold_replaces_mob(self):
        # GAP-14 拆除+增量③（2026-10-06 速度链块；原 test_mob_major_immobilized/
        # test_mob_minor_halves 两锚随 §9 tests 行改写为重伤阈值版）：MOB 暴击
        # MAJOR 不再趴窝/MINOR 不再减速（消费面拆除——combat.roll_crit 亦不再
        # 产出 MOB），HP≤25% 单阈值 ×crippled_speed_mult_bp 原位替换（D068：
        # 重伤≠瘫痪，仅减速不减停）；边界含等号——16HP 车 4HP 恰触发（§2.3 边界③）
        u, e = make_tank(speed_tier=4, cls=MovementClass.WHEEL)  # 100×5000=50
        e.crit[CritSlot.MOB] = CritLevel.MAJOR                    # 拆除锚：不再趴窝
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 50)
        e.crit[CritSlot.MOB] = CritLevel.MINOR                    # 拆除锚：不再减速
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 50)
        e.crit.clear()
        e.hp_current = 5      # 5×10000=50000 > 16×2500=40000：不触发
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 50)
        e.hp_current = 4      # 恰 25%：40000 ≤ 40000 触发（等号边界）
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 25)    # 50×5000//10000

    def test_crippled_any_element_slows_unit(self):
        # §2.3 边界④/MV-B-14：ANY 元素重伤 → 全单位减速（排级同速抽象，与拖曳
        # ANY 双态判同构）——满血首元素 + 重伤次元素仍触发
        et = ElementTemplate(element_type=0, unit_type=UnitType.MECH, hp_max=16)
        ut = UnitTemplate(template_id=2, name="plt", category=2, cost=200,
                          element_templates=(et, et), optics_ground_cm=1400,
                          stealth_base=1, speed_tier=4,
                          movement_class=MovementClass.TRACK)
        u = UnitInstance(id=1, team=0, template=ut, pos=(0, 0))
        e1 = ElementInstance(id=1, unit=u, template=et, pos=(0, 0), hp_current=16)
        e2 = ElementInstance(id=2, unit=u, template=et, pos=(0, 0), hp_current=4)
        u.elements.extend((e1, e2))
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 35)    # 70×5000//10000

    def test_reverse_speed_mult(self):
        # §2.3 增量②（锚点验算 §2.3 :221-222）：档4 轮式 50 → ×2500//10000=12；
        # 档2 履带 45×7000//10000=31 → ×3000//10000=9
        u, _ = make_tank(speed_tier=4, cls=MovementClass.WHEEL)
        u.move_mode = MoveMode.REVERSE
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 12)
        t, _ = make_tank(speed_tier=2, cls=MovementClass.TRACK)
        t.move_mode = MoveMode.REVERSE
        self.assertEqual(move_speed_cm_tick(CONFIG, t, 0), 9)

    def test_reverse_unit_override_pb52(self):
        # PB-52 求值函数单位级>类级（增量② 读 movement.reverse_speed_bp——与
        # issue_move 门4 同一求值点）：override 5000 → 50×5000//10000=25
        u, _ = make_tank(speed_tier=4, cls=MovementClass.WHEEL, reverse_bp=5000)
        u.move_mode = MoveMode.REVERSE
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 25)

    def test_reverse_crippled_compose_frozen_order(self):
        # §2.3 求值顺序 v2 冻结：倒车→重伤 串接（整数逐级舍入位级确定）。
        # 〔判别力修复 2026-10-07（D071 全拆块随拆重锚）〕原锚取值组合
        # （50→×2500→12→×5000→6）两序同值 6=对串接次序不具判别力（实测验证：
        # 反序 50×5000//10000=25→25×2500//10000=6 同值——「冻结」断言空转）；
        # 换判别组合：tier2 45×terrain_bp 5200//10000=23 → ×5900//10000=13 →
        # ×2600//10000=3（反序 23×2600//10000=5→5×5900//10000=2——3≠2，
        # 本会话 python 实算双验成立）
        cfg2 = replace(CONFIG, reverse_speed_bp=(0, 5900, 3000, 0),
                       crippled_speed_mult_bp=2600)
        u, e = make_tank(speed_tier=2, cls=MovementClass.WHEEL)
        u.move_mode = MoveMode.REVERSE
        e.hp_current = 4                                          # 4×10000≤16×2500 恰触发
        self.assertEqual(move_speed_cm_tick(cfg2, u, 0, terrain_bp=5200), 3)

    def test_reverse_tow_stack(self):
        # §2.3 边界①：倒车×拖曳叠加——拖曳锁 1 档（硬覆盖钳制）后再乘倒车 bp
        # （牵引车倒车调炮位是真实操作；随动偏移基向=增量⑨ 已随批落地 2026-10-07
        # ——车尾侧取向锚见 test_tow_follow_reverse_keeps_towed_at_rear）
        u, e = make_tank(speed_tier=4, cls=MovementClass.WHEEL)
        e.towed = TowState.TOWING
        u.move_mode = MoveMode.REVERSE
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0),
                         25 * 5000 // 10000 * 2500 // 10000)      # 12→3

    def test_sprint_caps_at_tier5(self):
        u, _ = make_tank(speed_tier=5, cls=MovementClass.TRACK)
        u.sprint_until = 100  # GAP-18：单位级归口
        # 档5=140 × 0.7 = 98（封顶不越档）
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 50), 98)

    def test_terrain_tile_injection(self):
        # GAP-19：瓦片注入接口——注入沼泽 3500‰ 覆盖类级缺省
        u, _ = make_tank(speed_tier=4, cls=MovementClass.TRACK)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0, terrain_bp=3500), 35)


class TestSystemMove(unittest.TestCase):
    def test_moves_to_waypoint(self):
        u, _ = make_tank(speed_tier=5, cls=MovementClass.WHEEL)  # 140×0.5=70/tick
        u.move_path = [(7000, 0)]
        for _ in range(150):
            system_move(CONFIG, u, 0)
            if not u.move_path:
                break
        self.assertEqual(u.pos, (7000, 0))
        self.assertFalse(u.move_path)

    def test_multi_waypoint_single_tick(self):
        # GAP-01：预算按实际距离扣减——98cm/tick，两个各距 40cm 的航点一 tick 走完
        u, _ = make_tank(speed_tier=5, cls=MovementClass.TRACK)  # 140×0.7=98
        u.pos = (4000, 0)
        u.elements[0].pos = (4000, 0)
        u.move_path = [(4040, 0), (4080, 0)]
        system_move(CONFIG, u, 0)
        self.assertEqual(u.pos, (4080, 0))  # 原"扣 1000"实现会停在 (4040,0)
        self.assertFalse(u.move_path)

    def test_facing_kept_on_arrival(self):
        # GAP-30：到达末航点保持末段航向（东=90°），不再重置 0°
        u, _ = make_tank(speed_tier=5, cls=MovementClass.WHEEL)
        u.move_path = [(7000, 0)]
        for _ in range(150):
            system_move(CONFIG, u, 0)
            if not u.move_path:
                break
        self.assertEqual(u.elements[0].facing, 90)

    def test_reverse_facing_locked(self):
        # §2.4 增量④（2026-10-06 速度链块）：三分支求值前 REVERSE 短路——倒车
        # 期间车头朝向不随位移翻转（保持现值；队形循环写同值=无操作）。档5 轮式
        # 70 → 倒车 70×2500//10000=17/tick 西移，facing 维持初始 90°（东）；
        # 对照：NORMAL 模式同向位移朝向翻转为 270°（西）
        u, e = make_tank(speed_tier=5, cls=MovementClass.WHEEL)
        e.facing = 90
        u.move_mode = MoveMode.REVERSE
        u.move_path = [(-700, 0)]
        system_move(CONFIG, u, 0)
        self.assertEqual(u.pos, (-17, 0))
        self.assertEqual(e.facing, 90)          # 倒车不翻转（无本行将=270°）
        u.move_mode = MoveMode.NORMAL
        u.move_path = [(-340, 0)]
        system_move(CONFIG, u, 1)
        self.assertEqual(e.facing, 270)         # 正常机动朝向随位移（对照支）

    def test_garrison_cleared_on_move(self):
        # GAP-02（补-18）：移动令即自动出楼——garrison_in 清、楼位释放
        u, e = make_tank()
        building = type("B", (), {"garrisoned": [e]})()
        e.garrison_in = building
        u.move_path = [(1000, 0)]
        system_move(CONFIG, u, 0)
        self.assertIsNone(e.garrison_in)
        self.assertNotIn(e, building.garrisoned)

    def test_formation_predicate_includes_lead_excludes_mounted(self):
        # GAP-03：§F5 :988-993 谓词——首元素 pos 随基准点更新；车载元素排除
        et = ElementTemplate(element_type=0, unit_type=UnitType.MECH, hp_max=16)
        ut = UnitTemplate(template_id=1, name="plt", category=2, cost=200,
                          element_templates=(et, et), optics_ground_cm=1400,
                          stealth_base=1, speed_tier=4, movement_class=MovementClass.TRACK)
        u = UnitInstance(id=1, team=0, template=ut, pos=(0, 0))
        e1 = ElementInstance(id=1, unit=u, template=et, pos=(999, 999), hp_current=16)
        e2 = ElementInstance(id=2, unit=u, template=et, pos=(888, 888), hp_current=16)
        u.elements.extend((e1, e2))
        u.move_path = [(2000, 0)]
        system_move(CONFIG, u, 0)   # 70cm → pos≈(70,0)
        self.assertEqual(e1.pos, u.pos)   # 首元素不再冻结于出生点
        self.assertEqual(e1.facing, 90)
        self.assertEqual(e2.pos, u.pos)
        # e2 车载：坐标不进队形循环
        carrier = ElementInstance(id=3, unit=u, template=et, pos=(5, 5), hp_current=16)
        e2.mounted_in = carrier
        u.move_path = [(4000, 0)]
        system_move(CONFIG, u, 1)
        self.assertEqual(e2.pos, (5, 5))

    def test_tow_follow_moves_towed_element(self):
        # GAP-14（§F5 :1001-1006）+ AMB-10：拖曳随动——被拖元素跟随于牵引元素后方 300cm、facing 跟随
        truck_u, truck_e = make_tank(speed_tier=2, cls=MovementClass.WHEEL)
        gun_u, gun_e = make_tank(speed_tier=1, cls=MovementClass.FOOT)
        from sovs.sim.types import TowPair
        pair = TowPair(tower_elements=[truck_e], towed_element=gun_e)
        truck_e.towed = TowState.TOWING
        gun_e.towed = TowState.TOWED
        truck_u.move_path = [(450, 0)]  # 拖曳锁 1 档：25×0.5=12/tick（v1.5 双态）
        system_move(CONFIG, truck_u, 0, tow_pairs=[pair])
        self.assertEqual(truck_e.pos[0], 12)
        self.assertEqual(gun_e.pos, (12 - CONFIG.tow_follow_offset_cm, 0))  # 后方偏移，不再同点重叠
        self.assertEqual(gun_e.facing, 90)  # 被拖 facing 跟随牵引朝向
        self.assertEqual(gun_u.pos, truck_e.pos)  # 全被拖单位基准点随动

    def test_tow_follow_reverse_keeps_towed_at_rear(self):
        # §2.3 边界① 增量⑨/MV-B-22（AMB-6 修复；2026-10-07 PB-60 随批落地）：
        # 倒车×拖曳叠加期偏移基向=车体朝向 elements[0].facing 反向（车尾正后方
        # −scale(DIR8[facing//45], off)）——原「本 tick 位移向量反向」归一取偏移，
        # 倒车时位移向量指向车尾、被拖元素反落牵引车车头侧（拖挂点物理上恒在车尾）。
        # 档2 轮式拖曳锁 1 档：25×5000//10000=12 →倒车 ×2500//10000=3/tick 西移；
        # 增量④ facing 维持 90°（东）→被拖元素恒在车尾侧（西）truck_x−300，
        # 无本行修复将落车头侧 truck_x+300
        truck_u, truck_e = make_tank(speed_tier=2, cls=MovementClass.WHEEL)
        gun_u, gun_e = make_tank(speed_tier=1, cls=MovementClass.FOOT)
        from sovs.sim.types import TowPair
        pair = TowPair(tower_elements=[truck_e], towed_element=gun_e)
        truck_e.towed = TowState.TOWING
        gun_e.towed = TowState.TOWED
        truck_e.facing = 90
        truck_u.move_mode = MoveMode.REVERSE
        truck_u.move_path = [(-700, 0)]
        system_move(CONFIG, truck_u, 0, tow_pairs=[pair])
        self.assertEqual(truck_u.pos, (-3, 0))              # 12×2500//10000=3 西移
        self.assertEqual(truck_e.facing, 90)                # 增量④：倒车不翻转
        self.assertEqual(gun_e.pos,
                         (truck_e.pos[0] - CONFIG.tow_follow_offset_cm, 0))  # 车尾侧（西）
        self.assertNotEqual(gun_e.pos[0], truck_e.pos[0] + CONFIG.tow_follow_offset_cm)
        self.assertEqual(gun_e.facing, 90)                  # 被拖 facing 跟随牵引朝向
        self.assertEqual(gun_u.pos, truck_e.pos)            # 全被拖单位基准点随动

    def test_deploying_blocks(self):
        u, _ = make_tank()
        u.deploy_state = DeployState.DEPLOYING
        u.move_path = [(1000, 0)]
        system_move(CONFIG, u, 0)
        self.assertEqual(u.pos, (0, 0))

    def test_move_exits_ambush(self):
        u, _ = make_tank()
        u.ambush_active = True
        u.ambush_shot_bonus = True
        u.move_path = [(1000, 0)]
        system_move(CONFIG, u, 0)
        self.assertFalse(u.ambush_active)
        self.assertFalse(u.ambush_shot_bonus)  # M19：加成随移动清除

    def test_manual_ambush_exit_still_clears_bonus_on_move(self):
        # GAP-28：两独立 IF——手动退出伏击（active=False, bonus=True）后移动仍清首击加成
        u, _ = make_tank()
        u.ambush_active = False
        u.ambush_shot_bonus = True
        u.move_path = [(1000, 0)]
        system_move(CONFIG, u, 0)
        self.assertFalse(u.ambush_shot_bonus)


class TestPinnedAndSprintBreak(unittest.TestCase):
    """2026-10-04 发起人拍板（断箭式，MV-B-03/MV-B-04 双改B——映射档 §四.2 冲突2）。"""

    def test_sprint_halves_suppression_on_start(self):
        # MV-B-04 改B：冲刺开跑拍全体元素压制 ×sprint_suppress_cut_bp（5000=减半）
        from types import SimpleNamespace

        from sovs.sim.tick import cmd_sprint
        u, e = make_tank()
        e.suppression = 80
        w = SimpleNamespace(tick=0)
        cmd_sprint(w, u)
        self.assertEqual(u.sprint_until, CONFIG.sprint_duration_ticks)
        self.assertEqual(e.suppression, 40)              # 80×5000//10000

    def test_pinned_speed_mult_wired_and_dormant(self):
        # MV-B-03 改B：PINNED 可动但减速 50%——判据缝 movement.pinned 已接真槽
        # （PB-54 士气块：读 unit.morale==PINNED）；本测试通过是因新造单位缺省
        # STABLE → pinned() 恒假走全速（「休眠」由缺省态承载，非判据缝恒假）；
        # 「置真验证减半」分支仍有效（临时替换 pinned 后还原——减速链接线本体）
        import sovs.sim.movement as movement
        u, _ = make_tank(speed_tier=4)                   # 档4=100×履带7000‰=70
        self.assertFalse(movement.pinned(u))             # 休眠判据缝
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 70)
        original = movement.pinned
        movement.pinned = lambda unit: True
        try:
            self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 35)   # 70×5000//10000
        finally:
            movement.pinned = original
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 70)       # 还原后零行为差


if __name__ == "__main__":
    unittest.main()
