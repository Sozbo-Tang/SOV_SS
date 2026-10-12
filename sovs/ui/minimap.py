"""小地图绘制（GP-01 §5.2 拆分自 shell_window＋§4 飞机图元增强）：纯呈现。

左键=跳转相机中心；右键=对选中单位下令（地面=移动/空选区=盘旋——GP-01 §4
右键语义在小地图的同构）。含飞机图元（黄点＋高度圈示意）。
"""
from __future__ import annotations

import arcade

from .palette import (MAP_BORDER, MARGIN, MINIMAP_BG,  # noqa: E402
                      MINIMAP_VIEW, MINIMAP_W, MINIMAP_H, TEAM_COLORS)

_UNOWNED = (150, 150, 150, 255)
_AIR_DOT = (240, 240, 160, 255)


def minimap_geom(win):
    """断箭位（实机参照 ba_shot4）：小地图居左下角，编组列在其右侧。"""
    x0 = MARGIN
    y0 = MARGIN
    return x0, y0, x0 + MINIMAP_W, y0 + MINIMAP_H


def minimap_to_cm(win, x: float, y: float):
    """小地图命中点 → 地图 cm（比例映射；未命中返回 None）。"""
    x0, y0, x1, y1 = minimap_geom(win)
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return None
    mw, mh = win.frame.get("map_cm", (200000, 100000))
    return (float(int((x - x0) / (x1 - x0) * mw)),
            float(int((y - y0) / (y1 - y0) * mh)))


def draw_minimap(win) -> None:
    """常驻小地图：整体战场+视口框；左键跳转/右键下令（见 shell_window 点击面）。"""
    x0, y0, x1, y1 = minimap_geom(win)
    mw, mh = win.frame.get("map_cm", (200000, 100000))
    arcade.draw_lrbt_rectangle_filled(x0, x1, y0, y1, MINIMAP_BG)
    arcade.draw_lrbt_rectangle_outline(x0, x1, y0, y1, MAP_BORDER, 1)

    def mm(pos_cm):
        return (x0 + pos_cm[0] / mw * (x1 - x0),
                y0 + pos_cm[1] / mh * (y1 - y0))

    for o in win.frame.get("objectives", ()):
        mx, my = mm(o["pos_cm"])
        arcade.draw_circle_filled(mx, my, 3,
                                  TEAM_COLORS.get(o["owner"], _UNOWNED))
    for u in win.frame.get("units", ()):
        mx, my = mm(u["pos_cm"])
        arcade.draw_point(mx, my, TEAM_COLORS.get(u["team"], _UNOWNED))
    for a in win.frame.get("aircraft", ()):
        mx, my = mm(a["pos_cm"])
        arcade.draw_point(mx, my, _AIR_DOT)
        arcade.draw_circle_outline(mx, my, 3,
                                   TEAM_COLORS.get(a["team"], _UNOWNED), 1)
    cl, cb, cr, ct = win._visible_cm_rect()
    vx0, vy0 = mm((max(0, cl), max(0, cb)))
    vx1, vy1 = mm((min(mw, cr), min(mh, ct)))
    arcade.draw_lrbt_rectangle_outline(vx0, vx1, vy0, vy1, MINIMAP_VIEW, 1)
