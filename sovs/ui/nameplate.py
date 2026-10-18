"""FE-05 F2 断箭铭牌：单位下方的下尖五边形铭牌（几何纯函数 + 绘制面）。

结论先行：nameplate_geom 为**纯几何函数**（px,py,zoom,state → {poly/
hp_rect/count_pos/badges}——无 arcade 依赖，测试直断言）；draw_nameplate
消费几何做绘制。规格（BA 复刻工单 F2）：铭牌 44×12 挂单位底缘+6px、下尖
五边形、半透明黑底+1px 队色描边；血条 40×3（>50% HP_HIGH/≤50% HP_LOW）；
人数=hp/hp_max（1HP=1 人「30/30」；R3 1-1：仅步兵 category==1 挂数字，
载具/火炮/防空/侦察车只留血条；缺 category 按步兵）9px 居中下缘；
状态角标≤4（压制>禁火>雷达>RTB>驻守>
牵引），3×3 色块+字母挂铭牌右上外缘；选中=描边换 SELECT_MARK＋
铭牌上方 3px 小三角。缺字段按 False/空处理不抛（鸭子帧兼容）。

缩放分档（R2 2026-10-17 拍板翻新——原 F2 档 0.06/0.12 高出默认视角
10~20 倍，默认 fit_scale≈0.006（视口 ~1260px/地图 200000cm）下铭牌
整体不显示，截图只有血条）：
  zoom >= 0.0040：五边形铭牌＋血条（默认 0.006 命中；min_scale≈
                  fit×0.8≈0.0048 下界仍见铭牌）；
  zoom >= 0.0050：人数与状态角标（默认 0.006 命中）；
  zoom <  0.0040：只画血条。
本模块只 import arcade＋本包 palette（禁 sovs.sim/sovs.ai——AST 守卫②）。
"""
from __future__ import annotations

import arcade

from .glyphs import team_color
from .palette import (BADGE_GARRISON, BADGE_HOLD_FIRE, BADGE_RADAR,
                      BADGE_RTB, BADGE_TOW, HP_HIGH, HP_LOW, HUD_TEXT,
                      NAMEPLATE_BG, SELECT_MARK, SUPPRESS_MARK)

PLATE_W, PLATE_H = 44, 12          # 铭牌量尺（px）
HP_W, HP_H = 40, 3                 # 铭牌内血条量尺（px）
HALF_UNIT = 24                     # 单位半边（48px 贴图口径——铭牌挂点）
PLATE_GAP = 6                      # 单位底缘→铭牌上缘缝（px）
BADGE_MAX = 4                      # 状态角标上限（超出按优先级截断）
BADGE_PITCH = 10                   # 角标横向节距（px——3px 色块+字母）

# R2 缩放分档（头注：与默认相机量尺对齐——fit≈0.006 / min≈0.0048）
ZOOM_PLATE_MIN = 0.0040            # ≥此值画五边形铭牌（否则只血条）
ZOOM_DETAIL_MIN = 0.0050           # ≥此值画人数与角标

# 角标定义（优先序 = 元组序）：(字母, 色, 判据键)——压>禁>雷>RTB>驻>牵
_BADGE_DEFS = (
    ("压", SUPPRESS_MARK, lambda s: bool(s.get("suppressed"))),
    ("禁", BADGE_HOLD_FIRE, lambda s: s.get("stance") == "hold_fire"),
    ("雷", BADGE_RADAR, lambda s: bool(s.get("radar_on"))),
    ("R", BADGE_RTB, lambda s: bool(s.get("rtb"))),
    ("驻", BADGE_GARRISON, lambda s: bool(s.get("garrisoned"))),
    ("牵", BADGE_TOW, lambda s: bool(s.get("towed"))),
)


def nameplate_geom(px: float, py: float, zoom: float, state) -> dict:
    """铭牌几何（纯函数——无 arcade 依赖；state 缺字段按 False/空处理）。

    返回 {poly: 5点列表|None, hp_rect: (x0,y0,x1,y1)|None,
          count_pos: (x,y)|None, badges: [(字母,色,x,y), ...]}；
    R2 分档：zoom<0.0040 → 只血条；0.0040≤zoom<0.0050 → 铭牌+血条（无人
    数/角标）；≥0.0050 → 全量（默认 fit_scale≈0.006 全量命中）。
    """
    s = state or {}
    zoom = float(zoom)
    cx = float(px)
    y_top = float(py) - HALF_UNIT - PLATE_GAP          # 铭牌上缘
    y_tip = y_top - PLATE_H                            # 下尖底点
    x0, x1 = cx - PLATE_W / 2, cx + PLATE_W / 2
    hp_rect = (cx - HP_W / 2, y_top - 2 - HP_H, cx + HP_W / 2, y_top - 2)
    if zoom < ZOOM_PLATE_MIN:
        return {"poly": None, "hp_rect": hp_rect, "count_pos": None,
                "badges": []}
    poly = [(x0, y_top), (x1, y_top), (x1, y_tip + 4),
            (cx, y_tip), (x0, y_tip + 4)]              # 下尖五边形
    count_pos = None
    if zoom >= ZOOM_DETAIL_MIN and int(s.get("category", 1)) == 1:
        # R3 1-1：人数只挂步兵（category==1——载具/火炮/防空/侦察车铭牌只
        # 留血条无数字）；缺 category 按步兵（既有测试兼容口径）。
        count_pos = (cx, y_tip + 1.5)
    badges = []
    if zoom >= ZOOM_DETAIL_MIN:
        for i, (letter, color, pred) in enumerate(_BADGE_DEFS):
            if len(badges) >= BADGE_MAX:
                break                                  # 优先级截断
            if pred(s):
                badges.append((letter, color, x1 + 2 + i * BADGE_PITCH,
                              y_top - 2))
    return {"poly": poly, "hp_rect": hp_rect, "count_pos": count_pos,
            "badges": badges}


def draw_nameplate(px: float, py: float, zoom: float, state) -> None:
    """铭牌绘制（draw_ground_unit 末尾调用——texture/字形两路同锚）。"""
    s = state or {}
    g = nameplate_geom(px, py, zoom, s)
    hp = int(s.get("hp", 0))
    hp_max = int(s.get("hp_max", 0))
    pct = (hp * 100 // hp_max) if hp_max > 0 else 0
    if g["poly"] is not None:
        selected = bool(s.get("selected"))
        arcade.draw_polygon_filled(g["poly"], NAMEPLATE_BG)
        edge = SELECT_MARK if selected else team_color(s.get("team", -1))
        arcade.draw_polygon_outline(g["poly"], edge, 1)
        if selected:                                   # 上方 3px 小三角
            cx = float(px)
            y_top = g["poly"][0][1]
            arcade.draw_triangle_filled(cx - 4, y_top + 2, cx + 4, y_top + 2,
                                        cx, y_top + 5, SELECT_MARK)
    x0, y0, x1, _y1 = g["hp_rect"]
    arcade.draw_lrbt_rectangle_filled(x0, x1, y0, y0 + HP_H, (30, 30, 30, 190))
    w = int(HP_W * max(0, min(100, pct)) / 100)
    if w > 0:
        arcade.draw_lrbt_rectangle_filled(
            x0, x0 + w, y0, y0 + HP_H,
            HP_HIGH if pct > 50 else HP_LOW)
    if g["count_pos"] is not None:
        # R3 1-1：人数文本=hp/hp_max（1HP=1 人——「30/30」现役/满编）；
        # 9 号字 ASCII ~5px/字，"120/120"≈30px ≤ 铭牌 44px 不截。
        arcade.draw_text("%d/%d" % (hp, int(s.get("hp_max", 0))),
                         g["count_pos"][0], g["count_pos"][1],
                         HUD_TEXT, 9, anchor_x="center")
    for letter, color, bx, by in g["badges"]:
        arcade.draw_lrbt_rectangle_filled(bx, bx + 3, by - 3, by, color)
        arcade.draw_text(letter, bx + 4, by - 4, color, 9)
