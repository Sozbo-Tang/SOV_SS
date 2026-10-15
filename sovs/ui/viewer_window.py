"""观战器窗口（FE-T06）：薄 arcade 层——只消费 dict 状态帧与 session 回调。

接线铁律（tests/test_arch_constraints.py 守卫）：本模块**不 import sovs.sim/
sovs.ai**——仿真驱动（Replayer/world_tick/state_frame）由 tools/replay_viewer.py
的 session 胶水持有并经鸭子类型注入（session.frame(view)/advance(n)/seek(t)）；
本模块负责：状态帧→屏幕图元（glyphs/palette 程序化绘制，零图片）、按键/
时间轴交互（PlaybackController 纯逻辑件）、HUD（比分条+tick/相位+时间轴）、
终局结算面板、离屏截帧（snapshot——arcade.get_image 落 PNG，spike §4 写法：
绘制后 flip 前读默认帧缓冲）。

按键（FE-T06 定档）：space=播放/暂停；←/→=逐拍步进（Shift=±10 拍）；
↑/↓ 或 +/-=倍速循环（0.5/1/2/4/8）；1/2/3=蓝/红/裁判视角（裁判走全知帧），
Tab 循环切换；点击/拖动时间轴=seek；esc=退出。
"""
from __future__ import annotations

import arcade

from .glyphs import (draw_aircraft_glyph, draw_objective_glyph,
                     draw_projectile_glyph, draw_smoke_glyph, draw_unit_glyph)
from .palette import (BACKGROUND, DEPLOY_BAND, GRID_LINE, HUD_PANEL, HUD_TEXT,
                      MAP_BORDER, PHASE_COLORS, TEAM_COLORS, TIMELINE_FILL,
                      TIMELINE_TRACK, TRAIL_LINE, TRAIL_MARK)
from .scene import draw_path_polyline
from .timeline import PlaybackController

VIEW_CYCLE: tuple[str, ...] = ("blue", "red", "ref")
VIEW_LABEL: dict[str, str] = {"blue": "BLUE VIEW (fog)", "red": "RED VIEW (fog)",
                              "ref": "REFEREE (omniscient)"}
_GRID_STEPS_CM = (1000, 2000, 5000, 10000, 20000, 50000, 100000)  # 自适应网格档
_TOP_H = 34          # 顶栏高（px）
_BOTTOM_H = 46       # 时间轴带高（px）
_MARGIN = 14
_BLEED_PAD = 20      # 图元出血余量（px）≥ 最大图元半径（飞机高层虚线圈 18）
                     # ——贴边图元完整入视口（FE 视觉自检：北缘单位不再顶栏下挂残条）


class ViewerWindow(arcade.Window):
    """观战主窗口（session 鸭子类型：frame/advance/seek/total/deploy_ticks/view）。"""

    def __init__(self, session, *, width: int = 1280, height: int = 720,
                 visible: bool = True):
        super().__init__(width, height, "SOV_SS 回放观战器 v1（FE-T06）",
                         visible=visible, vsync=False, antialiasing=False,
                         resizable=True)
        self.session = session
        self.ctrl = PlaybackController(session.total, start_tick=session.cursor)
        self.view_key = getattr(session, "view", "ref")
        self.show_hud = True
        self._dragging_timeline = False
        self._refresh()

    # ── session 侧驱动面（胶水层调用）──

    def _refresh(self):
        """按当前游标/视角取帧（现场推导，不预存帧序列）。"""
        self.frame = self.session.frame(self.view_key)

    def set_view(self, view: str):
        if view not in VIEW_LABEL:
            raise ValueError("未知视角 %r（%s）" % (view, list(VIEW_LABEL)))
        self.view_key = view
        self.session.view = view
        self._refresh()

    def snapshot(self, path: str):
        """离屏截帧存 PNG（隐藏窗可写；arcade.get_image 已做像素比换算勿再翻转）。"""
        self.clear(color=BACKGROUND)
        self.render_scene(self.frame, show_hud=self.show_hud)
        arcade.get_image().save(path)

    # ── arcade 事件 ──

    def on_update(self, dt: float):
        moved = self.ctrl.advance(dt)
        if moved > 0:
            reached = self.session.advance(moved)
            self.ctrl.tick = reached            # 同步实际到达拍（末拍夹取）
            self._refresh()

    def on_key_press(self, key, modifiers):
        shift = bool(modifiers & arcade.key.MOD_SHIFT)
        if key == arcade.key.SPACE:
            self.ctrl.toggle()
        elif key == arcade.key.LEFT:
            self._seek_ctrl(self.ctrl.step(-10 if shift else -1))
        elif key == arcade.key.RIGHT:
            self._seek_ctrl(self.ctrl.step(10 if shift else 1))
        elif key in (arcade.key.UP, arcade.key.EQUAL):
            self.ctrl.faster()
        elif key in (arcade.key.DOWN, arcade.key.MINUS):
            self.ctrl.slower()
        elif key == arcade.key.KEY_1:
            self.set_view("blue")
        elif key == arcade.key.KEY_2:
            self.set_view("red")
        elif key == arcade.key.KEY_3:
            self.set_view("ref")
        elif key == arcade.key.TAB:
            self.set_view(VIEW_CYCLE[(VIEW_CYCLE.index(self.view_key) + 1)
                                     % len(VIEW_CYCLE)])
        elif key == arcade.key.ESCAPE:
            self.close()

    def _seek_ctrl(self, tick: int):
        """步进/拖动统一走 seek（胶水层重放推导至目标拍）。"""
        self.session.seek(tick)
        self.ctrl.tick = tick
        self._refresh()

    def _timeline_geom(self):
        """时间轴拖槽 (left, right, y_center, height)。"""
        inset = 64
        left, right = inset, self.width - inset
        return left, right, _BOTTOM_H // 2, 10

    def on_mouse_press(self, x, y, button, modifiers):
        left, right, cy, ch = self._timeline_geom()
        if abs(y - cy) <= ch:
            self._dragging_timeline = True
            self._timeline_seek_x(x)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self._dragging_timeline:
            self._timeline_seek_x(x)

    def on_mouse_release(self, x, y, button, modifiers):
        self._dragging_timeline = False

    def _timeline_seek_x(self, x: float):
        left, right, _cy, _ch = self._timeline_geom()
        frac = max(0.0, min(1.0, (x - left) / max(1.0, right - left)))
        self._seek_ctrl(int(frac * self.session.total))

    def on_draw(self):
        self.clear(color=BACKGROUND)
        self.render_scene(self.frame, show_hud=self.show_hud)

    # ── 场景合成（纯函数式：帧 dict → 图元）──

    def _geo(self):
        """地图视口 (left, bottom, right, top) 与 cm→px 变换。

        fit 两侧各留 _BLEED_PAD 图元出血余量：贴地图边的单位/飞机字形
        （半径最大 18px）完整落在视口内，不再溢进顶栏/时间轴边距带。
        """
        left, bottom = _MARGIN, _BOTTOM_H + _MARGIN
        right, top = self.width - _MARGIN, self.height - _TOP_H - _MARGIN
        mw, mh = self.frame.get("map_cm", (200000, 100000))
        vw, vh = max(1, right - left - 2 * _BLEED_PAD), \
            max(1, top - bottom - 2 * _BLEED_PAD)
        scale = min(vw / mw, vh / mh)
        ox = left + _BLEED_PAD + (right - left - 2 * _BLEED_PAD - mw * scale) / 2
        oy = bottom + _BLEED_PAD + (top - bottom - 2 * _BLEED_PAD - mh * scale) / 2
        return left, bottom, right, top, ox, oy, scale

    def _to_px(self, x_cm: int, y_cm: int):
        _l, _b, _r, _t, ox, oy, s = self._geo()
        return ox + x_cm * s, oy + y_cm * s

    def render_scene(self, frame: dict, *, show_hud: bool = True):
        left, bottom, right, top, _ox, _oy, scale = self._geo()
        self._draw_map(frame, scale)
        for o in frame.get("objectives", ()):
            px, py = self._to_px(o["pos_cm"][0], o["pos_cm"][1])
            draw_objective_glyph(px, py, max(4.0, o["radius_cm"] * scale),
                                 owner=o["owner"])
        for z in frame.get("smoke_zones", ()):
            px, py = self._to_px(z["pos_cm"][0], z["pos_cm"][1])
            draw_smoke_glyph(px, py, max(5.0, z["radius_cm"] * scale))
        for p in frame.get("projectiles", ()):
            px, py = self._to_px(p["pos_cm"][0], p["pos_cm"][1])
            draw_projectile_glyph(px, py)
        # 图幅剔除（定幅视口=图幅：图内单位恒在 _BLEED_PAD 余量内整画；
        # 被推挤出图幅的实体（实测终局帧 pos y_cm>map 高 4m+）不画——否则其
        # 字形跨在视口上缘，遮罩裁后半截残边即顶栏下挂条类瑕疵的换形态复发）
        mw_c, mh_c = frame.get("map_cm", (200000, 100000))
        for u in frame.get("units", ()):
            if not (0 <= u["pos_cm"][0] <= mw_c and 0 <= u["pos_cm"][1] <= mh_c):
                continue
            px, py = self._to_px(u["pos_cm"][0], u["pos_cm"][1])
            hp_pct = (u["hp"] * 100 // u["hp_max"]) if u["hp_max"] > 0 else 0
            draw_unit_glyph(px, py, category=u["category"], team=u["team"],
                            hp_pct=hp_pct, suppressed=u["suppressed"],
                            moving=u["moving"],
                            facing_deg=u.get("facing_deg"))   # 未来槽位（帧 v1 无）
        for a in frame.get("aircraft", ()):
            if not (0 <= a["pos_cm"][0] <= mw_c and 0 <= a["pos_cm"][1] <= mh_c):
                continue
            px, py = self._to_px(a["pos_cm"][0], a["pos_cm"][1])
            draw_aircraft_glyph(px, py, team=a["team"], alt_tier=a["alt_tier"],
                                spotted=a["spotted"],
                                facing_deg=a.get("facing"))   # 帧 1.1 机头向
            self._draw_air_task_mark(a, px, py)
        self._draw_move_paths(frame)
        self._draw_margin_mat(left, bottom, right, top)
        if show_hud:
            self._draw_top_bar(frame)
            self._draw_timeline(frame)
            if frame.get("result") is not None:
                self._draw_settle_panel(frame["result"])

    _TASK_MARK = (240, 224, 96, 200)      # 任务标记色（patrol 圈/strike 十字/airdrop 叉）

    def _draw_move_paths(self, frame: dict):
        """B4 修复块（2026-10-13）：地面单位移动路线（帧 units[].move_path/
        queued——实线当前段+虚线排队段，scene.draw_path_polyline 同源画法）。
        视角语义天然成立：蓝/红视角帧敌方条目恒 []（移动意图=私有情报），
        仅本方折线入画；裁判全知帧（view=None）双方全画。观战器无选区概念
        ——在路线者全画（逐拍步进可见前段随推进缩短=pop 语义）。"""
        for u in frame.get("units", ()):
            path = u.get("move_path") or []
            queued = u.get("queued") or []
            if not path and not queued:
                continue
            draw_path_polyline(self._to_px, u["pos_cm"], path, queued,
                               line_color=TRAIL_LINE, mark_color=TRAIL_MARK)

    def _draw_air_task_mark(self, a: dict, px: float, py: float):
        """飞机任务标记（GP-01 §4 ①段帧 1.1 task 摘要——观战器同步渲染）：
        patrol=盘旋圈/strike=目标十字/airdrop=落点叉——「这架飞机在干什么」。"""
        task = a.get("task")
        if not task:
            return
        kind = task.get("kind")
        col = self._TASK_MARK
        if kind == "patrol":
            cx, cy = self._to_px(task["center"][0], task["center"][1])
            arcade.draw_circle_outline(cx, cy, max(6.0, task["radius"] * self._geo()[6]),
                                       col, 1)
        elif kind == "strike":
            tx, ty = self._to_px(task["target"][0], task["target"][1])
            arcade.draw_line(tx - 9, ty, tx + 9, ty, col, 2)
            arcade.draw_line(tx, ty - 9, tx, ty + 9, col, 2)
            arcade.draw_line(px, py, tx, ty, col, 1)
        elif kind == "airdrop":
            dx, dy = self._to_px(task["drop"][0], task["drop"][1])
            arcade.draw_line(dx - 7, dy - 7, dx + 7, dy + 7, col, 2)
            arcade.draw_line(dx - 7, dy + 7, dx + 7, dy - 7, col, 2)

    def _draw_margin_mat(self, left, bottom, right, top):
        """边距遮罩：视口外四条带回填不透明底色——场景图元（含越界实体，如
        被推出图幅北缘的单位）渗入 HUD 边距带即被裁回，杜绝「顶栏下沿挂 2px
        残条」类层叠瑕疵（场景只在视口内呈现，HUD 恒净）。"""
        arcade.draw_lrbt_rectangle_filled(0, self.width, top, self.height,
                                          BACKGROUND)
        arcade.draw_lrbt_rectangle_filled(0, self.width, 0, bottom, BACKGROUND)
        arcade.draw_lrbt_rectangle_filled(0, left, bottom, top, BACKGROUND)
        arcade.draw_lrbt_rectangle_filled(right, self.width, bottom, top,
                                          BACKGROUND)

    def _draw_map(self, frame: dict, scale: float):
        mw, mh = frame.get("map_cm", (200000, 100000))
        left, bottom, right, top, _ox, _oy, _s = self._geo()
        # v1 无地形层（回放 map_key='none'）——旷野底色+网格最简版；瓦片着色
        # （路/林/废墟）待挂图场景接 map_loader 数据（未来槽位，palette.TEXTURE_SLOTS）
        step = next((s for s in _GRID_STEPS_CM if s * scale >= 24), _GRID_STEPS_CM[-1])
        x = step
        while x < mw:
            px, _ = self._to_px(x, 0)
            arcade.draw_line(px, bottom, px, top, GRID_LINE, 1)
            x += step
        y = step
        while y < mh:
            _, py = self._to_px(0, y)
            arcade.draw_line(left, py, right, py, GRID_LINE, 1)
            y += step
        arcade.draw_lrbt_rectangle_outline(left, right, bottom, top,
                                           MAP_BORDER, 2)

    def _draw_top_bar(self, frame: dict):
        arcade.draw_lrbt_rectangle_filled(0, self.width, self.height - _TOP_H,
                                          self.height, HUD_PANEL)
        phase = str(frame.get("phase", "?"))
        col = PHASE_COLORS.get(phase, HUD_TEXT)
        total = self.session.total
        arcade.draw_text("t %d/%d" % (self.ctrl.tick, total), 10,
                         self.height - _TOP_H + 9, HUD_TEXT, 13)
        arcade.draw_text(phase.upper(), 180, self.height - _TOP_H + 9, col, 13)
        state = ">>" if self.ctrl.playing else "||"
        arcade.draw_text("%s x%g  %s" % (state, self.ctrl.speed,
                                         VIEW_LABEL[self.view_key]), 280,
                         self.height - _TOP_H + 9, HUD_TEXT, 13)
        # 比分条：占点归属计数（红-蓝）+可见玩家积分
        objs = frame.get("objectives", ())
        red = sum(1 for o in objs if o["owner"] == 0)
        blue = sum(1 for o in objs if o["owner"] == 1)
        pts_r = pts_b = None
        for p in frame.get("players", ()):
            if p["team"] == 0:
                pts_r = p["points"]
            elif p["team"] == 1:
                pts_b = p["points"]
        pts = "pts R%s/B%s" % (
            "?" if pts_r is None else pts_r, "?" if pts_b is None else pts_b)
        score = "OBJ %d-%d  %s  %s" % (red, blue, pts, _units_label(frame))
        arcade.draw_text(score, self.width - 10, self.height - _TOP_H + 9,
                         HUD_TEXT, 13, anchor_x="right")

    def _draw_timeline(self, frame: dict):
        arcade.draw_lrbt_rectangle_filled(0, self.width, 0, _BOTTOM_H, HUD_PANEL)
        left, right, cy, ch = self._timeline_geom()
        arcade.draw_lrbt_rectangle_filled(left, right, cy - ch, cy + ch,
                                          TIMELINE_TRACK)
        # 盲部署段底色（deploy_ticks 由 session 自回放头携带）
        deploy = int(getattr(self.session, "deploy_ticks", 0))
        total = max(1, self.session.total)
        dw = (right - left) * min(deploy, total) / total
        if dw > 0:
            arcade.draw_lrbt_rectangle_filled(left, left + dw, cy - ch, cy + ch,
                                              DEPLOY_BAND)
        frac = self.ctrl.tick / total
        fw = (right - left) * frac
        if fw > 0:
            arcade.draw_lrbt_rectangle_filled(left, left + fw, cy - ch, cy + ch,
                                              TIMELINE_FILL)
        arcade.draw_point(left + fw, cy, arcade.color.WHITE)
        arcade.draw_text("SPACE=play/pause  ←/→=step(Shift=10t)  1/2/3=blue/red/"
                         "ref  Tab=cycle  +/-=speed  drag=seek  ESC=quit",
                         self.width // 2, 4, HUD_TEXT, 10, anchor_x="center")
        # 占点比分随时间轴同行（验收字面：底部时间轴条显示当前进度与占点比分）
        objs = frame.get("objectives", ())
        red = sum(1 for o in objs if o["owner"] == 0)
        blue = sum(1 for o in objs if o["owner"] == 1)
        arcade.draw_text("OBJ %d-%d" % (red, blue), self.width - 10, 4, HUD_TEXT,
                         10, anchor_x="right")

    def _draw_settle_panel(self, result: dict):
        """终局结算面板（result 三级证据：占点分→剩余单位分值→剩余总血量）。"""
        w, h = 460, 190
        x0, y0 = (self.width - w) // 2, (self.height - h) // 2
        arcade.draw_lrbt_rectangle_filled(x0, x0 + w, y0, y0 + h, (10, 12, 10, 235))
        arcade.draw_lrbt_rectangle_outline(x0, x0 + w, y0, y0 + h,
                                           arcade.color.WHITE, 2)
        winner = result.get("winner")
        title = "DRAW" if winner is None else "%s WINS" % (
            "RED" if winner == 0 else "BLUE")
        tcol = HUD_TEXT if winner is None else TEAM_COLORS[winner]
        arcade.draw_text("== SETTLEMENT: %s ==" % title, self.width // 2,
                         y0 + h - 34, tcol, 20, anchor_x="center")
        oc, us, ht = (result.get("obj_counts"), result.get("unit_scores"),
                      result.get("hp_totals"))

        def _row(label, vals, yy):
            arcade.draw_text(label, x0 + 28, yy, HUD_TEXT, 12)
            arcade.draw_text("R %-8s B %-8s" % (
                "?" if not vals else vals[0], "?" if not vals else vals[1]),
                x0 + 250, yy, HUD_TEXT, 12)
        _row("objectives (red-blue)", oc, y0 + h - 70)
        _row("unit scores", us, y0 + h - 102)
        _row("hp totals", ht, y0 + h - 134)


def _units_label(frame: dict) -> str:
    """可见单位/飞机计数（迷雾视角直观差异——蓝/红视角看不到未侦察敌军）。"""
    return "vis u%d a%d" % (len(frame.get("units", ())),
                            len(frame.get("aircraft", ())))
