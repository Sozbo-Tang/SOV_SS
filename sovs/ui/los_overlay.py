"""FE-05 F6 ALT 视线工具：按住 ALT 画视野圈+单位→鼠标视线（可见白实线/
遮拦红虚线+距离标注）；火力任务/空袭画线预览端点被遮挡时红色段+「遮拦」标。

结论先行：本模块是 ALT 视线的**呈现面**——判定数据全部来自
session.los_probe(uid, cm)（app 层鸭子面，缺槽/None 即不画，不崩截图）。
win._los_hold 由 shell_window 的 LALT/RALT 按下/松开分支维护；ESC 分层
取消与切页（选区清空）自然消隐。本模块只 import arcade＋本包 palette
（禁 sovs.sim/sovs.ai——AST 守卫②）。
"""
from __future__ import annotations

import arcade

from .palette import HUD_TEXT, WARN_RED

LOS_VISIBLE = (255, 255, 255, 235)      # 可见=白实线
LOS_BLOCKED = (255, 96, 96, 235)        # 遮拦=红（WARN_RED 同系）
_DASH_PX = 8.0                          # 红虚线周期（画 5 跳 3）


def los_active(win) -> bool:
    """ALT 按住＋对战页＋有地面选区（松开/ESC/切页=选区或旗标清零即消隐）。"""
    return (bool(getattr(win, "_los_hold", False))
            and getattr(win.fsm, "page", None) in ("deploy", "battle")
            and bool(win.fsm.selected))


def _dashed_line(x0, y0, x1, y1, color, width=2) -> None:
    import math
    length = math.hypot(x1 - x0, y1 - y0)
    if length <= _DASH_PX:
        arcade.draw_line(x0, y0, x1, y1, color, width)
        return
    drawn = 0.0
    while drawn < length:
        seg = min(drawn + 5.0, length)
        f0, f1 = drawn / length, seg / length
        arcade.draw_line(x0 + (x1 - x0) * f0, y0 + (y1 - y0) * f0,
                         x0 + (x1 - x0) * f1, y0 + (y1 - y0) * f1,
                         color, width)
        drawn += _DASH_PX


def _dashed_circle(x, y, r, color, segments: int = 24) -> None:
    import math
    if r < 4:
        return
    step = 2 * math.pi / segments
    for i in range(0, segments, 2):                 # 隔弧留白=虚线感
        a0, a1 = i * step, min((i + 1) * step, 2 * math.pi)
        arcade.draw_line(x + r * math.cos(a0), y + r * math.sin(a0),
                         x + r * math.cos(a1), y + r * math.sin(a1),
                         color, 3)                  # R2：1→3（深底上可见度）


def draw_los_overlay(win) -> None:
    """ALT 视线：焦点单位视野圈（虚线）＋单位→鼠标连线＋中点距离(m)。"""
    if not los_active(win):
        return
    mouse = getattr(win, "_mouse_xy", None)
    probe = getattr(win.session, "los_probe", None)
    if mouse is None or probe is None:
        return
    uid = win.fsm.focus_unit if win.fsm.focus_unit is not None \
        else win.fsm.selected[0]
    u = next((x for x in win.frame.get("units", ())
              if x.get("id") == uid), None)
    if u is None:
        return
    cm = win.px_to_cm(mouse[0], mouse[1])
    res = probe(uid, cm)
    if res is None:
        return
    px, py = win.cm_to_px(u["pos_cm"][0], u["pos_cm"][1])
    _dashed_circle(px, py, max(6.0, res["range_cm"] * win.cam_scale),
                   (200, 200, 200, 130))
    mx, my = mouse
    if res.get("visible"):
        arcade.draw_line(px, py, mx, my, LOS_VISIBLE, 2)
    else:
        _dashed_line(px, py, mx, my, LOS_BLOCKED)
    mid = ((px + mx) / 2, (py + my) / 2)
    label = "%dm" % (res["dist_cm"] // 100)
    if not res.get("visible"):
        label += "·遮拦(%s)" % {"terrain": "地形", "smoke": "烟幕",
                                "range": "超程"}.get(res.get("reason"), "?")
    w = 8 * len(label) + 8
    arcade.draw_lrbt_rectangle_filled(mid[0] - w / 2, mid[0] + w / 2,
                                      mid[1] + 4, mid[1] + 18,
                                      (10, 12, 10, 205))
    arcade.draw_text(label, mid[0], mid[1] + 5,
                     HUD_TEXT if res.get("visible") else WARN_RED, 10,
                     anchor_x="center")


def annotate_fm_block(win, end_px) -> None:
    """火力任务/空袭画线预览：端点被遮挡（terrain/smoke）→弹道段红色＋
    端点「遮拦」标（引擎门仍为最终权威——呈现层提示，不拦下令）。"""
    if getattr(win.fsm, "armed_order", None) not in ("fire_mission", "strike"):
        return
    probe = getattr(win.session, "los_probe", None)
    if probe is None or not win.fsm.selected:
        return
    uid = win.fsm.focus_unit if win.fsm.focus_unit is not None \
        else win.fsm.selected[0]
    u = next((x for x in win.frame.get("units", ())
              if x.get("id") == uid), None)
    if u is None:
        return
    cm = win.px_to_cm(end_px[0], end_px[1])
    res = probe(uid, cm)
    if res is None or res.get("visible") or res.get("reason") == "range":
        return                                      # 超程不红显（射程≠光学）
    px, py = win.cm_to_px(u["pos_cm"][0], u["pos_cm"][1])
    _dashed_line(px, py, end_px[0], end_px[1], LOS_BLOCKED, 3)
    arcade.draw_text("遮拦", end_px[0], end_px[1] + 8, WARN_RED, 11,
                     anchor_x="center")
