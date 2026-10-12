"""程序化字形绘制（FE-T06）：单位/飞机/占点/烟区/弹丸的矢量图元——零图片资源。

结论先行：观战 v1 一切视觉元素为程序化绘制（形状/纯色/线框，本模块+palette
为唯一画法事实源）；贴图槽位见 palette.TEXTURE_SLOTS（恒 None，引入时登记）。
本模块只 import arcade 与本包 palette——不 import sovs.sim/sovs.ai（接线铁律，
tests/test_arch_constraints.py 守卫），画法参数全部由调用方从 dict 状态帧取值。

单位字形六类（FE-T06 画法定档，色板对齐 GDD-01 六类）：
  侦察=斜杠圆 / 步兵=矩形对角线 / 装甲=矩形内椭圆 / 火支=实心圆 /
  防空后勤=方形对角 / 指挥=星标（帧 v1 无识别位——card_key/标志位联合键缺口，
  美术需求文档立项钉死；字形先行实现，入口识别位就绪即点亮）。
朝向短线：帧 v1 字段档不含单位/飞机 facing（FE-T02 冻结档），先按
frame.get("facing_deg") 惰性取值——缺位不画（未来字段槽位，非硬凑数据）。

arcade 3.3 API 注：矩形图元为 draw_lrbt_*（left,right,bottom,top 参数序）。
"""
from __future__ import annotations

import math

import arcade

from .palette import (AIR_OUTLINE_DASH, CATEGORY_COLORS, HP_HIGH, HP_LOW,
                      PROJECTILE, SMOKE_FILL, SUPPRESS_MARK, TEAM_COLORS,
                      UNOWNED_COLOR)

# 单位字形基准半径（px）与 HP 条规格
GLYPH_R = 9
HP_BAR_W = 20
HP_BAR_H = 3
MAP_RING_GRAY = (120, 120, 120, 200)      # 占点范围界圈（灰细线）


def team_color(team: int):
    """队色（未知队号落中立灰——帧数据自洽时不触发）。"""
    return TEAM_COLORS.get(int(team), UNOWNED_COLOR)


def owner_color(owner):
    """占点/归属色（None=无主灰）。"""
    return UNOWNED_COLOR if owner is None else team_color(owner)


def draw_unit_glyph(x: float, y: float, *, category: int, team: int,
                    hp_pct: int = 100, suppressed: bool = False,
                    moving: bool = False, facing_deg=None, selected: bool = False):
    """单位：类别字形 + 队色描边 + HP 窄条 + 压制角标 + 朝向短线（未来槽位）。

    取数面=状态帧 units 条目（viewer_window 逐字段传入——本函数不触碰帧结构）。
    """
    fill = CATEGORY_COLORS.get(int(category), UNOWNED_COLOR)
    edge = team_color(team)
    r = GLYPH_R
    if category == 0:                       # 侦察=圆+斜杠
        arcade.draw_circle_outline(x, y, r, edge, 2)
        _slash(x, y, r, fill)
    elif category == 1:                     # 步兵=矩形对角线
        arcade.draw_lrbt_rectangle_outline(x - r, x + r, y - r, y + r, edge, 2)
        _diagonal(x, y, r, fill)
    elif category == 2:                     # 装甲=矩形内椭圆
        arcade.draw_lrbt_rectangle_outline(x - r, x + r, y - r, y + r, edge, 2)
        arcade.draw_ellipse_outline(x, y, r - 2, r * 0.6, fill, 2)
    elif category == 3:                     # 火支=实心圆
        arcade.draw_circle_filled(x, y, r - 2, fill)
        arcade.draw_circle_outline(x, y, r, edge, 2)
    elif category == 4:                     # 防空后勤=方形对角（与步兵区分：叉而非单对角）
        arcade.draw_lrbt_rectangle_outline(x - r, x + r, y - r, y + r, edge, 2)
        _slash(x, y, r, fill)               # 对角叉两臂
        _diagonal(x, y, r, fill)
    else:                                   # 指挥=星标（识别位缺口，见头注）
        _star(x, y, r, fill, edge)
    # 朝向短线（未来槽位：帧 v1 无 facing——就绪即画）
    if facing_deg is not None:
        rad = math.radians(90.0 - float(facing_deg))     # 0°=北，顺时针
        arcade.draw_line(x, y, x + (r + 7) * math.cos(rad),
                         y + (r + 7) * math.sin(rad), edge, 2)
    if moving:                              # 机动角标：字形单位底部小三角
        arcade.draw_triangle_filled(x - 4, y - r - 5, x + 4, y - r - 5,
                                    x, y - r - 1, edge)
    if suppressed:                          # 压制角标：左上角短竖条
        arcade.draw_lrbt_rectangle_filled(x - r - 4, x - r - 1, y + r,
                                          y + r + 4, SUPPRESS_MARK)
    _hp_bar(x, y + r + 5, hp_pct)
    if selected:                            # 预留：点选高亮框（观战 v1 未接线）
        arcade.draw_lrbt_rectangle_outline(x - r - 3, x + r + 3, y - r - 9,
                                           y + r + 9, arcade.color.WHITE, 1)


def draw_aircraft_glyph(x: float, y: float, *, team: int, alt_tier: str = "mid",
                        spotted: bool = False, facing_deg=None,
                        selected: bool = False):
    """飞机：队色三角 + 高度层虚线圈（low=密小圈/mid=中圈/high=疏大圈）。

    spotted=True 加白点中心——「我机被对方探测」自报状态（state_frame 口径）。
    alt_tier 取值 low/mid/high（帧 aircraft.alt_tier）。
    〔GP-01 §4 ①段（帧 1.1 富化）：+facing_deg 机头朝向线（octant_deg 八向档，
    0°=北顺时针——与单位字形同口径；缺位不画=观战 v1 兼容）＋selected 选中
    角框（可玩壳空选区高亮——观战 v1 不传即不画）。〕
    """
    edge = team_color(team)
    arcade.draw_triangle_filled(x, y + 9, x - 7, y - 6, x + 7, y - 6, edge)
    r = {"low": 10, "mid": 14, "high": 18}.get(alt_tier, 14)
    segs = 5 if alt_tier == "low" else 8
    _dashed_circle(x, y, r, AIR_OUTLINE_DASH, segs)
    if spotted:
        arcade.draw_circle_filled(x, y, 2, arcade.color.WHITE)
    if facing_deg is not None:                    # 机头朝向线（CAP 微操依据）
        rad = math.radians(90.0 - float(facing_deg))   # 0°=北，顺时针
        arcade.draw_line(x, y, x + (r + 5) * math.cos(rad),
                         y + (r + 5) * math.sin(rad), edge, 2)
    if selected:
        arcade.draw_lrbt_rectangle_outline(x - r - 3, x + r + 3,
                                           y - r - 3, y + r + 3,
                                           arcade.color.WHITE, 1)


def draw_objective_glyph(x: float, y: float, radius: float, *, owner):
    """占点：同心圆（外圈细灰=范围界/内盘 owner 色半透明/中心点）。

    radius 为屏幕像素半径（调用方按 cm→px 换算传入，含 min 下限防 0 不可见）。
    """
    col = owner_color(owner)
    arcade.draw_circle_outline(x, y, radius, MAP_RING_GRAY, 1)
    arcade.draw_circle_filled(x, y, max(3.0, radius * 0.55),
                              (col[0], col[1], col[2], 70))
    arcade.draw_circle_filled(x, y, 3, col)


def draw_smoke_glyph(x: float, y: float, radius: float):
    """烟区：半透明白圆（物理可见面——公开不裁剪）。"""
    arcade.draw_circle_filled(x, y, radius, SMOKE_FILL)
    arcade.draw_circle_outline(x, y, radius, (SMOKE_FILL[0], SMOKE_FILL[1],
                                              SMOKE_FILL[2], 140), 1)


def draw_projectile_glyph(x: float, y: float):
    """弹丸：小点（ke/he/smoke 同形，色统一亮黄——量小不做类型分色）。"""
    arcade.draw_point(x, y, PROJECTILE)


# ── 内部图元 ──

def _hp_bar(x: float, y: float, hp_pct: int):
    """HP 窄条（≤50% 红档/余绿档；hp_pct 夹取 0..100）。"""
    pct = max(0, min(100, int(hp_pct)))
    arcade.draw_lrbt_rectangle_filled(x - HP_BAR_W // 2, x + HP_BAR_W // 2,
                                      y, y + HP_BAR_H, (30, 30, 30, 200))
    w = int(HP_BAR_W * pct / 100)
    if w > 0:
        arcade.draw_lrbt_rectangle_filled(x - HP_BAR_W // 2,
                                          x - HP_BAR_W // 2 + w, y, y + HP_BAR_H,
                                          HP_HIGH if pct > 50 else HP_LOW)


def _slash(x, y, r, color):
    """斜杠（侦察圆内 / 防空方形对角臂）：左下→右上。"""
    arcade.draw_line(x - r * 0.7, y - r * 0.7, x + r * 0.7, y + r * 0.7, color, 2)


def _diagonal(x, y, r, color):
    """对角线（步兵/防空方形）：左上→右下。"""
    arcade.draw_line(x - r * 0.7, y + r * 0.7, x + r * 0.7, y - r * 0.7, color, 2)


def _star(x, y, r, fill, edge):
    """五角星（指挥字形——外接圆 r，程序化折线）。"""
    pts = []
    for i in range(10):
        rad = math.radians(90 + i * 36)
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((x + rr * math.cos(rad), y + rr * math.sin(rad)))
    arcade.draw_polygon_filled(pts, fill)
    arcade.draw_polygon_outline(pts, edge, 1)


def _dashed_circle(x, y, r, color, segments: int = 8):
    """虚线圆：segments 段弧交替留白（高度层圈）。"""
    step = 360 // max(2, segments)
    for i in range(0, 360, step * 2):
        arcade.draw_arc_outline(x, y, r * 2, r * 2, color,
                                i, min(i + step, 359), border_width=1)
