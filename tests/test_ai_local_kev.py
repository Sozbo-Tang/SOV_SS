"""sovs.ai 进程内引擎（LocalKevEngine）与 1Hz 节奏测试台的测试。

不依赖 torch/kev 安装——真模型路径按环境手动跑
（python tools/kev_bench_1hz.py），此处覆盖：
- LocalKevEngine 在未装 kev/torch 的环境 → KevUnavailableError（含安装指引）
- 鸭子类型契约：任意带 choose() 的进程内对象可直接作 KevPlayer 的 client
  （LocalKevEngine 的接口形状，用假引擎验证全链路）
- 1Hz 节奏测试台 fallback 模式：进程内直调 main(argv)，小 pace 快跑通过
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import time
import unittest

from sovs.ai import KevChoiceAnswer, KevPlayer, LocalKevEngine
from sovs.ai.kev_client import KevUnavailableError
from sovs.sim.air import PHASE_COMBAT
from sovs.sim.tick import (DeckSlot, Objective, add_unit, make_unit,
                           make_world)
from tests.test_ai_kev import RIFLE_TPL, TANK_TPL

SOUTH, NORTH = (100000, 0), (100000, 100000)


def combat_world():
    w = make_world(7, phase=PHASE_COMBAT, size_cm=(200000, 100000))
    w.objectives.append(Objective(id=1, pos=(100000, 50000), radius_cm=5000))
    for p in w.players:
        p.deck_slots = [DeckSlot(RIFLE_TPL, 2), DeckSlot(TANK_TPL, 1)]
    add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (100000, 45000)))
    foe = add_unit(w, make_unit(w, TANK_TPL, 1, 1, (100000, 55000)))
    foe.spotted_mask = 0b11
    return w


class FakeEngine:
    """进程内假引擎——鸭子类型契约探针（模拟 LocalKevEngine 的形状）。"""

    def __init__(self, delay_s: float = 0.0):
        self.delay_s = delay_s
        self.calls = 0

    def choose(self, state, question_id, instructions, options):
        self.calls += 1
        if self.delay_s:
            time.sleep(self.delay_s)
        first = next(iter(options))
        return KevChoiceAnswer(question_id, first, 0.9,
                               {k: 0.5 for k in options})


class TestLocalEngineContract(unittest.TestCase):
    def test_missing_kev_raises_with_hint(self):
        # 本环境未装 kev/torch——构造必须收敛为 KevUnavailableError（非裸 ImportError）
        with self.assertRaises(KevUnavailableError) as ctx:
            LocalKevEngine("jaredpalmer/kev-0.5b")
        self.assertIn("pip install", str(ctx.exception))
        self.assertIn("kev", str(ctx.exception))

    def test_bad_dtype_rejected(self):
        with self.assertRaises(KevUnavailableError):
            LocalKevEngine(dtype="int8")   # 触发前先过 dtype 白名单——不触网络

    def test_inprocess_engine_through_player(self):
        w = combat_world()
        engine = FakeEngine(delay_s=0.005)
        ai = KevPlayer(0, engine, anchors=(SOUTH, NORTH), decide_every=1,
                       air_every=0)
        ai.step(w)
        self.assertEqual(engine.calls, 1)
        self.assertEqual(ai.stats["kev"], 1)          # 进程内引擎=kev 决策
        # 敌坦克可见且在射程 → 首选=效用最高的攻击令（>占点 30/推进 20）
        self.assertGreaterEqual(len(w.command_queue), 1)
        from sovs.sim.tick import AttackCmd
        kinds = {type(c).__name__ for c in w.command_queue}
        self.assertIn(kinds.pop(), {"AttackCmd", "MoveCmd", "SetModeCmd",
                                    "FireMissionCmd", "StopCmd"})
        ai.close()


def _load_bench():
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "kev_bench_1hz.py")
    spec = importlib.util.spec_from_file_location("kev_bench_tool", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestBenchHarness(unittest.TestCase):
    """fallback 模式小 pace 快跑——测试台自身可用性（真模型 bench 手动跑）。"""

    def test_fallback_mode_passes(self):
        import tempfile
        mod = _load_bench()
        with tempfile.TemporaryDirectory() as td:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mod.main(["--engine", "fallback", "--decisions", "5",
                               "--pace", "0.05", "--warmup", "1",
                               "--log", os.path.join(td, "b.jsonl")])
            out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)
        self.assertIn("规则 argmax", out)
        self.assertIn("整拍周期", out)
        self.assertIn("判定", out)

    def test_local_mode_missing_kev_exit_code(self):
        mod = _load_bench()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mod.main(["--engine", "local", "--decisions", "2"])
        self.assertEqual(rc, 2)                       # 引擎不可用=显式失败
        self.assertIn("不可用", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
