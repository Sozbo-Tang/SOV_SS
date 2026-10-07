"""§F6 拖曳/展开命令块（PB-56 批② 机动链命令块·拖曳展开，2026-10-06）：
cmd_tow/cmd_untow（:1228-1245）+ cmd_deploy/cmd_pack_or_move（:1072-1118）
+ start_tow（§F2 :494-516，combat.py——TowPair 建立唯一入口）。

锚点全部手推写死（拖曳吨位贪心降序稳定排序并列取原序、TOWING/TOWED 双态写点、
C3 redeploy_needed 保留语义、C5 拖曳不触碰 deploy_state、GAP-09 留守门 ELIF 过滤、
M18/A20 计时器分支内写入不重置、DEPLOYING/PACKING 计时 300 拍迁移、拖曳锁速
tow_speed_tier=1〔WHEEL 70×5000//10000=35 → 25×5000//10000=12〕、GAP-14 随动
偏移 tow_follow_offset_cm=300、门1 展开/收起互锁），不自证；真卡链
（SU_TRUCK 15t 拖 SU_ZIS3 13t / GER_PAK40 15t 恰满足——data/gen/cards_ground.v1.json
实测值）；确定性双跑照 tests/test_integration.py fingerprint 范式（同 seed 两
world 逐 tick 比指纹），全程零掷骰（同队无对抗场景八通道 PCG32 state 不动）。"""
import unittest
from pathlib import Path

from sovs.sim import card_loader as cl
from sovs.sim.movement import move_speed_cm_tick
from sovs.sim.tables import CONFIG
from sovs.sim.tick import (DeployCmd, MoveCmd, PackCmd, SetModeCmd, TowCmd,
                           UntowCmd, add_unit, cmd_deploy, cmd_pack_or_move,
                           cmd_tow, cmd_untow, fire_permitted, make_unit,
                           make_world, queue_command, start_tow, world_tick)
from sovs.sim.types import (DeployState, ElementTemplate, ElementType,
                            FireMission, FireMissionForm, Mode, MovementClass,
                            TowState, UnitTemplate, UnitType, WeaponTemplate)

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_LIBRARY = REPO_ROOT / "data" / "gen" / "cards_ground.v1.json"

# ── 合成模板（测试用，不对应真实卡；test_supply_mount 同款）──
GUN_ELEM = ElementTemplate(element_type=ElementType.GUN,
                           unit_type=UnitType.MECH, hp_max=12)
VEH_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                           unit_type=UnitType.MECH, hp_max=10)
SQUAD_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                             unit_type=UnitType.INFANTRY, hp_max=10)

GUN_TPL = UnitTemplate(                    # 牵引炮（own 13 / 展开·收装 300）
    template_id=401, name="at gun", category=3, cost=60,
    element_templates=(GUN_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=1, movement_class=MovementClass.FOOT,
    deploy_time_ticks=300, pack_time_ticks=300, own_weight_tons=13)
BAT_TPL = UnitTemplate(                    # 4 门炮连（GAP-09 留守门载体）
    template_id=402, name="gun bty", category=3, cost=200,
    element_templates=(GUN_ELEM,) * 4,
    optics_ground_cm=20000, stealth_base=3, speed_tier=1,
    movement_class=MovementClass.FOOT,
    deploy_time_ticks=300, pack_time_ticks=300, own_weight_tons=13)
TRA_TPL = UnitTemplate(                    # 三模式牵引车（吨位 15——SU_TRUCK 同构）
    template_id=403, name="tractor", category=4, cost=30,
    element_templates=(VEH_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=3, movement_class=MovementClass.WHEEL,
    mode_set=((1 << Mode.DIRECT) | (1 << Mode.TOW) | (1 << Mode.CARGO)
              | (1 << Mode.TRANSPORT)),
    tow_tonnage=15)
TR30_TPL = UnitTemplate(                   # 30t 牵引车（DIRECT|TOW 最小位集）
    template_id=404, name="30t tractor", category=4, cost=40,
    element_templates=(VEH_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=2, movement_class=MovementClass.WHEEL,
    mode_set=((1 << Mode.DIRECT) | (1 << Mode.TOW)), tow_tonnage=30)
TR10_TPL = UnitTemplate(                   # 10t 牵引车（吨位不足载体）
    template_id=405, name="10t tractor", category=4, cost=25,
    element_templates=(VEH_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=2, movement_class=MovementClass.WHEEL,
    mode_set=((1 << Mode.DIRECT) | (1 << Mode.TOW)), tow_tonnage=10)
NT_TPL = UnitTemplate(                     # 无 TOW 位车（③ 第三门载体——吨位
    template_id=406, name="soft truck",    # 再大也无牵引资格，§D.1#15）
    category=4, cost=20,
    element_templates=(VEH_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=3, movement_class=MovementClass.WHEEL, tow_tonnage=99)
INF_TPL = UnitTemplate(                    # 步兵班（② 门排除载体）
    template_id=407, name="line inf", category=1, cost=20,
    element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)
MECH_TOW_TPL = UnitTemplate(               # MECH×TOW 位被拖（卡车拖卡车退化合法：
    template_id=408, name="towable mech",  # own_weight 0 → 吨位门恒满足——字面登记）
    category=4, cost=30,
    element_templates=(VEH_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=3, movement_class=MovementClass.WHEEL,
    mode_set=((1 << Mode.DIRECT) | (1 << Mode.TOW)), tow_tonnage=15)
DEPLOY_W = WeaponTemplate(                 # needs_deployed 武器（③ 门/fire 恢复链）
    name="AT GUN", max_range_cm=30000, damage=5, ammo_base=10,
    aim_time_ticks=5, reload_time_ticks=10, needs_deployed=True)
DEPLOY_GUN_ELEM = ElementTemplate(element_type=ElementType.GUN,
                                  unit_type=UnitType.MECH, hp_max=12,
                                  weapons=(DEPLOY_W,))
DEPLOY_GUN_TPL = UnitTemplate(             # 须展开才可开火的炮（整链载体）
    template_id=409, name="deploy gun", category=3, cost=60,
    element_templates=(DEPLOY_GUN_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=1, movement_class=MovementClass.FOOT,
    deploy_time_ticks=300, pack_time_ticks=300, own_weight_tons=13)
TR45_TPL = UnitTemplate(                   # 45t 重牵引（降序贪心首取载体）
    template_id=410, name="45t tractor", category=4, cost=50,
    element_templates=(VEH_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=2, movement_class=MovementClass.WHEEL,
    mode_set=((1 << Mode.DIRECT) | (1 << Mode.TOW)), tow_tonnage=45)
HEAVY15_TPL = UnitTemplate(                # 15t 炮（吨位恰满足边界载体）
    template_id=411, name="15t gun", category=3, cost=60,
    element_templates=(GUN_ELEM,), optics_ground_cm=20000, stealth_base=3,
    speed_tier=1, movement_class=MovementClass.FOOT, own_weight_tons=15)
DEPLOY_BTY_TPL = UnitTemplate(             # 4 门须展开炮连（GAP-09 留守门整锚）
    template_id=412, name="deploy bty", category=3, cost=240,
    element_templates=(DEPLOY_GUN_ELEM,) * 4,
    optics_ground_cm=20000, stealth_base=3, speed_tier=1,
    movement_class=MovementClass.FOOT,
    deploy_time_ticks=300, pack_time_ticks=300, own_weight_tons=13)


def tractor(w, team=0, pos=(0, 0), tpl=TRA_TPL, tow_mode=True):
    """牵引车工厂：tow_mode=True 直写 e.mode=TOW（SetModeCmd 命令链在分派支
    测试另走；D065 互斥门要求牵引前处 TOW 态）。"""
    u = add_unit(w, make_unit(w, tpl, team, team, pos))
    if tow_mode:
        u.elements[0].mode = Mode.TOW
    return u


def gun(w, team=0, pos=(0, 0), tpl=GUN_TPL):
    return add_unit(w, make_unit(w, tpl, team, team, pos))


def fingerprint(w):
    """本块状态面指纹：tick/相位 + 八通道 PCG32 state + 单位（pos/展开态/计时/
    任务）+ 元素（pos/mode/towed/redeploy）+ tow_pairs（照 test_supply_mount
    fingerprint 范式扩 deploy 面）。"""
    parts = ["t%d:p%d:r%s" % (w.tick, w.phase,
                              ",".join(str(r.state) for r in w.rng._rngs))]
    for u in w.units:
        parts.append("U%d,%d,%s,%d,%d,%d,%d,%d,%s" % (
            u.id, u.team, u.pos, int(u.alive), int(u.deploy_state),
            u.deploy_timer, len(u.move_path), u.spotted_mask, u.fire_mission))
        for e in u.elements:
            parts.append("E%d,%s,%d,%d,%d,%d" % (
                e.id, e.pos, int(e.mode), int(e.towed),
                int(e.redeploy_needed), e.hp_current))
    parts.append("TP%d" % len(w.tow_pairs))
    parts.append("Q%d" % len(w.command_queue))
    return "|".join(parts)


# ── §F2 :494-516 start_tow（函数体级——cmd_tow 之外的未来脚本/AI 路径兜底）──


class TestStartTow(unittest.TestCase):
    def test_pair_built_and_four_write_points(self):
        # :506-515 四写点：TowPair 入表 / 牵引 TOWING（C1）/ 被拖 TOWED /
        # redeploy_needed=TRUE（C3）；deploy_state 不触碰（C5——:513 v1.4 单位级
        # 重置行为已删除）
        w = make_world(3)
        t, g = tractor(w), gun(w)
        self.assertTrue(start_tow(w, [t.elements[0]], g.elements[0]))
        self.assertEqual(len(w.tow_pairs), 1)
        self.assertIs(w.tow_pairs[0].tower_elements[0], t.elements[0])
        self.assertIs(w.tow_pairs[0].towed_element, g.elements[0])
        self.assertIs(t.elements[0].towed, TowState.TOWING)
        self.assertIs(g.elements[0].towed, TowState.TOWED)
        self.assertTrue(g.elements[0].redeploy_needed)
        self.assertIs(g.deploy_state, DeployState.MOBILE)      # C5 不触碰
        self.assertEqual(g.deploy_timer, 0)

    def test_empty_towers_or_towed_already_busy(self):
        # :495 空列表 FALSE；被拖元素 towed≠NONE（C1 双态）FALSE
        w = make_world(3)
        t, g = tractor(w), gun(w)
        self.assertFalse(start_tow(w, [], g.elements[0]))
        g.elements[0].towed = TowState.TOWED
        self.assertFalse(start_tow(w, [t.elements[0]], g.elements[0]))
        self.assertEqual(w.tow_pairs, [])

    def test_function_level_team_gate(self):
        # :497 GAP-10 函数级同队硬门（cmd_tow 命令门之外的兜底）
        w = make_world(3)
        t = tractor(w, team=0)
        g = gun(w, team=1)
        self.assertFalse(start_tow(w, [t.elements[0]], g.elements[0]))

    def test_tonnage_greedy_descending_pick(self):
        # :500-505 降序贪心：命令序 [10t, 45t, 30t] 拖 GUN_TPL（own=13t，批②
        # 评审#4 勘正：原注「40t」与载体不符）→ 稳定降序取 45t
        # 单车即止（30/10t 不入对不置态）
        w = make_world(3)
        t10 = tractor(w, tpl=TR10_TPL)
        t45 = tractor(w, tpl=TR45_TPL)
        t30 = tractor(w, tpl=TR30_TPL)
        g = gun(w)
        self.assertTrue(start_tow(w, [t10.elements[0], t45.elements[0],
                                      t30.elements[0]], g.elements[0]))
        towers = w.tow_pairs[0].tower_elements
        self.assertEqual(len(towers), 1)
        self.assertIs(towers[0], t45.elements[0])
        self.assertIs(t30.elements[0].towed, TowState.NONE)
        self.assertIs(t10.elements[0].towed, TowState.NONE)

    def test_tonnage_tie_original_order_and_accumulate(self):
        # 稳定排序并列取原序：两台 30t（列表序 a,b）并拖 60t 炮 → 双双入对且
        # 保序（重坦 45t=2×30t 并拖可表达）；61t 差 1t 即不足 FALSE
        heavy60 = UnitTemplate(template_id=413, name="60t gun", category=3,
                               cost=100, element_templates=(GUN_ELEM,),
                               optics_ground_cm=20000, stealth_base=3,
                               speed_tier=1, movement_class=MovementClass.FOOT,
                               own_weight_tons=60)
        heavy61 = UnitTemplate(template_id=414, name="61t gun", category=3,
                               cost=100, element_templates=(GUN_ELEM,),
                               optics_ground_cm=20000, stealth_base=3,
                               speed_tier=1, movement_class=MovementClass.FOOT,
                               own_weight_tons=61)
        w = make_world(5)
        a = tractor(w, pos=(100, 0), tpl=TR30_TPL)
        b = tractor(w, pos=(200, 0), tpl=TR30_TPL)
        g60 = gun(w, pos=(300, 0), tpl=heavy60)
        self.assertTrue(start_tow(w, [a.elements[0], b.elements[0]],
                                  g60.elements[0]))          # 30+30 ≥ 60
        towers = w.tow_pairs[0].tower_elements
        self.assertEqual(len(towers), 2)
        self.assertIs(towers[0], a.elements[0])               # 并列取原序
        self.assertIs(towers[1], b.elements[0])
        self.assertEqual((a.elements[0].towed, b.elements[0].towed),
                         (TowState.TOWING, TowState.TOWING))
        w2 = make_world(5)
        a2 = tractor(w2, pos=(100, 0), tpl=TR30_TPL)
        b2 = tractor(w2, pos=(200, 0), tpl=TR30_TPL)
        g61 = gun(w2, pos=(300, 0), tpl=heavy61)
        self.assertFalse(start_tow(w2, [a2.elements[0], b2.elements[0]],
                                   g61.elements[0]))          # 60 < 61 不足
        self.assertEqual(w2.tow_pairs, [])

    def test_tonnage_insufficient_silent_false(self):
        # :505 不足 FALSE：10t 车（TR10）对 13t 炮——零写点（表空/态 NONE/旗 False）
        w = make_world(6)
        t = tractor(w, tpl=TR10_TPL)
        g = gun(w)                                            # own 13 > 10
        self.assertFalse(start_tow(w, [t.elements[0]], g.elements[0]))
        self.assertFalse(cmd_tow(w, [t.elements[0]], g.elements[0]))
        self.assertEqual(w.tow_pairs, [])
        self.assertIs(g.elements[0].towed, TowState.NONE)
        self.assertFalse(g.elements[0].redeploy_needed)

    def test_exact_tonnage_boundary_accepted(self):
        # 恰满足档：15t 车 × 15t 炮（≥ 含等号；真卡 GER_PAK40 同值链见 TestRealCards）
        w = make_world(7)
        t = tractor(w)                                        # 15t
        g = gun(w, tpl=HEAVY15_TPL)
        self.assertTrue(start_tow(w, [t.elements[0]], g.elements[0]))

    def test_fire_mission_cleared_unit_level(self):
        # :515 方案10：清 towed.unit.fire_mission（单位级整清——与 SetModeCmd ⑦
        # M21 半清除粒度不同构，照字面）
        w = make_world(8)
        t, g = tractor(w), gun(w)
        g.fire_mission = FireMission(form=FireMissionForm.POINT,
                                     target_point=(1, 2), shots_left=5)
        self.assertTrue(start_tow(w, [t.elements[0]], g.elements[0]))
        self.assertIsNone(g.fire_mission)


# ── §F6 :1228-1241 cmd_tow（命令门序①-③ + start_tow 静默失败）──


class TestCmdTow(unittest.TestCase):
    def test_gate1_team_mixed_rejects(self):
        w = make_world(3)
        t0 = tractor(w, team=0, tpl=TR30_TPL)
        t1 = tractor(w, team=1, tpl=TR10_TPL)
        g = gun(w, team=0)
        self.assertFalse(cmd_tow(w, [t0.elements[0], t1.elements[0]],
                                 g.elements[0]))
        self.assertEqual(w.tow_pairs, [])

    def test_gate2_squad_rejected(self):
        # SQUAD 班不可被拖（GAP-10——非 GUN 非 MECH×TOW）
        w = make_world(3)
        t = tractor(w, tpl=TR30_TPL)
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        self.assertFalse(cmd_tow(w, [t.elements[0]], inf.elements[0]))

    def test_gate2_mech_with_tow_bit_accepted_degenerate(self):
        # MECH×TOW 位被拖=卡车拖卡车（own 0 吨位恒满足）——伪代码字面退化合法，
        # 登记（补「自重>0 才可被拖」或数据侧补卡车自重随数值章节）
        w = make_world(3)
        t = tractor(w, tpl=TR30_TPL)
        m = add_unit(w, make_unit(w, MECH_TOW_TPL, 0, 0, (0, 0)))
        self.assertTrue(cmd_tow(w, [t.elements[0]], m.elements[0]))

    def test_gate3_mutex_requires_tow_mode(self):
        # D065 互斥：mode_set 含 TOW|CARGO|TRANSPORT 任一位且 mode≠TOW → REJECT；
        # 载具须先 SetModeCmd(TOW)
        w = make_world(3)
        t = tractor(w, tow_mode=False)          # DIRECT 态三模式车
        g = gun(w)
        self.assertFalse(cmd_tow(w, [t.elements[0]], g.elements[0]))
        t.elements[0].mode = Mode.TOW
        self.assertTrue(cmd_tow(w, [t.elements[0]], g.elements[0]))

    def test_gate3_direct_tow_bit_also_needs_mode(self):
        # DIRECT|TOW 最小位集同受互斥门（mode_set & (TOW|CARGO|TRANSPORT)≠0 →
        # 须 mode==TOW——:1239 字面无一刀切豁免）
        w = make_world(3)
        t = tractor(w, tpl=TR30_TPL, tow_mode=False)
        g = gun(w)
        self.assertFalse(cmd_tow(w, [t.elements[0]], g.elements[0]))
        t.elements[0].mode = Mode.TOW
        self.assertTrue(cmd_tow(w, [t.elements[0]], g.elements[0]))

    def test_gate3_already_towing_rejects(self):
        # C1 双态：已在拖（TOWING/TOWED）不可再挂——tower 侧与被拖侧同拦
        w = make_world(3)
        t = tractor(w)
        g1 = gun(w)
        g2 = gun(w, pos=(100, 0))
        self.assertTrue(cmd_tow(w, [t.elements[0]], g1.elements[0]))
        self.assertFalse(cmd_tow(w, [t.elements[0]], g2.elements[0]))
        self.assertFalse(cmd_tow(w, [g2.elements[0]], g1.elements[0]))  # TOWED 同拦

    def test_gate3_no_tow_bit_rejects(self):
        # §D.1#15 牵引资格=TOW 位：无位车吨位再大也拒
        w = make_world(3)
        t = tractor(w, tpl=NT_TPL, tow_mode=False)     # mode_set=DIRECT only
        g = gun(w)
        self.assertFalse(cmd_tow(w, [t.elements[0]], g.elements[0]))

    def test_rehook_after_untow_and_zero_dice(self):
        # 解挂后可重挂（无冷却/无残留态）；门序+建立全程零掷骰
        w = make_world(9)
        rng0 = [r.state for r in w.rng._rngs]
        t, g = tractor(w), gun(w)
        self.assertTrue(cmd_tow(w, [t.elements[0]], g.elements[0]))
        cmd_untow(w, t.elements[0])
        self.assertEqual(w.tow_pairs, [])
        self.assertTrue(cmd_tow(w, [t.elements[0]], g.elements[0]))  # 重挂
        self.assertEqual([r.state for r in w.rng._rngs], rng0)

    def test_dispatch_chain_via_commands(self):
        # 分派链：SetModeCmd→TowCmd 经 queue_command/world_tick 落地；
        # UntowCmd 牵引侧入口解对
        w = make_world(11)
        t = tractor(w, tow_mode=False)
        g = gun(w)
        queue_command(w, SetModeCmd(element=t.elements[0], mode=Mode.TOW))
        queue_command(w, TowCmd(tower_elements=[t.elements[0]],
                                towed_element=g.elements[0]))
        world_tick(w)
        self.assertEqual(len(w.tow_pairs), 1)
        self.assertEqual((t.elements[0].towed, g.elements[0].towed),
                         (TowState.TOWING, TowState.TOWED))
        queue_command(w, UntowCmd(element=t.elements[0]))    # 牵引侧入口
        world_tick(w)
        self.assertEqual(w.tow_pairs, [])
        self.assertEqual((t.elements[0].towed, g.elements[0].towed),
                         (TowState.NONE, TowState.NONE))


class TestCmdUntow(unittest.TestCase):
    def _paired(self, seed=3, tpl=DEPLOY_GUN_TPL):
        w = make_world(seed)
        t = tractor(w)
        g = gun(w, tpl=tpl)
        self.assertTrue(cmd_tow(w, [t.elements[0]], g.elements[0]))
        return w, t, g

    def test_towed_side_entry_unhooks(self):
        # 被拖侧入口解对；stop_tow VOLUNTARY 同一收口（因由不分支）
        w, t, g = self._paired()
        cmd_untow(w, g.elements[0])
        self.assertEqual(w.tow_pairs, [])
        self.assertEqual((t.elements[0].towed, g.elements[0].towed),
                         (TowState.NONE, TowState.NONE))

    def test_uninvolved_element_noop(self):
        # 无涉元素=无操作（伪代码无资格门/无 REJECT）
        w, t, g = self._paired()
        other = gun(w, pos=(999, 0))
        cmd_untow(w, other.elements[0])
        self.assertEqual(len(w.tow_pairs), 1)
        self.assertIs(t.elements[0].towed, TowState.TOWING)

    def test_redeploy_flag_kept_blocking_fire(self):
        # C3：stop_tow 不清 redeploy_needed——解挂后 fire_permitted ③ 仍禁射
        #（重展开链起点：须 cmd_deploy 清旗重走 300 拍，见跨链整链用例）
        w, t, g = self._paired()
        g.deploy_state = DeployState.DEPLOYED
        cmd_untow(w, g.elements[0])
        self.assertTrue(g.elements[0].redeploy_needed)      # C3 保留
        e, ws = g.elements[0], g.elements[0].weapon_states[0]
        self.assertFalse(fire_permitted(w, g, e, ws))       # ③ 拦


# ── §F6 :1072-1115 cmd_deploy / :1116-1118 cmd_pack_or_move ──


class TestCmdDeploy(unittest.TestCase):
    def test_mobile_to_deploying_with_timer(self):
        # ① MOBILE → DEPLOYING + deploy_timer=300（timer 写入在分支内）
        w = make_world(3)
        g = gun(w)
        cmd_deploy(w, g)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.DEPLOYING, 300))

    def test_system_timers_transitions_to_deployed_at_300(self):
        # 消费端 system_timers ①：consume 同拍递减 1 → 第 300 拍末 DEPLOYED
        w = make_world(3)
        g = gun(w)
        queue_command(w, DeployCmd(unit=g))
        for _ in range(299):
            world_tick(w)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.DEPLOYING, 1))
        world_tick(w)
        self.assertIs(g.deploy_state, DeployState.DEPLOYED)

    def test_elif_redeploy_has_duration(self):
        # v1.5 终审修 1a：DEPLOYED×含旗（非 TOWED）元素 → 回 DEPLOYING 重走
        # 300 拍（非零成本清旗）
        w = make_world(4)
        g = gun(w)
        g.deploy_state = DeployState.DEPLOYED
        g.elements[0].redeploy_needed = True
        cmd_deploy(w, g)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.DEPLOYING, 300))

    def test_gap09_towed_element_excluded_from_elif(self):
        # GAP-09：留守门不空走——4 门连拖走 1 门（TOWED 中）时 ELIF 不中，
        # 全连保持 DEPLOYED 留守门可开火；被拖门旗保持 TRUE
        w = make_world(5)
        b = add_unit(w, make_unit(w, BAT_TPL, 0, 0, (0, 0)))
        t = tractor(w)
        b.deploy_state = DeployState.DEPLOYED
        self.assertTrue(cmd_tow(w, [t.elements[0]], b.elements[1]))
        cmd_deploy(w, b)
        self.assertIs(b.deploy_state, DeployState.DEPLOYED)     # 不空走
        self.assertEqual(b.deploy_timer, 0)
        self.assertTrue(b.elements[1].redeploy_needed)          # TOWED 旗保持
        self.assertFalse(b.elements[0].redeploy_needed)         # 其余无旗

    def test_after_untow_elif_hits_and_clears(self):
        # 解挂后（towed=NONE、旗 TRUE）→ ELIF 中 → DEPLOYING + 全连清旗
        w = make_world(6)
        b = add_unit(w, make_unit(w, BAT_TPL, 0, 0, (0, 0)))
        t = tractor(w)
        b.deploy_state = DeployState.DEPLOYED
        self.assertTrue(cmd_tow(w, [t.elements[0]], b.elements[1]))
        cmd_untow(w, b.elements[1])
        cmd_deploy(w, b)
        self.assertEqual((b.deploy_state, b.deploy_timer),
                         (DeployState.DEPLOYING, 300))
        self.assertFalse(any(e.redeploy_needed for e in b.elements))

    def test_clear_loop_excludes_only_towed(self):
        # 清旗范围限 towed≠TOWED：TOWING 牵引元素正常清（其禁射由 ⑤ 门另拦）；
        # 仅 TOWED 被拖元素保持
        w = make_world(7)
        b = add_unit(w, make_unit(w, BAT_TPL, 0, 0, (0, 0)))
        t = tractor(w)
        b.deploy_state = DeployState.DEPLOYED
        for e in b.elements:
            e.redeploy_needed = True
        b.elements[2].towed = TowState.TOWING                  # 牵引中元素
        self.assertTrue(cmd_tow(w, [t.elements[0]], b.elements[3]))
        cmd_deploy(w, b)                                       # ELIF：elements[2]
        # 旗 TRUE 且非 TOWED → 中
        self.assertIs(b.deploy_state, DeployState.DEPLOYING)
        self.assertFalse(b.elements[2].redeploy_needed)         # TOWING 正常清
        self.assertTrue(b.elements[3].redeploy_needed)          # TOWED 保持 TRUE

    def test_m18_deploying_no_reset(self):
        # M18/A20：DEPLOYING 期重复下达不重置进度
        w = make_world(8)
        g = gun(w)
        g.deploy_state = DeployState.DEPLOYING
        g.deploy_timer = 100
        cmd_deploy(w, g)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.DEPLOYING, 100))

    def test_packing_period_no_overwrite(self):
        # M18/A20 半边：PACKING 期下达不迁移状态不覆盖计时器（收起以收起时长完成）
        w = make_world(9)
        g = gun(w)
        g.deploy_state = DeployState.PACKING
        g.deploy_timer = 50
        cmd_deploy(w, g)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.PACKING, 50))

    def test_dispatch_chain(self):
        w = make_world(11)
        g = gun(w)
        queue_command(w, DeployCmd(unit=g))
        world_tick(w)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.DEPLOYING, 299))          # 同拍递减 1


class TestCmdPack(unittest.TestCase):
    def _deployed(self, seed=3):
        w = make_world(seed)
        g = gun(w)
        g.deploy_state = DeployState.DEPLOYED
        return w, g

    def test_deployed_to_packing_with_pack_timer(self):
        # ① DEPLOYED → PACKING + pack_time_ticks=300（:1117 pack_time 换名写）
        w, g = self._deployed()
        cmd_pack_or_move(w, g)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.PACKING, 300))

    def test_packing_cycle_via_system_timers_to_mobile(self):
        # 消费端：300 拍计满 → MOBILE（consume 同拍递减 → 第 300 拍末 MOBILE）
        w, g = self._deployed()
        queue_command(w, PackCmd(unit=g))
        for _ in range(299):
            world_tick(w)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.PACKING, 1))
        world_tick(w)
        self.assertIs(g.deploy_state, DeployState.MOBILE)
        self.assertEqual(g.deploy_timer, 0)

    def test_deploying_to_mobile_voids_progress(self):
        # ② DEPLOYING → MOBILE + timer=0（进度作废）
        w = make_world(4)
        g = gun(w)
        g.deploy_state = DeployState.DEPLOYING
        g.deploy_timer = 123
        cmd_pack_or_move(w, g)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.MOBILE, 0))

    def test_packing_period_noop_literal(self):
        # 照字面：两独立 IF——收起中（已 PACKING）下达两 IF 均不中=无操作
        w = make_world(4)
        g = gun(w)
        g.deploy_state = DeployState.PACKING
        g.deploy_timer = 50
        cmd_pack_or_move(w, g)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.PACKING, 50))

    def test_mobile_noop(self):
        w = make_world(5)
        g = gun(w)
        cmd_pack_or_move(w, g)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.MOBILE, 0))

    def test_full_cycle_deploy_pack_via_commands(self):
        # MOBILE →(DeployCmd 300 拍)→ DEPLOYED →(PackCmd 300 拍)→ MOBILE 整环
        w = make_world(6)
        g = gun(w)
        queue_command(w, DeployCmd(unit=g))
        for _ in range(300):
            world_tick(w)
        self.assertIs(g.deploy_state, DeployState.DEPLOYED)
        queue_command(w, PackCmd(unit=g))
        for _ in range(300):
            world_tick(w)
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.MOBILE, 0))


class TestDeployMoveInterlock(unittest.TestCase):
    """门1（契约㉑）联动锚：PACKING 拒移动令既有（movement.py issue_move/
    system_move 双侧）——批② 命令落地后经命令链复合锚定；DEPLOYED/DEPLOYING
    半边=2026-10-07 发起人拍板（pack_or_move 移动触发面=采 IMPL 字面）接线：
    DEPLOYED×移动令先转 PACKING 再走（收装完成后继续移动）、DEPLOYING×外部
    移动令作废放行（unit 侧锚在 tests/test_move_commands.py TestIssueMove）。"""

    def test_packing_rejects_move_order(self):
        w = make_world(3)
        g = gun(w)
        g.deploy_state = DeployState.PACKING
        g.deploy_timer = 50
        queue_command(w, MoveCmd(unit=g, path=[(5000, 0)]))
        world_tick(w)
        self.assertEqual(g.move_path, [])                     # 门1 拒
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.PACKING, 49))           # 计时照走

    def test_deployed_move_order_packs_then_walks(self):
        # 2026-10-07 拍板重锚（原 test_deployed_move_order_walks_without_packing
        # 行为洞锚翻转）：DEPLOYED 单位收移动令先转 PACKING（IMPL :1116 ① 半边）
        # ——本令照常安装（不丢失），收装完成前 system_move 同名门拦位移；
        # GUN_TPL FOOT 档1 越野 25×8000//10000=20cm/拍——300 拍收装毕当拍开走，
        # 250 拍行满 5000cm
        w = make_world(4)
        g = gun(w)
        g.deploy_state = DeployState.DEPLOYED
        queue_command(w, MoveCmd(unit=g, path=[(5000, 0)]))
        world_tick(w)                                         # 受领拍 1
        self.assertEqual(g.move_path, [(5000, 0)])            # 本令已安装
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.PACKING, 299))          # 转收装（同拍递减）
        self.assertEqual(g.pos, (0, 0))                       # 收装中拦位移
        for _ in range(299):
            world_tick(w)                                     # 至 tick 300
        self.assertIs(g.deploy_state, DeployState.MOBILE)     # 收装毕
        self.assertEqual(g.pos, (20, 0))                      # 当拍即开走 20
        for _ in range(249):
            world_tick(w)                                     # 250 拍×20
        self.assertEqual(g.pos, (5000, 0))                    # 行满到达
        self.assertEqual(g.move_path, [])


# ── 跨链：Tow×Deploy×FireMission（G17 闭合整链）+ Tow×Movement（锁速/随动）──


class TestCrossChain(unittest.TestCase):
    def test_tow_untow_redeploy_fire_recovery_chain(self):
        # G17 闭合整链：展开→拖走（旗置位+任务清+③拦）→解挂（旗保持仍拦）→
        # 重展开 300 拍→DEPLOYED 旗清→③ 放行——「到位后展开 30 秒」不可旁路
        w = make_world(3)
        g = add_unit(w, make_unit(w, DEPLOY_GUN_TPL, 0, 0, (0, 0)))
        t = tractor(w)
        e, ws = g.elements[0], g.elements[0].weapon_states[0]
        self.assertFalse(fire_permitted(w, g, e, ws))          # MOBILE ③ 拦
        cmd_deploy(w, g)
        for _ in range(300):
            world_tick(w)
        self.assertIs(g.deploy_state, DeployState.DEPLOYED)
        self.assertTrue(fire_permitted(w, g, e, ws))           # ③ 过
        g.fire_mission = FireMission(form=FireMissionForm.POINT,
                                     target_point=(1, 2), shots_left=5)
        self.assertTrue(cmd_tow(w, [t.elements[0]], e))        # 拖走
        self.assertIsNone(g.fire_mission)                      # :515 单位级整清
        self.assertFalse(fire_permitted(w, g, e, ws))          # redeploy ③ 拦
        cmd_untow(w, e)
        self.assertFalse(fire_permitted(w, g, e, ws))          # C3 旗保持仍拦
        cmd_deploy(w, g)                                       # ELIF 重展开
        self.assertEqual((g.deploy_state, g.deploy_timer),
                         (DeployState.DEPLOYING, 300))
        for _ in range(300):
            world_tick(w)
        self.assertIs(g.deploy_state, DeployState.DEPLOYED)
        self.assertFalse(e.redeploy_needed)
        self.assertTrue(fire_permitted(w, g, e, ws))           # 开火恢复

    def test_gap09_left_behind_guns_keep_firing(self):
        # GAP-09 留守门整锚：4 门须展开炮连 DEPLOYED、拖走 1 门——拖曳中下
        # DeployCmd 全连不空走（保持 DEPLOYED），留守 3 门 fire_permitted ③
        # 持续放行、被拖门拦（AMB-11 重展开窗口全连禁射未被触发=留守门语义）
        w = make_world(5)
        b = add_unit(w, make_unit(w, DEPLOY_BTY_TPL, 0, 0, (0, 0)))
        t = tractor(w)
        b.deploy_state = DeployState.DEPLOYED
        self.assertTrue(cmd_tow(w, [t.elements[0]], b.elements[1]))
        cmd_deploy(w, b)                                      # 拖曳中下令
        self.assertIs(b.deploy_state, DeployState.DEPLOYED)    # 不空走
        for i, e in enumerate(b.elements):
            ws = e.weapon_states[0]
            if i == 1:
                self.assertFalse(fire_permitted(w, b, e, ws))  # 被拖门拦
            else:
                self.assertTrue(fire_permitted(w, b, e, ws))   # 留守门放行

    def test_tow_speed_lock_and_follow_offset(self):
        # Tow×Movement：拖曳锁速（tier3 WHEEL 35→12）+ GAP-14 随动偏移 300
        #（被拖 pos 唯一写点）——MoveCmd 受领拍起逐拍 12cm，100 拍恰达 1200cm
        w = make_world(6)
        t = tractor(w, pos=(10000, 0))                          # 35=70×5000//10000
        g = gun(w, pos=(10000, 0))
        self.assertEqual(move_speed_cm_tick(CONFIG, t, 0), 35)
        self.assertTrue(cmd_tow(w, [t.elements[0]], g.elements[0]))
        self.assertEqual(move_speed_cm_tick(CONFIG, t, 0), 12)  # 25×5000//10000
        queue_command(w, MoveCmd(unit=t, path=[(11200, 0)]))
        for _ in range(50):
            world_tick(w)
        self.assertEqual(t.pos, (10000 + 50 * 12, 0))           # 命令拍即首移拍
        self.assertEqual(g.elements[0].pos, (10000 + 50 * 12 - 300, 0))  # 随动偏移
        for _ in range(50):
            world_tick(w)
        self.assertEqual(t.pos, (11200, 0))                     # 100 拍恰达
        self.assertEqual(g.elements[0].pos, (10900, 0))
        self.assertEqual(g.pos, (11200, 0))                     # 全被拖单位基准随动
        self.assertEqual(t.move_path, [])

    def test_setmode_switch_out_releases_pair(self):
        # Tow×SetMode ④：切出 TOW 即解挂（批① cmd_set_element_mode ② 既有——
        # 经 cmd_tow 建立的真对复核）；解挂后可重新挂
        w = make_world(7)
        t, g = tractor(w), gun(w)
        self.assertTrue(cmd_tow(w, [t.elements[0]], g.elements[0]))
        queue_command(w, SetModeCmd(element=t.elements[0], mode=Mode.DIRECT))
        world_tick(w)
        self.assertEqual(w.tow_pairs, [])
        self.assertIs(t.elements[0].towed, TowState.NONE)
        self.assertTrue(g.elements[0].redeploy_needed)          # C3 保持
        t.elements[0].mode = Mode.TOW
        self.assertTrue(cmd_tow(w, [t.elements[0]], g.elements[0]))  # 可重挂


# ── 真卡链（data/gen/cards_ground.v1.json 实测：SU_TRUCK 15t / SU_ZIS3 13t /
#    GER_PAK40 15t——吨位 0.1t 刻度×10 整型比较用 ≥）──


class TestRealCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = cl.load_library(GEN_LIBRARY)

    def test_su_truck_tows_zis3_and_pak40(self):
        # D065 互斥（真卡）：卡车须先 SetMode(TOW)；15≥13 与 15≥15（恰满足）两链
        w = make_world(42)
        truck = add_unit(w, make_unit(
            w, self.lib["SU_TRUCK"].unit_template, 0, 0, (0, 0)))
        zis = add_unit(w, make_unit(
            w, self.lib["SU_ZIS3"].unit_template, 0, 0, (0, 0)))
        pak = add_unit(w, make_unit(
            w, self.lib["GER_PAK40"].unit_template, 0, 0, (100, 0)))
        te = truck.elements[0]
        self.assertFalse(cmd_tow(w, [te], zis.elements[0]))     # 未切 TOW 拒
        queue_command(w, SetModeCmd(element=te, mode=Mode.TOW))
        world_tick(w)
        self.assertTrue(cmd_tow(w, [te], zis.elements[0]))      # 15 ≥ 13
        self.assertTrue(zis.elements[0].redeploy_needed)
        cmd_untow(w, te)
        self.assertTrue(cmd_tow(w, [te], pak.elements[0]))      # 15 ≥ 15 恰满足
        self.assertEqual(len(w.tow_pairs), 1)

    def test_zis3_deploy_pack_real_timings(self):
        # 真卡 deploy/pack 300 拍（ground_cards.csv SU_ZIS3 行实测）
        w = make_world(43)
        zis = add_unit(w, make_unit(
            w, self.lib["SU_ZIS3"].unit_template, 0, 0, (0, 0)))
        queue_command(w, DeployCmd(unit=zis))
        world_tick(w)
        self.assertEqual((zis.deploy_state, zis.deploy_timer),
                         (DeployState.DEPLOYING, 299))
        for _ in range(299):
            world_tick(w)
        self.assertIs(zis.deploy_state, DeployState.DEPLOYED)
        queue_command(w, PackCmd(unit=zis))
        for _ in range(300):
            world_tick(w)
        self.assertIs(zis.deploy_state, DeployState.MOBILE)


# ── 确定性双跑（同 seed 两 world 逐 tick 指纹位级一致）──


class TestDeterminismDualRun(unittest.TestCase):
    def test_full_maneuver_chain_dual_run_bit_identical(self):
        # 全链命令脚本：SetMode→Tow→Move（锁速+随动）→Untow→Deploy(300 拍)→
        # Pack(300 拍)→MOBILE——逐 tick 指纹位级一致 + 全程零掷骰
        def build(seed):
            w = make_world(seed)
            t = add_unit(w, make_unit(w, TRA_TPL, 0, 0, (10000, 0)))
            g = add_unit(w, make_unit(w, GUN_TPL, 0, 0, (10000, 0)))
            return w, t, g

        def script(w, t, g):
            n = w.tick + 1
            if n == 1:
                queue_command(w, SetModeCmd(element=t.elements[0], mode=Mode.TOW))
            elif n == 2:
                queue_command(w, TowCmd(tower_elements=[t.elements[0]],
                                        towed_element=g.elements[0]))
            elif n == 3:
                queue_command(w, MoveCmd(unit=t, path=[(11200, 0)]))
            elif n == 200:
                queue_command(w, UntowCmd(element=g.elements[0]))
            elif n == 201:
                queue_command(w, DeployCmd(unit=g))
            elif n == 510:
                queue_command(w, PackCmd(unit=g))

        w1, t1, g1 = build(42)
        w2, t2, g2 = build(42)
        rng0 = [r.state for r in w1.rng._rngs]
        while w1.tick < 850:
            script(w1, t1, g1)
            script(w2, t2, g2)
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(fingerprint(w1), fingerprint(w2))
        self.assertEqual([r.state for r in w1.rng._rngs], rng0)   # 零掷骰
        self.assertEqual((g1.deploy_state, g1.deploy_timer),
                         (DeployState.MOBILE, 0))                  # 510+300 拍收装毕
        self.assertEqual(t1.pos, (11200, 0))


if __name__ == "__main__":
    unittest.main()
