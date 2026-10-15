"""可玩壳窗口（FE-T07 → GP-01 §5.2 瘦壳化）：薄 arcade 层——四页状态机的呈现与输入。

结论先行：本模块是 arcade 薄壳（目标 <500 行），只消费 dict 状态帧与
session/cmd_bus 回调（鸭子类型注入——接线铁律 tests/test_arch_constraints.py ②：
本模块不 import sovs.sim/sovs.ai）；页面流转/选区双通道/编组/待令/炮击参数态/
页面门/toast/退出确认由 sovs/ui/shell_fsm.py 纯逻辑承载；绘制与页面语义拆分至
scene（战场）/hud_top（顶栏·浮层·结算）/hud_bottom（底栏四行分组带·面板语义）/
minimap/selection_panel（右侧常驻）/fm_panel（炮击参数条）/deck_editor_page
（战前两页：config＋卡组编辑器）；仿真驱动在 sovs/app/session.py。

session 鸭子面（sovs/app/session.SkirmishSession 实现）：frame/advance/cmd/
total_ticks/world_tick_count/air_roster/deck_info/deck_list/card_cost/
pending_expands/queue_expand/new_game/deck_editor/cooldown_labels。

键位（GP-01 §4/§3/§6 全集＋P0 键位纠偏块 2026-10-13 手册对齐——证据三档
溯源见 shell_fsm 头注与 docs/FE-03；手册 HOTKEYS out/refs/manual.txt:547-580）：
  SPACE=暂停  +/-=调速  方向键/WASD=平移（并存）  贴边=边缘滚动  滚轮=缩放
  左键=点选（单位∪飞机）/框选/Shift 点己方=加减选/点空地清选区
  右键=移动（空选区=盘旋待命 CAP；Shift+右键=追加路径点/直飞航路）
  Q/S/E/R/F 待令族（Q=攻击移动——手册 A→Q 纠偏，A 退役归相机）
  T 炮击三段式（参数条+点地/画线）  K 空袭（点/画攻击轴）
  O 空投（按住左键拖拽画区=区心投/单击点投）  X 烟幕  G 组合  H 纪律
  U 卸载（点地/点楼；再按 U=就地立即卸载——手册双击语义）  N 狙击
  Shift+待令确认=命令入队排队（移动/攻击/炮击/卸载四族；不清待令续令）
  飞机 V/B(不可逆)/J/Y
  Ctrl+1..9=建组（单位∪飞机二元组） 1..9=取组  TAB=双通道子选  F1=帮助
  ESC=分层取消  config 页：Enter 开始/1·2 卡组/3 KEV 档/『编辑卡组』→deck_edit
  （本阶段零图片资源——一切视觉元素程序化绘制 glyphs/palette 矢量图元）
"""
from __future__ import annotations

import arcade

from . import keybinds
from .deck_editor_page import (draw_config_page, draw_deck_edit_page,  # noqa: E402
                               handle_config_click, layout_config_page,
                               layout_deck_edit_page)
from .fm_panel import draw_fm_panel, finish_line_drag, layout_fm_panel  # noqa: E402
from .hud_bottom import (Btn, draw_deploy_panel,  # noqa: E402
                         draw_group_bar, draw_order_panel,
                         handle_confirm_purchase, handle_panel_button,
                         layout_battle_buttons, layout_deploy_panel,
                         layout_group_bar)
from .hud_top import (draw_command_stats, draw_exit_confirm,  # noqa: E402
                      draw_help_overlay, draw_settle_panel, draw_toasts,
                      draw_top_bar, flow_positions, text_width)
from .minimap import draw_minimap, minimap_geom, minimap_to_cm  # noqa: E402
from .palette import BACKGROUND, TOP_SEG_GAP  # noqa: E402
from .settings_page import (draw_settings_page,  # noqa: E402
                            handle_settings_click, handle_settings_key,
                            layout_settings_page)
from .scene import draw_deploy_markers, draw_margin_mat, draw_scene  # noqa: E402
from . import scene  # noqa: E402（相机/命中数学面——薄委托）
from .selection_panel import (draw_selection_panel,  # noqa: E402
                              layout_selection_panel, panel_geom)
from .shell_fsm import ShellFsm  # noqa: E402
from .timeline import PlaybackController  # noqa: E402

# 顶栏流式量尺再出口（tests/test_shell_window 既有导入面）
_TOP_SEG_GAP = TOP_SEG_GAP
_flow_positions = flow_positions
_text_width = text_width

_SPEED_STEPS = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)   # 调速档（13200t 实战 16x 缓解）


class ShellWindow(arcade.Window):
    """可玩壳主窗（config/deck_edit/deploy/battle/settle；session 鸭子面见头注）。"""

    def __init__(self, session, *, width: int = 1280, height: int = 800,
                 visible: bool = True):
        super().__init__(width, height, "SOV_SS 遭遇战（FE-T07 可玩壳）",
                         visible=visible, vsync=False, antialiasing=False,
                         resizable=True)
        self.session = session
        self.fsm = ShellFsm()
        self.ctrl = PlaybackController(session.total_ticks, speeds=_SPEED_STEPS)
        self.show_hud = True
        self.cam_scale = 1.0
        self.cam_cx = 0.0
        self.cam_cy = 0.0
        self.cam_rot = 0.0            # 视图旋转角（MMB+拖拽——manual.txt:594，
                                      # 2026-10-13 终审修复块；0=北向上轴对齐）
        # 交互态（框选松手即清拖拽角点——橡皮筋不留痕；选中态由单位角框
        # （scene.draw_selection_marks）与选中卡承载，B2 修复块 2026-10-13）
        self._box_p0 = None            # 框选拖拽起点（px）
        self._box_p1 = None
        self._line_p0 = None           # 画线拖拽起点（px——K/T 待令画线态）
        self._line_p1 = None
        self._buttons: list[Btn] = []
        self._cam_held: set = set()
        self._mmb_drag = False        # MMB 旋转拖拽在途（中键按下期间）
        self._mouse_xy: tuple[float, float] | None = None
        self._fitted_page: str | None = None
        self._deck_catalog: list[dict] = []      # 编辑器卡池目录（deck_edit 页缓存）
        self.refresh()

    # ── session 侧驱动面 ──

    def refresh(self):
        self.frame = self.session.frame()
        self.fsm.on_frame(self.frame)
        if self.fsm.page != self._fitted_page:
            self._camera_fit()                     # 换页=视口镶边变化→整图重适配
            self._fitted_page = self.fsm.page
        if self.frame.get("phase") == "settle":
            self.ctrl.pause()
        self._layout_buttons()

    def snapshot(self, path: str):
        self.clear(color=BACKGROUND)
        self.render_page()
        arcade.get_image().save(path)

    # ── 相机（地图空间数学在 scene.py——本类薄委托保既有调用面）──

    def _viewport_px(self):
        return scene.viewport_px(self)

    def _fit_scale(self) -> float:
        return scene.fit_scale(self)

    def _min_scale(self) -> float:
        return scene.min_scale(self)

    def _camera_fit(self):
        scene.fit_camera(self)

    def _clamp_camera(self):
        scene.clamp_camera(self)

    def cm_to_px(self, x_cm, y_cm):
        return scene.cm_to_px(self, x_cm, y_cm)

    def px_to_cm(self, x_px, y_px):
        return scene.px_to_cm(self, x_px, y_px)

    def _visible_cm_rect(self):
        return scene.visible_cm_rect(self)

    # ── 选区/浮层 API（交互与测试/截屏门禁同入口）──

    def select_box_px(self, x0, y0, x1, y1):
        c0, c1 = self.px_to_cm(x0, y0), self.px_to_cm(x1, y1)
        self.fsm.box_select(c0, c1)
        # B2（2026-10-13）：不再记录残留白框——框选松手即由选中态（单位角框+
        # 选中条）接管呈现；本 API 仅保留框选语义（screenshot 消费）
        # 〔2026-10-15 二轮拍板：点击单位浮层（show_unit_info/_info_uid 链）
        # 整体撤除——底中只留选中长条，血量/弹药明细不再常驻屏〕

    @property
    def _armed_purchase(self):
        return self.fsm.armed_purchase

    # ── arcade 事件 ──

    def on_update(self, dt: float):
        scene.pan_camera(self, dt)
        scene.edge_scroll(self, dt)
        self.fsm.pump_notifications(dt)
        if self.fsm.page in ("deploy", "battle"):
            moved = self.ctrl.advance(dt)
            if moved > 0:
                self.session.advance(moved)
                self.ctrl.tick = self.session.world_tick_count
                self.refresh()

    def on_key_press(self, key, modifiers):
        fsm, page = self.fsm, self.fsm.page
        ctrl = bool(modifiers & arcade.key.MOD_CTRL)
        shift = bool(modifiers & arcade.key.MOD_SHIFT)
        if key in (arcade.key.UP, arcade.key.DOWN, arcade.key.LEFT,
                   arcade.key.RIGHT):
            self._cam_held.add(key)
            return
        if key in (arcade.key.W, arcade.key.A, arcade.key.S, arcade.key.D):
            # P0 键位纠偏块（2026-10-13）：WASD=相机平移（手册 Camera Controls
            # 「W, A, S, D Camera movement」manual.txt:579-580；方向键保留并存）。
            # 不 return：S 仍落 fsm 分发（S=停止为既有战斗令，未获拍板不移除——
            # 按住 S=平移+按下即停双效，留痕）；W/A/D 无战斗绑定直落空。
            self._cam_held.add(key)
        if key == arcade.key.F1 and page != "settings":
            fsm.help_open = not fsm.help_open
            return
        if key == arcade.key.ESCAPE:
            if page == "settle":
                self.close()
                return
            if page == "deck_edit":                 # 编辑器页 ESC=返回 config
                fsm.close_deck_edit()
                self._layout_buttons()
                return
            if page == "settings":                  # 设置页 ESC=取消捕获/返回 config
                handle_settings_key(self, key)
                return
            if fsm.esc() == "exit":
                self.close()
            return
        if page == "deck_edit":                     # 改名字态：退格编辑/其余经 on_text
            if key == arcade.key.BACKSPACE:
                fsm.deck_edit_rename_backspace()
            return
        if page == "settings":                      # 改键捕获/吞键（语义在 settings_page）
            handle_settings_key(self, key)
            return
        fsm.cancel_exit_confirm()
        if page == "config":
            if key == arcade.key.ENTER:
                self._start_game()
            elif key == arcade.key.KEY_1:
                fsm.deck_key = "su_min"
            elif key == arcade.key.KEY_2:
                fsm.deck_key = "ger_min"
            elif key == arcade.key.KEY_3:
                fsm.kev_level = "rule" if fsm.kev_level != "rule" else "local"
            else:
                fsm.key(self._key_name(key), ctrl=ctrl, shift=shift,
                        cmd=self.session.cmd)
            return
        if page == "settle":
            if key == arcade.key.ENTER:
                fsm.reset()
                self._layout_buttons()
            return
        if key == arcade.key.SPACE:
            self.ctrl.toggle()
            return
        if key in (arcade.key.EQUAL, arcade.key.NUM_ADD):
            self.ctrl.faster()
            return
        if key in (arcade.key.MINUS, arcade.key.NUM_SUBTRACT):
            self.ctrl.slower()
            return
        name = self._key_name(key)
        if name is not None:
            fsm.key(name, ctrl=ctrl, shift=shift, cmd=self.session.cmd)
            if fsm.armed_order is None:
                self._line_p0 = self._line_p1 = None   # 撤令清理陈旧画线态

    def on_text(self, text: str):
        """改名字态逐字符入缓冲（deck_edit 页——GP-01 §7 改名）。"""
        if self.fsm.page == "deck_edit" and self.fsm.deck_edit \
                and self.fsm.deck_edit.get("renaming"):
            self.fsm.deck_edit_rename_key(text)

    def _key_name(self, key):
        return self._KEY_NAMES.get(key)

    def _rebuild_key_names(self):
        """设置改键后即时重建映射（settings_page 改绑成功/恢复默认后调用）。"""
        ShellWindow._KEY_NAMES = _build_key_names()

    def _edge_scroll(self, dt: float):   # 兼容面再出口（tests/test_shell_window 锚）
        scene.edge_scroll(self, dt)

    def on_key_release(self, key, modifiers):
        self._cam_held.discard(key)

    def _ui_rect_hit(self, x, y) -> bool:
        """UI 命中域（边缘滚动豁免面）：按钮 + 小地图 + 选中面板带。"""
        if any(btn.hit(x, y) for btn in self._buttons):
            return True
        mx0, my0, mx1, my1 = minimap_geom(self)
        if mx0 <= x <= mx1 and my0 <= y <= my1:
            return True
        px0, py0, px1, py1 = panel_geom(self)
        return px0 - 2 <= x <= px1 + 2 and py0 <= y <= py1

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        self._mouse_xy = (x, y)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        scene.scroll_zoom(self, x, y, scroll_y)

    def on_mouse_press(self, x, y, button, modifiers):
        self.fsm.cancel_exit_confirm()
        page = self.fsm.page
        # 2026-10-15 六条修正·问题1：settings 入元组——_config_click 的 settings
        # 分支（→handle_settings_click）此前无人路由，st_* 命中落入 _panel_click
        # 即被吞（含返回钮 st_back）；点击不再漏到框选起笔边路。
        if page in ("config", "deck_edit", "settings"):
            self._config_click(x, y)
            return
        if page == "settle":
            return
        if button == arcade.MOUSE_BUTTON_MIDDLE:
            self._mmb_drag = True     # MMB+移动=相机旋转（manual.txt:594）
            return
        if self.fsm.armed_order is None:
            self._line_p0 = self._line_p1 = None   # 撤令后的陈旧画线态清理
        if self._panel_click(x, y, button):
            return
        if self.fsm.page != "deploy" and minimap_to_cm(self, x, y) is not None:
            self._minimap_click(x, y, button, modifiers)   # §11：部署页无小地图
            return
        if button == arcade.MOUSE_BUTTON_RIGHT:
            self._right_click_map(x, y, modifiers)
        elif button == arcade.MOUSE_BUTTON_LEFT:
            self._left_click_map(x, y, modifiers)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self.fsm.page not in ("deploy", "battle"):
            return
        if self._mmb_drag and (buttons & arcade.MOUSE_BUTTON_MIDDLE):
            scene.rotate_camera(self, dx)          # MMB 旋转跟手（594 行语义）
            return
        if self._line_p0 is not None:              # K/T 画线态：跟手预览
            self._line_p1 = (x, y)
        elif self._box_p0 is not None:
            self._box_p1 = (x, y)

    def on_mouse_release(self, x, y, button, modifiers):
        if (self.fsm.page in ("deploy", "battle")
                and button == arcade.MOUSE_BUTTON_LEFT):
            shift = bool(modifiers & arcade.key.MOD_SHIFT)
            if self._line_p0 is not None:          # 画线/画区收笔（语义在 fm_panel）
                p0, p1 = self._line_p0, self._line_p1 or self._line_p0
                self._line_p0 = self._line_p1 = None
                if not finish_line_drag(self, p0, p1, shift=shift):
                    self._left_click_map(p0[0], p0[1], 0)  # 其余待令=点令回落
                return
            if self._box_p0 is not None:
                if self._box_p1 is not None:
                    self.select_box_px(*self._box_p0, *self._box_p1)
                else:
                    self.fsm.clear_selection()     # 点空地=清选区（含空选区）
        self._box_p0 = self._box_p1 = None
        if button == arcade.MOUSE_BUTTON_MIDDLE:
            self._mmb_drag = False                 # MMB 旋转收笔

    # ── 点击处理 ──

    def _config_click(self, x, y):
        if self.fsm.page == "settings":             # 设置页命中域独立分发
            handle_settings_click(self, x, y)
            return
        handle_config_click(self, x, y)

    def _start_game(self):
        self.session.new_game(self.fsm.deck_key, self.fsm.kev_level, self.fsm.seed)
        self.fsm.start_deploy()
        self.ctrl = PlaybackController(self.session.total_ticks,
                                       speeds=_SPEED_STEPS)
        self._camera_fit()
        self.ctrl.play()
        self.refresh()

    def _panel_click(self, x, y, button) -> bool:
        """面板命中处理（语义在 hud_bottom.handle_panel_button——热键镜像）。"""
        if button != arcade.MOUSE_BUTTON_LEFT:
            return False
        for btn in self._buttons:
            if btn.hit(x, y):
                handle_panel_button(self, btn.key)
                return True
        return False

    def _minimap_geom(self):          # 兼容面再出口（tests/test_shell_window 锚）
        return minimap_geom(self)

    def _minimap_click(self, x, y, button, modifiers=0):
        cm = minimap_to_cm(self, x, y)
        if cm is None:
            return False
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.cam_cx, self.cam_cy = cm
            self._clamp_camera()
            return True
        if button == arcade.MOUSE_BUTTON_RIGHT:
            queue = bool(modifiers & arcade.key.MOD_SHIFT)   # Shift=排队（2026-10-14
            if self.fsm.selected:                            # 小地图 Shift 锚——与
                self.session.cmd.move(list(self.fsm.selected), cm,  # 地图右键同口径）
                                      queue=queue)
            if self.fsm.selected_air:              # 空选区=盘旋待命（§4 右键语义）
                self.session.cmd.air_patrol(list(self.fsm.selected_air), cm)
            return True
        return False

    def _left_click_map(self, x, y, modifiers):
        fsm = self.fsm
        cm = self.px_to_cm(x, y)
        shift = bool(modifiers & arcade.key.MOD_SHIFT)
        if fsm.armed_purchase is not None:
            handle_confirm_purchase(self, cm)      # 待放卡：点地确认
            return
        foe = self._unit_at(x, y, team="enemy")
        own = self._unit_at(x, y, team="own")
        air = self._aircraft_at(x, y)
        building = self._building_at(x, y)
        if fsm.armed_order is not None:
            if fsm.armed_order == "unload" and building is not None:
                self.session.cmd.unload(list(fsm.selected),      # U+点楼=进楼
                                        building_id=building["id"],
                                        queue=shift)
                if not shift:
                    fsm.clear_order()
                return
            if foe is not None and fsm.execute_armed_unit(
                    foe["id"], self.session.cmd, enemy=True, shift=shift):
                return
            if own is not None and fsm.execute_armed_ground(
                    own["pos_cm"], self.session.cmd, shift=shift):
                return
            if air is not None and fsm.execute_armed_ground(
                    air["pos_cm"], self.session.cmd, shift=shift):
                return
            if fsm.armed_order == "strike":
                if not fsm.selected_air \
                        and fsm._first_aircraft(bomber=True) is None:
                    fsm.notify("无在空飞机，请先经底栏空呼", tone="error")
                    return                         # 待令保留（A9 反馈不静默）
                self._line_p0 = (x, y)             # K：落笔（拖拽=画轴/松手=点目标）
                self._line_p1 = None
                return
            if fsm.armed_order == "drop":
                # O：落笔画区（P0 键位纠偏块 2026-10-13——拖拽=矩形区/单击=点投；
                # 与 K/T 画线态同构）。无载伞机=提前 toast（A9 口径），待令保留。
                if not fsm.selected_air \
                        and fsm._first_aircraft(bomber=False) is None:
                    fsm.notify("无在空飞机，请先经底栏空呼", tone="error")
                    return
                self._line_p0 = (x, y)
                self._line_p1 = None
                return
            if fsm.armed_order == "fire_mission" \
                    and fsm.fm_params["form"] in ("LINE", "CREEP"):
                self._line_p0 = (x, y)             # LINE/CREEP：落笔拖拽画线
                self._line_p1 = None
                return
            fsm.execute_armed_ground(cm, self.session.cmd, shift=shift)
            return
        # 无待令：点选（单位∪飞机双通道）/点空地=框选落笔
        if own is not None:
            fsm.click_unit(own["id"], shift=shift)
        elif air is not None:
            fsm.click_aircraft(air["id"], shift=shift)
        else:
            self._box_p0 = (x, y)
            self._box_p1 = None

    def _right_click_map(self, x, y, modifiers):
        """右键：移动选中单位（Shift=追加路径点）；空选区=盘旋待命 CAP（
        Shift+右键=直飞航路——§4 ③段）；待放卡或待令时=撤回/取消（优先序保留）。"""
        fsm = self.fsm
        if fsm.armed_purchase is not None:
            fsm.cancel_purchase()
            return
        if fsm.armed_order:
            fsm.clear_order()
            self._line_p0 = self._line_p1 = None
            return
        sel = list(fsm.selected)
        if sel:
            queue = bool(modifiers & arcade.key.MOD_SHIFT)
            self.session.cmd.move(sel, self.px_to_cm(x, y), queue=queue)
        if fsm.selected_air:                      # 飞机：右键=盘旋/Shift=直飞（§4）
            cm = self.px_to_cm(x, y)
            if modifiers & arcade.key.MOD_SHIFT:
                self.session.cmd.air_move(list(fsm.selected_air), cm)
            else:
                self.session.cmd.air_patrol(list(fsm.selected_air), cm)

    def _unit_at(self, x, y, team=None):
        return scene.hit_unit(self, x, y, team)

    def _aircraft_at(self, x, y):
        return scene.hit_aircraft(self, x, y)

    def _building_at(self, x, y):
        return scene.hit_building(self, x, y)

    # ── 按钮布局（每帧重算——resize/换页自适应）──

    def _layout_buttons(self):
        self._buttons = []
        page = self.fsm.page
        if page == "config":
            layout_config_page(self)
            return
        if page == "deck_edit":
            layout_deck_edit_page(self)
            return
        if page == "settings":
            layout_settings_page(self)
            return
        if page == "settle":
            return
        if page == "deploy":
            layout_deploy_panel(self)      # §11 断箭部署面：无小地图/编组列/命令格
            return                         # （选中卡亦不绘——与左栏卡轨让位）
        # B1 修复块（2026-10-13）：命令格/呼援轨先布局（layout_air_rail 记录
        # win._rail_bottom）——六处修正块后选中卡已迁底中、不再消费该让位值
        # （记录仍写：qa.py rail_rect 在读），布局调用序维持不动。
        layout_battle_buttons(self)
        layout_selection_panel(self)
        layout_group_bar(self)
        layout_fm_panel(self)

    # ── 绘制 ──

    def on_draw(self):
        self.clear(color=BACKGROUND)
        self.render_page()

    def render_page(self):
        page = self.fsm.page
        if page == "config":
            draw_config_page(self)
            draw_help_overlay(self)
            draw_exit_confirm(self)
            return
        if page == "deck_edit":
            draw_deck_edit_page(self)
            draw_toasts(self)
            return
        if page == "settings":
            draw_settings_page(self)
            draw_toasts(self)
            return
        draw_scene(self)
        draw_margin_mat(self)
        draw_top_bar(self)
        if page == "settle":
            draw_settle_panel(self, self.frame.get("result"))
            draw_command_stats(self)
            return
        if page == "deploy":
            # §11 断箭部署面：全图即视野——无小地图/编组列/命令格/选中卡
            # （左栏卡轨+车道+机动行；点击单位的信息浮层仍可用）
            draw_deploy_markers(self)
            draw_deploy_panel(self)
        else:
            draw_order_panel(self)
            draw_fm_panel(self)
            draw_minimap(self)
            draw_group_bar(self)
            draw_selection_panel(self)
        # 〔2026-10-15 二轮拍板：单位信息浮层整体撤除（§11.3 炮击待令抑制
        # 判据随之废止）——底中只留选中长条；地图痕迹文字标签同批撤（scene）。〕
        draw_toasts(self)
        draw_help_overlay(self)
        draw_exit_confirm(self)


# 键名映射表（arcade.key → fsm 键语义名；GP-01 §4/§6 扩容键位；P0 键位纠偏块
# 2026-10-13：A 出表（退役归相机 WASD——手册无 A 战斗令）、Q 入表（Attack Move））
def _build_key_names():
    keys = {arcade.key.Q: "Q", arcade.key.S: "S", arcade.key.E: "E",
            arcade.key.Z: "Z", arcade.key.X: "X", arcade.key.R: "R",
            arcade.key.T: "T", arcade.key.G: "G", arcade.key.H: "H",
            arcade.key.K: "K", arcade.key.O: "O", arcade.key.F: "F",
            arcade.key.U: "U", arcade.key.N: "N", arcade.key.V: "V",
            arcade.key.B: "B", arcade.key.J: "J", arcade.key.Y: "Y",
            arcade.key.TAB: "TAB",
            # P1 机制块（2026-10-13）：C 诱饵/L 狙击观测（N 让位照射）/
            # M 登车/P 精密打击
            arcade.key.C: "C", arcade.key.L: "L", arcade.key.M: "M",
            arcade.key.P: "P"}
    for d in range(1, 10):
        keys[getattr(arcade.key, "KEY_%d" % d)] = str(d)
    # 设置改键块（2026-10-14）：用户覆盖层（data/gen/keybinds.json）叠加——
    # 被覆盖槽位的默认键码移除（防双触发），新码入表。默认表保持字面=
    # tests/test_manual_conformance HOTKEYS 节源码解析锚不破。
    overrides = keybinds.load_overrides()
    for name, code in overrides.items():
        for k, v in list(keys.items()):
            if v == name:
                del keys[k]
        keys[int(code)] = name
    return keys


ShellWindow._KEY_NAMES = _build_key_names()
