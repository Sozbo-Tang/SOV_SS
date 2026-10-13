"""MOVEMENT_PSEUDOCODE_v1.2 命令层测试（2026-10-04 命令层块）：§2.2 issue_move/
handoff（BLK-1/AMB-11 分支次序）/门 1·3·4/HaltCmd(StopCmd)/SprintCmd 写点/
consume_unit_commands（T-queue-1）/current_order；§2.4 dispatch（MARCH 道路门/
到达模式复位/§2.5 攻击前进保持）；§2.8 队形三表（含 §2.8 楔形锚点）；§2.10-8
D072 疾跑禁射两门。

锚点算术（§2.2 要点⑤/T-queue-1 规格，全部手推不自证）：
- 档 5 轮式 v=140×5000//10000=70 cm/tick ⇒ 7000cm 段恰 100 拍；
- 档 2 轮式 v=45×5000//10000=22；道路下限 road_bonus_cm_tick=170（MARCH∧on_road
  取 max——契约⑦）；步兵 FOOT 越野 25×8000//10000=20（不吃道路）；
- sprint_duration_ticks=100（§D.0）：sprint_until=now+100。

PB-56 批③ Formation 族块（2026-10-06）增面：FormationCmd 写槽/分派链、
issue_group_move（§2.9 组下令）、move_speed_cm_tick §2.3 增量① 档位钳制消费者
——T-queue-2 v 相等断言就此补锚（原 test_cap_kept… 重锚：cap=2 下 v 由 70→22，
原 101 拍时序假设随消费者接线失效，重写为全规格双单位编组版）。

速度链块（2026-10-06）增面：TestReverseDispatch（§2.3 增量②+§2.4 增量④ 的
dispatch/world_tick 集成——倒车 17/拍逐拍锚+facing 全程锁定+到位模式复位）、
TestAutoApproach（§2.11 超射程进位纯函数锚：射程内 None/standoff+DIR8 方位/
AMB-4 半射程下界/斜向/nearest_on_segment 线段最近点；消费锚=cmd_fire_mission
在 tests/test_ground_combat.py TestAutoApproachConsumption；速度乘区单元锚在
tests/test_movement.py）。

命令族收口块（2026-10-07）增面：TestIssueMove 门1 族重锚+扩（发起人拍板
pack_or_move 移动触发面=采 IMPL 字面——DEPLOYING×外部=作废放行/DEPLOYED=转收装
再走/PACKING 拒维持/效果点后置零副作用/queue=TRUE 执行拍收装）；TestCancelCmd
（MV-B-18 另半全清变体——cancel 全清 vs halt 保动作令对照/ROUTED 拒/stance 不动/
零掷骰）；TestReverseDispatch 增 ReverseCmd 命令流归一化锚（≡MoveCmd(mode=
REVERSE)/FOOT 门4 拒/halt 过滤防御位/零掷骰）；TestHaltAndSprint 冷却门重锚+独立
窗锚（窗内拒不变/窗外重写/首冲哨兵豁免）；cap-literal 门拒载体 DEPLOYING→PACKING
重锚（DEPLOYING 不再拒外部移动令）。
"""
import unittest

from sovs.sim.movement import (attack_move_engage_hold, auto_approach_waypoint,
                               current_order, issue_move, make_formation_fn,
                               move_speed_cm_tick, nearest_on_segment,
                               system_move_dispatch)
from sovs.sim.pathfind import TerrainLayer, TerrainTile
from sovs.sim.tables import CONFIG
from sovs.sim.tick import (AttackCmd, CancelCmd, DismountCmd, FormationCmd,
                           MoveCmd, ReverseCmd,
                           SprintCmd, StopCmd,
                           add_unit, cmd_halt, cmd_sprint,
                           consume_commands, consume_unit_commands,
                           fire_permitted,
                           issue_group_move, make_unit, make_world,
                           queue_command, world_tick)
from sovs.sim.types import (DamageType, DeployState, ElementInstance,
                            ElementTemplate, ElementType, FireMission,
                            FireMissionForm, FormationShape,
                            MoraleState,
                            MovementClass, MoveMode, Stance, TargetDomain,
                            TowState, Trajectory, UnitTemplate, UnitType,
                            WeaponTemplate, WState)


def wheel_tpl(speed_tier=5, weapons=(), template_id=901, optics_cm=20000):
    return UnitTemplate(
        template_id=template_id, name="wheel plt", category=2, cost=100,
        element_templates=(ElementTemplate(
            element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
            hp_max=10, weapons=tuple(weapons)),),
        optics_ground_cm=optics_cm, stealth_base=3, speed_tier=speed_tier,
        movement_class=MovementClass.WHEEL)


def foot_tpl(template_id=902):
    return UnitTemplate(
        template_id=template_id, name="foot plt", category=1, cost=40,
        element_templates=(ElementTemplate(
            element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
            hp_max=10),),
        optics_ground_cm=20000, stealth_base=5, speed_tier=1,
        movement_class=MovementClass.FOOT)


GUN_W = WeaponTemplate(                    # 地面直射武器（攻击前进射程判据）
    name="gun", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    damage=3, salvo=1, aim_time_ticks=5, reload_time_ticks=30, ammo_base=10,
    max_range_cm=50000, dispersion_cm=300, accuracy_base_bp=8000,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    suppression_power=2, reveal_time_ticks=10)


def mk_unit(w, tpl, team=0, pos=(0, 0)):
    return add_unit(w, make_unit(w, tpl, team, team, pos))


# ── §2.2 issue_move：覆盖四件一体 / 排队 / handoff / 门 1·3·4 ──

class TestIssueMove(unittest.TestCase):
    def _u(self, tier=5):
        w = make_world(11)
        return w, mk_unit(w, wheel_tpl(tier), pos=(0, 0))

    def test_external_new_order_overrides_fourfold(self):
        # GAP-18 硬规则：外部非排队新令=清 move_path+换模式+清链+清 cap 四件一体
        w, u = self._u()
        u.move_path = [(1000, 0)]
        u.move_mode = MoveMode.MARCH
        u.command_queue = [MoveCmd(unit=u, path=[(9000, 0)])]
        u.group_speed_cap = 3
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=u, path=[(7000, 0)])))
        self.assertEqual(u.move_path, [(7000, 0)])
        self.assertEqual(u.move_mode, MoveMode.NORMAL)
        self.assertEqual(u.command_queue, [])
        self.assertEqual(u.group_speed_cap, 0)

    def test_queue_true_appends_without_touching_state(self):
        # GAP-05 Shift 排队：入链尾——不动进行中移动令/模式/cap
        w, u = self._u()
        u.move_path = [(1000, 0)]
        u.move_mode = MoveMode.MARCH
        u.group_speed_cap = 3
        cmd = MoveCmd(unit=u, path=[(7000, 0)], queue=True)
        self.assertTrue(issue_move(w, CONFIG, cmd))
        self.assertEqual(u.move_path, [(1000, 0)])
        self.assertEqual(u.move_mode, MoveMode.MARCH)
        self.assertEqual(u.group_speed_cap, 3)
        self.assertIs(u.command_queue[0], cmd)

    def test_handoff_installs_without_clearing(self):
        # BLK-1 核心：内部移交通道只装 move_path+换 mode——不清链不清 cap
        w, u = self._u()
        u.command_queue = [MoveCmd(unit=u, path=[(9000, 0)], queue=True)]
        u.group_speed_cap = 2
        self.assertTrue(issue_move(
            w, CONFIG, MoveCmd(unit=u, path=[(7000, 0)]), handoff=True))
        self.assertEqual(u.move_path, [(7000, 0)])
        self.assertEqual(u.move_mode, MoveMode.NORMAL)
        self.assertEqual(len(u.command_queue), 1)      # 链未被清
        self.assertEqual(u.group_speed_cap, 2)         # cap 未被清（跨队列令保持）

    def test_handoff_branch_precedes_queue_branch(self):
        # AMB-11 冻结分支次序：queue=False + handoff=TRUE 并传时 handoff 先判——
        # 不走"非排队覆盖"分支清链清 cap（若先判 queue，BLK-1 经此复活）
        w, u = self._u()
        u.command_queue = [MoveCmd(unit=u, path=[(9000, 0)], queue=True)]
        u.group_speed_cap = 2
        self.assertTrue(issue_move(
            w, CONFIG, MoveCmd(unit=u, path=[(7000, 0)], queue=False),
            handoff=True))
        self.assertEqual(len(u.command_queue), 1)
        self.assertEqual(u.group_speed_cap, 2)
        self.assertEqual(u.move_path, [(7000, 0)])

    def test_gate1_deploying_move_voids_and_passes(self):
        # 2026-10-07 发起人拍板重锚（pack_or_move 移动触发面=采 IMPL 字面，原
        # test_gate1_deploying_rejects 翻转）：DEPLOYING×外部移动令=作废展开进度
        # 回 MOBILE 同拍放行（机制版 v1.7 :1098 字面=cmd_pack_or_move ② 同款）；
        # handoff 通道仍拒（排队令丢弃——test_rejected_queue_head_dropped_
        # not_requeued 既有锚）；PACKING 拒令维持（下方 packing 锚）
        w, u = self._u()
        u.deploy_state = DeployState.DEPLOYING
        u.deploy_timer = 120
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=u, path=[(7000, 0)])))
        self.assertEqual(u.move_path, [(7000, 0)])               # 同拍放行安装
        self.assertEqual((u.deploy_state, u.deploy_timer),
                         (DeployState.MOBILE, 0))                # 进度作废

    def test_gate1_packing_rejects(self):
        # 门1 收起中拒令维持（三文档均无「打断收装」写点——2026-10-07 拍板口径）
        w, u = self._u()
        u.deploy_state = DeployState.PACKING
        u.deploy_timer = 50
        self.assertFalse(issue_move(w, CONFIG, MoveCmd(unit=u, path=[(7000, 0)])))
        self.assertEqual((u.deploy_state, u.deploy_timer),
                         (DeployState.PACKING, 50))              # 拒令零副作用

    def test_gate1_deployed_move_packs_then_installs(self):
        # 2026-10-07 拍板（IMPL :1116 ① 半边）：DEPLOYED×外部移动令=转 PACKING+
        # 本令照常安装（不丢失）——收装完成前 system_move 同名门拦位移、毕后自动
        # 续走（「先收装再走」）；效果点后置=门2/3/4 拒令零副作用（见下锚）
        w, u = self._u()
        u.deploy_state = DeployState.DEPLOYED
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=u, path=[(7000, 0)])))
        self.assertEqual(u.move_path, [(7000, 0)])               # 本令已安装
        self.assertIs(u.deploy_state, DeployState.PACKING)       # 转收装
        self.assertEqual(u.deploy_timer, u.template.pack_time_ticks)

    def test_gate1_deployed_reverse_rejected_no_pack_side_effect(self):
        # 效果点后置（门4 拒零副作用）：FOOT 倒车资格拒 → 不触收装（DEPLOYED 保持）
        w = make_world(14)
        foot = mk_unit(w, foot_tpl(), pos=(0, 0))
        foot.deploy_state = DeployState.DEPLOYED
        self.assertFalse(issue_move(w, CONFIG, ReverseCmd(unit=foot,
                                                          dest=(-100, 0))))
        self.assertIs(foot.deploy_state, DeployState.DEPLOYED)   # 无收装副作用
        self.assertEqual(foot.move_path, [])

    def test_gate1_deployed_queue_true_appends_packs_on_execution(self):
        # queue=TRUE 排队令不触收装（入链尾）；执行拍经 handoff 到 DEPLOYED 分支
        # 照样转收装+安装（排队倒车令的收装面同构）
        w, u = self._u()
        u.deploy_state = DeployState.DEPLOYED
        cmd = MoveCmd(unit=u, path=[(7000, 0)], queue=True)
        self.assertTrue(issue_move(w, CONFIG, cmd))
        self.assertIs(u.deploy_state, DeployState.DEPLOYED)      # 入队不触
        self.assertEqual(u.command_queue, [cmd])
        consume_unit_commands(w)                                 # 执行拍（handoff）
        self.assertIs(u.deploy_state, DeployState.PACKING)       # 执行拍收装
        self.assertEqual(u.move_path, [(7000, 0)])

    def test_gate1_deployed_routed_handoff_packs_and_installs(self):
        # 溃逃航点形态（handoff 豁免门2）×DEPLOYED：同触收装+照装航点——收装完成
        # 前 system_move 同名门拦位移、毕后自动溃逃走（_enter_routed 留痕口径：
        # 「先收装再走」对失控移动同构成立）
        w, u = self._u()
        u.morale = MoraleState.ROUTED
        u.deploy_state = DeployState.DEPLOYED
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=u, path=[(7000, 0)]),
                                   handoff=True))
        self.assertIs(u.deploy_state, DeployState.PACKING)       # 同触收装
        self.assertEqual(u.move_path, [(7000, 0)])               # 溃逃航点已装

    def test_gate3_all_mounted_rejects(self):
        # GAP-2：整班车载（全部元素挂他卡载具）无独立移动令——与 system_move 早退
        # 双保险；同卡混编（载具+班）不算：载具自身未挂载、单位可机动
        w = make_world(12)
        carrier_tpl = UnitTemplate(
            template_id=903, name="carrier", category=4, cost=60,
            element_templates=(ElementTemplate(
                element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                hp_max=15, seats=2),),
            optics_ground_cm=20000, stealth_base=3, speed_tier=3,
            movement_class=MovementClass.WHEEL)
        squad_tpl = UnitTemplate(
            template_id=904, name="riders", category=1, cost=30,
            element_templates=(
                ElementTemplate(element_type=ElementType.SQUAD,
                                unit_type=UnitType.INFANTRY, hp_max=8),
                ElementTemplate(element_type=ElementType.SQUAD,
                                unit_type=UnitType.INFANTRY, hp_max=8)),
            optics_ground_cm=20000, stealth_base=5, speed_tier=1,
            movement_class=MovementClass.FOOT)
        carrier = mk_unit(w, carrier_tpl, pos=(0, 0))
        riders = mk_unit(w, squad_tpl, pos=(0, 0))
        for s in riders.elements:
            s.mounted_in = carrier.elements[0]
        self.assertFalse(issue_move(w, CONFIG, MoveCmd(unit=riders, path=[(7000, 0)])))
        self.assertEqual(riders.move_path, [])
        # 同卡混编对照：载具元素未挂载 → 门 3 不拒（载具驮班机动）
        mixed_tpl = UnitTemplate(
            template_id=905, name="mixed", category=1, cost=60,
            element_templates=(
                ElementTemplate(element_type=ElementType.VEHICLE,
                                unit_type=UnitType.MECH, hp_max=15, seats=2),
                ElementTemplate(element_type=ElementType.SQUAD,
                                unit_type=UnitType.INFANTRY, hp_max=8)),
            optics_ground_cm=20000, stealth_base=5, speed_tier=2,
            movement_class=MovementClass.WHEEL)
        mixed = mk_unit(w, mixed_tpl, pos=(0, 0))
        mixed.elements[1].mounted_in = mixed.elements[0]
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=mixed, path=[(7000, 0)])))
        self.assertEqual(mixed.move_path, [(7000, 0)])

    def test_gate4_reverse_eligibility(self):
        # AMB-9：FOOT/HORSE reverse_speed_bp=0 → 显式拒令（不产生 REVERSE 空转锁）
        w = make_world(13)
        foot = mk_unit(w, foot_tpl(), pos=(0, 0))
        self.assertFalse(issue_move(w, CONFIG, MoveCmd(
            unit=foot, path=[(7000, 0)], mode=MoveMode.REVERSE)))
        self.assertEqual(foot.move_mode, MoveMode.NORMAL)
        wheel = mk_unit(w, wheel_tpl(), pos=(0, 0))
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(
            unit=wheel, path=[(7000, 0)], mode=MoveMode.REVERSE)))
        self.assertEqual(wheel.move_mode, MoveMode.REVERSE)
        # 注：REVERSE 速度乘区/facing 锁定消费者（§2.3 增量②④）随速度链块落地——
        # 本块仅门 4 与模式槽（登记表口径，不冒充）

    def test_world_dispatch_move_then_halt(self):
        # 世界级收件箱 → 分派支真调用：MoveCmd 落地、StopCmd（HaltCmd 语义）清停
        w, u = self._u()
        queue_command(w, MoveCmd(unit=u, path=[(70, 0)]))
        world_tick(w)
        self.assertEqual(u.move_path, [])          # v=70：一拍即到
        self.assertEqual(u.pos, (70, 0))
        queue_command(w, MoveCmd(unit=u, path=[(7000, 0)]))
        world_tick(w)
        self.assertEqual(len(u.move_path), 1)
        queue_command(w, StopCmd(unit=u))
        world_tick(w)
        self.assertEqual(u.move_path, [])
        world_tick(w)
        self.assertEqual(u.pos, (140, 0))          # halt 后不再前进

    def test_find_path_consumed_by_issue_move(self):
        # ⑦块登记接线：命令航点逐段经 world.find_path 展开——terrain=None stub
        # 直线直填（与 list(cmd.path) 逐位一致）；接入地形层后绕行 bp=0 墙
        w, u = self._u()
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=u, path=[(76250, 1250)])))
        self.assertEqual(u.move_path, [(76250, 1250)])      # stub=直线直填
        u.move_path = []
        w.map_extent = (100000, 100000)
        w.terrain = TerrainLayer(tile_cm=2500, tiles={
            (2, iy): TerrainTile(speed_bp={MovementClass.WHEEL: 0})
            for iy in range(0, 37)})                          # ix=2 纵墙（iy 0..36，
                                                              # 北侧 iy 37..39 留缺口）
        u.pos = (1250, 1250)
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=u, path=[(76250, 1250)])))
        self.assertNotEqual(u.move_path, [(76250, 1250)])    # 绕行≠直线
        self.assertGreaterEqual(len(u.move_path), 2)
        for wp in u.move_path[:-1]:                           # 中途航点避开墙列
            self.assertNotEqual(wp[0] // 2500, 2)
        self.assertEqual(u.move_path[-1], (76250, 1250))     # 末点=精确目标

    def test_issue_move_hits_path_cache_and_invalidates(self):
        # PB-10 路径缓存随消费侧落地（2026-10-04 寻路接线块）：同位两单位同令
        # 第二次走缓存——move_path 位级一致；地形突变（原链中途航点格封墙）
        # → 换键重算出新绕行（缓存不吐旧路）
        w = make_world(62)
        w.map_extent = (100000, 100000)
        w.terrain = TerrainLayer(tile_cm=2500, tiles={
            (2, iy): TerrainTile(speed_bp={MovementClass.WHEEL: 0})
            for iy in range(0, 37)})
        u1 = mk_unit(w, wheel_tpl(5), pos=(1250, 1250))
        u2 = mk_unit(w, wheel_tpl(5, template_id=913), pos=(1250, 1250))
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=u1, path=[(76250, 1250)])))
        first = list(u1.move_path)
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=u2, path=[(76250, 1250)])))
        self.assertEqual(u2.move_path, first)                 # 命中缓存仍位级一致
        # 封死首航点所在格（在编瓦片原值替换——len 不变）：同令必须改道
        wp0 = first[0]
        w.terrain.tiles[(wp0[0] // 2500, wp0[1] // 2500)] = TerrainTile(
            speed_bp={MovementClass.WHEEL: 0})
        u2.move_path = []
        self.assertTrue(issue_move(w, CONFIG, MoveCmd(unit=u2, path=[(76250, 1250)])))
        self.assertNotEqual(u2.move_path, first)              # 缓存失效——真重算
        for wp in u2.move_path[:-1]:
            self.assertNotEqual((wp[0] // 2500, wp[1] // 2500),
                                (wp0[0] // 2500, wp0[1] // 2500))  # 新路避开封格
        self.assertEqual(u2.move_path[-1], (76250, 1250))


# ── §2.2 consume_unit_commands：T-queue-1 三令排队逐令执行 ──

class TestConsumeUnitCommands(unittest.TestCase):
    def test_t_queue_1_three_queued_legs(self):
        # §2.2 要点⑤ T-queue-1（v1.2 规格）：档 5 轮式载具（v=70）入队三段各
        # 7000cm——第 100/200 拍末 command_queue 长 2/1（链未被清）、到位拍后一拍
        # 安装下一段；300 拍后 pos==第三段终点、链空、模式复位 NORMAL
        w = make_world(21)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        for dest in ((7000, 0), (14000, 0), (21000, 0)):
            issue_move(w, CONFIG, MoveCmd(unit=u, path=[dest], queue=True))
        self.assertEqual(len(u.command_queue), 3)
        for _ in range(100):
            world_tick(w)
        self.assertEqual(len(u.command_queue), 2)             # 链未被清（BLK-1）
        self.assertEqual(u.pos, (7000, 0))                    # 第一段到位
        self.assertEqual(u.move_path, [])                     # 下一段于 101 拍安装
        world_tick(w)
        self.assertEqual(len(u.command_queue), 1)
        self.assertEqual(u.move_path, [(14000, 0)])           # 当前段
        for _ in range(99):
            world_tick(w)
        self.assertEqual(len(u.command_queue), 1)             # 第 200 拍末
        self.assertEqual(u.pos, (14000, 0))
        world_tick(w)
        self.assertEqual(u.command_queue, [])
        self.assertEqual(u.move_path, [(21000, 0)])
        for _ in range(99):
            world_tick(w)
        self.assertEqual(u.pos, (21000, 0))                   # 300 拍：第三段终点
        self.assertEqual(u.command_queue, [])
        self.assertEqual(u.move_path, [])
        self.assertEqual(u.move_mode, MoveMode.NORMAL)        # 到达复位

    def test_rejected_queue_head_dropped_not_requeued(self):
        # §2.2 成文口径：拒令不回队首防死锁——DEPLOYING 期排队移动令被丢弃、
        # 循环继续（后续令仍可消费）
        w = make_world(22)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        issue_move(w, CONFIG, MoveCmd(unit=u, path=[(7000, 0)], queue=True))
        issue_move(w, CONFIG, MoveCmd(unit=u, path=[(14000, 0)], queue=True))
        u.deploy_state = DeployState.DEPLOYING
        consume_unit_commands(w)
        self.assertEqual(u.command_queue, [])                 # 两令均被门 1 丢弃
        self.assertEqual(u.move_path, [])

    def test_non_normal_install_breaks_pass(self):
        # §2.2 字面：移动令安装后非 NORMAL → BREAK 交还控制（下一令须等到位）——
        # 空 path 的 MARCH 令安装后同拍不再消费后续令
        w = make_world(23)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        issue_move(w, CONFIG, MoveCmd(unit=u, path=[], mode=MoveMode.MARCH,
                                      queue=True))
        issue_move(w, CONFIG, MoveCmd(unit=u, path=[(7000, 0)], queue=True))
        consume_unit_commands(w)
        self.assertEqual(len(u.command_queue), 1)             # BREAK：第二令保留
        self.assertEqual(u.move_mode, MoveMode.MARCH)

    def test_t_queue_2_group_cap_v_equality_full(self):
        # §2.2 要点⑤ T-queue-2 全规格（PB-56 批③ Formation 族块 2026-10-06 补锚
        # ——§2.3 增量① 消费者接线后 v 相等断言可落）：同 WHEEL 类编组（档 5+档 2，
        # 类缺省 bp 均 5000）组下令+排队第二段：cap=2 下两单位 v 恒相等
        # （45×5000//10000=22，逐拍 pos 全等）；中途 command_queue 未清、
        # group_speed_cap==2 跨队列令保持（BLK-1）；对档 5 单位单独外部新令后
        # 其 cap==0、v 恢复 140×5000//10000=70。
        w = make_world(24)
        fast = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        slow = mk_unit(w, wheel_tpl(2, template_id=911), pos=(0, 0))
        issue_group_move(w, CONFIG, [fast, slow], [(7000, 0)])
        self.assertEqual(fast.group_speed_cap, 2)               # cap=MIN(5,2)
        self.assertEqual(slow.group_speed_cap, 2)
        self.assertEqual(fast.move_path, [(7000, 0)])           # 外部通道安装
        issue_move(w, CONFIG, MoveCmd(unit=fast, path=[(14000, 0)], queue=True))
        issue_move(w, CONFIG, MoveCmd(unit=slow, path=[(14000, 0)], queue=True))
        cap_seen, queue_seen = set(), set()
        for _ in range(639):                                    # 319+1+319=639 拍双段
            world_tick(w)
            self.assertEqual(fast.pos, slow.pos)                # v 恒相等（逐拍）
            cap_seen.update((fast.group_speed_cap, slow.group_speed_cap))
            queue_seen.add(len(fast.command_queue))
        self.assertEqual(fast.pos, (14000, 0))                  # 双段终点（22cm/拍手推：
        self.assertEqual(slow.pos, (14000, 0))                  # 318×22+4=7000/段）
        self.assertEqual(cap_seen, {2})                         # cap 全程保持（含跨段）
        self.assertEqual(queue_seen, {1, 0})                    # 链未被清、逐段消费
        self.assertEqual(move_speed_cm_tick(CONFIG, fast, w.tick), 22)  # 到位后 cap 仍钳
        # （槽跨令持续——§2.1 生命周期；mode 已复位 NORMAL 不影响 tier 钳制）
        # 单独外部新令（脱离编组）后 cap==0、v 恢复 70
        issue_move(w, CONFIG, MoveCmd(unit=fast, path=[(28000, 0)]))
        self.assertEqual(fast.group_speed_cap, 0)
        self.assertEqual(slow.group_speed_cap, 2)               # 编组另一员不受牵连
        self.assertEqual(move_speed_cm_tick(CONFIG, fast, w.tick), 70)
        self.assertEqual(move_speed_cm_tick(CONFIG, slow, w.tick), 22)
        for _ in range(10):
            world_tick(w)
        self.assertEqual(fast.pos[0] - 14000, 700)              # 70cm/拍脱离后
        self.assertEqual(slow.pos, (14000, 0))                  # 无令静止（v 差已由
                                                               # move_speed 断言锚定）


# ── §2.2 HaltCmd(StopCmd)/current_order + SprintCmd 写点 ──

# ── P0 键位纠偏块（2026-10-13）：动作令排队（手册 SHIFT=Queue orders 通用化）──


class TestP0ActionCommandQueue(unittest.TestCase):
    """AttackCmd/DismountCmd queue=True 经世界级命令流路由入单位级链，
    consume_unit_commands 空闲消费**每拍至多一条**（break 交还控制）；移动令
    到位阻塞保持（排队动作令须等前序移动到位）。引擎门拒绝的队列头照移动令
    口径丢弃不回队首。"""

    def test_action_cmds_route_to_unit_queue_and_consume_one_per_tick(self):
        w = make_world(31)
        u = mk_unit(w, wheel_tpl(5, weapons=(GUN_W,)), pos=(0, 0))
        foe = mk_unit(w, wheel_tpl(5), team=1, pos=(7000, 0))
        queue_command(w, AttackCmd(element=u.elements[0],
                                   target=foe.elements[0], queue=True))
        queue_command(w, DismountCmd(squad_unit=u, queue=True))
        consume_commands(w)                       # 世界级分派：queue=True → 单位链
        self.assertEqual(len(u.command_queue), 2)
        self.assertNotEqual(u.command_queue[0], u.command_queue[1])
        consume_unit_commands(w)                  # 空闲：pop 首条执行后 break
        self.assertEqual(len(u.command_queue), 1)
        consume_unit_commands(w)                  # 次拍再消费一条
        self.assertEqual(u.command_queue, [])

    def test_queued_action_waits_for_move_arrival(self):
        w = make_world(32)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        queue_command(w, MoveCmd(unit=u, path=[(7000, 0)], queue=True))
        queue_command(w, DismountCmd(squad_unit=u, queue=True))
        consume_commands(w)
        self.assertEqual(len(u.command_queue), 2)
        for _ in range(100):
            world_tick(w)                         # 移动令安装并到位（70cm/拍×100）
        self.assertEqual(u.pos, (7000, 0))
        self.assertEqual(len(u.command_queue), 1) # 动作令仍排队（move_path 阻塞）
        world_tick(w)                             # 到位后下一拍消费
        self.assertEqual(u.command_queue, [])

    def test_halt_keeps_queued_action_cmds(self):
        # StopCmd=保动作令（只清移动令条目）——排队攻击/卸载不受停止令牵连
        w = make_world(33)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        queue_command(w, MoveCmd(unit=u, path=[(7000, 0)], queue=True))
        queue_command(w, DismountCmd(squad_unit=u, queue=True))
        consume_commands(w)
        cmd_halt(u)
        self.assertEqual(len(u.command_queue), 1)     # 移动令被清
        self.assertIsInstance(u.command_queue[0], DismountCmd)


class TestHaltAndSprint(unittest.TestCase):
    def test_halt_clears_path_mode_and_queued_move_orders(self):
        # MV-B-18：清航点+复位模式+移出队列移动令（动作令保留——动作令入队路径
        # 随各自 cmd_* 处理体落地，当前队列仅 MoveCmd 可入）
        w = make_world(31)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        u.move_path = [(7000, 0)]
        u.move_mode = MoveMode.ATTACK
        u.command_queue = [MoveCmd(unit=u, path=[(14000, 0)], queue=True),
                           MoveCmd(unit=u, path=[(21000, 0)], queue=True)]
        cmd_halt(u)
        self.assertEqual(u.move_path, [])
        self.assertEqual(u.move_mode, MoveMode.NORMAL)
        self.assertEqual(u.command_queue, [])

    def test_halt_keeps_stance(self):
        w = make_world(32)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        u.stance = Stance.HOLD_FIRE
        cmd_halt(u)
        self.assertEqual(u.stance, Stance.HOLD_FIRE)          # 两命令均不动 stance

    def test_current_order_query(self):
        # GAP-18 推导式查询位（零新槽）
        w = make_world(33)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        self.assertEqual(current_order(u)["kind"], "IDLE")
        u.command_queue = [MoveCmd(unit=u, path=[(7000, 0)], queue=True)]
        self.assertEqual(current_order(u)["kind"], "QUEUED")
        u.move_path = [(7000, 0)]
        u.move_mode = MoveMode.ATTACK
        cur = current_order(u)
        self.assertEqual((cur["kind"], cur["mode"], cur["dest"]),
                         ("MOVE", MoveMode.ATTACK, (7000, 0)))

    def test_sprint_write_point_and_speed_window(self):
        # §D.0 :48/方案14：sprint_until=now+sprint_duration_ticks（唯一写点）；
        # 契约⑧ 速度式：升 1 档钳 5（既有 move_speed 消费——档 3 轮式 35→50）。
        # 2026-10-07 冷却门接线重锚（发起人拍板采纳）：冷却窗=开跑拍起 700t
        # （duration 100+cooldown 600）——受领拍 1 再令落窗内（1<700）→拒，
        # sprint_until 不变；窗外（tick 700=窗界不含）重写
        w = make_world(34)
        u = mk_unit(w, wheel_tpl(3), pos=(0, 0))
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 35)
        cmd_sprint(w, u, CONFIG)                              # w.tick=0 → until=100
        self.assertEqual(u.sprint_until, 100)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 50), 50)   # 档4=100×0.5
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 100), 35)  # 到期恢复
        queue_command(w, SprintCmd(unit=u))
        world_tick(w)                                         # 冷却窗内再令：拒
        self.assertEqual(u.sprint_until, 100)                 # 不变（原锚 101 作废）
        for _ in range(698):
            world_tick(w)                                     # 至 tick 699（窗内）
        self.assertEqual(w.tick, 699)
        queue_command(w, SprintCmd(unit=u))
        world_tick(w)                                         # tick 700：窗界外→重写
        self.assertEqual(u.sprint_until, 800)                 # 700+100

    def test_sprint_cooldown_gate_window(self):
        # 冷却门独立锚（2026-10-07 拍板采纳）：窗内再令 sprint_until 不变/窗外
        # 重写；首冲豁免（sprint_until 初值 0=从未冲刺哨兵——无哨兵则 tick<600
        # 首冲恒拒）；ROUTED 拒在冷却门之前（先例门序不动）
        w = make_world(35)
        u = mk_unit(w, wheel_tpl(3), pos=(0, 0))
        cmd_sprint(w, u, CONFIG)                              # tick 0 首冲 → until=100
        self.assertEqual(u.sprint_until, 100)
        w.tick = 650                                          # 窗内（650<100+600）
        cmd_sprint(w, u, CONFIG)
        self.assertEqual(u.sprint_until, 100)                 # 拒——不变
        w.tick = 700                                          # 窗界（700≮700）→放行
        cmd_sprint(w, u, CONFIG)
        self.assertEqual(u.sprint_until, 800)                 # 700+100 重写



# ── §2.2 CancelCmd（MV-B-18 另半·全清变体——2026-10-07 命令族收口块）──

class TestCancelCmd(unittest.TestCase):
    def _loaded(self, seed=36):
        w = make_world(seed)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        u.move_path = [(7000, 0)]
        u.move_mode = MoveMode.ATTACK
        u.pivot_to = 90                       # 进行中 pivot（PB-51 超集语义）
        u.command_queue = [MoveCmd(unit=u, path=[(14000, 0)], queue=True),
                           SprintCmd(unit=u)]
        u.fire_mission = FireMission(form=FireMissionForm.POINT,
                                     target_point=(1, 2), shots_left=5)
        u.stance = Stance.HOLD_FIRE
        return w, u

    def test_cancel_clears_everything_vs_halt_keeps_action_orders(self):
        # MV-B-18 边界对照锚：cancel=全清（航点+模式+pivot+**整个**队列——动作令
        # 一并清+任务体 fire_mission——发起人任务块口径）；halt=清移动令**保动作令**
        w, u = self._loaded()
        rng0 = [r.state for r in w.rng._rngs]
        queue_command(w, CancelCmd(unit=u))
        world_tick(w)                                          # 经命令流分派支
        self.assertEqual(u.move_path, [])
        self.assertIs(u.move_mode, MoveMode.NORMAL)
        self.assertEqual(u.pivot_to, -1)
        self.assertEqual(u.command_queue, [])                  # 动作令一并清
        self.assertIsNone(u.fire_mission)                      # 任务体清
        self.assertIs(u.stance, Stance.HOLD_FIRE)              # stance 不动
        self.assertEqual([r.state for r in w.rng._rngs], rng0)  # 全清链零掷骰
        # halt 对照：同载荷只清移动令，SprintCmd 动作令保留
        w2, u2 = self._loaded(seed=37)
        cmd_halt(u2)
        self.assertEqual(u2.command_queue, [u2.command_queue[0]])  # 非空=有保留
        self.assertEqual([type(c).__name__ for c in u2.command_queue],
                         ["SprintCmd"])
        self.assertIsNotNone(u2.fire_mission)                  # halt 不动任务体

    def test_cancel_routed_rejected(self):
        # ROUTED 拒（cmd_halt 先例对齐——清链等效失控干预；溃逃航点唯一清写点
        # =system_morale 重整拍）：全载荷原样保持
        w, u = self._loaded(seed=38)
        u.morale = MoraleState.ROUTED
        queue_command(w, CancelCmd(unit=u))
        world_tick(w)
        self.assertEqual(len(u.command_queue), 2)         # 未清（移动令+动作令）
        self.assertIsNotNone(u.fire_mission)
        self.assertEqual(u.pivot_to, 90)


# ── §2.10-8 D072 疾跑禁射两门 ──

class TestD072SprintFireGates(unittest.TestCase):
    def _armed(self):
        w = make_world(41)                                    # phase=COMBAT 默认
        u = mk_unit(w, wheel_tpl(5, weapons=(GUN_W,)), pos=(0, 0))
        return w, u, u.elements[0].weapon_states[0]

    def test_aiming_timer_frozen_reloading_continues(self):
        # 挂点=system_timers（GAP-3 修复）：AIMING 且 tick<sprint_until → 跳过
        # 递减（timer 永不归零 ⇒ 不发射不耗弹天然保证）；RELOADING 不冻结
        from sovs.sim.types import WeaponState
        w, u, ws = self._armed()
        reload_ws = WeaponState(template=GUN_W, state=WState.RELOADING,
                                timer=9, ammo_left=5)
        u.elements[0].weapon_states.append(reload_ws)
        ws.state = WState.AIMING
        ws.timer = 5
        cmd_sprint(w, u, CONFIG)                              # tick 0 → until=100
        for _ in range(10):
            world_tick(w)
        self.assertEqual(ws.timer, 5)                         # AIMING 冻结
        self.assertEqual(reload_ws.timer, 0)                  # RELOADING 照常递减
        for _ in range(90):
            world_tick(w)                                     # 至 tick 100（sprint 到期拍）
        self.assertEqual(w.tick, 100)
        self.assertEqual(ws.timer, 4)                         # 到期拍即恢复递减

    def test_fire_permitted_sprint_gate(self):
        # 索敌门（⑦）：sprint_until 期间 fire_permitted=False（不开新 AIMING）
        w, u, ws = self._armed()
        self.assertTrue(fire_permitted(w, u, u.elements[0], ws))
        cmd_sprint(w, u, CONFIG)
        self.assertFalse(fire_permitted(w, u, u.elements[0], ws))

    def test_ground_direct_no_new_aiming_while_sprinting(self):
        # §2.10-8 配套：冲刺期索敌门拦新 AIMING；到期后恢复（观察者光学 60000——
        # 敌 30000cm 内可持续被 system_sensing 保持发现位）
        w = make_world(42)
        u = mk_unit(w, wheel_tpl(5, (GUN_W,), optics_cm=60000), pos=(0, 0))
        ws = u.elements[0].weapon_states[0]
        foe = mk_unit(w, wheel_tpl(5, template_id=909), team=1, pos=(30000, 0))
        foe.spotted_mask = 1 << 0                             # 已发现
        cmd_sprint(w, u, CONFIG)
        for _ in range(3):
            world_tick(w)
        self.assertEqual(ws.state, WState.READY)              # 未进入 AIMING
        self.assertEqual(ws.ammo_left, GUN_W.ammo_base)       # 未耗弹
        for _ in range(98):
            world_tick(w)                                     # sprint 到期（tick 100）
        for _ in range(3):
            world_tick(w)
        self.assertEqual(ws.state, WState.AIMING)             # 恢复开火链


# ── §2.4 system_move_dispatch：MARCH 道路门 / 模式复位 / §2.5 攻击前进保持 ──

class TestDispatch(unittest.TestCase):
    def _road_world(self):
        w = make_world(51)
        w.terrain = TerrainLayer(tile_cm=2500, tiles={
            (ix, 0): TerrainTile(on_road=True) for ix in range(40)})
        return w

    def test_march_eats_road_normal_does_not(self):
        # 增量⑥/MV-B-17：on_road=(MARCH∧road_at)——档 2 轮式 22 → MARCH 上路 170；
        # 普通机动在路瓦片不吃道路档；FOOT 恒不吃（契约⑦ 冻结行内谓词）
        w = self._road_world()
        u_march = mk_unit(w, wheel_tpl(2, template_id=904), pos=(1250, 1250))
        issue_move(w, CONFIG, MoveCmd(unit=u_march, path=[(100000, 1250)],
                                      mode=MoveMode.MARCH))
        world_tick(w)
        self.assertEqual(u_march.pos[0] - 1250, 170)          # 道路下限取 max
        u_norm = mk_unit(w, wheel_tpl(2, template_id=905), pos=(1250, 6250))
        issue_move(w, CONFIG, MoveCmd(unit=u_norm, path=[(100000, 6250)]))
        world_tick(w)
        self.assertEqual(u_norm.pos[0] - 1250, 22)            # 普通机动不吃路
        w2 = make_world(52)
        w2.terrain = self._road_world().terrain
        f = mk_unit(w2, foot_tpl(), pos=(1250, 1250))
        issue_move(w2, CONFIG, MoveCmd(unit=f, path=[(100000, 1250)],
                                       mode=MoveMode.MARCH))
        world_tick(w2)
        self.assertEqual(f.pos[0] - 1250, 20)                 # FOOT 不吃道路

    def test_mode_resets_on_arrival(self):
        w = make_world(53)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        issue_move(w, CONFIG, MoveCmd(unit=u, path=[(70, 0)],
                                      mode=MoveMode.MARCH))
        world_tick(w)
        self.assertEqual(u.move_path, [])
        self.assertEqual(u.move_mode, MoveMode.NORMAL)        # §2.4 末行：到达复位

    def test_attack_engage_hold_predicate(self):
        # §2.5：单位首元素 pos × 敌元素 pos × MAX 自身地面武器射程 × spotted_mask
        w = make_world(54)
        u = mk_unit(w, wheel_tpl(5, weapons=(GUN_W,)), pos=(0, 0))
        foe = mk_unit(w, wheel_tpl(5, template_id=906), team=1,
                      pos=(30000, 0))                          # ≤50000 射程内
        foe.spotted_mask = 1 << 0
        self.assertTrue(attack_move_engage_hold(w, u))
        foe.spotted_mask = 0                                   # 未发现：不停
        self.assertFalse(attack_move_engage_hold(w, u))
        foe.spotted_mask = 1 << 0
        foe.elements[0].pos = (60000, 0)                       # 出射程（判据=元素 pos）：不停
        self.assertFalse(attack_move_engage_hold(w, u))
        foe.elements[0].pos = (30000, 0)
        foe.alive = False                                      # 被毁：不停
        self.assertFalse(attack_move_engage_hold(w, u))
        foe.alive = True
        carrier = ElementInstance(id=99, unit=foe, template=foe.elements[0].template,
                                  pos=foe.pos, hp_current=10)
        foe.elements[0].mounted_in = carrier                   # 车载班随车结算：不停
        self.assertFalse(attack_move_engage_hold(w, u))
        foe.elements[0].mounted_in = None
        self.assertTrue(attack_move_engage_hold(w, u))
        bare = mk_unit(w, wheel_tpl(5, template_id=907), pos=(0, 0))
        self.assertFalse(attack_move_engage_hold(w, bare))     # 无地面武器→R=0

    def test_attack_mode_holds_then_resumes(self):
        # GAP-04：遇已发现敌停下交战（move_path 预算暂停、无位移不触发出楼/退伏击
        # 副作用）；敌被毁自动恢复；保持期 moving() 仍真（MV-B-23 口径④）。
        # 观察者光学 60000：敌 30000cm 在 sensing 周期重算下保持发现位
        w = make_world(55)
        u = mk_unit(w, wheel_tpl(5, (GUN_W,), optics_cm=60000), pos=(0, 0))
        foe = mk_unit(w, wheel_tpl(5, template_id=908), team=1, pos=(30000, 0))
        foe.spotted_mask = 1 << 0
        issue_move(w, CONFIG, MoveCmd(unit=u, path=[(90000, 0)],
                                      mode=MoveMode.ATTACK))
        for _ in range(10):
            world_tick(w)
        self.assertEqual(u.pos, (0, 0))                        # 停住不动
        self.assertEqual(len(u.move_path), 1)                  # 预算暂停（令仍在）
        self.assertTrue(u.moving())                            # MV-B-23：仍按移动中计
        self.assertEqual(u.move_mode, MoveMode.ATTACK)         # 模式不复位
        foe.alive = False
        world_tick(w)
        self.assertEqual(u.pos[0], 70)                         # 敌消失自动恢复
        self.assertEqual(u.move_mode, MoveMode.ATTACK)         # 令仍在执行


# ── §2.8 队形三表（make_formation_fn 直调；FormationCmd 写点未落地——槽直写）──

class TestFormationFn(unittest.TestCase):
    def _unit(self, n):
        w = make_world(61)
        et = ElementTemplate(element_type=ElementType.VEHICLE,
                             unit_type=UnitType.MECH, hp_max=10)
        tpl = UnitTemplate(template_id=910, name="plt", category=2, cost=100,
                           element_templates=(et,) * n, optics_ground_cm=20000,
                           stealth_base=3, speed_tier=5,
                           movement_class=MovementClass.WHEEL)
        u = mk_unit(w, tpl, pos=(0, 0))
        u.move_path = [(0, 7000)]      # 行进向 k=0（北）→ DIR8[0]=(0,7)、PERP8[0]=(-7,0)
        return w, u

    def test_none_returns_none(self):
        # MV-B-19：NONE 默认=None——现状同点堆叠（零行为变化）
        w, u = self._unit(3)
        self.assertIsNone(make_formation_fn(w, CONFIG, u))

    def test_line_lateral_offsets(self):
        # n=3 → lat=−1,0,+1（round_div 半舍入位级确定；n=4 → −1,0,1,2）；
        # 北向行进 PERP8[0]=(-7,0) → 负 lat 在东（x=+）
        w, u = self._unit(3)
        u.formation_shape = FormationShape.LINE
        fn = make_formation_fn(w, CONFIG, u)
        self.assertEqual(fn((0, 0), 1), (1500, 0))            # r0：lat=−1500 → 东
        self.assertEqual(fn((0, 0), 2), (0, 0))               # r1：中轴
        self.assertEqual(fn((0, 0), 3), (-1500, 0))           # r2：lat=+1500 → 西

    def test_column_serial_offsets(self):
        # 纵队：沿行进反方向串列（首车在前）——北向行进 → 纵深沿 −y
        w, u = self._unit(3)
        u.formation_shape = FormationShape.COLUMN
        fn = make_formation_fn(w, CONFIG, u)
        self.assertEqual(fn((0, 0), 1), (0, 0))
        self.assertEqual(fn((0, 0), 2), (0, -1000))
        self.assertEqual(fn((0, 0), 3), (0, -2000))

    def test_wedge_anchor_five_elements(self):
        # §2.8 楔形锚点（n=5，line_s=1500、col_s=1000，行进向 k）：
        # r0=(0,0)；r1=后1000+左750；r2=后1000+右750；r3=后2000+左750；r4=后2000+右750
        w, u = self._unit(5)
        u.formation_shape = FormationShape.WEDGE
        fn = make_formation_fn(w, CONFIG, u)
        self.assertEqual(fn((0, 0), 1), (0, 0))
        self.assertEqual(fn((0, 0), 2), (-750, -1000))
        self.assertEqual(fn((0, 0), 3), (750, -1000))
        self.assertEqual(fn((0, 0), 4), (-750, -2000))
        self.assertEqual(fn((0, 0), 5), (750, -2000))

    def test_formation_applied_via_system_move(self):
        # dispatch→make_formation_fn 接线：LINE 队形三元素沿行进垂线展开
        # （formation_offset_fn 消费签名冻结 movement.system_move :91）
        w, u = self._unit(3)
        u.formation_shape = FormationShape.LINE
        from sovs.sim.movement import system_move as raw_move
        raw_move(CONFIG, u, 0,
                 formation_offset_fn=make_formation_fn(w, CONFIG, u))
        self.assertEqual(u.pos, (0, 70))
        self.assertEqual(u.elements[0].pos, (1500, 70))       # lat=−1 → 东
        self.assertEqual(u.elements[1].pos, (0, 70))          # 中轴
        self.assertEqual(u.elements[2].pos, (-1500, 70))      # lat=+1 → 西


# ── PB-56 批③ Formation 族块（2026-10-06）：FormationCmd 写槽/分派链 +
#    issue_group_move（§2.9）+ move_speed_cm_tick §2.3 增量① 档位钳制消费者 ──

class TestFormationCmd(unittest.TestCase):
    def _plt(self, n=3, tier=5):
        w = make_world(63)
        et = ElementTemplate(element_type=ElementType.VEHICLE,
                             unit_type=UnitType.MECH, hp_max=10)
        tpl = UnitTemplate(template_id=912, name="fmt plt", category=2, cost=100,
                           element_templates=(et,) * n, optics_ground_cm=20000,
                           stealth_base=3, speed_tier=tier,
                           movement_class=MovementClass.WHEEL)
        return w, add_unit(w, make_unit(w, tpl, 0, 0, (0, 0)))

    def test_dispatch_writes_slot_per_unit(self):
        # §2.2 :151-152：组下令=逐单位写槽、无 REJECT 门——世界级收件箱→分派支
        # 真调用（cmd_formation）；两单位一字段承载（FormationCmd{units, shape}）
        w, u1 = self._plt()
        u2 = mk_unit(w, wheel_tpl(2, template_id=913), pos=(5000, 0))
        rng0 = [r.state for r in w.rng._rngs]
        queue_command(w, FormationCmd(units=[u1, u2], shape=FormationShape.WEDGE))
        world_tick(w)
        self.assertEqual(u1.formation_shape, FormationShape.WEDGE)
        self.assertEqual(u2.formation_shape, FormationShape.WEDGE)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)   # 零掷骰
        queue_command(w, FormationCmd(units=[u1], shape=FormationShape.NONE))
        world_tick(w)
        self.assertEqual(u1.formation_shape, FormationShape.NONE)  # 显式复位
        self.assertEqual(u2.formation_shape, FormationShape.WEDGE)  # 未下达不动

    def test_shape_reset_to_none_restores_stacking(self):
        # NONE 复位=现状同点堆叠（MV-B-19）：make_formation_fn 返 None——
        # 与未下令位级同效
        w, u = self._plt()
        u.formation_shape = FormationShape.WEDGE
        self.assertIsNotNone(make_formation_fn(w, CONFIG, u))
        cmd_formation_via_queue = FormationCmd(units=[u], shape=FormationShape.NONE)
        queue_command(w, cmd_formation_via_queue)
        world_tick(w)
        self.assertIsNone(make_formation_fn(w, CONFIG, u))

    def test_formation_command_stream_end_to_end(self):
        # 命令流全链：FormationCmd(WEDGE)+MoveCmd（北向）→ 逐拍 dispatch 消费
        # formation_shape 重建闭包——四元素楔形偏移位级=§2.8 楔形锚（k=0 北向）
        w, u = self._plt(n=4)
        queue_command(w, FormationCmd(units=[u], shape=FormationShape.WEDGE))
        queue_command(w, MoveCmd(unit=u, path=[(0, 7000)]))
        world_tick(w)
        self.assertEqual(u.pos, (0, 70))
        base = u.pos
        self.assertEqual(u.elements[0].pos, base)                    # r0 楔尖 (0,0)
        self.assertEqual(u.elements[1].pos, (base[0] - 750, base[1] - 1000))  # r1 左后
        self.assertEqual(u.elements[2].pos, (base[0] + 750, base[1] - 1000))  # r2 右后
        self.assertEqual(u.elements[3].pos, (base[0] - 750, base[1] - 2000))  # r3 左深
        # 槽跨令持续：到达后（move_path 耗尽）形状保持、k 按末段朝向取位
        for _ in range(99):
            world_tick(w)
        self.assertEqual(u.formation_shape, FormationShape.WEDGE)
        self.assertFalse(u.move_path)
        self.assertEqual(u.elements[1].pos,
                         (u.pos[0] - 750, u.pos[1] - 1000))


class TestIssueGroupMove(unittest.TestCase):
    def test_cap_min_written_after_external_order(self):
        # §2.9 字面次序：逐单位 issue_move（外部通道四件一体含清 cap）**后**写
        # cap=MIN(speed_tier)——组令随后写 cap 不被自己的清 0 吃掉；len>1 才写
        w = make_world(64)
        fast = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        slow = mk_unit(w, wheel_tpl(2, template_id=914), pos=(0, 0))
        fast.group_speed_cap = 4      # 旧编组残值——issue_move 先清后组令覆写
        issue_group_move(w, CONFIG, [fast, slow], [(7000, 0)],
                         mode=MoveMode.MARCH)
        self.assertEqual(fast.group_speed_cap, 2)              # cap=MIN(5,2)
        self.assertEqual(slow.group_speed_cap, 2)
        self.assertEqual(fast.move_mode, MoveMode.MARCH)       # mode 逐单位生效
        self.assertEqual(slow.move_path, [(7000, 0)])

    def test_single_unit_group_writes_no_cap(self):
        # §2.9 IF len(units)>1：单单位组令不写 cap（issue_move 清 0 后不再覆写）
        w = make_world(65)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        u.group_speed_cap = 3
        issue_group_move(w, CONFIG, [u], [(7000, 0)])
        self.assertEqual(u.group_speed_cap, 0)
        self.assertEqual(u.move_path, [(7000, 0)])

    def test_gate_rejected_unit_still_gets_cap_literal(self):
        # §2.9 字面（可推翻留痕）：cap 写入不设 issue_move 结果条件——组内
        # PACKING 单位被门1 拒令（无航点）仍带 cap 离场；其后续独立新令/组令
        # 均会重写 cap，无死锁面〔2026-10-07 命令族收口块重锚：原用 DEPLOYING
        # 作门拒载体——pack_or_move 移动触发面接线（发起人拍板采 IMPL 字面）后
        # DEPLOYING×外部移动令=作废放行不再是拒令态，改 PACKING（仍拒）承载〕
        w = make_world(66)
        packing = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        packing.deploy_state = DeployState.PACKING
        packing.deploy_timer = 50
        slow = mk_unit(w, wheel_tpl(2, template_id=915), pos=(0, 0))
        issue_group_move(w, CONFIG, [packing, slow], [(7000, 0)])
        self.assertEqual(packing.move_path, [])                # 门1 拒令
        self.assertEqual(packing.group_speed_cap, 2)           # 字面仍写
        self.assertEqual(slow.move_path, [(7000, 0)])

    def test_group_move_zero_dice(self):
        w = make_world(67)
        a = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        b = mk_unit(w, wheel_tpl(1, template_id=916), pos=(0, 0))
        rng0 = [r.state for r in w.rng._rngs]
        issue_group_move(w, CONFIG, [a, b], [(7000, 0)])
        issue_move(w, CONFIG, MoveCmd(unit=a, path=[(14000, 0)], queue=True))
        for _ in range(5):
            world_tick(w)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)  # 全链零掷骰


class TestGroupSpeedCapConsumer(unittest.TestCase):
    """§2.3 增量①（movement.move_speed_cm_tick 档位钳制——2026-10-06 接线；
    速度链块余量增量②③/MOB 拆除不随本块）。锚点算术：档位基值
    (0,25,45,70,100,140)×WHEEL 类缺省 bp 5000//10000=半值：
    tier5→70 / tier3→35 / tier2→22 / tier1→12。"""

    def _u(self, tier=5):
        w = make_world(68)
        return mk_unit(w, wheel_tpl(tier), pos=(0, 0))

    def test_cap_clamps_tier(self):
        u = self._u(5)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 70)   # 无 cap
        u.group_speed_cap = 3
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 35)   # 钳 tier3
        u.group_speed_cap = 2
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 22)   # 钳 tier2

    def test_cap_above_own_tier_is_noop(self):
        # MIN 语义：cap 高于自身档不加速（钳制单向）
        u = self._u(2)
        u.group_speed_cap = 5
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 22)

    def test_sprint_breaks_cap_after_clamp(self):
        # §2.9 口径/契约⑧：疾跑升档在钳制**后**——个体冲刺允许破格但不越
        # cap+1 档（tier5+cap2+疾跑 → min(5, 2+1)=3 → 35；非 70）
        u = self._u(5)
        u.group_speed_cap = 2
        cmd_sprint(make_world(69), u, CONFIG)
        self.assertEqual(u.sprint_until, CONFIG.sprint_duration_ticks)
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 1), 35)
        self.assertEqual(move_speed_cm_tick(CONFIG, u,
                                            CONFIG.sprint_duration_ticks + 1), 22)

    def test_tow_hard_override_beats_cap(self):
        # §2.9 口径：拖曳锁档硬覆盖钳制（tow_speed_tier=1 已是最低）——
        # 拖曳态速度与 cap 无关（movement 冻结行不动）
        w = make_world(70)
        tower = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        towed_u = mk_unit(w, wheel_tpl(5, template_id=917), pos=(0, 0))
        tower.elements[0].towed = TowState.TOWING
        towed_u.elements[0].towed = TowState.TOWED
        tower.group_speed_cap = 4
        self.assertEqual(move_speed_cm_tick(CONFIG, tower, 0), 12)   # tier1×0.5
        towed_u.group_speed_cap = 0
        self.assertEqual(move_speed_cm_tick(CONFIG, towed_u, 0), 12)


class TestSimImportHygiene(unittest.TestCase):
    """sovs/sim 模块导入面守卫（PB-56 批③ Formation 族块评审退回修复
    2026-10-06 补锚）：movement.py 导入面=历史基线（air/geom/tables/types +
    既有注记的 __future__），不得出现对 tick 的反向导入边（tick 本体 import
    movement——反向边即循环依赖，曾以 issue_group_move 函数体延迟
    `from .tick import MoveCmd` 形式混入被评审指认，移位 tick.py 后本锚防回归）。
    双查：①子进程净导入 sovs.sim.movement 断言 sovs.sim.tick 不入 sys.modules
    （函数体延迟导入不在 import 期显形——源码扫描补面）；②源码零反向 import
    语句（from .tick/sovs.sim.tick import 或 import sovs.sim.tick——正则只咬
    import 形态，world.tick 等属性读不误伤）。"""

    def test_movement_module_has_no_tick_import_edge(self):
        import subprocess
        import sys
        code = ("import sys; import sovs.sim.movement; "
                "print('sovs.sim.tick' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "False")
        import re
        import sovs.sim.movement as mv
        src = open(mv.__file__, encoding="utf-8").read()
        # 源码级零反向 import 语句（含函数体延迟导入——`world.tick` 等属性读不含
        # import 关键字，正则只咬 import 形态不误伤）
        self.assertIsNone(re.search(r"^\s*(from\s+(\.tick|sovs\.sim\.tick)\s+import"
                                    r"|import\s+sovs\.sim\.tick)",
                                    src, re.MULTILINE))


class TestFormationInputDiscipline(unittest.TestCase):
    """2026-10-06 批③评审#4：cmd_formation 输入纪律归一（SetMode 先例同款）。"""

    def test_bare_int_normalized_and_invalid_skipped(self):
        # 裸 int 在枚举域内 → 归一写入（is 判据可达，消费端 else=WEDGE 不再静默兜底）；
        # 非成员值 → 跳过不写不抛（无门字面 × 输入纪律折中——docstring 留痕）
        from sovs.sim.tick import cmd_formation
        w = make_world(7)
        u1 = mk_unit(w, wheel_tpl())
        u2 = mk_unit(w, wheel_tpl(), pos=(1000, 0))
        cmd_formation([u1], int(FormationShape.LINE))
        self.assertIs(u1.formation_shape, FormationShape.LINE)
        cmd_formation([u2], 99)
        self.assertIs(u2.formation_shape, FormationShape.NONE)   # 缺省不动


# ── 速度链块（2026-10-06）：§2.3 增量②④ dispatch 集成 + §2.11 超射程进位 ──

class TestReverseDispatch(unittest.TestCase):
    """§2.3 增量② REVERSE 乘区 + §2.4 增量④ facing 锁定的 dispatch/world_tick
    集成（move_speed 单元锚在 tests/test_movement.py）。锚点算术：档 5 轮式
    v=140×5000//10000=70 → 倒车 70×2500//10000=17。"""

    def test_reverse_move_slower_facing_kept_mode_resets(self):
        # 命令流全链：MoveCmd(mode=REVERSE)（门4 轮式资格过）→ 逐拍 dispatch——
        # v=17/拍、facing 全程锁定初始 90°（东）而位移向西、到位后模式复位
        # NORMAL（§2.4 末行——REVERSE 生命周期=当前移动令）
        w = make_world(71)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        u.elements[0].facing = 90
        queue_command(w, MoveCmd(unit=u, path=[(-170, 0)],
                                 mode=MoveMode.REVERSE))
        for _ in range(9):
            world_tick(w)
            self.assertEqual(u.elements[0].facing, 90)   # 逐拍锁定（增量④）
            self.assertEqual(u.pos[0], -17 * w.tick)     # 17/拍（增量②）
            self.assertIs(u.move_mode, MoveMode.REVERSE)
        world_tick(w)                                     # 第 10 拍到位（10×17=170）
        self.assertEqual(u.pos, (-170, 0))
        self.assertEqual(u.move_path, [])
        self.assertIs(u.move_mode, MoveMode.NORMAL)      # 到达复位

    def test_reverse_cmd_dispatch_full_chain(self):
        # §2.2 :142 归一化（2026-10-07 命令族收口块）：ReverseCmd{unit,dest} ≡
        # MoveCmd{path=[dest], mode=REVERSE, queue=FALSE}——命令流全链同主锚
        # （17/拍+facing 锁定+到位复位）；归一化在 issue_move 门3 后门4 前
        w = make_world(78)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        u.elements[0].facing = 90
        rng0 = [r.state for r in w.rng._rngs]
        queue_command(w, ReverseCmd(unit=u, dest=(-170, 0)))
        for _ in range(9):
            world_tick(w)
            self.assertEqual(u.elements[0].facing, 90)   # 逐拍锁定（增量④）
            self.assertEqual(u.pos[0], -17 * w.tick)     # 17/拍（增量②）
            self.assertIs(u.move_mode, MoveMode.REVERSE)
        world_tick(w)                                     # 第 10 拍到位（10×17=170）
        self.assertEqual(u.pos, (-170, 0))
        self.assertIs(u.move_mode, MoveMode.NORMAL)      # 到达复位
        self.assertEqual([r.state for r in w.rng._rngs], rng0)  # 全链零掷骰

    def test_reverse_cmd_foot_rejected_gate4(self):
        # 门4 经归一化生效：FOOT reverse_bp=0 → 拒令（原生 ReverseCmd 无 mode
        # 字段——归一化先行门4 才有 mode 可读）
        w = make_world(79)
        foot = mk_unit(w, foot_tpl(), pos=(0, 0))
        queue_command(w, ReverseCmd(unit=foot, dest=(-100, 0)))
        world_tick(w)
        self.assertEqual(foot.move_path, [])
        self.assertIs(foot.move_mode, MoveMode.NORMAL)

    def test_reverse_cmd_halt_clears_and_never_queues(self):
        # 归一化 queue=FALSE ⇒ ReverseCmd 常规不入单位级队列；cmd_halt 过滤
        # 并入 MoveCmd|ReverseCmd（v1.3 :159 字面防御位）——手挂 ReverseCmd
        # 亦被 halt 移出（与 MoveCmd 同族）
        w = make_world(80)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        self.assertTrue(issue_move(w, CONFIG, ReverseCmd(unit=u,
                                                         dest=(-170, 0))))
        self.assertEqual(u.command_queue, [])             # queue=FALSE 不入队
        cmd_halt(u)
        self.assertEqual(u.move_path, [])
        u.command_queue = [ReverseCmd(unit=u, dest=(-170, 0)),   # 手挂防御位
                           SprintCmd(unit=u)]
        cmd_halt(u)
        self.assertEqual([type(c).__name__ for c in u.command_queue],
                         ["SprintCmd"])                   # ReverseCmd 被过滤


class TestAutoApproach(unittest.TestCase):
    """§2.11 超射程自动进位纯函数锚（2026-10-06 速度链块；消费锚=cmd_fire_mission
    在 tests/test_ground_combat.py TestAutoApproachConsumption）。stand=
    MAX(max_range−cfg.auto_approach_standoff_cm, max_range//2)（AMB-4 半射程
    下界）；k=octant_deg(目标−pos)//45；航点=目标−scale(DIR8[k], stand)。"""

    def test_in_range_returns_none(self):
        # 射程内：不插航点（行为不变分支）
        w = make_world(72)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        self.assertIsNone(auto_approach_waypoint(u, (50000, 0), 60000, CONFIG))
        self.assertIsNone(auto_approach_waypoint(u, (60000, 0), 60000, CONFIG))  # 等号=射程内

    def test_standoff_and_dir8_direction(self):
        # 超射程：max_range=100000、目标 (0,120000) → d=120000；stand=
        # MAX(100000−2000, 50000)=98000；正北 k=0 → DIR8[0]=(0,7) → scale=
        # (0,98000) → 航点=(0,120000−98000)=(0,22000)——目标内侧、同方位线上
        w = make_world(73)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        wp = auto_approach_waypoint(u, (0, 120000), 100000, CONFIG)
        self.assertEqual(wp, (0, 22000))

    def test_short_range_half_floor(self):
        # AMB-4：max_range=1500 < standoff 常数 2000 → 负 stand 由半射程下界兜底：
        # stand=MAX(−500, 750)=750 → 航点=(0,10000−750)=(0,9250)——不反向越过目标
        w = make_world(74)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        wp = auto_approach_waypoint(u, (0, 10000), 1500, CONFIG)
        self.assertEqual(wp, (0, 9250))

    def test_diagonal_dir8(self):
        # 斜向：max_range=100000、目标 (100000,100000) → d=141421 超射程；东北
        # k=1 → DIR8[1]=(5,5)→scale(98000)=(70000,70000) → 航点=(30000,30000)
        # ——DIR8 各向异性 ≈1.015% 由 50% 比例余量覆盖（AMB-4 成文）
        w = make_world(75)
        u = mk_unit(w, wheel_tpl(5), pos=(0, 0))
        wp = auto_approach_waypoint(u, (100000, 100000), 100000, CONFIG)
        self.assertEqual(wp, (30000, 30000))

    def test_nearest_on_segment(self):
        # LINE/CREEP 判距基准（§2.11 定标延伸）：投影内点/两端夹持/零长退化
        self.assertEqual(nearest_on_segment((0, 0), (0, 10), (0, 20)), (0, 10))
        self.assertEqual(nearest_on_segment((50, 0), (0, 10), (0, 20)), (0, 10))
        self.assertEqual(nearest_on_segment((-5, 7), (0, 10), (0, 20)), (0, 10))
        self.assertEqual(nearest_on_segment((10, 15), (0, 10), (10, 20)), (7, 17))
        self.assertEqual(nearest_on_segment((3, 3), (7, 7), (7, 7)), (7, 7))


if __name__ == "__main__":
    unittest.main()
