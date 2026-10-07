"""§F6 :1248-1255 cmd_garrison / cmd_un_garrison（PB-57 驻楼命令块，2026-10-06；
D003 建筑进驻——拍板清单 PB-57「机制先行、数据后接」）。

锚点全部手推写死（门序/容量比较/隐蔽算式/命中面锚），不自证。效果面为既有
接线（sensing AMB-02 合取式 / compute_hit_facing 驻楼 REAR / GAP-02 移动出楼）
——本文件以真命令写侧（cmd_garrison 经分派链）驱动复核，另补效果合取式负锚。
现役 ground_cards.csv 零卡置 CAN_GARRISON（数据侧脱节登记见 tick.py 登记表）——
测试全部用合成模板（template_id 6xx 段，GDD-02 v1.9:50 侦察班卡面承诺的
机制侧占位）。零掷骰：命令处理纯整数确定性，不触任何 PCG32 通道。
"""
import unittest

from sovs.sim.combat import (apply_damage, compute_hit_facing, hit_building,
                             resolve_hit)
from sovs.sim.map_loader import apply_map, load_demo_map
from sovs.sim.sensing import effective_stealth_x10
from sovs.sim.tick import (GarrisonCmd, MoveCmd, Projectile, UnGarrisonCmd,
                           add_unit, begin_aim, cmd_garrison, cmd_un_garrison,
                           consume_commands, finish_aim, make_unit, make_world,
                           queue_command, select_target, world_tick)
from sovs.sim.tables import BalanceConfig, CONFIG
from sovs.sim.types import (Armor, Building, DamageType, ElementTemplate,
                            ElementType, Facing, MovementClass, UnitFlag,
                            UnitTemplate, UnitType, WeaponTemplate, WState)

# ── 合成模板（测试用，不对应真实卡；6xx 段）──

GAR_RIFLE = WeaponTemplate(name="GAR_RIFLE", damage=1, max_range_cm=10000,
                           ammo_base=10, reload_time_ticks=10, salvo=1,
                           aim_time_ticks=0)
GAR_SQUAD_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                                 unit_type=UnitType.INFANTRY, hp_max=10,
                                 weapons=(GAR_RIFLE,))
# 可驻楼侦察班（GDD-02 v1.9:50 卡面承诺的机制侧合成承载——现役卡无此位）
RECON_TPL = UnitTemplate(
    template_id=610, name="recon gar", category=0, cost=15,
    element_templates=(GAR_SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT, flags=UnitFlag.CAN_GARRISON)
# 双班排（容量门按单位整体判一次的伪代码字面行为载体）
RECON_PLATOON_TPL = UnitTemplate(
    template_id=611, name="recon plt", category=0, cost=30,
    element_templates=(GAR_SQUAD_ELEM, GAR_SQUAD_ELEM), optics_ground_cm=20000,
    stealth_base=5, speed_tier=1, movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_GARRISON)
# 无 CAN_GARRISON 位（① 门/隐蔽合取式负锚）
PLAIN_INF_TPL = UnitTemplate(
    template_id=612, name="plain inf", category=1, cost=20,
    element_templates=(GAR_SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)
# 混编双班排（塌楼混合处置载体——PB-57 塌楼验收块 2026-10-06）：班0 hp10（恰死档）
# + 班1 hp16（带伤存活档）——同楼塌落一发伤害分置生死两途
MIXED_SQUAD_ELEM_16 = ElementTemplate(element_type=ElementType.SQUAD,
                                      unit_type=UnitType.INFANTRY, hp_max=16,
                                      weapons=(GAR_RIFLE,))
MIXED_PLATOON_TPL = UnitTemplate(
    template_id=615, name="mixed plt", category=0, cost=30,
    element_templates=(GAR_SQUAD_ELEM, MIXED_SQUAD_ELEM_16),
    optics_ground_cm=20000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT, flags=UnitFlag.CAN_GARRISON)
# 可驻楼装甲车（驻楼 REAR 命中面积分载体——合成：CAN_GARRISON 现役无卡置位）
GAR_ARMOR_ELEM = ElementTemplate(
    element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=20,
    armor_ke=Armor(front=8, side=5, rear=3, top=1),
    armor_he=Armor(front=6, side=4, rear=2, top=1), weapons=())
GAR_ARMORED_TPL = UnitTemplate(
    template_id=613, name="gar armor", category=2, cost=120,
    element_templates=(GAR_ARMOR_ELEM,), optics_ground_cm=20000, stealth_base=4,
    speed_tier=2, movement_class=MovementClass.TRACK, flags=UnitFlag.CAN_GARRISON)
# 固定穿深 KE 炮（pen_min=pen_max——锚点与落点距离解耦；同 test_ground_combat.KE6）
KE6 = WeaponTemplate(name="GAR_KE6", damage_type=DamageType.KE, pen_min=6,
                     pen_max=6, damage=10, max_range_cm=50000,
                     projectile_speed_cm_tick=100, blast_radius_cm=2500,
                     suppression_power=10)
SHOOTER_TPL = UnitTemplate(
    template_id=614, name="gar shooter", category=2, cost=60,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=20,
                                       weapons=(KE6,)),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=2,
    movement_class=MovementClass.TRACK)


def channel_states(w):
    return {name: w.rng.rng(i).state for i, name in enumerate(
        ("HIT", "SCATTER", "SPOT", "CRIT", "SNIPER", "SONAR", "ECONOMY", "AIR"))}


def mk_proj(w, shooter_e, weapon, *, dest, pos=None, hit_target=None,
            will_hit=True):
    """直达弹（speed=100000 一拍即达——命中面积分载体，同 test_ground_combat 惯例）。"""
    return Projectile(shooter=shooter_e, weapon=weapon,
                      damage_type=weapon.damage_type, damage=weapon.damage,
                      blast_cm=weapon.blast_radius_cm,
                      pos=pos if pos is not None else dest, dest=dest,
                      speed_cm_tick=100000, trajectory=weapon.trajectory,
                      hit_target=hit_target, will_hit=will_hit)


class TestGarrisonGates(unittest.TestCase):
    """cmd_garrison 门序逐项（§F6 :1248-1250 字面两门 + 塌楼完整性收口）。"""

    def _world_unit(self, tpl=RECON_TPL, pos=(0, 0)):
        w = make_world(7)
        return w, add_unit(w, make_unit(w, tpl, 0, 0, pos))

    def test_gate_can_garrison_flag_required(self):
        # ① 兵种门：无 CAN_GARRISON 位 → REJECT（现役全卡恒此支——数据侧脱节登记）
        w, u = self._world_unit(PLAIN_INF_TPL)
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=3)
        self.assertFalse(cmd_garrison(w, u, b))
        self.assertIsNone(u.elements[0].garrison_in)
        self.assertEqual(b.garrisoned, [])

    def test_gate_capacity_exhausted(self):
        # ② 容量门（按排=单位数计——2026-10-06 拍板）：第二个单位拒入
        w, u1 = self._world_unit()
        u2 = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        self.assertTrue(cmd_garrison(w, u1, b))
        self.assertFalse(cmd_garrison(w, u2, b))
        self.assertEqual(len(b.garrisoned), 1)

    def test_gate_zero_slots_default_reject(self):
        # Building.garrison_slots 缺省 0：0<=0 恒 REJECT——合成/装配建筑必须显式赋槽
        # （apply_map 经楼型派生赋槽——小/中/大楼 1/2/3 排；直接 Building() 构造的
        # 缺省 0 是容量关闭哨兵非可用值）
        w, u = self._world_unit()
        b = Building(id=1, pos=(0, 0), hp=30)      # garrison_slots 缺省 0
        self.assertFalse(cmd_garrison(w, u, b))

    def test_gate_dead_building_rejected(self):
        # ③ 塌楼收口（伪代码 :1248 未列——§F4 :768-771 同款判据；留痕可推翻）：
        # hp<=0 楼已出 world.buildings，驻入产生永不可达引用且白吃隐蔽加成
        w, u = self._world_unit()
        b = Building(id=1, pos=(0, 0), hp=0, garrison_slots=3)
        w.buildings.append(b)
        self.assertFalse(cmd_garrison(w, u, b))
        self.assertEqual(b.garrisoned, [])

    def test_no_distance_gate(self):
        # 伪代码 :1248-1250 仅兵种+容量两门、无距离门——本锚固化「全场遥控驻楼可达」
        # 现行为（命令即挂引用无贴近校验；留痕待发起人确认是否补门）
        w, u = self._world_unit(pos=(0, 0))
        b = Building(id=1, pos=(990000, 990000), hp=30, garrison_slots=1)
        self.assertTrue(cmd_garrison(w, u, b))
        self.assertIs(u.elements[0].garrison_in, b)

    def test_multi_element_unit_occupies_one_platoon_slot(self):
        # 2026-10-06 发起人拍板：容量按排（单位数）计、按单位整体判一次再全体
        # 塞入——双班排=1 排：slots=1 仍整体塞入（garrisoned=2 元素），第二个
        # 单位拒入；原「元素计数超容缺口」随拍板消解
        w, u1 = self._world_unit(RECON_PLATOON_TPL)
        u2 = add_unit(w, make_unit(w, RECON_PLATOON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        self.assertTrue(cmd_garrison(w, u1, b))
        self.assertEqual(len(b.garrisoned), 2)             # 双班全入=1 排
        self.assertFalse(cmd_garrison(w, u2, b))           # 第 2 排拒入
        self.assertTrue(all(e.garrison_in is b for e in u1.elements))

    def test_bidirectional_refs_written(self):
        # :1250 字面：e.garrison_in=building + building.garrisoned.append(e) 双向
        w, u = self._world_unit()
        b = Building(id=1, pos=(5000, 0), hp=30, garrison_slots=2)
        self.assertTrue(cmd_garrison(w, u, b))
        e = u.elements[0]
        self.assertIs(e.garrison_in, b)
        self.assertEqual(b.garrisoned, [e])
        self.assertEqual(e.pos, (0, 0))                    # 驻楼不写 e.pos（伪代码无此写点）

    def test_re_garrison_preserves_invariant(self):
        # 换楼驻入：伪代码 :1250 直覆盖未及旧楼条目——本实现同步移除保双向不变式
        # e.garrison_in=b ⇔ e∈b.garrisoned（登记在案）
        w, u = self._world_unit()
        b1 = Building(id=1, pos=(1000, 0), hp=30, garrison_slots=1)
        b2 = Building(id=2, pos=(2000, 0), hp=30, garrison_slots=1)
        self.assertTrue(cmd_garrison(w, u, b1))
        self.assertTrue(cmd_garrison(w, u, b2))
        self.assertEqual(b1.garrisoned, [])
        self.assertIs(u.elements[0].garrison_in, b2)
        self.assertEqual(b2.garrisoned, [u.elements[0]])


class TestGarrisonDispatch(unittest.TestCase):
    """GarrisonCmd/UnGarrisonCmd 分派支（本块前丢弃——现真调用）。"""

    def test_garrison_cmd_via_command_queue(self):
        w = make_world(11)
        u = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        w.buildings.append(b)
        queue_command(w, GarrisonCmd(unit=u, building=b))
        consume_commands(w, CONFIG)
        self.assertIs(u.elements[0].garrison_in, b)

    def test_garrison_cmd_rejected_still_consumed(self):
        # 拒令不抛不错峰——FIFO 丢弃（consume_commands 命令驱动口径）
        w = make_world(11)
        u = add_unit(w, make_unit(w, PLAIN_INF_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        w.buildings.append(b)
        queue_command(w, GarrisonCmd(unit=u, building=b))
        consume_commands(w, CONFIG)
        self.assertIsNone(u.elements[0].garrison_in)
        self.assertEqual(w.command_queue, [])

    def test_un_garrison_cmd_via_command_queue(self):
        w = make_world(11)
        u = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(5000, 5000), hp=30, garrison_slots=1)
        self.assertTrue(cmd_garrison(w, u, b))
        queue_command(w, UnGarrisonCmd(unit=u))
        consume_commands(w, CONFIG)
        self.assertIsNone(u.elements[0].garrison_in)
        self.assertEqual(b.garrisoned, [])


class TestGarrisonEffects(unittest.TestCase):
    """驻楼效果面（既有接线经真命令写侧复核）：隐蔽+3 合取式 / 命中面 REAR /
    楼内射击照常 / 楼内可被直射选定（后两者=伪代码无门，锚定现状）。"""

    def test_stealth_add_with_flag_and_garrison(self):
        # 拍板默认 +3.0 级（garrison_stealth_add_x10=30）：base 5 → 50+30=80
        # （无其他乘区/加成：不移动/无渗透/无伏击/无暴露）
        w = make_world(13)
        u = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        self.assertEqual(effective_stealth_x10(CONFIG, u), 50)
        self.assertTrue(cmd_garrison(w, u, b))
        self.assertEqual(effective_stealth_x10(CONFIG, u), 80)

    def test_stealth_conjunction_requires_flag(self):
        # AMB-02 合取式负锚：驻楼引用在手但无 CAN_GARRISON 位 → 不加成
        # （方案5 短路——非步兵卡不因引用残留白吃加成）
        w = make_world(13)
        u = add_unit(w, make_unit(w, PLAIN_INF_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        u.elements[0].garrison_in = b            # 手写引用（该模板进不了楼——负锚专用）
        self.assertEqual(effective_stealth_x10(CONFIG, u), 50)

    def test_facing_rear_garrisoned(self):
        # compute_hit_facing 覆盖序首位：驻楼恒 REAR（v1.6 ⑨A「受击判定简化[按尾甲]」）
        w = make_world(13)
        tgt = add_unit(w, make_unit(w, GAR_ARMORED_TPL, 1, 1, (0, 5000)))
        te = tgt.elements[0]
        b = Building(id=1, pos=(0, 5000), hp=30, garrison_slots=1)
        self.assertTrue(cmd_garrison(w, tgt, b))
        for approach in (0, 45, 90, 180, 270):   # 任意入射角皆 REAR
            self.assertIs(compute_hit_facing(te, approach, CONFIG), Facing.REAR)

    def test_resolve_hit_rear_anchor_via_command(self):
        # 积分锚（同 test_ground_combat 口径）：南射本为 FRONT 中段 5 伤
        # （pen6<front8、6*2>=8 → (54−32)*1000//40=550‰ → 10*550//1000=5），
        # 驻楼强制 REAR（armor 3、pen 6>=3 → 1000‰ → 10 伤）
        w = make_world(13)
        shooter = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (0, 0)))
        tgt = add_unit(w, make_unit(w, GAR_ARMORED_TPL, 1, 1, (0, 5000)))
        te = tgt.elements[0]
        b = Building(id=1, pos=(0, 5000), hp=30, garrison_slots=1)
        w.buildings.append(b)
        self.assertTrue(cmd_garrison(w, tgt, b))
        resolve_hit(w, mk_proj(w, shooter.elements[0], KE6, dest=te.pos,
                               pos=(0, 0), hit_target=te))
        self.assertEqual(te.hp_current, 20 - 10)            # REAR 满伤（非 FRONT 5）

    def test_garrisoned_shooter_fires_normally(self):
        # 楼内射击=照常直射无修正（伪代码无驻楼射击门）：fire_permitted 九门无驻楼门，
        # 弹丸起点仍 e.pos（驻楼不写 pos）
        w = make_world(13)
        shooter = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (3000, 0)))
        enemy = add_unit(w, make_unit(w, PLAIN_INF_TPL, 1, 1, (3000, 5000)))
        b = Building(id=1, pos=(3000, 0), hp=30, garrison_slots=1)
        self.assertTrue(cmd_garrison(w, shooter, b))
        e, ws = shooter.elements[0], shooter.elements[0].weapon_states[0]
        begin_aim(e, ws, enemy.elements[0], CONFIG)        # aim 0 → timer=max(1,0)=1
        ws.timer = 0
        finish_aim(w, e, ws, CONFIG)
        self.assertIs(ws.state, WState.RELOADING)          # 照常发射
        self.assertEqual(ws.ammo_left, 9)
        self.assertEqual(len(w.projectiles), 1)
        self.assertEqual(w.projectiles[0].pos, e.pos)      # 起点仍 e.pos（未被楼改写）

    def test_garrisoned_target_selectable(self):
        # 楼内可被直射选定：select_target 候选门无驻楼排除（伪代码无此门——
        # 驻楼防御价值=隐蔽+3 与 REAR 命中面，非免选定）
        w = make_world(13)
        shooter = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        tgt = add_unit(w, make_unit(w, PLAIN_INF_TPL, 1, 1, (5000, 0)))
        tgt.spotted_mask |= 1 << 0                         # 我方（队0）已发现
        b = Building(id=1, pos=(5000, 0), hp=30, garrison_slots=1)
        tgt.elements[0].garrison_in = b                    # 手写引用（负锚模板进不了楼）
        b.garrisoned.append(tgt.elements[0])
        picked = select_target(w, shooter.elements[0],
                               shooter.elements[0].weapon_states[0])
        self.assertIs(picked, tgt.elements[0])


class TestUnGarrison(unittest.TestCase):
    """§F6 :1253-1255 出楼：无资格门 / WHERE 过滤 / 楼旁落位。"""

    def test_clears_refs_and_repositions(self):
        # 双向引用清 + e.pos=楼旁落位（偏移未定标取楼锚同点位——destroy_element
        # 车毁旁落位同款登记）
        w = make_world(17)
        u = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(7000, 7000), hp=30, garrison_slots=1)
        self.assertTrue(cmd_garrison(w, u, b))
        cmd_un_garrison(w, u)
        e = u.elements[0]
        self.assertIsNone(e.garrison_in)
        self.assertEqual(b.garrisoned, [])
        self.assertEqual(e.pos, (7000, 7000))              # 楼旁落位=楼锚同点位

    def test_noop_when_not_garrisoned(self):
        # :1253 无资格门：未驻楼单位出楼=无操作（无异常、pos 不动）
        w = make_world(17)
        u = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (123, 456)))
        cmd_un_garrison(w, u)
        self.assertIsNone(u.elements[0].garrison_in)
        self.assertEqual(u.elements[0].pos, (123, 456))

    def test_where_filter_only_garrisoned_elements(self):
        # WHERE garrison_in != NULL：仅驻楼元素清+落位，未驻楼元素不动
        # （部分驻楼态经手写构造——cmd_garrison 恒整单位进驻）
        w = make_world(17)
        u = add_unit(w, make_unit(w, RECON_PLATOON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(9000, 0), hp=30, garrison_slots=2)
        e0, e1 = u.elements
        e0.garrison_in = b
        b.garrisoned.append(e0)
        cmd_un_garrison(w, u)
        self.assertIsNone(e0.garrison_in)
        self.assertEqual(e0.pos, (9000, 0))
        self.assertIsNone(e1.garrison_in)
        self.assertEqual(e1.pos, (0, 0))                   # 未驻楼元素不被落位改写


class TestBidirectionalCleanup(unittest.TestCase):
    """双向清理三向（写侧经真命令）：元素毁 / 楼塌 / 移动自动出楼。"""

    def test_element_destroyed_clears_both_sides(self):
        # destroy_element（combat.py:182-185 既有）经 cmd_garrison 写侧复核
        w = make_world(19)
        u = add_unit(w, make_unit(w, RECON_PLATOON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=2)
        self.assertTrue(cmd_garrison(w, u, b))
        apply_damage(w, u.elements[0], 999)
        self.assertEqual(b.garrisoned, [u.elements[0]])    # 幸存班仍在楼
        apply_damage(w, u.elements[0], 999)
        self.assertEqual(b.garrisoned, [])                 # 末班毁→楼清
        self.assertEqual(u.elements, [])

    def test_building_collapse_clears_and_damages(self):
        # 楼塌（collapse_building 既有）：清引用+cfg.building_collapse_dmg 结算
        # （§D.0 :76 默认 0=无伤害；本锚拨非零档验伤害链——带伤步兵走医疗链由
        # apply_damage 唯一入口承接）
        w = make_world(19)
        u = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        w.buildings.append(b)
        self.assertTrue(cmd_garrison(w, u, b))
        cfg = BalanceConfig(building_collapse_dmg=3)
        hit_building(w, b, 30, cfg)                        # hp 30−30<=0 → 塌
        self.assertNotIn(b, w.buildings)
        self.assertEqual(b.garrisoned, [])
        self.assertIsNone(u.elements[0].garrison_in)
        self.assertEqual(u.elements[0].hp_current, 10 - 3)
        self.assertIn(u, w.await_resupply)                 # 带伤登记（医疗链承接）

    def test_move_order_auto_exits_building(self):
        # GAP-02（§F5 :994-995）：移动令即自动出楼——整链 queue_command→
        # consume_commands→system_move_dispatch（movement 出楼清理本块改按身份移除）
        w = make_world(19)
        u = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        w.buildings.append(b)
        queue_command(w, GarrisonCmd(unit=u, building=b))
        queue_command(w, MoveCmd(unit=u, path=[(100, 0)]))
        world_tick(w, CONFIG)
        self.assertIsNone(u.elements[0].garrison_in)       # 移动即出楼
        self.assertEqual(b.garrisoned, [])
        self.assertNotEqual(u.pos, (0, 0))                 # 移动令确已推进（速度档1=25/tick）


class TestCollapseCasualties(unittest.TestCase):
    """塌楼驻军处置分级（PB-57 塌楼验收块，2026-10-06）：§F5 :537-541 清引用后
    apply_damage 唯一入口——hp<=0 走 destroy_element 完整连带（死亡处置）、存活
    带伤步兵进 await_resupply 医疗链（D012 口径：楼塌伤步兵由医疗链承接——引注勘正 2026-10-06）、
    全灭 unregister+alive=False+尸体清扫（world_tick :1439 尾部过滤）。
    伪代码口径无「弹出落位」写点（驻楼本不写 pos、塌楼亦不写——元素保持原位）。
    零掷骰：塌楼伤害=cfg.building_collapse_dmg 固定整数（§D.0 :76），不掷骰、
    不开新通道（ask「若规格要求掷骰伤害则新开 PCG32 通道并升级确认」——规格
    无掷骰要求，零掷骰档成立）。"""

    def test_collapse_damage_kills_squad_full_wipe(self):
        # 恰死档：hp10 − dmg10 = 0 → destroy_element → 全灭 alive=False →
        # world_tick 尾部尸体清扫出 world.units（引用三向清理之尸体清扫侧）
        w = make_world(31)
        u = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        w.buildings.append(b)
        self.assertTrue(cmd_garrison(w, u, b))
        before = channel_states(w)
        cfg = BalanceConfig(building_collapse_dmg=10)
        hit_building(w, b, 30, cfg)                        # 30−30<=0 → 塌
        self.assertEqual(channel_states(w), before)        # 塌楼链零掷骰
        self.assertNotIn(b, w.buildings)
        self.assertEqual(b.garrisoned, [])
        self.assertEqual(u.elements, [])                   # 唯一班恰死=全灭
        self.assertFalse(u.alive)                          # 一命制（无回圈无退款）
        self.assertIn(u, w.units)                          # 尸体清扫在 world_tick 尾部
        world_tick(w, cfg)                                 # ——本拍出表：
        self.assertNotIn(u, w.units)
        self.assertEqual(len(w.units), 0)

    def test_collapse_mixed_casualties_snapshot_iteration(self):
        # 混合处置（快照迭代安全）：同楼双班一发塌落伤害——班0 hp10 恰死（destroy_
        # element 中途改 garrisoned）、班1 hp16 带伤存活进医疗链；collapse 逐驻军
        # 先清 garrison_in 再结算（combat.py :350-353）⇒ 班0 死亡路径的 destroy_
        # element 驻楼清理分支见 garrison_in=None 跳过、终局 garrisoned.clear() 兜底
        w = make_world(31)
        u = add_unit(w, make_unit(w, MIXED_PLATOON_TPL, 0, 0, (0, 0)))
        e0, e1 = u.elements
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        w.buildings.append(b)
        self.assertTrue(cmd_garrison(w, u, b))             # 双班单位驻入 slots=1
        before = channel_states(w)
        cfg = BalanceConfig(building_collapse_dmg=10)
        hit_building(w, b, 30, cfg)
        self.assertEqual(channel_states(w), before)        # 零掷骰
        self.assertNotIn(b, w.buildings)
        self.assertEqual(b.garrisoned, [])
        self.assertEqual(u.elements, [e1])                 # 班0 死、班1 在编
        self.assertIsNone(e1.garrison_in)                  # 幸存班清引用（无弹出落位）
        self.assertEqual(e1.hp_current, 16 - 10)           # 带伤存活
        self.assertEqual(e1.pos, (0, 0))                   # 塌楼不写 pos（伪代码无写点）
        self.assertTrue(u.alive)                           # 非全灭
        self.assertIn(u, w.await_resupply)                 # 带伤步兵登记（医疗链承接）
        self.assertIn(u, w.units)

    def test_collapse_default_cfg_zero_damage(self):
        # §D.0 :76 默认 0=塌楼无伤害（数值章节定标前既定缺省）：引用照清、驻军无伤
        w = make_world(31)
        u = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        w.buildings.append(b)
        self.assertTrue(cmd_garrison(w, u, b))
        self.assertEqual(CONFIG.building_collapse_dmg, 0)  # 表 pin（缺省档锚）
        hit_building(w, b, 30, CONFIG)
        self.assertNotIn(b, w.buildings)
        self.assertEqual(u.elements[0].hp_current, 10)     # 无伤存活
        self.assertIsNone(u.elements[0].garrison_in)
        self.assertEqual(b.garrisoned, [])
        self.assertNotIn(u, w.await_resupply)              # 无缺口不登记


class TestDemoMapGarrison(unittest.TestCase):
    """apply_map 装配楼 × 楼型派生驻楼容量（2026-10-06 拍板：小/中/大楼=1/2/3 排）。"""

    def test_demo_map_buildings_garrisonable_to_cfg_slots(self):
        # 示范图 5 锚装配（PB-58 数据位，footprint 2500<5000=小楼 1 排）：首班进驻
        # 成功、次班容量拒——整链 data/gen JSON→apply_map→cmd_garrison
        w = make_world(23)
        apply_map(w, load_demo_map(CONFIG), CONFIG)
        self.assertEqual(len(w.buildings), 5)
        u1 = add_unit(w, make_unit(w, RECON_TPL, 0, 0, w.buildings[0].pos))
        u2 = add_unit(w, make_unit(w, RECON_TPL, 0, 0, w.buildings[0].pos))
        self.assertTrue(cmd_garrison(w, u1, w.buildings[0]))
        self.assertFalse(cmd_garrison(w, u2, w.buildings[0]))   # 小楼 1 排恰满
        for b in w.buildings:
            self.assertEqual(b.garrison_slots, CONFIG.building_garrison_slots_small)


class TestBuildingSizeSlots(unittest.TestCase):
    """2026-10-06 发起人拍板：小/中/大楼=1/2/3 个步兵排（按单位数计）。"""

    def test_size_slots_derivation(self):
        # footprint 阈值派生（5000/10000cm 占位入表；≥上限即下一档）
        from sovs.sim.map_loader import garrison_slots_for
        self.assertEqual(garrison_slots_for(2500), 1)     # 小楼（demo 5 锚同档）
        self.assertEqual(garrison_slots_for(4999), 1)
        self.assertEqual(garrison_slots_for(5000), 2)     # 中楼
        self.assertEqual(garrison_slots_for(9999), 2)
        self.assertEqual(garrison_slots_for(10000), 3)    # 大楼

    def test_medium_building_holds_two_platoons(self):
        # 中楼（2 排）：双班排（1 排）+单班排（1 排）入、第三排拒
        w = make_world(9)
        u1 = add_unit(w, make_unit(w, RECON_PLATOON_TPL, 0, 0, (0, 0)))
        u2 = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        u3 = add_unit(w, make_unit(w, RECON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=2)
        self.assertTrue(cmd_garrison(w, u1, b))
        self.assertTrue(cmd_garrison(w, u2, b))
        self.assertFalse(cmd_garrison(w, u3, b))
        self.assertEqual(len(b.garrisoned), 3)            # 元素计=2+1（容量按排判）

    def test_real_cards_garrison_flag(self):
        # 2026-10-06 发起人拍板：步兵/侦察/军官政委类可驻楼——真卡管线端到端
        # （SU_RECON 侦察班卡带 CAN_GARRISON 可入；SU_T3485 坦克无位拒入）
        from sovs.sim.card_loader import load_library
        lib = load_library("data/gen/cards_ground.v1.json")
        w = make_world(11)
        recon = add_unit(w, make_unit(w, lib["SU_RECON"].unit_template, 0, 0, (0, 0)))
        tank = add_unit(w, make_unit(w, lib["SU_T3485"].unit_template, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=3)
        self.assertTrue(cmd_garrison(w, recon, b))
        self.assertFalse(cmd_garrison(w, tank, b))


class TestGarrisonZeroDice(unittest.TestCase):
    """命令处理零掷骰（契约：命令层不触任何 PCG32 通道）。"""

    def test_garrison_un_garrison_channels_untouched(self):
        w = make_world(29)
        u = add_unit(w, make_unit(w, RECON_PLATOON_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 0), hp=30, garrison_slots=1)
        w.buildings.append(b)
        before = channel_states(w)
        queue_command(w, GarrisonCmd(unit=u, building=b))
        queue_command(w, UnGarrisonCmd(unit=u))
        consume_commands(w, CONFIG)
        after = channel_states(w)
        self.assertEqual(after, before)
        self.assertIsNone(u.elements[0].garrison_in)       # 两令确已落地


if __name__ == "__main__":
    unittest.main()
