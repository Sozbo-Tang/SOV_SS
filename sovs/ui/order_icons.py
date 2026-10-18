"""右下命令格图标面（断箭级命令菜单呈现层·2026-10-14 用户拍板「集成到断箭的水平」）。

结论先行：本模块是命令格的**图标呈现层**——参照实机 out/refs/ba_shot4.jpg 读图
规格（约 44×44 方形图标格 / 2-3px 缝 / 矢量图标 / 右下热键角 / 角标数字=余量 /
灰显去饱和=禁用 / 悬停 tooltip / 行间细分隔线），键集与三态过滤仍由
hud_bottom._battle_rows + order_filter 提供（数据面不动，只换呈现）。零图片资源
纪律不变：全部图标 arcade 图元程序化绘制（draw_*_icon），键覆盖全命令格行集
（tests 断言行集键 ⊆ 图标表，防新命令漏图标）。本模块只 import arcade＋本包
palette（不 import sovs.sim——AST 守卫②）。
"""
from __future__ import annotations

import math
import re

import arcade

from . import assets
from .palette import (HUD_TEXT, ORDER_ARMED, ORDER_PANEL, ORDER_TEXT)

# ── 热键角字解析：label 形如「雷达(Z)」→ "Z"；无键（图标类命令）→ None ──
_HOTKEY_RE = re.compile(r"（?\(([A-Z])\)）?$|（([A-Z])）$")


def hotkey_of(label: str) -> str | None:
    m = _HOTKEY_RE.search(label)
    if m is None:
        return None
    return m.group(1) or m.group(2)


# ── 图元助手（24px 字形画在 40px 格内——坐标以中心 cx,cy 与尺寸 s 给出）──

def _crosshair(cx, cy, s, col):
    r = s * 0.32
    arcade.draw_circle_outline(cx, cy, r, col, 2)
    arcade.draw_point(cx, cy, col)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        arcade.draw_line(cx + dx * r * 0.7, cy + dy * r * 0.7,
                         cx + dx * r * 1.25, cy + dy * r * 1.25, col, 2)


def _chevrons(cx, cy, s, col, n=2, dx=1):
    for i in range(n):
        x = cx + dx * (i - (n - 1) / 2) * s * 0.22
        arcade.draw_line(x - dx * s * 0.10, cy - s * 0.18,
                         x + dx * s * 0.10, cy, col, 2)
        arcade.draw_line(x + dx * s * 0.10, cy,
                         x - dx * s * 0.10, cy + s * 0.18, col, 2)


def _plane(cx, cy, s, col):
    arcade.draw_triangle_filled(cx, cy, cx - s * 0.34, cy + s * 0.22,
                                cx - s * 0.34, cy - s * 0.10, col)
    arcade.draw_triangle_filled(cx - s * 0.05, cy + s * 0.02,
                                cx - s * 0.30, cy + s * 0.34,
                                cx - s * 0.30, cy + s * 0.10, col)
    arcade.draw_triangle_filled(cx - s * 0.05, cy - s * 0.02,
                                cx - s * 0.30, cy - s * 0.34,
                                cx - s * 0.30, cy - s * 0.10, col)


def _cloud(cx, cy, s, col):
    arcade.draw_circle_outline(cx - s * 0.14, cy, s * 0.16, col, 2)
    arcade.draw_circle_outline(cx + s * 0.10, cy + s * 0.04, s * 0.20, col, 2)
    arcade.draw_circle_outline(cx + s * 0.28, cy - s * 0.04, s * 0.12, col, 2)


def _crate(cx, cy, s, col, w=0.36, h=0.28):
    arcade.draw_lrbt_rectangle_outline(cx - s * w, cx + s * w,
                                       cy - s * h, cy + s * h, col, 2)
    arcade.draw_line(cx - s * w, cy - s * h, cx + s * w, cy + s * h, col, 1)
    arcade.draw_line(cx - s * w, cy + s * h, cx + s * w, cy - s * h, col, 1)


# ── 逐命令图标（签名 draw(cx, cy, s, col)；s=格内字形宽）──

def _i_attack(cx, cy, s, col):
    _crosshair(cx, cy, s, col)


def _i_fm(cx, cy, s, col):
    arcade.draw_line(cx - s * 0.28, cy + s * 0.30, cx + s * 0.10, cy - s * 0.20, col, 2)
    arcade.draw_point(cx + s * 0.10, cy - s * 0.20, col)


def _i_fm_cancel(cx, cy, s, col):
    _i_fm(cx, cy, s, col)
    arcade.draw_line(cx - s * 0.30, cy - s * 0.26, cx + s * 0.30, cy + s * 0.26, col, 2)


def _i_strike(cx, cy, s, col):
    _plane(cx, cy, s * 0.9, col)
    arcade.draw_line(cx + s * 0.10, cy + s * 0.26, cx + s * 0.22, cy + s * 0.38, col, 2)


def _i_drop(cx, cy, s, col):
    arcade.draw_arc_outline(cx, cy + s * 0.18, s * 0.40, s * 0.32, col, 0, 180, 2)
    for t in (-1, 0, 1):
        arcade.draw_line(cx + t * s * 0.18, cy + s * 0.18,
                         cx + t * s * 0.10, cy - s * 0.06, col, 1)
    arcade.draw_lrbt_rectangle_outline(cx - s * 0.12, cx + s * 0.12,
                                       cy - s * 0.30, cy - s * 0.08, col, 2)


def _i_smoke(cx, cy, s, col):
    _cloud(cx, cy, s, col)


def _i_laser(cx, cy, s, col):
    arcade.draw_line(cx - s * 0.30, cy - s * 0.26, cx + s * 0.22, cy + s * 0.22, col, 2)
    arcade.draw_circle_outline(cx + s * 0.22, cy + s * 0.22, s * 0.10, col, 2)


def _i_precision(cx, cy, s, col):
    _crosshair(cx, cy, s * 0.8, col)
    arcade.draw_line(cx - s * 0.04, cy + s * 0.20, cx + s * 0.08, cy, col, 2)
    arcade.draw_line(cx + s * 0.08, cy, cx - s * 0.06, cy - s * 0.20, col, 2)


def _i_radar(cx, cy, s, col):
    for r in (0.14, 0.26, 0.38):
        arcade.draw_arc_outline(cx - s * 0.10, cy, s * r * 2, s * r * 2,
                                col, -55, 55, 2)
    arcade.draw_point(cx - s * 0.10, cy, col)


def _i_stop(cx, cy, s, col):
    arcade.draw_lrbt_rectangle_outline(cx - s * 0.20, cx + s * 0.20,
                                       cy - s * 0.20, cy + s * 0.20, col, 2)


def _i_cancel(cx, cy, s, col):
    arcade.draw_line(cx - s * 0.20, cy - s * 0.20, cx + s * 0.20, cy + s * 0.20, col, 2)
    arcade.draw_line(cx - s * 0.20, cy + s * 0.20, cx + s * 0.20, cy - s * 0.20, col, 2)


def _i_reverse(cx, cy, s, col):
    arcade.draw_line(cx + s * 0.24, cy, cx - s * 0.10, cy, col, 2)
    arcade.draw_line(cx - s * 0.10, cy, cx + s * 0.04, cy - s * 0.16, col, 2)
    arcade.draw_line(cx - s * 0.10, cy, cx + s * 0.04, cy + s * 0.16, col, 2)


def _i_sprint(cx, cy, s, col):
    _chevrons(cx, cy, s, col, 2, 1)


def _i_march(cx, cy, s, col):
    arcade.draw_line(cx, cy + s * 0.28, cx, cy - s * 0.24, col, 2)
    arcade.draw_line(cx, cy - s * 0.24, cx - s * 0.14, cy - s * 0.08, col, 2)
    arcade.draw_line(cx, cy - s * 0.24, cx + s * 0.14, cy - s * 0.08, col, 2)
    for i, x in enumerate((-0.22, 0.0, 0.22)):
        arcade.draw_point(cx + x * s, cy - s * (0.34 + 0.06 * (i % 2)), col)


def _i_stance(cx, cy, s, col):
    arcade.draw_arc_outline(cx, cy, s * 0.40, s * 0.52, col, 0, 180, 2)
    arcade.draw_line(cx - s * 0.20, cy, cx - s * 0.20, cy - s * 0.22, col, 2)
    arcade.draw_line(cx + s * 0.20, cy, cx + s * 0.20, cy - s * 0.22, col, 2)
    arcade.draw_line(cx - s * 0.20, cy - s * 0.22, cx + s * 0.20, cy - s * 0.22, col, 2)


def _i_smoke_sprint(cx, cy, s, col):
    _cloud(cx - s * 0.06, cy + s * 0.12, s * 0.7, col)
    _chevrons(cx, cy - s * 0.14, s * 0.7, col, 2, 1)


def _i_unload(cx, cy, s, col):
    _crate(cx - s * 0.16, cy - s * 0.10, s * 0.8, col, 0.20, 0.16)
    arcade.draw_circle_outline(cx + s * 0.20, cy + s * 0.18, s * 0.07, col, 2)
    arcade.draw_line(cx + s * 0.20, cy + s * 0.11, cx + s * 0.20, cy - s * 0.04, col, 2)
    arcade.draw_line(cx + s * 0.20, cy - s * 0.04, cx + s * 0.10, cy - s * 0.20, col, 2)
    arcade.draw_line(cx + s * 0.20, cy - s * 0.04, cx + s * 0.30, cy - s * 0.20, col, 2)


def _i_mount(cx, cy, s, col):
    _crate(cx + s * 0.16, cy - s * 0.10, s * 0.8, col, 0.20, 0.16)
    arcade.draw_circle_outline(cx - s * 0.20, cy + s * 0.10, s * 0.07, col, 2)
    arcade.draw_line(cx - s * 0.20, cy + s * 0.03, cx - s * 0.20, cy - s * 0.14, col, 2)


def _i_sniper(cx, cy, s, col):
    arcade.draw_circle_outline(cx, cy, s * 0.26, col, 2)
    arcade.draw_line(cx - s * 0.26, cy, cx + s * 0.26, cy, col, 1)
    arcade.draw_line(cx, cy - s * 0.26, cx, cy + s * 0.26, col, 1)


def _i_supply(cx, cy, s, col):
    _crate(cx, cy, s, col)


def _i_ambush(cx, cy, s, col):
    arcade.draw_arc_outline(cx, cy, s * 0.52, s * 0.36, col, 15, 165, 2)
    arcade.draw_circle_filled(cx, cy, s * 0.07, col)


def _i_deploy_gun(cx, cy, s, col):
    arcade.draw_line(cx - s * 0.26, cy - s * 0.10, cx + s * 0.26, cy - s * 0.10, col, 2)
    arcade.draw_line(cx + s * 0.10, cy - s * 0.10, cx + s * 0.10, cy - s * 0.26, col, 2)
    arcade.draw_circle_outline(cx - s * 0.10, cy - s * 0.20, s * 0.09, col, 2)


def _i_pack_gun(cx, cy, s, col):
    _crate(cx, cy + s * 0.10, s * 0.9, col, 0.26, 0.16)
    arcade.draw_line(cx - s * 0.16, cy - s * 0.24, cx + s * 0.16, cy - s * 0.24, col, 2)


def _i_tow(cx, cy, s, col):
    arcade.draw_line(cx - s * 0.28, cy, cx + s * 0.10, cy, col, 2)
    arcade.draw_arc_outline(cx + s * 0.18, cy, s * 0.18, s * 0.24, col, -90, 90, 2)


def _i_untow(cx, cy, s, col):
    _i_tow(cx, cy, s, col)
    arcade.draw_line(cx - s * 0.10, cy - s * 0.24, cx + s * 0.20, cy + s * 0.24, col, 2)


def _i_formation(cx, cy, s, col):
    for dx, dy in ((0, 0.22), (-0.22, -0.14), (0.22, -0.14)):
        arcade.draw_circle_outline(cx + dx * s, cy + dy * s, s * 0.09, col, 2)


def _i_air_alt(cx, cy, s, col):
    _chevrons(cx, cy + s * 0.10, s * 0.8, col, 1, 1)
    _chevrons(cx, cy - s * 0.10, s * 0.8, col, 1, -1)


def _i_air_rtb(cx, cy, s, col):
    _plane(cx + s * 0.06, cy, s * 0.8, col)
    arcade.draw_line(cx - s * 0.30, cy - s * 0.26, cx - s * 0.30, cy + s * 0.10, col, 2)
    arcade.draw_line(cx - s * 0.30, cy + s * 0.10, cx - s * 0.18, cy + s * 0.24, col, 2)
    arcade.draw_line(cx - s * 0.30, cy + s * 0.10, cx - s * 0.42, cy + s * 0.24, col, 2)


def _i_air_engage(cx, cy, s, col):
    _plane(cx - s * 0.08, cy + s * 0.10, s * 0.6, col)
    arcade.draw_circle_outline(cx + s * 0.18, cy - s * 0.12, s * 0.14, col, 2)


def _i_air_disengage(cx, cy, s, col):
    _plane(cx - s * 0.10, cy, s * 0.7, col)
    arcade.draw_line(cx + s * 0.14, cy - s * 0.20, cx + s * 0.34, cy + s * 0.20, col, 2)
    arcade.draw_line(cx + s * 0.14, cy + s * 0.20, cx + s * 0.34, cy - s * 0.20, col, 2)


def _i_air_ab(cx, cy, s, col):
    _chevrons(cx, cy, s, col, 3, 1)
    arcade.draw_point(cx - s * 0.30, cy - s * 0.24, col)


def _i_decoy(cx, cy, s, col):
    for i in range(3):
        a = 90 + i * 120
        x = cx + s * 0.20 * math.cos(math.radians(a))
        y = cy + s * 0.20 * math.sin(math.radians(a))
        arcade.draw_line(cx, cy, x, y, col, 2)


def _i_sup_buy1(cx, cy, s, col):
    _crate(cx, cy + s * 0.06, s * 0.9, col, 0.24, 0.18)
    arcade.draw_point(cx, cy - s * 0.26, col)


def _i_sup_buy4(cx, cy, s, col):
    _crate(cx, cy + s * 0.06, s * 0.9, col, 0.24, 0.18)
    for dx in (-0.12, -0.04, 0.04, 0.12):
        arcade.draw_point(cx + dx * s, cy - s * 0.26, col)


def _i_sup_buymax(cx, cy, s, col):
    _crate(cx, cy + s * 0.06, s * 0.9, col, 0.24, 0.18)
    arcade.draw_line(cx - s * 0.12, cy - s * 0.30, cx + s * 0.12, cy - s * 0.22, col, 2)


def _i_sup_share(cx, cy, s, col):
    _crate(cx - s * 0.14, cy, s * 0.6, col, 0.16, 0.13)
    _crate(cx + s * 0.14, cy, s * 0.6, col, 0.16, 0.13)
    arcade.draw_line(cx - s * 0.02, cy + s * 0.30, cx + s * 0.02, cy - s * 0.30, col, 1)


def _i_sup_heal(cx, cy, s, col):
    arcade.draw_line(cx - s * 0.18, cy, cx + s * 0.18, cy, col, 3)
    arcade.draw_line(cx, cy - s * 0.18, cx, cy + s * 0.18, col, 3)


def _i_sup_repair(cx, cy, s, col):
    arcade.draw_circle_outline(cx + s * 0.10, cy + s * 0.12, s * 0.10, col, 2)
    arcade.draw_line(cx + s * 0.04, cy + s * 0.06, cx - s * 0.24, cy - s * 0.22, col, 2)


def _i_sup_ammo(cx, cy, s, col):
    for dx in (-0.16, 0.0, 0.16):
        arcade.draw_lrbt_rectangle_outline(cx + dx * s - s * 0.05,
                                           cx + dx * s + s * 0.05,
                                           cy - s * 0.20, cy + s * 0.14, col, 1)


def _i_fallback(cx, cy, s, col):
    # 未知键兜底菱形（四线手绘——lrbt 变体无 tilt 参数，实机复现崩溃勘正）
    r = s * 0.20
    pts = ((cx, cy + r), (cx + r, cy), (cx, cy - r), (cx - r, cy))
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        arcade.draw_line(x0, y0, x1, y1, col, 1)


# 键 → 图标绘制函数（新增命令键必须在此登记——tests 覆盖断言防漏）
ICON_FUNCS: dict[str, callable] = {
    "attack": _i_attack, "fm": _i_fm, "fm_cancel": _i_fm_cancel,
    "strike": _i_strike, "drop": _i_drop, "smoke_x": _i_smoke,
    "laser": _i_laser, "precision": _i_precision, "radar": _i_radar,
    "stop": _i_stop, "cancel": _i_cancel, "reverse": _i_reverse,
    "sprint": _i_sprint, "march": _i_march, "stance_h": _i_stance,
    "smoke_sprint": _i_smoke_sprint, "unload": _i_unload, "mount": _i_mount,
    "sniper": _i_sniper, "supply": _i_supply, "ambush": _i_ambush,
    "deploy_gun": _i_deploy_gun, "pack_gun": _i_pack_gun, "tow": _i_tow,
    "untow": _i_untow, "formation": _i_formation,
    "air_alt": _i_air_alt, "air_rtb": _i_air_rtb, "air_engage": _i_air_engage,
    "air_disengage": _i_air_disengage, "air_ab": _i_air_ab, "decoy": _i_decoy,
    "sup_buy1": _i_sup_buy1, "sup_buy4": _i_sup_buy4,
    "sup_buymax": _i_sup_buymax, "sup_share": _i_sup_share,
    "sup_heal": _i_sup_heal, "sup_repair": _i_sup_repair,
    "sup_ammo": _i_sup_ammo,
}

# 悬停 tooltip 一句话（label 自带名称与热键，此为操作说明）
TOOLTIPS: dict[str, str] = {
    "attack": "点敌=集火 / 点地=攻击移动（沿途接战）",
    "fm": "点地或拖线召唤炮击（参数条选弹种与模式）",
    "fm_cancel": "撤销进行中的火力任务",
    "strike": "点目标或拖画攻击轴，空袭沿线投弹",
    "drop": "拖拽画区空投伞兵/补给",
    "smoke_x": "原地施放自卫烟幕遮断视线",
    "laser": "照射敌目标引导精确弹药（断视线失效）",
    "precision": "对激光位发射精确弹药（Shift 可排队）",
    "radar": "开/关雷达——大增视野射程，开机对敌可见",
    "stop": "停止移动与当前行动",
    "cancel": "取消选中单位全部命令",
    "reverse": "倒车移动——车头朝敌不露后装甲",
    "sprint": "短时冲刺（需回充）",
    "march": "沿道路快行军",
    "stance_h": "受击还击纪律（只被打才开火）",
    "smoke_sprint": "烟幕+冲刺+禁火组合突击",
    "unload": "点地卸载 / 点楼进楼；再按 U 就地卸载",
    "mount": "点载具登车",
    "sniper": "狙击观测指定敌目标",
    "supply": "点补给卡车停靠补给",
    "ambush": "伏击姿态（隐蔽+停火）",
    "deploy_gun": "展开火炮进入射击位",
    "pack_gun": "收炮转为行军态",
    "tow": "拖曳火炮（点炮再点车）",
    "untow": "解除拖曳",
    "formation": "切换队形",
    "air_alt": "升高/降低飞行高度（低空隐蔽）",
    "air_rtb": "返航离场并按损退款",
    "air_engage": "接敌空战（对空拦截）",
    "air_disengage": "脱离空战规避",
    "air_ab": "加力燃烧——双倍速双倍油耗",
    "decoy": "投放诱饵弹反制导弹",
    "sup_buy1": "购入 1t 物资", "sup_buy4": "购入 4t 物资",
    "sup_buymax": "按点数购满物资",
    "sup_share": "共享物资堆", "sup_heal": "医疗伤员",
    "sup_repair": "维修载具", "sup_ammo": "补满弹药",
}


def badge_for(win, key: str) -> str | None:
    """角标（余量数字）：烟幕=选区地面单位最小余发；诱饵=选区在空机余发和。"""
    if key == "smoke_x":
        vals = [u.get("smoke_left", 0) for u in win.frame.get("units", ())
                if u["id"] in win.fsm.selected]
        if vals:
            return str(min(vals)) if min(vals) > 0 else "0"
        return None
    if key == "decoy":
        vals = [a.get("decoy_left", 0) for a in win.frame.get("aircraft", ())
                if a["id"] in win.fsm.selected_air]
        if vals:
            return str(sum(vals))
        return None
    return None


# ── 格子绘制（hud_bottom.draw_order_panel 消费——呈现层唯一入口）──

_DISABLED_FILL = (44, 46, 44, 255)
_NORMAL_FILL = (58, 64, 58, 255)
_HOVER_FILL = (74, 80, 74, 255)


def draw_order_tile(btn, *, armed: bool, hovered: bool) -> None:
    """断箭式图标格：底板+图标+热键角+角标；禁用去饱和灰。

    〔FE-05 F4 贴图化（2026-10-17）：底板=cmd_tile 四态九宫格（缺图回退纯色
    原填充）；图标=cmd_<key>.png 32px 居中于 40×40 格（缺图回退 ICON_FUNCS
    矢量）；禁用=灰 tint＋alpha 90；armed=ORDER_ARMED 2px 描边叠加。热键
    角标/draw_badge/draw_tooltip 行为零变。〕"""
    disabled = btn.tone == "disabled"
    tile = (assets.ui_tex("cmd_tile_disabled") if disabled
            else assets.ui_tex("cmd_tile_armed") if armed
            else assets.ui_tex("cmd_tile_hover") if hovered
            else assets.ui_tex("cmd_tile"))
    if tile is not None:
        assets.draw_nine_patch((btn.x0, btn.yb, btn.x1, btn.yt), tile,
                               corner=16)
        if armed:                                   # 待令=橙描边叠加（底砖之上）
            arcade.draw_lrbt_rectangle_outline(btn.x0, btn.x1, btn.yb, btn.yt,
                                               ORDER_ARMED, 2)
    else:
        fill = _DISABLED_FILL if disabled else \
            (_HOVER_FILL if hovered else _NORMAL_FILL)
        if armed:
            fill = (96, 84, 30, 255)
        arcade.draw_lrbt_rectangle_filled(btn.x0, btn.x1, btn.yb, btn.yt, fill)
        arcade.draw_lrbt_rectangle_outline(
            btn.x0, btn.x1, btn.yb, btn.yt,
            ORDER_ARMED if armed else ORDER_TEXT, 2 if armed else 1)
    cx, cy = (btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2
    tex = assets.order_tex(btn.key)
    if tex is not None:                             # 贴图图标 32px 居中
        if disabled:
            arcade.draw_texture_rect(
                tex, arcade.XYWH(cx, cy, 32, 32),
                color=arcade.types.Color(160, 160, 160), alpha=90)
        else:
            arcade.draw_texture_rect(tex, arcade.XYWH(cx, cy, 32, 32))
    else:                                           # 矢量回退（原行为）
        col = (150, 150, 150, 255) if disabled else HUD_TEXT
        ICON_FUNCS.get(btn.key, _i_fallback)(cx, cy, btn.x1 - btn.x0, col)
    hk = hotkey_of(btn.label)
    if hk:
        arcade.draw_text(hk, btn.x1 - 3, btn.yb + 1,
                         ORDER_ARMED if not armed else ORDER_TEXT, 9,
                         anchor_x="right")


def draw_badge(btn, text: str) -> None:
    """右上角标（余量）：橙字小号。"""
    arcade.draw_text(text, btn.x1 - 2, btn.yt - 12, ORDER_ARMED, 10,
                     anchor_x="right")


def draw_tooltip(btn, win) -> None:
    """悬停 tooltip：格上方深底面板「名称(热键) + 一句话」。"""
    tip = TOOLTIPS.get(btn.key)
    if tip is None:
        return
    name = btn.label if btn.label else btn.key
    w = max(arcade.Text(name, 0, 0, arcade.color.WHITE, 13).content_width,
            arcade.Text(tip, 0, 0, arcade.color.WHITE, 11).content_width) + 20
    x0 = min(max(btn.x0 - 4, 4), win.width - w - 4)
    y1 = btn.yt + 8
    arcade.draw_lrbt_rectangle_filled(x0, x0 + w, y1 - 2, y1 + 44, ORDER_PANEL)
    arcade.draw_lrbt_rectangle_outline(x0, x0 + w, y1 - 2, y1 + 44, ORDER_TEXT, 1)
    arcade.draw_text(name, x0 + 10, y1 + 26, HUD_TEXT, 13)
    arcade.draw_text(tip, x0 + 10, y1 + 8, (190, 190, 182, 255), 11)
