#!/usr/bin/env python3
"""1Hz 作战指令下发节奏测试：进程内 Kev-0.5B 决策，实测每秒一条指令能否守住。

测的是**完整链路**（非裸模型）：每节拍 = 态势摘要 → 候选枚举 → 模型前向
（或规则 argmax）→ 命令构造 → queue_command → consume_commands 引擎落地，
随后推进 10 拍模拟时间（1 实秒 ↔ 1 游戏秒 @10Hz）让态势演化；按 --pace
（缺省 1.0s）补足节拍。判定：所有节拍周期 ≤ 预算（1000ms）即 PASS。

两种引擎：
  --engine local     进程内加载 Kev-0.5B（LocalKevEngine——torch 后端
                     cuda/mps/cpu 自动探测，**不起任何端口服务**；需先
                     pip install -e ./kev，首跑自动从 HF 拉权重缓存）
  --engine fallback  纯规则 argmax（零模型依赖——先验证测试台本身）
  --mode player      KevPlayer 单体驱动（缺省——行为与本工具旧版逐位一致）
  --mode squad       AgentSquad 四角色班组驱动（每拍恰一次角色决策，
                     地面→空中→预备队 固定轮转；squad_every=1 对齐
                     测试台"每迭代一拍"的节拍结构）

用法（SOV_SS 仓库根目录）：
  python tools/kev_bench_1hz.py --engine fallback          # 测试台自检
  python tools/kev_bench_1hz.py                            # 真模型 1Hz 实测
  python tools/kev_bench_1hz.py --decisions 120 --dtype bf16

输出：逐拍周期/模型前向延迟的 min/p50/p95/max、输入 token、命令落地点、
实际达成节拍（decisions/墙钟）、PASS/FAIL 判定。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.ai import AgentSquad, KevPlayer, LocalKevEngine  # noqa: E402
from sovs.ai.kev_client import KevUnavailableError  # noqa: E402
from sovs.sim.air import PHASE_COMBAT  # noqa: E402
from sovs.sim.tick import (DeckSlot, Objective, add_unit, consume_commands,  # noqa: E402
                           make_unit, make_world, world_tick)
from sovs.sim.types import (Armor, DamageType, ElementTemplate,  # noqa: E402
                            ElementType, Mode, MovementClass, TargetDomain,
                            Trajectory, UnitTemplate, UnitType,
                            WeaponTemplate)

# ── 合成卡（照 tests/test_fullgame_acceptance 数值档——锚点服务非平衡档）──

RIFLE_W = WeaponTemplate(
    name="rifle", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    damage=2, salvo=1, aim_time_ticks=5, reload_time_ticks=30, ammo_base=50,
    max_range_cm=120000, dispersion_cm=500, accuracy_base_bp=6000,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    suppression_power=3, reveal_time_ticks=10)
CANNON_W = WeaponTemplate(
    name="cannon", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    pen_min=6, pen_max=9, damage=6, salvo=1, aim_time_ticks=6,
    reload_time_ticks=50, ammo_base=30, max_range_cm=115000,
    dispersion_cm=400, accuracy_base_bp=6200,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    blast_radius_cm=500, suppression_power=5, reveal_time_ticks=10)

RIFLE_TPL = UnitTemplate(
    template_id=911, name="rifle plt", category=1, cost=60,
    element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                       unit_type=UnitType.INFANTRY, hp_max=10,
                                       weapons=(RIFLE_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)
TANK_TPL = UnitTemplate(
    template_id=913, name="tank", category=2, cost=180,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=15,
        armor_ke=Armor(10, 7, 5, 3), armor_he=Armor(8, 6, 4, 3),
        weapons=(CANNON_W,)),),
    optics_ground_cm=110000, stealth_base=3, speed_tier=2,
    movement_class=MovementClass.TRACK)

SOUTH, NORTH = (100000, 0), (100000, 100000)


def bench_world(seed: int):
    """实战相位对抗场景：南北各 步兵×2+坦克×1，相距 1000m（光学/射程内互见）。"""
    w = make_world(seed, phase=PHASE_COMBAT, size_cm=(200000, 100000))
    w.objectives.append(Objective(id=1, pos=(100000, 50000), radius_cm=5000))
    for p in w.players:
        p.deck_slots = [DeckSlot(RIFLE_TPL, 2), DeckSlot(TANK_TPL, 1)]
    for team, base_y in ((0, 45000), (1, 55000)):
        for k in range(3):
            tpl = TANK_TPL if k == 2 else RIFLE_TPL
            u = add_unit(w, make_unit(w, tpl, team, team,
                                      (100000 - 15000 * (k - 1), base_y)))
            u.spotted_mask = 0b11          # 双方互见（决策链有真实目标可打）
    return w


def _pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def run(args) -> int:
    # ── 引擎装配（进程内；不起端口服务）──
    engine = None
    engine_desc = "规则 argmax（零模型）"
    if args.engine == "local":
        try:
            engine = LocalKevEngine(args.run, dtype=args.dtype,
                                    device=args.device or None,
                                    kev_path=args.kev_path)
            engine_desc = (f"{engine.run} 进程内 device={engine.device} "
                           f"dtype={engine.dtype} backend={engine.backend}")
        except KevUnavailableError as e:
            print(f"✗ 模型引擎不可用：{e}")
            print("  （测试台自检可先跑：python tools/kev_bench_1hz.py "
                  "--engine fallback）")
            return 2
    print(f"引擎：{engine_desc}")
    if args.mode == "squad":
        print("驱动：AgentSquad 四角色班组（每拍一次角色决策，地面→空中→预备队 轮转）")
    print(f"节拍：pace={args.pace}s × {args.decisions} 拍（预算 "
          f"{args.pace * 1000:.0f}ms/拍），warmup={args.warmup}")

    # ── 对局装配：decide_every=1 → 每次 step 必为一拍决策 ──
    # squad 模式取 squad_every=1：测试台 warmup 逐拍推进会把 tick 错出 %10
    # 对齐位（10 拍节流会整场零决策），取 1 保证每迭代恰一次角色决策
    # （地面→空中→预备队 固定轮转——判定逻辑与 player 模式照用）。
    w = bench_world(args.seed)
    if args.mode == "squad":
        player = AgentSquad(0, engine, anchors=(SOUTH, NORTH),
                            squad_every=1, log=args.log, label="bench-squad")
    else:
        player = KevPlayer(0, engine, anchors=(SOUTH, NORTH),
                           decide_every=1, log=args.log, label="bench")
    budget_ms = args.pace * 1000 if args.pace > 0 else 1000.0

    # warmup：不计时（首拍含内核 JIT/显存分配）
    for _ in range(args.warmup):
        player.step(w)
        consume_commands(w)
        world_tick(w)
    if args.mode == "squad":
        player.reset_stats()
    else:
        player.stats = {"kev": 0, "fallback": 0}

    cycle_ms: list[float] = []
    fwd_ms: list[float] = []
    tokens: list[int] = []
    issued = 0                     # 实际入队 ≥1 条命令的拍数
    t_wall = time.perf_counter()
    for i in range(args.decisions):
        t0 = time.perf_counter()
        before = len(w.command_queue)
        player.step(w)             # 态势→候选→决策→queue_command
        cycle = (time.perf_counter() - t0) * 1000
        cycle_ms.append(cycle)
        if len(w.command_queue) > before:
            issued += 1
        if engine is not None and engine.last:
            fwd_ms.append(float(engine.last.get("latency_ms", 0.0)))
            tokens.append(int(engine.last.get("input_tokens", 0)))
        consume_commands(w)        # 引擎门序裁决落地
        for _ in range(10):        # 1 实秒 ↔ 1 游戏秒（10Hz）
            world_tick(w)
            if w.result is not None:
                break
        if w.result is not None:
            print(f"  （第 {i + 1} 拍进入结算——对局提前结束，按已完成拍统计）")
            break
        if args.pace > 0:          # 节拍纪律：补足到 pace 秒
            rest = args.pace - (time.perf_counter() - t0)
            if rest > 0:
                time.sleep(rest)
    wall = time.perf_counter() - t_wall
    player.close()

    # ── 报告 ──
    overruns = sum(1 for c in cycle_ms if c > budget_ms)
    done = len(cycle_ms)
    print("── 结果 " + "─" * 40)
    print(f"  完成拍数 {done}/{args.decisions}   入队命令拍数 {issued}")
    print(f"  整拍周期 ms：min={min(cycle_ms):.0f} p50={_pct(cycle_ms, .5):.0f} "
          f"p95={_pct(cycle_ms, .95):.0f} max={max(cycle_ms):.0f}"
          f"（预算 {budget_ms:.0f}）")
    if fwd_ms:
        print(f"  模型前向 ms：min={min(fwd_ms):.0f} p50={_pct(fwd_ms, .5):.0f} "
              f"p95={_pct(fwd_ms, .95):.0f} max={max(fwd_ms):.0f}"
              f"   输入 tokens p50={_pct([float(t) for t in tokens], .5):.0f}")
    print(f"  决策来源：kev={player.stats['kev']} fallback={player.stats['fallback']}")
    if args.mode == "squad":
        rs = player.role_stats
        print(f"  角色决策（kev/兜底）：地面={rs['ground']['kev']}/{rs['ground']['fallback']}"
              f" 空中={rs['air']['kev']}/{rs['air']['fallback']}"
              f" 预备队={rs['reserve']['kev']}/{rs['reserve']['fallback']}")
    if args.pace > 0 and done:
        print(f"  实际节拍：{done / wall:.2f} 指令/秒（墙钟 {wall:.1f}s）")
    alive = sum(1 for u in w.units if u.alive)
    print(f"  对局态：存活 {alive}/{len(w.units)} 单位，tick={w.tick}")
    verdict = "PASS" if overruns == 0 and done == args.decisions else (
        "FAIL" if overruns else "PARTIAL（对局提前结算）")
    print(f"  判定：{verdict}——超预算拍数 {overruns}/{done}")
    if args.log:
        print(f"  决策日志：{args.log}")
    return 0 if verdict.startswith(("PASS", "PARTIAL")) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="1Hz 作战指令下发节奏测试（进程内模型）")
    ap.add_argument("--engine", choices=["local", "fallback"], default="local")
    ap.add_argument("--mode", choices=["player", "squad"], default="player",
                    help="决策驱动：player=KevPlayer 单体（缺省）；"
                         "squad=AgentSquad 四角色班组（1Hz 轮转）")
    ap.add_argument("--run", default="jaredpalmer/kev-0.5b")
    ap.add_argument("--dtype", default="bf16", choices=["bf16", "fp16", "fp32"])
    ap.add_argument("--device", default=None,
                    help="强制设备（cuda/mps/cpu；缺省自动探测）")
    ap.add_argument("--kev-path", default=None,
                    help="kev 仓库路径（免 pip install 直挂 sys.path）")
    ap.add_argument("--decisions", type=int, default=60,
                    help="计时拍数（缺省 60=一分钟）")
    ap.add_argument("--pace", type=float, default=1.0,
                    help="节拍秒（缺省 1.0；0=不等待，压测裸延迟）")
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--log", default="out/bench_decisions.jsonl")
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
