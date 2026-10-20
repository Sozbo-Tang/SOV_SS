"""KevAgentV3：进化代①（冻结 kev-0.5B——进化全部在 agent 架构层）。

对 v2 的三项架构改进（思路来源：Churchill et al. AIIDE 2012 快启发式战斗
搜索的 Attack-Weakest/集中火力 + 本项目实测推演分分析）：
1. **全目标攻击候选**：enumerate_candidates_v3 为每单位追加对第二个射程内
   敌目标的攻击候选——集中火力的选择空间交给推演裁决（v2 只打表序首个敌）；
2. **炮兵打可见敌集群质心**：v2 炮击只炸敌纵深锚点，敌情可见时空炸锚点
   是浪费——arty2 候选把火力引到真实集群上；
3. **推演分数位置项 + 自适应视野**：机动类候选（占点/推进/登车）用 3×
   长视野推演，分数加"向无主占点推进的位置增益"（//300 克质量纲、±80
   截幅）——修复 v2 推演对机动候选全零分、位置决策退回效用表的盲区。

kev-0.5B 的角色不变：每个决策拍在环提案，推演校验按 eps 裁决（v2 同款）。
"""
from __future__ import annotations

import copy

from sovs.ai.actions import build_commands, enumerate_candidates_v3
from sovs.ai.agent_v2 import KevAgentV2
from sovs.sim.tick import MoveCmd, MoveMode, queue_command, world_tick


class KevAgentV3(KevAgentV2):
    """v2 + 集中火力候选空间 + 炮兵质心射击 + 位置感知推演。

    pos_weight：位置项权重（0=关——消融实验用；实测默认 1 对 v2 反而劣化，
    开发批用 0/1 对照定位）。"""

    LONG_KINDS = frozenset({"objective", "advance", "mount", "deploy_move"})

    def __init__(self, player_index: int, client=None, *, anchors=None,
                 purchase_every: int = 50, squad_every: int = 5,
                 candidate_limit: int = 16, log=None, label: str = "",
                 rich_state: bool = False, min_top_prob: float = 0.0,
                 rollout_k: int = 5, horizon: int = 80, eps: float = 0.0,
                 pos_weight: int = 0, purchase_argmax: bool = True):
        super().__init__(player_index, client, anchors=anchors,
                         purchase_every=purchase_every, squad_every=squad_every,
                         candidate_limit=candidate_limit, log=log, label=label,
                         rich_state=rich_state, min_top_prob=min_top_prob,
                         rollout_k=rollout_k, horizon=horizon, eps=eps)
        self.pos_weight = max(0, pos_weight)
        self.purchase_argmax = purchase_argmax   # 购卡角色委托规则层（进化代①）

    def _ground_beat(self, world) -> None:
        anchor = self._enemy_anchor(world,
                                    world.players[self.player_index].team)
        cands = [c for c in enumerate_candidates_v3(
            world, self.player_index,
            artillery_issued=self._artillery_issued, enemy_anchor=anchor,
            limit=self.candidate_limit) if c.kind != "wait"]
        if not cands:                       # 无真地面选项——静默
            return
        chosen = self._choose_and_run(world, "ground", cands, phase="combat",
                                      p=world.players[self.player_index])
        if chosen is not None and chosen.kind == "artillery":
            self._artillery_issued.add(chosen.params["unit_id"])

    def _horizon_for(self, cand) -> int:
        return self.horizon * 3 if cand.kind in self.LONG_KINDS else self.horizon

    def _extend_ties(self, world, player_index: int, scores: dict, cands) -> None:
        """并列残差消解：base 视野下并列（差 ≤3）且存在非零交战信号时，把
        并列者（至多 3 个）推到 3× 视野重评分——纯零并列=纯机动拍跳过省算力。
        确定性：按 key 字母序取前 3。"""
        if not scores:
            return
        best = max(scores.values())
        if best == 0:
            return
        tied = sorted(k for k, s in scores.items() if s >= best - 3)[:3]
        if len(tied) <= 1:
            return
        by_key = {c.key: c for c in cands}
        for k in tied:
            c = by_key.get(k)
            if c is None:
                continue
            scores[k] = self._rollout_score(world, player_index, c,
                                            self._horizon_for(c) * 3)
            self.verify_stats["rollouts"] += 1

    def _rollout_score(self, world, player_index: int, cand, horizon: int) -> int:
        """v2 战果分 + 位置项：己方存活单位到最近非己方占点的距离和每推进
        300cm 记 1 分（±80 截幅——次级于战损、可比一次命中）。"""
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

        def pos_sum() -> int:
            total = 0
            for u in snap.units:
                if not (u.alive and u.team == my_team) or u.template.cost <= 0:
                    continue
                ds = [abs(u.pos[0] - o.pos[0]) + abs(u.pos[1] - o.pos[1])
                      for o in snap.objectives
                      if o.owner != my_team]
                if ds:
                    total += min(ds)
            return total

        enemy0, mine0, obj0, pos0 = (hp_of(1 - my_team), hp_of(my_team),
                                     obj_net(), pos_sum())
        for cmd in build_commands(snap, p, cand):
            queue_command(snap, cmd)
        # 对手建模：克隆内每 10 拍给敌单位注入 argmax 机动（向最近非己方
        # 占点推进）——推演从"打木桩"升级为"预演对手反制"（v2 无此层）。
        for t in range(horizon):
            if t % 10 == 0:
                for u in snap.units:
                    if (u.alive and u.team != my_team and not u.moving()
                            and u.template.cost > 0):
                        objs = [o for o in snap.objectives if o.owner != u.team]
                        if objs:
                            dest = min(objs, key=lambda o: (
                                abs(u.pos[0] - o.pos[0])
                                + abs(u.pos[1] - o.pos[1]), o.id)).pos
                            queue_command(snap, MoveCmd(
                                unit=u, path=[dest], mode=MoveMode.NORMAL,
                                queue=False))
            world_tick(snap)
            if snap.result is not None:
                break
        dmg = (enemy0 - hp_of(1 - my_team)) - (mine0 - hp_of(my_team))
        pos_gain = 0
        if self.pos_weight:
            pos_gain = max(-80, min(80, (pos0 - pos_sum()) // 300))
        return dmg + 400 * (obj_net() - obj0) + self.pos_weight * pos_gain
