"""KevPlayer：Kev-0.5B 决策服务驱动的虚拟玩家（HeadlessAI 即插即用替代）。

用法与 tests/test_fullgame_acceptance.HeadlessAI 同构——每 tick 调
`step(world)`，只经 `queue_command→consume_commands` 公开接口发令，
零直接写 world 状态、零掷骰（决策侧不触碰任何 PCG32 通道）：

    from sovs.ai import KevPlayer, KevClient
    kev = KevPlayer(0, client=KevClient("http://127.0.0.1:8011"))
    bot = KevPlayer(1)                       # 无 client=纯规则兜底
    while w.phase != PHASE_SETTLE:
        kev.step(w); bot.step(w)
        world_tick(w)

决策节拍（确定性 tick 门，与 HeadlessAI 同款）——覆盖完整游戏流程：
- 盲部署相位：每 purchase_every 拍购卡决策（可负担卡组序）+ 错半拍排兵决策
  （deploy_candidates：队形令+预置展开车道）；
- 实战相位：每 decide_every 拍地面动作决策 + 每 air_every 拍空军调度决策
  （air_candidates：呼叫/打击/空投预备队/巡逻/对空/返场）；
- 空军呼叫无相位门（B-18——部署期即呼），故 air 节拍两相位都走、结算停。

降级链：client 为 None / KevUnavailableError（连接失败、超时、非法选项）→
同一候选表的 argmax（效用分最高，确定性）——对局永不因模型侧故障中断。

决策日志：log（路径或 DecisionLog）逐决策记录 source=kev|fallback、
选项概率、命令描述符（回放=种子+命令流，见 decision_log.py）。
"""
from __future__ import annotations

import time

from sovs.ai.actions import (air_candidates, build_commands,
                             deploy_candidates, enumerate_candidates,
                             purchase_candidates)
from sovs.ai.decision_log import DecisionLog, describe_command
from sovs.ai.kev_client import KevClient, KevUnavailableError
from sovs.ai.state_view import compact_brief, situation_brief
from sovs.sim.air import PHASE_COMBAT, PHASE_DEPLOY, PHASE_SETTLE
from sovs.sim.tick import PurchaseCmd, queue_command

_PURCHASE_QID = "purchase"
_ACTION_QID = "action"
_DEPLOY_QID = "deploy"
_AIR_QID = "air"


class KevPlayer:
    """Kev 决策虚拟玩家。兼容面：stdlib-only，CUDA/MPS/MLX 由服务端承载。"""

    def __init__(self, player_index: int, client: KevClient | None = None, *,
                 anchors=None, purchase_every: int = 50, decide_every: int = 100,
                 air_every: int = 150, candidate_limit: int = 12, log=None,
                 label: str = "", rich_state: bool = False,
                 min_top_prob: float = 0.0):
        self.player_index = player_index
        self.client = client
        self.purchase_every = max(1, purchase_every)
        self.decide_every = max(1, decide_every)
        self.air_every = max(0, air_every)   # 0=禁用空军节拍（纯地面场景/测试隔离）
        self.candidate_limit = max(1, candidate_limit)
        self.anchors = anchors          # None=按地图推导（南/北中点——见 _enemy_anchor）
        self.label = label or f"p{player_index}"
        self.rich_state = rich_state    # False=紧凑文本态（0.5B 384 预算）；True=丰富 dict 态
        self.min_top_prob = max(0.0, min_top_prob)   # 置信度门（0=关，见 _decide）
        self._log = log if isinstance(log, DecisionLog) else DecisionLog(log)
        self._artillery_issued: set[int] = set()
        self._deploy_moved: set = set()       # 预置展开已发单位（一单位一次）
        self._formed: set = set()             # 队形令已发单位（一单位一次）
        # 决策来源计数（demo/测试观测面）
        self.stats = {"kev": 0, "fallback": 0}

    # ── 每 tick 入口（对齐 HeadlessAI.step 签名）──

    def step(self, world) -> None:
        if world.phase == PHASE_DEPLOY:
            if world.tick % self.purchase_every == 0:
                self._purchase_beat(world)
            if world.tick % self.purchase_every == self.purchase_every // 2:
                self._deploy_beat(world)
        elif world.phase == PHASE_COMBAT:
            if world.tick % self.decide_every == 0:
                self._combat_beat(world)
        if (self.air_every and world.phase != PHASE_SETTLE
                and world.tick % self.air_every == 0):
            self._air_beat(world)      # B-18：空军无相位门（部署期即呼）

    # ── 购卡决策（盲部署相位）──

    def _purchase_beat(self, world) -> None:
        p = world.players[self.player_index]
        cands = purchase_candidates(world, self.player_index)
        if not cands:
            return
        options = {key: desc for _tpl, key, desc in cands}
        state = (situation_brief if self.rich_state else compact_brief)(
                world, self.player_index)
        chosen_key, source, extra = self._decide(
            state, _PURCHASE_QID,
            "盲部署购卡：下一张买什么（考虑点数余量与卡组构成）", options,
            fallback_key=cands[0][1])
        if source == "kev":
            self.stats["kev"] += 1
        else:
            self.stats["fallback"] += 1
        if chosen_key is None:
            return
        tpl = next(t for t, k, _d in cands if k == chosen_key)
        queue_command(world, PurchaseCmd(player=p, template=tpl))
        self._log.record({
            "label": self.label, "state": state, "kind": "purchase", "tick": world.tick,
            "phase": "deploy", "source": source, **extra,
            "candidates": [{"key": k, "desc": d} for _t, k, d in cands],
            "commands": [describe_command(PurchaseCmd(player=p, template=tpl))],
        })

    # ── 动作决策（实战相位）──

    def _combat_beat(self, world) -> None:
        p = world.players[self.player_index]
        anchor = self._enemy_anchor(world, p.team)
        cands = enumerate_candidates(
            world, self.player_index,
            artillery_issued=self._artillery_issued, enemy_anchor=anchor,
            limit=self.candidate_limit)
        if not cands:
            return
        options = {c.key: c.desc for c in cands}
        state = (situation_brief if self.rich_state else compact_brief)(
                world, self.player_index)
        chosen_key, source, extra = self._decide(
            state, _ACTION_QID,
            "战术指挥：本节拍采取哪个行动（考虑可见敌情、占点胜负与单位状态）",
            options, fallback_key=cands[0].key)
        if source == "kev":
            self.stats["kev"] += 1
        else:
            self.stats["fallback"] += 1
        chosen = next((c for c in cands if c.key == chosen_key), None)
        if chosen is None:
            return
        if chosen.kind == "artillery":
            self._artillery_issued.add(chosen.params["unit_id"])
        cmds = build_commands(world, p, chosen)
        for cmd in cmds:
            queue_command(world, cmd)
        self._log.record({
            "label": self.label, "state": state, "kind": "combat", "tick": world.tick,
            "phase": "combat", "source": source, **extra,
            "candidates": [{"key": c.key, "desc": c.desc, "utility": c.utility}
                           for c in cands],
            "commands": [describe_command(c) for c in cmds],
        })

    # ── 排兵决策（盲部署相位，购卡节拍错半拍）──

    def _deploy_beat(self, world) -> None:
        p = world.players[self.player_index]
        cands = deploy_candidates(
            world, self.player_index,
            issued_moves=self._deploy_moved, issued_formations=self._formed,
            limit=self.candidate_limit)
        if len(cands) == 1:            # 只剩 wait——排兵已毕
            return
        options = {c.key: c.desc for c in cands}
        state = (situation_brief if self.rich_state else compact_brief)(
                world, self.player_index)
        chosen_key, source, extra = self._decide(
            state, _DEPLOY_QID,
            "排兵布阵：本节拍如何布置部队（队形与预置展开车道）",
            options, fallback_key=cands[0].key)
        if source == "kev":
            self.stats["kev"] += 1
        else:
            self.stats["fallback"] += 1
        chosen = next((c for c in cands if c.key == chosen_key), None)
        if chosen is None:
            return
        if chosen.kind == "deploy_move":
            self._deploy_moved.add(chosen.params["unit_id"])
        elif chosen.kind == "formation":
            self._formed.add(chosen.params["unit_id"])
        cmds = build_commands(world, p, chosen)
        for cmd in cmds:
            queue_command(world, cmd)
        self._log.record({
            "label": self.label, "state": state, "kind": "deploy", "tick": world.tick,
            "phase": "deploy", "source": source, **extra,
            "candidates": [{"key": c.key, "desc": c.desc, "utility": c.utility}
                           for c in cands],
            "commands": [describe_command(c) for c in cmds],
        })

    # ── 空军调度决策（部署+实战两相位；B-18 无相位门）──

    def _air_beat(self, world) -> None:
        p = world.players[self.player_index]
        anchor = self._enemy_anchor(world, p.team)
        cands = air_candidates(world, self.player_index, enemy_anchor=anchor,
                               limit=self.candidate_limit)
        if len(cands) == 1:            # 只剩 wait——无航空选项（点数/冷却/在空全闭）
            return
        options = {c.key: c.desc for c in cands}
        state = (situation_brief if self.rich_state else compact_brief)(
                world, self.player_index)
        chosen_key, source, extra = self._decide(
            state, _AIR_QID,
            "空军调度：呼叫新机或在空飞机行动（考虑空援点数、敌情与预备队）",
            options, fallback_key=cands[0].key)
        if source == "kev":
            self.stats["kev"] += 1
        else:
            self.stats["fallback"] += 1
        chosen = next((c for c in cands if c.key == chosen_key), None)
        if chosen is None:
            return
        cmds = build_commands(world, p, chosen)
        for cmd in cmds:
            queue_command(world, cmd)
        self._log.record({
            "label": self.label, "state": state, "kind": "air", "tick": world.tick,
            "phase": "air", "source": source, **extra,
            "candidates": [{"key": c.key, "desc": c.desc, "utility": c.utility}
                           for c in cands],
            "commands": [describe_command(c) for c in cmds],
        })

    # ── 决策统一入口：Kev choice + argmax 兜底 ──

    def _decide(self, state, qid: str, instructions: str,
                options: dict[str, str], fallback_key: str):
        """→ (chosen_key|None, source, extra)。extra 进日志（概率/原因/时延）。

        chosen_key=None 仅发生在兜底候选自身不可用（不构造）——正常路径恒有选择。
        """
        if self.client is None:
            return fallback_key, "fallback", {"reason": "no-client"}
        t0 = time.monotonic()
        try:
            ans = self.client.choose(state, qid, instructions, options)
        except KevUnavailableError as e:
            return fallback_key, "fallback", {"reason": str(e)[:200]}
        latency_ms = int((time.monotonic() - t0) * 1000)
        extra = {"confidence": round(ans.confidence, 4),
                 "probabilities": ans.probabilities, "latency_ms": latency_ms}
        # 置信度门控（与 AgentSquad 同款）：模型首选概率低于阈值→argmax
        top = max(ans.probabilities.values(), default=0.0)
        if self.min_top_prob > 0 and top < self.min_top_prob:
            return (fallback_key, "fallback",
                    {**extra, "reason": f"low-top-prob {top:.3f}"})
        return ans.choice, "kev", extra

    # ── 敌锚点推导（缺省：地图南北中点——200k×100k 演示图恰为 SOUTH/NORTH）──

    def _enemy_anchor(self, world, team: int):
        if self.anchors is not None:
            return self.anchors[0] if team == 1 else self.anchors[1]
        cx = world.map_center[0]
        h = world.map_extent[1]
        south, north = (cx, 0), (cx, h)
        return south if team == 1 else north

    def close(self) -> None:
        self._log.close()
