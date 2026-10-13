"""手册符合性门禁（Manual Conformance Gate）——常驻门禁，与 pytest 平级。

结论先行：本文件把《断箭》官方手册指令系统的**仲裁规格（46 条，2026-10-13）**
逐条锁进断言——改键位/改语义前先改这里：
- ① 键位类：读 shell_fsm 键位表（COMBAT_KEYS/_ARM_BY_KEY）＋窗口键名映射＋
  帮助面板/参数条**源表**断言（读文本/读常量，不依赖 GL 开窗）；
- ② 语义类：规格各条已实现面至少一个**行为锚**（无头会话/命令层驱动——
  make_world/make_unit 合成卡 61x/69x＋CmdBus/queue_command 真引擎链，
  夹具风格同 tests/test_p1_mechanics.py 60x 段）；
- ③ done 项各一个存在性锚（行为锚/常量锚/源文本锚至少其一）；
- ④ deferred/manual_silent 项以**清单常量**登记在册（防静默蒸发：条目增删、
  后置项被悄悄实现或登记被悄悄删除都会在本门禁爆红）。

手册原文（唯一权威）：out/refs/manual.txt＋out/refs/basics.txt（本地已抽取）。
断言失败=实现与规格不符=**修实现不修断言**；只有当断言本身与手册原文冲突时
才允许改断言，且必须 quote 手册原文（行号）并同步 MANUAL_SPEC 登记面。

现值口径（与仲裁规格原判的差异登记，防口径漂移）：
- 仲裁规格三项 deferred（弹药档 Precision／Laser Designation／Precision
  Strike——原「1944 题材无激光制导」裁决）已被 **P1 机制块（2026-10-13）推翻
  实现**：激光照射 N＋第三弹药位 PRECISION＋精密打击 P 均已落地（发起人拍板
  修订题材裁决，fm_panel.py「精确弹=吸附最近本队激光位」留痕）——本门禁按
  现值判 done 并给行为锚。
- 其余仲裁 todo_p1 项（B 地面退款／K 全航道扫射／V 两态／O 逐一跳伞+自动
  空投／Z 加力燃油／X 自动触发事件口／C 诱饵／雷达／被动对策／TAB／战中
  呼援／登车／补给三档／补给堆四开关／飞机限制）同由 P1 块收口为 done。
- deferred 现存 5 条（弹道红显／APS／通讯标记／收入维护费／损毁回卡组）与
  manual_silent 6 条维持仲裁判——非实现面用「不存在锚」反向锁死（防半吊子
  悄悄长出，也防登记蒸发）。
- **终审修复块（2026-10-13，GP-02 §三 6/8/10/13/14 判「与手册不符且非后置」
  的逐条收口）**：①MMB 相机旋转落地（2D 顶视=绕视口中心的视图旋转——
  manual.txt:594）；②严重损伤四类暴击恢复（D071「全拆+留口子」被推翻——
  按预留口子回贴 roll_crit/upgrade_crit＋below(4) 四类＋步兵轻 AT 必暴击位
  crit_guaranteed，basics:214-230＋manual.txt:339-341）并**入登记面**（46→
  47 条——原覆盖缺口补防）；③补给三档改手册数值刻度 1000/4000/买满
  （basics:198-200，卡车舱位随扩 4000）；④卸货成堆落地（CreateDumpCmd——
  basics:202-204，D065「卡车即堆不建堆实体」单形态判被推翻为并存形态）；
  ⑤新增 SPEC_DEVIATED 走样分区（SEAD 反辐射博弈／设置菜单改键——题材与
  范围硬冲突的显式在册登记，非后置、非静默）。
"""
from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.sim import air as _air_mod                                    # noqa: E402
from sovs.sim.air import (PHASE_DEPLOY, AirRole, AirState, AirTask,     # noqa: E402
                          AircraftTemplate, StrikePhase, TaskKind,
                          aircraft_move_step, cmd_air_afterburner,
                          cmd_air_decoy, cmd_air_strike, entry_tier,
                          missile_warning, resolve_airdrop, resolve_strafe)
from sovs.sim.combat import apply_damage                                # noqa: E402
from sovs.sim.tables import CONFIG                                      # noqa: E402
from sovs.sim.tick import (CancelCmd, DeckSlot, DismountCmd, MoveCmd,   # noqa: E402
                           SetModeCmd, SetStanceCmd, add_unit, cmd_attack,
                           cmd_fire_mission, cmd_ground_rtb,
                           cmd_laser_designate, cmd_purchase, cmd_radar,
                           cmd_smoke, cmd_sprint, consume_commands,
                           fire_permitted, ground_recovery, laser_marks_of,
                           make_unit, make_world, queue_command,
                           radar_active, radar_range_mult,
                           unit_refund_points, world_tick)
from sovs.sim.types import (AltTier, Building, DamageType,               # noqa: E402
                            ElementTemplate, ElementType, FireMission,
                            FireMissionForm, Mode, MoveMode,
                            MovementClass, Stance, TargetDomain,
                            Trajectory, UnitFlag, UnitTemplate, UnitType,
                            WeaponTemplate, WState)
from sovs.ui import shell_fsm as _fsm_mod                               # noqa: E402
from sovs.ui.cmd_bus import CmdBus                                      # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ════════════════════════════════════════════════════════════════════
# ④ 规格登记面（仲裁规格 46 条现值——防静默蒸发的事实源；改判先改这里）
# ════════════════════════════════════════════════════════════════════
# 条目三元组：(键位, 条目名, 手册锚)。verdict 分区由三个清单承载：
# SPEC_DONE=已实现（各至少一个锚）；SPEC_DEFERRED=后置（登记+不存在锚）；
# SPEC_MANUAL_SILENT=手册无数值/未定义（登记在册，无从逐值验收）。

SPEC_DONE: tuple[tuple[str, str, str], ...] = (
    # ── ORDERS（manual.txt:350-401）──
    ("Q", "ORDERS/Attack Move（攻击移动）", "manual.txt:352-355,560-562"),
    ("E", "ORDERS/Cancel Order（取消命令）", "manual.txt:357-359,565"),
    ("H", "ORDERS/Hold Fire（禁火/还击纪律）", "manual.txt:364-368,575"),
    ("F", "ORDERS/Fast Move（快速移动）", "manual.txt:370-374,570"),
    ("R", "ORDERS/Reverse Move（倒车）", "manual.txt:376-381,566"),
    ("Q+左键点敌", "ORDERS/Force Fire（强制射击）", "manual.txt:383-388"),
    ("B", "ORDERS/Return to Base（回基地退款）", "manual.txt:390-400,577-578"),
    ("U", "ORDERS/Unload（卸载）", "manual.txt:402-407,567-568"),
    # ── AIRCRAFT（manual.txt:409-441）──
    ("K+拖拽画线", "AIRCRAFT/Strafing and Bombing Run（扫射/轰炸航线）",
     "manual.txt:411-418"),
    ("V", "AIRCRAFT/Low Altitude（低空）", "manual.txt:421-428,576"),
    ("O", "AIRCRAFT/Airdrop（空投）", "manual.txt:430-440"),
    # ── ARTILLERY（manual.txt:443-474）──
    ("T", "ARTILLERY/Fire Mission（火任务主令）", "manual.txt:443-453,569"),
    ("图标（fm_panel 参数条）", "ARTILLERY/弹药档 Explosive/Smoke/Precision",
     "manual.txt:455-458"),
    ("图标（fm_panel 参数条）", "ARTILLERY/弹幕时长 Short/Medium/Long",
     "manual.txt:459-461"),
    ("图标（fm_panel 参数条）", "ARTILLERY/弹幕模式 Point/Line/Walking",
     "manual.txt:463-465"),
    ("随火任务（无独立键）", "ARTILLERY/超程自动进位", "manual.txt:471-474"),
    # ── ABILITIES（manual.txt:476-539）──
    ("Z", "ABILITIES/Sprint（冲刺）", "manual.txt:487-490,571-572"),
    ("Z（飞机）", "ABILITIES/Afterburner（加力燃烧）", "manual.txt:492-497"),
    ("X", "ABILITIES/Smoke（自卫烟幕）", "manual.txt:499-503,573"),
    ("C", "ABILITIES/Decoy（诱饵）", "manual.txt:505-509,574"),
    ("N", "ABILITIES/Laser Designation（激光指示）", "manual.txt:517-522"),
    ("P", "ABILITIES/Precision Strike（精确打击）", "manual.txt:528-532"),
    ("Z（高炮单位）", "ABILITIES/Radar（雷达）", "manual.txt:534-539,basics:327-335"),
    ("（无键——常驻装备属性）", "basics/被动对策（Passive countermeasures）",
     "basics:353-356"),
    # ── HOTKEYS（manual.txt:543-580）＋basics 流程 ──
    ("TAB", "HOTKEYS/TAB 子选择", "manual.txt:549,basics:59-60"),
    ("SHIFT", "HOTKEYS/SHIFT 排队下令", "manual.txt:551"),
    ("CTRL+1-9", "HOTKEYS/CTRL+1-9 编组", "manual.txt:554"),
    ("Scroll 缩放 / WASD 平移 / MMB 旋转", "HOTKEYS/镜头控制（滚轮/WASD/MMB）",
     "manual.txt:583-594"),
    ("（无键——流程）", "basics/Deployment 部署暂停", "basics:158-160"),
    ("（无键——流程）", "basics/Deployment 逐个出生+幽灵表示", "basics:162-163"),
    ("增援菜单（无键）", "basics/Reinforcements 战中呼援", "basics:165-168"),
    ("增援菜单（无键）", "basics/Transports 运输呼叫两途", "basics:181-193"),
    ("补给卡点击/Ctrl+Click/Shift+Click", "basics/Supplies 补给购买三档",
     "basics:198-200——数值刻度 1000/4000/买满同复刻（终审修复块）"),
    ("U+点地（卡车）", "basics/补给堆建立与四开关", "basics:202-213——卸货成堆"
     "实体落地＋车载并存（终审修复块推翻 D065 单形态判）"),
    ("（无键——规则）", "basics/飞机限制（补给/燃油/观地）", "basics:311-314"),
    ("（无键——受击规则）", "basics/严重损伤四类暴击＋步兵轻AT必暴击",
     "basics:214-230＋manual.txt:339-341（终审修复块恢复并入登记面）"),
)

# 走样登记（终审修复块 2026-10-13 新增分区）：题材/范围硬冲突的显式在册登记
# ——非后置（不可挂 deferred：无实现排期）、非静默（不留无登记缺口）。条目
# 三元组同上；锚给「已落地的近似面＋不存在锚」双证。
SPEC_DEVIATED: tuple[tuple[str, str, str], ...] = (
    ("Z（高炮单位）——反辐射面", "deviated/SEAD 反辐射博弈",
     "manual.txt:537-539＋basics:331-335——1944 无反辐射弹种：仅落「雷达开机"
     "可视」易损标记位（radar_on 进帧），关机脱锁语义无载体（对空弹非辐射寻的）"),
    ("设置菜单（无入口）", "deviated/设置菜单改键",
     "manual.txt:91,544-545——菜单章节功能在 GP-01 六件需求之外（单机 1944 "
     "题材无 Settings 面）；键位表为源码级常量（shell_fsm COMBAT_KEYS）"),
)

SPEC_DEFERRED: tuple[tuple[str, str, str], ...] = (
    ("随火任务（无独立键）", "ARTILLERY/弹道被遮拦红显告警",
     "manual.txt:467-470——后置：引擎级 LOS/弹道遮拦可视化，宜与弹道检测同批"),
    ("图标（全自动）", "ABILITIES/Active protection system（APS）",
     "manual.txt:511-515,basics:337-346——后置：现代装备，1944 题材无对应"),
    ("F1..F4（现 F1=帮助面板）", "HOTKEYS/通讯标记 F1..F4",
     "manual.txt:547-548,basics:125-138——后置：多人协作功能，单机无消费方"),
    ("（无键——经济）", "basics/Income & Upkeep（收入/维护费）",
     "basics:165-173——后置：2026-10-03 发起人拍板『没有收入机制』冲突"),
    ("（无键——经济）", "basics/损毁单位回卡组",
     "basics:174-175——后置：卡组一命制反向拍板冲突（air 击落/回收冷却为租赁近似）"),
)

SPEC_MANUAL_SILENT: tuple[tuple[str, str, str], ...] = (
    ("随时长档（无独立键）", "manual_silent/长弹幕遭反击脆弱",
     "manual.txt:458-461——『more vulnerable to return fire』无数值（现=声测圈暴露近似）"),
    ("Z", "manual_silent/Sprint 数值",
     "manual.txt:487-490——倍率/时长/冷却无数值（现=升1档钳5）"),
    ("X", "manual_silent/Smoke 数值", "manual.txt:499-503——发数/冷却/半径/持续无数值"),
    ("F", "manual_silent/Fast Move『ignoring cover』行为定义",
     "manual.txt:370-374——无视掩体的具体行为未定义（现=道路提速+prefer_road）"),
    ("随空袭（无独立键）", "manual_silent/低阻/高阻弹机型配属与导弹目标指定",
     "manual.txt:413-418——弹型配属清单与导弹目标指定交互未写"),
    ("（手册未给）", "manual_silent/Force Fire 点地语义与键位",
     "manual.txt:383-388——ORDERS 节本条未给键位，点地语义无从判断"),
)

MANUAL_SPEC: tuple[tuple[str, str, str], ...] = (SPEC_DONE + SPEC_DEFERRED
                                                 + SPEC_MANUAL_SILENT
                                                 + SPEC_DEVIATED)


# ════════════════════════════════════════════════════════════════════
# 源表读取（不依赖 GL：帮助面板/参数条/窗口键名映射读源文本）
# ════════════════════════════════════════════════════════════════════

def _src(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


# ════════════════════════════════════════════════════════════════════
# 无头夹具（合成卡 61x/69x——test_p1_mechanics 60x 段后继，不对应真实卡）
# ════════════════════════════════════════════════════════════════════

def _truck_tpl(cost=50, flags=0):
    return UnitTemplate(
        template_id=611, name="mc truck", category=4, cost=cost,
        element_templates=(ElementTemplate(
            element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
            hp_max=20, cargo_rounds_max=600, cargo_medical_max=120,
            cargo_weight_max=600,
            weapons=(WeaponTemplate(name="mc truck mg", damage=1,
                                    max_range_cm=10000, ammo_base=100,
                                    salvo=1),),),),
        optics_ground_cm=10000, stealth_base=5, speed_tier=3,
        movement_class=MovementClass.WHEEL, flags=flags,
        mode_set=(1 << Mode.DIRECT) | (1 << Mode.CARGO))


def _rifle_tpl(flags=0):
    return UnitTemplate(
        template_id=612, name="mc rifle", category=1, cost=30, flags=flags,
        element_templates=(ElementTemplate(
            element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
            hp_max=10, weapons=(WeaponTemplate(
                name="mc rifle gun", damage=2, max_range_cm=30000,
                ammo_base=100, ammo_weight=1, salvo=1),),),),
        optics_ground_cm=30000, stealth_base=5, speed_tier=1,
        movement_class=MovementClass.FOOT)


def _sniper_tpl():
    return UnitTemplate(
        template_id=613, name="mc sniper", category=0, cost=15,
        flags=UnitFlag.CAN_SNIPER_COVER,
        element_templates=(ElementTemplate(
            element_type=ElementType.SQUAD, unit_type=UnitType.INFANTRY,
            hp_max=4, weapons=(WeaponTemplate(
                name="mc mosin", damage=5, max_range_cm=40000,
                ammo_base=40, combat_style=2, salvo=1),),),),
        optics_ground_cm=50000, stealth_base=10, speed_tier=1,
        movement_class=MovementClass.FOOT)


def _gun_tpl(smoke_row=False):
    weapons = [WeaponTemplate(
        name="mc howitzer", damage=30, max_range_cm=100000,
        blast_radius_cm=2500, ammo_base=60, salvo=2,
        trajectory=Trajectory.BALLISTIC, damage_type=DamageType.HE,
        dispersion_cm=2000, projectile_speed_cm_tick=2000)]
    if smoke_row:
        weapons.append(WeaponTemplate(
            name="mc smoke shell", damage=0, max_range_cm=80000,
            ammo_base=30, salvo=1, trajectory=Trajectory.BALLISTIC,
            damage_type=DamageType.SMOKE, dispersion_cm=1500,
            projectile_speed_cm_tick=2000))
    return UnitTemplate(
        template_id=614, name="mc gun", category=3, cost=70,
        element_templates=(ElementTemplate(
            element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=8,
            weapons=tuple(weapons),),),
        optics_ground_cm=30000, stealth_base=5, speed_tier=1,
        movement_class=MovementClass.WHEEL,
        mode_set=(1 << Mode.DIRECT) | (1 << Mode.INDIRECT))


def _aa_tpl(optics_air=10000, rng=10000, acc_bp=8000):
    return UnitTemplate(
        template_id=615, name="mc aa", category=4, cost=60,
        element_templates=(ElementTemplate(
            element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
            hp_max=10, weapons=(WeaponTemplate(
                name="mc flak", damage=6, max_range_cm=rng,
                target_mask=TargetDomain.AIR | TargetDomain.GROUND,
                ammo_base=200, salvo=1, damage_type=DamageType.HE,
                accuracy_base_bp=acc_bp,
                projectile_speed_cm_tick=4000),),),),
        optics_ground_cm=10000, stealth_base=5, speed_tier=2,
        movement_class=MovementClass.WHEEL, optics_air_cm=optics_air,
        air_ceiling=AltTier.HIGH)


def _air_tpl(**kw):
    d = dict(template_id=696, name="MCT", role=AirRole.FIGHTER, cost_body=60,
             hp_max=60, armor_aa=4, speed_cm_tick=100, dogfight_power=5,
             maneuver=6, alt_ceiling=AltTier.HIGH, weapons=(),
             payload_max_bombs=0, payload_price={})
    d.update(kw)
    return AircraftTemplate(**d)


def _mk_air(w, tpl, team=0, alt=AltTier.MID, pos=(500000, 500000)):
    a = _air_mod.AircraftInstance(id=w.next_aircraft_id, team=team,
                                  player_index=team, template=tpl, pos=pos,
                                  alt_tier=alt, hp_current=tpl.hp_max,
                                  state=AirState.PATROL)
    w.next_aircraft_id += 1
    a.fuel_ticks = CONFIG.air_fuel_ticks
    a.decoy_left = tpl.decoy_charges
    w.aircraft.append(a)
    return a


def _frame(phase="combat", tick=700, *, units=(), aircraft=(), team=0,
           refunds=()):
    return {"schema_version": "1.1", "tick": tick, "phase": phase, "view": team,
            "map_cm": [200000, 100000], "units": list(units),
            "aircraft": list(aircraft), "objectives": [], "players": [],
            "smoke_zones": [], "projectiles": [], "buildings": [],
            "rejections": [], "result": None, "refunds": list(refunds),
            "lasers": []}


def _funit(uid, team=0, x=0, y=0, **kw):
    entry = {"id": uid, "team": team, "pos_cm": [x, y], "hp": 10, "hp_max": 10,
             "category": 1, "name": "u%d" % uid, "stance": "weapons_free",
             "smoke_left": 0, "radar_on": False, "rtb": False,
             "supply_gates": {"share": True, "heal": True, "repair": True,
                              "ammo": True}}
    entry.update(kw)
    return entry


def _fair(aid, team=0, x=0, y=0, **kw):
    entry = {"id": aid, "team": team, "name": "a%d" % aid, "state": "patrol",
             "alt_tier": "mid", "pos_cm": [x, y], "facing": 90, "hp": 10,
             "hp_max": 10, "ammo": {"BOMB": 2}, "paratroop": None,
             "spotted": False, "engage_air": None, "task": None,
             "alt_pending": None, "afterburner": False, "fuel_pct": 100,
             "decoy_left": 2, "evade_active": False, "evade_pct": 0,
             "paratroop_count": 0}
    entry.update(kw)
    return entry


class _SpyCmd:
    """fsm 空令分发的调用面断言桩（calls=[(名, args, kwargs)]）。"""

    def __init__(self):
        self.calls = []

    def _log(self, name, *a, **kw):
        self.calls.append((name, a, kw))
        return [object()]

    def stop(self, ids):
        return self._log("stop", tuple(ids))

    def cancel(self, ids):
        return self._log("cancel", tuple(ids))

    def air_reset(self, ids):
        return self._log("air_reset", tuple(ids))

    def move(self, ids, dest, mode="NORMAL", queue=False):
        return self._log("move", tuple(ids), tuple(dest), mode=mode,
                         queue=queue)

    def smoke(self, ids):
        return self._log("smoke", tuple(ids))

    def sprint(self, ids):
        return self._log("sprint", tuple(ids))

    def stance(self, ids, s):
        return self._log("stance", tuple(ids), s)

    def smoke_sprint_stance(self, ids, stance="HOLD_FIRE"):
        return self._log("smoke_sprint_stance", tuple(ids))

    def reverse(self, ids, dest):
        return self._log("reverse", tuple(ids), tuple(dest))

    def fire_mission(self, uid, point, **kw):
        return self._log("fire_mission", uid, point, **kw)

    def attack(self, uid, foe, queue=False):
        return self._log("attack", uid, foe, queue=queue)

    def sniper_cover(self, ids, foe):
        return self._log("sniper_cover", tuple(ids), foe)

    def supply_dock(self, ids, truck):
        return self._log("supply_dock", tuple(ids), truck)

    def mount(self, ids, carrier):
        return self._log("mount", tuple(ids), carrier)

    def laser_designate(self, ids, foe):
        return self._log("laser_designate", tuple(ids), foe)

    def ground_rtb(self, ids):
        return self._log("ground_rtb", tuple(ids))

    def radar(self, ids, engage):
        return self._log("radar", tuple(ids), engage)

    def air_rtb(self, ids):
        return self._log("air_rtb", tuple(ids))

    def air_alt(self, ids, tier):
        return self._log("air_alt", tuple(ids), tier)

    def air_afterburner(self, ids, engage):
        return self._log("air_afterburner", tuple(ids), engage)

    def air_decoy(self, ids, action="POP"):
        return self._log("air_decoy", tuple(ids), action)

    def air_strike(self, aid, cm, weapon="BOMB", axis=None):
        return self._log("air_strike", aid, tuple(cm), weapon, axis)

    def air_airdrop(self, aid, cm):
        return self._log("air_airdrop", aid, tuple(cm))

    def unload(self, ids, cm=None, building_id=None, queue=False):
        return self._log("unload", tuple(ids), cm, building_id, queue=queue)


# ════════════════════════════════════════════════════════════════════
# ④ 登记面完整性：分区计数/重名/防蒸发
# ════════════════════════════════════════════════════════════════════

class TestSpecRegistry(unittest.TestCase):
    """规格分区在册：36 done／5 deferred／6 manual_silent／2 deviated（终审修复块
    2026-10-13：crit 入 done 46→47＋走样分区 +2→49），零重名。"""

    def test_registry_partition_and_count(self):
        self.assertEqual(len(MANUAL_SPEC), 49)              # 仲裁 46＋crit 补防＋2 走样
        names = [n for _k, n, _r in MANUAL_SPEC]
        self.assertEqual(len(names), len(set(names)))       # 零重名（防增删互抵）
        self.assertEqual((len(SPEC_DONE), len(SPEC_DEFERRED),
                          len(SPEC_MANUAL_SILENT), len(SPEC_DEVIATED)),
                         (36, 5, 6, 2))

    def test_deviated_registered_verbatim(self):
        # 防静默蒸发：走样分区逐名在册（题材/范围硬冲突显式登记——增删任一即红）
        self.assertEqual(
            {n for _k, n, _r in SPEC_DEVIATED},
            {"deviated/SEAD 反辐射博弈", "deviated/设置菜单改键"})

    def test_deferred_registered_verbatim(self):
        # 防静默蒸发：五条后置项逐名在册（增删任一即红）
        self.assertEqual(
            {n for _k, n, _r in SPEC_DEFERRED},
            {"ARTILLERY/弹道被遮拦红显告警",
             "ABILITIES/Active protection system（APS）",
             "HOTKEYS/通讯标记 F1..F4",
             "basics/Income & Upkeep（收入/维护费）",
             "basics/损毁单位回卡组"})

    def test_manual_silent_registered_verbatim(self):
        self.assertEqual(
            {n for _k, n, _r in SPEC_MANUAL_SILENT},
            {"manual_silent/长弹幕遭反击脆弱",
             "manual_silent/Sprint 数值",
             "manual_silent/Smoke 数值",
             "manual_silent/Fast Move『ignoring cover』行为定义",
             "manual_silent/低阻/高阻弹机型配属与导弹目标指定",
             "manual_silent/Force Fire 点地语义与键位"})


# ════════════════════════════════════════════════════════════════════
# ① 键位类：键位表/窗口键名映射/帮助面板/参数条（读表读文本，零 GL）
# ════════════════════════════════════════════════════════════════════

class TestHotkeyTable(unittest.TestCase):
    """手册 HOTKEYS 节键位 ↔ shell_fsm 键位表逐键对表（manual.txt:545-580）。"""

    def test_manual_letter_keys_in_combat_keys_and_a_retired(self):
        # 手册全部战斗字母令在册；A 无手册战斗令→退役归相机（manual.txt:583-588
        # Camera Controls「W, A, S, D    Camera movement」）。
        for k in ("Q", "E", "H", "F", "R", "T", "U", "Z", "X", "C", "V",
                  "B", "N", "P"):
            self.assertIn(k, _fsm_mod.COMBAT_KEYS, k)
        self.assertNotIn("A", _fsm_mod.COMBAT_KEYS)        # A=相机平移非战斗令

    def test_arm_by_key_matches_manual(self):
        # 待令键→待令组与手册逐键对表（Q 攻击移动/T 炮击/R 倒车/F 行军/U 卸载
        # ——manual.txt:560-570；N 照射/P 精密——manual.txt:517-532）。
        self.assertEqual(_fsm_mod._ARM_BY_KEY, {
            "Q": "attack", "T": "fire_mission", "R": "reverse",
            "K": "strike", "O": "drop", "F": "march", "U": "unload",
            "N": "laser", "L": "sniper", "M": "mount", "P": "precision"})

    def test_window_key_names_mirror_and_no_a(self):
        # 窗口键名映射（GL 事件→fsm 键名）与键位表同源镜像；A 不入表（退役）。
        src = _src("sovs/ui/shell_window.py")
        m = re.search(r"def _build_key_names\(.*?\n    return keys", src, re.S)
        self.assertIsNotNone(m, "键名映射表缺失")
        body = m.group(0)
        for k in ("Q", "S", "E", "Z", "X", "R", "T", "G", "H", "K", "O",
                  "F", "U", "N", "V", "B", "J", "Y", "C", "L", "M", "P"):
            self.assertIn("arcade.key.%s: \"%s\"" % (k, k), body, k)
        self.assertNotIn("arcade.key.A: \"A\"", body)

    def test_help_panel_lists_manual_keys(self):
        # F1 帮助面板速查（hud_top 源表）覆盖规格键位面——改面板文案需保键名。
        src = _src("sovs/ui/hud_top.py")
        m = re.search(r"_HELP_KEYS_LEFT = \(.*?def draw_help_overlay",
                      src, re.S)
        self.assertIsNotNone(m)
        help_text = m.group(0)
        for token in ("Q+左键：攻击移动", "E：取消", "H：纪律", "F+左键：行军",
                      "R+左键：倒车", "T+左键/拖拽：炮击", "K+左键/拖拽：空袭",
                      "O+左键拖拽：空投", "X：自卫烟幕", "U：卸载",
                      "N+点敌：激光照射", "P+点地：精密打击", "M+点己方载具：登车",
                      "B：回基地", "C：诱饵", "Z：冲刺/加力/雷达",
                      "Shift+确认：命令入队", "Ctrl+1..9：建组", "TAB：子选",
                      "F1：本面板", "方向键/WASD：平移", "滚轮：缩放"):
            self.assertIn(token, help_text, token)

    def test_fm_panel_buttons_mirror(self):
        # 参数条按钮镜像：弹药三档含 PRECISION（manual.txt:456-458）＋时长
        # ×1/×2/×3＋形态 POINT/LINE/CREEP＋徐进速度档（fm_panel 源表——按钮键
        # 为 "fm_*_%s" 格式串＋值域字面量成对断言）。
        src = _src("sovs/ui/fm_panel.py")
        for token in ('"fm_form_%s" % form', '"fm_ammo_%s" % ammo',
                      '"fm_mult_%d" % mult', '"fm_salvo_%s" % salvo',
                      '"fm_creep_%d" % i',
                      '("POINT", "点目标"), ("LINE", "线形"), ("CREEP", "徐进")',
                      '("HE", "高爆"), ("SMOKE", "烟幕"),',
                      '("PRECISION", "精确")',
                      "for mult in (1, 2, 3):",
                      '("FULL", "全齐射"), ("HALF", "半齐射")',
                      "CREEP_SPEEDS_CM"):
            self.assertIn(token, src, token)
        # 徐进速度档与 fsm 常量同源（值域门共用登记面）
        self.assertEqual(_fsm_mod.CREEP_SPEEDS_CM, (10, 25, 50))

    def test_camera_wasd_arrows_scroll_and_mmb_rotation(self):
        # manual.txt:583-594：滚轮缩放+WASD 平移＋「MMB + Move Camera rotation」
        # ——终审修复块 2026-10-13：MMB 旋转落地（2D 顶视=绕视口中心的视图旋转，
        # scene cm_to_px/px_to_cm 旋转对偶＋窗口 MIDDLE 拖拽）；源表断言三件套。
        scene = _src("sovs/ui/scene.py")
        m = re.search(r"def pan_camera\(.*?\n\n\ndef ", scene, re.S)
        self.assertIsNotNone(m, "pan_camera 缺失")
        body = m.group(0)
        for k in ("arcade.key.W", "arcade.key.A", "arcade.key.S",
                  "arcade.key.D", "arcade.key.UP", "arcade.key.DOWN",
                  "arcade.key.LEFT", "arcade.key.RIGHT"):
            self.assertIn(k, body, k)
        self.assertIn("def rotate_camera(", scene)         # MMB 旋转写点（594 行）
        self.assertIn("def _cam_rot(", scene)              # 旋转角读点（变换对偶）
        win = _src("sovs/ui/shell_window.py")
        self.assertIn("on_mouse_scroll", win)              # 滚轮缩放入窗
        self.assertIn("arcade.MOUSE_BUTTON_MIDDLE", win)   # MMB 拖拽入窗（594 行）

    def test_camera_rotation_transform_roundtrip(self):
        # 旋转变换数学锚（无 GL）：旋转 90° 下 cm_to_px/px_to_cm 互逆、且与
        # 0° 位移正交（东移变南移——旋转真生效非恒等）；鸭子窗零依赖。
        import math
        from sovs.ui import scene as sc

        class _Duck:
            cam_scale, cam_cx, cam_cy, cam_rot = 1.0, 0.0, 0.0, 90.0
            width, height = 1000, 800
            frame = {"map_cm": (200000, 100000)}
            fsm = type("F", (), {"page": "battle"})()

        d = _Duck()
        cx, cy = sc._viewport_center_px(d)
        px = sc.cm_to_px(d, 10000, 0)                      # 视心东 10000cm
        # 屏幕系 y 向下：+90°（顺时针）=东→南=视心下方（py>cy；cos90°≈0 → px≈cx）
        self.assertLess(abs(px[0] - cx), 1e-6)             # x 仍在视心（余弦≈0）
        self.assertGreater(px[1], cy)                      # y 南移=屏幕下方
        back = sc.px_to_cm(d, px[0], px[1])
        self.assertLessEqual(abs(back[0] - 10000), 1)      # 互逆（px→cm 复原）
        self.assertLessEqual(abs(back[1] - 0), 1)
        d.cam_rot = 0.0
        px0 = sc.cm_to_px(d, 10000, 0)
        self.assertAlmostEqual(px0[0], cx + 10000)         # 0° 恒等链（无旋转回归）
        self.assertAlmostEqual(px0[1], cy)


# ════════════════════════════════════════════════════════════════════
# ② ORDERS 语义类（行为锚——真引擎链）
# ════════════════════════════════════════════════════════════════════

class TestOrdersQAttackMove(unittest.TestCase):
    """Q：直奔指定点沿途接战——trail mode=ATTACK＋引擎 MoveCmd(ATTACK)。"""

    def test_q_ground_orders_land_as_attack_move(self):
        w = make_world(21)
        u = add_unit(w, make_unit(w, _truck_tpl(), 0, 0, (500000, 500000)))
        bus = CmdBus(w, 0)
        bus.move([u.id], (600000, 500000), mode="ATTACK")   # Q+点地（fsm 同调面）
        self.assertEqual(bus.trail[-1]["mode"], "ATTACK")   # trail 判据面
        consume_commands(w)
        self.assertIs(u.move_mode, MoveMode.ATTACK)         # 引擎侧攻击前进
        self.assertTrue(u.move_path)


class TestOrdersECancel(unittest.TestCase):
    """E：取消全部命令——航点/队列/炮击任务体/RTB 在途位一并清（manual.txt:357-359）。"""

    def test_cancel_clears_everything(self):
        w = make_world(22)
        u = add_unit(w, make_unit(w, _gun_tpl(), 0, 0, (500000, 500000)))
        u.move_path = [(600000, 500000)]
        u.move_mode = MoveMode.ATTACK
        u.command_queue = [MoveCmd(unit=u, path=[(700000, 500000)],
                                   mode=MoveMode.NORMAL, queue=False)]
        u.fire_mission = FireMission(form=FireMissionForm.POINT,
                                     target_point=(550000, 500000),
                                     shots_left=3)
        u.rtb_pending = True
        queue_command(w, CancelCmd(unit=u))
        consume_commands(w)
        self.assertEqual((u.move_path, u.command_queue, u.fire_mission,
                          u.rtb_pending), ([], [], None, False))
        self.assertTrue(u.alive)                            # 撤令≠消失


class TestOrdersHHoldFire(unittest.TestCase):
    """H：不主动开火仍瞄准；受击开还击窗（manual.txt:364-368）。"""

    def _world(self):
        w = make_world(23)
        u = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (500000, 500000)))
        return w, u

    def test_hold_fire_blocks_fire_but_aims(self):
        w, u = self._world()
        queue_command(w, SetStanceCmd(unit=u, stance=Stance.HOLD_FIRE))
        consume_commands(w)
        self.assertIs(u.stance, Stance.HOLD_FIRE)
        e, ws = u.elements[0], u.elements[0].weapon_states[0]
        self.assertFalse(fire_permitted(w, u, e, ws))            # 拦发射
        self.assertTrue(fire_permitted(w, u, e, ws, aim_phase=True))  # still aim

    def test_fired_upon_opens_return_fire_window(self):
        w, u = self._world()
        u.stance = Stance.HOLD_FIRE
        apply_damage(w, u.elements[0], 1)                        # 受击写还击窗
        self.assertGreaterEqual(u.return_fire_until, w.tick)
        e, ws = u.elements[0], u.elements[0].weapon_states[0]
        self.assertTrue(fire_permitted(w, u, e, ws))             # 窗内可还击


class TestOrdersFFastMove(unittest.TestCase):
    """F：最快路径上公路提速——MARCH 模式落引擎＋道路档源锚（manual.txt:370-374）。"""

    def test_march_mode_lands_and_road_gate_source(self):
        w = make_world(24)
        u = add_unit(w, make_unit(w, _truck_tpl(), 0, 0, (500000, 500000)))
        bus = CmdBus(w, 0)
        bus.move([u.id], (600000, 500000), mode="MARCH")
        self.assertEqual(bus.trail[-1]["mode"], "MARCH")
        consume_commands(w)
        self.assertIs(u.move_mode, MoveMode.MARCH)
        # 道路提速/寻路优先=源锚（『ignoring cover』行为手册未定义→manual_silent 在册）
        mv = _src("sovs/sim/movement.py")
        self.assertIn("prefer_road", mv)
        self.assertIn("move_mode is MoveMode.MARCH", mv)   # 道路档 MARCH 独占


class TestOrdersRReverse(unittest.TestCase):
    """R：倒车直行保前甲——ReverseCmd 归一化 MoveCmd(REVERSE)（manual.txt:376-381）。"""

    def test_reverse_normalizes_to_reverse_mode(self):
        w = make_world(25)
        u = add_unit(w, make_unit(w, _truck_tpl(), 0, 0, (500000, 500000)))
        bus = CmdBus(w, 0)
        bus.reverse([u.id], (450000, 500000))
        consume_commands(w)
        self.assertIs(u.move_mode, MoveMode.REVERSE)        # WHEEL 类 bp 过门4
        self.assertTrue(u.move_path)


class TestOrdersForceFire(unittest.TestCase):
    """Q+点敌：全武器齐射／射程不足不射／未发现敌元素不射／建筑无发现门
    （manual.txt:383-388 逐要素）。"""

    def _shooter(self, w, weapons):
        tpl = UnitTemplate(
            template_id=616, name="mc fort buster", category=4, cost=80,
            element_templates=(ElementTemplate(
                element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                hp_max=20, weapons=tuple(weapons),),),
            optics_ground_cm=50000, stealth_base=5, speed_tier=2,
            movement_class=MovementClass.WHEEL,
            mode_set=(1 << Mode.DIRECT))
        return add_unit(w, make_unit(w, tpl, 0, 0, (500000, 500000)))

    def test_all_weapons_fire_in_range_only(self):
        # 「fire all their weapons」×「insufficient range will not fire」
        w = make_world(26)
        u = self._shooter(w, (
            WeaponTemplate(name="mc gun a", damage=3, max_range_cm=30000,
                           ammo_base=10, salvo=1, damage_type=DamageType.KE,
                           trajectory=Trajectory.DIRECT),
            WeaponTemplate(name="mc gun b", damage=3, max_range_cm=5000,
                           ammo_base=10, salvo=1, damage_type=DamageType.KE,
                           trajectory=Trajectory.DIRECT)))
        foe = add_unit(w, make_unit(w, _rifle_tpl(), 1, 1, (520000, 500000)))
        foe.spotted_mask = 1 << 0                           # 已发现（2 万 cm 内）
        cmd_attack(w, u.elements[0], foe.elements[0])
        states = [ws.state for ws in u.elements[0].weapon_states]
        self.assertEqual(states, [WState.AIMING, WState.READY])  # ②射程外不射

    def test_unspotted_element_rejected_building_passes(self):
        # 门④发现门仅作用于元素目标；建筑无发现门——「suspicious buildings even
        # if no enemy is spotted」＋攻坚资格门（vs_fort）。
        w = make_world(27)
        u = self._shooter(w, (
            WeaponTemplate(name="mc heat", damage=8, max_range_cm=30000,
                           ammo_base=10, salvo=1, damage_type=DamageType.HE,
                           trajectory=Trajectory.DIRECT,
                           vs_fort_mult_permille=4000),))
        foe = add_unit(w, make_unit(w, _rifle_tpl(), 1, 1, (520000, 500000)))
        cmd_attack(w, u.elements[0], foe.elements[0])       # 未发现（mask=0）
        self.assertEqual(u.elements[0].weapon_states[0].state, WState.READY)
        b = Building(id=1, pos=(520000, 500000), hp=100)    # 建筑无 spotted 概念
        w.buildings.append(b)
        cmd_attack(w, u.elements[0], b)
        self.assertEqual(u.elements[0].weapon_states[0].state, WState.AIMING)


class TestOrdersBReturnToBase(unittest.TestCase):
    """B：快移出生点→消失退款（损伤/耗弹扣减≥20%＋舱载连带）（manual.txt:390-400）。"""

    def test_arrival_refund_and_disappear(self):
        w = make_world(28)
        u = add_unit(w, make_unit(w, _truck_tpl(50), 0, 0, (500000, 50000)))
        pts0 = w.players[0].points
        self.assertTrue(cmd_ground_rtb(w, u))
        self.assertTrue(u.rtb_pending)
        for _ in range(4000):
            world_tick(w)
            if not u.alive:
                break
        self.assertFalse(u.alive)                          # 到场消失
        self.assertEqual(w.players[0].points, pts0 + 50)   # 退款到账
        self.assertEqual(w.refund_log[-1]["amount"], 50)

    def test_damage_ammo_deduction_with_floor(self):
        # basics:179-180：按损伤/耗弹扣减、不低于原价 20%
        w = make_world(28)
        u = add_unit(w, make_unit(w, _truck_tpl(100), 0, 0, (500000, 50000)))
        for e in u.elements:
            e.hp_current = e.template.hp_max // 2          # 损 50%
        self.assertEqual(unit_refund_points(u), 50)
        for e in u.elements:
            e.weapon_states[0].ammo_left = 0               # 弹尽→触底
        self.assertEqual(unit_refund_points(u),
                         100 * CONFIG.rtb_refund_floor_permille // 10000)

    def test_cargo_units_refunded_together(self):
        # manual.txt:399-400：载具内单位与补给一并退款
        w = make_world(28)
        carrier = add_unit(w, make_unit(w, _truck_tpl(50), 0, 0,
                                        (500000, 50000)))
        rider = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (500000, 50000)))
        carrier.elements[0].cargo_units = [rider]
        pts0 = w.players[0].points
        self.assertEqual(ground_recovery(w, carrier), 80)  # 50+30
        self.assertEqual(w.players[0].points, pts0 + 80)
        self.assertFalse(rider.alive)


class TestOrdersUUnload(unittest.TestCase):
    """U：点地卸载/连按 U 就地立即卸载（manual.txt:402-407,567-568）。"""

    def _fsm(self):
        f = _fsm_mod.ShellFsm()
        f.start_deploy()
        f.on_frame(_frame(units=[_funit(1)]))
        return f

    def test_double_press_unloads_in_place(self):
        f = self._fsm()
        f.select_units([1])
        self.assertEqual(f.key("U"), "arm:unload")         # 首按=待令
        cmd = _SpyCmd()
        self.assertEqual(f.key("U", cmd=cmd), "unload_now")  # 再按=就地立即卸载
        self.assertEqual(cmd.calls[0][0], "unload")
        self.assertIsNone(cmd.calls[0][1][1])              # cm=None（仅 DismountCmd）
        self.assertIsNone(f.armed_order)

    def test_cmd_bus_unload_enqueues_dismount(self):
        w = make_world(29)
        u = add_unit(w, make_unit(w, _truck_tpl(), 0, 0, (500000, 500000)))
        bus = CmdBus(w, 0)
        cmds = bus.unload([u.id], (510000, 500000))
        self.assertTrue(any(isinstance(c, DismountCmd) for c in cmds))


# ════════════════════════════════════════════════════════════════════
# ② AIRCRAFT 语义类
# ════════════════════════════════════════════════════════════════════

def _strafe_air(w, team=0, shots=6):
    """带 STRAFE 档（DIRECT∧KE∧GROUND=weapon_slot 判据）的攻击机。"""
    tpl = _air_tpl(template_id=697, role=AirRole.FIGHTER, weapons=(
        (WeaponTemplate(name="mc mg", damage=2, max_range_cm=20000,
                        ammo_base=shots, salvo=shots,
                        target_mask=TargetDomain.GROUND,
                        trajectory=Trajectory.DIRECT, damage_type=DamageType.KE,
                        accuracy_base_bp=10000,
                        projectile_speed_cm_tick=4000), shots),))
    a = _mk_air(w, tpl, team=team)
    a.ammo_left = {"STRAFE": shots}
    return a


class TestAircraftKStrafeRun(unittest.TestCase):
    """K：航炮/火箭沿全航道无差别射＋画攻击轴定位置朝向（manual.txt:411-418）。"""

    def test_guns_fire_indiscriminately_with_zero_enemies(self):
        # 「fired indiscriminately along the entire length」取严修正的行为锚：
        # 走廊内零敌元素也照样开火耗弹（旧『逐目标 salvo』实现下零目标=零耗弹）。
        w = make_world(30)
        a = _strafe_air(w)
        task = AirTask(kind=TaskKind.STRIKE, weapon="STRAFE",
                       target=(500000, 500000), phase=StrikePhase.RUN,
                       run_start=(450000, 500000), run_end=(550000, 500000))
        resolve_strafe(w, a, task)
        self.assertEqual(a.ammo_left["STRAFE"], 0)         # 全弹沿航道泼洒

    def test_drawn_axis_fixes_run_orientation(self):
        # 拖拽画线=一次性确定打击位置与航线走向（axis[0]→axis[1]=攻击方向）
        w = make_world(30)
        a = _strafe_air(w)
        self.assertTrue(cmd_air_strike(w, a, (500000, 500000), "STRAFE",
                                       axis=((480000, 480000),
                                             (520000, 520000))))
        t = a.task
        self.assertIsNotNone(t)
        # run 轴沿玩家线向、以 target 为心对称（strafe_run_lead_cm 半长）
        mid = ((t.run_start[0] + t.run_end[0]) // 2,
               (t.run_start[1] + t.run_end[1]) // 2)
        self.assertEqual(mid, (500000, 500000))
        self.assertGreater(t.run_end[0], t.run_start[0])   # 走向=画线方向


class TestAircraftVLowAltitude(unittest.TestCase):
    """V：两态 toggle（降→恢复）＋低空降速＋按角色出场高度（manual.txt:421-428）。"""

    def test_two_state_toggle_in_fsm(self):
        f = _fsm_mod.ShellFsm()
        f.start_deploy()
        f.on_frame(_frame(aircraft=[_fair(7, alt_tier="mid")]))
        f.select_aircraft([7])
        cmd = _SpyCmd()
        f.key("V", cmd=cmd)                                # MID→LOW
        self.assertEqual([c[1][1] for c in cmd.calls
                          if c[0] == "air_alt"], ["LOW"])
        f.on_frame(_frame(aircraft=[_fair(7, alt_tier="low")]))
        f.select_aircraft([7])
        f.key("V", cmd=cmd)                                # LOW→恢复出场层
        self.assertEqual([c[1][1] for c in cmd.calls
                          if c[0] == "air_alt"], ["LOW", "MID"])

    def test_fighter_enters_high_low_slows(self):
        # 「fighters will be high」＋「reducing their speed」
        self.assertIs(entry_tier(AltTier.HIGH, AirRole.FIGHTER), AltTier.HIGH)
        self.assertIs(entry_tier(AltTier.MID, AirRole.BOMBER), AltTier.MID)
        w = make_world(31)
        a = _mk_air(w, _air_tpl())
        a.alt_tier = AltTier.LOW
        a.flight_plan = [(a.pos[0] + 10000, a.pos[1])]
        x0 = a.pos[0]
        aircraft_move_step(w, a)
        self.assertEqual(a.pos[0] - x0,
                         a.template.speed_cm_tick
                         * CONFIG.alt_low_speed_mult_bp // 10000)


class TestAircraftOAirdrop(unittest.TestCase):
    """O：逐一跳伞费一次＋无令货机到场自动空投（manual.txt:430-440）。"""

    def _transport(self):
        return AircraftTemplate(
            template_id=698, name="MCTwin", role=AirRole.TRANSPORT,
            cost_body=40, hp_max=80, armor_aa=2, speed_cm_tick=100,
            dogfight_power=1, maneuver=4, alt_ceiling=AltTier.MID,
            payload_max_supply=150, paratroop_seats=2, turret_damage=2,
            payload_price={"SUPPLY": 1})

    def test_sticks_one_by_one_single_fee(self):
        # 「jump out one by one」：两份装载=两个落点，投放费一次
        w = make_world(32, phase=1)
        ground_tpl = _rifle_tpl()
        w.players[0].deck_slots = [DeckSlot(ground_tpl, 2)]
        a = _air_mod.cmd_air_call(w, w.players[0], self._transport(),
                                  {"PARATROOP": ground_tpl,
                                   "PARATROOP_COUNT": 2})
        self.assertIsNotNone(a)
        self.assertEqual(a.paratroop_left, 2)
        pts0 = w.players[0].air_points
        task = AirTask(kind=TaskKind.AIRDROP, drop=(500000, 500000))
        resolve_airdrop(w, a, task)
        resolve_airdrop(w, a, task)
        self.assertEqual(len([u for u in w.units
                              if u.template is ground_tpl]), 2)
        self.assertIsNone(a.paratroop_cargo)               # 投毕清舱
        self.assertEqual(w.players[0].air_points,
                         max(0, pts0 - CONFIG.airdrop_fee_points))

    def test_auto_drop_scheduled_on_arrival_and_cleared_by_order(self):
        # 「given no other orders, cargo planes will automatically airdrop …
        # at the call-in point」：到场排程、显式令撤销
        from sovs.sim.air import cmd_air_move
        w = make_world(32, phase=1)
        ground_tpl = _rifle_tpl()
        w.players[0].deck_slots = [DeckSlot(ground_tpl, 1)]
        a = _air_mod.cmd_air_call(w, w.players[0], self._transport(),
                                  {"PARATROOP": ground_tpl,
                                   "PARATROOP_COUNT": 1})
        a.state = AirState.INBOUND
        a.flight_plan = []                                 # 到场拍（INBOUND 无航路）
        aircraft_move_step(w, a)
        self.assertEqual(a.auto_drop_tick,
                         w.tick + CONFIG.airdrop_auto_delay_ticks)
        cmd_air_move(w, a, [(400000, 400000)])             # 玩家显式令
        self.assertEqual(a.auto_drop_tick, 0)


class TestAircraftLimits(unittest.TestCase):
    """飞机限制：不能图上补给（弹尽自动 RTB）／燃油耗尽弹射／观地仅侦察
    （basics:311-314）。"""

    def test_auto_rtb_when_payload_empty(self):
        w = make_world(33)
        a = _mk_air(w, _air_tpl(payload_max_supply=10))
        a.ammo_left = {"SUPPLY": 0}                        # 投送毕
        a.paratroop_cargo = None
        a.state = AirState.PATROL
        _air_mod.aircraft_tick(w)
        self.assertIs(a.state, AirState.RTB)               # 自动回基地

    def test_fuel_eject_on_burnout(self):
        # basics:312-314：耗尽前不 RTB→被迫跳伞（air_downed 同链=冷却入账）
        w = make_world(33)
        a = _mk_air(w, _air_tpl(can_afterburner=True))
        a.fuel_ticks = 1
        a.afterburner = True
        aircraft_move_step(w, a)
        self.assertNotIn(a, w.aircraft)                    # 弹射移除
        self.assertGreater(
            w.players[a.player_index].air_cooldowns[a.template.template_id],
            w.tick)

    def test_only_recon_marks_ground(self):
        # 「They do not see ground units on their own」：观地=RECON 角色专属
        #（侦察机 LOW+基准速=标记概率 10000bp 确定性；战斗机角色门直接跳过）
        w = make_world(33)
        foe = add_unit(w, make_unit(w, _rifle_tpl(), 1, 1, (500000, 500000)))
        _mk_air(w, _air_tpl(), team=0, pos=(500000, 500000))   # 战斗机
        _air_mod.air_recon_step(w)
        self.assertEqual(foe.spotted_mask, 0)              # 战斗机观不见地
        _mk_air(w, _air_tpl(template_id=699, role=AirRole.RECON,
                            optics_air_cm=500000,
                            recon_mark_base_bp=10000),
                team=0, alt=AltTier.LOW, pos=(500000, 500000))
        _air_mod.air_recon_step(w)
        self.assertEqual(foe.spotted_mask, 1 << 0)         # 侦察机标记 SPOTTED


# ════════════════════════════════════════════════════════════════════
# ② ARTILLERY 语义类
# ════════════════════════════════════════════════════════════════════

class TestArtilleryFireMission(unittest.TestCase):
    """T 三段式全参＋弹药档三门＋时长档 shots 式＋形态三档＋超程进位。"""

    def _gun(self, w, pos, tpl=None):
        u = add_unit(w, make_unit(w, tpl or _gun_tpl(), 0, 0, pos))
        queue_command(w, SetModeCmd(element=u.elements[0],
                                    mode=Mode.INDIRECT))
        consume_commands(w)
        return u

    def test_ammo_domain_gate_and_duration_formula(self):
        # 值域门（HE|SMOKE|PRECISION）＋「a longer barrage … use more ammo」：
        # shots = N炮 × ammo_base × ammo_mult（HALF=⌈N/2⌉——仲裁规格 done 面锚）
        w = make_world(34)
        u = self._gun(w, (500000, 500000))
        self.assertFalse(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                          (560000, 500000), 1, "AP", None, 0))
        self.assertTrue(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                         (560000, 500000), 1, "HE", None, 0))
        self.assertEqual(u.fire_mission.shots_left, 60)    # 1炮×60×1
        self.assertTrue(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                         (560000, 500000), 3, "HE", None, 0))
        self.assertEqual(u.fire_mission.shots_left, 180)   # ×3 时长档

    def test_smoke_gate_requires_smoke_weapon_row(self):
        # ② 烟档门：无 SMOKE 武器行的卡组任务被拒；带烟档放行
        w = make_world(34)
        u = self._gun(w, (500000, 500000))
        self.assertFalse(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                          (560000, 500000), 1, "SMOKE",
                                          None, 0))
        u2 = self._gun(w, (500000, 500000), tpl=_gun_tpl(smoke_row=True))
        self.assertTrue(cmd_fire_mission(w, u2, FireMissionForm.POINT,
                                         (560000, 500000), 1, "SMOKE",
                                         None, 0))
        self.assertEqual(u2.fire_mission.ammo, "SMOKE")

    def test_line_creep_forms_store_geometry(self):
        # 弹幕模式：LINE=车道、CREEP=沿画线路径逐段推进（creep 速度档透传）
        w = make_world(34)
        u = self._gun(w, (500000, 500000))
        line = ((540000, 480000), (600000, 480000))
        self.assertTrue(cmd_fire_mission(w, u, FireMissionForm.LINE, line,
                                         1, "HE", None, 0))
        self.assertEqual(u.fire_mission.target_line, line)
        self.assertTrue(cmd_fire_mission(
            w, u, FireMissionForm.CREEP, line, 1, "HE", None, 25))
        self.assertEqual(u.fire_mission.creep_speed_cm_tick, 25)

    def test_out_of_range_auto_approach(self):
        # manual.txt:471-474：超程炮自动前移到最大射程处再开火
        w = make_world(34)
        u = self._gun(w, (100000, 50000))                  # 距目标 40 万≫10 万
        self.assertFalse(u.move_path)
        self.assertTrue(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                         (500000, 50000), 1, "HE", None, 0))
        self.assertTrue(u.fire_mission)
        self.assertTrue(u.move_path)                       # standoff 进位航点已插

    def test_precision_gate_and_landing_on_laser(self):
        # PRECISION 第三弹药位：无激光位拒；有激光位落弹着点于照射位（紧散射）
        from sovs.sim.tick import fire_at
        w = make_world(34)
        sniper = add_unit(w, make_unit(w, _sniper_tpl(), 0, 0,
                                       (500000, 60000)))
        foe = add_unit(w, make_unit(w, _rifle_tpl(), 1, 1, (500000, 90000)))
        gun = self._gun(w, (500000, 30000))
        self.assertFalse(cmd_fire_mission(w, gun, FireMissionForm.POINT,
                                          foe.pos, 1, "PRECISION", None, 0))
        self.assertTrue(cmd_laser_designate(w, sniper, foe))
        self.assertEqual(laser_marks_of(w, 0)[0][0], foe.pos)   # 照射跟随目标
        self.assertTrue(cmd_fire_mission(w, gun, FireMissionForm.POINT,
                                         foe.pos, 1, "PRECISION", None, 0))
        self.assertEqual(gun.fire_mission.ammo, "PRECISION")
        gun.elements[0].weapon_states[0].state = WState.READY
        fire_at(w, gun.elements[0], gun.elements[0].weapon_states[0],
                gun.fire_mission)
        self.assertTrue(w.projectiles)
        for p in w.projectiles:                            # 落点=激光位±紧散射
            d = abs(p.dest[0] - foe.pos[0]) + abs(p.dest[1] - foe.pos[1])
            self.assertLessEqual(
                d, 2 * (2000 * CONFIG.precision_scatter_bp // 10000) + 1)


# ════════════════════════════════════════════════════════════════════
# ② ABILITIES 语义类
# ════════════════════════════════════════════════════════════════════

class TestAbilitySprint(unittest.TestCase):
    """Z 冲刺：提速窗＋冷却门＋冲刺禁射＋破压制减半（manual.txt:487-490）。"""

    def test_sprint_window_cooldown_nofire_suppression_cut(self):
        w = make_world(35)
        u = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (500000, 500000)))
        e, ws = u.elements[0], u.elements[0].weapon_states[0]
        self.assertTrue(fire_permitted(w, u, e, ws))       # 基线可射
        e.suppression = 80
        cmd_sprint(w, u)
        self.assertEqual(u.sprint_until,
                         w.tick + CONFIG.sprint_duration_ticks)
        self.assertFalse(fire_permitted(w, u, e, ws))      # ⑦ 冲刺禁射
        self.assertEqual(e.suppression, 40)                # 破压制减半
        t0 = u.sprint_until
        e.suppression = 80
        cmd_sprint(w, u)                                   # 冷却窗内再令
        self.assertEqual(u.sprint_until, t0)               # 不刷新（冷却门）
        self.assertEqual(e.suppression, 80)                # 且无副作用


class TestAbilityAfterburner(unittest.TestCase):
    """Z 加力：×2 速度/×2 油耗 toggle＋无资格拒（manual.txt:492-497）。"""

    def test_toggle_speed_and_fuel(self):
        w = make_world(36)
        a = _mk_air(w, _air_tpl(can_afterburner=True, speed_cm_tick=100))
        b = _mk_air(w, _air_tpl(template_id=700), team=1)
        self.assertFalse(cmd_air_afterburner(w, b, True))  # 无资格机型拒
        self.assertTrue(cmd_air_afterburner(w, a, True))
        a.flight_plan = [(a.pos[0] + 200, a.pos[1])]
        aircraft_move_step(w, a)
        self.assertEqual(a.pos[0], 500000 + 200)           # 100×2 预算整步到
        self.assertEqual(a.fuel_ticks, CONFIG.air_fuel_ticks - 2)  # 油耗×2
        self.assertTrue(cmd_air_afterburner(w, a, False))  # 再按 Z 关闭
        self.assertFalse(a.afterburner)


class TestAbilitySmoke(unittest.TestCase):
    """X 烟幕：手动投放发数门/冷却门＋延迟落烟＋导弹来袭事件口（manual.txt:499-503）。"""

    def test_manual_pop_delayed_zone_and_charges(self):
        w = make_world(37)
        u = add_unit(w, make_unit(w, _truck_tpl(), 0, 0, (500000, 500000)))
        e = u.elements[0]
        e.self_smoke_left = 2
        self.assertTrue(cmd_smoke(w, e, e.pos))
        self.assertEqual(e.self_smoke_left, 1)             # 发数有限
        self.assertFalse(cmd_smoke(w, e, e.pos))           # 冷却窗内拒
        for _ in range(CONFIG.self_smoke_delay_ticks + 1):
            world_tick(w)
        self.assertEqual(len(w.smoke_zones), 1)            # 延迟落烟成区遮断

    def test_missile_warning_auto_pops_ground_smoke(self):
        # 「Triggers automatically if a missile is fired on the unit」：
        # 统一事件口直调（1944 无对地导弹→无生产调用点，接线留痕 manual_silent）
        w = make_world(37)
        u = add_unit(w, make_unit(w, _truck_tpl(), 0, 0, (500000, 500000)))
        u.elements[0].self_smoke_left = 2
        missile_warning(w, u)
        self.assertEqual(u.elements[0].self_smoke_left, 1)


class TestAbilityDecoy(unittest.TestCase):
    """C 诱饵：手动投放/发数门/规避窗＋被瞄准自动减弹药（manual.txt:505-509）。"""

    def test_manual_and_auto_pop(self):
        from sovs.sim.tick import begin_aim, fire_aa
        w = make_world(38)
        a = _mk_air(w, _air_tpl(decoy_charges=2))
        self.assertTrue(cmd_air_decoy(w, a, "POP"))
        self.assertEqual((a.decoy_left, a.evade_until),
                         (1, w.tick + CONFIG.decoy_evade_ticks))
        self.assertTrue(cmd_air_decoy(w, a, "AUTO_ON"))    # 自动档开
        self.assertTrue(a.decoy_auto)
        # 对空弹发射拍=「导弹来袭」事件源→自动投放（fire_aa 消费规避窗）
        aa = add_unit(w, make_unit(w, _aa_tpl(optics_air=50000, rng=50000),
                                   0, 0, (500000, 500000)))
        ws = aa.elements[0].weapon_states[0]
        begin_aim(aa.elements[0], ws, a)
        fire_aa(w, aa.elements[0], ws, a)
        self.assertEqual(a.decoy_left, 0)                  # 自动再投一发
        self.assertFalse(cmd_air_decoy(w, a, "POP"))       # 发数尽拒


class TestAbilityRadar(unittest.TestCase):
    """Z 雷达：资格门＋5s 启动＋即刻关＋对空探测/射程增幅（basics:327-335）。"""

    def test_gate_spinup_off_and_range_mult(self):
        w = make_world(39)
        u = add_unit(w, make_unit(w, _aa_tpl(), 0, 0, (500000, 500000)))
        rifle = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (510000, 500000)))
        self.assertFalse(cmd_radar(w, rifle, True))        # 非对空资格拒
        self.assertTrue(cmd_radar(w, u, True))
        self.assertFalse(radar_active(u, w))               # 启动窗内未生效
        for _ in range(CONFIG.radar_spinup_ticks):
            world_tick(w)
        self.assertTrue(radar_active(u, w))
        self.assertEqual(radar_range_mult(u, w, AltTier.HIGH),
                         CONFIG.radar_mult_high_bp)        # 高空×2
        self.assertEqual(radar_range_mult(u, w, AltTier.LOW),
                         CONFIG.radar_mult_low_bp)         # 低空+25%
        cmd_radar(w, u, False)
        self.assertFalse(radar_active(u, w))               # 关=即刻
        self.assertEqual(radar_range_mult(u, w, AltTier.HIGH), 10000)


class TestAbilityPassiveCountermeasures(unittest.TestCase):
    """被动对策：规避乘区降对空弹命中（basics:353-356）。"""

    def test_passive_evade_reduces_hit(self):
        # 确定性对照：满命中机型必中、10000bp 被动对策机型必不中
        from sovs.sim.tick import begin_aim, fire_aa
        for tpl, expect_hit in (
                (_air_tpl(hp_max=1000, armor_aa=1), True),
                (_air_tpl(template_id=701, hp_max=1000, armor_aa=1,
                          passive_evade_bp=10000), False)):
            w = make_world(40)
            aa = add_unit(w, make_unit(w, _aa_tpl(optics_air=50000,
                                                  rng=50000, acc_bp=10000),
                                       0, 0, (500000, 500000)))
            ws = aa.elements[0].weapon_states[0]
            a = _mk_air(w, tpl, team=1)
            begin_aim(aa.elements[0], ws, a)
            fire_aa(w, aa.elements[0], ws, a)
            self.assertEqual(bool([p for p in w.projectiles if p.will_hit]),
                             expect_hit, tpl.name)


class TestBasicsCriticalEffects(unittest.TestCase):
    """严重损伤四类暴击（basics:214-230＋manual.txt:339-341——终审修复块恢复
    D071 拆除面）：四类产出/概率随伤害/只升不降/步兵轻AT必暴击/修满移除。"""

    def _tank_tpl(self, template_id=617, **kw):
        d = dict(template_id=template_id, name="mc crit tank", category=2,
                 cost=100,
                 element_templates=(ElementTemplate(
                     element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                     hp_max=30, weapons=(),),),
                 optics_ground_cm=20000, stealth_base=5, speed_tier=2,
                 movement_class=MovementClass.TRACK)
        d.update(kw)
        return UnitTemplate(**d)

    def test_four_slots_produced_and_upgrade_only_up(self):
        # below(4) 四类等权产出＋NONE→MINOR→MAJOR 只升不降（basics:222-224）
        from sovs.sim.combat import roll_crit, upgrade_crit
        from sovs.sim.types import CritLevel, CritSlot
        w = make_world(47)
        u = add_unit(w, make_unit(w, self._tank_tpl(), 0, 0, (500000, 500000)))
        e = u.elements[0]
        probe = WeaponTemplate(name="mc probe", damage=1, max_range_cm=10000)
        # 大伤害（dmg≥9）→ prob 饱和 10000 → 必暴击；反复命中四槽逐渐出齐
        for _ in range(60):
            roll_crit(w, e, 10, probe)
        self.assertEqual(set(e.crit), {CritSlot.FC, CritSlot.SEN,
                                       CritSlot.RLD, CritSlot.MOB})  # 四类全出
        # 只升不降：已 MAJOR 的槽再掷保持 MAJOR
        e.crit[CritSlot.FC] = CritLevel.MAJOR
        for _ in range(10):
            roll_crit(w, e, 10, probe)
        self.assertIs(e.crit[CritSlot.FC], CritLevel.MAJOR)

    def test_infantry_light_at_guaranteed_crit_data_and_zero_pen(self):
        # manual.txt:339-341：步兵轻 AT（本作=铁拳×2/PTRS 反坦克枪——数据位
        # crit_guaranteed=True）对车辆必暴击，穿深不足跳弹 0 伤亦触发
        from sovs.sim.combat import roll_guaranteed_crit
        from sovs.sim.types import CritLevel
        from sovs.sim.card_loader import load_library
        lib = load_library(os.path.join(_ROOT, "data/gen/cards_ground.v1.json"))
        marked = set()
        for rec in lib.values():
            for et in rec.unit_template.element_templates:
                for wt in et.weapons:
                    if wt.crit_guaranteed:
                        marked.add(wt.name)
        self.assertEqual(marked, {"铁拳", "PTRS反坦克枪"})  # 数据位恰三行两名录
        w = make_world(47)
        u = add_unit(w, make_unit(w, self._tank_tpl(), 0, 0, (500000, 500000)))
        e = u.elements[0]
        roll_guaranteed_crit(w, e)
        self.assertEqual(len(e.crit), 1)                    # 单次命中=恰一槽必暴
        infantry = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (500000, 500000)))
        roll_guaranteed_crit(w, infantry.elements[0])
        self.assertEqual(infantry.elements[0].crit, {})     # 非车辆无暴击槽门

    def test_full_repair_removes_crits(self):
        # basics:204「Once a unit is fully repaired the critical effects are also
        # removed」——system_supply 恢复门口子④：修满 crit.clear()（恢复后真吃值）
        from sovs.sim.types import CritLevel, CritSlot
        w = make_world(47, phase=1)
        repair = add_unit(w, make_unit(w, self._tank_tpl(
            618, repair_power_hp_per_tick=2), 0, 0,
            (500000, 500000)))                           # 维修车（R-19：repair_power>0）
        tank = add_unit(w, make_unit(w, self._tank_tpl(), 0, 0, (501000, 500000)))
        e = tank.elements[0]
        e.hp_current = 10                                   # 带伤＋带暴击
        e.crit[CritSlot.MOB] = CritLevel.MAJOR
        w.await_resupply.append(tank)
        for _ in range(400):
            world_tick(w)
            if e.hp_current >= e.template.hp_max:
                break
        self.assertEqual(e.hp_current, e.template.hp_max)   # 修满
        self.assertEqual(e.crit, {})                        # 暴击随之移除

    def test_mob_crit_slows_and_sticks(self):
        # basics:229-230 Mobility：MINOR 减速/MAJOR 趴窝（速度链乘区恢复）
        from sovs.sim.movement import move_speed_cm_tick
        from sovs.sim.types import CritLevel, CritSlot
        w = make_world(47)
        u = add_unit(w, make_unit(w, self._tank_tpl(), 0, 0, (500000, 500000)))
        v0 = move_speed_cm_tick(CONFIG, u, 0)
        u.elements[0].crit[CritSlot.MOB] = CritLevel.MINOR
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0),
                         v0 * CONFIG.crit_mob_minor_mult_bp // 10000)
        u.elements[0].crit[CritSlot.MOB] = CritLevel.MAJOR
        self.assertEqual(move_speed_cm_tick(CONFIG, u, 0), 0)   # totally stuck


class TestDeviatedRegistrations(unittest.TestCase):
    """走样分区锚（终审修复块 2026-10-13）：题材/范围硬冲突的已落地近似面＋
    不存在锚双证——防半吊子悄悄长出，也防登记蒸发。"""

    def test_sead_cut_anchors(self):
        # 已落地近似面：雷达开机=可视易损（radar_on 进状态帧——敌我共见）
        self.assertIn("radar_on", _src("sovs/sim/state_frame.py"))
        # 不存在锚：1944 无反辐射弹种——sim 全目录无反辐射武器标识符/寻的语义
        #（注释正文合法提及「SEAD」题材词——判据=标识符级非子串级）
        sim = "".join(_src(os.path.join("sovs/sim", f))
                      for f in os.listdir(os.path.join(_ROOT, "sovs/sim"))
                      if f.endswith(".py"))
        self.assertIsNone(re.search(r"\banti_radiation\b|\bradiation_seek", sim))
        self.assertIsNone(re.search(r"\bSEAD_[A-Za-z]|\bsead_[a-z]", sim))
        # 关机脱锁语义的对空弹非辐射寻的（命中判定无 radar_on 因子——负锚）
        self.assertNotIn("radar_on", _src("sovs/sim/air.py"))

    def test_settings_rebind_absent(self):
        # 菜单章节功能在六件需求之外：无 settings/rebind 入口（负锚）；键位表=
        # 源码级常量（改键=改 COMBAT_KEYS 源，无运行时改键面）
        for rel in ("sovs/ui/shell_window.py", "sovs/ui/shell_fsm.py"):
            src = _src(rel)
            self.assertNotIn("rebind", src.lower(), rel)
            self.assertNotIn("settings_menu", src.lower(), rel)


# ════════════════════════════════════════════════════════════════════
# ② HOTKEYS/basics 语义类（TAB/SHIFT/CTRL/部署/出生/呼援/登车/补给）
# ════════════════════════════════════════════════════════════════════

class TestHotkeyTabSubSelection(unittest.TestCase):
    """TAB 子选：只对焦点单位下令、选区不散（basics:59-60）。"""

    def test_focus_filter_keeps_selection(self):
        f = _fsm_mod.ShellFsm()
        f.start_deploy()
        f.on_frame(_frame(units=[_funit(1), _funit(2), _funit(3)]))
        f.select_units([1, 2, 3])
        f.key("Q")
        cmd = _SpyCmd()
        f.execute_armed_unit(9, cmd, enemy=True)
        self.assertEqual(sorted(c[1][0] for c in cmd.calls
                                if c[0] == "attack"), [1, 2, 3])  # 全选区
        f.key("TAB")                                       # 焦点→2
        f.key("Q")
        cmd = _SpyCmd()
        f.execute_armed_unit(9, cmd, enemy=True)
        self.assertEqual([c[1][0] for c in cmd.calls if c[0] == "attack"],
                         [2])                              # 仅焦点下令
        self.assertEqual(f.selected, (1, 2, 3))            # 「without losing」


class TestHotkeyShiftQueue(unittest.TestCase):
    """SHIFT=Queue orders：命令入单位级链尾排队、即发新令清链（manual.txt:551）。"""

    def test_move_queue_lands_in_command_queue(self):
        w = make_world(41)
        u = add_unit(w, make_unit(w, _truck_tpl(), 0, 0, (500000, 500000)))
        bus = CmdBus(w, 0)
        bus.move([u.id], (510000, 500000))                 # 先即发一条
        consume_commands(w)
        self.assertTrue(u.move_path)
        bus.move([u.id], (520000, 500000), queue=True)     # Shift=排队
        consume_commands(w)
        self.assertEqual(len(u.command_queue), 1)          # 入链尾不即执行
        self.assertEqual(u.command_queue[0].path[-1], (520000, 500000))
        bus.move([u.id], (530000, 500000))                 # 新即发令=清链（GAP-18）
        consume_commands(w)
        self.assertEqual(u.command_queue, [])
        self.assertEqual(u.move_path[-1], (530000, 500000))

    def test_attack_queue_flag_passthrough(self):
        # Q+Shift+点敌=齐射入队（AttackCmd queue 位透传）
        from sovs.sim.tick import AttackCmd
        w = make_world(41)
        u = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (500000, 500000)))
        foe = add_unit(w, make_unit(w, _rifle_tpl(), 1, 1, (510000, 500000)))
        bus = CmdBus(w, 0)
        cmds = bus.attack(u.id, foe.id, queue=True)
        self.assertEqual(bus.trail[-1]["kind"], "attack")
        self.assertEqual(len(cmds), 1)
        self.assertIsInstance(cmds[0], AttackCmd)
        self.assertTrue(cmds[0].queue)                     # 入队位真透传


class TestHotkeyCtrlGroups(unittest.TestCase):
    """CTRL+1-9 编组／数字取组（manual.txt:554）。"""

    def test_assign_and_recall(self):
        f = _fsm_mod.ShellFsm()
        f.start_deploy()
        f.on_frame(_frame(units=[_funit(1), _funit(2)]))
        f.select_units([1, 2])
        self.assertEqual(f.key("5", ctrl=True), "group_assign")
        self.assertEqual(f.groups[5], ((1, 2), ()))
        f.clear_selection()
        self.assertEqual(f.key("5"), "group_recall")
        self.assertEqual(f.selected, (1, 2))               # 剪尸后取组


class TestBasicsDeployment(unittest.TestCase):
    """部署暂停 60s＋逐个出生＋幽灵表示（basics:158-163）。"""

    def test_deploy_pause_600_ticks(self):
        self.assertEqual(_fsm_mod.DEPLOY_TICKS_IMPL, 600)
        self.assertEqual(CONFIG.phase_ticks[0], 600)       # tables 实现现值锚

    def test_units_spawn_one_by_one_fifo(self):
        w = make_world(42, phase=PHASE_DEPLOY)
        p = w.players[0]
        p.points = 200
        tpl = _rifle_tpl()
        p.deck_slots = [DeckSlot(tpl, 2)]
        self.assertTrue(cmd_purchase(w, p, tpl))
        self.assertTrue(cmd_purchase(w, p, tpl))
        counts = []
        for _ in range(120):
            world_tick(w)
            counts.append(len([u for u in w.units
                               if u.template is tpl]))
        # 逐个出生：任一相邻两拍增量 ≤1（FIFO 间隔 spawn_interval_ticks）
        self.assertLessEqual(max(b - a for a, b in zip(counts, counts[1:])),
                             1)
        self.assertEqual(counts[-1], 2)                    # 最终两单位都到场

    def test_ghost_representation_source(self):
        # 待出场=半透明幽灵（部署页标记源锚——渲染层零 GL 断言面）
        self.assertIn("幽灵", _src("sovs/ui/scene.py"))


class TestBasicsReinforcements(unittest.TestCase):
    """战中呼援：实战期 PurchaseCmd 放行、扣点数池（basics:165-168）。"""

    def test_purchase_allowed_in_combat(self):
        w = make_world(43, phase=1)
        p = w.players[0]
        p.points = 100
        tpl = _rifle_tpl()
        p.deck_slots = [DeckSlot(tpl, 1)]
        self.assertTrue(cmd_purchase(w, p, tpl))
        self.assertEqual((p.points, p.deck_slots[0].copies_left,
                          len(p.spawn_queue)), (70, 0, 1))


class TestBasicsTransportsAndSupplies(unittest.TestCase):
    """登车 UI 入口（M）＋补给购买三档＋补给堆四开关/命中即爆（basics:181-213）。"""

    def test_mount_ui_entry(self):
        # M+点己方载具=登车（battle 期待令组→cmd.mount）
        f = _fsm_mod.ShellFsm()
        f.start_deploy()
        f.on_frame(_frame(units=[_funit(1), _funit(2)]))
        f.select_units([1])
        self.assertEqual(f.key("M"), "arm:mount")
        cmd = _SpyCmd()
        self.assertTrue(f.execute_armed_unit(2, cmd, enemy=False))
        self.assertEqual(cmd.calls[0][0], "mount")

    def test_buy_supplies_three_tiers(self):
        # basics:198-200 数值刻度同复刻（终审修复块 2026-10-13）：点=1000 /
        # Ctrl+点=4000 / Shift+点=舱满——supplies 重量池读数即手册 Kg 读数
        # （supply_round_weight=1）；「limited by your money」半边=经济计价
        # manual_silent 在册（无点数门），现买满仅受舱位钳制。
        w = make_world(44)
        u = add_unit(w, make_unit(w, _truck_tpl(flags=UnitFlag.HAS_SUPPLY),
                                  0, 0, (500000, 500000)))
        u.elements[0].mode = Mode.CARGO
        bus = CmdBus(w, 0)
        cap = u.elements[0].template.cargo_rounds_max        # 600（合成卡车舱位）
        rounds = []
        for tier in ("t1", "t4", "max"):
            rounds += [c.rounds for c in bus.buy_supplies_tier([u.id], tier)]
        self.assertEqual(rounds, [min(1000, cap), min(4000, cap), cap])

    def test_real_truck_capacity_fits_t4(self):
        # 数据侧配套锚：真实卡车舱位扩至 4000（GER/SU 同制）——t4=4000 恰满舱、
        # t1=1000 四分之一舱（手册「gauge … filling up」读数面）
        from sovs.sim.card_loader import load_library
        lib = load_library(os.path.join(_ROOT, "data/gen/cards_ground.v1.json"))
        for key in ("GER_TRUCK", "SU_TRUCK"):
            e = lib[key].unit_template.element_templates[0]
            self.assertEqual((e.cargo_rounds_max, e.cargo_weight_max),
                             (4000, 4000), key)

    def test_unload_creates_supply_dump(self):
        # basics:202-204「Order your truck to unload somewhere to create a supply
        # dump」：满载卡车 U+点地 → CreateDumpCmd → 行至落点落堆（空投箱式堆
        # 实体：不可移动/拾取链/命中即爆全继承）＋卡车清载；E 撤令清在途位。
        w = make_world(44)
        u = add_unit(w, make_unit(w, _truck_tpl(flags=UnitFlag.HAS_SUPPLY),
                                  0, 0, (500000, 500000)))
        e = u.elements[0]
        e.mode = Mode.CARGO
        e.supply_weight_g = 4000
        bus = CmdBus(w, 0)
        from sovs.sim.tick import CreateDumpCmd
        cmds = bus.unload([u.id], (505000, 500000))
        self.assertTrue(any(isinstance(c, CreateDumpCmd) for c in cmds))
        consume_commands(w)
        self.assertEqual(u.dump_pending, (505000, 500000))  # 在途位（未到不落堆）
        for _ in range(4000):
            world_tick(w)
            if u.dump_pending is None:
                break
        dumps = [x for x in w.units if x.template.name == "空投补给箱"]
        self.assertEqual(len(dumps), 1)                     # 落堆恰一个
        self.assertEqual(dumps[0].elements[0].supply_weight_g, 4000)  # 整转
        self.assertEqual(e.supply_weight_g, 0)              # 卡车清载（不双记）
        self.assertIsNone(u.dump_pending)

    def test_cancel_clears_dump_pending(self):
        # E=取消命令（manual.txt:357-359）清卸货在途位——撤令后卡车留场不清载
        w = make_world(44)
        u = add_unit(w, make_unit(w, _truck_tpl(flags=UnitFlag.HAS_SUPPLY),
                                  0, 0, (500000, 500000)))
        u.elements[0].mode = Mode.CARGO
        u.elements[0].supply_weight_g = 1000
        from sovs.sim.tick import cmd_create_dump
        self.assertTrue(cmd_create_dump(w, u, (590000, 500000)))
        self.assertIsNotNone(u.dump_pending)
        queue_command(w, CancelCmd(unit=u))
        consume_commands(w)
        self.assertIsNone(u.dump_pending)
        self.assertEqual(u.elements[0].supply_weight_g, 1000)  # 未落堆不清载

    def test_supply_dump_switches_and_explosion(self):
        # basics:208-213 四开关实门（ammo 关→不补给）；basics:206-207 命中即爆
        w = make_world(44)
        truck = add_unit(w, make_unit(w, _truck_tpl(flags=UnitFlag.HAS_SUPPLY),
                                      0, 0, (500000, 500000)))
        truck.elements[0].mode = Mode.CARGO
        truck.elements[0].supply_weight_g = 600
        rifle = add_unit(w, make_unit(w, _rifle_tpl(), 0, 0, (501000, 500000)))
        rifle.elements[0].weapon_states[0].ammo_left = 0
        w.await_resupply.append(rifle)
        from sovs.sim.tick import cmd_supply_switch
        self.assertTrue(cmd_supply_switch(w, truck, "ammo", False))
        for _ in range(50):
            world_tick(w)
        self.assertEqual(rifle.elements[0].weapon_states[0].ammo_left, 0)
        apply_damage(w, truck.elements[0], 1)              # 任何命中即爆
        self.assertFalse(truck.alive)
        self.assertFalse(rifle.alive)                      # 溅射敌我不分


# ════════════════════════════════════════════════════════════════════
# ④ deferred 现存五条：登记在册＋「不存在锚」反向锁死
# ════════════════════════════════════════════════════════════════════

class TestDeferredNotImplemented(unittest.TestCase):
    """后置项的不可实现面锁死：悄悄长出半吊子实现（无规格数值/无拍板）即红，
    同样防登记蒸发（与 TestSpecRegistry 双保险）。"""

    def test_aps_absent(self):
        sim = "".join(_src(os.path.join("sovs/sim", f))
                      for f in os.listdir(os.path.join(_ROOT, "sovs/sim"))
                      if f.endswith(".py"))
        self.assertIsNone(re.search(r"\baps\b", sim, re.I))
        self.assertNotIn("intercept", sim.lower())

    def test_trajectory_red_highlight_absent_with_hint(self):
        # 现值：仅 fm_panel『超程自动前移提示先行』文案位；引擎无弹道遮拦门
        self.assertIn("超程自动前移提示先行", _src("sovs/ui/fm_panel.py"))
        for rel in ("sovs/sim/tick.py", "sovs/sim/combat.py"):
            self.assertNotIn("trajectory_block", _src(rel))

    def test_comm_markers_f2_f4_absent_and_f1_is_help(self):
        win = _src("sovs/ui/shell_window.py")
        for k in ("F2", "F3", "F4"):
            self.assertNotIn("arcade.key.%s" % k, win)     # 通讯标记后置
        f = _fsm_mod.ShellFsm()
        f.help_open = True                                  # F1=帮助/键位面板
        self.assertEqual(f.esc(), "help_closed")

    def test_no_income_accrual(self):
        # 2026-10-03 拍板『没有收入机制』：闲置不加点（income 后置的行为面锁死）
        w = make_world(45)
        pts0 = w.players[0].points
        for _ in range(100):
            world_tick(w)
        self.assertEqual(w.players[0].points, pts0)

    def test_destroyed_units_do_not_return_to_deck(self):
        # 一命制：购卡扣份后，单位损毁不回补卡组（basics:174-175 后置的行为面）
        w = make_world(46, phase=1)
        p = w.players[0]
        p.points = 100
        tpl = _rifle_tpl()
        p.deck_slots = [DeckSlot(tpl, 1)]
        self.assertTrue(cmd_purchase(w, p, tpl))
        self.assertEqual(p.deck_slots[0].copies_left, 0)
        spawned = []
        for _ in range(200):                               # 出生到场
            world_tick(w)
            spawned = [u for u in w.units if u.template is tpl]
            if spawned:
                break
        self.assertTrue(spawned)
        for e in spawned[0].elements:                      # 摧毁
            e.hp_current = 0
        spawned[0].alive = False
        for _ in range(2000):
            world_tick(w)
        self.assertEqual(p.deck_slots[0].copies_left, 0)   # 不回补


if __name__ == "__main__":
    unittest.main()
