"""KevAgentV2：propose–verify agent（冻结 kev-0.5B，零训练）。

设计（联网调研拍板的 simulation-in-the-loop / propose–verify 范式）：
- kev-0.5B 在**每个决策拍在环**：生成候选后由模型提案一个选项（含角色化
  提示词与降级链，AgentSquad 同款）；
- 地面拍加**确定性引擎推演校验**：deepcopy 世界克隆，把模型提案与效用
  Top-K 候选各自推演 horizon 拍，按战果分（敌方损失-己方损失+占点净变化）
  排名——模型提案分 ≥ 最优分-eps 则执行模型提案，否则执行推演最优；
- 空中/预备队/部署拍模型直决（实测已对齐 argmax，机动类长时延推演无信息）。

可复现纪律：推演在**克隆世界**上进行（deepcopy 含 RNG 通道状态），真实世界
零 RNG 触碰、零直接写——回放=种子+命令流不变。eps=0 表示模型仅在并列或
选中推演最优时才被执行（校验最严）。
"""
from __future__ import annotations

import copy
import time

from sovs.ai.actions import build_commands
from sovs.ai.agents import AgentSquad
from sovs.ai.decision_log import describe_command
from sovs.sim.tick import queue_command, world_tick


class KevAgentV2(AgentSquad):
    """kev-0.5B 提案 + 引擎推演校验（propose–verify）。"""

    def __init__(self, player_index: int, client=None, *, anchors=None,
                 purchase_every: int = 50, squad_every: int = 10,
                 candidate_limit: int = 12, log=None, label: str = "",
                 rich_state: bool = False, min_top_prob: float = 0.0,
                 rollout_k: int = 4, horizon: int = 80, eps: float = 0.0):
        super().__init__(player_index, client, anchors=anchors,
                         purchase_every=purchase_every, squad_every=squad_every,
                         candidate_limit=candidate_limit, log=log, label=label,
                         rich_state=rich_state, min_top_prob=min_top_prob)
        self.rollout_k = max(1, rollout_k)
        self.horizon = max(10, horizon)
        self.eps = max(0.0, eps)
        self.verify_stats = {"model_kept": 0, "overridden": 0, "rollouts": 0}

    # ── 推演校验 ──

    def _horizon_for(self, cand) -> int:
        """推演视野钩子（v3 按候选类型覆写——机动类长视野）。"""
        return self.horizon

    def _extend_ties(self, world, player_index: int, scores: dict, cands) -> None:
        """并列残差消解钩子（v2 缺省无操作；v3 对交战并列者加深推演）。"""
        return None

    def _rollout_score(self, world, player_index: int, cand, horizon: int) -> int:
        """克隆世界推演一个候选 → 战果分（敌损-我损+400×占点净变化）。"""
        from sovs.sim.tick import consume_commands
        snap = copy.deepcopy(world)
        p = snap.players[player_index]
        my_team = p.team

        def hp_of(team: int) -> int:
            return sum(e.hp_current for u in snap.units if u.alive
                       and u.team == team for e in u.elements)

        def obj_net() -> int:
            ours = sum(1 for o in snap.objectives if o.owner == my_team)
            theirs = sum(1 for o in snap.objectives
                         if o.owner is not None and o.owner != my_team)
            return ours - theirs

        enemy0, mine0, obj0 = hp_of(1 - my_team), hp_of(my_team), obj_net()
        for cmd in build_commands(snap, p, cand):
            queue_command(snap, cmd)
        for _ in range(horizon):
            world_tick(snap)
            if snap.result is not None:
                break
        dmg = (enemy0 - hp_of(1 - my_team)) - (mine0 - hp_of(my_team))
        return dmg + 400 * (obj_net() - obj0)

    def _choose_and_run(self, world, role, cands, *, phase, p):
        if role != "ground" or self.client is None or len(cands) <= 1:
            return super()._choose_and_run(world, role, cands, phase=phase, p=p)

        # ① 推演效用 Top-K
        t0 = time.monotonic()
        top = cands[:self.rollout_k]
        scores: dict[str, int] = {}
        for c in top:
            scores[c.key] = self._rollout_score(world, self.player_index, c,
                                                self._horizon_for(c))
            self.verify_stats["rollouts"] += 1

        # ② kev-0.5B 提案（全候选集）
        state = self._state(world)
        chosen_key, source, extra = self._decide(
                state, role, {c.key: c.desc for c in cands},
                fallback_key=top[0].key)
        self._tally(role, source)

        # ③ 校验：模型提案也推演（不在 Top-K 时补一次），分够则执行模型提案
        if chosen_key is not None and chosen_key not in scores:
            mc = next((c for c in cands if c.key == chosen_key), None)
            if mc is not None:
                scores[chosen_key] = self._rollout_score(
                    world, self.player_index, mc, self._horizon_for(mc))
                self.verify_stats["rollouts"] += 1
        self._extend_ties(world, self.player_index, scores, cands)
        best_key = max(scores, key=lambda k: (scores[k], k))
        best = scores[best_key]
        m_score = scores.get(chosen_key)
        if chosen_key is None or m_score is None or m_score < best - self.eps:
            final_key = best_key
            self.verify_stats["overridden"] += 1
            final_source = "verify"
        else:
            final_key = chosen_key
            self.verify_stats["model_kept"] += 1
            final_source = source
        chosen = next(c for c in cands if c.key == final_key)
        if chosen is None:
            return None
        cmds = build_commands(world, p, chosen)
        for cmd in cmds:
            queue_command(world, cmd)
        latency_ms = int((time.monotonic() - t0) * 1000)
        self._log.record({
            "label": self.label, "state": state,
            "kind": self._LOG_KIND[role],
            "tick": world.tick, "phase": phase, "role": role,
            "source": final_source, "chosen": final_key,
            "model_pick": chosen_key, "model_source": source, **extra,
            "rollout_scores": scores, "eps": self.eps,
            "latency_ms": latency_ms,
            "candidates": [{"key": c.key, "desc": c.desc, "utility": c.utility}
                           for c in cands],
            "commands": [describe_command(c) for c in cmds],
        })
        return chosen
