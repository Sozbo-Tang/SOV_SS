"""顶栏与浮层绘制（GP-01 §5.2 拆分自 shell_window）：HUD 顶部面——纯呈现。

顶栏三段流式排布（计时→阶段→提示，量尺见 _text_width/_flow_positions——
「|| 命令照收」暂停徽标拉长计时段的防叠压机制）＋右侧三池余量（点数/空援，
GP-01 §4 ①段增冷却段——air_cooldowns 倒计时可视化）＋toast 通道＋F1 帮助
面板＋退出确认覆盖层。本模块只 import arcade＋本包常量/词面（不 import
sovs.sim——tests/test_arch_constraints.py ② 守卫）。
"""
from __future__ import annotations

import arcade

from .palette import (HUD_PANEL, HUD_TEXT, MARGIN, ORDER_ARMED, ORDER_TEXT,  # noqa: E402
                      PHASE_COLORS, TEAM_COLORS, TEAM_NAMES, TOAST_ERROR,
                      TOAST_INFO, TOP_H, TOP_SEG_GAP, WARN_RED)
from .shell_fsm import STATE_CN

_TEXT_W_CACHE: dict[tuple[str, float], float] = {}


def text_width(text: str, font_size: float) -> float:
    """文本像素宽（arcade.Text.content_width——与 draw_text 同默认字体/字号）。

    顶栏左段流式排布的量尺：暂停徽标「|| 命令照收」把计时段拉到 212~232px，
    固定槽位会让白字尾压上红阶段标签（battle.png 视觉复检唯一必修项）。
    缓存键=整串+字号（与 arcade ctx.label_cache 同粒度；字符串集有限）。
    """
    key = (text, font_size)
    w = _TEXT_W_CACHE.get(key)
    if w is None:
        w = arcade.Text(text, 0, 0, arcade.color.WHITE, font_size).content_width
        _TEXT_W_CACHE[key] = w
    return w


def flow_positions(start: float, widths, gap: float = TOP_SEG_GAP):
    """流式段位：各段起点=前段起点+宽+gap（顶栏三段零叠压排布，纯算术可测）。"""
    x = start
    out = []
    for w in widths:
        out.append(x)
        x += w + gap
    return out


def draw_top_bar(win) -> None:
    """顶栏（§11 断箭式重排，实机参照 out/refs/ba_shot4.jpg）：中央=大计时＋
    己方/敌方点数（己左敌右，队色方块标认）＋占点指示行；左=相位/速度徽标＋
    操作提示；右=空援点数＋冷却流。量尺 TOP_H=56 双行。"""
    arcade.draw_lrbt_rectangle_filled(0, win.width, win.height - TOP_H,
                                      win.height, HUD_PANEL)
    frame = win.frame
    phase = str(frame.get("phase", "?"))
    col = PHASE_COLORS.get(phase, HUD_TEXT)
    tick = frame.get("tick", 0)
    cx = win.width / 2
    y1 = win.height - TOP_H + 32          # 主行（计时/点数/相位）
    y2 = win.height - TOP_H + 11          # 次行（占点指示/提示/冷却）
    view = frame.get("view", 0)
    players = list(frame.get("players", ()))
    own = players[view] if view < len(players) else None
    foe = (players[(view + 1) % len(players)]
           if len(players) > 1 else None)

    # ── 中央：大计时＋双方点数＋占点 pips（断箭顶中块）──
    if win.fsm.page == "deploy":
        clock = "部署 %ds" % win.fsm.deploy_seconds_left
    else:
        left = max(0, win.session.total_ticks - tick)
        clock = "%02d:%02d" % (left // 600, (left // 10) % 60)
    if win.fsm.page in ("deploy", "battle") and not win.ctrl.playing:
        clock = "|| " + clock              # 暂停徽标并入计时（暂停零反馈 P2）
    if own is not None:
        oc = TEAM_COLORS.get(view, HUD_TEXT)
        arcade.draw_lrbt_rectangle_filled(cx - 96 - text_width(
            "%d" % own["points"], 15) - 14, cx - 96 - 4, y1 + 1, y1 + 11, oc)
        arcade.draw_text("%d" % own["points"], cx - 96, y1, oc, 15,
                         anchor_x="right")
    arcade.draw_text(clock, cx, y1, HUD_TEXT, 20, anchor_x="center")
    if foe is not None:
        fc = TEAM_COLORS.get((view + 1) % 2, HUD_TEXT)
        fx = cx + 96
        arcade.draw_text("%d" % foe["points"], fx + 14, y1, fc, 15)
        arcade.draw_lrbt_rectangle_filled(fx, fx + 10, y1 + 1, y1 + 11, fc)
    objs = frame.get("objectives", ())
    for i, o in enumerate(objs):
        px = cx - (len(objs) - 1) * 9 + i * 18
        arcade.draw_lrbt_rectangle_filled(px - 5, px + 5, y2 - 2, y2 + 8,
                                          TEAM_COLORS.get(o.get("owner"),
                                                          (150, 150, 150, 255)))

    # ── 左段：相位/速度徽标＋操作提示 ──
    if win.fsm.page in ("deploy", "battle") and not win.ctrl.playing:
        state = "|| 命令照收"
    else:
        state = ">> x%g" % win.ctrl.speed if win.ctrl.playing else "||"
    if win.fsm.page == "deploy":
        head = "盲部署｜点槽装弹→点地放卡（兵出场后自动开进）·右键撤回"
    else:
        head = ("右键移动/盘旋·Q攻·T炮击·K空袭·V高度·B返航·Ctrl+数字编组"
                "·选中卡在左")
    x0, x1 = flow_positions(MARGIN, (text_width(state, 13),
                                     text_width(phase.upper(), 13)))
    arcade.draw_text(state, x0, y1, HUD_TEXT, 13)
    arcade.draw_text(phase.upper(), x1, y1, col, 13)
    arcade.draw_text(head, MARGIN, y2, (170, 170, 160, 255), 11)

    # ── 右段：空援点数＋冷却流（右锚）──
    segs = []
    if own is not None:
        segs.append("空援 %d" % own.get("air_points", 0))
    for name, secs in getattr(win.session, "cooldown_labels", lambda: [])():
        segs.append("%s 冷却%ds" % (name, secs))     # GP-01 §4 冷却可视化
    xr = win.width - 10
    for i, seg in enumerate(segs):
        arcade.draw_text(seg, xr, y1 if i == 0 else y2, HUD_TEXT,
                         13 if i == 0 else 11, anchor_x="right")
        xr -= text_width(seg, 13 if i == 0 else 11) + TOP_SEG_GAP


def draw_toasts(win) -> None:
    """toast 通道：视口顶缘中置红/白字＋深底衬条（battle.png 复检②——文字压
    地图图元时可读；行距 20px 只承载互异的行，同文重复已在 fsm.notify 聚合）。"""
    l, b, r, t = win._viewport_px()
    cx = (l + r) / 2
    for i, note in enumerate(win.fsm.notifications[:3]):
        col = TOAST_ERROR if note["tone"] == "error" else TOAST_INFO
        w = text_width(note["text"], 13) + 18
        y = t - 24 - i * 20
        arcade.draw_lrbt_rectangle_filled(cx - w / 2, cx + w / 2, y - 4, y + 15,
                                          (10, 12, 10, 205))
        arcade.draw_text(note["text"], cx, y, col, 13, anchor_x="center")


# F1 帮助面板键位速查（两栏；核心键＋镜头/飞机族——GP-01 §4/§6 扩容后全集；
# P0 键位纠偏块 2026-10-13：Q 攻/SHIFT 排队/U 双击/O 画区/WASD 平移——手册
# HOTKEYS manual.txt:547-580）
_HELP_KEYS_LEFT = (
    "左键：点选/框选（Shift 点己方=加减选）", "右键：移动（Shift=追加路径点）",
    "Q+左键：攻击移动/齐射   S：停止   E：取消", "R+左键：倒车   F+左键：行军",
    "T+左键/拖拽：炮击（点/线/徐进/精确）", "K+左键/拖拽：空袭（点目标/画攻击轴）",
    "O+左键拖拽：空投画区（单击=点投）", "X：自卫烟幕   G：组合",
    "H：纪律（受击才还击·保持瞄准）   L：狙击观测", "U：卸载（再按=就地卸载）",
    "N+点敌：激光照射   P+点地：精密打击（近激光位）",
    "M+点己方载具：登车   B：回基地（到场退款≥20%）",
    "C：诱饵（手动投放）   Z：冲刺/加力/雷达（按单位分派）",
    "Shift+确认：命令入队（连续下令排队执行）",
)
_HELP_KEYS_RIGHT = (
    "飞机：V 高度(toggle) B 返航 J 对空 Y 脱离", "Z（飞机）：加力 toggle   C：诱饵",
    "左轨空援卡＋地面呼援卡（实战随时可呼）", "选中补给堆：买1t/4t/满+四开关",
    "SPACE：暂停（下令照收）   +/-：调速", "方向键/WASD：平移   贴边：边缘滚动",
    "滚轮：缩放（下限=整图适配）", "小地图：左键跳转 / 右键下令",
    "Ctrl+1..9：建组   1..9：取组   TAB：子选（下令只对焦点）", "F1：本面板   ESC：分层取消",
)


def draw_help_overlay(win) -> None:
    """F1 帮助/键位面板（覆盖层；再按 F1 或 ESC 首层关闭，不阻断其他操作）。"""
    if not win.fsm.help_open:
        return
    w, h = 860, 440
    x0, y0 = (win.width - w) / 2, (win.height - h) / 2
    arcade.draw_lrbt_rectangle_filled(x0, x0 + w, y0, y0 + h, (8, 10, 8, 242))
    arcade.draw_lrbt_rectangle_outline(x0, x0 + w, y0, y0 + h,
                                       ORDER_TEXT, 2)
    arcade.draw_text("键位与操作（F1/ESC 关闭）", win.width / 2,
                     y0 + h - 36, ORDER_ARMED, 18, anchor_x="center")
    for i, line in enumerate(_HELP_KEYS_LEFT):
        arcade.draw_text(line, x0 + 36, y0 + h - 78 - i * 30, HUD_TEXT, 13)
    for i, line in enumerate(_HELP_KEYS_RIGHT):
        arcade.draw_text(line, x0 + w / 2 + 26, y0 + h - 78 - i * 30,
                         HUD_TEXT, 13)
    arcade.draw_text("页面门：部署期可 S/E/R/Z/F+编组；战斗令在实战页开放"
                     "（G 组合含禁火姿态）；炮击三段式=T 待令→参数条→点地/画线",
                     win.width / 2, y0 + 14, (170, 170, 160, 255), 11,
                     anchor_x="center")


def draw_exit_confirm(win) -> None:
    """退出确认覆盖层（ESC 分层链末层——防误触丢整局）。"""
    if not win.fsm.exit_confirm:
        return
    w, h = 420, 90
    x0, y0 = (win.width - w) / 2, (win.height - h) / 2
    arcade.draw_lrbt_rectangle_filled(x0, x0 + w, y0, y0 + h, (60, 14, 14, 242))
    arcade.draw_lrbt_rectangle_outline(x0, x0 + w, y0, y0 + h, WARN_RED, 2)
    arcade.draw_text("再按 ESC 退出（将丢弃本局）· 其他键/点击取消",
                     win.width / 2, y0 + h / 2 - 8, HUD_TEXT, 14,
                     anchor_x="center")


def phase_label(phase: str) -> str:
    """相位中文名（结算页/顶栏共用——STATE_CN 词面）。"""
    return STATE_CN.get(phase, phase)


# ── 结算面（GP-01 §5.2 拆分自 shell_window——结算 HUD 家族）──

def draw_settle_panel(win, result: dict | None) -> None:
    """结算屏：读帧 result（D031 三级裁决证据）。"""
    w, h = 560, 240
    x0, y0 = (win.width - w) // 2, (win.height - h) // 2
    arcade.draw_lrbt_rectangle_filled(x0, x0 + w, y0, y0 + h, (10, 12, 10, 242))
    arcade.draw_lrbt_rectangle_outline(x0, x0 + w, y0, y0 + h,
                                       arcade.color.WHITE, 2)
    if result is None:
        arcade.draw_text("== 对局终止（无结算数据） ==", win.width / 2,
                         y0 + h - 44, HUD_TEXT, 18, anchor_x="center")
        return
    winner = result.get("winner")
    if winner is None:
        title, tcol = "平局", HUD_TEXT
    else:
        title = "%s 胜" % TEAM_NAMES.get(winner, "队%d" % winner)
        tcol = arcade.color.WHITE
    arcade.draw_text("== 结算：%s ==" % title, win.width / 2, y0 + h - 46,
                     tcol, 22, anchor_x="center")

    def _row(label, vals, yy):
        arcade.draw_text(label, x0 + 28, yy, HUD_TEXT, 13)
        arcade.draw_text("红方 %-10s 蓝方 %-10s" % tuple(
            "?" if not vals else v for v in vals[:2]),
            x0 + 268, yy, HUD_TEXT, 13)

    _row("占点分（第一级）", result.get("obj_counts"), y0 + h - 86)
    _row("剩余单位分值（第二级）", result.get("unit_scores"), y0 + h - 118)
    _row("剩余总血量（第三级）", result.get("hp_totals"), y0 + h - 150)


# 结算统计分组（trail kind → 复盘组——GP-01 §4/§6 扩容后全集）
_STATS_GROUP = {"move": "move", "stop": "move", "cancel": "move",
                "reverse": "move", "sprint": "move", "march": "move",
                "attack": "attack",
                "fire_mission": "fire_mission",
                "cancel_fire_mission": "fire_mission",
                "air_call": "air", "air_strike": "air", "air_airdrop": "air",
                "air_patrol": "air", "air_move": "air", "air_reset": "air",
                "air_alt": "air", "air_rtb": "air",
                "air_engage_air": "air", "air_disengage": "air",
                "smoke_sprint": "smoke_sprint", "smoke": "smoke_sprint",
                "stance": "smoke_sprint",
                "unload": "support", "sniper_cover": "support",
                "ambush": "support", "deploy": "support", "pack": "support",
                "tow": "support", "untow": "support", "formation": "support",
                "supply_dock": "support", "mount": "support",
                # ── P1 机制块（2026-10-13）──
                "ground_rtb": "support", "laser_designate": "support",
                "radar": "support", "supply_switch": "support",
                "buy_supplies": "support",
                "air_afterburner": "air", "air_decoy": "air",
                "precision": "fire_mission"}


def draw_command_stats(win) -> None:
    """结算页命令统计：trail 按组汇总+无效操作（被拒）计数——复盘面。"""
    trail = getattr(win.session.cmd, "trail", ())
    counts = {"move": 0, "attack": 0, "fire_mission": 0, "air": 0,
              "smoke_sprint": 0, "support": 0}
    for tr in trail:
        g = _STATS_GROUP.get(tr["kind"])
        if g is not None:
            counts[g] += 1
    y0 = (win.height - 240) // 2 - 96
    arcade.draw_text("本局命令统计：移动 %d｜攻击 %d｜炮兵 %d｜空军 %d｜烟幕 %d｜"
                     "支援 %d｜无效操作被拒 %d"
                     % (counts["move"], counts["attack"],
                        counts["fire_mission"], counts["air"],
                        counts["smoke_sprint"], counts["support"],
                        win.fsm.rejected_count),
                     win.width / 2, y0, HUD_TEXT, 12, anchor_x="center")
    arcade.draw_text("Enter=再来一局（保留上局配置）｜ESC=退出",
                     win.width / 2, y0 - 24, HUD_TEXT, 12, anchor_x="center")
