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
    # 显示会话探针：arcade 可导入但 WindowServer 不可达（合盖/无头）时，建窗会在
    # pyglet cocoa get_default_screen 处 IndexError——以屏幕枚举预判并整类跳过。
    # （探针修复：pyglet 2.x 已删 pyglet.canvas 模块——pyglet.display.get_display()
    # 为现行 API；旧探针 AttributeError 被 except 吞成 HAS_GL_WINDOW=False，
    # 全类静默 SKIPPED——「崩溃零门禁暴露」的系统性根因之一。）
    # 〔2026-10-13 探针加固：屏幕枚举通过但建窗仍可能撞 WindowServer 瞬态不可达
    #  （门禁实撞=整类 ERROR 非 SKIP）——改共享 _gl_probe 双检：枚举＋隐藏窗
    #  实试，建不起来=按既有口径整类跳过。〕
    from tests._gl_probe import gl_window_available
    HAS_GL_WINDOW = gl_window_available()
    HAS_ARCADE = HAS_GL_WINDOW or arcade is not None
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

    def test_04_unit_overlay_removed_negative_anchor(self):
        """〔2026-10-15 二轮拍板〕点击单位浮层整体撤除（底中只留选中长条）：
        show_unit_info/unit_info_entry 不复存在（防复活负锚）；点选单位只落
        选中态（明细呈现面=选中条图标＋单位图标血条，不再常驻文字浮层）。"""
        self.assertFalse(hasattr(self.win, "show_unit_info"))
        self.assertFalse(hasattr(self.win, "unit_info_entry"))
        mine = [u for u in self.win.frame["units"] if u["team"] == 0]
        self.win.fsm.select_units([mine[0]["id"]])
        self.assertIn(mine[0]["id"], self.win.fsm.selected)

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
        # B3（2026-10-13）：空选区且无在空机→strike/drop 钮不布局（命令格按
        # 选区过滤，manual.txt:344-346）；直造带弹/载伞在空机＋空选区→钮存在
        self.assertFalse(any(b.key == "strike" for b in win._buttons))
        self.assertFalse(any(b.key == "drop" for b in win._buttons))
        win.frame["aircraft"].append({
            "id": 9001, "team": 0, "name": "mc bomber", "state": "patrol",
            "alt_tier": "mid", "pos_cm": [100000, 50000], "facing": 90,
            "hp": 10, "hp_max": 10, "ammo": {"BOMB": 2}, "paratroop": 922,
            "spotted": False, "engage_air": None, "task": None,
            "alt_pending": None, "afterburner": False, "fuel_pct": 100,
            "decoy_left": 0, "evade_active": False, "evade_pct": 0,
            "paratroop_count": 1, "alt_ceiling": "mid",
            "can_afterburner": False, "can_decoy": False})
        win.fsm.clear_selection()
        win.fsm.select_aircraft([9001])                 # 直置空选区（plan B3 驱动）
        win._layout_buttons()
        btn = next(b for b in win._buttons if b.key == "strike")
        win.on_mouse_press((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2, L, 0)
        self.assertEqual(win.fsm.armed_order, "strike")   # 有机在空→钮在册可待令
        win.fsm.clear_order()
        # 撤销造机→恢复无机现场，走原 A9 无机链（K/O 经热键全量通道待令）
        win.frame["aircraft"][:] = [a for a in win.frame["aircraft"]
                                    if a["id"] != 9001]
        win.fsm.clear_selection()
        win._layout_buttons()
        for key, kname in (("K", "strike"), ("O", "drop")):
            win.fsm.clear_order()
            win.on_key_press(getattr(self.arcade.key, key), 0)
            self.assertEqual(win.fsm.armed_order, kname)
            win.fsm.notifications.clear()
            tx, ty = win.cm_to_px(100000, 70000)
            win.on_mouse_press(tx, ty, L, 0)          # 无在空飞机→toast+待令保留
            self.assertTrue(any("无在空飞机" in n["text"]    # A9 反馈不静默
                                for n in win.fsm.notifications))
            self.assertEqual(win.fsm.armed_order, kname)
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

    def test_13_box_release_rubber_band_cleared(self):
        """B2（2026-10-13）：框选 press→drag→release 后橡皮筋即清除——拖拽角点
        归 None、无残留白框属性；随后点空地清选区后仍无残留。"""
        win, L = self.win, self.L
        mine = [u for u in win.frame["units"] if u["team"] == 0]
        self.assertTrue(mine)
        bx0, by0 = win.cm_to_px(mine[0]["pos_cm"][0] - 5000,
                                mine[0]["pos_cm"][1] - 5000)
        bx1, by1 = win.cm_to_px(mine[0]["pos_cm"][0] + 5000,
                                mine[0]["pos_cm"][1] + 5000)
        win.on_mouse_press(bx0, by0, L, 0)
        win.on_mouse_drag(bx1, by1, 0, 0, L, 0)
        self.assertIsNotNone(win._box_p1)                  # 拖拽中=进行中框选
        win.on_mouse_release(bx1, by1, L, 0)
        self.assertIsNone(win._box_p0)
        self.assertIsNone(win._box_p1)
        self.assertIsNone(getattr(win, "_last_box", None))  # 松手=无残留白框
        self.assertTrue(win.fsm.selected)                  # 选中态由角框承载
        win.on_mouse_press(900, 400, L, 0)                 # 点空地=清选区
        win.on_mouse_release(900, 400, L, 0)
        self.assertEqual(win.fsm.selected, ())
        self.assertIsNone(getattr(win, "_last_box", None))  # 清选区后仍无残留

    def test_14_settings_page_click_back_button(self):
        """〔2026-10-15 六条修正·问题1·GL 行为锚〕设置页 st_back 钮经真实
        on_mouse_press 事件返回 config——修前该点击落入 _panel_click 被吞（页
        不变）。"""
        from sovs.ui import settings_page
        win = self.win
        win.fsm.page = "config"                    # 强制回 config（事件起点）
        settings_page.open_settings(win)           # 含命中域重排（st_* 在册）
        self.assertEqual(win.fsm.page, "settings")
        btn = next(b for b in win._buttons if b.key == "st_back")
        win.on_mouse_press((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2,
                           self.L, 0)
        self.assertEqual(win.fsm.page, "config")   # 点击返回钮=退设置页

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


class TestMovePathRendering(unittest.TestCase):
    """B4 路线绘制无头断言（2026-10-13）：arcade 绘制调用全 mock——鸭子窗驱动，
    不建窗；GL 显示依赖时随既有 GL 类跳过口径不适用（本类零 GL 需求）。
    〔修复（2026-10-13 门禁红）：draw_trails 标签块经 fit_text→真 text_width
    （arcade.Text 需活动窗——无显示会话 RuntimeError: No window is active）——
    本类统一 patch hud_top.text_width 为确定性 CJK 估算量尺
    （tests/test_hud_geometry._est_width 同款），断言口径=该量尺下的绘制调用。〕"""

    @staticmethod
    def _est_width(text, size):
        return size * sum(2 if ord(ch) > 0x2E7F else 1 for ch in str(text))

    @classmethod
    def setUpClass(cls):
        import unittest.mock as mock
        from sovs.ui import hud_top, scene
        # 双绑定全 patch：hud_top 模块全局（fit_text 内部解析）＋scene 自有
        # `from .hud_top import text_width` 绑定（draw_trails 标签块直调）——
        # 显示会话有无两态下均不触真 arcade.Text（需活动窗）。
        cls._rulers = [mock.patch.object(hud_top, "text_width", cls._est_width),
                       mock.patch.object(scene, "text_width", cls._est_width)]
        for r in cls._rulers:
            r.start()

    @classmethod
    def tearDownClass(cls):
        for r in cls._rulers:
            r.stop()

    @staticmethod
    def _duck(unit_entry, trail=()):
        from types import SimpleNamespace
        return SimpleNamespace(
            frame={"units": [unit_entry]},
            fsm=SimpleNamespace(selected=(unit_entry["id"],)),
            session=SimpleNamespace(cmd=SimpleNamespace(trail=list(trail))),
            cm_to_px=lambda x, y: (float(x) / 100.0, float(y) / 100.0),
            _viewport_px=lambda: (0, 0, 1280, 800))

    def test_draw_move_paths_line_count_covers_waypoints(self):
        """选中带 move_path 单位→draw_move_paths 无异常；draw_line 次数≥航点数
        （2 航点=2 段实线）；追加排队令→虚线分段使调用数再增。"""
        import unittest.mock as mock
        from sovs.ui import scene
        entry = {"id": 1, "team": 0, "pos_cm": [0, 0],
                 "move_path": [[1000, 0], [1000, 1000]], "queued": []}
        with mock.patch("arcade.draw_line") as dl, \
                mock.patch("arcade.draw_circle_outline"), \
                mock.patch("arcade.draw_circle_filled"):
            scene.draw_move_paths(self._duck(entry))
            solid = dl.call_count
        self.assertGreaterEqual(solid, 2)                 # ≥航点数
        entry["queued"] = [[[2000, 1000]]]                # Shift 排队令
        with mock.patch("arcade.draw_line") as dl2, \
                mock.patch("arcade.draw_circle_outline"), \
                mock.patch("arcade.draw_circle_filled"):
            scene.draw_move_paths(self._duck(entry))
            dashed_total = dl2.call_count
        self.assertGreater(dashed_total, solid)           # 虚线分段>纯实线段数

    def test_trail_degenerates_when_real_path_present(self):
        """trail 退化：单位有 move_path 时 draw_trails 不画该单位『当前位→落点』
        直线（draw_line 计数 0）；无路径时 1 段。"""
        import unittest.mock as mock
        from sovs.ui import scene
        trail = [{"kind": "move", "unit_ids": [1], "point_cm": [5000, 5000],
                  "tick": 1, "mode": "NORMAL"}]
        entry = {"id": 1, "team": 0, "pos_cm": [0, 0],
                 "move_path": [[1000, 0]], "queued": []}
        with mock.patch("arcade.draw_line") as dl, \
                mock.patch("arcade.draw_circle_outline"), \
                mock.patch("arcade.draw_text"), \
                mock.patch("arcade.draw_lrbt_rectangle_filled"):
            scene.draw_trails(self._duck(entry, trail))
            self.assertEqual(dl.call_count, 0)            # 有路径=0 段
        entry["move_path"] = []
        with mock.patch("arcade.draw_line") as dl2, \
                mock.patch("arcade.draw_circle_outline"), \
                mock.patch("arcade.draw_text"), \
                mock.patch("arcade.draw_lrbt_rectangle_filled"):
            scene.draw_trails(self._duck(entry, trail))
            self.assertEqual(dl2.call_count, 1)           # 无路径=1 段（旧行为）

    def test_trail_cross_marker_strokes_locked(self):
        """cross 分型痕迹标记（air_call/air_strike/air_airdrop——_TRAIL_STYLE）
        两笔坐标锁：横笔 y0=y1=py、竖笔 x0=x1=px。〔终审第四批回归锁：B1 编辑
        块曾误伤竖笔第三参 px→py（px≠py 落点竖笔变斜线，全量绿未拦——本类原只
        测 move/circle）；落点特取 px≠py（50,30），笔误态 (50,22,30,38) 即红。〕"""
        import unittest.mock as mock
        from sovs.ui import scene
        trail = [{"kind": "air_strike", "unit_ids": (),
                  "point_cm": [5000, 3000], "tick": 1}]    # →px(50,30)
        entry = {"id": 1, "team": 0, "pos_cm": [0, 0],
                 "move_path": [], "queued": []}
        with mock.patch("arcade.draw_line") as dl, \
                mock.patch("arcade.draw_circle_outline"), \
                mock.patch("arcade.draw_text"), \
                mock.patch("arcade.draw_lrbt_rectangle_filled"):
            scene.draw_trails(self._duck(entry, trail))
            strokes = {tuple(c.args[:4]) for c in dl.call_args_list}
        self.assertEqual(len(strokes), 2)                  # 恰两笔（无连线干扰）
        self.assertIn((42.0, 30.0, 58.0, 30.0), strokes)   # 横笔 y 两端=py±8
        self.assertIn((50.0, 22.0, 50.0, 38.0), strokes)   # 竖笔 x 两端=px±8


class TestAirTrailFromAircraft(unittest.TestCase):
    """〔2026-10-15 六条修正·问题6〕空中令 trail 线自**本机当前帧位置**起绘。

    根因：trail.unit_ids 记飞机 id，而位置表只建自地面单位——单位/飞机两套
    计数器都自 1 起，撞号时线从错误的地面单位位置起画、不撞号时不绘。修复=
    draw_trails 按 kind 分流位置表（air_* 查飞机帧位）。无 GL 需求（arcade
    绘制全 mock——TestMovePathRendering 同族口径）。"""

    @staticmethod
    def _est_width(text, size):
        return size * sum(2 if ord(ch) > 0x2E7F else 1 for ch in str(text))

    @classmethod
    def setUpClass(cls):
        import unittest.mock as mock
        from sovs.ui import hud_top, scene
        cls._rulers = [mock.patch.object(hud_top, "text_width", cls._est_width),
                       mock.patch.object(scene, "text_width", cls._est_width)]
        for r in cls._rulers:
            r.start()

    @classmethod
    def tearDownClass(cls):
        for r in cls._rulers:
            r.stop()

    @staticmethod
    def _duck(*, units=(), aircraft=(), trail=()):
        from types import SimpleNamespace
        return SimpleNamespace(
            frame={"units": list(units), "aircraft": list(aircraft)},
            fsm=SimpleNamespace(selected=()),
            session=SimpleNamespace(cmd=SimpleNamespace(trail=list(trail))),
            cm_to_px=lambda x, y: (float(x) / 100.0, float(y) / 100.0),
            _viewport_px=lambda: (0, 0, 1280, 800))

    def test_air_move_trail_starts_from_aircraft_not_colliding_unit(self):
        """撞号回归锚：飞机 id=1 与地面单位 id=1 撞号——线须自飞机位 (50,50) 起，
        不得自地面单位位 (10,0) 起（修前=错误地面起点）。"""
        import unittest.mock as mock
        from sovs.ui import scene
        units = [{"id": 1, "team": 0, "pos_cm": [1000, 0],
                  "move_path": [], "queued": []}]
        aircraft = [{"id": 1, "team": 0, "pos_cm": [5000, 5000]}]
        trail = [{"kind": "air_move", "unit_ids": [1],
                  "point_cm": [9000, 9000], "tick": 1}]
        with mock.patch("arcade.draw_line") as dl, \
                mock.patch("arcade.draw_circle_outline"), \
                mock.patch("arcade.draw_text"), \
                mock.patch("arcade.draw_lrbt_rectangle_filled"):
            scene.draw_trails(self._duck(units=units, aircraft=aircraft,
                                         trail=trail))
        starts = {(c.args[0], c.args[1]) for c in dl.call_args_list}
        self.assertIn((50.0, 50.0), starts)        # 自飞机当前位起绘
        self.assertNotIn((10.0, 0.0), starts)      # 不自撞号地面单位位起绘
        self.assertIn((50.0, 50.0, 90.0, 90.0),
                      {tuple(c.args[:4]) for c in dl.call_args_list})

    def test_ground_trail_unchanged_by_air_table(self):
        """地面令行为零变：无飞机帧时 move 线仍自地面单位位起绘。"""
        import unittest.mock as mock
        from sovs.ui import scene
        units = [{"id": 2, "team": 0, "pos_cm": [2000, 0],
                  "move_path": [], "queued": []}]
        trail = [{"kind": "move", "unit_ids": [2],
                  "point_cm": [8000, 0], "tick": 1, "mode": "NORMAL"}]
        with mock.patch("arcade.draw_line") as dl, \
                mock.patch("arcade.draw_circle_outline"), \
                mock.patch("arcade.draw_text"), \
                mock.patch("arcade.draw_lrbt_rectangle_filled"):
            scene.draw_trails(self._duck(units=units, trail=trail))
        self.assertIn((20.0, 0.0, 80.0, 0.0),
                      {tuple(c.args[:4]) for c in dl.call_args_list})

    def test_task_mark_lines_from_aircraft_all_three_kinds(self):
        """三态任务线统一自飞机当前位置 (50,50) 起：patrol→圆心/strike→目标
        （既有不回归）/airdrop→落点。"""
        import unittest.mock as mock
        from sovs.ui import scene
        win = self._duck(aircraft=[{"id": 1, "team": 0,
                                    "pos_cm": [5000, 5000]}])
        win.cam_scale = 1.0
        cases = (
            ({"kind": "patrol", "center": [8000, 8000], "radius": 500},
             (50.0, 50.0, 80.0, 80.0)),
            ({"kind": "strike", "target": [6000, 6000]},
             (50.0, 50.0, 60.0, 60.0)),
            ({"kind": "airdrop", "drop": [7000, 7000]},
             (50.0, 50.0, 70.0, 70.0)),
        )
        for task, want in cases:
            with self.subTest(kind=task["kind"]):
                a = {"id": 1, "task": task}
                with mock.patch("arcade.draw_line") as dl, \
                        mock.patch("arcade.draw_circle_outline"), \
                        mock.patch("arcade.draw_text"):
                    scene.draw_task_mark(win, a, 50.0, 50.0)
                strokes = {tuple(c.args[:4]) for c in dl.call_args_list}
                self.assertIn(want, strokes)       # (px,py)→任务点连线在册


class TestBoxResidueRemoved(unittest.TestCase):
    """B2 源码级断言（无头可跑，不建窗不导入渲染件）：残留白框属性全仓代码
    引用归零——初始化/写入/绘制三分支删除后，scene/shell_window 源内不得再
    出现该标识。"""

    def test_no_last_box_token_in_sources(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in ("sovs/ui/scene.py", "sovs/ui/shell_window.py"):
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                self.assertNotIn("_last_box", fh.read(), rel)


if __name__ == "__main__":
    unittest.main()
