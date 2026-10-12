#!/usr/bin/env python3
"""单机可玩壳入口（FE-T07 → 交互重设计 v2 → GP-01 §5.3 薄壳化）：vs KEV 遭遇战。

GP-01 §5.3 拆包后本文件＝**CLI 薄入口＋再出口**——会话胶水/剧本/门禁全部
迁入 sovs/app/（session/scripts/qa/screenshot/deck_editor），渲染语义层在
sovs/ui/（cmd_bus/shell_fsm/shell_window…）；既有测试与脚本导入面
（tests/test_skirmish_shell 等）经本文件再出口零改动（迁移提交内全量绿）。

用法（仓库根；四种门禁入口）：
  python3 tools/skirmish_shell.py
    # 交互可玩（arcade 可见窗：四页状态机+框选下令+暂停调速+小地图）
  python3 tools/skirmish_shell.py --smoke
    # 默认配置自动跑一局到结算（人类席=脚本驾驶经 CmdBus 同通道发令）：
    # 五组命令「入队+被消费+World 可断言变化」证据逐条核对＋标准玩法剧本＋
    # GP-01 扩展三段（空中可控链/炮击新模式 LINE·CREEP/编辑器造卡组开一局
    # ——含 SMOKE 弹药位烟弹任务），全绿 exit 0
  python3 tools/skirmish_shell.py --coldstart
    # 冷启动门禁（交互重设计 A11）：隐藏窗经真实事件层走完四页逐项断言
  python3 tools/skirmish_shell.py --screenshot out/qa/
    # 隐藏窗离屏渲染五页 PNG（config/deck_edit/deploy/battle/result）+每张
    # ≥8 色自检 + deploy 图南缘锚点区域采样非底色 ≥1px（A3 护栏）

KEV 档位：--kev rule 规则兜底（缺省零依赖）；--kev local 0.5B 进程内
（MPS 失败自动回退规则）。地图固定 data/gen/map_demo_2km.v1.json；卡组
data/gen/decks 下任意编译产物（GP-01 §7 泛化——编辑器保存后即时可选）；
人类席恒 player0（team0 南）。盲部署计时 600t=60s（tables.py:266 实现现值）。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 再出口（既有导入面零改动——GP-01 §5.3 迁移纪律）──
from sovs.app.qa import coldstart, interactive, smoke  # noqa: E402,F401
from sovs.app.screenshot import screenshot  # noqa: E402,F401
from sovs.app.scripts import ScriptedPilot, StandardPlay  # noqa: E402,F401
from sovs.app.session import (DECKS, HUMAN_INDEX, KEV_INDEX,  # noqa: E402,F401
                              SkirmishSession, build_world)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="单机可玩壳（vs KEV 遭遇战；缺省交互，--smoke/--coldstart/"
                    "--screenshot 门禁）")
    ap.add_argument("--smoke", action="store_true",
                    help="默认配置自动跑一局到结算（证据核对，全绿 exit 0）")
    ap.add_argument("--coldstart", action="store_true",
                    help="冷启动门禁：隐藏窗经真实事件层走完四页并逐项断言")
    ap.add_argument("--screenshot", metavar="DIR",
                    help="隐藏窗离屏渲染五页存 PNG 后退出（需 fe 渲染栈）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--deck", default="su_min",
                    help="卡组键（data/gen/decks 下任意编译产物——GP-01 §7 "
                         "泛化，编辑器产出即时可选）")
    ap.add_argument("--kev", choices=["rule", "local"], default="rule",
                    help="KEV 档位：rule=规则兜底（缺省）；local=0.5B 进程内")
    ap.add_argument("--kev-beat", type=int, default=10,
                    help="KEV 决策节拍（tick；缺省 10=1Hz）")
    args = ap.parse_args(argv)
    if args.smoke:
        return smoke(seed=args.seed, deck=args.deck, kev=args.kev,
                     beat=args.kev_beat)
    if args.coldstart:
        return coldstart(seed=args.seed, deck=args.deck, kev=args.kev)
    if args.screenshot:
        return screenshot(args.screenshot, seed=args.seed, deck=args.deck,
                          kev=args.kev)
    return interactive(seed=args.seed, deck=args.deck, kev=args.kev,
                       beat=args.kev_beat)


if __name__ == "__main__":
    sys.exit(main())
