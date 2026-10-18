"""FE-05 F7 断箭式主菜单：bg_mainmenu 背景＋左列 HOME/PLAY/ARSENAL/SETTINGS
页签＋右区动作钮（btn_primary/btn_generic_36 皮肤，缺图回退纯色按钮）。

结论先行：本模块是主菜单的呈现+命中面——页面态在 shell_fsm（page "menu"＋
menu_tab），跳转语义=menu→config（起局门不动）→settings/deck_edit（既有
入页断言零改）；灰显钮只 toast 不跳页（单人版本口径）。本模块只 import
arcade＋本包 assets/hud_bottom/palette（禁 sovs.sim/sovs.ai——AST 守卫②）。
"""
from __future__ import annotations

import arcade

from . import assets, page_fit
from .hud_bottom import Btn, draw_button
from .palette import BTN_FONT, HUD_TEXT, MARGIN, ORDER_TEXT, TOP_H

# 左列页签（键, 中文标签）——断箭 HOME/PLAY/ARSENAL/SETTINGS 四签
MENU_TABS = (("HOME", "HOME"), ("PLAY", "PLAY"),
             ("ARSENAL", "兵工厂 ARSENAL"), ("SETTINGS", "设置 SETTINGS"))

# 页签动作表：键 → (标签, 样式 primary|generic, 动作, 动作参数)
# 动作：enter=menu→config；toast=灰显提示；quit=关窗；deck=进卡组编辑器；
# settings=进设置页；help=开 F1 帮助（改键说明）。
MENU_ACTIONS = {
    "HOME": (
        ("menu_solo", "单人遭遇战", "primary", "enter", None),
        ("menu_continue", "继续", "disabled", "toast", "继续：暂无进行中对局"),
        ("menu_quit", "退出", "generic", "quit", None),
    ),
    "PLAY": (
        ("menu_play_solo", "遭遇战", "primary", "enter", None),
        ("menu_campaign", "战役", "disabled", "toast", "战役模式未开放（单人版本）"),
        ("menu_multi", "多人", "disabled", "toast", "单人版本未开放"),
    ),
    "ARSENAL": (
        ("menu_deck", "卡组编辑器", "generic", "deck", None),
        ("menu_codex", "单位图鉴", "disabled", "toast", "单位图鉴：后续版本"),
    ),
    "SETTINGS": (
        ("menu_settings", "设置", "generic", "settings", None),
        ("menu_keys", "改键说明", "generic", "help", None),
    ),
}

_TAB_X, _TAB_W, _TAB_H = 48, 210, 36      # 页签列
_TAB_Y0, _TAB_STEP = 176, 44              # 页签自顶排布（距顶 px）
_ACT_X, _ACT_W, _ACT_H = 300, 340, 36     # 动作钮区
_ACT_Y0, _ACT_STEP = 196, 44


def menu_tab_of(win) -> str:
    tab = getattr(win.fsm, "menu_tab", "HOME")
    return tab if tab in dict(MENU_TABS) else "HOME"


def layout_menu_page(win) -> None:
    """主菜单命中域：左列页签（menutab_*）＋当前页签动作钮（menu_*）。
    （R4：设计画布坐标——命中面与绘制同一坐标系，鼠标经 page_fit.to_design。）"""
    y = page_fit.DESIGN_H - TOP_H - _TAB_Y0
    for key, label in MENU_TABS:
        win._buttons.append(Btn(_TAB_X, y, _TAB_W, _TAB_H,
                                "menutab_%s" % key, label,
                                tone="focus" if key == menu_tab_of(win)
                                else "normal"))
        y -= _TAB_STEP
    y = page_fit.DESIGN_H - TOP_H - _ACT_Y0
    for key, label, style, _act, _arg in MENU_ACTIONS[menu_tab_of(win)]:
        win._buttons.append(Btn(_ACT_X, y, _ACT_W, _ACT_H, key, label,
                                tone="disabled" if style == "disabled"
                                else "normal"))
        y -= _ACT_STEP


def _draw_menu_button(btn: Btn, *, style: str, active: bool) -> None:
    """菜单钮：primary/generic/disabled 皮肤（缺图回退 draw_button 纯色）。"""
    skin = {"primary": "btn_primary",
            "disabled": "btn_generic_36_disabled"}.get(style)
    if skin and assets.ui_tex(skin) is not None:
        assets.draw_nine_patch((btn.x0, btn.yb, btn.x1, btn.yt),
                               assets.ui_tex(skin))
    elif style == "generic" and assets.ui_tex(
            "btn_generic_36%s" % ("_selected" if active else "")) is not None:
        assets.draw_nine_patch(
            (btn.x0, btn.yb, btn.x1, btn.yt),
            assets.ui_tex("btn_generic_36%s" % ("_selected" if active
                                                else "")))
    else:
        draw_button(btn, armed=active)
    col = (150, 150, 150, 255) if style == "disabled" else ORDER_TEXT
    arcade.draw_text(btn.label, (btn.x0 + btn.x1) / 2, btn.yb + 11,
                     col, 14, anchor_x="center")


def draw_menu_background(win) -> None:
    """主菜单整页背景（R4：画在 page_fit 相机外——整窗 cover 填满 letterbox）。"""
    bg = assets.bg_tex("bg_mainmenu")
    if bg is not None:
        arcade.draw_texture_rect(bg, arcade.XYWH(win.width / 2,
                                                 win.height / 2,
                                                 win.width, win.height))


def draw_menu_page(win) -> None:
    """主菜单内容绘制（R4：设计画布坐标——页签/动作钮/标题/版本行；
    背景由 draw_menu_background 在相机外整窗铺）。"""
    arcade.draw_text("SOV_SS · 1944 东线遭遇战", MARGIN + 36,
                     page_fit.DESIGN_H - TOP_H - 96, HUD_TEXT, 26)
    arcade.draw_text("单机版（vs KEV）", MARGIN + 40,
                     page_fit.DESIGN_H - TOP_H - 122,
                     (170, 170, 160, 255), 12)
    tab = menu_tab_of(win)
    for btn in win._buttons:
        if btn.key.startswith("menutab_"):
            _draw_menu_button(btn, style="generic",
                              active=btn.key[8:] == tab)
        elif btn.key.startswith("menu_"):
            spec = next((s for s in MENU_ACTIONS[tab] if s[0] == btn.key),
                        None)
            if spec is not None:
                _draw_menu_button(btn, style=spec[2], active=False)
    arcade.draw_text("FE-05 · 断箭 HUD 复刻轮", MARGIN + 4, MARGIN + 8,
                     (150, 150, 150, 255), 11)


def handle_menu_click(win, x: float, y: float) -> None:
    """主菜单点击语义：页签切换 / 动作分发（灰显只 toast）。"""
    fsm = win.fsm
    for btn in win._buttons:
        if not btn.hit(x, y):
            continue
        if btn.key.startswith("menutab_"):
            fsm.menu_tab = btn.key[8:]
            win._layout_buttons()
            return
        spec = next((s for s in MENU_ACTIONS[menu_tab_of(win)]
                     if s[0] == btn.key), None)
        if spec is None:
            return
        _key, _label, style, act, arg = spec
        if style == "disabled":
            fsm.notify(arg, tone="info")
            return
        if act == "enter":
            fsm.open_config()
        elif act == "deck":
            fsm.open_config()
            from .deck_editor_page import open_deck_editor
            open_deck_editor(win)
        elif act == "settings":
            fsm.open_config()
            from .settings_page import open_settings
            open_settings(win)
        elif act == "help":
            fsm.help_open = True
        elif act == "quit":
            win.close()
        return
