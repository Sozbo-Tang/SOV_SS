"""§F1 命中结算纯函数族（伪代码 v1.7 §F1 的可直接单测实现）+ §F1 落点结算组
（resolve_hit/resolve_sniper_hit/resolve_melee_hit/resolve_blast——2026-10-02 ⑤块）
+ §F2 生命周期完整体（apply_damage/destroy_element/unregister_unit_refs）
+ §F2 拖曳建立 start_tow（§F6 :494-516——PB-56 批② 拖曳展开块 2026-10-06 落，
cmd_tow 消费；解挂侧 stop_tow/release_tow_if_involved ⑤块既有）
+ §F5 建筑受击原语（hit_building/collapse_building，§F5 :533-541）。

两条核心曲线的整型化（官方锚点精确成立）：
- KE 中段 (0.5 ≤ r < 1)：mult‰ = (9·pen − 4·armor) × 1000 ÷ (5·armor)
    锚点：pen=armor → 1000‰；pen=½armor → 100‰；pen<½armor → 跳弹 0
- HE / 对步兵一切弹种：pen² × 1000 ÷ (pen² + armor²)
    锚点：pen=½a → 200‰；pen=a → 500‰；pen=2a → 800‰
- 无甲（armor<=0，卡车）→ 1000‰；SMOKE → 0

掷骰通道纪律（⑤块起）：狙击=R-02 概率掷 SNIPER 通道（world.rng.sniper()）；
近战/爆破伤害段零掷骰。〔D071 全拆 2026-10-07 发起人拍板「全拆+留口子」：暴击
掷骰整体退役——roll_crit/upgrade_crit 删除、CRIT 通道零消费者（通道号 3 冻结
不回收=口子③，见 rng.py 预留注）；恢复路径一步可回，见下方拆除留痕〕
"""
from __future__ import annotations

from .geom import approach_deg_of, dist_cm, facing_of
from .tables import BalanceConfig, CONFIG
from .types import (AuraKind, Building, CritLevel, CritSlot, DamageType, ElementType,
                    Facing, MoraleState, SmokeZone, TowPair, TowState, TowStopReason,
                    UnitFlag, UnitType, WeaponTemplate)

# §D.3#26 combat_style 档位（0=NORMAL 1=MELEE 2=SNIPER）——tick.py 同名常量自此再出口
COMBAT_STYLE_MELEE = 1
COMBAT_STYLE_SNIPER = 2


def damage_mult_permille(unit_type: UnitType, dmg_type: DamageType,
                         pen: int, armor: int) -> int:
    if dmg_type is DamageType.SMOKE:
        return 0
    if armor <= 0:
        return 1000
    if unit_type is UnitType.INFANTRY or dmg_type is DamageType.HE:
        return pen * pen * 1000 // (pen * pen + armor * armor)
    if pen >= armor:
        return 1000
    if pen * 2 >= armor:
        return (9 * pen - 4 * armor) * 1000 // (5 * armor)
    return 0


def penetration_at(w: WeaponTemplate, dist_cm_: int, pen_bonus: int = 0) -> int:
    """KE 随距离线性插值（贴脸 pen_max → 最远 pen_min）；HE/SMOKE 恒定。"""
    if w.damage_type is not DamageType.KE or w.max_range_cm <= 0:
        base = w.pen_max
    else:
        d = min(dist_cm_, w.max_range_cm)
        base = w.pen_max - (w.pen_max - w.pen_min) * d // w.max_range_cm
    return base + pen_bonus


def armor_lookup(elem, facing: Facing, dmg_type: DamageType) -> int:
    table = elem.template.armor_ke if dmg_type is DamageType.KE else elem.template.armor_he
    if table is None:
        return 0
    return table.of(facing)


def squad_hp_factor_bp(shooter_elem) -> int:
    """班火力=血量比例（线性，1HP=1人）。"""
    if shooter_elem.template.unit_type is not UnitType.INFANTRY:
        return 10000
    if shooter_elem.template.hp_max <= 0:
        return 0
    return max(0, shooter_elem.hp_current * 10000 // shooter_elem.template.hp_max)


def compute_direct_damage(target_elem, facing: Facing, dmg_type: DamageType, pen: int,
                          damage: int, shooter_elem) -> int:
    """§F1 :315-319 直射伤害（纯函数）：装甲面 → 曲线倍率 → 班火力比例，
    乘区书写序 damage * mult // 1000 * squad_bp // 10000（逐级截断）。"""
    armor = armor_lookup(target_elem, facing, dmg_type)
    mult = damage_mult_permille(target_elem.template.unit_type, dmg_type, pen, armor)
    return damage * mult // 1000 * squad_hp_factor_bp(shooter_elem) // 10000


def compute_hit_facing(target_elem, approach_deg: int, cfg: BalanceConfig,
                       top_attack: bool = False) -> Facing:
    """v1.7 §F1 :334-338 命中面链（覆盖序：驻楼→转向中→顶攻→按角度——后检
    后覆盖，v1.7 行序为准；本仓 v1.6 时期"顶攻最先"序已被 v1.7 覆盖序取代，
    top_attack 现无生产者置位、行为差不可达〔**滞文勘正 2026-10-07 空中闭环·块1**：
    自该块起扫射命中支走 resolve_hit{top_attack=TRUE}（AIR §F3 契约⑥——air.py
    resolve_strafe），top_attack 首个生产者已置位、顶攻分支可达〕）。驻楼 REAR=尾甲
    参考（v1.3 补齐）；转向中 SIDE 仅无炮塔（fire_arc<360 模板前置——方案6 双保险，
    GAP-08）。"""
    if getattr(target_elem, "garrison_in", None) is not None:
        return Facing.REAR
    if getattr(target_elem, "rotating", False) \
            and target_elem.template.fire_arc_deg < 360:
        return Facing.SIDE
    if top_attack:
        return Facing.TOP
    return facing_of(target_elem.facing, approach_deg, cfg.front_arc, cfg.side_arc)


def apply_damage(world, elem, dmg: int) -> None:
    """全游戏唯一伤害入口、唯一除名路径（§F2 :435-440 完整体——2026-10-02 ⑤块）：
    幂等门（dmg<=0 或元素不在编）→ 扣血 → hp<=0 走 destroy_element 完整连带，
    存活且出现缺口（弹药未满/步兵带伤）登记 world.await_resupply（:439-440
    带伤登记——原登记表记"⑥块补"，因本块重写 apply_damage 主体一并落地）。"""
    if dmg <= 0 or elem not in elem.unit.elements:
        return
    elem.hp_current -= dmg
    if elem.hp_current <= 0:
        destroy_element(world, elem)
    elif needs_resupply(elem.unit) and elem.unit not in world.await_resupply:
        world.await_resupply.append(elem.unit)


def needs_resupply(u) -> bool:
    """§F2 :442-445 待补给判据（v1.3 审查#11 缺口制）：任一武器弹药未满，或任一
    INFANTRY 元素带伤（0<hp<max）——弃 v1.1"仅 EMPTY"收窄，保 R-18"补满缺口"与
    医疗承载。消费端：system_supply 尾部自清理 + mark_resupply_if_needed（:447-449）
    + apply_damage 带伤登记（:439-440）。"""
    for e in u.elements:
        for ws in e.weapon_states:
            if ws.ammo_left < ws.template.ammo_base:
                return True
    for e in u.elements:
        if (e.template.unit_type is UnitType.INFANTRY
                and 0 < e.hp_current < e.template.hp_max):
            return True
    return False


def mark_resupply_if_needed(world, u) -> None:
    """§F2 :447-449 弹药消耗/受伤点统一调用（事件登记，免每 tick 全扫）：
    u 存活且 needs_resupply 且未登记 → world.await_resupply 追加。
    消费点：fire_direct（:811）/ fire_at（:951）/ apply_damage（:439-440 带伤
    登记同式内联）。"""
    if u.alive and needs_resupply(u) and u not in world.await_resupply:
        world.await_resupply.append(u)


def start_tow(world, tower_elements, towed_element) -> bool:
    """§F6 :494-516 建立拖曳对（PB-56 批② 机动链命令块·拖曳展开，2026-10-06——
    cmd_tow 消费；解挂侧 stop_tow/release_tow_if_involved/拖曳锁速与随动消费端
    movement.py 既有）。门序/写点照伪代码字面：
      ① 被拖元素已在拖（towed≠NONE——C1 双态 TOWING/TOWED）或牵引列表空 → FALSE；
      ② 函数级同队硬门（v1.7 GAP-10——cmd_tow 命令门之外的兜底：start_tow 亦被
        未来脚本/AI 路径调用，门不得只设命令层）；
      ③ 吨位贪心：按 tow_tonnage 降序稳定排序（并列取原序——sorted(key=…,
        reverse=True) 稳定序承载）逐个累计，acc≥own_weight_tons 即止
        （重坦 45t=2×30t 并拖或 1×45t 可表达），不足 FALSE；
      ④ TowPair 入 world.tow_pairs；牵引元素置 TOWING（C1——原与被拖同置 TOWED
        使牵引元素被队形闸一并排除、拖曳转场不发生的 B03 根因）、被拖置 TOWED；
        towed_element.redeploy_needed=TRUE（C3 元素级重展开旗——解挂后须
        cmd_deploy 重新展开才可开火。〔条件槽〕代码 ElementInstance.redeploy_needed
        恒有槽（types.py 默认 False），「仅 GUN/可被拖 MECH 分配」由 cmd_tow ② 门
        承载——合法被拖对象按分配规则必有此槽，此处直写无害）；
      ⑤ C5：不写 unit.deploy_state/deploy_timer（v1.4 的单位级「拖走一门炮整连
        收炮」行为已删除——留守已展开炮被强制 MOBILE 即时禁射须整连重走 30 秒的
        G04/G09 随之闭合，留守门可开火的设计前提）；
      ⑥ 清 towed_element.unit.fire_mission（方案10——单位级整清：与 SetModeCmd ⑦
        M21 半清除（仅本单位已无任何 INDIRECT 元素才清）粒度不同构，照字面）。
    〔规格字段勘误〕:500-505/:515 写 t.template.tow_tonnage /
    towed_element.template.own_weight_tons——两槽在 UnitTemplate（types.py），
    ElementTemplate 无此槽（照写即 AttributeError），按批① supply_rounds→
    supply_weight_g/批② 上车块 carrier.template.mode_set→carrier.unit.template.
    mode_set 换写先例改 t.unit.template.tow_tonnage / towed_element.unit.
    template.own_weight_tons。零掷骰（稳定排序+整数累计，不触任何 PCG32 通道）。"""
    if towed_element.towed is not TowState.NONE or not tower_elements:
        return False                                    # ① C1 双态已在拖 / 空列表
    if any(t.unit.team != towed_element.unit.team for t in tower_elements):
        return False                                    # ② GAP-10 同队硬门（兜底）
    ordered = sorted(tower_elements,
                     key=lambda t: t.unit.template.tow_tonnage,
                     reverse=True)                      # ③ 降序稳定排序（并列取原序）
    acc = 0
    chosen = []
    for t in ordered:
        chosen.append(t)
        acc += t.unit.template.tow_tonnage
        if acc >= towed_element.unit.template.own_weight_tons:
            break
    if acc < towed_element.unit.template.own_weight_tons:
        return False                                    # 吨位不足
    pair = TowPair(tower_elements=chosen, towed_element=towed_element)
    world.tow_pairs.append(pair)
    for t in chosen:
        t.towed = TowState.TOWING                       # C1：牵引元素 TOWING
    towed_element.towed = TowState.TOWED
    towed_element.redeploy_needed = True                # C3：元素级重展开旗
    if towed_element.unit.fire_mission is not None:     # 方案10：拖曳取消炮击任务
        towed_element.unit.fire_mission = None          #   （单位级整清）
    return True


def stop_tow(world, pair, reason: TowStopReason) -> None:
    """§F6 :518-522 解除拖曳对（reason ∈ {VOLUNTARY, REPAIRED, DESTROYED}——函数体
    不按因由分支，三因由同一收口）：牵引侧回 NONE（v1.5 C1）、被拖侧回 NONE、pair
    出 world.tow_pairs。v1.5（C3）：不清 towed_element.redeploy_needed——解挂后须
    cmd_deploy 重新展开；被拖者暴击槽保留〔**2026-10-07 D071 全拆批注**：MOB 生产端
    2026-10-06 已拆、FC/SEN/RLD 本块再拆——四槽皆无产出者=预留空槽；REPAIRED 时
    system_supply 的 crit.clear() 仍先行（恢复路径口子④登记，D016 语义零改动）〕。
    2026-10-02 ⑤块自 tick.py 迁入（destroy_element/release_tow_if_involved 消费
    需要——tick.py 再出口保既有 import 路径）。"""
    for t in pair.tower_elements:
        t.towed = TowState.NONE
    pair.towed_element.towed = TowState.NONE
    world.tow_pairs = [p for p in world.tow_pairs if p is not pair]   # 按身份除名


def release_tow_if_involved(world, elem) -> None:
    """§F6 :523-527 拖曳连带解除（v1.7 GAP-24：传元素——仅涉本元素的拖曳对，
    不整批误杀同单位健康拖曳）。"""
    for pair in [p for p in world.tow_pairs
                 if any(t is elem for t in p.tower_elements)
                 or p.towed_element is elem]:
        stop_tow(world, pair, TowStopReason.DESTROYED)


def destroy_element(world, elem) -> None:
    """§F2 :451-484 元素销毁完整定义（B7；2026-10-02 ⑤块落地——原 apply_damage
    仅最小除名）。v1.3（审查#1）车载连带按元素收集一次只结算一次；R-07 车毁
    连带 dmg = (hp*(1000−permille)+999)//1000（v1.5 M14/G22 向上取整式，D.0 常数）；
    s.pos=elem.pos「旁落位」——v1.7 未定标偏移量，取车毁同点位（见登记表）；
    物资清零按条件槽 None 判（方案12）；拖曳连带 GAP-24 元素级；装载请求撤销
    谓词 v1.6 ㉑A 元素粒度；全灭 → unregister_unit_refs + alive=False（一命制）。"""
    unit = elem.unit
    unit.elements.remove(elem)                            # 物理移除（§D.4 不变式）
    affected = [s for u in world.units if u.alive
                for s in u.elements if s.mounted_in is elem]
    if elem.cargo_units is not None:
        for squad in list(elem.cargo_units):
            squad.pos = elem.pos
            squad.move_path.clear()
            for se in list(squad.elements):
                if not any(se is s for s in affected):    # 按元素去重（身份判）
                    affected.append(se)                   # 跨卡班元素亦挂 mounted_in
        elem.cargo_units = []
    for s in affected:
        s.mounted_in = None
        s.pos = elem.pos                                  # 旁落位（同点位——偏移未定标）
        dmg = (s.hp_current * (1000 - CONFIG.vehicle_death_crew_permille) + 999) // 1000
        apply_damage(world, s, dmg)                       # 每元素仅一次（剩 1000−permille‰ 血）
    if elem.supply_weight_g is not None:
        elem.supply_weight_g = 0                            # hasSupply 槽（None=未分配，方案12；车毁物资清零）
    if elem.garrison_in is not None:                      # 驻楼引用清理（方案5 条件槽）
        elem.garrison_in.garrisoned = [x for x in elem.garrison_in.garrisoned
                                       if x is not elem]
        elem.garrison_in = None
    release_tow_if_involved(world, elem)                  # GAP-24 元素级拖曳连带
    if world.mount_requests is not None:                  # v1.4 I-19 + v1.5 M12/G26 撤销谓词
        world.mount_requests = [r for r in world.mount_requests
                                if r.carrier is not elem
                                and r.squad_element in r.squad_element.unit.elements]
    if not unit.elements:                                 # 全灭：一命制（无回圈无退款）
        unregister_unit_refs(world, unit)
        unit.alive = False                                # 声测圈不撤销（R-03 冻结）


def unregister_unit_refs(world, unit) -> None:
    """§F2 :487-492 所有销毁路径收口注销：信标注销（unit 作标定者）、掩护整键注销
    （unit 作被掩护对象）+ 从全部掩护者名单移除（空键删除——v1.3 终审遗留闭合）。
    旁表键型=unit.id（UnitInstance 为 mutable dataclass 不可哈希，v1.7 §D.6 键型
    unit 的实现适配——见 tick.py 登记表 discrepancies）。"""
    world.beacon_by_unit.pop(unit.id, None)
    world.cover_by_target.pop(unit.id, None)
    for tgt_id in list(world.cover_by_target):
        protectors = world.cover_by_target[tgt_id]
        protectors[:] = [x for x in protectors if x is not unit]
        if not protectors:
            del world.cover_by_target[tgt_id]


# ── D071 暴击掷骰整体拆除留痕（2026-10-07 发起人拍板「全拆+留口子」）──
# roll_crit/upgrade_crit 两函数原位删除（MOB 范围 2026-10-06 速度链块先行收窄
# below(4)→below(3)，本块 FC/SEN/RLD 一并=暴击掷骰整体退役，与 D068「纯血条
# 到底」字面全一致）。resolve_hit/resolve_blast 的两 MECH 暴击生产块同日同删。
# 恢复路径（一步可回，四处写点）：恢复 roll_crit（prob=MIN(10000, dmg×
# crit_per_hp_bp×crit_mod_permille//1000)→chance_bp 一次→成功 below(3) 一次，
# CRIT 通道即用）+ upgrade_crit（NONE→MINOR→MAJOR 只升不降）+ tables
# crit_per_hp_bp 出表 + resolve_hit/resolve_blast 生产块回贴——消费端（三乘区
# 族/恢复门/指纹 E 段）零改动即活。crit_mod_permille 字段保留标预留（勘察案 b：
# schema 冻结 D.3#20/空射硬要求⑥=0 契约/CSV 全空默认 1000——零数据改动）。


def inject_suppression(elem, amount: int) -> None:
    elem.suppression = min(100, elem.suppression
                           + amount * elem.template.suppression_vuln_permille // 1000)


def inject_suppression_area(world, center, radius_cm: int, power: int) -> None:
    """§F1 :394-400 面压制（目标+溅射圈内近旁；MAX(radius, suppression_min_radius_cm)
    圈、AMB-01 衰减式——2026-10-03 拍板常数出表进 BalanceConfig，数值不变）。"""
    for u in world.units:
        for e in u.elements:
            if dist_cm(e.pos, center) <= max(radius_cm,
                                             CONFIG.suppression_min_radius_cm):
                inject_suppression(e, power * falloff_bp(dist_cm(e.pos, center),
                                                         radius_cm) // 10000)


def falloff_bp(d: int, radius_cm: int) -> int:
    """v1.7（AMB-01 拍板·可推翻）衰减式：falloff_bp(d) = 10000 − MIN(coeff,
    d×coeff ÷ (2×radius_cm))——衰减跨度=2×弹半径（随弹径插值：
    大口径弹压制圈大且衰减缓、小口径集中；压制面与溅射伤害共用（:400/:407）。
    span 下限 1 防零径除零（radius 0 时仅贴点满衰减）。coeff/底线
    （10000−coeff）2026-10-03 拍板出表（数值不变）。"""
    span = max(1, 2 * radius_cm)
    coeff = CONFIG.blast_falloff_coeff_bp
    return 10000 - min(coeff, d * coeff // span)


# ── 修饰器族（查询期计算，不落变量；v1.7 GAP-29：crit × 压制 乘法复合，对齐 §F1 :414-419）──
# 〔口子②·预留分支 2026-10-07 D071 全拆〕下方 aim/reload/optics 三函数的
# crit.get(CritSlot.X) 分支原样保留：生产端已拆、elem.crit 恒空 dict → 分支恒
# miss=暴击项恒等（aim/reload 退化为纯压制连续项 10000∓6000×sup//100、optics
# 恒 10000）。重启用零改动——恢复生产端即活；tests/test_curves.py 三锚/ sensing
# SEN 锚手写 crit 槽位即生效，恰证口子活着。
def aim_factor_bp(elem, cfg: BalanceConfig = CONFIG) -> int:
    f = 10000
    c = elem.crit.get(CritSlot.FC)                # 预留口子（D071 全拆后恒 miss）
    if c is CritLevel.MINOR:
        f = f * 7500 // 10000
    elif c is CritLevel.MAJOR:
        f = f * 5000 // 10000
    f = f * (10000 - cfg.sup_penalty_bp * elem.suppression // 100) // 10000
    return max(1000, f)


def reload_factor_bp(elem, cfg: BalanceConfig = CONFIG) -> int:
    f = 10000
    c = elem.crit.get(CritSlot.RLD)               # 预留口子（D071 全拆后恒 miss）
    if c is CritLevel.MINOR:
        f = f * 13000 // 10000
    elif c is CritLevel.MAJOR:
        f = f * 16000 // 10000
    f = f * (10000 + cfg.sup_penalty_bp * elem.suppression // 100) // 10000
    return f


def morale_acc_factor_bp(unit, cfg: BalanceConfig = CONFIG) -> int:
    """士气态命中乘区（2026-10-04 士气效果接线块）：GDD-05 B4:149 moraleFactor
    按态乘区（受压×0.7/钉住×0.3）+ D023 命中率式「×士气惩罚」项双锚；值出
    cfg.morale_acc_factor_{sup,pin}_bp（低置信占位待定标——断箭参考杠杆为瞄准
    时间×2/×3，未采）。消费=tick.fire_direct acc 链（单位级；对空不乘——依据=
    代码先例：fire_aa 本就窄于 fire_direct（不乘 ambush/aura/self_defense，
    tick.py:1385-1387）+⑦⑧最小许可集先例；§F9 字面委托 fire_direct，故此为
    已留痕的推定豁免，登记表⑫在册）。与 aim_factor_bp 元素级连续项叠乘=双粒度
    记账（本元素乘员抖动 vs 单位指挥协同），非同一量双算。ROUTED=0 防御值：
    地面链 fire_permitted ⑨ 门已拦发射，正常流程不可达（直调 fire_direct 的
    测试路径下表现为必不命中）。零掷骰（确定性查表）。"""
    m = unit.morale
    if m is MoraleState.SUPPRESSED:
        return cfg.morale_acc_factor_sup_bp
    if m is MoraleState.PINNED:
        return cfg.morale_acc_factor_pin_bp
    if m is MoraleState.ROUTED:
        return 0
    return 10000                                              # STABLE 恒等


def optics_factor_bp(elem) -> int:
    """值域 {3000,6000,10000}（§F1 :414-419 字面）。〔口子②·预留分支 2026-10-07
    D071 全拆〕SEN 查表分支保留：恒空 dict → 恒 10000（纯查表无压制项）；重启用
    零改动——恢复生产端即恢复三值域（sensing 四消费点零改动）。"""
    c = elem.crit.get(CritSlot.SEN)               # 预留口子（D071 全拆后恒 miss）
    if c is CritLevel.MINOR:
        return 6000
    if c is CritLevel.MAJOR:
        return 3000
    return 10000


def aura_bonus_bp(world, team: int, kind, at_pos) -> int:
    """§F1 :425-427 修饰器族（查询期计算，不落变量）：每个存活友方 aura.kind==kind
    单位且 dist(aura_unit.pos, at_pos) <= aura.radius_cm → (10000+bonus_bp) 连乘。
    消费点：fire_direct 精度项（方案17：仅精度项）/ resolve_melee_hit 近战项（⑤块）。
    aura 为 UnitTemplate 字段（§D.1#24，unit 级承载）。"""
    f = 10000
    for u in world.units:
        if not u.alive or u.team != team:
            continue
        aura = u.template.aura
        if aura is None or aura.kind is not kind:
            continue
        if dist_cm(u.pos, at_pos) <= aura.radius_cm:
            f = f * (10000 + aura.bonus_bp) // 10000
    return f


# ── §F1 落点结算组（2026-10-02 ⑤块：地面命中/狙击/近战/爆破·烟弹——system_projectiles 分派支消费）──

def alive_elements_within(world, center, radius_cm: int) -> list:
    """§F1 :406 消费（v1.7 无定义体）：半径内（含等号）存活单位全体元素，
    先物化快照再结算——车毁连带旁落班仍按拍前名单各结一次（确定性列表序）。"""
    out = []
    for u in world.units:
        if not u.alive:
            continue
        for e in u.elements:
            if dist_cm(e.pos, center) <= radius_cm:
                out.append(e)
    return out


def hit_building(world, building: Building, dmg: int,
                 cfg: BalanceConfig = CONFIG) -> None:
    """§F5 :533-535 建筑受击：扣血、hp<=0 塌楼（×vs_fort 在调用侧已乘入 dmg）。"""
    building.hp -= dmg
    if building.hp <= 0:
        collapse_building(world, building, cfg)


def collapse_building(world, building: Building,
                      cfg: BalanceConfig = CONFIG) -> None:
    """§F5 :537-541 楼毁：驻军清引用、按 building_collapse_dmg 结算伤害（§D.0 :76
    默认 0=塌楼无伤害）、建筑出 world.buildings。"""
    for e in list(building.garrisoned):
        e.garrison_in = None
        if cfg.building_collapse_dmg > 0:
            apply_damage(world, e, cfg.building_collapse_dmg)
    building.garrisoned.clear()
    world.buildings = [b for b in world.buildings if b is not building]


def resolve_hit(world, p, cfg: BalanceConfig = CONFIG) -> None:
    """§F1 :321-346 地面直射命中结算（system_projectiles ⑤ will_hit 分派支）：
    建筑支（×vs_fort、无装甲曲线——v1.3 审查#5）→ 失的守卫（飞行中阵亡按落空 B9）
    → 方案1 combat_style 分支（狙击 R-02 / 近战绕装甲曲线）→ 装甲面/穿深/曲线伤害
    → apply_damage 唯一入口 → 面压制（AMB-01 衰减）。〔D071 全拆 2026-10-07：原
    「MECH 暴击掷 CRIT 通道」生产块删除——CRIT 通道零消费者〕"""
    tgt = p.hit_target
    if isinstance(tgt, Building):
        hit_building(world, tgt, p.damage * p.weapon.vs_fort_mult_permille // 1000
                     * squad_hp_factor_bp(p.shooter) // 10000, cfg)
        inject_suppression_area(world, tgt.pos, p.weapon.blast_radius_cm,
                                p.weapon.suppression_power)
        return
    if tgt is None or getattr(tgt, "unit", None) is None \
            or tgt not in tgt.unit.elements:
        return                                    # 目标已在飞行中阵亡 → 按失的落空
    if p.weapon.combat_style == COMBAT_STYLE_SNIPER:
        resolve_sniper_hit(world, p, tgt, cfg)    # R-02 概率结算，不走装甲/暴击曲线
        return
    if p.weapon.combat_style == COMBAT_STYLE_MELEE:
        resolve_melee_hit(world, p, tgt)          # 近战伤害，绕过装甲曲线（AMB-05）
        return
    approach = approach_deg_of(p.pos, tgt.pos)    # 8 扇区整型（弹道行进方向）
    facing = compute_hit_facing(tgt, approach, cfg, top_attack=p.top_attack)
    pen = penetration_at(p.weapon, dist_cm(p.pos, tgt.pos), p.pen_bonus)
    dmg = compute_direct_damage(tgt, facing, p.damage_type, pen, p.damage, p.shooter)
    apply_damage(world, tgt, dmg)                 # 唯一伤害入口（§F2）
    # 〔D071 全拆 2026-10-07〕原 MECH 暴击生产块（roll_crit CRIT 通道掷+upgrade_crit
    # 只升不降）删除——恢复路径见本文件头部拆除留痕（口子登记）
    inject_suppression_area(world, tgt.pos, p.weapon.blast_radius_cm,
                            p.weapon.suppression_power)   # 目标+溅射圈内近旁


def resolve_sniper_hit(world, p, tgt_elem,
                       cfg: BalanceConfig = CONFIG) -> None:
    """§F1 :348-371 R-02 概率结算（方案1：原 fire_sniper 结算体原样搬入）。
    掩盖查旁表 cover_by_target（方案9；键=unit.id）；M2/G12 整除外置（covered
    5000//10000、未掩护乘 10000——掩护≈减半非免疫）；掷 SNIPER 通道（首消费者）；
    v1.4 tally 记实际击杀；⑲A 后"对无班元素车辆直扣"路径已关（select_target 剔
    MECH）；tally≥sniper_tally_kills 灭最低血班（MIN by hp_current，并列取列表
    序首；存活元素空集防御跳过——伪代码 MIN 空集无定义，见登记表）。"""
    tgt_unit = tgt_elem.unit
    covered = tgt_unit.id in world.cover_by_target
    prob = cfg.sniper_base_prob_bp * (cfg.sniper_cover_mult_bp if covered
                                      else 10000) // 10000
    rng = world.rng.sniper()
    squads = [x for x in tgt_unit.elements
              if x.template.element_type is ElementType.SQUAD] \
        or list(tgt_unit.elements)                # 回退仅无班元素 INFANTRY 单位可达
    if tgt_unit.template.flags & UnitFlag.SINGLE_SQUAD_CARD:
        if rng.chance_bp(prob):                   # 指挥班组/声测班：概率灭排
            apply_damage(world, squads[0], squads[0].hp_current)
        return
    kills = int(rng.chance_bp(prob)) + int(rng.chance_bp(prob))   # 1~2 人（两掷序定）
    if kills > 0:
        actual = min(kills, squads[0].hp_current)  # v1.4：tally 记实际击杀
        apply_damage(world, squads[0], actual)     # 统一伤害入口（B9）
        tgt_unit.r02_kill_tally += actual
    if tgt_unit.r02_kill_tally >= cfg.sniper_tally_kills and tgt_unit.elements:
        lowest = None
        for x in tgt_unit.elements:                # 存活元素 MIN by hp_current
            if lowest is None or x.hp_current < lowest.hp_current:
                lowest = x
        apply_damage(world, lowest, lowest.hp_current)
        tgt_unit.r02_kill_tally -= cfg.sniper_tally_kills


def resolve_melee_hit(world, p, tgt_elem) -> None:
    """§F1 :373-380 近战结算（方案1：原 fire_melee 结算体原样搬入；AMB-05 绕过
    装甲曲线）。政委 MELEE 光环"跟我上"乘区（GAP-13 改锚：消费点随方案1 挪入
    直射伤害链）；弹药/装填/暴露/渗透清零已上移 fire_direct。零掷骰。"""
    bonus = p.shooter.unit.template.close_combat_bonus_permille       # 骑兵 1800
    bonus = bonus * aura_bonus_bp(world, p.shooter.unit.team, AuraKind.MELEE,
                                  tgt_elem.pos) // 10000
    dmg = p.weapon.damage * bonus // 1000
    apply_damage(world, tgt_elem, dmg)
    inject_suppression(tgt_elem, p.weapon.suppression_power)


def resolve_blast(world, p, cfg: BalanceConfig = CONFIG) -> None:
    """§F1 :402-412 曲射落点/烟弹/近失爆破（system_projectiles ⑤ BALLISTIC 分派支
    ——空投炸弹 AirProjectile 鸭子兼容同走此支）。SMOKE → 烟区实体（B4：半径/时长
    出 cfg，§D.6 :222 三字段口径）；爆破：半径内（含等号）元素按 AMB-01 衰减式吃
    溅射（乘区书写序 damage*falloff//10000*squad_bp//10000）+ 点压制；建筑按
    weapon vs_fort 直扣（无 squad 衰减）。〔D071 全拆 2026-10-07：原「MECH 暴击
    掷 CRIT」生产块删除——CRIT 通道零消费者〕"""
    if p.damage_type is DamageType.SMOKE:
        world.smoke_zones.append(SmokeZone(center=p.dest, radius_cm=cfg.smoke_radius_cm,
                                           ttl_ticks=cfg.smoke_ttl_ticks))
        return                                    # B4：spawnSmokeZone 定义体在此
    radius = p.weapon.blast_radius_cm
    for e in alive_elements_within(world, p.dest, radius):
        dmg = p.damage * falloff_bp(dist_cm(e.pos, p.dest), radius) // 10000 \
            * squad_hp_factor_bp(p.shooter) // 10000
        apply_damage(world, e, dmg)
        # 〔D071 全拆 2026-10-07〕原 MECH 暴击生产块（每受击元素各掷 CRIT 通道）
        # 删除——恢复路径见本文件头部拆除留痕（口子登记）
        inject_suppression(e, p.weapon.suppression_power)
    for b in list(world.buildings):               # buildings_within（快照——塌楼出表）
        if dist_cm(b.pos, p.dest) <= radius:
            hit_building(world, b, p.damage * p.weapon.vs_fort_mult_permille // 1000, cfg)
