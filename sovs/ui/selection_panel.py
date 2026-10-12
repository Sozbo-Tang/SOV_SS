"""右侧选中面板＋单位/飞机浮层（GP-01 §5.2 拆分自 shell_window＋§5.4 常驻重排）。

结论先行：右侧**选中面板常驻**（单位/飞机共槽，TAB 焦点联动——修「选中信息
与命令入口分离」的布局不合理主诉）；空选区时列在空飞机（名/状态/高度/弹舱/
任务/对空开关/血量，点击即选中——§4 ④段「呼入后全程可微操」的面板面）。
本模块只 import arcade＋本包常量/词面（不 import sovs.sim——AST 守卫②）。
"""
from __future__ import annotations

import arcade

from .hud_bottom import Btn  # noqa: E402（按钮原语共享——绘制与命中一处口径）
from .hud_top import text_width
from .palette import (AIR_FOCUS_MARK, CATEGORY_COLORS,  # noqa: E402
                      HUD_TEXT, INFO_PANEL, MARGIN, MINIMAP_H,
                      ORDER_TEXT, SEL_PANEL_BG, SEL_PANEL_W, SELECT_MARK,
                      TEAM_NAMES, TOP_H)
from .scene import air_state_label

_MAX_ROWS = 13                  # 面板行上限（超出截断——不滚动，密度换可读）


def fit_text(text: str, max_px: float, size: float) -> str:
    """截宽到 max_px（超出以「…」收尾——实测宽逐字符退）。

    battle.png 复检③修复：机型名+状态行（如「Il-2M攻击机 盘旋·盘旋待命·中空」
    实测 ~190px）超面板内宽（SEL_PANEL_W-16-10≈166px）溢出到屏缘被裁——一切
    面板行文字经此收口，超宽显式「…」而非无声截断。"""
    if text_width(text, size) <= max_px:
        return text
    while text and text_width(text + "…", size) > max_px:
        text = text[:-1]
    return text + "…"


def panel_geom(win):
    """面板矩形 (x0, y0, x1, y1)：§11 断箭位——左侧选中卡（呼援轨之下、小地图
    之上）；离左缘 26px 内缩给边缘滚动热区让位（RTS 贴边平移不被面板吞）。"""
    x0 = MARGIN + 26
    x1 = x0 + SEL_PANEL_W
    y0 = MARGIN + MINIMAP_H + 8
    y1 = win.height - TOP_H - 150
    return x0, y0, x1, y1


def layout_selection_panel(win) -> None:
    """选中面板命中域：单位图标（sel:）/飞机行（airsel:——空选区时列在空机）。"""
    _x0, y0, _x1, _y1 = panel_geom(win)
    fsm = win.fsm
    y = y0 + 64
    for uid in fsm.selected[:_MAX_ROWS]:
        win._buttons.append(Btn(_x0 + 8, y, SEL_PANEL_W - 16, 22,
                                "sel:%d" % uid, ""))
        y -= 24
    if not fsm.selected and not fsm.selected_air:
        own_air = [a for a in win.frame.get("aircraft", ())
                   if a.get("team") == win.frame.get("view")]
        for a in own_air[:_MAX_ROWS]:            # 在空面板（§4 ④段——点击即选中）
            win._buttons.append(Btn(_x0 + 8, y, SEL_PANEL_W - 16, 26,
                                    "airsel:%d" % a["id"], ""))
            y -= 28
    for aid in fsm.selected_air[:_MAX_ROWS]:
        win._buttons.append(Btn(_x0 + 8, y, SEL_PANEL_W - 16, 26,
                                "airsel:%d" % aid, ""))
        y -= 28


def draw_selection_panel(win) -> None:
    """右侧常驻面板绘制：标题/单位图标行/飞机行（状态·任务·高度·弹舱·血量）。"""
    x0, y0, x1, y1 = panel_geom(win)
    if y1 - y0 < 90:
        return
    fsm = win.fsm
    arcade.draw_lrbt_rectangle_filled(x0, x1, y0, y1, SEL_PANEL_BG)
    arcade.draw_lrbt_rectangle_outline(x0, x1, y0, y1, ORDER_TEXT, 1)
    title = ("选中 %d 单位%s" % (len(fsm.selected),
                                "＋%d 机" % len(fsm.selected_air)
                                if fsm.selected_air else "")
             if (fsm.selected or fsm.selected_air) else "在空飞机（点击选中）")
    arcade.draw_text(title, x0 + 8, y1 - 22, HUD_TEXT, 12)
    frame = win.frame
    entry_by_id = {u["id"]: u for u in frame.get("units", ())}
    air_by_id = {a["id"]: a for a in frame.get("aircraft", ())}
    focus = fsm.focus_unit
    focus_air = fsm.focus_aircraft
    for btn in win._buttons:
        if btn.key.startswith("sel:"):
            uid = int(btn.key[4:])
            entry = entry_by_id.get(uid)
            col = CATEGORY_COLORS.get(entry.get("category", 1) if entry else 1,
                                      (160, 160, 160, 255))
            arcade.draw_lrbt_rectangle_filled(btn.x0, btn.x1, btn.yb, btn.yt, col)
            if entry is not None:
                arcade.draw_text(
                    fit_text("%d %s" % (uid % 100, entry.get("name", "")),
                             btn.x1 - btn.x0 - 8, 11),
                    btn.x0 + 4, btn.yb + 4, ORDER_TEXT, 11)
            if uid == focus:                    # TAB 子选高亮（白框）
                arcade.draw_lrbt_rectangle_outline(btn.x0 - 2, btn.x1 + 2,
                                                   btn.yb - 2, btn.yt + 2,
                                                   SELECT_MARK, 2)
        elif btn.key.startswith("airsel:"):
            aid = int(btn.key[7:])
            a = air_by_id.get(aid)
            if a is None:
                continue
            ammo = " ".join("%s%d" % (k, v) for k, v in
                            sorted((a.get("ammo") or {}).items()) if v > 0)
            engage = ("" if a.get("engage_air") is None
                      else ("对空开" if a["engage_air"] else "对空关"))
            hp_pct = (a["hp"] * 100 // a["hp_max"]) if a["hp_max"] else 0
            # 行宽收口（复检③）：状态行拆两行——L1 机型名+飞行状态，L2 任务·高度
            # +血量+弹舱+对空开关；超内宽以「…」显式截断（不再溢出面板/屏缘）
            w = btn.x1 - btn.x0 - 10
            state_parts = air_state_label(a).split("·")
            line1 = fit_text("%s %s" % (a["name"], state_parts[0]), w, 11)
            line2 = fit_text("%s HP%d%% %s %s" % ("·".join(state_parts[1:]),
                                                  hp_pct, ammo or "无弹",
                                                  engage), w, 10)
            arcade.draw_text(line1, btn.x0 + 6, btn.yb + 12, HUD_TEXT, 11)
            arcade.draw_text(line2, btn.x0 + 6, btn.yb + 1,
                             ORDER_TEXT if hp_pct > 40
                             else (235, 100, 100, 255), 10)
            if aid == focus_air:                 # TAB 子选高亮（黄粗框）
                arcade.draw_lrbt_rectangle_outline(btn.x0 - 2, btn.x1 + 2,
                                                   btn.yb - 2, btn.yt + 2,
                                                   AIR_FOCUS_MARK, 2)
            elif aid in fsm.selected_air:
                arcade.draw_lrbt_rectangle_outline(btn.x0, btn.x1, btn.yb,
                                                   btn.yt, AIR_FOCUS_MARK, 1)


def draw_unit_info(win, entry: dict) -> None:
    """点击单位浮层：血量/弹药/士气（帧条目——迷雾外敌单位无条目即无浮层）。
    §11 断箭位：选中卡右侧浮出（左缘已被呼援轨占用）。"""
    w, h = 330, 168
    x0 = MARGIN + 26 + SEL_PANEL_W + 12
    y0 = win.height - TOP_H - h - 8
    arcade.draw_lrbt_rectangle_filled(x0, x0 + w, y0, y0 + h, INFO_PANEL)
    arcade.draw_lrbt_rectangle_outline(x0, x0 + w, y0, y0 + h, ORDER_TEXT, 1)
    morale_cn = {"stable": "稳定", "suppressed": "受压", "pinned": "钉住",
                 "routed": "溃逃"}
    stance_cn = {"weapons_free": "自由射击", "hold_fire": "禁火"}
    ammo = ("弹药 —" if entry["ammo_pct"] < 0
            else "弹药 %d%%" % entry["ammo_pct"])
    rows = [
        "#%d %s（%s）" % (entry["id"], entry["name"],
                          TEAM_NAMES.get(entry["team"], "?")),
        "血量 %d/%d" % (entry["hp"], entry["hp_max"]),
        ammo,
        "士气 %s" % morale_cn.get(entry["morale"], entry["morale"]),
        "姿态 %s｜模式 %s" % (stance_cn.get(entry["stance"], entry["stance"]),
                              entry["mode"]),
        "机动 %s｜烟幕余 %d" % ("是" if entry["moving"] else "否",
                               entry["smoke_left"]),
    ]
    for i, line in enumerate(rows):
        arcade.draw_text(line, x0 + 12, y0 + h - 26 - i * 22, HUD_TEXT, 12)
