"""FE-05 F3 单位详细卡（断箭右下状态主卡·地面选区档）。

结论先行：地面选区有内容且空中卡未占位时，摘要行上方 12px 绘 320×236
主卡（右缘与命令格右缘对齐、顶缘钳不溢顶栏——air_panel_geom 同构）。数据
经 session.unit_detail(uid) **按需查询**（app 层胶水——本模块不 import
sovs.sim，AST 守卫②），win._detail_cache 以 (page, 选区元组, TAB 焦点)
为签名——签名变才重查（不在 on_draw 每帧重算）。行布局：标题/HP 条/
装甲 KE·HE/视野 地·空(m)/速度档·隐蔽/武器表（超 4 行尾部「+N」）/状态行。
与空中卡互斥：空中选区（含在空列表态）优先——selection_panel 接线面裁决。
"""
from __future__ import annotations

import arcade

from .hud_top import fit_text
from .palette import (HP_HIGH, HP_LOW, HUD_TEXT, MARGIN, ORDER_ARMED,
                      ORDER_TEXT, SEL_PANEL_BG, TOP_H)
from .shell_fsm import STATE_CN

CARD_W, CARD_H = 340, 236          # 主卡量尺（R1：320→340——末列 282+弹种宽
                                   # ~40 超 312 被裁；340 下 282+40=322≤332）
_GAP = 12                          # 与摘要行的缝（与集群节拍一致）
_MAX_WEAPON_ROWS = 4               # 武器表行上限（超出尾部「+N」）

# 武器表五列锚（卡内偏移——名称｜弹药｜射程｜穿深｜弹种）
# 〔R2：末列 282→272——末列 span 50 时 "SMOKE" fit 到 46px 仍截成 SMO...；
#   span 60（fit 56px）下 10 号字 "SMOKE" 全文容纳。〕
_COL = (8, 128, 186, 240, 272)
_COL_RIGHT_PAD = 8                 # 末列右界内边距（CARD_W-8=332）


def col_spans() -> list:
    """武器表各列可用宽（相邻锚差与 CARD_W-8 边界——R1 列宽断言的量尺源）。"""
    anchors = list(_COL) + [CARD_W - _COL_RIGHT_PAD]
    return [b - a for a, b in zip(anchors, anchors[1:])]


def hp_bar_rect():
    """HP 血条带（自卡顶 y1 向下的偏移矩形 (x_l, off_b, x_r, off_t)——纯几何，
    测试断言「与 HP 文本带零重叠」的量尺源）。"""
    return (8, 36, CARD_W - 8, 42)


def hp_text_rect():
    """HP 数字文本带（10px 右锚——R1 自 y1-46 上移 y1-56，与血条零重叠）。"""
    return (CARD_W // 2, 46, CARD_W - 8, 56)


def unit_card_geom(win):
    """主卡矩形 (x0,y0,x1,y1)：右缘=命令格右缘（win.width-MARGIN）、
    卡底=摘要行顶+12、320×236、顶缘钳不溢顶栏。"""
    from .selection_panel import panel_geom
    x1 = win.width - MARGIN
    x0 = x1 - CARD_W
    y0 = panel_geom(win)[3] + _GAP
    y1 = min(y0 + CARD_H, win.height - TOP_H - 8)
    return x0, y0, x1, max(y0, y1)


def unit_card_active(win) -> bool:
    """地面选区详细卡是否绘（battle 页＋有地面选区＋空中卡不占位——互斥）。"""
    if getattr(win.fsm, "page", None) != "battle" or not win.fsm.selected:
        return False
    from .selection_panel import _air_card_rows
    return not _air_card_rows(win)[0]


def _detail_cached(win) -> dict | None:
    """win._detail_cache 按需刷新（签名=页面/选区/焦点——变才重查 session）。"""
    fsm = win.fsm
    sig = (fsm.page, tuple(fsm.selected), fsm.focus_unit)
    cache = getattr(win, "_detail_cache", None)
    if cache is not None and cache.get("sig") == sig:
        return cache.get("data")
    uid = fsm.focus_unit if fsm.focus_unit is not None \
        else (fsm.selected[0] if fsm.selected else None)
    data = None
    if uid is not None and hasattr(win.session, "unit_detail"):
        try:
            data = win.session.unit_detail(uid)
        except Exception:                              # noqa: BLE001（鸭子面）
            data = None
    win._detail_cache = {"sig": sig, "data": data}
    return data


def _cn(word) -> str:
    return STATE_CN.get(word, word)


def _weapon_rows(data: dict) -> list[tuple]:
    """武器表行 (名称, 弹药, 射程m, 穿深, 弹种)——全元素武器平铺。"""
    rows = []
    for el in data.get("elements", ()):
        for w in el.get("weapons", ()):
            pen = "-" if not w["pen_min"] and not w["pen_max"] else (
                str(w["pen_min"]) if w["pen_min"] == w["pen_max"]
                else "%d~%d" % (w["pen_min"], w["pen_max"]))
            rows.append((w["name"], "%d/%d" % (w["ammo_left"], w["ammo_base"]),
                         "%d" % (w["max_range_cm"] // 100), pen,
                         str(w["damage_type"]).upper()))
    return rows


def draw_unit_card(win) -> None:
    """地面选区状态主卡（selection_panel 在空中卡不占位时调用）。"""
    data = _detail_cached(win)
    if data is None:
        return
    x0, y0, x1, y1 = unit_card_geom(win)
    if y1 - y0 < 100:                   # 顶缘钳退化（零/负高）不绘
        return
    arcade.draw_lrbt_rectangle_filled(x0, x1, y0, y1, SEL_PANEL_BG)
    arcade.draw_lrbt_rectangle_outline(x0, x1, y0, y1, ORDER_TEXT, 1)
    # ── 标题 ──
    arcade.draw_text(fit_text(data["name"], CARD_W - 60, 13), x0 + 8,
                     y1 - 22, HUD_TEXT, 13)
    arcade.draw_text("%d" % data["team"], x1 - 24, y1 - 22, ORDER_ARMED, 12)
    # ── HP 条 ──（R1：文本带 y1-56..46 与血条带 y1-42..36 零重叠）
    hp, hp_max = data["hp"], max(1, data["hp_max"])
    pct = max(0, min(100, hp * 100 // hp_max))
    bw = CARD_W - 16
    arcade.draw_lrbt_rectangle_filled(x0 + 8, x0 + 8 + bw, y1 - 42, y1 - 36,
                                      (30, 30, 30, 200))
    if pct > 0:
        arcade.draw_lrbt_rectangle_filled(
            x0 + 8, x0 + 8 + int(bw * pct / 100), y1 - 42, y1 - 36,
            HP_HIGH if pct > 50 else HP_LOW)
    arcade.draw_text("%d/%d" % (hp, data["hp_max"]), x1 - 8, y1 - 56,
                     HUD_TEXT, 10, anchor_x="right")
    # ── 三行属性 ──
    ak = data.get("armor_ke")
    ah = data.get("armor_he")
    armor = "装甲 KE %s·HE %s" % ("-" if ak is None else ak,
                                  "-" if ah is None else ah)
    optics = "视野 地 %dm·空 %dm" % (data.get("optics_ground_cm", 0) // 100,
                                     data.get("optics_air_cm", 0) // 100)
    speed = "速度档 %s·隐蔽 %s" % (data.get("speed_tier", 1),
                                  data.get("stealth_base", 0))
    for i, line in enumerate((armor, optics, speed)):
        arcade.draw_text(line, x0 + 8, y1 - 64 - i * 16, HUD_TEXT, 11)
    # ── 武器表 ──（R1：逐列 fit 到列距-4——任何单元格不越列界/卡缘）
    spans = col_spans()
    ty = y1 - 118
    for label, cx, span in zip(("武器", "弹药", "射程m", "穿深", "弹种"),
                               _COL, spans):
        arcade.draw_text(fit_text(label, span - 4, 11),
                         x0 + cx, ty, ORDER_ARMED, 11)
    rows = _weapon_rows(data)
    for i, (name, ammo, rng, pen, dtype) in enumerate(rows[:_MAX_WEAPON_ROWS]):
        yy = ty - 16 - i * 14
        for j, cell in enumerate((name, ammo, rng, pen, dtype)):
            arcade.draw_text(fit_text(str(cell), spans[j] - 4, 10),
                             x0 + _COL[j], yy, HUD_TEXT, 10)
    if len(rows) > _MAX_WEAPON_ROWS:             # 超 4 行尾部「+N」
        arcade.draw_text("+%d" % (len(rows) - _MAX_WEAPON_ROWS),
                         x0 + _COL[4], ty - 16 - _MAX_WEAPON_ROWS * 14,
                         ORDER_ARMED, 10)
    # ── 状态行 ──（R1：fit 收进卡宽——不溢右缘）
    arcade.draw_text(fit_text("士气 %s｜姿态 %s｜模式 %s"
                             % (_cn(data.get("morale", "?")),
                                _cn(data.get("stance", "?")),
                                _cn(data.get("mode", "?"))),
                             CARD_W - 16, 10),
                     x0 + 8, y0 + 6, HUD_TEXT, 10)
