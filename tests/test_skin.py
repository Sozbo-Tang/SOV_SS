"""FE-05 F8 皮肤统一测试：光标映射纯逻辑 / 皮肤资产在场 / AST 守卫 /
七页实渲染 vs 基线逐张 diff ≥0.01（GL 类）。"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.ui.shell_fsm import ShellFsm                              # noqa: E402

try:
    import arcade                                    # noqa: F401（探针）
    from tests._gl_probe import gl_window_available
    HAS_GL_WINDOW = gl_window_available()
except Exception:                                    # noqa: BLE001
    HAS_GL_WINDOW = False

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _duck_win(page="battle", mouse=None, armed=None, purchase=None):
    fsm = ShellFsm()
    fsm.page = page
    fsm.armed_order = armed
    fsm.armed_purchase = purchase
    win = SimpleNamespace(fsm=fsm, _mouse_xy=mouse,
                          frame={"units": [], "aircraft": [], "view": 0},
                          width=1280, height=800)
    return win


class TestCursorMapping(unittest.TestCase):

    def test_context_kind_rules(self):
        from sovs.ui.cursor import context_kind
        self.assertEqual(context_kind(_duck_win(page="config")), "default")
        self.assertEqual(context_kind(_duck_win(armed="attack")), "attack")
        self.assertEqual(context_kind(_duck_win(armed="fire_mission")),
                         "target")
        self.assertEqual(context_kind(_duck_win(purchase=(1, "x"))), "target")
        self.assertEqual(context_kind(_duck_win(armed="march")), "move")
        self.assertEqual(context_kind(_duck_win()), "default")   # 无悬停
        # 悬停己方单位（scene.hit_unit 鸭子面——真单位由 GL 链承载）
        win = _duck_win(mouse=(640, 400))
        win.frame = {"units": [{"id": 1, "team": 0, "pos_cm": [0, 0]}],
                     "aircraft": [], "view": 0}
        win.cam_scale = 1.0
        win.cam_cx = win.cam_cy = 0.0
        import unittest.mock as mock
        from sovs.ui import scene as scene_mod
        with mock.patch.object(scene_mod, "hit_unit",
                               return_value={"id": 1}) as hu:
            self.assertEqual(context_kind(win), "select")
            hu.assert_called_once()

    def test_hotspots_loaded(self):
        from sovs.ui.cursor import hotspots
        hs = hotspots()
        self.assertIn("cur_default", hs)
        self.assertIn("cur_move", hs)
        self.assertEqual(hs["cur_move"], [2, 2])     # 规格热点（左上角尖）

    def test_cursor_assets_mapped(self):
        from sovs.ui import assets
        for k in ("cur_default", "cur_select", "cur_attack", "cur_target",
                  "cur_move"):
            self.assertIsNotNone(assets.cursor_tex(k), k)


class TestSkinAssets(unittest.TestCase):

    def test_panel_skins_mapped(self):
        from sovs.ui import assets
        for name in ("panel_topbar", "chip_timer", "panel_select",
                     "panel_air", "panel_fm", "rail_bg", "panel_deploy_left",
                     "panel_deck_pool", "settings_row", "keycap",
                     "btn_generic_30", "btn_generic_30_hover",
                     "btn_generic_30_pressed", "btn_generic_30_selected",
                     "btn_generic_30_disabled", "btn_generic_36",
                     "btn_rail", "btn_lane", "btn_primary",
                     "group_slot", "group_slot_selected", "group_slot_dead",
                     "minimap_frame", "minimap_terrain", "banner_win_red",
                     "badge_victory", "row_obj"):
            self.assertIsNotNone(assets.ui_tex(name)
                                 or assets.terrain_tex(name)
                                 or assets.settle_tex(name), name)

    def test_button_skin_tone_mapping(self):
        from sovs.ui import assets
        from sovs.ui.hud_bottom import Btn
        b = Btn(0, 0, 92, 20, "stop", "停止(S)")          # 矮钮→30 族
        self.assertEqual(assets.button_skin(b), "btn_generic_30")
        self.assertEqual(assets.button_skin(b, armed=True),
                         "btn_generic_30_selected")
        self.assertEqual(assets.button_skin(Btn(0, 0, 92, 20, "k", "x",
                                                tone="disabled")),
                         "btn_generic_30_disabled")
        rail = Btn(0, 0, 216, 24, "buy:1|x", "x")
        self.assertEqual(assets.button_skin(rail), "btn_rail")
        lane = Btn(0, 0, 92, 30, "lane0", "x")
        self.assertEqual(assets.button_skin(lane), "btn_lane")

    def test_ast_no_sim_no_pil(self):
        for rel in ("sovs/ui/cursor.py", "sovs/ui/assets.py"):
            src = open(os.path.join(_ROOT, rel), encoding="utf-8").read()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    tops = {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    tops = {node.module.split(".")[0]}
                else:
                    continue
                self.assertNotIn("PIL", tops, rel)
                self.assertNotIn("sovs", tops, rel)


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
def _drive_fe05_pages(cls, width: int, height: int) -> None:
    """TestSkinStructure 共享驱动（R3 1-4：1280×800 与 1600×900 两档复用）：
    menu→config→deck_edit/over→deploy→battle_empty→battle→los 九页快照到
    cls.tmp；记录 cls.grid_rect（选区态命令格）/los_anchor/los_range_cm。
    win 保活（几何与 text_width 量尺面）。"""
    import tempfile
    from sovs.app.scripts import ScriptedPilot
    from sovs.app.session import SkirmishSession
    from sovs.ui.deck_editor_page import deck_revalidate
    from sovs.ui.shell_window import ShellWindow
    cls.tmp = tempfile.mkdtemp()
    cls.session = SkirmishSession(seed=42)
    cls.pilot = ScriptedPilot(cls.session)
    cls.win = ShellWindow(cls.session, visible=False, width=width,
                          height=height)
    cls.grid_rect = None                    # battle 选区态命令格（tile 断言用）
    # ⓪ menu → ① config → ①b deck_edit/over（screenshot 同款推进）
    cls.win.fsm.open_menu()
    cls.win._layout_buttons()
    cls.win.snapshot(os.path.join(cls.tmp, "menu.png"))
    cls.win.fsm.open_config()
    cls.win._layout_buttons()
    cls.win.snapshot(os.path.join(cls.tmp, "config.png"))
    # ①a 设置页（R4.1：config 之后进/出）
    from sovs.ui.settings_page import close_settings, open_settings
    open_settings(cls.win)
    cls.win.snapshot(os.path.join(cls.tmp, "settings.png"))
    close_settings(cls.win)
    ed = cls.session.deck_editor
    cls.win._deck_catalog = ed.catalog()
    cls.win.fsm.open_deck_edit(
        {"deck_key": cls.session.human_deck, "faction": "SOVIET",
         "cards": ed.load_deck(cls.session.human_deck)["cards"],
         "tab": "INFANTRY", "errors": []})
    deck_revalidate(cls.win)
    cls.win._layout_buttons()
    cls.win.snapshot(os.path.join(cls.tmp, "deck_edit.png"))
    over = max((c for c in cls.win._deck_catalog
                if c["faction"] == cls.win.fsm.deck_edit["faction"]),
               key=lambda c: c["cost"])
    for _ in range(over["per_card_limit"] + 1):
        cls.win.fsm.deck_edit_add(over["card_key"])
    deck_revalidate(cls.win)
    cls.win._layout_buttons()
    cls.win.snapshot(os.path.join(cls.tmp, "deck_edit_over.png"))
    cls.win.fsm.close_deck_edit()
    cls.win._layout_buttons()
    # ② deploy ③ battle_empty / battle（选区态记录命令格矩形）
    cls.win.fsm.start_deploy()
    for _ in range(480):
        cls.pilot.step()
        cls.session.advance(1)
    cls.win.refresh()
    cls.win.snapshot(os.path.join(cls.tmp, "deploy.png"))
    while cls.session.world.tick < 2165:
        cls.pilot.step()
        cls.session.advance(1)
    cls.win.refresh()
    mine = [u for u in cls.win.frame["units"] if u["team"] == 0]
    cls.win.fsm.clear_selection()
    cls.win._layout_buttons()
    cls.win.snapshot(os.path.join(cls.tmp, "battle_empty.png"))
    anchor = mine[0]["pos_cm"]
    x0, y0 = cls.win.cm_to_px(anchor[0] - 4000, anchor[1] - 4000)
    x1, y1 = cls.win.cm_to_px(anchor[0] + 4000, anchor[1] + 4000)
    cls.win.select_box_px(x0, y0, x1, y1)
    cls.session.cmd.move(list(cls.win.fsm.selected), (100000, 50000))
    cls.win._layout_buttons()
    from sovs.ui.hud_bottom import order_panel_rect
    cls.grid_rect = order_panel_rect(cls.win)      # 选区态（tile 在绘）
    cls.win.snapshot(os.path.join(cls.tmp, "battle.png"))
    # ③c los 页（范围圈像素断言）＋铭牌锚（默认视角单位屏位）
    cls.los_anchor = None
    cls.los_range_cm = None
    if cls.win.fsm.selected:
        uid = cls.win.fsm.selected[0]
        u = next((x for x in cls.win.frame["units"]
                  if x["id"] == uid), None)
        if u is not None:
            cls.los_anchor = cls.win.cm_to_px(u["pos_cm"][0],
                                              u["pos_cm"][1])
            mouse_cm = cls.win.px_to_cm(*cls.win.cm_to_px(100000, 52000))
            probe = getattr(cls.session, "los_probe", None)
            if probe is not None:
                res = probe(uid, mouse_cm)
                if res is not None:
                    cls.los_range_cm = res["range_cm"]
    cls.win._los_hold = True
    cls.win._mouse_xy = cls.win.cm_to_px(100000, 52000)
    cls.win.snapshot(os.path.join(cls.tmp, "los.png"))
    cls.win._los_hold = False
    cls.win._mouse_xy = None
    # ④ settle（result.png——R3 1-4e 九图完备）
    while cls.session.world.phase != 2:
        cls.pilot.step()
        cls.session.advance(1)
    cls.win.refresh()
    cls.win.snapshot(os.path.join(cls.tmp, "result.png"))


class TestSkinStructure(unittest.TestCase):
    """R1 结构验收（diff 只证明变化、不证明正确——本类不依赖基线 diff 阈值）：
    七页非空 1280×800 / 顶栏皮肤覆盖 / 命令格 tile 底色占比 / 小地图结构 /
    单位卡列宽契约。渲染走 screenshot 同款驱动，win 保活供几何与文字量尺。"""

    @classmethod
    def setUpClass(cls):
        _drive_fe05_pages(cls, 1280, 800)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def _png(self, name):
        return os.path.join(self.tmp, name)

    def test_a_pages_nonempty_1280x800(self):
        from PIL import Image
        for name in ("menu.png", "config.png", "settings.png",  # R4.1：十图
                     "deck_edit.png", "deck_edit_over.png", "deploy.png",
                     "battle_empty.png", "battle.png", "los.png",
                     "result.png"):
            self.assertTrue(os.path.isfile(self._png(name)), name)
            self.assertGreater(os.path.getsize(self._png(name)), 0, name)
            img = Image.open(self._png(name))
            self.assertEqual(img.size, (1280, 800), name)

    def test_b_topbar_skin_covers_over_5pct(self):
        from tools.qa_visual import non_bg_ratio
        ratio = non_bg_ratio(self._png("battle.png"), (0, 0, 1280, 56))
        self.assertGreater(ratio, 0.05, "顶栏非底色占比 %r ≤5%%" % ratio)

    def test_c_order_grid_tile_base_over_20pct(self):
        from PIL import Image
        from tools.qa_visual import count_pixels
        tile = Image.open(os.path.join(
            _ROOT, "assets", "fe", "orders", "cmd_tile.png")).convert("RGB")
        dom = max(tile.getcolors(maxcolors=100000))[1]     # tile 主色
        gx0, gy0, gx1, gy1 = self.grid_rect
        box = (int(gx0) + 2, int(800 - gy1) + 2, int(gx1) - 2, int(800 - gy0) - 2)
        hits = count_pixels(self._png("battle.png"), box,
                            lambda p: max(abs(p[0] - dom[0]),
                                          abs(p[1] - dom[1]),
                                          abs(p[2] - dom[2])) <= 12)
        total = max(1, (box[2] - box[0]) * (box[3] - box[1]))
        self.assertGreater(hits / total, 0.20,
                           "tile 底色占比 %r ≤20%%" % (hits / total))

    def test_d_minimap_structure(self):
        from tools.qa_visual import colors_in_region, count_pixels
        box = (10, 800 - 160, 230, 800)                     # minimap_geom PIL 系
        self.assertGreaterEqual(len(colors_in_region(
            self._png("battle.png"), box)), 3)
        # 视口框=白 180α 叠深色地形 → 实测中性灰 ~185-200（亮行/列实测锚）
        gray = count_pixels(self._png("battle.png"), box,
                            lambda p: min(p) >= 170 and max(p) - min(p) <= 25)
        self.assertGreaterEqual(gray, 4, "视口框灰线像素 %d" % gray)

    def test_f_nameplate_pixels_at_default_zoom(self):
        """R2 1-1：默认视角下铭牌在场——焦点单位下方 6..30px、宽 44px 带
        非底色像素 ≥30（旧阈值 0.06/0.12 下此带只有血条，本断言即红）。"""
        from tools.qa_visual import count_pixels
        px, py = self.los_anchor
        px, py = int(px), int(py)
        box = (px - 22, (800 - py) + 26, px + 22, (800 - py) + 44)
        hits = count_pixels(self._png("battle.png"), box,
                            lambda p: p != (26, 30, 26))
        self.assertGreaterEqual(hits, 30, "铭牌带非底色像素 %d" % hits)

    def test_g_los_ring_pixels(self):
        """R2 2-1：los.png 范围圈可见——单位为心、range_cm×cam_scale 半径
        ±6px 圆环带内非底色像素 ≥20（线宽 3 修复的像素锚）。"""
        from PIL import Image
        if self.los_anchor is None or self.los_range_cm is None:
            self.skipTest("los 锚缺失（选区/probe 不可用）")
        img = Image.open(self._png("los.png")).convert("RGB")
        cx, cy = int(self.los_anchor[0]), int(800 - self.los_anchor[1])
        r = self.los_range_cm * self.win.cam_scale
        hits = 0
        for y in range(max(0, cy - int(r) - 8), min(img.height, cy + int(r) + 8)):
            for x in range(max(0, cx - int(r) - 8), min(img.width, cx + int(r) + 8)):
                d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                if abs(d - r) <= 6 and img.getpixel((x, y)) != (26, 30, 26):
                    hits += 1
        self.assertGreaterEqual(hits, 20, "范围圈环带非底色像素 %d（r=%r）"
                                % (hits, r))

    def test_e_unit_card_column_width_contract(self):
        """R2 非恒真改写（R1 版"fit 后测 fit 宽"任何截断都能过——不能证明
        全文可容纳）：末列 token 全文 fit 不截断＋短 token 无「…」＋长卡名
        允许且必然截断（真 text_width——本类窗保活）。"""
        from sovs.ui.hud_top import fit_text, text_width
        from sovs.ui.unit_card import _COL, col_spans
        spans = col_spans()
        self.assertEqual(_COL[4], 272)                   # R2 末列锚（282 时 SMO...）
        # 末列全文容纳：fit_text 不改写 "SMOKE" 且真宽入列
        self.assertEqual(fit_text("SMOKE", spans[4] - 4, 10), "SMOKE")
        self.assertLessEqual(text_width("SMOKE", 10), spans[4] - 4)
        # 短 token 各归列：不出现「…」
        for tok, col in (("KE", 4), ("HE", 4), ("71/71", 1), ("120", 2)):
            fitted = fit_text(tok, spans[col] - 4, 10)
            self.assertEqual(fitted, tok, "列 %d token %r 被截为 %r"
                             % (col, tok, fitted))
            self.assertLessEqual(text_width(tok, 10), spans[col] - 4)
        # 长卡名：允许截断且截断确实发生（锁截宽行为本身）
        long_name = "莫辛纳甘步枪班组（满编超长武器名）"
        fitted = fit_text(long_name, spans[0] - 4, 10)
        self.assertLess(len(fitted), len(long_name))
        self.assertTrue(fitted.endswith("…"))


@unittest.skipUnless(HAS_GL_WINDOW, "需 fe 渲染栈且显示会话可用")
class TestSkinStructure1600(unittest.TestCase):
    """R3 1-4e：1600×900 双分辨率结构验收——九图存在/非空/尺寸正确、
    顶栏非底色 >5%、命令格 tile 底色 >20%（不依赖基线 diff）。"""

    @classmethod
    def setUpClass(cls):
        _drive_fe05_pages(cls, 1600, 900)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def _png(self, name):
        return os.path.join(self.tmp, name)

    def test_pages_nonempty_1600x900(self):
        from PIL import Image
        for name in ("menu.png", "config.png", "settings.png",  # R4.1：十图
                     "deck_edit.png", "deck_edit_over.png", "deploy.png",
                     "battle_empty.png", "battle.png", "los.png",
                     "result.png"):
            self.assertTrue(os.path.isfile(self._png(name)), name)
            self.assertGreater(os.path.getsize(self._png(name)), 0, name)
            self.assertEqual(Image.open(self._png(name)).size,
                             (1600, 900), name)

    def test_topbar_skin_covers_over_5pct(self):
        from tools.qa_visual import non_bg_ratio
        ratio = non_bg_ratio(self._png("battle.png"), (0, 0, 1600, 56))
        self.assertGreater(ratio, 0.05, "1600×900 顶栏非底色占比 %r" % ratio)

    def test_order_grid_tile_base_over_20pct(self):
        from PIL import Image
        from tools.qa_visual import count_pixels
        tile = Image.open(os.path.join(
            _ROOT, "assets", "fe", "orders", "cmd_tile.png")).convert("RGB")
        dom = max(tile.getcolors(maxcolors=100000))[1]
        gx0, gy0, gx1, gy1 = self.grid_rect
        h = self.win.height
        box = (int(gx0) + 2, int(h - gy1) + 2, int(gx1) - 2, int(h - gy0) - 2)
        hits = count_pixels(self._png("battle.png"), box,
                            lambda p: max(abs(p[0] - dom[0]),
                                          abs(p[1] - dom[1]),
                                          abs(p[2] - dom[2])) <= 12)
        total = max(1, (box[2] - box[0]) * (box[3] - box[1]))
        self.assertGreater(hits / total, 0.20,
                           "1600×900 tile 底色占比 %r" % (hits / total))


class TestNinePatchParamOrder(unittest.TestCase):
    """R1 根因回归：draw_nine_patch 的 LRBT 参数序——宽高/左右上下不得颠倒。"""

    def test_rect_width_height_forwarded(self):
        import unittest.mock as mock
        from sovs.ui import assets
        seen = {}

        class Stub9:
            def __init__(self, l, r, b, t, tex, **kw):
                seen["init"] = (l, r, b, t)

            def draw_rect(self, *, rect, **kw):
                seen["rect"] = rect

        fake = mock.MagicMock()
        fake.cache_name = "r1-lrbt-fake"
        with mock.patch.object(assets.arcade.gui, "NinePatchTexture", Stub9):
            assets.draw_nine_patch((10, 20, 210, 120), fake, corner=16)
        r = seen["rect"]
        self.assertEqual((r.width, r.height), (200, 100))
        self.assertEqual((r.left, r.right, r.bottom, r.top),
                         (10, 210, 20, 120))


class TestSelectedOverlayKeepsAssetSize(unittest.TestCase):
    """R1 回归：selected overlay 资产 12×12 原尺寸四角角标——不得拉成 48px。"""

    def test_scene_selection_white_box_removed(self):
        """R1-4 源级锁：选中白框（SELECT_MARK 26×26 描边）已自 scene 删除——
        选中态唯一呈现=unit_render 四角角标（双重标记回归即红）。"""
        src = open(os.path.join(_ROOT, "sovs", "ui", "scene.py"),
                   encoding="utf-8").read()
        self.assertNotIn("SELECT_MARK", src,
                         "scene 不得再画选中白框（与四角角标双重标记）")

    def _draw(self, selected):
        import unittest.mock as mock
        from sovs.ui import unit_render
        fake = mock.MagicMock()
        fake.size = (12, 12)
        u = {"id": 7, "template_id": 101, "team": 0, "category": 1,
             "hp": 8, "hp_max": 10, "suppressed": False, "moving": False,
             "stance": "weapons_free"}
        win = mock.MagicMock()
        win.fsm.selected = (7,) if selected else ()
        win.cam_scale = 1.0
        with mock.patch.object(unit_render.assets, "overlay_tex",
                               return_value=fake), \
                mock.patch.object(unit_render.arcade,
                                  "draw_texture_rect") as dt, \
                mock.patch.object(unit_render, "draw_nameplate"):
            unit_render.draw_ground_unit(win, u, 0.0, 0.0)
        return [(c.args[1].width, c.args[1].height)
                for c in dt.call_args_list
                if len(c.args) >= 2 and hasattr(c.args[1], "width")]

    def test_selected_corner_marks_at_asset_size(self):
        sizes = self._draw(True)
        self.assertIn((12, 12), sizes)                 # 四角角标原尺寸
        self.assertGreaterEqual(sizes.count((12, 12)), 4)
        self.assertEqual(sizes.count((48, 48)), 1)     # 仅本体一处 48（无拉伸角标）
        self.assertEqual(sizes.count((54, 54)), 1)     # 队色底衬一处

    def test_unselected_no_corner_marks(self):
        sizes = self._draw(False)
        self.assertNotIn((12, 12), sizes)


if __name__ == "__main__":
    unittest.main()
