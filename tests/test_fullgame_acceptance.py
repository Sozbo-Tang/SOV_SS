"""整局验收（最终门）：无头 AI 对 AI 打完整一局（盲部署→实战→结算三相位全程——
2026-10-03 拍板：禁火段取消、部署 60s；D031 胜负输出、无异常）+ 同 seed 双 world
逐 tick 全状态指纹位级相等（照
tests/test_integration.py 的 fingerprint/rich_world/双跑范式，指纹面按八块后的
完整状态容器扩展）+ 多 seed 冒烟（混编卡/渗透/狙击/烟弹/窄射界/磨耗耗弹）。

AI 驱动器（HeadlessAI，本文件内=tests 侧，不进仿真核心、零渲染依赖）：只经
queue_command→consume_commands 接口发令——盲部署相位按卡组序购卡（PurchaseCmd），
实战期发移动/攻击/炮击任务/取消任务令。命令层现状（2026-10-06 PB-56 批① 收口后）：
MoveCmd 已落地（MOVEMENT v1.2 §2.2 issue_move——双方每 100 拍对首个己方单位发
向敌锚点的移动令，单位真实机动、占点归属随之可改写）；AttackCmd 已落地
（§F4 :848 cmd_attack，2026-10-06 PB-56 批①）——本文件各整局场景实测全部被门序
REJECT、武器状态零迁移（探针复核 seed 42/3/11：lean42 12 令/rich3 22 令/
rich11 14 令全部零迁移）——机理=consume_commands 位于 world_tick 首、① system_
timers 的 RELOADING→READY 迁移后 ④ 自动交战链同拍即重新占位（ground_direct），
故 consume 时点武器在有效目标存在期间恒非 READY；目标对超程/未发现时亦被
⑨/④ 门拒——既有整局锚（首弹拍/弹耗/全灭拍/幸存者/裁决）逐位不变，无需重锚；
min_range 内「自动链结构性不接战、手动令唯一交战入口」的对照画像见
TestManualEngageFullGame（PB-56 批① 余三命令整局验收块）；SetModeCmd/
ToggleAmbushCmd/SetStanceCmd 已落地（2026-10-06 PB-56 批① 余三命令——§F6 :1193
cmd_set_element_mode/§F4 :874 cmd_toggle_ambush/§D.7 :261 最小写点）——
FireMissionCmd 默认画像下仍被 cmd_fire_mission 双门第二门 REJECT（AI 不发
SetModeCmd、元素初始 mode=DIRECT）；artillery=True 火支画像（SetMode+
FireMission 使炮击任务真实建立——校射/落点链）见 TestArtilleryMissionFullGame，
三命令合链指纹双跑见 TestCommandChainFullGame。
CancelFireMissionCmd 落地（空任务 no-op）。

锚点写死不自证：相位边界 601/13801（phase_ticks 600/13200 手推）；
购卡算术（点数/份数/出牌序）；首发弹 tick=601+aim 5=606（AIMING 计时手推）；
RNG 通道纪律（SPOT/SONAR/ECONOMY/AIR 全程零消费——sensing/经济/占点零掷骰、
无航空器）；结局数值（幸存者血量/弹药/比分/击杀 tally/弹丸总数/占点归属）为
固定 seed 的确定性观测定锚（2026-10-04 命令层块 MoveCmd 落地后全部重锚——
单位机动改变交战距离/占点改写路径，结局随 seed 重新定观测值）。

正式示范地形图整局验收（PB-58 块③，2026-10-06）：build_map_world 场景工厂
（lean 卡组 + apply_map 挂 data/gen/map_demo_2km.v1.json——200000×100000 与
MAP_SIZE 同幅原位接入，make_world 不动）；HeadlessAI 增 keyword 参数
anchors/move_mode（缺省=既有行为逐位不变）——地图场景用 MARCH 令 + 图内
侧翼敌锚点 MAP_ANCHORS，移动令经 issue_move→_resolve_move_path→真 A*（绕障
航点+沿路 MARCH 道路地板可观测）。指纹面核对留痕：full_fingerprint 不含
path_cache（§D.6 未列实现记账槽、纯派生 memo——键含地形指纹故值确定），
双跑一致性由测试侧额外比对有序 path_cache 条目补面（非改冻结指纹函数）。
边界语义留痕：北部署锚点 (100000,100000) 恰落图界（tile (40,40)=图外）——
起点格豁免可寻出、立位瓦片缺席=类级缺省、以它为终点则直线兜底（pathfind.py
既定口径，登记表 discrepancies 留痕）；地图场景 AI 锚点全图内。
"""
import math
import time
import unittest

from sovs.sim.air import (PHASE_COMBAT, PHASE_DEPLOY, PHASE_SETTLE,
                          AirRole, AirState)
from sovs.sim.air_data import CARD_OBJECTS
from sovs.sim.map_loader import apply_map, load_demo_map
from sovs.sim.pathfind import tile_cost
from sovs.sim.sensing import effective_stealth_x10
from sovs.sim.tables import CONFIG, BalanceConfig
from sovs.sim.tick import (AirAirdropCmd, AirAltCmd, AirCallCmd, AirDisengageCmd,
                           AirEngageAirCmd, AirMoveCmd, AirPatrolCmd,
                           AirRTBCmd, AirStrikeCmd, AttackCmd,
                           CancelFireMissionCmd, DeckSlot, DeployCmd,
                           DismountCmd, FireMissionCmd,
                           FireMissionForm, FormationCmd, GarrisonCmd,
                           issue_group_move, MountCmd, MoveCmd, Objective,
                           PackCmd, PurchaseCmd, SalvoMode, SetModeCmd,
                           SetStanceCmd, ToggleAmbushCmd, TowCmd, UntowCmd,
                           add_unit, begin_aim, fire_permitted, make_unit,
                           make_world, queue_command, world_tick)
from sovs.sim.types import (AltTier, Armor, Building, DamageType, DeployState,
                            ElementTemplate, ElementType, FormationShape,
                            Mode, MoraleState, MoveMode, MovementClass,
                            Stance, TargetDomain, TowState, Trajectory,
                            UnitFlag, UnitTemplate, UnitType, WeaponTemplate,
                            WState)

# 地图：200000×100000 cm——部署锚点 (100000,0)/(100000,100000)，两军相距 100000 cm
# （光学 110000~130000 内互相可见、步枪/炮射程 110000~120000 内可交战；2026-10-04
# 命令层块 MoveCmd 落地后双方首单位真实对进——远距静态对射 + 机动单位改写占点）。
SOUTH = (100000, 0)
NORTH = (100000, 100000)
MAP_SIZE = (200000, 100000)

# 正式示范图（PB-58 块③）——与 MAP_SIZE 同幅 200000×100000（80×40 瓦片×2500cm）：
#   tile_cm 坐标换算 ix=x//2500, iy=y//2500；干道 y≈22 横贯、x=40 纵路 y=1..21、
#   V1 村庄废墟 [34..46]×[15..24]、V2 横带废墟 [28..49]×[31..36]、4 林区旁挂
#   forest_tiles（不减速）、废墟瓦片 speed_bp=cfg.ruin_speed_bp（4000=可通行减速，
#   本图无 bp==0 不可通行瓦片）。图幅与现有整局同尺寸 → 原位替换接入（apply_map
#   对齐 terrain/map_extent/map_center，勘察③「场景工厂构造后赋 w.terrain」先例）。
# 地图场景 AI 敌锚点（图内侧翼——双方首单位斜穿地图，A* 绕障+沿路可观测；
# tile (20,0)/(60,39) 均图内可通行，见护栏锚 test_map_world_anchor_tiles_passable）：
MAP_ANCHORS = ((50000, 1250), (150000, 98750))


# ── 武器/模板（合成测试卡，数值为锚点服务）──

RIFLE_W = WeaponTemplate(
    name="rifle", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    damage=2, salvo=1, aim_time_ticks=5, reload_time_ticks=30, ammo_base=50,
    max_range_cm=120000, dispersion_cm=500, accuracy_base_bp=6000,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    suppression_power=3, reveal_time_ticks=10)
GUN_W = WeaponTemplate(                       # 直射 HE 突击炮：BALLISTIC→resolve_blast 支
    name="he gun", target_mask=TargetDomain.GROUND, damage_type=DamageType.HE,
    pen_min=6, pen_max=6, damage=5, blast_radius_cm=4000, salvo=2,
    aim_time_ticks=8, reload_time_ticks=60, ammo_base=40,
    max_range_cm=110000, dispersion_cm=800, accuracy_base_bp=5500,
    projectile_speed_cm_tick=5000, trajectory=Trajectory.BALLISTIC,
    suppression_power=8, reveal_time_ticks=10)
CANNON_W = WeaponTemplate(                    # 直射 KE 坦克炮（穿甲曲线+暴击掷 CRIT）
    name="cannon", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    pen_min=6, pen_max=9, damage=6, salvo=1, aim_time_ticks=6,
    reload_time_ticks=50, ammo_base=30, max_range_cm=115000,
    dispersion_cm=400, accuracy_base_bp=6200,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    blast_radius_cm=500, suppression_power=5, reveal_time_ticks=10)
SNIPER_W = WeaponTemplate(                    # R-02 狙击（SNIPER 通道首消费者链）
    name="sniper rifle", target_mask=TargetDomain.GROUND,
    damage_type=DamageType.KE, damage=1, salvo=1, aim_time_ticks=10,
    reload_time_ticks=60, ammo_base=40, max_range_cm=120000,
    dispersion_cm=200, accuracy_base_bp=8000,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    combat_style=2, suppression_power=1, reveal_time_ticks=10)
SMOKE_W = WeaponTemplate(                     # 烟弹（SMOKE→SmokeZone 生命周期）
    name="smoke mortar", target_mask=TargetDomain.GROUND,
    damage_type=DamageType.SMOKE, damage=0, salvo=2, aim_time_ticks=8,
    reload_time_ticks=200, ammo_base=20, max_range_cm=110000,
    dispersion_cm=1000, accuracy_base_bp=9000,
    projectile_speed_cm_tick=3000, trajectory=Trajectory.BALLISTIC,
    suppression_power=0)
GRIND_W = WeaponTemplate(                     # 磨耗步枪：低伤高命中，30 发必耗尽→EMPTY
    name="grind rifle", target_mask=TargetDomain.GROUND,
    damage_type=DamageType.KE, damage=1, salvo=1, aim_time_ticks=3,
    reload_time_ticks=20, ammo_base=30, max_range_cm=120000,
    dispersion_cm=300, accuracy_base_bp=9500,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    suppression_power=1, reveal_time_ticks=5)

RIFLE_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                             unit_type=UnitType.INFANTRY, hp_max=10,
                             weapons=(RIFLE_W,))
GUN_ELEM = ElementTemplate(
    element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=12,
    armor_ke=Armor(8, 5, 3, 2), armor_he=Armor(6, 4, 3, 2), weapons=(GUN_W,))
TANK_ELEM = ElementTemplate(
    element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=15,
    armor_ke=Armor(10, 7, 5, 3), armor_he=Armor(8, 6, 4, 3), weapons=(CANNON_W,))
ARC_TANK_ELEM = ElementTemplate(              # 窄射界 120°（R-09 rotate_step/GAP-25 复位）
    element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=25,
    armor_ke=Armor(10, 7, 5, 3), armor_he=Armor(8, 6, 4, 3),
    fire_arc_deg=120, weapons=(CANNON_W,))
CARRIER_ELEM = ElementTemplate(               # 运载元素（seats=2，MIXED 卡开局车载形态）
    element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=15,
    seats=2, weapons=(RIFLE_W,))

RIFLE_TPL = UnitTemplate(
    template_id=301, name="rifle plt", category=1, cost=60,
    element_templates=(RIFLE_ELEM,), optics_ground_cm=120000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT)
GUN_TPL = UnitTemplate(
    template_id=302, name="assault gun", category=3, cost=150,
    element_templates=(GUN_ELEM,), optics_ground_cm=120000, stealth_base=3,
    speed_tier=2, movement_class=MovementClass.TRACK,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.INDIRECT))  # 双职炮（PB-56 批① 余三
    # 命令整局验收扩位——SU_ZIS3 现役唯一 DIRECT;INDIRECT 双位卡先例；无
    # SetModeCmd 时 FireMissionCmd 仍被 cmd_fire_mission 双门第二门 REJECT
    #（元素初始 mode=DIRECT）→ 既有 lean/rich/map 场景锚位级不变）
TANK_TPL = UnitTemplate(
    template_id=303, name="tank", category=2, cost=180,
    element_templates=(TANK_ELEM,), optics_ground_cm=110000, stealth_base=3,
    speed_tier=2, movement_class=MovementClass.TRACK)
ARC_TANK_TPL = UnitTemplate(
    template_id=309, name="arc tank", category=2, cost=180,
    element_templates=(ARC_TANK_ELEM,), optics_ground_cm=110000, stealth_base=3,
    speed_tier=2, movement_class=MovementClass.TRACK, turn_rate_deg=30)
MIXED_TPL = UnitTemplate(
    template_id=304, name="grenadiers", category=1, cost=90,
    element_templates=(RIFLE_ELEM, RIFLE_ELEM, CARRIER_ELEM),
    optics_ground_cm=120000, stealth_base=5, speed_tier=2,
    movement_class=MovementClass.WHEEL)
INFIL_TPL = UnitTemplate(
    template_id=305, name="infiltrators", category=1, cost=30,
    element_templates=(RIFLE_ELEM,), optics_ground_cm=120000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT,
    flags=UnitFlag.CAN_INFILTRATE)
SNIPER_TPL = UnitTemplate(
    template_id=306, name="sniper team", category=1, cost=40,
    element_templates=(ElementTemplate(
        element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
        hp_max=6, weapons=(SNIPER_W,)),),
    optics_ground_cm=130000, stealth_base=7, speed_tier=1,
    movement_class=MovementClass.FOOT, flags=UnitFlag.SINGLE_SQUAD_CARD)
SMOKE_TPL = UnitTemplate(
    template_id=307, name="smoke mortar", category=3, cost=50,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH,
        hp_max=8, weapons=(SMOKE_W,)),),
    optics_ground_cm=120000, stealth_base=3, speed_tier=1,
    movement_class=MovementClass.FOOT)
GRIND_TPL = UnitTemplate(
    template_id=308, name="grind plt", category=1, cost=50,
    element_templates=(ElementTemplate(
        element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
        hp_max=20, weapons=(GRIND_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)
PIN_W = WeaponTemplate(                    # 压制观测炮（士气生命周期场景）：
    name="pin gun", target_mask=TargetDomain.GROUND,   # accuracy=10000 → will_hit
    damage_type=DamageType.KE,             # 恒真（chance_bp(10000) 恒成立）——
    damage=1, salvo=1, aim_time_ticks=5,   # 命中拍序列可全手推、零 seed 依赖；
    reload_time_ticks=30, ammo_base=4,     # suppression_power=55+周期 35 拍
    max_range_cm=200000, dispersion_cm=100,  # （aim5+reload30）+衰减 1/tick →
    accuracy_base_bp=10000,                # 压制 55→75→95→100 四发自然过全档
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    suppression_power=55, reveal_time_ticks=5)
SUPPRESS_TPL = UnitTemplate(               # 攻方（队1 北）：4 发压制炮、恒命中
    template_id=310, name="pin battery", category=1, cost=60,
    element_templates=(ElementTemplate(
        element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
        hp_max=150, weapons=(PIN_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)
BULWARK_TPL = UnitTemplate(                # 守方（队0 南）：厚血无武器靶——零反击
    template_id=311, name="bulwark", category=1, cost=60,   # （攻方压制恒 0 不
    element_templates=(ElementTemplate(                    # 搅浑观测）、4×damage1 打不死
        element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
        hp_max=200),),                     # （开敞观测面）
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)

# ── PB-56 批① 余三命令整局验收载体（2026-10-06；template_id 330/331 段）──

# min_range 恒命中步枪（攻击令×自动链对照载体）：min 60000 使 select_target
# 候选门结构性不接战（§F4 :712 min≤d≤max）而 cmd_attack 无 min 门（:868 字面
# 仅上限——勘察留痕），accuracy 10000 → will_hit 恒真（命中节拍全手推零 seed
# 依赖——PIN_W 同款手法）
MIN_SURE_W = WeaponTemplate(
    name="min sure rifle", target_mask=TargetDomain.GROUND,
    damage_type=DamageType.KE, damage=3, salvo=1, min_range_cm=60000,
    max_range_cm=200000, aim_time_ticks=5, reload_time_ticks=30,
    ammo_base=40, dispersion_cm=100, accuracy_base_bp=10000,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT)
MIN_SHOOTER_TPL = UnitTemplate(            # 攻击令主动交战载体（TestManualEngage）
    template_id=330, name="min shooter", category=1, cost=50,
    element_templates=(ElementTemplate(
        element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
        hp_max=10, weapons=(MIN_SURE_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)
AMBUSH_MIN_TPL = UnitTemplate(             # 三命令合链载体（TestCommandChain）：
    template_id=331, name="ambush min plt", category=1, cost=50,   # CAN_AMBUSH 位
    element_templates=(ElementTemplate(    # 合成置位（现役 0 卡置位——数据侧脱节
        element_type=ElementType.SQUAD,    # 登记）+ min 60000（自动链不接战=发射
        unit_type=UnitType.INFANTRY,       # 归因唯一：只可能来自手动令）
        hp_max=10, weapons=(MIN_SURE_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT, flags=UnitFlag.CAN_AMBUSH)

# ── PB-56 批② 机动链整局验收载体（2026-10-06 拖曳展开块；template_id 332/333 段，
#    GUN_TPL 扩位先例：新合成模板零命令时不参与既有场景=既有锚位级不变）──

TRACTOR_FG_TPL = UnitTemplate(             # 牵引车（DIRECT|TOW 位、15t——SU_TRUCK
    template_id=332, name="fg tractor",    # 同构；现役 fullgame 模板集无 TOW 位卡）
    category=4, cost=30,
    element_templates=(ElementTemplate(
        element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=10),),
    optics_ground_cm=120000, stealth_base=3, speed_tier=3,
    movement_class=MovementClass.WHEEL,
    mode_set=((1 << Mode.DIRECT) | (1 << Mode.TOW)), tow_tonnage=15)
AT_GUN_FG_W = WeaponTemplate(              # 须展开武器（③ 门/fire 恢复整局面锚）
    name="fg at gun", target_mask=TargetDomain.GROUND,
    damage_type=DamageType.KE, damage=4, salvo=1, aim_time_ticks=5,
    reload_time_ticks=20, ammo_base=10, max_range_cm=150000,
    accuracy_base_bp=9500, projectile_speed_cm_tick=20000,
    trajectory=Trajectory.DIRECT, needs_deployed=True)
AT_GUN_FG_TPL = UnitTemplate(              # 须展开牵引炮（own 13 / 展开·收装 300）
    template_id=333, name="fg at gun", category=3, cost=60,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=12,
        weapons=(AT_GUN_FG_W,)),),
    optics_ground_cm=120000, stealth_base=3, speed_tier=1,
    movement_class=MovementClass.FOOT,
    deploy_time_ticks=300, pack_time_ticks=300, own_weight_tons=13)

# ── PB-56 批③ Formation 族整局验收载体（2026-10-06；template_id 334/335 段，
#    GUN_TPL 扩位先例：新合成模板零命令时不参与既有场景=既有锚位级不变）──

FM_PLT_TPL = UnitTemplate(                 # 编队排（4 车楔形——§2.8 楔形锚 n≥4 可观测；
    template_id=334, name="fmt plt",        # 无武器=单队无对抗零掷骰；档 3 WHEEL：
    category=2, cost=120,                   # 脱离编组后 70×5000//10000=35cm/拍）
    element_templates=(ElementTemplate(
        element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=10),) * 4,
    optics_ground_cm=120000, stealth_base=3, speed_tier=3,
    movement_class=MovementClass.WHEEL)
FM_ESC_TPL = UnitTemplate(                 # 护卫车（同 WHEEL 类=类缺省 bp 相等——
    template_id=335, name="fmt escort",     # cap 钳制下 v 恒相等可断言；档 1：
    category=2, cost=40,                    # 组令 cap=MIN(3,1)=1 → 双方 12cm/拍）
    element_templates=(ElementTemplate(
        element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=10),),
    optics_ground_cm=120000, stealth_base=3, speed_tier=1,
    movement_class=MovementClass.WHEEL)


# ── AI 驱动器（tests 侧；决策只读 world 确定性状态，零掷骰零渲染）──

# 纯航空画像呼叫脚本（空中闭环·块2；(team, tick, air_data 卡键, payload)——
# 队0=Il-2M 攻击机（BOMB 2 载荷+扫射档随机体）/Yak-9 战斗机；队1=Pe-2 轰炸机
# （BOMB 4——salvo 2×两次出击=弹尽自动 RTB 链 GAP3-02）/Fw 190A 战斗机（CAP 对位）
AIR_CALL_SCRIPTS = (
    (0, 100, "IL2M", {"BOMB": 2}),
    (0, 120, "YAK9", {}),
    (1, 100, "PE2", {"BOMB": 4}),
    (1, 120, "FW190A", {}),
)

class HeadlessAI:
    """最小确定性虚拟玩家：每 tick 决策→queue_command（只经 consume_commands 落地）。

    策略（固定节拍、按列表序取首个——确定性）：
    - 盲部署相位：每 50 tick 按卡组序购首张可负担且有余额的卡（PurchaseCmd）；
    - 实战期：每 100 tick 对首个己方单位发移动令（向敌锚点）与攻击令（首敌元素）、
      对火支类（category=3）单位发 POINT 炮击任务令；每 500 tick 发取消任务令。
    移动令已落地（2026-10-04 命令层块）；攻击令已落地（2026-10-06 PB-56 批①
    cmd_attack——默认画像下实测被门序 REJECT、武器状态零迁移，机理见模块
    docstring；min_range 内自动链结构性不接战的手动交战画像见
    TestManualEngageFullGame）。

    PB-58 块③（2026-10-06）增 keyword 参数（缺省=既有行为逐位不变）：
    - anchors=(south, north)：敌锚点对；None=缺省 (SOUTH, NORTH)——地图场景传
      图内侧翼锚点（MAP_ANCHORS），使整局移动令斜穿示范图（A* 绕障可观测）；
    - move_mode：移动令模式；缺省 NORMAL——地图场景传 MARCH（勘察③「AI 加一档
      MARCH 令」：prefer_road 寻路 + 道路地板速度均只走 MARCH，NORMAL 观测不到）。

    PB-56 批① 余三命令整局验收（2026-10-06）增 keyword 参数（缺省=既有行为
    逐位不变——同 anchors/move_mode 先例）：
    - artillery=False：**火支 AI 画像**——实战期只发炮击任务令（SetModeCmd
      逐元素 INDIRECT + FireMissionCmd POINT 敌锚点，每单位仅发一次〔issued
      集合记 unit.id——重发将重置 shots/calib 破坏耗尽节拍〕；不发移动/攻击/
      取消令——炮击链节拍可全手推）。任务令在 SetModeCmd 未落地时被
      cmd_fire_mission 双门 REJECT 的⑧块留痕态就此转活（元素初始 mode=DIRECT
      → SetModeCmd=唯一解锁钥匙）。GUN_TPL 已扩 DIRECT|INDIRECT 双位。
    - send_attack=True：攻击令开关——False 供 TestManualEngageFullGame 作
      「无攻击令对照组」（自动交战链对照锚：min_range 内自动链结构性不接战）。

    PB-56 批② 机动链整局验收（2026-10-06 拖曳展开块）增 keyword 参数（缺省
    =既有行为逐位不变——同先例）：
    - motorized=False：**车载机动画像**——固定拍脚本驱动首个「班+座」混编单位
      （MIXED 卡）：开局预挂（spawn_step R-07）→ t700 移动令（车载班随车机动）
      → t950 DismountCmd（下车）→ t951 MountCmd（再上车，200 拍倒计时）；
      机动链六命令中 Mount/Dismount 半边的整局面载体（TestMotorizedFullGame）。
    - tractor=False：**拖曳展开画像**——固定拍脚本：t1 SetModeCmd(TOW) → t2
      TowCmd → t3 移动令（锁速+随动）→ t200 UntowCmd（被拖侧入口）→ t201
      DeployCmd（重展开 300 拍）→ t510 PackCmd（收装 300 拍）——Tow/Untow/
      Deploy/Pack 四命令整局面载体（TestTowDeployFullGame）。

    PB-56 批③ Formation 族整局验收（2026-10-06）增 keyword 参数（缺省=既有
    行为逐位不变——同先例）：
    - formation=False：**编队行军画像**——固定拍脚本驱动首个多元素单位（FM 排）
      与首个单元素单位（FM 护卫车，同 WHEEL 类）：t1 FormationCmd(WEDGE)（命令
      流）→ t2 issue_group_move([排,护卫], 北 4800cm)（**§2.9 组下令=UI 层聚合
      直调非命令流**——AI 即虚拟玩家/UI 位，勘察「组令画像 issue_group_move 须
      直调」口径；cap=MIN(3,1)=1 → 双方 12cm/拍、逐拍 v 相等）→ t402 排单独
      外部新令（脱离编组：cap=0、35cm/拍与护卫 12cm/拍分离）——FormationCmd/
      issue_group_move/§2.3 增量① 消费者三件整局面载体（TestFormationMarch
      FullGame）。

    空中闭环·块2（2026-10-07）增 keyword 参数（缺省=既有行为逐位不变——同先例）：
    - air=False：**纯航空画像**——固定拍呼叫脚本（AIR_CALL_SCRIPTS，双方
      攻击机/轰炸机+战斗机）+ 实战期节拍令：攻击/轰炸机 PATROL 且带弹 →
      AirStrikeCmd 敌锚点（BOMB 档）；t650 战斗机 AirAltCmd(HIGH)（高度层
      过渡入指纹面）；每 150t 战斗机 AirPatrolCmd 图中心（B-20 CAP——同空域
      自动缠斗 R-20）；全弹尽 PATROL 机 → AirRTBCmd（B-29 手动弃权——IL2M
      扫射弹未耗尽的离场路径）；每 100t 经济轮转（回收冷却到期且点数够 →
      重呼同型——D015 租借闭环）。运载 TestAirFullGame。
    """

    def __init__(self, player_index: int, *, anchors=None,
                 move_mode=MoveMode.NORMAL, artillery=False, send_attack=True,
                 motorized=False, tractor=False, formation=False, air=False):
        self.player_index = player_index
        self.anchors = anchors if anchors is not None else (SOUTH, NORTH)
        self.move_mode = move_mode
        self.artillery = artillery
        self.send_attack = send_attack
        self.motorized = motorized
        self.tractor = tractor
        self.formation = formation
        self.air = air
        self._artillery_issued = set()   # 已发炮击任务令的 unit.id（一次性画像）

    def step(self, w) -> None:
        p = w.players[self.player_index]
        if self.air:                     # 固定拍呼叫（B-18 无 phase 门——部署期即呼）
            for team, t_call, key, payload in AIR_CALL_SCRIPTS:
                if p.team == team and w.tick == t_call:
                    queue_command(w, AirCallCmd(player=p,
                                                template=CARD_OBJECTS[key],
                                                payload=dict(payload)))
        enemy_anchor = self.anchors[0] if p.team == 1 else self.anchors[1]
        if w.phase == PHASE_DEPLOY:
            if w.tick % 50 == 0:
                for slot in p.deck_slots:
                    if slot.copies_left > 0 and p.points >= slot.template.cost:
                        queue_command(w, PurchaseCmd(player=p,
                                                     template=slot.template))
                        break                                   # 每节拍一卡（FIFO 出牌）
        elif w.phase == PHASE_COMBAT:
            if self.air:                     # 纯航空画像（空中闭环·块2）：
                mine = [a for a in w.aircraft if a.team == p.team]
                if w.tick % 50 == 0:
                    for a in mine:           # 带 BOMB 的攻击/轰炸机出击
                        if (a.state is AirState.PATROL
                                and a.ammo_left.get("BOMB", 0) > 0
                                and a.template.role in (AirRole.ATTACK,
                                                        AirRole.BOMBER)):
                            queue_command(w, AirStrikeCmd(
                                aircraft=a, target=enemy_anchor, weapon="BOMB"))
                if w.tick == 650:            # 战斗机爬升（alt_pending 入指纹面）
                    for a in mine:
                        if (a.template.role is AirRole.FIGHTER
                                and a.state is AirState.PATROL):
                            queue_command(w, AirAltCmd(aircraft=a,
                                                       tier=AltTier.HIGH))
                if w.tick % 150 == 0:        # CAP 盘旋（B-20——同空域自动缠斗）
                    for a in mine:
                        if (a.template.role is AirRole.FIGHTER
                                and a.state is AirState.PATROL):
                            queue_command(w, AirPatrolCmd(
                                aircraft=a, center=(100000, 50000), radius=3000))
                if w.tick % 100 == 0:
                    for a in mine:           # 攻击/轰炸机投完弹→手动弃权（B-29——
                        if (a.state is AirState.PATROL  # 纯航空场景无地面目标、
                                and a.template.role in (  # STRAFE 弹无从消耗，
                                    AirRole.ATTACK, AirRole.BOMBER)  # 以 BOMB 耗尽
                                and a.ammo_left.get("BOMB", 0) <= 0):  # 为弃权判据
                            queue_command(w, AirRTBCmd(aircraft=a))
                    for team, _t, key, payload in AIR_CALL_SCRIPTS:
                        if p.team != team or w.tick <= 500:
                            continue         # 经济轮转：冷却到期+不在空+点数够→重呼
                        tpl = CARD_OBJECTS[key]
                        cost = tpl.cost_body + sum(
                            tpl.payload_price.get(k, 0) * v
                            for k, v in payload.items())
                        in_air = any(x.template is tpl for x in w.aircraft
                                     if x.team == p.team)
                        cd = p.air_cooldowns.get(tpl.template_id, 0)
                        if not in_air and w.tick >= cd and p.air_points >= cost:
                            queue_command(w, AirCallCmd(
                                player=p, template=tpl, payload=dict(payload)))
                return
            mine = [u for u in w.units if u.alive and u.team == p.team]
            foes = [u for u in w.units if u.alive and u.team != p.team]
            if self.artillery:                     # 火支画像：只发炮击任务令（一次）
                if w.tick % 100 == 0:
                    for u in mine:
                        if (u.template.category == 3
                                and u.id not in self._artillery_issued):
                            for el in u.elements:
                                queue_command(w, SetModeCmd(
                                    element=el, mode=Mode.INDIRECT))
                            queue_command(w, FireMissionCmd(
                                unit=u, form=FireMissionForm.POINT,
                                point=enemy_anchor, ammo_mult=1,
                                salvo_mode=SalvoMode.FULL, creep_speed=0))
                            self._artillery_issued.add(u.id)
                return
            if self.motorized:                   # 车载机动画像（PB-56 批②）：
                mot = next((u for u in mine       # 首个「班+座」混编单位固定拍脚本
                            if any(e.template.seats > 0 for e in u.elements)
                            and any(e.template.element_type is ElementType.SQUAD
                                    for e in u.elements)), None)
                if mot is not None:
                    squads = [e for e in mot.elements
                              if e.template.element_type is ElementType.SQUAD]
                    if w.tick == 700:            # 车载机动（预挂班随车）
                        queue_command(w, MoveCmd(unit=mot, path=[(104000, 0)]))
                    elif w.tick == 950:          # 下车
                        queue_command(w, DismountCmd(squad_unit=mot))
                    elif w.tick == 951:          # 再上车（200 拍倒计时）
                        queue_command(w, MountCmd(squad_elements=squads,
                                                  carrier_unit=mot))
                return
            if self.tractor:                     # 拖曳展开画像（PB-56 批②）：
                tra = next((u for u in mine       # 首个 TOW 位单位 × 首个含 GUN
                            if u.template.mode_set & (1 << Mode.TOW)), None)  # 单位
                gun_u = next((u for u in mine
                              if any(e.template.element_type is ElementType.GUN
                                     for e in u.elements)), None)
                if tra is not None and gun_u is not None:
                    gun_e = next(e for e in gun_u.elements
                                 if e.template.element_type is ElementType.GUN)
                    if w.tick == 1:              # D065：牵引前先切 TOW
                        queue_command(w, SetModeCmd(element=tra.elements[0],
                                                    mode=Mode.TOW))
                    elif w.tick == 2:
                        queue_command(w, TowCmd(tower_elements=[tra.elements[0]],
                                                towed_element=gun_e))
                    elif w.tick == 3:            # 锁速机动（随动偏移 300）
                        queue_command(w, MoveCmd(
                            unit=tra, path=[(tra.pos[0] + 1200, tra.pos[1])]))
                    elif w.tick == 200:          # 解挂（被拖侧入口）
                        queue_command(w, UntowCmd(element=gun_e))
                    elif w.tick == 201:          # 重展开 300 拍
                        queue_command(w, DeployCmd(unit=gun_u))
                    elif w.tick == 510:          # 收装 300 拍
                        queue_command(w, PackCmd(unit=gun_u))
                return
            if self.formation:                     # 编队行军画像（PB-56 批③）：
                plt = next((u for u in mine        # 首个多元素单位=FM 排
                            if len(u.elements) > 1), None)
                esc = next((u for u in mine        # 首个单元素单位=FM 护卫车
                            if len(u.elements) == 1), None)
                if plt is not None and esc is not None:
                    if w.tick == 1:            # 队形令（命令流——§2.2 独立入口）
                        queue_command(w, FormationCmd(
                            units=[plt], shape=FormationShape.WEDGE))
                    elif w.tick == 2:          # 组下令（§2.9 UI 聚合直调非命令流）：
                        issue_group_move(      # cap=MIN(3,1)=1 → 双方 12cm/拍
                            w, CONFIG, [plt, esc],
                            [(plt.pos[0], plt.pos[1] + 4800)],
                            self.move_mode)
                    elif w.tick == 402:        # 排单独外部新令=脱离编组（400 拍×12
                        queue_command(w, MoveCmd(   # 恰达后一拍；cap=0 → 35cm/拍）
                            unit=plt,
                            path=[(plt.pos[0], plt.pos[1] + 4800)]))
                return
            if w.tick % 100 == 0 and mine and foes:
                queue_command(w, MoveCmd(unit=mine[0], path=[enemy_anchor],
                                         mode=self.move_mode))
                if self.send_attack:
                    queue_command(w, AttackCmd(element=mine[0].elements[0],
                                               target=foes[0].elements[0]))
                for u in mine:
                    if u.template.category == 3:
                        queue_command(w, FireMissionCmd(
                            unit=u, form=FireMissionForm.POINT,
                            point=enemy_anchor, ammo_mult=1,
                            salvo_mode=SalvoMode.FULL, creep_speed=0))
            if w.tick % 500 == 0 and mine:
                queue_command(w, CancelFireMissionCmd(unit=mine[0]))


# ── 场景工厂 ──

def _world_with_deck(seed, decks, objectives):
    w = make_world(seed, phase=PHASE_DEPLOY, size_cm=MAP_SIZE)
    for p, deck in zip(w.players, decks):
        p.deck_slots = [DeckSlot(tpl, n) for tpl, n in deck]
    w.objectives = objectives
    return w


def build_lean_world(seed):
    """整局主场景：队0=3 步兵+1 突击炮，队1=3 步兵+1 坦克（两占点各据一方）。"""
    return _world_with_deck(
        seed,
        [[(RIFLE_TPL, 3), (GUN_TPL, 1)], [(RIFLE_TPL, 3), (TANK_TPL, 1)]],
        [Objective(id=1, pos=SOUTH, radius_cm=25000),
         Objective(id=2, pos=NORTH, radius_cm=25000)])


def build_rich_world(seed):
    """宽面场景：混编卡（开局车载）/渗透/狙击/烟弹/坦克全配置（双跑指纹面最大化）。"""
    deck = [(RIFLE_TPL, 2), (MIXED_TPL, 1), (INFIL_TPL, 1), (TANK_TPL, 1),
            (SNIPER_TPL, 1), (SMOKE_TPL, 1)]
    return _world_with_deck(
        seed, [deck, deck],
        [Objective(id=1, pos=SOUTH, radius_cm=25000),
         Objective(id=2, pos=NORTH, radius_cm=25000)])


def build_grind_world(seed):
    """磨耗场景：低伤高命中步枪 4 张+窄射界坦克——弹药 30 发必耗尽（EMPTY 迁移）。"""
    deck = [(GRIND_TPL, 4), (ARC_TANK_TPL, 1)]
    return _world_with_deck(
        seed, [deck, deck],
        [Objective(id=1, pos=SOUTH, radius_cm=25000),
         Objective(id=2, pos=NORTH, radius_cm=25000)])


def build_suppression_world(seed):
    """士气生命周期场景（2026-10-04 士气整局验收块）：队0=厚血无武器靶（南），
    队1=4 发恒命中压制炮（北）——交战火力自然把守方打过 40/70/100 三档阈值，
    完整走 受压→钉住→溃逃→（弹尽火力停）重整→衰减回落 全周期（拍序可全手推：
    命中恒真零 seed 依赖——PIN_W accuracy_base_bp=10000）。"""
    return _world_with_deck(
        seed,
        [[(BULWARK_TPL, 1)], [(SUPPRESS_TPL, 1)]],
        [Objective(id=1, pos=SOUTH, radius_cm=25000),
         Objective(id=2, pos=NORTH, radius_cm=25000)])


def build_five_objective_world(seed):
    """2026-10-03 拍板场景：战区五占点（南 3 北 2）——占点多数直接定胜负。
    三个南点落在队0 开局部署圈内、两个北点落在队1 圈内（双方步枪锚点 ±15000
    ≤ 25000 半径）。2026-10-04 移动令落地后对位归属可被机动单位改写（见测试
    注释——seed 42 队1 南进扫点 0:5、seed 3 队0 歼灭后保 3:2）。"""
    return _world_with_deck(
        seed,
        [[(RIFLE_TPL, 3), (GUN_TPL, 1)], [(RIFLE_TPL, 3), (TANK_TPL, 1)]],
        [Objective(id=1, pos=(85000, 0), radius_cm=25000),
         Objective(id=2, pos=(100000, 0), radius_cm=25000),
         Objective(id=3, pos=(115000, 0), radius_cm=25000),
         Objective(id=4, pos=(85000, 100000), radius_cm=25000),
         Objective(id=5, pos=(115000, 100000), radius_cm=25000)])


def build_map_world(seed):
    """正式示范地形图整局场景（PB-58 块③，2026-10-06）：lean 卡组（与
    build_lean_world 同构）+ apply_map 挂 data/gen/map_demo_2km.v1.json。
    图幅 200000×100000 与 MAP_SIZE 同幅 → 原位接入零锚点搬移（apply_map 对齐
    terrain/map_extent/map_center 三件；make_world 本体不动、terrain 缺省
    None=既有场景 stub 口径保持）。移动令侧由 HeadlessAI(anchors=MAP_ANCHORS,
    move_mode=MARCH) 承载（见 TestDemoMapFullGame）。"""
    w = _world_with_deck(
        seed,
        [[(RIFLE_TPL, 3), (GUN_TPL, 1)], [(RIFLE_TPL, 3), (TANK_TPL, 1)]],
        [Objective(id=1, pos=SOUTH, radius_cm=25000),
         Objective(id=2, pos=NORTH, radius_cm=25000)])
    apply_map(w, load_demo_map())
    return w


def build_air_world(seed):
    """纯航空整局场景（2026-10-07 空中闭环·块2）：双方无地面单位/无占点——
    经济闭环（呼叫→出击→回收/击落→冷却→重呼）+制空（CAP→自动缠斗）全程；
    D031 结算走第四链（占点 0:0/分值 0:0/血量 0:0 → 队0 胜——纯航空场景约定）。
    AI=HeadlessAI(air=True)（AIR_CALL_SCRIPTS 呼叫+实战期节拍令）。"""
    return _world_with_deck(seed, [[], []], [])


def run_full_game(w, settle_extra=25, max_ticks=30000, ai_factory=HeadlessAI):
    """驱动整局至结算+settle_extra 拍；逐拍收集确定性观测统计（AI=每玩家一个实例）。
    ai_factory（PB-58 块③增参，缺省=HeadlessAI 逐位不变）：地图场景注入
    MARCH/侧翼锚点变体 AI。"""
    ais = [ai_factory(i) for i in range(len(w.players))]
    st = {
        "transitions": [],          # (tick, from, to)
        "first_projectile_tick": None,
        "projectile_total": 0,
        "first_spotted_tick": None,
        "first_death_tick": None,
        "elimination": {},          # team -> tick（全军覆没）
        "max_suppression": 0,
        "max_sniper_tally": 0,
        "smoke_created": 0,
        "smoke_peak": 0,
        "first_empty_tick": None,
        "empty_unit_ids": set(),
        "rotating_ticks": 0,
        "command_residue_ticks": 0,
        "post_deploy_units": None,  # 迁实战拍（部署期结束）时各单位 (id, team, 挂载数)
        # 士气生命周期观测（2026-10-04 士气整局验收块——PB-54 状态机/PB-49 判据缝
        # 在整局 AI 对 AI 火力下的自然行为锚；逐拍比对 prev_morale 捕获迁移拍）
        "first_morale_suppressed_tick": None,   # 首个单位进受压态的拍
        "first_morale_pinned_tick": None,       # 首个单位进钉住态的拍
        "first_morale_routed_tick": None,       # 首个单位进溃逃态的拍
        "morale_rallies": [],                   # [(tick, unit_id)] 重整拍（ROUTED→SUPPRESSED）
        "first_morale_stable_return_tick": None,  # 曾受压+ 的单位回落稳定态的首拍
        # 航空生命周期观测（2026-10-07 空中闭环·块2——逐拍比对 prev_air 快照捕获
        # 事件拍；消失分类：prev RTB=回收、prev DOGFIGHT/hp<=0=击落）
        "air_calls": [],          # [(tick, team, template_id)] 新机入列（INBOUND）
        "air_arrivals": [],       # [(tick, template_id)] INBOUND→PATROL（进场完成）
        "air_recoveries": [],     # [(tick, team, template_id)] RTB 到达回收（退本体价）
        "air_downed": [],         # [(tick, team, template_id)] 击落（冷却×3 不退款）
        "first_air_strike_tick": None,   # 首机转 STRIKE（攻击令受理）
        "first_air_rtb_tick": None,      # 首机转 RTB（自动 GAP3-02 或手动 B-29）
        "first_air_dogfight_tick": None,  # 首机转 DOGFIGHT（R-20 自动缠斗）
        "first_air_projectile_tick": None,  # 首枚空射弹丸（AirShooterView shooter）
        "dogfight_ticks": 0,      # 任一机缠斗在身的拍数
    }
    prev_alive = {0: 0, 1: 0}
    prev_smoke = 0
    prev_morale = {}                            # unit_id -> 上拍末 MoraleState
    seen_suppressed = set()                     # 曾达受压+ 的单位（回落锚资格）
    prev_air = {}                               # aircraft.id -> (state, hp_current, team, template_id)
    while w.phase != PHASE_SETTLE:
        if w.tick > max_ticks:
            raise AssertionError("game did not settle within %d ticks" % max_ticks)
        for ai in ais:
            ai.step(w)
        prev_phase = w.phase
        world_tick(w)
        if w.phase != prev_phase:
            st["transitions"].append((w.tick, prev_phase, w.phase))
        for u in w.units:                       # 士气生命周期逐拍观测（拍末态）
            m = u.morale
            if m is not MoraleState.STABLE:
                seen_suppressed.add(u.id)
            if m is MoraleState.SUPPRESSED \
                    and st["first_morale_suppressed_tick"] is None:
                st["first_morale_suppressed_tick"] = w.tick
            if m is MoraleState.PINNED \
                    and st["first_morale_pinned_tick"] is None:
                st["first_morale_pinned_tick"] = w.tick
            if m is MoraleState.ROUTED \
                    and st["first_morale_routed_tick"] is None:
                st["first_morale_routed_tick"] = w.tick
            if prev_morale.get(u.id) is MoraleState.ROUTED \
                    and m is not MoraleState.ROUTED:
                st["morale_rallies"].append((w.tick, u.id))
            if u.id in seen_suppressed and m is MoraleState.STABLE \
                    and st["first_morale_stable_return_tick"] is None:
                st["first_morale_stable_return_tick"] = w.tick
            prev_morale[u.id] = m
        if w.projectiles and st["first_projectile_tick"] is None:
            st["first_projectile_tick"] = w.tick
        st["projectile_total"] += len(w.projectiles)
        if st["first_spotted_tick"] is None and any(u.spotted_mask
                                                    for u in w.units):
            st["first_spotted_tick"] = w.tick
        for u in w.units:
            for e in u.elements:
                st["max_suppression"] = max(st["max_suppression"],
                                            e.suppression)
                st["rotating_ticks"] += 1 if e.rotating else 0
                for ws in e.weapon_states:
                    if int(ws.state) == 3:                    # WState.EMPTY
                        if st["first_empty_tick"] is None:
                            st["first_empty_tick"] = w.tick
                        st["empty_unit_ids"].add(u.id)
            st["max_sniper_tally"] = max(st["max_sniper_tally"],
                                         u.r02_kill_tally)
        alive = {t: sum(1 for u in w.units if u.alive and u.team == t)
                 for t in (0, 1)}
        for t in (0, 1):
            if prev_alive[t] > 0 and alive[t] < prev_alive[t] \
                    and st["first_death_tick"] is None:
                st["first_death_tick"] = w.tick
            if prev_alive[t] > 0 and alive[t] == 0:
                st["elimination"].setdefault(t, w.tick)
        prev_alive = alive
        # 航空生命周期观测（块2）：新机入列/状态迁移/消失分类
        # 〔块2 评审修复 2026-10-07〕①消失分类补 hp 判据（prev=RTB 且 hp>0 才是
        # 回收——RTB 态被迟到防空弹打到 hp≤0 跨拍清除者实为击落×3 不退款，
        # 纯航空场景不可达、跨域场景可达）；②状态迁移检测改独立 if（同拍
        # INBOUND→PATROL→DOGFIGHT 一拍多迁移不漏记 arrival）
        cur_air = {a.id: (a.state, a.hp_current) for a in w.aircraft}
        for aid, (st_, hp, team, tid) in prev_air.items():
            if aid not in cur_air:                       # 本拍消失
                if st_ is AirState.RTB and hp > 0:
                    st["air_recoveries"].append((w.tick, team, tid))
                else:                                    # 缠斗阵亡即时清/防空击落
                    st["air_downed"].append(            # 跨拍清（hp≤0 残留一拍）
                        (w.tick, team, tid))
        for a in w.aircraft:
            prev = prev_air.get(a.id)
            if prev is None:
                st["air_calls"].append((w.tick, a.team, a.template.template_id))
                continue
            if prev[0] is AirState.INBOUND and a.state is not AirState.INBOUND:
                st["air_arrivals"].append((w.tick, a.template.template_id))
            if prev[0] is not AirState.STRIKE and a.state is AirState.STRIKE:
                if st["first_air_strike_tick"] is None:
                    st["first_air_strike_tick"] = w.tick
            if prev[0] is not AirState.RTB and a.state is AirState.RTB:
                if st["first_air_rtb_tick"] is None:
                    st["first_air_rtb_tick"] = w.tick
            if prev[0] is not AirState.DOGFIGHT and a.state is AirState.DOGFIGHT:
                if st["first_air_dogfight_tick"] is None:
                    st["first_air_dogfight_tick"] = w.tick
            if a.dogfight is not None:
                st["dogfight_ticks"] += 1
        prev_air = {a.id: (a.state, a.hp_current, a.team, a.template.template_id)
                    for a in w.aircraft}
        for p in w.projectiles:
            if (st["first_air_projectile_tick"] is None
                    and p.shooter.__class__.__name__ == "AirShooterView"):
                st["first_air_projectile_tick"] = w.tick
        if len(w.smoke_zones) > prev_smoke:
            st["smoke_created"] += len(w.smoke_zones) - prev_smoke
        prev_smoke = len(w.smoke_zones)
        st["smoke_peak"] = max(st["smoke_peak"], len(w.smoke_zones))
        if w.command_queue:
            st["command_residue_ticks"] += 1
        if w.phase is PHASE_COMBAT and st["post_deploy_units"] is None:
            st["post_deploy_units"] = [
                (u.id, u.team,
                 sum(1 for e in u.elements if e.mounted_in is not None))
                for u in w.units]
    for _ in range(settle_extra):                            # 结算后继续推进（终态）
        for ai in ais:
            ai.step(w)                                       # SETTLE：AI 自然静默
        world_tick(w)
        if w.command_queue:
            st["command_residue_ticks"] += 1
        st["smoke_peak"] = max(st["smoke_peak"], len(w.smoke_zones))
    return st


# ── 全状态指纹（照 test_integration.fingerprint 范式，面扩到八块后的完整容器：
#    fire_mission/弹药受限档/物资槽/挂载/待补给/上车请求/占点/玩家经济/声测痕迹/
#    声测圈/建筑/拖曳对/裁决 + 八通道 PCG32 内部 state）──

def full_fingerprint(w):
    def elem_ref(e):
        return "-" if e is None else "U%dE%d" % (e.unit.id, e.id)

    def tgt_ref(t):
        """W 段 ws.target / P 段 hit_target 的目标引用（2026-10-06 PB-57 塌楼验收块
        修复：Building 目标无 .unit——原 elem_ref 直崩 AttributeError；⑧块成文时
        world.buildings 恒空无 Building 弹丸/瞄准为盲区，本块驻楼-拆楼整链首次
        产生在飞 Building 弹丸而暴露。分支序=航空器→楼→元素，与 E 段 gref 的
        "B%d" 同款编号域）。"""
        if t is None:
            return "-"
        if t.__class__.__name__ == "AircraftInstance":
            return "A%d" % t.id
        if isinstance(t, Building):
            return "B%d" % t.id
        return elem_ref(t)

    parts = ["t%d:p%d:s%d:R%s:r%s" % (
        w.tick, w.phase, w.phase_start_tick, w.result,
        ",".join(str(r.state) for r in w.rng._rngs))]
    for u in w.units:
        fm = u.fire_mission
        fms = "-" if fm is None else "fm%d,%d,%d,%s,%d,%d,%d,%d,%d" % (
            fm.form, fm.shots_left, fm.shots_fired, fm.calib_target,
            fm.calib_progress, fm.started_tick, fm.ammo_mult,
            int(fm.salvo_mode), fm.creep_speed_cm_tick)
        parts.append("U%d,%d,%s,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%s,%d,%d,%d,%d,%d" % (
            u.id, u.team, u.pos, int(u.alive), u.spotted_mask,
            int(u.mark_level), int(u.stance), int(u.deploy_state),
            u.deploy_timer, u.infiltration_timer, u.sprint_until,
            int(u.ambush_active), int(u.ambush_shot_bonus),
            u.r02_kill_tally, len(u.move_path), fms,
            int(u.formation_shape), u.group_speed_cap,
            len(u.command_queue),   # 2026-10-06 PB-56 批③ Formation 族块：
                                     # 队形槽/cap/排队链长入指纹（编队行军/组令
                                     # 任何非确定写在双跑位级比对暴露——扩面仅加严
                                     # 既有双跑锚；插在 morale 段前=U 段尾 morale/
                                     # routed_until 保持，既有段尾自证锚不动）
            int(u.morale), u.routed_until))   # 2026-10-04 士气整局验收块：
                                              # morale 槽+routed_until 入指纹（压制值
                                              # e.suppression 已在 E 段）——状态机任何
                                              # 非确定迁移/计时漂移在双跑位级比对暴露
        for e in u.elements:
            gref = "-" if e.garrison_in is None else "B%d" % e.garrison_in.id
            cargo = "-" if e.cargo_units is None \
                else ",".join("U%d" % s.id for s in e.cargo_units)
            parts.append("E%d,%s,%d,%d,%d,%d,%d,%d,%d,%d,%d,%s,%s,%s,%s,%s" % (
                e.id, e.pos, e.hp_current, e.facing, e.suppression,
                e.reveal_timer, int(e.rotating), int(e.mode), int(e.towed),
                int(e.redeploy_needed), len(e.crit),
                sorted((int(k), int(v)) for k, v in e.crit.items()),
                elem_ref(e.mounted_in), gref, e.supply_weight_g,
                cargo))
            for ws in e.weapon_states:
                parts.append("W%d,%d,%d,%s,%s,%d" % (
                    int(ws.state), ws.timer, ws.ammo_left,
                    ws.restricted_left, tgt_ref(ws.target),
                    int(ws.use_self_defense)))
    for a in w.aircraft:
        # A 段全字段入面（2026-10-07 空中闭环·块2——工作流验收标准"航空字段全入
        # 指纹面"：spotted_mask/facing/flight_plan/patrol_loop/task/ammo/alt_pending/
        # dogfight/engage_air/paratroop_cargo/no_engage_until。前 6 字段序=原 A 段
        # 保持；无航空器场景本段零贡献=既有指纹位级不变，扩面仅加严双跑锚）
        t = a.task
        ts = "-"
        if t is not None:
            ts = "tk%d,%s,%s,%s,%s,%s,%s,%d,%s" % (
                int(t.kind), t.weapon or "-", t.target or "-",
                ("%d" % int(t.phase)) if t.phase is not None else "-",
                t.run_start or "-", t.run_end or "-", t.center or "-",
                t.radius, t.drop or "-")
        ap = "-" if a.alt_pending is None else "%d,%d" % (
            int(a.alt_pending[0]), a.alt_pending[1])
        df = "-" if a.dogfight is None else "op%d,%d,%d" % (
            a.dogfight.opponent.id, a.dogfight.round_timer, a.dogfight.rounds)
        ea = "-" if a.engage_air is None else "%d" % int(a.engage_air)
        pc = "-" if a.paratroop_cargo is None \
            else "T%d" % getattr(a.paratroop_cargo, "template_id", 0)
        parts.append("A%d,%d,%s,%d,%d,%d,%d,%d,%d,%s,%s,%s,%s,%s,%d,%s,%s" % (
            a.id, a.team, a.pos, int(a.alt_tier), a.hp_current, int(a.state),
            a.spotted_mask, a.facing, int(a.patrol_loop), a.flight_plan, ts,
            sorted((k, v) for k, v in a.ammo_left.items()), ap, df,
            a.no_engage_until, ea, pc))
    for p in w.projectiles:
        parts.append("P%s,%s,%d,%d,%d,%d,%d,%d,%s,%s" % (
            p.pos, p.dest, int(p.will_hit), p.speed_cm_tick, p.damage,
            p.blast_cm, p.pen_bonus, int(p.trajectory), tgt_ref(p.hit_target),
            int(p.damage_type)))
    for pl in w.players:
        parts.append("PL%d,%d,%d,%d,%d,%s,%s,%s" % (
            pl.index, pl.team, pl.points, pl.air_points,
            pl.spawn_serial,
            [t.template_id for t in pl.spawn_queue],
            [s.copies_left for s in pl.deck_slots],
            sorted(pl.air_cooldowns.items())))
    for o in w.objectives:
        parts.append("O%d,%s" % (o.id, o.owner))
    parts.append("AR%s" % [u.id for u in w.await_resupply])
    parts.append("MR%s" % [("%s>%s:%d" % (elem_ref(r.squad_element),
                                          elem_ref(r.carrier), r.ticks_left))
                           for r in (w.mount_requests or ())])
    for z in w.smoke_zones:
        parts.append("S%s,%d,%d" % (z.center, z.radius_cm, z.ttl_ticks))
    for s in w.sound_tracks:
        parts.append("ST%d,%d,%s,%d,%d" % (s.listening_team, s.unit.id,
                                           s.pos, s.accum, s.last_fire_tick))
    for c in w.intel_circles:
        parts.append("IC%d,%d,%s,%d" % (c.team, c.source_unit.id, c.center,
                                        c.radius_cm))
    for b in w.buildings:
        parts.append("B%d,%s,%d,%d" % (b.id, b.pos, b.hp, len(b.garrisoned)))
    parts.append("TP%d" % len(w.tow_pairs))
    parts.append("Q%d" % len(w.command_queue))
    return "|".join(parts)


def channels_used(w, initial_states):
    """整局后 PCG32 通道消费面（对照构造时 state）。"""
    names = ["HIT", "SCATTER", "SPOT", "CRIT", "SNIPER", "SONAR",
             "ECONOMY", "AIR"]
    return {n for n, s0, s1 in zip(names, initial_states,
                                   (r.state for r in w.rng._rngs)) if s0 != s1}


def _route_tile_kinds(w, frm, path):
    """示范图航路瓦片类型序列（tests 侧探针，PB-58 块③）：沿 find_path 共线段
    逐 2500cm 步进取样落格（航路=共线段合并输出，段内直线；步长=tile_cm 端点
    含糊一格不影响结构断言的多数派口径）。整型步进（math.isqrt——movement.py
    拖曳随动同款先例，非超越函数）。返回 '#'(路) / 'R'(废墟) / '.'(旷野)。"""
    t = w.terrain.tile_cm
    cur = frm
    kinds = []
    for wp in path:
        dx, dy = wp[0] - cur[0], wp[1] - cur[1]
        n = max(1, math.isqrt(dx * dx + dy * dy) // t)
        for i in range(1, n + 1):
            ix, iy = (cur[0] + dx * i // n) // t, (cur[1] + dy * i // n) // t
            tile = w.terrain.tiles.get((ix, iy))
            kinds.append("#" if (tile is not None and tile.on_road)
                         else ("R" if tile is not None else "."))
        cur = wp
    return kinds


# ── ① 整局 AI-vs-AI：四相位全程 + 胜负 + 无异常 ──

class TestFullGameAIVsAI(unittest.TestCase):
    def test_full_game_all_phases_settlement_and_channel_discipline(self):
        # seed 42 整局（测试通过本身=全程无异常）。相位边界手推（phase_ticks
        # 600/13200）：盲部署恰占 1..600、实战 601..13800、
        # 13801 迁结算；结算为终态（settle_extra 25 拍不再迁出、裁决保持）。
        w = build_lean_world(42)
        rng0 = [r.state for r in w.rng._rngs]
        st = run_full_game(w, settle_extra=25)
        self.assertEqual(st["transitions"],
                         [(601, PHASE_DEPLOY, PHASE_COMBAT),
                          (13801, PHASE_COMBAT, PHASE_SETTLE)])
        self.assertEqual(w.tick, 13801 + 25)
        # 购卡算术（手推）：队0 3×60+150=330 → 1000−330=670；队1 3×60+180=360 → 640；
        # 双方各出 4 张卡（spawn_serial=4）、卡组余量清零、spawn_queue 空
        self.assertEqual([p.points for p in w.players], [670, 640])
        self.assertEqual([p.spawn_serial for p in w.players], [4, 4])
        self.assertEqual([[s.copies_left for s in p.deck_slots]
                          for p in w.players], [[0, 0], [0, 0]])
        self.assertTrue(all(not p.spawn_queue for p in w.players))
        # 全部 spawn 于盲部署期（迁实战拍时每队 4 单位；队0 混编无车载=挂载 0）
        self.assertEqual(st["post_deploy_units"],
                         [(1, 0, 0), (2, 1, 0), (3, 0, 0), (4, 1, 0),
                          (5, 0, 0), (6, 1, 0), (7, 0, 0), (8, 1, 0)])
        # 交战链（手推+seed 定锚）：tick15 首个整秒扫描后互相发现（静态单位
        # keep_range 内不清位）；实战 601 起 begin_aim（aim 5）→ 606 首发弹；
        # 队0 于 1227 拍全军覆没；全场 450 发弹丸、峰值压制 16（2026-10-04 命令层
        # 块 MoveCmd 落地后重锚：队0 首单位北进改变交战距离，弹耗 465→450；
        # 2026-10-06 速度链块重锚：MOB 拆除+HP≤25% 重伤减速+暴击域收窄〔MOB 掷
        # 改 FC/SEN/RLD——受害面从机动转瞄准/装填/光学〕改写消耗节奏，全灭
        # 1227→1098、弹耗 450→397；2026-10-07 D071 全拆重锚：暴击掷骰退役=瞄准/
        # 装填/光学受害面消失，全灭 1098→1227、弹耗 397→450——恰回速度链块前
        # 定值（MOB 拆除/重伤减速速度面仍在效，仅暴击面归零））
        self.assertEqual(st["first_spotted_tick"], 15)
        self.assertEqual(st["first_projectile_tick"], 606)
        self.assertEqual(st["elimination"], {0: 1227})
        self.assertEqual(st["projectile_total"], 450)
        self.assertEqual(st["max_suppression"], 16)
        self.assertEqual(st["max_sniper_tally"], 0)          # 本场景无狙击卡
        # 命令层：本 tick 命令全部落地（AI 节拍令不留残队）；移动令已生效（单位
        # 真实机动）、攻击令已落地但本场景全程被门序 REJECT（2026-10-06 PB-56 批①——
        # 探针复核 12 令武器状态零迁移，锚逐位不变，见模块 docstring 机理注）、炮击任务
        # 令被 mode 门 REJECT——全场无任何单位
        # 建立过任务体
        self.assertEqual(st["command_residue_ticks"], 0)
        self.assertTrue(all(u.fire_mission is None for u in w.units))
        # D031 裁决：队1 步兵南进占双点 0:2 占点多数 → 队1 胜（队0 全灭后南占点
        # 归属改写——2026-10-04 移动令落地后不再"各据一方 1:1 平比分"）
        self.assertEqual(w.phase, PHASE_SETTLE)
        self.assertIsNotNone(w.result)
        self.assertEqual(w.result.winner, 1)
        self.assertEqual(w.result.obj_counts, (0, 2))
        self.assertEqual(w.result.unit_scores, (0, 360))
        self.assertEqual([o.owner for o in w.objectives], [1, 1])
        # 幸存者（seed 42 定锚，点单位叠放出生后）：队1 四单位 id 2/4/6/8，
        # 血量 1/1/1/6（三步枪叠于锚点同被压制打击）、步枪弹药 50−18=32、
        # 坦克 30−12=18——存活且缺口在册（await_resupply）〔2026-10-06 速度链块
        # 重锚：弹耗 18→15/12→10（全灭拍提前 129 拍=受击窗口缩短）；2026-10-07
        # D071 全拆重锚：全灭拍回延 129 拍=受击窗口恢复，弹耗 15→18/10→12——
        # 恰回速度链块前值〕
        alive = [(u.id, u.template.template_id,
                  u.elements[0].hp_current,
                  u.elements[0].weapon_states[0].ammo_left)
                 for u in w.units if u.alive]
        self.assertEqual(alive, [(2, 301, 1, 32), (4, 301, 1, 32),
                                 (6, 301, 1, 32), (8, 303, 6, 18)])
        self.assertEqual([u.id for u in w.await_resupply], [2, 4, 6, 8])
        self.assertEqual(len(w.smoke_zones), 0)              # 本场景无烟弹
        # 通道纪律：直射=HIT+SCATTER；SPOT/SONAR/
        # ECONOMY/AIR/SNIPER 全程零消费（sensing/经济/占点零掷骰、无航空无狙击、
        # 本场景无渗透卡——渗透随机出生才消费 ECONOMY，见富配置场景）
        # 〔D071 全拆 2026-10-07 重锚：原「MECH 命中暴击=CRIT 被消费」随暴击掷骰
        # 退役——CRIT 归零消费（通道号保留=口子③，channels_used 无 CRIT 即自证）〕
        self.assertEqual(channels_used(w, rng0),
                         {"HIT", "SCATTER"})

    def test_settle_phase_runs_silent_after_verdict(self):
        # 结算后再跑 200 拍：相位终态、裁决不被改写、无新弹丸（相位门①拦直射）
        w = build_lean_world(42)
        run_full_game(w, settle_extra=200)
        self.assertEqual((w.phase, w.result.winner), (PHASE_SETTLE, 1))
        self.assertEqual(w.result.unit_scores, (0, 360))
        self.assertEqual(w.projectiles, [])


# ── ② 同 seed 双 world 逐 tick 指纹位级相等（宽面场景）──

class TestDualRunFullGameBitIdentical(unittest.TestCase):
    def test_dual_run_entire_game_tick_by_tick(self):
        # seed 3 两个同构 world 各挂一套 AI 同步推进：盲部署→实战→结算→
        # 结算后 25 拍，逐 tick 全状态指纹位级相等（含八通道 PCG32 内部 state——
        # 任何通道泄漏/迭代序漂移/字典序漂移都会在此暴露）
        w1, w2 = build_rich_world(3), build_rich_world(3)
        ais1 = [HeadlessAI(i) for i in range(len(w1.players))]
        ais2 = [HeadlessAI(i) for i in range(len(w2.players))]
        ticks = 0
        while w1.phase != PHASE_SETTLE:
            for a in ais1:
                a.step(w1)
            for a in ais2:
                a.step(w2)
            world_tick(w1)
            world_tick(w2)
            ticks += 1
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertEqual(ticks, 13801)
        for _ in range(25):                                   # 结算尾段同比对
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        # 末态锚（seed 3 定锚，2026-10-04 命令层块 MoveCmd 落地后重锚；2026-10-06
        # 速度链块再重锚：MOB 拆除/重伤减速/暴击域收窄改写磨耗节奏）：队1 胜
        # （0:2 占点多数——队1 首单位南进占双点）；队0 全灭于 1534 拍（含西边
        # 随机落点的渗透卡），队1 幸存分值 480（180→480：狙击/烟幕/步枪卡存活面
        # 扩大——队1 全员四卡存续）〔2026-10-07 D071 全拆重锚：480→180——恰回
        # 速度链块前值（暴击后效消失改回狙击/烟幕/步枪卡存活面），双跑指纹位级
        # 一致全部维持〕
        self.assertEqual(w1.phase, PHASE_SETTLE)
        self.assertEqual(w1.result.winner, 1)
        self.assertEqual(w1.result.obj_counts, (0, 2))
        self.assertEqual(w1.result.unit_scores, (0, 180))
        self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))


# ── ③ 多 seed/多形态冒烟：无异常 + 结局 + 机制生命周期 ──

class TestFullGameMultiSeedSmoke(unittest.TestCase):
    def test_rich_configs_settle_with_smoke_and_sniper_lifecycle(self):
        # 宽面场景（混编车载/渗透/狙击/烟弹/坦克）：seeds 3/11 全程无异常、
        # 四相位边界、胜负产出；烟区全生命周期（创建→ttl 600 耗尽清空——
        # 实战 13200 拍 >> 600）；狙击 tally 有累积（R-02 击杀记账）
        for seed in (3, 11):
            w = build_rich_world(seed)
            rng0 = [r.state for r in w.rng._rngs]
            st = run_full_game(w, settle_extra=25)
            self.assertEqual(st["transitions"],
                             [(601, PHASE_DEPLOY, PHASE_COMBAT),
                              (13801, PHASE_COMBAT, PHASE_SETTLE)],
                             msg="seed %d" % seed)
            # 四链裁决锚（seed 定锚+三级证据；2026-10-04 命令层块 MoveCmd 落地后
            # 重锚——双方首单位对进改写占点归属；2026-10-06 速度链块再重锚——
            # MOB 拆除/重伤减速/暴击域收窄改写磨耗节奏）：3: 占点 0:2 → 队1 胜
            # （队0 全灭 1534 拍、队1 南进占双点，分值 0:480=全员四卡存续）；
            # 11: 占点 2:0 → 队0 胜（队0 歼灭队1 全员〔1405 拍〕并北进占双点，
            # 分值 450:0）〔2026-10-07 D071 全拆重锚：暴击后效消失改写存活面——
            # 3: 480→180/hp 79→48（恰回速度链块前值）；11: hp 82→71〕
            expected = {3: (1, (0, 2), (0, 180), (0, 48)),
                        11: (0, (2, 0), (450, 0), (71, 0))}[seed]
            self.assertEqual(w.result.winner, expected[0], msg="seed %d" % seed)
            self.assertEqual(w.result.obj_counts, expected[1], msg="seed %d" % seed)
            self.assertEqual(w.result.unit_scores, expected[2], msg="seed %d" % seed)
            self.assertEqual(w.result.hp_totals, expected[3], msg="seed %d" % seed)
            self.assertGreater(st["smoke_created"], 0)
            self.assertEqual(len(w.smoke_zones), 0)          # ttl 600 已耗尽
            self.assertGreater(st["max_sniper_tally"], 0)
            self.assertEqual(st["command_residue_ticks"], 0)
            # 通道纪律：+SNIPER（狙击 R-02 概率掷）+ECONOMY（渗透卡沿边随机出生
            # 2026-10-03 拍板——每张两掷）；SPOT/SONAR/AIR 零消费
            # 〔D071 全拆 2026-10-07 重锚：CRIT 随暴击掷骰退役归零消费〕
            self.assertEqual(channels_used(w, rng0),
                             {"HIT", "SCATTER", "SNIPER", "ECONOMY"})
            # 渗透计时自然耗尽（实战起 600 拍 << 13200）
            self.assertTrue(all(u.infiltration_timer == 0 for u in w.units))
            # 混编卡开局车载形态（迁实战拍快照：MIXED 单位 2 班 1 车 → 恰 1 班挂载）
            mixed = [(uid, team, mounted) for uid, team, mounted
                     in st["post_deploy_units"] if mounted > 0]
            self.assertEqual(len(mixed), 2)                  # 双方各 1 张 MIXED 卡
            self.assertTrue(all(m == 1 for _, _, m in mixed))

    def test_attrition_configs_reach_empty_and_rotation(self):
        # 磨耗场景：弹药 30 发必耗尽（EMPTY 迁移+await_resupply 登记）；窄射界
        # 坦克 R-09 转车体（rotating 置位拍>0，GAP-25 每 tick 复位不滞留——
        # 复位正确性由逐拍观测 rotating 元素在转完后归零保证）
        for seed in (42, 7):
            w = build_grind_world(seed)
            rng0 = [r.state for r in w.rng._rngs]
            st = run_full_game(w, settle_extra=25)
            self.assertEqual(st["transitions"][-1],
                             (13801, PHASE_COMBAT, PHASE_SETTLE))
            self.assertIsNotNone(w.result)
            # 手推：实战 601 起 aim3+reload20≈23 拍/发 ×30 发 ≈ 1290 拍 EMPTY
            # （2026-10-04 命令层块 MoveCmd 落地后重锚——首单位机动微移首发时序：
            # seed 42 定 1291、seed 7 定 1289；2026-10-06 速度链块重锚——暴击域
            # 收窄〔MOB 掷改 FC/SEN/RLD=受害面从机动转瞄准/装填〕+重伤减速改写
            # 磨耗节奏：seed 42 定 1290、seed 7 定 1291；2026-10-07 D071 全拆
            # 重锚——暴击受害面归零：seed 42 定 1290、seed 7 定 1290）
            self.assertEqual(st["first_empty_tick"],
                             {42: 1290, 7: 1290}[seed], msg="seed %d" % seed)
            self.assertGreater(len(st["empty_unit_ids"]), 0)
            self.assertGreater(st["rotating_ticks"], 0)
            self.assertEqual(st["command_residue_ticks"], 0)
            # 磨耗=双方步兵互耗到弹药尽：结局必有裁决（seed 定锚：42→队0 胜
            # 380:0；7→队0 胜 380:0〔2026-10-06 速度链块重锚：原 7→队1 胜 50:380
            # 翻转——MOB 拆除后窄界坦克不再暴击趴窝、重伤减速对称作用于双方，
            # 磨耗竞速重新结算；2026-10-07 D071 全拆重锚：7→队0 胜 380:50——
            # 队1 残存 50 分（暴击后效消失改写磨耗尾段，胜方不变）〕）
            expected = {42: (0, (380, 0)), 7: (0, (380, 50))}[seed]
            self.assertEqual(w.result.winner, expected[0])
            self.assertEqual(w.result.unit_scores, expected[1])
            # 全场直射链只碰 HIT/SCATTER（KE 命中；D071 全拆 2026-10-07 重锚：
            # MECH 暴击掷退役——CRIT 零消费）
            self.assertEqual(channels_used(w, rng0),
                             {"HIT", "SCATTER"})


class TestFiveObjectiveMajorityRule(unittest.TestCase):
    def test_five_objectives_majority_wins_over_score(self):
        # 2026-10-03 拍板：战区五占点、占点多数定胜负且为第一级。2026-10-04 命令层
        # 块 MoveCmd 落地后占点归属不再"部署期圈定后不改写"：seed 42 队0 全灭
        # （1098 拍〔2026-10-06 速度链块重锚：原 1227；2026-10-07 D071 全拆重锚：
        # 回 1227〕）后队1 首单位南进扫占全部五点（0:5 → 队1 胜——分值 0:360
        # 不再进链）；seed 3 队1 全灭（696 拍）后队0 保南三点 3:2 胜（330:0；
        # hp_totals 42——速度链块重锚，原 36〔2026-10-07 D071 全拆重锚：回 36——
        # 恰回速度链块前值〕）。
        for seed, owners, winner, scores, hps in (
                (42, [1, 1, 1, 1, 1], 1, (0, 360), (0, 9)),
                (3, [0, 0, 0, 1, 1], 0, (330, 0), (36, 0))):
            w = build_five_objective_world(seed)
            st = run_full_game(w, settle_extra=25)
            self.assertEqual(st["transitions"],
                             [(601, PHASE_DEPLOY, PHASE_COMBAT),
                              (13801, PHASE_COMBAT, PHASE_SETTLE)],
                             msg="seed %d" % seed)
            self.assertEqual([o.owner for o in w.objectives],
                             owners, msg="seed %d" % seed)
            self.assertEqual(w.result.winner, winner, msg="seed %d" % seed)
            self.assertEqual(w.result.obj_counts,
                             (3, 2) if winner == 0 else (0, 5), msg="seed %d" % seed)
            self.assertEqual(w.result.unit_scores, scores, msg="seed %d" % seed)
            self.assertEqual(w.result.hp_totals, hps, msg="seed %d" % seed)


# ── ⑤ 正式示范地形图整局验收（PB-58 块③，2026-10-06——勘察③接入面：
#    build_map_world 场景工厂挂 apply_map；移动令经 issue_move→_resolve_move_path
#    →真 A*（MARCH 侧翼锚点令斜穿图面，绕障航点+沿路道路地板可观测））──


class TestDemoMapFullGame(unittest.TestCase):
    """示范图（data/gen/map_demo_2km.v1.json，80×40 瓦片）上的整局与机动验收。

    图面结构（data/map_demo_2km.csv 声明→build_map 栅格化）：干道 y≈22 横贯
    x=2..77、x=40 纵路 y=1..21、x=58 纵路 y=22..37、对角支线 (58,22)→(72,10)、
    x=12 纵路 y=22..31；V1 村庄废墟 [34..46]×[15..24]、V2 横带废墟
    [28..49]×[31..36]；4 林区旁挂 forest_tiles（§2.12 不减速）。废墟瓦片
    speed_bp=cfg.ruin_speed_bp=4000（可通行减速占位），本图无 bp==0 瓦片。

    边界语义留痕（登记表 discrepancies 同款）：北部署锚点 NORTH=(100000,100000)
    恰落图界线（tile (40,40)=图外——map_extent 图内域 [0..39]）——立位瓦片缺席=
    类级缺省三谓词、移动起点格豁免（pathfind.py 实现闭合规则）可正常寻出、
    以它为终点的令走直线兜底（§2.14 既定口径）。地图场景 AI 锚点 MAP_ANCHORS
    全图内（勘察③护栏：锚点不落不可通行瓦）。"""

    def test_map_world_anchor_tiles_passable(self):
        # 勘察③护栏锚：南部署锚点/两 AI 敌锚点/占点坐标瓦片均可通行
        # （tile_cost 非 None——本图无 bp==0 瓦片=结构性成立，断言防地图回归）
        w = build_map_world(42)
        layer = w.terrain
        for x_cm, y_cm in ((100000, 0),          # SOUTH 部署锚点 → tile (40,0)
                           (50000, 1250),        # MAP_ANCHORS 南侧翼 → tile (20,0)
                           (150000, 98750)):     # MAP_ANCHORS 北侧翼 → tile (60,39)
            for cls in (MovementClass.FOOT, MovementClass.TRACK):
                self.assertIsNotNone(
                    tile_cost(w, layer, CONFIG, x_cm // 2500, y_cm // 2500,
                              cls, True), (x_cm, y_cm, cls))
        # 北部署锚点=图界线（tile (40,40) 图外不可通行）——既定边界语义（类
        # docstring 留痕），断言钉住该事实：以 NORTH 为目标即走直线兜底
        self.assertIsNone(tile_cost(w, layer, CONFIG, 40, 40,
                                    MovementClass.TRACK, True))
        # 限幅界内（结构论证）：图面瓦片总数 80×40=3200 << cfg.pathfind_max_
        # expansions（500,000）——任何单查询展开数 ≤ 可达瓦片数 < cap ⇒ 保险丝
        # 在本图结构性不可能触发 ⇒ 全部查询为真 A* 输出（无超限兜底混入）
        nx = w.map_extent[0] // layer.tile_cm
        ny = w.map_extent[1] // layer.tile_cm
        self.assertEqual((nx, ny), (80, 40))
        self.assertLessEqual(nx * ny, CONFIG.pathfind_max_expansions)

    def test_map_world_full_game_march_settles(self):
        # seed 42 整局（MARCH+侧翼锚点 AI）：三相位全程无异常、结算产出、双方
        # 移动令真实走 A*。观测锚与 lean 场景对照：交战链同源（同卡组同出生列
        # 对射——first_spotted 15/首发弹 606/压制峰值 16 与 lean seed 42 逐项
        # 相同；队0 全灭 1227/弹丸 450=lean 同值〔2026-10-06 速度链块重锚，原
        # 1227/450；2026-10-07 D071 全拆重锚：1098/397→回 1227/450——机动只改写
        # 占点归属与幸存者位置〕）；
        # 占点因侧翼机动改写为各据一点 1:1 → 分值链 0:360 → 队1 胜。
        w = build_map_world(42)
        rng0 = [r.state for r in w.rng._rngs]
        stats = {"n": 0, "ms": 0.0, "max_ms": 0.0}      # 工具侧计时（bench 同款
        orig_find = w.find_path                        # float 只在 tests 侧）
        def timed(frm, to, cls, pref):
            t0 = time.perf_counter()
            r = orig_find(frm, to, cls, pref)
            ms = (time.perf_counter() - t0) * 1000
            stats["n"] += 1
            stats["ms"] += ms
            stats["max_ms"] = max(stats["max_ms"], ms)
            return r
        w.find_path = timed
        st = run_full_game(
            w, settle_extra=25,
            ai_factory=lambda i: HeadlessAI(i, anchors=MAP_ANCHORS,
                                            move_mode=MoveMode.MARCH))
        self.assertEqual(st["transitions"],
                         [(601, PHASE_DEPLOY, PHASE_COMBAT),
                          (13801, PHASE_COMBAT, PHASE_SETTLE)])
        self.assertEqual(st["first_spotted_tick"], 15)
        self.assertEqual(st["first_projectile_tick"], 606)
        self.assertEqual(st["elimination"], {0: 1227})
        self.assertEqual(st["projectile_total"], 450)
        self.assertEqual(st["max_suppression"], 16)
        self.assertEqual(st["command_residue_ticks"], 0)
        self.assertEqual(w.result.winner, 1)
        self.assertEqual(w.result.obj_counts, (1, 1))
        self.assertEqual(w.result.unit_scores, (0, 360))
        self.assertEqual(w.result.hp_totals, (0, 9))
        self.assertEqual([o.owner for o in w.objectives], [0, 1])
        # 幸存者（seed 42 定锚）：队1 四单位——id2=首单位侧翼横穿**在途**（真实
        # 跨图机动证；2026-10-06 速度链块重锚：原「完成横穿抵达 MAP_ANCHORS[0]
        # =(50000,1250)」——该单位交战受创 HP1/10≤25% 重伤减速 ×5000〔FOOT
        # 20→10cm/拍〕，13801 拍横穿未完成、终位 (51980,2996)=重伤减速整局实证；
        # =§2.3 增量③ 的整局可观测锚〔2026-10-07 D071 全拆重锚：终位 (52377,3346)
        # ——暴击后效消失改受创拍/减速起拍漂移，仍在途同性质；HP1/10 实测保持〕），
        # 其余三单位驻北界未受令
        self.assertEqual([(u.id, u.team, u.pos) for u in w.units if u.alive],
                         [(2, 1, (52377, 3346)), (4, 1, (100000, 100000)),
                          (6, 1, (100000, 100000)), (8, 1, (100000, 100000))])
        self.assertEqual(channels_used(w, rng0), {"HIT", "SCATTER"})
        # 〔D071 全拆 2026-10-07 重锚：原 {"HIT","SCATTER","CRIT"}——CRIT 随暴击
        # 掷骰退役归零消费〕
        # 寻路性能观测（量级注释留档）：12 次查询（受令拍 700..1200×双方——
        # 1227 队0 全灭后 mine/foes 双空、AI 自然停发〔2026-10-06 速度链块重锚：
        # 原 12 次/受令窗 700..1200→8 次/700..1000；2026-10-07 D071 全拆重锚：
        # 全灭拍回延 1227→受令窗回 700..1200、回 12 次〕）、总耗时 ~53ms 量级、
        # 单查询峰值 ~12ms
        # （80×40=3200 瓦片档——远低于 S1 基准档，勘察①「限幅是保险丝
        # 而非现痛」的整局实证）。硬门=结构性论证（上锚 test_map_world_anchor_
        # tiles_passable：3200 瓦片 << cap 500,000 ⇒ 保险丝不可能触发）；耗时
        # 断言取 ~500×/~400× 极松护栏（只拦病理性回归——如 fuse 失效全图扫描
        # 循环；量级观测非 CI 硬门：墙钟在重载机器可抖动——2026-10-06 本机后台
        # 跑批时实测单次 267s/常规 1.8s≈150× 拖慢，全套唯一墙钟依赖断言即此二条）
        self.assertEqual(stats["n"], 12)
        self.assertLess(stats["ms"], 30000.0)
        self.assertLess(stats["max_ms"], 5000.0)

    def test_map_world_first_order_waypoints_ride_road(self):
        # 首受令拍（700 入队→701 落地）move_path 逐点定锚：双方首单位的侧翼
        # 令展开为 10/8 航点 A* 航路（≠直线直填单航点）——队0 单位沿 x=40 纵路
        # 北上接干道东进（沿路），队1 单位西行绕 V2 横带南下（绕障）。航点列表
        # 为图面+cfg 的纯函数（零 seed 依赖），随地图/常数改动须有意重锚。
        w = build_map_world(42)
        ais = [HeadlessAI(i, anchors=MAP_ANCHORS, move_mode=MoveMode.MARCH)
               for i in range(len(w.players))]
        captured = {}
        while w.tick < 701:
            for a in ais:
                a.step(w)
            world_tick(w)
        for u in w.units:
            if u.move_path:
                captured.setdefault(u.id, list(u.move_path))
        self.assertEqual(captured[1], [
            (101250, 48750), (106250, 53750), (111250, 53750), (113750, 56250),
            (133750, 56250), (136250, 58750), (143750, 58750), (146250, 61250),
            (146250, 93750), (150000, 98750)])       # 队0 步兵：纵路→干道→东段
        self.assertEqual(captured[2], [
            (101250, 98750), (96250, 93750), (71250, 93750), (68750, 91250),
            (68750, 61250), (63750, 56250), (63750, 13750), (50000, 1250)])
        # 结构断言（独立于逐点锚）：两航路零废墟格（绕障——V2 横带被绕行）；
        # 队0 航路大半程在路面（prefer_road=MARCH 上路——瓦片代价减半生效）
        kinds0 = _route_tile_kinds(w, (100000, 0), captured[1])
        kinds1 = _route_tile_kinds(w, (100000, 100000), captured[2])
        self.assertNotIn("R", kinds0)
        self.assertNotIn("R", kinds1)
        self.assertGreater(kinds0.count("#"), len(kinds0) // 2)
        self.assertGreaterEqual(kinds1.count("#"), 2)     # 队1 短上一段纵路即西折

    def test_map_world_dual_run_bit_identical(self):
        # 同 seed 双 world 整局逐 tick 指纹位级一致（含结算尾段 25 拍）——指纹面
        # 核对留痕：full_fingerprint 不含 path_cache（§D.6 未列记账槽、键含地形
        # 内容指纹的纯派生 memo）——缓存一致性由尾部有序条目比对单独补面
        # （dict 迭代序=插入序，比对含序=缓存键序/驱逐序亦须一致）。
        w1, w2 = build_map_world(42), build_map_world(42)
        ais1 = [HeadlessAI(i, anchors=MAP_ANCHORS, move_mode=MoveMode.MARCH)
                for i in range(len(w1.players))]
        ais2 = [HeadlessAI(i, anchors=MAP_ANCHORS, move_mode=MoveMode.MARCH)
                for i in range(len(w2.players))]
        while w1.phase != PHASE_SETTLE:
            for a in ais1:
                a.step(w1)
            for a in ais2:
                a.step(w2)
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        for _ in range(25):
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        # 缓存补面：非空（6 键——12 查询 6 重复命中〔2026-10-06 速度链块重锚：
        # 原 7 键/12 查询→4 键/8 查询——受令窗随队0 全灭提前（1098）缩短；
        # 2026-10-07 D071 全拆重锚：全灭拍回延（1227）受令窗回扩——6 键/12 查询〕）
        # 且双跑有序条目位级一致。
        # 键含 terrain_fingerprint，其首分量=id(layer)（层身份——换层天然换键，
        # pathfind.py:176）；同图两次加载=两个层对象、id 必异（内容恒等由
        # test_map_pipeline.test_two_loads_identical_content 锚定）——跨 world
        # 比对剥层身份分量后逐位比较（其余全分量+值+插入序）。
        def _norm_cache(w):
            return [(k[:-1], k[-1][1:], v) for k, v in w.path_cache.items()]
        self.assertEqual(len(w1.path_cache), 6)
        self.assertEqual(_norm_cache(w1), _norm_cache(w2))
        self.assertEqual(w1.result.winner, 1)

    def test_map_march_trajectory_road_floor_and_detour(self):
        # 专用机动场景（零交战/零掷骰）：突击炮（TRACK tier2——越野 45×7000//10000
        # =31 cm/tick；MARCH 路瓦 max(31, cfg.road_bonus_cm_tick=170)=170）两令：
        # ① 纵路纵向行军（速度两档可观测）；② V2 横带东西横穿（航路+实走均绕障）。
        # 速度分段手推：起点 (101250,1250) 落 tile (40,0)=非路瓦（路自 y=2500 起）
        # ——1250cm÷31：t1..40 走 1240 至 y=2490（仍在 (40,0)），t41 再 +31 至
        # 2521 入 tile (40,1)，t42 起 pos 已在路瓦 → 170/tick 直至纵路段末
        # (101250,48750)——纵路段剩余 48750−2521=46229cm：t42..312 共 271 拍×170
        # =46070、余 159cm 由后续拍收（数值以断言锚为准；旧注「+47529」系算术误，
        # 2026-10-06 评审核正）。
        md = load_demo_map()
        w = make_world(42, size_cm=MAP_SIZE)
        apply_map(w, md)
        rng0 = [(r.state, r.inc) for r in w.rng._rngs]
        u1 = add_unit(w, make_unit(w, GUN_TPL, 0, 0, (101250, 1250)))   # 纵路起
        u2 = add_unit(w, make_unit(w, GUN_TPL, 0, 0, (62500, 86250)))   # V2 西侧
        u3 = add_unit(w, make_unit(w, GUN_TPL, 0, 0, (101250, 3750)))   # 对照：NORMAL
        y1 = {0: u1.pos[1]}                             # 逐拍 y 起点=发令前
        y3 = {0: u3.pos[1]}
        queue_command(w, MoveCmd(unit=u1, path=[(150000, 56250)],
                                 mode=MoveMode.MARCH))
        queue_command(w, MoveCmd(unit=u2, path=[(138750, 86250)],
                                 mode=MoveMode.MARCH))
        queue_command(w, MoveCmd(unit=u3, path=[(101250, 48750)],
                                 mode=MoveMode.NORMAL))
        world_tick(w)                                   # t1：令落地=consume+首步
        # 航点逐点定锚（图面纯函数）：u1=纵路北上→干道东进 5 航点；u2=南绕
        # V2 走 y=37 走廊 3 航点；两航路零废墟格、u1 大半程路面
        self.assertEqual(u1.move_path, [
            (101250, 48750), (106250, 53750), (111250, 53750),
            (113750, 56250), (150000, 56250)])
        self.assertEqual(u2.move_path, [
            (71250, 93750), (131250, 93750), (138750, 86250)])
        for frm, path in (((101250, 1250), u1.move_path),
                          ((62500, 86250), u2.move_path)):
            self.assertNotIn("R", _route_tile_kinds(w, frm, path))
        self.assertGreater(
            _route_tile_kinds(w, (101250, 1250), u1.move_path).count("#"), 15)
        # 逐拍位移：纵路段两档（31 → 入路瓦后 170）；u3 对照恒 31（MV-B-17
        # 普通机动在路瓦不吃道路地板——同位同瓦仅模式差）。y_at[t]=t 拍末 y 坐标
        # （y_at[0]=发令前；t1 的 world_tick 即消费令并位移——勘察探针同口径）
        y1[1] = u1.pos[1]
        y3[1] = u3.pos[1]
        u2_at = {}
        arrive1 = arrive2 = None
        for t in range(2, 2700):
            world_tick(w)
            y1[t] = u1.pos[1]
            y3[t] = u3.pos[1]
            if t in (500, 1000):
                u2_at[t] = u2.pos
            if arrive1 is None and not u1.move_path:
                arrive1 = t
            if arrive2 is None and not u2.move_path:
                arrive2 = t
            if arrive1 and arrive2:
                break
        self.assertEqual([y1[t] - y1[t - 1] for t in range(1, 42)],
                         [31] * 41)                     # t1..41 非路瓦（tile (40,0)）
        self.assertEqual([y1[t] - y1[t - 1] for t in range(42, 313)],
                         [170] * 271)                   # t42..312 路瓦 MARCH 地板
        self.assertEqual(y1[41], 2521)                  # 入 tile (40,1) 换挡位
        self.assertEqual(arrive1, 619)                  # 抵 (150000,56250)
        self.assertEqual(u1.pos, (150000, 56250))
        # NORMAL 对照（MV-B-17）：同窗 t42..312 u3 恒 31——u3 起于路瓦 (40,1)
        # 一路在路面列行进，无地板（末拍 363 以余量 28 收尾抵 (101250,48750)）
        self.assertEqual([y3[t] - y3[t - 1] for t in range(42, 313)],
                         [31] * 271)
        self.assertEqual(u3.pos, (101250, 48750))
        # u2 实走绕障：中程贴 y=93750 走廊东进（直线穿带将恒 y=86250 过废墟）
        self.assertEqual(u2_at[500], (75130, 93750))
        self.assertEqual(u2_at[1000][1], 93750)
        self.assertGreater(u2_at[1000][0], 90000)       # 走廊上东进中
        self.assertEqual(arrive2, 2652)
        self.assertEqual(u2.pos, (138750, 86250))
        # 零掷骰：纯机动链（issue_move/A*/system_move）不触任何 PCG32 通道
        self.assertEqual([(r.state, r.inc) for r in w.rng._rngs], rng0)


# ── ⑤ 驻楼-塌楼整链验收（PB-57 塌楼验收块，2026-10-06：真实建筑锚[示范图 5 锚]
#    × 驻楼命令 × 直射拆楼 × 塌楼驻军处置 × 双跑指纹）──


# 恒命中拆楼炮（PIN_W 先例：accuracy_base_bp=10000 → chance_bp(10000) 恒真——
# will_hit 恒真、命中拍序列零 seed 依赖可全手推）；damage=20 → 示范楼 hp100×5 发；
# vs_fort_mult_permille 缺省 1000（×1——resolve_hit 建筑支直扣）
DEMOLITION_W = WeaponTemplate(
    name="demo gun", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    damage=20, salvo=1, aim_time_ticks=5, reload_time_ticks=10, ammo_base=10,
    max_range_cm=50000, dispersion_cm=100, accuracy_base_bp=10000,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    suppression_power=0, reveal_time_ticks=5)
# 队1 拆楼炮车：optics 500cm——对 stealth 5 驻军 detection=400~500 << 25000 恒不
# 发现 → select_target 恒无候选（ground_direct 不开自动 AIMING，直挂链不被搅浑）
DEMOLITION_TPL = UnitTemplate(
    template_id=312, name="demolition gun", category=2, cost=120,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=20,
        weapons=(DEMOLITION_W,)),),
    optics_ground_cm=500, stealth_base=3, speed_tier=2,
    movement_class=MovementClass.TRACK)
# 队0 混编双班可驻楼排（塌楼混合处置整链载体）：班0 hp10 恰死 / 班1 hp16 带伤；
# 无武器（零反击不搅浑拍序）、optics 0（不发现射手——互相隐身静场）
GAR_SQUAD_HP10 = ElementTemplate(element_type=ElementType.SQUAD,
                                  unit_type=UnitType.INFANTRY, hp_max=10)
GAR_SQUAD_HP16 = ElementTemplate(element_type=ElementType.SQUAD,
                                  unit_type=UnitType.INFANTRY, hp_max=16)
GARRISON_PLT_TPL = UnitTemplate(
    template_id=313, name="garrison plt", category=0, cost=30,
    element_templates=(GAR_SQUAD_HP10, GAR_SQUAD_HP16),
    optics_ground_cm=0, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT, flags=UnitFlag.CAN_GARRISON)


def build_garrison_collapse_world(seed, cfg):
    """驻楼-塌楼整链场景（PB-57 塌楼验收块）：示范图真实锚（apply_map 5 楼——
    B1=V1_HOUSE_A (93750,43750) 文件序首锚）+ 队0 双班可驻楼排驻 B1 + 队1 恒命中
    拆楼炮正南 25000cm。cfg 出表消费：building_collapse_dmg（塌楼驻军伤害档）/
    building_garrison_slots（装配槽=缺省 1——双班单位整体判一次驻入=伪代码 :1249
    字面超容行为随整链复锚）。phase=COMBAT 直进（fire_permitted ① 门）。"""
    w = make_world(seed, size_cm=MAP_SIZE)
    apply_map(w, load_demo_map(cfg), cfg)
    add_unit(w, make_unit(w, DEMOLITION_TPL, 1, 1, (93750, 18750)))   # 正南 25000
    add_unit(w, make_unit(w, GARRISON_PLT_TPL, 0, 0, (93750, 43750)))  # B1 楼锚
    return w


def garrison_first_building(w, cfg):
    """驻楼步（命令链整链）：GarrisonCmd 入队 → world_tick 落地（consume_commands
    分派支→cmd_garrison）。t1 拍驻楼——效果断言由调用方在拆楼前就地校验。"""
    b = w.buildings[0]                                   # B1（id=1 文件序首锚）
    queue_command(w, GarrisonCmd(unit=w.units[1], building=b))
    world_tick(w, cfg)                                   # t1：consume_commands 驻楼
    return b


def drive_demolition(w, cfg):
    """拆楼驱动：循环「READY 即 begin_aim 直挂楼 → world_tick」至楼塌（AttackCmd
    分派支待 PB-56 批①——begin_aim 直挂 ws.target 验证链体，TestFinishAimBuildingGuard
    同款留痕口径）。返回 (hp 变化拍表 [(tick, hp)], 塌楼拍)。发射节拍手推：
    aim5+reload10=15 拍周期、弹丸 speed 20000 距 25000 → 发射拍+1 命中。"""
    b = w.buildings[0]
    shooter = w.units[0]
    ws = shooter.elements[0].weapon_states[0]
    hp_events, prev_hp = [], b.hp
    while b in w.buildings:
        if ws.state is WState.READY:
            begin_aim(shooter.elements[0], ws, b, cfg)
        world_tick(w, cfg)
        if b in w.buildings and b.hp != prev_hp:
            hp_events.append((w.tick, b.hp))             # (命中拍, 命中后 hp)
            prev_hp = b.hp
    return hp_events, w.tick


class TestGarrisonCollapseFullGame(unittest.TestCase):
    """PB-57 塌楼验收（带建筑集成验收·真实锚）：驻楼（GarrisonCmd 命令链）→
    隐蔽+3 → 直射拆楼（finish_aim→fire_direct 建筑支 HE 档→system_projectiles→
    resolve_hit ×vs_fort→hit_building 扣血）→ 楼塌（collapse_building：清引用×
    cfg.building_collapse_dmg 伤害→驻军死亡/带伤分级处置→garrisoned 清→world.
    buildings 除名）。全链手推定锚零 seed 依赖（恒命中炮）；驻军处置按伪代码口径
    （§F5 :537-541 无「弹出落位」写点——驻楼/塌楼均不写 e.pos，元素保持原位；
    无额外「受罚」常数——伤害外无士气/压制惩罚写点，如实留痕）。"""

    def test_garrison_demolition_collapse_full_chain(self):
        # 手推拍序（aim5+reload10 周期；弹丸 20000cm/tick、距 25000=2 拍到达）：
        # t1 驻楼；发射拍 6/21/36/51/66；命中拍 7/22/37/52/67（发射拍+⑤推进 20000、
        # 次拍到达结算）——hp 100→80→60→40→20→0 塌
        cfg = BalanceConfig(building_collapse_dmg=10)
        w = build_garrison_collapse_world(42, cfg)
        rng0 = [r.state for r in w.rng._rngs]
        self.assertEqual(len(w.buildings), 5)             # apply_map 真实 5 锚
        b1 = w.buildings[0]
        self.assertEqual((b1.id, b1.pos, b1.hp, b1.garrison_slots),
                         (1, (93750, 43750), 100, 1))     # B1=V1_HOUSE_A 文件序首锚
        garrison_unit = w.units[1]
        self.assertEqual(effective_stealth_x10(cfg, garrison_unit), 50)  # 驻楼前
        # t1 驻楼（命令链整链：GarrisonCmd→consume_commands→cmd_garrison）
        b = garrison_first_building(w, cfg)
        self.assertIs(b, b1)
        self.assertEqual(effective_stealth_x10(cfg, garrison_unit), 80)  # +3.0 级
        self.assertTrue(all(e.garrison_in is b1 for e in garrison_unit.elements))
        self.assertEqual(len(b1.garrisoned), 2)           # 双班整体驻入 slots=1（超容字面）
        e0, e1 = garrison_unit.elements                   # 塌楼前双班引用（分级断言用）
        # 拆楼手推锚：命中拍×4 半血序 + 塌楼拍（第 5 发）
        hp_events, collapse_tick = drive_demolition(w, cfg)
        self.assertEqual(hp_events, [(7, 80), (22, 60), (37, 40), (52, 20)])
        self.assertEqual(collapse_tick, 67)
        # 楼塌收口：B1 出 world.buildings（4 锚存续=纯 terrain 用户无行为差）
        self.assertNotIn(b1, w.buildings)
        self.assertEqual([nb.id for nb in w.buildings], [2, 3, 4, 5])
        self.assertEqual(b1.garrisoned, [])
        # 驻军分级处置（伪代码 §F5 :537-541 清引用→apply_damage 唯一入口）：
        # 班0 hp10−10=0 恰死（destroy_element）；班1 hp16−10=6 带伤存活进医疗链
        # （e0/e1 驻楼期已捕获——塌楼后班0 除编不可再从 elements 解包）
        self.assertEqual(garrison_unit.elements, [e1])    # 班0 死亡除编
        self.assertIsNone(e1.garrison_in)                 # 幸存班清引用（无弹出落位）
        self.assertEqual(e1.hp_current, 6)
        self.assertEqual(e1.pos, (93750, 43750))          # 塌楼不写 pos（无规定留痕）
        self.assertTrue(garrison_unit.alive)              # 非全灭
        self.assertIn(garrison_unit, w.await_resupply)    # 带伤步兵登记（医疗承接）
        self.assertIn(garrison_unit, w.units)             # 非全灭不过尸体清扫
        # 塌楼后隐蔽加成终止（驻楼引用已清——50 回落）
        self.assertEqual(effective_stealth_x10(cfg, garrison_unit), 50)
        # 射手侧：5 发耗弹（10→5）、RELOADING 常态；塌楼后 select_target 恒无候选
        ws = w.units[0].elements[0].weapon_states[0]
        self.assertEqual(ws.ammo_left, 5)
        self.assertEqual(w.tick, 67)
        # 通道纪律：仅 HIT（命中掷）/SCATTER（命中点 jitter——零幅实现字面消费）
        # 各 5 次；CRIT 零消费〔D071 全拆 2026-10-07 勘正：暴击掷骰整体退役——
        # 全场景 CRIT 恒零消费（原注「建筑支无暴击、驻军 INFANTRY 无暴击」系拆前
        # 机理）〕；塌楼链零掷骰
        self.assertEqual(channels_used(w, rng0), {"HIT", "SCATTER"})

    def test_collapse_wipes_unit_full_sweep(self):
        # 全灭尸体清扫整链：hp10 单班单位（恰死档 collapse_dmg=10）楼塌全灭 →
        # destroy_element→unregister_unit_refs+alive=False → 同拍 world_tick 尾部
        # 尸体清扫出 world.units（:1439——引用三向清理之尸体清扫侧整局活证）。
        # 单班载体=GARRISON_PLT_TPL 弃班1 后的编成（make_unit 后移除——元素 id 保留
        # 班0 的 1，非全灭分支不可达=干净观察尸体清扫）
        cfg = BalanceConfig(building_collapse_dmg=10)
        w = make_world(42, size_cm=MAP_SIZE)
        apply_map(w, load_demo_map(cfg), cfg)
        shooter = add_unit(w, make_unit(w, DEMOLITION_TPL, 1, 1, (93750, 18750)))
        single = make_unit(w, GARRISON_PLT_TPL, 0, 0, (93750, 43750))
        single.elements.remove(single.elements[1])        # 弃班1 → hp10 单班恰死载体
        add_unit(w, single)
        garrison_first_building(w, cfg)                   # t1 驻楼
        hp_events, collapse_tick = drive_demolition(w, cfg)
        self.assertEqual(hp_events, [(7, 80), (22, 60), (37, 40), (52, 20)])
        self.assertEqual(collapse_tick, 67)
        self.assertEqual(single.elements, [])             # 恰死全灭
        self.assertFalse(single.alive)
        self.assertNotIn(single, w.units)                 # 同拍尾部尸体清扫出表
        self.assertEqual([u.template.template_id for u in w.units], [312])
        self.assertIs(w.units[0], shooter)

    def test_garrison_collapse_dual_run_bit_identical(self):
        # 同 seed 双 world 逐 tick 指纹位级一致（驻楼/塌楼动态场景）：指纹面=
        # E 段 gref（B1 驻楼引用）+ B 段（b.id/b.pos/b.hp/len(garrisoned)——塌楼
        # 逐发掉血与出表均在面内）+ R 段八通道 state（HIT/SCATTER 同步推进）。
        # 跑过塌楼拍再 5 拍（含 await_resupply/尸体清扫后稳态）。
        cfg1 = BalanceConfig(building_collapse_dmg=10)
        cfg2 = BalanceConfig(building_collapse_dmg=10)
        w1, w2 = (build_garrison_collapse_world(42, c) for c in (cfg1, cfg2))

        def step(w, cfg, b, ws):
            """单拍推进（与 drive_demolition 同节拍）：READY 即重挂直射。"""
            shooter_e = w.units[0].elements[0]
            if ws.state is WState.READY:
                begin_aim(shooter_e, ws, b, cfg)
            world_tick(w, cfg)

        b1 = garrison_first_building(w1, cfg1)             # t1 驻楼（两跑同拍）
        b2 = garrison_first_building(w2, cfg2)
        self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        ws1 = w1.units[0].elements[0].weapon_states[0]
        ws2 = w2.units[0].elements[0].weapon_states[0]
        while b1 in w1.buildings:                          # 至塌楼拍（含塌楼当拍）
            step(w1, cfg1, b1, ws1)
            step(w2, cfg2, b2, ws2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertEqual(w1.tick, 67)                      # 塌楼拍手推锚
        for _ in range(5):                                 # 塌楼后稳态 5 拍
            world_tick(w1, cfg1); world_tick(w2, cfg2)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertEqual(len(w1.buildings), 4)             # 两跑同塌（指纹非平凡）
        self.assertEqual(w1.tick, 72)


# ── ④ 士气生命周期整局验收（2026-10-04 士气整局验收块——PB-54 状态机/PB-49 判据缝
#    在整局 AI 对 AI 交战火力下的自然行为锚；D014 四态/D025 阈值制/GDD-05 B2 步序）──

class TestMoraleLifecycleFullGame(unittest.TestCase):
    """交战火力自然把单位打过三档阈值（压制场景：恒命中炮 4 发×55 压制 vs 衰减
    1/tick——净累积 55→75→95→100 封顶），完整走 受压→钉住→溃逃→重整→回落 周期。

    手推链（零 seed 依赖——PIN_W accuracy_base_bp=10000 → chance_bp(10000) 恒真；
    攻方压制恒 0 → aim/reload 因子恒等 → 发射节拍=601+aim5=606 起、周期 35 拍；
    弹丸发射拍即首次推进 → 命中拍=发射+4【606→610，5 步×20000cm/tick】）：
    - 610 命中#1：sup 55 → 受压拍（≥40）；
    - 626：空窗衰减跌破 40（55−16 拍）→ 衰减回落拍（STABLE）；
    - 645 命中#2：残 20+55=75 → 进钉住（≥70）；
    - 651：空窗衰减跌破 70（75−6 拍→69）→ 钉住→受压降档（衰减回落，非持续钉住）；
    - 680 命中#3：残 40+55=95 → 由受压再进钉住（再进入——非「仍钉住」；评审实跑
      探针修正：645 PINNED → 651 SUPPRESSED(69) → 680 PINNED(95)）；
    - 706：衰减跌破 70（95−26 拍→69）→ 再钉住→受压降档。判态在 ⑤.5、速度消费在
      次拍 ②：706 拍位移仍为钉住速 +10（y 50→60），+20/tick 自 707 起——AI 北上令
      701 起两锚整局连续活证：PB-49 钉住减速 + PB-55 受压不减速；
    - 715 命中#4：残 60+55=115→封顶 100 → 溃逃拍（ROUTED；routed_until=1015；
      进入拍清玩家令+装南逃航点）；
    - 716..727：全速南逃 20/tick×12 拍（240→0 抵己方底边锚点）；
    - 741：弹尽（#4 发射 711+reload30）→ EMPTY+await_resupply；
    - 1015：routed_until 到拍，sup 已衰减尽 → 重整拍（回 SUPPRESSED=B4:182 默认）；
    - 1016：回落拍（STABLE）。"""

    def test_suppression_lifecycle_ticks_and_settlement(self):
        w = build_suppression_world(42)
        rng0 = [r.state for r in w.rng._rngs]
        st = run_full_game(w, settle_extra=25)
        self.assertEqual(st["transitions"],
                         [(601, PHASE_DEPLOY, PHASE_COMBAT),
                          (13801, PHASE_COMBAT, PHASE_SETTLE)])
        self.assertEqual(st["first_projectile_tick"], 606)
        # 士气生命周期四类锚拍（手推——见类 docstring 算术链）
        self.assertEqual(st["first_morale_suppressed_tick"], 610)   # 受压出现拍
        self.assertEqual(st["first_morale_stable_return_tick"], 626)  # 衰减回落拍
        self.assertEqual(st["first_morale_pinned_tick"], 645)       # 钉住出现拍
        self.assertEqual(st["first_morale_routed_tick"], 715)       # 溃逃拍
        self.assertEqual(st["morale_rallies"], [(1015, 1)])         # 重整拍（守方 id1）
        self.assertEqual(st["max_suppression"], 100)                # 封顶值可达
        # 弹尽：4 发耗尽后 EMPTY（711+reload30=741）——火力自然停=重整前提
        self.assertEqual(st["first_empty_tick"], 741)
        self.assertEqual(st["empty_unit_ids"], {2})
        # 结算（双方 AI 互换占点各 1:1 → 分值 60:60 平 → 血量链 196:150 → 队0 胜；
        # 守方 4×damage1 存活=196、攻方无伤=150——D031 四链第三级定胜负）
        self.assertEqual(w.result.winner, 0)
        self.assertEqual(w.result.obj_counts, (1, 1))
        self.assertEqual(w.result.unit_scores, (60, 60))
        self.assertEqual(w.result.hp_totals, (196, 150))
        self.assertEqual([o.owner for o in w.objectives], [1, 0])
        self.assertEqual(st["command_residue_ticks"], 0)
        # 通道纪律：直射 HIT+SCATTER 消费（SQUAD 无 MECH 暴击）；其余六通道零消费
        # （sensing/经济/占点零掷骰、无航空无狙击无渗透——士气链本身零掷骰）
        self.assertEqual(channels_used(w, rng0), {"HIT", "SCATTER"})

    def test_suppression_lifecycle_movement_trajectory(self):
        # 逐拍位移轨迹锚（专用驱动循环）：钉住减速 10→受压提速 20→溃逃全速南逃
        # 20→抵锚停驻→失控期拒 AI 令→重整后恢复受令北上。y 坐标全程手推（见类
        # docstring；x 恒 100000 南北走廊）
        w = build_suppression_world(42)
        ais = [HeadlessAI(i) for i in range(len(w.players))]
        y_at, path_at = {}, {}
        while w.tick < 1105:
            for a in ais:
                a.step(w)
            world_tick(w)
            u0 = w.units[0] if w.units else None      # t<10 双方未 spawn
            if u0 is not None:
                y_at[w.tick] = u0.pos[1]
                path_at[w.tick] = list(u0.move_path)
        u0 = w.units[0]
        # 北上段（AI 令 700 入队→701 消费首步）：701..705 钉住 10/tick（PB-49 减速缝）
        self.assertEqual([y_at[t] for t in range(701, 706)], [10, 20, 30, 40, 50])
        # 判态在 ⑤.5、速度消费在次拍 ②：706 拍位移仍为钉住速 +10（y 50→60），
        # +20/tick 自 707 起（PB-55 留待项⑩「受压不减速」整局锚——707..715 九拍
        # 20/tick：60+9×20=240）
        self.assertEqual(y_at[706], 60)
        self.assertEqual(y_at[715], 240)     # 715 ② 时仍受压（判态在 ⑤.5）
        # 溃逃段：716 起全速南逃（不走钉住缝）→ 727 抵己方底边锚点停驻
        self.assertEqual(y_at[716], 220)
        self.assertEqual(y_at[727], 0)
        self.assertEqual(path_at[727], [])   # 航点耗尽=溃逃已抵锚（非拒令清空）
        # 失控期（716..1015）AI 三次移动令全被门0 拒（800/900/1000）：move_path
        # 恒空、无新航点（若受令则=[NORTH 链]）——整局失控门锚
        for t in (800, 900, 1000):
            self.assertEqual(y_at[t], 0, t)
            self.assertEqual(path_at[t], [], t)
        # 重整（1015）→ 回落（1016）→ 1101 起恢复受令北上（AI 令 1100 入队）
        self.assertEqual(y_at[1015], 0)
        self.assertEqual(y_at[1100], 0)
        self.assertEqual(y_at[1101], 20)
        self.assertEqual(y_at[1104], 80)

    def test_dual_run_morale_fingerprint_bit_identical(self):
        # 同 seed 双 world 逐 tick 指纹位级一致（指纹面含 morale 槽+routed_until+
        # 元素压制值——本场景四态全迁移过=非平凡覆盖；任何状态机迭代序/计时漂移
        # 都会在位级比对暴露）
        w1, w2 = build_suppression_world(7), build_suppression_world(7)
        ais1 = [HeadlessAI(i) for i in range(len(w1.players))]
        ais2 = [HeadlessAI(i) for i in range(len(w2.players))]
        while w1.phase != PHASE_SETTLE:
            for a in ais1:
                a.step(w1)
            for a in ais2:
                a.step(w2)
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        for _ in range(25):
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        # 指纹面自证：末态指纹含士气字段（守方重整后 STABLE/-1、攻方恒 STABLE）
        fp = full_fingerprint(w1)
        self.assertIn(",0,-1|" , fp)         # U 段尾 morale=0/routed_until=-1
        self.assertEqual(w1.result.winner, 0)


# ── ⑤ PB-56 批① 余三命令整局验收（2026-10-06——SetMode/ToggleAmbush/SetStance
#    落地后的转活链验收：既有场景锚逐位不动〔artillery/send_attack 缺省=既有
#    行为、GUN_TPL 扩位被双门第二门兜住〕，新画像/新场景承载炮击任务链转活与
#    攻击令主动交战对照；同 seed 双 world 逐 tick 指纹位级一致维持）──

class TestArtilleryMissionFullGame(unittest.TestCase):
    """炮击任务链整局转活：HeadlessAI(artillery=True) 火支画像发
    SetModeCmd(INDIRECT)+FireMissionCmd → cmd_fire_mission 双门解锁（⑧块
    「任务令恒 REJECT」留痕就此闭环）→ process_fire_mission 逐拍推进 →
    R-16 校射按批累积（POINT+友军视野内：116619cm ≤ 光学 120000）→ 弹药/任务
    计数按 salvo → 耗尽任务体销毁（方案10——校射随之失效）→ EMPTY+await_
    resupply。节拍全手推（GUN_W：salvo 2/ammo_base 40/reload 60、速 5000、
    距 116619：发射拍 1+60k〔k=0..19〕、到着拍=发射+23、校射 20(k+1) 封顶
    100、每到着 −8 血〔HE 5×2 发×AMB-01 衰减〕）；通道纪律=曲射 SCATTER only。"""

    def _world(self, seed=42):
        w = make_world(seed, size_cm=MAP_SIZE)
        gun = add_unit(w, make_unit(w, GUN_TPL, 1, 1, (40000, 100000)))
        bulwark = add_unit(w, make_unit(w, BULWARK_TPL, 0, 0, SOUTH))
        return w, gun, bulwark

    def test_artillery_mission_full_chain(self):
        w, gun, bulwark = self._world()
        rng0 = [r.state for r in w.rng._rngs]
        ai = HeadlessAI(1, artillery=True)
        e, ws = gun.elements[0], gun.elements[0].weapon_states[0]
        snap = {}
        first_volley = None
        while w.tick < 1260:
            ai.step(w)
            world_tick(w)
            t = w.tick
            if t == 1:                                    # 首拍弹形锚（在飞时捕获）
                first_volley = w.projectiles
            if t in (1, 24, 61, 241, 1141, 1142, 1201, 1259):
                fm = gun.fire_mission
                snap[t] = (int(ws.state), ws.timer, ws.ammo_left,
                           None if fm is None else
                           (fm.shots_left, fm.shots_fired, fm.calib_progress),
                           bulwark.elements[0].hp_current, len(w.projectiles))
        # t1：SetModeCmd+FireMissionCmd 同拍 FIFO 落地——双门解锁、fire_at 即拍
        # 发射（salvo 2 BALLISTIC 无目标盲射 R-03）、首批校射 +20（视野内：
        # 116619 ≤ 光学 120000）
        self.assertIs(e.mode, Mode.INDIRECT)
        self.assertEqual(snap[1], (int(WState.RELOADING), 60, 38,
                                   (38, 2, 20), 200, 2))
        self.assertEqual(len(first_volley), 2)
        self.assertTrue(all(p.trajectory is Trajectory.BALLISTIC
                            and p.hit_target is None and not p.will_hit
                            for p in first_volley))
        # t24：首批到着（1+23）→ −8；t61 第二批发射、校射 40；t241 第五批后
        # 校射封顶 100（calib_per_shot 20×5）
        self.assertEqual(snap[24][4], 192)
        self.assertEqual(snap[61], (int(WState.RELOADING), 60, 36,
                                    (36, 4, 40), 192, 2))
        self.assertEqual(snap[241][3], (30, 10, 100))
        # t1141：第 20 批发射即耗尽（40 发）→ 任务体销毁（方案10）；弹尽
        # RELOADING 到期转 EMPTY（t1201）+ 待补给登记
        self.assertEqual(snap[1141], (int(WState.RELOADING), 60, 0,
                                      None, 48, 2))
        self.assertEqual(snap[1142][0], int(WState.RELOADING))
        self.assertEqual(snap[1201], (int(WState.EMPTY), 0, 0, None, 40, 0))
        self.assertEqual(snap[1259], snap[1201])          # 终态稳定
        self.assertIsNone(gun.fire_mission)
        self.assertIn(gun, w.await_resupply)
        # 声测痕迹（㉗A）：一条、听方=敌队 0（声测圈服务对手定位）、last_fire_tick
        # =末批发射拍
        self.assertEqual([(s.listening_team, s.last_fire_tick)
                          for s in w.sound_tracks], [(0, 1141)])
        self.assertEqual(len(w.command_queue), 0)         # 一次性画像无残队
        # 通道纪律：曲射=SCATTER only（HIT/CRIT/SNIPER/SPOT/SONAR/ECONOMY/AIR 零消费
        # ——D071 全拆 2026-10-07 后 CRIT 为全场景恒零消费通道）
        self.assertEqual(channels_used(w, rng0), {"SCATTER"})

    def test_artillery_dual_run_bit_identical(self):
        # 同 seed 双 world 逐 tick 指纹位级一致：E 段 mode、U 段 fire_mission
        #（shots/calib 逐批推进）、P 段 BALLISTIC 弹丸、R 段 SCATTER 通道同步
        # 均在指纹面——任务建立/校射/耗尽/EMPTY 全程非平凡覆盖
        w1, g1, b1 = self._world()
        w2, g2, b2 = self._world()
        a1, a2 = HeadlessAI(1, artillery=True), HeadlessAI(1, artillery=True)
        while w1.tick < 1260:
            a1.step(w1)
            a2.step(w2)
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertIsNone(g1.fire_mission)
        self.assertIsNone(g2.fire_mission)
        self.assertEqual(b1.elements[0].hp_current, b2.elements[0].hp_current)
        self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))


class TestManualEngageFullGame(unittest.TestCase):
    """攻击令主动交战×自动链对照：min_range 60000 武器使自动交战链结构性
    不接战（select_target 候选门 min≤d≤max——§F4 :712），而 cmd_attack 无
    min 门（:868 字面仅上限——勘察留痕）→ 攻击令=唯一交战入口；无攻击令
    对照组（send_attack=False）全程零弹丸零掷骰。节拍手推（aim 5/reload 30/
    速 20000/距 50000=2 拍到着、AI 节拍 100）：t1 令被 ④ 拒（t5 首扫描才
    发现）、t101 受令→t105 发射→t107 命中 −3、t135 READY 空转至 t201 复令
    （自动链整窗不接战=对照锚）。anchors=自身位置使移动令 no-op（射手静止、
    到着拍可全手推）。通道=HIT+SCATTER（直射）。"""

    SHOOTER_POS = (100000, 50000)          # 距 SOUTH 50000 < min 60000（带内盲区）

    def _world(self, send_attack):
        w = make_world(42, size_cm=MAP_SIZE)
        shooter = add_unit(w, make_unit(w, MIN_SHOOTER_TPL, 1, 1,
                                        self.SHOOTER_POS))
        bulwark = add_unit(w, make_unit(w, BULWARK_TPL, 0, 0, SOUTH))
        ai = HeadlessAI(1, anchors=(self.SHOOTER_POS, NORTH),
                        send_attack=send_attack)
        return w, shooter, bulwark, ai

    def test_manual_attack_engages_where_auto_chain_cannot(self):
        w, shooter, bulwark, ai = self._world(True)
        rng0 = [r.state for r in w.rng._rngs]
        ws = shooter.elements[0].weapon_states[0]
        snap = {}
        while w.tick < 330:
            ai.step(w)
            world_tick(w)
            t = w.tick
            if t in (1, 5, 99, 101, 105, 107, 135, 200, 205, 207, 330):
                snap[t] = (int(ws.state), ws.timer, ws.ammo_left,
                           len(w.projectiles), bulwark.elements[0].hp_current)
        self.assertEqual(snap, {
            1:   (int(WState.READY), 0, 40, 0, 200),      # t0 令被 ④ 拒（未发现）
            5:   (int(WState.READY), 0, 40, 0, 200),      # t5 发现——自动链仍不接战
            99:  (int(WState.READY), 0, 40, 0, 200),      # （min 门结构性空转）
            101: (int(WState.AIMING), 4, 40, 0, 200),     # t100 令受领（aim 5 同拍递减）
            105: (int(WState.RELOADING), 30, 39, 1, 200),  # 发射（在途 2 拍）
            107: (int(WState.RELOADING), 28, 39, 0, 197),  # 到着 −3（恒命中）
            135: (int(WState.READY), 0, 39, 0, 197),       # 装填到期→自动链空转窗
            200: (int(WState.READY), 0, 39, 0, 197),       # （对照锚：无手动令不交战）
            205: (int(WState.RELOADING), 30, 38, 1, 197),
            207: (int(WState.RELOADING), 28, 38, 0, 194),
            330: (int(WState.RELOADING), 5, 37, 0, 191),   # t305 第三发后（命中 t307）
        })
        self.assertEqual(channels_used(w, rng0), {"HIT", "SCATTER"})
        self.assertEqual(len(w.command_queue), 0)

    def test_control_without_attack_orders_zero_engagement(self):
        # 对照组：不发攻击令 → 全程零弹丸、武器恒 READY、八通道零消费
        #（自动链 min 门结构性不接战的活证——同几何同 seed 同节拍）
        w, shooter, bulwark, ai = self._world(False)
        rng0 = [r.state for r in w.rng._rngs]
        ws = shooter.elements[0].weapon_states[0]
        for _ in range(330):
            ai.step(w)
            world_tick(w)
            self.assertEqual(w.projectiles, [])
        self.assertIs(ws.state, WState.READY)
        self.assertEqual(ws.ammo_left, 40)
        self.assertEqual(bulwark.elements[0].hp_current, 200)
        self.assertEqual(channels_used(w, rng0), set())
        self.assertEqual(shooter.pos, self.SHOOTER_POS)   # 移动令 no-op（锚点=自身）

    def test_manual_engage_dual_run_bit_identical(self):
        w1, s1, b1, a1 = self._world(True)
        w2, s2, b2, a2 = self._world(True)
        while w1.tick < 330:
            a1.step(w1)
            a2.step(w2)
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertEqual(b1.elements[0].hp_current, b2.elements[0].hp_current)


class TestCommandChainFullGame(unittest.TestCase):
    """三命令合链（SetStance/ToggleAmbush/AttackCmd 整合）：SetStance 写点 →
    HOLD_FIRE 拦手动攻击（⑧ fire_permitted ② 消费侧——④ 已过：t5 首扫描发现）
    → ToggleAmbush 开启/手动退出（携首击加成）→ SetStance 解除 → AttackCmd
    受令 → fire_direct 首击 ×ambush_acc_bonus_bp（10000 基座必中）打完清。
    min_range 武器=自动链结构性不接战（发射归因唯一：只可能来自手动令）。
    节拍手推：t6 令被 ② 拒、t8 受令→t12 发射（bonus 清）→t14 命中 −3。
    同 seed 双 world 逐 tick 指纹位级一致（U 段 stance/ambush_active/
    ambush_shot_bonus 均在指纹面——三命令写点全指纹覆盖）。"""

    POS = (100000, 50000)                  # 距 NORTH 50000 < min 60000

    def _world(self, seed=42):
        w = make_world(seed, size_cm=MAP_SIZE)
        shooter = add_unit(w, make_unit(w, AMBUSH_MIN_TPL, 0, 0, self.POS))
        bulwark = add_unit(w, make_unit(w, BULWARK_TPL, 1, 1, NORTH))
        return w, shooter, bulwark

    @staticmethod
    def _queue_tickle(t, w, shooter, bulwark):
        """逐拍命令脚本（单拍份额；两跑各自以本 world 引用构造同形命令——
        frozen dataclass 可共享，但按 world 各自构造保引用纯度）：t1 stance /
        t2 开伏击 / t3 手动退出 / t6 攻击（② 拒）/ t7 解除 / t8 攻击（受令）。"""
        e = shooter.elements[0]
        if t == 1:
            queue_command(w, SetStanceCmd(unit=shooter, stance=Stance.HOLD_FIRE))
        elif t in (2, 3):
            queue_command(w, ToggleAmbushCmd(unit=shooter))
        elif t in (6, 8):
            queue_command(w, AttackCmd(element=e, target=bulwark.elements[0]))
        elif t == 7:
            queue_command(w, SetStanceCmd(unit=shooter, stance=Stance.WEAPONS_FREE))

    def test_three_commands_integrated_chain(self):
        w, shooter, bulwark = self._world()
        ws = shooter.elements[0].weapon_states[0]
        rng0 = [r.state for r in w.rng._rngs]
        for t in range(1, 21):
            self._queue_tickle(t, w, shooter, bulwark)
            world_tick(w)
            if t == 1:
                self.assertIs(shooter.stance, Stance.HOLD_FIRE)   # 写点
            if t == 2:
                self.assertTrue(shooter.ambush_active)            # 静止开启
            if t == 3:
                self.assertFalse(shooter.ambush_active)           # 手动退出
                self.assertTrue(shooter.ambush_shot_bonus)        # 携首击加成
            if t == 5:
                self.assertEqual(bulwark.spotted_mask, 1)         # 首扫描发现（④ 将过）
            if t == 6:
                self.assertIs(ws.state, WState.READY)             # ⑧ ② HOLD_FIRE 拦
                self.assertIs(shooter.stance, Stance.HOLD_FIRE)
            if t == 8:
                self.assertIs(ws.state, WState.AIMING)            # 解除后受令
                self.assertTrue(shooter.ambush_shot_bonus)        # 加成保持至发射
        self.assertIs(ws.state, WState.RELOADING)                 # t12 发射
        self.assertEqual(ws.ammo_left, 39)                        # MIN_SURE_W 满编 40
        self.assertFalse(shooter.ambush_shot_bonus)               # R-12 首击打完清
        self.assertEqual(bulwark.elements[0].hp_current, 197)     # t14 命中 −3
        self.assertEqual(channels_used(w, rng0), {"HIT", "SCATTER"})

    def test_command_chain_dual_run_bit_identical(self):
        w1, s1, b1 = self._world()
        w2, s2, b2 = self._world()
        for t in range(1, 21):
            self._queue_tickle(t, w1, s1, b1)
            self._queue_tickle(t, w2, s2, b2)
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertEqual(b1.elements[0].hp_current, b2.elements[0].hp_current)
        self.assertEqual(b1.elements[0].hp_current, 197)


class TestMotorizedFullGame(unittest.TestCase):
    """PB-56 批② 车载机动画像整局验收（2026-10-06 拖曳展开块；Mount/Dismount
    处理体=批② 首块，本块补整局面）：真购卡（t50）→ spawn_step R-07 开局预挂
    （t60，班[0]↔车 1:1、班多车少溢出班不挂）→ 车载机动（移动令受领拍 701 起
    4000cm÷22cm/拍=182 拍，t882 到）→ DismountCmd 受领拍 951 下车 → MountCmd
    受领拍 952 再上车（200 拍倒计时）→ t1151 双班重挂（㉑A 形态重建——「开局
    形态一旦下车即劣化」闭环的整局面复证；命令拍口径：step 时点 w.tick==N
    入队 → tick N+1 受领，TestManualEngage「t101 受令」同款）。
    单队无对抗 → 全程零掷骰；E 段 mounted_in/MR 段 mount_requests 均在指纹面
    内。MIXED 速度=45×5000//10000=22（WHEEL tier2）。"""

    def _world(self, seed=42):
        w = make_world(seed, phase=PHASE_DEPLOY, size_cm=MAP_SIZE)
        w.players[0].deck_slots = [DeckSlot(MIXED_TPL, 1)]
        return w

    def test_mount_maneuver_dismount_remount_chain(self):
        w = self._world()
        ai = HeadlessAI(0, motorized=True)
        rng0 = [r.state for r in w.rng._rngs]
        mot = None
        snap = {}
        while w.tick < 1200:
            ai.step(w)
            world_tick(w)
            t = w.tick
            if t == 60:                       # spawn 拍末：R-07 开局预挂
                mot = w.units[0]
                s0, s1, car = mot.elements
                snap[t] = (mot.pos, s0.mounted_in is car, s1.mounted_in is None)
            elif mot is not None and t in (700, 701, 882, 950, 951, 952,
                                           961, 1150, 1151, 1200):
                s0, s1, _car = mot.elements
                snap[t] = (mot.pos, bool(mot.move_path),
                           s0.mounted_in is not None, s1.mounted_in is not None,
                           len(w.mount_requests or ()))
        self.assertEqual(snap, {
            60:   ((100000, 0), True, True),        # 预挂：班0↔车，班1 溢出不挂
            700:  ((100000, 0), False, True, False, 0),    # 令在队（受领拍 701）
            701:  ((100022, 0), True, True, False, 0),     # 受令拍即首移拍
            882:  ((104000, 0), False, True, False, 0),    # 182 拍恰达 4000
            950:  ((104000, 0), False, True, False, 0),    # 静止（⑪ 门前置）
            951:  ((104000, 0), False, False, False, 0),   # 下车（受领拍 951）
            952:  ((104000, 0), False, False, False, 2),   # 再上车 2 请求
            961:  ((104000, 0), False, False, False, 2),   # 倒计时在途
            1150: ((104000, 0), False, False, False, 2),   # 末拍前未挂
            1151: ((104000, 0), False, True, True, 0),     # 第 200 拍双班重挂
            1200: ((104000, 0), False, True, True, 0),     # 稳态
        })
        self.assertEqual(channels_used(w, rng0), set())       # 全程零掷骰
        self.assertEqual(w.players[0].points, 910)            # 1000−90 购卡
        # 下车旁落位=载具同点位（偏移未定标登记档）
        self.assertEqual(mot.elements[0].pos, (104000, 0))
        self.assertEqual(len(w.command_queue), 0)

    def test_motorized_dual_run_bit_identical(self):
        w1, w2 = self._world(42), self._world(42)
        a1, a2 = HeadlessAI(0, motorized=True), HeadlessAI(0, motorized=True)
        while w1.tick < 1200:
            a1.step(w1)
            a2.step(w2)
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertEqual(w1.units[0].pos, w2.units[0].pos)


class TestTowDeployFullGame(unittest.TestCase):
    """PB-56 批② 拖曳展开画像整局验收（2026-10-06）：SetMode(TOW)→TowCmd 建对
    （TOWING/TOWED/redeploy_needed/清 fire_mission 四写点）→ 锁速机动（tier3
    WHEEL 35→25×5000//10000=12，GAP-14 随动偏移 300：受领拍 4 起 100 拍×12cm
    =1200cm，t103 恰达）→ UntowCmd 受领拍 201 被拖侧解挂（C3 旗保持 ③ 禁射）→
    DeployCmd 受领拍 202 首展分支（被拖炮自始 MOBILE——批②评审#3 勘正分支名；真 ELIF 重展开覆盖在 test_tow_deploy 跨链锚）300 拍（t501 DEPLOYED、旗清 ③ 放行——G17
    闭合）→ PackCmd 受领拍 511 收装 300 拍（t810 MOBILE）。单队无对抗 →
    零掷骰（fire_permitted 为直调断言，不耗弹不掷骰）。"""

    POS = (100000, 50000)

    def _world(self, seed=42):
        w = make_world(seed, size_cm=MAP_SIZE)
        tra = add_unit(w, make_unit(w, TRACTOR_FG_TPL, 0, 0, self.POS))
        gun = add_unit(w, make_unit(w, AT_GUN_FG_TPL, 0, 0, self.POS))
        return w, tra, gun

    def test_tow_move_untow_deploy_pack_chain(self):
        w, tra, gun = self._world()
        ai = HeadlessAI(0, tractor=True)
        rng0 = [r.state for r in w.rng._rngs]
        te, ge = tra.elements[0], gun.elements[0]
        snap = {}
        fire_gate = {}
        while w.tick < 850:
            ai.step(w)
            world_tick(w)
            t = w.tick
            if t in (2, 3, 11, 103, 201, 202, 501, 511, 810):
                snap[t] = (te.mode is Mode.TOW, te.towed, ge.towed,
                           ge.redeploy_needed, gun.deploy_state,
                           gun.deploy_timer, tra.pos, ge.pos,
                           len(w.tow_pairs))
            if t in (201, 501):
                fire_gate[t] = fire_permitted(w, gun, ge,
                                              ge.weapon_states[0])
        self.assertEqual(snap, {
            2:   (True, TowState.NONE, TowState.NONE, False,       # SetMode 受领拍 2
                  DeployState.MOBILE, 0, self.POS, self.POS, 0),
            3:   (True, TowState.TOWING, TowState.TOWED, True,     # TowCmd 受领拍 3：
                  DeployState.MOBILE, 0, self.POS, self.POS, 1),   # 建对四写点
            11:  (True, TowState.TOWING, TowState.TOWED, True,
                  DeployState.MOBILE, 0, (100096, 50000),
                  (99796, 50000), 1),                              # 8 拍×12 + 偏移 300
            103: (True, TowState.TOWING, TowState.TOWED, True,
                  DeployState.MOBILE, 0, (101200, 50000),
                  (100900, 50000), 1),                             # 100 拍恰达 1200
            201: (True, TowState.NONE, TowState.NONE, True,        # 解挂 C3 旗保持
                  DeployState.MOBILE, 0, (101200, 50000),
                  (100900, 50000), 0),
            202: (True, TowState.NONE, TowState.NONE, False,       # DeployCmd 清旗
                  DeployState.DEPLOYING, 299, (101200, 50000),
                  (100900, 50000), 0),
            501: (True, TowState.NONE, TowState.NONE, False,
                  DeployState.DEPLOYED, 0, (101200, 50000),
                  (100900, 50000), 0),                             # 重展开毕
            511: (True, TowState.NONE, TowState.NONE, False,
                  DeployState.PACKING, 299, (101200, 50000),
                  (100900, 50000), 0),
            810: (True, TowState.NONE, TowState.NONE, False,
                  DeployState.MOBILE, 0, (101200, 50000),
                  (100900, 50000), 0),                             # 收装毕
        })
        self.assertEqual(fire_gate, {201: False, 501: True})       # G17 闭合
        self.assertEqual(channels_used(w, rng0), set())            # 零掷骰
        self.assertEqual(gun.pos, (101200, 50000))                 # 全被拖基准随动

    def test_tow_deploy_dual_run_bit_identical(self):
        w1, t1, g1 = self._world()
        w2, t2, g2 = self._world()
        a1, a2 = HeadlessAI(0, tractor=True), HeadlessAI(0, tractor=True)
        while w1.tick < 850:
            a1.step(w1)
            a2.step(w2)
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertEqual((t1.pos, g1.pos), (t2.pos, g2.pos))


class TestFormationMarchFullGame(unittest.TestCase):
    """PB-56 批③ Formation 族整局验收（2026-10-06）：FormationCmd（命令流写槽）
    → issue_group_move（§2.9 组下令 UI 聚合**直调**——非命令流，勘察口径）→
    §2.3 增量① cap 钳制消费者（同 WHEEL 类编组 v 恒相等）→ 单独外部新令脱离
    编组（cap=0、速差分离）。命令拍口径同 TestMotorizedFullGame：step 时点
    w.tick==N 入队/直调 → 该次 world_tick 内受领。算术全手推：cap=MIN(3,1)=1
    → 双方 25×5000//10000=12cm/拍（t3 起行，4800cm 恰 400 拍 t402 到位）；
    脱离后排 70×5000//10000=35cm/拍（t403 起行）。楔形元素偏移=§2.8 锚
    （k=0 北向：r0 楔尖/r1 左后 750+1000/r2 右后/r3 左深 2000）。单队无对抗
    无武器 → 全程零掷骰；formation_shape/group_speed_cap/队列长已在指纹面
    （U 段扩面，双跑锚仅加严）。"""

    POS = (100000, 50000)

    def _world(self, seed=42):
        w = make_world(seed, size_cm=MAP_SIZE)
        plt = add_unit(w, make_unit(w, FM_PLT_TPL, 0, 0, self.POS))
        esc = add_unit(w, make_unit(w, FM_ESC_TPL, 0, 0, self.POS))
        return w, plt, esc

    def test_formation_group_march_and_detach_chain(self):
        w, plt, esc = self._world()
        ai = HeadlessAI(0, formation=True)
        rng0 = [r.state for r in w.rng._rngs]
        snap = {}
        pos_equal = True
        while w.tick < 412:
            ai.step(w)
            world_tick(w)
            t = w.tick
            if 3 <= t <= 402 and plt.pos != esc.pos:
                pos_equal = False                      # 组令期逐拍 v 相等
            if t in (2, 3, 402, 403, 412):
                snap[t] = (int(plt.formation_shape), plt.group_speed_cap,
                           esc.group_speed_cap, plt.pos, esc.pos,
                           tuple(e.pos for e in plt.elements))
        arr = (100000, 54800)                          # 50000+400 拍×12
        self.assertEqual(snap, {
            2:   (int(FormationShape.WEDGE), 0, 0,     # 队形令受领拍：槽已写、组令未下
                  self.POS, self.POS,
                  ((100000, 50000),) * 4),             # 静止不施偏移（system_move 早退）
            3:   (int(FormationShape.WEDGE), 1, 1,     # 组令首移拍：cap=MIN(3,1)
                  (100000, 50012), (100000, 50012),    # v 恒相等（12cm/拍）
                  ((100000, 50012), (99250, 49012),    # §2.8 楔形锚（k=0 北向）：
                   (100750, 49012), (99250, 48012))),  # r1 左后/r2 右后/r3 左深
            402: (int(FormationShape.WEDGE), 1, 1,     # 恰达：偏移按末段朝向保持
                  arr, arr,
                  ((100000, 54800), (99250, 53800),
                   (100750, 53800), (99250, 52800))),
            403: (int(FormationShape.WEDGE), 0, 1,     # 排单独外部新令=脱离（cap=0）
                  (100000, 54835), arr,                # 排 35cm/拍 vs 护卫静止到位
                  ((100000, 54835), (99250, 53835),
                   (100750, 53835), (99250, 52835))),
            412: (int(FormationShape.WEDGE), 0, 1,     # 10 拍×35=350 稳定分离
                  (100000, 55150), arr,
                  ((100000, 55150), (99250, 54150),
                   (100750, 54150), (99250, 53150))),
        })
        self.assertTrue(pos_equal)
        self.assertEqual(channels_used(w, rng0), set())      # 全程零掷骰
        self.assertEqual(len(w.command_queue), 0)

    def test_formation_march_dual_run_bit_identical(self):
        w1, p1, e1 = self._world(42)
        w2, p2, e2 = self._world(42)
        a1, a2 = HeadlessAI(0, formation=True), HeadlessAI(0, formation=True)
        while w1.tick < 412:
            a1.step(w1)
            a2.step(w2)
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(w1.tick, w2.tick)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertEqual((p1.pos, e1.pos), (p2.pos, e2.pos))


# ── 空中闭环·块2（2026-10-07）：纯航空无头整局——经济闭环/制空/击落/弹尽 RTB
#    全程 + 同 seed 双 world 逐 tick 指纹位级相等（A 段全字段指纹面）──

class TestAirFullGame(unittest.TestCase):
    """纯航空整局（build_air_world + HeadlessAI(air=True)，seed 42 定锚——
    全程确定性、手推成分逐条注明）：
    - 呼叫→进场（飞入时间=air_entry_offset 60000÷速——GAP-04 位置化锚）→
      攻击令（首拍=650 实战首 %50 拍）→投放（AIR 通道）→RTB（PE2 弹尽自动
      GAP3-02 在先/IL2M 投完手动弃权 B-29 在后）→回收退款（本体价 D015）→
      冷却 600 →重呼（经济轮转多周期）；
    - 制空：双方战斗机 CAP（B-20）→同空域自动缠斗（R-20）→击落 3 架
      （冷却=(600+hp_max×30)×3 精确公式锚）；
    - 通道纪律：纯航空整局只消费 AIR（无地面单位→HIT/SCATTER/SPOT 等零消费）。"""

    def test_air_fullgame_lifecycle_economy_and_settlement(self):
        w = build_air_world(42)
        rng0 = [r.state for r in w.rng._rngs]
        st = run_full_game(w, settle_extra=25,
                           ai_factory=lambda i: HeadlessAI(i, air=True))
        # 三相位全程+无异常+有输出（D031 第四链：纯航空 0:0:0:0 → 队0 胜）
        self.assertEqual(st["transitions"],
                         [(601, PHASE_DEPLOY, PHASE_COMBAT),
                          (13801, PHASE_COMBAT, PHASE_SETTLE)])
        self.assertEqual((w.result.winner, w.result.obj_counts,
                          w.result.unit_scores, w.result.hp_totals),
                         (0, (0, 0), (0, 0), (0, 0)))
        # 呼叫拍：AI t100/120 入队→world_tick 101/121 落地（命令驱动首拍）
        self.assertEqual(st["air_calls"][:4],
                         [(101, 0, 3), (101, 1, 2), (121, 0, 4), (121, 1, 14)])
        # 进场完成拍（手推：spawn+⌈60000÷speed⌉−1）：FW190A 121+239−1=359、
        # Yak-9 121+252−1=372、Pe-2 101+278−1=378、Il-2M 101+375−1=475
        # （160×375=60000 恰整除）
        self.assertEqual(st["air_arrivals"][:4],
                         [(359, 14), (372, 4), (378, 2), (475, 3)])
        # 首攻击令拍：实战首 %50 拍=650 入队→651 观测 STRIKE；首 RTB=Pe-2
        # 两轮出击 BOMB 耗尽自动 RTB（GAP3-02——salvo 2×2 轮）；缠斗/空射弹丸
        # 观测在案
        self.assertEqual(st["first_air_strike_tick"], 651)
        self.assertEqual(st["first_air_rtb_tick"], 1188)
        self.assertEqual(st["first_air_dogfight_tick"], 851)
        self.assertEqual(st["first_air_projectile_tick"], 1030)
        self.assertGreater(st["dogfight_ticks"], 0)
        # 击落 3 架（seed 42 定锚：Yak-9 咬落 Fw 190A#1@910；重呼 Fw 190A#2
        # 咬落 Yak-9@10644 与 Il-2M#5@11311）
        self.assertEqual(st["air_downed"],
                         [(910, 1, 14), (10644, 0, 4), (11311, 0, 3)])
        # 冷却公式精确锚：击落=(600+hp_max×30)×3（FW190A(600+2400)×3=9000→
        # 910+9000=9910；Yak-9(600+2100)×3=8100→10644+8100=18744；Il-2M
        # (600+3900)×3=13500→11311+13500=24811）；回收=600+损血×0（满血 Pe-2
        # 末次回收 13788+600=14388）
        self.assertEqual(dict(w.players[0].air_cooldowns), {3: 24811, 4: 18744})
        self.assertEqual(dict(w.players[1].air_cooldowns), {14: 9910, 2: 14388})
        # 经济恒等式（D015 租借闭环——实现无关不变量）：
        #   750 − Σ呼叫(本体+载荷) + Σ回收(本体) = 终值
        #   队0: 750−(96×5+70)+90×4=560；队1: 750−(109×7+80×2)+85×7=422
        for pi in (0, 1):
            spent = refunded = 0
            for _tick, team, tid in st["air_calls"]:
                if team != pi:
                    continue
                tpl = CARD_OBJECTS["IL2M"] if tid == 3 else (
                    CARD_OBJECTS["PE2"] if tid == 2 else (
                        CARD_OBJECTS["YAK9"] if tid == 4
                        else CARD_OBJECTS["FW190A"]))
                payload = {"BOMB": 2} if tid == 3 else (
                    {"BOMB": 4} if tid == 2 else {})
                spent += tpl.cost_body + sum(
                    tpl.payload_price.get(k, 0) * v for k, v in payload.items())
            for _tick, team, tid in st["air_recoveries"]:
                if team == pi:
                    refunded += (CARD_OBJECTS["IL2M"] if tid == 3 else
                                 CARD_OBJECTS["PE2"]).cost_body
            self.assertEqual(w.players[pi].air_points, 750 - spent + refunded)
        self.assertEqual([p.air_points for p in w.players], [560, 422])
        self.assertEqual(st["air_recoveries"],
                         [(1800, 1, 2), (2117, 0, 3), (3788, 1, 2), (4713, 0, 3),
                          (5788, 1, 2), (7313, 0, 3), (7788, 1, 2),
                          (9788, 1, 2), (9913, 0, 3), (11788, 1, 2),
                          (13788, 1, 2)])
        # 通道纪律：纯航空只消费 AIR（轰炸散布/缠斗掷骰；无地面单位——
        # HIT/SCATTER/SPOT/SONAR/ECONOMY/SNIPER 全零）
        self.assertEqual(channels_used(w, rng0), {"AIR"})
        self.assertEqual(st["command_residue_ticks"], 0)

    def test_air_dual_run_fingerprint_bit_identical(self):
        # 同 seed 双 world 全局锁步（含结算尾段 25 拍）：A 段全字段指纹
        # （spotted_mask/facing/flight_plan/task/ammo/alt_pending/dogfight/
        # engage_air/paratroop_cargo/no_engage_until）位级相等——航空侧任何
        # 非确定写/迭代序漂移在此暴露
        w1, w2 = build_air_world(42), build_air_world(42)
        ais1 = [HeadlessAI(i, air=True) for i in range(len(w1.players))]
        ais2 = [HeadlessAI(i, air=True) for i in range(len(w2.players))]
        ticks = 0
        while w1.phase != PHASE_SETTLE:
            for a in ais1:
                a.step(w1)
            for a in ais2:
                a.step(w2)
            world_tick(w1)
            world_tick(w2)
            ticks += 1
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        self.assertEqual(ticks, 13801)
        for _ in range(25):
            world_tick(w1)
            world_tick(w2)
            self.assertEqual(full_fingerprint(w1), full_fingerprint(w2))
        # 末态与单跑一致（队0 终值 560/422——双跑同构自证）
        self.assertEqual([p.air_points for p in w1.players], [560, 422])
        self.assertEqual([p.air_points for p in w2.players], [560, 422])


if __name__ == "__main__":
    unittest.main()

