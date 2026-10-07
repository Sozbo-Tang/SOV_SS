"""system_combat ③ 对地分流（§F4 :674-917）：fire_permitted 六门 / select_target
评分与候选门 / ground_direct 射界门+rotate_step（R-09/AMB-5）/ indirect_role 自卫
直射（R-15/M20）/ finish_aim 地面出口（M4/G32）/ select_profile（R-11/M16 钨芯）/
fire_direct（acc 乘区/渗透清零⑦A/AMB-14 不喂声测）/ process_fire_mission·fire_at
（R-13 三形式/R-14 ⌈N/2⌉/R-16 校射⑩A·AMB-06/声测痕迹 C4）/ cmd_fire_mission。
⑤块（2026-10-02）：resolve_hit 地面命中（装甲面链/CRIT 暴击通道/面压制）、
resolve_sniper_hit（R-02/SNIPER 通道/掩护旁表/tally）、resolve_melee_hit
（AMB-05 绕装甲/GAP-13 光环）、resolve_blast（AMB-01 衰减/烟弹 B4/建筑）、
apply_damage/destroy_element 完整体（R-07 连带/带伤登记）、system_projectiles
分派支接线。

锚点全部手推写死（配置表值/评分算式/取样公式/通道纪律），不自证；掷骰通道纪律：
直射=HIT+SCATTER、曲射=SCATTER only（AIR/CRIT/SNIPER/SPOT/SONAR/ECONOMY 不触碰）；
确定性双跑：同 seed 两 world 逐 tick 比指纹（fingerprint 范式同 test_integration）。"""
import unittest

from sovs.sim.air import AircraftInstance, AltTier
from sovs.sim.combat import (aura_bonus_bp, hit_building, resolve_blast,
                             resolve_hit, resolve_melee_hit, resolve_sniper_hit)
from sovs.sim.geom import approach_deg_of, angle_diff
from sovs.sim.movement import rotate_step
from sovs.sim.sensing import (detection_range_cm, effective_stealth_x10)
from sovs.sim.tick import (IntelCircle, Projectile, add_unit, aa_try_engage,
                           begin_aim, cmd_attack, cmd_fire_mission,
                           cmd_set_element_mode, cmd_set_stance,
                           cmd_toggle_ambush, finish_aim, fire_at,
                           fire_direct, fire_permitted, ground_direct,
                           indirect_role, make_unit, make_world,
                           process_fire_mission, queue_command, select_profile,
                           select_target, system_combat, system_projectiles,
                           world_tick)
from sovs.sim.tick import (AttackCmd, SetModeCmd, SetStanceCmd,
                           ToggleAmbushCmd)
from sovs.sim.tick import MoveCmd
from sovs.sim.types import (AltProfile, Armor, Aura, AuraKind, Building, DamageType,
                            DeployState, ElementTemplate, ElementType, FireMission,
                            FireMissionForm, MarkLevel, Mode, MountRequest,
                            MovementClass, MoveMode, SalvoMode, SelfDefenseProfile,
                            SmokeZone, Stance, TargetDomain, TowPair, TowState,
                            Trajectory, UnitFlag, UnitTemplate, UnitType,
                            WeaponTemplate, WState)
from sovs.sim.tables import BalanceConfig, CONFIG

# ── 合成模板（测试用，不对应真实卡；template_id 5xx/6xx 段）──

# 直射坦克：必中（accuracy 10000 且无压制/crit）、aim 3、reload 20、弹速 100（在途可见）
CANNON = WeaponTemplate(name="CANNON", damage_type=DamageType.KE, pen_max=5,
                        damage=10, max_range_cm=50000, aim_time_ticks=3,
                        reload_time_ticks=20, ammo_base=10, salvo=1, dispersion_cm=100,
                        accuracy_base_bp=10000, projectile_speed_cm_tick=100)
TANK_ELEM = ElementTemplate(element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                            hp_max=20, weapons=(CANNON,))
TANK_TPL = UnitTemplate(
    template_id=501, name="tank", category=2, cost=100, element_templates=(TANK_ELEM,),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3, movement_class=MovementClass.TRACK)

# 无炮塔歼击车（R-09 载体）：射界 ±30°、转向 30°/s → 3°/tick（AMB-5 换算）
TD_CANNON = WeaponTemplate(name="TD", damage=12, max_range_cm=40000, aim_time_ticks=2,
                           reload_time_ticks=30, ammo_base=8, accuracy_base_bp=10000,
                           projectile_speed_cm_tick=100)
TD_ELEM = ElementTemplate(element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                          hp_max=18, fire_arc_deg=30, weapons=(TD_CANNON,))
TD_TPL = UnitTemplate(
    template_id=502, name="td", category=2, cost=90, element_templates=(TD_ELEM,),
    optics_ground_cm=20000, stealth_base=5, speed_tier=2,
    movement_class=MovementClass.TRACK, turn_rate_deg=30)

# 榴弹炮连（R-13 载体）：3 门、needs_deployed、BALLISTIC、alt_profile HE 档、salvo 1
HOW = WeaponTemplate(name="HOW", damage_type=DamageType.HE, damage=6, blast_radius_cm=2500,
                     max_range_cm=200000, min_range_cm=25000, dispersion_cm=0,
                     aim_time_ticks=0, reload_time_ticks=10, ammo_base=6, salvo=1,
                     accuracy_base_bp=10000, needs_deployed=True,
                     projectile_speed_cm_tick=100, trajectory=Trajectory.BALLISTIC,
                     alt_profile=AltProfile(damage=12, blast_radius_cm=3500))
HOW_ELEM = ElementTemplate(element_type=ElementType.GUN, unit_type=UnitType.INFANTRY,
                           hp_max=6, weapons=(HOW,))
BATT_TPL = UnitTemplate(
    template_id=503, name="how battery", category=3, cost=85,
    element_templates=(HOW_ELEM, HOW_ELEM, HOW_ELEM), optics_ground_cm=20000,
    stealth_base=4, speed_tier=1, movement_class=MovementClass.FOOT,
    deploy_time_ticks=30, mode_set=(1 << Mode.DIRECT) | (1 << Mode.INDIRECT))

# 迫击炮（R-15 载体）：主武器带 self_defense 自卫档
MORTAR = WeaponTemplate(name="MORTAR", damage_type=DamageType.HE, damage=5,
                        max_range_cm=150000, min_range_cm=10000, dispersion_cm=0,
                        aim_time_ticks=0, reload_time_ticks=15, ammo_base=8,
                        accuracy_base_bp=10000, projectile_speed_cm_tick=100,
                        trajectory=Trajectory.BALLISTIC,
                        self_defense=SelfDefenseProfile(max_range_cm=4000,
                                                        accuracy_mult_bp=6000))
MORTAR_ELEM = ElementTemplate(element_type=ElementType.GUN, unit_type=UnitType.INFANTRY,
                              hp_max=5, weapons=(MORTAR,))
MORTAR_TPL = UnitTemplate(
    template_id=504, name="mortar", category=3, cost=60,
    element_templates=(MORTAR_ELEM,), optics_ground_cm=20000, stealth_base=4,
    speed_tier=1, movement_class=MovementClass.FOOT,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.INDIRECT))

# 步兵（威胁值/候选门载体）
RIFLE = WeaponTemplate(name="RIFLE", damage=1, max_range_cm=10000, ammo_base=10,
                       reload_time_ticks=10, salvo=1)
MG = WeaponTemplate(name="MG", damage=4, max_range_cm=10000, ammo_base=10,
                    reload_time_ticks=20, salvo=5)
SQUAD_ELEM = ElementTemplate(element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
                             hp_max=10, weapons=(RIFLE,))
MG_SQUAD_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                                unit_type=UnitType.INFANTRY, hp_max=10, weapons=(MG,))
INF_TPL = UnitTemplate(
    template_id=505, name="rifle squad", category=1, cost=20,
    element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)
MG_INF_TPL = UnitTemplate(
    template_id=506, name="mg squad", category=1, cost=25,
    element_templates=(MG_SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)

# 狙击（⑲A 载体：combat_style=2）
SNIPER_W = WeaponTemplate(name="SNIPER", combat_style=2, damage=1, max_range_cm=40000,
                          aim_time_ticks=50, reload_time_ticks=100, ammo_base=5,
                          accuracy_base_bp=10000, projectile_speed_cm_tick=100)
SNIPER_ELEM = ElementTemplate(element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
                              hp_max=4, weapons=(SNIPER_W,))
SNIPER_TPL = UnitTemplate(
    template_id=507, name="sniper", category=1, cost=30,
    element_templates=(SNIPER_ELEM,), optics_ground_cm=20000, stealth_base=6,
    speed_tier=1, movement_class=MovementClass.FOOT)

# 近战（渗透清零⑦A 载体：combat_style=1）
MELEE_W = WeaponTemplate(name="BAYONET", combat_style=1, damage=2, min_range_cm=0,
                         max_range_cm=5000, aim_time_ticks=0, reload_time_ticks=5,
                         ammo_base=99, accuracy_base_bp=10000,
                         projectile_speed_cm_tick=100)
MELEE_ELEM = ElementTemplate(element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
                             hp_max=8, weapons=(MELEE_W,))
MELEE_TPL = UnitTemplate(
    template_id=508, name="cavalry", category=1, cost=35,
    element_templates=(MELEE_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=3, movement_class=MovementClass.HORSE)

# 装甲目标（狙击剔除/选弹载体）
ARMORED_ELEM = ElementTemplate(
    element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=20,
    armor_ke=Armor(front=8, side=5, rear=3, top=1),
    armor_he=Armor(front=6, side=4, rear=2, top=1), weapons=())
ARMORED_TPL = UnitTemplate(
    template_id=509, name="heavy tank", category=2, cost=120,
    element_templates=(ARMORED_ELEM,), optics_ground_cm=20000, stealth_base=4,
    speed_tier=2, movement_class=MovementClass.TRACK)

# 双职炮（选弹载体）：KE 主炮 pen_max=4 < 目标 front 8、alt HE 档、钨芯 (+3, 2 发)
DUAL_W = WeaponTemplate(name="DUAL", damage_type=DamageType.KE, pen_min=2, pen_max=4,
                        damage=9, max_range_cm=60000, aim_time_ticks=2,
                        reload_time_ticks=25, ammo_base=7, dispersion_cm=100,
                        accuracy_base_bp=10000, projectile_speed_cm_tick=100,
                        restricted_profiles=((2, 3),),
                        alt_profile=AltProfile(damage=7, blast_radius_cm=2000))
DUAL_ELEM = ElementTemplate(element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                            hp_max=15, weapons=(DUAL_W,))
DUAL_TPL = UnitTemplate(
    template_id=510, name="dual gun", category=2, cost=80,
    element_templates=(DUAL_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=2, movement_class=MovementClass.TRACK)

# 80% 精度炮（R-12 首击乘区锚点载体：+伏击 13000bp → 10400 必中）
G80 = WeaponTemplate(name="G80", damage=5, max_range_cm=50000, aim_time_ticks=0,
                     reload_time_ticks=50, ammo_base=10, accuracy_base_bp=8000,
                     projectile_speed_cm_tick=100, dispersion_cm=100)
ACC80_TPL = UnitTemplate(
    template_id=513, name="acc80", category=2, cost=50,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=10,
                                       weapons=(G80,)),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=2,
    movement_class=MovementClass.TRACK)

# ── PB-56 批① 余三命令载体（2026-10-06；template_id 523-525 段）──

# 伏击炮班（⑮A canAmbush 位合成置位——现役 0 卡置位〔实测 ground_cards.csv〕，
# 数据侧脱节登记；stealth 3 → 伏击 ×2 恰 60 不触顶，乘区形状可锚）
AMBUSH_ACC80_TPL = UnitTemplate(
    template_id=523, name="ambush squad", category=1, cost=50,
    element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                       unit_type=UnitType.INFANTRY, hp_max=10,
                                       weapons=(G80,)),),
    optics_ground_cm=20000, stealth_base=3, speed_tier=1,
    movement_class=MovementClass.FOOT, flags=UnitFlag.CAN_AMBUSH)
# 运载卡（TRANSPORT 位——④ 卸客分支载体）
TRANSPORT_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                                 unit_type=UnitType.MECH, hp_max=15, seats=2)
TRANSPORT_TPL = UnitTemplate(
    template_id=524, name="apc", category=2, cost=70,
    element_templates=(TRANSPORT_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=2, movement_class=MovementClass.WHEEL,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.TRANSPORT))
# 对空炮（SetStance 对空豁免锚载体：AIR 武器+air_ceiling）
AA_STANCE_W = WeaponTemplate(name="AAG", target_mask=TargetDomain.AIR,
                             damage_type=DamageType.KE, max_range_cm=60000,
                             aim_time_ticks=3, reload_time_ticks=50, ammo_base=10)
AA_STANCE_TPL = UnitTemplate(
    template_id=525, name="aa stance", category=4, cost=60,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=10,
        weapons=(AA_STANCE_W,),),),
    optics_ground_cm=20000, optics_air_cm=60000, air_ceiling=AltTier.HIGH,
    stealth_base=5, speed_tier=1, movement_class=MovementClass.TRACK)

# 位掩码变体（frozen 模板——测试以独立模板表达 mode_set/flags 组合）
TANK_TOW_TPL = UnitTemplate(                       # 含 TOW 位（⑤ 门载体）
    template_id=518, name="tank tow", category=2, cost=100,
    element_templates=(TANK_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=3, movement_class=MovementClass.TRACK,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.TOW))
TANK_CARGO_TPL = UnitTemplate(                     # 含 CARGO 位（⑥ 门载体）
    template_id=519, name="tank cargo", category=2, cost=100,
    element_templates=(TANK_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=3, movement_class=MovementClass.TRACK,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.CARGO))
TANK_MARK_TPL = UnitTemplate(                      # requiresMark（犀牛门载体）
    template_id=520, name="rhino", category=2, cost=100,
    element_templates=(TANK_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=2, movement_class=MovementClass.TRACK,
    flags=UnitFlag.REQUIRES_MARK)
MORTAR_NOBIT_TPL = UnitTemplate(                   # 无 INDIRECT 位（方案3 静态门）
    template_id=521, name="mortar nobit", category=3, cost=60,
    element_templates=(MORTAR_ELEM,), optics_ground_cm=20000, stealth_base=4,
    speed_tier=1, movement_class=MovementClass.FOOT,
    mode_set=1 << Mode.DIRECT)
BATT_NOBIT_TPL = UnitTemplate(                     # 无 INDIRECT 位（:689 尾部门）
    template_id=522, name="how nobit", category=3, cost=85,
    element_templates=(HOW_ELEM, HOW_ELEM, HOW_ELEM), optics_ground_cm=20000,
    stealth_base=4, speed_tier=1, movement_class=MovementClass.FOOT,
    deploy_time_ticks=30, mode_set=1 << Mode.DIRECT)

# ── ⑤块模板（§F1 结算载体；template_id 52x/53x 段）──

# 固定穿深 KE 炮（pen_min=pen_max——距离插值恒等，锚点与落点距离解耦）
KE6 = WeaponTemplate(name="KE6", damage_type=DamageType.KE, pen_min=6, pen_max=6,
                     damage=10, max_range_cm=50000, projectile_speed_cm_tick=100,
                     blast_radius_cm=2500, suppression_power=10)
KE3 = WeaponTemplate(name="KE3", damage_type=DamageType.KE, pen_min=3, pen_max=3,
                     damage=10, max_range_cm=50000, projectile_speed_cm_tick=100)
SHOOTER_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                               unit_type=UnitType.MECH, hp_max=20, weapons=(KE6,))
SHOOTER_TPL = UnitTemplate(
    template_id=523, name="shooter", category=2, cost=60,
    element_templates=(SHOOTER_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=2, movement_class=MovementClass.TRACK)
# 窄射界装甲载体（R-09 rotating→SIDE 命中面载体）
ARC_ARMOR_ELEM = ElementTemplate(
    element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=20,
    fire_arc_deg=60, armor_ke=Armor(front=8, side=5, rear=3, top=1),
    armor_he=Armor(front=6, side=4, rear=2, top=1))
ARC_ARMOR_TPL = UnitTemplate(
    template_id=524, name="arc armor", category=2, cost=100,
    element_templates=(ARC_ARMOR_ELEM,), optics_ground_cm=20000, stealth_base=4,
    speed_tier=2, movement_class=MovementClass.TRACK)

# 榴弹（爆破载体）：HE、damage 20、blast 4000（span 8000）、power 10
HE20 = WeaponTemplate(name="HE20", damage_type=DamageType.HE, damage=20,
                      blast_radius_cm=4000, max_range_cm=200000,
                      projectile_speed_cm_tick=100, suppression_power=10,
                      crit_mod_permille=1000)  # 字段保留标预留（D071 全拆后零消费者——口子，恢复即用）
HOW20_ELEM = ElementTemplate(element_type=ElementType.GUN, unit_type=UnitType.INFANTRY,
                             hp_max=6, weapons=(HE20,))
HOW20_TPL = UnitTemplate(
    template_id=525, name="how20", category=3, cost=85,
    element_templates=(HOW20_ELEM,), optics_ground_cm=20000, stealth_base=4,
    speed_tier=1, movement_class=MovementClass.FOOT)
SMOKE_W = WeaponTemplate(name="SMK", damage_type=DamageType.SMOKE, damage=0,
                         blast_radius_cm=0, max_range_cm=200000,
                         projectile_speed_cm_tick=100)
# 攻坚炮（直射建筑载体）：vs_fort ×2、blast 2500、power 10
SIEGE_W = WeaponTemplate(name="SIEGE", damage_type=DamageType.HE, damage=10,
                         vs_fort_mult_permille=2000, blast_radius_cm=2500,
                         suppression_power=10, max_range_cm=50000,
                         projectile_speed_cm_tick=100000)

# 骑兵（近战载体）：close_combat_bonus 1800、武器 damage 5/power 7、带甲步靶证绕曲线
MELEE5 = WeaponTemplate(name="SABRE", combat_style=1, damage=5, min_range_cm=0,
                        max_range_cm=5000, ammo_base=99, projectile_speed_cm_tick=100,
                        suppression_power=7)
CAVALRY_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                               unit_type=UnitType.INFANTRY, hp_max=8,
                               weapons=(MELEE5,))
CAVALRY_TPL = UnitTemplate(
    template_id=526, name="cavalry1800", category=1, cost=35,
    element_templates=(CAVALRY_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=3, movement_class=MovementClass.HORSE,
    close_combat_bonus_permille=1800)
# 带甲步靶（MELEE 绕曲线载体：armor_he 10 满甲，走 HE 曲线则 pen=0 恒 0 伤）
ARMOURED_INF_ELEM = ElementTemplate(
    element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY, hp_max=10,
    armor_he=Armor(front=10, side=10, rear=10, top=10))
ARMOURED_INF_TPL = UnitTemplate(
    template_id=527, name="arm inf", category=1, cost=25,
    element_templates=(ARMOURED_INF_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)
# 政委（MELEE 光环 +1500bp，半径 5000）
COMMISSAR_TPL = UnitTemplate(
    template_id=528, name="commissar", category=1, cost=30,
    element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT,
    aura=Aura(kind=AuraKind.MELEE, bonus_bp=1500, radius_cm=5000))
# 指挥班组（singleSquadCard：狙击概率灭排载体）
CMD_SQUAD_TPL = UnitTemplate(
    template_id=529, name="cmd squad", category=1, cost=20,
    element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT,
    flags=UnitFlag.SINGLE_SQUAD_CARD)
# 快弹坦克（分派接线双跑载体：弹速 100000——发射同拍即落）
FAST_CANNON = WeaponTemplate(name="FAST", damage_type=DamageType.KE, pen_min=5,
                             pen_max=5, damage=10, max_range_cm=50000,
                             aim_time_ticks=3, reload_time_ticks=20, ammo_base=10,
                             dispersion_cm=100, accuracy_base_bp=10000,
                             projectile_speed_cm_tick=100000)
FAST_TANK_TPL = UnitTemplate(
    template_id=530, name="fast tank", category=2, cost=100,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=20,
                                       weapons=(FAST_CANNON,)),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.TRACK)
# ── PB-56 批① cmd_attack 载体（2026-10-06；§F4 :848-872 门序逐项锚）──
# 攻坚令链炮（① 建筑资格门载体，与 :235 SIEGE_W 分工——彼为 resolve_hit 结算
# 载体零 ammo/aim 槽，此为命令链载体带 aim3/reload20/ammo10）：vs_fort 2000‰
# （>1000 过门）、必中、快弹同拍落
SIEGE_CMD_W = WeaponTemplate(name="SIEGE_CMD", damage_type=DamageType.KE,
                             pen_max=5, damage=10, vs_fort_mult_permille=2000,
                             max_range_cm=50000, aim_time_ticks=3,
                             reload_time_ticks=20, ammo_base=10, salvo=1,
                             dispersion_cm=100, accuracy_base_bp=10000,
                             projectile_speed_cm_tick=100000)
SIEGE_TPL = UnitTemplate(
    template_id=531, name="siege gun", category=2, cost=100,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=20,
                                       weapons=(SIEGE_CMD_W,)),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.TRACK)
# 混装攻坚（① 门滤除非攻坚武器载体：攻坚炮+步枪同元素——对建筑仅前者过门）
SIEGE_MIX_TPL = UnitTemplate(
    template_id=532, name="siege mix", category=2, cost=110,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=20,
                                       weapons=(SIEGE_CMD_W, RIFLE)),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.TRACK)
# 犀牛（⑤ requiresMark 门载体：CANNON 同款武器+REQUIRES_MARK 位）
MARK_TANK_TPL = UnitTemplate(
    template_id=533, name="mark tank", category=2, cost=100,
    element_templates=(TANK_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=3, movement_class=MovementClass.TRACK,
    flags=UnitFlag.REQUIRES_MARK)
# 对空专用武器（② target_mask 无 GROUND 位载体）
AAONLY_W = WeaponTemplate(name="AAONLY", damage_type=DamageType.KE, damage=4,
                          target_mask=TargetDomain.AIR, max_range_cm=50000,
                          aim_time_ticks=3, reload_time_ticks=20, ammo_base=10,
                          accuracy_base_bp=10000, projectile_speed_cm_tick=100000)
AAONLY_TPL = UnitTemplate(
    template_id=534, name="aa only", category=2, cost=80,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=16,
                                       weapons=(AAONLY_W,)),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.TRACK)
# 无武装元素（target=None 超契约存活锚——循环体零执行自然无操作）
WEAPONLESS_TPL = UnitTemplate(
    template_id=535, name="weaponless", category=1, cost=10,
    element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                       unit_type=UnitType.INFANTRY, hp_max=6),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)
# 最小射程炮（⑨ 无 min_range 门锚——伪代码 :868 字面仅上限，近距手动指火放行）
MINR_CANNON = WeaponTemplate(name="MINR", damage_type=DamageType.KE, pen_max=5,
                             damage=10, min_range_cm=25000, max_range_cm=50000,
                             aim_time_ticks=3, reload_time_ticks=20,
                             ammo_base=10, accuracy_base_bp=10000,
                             projectile_speed_cm_tick=100000)
MINR_TPL = UnitTemplate(
    template_id=536, name="minr tank", category=2, cost=100,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=20,
                                       weapons=(MINR_CANNON,)),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.TRACK)
# 攻坚犀牛（⑤ 门建筑豁免载体：SIEGE 同款武器+REQUIRES_MARK 位）
MARK_SIEGE_TPL = UnitTemplate(
    template_id=537, name="mark siege", category=2, cost=110,
    element_templates=(ElementTemplate(element_type=ElementType.VEHICLE,
                                       unit_type=UnitType.MECH, hp_max=20,
                                       weapons=(SIEGE_CMD_W,)),),
    optics_ground_cm=20000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.TRACK, flags=UnitFlag.REQUIRES_MARK)
# 双炮歼击车（⑩ RETURN 语义载体：射界 30°×双武器——循环形下 rotate 后函数退出，
# 每令至多转一步 3°）
TD_DUAL_ELEM = ElementTemplate(element_type=ElementType.VEHICLE,
                               unit_type=UnitType.MECH, hp_max=18,
                               fire_arc_deg=30, weapons=(TD_CANNON, TD_CANNON))
TD_DUAL_TPL = UnitTemplate(
    template_id=538, name="td dual", category=2, cost=120,
    element_templates=(TD_DUAL_ELEM,), optics_ground_cm=20000, stealth_base=5,
    speed_tier=2, movement_class=MovementClass.TRACK, turn_rate_deg=30)


def channel_states(w):
    return {name: w.rng.rng(i).state for i, name in enumerate(
        ("HIT", "SCATTER", "SPOT", "CRIT", "SNIPER", "SONAR", "ECONOMY", "AIR"))}


def mk_proj(w, shooter_e, weapon, *, dest, pos=None, dmg_type=None, dmg=None,
            hit_target=None, will_hit=True, trajectory=Trajectory.DIRECT,
            pen_bonus=0, top_attack=False):
    """直达弹（speed=100000——pos→dest 一拍即到达，分派支/命中面单测载体；
    pos 省略=贴目标落点，传入射手位则控制 approach 入射角）。"""
    return Projectile(
        shooter=shooter_e, weapon=weapon,
        damage_type=dmg_type if dmg_type is not None else weapon.damage_type,
        damage=dmg if dmg is not None else weapon.damage,
        blast_cm=weapon.blast_radius_cm, pos=pos if pos is not None else dest,
        dest=dest, speed_cm_tick=100000, trajectory=trajectory,
        hit_target=hit_target, will_hit=will_hit, top_attack=top_attack,
        pen_bonus=pen_bonus)


class TestFirePermitted(unittest.TestCase):
    """§F4 :693-706 六门逐条（无武器特殊配置时全开=True 基线）。"""

    def _world_unit(self):
        w = make_world(3)
        u = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (0, 0)))
        return w, u, u.elements[0], u.elements[0].weapon_states[0]

    def test_baseline_all_gates_open(self):
        w, u, e, ws = self._world_unit()
        self.assertTrue(fire_permitted(w, u, e, ws))

    def test_phase_gate(self):
        w, u, e, ws = self._world_unit()
        w.phase = 0                                   # PHASE_DEPLOY：非实战（禁射门）
        self.assertFalse(fire_permitted(w, u, e, ws))

    def test_stance_gate(self):
        w, u, e, ws = self._world_unit()
        u.stance = Stance.HOLD_FIRE
        self.assertFalse(fire_permitted(w, u, e, ws))

    def test_deploy_gate(self):
        w = make_world(3)
        u = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (0, 0)))
        e, ws = u.elements[0], u.elements[0].weapon_states[0]
        self.assertTrue(ws.template.needs_deployed)   # 榴弹炮须展开
        self.assertFalse(fire_permitted(w, u, e, ws))            # MOBILE
        u.deploy_state = DeployState.DEPLOYED
        e.redeploy_needed = True                      # C3 元素粒度：被拖过未重展开
        self.assertFalse(fire_permitted(w, u, e, ws))
        e.redeploy_needed = False
        self.assertTrue(fire_permitted(w, u, e, ws))
        # 无 needs_deployed 武器不受展开门约束
        w2, u2, e2, ws2 = self._world_unit()
        u2.deploy_state = DeployState.MOBILE
        self.assertTrue(fire_permitted(w2, u2, e2, ws2))

    def test_mounted_gate(self):
        w = make_world(3)
        carrier = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (0, 0)))
        carrier_e = carrier.elements[0]
        squad = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        s = squad.elements[0]
        s.mounted_in = carrier_e                      # 班上车（载具无 mounted_armament）
        ws = s.weapon_states[0]
        self.assertFalse(fire_permitted(w, squad, s, ws))         # 步枪非车载武器

    def test_mounted_armament_weapon_permits(self):
        # mounted_armament 标记的车载 MG 空车可射击（AMB-07：须同时配入 weapons[]）
        mg = WeaponTemplate(name="HULL_MG", damage=2, max_range_cm=8000,
                            ammo_base=20, reload_time_ticks=10)
        et = ElementTemplate(element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                             hp_max=10, weapons=(mg,), mounted_armament=(mg,))
        tpl = UnitTemplate(template_id=511, name="ht", category=2, cost=50,
                           element_templates=(et,), optics_ground_cm=10000,
                           stealth_base=5, speed_tier=2,
                           movement_class=MovementClass.TRACK)
        w = make_world(3)
        carrier = add_unit(w, make_unit(w, tpl, 0, 0, (0, 0)))
        ce, cws = carrier.elements[0], carrier.elements[0].weapon_states[0]
        self.assertTrue(fire_permitted(w, carrier, ce, cws))      # 未载班：本就许可
        squad = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        squad.elements[0].mounted_in = ce
        self.assertTrue(fire_permitted(w, carrier, ce, cws))      # ④ 门：车载 MG 放行

    def test_tow_gate(self):
        w = make_world(3)
        u = add_unit(w, make_unit(w, TANK_TOW_TPL, 0, 0, (0, 0)))   # 模板含 TOW 位
        e, ws = u.elements[0], u.elements[0].weapon_states[0]
        e.towed = TowState.TOWING
        self.assertFalse(fire_permitted(w, u, e, ws))              # 牵引侧禁射
        e.towed = TowState.TOWED
        self.assertFalse(fire_permitted(w, u, e, ws))              # 被拖侧禁射
        e.towed = TowState.NONE
        self.assertTrue(fire_permitted(w, u, e, ws))
        # 方案13：模板无 TOW 位则不问（双态悬置不拦截）——TANK_TPL 仅 DIRECT 位
        u2 = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (0, 0)))
        e2, ws2 = u2.elements[0], u2.elements[0].weapon_states[0]
        e2.towed = TowState.TOWED
        self.assertTrue(fire_permitted(w, u2, e2, ws2))
        e2.towed = TowState.NONE

    def test_d065_mode_gate(self):
        w = make_world(3)
        u = add_unit(w, make_unit(w, TANK_CARGO_TPL, 0, 0, (0, 0)))  # D065 三模式卡
        e, ws = u.elements[0], u.elements[0].weapon_states[0]
        e.mode = Mode.CARGO
        self.assertFalse(fire_permitted(w, u, e, ws))              # 载货状态不作战
        e.mode = Mode.TRANSPORT
        self.assertFalse(fire_permitted(w, u, e, ws))
        e.mode = Mode.DIRECT
        self.assertTrue(fire_permitted(w, u, e, ws))


class TestSelectTarget(unittest.TestCase):
    """§F4 :708-729 候选门 + 评分（damage*salvo + threat − dist//100，并列取列表序首）。"""

    def _shooter_world(self):
        w = make_world(5)
        u = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (0, 0)))
        return w, u, u.elements[0], u.elements[0].weapon_states[0]

    def test_threat_value_dps(self):
        # :727-729 damage*salvo*10000//MAX(1,reload)：MG=4*5*10000//20=10000；
        # RIFLE=1*1*10000//10=1000；无武装元素（MAX 空集）=0
        w = make_world(5)
        mg = add_unit(w, make_unit(w, MG_INF_TPL, 1, 1, (0, 0)))
        from sovs.sim.tick import threat_value
        self.assertEqual(threat_value(mg.elements[0]), 10000)
        inf = add_unit(w, make_unit(w, INF_TPL, 1, 1, (0, 0)))
        self.assertEqual(threat_value(inf.elements[0]), 1000)
        mech = add_unit(w, make_unit(w, ARMORED_TPL, 1, 1, (0, 0)))   # 无武器
        self.assertEqual(threat_value(mech.elements[0]), 0)

    def test_score_picks_high_threat_despite_distance(self):
        # 手推：w.damage*salvo=10*1=10；远 MG 班（dist 10000）：10+10000−100=9910；
        # 近步枪班（dist 5000）：10+100−50=1060 → 选 MG 班
        w, u, e, ws = self._shooter_world()
        near = add_unit(w, make_unit(w, INF_TPL, 1, 1, (5000, 0)))
        far = add_unit(w, make_unit(w, MG_INF_TPL, 1, 1, (10000, 0)))
        near.spotted_mask = far.spotted_mask = 1
        self.assertIs(select_target(w, e, ws), far.elements[0])

    def test_tie_takes_first_in_list_order(self):
        # 同武器同距离 → 同分 → world.units 序首（确定性）
        w, u, e, ws = self._shooter_world()
        first = add_unit(w, make_unit(w, INF_TPL, 1, 1, (5000, 0)))
        second = add_unit(w, make_unit(w, INF_TPL, 1, 1, (-5000, 0)))
        first.spotted_mask = second.spotted_mask = 1
        self.assertIs(select_target(w, e, ws), first.elements[0])

    def test_unspotted_excluded(self):
        w, u, e, ws = self._shooter_world()
        add_unit(w, make_unit(w, INF_TPL, 1, 1, (5000, 0)))        # 无队 0 位
        self.assertIsNone(select_target(w, e, ws))

    def test_mounted_squad_excluded(self):
        # M10/G23：车载班不可被直接命中
        w, u, e, ws = self._shooter_world()
        mounted = add_unit(w, make_unit(w, INF_TPL, 1, 1, (5000, 0)))
        mounted.spotted_mask = 1
        mounted.elements[0].mounted_in = u.elements[0]
        self.assertIsNone(select_target(w, e, ws))

    def test_sniper_excludes_mech(self):
        # ⑲A：狙击候选剔除 MECH 元素（保留 INFANTRY 候选）
        w = make_world(5)
        s = add_unit(w, make_unit(w, SNIPER_TPL, 0, 0, (0, 0)))
        e, ws = s.elements[0], s.elements[0].weapon_states[0]
        self.assertEqual(ws.template.combat_style, 2)
        mech = add_unit(w, make_unit(w, ARMORED_TPL, 1, 1, (10000, 0)))
        mech.spotted_mask = 1
        inf = add_unit(w, make_unit(w, INF_TPL, 1, 1, (20000, 0)))
        inf.spotted_mask = 1
        self.assertIs(select_target(w, e, ws), inf.elements[0])

    def test_requires_mark_gate(self):
        # 犀牛门（第8轮）：shooter 单位 REQUIRES_MARK 置位 → 目标须 mark_level ≥ SPOTTED
        w = make_world(5)
        u = add_unit(w, make_unit(w, TANK_MARK_TPL, 0, 0, (0, 0)))
        e, ws = u.elements[0], u.elements[0].weapon_states[0]
        self.assertTrue(u.template.flags & UnitFlag.REQUIRES_MARK)
        tgt = add_unit(w, make_unit(w, INF_TPL, 1, 1, (5000, 0)))
        tgt.spotted_mask = 1
        tgt.mark_level = MarkLevel.NONE
        self.assertIsNone(select_target(w, e, ws))
        tgt.mark_level = MarkLevel.SPOTTED
        self.assertIs(select_target(w, e, ws), tgt.elements[0])

    def test_range_window(self):
        w, u, e, ws = self._shooter_world()                          # max 50000
        near = add_unit(w, make_unit(w, INF_TPL, 1, 1, (3000, 0)))   # 3000 < max：可及
        near.spotted_mask = 1
        self.assertIs(select_target(w, e, ws), near.elements[0])
        far = add_unit(w, make_unit(w, MG_INF_TPL, 1, 1, (60000, 0)))
        far.spotted_mask = 1                                          # 威胁更高但超程
        self.assertIs(select_target(w, e, ws), near.elements[0])
        # min_range 门：min>0 武器（曲射自卫同理走 select_target）剔除近靶
        w2 = make_world(5)
        u2 = add_unit(w2, make_unit(w2, MORTAR_TPL, 0, 0, (0, 0)))
        e2, ws2 = u2.elements[0], u2.elements[0].weapon_states[0]
        self.assertEqual(ws2.template.min_range_cm, 10000)
        close = add_unit(w2, make_unit(w2, INF_TPL, 1, 1, (5000, 0)))
        close.spotted_mask = 1
        self.assertIsNone(select_target(w2, e2, ws2))


class TestRotateStep(unittest.TestCase):
    """§F5 :1051-1058 + AMB-5 换算（MAX(1, turn_rate_deg//10)）+ M3/B04 rotating 重算。"""

    def _unit(self, turn_rate_deg=30, fire_arc=30):
        tpl = UnitTemplate(
            template_id=512, name="rot", category=2, cost=50,
            element_templates=(ElementTemplate(
                element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                hp_max=10, fire_arc_deg=fire_arc, weapons=(TD_CANNON,)),),
            optics_ground_cm=20000, stealth_base=5, speed_tier=2,
            movement_class=MovementClass.TRACK, turn_rate_deg=turn_rate_deg)
        w = make_world(3)
        return add_unit(w, make_unit(w, tpl, 0, 0, (0, 0)))

    def test_step_conversion_and_direction(self):
        u = self._unit(turn_rate_deg=30)                 # 30°/s → 3°/tick
        e = u.elements[0]
        e.facing = 90
        rotate_step(e, 180)                              # diff=+90 → 90+3=93
        self.assertEqual(e.facing, 93)
        self.assertTrue(e.rotating)                      # |angle_diff(180,93)|=87 > 30

    def test_snap_within_step(self):
        u = self._unit(turn_rate_deg=50)                 # 5°/tick
        e = u.elements[0]
        e.facing = 176
        rotate_step(e, 180)                              # |diff|=4 ≤ 5 → 直接到位
        self.assertEqual(e.facing, 180)
        self.assertFalse(e.rotating)                     # 入射界内不计转向中（M3/B04）

    def test_max_guard_low_turn_rate(self):
        u = self._unit(turn_rate_deg=5)                  # 5//10=0 → MAX(1,·)=1（AMB-5 防锁死）
        e = u.elements[0]
        e.facing = 90
        rotate_step(e, 180)
        self.assertEqual(e.facing, 91)

    def test_rotate_enters_arc_clears_rotating(self):
        u = self._unit(turn_rate_deg=30, fire_arc=60)
        e = u.elements[0]
        e.facing = 140
        rotate_step(e, 180)                              # 143；|37| ≤ 60 → rotating False
        self.assertEqual(e.facing, 143)
        self.assertFalse(e.rotating)


class TestGroundDirectFlow(unittest.TestCase):
    """ground_direct → begin_aim → finish_aim 地面出口 → fire_direct 全链（world_tick）。"""

    def test_aim_fire_sequence_and_projectile_fields(self):
        # 手推时序：tick1 begin_aim（timer=3）→ tick2/3 递减 → tick4 fire_direct：
        # RELOADING(20)、ammo 10→9、弹丸携 hit_target/will_hit=True、dest=tgt.pos
        # （jitter_small 零幅——acc 10000 必中且命中点贴目标）、reveal_timer=w.reveal=0
        w = make_world(7)
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (100000, 100000)))
        inf = add_unit(w, make_unit(w, INF_TPL, 1, 1, (130000, 100000)))   # dist 30000
        inf.spotted_mask = 1
        ws = tank.elements[0].weapon_states[0]
        world_tick(w)
        self.assertIs(ws.state, WState.AIMING)
        self.assertEqual(ws.timer, 3)
        for _ in range(3):
            world_tick(w)
        self.assertIs(ws.state, WState.RELOADING)                       # tick4 已发射
        self.assertEqual(ws.timer, 20)
        self.assertEqual(ws.ammo_left, 9)
        self.assertIs(ws.target, inf.elements[0])
        self.assertEqual(len(w.projectiles), 1)
        p = w.projectiles[0]
        self.assertIs(p.hit_target, inf.elements[0])
        self.assertTrue(p.will_hit)
        self.assertEqual(p.dest, inf.elements[0].pos)                   # 零幅 jitter
        self.assertEqual(p.pos, (100100, 100000))      # 出生点+1 步（100cm/tick 同拍推进）
        self.assertIs(p.trajectory, Trajectory.DIRECT)
        self.assertEqual(p.pen_bonus, 0)
        self.assertEqual(w.sound_tracks, [])                            # AMB-14 不喂声测
        self.assertIn(tank, w.await_resupply)                           # :811 弹药缺口登记

    def test_hold_fire_blocks_engagement(self):
        w = make_world(7)
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (100000, 100000)))
        inf = add_unit(w, make_unit(w, INF_TPL, 1, 1, (130000, 100000)))
        inf.spotted_mask = 1
        tank.stance = Stance.HOLD_FIRE
        ws = tank.elements[0].weapon_states[0]
        for _ in range(6):
            world_tick(w)
        self.assertIs(ws.state, WState.READY)
        self.assertEqual(ws.ammo_left, 10)
        self.assertEqual(w.projectiles, [])

    def test_out_of_arc_rotates_before_aim(self):
        # R-09：歼击车 facing 90（东）、敌正北（want 180）→ 射界 30° 外先转车体
        # 手推：diff 90、3°/tick；diff>30 才转——tick1 93、tick20 150（rotating）；
        # tick21 起 diff=30 ≤ 30 入射界即 begin_aim（不再转车、facing 停 150）
        w = make_world(7)
        td = add_unit(w, make_unit(w, TD_TPL, 0, 0, (200000, 200000)))
        inf = add_unit(w, make_unit(w, INF_TPL, 1, 1, (200000, 180000)))   # 正北 20000cm
        inf.spotted_mask = 1
        e, ws = td.elements[0], td.elements[0].weapon_states[0]
        e.facing = 90
        world_tick(w)
        self.assertEqual(e.facing, 93)                      # 90 + 3（朝 180 方向）
        self.assertTrue(e.rotating)
        self.assertIs(ws.state, WState.READY)               # 不瞄准
        for _ in range(19):
            world_tick(w)                                   # 共 20 tick
        self.assertEqual(e.facing, 150)                     # 90+3×20
        self.assertFalse(e.rotating)   # 末拍转完恰达边界：|150−180|=30 ≤ 30（M3/B04 重算）
        world_tick(w)                                       # tick21：diff 30 ≤ 30 入射界
        self.assertEqual(e.facing, 150)                     # 不再转车（已在射界内）
        self.assertFalse(e.rotating)
        self.assertIs(ws.state, WState.AIMING)              # 入射界即开始瞄准
        self.assertIs(ws.target, inf.elements[0])

    def test_unspotted_no_engagement(self):
        w = make_world(7)
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (100000, 100000)))
        add_unit(w, make_unit(w, INF_TPL, 1, 1, (130000, 100000)))   # 未标记 spotted
        ws = tank.elements[0].weapon_states[0]
        for _ in range(6):
            world_tick(w)
        self.assertIs(ws.state, WState.READY)

    def test_direct_fire_channels(self):
        # 通道纪律：直射只碰 HIT/SCATTER（:287 范式——shot 前取一次 rng 对象循环内消费）
        w = make_world(11)
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (100000, 100000)))
        inf = add_unit(w, make_unit(w, INF_TPL, 1, 1, (130000, 100000)))
        inf.spotted_mask = 1
        before = channel_states(w)
        for _ in range(4):
            world_tick(w)                                   # tick4 发射
        after = channel_states(w)
        self.assertNotEqual(after["HIT"], before["HIT"])
        self.assertNotEqual(after["SCATTER"], before["SCATTER"])
        for name in ("SPOT", "CRIT", "SNIPER", "SONAR", "ECONOMY", "AIR"):
            self.assertEqual(after[name], before[name], name)

    def test_ambush_shot_bonus_pushes_acc_over_certain(self):
        # R-12 首击：base 8000 × ambush 13000 //10000 = 10400 > 10000 → 必中；
        # 无加成时 8000 < 10000 非必然——两场景对照锚定乘区项
        w = make_world(13)
        u = add_unit(w, make_unit(w, ACC80_TPL, 0, 0, (100000, 100000)))
        add_unit(w, make_unit(w, INF_TPL, 1, 1, (130000, 100000))).spotted_mask = 1
        u.ambush_shot_bonus = True
        world_tick(w)                                       # tick1 begin_aim（timer≥1）
        world_tick(w)                                       # tick2 到期 → fire_direct
        self.assertEqual(len(w.projectiles), 1)
        self.assertTrue(w.projectiles[0].will_hit)          # 10400bp 必中
        self.assertFalse(u.ambush_shot_bonus)               # :830 打完清

    def test_infiltration_cleared_only_melee_sniper(self):
        # ⑦A：狙击/近战开火清渗透身份；普通自卫开火不清
        w = make_world(13)
        melee = add_unit(w, make_unit(w, MELEE_TPL, 0, 0, (100000, 100000)))
        add_unit(w, make_unit(w, INF_TPL, 1, 1, (104000, 100000))).spotted_mask = 1
        tgt = w.units[1].elements[0]
        melee.infiltration_timer = 600
        fire_direct(w, melee.elements[0], melee.elements[0].weapon_states[0], tgt)
        self.assertEqual(melee.infiltration_timer, 0)       # 近战开火即清
        w2 = make_world(13)
        tank = add_unit(w2, make_unit(w2, TANK_TPL, 0, 0, (100000, 100000)))
        inf2 = add_unit(w2, make_unit(w2, INF_TPL, 1, 1, (130000, 100000)))
        inf2.spotted_mask = 1
        tank.infiltration_timer = 600
        fire_direct(w2, tank.elements[0], tank.elements[0].weapon_states[0],
                    inf2.elements[0])
        self.assertEqual(tank.infiltration_timer, 600)      # 普通开火不清

    def test_self_defense_reset_after_fire(self):
        # R-15：use_self_defense 发射即复位（疑点④）
        w = make_world(13)
        m = add_unit(w, make_unit(w, MORTAR_TPL, 0, 0, (100000, 100000)))
        inf = add_unit(w, make_unit(w, INF_TPL, 1, 1, (103000, 100000)))
        inf.spotted_mask = 1
        e, ws = m.elements[0], m.elements[0].weapon_states[0]
        e.mode = Mode.INDIRECT
        world_tick(w)                                       # tick1 自卫 begin_aim（≥1）
        self.assertIs(ws.state, WState.AIMING)
        self.assertTrue(ws.use_self_defense)
        world_tick(w)                                       # tick2 到期 → fire_direct
        self.assertIs(ws.state, WState.RELOADING)
        self.assertFalse(ws.use_self_defense)               # 复位（疑点④）
        self.assertEqual(ws.ammo_left, 7)
        self.assertEqual(len(w.projectiles), 1)
        self.assertIs(w.projectiles[0].hit_target, inf.elements[0])


class TestFinishAimBuildingGuard(unittest.TestCase):
    """§F4 :766-769 失的守卫 Building 支（PB-57 建筑实体块，2026-10-06）：
    活楼（hp>0）放行续 fire_permitted+fire_direct（建筑支 HE 默认档/pen_bonus=0/
    R-01 标记豁免——fire_direct 既有接线核对）；塌楼（hp<=0，已出 world.buildings）
    失的转 READY 不耗弹——与「目标已除名」（B9 元素判据）分离。玩家令入口
    AttackCmd 分派原待 PB-56 批①，此处 begin_aim 直挂 ws.target 验证链体
    （begin_aim ws.target: object 兼容）〔**批① 已落地 2026-10-06——命令链
    全链锚见 TestCmdAttack**〕。"""

    def _world_with_building(self, hp, cfg=CONFIG):
        w = make_world(7)
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (100000, 100000)))
        b = Building(id=1, pos=(103000, 100000), hp=hp)     # dist 3000 ≤ 50000
        w.buildings.append(b)
        return w, tank.elements[0], b

    def test_live_building_passes_guard_and_fires(self):
        # 守卫放行：finish_aim → fire_permitted（九门全过）→ fire_direct 建筑支
        w, e, b = self._world_with_building(hp=30)
        ws = e.weapon_states[0]
        begin_aim(e, ws, b, CONFIG)                          # timer=3（aim 3×10000）
        self.assertIs(ws.target, b)
        ws.timer = 0
        finish_aim(w, e, ws, CONFIG)
        self.assertIs(ws.state, WState.RELOADING)            # 未被误判失的
        self.assertEqual(ws.timer, 20)                       # reload 20×10000
        self.assertEqual(ws.ammo_left, 9)                    # 耗弹 1
        self.assertEqual(len(w.projectiles), 1)
        p = w.projectiles[0]
        self.assertIs(p.hit_target, b)
        self.assertIs(p.damage_type, DamageType.HE)          # 建筑档案=HE 默认档
        self.assertEqual(p.damage, 10)                       # w.damage（CANNON KE→HE 档）
        self.assertEqual(p.pen_bonus, 0)
        self.assertTrue(p.will_hit)                          # acc 10000 必中
        self.assertEqual(b.hp, 30)                           # 未到达不掉血
        self.assertIn(b, w.buildings)

    def test_projectile_arrival_reduces_building_hp(self):
        # 全链：fire_direct 弹丸 → system_projectiles 到达 → resolve_hit 建筑支
        # ×vs_fort（CANNON vs_fort 1000‰）→ hit_building 掉血（30−10=20 未塌）
        w, e, b = self._world_with_building(hp=30)
        ws = e.weapon_states[0]
        begin_aim(e, ws, b, CONFIG)
        ws.timer = 0
        finish_aim(w, e, ws, CONFIG)
        for _ in range(40):                                  # dist 3000/速 100=30 拍
            system_projectiles(w, CONFIG)
        self.assertEqual(w.projectiles, [])
        self.assertEqual(b.hp, 30 - 10)
        self.assertIn(b, w.buildings)                        # hp>0 未塌不出表

    def test_collapsed_building_is_lost_target(self):
        # 瞄准窗口内楼塌（hp<=0 已出表）→ 失的转 READY 不耗弹（:768-769 补支）
        w, e, b = self._world_with_building(hp=30)
        ws = e.weapon_states[0]
        begin_aim(e, ws, b, CONFIG)
        ws.timer = 0
        hit_building(w, b, 30, CONFIG)                       # 30−30=0 → 塌楼出表
        self.assertNotIn(b, w.buildings)
        finish_aim(w, e, ws, CONFIG)
        self.assertIs(ws.state, WState.READY)
        self.assertEqual(ws.ammo_left, 10)                   # 不耗弹
        self.assertEqual(w.projectiles, [])                  # 不发射
        self.assertIs(ws.target, b)                          # 引用不越权清（READY 自涵）


class TestCmdAttack(unittest.TestCase):
    """§F4 :848-872 AttackCmd 处理体（PB-56 批① 作战链命令块，2026-10-06）：
    门序①-⑪ 逐项锚 + 玩家令直射拆楼全链（命令→瞄准→弹丸→掉血→塌楼——PB-57
    建筑实体块④ 留待项的命令侧闭环）+ 元素目标既有链回归 + 分派链 + 零掷骰。
    武器选择=循环案（勘察 decisionPoint#1 默认裁决可推翻）：遍历 weapon_states
    逐武器过门、过门者各自 begin_aim（ground_direct :736-747 同构）。节拍手推：
    令拍 t1 consume→begin_aim(3)，① t1-t3 递减，t3 ④ 到期发射，⑤ 快弹
    （速 100000>程 3000）同拍到达结算；RELOADING(20) 于 t23 ① 归零，t24 复令。"""

    def _siege_world(self, hp=40):
        w = make_world(7)
        u = add_unit(w, make_unit(w, SIEGE_TPL, 0, 0, (100000, 100000)))
        b = Building(id=1, pos=(103000, 100000), hp=hp)     # dist 3000 ≤ 50000
        w.buildings.append(b)
        return w, u.elements[0], b

    def _pair(self, shooter_tpl, target_tpl, spotted=1,
              tgt_pos=(103000, 100000)):
        w = make_world(7)
        s = add_unit(w, make_unit(w, shooter_tpl, 0, 0, (100000, 100000)))
        t = add_unit(w, make_unit(w, target_tpl, 1, 1, tgt_pos))
        t.spotted_mask = spotted
        return w, s.elements[0], t.elements[0]

    # ── ① 建筑资格门（攻坚武器专属）──

    def test_gate_building_vs_fort_boundary(self):
        # >1000 过门 begin_aim；<=1000（含 WeaponTemplate 缺省 1000=现役全档，
        # ground_weapons.csv 实测无 >1000 值——数据侧脱节登记）REJECT
        w, e, b = self._siege_world()
        ws = e.weapon_states[0]
        cmd_attack(w, e, b, CONFIG)
        self.assertIs(ws.state, WState.AIMING)               # SIEGE vs_fort=2000
        self.assertIs(ws.target, b)
        self.assertEqual(ws.timer, 3)
        w2 = make_world(7)
        t = add_unit(w2, make_unit(w2, TANK_TPL, 0, 0, (100000, 100000)))
        b2 = Building(id=1, pos=(103000, 100000), hp=40)
        w2.buildings.append(b2)
        ws2 = t.elements[0].weapon_states[0]                 # CANNON vs_fort 缺省 1000
        cmd_attack(w2, t.elements[0], b2, CONFIG)
        self.assertIs(ws2.state, WState.READY)               # <=1000 REJECT

    def test_gate_building_multi_weapon_filter(self):
        # 循环案：攻坚炮过门、同元素步枪被 ① 自然滤除（保持 READY 不冒充）
        w = make_world(7)
        u = add_unit(w, make_unit(w, SIEGE_MIX_TPL, 0, 0, (100000, 100000)))
        b = Building(id=1, pos=(103000, 100000), hp=40)
        w.buildings.append(b)
        e = u.elements[0]
        cmd_attack(w, e, b, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.AIMING)   # SIEGE 过门
        self.assertIs(e.weapon_states[0].target, b)
        self.assertIs(e.weapon_states[1].state, WState.READY)    # RIFLE 滤除

    # ── ②-⑥ 目标资格门（Element 支）──

    def test_gate_ground_mask(self):
        # ② target_mask 无 GROUND 位（对空专用武器）REJECT
        w, e, tgt = self._pair(AAONLY_TPL, TANK_TPL)
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.READY)

    def test_gate_sniper_vs_mech(self):
        # ③ ⑲A：狙击指火 MECH 元素 REJECT；INFANTRY 放行
        w, e, tgt = self._pair(SNIPER_TPL, TANK_TPL)
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.READY)
        w2, e2, tgt2 = self._pair(SNIPER_TPL, INF_TPL)
        cmd_attack(w2, e2, tgt2, CONFIG)
        self.assertIs(e2.weapon_states[0].state, WState.AIMING)
        self.assertEqual(e2.weapon_states[0].timer, 50)      # aim 50×10000

    def test_gate_not_spotted(self):
        # ④ M5/B01：spotted_mask 不含我队位（队0 位=bit0）REJECT
        w, e, tgt = self._pair(TANK_TPL, TANK_TPL, spotted=0)
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.READY)
        w2, e2, tgt2 = self._pair(TANK_TPL, TANK_TPL, spotted=1)
        cmd_attack(w2, e2, tgt2, CONFIG)
        self.assertIs(e2.weapon_states[0].state, WState.AIMING)

    def test_gate_requires_mark(self):
        # ⑤ 犀牛门：requiresMark 且 target.mark_level<SPOTTED REJECT；SPOTTED 放行
        w, e, tgt = self._pair(MARK_TANK_TPL, INF_TPL)
        self.assertEqual(tgt.unit.mark_level, MarkLevel.NONE)
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.READY)
        tgt.unit.mark_level = MarkLevel.SPOTTED
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.AIMING)

    def test_gate_requires_mark_building_exempt(self):
        # ⑤ 建筑豁免（:860-863——建筑无标记，犀牛攻坚照常可指）
        w = make_world(7)
        u = add_unit(w, make_unit(w, MARK_SIEGE_TPL, 0, 0, (100000, 100000)))
        b = Building(id=1, pos=(103000, 100000), hp=40)
        w.buildings.append(b)
        cmd_attack(w, u.elements[0], b, CONFIG)
        self.assertIs(u.elements[0].weapon_states[0].state, WState.AIMING)

    def test_gate_mounted_squad(self):
        # ⑥ M10/G23：车载班不可被指火
        w, e, tgt = self._pair(TANK_TPL, INF_TPL)
        tgt.mounted_in = e                                     # 任意非空引用
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.READY)

    # ── ⑦-⑨ 武器状态/许可/射程门 ──

    def test_gate_ready_and_ammo(self):
        # ⑦ 非 READY 或 ammo<=0 REJECT
        w, e, tgt = self._pair(TANK_TPL, TANK_TPL)
        ws = e.weapon_states[0]
        ws.state = WState.RELOADING
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(ws.state, WState.RELOADING)              # 未被覆盖
        ws.state = WState.READY
        ws.ammo_left = 0
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(ws.state, WState.READY)

    def test_gate_fire_permitted_stance(self):
        # ⑧ 姿态门既有接线（fire_permitted ② HOLD_FIRE——不约束对空，对地手动
        # 指火同受约束）
        w, e, tgt = self._pair(TANK_TPL, TANK_TPL)
        e.unit.stance = Stance.HOLD_FIRE
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.READY)
        e.unit.stance = Stance.WEAPONS_FREE
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.AIMING)

    def test_gate_max_range(self):
        # ⑨ 超 max_range（50000）REJECT——dist 60000
        w, e, tgt = self._pair(TANK_TPL, TANK_TPL, tgt_pos=(160000, 100000))
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.READY)

    def test_no_min_range_gate(self):
        # ⑨ 无 min_range 门（:868 字面仅上限，宽于 select_target 的 min≤d≤max
        # ——近距手动指火放行，照字面落地留痕）：MINR min 25000、dist 3000 仍瞄准
        w, e, tgt = self._pair(MINR_TPL, TANK_TPL)
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.AIMING)

    # ── ⑩ 射界门 R-09（转车体+RETURN）与 ⑪ begin_aim ──

    def test_gate_arc_in_and_out(self):
        # 射界内（正北 approach 0=facing）直接 begin_aim；射界外（正南 180，
        # 角差 180>30）转车体不瞄准
        w, e, tgt = self._pair(TD_TPL, TANK_TPL, tgt_pos=(100000, 103000))
        cmd_attack(w, e, tgt, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.AIMING)
        w2, e2, tgt2 = self._pair(TD_TPL, TANK_TPL, tgt_pos=(100000, 97000))
        ws2 = e2.weapon_states[0]
        cmd_attack(w2, e2, tgt2, CONFIG)
        self.assertIs(ws2.state, WState.READY)                 # 未瞄准
        self.assertIs(ws2.target, None)
        self.assertEqual(abs(angle_diff(0, e2.facing)), 3)     # 转一步 3°（AMB-5）
        self.assertTrue(e2.rotating)                           # M3/B04 重算标志

    def test_gate_arc_return_single_rotate_step(self):
        # ⑩ RETURN 语义（循环形=函数退出）：双武器射界外至多转一步——若按
        # continue 逐武器再转将一步 6°，此处锚死单步
        w, e, tgt = self._pair(TD_DUAL_TPL, TANK_TPL, tgt_pos=(100000, 97000))
        cmd_attack(w, e, tgt, CONFIG)
        self.assertEqual(abs(angle_diff(0, e.facing)), 3)      # 恰一步
        self.assertIs(e.weapon_states[0].state, WState.READY)
        self.assertIs(e.weapon_states[1].state, WState.READY)

    # ── 全链：玩家令直射拆楼（命令→瞄准→弹丸→掉血→塌楼）──

    def test_building_demolition_full_chain(self):
        # SIEGE×vs_fort 2000：每发 10×2000//1000=20 伤（MECH 射手 squad_hp_factor
        # 10000）。节拍手推：t1 受令 AIMING(3)→t3 ④ 发射、⑤ 快弹同拍命中 hp 40→20；
        # RELOADING(20) t23 ① 归零、t24 复令→t26 第二发 20-20=0 塌楼出表
        w, e, b = self._siege_world(hp=40)
        ws = e.weapon_states[0]
        events, collapse_tick = [], None
        for _ in range(60):
            if b not in w.buildings:
                break
            if ws.state is WState.READY:
                queue_command(w, AttackCmd(element=e, target=b))
            hp_before = b.hp
            world_tick(w)
            if b in w.buildings and b.hp != hp_before:
                events.append((w.tick, b.hp))
            if b not in w.buildings and collapse_tick is None:
                collapse_tick = w.tick
        self.assertEqual(events, [(3, 20)])                    # 首发命中拍/血
        self.assertEqual(collapse_tick, 26)                    # 塌楼拍
        self.assertNotIn(b, w.buildings)                       # 出表（collapse）
        self.assertTrue(b.hp <= 0)
        self.assertEqual(ws.ammo_left, 8)                      # 两发耗弹
        self.assertEqual(w.projectiles, [])                    # 无滞留弹丸

    def test_element_target_chain_regression(self):
        # 元素目标既有链回归（命令入口→begin_aim→finish_aim→fire_direct→
        # system_projectiles→resolve_hit）：FAST 必中、MECH 无甲 mult 1000‰、
        # D071 全拆后 MECH 命中零暴击零掷——t3 同拍命中 hp 20-10=10
        # 〔勘正 2026-10-07：原注「crit_mod 0 零 CRIT 掷」与模板事实不符——
        # FAST_CANNON 未设 crit_mod_permille=默认 1000、TANK_TPL 为 MECH →
        # 旧链 prob=MIN(10000,10×1200×1000//1000)=10000 每发必掷 CRIT；现全拆
        # 后零掷（断言本就不查 crit 故当时仍绿——存量滞文本轮勘正）〕
        w, e, tgt = self._pair(FAST_TANK_TPL, TANK_TPL)
        ws = e.weapon_states[0]
        queue_command(w, AttackCmd(element=e, target=tgt))
        world_tick(w)                                          # t1 受令
        self.assertIs(ws.state, WState.AIMING)
        world_tick(w)                                          # t2
        world_tick(w)                                          # t3 发射+命中
        self.assertIs(ws.state, WState.RELOADING)
        self.assertEqual(ws.ammo_left, 9)
        self.assertEqual(w.projectiles, [])
        self.assertEqual(tgt.hp_current, 20 - 10)
        self.assertTrue(tgt.unit.alive)

    # ── 分派链与零掷骰 ──

    def test_dispatch_via_queue_command(self):
        # AttackCmd 分派支：queue_command→consume_commands→cmd_attack（真调用）
        w, e, b = self._siege_world()
        queue_command(w, AttackCmd(element=e, target=b))
        self.assertEqual(len(w.command_queue), 1)
        world_tick(w)
        self.assertEqual(w.command_queue, [])
        self.assertIs(e.weapon_states[0].state, WState.AIMING)
        self.assertIs(e.weapon_states[0].target, b)

    def test_zero_rng_command_processing(self):
        # 零掷骰：命令受理全门序+begin_aim 纯整数——直调与分派整拍八通道不动
        w, e, b = self._siege_world()
        rng0 = [r.state for r in w.rng._rngs]
        cmd_attack(w, e, b, CONFIG)
        self.assertIs(e.weapon_states[0].state, WState.AIMING)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)
        w2, e2, b2 = self._siege_world()
        rng0b = [r.state for r in w2.rng._rngs]
        queue_command(w2, AttackCmd(element=e2, target=b2))
        world_tick(w2)                                         # t1：受令+①递减，无发射
        self.assertEqual([r.state for r in w2.rng._rngs], rng0b)

    def test_none_target_with_weapons_contract_violation(self):
        # 契约外输入（§D.7 契约 target=Element|Building）的另一半：有武器元素
        # × target=None 在门序触 AttributeError=程序员错误口径（与未知命令类型
        # 抛 TypeError 同款）——2026-10-06 批①评审#1 补锚：docstring 声明的
        # 契约外行为此前零覆盖（无武器元素存活路径已由下方 noop 用例锚定）
        w, e, tgt = self._pair(FAST_TANK_TPL, TANK_TPL)
        with self.assertRaises(AttributeError):
            cmd_attack(w, e, None)

    def test_none_target_weaponless_noop(self):
        # target=None 超 §D.7 契约（Element|Building）：无武器元素循环体零执行
        # 自然无操作存活（test_economy_phase drain 用例同款契约锚）
        w = make_world(7)
        u = add_unit(w, make_unit(w, WEAPONLESS_TPL, 0, 0, (100000, 100000)))
        e = u.elements[0]
        queue_command(w, AttackCmd(element=e, target=None))
        world_tick(w)
        self.assertEqual(w.command_queue, [])
        self.assertEqual(u.pos, (100000, 100000))
        self.assertIs(u.stance, Stance.WEAPONS_FREE)


# ── PB-56 批① 余三命令（2026-10-06）：SetMode 写点序①-⑦ / ToggleAmbush R-12 开关 /
#    SetStance 最小写点——消费侧锚 + 分派链 + 零掷骰 ──

class TestCmdSetMode(unittest.TestCase):
    """§F6 :1193-1213 SetModeCmd 处理体（PB-56 批① 作战链命令块·余三命令，
    2026-10-06）：写点序①-⑦ 逐项锚——mode_set 资格门/TOW 解挂（GAP-24 元素级）/
    CARGO 卸货清零（:1196-1197 伪代码字段 supply_rounds/supply_medical 不存在，
    按 2026-10-03 一池拍板换 supply_weight_g——destroy_element 同款先例）/
    TRANSPORT 逐班卸客（v1.3 审查#3 双向清+旁落位）/m≠TRANSPORT 清挂起请求
    （I-19）/M21 元素级半清除（e.mode 先行赋值）。cmd_fire_mission 双门第二门
    就此解锁——元素初始 mode=DIRECT（types.py）→ 本命令=炮击任务令唯一解锁钥匙
    （⑧块「任务令恒 REJECT」留痕闭环）。零掷骰。"""

    def test_gate_mode_set_membership(self):
        # ① m ∉ mode_set → REJECT 不写：DIRECT-only 缺省卡 / 位集外 int 同被掩码滤除
        w = make_world(7)
        t = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (0, 0)))
        self.assertEqual(t.template.mode_set, 1 << Mode.DIRECT)   # 缺省（types.py:321）
        self.assertFalse(cmd_set_element_mode(w, t.elements[0], Mode.INDIRECT))
        self.assertIs(t.elements[0].mode, Mode.DIRECT)
        b = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (5000, 0)))
        self.assertTrue(cmd_set_element_mode(w, b.elements[0], Mode.INDIRECT))
        self.assertIs(b.elements[0].mode, Mode.INDIRECT)
        self.assertFalse(cmd_set_element_mode(w, b.elements[0], 9))  # 越界 int
        self.assertIs(b.elements[0].mode, Mode.INDIRECT)             # 拒令不写

    def test_bare_int_normalized_to_mode_enum(self):
        # 输入纪律（2026-10-06 批①评审#3 补锚）：位集内裸 int 归一为 Mode 枚举
        # ——归一前 e.mode=3 与身份比较分支失配（再切模式的 ③ CARGO 卸货被
        # 静默跳过）；归一后 is 判据全链可达
        from sovs.sim.types import Mode as M
        w = make_world(7)
        u = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (0, 0)))
        e = u.elements[0]
        self.assertTrue(cmd_set_element_mode(w, e, int(M.INDIRECT)))  # 裸 int 在位集内
        self.assertIs(e.mode, M.INDIRECT)                             # 归一=身份可达
        # 位组合非法值（非单一 Mode 成员）→ REJECT（掩码滤除同款拒令口径）
        self.assertFalse(cmd_set_element_mode(w, e, (1 << M.INDIRECT) | (1 << M.DIRECT)))
        self.assertIs(e.mode, M.INDIRECT)                             # 拒令不写

    def test_dispatch_via_queue_command(self):
        # 分派支真调用：queue_command→consume_commands→cmd_set_element_mode；
        # 元素粒度（同单位他元素不动）+ 零掷骰
        w = make_world(7)
        u = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (0, 0)))
        rng0 = [r.state for r in w.rng._rngs]
        queue_command(w, SetModeCmd(element=u.elements[1], mode=Mode.INDIRECT))
        world_tick(w)                                          # t1 consume
        self.assertEqual(w.command_queue, [])
        self.assertIs(u.elements[1].mode, Mode.INDIRECT)
        self.assertIs(u.elements[0].mode, Mode.DIRECT)         # 元素粒度
        self.assertEqual([r.state for r in w.rng._rngs], rng0)

    def test_fire_mission_double_gate_unlocked_by_setmode(self):
        # 双门第二门：模板有 INDIRECT 位但元素初始 mode=DIRECT → cmd_fire_mission
        # REJECT（⑧块成文时整局不可达态）；SetModeCmd 后同拍解锁
        w = make_world(7)
        u = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (0, 0)))
        self.assertTrue(u.template.mode_set & (1 << Mode.INDIRECT))
        self.assertFalse(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                          (50000, 50000), 1, SalvoMode.FULL, 0))
        self.assertIsNone(u.fire_mission)
        queue_command(w, SetModeCmd(element=u.elements[0], mode=Mode.INDIRECT))
        world_tick(w)
        self.assertTrue(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                         (50000, 50000), 1, SalvoMode.FULL, 0))
        fm = u.fire_mission
        self.assertIsNotNone(fm)
        self.assertEqual(fm.shots_left, 6)          # 1 门 INDIRECT × HOW ammo_base 6 × 1
        self.assertEqual(fm.shots_fired, 0)
        self.assertEqual(fm.target_point, (50000, 50000))
        self.assertEqual(fm.calib_progress, 0)

    def test_m21_half_clear_semantics(self):
        # ⑦ M21/A24 元素级半清除：任一 INDIRECT 元素存续 → 任务存活；全切才清
        #（e.mode=m 先行赋值故判据自然含刚切元素）；他单位切换不清本单位任务
        w = make_world(7)
        u = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (0, 0)))
        for e in u.elements:
            cmd_set_element_mode(w, e, Mode.INDIRECT)
        self.assertTrue(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                         (1, 2), 1, SalvoMode.FULL, 0))
        fm = u.fire_mission
        self.assertEqual(fm.shots_left, 18)                     # 3 门 × 6
        self.assertTrue(cmd_set_element_mode(w, u.elements[0], Mode.DIRECT))
        self.assertIs(u.fire_mission, fm)                       # 2 门仍在 INDIRECT
        self.assertTrue(cmd_set_element_mode(w, u.elements[1], Mode.DIRECT))
        self.assertIs(u.fire_mission, fm)                       # 末门仍在
        self.assertTrue(cmd_set_element_mode(w, u.elements[2], Mode.DIRECT))
        self.assertIsNone(u.fire_mission)                       # 全切才清（方案10：
                                                                # 任务体销毁校射随之失效）
        cmd_set_element_mode(w, u.elements[0], Mode.INDIRECT)   # 重开 1 门重建任务
        self.assertTrue(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                         (1, 2), 1, SalvoMode.FULL, 0))
        fm2 = u.fire_mission
        u2 = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (1000, 1000)))
        for e in u2.elements:
            cmd_set_element_mode(w, e, Mode.INDIRECT)
        for e in u2.elements:                                  # 他单位全切不清 u1
            cmd_set_element_mode(w, e, Mode.DIRECT)
        self.assertIs(u.fire_mission, fm2)

    def test_tow_release_on_mode_switch(self):
        # ② e.mode==TOW → release_tow_if_involved（GAP-24 元素级：仅涉本元素对；
        # 被拖侧非 TOW 模式不进分支照字面——pair 不因被拖方切模解除）
        w = make_world(7)
        tower = add_unit(w, make_unit(w, TANK_TOW_TPL, 0, 0, (0, 0)))
        other = add_unit(w, make_unit(w, TANK_TOW_TPL, 0, 0, (5000, 0)))
        gun = add_unit(w, make_unit(w, BATT_TPL, 1, 1, (10000, 0))).elements[0]
        gun2 = add_unit(w, make_unit(w, BATT_TPL, 1, 1, (15000, 0))).elements[0]
        te, oe = tower.elements[0], other.elements[0]
        te.mode = Mode.TOW
        oe.mode = Mode.TOW
        te.towed = TowState.TOWING
        gun.towed = TowState.TOWED
        oe.towed = TowState.TOWING
        gun2.towed = TowState.TOWED
        pair1 = TowPair(tower_elements=[te], towed_element=gun)
        pair2 = TowPair(tower_elements=[oe], towed_element=gun2)
        w.tow_pairs.extend((pair1, pair2))
        self.assertTrue(cmd_set_element_mode(w, te, Mode.DIRECT))
        self.assertEqual(w.tow_pairs, [pair2])          # 仅涉 te 的对解除
        self.assertIs(te.towed, TowState.NONE)
        self.assertIs(gun.towed, TowState.NONE)
        self.assertIs(oe.towed, TowState.TOWING)        # 他对健康拖曳不动
        self.assertIs(gun2.towed, TowState.TOWED)
        # 被拖方（mode=DIRECT 非 TOW）切模：② 分支不进——pair 照字面存续
        self.assertTrue(cmd_set_element_mode(w, gun2, Mode.INDIRECT))
        self.assertEqual(w.tow_pairs, [pair2])

    def test_cargo_unload_zeros_supply_weight(self):
        # ③ e.mode==CARGO 且有 hasSupply 槽 → supply_weight_g=0（伪代码 :1196-1197
        # 字段不存在——2026-10-03 一池拍板换槽；None=未分配条件槽不触碰，方案12）
        w = make_world(7)
        u = add_unit(w, make_unit(w, TANK_CARGO_TPL, 0, 0, (0, 0)))
        e = u.elements[0]
        e.mode = Mode.CARGO
        e.supply_weight_g = 500
        self.assertTrue(cmd_set_element_mode(w, e, Mode.DIRECT))
        self.assertEqual(e.supply_weight_g, 0)
        e.mode = Mode.CARGO
        e.supply_weight_g = None                          # 未分配槽
        self.assertTrue(cmd_set_element_mode(w, e, Mode.DIRECT))
        self.assertIsNone(e.supply_weight_g)              # 不写

    def test_transport_unload_passengers(self):
        # ④ e.mode==TRANSPORT 卸客：班元素 mounted_in 双向清+旁落位（偏移未定标
        # 取载具同点位——destroy_element 同款登记）、班锚同旁落位、cargo_units=[]
        #（:1203 字面）；其他载具舱内班不动
        w = make_world(7)
        carrier = add_unit(w, make_unit(w, TRANSPORT_TPL, 0, 0, (10000, 10000)))
        other = add_unit(w, make_unit(w, TRANSPORT_TPL, 0, 0, (20000, 20000)))
        squad = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        other_squad = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        ce, oc = carrier.elements[0], other.elements[0]
        se, ose = squad.elements[0], other_squad.elements[0]
        ce.mode = Mode.TRANSPORT
        ce.cargo_units = [squad]
        se.mounted_in = ce
        se.pos = (9000, 9000)                             # 舱内班在别处（合成态）
        squad.pos = (8000, 8000)
        oc.mode = Mode.TRANSPORT
        oc.cargo_units = [other_squad]
        ose.mounted_in = oc
        ose.pos = (21000, 21000)
        self.assertTrue(cmd_set_element_mode(w, ce, Mode.DIRECT))
        self.assertEqual(ce.cargo_units, [])
        self.assertIsNone(se.mounted_in)                  # v1.3 审查#3 双向清
        self.assertEqual(se.pos, (10000, 10000))          # 旁落位=载具同点位
        self.assertEqual(squad.pos, (10000, 10000))       # 班锚旁落位
        self.assertIs(ose.mounted_in, oc)                 # 他载具舱内班不动
        self.assertEqual(oc.cargo_units, [other_squad])

    def test_mount_requests_cleanup_except_transport(self):
        # ⑤ m≠TRANSPORT → 清 carrier==本元素挂起条目（I-19，按身份）；切入
        # TRANSPORT 不清（:1204 字面）
        w = make_world(7)
        u = add_unit(w, make_unit(w, TRANSPORT_TPL, 0, 0, (0, 0)))
        u2 = add_unit(w, make_unit(w, TRANSPORT_TPL, 0, 0, (5000, 0)))
        c, c2 = u.elements[0], u2.elements[0]
        s = add_unit(w, make_unit(w, INF_TPL, 1, 1, (0, 0))).elements[0]
        w.mount_requests = [MountRequest(squad_element=s, carrier=c, ticks_left=100),
                            MountRequest(squad_element=s, carrier=c2, ticks_left=100)]
        self.assertTrue(cmd_set_element_mode(w, c, Mode.DIRECT))
        self.assertEqual(len(w.mount_requests), 1)
        self.assertIs(w.mount_requests[0].carrier, c2)
        self.assertTrue(cmd_set_element_mode(w, c2, Mode.TRANSPORT))
        self.assertEqual(len(w.mount_requests), 1)        # m==TRANSPORT 不滤

    def test_zero_rng_all_cleanup_branches(self):
        # 零掷骰：②③④⑤⑦ 清理分支连打八通道不动（含前置 SetMode/任务创建）
        w = make_world(11)
        rng0 = [r.state for r in w.rng._rngs]
        tow_u = add_unit(w, make_unit(w, TANK_TOW_TPL, 0, 0, (0, 0)))
        te = tow_u.elements[0]
        te.mode = Mode.TOW
        te.towed = TowState.TOWING
        gun = add_unit(w, make_unit(w, BATT_TPL, 1, 1, (5000, 0))).elements[0]
        gun.towed = TowState.TOWED
        w.tow_pairs.append(TowPair(tower_elements=[te], towed_element=gun))
        cargo_u = add_unit(w, make_unit(w, TANK_CARGO_TPL, 0, 0, (10000, 0)))
        ce = cargo_u.elements[0]
        ce.mode = Mode.CARGO
        ce.supply_weight_g = 300
        batt = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (15000, 0)))
        cmd_set_element_mode(w, batt.elements[0], Mode.INDIRECT)
        self.assertTrue(cmd_fire_mission(w, batt, FireMissionForm.POINT,
                                         (1, 1), 1, SalvoMode.FULL, 0))
        self.assertIsNotNone(batt.fire_mission)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)   # 前置亦零掷骰
        cmd_set_element_mode(w, te, Mode.DIRECT)                 # ② TOW 解挂
        cmd_set_element_mode(w, ce, Mode.DIRECT)                 # ③ CARGO 清零
        cmd_set_element_mode(w, batt.elements[0], Mode.DIRECT)   # ⑦ 全切清任务
        self.assertEqual(w.tow_pairs, [])
        self.assertEqual(ce.supply_weight_g, 0)
        self.assertIsNone(batt.fire_mission)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)   # 纯整数写点


class TestCmdToggleAmbush(unittest.TestCase):
    """§F4 :874-883 ToggleAmbushCmd 处理体（PB-56 批①，2026-10-06）——R-12 伏击
    开关唯一写点（原 ambush_active 全文无 TRUE 写点=整链不可达）。资格门/开关
    双稳/开启需静止（「静止 AND move_path==[]」同源谓词折叠）/手动退出携首击加成
    全链（退出→AttackCmd→fire_direct 首击 ×13000 打完清）/§F3 两消费点/分派链。
    移动自动退出（无加成+M19 清加成）既有锚=tests/test_movement.py:153-169；
    首击乘区数值锚既有=本文件 test_ambush_shot_bonus_pushes_acc_over_certain。
    零掷骰（写点纯布尔，发射段掷骰属 fire_direct 既有通道纪律）。"""

    def test_gate_can_ambush_flag(self):
        # ① 资格门：无 CAN_AMBUSH 位 → REJECT（现役 0 卡置位〔实测 CSV〕——
        # 数据侧脱节登记，合成模板置位）
        w = make_world(7)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        self.assertFalse(u.template.flags & UnitFlag.CAN_AMBUSH)
        self.assertFalse(cmd_toggle_ambush(u))
        self.assertFalse(u.ambush_active)
        self.assertFalse(u.ambush_shot_bonus)

    def test_bistable_and_stationary_gate(self):
        # ②③ 开关双稳 + 开启需静止（移动中受令=过门无操作——伪代码无第二 REJECT
        # 字面）+ 退出携首击加成（开启不清加成，消费/移动才清）
        w = make_world(7)
        u = add_unit(w, make_unit(w, AMBUSH_ACC80_TPL, 0, 0, (0, 0)))
        self.assertTrue(cmd_toggle_ambush(u))             # 静止开启
        self.assertTrue(u.ambush_active)
        self.assertTrue(cmd_toggle_ambush(u))             # 手动退出
        self.assertFalse(u.ambush_active)
        self.assertTrue(u.ambush_shot_bonus)              # :879-880
        u.move_path = [(1000, 1000)]                      # 移动中：ELIF 不满足
        self.assertTrue(cmd_toggle_ambush(u))             # 资格门过=受令
        self.assertFalse(u.ambush_active)                 # 无操作
        self.assertTrue(u.ambush_shot_bonus)              # 加成不被开启清除
        u.move_path = []
        self.assertTrue(cmd_toggle_ambush(u))             # 再静止可重开
        self.assertTrue(u.ambush_active)
        self.assertTrue(u.ambush_shot_bonus)

    def test_manual_exit_to_first_shot_full_chain(self):
        # R-12 全链：开启→手动退出（加成挂起）→AttackCmd 受令→begin_aim→
        # finish_aim→fire_direct 首击 ×ambush_acc_bonus_bp（8000×13000//10000
        # =10400 >10000 必中）→打完清（:830 消费点）
        w = make_world(13)
        u = add_unit(w, make_unit(w, AMBUSH_ACC80_TPL, 0, 0, (100000, 100000)))
        foe = add_unit(w, make_unit(w, INF_TPL, 1, 1, (130000, 100000)))
        foe.spotted_mask = 1
        self.assertTrue(cmd_toggle_ambush(u))             # 开启
        self.assertTrue(cmd_toggle_ambush(u))             # 手动退出 → 加成挂起
        self.assertTrue(u.ambush_shot_bonus)
        queue_command(w, AttackCmd(element=u.elements[0],
                                   target=foe.elements[0]))
        world_tick(w)                                     # t1 受令 begin_aim（aim 0→
        ws = u.elements[0].weapon_states[0]               # timer 1）→① 同拍递减到期→
        self.assertIs(ws.state, WState.RELOADING)         # ④ fire_direct 即拍发射
        self.assertEqual(len(w.projectiles), 1)
        self.assertTrue(w.projectiles[0].will_hit)        # 10400bp 必中
        self.assertFalse(u.ambush_shot_bonus)             # 首击打完清
        self.assertEqual(ws.ammo_left, 9)                 # 耗 1 发

    def test_sensing_consumers(self):
        # §F3 两消费点：目标侧 effective_stealth_x10 ×ambush_mult_bp=20000
        #（stealth 3→30→60，不触顶可锚乘区形状）；观察者侧 detection_range r//2
        w = make_world(7)
        u = add_unit(w, make_unit(w, AMBUSH_ACC80_TPL, 0, 0, (0, 0)))
        obs = add_unit(w, make_unit(w, INF_TPL, 0, 0, (5000, 0)))
        tgt = add_unit(w, make_unit(w, INF_TPL, 1, 1, (8000, 0)))  # 非伏击目标
        self.assertEqual(effective_stealth_x10(CONFIG, u), 30)      # 开启前
        self.assertTrue(cmd_toggle_ambush(u))
        self.assertEqual(effective_stealth_x10(CONFIG, u), 60)      # ×20000//10000
        r0 = detection_range_cm(CONFIG, obs, tgt)
        obs.ambush_active = True
        self.assertEqual(detection_range_cm(CONFIG, obs, tgt), r0 // 2)

    def test_dispatch_and_zero_rng(self):
        w = make_world(7)
        u = add_unit(w, make_unit(w, AMBUSH_ACC80_TPL, 0, 0, (0, 0)))
        rng0 = [r.state for r in w.rng._rngs]
        queue_command(w, ToggleAmbushCmd(unit=u))
        world_tick(w)
        self.assertTrue(u.ambush_active)
        queue_command(w, ToggleAmbushCmd(unit=u))
        world_tick(w)
        self.assertFalse(u.ambush_active)
        self.assertTrue(u.ambush_shot_bonus)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)      # 零掷骰


class TestCmdSetStance(unittest.TestCase):
    """§D.7 :261 SetStanceCmd 最小写点（PB-56 批①，2026-10-06——勘察处置案 a：
    v1.7 仅字段定义无处理体、GDD 无姿态细则锚 → 单写点+Stance 枚举校验、无资格
    门，行为门全在消费侧 fire_permitted ②）。消费锚：地面自动/手动链同拦
    （fire_permitted）、对空链豁免（§F4 :695「不约束对空」——aa_try_engage 不调
    fire_permitted）、切回恢复。零掷骰。"""

    def test_write_point_and_enum_gate(self):
        # 单写点 + 枚举合法性校验（枚举外值/裸 int 均 REJECT 不冒充写点）
        w = make_world(7)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        self.assertTrue(cmd_set_stance(u, Stance.HOLD_FIRE))
        self.assertIs(u.stance, Stance.HOLD_FIRE)
        self.assertFalse(cmd_set_stance(u, 5))            # 枚举外值
        self.assertIs(u.stance, Stance.HOLD_FIRE)
        self.assertFalse(cmd_set_stance(u, 1))            # 裸 int（==HOLD_FIRE 非成员）
        self.assertIs(u.stance, Stance.HOLD_FIRE)
        self.assertTrue(cmd_set_stance(u, Stance.WEAPONS_FREE))
        self.assertIs(u.stance, Stance.WEAPONS_FREE)

    def test_hold_fire_blocks_auto_and_manual_ground_fire(self):
        # 消费侧：fire_permitted ② 同时拦自动链（ground_direct 经 system_combat）
        # 与手动链（cmd_attack ⑧ 同门）；切回恢复
        w = make_world(7)
        shooter = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (100000, 100000)))
        foe = add_unit(w, make_unit(w, INF_TPL, 1, 1, (130000, 100000)))
        foe.spotted_mask = 1
        e, ws = shooter.elements[0], shooter.elements[0].weapon_states[0]
        shooter.stance = Stance.HOLD_FIRE
        system_combat(w, shooter)                         # 自动链
        self.assertIs(ws.state, WState.READY)
        cmd_attack(w, e, foe.elements[0], CONFIG)         # 手动链（⑧）
        self.assertIs(ws.state, WState.READY)
        shooter.stance = Stance.WEAPONS_FREE
        system_combat(w, shooter)
        self.assertIs(ws.state, WState.AIMING)            # 解除即恢复

    def test_aa_chain_exempt_from_stance(self):
        # §F4 :695「不约束对空」：HOLD_FIRE 下 aa_try_engage 照常 begin_aim
        #（对空链不调 fire_permitted——R-17 最小许可集口径）
        w = make_world(7)
        u = add_unit(w, make_unit(w, AA_STANCE_TPL, 0, 0, (100000, 100000)))
        air = AircraftInstance(id=1, team=1, player_index=1, template=None,
                               pos=(130000, 100000), alt_tier=AltTier.HIGH,
                               hp_current=30)
        air.spotted_mask = 1
        w.aircraft.append(air)
        u.stance = Stance.HOLD_FIRE
        ws = u.elements[0].weapon_states[0]
        aa_try_engage(w, u.elements[0], ws)
        self.assertIs(ws.state, WState.AIMING)
        self.assertIs(ws.target, air)

    def test_dispatch_and_zero_rng(self):
        w = make_world(7)
        u = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        rng0 = [r.state for r in w.rng._rngs]
        queue_command(w, SetStanceCmd(unit=u, stance=Stance.HOLD_FIRE))
        world_tick(w)
        self.assertIs(u.stance, Stance.HOLD_FIRE)
        queue_command(w, SetStanceCmd(unit=u, stance=Stance.WEAPONS_FREE))
        world_tick(w)
        self.assertIs(u.stance, Stance.WEAPONS_FREE)
        self.assertEqual([r.state for r in w.rng._rngs], rng0)


class TestIndirectRole(unittest.TestCase):
    """§F4 :749-764 自卫直射（M20 已发现门/方案3 判空短路/最近者）。"""

    def _mortar_world(self):
        w = make_world(5)
        m = add_unit(w, make_unit(w, MORTAR_TPL, 0, 0, (100000, 100000)))
        m.elements[0].mode = Mode.INDIRECT
        return w, m, m.elements[0], m.elements[0].weapon_states[0]

    def test_engages_nearest_spotted_enemy(self):
        w, m, e, ws = self._mortar_world()
        near = add_unit(w, make_unit(w, INF_TPL, 1, 1, (102000, 100000)))   # 2000cm
        near.spotted_mask = 1
        far = add_unit(w, make_unit(w, MG_INF_TPL, 1, 1, (105000, 100000)))  # 5000 超自卫程
        far.spotted_mask = 1
        indirect_role(w, m, e)
        self.assertIs(ws.state, WState.AIMING)
        self.assertTrue(ws.use_self_defense)
        self.assertIs(ws.target, near.elements[0])          # 最近已发现候选

    def test_unspotted_not_engaged(self):
        # M20：自卫仅对已发现敌（渗透班/骑兵摸炮位不可见即无还手）
        w, m, e, ws = self._mortar_world()
        add_unit(w, make_unit(w, INF_TPL, 1, 1, (102000, 100000)))          # 未发现
        indirect_role(w, m, e)
        self.assertIs(ws.state, WState.READY)
        self.assertFalse(ws.use_self_defense)

    def test_busy_weapon_mutual_exclusion(self):
        # 与炮击任务经 weapon_states 忙碌互斥：AIMING/RELOADING 不再自卫瞄准
        w, m, e, ws = self._mortar_world()
        add_unit(w, make_unit(w, INF_TPL, 1, 1, (102000, 100000))).spotted_mask = 1
        ws.state = WState.RELOADING
        indirect_role(w, m, e)
        self.assertIs(ws.state, WState.RELOADING)
        self.assertFalse(ws.use_self_defense)

    def test_no_profile_short_circuit(self):
        # 方案3：无自卫档曲射炮判空短路（HOW 无 self_defense）
        w = make_world(5)
        b = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (100000, 100000)))
        add_unit(w, make_unit(w, INF_TPL, 1, 1, (102000, 100000))).spotted_mask = 1
        e = b.elements[0]
        e.mode = Mode.INDIRECT
        system_combat(w, b)                                 # 经 ③ 分流（位门开）
        self.assertIs(e.weapon_states[0].state, WState.READY)

    def test_mode_set_gate_blocks_dispatch(self):
        # 方案3 静态门：模板无 INDIRECT 位 → e.mode=INDIRECT 亦不进 indirect_role
        w = make_world(5)
        m = add_unit(w, make_unit(w, MORTAR_NOBIT_TPL, 0, 0, (100000, 100000)))
        self.assertEqual(m.template.mode_set, 1 << Mode.DIRECT)
        add_unit(w, make_unit(w, INF_TPL, 1, 1, (102000, 100000))).spotted_mask = 1
        e = m.elements[0]
        e.mode = Mode.INDIRECT
        world_tick(w)
        self.assertIs(e.weapon_states[0].state, WState.READY)


class TestSelectProfile(unittest.TestCase):
    """§F4 :790-804 R-11 alt_profile / M16 钨芯实例副本 / 默认档案。"""

    def _dual(self):
        w = make_world(3)
        u = add_unit(w, make_unit(w, DUAL_TPL, 0, 0, (0, 0)))
        return w, u.elements[0], u.elements[0].weapon_states[0]

    def test_alt_profile_he_on_infantry(self):
        w, e, ws = self._dual()
        inf = add_unit(w, make_unit(w, INF_TPL, 1, 1, (1000, 0)))
        prof = select_profile(w, e, ws, inf.elements[0])
        self.assertEqual(prof, (DamageType.HE, 7, 2000, 0))          # alt HE 档（§D.3#23）

    def test_tungsten_switch_on_mech_front(self):
        # KE 默认 pen_max=4 < 目标 front 8 → 钨芯 (+3) 救场、档内计数递减
        w, e, ws = self._dual()
        mech = add_unit(w, make_unit(w, ARMORED_TPL, 1, 1, (1000, 0)))
        self.assertEqual(ws.restricted_left, (2,))
        prof = select_profile(w, e, ws, mech.elements[0])
        self.assertEqual(prof, (DamageType.KE, 9, 0, 3))             # 默认AP+pen_bonus
        self.assertEqual(ws.restricted_left, (1,))
        prof = select_profile(w, e, ws, mech.elements[0])
        self.assertEqual(prof, (DamageType.KE, 9, 0, 3))
        self.assertEqual(ws.restricted_left, (0,))
        prof = select_profile(w, e, ws, mech.elements[0])            # 存货尽 → 默认
        self.assertEqual(prof, (DamageType.KE, 9, 0, 0))

    def test_no_switch_when_pen_sufficient(self):
        # pen_max ≥ front（换软甲目标）不切钨芯
        w, e, ws = self._dual()
        soft = ElementTemplate(element_type=ElementType.VEHICLE,
                               unit_type=UnitType.MECH, hp_max=10,
                               armor_ke=Armor(front=3, side=2, rear=1, top=1))
        tpl = UnitTemplate(template_id=514, name="light", category=2, cost=40,
                           element_templates=(soft,), optics_ground_cm=10000,
                           stealth_base=5, speed_tier=2,
                           movement_class=MovementClass.TRACK)
        mech = add_unit(w, make_unit(w, tpl, 1, 1, (1000, 0)))
        prof = select_profile(w, e, ws, mech.elements[0])
        self.assertEqual(prof, (DamageType.KE, 9, 0, 0))
        self.assertEqual(ws.restricted_left, (2,))                   # 未消耗

    def test_make_unit_deep_copies_restricted_counts(self):
        # M16：每门独立实例副本（模板不被写、同模板两单位互不影响）
        w, e1, ws1 = self._dual()
        u2 = add_unit(w, make_unit(w, DUAL_TPL, 0, 0, (5000, 0)))
        ws2 = u2.elements[0].weapon_states[0]
        mech = add_unit(w, make_unit(w, ARMORED_TPL, 1, 1, (1000, 0)))
        select_profile(w, e1, ws1, mech.elements[0])
        self.assertEqual(ws1.restricted_left, (1,))
        self.assertEqual(ws2.restricted_left, (2,))                  # 深拷贝独立
        self.assertEqual(DUAL_W.restricted_profiles, ((2, 3),))      # 模板原样


class TestFireMission(unittest.TestCase):
    """§F4.1 :908-973 炮击任务（R-13/R-14/R-16）+ fire_at 落点链。"""

    def _battery(self, seed=3, deployed=True, n=3):
        w = make_world(seed)
        b = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (500000, 500000)))
        for e in b.elements[:n]:
            e.mode = Mode.INDIRECT
        if deployed:
            b.deploy_state = DeployState.DEPLOYED
        return w, b

    def test_cmd_fire_mission_rejects(self):
        w = make_world(3)
        nb = add_unit(w, make_unit(w, BATT_NOBIT_TPL, 0, 0, (0, 0)))   # 无 INDIRECT 位
        self.assertFalse(cmd_fire_mission(w, nb, FireMissionForm.POINT,
                                          (510000, 500000), 1, SalvoMode.FULL, 0))
        b = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (500000, 500000)))
        for e in b.elements:                                # 有位无 INDIRECT 元素
            e.mode = Mode.DIRECT
        self.assertFalse(cmd_fire_mission(w, b, FireMissionForm.POINT,
                                          (510000, 500000), 1, SalvoMode.FULL, 0))
        self.assertIsNone(b.fire_mission)
        self.assertIsNone(nb.fire_mission)

    def test_cmd_shots_half_ceil_and_full(self):
        # R-13/R-14：HALF=⌈3/2⌉=2 门 ×6=12；FULL=3×6=18；mult=2 翻倍
        w, b = self._battery()
        self.assertTrue(cmd_fire_mission(w, b, FireMissionForm.POINT,
                                         (510000, 500000), 1, SalvoMode.HALF, 0))
        self.assertEqual(b.fire_mission.shots_left, 12)
        self.assertEqual(b.fire_mission.calib_target, (510000, 500000))
        self.assertEqual(b.fire_mission.calib_progress, 0)
        self.assertTrue(cmd_fire_mission(w, b, FireMissionForm.POINT,
                                         (510000, 500000), 2, SalvoMode.FULL, 0))
        self.assertEqual(b.fire_mission.shots_left, 3 * 6 * 2)

    def test_half_round_only_first_ceil_guns_fire(self):
        # AMB-09：半轮=前 ⌈3/2⌉=2 门；第 3 门弹药不动
        w, b = self._battery()
        cmd_fire_mission(w, b, FireMissionForm.POINT, (520000, 500000), 1,
                         SalvoMode.HALF, 0)
        world_tick(w)                                       # tick1 齐射（aim 0）
        self.assertEqual([e.weapon_states[0].ammo_left for e in b.elements],
                         [5, 5, 6])
        self.assertEqual(b.fire_mission.shots_left, 12 - 2)
        self.assertEqual(b.fire_mission.shots_fired, 2)

    def test_point_fire_at_ballistic_no_target_projectiles(self):
        # 无目标弹丸：BALLISTIC / hit_target None / will_hit False / dest=pt（dispersion 0
        # 且无圈——sym(0)=0 恒等）；ammo/状态/计时/counters 按批推进
        w, b = self._battery()
        pt = (520000, 500000)
        cmd_fire_mission(w, b, FireMissionForm.POINT, pt, 1, SalvoMode.FULL, 0)
        world_tick(w)
        self.assertEqual(len(w.projectiles), 3)             # 3 门各 1 发
        for p in w.projectiles:
            self.assertIs(p.trajectory, Trajectory.BALLISTIC)
            self.assertIsNone(p.hit_target)
            self.assertFalse(p.will_hit)
            self.assertEqual(p.dest, pt)
        ws0 = b.elements[0].weapon_states[0]
        self.assertEqual(ws0.ammo_left, 5)
        self.assertIs(ws0.state, WState.RELOADING)
        self.assertEqual(ws0.timer, 10)                     # reload 10 ×1.0
        self.assertEqual(b.fire_mission.shots_left, 18 - 3)

    def test_mission_exhausted_and_destroyed(self):
        # HALF 12 发：2 门 × 6 轮 → 打空即销毁任务体（方案10）；第 3 门弹药满
        w, b = self._battery()
        cmd_fire_mission(w, b, FireMissionForm.POINT, (520000, 500000), 1,
                         SalvoMode.HALF, 0)
        for _ in range(60):                                 # 齐射节拍=reload 10
            world_tick(w)
            if b.fire_mission is None:
                break
        self.assertIsNone(b.fire_mission)                   # 12 发打完销毁
        self.assertEqual([e.weapon_states[0].ammo_left for e in b.elements],
                         [0, 0, 6])

    def test_deploy_gate_blocks_undeployed_guns(self):
        # v1.1 修复：未展开的炮不打（统一走开火许可）
        w, b = self._battery(deployed=False)
        b.deploy_state = DeployState.MOBILE
        cmd_fire_mission(w, b, FireMissionForm.POINT, (520000, 500000), 1,
                         SalvoMode.FULL, 0)
        for _ in range(3):
            world_tick(w)
        self.assertEqual(w.projectiles, [])
        self.assertEqual(b.fire_mission.shots_left, 18)

    def test_no_indirect_bit_template_tail_not_called(self):
        # :689-691 方案3 静态门：模板无 INDIRECT 位 → 手置 fire_mission 也不推进
        w = make_world(3)
        nb = add_unit(w, make_unit(w, BATT_NOBIT_TPL, 0, 0, (0, 0)))
        nb.deploy_state = DeployState.DEPLOYED
        for e in nb.elements:
            e.mode = Mode.INDIRECT
        nb.fire_mission = FireMission(form=FireMissionForm.POINT,
                                      target_point=(20000, 0),
                                      shots_left=5, started_tick=0)
        world_tick(w)
        self.assertEqual(w.projectiles, [])
        self.assertEqual(nb.fire_mission.shots_left, 5)

    def test_cancel_command_destroys_mission(self):
        w, b = self._battery()
        cmd_fire_mission(w, b, FireMissionForm.POINT, (520000, 500000), 1,
                         SalvoMode.FULL, 0)
        from sovs.sim.tick import CancelFireMissionCmd, FireMissionCmd, queue_command
        queue_command(w, CancelFireMissionCmd(unit=b))
        world_tick(w)
        self.assertIsNone(b.fire_mission)                   # consume_commands 落地
        self.assertEqual(w.projectiles, [])                 # 任务取消即无发射

    def test_calib_accumulates_per_batch_in_vision(self):
        # R-16/⑩A/AMB-06：POINT+目标点在友军视野内（观察者 20000 光学×档位5 10500
        # =21000 ≥ dist 20000）→ 每次 fire_at（批）+calib_per_shot=20；LINE 短路
        w, b = self._battery(n=1)
        observer_tpl = UnitTemplate(
            template_id=515, name="obs", category=1, cost=10,
            element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
            speed_tier=1, movement_class=MovementClass.FOOT)
        obs = add_unit(w, make_unit(w, observer_tpl, 0, 0, (500000, 500000)))
        cmd_fire_mission(w, b, FireMissionForm.POINT, (520000, 500000), 1,
                         SalvoMode.FULL, 0)
        fire_at(w, b.elements[0], b.elements[0].weapon_states[0], b.fire_mission)
        self.assertEqual(b.fire_mission.calib_progress, 20)
        b.elements[0].weapon_states[0].state = WState.READY
        fire_at(w, b.elements[0], b.elements[0].weapon_states[0], b.fire_mission)
        self.assertEqual(b.fire_mission.calib_progress, 40)
        del obs

    def test_calib_out_of_vision_and_line_short_circuit(self):
        # 目标点超全部观察者视野（最近观察者 20000cm 处、目标 60000cm 外）→ 不累积；
        # LINE 形式即使在视野内也短路（⑩A）
        w, b = self._battery(n=1, seed=5)
        b.elements[0].pos = (0, 0)
        fm = FireMission(form=FireMissionForm.POINT, target_point=(60000, 0),
                         shots_left=6, calib_target=(60000, 0))
        b.fire_mission = fm
        fire_at(w, b.elements[0], b.elements[0].weapon_states[0], fm)
        self.assertEqual(fm.calib_progress, 0)
        fm2 = FireMission(form=FireMissionForm.LINE, target_line=((0, 0), (5000, 0)),
                          shots_left=6)
        b.fire_mission = fm2
        b.elements[0].weapon_states[0].state = WState.READY
        fire_at(w, b.elements[0], b.elements[0].weapon_states[0], fm2)
        self.assertEqual(fm2.calib_progress, 0)

    def test_calib_blocked_by_smoke_on_sight_line(self):
        # 感知接线块（2026-10-07）：校射视线穿烟衰减——fire_at 内
        # point_in_friendly_vision 经 terrain_sensing_channels 喂 smoke_m_fn。
        # 炮位/观察者同点 (500000,500000)（光学 20000×档位中值 10000bp=20000
        # ≥ dist 20000 边界可见）；目标点 (520000,500000) 线中点烟区 r=3000
        # → 弦 60m×detect_atten_per_m=150 → 11000<20000 不可见不累积；
        # 烟区移除即恢复累积（同批口径 AMB-06）
        w, b = self._battery(n=1)
        observer_tpl = UnitTemplate(
            template_id=515, name="obs", category=1, cost=10,
            element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
            speed_tier=1, movement_class=MovementClass.FOOT)
        obs = add_unit(w, make_unit(w, observer_tpl, 0, 0, (500000, 500000)))
        cmd_fire_mission(w, b, FireMissionForm.POINT, (520000, 500000), 1,
                         SalvoMode.FULL, 0)
        w.smoke_zones.append(SmokeZone(center=(510000, 500000),
                                       radius_cm=CONFIG.smoke_radius_cm,
                                       ttl_ticks=CONFIG.smoke_ttl_ticks))
        fire_at(w, b.elements[0], b.elements[0].weapon_states[0], b.fire_mission)
        self.assertEqual(b.fire_mission.calib_progress, 0)      # 穿烟遮蔽
        w.smoke_zones.clear()                                   # 烟散即恢复
        b.elements[0].weapon_states[0].state = WState.READY
        fire_at(w, b.elements[0], b.elements[0].weapon_states[0], b.fire_mission)
        self.assertEqual(b.fire_mission.calib_progress, 20)
        del obs

    def test_line_sampling_by_shots_fired(self):
        # LINE 均匀取样：k=shots_fired、分母=任务总发数（不变式 shots_fired+shots_left
        # =总发数——实现记账）；dispersion 0 → dest 精确等于取样点 a+(b−a)*k//6
        w = make_world(7)
        b = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (0, 0)))
        e = b.elements[0]
        e.mode = Mode.INDIRECT
        b.deploy_state = DeployState.DEPLOYED
        a, bb = (100000, 100000), (160000, 100000)          # 线长 60000、总 6 发
        fm = FireMission(form=FireMissionForm.LINE, target_line=(a, bb), shots_left=6)
        ws = e.weapon_states[0]
        for k, expect_x in ((0, 100000), (1, 110000), (5, 150000)):
            fm.shots_fired, fm.shots_left = k, 6 - k        # 维持总发数不变式
            ws.state = WState.READY
            fire_at(w, e, ws, fm)
            self.assertEqual(w.projectiles[-1].dest, (expect_x, 100000), "k=%d" % k)

    def test_creep_sampling_advances_with_time(self):
        # CREEP：t=经过tick×creep_speed/线长；t=0→a、t=0.5→中点、t≥1→b
        w = make_world(7)
        b = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (0, 0)))
        e = b.elements[0]
        e.mode = Mode.INDIRECT
        b.deploy_state = DeployState.DEPLOYED
        a, bb = (100000, 100000), (160000, 100000)          # 线长 60000、creep 1000/tick
        fm = FireMission(form=FireMissionForm.CREEP, target_line=(a, bb),
                         creep_speed_cm_tick=1000, shots_left=9, started_tick=0)
        ws = e.weapon_states[0]
        for tick, expect_x in ((0, 100000), (30, 130000), (60, 160000), (99, 160000)):
            w.tick = tick
            fm.started_tick = 0
            ws.state = WState.READY
            fire_at(w, e, ws, fm)
            self.assertEqual(w.projectiles[-1].dest, (expect_x, 100000),
                             "tick=%d" % tick)

    def test_intel_circle_adds_scatter_radius(self):
        # 盲射声测圈：目标点在圈内（半径 5000）→ 散布=dispersion(0)+5000——
        # dest 各轴偏移 ∈ [−5000, 5000]（方形散布）
        w = make_world(7)
        b = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (0, 0)))
        e = b.elements[0]
        e.mode = Mode.INDIRECT
        b.deploy_state = DeployState.DEPLOYED
        pt = (200000, 200000)
        e.pos = (190000, 200000)
        w.intel_circles.append(IntelCircle(team=0, source_unit=b, center=pt,
                                           radius_cm=5000))
        fm = FireMission(form=FireMissionForm.POINT, target_point=pt, shots_left=6)
        fire_at(w, e, e.weapon_states[0], fm)
        p = w.projectiles[-1]
        self.assertLessEqual(abs(p.dest[0] - pt[0]), 5000)
        self.assertLessEqual(abs(p.dest[1] - pt[1]), 5000)

    def test_sound_track_upsert_and_move_reset(self):
        # C4：每 (侦听队, 开火单位) 一条（两队制=敌方一条）；last_fire_tick 刷新；
        # 换位 > sonar_move_reset_cm(3000) → accum 清零
        w, b = self._battery(n=1, seed=9)
        e = b.elements[0]
        e.pos = (500000, 500000)
        fm = FireMission(form=FireMissionForm.POINT, target_point=(520000, 500000),
                         shots_left=6)
        fire_at(w, e, e.weapon_states[0], fm)
        self.assertEqual(len(w.sound_tracks), 1)
        st = w.sound_tracks[0]
        self.assertEqual(st.listening_team, 1)              # 队 0 开火 → 敌队侦听
        self.assertIs(st.unit, b)
        self.assertEqual(st.pos, e.pos)
        self.assertEqual(st.last_fire_tick, w.tick)
        st.accum = 7                                        # 模拟 sonar_step 累积
        w.tick += 10
        e.weapon_states[0].state = WState.READY
        fire_at(w, e, e.weapon_states[0], fm)               # 原地再射：accum 保留
        self.assertEqual(st.accum, 7)
        self.assertEqual(st.last_fire_tick, w.tick)
        e.pos = (510000, 500000)                            # 换位 10000 > 3000
        e.weapon_states[0].state = WState.READY
        fire_at(w, e, e.weapon_states[0], fm)
        self.assertEqual(st.accum, 0)                       # 换阵地重定位
        self.assertEqual(st.pos, e.pos)

    def test_multi_battery_multi_tracks(self):
        # 同侦听队多开火单位共存（(t, unit) 键）
        w, b = self._battery(n=1, seed=11)
        b2 = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (400000, 400000)))
        b2.elements[0].mode = Mode.INDIRECT
        b2.deploy_state = DeployState.DEPLOYED
        fm1 = FireMission(form=FireMissionForm.POINT, target_point=(520000, 500000),
                          shots_left=6)
        fire_at(w, b.elements[0], b.elements[0].weapon_states[0], fm1)
        fm2 = FireMission(form=FireMissionForm.POINT, target_point=(420000, 400000),
                          shots_left=6)
        fire_at(w, b2.elements[0], b2.elements[0].weapon_states[0], fm2)
        self.assertEqual(len(w.sound_tracks), 2)
        self.assertEqual([s.unit for s in w.sound_tracks], [b, b2])

    def test_fire_at_scatter_channel_only(self):
        # 曲射落点只消费 SCATTER（will_hit 字面 FALSE——无 HIT 掷）
        w, b = self._battery(n=1, seed=13)
        e = b.elements[0]
        fm = FireMission(form=FireMissionForm.POINT, target_point=(520000, 500000),
                         shots_left=6)
        before = channel_states(w)
        fire_at(w, e, e.weapon_states[0], fm)
        after = channel_states(w)
        self.assertEqual(after["HIT"], before["HIT"])
        self.assertNotEqual(after["SCATTER"], before["SCATTER"])
        for name in ("SPOT", "CRIT", "SNIPER", "SONAR", "ECONOMY", "AIR"):
            self.assertEqual(after[name], before[name], name)


class TestAutoApproachConsumption(unittest.TestCase):
    """§2.11 超射程自动进位消费锚（2026-10-06 速度链块；MOVEMENT v1.2 §2.11——
    GAP-13 adopt）：cmd_fire_mission 双门通过后、目标在 INDIRECT 主武器射程外 →
    经 issue_move 外部通道插进位航点（四件一体：清链+退编组；进位移动恒 NORMAL）；
    射程内零行为差。HOW max_range=200000。纯函数锚在 tests/test_move_commands.py
    TestAutoApproach。"""

    def _battery(self, seed=17, n=1):
        w = make_world(seed)
        b = add_unit(w, make_unit(w, BATT_TPL, 0, 0, (0, 0)))
        for e in b.elements[:n]:
            e.mode = Mode.INDIRECT
        b.deploy_state = DeployState.DEPLOYED
        return w, b

    def test_out_of_range_point_mission_installs_waypoint(self):
        # 单位 (0,0)、目标 (250000,0)：d=250000>200000 → k=octant(250000,0)//45=2
        # （东 DIR8[2]=(7,0)）→ stand=MAX(200000−2000,100000)=198000 →
        # scale=(198000,0) → 航点=(250000−198000,0)=(52000,0)；外部通道四件一体：
        # 既有排队令清空、group_speed_cap 清 0、mode=NORMAL
        # 〔2026-10-07 命令族收口块补锚：DEPLOYED×进位移动令=移动令触发收装
        # （发起人拍板采 IMPL 字面）——转 PACKING+本令照常安装，收装完成前
        # system_move 同名门拦位移、毕后自动续走〕
        w, b = self._battery()
        b.command_queue = [MoveCmd(unit=b, path=[(9000, 0)], queue=True)]
        b.group_speed_cap = 2
        rng0 = [r.state for r in w.rng._rngs]
        self.assertTrue(cmd_fire_mission(w, b, FireMissionForm.POINT,
                                         (250000, 0), 1, SalvoMode.FULL, 0))
        self.assertIsNotNone(b.fire_mission)
        self.assertEqual(b.move_path, [(52000, 0)])
        self.assertIs(b.move_mode, MoveMode.NORMAL)
        self.assertEqual(b.command_queue, [])              # 外部通道四件一体清链
        self.assertEqual(b.group_speed_cap, 0)             # 退编组
        self.assertIs(b.deploy_state, DeployState.PACKING)  # 移动令触发收装
        self.assertEqual([r.state for r in w.rng._rngs], rng0)   # 进位零掷骰

    def test_in_range_point_mission_no_waypoint(self):
        # 射程内（d=100000≤200000）：不插航点——move_path 原样（零行为差分支）
        w, b = self._battery()
        self.assertTrue(cmd_fire_mission(w, b, FireMissionForm.POINT,
                                         (100000, 0), 1, SalvoMode.FULL, 0))
        self.assertEqual(b.move_path, [])

    def test_line_mission_uses_nearest_point(self):
        # LINE：判距基准=线段最近点——线 (250000,0)-(250000,100000) 对 (0,0)
        # 最近点=(250000,0)（端点夹持）→ 同 POINT 支航点 (52000,0)
        w, b = self._battery()
        self.assertTrue(cmd_fire_mission(w, b, FireMissionForm.LINE,
                                         [(250000, 0), (250000, 100000)],
                                         1, SalvoMode.FULL, 0))
        self.assertEqual(b.move_path, [(52000, 0)])

    def test_rejected_mission_installs_nothing(self):
        # 双门任一拒（无 INDIRECT 元素）：任务不建、亦不插航点（进位随任务安装）
        w, b = self._battery()
        for e in b.elements:
            e.mode = Mode.DIRECT
        self.assertFalse(cmd_fire_mission(w, b, FireMissionForm.POINT,
                                          (250000, 0), 1, SalvoMode.FULL, 0))
        self.assertIsNone(b.fire_mission)
        self.assertEqual(b.move_path, [])


class TestApproachDeg(unittest.TestCase):
    """geom.approach_deg_of（v1.7 零定义体——签名按 :334 用例定标，见登记表）。"""

    def test_octant_bearings(self):
        self.assertEqual(approach_deg_of((0, 0), (0, 100)), 0)       # 北
        self.assertEqual(approach_deg_of((0, 0), (100, 0)), 90)      # 东
        self.assertEqual(approach_deg_of((0, 0), (0, -100)), 180)    # 南
        self.assertEqual(approach_deg_of((0, 0), (-100, 100)), 315)  # 西北
        # 射界门用例：指向目标的方位 = approach_deg_of(e.pos, tgt.pos)
        self.assertEqual(approach_deg_of((200000, 200000), (200000, 170000)), 180)


class TestAuraBonus(unittest.TestCase):
    """§F1 :425-427（10000+bonus_bp) 连乘、半径门、同类过滤。"""

    def test_precision_aura_in_radius(self):
        w = make_world(3)
        officer_tpl = UnitTemplate(
            template_id=516, name="officer", category=1, cost=30,
            element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
            speed_tier=1, movement_class=MovementClass.FOOT,
            aura=Aura(kind=AuraKind.PRECISION, bonus_bp=1000, radius_cm=5000))
        add_unit(w, make_unit(w, officer_tpl, 0, 0, (0, 0)))
        self.assertEqual(aura_bonus_bp(w, 0, AuraKind.PRECISION, (3000, 0)), 11000)
        self.assertEqual(aura_bonus_bp(w, 0, AuraKind.PRECISION, (9000, 0)), 10000)
        self.assertEqual(aura_bonus_bp(w, 0, AuraKind.MELEE, (0, 0)), 10000)  # 类型门
        self.assertEqual(aura_bonus_bp(w, 1, AuraKind.PRECISION, (0, 0)), 10000)  # 队门

    def test_two_auras_multiply(self):
        w = make_world(3)
        tpl = UnitTemplate(
            template_id=517, name="off2", category=1, cost=30,
            element_templates=(SQUAD_ELEM,), optics_ground_cm=20000, stealth_base=5,
            speed_tier=1, movement_class=MovementClass.FOOT,
            aura=Aura(kind=AuraKind.PRECISION, bonus_bp=500, radius_cm=5000))
        add_unit(w, make_unit(w, tpl, 0, 0, (0, 0)))
        add_unit(w, make_unit(w, tpl, 0, 0, (1000, 0)))
        self.assertEqual(aura_bonus_bp(w, 0, AuraKind.PRECISION, (0, 0)),
                         10500 * 10500 // 10000)          # 连乘=11025


class TestFireMissionDeterminismDualRun(unittest.TestCase):
    """同 seed 两 world（直射对射+HALF 炮击任务）逐 tick 比指纹——位级相等。"""

    @staticmethod
    def _fingerprint(w):
        parts = ["t%d" % w.tick]
        for u in w.units:
            parts.append("U%d,%d,%d,%s,%r" % (
                u.id, u.spotted_mask, u.infiltration_timer, u.fire_mission is not None,
                u.pos))
            for e in u.elements:
                parts.append("E%d,%s,%d,%d,%d,%r" % (
                    e.id, e.pos, e.facing, int(e.rotating), e.suppression,
                    [(int(s.state), s.timer, s.ammo_left, s.target if s.target is None
                      else s.target.id, s.use_self_defense, s.restricted_left)
                     for s in e.weapon_states]))
            if u.fire_mission is not None:
                fm = u.fire_mission
                parts.append("FM%d,%d,%d,%d,%r" % (int(fm.form), fm.shots_left,
                                                   fm.shots_fired, fm.calib_progress,
                                                   fm.calib_target))
        parts.append("P%d" % len(w.projectiles))
        parts.append(",".join(str(r.state) for r in w.rng._rngs))
        parts.append(",".join("%s@%d/%d" % (s.pos, s.accum, s.last_fire_tick)
                              for s in w.sound_tracks))
        return "|".join(parts)

    def test_dual_run_80_ticks_bit_identical(self):
        def rich(seed):
            w = make_world(seed)
            tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (400000, 400000)))
            inf = add_unit(w, make_unit(w, MG_INF_TPL, 1, 1, (430000, 400000)))
            tank.spotted_mask = inf.spotted_mask = 2 | 1   # 互见（sensing 周期内有效）
            td = add_unit(w, make_unit(w, TD_TPL, 0, 0, (350000, 350000)))
            td.elements[0].facing = 45
            add_unit(w, make_unit(w, INF_TPL, 1, 1, (350000, 330000))).spotted_mask = 1
            b = add_unit(w, make_unit(w, BATT_TPL, 1, 1, (600000, 600000)))
            for e in b.elements:
                e.mode = Mode.INDIRECT
            b.deploy_state = DeployState.DEPLOYED
            cmd_fire_mission(w, b, FireMissionForm.LINE,
                             ((450000, 450000), (480000, 450000)), 1,
                             SalvoMode.HALF, 0)
            return w

        w1, w2 = rich(42), rich(42)
        for _ in range(80):
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(self._fingerprint(w1), self._fingerprint(w2))
        # 非平凡前提：直射已耗弹（坦克首群 tick4 发射）、曲射声测痕迹在案、
        # HALF 任务 12 发（2 门×6 轮、reload 10）约 51 tick 打完销毁
        ws = w1.units[0].elements[0].weapon_states[0]
        self.assertLess(ws.ammo_left, 10)                  # 直射已耗弹
        self.assertEqual(len(w1.sound_tracks), 1)          # 曲射声测痕迹在案
        batt = w1.units[4]
        self.assertIsNone(batt.fire_mission)               # 任务打完销毁（方案10）
        self.assertEqual([e.weapon_states[0].ammo_left for e in batt.elements],
                         [0, 0, 6])                        # 半轮：第 3 门未动


# ══ ⑤块（2026-10-02）：§F1 落点结算 + §F2 生命周期完整体 + system_projectiles 接线 ══

CFG_SNIPER_CERTAIN = BalanceConfig(sniper_base_prob_bp=10000)   # 未掩护 prob=10000 必中
CFG_SNIPER_ZERO = BalanceConfig(sniper_base_prob_bp=0)
CFG_SNIPER_COVER0 = BalanceConfig(sniper_base_prob_bp=10000,
                                  sniper_cover_mult_bp=0)        # 有掩护→prob 0 必不中


class TestResolveHitDirect(unittest.TestCase):
    """§F1 :321-346 地面命中：装甲面链（v1.7 覆盖序）/KE 曲线锚点/暴击 CRIT 通道/
    失的守卫 B9/班火力乘区/面压制。KE6 pen 恒 6、dmg 10、射手 MECH（factor 10000）。"""

    def _world_pair(self, shooter_pos, tgt_pos, tgt_tpl=ARMORED_TPL):
        w = make_world(3)
        shooter = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, shooter_pos))
        tgt = add_unit(w, make_unit(w, tgt_tpl, 1, 1, tgt_pos))
        return w, shooter.elements[0], tgt.elements[0]

    def test_facing_front_midband_rear_side(self):
        # ARMORED ke front=8/side=5/rear=3、facing 0（北）：
        # 正面（南射，approach 0）：pen6<8、12≥8 → 中段 (54−32)*1000//40=550‰ → 10*550//1000=5
        # 尾面（北射，approach 180）：6≥3 → 1000‰ → 10；侧面（东射，approach 270）：6≥5 → 10
        w, se, te = self._world_pair((0, 0), (0, 5000))
        resolve_hit(w, mk_proj(w, se, KE6, dest=te.pos, pos=(0, 0), hit_target=te))
        self.assertEqual(te.hp_current, 20 - 5)                  # FRONT 中段锚点
        w, se, te = self._world_pair((0, 10000), (0, 5000))
        resolve_hit(w, mk_proj(w, se, KE6, dest=te.pos, pos=(0, 10000), hit_target=te))
        self.assertEqual(te.hp_current, 20 - 10)                 # REAR
        w, se, te = self._world_pair((5000, 5000), (0, 5000))
        resolve_hit(w, mk_proj(w, se, KE6, dest=te.pos, pos=(5000, 5000), hit_target=te))
        self.assertEqual(te.hp_current, 20 - 10)                 # SIDE

    def test_bounce_zero_damage_and_no_crit_draw(self):
        # KE3 pen3：3*2=6 < front8 → 跳弹 0 伤（hp 不动）；D071 全拆后 MECH 命中
        # 零暴击掷——CRIT 通道零消费〔勘正 2026-10-07：原注「roll_crit prob=0
        # 短路（prob<=0 先于 chance_bp 判）」系拆除前机理——已随生产端退役〕
        w, se, te = self._world_pair((0, 0), (0, 5000))
        before = channel_states(w)
        resolve_hit(w, mk_proj(w, se, KE3, dest=te.pos, pos=(0, 0), hit_target=te))
        self.assertEqual(te.hp_current, 20)
        self.assertEqual(channel_states(w), before)

    def test_garrison_overrides_to_rear(self):
        # v1.7 覆盖序（驻楼→转向→顶攻→角度）：南射本为 FRONT（5 伤），驻楼强制 REAR（10 伤）
        w, se, te = self._world_pair((0, 0), (0, 5000))
        te.garrison_in = Building(id=1, pos=te.pos, hp=9)
        resolve_hit(w, mk_proj(w, se, KE6, dest=te.pos, pos=(0, 0), hit_target=te))
        self.assertEqual(te.hp_current, 20 - 10)

    def test_rotating_overrides_to_side(self):
        # R-09：转向中（无炮塔 fire_arc<360）→ SIDE；南射本为 FRONT（中段 5），SIDE(5) 6≥5 → 10
        w = make_world(3)
        shooter = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (0, 0)))
        tgt = add_unit(w, make_unit(w, ARC_ARMOR_TPL, 1, 1, (0, 5000)))
        te = tgt.elements[0]
        te.rotating = True
        resolve_hit(w, mk_proj(w, shooter.elements[0], KE6, dest=te.pos,
                               pos=(0, 0), hit_target=te))
        self.assertEqual(te.hp_current, 20 - 10)

    def test_mech_hit_zero_crit_zero_crit_draw(self):
        # D071 全拆（2026-10-07 发起人拍板「全拆+留口子」）负锚——前身
        # test_mech_crit_on_crit_channel_only（旧链 REAR 满伤 10 → prob=10000 必暴击、
        # below(3) 掷 CRIT 通道）随拆重锚：MECH 命中伤害链不动（REAR 满伤 10）、
        # crit 槽恒空（四槽无产出者=口子①枚举预留）、CRIT 通道零消费（口子③
        # 通道号保留=掷骰面退役自证）；HIT/SCATTER/SNIPER 等七通道全不动
        w, se, te = self._world_pair((0, 10000), (0, 5000))
        before = channel_states(w)
        resolve_hit(w, mk_proj(w, se, KE6, dest=te.pos, pos=(0, 10000), hit_target=te))
        self.assertEqual(te.hp_current, 10)                      # 20−10（REAR 满伤不动）
        self.assertEqual(len(te.crit), 0)                        # 零暴击产出（恒空 dict）
        after = channel_states(w)
        self.assertEqual(after["CRIT"], before["CRIT"])
        for name in ("HIT", "SCATTER", "SPOT", "SNIPER", "SONAR", "ECONOMY", "AIR"):
            self.assertEqual(after[name], before[name], name)

    def test_infantry_no_crit_and_squad_factor(self):
        # 步枪班 5/10 血射手（factor 5000）：对无甲步兵 10*1000//1000*5000//10000=5；
        # INFANTRY 目标无 crit 槽门〔D071 全拆后：MECH 亦零掷——该门已随生产端
        # 退役，断言不变〕——CRIT 通道不动
        w = make_world(3)
        shooter = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        shooter.elements[0].hp_current = 5
        tgt = add_unit(w, make_unit(w, INF_TPL, 1, 1, (0, 5000)))
        te = tgt.elements[0]
        before = channel_states(w)
        resolve_hit(w, mk_proj(w, shooter.elements[0], KE6, dest=te.pos,
                               pos=(0, 0), hit_target=te))
        self.assertEqual(te.hp_current, 10 - 5)
        self.assertEqual(channel_states(w)["CRIT"], before["CRIT"])

    def test_dead_target_is_miss(self):
        # B9：目标飞行中阵亡 → 落空 RETURN（无伤害无压制）
        w, se, te = self._world_pair((0, 0), (0, 5000))
        te.unit.elements.remove(te)
        resolve_hit(w, mk_proj(w, se, KE6, dest=te.pos, pos=(0, 0), hit_target=te))
        self.assertEqual(te.hp_current, 20)
        self.assertEqual(te.suppression, 0)

    def test_building_branch_vs_fort(self):
        # 直射建筑：×vs_fort 2000‰、无装甲曲线；dmg=10*2000//1000*10000//10000=20
        # → hp 30−20=10；溅射圈内（dist 1000 ≤ max(2500,2000)）步兵吃压制
        # falloff(1000,2500)=10000−1000*8000//5000=8400 → 10*8400//10000=8
        w = make_world(3)
        shooter = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (0, 0)))
        b = Building(id=1, pos=(0, 5000), hp=30)
        w.buildings.append(b)
        bystander = add_unit(w, make_unit(w, INF_TPL, 1, 1, (1000, 5000)))
        resolve_hit(w, mk_proj(w, shooter.elements[0], SIEGE_W, dest=b.pos,
                               pos=(0, 0), hit_target=b))
        self.assertEqual(b.hp, 10)
        self.assertEqual(bystander.elements[0].suppression, 8)
        self.assertIn(b, w.buildings)                            # 未塌不出表


class TestResolveSniper(unittest.TestCase):
    """§F1 :348-371 R-02 概率结算：两掷杀 1~2 人 / tally≥3 灭班 / v1.4 实杀计数 /
    singleSquadCard 概率灭排 / 掩护旁表 / 无班元素回退 / SNIPER 通道独占。"""

    def _sniped(self, seed, tgt_tpl, cfg=CONFIG, cover=False):
        w = make_world(seed)
        tgt = add_unit(w, make_unit(w, tgt_tpl, 1, 1, (0, 0)))
        shooter = add_unit(w, make_unit(w, SNIPER_TPL, 0, 0, (3000, 0)))
        if cover:
            w.cover_by_target[tgt.id] = [shooter]
        p = mk_proj(w, shooter.elements[0], SNIPER_W, dest=tgt.elements[0].pos,
                    hit_target=tgt.elements[0])
        return w, tgt, shooter, p

    def test_two_certain_kills_then_tally_destroys_squad(self):
        # cfg prob=10000：第一发 kills=2 → hp 8/tally 2；第二发 hp 6/tally 4≥3
        # → 灭最低血班（本班 hp6）→ 全灭 alive=False、tally 4−3=1
        w, tgt, shooter, p = self._sniped(7, INF_TPL, CFG_SNIPER_CERTAIN)
        resolve_hit(w, p, CFG_SNIPER_CERTAIN)
        self.assertEqual(tgt.elements[0].hp_current, 10 - 2)
        self.assertEqual(tgt.r02_kill_tally, 2)
        resolve_hit(w, p, CFG_SNIPER_CERTAIN)
        self.assertEqual(tgt.elements, [])
        self.assertFalse(tgt.alive)
        self.assertEqual(tgt.r02_kill_tally, 1)

    def test_actual_kills_clamped_to_hp_v14(self):
        # v1.4：残班 hp1 吃 2 掷 → actual=MIN(2,1)=1 → 灭班、tally 记 1（非掷骰值 2）；
        # 存活元素空集 → 灭班支防御跳过（无异常）
        w, tgt, shooter, p = self._sniped(7, INF_TPL, CFG_SNIPER_CERTAIN)
        tgt.elements[0].hp_current = 1
        resolve_hit(w, p, CFG_SNIPER_CERTAIN)
        self.assertEqual(tgt.elements, [])
        self.assertEqual(tgt.r02_kill_tally, 1)

    def test_cover_table_consulted(self):
        # 同 seed 两世界：有掩护键 + cover_mult=0 → prob=0 必不中（hp 不动）；
        # 无掩护键同 cfg → prob=10000 必中 2 人——旁表读取与乘数的确定性分离锚点。
        # 两种情况 SNIPER 通道各耗 2 掷（chance_bp 无条件抽签）
        w1, tgt1, _, p1 = self._sniped(9, INF_TPL, CFG_SNIPER_COVER0, cover=True)
        before1 = channel_states(w1)
        resolve_hit(w1, p1, CFG_SNIPER_COVER0)
        self.assertEqual(tgt1.elements[0].hp_current, 10)
        self.assertEqual(tgt1.r02_kill_tally, 0)
        self.assertNotEqual(channel_states(w1)["SNIPER"], before1["SNIPER"])
        w2, tgt2, _, p2 = self._sniped(9, INF_TPL, CFG_SNIPER_COVER0)
        resolve_hit(w2, p2, CFG_SNIPER_COVER0)
        self.assertEqual(tgt2.elements[0].hp_current, 8)

    def test_zero_prob_no_kills(self):
        w, tgt, shooter, p = self._sniped(9, INF_TPL, CFG_SNIPER_ZERO)
        resolve_hit(w, p, CFG_SNIPER_ZERO)
        self.assertEqual(tgt.elements[0].hp_current, 10)
        self.assertEqual(tgt.r02_kill_tally, 0)

    def test_single_squad_card_whole_element(self):
        # singleSquadCard：单掷、命中即整班灭（hp_current 全扣）
        w, tgt, shooter, p = self._sniped(7, CMD_SQUAD_TPL, CFG_SNIPER_CERTAIN)
        resolve_hit(w, p, CFG_SNIPER_CERTAIN)
        self.assertEqual(tgt.elements, [])
        self.assertFalse(tgt.alive)
        self.assertEqual(tgt.r02_kill_tally, 0)                  # 灭排支不记 tally

    def test_fallback_all_elements_for_gun_crew(self):
        # 无 SQUAD 元素单位（牵引炮班）：回退全部元素，kills 打 elements[0]
        w, tgt, shooter, p = self._sniped(7, MORTAR_TPL, CFG_SNIPER_CERTAIN)
        resolve_hit(w, p, CFG_SNIPER_CERTAIN)
        self.assertEqual(tgt.elements[0].hp_current, 5 - 2)
        self.assertEqual(tgt.r02_kill_tally, 2)

    def test_sniper_channel_only(self):
        w, tgt, shooter, p = self._sniped(11, INF_TPL, CFG_SNIPER_CERTAIN)
        before = channel_states(w)
        resolve_hit(w, p, CFG_SNIPER_CERTAIN)
        after = channel_states(w)
        self.assertNotEqual(after["SNIPER"], before["SNIPER"])
        for name in ("HIT", "SCATTER", "SPOT", "CRIT", "SONAR", "ECONOMY", "AIR"):
            self.assertEqual(after[name], before[name], name)


class TestResolveMelee(unittest.TestCase):
    """§F1 :373-380 近战：AMB-05 绕装甲曲线 / 1800‰ 加成 / 政委 MELEE 光环 GAP-13 /
    点压制 / 零掷骰。武器 damage 5、power 7。"""

    def _melee_world(self, seed=3, commissar=False):
        w = make_world(seed)
        cav = add_unit(w, make_unit(w, CAVALRY_TPL, 0, 0, (0, 0)))
        tgt = add_unit(w, make_unit(w, ARMOURED_INF_TPL, 1, 1, (0, 1000)))
        if commissar:
            add_unit(w, make_unit(w, COMMISSAR_TPL, 0, 0, (500, 0)))  # 距靶 ≈1118 ≤ 5000
        return w, cav.elements[0], tgt.elements[0]

    def test_bonus_1800_bypasses_armor(self):
        # bonus = 1800*10000//10000=1800 → dmg = 5*1800//1000=9（armor_he=10 满甲
        # 被绕过——走 HE 曲线则 pen0 → 0 伤）；压制 7*1000//1000=7
        w, ce, te = self._melee_world()
        before = channel_states(w)
        resolve_hit(w, mk_proj(w, ce, MELEE5, dest=te.pos, hit_target=te))
        self.assertEqual(te.hp_current, 10 - 9)
        self.assertEqual(te.suppression, 7)
        self.assertEqual(channel_states(w), before)              # 近战零掷骰

    def test_commissar_aura_pushes_over_kill(self):
        # 光环 +1500bp：bonus=1800*11500//10000=2070 → dmg=5*2070//1000=10 恰满血
        # → 灭班（无光环时 9 伤存活——边界锚点）
        w, ce, te = self._melee_world(commissar=True)
        resolve_hit(w, mk_proj(w, ce, MELEE5, dest=te.pos, hit_target=te))
        self.assertEqual(te.unit.elements, [])
        self.assertFalse(te.unit.alive)


class TestResolveBlast(unittest.TestCase):
    """§F1 :402-412 曲射落点：AMB-01 衰减（span=2×半径）/含等号边界/敌我不分/
    班火力乘区/MECH 暴击 CRIT/点压制全值/SMOKE 烟区 B4/建筑 vs_fort 直扣。
    HE20：dmg 20、blast 4000（span 8000 → falloff=10000−d）、power 10。"""

    def _world(self, seed=3):
        w = make_world(seed)
        how = add_unit(w, make_unit(w, HOW20_TPL, 0, 0, (0, 0)))
        return w, how.elements[0]

    def test_falloff_anchors_and_inclusive_edge(self):
        # d=2000 → 20*8000//10000=16（MECH hp20→4）；d=4000 边界含 → 12（→8）；
        # d=4001 界外 → 不动。D071 全拆（2026-10-07）重锚：爆破受击 MECH 零暴击
        # 零掷（原「每受击元素各掷 CRIT、dmg≥9 必暴击」生产块已删）——CRIT 通道
        # 零消费、crit 槽恒空；界外锚保留
        w, how = self._world()
        dest = (200000, 200000)
        t2 = add_unit(w, make_unit(w, ARMORED_TPL, 1, 1, (202000, 200000)))
        t4 = add_unit(w, make_unit(w, ARMORED_TPL, 1, 1, (204000, 200000)))
        tout = add_unit(w, make_unit(w, ARMORED_TPL, 1, 1, (204001, 200000)))
        before = channel_states(w)
        resolve_blast(w, mk_proj(w, how, HE20, dest=dest, will_hit=False,
                                 trajectory=Trajectory.BALLISTIC))
        self.assertEqual(t2.elements[0].hp_current, 20 - 16)
        self.assertEqual(t4.elements[0].hp_current, 20 - 12)     # 边界含等号
        self.assertEqual(tout.elements[0].hp_current, 20)
        self.assertEqual(len(t2.elements[0].crit), 0)            # 零暴击产出
        self.assertEqual(t2.elements[0].suppression, 10)         # 点压制全值（不衰减）
        after = channel_states(w)
        self.assertEqual(after["CRIT"], before["CRIT"])
        for name in ("HIT", "SCATTER", "SPOT", "SNIPER", "SONAR", "ECONOMY", "AIR"):
            self.assertEqual(after[name], before[name], name)
        self.assertEqual(tout.elements[0].crit, {})              # 界外亦零掷（锚保留）

    def test_friendly_fire_and_squad_factor(self):
        # 敌我不分（自由落体砸落点双方）：己方步兵贴点满衰减 20 伤灭班；
        # 半血步兵射手 factor 5000 → MECH@2000 处 16*5000//10000=8
        w = make_world(5)
        inf_shooter = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        inf_shooter.elements[0].hp_current = 5
        friend = add_unit(w, make_unit(w, INF_TPL, 0, 0, (200000, 200000)))
        mech = add_unit(w, make_unit(w, ARMORED_TPL, 1, 1, (202000, 200000)))
        resolve_blast(w, mk_proj(w, inf_shooter.elements[0], HE20,
                                 dest=(200000, 200000), will_hit=False,
                                 trajectory=Trajectory.BALLISTIC))
        self.assertEqual(friend.elements, [])                    # 己方照吃
        self.assertFalse(friend.alive)
        self.assertEqual(mech.elements[0].hp_current, 20 - 8)

    def test_smoke_shell_spawns_zone(self):
        # B4：SMOKE 弹 → SmokeZone(center=dest, radius=cfg 3000, ttl=600)；无伤害
        w, how = self._world()
        bystander = add_unit(w, make_unit(w, INF_TPL, 1, 1, (200000, 200000)))
        resolve_blast(w, mk_proj(w, how, SMOKE_W, dest=(200000, 200000),
                                 will_hit=False, trajectory=Trajectory.BALLISTIC))
        self.assertEqual(len(w.smoke_zones), 1)
        z = w.smoke_zones[0]
        self.assertEqual((z.center, z.radius_cm, z.ttl_ticks),
                         ((200000, 200000), 3000, 600))
        self.assertEqual(bystander.elements[0].hp_current, 10)

    def test_buildings_hit_and_collapse(self):
        # 建筑按 weapon vs_fort 直扣（无衰减无暴击）：20*1000//1000=20 → hp 30→10；
        # 再一发 → 塌楼出表；界外建筑不动；塌楼驻军清引用 + building_collapse_dmg
        w, how = self._world()
        dest = (200000, 200000)
        b1 = Building(id=1, pos=dest, hp=30)
        b2 = Building(id=2, pos=(210000, 200000), hp=30)         # 界外（>4000）
        w.buildings.extend([b1, b2])
        cfg = BalanceConfig(building_collapse_dmg=3)
        resolve_blast(w, mk_proj(w, how, HE20, dest=dest, will_hit=False,
                                 trajectory=Trajectory.BALLISTIC), cfg)
        self.assertEqual(b1.hp, 10)
        self.assertEqual(b2.hp, 30)
        garrison_unit = add_unit(w, make_unit(w, INF_TPL, 1, 1, (100000, 100000)))
        ge = garrison_unit.elements[0]
        ge.garrison_in = b1
        b1.garrisoned.append(ge)
        resolve_blast(w, mk_proj(w, how, HE20, dest=dest, will_hit=False,
                                 trajectory=Trajectory.BALLISTIC), cfg)
        self.assertNotIn(b1, w.buildings)                        # hp 10−20≤0 → 塌
        self.assertEqual(b1.garrisoned, [])
        self.assertIsNone(ge.garrison_in)
        self.assertEqual(ge.hp_current, 10 - 3)                  # 塌楼伤（cfg 3）
        self.assertIn(b2, w.buildings)


class TestDestroyElementCascade(unittest.TestCase):
    """§F2 :451-484 R-07 车毁连带（按元素去重/向上取整式/旁落位）/物资清零/驻楼清理/
    装载请求撤销谓词/拖曳连带 GAP-24/全灭注销 unregister_unit_refs。"""

    def test_same_card_crew_damage_ceil(self):
        # (hp*(1000−400)+999)//1000：hp10 → 6999//1000=6 → 剩 4；hp1 → 1599//1000=1
        # → 恰灭（向上取整式——M14/G22 锚点）；班旁落车毁位、mounted_in 摘除
        w = make_world(3)
        carrier = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (5000, 5000)))
        ce = carrier.elements[0]
        squad = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        s = squad.elements[0]
        s.mounted_in = ce
        from sovs.sim.combat import apply_damage
        apply_damage(w, ce, 999)
        self.assertEqual(ce.unit.elements, [])
        self.assertIsNone(s.mounted_in)
        self.assertEqual(s.pos, ce.pos)                          # 旁落位（同点位）
        self.assertEqual(s.hp_current, 10 - 6)
        s.hp_current = 1
        ce2 = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (0, 0))).elements[0]
        s.mounted_in = ce2
        apply_damage(w, ce2, 999)
        self.assertEqual(squad.elements, [])                     # 1 血班恰灭
        self.assertFalse(squad.alive)

    def test_cross_card_dedup_single_settlement(self):
        # 跨卡班（cargo_units + mounted_in 双挂）按元素去重只结一次：hp10 → 4
        # （双结则 10→4→1）；单位级 pos 重定位 + move_path 清空
        w = make_world(3)
        carrier = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (5000, 5000)))
        ce = carrier.elements[0]
        squad = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        squad.move_path = [(1, 1)]
        squad.elements[0].mounted_in = ce
        ce.cargo_units = [squad]
        from sovs.sim.combat import apply_damage
        apply_damage(w, ce, 999)
        self.assertEqual(squad.elements[0].hp_current, 10 - 6)   # 一次 60%
        self.assertEqual(squad.pos, ce.pos)
        self.assertEqual(squad.move_path, [])
        self.assertEqual(ce.cargo_units, [])

    def test_supply_slots_zeroed_on_destroy(self):
        w = make_world(3)
        truck = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (0, 0)))
        te = truck.elements[0]
        te.supply_weight_g = 8
        from sovs.sim.combat import apply_damage
        apply_damage(w, te, 999)
        self.assertEqual(te.supply_weight_g, 0)

    def test_garrison_ref_cleanup(self):
        w = make_world(3)
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        ie = inf.elements[0]
        b = Building(id=1, pos=(0, 0), hp=9)
        ie.garrison_in = b
        b.garrisoned.append(ie)
        from sovs.sim.combat import apply_damage
        apply_damage(w, ie, 99)
        self.assertEqual(b.garrisoned, [])
        self.assertIsNone(ie.garrison_in)

    def test_mount_request_revocation_predicates(self):
        # 仅撤"本元素为载具"或"申请班已全灭"（M12/G26 + ㉑A 元素粒度）
        w = make_world(3)
        carrier = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (0, 0)))
        ce = carrier.elements[0]
        other = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (9000, 9000)))
        oe = other.elements[0]
        s_alive = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        s_dead_unit = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        dead_elem = s_dead_unit.elements[0]
        s_dead_unit.elements.remove(dead_elem)
        w.mount_requests = [
            MountRequest(squad_element=s_alive.elements[0], carrier=ce, ticks_left=50),
            MountRequest(squad_element=s_alive.elements[0], carrier=oe, ticks_left=50),
            MountRequest(squad_element=dead_elem, carrier=oe, ticks_left=50)]
        from sovs.sim.combat import apply_damage
        apply_damage(w, ce, 999)
        self.assertEqual(len(w.mount_requests), 1)
        self.assertIs(w.mount_requests[0].carrier, oe)           # 无关请求保留

    def test_tow_release_on_destroy(self):
        w = make_world(3)
        tower = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (0, 0))).elements[0]
        gun = add_unit(w, make_unit(w, MORTAR_TPL, 0, 0, (1000, 0))).elements[0]
        tower.towed = TowState.TOWING
        gun.towed = TowState.TOWED
        w.tow_pairs.append(TowPair(tower_elements=[tower], towed_element=gun))
        from sovs.sim.combat import apply_damage
        apply_damage(w, tower, 999)
        self.assertEqual(w.tow_pairs, [])
        self.assertEqual(tower.towed, TowState.NONE)
        self.assertEqual(gun.towed, TowState.NONE)

    def test_full_death_unregisters_refs(self):
        # 全灭：alive=False；信标注销；掩护两角色注销（被掩护整键删 +
        # 掩护者出名单 + 空名单键删除——v1.3 终审遗留闭合）
        w = make_world(3)
        dying = add_unit(w, make_unit(w, SNIPER_TPL, 0, 0, (0, 0)))
        other_protector = add_unit(w, make_unit(w, SNIPER_TPL, 0, 0, (1000, 0)))
        tgt_a = add_unit(w, make_unit(w, INF_TPL, 1, 1, (0, 0)))
        tgt_b = add_unit(w, make_unit(w, INF_TPL, 1, 1, (500, 0)))
        w.cover_by_target[dying.id] = [dying]                    # dying 亦被掩护
        w.cover_by_target[tgt_a.id] = [dying, other_protector]
        w.cover_by_target[tgt_b.id] = [dying]                    # 仅 dying → 空键删
        w.beacon_by_unit[dying.id] = (0, (123, 456))    # 值=(team,pos)——键型适配
        from sovs.sim.combat import apply_damage
        apply_damage(w, dying.elements[0], 99)
        self.assertFalse(dying.alive)
        self.assertNotIn(dying.id, w.cover_by_target)
        self.assertNotIn(dying.id, w.beacon_by_unit)
        self.assertEqual(w.cover_by_target[tgt_a.id], [other_protector])
        self.assertNotIn(tgt_b.id, w.cover_by_target)            # 空键删除
        self.assertIn(tgt_a.id, w.cover_by_target)


class TestApplyDamageResupplyRegistration(unittest.TestCase):
    """§F2 :439-440 带伤登记（⑤块落地）：存活出现缺口 → await_resupply；
    MECH 带伤无弹药缺口不登记（needs_resupply INFANTRY 判据）；幂等不重复。"""

    def test_infantry_wound_registers(self):
        w = make_world(3)
        inf = add_unit(w, make_unit(w, INF_TPL, 0, 0, (0, 0)))
        from sovs.sim.combat import apply_damage
        apply_damage(w, inf.elements[0], 4)
        self.assertEqual(inf.elements[0].hp_current, 6)
        self.assertIn(inf, w.await_resupply)
        apply_damage(w, inf.elements[0], 1)                      # 已登记不重复
        self.assertEqual(w.await_resupply.count(inf), 1)

    def test_mech_wound_alone_not_registered(self):
        w = make_world(3)
        mech = add_unit(w, make_unit(w, ARMORED_TPL, 0, 0, (0, 0)))
        from sovs.sim.combat import apply_damage
        apply_damage(w, mech.elements[0], 5)
        self.assertEqual(mech.elements[0].hp_current, 15)
        self.assertNotIn(mech, w.await_resupply)                 # 非步兵带伤不算缺口


class TestProjectileDispatch(unittest.TestCase):
    """§F8 :1468-1473 system_projectiles 四分派支：BALLISTIC→resolve_blast /
    对空 resolve_hit_aa / will_hit→resolve_hit / ELSE 近失压制。"""

    def test_direct_hit_branch(self):
        w = make_world(3)
        shooter = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (0, 0)))
        tgt = add_unit(w, make_unit(w, INF_TPL, 1, 1, (3000, 0)))
        w.projectiles.append(mk_proj(w, shooter.elements[0], KE6,
                                     dest=tgt.elements[0].pos,
                                     hit_target=tgt.elements[0]))
        system_projectiles(w)
        self.assertEqual(w.projectiles, [])
        self.assertEqual(tgt.elements, [])                       # 无甲 1000‰ → 10 伤灭班
        self.assertFalse(tgt.alive)

    def test_ballistic_branch_blast(self):
        w = make_world(3)
        how = add_unit(w, make_unit(w, HOW20_TPL, 0, 0, (0, 0)))
        mech = add_unit(w, make_unit(w, ARMORED_TPL, 1, 1, (202000, 200000)))
        w.projectiles.append(mk_proj(w, how.elements[0], HE20, dest=(200000, 200000),
                                     will_hit=False,
                                     trajectory=Trajectory.BALLISTIC))
        system_projectiles(w)
        self.assertEqual(w.projectiles, [])
        self.assertEqual(mech.elements[0].hp_current, 20 - 16)   # d=2000 衰减锚点

    def test_ballistic_branch_smoke(self):
        w = make_world(3)
        how = add_unit(w, make_unit(w, HOW20_TPL, 0, 0, (0, 0)))
        w.projectiles.append(mk_proj(w, how.elements[0], SMOKE_W, dest=(100000, 100000),
                                     will_hit=False, dmg_type=DamageType.SMOKE,
                                     trajectory=Trajectory.BALLISTIC))
        system_projectiles(w)
        self.assertEqual(len(w.smoke_zones), 1)
        self.assertEqual(w.smoke_zones[0].ttl_ticks, 600)

    def test_near_miss_branch_suppression_only(self):
        # DIRECT + hit_target None + will_hit False → 仅近失压制（无伤害）
        w = make_world(3)
        shooter = add_unit(w, make_unit(w, SHOOTER_TPL, 0, 0, (0, 0)))
        tgt = add_unit(w, make_unit(w, INF_TPL, 1, 1, (3000, 0)))
        w.projectiles.append(mk_proj(w, shooter.elements[0], HE20,
                                     dest=tgt.elements[0].pos, hit_target=None,
                                     will_hit=False))
        system_projectiles(w)
        self.assertEqual(tgt.elements[0].hp_current, 10)
        self.assertEqual(tgt.elements[0].suppression, 10)        # falloff(0)=10000 全值


class TestFastProjectileDualRun(unittest.TestCase):
    """⑤块接线确定性双跑：快弹坦克（弹速 100000——发射同拍即落）对射步兵，
    30 tick 逐拍比指纹（复用 TestFireMissionDeterminismDualRun 指纹范式）。"""

    def test_dual_run_30_ticks_bit_identical(self):
        def rich(seed):
            w = make_world(seed)
            tank = add_unit(w, make_unit(w, FAST_TANK_TPL, 0, 0, (100000, 100000)))
            inf = add_unit(w, make_unit(w, INF_TPL, 1, 1, (130000, 100000)))
            tank.spotted_mask = 2                                # 互见（单向即可）
            inf.spotted_mask = 1
            return w

        fp = TestFireMissionDeterminismDualRun._fingerprint
        w1, w2 = rich(42), rich(42)
        for _ in range(30):
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(fp(w1), fp(w2))
        # 手推时序：tick1 begin_aim(3) → tick2/3 递减 → tick4 fire_direct（ammo 9、
        # RELOADING 20）→ 同拍 ⑤ 弹丸到达 resolve_hit（KE pen5 对无甲步兵 1000‰ →
        # 10 伤恰灭班）→ 尾拍尸体清扫出表；AMB-14 直射不喂声测；:811 弹药缺口登记
        self.assertEqual([u.template for u in w1.units],
                         [FAST_TANK_TPL])                        # 步兵 tick4 已除名
        ws = w1.units[0].elements[0].weapon_states[0]
        self.assertEqual(ws.ammo_left, 9)
        self.assertEqual(w1.projectiles, [])
        self.assertEqual(w1.sound_tracks, [])
        self.assertIn(w1.units[0], w1.await_resupply)


if __name__ == "__main__":
    unittest.main()
