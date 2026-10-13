"""门禁剧本（FE-T07 → GP-01 §5.3 自 tools/skirmish_shell.py 迁入＋§6/§7 扩）。

- smoke：默认配置自动跑一局到结算，五组命令证据＋GP-01 三段扩展证据：
  ① 空中可控链（呼入→选中→≥2 空令→任务体安装）；② 炮击新模式 LINE/CREEP
  任务体逐型落账；③ 编辑器造卡组→保存→SMOKE 弹药位烟弹任务→用自制卡组
  开一局到自然结算（GP-01 §7 验收锚「编辑器产出新卡组打一局完整 smoke」）。
- coldstart：隐藏窗经真实事件层走完四页逐项断言（交互重设计 A11——原文迁入）。
- interactive：交互可玩入口（缺省）。
"""
from __future__ import annotations

import time

from sovs.app.scripts import ScriptedPilot
from sovs.app.session import SkirmishSession
from sovs.sim.air import PHASE_COMBAT, PHASE_DEPLOY, PHASE_SETTLE

# 冷启动购卡序列（A11 写死）：su_min 非空降全池 8 份（合计 455 点/初始 1000），
# 必含 ZiS-3（非空降池唯一 INDIRECT）与 T-34/85（self_smoke_charges 2 烟幕载体）
# ——漏购任一张即后续判据红，属有意设计。每份配点击展开目标（车道三向）。
_COLDSTART_BUYS: tuple[tuple[int, tuple[int, int]], ...] = (
    (101, (60000, 20000)),    # SU_RECON
    (102, (90000, 25000)),    # SU_RIFLE
    (102, (110000, 25000)),   # SU_RIFLE（第 2 份）
    (104, (100000, 30000)),   # SU_COMMISSAR
    (105, (80000, 35000)),    # SU_T3485
    (105, (120000, 35000)),   # SU_T3485（第 2 份）
    (106, (100000, 15000)),   # SU_ZIS3
    (107, (100000, 8000)),    # SU_TRUCK
)


def _lib_template_id(card_key: str) -> int:
    """card_key → template_id（lib 查表——UnitTemplate 无 card_key 位）。"""
    from sovs.app.session import LIB_PATH
    from sovs.sim import card_loader
    return card_loader.load_library(LIB_PATH)[card_key].unit_template.template_id


# ── 门禁①：--smoke ──

def smoke(seed: int = 42, deck: str = "su_min", kev: str = "rule",
          beat: int = 10) -> int:
    session = SkirmishSession(seed=seed, human_deck=deck, kev_level=kev,
                              kev_beat=beat)
    pilot = ScriptedPilot(session)
    t0 = time.monotonic()
    limit = session.total_ticks + 600                      # 结算裕量
    while session.world.phase != PHASE_SETTLE and session.world.tick < limit:
        pilot.step()
        session.advance(1)
    wall = time.monotonic() - t0
    w = session.world
    if w.result is None:
        print("✗ 未到自然结算（phase=%s tick=%d）——smoke 红" % (w.phase, w.tick))
        return 1
    r = w.result
    print("对局结束 tick=%d 用时=%.1fs" % (w.tick, wall))
    print("  结算：胜方 team%d 占点=%s 剩余分值=%s 剩余血量=%s"
          % (r.winner, list(r.obj_counts), list(r.unit_scores),
             list(r.hp_totals)))
    ok = True
    for group in ("move", "attack", "fire_mission", "air", "smoke_sprint"):
        ev = pilot.evidence[group]
        verdict = "✓" if (ev["issued"] > 0 and ev["observed"]) else "✗"
        ok = ok and ev["issued"] > 0 and ev["observed"]
        print("  %s %s：入队生效 %d 笔，World 可断言变化=%s"
              % (verdict, group, ev["issued"], "是" if ev["observed"] else "否"))
    # 标准玩法剧本断言（附加要求③：框选→右键移动→Q 攻击移动→烟幕→编组→切组）
    for name, passed, detail in pilot.script.checks:
        if not passed:
            print("  ✗ 标准玩法：%s（%s）" % (name, detail))
    script_ok = pilot.script.ok
    if not script_ok:
        print("  ✗ 标准玩法剧本存在未通过断言（共 %d 条）"
              % len(pilot.script.checks))
    else:
        print("  ✓ 标准玩法剧本 %d 条断言全过（框选/建组/取组剪尸/右键移动/"
              "Q 攻击移动/G 组合）" % len(pilot.script.checks))
    # ── GP-01 §4 空中可控链（--smoke 剧本扩展①）──
    air_ctrl_ok = (pilot.air_ctrl["selected"]
                   and pilot.air_ctrl["commands"] >= 2
                   and pilot.air_ctrl["observed"])
    print("  %s 空中可控链：选中=%s 空令=%d 笔 任务体安装=%s"
          % ("✓" if air_ctrl_ok else "✗", pilot.air_ctrl["selected"],
             pilot.air_ctrl["commands"],
             "是" if pilot.air_ctrl["observed"] else "否"))
    # ── GP-01 §3 炮击新模式（--smoke 剧本扩展②）──
    fm_new_ok = pilot.fm_modes.get("LINE", False) \
        and pilot.fm_modes.get("CREEP", False)
    print("  %s 炮击新模式任务体：LINE=%s CREEP=%s（POINT=%s）"
          % ("✓" if fm_new_ok else "✗", pilot.fm_modes.get("LINE"),
             pilot.fm_modes.get("CREEP"), pilot.fm_modes.get("POINT")))
    # ── GP-01 §7 编辑器→自制卡组→一局到结算（--smoke 剧本扩展③）──
    deck_ok, deck_detail = _custom_deck_smoke(seed, kev)
    print("  %s 编辑器造卡组开一局：%s" % ("✓" if deck_ok else "✗", deck_detail))
    # ── P1 机制块（2026-10-13——地面 RTB 退款／激光→精密打击／诱饵+加力）──
    p1_pilot_ok = (pilot.p1["rtb_issued"] and pilot.p1["rtb_observed"]
                   and pilot.p1["decoy_issued"] and pilot.p1["decoy_observed"]
                   and pilot.p1["ab_issued"] and pilot.p1["ab_observed"])
    print("  %s P1 剧本证据：RTB退款=%s/%s 诱饵=%s/%s 加力=%s/%s（发令/观测）"
          % ("✓" if p1_pilot_ok else "✗",
             pilot.p1["rtb_issued"], pilot.p1["rtb_observed"],
             pilot.p1["decoy_issued"], pilot.p1["decoy_observed"],
             pilot.p1["ab_issued"], pilot.p1["ab_observed"]))
    p1_laser_ok, p1_laser_detail = _p1_mechanics_smoke(seed, kev)
    print("  %s P1 激光→精密打击：%s" % ("✓" if p1_laser_ok else "✗",
                                        p1_laser_detail))
    ok = ok and script_ok and air_ctrl_ok and fm_new_ok and deck_ok \
        and p1_pilot_ok and p1_laser_ok
    if ok:
        print("OK  smoke 五组命令全部经 queue_command 入队、被 consume_commands "
              "消费且 World 状态可断言变化；标准玩法剧本全绿；空中可控链/"
              "炮击新模式/编辑器自制卡组三段扩展证据全绿；P1 机制证据（地面 "
              "RTB 退款/激光→精密打击/诱饵/加力）全绿")
    return 0 if ok else 1


def _custom_deck_smoke(seed: int, kev: str) -> tuple[bool, str]:
    """编辑器造卡组→保存→SMOKE 烟弹任务→自制卡组开一局到自然结算。

    断言链：①保存产物 YAML+JSON 落盘且 card_loader 读回；②自制卡组开局
    （mortar 烟弹卡在册）；③SMOKE 弹药位任务安装且烟区落 SmokeZone；
    ④跑到自然结算有 result。产物 finally 删除（门禁不自留文件）。
    """
    from sovs.sim.types import UnitFlag
    from sovs.app.deck_editor import DeckEditor

    key = "smoke_gp01"
    ed = DeckEditor()
    try:
        entries = [("SU_RECON", 1), ("SU_RIFLE", 2), ("SU_MORTAR82", 1),
                   ("SU_ZIS3", 1), ("SU_T3485", 1)]
        ed.save(key, "SOVIET", entries)
        if not (ed.yaml_path(key).is_file() and ed.json_path(key).is_file()):
            return False, "保存产物缺 YAML/JSON"
        from sovs.sim import card_loader
        deck = card_loader.load_deck(ed.json_path(key))
        if dict(deck.cards).get("SU_MORTAR82") != 1:
            return False, "运行期读回缺 SU_MORTAR82"
        session = SkirmishSession(seed=seed, human_deck=key, kev_level=kev)
        w = session.world
        mortar_tid = _lib_template_id("SU_MORTAR82")
        if not any(s.template.template_id == mortar_tid
                   for s in w.players[0].deck_slots):
            return False, "自制卡组未挂载烟弹卡"
        # 盲部署购卡（迫击炮优先——引擎门裁决点数/余量）
        while w.phase == PHASE_DEPLOY:
            p = w.players[0]
            order = [mortar_tid, 102, 101]
            bought = False
            for tid in order:
                slot = next((s for s in p.deck_slots
                             if s.template.template_id == tid
                             and s.copies_left > 0
                             and p.points >= s.template.cost
                             and not (s.template.flags
                                      & UnitFlag.DELIVERY_AIRDROP_ONLY)), None)
                if slot is not None:
                    session.cmd.purchase(tid)
                    bought = True
                    break
            session.advance(1)
            if not bought and w.tick > 60:
                session.advance(1)
        if w.phase != PHASE_COMBAT:
            return False, "未入实战（phase=%s）" % w.phase
        mortar = next((u for u in w.units if u.team == 0
                       and u.template.template_id == mortar_tid
                       and u.alive), None)
        if mortar is None:
            return False, "迫击炮未出场"
        session.cmd.deploy_gun([mortar.id])           # needs_deployed 射击门
        session.advance(400)                          # 展开窗（150t）+余量
        # 目标取迫击炮位正北 20km（82mm 烟弹射程 32km 内——超程会触发 §2.11
        # 自动前移让 mortar 走路，观测窗内打不出来；射程内=原地展开即射）
        target = (mortar.pos[0], min(99000, mortar.pos[1] + 20000))
        # 烟区落账判据=**新烟区对象**（基线在下令**前**拍—— mortar 首两发烟弹
        # 可能在下令后第 1 拍即落区；KEV 自卫烟幕也可能与基线计数抵消——按
        # 对象身份而非计数差，锚定「本任务确实落下新烟区」）
        seen_zones = {id(z) for z in w.smoke_zones}
        if not session.cmd.fire_mission(mortar.id, target, ammo="SMOKE"):
            return False, "SMOKE 弹药位任务构造被拒（烟档门）"
        session.advance(1)
        if not (mortar.alive and mortar.fire_mission is not None
                and mortar.fire_mission.ammo == "SMOKE"):
            return False, "SMOKE 任务体未安装"
        smoke_landed = False
        guard = 0
        while guard < 1500 and w.phase != PHASE_SETTLE:
            session.advance(10)
            guard += 10
            if any(id(z) not in seen_zones for z in w.smoke_zones):
                smoke_landed = True
                break
        if not smoke_landed:
            return False, "烟弹未落 SmokeZone（%d 拍窗内）" % guard
        while w.phase != PHASE_SETTLE:
            session.advance(100)
        if w.result is None:
            return False, "自制卡组未到自然结算"
        return True, ("SMOKE 烟弹任务安装+烟区落账+自然结算 tick=%d"
                      % w.tick)
    except Exception as exc:                          # noqa: BLE001（门禁转红不崩栈）
        return False, "异常 %r" % (exc,)
    finally:
        try:
            ed.delete(key)
        except (FileNotFoundError, ValueError):
            pass


def _p1_mechanics_smoke(seed: int, kev: str) -> tuple[bool, str]:
    """P1 机制证据段（2026-10-13）：激光照射 N→精密打击 P 一笔（自制卡组——
    su_min 无狙击卡，SU_SNIPER 为照射器载体）＋战中购卡通道实证。

    断言链：①自制卡组（SU_SNIPER/SU_RIFLE/SU_ZIS3）开局；②部署购卡后入实战，
    战中再购一张（basics:165-168 战斗全程随时可呼——cmd_purchase 实战放行）；
    ③狙击组对已发现敌下激光照射（laser_by_unit 落账）；④ZiS-3 对激光位近点下
    PRECISION 炮击任务（任务体 ammo==PRECISION 安装+至少一发弹丸落激光位近旁）；
    ⑤地面 RTB 退款（cmd 侧直验在 pilot 段/单测，此处不重复）。产物 finally 删除。
    """
    from sovs.app.deck_editor import DeckEditor

    key = "p1_gp01"
    ed = DeckEditor()
    try:
        entries = [("SU_SNIPER", 1), ("SU_RIFLE", 2), ("SU_ZIS3", 1)]
        ed.save(key, "SOVIET", entries)
        session = SkirmishSession(seed=seed, human_deck=key, kev_level=kev)
        w = session.world
        from sovs.sim import card_loader
        from sovs.app.session import LIB_PATH
        lib = card_loader.load_library(LIB_PATH)
        sniper_tid = lib["SU_SNIPER"].unit_template.template_id
        zis_tid = lib["SU_ZIS3"].unit_template.template_id
        rifle_tid = lib["SU_RIFLE"].unit_template.template_id
        # 部署期购狙击+ZiS-3+步枪各 1 份（各只买首份——步枪留 1 份给战中购卡
        # 断言：basics:165-168「战斗全程随时可呼」）
        bought: set[int] = set()
        while w.phase == PHASE_DEPLOY:
            p = w.players[0]
            for tid in (sniper_tid, zis_tid, rifle_tid):
                if tid in bought:
                    continue
                slot = next((s for s in p.deck_slots
                             if s.template.template_id == tid
                             and s.copies_left > 0
                             and p.points >= s.template.cost), None)
                if slot is not None:
                    if session.cmd.purchase(tid):
                        bought.add(tid)
                    break
            session.advance(1)
        if w.phase != PHASE_COMBAT:
            return False, "未入实战（phase=%s）" % w.phase
        sniper = next((u for u in w.units if u.team == 0 and u.alive
                       and u.template.template_id == sniper_tid), None)
        gun = next((u for u in w.units if u.team == 0 and u.alive
                    and u.template.template_id == zis_tid), None)
        if sniper is None or gun is None:
            return False, "狙击组/ZiS-3 未出场（sniper=%s gun=%s）" % (
                sniper is not None, gun is not None)
        # ①战中购卡通道（P1：实战期 PurchaseCmd 放行——剩 1 份步枪；经命令流
        # 入队→下一拍落地后核对扣点扣份）
        p = w.players[0]
        slot = next((s for s in p.deck_slots
                     if s.template.template_id == rifle_tid
                     and s.copies_left > 0), None)
        if slot is None or not session.cmd.purchase(rifle_tid,
                                                    (60000, 20000)):
            return False, "战中购卡构造被拒（无余份）"
        pts0, copies0 = p.points, slot.copies_left
        session.advance(1)
        if not (p.points == pts0 - slot.template.cost
                and slot.copies_left == copies0 - 1):
            return False, ("战中购卡被拒（P1 相位门未放行？points %d→%d copies "
                           "%d→%d）" % (pts0, p.points, copies0,
                                       slot.copies_left))
        # ②激光照射：开战首拍敌尚在北缘（80km+）——狙击组先安全行军一次到
        # (100000, 12000) 前哨站定（站立隐蔽 10 档=敌目视 17500 内不可见），
        # 候敌南压进入光学 45000 圈即**停稳照射**（观察者移动=LOS 减半——
        # sensing 既有 move_vision 乘区）；断 LOS 则横向换位重试（穿林带侧移）
        session.cmd.move([sniper.id], (100000, 12000))
        session.cmd.move([gun.id], (86000, 9000))    # 火炮同步疏散（② 等待窗
                                                      # 内走完——③ 到位即展开）
        sniper_id = sniper.id
        designated = False
        guard = 0
        lateral = (0, 15000, -15000, 30000, -30000)   # 断 LOS 换位候选
        li = 0
        while guard < 6000 and w.phase != PHASE_SETTLE and not designated:
            foe = next((u for u in w.units if u.team == 1 and u.alive), None)
            sniper = next((u for u in w.units
                           if u.id == sniper_id and u.alive), None)
            if sniper is None:
                return False, "照射窗内射手消亡"
            if foe is None:
                return False, "照射窗内无敌方单位"
            d = abs(foe.pos[0] - sniper.pos[0]) + abs(foe.pos[1] - sniper.pos[1])
            if not sniper.moving():
                if d <= 42000:
                    session.cmd.laser_designate([sniper_id], foe.id)
                    session.advance(1)
                    designated = sniper_id in w.laser_by_unit
                    if designated:
                        break                     # 即时出窗（防尾拍 advance 剪枝）
                    if li < len(lateral) - 1:
                        li += 1                   # 断 LOS——横向换位再试
                        session.cmd.move([sniper_id],
                                         (100000 + lateral[li], 12000))
                elif li > 0:                      # 换位后未入圈——回中列候敌
                    session.cmd.move([sniper_id], (100000 + lateral[li], 12000))
                session.advance(100)
                guard += 100
                continue
            session.advance(100)
            guard += 100
        if not designated:
            return False, "激光位未落账（资格/LOS 门拒——%d 拍窗内未成 LOS）" % guard
        # ③精密打击：ZiS-3 射程 100km+ 覆盖全图——短距疏散（离锚点 ~20km，
        # spy 实测蹲锚点被 KEV 炮火拆）+到位即展开；照射与下令**同拍**完成
        # （激光随目标移动，防照射→下令间隔断链），任务先安装、展开毕自然开火
        gun_id, sniper_id0 = gun.id, sniper_id
        fired = False
        guard = 0
        while guard < 6000 and w.phase != PHASE_SETTLE:
            gun = next((u for u in w.units if u.id == gun_id and u.alive), None)
            sniper = next((u for u in w.units
                           if u.id == sniper_id0 and u.alive), None)
            if gun is None or sniper is None:
                return False, "射击窗内火炮/射手消亡（gun=%s sniper=%s）" % (
                    gun is not None, sniper is not None)
            if not gun.moving() and gun.deploy_state == 0:
                session.cmd.deploy_gun([gun_id])     # 到位即展开（MOBILE=0）
            if not sniper.moving():
                foe = next((u for u in w.units if u.team == 1 and u.alive), None)
                if foe is not None:
                    d = abs(foe.pos[0] - sniper.pos[0]) \
                        + abs(foe.pos[1] - sniper.pos[1])
                    if d <= 42000:
                        if sniper_id0 not in w.laser_by_unit:
                            session.cmd.laser_designate([sniper_id0], foe.id)
                            session.advance(1)
                        if sniper_id0 in w.laser_by_unit:
                            laser_pos = w.laser_by_unit[sniper_id0][1].pos
                            if session.cmd.fire_mission(gun_id, laser_pos,
                                                        ammo="PRECISION"):
                                fired = True
                                break
            session.advance(50)
            guard += 50
        if not fired:
            return False, "PRECISION 任务未构造（激光位/火炮门——%d 拍窗）" % guard
        session.advance(1)
        gun = next((u for u in w.units if u.id == gun_id and u.alive), None)
        fm = gun.fire_mission if gun is not None else None
        if fm is None or fm.ammo != "PRECISION":
            return False, "PRECISION 任务体未安装"
        # ④观测至少一发精密弹丸（落点近激光位——紧散射判据曼哈顿 ≤5km；
        # 展开毕自然开火，等候窗覆盖展开+装填节奏）
        landed = False
        guard = 0
        seen = {id(pr) for pr in w.projectiles}
        while guard < 2500 and w.phase != PHASE_SETTLE:
            session.advance(10)
            guard += 10
            for pr in w.projectiles:
                if id(pr) not in seen:
                    seen.add(id(pr))
                    if pr.weapon is fm_target_ws(gun, "PRECISION"):
                        d = abs(pr.dest[0] - laser_pos[0]) \
                            + abs(pr.dest[1] - laser_pos[1])
                        if d <= 5000:
                            landed = True
        if not landed:
            return False, "精密弹未在激光位近旁落点（%d 拍窗）" % guard
        while w.phase != PHASE_SETTLE:
            session.advance(100)
        return True, "照射→PRECISION 任务安装+落点近激光位+战中购卡放行 tick=%d" % w.tick
    except Exception as exc:                          # noqa: BLE001（门禁转红不崩栈）
        return False, "异常 %r" % (exc,)
    finally:
        try:
            ed.delete(key)
        except (FileNotFoundError, ValueError):
            pass


def fm_target_ws(gun_unit, ammo):
    """炮击任务武器档（tick._fm_ws 惰性代理——qa 侧判弹丸归属；入参=单位，
    取其首个 INDIRECT 元素档）。"""
    from sovs.sim.tick import _fm_ws
    from sovs.sim.types import Mode
    el = next((g for g in gun_unit.elements if g.mode is Mode.INDIRECT),
              gun_unit.elements[0] if gun_unit.elements else None)
    return _fm_ws(el, ammo).template if el is not None and el.weapon_states else None


# ── 门禁②：--coldstart（真实事件层冷启动——交互重设计 A11）──

def coldstart(seed: int = 42, deck: str = "su_min", kev: str = "rule") -> int:
    """冷启动门禁：隐藏窗经真实事件层走完四页，逐项断言，全绿 exit 0。

    判据（A11）：① 部署期写死购卡序列（su_min 非空降全池 8 份/455 点，paced
    购法 tick600 出齐）——出场数期望=进 deploy 页时初始帧快照非空降份数
    （断言已购已出场数==Σ初始−Σ剩余，锚定口径防剩余值退化）；② 实战有效命令
    ≥10 条（trail 计数 move≥4 且 attack≥3 且 smoke_sprint≥1 且 fire_mission≥1）
    +world 状态变化（位移 probe+指定 shooter 武器 target.unit.id+烟区存在）。"""
    try:
        import arcade
    except ImportError as exc:
        print("✗ --coldstart 需要渲染栈（pip install -e \".[fe]\"）：%s" % exc)
        return 1
    from sovs.ui.shell_window import ShellWindow

    session = SkirmishSession(seed=seed, human_deck=deck, kev_level=kev)
    win = ShellWindow(session, visible=False)
    L, R = arcade.MOUSE_BUTTON_LEFT, arcade.MOUSE_BUTTON_RIGHT
    failures: list[str] = []

    def expect(name: str, cond, detail: str = "") -> bool:
        ok = bool(cond)
        if not ok:
            failures.append("%s（%s）" % (name, detail))
        print("  %s %s%s" % ("✓" if ok else "✗", name,
                             "" if ok else "——" + detail))
        return ok

    def advance_to(tick: int) -> None:
        while session.world.tick < tick and session.world.phase != PHASE_SETTLE:
            session.advance(1)
        win.refresh()

    try:
        # ── ① config → deploy：真实事件层（Enter）──
        win.on_key_press(arcade.key.ENTER, 0)
        expect("Enter 进部署页", win.fsm.page == "deploy", win.fsm.page)
        p0 = win.frame["players"][0]
        initial_copies = sum(s["copies_left"] for s in p0["deck"]
                             if not s["airdrop"])
        expect("初始非空降份数=8（锚定口径快照）", initial_copies == 8,
               str(initial_copies))

        # ── ② 部署期写死购卡序列：点卡槽→点地（真实鼠标事件）──
        buys = list(_COLDSTART_BUYS)
        pace = 60                                   # 每 60t 一份（tick600 出齐）
        for i, (tid, dest) in enumerate(buys):
            btn = next((b for b in win._buttons
                        if b.key.startswith("buy:%d|" % tid)), None)
            if btn is None:
                failures.append("购卡槽未找到 template=%d" % tid)
                continue
            win.on_mouse_press((btn.x0 + btn.x1) / 2, (btn.yb + btn.yt) / 2,
                               L, 0)
            if win.fsm.armed_purchase is None or win.fsm.armed_purchase[0] != tid:
                failures.append("装弹失败 template=%d（点数/余量门？）" % tid)
                continue
            px, py = win.cm_to_px(dest[0], dest[1])
            win.on_mouse_press(px, py, L, 0)        # 点地放卡（位置=展开目标）
            advance_to(session.world.tick + pace)
        pending_left = len(session.pending_expands)
        expect("8 份全购（pending 展开队列已消化）", pending_left == 0,
               "pending=%d" % pending_left)
        points_left = win.frame["players"][0]["points"]
        expect("购后余点=545（455 点已花）", points_left == 545,
               str(points_left))

        # ── ③ 出场数锚定断言（进 battle 前后口径）──
        from sovs.sim.tables import CONFIG
        advance_to(CONFIG.phase_ticks[0] + 2)       # 越过盲部署（600t）入实战
        expect("相位入实战", win.fsm.page == "battle", win.fsm.page)
        p_now = win.frame["players"][0]
        remaining = sum(s["copies_left"] for s in p_now["deck"]
                        if not s["airdrop"])
        spawned = sum(1 for u in session.world.units
                      if u.team == 0)
        expect("出场数==Σ初始−Σ剩余（已购且已出场）",
               spawned == initial_copies - remaining,
               "spawned=%d initial=%d remaining=%d"
               % (spawned, initial_copies, remaining))

        # ── ④ 实战：真实事件层标准玩法（框选→右键→Q 攻击移动→齐射→T/Z/X/G
        #    →编组→切组），逐 100t 节拍推进至结算（50t+观测+50t——观测窗加密，
        #    瞄准/位移等短生命周期状态不因节拍过疏而漏采）──
        counts = {"move": 0, "attack": 0, "fire_mission": 0, "smoke_sprint": 0,
                  "total": 0}
        probes: dict[int, tuple[int, int]] = {}         # 位移 probe（发令对象→下令时位）
        volley_pairs: list[tuple[int, int]] = []         # (shooter_id, foe_id)
        target_observed = False
        smoke_zone_observed = False
        smoke_elems: list = []                       # G 下令时的烟元素本体引用（终审：
        #  烟区判据锚定我方发起——cmd_smoke 不消费下令点，落区心=pop 拍（令后
        #  cfg.self_smoke_delay_ticks=20t）元素当前位；KEV 敌烟不满足本判据，
        #  对齐 A12/ScriptedPilot「距发起单位 ≤ 烟幕半径」口径）
        probe_moved = False
        g_done = False                                   # G 组合仅一次（含禁火姿态）
        counts_since_tick = session.world.tick - 1       # trail 增量计数锚（按 tick
        #  过滤——TRAIL_CAP 从头截断滑窗，按下标游标会越窗冻结导致计数停摆；
        #  -1=计入入战拍当拍命令——beat1 的 G/Z 等首拍令不被锚拍吞掉）
        beat = 0
        while session.world.phase != PHASE_SETTLE:
            beat += 1
            win.refresh()
            frame = win.frame
            mine = [u for u in frame["units"] if u["team"] == 0]
            if not mine:
                session.advance(100)
                continue
            # 框选（press→drag→release 真实事件）
            xs = [u["pos_cm"][0] for u in mine]
            ys = [u["pos_cm"][1] for u in mine]
            bx0, by0 = win.cm_to_px(min(xs) - 6000, min(ys) - 6000)
            bx1, by1 = win.cm_to_px(max(xs) + 6000, max(ys) + 6000)
            win.on_mouse_press(bx0, by0, L, 0)
            win.on_mouse_drag(bx1, by1, 0, 0, L, 0)
            win.on_mouse_release(bx1, by1, L, 0)
            if beat == 1:
                expect("事件层框选=己方全集",
                       set(win.fsm.selected) == {u["id"] for u in mine},
                       str(win.fsm.selected))
                # 编组+切组（真实键事件）
                win.on_key_press(arcade.key.KEY_1, arcade.key.MOD_CTRL)
                win.fsm.clear_selection()
                win.on_key_press(arcade.key.KEY_1, 0)
                expect("Ctrl+1 建组+1 取组恢复",
                       win.fsm.groups.get(1)
                       and set(win.fsm.selected) <= set(win.fsm.groups[1][0])
                       and win.fsm.selected,
                       "groups[1]=%s selected=%s" % (win.fsm.groups.get(1),
                                                     win.fsm.selected))
            foes = [u for u in frame["units"] if u["team"] == 1]
            # 右键移动（真实事件）→ 位移 probe（逐单位登记发令时位置）
            probe_unit = next((u for u in mine if u["id"] not in probes), None)
            if probe_unit is not None:
                probes[probe_unit["id"]] = tuple(probe_unit["pos_cm"])
                rx, ry = win.cm_to_px(100000, 45000)
                win.on_mouse_press(rx, ry, R, 0)
            # Q+点地攻击移动（真实事件——P0 键位纠偏块 2026-10-13 A→Q）
            win.on_key_press(arcade.key.Q, 0)
            ax, ay = win.cm_to_px(100000, 55000)
            win.on_mouse_press(ax, ay, L, 0)
            # Q+点敌齐射（真实事件；点距我军最近已发现敌——齐射观测对=选中
            # 全员×该敌，A11 判据「指定 shooter 武器 target.unit.id==指定 foe id」）
            if foes and counts["attack"] < 8:
                cx = sum(u["pos_cm"][0] for u in mine) / len(mine)
                cy = sum(u["pos_cm"][1] for u in mine) / len(mine)
                foe = min(foes, key=lambda f: (abs(f["pos_cm"][0] - cx)
                                               + abs(f["pos_cm"][1] - cy), f["id"]))
                win.on_key_press(arcade.key.Q, 0)
                fx, fy = win.cm_to_px(foe["pos_cm"][0], foe["pos_cm"][1])
                win.on_mouse_press(fx, fy, L, 0)
                volley_pairs.extend((u["id"], foe["id"]) for u in mine)
            # T+点地炮击（ZiS-3 在选区内即可）
            win.on_key_press(arcade.key.T, 0)
            tx, ty = win.cm_to_px(100000, 80000)
            win.on_mouse_press(tx, ty, L, 0)
            # Z 冲刺 / X 烟幕（真实键事件；G 组合含禁火姿态——真实用法=单车
            # 突击/脱离，对全军下会压住射击，故仅一次、且只对单个烟幕载体下发）
            win.on_key_press(arcade.key.Z, 0)
            win.on_key_press(arcade.key.X, 0)
            if not g_done:
                smoker = next((u for u in mine if u.get("smoke_left", 0) > 0),
                              None)
                if smoker is not None:
                    full_sel = list(win.fsm.selected)
                    win.fsm.select_units([smoker["id"]])
                    wu = next((x for x in session.world.units
                               if x.id == smoker["id"]), None)
                    if wu is not None:
                        smoke_elems.extend(
                            e for e in wu.elements if e.self_smoke_left > 0)
                    win.on_key_press(arcade.key.G, 0)
                    win.fsm.select_units(full_sel)
                    g_done = True
                    if smoke_elems:               # N32 延迟窗（20t，留 3 倍余量）
                        for _ in range(60):       # 内逐拍贴身比对：pop 拍落区心==
                            session.advance(1)    # 元素当拍位（冲刺位移随拍跟随）
                            for z in session.world.smoke_zones:
                                if any(abs(z.center[0] - e.pos[0]) <= 1000
                                       and abs(z.center[1] - e.pos[1]) <= 1000
                                       for e in smoke_elems):
                                    smoke_zone_observed = True
                                    break
                            if smoke_zone_observed:
                                break

            def observe() -> None:
                """world 侧观测（trail 增量计数/瞄准/烟区/probe 位移）。"""
                nonlocal target_observed, smoke_zone_observed, probe_moved
                nonlocal counts_since_tick
                for tr in session.cmd.trail:
                    if tr["tick"] > counts_since_tick:
                        counts["total"] += 1
                        if tr["kind"] in counts:
                            counts[tr["kind"]] += 1
                counts_since_tick = session.world.tick
                if not target_observed:
                    by_id = {u.id: u for u in session.world.units}
                    for sid, fid in volley_pairs:
                        shooter = by_id.get(sid)
                        if shooter is None:
                            continue
                        for e in shooter.elements:
                            for ws in e.weapon_states:
                                t = ws.target
                                if (t is not None
                                        and getattr(t, "unit", None) is not None
                                        and t.unit.id == fid):
                                    target_observed = True
                if smoke_elems and not smoke_zone_observed:
                    for z in session.world.smoke_zones:
                        if any(abs(z.center[0] - e.pos[0]) <= 1000
                               and abs(z.center[1] - e.pos[1]) <= 1000
                               for e in smoke_elems):
                            smoke_zone_observed = True
                if not probe_moved:
                    for uid, pos0 in probes.items():
                        u = next((x for x in session.world.units
                                  if x.id == uid), None)
                        if u is not None and u.pos != pos0:
                            probe_moved = True

            session.advance(50)
            observe()
            session.advance(50)

        # ── ⑤ 结算断言（trail 计数+world 状态变化）──
        win.refresh()
        expect("到自然结算", win.fsm.page == "settle" and win.frame.get("result"),
               win.fsm.page)
        expect("有效命令≥10（trail 总额）", counts["total"] >= 10,
               "total=%d" % counts["total"])
        expect("trail 计数 move≥4", counts["move"] >= 4,
               "move=%d" % counts["move"])
        expect("trail 计数 attack≥3（齐射逐单位落账）", counts["attack"] >= 3,
               "attack=%d" % counts["attack"])
        expect("trail 计数 smoke_sprint≥1", counts["smoke_sprint"] >= 1,
               "smoke_sprint=%d" % counts["smoke_sprint"])
        expect("trail 计数 fire_mission≥1", counts["fire_mission"] >= 1,
               "fire_mission=%d" % counts["fire_mission"])
        expect("位移 probe 位置改变（发令对象本体，战中观测）", probe_moved,
               "probes=%d" % len(probes))
        expect("指定 shooter 武器 target.unit.id==指定 foe id",
               target_observed, "pairs=%d" % len(volley_pairs))
        expect("我方发起烟区存在（N32 延迟窗内贴身锚定烟元素，敌烟不计）",
               smoke_zone_observed)
    finally:
        win.close()

    if failures:
        print("✗ coldstart %d 项红：" % len(failures))
        for f in failures:
            print("   - %s" % f)
        return 1
    print("OK  coldstart 事件层冷启动全绿（配置→盲部署→实战→结算；购卡 8 份/"
          "出场锚定/事件层框选编组/Q 攻击移动/齐射/炮击/烟幕/位移与目标观测）")
    return 0


# ── 门禁④：交互可玩（缺省入口）──

def interactive(seed: int = 42, deck: str = "su_min", kev: str = "rule",
                beat: int = 10) -> int:
    try:
        import arcade
    except ImportError as exc:
        print("✗ 交互可玩需要渲染栈（pip install -e \".[fe]\"）：%s" % exc)
        return 1
    from sovs.ui.shell_window import ShellWindow
    session = SkirmishSession(seed=seed, human_deck=deck, kev_level=kev,
                              kev_beat=beat)
    win = ShellWindow(session, visible=True)
    win.center_window()
    arcade.run()
    return 0
