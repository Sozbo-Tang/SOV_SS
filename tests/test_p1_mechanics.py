"""P1 机制块锚点测试（2026-10-13，GP-01 断箭手册 P1 补建）。

覆盖面（逐条对位手册原文——manual.txt/basics 行号见各断言注）：
- 地面 RTB（manual.txt:394-400）：B 快移出生点→到场消失退款（损伤/耗弹扣减、
  ≥20% 下限——basics:179-180；舱载连带退款——basics:399；卡组份不回补=一命制
  拍板优先，头注留痕 tick.GroundRTBCmd）；E 撤令清在途位。
- 激光照射 N（manual.txt:517-522）：跟随目标/断 LOS 失效/照射者亡注销；
  PRECISION 第三弹药位（manual.txt:456-458）：无激光位拒、有激光位落点吸附。
- 雷达 Z（manual.txt:534-539、basics:327-335）：资格门/5s 启动/即刻关/
  对空探测与射程增幅（高空×2——basics:328-329）。
- 诱饵 C（manual.txt:505-509）：手动投放/发数门/规避窗；fire_aa 来袭事件
  自动投放（manual.txt:507-508）；被动对策乘区（basics:353-356）。
- 加力 Z（manual.txt:492-497）：toggle/速度×2/油耗×2/无资格拒；
  燃油耗尽被迫弹射（basics:312-314——air_downed 同链）。
- 低空 V（manual.txt:421-428）：两态 toggle（UI 侧）/低空降速/按角色出场
  高度（fighters high）。
- 空投逐一跳伞（manual.txt:430-433）：多份装载逐 stick 投放/费一次；
  无令货机自动空投（manual.txt:434-440）。
- 补给堆（basics:198-213）：四开关实门/任何命中即爆（basics:206-207）。
- 战中呼援（basics:165-168）：实战期 PurchaseCmd 放行。
- UI 键位：B 双通道/Z 按单位分派/C 诱饵/N·L·M·P 待令组/TAB 焦点过滤
  （basics:59-60——只对焦点下令不散选区）。
wire 编解码互逆/AST 闭合清单在 tests/test_wire.py（41 类）；黄金回放随
wire 1.3 重录（tools/record_golden.py）。
"""
import unittest

from sovs.sim.air import (AirRole, AirState, AircraftTemplate, TaskKind,
                          aircraft_move_step, cmd_air_afterburner,
                          cmd_air_call, cmd_air_decoy, entry_tier,
                          missile_warning, resolve_airdrop)
from sovs.sim.air_data import LI2, YAK9
from sovs.sim.combat import apply_damage
from sovs.sim.tables import CONFIG, BalanceConfig
from sovs.sim.tick import (AirAfterburnerCmd, AirDecoyCmd, GroundRTBCmd,
                           LaserDesignateCmd, RadarCmd, SupplySwitchCmd,
                           add_unit, cmd_ground_rtb, cmd_laser_designate,
                           cmd_purchase, cmd_radar, cmd_supply_switch,
                           consume_commands, ground_recovery, laser_marks_of,
                           make_unit, make_world, queue_command, radar_active,
                           unit_refund_points, world_tick)
from sovs.sim.types import (AltTier, DamageType, ElementTemplate, ElementType,
                            Mode, MovementClass, TargetDomain, Trajectory,
                            UnitFlag, UnitTemplate, UnitType, WeaponTemplate)
from sovs.ui.shell_fsm import ShellFsm

# ── 合成模板（测试专用，不对应真实卡——test_self_smoke 59x 段后继 60x）──


def _truck_tpl(cost=50, flags=0):
    return UnitTemplate(
        template_id=601, name="p1 truck", category=4, cost=cost,
        element_templates=(ElementTemplate(
            element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
            hp_max=20, cargo_rounds_max=600, cargo_medical_max=120,
            cargo_weight_max=600,
            weapons=(WeaponTemplate(name="p1 truck mg", damage=1,
                                    max_range_cm=10000, ammo_base=100,
                                    salvo=1),),),),
        optics_ground_cm=10000, stealth_base=5, speed_tier=3,
        movement_class=MovementClass.WHEEL, flags=flags,
        mode_set=(1 << Mode.DIRECT) | (1 << Mode.CARGO))


def _rifle_tpl(flags=0):
    return UnitTemplate(
        template_id=602, name="p1 rifle", category=1, cost=30, flags=flags,
        element_templates=(ElementTemplate(
            element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
            hp_max=10, weapons=(WeaponTemplate(
                name="p1 rifle gun", damage=2, max_range_cm=30000,
                ammo_base=100, ammo_weight=1, salvo=1),),),),
        optics_ground_cm=30000, stealth_base=5, speed_tier=1,
        movement_class=MovementClass.FOOT)


def _sniper_tpl():
    return UnitTemplate(
        template_id=603, name="p1 sniper", category=0, cost=15,
        flags=UnitFlag.CAN_SNIPER_COVER,
        element_templates=(ElementTemplate(
            element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
            hp_max=4, weapons=(WeaponTemplate(
                name="p1 mosin", damage=5, max_range_cm=40000,
                ammo_base=40, combat_style=2, salvo=1),),),),
        optics_ground_cm=50000, stealth_base=10, speed_tier=1,
        movement_class=MovementClass.FOOT)


def _gun_tpl():
    return UnitTemplate(
        template_id=604, name="p1 gun", category=3, cost=70,
        element_templates=(ElementTemplate(
            element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=8,
            weapons=(WeaponTemplate(
                name="p1 howitzer", damage=30, max_range_cm=100000,
                blast_radius_cm=2500, ammo_base=60, salvo=2,
                trajectory=Trajectory.BALLISTIC,
                damage_type=DamageType.HE, dispersion_cm=2000,
                projectile_speed_cm_tick=2000),),),),
        optics_ground_cm=30000, stealth_base=5, speed_tier=1,
        movement_class=MovementClass.WHEEL,
        mode_set=(1 << Mode.DIRECT) | (1 << Mode.INDIRECT))


def _aa_tpl(optics_air=10000, rng=10000, acc_bp=8000):
    return UnitTemplate(
        template_id=605, name="p1 aa", category=4, cost=60,
        element_templates=(ElementTemplate(
            element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
            hp_max=10, weapons=(WeaponTemplate(
                name="p1 flak", damage=6, max_range_cm=rng,
                target_mask=TargetDomain.AIR | TargetDomain.GROUND,
                ammo_base=200, salvo=1, damage_type=DamageType.HE,
                accuracy_base_bp=acc_bp,
                projectile_speed_cm_tick=4000),),),),
        optics_ground_cm=10000, stealth_base=5, speed_tier=2,
        movement_class=MovementClass.WHEEL, optics_air_cm=optics_air,
        air_ceiling=AltTier.HIGH)


def _air_tpl(**kw):
    d = dict(template_id=690, name="P1T", role=AirRole.FIGHTER, cost_body=60,
             hp_max=60, armor_aa=4, speed_cm_tick=100, dogfight_power=5,
             maneuver=6, alt_ceiling=AltTier.HIGH, weapons=(),
             payload_max_bombs=0, payload_price={})
    d.update(kw)
    return AircraftTemplate(**d)


def _mk_air(w, tpl, team=0, alt=AltTier.MID, pos=(500000, 500000)):
    from sovs.sim.air import AircraftInstance
    a = AircraftInstance(id=w.next_aircraft_id, team=team, player_index=team,
                         template=tpl, pos=pos, alt_tier=alt,
                         hp_current=tpl.hp_max, state=AirState.PATROL)
    w.next_aircraft_id += 1
    a.fuel_ticks = CONFIG.air_fuel_ticks
    a.decoy_left = tpl.decoy_charges
    w.aircraft.append(a)
    return a


def _frame(phase="combat", tick=700, *, units=(), aircraft=(), team=0,
           players=(), rejections=(), refunds=()):
    return {"schema_version": "1.1", "tick": tick, "phase": phase, "view": team,
            "map_cm": [200000, 100000], "units": list(units),
            "aircraft": list(aircraft), "objectives": [], "players": list(players),
            "smoke_zones": [], "projectiles": [], "buildings": [],
            "rejections": list(rejections), "result": None,
            "refunds": list(refunds), "lasers": []}


def _funit(uid, team=0, x=0, y=0, **kw):
    entry = {"id": uid, "team": team, "pos_cm": [x, y], "hp": 10, "hp_max": 10,
             "category": 1, "name": "u%d" % uid, "stance": "weapons_free",
             "smoke_left": 0, "radar_on": False, "rtb": False,
             "supply_gates": {"share": True, "heal": True, "repair": True,
                              "ammo": True}}
    entry.update(kw)
    return entry


def _fair(aid, team=0, x=0, y=0, **kw):
    entry = {"id": aid, "team": team, "name": "a%d" % aid, "state": "patrol",
             "alt_tier": "mid", "pos_cm": [x, y], "facing": 90, "hp": 10,
             "hp_max": 10, "ammo": {"BOMB": 2}, "paratroop": None,
             "spotted": False, "engage_air": None, "task": None,
             "alt_pending": None, "afterburner": False, "fuel_pct": 100,
             "decoy_left": 2, "evade_active": False, "evade_pct": 0,
             "paratroop_count": 0}
    entry.update(kw)
    return entry


class _SpyCmd:
    """fsm 空令分发的调用面断言桩（calls=[(名, args, kwargs)]）。"""

    def __init__(self):
        self.calls = []

    def _log(self, name, *a, **kw):
        self.calls.append((name, a, kw))
        return [object()]

    def stop(self, ids):
        return self._log("stop", tuple(ids))

    def cancel(self, ids):
        return self._log("cancel", tuple(ids))

    def move(self, ids, dest, mode="NORMAL", queue=False):
        return self._log("move", tuple(ids), tuple(dest), mode=mode)

    def smoke(self, ids):
        return self._log("smoke", tuple(ids))

    def sprint(self, ids):
        return self._log("sprint", tuple(ids))

    def stance(self, ids, s):
        return self._log("stance", tuple(ids), s)

    def smoke_sprint_stance(self, ids, stance="HOLD_FIRE"):
        return self._log("smoke_sprint_stance", tuple(ids))

    def reverse(self, ids, dest):
        return self._log("reverse", tuple(ids), tuple(dest))

    def fire_mission(self, uid, point, **kw):
        return self._log("fire_mission", uid, tuple(point), **kw)

    def attack(self, uid, foe, queue=False):
        return self._log("attack", uid, foe, queue=queue)

    def sniper_cover(self, ids, foe):
        return self._log("sniper_cover", tuple(ids), foe)

    def supply_dock(self, ids, truck):
        return self._log("supply_dock", tuple(ids), truck)

    def mount(self, ids, carrier):
        return self._log("mount", tuple(ids), carrier)

    def laser_designate(self, ids, foe):
        return self._log("laser_designate", tuple(ids), foe)

    def ground_rtb(self, ids):
        return self._log("ground_rtb", tuple(ids))

    def radar(self, ids, engage):
        return self._log("radar", tuple(ids), engage=engage)

    def air_rtb(self, ids):
        return self._log("air_rtb", tuple(ids))

    def air_alt(self, ids, tier):
        return self._log("air_alt", tuple(ids), tier)

    def air_afterburner(self, ids, engage):
        return self._log("air_afterburner", tuple(ids), engage)

    def air_decoy(self, ids, action="POP"):
        return self._log("air_decoy", tuple(ids), action)


# ══════════════ ① 地面 RTB（B）══════════════

class TestGroundRTB(unittest.TestCase):

    def test_full_refund_on_arrival(self):
        # manual.txt:396-398：到场消失退款；basics:180 下限 20%；满血满弹=全额
        w = make_world(11)
        u = add_unit(w, make_unit(w, _truck_tpl(50), 0, 0, (500000, 50000)))
        pts0 = w.players[0].points
        self.assertTrue(cmd_ground_rtb(w, u))
        self.assertTrue(u.rtb_pending)
        for _ in range(4000):
            world_tick(w)
            if not u.alive:
                break
        self.assertFalse(u.alive)                       # 到场消失
        self.assertNotIn(u, w.units)
        self.assertEqual(w.players[0].points, pts0 + 50)  # 全额退款
        self.assertEqual(w.refund_log[-1]["amount"], 50)

    def test_damage_and_ammo_deductions_with_floor(self):
        # basics:179-180：按损伤与耗弹扣减；不低于原价 20%
        w = make_world(11)
        u = add_unit(w, make_unit(w, _truck_tpl(100), 0, 0, (500000, 50000)))
        for e in u.elements:                             # 损 50% 血
            e.hp_current = e.template.hp_max // 2
        self.assertEqual(unit_refund_points(u), 50)      # 100×(1−0.5)
        for e in u.elements:                             # 再耗尽一个 100 发弹舱
            e.weapon_states[0].ammo_left = 0
        # 等权折减：耗弹比例=1.0（唯一武器）→ 1−0.5−1.0<0 → 下限 20%
        self.assertEqual(unit_refund_points(u),
                         100 * CONFIG.rtb_refund_floor_permille // 10000)

    def test_cargo_units_refunded_too(self):
        # manual.txt:399-400：载具内单位与补给一并退款（跨卡舱载逐单位退）
        w = make_world(11)
        carrier = add_unit(w, make_unit(w, _truck_tpl(50), 0, 0, (500000, 50000)))
        cargo = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (500000, 50000)))
        carrier.elements[0].cargo_units = [cargo]        # 跨卡舱载
        pts0 = w.players[0].points
        total = ground_recovery(w, carrier)
        self.assertEqual(total, 50 + 30)                 # 本体+舱载
        self.assertEqual(w.players[0].points, pts0 + 80)
        self.assertFalse(cargo.alive)                    # 舱载连带消失

    def test_deck_copy_not_restored(self):
        # 一命制拍板优先（手册 hotkeys「recalled later」冲突留痕）——退款只入点数
        w = make_world(11)
        u = add_unit(w, make_unit(w, _truck_tpl(50), 0, 0, (100000, 50000)))
        ground_recovery(w, u)
        self.assertEqual(w.players[0].deck_slots, [])    # 无回补面

    def test_cancel_clears_rtb_pending(self):
        w = make_world(11)
        u = add_unit(w, make_unit(w, _truck_tpl(50), 0, 0, (500000, 50000)))
        cmd_ground_rtb(w, u)
        from sovs.sim.tick import CancelCmd
        queue_command(w, CancelCmd(unit=u))
        consume_commands(w)
        self.assertFalse(u.rtb_pending)                  # E=撤令留场
        self.assertTrue(u.alive)

    def test_fully_mounted_squad_rejected(self):
        w = make_world(11)
        u = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (500000, 50000)))
        u.elements[0].mounted_in = object()              # 整班车载
        self.assertFalse(cmd_ground_rtb(w, u))
        self.assertFalse(u.rtb_pending)


# ══════════════ ② 激光照射 N → 精密打击 P ══════════════

class TestLaserPrecision(unittest.TestCase):

    def _world(self):
        w = make_world(12)
        sniper = add_unit(w, make_unit(w, _sniper_tpl(), 0, 0, (100000, 40000)))
        foe = add_unit(w, make_unit(w, _rifle_tpl(), 1, 1, (100000, 70000)))
        return w, sniper, foe

    def test_designate_follow_and_los_break(self):
        # manual.txt:519-522：照射跟随目标、断 LOS 失效
        w, sniper, foe = self._world()
        self.assertTrue(cmd_laser_designate(w, sniper, foe))
        marks = laser_marks_of(w, 0)
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0][0], foe.pos)           # 跟随目标现位
        foe.pos = (100000, 200000)                       # 拉出 LOS（光学 50000）
        self.assertEqual(laser_marks_of(w, 0), [])       # 断 LOS→剪枝
        self.assertNotIn(sniper.id, w.laser_by_unit)

    def test_designator_death_unregisters(self):
        w, sniper, foe = self._world()
        cmd_laser_designate(w, sniper, foe)
        from sovs.sim.tick import unregister_unit_refs
        unregister_unit_refs(w, sniper)
        self.assertEqual(laser_marks_of(w, 0), [])

    def test_precision_gate_requires_laser(self):
        # manual.txt:456-458：Precision 命中 Fire Mission 区附近的激光位
        from sovs.sim.tick import cmd_fire_mission, cmd_cancel_fire_mission
        from sovs.sim.types import FireMissionForm
        w, sniper, foe = self._world()
        gun = add_unit(w, make_unit(w, _gun_tpl(), 0, 0, (100000, 30000)))
        from sovs.sim.tick import SetModeCmd
        queue_command(w, SetModeCmd(element=gun.elements[0],
                                    mode=Mode.INDIRECT))
        consume_commands(w)
        self.assertFalse(cmd_fire_mission(w, gun, FireMissionForm.POINT,
                                          foe.pos, 1, "PRECISION", None, 0))
        cmd_laser_designate(w, sniper, foe)
        self.assertTrue(cmd_fire_mission(w, gun, FireMissionForm.POINT,
                                         foe.pos, 1, "PRECISION", None, 0))
        self.assertEqual(gun.fire_mission.ammo, "PRECISION")

    def test_precision_shell_lands_on_laser(self):
        # 落点吸附激光位（紧散射 precision_scatter_bp×dispersion）
        from sovs.sim.tick import cmd_fire_mission
        from sovs.sim.types import FireMissionForm
        w, sniper, foe = self._world()
        gun = add_unit(w, make_unit(w, _gun_tpl(), 0, 0, (100000, 30000)))
        from sovs.sim.tick import SetModeCmd
        queue_command(w, SetModeCmd(element=gun.elements[0],
                                    mode=Mode.INDIRECT))
        consume_commands(w)
        cmd_laser_designate(w, sniper, foe)
        cmd_fire_mission(w, gun, FireMissionForm.POINT, foe.pos, 1,
                         "PRECISION", None, 0)
        from sovs.sim.tick import fire_at
        gun.elements[0].weapon_states[0].state = 0
        fire_at(w, gun.elements[0], gun.elements[0].weapon_states[0],
                gun.fire_mission)
        self.assertEqual(len(w.projectiles), 2)          # salvo 2
        for p in w.projectiles:
            d = abs(p.dest[0] - foe.pos[0]) + abs(p.dest[1] - foe.pos[1])
            self.assertLessEqual(d, 2 * (2000 * CONFIG.precision_scatter_bp
                                         // 10000) + 1)  # 双向散布上界


# ══════════════ ③ 雷达 Z ══════════════

class TestRadar(unittest.TestCase):

    def test_gate_spinup_and_off(self):
        # basics:334-335：5s 启动、即刻可关
        w = make_world(13)
        u = add_unit(w, make_unit(w, _aa_tpl(), 0, 0, (100000, 50000)))
        rifle = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (90000, 50000)))
        self.assertFalse(cmd_radar(w, rifle, True))      # 非对空资格拒
        self.assertTrue(cmd_radar(w, u, True))
        self.assertFalse(radar_active(u, w))             # 启动窗内未生效
        for _ in range(CONFIG.radar_spinup_ticks):
            world_tick(w)
        self.assertTrue(radar_active(u, w))
        cmd_radar(w, u, False)
        self.assertFalse(radar_active(u, w))             # 关=即刻

    def test_radar_doubles_air_detection(self):
        # basics:328-329：对高空探测 ×2（sense_air 名单支）
        from sovs.sim.sensing import sense_air
        w = make_world(13)
        u = add_unit(w, make_unit(w, _aa_tpl(optics_air=10000), 0, 0,
                                  (100000, 50000)))
        a = _mk_air(w, _air_tpl(), team=1, alt=AltTier.HIGH,
                    pos=(100000, 68000))                  # 距 18000>10000
        sense_air(CONFIG, w)
        self.assertEqual(a.spotted_mask, 0)               # 基础光学不可见
        u.radar_on = True
        u.radar_ready_tick = w.tick                      # 越过启动窗
        sense_air(CONFIG, w)
        self.assertEqual(a.spotted_mask, 1 << 0)          # ×2=20000 可见

    def test_radar_extends_aa_engage_range(self):
        # basics:328-330：对空射程增幅（aa_try_engage 候选门）
        from sovs.sim.tick import aa_try_engage
        w = make_world(13)
        u = add_unit(w, make_unit(w, _aa_tpl(optics_air=40000, rng=10000),
                                  0, 0, (100000, 50000)))
        a = _mk_air(w, _air_tpl(), team=1, alt=AltTier.HIGH,
                    pos=(100000, 68000))                  # 距 18000>10000
        a.spotted_mask = 1 << 0
        ws = u.elements[0].weapon_states[0]
        aa_try_engage(w, u.elements[0], ws)
        self.assertIsNone(ws.target)                     # 射程外不开瞄
        u.radar_on = True
        u.radar_ready_tick = w.tick
        aa_try_engage(w, u.elements[0], ws)
        self.assertIsNotNone(ws.target)                   # ×2=20000 圈内开瞄


# ══════════════ ④ 诱饵 C／被动对策／导弹来袭事件 ══════════════

class TestDecoyAndWarning(unittest.TestCase):

    def test_manual_pop_and_charges(self):
        w = make_world(14)
        a = _mk_air(w, _air_tpl(decoy_charges=2))
        self.assertTrue(cmd_air_decoy(w, a, "POP"))
        self.assertEqual((a.decoy_left, a.evade_until),
                         (1, w.tick + CONFIG.decoy_evade_ticks))
        cmd_air_decoy(w, a, "POP")
        self.assertFalse(cmd_air_decoy(w, a, "POP"))     # 发数尽拒
        self.assertTrue(cmd_air_decoy(w, a, "AUTO_OFF"))
        self.assertFalse(a.decoy_auto)                    # basics:351-352 自动档

    def test_fire_aa_auto_pops_decoy(self):
        # manual.txt:507-508：被导弹攻击自动触发（fire_aa=来袭事件口）
        from sovs.sim.tick import begin_aim, fire_aa
        w = make_world(14)
        u = add_unit(w, make_unit(w, _aa_tpl(optics_air=50000, rng=50000),
                                  0, 0, (500000, 500000)))
        a = _mk_air(w, _air_tpl(decoy_charges=2), team=1)
        begin_aim(u.elements[0], u.elements[0].weapon_states[0], a)
        fire_aa(w, u.elements[0], u.elements[0].weapon_states[0], a)
        self.assertEqual(a.decoy_left, 1)                 # 自动投放一发
        self.assertGreater(a.evade_until, w.tick)

    def test_missile_warning_ground_branch_pops_smoke(self):
        # 地面支接线留痕（1944 无对地导弹→无生产调用点；直调验证口子活着）
        w = make_world(14)
        u = add_unit(w, make_unit(w, _truck_tpl(), 0, 0, (100000, 50000)))
        u.elements[0].self_smoke_left = 2
        missile_warning(w, u)
        self.assertEqual(u.elements[0].self_smoke_left, 1)
        self.assertGreater(u.elements[0].self_smoke_pop_tick, 0)  # 延迟落烟排程

    def test_passive_evade_reduces_hit(self):
        # basics:353-356：被动对策降命中概率（fire_aa acc 乘区——确定性对照：
        # 满命中机型必中、带 10000bp 被动对策机型必不中）
        from sovs.sim.tick import begin_aim, fire_aa
        plain = _air_tpl(hp_max=1000, armor_aa=1)
        guarded = _air_tpl(template_id=691, hp_max=1000, armor_aa=1,
                           passive_evade_bp=10000)
        for tpl, expect_hit in ((plain, True), (guarded, False)):
            w = make_world(15)
            u = add_unit(w, make_unit(w, _aa_tpl(optics_air=50000,
                                                 rng=50000, acc_bp=10000),
                                      0, 0, (500000, 500000)))
            ws = u.elements[0].weapon_states[0]
            a = _mk_air(w, tpl, team=1)
            begin_aim(u.elements[0], ws, a)
            fire_aa(w, u.elements[0], ws, a)
            hits = [p for p in w.projectiles if p.will_hit]
            self.assertEqual(bool(hits), expect_hit, tpl.name)


# ══════════════ ⑤ 加力 Z／燃油／低空 V ══════════════

class TestAfterburnerFuelAltitude(unittest.TestCase):

    def test_afterburner_toggle_and_speed(self):
        # manual.txt:495-497：×2 速度 toggle；无资格机型拒
        w = make_world(16)
        a = _mk_air(w, _air_tpl(can_afterburner=True, speed_cm_tick=100))
        b = _mk_air(w, _air_tpl(template_id=692), team=1)
        self.assertFalse(cmd_air_afterburner(w, b, True))
        self.assertTrue(cmd_air_afterburner(w, a, True))
        a.flight_plan = [(500000 + 100, 500000)]
        aircraft_move_step(w, a)
        self.assertEqual(a.pos[0], 500000 + 100)          # 100×2 预算=整步到
        self.assertTrue(cmd_air_afterburner(w, a, False))
        a.pos = (500000, 500000)
        a.flight_plan = [(500000 + 100, 500000)]
        aircraft_move_step(w, a)
        self.assertEqual(a.pos[0], 500000 + 100)          # 关后 100 预算恰到
        b.pos = (500000, 500000)
        b.flight_plan = [(500000 + 200, 500000)]
        aircraft_move_step(w, b)
        self.assertEqual(b.pos[0], 500000 + 100)          # 无加力恒速 100

    def test_fuel_double_drain_and_eject(self):
        # manual.txt:496 油耗×2；basics:312-314 耗尽被迫弹射（air_downed 同链）
        w = make_world(16)
        a = _mk_air(w, _air_tpl(can_afterburner=True))
        a.fuel_ticks = 10
        a.afterburner = True
        aircraft_move_step(w, a)
        self.assertEqual(a.fuel_ticks, 8)                  # ×2 消耗
        a.afterburner = False
        aircraft_move_step(w, a)
        self.assertEqual(a.fuel_ticks, 7)                  # ×1 消耗
        a.fuel_ticks = 1
        a.afterburner = True
        aircraft_move_step(w, a)
        self.assertNotIn(a, w.aircraft)                    # 弹射移除
        cd = w.players[a.player_index].air_cooldowns.get(a.template.template_id)
        self.assertGreater(cd, w.tick)                     # 击落冷却同链

    def test_fighter_enters_high_and_low_slows(self):
        # manual.txt:426-428：按角色出场高度（fighters high）；423-425 低空降速
        self.assertIs(entry_tier(AltTier.HIGH, AirRole.FIGHTER), AltTier.HIGH)
        self.assertIs(entry_tier(AltTier.MID, AirRole.BOMBER), AltTier.MID)
        w = make_world(16)
        p0 = w.players[0]
        a = cmd_air_call(w, p0, YAK9, {})
        self.assertIs(a.alt_tier, AltTier.HIGH)            # YAK9=FIGHTER
        a.alt_tier = AltTier.LOW
        a.flight_plan = [(a.pos[0] + 10000, a.pos[1])]
        x0 = a.pos[0]
        aircraft_move_step(w, a)
        self.assertEqual(a.pos[0] - x0,
                         a.template.speed_cm_tick
                         * CONFIG.alt_low_speed_mult_bp // 10000)

    def test_rtb_command_rejects_afterburner(self):
        w = make_world(16)
        a = _mk_air(w, _air_tpl(can_afterburner=True))
        from sovs.sim.air import cmd_air_rtb
        cmd_air_rtb(w, a)
        self.assertFalse(cmd_air_afterburner(w, a, True))  # RTB 不可逆段拒微操


# ══════════════ ⑥ 空投逐一跳伞／自动空投 ══════════════

class TestAirdropSticks(unittest.TestCase):

    def test_two_sticks_one_fee(self):
        # manual.txt:432-433「jump out one by one」：两份装载=两个落点、费一次。
        # 合成双座运输机（现役 Li-2 paratroop_seats=1——多份装载面引擎支持、
        # 真实卡单座为数据侧配属，manual_silent 留痕）
        w = make_world(17, phase=1)
        from sovs.sim.tick import DeckSlot
        ground_tpl = _rifle_tpl()
        transport = AircraftTemplate(
            template_id=695, name="P1Twin", role=AirRole.TRANSPORT,
            cost_body=40, hp_max=80, armor_aa=2, speed_cm_tick=100,
            dogfight_power=1, maneuver=4, alt_ceiling=AltTier.MID,
            payload_max_supply=150, paratroop_seats=2, turret_damage=2,
            payload_price={"SUPPLY": 1})
        w.players[0].deck_slots = [DeckSlot(ground_tpl, 2)]
        a = cmd_air_call(w, w.players[0], transport,
                         {"PARATROOP": ground_tpl, "PARATROOP_COUNT": 2})
        self.assertIsNotNone(a)
        self.assertEqual((a.paratroop_left,
                          w.players[0].deck_slots[0].copies_left), (2, 0))
        pts0 = w.players[0].air_points
        from sovs.sim.air import AirTask
        a.task = AirTask(kind=TaskKind.AIRDROP, drop=(500000, 500000))
        resolve_airdrop(w, a, a.task)
        resolve_airdrop(w, a, a.task)
        spawned = [u for u in w.units if u.template is ground_tpl]
        self.assertEqual(len(spawned), 2)                  # 逐一落地两单位
        self.assertIsNone(a.paratroop_cargo)
        self.assertEqual(w.players[0].air_points,
                         max(0, pts0 - CONFIG.airdrop_fee_points))  # 费一次

    def test_auto_airdrop_after_delay(self):
        # manual.txt:434-440：无其他命令时货机自动在呼叫点空投、完毕回基地
        from sovs.sim.air import aircraft_tick, cmd_air_move
        w = make_world(17, phase=1)
        from sovs.sim.tick import DeckSlot
        ground_tpl = _rifle_tpl()
        w.players[0].deck_slots = [DeckSlot(ground_tpl, 1)]
        a = cmd_air_call(w, w.players[0], LI2,
                         {"PARATROOP": ground_tpl, "PARATROOP_COUNT": 1})
        # 快进到 INBOUND 完成进待命盘旋（auto_drop 排程在到场拍写入——
        # world_tick 整链推进：auto_drop_tick 判据读 world.tick）
        for _ in range(3000):
            world_tick(w)
            if a.auto_drop_tick > 0:
                break
        self.assertGreater(a.auto_drop_tick, 0)           # 到场排程
        cmd_air_move(w, a, [(400000, 400000)])             # 玩家显式令撤销排程
        self.assertEqual(a.auto_drop_tick, 0)
        # 重触发到场排程：直写（模拟再次到场）
        a.auto_drop_tick = w.tick + CONFIG.airdrop_auto_delay_ticks
        a.state = AirState.PATROL
        from sovs.sim.air import AirTask
        a.task = AirTask(kind=TaskKind.PATROL, center=a.pos, radius=2000)
        saw_airdrop_task = False
        for _ in range(3000):
            world_tick(w)
            if a.task is not None and a.task.kind is TaskKind.AIRDROP:
                saw_airdrop_task = True
            if a.paratroop_cargo is None:
                break
        self.assertTrue(saw_airdrop_task)                  # 自动空投任务建立
        self.assertIsNone(a.paratroop_cargo)               # 投毕清舱


# ══════════════ ⑦ 补给堆四开关＋命中即爆 ══════════════

class TestSupplyDump(unittest.TestCase):

    def _world(self):
        w = make_world(18)
        truck = add_unit(w, make_unit(w, _truck_tpl(flags=UnitFlag.HAS_SUPPLY),
                                      0, 0, (100000, 50000)))
        truck.elements[0].mode = Mode.CARGO
        truck.elements[0].supply_weight_g = 600
        rifle = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (101000, 50000)))
        rifle.elements[0].weapon_states[0].ammo_left = 0
        rifle.elements[0].hp_current = 5
        w.await_resupply.append(rifle)
        return w, truck, rifle

    def test_switches_gate_resupply(self):
        # basics:208-213：四开关（heal/ammo 为实门）
        w, truck, rifle = self._world()
        for _ in range(50):
            world_tick(w)
        self.assertEqual(rifle.elements[0].weapon_states[0].ammo_left, 100)  # 补满
        self.assertEqual(rifle.elements[0].hp_current, 10)
        # 关弹药+医疗后不再补给
        rifle.elements[0].weapon_states[0].ammo_left = 0
        rifle.elements[0].hp_current = 5
        w.await_resupply.append(rifle)
        self.assertTrue(cmd_supply_switch(w, truck, "ammo", False))
        self.assertTrue(cmd_supply_switch(w, truck, "heal", False))
        self.assertFalse(cmd_supply_switch(w, rifle, "ammo", False))  # 非补给载具拒
        for _ in range(50):
            world_tick(w)
        self.assertEqual(rifle.elements[0].weapon_states[0].ammo_left, 0)
        self.assertEqual(rifle.elements[0].hp_current, 5)

    def test_dump_explodes_on_hit(self):
        # basics:206-207：任何命中即爆（溅射敌我不分）
        w, truck, rifle = self._world()
        bystander = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0,
                                          (102000, 50000)))
        apply_damage(w, truck.elements[0], 1)             # 轻擦也爆
        self.assertFalse(truck.alive)                      # 本体摧毁
        self.assertFalse(rifle.alive)                      # 近旁步兵溅射团灭
        self.assertFalse(bystander.alive)                  # （爆伤 40 vs hp10——
                                                            # 敌我不分字面）


# ══════════════ ⑧ 战中呼援 ══════════════

class TestCombatReinforcement(unittest.TestCase):

    def test_purchase_allowed_in_combat(self):
        # basics:165-168：战斗全程随时可呼（部署点数池延用）
        from sovs.sim.tick import DeckSlot
        w = make_world(19, phase=1)
        p = w.players[0]
        p.points = 100
        tpl = _rifle_tpl()
        p.deck_slots = [DeckSlot(tpl, 1)]
        self.assertTrue(cmd_purchase(w, p, tpl))
        self.assertEqual((p.points, p.deck_slots[0].copies_left,
                          len(p.spawn_queue)), (70, 0, 1))


# ══════════════ ⑨ UI 键位与 TAB 焦点过滤 ══════════════

class TestFsmP1Keys(unittest.TestCase):

    def _fsm(self, units=(), aircraft=()):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame(units=units, aircraft=aircraft))
        return f

    def test_B_dual_channel(self):
        # manual ORDERS：B 通用回基地——地面选区走 ground_rtb、飞机走 air_rtb
        f = self._fsm(units=[_funit(1)], aircraft=[_fair(7)])
        f.select_units([1])
        cmd = _SpyCmd()
        self.assertEqual(f.key("B", cmd=cmd), "rtb")
        self.assertTrue(any(c[0] == "ground_rtb" for c in cmd.calls))
        f.select_aircraft([7])
        cmd = _SpyCmd()
        f.key("B", cmd=cmd)
        self.assertTrue(any(c[0] == "air_rtb" for c in cmd.calls))

    def test_Z_dispatch_air_afterburner_ground_radar_sprint(self):
        # manual HOTKEYS：Z Sprint(infantry)/Afterburner(fighters)+Radar 同键
        f = self._fsm(aircraft=[_fair(7, afterburner=False)])
        f.select_aircraft([7])
        cmd = _SpyCmd()
        self.assertEqual(f.key("Z", cmd=cmd), "afterburner")
        self.assertTrue(any(c[0] == "air_afterburner" for c in cmd.calls))
        f = self._fsm(units=[_funit(1)])
        f.select_units([1])
        cmd = _SpyCmd()
        self.assertEqual(f.key("Z", cmd=cmd), "z_dispatch")
        kinds = [c[0] for c in cmd.calls]
        self.assertIn("radar", kinds)                      # 对空令先行（门裁决）
        self.assertIn("sprint", kinds)

    def test_C_decoy_and_V_toggle(self):
        f = self._fsm(aircraft=[_fair(7, alt_tier="mid")])
        f.select_aircraft([7])
        cmd = _SpyCmd()
        self.assertEqual(f.key("C", cmd=cmd), "decoy")
        self.assertTrue(any(c[0] == "air_decoy" for c in cmd.calls))
        # V 两态：MID→LOW→regain（manual.txt:426「Press V again to regain」）
        cmd = _SpyCmd()
        f.key("V", cmd=cmd)
        tiers = [c[1][1] for c in cmd.calls if c[0] == "air_alt"]
        self.assertEqual(tiers, ["LOW"])
        f.on_frame(_frame(units=(), aircraft=[_fair(7, alt_tier="low")]))
        f.select_aircraft([7])
        f.key("V", cmd=cmd)
        tiers = [c[1][1] for c in cmd.calls if c[0] == "air_alt"]
        self.assertEqual(tiers, ["LOW", "MID"])            # 低→恢复出场层

    def test_N_L_M_P_arm_groups(self):
        f = self._fsm()
        self.assertEqual(f.key("N"), "arm:laser")
        self.assertEqual(f.key("L"), "arm:sniper")
        self.assertEqual(f.key("M"), "arm:mount")
        self.assertEqual(f.key("P"), "arm:precision")

    def test_laser_and_mount_execution(self):
        f = self._fsm(units=[_funit(1), _funit(2)])
        f.select_units([1])
        f.key("N")
        cmd = _SpyCmd()
        self.assertTrue(f.execute_armed_unit(9, cmd, enemy=True))
        self.assertTrue(any(c[0] == "laser_designate" for c in cmd.calls))
        self.assertIsNone(f.armed_order)
        f.select_units([1])
        f.key("M")
        self.assertTrue(f.execute_armed_unit(2, cmd, enemy=False))
        self.assertTrue(any(c[0] == "mount" for c in cmd.calls))

    def test_TAB_focus_filters_commands_keeps_selection(self):
        # basics:59-60：TAB 子选——只对焦点单位下令而不丢失选区
        f = self._fsm(units=[_funit(1), _funit(2), _funit(3)])
        f.select_units([1, 2, 3])
        f.key("Q")
        cmd = _SpyCmd()
        f.execute_armed_unit(9, cmd, enemy=True)
        shooters = [c[1][0] for c in cmd.calls if c[0] == "attack"]
        self.assertEqual(sorted(shooters), [1, 2, 3])      # 未按 TAB=全选区
        cmd = _SpyCmd()
        f.key("TAB")                                       # 焦点→2
        self.assertEqual(f.focus_unit, 2)
        f.key("Q")
        f.execute_armed_unit(9, cmd, enemy=True)
        shooters = [c[1][0] for c in cmd.calls if c[0] == "attack"]
        self.assertEqual(shooters, [2])                    # 仅焦点下令
        self.assertEqual(f.selected, (1, 2, 3))            # 选区不散
        cmd = _SpyCmd()                                    # Shift=排队走全选区
        f.key("Q")
        f.execute_armed_unit(9, cmd, enemy=True, shift=True)
        shooters = [c[1][0] for c in cmd.calls if c[0] == "attack"]
        self.assertEqual(sorted(shooters), [1, 2, 3])

    def test_refund_toast_from_frame(self):
        # 帧顶层 refunds → fsm toast（manual「immediately reimbursed」可见化）
        f = self._fsm(units=[_funit(1)])
        f.on_frame(_frame(units=[_funit(1)], refunds=[
            {"tick": 700, "unit_id": 5, "team": 0, "amount": 40}]))
        self.assertTrue(any("退款" in n["text"] and "+40" in n["text"]
                            for n in f.notifications))
        f.on_frame(_frame(units=[_funit(1)], refunds=[
            {"tick": 700, "unit_id": 5, "team": 0, "amount": 40}]))
        count = sum(1 for n in f.notifications if "+40" in n["text"])
        self.assertEqual(count, 1)                          # 同 (tick,uid) 去重


# ══════════════ ⑩ wire 1.3 六命令 dispatch 全链 ══════════════

class TestP1CommandDispatch(unittest.TestCase):
    """六新命令经 queue_command→_dispatch_command 命令流真落地（wire 1.3）。"""

    def test_all_six_dispatch(self):
        w = make_world(20)
        u = add_unit(w, make_unit(w, _sniper_tpl(), 0, 0, (500000, 50000)))
        foe = add_unit(w, make_unit(w, _rifle_tpl(), 1, 1, (500000, 60000)))
        aa = add_unit(w, make_unit(w, _aa_tpl(), 0, 0, (90000, 50000)))
        truck = add_unit(w, make_unit(w, _truck_tpl(flags=UnitFlag.HAS_SUPPLY),
                                      0, 0, (80000, 50000)))
        truck.elements[0].mode = Mode.CARGO
        a = _mk_air(w, _air_tpl(can_afterburner=True, decoy_charges=1))
        for cmd in (LaserDesignateCmd(designator_unit=u, target_unit=foe),
                    RadarCmd(unit=aa, engage=True),
                    SupplySwitchCmd(unit=truck, switch="heal", on=False),
                    AirAfterburnerCmd(aircraft=a, engage=True),
                    AirDecoyCmd(aircraft=a, action="POP")):
            queue_command(w, cmd)
        consume_commands(w)
        self.assertEqual(len(w.laser_by_unit), 1)          # LOS 内（10000 内贴脸）
        self.assertTrue(aa.radar_on)
        self.assertFalse(truck.supply_switches & 2)
        self.assertTrue(a.afterburner)
        self.assertEqual(a.decoy_left, 0)


if __name__ == "__main__":
    unittest.main()
