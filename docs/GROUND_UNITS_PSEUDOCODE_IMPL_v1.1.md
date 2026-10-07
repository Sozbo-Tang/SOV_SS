# 地面单位实现伪代码——§13 对照表落地版（v1.1-IMPL）

> 上游：GROUND_UNITS_PSEUDOCODE_v1.1.md（机制权威）+ TECH-00（整型确定性约束）+ GDD-02-伪代码审查问题文档（§13 验收）。
> 本文把 §13 对照表逐项落成**可直接照写代码的伪代码**：数据结构逐字段（类型/单位/默认值）、系统函数逐函数（签名/步骤体/边界）。
> 语言中立；不出现任何具体语言代码。

---

## §T. 整型确定性落地约定（TECH-00，全文档生效）

| 项 | 约定 |
|---|---|
| 坐标 | 整型**厘米** (x, y)；长度字段一律 cm 后缀 |
| 时长 | 一律 **tick**（10Hz，1s = 10 tick） |
| 概率 | **bp 万分比**（0..10000），掷骰 = `rng.below(10000) < prob_bp` |
| 倍率 | **permille（‰，1000=100%）或 bp（10000=100%）**，字段名后缀标明 |
| 随机 | 禁语言随机库；自研 PCG32，**按通道分种子**：HIT / SCATTER / SPOT / CRIT / SNIPER / SONAR / ECONOMY |
| 禁项 | 禁 float、禁三角函数；整型平方根 `isqrt` 允许（精确整数运算，跨平台确定） |
| 朝向 | 整型度 0..359（0=上，顺时针）；方向向量量化 **8 扇区（45°）**，用 \|dx\| vs \|dy\| 符号比较，不用 atan2 |
| 散布 | **方形散布**：aimPoint = 目标点 + (rng.sym(R), rng.sym(R))，R=散布半径；不画圆 |
| 除法 | 整除向下；需要四舍五入用 `round_div(n,d) = (2n+d) // (2d)`（half-up，负号同样确定） |
| 迭代 | 一切遍历走**插入序列表**，禁无序集合遍历（保证逐 tick 位级可复现） |

**两条核心曲线的整型化**（锚点精确成立）：

```
KE 中段 (0.5 ≤ r < 1)：  mult‰ = (9·pen − 4·armor) × 1000 ÷ (5·armor)
    验算：pen=armor → 1000‰；pen=½armor → (4.5−4)×1000÷5 = 100‰ ✓
HE / 对步兵一切弹种：    mult‰ = pen² × 1000 ÷ (pen² + armor²)
    验算：pen=½a → 200‰；pen=a → 500‰；pen=2a → 800‰ ✓
```

---

## §D. 数据结构总表

### D.0 全局常数 BalanceConfig（§11 展开到字段级；禁止在系统函数里写死数值）

| 字段 | 类型/单位 | 默认 | 说明 |
|---|---|---|---|
| speed_table_cm_tick[0..5] | int[] | [0,25,45,70,100,140] | 速度档 1..5 |
| road_bonus_cm_tick | int | 170 | 道路速度（取 max 而非叠加） |
| sprint_mult_bp | bp | 15000 | 疾跑速度乘成 |
| tow_speed_tier | 档 | 1 | 拖曳双方最低档 R-19 |
| crit_mob_minor_mult_bp | bp | 5000 | 机动轻伤速度乘成 |
| stealth_factor_bp[0..10] | bp[] | [15000,13500,12000,11000,10500,10000,9500,9000,8000,6500,5000] | 隐蔽→视野倍率查表 |
| forest_stealth_add | 0.1级 | +2.0 | 林地隐蔽加值（×10 存储=20） |
| garrison_stealth_add | 0.1级 | +3.0 | 进驻建筑隐蔽【拍板默认】 |
| detect_atten_per_m | cm/米 | 150 | 每米森林/烟遮断的视野 |
| infiltration_mult_bp | bp | 15000 | R-04 渗透期隐蔽乘成 |
| ambush_mult_bp | bp | 20000 | R-12 伏击隐蔽乘成 |
| reveal_mult_bp | bp | 4000 | 开火暴露后隐蔽乘成 |
| sensing_period_ticks | tick | 5 | 侦察扫描节流 |
| melee_range_cm | cm | 5000 | 近战阈值 50m |
| ambush_acc_bonus_bp | bp | 13000 | R-12 脱伏击首击精度 |
| calib_acc_bonus_bp | bp | 12500 | R-01 侦察校准命中档 |
| calib_per_shot | 点/发 | 20 | 校射按发累积【拍板默认】 |
| calib_max_reduction_bp | bp | 6000 | 校射最大散布收束 |
| sup_penalty_bp | bp | 6000 | 压制满值精度惩罚 |
| sup_decay_per_tick | 点/tick | 1 | 压制自然衰减 |
| crit_per_hp_bp | bp/HP | 1200 | 暴击概率系数 |
| front_arc / side_arc | 度 | 45 / 135 | 命中面扇区 |
| sniper_base_prob_bp | bp | 3000 | R-02 基础击杀概率 |
| sniper_cover_mult_bp | bp | 5000 | 反狙击掩护减半（第1轮） |
| sniper_tally_kills | 人 | 3 | 排内累计灭班线（R-02） |
| r18_radius_cm | cm | 8000 | R-18 自动补给半径 |
| ammo_resupply_per_tick | 发/tick | 2 | 每武器补弹速率 |
| med_hp_per_unit | HP/份 | 1 | 医疗品=步兵回血（拍板①） |
| med_weight_per_unit | 重量/份 | 5 | D065 混装载重核算 |
| building_collapse_dmg | HP | 0 | 楼塌驻军伤害（数值章节定） |
| vehicle_death_crew_permille | ‰ | 400 | R-07 车载被毁：班剩 40% 血（扣 60%） |
| mount_time_ticks | tick | 200 | R-07 上车 20s |
| smoke_radius_cm / smoke_ttl_ticks | cm/tick | 3000 / 600 | 烟幕实体参数 |
| spawn_interval_ticks | tick | 10 | 逐个间隔出牌 |
| phase_ticks | tick | 900 / 450 / 13200 | 盲部署90s / 禁火45s / 实战22min |
| category_quota[类别][池] | 排 | GDD-01 配额表 | validateDeck 用 |
| fire_support_subquota[桶] | 连 | 榴3 / 反坦克2 / 火箭1 | R-13 子配额 |
| sonar_locate_threshold / min_radius_cm / max_radius_cm | 点/cm | 待定 | R-03 定位曲线 |

地形表 `TERRAIN`（Tiled 属性 → JSON）：`TERRAIN[tile].speed_bp[movementClass]`、`.stealth_add`、`.is_forest`、`.on_road`。

### D.1 UnitTemplate（单位静态 30）

| # | 字段 | 类型 | 说明 |
|---|---|---|---|
| 1 | template_id | int | 回放校验 |
| 2 | name | str | — |
| 3 | category | 枚举 侦察/步兵/装甲/火支/防空后勤 | UI + R-01 判定 |
| 4 | cost | int 部署点 | — |
| 5 | element_groups | [(ElementTemplate, 数量), ...] | **混编卡**：装掷=[(班,3),(251,4)] |
| 6 | optics_ground_cm | int | 视野 |
| 7 | optics_air_cm | int | R-17 对空探测（0=无） |
| 8 | air_ceiling | 无/低/中/高 | 可及高度层 |
| 9 | stealth_base | 0..10 | 头注刻度 |
| 10 | speed_tier | 1..5 | — |
| 11 | movement_class | FOOT/WHEEL/TRACK/HORSE | 骑兵=HORSE |
| 12 | turn_rate_deg_per_tick | int | R-09 车体转向 |
| 13 | deploy_time_ticks / 14 pack_time_ticks | int | 0=免展开 |
| 15 | mode_set | Mode 位掩码 | DIRECT/INDIRECT/TOW/CARGO/TRANSPORT（无 AA） |
| 16 | close_combat_bonus_permille | ‰ | 骑兵 1800；冲锋枪排高档 |
| 17 | tow_tonnage / 18 own_weight_tons | 吨 | R-19 |
| 19 | repair_power_hp_per_tick | int | D016 |
| 20 | supply_radius_cm | int | R-18（0/8000） |
| 21 | acoustic_signature | int | 声测定位权重（火箭炮最高） |
| 22 | sonar_radius_cm / 23 sonar_rate | int | R-03 |
| 24 | aura | {kind: MELEE\|PRECISION, bonus_bp, radius_cm} \| null | 政委/军官 |
| 25 | flags | 位段 | canSprint canGarrison canAmbush canInfiltrate noMoveVisionPenalty forestWalkSilent requiresMark singleSquadCard |
| 26 | pool | MAIN/RESERVE | 双池 |
| 27 | per_card_limit | int | 指挥班组=1 |
| 28 | quota_group | 无/榴弹炮/反坦克炮/火箭炮 | 火支子配额 |
| 29 | unlock_by | str | 特化解锁 |
| 30 | element_count | 派生 | Σ element_groups 数量（不存） |

### D.2 ElementTemplate（元素静态 15）

| # | 字段 | 说明 |
|---|---|---|
| 1 | element_type | VEHICLE/GUN/SQUAD |
| 2 | unit_type | INFANTRY/MECH（bodyType 派生：MECH→HARD） |
| 3 | hp_max | MECH 车体血；SQUAD=编制人数（1HP=1人） |
| 4-5 | armor_ke{F,S,R,T} / armor_he{F,S,R,T} | 0-20 相对刻度；T 仅空袭读取；0=无甲合法 |
| 6 | fire_arc_deg | 360 或 ±15°（R-09） |
| 7 | turret_traverse_deg_per_tick | 无炮塔=0 |
| 8 | suppression_vuln_permille | 敞篷 >1000 |
| 9 | squad_quality_bp | 老兵班 11500 |
| 10 | weapons[] | WeaponTemplate 列表 |
| 11 | mounted_armament | 空车可射击武器（251 车载 MG，第5轮） |
| 12 | seats | 运兵座位（卡车1班；0=不可载） |
| 13 | cargo_rounds_max / 14 cargo_medical_max | 每车 600 发 / 120 份（D065） |
| 15 | cargo_weight_max | 总载重（混装核算） |

### D.3 WeaponTemplate（武器 27 子字段）

| # | 字段 | 类型/说明 |
|---|---|---|
| 1 | name | — |
| 2 | target_mask | GROUND=1 / AIR_LOW=2 / AIR_MID=4 / AIR_HIGH=8 位掩码 |
| 3 | damage_type | KE/HE/SMOKE |
| 4 | pen_min / 5 pen_max | KE 远距~贴脸（0-20）；HE/SMOKE 相等 |
| 6 | damage | HP/发 |
| 7 | blast_radius_cm | — |
| 8 | max_range_cm / 9 min_range_cm | 迫击炮 250~1800；狙击 400；默认 min=0 |
| 10 | dispersion_cm | 散布半径（方形散布） |
| 11 | accuracy_base_bp | 基础命中 bp |
| 12 | aim_time_ticks / 13 reload_time_ticks | — |
| 14 | salvo | 连发数（机枪点射>1） |
| 15 | ammo_base / 16 ammo_weight | 基数（烟弹=SMOKE 武器档案，同轨）；每发补给重量 |
| 17 | projectile_speed_cm_per_tick | — |
| 18 | trajectory | DIRECT/BALLISTIC |
| 19 | suppression_power | 压制值/发 |
| 20 | crit_mod_permille | RPG/集束 >1000 |
| 21 | vs_fort_mult_permille | 工兵 2000 / ISU-HE 1500 / OT-34 2000 |
| 22 | special_ammo | {count:3, pen_bonus:+3} 钨芯 \| null |
| 23 | alt_profile | R-11 HE 档案 {damage, blast} \| null（AP 主炮共槽） |
| 24 | needs_deployed | R-05 |
| 25 | self_defense | R-15 {max_range_cm, accuracy_mult_bp} \| null |
| 26 | melee_flag / sniper_flag | 近战 / 狙击路由 |
| 27 | reveal_time_ticks | 开火暴露时长（联动声测） |

### D.4 UnitInstance（单位运行时 21）

| # | 字段 | 类型/说明 |
|---|---|---|
| 1 | unit_id / 2 team / 3 player_index | — |
| 4 | pos | (cm,cm) 队形基准 |
| 5 | elements[] | ElementInstance；**不变式：数组内必然存活** |
| 6 | move_path[] | 航点表 |
| 7 | deploy_state / 8 deploy_timer | MOBILE/DEPLOYING/DEPLOYED/PACKING |
| 9 | stance | 自由/禁射（不约束对空武器） |
| 10 | fire_mission | FireMission \| null（R-13） |
| 11 | calib_target / 12 calib_progress | 校射点 / 0..100 按发累积（R-16） |
| 13 | mark_level / 14 spotted_mask | 无/发现/校准；队伍位掩码 |
| 15 | infiltration_timer | R-04（600 tick） |
| 16 | ambush_active / 17 ambush_shot_bonus | R-12 |
| 18 | tow_pair | TowPair 引用 \| null |
| 19 | sniper_cover_target | 反狙击掩护对象（第1轮） |
| 20 | airdrop_beacon | 引导空投标记（第2轮） |
| 21 | r02_kill_tally / alive | 狙击计数 / 存活 |

### D.5 ElementInstance（元素运行时 16 + 2 工程槽）

| # | 字段 | 说明 |
|---|---|---|
| 1 | element_id / 2 unit / 3 template | — |
| 4 | pos / 5 facing(度) | 各自占位与车体朝向 |
| 6 | hp_current | 血条即兵力（SQUAD：1HP=1人） |
| 7 | crit{FC,SEN,RLD,MOB} | NONE/MINOR/MAJOR，仅 MECH 生效 |
| 8 | suppression | 0..100 |
| 9 | sprint_timer / 10 reveal_timer | 疾跑 / 开火暴露残留 |
| 11 | mounted_in | 载具元素引用（R-07，同卡） |
| 12 | weapon_states[] | {template, state, timer, target, ammo_left, special_ammo_left, use_self_defense} |
| 13 | rotating | 转向中→受弹按侧面（R-09） |
| 14 | towed | NONE/TOWED |
| 15 | mode | DIRECT/INDIRECT/TOW/CARGO/TRANSPORT（卡车每辆独立，D065） |
| 16 | cargo_units[] | 跨卡载运的班 UnitInstance（D065 运兵） |
| 17 | supply_rounds / 18 supply_medical | 本车在途物资（CARGO） |
| 工1 | garrison_in | 驻楼 Building 引用（§7 驻建筑） |
| 工2 | （上车进度不占字段） | world.mount_requests: [{squad_unit, carrier, ticks_left}] |

### D.6 世界实体与寄存器

```
Projectile   {shooter:Element, weapon:WT, damage_type, damage, blast_cm, pen_bonus,
              pos, dest, speed_cm_tick, trajectory, hit_target: Element|AircraftRef|None,
              will_hit: BOOL}
SmokeZone    {pos, radius_cm, ttl_ticks}
IntelCircle  {team, center, radius_cm}                    // R-03 冻结精度，不撤销
SoundTrack   {unit, pos, accum}                            // 每敌开火单位一条
Building     {id, pos, hp, garrison_slots, garrisoned[Element]}
AircraftRef  {id, team, pos, alt_tier, hp_current, hp_max, armor_aa, spotted_mask}   // §12 航空契约
Objective    {id, pos, radius_cm, owner}
TowPair      {tower_units[Unit], towed_unit:Unit}
FireMission  {form: POINT|LINE|CREEP, target_point, target_line[a,b], creep_speed_cm_tick,
              ammo_mult(1..3), salvo_mode: FULL|HALF, shots_left, started_tick}
DeckSlot     {template, copies_left}
PlayerState  {index, team, points, deck_slots[], spawn_queue[], income_per_second}

WORLD        {tick, phase(盲部署/禁火/实战/结算), seed, rng_channels[7],
              units[], players[], projectiles[], smoke_zones[], intel_circles[],
              sound_tracks[], buildings[], objectives[], tow_pairs[], aircraft[],
              mount_requests[], next_element_id}
```

### D.7 命令集（命令驱动；回放 = 种子 + 命令流）

```
MoveCmd{unit, path}  StopCmd{unit}  DeployCmd{unit}  PackCmd{unit}
SetModeCmd{element, mode}                                    // D065 三模式/火炮双职
PurchaseCmd{player, template}                                // 仅盲部署 phase
FireMissionCmd{unit, form, point|line, ammo_mult, salvo_mode, creep_speed}
CancelFireMissionCmd{unit}   SmokeCmd{element, point}         // 烟弹发射唯一入口
SetStanceCmd{unit, stance}   ToggleAmbushCmd{unit}   SprintCmd{unit}
GarrisonCmd{unit, building}  UnGarrisonCmd{unit}
MountCmd{squad_unit, carrier_unit}  DismountCmd{squad_unit}
TowCmd{tower_units[], target_unit}  UntowCmd{pair}
SetSniperCoverCmd{sniper_unit, target_unit}   SetAirdropBeaconCmd{unit, pos}
BuySuppliesCmd{truck_element, rounds, medical}
```

---

## §F1. 命中结算函数组（§13→B10 / KE·HE 曲线；纯函数可单测）

```
FUNCTION damage_mult_permille(unit_type, dmg_type, pen, armor) → ‰
    IF dmg_type == SMOKE: RETURN 0
    IF armor <= 0: RETURN 1000                          // 无甲守卫（卡车 D065 装甲0）→ B10
    IF unit_type == INFANTRY OR dmg_type == HE:
        RETURN pen*pen*1000 // (pen*pen + armor*armor)  // HE 曲线（整型精确）
    // KE 阶梯
    IF pen >= armor: RETURN 1000
    IF pen*2 >= armor: RETURN (9*pen − 4*armor)*1000 // (5*armor)
    RETURN 0                                              // 跳弹

FUNCTION penetration_at(w:WeaponTemplate, dist_cm, pen_bonus=0) → int
    IF w.damage_type != KE OR w.max_range_cm == 0: RETURN w.pen_max + pen_bonus
    d = MIN(dist_cm, w.max_range_cm)
    RETURN w.pen_max − (w.pen_max − w.pen_min) * d // w.max_range_cm + pen_bonus

FUNCTION armor_of(elem, facing, dmg_type) → int
    RETURN (elem.template.armor_ke IF dmg_type==KE ELSE elem.template.armor_he).of(facing)

FUNCTION squad_hp_factor_bp(shooter_elem) → bp            // 班火力=血量比例（线性）
    IF shooter_elem.template.unit_type != INFANTRY: RETURN 10000
    RETURN MAX(0, shooter_elem.hp_current * 10000 // shooter_elem.template.hp_max)

FUNCTION compute_direct_damage(target_elem, facing, dmg_type, pen, damage,
                               shooter_elem) → int        // 纯函数
    armor = armor_of(target_elem, facing, dmg_type)
    mult  = damage_mult_permille(target_elem.template.unit_type, dmg_type, pen, armor)
    RETURN damage * mult // 1000 * squad_hp_factor_bp(shooter_elem) // 10000

FUNCTION resolve_hit(world, p:Projectile)
    tgt = p.hit_target
    IF tgt NOT alive: RETURN                              // 目标已在飞行中阵亡 → 按失的落空
    approach = approach_deg_of(p.pos, tgt.pos)            // 8 扇区整型
    facing  = (TOP IF p.top_attack ELSE facing_of(tgt.facing, approach,
                                                   cfg.front_arc, cfg.side_arc))
    IF tgt.rotating: facing = SIDE                        // R-09 转向中侧面暴露
    pen  = penetration_at(p.weapon, dist_cm(p.pos, tgt.pos), p.pen_bonus)
    dmg  = compute_direct_damage(tgt, facing, p.damage_type, pen, p.damage, p.shooter)
    apply_damage(world, tgt, dmg)                         // 唯一伤害入口（§F2）
    IF tgt alive AND tgt.template.unit_type == MECH:
        crit = roll_crit(world.rng[CRIT], dmg, p.weapon.crit_mod_permille)
        IF crit: upgrade_crit(tgt.crit, crit)             // 只升不降
    inject_suppression_area(world, tgt.pos, p.weapon.blast_radius_cm,
                            p.weapon.suppression_power)   // 目标+溅射圈内近旁

FUNCTION roll_crit(rng, dmg, crit_mod_permille) → CritSlot|None
    prob = MIN(10000, dmg * cfg.crit_per_hp_bp * crit_mod_permille // 1000)
    IF prob <= 0 OR NOT rng.chance_bp(prob): RETURN None
    RETURN crit_slots[rng.below(4)]                       // FC/SEN/RLD/MOB 均匀

FUNCTION upgrade_crit(slots, slot)                        // NONE→MINOR→MAJOR，只升不降
    slots[slot] = MIN(MAJOR, slots.get(slot, NONE) + 1)

FUNCTION inject_suppression(element, amount)
    element.suppression = MIN(100, element.suppression
                              + amount * element.template.suppression_vuln_permille // 1000)

FUNCTION inject_suppression_area(world, center, radius_cm, power)
    FOR e IN all_alive_elements(world) WHERE dist_cm(e.pos, center) <= MAX(radius_cm, 2000):
        inject_suppression(e, power * falloff_bp(dist) // 10000)   // falloff: 10000→2000 线性

FUNCTION resolve_blast(world, p:Projectile)               // 曲射落点 / 烟弹 / 近失
    IF p.damage_type == SMOKE:
        world.smoke_zones.append(SmokeZone(p.dest, cfg.smoke_radius_cm, cfg.smoke_ttl_ticks))
        RETURN                                            // B4：spawnSmokeZone 定义体在此
    FOR e IN alive_elements_within(world, p.dest, p.weapon.blast_radius_cm):
        dmg = p.damage * falloff_bp(dist) // 10000 * squad_hp_factor_bp(p.shooter) // 10000
        apply_damage(world, e, dmg)
        IF e alive AND MECH: roll_crit → upgrade
        inject_suppression(e, p.weapon.suppression_power)
    FOR b IN buildings_within(p.dest, blast): hit_building(world, b, p.damage * vs_fort // 1000)
```

修饰器族（查询期计算，不落变量）：

```
aim_factor_bp(e)     = critFC{MINOR:×0.75, MAJOR:×0.5} × (10000 − sup_penalty_bp×sup//100)   下限1000
reload_factor_bp(e)  = critRLD{MINOR:×1.3, MAJOR:×1.6} × (10000 + sup_penalty_bp×sup//100)
optics_factor_bp(e)  = critSEN{MINOR:0.6, MAJOR:0.3}
aura_bonus_bp(team, kind, at_pos) = Σ 每个存活友方指挥元素 aura.kind==kind
                                     AND dist(aura_unit.pos, at_pos) <= aura.radius_cm
                                     → (10000 + bonus_bp) 连乘
```

---

## §F2. 生命周期（§13→B7 / B9 / R-07）

```
FUNCTION apply_damage(world, elem, dmg)                   // 全游戏唯一伤害入口、唯一除名路径
    IF dmg <= 0 OR elem NOT IN elem.unit.elements: RETURN // 幂等
    elem.hp_current −= dmg
    IF elem.hp_current <= 0: destroy_element(world, elem)

FUNCTION destroy_element(world, elem)                     // B7：完整定义
    unit = elem.unit
    unit.elements.remove(elem)                            // 物理移除，维持 §D.4 不变式
    // R-07 车载连带：车内班不消失，扣60%血，落位载具旁
    FOR s IN all_alive_elements(world) WHERE s.mounted_in == elem:
        s.mounted_in = None
        s.pos = elem.pos
        apply_damage(world, s, ceil(s.hp_current × 60%))  // 整型: (hp*600+999)//1000
    // D065 运兵连带：跨卡载运的班同样落位+扣血；物资随车毁
    FOR squad IN list(elem.cargo_units):
        squad.pos = elem.pos; squad.move_path.clear()
        FOR se IN list(squad.elements):
            se.pos = elem.pos
            apply_damage(world, se, ceil(se.hp_current × 60%))
        elem.cargo_units.remove(squad)
    elem.supply_rounds = 0; elem.supply_medical = 0
    // 驻楼引用清理
    IF elem.garrison_in != NULL: elem.garrison_in.garrisoned.remove(elem); elem.garrison_in = None
    // 拖曳连带
    release_tow_if_involved(world, unit)
    // 反狙击掩护失效：被掩护单位全灭时清引用
    FOR u IN world.units WHERE u.sniper_cover_target == unit AND unit.elements == []:
        u.sniper_cover_target = None
    // 全灭：一命制（无回圈无退款）；声测圈不撤销（R-03 冻结）；光环/侦听随清空自然失效
    IF unit.elements == []: unit.alive = False

FUNCTION start_tow(world, tower_units[], target) → BOOL   // R-19 拖曳吨位制
    IF target.tow_pair != NULL OR tower_units 为空: RETURN FALSE
    capacity = MAX(t.template.tow_tonnage FOR t IN tower_units)
    IF capacity <= 0: RETURN FALSE
    need = CEIL(target.template.own_weight_tons ÷ capacity)   // 重坦45/30=2并拖；45/45=1
    IF LEN(tower_units) < need: RETURN FALSE
    pair = TowPair(towers=tower_units[:need], towed=target)
    world.tow_pairs.append(pair); 双方 unit.tow_pair = pair
    FOR e IN 双方全部元素: e.towed = TOWED                     // 双方禁射+速度1档
    IF target.fire_mission != NULL: target.fire_mission = None  // 拖曳取消炮击任务
    RETURN TRUE

FUNCTION stop_tow(world, pair, reason ∈ {VOLUNTARY, REPAIRED, DESTROYED})
    FOR tu IN pair.towers: tu.tow_pair = None; FOR e IN tu.elements: e.towed = NONE
    pair.towed.tow_pair = None; FOR e IN pair.towed.elements: e.towed = NONE
    world.tow_pairs.remove(pair)                          // 被拖者 MOB 暴击保留（REPAIRED 时已先修）

FUNCTION release_tow_if_involved(world, unit)
    IF unit.tow_pair != NULL: stop_tow(world, unit.tow_pair, DESTROYED)

FUNCTION hit_building(world, building, dmg)               // 建筑受击
    building.hp −= dmg
    IF building.hp <= 0: collapse_building(world, building)

FUNCTION collapse_building(world, building)               // 楼毁：驻军结局
    FOR e IN list(building.garrisoned):
        e.garrison_in = None
        IF cfg.building_collapse_dmg > 0: apply_damage(world, e, cfg.building_collapse_dmg)
    building.garrisoned.clear(); world.buildings.remove(building)
```

---

## §F3. 侦察函数组（§13→g-伏击视野 / R-01 / R-03 / R-17）

```
FUNCTION effective_stealth_x10(world, unit) → 0..100      // 内部×10
    s = unit.template.stealth_base * 10
    m = 10000
    IF unit.moving:
        m = m * 5000 // 10000                              // 移动隐蔽减半
        IF flags.forestWalkSilent AND world.in_forest(unit.pos): m = m * 20000 // 10000  // 猎兵
    IF unit.infiltration_timer > 0: m = m * infiltration_mult_bp // 10000
    IF unit.ambush_active:          m = m * ambush_mult_bp // 10000
    IF ANY(e.reveal_timer > 0 FOR e IN unit.elements): m = m * reveal_mult_bp // 10000
    s = s * m // 10000
    IF ANY(e.garrison_in != NULL): s += garrison_stealth_add * 10
    IF world.in_forest(unit.pos):  s += forest_stealth_add
    RETURN CLAMP(s, 0, 100)

FUNCTION detection_range_cm(world, obs, tgt) → cm
    r = obs.template.optics_ground_cm
    IF obs.moving AND NOT flags.noMoveVisionPenalty: r = r // 2   // 侦察车轮式豁免（第1轮）
    IF obs.ambush_active: r = r // 2                              // 伏击视野减半（R-12，g-修复）
    r = r * stealth_factor_bp[CLAMP(effective_stealth_x10(tgt) // 10, 0, 10)] // 10000
    r −= detect_atten_per_m * (world.los_forest_m(obs.pos, tgt.pos)
                             + world.los_smoke_m(obs.pos, tgt.pos))   // 穿林/穿烟逐米衰减
    RETURN MAX(0, r)

FUNCTION keep_range_cm(world, obs, tgt) → cm               // 保持跟踪：无衰减距离（更难甩）
    RETURN obs.template.optics_ground_cm
         * stealth_factor_bp[CLAMP(tgt.template.stealth_base, 0, 10)] // 10000

FUNCTION system_sensing(world)                              // 每 sensing_period_ticks 一次
    FOR obs IN alive_units, FOR tgt IN 敌方 alive_units:
        d = dist_cm(obs.pos, tgt.pos)
        IF d <= detection_range_cm(obs, tgt):
            tgt.spotted_mask |= 1 << obs.team
            IF obs.template.category == 侦察: tgt.mark_level = CALIBRATED    // R-01
            ELIF tgt.mark_level < SPOTTED:    tgt.mark_level = SPOTTED
        ELIF d > keep_range_cm(obs, tgt):
            IF NOT ANY(同队其他观察者仍保持): tgt.spotted_mask &= ~(1 << obs.team)
    sense_air(world)                                       // R-17/R-23
    sonar_step(world)                                      // R-03

FUNCTION sense_air(world)
    FOR a IN world.aircraft, FOR g IN 敌方 alive_units:
        seen = (g.air_ceiling != NULL AND a.alt_tier <= g.air_ceiling
                AND dist <= g.optics_air_cm)                // 防空体系探测
             OR (a.alt_tier == LOW AND dist <= g.optics_ground_cm)   // 普通单位目视低空
        IF seen: a.spotted_mask |= 1 << g.team

FUNCTION sonar_step(world)                                  // R-03：开火越久定位越准
    FOR track IN world.sound_tracks:                        // SoundTrack 于 fire() 时 upsert
        listeners = 敌方部署完成(DEPLOYED)且 dist <= sonar_radius_cm 的声测单位
        IF listeners == []: CONTINUE                        // 声测班移动/阵亡→圈冻结不撤销
        track.accum += MAX(sonar_rate) * track.unit.template.acoustic_signature
        IF track.accum >= cfg.sonar_locate_threshold:
            radius = LERP(sonar_max_radius_cm, sonar_min_radius_cm,
                          MIN(1, (accum−threshold) ÷ threshold))     // 圈随时长收窄
            upsert IntelCircle(team=track.unit.team, center=track.pos, radius)  // 全队共享
```

---

## §F4. 交战函数组（§13→B2 / B3 / B5 / g-R15 / fireAt / 威胁值）

```
FUNCTION system_combat(world, unit)
    FOR e IN list(unit.elements):                          // elements 内必然存活
        // ① AIMING 到期结算
        FOR ws IN e.weapon_states WHERE ws.state == AIMING AND ws.timer <= 0:
            finish_aim(world, e, ws)
        // ② 对空：恒自动、并行、不受 stance/mode 影响（R-17）—— B5 修复核心
        FOR ws IN e.weapon_states
                WHERE ws.template.target_mask & AIR AND ws.state == READY AND ws.ammo_left > 0:
            aa_try_engage(world, e, ws)
        // ③ 对地：按元素 mode 分流
        IF e.mode == DIRECT:      ground_direct(world, unit, e)
        ELIF e.mode == INDIRECT:  indirect_role(world, unit, e)
        // TOW/CARGO/TRANSPORT：不开火（开火许可亦拦截）
    IF unit.fire_mission != NULL AND ANY(e.mode == INDIRECT):
        process_fire_mission(world, unit)

FUNCTION fire_permitted(world, unit, e, ws) → BOOL
    IF world.phase != 实战: RETURN FALSE                    // 禁火 phase 门
    IF unit.stance == HOLD_FIRE: RETURN FALSE               // 不约束对空（对空走②）
    IF ws.template.needs_deployed AND unit.deploy_state != DEPLOYED: RETURN FALSE  // R-05
    IF e.mounted_in != NULL AND ws.template 不是 mounted_armament: RETURN FALSE
    IF e.towed == TOWED: RETURN FALSE                       // R-19 拖曳双方禁射
    IF e.mode IN {TOW, CARGO, TRANSPORT}: RETURN FALSE      // D065 载货状态不作战
    RETURN TRUE

FUNCTION select_target(world, e, ws) → Element|NULL
    w = ws.template
    cands = [x FOR x IN 敌方存活元素
             IF 单位被我发现(x.unit)                        // spotted_mask 含我队位
             AND (GROUND & w.target_mask)
             AND w.min_range_cm <= dist_cm(e.pos, x.pos) <= w.max_range_cm
             AND (NOT unit.flags.requiresMark OR x.unit.mark_level >= SPOTTED)]  // 犀牛（第8轮）
    IF cands == []: RETURN NULL
    // 评分：预估伤害 + 威胁值 − 距离惩罚（威胁值=可计算量，无新变量——g-修复）
    FOR x IN cands: score[x] = w.damage * w.salvo + threat_value(x) − dist_cm(e.pos,x.pos)//100
    RETURN cands 中 score 最大者（并列取列表序首个——确定性）

FUNCTION threat_value(x) → int                              // 目标对我方的 DPS 近似
    RETURN MAX(w.damage * w.salvo * 10000 // MAX(1, w.reload_time_ticks)
               FOR w IN x.weapon_states 的模板)

FUNCTION begin_aim(world, e, ws, target)
    ws.state = AIMING
    ws.timer = MAX(1, ws.template.aim_time_ticks * aim_factor_bp(e) // 10000)
    ws.target = target

FUNCTION ground_direct(world, unit, e)
    FOR ws IN e.weapon_states WHERE target_mask & GROUND AND state==READY AND ammo_left>0:
        IF NOT fire_permitted(world, unit, e, ws): CONTINUE
        // 近战分支—— B3 修复：meleeFlag 武器近距自动接战（走同一状态机，无弹丸）
        IF ws.template.melee_flag:
            tgt = nearest_enemy_element(e, <= cfg.melee_range_cm, spotted_only=TRUE)
            IF tgt != NULL: begin_aim(world, e, ws, tgt)
            CONTINUE
        // 狙击分支—— B2 修复：sniperFlag 路由 R-02
        IF ws.template.sniper_flag:
            tgt = select_target(world, e, ws)
            IF tgt != NULL: begin_aim(world, e, ws, tgt.unit)   // 狙击以“单位”为目标
            CONTINUE
        // 普通直射
        tgt = select_target(world, e, ws)
        IF tgt == NULL: CONTINUE
        want = approach_deg_of(tgt.pos, e.pos)
        IF |angle_diff(e.facing, want)| > e.template.fire_arc_deg:      // R-09
            rotate_step(world, e, want); CONTINUE                        // 射界外先转车体
        begin_aim(world, e, ws, tgt)

FUNCTION indirect_role(world, unit, e)
    w_main = e.weapon_states[0]
    // 自卫直射—— g-R15 修复：曲射炮被近身时以惩罚档案直射（与炮击任务经 weaponStates 忙碌互斥）
    IF w_main.state == READY AND fire_permitted(world, unit, e, w_main)
       AND ANY(敌元素 dist <= w_main.self_defense.max_range_cm):
        near = 最近敌元素
        w_main.use_self_defense = TRUE
        begin_aim(world, e, w_main, near)
    // 否则炮击任务在 system_combat 尾部统一推进

FUNCTION finish_aim(world, e, ws)
    tgt = ws.target
    IF tgt == NULL OR NOT alive(tgt): ws.state = READY; RETURN       // 不消耗弹药
    IF ws.template.sniper_flag:
        fire_sniper(world, e, ws, tgt)
    ELIF ws.template.melee_flag:
        fire_melee(world, e, ws, tgt)
    ELIF is_aircraft(tgt):
        fire_aa(world, e, ws, tgt)
    ELSE:
        fire_direct(world, e, ws, tgt)

FUNCTION select_profile(world, e, ws, tgt) → {damage_type, damage, blast_cm, pen_bonus}
    w = ws.template
    // R-11 自动选弹（共槽）：软目标优先 HE 档案
    IF w.alt_profile != NULL AND tgt.template.unit_type == INFANTRY:
        RETURN HE档案(w.alt_profile)
    // 钨芯：常规 AP 打不动正面且还有存货 → 自动救场
    IF w.special_ammo != NULL AND ws.special_ammo_left > 0
       AND tgt.template.unit_type == MECH
       AND w.pen_max < tgt.template.armor_ke.front:
        ws.special_ammo_left −= 1
        RETURN 默认AP(pen_bonus=+w.special_ammo.pen_bonus)
    RETURN 默认档案

FUNCTION fire_direct(world, e, ws, tgt)
    unit = e.unit; w = ws.template
    prof  = select_profile(world, e, ws, tgt)
    ws.ammo_left −= 1
    ws.state = RELOADING; ws.timer = MAX(1, w.reload_time_ticks * reload_factor_bp(e)//10000)
    e.reveal_timer = MAX(e.reveal_timer, w.reveal_time_ticks)          // 开火暴露
    upsert_sound_track(world, unit, e.pos)                             // 喂声测 R-03
    dist = dist_cm(e.pos, tgt.pos)
    acc_bp = w.accuracy_base_bp
           × accuracy_ratio_bp(dist // MAX(1, w.max_range_cm))          // 17 段查表，默认全 10000
           × aim_factor_bp(e)
           × (unit.ambush_shot_bonus ? ambush_acc_bonus_bp : 10000)      // R-12 首击，打完清
           × aura_bonus_bp(unit.team, PRECISION, e.pos) // 10000          // 军官光环
           × e.template.squad_quality_bp // 10000                         // 老兵班
           × (tgt.unit.mark_level == CALIBRATED ? calib_acc_bonus_bp : 10000)  // R-01 消费
           × (ws.use_self_defense ? w.self_defense.accuracy_mult_bp : 10000)   // R-15 惩罚
    unit.ambush_shot_bonus = FALSE
    calib_reduction_bp = 10000 − unit.calib_progress * calib_max_reduction_bp // 100
    FOR i IN 1..w.salvo:
        will_hit = world.rng[HIT].chance_bp(acc_bp)
        IF will_hit:
            aim = jitter_small(tgt.pos, world.rng[SCATTER])               // 命中点贴目标
        ELSE:
            R = w.dispersion_cm * calib_reduction_bp // 10000
            aim = tgt.pos + (world.rng[SCATTER].sym(R), world.rng[SCATTER].sym(R))  // 方形散布
        world.projectiles.append(Projectile(shooter=e, weapon=w, profile=prof,
            pos=e.pos, dest=aim, speed=w.projectile_speed_cm_tick,
            trajectory=w.trajectory, hit_target=tgt, will_hit=will_hit))

FUNCTION fire_sniper(world, e, ws, tgt_unit)              // B2/B9 修复
    IF dist_cm(e.pos, tgt_unit.pos) > ws.template.max_range_cm: ws.state=READY; RETURN  // 射程门
    ws.ammo_left −= 1; ws.state = RELOADING; ws.timer = reload…
    e.reveal_timer = MAX(…); unit.infiltration_timer = 0                 // 渗透身份消失 R-04
    covered = ANY(u.team != tgt_unit.team AND u.sniper_cover_target == tgt_unit)
    prob = sniper_base_prob_bp * (covered ? sniper_cover_mult_bp // 10000 : 10000)
    rng = world.rng[SNIPER]
    squads = [班元素 OF tgt_unit] 或 全部元素
    IF flags.singleSquadCard:                                            // 指挥班组/声测班：概率灭排
        IF rng.chance_bp(prob): apply_damage(world, squads[0], squads[0].hp_current)
        RETURN
    kills = rng.chance_bp(prob) + rng.chance_bp(prob)                    // 1~2 人
    IF kills > 0:
        apply_damage(world, squads[0], MIN(kills, squads[0].hp_current)) // 走统一伤害入口——B9
        tgt_unit.r02_kill_tally += kills
    IF tgt_unit.r02_kill_tally >= sniper_tally_kills:                    // ≥3人=损失1班
        lowest = MIN(存活元素, by hp_current)
        apply_damage(world, lowest, lowest.hp_current)
        tgt_unit.r02_kill_tally −= sniper_tally_kills

FUNCTION fire_melee(world, e, ws, tgt)                    // B3 修复
    bonus = e.unit.template.close_combat_bonus_permille                     // 骑兵1800
    bonus = bonus * aura_bonus_bp(e.unit.team, MELEE, tgt.pos) // 10000      // 政委督战光环
    dmg = ws.template.damage * bonus // 1000
    apply_damage(world, tgt, dmg)
    inject_suppression(tgt, ws.template.suppression_power)
    ws.ammo_left −= 1; ws.state = RELOADING
    IF e.unit.infiltration_timer > 0: e.unit.infiltration_timer = 0

FUNCTION aa_try_engage(world, e, ws)                      // B5 修复的另一半
    cands = [a FOR a IN world.aircraft
             IF a.team != e.unit.team AND (a.spotted_mask & 我队位)
             AND (a.alt_tier <= unit.air_ceiling)
             AND dist_cm(e.pos, a.pos) <= ws.template.max_range_cm]
    IF cands == []: RETURN
    ws.target = MIN(cands, by dist_cm)                    // 【拍板默认】对空威胁=最近
    begin_aim(world, e, ws, ws.target)
```

### F4.1 炮击任务（R-13/R-14/R-16/R-03 盲射）

```
FUNCTION process_fire_mission(world, unit)
    fm = unit.fire_mission
    guns  = (fm.salvo_mode == HALF) ? 前一半 INDIRECT 元素 : 全部 INDIRECT 元素   // R-14 半轮
    FOR gun IN guns:
        ws = gun 主武器
        IF NOT (ws.state == READY AND fire_permitted(world, unit, gun, ws)): CONTINUE
        // 【v1.1 修复】未展开/被拖/载货的炮不打——统一走开火许可
        fire_at(world, gun, ws, fm)

FUNCTION fire_at(world, gun, ws, fm)                      // 无目标弹丸（B：fireAt 定义体）
    w = ws.template
    IF fm.form == POINT:  pt = fm.target_point
    ELIF fm.form == LINE: pt = 沿 fm.target_line 均匀取样(第 k 份, k=已发射数)
    ELSE: /* CREEP */     t = MIN(1, (world.tick − fm.started_tick) * fm.creep_speed_cm_tick
                                       // MAX(1, 线长))
                          pt = LERP(fm.target_line.a, fm.target_line.b, t)
    // 盲射声测圈：目标点落在模糊圈内 → 叠加圈半径
    extra = 0
    FOR c IN world.intel_circles WHERE c.team == unit.team
         AND dist_cm(c.center, pt) <= c.radius_cm: extra = MAX(extra, c.radius_cm)
    // 连内共享校射 R-16：落点在友军视野内才逐发收束
    IF point_in_friendly_vision(world, fm.target_point):
        unit.calib_progress = MIN(100, unit.calib_progress + cfg.calib_per_shot)  // 按发累积
    IF fm.target_point != unit.calib_target: unit.calib_target = fm.target_point;
                                             unit.calib_progress = 0                 // 换点重置
    scatter_cm = w.dispersion_cm * (10000 − unit.calib_progress*calib_max_reduction_bp//100)//10000
               + extra
    aim = pt + (world.rng[SCATTER].sym(scatter_cm), world.rng[SCATTER].sym(scatter_cm))
    ws.ammo_left −= 1; ws.state = RELOADING; ws.timer = reload…
    fm.shots_left −= 1
    upsert_sound_track(world, unit, gun.pos)              // 火箭炮 acoustic_signature 最高→最快被定位
    world.projectiles.append(Projectile(shooter=gun, weapon=w, profile=默认HE,
        pos=gun.pos, dest=aim, speed=w.projectile_speed_cm_tick,
        trajectory=BALLISTIC, hit_target=NULL, will_hit=FALSE))
    IF fm.shots_left <= 0: unit.fire_mission = None
```

---

## §F5. 移动函数组（§13→B8 / R-09 / R-12）

```
FUNCTION move_speed_cm_tick(world, unit) → int
    e = unit.elements[0]                                   // 空编制的单位不存在
    IF e.crit[MOB] == MAJOR: RETURN 0                      // 趴窝 R-19
    base = speed_table[unit.template.speed_tier]
    IF unit.tow_pair != NULL OR ANY(e.towed == TOWED): base = speed_table[tow_speed_tier]
    m_bp = world.terrain_speed_bp(unit.pos, unit.template.movement_class)   // Tiled 属性
    IF e.crit[MOB] == MINOR: m_bp = m_bp * crit_mob_minor_mult_bp // 10000
    v = base * m_bp // 10000
    IF ANY(e.sprint_timer > 0): v = v * sprint_mult_bp // 10000
    RETURN v

FUNCTION system_move(world, unit)
    IF unit.deploy_state IN {DEPLOYING, PACKING}: RETURN   // 展开中禁移动
    IF unit.tow_pair != NULL AND unit.tow_pair.towed == unit: RETURN   // 被拖：由牵引车带
    IF 全部元素 mounted_in != NULL:                        // R-07 整班随车
        unit.pos = carrier.pos; sync_mounted(unit); RETURN
    v = move_speed_cm_tick(world, unit)
    IF v <= 0 OR unit.move_path == []: sync_followers(unit); RETURN
    budget = v
    WHILE budget > 0 AND unit.move_path != []:
        dest = unit.move_path[0]
        unit.pos, arrived = step_toward(unit.pos, dest, budget)   // 整型 DDA（round_div）
        IF arrived: unit.move_path.pop(0); budget −= dist_cm(前位置, dest)
        ELSE: budget = 0
    unit.elements[0].facing = octant_deg(下一航点 − unit.pos)       // 8 扇区整型朝向
    IF unit.ambush_active: ambush_active = FALSE                    // 移动自动退出，无首击加成
    IF unit.tow_pair != NULL AND unit IN towers: towed.pos = unit.pos   // 拖曳随动
    sync_followers(unit)

FUNCTION sync_followers(unit)
    FOR e IN unit.elements WHERE e.mounted_in != NULL: e.pos = e.mounted_in.pos
    FOR e IN unit.elements WHERE e.mode == TRANSPORT:
        FOR squad IN e.cargo_units: squad.pos = e.pos               // D065 摩托化机动——B8

FUNCTION rotate_step(world, e, target_deg)                  // R-09 转车体（转向慢=暴露窗口）
    diff = angle_diff(target_deg, e.facing)
    step = unit.template.turn_rate_deg_per_tick
    IF |diff| <= step: e.facing = target_deg; e.rotating = FALSE
    ELSE: e.facing = (e.facing + SIGN(diff)*step) % 360; e.rotating = TRUE
```

---

## §F6. 展开 / 运输 / 拖曳 / 驻楼 / 后勤（§13→B4 / B6 / g-载重 / g-拖曳解除）

```
// ── deployState 状态机（迁移表见 v1.1 §10；动作函数在此）──
FUNCTION cmd_deploy(world, unit)                            // DeployCmd
    IF unit.deploy_state == MOBILE: unit.deploy_state = DEPLOYING
    unit.deploy_timer = unit.template.deploy_time_ticks
FUNCTION cmd_pack_or_move(world, unit)                      // PackCmd / MoveCmd 触发
    IF unit.deploy_state == DEPLOYED:  unit.deploy_state = PACKING; unit.deploy_timer = pack_time
    IF unit.deploy_state == DEPLOYING: unit.deploy_state = MOBILE; unit.deploy_timer = 0  // 进度作废

// ── R-07 上/下车（同卡）与 D065 运兵（跨卡）统一 ──
FUNCTION cmd_dismount(world, squad_unit)
    FOR e IN squad_unit.elements WHERE e.mounted_in != NULL:
        e.pos = e.mounted_in.pos 旁落位; e.mounted_in = None
FUNCTION cmd_mount(world, squad_unit, carrier_unit)         // 进入 world.mount_requests
    IF 班静止于载具旁 AND 载具静止: world.mount_requests.append({squad_unit, 首个车元素, mount_time_ticks})
FUNCTION mount_requests_step(world)                          // 每 tick
    FOR r IN world.mount_requests:
        r.ticks_left −= 1
        IF r.ticks_left <= 0:
            FOR e IN r.squad_unit.elements: e.mounted_in = r.carrier
            r.carrier.cargo_units.append(r.squad_unit)       // 双向引用
            remove r

// ── D065 卡车三模式：元素级互斥切换（B6 修复）──
FUNCTION cmd_set_element_mode(world, e, m)
    IF m NOT IN e.unit.template.mode_set: REJECT
    IF e.mode == TOW:      release_tow_if_involved(world, e.unit)     // 切模式先解挂
    IF e.mode == CARGO:    e.supply_rounds = 0; e.supply_medical = 0  // 卸货
    IF e.mode == TRANSPORT: FOR s IN e.cargo_units: s.pos = e.pos 旁落位; e.cargo_units.clear()
    e.mode = m
    IF m != INDIRECT: IF e.unit.fire_mission != NULL: e.unit.fire_mission = None  // 任务取消

FUNCTION buy_supplies(world, truck_element, rounds, medical)         // BuySuppliesCmd
    weight = rounds × Σ(武器 ammo_weight 均摊) + medical × med_weight_per_unit
    IF rounds  > truck.template.cargo_rounds_max:  REJECT
    IF medical > truck.template.cargo_medical_max: REJECT
    IF weight  > truck.template.cargo_weight_max:  REJECT               // D012 混装载重闸（g-载重）
    truck_element.supply_rounds = rounds; truck_element.supply_medical = medical

// ── 拖曳指令 ──
FUNCTION cmd_tow(world, towers[], target):  start_tow(world, towers, target)   // 失败静默拒绝
FUNCTION cmd_untow(world, unit): IF unit.tow_pair != NULL: stop_tow(world, unit.tow_pair, VOLUNTARY)

// ── 驻楼（最小实现，【拍板默认】隐蔽+3、受击参考尾甲）──
FUNCTION cmd_garrison(world, unit, building)
    IF NOT flags.canGarrison OR building.garrison_slots <= LEN(building.garrisoned): REJECT
    FOR e IN unit.elements: e.garrison_in = building; building.garrisoned.append(e)
    // 效果挂在 effective_stealth_x10（+garrison_stealth_add）与命中面（REAR 参考）两处
FUNCTION cmd_un_garrison(world, unit)
    FOR e IN unit.elements WHERE e.garrison_in != NULL:
        e.garrison_in.garrisoned.remove(e); e.garrison_in = None; e.pos = 楼旁落位

// ── 烟弹发射（B4：烟=SMOKE 武器档案，唯一入口；不进自动选目标）──
FUNCTION cmd_smoke(world, element, point)
    ws = 首个 damage_type==SMOKE 且 READY 且 ammo_left>0 的武器
    IF ws == NULL OR NOT fire_permitted(world, element.unit, element, ws): REJECT
    R = ws.template.dispersion_cm
    aim = point + (rng[SCATTER].sym(R), rng[SCATTER].sym(R))
    ws.ammo_left −= 1; ws.state = RELOADING; ws.timer = reload_time
    world.projectiles.append(Projectile(shooter=element, weapon=ws.template,
        profile=SMOKE, pos=element.pos, dest=aim, trajectory=BALLISTIC,
        hit_target=NULL, will_hit=FALSE))

// ── 后勤（R-18 自动补给；烟弹在武器弹药轨内随弹补给——B4 单轨闭环）──
FUNCTION system_supply(world)
    FOR t IN all_elements WHERE t.mode == CARGO AND (supply_rounds>0 OR supply_medical>0):
        FOR u IN alive_units_within(t.pos, t.unit.template.supply_radius_cm):
            FOR e IN u.elements:
                FOR ws IN e.weapon_states WHERE ws.ammo_left < ws.template.ammo_base:
                    take = MIN(ammo_base − ammo_left, t.supply_rounds, ammo_resupply_per_tick)
                    ws.ammo_left += take; t.supply_rounds −= take               // 烟弹同轨自动补
                IF e.template.unit_type == INFANTRY AND 0 < e.hp_current < e.template.hp_max:
                    med = MIN(CEIL((hp_max − hp_current) ÷ med_hp_per_unit), t.supply_medical)
                    e.hp_current = MIN(hp_max, e.hp_current + med × med_hp_per_unit)
                    t.supply_medical −= med
            // 边界：hp==0 的班已被 destroy_element 除名——医疗永不复活班元素
    FOR rep IN all_elements WHERE unit.template.repair_power_hp_per_tick > 0:
        FOR e IN 贴靠的 MECH 元素 WHERE hp<max OR crit 非空:
            e.hp_current = MIN(hp_max, e.hp_current + repair_power)
            IF e.hp_current >= e.template.hp_max:
                e.crit.clear()                                    // D016 修满清状态伤
                FOR pair IN world.tow_pairs WHERE pair 涉及 e.unit:
                    stop_tow(world, pair, REPAIRED)               // 修好即归队（R-19）
    FOR box IN world.supply_boxes:                                // R-21 空投箱=临时 CARGO
        同上结算（友军进入半径自动拾取）
```

---

## §F7. 经济与部署（§13→g-配额；一命制）

```
FUNCTION validate_deck(deck_slots[]) → BOOL                 // 卡组构筑期（战斗外）
    FOR (card, copies) IN deck_slots:
        IF copies > card.per_card_limit: REJECT             // 每卡限份（指挥班组=1）
        IF card.unlock_by != "" AND NOT unlocked(card.unlock_by): REJECT   // 特化解锁
    FOR cat IN 类别:
        主力数 = Σ copies WHERE category==cat AND pool==MAIN
        预备数 = Σ copies WHERE category==cat AND pool==RESERVE
        IF 主力数 > category_quota[cat][MAIN] OR 预备数 > category_quota[cat][RESERVE]: REJECT
    FOR g IN {HOWITZER, AT_GUN, ROCKET}:                    // R-13 火支子配额
        IF Σ copies WHERE quota_group==g > fire_support_subquota[g]: REJECT
    RETURN TRUE

FUNCTION cmd_purchase(world, player, template)              // 仅盲部署 phase
    slot = player.deck_slots.find(template)
    IF slot == NULL OR slot.copies_left <= 0: REJECT        // 一命制：卡组余量不回补
    IF player.points < template.cost: REJECT
    player.points −= template.cost; slot.copies_left −= 1
    player.spawn_queue.append(template)                     // 逐个间隔出牌

FUNCTION spawn_step(world)                                  // 每 spawn_interval_ticks 出一个
    FOR p IN players:
        IF p.spawn_queue == []: CONTINUE
        card = p.spawn_queue.pop(0)
        spawn_pos = (任意地图边缘(敌方部署区除外) IF flags.canInfiltrate     // R-04
                     ELSE 己方部署区锚点 + 出牌序偏移)
        unit = instantiate(card, p.team, p.index, spawn_pos) // 元素/武器弹药全部满编
        IF flags.canInfiltrate: unit.infiltration_timer = 600       // 渗透 60s

FUNCTION system_objectives(world)                           // 每秒
    FOR obj IN world.objectives:
        占点半径内存活单位 ∩ 各队 → 仅一方存在时 obj.owner = 该队
```

---

## §F8. 主循环与计时器

```
FUNCTION world_tick(world)                                  // 固定步长，10Hz
    world.tick += 1
    update_phase(world)                                     // 盲部署900→禁火450→实战13200→结算
    consume_commands(world)                                 // 命令驱动：本 tick 的命令全部落地
    system_timers(world)                                    // ①
    FOR unit IN world.units: system_move(world, unit)       // ② 移动（含随动）
    system_sensing(world)                                   // ③ 节流扫描
    FOR unit IN world.units: system_combat(world, unit)     // ④ 交战
    system_projectiles(world)                               // ⑤ 弹丸推进与命中（§F1/§F9）
    system_supply(world)                                    // ⑥ 后勤
    mount_requests_step(world)                              // ⑦ 上车进度
    IF world.tick % 10 == 0: system_economy(world)          // ⑧ 按秒：收入/出牌/占点
    world.units = [u FOR u IN world.units IF u.alive]       // 尸体清扫（alive 标记于 destroy）
    world.smoke_zones = [z FOR z IN … IF z.ttl_ticks > 0]

FUNCTION system_timers(world)
    FOR u IN alive_units:
        u.infiltration_timer = MAX(0, −1)
        FOR e IN u.elements:
            e.reveal_timer = MAX(0, −1)
            e.sprint_timer = MAX(0, −1)
            e.suppression  = MAX(0, e.suppression − sup_decay_per_tick)
        IF u.deploy_state == DEPLOYING: u.deploy_timer −= 1; IF <=0 → DEPLOYED
        IF u.deploy_state == PACKING:   u.deploy_timer −= 1; IF <=0 → MOBILE
        FOR ws IN 所有武器: IF ws.state IN {AIMING, RELOADING}: ws.timer = MAX(0, −1)

FUNCTION system_projectiles(world)
    FOR p IN world.projectiles:
        p.pos, arrived = step_toward(p.pos, p.dest, p.speed_cm_tick)
        IF NOT arrived: CONTINUE
        IF p.trajectory == BALLISTIC: resolve_blast(world, p)          // 含烟弹落点
        ELIF p.hit_target is AircraftRef:                              // §F9 对空
            resolve_hit_aa(world, p)
        ELIF p.will_hit: resolve_hit(world, p)                          // B9：目标亡则落空
        ELSE: inject_suppression_area(world, p.dest, p.weapon.blast_radius_cm,
                                      p.weapon.suppression_power)       // 近失：仅压制
    world.projectiles = [p FOR p IN … 未到达者]

FUNCTION system_economy(world)                              // 每秒；D038 池子挂钩点
    FOR p IN players: p.points += p.income_per_second
    spawn_step(world)                                       // 出牌节流（内部再按 interval 判）
    system_objectives(world)
```

---

## §F9. 对空结算接口（§12 航空契约；地面侧只读）

```
AircraftRef 航空系统提供（pos/alt_tier/hp/armor_aa/spotted_mask），地面侧不推进其运动。
FUNCTION fire_aa(world, e, ws, aircraft)                    // finish_aim 分支
    dist 检查 + acc 计算（同 fire_direct，无 markLevel/校射项）
    ws.ammo_left −= 1; RELOADING; 暴露; 声事件
    FOR i IN 1..salvo:
        will_hit = chance_bp(acc_bp)
        aim = aircraft.pos + 散布
        world.projectiles.append(… hit_target=aircraft, will_hit)
FUNCTION resolve_hit_aa(world, p)
    a = p.hit_target
    r  = penetration_at(p.weapon, dist_flew) // MAX(1, a.armor_aa)   // 飞机无分面，单值
    mult = r*r*1000 // (r*r + 1000)                                  // 对空一律 HE 曲线
    a.hp_current −= p.damage * mult // 1000                          // 击落判定归航空系统
"Flak 38 对空伤害更高" = 武器数值配平，无机制分支。
渗透班"引导空投"：SetAirdropBeaconCmd 写 unit.airdrop_beacon（不算暴露，不清渗透身份）；
    航空系统投散时读取该标记 → 散布 ×0.5（接口约定，公式在航空侧）。
```

---

## §A. 验收对照：§13 → 实现函数

| §13 问题 | 落地函数 |
|---|---|
| B1 武器缺射程/散布 | §D.3 字段 8/9/10 + §F4 select_target(min_range) + fire_direct(散布) |
| B2 狙击死代码 | §D.3 sniper_flag + §F4 ground_direct 狙击分支 + fire_sniper（含射程门） |
| B3 近战死代码 | §F4 ground_direct 近战分支 + fire_melee |
| B4 烟雾闭环 | §D.3 SMOKE 档案 + §F6 cmd_smoke + §F1 resolve_blast 生烟 + §F6 system_supply 同轨补弹 |
| B5 防空互斥 | §F4 system_combat ②对空并行 / ③按元素 mode 分流（mode 枚举无 AA） |
| B6 卡车槽位层级 | §D.5 元素级 mode/cargo/supply + §F6 cmd_set_element_mode / buy_supplies |
| B7 destroyElement | §F2 完整级联（车载/运兵/物资/拖曳/掩护/驻楼/全灭） |
| B8 pos 随动 | §F5 system_move + sync_followers（mounted/towed/cargo 三路） |
| B9 僵尸班 | §F4 fire_sniper 走 apply_damage + §D.4 不变式 + §F8 尸体清扫 |
| B10 装甲0除零 | §F1 damage_mult_permille 无甲守卫 |
| g-R01 标记消费 | §F4 fire_direct acc × calib_acc_bonus_bp |
| g-R15 自卫直射 | §F4 indirect_role 触发 + use_self_defense 档案 |
| g-伏击视野减半 | §F3 detection_range ×0.5 |
| g-fireAt/任务门控 | §F4.1 process_fire_mission 走 fire_permitted + fire_at 定义 + cmd_set_element_mode/start_tow 清任务 |
| g-拖曳解除 | §F2 stop_tow（四触发）+ §F6 cmd_untow + 修好自动解挂 |
| g-配额 | §F7 validate_deck + cmd_purchase 扣余量 |
| g-建筑进驻 | §F6 cmd_garrison / collapse_building（【拍板默认】） |
| g-载重混装 | §F6 buy_supplies 重量核算 |
| g-威胁值 | §F4 threat_value 可计算定义 |
| g-对空结算 | §F9 resolve_hit_aa 接口 |
| g-校射口径 | §F4.1 按发累积（calib_per_shot） |

**落地说明**：相对 v1.1 文档的两个工程槽已在 §D.5 声明（`garrison_in` 字段 + world 级上车进度表）；确定性整型改造见 §T（PCG32 通道、bp/permille、8 扇区朝向、方形散布、isqrt）。实现顺序建议：§D 数据结构 → §F1 命中结算（纯函数+锚点单测）→ §F3 侦察 → §F4 交战 → §F2/§F5/§F6/§F7/§F8 依序补齐。
