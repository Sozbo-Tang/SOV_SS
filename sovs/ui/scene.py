"""战场场景绘制（GP-01 §5.2 拆分自 shell_window）：地图空间图元——纯呈现。

结论先行：网格/占点/烟区/弹丸/单位/飞机（含 §4 富化：机头朝向线/任务标记/
空选区角框）/命令痕迹/部署标记/框选矩形全部收敛在本模块；本模块只 import
arcade＋本包 palette/glyphs/shell_fsm 词面（不 import sovs.sim/sovs.ai——
tests/test_arch_constraints.py ② 守卫），画法参数全部由调用方（shell_window）
自 dict 状态帧取值换算后传入。win 为鸭子（cm_to_px/cam_scale/_viewport_px/
fsm/frame/session——窗口几何面）。
"""
from __future__ import annotations

import math

import arcade

from .glyphs import (draw_aircraft_glyph, draw_objective_glyph,  # noqa: E402
                     draw_projectile_glyph, draw_smoke_glyph, draw_unit_glyph)
from .hud_top import text_width
from .palette import (AIR_FOCUS_MARK, AIR_MARK, ANCHOR_SECTOR, ATTACK_MARK,  # noqa: E402
                      CAM_PAD, FM_MARK, GHOST_MARK, GRID_LINE, HUD_TEXT,
                      MAP_BORDER, SELECT_BOX, SELECT_MARK, SMOKE_MARK,
                      TEAM_COLORS, TRAIL_LINE, TRAIL_MARK, WARN_RED)
from .shell_fsm import STATE_CN

_GRID_STEPS_CM = (1000, 2000, 5000, 10000, 20000, 50000, 100000)

_EDGE_SCROLL_PX = 24                 # 边缘滚动热区宽（px，视口内缘）
_ZOOM_MAX = 2.0


# ── 相机与命中（GP-01 §5.2 拆分自 shell_window——地图空间数学面）──

def viewport_px(win):
    """地图视口（px l,b,r,t）：deploy 左栏与顶栏镶边之间；§11 断箭式重排后无底
    栏带——地图直达底缘（小地图/命令格/选中卡浮于其上，断箭同款）。"""
    from .palette import LEFT_W, MARGIN, TOP_H
    left = LEFT_W if win.fsm.page == "deploy" else MARGIN
    return (left, MARGIN, win.width - MARGIN,
            win.height - TOP_H - MARGIN)


def fit_scale(win) -> float:
    mw, mh = win.frame.get("map_cm", (200000, 100000))
    l, b, r, t = viewport_px(win)
    return min((r - l - 2 * CAM_PAD) / mw, (t - b - 2 * CAM_PAD) / mh)


def min_scale(win) -> float:
    """缩放下限（A8 动态值）：min(0.02, 整图适配×0.8)——修「滚一下就回不到
    全图」的锁视野 bug。"""
    return min(0.02, fit_scale(win) * 0.8)


def fit_camera(win) -> None:
    """整图入视口：相机中心对齐**视口中心**（非窗心——deploy 左栏/上下栏镶边
    下窗心居中会把南缘图幅压进底部命令带，出生锚单位全被遮挡）。"""
    win.cam_scale = fit_scale(win)
    mw, mh = win.frame.get("map_cm", (200000, 100000))
    win.cam_cx, win.cam_cy = mw / 2, mh / 2


def clamp_camera(win) -> None:
    """图幅钳制：视口小于图幅时中心钳在 [−半视口, 图幅+半视口]（可看半屏
    出图找方位，不把镜头漂到无关远区）；放大到超图幅时居中。"""
    mw, mh = win.frame.get("map_cm", (200000, 100000))
    l, b, r, t = viewport_px(win)
    vw_cm = (r - l) / win.cam_scale
    vh_cm = (t - b) / win.cam_scale
    win.cam_cx = (mw / 2 if vw_cm >= mw
                  else min(max(win.cam_cx, -vw_cm / 2), mw + vw_cm / 2))
    win.cam_cy = (mh / 2 if vh_cm >= mh
                  else min(max(win.cam_cy, -vh_cm / 2), mh + vh_cm / 2))


def _viewport_center_px(win):
    l, b, r, t = viewport_px(win)
    return (l + r) / 2, (b + t) / 2


def _cam_rot(win) -> float:
    """视图旋转角（deg，顺时针；MMB+拖拽写点——manual.txt:594「MMB + Move
    Camera rotation」，2026-10-13 终审修复块。2D 顶视下=绕视口中心的视图旋转：
    老窗口/鸭子无槽=0°（无旋转，行为与旧链逐位一致）。"""
    return getattr(win, "cam_rot", 0.0) % 360.0


def cm_to_px(win, x_cm, y_cm):
    """世界 cm → 屏幕 px（绕**视口中心**平移+缩放+旋转；rot=0 与旧轴对齐链
    逐位一致——旋转仅以加法项介入，无旋转路径零行为差）。"""
    cx_px, cy_px = _viewport_center_px(win)
    dx = (x_cm - win.cam_cx) * win.cam_scale
    dy = (y_cm - win.cam_cy) * win.cam_scale
    rot = _cam_rot(win)
    if rot:
        rad = math.radians(rot)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        dx, dy = dx * cos_r - dy * sin_r, dx * sin_r + dy * cos_r
    return (cx_px + dx, cy_px + dy)


def px_to_cm(win, x_px, y_px):
    """cm_to_px 逆变换（点击命中/框选/画线共用——旋转视图下指令坐标仍落世界系）。"""
    cx_px, cy_px = _viewport_center_px(win)
    dx, dy = x_px - cx_px, y_px - cy_px
    rot = _cam_rot(win)
    if rot:
        rad = math.radians(-rot)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        dx, dy = dx * cos_r - dy * sin_r, dx * sin_r + dy * cos_r
    return (int(dx / win.cam_scale + win.cam_cx),
            int(dy / win.cam_scale + win.cam_cy))


def rotate_camera(win, dx_px: float) -> None:
    """MMB 横拖=视图旋转（manual.txt:594——0.4°/px 灵敏度占位可调；只动视角
    不动 cam_cx/cy（旋转绕视口中心，图幅钳制语义不受扰））。"""
    win.cam_rot = (getattr(win, "cam_rot", 0.0) + dx_px * 0.4) % 360.0


def visible_cm_rect(win):
    cx0, cy0 = px_to_cm(win, 0, 0)
    cx1, cy1 = px_to_cm(win, win.width, win.height)
    return cx0, cy0, cx1, cy1


def pan_camera(win, dt: float) -> None:
    """方向键+WASD 平移（P0 键位纠偏块 2026-10-13：WASD 并入——手册 Camera
    Controls「W, A, S, D Camera movement」manual.txt:579-580；方向键保留并存，
    held 集合由窗口层自维护。S 双职（相机下移+停止令）——A 已随攻击移动改 Q
    退役归相机，S=停止为既有战斗令未获拍板不移除，按住 S 两效并存留痕）。"""
    step = 700.0 * dt / max(win.cam_scale, 1e-9)
    dx = dy = 0.0
    held = win._cam_held
    if arcade.key.UP in held or arcade.key.W in held:
        dy += step
    if arcade.key.DOWN in held or arcade.key.S in held:
        dy -= step
    if arcade.key.LEFT in held or arcade.key.A in held:
        dx -= step
    if arcade.key.RIGHT in held or arcade.key.D in held:
        dx += step
    if dx or dy:
        win.cam_cx += dx
        win.cam_cy += dy
        clamp_camera(win)


def edge_scroll(win, dt: float) -> None:
    """边缘滚动（〔研·FE-03〕）：热区=视口内缘 24px；UI 命中优先于镜头。"""
    if win.fsm.page not in ("deploy", "battle") or win._mouse_xy is None:
        return
    mx, my = win._mouse_xy
    l, b, r, t = viewport_px(win)
    if not (l <= mx <= r and b <= my <= t):
        return
    dx = dy = 0.0
    if mx <= l + _EDGE_SCROLL_PX:
        dx = -1.0
    elif mx >= r - _EDGE_SCROLL_PX:
        dx = 1.0
    if my <= b + _EDGE_SCROLL_PX:
        dy = -1.0
    elif my >= t - _EDGE_SCROLL_PX:
        dy = 1.0
    if (not dx and not dy) or win._ui_rect_hit(mx, my):
        return
    step = 900.0 * dt / max(win.cam_scale, 1e-9)
    win.cam_cx += dx * step
    win.cam_cy += dy * step
    clamp_camera(win)


def scroll_zoom(win, x, y, scroll_y) -> None:
    """滚轮缩放（光标锚定；下限=动态整图适配×0.8）。"""
    if win.fsm.page not in ("deploy", "battle"):
        return
    cmx, cmy = px_to_cm(win, x, y)
    factor = 1.25 if scroll_y > 0 else 0.8
    win.cam_scale = max(min_scale(win),
                        min(_ZOOM_MAX, win.cam_scale * factor))
    px, py = cm_to_px(win, cmx, cmy)
    win.cam_cx += (px - x) / win.cam_scale
    win.cam_cy += (py - y) / win.cam_scale
    clamp_camera(win)


def hit_unit(win, x, y, team=None):
    """单位命中（曼哈顿 ≤14px；team='enemy'=非视角队/'own'=视角队）。"""
    view = win.frame.get("view")
    best, best_d = None, 1e9
    for u in win.frame.get("units", ()):
        if team == "enemy" and u["team"] == view:
            continue
        if team == "own" and u["team"] != view:
            continue
        px, py = cm_to_px(win, u["pos_cm"][0], u["pos_cm"][1])
        d = abs(px - x) + abs(py - y)
        if d < best_d:
            best, best_d = u, d
    return best if best_d <= 14 else None


def hit_aircraft(win, x, y):
    """飞机命中（己方视角队，半径 18px——§4 ②段；敌机不进选区）。"""
    view = win.frame.get("view")
    best, best_d = None, 1e9
    for a in win.frame.get("aircraft", ()):
        if a.get("team") != view:
            continue
        px, py = cm_to_px(win, a["pos_cm"][0], a["pos_cm"][1])
        d = abs(px - x) + abs(py - y)
        if d < best_d:
            best, best_d = a, d
    return best if best_d <= 18 else None


def hit_building(win, x, y):
    """建筑命中（U+点楼=下车进楼——§6；帧 buildings 公开面）。"""
    best, best_d = None, 1e9
    for b in win.frame.get("buildings", ()):
        px, py = cm_to_px(win, b["pos_cm"][0], b["pos_cm"][1])
        d = abs(px - x) + abs(py - y)
        if d < best_d:
            best, best_d = b, d
    return best if best_d <= 22 else None

# 命令标记分型（trail kind → (色, 型)——「世界内反馈优先于弹窗」底色）
_TRAIL_STYLE = {
    "move": (TRAIL_MARK, "circle"), "reverse": (TRAIL_MARK, "circle"),
    "march": (TRAIL_MARK, "circle"),
    "attack": (ATTACK_MARK, "target"),
    "fire_mission": (FM_MARK, "barrage"),
    "air_call": (AIR_MARK, "cross"), "air_strike": (AIR_MARK, "cross"),
    "air_airdrop": (AIR_MARK, "cross"), "air_patrol": (AIR_MARK, "circle"),
    "air_move": (AIR_MARK, "circle"), "air_reset": (AIR_MARK, "circle"),
    "air_alt": (AIR_MARK, "circle"), "air_rtb": (AIR_MARK, "circle"),
    "smoke_sprint": (SMOKE_MARK, "smoke"), "smoke": (SMOKE_MARK, "smoke"),
    "stance": (SMOKE_MARK, "circle"),
    # ── P1 机制块（2026-10-13）──
    "ground_rtb": (TRAIL_MARK, "circle"), "laser_designate": (ATTACK_MARK, "target"),
    "radar": (SMOKE_MARK, "circle"), "supply_switch": (SMOKE_MARK, "circle"),
    "buy_supplies": (SMOKE_MARK, "circle"),
    "air_afterburner": (AIR_MARK, "circle"), "air_decoy": (AIR_MARK, "circle"),
}

TASK_MARK_COLOR = (240, 224, 96, 200)      # 任务标记（patrol 圈/strike 十字/airdrop 叉）
AIR_NAME_TEXT = (216, 212, 196, 225)       # 机型名标注（己方飞机旁浅字）

# 炮击任务形态词面（帧 fire_mission.form → 人读名——标记文字标注用）
_FM_FORM_CN = {"point": "定点", "line": "线射", "creep": "徐进"}


def draw_scene(win) -> None:
    """战场（部署/实战/结算底图）：网格+占点+烟+弹+单位+飞机+选区+痕迹。"""
    frame = win.frame
    mw, mh = frame.get("map_cm", (200000, 100000))
    l, b, r, t = win._viewport_px()
    step = next((s for s in _GRID_STEPS_CM if s * win.cam_scale >= 24),
                _GRID_STEPS_CM[-1])
    rot = _cam_rot(win)      # 旋转视图：网格/图幅框按变换后端点画（rot=0 竖平线
                             # 与旧轴对齐画法像素等价——端点画法仅越界段被裁）
    x = step
    while x < mw:
        p0x, p0y = win.cm_to_px(x, 0)
        p1x, p1y = win.cm_to_px(x, mh)
        if max(p0x, p1x) >= l and min(p0x, p1x) <= r:
            arcade.draw_line(p0x, p0y, p1x, p1y, GRID_LINE, 1)
        x += step
    y = step
    while y < mh:
        p0x, p0y = win.cm_to_px(0, y)
        p1x, p1y = win.cm_to_px(mw, y)
        if max(p0y, p1y) >= b and min(p0y, p1y) <= t:
            arcade.draw_line(p0x, p0y, p1x, p1y, GRID_LINE, 1)
        y += step
    for (ax, ay), (bx, by) in zip(
            ((0, 0), (mw, 0), (mw, mh), (0, mh)),
            ((mw, 0), (mw, mh), (0, mh), (0, 0))):
        p0 = win.cm_to_px(ax, ay)
        p1 = win.cm_to_px(bx, by)
        arcade.draw_line(p0[0], p0[1], p1[0], p1[1], MAP_BORDER, 2)
    for o in frame.get("objectives", ()):
        px, py = win.cm_to_px(o["pos_cm"][0], o["pos_cm"][1])
        draw_objective_glyph(px, py, max(4.0, o["radius_cm"] * win.cam_scale),
                             owner=o["owner"])
    for z in frame.get("smoke_zones", ()):
        px, py = win.cm_to_px(z["pos_cm"][0], z["pos_cm"][1])
        draw_smoke_glyph(px, py, max(5.0, z["radius_cm"] * win.cam_scale))
    for p in frame.get("projectiles", ()):
        px, py = win.cm_to_px(p["pos_cm"][0], p["pos_cm"][1])
        draw_projectile_glyph(px, py)
    selected = set(win.fsm.selected)
    selected_air = set(win.fsm.selected_air)
    # 视口剔除（边距=CAM_PAD+2：贴缘图元整画、越界图元不画——与 viewer 同规则）
    for u in frame.get("units", ()):
        px, py = win.cm_to_px(u["pos_cm"][0], u["pos_cm"][1])
        if not (l - CAM_PAD - 2 <= px <= r + CAM_PAD + 2
                and b - CAM_PAD - 2 <= py <= t + CAM_PAD + 2):
            continue
        hp_pct = (u["hp"] * 100 // u["hp_max"]) if u["hp_max"] > 0 else 0
        draw_unit_glyph(px, py, category=u["category"], team=u["team"],
                        hp_pct=hp_pct, suppressed=u["suppressed"],
                        moving=u["moving"], selected=u["id"] in selected)
    for a in frame.get("aircraft", ()):
        px, py = win.cm_to_px(a["pos_cm"][0], a["pos_cm"][1])
        if not (l - CAM_PAD - 2 <= px <= r + CAM_PAD + 2
                and b - CAM_PAD - 2 <= py <= t + CAM_PAD + 2):
            continue
        facing = a.get("facing")
        if facing is not None:
            facing = facing + rot          # 世界朝向+视图旋转（屏幕系机头指向）
        draw_aircraft_glyph(px, py, team=a["team"], alt_tier=a["alt_tier"],
                            spotted=a["spotted"], facing_deg=facing,
                            selected=a["id"] in selected_air)
        if a["id"] in selected_air:            # 空选区角框（黄——与单位白框区分）
            arcade.draw_lrbt_rectangle_outline(px - 16, px + 16, py - 16, py + 16,
                                               AIR_FOCUS_MARK, 2)  # noqa: l,b,r,t
        # 机型名标注（battle.png 复检①二轮）：己方飞机旁浅字标名——空域内
        # 「三角形+虚线圈是什么」一眼可读，与炮击准星/痕迹落点环不再混淆
        if a.get("team") == frame.get("view"):
            arcade.draw_text(str(a.get("name", "")), px + 16, py - 5,
                             AIR_NAME_TEXT, 9)
        draw_task_mark(win, a, px, py)
    draw_trails(win)
    draw_move_paths(win)          # B4：选中单位真实路线（折线/虚线分层）
    draw_fire_mission_marks(win)
    draw_selection_marks(win)


def draw_task_mark(win, a: dict, px: float, py: float) -> None:
    """飞机任务标记（GP-01 §4 ①段 task 摘要的可视面）：patrol=盘旋圈/strike=
    目标十字+run 轴线/airdrop=落点叉——「在空飞机在干什么」一眼可读。
    〔问题6·2026-10-15：三态任务线统一从**飞机当前位置** (px,py) 起绘（strike
    既有 346 行同款）——patrol 补 →圆心连线、airdrop 补 →落点连线（TASK_MARK_
    COLOR 宽 1）：空中路线不再只见图/叉读不出「从机起向哪去」。〕"""
    task = a.get("task")
    if not task:
        return
    kind = task.get("kind")
    if kind == "patrol":
        cx, cy = win.cm_to_px(task["center"][0], task["center"][1])
        arcade.draw_circle_outline(cx, cy, max(6.0, task["radius"]
                                               * win.cam_scale),
                                   TASK_MARK_COLOR, 1)
        arcade.draw_line(px, py, cx, cy, TASK_MARK_COLOR, 1)
    elif kind == "strike":
        tx, ty = win.cm_to_px(task["target"][0], task["target"][1])
        arcade.draw_line(tx - 9, ty, tx + 9, ty, TASK_MARK_COLOR, 2)
        arcade.draw_line(tx, ty - 9, tx, ty + 9, TASK_MARK_COLOR, 2)
        arcade.draw_line(px, py, tx, ty, TASK_MARK_COLOR, 1)
    elif kind == "airdrop":
        dx, dy = win.cm_to_px(task["drop"][0], task["drop"][1])
        arcade.draw_line(dx - 7, dy - 7, dx + 7, dy + 7, TASK_MARK_COLOR, 2)
        arcade.draw_line(dx - 7, dy + 7, dx + 7, dy - 7, TASK_MARK_COLOR, 2)
        arcade.draw_line(px, py, dx, dy, TASK_MARK_COLOR, 1)


def _crosshair(px: float, py: float, r: float) -> None:
    """准星图元（炮击目标标记——圈+四向刻线+中心点，零图片纪律程序化绘制）。"""
    arcade.draw_circle_outline(px, py, r, FM_MARK, 2)
    arcade.draw_line(px - r - 5, py, px - r + 5, py, FM_MARK, 2)
    arcade.draw_line(px + r - 5, py, px + r + 5, py, FM_MARK, 2)
    arcade.draw_line(px, py - r - 5, px, py - r + 5, FM_MARK, 2)
    arcade.draw_line(px, py + r - 5, px, py + r + 5, FM_MARK, 2)
    arcade.draw_circle_filled(px, py, 2, FM_MARK)


def _creep_arrow(x: float, y: float, from_x: float, from_y: float) -> None:
    """徐进方向箭头（线目标末端两撇——指向 from→(x,y) 延伸向）。"""
    ang = math.atan2(y - from_y, x - from_x)
    for da in (2.6, -2.6):
        arcade.draw_line(x, y, x - 11 * math.cos(ang + da),
                         y - 11 * math.sin(ang + da), FM_MARK, 2)


def _mark_label(x: float, y: float, label: str) -> None:
    """标记文字（深底衬+橙字——地图图元之上可读；复检①「无文字标注语义」修复）。"""
    w = text_width(label, 11) + 10
    arcade.draw_lrbt_rectangle_filled(x - w / 2, x + w / 2, y - 4, y + 14,
                                      (10, 12, 10, 205))
    arcade.draw_text(label, x, y, FM_MARK, 11, anchor_x="center")


def draw_fire_mission_marks(win) -> None:
    """地面炮击任务目标标记（GP-01 §3 可视面——battle.png 复检①修复）：
    己方单位带在执行炮击任务＝目标处画准星（POINT）/目标轴线+两端准星（LINE/
    CREEP，CREEP 加徐进箭头）+『炮击·形态』文字标注+炮位→目标细引导线——
    「炮击打向哪里」一眼可辨。数据面=帧 units[].fire_mission 判别摘要
    （state_frame 1.1 加键，仅己方导出——敌方任务目标不进帧，本函数无泄露面）。"""
    view = win.frame.get("view")
    for u in win.frame.get("units", ()):
        fm = u.get("fire_mission")
        if fm is None or (view is not None and u.get("team") != view):
            continue
        ux, uy = win.cm_to_px(u["pos_cm"][0], u["pos_cm"][1])
        # 标签带炮名（复检①二轮）：谁在打、什么形态、什么弹——语义自足；超宽
        # 260px 按 text_width 收「…」（炮名取前 10 字符短名）
        label = "炮击·%s%s·%s" % (_FM_FORM_CN.get(fm.get("form"), fm.get("form")),
                                 "·烟" if fm.get("ammo") == "SMOKE" else "",
                                 str(u.get("name", ""))[:10])
        if text_width(label, 11) > 260:
            label = "炮击·%s%s" % (_FM_FORM_CN.get(fm.get("form"),
                                                  fm.get("form")),
                                   "·烟" if fm.get("ammo") == "SMOKE" else "")
        if fm.get("point") is not None:
            tx, ty = win.cm_to_px(fm["point"][0], fm["point"][1])
            _crosshair(tx, ty, 16)
            _mark_label(tx, ty - 30, label)
            ax, ay = tx, ty
        elif fm.get("line") is not None:
            (x0, y0), (x1, y1) = fm["line"]
            ax, ay = win.cm_to_px(x0, y0)
            bx, by = win.cm_to_px(x1, y1)
            arcade.draw_line(ax, ay, bx, by, FM_MARK, 3)
            if fm.get("form") == "creep":
                _creep_arrow(bx, by, ax, ay)
            _crosshair(ax, ay, 9)
            _crosshair(bx, by, 9)
            _mark_label((ax + bx) / 2, (ay + by) / 2 - 24, label)
        else:
            continue
        arcade.draw_line(ux, uy, ax, ay, (240, 160, 60, 110), 1)


_TRAIL_MARK_TTL = 60           # 移动族痕迹自隐时限（拍——10 拍/秒 ≈ 6s「短暂显示」）
_MOVE_FAMILY = {"move", "reverse", "march",
                "air_move", "air_patrol", "air_alt", "air_rtb"}


def visible_trail_entries(trail, now_tick: int) -> list:
    """痕迹**呈现层**过滤（2026-10-15 用户报障「改了路线后旧途径点还保留/变位」）：
    移动族标记=断箭「短暂显示」语义（basics/调研报告 02 §4：下令后短暂显示、
    Shift 重显）——① 同单位已有**更晚的移动族令**→旧标即时隐去（换路即换标，
    cmd_bus 数据面不动——回放/断言零扰动）；② 超过 _TRAIL_MARK_TTL 自隐。
    战斗类标记（attack/fire_mission/smoke/air_call 等）不受 TTL 约束（任务区
    持续呈现）。纯函数供 draw_trails 与无头锚共用。"""
    latest_move = {}                     # uid → 最新移动族令下标
    for i, tr in enumerate(trail):
        if tr.get("kind") in _MOVE_FAMILY:
            for uid in tr.get("unit_ids", ()):
                latest_move[uid] = i
    out = []
    for i, tr in enumerate(trail):
        if tr.get("kind") in _MOVE_FAMILY:
            if now_tick - tr.get("tick", now_tick) > _TRAIL_MARK_TTL:
                continue                                  # ② 短暂显示：超时自隐
            uids = tr.get("unit_ids", ())
            if uids and all(latest_move.get(uid, i) > i for uid in uids):
                continue                                  # ① 换路即取代旧标
        out.append(tr)
    return out


def draw_trails(win) -> None:
    """已下达命令痕迹（分型标记）：最近数条（单位→落点线+分型落点标记）。
    同文同点标签去重（battle.png 复检②：脚本驾驶每 100t 重发同令，8 条
    move 痕迹曾叠出 3 组重字——同 (label,落点) 只画一次文字）。
    〔B4 修复块（2026-10-13）：move/reverse/march 族且该单位帧内已有真实
    move_path 时跳过「当前位→落点」意图直线——真实绕障折线由 draw_move_paths
    呈现（落点标记与标签保留）；attack/fm 等意图标记不受影响。〕
    〔2026-10-15 排障轮：入口改经 visible_trail_entries 过滤——移动族标记
    短暂显示（换路取代+TTL 自隐），旧标签去重集随文字块一并失去消费面。〕"""
    trail = visible_trail_entries(win.session.cmd.trail[-8:],
                                  win.frame.get("tick", 0))
    pos_by_id = {u["id"]: u["pos_cm"] for u in win.frame.get("units", ())}
    # 〔问题6·2026-10-15：空中令（air_*）trail 的 unit_ids 记的是**飞机 id**——
    # 单位/飞机两套计数器都自 1 起（tick next_unit_id/next_aircraft_id），撞号时
    # 线从错误的地面单位位置起画、不撞号时 src=None 干脆不绘。位置表按 kind
    # 分流：air_* 查飞机帧位（pos_cm=实时值），空中令线恒从本机当前位置起绘；
    # 地面令行为零变（kind 不以 air_ 开头仍查 pos_by_id）。〕
    air_pos_by_id = {a["id"]: a["pos_cm"]
                     for a in win.frame.get("aircraft", ())}
    path_by_id = {u["id"]: (u.get("move_path") or [])
                  for u in win.frame.get("units", ())}
    for tr in trail:
        point = tr.get("point_cm")
        if point is None:
            continue
        kind = tr["kind"]
        color, style = _TRAIL_STYLE.get(kind, (TRAIL_MARK, "circle"))
        px, py = win.cm_to_px(point[0], point[1])
        if style == "barrage":
            arcade.draw_circle_outline(px, py, 26, color, 2)
        elif style == "cross":
            arcade.draw_line(px - 8, py, px + 8, py, color, 2)
            arcade.draw_line(px, py - 8, px, py + 8, color, 2)
        elif style == "smoke":
            arcade.draw_circle_outline(px, py, 12, color, 2)
        elif style == "target":
            arcade.draw_lrbt_rectangle_outline(px - 10, px + 10, py - 10,
                                               py + 10, color, 2)
        else:
            arcade.draw_circle_outline(px, py, 6, color, 2)
        # 2026-10-15 二轮拍板（用户截图反馈）：痕迹只画几何标记——move/NORMAL
        # 类自动状态文字标签整体撤屏（B1 深底衬/截宽/视口翻转折返块随之失去
        # 消费面；命令语义仍由 _TRAIL_STYLE 色/形承载）
        for uid in tr.get("unit_ids", ()):
            src = (air_pos_by_id if kind.startswith("air_")
                   else pos_by_id).get(uid)
            if src is None:
                continue
            if kind in ("move", "reverse", "march") and path_by_id.get(uid):
                continue                  # B4：真实路线折线已呈现（见头注）
            sx, sy = win.cm_to_px(src[0], src[1])
            arcade.draw_line(sx, sy, px, py, color if style != "circle"
                             else TRAIL_LINE, 2)


# ── B4 修复块（2026-10-13）：真实移动路线呈现 ──
# 虚线程序化参数（零图片纪律）：周期 10px，画 6px 跳 4px
_DASH_PERIOD_PX = 10.0
_DASH_ON_PX = 6.0


def _dashed_segment(x0, y0, x1, y1, color, width) -> None:
    """程序化虚线段（每 10px 画 6 跳 4——排队令段与当前执行段的视觉区分）。"""
    length = math.hypot(x1 - x0, y1 - y0)
    if length <= _DASH_ON_PX:
        arcade.draw_line(x0, y0, x1, y1, color, width)
        return
    drawn = 0.0
    while drawn < length:
        seg_end = min(drawn + _DASH_ON_PX, length)
        f0, f1 = drawn / length, seg_end / length
        arcade.draw_line(x0 + (x1 - x0) * f0, y0 + (y1 - y0) * f0,
                         x0 + (x1 - x0) * f1, y0 + (y1 - y0) * f1,
                         color, width)
        drawn += _DASH_PERIOD_PX


def draw_path_polyline(to_px, pos_cm, path, queued, *, line_color,
                       mark_color) -> None:
    """移动路线折线（B4）：当前执行段=实线（pos→逐航点，帧 move_path 每拍 pop
    前段=剩余路线）；排队段=逐令虚线（Shift 排队令航点，段接点 3px 实心点）；
    末端=6px 空心圈（与 draw_trails 落点同款）。to_px=cm→px 变换函数
    （shell=win.cm_to_px；viewer=_to_px——本函数纯绘制无 win 依赖，两窗共用）。"""
    pts = [to_px(pos_cm[0], pos_cm[1])] + [to_px(p[0], p[1]) for p in path]
    for a, b in zip(pts, pts[1:]):                    # 当前段：实线
        arcade.draw_line(a[0], a[1], b[0], b[1], line_color, 2)
    cur = pts[-1]
    drew = len(pts) > 1
    for cmd_path in queued:                           # 排队段：逐令虚线
        arcade.draw_circle_filled(cur[0], cur[1], 1.5, mark_color)  # 段接点
        for wp in cmd_path:
            nxt = to_px(wp[0], wp[1])
            _dashed_segment(cur[0], cur[1], nxt[0], nxt[1], line_color, 2)
            cur = nxt
            drew = True
    if drew:
        arcade.draw_circle_outline(cur[0], cur[1], 6, mark_color, 2)  # 末点


def draw_move_paths(win) -> None:
    """选中己方单位的真实移动路线（B4 修复块 2026-10-13）：帧 units[].move_path
    （A* 绕障剩余航点）+queued（Shift 排队令航点）→ 折线呈现。仅绘**选中**己方
    单位（选区=注意力焦点——basics.txt:59 Selection panel 信息聚焦口径；本作
    拍板「常显选中者」强于断箭「短暂显示+Shift 重显」社区口径（D 级无时长依据，
    manual_silent 留痕）；手册锚 manual.txt:552「SHIFT Queue orders」。"""
    by_id = {u["id"]: u for u in win.frame.get("units", ())}
    for uid in win.fsm.selected:
        u = by_id.get(uid)
        if u is None:
            continue
        path = u.get("move_path") or []
        queued = u.get("queued") or []
        if not path and not queued:
            continue
        draw_path_polyline(win.cm_to_px, u["pos_cm"], path, queued,
                           line_color=TRAIL_LINE, mark_color=TRAIL_MARK)


def draw_selection_marks(win) -> None:
    """进行中框选/画线预览矩形 + 选中单位角框（B2 修复块 2026-10-13：框选
    松手后橡皮筋即消失——不再重画「最近一次框选」残留白框，选中态由角框与
    选中卡承载；SELECT_BOX 仅在拖拽进行中呈现）。"""
    box_p0, box_p1 = win._box_p0, win._box_p1
    if win._line_p0 is not None and win._line_p1 is not None:   # 画线预览（K/T）
        x0, y0 = win._line_p0
        x1, y1 = win._line_p1
        arcade.draw_line(x0, y0, x1, y1, FM_MARK, 3)
        arcade.draw_circle_filled(x0, y0, 4, FM_MARK)
        arcade.draw_circle_filled(x1, y1, 4, FM_MARK)
    elif box_p0 is not None and box_p1 is not None:             # 框选拖拽中
        arcade.draw_lrbt_rectangle_outline(min(box_p0[0], box_p1[0]),
                                           max(box_p0[0], box_p1[0]),
                                           min(box_p0[1], box_p1[1]),
                                           max(box_p0[1], box_p1[1]),
                                           SELECT_BOX, 2)
    for u in win.frame.get("units", ()):
        if u["id"] not in win.fsm.selected:
            continue
        px, py = win.cm_to_px(u["pos_cm"][0], u["pos_cm"][1])
        arcade.draw_lrbt_rectangle_outline(px - 13, px + 13, py - 13, py + 13,
                                           SELECT_MARK, 2)


def draw_margin_mat(win) -> None:
    """边距遮罩：视口外四条带回填不透明底色——场景图元（越界实体/大半径
    烟区圈等）渗出视口即被裁回，HUD 层之下不再出现残条/碎片。"""
    l, b, r, t = win._viewport_px()
    from .palette import BACKGROUND
    arcade.draw_lrbt_rectangle_filled(0, win.width, t, win.height, BACKGROUND)
    arcade.draw_lrbt_rectangle_filled(0, win.width, 0, b, BACKGROUND)
    arcade.draw_lrbt_rectangle_filled(0, l, b, t, BACKGROUND)
    arcade.draw_lrbt_rectangle_filled(r, win.width, b, t, BACKGROUND)


def draw_deploy_markers(win) -> None:
    """部署页主图标记：南缘集结区扇区+『集结区』标签+待出场幽灵队列+每笔放卡
    的目标点标记与锚点→目标虚线（pending 展开意图可视化）+裸奔警告。"""
    frame = win.frame
    mw, mh = frame.get("map_cm", (200000, 100000))
    ax, ay = win.cm_to_px(mw / 2, 0)
    from .palette import LEFT_W
    sector_w = min(30000 * win.cam_scale, (win.width - LEFT_W) / 3)
    arcade.draw_lrbt_rectangle_filled(ax - sector_w / 2, ax + sector_w / 2,
                                      ay - 4, ay + 6000 * win.cam_scale,
                                      ANCHOR_SECTOR)
    arcade.draw_text("集结区", ax, ay + 6000 * win.cam_scale + 6,
                     HUD_TEXT, 11, anchor_x="center")
    pending = list(getattr(win.session, "pending_expands", ()) or ())
    for i, entry in enumerate(pending):
        gx = ax - (len(pending) - 1) * 10 + i * 20
        gy = ay + 28
        arcade.draw_lrbt_rectangle_outline(gx - 7, gx + 7, gy - 7, gy + 7,
                                           GHOST_MARK, 1)
        dest = entry.get("dest") if isinstance(entry, dict) else entry[1]
        px, py = win.cm_to_px(dest[0], dest[1])
        arcade.draw_circle_outline(px, py, 7, GHOST_MARK, 2)
        steps = int(((px - ax) ** 2 + (py - ay) ** 2) ** 0.5 / 14) + 1
        for s in range(1, steps):
            f = s / steps
            arcade.draw_point(ax + (px - ax) * f, ay + (py - ay) * f,
                              GHOST_MARK)
    if pending:
        arcade.draw_text("待出场 %d" % len(pending), ax + 10, ay + 44,
                         HUD_TEXT, 11)
    # 裸奔警告：倒计时 <100t（10s）且场上 0 我方单位——红字前置
    view = frame.get("view")
    mine = [u for u in frame.get("units", ()) if u["team"] == view]
    if win.fsm.page == "deploy" and win.fsm.deploy_ticks_left < 100 \
            and not mine:
        l, b, r, t = win._viewport_px()
        arcade.draw_text("⚠ 未购卡将裸奔进实战（最后 10s 补救窗口）",
                         (l + r) / 2, t - 60, WARN_RED, 16, anchor_x="center")


def lane_points(map_cm) -> list[tuple[int, int]]:
    """部署页三车道（actions.py _deploy_lanes 同式——纯 UI 算术，不 import sim）。"""
    cx = map_cm[0] // 2
    ex, ey = map_cm
    y = ey // 5                                  # 己方（team0=南）向图心推进 1/5
    off = ex // 5
    return [(cx + d * off, y) for d in (-1, 0, 1)]


def air_state_label(a: dict) -> str:
    """飞机状态短标签（选中面板/浮层共用——STATE_CN 词面）。"""
    task = a.get("task")
    task_cn = (STATE_CN.get(task["kind"] + "_task", task["kind"])
               if task else "待命")
    alt = STATE_CN.get(a.get("alt_tier", "mid"), a.get("alt_tier", "?"))
    return "%s·%s·%s" % (STATE_CN.get(a.get("state", "?"), a.get("state", "?")),
                         task_cn, alt)
