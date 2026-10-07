# 地面单位实现伪代码——§13 对照表落地版（v1.3-IMPL）

> 上游：GROUND_UNITS_PSEUDOCODE_v1.3.md（机制权威；口径映射见 §D.8）+ TECH-00（整型确定性约束）+ GDD-02-函数变量调用频率与替代方案.md（19 条方案，v1.2 落实）+ GDD-02-伪代码审查问题文档-v1.2.md（13 项审查问题，v1.3 修复——见文末 v1.3 变更记录）。
> 本文把 §13 对照表逐项落成**可直接照写代码的伪代码**：数据结构逐字段（类型/单位/默认值）、系统函数逐函数（签名/步骤体/边界）。
> 语言中立；不出现任何具体语言代码。
>
> **槽位账目（v1.3）**：单位静态 30 + 单位运行时 17 + 元素静态 14 + 元素运行时 15 + 工程槽 1（garrison_in，条件分配）= **77 槽**（v1.2 为 78：拖曳改元素级，删单位级 tow_pair 引用槽——v1.3 变更记录#12）；武器 **27** 子字段（含 name）。mounted_in 自 v1.3 起为全体 SQUAD 元素常驻槽（原 hasMount 条件槽——变更记录#8）。（v1.2=78、v1.1=82+27；变化明细见文末变更记录）
> **〔条件槽〕约定**：标注〔条件槽〕的运行时槽按模板能力在实例化时决定是否分配（方案7/12 等）；未分配时读取恒为 NULL/空表——各读取点的既有 NULL 判断即天然短路。

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
| 迭代 | 一切遍历走**插入序列表**，禁无序集合遍历（保证逐 tick 位级可复现）；旁表 map 亦按插入序实现 |

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
| sprint_duration_ticks | tick | 待定 | 疾跑时长；SprintCmd 写 sprint_until = now + 此值（方案14） |
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
| melee_range_cm | cm | 5000 | 近战阈值 50m（近战档案 max_range 上限，方案1） |
| ambush_acc_bonus_bp | bp | 13000 | R-12 脱伏击首击精度 |
| calib_acc_bonus_bp | bp | 12500 | R-01 侦察校准命中档 |
| calib_per_shot | 点/发 | 20 | 校射按发累积【拍板默认】 |
| calib_max_reduction_bp | bp | 6000 | 校射最大散布收束 |
| sup_penalty_bp | bp | 6000 | 压制满值精度惩罚 |
| sup_decay_per_tick | 点/tick | 1 | 压制自然衰减（近卫旗标 ×2，方案18） |
| crit_per_hp_bp | bp/HP | 1200 | 暴击概率系数 |
| front_arc / side_arc | 度 | 45 / 135 | 命中面扇区 |
| sniper_base_prob_bp | bp | 3000 | R-02 基础击杀概率 |
| sniper_cover_mult_bp | bp | 5000 | 反狙击掩护减半（第1轮） |
| sniper_tally_kills | 人 | 3 | 排内累计灭班线（R-02） |
| r18_radius_cm | cm | 8000 | R-18 自动补给半径 |
| ammo_resupply_per_tick | 发/tick | 2 | 每武器补弹速率（保留清单#10：烟弹同轨原样） |
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
| 15 | mode_set | Mode 位掩码 | DIRECT/INDIRECT/TOW/CARGO/TRANSPORT（无 AA）；v1.2 兼作交战分流与 fire_permitted 门、拖曳/载货门的静态位源（方案3/13）；被拖侧卡（中/重坦 R-19 维修拖曳、轻防空第11/12轮卡车牵引、**火支全部牵引炮与火箭炮**——v1.3 审查#10 补全）mode_set 须含 TOW 位，漏配即"拖曳中禁射"失效 |
| 16 | close_combat_bonus_permille | ‰ | 骑兵 1800；冲锋枪排高档；仅 combat_style==MELEE 武器读取（方案1） |
| 17 | tow_tonnage / 18 own_weight_tons | 吨 | R-19 |
| 19 | repair_power_hp_per_tick | int | D016 |
| 20 | supply_radius_cm | int | R-18（0/8000） |
| 21 | acoustic_signature | int | 声测定位权重（火箭炮最高） |
| 22 | sonar_radius_cm / 23 sonar_rate | int | R-03（侦听侧名单化条件，方案4） |
| 24 | aura | {kind: MELEE\|PRECISION, bonus_bp, radius_cm} \| null | 政委/军官；军官=PRECISION 精度+10%（射程项按方案17拍板移除） |
| 25 | flags | 位段 | canSprint canGarrison canAmbush canInfiltrate noMoveVisionPenalty forestWalkSilent requiresMark singleSquadCard hasCargo hasMount hasSupply（方案12，由 seats/cargo 派生） suppDecayX2（方案18 近卫意志近似；旗标名与机制版 v1.2 同名） |
| 26 | pool | MAIN/RESERVE | 双池 |
| 27 | per_card_limit | int | 指挥班组=1 |
| 28 | quota_group | 无/榴弹炮/反坦克炮/火箭炮 | 火支子配额 |
| 29 | unlock_by | str | 特化解锁 |
| 30 | element_count | 派生 | Σ element_groups 数量（不存） |

### D.2 ElementTemplate（元素静态 14）

| # | 字段 | 说明 |
|---|---|---|
| 1 | element_type | VEHICLE/GUN/SQUAD |
| 2 | unit_type | INFANTRY/MECH（bodyType 派生：MECH→HARD） |
| 3 | hp_max | MECH 车体血；SQUAD=编制人数（1HP=1人） |
| 4-5 | armor_ke{F,S,R,T} / armor_he{F,S,R,T} | 0-20 相对刻度；T 仅空袭读取；0=无甲合法 |
| 6 | fire_arc_deg | 360 或 ±15°（R-09）；==360 的模板不分配 rotating 槽（方案6） |
| 7 | suppression_vuln_permille | 敞篷 >1000 |
| 8 | squad_quality_bp | 老兵班 11500 |
| 9 | weapons[] | WeaponTemplate 列表 |
| 10 | mounted_armament | 空车可射击武器（251 车载 MG，第5轮） |
| 11 | seats | 运兵座位（卡车1班；0=不可载） |
| 12 | cargo_rounds_max / 13 cargo_medical_max | 每车 600 发 / 120 份（D065） |
| 14 | cargo_weight_max | 总载重（混装核算） |

（v1.1 的 #7 turret_traverse_deg_per_tick 已删——全文无消费点，方案15；"无炮塔"语义由 fire_arc_deg<360 + turn_rate_deg_per_tick 承载。）

### D.3 WeaponTemplate（武器 27 子字段）

| # | 字段 | 类型/说明 |
|---|---|---|
| 1 | name | — |
| 2 | target_mask | GROUND=1 / AIR_LOW=2 / AIR_MID=4 / AIR_HIGH=8 位掩码 |
| 3 | damage_type | KE/HE/SMOKE |
| 4 | pen_min / 5 pen_max | KE 远距~贴脸（0-20）；HE/SMOKE 相等 |
| 6 | damage | HP/发 |
| 7 | blast_radius_cm | — |
| 8 | max_range_cm / 9 min_range_cm | 迫击炮 250~1800；狙击档案 400；近战档案 0~5000（方案1）；默认 min=0 |
| 10 | dispersion_cm | 散布半径（方形散布） |
| 11 | accuracy_base_bp | 基础命中 bp（近战档案=10000 必中，方案1） |
| 12 | aim_time_ticks / 13 reload_time_ticks | 近战档案 aim≈0；狙击档案超长 aim+极低射速（方案1） |
| 14 | salvo | 连发数（机枪点射>1） |
| 15 | ammo_base / 16 ammo_weight | 基数（烟弹=SMOKE 武器档案，同轨）；每发补给重量 |
| 17 | projectile_speed_cm_per_tick | — |
| 18 | trajectory | DIRECT/BALLISTIC |
| 19 | suppression_power | 压制值/发 |
| 20 | crit_mod_permille | RPG/集束 >1000 |
| 21 | vs_fort_mult_permille | 工兵 2000 / ISU-HE 1500 / OT-34 2000 |
| 22 | ammo_profiles[] | 受限弹药档案数组：{count_left, pen_bonus}（钨芯=3发/穿+3），**余量存档内计数**（方案11，替代 special_ammo + special_ammo_left）；烟弹仍为独立 SMOKE 档不并入 |
| 23 | alt_profile | R-11 HE 档案 {damage, blast} \| null（AP 主炮共槽） |
| 24 | needs_deployed | R-05 |
| 25 | self_defense | R-15 {max_range_cm, accuracy_mult_bp} \| null（indirect_role 读取前判空，方案3） |
| 26 | combat_style | NORMAL/MELEE/SNIPER 条件位（方案1，替代 melee_flag/sniper_flag 路由旗标）：MELEE→伤害读 close_combat_bonus_permille 与 MELEE 光环、绕过装甲曲线；SNIPER→弹丸命中后进 R-02 结算分支；两者均不再参与 ground_direct/finish_aim 路由 |
| 27 | reveal_time_ticks | 开火暴露时长（联动声测） |

**档案配置示例（方案1）**：近战=骑枪/刺刀档案 {min_range:0, max_range:5000, aim_time:0, accuracy_base_bp:10000, combat_style:MELEE}；狙击={max_range:400, aim_time 超长, reload_time 极长, combat_style:SNIPER}。

### D.4 UnitInstance（单位运行时 18）

| # | 字段 | 类型/说明 |
|---|---|---|
| 1 | unit_id / 2 team / 3 player_index | — |
| 4 | pos | (cm,cm) 队形基准 |
| 5 | elements[] | ElementInstance；**不变式：数组内必然存活** |
| 6 | move_path[] | 航点表 |
| 7 | deploy_state / 8 deploy_timer | MOBILE/DEPLOYING/DEPLOYED/PACKING |
| 9 | stance | 自由/禁射（不约束对空武器） |
| 10 | fire_mission | FireMission \| null（R-13）；校射两槽已下沉任务体（方案10） |
| 11 | mark_level / 12 spotted_mask | 无/发现/校准；队伍位掩码 |
| 13 | infiltration_timer | R-04（600 tick）；仅 canInfiltrate 卡分配并参与衰减（方案8） |
| 14 | ambush_active / 15 ambush_shot_bonus | R-12 |
| 16 | sprint_until | 疾跑到期 tick 时间戳（方案14；机制版挂元素级主元素——§D.8） |
| 17 | r02_kill_tally / alive | 狙击计数 / 存活 |

（v1.1 的 calib_target/calib_progress 下沉 FireMission、sniper_cover_target/airdrop_beacon 迁 world 旁表，方案9/10；方案10 的"最近任务收束缓存"变体**未采纳**——机制版 v1.2 同款拍板，直射仅在活跃任务期读 fm.calib_progress，任务结束无收束。v1.3：单位级 tow_pair 槽删除——拖曳改元素级 TowPair{tower_elements, towed_element}，"拖曳中"判定 = ANY(e.towed==TOWED)，见 §F2 start_tow 与变更记录#12。）

### D.5 ElementInstance（元素运行时 15 + 1 工程槽；表内序号至 17，系含 unit/template 两个引用槽）

| # | 字段 | 说明 |
|---|---|---|
| 1 | element_id / 2 unit / 3 template | — |
| 4 | pos / 5 facing(度) | 各自占位与车体朝向 |
| 6 | hp_current | 血条即兵力（SQUAD：1HP=1人） |
| 7 | crit{FC,SEN,RLD,MOB} | NONE/MINOR/MAJOR；〔条件槽：仅 unit_type==MECH 元素分配，其余恒 NULL，方案7〕修饰器读槽前判空 |
| 8 | suppression | 0..100 |
| 9 | reveal_timer | 开火暴露残留 |
| 10 | mounted_in | 载具元素引用（R-07 同卡 / D065 跨卡）；v1.3 起为**全体 SQUAD 元素常驻槽**（原 hasMount 条件槽使无座位步兵卡派生不出槽、跨卡运兵无确定承载——审查#8）；非 SQUAD 元素恒 NULL |
| 11 | weapon_states[] | {template, state, timer, target, ammo_left, use_self_defense}；state∈READY/AIMING/RELOADING/EMPTY（方案19 显式 EMPTY 迁移；special_ammo_left 已删，方案11） |
| 12 | rotating | 转向中→受弹按侧面（R-09）；〔条件槽：仅 fire_arc_deg<360 模板分配，方案6〕 |
| 13 | towed | NONE/TOWED |
| 14 | mode | DIRECT/INDIRECT/TOW/CARGO/TRANSPORT（卡车每辆独立，D065） |
| 15 | cargo_units[] | 跨卡载运的班 UnitInstance（D065 运兵）；〔条件槽：仅 hasCargo 元素分配，方案12〕 |
| 16 | supply_rounds / 17 supply_medical | 本车在途物资（CARGO）；〔条件槽：仅 hasSupply 元素分配，方案12〕 |
| 工1 | garrison_in | 驻楼 Building 引用（§7 驻建筑）；〔条件槽：仅 flags.canGarrison 步兵卡分配，方案5〕 |
| 工2 | （上车进度不占字段） | world.mount_requests: [{squad_unit, carrier, ticks_left}]（惰性建表，方案12） |

### D.6 世界实体与寄存器

```
Projectile   {shooter:Element, weapon:WT, damage_type, damage, blast_cm, pen_bonus,
              pos, dest, speed_cm_tick, trajectory, hit_target: Element|AircraftRef|Building|None,
              will_hit: BOOL}                        // v1.3：Building 入列——工兵/ISU 直射拆楼（审查#5）
SmokeZone    {pos, radius_cm, ttl_ticks}
IntelCircle  {team, center, radius_cm}                    // R-03 冻结精度，不撤销
SoundTrack   {unit, pos, accum}                            // 每敌开火单位一条
Building     {id, pos, hp, garrison_slots, garrisoned[Element]}
AircraftRef  {id, team, pos, alt_tier, hp_current, hp_max, armor_aa, spotted_mask}   // §12 航空契约
Objective    {id, pos, radius_cm, owner}
TowPair      {tower_elements[Element], towed_element:Element}   // v1.3：元素级（审查#12）——单卡2车并拖/拖单门炮可表达
FireMission  {form: POINT|LINE|CREEP, target_point, target_line[a,b], creep_speed_cm_tick,
              ammo_mult(1..3), salvo_mode: FULL|HALF, shots_left, started_tick,
              calib_target, calib_progress}               // 方案10：校射两槽下沉任务体（连内共享=同任务参与者共享同一 fm）；
                                                            // 任务体销毁（耗尽/取消/拖曳/切模清任务）进度随之失效——直射仅在活跃任务期读收束（机制版同款）
DeckSlot     {template, copies_left}
PlayerState  {index, team, points, deck_slots[], spawn_queue[], income_per_second}

WORLD        {tick, phase(盲部署/禁火/实战/结算), seed, rng_channels[7],
              units[], players[], projectiles[], smoke_zones[], intel_circles[],
              sound_tracks[], buildings[], objectives[], tow_pairs[], aircraft[],
              mount_requests[],                            // 惰性建表（方案12：首条请求才建）
              aa_roster[],                                 // 方案2：对空开火/对空探测名单（部署时按模板登记）
              beacon_by_unit{}, cover_by_target{},         // 方案9：空投信标/狙击掩护旁表（插入序 map）
              await_resupply[],                            // 方案19 + v1.3（审查#11）：待补给单位集合（弹药缺口/步兵带伤登记——弃"仅EMPTY"收窄，保 R-18"补满缺口"）
              next_element_id}
// v1.1 曾在 system_supply 引用而 §D.6 漏列的 world.supply_boxes 已删（方案16）：空投箱落地即
// 实例化为一次性 CARGO 单位，进 units[]，文档缺口随之消除。
```

### D.7 命令集（命令驱动；回放 = 种子 + 命令流）

```
MoveCmd{unit, path}  StopCmd{unit}  DeployCmd{unit}  PackCmd{unit}
SetModeCmd{element, mode}                                    // D065 三模式/火炮双职
PurchaseCmd{player, template}                                // 仅盲部署 phase
FireMissionCmd{unit, form, point|line, ammo_mult, salvo_mode, creep_speed}
CancelFireMissionCmd{unit}   SmokeCmd{element, point}         // 烟弹发射唯一入口
SetStanceCmd{unit, stance}   ToggleAmbushCmd{unit}   SprintCmd{unit}   // SprintCmd 写 unit.sprint_until（方案14）
GarrisonCmd{unit, building}  UnGarrisonCmd{unit}
MountCmd{squad_unit, carrier_unit}  DismountCmd{squad_unit}
TowCmd{tower_elements[], towed_element}  UntowCmd{element}      // v1.3：元素级（审查#12）
AttackCmd{element, target: Element|Building}                    // v1.3：直射指定目标（含建筑——审查#5；cmd_attack 见 §F4）
SetSniperCoverCmd{sniper_unit, target_unit}                  // 写 world.cover_by_target（方案9）
SetAirdropBeaconCmd{unit, pos}                               // 写 world.beacon_by_unit（方案9）
BuySuppliesCmd{truck_element, rounds, medical}
```

### D.8 与机制版 v1.2（GROUND_UNITS_PSEUDOCODE_v1.2.md）的口径映射表

> 两份 v1.2 行为同向（方案10 已统一拍板）；下列为实现等价的口径差，跨文档对照与编码按下表对表。机制语义冲突时以 GDD-02 为准。

| # | 项 | IMPL v1.2（本文） | 机制版 v1.2 | 对齐说明 |
|---|---|---|---|---|
| 1 | 武器子字段计数 | 27（含 name） | 26（不含 name） | 同一结构；另 combat_style（1 位，方案1）↔ meleeFlag+sniperFlag（2 位）、alt_profile+ammo_profiles（受限档）↔ ammoProfiles（全档集）——承载等价，计数差即 name |
| 2 | 疾跑时间戳归口 | unit.sprint_until（D.4#17；SprintCmd 写单位，全卡生效） | ElementInstance.sprintUntil（读主元素） | 等价口径差：单位级 vs 元素级（主元素）；两版分项账目随之差 1 |
| 3 | garrison 槽归口 | 工程槽单列（元素运行时 15 + 工程槽 1） | 计入 ElementInstance.garrisonedIn（元素运行时 17） | 归口差，槽位本体一致（仅 canGarrison 条件分配，方案5） |
| 4 | 对空名单粒度 | world.aa_roster 存 Unit（§F7 spawn_step 登记） | aaRoster 存 Element | 登记条件相同（AIR 武器位或 optics_air_cm>0，方案2）；消费按 unit↔elements 归并，等价 |
| 5 | 掩护旁表值型 | cover_by_target：被掩护 unit → 掩护者列表；消费=存在性布尔（多掩护者不叠加） | coverByTarget：被掩护 unitId → 单个掩护 unitId（后者覆盖前者） | 两版消费均为"是否有掩护"布尔、减半不叠加——结果等价；同目标多狙击的并存/覆盖行为 GDD-02 第1轮未规定（该轮仅拍板每狙击可掩护一个友军单位），如需明确叠加/互斥须另行拍板 |
| 6 | 压制衰减旗标 | suppDecayX2 | suppDecayX2 | 同名（走查前本文曾用 supDecayDoubled，已统一） |
| 7 | 曲射分流承载 | 查询期模板位测试（mode_set & INDIRECT，§F4 system_combat） | indirectDispatch 表 + setElementMode 动态刷新 | 语义等价（模板静态能力一致）；本文无运行时扩位兜底为方案3 已接受代价，mech 分发表刷新即其对应物 |
| 8 | 槽位账目 | 78 = 30 + 18 + 14 + 15 + 1 工程槽 | 78 = 30 + 17 + 14 + 17 | 总账同向；分项差 = ②③ 归口 |
| 9 | 方案19 医疗扫描口径 | 医疗随待补给集合服务（登记条件含步兵带伤，apply_damage 即登记→集合自清理） | 医疗保持全半径扫描（不入集合，补弹才走 pendingResupply） | 行为等价：本文任一带伤步兵必已登记在集合（needs_resupply 含带伤判据），R-18 医疗承载不受影响（保留清单#9 两版均保） |

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
    IF tgt is Building:                                    // v1.3（审查#5）：直射建筑——×vs_fort、无装甲曲线（GDD-02 为准，疑点②闭合）
        hit_building(world, tgt, p.damage * p.weapon.vs_fort_mult_permille // 1000
                                        * squad_hp_factor_bp(p.shooter) // 10000)
        inject_suppression_area(world, tgt.pos, p.weapon.blast_radius_cm, p.weapon.suppression_power)
        RETURN
    IF tgt NOT alive: RETURN                              // 目标已在飞行中阵亡 → 按失的落空
    // 方案1：combat_style 结算分支（狙击/近战不再有独立 fire 函数，语义原样搬入）
    IF p.weapon.combat_style == SNIPER:
        resolve_sniper_hit(world, p, tgt); RETURN         // R-02 概率结算，不走装甲/暴击曲线
    IF p.weapon.combat_style == MELEE:
        resolve_melee_hit(world, p, tgt); RETURN          // 近战伤害，绕过装甲曲线
    approach = approach_deg_of(p.pos, tgt.pos)            // 8 扇区整型
    facing  = (TOP IF p.top_attack ELSE facing_of(tgt.facing, approach,
                                                   cfg.front_arc, cfg.side_arc))
    IF tgt.template.fire_arc_deg < 360 AND tgt.rotating: facing = SIDE   // R-09（方案6：炮塔车/全向基座无 rotating 槽，模板短路）
    IF tgt.garrison_in != NULL: facing = REAR              // v1.3：驻楼受击参考尾甲（原注释宣称两处实现只落地一处——补齐）
    pen  = penetration_at(p.weapon, dist_cm(p.pos, tgt.pos), p.pen_bonus)
    dmg  = compute_direct_damage(tgt, facing, p.damage_type, pen, p.damage, p.shooter)
    apply_damage(world, tgt, dmg)                         // 唯一伤害入口（§F2）
    IF tgt alive AND tgt.template.unit_type == MECH:
        crit = roll_crit(world.rng[CRIT], dmg, p.weapon.crit_mod_permille)
        IF crit: upgrade_crit(tgt.crit, crit)             // 只升不降（非 MECH 元素无 crit 槽，此门已挡）
    inject_suppression_area(world, tgt.pos, p.weapon.blast_radius_cm,
                            p.weapon.suppression_power)   // 目标+溅射圈内近旁

FUNCTION resolve_sniper_hit(world, p, tgt_elem)           // 方案1：原 fire_sniper 结算体原样搬入（R-02）
    tgt_unit = tgt_elem.unit
    covered = cover_by_target 含 tgt_unit 键               // 方案9：掩护改查旁表
    prob = sniper_base_prob_bp * (covered ? sniper_cover_mult_bp // 10000 : 10000)
    rng = world.rng[SNIPER]
    squads = [班元素 OF tgt_unit] 或 全部元素
    IF tgt_unit.template.flags.singleSquadCard:           // 指挥班组/声测班：概率灭排
        IF rng.chance_bp(prob): apply_damage(world, squads[0], squads[0].hp_current)
        RETURN
    kills = rng.chance_bp(prob) + rng.chance_bp(prob)     // 1~2 人（先命中[fire_direct 的 HIT 掷]再判定——方案1 已接受的方差变化）
    IF kills > 0:
        apply_damage(world, squads[0], MIN(kills, squads[0].hp_current)) // 走统一伤害入口——B9
        tgt_unit.r02_kill_tally += kills
    IF tgt_unit.r02_kill_tally >= sniper_tally_kills:     // ≥3人=损失1班
        lowest = MIN(存活元素, by hp_current)
        apply_damage(world, lowest, lowest.hp_current)
        tgt_unit.r02_kill_tally −= sniper_tally_kills

FUNCTION resolve_melee_hit(world, p, tgt_elem)            // 方案1：原 fire_melee 结算体原样搬入
    bonus = p.shooter.unit.template.close_combat_bonus_permille              // 骑兵1800
    bonus = bonus * aura_bonus_bp(p.shooter.unit.team, MELEE, tgt_elem.pos) // 10000  // 政委督战光环（消费点随方案1挪入直射伤害链——光环会同时放大近距射击，负面影响已接受）
    dmg = p.weapon.damage * bonus // 1000
    apply_damage(world, tgt_elem, dmg)
    inject_suppression(tgt_elem, p.weapon.suppression_power)
    //（弹药/装填/暴露/渗透清零已上移 fire_direct 统一处理）

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
aim_factor_bp(e)     = (e.crit == NULL ? 无crit项                      // 方案7：非 MECH 元素无槽
                        : critFC{MINOR:×0.75, MAJOR:×0.5})
                       × (10000 − sup_penalty_bp×sup//100)   下限1000
reload_factor_bp(e)  = (e.crit == NULL ? 无crit项
                        : critRLD{MINOR:×1.3, MAJOR:×1.6})
                       × (10000 + sup_penalty_bp×sup//100)
optics_factor_bp(e)  = (e.crit == NULL ? 10000 : critSEN{MINOR:0.6, MAJOR:0.3})
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
    ELSE IF needs_resupply(elem.unit) AND elem.unit NOT IN world.await_resupply:
        world.await_resupply.append(elem.unit)            // 方案19：步兵带伤即登记待补给（保 R-18 医疗）

FUNCTION needs_resupply(u) → BOOL                         // v1.3（审查#11）：登记/保持条件=任一缺口（弹药未满或步兵带伤）
    IF ANY(ws.ammo_left < ws.template.ammo_base FOR ws IN 全部武器): RETURN TRUE   // 原"仅EMPTY"收窄违背 R-18"补满缺口"，弃用
    IF ANY(e INFANTRY AND 0 < e.hp_current < e.template.hp_max FOR e IN u.elements): RETURN TRUE
    RETURN FALSE

FUNCTION mark_resupply_if_needed(world, u)                // v1.3：弹药消耗/受伤点统一调用（事件登记，免每tick全扫）
    IF u.alive AND needs_resupply(u) AND u NOT IN world.await_resupply:
        world.await_resupply.append(u)

FUNCTION destroy_element(world, elem)                     // B7：完整定义
    unit = elem.unit
    unit.elements.remove(elem)                            // 物理移除，维持 §D.4 不变式
    // v1.3（审查#1）：车载连带去重——统一装载对同卡写 mounted_in、跨卡写 mounted_in+cargo_units，
    // 原两环串联对同一班连扣两次 60%（10人班→4人→1人）。改为按元素收集一次、只结算一次：
    受影响班元素 = [s FOR s IN all_alive_elements(world) WHERE s.mounted_in == elem]
    IF elem.cargo_units != NULL:
        FOR squad IN list(elem.cargo_units):
            squad.pos = elem.pos; squad.move_path.clear()
            FOR se IN list(squad.elements):
                IF se NOT IN 受影响班元素: 受影响班元素.append(se)   // 跨卡班元素亦挂 mounted_in，按元素去重
        elem.cargo_units = []
    FOR s IN 受影响班元素:
        s.mounted_in = None
        s.pos = elem.pos 旁落位
        apply_damage(world, s, ceil(s.hp_current × 60%))  // 整型: (hp*600+999)//1000——每元素仅一次，"剩40%血"承诺恢复
    IF elem 有 hasSupply 槽: elem.supply_rounds = 0; elem.supply_medical = 0
    // 驻楼引用清理（garrison_in 为条件槽——方案5）
    IF elem.garrison_in != NULL: elem.garrison_in.garrisoned.remove(elem); elem.garrison_in = None
    // 拖曳连带
    release_tow_if_involved(world, unit)
    // 方案9：反狙击掩护/空投信标改按键注销（替代 v1.1 的全单位遍历清理）
    IF unit.elements == []:
        unregister_unit_refs(world, unit)
        unit.alive = False                                // 全灭：一命制（无回圈无退款）；声测圈不撤销（R-03 冻结）；光环/侦听随清空自然失效

FUNCTION unregister_unit_refs(world, unit)                // 方案9：所有销毁路径收口到此注销函数
    world.beacon_by_unit.remove(unit)                     // 空投信标注销（unit 作为标定者）
    world.cover_by_target.remove(unit)                    // unit 作为被掩护对象 → 整键注销
    FOR (tgt, protectors) IN world.cover_by_target 按插入序:
        protectors.remove(unit)                           // unit 作为掩护者 → 从名单移除
        IF protectors == []: world.cover_by_target 删除 tgt 键   // v1.3：空键不删→掩护者全灭后目标恒判 covered（终审遗留）

FUNCTION start_tow(world, tower_elements[], towed_element) → BOOL   // v1.3（审查#12）：元素级拖曳
    IF towed_element.towed == TOWED OR tower_elements == []: RETURN FALSE
    sorted = tower_elements 按模板 tow_tonnage 降序（稳定排序，并列取原序）   // 杜绝"30t车被指派45t任务"（原按命令序切片）
    acc = 0; chosen = []
    FOR t IN sorted:
        chosen.append(t); acc += t.template.tow_tonnage
        IF acc >= towed_element.template.own_weight_tons: BREAK
    IF acc < towed_element.template.own_weight_tons: RETURN FALSE   // 吨位不足（重坦45t=2×30t 并拖或 1×45t——单卡2车并拖可表达）
    pair = TowPair(tower_elements=chosen, towed_element=towed_element)
    world.tow_pairs.append(pair)
    FOR t IN chosen: t.towed = TOWED                       // 牵引元素（不再整队置位）
    towed_element.towed = TOWED                            // 被拖元素（如单门炮——不再整卡同拖）
    IF towed_element.unit.fire_mission != NULL: towed_element.unit.fire_mission = None   // 拖曳取消炮击任务（方案10）
    RETURN TRUE

FUNCTION stop_tow(world, pair, reason ∈ {VOLUNTARY, REPAIRED, DESTROYED})
    FOR t IN pair.tower_elements: t.towed = NONE
    pair.towed_element.towed = NONE
    world.tow_pairs.remove(pair)                          // 被拖者 MOB 暴击保留（REPAIRED 时已先修）

FUNCTION release_tow_if_involved(world, unit)
    FOR pair IN [p FOR p IN world.tow_pairs IF p 涉及 unit 任一元素]:
        stop_tow(world, pair, DESTROYED)                   // v1.3：元素级——一单位多对拖曳各自解除

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
    IF unit.infiltration_timer > 0: m = m * infiltration_mult_bp // 10000    // 读取点不动（方案8）
    IF unit.ambush_active:          m = m * ambush_mult_bp // 10000
    IF ANY(e.reveal_timer > 0 FOR e IN unit.elements): m = m * reveal_mult_bp // 10000
    s = s * m // 10000
    IF unit.template.flags.canGarrison AND ANY(e.garrison_in != NULL):       // 方案5：模板前置短路
        s += garrison_stealth_add * 10
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

FUNCTION point_in_friendly_vision(world, team, pt) → BOOL  // v1.3（审查#13）：定义体补齐——校射视线判定
    // R-06"遮断校射"承载：穿林/穿烟衰减计入（烟墙后的目标点不收束）；点目标按隐蔽中位档(5)近似
    FOR obs IN 该队 alive_units:
        r = obs.template.optics_ground_cm * stealth_factor_bp[5] // 10000
        r −= detect_atten_per_m * (world.los_forest_m(obs.pos, pt) + world.los_smoke_m(obs.pos, pt))
        IF dist_cm(obs.pos, pt) <= MAX(0, r): RETURN TRUE
    RETURN FALSE

FUNCTION system_sensing(world)                              // 每 sensing_period_ticks 一次
    FOR obs IN alive_units, FOR tgt IN 敌方 alive_units:
        d = dist_cm(obs.pos, tgt.pos)
        IF d <= detection_range_cm(obs, tgt):
            tgt.spotted_mask |= 1 << obs.team
            IF obs.template.category == 侦察: tgt.mark_level = CALIBRATED    // R-01
            ELIF tgt.mark_level < SPOTTED:    tgt.mark_level = SPOTTED
        ELIF d > keep_range_cm(obs, tgt):
            IF NOT ANY(同队其他观察者仍保持): tgt.spotted_mask &= ~(1 << obs.team)
    sense_air(world)                                       // R-17/R-23（AA 分支名单化，方案2）
    sonar_listeners = [u FOR u IN alive_units
                       WHERE u.template.sonar_radius_cm > 0 AND u.deploy_state == DEPLOYED]
    IF sonar_listeners != []: sonar_step(world, sonar_listeners)   // 方案4：名单空→整段跳过，IntelCircle 不再生成（盲射圈随之不再新增——负面影响已接受）
    // fire_direct / fire_at 的 upsert_sound_track 写侧原样保留（保留清单#3）

FUNCTION sense_air(world)                                   // R-17；方案2：探测分支名单化
    FOR a IN world.aircraft:
        FOR g IN 敌方 alive_units WHERE g IN world.aa_roster:          // 防空体系探测——仅名单（方案2）
            IF a.alt_tier <= g.air_ceiling AND dist <= g.optics_air_cm:
                a.spotted_mask |= 1 << g.team
        FOR g IN 敌方 alive_units:                                      // 低空目视分支保留不动（方案2）
            IF a.alt_tier == LOW AND dist <= g.optics_ground_cm:
                a.spotted_mask |= 1 << g.team

FUNCTION sonar_step(world, listeners_pool)                  // R-03：开火越久定位越准（读侧名单化，方案4）
    FOR track IN world.sound_tracks:                        // SoundTrack 于 fire() 时 upsert（写侧不动）
        listeners = [u FOR u IN listeners_pool
                     WHERE u.team != track.unit.team
                       AND dist_cm(u.pos, track.pos) <= u.template.sonar_radius_cm]
        IF listeners == []: CONTINUE                        // 声测班移动/阵亡→圈冻结不撤销
        track.accum += MAX(sonar_rate) * track.unit.template.acoustic_signature
        IF track.accum >= cfg.sonar_locate_threshold:
            radius = LERP(sonar_max_radius_cm, sonar_min_radius_cm,
                          MIN(1, (accum−threshold) ÷ threshold))     // 圈随时长收窄
            upsert IntelCircle(team=listeners[0].team, center=track.pos, radius)  // v1.3（审查#2）：圈记侦听方队——原记到被侦听敌方名下，消费链永远匹配不上
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
        //    方案2：仅 aa_roster 名单单位执行（名单按模板登记于部署期，运行时不重建——负面影响已接受）
        IF unit.alive AND unit IN world.aa_roster:
            FOR ws IN e.weapon_states
                    WHERE ws.template.target_mask & AIR AND ws.state == READY AND ws.ammo_left > 0:
                aa_try_engage(world, e, ws)
        // ③ 对地：按元素 mode 分流；方案3：indirect 分流加模板 mode_set 静态门（分发表=模板位测试）
        IF e.mode == DIRECT:      ground_direct(world, unit, e)
        ELIF e.mode == INDIRECT AND (unit.template.mode_set & INDIRECT): indirect_role(world, unit, e)
        // TOW/CARGO/TRANSPORT：不开火（开火许可亦拦截）
    IF (unit.template.mode_set & INDIRECT)                        // 方案3：无 INDIRECT 位模板不问
       AND unit.fire_mission != NULL AND ANY(e.mode == INDIRECT):
        process_fire_mission(world, unit)

FUNCTION fire_permitted(world, unit, e, ws) → BOOL
    IF world.phase != 实战: RETURN FALSE                    // 禁火 phase 门
    IF unit.stance == HOLD_FIRE: RETURN FALSE               // 不约束对空（对空走②）
    IF ws.template.needs_deployed AND unit.deploy_state != DEPLOYED: RETURN FALSE  // R-05
    IF e.mounted_in != NULL AND ws.template 不是 mounted_armament: RETURN FALSE
    ms = unit.template.mode_set
    IF (ms & TOW) AND e.towed == TOWED: RETURN FALSE        // R-19 拖曳双方禁射（方案13：模板无 TOW 位则不问；轻防空被拖侧 mode_set 须含 TOW）
    IF (ms & (TOW|CARGO|TRANSPORT)) AND e.mode IN {TOW, CARGO, TRANSPORT}: RETURN FALSE  // D065 载货状态不作战（方案13）
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
    // 方案17：军官射程+10% 项不补消费点（拍板改纯精度光环），本函数不读 aura

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
        // 方案1：melee_flag/sniper_flag 路由分支取消——近战/狙击均由武器档案表达
        //（近战 max_range=5000/aim≈0/必中；狙击 max_range=400/超长 aim/极低射速），
        //  统一走 select_target 射程过滤 → 射界门 → begin_aim 的直射主链。
        tgt = select_target(world, e, ws)
        IF tgt == NULL: CONTINUE
        want = approach_deg_of(tgt.pos, e.pos)
        IF |angle_diff(e.facing, want)| > e.template.fire_arc_deg:      // R-09
            rotate_step(world, e, want); CONTINUE                        // 射界外先转车体（fire_arc==360 模板恒不进此分支——方案6）
        begin_aim(world, e, ws, tgt)

FUNCTION indirect_role(world, unit, e)
    w_main = e.weapon_states[0]
    // 自卫直射—— g-R15 修复：曲射炮被近身时以惩罚档案直射（与炮击任务经 weaponStates 忙碌互斥）
    // 方案3：self_defense!=NULL 一行短路（消除无自卫档案炮卡每tick裸检查风险）
    IF w_main.self_defense != NULL
       AND w_main.state == READY AND fire_permitted(world, unit, e, w_main)
       AND ANY(敌元素 dist <= w_main.self_defense.max_range_cm):
        near = 最近敌元素
        w_main.use_self_defense = TRUE
        begin_aim(world, e, w_main, near)
    // 否则炮击任务在 system_combat 尾部统一推进

FUNCTION finish_aim(world, e, ws)
    tgt = ws.target
    IF tgt == NULL OR NOT alive(tgt): ws.state = READY; RETURN       // 不消耗弹药
    IF is_aircraft(tgt):
        fire_aa(world, e, ws, tgt)
    ELSE:
        fire_direct(world, e, ws, tgt)                    // 方案1：狙击/近战不再专路，统一直射链

FUNCTION select_profile(world, e, ws, tgt) → {damage_type, damage, blast_cm, pen_bonus}
    w = ws.template
    // R-11 自动选弹（共槽）：软目标优先 HE 档案
    IF w.alt_profile != NULL AND tgt.template.unit_type == INFANTRY:
        RETURN HE档案(w.alt_profile)
    // 方案11：受限弹药档案（钨芯）并入 ammo_profiles——常规 AP 打不动正面且档内有存货 → 自动救场，
    // 余量在档内计数（special_ammo_left 变量已删）；"仅正面打不穿才切"条件原样保留（第11轮语义）
    FOR prof IN w.ammo_profiles:
        IF prof.count_left > 0 AND tgt.template.unit_type == MECH
           AND w.pen_max < tgt.template.armor_ke.front:
            prof.count_left −= 1
            RETURN 默认AP(pen_bonus=+prof.pen_bonus)
    RETURN 默认档案

FUNCTION fire_direct(world, e, ws, tgt)
    unit = e.unit; w = ws.template
    IF tgt is Building: prof = {damage_type: HE, damage: w.damage, blast_cm: w.blast_radius_cm, pen_bonus: 0}
    ELSE:               prof = select_profile(world, e, ws, tgt)     // v1.3：建筑无 unit_type，跳过自动选弹（审查#5）
    ws.ammo_left −= 1
    mark_resupply_if_needed(world, unit)                   // v1.3（审查#11）：弹药缺口即登记
    ws.state = RELOADING; ws.timer = MAX(1, w.reload_time_ticks * reload_factor_bp(e)//10000)
    e.reveal_timer = MAX(e.reveal_timer, w.reveal_time_ticks)          // 开火暴露
    upsert_sound_track(world, unit, e.pos)                             // 喂声测 R-03（写侧不动，方案4）
    IF w.combat_style IN {MELEE, SNIPER} AND unit.infiltration_timer > 0:
        unit.infiltration_timer = 0                                    // 方案1：渗透身份清零随原 fire_sniper/fire_melee
                                                                       // 迁入此处；普通自卫开火不清——语义以 IMPL 为准（方案8）
    dist = dist_cm(e.pos, tgt.pos)
    acc_bp = w.accuracy_base_bp
           × accuracy_ratio_bp(dist // MAX(1, w.max_range_cm))          // 17 段查表，默认全 10000
           × aim_factor_bp(e)
           × (unit.ambush_shot_bonus ? ambush_acc_bonus_bp : 10000)      // R-12 首击，打完清
           × aura_bonus_bp(unit.team, PRECISION, e.pos) // 10000          // 军官光环（方案17：仅精度项）
           × e.template.squad_quality_bp // 10000                         // 老兵班
           × (tgt is Building ? 10000 :
              tgt.unit.mark_level == CALIBRATED ? calib_acc_bonus_bp : 10000)  // R-01 消费（建筑无标记——v1.3）
           × (ws.use_self_defense ? w.self_defense.accuracy_mult_bp : 10000)   // R-15 惩罚
    unit.ambush_shot_bonus = FALSE
    // 方案10（机制版 v1.2 同款拍板）：直射散布收束仅在有活跃炮击任务时读 fm.calib_progress；
    // 任务结束/无任务 = 无收束（"最近任务收束缓存"变体未采纳，双职炮直射不吃历史校射——已接受代价）
    calib_reduction_bp = (unit.fire_mission != NULL)
                       ? 10000 − unit.fire_mission.calib_progress * calib_max_reduction_bp // 100
                       : 10000
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
    ws.use_self_defense = FALSE                            // v1.3：自卫档案一次性，发射即复位（疑点④闭合——52-K/88 直射不被永久污染）

FUNCTION aa_try_engage(world, e, ws)                      // B5 修复的另一半（进入条件已由 system_combat ② 名单化——方案2）
    IF e.towed == TOWED OR ANY(x.towed == TOWED FOR x IN e.unit.elements):
        RETURN                                            // v1.3（审查#9）：R-19 拖曳双方禁射扩展至对空链（疑点⑤闭合——被拖防空不再自动开火）
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
    FOR c IN world.intel_circles WHERE c.team == gun.unit.team
         AND dist_cm(c.center, pt) <= c.radius_cm: extra = MAX(extra, c.radius_cm)
    // 连内共享校射 R-16（方案10：进度/目标下沉任务体 fm.calib_*；两连打同点各有 fm，互不叠加语义保留）：
    // 落点在友军视野内才逐发收束
    IF point_in_friendly_vision(world, gun.unit.team, fm.target_point):   // v1.3：补 team 实参；定义体 §F3 含烟/林遮断（审查#13）
        fm.calib_progress = MIN(100, fm.calib_progress + cfg.calib_per_shot)     // 按发累积
    IF fm.target_point != fm.calib_target: fm.calib_target = fm.target_point;
                                             fm.calib_progress = 0              // 换点重置
    scatter_cm = w.dispersion_cm * (10000 − fm.calib_progress*calib_max_reduction_bp//100)//10000
               + extra
    aim = pt + (world.rng[SCATTER].sym(scatter_cm), world.rng[SCATTER].sym(scatter_cm))
    ws.ammo_left −= 1; ws.state = RELOADING; ws.timer = reload…
    mark_resupply_if_needed(world, gun.unit)               // v1.3（审查#11）
    fm.shots_left −= 1
    upsert_sound_track(world, gun.unit, gun.pos)          // 火箭炮 acoustic_signature 最高→最快被定位（写侧不动，方案4）
    world.projectiles.append(Projectile(shooter=gun, weapon=w, profile=默认HE,
        pos=gun.pos, dest=aim, speed=w.projectile_speed_cm_tick,
        trajectory=BALLISTIC, hit_target=NULL, will_hit=FALSE))
    IF fm.shots_left <= 0: gun.unit.fire_mission = None   // 方案10：任务体销毁，校射进度随之失效

FUNCTION cmd_fire_mission(world, unit, form, point_or_line, ammo_mult, salvo_mode, creep_speed)
                                                           // v1.3（审查-原始行）：任务创建入口——原全文只有清空写点，任务永远无法下达
    IF NOT (unit.template.mode_set & INDIRECT): REJECT
    guns = [e FOR e IN unit.elements IF e.mode == INDIRECT]
    IF guns == []: REJECT
    shots = LEN(guns) × guns[0] 主武器 ammo_base × ammo_mult      // R-13 弹量基数（一倍/两倍/三倍）
    unit.fire_mission = FireMission{form, point_or_line, creep_speed, ammo_mult, salvo_mode,
                                    shots_left = shots, started_tick = world.tick,
                                    calib_target = 目标点, calib_progress = 0}
FUNCTION cmd_cancel_fire_mission(world, unit)
    unit.fire_mission = None                               // 任务体销毁，校射随之失效（方案10）
```

---

## §F5. 移动函数组（§13→B8 / R-09 / R-12）

```
FUNCTION move_speed_cm_tick(world, unit) → int
    e = unit.elements[0]                                   // 空编制的单位不存在
    IF e.crit != NULL AND e.crit[MOB] == MAJOR: RETURN 0   // 趴窝 R-19（方案7：非 MECH 元素无 crit 槽）
    base = speed_table[unit.template.speed_tier]
    IF world.tick < unit.sprint_until:                     // 方案14：疾跑=到期时间戳，速度档+1（封顶5）
        base = speed_table[MIN(5, unit.template.speed_tier + 1)]
    IF ANY(x.towed == TOWED FOR x IN unit.elements): base = speed_table[tow_speed_tier]   // v1.3：元素级判定（原 unit.tow_pair 已删）
    m_bp = world.terrain_speed_bp(unit.pos, unit.template.movement_class)   // Tiled 属性
    IF e.crit != NULL AND e.crit[MOB] == MINOR: m_bp = m_bp * crit_mob_minor_mult_bp // 10000
    v = base * m_bp // 10000
    IF world.on_road(unit.pos) AND unit.template.movement_class != FOOT:
        v = MAX(v, cfg.road_bonus_cm_tick)                 // v1.3（审查#6）：道路机动承载——原 road_bonus/on_road 全文零消费（轮式侦察卡核心身份）
    RETURN v
    //（v1.1 的 sprint_timer × sprint_mult_bp 行已删——方案14；sprint_mult_bp 常数随之删除）

FUNCTION system_move(world, unit)
    IF unit.deploy_state IN {DEPLOYING, PACKING}: RETURN   // 展开中禁移动
    IF ∃ pair IN world.tow_pairs: pair.towed_element ∈ unit.elements: RETURN   // v1.3：被拖元素所在单位不自主移动（由牵引车带）
    IF 全部元素 mounted_in != NULL:                        // R-07 整班随车（非 SQUAD 元素恒 NULL——v1.3 常驻槽）
        carrier = unit.elements[0].mounted_in
        unit.pos = carrier.pos; sync_followers(unit); RETURN   // v1.3：原引用未定义函数 sync_mounted，改 sync_followers（审查#4）
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
    FOR pair IN world.tow_pairs WHERE pair.tower_elements[0].unit == unit:
        pair.towed_element.pos = pair.tower_elements[0].pos   // v1.3：拖曳随动（元素级，随首牵引元素）
    sync_followers(unit)

FUNCTION sync_followers(unit)
    FOR e IN unit.elements WHERE e.mounted_in != NULL: e.pos = e.mounted_in.pos    // 条件槽：未分配恒 NULL（方案12）
    FOR e IN unit.elements WHERE e.mode == TRANSPORT AND e.cargo_units != NULL:    // 方案12：按槽存在性短路
        FOR squad IN e.cargo_units: squad.pos = e.pos               // D065 摩托化机动——B8

FUNCTION rotate_step(world, e, target_deg)                  // R-09 转车体（转向慢=暴露窗口）
    // 方案6：仅 fire_arc_deg<360 模板可达（ground_direct 射界门对 360° 模板恒假，天然豁免；
    // 此类模板不分配 rotating 槽，resolve_hit 受弹面判定亦按模板短路）
    diff = angle_diff(target_deg, e.facing)
    step = unit.template.turn_rate_deg_per_tick
    IF |diff| <= step: e.facing = target_deg; e.rotating = FALSE
    ELSE: e.facing = (e.facing + SIGN(diff)*step) % 360; e.rotating = TRUE
```

---

## §F6. 展开 / 运输 / 拖曳 / 驻楼 / 后勤（§13→B4 / B6 / g-载重 / g-拖曳解除）

```
// ── deployState 状态机（迁移表见机制版 v1.2 §10；动作函数在此）──
FUNCTION cmd_deploy(world, unit)                            // DeployCmd
    IF unit.deploy_state == MOBILE: unit.deploy_state = DEPLOYING
    unit.deploy_timer = unit.template.deploy_time_ticks
FUNCTION cmd_pack_or_move(world, unit)                      // PackCmd / MoveCmd 触发
    IF unit.deploy_state == DEPLOYED:  unit.deploy_state = PACKING; unit.deploy_timer = pack_time
    IF unit.deploy_state == DEPLOYING: unit.deploy_state = MOBILE; unit.deploy_timer = 0  // 进度作废

// ── R-07 上/下车（同卡）与 D065 运兵（跨卡）统一（v1.3 审查#3/#4/#8 重写）──
FUNCTION cmd_dismount(world, squad_unit)
    FOR e IN squad_unit.elements WHERE e.mounted_in != NULL AND e.template.element_type == SQUAD:
        carrier = e.mounted_in
        e.pos = carrier.pos 旁落位; e.mounted_in = None
        IF squad_unit != carrier.unit AND carrier.cargo_units != NULL       // v1.3：双向引用同步清（原漏清→下车班被拴回卡车死锁）
           AND squad_unit IN carrier.cargo_units: carrier.cargo_units.remove(squad_unit)
FUNCTION cmd_mount(world, squad_unit, carrier_unit)         // 进入 world.mount_requests
    carrier = carrier_unit 首个 seats>0 的元素
    IF carrier == NULL OR carrier.mode != TRANSPORT: REJECT    // v1.3（审查#8）：仅运兵模式可载人（原可向物资卡车装班）
    占用 = (carrier.cargo_units != NULL ? LEN(carrier.cargo_units) : 0)
    IF 占用 + 1 > carrier.template.seats: REJECT               // v1.3（审查#8）：seats 上限（原全文零消费，超载合法）
    IF world.mount_requests == NULL: world.mount_requests = []      // 方案12：惰性建表（首条请求才建）
    IF 班静止于载具旁 AND 载具静止: world.mount_requests.append({squad_unit, carrier, mount_time_ticks})
FUNCTION mount_requests_step(world)                          // 每 tick
    IF world.mount_requests == NULL: RETURN                 // 方案12：无表即无请求（非异常）
    FOR r IN world.mount_requests:
        r.ticks_left −= 1
        IF r.ticks_left <= 0:
            FOR e IN r.squad_unit.elements
                    WHERE e.template.element_type == SQUAD:           // v1.3（审查#4）：只挂班元素（原把 251 也挂上车→全排瞬移叠车）
                e.mounted_in = r.carrier
            IF r.squad_unit != r.carrier.unit:                       // v1.3：cargo_units 仅跨卡（同卡自引用+mounted 双计=连带双扣）
                IF r.carrier.cargo_units == NULL: r.carrier.cargo_units = []
                r.carrier.cargo_units.append(r.squad_unit)
            remove r

// ── D065 卡车三模式：元素级互斥切换（B6 修复）──
FUNCTION cmd_set_element_mode(world, e, m)
    IF m NOT IN e.unit.template.mode_set: REJECT
    IF e.mode == TOW:      release_tow_if_involved(world, e.unit)     // 切模式先解挂
    IF e.mode == CARGO AND e 有 hasSupply 槽:                                  // 方案12 条件槽
        e.supply_rounds = 0; e.supply_medical = 0                     // 卸货
    IF e.mode == TRANSPORT AND e.cargo_units != NULL:                 // 方案12 条件槽
        FOR s IN e.cargo_units:
            FOR se IN s.elements WHERE se.mounted_in == e:            // v1.3（审查#3）：双向引用同步清（原只清 cargo→班仍随车瞬移+车载禁射）
                se.pos = e.pos 旁落位; se.mounted_in = None
            s.pos = e.pos 旁落位
        e.cargo_units = []
    e.mode = m
    IF m != INDIRECT: IF e.unit.fire_mission != NULL: e.unit.fire_mission = None  // 任务取消（方案10：任务体销毁，校射随之失效）

FUNCTION buy_supplies(world, truck_element, rounds, medical)         // BuySuppliesCmd
    IF NOT truck_element 有 hasSupply 槽: REJECT                     // 方案12：非补给载具直接拒绝
    IF truck_element.mode != CARGO: REJECT                 // v1.3（审查#8）：仅物资模式可装货（原运兵/拖曳模式可预装，切回即生效破坏互斥）
    weight = rounds × Σ(武器 ammo_weight 均摊) + medical × med_weight_per_unit
    IF rounds  > truck.template.cargo_rounds_max:  REJECT
    IF medical > truck.template.cargo_medical_max: REJECT
    IF weight  > truck.template.cargo_weight_max:  REJECT               // D012 混装载重闸（g-载重）
    truck_element.supply_rounds = rounds; truck_element.supply_medical = medical

// ── 拖曳指令（v1.3：元素级——审查#12）──
FUNCTION cmd_tow(world, tower_elements[], towed_element): start_tow(world, tower_elements, towed_element)   // 失败静默拒绝
FUNCTION cmd_untow(world, element):
    FOR pair IN [p FOR p IN world.tow_pairs
                 IF element ∈ p.tower_elements OR element == p.towed_element]:
        stop_tow(world, pair, VOLUNTARY)

// ── 驻楼（最小实现，【拍板默认】隐蔽+3、受击参考尾甲）──
FUNCTION cmd_garrison(world, unit, building)
    IF NOT flags.canGarrison OR building.garrison_slots <= LEN(building.garrisoned): REJECT
    FOR e IN unit.elements: e.garrison_in = building; building.garrisoned.append(e)
    // 效果两处（v1.3 补齐第二处，原注释宣称两处实现只落地一处）：
    // effective_stealth_x10（+garrison_stealth_add，方案5 短路）+ resolve_hit 命中面（garrison_in != NULL → REAR）
FUNCTION cmd_un_garrison(world, unit)
    FOR e IN unit.elements WHERE e.garrison_in != NULL:
        e.garrison_in.garrisoned.remove(e); e.garrison_in = None; e.pos = 楼旁落位

// ── 反狙击掩护（v1.3：1:1 约束——审查#7）──
FUNCTION cmd_set_sniper_cover(world, sniper_unit, target_unit)
    FOR (tgt, protectors) IN world.cover_by_target 按插入序:
        IF sniper_unit IN protectors: protectors.remove(sniper_unit)   // 替换语义：新指令顶掉旧目标（"可掩护一个友军单位"——原可掩护全军）
    world.cover_by_target[target_unit].append(sniper_unit)  //（键不存在则建）

// ── 烟弹发射（B4：烟=SMOKE 武器档案，唯一入口；不进自动选目标）──
FUNCTION cmd_smoke(world, element, point)
    // 数据规则（v1.3）：SMOKE 武器 target_mask 必须为 0（无 GROUND 位）——永不进 select_target 自动索敌，仅此指令入口
    ws = 首个 damage_type==SMOKE 且 READY 且 ammo_left>0 的武器
    IF ws == NULL OR NOT fire_permitted(world, element.unit, element, ws): REJECT
    R = ws.template.dispersion_cm
    aim = point + (rng[SCATTER].sym(R), rng[SCATTER].sym(R))
    ws.ammo_left −= 1; ws.state = RELOADING; ws.timer = reload_time
    mark_resupply_if_needed(world, element.unit)           // v1.3（审查#11）：烟弹缺口同样登记
    world.projectiles.append(Projectile(shooter=element, weapon=ws.template,
        profile=SMOKE, pos=element.pos, dest=aim, trajectory=BALLISTIC,
        hit_target=NULL, will_hit=FALSE))

// ── 后勤（R-18 自动补给；烟弹在武器弹药轨内随弹补给——B4 单轨闭环）──
// 方案19：主扫描由"全单位"改为"在场 CARGO 卡车 × 待补给集合"；
// 保留清单#10：ammo_resupply_per_tick=2 速率与烟弹同轨自动补【原样保留】；
// 保留清单#9：医疗回血 INFANTRY 分支【原样保留】（登记条件含步兵带伤，见 needs_resupply）。
FUNCTION system_supply(world)
    FOR t IN all_elements WHERE t.mode == CARGO AND (supply_rounds>0 OR supply_medical>0):
        FOR u IN world.await_resupply
                WHERE u.alive AND u.team == t.unit.team                        // 队伍过滤（GDD-02 R-21"敌方不可拾取"——v1.1 遗漏，以 GDD-02 为准补）
                      AND dist_cm(u.pos, t.pos) <= t.unit.template.supply_radius_cm:
            FOR e IN u.elements:
                FOR ws IN e.weapon_states WHERE ws.ammo_left < ws.template.ammo_base:
                    take = MIN(ammo_base − ammo_left, t.supply_rounds, ammo_resupply_per_tick)
                    ws.ammo_left += take; t.supply_rounds −= take               // 烟弹同轨自动补【速率原样】
                    IF ws.state == EMPTY AND ws.ammo_left > 0: ws.state = READY // 方案19：EMPTY 补给转 READY
                IF e.template.unit_type == INFANTRY AND 0 < e.hp_current < e.template.hp_max:
                    med = MIN(CEIL((hp_max − hp_current) ÷ med_hp_per_unit), t.supply_medical)
                    e.hp_current = MIN(hp_max, e.hp_current + med × med_hp_per_unit)
                    t.supply_medical −= med
            // 边界：hp==0 的班已被 destroy_element 除名——医疗永不复活班元素
    world.await_resupply = [u FOR u IN world.await_resupply
                            IF u.alive AND needs_resupply(u)]                   // 方案19：集合自清理（含车毁/全灭注销）
    FOR rep IN all_elements WHERE unit.template.repair_power_hp_per_tick > 0:
        FOR e IN 贴靠的 MECH 元素 WHERE hp<max OR (e.crit != NULL AND e.crit 非空):   // 方案7：crit 判空
            e.hp_current = MIN(hp_max, e.hp_current + repair_power)
            IF e.hp_current >= e.template.hp_max:
                e.crit.clear()                                    // D016 修满清状态伤
                FOR pair IN world.tow_pairs WHERE pair 涉及 e.unit:
                    stop_tow(world, pair, REPAIRED)               // 修好即归队（R-19）
    //（v1.1 尾部 world.supply_boxes 空投箱循环已删——方案16：空投箱落地即一次性 CARGO 单位，
    //  被上方 CARGO 分支自动覆盖）

FUNCTION spawn_airdrop_crate(world, team, pos, rounds, medical)      // 方案16：R-21 航空侧调用接口
    // 一次性补给箱模板（非卡组卡面）：speed_tier=0/move_path 恒空（不可移动）、装甲0、HP 小（可摧毁）、
    // 无 flags；**supply_radius_cm 必配 8000**（v1.3 审查：原规格漏配→按模板半径过滤的拾取链对箱子恒不触发，
    // 谁也拾取不了）；落地实例化为 CARGO 单位，物资预填
    unit = instantiate(crate_template, team, pos)          // crate_template.supply_radius_cm = 8000（数据硬要求）
    e = unit.elements[0]
    e.mode = CARGO; e.supply_rounds = rounds; e.supply_medical = medical
    // 不登记 aa_roster（无 AIR 武器且 optics_air_cm=0，名单条件天然排除——方案2）
    // 被摧毁走 destroy_element 常规级联（物资随毁）
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
        // v1.3（审查#4）：R-07 开局车载默认形态——混编卡（装掷）班元素预挂随车（同卡只写 mounted_in）
        carriers = [e FOR e IN unit.elements IF e.template.seats > 0]
        squads   = [e FOR e IN unit.elements IF e.template.element_type == SQUAD]
        FOR (i, s) IN ENUM(squads): IF carriers[i] != NULL: s.mounted_in = carriers[i]
        IF flags.canInfiltrate: unit.infiltration_timer = 600       // 渗透 60s（仅 canInfiltrate 卡分配此槽——方案8）
        IF ANY(w.target_mask & AIR FOR w IN 全部武器) OR unit.template.optics_air_cm > 0:
            world.aa_roster.append(unit)                    // 方案2：对空名单登记（部署初始化=首批 spawn，运行时不重建）

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
        IF u.template.flags.canInfiltrate:                  // 方案8：渗透计时器门控（非渗透卡零写）
            u.infiltration_timer = MAX(0, u.infiltration_timer − 1)
        FOR e IN u.elements:
            e.reveal_timer = MAX(0, −1)
            decay = sup_decay_per_tick
            IF u.template.flags.suppDecayX2: decay = decay * 2       // 方案18：近卫意志近似（压制恢复加倍；旗标名与机制版同名）
            e.suppression  = MAX(0, e.suppression − decay)
            （sprint_timer 递减行已删——方案14）
        IF u.deploy_state == DEPLOYING: u.deploy_timer −= 1; IF <=0 → DEPLOYED
        IF u.deploy_state == PACKING:   u.deploy_timer −= 1; IF <=0 → MOBILE
        FOR ws IN 所有武器: IF ws.state IN {AIMING, RELOADING}:
            ws.timer = MAX(0, −1)
            IF ws.state == RELOADING AND ws.timer <= 0:      // 方案19：显式 EMPTY 迁移（v1.1 隐式转 READY 补全）
                ws.state = (ws.ammo_left > 0) ? READY : EMPTY
                IF ws.state == EMPTY AND u NOT IN world.await_resupply:
                    world.await_resupply.append(u)           // 方案19：EMPTY 即登记"等水名单"

FUNCTION system_projectiles(world)
    FOR p IN world.projectiles:
        p.pos, arrived = step_toward(p.pos, p.dest, p.speed_cm_tick)
        IF NOT arrived: CONTINUE
        IF p.trajectory == BALLISTIC: resolve_blast(world, p)          // 含烟弹落点
        ELIF p.hit_target is AircraftRef:                              // §F9 对空
            resolve_hit_aa(world, p)
        ELIF p.will_hit: resolve_hit(world, p)                          // B9：目标亡则落空；combat_style 分支在 resolve_hit 内（方案1）
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
渗透班"引导空投"：SetAirdropBeaconCmd 写 world.beacon_by_unit[unit] = pos
    （方案9：改全局旁表；不算暴露，不清渗透身份）；
    航空系统投散时按键读取该标记 → 散布 ×0.5（接口约定，公式在航空侧）；
    标定单位全灭时由 unregister_unit_refs 按键注销（方案9）。
```

---

## §A. 验收对照：§13 → 实现函数

| §13 问题 | 落地函数 |
|---|---|
| B1 武器缺射程/散布 | §D.3 字段 8/9/10 + §F4 select_target(min_range) + fire_direct(散布) |
| B2 狙击死代码 | §D.3 combat_style=SNIPER + §F4 fire_direct 常规路由（超长 aim/极低射速档案）+ §F1 resolve_hit SNIPER 分支（R-02，方案1） |
| B3 近战死代码 | §D.3 combat_style=MELEE 档案（0~50m/aim≈0/必中）+ §F1 resolve_hit MELEE 分支（方案1） |
| B4 烟雾闭环 | §D.3 SMOKE 档案 + §F6 cmd_smoke + §F1 resolve_blast 生烟 + §F6 system_supply 同轨补弹（速率原样，方案19 扫描集收窄） |
| B5 防空互斥 | §F4 system_combat ②对空并行（aa_roster 名单化，方案2）/ ③按元素 mode 分流（mode_set 静态门，方案3）（mode 枚举无 AA） |
| B6 卡车槽位层级 | §D.5 元素级 mode/cargo/supply（条件槽，方案12）+ §F6 cmd_set_element_mode / buy_supplies |
| B7 destroyElement | §F2 完整级联（车载/运兵/物资/拖曳/驻楼/全灭 + unregister_unit_refs 旁表注销，方案9） |
| B8 pos 随动 | §F5 system_move + sync_followers（mounted/towed/cargo 三路，条件槽短路，方案12） |
| B9 僵尸班 | §F1 resolve_sniper_hit 走 apply_damage + §D.4 不变式 + §F8 尸体清扫 |
| B10 装甲0除零 | §F1 damage_mult_permille 无甲守卫 |
| g-R01 标记消费 | §F4 fire_direct acc × calib_acc_bonus_bp |
| g-R15 自卫直射 | §F4 indirect_role 触发（self_defense!=NULL 短路，方案3）+ use_self_defense 档案 |
| g-伏击视野减半 | §F3 detection_range ×0.5 |
| g-fireAt/任务门控 | §F4.1 process_fire_mission 走 fire_permitted + fire_at 定义 + cmd_set_element_mode/start_tow 清任务（任务体销毁，方案10） |
| g-拖曳解除 | §F2 stop_tow（四触发）+ §F6 cmd_untow + 修好自动解挂 |
| g-配额 | §F7 validate_deck + cmd_purchase 扣余量 |
| g-建筑进驻 | §F6 cmd_garrison / collapse_building（【拍板默认】；§F3 canGarrison 前置短路，方案5） |
| g-载重混装 | §F6 buy_supplies 重量核算 |
| g-威胁值 | §F4 threat_value 可计算定义 |
| g-对空结算 | §F9 resolve_hit_aa 接口 |
| g-校射口径 | §F4.1 按发累积（fm.calib_progress，校射槽下沉任务体，方案10）；fire_direct 仅活跃任务期读收束（无任务=无收束，机制版同款） |
| v1.2-方案2 | 对空名单：§D.6 world.aa_roster + §F7 spawn_step 登记 + §F4 system_combat ② / §F3 sense_air 名单化 |
| v1.2-方案9 | 旁表：§D.6 beacon_by_unit/cover_by_target + §D.7 两命令写表 + §F1 掩护查表 + §F2 unregister_unit_refs 注销 |
| v1.2-方案19 | 事件补给：§F8 system_timers EMPTY 迁移登记 + §F2 needs_resupply/apply_damage 登记 + §F6 system_supply 扫描集合（速率/烟弹同轨原样）；v1.3 改缺口制（审查#11） |
| v1.3-审查修复 | 13 项问题：车载双扣血去重(#1)/声测圈阵营(#2)/上下车双向清理(#3)/装载SQUAD过滤+开局接线+sync笔误(#4)/工兵vs_fort直射+AttackCmd(#5)/道路机动(#6)/掩护1:1(#7)/卡车装载门+seats(#8)/对空拖曳门(#9)/TOW位补全(#10)/补给缺口制(#11)/拖曳元素级(#12)/校射视线定义(#13)；附属：FireMissionCmd处理体/use_self_defense复位/驻楼REAR/空投箱半径/烟mask规则/掩护空键删——详见文末 v1.3 变更记录 |

**落地说明**：相对 v1.1 文档的两个工程槽已在 §D.5 声明（`garrison_in` 字段 + world 级上车进度表）；确定性整型改造见 §T（PCG32 通道、bp/permille、8 扇区朝向、方形散布、isqrt）。实现顺序建议：§D 数据结构 → §F1 命中结算（纯函数+锚点单测）→ §F3 侦察 → §F4 交战 → §F2/§F5/§F6/§F7/§F8 依序补齐。

---

## §C. v1.1 → v1.2 变更记录（GDD-02-函数变量调用频率与替代方案.md 第五节 19 条逐条落实）

> 依据：方案文档每条的 sketch 为落地方法，negativeImpacts 为已接受代价（本文不修复这些代价）。
> corroborated 14 条 + single-pass 5 条全部落实（single-pass 已由用户拍板采纳）。

1. **方案1（狙击/近战路由档案化，corroborated）**：删除 §F4 `fire_sniper`/`fire_melee` 两函数与 `ground_direct`/`finish_aim` 的 melee_flag/sniper_flag 路由分支；D.3#26 由 `melee_flag/sniper_flag` 改为 `combat_style`（NORMAL/MELEE/SNIPER 条件位）。近战档案 = min_range 0 / max_range 5000cm / aim≈0 / accuracy_base_bp=10000 必中；狙击档案 = max_range 400 / 超长 aim_time / 极低 reload。R-02 结算（掩护减半、singleSquadCard 概率灭排、kills 1~2、r02_kill_tally≥3 灭班）**原样搬入** §F1 新增 `resolve_sniper_hit`；近战结算（close_combat_bonus_permille × 政委 MELEE 光环、绕过装甲曲线）搬入 `resolve_melee_hit`。两者在 `resolve_hit` 入口分流（先命中再判定/近距必中的方差变化为已接受代价）。渗透身份清零随原两函数迁入 `fire_direct`（仅 combat_style∈{MELEE,SNIPER} 触发——普通自卫开火不清身份，语义以 IMPL 为准）。fire_permitted/select_profile 未动。§A B2/B3 行同步。
2. **方案2（对空链点名表，corroborated）**：§D.6 WORLD 增 `aa_roster[]`；§F7 spawn_step 按「任一武器 target_mask&AIR 或 optics_air_cm>0」登记（部署初始化=首批 spawn，运行时不重建——静态名单无兜底为已接受代价）。§F4 system_combat ② 仅对名单单位执行；§F3 sense_air 防空体系探测分支仅遍历名单，低空目视分支（原 IMPL:443）对全体单位保留。重机枪（AIR_LOW）满足登记条件在名单上（GDD:364 保住）。
3. **方案3（曲射链按模板分流，corroborated）**：§F4 system_combat ③ `indirect_role` 与尾部 `process_fire_mission` 均加 `unit.template.mode_set & INDIRECT` 静态门（分发表=模板位测试，查询期不落槽位）；`indirect_role` 入口加 `w_main.self_defense != NULL` 一行短路（顺带消除 F3 火箭炮每 tick 裸检查风险）。数据配置要求：52-K/Flak 88（D029 三模式）mode_set 必须含 INDIRECT 位，漏配则曲射静默失效（已接受的配置风险）。
4. **方案4（声测侦听侧名单化，corroborated）**：§F3 system_sensing 先建 listener 名单（`sonar_radius_cm>0 且 DEPLOYED`），名单空则整段 `sonar_step` 跳过、IntelCircle 不再生成——名单内无声测班时盲射圈不再新增（R-03 规则内正确，已接受）。SoundTrack 写侧（fire_direct/fire_at 的 upsert_sound_track）与 acoustic_signature 读取**原样保留**（保留清单#3）。
5. **方案5（驻楼槽前置短路，corroborated）**：§F3 effective_stealth_x10 的 `ANY(garrison_in)` 加成前加 `flags.canGarrison` 模板短路；§D.5 工1 garrison_in 标〔条件槽：仅 canGarrison 卡分配〕；§F6 cmd_garrison 原 canGarrison 校验保留。非步兵卡（含高炮组）从此无法进楼——"88 炮进楼"后门若要保留须另行拍板（负面影响已列）。
6. **方案6（炮塔车转向豁免，corroborated）**：§D.5#12 rotating 标〔条件槽：仅 fire_arc_deg<360 模板分配〕；§F1 resolve_hit 受弹面判定加 `fire_arc_deg<360` 前置（炮塔车/全向基座恒走正常朝向）；rotate_step 仅 fire_arc<360 模板可达（ground_direct 射界门对 360° 恒假，天然保证）。R-09 侧露克制链收窄到无炮塔卡（已接受）；未来"炮塔卡死"类状态伤需把"炮塔可用"改为可变位（负面影响已列）。
7. **方案7（crit 四槽按 unit_type 短路，corroborated）**：§D.5#7 crit{FC,SEN,RLD,MOB} 标〔条件槽：仅 unit_type==MECH 元素分配，其余恒 NULL〕；§F1 修饰器族 aim/reload/optics_factor_bp 读槽前判 NULL 返回默认；§F5 move_speed_cm_tick、§F6 system_supply 维修分支加判空。MECH 白名单（BA-64/美洲狮、卡车、维修车、火箭炮牵引车）保留 crit 槽（保留清单#4：MOB 趴窝表现不变）。
8. **方案8（渗透计时器门控，corroborated）**：§F8 system_timers 的 infiltration 衰减行前加 `flags.canInfiltrate` 门（非渗透卡每 tick 空写消除）；读取点 effective_stealth 不动；开火清零点随方案1 迁移至 fire_direct 且**仅狙击/近战 combat_style 触发**——未改成机制版三路全清，R-04"自卫开火不清身份"语义保持 IMPL 口径。
9. **方案9（空投信标/狙击掩护改全局旁表，corroborated）**：删 §D.4 的 `sniper_cover_target`/`airdrop_beacon` 两槽；§D.6 WORLD 增 `beacon_by_unit{}`/`cover_by_target{}` 两张插入序 map；SetAirdropBeaconCmd/SetSniperCoverCmd 改写表；R-02 掩盖判定改查表（§F1 resolve_sniper_hit 内）；destroy_element 的"全单位遍历清理"改为 `unregister_unit_refs`（按键注销信标与掩护，销毁路径统一收口，防悬空引用）。r02_kill_tally 留在单位上未搬表（sketch 未含）。
10. **方案10（校射三槽下沉任务体，corroborated）**：删 §D.4 `calib_target`/`calib_progress`；§D.6 FireMission 内嵌 `calib_target`/`calib_progress`；fire_at 读写改走 `fm.*`；R-16"连内共享"=同任务参与者共享同一 fm，两连打同点各有 fm、互不叠加语义保留。直射收束口径按机制版 v1.2 同款拍板统一（走查修复）：fire_direct 仅在存在活跃任务时读 `fm.calib_progress`，任务耗尽/取消/拖曳/切模清任务后**无收束**——"保留最近任务收束缓存"变体**未采纳**（两 v1.2 同向），ZiS-3/52-K 双职炮直射不吃历史校射为已接受代价。
11. **方案11（钨芯弹并入弹药档案，corroborated）**：删 §D.3#22 `special_ammo` 与 weapon_states 内 `special_ammo_left`；§D.3#22 改为 `ammo_profiles[]`（受限档 {count_left, pen_bonus}，余量存档内计数）；select_profile 先按 R-11 对软目标切 HE，再查钨芯档「余量>0 且目标 MECH 且正面 pen_max<armor」条件（"打侧面不浪费"第11轮语义保留）。烟弹维持独立 SMOKE 档不并入（负面影响#2）。
12. **方案12（载运/物资槽子结构化，corroborated）**：mounted_in/cargo_units/supply_rounds/supply_medical 标〔条件槽〕，实例化按模板 flags（hasCargo/hasMount/hasSupply，D.1#25 新增位）决定分配；未分配读取恒 NULL/空表，sync_followers/system_supply/destroy_element/system_move 按空判天然短路；world.mount_requests 惰性建表（首条请求才建，mount_requests_step 空表即返回，查询返回"无请求"非异常）。D065 车毁连带分支仅对有 cargo_units 槽元素执行——装掷 251 车毁扣 60% 血克制链保留。
13. **方案13（三模式许可门按 mode_set 剔除，corroborated）**：fire_permitted 的 towed/mode 两道门改为先测 `unit.template.mode_set` 位，模板不含对应位则跳过该问（恒 DIRECT 卡每 tick 两问消除）。数据配置要求：一切可作为被拖方的卡——中/重坦（R-19 维修拖曳）与轻防空（第11/12轮卡车牵引）——mode_set 须含 TOW 位，漏配则"拖曳中禁射"失效（负面影响的荒诞画面风险已列；与机制版 v1.2 §4 数据硬要求注记同口径）；R-19 双方禁射对称性由两门同测 mode_set 保证。
14. **方案14（疾跑改时间戳，corroborated/V9 删档）**：删 §D.5 sprint_timer 与 §D.0 sprint_mult_bp；§D.4 增 `sprint_until`（tick 时间戳）；§D.0 增 `sprint_duration_ticks`（待定）；SprintCmd 写 `sprint_until = now + sprint_duration_ticks`；move_speed 改为 `now < sprint_until` 时速度档+1（封顶 5，改挂 speed_table——sprint_mult_bp 表述随之作废）；system_timers 删 sprint 递减行（统一衰减循环多一个例外，整洁度代价已接受）。
15. **方案15（删除死字段 turret_traverse_deg_per_tick，single-pass）**：删 §D.2#7 定义行，D.2 重排为 14 字段（v1.1 全文确无消费点）；"无炮塔"语义由 fire_arc_deg<360 + turn_rate_deg_per_tick 完整承载。未来做"炮塔独立转速"需重新加字段（已接受）。
16. **方案16（空投箱改为一次性 CARGO 元素，single-pass）**：删 system_supply 尾部 `world.supply_boxes` 循环（该字段在 v1.1 即属"引用了但 §D.6 漏列"的文档缺口，删除后缺口消除）；新增 §F6 `spawn_airdrop_crate`（R-21 航空侧调用接口）：落地实例化为预填物资、不可移动、可摧毁的 CARGO 单位，进 units[]，被 system_supply 既有 CARGO 分支自动覆盖。**GDD-02 为准修正**：system_supply 补给对象补 `u.team == t.unit.team` 过滤（GDD-02 R-21"敌方不可拾取"，v1.1 内环漏队伍过滤）。一次性元素占 units 遍历槽的微增开销为已接受代价。
17. **方案17（军官"射程+10%"改拍板为纯精度加成，single-pass）**：伪代码维持仅 PRECISION 精度+10%（fire_direct 精度乘区原样），**不补** select_target 射程消费点；即 sketch 的"改拍板"档。GDD-02 第4轮"军官=精准光环：射程+10%、精度+10%"表述由本方案拍板废止为"精度+10%"——GDD-02 卡面与拍板记录需在 GDD 文档侧同步回写（本文不改 GDD，列入对齐清单）。德军军官走位站位价值下降为已接受代价。
18. **方案18（近卫"溃逃重整×2"以压制衰减近似，single-pass）**：§D.1#25 flags 增 `suppDecayX2`（近卫步枪排置位；旗标名与机制版 v1.2 同名——走查统一）；§F8 system_timers 压制衰减行按旗标 `decay×2`。卡面"溃逃重整×2"表述需在 GDD 侧改写为"压制恢复加倍"（列入对齐清单）；"溃逃→重整"两态表现丢失为已接受近似。
19. **方案19（弹药补给事件触发，single-pass）**：§D.6 WORLD 增 `await_resupply[]`；§F8 system_timers 补 RELOADING→EMPTY 显式迁移（v1.1 隐式转 READY 一并补全），EMPTY 时把单位登记入待补给集合；§F2 增 `needs_resupply`（登记/保持条件 = 任一武器 EMPTY 或任一步兵元素带伤——含带伤条件是为保住保留清单#9 的 R-18 医疗承载），apply_damage 命中带伤即登记；§F6 system_supply 主扫描由"半径内全单位"改为"在场 CARGO 卡车 × 待补给集合"，补给后自清理。**保留清单#10 原样落实**：`ammo_resupply_per_tick=2` 速率与烟弹同轨自动补逐字保留，EMPTY 补满转 READY。事件集合维护（登记/车毁清理/自清理）为已接受的逻辑分支增量。

### 对齐与保留清单记录（notApplied / GDD-02 对齐）

- **notApplied（GDD-02 为准的修正）**：system_supply 补给内环补 `u.team == t.unit.team` 队伍过滤（GDD-02 R-21"敌方不可拾取"，v1.1 遗漏）——随方案16 落地一并修正，见变更记录#16。
- **GDD-02 卡面回写清单（GDD 文档侧执行，本文不改 GDD）**：①军官光环"射程+10%"删除（方案17 拍板，GDD-02 第4轮）；②近卫"溃逃重整×2"改写为"压制恢复加倍"（方案18，GDD-02 第3轮）。
- **保留清单十条全部未破坏**：start_tow/stop_tow 族、fm.target_line/creep_speed、SoundTrack 写侧、crit 的 MECH 侧、mark_level=CALIBRATED 消费链、requiresMark 门、vs_fort_mult_permille 字段、R-12 首击设计意图（置位点缺口仍为待拍板疑点，未顺手修复）、医疗 INFANTRY 分支、补弹速率与烟弹同轨。
- **方案文档 1.4 疑点清单未被 19 条方案触及者逐字保留**：疑点①（R-12 ambush_shot_bonus 无置位点）、②（vs_fort 直射不可达）、③（士气状态机，由方案18 近似处理近卫一卡，其余仍无锚）、④（use_self_defense 无复位行）、⑤（aa_try_engage 无 towed/mode 门）、⑥（军官射程光环，由方案17 拍板移除）、⑧（cmd_smoke 未查 min_range）、⑨（fire_at 不写 reveal_timer）、⑩（82mm 轻迫 self_defense 归属）、⑪（canAmbush 归属）、⑫（迫击炮可否领任务）——均维持 v1.1 口径，待另行拍板。
- **槽位账目变化**：v1.1 的 82 槽（单位静态 30 + 单位运行时 21 + 元素静态 15 + 元素运行时 16）→ v1.2 的 77 常驻槽 + 1 条件工程槽 = **78 槽**（单位运行时 −4：calib_target/calib_progress/sniper_cover_target/airdrop_beacon；+1：sprint_until → 18；元素静态 −1：turret_traverse_deg_per_tick → 14；元素运行时 −1：sprint_timer → 15）。总账 78 与机制版 v1.2 同向（其分项 30+17+14+17 与本文 30+18+14+15+1 的归口差见 §D.8）。武器子字段维持 27（special_ammo→ammo_profiles、melee_flag/sniper_flag→combat_style 两处换装；机制版 26 不含 name——§D.8）。

### v1.2 走查修复记录（对照机制版 GROUND_UNITS_PSEUDOCODE_v1.2.md）

1. **方案10 处置两版对立 → 拍板统一为机制版口径**：删 §D.4#18 `last_calib_reduction_bp`（原"最近任务收束缓存"补救档）与 `archive_calib_cache` 函数及其 fire_at（任务耗尽）/ start_tow（拖曳清任务）/ cmd_set_element_mode（切模清任务）三处调用；fire_direct 散布改读**活跃任务**的 `fm.calib_progress`（无任务=无收束）。"取消指令"回写点随函数一并删除（CancelFireMissionCmd 处理体两版伪代码均未定义，原调用点无实体）。账目 79→**78**，与机制版总账同向（分项归口差见 §D.8）。
2. **口径映射表落地**：新增 §D.8，逐项对表两 v1.2 的实现等价口径差——武器 27↔26（name）、sprint 单位/元素级、工程槽归口、aa_roster 粒度（单位/元素）、cover_by_target 值型（列表/单值）、曲射分流承载（模板位测试/分发表）；压制衰减旗标统一为 `suppDecayX2`（原 supDecayDoubled 改名，D.1#25/§F8/§C#18 同步）。
3. **cover_by_target 多掩护者语义**：GDD-02 第1轮仅拍板"每狙击可掩护一个友军单位"，未规定同目标多狙击行为；两版消费均为存在性布尔（减半不叠加、结果等价），如需叠加/互斥须另行拍板（§D.8#5 登记）。

### v1.2 终审自查修复记录

> 自查范围：19 条方案逐条落实核对（重点 5 条 single-pass）、对照 v1.1 底本的过度删减检查（函数清单 diff：仅删方案1 明令取消的 fire_sniper/fire_melee，仅增方案1/9/16/19 新函数）、§D 账目与交叉引用自洽。修复如下：

1. **§F4.1 fire_at 未定义变量 `unit`（继承 v1.1 底本 :653/:665/:669 的笔误）**：签名 `fire_at(world, gun, ws, fm)` 无 `unit` 形参——盲射圈匹配 `c.team == unit.team` 改 `gun.unit.team`，声源 `upsert_sound_track(world, unit, gun.pos)` 改 `(world, gun.unit, gun.pos)`，任务耗尽 `unit.fire_mission = None` 改 `gun.unit.fire_mission = None`，共三处。
2. **错别字**：§A "v1.2-方案9" 行"掩盖查表"→"掩护查表"；§C#1"先命中后判定"→"先命中再判定"（与方案文档/机制版措辞统一）。
3. **口径注记补齐**：§D.1#15 拖曳数据要求由"轻防空卡"扩为"被拖侧卡（中/重坦 R-19 维修拖曳、轻防空第11/12轮卡车牵引）"，与 §C#13 及机制版 v1.2 §4 数据硬要求注记同口径。
4. **§D.8 增补第 9 行**：方案19 医疗扫描口径差（本文医疗随待补给集合+带伤登记；机制版医疗保持全半径扫描）——行为等价（本文任一带伤步兵必已登记在集合），此前漏对表。
5. **§T 迭代行扩注说明（非误改）**：v1.1 §T"插入序列表"行末尾的"；旁表 map 亦按插入序实现"为方案9 引入 world 级 map 的确定性配套约定，属有意扩注、原句逐字保留。
6. **核对通过项（无改动）**：5 条 single-pass（方案15 删字段/方案16 CARGO 化/方案17 纯精度/方案18 suppDecayX2/方案19 EMPTY 事件驱动）落实正确；保留清单十条在位；v1.1 未触及函数逐字保留（§T 除上述扩注外全同）；账目 78=30+18+14+15+1 三处一致；§C 19 条与正文一一对应，交叉引用（§A↔函数名、§D.8↔§C）完整。

---

## §V. v1.2 → v1.3 变更记录（GDD-02-伪代码审查问题文档-v1.2.md 13 项问题修复）

> 编号对应问题文档；#1~#5 为单遍发现（high），#6~#13 为双遍以上命中（medium）。冲突裁决原则：机制语义冲突以 GDD-02 为准。

1. **车载被毁双扣血（#1）**：destroy_element 两串联连带环（mounted_in 环 + cargo_units 环）改为按元素收集去重、每元素只扣一次 60%——"剩 40% 血"承诺恢复（原 10 人班实扣 84%）。
2. **声测圈阵营记反（#2）**：sonar_step 的 IntelCircle.team 由 track.unit.team（被侦听的敌方）改为 listeners[0].team（侦听方）——盲射收束收益链恢复，全队共享归属修正。
3. **上下车循环死锁（#3）**：cmd_dismount 同步清 carrier.cargo_units（原漏清→下车班被每 tick 拴回卡车）；cmd_set_element_mode 切出 TRANSPORT 同步清班侧 mounted_in（原漏清→班继续瞬移+车载禁射+车毁追扣）；空车被毁不再追扣已下班（双向清理后天然成立）。
4. **装载过滤与开局接线（#4）**：mount_requests_step 只对 element_type==SQUAD 元素写 mounted_in（原把 251 也挂上车→全排瞬移叠车）；spawn_step 补混编卡开局车载默认形态（班元素预挂 carriers，同卡只写 mounted_in）；system_move 的未定义函数引用 sync_mounted 改 sync_followers。
5. **工兵 vs_fort 直射不可达（#5，疑点②闭合）**：resolve_hit 增建筑分支（×vs_fort、无装甲曲线）；Projectile.hit_target 类型扩 Building；fire_direct 对建筑跳过自动选弹与标记项；§D.7 增 AttackCmd{element, target: Element|Building}（直射指定目标入口）。ISU-152 混凝土弹/OT-34/ML-20 直射拆楼同步可达。
6. **道路机动死数据（#6）**：move_speed_cm_tick 增道路分支（on_road 且非 FOOT：v = MAX(v, road_bonus_cm_tick)）——road_bonus/on_road 恢复消费，轮式侦察卡"道路速度最高档"成立。
7. **反狙击掩护 1:1（#7）**：新增 cmd_set_sniper_cover 处理体，替换语义（新指令先从旧目标名单移除该狙击）——"可掩护一个友军单位"约束可执行（原单狙击可掩护全军）。
8. **卡车装载四缺口（#8）**：cmd_mount 增 TRANSPORT 模式校验 + seats 上限校验（seats 恢复消费）；buy_supplies 增 CARGO 模式校验；mounted_in 改为全体 SQUAD 元素常驻槽（原 hasMount 条件槽使无座位步兵卡派生不出槽，跨卡运兵无承载）。
9. **被拖防空自动对空开火（#9，疑点⑤闭合）**：aa_try_engage 增拖曳门（e.towed==TOWED 或本单位任一元素拖曳中即返回）——R-19 拖曳双方禁射扩展至对空链。
10. **TOW 位数据要求补全（#10）**：被拖侧卡枚举由"中/重坦+轻防空"扩为"火支全部牵引炮与火箭炮"（D.1#15 与 §C#13 同步）——按数据要求逐字配置即不再漏配；维持方案13"无运行时兜底"拍板。
11. **R-18 补给收窄（#11）**：needs_resupply 判据由"仅 EMPTY"改为"任一武器弹药未满或步兵带伤"；新增 mark_resupply_if_needed 于弹药消耗点（fire_direct/fire_at/cmd_smoke）与受伤点事件登记——保留方案19 事件驱动效率，同时恢复 GDD-02:247"补满缺口"语义（GDD 无需回写）。
12. **拖曳粒度元素级（#12）**：TowPair 改 {tower_elements, towed_element}；start_tow 按吨位降序贪心选车（累计吨位≥被拖元素自重）——单卡 2 车并拖可表达（苏军重坦不再需买两张卡）、混合牵引组不再出现 30t 车拖 45t 坦、61-K 可只拖一门；删单位级 tow_pair 槽（判定=ANY(e.towed==TOWED)），账目 78→77。
13. **校射视线定义（#13）**：新增 point_in_friendly_vision 定义体（含穿林/穿烟衰减，点目标按隐蔽中位档近似）——R-06"遮断校射"承载成立（烟墙后的目标点不收束）；fire_at 调用补 team 实参。

**附属修复**：FireMissionCmd/cmd_cancel_fire_mission 处理体补定义（原任务只有清空写点，永远无法下达）；fire_direct 发射后复位 use_self_defense（自卫档案一次性，52-K/88 直射不再被永久污染——疑点④闭合）；resolve_hit 驻楼受击 garrison_in→REAR 分支（原注释宣称两处实现只落地一处）；spawn_airdrop_crate 模板规格补 supply_radius_cm=8000 硬要求（原漏配→箱子无人能拾取）；SMOKE 武器 target_mask=0 数据规则成文（永不进自动索敌）；unregister_unit_refs 删掩护空键（掩护者全灭后目标不再恒判 covered）。

**裁决记录（可推翻）**：①#11 取"缺口制"而非回写 GDD——保 R-18 原文语义；②#12 取元素级并删 tow_pair 槽——R-19 史实制（单卡 2 车并拖）要求；③#5 按 GDD-02 补直射建筑分支（§D.8 冲突规则），非"维持待拍板"；④#10 扩枚举不加运行时兜底——尊重方案13 已接受代价。

**账目**：77 槽 = 30 + 17 + 14 + 15 + 1 工程槽（单位运行时 −1：tow_pair；mounted_in 转常驻不改总数——原已计入元素运行时 15）。武器 27 子字段不变。
