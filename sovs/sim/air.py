"""航空增量（对齐 AIR_UNITS_PSEUDOCODE_IMPL_v1.4）。

第一批（纯函数层）：§T DIR8/PERP8 几何、经济式、散布与走廊式、缠斗概率式、
侦察标记链、空投散布/信标判定、air_shooter_view（契约⑥）、entry_tier、alive 谓词。
第二批（行为层）：AircraftTemplate/AircraftInstance（§D.1/§D.2，航空自包含
结构——不入地面 types.py）、§F1 呼叫/回收/击落/移除、§F2 飞行/巡逻/高度/RTB、
§F3 攻击航线状态机与投放、§F4 自动缠斗、§F5 侦察标记、§F6 空投、§F7 aircraft_tick。
增量登记（更新，2026-10-01 接线）：world_tick 主循环接线**已完成**——sovs/sim/tick.py
落地（air_recon_step 挂 ③sensing 与 ④combat 之间、aircraft_tick 挂 ④combat 与
⑤projectiles 之间，照伪代码 v1.4 头部增量登记清单①；地面防空链 sense_air/fire_aa/
resolve_hit_aa 与 system_projectiles 一并接线，防空链地面侧函数承载于 tick.py）。
该项原属 GDD-02-航空终检报告-v1.md 第九章登记的规划内增量（范围外事项，见该报告
第一章第 5 条），本次接线即其执行。空降兵 instantiate 规划内增量**已完成
（2026-10-02 ⑥块）**：地面卡管线数据/schema/加载侧 2026-10-02 首批落地
（DATA-01 冻结：schema=sovs/sim/card_schema.py、源=data/ground_*.csv、产物=
data/gen/cards_ground.v1.json（含 SU_PARATROOP/GER_PARATROOP 两卡，air_data.
P-13 衔接登记）、加载=sovs/sim/card_loader.load_library（加载期与 air_data.
ParatroopCardSpec 对表）），tick.World.spawn_paratroop 桩已替换为
tick.make_unit(rec.unit_template,…)＋tick.add_unit 真实现（AIR §F6 :610-619——
本层 resolve_airdrop 回调语义不变：AMB3-06 构造+入 world.units 同构、deck 份
装机即扣不重扣；施工方案 §E.3 对接点闭合；详见 tick.py 登记表）。
扫射即时结算走 combat.resolve_hit（§F3 字面：Projectile{top_attack=TRUE}→resolve_hit
——契约⑥ TOP 分支即时结算 B-13；〔2026-10-07 空中闭环·块1切换〕原"combat 冻结纯函数
组合直扣"实现缺命中面压制注入且恒 TOP——地面 resolve_hit 完整体 2026-10-02 ⑤块落地，
air.py 头注预留的切换点本块执行）。

P1 机制块（2026-10-13，GP-01 断箭手册 P1 补建）：加力/燃油/弹射（manual.txt:492-497、
basics:312-314）、诱饵与导弹来袭事件口（manual.txt:505-509）、低空降速与按角色出场
高度（manual.txt:421-428）、扫射沿全航道无差别（manual.txt:411-418 取严修正）、空投
逐一跳伞+无令货机自动空投（manual.txt:430-440）。数值手册未给者一律 manual_silent
出表占位（tables.py P1 段），配属清单（哪些机型带加力/诱饵/被动对策）=数据侧
data/yaml/units/air_*.yaml。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .geom import dist_cm, octant_deg, step_toward
from .tables import BalanceConfig, CONFIG
from .types import AltTier, DamageType, Trajectory, UnitType

# §T DIR8/PERP8：全圆 8 向量（octant_deg 45° 制扇区序 0°北→315°），
# 模长 7 或 √50≈7.071（各向异性 ≈1%，√50/7≈1.015%）；DIR_NORM=7（结构常量，非平衡常数）。
DIR_NORM = 7
DIR8: tuple[tuple[int, int], ...] = (
    (0, 7), (5, 5), (7, 0), (5, -5), (0, -7), (-5, -5), (-7, 0), (-5, 5),
)
PERP8: tuple[tuple[int, int], ...] = tuple((-y, x) for (x, y) in DIR8)  # 旋转 90°


def scale(v: tuple[int, int], s: int) -> tuple[int, int]:
    """§T 标量缩放：DIR8/PERP8 向量 × s ÷ DIR_NORM（整型，跨平台确定）。"""
    return (v[0] * s // DIR_NORM, v[1] * s // DIR_NORM)


def dir_index(dx: int, dy: int) -> int:
    """八扇区索引：octant_deg 度值(0..315) → 0..7（西向 270°→索引 6，GAP-03 索引修复）。"""
    from .geom import octant_deg
    return octant_deg(dx, dy) // 45


def entry_tier(alt_ceiling: AltTier, role: "AirRole | None" = None) -> AltTier:
    """§D.1 注：进场高度层派生式 entry_tier = MIN(MID, alt_ceiling)（AMB-03，零新槽）。
    〔P1 机制块 2026-10-13：+role 形参——manual.txt:426-428「Each plane spawns on map
    with either high or low altitude depending on its role (e.g., fighters will be
    high)」：FIGHTER=MIN(HIGH, ceiling)、其余角色维持 MIN(MID, ceiling)（手册只给
    fighters-high 一例，余角色从简维持现值——manual_silent 留痕）。缺省 role=None=
    旧签名行为逐位不变（测试直调兼容面）。〕"""
    base = AltTier.HIGH if role is AirRole.FIGHTER else AltTier.MID
    return min(base, alt_ceiling)


# ── §F4 缠斗概率式（R-20：对空战力/机动性）──

def dogfight_kill_prob_bp(cfg: BalanceConfig, atk_power: int,
                          dfn_power: int, dfn_maneuver: int) -> int:
    """p = MIN(10000, base × atk_power ÷ MAX(1, dfn_power + dfn_maneuver))。
    〔二轮前自查修复：钳制与 tail 同族（GAP-25 根因=bp 输出函数钳制缺失族，
    atk≫dfn 时可超界——v1.1 §F4 注释"p<base 恒成立"错误，测试锚点逮出〕"""
    return min(10000, cfg.dogfight_base_prob_bp * atk_power // max(1, dfn_power + dfn_maneuver))


def tail_prob_bp(cfg: BalanceConfig, opponent_power: int, self_maneuver: int) -> int:
    """脱离追尾概率（GAP-25：MIN(10000, …) 钳制）。"""
    return min(10000, cfg.dogfight_tail_base_bp * opponent_power // max(1, self_maneuver))


# ── §F1 租借经济式（D015：冷却随受损增长；B-25 机型级 MAX 合并由调用方套用）──

def recovery_cooldown_ticks(cfg: BalanceConfig, hp_max: int, hp_current: int) -> int:
    """安全返场冷却 = base + 损失HP × per_hp。锚点：满血=base；损 10 HP=base+300。"""
    return cfg.air_cooldown_base_ticks + (hp_max - hp_current) * cfg.air_cooldown_per_missing_hp_ticks


def downed_cooldown_ticks(cfg: BalanceConfig, hp_max: int) -> int:
    """击落冷却 =（base + hp_max × per_hp）× downed_multiplier（满损×倍——B-04 梯度）。"""
    return (cfg.air_cooldown_base_ticks + hp_max * cfg.air_cooldown_per_missing_hp_ticks) \
        * cfg.air_cooldown_downed_multiplier


# ── §F3 投放散布与走廊（R-22/D015/D026）──

def bomb_scatter_major_cm(cfg: BalanceConfig, dispersion_cm: int, speed_cm_tick: int,
                          alt_tier: AltTier, has_dive: bool = False,
                          cloud_tier: int = 0, dump: bool = False) -> int:
    """炸弹/丢弹散布主轴（整型乘区链，次序对齐伪代码 v1.2 §F3——GAP2-14）：
    投弹：dispersion × 高度系数(has_dive 按低空) × 速度因子 × 云层系数 ×(俯冲 ×dive)；
    丢弹：dispersion × 高度系数(实飞层，不俯冲换档) × 速度因子 × dump × 云层系数。
    锚点：斯图卡（has_dive，低空系数 6000bp）×dive 5000bp = ×0.3 全场最低散布。"""
    tier_idx = alt_tier if dump else (AltTier.LOW if has_dive else alt_tier)
    r = dispersion_cm * cfg.bomb_scatter_alt_bp[tier_idx] // 10000
    r = r * max(1, speed_cm_tick) // cfg.bomb_scatter_speed_ref
    if dump:
        r = r * cfg.dump_scatter_mult_bp // 10000
    r = r * cfg.bomb_scatter_cloud_bp[cloud_tier] // 10000
    if has_dive and not dump:
        r = r * cfg.dive_scatter_mult_bp // 10000
    return r


def strafe_acc_bp(cfg: BalanceConfig, accuracy_base_bp: int, alt_tier: AltTier) -> int:
    """§F3 扫射精度 = MIN(10000, 基础 × 高度修正)（R-23 低空最高；钳制族联立修复）。"""
    return min(10000, accuracy_base_bp * cfg.strafe_acc_alt_bp[alt_tier] // 10000)


def point_segment_dist_cm(p: tuple[int, int], a: tuple[int, int],
                          b: tuple[int, int]) -> int:
    """点到线段整型距离（R-22 走廊判定；isqrt 精确整数运算，纯整型无浮点）。"""
    import math
    ax, ay = a[0] - p[0], a[1] - p[1]
    bx, by = b[0] - p[0], b[1] - p[1]
    ab2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
    if ab2 == 0:
        return math.isqrt(ax * ax + ay * ay)
    t_num = -(ax * (b[0] - a[0]) + ay * (b[1] - a[1]))
    t = max(0, min(ab2, t_num))  # 参数 t ∈ [0, ab2]（避免除法先钳分子）
    cx = ax + (b[0] - a[0]) * t // ab2
    cy = ay + (b[1] - a[1]) * t // ab2
    return math.isqrt(cx * cx + cy * cy)


def in_strafe_corridor(p: tuple[int, int], run_start: tuple[int, int],
                       run_end: tuple[int, int], cfg: BalanceConfig = CONFIG) -> bool:
    return point_segment_dist_cm(p, run_start, run_end) <= cfg.strafe_corridor_half_cm


# ── §F5 侦察标记链（D015/R-23/D026；B-23 逐拍续标）──

def recon_radius_cm(cfg: BalanceConfig, optics_air_cm: int, alt_tier: AltTier,
                    cloud_tier: int = 0) -> int:
    """观察半径 = optics × 高度修正 ×（高空时）云层系数（R-23 低小/高大；B-11 只削高空）。"""
    r = optics_air_cm * cfg.recon_optics_alt_bp[alt_tier] // 10000
    if alt_tier == AltTier.HIGH:
        r = r * cfg.cloud_air_recon_mult_bp[cloud_tier] // 10000
    return r


def recon_mark_prob_bp(cfg: BalanceConfig, mark_base_bp: int, alt_tier: AltTier,
                       speed_cm_tick: int, cloud_tier: int = 0) -> int:
    """标记概率 = base × 高度修正 × 速度因子(cap 10000) ×（高空时）云层系数。
    锚点：慢速(Po-2)速度因子=10000；两倍基准速=5000。"""
    p = mark_base_bp * cfg.recon_mark_alt_bp[alt_tier] // 10000
    speed_factor = min(10000, cfg.air_recon_speed_ref * 10000 // max(1, speed_cm_tick))
    p = p * speed_factor // 10000
    if alt_tier == AltTier.HIGH:
        p = p * cfg.cloud_air_recon_mult_bp[cloud_tier] // 10000
    return min(10000, p)  # 钳制族联立修复（GAP-25 根因）


# ── §F6 空投散布与信标（R-21/D015/契约⑤；B-16 最近吸附）──

def airdrop_scatter_cm(cfg: BalanceConfig, alt_tier: AltTier,
                       speed_cm_tick: int) -> int:
    """空投散布 = base × 高度系数 × 速度因子（D015 高度×速度）。"""
    return (cfg.airdrop_scatter_base_cm * cfg.airdrop_scatter_alt_bp[alt_tier] // 10000
            * max(1, speed_cm_tick) // cfg.airdrop_scatter_speed_ref)


def nearest_friendly_beacon(beacon_by_unit: dict, team: int, drop_point: tuple[int, int],
                            cfg: BalanceConfig = CONFIG):
    """B-16：距投放点最近的己方信标且 ≤吸附半径 → 返回该 pos；否则 None。
    beacon_by_unit 键型适配（2026-10-06 信标令落地同修——PB-45 cover_by_target
    同款）：键=unit.id（UnitInstance mutable 不可哈希）、值=(team, pos)——队属
    随值携带免读侧回查（§D.6 :246 键=unit/值=pos 的实现适配，登记在案）；
    写侧=cmd_set_airdrop_beacon（tick.py）、注销侧=unregister（combat.py
    pop(unit.id)）——三口同形。插入序 map（并列取首个 ≤ 保先见者——确定性）。"""
    from .geom import dist_cm
    best, best_d = None, cfg.airdrop_beacon_radius_cm
    for _uid, entry in beacon_by_unit.items():
        bteam, pos = entry
        if bteam != team:
            continue
        d = dist_cm(pos, drop_point)
        if d <= best_d:
            best, best_d = pos, d
    return best


def airdrop_beacon_mult(cfg: BalanceConfig) -> int:
    """契约⑤冻结值（出表常量访问器——散布 ×5000bp）。"""
    return cfg.airdrop_beacon_mult_bp


# ── §D.3 契约⑥：空射射手视图（GAP-17 适配器）──

class _AirShooterTemplate:
    """最小只读适配：暴露 unit_type=MECH（squad_hp_factor_bp 走非步兵分支恒 10000bp）。"""

    unit_type = UnitType.MECH


class AirShooterView:
    """空射弹丸 shooter 适配器——满足地面 Projectile{shooter: Element} 类型契约
    （combat.squad_hp_factor_bp 读 shooter.template.unit_type 可求值）。"""

    __slots__ = ("template", "hp_current", "aircraft")

    def __init__(self, aircraft) -> None:
        self.aircraft = aircraft
        self.template = _AirShooterTemplate()
        # §D.3（GAP-17 成文）：hp_current=hp_max 语义——取模板满值而非飞机当前血量（缺模板兜底 0）
        self.hp_current = getattr(getattr(aircraft, "template", None), "hp_max", 0)


def air_shooter_view(a) -> AirShooterView:
    return AirShooterView(a)


def is_aircraft_alive(a, world) -> bool:
    """§D.2 存活谓词（AMB-02 ③）：alive(a) := a IN world.aircraft——航空侧供给，
    地面 finish_aim/resolve 消费的对空存活判据由此成立（地面文档零改动）。"""
    return a in world.aircraft


# ══════════════════ 行为层（第二批，对齐 v1.2 §D.1/§D.2/§F1~§F7）══════════════════

from enum import IntEnum  # noqa: E402


class AirRole(IntEnum):
    RECON = 0
    BOMBER = 1
    ATTACK = 2
    FIGHTER = 3
    TRANSPORT = 4


class AirState(IntEnum):
    INBOUND = 0
    PATROL = 1
    STRIKE = 2
    RTB = 3
    DOGFIGHT = 4


class StrikePhase(IntEnum):
    INGRESS = 0
    RUN = 1
    EGRESS = 2


class TaskKind(IntEnum):
    STRIKE = 0
    PATROL = 1
    AIRDROP = 2


# phase 常量（对齐地面盲部署/实战/结算三态；world.phase 以此判等）。
# 2026-10-03 发起人拍板：取消开局禁火相位（D007/D008=GDD-00 :55/:59 废止）、盲部署
# 90s→60s——原 v1.7 四态（0=DEPLOY/1=HOLD/2=COMBAT/3=SETTLE）删 HOLD 后重排为 0/1/2。
PHASE_DEPLOY, PHASE_COMBAT, PHASE_SETTLE = 0, 1, 2


@dataclass(frozen=True, slots=True)
class AircraftTemplate:
    """§D.1 航空模板静态 20（独立模板 B-01；空射武器复用地面 WeaponTemplate）。"""
    template_id: int
    name: str
    role: AirRole
    cost_body: int
    hp_max: int
    armor_aa: int
    speed_cm_tick: int
    dogfight_power: int
    maneuver: int
    alt_ceiling: AltTier
    optics_air_cm: int = 0
    recon_mark_base_bp: int = 0
    weapons: tuple = ()            # (WeaponTemplate, 弹量) 元组——GAP2-04：STRAFE 弹药来源
    payload_max_bombs: int = 0
    payload_max_supply: int = 0
    paratroop_seats: int = 0
    turret_damage: int = 0
    can_engage_air: bool = False
    has_dive: bool = False
    payload_price: dict = field(default_factory=dict)  # {BOMB: 单价, SUPPLY: 每重量单位单价}（2026-10-03 拍板：载荷一池化）
    # ── P1 机制块 +3 槽（2026-10-13，GP-01 断箭手册 P1 补建——basics/ABILITIES；
    #    数值/配属清单手册未给→manual_silent，数据侧 data/yaml/units/air_*.yaml）──
    can_afterburner: bool = False   # 加力资格（manual.txt:492-497「Afterburner … Press Z」
                                    # ——仅战斗机配属，YAK9/FW190A）
    decoy_charges: int = 0          # 诱饵发数（manual.txt:505-509「ammo limited and can be
                                    # resupplied」——再补给走「不能图上补给」飞机限制位，
                                    # 回基地冷却后再呼入即满发，manual_silent 留痕）
    passive_evade_bp: int = 0       # 被动对策规避 bp（basics:353-356「reduces the probability
                                    # of missiles to hit」——fire_aa acc 乘区；统计面板以 %
                                    # 显示=帧 evade_pct）


@dataclass(slots=True)
class AirTask:
    """§D.2 #14 任务槽（判别联合 G v1.1 联立解——kind 判别，未用变体字段为 None）。"""
    kind: TaskKind
    weapon: str | None = None                 # STRIKE 变体：'BOMB' | 'STRAFE'
    target: tuple[int, int] | None = None     # STRIKE
    phase: StrikePhase | None = None          # STRIKE/AIRDROP
    run_start: tuple[int, int] | None = None
    run_end: tuple[int, int] | None = None
    center: tuple[int, int] | None = None     # PATROL
    radius: int = 0                           # PATROL
    drop: tuple[int, int] | None = None       # AIRDROP
    sticks_done: int = 0                      # AIRDROP P1：已投 stick 数（逐一跳伞节拍账）


@dataclass(slots=True)
class DogfightState:
    """§D.2 #17 缠斗任务体（rounds 入体——GAP-01；is_disengaging 死槽已删）。"""
    opponent: "AircraftInstance"
    round_timer: int
    rounds: int = 0


@dataclass(slots=True)
class AirProjectile:
    """空射弹丸（字段名对齐地面 Projectile 冻结语义；推进/落点结算属地面 system_projectiles
    规划内增量——航空侧生成，BALLISTIC 不分敌我/近失压制由该管线承载）。"""
    shooter: object
    weapon: object
    damage_type: DamageType
    damage: int
    blast_cm: int
    pos: tuple[int, int]
    dest: tuple[int, int]
    speed_cm_tick: int
    trajectory: Trajectory
    hit_target: object
    will_hit: bool
    top_attack: bool = False
    pen_bonus: int = 0        # 对齐地面 Projectile 档案位（§F4 :790——resolve_hit
                              # 读 p.pen_bonus；2026-10-07 空中闭环·块1 扫射切
                              # resolve_hit 随补，空射恒 0）


@dataclass(slots=True)
class AircraftInstance:
    """§D.2 航空运行时 21（含契约① 八字段；构造默认 AMB2-02 成文）。"""
    id: int
    team: int
    player_index: int
    template: AircraftTemplate            # #0 模板指针槽（GAP2-12）
    pos: tuple[int, int]
    alt_tier: AltTier
    hp_current: int
    spotted_mask: int = 0                 # 地面 sense_air 唯一写者，航空只读
    state: AirState = AirState.INBOUND
    facing: int = 0
    flight_plan: list = field(default_factory=list)
    patrol_loop: bool = False
    task: AirTask | None = None           # 任务槽判别联合
    ammo_left: dict = field(default_factory=dict)   # BOMB/STRAFE/SUPPLY（补给重量 g）
    alt_pending: tuple | None = None      # (target_tier, ticks_left)——条件槽
    dogfight: DogfightState | None = None
    engage_air: bool | None = None        # 条件槽：can_engage_air 或 FIGHTER
    paratroop_cargo: object | None = None  # 条件槽：paratroop_seats>0（舱内空降卡模板；
                                    # 份数账在 paratroop_left——P1「逐一跳伞」节拍消费）
    no_engage_until: int = 0
    # ── P1 机制块 +6 槽（2026-10-13，GP-01 断箭手册 P1 补建）──
    paratroop_left: int = 0         # 舱内空降份数（cmd_air_call ← payload["PARATROOP_COUNT"]
                                    # 缺省 1；resolve_airdrop 逐 stick 递减，0 时清 cargo——
                                    # manual.txt:432-433「jump out one by one」）
    afterburner: bool = False       # 加力开关（cmd_air_afterburner 写点；速度/油耗 ×2——
                                    # manual.txt:492-497 toggle）
    fuel_ticks: int = -1            # 燃油余量（-1=未初始化哨兵；cmd_air_call ← cfg.
                                    # air_fuel_ticks。耗尽=飞行员被迫跳伞 eject——basics:
                                    # 312-314，走 air_downed 同链（冷却+无退款），manual_silent）
    decoy_left: int = 0             # 诱饵余发（cmd_air_call ← template.decoy_charges）
    decoy_auto: bool = True         # 诱饵自动模式（basics:351-352 右键切换自动档；缺省开
                                    # ——basics 未言缺省，manual_silent 从简）
    evade_until: int = 0            # 诱饵规避窗到期拍（0=无在途；fire_aa acc 乘区消费）
    auto_drop_tick: int = 0         # 无令货机自动空投到期拍（0=无排程；进场到场拍+
                                    # cfg.airdrop_auto_delay_ticks——manual.txt:434-440）

    @property
    def hp_max(self) -> int:              # 契约①字段引用槽
        return self.template.hp_max

    @property
    def armor_aa(self) -> int:
        return self.template.armor_aa


def _air(rng_air, bp: int) -> bool:
    return rng_air.chance_bp(bp)


def payload_price_of(t: AircraftTemplate, payload: dict) -> int:
    """§F1 payload_price：模板价表逐项（空降兵不计价——D017 预备队池已付）。"""
    return sum(t.payload_price.get(k, 0) * v for k, v in payload.items()
               if k in ("BOMB", "SUPPLY"))


# ── §F1 经济与租借 ──

def cmd_air_call(world, player, template: AircraftTemplate, payload: dict,
                 cfg: BalanceConfig = CONFIG) -> AircraftInstance | None:
    """AirCallCmd：slot_ok→容量→在空≤2→冷却→点数→空降 deck 份→扣费→spawn INBOUND。
    payload={BOMB:int, SUPPLY:int(重量 g), PARATROOP:地面卡模板|None}。"""
    r = template.role
    if r is AirRole.BOMBER or r is AirRole.ATTACK:
        slot_ok = payload.get("PARATROOP") is None and payload.get("SUPPLY", 0) == 0
    elif r is AirRole.TRANSPORT:
        slot_ok = payload.get("BOMB", 0) == 0
    else:  # FIGHTER/RECON：空载荷
        slot_ok = all(payload.get(k, 0) == 0 for k in ("BOMB", "SUPPLY")) \
            and payload.get("PARATROOP") is None
    if not slot_ok:
        return None                                                   # GAP2-26 修复后的门
    if payload.get("BOMB", 0) > template.payload_max_bombs:
        return None                                                   # GAP2-13 容量门
    if payload.get("SUPPLY", 0) > template.payload_max_supply:
        return None
    n_same = sum(1 for x in world.aircraft
                 if x.team == player.team and x.template.template_id == template.template_id)
    if n_same >= cfg.air_per_type_max:                               # B-24/AMB3-08：在空上限出表
        return None
    cd = player.air_cooldowns.get(template.template_id, 0)
    if world.tick < cd:
        return None
    # 2026-10-14 空袭按用计费块（用户拍板「要扣空投和炸弹的花费」）：BOMB 载荷
    # 不再呼叫预付——改 resolve_bomb_release 每发投放扣 air_points（单价=模板
    # payload_price["BOMB"]，max(0,·) 钳同空投作业费款式；被击落剩余弹未付费=
    # 按用实付自洽）。SUPPLY 仍呼叫预付（空投作业费=另一作业面，不双计）。
    cost = template.cost_body + payload_price_of(
        template, {"SUPPLY": payload.get("SUPPLY", 0)})
    if player.air_points < cost:
        return None
    paratroop_tpl = payload.get("PARATROOP")
    ps = None
    if paratroop_tpl is not None:                                     # B-06/B-12：装机即扣份
        ps = next((s for s in player.deck_slots if s.template is paratroop_tpl), None)
        if ps is None or ps.copies_left <= 0:
            return None
    player.air_points -= cost
    if ps is not None:
        ps.copies_left -= 1
    entry = world.air_entry_point(player.team)                        # 己方底边场外点（world 注入）
    a = AircraftInstance(id=world.next_aircraft_id, team=player.team,
                         player_index=player.index, template=template,
                         pos=entry, alt_tier=entry_tier(template.alt_ceiling, r),
                         hp_current=template.hp_max, state=AirState.INBOUND)
    world.next_aircraft_id += 1
    # P1 机制块（2026-10-13）：燃油/诱饵/空降份数运行时初始化（模板缺省 0/缺省份数 1）
    a.fuel_ticks = cfg.air_fuel_ticks
    a.decoy_left = template.decoy_charges
    ammo = {"BOMB": payload.get("BOMB", 0),
            "SUPPLY": payload.get("SUPPLY", 0)}
    for w, n in template.weapons:                                     # GAP2-04：STRAFE←weapons[] 弹量
        if weapon_slot(w) == "STRAFE":                                # 复检①：与 _weapon_of 同一口径
            ammo["STRAFE"] = ammo.get("STRAFE", 0) + n
    ammo.setdefault("STRAFE", 0)
    a.ammo_left = ammo
    if template.paratroop_seats > 0:
        a.paratroop_cargo = paratroop_tpl
        # P1「逐一跳伞」份数账（manual.txt:432-433）：payload["PARATROOP_COUNT"] 可装
        # 多份（受 deck 余份与 paratroop_seats 钳制；缺省 1=旧行为）。装机即扣份
        # B-06/B-12 同拍——份数扣减在此（cmd_air_call 经济段之后）。
        count = int(payload.get("PARATROOP_COUNT", 1) or 1)
        count = max(1, min(count, template.paratroop_seats))
        if ps is not None:
            count = min(count, ps.copies_left + 1)               # deck 余份钳（经济段
                                                                # 已扣 1——余份≥1 上面
                                                                # ≤0 已整呼叫拒）
            ps.copies_left -= count - 1
        a.paratroop_left = count
    if template.can_engage_air or r is AirRole.FIGHTER:               # AMB2-02：FIGHTER 同配槽
        a.engage_air = False
    cx, cy = world.map_center
    k = dir_index(cx - entry[0], cy - entry[1])
    a.flight_plan = [tuple(entry[i] + scale(DIR8[k], cfg.air_entry_offset_cm)[i] for i in (0, 1))]
    world.aircraft.append(a)
    return a


def air_recovery(world, a: AircraftInstance, cfg: BalanceConfig = CONFIG) -> None:
    """§F1 安全飞离：舱内班退份（B-27②）→本体价回收→冷却 MAX 合并（B-25）。
    〔P1 机制块 2026-10-13：舱内份按 paratroop_left 计（多份装载/逐 stick 投放后
    余份全退——「逐一跳伞」份数账的回收侧）。〕"""
    player = world.players[a.player_index]
    tid = a.template.template_id
    if a.paratroop_cargo is not None:
        ps = next((s for s in player.deck_slots if s.template is a.paratroop_cargo), None)
        if ps is not None:
            ps.copies_left += a.paratroop_left
        a.paratroop_cargo = None
        a.paratroop_left = 0
    player.air_points += a.template.cost_body
    new_cd = world.tick + recovery_cooldown_ticks(cfg, a.template.hp_max, a.hp_current)
    player.air_cooldowns[tid] = max(player.air_cooldowns.get(tid, 0), new_cd)
    remove_aircraft(world, a)


def air_downed(world, a: AircraftInstance, cfg: BalanceConfig = CONFIG) -> None:
    """§F1 击落：舱内班亡不退（B-06）→击落冷却 MAX（B-04/B-25）→移除。"""
    player = world.players[a.player_index]
    tid = a.template.template_id
    a.paratroop_cargo = None                                           # 班随机毁（deck 份已扣）
    new_cd = world.tick + downed_cooldown_ticks(cfg, a.template.hp_max)
    player.air_cooldowns[tid] = max(player.air_cooldowns.get(tid, 0), new_cd)
    remove_aircraft(world, a)


def remove_aircraft(world, a: AircraftInstance) -> None:
    """§F1 移除：缠斗对偶清理（GAP-16）+在途弹丸自清（GAP-02/AMB2-04）。"""
    for x in world.aircraft:
        if x.dogfight is not None and x.dogfight.opponent is a:
            exit_dogfight(world, x, "OPPONENT_DOWNED")
    for p in world.projectiles:
        if p.hit_target is a:
            p.hit_target = None
            p.will_hit = False                                         # 晚到弹按冻结分派近失压制
    world.aircraft.remove(a)


# ── §F2 飞行与高度 ──

def patrol_waypoints(center: tuple[int, int], radius: int) -> list:
    c, r = center, radius
    return [(c[0] - r, c[1] - r), (c[0] + r, c[1] - r), (c[0] + r, c[1] + r), (c[0] - r, c[1] + r)]


def enter_patrol_hold(world, a: AircraftInstance, cfg: BalanceConfig = CONFIG) -> None:
    """待命盘旋统一入口（GAP-23）：任务槽 PATROL 变体就位。"""
    a.state = AirState.PATROL
    a.patrol_loop = True
    a.task = AirTask(kind=TaskKind.PATROL, center=a.pos, radius=cfg.patrol_orbit_radius_cm)
    a.flight_plan = patrol_waypoints(a.pos, cfg.patrol_orbit_radius_cm)


def _strike_busy(a: AircraftInstance) -> bool:
    """RUN/EGRESS 直线段不可中断（GAP-28/GAP2-06 统一式）。"""
    return (a.state is AirState.STRIKE and a.task is not None
            and a.task.kind is not TaskKind.PATROL
            and a.task.phase is not StrikePhase.INGRESS)


def cmd_air_patrol(world, a: AircraftInstance, center: tuple[int, int], radius: int) -> bool:
    if a.state in (AirState.DOGFIGHT, AirState.RTB):
        return False
    if _strike_busy(a):
        return False
    a.auto_drop_tick = 0                    # P1：显式令撤销自动空投排程
    a.task = AirTask(kind=TaskKind.PATROL, center=center, radius=radius)
    a.state = AirState.PATROL
    a.patrol_loop = True
    a.flight_plan = patrol_waypoints(center, radius)
    return True


def cmd_air_move(world, a: AircraftInstance, path: list) -> bool:
    if a.state in (AirState.DOGFIGHT, AirState.RTB):
        return False
    if _strike_busy(a):
        return False
    a.auto_drop_tick = 0                    # P1：显式令撤销自动空投排程
    a.task = None
    a.state = AirState.PATROL
    a.patrol_loop = False
    a.flight_plan = list(path)
    return True


def cmd_air_alt(world, a: AircraftInstance, tier: AltTier,
                cfg: BalanceConfig = CONFIG) -> bool:
    # 空裁6（2026-10-07 发起人拍板采纳）：cfg 形参补齐——原直读全局 CONFIG
    if tier > a.template.alt_ceiling or a.state is AirState.DOGFIGHT:
        return False
    if tier == a.alt_tier and a.alt_pending is None:
        return True
    a.alt_pending = (tier, cfg.alt_transition_ticks)
    return True


def cmd_air_rtb(world, a: AircraftInstance) -> bool:
    if a.state is AirState.DOGFIGHT:
        return False
    a.auto_drop_tick = 0                    # P1：显式令撤销自动空投排程
    a.task = None
    a.patrol_loop = False
    a.state = AirState.RTB
    a.flight_plan = [world.rtb_exit_point(a.team)]
    return True


def aircraft_move_step(world, a: AircraftInstance, cfg: BalanceConfig = CONFIG) -> None:
    if a.state is AirState.DOGFIGHT:
        return
    if a.alt_pending is not None:
        t, left = a.alt_pending
        left -= 1
        if left <= 0:
            a.alt_tier = t
            a.alt_pending = None
        else:
            a.alt_pending = (t, left)
    # ── P1 燃油/加力/低空降速（2026-10-13，manual.txt:421-428/:492-497、basics:312-314）──
    # 油耗=每拍 1（加力 ×2——afterburner_fuel_mult_bp）；耗尽=飞行员被迫跳伞 eject
    # （走 air_downed 同链：冷却+无退款+舱内份亡——手册未给区别性后果，manual_silent）。
    # 燃油只在飞机实际飞行（非 settle/已移除）时消耗——aircraft_tick settle 早退兜底。
    if a.fuel_ticks > 0:
        a.fuel_ticks -= (cfg.afterburner_fuel_mult_bp // 10000
                         if a.afterburner else 1)
        if a.fuel_ticks <= 0:
            a.fuel_ticks = 0
            a.afterburner = False                                   # 无油不加力
            air_downed(world, a, cfg)                               # eject（basics:312-314）
            return
    budget = a.template.speed_cm_tick
    if a.afterburner:                                               # 加力 ×2
        budget = budget * cfg.afterburner_speed_mult_bp // 10000
    if a.alt_tier is AltTier.LOW:                                   # 低空降速
        budget = budget * cfg.alt_low_speed_mult_bp // 10000
    while budget > 0 and a.flight_plan:
        dest = a.flight_plan[0]
        prev = a.pos
        a.pos, arrived = step_toward(a.pos, dest, budget)
        if arrived:
            a.flight_plan.pop(0)
            budget -= dist_cm(prev, dest)
            if not a.flight_plan and a.patrol_loop and a.task is not None \
                    and a.task.kind is TaskKind.PATROL:
                a.flight_plan = patrol_waypoints(a.task.center, a.task.radius)
        else:
            budget = 0
    if a.state is AirState.INBOUND and not a.flight_plan:
        # P1 无令货机自动空投排程（manual.txt:434-440：进场到场=呼叫点；无其他命令
        # 时延迟窗后自动投放。任何显式令在 cmd_air_* 侧清零本排程——「given no
        # other orders」字面；EGRESS/缠斗收尾走 enter_patrol_hold 不经此支）。
        if (a.template.role is AirRole.TRANSPORT
                and (a.paratroop_cargo is not None
                     or a.ammo_left.get("SUPPLY", 0) > 0)):
            a.auto_drop_tick = world.tick + cfg.airdrop_auto_delay_ticks
        enter_patrol_hold(world, a, cfg)
    if a.state is AirState.STRIKE:
        strike_step(world, a, cfg)
    if a.state is AirState.RTB and not a.flight_plan:
        air_recovery(world, a, cfg)                                   # AMB-08：到达航点即回收


def _set_facing(a: AircraftInstance, start: tuple[int, int]) -> None:
    if a.pos != start:
        a.facing = octant_deg(a.pos[0] - start[0], a.pos[1] - start[1])


# ── §F3 攻击航线与对地投放 ──

def _run_points(target: tuple[int, int], from_pos: tuple[int, int],
                cfg: BalanceConfig) -> tuple:
    k = dir_index(target[0] - from_pos[0], target[1] - from_pos[1])
    s = scale(DIR8[k], cfg.strafe_run_lead_cm)
    return (tuple(target[i] - s[i] for i in (0, 1)),
            tuple(target[i] + s[i] for i in (0, 1)))


def weapon_slot(w) -> str | None:
    """§D.3 档身份按配置判定（与 name 无关；§F1 弹药初始化与 _weapon_of 同一 helper
    ——复检①统一谓词）：STRAFE 档=DIRECT ∧ KE ∧ GROUND；BOMB 档=HE ∧ BALLISTIC ∧
    GROUND；其余 None。"""
    if not (w.target_mask & 1):                                        # GROUND
        return None
    if w.trajectory is Trajectory.DIRECT and w.damage_type is DamageType.KE:
        return "STRAFE"
    if w.trajectory is Trajectory.BALLISTIC and w.damage_type is DamageType.HE:
        return "BOMB"
    return None


def _weapon_of(a: AircraftInstance, key: str):
    for w, _n in a.template.weapons:
        if weapon_slot(w) == key:
            return w
    return None


def cmd_air_strike(world, a: AircraftInstance, target: tuple[int, int], weapon: str,
                   axis=None, cfg: BalanceConfig = CONFIG) -> bool:
    """§F3 cmd_air_strike（attack run 状态机；空裁6 cfg 形参补齐——_run_points 原
    直传全局 CONFIG）。
    〔GP-01 §4 ③段（2026-10-12 空中可控块·评审②补）：+axis 可选攻击轴
    ((cm,cm),(cm,cm))|None——K+拖拽画线形态（对齐断箭「按住左键拖拽，一次性确定
    打击位置与航线走向」/仓库落档 GDD-06 A1:157-159、FE-01:54）。有 axis 时
    run_start/run_end 按玩家线向（axis[0]→axis[1]＝攻击方向）推导——替代
    _run_points 的 from_pos 机位向（「先调好进场角再下攻击令」的航点纪律由玩家
    显式承载）；缺省 None=现行为逐位不变。目标点仍取 target（UI 画线时取线段
    瞄准点，命令层不猜）。〕"""
    if a.state in (AirState.DOGFIGHT, AirState.RTB):
        return False
    if _strike_busy(a):
        return False
    if a.ammo_left.get(weapon, 0) <= 0:
        return False
    if world.phase == PHASE_SETTLE:
        return False
    if axis is not None:                                     # GP-01 §4：画线攻击轴
        k = dir_index(axis[1][0] - axis[0][0], axis[1][1] - axis[0][1])
        s = scale(DIR8[k], cfg.strafe_run_lead_cm)
        rs = tuple(target[i] - s[i] for i in (0, 1))
        re = tuple(target[i] + s[i] for i in (0, 1))
    else:
        rs, re = _run_points(target, a.pos, cfg)
    a.auto_drop_tick = 0                    # P1：显式令撤销自动空投排程
    a.task = AirTask(kind=TaskKind.STRIKE, weapon=weapon, target=target,
                     phase=StrikePhase.INGRESS, run_start=rs, run_end=re)
    a.state = AirState.STRIKE
    a.patrol_loop = False
    a.flight_plan = [rs]
    return True


def cmd_air_airdrop(world, a: AircraftInstance, drop_point: tuple[int, int],
                    cfg: BalanceConfig = CONFIG) -> bool:
    # 空裁6（2026-10-07 发起人拍板采纳）：cfg 形参补齐——_run_points 原直传全局 CONFIG
    if a.state in (AirState.DOGFIGHT, AirState.RTB):
        return False
    if _strike_busy(a):
        return False
    if a.template.role is not AirRole.TRANSPORT:
        return False
    if a.ammo_left.get("SUPPLY", 0) <= 0 \
            and a.paratroop_cargo is None:
        return False
    if world.phase == PHASE_SETTLE:
        return False
    rs, re = _run_points(drop_point, a.pos, cfg)
    a.auto_drop_tick = 0                    # P1：显式令撤销自动空投排程
    a.task = AirTask(kind=TaskKind.AIRDROP, drop=drop_point,
                     phase=StrikePhase.INGRESS, run_start=rs, run_end=re)
    a.state = AirState.STRIKE
    a.flight_plan = [rs]
    return True


def strike_step(world, a: AircraftInstance, cfg: BalanceConfig = CONFIG) -> None:
    s = a.task
    if s is None or s.kind is TaskKind.PATROL:
        return
    line_point = s.drop if s.kind is TaskKind.AIRDROP else s.target
    if s.phase is StrikePhase.INGRESS and a.pos == s.run_start:
        if world.phase != PHASE_COMBAT:
            return                                                     # GAP2-03：非实战期（盲部署/结算）悬停 run_start
        s.phase = StrikePhase.RUN
        a.flight_plan = [s.run_end]
        if s.kind is TaskKind.STRIKE and s.weapon == "STRAFE":
            resolve_strafe(world, a, s, cfg)
    elif s.phase is StrikePhase.RUN:
        if s.kind is TaskKind.AIRDROP:
            # P1「逐一跳伞」（manual.txt:432-433）：RUN 段逐 stick 投放（几何过点
            # 触发——airdrop_run_step）；投毕或抵达 run_end 转 EGRESS（残余舱载保留，
            # 由弹尽自动 RTB/玩家令接管）。
            airdrop_run_step(world, a, s, cfg)
            empty = ((a.paratroop_cargo is None or a.paratroop_left <= 0)
                     and a.ammo_left.get("SUPPLY", 0) <= 0)
            if empty or not a.flight_plan:
                if world.phase == PHASE_COMBAT:
                    s.phase = StrikePhase.EGRESS
                else:
                    s.phase = StrikePhase.INGRESS                      # GAP2-03：非实战期挂起重走
                    a.flight_plan = [s.run_start]
        elif dist_cm(a.pos, line_point) <= a.template.speed_cm_tick:
            if s.weapon == "BOMB":
                resolve_bomb_release(world, a, s, cfg)
            if world.phase == PHASE_COMBAT:
                s.phase = StrikePhase.EGRESS
            else:
                s.phase = StrikePhase.INGRESS                          # GAP2-03：非实战期挂起回 INGRESS 重走
                a.flight_plan = [s.run_start]
    elif s.phase is StrikePhase.EGRESS and not a.flight_plan:
        enter_patrol_hold(world, a, cfg)


def resolve_bomb_release(world, a: AircraftInstance, s: AirTask,
                         cfg: BalanceConfig = CONFIG) -> None:
    if world.phase != PHASE_COMBAT:
        return
    w = _weapon_of(a, "BOMB")
    if w is None:
        return
    rng = world.rng.air()
    r_major = bomb_scatter_major_cm(cfg, w.dispersion_cm, a.template.speed_cm_tick,
                                    a.alt_tier, has_dive=a.template.has_dive,
                                    cloud_tier=getattr(world, "cloud_tier", 0))
    r_minor = r_major * cfg.bomb_ellipse_ratio_bp // 10000
    k = dir_index(s.run_end[0] - s.run_start[0], s.run_end[1] - s.run_start[1])
    # 按用计费（2026-10-14 空袭按用计费块——呼叫价已剔除 BOMB，见 cmd_air_call）
    player = world.players[a.player_index]
    price = a.template.payload_price.get("BOMB", 0)
    for _i in range(w.salvo):
        if a.ammo_left.get("BOMB", 0) <= 0:
            break
        mj, mn = rng.sym(r_major), rng.sym(r_minor)
        d1, d2 = scale(DIR8[k], mj), scale(PERP8[k], mn)
        aim = (s.target[0] + d1[0] + d2[0], s.target[1] + d1[1] + d2[1])
        world.projectiles.append(AirProjectile(
            shooter=air_shooter_view(a), weapon=w, damage_type=DamageType.HE,
            damage=w.damage, blast_cm=w.blast_radius_cm, pos=a.pos, dest=aim,
            speed_cm_tick=w.projectile_speed_cm_tick, trajectory=Trajectory.BALLISTIC,
            hit_target=None, will_hit=False))
        a.ammo_left["BOMB"] -= 1                                       # GAP-15：每发递减
        player.air_points = max(0, player.air_points - price)          # 弹费按发扣


def resolve_strafe(world, a: AircraftInstance, s: AirTask,
                   cfg: BalanceConfig = CONFIG) -> None:
    """§F3 扫射结算。〔P1 机制块 2026-10-13 取严修正：manual.txt:413-416「guns and
    rockets are fired **indiscriminately along the entire length** of the selected
    strafing lane」——落点=沿全航道均匀取样（rng.below 全长），不再是「走廊内敌
    元素逐目标 salvo」；取样点近旁（走廊半宽内）有敌元素则按精度掷 HIT 命中最近
    一名（resolve_hit 契约⑥ TOP 支），否则该发落空仅面压制（无差别扫射打地面）。
    敌元素自然加权（落点密集处才打得着）而非显式选靶。我方单位不误伤——引擎级
    「无友军伤害」既有口径沿用（断箭扫射同样不打友军，留痕）。导弹打航道周边
    特定目标：1944 现役航空卡无导弹档（weapon_slot 仅 STRAFE/BOMB）——manual_silent
    留痕，弹型位待数据章节。低阻/高阻弹高度配对：卡面无弹型区分，由既有
    bomb_scatter_alt_bp 高度乘区承载（低空更准）——manual_silent 留痕。〕"""
    if world.phase != PHASE_COMBAT:
        return
    w = _weapon_of(a, "STRAFE")
    if w is None:
        return
    rng = world.rng.air()
    from .combat import inject_suppression_area, resolve_hit
    run_len = dist_cm(s.run_start, s.run_end)
    acc = strafe_acc_bp(cfg, w.accuracy_base_bp, a.alt_tier)
    for _i in range(w.salvo):
        if a.ammo_left.get("STRAFE", 0) <= 0:
            break
        t = rng.below(run_len + 1) if run_len > 0 else 0
        pt = _lerp_int(s.run_start, s.run_end, t, run_len)
        # 落点近旁最近敌元素（走廊半宽内——无差别落点+几何命中面）
        tgt, tgt_d = None, None
        for u in list(world.units):
            if u.team == a.team or not u.alive:
                continue
            for x in list(u.elements):
                if x.mounted_in is not None:
                    continue
                d = dist_cm(x.pos, pt)
                if d <= cfg.strafe_corridor_half_cm and (tgt_d is None or d < tgt_d):
                    tgt, tgt_d = x, d
        if tgt is not None and rng.chance_bp(acc):
            resolve_hit(world, AirProjectile(
                shooter=air_shooter_view(a), weapon=w,
                damage_type=w.damage_type, damage=w.damage,
                blast_cm=w.blast_radius_cm, pos=a.pos, dest=tgt.pos,
                speed_cm_tick=w.projectile_speed_cm_tick,
                trajectory=Trajectory.DIRECT, hit_target=tgt,
                will_hit=True, top_attack=True), cfg)
        else:
            j = (rng.sym(cfg.strafe_suppress_jitter_cm),
                 rng.sym(cfg.strafe_suppress_jitter_cm))           # AMB-01
            inject_suppression_area(world, (pt[0] + j[0], pt[1] + j[1]),
                                    cfg.strafe_suppression_radius_cm,
                                    w.suppression_power)
        a.ammo_left["STRAFE"] -= 1


def _lerp_int(a: tuple[int, int], b: tuple[int, int], d: int, total: int
              ) -> tuple[int, int]:
    """沿线段 a→b 行进 d 的整型插值点（total=线长；d≥total → b）。"""
    if total <= 0 or d >= total:
        return b
    return (a[0] + (b[0] - a[0]) * d // total,
            a[1] + (b[1] - a[1]) * d // total)


def dump_bombs(world, a: AircraftInstance, cfg: BalanceConfig = CONFIG) -> None:
    """§F3 转对空丢弹（D015：自由落体砸落点敌我双方；AMB2-08 crit=0 由数据侧保证）。"""
    if world.phase != PHASE_COMBAT:
        return
    if a.ammo_left.get("BOMB", 0) <= 0:
        return
    w = _weapon_of(a, "BOMB")
    if w is None:
        return
    rng = world.rng.air()
    k = a.facing // 45
    cloud = getattr(world, "cloud_tier", 0)
    for _i in range(a.ammo_left["BOMB"]):
        r_major = bomb_scatter_major_cm(cfg, w.dispersion_cm, a.template.speed_cm_tick,
                                        a.alt_tier, dump=True, cloud_tier=cloud)
        mj, mn = rng.sym(r_major), rng.sym(r_major * cfg.bomb_ellipse_ratio_bp // 10000)
        d1, d2 = scale(DIR8[k], mj), scale(PERP8[k], mn)
        aim = (a.pos[0] + d1[0] + d2[0], a.pos[1] + d1[1] + d2[1])
        world.projectiles.append(AirProjectile(
            shooter=air_shooter_view(a), weapon=w, damage_type=DamageType.HE,
            damage=w.damage, blast_cm=w.blast_radius_cm, pos=a.pos, dest=aim,
            speed_cm_tick=w.projectile_speed_cm_tick, trajectory=Trajectory.BALLISTIC,
            hit_target=None, will_hit=False))
    a.ammo_left["BOMB"] = 0


# ── §F4 自动缠斗 ──

def dogfight_check(world, cfg: BalanceConfig = CONFIG) -> None:
    if world.phase != PHASE_COMBAT:
        return
    for a in list(world.aircraft):
        if a.state in (AirState.DOGFIGHT, AirState.RTB) or world.tick < a.no_engage_until:
            continue
        if a.template.role is AirRole.FIGHTER or \
                (a.template.role is AirRole.ATTACK and a.engage_air):
            for b in list(world.aircraft):
                if b.team == a.team or b.state in (AirState.RTB, AirState.DOGFIGHT):
                    continue                                           # GAP-09：一对一成对
                if world.tick < b.no_engage_until:
                    continue
                if dist_cm(a.pos, b.pos) <= cfg.dogfight_engage_cm \
                        and b.alt_tier <= a.template.alt_ceiling \
                        and a.alt_tier <= b.template.alt_ceiling:
                    enter_dogfight(world, a, b, cfg)
                    break


def enter_dogfight(world, a: AircraftInstance, b: AircraftInstance,
                   cfg: BalanceConfig = CONFIG) -> None:
    a.task = None
    b.task = None
    for x in (a, b):
        x.state = AirState.DOGFIGHT
        x.patrol_loop = False
        x.flight_plan = []
        x.dogfight = DogfightState(opponent=(b if x is a else a),
                                   round_timer=cfg.dogfight_interval_ticks, rounds=0)


def dogfight_step(world, a: AircraftInstance, cfg: BalanceConfig = CONFIG) -> None:
    if world.phase != PHASE_COMBAT:
        return
    d = a.dogfight
    if d is None:
        return
    b = d.opponent                                                    # GAP-14：绑定
    if b not in world.aircraft or b.state is not AirState.DOGFIGHT \
            or b.dogfight is None or b.dogfight.opponent is not a:
        exit_dogfight(world, a, "OPPONENT_GONE")                      # GAP-08/16 守卫三条件
        return
    d.round_timer -= 1
    if d.round_timer > 0:
        return
    d.round_timer = cfg.dogfight_interval_ticks
    d.rounds += 1
    for atk, dfn in ((a, b), (b, a)):
        p = dogfight_kill_prob_bp(cfg, atk.template.dogfight_power,
                                  dfn.template.dogfight_power, dfn.template.maneuver)
        if world.rng.air().chance_bp(p):
            air_downed(world, dfn, cfg)
            return
    for gunner, target in ((a, b), (b, a)):
        if gunner.template.turret_damage > 0 and world.rng.air().chance_bp(cfg.self_defense_prob_bp):
            target.hp_current -= gunner.template.turret_damage
            if target.hp_current <= 0:
                air_downed(world, target, cfg)
                return
    if d.rounds >= cfg.dogfight_rounds_max:                           # B-07
        exit_dogfight(world, a, "TIME_LIMIT")
        if b in world.aircraft and b.state is AirState.DOGFIGHT:
            exit_dogfight(world, b, "TIME_LIMIT")


def cmd_air_disengage(world, a: AircraftInstance, cfg: BalanceConfig = CONFIG) -> bool:
    if a.state is not AirState.DOGFIGHT or world.phase != PHASE_COMBAT:
        return False
    b = a.dogfight.opponent
    tail_p = tail_prob_bp(cfg, b.template.dogfight_power, a.template.maneuver)
    if world.rng.air().chance_bp(tail_p):
        air_downed(world, a, cfg)                                     # 被追尾击落
        return True
    exit_dogfight(world, a, "VOLUNTARY")
    if b in world.aircraft and b.state is AirState.DOGFIGHT \
            and b.dogfight is not None and b.dogfight.opponent is a:
        exit_dogfight(world, b, "OPPONENT_LEFT")                      # GAP-08：对手同拍解缠
    return True


def exit_dogfight(world, x: AircraftInstance, _reason: str,
                  cfg: BalanceConfig = CONFIG) -> None:
    x.dogfight = None
    x.no_engage_until = world.tick + cfg.dogfight_reengage_immunity_ticks
    enter_patrol_hold(world, x, cfg)


def cmd_air_engage_air(world, a: AircraftInstance, engage: bool) -> bool:
    if engage and not a.template.can_engage_air and a.template.role is not AirRole.FIGHTER:
        return False                                                  # B-21
    if a.state is AirState.RTB:
        return False                                                  # AMB2-05
    if engage and world.phase != PHASE_COMBAT:
        return False                                                  # GAP2-08：开拨须实战
    if engage and a.ammo_left.get("BOMB", 0) > 0:
        dump_bombs(world, a)                                          # D015 转对空丢弹
    if a.engage_air is not None:
        a.engage_air = engage
    return True


# ── §F5 侦察标记（独立挂点：world_tick ③sensing 与 ④交战 之间——GAP2-01）──

def air_recon_step(world, cfg: BalanceConfig = CONFIG) -> None:
    """独立挂点（world_tick ③sensing 与 ④交战 之间——GAP2-01）。
    B-30①（AMB3-04）：相位门=结算门（非结算期照常标记——与地面 sensing 同门）。"""
    if world.phase == PHASE_SETTLE:
        return
    if world.tick % cfg.air_recon_period_ticks != 0:
        return
    from .types import MarkLevel
    for a in world.aircraft:
        if a.template.role is not AirRole.RECON or a.state in (AirState.RTB, AirState.DOGFIGHT):
            continue                                                  # B-27①
        cloud = getattr(world, "cloud_tier", 0)
        radius = recon_radius_cm(cfg, a.template.optics_air_cm, a.alt_tier, cloud)
        mark_p = recon_mark_prob_bp(cfg, a.template.recon_mark_base_bp,
                                    a.alt_tier, a.template.speed_cm_tick, cloud)
        rng = world.rng.air()
        for u in world.units:
            if u.team == a.team or not u.alive:
                continue
            if dist_cm(a.pos, u.pos) <= radius and rng.chance_bp(mark_p):
                u.spotted_mask |= 1 << a.team
                if u.mark_level < MarkLevel.SPOTTED:
                    u.mark_level = MarkLevel.SPOTTED                  # B-15：SPOTTED 档


# ── §F6 空投链 ──

def _airdrop_scatter_now(world, a: AircraftInstance, s: AirTask,
                         cfg: BalanceConfig) -> int:
    """当次散布幅度（高度×速度×信标吸附——resolve_airdrop 既有口径抽取）。"""
    r = airdrop_scatter_cm(cfg, a.alt_tier, a.template.speed_cm_tick)
    beacon = nearest_friendly_beacon(world.beacon_by_unit, a.team, s.drop, cfg)
    if beacon is not None:
        r = r * airdrop_beacon_mult(cfg) // 10000                     # 契约⑤ ×0.5
    return r


def resolve_airdrop(world, a: AircraftInstance, s: AirTask,
                    cfg: BalanceConfig = CONFIG, point=None) -> None:
    """投放**一份**（P1「逐一跳伞」——manual.txt:432-433「jump out one by one」）：
    空降分支=投一个舱内卡单位（point=stick 点，缺省 s.drop——测试直调兼容面），
    投放作业费 B-30② 每任务收一次（首 stick 拍——多份装载不重复计费，manual_silent）；
    补给分支=整舱一箱（「one by one」主要语义=人员，补给单投留痕 manual_silent——
    Li-2 载荷量级单箱即全舱）。舱空判定由调用侧（airdrop_run_step/strike_step）。"""
    if world.phase != PHASE_COMBAT:
        return
    rng = world.rng.air()
    r = _airdrop_scatter_now(world, a, s, cfg)
    at = s.drop if point is None else point
    if a.paratroop_cargo is not None and a.paratroop_left <= 0:
        a.paratroop_left = 1        # 份数账缺省归一（直构实例只挂 cargo 未置份数=
                                    # 单份旧语义——cmd_air_call 路径恒显式置数）
    if a.paratroop_cargo is not None and a.paratroop_left > 0:        # D017：落地即地面一命单位
        tpl = a.paratroop_cargo
        land = (at[0] + rng.sym(r), at[1] + rng.sym(r))
        world.spawn_paratroop(tpl, a.team, a.player_index, land)      # 地面管线回调（边界登记）
        a.paratroop_left -= 1
        if a.paratroop_left <= 0:
            a.paratroop_cargo = None
        if s.sticks_done == 0:
            p = world.players[a.player_index]
            p.air_points = max(0, p.air_points - cfg.airdrop_fee_points)  # B-30② 下限钳（AMB3-07）
        s.sticks_done += 1
    else:                                                             # R-21：落地实体补给箱
        supply_left = a.ammo_left.get("SUPPLY", 0)
        if supply_left <= 0:
            return
        land = (at[0] + rng.sym(r), at[1] + rng.sym(r))
        world.spawn_airdrop_crate(a.team, land, supply_left)          # 契约④：地面冻结接口
        a.ammo_left["SUPPLY"] = 0


def airdrop_run_step(world, a: AircraftInstance, s: AirTask,
                     cfg: BalanceConfig = CONFIG) -> None:
    """RUN 段逐 stick 投放（P1 逐一跳伞节拍，2026-10-13）：stick 点=drop 点沿 run
    轴向两侧对称排开（间隔=速度×5≈0.5s 航程——manual 无节拍数值，manual_silent）；
    飞机航向进度越过某 stick 阈值即投一份（几何过点触发，确定性零节拍计数器）。
    补给箱在飞机抵达 drop 点（旧触发口径）时整舱投放。"""
    if world.phase != PHASE_COMBAT:
        return
    if a.paratroop_cargo is not None and a.paratroop_left <= 0:
        a.paratroop_left = 1            # 份数账缺省归一（resolve_airdrop 同款）
    if a.paratroop_cargo is not None and a.paratroop_left > 0:
        n_total = s.sticks_done + a.paratroop_left
        k = dir_index(s.run_end[0] - s.run_start[0], s.run_end[1] - s.run_start[1])
        d = DIR8[k]
        spacing = max(1, a.template.speed_cm_tick * 5)
        prog = ((a.pos[0] - s.run_start[0]) * d[0]
                + (a.pos[1] - s.run_start[1]) * d[1])                 # 轴向进度（同基不含模长）
        while s.sticks_done < n_total and a.paratroop_left > 0:
            i = s.sticks_done
            off = (2 * i - (n_total - 1)) * spacing // 2              # 对称分布
            pt = (s.drop[0] + d[0] * off // DIR_NORM,
                  s.drop[1] + d[1] * off // DIR_NORM)
            thr = ((pt[0] - s.run_start[0]) * d[0]
                   + (pt[1] - s.run_start[1]) * d[1])
            if prog >= thr:
                resolve_airdrop(world, a, s, cfg, point=pt)
            else:
                break
    if a.ammo_left.get("SUPPLY", 0) > 0 \
            and dist_cm(a.pos, s.drop) <= max(1, a.template.speed_cm_tick):
        resolve_airdrop(world, a, s, cfg)                             # 补给箱：抵达 drop 点整舱投


# ── §F7 击落结算与主循环 ──

def air_check_downed(world, cfg: BalanceConfig = CONFIG) -> None:
    for a in list(world.aircraft):
        if a.hp_current <= 0:
            air_downed(world, a, cfg)


def aircraft_tick(world, cfg: BalanceConfig = CONFIG) -> None:
    """world_tick 航空段（挂 ④交战之后、⑤弹丸之前；recon 独立挂点在 ③④ 之间——GAP2-01）。"""
    if world.phase == PHASE_SETTLE:
        return
    for a in list(world.aircraft):
        start = a.pos
        aircraft_move_step(world, a, cfg)
        _set_facing(a, start)
    dogfight_check(world, cfg)
    for a in list(world.aircraft):
        d = a.dogfight
        if d is not None and (d.opponent not in world.aircraft or a.id < d.opponent.id):
            dogfight_step(world, a, cfg)
    air_check_downed(world, cfg)
    for a in list(world.aircraft):                                    # ⑥ 弹尽自动 RTB（GAP2-05/11/GAP3-02）
        if a.state in (AirState.INBOUND, AirState.PATROL) \
                and (a.template.weapons or a.template.payload_max_supply > 0
                     or a.template.paratroop_seats > 0) \
                and all(v <= 0 for v in a.ammo_left.values()) \
                and a.paratroop_cargo is None:
            # GAP3-02（v1.3）：资格门=有可投送载荷资格（weapons/补给舱/空降舱三析取）——
            # 运输机投送完毕恢复自动 RTB（B-05/D001），侦察机（三者皆无）豁免维持。
            cmd_air_rtb(world, a)
        elif (a.auto_drop_tick > 0 and world.tick >= a.auto_drop_tick
              and a.state is AirState.PATROL and a.task is not None
              and a.task.kind is TaskKind.PATROL and world.phase == PHASE_COMBAT
              and (a.paratroop_cargo is not None
                   or a.ammo_left.get("SUPPLY", 0) > 0)):
            # P1 无令货机自动空投（manual.txt:434-440：到场延迟窗内无其他命令→
            # 在呼叫点自动投放；投毕由上方弹尽自动 RTB 接管回基地）。投放点=当前
            # 盘旋位（呼叫到场点）。排程一次性（清零防重排）。
            a.auto_drop_tick = 0
            cmd_air_airdrop(world, a, a.pos, cfg)


# ── P1 机制块（2026-10-13，GP-01 断箭手册 P1 补建）──
# Afterburner（manual.txt:492-497）／Decoy（manual.txt:505-509、basics:347-352）／
# 导弹来袭统一事件口 missile_warning（Smoke/Decoy 自动触发的共同事件源）。

def cmd_air_afterburner(world, a: AircraftInstance, engage: bool,
                        cfg: BalanceConfig = CONFIG) -> bool:
    """Z 加力开关（toggle——再按 Z 关闭，manual.txt:496-497「Press Z again to turn
    it off」）。门：模板无加力资格（can_afterburner=False）→REJECT；DOGFIGHT/RTB
    态 →REJECT（失控段不可微操——B-22 同口径）；燃油耗尽 →REJECT。速度/油耗 ×2
    消费点=aircraft_move_step。"""
    if not a.template.can_afterburner:
        return False
    if a.state in (AirState.DOGFIGHT, AirState.RTB):
        return False
    if engage and a.fuel_ticks <= 0:
        return False
    a.afterburner = bool(engage)
    return True


def cmd_air_decoy(world, a: AircraftInstance, action: str,
                  cfg: BalanceConfig = CONFIG) -> bool:
    """C 诱饵令（manual.txt:508「Press C to fire a decoy manually」＋basics:351-352
    右键切自动档）。action ∈ {"POP","AUTO_ON","AUTO_OFF"}：POP=立即投放一发（发数
    门），规避窗 evade_until=now+cfg.decoy_evade_ticks——fire_aa acc 乘区消费；
    AUTO_ON/OFF=自动模式开关（「被导弹攻击自动触发」的资格位）。"""
    if a.template.decoy_charges <= 0:
        return False                                  # 机型无诱饵槽（数据位）
    if action in ("AUTO_ON", "AUTO_OFF"):
        a.decoy_auto = action == "AUTO_ON"
        return True
    if action != "POP":
        return False
    if a.decoy_left <= 0:
        return False
    a.decoy_left -= 1
    a.evade_until = world.tick + cfg.decoy_evade_ticks
    return True


def missile_warning(world, target) -> None:
    """「导弹来袭」统一事件口（P1——Smoke/Decoy 自动触发的共同事件源）。

    断箭原文：Smoke「Triggers automatically if a missile is fired on the unit」
    （manual.txt:501-502）/ Decoy「Triggers automatically if a missile is fired on
    the unit」（manual.txt:507-508）。本作 1944 题材的「导弹」对应物=对空高炮弹
    （唯一制导样武器的时代表亲）——**唯一生产调用点=tick.fire_aa（对空弹发射拍，
    target=被瞄准飞机）**：飞机诱饵自动投放（decoy_auto 且有发）。
    地面支：函数体承载（任一元素有自卫烟幕发数且过冷却→cmd_smoke 自动落烟），
    但 1944 现役武器面**无对地导弹**（无 ATGM/SEAD 弹种）→事件源不可达、无生产
    调用点——接线留痕（manual_silent）：将来出现对地导弹武器时在其发射点调本函数
    即激活；X 手动路径不变。"""
    from .tick import cmd_smoke
    if isinstance(target, AircraftInstance):
        if target.decoy_auto and target.decoy_left > 0:
            cmd_air_decoy(world, target, "POP")
        return
    unit = getattr(target, "unit", target)                 # 元素或单位均可
    if getattr(unit, "alive", False):
        for e in unit.elements:
            if e.self_smoke_left > 0:
                cmd_smoke(world, e, e.pos)
                return
