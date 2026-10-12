"""sovs.ui：前端渲染语义层（FE-T06 观战器起步 → GP-01 §5.2 模块化拆分）。

接线铁律（tests/test_arch_constraints.py ② 守卫）：本包除 cmd_bus.py 外
（限 sovs.sim.tick/types 命令类 + queue_command 通道）**禁止 import
sovs.sim / sovs.ai**——取数只经 dict 状态帧与回调；Replayer/world_tick/
state_frame/KevPlayer 等仿真驱动只存在于会话胶水层（GP-01 §5.3 起为
sovs/app/ 包；tools/skirmish_shell.py 与 tools/replay_viewer.py 为 CLI 薄
入口/再出口）。

模块目录（GP-01 §5.2；新模块落地先在 test_arch_constraints
_UI_SIM_BANNED_MODULES 登记归属）：cmd_bus（发令通道）/shell_fsm（页面状态
机）/palette（色板与布局几何）/glyphs（矢量图元）/timeline（播放控制）/
hud_top（顶栏·浮层·结算）/hud_bottom（底栏四行分组带·面板语义）/scene
（战场图元·相机与命中数学）/minimap（小地图）/selection_panel（右侧常驻
选中面板）/fm_panel（炮击参数条·画线令）/deck_editor_page（战前两页：
config＋卡组编辑器）/shell_window（薄壳 <500 行）/viewer_window（观战器）。
"""
