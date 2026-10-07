"""§F6 :1258-1267 cmd_set_sniper_cover + :1215-1225 buy_supplies（PB-56 批③
支援链命令块，2026-10-06；GDD-02 v1.9:360「可掩护一个友军单位，敌狙击对该单位
减员概率减半」/:452「物资模式：载弹药600发或医疗品120份按重量混装」）。

锚点全部手推写死（门序/重量式/池写点/乘区分离），不自证。消费端为既有接线
（resolve_sniper_hit covered 乘区 / system_supply ⑥ 补弹医疗 / unregister 双向
清理）——本文件以真命令写侧（经分派链）驱动复核。现役 ground_cards.csv 零卡置
CAN_SNIPER_COVER/HAS_SUPPLY（数据侧双缺位登记见 tick.py 登记表）——测试全部用
合成模板（template_id 6xx 段，CAN_GARRISON 追认前同款机制侧占位）。零掷骰：
命令处理纯整数确定性，不触任何 PCG32 通道（消费端乘区掷 SNIPER=既有通道纪律）。
"""
import unittest

from sovs.sim.combat import resolve_hit, unregister_unit_refs
from sovs.sim.tick import (BuySuppliesCmd, Projectile, SetAirdropBeaconCmd,
                           SetModeCmd,
                           SetSniperCoverCmd, add_unit, buy_supplies,
                           cmd_set_airdrop_beacon, cmd_set_sniper_cover,
                           consume_commands, make_unit,
                           make_world, queue_command, system_supply,
                           world_tick)
from sovs.sim.tables import BalanceConfig, CONFIG
from sovs.sim.types import (DamageType, ElementTemplate, ElementType, Mode,
                            MovementClass, UnitFlag, UnitTemplate, UnitType,
                            WeaponTemplate, WState)

# ── 合成模板（测试用，不对应真实卡；6xx 段——test_garrison 先例）──

RIFLE = WeaponTemplate(name="SPT_RIFLE", damage=1, max_range_cm=10000,
                       ammo_base=10, reload_time_ticks=10, salvo=1)
SQUAD_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                             unit_type=UnitType.INFANTRY, hp_max=10,
                             weapons=(RIFLE,))
# 可掩护狙击组（GDD-02 v1.9:360 卡面承诺的机制侧合成承载——现役无狙击组卡且
# CAN_SNIPER_COVER 0 卡置位）
COVER_SNIPER_TPL = UnitTemplate(
    template_id=620, name="cover sniper", category=1, cost=30,
    element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=6,
    speed_tier=1, movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_SNIPER_COVER)
# 无资格位班（① 门负锚）
PLAIN_SQUAD_TPL = UnitTemplate(
    template_id=621, name="plain squad", category=1, cost=20,
    element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)
# 敌方射手（消费端乘区对照载体——combat_style=2 SNIPER；⑲A 载体同 test_ground_
# combat :116-118）
SNIPER_W = WeaponTemplate(name="SPT_SNIPER", combat_style=2, damage=1,
                          max_range_cm=40000, aim_time_ticks=50,
                          reload_time_ticks=100, ammo_base=5,
                          accuracy_base_bp=10000, projectile_speed_cm_tick=100)
SNIPER_SHOOTER_TPL = UnitTemplate(
    template_id=622, name="enemy sniper", category=1, cost=30,
    element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                       unit_type=UnitType.INFANTRY, hp_max=4,
                                       weapons=(SNIPER_W,)),),
    optics_ground_cm=20000, stealth_base=6, speed_tier=1,
    movement_class=MovementClass.FOOT)
# 补给卡车（D065 三舱 600/120/600=ground_elements.csv SU_TRUCK 同值；HAS_SUPPLY
# +CARGO 位——现役 SU_TRUCK flags 空的数据侧补位载体，supply_radius 默认 8000）
CARGO_TRUCK_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                                   unit_type=UnitType.MECH, hp_max=10,
                                   cargo_rounds_max=600, cargo_medical_max=120,
                                   cargo_weight_max=600)
CARGO_TRUCK_TPL = UnitTemplate(
    template_id=630, name="supply truck", category=4, cost=30,
    element_templates=(CARGO_TRUCK_ELEM,), optics_ground_cm=20000,
    stealth_base=5, speed_tier=3, movement_class=MovementClass.WHEEL,
    flags=UnitFlag.HAS_SUPPLY,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.CARGO))
# 无 HAS_SUPPLY 位卡车（① 门负锚——舱位数据在位但链不可达的现役 SU_TRUCK 同款）
TRUCK_NOFLAG_TPL = UnitTemplate(
    template_id=631, name="plain truck", category=4, cost=30,
    element_templates=(CARGO_TRUCK_ELEM,), optics_ground_cm=20000,
    stealth_base=5, speed_tier=3, movement_class=MovementClass.WHEEL,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.CARGO))

# 消费端确定性 cfg（test_ground_combat :1979-1982 同款——prob 钳 0/10000 锚）
CFG_SNIPER_CERTAIN = BalanceConfig(sniper_base_prob_bp=10000)
CFG_SNIPER_COVER0 = BalanceConfig(sniper_base_prob_bp=10000,
                                  sniper_cover_mult_bp=0)   # 有掩护→prob 0 必不中
# 重量式 cfg 覆写（§D.0 :73-74 常数接线锚——D012 互算外的独立定标可表达）
CFG_WEIGHT2 = BalanceConfig(supply_round_weight_g=2, med_weight_per_unit_g=10)


def channel_states(w):
    return {name: w.rng.rng(i).state for i, name in enumerate(
        ("HIT", "SCATTER", "SPOT", "CRIT", "SNIPER", "SONAR", "ECONOMY", "AIR"))}


def mk_proj(w, shooter_e, weapon, *, dest, pos=None, hit_target=None):
    """直达狙击弹（speed=100000 一拍即达——resolve_sniper_hit 载体，test_garrison
    mk_proj 同款）。"""
    return Projectile(shooter=shooter_e, weapon=weapon,
                      damage_type=weapon.damage_type, damage=weapon.damage,
                      blast_cm=weapon.blast_radius_cm,
                      pos=pos if pos is not None else dest, dest=dest,
                      speed_cm_tick=100000, trajectory=weapon.trajectory,
                      hit_target=hit_target, will_hit=True)


class TestCmdSetSniperCoverGates(unittest.TestCase):
    """§F6 :1258-1263 门序逐项（①资格/②⑳A 同队/③存活两支/④非自身）。"""

    def _pair(self, sniper_tpl=COVER_SNIPER_TPL, tgt_tpl=PLAIN_SQUAD_TPL):
        w = make_world(7)
        sniper = add_unit(w, make_unit(w, sniper_tpl, 0, 0, (0, 0)))
        tgt = add_unit(w, make_unit(w, tgt_tpl, 0, 0, (1000, 0)))
        return w, sniper, tgt

    def test_gate_qualification_flag_required(self):
        # ① 无 CAN_SNIPER_COVER 位 → REJECT（现役全卡恒此支——数据侧双缺位登记）
        w, sniper, tgt = self._pair(sniper_tpl=PLAIN_SQUAD_TPL)
        self.assertFalse(cmd_set_sniper_cover(w, sniper, tgt))
        self.assertEqual(w.cover_by_target, {})

    def test_gate_same_team_required(self):
        # ② ⑳A 同队门：敌队目标拒（原可对敌挂掩护压低我方狙击概率=自伤型误操作）
        w = make_world(7)
        sniper = add_unit(w, make_unit(w, COVER_SNIPER_TPL, 0, 0, (0, 0)))
        enemy = add_unit(w, make_unit(w, PLAIN_SQUAD_TPL, 1, 1, (1000, 0)))
        self.assertFalse(cmd_set_sniper_cover(w, sniper, enemy))
        self.assertEqual(w.cover_by_target, {})

    def test_gate_dead_target_rejected(self):
        # ③ 存活门前半：alive=False 拒（元素仍在编）
        w, sniper, tgt = self._pair()
        tgt.alive = False
        self.assertFalse(cmd_set_sniper_cover(w, sniper, tgt))
        self.assertEqual(w.cover_by_target, {})

    def test_gate_empty_elements_target_rejected(self):
        # ③ 存活门后半：elements==[] 拒
        w, sniper, tgt = self._pair()
        tgt.elements.clear()
        self.assertFalse(cmd_set_sniper_cover(w, sniper, tgt))
        self.assertEqual(w.cover_by_target, {})

    def test_gate_self_target_rejected(self):
        # ④ 非自身门：sniper==target 拒（恒等判 is）
        w, sniper, _ = self._pair()
        self.assertFalse(cmd_set_sniper_cover(w, sniper, sniper))
        self.assertEqual(w.cover_by_target, {})


class TestCmdSetSniperCoverWrites(unittest.TestCase):
    """§F6 :1265-1267 替换语义+写点（键=unit.id；值=掩护者 unit 列表配 identity
    清理；空键删收口=IMPL :492 unregister 同款）。"""

    def _world_units(self, n_targets=1):
        w = make_world(11)
        snipers = [add_unit(w, make_unit(w, COVER_SNIPER_TPL, 0, 0, (0, 0)))
                   for _ in range(2)]
        targets = [add_unit(w, make_unit(w, PLAIN_SQUAD_TPL, 0, 0,
                                         (1000 * (i + 1), 0)))
                   for i in range(n_targets)]
        return w, snipers, targets

    def test_accept_writes_id_keyed_protector_list(self):
        # 接受：cover_by_target[tgt.id]=[sniper]——键=unit.id（v1.7 键型适配），
        # 值=unit 对象（后随 identity 清理消费）
        w, snipers, targets = self._world_units()
        s, tgt = snipers[0], targets[0]
        self.assertTrue(cmd_set_sniper_cover(w, s, tgt))
        self.assertEqual(w.cover_by_target, {tgt.id: [s]})
        self.assertIs(w.cover_by_target[tgt.id][0], s)

    def test_replacement_clears_old_target_key(self):
        # 1:1 替换：换目标后旧键**整键删除**（伪代码 :1265-1266 未删空键——消费=
        # 键存在性布尔，留洞则旧目标零掩护者仍恒享减半；IMPL :492 同款收口锚）
        w, snipers, targets = self._world_units(n_targets=2)
        s, a, b = snipers[0], targets[0], targets[1]
        self.assertTrue(cmd_set_sniper_cover(w, s, a))
        self.assertTrue(cmd_set_sniper_cover(w, s, b))
        self.assertEqual(w.cover_by_target, {b.id: [s]})       # a 键已删
        self.assertNotIn(a.id, w.cover_by_target)

    def test_reissue_same_target_reinserts(self):
        # 重挂同目标：先移除后重插——净状态同（插入序移尾，无重复条目）
        w, snipers, targets = self._world_units()
        s, tgt = snipers[0], targets[0]
        cmd_set_sniper_cover(w, s, tgt)
        self.assertTrue(cmd_set_sniper_cover(w, s, tgt))
        self.assertEqual(w.cover_by_target, {tgt.id: [s]})

    def test_two_snipers_same_target_coexist(self):
        # §D.8#5：同目标多狙击并存（值=列表；消费=存在性布尔不叠加）
        w, snipers, targets = self._world_units()
        s1, s2, tgt = snipers[0], snipers[1], targets[0]
        self.assertTrue(cmd_set_sniper_cover(w, s1, tgt))
        self.assertTrue(cmd_set_sniper_cover(w, s2, tgt))
        self.assertEqual(w.cover_by_target, {tgt.id: [s1, s2]})

    def test_partial_replacement_keeps_other_protector(self):
        # s1/s2 同护 A；s1 改护 B → A 保留 [s2]（键不删——非空）、B=[s1]
        w, snipers, targets = self._world_units(n_targets=2)
        s1, s2, a, b = snipers[0], snipers[1], targets[0], targets[1]
        cmd_set_sniper_cover(w, s1, a)
        cmd_set_sniper_cover(w, s2, a)
        self.assertTrue(cmd_set_sniper_cover(w, s1, b))
        self.assertEqual(w.cover_by_target, {a.id: [s2], b.id: [s1]})

    def test_unregister_composes_with_command_writes(self):
        # 与 unregister_unit_refs 合成：掩护者销毁→名单移除+空键删；被掩护者销毁
        # →整键注销（combat.py :257-263 既有，本锚证命令写点形态与其闭环）
        w, snipers, targets = self._world_units(n_targets=2)
        s1, s2, a, b = snipers[0], snipers[1], targets[0], targets[1]
        cmd_set_sniper_cover(w, s1, a)
        cmd_set_sniper_cover(w, s2, a)
        cmd_set_sniper_cover(w, s1, b)
        unregister_unit_refs(w, s1)                    # s1 护 a、b → 两处移除
        self.assertEqual(w.cover_by_target, {a.id: [s2]})
        unregister_unit_refs(w, a)                     # a 被掩护 → 整键注销
        self.assertEqual(w.cover_by_target, {})

    def test_cmd_via_command_queue(self):
        # 分派链全链：queue_command→consume_commands→真调用；拒令仍消费（FIFO 丢弃）
        w, snipers, targets = self._world_units()
        s, tgt = snipers[0], targets[0]
        queue_command(w, SetSniperCoverCmd(sniper_unit=s, target_unit=s))   # ④ 拒
        queue_command(w, SetSniperCoverCmd(sniper_unit=snipers[1],
                                           target_unit=tgt))                # 受理
        consume_commands(w, CONFIG)
        self.assertEqual(w.command_queue, [])
        self.assertEqual(w.cover_by_target, {tgt.id: [snipers[1]]})

    def test_channels_untouched_zero_dice(self):
        # 零掷骰：受理+拒令各一，八通道 state 逐位不动
        w, snipers, targets = self._world_units()
        before = channel_states(w)
        cmd_set_sniper_cover(w, snipers[0], targets[0])
        cmd_set_sniper_cover(w, snipers[0], snipers[0])
        queue_command(w, SetSniperCoverCmd(sniper_unit=snipers[1],
                                           target_unit=targets[0]))
        consume_commands(w, CONFIG)
        self.assertEqual(channel_states(w), before)


class TestSniperCoverConsumerViaCommand(unittest.TestCase):
    """消费端乘区经真命令写侧驱动（resolve_sniper_hit covered 判定×
    sniper_cover_mult_bp——combat.py 既有零改动；test_ground_combat
    test_cover_table_consulted 手写旁表的命令侧对偶锚）。"""

    def _worlds(self, covered: bool):
        w = make_world(9)
        tgt = add_unit(w, make_unit(w, PLAIN_SQUAD_TPL, 1, 1, (0, 0)))
        shooter = add_unit(w, make_unit(w, SNIPER_SHOOTER_TPL, 0, 0, (3000, 0)))
        if covered:
            protector = add_unit(w, make_unit(w, COVER_SNIPER_TPL, 1, 1, (500, 0)))
            self.assertTrue(cmd_set_sniper_cover(w, protector, tgt))
        p = mk_proj(w, shooter.elements[0], SNIPER_W,
                    dest=tgt.elements[0].pos, hit_target=tgt.elements[0])
        return w, tgt, p

    def test_cover_multiplier_via_real_command(self):
        # 同 seed 双世界：有掩护（经真命令写入）+cover_mult=0 → prob=0 必不中；
        # 无掩护同 cfg → prob=10000 必中 2 人（hp 10→8）。两世界 SNIPER 通道
        # 各耗掷（chance_bp 无条件抽签）——分离锚同 test_cover_table_consulted。
        w1, tgt1, p1 = self._worlds(covered=True)
        before1 = channel_states(w1)
        resolve_hit(w1, p1, CFG_SNIPER_COVER0)
        self.assertEqual(tgt1.elements[0].hp_current, 10)      # 减半乘区生效
        self.assertEqual(tgt1.r02_kill_tally, 0)
        self.assertNotEqual(channel_states(w1)["SNIPER"], before1["SNIPER"])
        w2, tgt2, p2 = self._worlds(covered=False)
        resolve_hit(w2, p2, CFG_SNIPER_COVER0)
        self.assertEqual(tgt2.elements[0].hp_current, 10 - 2)  # 无掩护必中


class TestBuySuppliesGates(unittest.TestCase):
    """§F6 :1215-1224 门序逐项（①hasSupply 载具/②仅 CARGO/③弹药舱/④医疗舱/
    ⑤D012 载重）+负值输入纪律防御门。"""

    def _truck(self, tpl=CARGO_TRUCK_TPL, mode=Mode.DIRECT, pos=(0, 0)):
        w = make_world(3)
        t = add_unit(w, make_unit(w, tpl, 0, 0, pos))
        t.elements[0].mode = mode
        return w, t.elements[0]

    def test_gate_has_supply_flag_required(self):
        # ① 无 HAS_SUPPLY 位 → REJECT（mode 已 CARGO=① 先于 ② 拒；现役 SU_TRUCK
        # flags 空恒此支——数据侧补位另裁）
        w, e = self._truck(tpl=TRUCK_NOFLAG_TPL, mode=Mode.CARGO)
        self.assertFalse(buy_supplies(w, e, 10, 0))
        self.assertIsNone(e.supply_weight_g)               # 条件槽不触碰（方案12）

    def test_gate_cargo_mode_required(self):
        # ② v1.3 审查#8：仅物资模式可装货（DIRECT/TRANSPORT/TOW 不可预装）
        w, e = self._truck(mode=Mode.DIRECT)
        self.assertFalse(buy_supplies(w, e, 10, 0))
        self.assertIsNone(e.supply_weight_g)

    def test_gate_rounds_bay(self):
        # ③ 弹药舱位：600 受理 / 601 拒（ground_elements.csv SU_TRUCK 同值）
        w, e = self._truck(mode=Mode.CARGO)
        self.assertTrue(buy_supplies(w, e, 600, 0))
        w, e = self._truck(mode=Mode.CARGO)
        self.assertFalse(buy_supplies(w, e, 601, 0))
        self.assertIsNone(e.supply_weight_g)

    def test_gate_medical_bay(self):
        # ④ 医疗舱位：120 受理 / 121 拒
        w, e = self._truck(mode=Mode.CARGO)
        self.assertTrue(buy_supplies(w, e, 0, 120))
        w, e = self._truck(mode=Mode.CARGO)
        self.assertFalse(buy_supplies(w, e, 0, 121))

    def test_gate_weight_d012(self):
        # ⑤ D012 混装载重闸：300 发+60 份=300×1+60×5=600 恰满受理；
        # 300 发+61 份=605>600 拒（单舱未超而混装超载——闸存在性锚）
        w, e = self._truck(mode=Mode.CARGO)
        self.assertTrue(buy_supplies(w, e, 300, 60))
        w, e = self._truck(mode=Mode.CARGO)
        self.assertFalse(buy_supplies(w, e, 300, 61))

    def test_negative_inputs_defensive_reject(self):
        # 输入纪律（可推翻防御门）：伪代码 > 比较对负数恒放行、直写负池惰性腐化
        # ——cmd_set_element_mode 裸 int 拒令同款显式拒令
        w, e = self._truck(mode=Mode.CARGO)
        self.assertFalse(buy_supplies(w, e, -1, 0))
        self.assertFalse(buy_supplies(w, e, 0, -5))
        self.assertIsNone(e.supply_weight_g)


class TestBuySuppliesWrites(unittest.TestCase):
    """§F6 :1218/:1225 重量式+一池写点（2026-10-03 拍板换写 supply_weight_g）。"""

    def _cargo_truck(self):
        w = make_world(5)
        t = add_unit(w, make_unit(w, CARGO_TRUCK_TPL, 0, 0, (0, 0)))
        t.elements[0].mode = Mode.CARGO
        return w, t.elements[0]

    def test_full_ammo_load(self):
        # 600 发=600g（supply_round_weight_g=1 占位：D012 满额互算 600÷600，
        # 与 per-weapon ammo_weight 占位同值）；None→首次写入即分配
        w, e = self._cargo_truck()
        self.assertTrue(buy_supplies(w, e, 600, 0))
        self.assertEqual(e.supply_weight_g, 600)

    def test_full_medical_load(self):
        # 120 份=600g（med_weight_per_unit_g=5=§D.0 :73 定值）——与 600 发同满额
        # （GDD-02 v1.9:452「600发或120份按重量混装」互算自洽锚）
        w, e = self._cargo_truck()
        self.assertTrue(buy_supplies(w, e, 0, 120))
        self.assertEqual(e.supply_weight_g, 600)

    def test_mixed_full_load(self):
        # 300 发+60 份=300+300=600 恰满混装
        w, e = self._cargo_truck()
        self.assertTrue(buy_supplies(w, e, 300, 60))
        self.assertEqual(e.supply_weight_g, 600)

    def test_partial_load_weight(self):
        # 7 发+3 份=7+15=22
        w, e = self._cargo_truck()
        self.assertTrue(buy_supplies(w, e, 7, 3))
        self.assertEqual(e.supply_weight_g, 22)

    def test_assignment_semantics_not_accumulate(self):
        # :1225 直赋值的等价换写=换装而非补装：重复购买 (100,0) 池=100 非 200
        w, e = self._cargo_truck()
        buy_supplies(w, e, 100, 0)
        buy_supplies(w, e, 100, 0)
        self.assertEqual(e.supply_weight_g, 100)

    def test_zero_zero_literal_write(self):
        # (0,0)：三门全过、weight=0 → 池写 0（伪代码字面——已分配槽清空同值）
        w, e = self._cargo_truck()
        self.assertTrue(buy_supplies(w, e, 0, 0))
        self.assertEqual(e.supply_weight_g, 0)

    def test_custom_cfg_constants_respected(self):
        # §D.0 :73-74 常数接线锚：覆写 2g/发+10g/份 → (100,10)=200+100=300；
        # (250,11)=500+110=610>600 拒（载重闸随 cfg 动）
        w, e = self._cargo_truck()
        self.assertTrue(buy_supplies(w, e, 100, 10, CFG_WEIGHT2))
        self.assertEqual(e.supply_weight_g, 300)
        w, e = self._cargo_truck()
        self.assertFalse(buy_supplies(w, e, 250, 11, CFG_WEIGHT2))

    def test_cmd_via_command_queue(self):
        # 分派链全链：queue_command→consume_commands→真调用；② 门拒令仍消费
        w, e = self._cargo_truck()
        e.mode = Mode.DIRECT                                   # ② 拒令载体
        queue_command(w, BuySuppliesCmd(truck_element=e, rounds=600, medical=0))
        consume_commands(w, CONFIG)
        self.assertEqual(w.command_queue, [])
        self.assertIsNone(e.supply_weight_g)
        queue_command(w, BuySuppliesCmd(truck_element=e, rounds=300, medical=60))
        e.mode = Mode.CARGO
        consume_commands(w, CONFIG)
        self.assertEqual(e.supply_weight_g, 600)

    def test_channels_untouched_zero_dice(self):
        w, e = self._cargo_truck()
        before = channel_states(w)
        buy_supplies(w, e, 300, 60)
        buy_supplies(w, e, 999, 0)                             # ③ 拒
        queue_command(w, BuySuppliesCmd(truck_element=e, rounds=0, medical=1))
        consume_commands(w, CONFIG)
        self.assertEqual(channel_states(w), before)


class TestBuySuppliesChain(unittest.TestCase):
    """跨链效果（补给量变化）：SetMode(CARGO)〔批①〕→BuySupplies〔本块〕→
    system_supply ⑥ 补弹/医疗〔2026-10-03 一池既有〕——装货整链首次全通
    （R-18 消费侧 test_supply_mount 既有锚不扰）。"""

    def _chain_world(self, rounds, medical):
        w = make_world(13)
        truck = add_unit(w, make_unit(w, CARGO_TRUCK_TPL, 0, 0, (5000, 0)))
        queue_command(w, SetModeCmd(element=truck.elements[0], mode=Mode.CARGO))
        queue_command(w, BuySuppliesCmd(truck_element=truck.elements[0],
                                        rounds=rounds, medical=medical))
        consume_commands(w, CONFIG)
        return w, truck

    def test_setmode_buy_resupply_ammo_chain(self):
        # 命令队列整链：SetMode(CARGO)→BuySupplies(600,0)→池 600；耗弹班（半径
        # 5000≤8000 内、EMPTY）system_supply 一拍补 2 发扣 2g（take=MIN(10,600//1,2)）
        w, truck = self._chain_world(600, 0)
        e = truck.elements[0]
        self.assertIs(e.mode, Mode.CARGO)
        self.assertEqual(e.supply_weight_g, 600)
        inf = add_unit(w, make_unit(w, PLAIN_SQUAD_TPL, 0, 0, (0, 0)))
        ws = inf.elements[0].weapon_states[0]
        ws.ammo_left = 0
        ws.state = WState.EMPTY
        w.await_resupply.append(inf)
        system_supply(w)
        self.assertEqual(ws.ammo_left, 2)
        self.assertIs(ws.state, WState.READY)                 # 方案19 EMPTY 转正
        self.assertEqual(e.supply_weight_g, 598)

    def test_setmode_buy_heal_medical_chain(self):
        # 医疗侧：(0,120)→池 600；带伤步兵 hp7 → heal=MIN(3,600//1)=3 → hp10 扣 3g
        w, truck = self._chain_world(0, 120)
        e = truck.elements[0]
        self.assertEqual(e.supply_weight_g, 600)
        inf = add_unit(w, make_unit(w, PLAIN_SQUAD_TPL, 0, 0, (0, 0)))
        inf.elements[0].hp_current = 7
        w.await_resupply.append(inf)
        system_supply(w)
        self.assertEqual(inf.elements[0].hp_current, 10)
        self.assertEqual(e.supply_weight_g, 597)

    def test_switch_out_of_cargo_unloads_bought_pool(self):
        # 联动（批① cmd_set_element_mode ③ 既有）：装货后切回 DIRECT → 池清零
        w, truck = self._chain_world(600, 0)
        e = truck.elements[0]
        self.assertEqual(e.supply_weight_g, 600)
        queue_command(w, SetModeCmd(element=e, mode=Mode.DIRECT))
        consume_commands(w, CONFIG)
        self.assertEqual(e.supply_weight_g, 0)


class TestAirdropBeaconCmd(unittest.TestCase):
    """§F6 :1269-1271 cmd_set_airdrop_beacon（2026-10-06 收口补落——§D.7 22 类最后一支）。"""

    def _beacon_unit(self, w, flag=True):
        tpl = UnitTemplate(
            template_id=620, name="beacon inf", category=1, cost=20,
            element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                               unit_type=UnitType.INFANTRY, hp_max=10),),
            optics_ground_cm=20000, stealth_base=5, speed_tier=1,
            movement_class=MovementClass.FOOT,
            flags=UnitFlag.CAN_AIRDROP_BEACON if flag else 0)
        return add_unit(w, make_unit(w, tpl, 0, 0, (0, 0)))

    def test_gate_and_write(self):
        # ① 资格门（无位 REJECT）/② 写 (team,pos)——键=unit.id 三口同形
        # （air 读侧/combat 注销侧同日同修——键型适配 PB-45 先例）
        w = make_world(7)
        u = self._beacon_unit(w, flag=False)
        self.assertFalse(cmd_set_airdrop_beacon(w, u, (1000, 2000)))
        self.assertEqual(w.beacon_by_unit, {})
        u2 = self._beacon_unit(w, flag=True)
        self.assertTrue(cmd_set_airdrop_beacon(w, u2, (1000, 2000)))
        self.assertEqual(w.beacon_by_unit, {u2.id: (0, (1000, 2000))})

    def test_dispatch_and_reader_e2e(self):
        # 分派链端到端：queue→consume→写入→nearest_friendly_beacon 读到（己方命中/
        # 敌队 None——键型三口同形）
        from sovs.sim.air import nearest_friendly_beacon
        w = make_world(9)
        u = self._beacon_unit(w)
        queue_command(w, SetAirdropBeaconCmd(unit=u, pos=(2000, 0)))
        world_tick(w)
        self.assertEqual(w.beacon_by_unit, {u.id: (0, (2000, 0))})
        self.assertEqual(nearest_friendly_beacon(w.beacon_by_unit, 0, (0, 0)),
                         (2000, 0))
        self.assertIsNone(nearest_friendly_beacon(w.beacon_by_unit, 1, (0, 0)))


class TestRealCardSupplyChain(unittest.TestCase):
    """SU_TRUCK 补 HAS_SUPPLY（2026-10-06 数据侧承载拍板）——真卡买补给链端到端。"""

    def test_su_truck_buy_supplies_e2e(self):
        from sovs.sim.card_loader import load_library
        lib = load_library("data/gen/cards_ground.v1.json")
        self.assertTrue(lib["SU_TRUCK"].unit_template.flags & UnitFlag.HAS_SUPPLY)
        w = make_world(11)
        truck = add_unit(w, make_unit(w, lib["SU_TRUCK"].unit_template, 0, 0, (0, 0)))
        e = truck.elements[0]
        self.assertIsNone(e.supply_weight_g)            # make_unit 未分配条件槽
        queue_command(w, SetModeCmd(element=e, mode=Mode.CARGO))   # ② 模式门：先切 CARGO
        queue_command(w, BuySuppliesCmd(truck_element=e, rounds=100, medical=20))
        world_tick(w)
        self.assertEqual(e.supply_weight_g,
                         100 * CONFIG.supply_round_weight_g
                         + 20 * CONFIG.med_weight_per_unit_g)   # 100×1+20×5=200g


if __name__ == "__main__":
    unittest.main()
