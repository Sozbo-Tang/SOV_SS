#!/usr/bin/env python3
"""Kev agent 代际对阵工具：任意两代 agent A/B 对战 + 全兵种调用覆盖统计。

代际注册表 --a-kind/--b-kind：
  player  KevPlayer（带模型=单体 0.5B；不带=规则 argmax）
  squad   AgentSquad（四块角色班组；不带模型=规则班组）
  v2      KevAgentV2（kev 提案+引擎推演校验）
  v3      KevAgentV3（v2+全目标攻击/炮兵打集群/推演位置项/自适应视野）
  v4      KevAgentV4（第②轮进化）

用法：
  # 规则自检（零模型）：
  python3 tools/kev_ab_match.py --smoke
  # v3(带模型) vs v2(带模型)，堆满卡组，6 seed 双侧：
  .venv-kev/bin/python tools/kev_ab_match.py --kev-path kev --full-deck \
      --a-kind v3 --b-kind v2 --seeds 41 42 43
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

SOUTH, NORTH = (100000, 0), (100000, 100000)

RIFLE_W = demo.RIFLE_TPL.element_templates[0].weapons[0]
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
    speed_tier=1, movement_class=MovementClass.FOOT, air_ceiling=AltTier.HIGH)
SUPPLY_TPL = UnitTemplate(                # 补给卡车（HAS_SUPPLY——买补给链）
    template_id=953, name="supply truck", category=4, cost=45,
    element_templates=(ElementTemplate(
        element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=12,
        cargo_rounds_max=600, cargo_medical_max=40, cargo_weight_max=800),),
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
PARA_TPL = UnitTemplate(                  # 预备队空降卡（购卡门恒拒——投送链走运输机）
    template_id=955, name="paratroop plt", category=1, cost=60,
    element_templates=(demo.RIFLE_TPL.element_templates[0],) * 3,
    optics_ground_cm=120000, stealth_base=6, speed_tier=1,
    movement_class=MovementClass.FOOT,
    flags=UnitFlag.DELIVERY_AIRDROP_ONLY)

# 全兵种卡组：步×2/坦/炮/侦/防/牵引烟幕卡车×2/摩步/补给/驻楼（1480 分 ≥1000 预算）
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
        p.deck_slots = [DeckSlot(tpl, n) for tpl, n in DECK]
    return w


def _mk_kind(kind: str, index: int, client, *, anchors, log, gate: float,
             eps: float, horizon: int, pos_weight: int = 1):  # noqa: ARG001
    """代际 → agent 实例。horizon 对 v2 固定生效；v3 的 horizon 语义由
    --b-horizon 单侧覆盖（见 main）。"""
    """代际 → agent 实例（client=None 即规则版）。"""
    if kind == "player":
        from sovs.ai import KevPlayer
        return KevPlayer(index, client, anchors=anchors, log=log,
                         min_top_prob=gate)
    if kind == "squad":
        from sovs.ai.agents import AgentSquad
        return AgentSquad(index, client, anchors=anchors, log=log,
                          min_top_prob=gate)
    if kind == "v2":
        from sovs.ai.agent_v2 import KevAgentV2
        return KevAgentV2(index, client, anchors=anchors, log=log,
                          min_top_prob=gate, eps=eps, horizon=horizon)
    if kind == "v3":
        from sovs.ai.agent_v3 import KevAgentV3
        return KevAgentV3(index, client, anchors=anchors, log=log,
                          min_top_prob=gate, eps=eps, horizon=horizon,
                          pos_weight=pos_weight)
    if kind == "v4":
        from sovs.ai.agent_v4 import KevAgentV4
        return KevAgentV4(index, client, anchors=anchors, log=log,
                          min_top_prob=gate, eps=eps, horizon=horizon)
    raise SystemExit(f"未知代际: {kind!r}（可选 player/squad/v2/v3/v4）")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kev agent 代际对阵工具")
    ap.add_argument("--smoke", action="store_true",
                    help="零模型冒烟（双方规则，验证全兵种覆盖）")
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13, 14])
    ap.add_argument("--kev-path", default=None)
    ap.add_argument("--a-kind", default="v2",
                    choices=["player", "squad", "v2", "v3", "v4"])
    ap.add_argument("--b-kind", default="player",
                    choices=["player", "squad", "v2", "v3", "v4"])
    ap.add_argument("--a-model", choices=["on", "off"], default="on")
    ap.add_argument("--b-model", choices=["on", "off"], default="off")
    ap.add_argument("--gate", type=float, default=0.0,
                    help="双方置信度门控阈值（0=关）")
    ap.add_argument("--eps", type=float, default=0.0,
                    help="v2+/v3/v4 推演校验容差（模型提案分 ≥ 最优-eps 则执行模型提案）")
    ap.add_argument("--horizon", type=int, default=80, help="A 侧推演拍数（战斗类候选）")
    ap.add_argument("--b-horizon", type=int, default=None,
                    help="B 侧推演拍数（缺省=与 A 侧同）")
    ap.add_argument("--pos-weight", type=int, default=1,
                    help="v3 推演位置项权重（0=关，消融用）")
    ap.add_argument("--run", default=None,
                    help="模型 run id 或本地 runs/ 路径（缺省 jaredpalmer/kev-0.5b）")
    args = ap.parse_args(argv)

    model_kinds = {"player", "squad", "v2", "v3", "v4"}
    a_model = args.a_model == "on" and not args.smoke
    b_model = args.b_model == "on" and not args.smoke
    client = None
    if a_model or b_model:
        from sovs.ai import LocalKevEngine
        client = LocalKevEngine(args.run or "jaredpalmer/kev-0.5b",
                                kev_path=args.kev_path)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        logs = [os.path.join(td, f"l{i}.jsonl")
                for i in range(len(args.seeds) * 2)]
        results, purchases, aircalls = [], Counter(), Counter()
        unit_cmds, cmd_kinds = Counter(), Counter()
        li = 0
        for seed in args.seeds:
            for a_side in (0, 1):
                w = match_world(seed)
                for p in w.players:            # 预备队大堆（堆满口径）
                    p.deck_slots.append(DeckSlot(PARA_TPL, 20))
                agents = {}
                b_horizon = args.b_horizon if args.b_horizon is not None \
                    else args.horizon
                for idx, kind, has_model, hz in (
                        (a_side, args.a_kind, a_model, args.horizon),
                        (1 - a_side, args.b_kind, b_model, b_horizon)):
                    agents[idx] = _mk_kind(
                        kind, idx, client if has_model else None,
                        anchors=(demo.SOUTH, demo.NORTH), log=logs[li],
                        gate=args.gate, eps=args.eps, horizon=hz,
                        pos_weight=args.pos_weight)
                pa, pb = agents[a_side], agents[1 - a_side]
                id2name = {}
                while w.tick < 15000 and w.result is None:
                    pa.step(w)
                    pb.step(w)
                    world_tick(w)
                    if w.tick % 10 == 0:
                        for u in w.units:
                            id2name.setdefault(u.id, u.template.name)
                for u in w.units:
                    id2name.setdefault(u.id, u.template.name)
                pa.close()
                pb.close()
                win = (w.result.winner == a_side) if w.result else None
                results.append(win)
                want = {t.template_id: n for t, n in DECK}
                for p in w.players:
                    for s in p.deck_slots:
                        if want.get(s.template.template_id, 1) - s.copies_left > 0:
                            purchases[s.template.name] += 1
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
    print(f"\n═══ A({args.a_kind}{'模型' if a_model else '规则'}) vs "
          f"B({args.b_kind}{'模型' if b_model else '规则'})：{wins}胜/{n}局 ═══")
    print("\n── 兵种调用覆盖（购买过的卡 / 收过令的单位 / 起飞过的机型）──")
    all_names = sorted({t.name for t, _ in DECK} | {PARA_TPL.name})
    for name in all_names:
        print(f"  {name:14s} 购买{purchases.get(name, 0)}次 收令{unit_cmds.get(name, 0)}次")
    from sovs.sim.air_data import CARD_OBJECTS
    for key in ("IL2M", "PE2", "YAK9", "PO2", "LI2"):
        print(f"  {CARD_OBJECTS[key].name:14s} 起飞{aircalls.get(CARD_OBJECTS[key].name, 0)}架次")
    print("\n── 命令种类分布 ──")
    for k, v in cmd_kinds.most_common():
        print(f"  {k:22s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
