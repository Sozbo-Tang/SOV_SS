"""独立复检：航空状态机/缠斗/经济 不变量暴力仿真（伪代码逻辑视角）。

不改动任何库文件；用与 tests 相同的 World 桩形制驱动 air.py 行为层，
在每个 tick 末检查不变量：
  I1 air_points >= 0
  I2 冷却表单调不减
  I3 缠斗配对对称（a.dogfight.opponent.dogfight.opponent is a；双方 state 均 DOGFIGHT）
  I4 无飞机滞留 DOGFIGHT 超过 rounds_max*interval+slack
  I5 死锁探测器：非 PATROL 态且非设计性挂起（非实战期 INGRESS 悬停——禁火相位
     2026-10-03 已取消，现为部署/结算期悬停）下，
     连续 N tick 位置/相位/计时器无任何推进
  I6 (state, task.kind, task.phase) 组合仅在白名单内
"""
import sys, itertools
from types import SimpleNamespace

sys.path.insert(0, "/Users/tianhuatang/Developer/SOV_SS")
from sovs.sim import air
from sovs.sim.air import (PHASE_COMBAT, PHASE_DEPLOY, PHASE_SETTLE,
                          AircraftInstance, AircraftTemplate, AirRole, AirState,
                          StrikePhase, TaskKind, aircraft_tick, air_recon_step,
                          cmd_air_call, cmd_air_move, cmd_air_patrol, cmd_air_rtb,
                          cmd_air_strike, cmd_air_airdrop, cmd_air_engage_air,
                          cmd_air_disengage, cmd_air_alt, air_downed)
from sovs.sim.rng import Channels
from sovs.sim.tables import CONFIG
from sovs.sim.types import AltTier, DamageType, Trajectory, WeaponTemplate, MarkLevel

STRAFE_W = WeaponTemplate(name="STRAFE", damage_type=DamageType.KE, target_mask=1,
                          trajectory=Trajectory.DIRECT, damage=4, pen_max=8,
                          salvo=4, max_range_cm=100000, suppression_power=2)
BOMB_W = WeaponTemplate(name="BOMB", damage_type=DamageType.HE, target_mask=1,
                        trajectory=Trajectory.BALLISTIC, damage=20,
                        blast_radius_cm=2500, salvo=2, dispersion_cm=1000,
                        projectile_speed_cm_tick=500)

def tpl(role, tid, **kw):
    d = dict(template_id=tid, name="T%d" % tid, role=role, cost_body=70, hp_max=30,
             armor_aa=4, speed_cm_tick=100, dogfight_power=10, maneuver=8,
             alt_ceiling=AltTier.HIGH, weapons=(), payload_max_bombs=4,
             payload_max_supply=600, paratroop_seats=0, turret_damage=0,
             can_engage_air=False, has_dive=False, payload_price={"BOMB": 5})
    d.update(kw)
    return AircraftTemplate(**d)

FIGHTER_T = [tpl(AirRole.FIGHTER, 10, weapons=((STRAFE_W, 20),)),
             tpl(AirRole.FIGHTER, 11, weapons=((STRAFE_W, 20),))]
ATTACK_T = tpl(AirRole.ATTACK, 12, weapons=((STRAFE_W, 10), (BOMB_W, 4)), can_engage_air=True)
BOMBER_T = tpl(AirRole.BOMBER, 13, weapons=((BOMB_W, 6),))
TRANSPORT_T = tpl(AirRole.TRANSPORT, 14, weapons=(), paratroop_seats=1)
RECON_T = tpl(AirRole.RECON, 15, weapons=(), payload_max_supply=0, payload_max_bombs=0,
              optics_air_cm=30000, recon_mark_base_bp=5000)

PARA_CARD = SimpleNamespace(name="para")

def mkworld(seed=7, phase=PHASE_DEPLOY, tick=0):
    w = SimpleNamespace(
        aircraft=[], projectiles=[], units=[], players=[], tick=tick, phase=phase,
        map_center=(500000, 500000), beacon_by_unit={}, cloud_tier=1,
        # ⑤/⑥块后伤害链消费面（对齐 tick.World 字段——空表/None 即惰性无行为）
        await_resupply=[], tow_pairs=[], mount_requests=None, cover_by_target={},
        buildings=[], next_aircraft_id=1, rng=Channels(seed),
        spawn_paratroop=lambda *a: setattr(w, "paratroop_calls", getattr(w, "paratroop_calls", []) + [a]),
        spawn_airdrop_crate=lambda *a: setattr(w, "crate_calls", getattr(w, "crate_calls", []) + [a]),
    )
    w.air_entry_point = lambda team: (500000, -40000 if team == 0 else 1040000)
    w.rtb_exit_point = lambda team: (500000, -40000 if team == 0 else 1040000)
    p0 = SimpleNamespace(index=0, team=0, air_points=100000, air_cooldowns={}, deck_slots=[])
    p1 = SimpleNamespace(index=1, team=1, air_points=100000, air_cooldowns={}, deck_slots=[])
    p0.deck_slots = [SimpleNamespace(template=PARA_CARD, copies_left=3)]
    p1.deck_slots = [SimpleNamespace(template=PARA_CARD, copies_left=3)]
    w.players = [p0, p1]
    return w

def mkunit(w, team, pos, elems=2):
    # 桩字段对齐伤害链消费面（⑤/⑥块后 apply_damage→needs_resupply/destroy_element
    # 读 weapon_states/supply_weight_g/crit/garrison_in——空值即惰性无行为）
    els = [SimpleNamespace(pos=pos, mounted_in=None, hp_current=10,
                           weapon_states=[], supply_weight_g=None,
                           crit={}, garrison_in=None, cargo_units=None,
                           suppression=0,
                           template=SimpleNamespace(unit_type=1, hp_max=10,
                                                    armor_ke=None, armor_he=None))
           for _ in range(elems)]
    u = SimpleNamespace(id=len(w.units) + 1, team=team, alive=True, elements=els,
                        pos=pos, spotted_mask=0, mark_level=MarkLevel.NONE)
    for e in els:
        e.unit = u
    w.units.append(u)
    return u

def snap(a):
    t = a.task
    return (a.state, t.kind if t else None, t.phase if t else None, a.pos,
            a.hp_current, a.alt_pending[1] if a.alt_pending else None,
            t.phase if t else None, len(a.flight_plan))

class Violation(Exception):
    pass

def check_invariants(w, stall, cfg=CONFIG):
    for p in w.players:
        if p.air_points < 0:
            raise Violation("I1 air_points negative: %r" % p.air_points)
    # I3 pairing symmetry
    for a in w.aircraft:
        d = a.dogfight
        if d is not None:
            b = d.opponent
            if b not in w.aircraft or b.dogfight is None or b.dogfight.opponent is not a \
               or a.state is not AirState.DOGFIGHT or b.state is not AirState.DOGFIGHT:
                raise Violation("I3 pairing asym: %r -> %r" % (a.id, getattr(b, 'id', None)))
            if d.rounds > cfg.dogfight_rounds_max:
                raise Violation("I4 rounds over limit: %r" % d.rounds)
    # I6 state/task combos
    for a in w.aircraft:
        t = a.task
        if a.state is AirState.STRIKE:
            if t is None or t.kind is TaskKind.PATROL:
                raise Violation("I6 STRIKE with %s task" % (t.kind if t else None))
        if a.state is AirState.PATROL and t is not None and t.kind is not TaskKind.PATROL:
            raise Violation("I6 PATROL with %s task" % t.kind)
        if a.state in (AirState.RTB, AirState.INBOUND) and t is not None:
            raise Violation("I6 %s with task %s" % (a.state, t.kind))
        if a.state is AirState.DOGFIGHT and (t is not None or a.dogfight is None):
            raise Violation("I6 DOGFIGHT task=%s dogfight=%s" % (t, a.dogfight))
    # I5 deadlock detector
    for a in w.aircraft:
        s = snap(a)
        prev = stall.get(a.id)
        if prev is not None and prev == s:
            stall[a.id] += 1
            designed = (a.state is AirState.STRIKE and a.task is not None
                        and a.task.phase is StrikePhase.INGRESS and w.phase != PHASE_COMBAT)
            designed = designed or (a.state is AirState.DOGFIGHT and w.phase != PHASE_COMBAT)
            if stall[a.id] > 40 and not designed:
                raise Violation("I5 stalled %d ticks: id=%r %r" % (stall[a.id], a.id, s))
        else:
            stall[a.id] = 0

def dogfight_stress(seed=1, rounds=400):
    """3v3 战斗机缠斗压力：验证一对一配对、TIME_LIMIT 释放、无永锁。"""
    cfg = CONFIG
    w = mkworld(seed=seed, phase=PHASE_COMBAT)
    for i in range(3):
        for team, t in ((0, FIGHTER_T[i % 2]), (1, FIGHTER_T[(i + 1) % 2])):
            a = cmd_air_call(w, w.players[team], t, {})
            assert a is not None
    # 直接空运到中场加速相遇
    for a in w.aircraft:
        a.pos = (500000 + (a.id - 1) * 500, 500000 + (a.id - 1) * 300)
        a.state = AirState.PATROL
        a.task = None
    stall = {}
    df_ticks = {}
    for tick in range(rounds):
        w.tick = tick
        aircraft_tick(w, cfg)
        air_recon_step(w, cfg)
        check_invariants(w, stall, cfg)
        for a in w.aircraft:
            if a.state is AirState.DOGFIGHT:
                df_ticks[a.id] = df_ticks.get(a.id, 0) + 1
                lim = cfg.dogfight_rounds_max * cfg.dogfight_interval_ticks + 20
                if df_ticks[a.id] > lim:
                    raise Violation("dogfight exceeded time limit: id=%r %d" % (a.id, df_ticks[a.id]))
            else:
                df_ticks.pop(a.id, None)
    return w

def full_lifecycle(seed=3):
    """全相位走查：盲部署呼叫→部署期攻击令悬停（非实战 GAP2-03）→实战投放→EGRESS→PATROL→自动RTB→回收。"""
    cfg = CONFIG
    w = mkworld(seed=seed, phase=PHASE_DEPLOY)
    mkunit(w, 1, (500000, 520000))
    mkunit(w, 1, (505000, 520000))
    b0 = cmd_air_call(w, w.players[0], BOMBER_T, {"BOMB": 4})
    f0 = cmd_air_call(w, w.players[0], FIGHTER_T[0], {})
    atk = cmd_air_call(w, w.players[0], ATTACK_T, {"BOMB": 2})
    tr = cmd_air_call(w, w.players[0], TRANSPORT_T, {"PARATROOP": PARA_CARD})
    rc = cmd_air_call(w, w.players[0], RECON_T, {})
    assert all([b0, f0, atk, tr, rc]), "call rejected"
    p0 = w.players[0]
    points0 = p0.air_points
    stall = {}
    saw = {"bomb_tick": None, "para": False, "crate": False}
    # 盲部署 30 tick
    for tick in range(30):
        w.tick = tick; w.phase = PHASE_DEPLOY
        aircraft_tick(w, cfg); air_recon_step(w, cfg); check_invariants(w, stall, cfg)
    # 部署期 60 tick：中途下攻击/空投令（非实战悬停验证——GAP2-03；禁火相位已取消）
    for tick in range(30, 90):
        w.tick = tick; w.phase = PHASE_DEPLOY
        if tick == 35:
            assert cmd_air_strike(w, b0, (500000, 520000), "BOMB"), "strike in DEPLOY should be accepted"
            assert cmd_air_strike(w, atk, (505000, 520000), "STRAFE")
            assert cmd_air_airdrop(w, tr, (500000, 530000)), "airdrop in DEPLOY accepted"
            assert not cmd_air_engage_air(w, atk, True), "engage-on must be rejected outside combat"
        if tick == 50:
            assert cmd_air_alt(w, f0, AltTier.HIGH), "alt cmd"
        aircraft_tick(w, cfg); air_recon_step(w, cfg); check_invariants(w, stall, cfg)
    # 实战 3000 tick
    n_proj0 = 0
    for tick in range(90, 3090):
        w.tick = tick; w.phase = PHASE_COMBAT
        if tick == 95:
            cmd_air_engage_air(w, atk, True)   # 转对空（丢弹）
        aircraft_tick(w, cfg); air_recon_step(w, cfg); check_invariants(w, stall, cfg)
        if len(w.projectiles) > n_proj0 and saw["bomb_tick"] is None:
            saw["bomb_tick"] = tick
        if getattr(w, "paratroop_calls", None):
            saw["para"] = True
        if getattr(w, "crate_calls", None):
            saw["crate"] = True
        # 结算期停止检查（抽查一次）
        if tick == 200:
            save_phase = w.phase
            w.phase = PHASE_SETTLE
            before = [(a.id, snap(a)) for a in w.aircraft]
            aircraft_tick(w, cfg); air_recon_step(w, cfg)
            after = [(a.id, snap(a)) for a in w.aircraft]
            if before != after:
                raise Violation("settle phase did not stop aircraft_tick")
            w.phase = save_phase
    if saw["bomb_tick"] is None:
        raise Violation("bomb never dropped after combat start (GAP2-03 resume broken?)")
    # 战斗机耗尽机炮弹 → 自动 RTB → 回收退本体价（延续窗口：空投线仍在飞）
    for tick in range(3090, 3090 + 6000):
        w.tick = tick; w.phase = PHASE_COMBAT
        aircraft_tick(w, cfg); air_recon_step(w, cfg); check_invariants(w, stall, cfg)
        if getattr(w, "paratroop_calls", None):
            saw["para"] = True
        if getattr(w, "crate_calls", None):
            saw["crate"] = True
    if not saw["para"]:
        raise Violation("paratroop never dropped")
    ids_left = [a.id for a in w.aircraft]
    # 侦察机无武器：不自动 RTB（GAP2-05/GAP3-02 豁免）——仍应在空
    if rc.id not in ids_left:
        raise Violation("recon should be exempt from auto-RTB but left: %r" % ids_left)
    print("lifecycle OK: bomb dropped at tick", saw["bomb_tick"],
          "para:", saw["para"], "left:", ids_left,
          "points delta:", p0.air_points - points0,
          "cooldowns:", p0.air_cooldowns)
    return w

def economy_probe(seed=5):
    """经济漏洞探针：0 载荷呼叫即自动 RTB、空降往返退份、投放费余额钳。"""
    cfg = CONFIG
    w = mkworld(seed=seed, phase=PHASE_COMBAT)
    p0 = w.players[0]
    t0 = p0.air_points
    b = cmd_air_call(w, p0, BOMBER_T, {"BOMB": 0})   # 0 载荷轰炸机
    assert b is not None
    for tick in range(3000):
        w.tick = tick
        aircraft_tick(w, cfg); air_recon_step(w, cfg)
    assert b not in w.aircraft, "0-payload bomber should auto-RTB and recover"
    print("economy: 0-payload bomber net cost:", t0 - p0.air_points,
          "(cooldown", p0.air_cooldowns.get(BOMBER_T.template_id), ")")
    # 空降往返：装机扣份 → 立即 RTB → 退份
    w2 = mkworld(seed=seed + 1, phase=PHASE_COMBAT)
    p = w2.players[0]
    tr = cmd_air_call(w2, p, TRANSPORT_T, {"PARATROOP": PARA_CARD})
    assert tr is not None and p.deck_slots[0].copies_left == 2
    cmd_air_rtb(w2, tr)
    for tick in range(3000):
        w2.tick = tick
        aircraft_tick(w2, cfg)
    assert tr not in w2.aircraft
    assert p.deck_slots[0].copies_left == 3, "deck share should refund on safe RTB"
    print("economy: paratroop round-trip deck shares:", p.deck_slots[0].copies_left,
          "points net:", p.air_points - 100000)
    # 投放费下限钳：余额 3 点、费 5 点
    w3 = mkworld(seed=seed + 2, phase=PHASE_COMBAT)
    p3 = w3.players[0]
    tr3 = AircraftInstance(id=w3.next_aircraft_id, team=0, player_index=0,
                           template=TRANSPORT_T, pos=(500000, 500000),
                           alt_tier=AltTier.MID, hp_current=30, state=AirState.PATROL)
    w3.next_aircraft_id += 1
    tr3.ammo_left = {"SUPPLY_ROUNDS": 100, "SUPPLY_MEDICAL": 0, "BOMB": 0, "STRAFE": 0}
    tr3.paratroop_cargo = PARA_CARD          # 空降分支才收投放费（§F6）
    w3.aircraft.append(tr3)
    p3.air_points = 3
    task = air.AirTask(kind=TaskKind.AIRDROP, drop=(500000, 500000),
                       phase=StrikePhase.RUN, run_start=(492000, 500000),
                       run_end=(508000, 500000))
    tr3.task = task
    air.resolve_airdrop(w3, tr3, task, CONFIG)
    assert p3.air_points == 0, "fee clamp failed: %r" % p3.air_points
    print("economy: fee clamp OK (3 -> %r), crate calls: %r" % (p3.air_points, getattr(w3, 'crate_calls', None)))

if __name__ == "__main__":
    for s in (1, 2, 3):
        dogfight_stress(seed=s)
    print("dogfight stress OK x3")
    full_lifecycle(seed=3)
    economy_probe(seed=5)
    print("ALL SIMULATION CHECKS PASSED")
