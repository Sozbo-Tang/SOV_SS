"""确定性 PCG32（TECH-00：禁用 random 模块——跨解释器版本不稳定）。"""
from __future__ import annotations

MASK64 = (1 << 64) - 1
_MULT = 6364136223846793005


class PCG32:
    """整型 PCG32；同 (seed, stream) 恒产生同序列，跨平台跨版本稳定。"""

    __slots__ = ("state", "inc")

    def __init__(self, seed: int, stream: int = 0) -> None:
        self.state = 0
        self.inc = ((stream << 1) | 1) & MASK64
        self.next()
        self.state = (self.state + (seed & MASK64)) & MASK64
        self.next()

    def next(self) -> int:
        old = self.state
        self.state = (old * _MULT + self.inc) & MASK64
        xorshifted = (((old >> 18) ^ old) >> 27) & 0xFFFFFFFF
        rot = (old >> 59) & 31
        return ((xorshifted >> rot) | (xorshifted << ((32 - rot) & 31))) & 0xFFFFFFFF

    def below(self, n: int) -> int:
        """[0, n) 均匀整数。"""
        return self.next() % n

    def chance_bp(self, basis_points: int) -> bool:
        """以 bp（万分比，0..10000）概率为真。"""
        return self.below(10000) < basis_points

    def sym(self, radius: int) -> int:
        """[-radius, radius] 均匀整数（方形散布，避免三角函数）。"""
        return self.below(2 * radius + 1) - radius


def mix64(x: int) -> int:
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK64
    return x ^ (x >> 31)


def channel_seed(global_seed: int, channel: int) -> int:
    return mix64((global_seed + 0x9E3779B97F4A7C15 * (channel + 1)) & MASK64)


class Channels:
    """按事件流分通道的子流：任一系统的随机消耗不扰动其他系统（回放稳定）。

    通道号与伪代码 §T 一致：HIT/SCATTER/SPOT/CRIT/SNIPER/SONAR/ECONOMY。
    """

    HIT = 0
    SCATTER = 1
    SPOT = 2
    CRIT = 3   # 〔口子③·预留 2026-10-07 D071 全拆〕通道号冻结不回收（§T 编号纪律；
               # SPOT/SONAR 零消费占号先例）——暴击掷骰拆除后 CRIT 零消费者，
               # 恢复 roll_crit 即用；channels_used 名单留 CRIT 即零消费自证
    SNIPER = 4
    SONAR = 5
    ECONOMY = 6
    AIR = 7  # 航空独立通道（任务授权增量：通道 7 空闲、_COUNT=8 原样——不复用地面 0~6 序列）
    _COUNT = 8

    def __init__(self, global_seed: int) -> None:
        self._rngs = [PCG32(channel_seed(global_seed, c), c) for c in range(self._COUNT)]

    def rng(self, channel: int) -> PCG32:
        return self._rngs[channel]

    def hit(self) -> PCG32:
        return self._rngs[self.HIT]

    def scatter(self) -> PCG32:
        return self._rngs[self.SCATTER]

    def crit(self) -> PCG32:
        # 〔口子③·预留 2026-10-07 D071 全拆〕拆后零消费者 accessor，原样保留——
        # 重启用即用（roll_crit 恢复后首消费者回归；SPOT/SONAR 无 accessor 先例对照）
        return self._rngs[self.CRIT]

    def sniper(self) -> PCG32:
        return self._rngs[self.SNIPER]

    def air(self) -> PCG32:
        return self._rngs[self.AIR]

    def economy(self) -> PCG32:
        return self._rngs[self.ECONOMY]
