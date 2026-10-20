"""AgentSquad：人机 AI 的四块专职角色班组 + 1Hz 固定顺序节拍器。

与 KevPlayer（单体四节拍，保留不动）并存的第二种驱动面：把决策任务拆给
四个专职角色，每角色有**独立的 choice instructions**（角色化提示词——地面
指挥官看敌情与占点/空中管制官看空援点数与制空/预备队参谋看预备队余份与
投送时机），四个角色共用同一个 client（KevClient 或 LocalKevEngine——
鸭子类型同口，一次装配全体共享）：

  角色1 排兵布阵（开始前，盲部署相位）：购卡（purchase_candidates）+
        队形/预置车道（deploy_candidates）。节拍沿用 KevPlayer 现制：
        购卡 %50、排兵错半拍（25/75…）——"开始前"不要求 1Hz。
  角色2 地面单位操作（开始后）：enumerate_candidates 全部地面候选
        （推进/占点/攻击/急停/炮击/上下车/拖曳/驻楼/烟幕/冲刺/转向/
        姿态/取消族/掩护/买补给/信标等）。
  角色3 空中单位操作（开始后）：纯航空作战——呼叫攻击机/轰炸机/战斗
        机/侦察、对集群打击(strike)、CAP 盘旋、对空交战、爬升、返场、
        缠斗脱离。
  角色4 预备部队出卡（开始后）：预备队与补给投送链——call_troop_*
        （运输机装空降卡）、call_supply_*（补给装载）、airdrop（预备
        队/补给箱投放）。〔ferry 转场候选已裁撤——模型陷阱，见 actions.py〕

1Hz 顺序节拍器（PHASE_COMBAT）：每 squad_every 拍（缺省 10=1 游戏秒
@10Hz）轮到下一个角色，顺序固定 **地面→空中→预备队** 循环；轮到的角色
当拍做一次决策（一次模型 choice）并 queue_command 其命令，其余拍静默。
PHASE_DEPLOY 走角色1 既有节拍（角色2/3/4 实战拍起才上场）；PHASE_SETTLE
全静默。

════════════════════════════════════════════════════════════════════════
air_candidates 输出的角色归属映射表（kind + key 前缀 → 角色3/角色4；
air_candidates 现把两者混在一起，split_air_candidates 按本表拆两份）
════════════════════════════════════════════════════════════════════════
  角色3 空中单位操作（纯航空作战）：
    kind=strike         key 前缀 strike_    对集群打击（在空攻击机/轰炸机投弹）
    kind=air_engage     key 前缀 engage_    对空交战（CAP 猎杀开关）
    kind=air_patrol     key 前缀 cap_       CAP 盘旋 / 侦察盘旋
    kind=air_alt        key 前缀 climb_     爬升至 ceiling 层
    kind=air_rtb        key 前缀 rtb_       任务完毕返场
    kind=air_disengage  key 前缀 break_     缠斗脱离（R-20）
    kind=air_call       key=call_{机名}     呼叫攻击机/轰炸机/战斗机/侦察
                         （凡 **不**以 call_troop_/call_supply_ 开头的呼叫）
  角色4 预备部队出卡（投送链）：
    kind=airdrop        key 前缀 drop_      空投预备队（AirAirdropCmd）
    kind=airdrop        key 前缀 supply_    空投补给箱
    kind=air_call       key 前缀 call_troop_    呼叫运输机装预备队（PARATROOP）
    kind=air_call       key 前缀 call_supply_   呼叫运输机装载补给（SUPPLY）
  wait（兜底位）：拆分时丢弃，各非空子集末尾自补一枚角色化 wait。
════════════════════════════════════════════════════════════════════════

降级链与决策日志口径同 KevPlayer：client 为 None / KevUnavailableError →
同一候选表的 argmax（效用分最高，确定性），对局永不因模型侧故障中断；
日志逐决策记录 kind=deploy|purchase|combat|air|reserve（角色2 记 combat、
角色3 记 air、角色4 记 reserve——与 KevPlayer 既有 kind 面对齐+新增
reserve），另记 role=角色名。stdlib-only；step(world) 对齐 HeadlessAI。
"""
from __future__ import annotations

import time

from sovs.ai.actions import (Candidate, air_candidates, build_commands,
                             deploy_candidates, enumerate_candidates,
                             purchase_candidates)
from sovs.ai.decision_log import DecisionLog, describe_command
from sovs.ai.kev_client import KevClient, KevUnavailableError
from sovs.ai.state_view import compact_brief, situation_brief
from sovs.sim.air import PHASE_COMBAT, PHASE_DEPLOY
from sovs.sim.tick import PurchaseCmd, queue_command

# ── air_candidates 拆分谓词（映射表见模块顶部注释）──

_RESERVE_KINDS = frozenset({"airdrop"})
_RESERVE_CALL_PREFIXES = ("call_troop_", "call_supply_")


def is_reserve_candidate(cand: Candidate) -> bool:
    """单候选归属判定：True=角色4（投送链），False=角色3（纯航空作战）。

    wait 兜底位不属于任何角色（拆分时单独处理）。
    """
    if cand.kind in _RESERVE_KINDS:
        return True
    return (cand.kind == "air_call"
            and cand.key.startswith(_RESERVE_CALL_PREFIXES))


def split_air_candidates(cands: list[Candidate]):
    """air_candidates 输出 → (空中作战候选, 预备队投送候选)。

    保持原效用序（stable 过滤）；wait 兜底位丢弃——各角色节拍对非空子集
    自行补角色化 wait（见 AgentSquad._air_role_beat）。
    """
    combat: list[Candidate] = []
    reserve: list[Candidate] = []
    for c in cands:
        if c.kind == "wait":
            continue
        (reserve if is_reserve_candidate(c) else combat).append(c)
    return combat, reserve


class AgentSquad:
    """四角色班组虚拟玩家（KevPlayer 即插即用同签名，两者并存不替代）。

    用法与 KevPlayer 完全同构（tools 侧 --mode squad 切换）：

        squad = AgentSquad(0, client, anchors=(SOUTH, NORTH))
        while w.phase != PHASE_SETTLE:
            squad.step(w)
            world_tick(w)
    """

    # PHASE_COMBAT 1Hz 轮转序（固定：地面→空中→预备队 循环）
    COMBAT_ORDER = ("ground", "air", "reserve")
    _ROLES = ("deploy", "ground", "air", "reserve")

    # 决策日志 kind（角色2=combat/角色3=air/角色4=reserve——对齐 KevPlayer
    # 既有 kind 面；角色1 两节拍分别为 purchase/deploy）
    _LOG_KIND = {"purchase": "purchase", "deploy": "deploy",
                 "ground": "combat", "air": "air", "reserve": "reserve"}

    _QID = {"purchase": "squad_purchase", "deploy": "squad_deploy",
            "ground": "squad_ground", "air": "squad_air",
            "reserve": "squad_reserve"}

    # 角色化提示词（四角色各自独立，不共用泛化句——"分四块"的核心语义）
    _INSTRUCTIONS = {
        "purchase": ("排兵布阵官·购卡：盲部署期决定下一张购入的卡"
                     "（看购卡点数余量与卡组构成，权衡步兵/装甲/火支搭配）"),
        "deploy": ("排兵布阵官·布阵：决定队形与预置展开车道"
                   "（看单位兵种与西中南三条车道，横队火力/楔形均衡/纵队机动）"),
        "ground": ("地面指挥官：决定地面单位本秒行动"
                   "（看可见敌情与占点归属，机动夺点、开火打击、烟幕遮蔽、"
                   "上下车与驻楼择优）"),
        "air": ("空中管制官：决定航空兵本秒行动"
                "（看空援点数与制空态势，呼叫攻击机/轰炸机/战斗机/侦察，"
                "或在空飞机打击/CAP/对空/爬升/返场/缠斗脱离）"),
        "reserve": ("预备队参谋：决定预备队与补给投送本秒行动"
                    "（看预备队余份与运输机状态，装伞、装补给、转场或择点投放）"),
    }

    # 各战斗角色子集的 wait 兜底位描述（角色化——模型读的判据）
    _WAIT_DESC = {"air": "航空兵本轮待命，保持现状",
                  "reserve": "投送链本轮待命，保持现状"}

    def __init__(self, player_index: int, client: KevClient | None = None, *,
                 anchors=None, purchase_every: int = 50, squad_every: int = 10,
                 candidate_limit: int = 12, log=None, label: str = "",
                 rich_state: bool = False, min_top_prob: float = 0.0):
        self.player_index = player_index
        self.client = client          # 四角色共用同一引擎实例（HTTP/进程内均可）
        self.purchase_every = max(1, purchase_every)   # 角色1 节拍（KevPlayer 现制）
        self.squad_every = max(1, squad_every)         # 1Hz 轮转拍距（10=1 游戏秒@10Hz）
        self.candidate_limit = max(1, candidate_limit)
        self.anchors = anchors        # None=按地图推导（南/北中点——见 _enemy_anchor）
        self.label = label or f"p{self.player_index}"
        self.rich_state = rich_state
        self.min_top_prob = max(0.0, min_top_prob)   # 置信度门（0=关，见 _decide）
        self._log = log if isinstance(log, DecisionLog) else DecisionLog(log)
        self._artillery_issued: set[int] = set()   # 角色2 记账（炮击一局一次）
        self._deploy_moved: set = set()            # 角色1 记账（预置车道一单位一次）
        self._formed: set = set()                  # 角色1 记账（队形令一单位一次）
        self._combat_beats = 0                     # 轮转拍计数（决定轮到哪个角色）
        # 决策来源计数：总量面（KevPlayer 同形）+ 分角色面
        self.stats = {"kev": 0, "fallback": 0}
        self.role_stats = {r: {"kev": 0, "fallback": 0} for r in self._ROLES}
        self.last_role: str | None = None          # 最近一次决策的角色（观测面）

    # ── 每 tick 入口（对齐 KevPlayer/HeadlessAI.step 签名）──

    def step(self, world) -> None:
        if world.phase == PHASE_DEPLOY:
            if world.tick % self.purchase_every == 0:
                self._purchase_beat(world)
            if world.tick % self.purchase_every == self.purchase_every // 2:
                self._deploy_beat(world)
        elif world.phase == PHASE_COMBAT:
            if world.tick % self.squad_every == 0:
                role = self.COMBAT_ORDER[
                    self._combat_beats % len(self.COMBAT_ORDER)]
                self._combat_beats += 1
                if role == "ground":
                    self._ground_beat(world)
                else:
                    self._air_role_beat(world, role)
        # PHASE_SETTLE：全静默

    # ── 角色1·购卡节拍（盲部署相位，%50）──

    def _purchase_beat(self, world) -> None:
        p = world.players[self.player_index]
        cands = purchase_candidates(world, self.player_index)
        if not cands:
            return
        options = {key: desc for _tpl, key, desc in cands}
        state = self._state(world)
        if getattr(self, "purchase_argmax", False):
            # 购卡角色委托规则层（FIFO 稳定节奏）：模型购卡序实测为纯噪声
            # 方差源（76% 偏离且与胜负无关），委托是 agent 角色分工设计。
            chosen_key, source, extra = cands[0][1], "fallback", {
                "reason": "purchase-argmax"}
        else:
            chosen_key, source, extra = self._decide(
                    state, "purchase", options, fallback_key=cands[0][1])
        self._tally("deploy", source)     # 购卡节拍归属角色1（排兵布阵）
        if chosen_key is None:
            return
        tpl = next(t for t, k, _d in cands if k == chosen_key)
        queue_command(world, PurchaseCmd(player=p, template=tpl))
        self._log.record({
            "label": self.label, "state": state, "kind": "purchase",
            "tick": world.tick, "phase": "deploy", "role": "deploy",
            "source": source, **extra,
            "candidates": [{"key": k, "desc": d} for _t, k, d in cands],
            "commands": [describe_command(PurchaseCmd(player=p, template=tpl))],
        })

    # ── 角色1·排兵节拍（盲部署相位，购卡错半拍）──

    def _deploy_beat(self, world) -> None:
        p = world.players[self.player_index]
        cands = deploy_candidates(
            world, self.player_index,
            issued_moves=self._deploy_moved, issued_formations=self._formed,
            limit=self.candidate_limit)
        if len(cands) == 1:            # 只剩 wait——排兵已毕
            return
        chosen = self._choose_and_run(world, "deploy", cands, phase="deploy",
                                      p=p)
        if chosen is None:
            return
        if chosen.kind == "deploy_move":
            self._deploy_moved.add(chosen.params["unit_id"])
        elif chosen.kind == "formation":
            self._formed.add(chosen.params["unit_id"])

    # ── 角色2·地面单位操作（实战相位，1Hz 轮转位1）──

    def _ground_beat(self, world) -> None:
        anchor = self._enemy_anchor(world, world.players[self.player_index].team)
        cands = [c for c in enumerate_candidates(
            world, self.player_index,
            artillery_issued=self._artillery_issued, enemy_anchor=anchor,
            limit=self.candidate_limit) if c.kind != "wait"]
        if not cands:                  # 无真地面选项——静默（wait 不入模选项，
            return                     # 同 _air_role_beat 反躺平口径）
        chosen = self._choose_and_run(world, "ground", cands, phase="combat",
                                      p=world.players[self.player_index])
        if chosen is not None and chosen.kind == "artillery":
            self._artillery_issued.add(chosen.params["unit_id"])

    # ── 角色3/角色4·空中作战/预备队投送（实战相位，1Hz 轮转位2/3）──

    def _air_role_beat(self, world, role: str) -> None:
        anchor = self._enemy_anchor(world, world.players[self.player_index].team)
        combat, reserve = split_air_candidates(
            air_candidates(world, self.player_index, enemy_anchor=anchor,
                           limit=self.candidate_limit))
        cands = combat if role == "air" else reserve
        if not cands:                  # 本角色无候选（点数/冷却/在空全闭）——静默
            return
        # 不给模型提供 wait 选项（实测 0.5B 在角色问题里 99% 选"待命"躺平，
        # 空中 435/440、预备队 440/440 全 wait）——"做不做"由节拍决定，
        # 模型只在真候选里选"怎么做"；wait 的兜底职责由 argmax 首位承担。
        self._choose_and_run(world, role, cands, phase="combat",
                             p=world.players[self.player_index])

    # ── 决策统一入口：一次 choice（或 argmax 兜底）→ 命令入队 + 日志 ──

    def _choose_and_run(self, world, role: str, cands, *, phase: str, p):
        """角色节拍公共体：choice → build_commands → queue_command → 记日志。

        → 选中的 Candidate（兜底候选不可用时 None——正常路径恒有选择）。
        """
        options = {c.key: c.desc for c in cands}
        state = self._state(world)
        chosen_key, source, extra = self._decide(
                state, role, options, fallback_key=cands[0].key)
        self._tally(role, source)
        chosen = next((c for c in cands if c.key == chosen_key), None)
        if chosen is None:
            return None
        cmds = build_commands(world, p, chosen)
        for cmd in cmds:
            queue_command(world, cmd)
        self._log.record({
            "label": self.label, "state": state, "kind": self._LOG_KIND[role],
            "tick": world.tick, "phase": phase, "role": role,
            "source": source, "chosen": chosen_key, **extra,
            "candidates": [{"key": c.key, "desc": c.desc, "utility": c.utility}
                           for c in cands],
            "commands": [describe_command(c) for c in cmds],
        })
        return chosen

    # ── Kev choice + argmax 兜底（KevPlayer._decide 同款降级链）──

    def _decide(self, state, role: str, options: dict[str, str],
                fallback_key: str):
        """→ (chosen_key|None, source, extra)。角色化 instructions 在此注入。"""
        if self.client is None:
            return fallback_key, "fallback", {"reason": "no-client"}
        t0 = time.monotonic()
        try:
            ans = self.client.choose(state, self._QID[role],
                                     self._INSTRUCTIONS[role], options)
        except KevUnavailableError as e:
            return fallback_key, "fallback", {"reason": str(e)[:200]}
        latency_ms = int((time.monotonic() - t0) * 1000)
        extra = {"confidence": round(ans.confidence, 4),
                 "probabilities": ans.probabilities, "latency_ms": latency_ms}
        # 置信度门控：模型首选概率 < min_top_prob（拿不准）→ 降级 argmax。
        # 0.5B 弱域（空军经济/购卡）概率近乎平坦（实测 p≈0.25~0.43），此门
        # 把瞎猜还给规则；有把握的决策仍归模型（语义增量保留）。缺省 0=关。
        top = max(ans.probabilities.values(), default=0.0)
        if self.min_top_prob > 0 and top < self.min_top_prob:
            return (fallback_key, "fallback",
                    {**extra, "reason": f"low-top-prob {top:.3f}"})
        return ans.choice, "kev", extra

    # ── 观测面与杂项 ──

    def _tally(self, role: str, source: str) -> None:
        key = "kev" if source == "kev" else "fallback"
        self.stats[key] += 1
        self.role_stats[role][key] += 1
        self.last_role = role

    def _state(self, world):
        return (situation_brief if self.rich_state else compact_brief)(
                world, self.player_index)

    def reset_stats(self) -> None:
        """清零决策计数（bench warmup 后丢弃预热拍——总量面+分角色面）。"""
        self.stats = {"kev": 0, "fallback": 0}
        for r in self._ROLES:
            self.role_stats[r] = {"kev": 0, "fallback": 0}

    def _enemy_anchor(self, world, team: int):
        if self.anchors is not None:
            return self.anchors[0] if team == 1 else self.anchors[1]
        cx = world.map_center[0]
        h = world.map_extent[1]
        south, north = (cx, 0), (cx, h)
        return south if team == 1 else north

    def close(self) -> None:
        self._log.close()
