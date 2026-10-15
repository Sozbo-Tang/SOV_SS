"""全流程 AI 层测试：排兵（队形/预置车道）/ 空军调度（呼叫/打击/巡逻/返场）/
预备队空投（DELIVERY_AIRDROP_ONLY 卡经运输机投放——D017 唯一投入路径）。

覆盖 v2 新增的三类决策节拍（deploy/air）与 state_view 空军段；地面节拍与
确定性回归在 test_ai_kev.py。零模型依赖（fallback/假引擎驱动）。
"""
from __future__ import annotations

import unittest

from sovs.ai import (KevPlayer, air_candidates, build_commands,
                     deploy_candidates, situation_brief)
from sovs.sim.air import (PHASE_COMBAT, PHASE_DEPLOY, AirRole, AirState,
                          AircraftInstance)
from sovs.sim.air_data import CARD_OBJECTS
from sovs.sim.tables import CONFIG
from sovs.sim.tick import (DeckSlot, FormationCmd, MoveCmd, Objective,
                           AirAirdropCmd, AirCallCmd, AirRTBCmd, AirStrikeCmd,
                           add_unit, make_unit, make_world)
from sovs.sim.types import (ElementTemplate, ElementType, Mode,
                            MovementClass, UnitFlag, UnitTemplate, UnitType,
                            WeaponTemplate)
from tests.test_ai_kev import GUN_TPL, RIFLE_W, RIFLE_TPL, TANK_TPL

SOUTH, NORTH = (100000, 0), (100000, 100000)

# 多元素单位（队形令载体——2 班排）
PLATOON_TPL = UnitTemplate(
    template_id=921, name="rifle plt(2sq)", category=1, cost=100,
    element_templates=(
        ElementTemplate(element_type=ElementType.SQUAD,
                        unit_type=UnitType.INFANTRY, hp_max=10,
                        weapons=(RIFLE_W,)),) * 2,
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)
# 预备队空降卡（空裁8 投送限定——购卡门恒拒，唯一路径=运输机 PARATROOP 载荷）
PARA_TPL = UnitTemplate(
    template_id=922, name="paratroop plt", category=1, cost=60,
    element_templates=(
        ElementTemplate(element_type=ElementType.SQUAD,
                        unit_type=UnitType.INFANTRY, hp_max=10,
                        weapons=(RIFLE_W,)),) * 3,
    optics_ground_cm=120000, stealth_base=6, speed_tier=1,
    movement_class=MovementClass.FOOT,
    flags=UnitFlag.DELIVERY_AIRDROP_ONLY)


def world_at(phase: int, tick: int = 0):
    w = make_world(11, phase=phase, tick=tick, size_cm=(200000, 100000))
    w.objectives.append(Objective(id=1, pos=(100000, 50000), radius_cm=5000))
    for p in w.players:
        p.deck_slots = [DeckSlot(RIFLE_TPL, 2)]
    return w


def mk_aircraft(w, key: str, *, state=AirState.PATROL, ammo=None, cargo=None,
                pos=(100000, 50000)):
    tpl = CARD_OBJECTS[key]
    a = AircraftInstance(id=w.next_aircraft_id, team=0, player_index=0,
                         template=tpl, pos=pos,
                         alt_tier=tpl.alt_ceiling or tpl.alt_ceiling,
                         hp_current=tpl.hp_max, state=state)
    w.next_aircraft_id += 1
    a.ammo_left = dict(ammo or {})
    a.paratroop_cargo = cargo
    w.aircraft.append(a)
    return a


# ── 排兵（盲部署相位）──

class TestDeployBeat(unittest.TestCase):
    def test_formation_and_lane_candidates(self):
        w = world_at(PHASE_DEPLOY)
        u = add_unit(w, make_unit(w, PLATOON_TPL, 0, 0, (100000, 0)))
        cands = deploy_candidates(w, 0, issued_moves=set(), issued_formations=set())
        kinds = {c.kind for c in cands}
        self.assertIn("formation", kinds)             # 多元素单位→队形令
        self.assertEqual(len([c for c in cands if c.kind == "formation"]), 3)
        self.assertIn("deploy_move", kinds)           # 预置展开车道（西/中/东）
        self.assertEqual(len([c for c in cands if c.kind == "deploy_move"]), 3)
        self.assertEqual(cands[-1].kind, "wait")

    def test_issued_sets_prevent_reissue(self):
        w = world_at(PHASE_DEPLOY)
        add_unit(w, make_unit(w, PLATOON_TPL, 0, 0, (100000, 0)))
        cands = deploy_candidates(w, 0, issued_moves={1}, issued_formations={1})
        self.assertEqual([c.kind for c in cands], ["wait"])   # 全已办→静默

    def test_player_step_issues_deploy_commands(self):
        w = world_at(PHASE_DEPLOY, tick=25)           # 25 % 50 == 25 → 排兵节拍
        add_unit(w, make_unit(w, PLATOON_TPL, 0, 0, (100000, 0)))
        ai = KevPlayer(0, None, anchors=(SOUTH, NORTH))
        ai.step(w)
        self.assertEqual(ai.stats["fallback"], 1)     # 兜底=车道 MoveCmd（效用 40）
        cmd = w.command_queue[0]
        self.assertIsInstance(cmd, MoveCmd)
        ai._deploy_moved.add(cmd.unit.id)             # 模拟执行期记账
        w.command_queue.clear()
        ai.step(w)                                    # 下一拍：队形令（LINE 36）
        self.assertTrue(any(isinstance(c, FormationCmd) for c in w.command_queue))
        ai.close()

    def test_lane_spread_deterministic(self):
        w = world_at(PHASE_DEPLOY)
        for i in range(3):
            add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (100000, 0)))
        moved = set()
        lanes = []
        for _ in range(3):
            cands = deploy_candidates(w, 0, issued_moves=moved,
                                      issued_formations=set())
            best = max(cands, key=lambda c: (c.utility, -ord(c.key[0])))
            lanes.append(tuple(best.params["dest"]))
            moved.add(best.params["unit_id"])
        self.assertEqual(len(set(lanes)), 3)          # 兜底轮转=三车道各一


# ── 空军调度 ──

class TestAirBeat(unittest.TestCase):
    def test_call_candidates_respect_gates(self):
        from sovs.ai.actions import _air_cost
        w = world_at(PHASE_COMBAT)
        p = w.players[0]
        il2m = CARD_OBJECTS["IL2M"]
        # 2026-10-14 空袭按用计费块：呼叫门=本体价（BOMB 弹费改投放时逐发扣，
        # 挂弹不再按点数预算钳——满载呼叫）；该型点数差 1 点即静默
        p.air_points = il2m.cost_body - 1
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        self.assertNotIn("call_il2m", {c.key for c in cands})
        p.air_points = il2m.cost_body
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        calls = {c.key: c for c in cands if c.kind == "air_call"}
        self.assertEqual(calls["call_il2m"].params["payload"]["BOMB"],
                         il2m.payload_max_bombs)       # 满载呼叫
        # 呼叫价与点数门一致（§F1 现口径=本体价，弹费按发另结）
        self.assertEqual(_air_cost(il2m, calls["call_il2m"].params["payload"]),
                         il2m.cost_body)
        p.air_points = 0
        self.assertEqual([c.kind for c in air_candidates(w, 0, enemy_anchor=NORTH)],
                         ["wait"])                    # 点数尽→静默

    def test_air_call_executes_and_spawns_aircraft(self):
        w = world_at(PHASE_COMBAT, tick=150)          # 150 % 150 == 0 → 空军节拍
        ai = KevPlayer(0, None, anchors=(SOUTH, NORTH))
        ai.step(w)
        self.assertGreaterEqual(ai.stats["fallback"], 1)
        call = next(c for c in w.command_queue if isinstance(c, AirCallCmd))
        before = w.players[0].air_points
        from sovs.sim.tick import consume_commands, world_tick
        consume_commands(w)
        world_tick(w)
        self.assertEqual(len(w.aircraft), 1)          # 飞机真实入列
        self.assertLess(w.players[0].air_points, before)
        ai.close()

    def test_strike_targets_visible_cluster(self):
        w = world_at(PHASE_COMBAT)
        foe = add_unit(w, make_unit(w, RIFLE_TPL, 1, 1, (100000, 60000)))
        foe.spotted_mask |= 1 << 0
        mk_aircraft(w, "IL2M", ammo={"BOMB": 2})
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        strike = next(c for c in cands if c.kind == "strike")
        self.assertEqual(strike.params["target"], [100000, 60000])  # 集群质心
        cmds = build_commands(w, w.players[0], strike)
        self.assertIsInstance(cmds[0], AirStrikeCmd)

    def test_rtb_for_spent_aircraft(self):
        w = world_at(PHASE_COMBAT)
        mk_aircraft(w, "IL2M", ammo={"BOMB": 0, "STRAFE": 3})
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        rtb = [c for c in cands if c.kind == "air_rtb"]
        self.assertEqual(len(rtb), 1)
        self.assertIsInstance(build_commands(w, w.players[0], rtb[0])[0],
                              AirRTBCmd)

    def test_in_air_cap_prevents_duplicate_calls(self):
        w = world_at(PHASE_COMBAT)
        mk_aircraft(w, "IL2M", ammo={"BOMB": 2})
        mk_aircraft(w, "IL2M", ammo={"BOMB": 2})      # air_per_type_max=2 已满
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        self.assertNotIn("call_il2m", [c.key for c in cands])


# ── 预备队（空降卡——运输机装机→投放）──

class TestReserveAirdrop(unittest.TestCase):
    def test_transport_call_carries_paratroop_template(self):
        w = world_at(PHASE_COMBAT)
        w.players[0].deck_slots.append(DeckSlot(PARA_TPL, 2))
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        troop = next(c for c in cands if c.key == "call_troop_li2")
        cmds = build_commands(w, w.players[0], troop)
        call = cmds[0]
        self.assertIsInstance(call, AirCallCmd)
        self.assertIs(call.payload["PARATROOP"], PARA_TPL)   # 执行期换真实模板
        # 装机即扣份（B-06/B-12）+ 飞机入列 + 载员槽
        from sovs.sim.tick import consume_commands
        w.command_queue.append(call)
        consume_commands(w)
        self.assertEqual(len(w.aircraft), 1)
        self.assertIs(w.aircraft[0].paratroop_cargo, PARA_TPL)
        copies = next(s.copies_left for s in w.players[0].deck_slots
                      if s.template is PARA_TPL)
        self.assertEqual(copies, 1)

    def test_drop_candidate_after_on_station(self):
        w = world_at(PHASE_COMBAT)
        mk_aircraft(w, "LI2", cargo=PARA_TPL, ammo={"SUPPLY": 0})
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        drop = next(c for c in cands if c.kind == "airdrop")
        self.assertEqual(drop.params["point"], [100000, 50000])  # 落点=无主占点
        cmds = build_commands(w, w.players[0], drop)
        self.assertIsInstance(cmds[0], AirAirdropCmd)

    def test_no_troop_call_without_reserve_copies(self):
        w = world_at(PHASE_COMBAT)
        w.players[0].deck_slots.append(DeckSlot(PARA_TPL, 0))   # 份尽
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        self.assertNotIn("call_troop_li2", [c.key for c in cands])


# ── 上下车 / 拖曳 / 驻楼 / 烟幕 / 高度层（v3 增量合成卡）──

CARRIER_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                               unit_type=UnitType.MECH, hp_max=15, seats=2)
MIXED_TPL = UnitTemplate(                      # 班+座混编卡（出生同点位堆叠）
    template_id=931, name="motorized plt", category=1, cost=120,
    element_templates=(
        ElementTemplate(element_type=ElementType.SQUAD,
                        unit_type=UnitType.INFANTRY, hp_max=10,
                        weapons=(RIFLE_W,)),
        ElementTemplate(element_type=ElementType.SQUAD,
                        unit_type=UnitType.INFANTRY, hp_max=10,
                        weapons=(RIFLE_W,)),
        CARRIER_ELEM),
    optics_ground_cm=120000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.WHEEL)
TRUCK_TPL = UnitTemplate(                      # 牵引/烟幕卡车（TOW|TRANSPORT 双位+2 发烟幕）
    template_id=932, name="tow truck", category=4, cost=40,
    element_templates=(ElementTemplate(
        element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=12,
        self_smoke_charges=2),),
    optics_ground_cm=80000, stealth_base=4, speed_tier=3,
    movement_class=MovementClass.WHEEL,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.TOW) | (1 << Mode.TRANSPORT),
    tow_tonnage=5, own_weight_tons=3)
GARRISON_TPL = UnitTemplate(                   # 驻楼资格卡（CAN_GARRISON 位）
    template_id=933, name="garrison squad", category=1, cost=50,
    element_templates=(
        ElementTemplate(element_type=ElementType.SQUAD,
                        unit_type=UnitType.INFANTRY, hp_max=10,
                        weapons=(RIFLE_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_GARRISON)


class TestMountDismount(unittest.TestCase):
    def test_mount_then_request_pending(self):
        from sovs.sim.tick import consume_commands
        w = world_at(PHASE_COMBAT)
        add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (100000, 40000)))
        cands = deploy_free_candidates(w)
        mount = next(c for c in cands if c.kind == "mount")
        cmds = build_commands(w, w.players[0], mount)
        self.assertEqual(type(cmds[0]).__name__, "MountCmd")
        self.assertEqual(len(cmds[0].squad_elements), 2)   # 双班登车
        w.command_queue.extend(cmds)
        consume_commands(w)
        self.assertIsNotNone(w.mount_requests)             # 上车请求在途（200 拍）

    def test_dismount_when_foe_near(self):
        w = world_at(PHASE_COMBAT)
        u = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (100000, 40000)))
        u.elements[0].mounted_in = u.elements[2]          # 模拟已挂载
        foe = add_unit(w, make_unit(w, RIFLE_TPL, 1, 1, (100000, 48000)))
        foe.spotted_mask |= 1 << 0
        cands = deploy_free_candidates(w)
        dis = next(c for c in cands if c.kind == "dismount")
        cmds = build_commands(w, w.players[0], dis)
        self.assertEqual(type(cmds[0]).__name__, "DismountCmd")

    def test_no_mount_when_moving(self):
        w = world_at(PHASE_COMBAT)
        u = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (100000, 40000)))
        u.move_path = [(90000, 40000)]                    # 行进中不可上车
        self.assertFalse([c for c in deploy_free_candidates(w)
                          if c.kind == "mount"])


class TestTowChain(unittest.TestCase):
    def test_tow_when_far_then_untow_when_arrived(self):
        from sovs.sim.tick import consume_commands
        from tests.test_ai_kev import GUN_TPL
        w = world_at(PHASE_COMBAT)
        gun_u = add_unit(w, make_unit(w, GUN_TPL, 0, 0, (100000, 10000)))
        add_unit(w, make_unit(w, TRUCK_TPL, 0, 0, (100000, 10000)))
        cands = deploy_free_candidates(w)
        tow = next(c for c in cands if c.kind == "tow")   # 距敌锚 900m>600m→挂拖
        cmds = build_commands(w, w.players[0], tow)
        names = [type(c).__name__ for c in cmds]
        self.assertEqual(names, ["SetModeCmd", "TowCmd"])  # 先转 TOW 再挂
        w.command_queue.extend(cmds)
        consume_commands(w)
        self.assertEqual(len(w.tow_pairs), 1)             # 拖曳对成立
        # 到达前线（<=600m 且停稳）→ 解拖+重展开
        gun_u.pos = (100000, 90000)
        w.tow_pairs[0].towed_element.pos = (100000, 90000)
        cands = deploy_free_candidates(w)
        untow = next(c for c in cands if c.kind == "untow")
        cmds = build_commands(w, w.players[0], untow)
        self.assertEqual([type(c).__name__ for c in cmds],
                         ["UntowCmd", "DeployCmd"])
        w.command_queue.extend(cmds)
        consume_commands(w)
        self.assertEqual(len(w.tow_pairs), 0)

    def test_no_tow_without_tower_capability(self):
        from tests.test_ai_kev import GUN_TPL
        w = world_at(PHASE_COMBAT)
        add_unit(w, make_unit(w, GUN_TPL, 0, 0, (100000, 10000)))
        add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (100000, 10000)))  # 无 TOW 位
        self.assertFalse([c for c in deploy_free_candidates(w)
                          if c.kind == "tow"])


class TestGarrisonSmoke(unittest.TestCase):
    def test_garrison_roundtrip(self):
        from sovs.sim.tick import consume_commands
        from sovs.sim.types import Building
        w = world_at(PHASE_COMBAT)
        u = add_unit(w, make_unit(w, GARRISON_TPL, 0, 0, (100000, 50000)))
        w.buildings.append(Building(id=1, pos=(100000, 50000), hp=100,
                                    garrison_slots=2))
        cands = deploy_free_candidates(w)
        gar = next(c for c in cands if c.kind == "garrison")
        cmds = build_commands(w, w.players[0], gar)
        self.assertEqual(type(cmds[0]).__name__, "GarrisonCmd")
        w.command_queue.extend(cmds)
        consume_commands(w)
        self.assertIsNotNone(u.elements[0].garrison_in)    # 双向引用成立
        # 无敌情 → 撤出
        cands = deploy_free_candidates(w)
        ung = next(c for c in cands if c.kind == "ungarrison")
        w.command_queue.extend(build_commands(w, w.players[0], ung))
        consume_commands(w)
        self.assertIsNone(u.elements[0].garrison_in)

    def test_smoke_gates_and_expenditure(self):
        from sovs.sim.tick import consume_commands
        w = world_at(PHASE_COMBAT)
        u = add_unit(w, make_unit(w, TRUCK_TPL, 0, 0, (100000, 40000)))
        u.elements[0].suppression = 5                     # 受压 → 施放
        cands = deploy_free_candidates(w)
        smoke = next(c for c in cands if c.kind == "smoke")
        self.assertEqual(smoke.utility, 35)
        w.command_queue.extend(build_commands(w, w.players[0], smoke))
        consume_commands(w)
        self.assertEqual(u.elements[0].self_smoke_left, 1)   # 耗 1 发
        # 在途守卫+冷却门：落烟前/冷却内不可连发（即刻无候选）
        self.assertFalse([c for c in deploy_free_candidates(w)
                          if c.kind == "smoke"])
        w.tick += CONFIG.self_smoke_cooldown_ticks + 1       # 冷却过后可再放
        u.elements[0].self_smoke_pop_tick = -1
        self.assertTrue([c for c in deploy_free_candidates(w)
                         if c.kind == "smoke"])               # 受压档仍在（utility 35）
        u.elements[0].self_smoke_left = 0                    # 发数尽 → 无候选
        self.assertFalse([c for c in deploy_free_candidates(w)
                          if c.kind == "smoke"])


class TestAltitudeMicro(unittest.TestCase):
    def test_fighter_climbs_to_ceiling(self):
        from sovs.sim.tick import consume_commands
        from sovs.sim.types import AltTier
        w = world_at(PHASE_COMBAT)
        a = mk_aircraft(w, "YAK9", ammo={"STRAFE": 16})
        a.alt_tier = AltTier.LOW                           # 高度层微操起点
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        climb = next(c for c in cands if c.kind == "air_alt")
        cmds = build_commands(w, w.players[0], climb)
        self.assertEqual(type(cmds[0]).__name__, "AirAltCmd")
        w.command_queue.extend(cmds)
        consume_commands(w)
        self.assertIsNotNone(a.alt_pending)               # 过渡在途
        # 已在 ceiling → 不再生成
        a.alt_pending = None
        a.alt_tier = a.template.alt_ceiling
        self.assertFalse([c for c in air_candidates(w, 0, enemy_anchor=NORTH)
                          if c.kind == "air_alt"])


def deploy_free_candidates(w):
    """地面候选便捷口（issued 全空——单拍视角）。"""
    from sovs.ai import enumerate_candidates
    return enumerate_candidates(w, 0, artillery_issued=set(),
                                enemy_anchor=NORTH)


# ── 次要令（v4：冲刺/转向/姿态/取消族/狙击掩护/买补给/信标/转场/脱离）──

INFIL_TPL = UnitTemplate(                   # 渗透+信标位卡（旗位合成承载）
    template_id=941, name="infiltrators", category=0, cost=40,
    element_templates=(
        ElementTemplate(element_type=ElementType.SQUAD,
                        unit_type=UnitType.INFANTRY, hp_max=8,
                        weapons=(RIFLE_W,)),),
    optics_ground_cm=100000, stealth_base=9, speed_tier=1,
    movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_INFILTRATE | UnitFlag.CAN_AIRDROP_BEACON)
SNIPER_TPL = UnitTemplate(                  # 反狙击掩护位卡（现役 0 卡置位）
    template_id=942, name="sniper team", category=0, cost=30,
    element_templates=(
        ElementTemplate(element_type=ElementType.SQUAD,
                        unit_type=UnitType.INFANTRY, hp_max=4,
                        weapons=(RIFLE_W,)),),
    optics_ground_cm=130000, stealth_base=8, speed_tier=1,
    movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_SNIPER_COVER)
SUPPLY_TPL = UnitTemplate(                  # HAS_SUPPLY 位补给卡（CARGO|TRANSPORT 模式）
    template_id=943, name="supply truck", category=4, cost=45,
    element_templates=(ElementTemplate(
        element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=12,
        cargo_rounds_max=600, cargo_medical_max=40,
        cargo_weight_max=800),),
    optics_ground_cm=80000, stealth_base=4, speed_tier=3,
    movement_class=MovementClass.WHEEL,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.CARGO) | (1 << Mode.TRANSPORT),
    flags=UnitFlag.HAS_SUPPLY)


class TestMinorGroundOrders(unittest.TestCase):
    def _w_with_foe(self):
        w = world_at(PHASE_COMBAT)
        foe = add_unit(w, make_unit(w, RIFLE_TPL, 1, 1, (100000, 60000)))
        foe.spotted_mask |= 1 << 0
        return w

    def test_sprint_breaks_suppression_with_cooldown(self):
        from sovs.sim.tick import consume_commands
        w = self._w_with_foe()
        u = add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (100000, 50000)))
        u.elements[0].suppression = 6
        cands = deploy_free_candidates(w)
        sprint = next(c for c in cands if c.kind == "sprint")
        w.command_queue.extend(build_commands(w, w.players[0], sprint))
        consume_commands(w)
        self.assertEqual(u.elements[0].suppression, 3)   # 破压减半（5000bp）
        self.assertFalse([c for c in deploy_free_candidates(w)
                          if c.kind == "sprint"])        # 冷却窗内无候选

    def test_pivot_faces_threat(self):
        from sovs.sim.tick import consume_commands
        w = self._w_with_foe()
        u = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (100000, 50000)))  # 有甲
        cands = deploy_free_candidates(w)
        pivot = next(c for c in cands if c.kind == "pivot")
        self.assertEqual(pivot.params["facing"], 90)     # 正北（威胁 1km 外）
        w.command_queue.extend(build_commands(w, w.players[0], pivot))
        consume_commands(w)
        self.assertEqual(u.pivot_to, 90)

    def test_stance_hold_and_free(self):
        from sovs.sim.tick import consume_commands
        from sovs.sim.types import Stance as St
        w = world_at(PHASE_COMBAT)                        # 无可见敌→渗透禁火
        u = add_unit(w, make_unit(w, INFIL_TPL, 0, 0, (100000, 30000)))
        u.infiltration_timer = 300
        cands = deploy_free_candidates(w)
        hold = next(c for c in cands if c.kind == "stance")
        self.assertEqual(hold.params["stance"], "HOLD_FIRE")
        w.command_queue.extend(build_commands(w, w.players[0], hold))
        consume_commands(w)
        self.assertIs(u.stance, St.HOLD_FIRE)
        foe = add_unit(w, make_unit(w, RIFLE_TPL, 1, 1, (100000, 40000)))
        foe.spotted_mask |= 1 << 0                        # 敌近→恢复自由射击
        free = next(c for c in deploy_free_candidates(w) if c.kind == "stance")
        self.assertEqual(free.params["stance"], "WEAPONS_FREE")

    def test_cancel_family(self):
        from sovs.sim.tick import consume_commands
        from sovs.sim.types import FireMission, FireMissionForm
        w = world_at(PHASE_COMBAT)
        u = add_unit(w, make_unit(w, GUN_TPL, 0, 0, (100000, 30000)))
        u.fire_mission = FireMission(form=FireMissionForm.POINT)
        u.command_queue = ["stub"]                        # 排队令在链
        cands = deploy_free_candidates(w)
        kinds = {c.kind for c in cands}
        self.assertIn("cancel_all", kinds)
        self.assertIn("cancel_fm", kinds)
        cand = next(c for c in cands if c.kind == "cancel_all")
        w.command_queue.clear()                           # 引擎队列清空后落令
        w.command_queue.extend(build_commands(w, w.players[0], cand))
        consume_commands(w)
        self.assertEqual(u.command_queue, [])
        self.assertIsNone(u.fire_mission)                 # CancelCmd 全清语义

    def test_sniper_cover_flags_target(self):
        from sovs.sim.tick import consume_commands
        w = world_at(PHASE_COMBAT)
        add_unit(w, make_unit(w, SNIPER_TPL, 0, 0, (100000, 30000)))
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (100000, 35000)))
        cands = deploy_free_candidates(w)
        cover = next(c for c in cands if c.kind == "sniper_cover")
        self.assertEqual(cover.params["target_unit_id"], tank.id)  # 最高价值
        w.command_queue.extend(build_commands(w, w.players[0], cover))
        consume_commands(w)
        self.assertIn(tank.id, w.cover_by_target)

    def test_buy_supplies_loads_capacity(self):
        from sovs.sim.tick import consume_commands
        from sovs.sim.types import Mode as M
        w = world_at(PHASE_COMBAT)
        u = add_unit(w, make_unit(w, SUPPLY_TPL, 0, 0, (100000, 30000)))
        cands = deploy_free_candidates(w)
        buy = next(c for c in cands if c.kind == "buy_supplies")
        self.assertEqual(buy.params["rounds"], 600)       # 600g 恰满 800 载重
        self.assertEqual(buy.params["medical"], 40)       # 600+40×5=800 恰满
        w.command_queue.extend(build_commands(w, w.players[0], buy))
        consume_commands(w)
        el = u.elements[0]
        self.assertIs(el.mode, M.CARGO)                   # 先转 CARGO 再装
        self.assertEqual(el.supply_weight_g, 800)

    def test_beacon_dead_path_alive_for_flagged_cards(self):
        from sovs.sim.tick import consume_commands
        w = world_at(PHASE_COMBAT)
        add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (100000, 30000)))  # 无旗位
        self.assertFalse([c for c in deploy_free_candidates(w)
                          if c.kind == "beacon"])         # 无旗→不生成
        add_unit(w, make_unit(w, INFIL_TPL, 0, 0, (110000, 30000)))
        cand = next(c for c in deploy_free_candidates(w) if c.kind == "beacon")
        self.assertEqual(cand.params["pos"], [100000, 50000])  # 落点=无主占点
        w.command_queue.extend(build_commands(w, w.players[0], cand))
        consume_commands(w)
        # 引擎门对现役卡恒 REJECT——旗位卡按 cmd_set_airdrop_beacon 实测为准

    def test_ferry_removed_and_disengage(self):
        w = world_at(PHASE_COMBAT)
        a = mk_aircraft(w, "LI2", cargo=PARA_TPL, ammo={})
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        # ferry/air_move 转场候选已裁撤（模型陷阱——实测 0.5B 97% 锁死转场
        # 永不投放；AirAirdropCmd 自带飞行，转场冗余）
        self.assertFalse([c for c in cands if c.kind == "air_move"])
        self.assertTrue([c for c in cands if c.kind == "airdrop"])  # 投放仍在
        # 缠斗中 → 脱离候选（战力劣势档）
        b = mk_aircraft(w, "FW190A", state=AirState.DOGFIGHT, pos=(90000, 50000))
        a.state = AirState.DOGFIGHT
        from types import SimpleNamespace
        a.dogfight = SimpleNamespace(opponent=b)
        cands = air_candidates(w, 0, enemy_anchor=NORTH)
        brk = next(c for c in cands if c.kind == "air_disengage")
        self.assertEqual(brk.utility, 22)                 # YAK9<FW190A 战力
        self.assertEqual(type(build_commands(w, w.players[0], brk)[0]).__name__,
                         "AirDisengageCmd")


# ── 态势摘要空军段 ──

class TestAirStateView(unittest.TestCase):
    def test_brief_has_air_and_reserve_sections(self):
        w = world_at(PHASE_COMBAT)
        w.players[0].deck_slots.append(DeckSlot(PARA_TPL, 2))
        mk_aircraft(w, "YAK9", ammo={"STRAFE": 16})
        brief = situation_brief(w, 0)
        self.assertEqual(brief["空军"]["在空架数"], 1)
        self.assertEqual(brief["空军"]["飞机"][0]["扫射弹"], 16)
        self.assertEqual(brief["预备队"]["空降卡余份"], 2)


if __name__ == "__main__":
    unittest.main()
