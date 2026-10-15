"""选中面板＋飞机信息（GP-01 §5.2 拆分自 shell_window＋§5.4 常驻重排）。

结论先行（BA 布局复刻轮 2026-10-15，参照 out/refs/ba_shot4.jpg＋调研报告
02 §1/§3/§4）：选中反馈三件套全部在**右下集群**（官方指南七组件表 5/6/7
——选择面板/状态面板/行动面板），底中无任何面板——
　命令格（行动面板）＝右下角（hud_bottom）；
　多选摘要行（选择面板）＝命令格正上方 12px、右对齐（panel_geom）；
　状态面板主卡（空中三态）＝摘要行上方 12px（air_panel_geom）。
本模块只 import arcade＋本包常量/词面（不 import sovs.sim——AST 守卫②）。
"""
from __future__ import annotations

import arcade

from .hud_bottom import Btn  # noqa: E402（按钮原语共享——绘制与命中一处口径）
from .hud_top import fit_text  # noqa: E402（B1 提升共享——面板行文字截宽范式）
from .palette import (AIR_FOCUS_MARK, CATEGORY_COLORS,  # noqa: E402
                      HUD_TEXT,
                      MARGIN, ORDER_ARMED, ORDER_TEXT, SEL_PANEL_BG, SEL_PANEL_W,
                      SELECT_MARK, TOP_H)
from .scene import air_state_label

STRIP_H = 64                     # 多选摘要行高（单行小卡——BA 选择面板式）
STRIP_W = 600                    # 摘要行宽（右对齐命令格右缘向左展开）


def panel_geom(win):
    """多选摘要行矩形 (x0, y0, x1, y1)——右下集群底件（BA 复刻轮 2026-10-15
    用户拍板「完全复刻断箭战斗界面布局」：**底中无面板**，选中单位小卡行
    进右下集群，贴命令格正上方 12px、与格右对齐）。几何静态（不随呼援轨
    长度/待令态跳变——qa.py B1 两两互斥剧本断言兼容）。旧底中竖卡/底中
    长条两形态废止（长条轮 §11.4 记录被本轮推翻——连续两轮翻案留痕）。"""
    from .hud_bottom import order_panel_rect
    gy1 = order_panel_rect(win)[3]
    x1 = win.width - MARGIN
    x0 = x1 - STRIP_W
    y0 = gy1 + 12
    y1 = min(y0 + STRIP_H, win.height - TOP_H - 8)
    return x0, y0, x1, max(y0, y1)   # 矮窗顶缘钳后 y1<y0 时夹回零高不绘


def air_panel_geom(win):
    """状态面板主卡矩形（右下集群顶件）：卡底=摘要行顶+12（BA 三件套垂直
    堆叠：命令格→摘要行→本卡）；顶缘钳不溢顶栏（不落回摘要行内）。"""
    sy1 = panel_geom(win)[3]           # 摘要行顶
    x1 = win.width - MARGIN
    x0 = x1 - SEL_PANEL_W
    y0 = sy1 + 12
    y1 = y0 + 236
    if y1 > win.height - TOP_H - 8:   # 顶缘钳（不溢顶栏；底不落回摘要行内）
        y1 = win.height - TOP_H - 8
        y0 = max(sy1 + 12, y1 - 236)
    return x0, y0, x1, y1


def _air_card_rows(win):
    """对战页空中卡行集（2026-10-15）：选中飞机（含混合选区的空中部分）优先；
    无任何选区=在空飞机列表（自左侧面板迁右下——断箭单位卡同位）；无内容=()
    不绘卡。返回 (ids, title)。"""
    fsm = win.fsm
    if fsm.selected_air:
        return list(fsm.selected_air), \
            "空中单位 ×%d（TAB 切换焦点）" % len(fsm.selected_air)
    if not fsm.selected:
        own = [a["id"] for a in win.frame.get("aircraft", ())
               if a.get("team") == win.frame.get("view")]
        if own:
            return own, "在空飞机（点击选中）"
    return [], ""


def _air_card_active(win) -> bool:
    """对战页右下空中卡是否绘（deploy 页不绘——空中信息属对战态）。"""
    return win.fsm.page == "battle" and bool(_air_card_rows(win)[0])


def draw_air_card(win, ids=None, title=None) -> None:
    """空中信息卡（右下·命令界面上方）：机型/状态/高度/血量行＋弹舱余量×单价
    价值＋空援点数——「余弹价值」行=空袭按用计费（呼叫只付本体、弹费投放时
    逐发扣）的呈现面；空投作业费投放时另计（tables 常量不经 ui——文案面）。
    2026-10-15：无选区态=在空飞机列表（ids 自 _air_card_rows）。"""
    if ids is None or title is None:
        ids, title = _air_card_rows(win)
    x0, y0, x1, y1 = air_panel_geom(win)
    if y1 - y0 < 100:                   # 矮窗顶缘钳退化（零/负高）不绘
        return
    arcade.draw_lrbt_rectangle_filled(x0, x1, y0, y1, SEL_PANEL_BG)
    arcade.draw_lrbt_rectangle_outline(x0, x1, y0, y1, ORDER_TEXT, 1)
    sel = {a["id"]: a for a in win.frame.get("aircraft", ())}
    arcade.draw_text(title, x0 + 8, y1 - 20, HUD_TEXT, 12)
    y = y1 - 46
    for aid in ids[:5]:
        a = sel.get(aid)
        if a is None:
            continue
        alt = {"low": "低空", "mid": "中空", "high": "高空"}.get(
            a.get("alt_tier"), "")
        line = fit_text("%s %s %s %d%%" % (a["name"], air_state_label(a),
                                           alt, a["hp"] * 100
                                           // max(1, a["hp_max"])),
                        SEL_PANEL_W - 16, 12)
        arcade.draw_text(line, x0 + 8, y, HUD_TEXT, 12)
        if aid == win.fsm.focus_aircraft:  # TAB 子选焦点行（黄框——左卡迁移保留）
            arcade.draw_lrbt_rectangle_outline(x0 + 8, x1 - 8, y - 2, y + 22,
                                               AIR_FOCUS_MARK, 2)
        y -= 24
    bombs = sum(sel[i].get("ammo", {}).get("BOMB", 0)
                for i in ids if i in sel)
    first = next((sel[i] for i in ids if i in sel), None)
    price = win.session.air_bomb_price(first["template_id"]) if first else 0
    arcade.draw_text("弹舱 %d 枚×%d 分＝%d 分（投放时扣）"
                     % (bombs, price, bombs * price), x0 + 8, y0 + 34,
                     ORDER_ARMED, 12)
    from .hud_bottom import my_air_points
    arcade.draw_text("空援点数 %d" % my_air_points(win), x0 + 8, y0 + 18,
                     HUD_TEXT, 12)
    arcade.draw_text("空投作业费投放时另计", x0 + 8, y0 + 4,
                     (150, 150, 150, 255), 10)


def _chip_cap(strip_w: float) -> int:
    """摘要行小卡容量：标题区 96px 后单行 96px 卡＋6px 缝（≥0 钳）。"""
    return max(0, int((strip_w - 96 - 8) // 102))


def layout_selection_panel(win) -> None:
    """选中面板命中域：地面单位小卡（sel:）在右下摘要行内**单行横排**
    （BA 复刻轮——命令格正上方、右对齐，超出容量截断）；空中行（airsel:）
    一律在右下状态面板主卡（三态统一：无选区在空列表/纯空中/混合选区空中
    部分同位——纯空中或无地面选区时摘要行不布局）。"""
    fsm = win.fsm
    if win.fsm.page == "battle":
        ids, _title = _air_card_rows(win)
        if ids:
            _ax0, _ay0, _ax1, ay1 = air_panel_geom(win)
            y = ay1 - 46
            for aid in ids[:5]:
                win._buttons.append(Btn(_ax0 + 8, y, SEL_PANEL_W - 16, 24,
                                        "airsel:%d" % aid, ""))
                y -= 26
            if not fsm.selected:          # 纯空中/无选区——摘要行无内容不布局
                return
    x0, y0, x1, _y1 = panel_geom(win)
    cy = y0 + (STRIP_H - 40) // 2         # 小卡 40 高，行内垂直居中
    cx = x0 + 96
    for uid in fsm.selected[:_chip_cap(x1 - x0)]:
        win._buttons.append(Btn(cx, cy, 96, 40, "sel:%d" % uid, ""))
        cx += 102


def draw_selection_panel(win) -> None:
    """右下集群两件：摘要行（地面选中单位小卡单行横排，超容量尾部「＋N」
    截断——BA 选择面板）＋状态面板主卡（空中三态，行文由 draw_air_card
    承载）。无地面选区时摘要行不绘（BA：无选区=无卡行）。"""
    fsm = win.fsm
    if win.fsm.page == "battle":
        ids, title = _air_card_rows(win)
        if ids:
            draw_air_card(win, ids, title)
            if not fsm.selected:
                return
    if not fsm.selected:
        return                # 无地面选区：摘要行不绘（空中信息在主卡或无内容）
    x0, y0, x1, y1 = panel_geom(win)
    if y1 - y0 < 44:
        return
    arcade.draw_lrbt_rectangle_filled(x0, x1, y0, y1, SEL_PANEL_BG)
    arcade.draw_lrbt_rectangle_outline(x0, x1, y0, y1, ORDER_TEXT, 1)
    arcade.draw_text("选中 %d" % len(fsm.selected), x0 + 10, y0 + 26,
                     HUD_TEXT, 12)
    frame = win.frame
    entry_by_id = {u["id"]: u for u in frame.get("units", ())}
    focus = fsm.focus_unit
    chips = [b for b in win._buttons if b.key.startswith("sel:")]
    for btn in chips:
        uid = int(btn.key[4:])
        entry = entry_by_id.get(uid)
        col = CATEGORY_COLORS.get(entry.get("category", 1) if entry else 1,
                                  (160, 160, 160, 255))
        arcade.draw_lrbt_rectangle_filled(btn.x0, btn.x1, btn.yb, btn.yt, col)
        if entry is not None:
            arcade.draw_text(
                fit_text("%d %s" % (uid % 100, entry.get("name", "")),
                         btn.x1 - btn.x0 - 8, 11),
                btn.x0 + 4, btn.yb + 13, ORDER_TEXT, 11)
        if uid == focus:                    # TAB 子选高亮（白框）
            arcade.draw_lrbt_rectangle_outline(btn.x0 - 2, btn.x1 + 2,
                                               btn.yb - 2, btn.yt + 2,
                                               SELECT_MARK, 2)
    rest = len(fsm.selected) - len(chips)
    if rest > 0:                            # 超容量截断：尾部「＋N」
        tail_x = chips[-1].x1 + 10 if chips else x1 - 60
        arcade.draw_text("＋%d" % rest, tail_x, y0 + 26, HUD_TEXT, 12)
