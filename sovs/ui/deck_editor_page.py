"""卡组编辑器页（GP-01 §7 M4）：纯呈现＋命中域——数据经 session.deck_editor 鸭子面。

布局（§7 拍板）：左＝类别页签（侦察/步兵/装甲/火力支援/防空后勤）；中＝该类目
卡池（名/价/限份/配额组——自 data/yaml 编译面按 faction 过滤）；右＝当前卡组
汇总（逐卡份数±、两池点数条、类别×池配额条、火支子配额条——超限即时红显）；
底＝动作行（新建/复制/改名/保存/删除/返回）。操作=点卡池条目加一份、汇总条目
±调份数、达 D032 限份即灰（拖放后置）。校验=card_schema.validate_deck 同权威
（经窗口层调 session.deck_editor.validate → fsm.deck_edit["errors"] 内联红字＋
保存禁用）。航空卡不入 deck（独立空点数池——页脚明示）。

本模块不 import sovs.sim（AST 守卫②）；deck_edit 页战斗键全拦同 config
（shell_fsm.key 页面门），ESC 返回 config。
"""
from __future__ import annotations

import arcade

from .hud_bottom import Btn, draw_button  # noqa: E402（按钮原语共享）
from .palette import (DECK_BAD, DECK_OK, HUD_PANEL,  # noqa: E402
                      HUD_TEXT, MARGIN, ORDER_ARMED, TOP_H)

_TAB_CN = {"RECON": "侦察", "INFANTRY": "步兵", "ARMOR": "装甲",
           "FIRE_SUPPORT": "火力支援", "AA_LOGISTICS": "防空后勤"}
_POOL_CN = {"MAIN": "主力", "RESERVE": "预备队"}
_MAX_POOL_ROWS = 11                  # 中栏卡池行上限（不滚动——类目页签分流）
_MAX_SUM_ROWS = 12                   # 右栏汇总行上限


def _tab_order(win) -> list[str]:
    catalog = getattr(win, "_deck_catalog", ()) or ()
    tabs = []
    for c in catalog:
        if c["category"] not in tabs:
            tabs.append(c["category"])
    return tabs


def layout_deck_edit_page(win) -> None:
    """编辑器页按钮：类别页签/卡池加卡行/汇总±行/动作行。"""
    fsm = win.fsm
    state = fsm.deck_edit or {}
    catalog = [c for c in (getattr(win, "_deck_catalog", ()) or ())
               if c["faction"] == state.get("faction")]
    tabs = _tab_order(win)
    x, y = MARGIN, win.height - TOP_H - 34
    for tab in tabs:
        label = _TAB_CN.get(tab, tab)
        win._buttons.append(Btn(x, y, 92, 26, "dk_tab_%s" % tab, label,
                                tone="focus" if state.get("tab") == tab
                                else "normal"))
        x += 96
    # 中栏卡池（当前页签×阵营过滤；限份用尽=灰）
    copies = dict(state.get("cards", ()))
    y = win.height - TOP_H - 78
    shown = 0
    for c in catalog:
        if c["category"] != state.get("tab"):
            continue
        if shown >= _MAX_POOL_ROWS:
            break
        used_out = copies.get(c["card_key"], 0) >= c["per_card_limit"]
        label = "%s %d分 限%d%s" % (c["name"], c["cost"], c["per_card_limit"],
                                    ("·%s" % c["quota_group"]
                                     if c["quota_group"] != "NONE" else ""))
        win._buttons.append(Btn(MARGIN + 130, y, 300, 24, "dk_add_%s"
                                % c["card_key"], label,
                                tone="disabled" if used_out else "normal"))
        y -= 26
        shown += 1
    # 右栏汇总（±调份数）
    summary = state.get("summary") or {}
    y = win.height - TOP_H - 78
    for card_key, n in list(state.get("cards", ()))[:_MAX_SUM_ROWS]:
        win._buttons.append(Btn(win.width - 300, y, 24, 22, "dk_dec_%s"
                                % card_key, "－"))
        win._buttons.append(Btn(win.width - 272, y, 24, 22, "dk_inc_%s"
                                % card_key, "＋"))
        y -= 26
    # 底部动作行
    actions = (("dk_new", "新建"), ("dk_clone", "复制"), ("dk_rename", "改名"),
               ("dk_save", "保存并编译"), ("dk_delete", "删除"), ("dk_back", "返回(ESC)"))
    x = MARGIN
    for key, label in actions:
        w = 16 + 11 * len(label)
        tone = "disabled" if (key == "dk_save" and state.get("errors")) else \
            "focus" if key == "dk_save" else "normal"
        win._buttons.append(Btn(x, MARGIN + 4, w, 26, key, label, tone=tone))
        x += w + 8


def draw_deck_edit_page(win) -> None:
    fsm = win.fsm
    state = fsm.deck_edit or {}
    if not state:
        return
    top = win.height - TOP_H
    arcade.draw_lrbt_rectangle_filled(0, win.width, 0, top, HUD_PANEL)
    rename = state.get("renaming")
    key_disp = (state["deck_key"] + "▏" + state.get("rename_key", "")
                if rename else state["deck_key"])
    arcade.draw_text("卡组编辑器：%s（%s）" % (key_disp, state.get("faction", "?")),
                     win.width / 2, top - 30, ORDER_ARMED, 18, anchor_x="center")
    if rename:
        arcade.draw_text("改名字态：输入字符+退格编辑，再点『改名』确认"
                         "（小写字母/数字/下划线）", win.width / 2, top - 52,
                         HUD_TEXT, 11, anchor_x="center")
    catalog = getattr(win, "_deck_catalog", ()) or ()
    by_key = {c["card_key"]: c for c in catalog}
    # 左栏：类别页签标题
    arcade.draw_text("类别", MARGIN + 4, top - 26, HUD_TEXT, 12)
    # 中栏：卡池标题
    arcade.draw_text("卡池（%s——点条目加一份）"
                     % _TAB_CN.get(state.get("tab", ""), state.get("tab", "?")),
                     MARGIN + 130, top - 56, HUD_TEXT, 12)
    # 右栏：汇总
    summary = state.get("summary") or {}
    sx = win.width - 300
    arcade.draw_text("当前卡组（±调份数）", sx, top - 56, HUD_TEXT, 12)
    y = win.height - TOP_H - 54
    for card_key, n in list(state.get("cards", ()))[:_MAX_SUM_ROWS]:
        c = by_key.get(card_key, {})
        arcade.draw_text("· %s ×%d（%d分）" % (c.get("name", card_key), n,
                                             c.get("cost", 0) * n),
                         sx + 56, y, HUD_TEXT, 11)
        y -= 26
    # 点数条/配额条
    pm, cm_ = summary.get("points_main", 0), summary.get("cap_main", 1)
    pr, cr = summary.get("points_reserve", 0), summary.get("cap_reserve", 1)
    col_m = DECK_BAD if pm > cm_ else DECK_OK
    col_r = DECK_BAD if pr > cr else DECK_OK
    arcade.draw_text("主力 %d/%d 分" % (pm, cm_), sx, y, col_m, 12)
    arcade.draw_text("预备队 %d/%d 分" % (pr, cr), sx, y - 18, col_r, 12)
    y -= 40
    arcade.draw_text("类别×池配额", sx, y, HUD_TEXT, 11)
    y -= 16
    for key, n in list(summary.get("cat_pool", {}).items())[:6]:
        arcade.draw_text("· %s：%d 份" % (key.replace("×", "·"), n),
                         sx + 6, y, HUD_TEXT, 10)
        y -= 14
    if summary.get("subquota"):
        arcade.draw_text("火支子配额（两池总和）", sx, y, HUD_TEXT, 11)
        y -= 16
        for group, n in summary["subquota"].items():
            arcade.draw_text("· %s：%d 份" % (group, n), sx + 6, y, HUD_TEXT, 10)
            y -= 14
    # 校验错误内联红字（保存禁用联动——布局层 tone 已灰）
    for i, err in enumerate((state.get("errors") or [])[:4]):
        arcade.draw_text("✗ %s" % err[:86], MARGIN + 130, 66 - i * 18,
                         DECK_BAD, 11)
    arcade.draw_text("航空卡不入卡组（独立 %d 空点数池，D038 方案A）；保存=写 "
                     "data/yaml/decks → 就地编译 data/gen/decks → config 页即时可选"
                     % 750, MARGIN + 4, MARGIN + 34, HUD_TEXT, 10)
    arcade.draw_text("Deck Code 分享码后置（本地文件互换=分享面）", MARGIN + 4,
                     MARGIN + 20, (150, 150, 150, 255), 10)
    for btn in win._buttons:
        if btn.key.startswith("dk_"):
            draw_button(btn)


def handle_config_click(win, x, y) -> None:
    """config 页点击语义（卡组选择/编辑卡组入口/KEV 档/开始）。"""
    fsm = win.fsm
    for btn in win._buttons:
        if btn.hit(x, y):
            if btn.key == "deck_edit":
                open_deck_editor(win)
            elif btn.key.startswith("dk_"):
                handle_deck_edit_button(win, btn.key)
            elif btn.key.startswith("deck:"):
                fsm.deck_key = btn.key[5:]
            elif btn.key == "kev_rule":
                fsm.kev_level = "rule"
            elif btn.key == "kev_local":
                fsm.kev_level = "local"
            elif btn.key == "start":
                win._start_game()
            return


# ── 战前配置页（config——GP-01 §5.2 拆分自 shell_window；编辑器入口在本页）──

def layout_config_page(win) -> None:
    """config 页命中域：卡组清单（session.deck_list 泛化）/编辑卡组入口/KEV 档/开始。"""
    cx = win.width / 2
    decks = win.session.deck_list()[:6]
    x, y = cx - 330, 430
    for key in decks:
        label = "卡组：%s" % key
        win._buttons.append(Btn(x, y, 200, 34, "deck:%s" % key, label,
                                tone="focus" if key == win.fsm.deck_key
                                else "normal"))
        x += 210
        if x > cx + 300:
            x, y = cx - 330, y - 40
    win._buttons.append(Btn(cx - 330, 374, 200, 34, "deck_edit",
                            "编辑卡组（新建/改卡）"))
    win._buttons.append(Btn(cx - 330, 330, 152, 34, "kev_rule", "KEV：规则兜底"))
    win._buttons.append(Btn(cx - 162, 330, 152, 34, "kev_local", "KEV：0.5B 本地"))
    win._buttons.append(Btn(cx - 110, 190, 220, 52, "start", "开始部署（Enter）"))


def draw_config_page(win) -> None:
    fsm = win.fsm
    cx = win.width / 2
    arcade.draw_text("SOV_SS 遭遇战 · 战前配置", cx, win.height - 110,
                     HUD_TEXT, 30, anchor_x="center")
    arcade.draw_text("地图：2km 演示图 map_demo_2km.v1（唯一现役·固定）",
                     cx, 496, HUD_TEXT, 14, anchor_x="center")
    arcade.draw_text("对手：KEV（0.5B 本地=MPS 失败自动回退规则兜底）",
                     cx, 474, HUD_TEXT, 12, anchor_x="center")
    cards = win.session.deck_info(fsm.deck_key)
    arcade.draw_text("卡组 %s 现役卡（data/gen/decks）：" % fsm.deck_key,
                     cx + 150, 430, HUD_TEXT, 13)
    for i, c in enumerate(cards[:9]):
        arcade.draw_text("· %s ×%d（%d分）" % (c["name"], c["copies"], c["cost"]),
                         cx + 170, 406 - i * 24, HUD_TEXT, 12)
    for btn in win._buttons:
        armed = (btn.key == "deck:" + fsm.deck_key
                 or (btn.key == "kev_rule" and fsm.kev_level == "rule")
                 or (btn.key == "kev_local" and fsm.kev_level == "local"))
        draw_button(btn, armed=armed)
    arcade.draw_text("开始后：60s 盲部署（600t）→ 实战 → 结算",
                     cx, 120, HUD_TEXT, 13, anchor_x="center")
    x0, y0 = 24, 300
    arcade.draw_text("键位速查（F1=完整面板）", x0, y0, ORDER_ARMED, 13)
    rows = ("左键 选/框选｜右键 移动/盘旋", "A+点 攻击｜T 炮击（参数条）｜F 行军",
            "K+点/画线 空袭｜O 空投｜U 卸载", "X 烟幕｜G 组合｜H 纪律｜N 狙击",
            "飞机 V 高度·B 返航·J 对空·Y 脱离", "Ctrl+1..9 建组｜1..9 取组",
            "SPACE 暂停（下令照收）｜± 调速", "方向键/贴边 平移｜滚轮 缩放")
    for i, r in enumerate(rows):
        arcade.draw_text(r, x0, y0 - 22 - i * 20, HUD_TEXT, 12)
    x0, y0 = 24, 118
    arcade.draw_text("胜利裁决（D031 三级）", x0, y0, ORDER_ARMED, 13)
    for i, r in enumerate(("第一级：占点分", "第二级：剩余单位分值",
                           "第三级：剩余总血量", "目标：中央占点（2km 图心）")):
        arcade.draw_text("· " + r, x0, y0 - 20 - i * 18, HUD_TEXT, 12)


# ── deck_edit 编排（窗口层事件 → 后端裁决 → fsm 态回填——§7 无双轨）──

def open_deck_editor(win) -> None:
    """自 config 进编辑器（卡池目录缓存＋fsm 纯数据态装填＋首检）。"""
    ed = win.session.deck_editor
    deck = ed.load_deck(win.fsm.deck_key)
    win._deck_catalog = ed.catalog()
    first_tab = next((c["category"] for c in win._deck_catalog
                      if c["faction"] == deck["faction"]), "INFANTRY")
    win.fsm.open_deck_edit({"deck_key": deck["deck_key"],
                            "faction": deck["faction"],
                            "cards": deck["cards"], "tab": first_tab,
                            "errors": []})
    deck_revalidate(win)
    win._layout_buttons()                 # 换页即重排命中域（dk_* 按钮就位）


def deck_revalidate(win) -> None:
    """编辑器态→后端校验/汇总回填（同一权威 validate_deck）。"""
    state = win.fsm.deck_edit
    if not state:
        return
    ed = win.session.deck_editor
    state["errors"] = ed.validate(state["faction"], state["cards"])
    state["summary"] = ed.summary(state["cards"], state["faction"])


def handle_deck_edit_button(win, key: str) -> None:
    """dk_* 按钮语义（新建/克隆/改名确认/保存/删除/返回/页签/加减卡）。"""
    fsm, ed = win.fsm, win.session.deck_editor
    state = fsm.deck_edit
    if state is None:
        return
    old_key = state["deck_key"]
    if key.startswith("dk_tab_"):
        fsm.deck_edit_set_tab(key[7:])
    elif key.startswith("dk_add_"):
        fsm.deck_edit_add(key[7:])               # 前缀 7 字符（card_key 含下划线）
        deck_revalidate(win)
    elif key.startswith("dk_inc_"):
        fsm.deck_edit_delta(key[7:], +1)
        deck_revalidate(win)
    elif key.startswith("dk_dec_"):
        fsm.deck_edit_delta(key[7:], -1)
        deck_revalidate(win)
    elif key == "dk_new":
        new_key = ed.new_key()
        fsm.open_deck_edit({"deck_key": new_key, "faction": state["faction"],
                            "cards": [], "tab": state["tab"], "errors": []})
        deck_revalidate(win)
    elif key == "dk_clone":
        new_key = ed.new_key()
        try:
            ed.clone(old_key, new_key)
            deck = ed.load_deck(new_key)
            fsm.open_deck_edit({"deck_key": new_key, "faction": deck["faction"],
                                "cards": deck["cards"], "tab": state["tab"],
                                "errors": []})
            fsm.notify("已克隆为 %s" % new_key)
        except (ValueError, FileNotFoundError) as exc:
            fsm.notify("克隆失败：%s" % exc, tone="error")
        deck_revalidate(win)
    elif key == "dk_rename":
        if state["renaming"]:                  # 确认改名（保存为新键+删旧）
            new_key = state["rename_key"].strip()
            if new_key and new_key != old_key:
                try:
                    ed.save(new_key, state["faction"], state["cards"])
                    if old_key not in ("su_min", "ger_min"):
                        ed.delete(old_key)
                    state["deck_key"] = new_key
                    fsm.deck_key = new_key
                    fsm.notify("已改名 %s" % new_key)
                except ValueError as exc:
                    fsm.notify("改名失败：%s" % exc, tone="error")
        fsm.deck_edit_start_rename()
    elif key == "dk_save":
        if state["errors"]:
            fsm.notify("存在违规条目，保存禁用", tone="error")
        else:
            try:
                ed.save(state["deck_key"], state["faction"], state["cards"])
                fsm.deck_key = state["deck_key"]
                fsm.notify("已保存并编译 %s（config 页即时可选）"
                           % state["deck_key"])
            except ValueError as exc:
                state["errors"] = [str(exc)]
                fsm.notify("保存失败：%s" % exc, tone="error")
    elif key == "dk_delete":
        try:
            ed.delete(state["deck_key"])
            fsm.notify("已删除 %s" % state["deck_key"])
            fsm.close_deck_edit()
        except (ValueError, FileNotFoundError) as exc:
            fsm.notify("删除失败：%s" % exc, tone="error")
    elif key == "dk_back":
        fsm.close_deck_edit()
    win._layout_buttons()
