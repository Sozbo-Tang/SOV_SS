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

from .order_filter import eligible_orders
from .order_icons import badge_for, draw_badge, draw_order_tile, draw_tooltip
from .palette import (BOTTOM_H, BTN_FONT, GROUP_BAR_GAP, GROUP_DEAD,  # noqa: E402
                      GROUP_PITCH, GROUP_SLOT, GROUP_SLOT_H, HUD_TEXT,
                      MARGIN, MINIMAP_W, ORDER_ARMED, ORDER_EMPTY_ROWS,
                      ORDER_GAP, ORDER_PANEL,
                      ORDER_TEXT, ORDER_TILE, RAIL_W, TOP_H)

# 底栏按钮 → fsm 键位语义（热键一一镜像：按钮=按键同门同令；GP-01 §4/§6 扩容；
# P0 键位纠偏块 2026-10-13：attack A→Q——手册 HOTKEYS「Q Attack Move」；
# P1 机制块 2026-10-13 +air_ab/decoy/laser/precision/mount_z 分派键（镜像 fsm.key）。
# 〔B3 修复块 2026-10-13 勘正：本表=按钮→热键的**分派**映射，非呈现许可——
# 按钮=order_filter 三态过滤的呈现面（hide 不布局/grey 灰显）；热键=全量通道
# （shell_fsm.key 不经过滤——热键宽容拍板留痕）；引擎资格门=唯一权威
# （rejections→toast 事后反馈链）。〕
# 〔终审第四批 2026-10-13 +radar：ABILITIES Radar（manual.txt:534-539）补菜单
# 面——manual.txt:482-485「They can be found in the orders menu」；镜像 Z 同门
# 同令（地面选区经 _ground_z_dispatch 分流，雷达优先双发口径不变）。〕
PANEL_KEY_MIRROR = {"stop": "S", "cancel": "E", "reverse": "R", "sprint": "Z",
                    "smoke_x": "X", "stance_h": "H", "attack": "Q", "fm": "T",
                    "strike": "K", "drop": "O", "march": "F", "unload": "U",
                    "sniper": "L", "air_alt": "V", "air_rtb": "B",
                    "air_engage": "J", "air_disengage": "Y",
                    "air_ab": "Z", "decoy": "C", "laser": "N", "precision": "P",
                    "mount": "M", "radar": "Z"}

# 待令组按钮 → fsm 待令组（armed 高亮映射；移动族右键直达无按钮）
ARM_KEYMAP = {"reverse": "reverse", "attack": "attack", "fm": "fire_mission",
              "strike": "strike", "drop": "drop", "march": "march",
              "unload": "unload", "sniper": "sniper", "supply": "supply",
              "laser": "laser", "mount": "mount", "precision": "precision"}

LANE_NAMES = ("西翼", "中央", "东翼")

# 呼援轨页签（2026-10-14 呼援轨页签块——断箭 REC/INF/VEH/SUP 呼援轨范式
# 〔02 调研 §1〕；2026-10-15 两处修正·其一：可见性按阶段与可放置性收敛——
# _rail_visible_tabs（deploy 无 AIR／无可放置卡类别整签不渲染／HEL 无旋翼机
# 数据不渲染）。页签态 win._rail_tab 两页共享（rail_tab_of 对不可见页签回退 ALL）
_RAIL_TABS = (("ALL", "全部"), ("REC", "侦察"), ("INF", "步兵"),
              ("VEH", "车辆"), ("SUP", "补给"), ("HEL", "直升机"),
              ("AIR", "固定翼"))


def _slot_tab(meta: dict) -> str:
    """模板→呼援轨页签：类目 0 侦察/1 步兵直映；2 装甲/3 火支→VEH；4 防空后勤
    按 HAS_SUPPLY 分流（有物资槽=补给卡车→SUP，否则防空车→VEH）。"""
    cat = meta.get("category")
    if cat == 0:
        return "REC"
    if cat == 1:
        return "INF"
    if cat == 4:
        return "SUP" if meta.get("supply") else "VEH"
    return "VEH"


def _rail_visible_tabs(win) -> list:
    """当前阶段可见页签（2026-10-15 两处修正·其一——用户拍板「不同阶段展现
    不同类别；无法放置的单位类别不出现」）：
    - 阶段差分：deploy=地面类别（航空=实战呼入——断箭参照〔02 调研 §2/§5〕部署
      期地面部署、飞行器战斗中呼援；引擎 cmd_air_call 无相位拦，UI 入口随阶段
      收口=纯呈现面，引擎不动）；battle=地面＋AIR（空援 roster 非空时）。
    - 无法放置不出现：地面页签须有 ≥1 可放置卡（非空降限定且余量>0——余量尽/
      纯空降类别整签不渲染）；HEL=1944 无旋翼机数据，整签不渲染（占位文案同批
      移除）；「全部」=可见类别之并的前置签（无任何可见类别时不渲染）。
    duck 窗（session 无 deck_slot_meta）保持既有兜底：无类别面→有任一可放置卡
    即四个地面页签全可见（测试兼容口径）。"""
    page = win.fsm.page
    known = hasattr(win.session, "deck_slot_meta")
    meta = win.session.deck_slot_meta() if known else {}
    counts: dict = {}
    unclassified = 0
    for p in win.frame.get("players", ()):
        for slot in p.get("deck", ()):
            if slot.get("airdrop") or slot.get("copies_left", 0) <= 0:
                continue
            if known:
                tk = _slot_tab(meta.get(slot["template_id"], {}))
                counts[tk] = counts.get(tk, 0) + 1
            else:
                unclassified += 1
    visible = []
    for tk, _cn in _RAIL_TABS:
        if tk in ("ALL", "HEL"):
            continue
        if tk == "AIR":
            if page == "battle" and list(win.session.air_roster()):
                visible.append(tk)
            continue
        if (counts.get(tk, 0) > 0) if known else (unclassified > 0):
            visible.append(tk)
    if visible:
        visible.insert(0, "ALL")
    return visible


def rail_tab_of(win) -> str:
    """当前呼援页签（窗口层态——两页共享；缺省 ALL=不过滤平铺）。2026-10-15：
    落在不可见页签（跨阶段残留——如上局实战切 AIR 后回部署、或类别余量耗尽）
    时回退 ALL，不留悬空态。"""
    tab = getattr(win, "_rail_tab", "ALL")
    return tab if tab in _rail_visible_tabs(win) else "ALL"

# 战斗页右下命令格（§11：行序=航空上下文（置顶）/作战/机动/支援/杂项——短标签
# 对齐断箭图标菜单密度；热键字母随标签保留，帮助面板 F1 仍载全文）
# 〔P1 机制块 2026-10-13：air 行 +加力(Z)/诱饵(C)；作战行 +照射(N)/精确(P)；
# 支援行狙击挪 L、+登车(M)；+补给行（选中补给载具浮出——购买三档+四开关，
# basics:198-213）。〕
_ORDER_ROW_AIR = (("air_alt", "高度(V)"), ("air_rtb", "返航(B)"),
                  ("air_engage", "对空(J)"), ("air_disengage", "脱离(Y)"),
                  ("air_ab", "加力(Z)"), ("decoy", "诱饵(C)"))
_ORDER_ROW_COMBAT = (("attack", "攻击(Q)"), ("fm", "炮击(T)"), ("strike", "空袭(K)"),
                     ("drop", "空投(O)"), ("smoke_x", "烟幕(X)"),
                     ("laser", "照射(N)"), ("precision", "精确(P)"),
                     ("radar", "雷达(Z)"))
_ORDER_ROW_MANEUVER = (("stop", "停止(S)"), ("cancel", "取消(E)"),
                       ("reverse", "倒车(R)"), ("sprint", "冲刺(Z)"),
                       ("march", "行军(F)"))
_ORDER_ROW_SUPPORT = (("stance_h", "纪律(H)"), ("smoke_sprint", "烟冲(G)"),
                      ("unload", "卸载(U)"), ("sniper", "狙击(L)"), ("supply", "补给"),
                      ("mount", "登车(M)"))
_ORDER_ROW_AUX = (("ambush", "伏击"), ("deploy_gun", "展开"), ("pack_gun", "收炮"),
                  ("tow", "拖曳"), ("untow", "解拖"), ("formation", "队形"),
                  ("fm_cancel", "撤炮"))
# 补给行（P1——选中带物资槽的己方单位时浮出；购买三档 basics:198-200 +
# 四开关 basics:208-213，开关标签带 ●=开）
_ORDER_ROW_SUPPLY = (("sup_buy1", "买1t"), ("sup_buy4", "买4t"),
                     ("sup_buymax", "买满"), ("sup_share", "共享"),
                     ("sup_heal", "医疗"), ("sup_repair", "维修"),
                     ("sup_ammo", "弹药"))


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


def order_grid_rect(win, rows: int, cols: int = 8):
    """右下命令格矩形 (x0,y0,x1,y1)：锚右下角（手册 P18 命令菜单位），纯算术。
    断箭式图标格（2026-10-14）：cols=最宽行格数（≤8），格=ORDER_TILE 方形＋
    ORDER_GAP 缝。"""
    w = 16 + cols * ORDER_TILE + (cols - 1) * ORDER_GAP
    h = 16 + rows * ORDER_TILE + (rows - 1) * ORDER_GAP
    x1 = win.width - MARGIN
    return (x1 - w, MARGIN, x1, MARGIN + h)


def order_panel_rect(win):
    """命令面板矩形（问题5·2026-10-15 用户拍板常驻右下）：有行=按行数/列数
    实足印（现状公式）；空选区=**满配 6×8 足印**占位（364×286——与 fm 参数条
    让位算术自洽：286+8=294=fm y0，面板高度不随选区跳变）。布局/绘制/空中卡
    锚（air_panel_geom）三消费面同源此函数——空态形态唯一事实源。"""
    rows = _battle_rows(win)
    if rows:
        cols = max(len(r) for r in rows)
        return order_grid_rect(win, len(rows), cols)
    return order_grid_rect(win, ORDER_EMPTY_ROWS, 8)


def _supply_selected(win) -> bool:
    """选中面含带物资槽的己方单位（帧 supply_gates 键存在即补给堆/卡车——
    P1 补给行浮出条件）。"""
    for u in win.frame.get("units", ()):
        if u["id"] in win.fsm.selected and u.get("team") == win.frame.get("view") \
                and "supply_gates" in u:
            return True
    return False


def _battle_rows(win) -> list[tuple]:
    """右下命令格行集（B3 修复块 2026-10-13）：经 order_filter.eligible_orders
    三态过滤——hide 键不布局、grey 键 tone=disabled（余量尽/前置缺失可恢复）；
    补给行维持 _supply_selected 浮出条件（P1 范式样板）。返回 [(key,label,
    tone), ...] 行列表（布局/绘制共用一源——行数与键集零漂移）。"""
    states = eligible_orders(win.frame, win.fsm.selected, win.fsm.selected_air)
    base = (_ORDER_ROW_AIR if win.fsm.selected_air else None,
            _ORDER_ROW_COMBAT, _ORDER_ROW_MANEUVER, _ORDER_ROW_SUPPORT,
            _ORDER_ROW_SUPPLY if _supply_selected(win) else None,
            _ORDER_ROW_AUX)
    rows = []
    for row in base:
        if not row:
            continue
        filtered = tuple((key, label,
                          "disabled" if states.get(key) == "grey" else "normal")
                         for key, label in row if states.get(key) != "hide")
        if filtered:
            rows.append(filtered)
    return rows


def layout_battle_buttons(win) -> None:
    """右下命令格＋左缘呼援轨（§11）：格行=航空上下文（置顶）/作战/机动/支援/
    杂项＋补给行（P1——选中补给载具浮出）；轨=空援卡+地面呼援卡竖排（P1 战中
    呼援 basics:165-168——战斗页同轨追加地面卡）。
    〔B3 修复块（2026-10-13）：格键经 order_filter 三态过滤——菜单只列选区
    可被下达的命令（manual.txt:344-346/482-485）。空选区=无命令钮可排（空循环）
    ——面板常驻足印由 order_panel_rect/draw_order_panel 承载（B3 勘注
    2026-10-15：原「空选区不绘命令格（basics.txt:62）」推读被用户拍板推翻——
    空选区绘满配足印提示格，manual.txt:344-346 未规定空选区形态；三态过滤
    行为保留）；呼援轨仍常驻（basics.txt:53 独立面）。〕"""
    rows = _battle_rows(win)
    cols = max((len(r) for r in rows), default=0)
    gx0, _gy0, _gx1, gy1 = order_grid_rect(win, len(rows), cols)
    for ri, row in enumerate(rows):                     # 行自顶向下
        y = gy1 - 8 - ORDER_TILE - ri * (ORDER_TILE + ORDER_GAP)
        x = gx0 + 8
        for key, label, tone in row:
            win._buttons.append(Btn(x, y, ORDER_TILE, ORDER_TILE,
                                    key, label, tone=tone))
            x += ORDER_TILE + ORDER_GAP
    layout_air_rail(win)


def layout_air_rail(win) -> None:
    """左缘呼援轨（§11 断箭位）：空援卡竖排（顶部对齐呼援点数下沿）。
    〔P1 机制块 2026-10-13：battle 页在空援轨下方续排**地面呼援卡**（basics:
    165-168「战斗全程随时可呼」——deploy 页左栏卡轨的实战页同构；两段式点击
    （点槽装弹→点地确认）与部署期共用 handle_confirm_purchase。〕
    〔B1 修复块 2026-10-13：循环末记录 win._rail_bottom=末卡下缘——左侧选中卡
    panel_geom 据此动态让位（卡下探多深、面板就让多矮），两面板互不遮盖；
    每帧布局无条件重写（陈旧值不留）。标签经 fit_text 截宽 RAIL_W-8——
    「（在空N）/（冷却Ns）」后缀再长也不溢出轨道。〕"""
    from .hud_top import fit_text
    y = win.height - TOP_H - 34
    top = y
    visible = _rail_visible_tabs(win)
    tab = rail_tab_of(win)
    xi = 0
    for tk, cn in _RAIL_TABS:                          # 页签行（仅可见类别）
        if tk not in visible:
            continue
        win._buttons.append(Btn(MARGIN + xi * 30, y - 20, 28, 20,
                                "railtab_%s" % tk, cn,
                                tone="focus" if tk == tab else "normal"))
        xi += 1
    y -= 46                                          # 页签带 y-20..y——卡片顶
    # 缘须低于页签带（首卡 yb=y-46 跨 y-46..y-22，与页签带零交——重叠会让
    # 首卡中心点击命中先布局的页签钮，toast/呼入吞事件）
    if tab == "AIR" or (tab == "ALL" and "AIR" in visible):
        # 固定翼空援卡（deploy 不列——阶段差分见 _rail_visible_tabs）
        for entry in win.session.air_roster():
            affordable = entry.get("affordable", True)
            label = entry["label"]
            if entry.get("in_air"):
                label += "（在空%d）" % entry["in_air"]       # GP-01 §4 在空态
            elif entry.get("cooldown_ticks", 0) > 0:
                label += "（冷却%ds）" % ((entry["cooldown_ticks"] + 9) // 10)
            win._buttons.append(Btn(MARGIN, y, RAIL_W, 24, "air:" + entry["key"],
                                    fit_text(label, RAIL_W - 8, BTN_FONT),
                                    tone="normal" if affordable else "disabled"))
            y -= 28
    if tab != "AIR":                                 # 地面卡（AIR 页签不混地面）
        # duck 窗（测试 SimpleNamespace session）无 deck_slot_meta 面——不过滤
        # 全展示（stub 场景惯例；真 session 恒有=按页签过滤）；ALL=可见类别之并
        # （隐藏类别的 ×0 卡不进——与页签可见性同口径）
        known = hasattr(win.session, "deck_slot_meta")
        meta = win.session.deck_slot_meta() if known else {}
        if not known:
            allowed = None
        elif tab == "ALL":
            allowed = set(visible) - {"ALL"}
        else:
            allowed = {tab}
        for p in win.frame.get("players", ()):
            for slot in p.get("deck", ()):
                if slot.get("airdrop"):
                    continue                          # 空降限定卡仍只经空投
                if allowed is not None and _slot_tab(
                        meta.get(slot["template_id"], {})) not in allowed:
                    continue
                win._buttons.append(
                    Btn(MARGIN, y, RAIL_W, 24,
                        "buy:%d|%s" % (slot["template_id"], slot["name"]),
                        fit_text("%s ×%d" % (slot["name"], slot["copies_left"]),
                                 RAIL_W - 8, BTN_FONT),
                        tone="normal" if slot.get("copies_left", 0) > 0
                        else "disabled"))
                y -= 28
    win._rail_bottom = y + 28 if y < top else top    # B1：末卡下缘（无卡=轨顶）


def layout_deploy_panel(win) -> None:
    """部署页：左栏卡槽按钮（三池余量实时）+ 车道按钮（地图下缘）+ 底栏移动族。
    〔B1 修复块 2026-10-13：卡槽标签 fit_text 截宽 LEFT_W-2*MARGIN-8——长卡名
    以「…」收尾不溢出 244px 卡槽；空降后缀压缩「（空投）」。〕"""
    from .palette import LEFT_W
    layout_air_rail(win)                 # §六页签轨（2026-10-14）——部署/实战同款
    x = LEFT_W + 12
    for i, name in enumerate(LANE_NAMES):
        win._buttons.append(Btn(x, MARGIN, 92, 30,
                                "lane%d" % i, "%s展开" % name))
        x += 100
    spec = (("stop", "停止(S)"), ("cancel", "取消(E)"), ("reverse", "倒车(R)"),
            ("sprint", "冲刺(Z)"), ("march", "行军(F)"))
    x = MARGIN + MINIMAP_W + 40
    for key, label in spec:        # 机动行（部署页文字按钮——图标格仅实战页）
        win._buttons.append(Btn(x, MARGIN + 40, 92, 24, key, label))
        x += 92 + 5


def layout_group_bar(win) -> None:
    """编组列（§11 断箭位）：小地图右侧竖排 1..9 槽（占用=活实体数角标，全灭
    灰显，点击=取组）。〔问题4·2026-10-15 对齐式：x 缝 GROUP_BAR_GAP=8、钮高
    GROUP_SLOT_H=14、pitch=GROUP_PITCH=17——列底=首钮 yb=MARGIN=小地图底、
    列顶=末钮 yt=MARGIN+MINIMAP_H=小地图顶（(150-14)/8=17 整除，顶底双齐）；
    旧位 x+56/高 20/pitch 24（列顶冒出小地图 66px）就此废止。〕"""
    x = MARGIN + MINIMAP_W + GROUP_BAR_GAP
    y = MARGIN
    for n in range(1, 10):
        win._buttons.append(Btn(x, y, 26, GROUP_SLOT_H, "grp:%d" % n, str(n)))
        y += GROUP_PITCH


def order_tile_buttons(win, rect):
    """命令格矩形内的图标格按钮集（**四边全含**判定）。

    崩溃勘正（2026-10-14 实机复现）：旧判定只有下界（yb>=gy0）无上界——炮击
    待令态浮出的参数条按钮（fm_salvo_HALF，格上方 y≈320）漏进图标格绘制，键
    不在 ICON_FUNCS 走 fallback 崩 tilt_angle。抽成纯函数供回归测试锚定。"""
    gx0, gy0, gx1, gy1 = rect
    return [b for b in win._buttons
            if b.x0 >= gx0 - 1 and b.x1 <= gx1 + 1
            and b.yb >= gy0 - 1 and b.yt <= gy1 + 1]


def draw_order_panel(win) -> None:
    """右下命令格（断箭式图标格·2026-10-14）：底板＋图标格（armed 高亮/悬停
    提亮/禁用去饱和）＋行间细分隔线＋右上余量角标＋悬停 tooltip＋待令提示＋
    左缘呼援轨（§11）。
    〔B3 修复块（2026-10-13）：行集走 _battle_rows（order_filter 三态过滤同源）
    ——菜单只列选区可被下达的命令。B3 勘注（2026-10-15 用户拍板常驻）：原「空
    选区不绘命令格（basics.txt:62）」推读推翻——空选区绘**满配 6×8 足印占位
    格**（order_panel_rect）＋居中灰字提示（不伪造可用性暗示——无按钮布局、
    命中面仅底板）；三态过滤行为保留（空选区仍无钮可下达）。
    呈现规格=实机 ba_shot4 读图：方形图标格/矢量图标/热键角/角标数字/灰显/
    悬停 tooltip/行间分隔线——图标绘制与 tooltip 在 order_icons.py。〕"""
    rows = _battle_rows(win)
    gx0, gy0, gx1, gy1 = order_panel_rect(win)
    if not rows:
        arcade.draw_lrbt_rectangle_filled(gx0, gx1, gy0, gy1, ORDER_PANEL)
        arcade.draw_lrbt_rectangle_outline(gx0, gx1, gy0, gy1, ORDER_TEXT, 1)
        arcade.draw_text("点选单位后列出可用命令", (gx0 + gx1) / 2,
                         (gy0 + gy1) / 2 - 7, (150, 150, 150, 255), 13,
                         anchor_x="center")
        draw_air_rail(win)
        return
    arcade.draw_lrbt_rectangle_filled(gx0, gx1, gy0, gy1, ORDER_PANEL)
    arcade.draw_lrbt_rectangle_outline(gx0, gx1, gy0, gy1, ORDER_TEXT, 1)
    for ri in range(len(rows) - 1):        # 行间细分隔线（断箭同款）
        yd = gy1 - 8 - ORDER_TILE - ri * (ORDER_TILE + ORDER_GAP) \
            + ORDER_TILE + ORDER_GAP / 2
        arcade.draw_line(gx0 + 6, yd, gx1 - 6, yd, (60, 66, 60, 255), 1)
    armed = win.fsm.armed_order
    mx, my = getattr(win, "_mouse_xy", None) or (-1, -1)
    hovered_btn = None
    for btn in order_tile_buttons(win, (gx0, gy0, gx1, gy1)):
        # 仅映射键参与高亮——旧式 `get(key) == armed` 在无待令（None）时
        # 会把全部未映射键误判成 armed（金色满格假高亮，§7 像素采样实锤）
        mapkey = ARM_KEYMAP.get(btn.key)
        is_armed = mapkey is not None and mapkey == armed
        hov = btn.hit(mx, my)
        if hov:
            hovered_btn = btn
        draw_order_tile(btn, armed=is_armed, hovered=hov)
        badge = badge_for(win, btn.key)
        if badge:
            draw_badge(btn, badge)
    if hovered_btn is not None and armed is None:
        draw_tooltip(hovered_btn, win)     # 待令态隐藏 tooltip（避免与提示语叠）
    label = {None: None, "reverse": "倒车→点地", "attack": "攻击→点敌单位/点地=攻击移动",
             "fire_mission": "炮击→点地（LINE/CREEP=拖拽画线）",
             "strike": "空袭→点目标/拖拽画攻击轴", "drop": "空投→按住左键拖拽画区/单击点投",
             "march": "行军→点地（沿路提速）",
             "unload": "卸载→点地/点楼进楼（再按 U=就地卸载）",
             "sniper": "狙击观测→点敌方目标（L）",
             "supply": "补给停靠→点己方补给卡车",
             # ── P1 待令组（2026-10-13）──
             "laser": "激光照射→点敌方目标（N——断 LOS 失效）",
             "mount": "登车→点己方载具（M）",
             "precision": "精密打击→点地（靠近激光位；Shift 排队）"}.get(armed)
    if label:
        # BA 复刻轮：待令提示行收进命令格顶与摘要行之间的 12px 缝
        # （旧 gy1+8 会压摘要行 y0=格顶+12 的上缘）
        arcade.draw_text("待令：%s（右键/ESC 取消｜Shift+确认=入队续令）" % label,
                         gx1, gy1 + 1, ORDER_ARMED, BTN_FONT, anchor_x="right")
    draw_air_rail(win)


def draw_air_rail(win) -> None:
    """左缘呼援轨绘制：页签行（仅可见类别）＋标题（空援点数）＋卡按钮。
    2026-10-15 两处修正·其一：HEL 占位文案随「无法放置类别不出现」移除
    （1944 无旋翼机，整签不渲染——_rail_visible_tabs）；railtab_/air:/buy:
    一并绘制（实战页 buy: 卡旧缺口 2026-10-14 已收口）。"""
    arcade.draw_text("呼援 %d（点卡呼入）" % my_air_points(win),
                     MARGIN + 4, win.height - TOP_H - 14, HUD_TEXT, 12)
    for btn in win._buttons:
        if btn.key.startswith("railtab_") or btn.key.startswith("air:") \
                or btn.key.startswith("buy:"):
            draw_button(btn, armed=(btn.key == "railtab_" + rail_tab_of(win)
                                    and btn.tone == "focus"))


def draw_group_bar(win) -> None:
    """编组栏：1..9 槽+活实体数角标；全灭灰显（组号保留）。〔问题4·2026-10-15：
    槽高 14——文字基线 yb+2（11 号字 yb+2..yb+13 恰容）、角标 9 号字 yt-11 起
    不越顶；两量在 14px 高内仍可读（量尺源 palette GROUP_SLOT_H）。〕"""
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
        arcade.draw_text(btn.label, (btn.x0 + btn.x1) / 2, btn.yb + 2,
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
    elif key in ("sup_buy1", "sup_buy4", "sup_buymax"):   # P1 补给购买三档
        tier = {"sup_buy1": "t1", "sup_buy4": "t4",
                "sup_buymax": "max"}[key]
        sel = [u["id"] for u in win.frame.get("units", ())
               if u["id"] in fsm.selected and "supply_gates" in u]
        if cmd.buy_supplies_tier(sel, tier):
            fsm.notify("补给购买：%s（重量入池——装填进度见弹药/医疗位）"
                       % {"t1": "小档", "t4": "中档", "max": "买满"}[tier])
        else:
            fsm.notify("购买被拒（非补给模式/舱位门）", tone="error")
    elif key.startswith("sup_"):                    # P1 四开关（share/heal/repair/ammo）
        which = key[4:]
        for u in win.frame.get("units", ()):
            if u["id"] in fsm.selected and "supply_gates" in u:
                on = not u["supply_gates"].get(which, True)
                cmd.supply_switch([u["id"]], which, on)
                fsm.notify("补给堆 %s=%s" % (which, "开" if on else "关"))
    elif key.startswith("railtab_"):
        win._rail_tab = key[8:]        # 页签切换（布局每帧重写即生效）
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
        fsm.select_units([int(key[4:])])
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
    arcade.draw_text("卡组呼援（点卡装弹→点地放卡）", MARGIN + 6, top - 26,
                     HUD_TEXT, 13)
    arcade.draw_text("空投限定卡灰显（经 O 键空投投送）", MARGIN + 6,
                     top - 44, (150, 150, 150, 255), 11)
    for btn in win._buttons:
        if btn.key.startswith("buy:"):
            armed = (win.fsm.armed_purchase is not None
                     and win.fsm.armed_purchase[0]
                     == int(btn.key[4:].split("|", 1)[0]))
            draw_button(btn, armed=armed)
        elif btn.key.startswith("railtab_") or btn.key.startswith("lane"):
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
    """点地放卡确认：购卡（引擎门裁决）+ 胶水层 pending 展开队列登记。
    〔P1 机制块 2026-10-13：deploy+battle 两页放行（basics:165-168 战斗全程
    随时可呼——战中呼援出场走 spawn_step 既有链，dest 钳己方部署条带）。〕"""
    fsm = win.fsm
    tid, name = fsm.armed_purchase
    if fsm.page not in ("deploy", "battle"):
        fsm.notify("购卡在部署/实战页可用", tone="error")
        fsm.cancel_purchase()
        return
    cmd_obj = win.session.cmd.purchase(
        tid, (int(cm[0]), int(cm[1])))      # dest=点击点→垂足出动（2026-10-12 拍板）
    if cmd_obj is None:
        fsm.notify("购卡被拒：%s（空降限定/未知卡）" % name, tone="error")
        return
    queue_expand = getattr(win.session, "queue_expand", None)
    if queue_expand is not None:
        queue_expand(tid, (int(cm[0]), int(cm[1])))
    fsm.cancel_purchase()
