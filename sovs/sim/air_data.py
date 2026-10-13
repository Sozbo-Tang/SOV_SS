"""机型数值数据表——薄壳再出口（2026-10-12 GP-01 §1.2/DATA-03 §3「航空卡」行改造）。

**数据源已迁 data/gen/cards_air.v1.json**（源＝data/yaml/units/air_{su,ger,weapons}.yaml，
tools/build_yaml.py 编译；数值＝下述账本冻结现值逐字平移）。本模块＝air_loader 加载＋
既有导出面再出口（wire.py `from .air_data import AIR_CARDS` 等导入面零改）；原
CARD_KWARGS 代码构造面改为「自加载模板重建」的派生导出（测试④对表面：真实构造器
AircraftTemplate(**kw) 重建逐字段相等——语义不变）。**12 卡冻结声明由 DATA-03 接管**
（docs/DATA-03-配置层YAML拍板-v1.md §3；编辑面＝YAML，非本表）。

12 张航空卡（GDD-02 v1.9 §6：苏①~⑥ / 德①~⑥）＝10 张 AircraftTemplate（二十字段全量，
经 air.py 冻结构造器实例化）＋2 张空降卡记录（D017 地面一命单位——AircraftTemplate
不适用，完整 UnitTemplate 走地面卡管线 data/yaml/units/{su,ger}_infantry.yaml；本库
paratroops 段保留价/池/投送三键＝运行期对表锚）。

数据来源分级（每字段行内注明；YAML 注释随迁同款）：
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
        承载：data/yaml/units/{su,ger}_infantry.yaml（SU_PARATROOP/GER_PARATROOP 卡）→
        data/gen/cards_ground.v1.json（card_loader.load_library 加载并对表本库 paratroops 段）；
        待定细化项在 data/yaml/sidecar/pending.yaml（P-101 限份/category、P-102 编制等，
        DATA-01 §13.2）——余量仅卡组限份待 D032 细化（O-05）
══════════════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from .air import AircraftTemplate
from .air_loader import (DEFAULT_AIR_LIBRARY_PATH, AirLoaderError,  # noqa: F401 （再出口）
                         ParatroopCardSpec, load_air_library)

# ── 模块级单例加载（air_data 既有消费面零改：导入即得冻结实例）──
_LIB = load_air_library(DEFAULT_AIR_LIBRARY_PATH)

# ── 空射武器档案（air_weapons.yaml 七档——air_loader 构造的共享 WeaponTemplate）──
W_BOMB_FAB100 = _LIB.weapons["W_BOMB_FAB100"]
W_BOMB_FAB250 = _LIB.weapons["W_BOMB_FAB250"]
W_BOMB_SC250 = _LIB.weapons["W_BOMB_SC250"]
W_BOMB_SC1000 = _LIB.weapons["W_BOMB_SC1000"]
W_STRAFE_VYA23 = _LIB.weapons["W_STRAFE_VYA23"]
W_STRAFE_SHVAK = _LIB.weapons["W_STRAFE_SHVAK"]
W_STRAFE_MG151 = _LIB.weapons["W_STRAFE_MG151"]

# ── §D.1 航空模板静态 20（air_loader 冻结构造；苏 1~5/德 11~15）──
PO2 = _LIB.aircraft["PO2"]
PE2 = _LIB.aircraft["PE2"]
IL2M = _LIB.aircraft["IL2M"]
YAK9 = _LIB.aircraft["YAK9"]
LI2 = _LIB.aircraft["LI2"]
FW189 = _LIB.aircraft["FW189"]
JU88 = _LIB.aircraft["JU88"]
JU87D = _LIB.aircraft["JU87D"]
FW190A = _LIB.aircraft["FW190A"]
JU52 = _LIB.aircraft["JU52"]

SOVIET_AIR: tuple[AircraftTemplate, ...] = (PO2, PE2, IL2M, YAK9, LI2)      # §6.1 ①~⑤
GERMAN_AIR: tuple[AircraftTemplate, ...] = (FW189, JU88, JU87D, FW190A, JU52)  # §6.2 ①~⑤
AIRCRAFT_TEMPLATES: tuple[AircraftTemplate, ...] = SOVIET_AIR + GERMAN_AIR


# ── 空降两卡（§6.1⑥ / §6.2⑥；D017 地面一命单位——完整 UnitTemplate 走地面卡管线，
#    本库 paratroops 段两记录保留价/池/投送三键＝运行期对表锚，类说明见 air_loader）──
SU_PARATROOP = _LIB.paratroops["SU_PARATROOP"]
GER_PARATROOP = _LIB.paratroops["GER_PARATROOP"]

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


def _kwargs_from(t: AircraftTemplate) -> dict:
    """自加载模板重建 CARD_KWARGS（§D.1 二十字段原样——测试④真实构造器对表面；
    P1 机制块 2026-10-13：+can_afterburner/decoy_charges/passive_evade_bp 三能力位）。"""
    return dict(
        template_id=t.template_id, name=t.name, role=t.role, cost_body=t.cost_body,
        hp_max=t.hp_max, armor_aa=t.armor_aa, speed_cm_tick=t.speed_cm_tick,
        dogfight_power=t.dogfight_power, maneuver=t.maneuver,
        alt_ceiling=t.alt_ceiling, optics_air_cm=t.optics_air_cm,
        recon_mark_base_bp=t.recon_mark_base_bp, weapons=t.weapons,
        payload_max_bombs=t.payload_max_bombs,
        payload_max_supply=t.payload_max_supply,
        paratroop_seats=t.paratroop_seats, turret_damage=t.turret_damage,
        can_engage_air=t.can_engage_air, has_dive=t.has_dive,
        payload_price=t.payload_price,
        can_afterburner=t.can_afterburner, decoy_charges=t.decoy_charges,
        passive_evade_bp=t.passive_evade_bp)


#: 十机 kwargs（派生导出——原代码构造面；数值权威＝data/yaml/units/air_*.yaml）
CARD_KWARGS: dict[str, dict] = {k: _kwargs_from(t) for k, t in _LIB.aircraft.items()}

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


# ── 数值待定清单（结构表——与文件头『数值待定清单』逐条对应，改动须两处同步；
#    值已逐字平移 data/yaml/units/air_*.yaml，本表为账本留档）──
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
     "本库仅登记价 60/65、预备队池、投送限定；地面侧全字段已由地面卡管线承载（2026-10-02 首批："
     "data/yaml/units/{su,ger}_infantry.yaml → data/gen/cards_ground.v1.json，card_loader 加载并与本库对表）",
     "管线已落地（DATA-01 冻结＋§13 首批 10 卡；待定细化转 data/yaml/sidecar/pending.yaml P-101/P-102）；"
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
