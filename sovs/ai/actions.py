"""合法动作枚举与效用打分：引擎出候选、模型做选择（兜底=argmax 同一分表）。

覆盖完整游戏流程（v2）：
- 盲部署相位：purchase_candidates 购卡（FIFO 出生序=排兵次序）+ deploy_candidates
  排兵（队形令 FormationCmd + 预置展开车道 MoveCmd——地面单位直落部署锚点、
  无位置控制，排兵=购卡序+队形+部署期预置机动）；
- 实战相位：enumerate_candidates 地面动作 + air_candidates 空军调度
  （呼叫 AirCall/打击 Strike/空投 Airdrop/巡逻 Patrol/对空 EngageAir/返场 RTB）；
- 预备队：空降卡（DELIVERY_AIRDROP_ONLY——购卡门恒拒，唯一投入路径=运输机
  PARATROOP 载荷装机 B-06 扣份 + AirAirdropCmd 择点投放，D017 预备队池）。

分层口径（调研报告拍板）：合法性由命令层门序（cmd_* 各门）最终裁决；本层
只做**候选生成**——生成的每个候选都构造为引擎真实存在的命令对象，越门的
令会被 cmd_* 静默 REJECT（引擎否决权，零异常）。

确定性纪律：枚举序=units/aircraft 列表序，排序键 (-utility, key) 全整数/
字符串——同 world 同候选表，argmax 兜底因此零掷骰可复现。

效用分（int，量纲=粗糙启发，仅决定候选排序与兜底选择，不进引擎）：
  strike/airdrop  55  在空飞机对可见敌集群投弹 / 预备队落点投放
  call_troop      45  呼叫运输机装预备队
  call_strike     50  呼叫攻击机/轰炸机（有可见敌情时）
  dismount        42  车载班近敌下车步战（1.2km 内见敌）
  deploy_move     40 - 4×车道偏置（部署期预置展开——兜底=按发出序轮转车道）
  formation       30~36 队形令（LINE 36 / WEDGE 34 / COLUMN 30，首个未编队单位）
  smoke           35/15 自卫烟幕（受压 35 / 敌近 1.2km 15——PB-53 发数/冷却门内）
  untow           33  解除拖曳+重展开射击（近敌锚<=600m 且停稳——转场终点）
  garrison        32  CAN_GARRISON 单位驻楼（隐蔽+3/受击按尾甲）
  objective       30  向最近非己方占点机动（占点=胜利条件）
  air_patrol      30  在空战斗机 CAP 盘旋
  air_engage      28  在空战斗机开对空交战
  tow             28  牵引车拖火支炮转场（远敌锚>600m——先 SetMode(TOW)）
  air_rtb         25  弹尽飞机返场（B-29 手动弃权）
  call_cap        30~40 呼叫战斗机（见敌机 40 / 常规 30）
  call_recon      35  呼叫侦察机
  advance         20  向敌锚点推进
  mount           18  班组登车行军（同点位静止混编卡）
  air_alt         18  战斗机爬升至 ceiling 层（能量优势；高度层微操）
  ungarrison      12  驻楼单位无敌情撤出机动
  air_move        34  运输机转场飞往落点（空投前置——非缠斗/返场态）
  pivot           34  静止装甲单位原地转向正面迎敌（首甲对威胁）
  sniper_cover    26  反狙击掩护我方最高价值单位（CAN_SNIPER_COVER 位）
  sprint          24  受压单位冲刺破压（冷却窗内不生成；期间禁射）
  buy_supplies    23  HAS_SUPPLY 位卡转 CARGO 满载装填（批③ 支援链）
  air_disengage  22/9 缠斗脱离（战力劣势 22 / 主动退出 9——R-20 尾掷）
  freefire        16  禁火单位敌近恢复自由射击
  holdfire        14  渗透潜行期转禁火（未暴露时）
  beacon          10  CAN_AIRDROP_BEACON 位布信标（对现役卡恒 REJECT 死路径）
  cancel_fm        8  撤销炮击任务（省弹）
  cancel_all       6  取消全部排队命令
  artillery       55  火支开任务（一局一次——重发重置校射进度）
  attack          40 - 距离km（仅当目标在某武器 max_range 内）
  halt             5  受压/钉住且在动的单位停车稳住
  wait             1  什么都不做，永远在场
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from sovs.sim.air import AirRole, AirState
from sovs.sim.air_data import CARD_OBJECTS
from sovs.sim.tables import CONFIG
from sovs.sim.tick import (AirAirdropCmd, AirAltCmd, AirCallCmd, AirDisengageCmd,
                           AirEngageAirCmd, AirMoveCmd, AirPatrolCmd,
                           AirRTBCmd, AirStrikeCmd, AttackCmd, BuySuppliesCmd,
                           CancelCmd, CancelFireMissionCmd, DeployCmd,
                           DismountCmd, FireMissionCmd, FireMissionForm,
                           FormationCmd, GarrisonCmd, MountCmd, MoveCmd, PivotCmd,
                           SetAirdropBeaconCmd, SetModeCmd, SetSniperCoverCmd,
                           SetStanceCmd, SmokeCmd, SprintCmd, StopCmd, TowCmd,
                           UnGarrisonCmd, UntowCmd)
from sovs.sim.types import (AltTier, ElementType, FormationShape, Mode,
                            MoraleState, MoveMode, Stance, TowState, UnitFlag)

# 阵营空册（§6.1/§6.2 苏德各五型——team0=苏 / team1=德，镜像结构）
TEAM_AIR_KEYS = (("IL2M", "PE2", "YAK9", "PO2", "LI2"),
                 ("JU87D", "JU88", "FW190A", "FW189", "JU52"))

# ── 候选对象：纯数据（可 JSON 落日志），命令在执行期构造 ──


@dataclass(frozen=True)
class Candidate:
    key: str                 # 选项名（choice criteria 键；ASCII 短标签）
    desc: str                # 中文描述（模型读的判据）
    utility: int             # 效用分（兜底=argmax）
    kind: str                # advance|objective|attack|halt|artillery|wait
    params: dict = field(default_factory=dict)


def build_commands(world, player, cand: Candidate):
    """候选 → 引擎命令对象列表（执行期由 KevPlayer 逐个 queue_command）。

    命令对象引用 world 内活实例（单位/元素）——id 在生成与执行之间必然存活：
    生成与执行同拍（决策节拍内完成），期间无 world_tick。
    """
    if cand.kind == "wait":
        return []
    if cand.kind in ("advance", "objective"):
        unit = _unit_by_id(world, cand.params["unit_id"])
        return [MoveCmd(unit=unit, path=[tuple(cand.params["dest"])],
                        mode=MoveMode.NORMAL, queue=False)] if unit else []
    if cand.kind == "attack":
        e = _element_by_id(world, cand.params["unit_id"], cand.params["element_id"])
        t = _element_by_id(world, cand.params["target_unit_id"],
                           cand.params["target_element_id"])
        return [AttackCmd(element=e, target=t)] if e is not None and t is not None else []
    if cand.kind == "halt":
        unit = _unit_by_id(world, cand.params["unit_id"])
        return [StopCmd(unit=unit)] if unit else []
    if cand.kind == "artillery":
        unit = _unit_by_id(world, cand.params["unit_id"])
        if unit is None:
            return []
        cmds = [SetModeCmd(element=el, mode=Mode.INDIRECT) for el in unit.elements]
        cmds.append(FireMissionCmd(unit=unit, form=FireMissionForm.POINT,
                                   point=tuple(cand.params["point"])))
        return cmds
    if cand.kind == "deploy_move":
        unit = _unit_by_id(world, cand.params["unit_id"])
        return [MoveCmd(unit=unit, path=[tuple(cand.params["dest"])],
                        mode=MoveMode.NORMAL, queue=False)] if unit else []
    if cand.kind == "formation":
        unit = _unit_by_id(world, cand.params["unit_id"])
        if unit is None:
            return []
        shape = FormationShape[cand.params["shape"]]
        return [FormationCmd(units=[unit], shape=shape)]
    if cand.kind == "air_call":
        payload = dict(cand.params["payload"])
        if payload.get("PARATROOP") is True:        # 执行期换装预备队卡模板引用
            slot = _paratroop_slot(player)
            if slot is None:
                return []
            payload["PARATROOP"] = slot.template
        return [AirCallCmd(player=player,
                           template=CARD_OBJECTS[cand.params["key"]],
                           payload=payload)]
    if cand.kind == "strike":
        a = _aircraft_by_id(world, cand.params["aircraft_id"])
        if a is None:
            return []
        return [AirStrikeCmd(aircraft=a,
                             target=tuple(cand.params["target"]),
                             weapon=cand.params.get("weapon", "BOMB"))]
    if cand.kind == "airdrop":
        a = _aircraft_by_id(world, cand.params["aircraft_id"])
        if a is None:
            return []
        return [AirAirdropCmd(aircraft=a,
                              drop_point=tuple(cand.params["point"]))]
    if cand.kind == "air_patrol":
        a = _aircraft_by_id(world, cand.params["aircraft_id"])
        if a is None:
            return []
        return [AirPatrolCmd(aircraft=a, center=tuple(cand.params["center"]),
                             radius=cand.params.get("radius", 3000))]
    if cand.kind == "air_engage":
        a = _aircraft_by_id(world, cand.params["aircraft_id"])
        return [AirEngageAirCmd(aircraft=a, engage=True)] if a is not None else []
    if cand.kind == "air_rtb":
        a = _aircraft_by_id(world, cand.params["aircraft_id"])
        return [AirRTBCmd(aircraft=a)] if a is not None else []
    if cand.kind == "air_alt":
        a = _aircraft_by_id(world, cand.params["aircraft_id"])
        if a is None:
            return []
        return [AirAltCmd(aircraft=a,
                          tier=AltTier[cand.params["tier"]])]
    if cand.kind == "mount":
        squad_u = _unit_by_id(world, cand.params["squad_unit_id"])
        carrier_u = _unit_by_id(world, cand.params["carrier_unit_id"])
        if squad_u is None or carrier_u is None:
            return []
        squads = [e for e in squad_u.elements
                  if e.template.element_type is ElementType.SQUAD
                  and e.mounted_in is None]
        return [MountCmd(squad_elements=squads, carrier_unit=carrier_u)] if squads else []
    if cand.kind == "dismount":
        u = _unit_by_id(world, cand.params["unit_id"])
        return [DismountCmd(squad_unit=u)] if u is not None else []
    if cand.kind == "tow":
        tower_u = _unit_by_id(world, cand.params["tower_unit_id"])
        gun_u = _unit_by_id(world, cand.params["towed_unit_id"])
        if tower_u is None or gun_u is None:
            return []
        towers = [e for e in tower_u.elements if e.template.seats >= 0
                  and e.towed is TowState.NONE
                  and e.template.element_type is not ElementType.SQUAD]
        gun = next((e for e in gun_u.elements
                    if e.id == cand.params["towed_element_id"]
                    and e.towed is TowState.NONE), None)
        if not towers or gun is None:
            return []
        cmds = [SetModeCmd(element=t, mode=Mode.TOW)
                for t in towers if t.mode is not Mode.TOW]
        cmds.append(TowCmd(tower_elements=towers, towed_element=gun))
        return cmds
    if cand.kind == "untow":
        u = _unit_by_id(world, cand.params["unit_id"])
        el = _element_by_id(world, cand.params["unit_id"],
                            cand.params["element_id"])
        if u is None or el is None:
            return []
        return [UntowCmd(element=el), DeployCmd(unit=u)]
    if cand.kind == "garrison":
        u = _unit_by_id(world, cand.params["unit_id"])
        b = next((x for x in world.buildings
                  if x.id == cand.params["building_id"] and x.hp > 0), None)
        return [GarrisonCmd(unit=u, building=b)] if u is not None and b is not None else []
    if cand.kind == "ungarrison":
        u = _unit_by_id(world, cand.params["unit_id"])
        return [UnGarrisonCmd(unit=u)] if u is not None else []
    if cand.kind == "smoke":
        el = _element_by_id(world, cand.params["unit_id"],
                            cand.params["element_id"])
        if el is None:
            return []
        return [SmokeCmd(element=el, point=tuple(el.pos))]
    if cand.kind == "pivot":
        u = _unit_by_id(world, cand.params["unit_id"])
        return [PivotCmd(unit=u, facing_deg=cand.params["facing"])] if u else []
    if cand.kind == "sprint":
        u = _unit_by_id(world, cand.params["unit_id"])
        return [SprintCmd(unit=u)] if u else []
    if cand.kind == "stance":
        u = _unit_by_id(world, cand.params["unit_id"])
        if u is None:
            return []
        return [SetStanceCmd(unit=u, stance=Stance[cand.params["stance"]])]
    if cand.kind == "cancel_all":
        u = _unit_by_id(world, cand.params["unit_id"])
        return [CancelCmd(unit=u)] if u else []
    if cand.kind == "cancel_fm":
        u = _unit_by_id(world, cand.params["unit_id"])
        return [CancelFireMissionCmd(unit=u)] if u else []
    if cand.kind == "sniper_cover":
        sniper = _unit_by_id(world, cand.params["sniper_unit_id"])
        target = _unit_by_id(world, cand.params["target_unit_id"])
        if sniper is None or target is None:
            return []
        return [SetSniperCoverCmd(sniper_unit=sniper, target_unit=target)]
    if cand.kind == "buy_supplies":
        el = _element_by_id(world, cand.params["unit_id"],
                            cand.params["element_id"])
        if el is None:
            return []
        cmds = []
        if el.mode is not Mode.CARGO:
            cmds.append(SetModeCmd(element=el, mode=Mode.CARGO))
        cmds.append(BuySuppliesCmd(truck_element=el,
                                   rounds=cand.params["rounds"],
                                   medical=cand.params["medical"]))
        return cmds
    if cand.kind == "beacon":
        u = _unit_by_id(world, cand.params["unit_id"])
        if u is None:
            return []
        return [SetAirdropBeaconCmd(unit=u, pos=tuple(cand.params["pos"]))]
    if cand.kind == "air_move":
        a = _aircraft_by_id(world, cand.params["aircraft_id"])
        if a is None:
            return []
        return [AirMoveCmd(aircraft=a, path=[tuple(cand.params["dest"])])]
    if cand.kind == "air_disengage":
        a = _aircraft_by_id(world, cand.params["aircraft_id"])
        return [AirDisengageCmd(aircraft=a)] if a is not None else []
    return []


def purchase_candidates(world, player_index: int):
    """盲部署相位的购卡候选：[(template, key, desc)]——可负担且有余额的卡组序。

    DELIVERY_AIRDROP_ONLY 空降卡不进候选（cmd_purchase 空裁8 门恒拒——
    提供引擎必拒的选项=浪费决策拍，2026-10-08 实测模型 7/13 拍被它吞掉）。
    不设 skip 选项：点数花不完的被动等待没有信息量，模型无需该选择
    （HeadlessAI 同款策略：每节拍必购一卡直到买不起）。
    """
    p = world.players[player_index]
    out = []
    for i, slot in enumerate(p.deck_slots):
        if slot.template.flags & UnitFlag.DELIVERY_AIRDROP_ONLY:
            continue                       # 购买门恒拒——引擎为假的选项不上桌
        if slot.copies_left > 0 and p.points >= slot.template.cost:
            out.append((slot.template, f"buy_{i}",
                        f"购入 {slot.template.name}（花费 {slot.template.cost} 点，"
                        f"剩余 {slot.copies_left} 份）"))
    return out


def enumerate_candidates(world, player_index: int, *, artillery_issued: set,
                         enemy_anchor, limit: int = 12) -> list[Candidate]:
    """实战相位决策候选：生成→效用排序→截断 limit。确定性（零掷骰）。"""
    p = world.players[player_index]
    my_team = p.team
    mine = [u for u in world.units if u.alive and u.team == my_team]
    foes = [u for u in world.units
            if u.alive and u.team != my_team and (u.spotted_mask >> my_team) & 1]
    wait = Candidate(key="wait", desc="按兵不动，保持现状", utility=1, kind="wait")
    out: list[Candidate] = []

    for u in mine:
        # 火支：一局一次的炮击任务（向敌锚点）
        if (u.template.category == 3 and u.id not in artillery_issued
                and u.elements):
            out.append(Candidate(
                key=f"arty_u{u.id}", kind="artillery",
                desc=f"{u.template.name}(#{u.id}) 转间接瞄准，向敌纵深 ({enemy_anchor[0]//100}m,"
                     f"{enemy_anchor[1]//100}m) 下炮击任务",
                utility=55, params={"unit_id": u.id, "point": list(enemy_anchor)}))

        # 攻击：最近可见敌元素，且在我方任一武器射程内
        for foe in foes:
            dist = _dist_cm(u.pos, foe.pos)
            max_range = max((ws.template.max_range_cm
                             for e in u.elements for ws in e.weapon_states),
                            default=0)
            if max_range <= 0 or dist > max_range or not foe.elements:
                continue
            tgt = min(foe.elements, key=lambda e: (e.hp_current, e.id))
            shooter = _first_armed_element(u)
            if shooter is None:
                continue
            out.append(Candidate(
                key=f"atk_u{u.id}_e{tgt.id}", kind="attack",
                desc=f"{u.template.name}(#{u.id}) 开火打击可见目标 "
                     f"{foe.template.name}(#{foe.id})，距离 {dist//100}m",
                utility=40 - dist // 100_000,   # -1/公里
                params={"unit_id": u.id, "element_id": shooter.id,
                        "target_unit_id": foe.id, "target_element_id": tgt.id}))
            break   # 每单位只报一个攻击候选（按表序首个射程内可打者——确定性）

        # 机动：向最近非己方占点 / 向敌锚点推进
        if u.moving():
            if any(e.suppression > 0 for e in u.elements) or u.morale >= 2:
                out.append(Candidate(
                    key=f"halt_u{u.id}", kind="halt",
                    desc=f"{u.template.name}(#{u.id}) 受压制，停车稳住阵脚",
                    utility=5, params={"unit_id": u.id}))
        else:
            obj = _nearest_unowned(world, u.pos, my_team)
            if obj is not None:
                out.append(Candidate(
                    key=f"obj_u{u.id}", kind="objective",
                    desc=f"{u.template.name}(#{u.id}) 向占点 #{obj.id} "
                         f"({obj.pos[0]//100}m,{obj.pos[1]//100}m) 机动",
                    utility=30, params={"unit_id": u.id, "dest": list(obj.pos)}))
            out.append(Candidate(
                key=f"adv_u{u.id}", kind="advance",
                desc=f"{u.template.name}(#{u.id}) 向敌纵深推进",
                utility=20, params={"unit_id": u.id, "dest": list(enemy_anchor)}))

    # ── 后勤/载具/驻楼/烟幕（首例匹配——确定性；各门内生成，越门令引擎静默拒）──

    # 上下车：混编卡班+座同点位堆叠可上（PB-16）；近敌下车步战、无敌情上车行军
    for u in mine:
        if any(e.mounted_in is not None for e in u.elements):
            if any(_dist_cm(u.pos, f.pos) <= 120000 for f in foes):
                out.append(Candidate(
                    key=f"dismount_u{u.id}", kind="dismount",
                    desc=f"{u.template.name}(#{u.id}) 车载班下车步战（敌近）",
                    utility=42, params={"unit_id": u.id}))
            break
    for u in mine:
        squads = [e for e in u.elements
                  if e.template.element_type is ElementType.SQUAD
                  and e.mounted_in is None]
        if not squads or u.moving():
            continue
        carrier = _eligible_carrier(u, mine)
        if carrier is not None:
            out.append(Candidate(
                key=f"mount_u{u.id}", kind="mount",
                desc=f"{u.template.name}(#{u.id}) 班组登上 "
                     f"{carrier.template.name}(#{carrier.id}) 行军（同点位静止）",
                utility=18, params={"squad_unit_id": u.id,
                                    "carrier_unit_id": carrier.id}))
            break

    # 拖曳：火支炮转场（远敌锚>600m 挂拖，近前<=600m 且停稳解拖重展开——成链）
    gun_u = next((u for u in mine if u.template.category == 3
                  and any(e.template.element_type is ElementType.GUN
                          and e.towed is TowState.NONE for e in u.elements)), None)
    if gun_u is not None and _dist_cm(gun_u.pos, enemy_anchor) > 60000:
        tower_u = next((u for u in mine if u is not gun_u
                        and (u.template.mode_set & (1 << Mode.TOW))
                        and u.template.tow_tonnage >= gun_u.template.own_weight_tons
                        and any(e.template.element_type is not ElementType.SQUAD
                                and e.towed is TowState.NONE
                                for e in u.elements)), None)
        if tower_u is not None:
            gun_el = next(e for e in gun_u.elements
                          if e.template.element_type is ElementType.GUN)
            out.append(Candidate(
                key=f"tow_u{gun_u.id}", kind="tow",
                desc=f"{tower_u.template.name}(#{tower_u.id}) 拖曳 "
                     f"{gun_u.template.name}(#{gun_u.id}) 转场（先转 TOW 模式）",
                utility=28, params={"tower_unit_id": tower_u.id,
                                    "towed_unit_id": gun_u.id,
                                    "towed_element_id": gun_el.id}))
    for pair in world.tow_pairs:
        gun = pair.towed_element
        if (gun.unit.team == my_team and gun.unit.alive
                and not gun.unit.moving()
                and _dist_cm(gun.unit.pos, enemy_anchor) <= 60000):
            out.append(Candidate(
                key=f"untow_u{gun.unit.id}", kind="untow",
                desc=f"{gun.unit.template.name}(#{gun.unit.id}) 解除拖曳并重展开射击",
                utility=33, params={"unit_id": gun.unit.id,
                                    "element_id": gun.id}))
            break

    # 驻楼：CAN_GARRISON 单位 + 有余位建筑（无距离门——伪代码字面全场可达）
    gar_u = next((u for u in mine
                  if (u.template.flags & UnitFlag.CAN_GARRISON)
                  and not any(e.garrison_in is not None for e in u.elements)), None)
    if gar_u is not None:
        b = next((x for x in world.buildings
                  if x.hp > 0 and x.garrison_slots
                  > len({e.unit.id for e in x.garrisoned})), None)
        if b is not None:
            out.append(Candidate(
                key=f"gar_u{gar_u.id}_b{b.id}", kind="garrison",
                desc=f"{gar_u.template.name}(#{gar_u.id}) 驻入建筑 #{b.id}"
                     f"（隐蔽+3，受击按尾甲）",
                utility=32, params={"unit_id": gar_u.id, "building_id": b.id}))
    for u in mine:
        if any(e.garrison_in is not None for e in u.elements):
            if not any(_dist_cm(u.pos, f.pos) <= 150000 for f in foes):
                out.append(Candidate(
                    key=f"ungar_u{u.id}", kind="ungarrison",
                    desc=f"{u.template.name}(#{u.id}) 撤出建筑机动",
                    utility=12, params={"unit_id": u.id}))
            break

    # 自卫烟幕：有发数且冷却就绪（PB-53 门内）；受压 35 / 敌近 15
    for u in mine:
        el = next((e for e in u.elements
                   if e.self_smoke_left > 0
                   and world.tick >= e.self_smoke_ready_tick
                   and e.self_smoke_pop_tick < 0), None)
        if el is None:
            continue
        if any(e.suppression > 0 for e in u.elements):
            out.append(Candidate(
                key=f"smoke_u{u.id}", kind="smoke",
                desc=f"{u.template.name}(#{u.id}) 施放自卫烟幕（受压遮蔽）",
                utility=35, params={"unit_id": u.id, "element_id": el.id}))
        elif any(_dist_cm(u.pos, f.pos) <= 120000 for f in foes):
            out.append(Candidate(
                key=f"smoke_u{u.id}", kind="smoke",
                desc=f"{u.template.name}(#{u.id}) 施放自卫烟幕（敌近遮蔽）",
                utility=15, params={"unit_id": u.id, "element_id": el.id}))
        break

    # ── 次要令（v4：冲刺/原地转向/姿态/取消族/狙击掩护/买补给/空投信标）──

    # 冲刺破压：受压非溃逃单位冲刺（压制减半+升速；冷却窗内不生成）
    for u in mine:
        if (any(e.suppression > 0 for e in u.elements)
                and u.morale is not MoraleState.ROUTED
                and not (u.sprint_until > 0 and world.tick
                         < u.sprint_until + CONFIG.sprint_cooldown_ticks)):
            out.append(Candidate(
                key=f"sprint_u{u.id}", kind="sprint",
                desc=f"{u.template.name}(#{u.id}) 冲刺脱离压制（压制减半+升速，期间禁射）",
                utility=24, params={"unit_id": u.id}))
            break

    # 原地转向：静止装甲单位正面朝向可见威胁（首甲迎敌——PB-51 停车转向）
    for u in mine:
        if (u.moving() or u.pivot_to >= 0):
            continue
        if not any(et.armor_ke is not None
                   for et in u.template.element_templates):
            continue                      # 无甲单位无首甲收益
        near = min(foes, key=lambda f: (_dist_cm(u.pos, f.pos), f.id),
                   default=None)
        if near is None:
            continue
        dy, dx = near.pos[1] - u.pos[1], near.pos[0] - u.pos[0]
        facing = int(math.degrees(math.atan2(dy, dx))) % 360
        out.append(Candidate(
            key=f"pivot_u{u.id}", kind="pivot",
            desc=f"{u.template.name}(#{u.id}) 原地转向正面迎敌（首甲对威胁）",
            utility=34, params={"unit_id": u.id, "facing": facing}))
        break

    # 姿态：渗透潜行期禁火保持隐蔽；禁火单位见敌恢复自由射击
    for u in mine:
        if (u.stance is Stance.WEAPONS_FREE
                and (u.template.flags & UnitFlag.CAN_INFILTRATE)
                and u.infiltration_timer > 0
                and not any(_dist_cm(u.pos, f.pos) <= 120000 for f in foes)):
            out.append(Candidate(
                key=f"holdfire_u{u.id}", kind="stance",
                desc=f"{u.template.name}(#{u.id}) 转禁火潜行（渗透期不暴露）",
                utility=14, params={"unit_id": u.id, "stance": "HOLD_FIRE"}))
            break
    for u in mine:
        if (u.stance is Stance.HOLD_FIRE
                and any(_dist_cm(u.pos, f.pos) <= 120000 for f in foes)):
            out.append(Candidate(
                key=f"freefire_u{u.id}", kind="stance",
                desc=f"{u.template.name}(#{u.id}) 恢复自由射击（敌已近身）",
                utility=16, params={"unit_id": u.id, "stance": "WEAPONS_FREE"}))
            break

    # 取消族：排队令链全清 / 撤销炮击任务（省弹）
    for u in mine:
        if u.command_queue:
            out.append(Candidate(
                key=f"cancel_u{u.id}", kind="cancel_all",
                desc=f"{u.template.name}(#{u.id}) 取消全部排队命令",
                utility=6, params={"unit_id": u.id}))
            break
    for u in mine:
        if u.fire_mission is not None:
            out.append(Candidate(
                key=f"cancelfm_u{u.id}", kind="cancel_fm",
                desc=f"{u.template.name}(#{u.id}) 撤销炮击任务（停止耗弹）",
                utility=8, params={"unit_id": u.id}))
            break

    # 反狙击掩护：CAN_SNIPER_COVER 位卡掩护我方最高价值单位（方案9——现役
    # 0 卡置位，合成卡/补卡后即活；同款旗位先例：CAN_GARRISON）
    sniper = next((u for u in mine
                   if (u.template.flags & UnitFlag.CAN_SNIPER_COVER)
                   and u.alive), None)
    if sniper is not None:
        covered = any(sniper in prots
                      for prots in world.cover_by_target.values())
        if not covered:
            target = max((u for u in mine if u is not sniper),
                         key=lambda u: (u.template.cost, -u.id), default=None)
            if target is not None:
                out.append(Candidate(
                    key=f"cover_u{sniper.id}", kind="sniper_cover",
                    desc=f"{sniper.template.name}(#{sniper.id}) 掩护 "
                         f"{target.template.name}(#{target.id})（受狙击伤害减半）",
                    utility=26, params={"sniper_unit_id": sniper.id,
                                        "target_unit_id": target.id}))

    # 买补给装填：HAS_SUPPLY 位卡 CARGO 模式满载（批③ 支援链——先转 CARGO 再装）
    for u in mine:
        if not (u.template.flags & UnitFlag.HAS_SUPPLY):
            continue
        el = next((e for e in u.elements
                   if (e.template.cargo_rounds_max or e.template.cargo_medical_max
                       or e.template.cargo_weight_max)), None)
        if el is None:
            continue
        rw = CONFIG.supply_round_weight_g
        mw = CONFIG.med_weight_per_unit_g
        rounds = el.template.cargo_rounds_max
        medical = el.template.cargo_medical_max
        cap = el.template.cargo_weight_max
        if el.supply_weight_g is not None and el.supply_weight_g >= cap:
            continue                       # 已满载——不重复装填（防兜底空转占槽）
        if rw > 0 and rounds * rw > cap:           # D012 混装载重闸内取整
            rounds = cap // rw
            medical = 0
        elif mw > 0 and rounds * rw + medical * mw > cap:
            medical = max(0, (cap - rounds * rw) // mw)
        out.append(Candidate(
            key=f"resupply_u{u.id}", kind="buy_supplies",
            desc=f"{u.template.name}(#{u.id}) 转物资模式装填 "
                 f"{rounds} 发/{medical} 医疗（补给车载弹）",
            utility=23, params={"unit_id": u.id, "element_id": el.id,
                                "rounds": rounds, "medical": medical}))
        break

    # 空投信标：CAN_AIRDROP_BEACON 位卡标记落点（方案9——对现役全卡恒 REJECT
    # 的规划面死路径；旗位补卡后即活，候选按旗位生成=如实态）
    for u in mine:
        if ((u.template.flags & UnitFlag.CAN_AIRDROP_BEACON)
                and u.id not in world.beacon_by_unit):
            zone = _nearest_unowned(world, world.map_center, my_team)
            pos = zone.pos if zone is not None else tuple(enemy_anchor)
            out.append(Candidate(
                key=f"beacon_u{u.id}", kind="beacon",
                desc=f"{u.template.name}(#{u.id}) 布设空投信标于"
                     + (f"占点 #{zone.id}" if zone is not None else "敌纵深"),
                utility=10, params={"unit_id": u.id, "pos": list(pos)}))
            break

    out.sort(key=lambda c: (-c.utility, c.key))
    # wait 恒在场（兜底安全位）：截断只切其余候选，为其保留末位一席
    if len(out) >= limit:
        out = out[: limit - 1]
    out.append(wait)
    return out


# ── 部署期排兵（队形 + 预置展开车道）──

_DEPLOY_SHAPES = (("LINE", FormationShape.LINE, 36, "横队展开——正面火力最大"),
                  ("WEDGE", FormationShape.WEDGE, 34, "楔形推进——攻守均衡"),
                  ("COLUMN", FormationShape.COLUMN, 30, "纵队行军——转移最快"))
_LANE_NAMES = ("西翼", "中央", "东翼")


def _deploy_lanes(world, team: int) -> list[tuple[tuple[int, int], str]]:
    """三条预置展开车道：部署锚点向图心推进 1/5 图高，横向往两侧各开 1/5 图宽。"""
    cx = world.map_center[0]
    ex, ey = world.map_extent
    fwd = ey // 5
    y = fwd if team == 0 else ey - fwd
    off = ex // 5
    return [((cx + d * off, y), _LANE_NAMES[d + 1]) for d in (-1, 0, 1)]


def deploy_candidates(world, player_index: int, *, issued_moves: set,
                      issued_formations: set, limit: int = 12) -> list[Candidate]:
    """盲部署相位的排兵候选：队形令（首个未编队多元素单位）+ 预置展开车道
    （每个未预置单位一次）。兜底车道分配=按已发出数轮转（确定性散开）。"""
    p = world.players[player_index]
    mine = [u for u in world.units if u.alive and u.team == p.team]
    wait = Candidate(key="wait", desc="按兵不动，保持现状", utility=1, kind="wait")
    out: list[Candidate] = []

    for u in mine:                                   # 队形：首个未编队多元素单位
        if len(u.elements) >= 2 and u.id not in issued_formations:
            for shape_name, _shape, u_i, desc in _DEPLOY_SHAPES:
                out.append(Candidate(
                    key=f"form_{shape_name.lower()}_u{u.id}", kind="formation",
                    desc=f"{u.template.name}(#{u.id}) 列{desc}", utility=u_i,
                    params={"unit_id": u.id, "shape": shape_name}))
            break                                    # 一次只问一个单位的队形

    lanes = _deploy_lanes(world, p.team)
    for u in mine:
        if u.id in issued_moves or u.moving():
            continue
        pref = len(issued_moves) % 3                 # 兜底轮转车道（西/中/东）
        for i, (pos, lane) in enumerate(lanes):
            out.append(Candidate(
                key=f"lane_{'wec'[i]}_u{u.id}", kind="deploy_move",
                desc=f"{u.template.name}(#{u.id}) 预置展开至{lane}车道 "
                     f"({pos[0] // 100}m,{pos[1] // 100}m)",
                utility=40 - 4 * abs(i - pref),
                params={"unit_id": u.id, "dest": list(pos)}))

    if not out:
        return [wait]
    out.sort(key=lambda c: (-c.utility, c.key))
    if len(out) >= limit:
        out = out[: limit - 1]
    out.append(wait)
    return out


# ── 空军调度（呼叫/打击/空投/巡逻/对空/返场；B-18 无相位门——部署期即呼）──

def _aircraft_by_id(world, aircraft_id: int):
    for a in world.aircraft:
        if a.id == aircraft_id and a.state != AirState.RTB:
            return a
    return None


def _air_cost(tpl, payload: dict) -> int:
    """§F1 出动价（呼叫时点）：机体价 + 非弹药载荷价。〔2026-10-14 空袭按用
    计费块：BOMB 改投放时逐发扣 air_points，不进呼叫价；空降兵不计价——D017
    预备队池已付，跳过非整型载荷值——HeadlessAI 同口径。〕"""
    return tpl.cost_body + sum(tpl.payload_price.get(k, 0) * v
                               for k, v in payload.items()
                               if isinstance(v, int) and k != "BOMB")


def _cluster_point(foes, fallback) -> tuple[int, int]:
    """可见敌集群质心（整除取整）；无敌情时回退锚点。"""
    if not foes:
        return tuple(fallback)
    n = len(foes)
    return (sum(u.pos[0] for u in foes) // n, sum(u.pos[1] for u in foes) // n)


def _paratroop_slot(p):
    """预备队空降卡槽（DELIVERY_AIRDROP_ONLY——购卡门恒拒的唯一投放路径）。"""
    for s in p.deck_slots:
        if s.template.flags & UnitFlag.DELIVERY_AIRDROP_ONLY and s.copies_left > 0:
            return s
    return None


def air_candidates(world, player_index: int, *, enemy_anchor,
                   limit: int = 12) -> list[Candidate]:
    """空军调度候选：在空飞机动作（打击/空投/巡逻/对空/返场）+ 呼叫新机。
    冷却/在空上限/点数三门的不可呼叫项不生成候选（省一次无效 choice）。"""
    p = world.players[player_index]
    my_team = p.team
    foes = [u for u in world.units
            if u.alive and u.team != my_team and (u.spotted_mask >> my_team) & 1]
    foe_air = sum(1 for a in world.aircraft
                  if a.team != my_team and (a.spotted_mask >> my_team) & 1)
    wait = Candidate(key="wait", desc="空军本轮待命", utility=1, kind="wait")
    out: list[Candidate] = []

    # —— 在空飞机调度（PATROL 位）——
    for a in world.aircraft:
        if a.team != my_team or a.state is not AirState.PATROL:
            continue
        role = a.template.role
        if (a.ammo_left.get("BOMB", 0) > 0
                and role in (AirRole.ATTACK, AirRole.BOMBER)):
            tgt = _cluster_point(foes, enemy_anchor)
            out.append(Candidate(
                key=f"strike_a{a.id}", kind="strike",
                desc=f"{a.template.name}(#{a.id}) 对可见敌集群 "
                     f"({tgt[0] // 100}m,{tgt[1] // 100}m) 投弹", utility=55,
                params={"aircraft_id": a.id, "target": list(tgt)}))
        if a.paratroop_cargo is not None:
            drop = _nearest_unowned(world, world.map_center, my_team)
            point = drop.pos if drop is not None else tuple(enemy_anchor)
            out.append(Candidate(
                key=f"drop_a{a.id}", kind="airdrop",
                desc=f"{a.template.name}(#{a.id}) 空投预备队至"
                     + (f"占点 #{drop.id}" if drop is not None else "敌纵深"),
                utility=55, params={"aircraft_id": a.id, "point": list(point)}))
        elif a.ammo_left.get("SUPPLY", 0) > 0:
            out.append(Candidate(
                key=f"supply_a{a.id}", kind="airdrop",
                desc=f"{a.template.name}(#{a.id}) 空投补给箱", utility=45,
                params={"aircraft_id": a.id, "point": list(enemy_anchor)}))
        if (role in (AirRole.FIGHTER, AirRole.RECON)
                and not getattr(a, "engage_air", False)
                and not a.patrol_loop):
            # patrol_loop=True 已在盘旋任务上——不重复下发（防兜底空转占槽）
            if role is AirRole.FIGHTER:
                out.append(Candidate(
                    key=f"engage_a{a.id}", kind="air_engage",
                    desc=f"{a.template.name}(#{a.id}) 开对空交战（CAP 猎杀）",
                    utility=28, params={"aircraft_id": a.id}))
            center = enemy_anchor if role is AirRole.RECON else world.map_center
            out.append(Candidate(
                key=f"cap_a{a.id}", kind="air_patrol",
                desc=f"{a.template.name}(#{a.id}) "
                     + ("侦察盘旋敌区" if role is AirRole.RECON else "CAP 盘旋图心"),
                utility=30, params={"aircraft_id": a.id, "center": list(center)}))
        if (role is AirRole.FIGHTER and a.alt_pending is None
                and a.alt_tier is not a.template.alt_ceiling
                and a.template.alt_ceiling is not None):
            out.append(Candidate(
                key=f"climb_a{a.id}", kind="air_alt",
                desc=f"{a.template.name}(#{a.id}) 爬升至"
                     f"{a.template.alt_ceiling.name} 层（能量优势）",
                utility=18, params={"aircraft_id": a.id,
                                    "tier": a.template.alt_ceiling.name}))
        # 〔ferry/air_move 转场候选已裁撤 2026-10-08〕AirAirdropCmd 自带飞往
        # 落点（resolve_airdrop 全链），转场是冗余微操；且实测 0.5B 在"转场"
        # 与"空投"二选一时 97% 锁死转场（273/281）永不投放——模型陷阱选项，
        # 删除。kind=air_move 的 build_commands 支持保留（引擎能力不裁）。
        if (a.ammo_left.get("BOMB", 0) <= 0 and a.paratroop_cargo is None
                and a.ammo_left.get("SUPPLY", 0) <= 0
                and role in (AirRole.ATTACK, AirRole.BOMBER, AirRole.RECON)):
            out.append(Candidate(
                key=f"rtb_a{a.id}", kind="air_rtb",
                desc=f"{a.template.name}(#{a.id}) 任务完毕返场（冷却后可再呼）",
                utility=25, params={"aircraft_id": a.id}))

    # —— 缠斗脱离（DOGFIGHT 态——独立循环：PATROL 门外的在空动作）——
    for a in world.aircraft:
        if (a.team != my_team or a.state is not AirState.DOGFIGHT
                or a.dogfight is None):
            continue
        opp = getattr(a.dogfight, "opponent", None)
        losing = (opp is not None
                  and a.template.dogfight_power < opp.template.dogfight_power)
        out.append(Candidate(
            key=f"break_a{a.id}", kind="air_disengage",
            desc=f"{a.template.name}(#{a.id}) 缠斗脱离"
                 + ("（战力劣势，脱离保机——R-20 尾掷）" if losing
                    else "（主动退出缠斗）"),
            utility=22 if losing else 9,
            params={"aircraft_id": a.id}))

    # —— 呼叫新机（冷却门/在空上限门/点数门内生成）——
    for key in TEAM_AIR_KEYS[my_team]:
        tpl = CARD_OBJECTS[key]
        n_same = sum(1 for x in world.aircraft
                     if x.team == my_team
                     and x.template.template_id == tpl.template_id)
        if n_same >= CONFIG.air_per_type_max:
            continue
        if world.tick < p.air_cooldowns.get(tpl.template_id, 0):
            continue
        role = tpl.role
        if role in (AirRole.ATTACK, AirRole.BOMBER):
            # 2026-10-14 空袭按用计费块：满载呼叫（弹费投放时逐发扣 air_points，
            # 不再按点数预算钳挂弹——点数耗尽后投放侧 max(0,·) 钳=免账不追缴，
            # manual_silent 留痕）；点数门=呼叫价（_air_cost 已剔除 BOMB）
            n_bomb = tpl.payload_max_bombs
            if n_bomb <= 0:
                continue
            payload = {"BOMB": n_bomb}
            if p.air_points >= _air_cost(tpl, payload):
                out.append(Candidate(
                    key=f"call_{key.lower()}", kind="air_call",
                    desc=f"呼叫 {tpl.name}（{n_bomb} 弹，{_air_cost(tpl, payload)} 点＋弹费按发）"
                         + ("打击可见敌情" if foes else "待命敌情"),
                    utility=50 if foes else 25,
                    params={"key": key, "payload": payload}))
        elif role is AirRole.FIGHTER:
            if p.air_points >= _air_cost(tpl, {}):
                out.append(Candidate(
                    key=f"call_{key.lower()}", kind="air_call",
                    desc=f"呼叫 {tpl.name} 夺取制空权",
                    utility=40 if foe_air else 30,
                    params={"key": key, "payload": {}}))
        elif role is AirRole.RECON:
            if p.air_points >= _air_cost(tpl, {}):
                out.append(Candidate(
                    key=f"call_{key.lower()}", kind="air_call",
                    desc=f"呼叫 {tpl.name} 侦察敌情（标记圈）", utility=35,
                    params={"key": key, "payload": {}}))
        elif role is AirRole.TRANSPORT:
            slot = _paratroop_slot(p)
            if slot is not None and p.air_points >= _air_cost(tpl, {}):
                out.append(Candidate(
                    key=f"call_troop_{key.lower()}", kind="air_call",
                    desc=f"呼叫 {tpl.name} 装载预备队 {slot.template.name}"
                         f"（余 {slot.copies_left} 份）——预备队池已付，仅机体价",
                    utility=45,
                    params={"key": key,
                            "payload": {"PARATROOP": True}}))   # 执行期换模板引用
            price = tpl.payload_price.get("SUPPLY", 0)
            max_sup = tpl.payload_max_supply if price == 0 else min(
                tpl.payload_max_supply,
                max(0, (p.air_points - tpl.cost_body) // price))
            if max_sup > 0:
                payload = {"SUPPLY": max_sup}
                if p.air_points >= _air_cost(tpl, payload):
                    out.append(Candidate(
                        key=f"call_supply_{key.lower()}", kind="air_call",
                        desc=f"呼叫 {tpl.name} 空投 {max_sup} 补给",
                        utility=20,
                        params={"key": key, "payload": payload}))

    if not out:
        return [wait]
    out.sort(key=lambda c: (-c.utility, c.key))
    if len(out) >= limit:
        out = out[: limit - 1]
    out.append(wait)
    return out


# ── 内部查找（生成/执行同拍，id 必然可解析；防御性 None 兜底不进命令流）──

def _unit_by_id(world, unit_id: int):
    for u in world.units:
        if u.id == unit_id and u.alive:
            return u
    return None


def _element_by_id(world, unit_id: int, element_id: int):
    u = _unit_by_id(world, unit_id)
    if u is None:
        return None
    for e in u.elements:
        if e.id == element_id and e.hp_current > 0:
            return e
    return None


def _first_armed_element(u):
    """首个有射程>0 武器的元素（AttackCmd 的 element 位）。"""
    for e in u.elements:
        if any(ws.template.max_range_cm > 0 and ws.ammo_left > 0
               for ws in e.weapon_states):
            return e
    return None


def _eligible_carrier(squad_u, mine):
    """cmd_mount 门内预检：同点位+双静止+座有余+载具模式可载人（⑦⑧门）。"""
    for cu in mine:
        if cu.pos != squad_u.pos or cu.moving():
            continue
        for e in cu.elements:
            if e.template.seats <= 0:
                continue
            if e.mode in (Mode.CARGO, Mode.TOW) or e.towed is not TowState.NONE:
                continue                       # ⑦ 载货/拖曳不载人
            ms = cu.template.mode_set
            if (ms & (1 << Mode.TRANSPORT)) and e.mode is not Mode.TRANSPORT:
                continue                       # ⑧ 三模式卡车须处 TRANSPORT
            if e.hp_current <= 0:
                continue
            return cu
    return None


def _nearest_unowned(world, pos, my_team: int):
    best, best_d = None, None
    for o in world.objectives:
        if o.owner == my_team:
            continue
        d = _dist_cm(pos, o.pos)
        if best_d is None or d < best_d or (d == best_d and o.id < best.id):
            best, best_d = o, d
    return best


def _dist_cm(a, b) -> int:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    # 整数欧氏距离（isqrt 下取整——确定性，无浮点）
    return math.isqrt(dx * dx + dy * dy)


def enumerate_candidates_v3(world, player_index: int, *, artillery_issued: set,
                            enemy_anchor, limit: int = 16) -> list:
    """v3 候选集（进化代①——Churchill AIIDE 2012 集中火力启发式的候选空间版）：
    在 v2 全集之上追加 ① 每单位对**第二个**射程内敌目标的攻击候选（集中火力
    选择空间交推演裁决）；② 炮兵对**可见敌集群质心**的射击候选（v2 只打敌
    纵深锚点——敌情可见时空炸锚点是浪费）。确定性同 v2（纯排序零掷骰）。"""
    cands = enumerate_candidates(world, player_index,
                                 artillery_issued=artillery_issued,
                                 enemy_anchor=enemy_anchor, limit=10 ** 9)
    out = list(cands)
    seen = {c.key for c in out}
    my_team = world.players[player_index].team
    mine = [u for u in world.units if u.alive and u.team == my_team]
    foes = [u for u in world.units
            if u.alive and u.team != my_team and (u.spotted_mask >> my_team) & 1]

    # ① 第二攻击目标（每单位至多一个补充候选——与首选目标不同的敌单位）
    for u in mine:
        max_range = max((ws.template.max_range_cm
                         for e in u.elements for ws in e.weapon_states),
                        default=0)
        if max_range <= 0:
            continue
        in_range = sorted((f for f in foes
                           if f.elements and _dist_cm(u.pos, f.pos) <= max_range),
                          key=lambda f: (_dist_cm(u.pos, f.pos), f.id))
        added = 0
        for foe in in_range:
            tgt = min(foe.elements, key=lambda e: (e.hp_current, e.id))
            key = f"atk_u{u.id}_e{tgt.id}"
            if key in seen:
                continue
            shooter = _first_armed_element(u)
            if shooter is None:
                break
            seen.add(key)
            out.append(Candidate(
                key=key, kind="attack",
                desc=f"{u.template.name}(#{u.id}) 转火 {foe.template.name}"
                     f"(#{foe.id})，距离 {_dist_cm(u.pos, foe.pos)//100}m",
                utility=39 - _dist_cm(u.pos, foe.pos) // 100_000,
                params={"unit_id": u.id, "element_id": shooter.id,
                        "target_unit_id": foe.id, "target_element_id": tgt.id}))
            added += 1
            if added >= 1:
                break

    # ② 炮兵打敌集群质心（有可见敌情时优于炸纵深锚点）
    if foes:
        for c in cands:
            if c.kind == "artillery":
                cx = sum(f.pos[0] for f in foes) // len(foes)
                cy = sum(f.pos[1] for f in foes) // len(foes)
                key = f"arty2_u{c.params['unit_id']}"
                if key not in seen:
                    out.append(Candidate(
                        key=key, kind="artillery",
                        desc=f"火支(#{c.params['unit_id']}) 向可见敌集群质心 "
                             f"({cx//100}m,{cy//100}m) 下炮击任务",
                        utility=54, params={"unit_id": c.params["unit_id"],
                                            "point": [cx, cy]}))
                break

    # ③ 攻击最弱单位（Churchill Attack-Weakest）：目标=存活元素血量和最小的
    #    射程内敌单位（与表序最近者不同的才是新候选）
    for u in mine:
        max_range = max((ws.template.max_range_cm
                         for e in u.elements for ws in e.weapon_states),
                        default=0)
        if max_range <= 0:
            continue
        in_range = [f for f in foes
                    if f.elements and _dist_cm(u.pos, f.pos) <= max_range]
        if not in_range:
            continue
        weakest = min(in_range,
                      key=lambda f: (sum(e.hp_current for e in f.elements),
                                     f.id))
        tgt = min(weakest.elements, key=lambda e: (e.hp_current, e.id))
        key = f"atkw_u{u.id}_e{tgt.id}"
        if key not in seen:
            shooter = _first_armed_element(u)
            if shooter is not None:
                out.append(Candidate(
                    key=key, kind="attack",
                    desc=f"{u.template.name}(#{u.id}) 集火最弱 "
                         f"{weakest.template.name}(#{weakest.id})，"
                         f"距离 {_dist_cm(u.pos, weakest.pos)//100}m",
                    utility=38 - _dist_cm(u.pos, weakest.pos) // 100_000,
                    params={"unit_id": u.id, "element_id": shooter.id,
                            "target_unit_id": weakest.id,
                            "target_element_id": tgt.id}))

    # ④ 残血撤退（kiting 防御面）：血量 <40% 且在敌武器射程内的单位，
    #    向己方底边撤退候选（效用低于推进——兜底不选，交推演裁决）
    for u in mine:
        hp = sum(e.hp_current for e in u.elements)
        hp_max = sum(e.template.hp_max for e in u.elements)
        if hp_max <= 0 or hp * 5 >= hp_max * 2:
            continue
        near_foe = any(_dist_cm(u.pos, f.pos) <= 120000 for f in foes)
        if not near_foe or u.moving():
            continue
        key = f"retreat_u{u.id}"
        if key not in seen:
            ex, ey = world.map_extent
            home_y = 0 if my_team == 0 else ey
            out.append(Candidate(
                key=key, kind="advance",
                desc=f"{u.template.name}(#{u.id}) 残血撤离火线（退往己方底边）",
                utility=15, params={"unit_id": u.id,
                                    "dest": [u.pos[0], home_y]}))

    out.sort(key=lambda c: (-c.utility, c.key))
    return out[:limit]
