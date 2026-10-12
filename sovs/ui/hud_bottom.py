"""命令格/呼援轨/编组列绘制（§11 断箭式重排，原 GP-01 §5.2/§5.4 底栏模块）。

结论先行：四行底栏带已拆除——改**断箭式布局**（实机参照 out/refs/ba_shot4.jpg
＋手册 P18「命令菜单位于屏幕右下」）：① 命令=右下浮动命令格（随选区上下文，
航空行置顶）；② 空援卡=左缘竖轨（断箭 REC/INF/VES…呼援轨同位）；③ 编组列=
小地图右侧竖排 1..9；④ 部署页左栏卡槽不变（断箭部署同为左栏轨）。热键镜像
原则不变：按钮与键盘同走 fsm.key，同门同令。本模块同时是 Btn 按钮原型的宿主
（fm_panel/selection_panel/deck_editor_page 复用——跨呈现件共享的唯一 UI 原语）。
"""
from __future__ import annotations

import arcade

from .palette import (BOTTOM_H, BTN_FONT, GROUP_DEAD, GROUP_SLOT, HUD_TEXT,  # noqa: E402
                      MARGIN, MINIMAP_W, ORDER_ARMED, ORDER_GRID_BTN_H,
                      ORDER_GRID_BTN_W, ORDER_GRID_COLS, ORDER_PANEL,
                      ORDER_TEXT, RAIL_W, TOP_H)

# 底栏按钮 → fsm 键位语义（热键一一镜像：按钮=按键同门同令；GP-01 §4/§6 扩容）
PANEL_KEY_MIRROR = {"stop": "S", "cancel": "E", "reverse": "R", "sprint": "Z",
                    "smoke_x": "X", "stance_h": "H", "attack": "A", "fm": "T",
                    "strike": "K", "drop": "O", "march": "F", "unload": "U",
                    "sniper": "N", "air_alt": "V", "air_rtb": "B",
                    "air_engage": "J", "air_disengage": "Y"}

# 待令组按钮 → fsm 待令组（armed 高亮映射；移动族右键直达无按钮）
ARM_KEYMAP = {"reverse": "reverse", "attack": "attack", "fm": "fire_mission",
              "strike": "strike", "drop": "drop", "march": "march",
              "unload": "unload", "sniper": "sniper", "supply": "supply"}

LANE_NAMES = ("西翼", "中央", "东翼")

# 战斗页右下命令格（§11：行序=航空上下文（置顶）/作战/机动/支援/杂项——短标签
# 对齐断箭图标菜单密度；热键字母随标签保留，帮助面板 F1 仍载全文）
_ORDER_ROW_AIR = (("air_alt", "高度(V)"), ("air_rtb", "返航(B)"),
                  ("air_engage", "对空(J)"), ("air_disengage", "脱离(Y)"))
_ORDER_ROW_COMBAT = (("attack", "攻击(A)"), ("fm", "炮击(T)"), ("strike", "空袭(K)"),
                     ("drop", "空投(O)"), ("smoke_x", "烟幕(X)"))
_ORDER_ROW_MANEUVER = (("stop", "停止(S)"), ("cancel", "取消(E)"),
                       ("reverse", "倒车(R)"), ("sprint", "冲刺(Z)"),
                       ("march", "行军(F)"))
_ORDER_ROW_SUPPORT = (("stance_h", "纪律(H)"), ("smoke_sprint", "烟冲(G)"),
                      ("unload", "卸载(U)"), ("sniper", "狙击(N)"), ("supply", "补给"))
_ORDER_ROW_AUX = (("ambush", "伏击"), ("deploy_gun", "展开"), ("pack_gun", "收炮"),
                  ("tow", "拖曳"), ("untow", "解拖"), ("formation", "队形"),
                  ("fm_cancel", "撤炮"))


class Btn:
    """命令面板按钮（矩形命中域 + 键 + 标签；绘制与命中一处口径）。"""

    __slots__ = ("x0", "yb", "x1", "yt", "key", "label", "tone")

    def __init__(self, x: float, y_bottom: float, w: float, h: float,
                 key: str, label: str, tone: str = "normal"):
        self.x0, self.x1 = x, x + w
        self.yb, self.yt = y_bottom, y_bottom + h
        self.key, self.label, self.tone = key, label, tone

    def hit(self, x, y) -> bool:
        return self.x0 <= x <= self.x1 and self.yb <= y <= self.yt


def button_width(label: str) -> float:
    return 16 + 11 * len(label)


def order_grid_rect(win, rows: int):
    """右下命令格矩形 (x0,y0,x1,y1)：锚右下角（手册 P18 命令菜单位），纯算术。"""
    w = ORDER_GRID_COLS * (ORDER_GRID_BTN_W + 5) + 8
    h = rows * (ORDER_GRID_BTN_H + 6) + 8
    x1 = win.width - MARGIN
    return (x1 - w, MARGIN, x1, MARGIN + h)


def layout_battle_buttons(win) -> None:
    """右下命令格＋左缘呼援轨（§11）：格行=航空上下文（置顶）/作战/机动/支援/
    杂项；轨=空援卡竖排（断箭呼援轨同位）。"""
    rows = [r for r in (_ORDER_ROW_AIR if win.fsm.selected_air else None,
                        _ORDER_ROW_COMBAT, _ORDER_ROW_MANEUVER,
                        _ORDER_ROW_SUPPORT, _ORDER_ROW_AUX) if r]
    gx0, _gy0, _gx1, gy1 = order_grid_rect(win, len(rows))
    for ri, row in enumerate(rows):                     # 行自顶向下
        y = gy1 - 8 - ORDER_GRID_BTN_H - ri * (ORDER_GRID_BTN_H + 6)
        x = gx0 + 8
        for key, label in row:
            win._buttons.append(Btn(x, y, ORDER_GRID_BTN_W, ORDER_GRID_BTN_H,
                                    key, label))
            x += ORDER_GRID_BTN_W + 5
    layout_air_rail(win)


def layout_air_rail(win) -> None:
    """左缘呼援轨（§11 断箭位）：空援卡竖排（顶部对齐呼援点数下沿）。"""
    y = win.height - TOP_H - 34
    for entry in win.session.air_roster():
        affordable = entry.get("affordable", True)
        label = entry["label"]
        if entry.get("in_air"):
            label += "（在空%d）" % entry["in_air"]       # GP-01 §4 在空态
        elif entry.get("cooldown_ticks", 0) > 0:
            label += "（冷却%ds）" % ((entry["cooldown_ticks"] + 9) // 10)
        win._buttons.append(Btn(MARGIN, y, RAIL_W, 24, "air:" + entry["key"],
                                label,
                                tone="normal" if affordable else "disabled"))
        y -= 28


def layout_deploy_panel(win) -> None:
    """部署页：左栏卡槽按钮（三池余量实时）+ 车道按钮（地图下缘）+ 底栏移动族。"""
    from .palette import LEFT_W
    y = win.height - TOP_H - 56
    for p in win.frame.get("players", ()):
        for slot in p.get("deck", ()):
            win._buttons.append(
                Btn(MARGIN, y, LEFT_W - 2 * MARGIN, 28,
                    "buy:%d|%s" % (slot["template_id"], slot["name"]),
                    "%s ×%d%s" % (slot["name"], slot["copies_left"],
                                  "（预备队·空投）" if slot["airdrop"] else ""),
                    tone="disabled" if slot["airdrop"] else "normal"))
            y -= 32
    x = LEFT_W + 12
    for i, name in enumerate(LANE_NAMES):
        win._buttons.append(Btn(x, MARGIN, 92, 30,
                                "lane%d" % i, "%s展开" % name))
        x += 100
    spec = (("stop", "停止(S)"), ("cancel", "取消(E)"), ("reverse", "倒车(R)"),
            ("sprint", "冲刺(Z)"), ("march", "行军(F)"))
    x = MARGIN + MINIMAP_W + 40
    for key, label in spec:                       # 机动行在车道行上方（避让同高）
        win._buttons.append(Btn(x, MARGIN + 40, ORDER_GRID_BTN_W,
                                ORDER_GRID_BTN_H, key, label))
        x += ORDER_GRID_BTN_W + 5


def layout_group_bar(win) -> None:
    """编组列（§11 断箭位）：小地图右侧竖排 1..9 槽（占用=活实体数角标，全灭
    灰显，点击=取组）——右移避开选中卡（卡 x≤252），仍邻小地图。"""
    x = MARGIN + MINIMAP_W + 56
    y = MARGIN + 4
    for n in range(1, 10):
        win._buttons.append(Btn(x, y, 26, 20, "grp:%d" % n, str(n)))
        y += 24


def draw_order_panel(win) -> None:
    """右下命令格底板＋按钮（armed 高亮）＋待令提示＋左缘呼援轨（§11）。"""
    rows = 4 + (1 if win.fsm.selected_air else 0)
    gx0, gy0, gx1, gy1 = order_grid_rect(win, rows)
    arcade.draw_lrbt_rectangle_filled(gx0, gx1, gy0, gy1, ORDER_PANEL)
    arcade.draw_lrbt_rectangle_outline(gx0, gx1, gy0, gy1, ORDER_TEXT, 1)
    armed = win.fsm.armed_order
    for btn in win._buttons:
        if btn.x0 >= gx0 - 1 and btn.yb >= gy0 - 1 and btn.x1 <= gx1 + 1:
            # 仅映射键参与高亮——旧式 `get(key) == armed` 在无待令（None）时
            # 会把全部未映射键误判成 armed（金色满格假高亮，§7 像素采样实锤）
            mapkey = ARM_KEYMAP.get(btn.key)
            draw_button(btn, armed=mapkey is not None and mapkey == armed)
    label = {None: None, "reverse": "倒车→点地", "attack": "攻击→点敌单位/点地=攻击移动",
             "fire_mission": "炮击→点地（LINE/CREEP=拖拽画线）",
             "strike": "空袭→点目标/拖拽画攻击轴", "drop": "空投→点地",
             "march": "行军→点地（沿路提速）", "unload": "卸载→点地/点楼进楼",
             "sniper": "狙击观测→点敌方目标",
             "supply": "补给停靠→点己方补给卡车"}.get(armed)
    if label:
        arcade.draw_text("待令：%s（右键/ESC 取消）" % label, gx1,
                         gy1 + 8, ORDER_ARMED, BTN_FONT, anchor_x="right")
    draw_air_rail(win)


def draw_air_rail(win) -> None:
    """左缘呼援轨绘制：标题+空援点数+卡按钮（disabled 灰显自带）。"""
    arcade.draw_text("空援 %d（点卡呼入）" % my_air_points(win),
                     MARGIN + 4, win.height - TOP_H - 14, HUD_TEXT, 12)
    for btn in win._buttons:
        if btn.key.startswith("air:"):
            draw_button(btn)


def draw_group_bar(win) -> None:
    """编组栏：1..9 槽+活实体数角标；全灭灰显（组号保留）。"""
    for btn in win._buttons:
        if not btn.key.startswith("grp:"):
            continue
        n = int(btn.key[4:])
        entry = win.fsm.groups.get(n)
        if entry is None:
            bg = GROUP_SLOT
        elif win.fsm.group_alive_count(n) == 0:
            bg = GROUP_DEAD                      # 全灭灰显（不清号）
        else:
            bg = ORDER_ARMED
        arcade.draw_lrbt_rectangle_filled(btn.x0, btn.x1, btn.yb, btn.yt, bg)
        arcade.draw_lrbt_rectangle_outline(btn.x0, btn.x1, btn.yb, btn.yt,
                                           ORDER_TEXT, 1)
        arcade.draw_text(btn.label, (btn.x0 + btn.x1) / 2, btn.yb + 3,
                         ORDER_TEXT, 11, anchor_x="center")
        if entry:
            arcade.draw_text(str(win.fsm.group_alive_count(n)),
                             btn.x1 - 2, btn.yt - 11, HUD_TEXT, 9,
                             anchor_x="right")


def draw_button(btn: Btn, *, armed: bool = False) -> None:
    if armed:
        fill = ORDER_ARMED
    elif btn.tone == "disabled":
        fill = (44, 46, 44, 255)                # 点数不足/空投限定/冷却灰显
    elif btn.tone == "focus":
        fill = (96, 84, 30, 255)                # 焦点/上下文令（飞机令行）
    else:
        fill = (58, 64, 58, 255)
    arcade.draw_lrbt_rectangle_filled(btn.x0, btn.x1, btn.yb, btn.yt, fill)
    arcade.draw_lrbt_rectangle_outline(btn.x0, btn.x1, btn.yb, btn.yt,
                                       ORDER_TEXT, 1)
    if btn.label:
        arcade.draw_text(btn.label, (btn.x0 + btn.x1) / 2, btn.yb + 6,
                         ORDER_TEXT, BTN_FONT, anchor_x="center")


def handle_panel_button(win, key: str) -> None:
    """面板按钮语义分发（热键镜像原则：按钮与键盘同走 fsm.key——同门同令；
    fm_panel/dk_* 编辑器键各自归口模块处理）。"""
    fsm, cmd = win.fsm, win.session.cmd
    sel = list(fsm.selected)
    if key.startswith("fm_form_"):
        fsm.set_fm_param("form", key[8:])
    elif key.startswith("fm_ammo_"):
        fsm.set_fm_param("ammo", key[8:])
    elif key.startswith("fm_mult_"):
        fsm.set_fm_param("ammo_mult", int(key[8:]))
    elif key.startswith("fm_salvo_"):
        fsm.set_fm_param("salvo", key[9:])
    elif key.startswith("fm_creep_"):
        fsm.set_fm_param("creep_idx", int(key[9:]))
    elif key in PANEL_KEY_MIRROR:              # 热键镜像：按钮=按键同门同令
        fsm.key(PANEL_KEY_MIRROR[key], cmd=cmd)
    elif key == "fm_cancel":
        cmd.cancel_fire_mission(sel)
    elif key == "smoke_sprint":
        fsm.key("G", cmd=cmd)
    elif key == "ambush":
        cmd.ambush(sel)
    elif key == "deploy_gun":
        cmd.deploy_gun(sel)
    elif key == "pack_gun":
        cmd.pack_gun(sel)
    elif key == "tow":
        cmd.tow(sel)
    elif key == "untow":
        cmd.untow(sel)
    elif key == "formation":                   # 队形循环 NONE→LINE→COLUMN→WEDGE
        order = ("NONE", "LINE", "COLUMN", "WEDGE")
        cur = next((u.get("formation", "none").upper()
                    for u in win.frame.get("units", ())
                    if u["id"] in fsm.selected), "NONE")
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order \
            else "LINE"
        cmd.formation(sel, nxt)
        fsm.notify("队形：%s" % nxt)
    elif key == "supply":
        fsm.arm_order("supply")
    elif key.startswith("lane"):
        handle_lane_move(win, int(key[4:]))
    elif key.startswith("air:"):
        handle_air_call_button(win, key[4:])
    elif key.startswith("buy:"):
        tid_s, name = key[4:].split("|", 1)
        handle_arm_purchase_card(win, int(tid_s), name)
    elif key.startswith("grp:"):
        fsm.recall_group(int(key[4:]))
    elif key.startswith("sel:"):
        uid = int(key[4:])
        fsm.select_units([uid])
        win._info_uid = uid
    elif key.startswith("airsel:"):            # 飞机面板行=选中该机（§4 ④段）
        fsm.click_aircraft(int(key[7:]))
    elif key == "buy_cancel":
        fsm.cancel_purchase()


# ── 面板点击语义（GP-01 §5.2 拆分自 shell_window——按钮面点击的语义体）──

def draw_deploy_panel(win) -> None:
    """部署页左栏三池面板绘制（卡槽/车道按钮/待放卡提示）。"""
    from .palette import LEFT_W
    top = win.height - TOP_H
    arcade.draw_lrbt_rectangle_filled(0, LEFT_W, BOTTOM_H, top,
                                      ORDER_PANEL)
    arcade.draw_text("卡组三池（点槽装弹→点地放卡）", MARGIN + 6, top - 26,
                     HUD_TEXT, 13)
    arcade.draw_text("空投限定卡灰显（经 O 键空投投送）", MARGIN + 6,
                     top - 44, (150, 150, 150, 255), 11)
    for btn in win._buttons:
        if btn.key.startswith("buy:"):
            armed = (win.fsm.armed_purchase is not None
                     and win.fsm.armed_purchase[0]
                     == int(btn.key[4:].split("|", 1)[0]))
            draw_button(btn, armed=armed)
        elif btn.key.startswith("lane"):
            draw_button(btn)
    if win.fsm.armed_purchase is not None:
        arcade.draw_text("待放：%s → 点地确认（右键撤回）"
                         % win.fsm.armed_purchase[1],
                         LEFT_W + 12, top - 46, ORDER_ARMED, 12)


def lane_points(map_cm) -> list[tuple[int, int]]:
    """部署页三车道（actions.py _deploy_lanes 同式——纯 UI 算术）。"""
    cx = map_cm[0] // 2
    ex, ey = map_cm
    y = ey // 5                                  # 己方（team0=南）向图心推进 1/5
    off = ex // 5
    return [(cx + d * off, y) for d in (-1, 0, 1)]


def handle_lane_move(win, idx: int) -> None:
    """车道批量展开（西/中/东——空选区=全己方）。"""
    lanes = lane_points(win.frame.get("map_cm", (200000, 100000)))
    sel = list(win.fsm.selected) or [
        u["id"] for u in win.frame.get("units", ())
        if u["team"] == win.frame.get("view")]
    if sel:
        win.session.cmd.move(sel, lanes[idx])


def my_air_points(win) -> int:
    for p in win.frame.get("players", ()):
        return p.get("air_points", 0)
    return 0


def handle_air_call_button(win, key: str) -> None:
    """空呼按钮：点数/冷却预判 toast（引擎门仍为最终权威）。"""
    for entry in win.session.air_roster():
        if entry["key"] == key:
            if not entry.get("affordable", True):
                if entry.get("cooldown_ticks", 0) > 0:
                    win.fsm.notify("%s 再呼入冷却中（%ds）"
                                   % (entry["template"].name,
                                      (entry["cooldown_ticks"] + 9) // 10),
                                   tone="error")
                    return
                win.fsm.notify("空援点数不足（需 %d/%d）"
                               % (entry.get("cost", 0), my_air_points(win)),
                               tone="error")
                return
            win.session.cmd.air_call(entry["template"], entry["payload"])
            return


def handle_arm_purchase_card(win, template_id: int, name: str) -> None:
    """点卡装弹（三池预检→toast 写明被拒原因；引擎门仍为最终权威）。"""
    fsm = win.fsm
    slot = None
    for p in win.frame.get("players", ()):
        for s in p.get("deck", ()):
            if s["template_id"] == template_id:
                slot = (p, s)
    if slot is None:
        return
    p, s = slot
    if s.get("airdrop"):
        fsm.notify("空降卡经空投投送（实战页 O 键投放），不能直接购买",
                   tone="error")
        return
    if s.get("copies_left", 0) <= 0:
        fsm.notify("%s 余量已尽" % name, tone="error")
        return
    cost = getattr(win.session, "card_cost", lambda _tid: 0)(template_id)
    if p.get("points", 0) < cost:
        fsm.notify("点数不足（需 %d/%d）" % (cost, p.get("points", 0)),
                   tone="error")
        return
    fsm.arm_purchase(template_id, name)


def handle_confirm_purchase(win, cm) -> None:
    """点地放卡确认：购卡（引擎门裁决）+ 胶水层 pending 展开队列登记。"""
    fsm = win.fsm
    tid, name = fsm.armed_purchase
    if fsm.page != "deploy":
        fsm.notify("购卡仅部署期可用", tone="error")
        fsm.cancel_purchase()
        return
    cmd_obj = win.session.cmd.purchase(tid)
    if cmd_obj is None:
        fsm.notify("购卡被拒：%s（空降限定/未知卡）" % name, tone="error")
        return
    queue_expand = getattr(win.session, "queue_expand", None)
    if queue_expand is not None:
        queue_expand(tid, (int(cm[0]), int(cm[1])))
    fsm.cancel_purchase()
