#!/usr/bin/env python3
"""A/B 对阵工具：四块班组 vs 单体玩家（模型/规则任意组合）+ 全兵种调用覆盖统计。

用法（SOV_SS 仓库根目录）：
  # 零模型冒烟（秒级，验证全兵种覆盖）：
  python3 tools/kev_ab_match.py --smoke
  # 真模型对局（本任务：四块班组带模型 vs 单体无模型 argmax）：
  .venv-kev/bin/python tools/kev_ab_match.py --kev-path kev --seeds 11 12 13 14

场景为全兵种卡组（比 demo 多：侦察/防空/补给卡车/驻楼卡+建筑），确保
各种单位的调用情况都有：步兵×2/坦克/火支炮/侦察/防空炮/牵引烟幕卡车×2/
摩托化班卡/补给卡车/驻楼卡 + 预备队空降卡；航空侧五型（攻击/轰炸/战斗/
侦察/运输）经 TEAM_AIR_KEYS 全量可呼。对局后从决策日志+终局世界统计：
每种卡购买与否、每单位收令与否、每型飞机呼叫与否。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if "--kev-path" in sys.argv:
    sys.path.insert(0, sys.argv[sys.argv.index("--kev-path") + 1])

import kev_game_demo as demo  # noqa: E402
from sovs.sim.air import PHASE_DEPLOY  # noqa: E402
from sovs.sim.tick import (Building, DeckSlot, Objective, make_world,  # noqa: E402
                           world_tick)
from sovs.sim.types import (AltTier, DamageType, ElementTemplate,  # noqa: E402
                            ElementType, Mode, MovementClass, TargetDomain,
                            Trajectory, UnitFlag, UnitTemplate, UnitType,
                            WeaponTemplate)

RIFLE_W = demo.RIFLE_TPL.element_templates[0].weapons[0]
CANNON_W = demo.TANK_TPL.element_templates[0].weapons[0]
AA_W = WeaponTemplate(                    # 对空炮（防空链载体——照验收测试数值档）
    name="aa gun", target_mask=TargetDomain.AIR, damage_type=DamageType.HE,
    pen_max=30, damage=25, blast_radius_cm=800, salvo=1,
    aim_time_ticks=5, reload_time_ticks=80, ammo_base=40,
    max_range_cm=25000, dispersion_cm=300, accuracy_base_bp=5500,
    projectile_speed_cm_tick=4000, trajectory=Trajectory.DIRECT,
    suppression_power=5, reveal_time_ticks=5)

RECON_TPL = UnitTemplate(                 # 侦察分队（category 0——高光学高隐蔽）
    template_id=951, name="recon team", category=0, cost=40,
    element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                       unit_type=UnitType.INFANTRY, hp_max=6,
                                       weapons=(RIFLE_W,)),),
    optics_ground_cm=140000, stealth_base=9, speed_tier=1,
    movement_class=MovementClass.FOOT)
AA_TPL = UnitTemplate(                    # 防空炮连（category 4——对空链）
    template_id=952, name="aa battery", category=4, cost=60,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=10,
        weapons=(AA_W,)),) * 2,
    optics_ground_cm=60000, optics_air_cm=60000, stealth_base=3,
    speed_tier=1, movement_class=MovementClass.FOOT,
    air_ceiling=AltTier.HIGH)
SUPPLY_TPL = UnitTemplate(                # 补给卡车（HAS_SUPPLY——买补给链）
    template_id=953, name="supply truck", category=4, cost=45,
    element_templates=(ElementTemplate(
        element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=12,
        cargo_rounds_max=600, cargo_medical_max=40,
        cargo_weight_max=800),),
    optics_ground_cm=80000, stealth_base=4, speed_tier=3,
    movement_class=MovementClass.WHEEL,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.CARGO) | (1 << Mode.TRANSPORT),
    flags=UnitFlag.HAS_SUPPLY)
GAR_TPL = UnitTemplate(                   # 驻楼资格卡（CAN_GARRISON）
    template_id=954, name="garrison squad", category=1, cost=50,
    element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                       unit_type=UnitType.INFANTRY, hp_max=10,
                                       weapons=(RIFLE_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_GARRISON)

# 全兵种卡组：步×2/坦/炮/侦/防/牵引×2/摩步/补给/驻楼 + 预备队空降（装机时走）
DECK = ((demo.RIFLE_TPL, 2), (demo.TANK_TPL, 1), (demo.GUN_TPL, 1),
        (RECON_TPL, 1), (AA_TPL, 1), (demo.TRUCK_TPL, 2),
        (demo.MIXED_TPL, 1), (SUPPLY_TPL, 1), (GAR_TPL, 1))
BUILDINGS = (Building(id=1, pos=(90000, 50000), hp=100, garrison_slots=2),
             Building(id=2, pos=(110000, 50000), hp=100, garrison_slots=2))


def match_world(seed: int):
    w = make_world(seed, phase=PHASE_DEPLOY, size_cm=(200000, 100000))
    w.objectives.append(Objective(id=1, pos=(100000, 50000), radius_cm=5000))
    w.buildings.extend(BUILDINGS)
    for p in w.players:
        p.deck_slots = [DeckSlot(t, n) for t, n in DECK]
        p.deck_slots.append(DeckSlot(demo.PARA_TPL, 1))
    return w


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="四块班组 vs 单体 A/B 对阵工具")
    ap.add_argument("--smoke", action="store_true",
                    help="零模型冒烟（双方规则，验证全兵种覆盖）")
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13, 14])
    ap.add_argument("--kev-path", default=None)
    ap.add_argument("--a-side", choices=["squad", "player"], default="squad",
                    help="A 方类（缺省四块班组）")
    ap.add_argument("--a-model", choices=["on", "off"], default="on")
    ap.add_argument("--gate", type=float, default=0.0,
                    help="A 方置信度门控阈值（模型首选概率低于此→argmax，0=关）")
    args = ap.parse_args(argv)

    if args.smoke:
        from sovs.ai.agents import AgentSquad
        from sovs.ai import KevPlayer
        mk_a = lambda w, i: AgentSquad(i, None, anchors=(demo.SOUTH, demo.NORTH))
        mk_b = lambda w, i: KevPlayer(i, None, anchors=(demo.SOUTH, demo.NORTH))
        client = None
    else:
        from sovs.ai.agents import AgentSquad
        from sovs.ai import KevPlayer, LocalKevEngine
        client = LocalKevEngine(kev_path=args.kev_path)
        if args.a_side == "squad":
            mk_a = lambda w, i: AgentSquad(i, client,
                                           anchors=(demo.SOUTH, demo.NORTH))
        else:
            mk_a = lambda w, i: KevPlayer(i, client,
                                          anchors=(demo.SOUTH, demo.NORTH))
        mk_b = lambda w, i: KevPlayer(i, None, anchors=(demo.SOUTH, demo.NORTH))

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        # 决策日志走临时文件以做覆盖统计
        from sovs.ai.decision_log import DecisionLog
        logs = [os.path.join(td, f"l{i}.jsonl") for i in range(len(args.seeds) * 2)]

        results, purchases, aircalls = [], Counter(), Counter()
        unit_cmds, cmd_kinds = Counter(), Counter()
        li = 0
        for seed in args.seeds:
            for a_side in (0, 1):
                w = match_world(seed)
                from sovs.ai.agents import AgentSquad
                from sovs.ai import KevPlayer
                base_a = AgentSquad if args.a_side == "squad" else KevPlayer
                mk = {a_side: lambda i=a_side: (base_a(i, client, anchors=(
                    demo.SOUTH, demo.NORTH), log=logs[li],
                    min_top_prob=args.gate)),
                      1 - a_side: lambda i=1 - a_side: KevPlayer(
                          i, None, anchors=(demo.SOUTH, demo.NORTH),
                          log=logs[li])}
                pa, pb = mk[a_side](), mk[1 - a_side]()
                id2name = {}                       # 持续快照：单位阵亡移出前记下
                while w.tick < 15000 and w.result is None:
                    pa.step(w)
                    pb.step(w)
                    world_tick(w)
                    if w.tick % 10 == 0:
                        for u in w.units:
                            id2name.setdefault(u.id, u.template.name)
                for u in w.units:
                    id2name.setdefault(u.id, u.template.name)
                pa.close(); pb.close()
                win = (w.result.winner == a_side) if w.result else None
                results.append(win)
                # 覆盖：购买（deck 余量减少即购过）
                want = {t.template_id: n for t, n in DECK}
                for p in w.players:
                    for s in p.deck_slots:
                        if want.get(s.template.template_id, 1) - s.copies_left > 0:
                            purchases[s.template.name] += 1
                # 覆盖：飞机呼叫从日志统计（终局快照漏掉已返场/被击落的）
                # 覆盖：每单位收令（日志 unit 字段 → 模板名）
                id2name = {u.id: u.template.name for u in w.units}
                with open(logs[li], encoding="utf-8") as fh:
                    for line in fh:
                        r = json.loads(line)
                        for c in r.get("commands", []):
                            cmd_kinds[c["cmd"]] += 1
                            if c["cmd"] == "AirCallCmd":
                                aircalls[c["aircraft"]] += 1
                            for key in ("unit", "towed_unit", "tower_unit_id",
                                        "squad_unit_id"):
                                if isinstance(c.get(key), int) and c[key] in id2name:
                                    unit_cmds[id2name[c[key]]] += 1
                li += 1

    wins = sum(1 for r in results if r)
    n = len(results)
    print(f"\n═══ A({args.a_side}+{'模型' if client else '规则'}) vs B(player+规则)："
          f"{wins}胜/{n}局 ═══")
    print("\n── 兵种调用覆盖（购买过的卡 / 收过令的单位 / 起飞过的机型）──")
    all_names = sorted({t.name for t, _ in DECK} | {demo.PARA_TPL.name})
    for name in all_names:
        print(f"  {name:14s} 购买{purchases.get(name, 0)}次 收令{unit_cmds.get(name, 0)}次")
    for key in ("IL2M", "PE2", "YAK9", "PO2", "LI2"):
        from sovs.sim.air_data import CARD_OBJECTS
        print(f"  {CARD_OBJECTS[key].name:14s} 起飞{aircalls.get(CARD_OBJECTS[key].name, 0)}架次")
    print("\n── 命令种类分布 ──")
    for k, v in cmd_kinds.most_common():
        print(f"  {k:22s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
