"""FE-T03 架构约束守卫（AST 静态断言）：

- ① sovs/sim/*.py 零渲染导入（禁 arcade/pyglet/pygame/tkinter/OpenGL/PIL）且
  stdlib-only——pydantic 例外落成显式文件级白名单常量：仅 card_schema.py
  （全 sim 包唯一 pydantic import 实证 card_schema.py:40；pyproject.toml 注释
  同口径「card_loader 及其余 sim 模块 stdlib-only」）。白名单外出现即红，
  新增 pydantic 消费必须先改清单留痕。
- ② 渲染/逻辑接线归属：sovs/ui/** 中唯 cmd_bus.py 允许 import sovs.sim（限
  tick/types 命令类+queue_command 命令通道），其余模块（viewer_window/
  shell_window/timeline/palette/glyphs/shell_fsm）禁 import sovs.sim 与
  sovs.ai——渲染件只消费 dict 帧与回调；Replayer/world_tick/state_frame/
  KevPlayer 等仿真驱动只存在于 tools/replay_viewer.py 与 tools/skirmish_shell.py
  的 session 胶水层（两入口文件头注明同一纪律）。sovs/ui 目录暂未落地时本组
  断言空转通过（文件落地即受守卫约束）。
"""
import ast
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "sovs" / "sim"
UI_DIR = ROOT / "sovs" / "ui"

# 渲染库禁入清单（sovs/sim 零渲染——含各自顶层包名/绑定名变体）
RENDER_BAN = frozenset({"arcade", "pyglet", "pygame", "_pygame",
                        "tkinter", "_tkinter", "OpenGL", "PIL"})

# pydantic 例外：显式文件级白名单（新增消费必须先改此处留痕——见头注①）
PYDANTIC_WHITELIST = frozenset({"card_schema.py"})

# cmd_bus.py 允许自 sovs.sim.tick import 的符号面：命令类（*Cmd）+ queue_command
_CMD_BUS_TICK_ALLOWED_EXTRA = frozenset({"queue_command"})
# sovs/ui 模块清单（GP-01 §5.2 拆分后全目录——新模块落地先在此登记归属再写文件；
# B3 修复块 2026-10-13 +order_filter：命令格三态过滤纯逻辑件，禁 import sovs.sim）
_UI_SIM_BANNED_MODULES = ("viewer_window", "shell_window", "timeline",
                          "palette", "glyphs", "shell_fsm",
                          "hud_top", "hud_bottom", "minimap", "scene",
                          "selection_panel", "fm_panel", "deck_editor_page",
                          "order_filter", "order_icons",
                          "keybinds", "settings_page")


def _imported_tops(node: ast.AST):
    """AST 节点内全部 import 顶层模块名（import x.y / from x.y import z → x）。
    含函数体内 import（wire.py importlib 惰性导入配套的常规模块 import 也在面）。"""
    tops = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            for alias in n.names:
                tops.add(alias.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom) and n.module is not None:
            if n.level == 0:                       # 相对导入另行归属（sovs.*）
                tops.add(n.module.split(".")[0])
    return tops


def _from_sovs_imports(node: ast.AST):
    """(sovs 子模块 dotted 名, 导入符号集) 列表——`from sovs.sim.tick import X, Y`
    → ("sovs.sim.tick", {"X","Y"})；`import sovs.sim.tick` → ("sovs.sim.tick", None)。"""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("sovs"):
            out.append((n.module, {a.name for a in n.names}))
        elif isinstance(n, ast.Import):
            for alias in n.names:
                if alias.name.startswith("sovs"):
                    out.append((alias.name, None))
    return out


class TestSimStdlibOnlyNoRender(unittest.TestCase):
    """① sim 包零渲染导入 + stdlib-only（pydantic 白名单外即红）。"""

    def test_sim_modules(self):
        files = sorted(SIM_DIR.glob("*.py"))
        self.assertGreaterEqual(len(files), 10)    # 目录存在性防呆（含 wire.py）
        for f in files:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            tops = _imported_tops(tree)
            with self.subTest(module=f.name):
                banned = tops & RENDER_BAN
                self.assertFalse(banned, "%s 渲染库导入：%s" % (f.name, sorted(banned)))
                for top in tops:
                    allowed = (top in sys.stdlib_module_names
                               or top == "sovs"
                               or (top == "pydantic"
                                   and f.name in PYDANTIC_WHITELIST))
                    self.assertTrue(
                        allowed,
                        "%s 非 stdlib 导入 %r（pydantic 白名单=%s——新增消费先改清单）"
                        % (f.name, top, sorted(PYDANTIC_WHITELIST)))


class TestUiLayerWiringOwnership(unittest.TestCase):
    """② sovs/ui 接线归属：唯 cmd_bus.py 通 sovs.sim（限命令通道），余者禁。"""

    def test_ui_import_policy(self):
        if not UI_DIR.is_dir():
            self.skipTest("sovs/ui 尚未落地（FE-T02 观战层）——落地即受本守卫约束")
        files = sorted(p for p in UI_DIR.rglob("*.py"))
        self.assertTrue(files)
        for f in files:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            with self.subTest(module=str(f.relative_to(ROOT))):
                sim_imports = [(m, s) for m, s in _from_sovs_imports(tree)
                               if m == "sovs.sim" or m.startswith("sovs.sim.")
                               or m == "sovs.ai" or m.startswith("sovs.ai.")]
                if f.name == "cmd_bus.py":
                    # 限 tick/types 命令类 + queue_command 命令通道
                    for mod, symbols in sim_imports:
                        if mod.startswith("sovs.ai"):
                            self.fail("cmd_bus 不得 import sovs.ai：%s" % mod)
                        self.assertIn(mod, ("sovs.sim.tick", "sovs.sim.types"),
                                      "cmd_bus 只许 tick/types：%s" % mod)
                        if symbols is None:
                            continue               # import sovs.sim.tick 整模块（符号面宽——tick/types 限内）
                        for sym in symbols:
                            ok = (mod == "sovs.sim.types" or sym.endswith("Cmd")
                                  or sym in _CMD_BUS_TICK_ALLOWED_EXTRA)
                            self.assertTrue(
                                ok, "cmd_bus 自 %s import 非命令通道符号 %r"
                                % (mod, sym))
                else:
                    self.assertFalse(
                        sim_imports,
                        "渲染件禁 import sovs.sim/sovs.ai（只消费 dict 帧与回调）：%s"
                        % [m for m, _ in sim_imports])

    def test_ui_module_roster_names_are_reserved_for_policy(self):
        # 预期模块清单（viewer_window/shell_window/timeline/palette/glyphs/
        # shell_fsm）落地即进入②的禁 import 面——本断言防清单与实际文件名漂移。
        # 勘正（FE-T06 落地激活时发现）：原写法拿无后缀名比对 .py 文件名必红
        # （目录未落地期空转未暴露）——清单补 .py 后缀归一，意图不变。
        if not UI_DIR.is_dir():
            self.skipTest("sovs/ui 尚未落地")
        names = {p.name for p in UI_DIR.rglob("*.py")}
        known = {m + ".py" for m in _UI_SIM_BANNED_MODULES} | {
            "cmd_bus.py", "__init__.py"}
        unknown = {n for n in names if n not in known}
        self.assertFalse(
            unknown,
            "sovs/ui 出现清单外模块 %s——先在 tests/test_arch_constraints.py "
            "_UI_SIM_BANNED_MODULES 登记归属再落地" % sorted(unknown))


if __name__ == "__main__":
    unittest.main()
