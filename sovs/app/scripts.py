"""标准玩法/脚本驾驶剧本（FE-T07 → GP-01 §5.3 自 tools/skirmish_shell.py 迁入＋扩）。

结论先行：StandardPlay＝标准玩法剧本（框选→右键移动→Q 攻击移动→烟幕→编组→
切组，经 ShellFsm 同一语义层发令——headless 可跑）；ScriptedPilot＝人类席
脚本驾驶（--smoke/--screenshot 门禁用；全部经 CmdBus 发令与玩家同通道）。

GP-01 扩量（--smoke 剧本扩展面）：
- 空中可控链（§4）：我方飞机在空→fsm 双通道选中→air_patrol＋air_strike
  两令（≥2 条）→观测任务体安装（a.task 非 None）；
- 炮击新模式（§3）：POINT→LINE→CREEP 逐模式各下一任务（同一门炮串行——
  任务体结束再下一条），观测 unit.fire_mission.form 逐型落账；
- SMOKE 弹药位与「编辑器造卡组→开局到结算」整链在 qa.py 的自制卡组段承载
  （迫击炮烟弹档须 M1 落库的 MORTAR 卡——su_min 无此卡，属编辑器产出面）。
"""
from __future__ import annotations

from sovs.sim.air import PHASE_COMBAT, PHASE_DEPLOY
from sovs.sim.geom import dist_cm
from sovs.sim.types import UnitFlag
from sovs.ui.shell_fsm import CREEP_SPEEDS_CM, ShellFsm

# 五组命令（门禁证据分组键——与 sovs/ui/shell_fsm.ORDER_GROUPS_FIRST_BATCH 对齐）
_GROUPS = ("move", "attack", "fire_mission", "air", "smoke_sprint")

# 炮击模式队列（GP-01 §3——POINT 既有，LINE/CREEP 新模式；逐模式观测落账）
_FM_MODE_QUEUE: tuple[tuple[str, dict], ...] = (
    ("POINT", {}),
    ("LINE", {"ammo_mult": 2}),
    ("CREEP", {"salvo_mode": "HALF", "creep_speed": CREEP_SPEEDS_CM[0]}),
)


class StandardPlay:
    """标准玩法剧本（交互重设计附加要求③）：模拟真实玩家路径——框选→右键移动
    →Q 攻击移动→烟幕→编组→切组——经 ShellFsm 同一语义层发令（窗口层只做 GL
    事件翻译，语义收敛 fsm——本剧本 headless 可跑，供 --smoke 与 pytest 复用），
    逐条断言状态变化（选中集合/已下命令进入队列/世界状态响应）。"""

    def __init__(self, session, fsm: ShellFsm | None = None):
        self.session = session
        self.fsm = fsm if fsm is not None else ShellFsm()
        if self.fsm.page == "config":
            self.fsm.start_deploy()      # 语义层入局（on_frame 后续驱动三页迁移）
        self.checks: list[tuple[str, bool, str]] = []
        self._g_done = False                             # G 组合仅首次（见 battle_beat ④）

    def check(self, name: str, cond, detail: str = "") -> bool:
        ok = bool(cond)
        self.checks.append((name, ok, detail))
        return ok

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c[1] for c in self.checks)

    def sync_frame(self) -> dict:
        frame = self.session.frame()
        self.fsm.on_frame(frame)
        return frame

    # ── 剧本节拍（deploy/battle 各一；断言内联）──

    def deploy_beat(self) -> None:
        """部署期标准玩法：框选→建组→取组剪尸断言。"""
        frame = self.sync_frame()
        if frame.get("phase") != "deploy":
            return
        mine = [u for u in frame["units"] if u["team"] == frame.get("view")]
        if not mine:
            return
        xs = [u["pos_cm"][0] for u in mine]
        ys = [u["pos_cm"][1] for u in mine]
        picked = self.fsm.box_select((min(xs) - 1, min(ys) - 1),
                                     (max(xs) + 1, max(ys) + 1))
        self.check("框选=帧内己方全集", set(picked) == {u["id"] for u in mine},
                   "selected=%s mine=%s" % (picked, [u["id"] for u in mine]))
        result = self.fsm.key("1", ctrl=True)
        self.check("Ctrl+1 建组=选中快照",
                   result == "group_assign"
                   and self.fsm.groups.get(1) == (tuple(picked), ()),
                   "groups[1]=%s" % (self.fsm.groups.get(1),))

    def battle_beat(self) -> None:
        """实战期标准玩法：取组→右键移动→Q 攻击移动→烟幕组合→切组。"""
        bus = self.session.cmd
        frame = self.sync_frame()
        if frame.get("phase") != "combat":
            return
        mine = [u for u in frame["units"] if u["team"] == frame.get("view")]
        if not mine:
            return
        # ① 取组（剪尸：按当前帧活单位过滤——组内死 id 不进选区）
        if self.fsm.groups.get(1):
            alive = {u["id"] for u in mine}
            recalled = self.fsm.key("1")
            picked_alive = tuple(i for i in self.fsm.groups[1][0]
                                 if i in alive)
            self.check("取组剪尸=组内活单位",
                       recalled == "group_recall"
                       and self.fsm.selected == picked_alive,
                       "selected=%s alive-in-group=%s"
                       % (self.fsm.selected, picked_alive))
            if not self.fsm.selected:
                self.fsm.select_units([u["id"] for u in mine])
        else:
            self.fsm.select_units([u["id"] for u in mine])
        sel = list(self.fsm.selected)
        # 2026-10-14 探测增量块适配（证据采集面）：已下 B（rtb_pending）的单位移出
        # 选区——真实玩家不会对已令撤回者续发推进令；反复右键拉走会使其永不停步，
        # system_rtb「停止即到场退款」无法触发。
        rtb_ids = {u.id for u in self.session.world.units if u.rtb_pending}
        if rtb_ids:
            self.fsm.selected = tuple(uid for uid in self.fsm.selected
                                      if uid not in rtb_ids)
            sel = list(self.fsm.selected)
        if not sel:
            return
        # ② 右键移动（窗口语义=直接 cmd.move）——断言入队
        n_queue0 = len(self.world_queue())
        dest = (100000, 45000)
        cmds = bus.move(sel, dest)
        self.check("右键移动=命令入队",
                   bool(cmds) and len(self.world_queue()) > n_queue0,
                   "cmds=%d" % len(cmds))
        # ③ Q 攻击移动（两段式：Q 待令→点地确认——MoveMode.ATTACK；P0 键位
        # 纠偏块 2026-10-13 A→Q——手册 HOTKEYS「Q Attack Move」manual.txt:560）
        armed = self.fsm.key("Q")
        attack_moves = self.fsm.execute_armed_ground((100000, 55000), bus)
        trail_moves = [t for t in bus.trail if t["kind"] == "move"]
        self.check("Q+点地=攻击移动（mode=ATTACK）",
                   armed == "arm:attack" and attack_moves
                   and trail_moves and trail_moves[-1].get("mode") == "ATTACK",
                   "armed=%s trail_tail=%s" % (armed, trail_moves[-1] if trail_moves
                                               else None))
        # ④ G 烟幕冲刺禁火组合（仅首次、仅单个烟幕载体——组合含禁火姿态，
        # 对全军反复下会压住射击使 attack 观测失去载体；真实玩家路径=G 用于
        # 单车突击/脱离而非全军；断言口径=trail 落账）
        if not self._g_done:
            smoker = next((u for u in mine if u.get("smoke_left", 0) > 0),
                          None)
            if smoker is not None:
                full_sel = list(self.fsm.selected)
                self.fsm.select_units([smoker["id"]])
                n0 = len([t for t in bus.trail if t["kind"] == "smoke_sprint"])
                self.fsm.key("G", cmd=bus)
                n1 = len([t for t in bus.trail if t["kind"] == "smoke_sprint"])
                self.check("G 组合令落账（单烟幕载体）", n1 > n0,
                           "trail smoke_sprint %d→%d" % (n0, n1))
                self.fsm.select_units(full_sel)      # 恢复大队选区
                self._g_done = True

    def world_queue(self) -> list:
        return self.session.world.command_queue


class ScriptedPilot:
    """人类席脚本驾驶（--smoke/--screenshot 门禁用；交互模式不挂）。

    全部经 CmdBus 发令（与玩家点击同一通道——门禁证据即通道证据）；节拍：
    盲部署每 10t 购一张卡+预置车道展开，实战每 100t 机动/攻击/炮击/空呼/烟幕
    冲刺各按条件触发。五组「生效」观测（A12 收紧口径）：
    - move：probe=pilot 发令对象本体（位移=pos 改变）；
    - attack：指定 shooter 的武器 target.unit.id==指定 foe id
      （WeaponState.target 是 ElementInstance——element.id 是单位内元素序号，
      不可当单位 id 比，须经 .unit 反引）；
    - fire_mission：我方任务体安装（unit.fire_mission 非 None）；
    - air：我方飞机在空（pilot 呼出）；
    - smoke_sprint：发起单位 self_smoke_left 减少，或存在中心距该单位
      pos ≤ 烟幕半径的己方发起烟区。

    GP-01 扩面证据（--smoke 剧本扩展段消费）：
    - air_ctrl：{selected, commands, observed}——选中飞机→≥2 空令→任务体安装；
    - fm_modes：{form: seen}——LINE/CREEP 任务体逐型安装观测。
    另嵌 StandardPlay 标准玩法剧本（框选→右键→Q 攻击移动→烟幕→编组→切组
    逐条断言——smoke 门禁一并核对）。
    """

    def __init__(self, session):
        self.session = session
        self.evidence = {g: {"issued": 0, "observed": False} for g in _GROUPS}
        self._move_probe: tuple[int, tuple[int, int]] | None = None
        self._fm_guns: set[int] = set()
        self._air_beat = 0
        self._attack_pairs: list[tuple[int, int]] = []   # (shooter_id, foe_id)
        self._smoke_probe: tuple[int, tuple[int, int], int] | None = None
        self.script = StandardPlay(session)          # 标准玩法剧本（附加要求③）
        # GP-01 扩面证据
        self.air_ctrl = {"selected": False, "commands": 0, "observed": False}
        self.fm_modes: dict[str, bool] = {form: False
                                          for form, _kw in _FM_MODE_QUEUE}
        # P1 机制证据（2026-10-13——地面 RTB 退款／诱饵／加力；激光→精密打击
        # 在 qa._p1_mechanics_smoke 自制卡组段承载）
        self.p1 = {"rtb_issued": False, "rtb_observed": False,
                   "decoy_issued": False, "decoy_observed": False,
                   "ab_issued": False, "ab_observed": False,
                   "rtb_carriers": []}

    def _p1_beat(self, bus) -> None:
        """P1 机制发令节拍（--smoke 判据面；一次性）：
        - 地面 RTB：最多 3 名并行载体下 B（到场退款——观测=refund_log 落账）；
        - 诱饵/加力：对在空战斗机各下一次（观测=decoy_left 减/afterburner 置位）。"""
        w = self.session.world
        mine = self._mine()
        # 地面 RTB 退款证据采集：最多 3 名并行载体（离出生锚最近优先），在册载体
        # 殁于半途即补位重发——证据采集重试面，非判据放宽〔终审修复块 2026-10-13
        # 先例：暴击恢复后软目标卡车在途损毁成为正常战果；2026-10-14 探测增量块
        # 后交战轨迹再变，单车顺发屡屡全灭，改并行+补位〕。
        if not self.p1["rtb_observed"]:
            from sovs.sim.tick import _deploy_anchor
            anchor = _deploy_anchor(w, 0)
            alive_ids = {u.id for u in mine}
            self.p1["rtb_carriers"] = [cid for cid in self.p1["rtb_carriers"]
                                       if cid in alive_ids]
            if len(self.p1["rtb_carriers"]) < 3:
                skip = set(self.p1["rtb_carriers"])
                cands = [u for u in mine if u.alive and not u.rtb_pending
                         and u.id not in skip
                         and not (u.elements
                                  and all(e.mounted_in is not None
                                          for e in u.elements))]
                if cands:
                    carrier = min(cands, key=lambda u: dist_cm(u.pos, anchor))
                    if bus.ground_rtb([carrier.id]):
                        self.p1["rtb_carriers"].append(carrier.id)
            if self.p1["rtb_carriers"]:
                self.p1["rtb_issued"] = True
        fighter = next((a for a in w.aircraft if a.team == 0
                        and (a.template.can_afterburner
                             or a.template.decoy_charges > 0)
                        and a.state not in (3, 4)), None)   # 非 RTB/DOGFIGHT
        if fighter is not None:
            if not self.p1["decoy_issued"] and fighter.decoy_left > 0:
                if bus.air_decoy([fighter.id], "POP"):
                    self.p1["decoy_issued"] = True
            if not self.p1["ab_issued"] and fighter.template.can_afterburner \
                    and not fighter.afterburner:
                if bus.air_afterburner([fighter.id], True):
                    self.p1["ab_issued"] = True

    def _p1_observe(self) -> None:
        """P1 机制生效观测（--smoke 判据）。"""
        w = self.session.world
        if self.p1["rtb_issued"] and not self.p1["rtb_observed"]:
            if any(r.get("team") == 0 for r in w.refund_log):
                self.p1["rtb_observed"] = True
        for a in w.aircraft:
            if a.team != 0:
                continue
            if a.decoy_left < a.template.decoy_charges:
                self.p1["decoy_observed"] = True
            if a.afterburner:
                self.p1["ab_observed"] = True

    # ── 意图发令（经 CmdBus）──

    def _issue(self, group: str, cmds) -> None:
        if cmds:
            self.evidence[group]["issued"] += len(cmds)

    def step(self) -> None:
        w = self.session.world
        if w.phase == PHASE_DEPLOY:
            if w.tick % 10 == 0:
                self._deploy_beat()
        elif w.phase == PHASE_COMBAT:
            if w.tick % 10 == 0:
                self._observe()
            if w.tick % 100 == 0:
                self._combat_beat()

    def _mine(self):
        w = self.session.world
        return [u for u in w.units if u.alive and u.team == 0]

    def _foes_spotted(self):
        w = self.session.world
        return [u for u in w.units
                if u.alive and u.team == 1 and (u.spotted_mask & 1)]

    def _deploy_beat(self) -> None:
        w, bus, p = self.session.world, self.session.cmd, \
            self.session.world.players[0]
        # 购卡：首个可购槽（非空降限定、余份>0、点数够——引擎门裁决；购卡走
        # 同一 queue_command 通道，但不属首批五组、不计入五组证据）
        for slot in p.deck_slots:
            if (slot.copies_left > 0 and p.points >= slot.template.cost
                    and not (slot.template.flags & UnitFlag.DELIVERY_AIRDROP_ONLY)):
                bus.purchase(slot.template.template_id)
                break
        # 预置展开车道（西/中/东轮转——actions.py _deploy_lanes 同式）
        lanes = [(60000, 20000), (100000, 20000), (140000, 20000)]
        idle = [u for u in self._mine() if not u.moving()]
        for i, u in enumerate(idle):
            self._issue("move", bus.move([u.id], lanes[i % 3]))
            if self._move_probe is None:
                self._move_probe = (u.id, u.pos)
        # 标准玩法：部署期框选+建组（预编组）
        self.script.deploy_beat()

    def _combat_beat(self) -> None:
        w, bus = self.session.world, self.session.cmd
        mine = self._mine()
        if not mine:
            return
        # 标准玩法：取组剪尸→右键移动→Q 攻击移动→G 组合（逐条断言入 script）
        self.script.battle_beat()
        sel = list(self.script.fsm.selected) or [u.id for u in mine]
        # 移动族：未机动单位向中央占点推进（rtb_pending 已令撤回者除外——
        # 2026-10-14 探测增量块适配，同 StandardPlay 选区过滤口径）
        idle = [u for u in mine if not u.moving() and not u.rtb_pending]
        if idle:
            self._issue("move", bus.move([u.id for u in idle],
                                         (100000, 50000)))
            if self._move_probe is None:
                self._move_probe = (idle[0].id, idle[0].pos)
        # 攻击：射程内最近 (shooter, foe) 对（观测锚=A12 指定对——引擎门 ⑨ 超
        # max_range 即 REJECT 不落瞄准，故只对射程内目标下令；距离=欧氏精确式，
        # 原曼哈顿保守上界弃用）。发现门=引擎门④同款全队 spotted_mask（fire
        # control 组网口径）——2026-10-14 探测增量块后团级视野收窄，不另加射手
        # 私视门（加门=超引擎语义过度收紧证据面）。
        foes = self._foes_spotted()
        if foes:
            best = None
            for u in mine:
                rng = max((ws.template.max_range_cm
                           for e in u.elements for ws in e.weapon_states),
                          default=0)
                if rng <= 0:
                    continue
                for f in foes:
                    d = dist_cm(u.pos, f.pos)
                    if d <= rng and (best is None or d < best[2]):
                        best = (u, f, d)
            if best is not None:
                shooter, target, _d = best
                cmds = bus.attack(shooter.id, target.id)
                if cmds:
                    self._attack_pairs.append((shooter.id, target.id))
                self._issue("attack", cmds)
        # 持令重发（2026-10-14 探测增量块适配，证据采集面）：引擎门⑩射界外每令
        # 仅转车体一步——单发令常止于旋转而永不落瞄准。首个配对（双方存活＋敌
        # 保持全队发现）持续重发，直至武器锁定被观测或目标消亡。
        if self._attack_pairs and not self.evidence["attack"]["observed"]:
            sid, fid = self._attack_pairs[0]
            s = next((u for u in mine if u.id == sid), None)
            f = next((u for u in w.units if u.id == fid and u.alive), None)
            if s is not None and f is not None and (f.spotted_mask & 1):
                self._issue("attack", bus.attack(sid, fid))
        # 炮击任务（GP-01 §3 模式队列）：首个 INDIRECT 单位逐模式各下一次任务
        # （POINT→LINE→CREEP——当前模式任务体**已被观测**即撤令换下一模式：
        # ZiS-3 六发任务自然打完耗时整段实战，等 fire_mission=None 会让
        # LINE/CREEP 无观测窗；撤令换模式=玩家「打完就转移」的常规操作）
        gun = next((u for u in mine
                    if u.template.mode_set & (1 << 1)), None)
        if gun is not None:
            pending = [(f, kw) for f, kw in _FM_MODE_QUEUE
                       if not self.fm_modes.get(f)]
            fm = gun.fire_mission
            if pending and fm is None:
                form, kwargs = pending[0]
                target = ((100000, 80000) if form == "POINT"
                          else ((100000, 78000), (115000, 88000)))
                cmds = bus.fire_mission(gun.id, target, form=form, **kwargs)
                if cmds:
                    self._issue("fire_mission", cmds)
            elif pending and fm is not None:
                done = getattr(fm.form, "name", str(fm.form))
                if self.fm_modes.get(done):        # 已观测→撤令腾位给下一模式
                    bus.cancel_fire_mission([gun.id])
        # 空军呼叫：首拍攻击机（BOMB）；其后有预备队伞兵时运输机装载
        roster = {e["key"]: e for e in self.session.air_roster()}
        self._air_beat += 1
        bomber = next((e for k, e in roster.items()
                       if k.startswith("call_") and "BOMB" in e["payload"]
                       and e["payload"]["BOMB"] > 0), None)
        troop = next((e for k, e in roster.items()
                      if e["payload"].get("PARATROOP")), None)
        fighter = next((e for k, e in roster.items()
                        if getattr(e["template"], "can_afterburner", False)
                        or getattr(e["template"], "decoy_charges", 0) > 0), None)
        if self._air_beat == 1 and bomber is not None:
            self._issue("air", bus.air_call(bomber["template"], bomber["payload"]))
        elif self._air_beat == 4 and troop is not None:
            self._issue("air", bus.air_call(troop["template"], troop["payload"]))
        elif self._air_beat == 7 and fighter is not None:
            # P1 证据段：呼一架带加力/诱饵的战斗机（YAK9——数据侧 P1 配属）
            self._issue("air", bus.air_call(fighter["template"], {}))
        # 空中可控链（GP-01 §4 --smoke 扩展）：我方飞机在空→双通道选中→两令
        self._air_ctrl_beat(bus)
        # P1 机制证据（--smoke 判据：地面 RTB 退款一笔／诱饵+加力各一次——
        # 激光→精密打击需狙击卡，su_min 无此卡，由 qa._p1_mechanics_smoke
        # 自制卡组段承载）
        self._p1_beat(bus)
        # 烟幕冲刺姿态：首个带自卫烟幕元素的单位三令一键（观测锚=该单位——A12）
        smoker = next((u for u in mine
                       if any(e.self_smoke_left > 0 for e in u.elements)), None)
        if smoker is not None and self.evidence["smoke_sprint"]["issued"] == 0:
            self._smoke_probe = (smoker.id, smoker.pos,
                                 sum(e.self_smoke_left for e in smoker.elements))
            self._issue("smoke_sprint",
                        bus.smoke_sprint_stance([smoker.id]))

    def _air_ctrl_beat(self, bus) -> None:
        """空中可控链：呼入→选中飞机→air_patrol＋air_strike 两令（§4 --smoke 判据）。"""
        if self.air_ctrl["observed"]:
            return
        mine_air = [a for a in self.session.world.aircraft if a.team == 0]
        if not mine_air:
            return
        a = mine_air[0]
        if not self.air_ctrl["selected"]:
            self.script.fsm.select_aircraft([a.id])       # 双通道选中（GP-01 §4）
            self.air_ctrl["selected"] = True
        if self.air_ctrl["commands"] >= 2:
            return
        if a.ammo_left.get("BOMB", 0) > 0:
            if bus.air_patrol([a.id], (95000, 40000)):
                self.air_ctrl["commands"] += 1
            if bus.air_strike(a.id, (96000, 45000)):
                self.air_ctrl["commands"] += 1
        else:
            if bus.air_patrol([a.id], (95000, 40000)):
                self.air_ctrl["commands"] += 1

    # ── 生效观测（「World 状态可断言变化」判据——A12 收紧口径）──

    def _observe(self) -> None:
        w = self.session.world
        self._p1_observe()                     # P1 机制证据观测（2026-10-13）
        mine = self._mine()
        by_id = {u.id: u for u in mine}
        if self._move_probe is not None:
            uid, pos0 = self._move_probe                # probe=发令对象本体
            u = by_id.get(uid)
            if u is not None and u.pos != pos0:
                self.evidence["move"]["observed"] = True      # 位移
        # attack：指定 shooter 的武器 target.unit.id==指定 foe id
        for shooter_id, foe_id in self._attack_pairs:
            shooter = by_id.get(shooter_id)
            if shooter is None:
                continue
            for e in shooter.elements:
                for ws in e.weapon_states:
                    t = ws.target
                    if t is not None and getattr(t, "unit", None) is not None \
                            and t.unit.id == foe_id:
                        self.evidence["attack"]["observed"] = True
        for u in mine:
            fm = u.fire_mission
            if fm is not None:
                self.evidence["fire_mission"]["observed"] = True  # 任务体安装
                form = getattr(fm.form, "name", str(fm.form))     # GP-01 §3 逐型
                if form in self.fm_modes:
                    self.fm_modes[form] = True
        if any(a.team == 0 for a in w.aircraft):
            self.evidence["air"]["observed"] = True           # 我方飞机在空
        # 空中可控链观测：选中机任务体安装（patrol/strike 任一——§4 生效面）
        if (self.air_ctrl["commands"] >= 2
                and any(a.team == 0 and a.task is not None
                        for a in w.aircraft)):
            self.air_ctrl["observed"] = True
        if self._smoke_probe is not None:                 # 发起单位烟幕观测
            uid, pos0, charges0 = self._smoke_probe
            u = by_id.get(uid)
            if u is not None:
                left = sum(e.self_smoke_left for e in u.elements)
                near = any(abs(z.center[0] - u.pos[0]) ** 2
                           + abs(z.center[1] - u.pos[1]) ** 2
                           <= z.radius_cm ** 2 for z in w.smoke_zones)
                if left < charges0 or near:
                    self.evidence["smoke_sprint"]["observed"] = True
