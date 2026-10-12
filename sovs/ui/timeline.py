"""播放状态机（FE-T06）：play/pause/speed/step/seek 纯逻辑——pytest 可测无 arcade。

结论先行：观战器的播放控制（播放态/拍游标/倍速档/步进/定位）全部收敛在本
模块，view 窗口层（viewer_window.py）只做按键→方法调用与帧呈现；本模块零
渲染依赖（不 import arcade）、零仿真依赖（不 import sovs.sim——接线铁律见
sovs/ui/__init__.py），故 CI 免装渲染栈也能全量 pytest。

口径：
- tick 时基=仿真 10Hz（1 秒=10 拍），advance(dt) 按「倍速×dt×10」累积小数拍、
  整拍推进（返回本轮实际推进数——调用方据此驱动重放）；
- 倍速档位 (0.5, 1, 2, 4, 8)——↑/↓ 或 +/- 循环换档（环不封顶回绕）；
- 播放到末拍自动暂停（result 面板由帧数据驱动，不由本模块管理）；
- 游标夹取 [0, total_ticks]：step/seek 一律 clamp，越界不抛。
"""
from __future__ import annotations

TICK_HZ = 10                      # 仿真节拍（10 拍/秒——tables/TECH-00 全局口径）
SPEED_STEPS: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0, 8.0)   # 倍速档（循环换档）


class PlaybackController:
    """观战播放状态机（纯逻辑；窗口层每帧调 advance(dt) 取推进拍数）。"""

    def __init__(self, total_ticks: int, *, start_tick: int = 0,
                 speeds: tuple[float, ...] = SPEED_STEPS):
        self.total_ticks = max(0, int(total_ticks))
        self.speeds = tuple(speeds) or SPEED_STEPS
        self._speed_idx = min(range(len(self.speeds)),
                              key=lambda i: abs(self.speeds[i] - 1.0))
        self.playing = False
        self._acc = 0.0                     # 小数拍累积（advance 消费）
        self.tick = self._clamp(int(start_tick))

    # ── 内部 ──

    def _clamp(self, tick: int) -> int:
        return max(0, min(int(tick), self.total_ticks))

    # ── 播放态 ──

    def play(self) -> None:
        """继续播放（末拍处再 play=原地停，不回绕）。"""
        if self.tick < self.total_ticks:
            self.playing = True

    def pause(self) -> None:
        self.playing = False
        self._acc = 0.0                     # 暂停清小数拍（恢复不跳帧）

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    # ── 游标 ──

    def seek(self, tick: int) -> int:
        """定位到目标拍（clamp；小数拍清零），返回实际到达拍。"""
        self._acc = 0.0
        self.tick = self._clamp(tick)
        return self.tick

    def step(self, delta: int = 1) -> int:
        """步进（默认先暂停——逐拍观察语义），返回实际到达拍。"""
        self.pause()
        self.tick = self._clamp(self.tick + int(delta))
        return self.tick

    # ── 倍速 ──

    @property
    def speed(self) -> float:
        return float(self.speeds[self._speed_idx])

    def faster(self) -> float:
        """升档（顶档回绕最低档——「倍速循环」口径）。"""
        self._speed_idx = (self._speed_idx + 1) % len(self.speeds)
        return self.speed

    def slower(self) -> float:
        """降档（底档回绕最高档）。"""
        self._speed_idx = (self._speed_idx - 1) % len(self.speeds)
        return self.speed

    # ── 帧驱动 ──

    def advance(self, dt_seconds: float) -> int:
        """按当前倍速消费一段真实时长 → 本轮应推进的整拍数（未播放=0）。

        小数拍累积到下一轮；到末拍自动暂停且永不越界。
        """
        if not self.playing or dt_seconds <= 0:
            return 0
        self._acc += float(dt_seconds) * TICK_HZ * self.speed
        whole = int(self._acc)
        if whole <= 0:
            return 0
        self._acc -= whole
        target = self._clamp(self.tick + whole)
        moved = target - self.tick
        self.tick = target
        if self.tick >= self.total_ticks:
            self.pause()                    # 末拍自动暂停（结算面板由帧驱动）
        return moved
