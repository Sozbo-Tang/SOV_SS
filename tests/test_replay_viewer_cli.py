"""回放查看器 CLI 参数面（FE-T06 门禁口径）：--smoke 零参数缺省全展开。

背景：门禁实测以零参数 `--smoke` 调用（nargs='+' 系 argparse exit 2
「expected at least one argument」——评审后终口径：零参数=data/gen/replays/
内全部 *.jsonl 稳定排序展开；显式传一或多路径则按传入清单——两种调用共享
同一 smoke() 校验体）。本测试 mock 重操作（真重放逐位比对在
tests/test_golden_replay.py 全量跑，不在此重复消耗），只锁参数面接线：
零参/显式/无旗标三分支 + all_replays 排序与空目录报错。
"""
import os
import unittest
from unittest import mock

from tools import replay_viewer


class TestSmokeArgSurface(unittest.TestCase):
    """--smoke 参数分支（mock smoke/interactive——CLI 布线断言，零真重放）。"""

    def test_smoke_zero_args_defaults_to_all_replays(self):
        """零参数 --smoke=缺省展开 REPLAY_DIR 全部 *.jsonl（门禁实测口径）。"""
        with mock.patch.object(replay_viewer, "smoke", return_value=0) as m:
            rc = replay_viewer.main(["--smoke"])
        m.assert_called_once_with(replay_viewer.all_replays())
        self.assertEqual(rc, 0)

    def test_smoke_explicit_paths_pass_through(self):
        """显式路径（一或多）按传入清单透传（nargs 多值语义保持）。"""
        with mock.patch.object(replay_viewer, "smoke", return_value=1) as m:
            rc = replay_viewer.main(["--smoke", "a.jsonl", "b.jsonl"])
        m.assert_called_once_with(["a.jsonl", "b.jsonl"])
        self.assertEqual(rc, 1)

    def test_no_smoke_flag_goes_interactive_not_smoke(self):
        """无旗标走交互观战（缺省最新一条），smoke 不被触碰。"""
        with mock.patch.object(replay_viewer, "latest_replay",
                               return_value="x.jsonl") as _lr, \
             mock.patch.object(replay_viewer, "interactive",
                               return_value=0) as inter, \
             mock.patch.object(replay_viewer, "smoke", return_value=0) as m:
            replay_viewer.main([])
        m.assert_not_called()
        inter.assert_called_once_with(["x.jsonl"])


class TestAllReplays(unittest.TestCase):
    """缺省展开面：稳定排序 + 目录缺失/为空明确报错（SystemExit 非静默）。"""

    def test_missing_or_empty_dir_raises_system_exit(self):
        for bad in ("/nonexistent/sovss/replays/xyz",):   # 缺失目录
            with mock.patch.object(replay_viewer, "REPLAY_DIR", bad):
                with self.assertRaises(SystemExit):
                    replay_viewer.all_replays()
        import tempfile
        with tempfile.TemporaryDirectory() as td:          # 存在但空
            with mock.patch.object(replay_viewer, "REPLAY_DIR", td):
                with self.assertRaises(SystemExit):
                    replay_viewer.all_replays()

    @unittest.skipUnless(
        os.path.isdir(replay_viewer.REPLAY_DIR)
        and any(n.endswith(".jsonl")
                for n in os.listdir(replay_viewer.REPLAY_DIR)),
        "data/gen/replays 黄金回放未录制（先 python3 tools/record_golden.py）")
    def test_all_replays_sorted_jsonl(self):
        paths = replay_viewer.all_replays()
        self.assertEqual(paths, sorted(paths))
        self.assertTrue(all(p.endswith(".jsonl") for p in paths))
        # 现值锚：首批 3 条黄金回放命名约定（缺一=录制面退化，全量比对另见
        # tests/test_golden_replay.py）
        names = {os.path.basename(p) for p in paths}
        self.assertTrue({"golden_rulevrule_seed42.jsonl",
                         "golden_rulevrule_seed7.jsonl",
                         "golden_air_seed42.jsonl"} <= names, names)


if __name__ == "__main__":
    unittest.main()
