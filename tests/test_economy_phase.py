"""相位状态机与命令驱动队列（GROUND_UNITS_PSEUDOCODE_IMPL_v1.7 §F8 :1413-1426
update_phase/consume_commands + §D.7 命令集 + tables phase_ticks/infiltration_ticks）
+ ⑧ 经济块（§F7 :1374-1405 cmd_purchase/spawn_step/system_objectives、§F8 :1476-1479
system_economy、D031 结算裁决挂迁入结算拍）。

锚点全部手推写死（2026-10-03 拍板后相位边界 600/13800、迁入拍同拍 system_timers 递减、
渗透 600−150=450、命令层零掷骰、经济 %10 门/出牌 FIFO/锚点+出牌序偏移 1000、
占点半径含等号、D031 四链裁决（2026-10-03 拍板：占点→分值→血量→队0，无平局）），不自证；确定性双跑照
tests/test_integration.py fingerprint 范式（同 seed 两 world 逐 tick 比指纹，
跨 600 相位边界 / 经济指纹含 points/队列/占点/裁决）。"""
import unittest

from sovs.sim.air import (PHASE_COMBAT, PHASE_DEPLOY, PHASE_SETTLE)
from sovs.sim.tick import (AttackCmd, BuySuppliesCmd, CancelFireMissionCmd,
                           DeckSlot, DeployCmd, DismountCmd, FireMissionCmd,
                           GarrisonCmd, MountCmd, MoveCmd, Objective, PackCmd,
                           PurchaseCmd, SetAirdropBeaconCmd, SetModeCmd,
                           SetSniperCoverCmd, SetStanceCmd, SmokeCmd, SprintCmd,
                           StopCmd, ToggleAmbushCmd, TowCmd, UnGarrisonCmd,
                           UntowCmd, add_unit, cmd_purchase, consume_commands,
                           ground_unit_score, make_unit, make_world,
                           queue_command, resolve_settlement, spawn_step,
                           system_economy, system_objectives, update_phase,
                           world_tick)
from sovs.sim.types import (DeployState, ElementTemplate, ElementType, Mode,
                            MovementClass, MoveMode, Stance, UnitFlag,
                            UnitTemplate, UnitType)

# ── 合成模板（测试用，不对应真实卡）──
SQUAD_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                             unit_type=UnitType.INFANTRY, hp_max=10)
VEHICLE_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                               unit_type=UnitType.MECH, hp_max=20)
CARRIER_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                               unit_type=UnitType.MECH, hp_max=15, seats=1)
INFIL_TPL = UnitTemplate(                       # 渗透卡（canInfiltrate 位）
    template_id=201, name="infiltrator", category=1, cost=20,
    element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_INFILTRATE)
LINE_TPL = UnitTemplate(                        # 普通步兵（无渗透位，对照组）
    template_id=202, name="line inf", category=1, cost=20,
    element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)
TANK_TPL = UnitTemplate(                        # 普通车辆卡（FIFO 出牌序对照）
    template_id=203, name="tank", category=2, cost=60,
    element_templates=(VEHICLE_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=3, movement_class=MovementClass.TRACK)
MIXED_TPL = UnitTemplate(                       # 混编卡（2 班 + 2 座车——R-07 开局车载）
    template_id=204, name="grenadiers", category=1, cost=40,
    element_templates=(SQUAD_ELEM, SQUAD_ELEM, CARRIER_ELEM, CARRIER_ELEM),
    optics_ground_cm=20000, stealth_base=5, speed_tier=2,
    movement_class=MovementClass.WHEEL)
MIXED_OVERFLOW_TPL = UnitTemplate(              # 混编卡（3 班 1 车——溢出班不挂）
    template_id=205, name="overflow", category=1, cost=40,
    element_templates=(SQUAD_ELEM, SQUAD_ELEM, SQUAD_ELEM, CARRIER_ELEM),
    optics_ground_cm=20000, stealth_base=5, speed_tier=2,
    movement_class=MovementClass.WHEEL)
AA_WATCH_TPL = UnitTemplate(                    # 对空探测>0 → aa_roster 登记载体
    template_id=206, name="aa watch", category=4, cost=50,
    element_templates=(VEHICLE_ELEM,), optics_ground_cm=20000, optics_air_cm=60000,
    stealth_base=3, speed_tier=1, movement_class=MovementClass.TRACK)


def fingerprint(w):
    """本块状态面指纹：tick/phase/相位起点 + 单位（pos/存活/渗透/展开）+ 命令队列长
    + 八通道 PCG32 内部 state（照 test_integration.fingerprint 范式裁剪）。"""
    parts = ["t%d:p%d:s%d:r%s" % (
        w.tick, w.phase, w.phase_start_tick,
        ",".join(str(r.state) for r in w.rng._rngs))]
    for u in w.units:
        parts.append("U%d,%s,%d,%d,%d,%d" % (
            u.id, u.pos, int(u.alive), u.infiltration_timer,
            int(u.deploy_state), u.deploy_timer))
    parts.append("Q%d" % len(w.command_queue))
    return "|".join(parts)


class TestUpdatePhase(unittest.TestCase):
    def _world_at(self, tick, seed=42):
        """DEPLOY 起步 world，预置 tick 模拟已流逝拍数（phase_start_tick=0），
        只 world_tick 一拍即命中待测边界（避免 14k 拍循环）。"""
        w = make_world(seed, phase=PHASE_DEPLOY)
        w.tick = tick
        return w

    def test_phase_durations_and_boundaries(self):
        # 2026-10-03 拍板：盲部署 600→实战 13200→结算（禁火段取消）；相位占据
        # 整数拍——第 600 拍仍盲部署、第 601 拍实战；第 13800 拍仍实战、13801 结算
        w = self._world_at(599)
        world_tick(w)
        self.assertEqual((w.tick, w.phase), (600, PHASE_DEPLOY))
        w = self._world_at(600)
        world_tick(w)
        self.assertEqual((w.tick, w.phase), (601, PHASE_COMBAT))   # 实战自 601 起
        w = self._world_at(13799)
        world_tick(w)
        self.assertEqual((w.tick, w.phase), (13800, PHASE_COMBAT))  # 实战第 13200 拍（601..13800）
        w = self._world_at(13800)
        world_tick(w)
        self.assertEqual((w.tick, w.phase), (13801, PHASE_SETTLE))  # 实战恰 13200 拍

    def test_full_run_infiltration_anchor(self):
        # 连续 700 拍零手工跳 tick：601 拍迁实战；update_phase 置 600 后同拍
        # system_timers（world_tick 行序 :1427 在 update_phase 之后）即递减 1 →
        # 迁入拍末 599；750 拍末 = 600−150 = 450；非渗透卡全程零写
        w = make_world(7, phase=PHASE_DEPLOY)
        infil = add_unit(w, make_unit(w, INFIL_TPL, 0, 0, (300000, 300000)))
        line = add_unit(w, make_unit(w, LINE_TPL, 0, 0, (310000, 310000)))
        for _ in range(600):
            world_tick(w)
            self.assertEqual(w.phase, PHASE_DEPLOY)
        self.assertEqual(infil.infiltration_timer, 0)   # 实战前渗透计时零写（方案8 门控）
        world_tick(w)                                   # 第 601 拍：迁入实战
        self.assertEqual(w.phase, PHASE_COMBAT)
        self.assertEqual(infil.infiltration_timer, 599)  # 600 置位后同拍递减 1
        self.assertEqual(line.infiltration_timer, 0)     # 对照组零写
        for _ in range(149):
            world_tick(w)
        self.assertEqual(w.tick, 750)
        self.assertEqual(infil.infiltration_timer, 450)  # 600 − 150 拍递减

    def test_dead_infiltrator_not_written_on_combat_entry(self):
        # §F8 :1418 alive_units 过滤：阵亡渗透卡迁入实战拍不写计时
        w = self._world_at(600, seed=9)
        dead = add_unit(w, make_unit(w, INFIL_TPL, 0, 0, (300000, 300000)))
        dead.alive = False
        world_tick(w)
        self.assertEqual(w.phase, PHASE_COMBAT)
        self.assertEqual(dead.infiltration_timer, 0)

    def test_injected_phase_not_clobbered_within_duration(self):
        # 登记表口径"phase 由调用方注入"：注入相位自构造 tick 起满时长（phase_start_tick
        # 记账），不被绝对 tick 推导改写——默认 phase=COMBAT 的既有测试不受扰
        w = make_world(11)
        for _ in range(300):
            world_tick(w)
        self.assertEqual(w.phase, PHASE_COMBAT)          # 300 ≤ 13200：不迁结算
        w2 = make_world(13, phase=PHASE_DEPLOY)
        for _ in range(600):
            world_tick(w2)
        self.assertEqual(w2.phase, PHASE_DEPLOY)         # 注入起点记 0：恰 600 拍盲部署
        world_tick(w2)
        self.assertEqual(w2.phase, PHASE_COMBAT)         # 第 601 拍迁实战

    def test_injected_combat_world_never_rewrites_infiltration(self):
        # 注入 phase=COMBAT 无迁入事件：infiltration_timer 只被 system_timers 自然递减
        w = make_world(3)
        u = add_unit(w, make_unit(w, INFIL_TPL, 0, 0, (0, 0)))
        u.infiltration_timer = 500
        for _ in range(20):
            world_tick(w)
        self.assertEqual(w.phase, PHASE_COMBAT)
        self.assertEqual(u.infiltration_timer, 480)

    def test_update_phase_settle_is_terminal(self):
        # 结算为终态：phase_ticks 无第四段，update_phase 不再迁出
        w = make_world(5, phase=PHASE_SETTLE)
        for _ in range(100):
            world_tick(w)
        self.assertEqual(w.phase, PHASE_SETTLE)


class TestConsumeCommands(unittest.TestCase):
    def test_all_22_command_types_drain_this_tick_zero_rng(self):
        # §F8 :1426 "本 tick 的命令全部落地"：§D.7 :256-268 全集 22 类命令一拍清空；
        # 零掷骰（八通道 PCG32 state 不动）。2026-10-04 命令层块后 MoveCmd/StopCmd/
        # SprintCmd 处理体已落地——FIFO 序下 MoveCmd 装路径→StopCmd 即刻清停（终态
        # move_path=[]/mode=NORMAL）、SprintCmd 写 sprint_until=1+100；SmokeCmd 处理体
        # 2026-10-04 PB-53 自卫烟幕路径落地——本测试元素 self_smoke_charges=0 → 发数门
        # 拒令（无冒充副作用）；2026-10-06 PB-56 批① 余三命令落地后本用例行为：
        # SetModeCmd→LINE_TPL mode_set=缺省 DIRECT-only → ① 资格门拒令（e.mode
        # 保持 DIRECT，state0 断言面内）；ToggleAmbushCmd→LINE_TPL flags=0 无
        # CAN_AMBUSH 位 → 资格门拒令（ambush 两槽不动）；SetStanceCmd→最小写点
        # 真生效：u.stance=HOLD_FIRE（state0 断言不含 stance——本用例无武器，
        # fire_permitted ② 消费面不触，消费侧锚见 test_ground_combat
        # TestCmdSetStance）；2026-10-06 PB-56 批② 上下车两命令落地后本用例行为：
        # MountCmd→carrier_unit 由 None 改传真实单位 u（原 None 载具照 cmd_mount
        # :1153 字面 carrier_unit.elements 直崩 AttributeError——随批更新；u=LINE_TPL
        # 唯一元素 SQUAD_ELEM seats=0 → ④ carriers=[] → ⑥ CONTINUE → ok==0 整体
        # REJECT，mount_requests 惰性表不建、无冒充副作用）；DismountCmd→u 无
        # mounted_in 元素=无操作；2026-10-06 PB-56 批② 拖曳展开块后本用例行为：
        # DeployCmd→LINE_TPL deploy_time_ticks=0：MOBILE→DEPLOYING/timer=0，FIFO 序
        # 随后 PackCmd 命中第二 IF（DEPLOYING→MOBILE/timer=0）——净抵消，state0
        # 断言存活（同拍 system_timers 观测 MOBILE 无写）；TowCmd→e 为 SQUAD 元素
        # 被 ② 合法被拖对象门 REJECT（非 GUN 非 MECH×TOW——零写点）；UntowCmd→
        # 无涉拖曳对=无操作；2026-10-06 PB-56 批③ 支援链两命令落地后本用例行为：
        # SetSniperCoverCmd→u=LINE_TPL 无 CAN_SNIPER_COVER 位被 ① 资格门 REJECT
        # （sniper=target=u 兼被 ④ 非自身门拦——cover_by_target 零写入）；
        # BuySuppliesCmd→e=LINE_TPL SQUAD 元素、单位无 HAS_SUPPLY 位被 ① 补给
        # 载具门 REJECT（supply_weight_g 条件槽不触）；SetAirdropBeaconCmd 处理体
        # 未落地=丢弃（§D.7 总收口后唯一剩余丢弃支，登记表口径，无冒充副作用）
        w = make_world(3)
        u = add_unit(w, make_unit(w, LINE_TPL, 0, 0, (100000, 100000)))
        e = u.elements[0]
        p = w.players[0]
        for c in (
            MoveCmd(unit=u, path=[(200000, 200000)]),
            StopCmd(unit=u),
            DeployCmd(unit=u),
            PackCmd(unit=u),
            SetModeCmd(element=e, mode=Mode.INDIRECT),
            PurchaseCmd(player=p, template=LINE_TPL),
            FireMissionCmd(unit=u, form=0, point=(300000, 300000),
                           ammo_mult=1, salvo_mode=0, creep_speed=0),
            CancelFireMissionCmd(unit=u),
            SmokeCmd(element=e, point=(300000, 300000)),
            SetStanceCmd(unit=u, stance=Stance.HOLD_FIRE),
            ToggleAmbushCmd(unit=u),
            SprintCmd(unit=u),
            GarrisonCmd(unit=u, building=None),
            UnGarrisonCmd(unit=u),
            MountCmd(squad_elements=[e], carrier_unit=u),
            DismountCmd(squad_unit=u),
            TowCmd(tower_elements=[e], towed_element=e),
            UntowCmd(element=e),
            AttackCmd(element=e, target=None),
            SetSniperCoverCmd(sniper_unit=u, target_unit=u),
            SetAirdropBeaconCmd(unit=u, pos=(300000, 300000)),
            BuySuppliesCmd(truck_element=e, rounds=10, medical=5),
        ):
            queue_command(w, c)
        self.assertEqual(len(w.command_queue), 22)
        rng0 = [r.state for r in w.rng._rngs]
        state0 = (u.pos, u.deploy_state, u.deploy_timer,
                  e.mode, p.points, len(p.spawn_queue))
        world_tick(w)
        self.assertEqual(w.command_queue, [])             # 全部落地
        self.assertEqual([r.state for r in w.rng._rngs], rng0)  # 零掷骰
        self.assertEqual((u.pos, u.deploy_state, u.deploy_timer,
                          e.mode, p.points, len(p.spawn_queue)), state0)
        self.assertEqual(u.move_path, [])                 # MoveCmd→StopCmd FIFO 抵消
        self.assertEqual(u.move_mode, MoveMode.NORMAL)
        self.assertEqual(u.sprint_until, 101)             # SprintCmd：tick1+100

    def test_queue_command_preserves_insertion_order(self):
        w = make_world(5)
        a, b = StopCmd(unit=None), StopCmd(unit=None)
        queue_command(w, a)
        queue_command(w, b)
        self.assertIs(w.command_queue[0], a)             # FIFO 插入序
        self.assertIs(w.command_queue[1], b)

    def test_unknown_command_type_raises(self):
        # 非 §D.7 类型=程序员错误：立即抛 TypeError（命令流完整性保护，不静默丢）
        w = make_world(5)
        queue_command(w, object())
        with self.assertRaises(TypeError):
            world_tick(w)

    def test_mid_run_enqueue_consumed_next_tick(self):
        # 虚拟玩家节奏：拍间入队 → 下一拍 consume_commands 清空
        # （2026-10-04 命令层块：StopCmd 处理体已落地——unit=None 占位令改真实单位，
        #   halt 对静止单位为无操作，测的仍是拍边界清空语义）
        w = make_world(13)
        u = add_unit(w, make_unit(w, LINE_TPL, 0, 0, (100000, 100000)))
        for _ in range(10):
            world_tick(w)
        queue_command(w, StopCmd(unit=u))
        self.assertEqual(len(w.command_queue), 1)
        world_tick(w)
        self.assertEqual(w.command_queue, [])

    def test_consume_commands_direct_call_drains(self):
        # 分派函数可脱离 world_tick 直调（cmd_* 处理体落地后的单测入口）。
        # 2026-10-06 PB-56 批② 拖曳展开块：DeployCmd 处理体落地——unit=None 占位令
        # 改真实单位（StopCmd 同款先例）；取 DEPLOYING 态单位使两分支均不中=无操作
        #（M18：DEPLOYING 期重复下达不重置计时——纯清空语义可独立断言）
        w = make_world(9)
        u = add_unit(w, make_unit(w, LINE_TPL, 0, 0, (100000, 100000)))
        u.deploy_state = DeployState.DEPLOYING
        u.deploy_timer = 7
        queue_command(w, DeployCmd(unit=u))
        consume_commands(w)
        self.assertEqual(w.command_queue, [])
        self.assertEqual((u.deploy_state, u.deploy_timer),
                         (DeployState.DEPLOYING, 7))    # M18 重复下达不重置


# ── ⑧ 经济块（§F7 :1374-1405 + §F8 :1476-1479 + D031）──

class TestCmdPurchase(unittest.TestCase):
    def _world(self, seed=42):
        w = make_world(seed, phase=PHASE_DEPLOY)
        w.players[0].points = 100
        w.players[0].deck_slots = [DeckSlot(template=LINE_TPL, copies_left=2)]
        return w

    def test_accept_deducts_points_copies_and_queues(self):
        # §F7 :1378-1379：扣点 100−20=80、扣 DeckSlot 份 2→1、卡入 spawn_queue（零掷骰）
        w = self._world()
        p = w.players[0]
        rng0 = [r.state for r in w.rng._rngs]
        self.assertTrue(cmd_purchase(w, p, LINE_TPL))
        self.assertEqual((p.points, p.deck_slots[0].copies_left,
                          len(p.spawn_queue)), (80, 1, 1))
        self.assertIs(p.spawn_queue[0], LINE_TPL)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)

    def test_reject_outside_deploy_phase(self):
        # §F7 :1374 "仅盲部署 phase"：实战期出牌 REJECT，零副作用
        w = make_world(7)                               # 默认 phase=COMBAT
        p = w.players[0]
        p.points = 100
        p.deck_slots = [DeckSlot(template=LINE_TPL, copies_left=2)]
        self.assertFalse(cmd_purchase(w, p, LINE_TPL))
        self.assertEqual((p.points, p.deck_slots[0].copies_left,
                          len(p.spawn_queue)), (100, 2, 0))

    def test_reject_no_slot_or_exhausted_or_insufficient_points(self):
        # :1376-1377 三门：卡组无此卡 / 余量尽（一命制不回补）/ 点数不足
        w = self._world(seed=9)
        p = w.players[0]
        self.assertFalse(cmd_purchase(w, p, TANK_TPL))  # 卡组无此卡
        p.deck_slots[0].copies_left = 0
        self.assertFalse(cmd_purchase(w, p, LINE_TPL))  # 一命制余量尽
        self.assertEqual(p.points, 100)
        p.deck_slots[0].copies_left = 1
        p.points = 19                                   # < cost 20
        self.assertFalse(cmd_purchase(w, p, LINE_TPL))
        self.assertEqual((p.points, p.deck_slots[0].copies_left,
                          len(p.spawn_queue)), (19, 1, 0))

    def test_purchase_cmd_dispatches_to_cmd_purchase(self):
        # §D.7 PurchaseCmd → §F7 cmd_purchase：盲部署拍命令流真落地（tick1 consume）
        w = self._world(seed=11)
        p = w.players[0]
        queue_command(w, PurchaseCmd(player=p, template=LINE_TPL))
        world_tick(w)
        self.assertEqual((w.tick, p.points, p.deck_slots[0].copies_left,
                          len(p.spawn_queue)), (1, 80, 1, 1))


class TestSpawnStep(unittest.TestCase):
    def _world(self, seed=42, phase=PHASE_DEPLOY):
        w = make_world(seed, phase=phase)
        return w

    def test_interval_gate_and_fifo_per_player(self):
        # §F7 :1381-1384：非间隔拍整函数早退；间隔拍逐玩家 pop(0)（FIFO 出牌序）
        w = self._world()
        p = w.players[0]
        p.spawn_queue = [LINE_TPL, TANK_TPL]
        w.tick = 11                                     # 11 % 10 ≠ 0：节流门
        spawn_step(w)
        self.assertEqual((len(w.units), len(p.spawn_queue)), (0, 2))
        w.tick = 10
        spawn_step(w)
        self.assertEqual(len(w.units), 1)
        self.assertIs(w.units[0].template, LINE_TPL)    # 先入先出
        self.assertEqual(len(p.spawn_queue), 1)
        w.tick = 20
        spawn_step(w)
        self.assertEqual(len(w.units), 2)
        self.assertIs(w.units[1].template, TANK_TPL)

    def test_deploy_anchor_point_stacking(self):
        # 2026-10-03 拍板（PB-16）：地面单位抽象为无宽度点单位——出生直落己方部署区
        # 锚点（=底边中点，部署区数据缺失），多单位叠放同点、无出牌序偏移
        w = self._world()
        for p, team in ((w.players[0], 0), (w.players[1], 1)):
            p.spawn_queue = [LINE_TPL, LINE_TPL]
        w.tick = 10
        spawn_step(w)
        self.assertEqual(w.units[0].pos, (500000, 0))
        self.assertEqual(w.units[1].pos, (500000, 1000000))
        self.assertEqual((w.units[0].team, w.units[0].id), (0, 1))
        w.tick = 20
        spawn_step(w)
        self.assertEqual(w.units[2].pos, (500000, 0))    # 点单位叠放（无偏移）
        self.assertEqual(w.units[3].pos, (500000, 1000000))
        self.assertEqual([p.spawn_serial for p in w.players], [2, 2])  # 序只计账

    def test_infiltrator_random_edge_point_deterministic(self):
        # 2026-10-03 拍板：渗透卡沿边随机入场（随机选边+沿边随机点，ECONOMY 通道
        # 两掷）——敌方底边除外；同 seed 双 world 逐张同位；仅 ECONOMY 通道被消费；
        # 盲部署期计时仍置 0。地图 1000000×1000000（_world 件）
        w = self._world()
        w.players[0].spawn_queue = [INFIL_TPL] * 6
        w.players[1].spawn_queue = [INFIL_TPL] * 6
        rng0 = [r.state for r in w.rng._rngs]
        for t in range(10, 70, 10):                     # 每拍逐玩家各出一张
            w.tick = t
            spawn_step(w)
        self.assertEqual(len(w.units), 12)
        width = height = 1000000
        for u in w.units:
            x, y = u.pos
            own_edge = (y == 0) if u.team == 0 else (y == height)
            self.assertTrue(own_edge or x == 0 or x == width)   # 合法边（含角）
            enemy_edge = ((y == height) if u.team == 0 else (y == 0)) \
                and x not in (0, width)
            self.assertFalse(enemy_edge)                # 敌方底边（除角）不可达
            self.assertEqual(u.infiltration_timer, 0)   # 非实战 spawn 置 0
        names = ("HIT", "SCATTER", "SPOT", "CRIT", "SNIPER", "SONAR",
                 "ECONOMY", "AIR")
        changed = [n for n, r, s in zip(names, w.rng._rngs, rng0)
                   if r.state != s]
        self.assertEqual(changed, ["ECONOMY"])          # 12 张 × 2 掷只动 ECONOMY
        w2 = self._world()
        w2.players[0].spawn_queue = [INFIL_TPL] * 6
        w2.players[1].spawn_queue = [INFIL_TPL] * 6
        for t in range(10, 70, 10):
            w2.tick = t
            spawn_step(w2)
        self.assertEqual([u.pos for u in w2.units], [u.pos for u in w.units])

    def test_infiltrator_spawned_in_combat_gets_timer(self):
        # :1393-1399 实战期 spawn 补置 600（盲部署期置 0——v1.6 ④A）
        w = self._world(phase=PHASE_COMBAT)
        w.players[0].spawn_queue = [INFIL_TPL]
        w.tick = 10
        spawn_step(w)
        self.assertEqual(w.units[0].infiltration_timer, 600)

    def test_mixed_card_default_mounted_form(self):
        # :1389-1392 R-07 开局车载默认形态：squads[i]↔carriers[i] 预挂 mounted_in
        # （同卡只写 mounted_in）；车少班多时溢出班不挂
        w = self._world()
        w.players[0].spawn_queue = [MIXED_TPL, MIXED_OVERFLOW_TPL]
        w.tick = 10
        spawn_step(w)
        u = w.units[0]                                  # 元素序=squad,squad,car,car
        self.assertIs(u.elements[0].mounted_in, u.elements[2])
        self.assertIs(u.elements[1].mounted_in, u.elements[3])
        self.assertIs(u.elements[2].mounted_in, None)   # 车自身不挂
        w.tick = 20
        spawn_step(w)
        v = w.units[1]                                  # 3 班 1 车：仅首班挂
        self.assertIs(v.elements[0].mounted_in, v.elements[3])
        self.assertIs(v.elements[1].mounted_in, None)
        self.assertIs(v.elements[2].mounted_in, None)

    def test_aa_roster_registered_on_spawn(self):
        # :1400-1401 对空名单登记（add_unit 承载）：optics_air_cm>0 入册、普通卡不入
        w = self._world()
        w.players[0].spawn_queue = [AA_WATCH_TPL, LINE_TPL]
        w.tick = 10
        spawn_step(w)
        self.assertIn(w.units[0], w.aa_roster)
        w.tick = 20
        spawn_step(w)
        self.assertNotIn(w.units[1], w.aa_roster)

    def test_spawn_pipeline_through_world_tick(self):
        # world_tick 全链：tick1 命令购 2 卡（points 100−2×20=60）→ tick10/20 各出一牌
        w = self._world(seed=13)
        p = w.players[0]
        p.points = 100
        p.deck_slots = [DeckSlot(template=LINE_TPL, copies_left=2)]
        queue_command(w, PurchaseCmd(player=p, template=LINE_TPL))
        queue_command(w, PurchaseCmd(player=p, template=LINE_TPL))
        for _ in range(9):
            world_tick(w)
        self.assertEqual((w.tick, len(w.units), len(p.spawn_queue)), (9, 0, 2))
        world_tick(w)                                   # tick10：⑧ 经济出牌
        self.assertEqual((w.tick, len(w.units), len(p.spawn_queue)), (10, 1, 1))
        for _ in range(9):
            world_tick(w)
        self.assertEqual(len(w.units), 1)
        world_tick(w)                                   # tick20：第二张
        self.assertEqual((len(w.units), len(p.spawn_queue), p.points), (2, 0, 60))


class TestSystemObjectives(unittest.TestCase):
    def _world(self, seed=42):
        w = make_world(seed)
        w.objectives = [Objective(id=1, pos=(500000, 500000), radius_cm=10000)]
        return w

    def test_sole_team_inside_captures(self):
        # §F7 :1404-1405 半径内仅一队存活 → owner=该队（含等号边界 dist==radius）
        w = self._world()
        add_unit(w, make_unit(w, LINE_TPL, 0, 0, (500000, 500000)))
        add_unit(w, make_unit(w, LINE_TPL, 0, 0, (510000, 500000)))  # dist 恰 10000
        add_unit(w, make_unit(w, LINE_TPL, 1, 1, (600000, 500000)))  # 场外
        rng0 = [r.state for r in w.rng._rngs]
        system_objectives(w)
        self.assertEqual(w.objectives[0].owner, 0)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)       # 占点零掷骰

    def test_contested_and_empty_no_write(self):
        # 双方在场（争夺）与空场均不写；换占时直接改写
        w = self._world()
        u0 = add_unit(w, make_unit(w, LINE_TPL, 0, 0, (500000, 500000)))
        u1 = add_unit(w, make_unit(w, LINE_TPL, 1, 1, (505000, 500000)))
        system_objectives(w)
        self.assertIsNone(w.objectives[0].owner)         # 争夺：不写
        u0.pos = (700000, 500000)
        system_objectives(w)
        self.assertEqual(w.objectives[0].owner, 1)       # 仅队1 → 改写
        u1.alive = False                                 # 阵亡不计（存活门）
        system_objectives(w)
        self.assertEqual(w.objectives[0].owner, 1)       # 空场：保持
        u0.pos = (500000, 500000)
        system_objectives(w)
        self.assertEqual(w.objectives[0].owner, 0)

    def test_objectives_run_on_second_boundary_via_economy(self):
        # world_tick :1438 %10 门 → system_objectives 每秒执行：tick9 不判、tick10 判
        w = self._world(seed=7)
        add_unit(w, make_unit(w, LINE_TPL, 1, 1, (500000, 500000)))
        for _ in range(9):
            world_tick(w)
        self.assertIsNone(w.objectives[0].owner)
        world_tick(w)
        self.assertEqual(w.objectives[0].owner, 1)


class TestSystemEconomyNoIncome(unittest.TestCase):
    """2026-10-03 拍板：收入机制整体删除（"没有收入机制"）——点数只在购卡时扣减。"""

    def test_points_never_accrue_over_time(self):
        # 25 拍（含两个整秒拍）点数纹丝不动；经济链仍驱动出牌与占点
        w = make_world(42)
        rng0 = [r.state for r in w.rng._rngs]
        for _ in range(25):
            world_tick(w)
        self.assertEqual([p.points for p in w.players], [1000, 1000])
        self.assertEqual([r.state for r in w.rng._rngs], rng0)  # 经济零掷骰

    def test_economy_direct_call_spawns_and_captures_without_income(self):
        # :1476-1479 直调口径：无收入步骤——出牌（节流门内）→ 占点
        w = make_world(3)
        w.objectives = [Objective(id=1, pos=(0, 0), radius_cm=10000)]
        add_unit(w, make_unit(w, LINE_TPL, 1, 1, (0, 0)))
        w.tick = 10
        system_economy(w)
        self.assertEqual((w.players[0].points, w.players[1].points,
                          w.objectives[0].owner), (1000, 1000, 1))


class TestSettlement(unittest.TestCase):
    def _combat_world_at_settle_boundary(self, seed):
        w = make_world(seed)
        w.phase = PHASE_COMBAT
        w.phase_start_tick = 0
        w.tick = 13201                                  # 13201 − 0 > 13200 → 本拍迁结算
        return w

    def test_objective_count_decides(self):
        # D031/GDD-00 :137：占点数多者胜（2:1 → 队0），不比单位分值
        w = self._combat_world_at_settle_boundary(42)
        w.objectives = [Objective(id=i, pos=(0, 0), radius_cm=1, owner=o)
                        for i, o in ((1, 0), (2, 0), (3, 1))]
        add_unit(w, make_unit(w, LINE_TPL, 1, 1, (0, 0)))   # 队1 分值 20 也不救
        update_phase(w)
        self.assertEqual(w.phase, PHASE_SETTLE)
        self.assertEqual(w.result.winner, 0)
        self.assertEqual(w.result.obj_counts, (2, 1))
        self.assertEqual(w.result.unit_scores, (0, 20))

    def test_tie_broken_by_ground_unit_score(self):
        # D031/GDD-00 :196：占点平局 → 剩余地面单位分值（Σ template.cost）多者胜
        w = self._combat_world_at_settle_boundary(9)
        w.objectives = [Objective(id=1, pos=(0, 0), radius_cm=1, owner=0),
                        Objective(id=2, pos=(0, 0), radius_cm=1, owner=1)]
        add_unit(w, make_unit(w, LINE_TPL, 0, 0, (0, 0)))   # 20
        add_unit(w, make_unit(w, TANK_TPL, 1, 1, (0, 0)))   # 60
        update_phase(w)
        self.assertEqual(w.result.winner, 1)
        self.assertEqual(w.result.unit_scores, (20, 60))
        self.assertEqual(ground_unit_score(w, 0), 20)

    def test_full_tie_falls_through_to_team0_no_draw(self):
        # 2026-10-03 拍板四链：占点/分值/血量全同（双方在场血量皆 0）→ 兜底判队 0
        # 胜（无平局，winner 恒非 None）；阵亡单位不计分值
        w = self._combat_world_at_settle_boundary(11)
        w.objectives = [Objective(id=1, pos=(0, 0), radius_cm=1, owner=0),
                        Objective(id=2, pos=(0, 0), radius_cm=1, owner=1)]
        dead = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (0, 0)))
        dead.alive = False                                 # 队0 分值归零
        update_phase(w)
        self.assertEqual(w.result.winner, 0)               # 四链兜底：必出胜者
        self.assertEqual(w.result.unit_scores, (0, 0))
        self.assertEqual(w.result.hp_totals, (0, 0))

    def test_hp_tier_breaks_score_tie(self):
        # 四链第三级：占点/分值同 → 剩余地面单位总血量多者胜（两班各 20 分、4 vs 7 血）
        w = self._combat_world_at_settle_boundary(15)
        w.objectives = [Objective(id=1, pos=(0, 0), radius_cm=1, owner=0),
                        Objective(id=2, pos=(0, 0), radius_cm=1, owner=1)]
        a = add_unit(w, make_unit(w, LINE_TPL, 0, 0, (0, 0)))
        b = add_unit(w, make_unit(w, LINE_TPL, 1, 1, (0, 0)))
        a.elements[0].hp_current = 4
        b.elements[0].hp_current = 7
        update_phase(w)
        self.assertEqual(w.result.winner, 1)
        self.assertEqual(w.result.unit_scores, (20, 20))
        self.assertEqual(w.result.hp_totals, (4, 7))

    def test_settlement_on_world_tick_settle_transition(self):
        # 全链：13800 拍仍实战（result None）→ 13801 拍迁结算拍当场裁决
        w = make_world(13, phase=PHASE_DEPLOY)
        w.objectives = [Objective(id=1, pos=(500000, 500000), radius_cm=10000,
                                  owner=None)]
        add_unit(w, make_unit(w, LINE_TPL, 0, 0, (500000, 500000)))
        w.tick = 13799
        world_tick(w)                                      # 13800：仍实战
        self.assertEqual(w.phase, PHASE_COMBAT)
        self.assertIsNone(w.result)
        world_tick(w)                                      # 13801：迁入结算
        self.assertEqual(w.phase, PHASE_SETTLE)
        self.assertEqual(w.result.winner, 0)               # 1:0 占点
        self.assertEqual(w.result.obj_counts, (1, 0))

    def test_resolve_settlement_pure_call(self):
        # 裁决函数纯调用（不迁相位）：无占点无单位 → 三级证据全零、四链兜底队 0 胜
        w = make_world(5)
        s = resolve_settlement(w)
        self.assertEqual(s.winner, 0)
        self.assertEqual((s.obj_counts, s.unit_scores, s.hp_totals),
                         ((0, 0), (0, 0), (0, 0)))


class TestDeterminismDualRun(unittest.TestCase):
    def test_dual_run_with_commands_bit_identical(self):
        # 同 seed 两 world（DEPLOY 起步 + 渗透班），开局与第 700 拍拍间入队相同命令流，
        # 逐 tick 比指纹至 1500 拍（跨 600 相位边界 + 迁入实战渗透置位）；
        # 末态锚点：phase=COMBAT、渗透计时 600−150=450
        def build(seed):
            w = make_world(seed, phase=PHASE_DEPLOY)
            add_unit(w, make_unit(w, INFIL_TPL, 0, 0, (300000, 300000)))
            add_unit(w, make_unit(w, LINE_TPL, 1, 1, (700000, 700000)))
            queue_command(w, MoveCmd(unit=w.units[0], path=[(400000, 400000)]))
            queue_command(w, PurchaseCmd(player=w.players[1], template=LINE_TPL))
            return w

        w1, w2 = build(42), build(42)
        for i in range(1500):
            if i == 700:                                  # 中途同拍入队（两 world 同序）
                for w in (w1, w2):
                    queue_command(w, DeployCmd(unit=w.units[0]))
                    queue_command(w, SmokeCmd(element=w.units[0].elements[0],
                                              point=(500000, 500000)))
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(fingerprint(w1), fingerprint(w2))
        self.assertEqual(w1.phase, PHASE_COMBAT)
        # 迁入实战拍 601 置 600 → 1201 拍自然耗尽；1500 拍末态为 0（全程递减已锚定）
        self.assertEqual(w1.units[0].infiltration_timer, 0)

    def test_economy_dual_run_45_ticks_bit_identical(self):
        # ⑧ 经济指纹双跑：同 seed 两 world（DEPLOY + 双方卡组/占点/收入），逐 tick 比
        # 经济指纹（points/出牌队列/出牌序/占点 owner/裁决 + 单位与八通道 state）至
        # 45 拍——覆盖 tick10/20/30/40 四次经济拍、队0 两卡一渗透混合出牌与两侧占点改写
        def eco_fingerprint(w):
            parts = ["t%d:p%d:r%s" % (
                w.tick, w.phase, ",".join(str(r.state) for r in w.rng._rngs))]
            for u in w.units:
                mref = "-" if u.elements[0].mounted_in is None \
                    else "M%d" % u.elements[0].mounted_in.id
                parts.append("U%d,%d,%s,%d,%d,%s" % (
                    u.id, u.team, u.pos, int(u.alive), u.infiltration_timer, mref))
            for pl in w.players:
                parts.append("PL%d,%d,%d,%d,%s" % (
                    pl.index, pl.points, pl.spawn_serial, len(pl.spawn_queue),
                    [s.copies_left for s in pl.deck_slots]))
            for o in w.objectives:
                parts.append("O%d,%s" % (o.id, o.owner))
            parts.append("R%s" % (w.result,))
            return "|".join(parts)

        def build(seed):
            w = make_world(seed, phase=PHASE_DEPLOY)
            w.players[0].points = 200
            w.players[0].deck_slots = [DeckSlot(LINE_TPL, 2), DeckSlot(TANK_TPL, 1)]
            w.players[1].deck_slots = [DeckSlot(INFIL_TPL, 2)]
            w.objectives = [Objective(id=1, pos=(500000, 0), radius_cm=30000),
                            Objective(id=2, pos=(500000, 1000000), radius_cm=30000)]
            queue_command(w, PurchaseCmd(player=w.players[0], template=LINE_TPL))
            queue_command(w, PurchaseCmd(player=w.players[0], template=TANK_TPL))
            queue_command(w, PurchaseCmd(player=w.players[1], template=INFIL_TPL))
            return w

        w1, w2 = build(42), build(42)
        for i in range(45):
            if i == 21:                                   # 中途同拍再购（两 world 同序）
                for w in (w1, w2):
                    queue_command(w, PurchaseCmd(player=w.players[0],
                                                 template=LINE_TPL))
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(eco_fingerprint(w1), eco_fingerprint(w2))
        # 末态锚点（2026-10-03 拍板后口径手推：tick1 购 3 卡 → 队0 200−80=120、
        # 队1 980（无收入机制——点数不再随时间增长）；tick10 出 LINE0@锚点
        # (500000,0) 改写 obj1=0；队1 INFIL0 随机落点 (657354,1000000)（seed 42
        # ECONOMY 前两掷：边 0=己方底边、x=657354）距 obj2 (500000,1000000)
        # 157354 > 30000 半径 → obj2 无唯一在场队不改写 owner=None；
        # tick20 TANK1@锚点叠放；tick22 补购队0 −20=100；tick30 LINE2@锚点叠放；
        # 队1 仅购 1 卡 → serial 1）
        self.assertEqual(w1.players[0].points, 100)
        self.assertEqual(w1.players[1].points, 980)
        self.assertEqual((w1.players[0].spawn_serial,
                          w1.players[1].spawn_serial), (3, 1))
        self.assertEqual([o.owner for o in w1.objectives], [0, None])
        self.assertEqual(len(w1.units), 4)
        self.assertIsNone(w1.result)


if __name__ == "__main__":
    unittest.main()
