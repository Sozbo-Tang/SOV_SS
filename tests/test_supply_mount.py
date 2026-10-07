"""system_supply（§F6 :1308-1341 ⑥ 后勤 R-18/R-19）与 mount_requests_step
（§F6 :1169-1190 ⑦ 上车 R-07）+ needs_resupply（§F2 :442-445）+ stop_tow/载具占用数
+ cmd_mount/cmd_dismount（§F6 :1137-1168/:1131-1136——PB-56 批② 机动链命令块·
上下车，2026-10-06：门序①-⑪ 逐项/分派链/挂载即出楼/㉑A 3班→3车/双形卸载）。

锚点全部手推写死（2026-10-03 拍板一池重量补给：补弹 take=MIN(缺口, 池//每发重量,
2 发/tick)、医疗 heal=MIN(缺口hp, 池//1g)、维修 repair_power/tick、
修满清 crit+解拖、上车 200 tick 倒计时、复核撤销谓词、惰性表 None），不自证；
确定性双跑照 tests/test_integration.py fingerprint 范式（同 seed 两 world 逐 tick
比指纹），全程零掷骰（八通道 PCG32 state 不动——两系统无随机消耗）。"""
import unittest

from sovs.sim.combat import needs_resupply
from sovs.sim.tick import (DismountCmd, MountCmd, add_unit, cmd_dismount,
                           cmd_garrison, cmd_mount, make_unit, make_world,
                           mount_requests_step, pending_mount_count, queue_command,
                           seat_usage, stop_tow, system_supply, world_tick)
from sovs.sim.types import (Building, CritLevel, CritSlot, ElementTemplate,
                            ElementType, Mode, MovementClass, MountRequest,
                            TowPair, TowState, TowStopReason, UnitFlag,
                            UnitTemplate, UnitType, WeaponTemplate, WState)

# ── 合成模板（测试用，不对应真实卡）──
RIFLE = WeaponTemplate(name="RIFLE", damage=1, max_range_cm=10000, ammo_base=10)
RIFLE_SQUAD = ElementTemplate(element_type=ElementType.SQUAD,
                              unit_type=UnitType.INFANTRY, hp_max=10,
                              weapons=(RIFLE,))
INF_TPL = UnitTemplate(                       # 步枪班（补弹/医疗消费端）
    template_id=301, name="rifle squad", category=1, cost=20,
    element_templates=(RIFLE_SQUAD,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)

TRUCK_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                             unit_type=UnitType.MECH, hp_max=10, seats=1)
TRUCK_TPL = UnitTemplate(                     # 补给卡车（supply_radius_cm 默认 8000）
    template_id=302, name="supply truck", category=4, cost=30,
    element_templates=(TRUCK_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=3, movement_class=MovementClass.WHEEL)

TANK_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                            unit_type=UnitType.MECH, hp_max=20)
TANK_TPL = UnitTemplate(                      # 受损坦克（维修消费端）
    template_id=303, name="tank", category=2, cost=100,
    element_templates=(TANK_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=3, movement_class=MovementClass.TRACK)
WRENCH_TPL = UnitTemplate(                    # 维修班（repair_power_hp_per_tick=2）
    template_id=304, name="wrecker", category=4, cost=40,
    element_templates=(TANK_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=2, movement_class=MovementClass.WHEEL,
    repair_power_hp_per_tick=2)

CARRIER_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                               unit_type=UnitType.MECH, hp_max=10, seats=1)
MIXED_TPL = UnitTemplate(                     # 混编卡：班元素 + 载具元素（同卡上车）
    template_id=305, name="grenadier halftrack", category=1, cost=40,
    element_templates=(RIFLE_SQUAD, CARRIER_ELEM), optics_ground_cm=20000,
    stealth_base=5, speed_tier=3, movement_class=MovementClass.TRACK)
TWO_SQUAD_TPL = UnitTemplate(                 # 两班步兵卡（跨卡上车去重载体）
    template_id=306, name="two squads", category=1, cost=40,
    element_templates=(RIFLE_SQUAD, RIFLE_SQUAD), optics_ground_cm=20000,
    stealth_base=5, speed_tier=1, movement_class=MovementClass.FOOT)
BIG_CARRIER_TPL = UnitTemplate(               # seats=2 跨卡载具
    template_id=307, name="big carrier", category=4, cost=50,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=10, seats=2),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.TRACK)
HEAVY_GUN = WeaponTemplate(name="CANNON", damage=5, max_range_cm=30000,
                           ammo_base=10, ammo_weight=30)     # 重弹 30g/发（拍板：按重量计）
HEAVY_TANK_TPL = UnitTemplate(                 # 重炮坦克（重弹补弹消费端）
    template_id=308, name="heavy tank", category=2, cost=100,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=20,
                                       weapons=(HEAVY_GUN,)),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.TRACK)
GAR_MOUNT_TPL = UnitTemplate(                  # 可驻楼班（③ 挂载即出楼联动——合成
    template_id=309, name="gar rider",         # CAN_GARRISON 位，现役 0 卡置位同
    category=1, cost=25,                       # test_garrison 数据侧脱节登记）
    element_templates=(RIFLE_SQUAD,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_GARRISON)
TRUCK3_TPL = UnitTemplate(                     # 三模式卡车（mode_set 含 TRANSPORT 位
    template_id=310, name="3-mode truck",      # ——⑧ M13/G18 门载体；seats=2）
    category=4, cost=35,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=10,
                                       seats=2),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.WHEEL,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.TRANSPORT))
PLATOON3_TPL = UnitTemplate(                   # 3 班 + 3 seats=1 载具（㉑A 主诺：
    template_id=311, name="mot plt",           # 3班→3车 1:1 形态重建载体）
    category=1, cost=60,
    element_templates=(RIFLE_SQUAD, RIFLE_SQUAD, RIFLE_SQUAD, CARRIER_ELEM,
                       CARRIER_ELEM, CARRIER_ELEM),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.TRACK)


def supply_truck(w, team, pos, weight=10):
    """CARGO 补给卡车（2026-10-03 拍板：一池通用补给按重量计 g——物资条件槽手工
    分配，make_unit 未承载 §D.5#16/17 分配）。"""
    t = add_unit(w, make_unit(w, TRUCK_TPL, team, team, pos))
    e = t.elements[0]
    e.mode = Mode.CARGO
    e.supply_weight_g = weight
    return t


class TestNeedsResupply(unittest.TestCase):
    """§F2 :442-445 判据（缺口制）：武器缺口 OR 步兵带伤。"""

    def test_weapon_deficit_only(self):
        w = make_world(3)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        u.elements[0].weapon_states[0].ammo_left = 9   # 9 < 10（非 EMPTY 亦登记）
        self.assertTrue(needs_resupply(u))

    def test_wounded_infantry_only(self):
        w = make_world(5)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        u.elements[0].hp_current = 7                   # 弹药满：仅带伤判据
        self.assertTrue(needs_resupply(u))

    def test_wounded_mech_alone_not_eligible(self):
        # MECH 带伤不入判据（医疗仅 INFANTRY——§F6 :1318 分支镜像）
        w = make_world(7)
        u = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (0, 0)))
        u.elements[0].hp_current = 5
        self.assertFalse(needs_resupply(u))

    def test_full_unit_false_and_zero_hp_edge(self):
        # 满编满血 → False；hp==0 班已被 destroy 除名（:1322 边界），带伤判据 0<hp 排除
        w = make_world(11)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        self.assertFalse(needs_resupply(u))
        u.elements[0].hp_current = 0
        self.assertFalse(needs_resupply(u))


class TestSystemSupplyAmmo(unittest.TestCase):
    def _world(self, seed=42):
        w = make_world(seed)
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        ws = inf.elements[0].weapon_states[0]
        ws.ammo_left = 0
        ws.state = WState.EMPTY
        w.await_resupply.append(inf)
        return w, inf, ws

    def test_resupply_rate_empty_to_ready(self):
        # 2026-10-03 一池重量口径：take=MIN(10−0, 10g//1g, 2)=2；EMPTY 有弹转 READY
        w, inf, ws = self._world()
        truck = supply_truck(w, 0, (5000, 0), weight=10)   # dist 5000 ≤ 8000
        system_supply(w)
        self.assertEqual(ws.ammo_left, 2)
        self.assertIs(ws.state, WState.READY)
        self.assertEqual(truck.elements[0].supply_weight_g, 8)
        self.assertEqual(w.await_resupply, [inf])       # 2<10 缺口仍在

    def test_fill_to_full_then_self_clean(self):
        # 2 发/tick × 5 tick 补满 10（每发 1g）；尾部 needs_resupply 自清理（方案19）
        w, inf, ws = self._world()
        supply_truck(w, 0, (5000, 0), weight=10)
        for _ in range(5):
            system_supply(w)
        self.assertEqual(ws.ammo_left, 10)
        self.assertEqual(w.await_resupply, [])

    def test_pool_limited_take(self):
        # 池重 1g 为最小项：take=MIN(10, 1//1, 2)=1；EMPTY 有弹仍转 READY
        w, inf, ws = self._world()
        supply_truck(w, 0, (0, 0), weight=1)
        system_supply(w)
        self.assertEqual(ws.ammo_left, 1)
        self.assertIs(ws.state, WState.READY)

    def test_heavy_round_drains_pool_faster(self):
        # 2026-10-03 拍板「不同弹药重量不同」：坦克炮弹 ammo_weight=30g——池 60g
        # 只补 2 发（take=MIN(缺口 10, 60//30=2, 2)=2，扣重 2×30=60g 池尽）；
        # 同速率下重弹吃池快（轻弹 1g/发同池可补 30 发）
        w = make_world(21)
        tank = add_unit(w, make_unit(w, HEAVY_TANK_TPL, 0, 0, (0, 0)))
        tws = tank.elements[0].weapon_states[0]
        tws.ammo_left = 0
        tws.state = WState.EMPTY
        w.await_resupply.append(tank)
        truck = supply_truck(w, 0, (0, 0), weight=60)
        system_supply(w)
        self.assertEqual(tws.ammo_left, 2)
        self.assertIs(tws.state, WState.READY)
        self.assertEqual(truck.elements[0].supply_weight_g, 0)

    def test_depleted_pool_keeps_empty_state(self):
        # 池耗尽（0g）：take=0——ammo_left 仍 0，EMPTY 不转（一池后无「医疗-only」形态）
        w, inf, ws = self._world()
        supply_truck(w, 0, (0, 0), weight=0)
        system_supply(w)
        self.assertEqual(ws.ammo_left, 0)
        self.assertIs(ws.state, WState.EMPTY)

    def test_partial_deficit_ready_stays(self):
        # 缺口 2（非 EMPTY、READY）：take=2 补满；状态不迁
        w, inf, ws = self._world()
        ws.ammo_left = 8
        ws.state = WState.READY
        supply_truck(w, 0, (0, 0), weight=10)
        system_supply(w)
        self.assertEqual(ws.ammo_left, 10)
        self.assertIs(ws.state, WState.READY)

    def test_multiple_cargo_elements_same_tick(self):
        # 外层逐 CARGO 元素扫描：两卡车同拍各补 2 → 4
        w, inf, ws = self._world()
        supply_truck(w, 0, (5000, 0), weight=10)
        supply_truck(w, 0, (0, 5000), weight=10)
        system_supply(w)
        self.assertEqual(ws.ammo_left, 4)

    def test_r21_team_gate(self):
        # R-21 敌方不可拾取（GDD-02 为准修正）：敌队班 radius 内零转移，且不入自清理
        w = make_world(9)
        enemy = add_unit(w, make_unit(w, INF_TPL, 1, 1, (0, 0)))
        ws = enemy.elements[0].weapon_states[0]
        ws.ammo_left = 0
        w.await_resupply.append(enemy)
        truck = supply_truck(w, 0, (5000, 0), weight=10)
        system_supply(w)
        self.assertEqual(ws.ammo_left, 0)
        self.assertEqual(truck.elements[0].supply_weight_g, 10)
        self.assertEqual(w.await_resupply, [enemy])     # alive+缺口仍在集合

    def test_radius_gate_inclusive_boundary(self):
        # dist==8000 恰在门内（<=）；8001 在门外
        w, inf, ws = self._world()
        supply_truck(w, 0, (8000, 0), weight=10)
        system_supply(w)
        self.assertEqual(ws.ammo_left, 2)
        w, inf, ws = self._world(seed=13)
        supply_truck(w, 0, (8001, 0), weight=10)
        system_supply(w)
        self.assertEqual(ws.ammo_left, 0)

    def test_self_clean_drops_dead_unit(self):
        # 车毁/全灭注销：alive=False 单位被尾部清理（world_tick 尸体清扫的前置防线）
        w, inf, ws = self._world()
        dead = add_unit(w, make_unit(w, INF_TPL, 0, 0, (1000, 1000)))
        dead.elements[0].weapon_states[0].ammo_left = 0
        dead.alive = False
        w.await_resupply.append(dead)
        system_supply(w)
        self.assertEqual(w.await_resupply, [inf])


class TestSystemSupplyMedical(unittest.TestCase):
    def _wounded(self, w, hp):
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        inf.elements[0].hp_current = hp                # 弹药满：仅带伤判据
        w.await_resupply.append(inf)
        return inf

    def test_medical_heal_amount(self):
        # 2026-10-03 一池重量口径：heal=MIN(10−3=7, 4g//1g=4)=4 → hp 7、池 4→0
        w = make_world(3)
        inf = self._wounded(w, 3)
        truck = supply_truck(w, 0, (0, 0), weight=4)
        system_supply(w)
        self.assertEqual(inf.elements[0].hp_current, 7)
        self.assertEqual(truck.elements[0].supply_weight_g, 0)
        self.assertEqual(w.await_resupply, [inf])      # 7<10 带伤保持

    def test_medical_deficit_limited(self):
        # 缺口限幅：hp 3/10、池 2g → hp 5；再补池 0 无效
        w = make_world(5)
        inf = self._wounded(w, 3)
        truck = supply_truck(w, 0, (0, 0), weight=2)
        system_supply(w)
        self.assertEqual(inf.elements[0].hp_current, 5)
        system_supply(w)
        self.assertEqual(inf.elements[0].hp_current, 5)

    def test_medical_caps_at_hp_max_and_self_clean(self):
        # hp 6/10、池 5g：heal=MIN(4, 5)=4 → hp 10、池剩 1；补满即出自清理
        w = make_world(7)
        inf = self._wounded(w, 6)
        truck = supply_truck(w, 0, (0, 0), weight=5)
        system_supply(w)
        self.assertEqual(inf.elements[0].hp_current, 10)
        self.assertEqual(truck.elements[0].supply_weight_g, 1)
        self.assertEqual(w.await_resupply, [])

    def test_mech_not_healed_and_dropped_from_set(self):
        # MECH 带伤不吃医疗且不满足 needs_resupply → 自清理移除
        w = make_world(11)
        truck = supply_truck(w, 0, (0, 0), weight=4)
        truck.elements[0].hp_current = 3
        w.await_resupply.append(truck)
        system_supply(w)
        self.assertEqual(truck.elements[0].hp_current, 3)
        self.assertEqual(w.await_resupply, [])


class TestRepair(unittest.TestCase):
    def _w(self, seed=42):
        w = make_world(seed)
        add_unit(w, make_unit(w, WRENCH_TPL, 0, 0, (0, 0)))   # repair_power=2 @原点
        return w

    def test_repair_power_per_tick_with_gates(self):
        # 同队半径内：5→7（repair_power 2）；敌队（2500 内）与半径外（4000>3000）零回血
        w = self._w()
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (2000, 0)))
        enemy = add_unit(w, make_unit(w, TANK_TPL, 1, 1, (2500, 0)))
        far = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (4000, 0)))
        for u in (tank, enemy, far):
            u.elements[0].hp_current = 5
        system_supply(w)
        self.assertEqual(tank.elements[0].hp_current, 7)
        self.assertEqual(enemy.elements[0].hp_current, 5)   # GAP-10 同队门
        self.assertEqual(far.elements[0].hp_current, 5)     # M24 repair_radius_cm=3000

    def test_infantry_not_repaired(self):
        # 维修目标仅 MECH 元素：带伤步兵半径内零回血
        w = self._w()
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (1000, 0)))
        inf.elements[0].hp_current = 4
        system_supply(w)
        self.assertEqual(inf.elements[0].hp_current, 4)

    def test_full_hp_with_crit_repaired_clears_crit(self):
        # hp 满但 crit 非空亦入维修门：hp 封顶不动、crit.clear()（D016）
        w = self._w()
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (1000, 0)))
        e = tank.elements[0]
        e.crit[CritSlot.MOB] = CritLevel.MAJOR
        system_supply(w)
        self.assertEqual(e.hp_current, 20)
        self.assertEqual(e.crit, {})

    def test_repair_to_full_stops_tow(self):
        # 修好即归队（R-19）：19+2 封顶 20 → crit 清 + stop_tow(REPAIRED)；
        # v1.5 C3：redeploy_needed 不清（解挂后须重新展开）
        w = self._w()
        tower = supply_truck(w, 0, (0, 0))                  # 牵引元素（任意 MECH）
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (1000, 0)))
        tow_e, tank_e = tower.elements[0], tank.elements[0]
        tow_e.towed = TowState.TOWING
        tank_e.towed = TowState.TOWED
        tank_e.redeploy_needed = True
        tank_e.hp_current = 19
        pair = TowPair(tower_elements=[tow_e], towed_element=tank_e)
        w.tow_pairs.append(pair)
        system_supply(w)
        self.assertEqual(tank_e.hp_current, 20)
        self.assertEqual(tank_e.crit, {})
        self.assertEqual(w.tow_pairs, [])
        self.assertIs(tow_e.towed, TowState.NONE)
        self.assertIs(tank_e.towed, TowState.NONE)
        self.assertTrue(tank_e.redeploy_needed)             # C3 锚点

    def test_repair_releases_only_involved_pair(self):
        # GAP-24 元素级：修好 1 辆只解除其牵涉的 1 对，另 1 对健康拖曳不动
        # （两对不相交——TowState 单槽：元素不可同时为牵引方与被拖方）
        w = self._w()
        a1 = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (0, 0)))
        t1 = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (1000, 0)))
        a2 = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (1500, 0)))
        t2 = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (2500, 0)))
        pairs = []
        for (tow, tw) in ((a1, t1), (a2, t2)):
            tow.elements[0].towed = TowState.TOWING
            tw.elements[0].towed = TowState.TOWED
            p = TowPair(tower_elements=[tow.elements[0]],
                        towed_element=tw.elements[0])
            pairs.append(p)
            w.tow_pairs.append(p)
        t1.elements[0].hp_current = 19                      # 仅 t1 修满触发
        system_supply(w)
        self.assertEqual(len(w.tow_pairs), 1)
        self.assertIs(w.tow_pairs[0], pairs[1])             # a2→t2 对保留
        self.assertIs(a2.elements[0].towed, TowState.TOWING)
        self.assertIs(t2.elements[0].towed, TowState.TOWED)
        self.assertIs(a1.elements[0].towed, TowState.NONE)  # 被解除对双方回 NONE
        self.assertIs(t1.elements[0].towed, TowState.NONE)

    def test_stop_tow_direct_call_reasons_identical(self):
        # §F6 :518-522：三因由同一收口——VOLUNTARY/DESTROYED 直调同效
        for reason in (TowStopReason.VOLUNTARY, TowStopReason.DESTROYED):
            w = make_world(13)
            tower = supply_truck(w, 0, (0, 0))
            tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (1000, 0)))
            pair = TowPair(tower_elements=[tower.elements[0]],
                           towed_element=tank.elements[0])
            tower.elements[0].towed = TowState.TOWING
            tank.elements[0].towed = TowState.TOWED
            w.tow_pairs.append(pair)
            stop_tow(w, pair, reason)
            self.assertEqual(w.tow_pairs, [])
            self.assertIs(tower.elements[0].towed, TowState.NONE)
            self.assertIs(tank.elements[0].towed, TowState.NONE)


class TestMountRequestsStep(unittest.TestCase):
    def _mixed(self, w):
        u = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (0, 0)))
        return u, u.elements[0], u.elements[1]              # 班元素 / seats=1 载具

    def test_lazy_none_table_returns(self):
        # 方案12：无表即无请求（非异常），表保持 None
        w = make_world(3)
        mount_requests_step(w)
        self.assertIsNone(w.mount_requests)

    def test_same_card_countdown_and_mount(self):
        # mount_time_ticks=200（R-07 上车 20s）：第 199 拍 ticks_left=1 未挂、
        # 第 200 拍挂载；同卡只写 mounted_in（cargo_units 不建）
        w = make_world(5)
        u, s, c = self._mixed(w)
        w.mount_requests = []
        w.mount_requests.append(MountRequest(squad_element=s, carrier=c, ticks_left=200))
        for _ in range(199):
            mount_requests_step(w)
        self.assertIsNone(s.mounted_in)
        self.assertEqual(w.mount_requests[0].ticks_left, 1)
        mount_requests_step(w)
        self.assertIs(s.mounted_in, c)
        self.assertEqual(w.mount_requests, [])
        self.assertIsNone(c.cargo_units)                    # 同卡不入 cargo_units
        self.assertEqual(seat_usage(c), 1)

    def test_recheck_revokes_on_carrier_mode_switch(self):
        # 载具切出可载状态（CARGO / TOW）→ 撤销且不递减；TRANSPORT 可载不撤
        for mode, revoked in ((Mode.CARGO, True), (Mode.TOW, True),
                              (Mode.TRANSPORT, False)):
            w = make_world(7)
            u, s, c = self._mixed(w)
            c.mode = mode
            w.mount_requests = [MountRequest(squad_element=s, carrier=c, ticks_left=200)]
            mount_requests_step(w)
            if revoked:
                self.assertEqual(w.mount_requests, [])
                self.assertIsNone(s.mounted_in)
            else:
                self.assertEqual(w.mount_requests[0].ticks_left, 199)

    def test_recheck_revokes_on_seat_overflow(self):
        # 座位超占：seats=1 已挂 1 班 + 在途 1 → 1+1 > 1 撤销（I-19 在途占座）
        w = make_world(9)
        u, s1, c = self._mixed(w)
        s1.mounted_in = c
        s2 = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0))).elements[0]
        w.mount_requests = [MountRequest(squad_element=s2, carrier=c, ticks_left=200)]
        mount_requests_step(w)
        self.assertEqual(w.mount_requests, [])
        self.assertIsNone(s2.mounted_in)
        self.assertEqual(seat_usage(c), 1)
        self.assertEqual(pending_mount_count(w, c), 0)

    def test_recheck_revokes_on_squad_removal(self):
        # 申请班元素不在编（除名）→ 撤销（㉑A 元素粒度复核）
        w = make_world(11)
        u, s, c = self._mixed(w)
        u.elements.remove(s)
        w.mount_requests = [MountRequest(squad_element=s, carrier=c, ticks_left=200)]
        mount_requests_step(w)
        self.assertEqual(w.mount_requests, [])

    def test_recheck_revokes_on_carrier_removal(self):
        # 载具元素不在编（车毁除名）→ 撤销
        w = make_world(13)
        u, s, c = self._mixed(w)
        u.elements.remove(c)
        w.mount_requests = [MountRequest(squad_element=s, carrier=c, ticks_left=200)]
        mount_requests_step(w)
        self.assertEqual(w.mount_requests, [])

    def test_cross_card_cargo_units_dedupe(self):
        # 跨卡：两班（同单位）挂 seats=2 载具——逐班各占 1 座；cargo_units 单位级
        # 登记去重（同单位多班挂同车不重复入表）
        w = make_world(3)
        cu = add_unit(w, make_unit(w, BIG_CARRIER_TPL, 0, 0, (0, 0)))
        su = add_unit(w, make_unit(w, TWO_SQUAD_TPL, 0, 0, (500, 0)))
        c = cu.elements[0]
        s1, s2 = su.elements
        w.mount_requests = [MountRequest(squad_element=s1, carrier=c, ticks_left=200),
                            MountRequest(squad_element=s2, carrier=c, ticks_left=200)]
        for _ in range(200):
            mount_requests_step(w)
        self.assertIs(s1.mounted_in, c)
        self.assertIs(s2.mounted_in, c)
        self.assertEqual(c.cargo_units, [su])               # 去重：单位一次
        self.assertEqual(seat_usage(c), 2)

    def test_seat_usage_counts_same_and_cross_card(self):
        # 载具占用数=同卡 mounted_in 班 + 跨卡 cargo_units 内班元素（㉑A 统一账）
        w = make_world(42)
        cu = add_unit(w, make_unit(w, BIG_CARRIER_TPL, 0, 0, (0, 0)))
        su = add_unit(w, make_unit(w, TWO_SQUAD_TPL, 0, 0, (500, 0)))
        c = cu.elements[0]
        su.elements[0].mounted_in = c                       # 跨卡班元素
        c.cargo_units = [su]
        self.assertEqual(seat_usage(c), 1)
        self.assertEqual(pending_mount_count(w, c), 0)      # 惰性表 None=0


class TestPipelineIntegration(unittest.TestCase):
    """world_tick ⑥⑦ 行序接线：system_projectiles 之后、尸体清扫之前；全程零掷骰。"""

    def test_world_tick_drives_supply_and_mount(self):
        w = make_world(42)
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        ws = inf.elements[0].weapon_states[0]
        ws.ammo_left = 0
        ws.state = WState.EMPTY
        w.await_resupply.append(inf)
        supply_truck(w, 0, (5000, 0), weight=10)
        mixed = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (1000, 0)))
        s, c = mixed.elements
        w.mount_requests = [MountRequest(squad_element=s, carrier=c, ticks_left=200)]
        rng0 = [r.state for r in w.rng._rngs]
        world_tick(w)
        self.assertEqual(ws.ammo_left, 2)                   # ⑥ 同拍生效
        world_tick(w)
        self.assertEqual(ws.ammo_left, 4)
        for _ in range(197):                                # 拍 3..199
            world_tick(w)
        self.assertIs(s.mounted_in, None)                   # 第 199 拍末未挂
        world_tick(w)                                       # 第 200 拍
        self.assertIs(s.mounted_in, c)                      # ⑦ 第 200 拍挂载
        self.assertEqual([r.state for r in w.rng._rngs], rng0)   # 零掷骰


def fingerprint(w):
    """本块状态面指纹：tick/相位 + 八通道 PCG32 state + 单位/元素（pos/hp/弹药/
    物资/挂载/模式/crit）+ await_resupply/mount_requests/tow_pairs（照
    tests/test_integration.py fingerprint 范式裁剪本块消费面）。"""
    parts = ["t%d:p%d:r%s" % (w.tick, w.phase,
                              ",".join(str(r.state) for r in w.rng._rngs))]
    for u in w.units:
        parts.append("U%d,%d,%s,%d,%d" % (u.id, u.team, u.pos, int(u.alive),
                                          u.spotted_mask))
        for e in u.elements:
            mref = "-" if e.mounted_in is None else "M%d" % e.mounted_in.id
            parts.append("E%d,%s,%d,%d,%d,%s,%d,%r,%r" % (
                e.id, e.pos, e.hp_current, int(e.mode), int(e.towed),
                mref, len(e.crit), e.supply_weight_g,
                [x.id for x in (e.cargo_units or ())]))
            for ws in e.weapon_states:
                parts.append("W%d,%d,%d" % (int(ws.state), ws.timer, ws.ammo_left))
    parts.append("AR%s" % [u.id for u in w.await_resupply])
    parts.append("MR%s" % [("s%d" % r.squad_element.id, "c%d" % r.carrier.id,
                            r.ticks_left) for r in (w.mount_requests or ())])
    parts.append("TP%d" % len(w.tow_pairs))
    return "|".join(parts)


class TestDeterminismDualRun(unittest.TestCase):
    def test_dual_run_250_ticks_bit_identical(self):
        # 同 seed 两 world（补给卡车 15g 一池+弹药/医疗双缺口班+上车请求+拖曳对+维修），
        # 逐 tick 比指纹至 250 拍。手推锚点（一池：先弹后医、同拍两扣）：拍1 弹+2
        # （池 15→13）/血 6→10（heal 4，池 13→9）、坦克 19→20 修满解拖；拍2..5 每
        # 拍弹+2 → 拍5 弹满 10（池共扣 10×1+4=14）、await 出清；拍200 班挂载；末态池剩 1。
        def build(seed):
            w = make_world(seed)
            truck = supply_truck(w, 0, (5000, 0), weight=15)
            inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
            ws = inf.elements[0].weapon_states[0]
            ws.ammo_left = 0
            ws.state = WState.EMPTY
            inf.elements[0].hp_current = 6
            w.await_resupply.append(inf)
            mixed = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (1000, 0)))
            s, c = mixed.elements
            w.mount_requests = [MountRequest(squad_element=s, carrier=c,
                                             ticks_left=200)]
            tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (2000, 0)))
            tank.elements[0].hp_current = 19
            tank.elements[0].redeploy_needed = True
            add_unit(w, make_unit(w, WRENCH_TPL, 0, 0, (0, 0)))
            tow_e = truck.elements[0]
            tow_e.towed = TowState.TOWING
            tank.elements[0].towed = TowState.TOWED
            w.tow_pairs.append(TowPair(tower_elements=[tow_e],
                                       towed_element=tank.elements[0]))
            add_unit(w, make_unit(w, INF_TPL, 1, 1, (800000, 800000)))
            return w

        w1, w2 = build(42), build(42)
        rng0 = [r.state for r in w1.rng._rngs]
        for _ in range(250):
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(fingerprint(w1), fingerprint(w2))
        self.assertEqual([r.state for r in w1.rng._rngs], rng0)   # 全程零掷骰
        inf = w1.units[1]
        self.assertEqual(inf.elements[0].weapon_states[0].ammo_left, 10)  # 拍5 补满
        self.assertEqual(inf.elements[0].hp_current, 10)                 # 拍1 医疗封顶
        self.assertEqual(w1.units[0].elements[0].supply_weight_g, 1)     # 15−10弹−4医
        self.assertEqual(w1.await_resupply, [])                          # 补满出清
        mixed = w1.units[2]
        self.assertIs(mixed.elements[0].mounted_in, mixed.elements[1])   # 拍200 挂载
        tank = w1.units[3]
        self.assertEqual(tank.elements[0].hp_current, 20)
        self.assertEqual(w1.tow_pairs, [])                               # 修满解拖
        self.assertTrue(tank.elements[0].redeploy_needed)                # C3 保留


# ── §F6 :1137-1168 cmd_mount / :1131-1136 cmd_dismount（PB-56 批② 机动链命令块·
#    上下车，2026-10-06——门序①-⑪ 逐项/分派链/全链挂载/容量占位/挂载即出楼/双形卸载）──


class TestCmdMount(unittest.TestCase):
    """cmd_mount 门序逐项（㉑A 逐班语义：ok==0 才整体 REJECT，部分成功为逐班）。"""

    def _mixed(self, w):
        u = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (0, 0)))
        return u, u.elements[0], u.elements[1]              # 班元素 / seats=1 载具

    def test_dispatch_chain_full_mount(self):
        # 分派链全链：queue_command→world_tick① consume（请求 ticks_left=200）→
        # 同拍 ⑦ mount_requests_step 递减至 199；第 200 拍挂载（同卡只写 mounted_in）
        w = make_world(5)
        u, s, c = self._mixed(w)
        rng0 = [r.state for r in w.rng._rngs]
        queue_command(w, MountCmd(squad_elements=[s], carrier_unit=u))
        world_tick(w)                                       # 拍 1：受令+首减
        self.assertEqual(len(w.mount_requests), 1)
        r = w.mount_requests[0]
        self.assertIs(r.squad_element, s)
        self.assertIs(r.carrier, c)
        self.assertEqual(r.ticks_left, 199)
        for _ in range(198):                                # 拍 2..199
            world_tick(w)
        self.assertIsNone(s.mounted_in)                     # 第 199 拍末未挂
        world_tick(w)                                       # 拍 200：挂载
        self.assertIs(s.mounted_in, c)
        self.assertEqual(w.mount_requests, [])
        self.assertIsNone(c.cargo_units)                    # 同卡不入 cargo_units
        self.assertEqual(seat_usage(c), 1)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)   # 零掷骰

    def test_gate1_non_squad_element_skipped(self):
        # ① 载具元素非 SQUAD → CONTINUE → ok==0 REJECT（表不建）
        w = make_world(3)
        u, s, c = self._mixed(w)
        self.assertFalse(cmd_mount(w, [c], u))
        self.assertIsNone(w.mount_requests)

    def test_gate2_pending_request_dedupe_no_reset(self):
        # ② 挂起请求在途不重发——既有条目 ticks_left 不被重置（无冒充副作用）。
        # 2026-10-06 批②评审#1 勘正：seats=1 同卡配置下 ⑨（座位）独立产生同样
        # REJECT=断言对 ② 不敏感（变异验证）；换 seats=2 跨卡载体（⑨ 0+1+1≤2
        # 可过）使 ② 成为唯一拦截门
        w = make_world(7)
        cu = add_unit(w, make_unit(w, BIG_CARRIER_TPL, 0, 0, (0, 0)))
        su = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        s = su.elements[0]
        c = cu.elements[0]
        w.mount_requests = [MountRequest(squad_element=s, carrier=c, ticks_left=57)]
        mount_requests_step(w)                              # 57→56（证明条目推进过）
        self.assertFalse(cmd_mount(w, [s], cu))             # ② 独家拦截（⑨ 不拦）
        self.assertEqual(len(w.mount_requests), 1)
        self.assertEqual(w.mount_requests[0].ticks_left, 56)

    def test_gate3_mount_exits_garrison(self):
        # ③ 挂载即出楼（M11/G24）：驻楼班上车 → cmd_un_garrison 双向清+楼旁落位，
        # 请求照建（真命令链驻楼：cmd_garrison CAN_GARRISON 合成位）
        w = make_world(9)
        b = Building(id=1, pos=(0, 0), hp=100, garrison_slots=2)
        gu = add_unit(w, make_unit(w, GAR_MOUNT_TPL, 0, 0, (0, 0)))
        cu = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (0, 0)))
        self.assertTrue(cmd_garrison(w, gu, b))
        self.assertEqual(b.garrisoned, [gu.elements[0]])
        self.assertTrue(cmd_mount(w, [gu.elements[0]], cu))
        self.assertIsNone(gu.elements[0].garrison_in)       # 双向清
        self.assertEqual(b.garrisoned, [])
        self.assertEqual(gu.elements[0].pos, b.pos)         # 楼旁落位（同点位）
        self.assertEqual(len(w.mount_requests), 1)          # 请求照建

    def test_gate3_unconditional_before_later_gates(self):
        # ③ 字面次序=无条件先行：载具无座（⑥ CONTINUE→ok==0 REJECT）出楼仍已发生
        w = make_world(11)
        b = Building(id=1, pos=(0, 0), hp=100, garrison_slots=2)
        gu = add_unit(w, make_unit(w, GAR_MOUNT_TPL, 0, 0, (0, 0)))
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        cmd_garrison(w, gu, b)
        self.assertFalse(cmd_mount(w, [gu.elements[0]], inf))   # ⑥ 无座 REJECT
        self.assertIsNone(gu.elements[0].garrison_in)           # 出楼已发生
        self.assertEqual(b.garrisoned, [])
        self.assertIsNone(w.mount_requests)

    def test_gate6_no_seats_carrier_reject(self):
        # ⑥ carrier_unit 无 seats>0 元素 → carriers=[] → CONTINUE → REJECT
        w = make_world(13)
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        self.assertFalse(cmd_mount(w, [inf.elements[0]], inf))
        self.assertIsNone(w.mount_requests)

    def test_gate7_cargo_or_tow_mode_skip(self):
        # ⑦ 载货/拖曳状态不可载人（REJECT 前置于 ⑩——表不建）
        for mode in (Mode.CARGO, Mode.TOW):
            w = make_world(15)
            u, s, c = self._mixed(w)
            c.mode = mode
            self.assertFalse(cmd_mount(w, [s], u))
            self.assertIsNone(w.mount_requests)

    def test_gate8_transport_bit_requires_transport_mode(self):
        # ⑧ mode_set 含 TRANSPORT 位（:1160 字段勘误→carrier.unit.template.mode_set）
        # 且 mode≠TRANSPORT → CONTINUE；切 TRANSPORT 后受令；无位载具（缺省
        # DIRECT-only）DIRECT 可载不受限
        w = make_world(17)
        cu = add_unit(w, make_unit(w, TRUCK3_TPL, 0, 0, (0, 0)))
        su = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))    # 同点位（⑪ 同点位判）
        c = cu.elements[0]
        self.assertEqual(c.unit.template.mode_set & (1 << Mode.TRANSPORT),
                         1 << Mode.TRANSPORT)                    # 位在（门可触发前提）
        self.assertFalse(cmd_mount(w, [su.elements[0]], cu))     # DIRECT → CONTINUE
        self.assertIsNone(w.mount_requests)
        c.mode = Mode.TRANSPORT
        self.assertTrue(cmd_mount(w, [su.elements[0]], cu))      # TRANSPORT → 受令
        self.assertEqual(len(w.mount_requests), 1)
        w2 = make_world(19)                                      # 无位载具不受限
        u2, s2, c2 = self._mixed(w2)
        self.assertEqual(c2.unit.template.mode_set & (1 << Mode.TRANSPORT), 0)
        self.assertTrue(cmd_mount(w2, [s2], u2))

    def test_gate9_seats_cap_includes_pending(self):
        # ⑨ seats 上限含在途占座：seats=1 已有 1 挂起请求 → 0+1+1>1 CONTINUE
        w = make_world(21)
        u, s1, c = self._mixed(w)
        self.assertTrue(cmd_mount(w, [s1], u))                   # 首班占在途 1
        s2 = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0))).elements[0]
        self.assertFalse(cmd_mount(w, [s2], u))
        self.assertEqual(len(w.mount_requests), 1)
        self.assertEqual(pending_mount_count(w, c), 1)

    def test_gate10_lazy_table_created_before_stationary_gate(self):
        # ⑩ 字面次序（:1165）：过 ⑨ 即惰性建表——⑪ 不中（距离不满足）表已建为空。
        # 跨卡载体（同卡班/载具共单位锚——dist 恒 0，距离门须跨卡才可触发）
        w = make_world(23)
        cu = add_unit(w, make_unit(w, BIG_CARRIER_TPL, 0, 0, (0, 0)))
        su = add_unit(w, make_unit(w, INF_TPL, 0, 0, (500, 0)))
        self.assertFalse(cmd_mount(w, [su.elements[0]], cu))    # ⑪ dist=500≠0 不中 → ok==0
        self.assertEqual(w.mount_requests, [])                  # ⑩ 空表已建（字面）

    def test_gate11_same_position_and_both_stationary(self):
        # ⑪ 「旁」=同点位判（可推翻拍板项）+ 双静止：距离不满足/申请班在动/载具在动
        # 三负锚 + 同点位静止正锚
        w = make_world(25)
        cu = add_unit(w, make_unit(w, BIG_CARRIER_TPL, 0, 0, (0, 0)))
        su = add_unit(w, make_unit(w, INF_TPL, 0, 0, (500, 0)))
        self.assertFalse(cmd_mount(w, [su.elements[0]], cu))     # dist=500≠0
        su.pos = (0, 0)                                         # 同点位（点单位可叠放）
        self.assertTrue(cmd_mount(w, [su.elements[0]], cu))      # 正锚：受令
        su2 = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))   # 申请班在动（负锚）
        su2.move_path = [(1000, 0)]                             # moving()=bool(move_path)
        self.assertFalse(cmd_mount(w, [su2.elements[0]], cu))    # seats=2：首班在途 1
        su3 = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))   # 载具在动（负锚）
        cu.move_path = [(1000, 0)]
        self.assertFalse(cmd_mount(w, [su3.elements[0]], cu))

    def test_min_load_three_squads_to_three_carriers(self):
        # ⑤ ㉑A 主诺（:1139-1143）：3 班一令逐班最少挂载重选 → 3 车各 1（1:1 形态
        # 重建）；分配确定：s0→c0（载 0+在途 0）、s1→c1（c0 已占 1）、s2→c2
        w = make_world(27)
        u = add_unit(w, make_unit(w, PLATOON3_TPL, 0, 0, (0, 0)))
        squads = u.elements[:3]
        carriers = u.elements[3:]
        self.assertTrue(cmd_mount(w, squads, u))
        got = [(r.squad_element, r.carrier) for r in w.mount_requests]
        self.assertEqual(got, list(zip(squads, carriers)))      # 列表序 1:1
        for _ in range(200):
            world_tick(w)
        for s, c in zip(squads, carriers):
            self.assertIs(s.mounted_in, c)                      # 逐班 1:1 挂载
            self.assertEqual(seat_usage(c), 1)

    def test_partial_success_returns_true(self):
        # 部分成功为逐班语义：2 班 × seats=1 → 首班占座、次班 ⑨ 跳过、整体受令
        w = make_world(29)
        u, s1, c = self._mixed(w)
        s2 = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0))).elements[0]
        self.assertTrue(cmd_mount(w, [s1, s2], u))
        self.assertEqual([r.squad_element for r in w.mount_requests], [s1])
        for _ in range(200):
            world_tick(w)
        self.assertIs(s1.mounted_in, c)
        self.assertIsNone(s2.mounted_in)

    def test_already_mounted_no_guard_literal(self):
        # 伪代码字面缺口登记（去重仅查挂起请求 :1147）：已挂班可再获新请求——
        # seats=2 载具已挂 1 班（挂载态照 ⑦ 到期写点补 mounted_in+cargo_units）→
        # 1+0+1=2≤2 过 ⑨、同点位静止过 ⑪ → 建条（请求不占指针账——窗口内双记仅
        # 体现为 seat_usage+pending=2==seats；到期覆写 mounted_in 同车、座位账
        # 事后自纠。低危照字面，登记可推翻）
        w = make_world(31)
        cu = add_unit(w, make_unit(w, BIG_CARRIER_TPL, 0, 0, (0, 0)))
        su = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        c = cu.elements[0]
        s = su.elements[0]
        s.mounted_in = c                                       # 已挂（⑦ 到期双写点：
        c.cargo_units = [su]                                   #  mounted_in+cargo_units）
        self.assertTrue(cmd_mount(w, [s], cu))                 # 字面：再建一条
        self.assertEqual(len(w.mount_requests), 1)
        self.assertEqual(seat_usage(c), 1)                     # 请求不改指针账（仍 1）


class TestCmdDismount(unittest.TestCase):
    """cmd_dismount 双形卸载（同卡 mounted_in / 跨卡 cargo_units 按身份移除）。"""

    def test_same_card_dismount(self):
        # 同卡：清 mounted_in+旁落位同点位；cargo_units 不建（同卡无跨卡登记）
        w = make_world(3)
        u = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (1000, 200)))
        s, c = u.elements
        s.mounted_in = c
        cmd_dismount(w, u)
        self.assertIsNone(s.mounted_in)
        self.assertEqual(s.pos, c.pos)                         # 载具元素同点位
        self.assertIsNone(c.cargo_units)

    def test_cross_card_dismount_clears_cargo_units_once(self):
        # 跨卡：两班同挂 → cargo_units 单位级条目按身份移除一次（两元素各清各的）
        w = make_world(5)
        cu = add_unit(w, make_unit(w, BIG_CARRIER_TPL, 0, 0, (2000, 0)))
        su = add_unit(w, make_unit(w, TWO_SQUAD_TPL, 0, 0, (0, 0)))
        c = cu.elements[0]
        for se in su.elements:
            se.mounted_in = c
        c.cargo_units = [su]
        cmd_dismount(w, su)
        for se in su.elements:
            self.assertIsNone(se.mounted_in)
            self.assertEqual(se.pos, c.pos)
        self.assertEqual(c.cargo_units, [])                    # 按身份移除 → 空

    def test_non_squad_mounted_ref_untouched(self):
        # WHERE element_type==SQUAD（㉑A 口径）：VEHICLE 元素的挂载引用不清
        w = make_world(7)
        u = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (0, 0)))
        cu = add_unit(w, make_unit(w, BIG_CARRIER_TPL, 0, 0, (0, 0)))
        s, veh = u.elements
        c = cu.elements[0]
        s.mounted_in = c
        veh.mounted_in = c                                     # 合成挂载引用（锚 WHERE 谓词）
        cmd_dismount(w, u)
        self.assertIsNone(s.mounted_in)                        # SQUAD 清
        self.assertIs(veh.mounted_in, c)                       # VEHICLE 保持（字面）

    def test_not_mounted_noop(self):
        # 无资格门/无 REJECT（:1131 无返回值）——未挂载单位下车=无操作
        w = make_world(9)
        u = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (0, 0)))
        pos0 = [e.pos for e in u.elements]
        self.assertIsNone(cmd_dismount(w, u))
        self.assertEqual([e.pos for e in u.elements], pos0)

    def test_dispatch_chain_dismount(self):
        # 分派链：queue_command→world_tick① consume → 卸载
        w = make_world(11)
        u = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (3000, 400)))
        s, c = u.elements
        s.mounted_in = c
        rng0 = [r.state for r in w.rng._rngs]
        queue_command(w, DismountCmd(squad_unit=u))
        world_tick(w)
        self.assertIsNone(s.mounted_in)
        self.assertEqual(s.pos, c.pos)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)   # 零掷骰

    def test_full_cycle_cross_card_mount_then_dismount(self):
        # 全链闭环：cmd_mount（跨卡同点位）→200 拍→两班挂+cargo_units=[单位]（去重）
        # →cmd_dismount→双向全清
        w = make_world(13)
        cu = add_unit(w, make_unit(w, BIG_CARRIER_TPL, 0, 0, (500, 500)))
        su = add_unit(w, make_unit(w, TWO_SQUAD_TPL, 0, 0, (500, 500)))
        c = cu.elements[0]
        self.assertTrue(cmd_mount(w, list(su.elements), cu))
        self.assertEqual(len(w.mount_requests), 2)             # 逐班各一条
        for _ in range(200):
            world_tick(w)
        for se in su.elements:
            self.assertIs(se.mounted_in, c)
        self.assertEqual(c.cargo_units, [su])                  # 单位级登记去重
        self.assertEqual(seat_usage(c), 2)
        cmd_dismount(w, su)
        for se in su.elements:
            self.assertIsNone(se.mounted_in)
            self.assertEqual(se.pos, c.pos)
        self.assertEqual(c.cargo_units, [])
        self.assertEqual(seat_usage(c), 0)


if __name__ == "__main__":
    unittest.main()
