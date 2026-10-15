"""炮击/空袭参数条（GP-01 §3 三段式第二段 UI）：浮出底栏上方——纯呈现。

T 待令后弹出（fire_mission 待令态呈现面）：模式 点/线/徐进｜弹药 高爆/烟幕｜
时长 ×1/×2/×3｜齐射 全/半｜徐进速度三档（CREEP 形态）——参数经 fsm.set_fm_param
值域门收口；确认=点地（POINT）/拖拽画线（LINE/CREEP）。K 空袭画线时同位浮出
攻击轴提示。本模块不 import sovs.sim（AST 守卫②）。
"""
from __future__ import annotations

import arcade

from .hud_bottom import Btn, draw_button  # noqa: E402（按钮原语共享）
from .palette import (FM_PANEL_BG, HUD_TEXT,  # noqa: E402
                      ORDER_ARMED, ORDER_TEXT)
from .shell_fsm import CREEP_SPEEDS_CM

_PANEL_H = 52
_PANEL_W = 930


def fm_panel_geom(win):
    """§11 断箭式重排：参数条浮出中下。〔BA 复刻轮 2026-10-15：右下集群
    （命令格→摘要行→状态主卡）占满 y 10..610 后，参数条上移**集群顶之上**
    （y0=主卡顶+12——旧静态 y0=294 与摘要行 298..362 同带互斥红，随集群
    重排迁位；x0 右让编组列、宽 930 CREEP 满配余量不变）。〕"""
    from .palette import MARGIN, MINIMAP_W
    from .selection_panel import air_panel_geom
    x0 = MARGIN + MINIMAP_W + 90
    y0 = air_panel_geom(win)[3] + 12
    return x0, y0, x0 + _PANEL_W, y0 + _PANEL_H


def layout_fm_panel(win) -> None:
    """参数条按钮（仅 fire_mission 待令态浮出；K 画线态提示条无按钮）。"""
    if win.fsm.armed_order != "fire_mission":
        return
    x0, y0, _x1, _y1 = fm_panel_geom(win)
    p = win.fsm.fm_params
    x, y = x0 + 96, y0 + 26
    for form, label in (("POINT", "点目标"), ("LINE", "线形"), ("CREEP", "徐进")):
        win._buttons.append(Btn(x, y, 64, 20, "fm_form_%s" % form, label,
                                tone="focus" if p["form"] == form else "normal"))
        x += 68
    x += 12
    for ammo, label in (("HE", "高爆"), ("SMOKE", "烟幕"),
                        ("PRECISION", "精确")):  # P1 第三弹药位（manual.txt:456-458）
        win._buttons.append(Btn(x, y, 52, 20, "fm_ammo_%s" % ammo, label,
                                tone="focus" if p["ammo"] == ammo else "normal"))
        x += 56
    x += 12
    for mult in (1, 2, 3):
        win._buttons.append(Btn(x, y, 34, 20, "fm_mult_%d" % mult,
                                "×%d" % mult,
                                tone="focus" if p["ammo_mult"] == mult
                                else "normal"))
        x += 38
    x += 12
    for salvo, label in (("FULL", "全齐射"), ("HALF", "半齐射")):
        win._buttons.append(Btn(x, y, 64, 20, "fm_salvo_%s" % salvo, label,
                                tone="focus" if p["salvo"] == salvo
                                else "normal"))
        x += 68
    if p["form"] == "CREEP":                      # 徐进速度三档（仅 CREEP 形态）
        x += 12
        for i, speed in enumerate(CREEP_SPEEDS_CM):
            win._buttons.append(Btn(x, y, 46, 20, "fm_creep_%d" % i,
                                    "%dm/s" % (speed // 10),
                                    tone="focus" if p["creep_idx"] == i
                                    else "normal"))
            x += 50


def draw_fm_panel(win) -> None:
    """参数条绘制（fire_mission 待令态；strike 画线态/drop 画区态给提示条）。"""
    armed = win.fsm.armed_order
    if armed not in ("fire_mission", "strike", "drop"):
        return
    x0, y0, x1, y1 = fm_panel_geom(win)
    arcade.draw_lrbt_rectangle_filled(x0, x1, y0, y1, FM_PANEL_BG)
    arcade.draw_lrbt_rectangle_outline(x0, x1, y0, y1, ORDER_TEXT, 1)
    if armed == "fire_mission":
        p = win.fsm.fm_params
        arcade.draw_text("炮击参数", x0 + 8, y0 + 8, ORDER_ARMED, 13)
        hint = "POINT=点地确认｜LINE/CREEP=拖拽画线（超程自动前移提示先行）"
        arcade.draw_text(hint, x0 + 8, y0 + 2, HUD_TEXT, 10)
        note = ("烟幕弹=落 SmokeZone 遮断（60s——断箭 1.1.1 标准）"
                if p["ammo"] == "SMOKE" else
                "精确弹=吸附最近本队激光位（N 照射——P1 manual.txt:456-458）"
                if p["ammo"] == "PRECISION" else
                "高爆=常规曲射（POINT 校射收束）")
        arcade.draw_text(note, x0 + 96, y0 + 30, HUD_TEXT, 10)
        for btn in win._buttons:
            if btn.key.startswith("fm_"):
                draw_button(btn)
    elif armed == "strike":
        arcade.draw_text("空袭攻击轴：按住左键拖拽画线（位置+朝向）；单击=点目标",
                         x0 + 10, y0 + 16, ORDER_ARMED, 13)
    else:
        arcade.draw_text("空投区：按住左键拖拽画矩形区（投点=区心）；单击=点投",
                         x0 + 10, y0 + 16, ORDER_ARMED, 13)


# ── 画线/画区收笔语义（GP-01 §3/§4——K 空袭攻击轴与 T LINE/CREEP 弹幕线；
#    P0 键位纠偏块 2026-10-13 +O 空投画区（手册拖拽画区同构）+shift 排队透传）──

DRAG_LINE_PX = 14                   # 画线阈值（px——超过即判拖拽画线非点选）


def finish_line_drag(win, p0, p1, *, shift: bool = False) -> bool:
    """画线/画区收笔：超阈值=线令（K 攻击轴/T 弹幕线/O 空投区）/短拖=点令
    （现行为）；待令已撤（ESC/右键）=画线态作废。返回是否消费该收笔。
    shift=命令排队透传（T LINE/CREEP 弹幕入队——手册 SHIFT=Queue orders；
    K/O 飞机令无单位级队列不排队，留痕）。"""
    fsm = win.fsm
    if fsm.armed_order is None:
        return True                          # 已作废（窗口层负责清 _line_*）
    dist = ((p0[0] - p1[0]) ** 2 + (p0[1] - p1[1]) ** 2) ** 0.5
    c0 = win.px_to_cm(p0[0], p0[1])
    c1 = win.px_to_cm(p1[0], p1[1])
    if fsm.armed_order == "strike":
        if dist >= DRAG_LINE_PX:             # K 拖拽=画线攻击轴（§4 ③段）
            fsm.execute_armed_strike_line(c0, c1, win.session.cmd)
        else:                                # 短拖/单击=点目标（现行为）
            fsm.execute_armed_ground(c0, win.session.cmd)
        return True
    if fsm.armed_order == "drop":
        if dist >= DRAG_LINE_PX:             # O 拖拽=画矩形区（区心投放）
            fsm.execute_armed_drop_area(c0, c1, win.session.cmd)
        else:                                # 短拖/单击=点投（现行为）
            fsm.execute_armed_ground(c0, win.session.cmd)
        return True
    if fsm.armed_order == "fire_mission":
        if fsm.fm_params["form"] in ("LINE", "CREEP"):
            if dist >= DRAG_LINE_PX:
                fsm.execute_armed_fm_line(c0, c1, win.session.cmd, shift=shift)
            else:
                fsm.notify("线形/徐进弹幕需按住左键拖拽画线", tone="error")
            return True
        fsm.execute_armed_ground(c0, win.session.cmd, shift=shift)
        return True
    return False                             # 其余待令=回落点选路径（窗口层处理）
