"""World 状态帧导出（FE-T02）：World → 纯 dict 公共状态帧（stdlib json 直序列化）。

结论先行：本模块是 sim 侧唯一的「玩家视角状态导出」公共 API——观战器
（FE-T06）/可玩壳（FE-T07）/将来 lockstep（FE-T10）取数只经 state_frame，
禁止渲染层直读 World（直读=看全图作弊面，FE-01 §2.7「迷雾不对称陷阱」）。
迷雾口径与 AI 摘要档（sovs/ai/state_view.py）同源单实现：敌方经
spotted_mask 位过滤（`(u.spotted_mask >> my_team) & 1`——types.py spotted_mask
为唯一事实源，sensing.py 唯一写者）、己方全量、占点公开；state_view 重构后
即在本帧之上做 AI 摘要档（截断+整米化+中文字段名），不重复实现迷雾。

契约三定（FE-01 §5 FE-T02「帧头契约」）：
① 视角——player_index 传玩家号取其队为迷雾视角；传 None 为裁判全知
  （双方全量导出，FE-T06 红蓝裁判三视角切换靠它）；
② 不截断——不带 max_units 上限（situation_brief 的 16 上限是 AI 摘要档
  行为，留在 AI 层），帧不丢实体；
③ 帧头——schema_version/tick/phase/view 每帧必带（FE-T06 按帧对齐依赖）。

坐标口径：保持整型 cm（原始精度——渲染插值需要）。整米化（//100）是 AI
摘要档行为，不进公共帧；此为对 FE-01 :270「复用…与整米化」字面的有意
偏离，拍板留痕见 TECH-00 §12.11（「整米化收敛为 AI 摘要档（state_view）
行为，公共帧保持 int cm」）。值域纪律：全帧递归仅 int/str/bool/None/
list/dict（显式无 float——FE-T02 测试兜底）；时长一律 tick（10Hz）。

私有信息边界（迷雾裁剪的对象面）：敌方玩家经济与卡组余份是私有信息——
队视角 players 段仅导出本队玩家；单位/飞机按 spotted_mask 过滤。公开面：
占点归属（system_objectives 每拍重写 owner）、烟区/建筑/弹道（物理可见）、
结算 result（终局公开）。
"""
from __future__ import annotations

from .air import (PHASE_COMBAT, PHASE_DEPLOY, PHASE_SETTLE, AltTier,
                  TaskKind)
from .types import UnitFlag

# 帧契约版本（FE-T03 wire/回放文件头同源节奏：字段档非向后兼容变更时 bump）。
# 1.0→1.1＝2026-10-12 GP-01 §4 ①段（空中可控块）：aircraft 条目 +facing/engage_air/
# task/alt_pending 四键、players 条目 +air_cooldowns、顶层 +rejections（尾 8 条）
# ——帧档扩面非向后兼容（FE-T06 观战器按帧头对齐既有口径），随 wire 1.1 同批。
# 1.1 加键不 bump（2026-10-12 battle.png 复检①）：units 条目 +fire_mission（己方
# 判别摘要，缺省 None——旧消费者忽略未知键即向后兼容，不随 wire 版联动）。
SCHEMA_VERSION = "1.1"

_PHASE_NAME = {PHASE_DEPLOY: "deploy", PHASE_COMBAT: "combat", PHASE_SETTLE: "settle"}


def _fm_summary(u) -> dict | None:
    """炮击任务判别摘要（GP-01 §3 可视面——battle 页炮击目标标记的数据面）：
    form point/line/creep + point|line 判别键（互斥，另一键 None）+ ammo 位。
    None=无任务。导出边界在调用侧（敌方任务目标=情报私有，见 _unit_entry 注）。"""
    fm = u.fire_mission
    if fm is None:
        return None
    return {
        "form": fm.form.name.lower(),                # point/line/creep
        "point": None if fm.target_point is None
                 else [fm.target_point[0], fm.target_point[1]],
        "line": None if fm.target_line is None
                else [[fm.target_line[0][0], fm.target_line[0][1]],
                      [fm.target_line[1][0], fm.target_line[1][1]]],
        "ammo": fm.ammo,                             # "HE"|"SMOKE"（GP-01 §3 弹药位）
    }


def _unit_entry(u, view: int | None) -> dict:
    """单位条目（全量档；hp=元素血量和/满值和，ammo=最紧武器弹量百分比）。

    fire_mission 摘要仅己方导出（view=None 裁判全知全量）——敌方即使被
    spotted，其炮击目标坐标也是对方私有情报，不随迷雾可见位泄露。
    〔2026-10-12 battle.png 复检①加键：帧档 1.1 加键不 bump，见模块头注。〕"""
    hp = sum(e.hp_current for e in u.elements)
    hp_max = sum(e.template.hp_max for e in u.elements)
    pcts = []
    for e in u.elements:
        for ws in e.weapon_states:
            if ws.template.ammo_base > 0:
                pcts.append(ws.ammo_left * 100 // ws.template.ammo_base)
    return {
        "id": u.id,
        "team": u.team,
        "category": int(u.template.category),        # 0 侦察/1 步兵/2 装甲/3 火支/4 防空后勤
        "name": u.template.name,
        "pos_cm": [u.pos[0], u.pos[1]],              # 原始整型厘米（不整米化，见头注）
        "hp": hp,
        "hp_max": hp_max,
        "ammo_pct": min(pcts) if pcts else -1,       # -1=无弹药武器（纯白刃/侦查）
        "morale": u.morale.name.lower(),             # stable/suppressed/pinned/routed（D014 四态）
        "suppressed": any(e.suppression > 0 for e in u.elements),
        "stance": u.stance.name.lower(),             # weapons_free/hold_fire
        "moving": u.moving(),
        "mounted": any(e.mounted_in is not None for e in u.elements),
        "garrisoned": any(e.garrison_in is not None for e in u.elements),
        "towed": any(e.towed != 0 for e in u.elements),
        "mode": u.move_mode.name.lower(),            # normal/attack/march/reverse
        "formation": u.formation_shape.name.lower(), # none/line/column/wedge
        "smoke_left": sum(e.self_smoke_left for e in u.elements),  # 自卫烟幕余发（AI 摘要档消费面）
        "fire_mission": (_fm_summary(u)
                         if view is None or u.team == view else None),
    }


def _task_summary(a) -> dict | None:
    """任务槽判别摘要（GP-01 §4 ①段——面板「盘旋/攻X/投X」显示面；None=无任务）。
    kind ∈ patrol/strike/airdrop，各变体只带未用字段为 None 的判别键。"""
    t = a.task
    if t is None:
        return None
    if t.kind is TaskKind.PATROL:
        return {"kind": "patrol",
                "center": [t.center[0], t.center[1]], "radius": t.radius}
    if t.kind is TaskKind.STRIKE:
        return {"kind": "strike", "weapon": t.weapon,
                "target": [t.target[0], t.target[1]]}
    return {"kind": "airdrop", "drop": [t.drop[0], t.drop[1]]}


def _aircraft_entry(a) -> dict:
    """飞机条目（ammo 弹舱整拷——BOMB/STRAFE/SUPPLY；spotted=被对方任一队
    发现（`a.spotted_mask & ~(1 << a.team)`，与观察视角无关的自身状态，
    断箭/Wargame 系玩家可见自身被探测状态的同款 UX，非视角泄露）。
    〔GP-01 §4 ①段（2026-10-12 空中可控块，帧 1.1）：+facing（机头八向度——CAP
    朝向微操依据）/engage_air（对空开关，None=机型无对空能力）/task（判别摘要
    _task_summary）/alt_pending（换层中 {tier,ticks_left}|None——B-29 微操特许
    的进行时可见）。〕"""
    ap = a.alt_pending
    return {
        "id": a.id,
        "team": a.team,
        "name": a.template.name,
        "state": a.state.name.lower(),        # inbound/patrol/strike/rtb/dogfight
        "alt_tier": a.alt_tier.name.lower(),  # low/mid/high
        "pos_cm": [a.pos[0], a.pos[1]],
        "facing": a.facing,                   # 机头朝向 deg（0..355 八向档）
        "hp": a.hp_current,
        "hp_max": a.hp_max,
        "ammo": dict(a.ammo_left),
        "paratroop": (a.paratroop_cargo.template_id
                      if a.paratroop_cargo is not None else None),  # 载伞卡 id；None=未载
        "spotted": bool(a.spotted_mask & ~(1 << a.team)),
        "engage_air": a.engage_air,           # None=无对空槽（can_engage_air=False 且非 FIGHTER）
        "task": _task_summary(a),             # 任务判别摘要（patrol/strike/airdrop）
        "alt_pending": (None if ap is None else
                        {"tier": AltTier(ap[0]).name.lower(),
                         "ticks_left": ap[1]}),  # 换层中；None=无在途换层
    }


def _player_entry(p) -> dict:
    """玩家条目（deck 余份全列——airdrop=空降投送限定卡标记，FE-07 卡面板消费）。
    〔GP-01 §4 ①段（帧 1.1）：+air_cooldowns（{template_id: 剩余 tick}——「打完回
    卡池再呼入」冷却可视化，断箭「RTB 返航、退款与再呼入冷却」的对应面）。〕"""
    airdrop_only = UnitFlag.DELIVERY_AIRDROP_ONLY  # 空裁8 A 案限定位
    return {
        "index": p.index,
        "team": p.team,
        "points": p.points,
        "air_points": p.air_points,
        "air_cooldowns": {tid: ticks
                          for tid, ticks in p.air_cooldowns.items()},  # 帧值域：int→int
        "deck": [{
            "template_id": s.template.template_id,
            "name": s.template.name,
            "copies_left": s.copies_left,
            "airdrop": bool(s.template.flags & airdrop_only),
        } for s in p.deck_slots],
    }


def _result_entry(result) -> dict:
    """结算三级证据（D031 Settlement：占点分→剩余单位分值→剩余总血量）。"""
    return {
        "winner": result.winner,
        "obj_counts": list(result.obj_counts),
        "unit_scores": list(result.unit_scores),
        "hp_totals": list(result.hp_totals),
    }


def state_frame(world, player_index: int | None) -> dict:
    """构造给定视角的公共状态帧（纯数据，stdlib json 可直接序列化）。

    player_index=None → 裁判全知（双方全量）；否则取该玩家的队号为迷雾视角
    （帧头 view=队号或 None）。迷雾：己方全量+敌方 spotted_mask 位过滤；
    占点/烟区/建筑/弹道/结算公开。不带任何 max_units 截断（见头注契约②）。
    """
    if player_index is None:
        view = None
        units = [u for u in world.units if u.alive]
        aircraft = list(world.aircraft)
        players = [p for p in world.players]
    else:
        view = world.players[player_index].team
        units = [u for u in world.units
                 if u.alive and (u.team == view or (u.spotted_mask >> view) & 1)]
        aircraft = [a for a in world.aircraft
                    if a.team == view or (a.spotted_mask >> view) & 1]
        players = [p for p in world.players if p.team == view]
    # 命令拒绝日志（GP-01 §4 ④段，帧 1.1）：尾 8 条（fsm toast 消费面）。视角
    # 过滤=ref_id 须在本帧可见实体 id 集（单位∪飞机）——拒绝条目含对方单位引用，
    # 全量导出=对方操作情报泄露（己方令恒可见；敌方令仅当其实体已被发现时可见；
    # 裁判全知全量）。条目本体见 tick._rej。
    if view is None:
        rejections = list(world.rejection_log[-8:])
    else:
        visible_ids = ({u.id for u in units} | {a.id for a in aircraft})
        rejections = [r for r in world.rejection_log[-8:]
                      if r["ref_id"] in visible_ids]
    return {
        # ── 帧头（契约③：FE-T06 按帧对齐依赖）──
        "schema_version": SCHEMA_VERSION,
        "tick": world.tick,
        "phase": _PHASE_NAME.get(world.phase, f"phase{world.phase}"),
        "view": view,
        "map_cm": [world.map_extent[0], world.map_extent[1]],
        # ── 实体全量档 ──
        "units": [_unit_entry(u, view) for u in units],
        "aircraft": [_aircraft_entry(a) for a in aircraft],
        "objectives": [{
            "id": o.id,
            "pos_cm": [o.pos[0], o.pos[1]],
            "radius_cm": o.radius_cm,
            "owner": o.owner,               # int 队号；None=无主（types.py Objective 口径）
        } for o in world.objectives],
        "players": [_player_entry(p) for p in players],
        "rejections": rejections,             # 命令拒绝尾 8 条（GP-01 §4 ④段——fsm toast）
        "smoke_zones": [{
            "pos_cm": [z.center[0], z.center[1]],
            "radius_cm": z.radius_cm,
            "ttl_ticks": z.ttl_ticks,
        } for z in world.smoke_zones],
        "projectiles": [{
            "pos_cm": [p.pos[0], p.pos[1]],
            "type": getattr(p.damage_type, "name", str(p.damage_type)).lower(),  # ke/he/smoke
        } for p in world.projectiles],
        "buildings": [{
            "id": b.id,
            "pos_cm": [b.pos[0], b.pos[1]],
            "hp": b.hp,
            "slots_free": max(0, b.garrison_slots
                              - len({e.unit.id for e in b.garrisoned})),
        } for b in world.buildings if b.hp > 0],
        "result": _result_entry(world.result) if world.result is not None else None,
    }
