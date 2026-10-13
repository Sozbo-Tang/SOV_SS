"""§D 数据结构（对齐伪代码 v1.7 定稿终检修复版；GAP-04/05/06/07/16/17/18 落地）。

坐标整型厘米；时长 tick（10Hz）；概率 bp 万分比；倍率 permille/bp。
枚举值与伪代码一致：UnitType 仅 INFANTRY/MECH 两类（bodyType 派生）。
条件槽（〔条件槽〕约定）：按模板能力实例化时决定分配，未分配读取恒为 None——
各读取点的 None 判断即天然短路（方案7/12）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, IntFlag


class UnitType(IntEnum):
    INFANTRY = 0  # 步兵类（含炮班、骑兵、狙击、渗透等一切 SOFT 目标）
    MECH = 1      # 机械化装备（HARD 目标，吃穿甲曲线与暴击）


class ElementType(IntEnum):
    VEHICLE = 0
    GUN = 1
    SQUAD = 2


class DamageType(IntEnum):
    KE = 0
    HE = 1
    SMOKE = 2


class Trajectory(IntEnum):
    DIRECT = 0
    BALLISTIC = 1


class Facing(IntEnum):
    FRONT = 0
    SIDE = 1
    REAR = 2
    TOP = 3


class Mode(IntEnum):
    DIRECT = 0
    INDIRECT = 1
    TOW = 2
    CARGO = 3
    TRANSPORT = 4


class DeployState(IntEnum):
    MOBILE = 0
    DEPLOYING = 1
    DEPLOYED = 2
    PACKING = 3


class WState(IntEnum):
    READY = 0
    AIMING = 1
    RELOADING = 2
    EMPTY = 3


class CritSlot(IntEnum):
    """严重损伤四类暴击槽（basics:220-230 四型左→右序；D071 全拆〔2026-10-07〕
    →**2026-10-13 终审修复块恢复**：roll_crit/roll_guaranteed_crit/upgrade_crit
    生产端回贴、四槽重新有产出者——消费端（aim/reload/optics 乘区族＋movement
    MOB 速度链＋system_supply 恢复门）零改动即活=口子设计的兑现）。"""

    FC = 0    # Targeting：瞄准时长增加/精度下降（aim_factor_bp）
    SEN = 1   # Detection：探测力下降（optics_factor_bp）
    RLD = 2   # Reloading：装填变慢（reload_factor_bp）
    MOB = 3   # Mobility：减速乃至趴窝（movement.move_speed_cm_tick）


class CritLevel(IntEnum):
    NONE = 0
    MINOR = 1
    MAJOR = 2


class MarkLevel(IntEnum):
    NONE = 0
    SPOTTED = 1
    CALIBRATED = 2


class Stance(IntEnum):
    WEAPONS_FREE = 0
    HOLD_FIRE = 1


class MoraleState(IntEnum):
    """GDD-00 D014 士气四态（2026-10-04 士气块落地；D025 阈值制——system_morale 每
    拍由存活元素压制聚合 max 对三档整数阈值确定性迁移，零掷骰）。值序=严重度序。
    独立 morale 槽口径=GDD-05 下篇 B1:100（B3:137 把 pinned/routed 列入姿态集的
    口径作废——stance 仍仅 WEAPONS_FREE/HOLD_FIRE）。"""

    STABLE = 0      # 稳定
    SUPPRESSED = 1  # 受压
    PINNED = 2      # 钉住（PB-49：可动减速——非 D014 旧文「无法移动」，已批注废止）
    ROUTED = 3      # 溃逃（失控强制移动，routed_until 计时到拍原地重整）


class AltTier(IntEnum):
    LOW = 0
    MID = 1
    HIGH = 2


class AuraKind(IntEnum):
    MELEE = 0      # 政委"跟我上"：近战火力+15%（⑬A：SPEED kind 已裁剪）
    PRECISION = 1  # 军官"按操典来"：精度+10%（方案17：射程项已裁剪）


class TargetDomain(IntFlag):
    GROUND = 1
    AIR_LOW = 2
    AIR_MID = 4
    AIR_HIGH = 8
    AIR = AIR_LOW | AIR_MID | AIR_HIGH


class MovementClass(IntEnum):
    FOOT = 0
    WHEEL = 1
    TRACK = 2
    HORSE = 3


class MoveMode(IntEnum):
    """MOVEMENT_PSEUDOCODE_v1.2 §2.1 移动模式判别槽（GAP-01；不复用 move_path 编码
    ——契约④）。四值互斥，NORMAL=现状。生命周期=当前移动令：move_path 耗尽即由
    system_move_dispatch 复位 NORMAL（§2.4 末行）；command_queue/group_speed_cap/
    formation_shape 跨令持续（§2.1 生命周期口径）。"""

    NORMAL = 0   # 普通机动（默认；现状行为逐位不变）
    ATTACK = 1   # 攻击前进（遇已发现敌停下转入射击——GAP-04/§2.5）
    MARCH = 2    # 强行军（沿路行军吃道路速度档——GAP-02/§2.6）
    REVERSE = 3  # 倒车（直线倒驶、保持车头朝向——GAP-03/§2.7）


class FormationShape(IntEnum):
    """MOVEMENT_PSEUDOCODE_v1.2 §2.1 队形形状（GAP-15 adopt 半；NONE 默认=零行为变化
    ——MV-B-19）。写点=FormationCmd（2026-10-06 PB-56 批③ Formation 族块已接——
    tick.py cmd_formation）；消费点=make_formation_fn（movement.py）。"""

    NONE = 0     # 未下令队形：formation_offset_fn=None（与现状同点堆叠一致）
    LINE = 1     # 横队（沿行进垂线展开）
    COLUMN = 2   # 纵队（沿行进反方向串列）
    WEDGE = 3    # 楔形（楔尖在前、成对左右递增纵深——§2.8 AMB-2 修正式）


class TowState(IntEnum):
    NONE = 0
    TOWING = 1  # 牵引中（v1.5 联立解：三值枚举）
    TOWED = 2   # 被拖中


class TowStopReason(IntEnum):
    """§F6 :518 stop_tow 解除因由（函数体不按因由分支——三因由同一收口）。"""
    VOLUNTARY = 0
    REPAIRED = 1
    DESTROYED = 2


class FireMissionForm(IntEnum):
    """§D.6 :233 R-13 射击形式。"""
    POINT = 0
    LINE = 1
    CREEP = 2


class SalvoMode(IntEnum):
    """§D.6 :234 R-14 半轮发射。"""
    FULL = 0
    HALF = 1


class UnitFlag(IntFlag):
    CAN_SPRINT = 1 << 0
    CAN_GARRISON = 1 << 1
    CAN_AMBUSH = 1 << 2
    CAN_INFILTRATE = 1 << 3
    NO_MOVE_VISION_PENALTY = 1 << 4
    FOREST_WALK_SILENT = 1 << 5
    REQUIRES_MARK = 1 << 6
    SINGLE_SQUAD_CARD = 1 << 7
    CAN_SNIPER_COVER = 1 << 8
    CAN_AIRDROP_BEACON = 1 << 9
    # §D.1#25 后四位（v1.7 GAP-07 补：D065/方案12/方案18 数据硬要求）
    HAS_CARGO = 1 << 10        # 由 seats/cargo 槽派生（方案12）
    HAS_MOUNT = 1 << 11        # 可上车
    HAS_SUPPLY = 1 << 12       # 物资槽分配条件（空投箱必配——GAP-21）
    SUPP_DECAY_X2 = 1 << 13    # 近卫意志近似（方案18）
    # 空裁8（2026-10-07 发起人拍板 A 案）：空降卡投送限定——「仅可经运输机空投落地」
    # （GDD-01 :99/:174 卡面字面，D017），cmd_purchase 第四门拒购。命名自查：既有令牌
    # 三族 CAN_*（能力）/HAS_*（派生槽位）/裸名（限定属性——REQUIRES_MARK/
    # SINGLE_SQUAD_CARD 等）；本位是限定非能力，不入前缀族、照裸名惯例，首词
    # DELIVERY 与卡记录层 delivery 列（P-13 空降投送限定）同词根。
    DELIVERY_AIRDROP_ONLY = 1 << 14


@dataclass(frozen=True, slots=True)
class Armor:
    """四面两类护甲，0-20 相对刻度（T 仅空袭读取）；0=无甲合法（卡车）。"""
    front: int
    side: int
    rear: int
    top: int

    def of(self, facing: Facing) -> int:
        return (self.front, self.side, self.rear, self.top)[facing]


@dataclass(frozen=True, slots=True)
class AltProfile:
    """§D.3#23 alt_profile：R-11 HE 档案 {damage, blast}（AP 主炮共槽）。"""
    damage: int
    blast_radius_cm: int


@dataclass(frozen=True, slots=True)
class SelfDefenseProfile:
    """§D.3#25 self_defense：R-15 自卫档（indirect_role 读取前判空，方案3）。"""
    max_range_cm: int
    accuracy_mult_bp: int


@dataclass(frozen=True, slots=True)
class WeaponTemplate:
    """武器 29 子字段（v1.7：27 + alt_profile/self_defense 两条件槽——GAP-04）。"""
    name: str
    target_mask: int = TargetDomain.GROUND
    damage_type: DamageType = DamageType.KE
    pen_min: int = 0
    pen_max: int = 0
    damage: int = 0
    blast_radius_cm: int = 0
    max_range_cm: int = 0
    min_range_cm: int = 0
    dispersion_cm: int = 0
    accuracy_base_bp: int = 10000
    aim_time_ticks: int = 0
    reload_time_ticks: int = 0
    salvo: int = 1
    ammo_base: int = 0
    ammo_weight: int = 1  # 每发重量 g（2026-10-03 拍板：补给按重量计——不同弹药不同重量；占位 1，数值章节定标）
    projectile_speed_cm_tick: int = 0
    trajectory: Trajectory = Trajectory.DIRECT
    suppression_power: int = 0
    crit_mod_permille: int = 1000  # 暴击概率倍率（basics:218「infantry RPGs and cluster
                              # munitions have a bigger chance」——>1000 放大；D071 全拆期间
                              # 零消费，2026-10-13 终审恢复后重新有消费者）
    crit_guaranteed: bool = False  # 步兵轻 AT 必暴击位（manual.txt:339-341「will
                              # always inflict a critical hit…even if they don't have
                              # enough penetration」——1944 题材=巴祖卡/铁拳/坦克杀手类
                              # 步兵破甲发射器；跳弹 0 伤亦触发）
    vs_fort_mult_permille: int = 1000
    needs_deployed: bool = False
    combat_style: int = 0  # 0=NORMAL 1=MELEE 2=SNIPER（v1.2 方案1 档案化）
    reveal_time_ticks: int = 0
    restricted_profiles: tuple = ()  # 受限弹药档（钨芯）{count,pen_bonus} 元组；v1.5 起每实例深拷贝计数
    alt_profile: AltProfile | None = None       # §D.3#23（GAP-04）
    self_defense: SelfDefenseProfile | None = None  # §D.3#25（GAP-04；⚠AMB-07：车载 MG 须同时配入元素 weapons[]）


@dataclass(frozen=True, slots=True)
class Aura:
    """§D.1#24 aura：政委/军官光环（查询期消费，aura_bonus_bp 连乘）。"""
    kind: AuraKind
    bonus_bp: int
    radius_cm: int


@dataclass(frozen=True, slots=True)
class ElementTemplate:
    element_type: ElementType
    unit_type: UnitType
    hp_max: int  # SQUAD=编制人数（1HP=1人）
    armor_ke: Armor | None = None  # SOFT 为 None
    armor_he: Armor | None = None
    fire_arc_deg: int = 360
    suppression_vuln_permille: int = 1000
    squad_quality_bp: int = 10000
    weapons: tuple[WeaponTemplate, ...] = ()
    seats: int = 0
    mounted_armament: tuple[WeaponTemplate, ...] | None = None  # §D.2#10 空车可射击（GAP-06；AMB-07 口径待拍板）
    cargo_rounds_max: int = 0   # §D.2#12 D065 弹药舱位（GAP-07）
    cargo_medical_max: int = 0  # §D.2#13 医疗舱位
    cargo_weight_max: int = 0   # §D.2#14 混装载重（D012）
    self_smoke_charges: int = 0  # ── PB-53 载具自卫烟幕发数（2026-10-04 拍板纳入——断箭
                                 #    N32/映射 §五.19；0=无该能力。哪些车配属=数据卡配置侧
                                 #    ——〔2026-10-07 收口轮配属 SU_TRUCK/SU_T34 各 2，P-121 已更新——原「0 卡」表述过时〕
                                 #    待定登记）。冷却/生效延迟全局常数与半径/时长复用见
                                 #    tables.py 烟雾段；消费=cmd_smoke 发数门，运行时余量
                                 #    ElementInstance.self_smoke_left 由 make_unit 自此初始化 ──


@dataclass(frozen=True, slots=True)
class UnitTemplate:
    template_id: int
    name: str
    category: int  # 0 侦察 / 1 步兵 / 2 装甲 / 3 火支 / 4 防空后勤
    cost: int
    element_templates: tuple[ElementTemplate, ...]
    optics_ground_cm: int
    stealth_base: int  # 0..10
    speed_tier: int  # 1..5
    movement_class: MovementClass
    turn_rate_deg: int = 1
    # ── PB-52 单位级地形数值 +3 槽（2026-10-04 拍板纳入——断箭 N10/映射 §五.6；推翻
    #    MOVEMENT v1.2 MV-B-01 defer 的类级系数口径，改「单位级覆盖、类级缺省回退」；
    #    水域仍随 MV-B-02 延期不设列）。0=回退类级缺省哨兵（三级回退次序见
    #    movement.move_speed_cm_tick：野=瓦片注入>单位级>类级；倒/路=单位级>类级）──
    terrain_speed_override_bp: int = 0   # 单位级越野速度 bp（0=回退类级 terrain_speed_bp[类]）
    reverse_speed_override_bp: int = 0   # 单位级倒车 bp（0=回退类级 reverse_speed_bp[类]；
                                         # 门4 资格与未来 REVERSE 速度乘区同读 movement.reverse_speed_bp）
    road_bonus_override_cm: int = 0      # 单位级道路下限 cm/tick（0=回退 cfg.road_bonus_cm_tick；
                                         # 契约⑦ max(v,·) 形态不动，仅下限常数可单位级覆盖）
    # ── PB-55 卡级士气阈值 +3 槽（2026-10-04 士气效果接线块——D027:174 生存段「士气
    #    阈值（受压/钉住/溃逃）」三值列，管线五步同 PB-52 先例：ground_cards.csv
    #    +3 列→card_schema 1.3→build_cards→card_loader→本槽。0=回退哨兵（三级回退：
    #    单位级>cfg 缺省——tick.system_morale 单点裁决；列间独立回退，可只覆盖单档，
    #    如 rout_th>100=该卡永不溃逃的差异化配置位）。现役 10 卡全空=全回退
    #    cfg 40/70/100，数值定标归数值章节──
    morale_sup_th: int = 0    # 受压阈值覆盖（0=回退 cfg.morale_sup_th）
    morale_pin_th: int = 0    # 钉住阈值覆盖（0=回退 cfg.morale_pin_th）
    morale_rout_th: int = 0   # 溃逃阈值覆盖（0=回退 cfg.morale_rout_th）
    deploy_time_ticks: int = 0
    pack_time_ticks: int = 0
    flags: UnitFlag = UnitFlag(0)
    supply_radius_cm: int = 8000
    sonar_radius_cm: int = 0
    sonar_rate: int = 0
    acoustic_signature: int = 1
    mode_set: int = 1 << Mode.DIRECT
    optics_air_cm: int = 0                    # §D.1#7 R-17 对空探测（0=无；GAP-05）
    air_ceiling: AltTier | None = None        # §D.1#8 可及高度层（None=不可及；GAP-05）
    tow_tonnage: int = 0                      # §D.1#17 牵引吨位（GAP-05）
    own_weight_tons: int = 0                  # §D.1#18 自重（GAP-05）
    repair_power_hp_per_tick: int = 0         # §D.1#19 D016 维修（GAP-05）
    close_combat_bonus_permille: int = 1000   # §D.1#16 骑兵 1800/冲锋枪高档（GAP-16）
    aura: Aura | None = None                  # §D.1#24 政委 MELEE/军官 PRECISION（GAP-17）


@dataclass(slots=True)
class WeaponState:
    template: WeaponTemplate
    state: WState = WState.READY
    timer: int = 0
    target: object = None
    ammo_left: int = 0
    restricted_left: tuple = ()  # 受限档计数（实例深拷贝）
    use_self_defense: bool = False


@dataclass(slots=True)
class ElementInstance:
    id: int
    unit: "UnitInstance"
    template: ElementTemplate
    pos: tuple[int, int]
    hp_current: int
    facing: int = 0
    crit: dict[CritSlot, CritLevel] = field(default_factory=dict)  # 仅 MECH 使用（方案7）；
    # 〔D071 2026-10-07 全拆后无生产者恒空 dict——槽位原位保留：口子①（枚举值位）
    # 与口子④（恢复路径 system_supply 修满 crit.clear()）的物理载体；指纹 E 段
    # （len+sorted items）随空 dict 天然自证「无写者」〕
    suppression: int = 0
    reveal_timer: int = 0
    mounted_in: "ElementInstance | None" = None
    weapon_states: list[WeaponState] = field(default_factory=list)
    rotating: bool = False  # 〔条件槽语义〕仅 fire_arc_deg<360 模板有效（方案6/GAP-08）
    towed: TowState = TowState.NONE
    redeploy_needed: bool = False  # v1.5 联立解：拖曳后须重展开
    mode: Mode = Mode.DIRECT
    garrison_in: object = None
    # §D.5#15-17 条件槽（仅 hasSupply/hasMount 元素分配——方案12；GAP-07）
    cargo_units: list | None = None      # TRANSPORT 舱内班（跨卡班）
    supply_weight_g: int | None = None   # CARGO 通用补给重量存量（2026-10-03 拍板：弹药/
                                         # 医疗一池按重量计；None=未分配（方案12），0=耗尽）
    # ── PB-53 载具自卫烟幕 +3 槽（元素运行时；2026-10-04 拍板纳入——断箭 N32/映射
    #    §五.19。发数能力位=template.self_smoke_charges；冷却/延迟出 cfg 烟雾段）──
    self_smoke_left: int = 0        # 剩余发数（make_unit ← template.self_smoke_charges；
                                    # 0=无能力或耗尽——cmd_smoke 发数门）
    self_smoke_ready_tick: int = 0  # 冷却门（world.tick>=此值才受令；0=开局即可。写点=
                                    # cmd_smoke 受令拍+cfg.self_smoke_cooldown_ticks——
                                    # 冷却自受令拍起算（非落烟拍），delay<cooldown 默认
                                    # 配置下与落烟拍起算无行为差）
    self_smoke_pop_tick: int = -1   # 生效延迟到期拍（-1=无在途。N32「固有部署延迟」：
                                    # cmd_smoke 受令拍+cfg.self_smoke_delay_ticks 写入，
                                    # system_timers 到拍以元素当前位置为心 append
                                    # SmokeZone 后复位 -1；载具延迟窗内被毁→烟幕随之
                                    # 取消（发数已耗不退——「不能导弹临头才按」代价））

    def is_mech(self) -> bool:
        return self.template.unit_type is UnitType.MECH


@dataclass(slots=True)
class UnitInstance:
    id: int
    team: int
    template: UnitTemplate
    pos: tuple[int, int]
    elements: list[ElementInstance] = field(default_factory=list)
    move_path: list[tuple[int, int]] = field(default_factory=list)
    deploy_state: DeployState = DeployState.MOBILE
    deploy_timer: int = 0
    stance: Stance = Stance.WEAPONS_FREE
    return_fire_until: int = -1  # 受击还击窗到期拍（-1=从未受击哨兵，pivot_to 同款
                                 # 风格）。写点=combat.apply_damage（任一元素吃到伤害
                                 # 即拍 now+cfg.return_fire_window_ticks）；消费=
                                 # tick.fire_permitted ②——HOLD_FIRE 期内仅本窗内放行
                                 # 发射（断箭官方手册 Hold Fire：「Unit(s) will not fire
                                 # unless fired upon」）。不进 state_fingerprint_text
                                 # （回放校验面零扰动——行为经弹药/弹丸位自然入指纹）
    mark_level: MarkLevel = MarkLevel.NONE
    spotted_mask: int = 0
    fire_mission: "FireMission | None" = None  # §D.4#10 R-13 炮击任务（校射两槽下沉任务体——方案10）
    infiltration_timer: int = 0
    ambush_active: bool = False
    ambush_shot_bonus: bool = False
    r02_kill_tally: int = 0
    alive: bool = True
    sprint_until: int = 0  # §D.4#16 单位级归口（v1.7 GAP-18：SprintCmd 唯一写点；元素级槽删除）
    # ── MOVEMENT_PSEUDOCODE_v1.2 §2.1 增量 +4 槽（单位运行时 17→22；GAP-1 勘误口径。
    #    计数勘误 2026-10-04：旧注「17→21」漏计 r02_kill_tally——经 dataclasses.fields
    #    实数复核修正）──
    move_mode: MoveMode = MoveMode.NORMAL          # 写点=命令族（§2.2）+ dispatch 到达复位（§2.4）
    command_queue: list = field(default_factory=list)  # 排队令链（GAP-05/18；consume_unit_commands 消费）
    group_speed_cap: int = 0                       # 编组速度钳制（0=无；GAP-16——§2.9；
                                                   # 写点=issue_group_move〔2026-10-06
                                                   # PB-56 批③ Formation 族块已接〕/
                                                   # 外部新令清 0/handoff 不清；消费=
                                                   # move_speed_cm_tick §2.3 增量①）
    formation_shape: FormationShape = FormationShape.NONE  # 队形形状（写点=FormationCmd
                                                   # 〔2026-10-06 同块已接〕；dispatch 读）
    # ── PB-51 原地转向 +1 槽（单位运行时 22→23；2026-10-04 拍板纳入——断箭 N17。
    #    计数勘误 2026-10-04：旧注「21→22」沿袭上行同向差一，实数经 fields 复核）──
    pivot_to: int = -1  # 原地转向目标朝向 deg 0..359（-1=无进行中 pivot）。写点=cmd_pivot
                        # （PivotCmd 处理体，停车后写入）；清点=到位（movement.pivot_step）/
                        # cmd_halt/issue_move 外部非排队新令。消费=system_move_dispatch 头部
                        # （独占移动拍）+ fire_permitted ⑧ 禁射门 + GAP-25 rotating 维持
                        # （tick.py）。互斥不变式：pivot_to>=0 ⇒ move_path 恒空
    # ── 士气状态机 +2 槽（单位运行时 23→25；2026-10-04 士气块——GDD-00 D014 四态/
    #    D025 阈值制/GDD-05 下篇 B1:100 morale 独立槽口径）。压制本体保持元素级
    #    ElementInstance.suppression 不动（层级错位留痕见 tick.py 登记表）；morale=
    #    单位级由元素压制聚合派生（「能算出来的不存」——每拍 system_morale 重写）──
    morale: MoraleState = MoraleState.STABLE  # 四态（消费=movement.pinned 判据缝【PB-49
                                              # 减速链】+ ROUTED 失控门族 issue_move 门0/
                                              # cmd_halt/cmd_pivot/cmd_sprint/
                                              # consume_unit_commands）
    routed_until: int = -1  # 溃逃重整到期拍（-1=非溃逃哨兵，pivot_to 同款风格）。
                            # 写点=system_morale 进入/再溃逃拍（now+morale_rally_ticks），
                            # 重整拍复位 -1
    # ── P1 机制块 +3 槽（2026-10-13，GP-01 断箭手册 P1 补建）──
    rtb_pending: bool = False        # 地面 RTB 在途（B 键——cmd_ground_rtb 写点；到场
                                     # system_rtb 结算退款移除。写点另有 cmd_cancel 撤令清位）
    dump_pending: tuple | None = None  # 卸货成堆在途位（U+点地——cmd_create_dump 写
                                     # 点；2026-10-13 终审修复块 basics:202--204「Order
                                     # your truck to unload somewhere to create a supply
                                     # dump」：到场 system_dump_delivery 落堆清位；E 撤令清）
    radar_on: bool = False           # 雷达开关（Z 高炮单位——cmd_radar 写点；缺省关，
                                     # basics:336「Radar is off by default」）
    radar_ready_tick: int = 0        # 雷达启动到期拍（cmd_radar 开=now+radar_spinup_ticks
                                     # （basics:334 5s）；关=即刻生效不写此槽。生效判据=
                                     # radar_on and world.tick>=radar_ready_tick）
    supply_switches: int = 0b1111    # 补给堆四功能开关位（basics:208-213；bit 位见
                                     # tick.py SUPPLY_SW_* 常量——缺省全开。share 位在
                                     # 单位无玩家归属面的现引擎下为呈现位（team 级拾取
                                     # 门恒同队），heal/repair/ammo 三位为 system_supply
                                     # 实门）

    def moving(self) -> bool:
        return bool(self.move_path)


@dataclass(slots=True)
class FireMission:
    """§D.6 :233-236 R-13 炮击任务体（校射两槽下沉——方案10：连内共享=同任务参与者共享
    同一 fm；任务体销毁（耗尽/取消/拖曳/切模清任务）进度随之失效）。
    target_point=(cm,cm)（POINT）；target_line=[(cm,cm),(cm,cm)]（LINE/CREEP）。
    〔GP-01 §3 表行5（2026-10-12 炮击模式块）：+ammo 弹药位 "HE"|"SMOKE"（断箭
    弹药三分类的 SOV_SS 承载——精确档=校射收束映射无新位；SMOKE=武器烟弹路径，
    fire_at 查 SMOKE 武器档落 SmokeZone）。缺省 "HE"=原行为逐位不变。〕"""
    form: FireMissionForm
    target_point: tuple[int, int] | None = None
    target_line: tuple = None               # ((cm,cm),(cm,cm)) | None
    creep_speed_cm_tick: int = 0
    ammo_mult: int = 1                      # 1..3（R-13 弹量基数）
    ammo: str = "HE"                        # "HE"|"SMOKE"（GP-01 §3——曲射弹药位）
    salvo_mode: SalvoMode = SalvoMode.FULL
    shots_left: int = 0
    shots_fired: int = 0                    # v1.4：LINE 取样序号承载（M8：按批推进）
    started_tick: int = 0
    calib_target: tuple[int, int] | None = None
    calib_progress: int = 0                 # 0..100（×calib_per_shot 按批累积——AMB-06）


@dataclass(frozen=True)
class MoveCmd:
    """§D.7 移动令 + MOVEMENT_PSEUDOCODE_v1.2 §2.2 增字段：mode=普通机动/攻击前进/
    强行军/倒车共用体（MoveMode），queue=Shift 排队位（True=入单位级 command_queue
    链尾；False=外部非排队新令四件一体覆盖——GAP-18）。queue 字段在 issue_move
    handoff=TRUE 调用下被忽略（§2.2 签名注记——AMB-11）。
    〔2026-10-07 命令族收口块迁入 types.py（原定义 tick.py §D.7 命令集——tick 顶部
    import 再出口，导入面 `from sovs.sim.tick import MoveCmd` 不变）：ReverseCmd
    特化归一（§2.2 :142 `cmd ← MoveCmd{path=[dest], mode=REVERSE, queue=FALSE}`）
    须在 movement.issue_move 门3 后门4 前构造本类——movement.py 对 tick.py 的
    反向导入边系 2026-10-06 评审明令禁止（issue_group_move 退回修复先例），命令
    dataclass 下沉共享叶模块 types.py 为零新导入边的字面落地位（FireMission
    任务体同款先例）。〕"""
    unit: object
    path: list
    mode: MoveMode = MoveMode.NORMAL
    queue: bool = False


@dataclass(frozen=True)
class ReverseCmd:
    """MOVEMENT_PSEUDOCODE_v1.2 §2.2 :119 倒车特化命令（2026-10-07 命令族收口块
    落地）：单航点直线 + REVERSE 模式——issue_move 门3 后门4 前归一化
    `cmd ← MoveCmd{path=[dest], mode=REVERSE, queue=FALSE}`（§2.2 :142 字面；
    归一化先于门4——门4 读 cmd.mode，原生 ReverseCmd 无该字段）。分派支/
    cmd_halt 过滤/consume_unit_commands 消费支均在 tick.py；门4（倒车资格）与
    §2.3 增量② 乘区/§2.4 增量④ facing 锁消费端随速度链块已活——归一化即达。
    定义落 types.py 与 MoveCmd 同址（归一化构造零反向导入边，见 MoveCmd 迁入注）。"""
    unit: object
    dest: tuple[int, int]


@dataclass(slots=True)
class TowPair:
    """§D.6 world.tow_pairs 元素（v1.5 联立解 C1；movement 拖曳随动消费——GAP-14）。"""
    tower_elements: list  # 牵引元素（TOWING；45t 可 2×30t 并拖）
    towed_element: ElementInstance


@dataclass(slots=True, eq=False)
class MountRequest:
    """§F6 :1167 / v1.6 ㉑A 上车请求条目 {squad_element, carrier, ticks_left}——
    cmd_mount 逐班建条（ticks_left 初值=mount_time_ticks），mount_requests_step 每 tick
    复核+递减+到期挂载。eq=False：引用记录按身份 remove（world.mount_requests.remove），
    字段相等不冒充同一条。"""
    squad_element: ElementInstance
    carrier: ElementInstance
    ticks_left: int


@dataclass(slots=True, eq=False)
class SmokeZone:
    """§D.6 :222 烟雾区 {pos, radius_cm, ttl_ticks}——ttl 由 system_timers 递减、
    world_tick 尾部过滤。字段名 center 为本仓消费面既有名（fingerprint 等）；
    radius_cm 字段序置于第三（兼容既有 (center, ttl) 位置构造——v1.7 三字段口径
    由 resolve_blast 以关键字传参承载，见 tick.py 登记表）。2026-10-02 ⑤块自
    tick.py 迁入（resolve_blast 落 combat.py 后跨模块引用需要）。"""
    center: tuple[int, int]
    ttl_ticks: int
    radius_cm: int = 0


@dataclass(slots=True, eq=False)
class Building:
    """§D.6 :229 Building {id, pos, hp, garrison_slots, garrisoned[Element]}——
    驻楼实体（§F5 hit_building/collapse_building 消费；写侧 apply_map 装配+cmd_garrison
    驻楼引用均已接【2026-10-06 驻楼命令块】；容量槽消费=cmd_garrison ② 门）。
    eq=False：world.buildings.remove 按身份除名。"""
    id: int
    pos: tuple[int, int]
    hp: int
    garrison_slots: int = 0
    garrisoned: list = field(default_factory=list)
