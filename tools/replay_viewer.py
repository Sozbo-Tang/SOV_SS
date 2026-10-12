#!/usr/bin/env python3
"""回放查看器入口（FE-T03 --smoke 无头校验通道 + FE-T06 观战器三入口）。

层级纪律（FE-01 §5「渲染/逻辑接线归属」——tests/test_arch_constraints.py 守卫）：
本文件与 tools/skirmish_shell.py 是 session 胶水层——Replayer/world_tick/state_frame/
KevPlayer 等仿真驱动**只允许存在于这两个入口**，不得下沉 sovs/ui（渲染件只消费
dict 状态帧与回调；放 sovs/ui 即触发自家守卫）。本文件的 ViewerSession 即胶水
本体：持有 Replayer（sovs/sim/wire）并逐 tick 现场推导状态帧（state_frame）——
不预存全量帧序列，单一事实源=命令流；sovs/ui/viewer_window.py 只经本胶水的
frame/advance/seek 回调取数。

用法（仓库根）：
  python3 tools/replay_viewer.py [data/gen/replays/xxx.jsonl ...]
    # 交互观战（缺省取目录内最新一条黄金回放；多文件时取第一条）
  python3 tools/replay_viewer.py --smoke [data/gen/replays/xxx.jsonl ...]
    # 逐文件 Replayer 全量重放+逐 tick 校验和核对+末帧 result 断言，
    # 全绿打印 OK 退出码 0、任一红即非 0（CI job2 与 FE-T04 本地降级共用口径）；
    # 零参数=缺省展开 REPLAY_DIR 内全部 *.jsonl（门禁实测口径），显式传路径
    # 则按传入清单；纯 Replayer 无窗口路径（惰性 import arcade——未装渲染栈也能跑）
  python3 tools/replay_viewer.py --screenshot out/qa/
    # 隐藏窗口（pyglet visible=False）离屏渲染关键帧存 PNG 后退出
    # （arcade 截帧落盘；命名 viewer_<blue|red|ref>_t<tick>.png 三视角同拍
    #  + viewer_timeline.png + viewer_settle.png + viewer.png 门禁通用名——
    #  代表拍由 _pick_representative_tick 扫描选取（双方存活+迷雾对照成立），
    #  viewer.png=代表拍蓝视角（单位可见且红蓝可辨），不再取终局帧）
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.sim.air import PHASE_SETTLE  # noqa: E402  （session 胶水层——见头注纪律）
from sovs.sim.state_frame import state_frame  # noqa: E402
from sovs.sim.wire import Replayer  # noqa: E402

REPLAY_DIR = os.path.join("data", "gen", "replays")
SEEK_BUDGET_S = 5.0          # seek 验收上限（5s/次——实测记录超时即打印警告）


def all_replays() -> list:
    """--smoke 缺省面：REPLAY_DIR 内全部 *.jsonl（稳定排序；目录空/缺失即报错）。"""
    if not os.path.isdir(REPLAY_DIR):
        raise SystemExit("回放目录不存在：%s（先 python3 tools/record_golden.py 录制）"
                         % REPLAY_DIR)
    jsonls = sorted(os.path.join(REPLAY_DIR, n) for n in os.listdir(REPLAY_DIR)
                    if n.endswith(".jsonl"))
    if not jsonls:
        raise SystemExit("回放目录为空：%s" % REPLAY_DIR)
    return jsonls


def latest_replay() -> str:
    """缺省回放：data/gen/replays/ 内 mtime 最新一条（目录空/缺失即报错）。"""
    return max(all_replays(), key=os.path.getmtime)


class ViewerSession:
    """观战 session 胶水：持有 Replayer，现场逐 tick 推导状态帧供 ui 消费。

    视角映射：team0=红方（录制标签 label="red"）、team1=蓝方（label="blue"——
    record_golden.py KevPlayer 标签口径）；ref=裁判全知（state_frame(None)）。
    """

    _PLAYER_INDEX = {"blue": 1, "red": 0, "ref": None}

    def __init__(self, path: str):
        self.path = str(path)
        self.rep = Replayer(self.path)      # 格式不符（schema/cksum/scenario）即抛
        self.rep.open()
        self.total = self.rep.ticks[-1]
        self.deploy_ticks = int(self.rep.header["phase_ticks"][0])
        self.view = "ref"

    @property
    def cursor(self) -> int:
        return self.rep.cursor

    def frame(self, view: str | None = None) -> dict:
        """当前拍状态帧（现场自 world 推导；视角→玩家号映射见头注）。"""
        return state_frame(self.rep.world,
                           self._PLAYER_INDEX[(view or self.view)])

    def advance(self, n: int) -> int:
        """前进 n 拍（逐拍核对校验和），返回到达拍。"""
        return self.rep.advance(self.rep.cursor + int(n))

    def seek(self, tick: int) -> int:
        """定位到目标拍（重放推导至目标；超 5s 预算打印实测警告）。"""
        t0 = time.perf_counter()
        reached = self.rep.seek(tick)
        dt = time.perf_counter() - t0
        if dt > SEEK_BUDGET_S:
            print("⚠ seek %d→%d 用时 %.2fs（超 %.0fs 验收预算）"
                  % (self.rep.cursor, reached, dt, SEEK_BUDGET_S))
        return reached


def smoke(paths: list) -> int:
    """逐文件 Replayer 校验（全量重放+逐 tick 校验和核对+末帧 result 断言）。

    全绿打印 OK 退出码 0、任一红 1（末帧断言口径：整局黄金回放须走到自然结算
    ——phase=SETTLE 且 result 非空；缺 result=回放被截断或仿真漂移，均红）。
    """
    failed = False
    for path in paths:
        try:
            world = Replayer(path).run()
            if world.phase != PHASE_SETTLE or world.result is None:
                raise ValueError("末帧无结算（phase=%r result=%r）——回放截断或漂移"
                                 % (world.phase, world.result))
            print("✓ %s：重放至 tick %d（相位 %d，逐 tick 校验和全等，result="
                  "winner=%s）" % (path, world.tick, world.phase,
                                  world.result.winner))
        except Exception as exc:                     # noqa: BLE001（CLI 汇总出口）
            failed = True
            print("✗ %s：%s" % (path, exc))
    if not failed:
        print("OK")
    return 1 if failed else 0


def _pick_representative_tick(session: "ViewerSession") -> int:
    """代表拍选取：实战段采样扫描，取**最后**一个合格拍。

    合格判据（三视角迷雾对照与『单位可见且红蓝可辨』两个验证面同时成立）：
    ① 裁判帧双方均有存活单位；② 蓝视角帧内红蓝两色单位各≥1（viewer.png
    承载红蓝可辨证据）；③ 裁判全知可见**实体**（单位+飞机——飞机迷雾位与
    单位独立，本回放红视角单位全见而飞机只见半）严格多于红/蓝单视角。
    取最后合格拍而非首个：交战越深可见面越丰富（接触单位/在空飞机更多）。
    修复动因：此前固定 total//2——黄金回放 golden_air_seed42 蓝方于 6900 拍
    前已全灭，代表拍三视角图无蓝方可显、viewer.png（原取终局蓝视角）更无
    任何完整单位，两验证面双失效（视觉自检 viewer.png/viewer_ref_t6900 条）。
    回退链：无全合格拍→最后双方存活拍→再退实战始拍（截图仍可出、判据降级
    由返回前打印留痕）。
    """
    def _ents(frame: dict) -> int:
        return len(frame["units"]) + len(frame["aircraft"])

    deploy, total = session.deploy_ticks, session.total
    session.seek(deploy)
    stride = 300                       # 与 wire.CHECKPOINT_EVERY 同量级采样步
    last_alive, last_full = None, None
    t = session.cursor
    while t < total:
        ref = session.frame("ref")
        alive0 = sum(1 for u in ref["units"] if u["team"] == 0)
        alive1 = sum(1 for u in ref["units"] if u["team"] == 1)
        if alive0 and alive1:
            last_alive = t
            blue = session.frame("blue")
            red = session.frame("red")
            if (any(u["team"] == 0 for u in blue["units"])
                    and _ents(ref) > _ents(blue) and _ents(ref) > _ents(red)):
                last_full = t
        t = session.advance(min(stride, total - t))
    if last_full is not None:
        return last_full
    if last_alive is not None:
        print("⚠ 实战段无『蓝视角红蓝互见+迷雾严格不对称』采样拍——回退最后"
              "双方存活拍 t=%d（三视角对照验证面降级）" % last_alive)
        return last_alive
    print("⚠ 实战段无双方存活采样拍——回退实战始拍 t=%d" % deploy)
    return deploy


def screenshot(paths: list, out_dir: str) -> int:
    """离屏渲染关键帧存 PNG（隐藏窗 visible=False；spike §4 写法落盘）。"""
    try:
        import arcade                                # 惰性 import（fe 门禁组）
    except ImportError as exc:
        print("✗ --screenshot 需要渲染栈（pip install -e \".[fe]\"）：%s" % exc)
        return 1
    from sovs.ui.viewer_window import ViewerWindow

    path = paths[0]
    os.makedirs(out_dir, exist_ok=True)
    session = ViewerSession(path)
    win = ViewerWindow(session, visible=False)       # pyglet 隐藏窗承载 GL 上下文
    tick_mid = _pick_representative_tick(session)    # 代表拍：双方存活+迷雾对照成立
    print("代表拍 t=%d（总 %d）" % (tick_mid, session.total))
    t0 = time.perf_counter()
    session.seek(tick_mid)
    seek_ms = (time.perf_counter() - t0) * 1000

    def _snap(name: str, view: str, *, hud: bool = True):
        session.view = view
        win.set_view(view)
        win.ctrl.seek(session.cursor)      # HUD tick/时间轴与游标同步（seek 在建窗后）
        win.show_hud = hud
        win.snapshot(os.path.join(out_dir, name))
        return name

    made = []
    # 三视角同拍（迷雾不对称验证面：蓝/红视角可见单位数 < 裁判全知）
    for view in ("blue", "red", "ref"):
        made.append(_snap("viewer_%s_t%d.png" % (view, tick_mid), view))
    made.append(_snap("viewer_timeline.png", "blue"))  # 蓝视角+时间轴/UI 叠层（与 ref 图区分）
    # 门禁通用名 viewer.png：代表拍蓝视角（帧内红蓝单位各≥1——单位可见且
    # 红蓝可辨；此前取终局蓝视角，蓝方全灭后图上无任何完整单位）
    made.append(_snap("viewer.png", "blue"))
    t0 = time.perf_counter()
    session.seek(session.total)                     # 终局帧（结算面板）
    settle_ms = (time.perf_counter() - t0) * 1000
    made.append(_snap("viewer_settle.png", "ref"))

    # 非空非白屏自检：每张 ≥8 色（全白/全黑/纯底即红——知情确认项验收判据）
    from PIL import Image
    ok = True
    for name in made:
        img = Image.open(os.path.join(out_dir, name)).convert("RGB")
        colors = img.getcolors(maxcolors=1_000_000)
        verdict = "✓" if len(colors) >= 8 else "✗"
        ok = ok and len(colors) >= 8
        print("%s %s：size=%s colors=%d" % (verdict, name, img.size, len(colors)))
    print("seek 实测：中段 %.0fms / 终局 %.0fms（预算 %.0fms/次）"
          % (seek_ms, settle_ms, SEEK_BUDGET_S * 1000))
    win.close()
    return 0 if ok else 1


def interactive(paths: list) -> int:
    """交互观战：时间轴+三视角+倍速（arcade 可见窗）。"""
    try:
        import arcade
    except ImportError as exc:
        print("✗ 交互观战需要渲染栈（pip install -e \".[fe]\"）：%s" % exc)
        return 1
    from sovs.ui.viewer_window import ViewerWindow

    if len(paths) > 1:
        print("（多文件仅观战第一条：%s）" % paths[0])
    session = ViewerSession(paths[0])
    win = ViewerWindow(session, visible=True)
    win.center_window()
    arcade.run()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="回放查看器（缺省交互观战；--smoke=无头校验通道（零渲染栈）；"
                    "--screenshot=离屏截帧）")
    ap.add_argument("replays", nargs="*", metavar="REPLAY",
                    help="回放文件（缺省取 %s 内最新一条）" % REPLAY_DIR)
    ap.add_argument("--smoke", nargs="*", metavar="REPLAY",
                    help="逐文件 Replayer 校验（可多个；零参数=%s 内全部 *.jsonl）"
                         % REPLAY_DIR)
    ap.add_argument("--screenshot", metavar="DIR",
                    help="隐藏窗口离屏渲染关键帧存 PNG 后退出（需 fe 渲染栈）")
    args = ap.parse_args(argv)
    try:
        if args.smoke is not None:                 # 旗标在=零参数亦走缺省全展开
            return smoke(args.smoke or all_replays())
        if args.screenshot:
            paths = args.replays or [latest_replay()]
            return screenshot(paths, args.screenshot)
        paths = args.replays or [latest_replay()]
        return interactive(paths)
    except (ValueError, OSError) as exc:             # 格式不符/路径缺误——明确报错拒播
        print("✗ %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
