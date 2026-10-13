"""FE-T07 壳窗口层测试（需 fe 渲染栈——未装 arcade 全类跳过，CI 零渲染栈空转）。

接线纪律自证：窗口只经 tools 胶水（SkirmishSession）驱动；窗口层自身不
import sovs.sim（tests/test_arch_constraints.py AST 守卫另查）。隐藏窗离屏，
不依赖可见 GUI 会话。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import arcade                                    # noqa: F401（探针）
    import pyglet.display
    # 显示会话探针：arcade 可导入但 WindowServer 不可达（合盖/无头）时，建窗会在
    # pyglet cocoa get_default_screen 处 IndexError——以屏幕枚举预判并整类跳过。
    # （探针修复：pyglet 2.x 已删 pyglet.canvas 模块——pyglet.display.get_display()
    # 为现行 API；旧探针 AttributeError 被 except 吞成 HAS_GL_WINDOW=False，
    # 全类静默 SKIPPED——「崩溃零门禁暴露」的系统性根因之一。）
    HAS_GL_WINDOW = len(pyglet.display.get_display().get_screens()) > 0
    HAS_ARCADE = True
except Exception:                                    # noqa: BLE001（缺渲染栈或无显示会话=跳过）
    HAS_ARCADE = False
    HAS_GL_WINDOW = False


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用（pip install -e \".[fe]\"）")
class TestShellWindow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from tools.skirmish_shell import ScriptedPilot, SkirmishSession
        from sovs.ui.shell_window import ShellWindow
        cls.session = SkirmishSession()               # 默认配置（su_min vs 规则 KEV）
        cls.pilot = ScriptedPilot(cls.session)        # 人类席脚本驾驶（购卡/出牌）
        cls.win = ShellWindow(cls.session, visible=False)
        cls.win.fsm.start_deploy()                    # config→deploy（会话已建世界）
        for _ in range(80):                           # 部署期出牌+spawn（计时起步）
            cls.pilot.step()
            cls.session.advance(1)
        cls.win.refresh()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def test_01_deploy_page_frame_and_countdown(self):
        f = self.win.frame
        self.assertEqual(f["phase"], "deploy")
        self.assertEqual(self.win.fsm.page, "deploy")
        self.assertGreater(self.win.fsm.deploy_ticks_left, 0)   # 60s 计时活
        self.assertTrue(any(p["team"] == 0 for p in f["players"]))

    def test_02_battle_page_selection_box_and_order_trail(self):
        """battle 页三要素：单位/框选/已下令痕迹（--screenshot battle.png 同款驱动）。"""
        self.session.advance(700)                     # 越过盲部署（600t）入实战
        self.win.refresh()
        self.assertEqual(self.win.frame["phase"], "combat")
        self.assertEqual(self.win.fsm.page, "battle")
        mine = [u for u in self.win.frame["units"] if u["team"] == 0]
        self.assertTrue(mine)                                    # 有单位
        # 框选（px 坐标——窗口 API 负责换算 cm）
        x0, y0 = self.win.cm_to_px(mine[0]["pos_cm"][0] - 3000,
                                   mine[0]["pos_cm"][1] - 3000)
        x1, y1 = self.win.cm_to_px(mine[0]["pos_cm"][0] + 3000,
                                   mine[0]["pos_cm"][1] + 3000)
        self.win.select_box_px(x0, y0, x1, y1)
        self.assertTrue(self.win.fsm.selected)                    # 框选痕迹
        # 已下达命令痕迹（经 cmd_bus → queue_command 真通道）
        self.session.cmd.move(list(self.win.fsm.selected), (120000, 50000))
        self.assertTrue(self.session.cmd.trail)                   # 痕迹在册

    def test_03_snapshot_offscreen_nonblank(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "probe.png")
            self.win.snapshot(path)
            img = Image.open(path).convert("RGB")
            colors = img.getcolors(maxcolors=1_000_000)
        self.assertGreaterEqual(len(colors), 8)
        self.assertEqual(img.size, (self.win.width, self.win.height))

    def test_04_unit_overlay_reads_frame_entry(self):
        """点击单位浮层：血量/弹药/士气取自状态帧条目（迷雾外敌单位不在帧=无浮层）。"""
        mine = [u for u in self.win.frame["units"] if u["team"] == 0]
        self.win.show_unit_info(mine[0]["id"])
        entry = self.win.unit_info_entry
        self.assertIsNotNone(entry)
        self.assertIn("hp", entry)
        self.assertIn("ammo_pct", entry)
        self.assertIn("morale", entry)

    def test_05_top_bar_flow_segments_no_overlap(self):
        """顶栏左三段流式排布（视觉复检必修项回归护栏）。

        「|| 命令照收」暂停徽标会拉长计时段（battle.png 实测 t2165 段宽 212px，
        最坏 t13800/13800 x16 达 232px），固定 x=200 的阶段标签会被顶入叠压。
        护栏：最坏串宽下（计时→阶段→提示）三段起点逐段后随、段间恒有
        _TOP_SEG_GAP 空隙，且提示段右端不撞右锚点数块。
        """
        from sovs.ui.shell_window import (_TOP_SEG_GAP, _flow_positions,
                                          _text_width)
        total = self.session.total_ticks
        worst = "t%d/%d || 命令照收 x16" % (total, total)
        head = "框选/点选 右键移动 Q+点地=攻击移动 G组合 X烟幕 H纪律 Ctrl+数字编组"
        widths = [_text_width(worst, 13), _text_width("COMBAT", 13),
                  _text_width(head, 12)]
        self.assertGreater(widths[0], 190)          # 徽标拉长段（旧固定 x=200 必叠）
        x0, x1, x2 = _flow_positions(10, widths)
        self.assertGreaterEqual(x1 - widths[0], x0 + _TOP_SEG_GAP)
        self.assertGreaterEqual(x2 - widths[1], x1 + _TOP_SEG_GAP)
        pts = _text_width("点数 9999｜空援 999", 13)
        self.assertLess(x2 + widths[2], self.win.width - 10 - pts)


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用（pip install -e \".[fe]\"）")
class TestRedesignWindow(unittest.TestCase):
    """交互重设计 v2 窗口层验收（真实 GL 事件层直调——A1/A2/A3/A6/A7/A8/A10/A14/A15）。

    全部经 win.on_key_press/on_mouse_press/on_mouse_drag/on_mouse_release 驱动
    （与玩家同路径）；窗口存活=用例不抛即证（P0 崩点回归护栏）。
    """

    L = None      # 类面填充（import arcade 后）

    @classmethod
    def setUpClass(cls):
        import arcade
        from sovs.ui.shell_window import ShellWindow
        from tools.skirmish_shell import SkirmishSession
        cls.arcade = arcade
        cls.L = arcade.MOUSE_BUTTON_LEFT
        cls.R = arcade.MOUSE_BUTTON_RIGHT
        cls.session = SkirmishSession(seed=42)
        cls.win = ShellWindow(cls.session, visible=False)
        cls.win.on_key_press(arcade.key.ENTER, 0)       # config→deploy（真实事件）

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    # ── A1：事件层点卡不崩+待放卡置位+点地确认 ──

    def test_01_A1_card_click_armed_and_ground_confirm(self):
        win, L = self.win, self.L
        self.assertEqual(win.fsm.page, "deploy")
        btn = next(b for b in win._buttons if b.key.startswith("buy:102|"))
        win.on_mouse_press((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2, L, 0)
        self.assertIsNotNone(win._armed_purchase)       # 点卡装弹（无 AttributeError）
        self.assertEqual(win._armed_purchase[0], 102)
        n_pending = len(self.session.pending_expands)
        win.on_mouse_press(1280 // 2, 400, L, 0)        # 点地放卡（真实事件层）
        self.assertIsNone(win._armed_purchase)          # 确认后清待放卡
        self.assertEqual(len(self.session.pending_expands), n_pending + 1)
        expect_cm = win.px_to_cm(1280 // 2, 400)
        self.assertEqual(self.session.pending_expands[-1]["dest"],
                         (expect_cm[0], expect_cm[1]))  # 位置意图登记=点击 cm

    # ── A2：四控件不崩（R 键+底栏 reverse；strike/drop 在 battle 布局见 test_05）──

    def test_02_A2_reverse_key_and_button(self):
        win = self.win
        win.on_key_press(self.arcade.key.R, 0)
        self.assertEqual(win.fsm.armed_order, "reverse")     # 登记面扩容后不再 ValueError
        win.on_key_press(self.arcade.key.ESCAPE, 0)          # 清待令（链中段）
        btn = next(b for b in win._buttons if b.key == "reverse")
        win.on_mouse_press((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2,
                           self.L, 0)
        self.assertEqual(win.fsm.armed_order, "reverse")     # 底栏按钮同达

    def test_03_A3_units_stay_in_viewport(self):
        """购卡出场后南缘锚点单位 px 仍在视口内（换页重适配回归护栏）。"""
        win = self.win
        for _ in range(100):
            self.session.advance(1)
        win.refresh()
        mine = [u for u in win.frame["units"] if u["team"] == 0]
        self.assertTrue(mine)
        l, b, r, t = win._viewport_px()
        for u in mine:
            px, py = win.cm_to_px(u["pos_cm"][0], u["pos_cm"][1])
            self.assertTrue(l <= px <= r and b <= py <= t,
                            "单位 %s px=(%.1f,%.1f) 出视口 %s"
                            % (u["id"], px, py, (l, b, r, t)))

    def test_04_A8_dynamic_zoom_floor_and_camera_clamp(self):
        """缩放下限=动态（≤整图适配）+图幅钳制——2km 图可回全图。"""
        win = self.win
        self.assertLessEqual(win._min_scale(), win._fit_scale())
        for _ in range(24):                              # 连续缩小
            win.on_mouse_scroll(win.width / 2, win.height / 2, 0, -1)
        self.assertAlmostEqual(win.cam_scale, win._min_scale(), places=9)
        mw, mh = win.frame["map_cm"]
        l, b, r, t = win._viewport_px()
        vw_cm = (r - l) / win.cam_scale
        vh_cm = (t - b) / win.cam_scale
        if vw_cm < mw:                                   # 图幅钳制（±半视口）
            self.assertGreaterEqual(win.cam_cx, -vw_cm / 2 - 1e-6)
            self.assertLessEqual(win.cam_cx, mw + vw_cm / 2 + 1e-6)
        if vh_cm < mh:
            self.assertGreaterEqual(win.cam_cy, -vh_cm / 2 - 1e-6)
            self.assertLessEqual(win.cam_cy, mh + vh_cm / 2 + 1e-6)
        for _ in range(8):                               # 放大后再连续缩小仍受钳
            win.on_mouse_scroll(win.width / 2, win.height / 2, 0, 1)
        for _ in range(24):
            win.on_mouse_scroll(win.width / 2, win.height / 2, 0, -1)
            win.on_mouse_scroll(0, 0, 0, -1)
        self.assertGreaterEqual(win.cam_scale, win._min_scale() - 1e-9)

    def test_05_battle_strike_drop_buttons_and_A6_attack_move(self):
        win, L = self.win, self.L
        from sovs.sim.tables import CONFIG
        while self.session.world.tick < CONFIG.phase_ticks[0] + 2:
            self.session.advance(1)
        win.refresh()
        self.assertEqual(win.fsm.page, "battle")
        for key, group in (("strike", "strike"), ("drop", "drop")):
            win.fsm.clear_order()
            btn = next(b for b in win._buttons if b.key == key)
            win.on_mouse_press((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2,
                               L, 0)
            self.assertEqual(win.fsm.armed_order, group)  # A2 三按钮齐
            win.fsm.notifications.clear()
            tx, ty = win.cm_to_px(100000, 70000)
            win.on_mouse_press(tx, ty, L, 0)          # 无在空飞机→toast+待令保留
            self.assertTrue(any("无在空飞机" in n["text"]    # A9 反馈不静默
                                for n in win.fsm.notifications))
            self.assertEqual(win.fsm.armed_order, group)
        # A6：Q+点地=攻击移动（真实事件层，trail mode=ATTACK——P0 键位纠偏
        # 块 2026-10-13 A→Q，手册 manual.txt:560-562）
        win.fsm.clear_order()                          # strike/drop 待令保留→先清
        mine = [u for u in win.frame["units"] if u["team"] == 0]
        self.assertTrue(mine)
        bx0, by0 = win.cm_to_px(mine[0]["pos_cm"][0] - 5000,
                                mine[0]["pos_cm"][1] - 5000)
        bx1, by1 = win.cm_to_px(mine[0]["pos_cm"][0] + 5000,
                                mine[0]["pos_cm"][1] + 5000)
        win.on_mouse_press(bx0, by0, L, 0)
        win.on_mouse_drag(bx1, by1, 0, 0, L, 0)
        win.on_mouse_release(bx1, by1, L, 0)
        self.assertTrue(win.fsm.selected)
        win.on_key_press(self.arcade.key.Q, 0)
        ax, ay = win.cm_to_px(100000, 55000)
        win.on_mouse_press(ax, ay, L, 0)
        moves = [t for t in self.session.cmd.trail if t["kind"] == "move"]
        self.assertTrue(moves)
        self.assertEqual(moves[-1]["mode"], "ATTACK")

    def test_06_A7_group_assign_and_recall_via_events(self):
        win = self.win
        win.refresh()
        self.assertTrue(win.fsm.selected or self._reselect_all())
        self.assertTrue(win.fsm.selected)
        win.on_key_press(self.arcade.key.KEY_1, self.arcade.key.MOD_CTRL)
        self.assertEqual(win.fsm.groups.get(1),
                         (tuple(win.fsm.selected), ()))  # (units, air) 二元组
        snapshot = win.fsm.selected
        win.fsm.clear_selection()
        win.on_key_press(self.arcade.key.KEY_1, 0)
        self.assertEqual(win.fsm.selected, tuple(
            i for i in snapshot
            if any(u["id"] == i for u in win.frame["units"])))   # 取组剪尸

    def _reselect_all(self):
        win, L = self.win, self.L
        mine = [u for u in win.frame["units"] if u["team"] == 0]
        if not mine:
            return False
        xs = [u["pos_cm"][0] for u in mine]
        ys = [u["pos_cm"][1] for u in mine]
        bx0, by0 = win.cm_to_px(min(xs) - 6000, min(ys) - 6000)
        bx1, by1 = win.cm_to_px(max(xs) + 6000, max(ys) + 6000)
        win.on_mouse_press(bx0, by0, L, 0)
        win.on_mouse_drag(bx1, by1, 0, 0, L, 0)
        win.on_mouse_release(bx1, by1, L, 0)
        return bool(win.fsm.selected)

    def test_07_A10_esc_layered_chain_window_alive(self):
        """待令态 ESC=清待令且窗口未关闭；F1>待令分层；退出确认态可撤销。"""
        import unittest.mock as mock
        win = self.win
        win.on_key_press(self.arcade.key.Q, 0)
        with mock.patch.object(win, "close") as close_spy:
            win.on_key_press(self.arcade.key.ESCAPE, 0)
        close_spy.assert_not_called()                    # 不丢整局
        self.assertIsNone(win.fsm.armed_order)
        # F1 首层：面板开→ESC 只关面板
        win.on_key_press(self.arcade.key.F1, 0)
        win.on_key_press(self.arcade.key.Q, 0)
        with mock.patch.object(win, "close") as close_spy:
            win.on_key_press(self.arcade.key.ESCAPE, 0)
        self.assertFalse(win.fsm.help_open)
        self.assertEqual(win.fsm.armed_order, "attack")  # 后续链未触发
        win.on_key_press(self.arcade.key.ESCAPE, 0)      # 清待令
        # 退出确认：无状态 ESC×2 才关（spy 证第二次才触发）
        win.fsm.clear_selection()
        with mock.patch.object(win, "close") as close_spy:
            win.on_key_press(self.arcade.key.ESCAPE, 0)
            close_spy.assert_not_called()
            self.assertTrue(win.fsm.exit_confirm)
            win.on_key_press(self.arcade.key.SPACE, 0)   # 任意键撤销确认
            self.assertFalse(win.fsm.exit_confirm)
            win.on_key_press(self.arcade.key.ESCAPE, 0)
            win.on_key_press(self.arcade.key.ESCAPE, 0)
            close_spy.assert_called_once()               # 确认态二次 ESC=真退出
        win.fsm.exit_confirm = False                     # 复位共享窗（spy 已拦截真关）

    def test_08_A14_page_gates_via_window_events(self):
        win = self.win
        win.fsm.reset()                                  # 回 config（再来一局入口）
        win.refresh()
        self.assertEqual(win.fsm.page, "config")
        n0 = len(self.session.cmd.trail)
        for key in (self.arcade.key.Q, self.arcade.key.S, self.arcade.key.E,
                    self.arcade.key.Z, self.arcade.key.X, self.arcade.key.R,
                    self.arcade.key.T, self.arcade.key.G, self.arcade.key.H,
                    self.arcade.key.K, self.arcade.key.O):
            win.on_key_press(key, 0)
        self.assertEqual(len(self.session.cmd.trail), n0)     # trail 零增长
        self.assertTrue(any("战斗令在部署/实战页可用" in n["text"]
                            for n in win.fsm.notifications))
        # deploy 页 G 拦截专案文案
        win.on_key_press(self.arcade.key.ENTER, 0)       # 新一局（真实事件）
        n1 = len(self.session.cmd.trail)                 # new_game 重建 CmdBus
        win.fsm.notifications.clear()
        win.on_key_press(self.arcade.key.G, 0)
        self.assertEqual(len(self.session.cmd.trail), n1)
        self.assertTrue(any("烟幕/姿态令在实战页可用（部署期冲刺用 Z）"
                            in n["text"] for n in win.fsm.notifications))

    def test_09_A15_minimap_right_click_orders_move(self):
        """小地图右键=有意下令（落点==小地图映射 cm 点）——修误穿歧义。"""
        win, R = self.win, self.R
        from sovs.sim.tables import CONFIG
        # test_08 重开了新局（世界重建无购卡）——先经事件层购一张卡再入实战
        btn = next(b for b in win._buttons if b.key.startswith("buy:102|"))
        win.on_mouse_press((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2,
                           self.L, 0)
        px, py = win.cm_to_px(90000, 25000)
        win.on_mouse_press(px, py, self.L, 0)
        while self.session.world.tick < CONFIG.phase_ticks[0] + 2 \
                and self.session.world.phase != 2:
            self.session.advance(1)
        win.refresh()
        self.assertTrue(self._reselect_all())
        x0, y0, x1, y1 = win._minimap_geom()
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2            # 小地图中心
        mw, mh = win.frame["map_cm"]
        expect = (int((mx - x0) / (x1 - x0) * mw), int((my - y0) / (y1 - y0) * mh))
        n_moves = len([t for t in self.session.cmd.trail
                       if t["kind"] == "move"])
        win.on_mouse_press(mx, my, R, 0)
        moves = [t for t in self.session.cmd.trail if t["kind"] == "move"]
        self.assertEqual(len(moves), n_moves + 1)        # 新增 1 条 move
        self.assertEqual(moves[-1]["point_cm"], [expect[0], expect[1]])

    def test_10_A9_air_call_button_insufficient_points_toast(self):
        """空呼点数预判：roster 灰显+点击 toast『空援点数不足』（非引擎门静默）。"""
        win, L = self.win, self.L
        self.session.world.players[0].air_points = 10    # 低于机身+弹价
        win.refresh()
        roster = {e["key"]: e for e in self.session.air_roster()}
        attack = next(e for e in roster.values()
                      if "BOMB" in e["payload"])
        self.assertFalse(attack["affordable"])          # A9 预判位=生成处
        btn = next(b for b in win._buttons
                   if b.key == "air:" + attack["key"])
        self.assertEqual(btn.tone, "disabled")          # 按钮灰显
        win.fsm.notifications.clear()
        win.on_mouse_press((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2, L, 0)
        self.assertTrue(any("空援点数不足" in n["text"]
                            for n in win.fsm.notifications))
        self.assertFalse(any(a.team == 0 for a in self.session.world.aircraft))

    def test_11_edge_scroll_pan_and_ui_hit_exemption(self):
        """边缘滚动：贴视口内缘平移；命中按钮矩形（UI 命中区）时不触发。"""
        win = self.win
        for _ in range(10):                              # 放大到视口<图幅（可滚动域）
            win.on_mouse_scroll(win.width / 2, win.height / 2, 0, 1)
        l, b, r, t = win._viewport_px()
        vw_cm = (r - l) / win.cam_scale
        mw = win.frame["map_cm"][0]
        self.assertLess(vw_cm, mw)
        cx0 = win.cam_cx
        win.on_mouse_motion(l + 6, (b + t) / 2, 0, 0)     # 贴左缘
        win._edge_scroll(0.1)
        self.assertLess(win.cam_cx, cx0)                 # 左移生效
        btn = next(b2 for b2 in win._buttons
                   if b2.key.startswith("air:"))          # 底栏按钮（侵入带）
        cx1 = win.cam_cx
        win.on_mouse_motion((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2, 0, 0)
        win._edge_scroll(0.1)
        self.assertEqual(win.cam_cx, cx1)                # UI 命中优先于镜头

    def test_12_WASD_camera_pan_with_arrow_coexistence(self):
        """P0 键位纠偏块：WASD=相机平移（手册 manual.txt:579-580「W, A, S, D
        Camera movement」），方向键并存；A 键不再承载攻击移动（Q 接管）。
        断言口径=方向+等距（共享窗缩放态不定，不锚具体步长值）。"""
        from sovs.ui import scene
        win, arc = self.win, self.arcade
        win._cam_held.clear()                       # 共享窗：前序用例遗留 held 清空
        mw, mh = win.frame["map_cm"]
        guard = 0                                     # 缩放至视口<图幅（横纵皆入
        while guard < 60:                             # 可平移域——否则钳心 pan 无效）
            l_, b_, r_, t_ = win._viewport_px()
            if (r_ - l_) / win.cam_scale < mw and (t_ - b_) / win.cam_scale < mh:
                break
            win.on_mouse_scroll(win.width / 2, win.height / 2, 0, 1)
            guard += 1
        win.cam_cx, win.cam_cy = mw / 2, mh / 2          # 图心起测（夹持零干扰）
        win._clamp_camera()

        def _pan():
            cx, cy = win.cam_cx, win.cam_cy
            scene.pan_camera(win, 0.1)
            return win.cam_cx - cx, win.cam_cy - cy

        # A=左移（A 退役归相机）；松键即停
        win.on_key_press(arc.key.A, 0)
        dax, _ = _pan()
        self.assertLess(dax, 0)
        win.on_key_release(arc.key.A, 0)
        self.assertEqual(_pan(), (0.0, 0.0))
        # D=右移（等距对称——同轴同 step）
        win.on_key_press(arc.key.D, 0)
        ddx, _ = _pan()
        win.on_key_release(arc.key.D, 0)
        self.assertAlmostEqual(ddx, -dax, places=6)
        # W=上移 / S=下移（S 双职：相机+停止令并存——on_key_press 不炸即证）
        win.on_key_press(arc.key.W, 0)
        _, dwy = _pan()
        win.on_key_release(arc.key.W, 0)
        self.assertGreater(dwy, 0)
        win.on_key_press(arc.key.S, 0)
        _, dsy = _pan()
        win.on_key_release(arc.key.S, 0)
        self.assertAlmostEqual(dsy, -dwy, places=6)
        # 方向键并存（LEFT 与 A 同向合流=单步——同轴不叠加增速，方向键保留）
        win.on_key_press(arc.key.LEFT, 0)
        dl, _ = _pan()
        self.assertAlmostEqual(dl, dax, places=6)
        win.on_key_release(arc.key.LEFT, 0)
        win.on_key_press(arc.key.A, 0)                   # A 单独同效（并存非替换）
        self.assertAlmostEqual(_pan()[0], dax, places=6)
        win.on_key_release(arc.key.A, 0)


if __name__ == "__main__":
    unittest.main()
