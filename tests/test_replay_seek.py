"""FE-T06 Replayer 增量会话测试：advance/seek 现场推导 + 检查点回退重建。

覆盖面（对黄金回放 golden_air_seed42 实测）：
- 增量分段推进与一次性全量重放逐拍等价（分段沿途每拍校验和照核，到达拍
  state_checksum == 记录值）；
- 回退 seek=最近检查点（600 拍档）重放推导至目标拍，指纹仍逐位一致；
  检查点可丢弃重建（丢弃后 seek 结果不变——正确性不依赖快照）；
- seek 到末拍=完整重放，末帧 phase=SETTLE 且 result 非空（观战结算面板数据面）；
- seek 预算：全新会话冷 seek 到末拍 < 5s（验收上限 5s/次——实测量级断言，
  CI 慢机余量按 5s 验收线本身）。
"""
from __future__ import annotations

import os
import time
import unittest

from sovs.sim.wire import (CHECKPOINT_EVERY, Replayer, state_checksum,
                           state_fingerprint_text)

REPLAY = os.path.join("data", "gen", "replays", "golden_air_seed42.jsonl")


@unittest.skipUnless(os.path.exists(REPLAY), "黄金回放未录制（先 tools/record_golden.py）")
class TestReplaySeek(unittest.TestCase):

    def _open(self) -> Replayer:
        rep = Replayer(REPLAY)
        rep.open()
        return rep

    def test_incremental_advance_matches_recorded_checksums(self):
        rep = self._open()
        rep.advance(700)                       # 过首检查点（600）
        rep.advance(1_300)                     # 分段再推（增量=同一确定性重放）
        self.assertEqual(rep.cursor, 1_300)
        self.assertEqual(state_checksum(rep.world), rep.checksums[1_300])
        self.assertEqual(state_fingerprint_text(rep.world).startswith("t1300:"),
                         True)
        self.assertIn(CHECKPOINT_EVERY, rep._checkpoints)

    def test_backward_seek_rebuilds_from_checkpoint(self):
        rep = self._open()
        rep.advance(1_200)
        rep.seek(300)                          # 回退跨检查点（600<300 重建自 0）
        self.assertEqual(rep.cursor, 300)
        self.assertEqual(state_checksum(rep.world), rep.checksums[300])
        rep.seek(650)                          # 再前跳：600 检查点恢复+50 拍推导
        self.assertEqual(state_checksum(rep.world), rep.checksums[650])

    def test_checkpoints_are_dropable_rebuildable(self):
        rep = self._open()
        rep.advance(1_200)
        rep._checkpoints.clear()               # 丢弃全部快照——可随时从命令流重建
        rep._checkpoints[0] = None
        rep.seek(900)
        self.assertEqual(rep.cursor, 900)
        self.assertEqual(state_checksum(rep.world), rep.checksums[900])

    def test_seek_to_end_settles_with_result(self):
        rep = self._open()
        rep.seek(100)                          # 先小步走（非直接冷 seek）
        rep.seek(rep.ticks[-1])
        self.assertEqual(rep.cursor, rep.ticks[-1])
        self.assertEqual(rep.world.phase, 2)   # PHASE_SETTLE
        self.assertIsNotNone(rep.world.result)

    def test_cold_seek_to_end_within_budget(self):
        rep = self._open()
        t0 = time.perf_counter()
        rep.seek(rep.ticks[-1])                # 最坏情形：冷会话直 seek 到末拍
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 5.0, "seek 超 5s 验收预算：%.2fs" % elapsed)

    def test_run_is_reentrant_after_incremental_use(self):
        rep = self._open()
        rep.advance(300)
        world = rep.run()                      # run 自建会话（不串增量态）
        self.assertEqual(world.tick, rep.ticks[-1])
        self.assertEqual(rep.cursor, rep.ticks[-1])
