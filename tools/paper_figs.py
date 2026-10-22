#!/usr/bin/env python3
r"""论文插图生成：全部使用项目实测决策日志，零虚构数据。

产出 paper/figs/ 下的 PDF 图（LaTeX 直接 \includegraphics）：
  fig_arch.pdf     propose–verify 架构图（矢量绘制）
  fig_traps.pdf    选项真实性陷阱：吸引率实测柱状
  fig_winrate.pdf  v2 agent vs 规则：两批判次 + 对称线
  fig_latency.pdf  真模型每决策时延分布（1Hz 预算线）
  fig_plateau.pdf  验证平台期：8 变体对 v2 胜率 + 50% 对称线
"""
from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGS = os.path.join(REPO, "paper", "figs")
os.makedirs(FIGS, exist_ok=True)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({"font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False})


def fig_arch() -> None:
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    ax.axis("off")
    boxes = [
        (0.01, 0.30, 0.17, 0.42, "Deterministic\nEngine (10 Hz)\ncandidates +\nutility order", "#dbeafe"),
        (0.22, 0.30, 0.17, 0.42, "Typed decision\nmodel (frozen\n0.5B)\nproposal", "#fecaca"),
        (0.43, 0.30, 0.20, 0.42, "Cloned-world\nrollout verification\n(deep-copied RNG,\nH-tick simulation)", "#fef3c7"),
        (0.67, 0.30, 0.15, 0.42, "Decision\n(ε-gate:\nproposal if\nscore ≥ best−ε)", "#dcfce7"),
        (0.86, 0.30, 0.13, 0.42, "Command\nqueue →\nengine gates", "#e5e7eb"),
    ]
    for x, y, w, h, label, c in boxes:
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=c,
                                   edgecolor="black", linewidth=0.8))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
                fontsize=7.2)
    for x0, x1 in ((0.18, 0.22), (0.39, 0.43), (0.63, 0.67), (0.82, 0.86)):
        ax.annotate("", xy=(x1, 0.51), xytext=(x0, 0.51),
                    arrowprops=dict(arrowstyle="->", lw=1.1))
    # 回放纪律侧注
    ax.text(0.5, 0.12, "seed + command stream = bit-exact replay  ·  "
            "rollouts run on deep-copied worlds (RNG channels included), "
            "real timeline untouched",
            ha="center", fontsize=7, style="italic", color="#374151")
    ax.text(0.475, 0.80, "propose", fontsize=7.5, ha="center")
    ax.text(0.70, 0.80, "verify", fontsize=7.5, ha="center")
    fig.savefig(os.path.join(FIGS, "fig_arch.pdf"), bbox_inches="tight")
    plt.close(fig)


def fig_traps() -> None:
    labels = ["wait option\n(air role)", "wait option\n(reserve role)",
              "ferry lock\n(transport)", "unbuyable card\n(purchase beat)"]
    vals = [435 / 440 * 100, 440 / 440 * 100, 273 / 281 * 100, 7 / 13 * 100]
    counts = ["435/440", "440/440", "273/281", "7/13"]
    fig, ax = plt.subplots(figsize=(4.6, 2.5))
    bars = ax.barh(range(len(vals))[::-1], vals, color="#f87171", height=0.55)
    ax.set_yticks(range(len(vals))[::-1], labels, fontsize=8)
    ax.set_xlabel("trap-option selection / wasted-beat rate (%)")
    ax.set_xlim(0, 112)
    for b, c in zip(bars, counts):
        ax.text(b.get_width() + 1.5, b.get_y() + b.get_height() / 2, c,
                va="center", fontsize=8)
    ax.axvline(50, color="gray", lw=0.8, ls="--")
    ax.text(50, len(vals) - 0.4, "chance", fontsize=7, color="gray")
    fig.savefig(os.path.join(FIGS, "fig_traps.pdf"), bbox_inches="tight")
    plt.close(fig)


def fig_winrate() -> None:
    fig, ax = plt.subplots(figsize=(3.6, 2.5))
    batches = ["batch 1\n(seeds 21–26)", "batch 2\n(seeds 31–36)", "total"]
    wins, n = [9, 8, 17], [12, 12, 24]
    bars = ax.bar(batches, [w / x * 100 for w, x in zip(wins, n)],
                  color="#60a5fa", width=0.55)
    for b, w, x in zip(bars, wins, n):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5,
                f"{w}/{x}", ha="center", fontsize=8)
    ax.axhline(50, color="gray", lw=0.8, ls="--")
    ax.text(-0.45, 51.5, "parity", fontsize=7, color="gray")
    ax.set_ylabel("win rate vs.\\ utility rules (%)")
    ax.set_ylim(0, 90)
    fig.savefig(os.path.join(FIGS, "fig_winrate.pdf"), bbox_inches="tight")
    plt.close(fig)


def fig_latency() -> None:
    lats = []
    path = os.path.join(REPO, "out", "kev_vs_rule.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r.get("latency_ms") is not None:
                lats.append(r["latency_ms"])
    if not lats:                                    # 兜底：bench 日志
        path = os.path.join(REPO, "out", "bench_real.jsonl")
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r.get("latency_ms") is not None:
                lats.append(r["latency_ms"])
    lats.sort()
    cdf = [i / len(lats) * 100 for i in range(1, len(lats) + 1)]
    fig, ax = plt.subplots(figsize=(4.2, 2.5))
    ax.plot(lats, cdf, color="#2563eb", lw=1.4)
    ax.axvline(1000, color="#dc2626", lw=1.0, ls="--")
    ax.text(1010, 8, "1 Hz budget\n(1000 ms)", fontsize=7, color="#dc2626")
    p50 = lats[len(lats) // 2]
    p95 = lats[int(len(lats) * 0.95)]
    ax.axvline(p50, color="gray", lw=0.8, ls=":")
    ax.text(p50 + 15, 45, f"p50 {p50} ms", fontsize=7, color="gray")
    ax.text(p95 + 15, 20, f"p95 {p95} ms", fontsize=7, color="gray")
    ax.set_xlabel("per-decision end-to-end latency (ms), stock 0.5B on MPS")
    ax.set_ylabel("% of decisions")
    ax.set_ylim(0, 102)
    fig.savefig(os.path.join(FIGS, "fig_latency.pdf"), bbox_inches="tight")
    plt.close(fig)


def fig_plateau() -> None:
    variants = ["positional\nterm", "focus-fire\ncandidates",
                "+weakest/\nretreat/\ntie-extend", "+purchase\ndelegation",
                "deep horizon\n160 vs 80",
                "opp-model +\n2× cadence\n(50-game gate)"]
    wins = [3, 11, 2, 0, 18, 16]
    games = [10, 16, 6, 6, 40, 50]
    rates = [w / g * 100 for w, g in zip(wins, games)]
    fig, ax = plt.subplots(figsize=(5.6, 2.6))
    bars = ax.bar(range(len(variants)), rates, color="#a5b4fc", width=0.6)
    for b, w, g in zip(bars, wins, games):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.2,
                f"{w}/{g}", ha="center", fontsize=7.5)
    ax.axhline(50, color="gray", lw=0.8, ls="--")
    ax.text(len(variants) - 0.45, 51.5, "parity", fontsize=7, color="gray")
    ax.axhline(80, color="#dc2626", lw=1.0, ls="--")
    ax.text(len(variants) - 0.45, 81.5, "evolution gate", fontsize=7,
            color="#dc2626")
    ax.set_xticks(range(len(variants)), variants, fontsize=6.8)
    ax.set_ylabel("win rate vs.\\ v2 incumbent (%)")
    ax.set_ylim(0, 95)
    fig.savefig(os.path.join(FIGS, "fig_plateau.pdf"), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig_arch()
    fig_traps()
    fig_winrate()
    fig_latency()
    fig_plateau()
    print("✓ 5 figures →", FIGS)
