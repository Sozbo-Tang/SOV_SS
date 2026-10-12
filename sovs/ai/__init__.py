"""AI 玩家层（sovs.ai）：仿真核心外部的决策适配——引擎管事实与合法性，模型管选择。

三层结构（stdlib-only，零新增第三方依赖；sovs.sim 核心不受本包影响）：
- kev_client：Kev 决策服务 HTTP 客户端（/v1/systemone，urllib 实现）
- actions/state_view：合法动作枚举+效用打分 / 迷雾过滤后的态势摘要
- kev_player：KevPlayer 虚拟玩家（HeadlessAI 即插即用替代，规则兜底+决策日志）
- agents：AgentSquad 四角色班组（1Hz 地面→空中→预备队 轮转，与 KevPlayer 并存）

平台兼容：客户端与播放器不依赖 torch——CUDA / Apple Silicon (MLX/MPS) /
CPU 的差异全部由 kev.serve 服务端承载（tools/kev_serve.py 负责探测与启动）。
"""
from sovs.ai.actions import (Candidate, air_candidates, build_commands,
                             deploy_candidates, enumerate_candidates,
                             purchase_candidates)
from sovs.ai.agents import AgentSquad, split_air_candidates
from sovs.ai.decision_log import DecisionLog, describe_command
from sovs.ai.kev_client import KevChoiceAnswer, KevClient, KevUnavailableError
from sovs.ai.kev_local import LocalKevEngine
from sovs.ai.kev_player import KevPlayer
from sovs.ai.state_view import situation_brief

__all__ = [
    "Candidate", "air_candidates", "build_commands", "deploy_candidates",
    "enumerate_candidates", "purchase_candidates",
    "AgentSquad", "split_air_candidates",
    "DecisionLog", "describe_command",
    "KevChoiceAnswer", "KevClient", "KevUnavailableError",
    "KevPlayer", "LocalKevEngine", "situation_brief",
]
