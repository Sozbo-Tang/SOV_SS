"""截图自检（FE-T07 → GP-01 §5.3 自 tools/skirmish_shell.py 迁入＋M4 增页）。

--screenshot DIR：隐藏窗离屏渲染各页 PNG + 每张 ≥8 色自检 + deploy 图南缘
锚点区域采样非底色 ≥1px（A3 部署可见性回归护栏）。GP-01 M4 增 deck_edit.png
（卡组编辑器页——§7「deck_edit 页 screenshot 自检绿」验收锚）。
"""
from __future__ import annotations

import os

from sovs.app.scripts import ScriptedPilot
from sovs.app.session import SkirmishSession


def screenshot(out_dir: str, seed: int = 42, deck: str = "su_min",
               kev: str = "rule") -> int:
    try:
        import arcade                                    # 惰性 import（fe 门禁组）
    except ImportError as exc:
        print("✗ --screenshot 需要渲染栈（pip install -e \".[fe]\"）：%s" % exc)
        return 1
    from sovs.ui.shell_window import ShellWindow

    os.makedirs(out_dir, exist_ok=True)
    session = SkirmishSession(seed=seed, human_deck=deck, kev_level=kev)
    pilot = ScriptedPilot(session)
    win = ShellWindow(session, visible=False)            # pyglet 隐藏窗承载 GL 上下文
    made = []

    # ① 战前配置页（缺省选项：su_min+规则兜底）
    win.snapshot(os.path.join(out_dir, "config.png"))
    made.append("config.png")

    # ①b 卡组编辑器页（GP-01 §7 M4——deck_edit 页 screenshot 自检锚；目录装填+
    # 现势校验回填与 deck_editor_page.open_deck_editor 同口径——卡池页签/两池
    # 点数条入图，非空摘要）
    from sovs.ui.deck_editor_page import deck_revalidate
    ed = session.deck_editor
    win._deck_catalog = ed.catalog()
    win.fsm.open_deck_edit({"deck_key": session.human_deck, "faction": "SOVIET",
                            "cards": ed.load_deck(session.human_deck)["cards"],
                            "tab": "INFANTRY", "errors": []})
    deck_revalidate(win)
    win._layout_buttons()
    win.snapshot(os.path.join(out_dir, "deck_edit.png"))
    made.append("deck_edit.png")

    # ①b-2 超限态（QA 复检④：超限反馈此前无覆盖图——经 fsm.deck_edit_add 与
    # 真实点卡池同门加卡到限份+1，D032 校验红字+保存禁用灰显入图）
    over = max((c for c in win._deck_catalog
                if c["faction"] == win.fsm.deck_edit["faction"]),
               key=lambda c: c["cost"])
    for _ in range(over["per_card_limit"] + 1):
        win.fsm.deck_edit_add(over["card_key"])
    deck_revalidate(win)
    win._layout_buttons()
    if not win.fsm.deck_edit["errors"]:
        print("✗ deck_edit 超限态无校验红字（%s 加至限份+1 后）"
              % over["card_key"])
        win.close()
        return 1
    print("✓ deck_edit 超限反馈红字在场：%s" % win.fsm.deck_edit["errors"][0])
    win.snapshot(os.path.join(out_dir, "deck_edit_over.png"))
    made.append("deck_edit_over.png")
    win.fsm.close_deck_edit()
    win._layout_buttons()

    # ② 盲部署页（购卡数张+出牌 spawn+计时进行中；推进 480t≈48s——出牌单位
    # 已沿车道预置展开散开，避免 8 单位仍堆叠在南缘出生锚渲染成一坨）
    win.fsm.start_deploy()
    for _ in range(480):
        pilot.step()
        session.advance(1)
    win.refresh()
    if win.frame["phase"] != "deploy":
        print("✗ deploy 页相位异常：%r" % win.frame["phase"])
        win.close()
        return 1
    # A3 部署可见性回归护栏（换页重适配机制）：购卡出场后南缘锚点单位 px
    # 坐标仍在视口内——防适配逻辑回退
    l, b, r, t = win._viewport_px()
    mine = [u for u in win.frame["units"] if u["team"] == 0]
    anchor_units_in = 0
    for u in mine:
        ux, uy = win.cm_to_px(u["pos_cm"][0], u["pos_cm"][1])
        if l <= ux <= r and b <= uy <= t:
            anchor_units_in += 1
    print("%s deploy 出场单位视口内 %d/%d（锚点可见性护栏）"
          % ("✓" if mine and anchor_units_in == len(mine) else "✗",
             anchor_units_in, len(mine)))
    if not mine or anchor_units_in != len(mine):
        win.close()
        return 1
    win.snapshot(os.path.join(out_dir, "deploy.png"))
    made.append("deploy.png")

    # ③ 实战页（单位+一处框选+一条已下达命令痕迹；t≈2165=seed42 实测蓝方
    # 先头进入人类视角帧的接触窗（2030–2300）中点——红蓝单位同帧可辨）
    while session.world.tick < 2165:
        pilot.step()
        session.advance(1)
    win.refresh()
    mine = [u for u in win.frame["units"] if u["team"] == 0]
    if not mine:
        print("✗ battle 页无单位（frame units 空）")
        win.close()
        return 1
    # ── B3 剧本（2026-10-13；勘注 2026-10-15 问题5 用户拍板常驻）：空选区
    #    battle 帧截屏——命令面板**绘满配 6×8 足印提示格**（order_panel_rect
    #    常驻——原「空选区不绘命令格（basics.txt:62）」推读推翻；三态过滤行为
    #    保留=空选区无命令钮）；呼援轨保留。──
    win.fsm.clear_selection()
    win._layout_buttons()
    win.snapshot(os.path.join(out_dir, "battle_empty.png"))
    made.append("battle_empty.png")
    # ── B3 布局级判据：无曲射/无狙击选区→命令格无 fm/sniper 钮（三态过滤）──
    plain = next((u for u in mine
                  if not (u.get("caps") or {}).get("indirect")
                  and not (u.get("caps") or {}).get("sniper")), None)
    if plain is None:
        print("✗ battle 页无『无曲射/无狙击』己方单位可验过滤面")
        win.close()
        return 1
    win.fsm.select_units([plain["id"]])
    win._layout_buttons()
    b3_keys = {b.key for b in win._buttons}
    b3_ok = "fm" not in b3_keys and "sniper" not in b3_keys \
        and "stop" in b3_keys
    print("%s B3 命令格过滤：选『%s』后无炮击(T)/狙击(L)钮、有停止(S)钮"
          % ("✓" if b3_ok else "✗", plain["name"]))
    if not b3_ok:
        win.close()
        return 1
    win.fsm.clear_selection()
    anchor = mine[0]["pos_cm"]
    x0, y0 = win.cm_to_px(anchor[0] - 4000, anchor[1] - 4000)
    x1, y1 = win.cm_to_px(anchor[0] + 4000, anchor[1] + 4000)
    win.select_box_px(x0, y0, x1, y1)                    # 框选（B2 后=角框呈现，无残留白框）
    session.cmd.move(list(win.fsm.selected), (100000, 50000))   # 已下令痕迹（trail）
    if not win.fsm.selected or not session.cmd.trail:
        print("✗ battle 页三要素缺失（选区 %r / trail %d）"
              % (win.fsm.selected, len(session.cmd.trail)))
        win.close()
        return 1
    win.snapshot(os.path.join(out_dir, "battle.png"))
    made.append("battle.png")

    # ④ 结算屏（读帧 result——D031 三级裁决证据）
    while session.world.phase != 2:                      # PHASE_SETTLE
        pilot.step()
        session.advance(1)
    win.refresh()
    if win.frame.get("result") is None:
        print("✗ 结算帧缺 result 字段")
        win.close()
        return 1
    win.snapshot(os.path.join(out_dir, "result.png"))
    made.append("result.png")

    # 非空非白屏自检（每张 ≥8 色——知情确认项验收判据）
    from PIL import Image
    ok = True
    for name in made:
        img = Image.open(os.path.join(out_dir, name)).convert("RGB")
        colors = img.getcolors(maxcolors=1_000_000)
        verdict = "✓" if len(colors) >= 8 else "✗"
        ok = ok and len(colors) >= 8
        print("%s %s：size=%s colors=%d" % (verdict, name, img.size, len(colors)))
    # A3 叠加：deploy.png 锚点区域采样非 BACKGROUND 色 ≥1px（集结区标记/锚点
    # 单位至少其一在渲染面上——防「部署页单位画不到主图」回归）
    dep = Image.open(os.path.join(out_dir, "deploy.png")).convert("RGB")
    mw, mh = win.frame.get("map_cm", (200000, 100000))
    ax, ay = win.cm_to_px(mw / 2, 0)
    bg = (26, 30, 26)
    hits = 0
    for dx in range(-12, 13, 2):
        for dy in range(-12, 13, 2):
            x, y = int(ax) + dx, int(ay) + dy
            if 0 <= x < dep.width and 0 <= y < dep.height:
                if dep.getpixel((x, y)) != bg:
                    hits += 1
    verdict = "✓" if hits >= 1 else "✗"
    ok = ok and hits >= 1
    print("%s deploy 锚点区域非底色像素 %d（A3 锚点采样护栏）" % (verdict, hits))
    # ── B3 像素判据（battle_empty.png；勘注 2026-10-15 问题5 常驻拍板——判据
    #    反转）：满配足印内 ORDER_TEXT 描边像素 ≥1（命令面板底板在绘——空选区
    #    常驻足印护栏，若回退「空选区不绘」即红；编组列/小地图在足印外不扰）。
    #    采样勘正（2026-10-15 长条轮·GL 会话首次实跑）：1px 描边经 GL 光栅居中
    #    落奇数列/行（实测竖线 x=905/1269、横线像 y=513/789），旧步长 2 的偶
    #    格点采样恒空——判据本轮前从未在 GL 会话跑过（§11.3「无显示不可跑」），
    #    步长改 1（阈值 ≥1 不变，量尺修正非放宽）。──
    from sovs.ui.hud_bottom import order_panel_rect
    from sovs.ui.palette import ORDER_TEXT
    gx0, gy0, gx1, gy1 = order_panel_rect(win)
    bimg = Image.open(os.path.join(out_dir, "battle_empty.png")).convert("RGB")
    outline = ORDER_TEXT[:3]
    panel_hits = sum(1 for x in range(int(gx0), int(gx1))
                     for y in range(int(bimg.height - gy1), int(bimg.height - gy0))
                     if bimg.getpixel((x, y)) == outline)
    verdict = "✓" if panel_hits >= 1 else "✗"
    ok = ok and panel_hits >= 1
    print("%s battle 空选区命令面板足印描边像素 %d（B3 常驻足印护栏）"
          % (verdict, panel_hits))
    win.close()
    return 0 if ok else 1
