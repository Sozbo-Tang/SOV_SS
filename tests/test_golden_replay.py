"""FE-T03 黄金回放验收：data/gen/replays/ 全部回放逐位比对 + 航空九令覆盖断言。

- 对 data/gen/replays/ 下全部黄金回放跑 Replayer 全量重放（逐 tick 校验和在
  Replayer.run 内核对——错位即抛）；本地即 FE-T04 跨平台基线的单端形态。
- 航空场景文件实际覆盖九令（读 rec:cmd 命令类型集合，与录制侧核对清单同源——
  AIR_NINE/GROUND_REQUIRED import 自 tools/record_golden，单一事实源）。
"""
import json
import pathlib
import unittest

from sovs.sim.wire import Replayer
from tools.record_golden import AIR_NINE, GROUND_REQUIRED

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "data" / "gen" / "replays"
EXPECTED_FILES = ("golden_rulevrule_seed42.jsonl",   # 规则 vs 规则
                 "golden_rulevrule_seed7.jsonl",     # 不同种子
                 "golden_air_seed42.jsonl")          # 航空覆盖场景（九令注入）


def _cmd_kinds(path: pathlib.Path) -> set:
    kinds = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            if obj.get("rec") == "cmd":
                kinds.add(obj["wire"]["cmd"])
    return kinds


class TestGoldenReplays(unittest.TestCase):
    def test_expected_golden_assets_committed(self):
        # 入库测试资产三件齐（命名约定 golden_<mode>_seed<seed>.jsonl）
        for name in EXPECTED_FILES:
            self.assertTrue((GOLDEN_DIR / name).is_file(),
                            "黄金回放缺失：%s" % name)

    def test_all_golden_replays_verify_bit_exact(self):
        files = sorted(GOLDEN_DIR.glob("golden_*.jsonl"))
        self.assertGreaterEqual(len(files), len(EXPECTED_FILES))
        for path in files:
            with self.subTest(replay=path.name):
                world = Replayer(path).run()       # 逐 tick 校验和核对在 run 内
                self.assertIsNotNone(world.result)  # 整局走到自然结算（D031 裁决）

    def test_air_golden_covers_nine_air_commands(self):
        # 航空场景实际覆盖九令+关键地面命令族（录制侧同源清单——不齐=录制/回放
        # 资产损坏，红）
        path = GOLDEN_DIR / "golden_air_seed42.jsonl"
        kinds = _cmd_kinds(path)
        self.assertLessEqual(set(AIR_NINE), kinds,
                             "缺航空命令：%s" % sorted(set(AIR_NINE) - kinds))
        self.assertLessEqual(set(GROUND_REQUIRED), kinds,
                             "缺关键地面命令：%s"
                             % sorted(set(GROUND_REQUIRED) - kinds))

    def test_rulevrule_goldens_cover_key_ground_commands(self):
        for name in ("golden_rulevrule_seed42.jsonl",
                     "golden_rulevrule_seed7.jsonl"):
            kinds = _cmd_kinds(GOLDEN_DIR / name)
            self.assertLessEqual(set(GROUND_REQUIRED), kinds,
                                 "%s 缺关键地面命令" % name)


if __name__ == "__main__":
    unittest.main()
