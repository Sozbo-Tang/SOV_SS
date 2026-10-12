"""决策日志（JSONL）：每个决策一条——回放依据与审计面。

口径（仓库既有「回放 = 种子 + 命令流」）：Kev 采样不可跨机逐位复现
（bf16 前向 + 批合并均影响概率），故可复现性锚在**落盘的命令流**——
日志逐决策记录 tick/命令描述符，重放=同 seed 重放命令流，无需模型。

stdlib-only：io/os/json/pathlib。

〔FE-T03 2026-10-11：describe_command 本体迁 sovs/sim/wire.py（wire schema 生成，
全命令族 35 类覆盖+旧键等价回归口径见该处头注；等价断言=tests/test_wire.py 对
本文件旧实现冻结快照逐键比对）——本模块再出口，导入面
`from sovs.ai.decision_log import describe_command` 不变。〕
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from sovs.sim.wire import describe_command  # noqa: F401（再出口——见头注）


class DecisionLog:
    """追加式 JSONL 日志。path=None → 空日志（no-op，缺省即无文件面）。"""

    def __init__(self, path: str | os.PathLike | None):
        self.path = str(path) if path is not None else None
        self._fh = None
        if self.path:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            self._fh = open(self.path, "a", encoding="utf-8")

    def record(self, entry: dict) -> None:
        """写一条决策记录（调用方给结构化字段；本方法只补时间戳并落盘）。"""
        if self._fh is None:
            return
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               **entry}
        self._fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "DecisionLog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
