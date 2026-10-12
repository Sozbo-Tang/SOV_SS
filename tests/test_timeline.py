"""FE-T06 播放状态机测试：play/pause/speed/step/seek 纯逻辑（零 arcade/零 sim）。

覆盖面：游标夹取（seek/step 越界不抛）、播放态迁移（末拍 play 停留/到末自动
暂停）、倍速循环换档（环回绕，两方向）、advance 小数拍累积（10Hz×倍速、不足
整拍留余、暂停恒 0）、步进先暂停。本模块即 timeline.py 头注口径的机器断言。
"""
from __future__ import annotations

import unittest

from sovs.ui.timeline import TICK_HZ, PlaybackController


class TestPlaybackController(unittest.TestCase):

    def test_init_clamp_and_default_speed_1x(self):
        c = PlaybackController(1000, start_tick=5000)     # 起点越界→夹末拍
        self.assertEqual(c.tick, 1000)
        self.assertEqual(c.speed, 1.0)
        self.assertFalse(c.playing)

    def test_play_pause_toggle_and_end_of_replay(self):
        c = PlaybackController(100)
        c.play()
        self.assertTrue(c.playing)
        c.pause()
        self.assertFalse(c.playing)
        c.seek(100)                                        # 末拍处 play=原地停
        c.play()
        self.assertFalse(c.playing)
        c.seek(50)                                         # 回中拍：toggle 恢复播放
        c.toggle()
        self.assertTrue(c.playing)
        c.toggle()
        self.assertFalse(c.playing)

    def test_seek_clamp(self):
        c = PlaybackController(100, start_tick=50)
        self.assertEqual(c.seek(-5), 0)
        self.assertEqual(c.seek(999), 100)

    def test_step_pauses_and_clamps(self):
        c = PlaybackController(100, start_tick=98)
        c.play()
        self.assertEqual(c.step(), 99)
        self.assertFalse(c.playing)                        # 步进先暂停（逐拍观察语义）
        self.assertEqual(c.step(), 100)
        self.assertEqual(c.step(), 100)                    # 末拍封顶不越界
        self.assertEqual(c.step(-500), 0)

    def test_speed_cycle_wraps_both_directions(self):
        c = PlaybackController(10)                         # 档位 (0.5,1,2,4,8)
        seq = [c.faster() for _ in range(6)]
        self.assertEqual(seq, [2.0, 4.0, 8.0, 0.5, 1.0, 2.0])   # 顶档回绕
        self.assertEqual(c.slower(), 1.0)
        self.assertEqual(c.slower(), 0.5)
        self.assertEqual(c.slower(), 8.0)                  # 底档回绕

    def test_advance_accumulates_fractional_ticks(self):
        c = PlaybackController(1000)
        c.play()
        self.assertEqual(c.speed, 1.0)
        # 0.05s×10Hz×1x=0.5 拍：不足整拍留余、推进 0
        self.assertEqual(c.advance(0.05), 0)
        self.assertEqual(c.tick, 0)
        self.assertEqual(c.advance(0.05), 1)               # 余 0.5+0.5=1 拍
        self.assertEqual(c.tick, 1)
        c.faster()                                         # 2x：0.3s=6 拍
        self.assertEqual(c.advance(0.3), 6)
        self.assertEqual(c.advance(0.0), 0)                # dt=0 不动
        c.pause()
        self.assertEqual(c.advance(0.5), 0)                # 暂停恒 0

    def test_advance_pauses_at_end_and_never_exceeds(self):
        c = PlaybackController(100, start_tick=95)
        c.play()
        moved = c.advance(10.0)                            # 请 100 拍、余 5 拍到末
        self.assertEqual(moved, 5)
        self.assertEqual(c.tick, 100)
        self.assertFalse(c.playing)                        # 末拍自动暂停
        self.assertEqual(c.advance(1.0), 0)

    def test_pause_clears_fraction_accumulator(self):
        c = PlaybackController(100)
        c.play()
        c.advance(0.05)                                    # 余 0.5 拍
        c.pause()
        c.play()
        self.assertEqual(c.advance(0.05), 0)               # 暂停清零→不补跳
        self.assertEqual(c.advance(0.05), 1)

    def test_tick_hz_is_ten(self):
        self.assertEqual(TICK_HZ, 10)                      # 全局节拍口径锚定
