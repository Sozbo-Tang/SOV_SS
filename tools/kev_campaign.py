#!/usr/bin/env python3
"""Kev-0.5B agent 战役工具：堆满卡组场景 / 数据工厂 / 评估接线。

子命令（stdin/stdout 管道面——本工具不做任何文件读写，落盘由调用方
shell 重定向完成）：
  gen    规则 vs 规则（或变体策略）自对局 → kev.train 训练记录 JSONL（stdout）
         --mode clone  双侧 argmax（行为克隆，label=效用榜首）
         --mode winner 双侧变体策略（效用 softmax 采样），只留胜者侧决策
  stats  从 stdin 读训练记录 → 统计（记录数/角色分布/state 长度抽检）

场景纪律（用户拍板）：双方同卡组且"主力+预备队分数堆满"——主力卡总成本
1490 ≥ 购卡点数 1000（购买期必然掏空点数），预备队空降卡 ×20（编制 1200
分；预备队池 D017 编制 5000 非运行时预算，以"份量堆满+对局内真实投放"为准）。

用法：
  python3 tools/kev_campaign.py gen --mode clone --n-games 20 --seed0 1000 \
      > data/kev_ft/train.jsonl
  python3 tools/kev_campaign.py stats < data/kev_ft/train.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from sovs.ai.agents import AgentSquad  # noqa: E402
from sovs.ai.kev_client import KevChoiceAnswer  # noqa: E402
from sovs.sim.tick import DeckSlot, make_world, world_tick  # noqa: E402
from sovs.sim.types import UnitFlag  # noqa: E402
import tools.kev_ab_match as ab  # noqa: E402
import tools.kev_game_demo as demo  # noqa: E402

ANCHORS = (demo.SOUTH, demo.NORTH)


def full_world(seed: int):
    """堆满卡组对局世界（双方同卡组：主力 1490 分 + 预备队空降 ×20）。"""
    w = ab.match_world(seed)
    for p in w.players:
        p.deck_slots.append(DeckSlot(ab.PARA_TPL, 20))
    return w


class _VariantEngine:
    """变体策略引擎（数据多样性源）：效用 softmax 采样（种子确定性）。

    与规则 argmax 的差异提供反事实覆盖——胜者侧标注才有超越 argmax 的信息。
    """

    def __init__(self, seed: int, temperature: float = 12.0):
        self._state = (seed * 2654435761) & 0xFFFFFFFF or 0x9E3779B9
        self.t = temperature

    def _next(self) -> float:
        # xorshift32——确定性零依赖（均匀 [0,1)）
        x = self._state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self._state = x & 0xFFFFFFFF
        return self._state / 0x100000000

    def choose(self, state, question_id, instructions, options, utilities=None):
        if not utilities:
            probs = {k: 1.0 / len(options) for k in options}
        else:
            mx = max(utilities.values())
            exps = {k: math.exp((u - mx) / self.t) for k, u in utilities.items()}
            z = sum(exps.values())
            probs = {k: v / z for k, v in exps.items()}
        r = self._next()
        acc = 0.0
        last = next(iter(options))
        for k in options:                       # options 插入序=候选效用序
            acc += probs.get(k, 0.0)
            last = k
            if r <= acc:
                return KevChoiceAnswer(question_id, k, 0.0, probs)
        return KevChoiceAnswer(question_id, last, 0.0, probs)

    def ping(self):
        return True


def _play_one(seed: int, side: int, *, variant: bool):
    """一局规则（或变体）自对局；返回 (胜者 team|None, [该 side 决策记录])。

    记录形状（kev.data.load_records 兼容 + 战役元数据 _battle）。
    """
    from sovs.ai.actions import build_commands
    from sovs.sim.tick import queue_command

    w = full_world(seed)
    eng = _VariantEngine(seed * 2 + side + 1) if variant else None
    recs: list[dict] = []

    class _Hook(AgentSquad):
        """AgentSquad 变体：拦截决策收集训练记录。"""

        def _choose_and_run(self, world, role, cands, *, phase, p):
            options = {c.key: c.desc for c in cands}
            utilities = {c.key: c.utility for c in cands}
            if eng is None:
                chosen_key = cands[0].key        # argmax（候选已按效用排序）
                probs = {}
            else:
                ans = eng.choose({}, AgentSquad._QID[role],
                                 AgentSquad._INSTRUCTIONS[role], options,
                                 utilities)
                chosen_key = ans.choice
                probs = ans.probabilities
            chosen = next(c for c in cands if c.key == chosen_key)
            for cmd in build_commands(world, p, chosen):
                queue_command(world, cmd)
            q: dict = {"type": "choice",
                       "instructions": AgentSquad._INSTRUCTIONS[role],
                       "criteria": options, "label": chosen_key}
            if probs:                            # 变体：采样分布作软目标
                q["target"] = {k: round(v, 4) for k, v in probs.items()}
            elif len(cands) > 1:                 # 克隆：效用 softmax 软目标
                mx = max(utilities.values())
                exps = {k: math.exp((u - mx) / 15.0)
                        for k, u in utilities.items()}
                z = sum(exps.values())
                q["target"] = {k: round(v / z, 4) for k, v in exps.items()}
            recs.append({"state": self._state(world),
                         "questions": {AgentSquad._QID[role]: q},
                         "_battle": {"seed": seed, "side": side,
                                     "role": role, "tick": world.tick}})
            return chosen

    red = _Hook(0, None, anchors=ANCHORS, label=f"s{seed}a")
    blue = _Hook(1, None, anchors=ANCHORS, label=f"s{seed}b")
    while w.tick < 15000 and w.result is None:
        red.step(w)
        blue.step(w)
        world_tick(w)
    red.close()
    blue.close()
    return (w.result.winner if w.result else None), recs


def cmd_gen(args) -> int:
    n_rec = 0
    for seed in range(args.seed0, args.seed0 + args.n_games):
        for side in (0, 1):
            winner, recs = _play_one(seed, side,
                                     variant=args.mode == "winner")
            if args.mode == "winner" and winner != side:
                continue                         # 只留胜者侧决策
            for r in recs:
                r["_battle"]["winner"] = (winner == side)
                sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")
                n_rec += 1
        if seed % 10 == 0:
            print(f"  … seed={seed} 累计 {n_rec} 记录", file=sys.stderr)
    print(f"✓ {n_rec} 条记录（mode={args.mode}，{args.n_games} 局×2 位）",
          file=sys.stderr)
    return 0


def cmd_stats(args) -> int:
    from collections import Counter
    roles: Counter = Counter()
    n = 0
    max_len = 0
    for line in sys.stdin:
        if not line.strip():
            continue
        r = json.loads(line)
        n += 1
        q = next(iter(r["questions"].values()))
        roles[q["instructions"][:12]] += 1
        max_len = max(max_len, len(r["state"]))
    print(f"记录 {n} · 最大 state 字符 {max_len}（Qwen2.5 约 2~3 字符/token，"
          f"须 <384 token）")
    for k, v in roles.most_common():
        print(f"  {k}… {v}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kev-0.5B agent 战役工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen", help="规则自对局 → kev 训练记录（stdout）")
    g.add_argument("--n-games", type=int, default=20)
    g.add_argument("--seed0", type=int, default=1000)
    g.add_argument("--mode", choices=["clone", "winner"], default="clone",
                   help="clone=双侧 argmax 克隆；winner=变体策略+只留胜者侧")
    s = sub.add_parser("stats", help="训练数据统计（stdin）")
    args = ap.parse_args(argv)
    if args.cmd == "gen":
        return cmd_gen(args)
    return cmd_stats(args)


if __name__ == "__main__":
    sys.exit(main())
