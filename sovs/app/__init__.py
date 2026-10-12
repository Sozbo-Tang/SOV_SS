"""sovs.app 会话胶水层（GP-01 §5.1/§5.3 ★新包）。

分层：sovs/sim 引擎（stdlib-only）→ sovs/ai AI 玩家 → sovs/ui 纯呈现语义层
（AST 守卫②：除 cmd_bus 外禁 import sim/ai——只吃 dict 帧）→ **本包＝会话
胶水**（世界生命周期/命令接线/数据装载/门禁剧本；可 import sim/ai——守卫不
涉）→ tools/ CLI 薄入口（tools/skirmish_shell.py 再出口保既有导入面）。
"""
