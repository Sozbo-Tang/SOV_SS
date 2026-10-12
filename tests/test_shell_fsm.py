"""FE-T07 四页状态机（sovs/ui/shell_fsm.py）纯逻辑测试：零 arcade、零 sovs.sim。

口径锚（FE-01 §5 FE-T07 + FE-T02 帧契约）：
- 页序 config→deploy→battle→settle；游戏内三页迁移由状态帧 phase 字段驱动
  （state_frame.py:141 phase ∈ deploy/combat/settle——fsm 不看 World 只看帧）；
- 盲部署计时 600t＝60s（tables.py:266 实现现值；勿抄 GDD-00 D007 旧 90s）；
- 框选=帧内己方队单位落框筛选（敌单位迷雾已由帧视角裁剪——fsm 不重复实现
  迷雾，只做几何筛选）；
- 首批五组命令登记面：移动族/攻击/炮击任务/空军呼叫/烟幕冲刺姿态。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.ui.shell_fsm import (DEPLOY_TICKS_IMPL, ORDER_GROUPS_FIRST_BATCH,  # noqa: E402
                               ShellFsm)


def _frame(phase: str, tick: int, *, units=(), result=None, team: int = 0) -> dict:
    """最小状态帧（fsm 消费面：phase/tick/units/view/result——state_frame 字段子集）。"""
    return {"schema_version": "1.0", "tick": tick, "phase": phase, "view": team,
            "map_cm": [200000, 100000], "units": list(units), "aircraft": [],
            "objectives": [], "players": [], "smoke_zones": [], "projectiles": [],
            "buildings": [], "result": result}


def _unit(uid: int, team: int, x: int, y: int) -> dict:
    return {"id": uid, "team": team, "pos_cm": [x, y], "hp": 10, "hp_max": 10,
            "category": 1, "name": "u%d" % uid}


class TestPageFlow(unittest.TestCase):
    """页序与帧驱动迁移。"""

    def test_initial_page_is_config(self):
        self.assertEqual(ShellFsm().page, "config")

    def test_start_moves_to_deploy_only_from_config(self):
        f = ShellFsm()
        f.start_deploy()
        self.assertEqual(f.page, "deploy")
        f.on_frame(_frame("combat", 700))            # 游戏中不可回 config
        self.assertEqual(f.page, "battle")
        with self.assertRaises(AssertionError):
            f.start_deploy()                          # 只许自 config 起局

    def test_frames_drive_deploy_battle_settle(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("deploy", 120))
        self.assertEqual(f.page, "deploy")
        f.on_frame(_frame("combat", 601))
        self.assertEqual(f.page, "battle")
        f.on_frame(_frame("settle", 13800, result={"winner": 0}))
        self.assertEqual(f.page, "settle")

    def test_settle_needs_result_frame(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("combat", 700))
        f.on_frame(_frame("settle", 13800, result={"winner": 1}))
        self.assertEqual(f.page, "settle")
        self.assertEqual(f.result["winner"], 1)       # 结算页数据源=帧 result 字段

    def test_reset_back_to_config(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("combat", 700))
        f.reset()
        self.assertEqual(f.page, "config")
        self.assertEqual(f.selected, ())              # 选区/命令态一并复位
        self.assertIsNone(f.armed_order)


class TestDeployTimer(unittest.TestCase):
    """60s 盲部署计时（600t 实现现值）。"""

    def test_deploy_ticks_constant_is_impl_value(self):
        self.assertEqual(DEPLOY_TICKS_IMPL, 600)      # tables.py:266 现值（非 GDD 90s）

    def test_countdown_from_frame_tick(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("deploy", 0))
        self.assertEqual(f.deploy_ticks_left, 600)
        self.assertEqual(f.deploy_seconds_left, 60.0)
        f.on_frame(_frame("deploy", 240))
        self.assertEqual(f.deploy_ticks_left, 360)
        self.assertEqual(f.deploy_seconds_left, 36.0)
        f.on_frame(_frame("deploy", 600))             # 末拍夹取 0（负数不出现）
        self.assertEqual(f.deploy_ticks_left, 0)

    def test_countdown_zero_outside_deploy(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("combat", 700))
        self.assertEqual(f.deploy_ticks_left, 0)


class TestSelection(unittest.TestCase):
    """框选：己方队 + 帧单位几何筛选（迷雾已由帧裁剪）。"""

    def test_box_select_filters_own_team_within_rect(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("deploy", 10, units=[
            _unit(1, 0, 10000, 20000), _unit(2, 0, 50000, 20000),
            _unit(3, 1, 20000, 20000),                # 敌队（帧内=已侦察敌）
            _unit(4, 0, 90000, 20000),
        ]))
        ids = f.box_select((5000, 10000), (60000, 30000))
        self.assertEqual(ids, (1, 2))                 # 敌队剔除、界外剔除、帧序稳定

    def test_box_select_normalizes_drag_direction(self):
        f = ShellFsm()
        f.start_deploy()
        f.on_frame(_frame("deploy", 10, units=[_unit(1, 0, 20000, 50000)]))
        self.assertEqual(f.box_select((60000, 80000), (0, 0)), (1,))  # 反向拖拽归一

    def test_select_units_replaces_selection(self):
        f = ShellFsm()
        f.start_deploy()
        f.select_units((5, 6))
        self.assertEqual(f.selected, (5, 6))
        f.select_units((7,))
        self.assertEqual(f.selected, (7,))
        f.clear_selection()
        self.assertEqual(f.selected, ())


class TestOrders(unittest.TestCase):
    """首批五组命令登记面 + 待令态。"""

    def test_first_batch_five_groups(self):
        self.assertEqual([g[0] for g in ORDER_GROUPS_FIRST_BATCH],
                         ["move", "attack", "fire_mission", "air", "smoke_sprint"])

    def test_arm_order_and_clear(self):
        f = ShellFsm()
        f.arm_order("attack")
        self.assertEqual(f.armed_order, "attack")
        f.arm_order("fire_mission")
        self.assertEqual(f.armed_order, "fire_mission")
        f.clear_order()
        self.assertIsNone(f.armed_order)

    def test_arm_order_rejects_unknown_group(self):
        f = ShellFsm()
        with self.assertRaises(ValueError):
            f.arm_order("nuclear_launch")

    def test_armed_order_cleared_by_page_reset(self):
        f = ShellFsm()
        f.arm_order("air")
        f.reset()
        self.assertIsNone(f.armed_order)


if __name__ == "__main__":
    unittest.main()
