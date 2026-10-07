"""登记项 7/8（2026-10-02 ⑥块）：system_timers 的 EMPTY→await_resupply 登记
（§F8 :1458-1459 方案19）+ World.spawn_paratroop / spawn_airdrop_crate 真实现
（AIR §F6 :610-619 空降回调 / §F6 :1343-1354 一次性 CARGO 补给箱——方案16）。
锚点全部手推写死（补弹 2 发/tick、空降卡满编数据、箱模板硬要求位、方形散布界），
不自证；零掷骰断言=八通道 PCG32 state 快照对比（spawn/timers 路径全通道不动，
resolve_airdrop e2e 仅 AIR 通道动——通道纪律）。"""
import unittest
from pathlib import Path

from sovs.sim import card_loader as cl
from sovs.sim.air import (AirRole, AirState, AircraftInstance, AircraftTemplate,
                          PHASE_DEPLOY, airdrop_scatter_cm, cmd_air_airdrop,
                          resolve_airdrop)
from sovs.sim.combat import apply_damage
from sovs.sim.movement import system_move
from sovs.sim.tables import CONFIG
from sovs.sim.tick import (DeckSlot, add_unit, ground_unit_score, make_unit,
                           make_world, system_supply, system_timers, world_tick)
from sovs.sim.types import (AltTier, ElementTemplate, ElementType, Mode,
                            MovementClass, UnitFlag, UnitTemplate, UnitType,
                            WeaponTemplate, WState)

REPO_ROOT = Path(__file__).resolve().parents[1]
GEN_LIBRARY = REPO_ROOT / "data" / "gen" / "cards_ground.v1.json"

_LIB = None


def library():
    """卡库惰性加载（data/gen 首批产物——空降两卡在库）。"""
    global _LIB
    if _LIB is None:
        _LIB = cl.load_library(GEN_LIBRARY)
    return _LIB


def channels(w):
    """八通道 PCG32 内部 state 快照（test_integration.fingerprint 同源口径）。"""
    return [r.state for r in w.rng._rngs]


# ── 合成模板（测试用，不对应真实卡；test_supply_mount 同款）──
RIFLE = WeaponTemplate(name="RIFLE", damage=1, max_range_cm=10000, ammo_base=10)
RIFLE_SQUAD = ElementTemplate(element_type=ElementType.SQUAD,
                              unit_type=UnitType.INFANTRY, hp_max=10,
                              weapons=(RIFLE,))
INF_TPL = UnitTemplate(
    template_id=401, name="rifle squad", category=1, cost=20,
    element_templates=(RIFLE_SQUAD,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)
INFIL_TPL = UnitTemplate(                    # 渗透位卡（spawn :1393 按相位置消费端）
    template_id=402, name="infiltrator squad", category=1, cost=20,
    element_templates=(RIFLE_SQUAD,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_INFILTRATE)


class TestTimersEmptyRegistration(unittest.TestCase):
    """§F8 :1456-1459 方案19：RELOADING 迁移落 EMPTY 即登记 await_resupply。"""

    def test_reloading_to_empty_registers(self):
        # timer 1→0 迁移、ammo=0 → EMPTY 且 u 入表；零掷骰（八通道不动）
        w = make_world(42)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        ws = u.elements[0].weapon_states[0]
        ws.ammo_left = 0
        ws.state = WState.RELOADING
        ws.timer = 1
        before = channels(w)
        system_timers(w)
        self.assertIs(ws.state, WState.EMPTY)
        self.assertEqual(w.await_resupply, [u])
        self.assertEqual(channels(w), before)

    def test_no_double_registration(self):
        # :1458 门（u NOT IN 才 append）：已登记不重复入表
        w = make_world(7)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        ws = u.elements[0].weapon_states[0]
        ws.ammo_left = 0
        ws.state = WState.RELOADING
        ws.timer = 1
        w.await_resupply.append(u)
        system_timers(w)
        self.assertIs(ws.state, WState.EMPTY)
        self.assertEqual(w.await_resupply, [u])           # 仍恰一条

    def test_reloading_to_ready_not_registered(self):
        # ammo>0 → READY：不登记（:1458 只对 EMPTY）
        w = make_world(9)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        ws = u.elements[0].weapon_states[0]
        ws.ammo_left = 5
        ws.state = WState.RELOADING
        ws.timer = 1
        system_timers(w)
        self.assertIs(ws.state, WState.READY)
        self.assertEqual(w.await_resupply, [])

    def test_dead_unit_skipped(self):
        # system_timers 逐单位 alive 门：亡者武器不迁移、不入表
        w = make_world(11)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        ws = u.elements[0].weapon_states[0]
        ws.ammo_left = 0
        ws.state = WState.RELOADING
        ws.timer = 1
        u.alive = False
        system_timers(w)
        self.assertIs(ws.state, WState.RELOADING)         # 整单位跳过
        self.assertEqual(w.await_resupply, [])


class TestSpawnParatroop(unittest.TestCase):
    """AIR §F6 :610-619：落地 instantiate=make_unit+add_unit（AMB3-06 同构）。"""

    def test_su_card_instantiation(self):
        # data/gen 实卡（SU_PARATROOP）：3 班×10HP、PPSh-41 满编 213 发；
        # PB-31 拍板（2026-10-03）：卡带 CAN_INFILTRATE——实战相位 spawn 置 600
        # （盲部署期置 0 见 spawn_step :1393 同款判据）；零掷骰
        tpl = library()["SU_PARATROOP"].unit_template
        w = make_world(7)                                # 默认 COMBAT 相位
        before = channels(w)
        w.spawn_paratroop(tpl, 1, 1, (123456, 654321))
        self.assertEqual(len(w.units), 1)
        u = w.units[0]
        self.assertIs(u.template, tpl)
        self.assertEqual((u.id, u.team, u.pos), (1, 1, (123456, 654321)))
        self.assertTrue(u.alive)
        self.assertEqual(len(u.elements), 3)              # count 3 展开
        for e in u.elements:
            self.assertEqual(e.hp_current, 10)            # hp_max=10 满编
            self.assertEqual(len(e.weapon_states), 1)
            self.assertEqual(e.weapon_states[0].ammo_left, 213)   # PPSh-41 ammo_base
        self.assertNotIn(u, w.aa_roster)                  # GROUND 武器+optics_air=0（:1353 同判）
        self.assertEqual(u.infiltration_timer, 600)       # 渗透卡实战落地置 600
        self.assertEqual(channels(w), before)             # 零掷骰

    def test_ger_card_two_weapons(self):
        # GER_PARATROOP：3 班×双武器（K98 200 / MP40 96）
        tpl = library()["GER_PARATROOP"].unit_template
        w = make_world(3)
        w.spawn_paratroop(tpl, 1, 1, (0, 0))
        u = w.units[0]
        self.assertEqual(len(u.elements), 3)
        for e in u.elements:
            self.assertEqual([x.ammo_left for x in e.weapon_states], [200, 96])

    def test_infiltration_by_phase(self):
        # spawn_step :1393 同款：canInfiltrate 卡按相位置（实战 600/其余 0）
        w1 = make_world(9)                                # 默认 phase=COMBAT
        w1.spawn_paratroop(INFIL_TPL, 0, 0, (0, 0))
        self.assertEqual(w1.units[0].infiltration_timer, CONFIG.infiltration_ticks)
        w2 = make_world(9, phase=PHASE_DEPLOY)
        w2.spawn_paratroop(INFIL_TPL, 0, 0, (0, 0))
        self.assertEqual(w2.units[0].infiltration_timer, 0)

    def test_deck_copies_not_touched(self):
        # deck 份装机时已扣（B-06/B-12）——落地不重扣
        tpl = library()["GER_PARATROOP"].unit_template
        w = make_world(11)
        p = w.players[1]
        p.deck_slots.append(DeckSlot(template=tpl, copies_left=1))
        w.spawn_paratroop(tpl, 1, 1, (0, 0))
        self.assertEqual(p.deck_slots[0].copies_left, 1)


class TestSpawnAirdropCrate(unittest.TestCase):
    """§F6 :1343-1354 方案16：一次性 CARGO 补给单位（模板硬要求+拾取链+销毁）。"""

    def test_crate_instantiation_spec(self):
        # :1344-1350 硬要求逐条：speed_tier=0/无武器/仅 hasSupply 位/radius 8000/
        # mode=CARGO+物资预填；aa_roster 天然不入；零掷骰
        w = make_world(3)
        before = channels(w)
        w.spawn_airdrop_crate(0, (400000, 400000), 120)   # 一池重量 120g（原 100 弹+20 医）
        self.assertEqual(len(w.units), 1)
        u = w.units[0]
        e = u.elements[0]
        self.assertEqual((u.team, u.pos), (0, (400000, 400000)))
        self.assertIs(e.mode, Mode.CARGO)
        self.assertEqual(e.supply_weight_g, 120)
        self.assertEqual(u.template.speed_tier, 0)
        self.assertEqual(CONFIG.speed_cm_tick(0), 0)      # §D.0 速度表 [0]=0
        self.assertEqual(u.template.flags, UnitFlag.HAS_SUPPLY)   # 仅此一位（GAP-21）
        self.assertEqual(u.template.supply_radius_cm, 8000)       # :1349 数据硬要求
        self.assertEqual(e.hp_current, CONFIG.airdrop_crate_hp)
        self.assertEqual(e.weapon_states, [])                     # 无行为
        self.assertEqual(u.move_path, [])
        self.assertNotIn(u, w.aa_roster)
        self.assertEqual(channels(w), before)             # 零掷骰

    def test_crate_immobile_under_move_order(self):
        # speed_tier=0 → v=0：即便塞入路径也不位移（不可移动）
        w = make_world(5)
        w.spawn_airdrop_crate(0, (400000, 400000), 1)
        u = w.units[0]
        u.move_path = [(450000, 400000)]
        system_move(CONFIG, u, 1)
        self.assertEqual(u.pos, (400000, 400000))
        self.assertEqual(u.move_path, [(450000, 400000)])  # 路径未耗

    def test_pickup_chain_from_timers_registration(self):
        # 登记项7 写点 → ⑥ CARGO 分支拾取闭环：RELOADING→EMPTY 登记 →
        # system_supply take=MIN(10−0, 120//1, 2)=2、EMPTY 有弹转 READY、箱扣 2g
        w = make_world(42)
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (404000, 400000)))  # dist 4000 ≤ 8000
        ws = inf.elements[0].weapon_states[0]
        ws.ammo_left = 0
        ws.state = WState.RELOADING
        ws.timer = 1
        w.spawn_airdrop_crate(0, (400000, 400000), 120)
        system_timers(w)
        self.assertIs(ws.state, WState.EMPTY)
        self.assertEqual(w.await_resupply, [inf])
        system_supply(w)
        self.assertEqual(ws.ammo_left, 2)
        self.assertIs(ws.state, WState.READY)
        self.assertEqual(w.units[-1].elements[0].supply_weight_g, 118)
        self.assertEqual(w.await_resupply, [inf])          # 2<10 缺口仍在

    def test_enemy_cannot_pickup(self):
        # R-21 同队门（GDD-02 修正）：敌队待补单位贴箱同点位亦不得拾取
        w = make_world(5)
        enemy = add_unit(w, make_unit(w, INF_TPL, 1, 1, (400000, 400000)))
        ws = enemy.elements[0].weapon_states[0]
        ws.ammo_left = 0
        ws.state = WState.EMPTY
        w.await_resupply.append(enemy)
        w.spawn_airdrop_crate(0, (400000, 400000), 120)
        system_supply(w)
        self.assertEqual(ws.ammo_left, 0)
        self.assertEqual(w.units[-1].elements[0].supply_weight_g, 120)
        self.assertEqual(w.await_resupply, [enemy])

    def test_crate_destroy_cascade_and_score(self):
        # 可摧毁：任一命中即毁（占位 hp=1）→ destroy_element 常规级联（物资随毁）；
        # cost=0 → D031 剩余地面单位分值不计箱；尸体清扫出表
        w = make_world(13)
        w.spawn_airdrop_crate(0, (400000, 400000), 120)
        u = w.units[0]
        self.assertEqual(ground_unit_score(w, 0), 0)
        e = u.elements[0]
        before = channels(w)
        apply_damage(w, e, CONFIG.airdrop_crate_hp)
        self.assertFalse(u.alive)
        self.assertEqual(u.elements, [])
        world_tick(w)                                     # :1439 尸体清扫
        self.assertEqual(w.units, [])
        self.assertEqual(channels(w), before)             # 全链零掷骰


def atpl(paratroop_seats: int) -> AircraftTemplate:
    """测试用运输机模板（test_air_behavior.tpl 同款口径）。"""
    return AircraftTemplate(
        template_id=901, name="transport", role=AirRole.TRANSPORT, cost_body=70,
        hp_max=30, armor_aa=4, speed_cm_tick=100, dogfight_power=10, maneuver=8,
        alt_ceiling=AltTier.HIGH, payload_max_supply=600,
        paratroop_seats=paratroop_seats, payload_price={})


def ainst(w, t: AircraftTemplate, team: int = 0) -> AircraftInstance:
    a = AircraftInstance(id=w.next_aircraft_id, team=team, player_index=team,
                         template=t, pos=(500000, 500000), alt_tier=AltTier.MID,
                         hp_current=t.hp_max, state=AirState.PATROL)
    w.next_aircraft_id += 1
    a.ammo_left = {"BOMB": 0, "STRAFE": 0, "SUPPLY": 0}
    w.aircraft.append(a)
    return a


class TestResolveAirdropGroundSpawn(unittest.TestCase):
    """air.py resolve_airdrop → 真 World 两回调端到端（契约④/D017）。"""

    def test_paratroop_drop_spawns_ground_unit(self):
        # 空降支：落地即地面一命单位（SU 卡 3 班）、cargo 清空、投放费扣 5；
        # 方形散布界 land=drop+(sym(R),sym(R))——每轴 |Δ|≤R（MID 档 R=3600）
        tpl = library()["SU_PARATROOP"].unit_template
        w = make_world(13)
        a = ainst(w, atpl(1))
        a.paratroop_cargo = tpl
        self.assertTrue(cmd_air_airdrop(w, a, (600000, 500000)))
        before_pts = w.players[0].air_points
        before = channels(w)
        resolve_airdrop(w, a, a.task)
        self.assertIsNone(a.paratroop_cargo)
        self.assertEqual(w.players[0].air_points,
                         before_pts - CONFIG.airdrop_fee_points)
        self.assertEqual(len(w.units), 1)
        u = w.units[0]
        self.assertIs(u.template, tpl)
        self.assertEqual(u.team, 0)
        self.assertTrue(u.alive)
        self.assertEqual(len(u.elements), 3)
        r = airdrop_scatter_cm(CONFIG, a.alt_tier, a.template.speed_cm_tick)
        self.assertEqual(r, 3600)                         # 3000×12000//10000×100//100
        self.assertLessEqual(abs(u.pos[0] - 600000), r)
        self.assertLessEqual(abs(u.pos[1] - 500000), r)
        after = channels(w)
        self.assertNotEqual(after[7], before[7])          # AIR 通道被消费（两轴散布）
        self.assertEqual(after[:7], before[:7])           # 地面七通道不动

    def test_supply_drop_spawns_crate(self):
        # 补给支：单点整箱投 → CARGO 箱单位入 units、一池重量预填、机载弹药清零
        w = make_world(3)
        a = ainst(w, atpl(0))
        a.ammo_left["SUPPLY"] = 75                       # 机载一池重量 75g
        self.assertTrue(cmd_air_airdrop(w, a, (600000, 500000)))
        resolve_airdrop(w, a, a.task)
        self.assertEqual(a.ammo_left["SUPPLY"], 0)
        self.assertEqual(len(w.units), 1)
        e = w.units[0].elements[0]
        self.assertIs(e.mode, Mode.CARGO)
        self.assertEqual(e.supply_weight_g, 75)
        self.assertEqual(w.units[0].template.supply_radius_cm, 8000)


if __name__ == "__main__":
    unittest.main()
