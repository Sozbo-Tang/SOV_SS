"""设置页（改键——2026-10-14 设置改键块；manual.txt:91,544-545 运行时承载）。

布局：标题＋两列命令行（COMBAT_KEYS 22 槽——命令中文名＋当前键），行尾 [改]
按钮进入捕获态（下一按键生效）；底=恢复默认/返回。改绑经 keybinds.assign
（保留键黑名单＋占用拒绝），成功即落盘 data/gen/keybinds.json 并经窗口层
_rebuild_key_names 即时生效（含 F1 帮助/速查行的 token 渲染面）。

fsm 面=page "settings"（自 config 进出；战斗键同 config 全拦）；捕获态
（armed 槽名）挂窗口层 win._settings_armed——非纯逻辑态不入 fsm。回放窗
（viewer_window）键位独立不联动（留痕）。本模块不 import sovs.sim（AST 守卫②）。
"""
from __future__ import annotations

import arcade

from . import keybinds
from .hud_bottom import Btn, draw_button
from .palette import HUD_PANEL, HUD_TEXT, MARGIN, ORDER_ARMED, TOP_H

_CMD_CN = {
    "Q": "攻击移动", "S": "停止", "E": "取消", "R": "倒车", "F": "行军",
    "T": "炮击任务", "K": "空袭", "O": "空投", "U": "卸载", "X": "自卫烟幕",
    "G": "组合令", "H": "开火纪律", "L": "狙击观测", "N": "激光照射",
    "P": "精密打击", "M": "登车", "B": "回基地（退款）", "V": "高度",
    "J": "对空开关", "Y": "缠斗脱离", "C": "诱饵", "Z": "冲刺/加力/雷达",
}
_ROWS_PER_COL = 11
_ROW_H = 30
_COL_W = 330


def open_settings(win) -> None:
    """自 config 进设置页（捕获态清零＋命中域重排）。"""
    win.fsm.open_settings()
    win._settings_armed = None
    win._layout_buttons()


def close_settings(win) -> None:
    """返回 config（捕获态随页清零）。"""
    win.fsm.close_settings()
    win._settings_armed = None
    win._layout_buttons()


def layout_settings_page(win) -> None:
    """设置页命中域：两列 [改] 钮＋底部恢复默认/返回。〔armed 态经 getattr
    兜底（2026-10-15 排障轮实测：绕过 open_settings 直接置 page=settings 的
    路径裸读 AttributeError——真实事件循环里即"整页点击/按键无反应"；余处
    本就 getattr，此两行补齐同口径）。〕"""
    mapping = keybinds.display_map()
    armed = getattr(win, "_settings_armed", None)
    top = win.height - TOP_H - 76
    for i, slot in enumerate(_CMD_CN):
        col, row = divmod(i, _ROWS_PER_COL)
        x = MARGIN + 60 + col * (_COL_W + 60)
        y = top - row * _ROW_H
        win._buttons.append(Btn(x + 236, y - 4, 56, 24,
                                "st_rebind_%s" % slot, "改",
                                tone="focus" if armed == slot
                                else "normal"))
    win._buttons.append(Btn(MARGIN + 60, MARGIN + 8, 150, 28, "st_reset",
                            "恢复默认键位"))
    win._buttons.append(Btn(win.width - MARGIN - 210, MARGIN + 8, 150, 28,
                            "st_back", "返回(ESC)",
                            tone="focus" if armed is None
                            else "disabled"))


def draw_settings_page(win) -> None:
    top = win.height - TOP_H
    arcade.draw_lrbt_rectangle_filled(0, win.width, 0, top, HUD_PANEL)
    arcade.draw_text("设置 · 键位（manual：键位可在设置菜单中修改）",
                     win.width / 2, top - 34, ORDER_ARMED, 20,
                     anchor_x="center")
    arcade.draw_text("点行尾〔改〕后按下新键即生效并保存；保留键（WASD 相机/"
                     "方向键/1..9 编组/TAB/ESC/F1/SPACE/±）与已占用键不可绑",
                     win.width / 2, top - 58, HUD_TEXT, 12,
                     anchor_x="center")
    mapping = keybinds.display_map()
    for i, slot in enumerate(_CMD_CN):
        col, row = divmod(i, _ROWS_PER_COL)
        x = MARGIN + 60 + col * (_COL_W + 60)
        y = top - 76 - row * _ROW_H
        if win._settings_armed == slot:
            arcade.draw_text("%s —— 请按新键（ESC 取消）" % _CMD_CN[slot],
                             x, y, ORDER_ARMED, 14)
        else:
            arcade.draw_text("%s（%s）" % (_CMD_CN[slot], mapping[slot]),
                             x, y, HUD_TEXT, 14)
    for btn in win._buttons:
        if btn.key.startswith("st_"):
            draw_button(btn)


def handle_settings_click(win, x: float, y: float) -> None:
    """st_* 按钮语义：改键捕获/恢复默认/返回。"""
    for btn in win._buttons:
        if not btn.hit(x, y):
            continue
        if btn.key.startswith("st_rebind_"):
            win._settings_armed = btn.key[len("st_rebind_"):]
            win._layout_buttons()
        elif btn.key == "st_reset":
            keybinds.reset_all()
            win._settings_armed = None
            getattr(win, "_rebuild_key_names", lambda: None)()
            win.fsm.notify("已恢复默认键位")
            win._layout_buttons()
        elif btn.key == "st_back":
            close_settings(win)
        return


def handle_settings_key(win, key: int) -> None:
    """设置页按键：捕获态=新键入绑；非捕获态=仅 ESC 返回（其余吞掉）。"""
    armed = getattr(win, "_settings_armed", None)
    if key == arcade.key.ESCAPE:
        if armed is not None:
            win._settings_armed = None
            win._layout_buttons()
        else:
            close_settings(win)
        return
    if armed is None:
        return
    ok, msg = keybinds.assign(armed, key)
    win.fsm.notify(msg, tone="info" if ok else "error")
    win._settings_armed = None
    if ok:
        getattr(win, "_rebuild_key_names", lambda: None)()
    win._layout_buttons()
