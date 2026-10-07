"""DATA-01 地面数据卡 schema（构建期 pydantic v2 校验层——冻结于 docs/DATA-01-地面数据卡schema冻结-v1.md）。

三层模型：WeaponRowModel（武器行 29 字段）→ ElementModel（元素 17 字段）→ UnitCardModel
（单卡 39 字段——33＋PB-52 三可选字段＋PB-55 三士气阈值可选字段 2026-10-04；元素级 PB-53 +1 字段同日）；外加 DeckModel（卡组）与 CardLibraryModel（全库 JSON 根）。
字段清单、单位、取值域、默认分级与冻结文档 §4 逐字段一一对应；本文档为唯一权威，
改字段先改文档（演进规则见 §2：只向后兼容——加可选字段＝minor，改语义/单位/删字段＝major）。

单位约定（硬约束：数值一律严格 int，float 必须被拒——StrictInt 实测拒 1.0/1.5/str/bool）：
  cm＝坐标/距离厘米；tick＝10Hz 时长；bp＝万分比（0..10000）；permille＝千分比；
  档/刻度＝无量纲整数；tow_tonnage/own_weight_tons＝0.1t 刻度×10 整型（DATA-01 §7）。

枚举表示（DATA-01 §2.4 唯一口径）：CSV/录入层一律 str 令牌（SOVIET/KE/HOWITZER…——
Literal[str] 令牌集，float 天然被拒）；JSON 一律落 int 值——令牌→int 的单点映射表
TOKEN_VALUE（值取自 types.py IntEnum/IntFlag，不重复手写数值），构建期序列化与
card_loader 构造冻结 dataclass 时共用该表反查。

来源分级：每字段经 Field(json_schema_extra={"grade": ..., "src": ...}) 声明默认分级与出处
（air_data.py:7-17 六级：〔GDD〕〔数锚〕〔冻结〕〔拍板〕〔锚点〕〔待定〕）；值级偏离与
待定登记走 sidecar（DATA-01 §6）。

版本门（DATA-01 §2.2）：SCHEMA_VERSION＝"1.3"（major.minor；1.0→1.1＝2026-10-04
PB-52 单位级地形数值块加三可选字段、1.1→1.2＝2026-10-04 PB-53 自卫烟幕块加元素级
可选字段 self_smoke_charges、1.2→1.3＝2026-10-04 PB-55 士气效果接线块加卡级三可选
字段 morale_{sup,pin,rout}_th——均 §2.3-1 加可选字段＝minor）；
SUPPORTED_CARD_SCHEMA＝{1: 3}——键＝major、值＝接受的 minor 上界；
schema_version_supported() 供 CardLibraryModel/DeckModel 校验器与加载器复用。

⚠️ 阈值常量归口偏离登记（DATA-01 §12）：施工方案（out/card-schema-plan.md §C.2，v1.1）
钉死 D011 类别配额/火支子配额阈值唯一权威＝tables.py BalanceConfig
（category_quota/fire_support_subquota 两字段行——IMPL-地面 §D.0 :82-83 既有定义的
落地欠账）；本轮施工约束「不改任何现有文件」，tables.py 该两字段尚未落地，故下方
PER_CARD_LIMIT_BY_CATEGORY/CATEGORY_QUOTA/FIRE_SUPPORT_SUBQUOTA 暂居本模块并已注释
登记——tables.py 落地后必须迁移归口（本模块改 import）并同步修订冻结文档 §8/§12，
在迁移完成前本模块为唯一权威、禁止在 card_loader 侧再抄一份（无双轨）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from .types import (AltTier, AuraKind, DamageType, ElementType, Mode,
                    MovementClass, TargetDomain, Trajectory, UnitFlag, UnitType)

# ── 版本门（DATA-01 §2）──
SCHEMA_VERSION: str = "1.3"
#: 结构化支持表：键＝major、值＝接受的 minor 上界（加载器 fail-fast 拒绝一切表外版本）
SUPPORTED_CARD_SCHEMA: dict[int, int] = {1: 3}


def schema_version_supported(version: str) -> bool:
    """版本门判定：major 必须在支持表内且 minor ≤ 该 major 的上界（DATA-01 §2.2）。"""
    try:
        major_s, _, minor_s = version.partition(".")
        major, minor = int(major_s), int(minor_s)
    except ValueError:
        return False
    return major in SUPPORTED_CARD_SCHEMA and minor <= SUPPORTED_CARD_SCHEMA[major]


# ── 令牌集（str Literal）与令牌→types.py IntEnum/IntFlag int 值映射（JSON int 表示单点）──

FactionTok = Literal["SOVIET", "GERMAN"]
CategoryTok = Literal["RECON", "INFANTRY", "ARMOR", "FIRE_SUPPORT", "AA_LOGISTICS"]
PoolTok = Literal["MAIN", "RESERVE"]
QuotaGroupTok = Literal["NONE", "HOWITZER", "AT_GUN", "ROCKET"]
DeliveryTok = Literal["NONE", "LI2", "JU52"]
AirCeilingTok = Literal["NONE", "LOW", "MID", "HIGH"]
MovementClassTok = Literal["FOOT", "WHEEL", "TRACK", "HORSE"]
ElementTypeTok = Literal["VEHICLE", "GUN", "SQUAD"]
UnitTypeTok = Literal["INFANTRY", "MECH"]
DamageTypeTok = Literal["KE", "HE", "SMOKE"]
TrajectoryTok = Literal["DIRECT", "BALLISTIC"]
CombatStyleTok = Literal["NORMAL", "MELEE", "SNIPER"]
AuraKindTok = Literal["MELEE", "PRECISION"]
TargetDomainTok = Literal["GROUND", "AIR_LOW", "AIR_MID", "AIR_HIGH"]
ModeTok = Literal["DIRECT", "INDIRECT", "TOW", "CARGO", "TRANSPORT"]
UnitFlagTok = Literal[
    "CAN_SPRINT", "CAN_GARRISON", "CAN_AMBUSH", "CAN_INFILTRATE",
    "NO_MOVE_VISION_PENALTY", "FOREST_WALK_SILENT", "REQUIRES_MARK",
    "SINGLE_SQUAD_CARD", "CAN_SNIPER_COVER", "CAN_AIRDROP_BEACON",
    "HAS_CARGO", "HAS_MOUNT", "HAS_SUPPLY", "SUPP_DECAY_X2",
]  # types.py UnitFlag 14 令牌（:121-136）全量

TOKEN_VALUE: dict[str, dict[str, int]] = {
    # faction 无 types 枚举（卡记录层）——0/1 为管线自编（D004 阵营）
    "faction": {"SOVIET": 0, "GERMAN": 1},
    # category：0 侦察/1 步兵/2 装甲/3 火支/4 防空后勤（types.py:227 注释＝冻结口径）
    "category": {"RECON": 0, "INFANTRY": 1, "ARMOR": 2, "FIRE_SUPPORT": 3, "AA_LOGISTICS": 4},
    "pool": {"MAIN": 0, "RESERVE": 1},
    "quota_group": {"NONE": 0, "HOWITZER": 1, "AT_GUN": 2, "ROCKET": 3},
    "delivery": {"NONE": 0, "LI2": 1, "JU52": 2},
    "air_ceiling": {"NONE": -1, "LOW": int(AltTier.LOW), "MID": int(AltTier.MID),
                    "HIGH": int(AltTier.HIGH)},  # NONE=-1→loader 转 types 的 None（不可及）
    "movement_class": {t.name: int(t) for t in MovementClass},
    "element_type": {t.name: int(t) for t in ElementType},
    "unit_type": {t.name: int(t) for t in UnitType},
    "damage_type": {t.name: int(t) for t in DamageType},
    "trajectory": {t.name: int(t) for t in Trajectory},
    "combat_style": {"NORMAL": 0, "MELEE": 1, "SNIPER": 2},  # types.py:190 注释口径
    "aura_kind": {t.name: int(t) for t in AuraKind},
    "target_mask": {t.name: int(t) for t in TargetDomain
                    if t.name in ("GROUND", "AIR_LOW", "AIR_MID", "AIR_HIGH")},
    "mode_set": {t.name: int(t) for t in Mode},
    "flags": {t.name: int(t) for t in UnitFlag},
}

# ── deck 阈值常量（〔待定〕占位——归口偏离登记见模块 docstring 与 DATA-01 §12）──
#: D032 同型限份类别默认（GDD-00 :200；指挥班组=1 为卡级覆盖，不入类别表）
PER_CARD_LIMIT_BY_CATEGORY: dict[str, int] = {
    "ARMOR": 2, "INFANTRY": 3, "RECON": 2, "FIRE_SUPPORT": 2, "AA_LOGISTICS": 2,
}
#: D011 类别配额〔待定〕占位（GDD-01 §0.5 :19-27 草案；定标来源＝数值章节＋批量模拟器联调）
CATEGORY_QUOTA: dict[str, dict[str, int]] = {
    "RECON": {"MAIN": 4, "RESERVE": 2},
    "INFANTRY": {"MAIN": 9, "RESERVE": 5},
    "ARMOR": {"MAIN": 8, "RESERVE": 4},
    "FIRE_SUPPORT": {"MAIN": 6, "RESERVE": 3},
    "AA_LOGISTICS": {"MAIN": 5, "RESERVE": 2},
}
#: R-13 火支子配额（IMPL-地面 §D.0 :83 定义值；GDD-02 :201 拍板⑥——两池总和校验）
FIRE_SUPPORT_SUBQUOTA: dict[str, int] = {"HOWITZER": 3, "AT_GUN": 2, "ROCKET": 1}
#: D038 方案A占位点数上限（〔待定〕O-06——GDD-00 :372）
POINTS_MAIN_CAP: int = 4000
POINTS_RESERVE_CAP: int = 2000


# ── 武器行子模型 ──

class RestrictedProfileModel(BaseModel):
    """钨芯受限弹药档（§D.3#22 restricted_profiles 元素 {count, pen_bonus}）。"""
    model_config = ConfigDict(extra="forbid")
    count: StrictInt = Field(ge=1, description="受限档发数")  # 〔拍板〕㉖A 钨芯换算锚
    pen_bonus: StrictInt = Field(ge=0, description="穿深加成（0-20 刻度）")


class AltProfileModel(BaseModel):
    """§D.3#23 alt_profile：R-11 HE 档案 {damage, blast}（AP 主炮共槽）。"""
    model_config = ConfigDict(extra="forbid")
    damage: StrictInt = Field(ge=0)
    blast_radius_cm: StrictInt = Field(ge=0)


class SelfDefenseModel(BaseModel):
    """§D.3#25 self_defense：R-15 自卫档 {max_range_cm, accuracy_mult_bp}。"""
    model_config = ConfigDict(extra="forbid")
    max_range_cm: StrictInt = Field(gt=0)
    accuracy_mult_bp: StrictInt = Field(ge=0)


class WeaponRowModel(BaseModel):
    """武器行（DATA-01 §4.5，29 字段＝§D.3 27 模板字段＋2 管线键；CSV 一武器一行）。"""
    model_config = ConfigDict(extra="forbid")
    weapon_key: str = Field(min_length=1)                       # 管线键（元素内唯一）
    element_key: str = Field(min_length=1)                      # 管线外键→ElementModel.element_key
    name: str = Field(min_length=1)                             # 〔冻结〕D.3#1
    target_mask: list[TargetDomainTok] = Field(
        default=["GROUND"], min_length=1)                       # 〔冻结〕D.3#2（位或→int）
    damage_type: DamageTypeTok                                  # 〔冻结〕D.3#3
    pen_min: StrictInt = Field(default=0, ge=0, le=20)          # 〔数锚+拍板〕⑤A mm 换算（远距）
    pen_max: StrictInt = Field(default=0, ge=0, le=20)          # 同上（贴脸）；≥pen_min 校验
    damage: StrictInt = Field(default=0, ge=0)                  # 〔数锚〕GDD-03 通用武器表
    blast_radius_cm: StrictInt = Field(default=0, ge=0)         # 〔数锚〕GDD-03 §2.3 溅射带
    max_range_cm: StrictInt = Field(gt=0)                       # 〔数锚〕史实射程换算
    min_range_cm: StrictInt = Field(default=0, ge=0)            # 〔冻结〕D.3#9
    dispersion_cm: StrictInt = Field(default=0, ge=0)           # 〔冻结〕D.3#10（方形散布半径）
    accuracy_base_bp: StrictInt = Field(default=10000, ge=0, le=10000)  # 〔待定〕距离衰减/精度定标
    aim_time_ticks: StrictInt = Field(default=0, ge=0)          # 〔数锚〕Enlisted 锚（D067 :350）
    reload_time_ticks: StrictInt = Field(default=0, ge=0)       # 〔数锚〕同上
    salvo: StrictInt = Field(default=1, ge=1)                   # 〔数锚〕同上
    ammo_base: StrictInt = Field(default=0, ge=0)               # 〔数锚〕史实弹容
    ammo_weight: StrictInt = Field(default=0, ge=0)             # 〔待定〕supply_round_weight 定标
    projectile_speed_cm_tick: StrictInt = Field(default=0, ge=0)  # 〔数锚〕史实弹速换算
    trajectory: TrajectoryTok = "DIRECT"                        # 〔冻结〕D.3#18
    suppression_power: StrictInt = Field(default=0, ge=0)       # 〔数锚〕GDD-03 §2.3 压制带
    crit_mod_permille: StrictInt = Field(default=1000, ge=0)    # 〔冻结〕D.3#20
    vs_fort_mult_permille: StrictInt = Field(default=1000, ge=0)  # 〔冻结〕D.3#21（M5 硬要求）
    needs_deployed: StrictBool = False                          # 〔冻结〕D.3#24（R-05）
    combat_style: CombatStyleTok = "NORMAL"                     # 〔冻结〕D.3#26（方案1 档案化）
    reveal_time_ticks: StrictInt = Field(default=0, ge=0)       # 〔冻结〕D.3#27
    restricted_profiles: list[RestrictedProfileModel] = []      # 〔拍板〕㉖A
    alt_profile: AltProfileModel | None = None                  # 〔冻结〕D.3#23（R-11）
    self_defense: SelfDefenseModel | None = None                # 〔冻结〕D.3#25（R-15）

    @model_validator(mode="after")
    def _pen_and_range_order(self) -> "WeaponRowModel":
        if self.pen_max < self.pen_min:
            raise ValueError("pen_max 必须 ≥ pen_min（贴脸≥远距）")
        if self.min_range_cm > self.max_range_cm:
            raise ValueError("min_range_cm 必须 ≤ max_range_cm")
        return self


# ── 元素级 ──

class ArmorModel(BaseModel):
    """四面护甲（0-20 相对刻度，⑤A mm 换算锚；0=无甲合法——卡车）。"""
    model_config = ConfigDict(extra="forbid")
    front: StrictInt = Field(ge=0, le=20)
    side: StrictInt = Field(ge=0, le=20)
    rear: StrictInt = Field(ge=0, le=20)
    top: StrictInt = Field(ge=0, le=20)


class ElementModel(BaseModel):
    """元素组（DATA-01 §4.4，17 字段；CSV 一元素组一行，count 展开在 loader。
    16→17＝2026-10-04 PB-53 加可选字段 self_smoke_charges——DATA-01 §2.3-1 minor）。"""
    model_config = ConfigDict(extra="forbid")
    element_key: str = Field(min_length=1)                      # 管线键（卡内唯一）
    count: StrictInt = Field(ge=1)                              # 〔GDD〕D027 :169 编制数
    element_type: ElementTypeTok                                # 〔冻结〕D.2#1
    unit_type: UnitTypeTok                                      # 〔冻结〕D.2#2（GUN 按 M22 归类）
    hp_max: StrictInt = Field(gt=0)                             # 〔数锚〕GDD-03 §1.1（SQUAD=人数）
    armor_ke: ArmorModel | None = None                          # 〔数锚+拍板〕MECH 必填/INFANTRY null
    armor_he: ArmorModel | None = None                          # 同上
    fire_arc_deg: StrictInt = Field(default=360, ge=0, le=360)  # 〔冻结〕D.2#6（360 或 30）
    suppression_vuln_permille: StrictInt = Field(default=1000, ge=0)  # 〔冻结〕D.2#7
    squad_quality_bp: StrictInt = Field(default=10000, ge=0)    # 〔冻结〕D.2#8（替代老练度）
    weapons: list[WeaponRowModel] = []                          # 〔冻结〕D.2#9
    seats: StrictInt = Field(default=0, ge=0)                   # 〔冻结〕D.2#11
    mounted_armament: list[str] | None = None                   # 〔冻结〕D.2#10（AMB-07）
    cargo_rounds_max: StrictInt = Field(default=0, ge=0)        # 〔冻结〕D.2#12（D065）
    cargo_medical_max: StrictInt = Field(default=0, ge=0)       # 〔冻结〕D.2#13
    cargo_weight_max: StrictInt = Field(default=0, ge=0)        # 〔冻结〕D.2#14（D012）
    self_smoke_charges: StrictInt = Field(default=0, ge=0)      # 〔拍板〕PB-53 自卫烟幕发数
                                                                # （0=无能力——哪些车配属归数据卡
                                                                # 配置侧；冷却/延迟/半径/时长=
                                                                # tables.py 烟雾段，非本表字段）

    @field_validator("fire_arc_deg")
    @classmethod
    def _arc_whitelist(cls, v: int) -> int:
        if v not in (360, 30):  # 全向 / ±15°（R-09）
            raise ValueError("fire_arc_deg 仅允许 360 或 30（R-09 射界）")
        return v

    @model_validator(mode="after")
    def _armor_and_mounts(self) -> "ElementModel":
        if self.unit_type == "MECH":
            if self.armor_ke is None or self.armor_he is None:
                raise ValueError("MECH 元素必须给 armor_ke/armor_he（HARD 目标）")
        else:  # INFANTRY（含炮班/骑兵等一切 SOFT 目标）
            if self.armor_ke is not None or self.armor_he is not None:
                raise ValueError("INFANTRY 元素 armor_ke/armor_he 必须为 null（SOFT 为 None）")
        keys = [w.weapon_key for w in self.weapons]
        if len(keys) != len(set(keys)):
            raise ValueError("weapons 内 weapon_key 必须元素内唯一")
        for w in self.weapons:
            if w.element_key != self.element_key:
                raise ValueError(f"武器行 {w.weapon_key!r} 的 element_key 与所属元素不一致")
        if self.mounted_armament is not None:
            known = set(keys)
            for key in self.mounted_armament:
                if key not in known:  # AMB-07：车载 MG 须同时配入 weapons[]
                    raise ValueError(f"mounted_armament 引用 {key!r} 不在本元素 weapons 内")
        return self


# ── 卡级 ──

class AuraModel(BaseModel):
    """§D.1#24 aura：政委 MELEE/军官 PRECISION 光环（查询期消费）。"""
    model_config = ConfigDict(extra="forbid")
    kind: AuraKindTok
    bonus_bp: StrictInt = Field(ge=0)
    radius_cm: StrictInt = Field(ge=0)


class UnitCardModel(BaseModel):
    """单卡（DATA-01 §4.3，39 字段；CSV 一卡一行。36→39＝2026-10-04 PB-55 加三士气阈值可选字段）。"""
    model_config = ConfigDict(extra="forbid")
    card_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")         # 管线主键（全库唯一）
    template_id: StrictInt = Field(gt=0)                        # 苏 101~/德 201~（O-11）
    name: str = Field(min_length=1)                             # 〔GDD〕GDD-01 卡名
    faction: FactionTok                                         # 〔GDD〕D004
    category: CategoryTok                                       # 〔GDD〕D028
    cost: StrictInt = Field(gt=0)                               # 〔GDD〕GDD-01 卡面价（D038 基准=100）
    pool: PoolTok                                               # 〔GDD〕D001
    per_card_limit: StrictInt | None = Field(default=None, ge=1)  # None=按类别默认（D032）
    quota_group: QuotaGroupTok = "NONE"                         # 〔GDD〕D028/GDD-02 :201
    unlock_by: str = ""                                         # 〔GDD〕D.1#29（空=通用）
    delivery: DeliveryTok = "NONE"                              # 〔GDD〕P-13 空降投送限定
    optics_ground_cm: StrictInt = Field(gt=0)                   # 〔冻结〕D.1#6
    optics_air_cm: StrictInt = Field(default=0, ge=0)           # 〔冻结〕D.1#7（0=无）
    air_ceiling: AirCeilingTok = "NONE"                         # 〔冻结〕D.1#8
    stealth_base: StrictInt = Field(ge=0, le=10)                # 〔冻结〕D.1#9
    speed_tier: StrictInt = Field(ge=1, le=5)                   # 〔冻结〕D.1#10
    movement_class: MovementClassTok                            # 〔冻结〕D.1#11
    turn_rate_deg: StrictInt = Field(default=1, ge=1)           # 〔冻结〕D.1#12（R-09）
    terrain_speed_override_bp: StrictInt = Field(default=0, ge=0, le=10000)  # 〔拍板〕PB-52 单位级越野 bp（0=回退类级）
    reverse_speed_override_bp: StrictInt = Field(default=0, ge=0, le=10000)  # 〔拍板〕PB-52 单位级倒车 bp（0=回退类级）
    road_bonus_override_cm: StrictInt = Field(default=0, ge=0)  # 〔拍板〕PB-52 单位级道路下限 cm/tick（0=回退类级常数）
    morale_sup_th: StrictInt = Field(default=0, ge=0)   # 〔拍板〕PB-55 卡级受压阈值（0=回退 cfg.morale_sup_th）
    morale_pin_th: StrictInt = Field(default=0, ge=0)   # 〔拍板〕PB-55 卡级钉住阈值（0=回退 cfg.morale_pin_th）
    morale_rout_th: StrictInt = Field(default=0, ge=0)  # 〔拍板〕PB-55 卡级溃逃阈值（0=回退 cfg.morale_rout_th；>100=永不溃逃差异化位）
    deploy_time_ticks: StrictInt = Field(default=0, ge=0)       # 〔GDD〕D027/D031
    pack_time_ticks: StrictInt = Field(default=0, ge=0)         # 〔GDD〕同上
    flags: list[UnitFlagTok] = []                               # 〔冻结〕D.1#25（位或→int）
    mode_set: list[ModeTok] = Field(default=["DIRECT"])         # 〔冻结〕D.1#15
    supply_radius_cm: StrictInt = Field(default=8000, ge=0)     # 〔冻结〕D.1#20（R-18）
    sonar_radius_cm: StrictInt = Field(default=0, ge=0)         # 〔冻结〕D.1#22（R-03）
    sonar_rate: StrictInt = Field(default=0, ge=0)              # 〔冻结〕D.1#23
    acoustic_signature: StrictInt = Field(default=1, ge=1)      # 〔冻结〕D.1#21
    tow_tonnage: StrictInt = Field(default=0, ge=0)             # 〔数锚+拍板〕0.1t 刻度（DATA-01 §7）
    own_weight_tons: StrictInt = Field(default=0, ge=0)         # 同上（被拖侧进一取整）
    repair_power_hp_per_tick: StrictInt = Field(default=0, ge=0)  # 〔冻结〕D.1#19（D016）
    close_combat_bonus_permille: StrictInt = Field(default=1000, ge=100)  # 〔冻结〕D.1#16
    size_factor_bp: StrictInt = Field(default=10000, ge=1)      # 〔D027 遗留〕G-1 不映射
    aura: AuraModel | None = None                               # 〔冻结〕D.1#24（仅步兵指挥卡）
    elements: list[ElementModel] = Field(min_length=1)          # 〔GDD〕D006/D009

    @field_validator("flags", "mode_set")
    @classmethod
    def _no_dup_tokens(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("令牌列表不得有重复（flags/mode_set 位或语义）")
        return v

    @model_validator(mode="after")
    def _card_cross_rules(self) -> "UnitCardModel":
        if self.aura is not None and self.category != "INFANTRY":
            raise ValueError("aura 仅步兵类（指挥班组）卡合法")
        if self.quota_group != "NONE" and self.category != "FIRE_SUPPORT":
            raise ValueError("quota_group 仅火力支援类卡可设非 NONE")
        if self.delivery != "NONE" and self.pool != "RESERVE":
            raise ValueError("空降投送卡必须占预备队池（D017）")
        ekeys = [e.element_key for e in self.elements]
        if len(ekeys) != len(set(ekeys)):
            raise ValueError("elements 内 element_key 必须卡内唯一")
        # PB-55 士气阈值三列显式设定值（非 0 回退哨兵）间须严格递增——错序三档在
        # system_morale elif 阶梯下产生不可达档（不崩溃但语义坏），构建期拦（仅校验
        # 双双显式的对；0=回退 cfg 缺省的跨列关系不在此冒充——由 system_morale
        # 运行期防御断言拦截：拼出有效阈值后非严格递增即抛错，2026-10-04 评审遗留⑤）
        for a, b in ((self.morale_sup_th, self.morale_pin_th),
                     (self.morale_pin_th, self.morale_rout_th),
                     (self.morale_sup_th, self.morale_rout_th)):
            if a > 0 and b > 0 and a >= b:
                raise ValueError(
                    "士气阈值列须严格递增 morale_sup_th < morale_pin_th < morale_rout_th"
                    f"（得 {self.morale_sup_th}/{self.morale_pin_th}/{self.morale_rout_th}）")
        return self


# ── 待定登记与库根 ──

class PendingItemModel(BaseModel):
    """待定登记五元组（air_data.py:416-454 PENDING_NUMERIC_ITEMS 惯例；DATA-01 §6.3）。"""
    model_config = ConfigDict(extra="forbid")
    pending_id: str = Field(pattern=r"^P-\d+$")
    scope: str = Field(min_length=1)
    field: str = Field(min_length=1)
    filled_value: str = Field(min_length=1)
    resolve_plan: str = Field(min_length=1)


class CardLibraryModel(BaseModel):
    """全库 JSON 根（DATA-01 §4.7）。"""
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    source_sha256: str = Field(min_length=1)  # 源 CSV 拼接哈希（审计用）
    cards: list[UnitCardModel] = Field(min_length=1)
    pending: list[PendingItemModel] = []

    @model_validator(mode="after")
    def _library_rules(self) -> "CardLibraryModel":
        if not schema_version_supported(self.schema_version):
            raise ValueError(
                f"schema_version {self.schema_version!r} 不在支持表 "
                f"{SUPPORTED_CARD_SCHEMA}（major 不在表或 minor 超上界）")
        ckeys = [c.card_key for c in self.cards]
        if len(ckeys) != len(set(ckeys)):
            raise ValueError("card_key 必须全库唯一")
        tids = [c.template_id for c in self.cards]
        if len(tids) != len(set(tids)):
            raise ValueError("template_id 必须全库唯一")
        return self


# ── deck ──

class DeckEntryModel(BaseModel):
    """deck 一行：{card_key, copies}。"""
    model_config = ConfigDict(extra="forbid")
    card_key: str = Field(min_length=1)
    copies: StrictInt = Field(ge=1)


class DeckModel(BaseModel):
    """卡组（DATA-01 §4.6；schema_version 由构建期注入，deck CSV 不携带）。"""
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    deck_key: str = Field(min_length=1)
    faction: FactionTok
    cards: list[DeckEntryModel]
    points_main_cap: StrictInt = Field(default=POINTS_MAIN_CAP, gt=0)      # 〔待定〕D038 方案A
    points_reserve_cap: StrictInt = Field(default=POINTS_RESERVE_CAP, gt=0)  # 同上

    @model_validator(mode="after")
    def _deck_version(self) -> "DeckModel":
        if not schema_version_supported(self.schema_version):
            raise ValueError(
                f"schema_version {self.schema_version!r} 不在支持表 "
                f"{SUPPORTED_CARD_SCHEMA}（major 不在表或 minor 超上界）")
        keys = [e.card_key for e in self.cards]
        if len(keys) != len(set(keys)):
            raise ValueError("deck 内 card_key 不得重复（copies 表份数）")
        return self


def validate_deck(deck: DeckModel, library: CardLibraryModel) -> None:
    """deck 构筑校验（构建期＝本模块；运行期 card_loader 同规则复用——DATA-01 §8）。

    覆盖：D032 同型限份（per_card_limit，None 解析类别默认）／faction 一致／
    D011 类别配额（category×pool 分桶）／R-13 火支子配额（两池总和）／
    D038 点数上限（主力/预备队分池）。违规抛 ValueError（fail-fast，不静默截断）。
    """
    if deck.schema_version != library.schema_version:
        raise ValueError(
            f"deck schema_version {deck.schema_version!r} 与卡库 "
            f"{library.schema_version!r} 不一致（三版本绑定——DATA-01 §3）")
    by_key = {c.card_key: c for c in library.cards}
    cat_pool: dict[tuple[str, str], int] = {}
    subquota: dict[str, int] = {}
    points: dict[str, int] = {"MAIN": 0, "RESERVE": 0}
    for entry in deck.cards:
        card = by_key.get(entry.card_key)
        if card is None:
            raise ValueError(f"deck 引用卡 {entry.card_key!r} 不在卡库")
        if card.faction != deck.faction:
            raise ValueError(f"卡 {entry.card_key!r} 阵营 {card.faction} 与 deck {deck.faction} 不一致")
        limit = (card.per_card_limit if card.per_card_limit is not None
                 else PER_CARD_LIMIT_BY_CATEGORY[card.category])
        if entry.copies > limit:  # D032
            raise ValueError(
                f"{entry.card_key} 份数 {entry.copies} 超 D032 同型限份 {limit}")
        cat_pool[(card.category, card.pool)] = (
            cat_pool.get((card.category, card.pool), 0) + entry.copies)
        if card.quota_group != "NONE":  # R-13 子配额（两池总和）
            subquota[card.quota_group] = subquota.get(card.quota_group, 0) + entry.copies
        points[card.pool] += card.cost * entry.copies
    for (cat, pool), n in cat_pool.items():  # D011
        cap = CATEGORY_QUOTA[cat][pool]
        if n > cap:
            raise ValueError(f"{cat}×{pool} 配额 {n} 超 D011 上限 {cap}")
    for group, n in subquota.items():
        cap = FIRE_SUPPORT_SUBQUOTA[group]
        if n > cap:
            raise ValueError(f"火支子配额 {group} 共 {n} 份超上限 {cap}（两池总和）")
    if points["MAIN"] > deck.points_main_cap:
        raise ValueError(f"主力池点数 {points['MAIN']} 超上限 {deck.points_main_cap}（D038）")
    if points["RESERVE"] > deck.points_reserve_cap:
        raise ValueError(f"预备队池点数 {points['RESERVE']} 超上限 {deck.points_reserve_cap}（D038）")
