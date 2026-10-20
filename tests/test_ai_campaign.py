"""tools/kev_campaign.py（Kev 数据工厂）测试：决策记录的侧别归属与胜者标注。

复测报告"问题一"回归（训练数据把败方决策错标为胜者）。内存探针照报告做法
"只替换世界结束条件与状态标记"：monkeypatch full_world→小战斗世界（双方互见、
三角色都有候选）、world_tick→N 拍后写 Settlement 强制结算、AgentSquad→_state
返回真实行动方标记（"p0"/"p1"——记录里的 state 即自证行动方）。零模型、零网络、
不起子进程；整局 13800 拍太慢，此处 30 拍覆盖 ground/air/reserve 各一轮。

修复前的行为（本文件各测试据此分辨）：_play_one 内红蓝两个 _Hook 共用一份
recs，且 _battle.side 统一取外层参数 side 而非 hook 自己的 player_index——
一遍对局把双方决策全收进同一列表并全标成目标 side；cmd_gen 再按整局
winner==side 筛选后把整份列表标 winner=True。于是败方（player_index=1）的
决策以 side=0、winner=True 导出；clone 两遍各收双方、互相重复。
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "tools"))   # kev_ab_match 裸 import 同目录

from sovs.ai.agents import AgentSquad  # noqa: E402
from sovs.sim.tick import Settlement, world_tick  # noqa: E402
from tests.test_ai_squad import combat_world  # noqa: E402

END_TICK = 30        # ground@0 / air@10 / reserve@20 各一轮后结算
WINNER = 0           # 强制红方（player_index=0）胜——蓝方照常决策但不该入库


def _load_campaign():
    """进程内装载 tools/kev_campaign.py（照 tests/test_ai_squad._load_tool 先例）。"""
    path = os.path.join(_REPO, "tools", "kev_campaign.py")
    spec = importlib.util.spec_from_file_location("kev_campaign_tool", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _MarkedSquad(AgentSquad):
    """状态标记探针：state 直接写真实行动方（_Hook 继承本类，_state 不被覆盖）。"""

    def _state(self, world):
        return f"p{self.player_index}"


def _actor(rec: dict) -> int:
    """记录里 state 标记解出的真实行动方。"""
    return int(rec["state"][1:])


@contextlib.contextmanager
def _probe(mod, *, winner: int = WINNER, end_tick: int = END_TICK):
    """替换世界构造 / 结束条件 / 状态标记三处，其余走 kev_campaign 真实代码。"""
    def _tick(world, *a, **kw):
        world_tick(world, *a, **kw)
        if world.tick >= end_tick and world.result is None:
            world.result = Settlement(winner=winner, obj_counts=(0, 0),
                                      unit_scores=(0, 0), hp_totals=(0, 0))

    with mock.patch.object(mod, "full_world", combat_world), \
            mock.patch.object(mod, "world_tick", _tick), \
            mock.patch.object(mod, "AgentSquad", _MarkedSquad):
        yield


def _gen(mod, *argv):
    """进程内直调 gen 子命令 → (rc, stdout JSONL 记录)；stderr 进度丢弃。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = mod.main(["gen", *argv])
    return rc, [json.loads(line) for line in out.getvalue().splitlines()
                if line.strip()]


# ── (a) winner 模式：双方决策并存、玩家 0 胜 ──

class TestWinnerModeSideAttribution(unittest.TestCase):
    """winner 模式输出里不得出现真实玩家=1 的记录，且每条 side==真实行动方。

    修复前：side=0 那遍把蓝方（p1）决策也收进 recs 并标 side=0；整局
    winner(0)==side(0) 通过筛选后全标 winner=True——输出里会出现
    state="p1" 而 _battle.side=0、winner=True 的记录，下列断言失败。
    """

    def test_play_one_collects_only_target_side(self):
        mod = _load_campaign()
        with _probe(mod):
            win0, recs0 = mod._play_one(7, 0, variant=True)
            win1, recs1 = mod._play_one(7, 1, variant=True)
        self.assertEqual((win0, win1), (WINNER, WINNER))
        self.assertTrue(recs0 and recs1)                 # 两侧在各自那遍都有决策
        for side, recs in ((0, recs0), (1, recs1)):
            for r in recs:
                self.assertEqual(_actor(r), side, r["_battle"])
                self.assertEqual(r["_battle"]["side"], side, r["_battle"])
        # 三角色各一轮（ground/air/reserve @ tick 0/10/20）——场景确有双方决策
        self.assertEqual([r["_battle"]["role"] for r in recs0],
                         ["ground", "air", "reserve"])
        self.assertEqual([r["_battle"]["role"] for r in recs1],
                         ["ground", "air", "reserve"])

    def test_gen_winner_mode_exports_winner_side_only(self):
        mod = _load_campaign()
        with _probe(mod):
            rc, rows = _gen(mod, "--mode", "winner", "--n-games", "1",
                            "--seed0", "7")
        self.assertEqual(rc, 0)
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(_actor(r), WINNER, r["_battle"])   # 败方 p1 不得出现
            self.assertEqual(r["_battle"]["side"], _actor(r))   # side=真实行动方
            self.assertIs(r["_battle"]["winner"], True)
        # 恰为胜方那一遍的全部决策（败方那遍 recs 非空却一条不出）
        self.assertEqual(len(rows), 3)
        # 记录形状向后兼容：kev.data.load_records 所需字段齐全、_battle 字段名不变
        for r in rows:
            self.assertIn("state", r)
            q = next(iter(r["questions"].values()))
            self.assertEqual(q["type"], "choice")
            self.assertIn("label", q)
            self.assertIn(q["label"], q["criteria"])
            self.assertEqual(set(r["_battle"]),
                             {"seed", "side", "role", "tick", "winner"})


# ── (b) clone 模式：side=0 与 side=1 分别调用 ──

class TestCloneModeSideAttribution(unittest.TestCase):
    """clone 对 side=0/1 各跑一遍：各自只含该侧记录、side==真实行动方、
    两侧都采到且不重复。

    修复前：两遍各收双方全部决策（recs0 与 recs1 内容相同，仅 side 标签
    不同）——"各自只含该侧"与"不重复"两条断言都失败。
    """

    def test_each_pass_collects_own_side_without_overlap(self):
        mod = _load_campaign()
        with _probe(mod):
            win0, recs0 = mod._play_one(7, 0, variant=False)
            win1, recs1 = mod._play_one(7, 1, variant=False)
        self.assertEqual((win0, win1), (WINNER, WINNER))   # 同一确定性对局
        self.assertTrue(recs0 and recs1)                   # 两侧都采到
        for side, recs in ((0, recs0), (1, recs1)):
            self.assertEqual({_actor(r) for r in recs}, {side})
            self.assertEqual({r["_battle"]["side"] for r in recs}, {side})

        def key(r):
            return r["_battle"]["tick"], r["_battle"]["role"], r["state"]

        self.assertFalse({key(r) for r in recs0} & {key(r) for r in recs1})
        self.assertEqual(len(recs0) + len(recs1), 6)       # 双方各三角色一轮

    def test_gen_clone_mode_labels_winner_per_real_side(self):
        mod = _load_campaign()
        with _probe(mod):
            rc, rows = _gen(mod, "--mode", "clone", "--n-games", "1",
                            "--seed0", "7")
        self.assertEqual(rc, 0)
        self.assertEqual(len(rows), 6)
        self.assertEqual({_actor(r) for r in rows}, {0, 1})   # 双侧都导出
        for r in rows:
            self.assertEqual(r["_battle"]["side"], _actor(r))
            self.assertIs(r["_battle"]["winner"], _actor(r) == WINNER)


if __name__ == "__main__":
    unittest.main()
