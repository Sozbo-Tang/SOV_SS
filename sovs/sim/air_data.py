"""机型数值数据表（终检报告登记的规划内增量②——§D.3 硬要求①~⑦ 的机型配置数据）。

12 张航空卡（GDD-02 v1.9 §6：苏①~⑥ / 德①~⑥）＝10 张 AircraftTemplate（二十字段全量，
经 air.py 冻结构造器实例化）＋2 张空降卡记录（D017 地面一命单位——AircraftTemplate 不适用，
完整 UnitTemplate 走地面卡管线；**该管线已落地（2026-10-02 首批，见下方 P-13 衔接登记）**，
air.py:8-15 自登记；本表登记 GDD 给出的卡面字段。12 张航空卡冻结于本表、不向管线迁移）。

数据来源分级（每字段行内注明）：
  〔GDD〕 GDD-02-单位功能细则-v1.9.md §6（:292-293 预算/限份、:312-317 R-23、:321-326 苏①~⑥、
          :330-335 德①~⑥、:339 阵营差异）＋ GDD-01-兵种表-v1.md 航空表（:92-99 苏 / :168-174 德）。
  〔数锚〕 GDD-03-单位机制数据全集.md（D067 数值现实锚定）：§1.1 HP（:12）、§2.3 曲射溅射/压制
          （:107-125）、§2.4 空对地/对空表（:127-142）、§3.6 航空卡（:209-215）。
  〔冻结〕 AIR_UNITS_PSEUDOCODE_IMPL_v1.4.md：§D.1 二十字段（:77-103）、§D.1 注 entry_tier
          （:102）、§D.3 空射武器档案与硬要求①~⑦（:136-146）、§A 逐卡验收（:673-705）、
          §D.0 常数（:29-73）。
  〔拍板〕 GDD-02-航空拍板清单-v1.md：B-09（:34-39）、B-21（:48-53）、B-24（:91-96）等。
  〔锚点〕 AIR-00-航空机制调研锚点.md（机制方向；机型数值无锚，仅机制印证）。
  〔待定〕 GDD 未给值、按默认填——逐项登记于下方『数值待定清单』（P-xx），留待数值章节。

════════════ 数值待定清单（GDD 未给值而按默认填；与 PENDING_NUMERIC_ITEMS 逐条对应）════════════
  P-01 十机空速 speed_cm_tick（km/h×2//5 换算标尺）……建议定标：数值章节（地图尺度×飞入时间体感）
  P-02 九机 hp_max 在 GDD-03 §1.1"飞机60~80"带内取值（Il-2M=130 为显式例外）……防空链联调
  P-03 十机 armor_aa（0-20 相对刻度；仅 Il-2M 高/Ju 87D 低两方向有据）……对空 HE 曲线配平
  P-04 攻击机/运输机 4 机 alt_ceiling=MID（§D.1 注仅明 Po-2=LOW/轰炸机=MID/战斗机=HIGH）……R-23 层博弈
  P-05 Po-2/Fw 189 optics_air_cm……对照地面 optics_air_cm 防空探测尺度
  P-06 Po-2/Fw 189 recon_mark_base_bp……与地面 sensing 标记率对照
  P-07 四型 BOMB 档全数值（blast/suppression 锚 GDD-03 §2.3 溅射/压制带）……数值章节
  P-08 三型 STRAFE 档全数值（攻顶穿深对照 Armor 0-20 相对刻度 T 槽）……地面 T 甲曲线配平
  P-09 四机 payload_max_bombs 颗数（GDD-03 kg 级→游戏颗数换算；Ju 87D=1 为 GDD-03 :212 直接数锚）……覆盖面积/经济联调
  P-10 payload_price 单价（BOMB×4 型 / SUPPLY×2 型）……空军预算 750（D038 方案A）体感
  P-11 Li-2/Ju 52 payload_max_supply=150（D012 重量口径 vs §F1 计数门两读）……D012 对齐
  P-12 Pe-2/Ju 88/Li-2/Ju 52 turret_damage（§D.1 #17 仅约束 BOMBER/TRANSPORT>0）……缠斗回合节奏
  P-13 空降两卡地面侧全字段与卡组限份（GDD 仅给价 60/65 与投送限定）……地面卡管线已落地
        承载：data/ground_cards.csv（SU_PARATROOP/GER_PARATROOP 行）→ data/gen/cards_ground.v1.json
        （card_loader.load_library 加载并对表本表 ParatroopCardSpec）；待定细化项已转地面侧
        data/ground_pending.csv（P-101 限份/category、P-102 编制等，DATA-01 §13.2）——余量仅
        卡组限份待 D032 细化（O-05），见下方结构表 P-13 行衔接说明
══════════════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from dataclasses import dataclass

from .air import AirRole, AircraftTemplate
from .types import AltTier, DamageType, TargetDomain, Trajectory, WeaponTemplate

_GROUND = int(TargetDomain.GROUND)  # §D.3：空射武器 target_mask=GROUND（对空无武器档案——R-20 走模板掷骰）


# ── §D.3 空射武器档案（复用地面 WeaponTemplate，0 新子字段；硬要求⑥ crit_mod_permille=0）──
# 档身份按配置判定（air.py weapon_slot——复检①统一谓词：STRAFE=DIRECT+KE+GROUND、
# BOMB=HE+BALLISTIC+GROUND），name 不再要求等于 "BOMB"/"STRAFE"（§F1 弹药初始化与
# _weapon_of 同一 helper）。
# 溅射/压制锚 GDD-03 §2.3（:107-125）：120迫 20m/35、ML-20 25m/55、sFH 25m/55——炸弹按
# 弹重插带取整；其余数值 GDD 未给〔待定 P-07/P-08〕。

W_BOMB_FAB100 = WeaponTemplate(
    # Il-2M 用 100kg 级〔数锚〕GDD-03 :131"炸弹400~600kg"→4×100kg〔待定 P-09〕
    name="BOMB", target_mask=_GROUND, damage_type=DamageType.HE,
    pen_max=8,                       # HE 直击穿透代理（resolve_blast 地面侧消费）〔待定 P-07〕
    damage=40, blast_radius_cm=2000,  # 100kg≈120迫-152加榴溅射带（§2.3）〔待定 P-07〕
    dispersion_cm=1500,              # 低空抛投散布最粗（Il-2 非精瞄机型）〔待定 P-07〕
    salvo=2,                         # §D.3"salvo=单次投弹颗数"〔待定 P-07〕
    ammo_base=4, projectile_speed_cm_tick=400, trajectory=Trajectory.BALLISTIC,
    suppression_power=35,            # §2.3 带：82迫25/120迫35 级〔待定 P-07〕
    crit_mod_permille=0,             # 〔冻结〕硬要求⑥：空射 crit=0（AMB2-08）
)

W_BOMB_FAB250 = WeaponTemplate(
    # Pe-2 用 250kg 级〔数锚〕GDD-03 :133"600~1000kg"→4×250kg〔待定 P-09〕
    name="BOMB", target_mask=_GROUND, damage_type=DamageType.HE,
    pen_max=12, damage=70, blast_radius_cm=2500,   # 250kg≈ML-20/sFH18 溅射带（§2.3）〔待定 P-07〕
    dispersion_cm=1200,             # 快速水平轰炸（540km/h 快→散布乘区大，精度让位速度）〔待定 P-07〕
    salvo=2, ammo_base=4, projectile_speed_cm_tick=400,
    trajectory=Trajectory.BALLISTIC, suppression_power=55,  # =ML-20/sFH18（§2.3）〔待定 P-07〕
    crit_mod_permille=0,
)

W_BOMB_SC250 = WeaponTemplate(
    # Ju 88 用 250kg 级×6〔数锚〕GDD-03 :138"~1400kg"＋:214"1400kg=覆盖最大"〔待定 P-09〕
    name="BOMB", target_mask=_GROUND, damage_type=DamageType.HE,
    pen_max=12, damage=70, blast_radius_cm=2500,
    dispersion_cm=1000,             # 〔GDD〕GDD-02 v1.9 :331"精度略高但慢"→基数低于 Pe-2〔待定 P-07〕
    salvo=3, ammo_base=6, projectile_speed_cm_tick=400,
    trajectory=Trajectory.BALLISTIC, suppression_power=55,
    crit_mod_permille=0,
)

W_BOMB_SC1000 = WeaponTemplate(
    # Ju 87D 用 1000kg 级×1〔数锚〕GDD-03 :212"常态挂载500~1400kg→游戏炸弹1×1000kg级"〔待定 P-09〕
    name="BOMB", target_mask=_GROUND, damage_type=DamageType.HE,
    pen_max=18, damage=130, blast_radius_cm=3500,  # 1000kg 超重弹（>ML-20 溅射带顶）〔待定 P-07〕
    dispersion_cm=900,              # 垂直精度由 has_dive×0.3 乘区承载（B-09）——基数再压低〔待定 P-07〕
    salvo=1, ammo_base=1, projectile_speed_cm_tick=400,
    trajectory=Trajectory.BALLISTIC, suppression_power=90,
    crit_mod_permille=0,
)

W_STRAFE_VYA23 = WeaponTemplate(
    # Il-2M VYa-23mm〔GDD〕GDD-02 v1.9 :323"扫射火力凶"→全场最强扫射〔待定 P-08〕
    name="STRAFE", target_mask=_GROUND, damage_type=DamageType.KE,
    pen_min=10, pen_max=12,         # 攻顶穿深（types.py Armor 0-20 相对刻度 T 槽）〔待定 P-08〕
    damage=5, blast_radius_cm=0, max_range_cm=80000,
    accuracy_base_bp=7000,          # 经 strafe_acc_alt_bp×1.3 低空=9100〔待定 P-08〕
    salvo=6,                        # §D.3/B-28：对走廊内每个敌方元素各掷 salvo 发
    ammo_base=24, projectile_speed_cm_tick=2000, trajectory=Trajectory.DIRECT,
    suppression_power=40,           # >边斗机枪 12/发（GDD-02 v1.9 :366 参照）〔待定 P-08〕
    crit_mod_permille=0,            # 〔冻结〕硬要求⑥
)

W_STRAFE_SHVAK = WeaponTemplate(
    # Yak-9 ShVAK 20mm〔GDD〕GDD-02 v1.9 :324"扫射攻顶"〔待定 P-08〕
    name="STRAFE", target_mask=_GROUND, damage_type=DamageType.KE,
    pen_min=6, pen_max=8, damage=3, blast_radius_cm=0, max_range_cm=80000,
    accuracy_base_bp=6500, salvo=4, ammo_base=16,
    projectile_speed_cm_tick=2000, trajectory=Trajectory.DIRECT,
    suppression_power=25, crit_mod_permille=0,
)

W_STRAFE_MG151 = WeaponTemplate(
    # Fw 190A MG151/20＋MG131〔GDD〕GDD-02 v1.9 :333"对空战力与扫射火力双强（贵于Yak-9的10分在此）"
    # →扫射强于 Yak-9、弱于 Il-2M〔待定 P-08〕
    name="STRAFE", target_mask=_GROUND, damage_type=DamageType.KE,
    pen_min=7, pen_max=9, damage=4, blast_radius_cm=0, max_range_cm=80000,
    accuracy_base_bp=7000, salvo=5, ammo_base=20,
    projectile_speed_cm_tick=2000, trajectory=Trajectory.DIRECT,
    suppression_power=30, crit_mod_permille=0,
)


# ── §D.1 航空模板静态 20（二十字段全量显式构造——缺一键即 TypeError，完备性由构造承担）──
# 每卡kwargs 原样存 CARD_KWARGS（测试④用真实构造器 AircraftTemplate(**kw) 重建逐字段相等）。

CARD_KWARGS: dict[str, dict] = {
    # ── 苏军（GDD-02 v1.9 :321-326；GDD-01 :92-99）──
    "PO2": dict(
        template_id=1,               # 回放校验号自编（苏 1~5/德 11~15）〔待定：无 GDD 值，编号方案留数值章节〕
        name="Po-2侦察机",
        role=AirRole.RECON,
        cost_body=20,                # 〔GDD〕v1.9 :321"① Po-2侦察机 · 20分"
        hp_max=60,                   # 〔数锚〕:12"飞机60~80"带内下限——便宜消耗品〔待定 P-02〕
        armor_aa=0,                  # 帆布双翼无装甲〔数锚〕GDD-03 :132 装甲"无"〔待定 P-03〕
        speed_cm_tick=60,            # 150km/h（GDD-03 :132）×2//5；≤air_recon_speed_ref=100 保
                                     # air.py:137"慢速(Po-2)速度因子=10000"锚点〔待定 P-01〕
        dogfight_power=1,            # 〔数锚〕GDD-03 :132"对空战力/机动=1/3"（照抄表值）
        maneuver=3,
        alt_ceiling=AltTier.LOW,     # 〔冻结〕IMPL v1.4 §A :677"alt_ceiling=LOW"（超低空侦察）
        optics_air_cm=6000,          # R-23 :314 低空观察半径小；卡面 :321"超低空慢速侦察"〔待定 P-05〕
        recon_mark_base_bp=3000,     # 概率性标记（GDD-01 :95"低空慢速概率侦察"）〔待定 P-06〕
        weapons=(),                  # 无武器机型（§F7 GAP2-05 侦察机豁免弹尽 RTB 前提）；
                                     # 夜间骚扰槽位零消费登记（§A :679，夜战首版后置）
        payload_max_bombs=0, payload_max_supply=0, paratroop_seats=0,
        turret_damage=0,             # 非 BOMBER/TRANSPORT（§D.1 #17）
        can_engage_air=False, has_dive=False, payload_price={},
    ),
    "PE2": dict(
        template_id=2,
        name="Pe-2战术轰炸机",
        role=AirRole.BOMBER,
        cost_body=85,                # 〔GDD〕v1.9 :322"② Pe-2战术轰炸机 · 85分"
        hp_max=70,                   # 〔数锚〕:12 带内中值〔待定 P-02〕
        armor_aa=3,                  # 〔数锚〕GDD-03 :133 装甲"无"→低档〔待定 P-03〕
        speed_cm_tick=216,           # 540km/h（GDD-03 :133）×2//5——快速水平轰炸（投弹前暴露短，
                                     # v1.9 :322；GDD-03 :142 注"快机暴露短"）〔待定 P-01〕
        dogfight_power=3,            # 〔数锚〕GDD-03 :133"3/7"（照抄）
        maneuver=7,
        alt_ceiling=AltTier.MID,     # 〔冻结〕§D.1 注 :102"轰炸机(MID)"
        optics_air_cm=0, recon_mark_base_bp=0,   # 非侦察职能（§F5 仅 RECON 消费）
        weapons=((W_BOMB_FAB250, 4),),           # 〔冻结〕硬要求③"Pe-2/Ju 88 配 BOMB"；弹量=档案满载
                                     # 数（运行时 BOMB 弹药以 payload 购买数为准——§F1/GAP2-04）
        payload_max_bombs=4,         # 1000kg=4×250kg 级〔数锚〕GDD-03 :133〔待定 P-09〕
        payload_max_supply=0, paratroop_seats=0,
        turret_damage=3,             # 〔冻结〕§D.1 #17"BOMBER/TRANSPORT>0"（后射机枪）〔待定 P-12〕
        can_engage_air=False, has_dive=False,    # 快速水平轰炸——非俯冲机型
        payload_price={"BOMB": 6},   # 〔待定 P-10〕D015 弹药价无量值
    ),
    "IL2M": dict(
        template_id=3,
        name="Il-2M攻击机",
        role=AirRole.ATTACK,
        cost_body=90,                # 〔GDD〕v1.9 :323"③ Il-2M攻击机 · 90分"
        hp_max=130,                  # 〔数锚〕GDD-03 :12"飞机60~80、Il-2=130"显式＋:211"装甲壳700kg=HP130"
        armor_aa=12,                 # 〔数锚〕GDD-03 :131"装甲壳700kg(5~12mm关键部位)"→全场最高
                                     # （v1.9 :323"重装甲飞行坦克：抗高炮"）〔待定 P-03〕
        speed_cm_tick=160,           # 400km/h（GDD-03 :211"速度400"取 §3.6 口径；§2.4 :131"400~415"）
                                     # ×2//5——慢=高炮窗口最长（GDD-03 :142 注）〔待定 P-01〕
        dogfight_power=5,            # 〔数锚〕GDD-03 :131"5/4"（照抄）
        maneuver=4,                  # 卡面 :323"机动笨"——maneuver 全场低位 ✓
        alt_ceiling=AltTier.MID,     # 〔待定 P-04〕§D.1 注未涉攻击机；取 MID（可下 LOW 扫射/投弹）
        optics_air_cm=0, recon_mark_base_bp=0,
        weapons=((W_BOMB_FAB100, 4), (W_STRAFE_VYA23, 24)),
                                     # 〔冻结〕硬要求①"Il-2M 配 STRAFE+BOMB"
        payload_max_bombs=4,         # 400kg=4×100kg 级〔数锚〕GDD-03 :131"炸弹400~600kg"〔待定 P-09〕
        payload_max_supply=0, paratroop_seats=0, turret_damage=0,
        can_engage_air=True,         # 〔冻结〕§D.1 #18"can_engage_air（Il-2 置位）"＋§A :684
                                     # ——v1.9 :323"转对空丢弹全职能"（D015）
        has_dive=False,              # 浅俯冲非真俯冲轰炸机（俯冲乘区专属 Ju 87D——B-09）
        payload_price={"BOMB": 3},   # 〔待定 P-10〕
    ),
    "YAK9": dict(
        template_id=4,
        name="Yak-9战斗机",
        role=AirRole.FIGHTER,
        cost_body=70,                # 〔GDD〕v1.9 :324"④ Yak-9战斗机 · 70分"
        hp_max=70,                   # 〔数锚〕:12 带内中值〔待定 P-02〕
        armor_aa=3,                  # 〔待定 P-03〕
        speed_cm_tick=239,           # ~599km/h（GDD-03 :134）×2//5〔待定 P-01〕
        dogfight_power=7,            # 〔数锚〕GDD-03 :134"7/9"（照抄；:215 注——Fw190 的 60km/h
        maneuver=9,                  #   优势换算缠斗机动+1"9→对8"已含在表值 9/8 内）
        alt_ceiling=AltTier.HIGH,    # 〔冻结〕§D.1 注 :102"战斗机(HIGH)"（R-23 :316 战斗机可及高空）
        optics_air_cm=0, recon_mark_base_bp=0,
        weapons=((W_STRAFE_SHVAK, 16),),
                                     # 〔冻结〕硬要求②"Yak-9/Fw 190A 配 STRAFE"（GDD-01 :97"俯冲扫射攻顶"）
        payload_max_bombs=0, payload_max_supply=0, paratroop_seats=0, turret_damage=0,
        can_engage_air=True,         # 〔冻结〕硬要求⑦"FIGHTER.can_engage_air=TRUE"（AMB3-03）
        has_dive=False, payload_price={},
    ),
    "LI2": dict(
        template_id=5,
        name="Li-2运输机",
        role=AirRole.TRANSPORT,
        cost_body=40,                # 〔GDD〕v1.9 :325"⑤ Li-2运输机 · 40分"
        hp_max=80,                   # 〔数锚〕:12 带内上限（运输机大机体）〔待定 P-02〕
        armor_aa=2,                  # 〔待定 P-03〕
        speed_cm_tick=128,           # 320km/h（GDD-03 :135）×2//5〔待定 P-01〕
        dogfight_power=2,            # 〔数锚〕GDD-03 :135"2/5"（照抄）
        maneuver=5,
        alt_ceiling=AltTier.MID,     # 〔待定 P-04〕
        optics_air_cm=0, recon_mark_base_bp=0,
        weapons=(),                  # 〔冻结〕硬要求⑤"运输机 weapons 可空表"——本表取空（无卡面武器句）
        payload_max_bombs=0,
        payload_max_supply=150,      # rounds+medical 计数合计上限（§F1 容量门口径）〔待定 P-11〕
        paratroop_seats=1,           # 〔冻结〕§D.1 #16"空降兵舱位（TRANSPORT=1，D017）"
        turret_damage=2,             # 〔冻结〕§D.1 #17"TRANSPORT>0"〔待定 P-12〕
        can_engage_air=False, has_dive=False,
        payload_price={"SUPPLY": 1},  # 每补给重量单位 1 点（2026-10-03 拍板：载荷一池化）〔待定 P-10〕
    ),
    # ── 德军（GDD-02 v1.9 :330-335；GDD-01 :168-174）──
    "FW189": dict(
        template_id=11,
        name="Fw 189侦察机",
        role=AirRole.RECON,
        cost_body=30,                # 〔GDD〕v1.9 :330"① Fw 189侦察机 · 30分"
        hp_max=70,                   # 〔数锚〕:12 带内中值〔待定 P-02〕
        armor_aa=2,                  # 〔待定 P-03〕
        speed_cm_tick=142,           # 355km/h（GDD-03 :136）×2//5〔待定 P-01〕
        dogfight_power=1,            # 〔数锚〕GDD-03 :136"1/4"（照抄）
        maneuver=4,
        alt_ceiling=AltTier.HIGH,    # 〔冻结〕§A :689"alt_ceiling=HIGH"——稳定中高空观察
                                     # （v1.9 :330"探测半径外安全"——高空仅重防空+战机可及 R-23 :316）
        optics_air_cm=14000,         # §A :689"optics_air_cm 大"——高空×1.4（recon_optics_alt_bp）
                                     # →大半径观察（v1.9 :330"稳定中高空大半径观察"）〔待定 P-05〕
        recon_mark_base_bp=4000,     # §A :689"recon_mark_base_bp 高"——标记概率靠机体性能〔待定 P-06〕
        weapons=(),                  # 同 Po-2（无武器机型）
        payload_max_bombs=0, payload_max_supply=0, paratroop_seats=0, turret_damage=0,
        can_engage_air=False, has_dive=False, payload_price={},
    ),
    "JU88": dict(
        template_id=12,
        name="Ju 88战术轰炸机",
        role=AirRole.BOMBER,
        cost_body=95,                # 〔GDD〕v1.9 :331"② Ju 88战术轰炸机 · 95分"
        hp_max=80,                   # 〔数锚〕:12 带内上限（大机体）〔待定 P-02〕
        armor_aa=4,                  # 〔待定 P-03〕
        speed_cm_tick=188,           # ~470km/h（GDD-03 :138）×2//5——慢于 Pe-2（v1.9 :331"但慢"）
                                     # 〔待定 P-01〕
        dogfight_power=3,            # 〔数锚〕GDD-03 :138"3/5"（照抄）
        maneuver=5,
        alt_ceiling=AltTier.MID,     # 〔冻结〕§D.1 注 :102"轰炸机(MID)"
        optics_air_cm=0, recon_mark_base_bp=0,
        weapons=((W_BOMB_SC250, 6),),
                                     # 〔冻结〕硬要求③；载弹多（GDD-01 :171"标定区域水平轰炸"）
        payload_max_bombs=6,         # ~1400kg=6×250kg 级——全场最多（GDD-03 :214"1400kg=覆盖最大"）
                                     # 〔待定 P-09〕
        payload_max_supply=0, paratroop_seats=0,
        turret_damage=4,             # 〔冻结〕§D.1 #17 BOMBER>0（双 MG 座）〔待定 P-12〕
        can_engage_air=False, has_dive=False,
        payload_price={"BOMB": 6},   # 〔待定 P-10〕
    ),
    "JU87D": dict(
        template_id=13,
        name="Ju 87D斯图卡",
        role=AirRole.ATTACK,
        cost_body=75,                # 〔GDD〕v1.9 :332"③ Ju 87D斯图卡 · 75分"
        hp_max=60,                   # 〔数锚〕:12 带内下限——v1.9 :332"机体脆"〔待定 P-02〕
        armor_aa=2,                  # 机体脆→低位（防空武器数值地面侧配平——§A :692）〔待定 P-03〕
        speed_cm_tick=160,           # ~400km/h（GDD-03 :137）×2//5〔待定 P-01〕
        dogfight_power=4,            # 〔数锚〕GDD-03 :137"4/5"（照抄）
        maneuver=5,
        alt_ceiling=AltTier.MID,     # 〔待定 P-04〕（俯冲投弹一律按低空系数——B-09，层仅为巡航位）
        optics_air_cm=0, recon_mark_base_bp=0,
        weapons=((W_BOMB_SC1000, 1),),
                                     # 〔冻结〕硬要求④"Ju 87D 配 BOMB 且 has_dive=TRUE"（最小配置；
                                     # GDD-01 :170"+攻顶机炮"表述未入 §A 承载——见文件头 assumptions）
        payload_max_bombs=1,         # 游戏炸弹 1×1000kg 级〔数锚〕GDD-03 :212〔待定 P-09〕
        payload_max_supply=0, paratroop_seats=0, turret_damage=0,
        can_engage_air=False,        # 〔拍板〕B-21"Ju 87D 不置位"（v1.9 :332 注"不可转对空"）
        has_dive=True,               # 〔冻结〕硬要求④；俯冲投弹垂直精度全场最高（×0.6×0.5=×0.3
                                     # 全场最低散布——B-09 锚点，tests/test_air_curves.py:94-97）
        payload_price={"BOMB": 12},  # 〔待定 P-10〕
    ),
    "FW190A": dict(
        template_id=14,
        name="Fw 190A战斗机",
        role=AirRole.FIGHTER,
        cost_body=80,                # 〔GDD〕v1.9 :333"④ Fw 190A战斗机 · 80分"（"贵于Yak-9的10分在此"）
        hp_max=80,                   # 〔数锚〕:12 带内上限〔待定 P-02〕
        armor_aa=5,                  # 德精准精密型（v1.9 :339）→高于 Yak-9〔待定 P-03〕
        speed_cm_tick=252,           # ~630km/h（GDD-03 :139）×2//5——全场最快〔待定 P-01〕
        dogfight_power=9,            # 〔数锚〕GDD-03 :139"9/8"（照抄）——对空战力全场最高
        maneuver=8,                  # （v1.9 :333"对空战力与扫射火力双强"）
        alt_ceiling=AltTier.HIGH,    # 〔冻结〕§D.1 注 :102"战斗机(HIGH)"
        optics_air_cm=0, recon_mark_base_bp=0,
        weapons=((W_STRAFE_MG151, 20),),
                                     # 〔冻结〕硬要求②
        payload_max_bombs=0, payload_max_supply=0, paratroop_seats=0, turret_damage=0,
        can_engage_air=True,         # 〔冻结〕硬要求⑦
        has_dive=False, payload_price={},
    ),
    "JU52": dict(
        template_id=15,
        name="Ju 52运输机",
        role=AirRole.TRANSPORT,
        cost_body=40,                # 〔GDD〕v1.9 :334"⑤ Ju 52运输机 · 40分 — 同Li-2"
        hp_max=80,                   # 同 Li-2（结构镜像；数值带内同取）〔待定 P-02〕
        armor_aa=2,                  # 〔数锚〕GDD-03 :140 装甲"无"〔待定 P-03〕
        speed_cm_tick=106,           # 265km/h（GDD-03 :140）×2//5——慢于 Li-2（265<320）〔待定 P-01〕
        dogfight_power=1,            # 〔数锚〕GDD-03 :140"1/4"（照抄）
        maneuver=4,
        alt_ceiling=AltTier.MID,     # 同 Li-2〔待定 P-04〕
        optics_air_cm=0, recon_mark_base_bp=0,
        weapons=(),                  # 同 Li-2（硬要求⑤ 空）
        payload_max_bombs=0,
        payload_max_supply=150,      # 同 Li-2〔待定 P-11〕
        paratroop_seats=1,           # 〔冻结〕§D.1 #16（TRANSPORT=1）
        turret_damage=2,             # 〔待定 P-12〕
        can_engage_air=False, has_dive=False,
        payload_price={"SUPPLY": 1},  # 每补给重量单位 1 点——同 Li-2〔待定 P-10〕
    ),
}

# 冻结构造器实例化（§D.1 AircraftTemplate——air.py:243-264 唯一权威签名）
PO2 = AircraftTemplate(**CARD_KWARGS["PO2"])
PE2 = AircraftTemplate(**CARD_KWARGS["PE2"])
IL2M = AircraftTemplate(**CARD_KWARGS["IL2M"])
YAK9 = AircraftTemplate(**CARD_KWARGS["YAK9"])
LI2 = AircraftTemplate(**CARD_KWARGS["LI2"])
FW189 = AircraftTemplate(**CARD_KWARGS["FW189"])
JU88 = AircraftTemplate(**CARD_KWARGS["JU88"])
JU87D = AircraftTemplate(**CARD_KWARGS["JU87D"])
FW190A = AircraftTemplate(**CARD_KWARGS["FW190A"])
JU52 = AircraftTemplate(**CARD_KWARGS["JU52"])

SOVIET_AIR: tuple[AircraftTemplate, ...] = (PO2, PE2, IL2M, YAK9, LI2)      # §6.1 ①~⑤
GERMAN_AIR: tuple[AircraftTemplate, ...] = (FW189, JU88, JU87D, FW190A, JU52)  # §6.2 ①~⑤
AIRCRAFT_TEMPLATES: tuple[AircraftTemplate, ...] = SOVIET_AIR + GERMAN_AIR


# ── 空降两卡（§6.1⑥ / §6.2⑥；D017 地面一命单位——完整 UnitTemplate 走地面卡管线，
#    管线已落地 2026-10-02 首批：地面侧字段见 data/ground_cards.csv 与 data/gen/
#    cards_ground.v1.json；本表两记录保留为卡面/对表锚，见 ParatroopCardSpec docstring）──

@dataclass(frozen=True, slots=True)
class ParatroopCardSpec:
    """空降卡 GDD 卡面字段记录（价/池/投送限定）——非 AircraftTemplate：
    落地 instantiate 走地面卡管线（air.py:8-15 自登记规划内增量；§A :688/:695）。
    地面侧全字段已由地面卡管线承载（〔P-13 衔接登记 2026-10-02〕：data/ground_cards.csv
    SU_PARATROOP/GER_PARATROOP 行 → data/gen/cards_ground.v1.json；card_loader 的
    _check_paratroop_alignment 加载期与本表逐字段对表；待定细化项转 data/ground_
    pending.csv P-101/P-102，DATA-01 §13.2）；本记录保留价/池/投送三字段＝运行期
    对表锚，空降落地 UnitInstance 化仍待 spawn_paratroop 桩替换（air.py 头注）。"""
    card_key: str
    name: str
    cost_points: int                 # 占预备队池（D017——不走空军预算）
    pool: str                        # "RESERVE"（预备队 5,000 分编制，GDD-00 D017）
    delivery: AircraftTemplate       # 唯一投送机型（"仅Li-2投送"/"仅Ju 52投送"）


SU_PARATROOP = ParatroopCardSpec(
    card_key="SU_PARATROOP",
    name="空降近卫步枪排",           # 〔GDD〕v1.9 :326"⑥ 空降近卫步枪排 · 60分（占预备队池）"
    cost_points=60,
    pool="RESERVE",
    delivery=LI2,                    # 〔GDD〕:326"仅Li-2投送"（GDD-01 :99）
)
GER_PARATROOP = ParatroopCardSpec(
    card_key="GER_PARATROOP",
    name="空降猎兵排",               # 〔GDD〕v1.9 :335"⑥ 空降猎兵排 · 65分（占预备队池）"
    cost_points=65,
    pool="RESERVE",
    delivery=JU52,                   # 〔GDD〕:335"仅Ju 52投送"（GDD-01 :174）
)

PARATROOP_CARDS: tuple[ParatroopCardSpec, ...] = (SU_PARATROOP, GER_PARATROOP)

# 12 卡总登记（序=GDD §6.1①~⑥ / §6.2①~⑥）
AIR_CARDS: dict = {t.template_id: t for t in AIRCRAFT_TEMPLATES}
AIR_CARD_ORDER: tuple[str, ...] = (
    "PO2", "PE2", "IL2M", "YAK9", "LI2", "SU_PARATROOP",
    "FW189", "JU88", "JU87D", "FW190A", "JU52", "GER_PARATROOP",
)
CARD_OBJECTS: dict = {
    "PO2": PO2, "PE2": PE2, "IL2M": IL2M, "YAK9": YAK9, "LI2": LI2,
    "SU_PARATROOP": SU_PARATROOP,
    "FW189": FW189, "JU88": JU88, "JU87D": JU87D, "FW190A": FW190A,
    "JU52": JU52, "GER_PARATROOP": GER_PARATROOP,
}

# 苏德镜像对（§6 结构：侦察/轰炸/攻击/战斗机/运输/空降 各一对；镜像=同型结构一致，
# 数值按阵营差分——苏皮厚消耗型/德精准精密型，v1.9 :339）
MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    ("PO2", "FW189"), ("PE2", "JU88"), ("IL2M", "JU87D"),
    ("YAK9", "FW190A"), ("LI2", "JU52"),
    ("SU_PARATROOP", "GER_PARATROOP"),
)
# 镜像一致字段集（结构性等——不含数值/编号/阵营特化位）：
#   role/共同武器档（BOMB|STRAFE 按职能）/paratroop_seats/payload_price 键集/
#   turret_damage>0/weapons==()
# 特意排除（成文的不对称位）：alt_ceiling（Po-2 LOW vs Fw 189 HIGH——卡面分层差异）、
#   can_engage_air/has_dive/攻击机对武器档（Il-2M BOMB+STRAFE 不可俯冲 vs Ju 87D 仅 BOMB
#   且俯冲——硬要求①vs④＋B-21/B-09 卡面收窄）、数值六件（价/HP/甲/速/战力/机动——
#   苏皮厚消耗 vs 德精准精密）。


# ── 数值待定清单（结构表——与文件头『数值待定清单』逐条对应，改动须两处同步）──
# 字段：(编号, 范围, 字段/项, 本次填入, 建议定标来源)
PENDING_NUMERIC_ITEMS: tuple[tuple[str, str, str, str, str], ...] = (
    ("P-01", "十机全部", "speed_cm_tick",
     "km/h×2//5（60/216/160/239/128/142/188/160/252/106）",
     "数值章节：地图尺度×飞入时间（air_entry_offset 60000cm÷速）体感复核；唯一硬锚=Po-2≤air_recon_speed_ref 100（air.py:137）"),
    ("P-02", "九机（除 Il-2M=130 显式）", "hp_max",
     "60~80 带内取值（60/70/70/80/70/80/60/80/80）",
     "数值章节：与地面防空链（fire_aa/resolve_hit_aa HE 曲线）落地后联调"),
    ("P-03", "十机全部", "armor_aa",
     "0/3/12/3/2/2/4/2/5/2（相对刻度 0-20）",
     "对空 HE 曲线 r²×1000÷(r²+1000) 配平（AIR-00 §二.契约③）；仅 Il-2M 高/Ju 87D 低两方向有卡面依据"),
    ("P-04", "攻击机/运输机 4 机", "alt_ceiling=MID",
     "IL2M/JU87D/LI2/JU52 = MID",
     "R-23 层博弈试玩；§D.1 注 :102 仅明 Po-2=LOW/轰炸机=MID/战斗机=HIGH"),
    ("P-05", "Po-2 / Fw 189", "optics_air_cm", "6000 / 14000",
     "对照地面 optics_air_cm 防空探测尺度（GDD-02 R-17 侦察值定标后统一）"),
    ("P-06", "Po-2 / Fw 189", "recon_mark_base_bp", "3000 / 4000",
     "与地面 sensing 标记率对照（B-23 同拍续标语义下的情报密度目标）"),
    ("P-07", "四型 BOMB 档", "damage/pen/blast/dispersion/salvo/speed/suppression",
     "FAB100 40/8/2000/1500/2、FAB250 70/12/2500/1200/2、SC250 70/12/2500/1000/3、SC1000 130/18/3500/900/1（suppression 35/55/55/90）",
     "blast/suppression 已锚 GDD-03 §2.3 迫/炮带（:107-125）；其余=数值章节覆盖面积/建筑毁伤联调"),
    ("P-08", "三型 STRAFE 档", "damage/pen/salvo/accuracy/suppression/弹量",
     "VYa23 5/10-12/6/7000/40/24、ShVAK 3/6-8/4/6500/25/16、MG151 4/7-9/5/7000/30/20",
     "地面 T 甲曲线（Armor 0-20 相对刻度 T 槽）配平；排序锚=Il-2 凶>Fw190 双强>Yak-9（卡面）"),
    ("P-09", "Pe-2/Ju 88/Il-2M/Ju 87D", "payload_max_bombs", "4/6/4/1",
     "kg→颗换算（250/250/100/1000kg 单弹制）——覆盖面积/经济联调"
     "〔复检注 2026-10-01：Ju 87D=1 已有 GDD-03 :212 直接数锚（'游戏炸弹1×1000kg级'），"
     "颗数本身不待定、留本组仅为覆盖面积/经济联调；余三项 4/6/4 仍按换算+联调待定〕"),
    ("P-10", "四机 BOMB＋两机 SUPPLY", "payload_price",
     "BOMB 6/6/3/12；SUPPLY 每重量单位 1（2026-10-03 一池化后口径）",
     "空军预算 750（D038 方案A占位——tables.py air_budget_base）出动体感"),
    ("P-11", "Li-2 / Ju 52", "payload_max_supply=150",
     "rounds+medical 计数合计（§F1 容量门口径）",
     "D012 重量体系对齐（supply_round_weight=1/med_weight_per_unit=5——tables.py）后改重量口径"),
    ("P-12", "Pe-2/Ju 88/Li-2/Ju 52", "turret_damage", "3/4/2/2",
     "缠斗回合节奏（interval 30 tick×self_defense_prob_bp 2000）联调；§D.1 #17 仅约束>0"),
    ("P-13", "空降两卡（苏⑥/德⑥）", "地面侧全字段＋卡组限份",
     "本表仅登记价 60/65、预备队池、投送限定；地面侧全字段已由地面卡管线承载（2026-10-02 首批："
     "data/ground_cards.csv → data/gen/cards_ground.v1.json，card_loader 加载并与本表对表）",
     "管线已落地（DATA-01 冻结＋§13 首批 10 卡；待定细化转 data/ground_pending.csv P-101/P-102）；"
     "余量仅卡组限份待 D032 细化（O-05）——数值章节"),
)

__all__ = [
    "AIRCRAFT_TEMPLATES", "AIR_CARDS", "AIR_CARD_ORDER", "CARD_OBJECTS",
    "CARD_KWARGS", "MIRROR_PAIRS", "PENDING_NUMERIC_ITEMS", "ParatroopCardSpec",
    "SOVIET_AIR", "GERMAN_AIR", "PARATROOP_CARDS",
    "PO2", "PE2", "IL2M", "YAK9", "LI2",
    "FW189", "JU88", "JU87D", "FW190A", "JU52",
    "SU_PARATROOP", "GER_PARATROOP",
    "W_BOMB_FAB100", "W_BOMB_FAB250", "W_BOMB_SC250", "W_BOMB_SC1000",
    "W_STRAFE_VYA23", "W_STRAFE_SHVAK", "W_STRAFE_MG151",
]
