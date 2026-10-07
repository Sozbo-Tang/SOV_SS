"""整型几何。坐标整型厘米；禁止浮点与三角函数（math.isqrt 为精确整数运算）。"""
from __future__ import annotations

import math

from .types import Facing


def dist2(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def dist_cm(a: tuple[int, int], b: tuple[int, int]) -> int:
    return math.isqrt(dist2(a, b))


def isqrt_exact(n: int) -> int:
    """非负整数精确平方根下取（math.isqrt 直通）。整型开方单点收口本模块
    （2026-10-07 感知接线块：sensing 遮蔽通道弦长半弦项消费——sensing.py
    不直接引入 math 模块，经本函数取用；dist_cm 同源同纪律）。"""
    return math.isqrt(n)


def angle_diff(a: int, b: int) -> int:
    """有符号角差，(-180, 180]。"""
    d = (a - b) % 360
    if d > 180:
        d -= 360
    return d


def facing_of(hull_facing_deg: int, approach_deg: int, front_arc: int = 45,
              side_arc: int = 135) -> Facing:
    """按弹道入射角与车体朝向夹角映射命中面（伪代码 §F1）。"""
    d = abs(angle_diff(hull_facing_deg, approach_deg))
    if d <= front_arc:
        return Facing.FRONT
    if d <= side_arc:
        return Facing.SIDE
    return Facing.REAR


def octant_deg(dx: int, dy: int) -> int:
    """方向向量 → 45° 扇区角（0/45/.../315），纯整型比较。"""
    if dx == 0 and dy == 0:
        return 0
    adx, ady = abs(dx), abs(dy)
    if adx <= ady // 2:
        base = 0 if dy > 0 else 180
    elif ady <= adx // 2:
        base = 90 if dx > 0 else 270
    else:
        if dx > 0:
            base = 45 if dy > 0 else 135
        else:
            base = 315 if dy > 0 else 225
    return base


def approach_deg_of(frm: tuple[int, int], to: tuple[int, int]) -> int:
    """§F1 :334/§F4 :744 approach_deg_of——frm→to 方位角（8 扇区整型）。
    v1.7 全文零定义体（仅三处调用），签名按 :334 用例定标：resolve_hit 的
    approach_deg_of(p.pos, tgt.pos) = 弹道行进方向（机制版 v1.2 :474 p.approachDir
    同语义）；:744/:870 射界门取"指向目标的方位"须传 (e.pos, tgt.pos)——见登记表
    discrepancies（两处调用实参序在任一单一签名下不可两全，:744/:870 按语义换序）。"""
    return octant_deg(to[0] - frm[0], to[1] - frm[1])


def round_div(n: int, d: int) -> int:
    """整型四舍五入除法——§T 字面式 (2n+d)//(2d)（v1.7 GAP-15 裁定：向 +∞ 半舍入，
    floor 除法跨实现位级确定）：round_div(5,2)=3, round_div(-5,2)=-2, round_div(-1,2)=0。"""
    if d == 0:
        raise ZeroDivisionError("round_div by zero")
    return (2 * n + d) // (2 * d)


def step_toward(pos: tuple[int, int], dest: tuple[int, int],
                step_cm: int) -> tuple[tuple[int, int], bool]:
    """向 dest 走不超过 step_cm；返回 (新位置, 是否到达)。"""
    dx = dest[0] - pos[0]
    dy = dest[1] - pos[1]
    d = math.isqrt(dx * dx + dy * dy)
    if d <= step_cm:
        return dest, True
    return (pos[0] + round_div(dx * step_cm, d),
            pos[1] + round_div(dy * step_cm, d)), False
