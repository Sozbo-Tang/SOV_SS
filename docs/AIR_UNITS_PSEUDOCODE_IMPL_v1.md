# 航空单位实现伪代码——§6 航空类落地版（v1-IMPL）

> 上游：GDD-02-单位功能细则-v1.8.md §6 航空类（R-20~R-23 + 第13/13~14轮拍板）+ GDD-00 D015/D017/D026/D038/D059 + TECH-00（整型确定性）+ GROUND_UNITS_PSEUDOCODE_IMPL_v1.7.md（**结构模板与接口契约来源，定稿只读**）+ AIR-00-航空机制调研锚点.md（调研参照与七条接口契约对表）。
> 本文是航空类**单一权威版**（不建双文档——地面管线双版同构税的教训），自身即"可直接照写代码"版。
> 语言中立；不出现任何具体语言代码。地面五份定稿文件与 sovs/sim 既有代码一律只读；本文全部产物为航空增量。
>
> **槽位账目（v1）**：航空模板静态 **20** + 航空运行时 **16** + 空射武器子字段 **0 新增**（复用地面 WeaponTemplate 27 子字段冻结账目）+ 航空命令 **9** + BalanceConfig 航空常数 **22** + PRNG 通道 **+1（AIR=7，Channels._COUNT=8 已覆盖——地面占 0~6，通道 7 空闲，零地面文件改动）**。与地面 78 槽账目**分账并行**（AircraftInstance 不是 UnitInstance，不入 units[]/aa_roster——契约②）。
> **〔条件槽〕约定（同地面）**：标注〔条件槽〕的运行时槽按模板能力实例化时决定分配，未分配读取恒 NULL——读取点判空短路。
> **无人值守模式**：本文所有设计决策按"推荐选项"执行并预登记于 §B（拍板预登记表），阶段 4 正式成文拍板清单；每条留推翻通道（回"N 改B"）。

---

## §T. 整型确定性落地约定（航空补充；地面 §T 全部适用）

| 项 | 约定（航空增量） |
|---|---|
| 高度 | AltTier 三层有序枚举 LOW=0 < MID=1 < HIGH=2（与地面冻结契约②一致：`a.alt_tier <= g.air_ceiling` 有序比较） |
| 空速 | 航空模板存 `speed_cm_tick`（整型 cm/tick 直存，**不走地面速度档表**——飞机速度差大且不受地形/道路影响；数值档待定项由数值章节定标，公式链只读该值） |
| 朝向 | 整型度 0..359 + 8 扇区量化（同地面）；**DIR8 整型方向表**：`[(0,1),(1,2),(1,1),(2,1),(1,0),(2,-1),(1,-1),(1,-2)]`——8 扇区代表方向，模长≈1（对角误差 ≤12%，跨平台位级确定，不画圆不用 atan2） |
| 椭圆散布（R-22 炸弹/丢弹） | `aim = center + DIR8[octant] × sym(R_major) + PERP8[octant] × sym(R_minor)`；PERP8[k] = DIR8[k] 旋转 90°（交换分量变一个符号）；两轴独立方形抖动（sym）——椭圆语义整型化，禁浮点禁三角 |
| 带状走廊（R-22 扫射） | 走廊 = 线段 [run_start, run_end] 两侧各 `strafe_corridor_half_cm`；元素在走廊内 ⇔ 点到线段整型距离（isqrt）≤ 半宽 |
| 随机 | 全部航空掷骰走 **rng[AIR]**（独立通道 7）：缠斗/追尾/自卫/侦察标记/投弹散布/扫射命中/空投散布。航空生成的地面弹丸若走地面 projectiles 推进（炸弹），散布掷骰仍用 AIR 通道（生成时刻在航空侧） |
| 移动 | 复用地面 `step_toward / round_div / octant_deg / dist_cm`（geom.py 冻结实现，只读复用） |

---

## §D.0 BalanceConfig 航空常数段（22 项；一常数一轨——系统函数禁止写死数值）

> 全部收进 tables.py BalanceConfig 单类（地面同轨纪律：同一张表=同一轨），数值"待定"项给占位默认并注明数值章节定标；**公式锚点常数在测试断言中逐一验证**。

| 字段 | 类型/单位 | 默认（占位） | 说明 |
|---|---|---|---|
| air_budget_base | 点 | 750 | D038 空军独立预算（方案A≈750/方案B≈2250 未拍板——按 A 占位，拍板后改此一处） |
| air_map_margin_cm | cm | 40000 | 场外缓冲带宽：飞机 spawn/RTB 完成点在己方底边外此距离（400m 外） |
| air_entry_offset_cm | cm | 60000 | INBOUND 入场点：己方底边场外 → 首任务的直线距离（飞入时间由距离÷速度自然承载——D015"飞入时间"位置化） |
| dogfight_engage_cm | cm | 8000 | R-20"同空域"判据：敌对战机相距≤此值且互在对空可及层→自动缠斗 |
| dogfight_interval_ticks | tick | 30 | R-20"每隔数秒"互相掷击落概率的回合周期（3s） |
| dogfight_base_prob_bp | bp | 3000 | 缠斗击落基础概率（乘战力/机动比，公式见 §F4） |
| dogfight_tail_base_bp | bp | 4000 | R-20 脱离瞬间被追尾基础概率 |
| dogfight_rounds_max | 回合 | 40 | 缠斗回合上限（120s 无结果→双方强制脱离、无追尾；防两架低战力机永久锁死）【拍板预登记 B-07】 |
| self_defense_prob_bp | bp | 2000 | D015 自卫火力基础命中概率（轰炸机/运输机缠斗回合对对手掷） |
| alt_transition_ticks | tick | 30 | 高度层间变更过渡时长（3s；过渡期保持原层判定）【拍板预登记 B-08】 |
| strafe_run_lead_cm | cm | 8000 | 扫射/投弹线：target 前后各此距离为 RUN 段（进场建立航向 → 投放 → 直线脱离——attack run 走廊，AIR-00 §一.2） |
| strafe_corridor_half_cm | cm | 1500 | R-22 带状走廊半宽 |
| strafe_acc_alt_bp[3] | bp[] | [13000, 10000, 7000] | R-23 扫射精度高度修正（低空最高） |
| strafe_suppression_radius_cm | cm | 2000 | 扫射近失压制半径（复用地面 inject_suppression_area 语义，近失弹参数） |
| bomb_scatter_alt_bp[3] | bp[] | [6000, 10000, 15000] | R-23/D015 炸弹散布高度系数（低空×0.6 / 中空×1.0 / 高空×1.5——中空中等、高空大） |
| bomb_scatter_speed_ref | cm/tick | 100 | D015"精度×飞行速度"：散布 ×MAX(1, speed)÷此值（越快越散） |
| bomb_ellipse_ratio_bp | bp | 5000 | R-22 椭圆短轴=长轴×0.5（沿航向长/垂直短） |
| dive_scatter_mult_bp | bp | 5000 | 俯冲投弹精度乘区（斯图卡等 has_dive 机型：散布×0.5 且无视巡航层一律按低空系数——俯冲本身=降 height 到投放，AIR-00 §一.3）【拍板预登记 B-09】 |
| airdrop_scatter_base_cm | cm | 3000 | R-21/D015 空投散布基础（×高度系数×速度系数） |
| airdrop_scatter_alt_bp[3] | bp[] | [8000, 12000, 16000] | 空投散布高度系数 |
| airdrop_beacon_radius_cm | cm | 2500 | 渗透班信标吸附半径（投放点距最近己方 beacon ≤此值→散布×0.5——契约⑤公式在航空侧） |
| air_cooldown_base_ticks / air_cooldown_per_missing_hp_ticks / air_cooldown_downed_multiplier | tick/tick/倍 | 600 / 30 / 3 | D015 冷却：安全返场=base+损失HP×per_hp；被击落=（base+hp_max×per_hp）×downed_multiplier（击落冷却远长于返场——AIR-00 §一.6 梯度）【拍板预登记 B-10：击落也进冷却】 |
| air_recon_period_ticks | tick | 10 | 侦察机标记节流（1s/掷——D015 概率性标记） |
| air_recon_speed_ref | cm/tick | 100 | D015 标记概率×飞行速度：慢速（Po-2）易标、快速难标（×ref÷MAX(1,speed)，上限 10000） |
| cloud_air_recon_mult_bp[3] | bp[] | [10000, 6000, 3000] | D026 云层对**高空侦察**的观察半径与标记概率乘数（cloud_tier 0/1/2）【拍板预登记 B-11：低云"掩护低空突防"的地面目视分支影响无法在航空侧承载（地面 sense_air 冻结只读）——收窄为高空侦察削弱+GDD-03 AI 云层修正，登记负面】 |

> 注：上表 26 行按字段名计 26 项、按条目计 22 项（三张 bp 数组各计 1 项、冷却三连计 1 项）——账目以"BalanceConfig 航空段新增字段行数=26"入 §D.6 总账，避免歧义。
> 弹药价/投放费（D015/D017）走模板与 PlayerState 扣费式（§F1），非 BalanceConfig 常数——每发弹价=机型差异化数据（下沉模板 payload_price 表），全局常数仅上列 26 项。

---

## §D.1 AircraftTemplate（航空模板静态 20）

> **结构裁决【拍板预登记 B-01】**：航空用**独立 AircraftTemplate**（非扩展地面 UnitTemplate）——理由（差异下沉到数据）：①飞机是单实体（无 elements 队形/无多元素卡），地面 UnitTemplate 的 element_groups/deploy/拖曳/驻楼/速度档/地形类 20+ 字段对飞机全部无意义；②AircraftRef 契约（八字段轻量引用）与 UnitInstance 结构天然异构；③分账使地面 78 槽冻结账目零扰动。**推翻通道：回"B-01 改B"**改为 UnitTemplate 加 category=航空+条件槽族（代价：地面账目全面重排）。

| # | 字段 | 类型 | 说明 |
|---|---|---|---|
| 1 | template_id | int | 回放校验 |
| 2 | name | str | — |
| 3 | role | 枚举 RECON/BOMBER/ATTACK/FIGHTER/TRANSPORT | 五机型职能（D015）；卡面差异全部走本表数据字段 |
| 4 | cost_body | int 点 | D015 本体价（走空军预算；卡面 20/30/85/95/75/90/70/80/40） |
| 5 | hp_max | int | 机体质 |
| 6 | armor_aa | int 0-20 相对刻度 | 契约①：对空单值装甲（resolve_hit_aa 消费）；Il-2"重装甲飞行坦克"=高值（抗高炮） |
| 7 | speed_cm_tick | int | 空速直存（§T；Po-2 慢/Stuka 中/战斗机快——数值章节定标） |
| 8 | dogfight_power | int | R-20 对空战力（Yak-9 中上/Fw 190 双强=高值） |
| 9 | maneuver | int | R-20 机动性（Il-2"机动笨"=低值） |
| 10 | alt_ceiling | AltTier | 可及高度层上限（TRANSPORT/ATTACK=LOW 或 MID、BOMBER=MID 起、FIGHTER=HIGH——R-23 各层可达性数据侧） |
| 11 | optics_air_cm | int | 空中对地观察半径（侦察机大；RECON 卡核心字段） |
| 12 | recon_mark_base_bp | bp | D015 标记概率基础（"标记概率靠机体性能"——Fw 189 高于 Po-2） |
| 13 | weapons[] | (WeaponTemplate, 弹量) 列表 | 空射武器档案（§D.3）：扫射机炮/炸弹；对空战力走 #8 不设对空武器档案 |
| 14 | payload_max_bombs / 15 payload_max_supply | int | 载荷上限（运输机补给舱：rounds/medical 合计按重量；BOMBER/ATTACK 炸弹数） |
| 16 | paratroop_seats | int | 空降兵舱位（TRANSPORT=1 班/架，D017；其余 0） |
| 17 | turret_damage | int | D015 自卫火力伤害/回合（BOMBER/TRANSPORT>0；FIGHTER/ATTACK=0——其"自卫"即缠斗本身） |
| 18 | can_engage_air | BOOL | 攻击机转对空资格（D015"可转对空"——Il-2 置位、Ju 87 不置、FIGHTER 恒对空优先不读本位） |
| 19 | has_dive | BOOL | 俯冲投弹（Ju 87D 置位→投弹散布×dive_scatter_mult_bp 且按低空系数；其余水平轰炸） |
| 20 | flags | 位段 | per_card_limit 走 D032 全局（每机型限 2——卡组层校验，不占本表）；isNightHarass（Po-2 夜间骚扰槽位——首版后置，零消费登记） |

## §D.2 AircraftInstance（航空运行时 16；含契约① AircraftRef 八字段超集）

| # | 字段 | 类型 | 说明 |
|---|---|---|---|
| 1 | id | int | 契约① |
| 2 | team / 3 player_index | int | 契约①（team）+ 经济归属 |
| 4 | pos | (cm,cm) | 契约①；航空侧唯一推进（地面"不推进其运动"） |
| 5 | alt_tier | AltTier | 契约①；变更经 alt_pending 过渡（#15） |
| 6 | hp_current / 7 hp_max / 8 armor_aa | int | 契约①（hp_max/armor_aa 实际读模板——存引用即可，账目记"经模板引用满足"；运行时真存 hp_current 一枚） |
| 9 | spotted_mask | int 位掩码 | 契约①；**地面 sense_air 唯一写者**（置位+M17 对偶清位），航空侧只读（aa_try_engage/缠斗可见性消费） |
| 10 | state | 枚举 INBOUND/PATROL/STRIKE/RTB/DOGFIGHT | 进出场状态机（§F2/§F3）；OFFBOARD 不实例化（冷却表承载） |
| 11 | flight_plan[] | 航点表 | 直线航段列表（step_toward 逐 tick 推进）；patrol_loop 旗随任务 |
| 12 | patrol_loop | BOOL | TRUE=末航点到达后回卷首航点循环（CAP/盘旋，§F2） |
| 13 | strike | {weapon: BOMB\|STRAFE, target, phase: INGRESS/RUN/EGRESS, run_start, run_end} \| NULL | 攻击航线任务体（§F3）；state==STRIKE 时非空 |
| 14 | ammo_left{weapon→int} | 旁表（插入序） | 各武器余弹（炸弹数=再出击前耗尽即自动 RTB 的判据——D015"弹药打完回场外"） |
| 15 | alt_pending | {target_tier, ticks_left} \| NULL | 高度变更过渡（§F2；〔条件槽：alt_ceiling>LOW 机型才分配〕——单层机型（仅 LOW）无变更需求） |
| 16 | dogfight | {opponent: AircraftRef, round_timer, is_disengaging} \| NULL | 缠斗任务体（§F4）；state==DOGFIGHT 时非空 |

> 击落/返场即整实例移出 world.aircraft（无尸体检扫——非 UnitInstance，不进 units[] 清扫循环）；对地面弹丸在途引用（hit_target=AircraftRef）的失效防护：resolve_hit_aa 结算前判 `a IN world.aircraft`（同地面"目标已在飞行中阵亡→落空"守卫，契约③消费安全）。

## §D.3 空射武器档案（复用地面 WeaponTemplate，0 新子字段）

> **复用裁决【拍板预登记 B-02】**：空射武器不建新结构——地面 WeaponTemplate 27 子字段（含 blast_radius_cm/dispersion_cm/accuracy_base_bp/salvo/ammo_base/suppression_power/vs_fort_mult_permille 等）全覆盖空射需求；空射特有语义（攻顶/椭圆/高度系数）由**调用侧**承载（top_attack 参数、散布公式、strafe_acc_alt_bp 查表），不进武器档案。"能算出来的不存"。

| 空射档案 | 配置要点（数据硬要求格式，同地面 TOW 位先例） |
|---|---|
| 扫射机炮（STRAFE） | target_mask=GROUND；trajectory=DIRECT；pen/damage 按 0-20 刻度（攻顶打 T 甲——T 槽最薄面）；**top_attack=TRUE 由 §F3 扫射结算统一传入**（resolve_hit 分支——契约⑥）；salvo=单次扫射发射数（走廊内逐发分配）；R-22 带状走廊由调用侧生成（§F3），武器不存走廊参数 |
| 炸弹（BOMB） | target_mask=GROUND；damage_type=HE；trajectory=BALLISTIC（**走地面 projectiles 推进**→resolve_blast 落点溅射——天然"不分敌我"（R-22/D015），契约⑥复用地面弹丸管线）；accuracy_base_bp 不消费（散布走 §F3 椭圆公式）；salvo=单次投弹颗数；blast_radius_cm=卡面杀伤半径 |
| （无对空武器档案） | R-20 缠斗掷骰走模板 dogfight_power/maneuver（§F4）；R-17 地面对空武器在地面文件——航空侧零对空武器档案 |

**数据硬要求**：① Il-2M weapons 须同时配 STRAFE+BOMB 两档（"炸弹+扫射+转对空丢弹全职能"可达性依赖）；② Yak-9/Fw 190A 须配 STRAFE（"扫射攻顶"）；③ Pe-2/Ju 88 须配 BOMB；④ Ju 87D 须配 BOMB 且 has_dive=TRUE；⑤ 运输机 weapons 可为空表（载荷走 #14/15/16）——漏配即对应职能静默失效（无运行时兜底，与地面 TOW/INDIRECT 位同约定）。

## §D.4 世界与玩家状态扩展（零地面文件改动）

```
WORLD 增量（aircraft[] 为地面 §D.6 已冻结字段，此处仅登记航空侧写者）：
  world.aircraft[]            // AircraftInstance 列表——航空侧唯一增删（契约①②）
  world.cloud_tier            // 0/1/2 地图参数（D026；Tiled 属性→JSON，默认 0）
  world.next_aircraft_id      // id 分配器
PlayerState 增量：
  air_points                  // 空军独立预算（D038/D001——与地面 points 分池）
  air_cooldowns{}             // 插入序 map：template_id → until_tick（D015 冷却表——AI 可查询，契约⑦）
```

## §D.5 航空命令集（9；命令驱动——AI 虚拟玩家走同一接口，契约⑦）

```
AirCallCmd{player, template, payload}          // 呼叫：payload={bombs, supply_rounds, supply_medical, paratroop_slot}（按机型资格互斥）
AirMoveCmd{aircraft, path[]}                   // 直飞航点（非 STRIKE/DOGFIGHT 态可下）
AirPatrolCmd{aircraft, center, radius}         // CAP/盘旋（生成 4 航点方形环路，§F2）
AirAltCmd{aircraft, tier}                      // 高度层变更（过渡 §F2）
AirStrikeCmd{aircraft, target_point, weapon}   // 攻击航线（BOMB|STRAFE——§F3 状态机）
AirAirdropCmd{aircraft, drop_point}            // 空投（空降兵/补给按 payload——§F6）
AirEngageAirCmd{aircraft, engage: BOOL}        // 攻击机转对空开关（TRUE 且挂弹→即刻丢弹，D015）
AirDisengageCmd{aircraft}                      // 缠斗脱离（瞬间被追尾掷骰，R-20）
AirRTBCmd{aircraft}                            // 返场（放弃任务）
```

## §D.6 槽位账目总表（一表成文）

| 层 | 数量 | 备注 |
|---|---|---|
| AircraftTemplate 静态 | 20 | §D.1 |
| AircraftInstance 运行时 | 16 | §D.2（hp_max/armor_aa 经模板引用满足契约①，真存槽 14+任务体 2） |
| 空射武器子字段新增 | 0 | 复用地面 27 冻结账目（§D.3/B-02） |
| 航空命令 | 9 | §D.5 |
| BalanceConfig 航空段 | 26 字段行 | §D.0 |
| PRNG 通道 | +1（AIR=7） | Channels._COUNT=8 已覆盖，零地面改动 |
| WORLD/PlayerState 增量 | 2+2 字段 | cloud_tier/next_aircraft_id；air_points/air_cooldowns |
| 地面账目扰动 | **0** | 78 槽/27 子字段/7 通道全部不动（分账并行） |

## §D.7 与地面结构的复用清单（只读复用，零改动）

| 复用项 | 来源（冻结） | 航空消费点 |
|---|---|---|
| Armor.of(Facing.TOP) | 地面 D.2#4-5（"T 仅空袭读取"） | 扫射/炸弹直击攻顶结算（契约⑥） |
| TargetDomain.AIR_LOW/MID/HIGH | 地面 D.3#2 | （对空武器掩码归地面侧；航空缠斗可及层走 alt_ceiling 有序比较） |
| AltTier 枚举 | types.py 冻结 | 全部高度判定 |
| PCG32/Channels | rng.py 冻结 | 新增 AIR=7 通道常量（加一行枚举值，_COUNT=8 原样） |
| geom：dist_cm/step_toward/round_div/octant_deg | geom.py 冻结 | 飞行推进/走廊距离/DIR8 |
| Projectile→resolve_blast | 地面 §F8/§F1 冻结语义 | 炸弹落点（BALLISTIC、不分敌我）；丢弹同 |
| resolve_hit（top_attack 分支） | 地面 §F1/combat.py 冻结 | 扫射逐发命中结算 |
| fire_aa / resolve_hit_aa | 地面 §F9 冻结 | 被防空命中（hp 扣减入口）；击落判定归航空（§F7） |
| spawn_airdrop_crate | 地面 §F6 冻结 | 空投补给落地（契约④） |
| beacon_by_unit | 地面 §D.6/§F9 冻结 | 空投散布 ×0.5（契约⑤） |
| sense_air/aa_roster/M17 清位 | 地面 §F3 冻结 | 航空零实现，只保证 pos/alt_tier/spotted_mask 语义（契约②） |
| apply_damage/inject_suppression* | 地面 §F1/F2 冻结 | 空降兵落地后即地面单位；扫射压制复用 |

---

## §F1. 经济与租借（D015/D017/D038）

```
FUNCTION cmd_air_call(world, player, template, payload)        // AirCallCmd——任何时候可下（D001，无 phase 门）
    slot_ok = (template.role 允许 payload 各成分)               // 资格：BOMBER/ATTACK: bombs；TRANSPORT: supply+paratroop；
                                                               // FIGHTER/RECON: 空载荷（RECON 零载荷价）
    cost = template.cost_body + payload_price(template, payload)
                                                               // 弹药价=按 payload 逐项（模板数据表）；空降兵本体价走预备队池
                                                               // （D017——deck 扣卡不扣点，见下）；投放费在空投时刻收（§F6）
    IF world.tick < player.air_cooldowns.get(template.template_id, 0): REJECT   // D015 冷却门
    IF player.air_points < cost: REJECT
    IF payload.paratroop_slot != NULL:                          // D017：空降兵卡走预备队 deck 槽
        ps = player.deck_slots 中该空降兵卡
        IF ps == NULL OR ps.copies_left <= 0: REJECT            // 一命制：预备队空降卡余量（落地成地面单位，永不回补）
    player.air_points -= cost
    IF payload.paratroop_slot != NULL: ps.copies_left -= 1      // 装机即扣（随机毁全损——B-12 拍板预登记）
    entry = 己方底边场外点(air_map_margin_cm) + 朝 map 中心
    a = AircraftInstance(template, player, pos=entry, alt_tier=模板默认进场层(=alt_ceiling 起始推荐 MID,
                          依机型数据字段默认——RECON 由首任务改层), state=INBOUND)
    a.ammo_left = payload 初始化（bombs/supply_rounds/supply_medical 旁表）
    a.paratroop_cargo = payload.paratroop_slot                  // 运输机舱内空降班（TRANSPORT〔条件槽：paratroop_seats>0〕）
    world.aircraft.append(a)

FUNCTION payload_price(template, payload) → int                 // 弹药价表（模板数据：每颗炸弹/每份补给单价）；空降兵不计价（预备队池已付）
FUNCTION air_recovery(world, a)                                 // 安全飞离结算（§F2 RTB 到达场外调用）
    player = a.player_index
    player.air_points += a.template.cost_body                   // D015：本体价回收
    player.air_cooldowns[a.template.template_id] = world.tick + air_cooldown_base_ticks
                                                   + (a.template.hp_max - a.hp_current) * air_cooldown_per_missing_hp_ticks
                                                               // 冷却随受损程度增长；弹药价不回收
    remove_aircraft(world, a)                                   // 移出列表、清任务体；在途弹丸引用由 resolve 侧守卫兜底

FUNCTION air_downed(world, a)                                   // 击落处置（§F7 hp≤0 唯一入口）
    IF a.paratroop_cargo != NULL: （舱内空降班随机毁——已扣 deck 份，不返还）   // B-12
    player.air_cooldowns[a.template.template_id] = world.tick
        + (air_cooldown_base_ticks + a.template.hp_max * air_cooldown_per_missing_hp_ticks)
          * air_cooldown_downed_multiplier // 1                 // 击落冷却远长于返场（AIR-00 §一.6 梯度）；本体价已付不退（D015）
    remove_aircraft(world, a)
```

## §F2. 飞行与高度（进出场/巡逻/层变更）

```
FUNCTION aircraft_move_step(world, a)                           // 每 tick、每架（世界循环挂点见 §F7）
    IF a.state == DOGFIGHT: RETURN                             // 缠斗期位置锁定（缠斗在空域内缠住——R-20 期间无法对地亦不位移）
    IF a.alt_pending != NULL:                                  // 高度过渡（B-08）
        a.alt_pending.ticks_left -= 1
        IF a.alt_pending.ticks_left <= 0:
            a.alt_tier = a.alt_pending.target_tier; a.alt_pending = NULL   // 过渡期保持原层判定（探测/散布/精度均按旧层）
    budget = a.template.speed_cm_tick
    WHILE budget > 0 AND a.flight_plan != []:
        dest = a.flight_plan[0]
        a.pos, arrived = step_toward(a.pos, dest, budget)
        IF arrived:
            a.flight_plan.pop(0); budget -= 本段实距
            IF a.flight_plan == [] AND a.patrol_loop: a.flight_plan = patrol_waypoints(a)   // 回卷
        ELSE: budget = 0
    IF 本 tick 有位移: a.facing = octant_deg(位移向量)          // 与地面同源 8 扇区
    IF a.state == INBOUND AND a.flight_plan == []:
        a.state = PATROL; a.patrol_loop = TRUE; a.flight_plan = [当前位置]  // 到达待命：原地盘旋待令
    IF a.state == STRIKE: strike_step(world, a)                 // 攻击航线推进（§F3）
    IF a.state == RTB AND a.pos 越过己方底边场外线: air_recovery(world, a)   // 安全飞离→回收（§F1）

FUNCTION patrol_waypoints(a) → path[]                           // 方形环路：center±radius 四航点按当前象限序
    center = a.flight_plan_anchor（PatrolCmd 写入的锚点；存 strike 任务体外的任务字段——patrol 任务的 anchor 挂
    在 a.strike 之外的任务槽（复用 #13 任务体结构 patrol 变体）——〔槽位复用：patrol {center, radius} 与 strike 任务体
    共用 #13 槽（互斥任务，判别字段区分）〕
    RETURN [c+(-r,-r), c+(r,-r), c+(r,r), c+(-r,r)]            // 顺时针方形环路（整型、确定性）

FUNCTION cmd_air_patrol(world, a, center, radius)               // AirPatrolCmd（CAP/盘旋）
    IF a.state IN {STRIKE, DOGFIGHT, RTB}: REJECT               // 攻击中/缠斗中/返场不可改巡逻
    a.state = PATROL; a.patrol_loop = TRUE
    a.任务槽 = {kind: PATROL, center, radius}
    a.flight_plan = patrol_waypoints(由 center/radius)

FUNCTION cmd_air_move(world, a, path)                           // AirMoveCmd（直飞）
    IF a.state IN {DOGFIGHT, RTB}: REJECT
    IF a.state == STRIKE: 取消当前攻击任务（strike 任务体清 NULL）   // 移动令打断 attack run（投放前）
    a.state = PATROL; a.patrol_loop = FALSE; a.任务槽 = NULL; a.flight_plan = path

FUNCTION cmd_air_alt(world, a, tier)                            // AirAltCmd
    IF tier > a.template.alt_ceiling: REJECT                    // 机型可及层上限（R-23 数据侧）
    IF a.state == DOGFIGHT: REJECT
    IF tier == a.alt_tier AND a.alt_pending == NULL: RETURN
    a.alt_pending = {target_tier: tier, ticks_left: alt_transition_ticks}

FUNCTION cmd_air_rtb(world, a)                                  // AirRTBCmd
    IF a.state == DOGFIGHT: RETURN                             // 缠斗中不可直接 RTB（须先 AirDisengageCmd 脱离）
    a.strike = NULL; a.patrol_loop = FALSE
    a.state = RTB; a.flight_plan = [己方底边场外点(最近侧)]      // 自动返场同一入口（弹药耗尽也走这里，§F3）
```

## §F3. 攻击航线与对地投放（R-22/D015；attack run 状态机）

```
FUNCTION cmd_air_strike(world, a, target_point, weapon)         // AirStrikeCmd
    IF a.state == DOGFIGHT: REJECT                              // 缠斗期间无法执行对地任务（R-20）
    IF weapon 对应武器 ammo_left <= 0: REJECT
    IF world.phase == 结算: REJECT
    dir = DIR8[octant_deg(target_point - a.pos)]               // 进场方向=当前位→目标 8 扇区量化（AIR-00 §一.2：走廊即此连线方向）
    run_start = target_point - dir × strafe_run_lead_cm
    run_end   = target_point + dir × strafe_run_lead_cm
    a.strike = {weapon, target: target_point, phase: INGRESS, run_start, run_end}
    a.state = STRIKE; a.patrol_loop = FALSE; a.flight_plan = [run_start]

FUNCTION strike_step(world, a)                                  // STRIKE 态推进（aircraft_move_step 尾部调用）
    s = a.strike
    IF s == NULL: RETURN
    IF s.phase == INGRESS AND a.pos == s.run_start（到达）:
        s.phase = RUN; a.flight_plan = [s.run_end]
        IF s.weapon == STRAFE: resolve_strafe(world, a, s)      // 扫射=RUN 段开始一次性结算（B-13 拍板预登记：走廊沿
                                                               // [run_start→run_end] 生成、整段一次掷骰——确定性优先，
                                                               // 避免逐 tick 采样与移动耦合）
    ELIF s.phase == RUN AND dist_cm(a.pos, s.target) <= a.template.speed_cm_tick（本 tick 越过目标线）:
        IF s.weapon == BOMB: resolve_bomb_release(world, a, s)  // 投弹=越过投放线（目标点）瞬间
        s.phase = EGRESS                                        // 直线脱离（attack run 不可中途转向——AIR-00 §一.2）
    ELIF s.phase == EGRESS AND a.flight_plan == []:
        a.strike = NULL; a.state = PATROL                       // 脱离完成→待命盘旋
        IF ALL(ammo <= 0 FOR a.ammo_left): cmd_air_rtb(world, a)   // 弹药打完回场外（D015 自动返场）

FUNCTION resolve_bomb_release(world, a, s)                      // 炸弹投放（R-22 椭圆/D015 精度式）
    IF world.phase != 实战: RETURN                              // 禁火期不投放（弹药保留；与地面 fire_aa phase 门同口径——M4）
    w = a.strike.weapon 对应 WeaponTemplate
    tier_idx = (a.template.has_dive ? LOW : a.alt_tier)         // B-09：俯冲投弹一律按低空系数（俯冲=降到低空投放）
    R_major = w.dispersion_cm * bomb_scatter_alt_bp[tier_idx] // 10000
               * MAX(1, a.template.speed_cm_tick) // bomb_scatter_speed_ref
    IF a.template.has_dive: R_major = R_major * dive_scatter_mult_bp // 10000
    R_minor = R_major * bomb_ellipse_ratio_bp // 10000
    k = octant_deg(s.run_end - s.run_start)                     // 航向扇区
    rng = world.rng[AIR]
    FOR i IN 1..w.salvo:                                        // salvo=单次投弹颗数（载弹量分解为多次出击次数）
        IF a.ammo_left[BOMB] <= 0: BREAK
        aim = s.target + DIR8[k] × rng.sym(R_major) + PERP8[k] × rng.sym(R_minor)   // §T 椭圆整型化
        world.projectiles.append(Projectile(shooter=a, weapon=w, profile=HE,
            pos=a.pos, dest=aim, speed=w.projectile_speed_cm_tick, trajectory=BALLISTIC,
            hit_target=NULL, will_hit=FALSE))                   // 走地面弹丸推进→resolve_blast：不分敌我/压制/伤楼全复用（契约⑥）
        a.ammo_left[BOMB] -= w.salvo_per_drop会计（每发递减）

FUNCTION resolve_strafe(world, a, s)                            // 机炮扫射（R-22 带状走廊+攻顶）
    IF world.phase != 实战: RETURN                              // 禁火期不扫射
    w = 对应 WeaponTemplate; rng = world.rng[AIR]
    FOR x IN 敌方存活元素:                                       // B-14 拍板预登记：扫射仅敌方（机炮有瞄准——D015"不分敌我"
                                                               // 明文仅限炸弹；敌我通吃=炸弹与丢弹）
        IF 点到线段距离(x.pos, s.run_start, s.run_end) > strafe_corridor_half_cm: CONTINUE
        IF x.mounted_in != NULL: CONTINUE                       // 与地面 select_target 同谓词（车载班不吃直击）
        FOR i IN 1..w.salvo:
            IF a.ammo_left[STRAFE] <= 0: BREAK
            acc = w.accuracy_base_bp * strafe_acc_alt_bp[a.alt_tier] // 10000        // R-23 低空精度最高
            IF rng.chance_bp(acc):
                p = Projectile(..., hit_target=x, will_hit=TRUE, top_attack=TRUE)    // 契约⑥：resolve_hit TOP 分支
                resolve_hit(world, p)                            // 即时结算（机炮弹速快，不飞行模拟——B-13 同批）
            ELSE:
                inject_suppression_area(world, x.pos 附近 jitter, strafe_suppression_radius_cm,
                                        w.suppression_power)   // 近失=压制
            a.ammo_left[STRAFE] -= 1

FUNCTION dump_bombs(world, a)                                   // 转对空丢弹（D015：自由落体砸落点敌我双方）
    IF a.ammo_left[BOMB] <= 0: RETURN
    w = BOMB 档; rng = world.rng[AIR]
    k = octant_deg(航向向量(a.facing 展开为 DIR8))
    FOR i IN 1..a.ammo_left[BOMB]:
        R_major = w.dispersion_cm * bomb_scatter_alt_bp[a.alt_tier] // 10000
                   * MAX(1, a.template.speed_cm_tick) // bomb_scatter_speed_ref * 2   // 丢弹=应急抛投，散布×2（有意识投放更散）
        aim = a.pos + DIR8[k] × rng.sym(R_major) + PERP8[k] × rng.sym(R_major * bomb_ellipse_ratio_bp // 10000)
        world.projectiles.append(..., dest=aim, trajectory=BALLISTIC, hit_target=NULL, will_hit=FALSE)
    a.ammo_left[BOMB] = 0                                       // 全部丢完（resolve_blast 不分敌我——R-22"敌我通吃"）
```

## §F4. 自动缠斗（R-20/D015 自卫火力）

```
FUNCTION dogfight_check(world)                                  // 每 tick（or 与 sensing 同节流——每 sensing_period_ticks 足够）
    FOR a IN world.aircraft WHERE state != DOGFIGHT AND state != RTB:
        IF a.template.role == FIGHTER OR (a.template.role == ATTACK AND a.engage_air):
            FOR b IN 敌方 world.aircraft WHERE b.state != RTB:   // RTB 机不被咬住（脱离中——已付追尾代价者豁免）
                IF dist_cm(a.pos, b.pos) <= dogfight_engage_cm AND 双方互在对方可及层（alt_tier 互 <= alt_ceiling）:
                    enter_dogfight(world, a, b); BREAK
    // BOMBER/TRANSPORT 不主动发起（只被动应战+自卫）；FIGHTER 对 RTB 敌机不追（上谓词排除）

FUNCTION enter_dogfight(world, a, b)
    a.strike = NULL; b.strike = NULL                             // 双方任务清空（R-20：缠斗期间无法执行对地任务）
    FOR x IN {a, b}: x.state = DOGFIGHT; x.patrol_loop = FALSE; x.flight_plan = []
    a.dogfight = {opponent: b, round_timer: dogfight_interval_ticks, is_disengaging: FALSE}
    b.dogfight = {opponent: a, round_timer: dogfight_interval_ticks, is_disengaging: FALSE}

FUNCTION dogfight_step(world, a)                                // 每 tick（成对推进：仅 id 较小侧驱动，防双结算）
    d = a.dogfight; IF d == NULL: RETURN
    IF d.opponent NOT IN world.aircraft: exit_dogfight(world, a, 对手已亡); RETURN
    d.round_timer -= 1
    IF d.round_timer > 0: RETURN
    d.round_timer = dogfight_interval_ticks
    dogfight_rounds += 1（任务体计数）
    // 双方互相掷击落概率（对空战力/机动性——R-20）
    FOR (atk, dfn) IN {(a, d.opponent), (d.opponent, a)}:
        p = dogfight_base_prob_bp * atk.template.dogfight_power
              // MAX(1, dfn.template.dogfight_power + dfn.template.maneuver)
        IF world.rng[AIR].chance_bp(p):
            air_shot_down_in_dogfight(world, dfn, atk); RETURN   // 击落=整发（掷击落概率，非扣血——R-20）
    // 自卫火力（D015：敌对空战机进入自卫火力范围受概率伤害——缠斗回合结算；无对空战力方掷）
    FOR (gunner, target) IN {(a,b),(b,a)} WHERE gunner.template.turret_damage > 0:
        IF world.rng[AIR].chance_bp(self_defense_prob_bp):
            target.hp_current -= gunner.template.turret_damage   // 伤害落库（击落判定走 hp≤0 统一口径 §F7）
            IF target.hp_current <= 0: air_shot_down_in_dogfight(world, target, gunner); RETURN
    IF dogfight_rounds >= dogfight_rounds_max:                   // B-07：回合上限强制双方脱离（无追尾）
        exit_dogfight(world, a, TIME_LIMIT); exit_dogfight(world, b, TIME_LIMIT)

FUNCTION cmd_air_disengage(world, a)                            // AirDisengageCmd——任何一方可下令脱离（R-20）
    IF a.state != DOGFIGHT: REJECT
    b = a.dogfight.opponent
    // 脱离瞬间有被追尾概率（对手 power / 自身 maneuver）
    tail_p = dogfight_tail_base_bp * b.template.dogfight_power // MAX(1, a.template.maneuver)
    IF world.rng[AIR].chance_bp(tail_p):
        air_shot_down_in_dogfight(world, a, b); RETURN          // 被追尾击落
    exit_dogfight(world, a, VOLUNTARY)                          // a 转 PATROL 待命；b 侧对手引用失效→自动 exit
FUNCTION exit_dogfight(world, x, reason)
    x.dogfight = NULL; x.state = PATROL; x.patrol_loop = TRUE; x.flight_plan = [x.pos]  // 原地待命

FUNCTION cmd_air_engage_air(world, a, engage)                    // AirEngageAirCmd（攻击机转对空——D015）
    IF a.template.can_engage_air == FALSE AND engage: REJECT
    IF engage AND a.ammo_left[BOMB] > 0: dump_bombs(world, a)    // 转对空时丢弃炸弹（§F3——自由落体敌我通吃）
    a.engage_air = engage                                        // 〔条件槽：仅 can_engage_air 机型分配；FIGHTER 恒真不占〕
```

## §F5. 侦察机标记（D015/R-23/D026）

```
FUNCTION air_recon_step(world)                                  // 每 air_recon_period_ticks（节流挂点 §F7）
    FOR a IN world.aircraft WHERE template.role == RECON AND state NOT IN {RTB}:
        tier_bp = recon_optics_alt_bp_of(a)                     // 高度修正：低空半径小/高空大（R-23——观察半径大但标记概率低）
        cloud_bp = cloud_air_recon_mult_bp[world.cloud_tier] IF a.alt_tier == HIGH ELSE 10000
                                                               // B-11：低云只削高空侦察（D026"低云削弱高空探测"）
        radius = a.template.optics_air_cm * tier_bp // 10000 * cloud_bp // 10000
        mark_p = a.template.recon_mark_base_bp * recon_mark_alt_bp_of(a) // 10000
                 * MIN(10000, air_recon_speed_ref * 10000 // MAX(1, a.template.speed_cm_tick) * 10000 // 10000)
                                                               // D015"飞行速度"：慢速易标（Po-2）——×ref÷speed，上限 10000
                 * cloud_bp // 10000
        FOR u IN 敌方 alive_units:
            IF dist_cm(a.pos, u.pos) <= radius AND world.rng[AIR].chance_bp(mark_p):
                u.spotted_mask |= (1 << a.team)                  // 发现（写 spotted_mask——与地面同一位掩码语义，契约②）
                IF u.mark_level < SPOTTED: u.mark_level = SPOTTED
                                                               // B-15 拍板预登记：侦察机标记=SPOTTED 不 CALIBRATED
                                                               // （R-01"校准"为地面侦察类专属；航空类≠§1 侦察类——GDD-02 §6 归类）
    // 高空标记概率低由 recon_mark_alt_bp_of 承载（[高,中,低]=[6000,9000,12000] 量级——数值章节定表；公式锚点见测试）
```

## §F6. 空投链（R-21/D017/契约④⑤）

```
FUNCTION cmd_air_airdrop(world, a, drop_point)                   // AirAirdropCmd
    IF a.state IN {DOGFIGHT, RTB}: REJECT
    IF a.template.role != TRANSPORT: REJECT
    IF a.ammo_left[Supply] <= 0 AND a.paratroop_cargo == NULL: REJECT   // 无载荷不可投
    dir = DIR8[octant_deg(drop_point - a.pos)]
    a.strike = {kind: AIRDROP, drop: drop_point, phase: INGRESS,
                run_start: drop_point - dir × strafe_run_lead_cm,
                run_end:   drop_point + dir × strafe_run_lead_cm}         // 复用 attack run 走廊（同状态机 §F3——任务体 kind 判别）
    a.state = STRIKE; a.flight_plan = [a.strike.run_start]

FUNCTION resolve_airdrop(world, a)                               // 越过投放线时刻（strike_step RUN 分支调用了本函数——AIRDROP kind）
    IF world.phase != 实战: RETURN
    rng = world.rng[AIR]
    // 散布（D015：高度×速度）+ 渗透班信标 ×0.5（契约⑤——公式在航空侧）
    R = airdrop_scatter_base_cm * airdrop_scatter_alt_bp[a.alt_tier] // 10000
        * MAX(1, a.template.speed_cm_tick) // air_recon_speed_ref       // 速度参考复用（同一量纲基准）
    beacon = 最近的 (unit→pos) IN world.beacon_by_unit WHERE unit.team == a.team
             AND dist_cm(pos, 投放点) <= airdrop_beacon_radius_cm       // 键读取：最近己方信标且在吸附半径内（B-16 拍板预登记）
    IF beacon != NULL: R = R * 5000 // 10000                             // 散布误差 -50%（第2轮拍板/契约⑤）
    IF a.paratroop_cargo != NULL:                                        // 空降兵（D017：落地即地面一命单位）
        FOR 每个舱内空降班:
            land = 投放点 + (rng.sym(R), rng.sym(R))                     // 方形散布（同地面纪律——空投箱/兵无航向椭圆语义）
            u = instantiate(该空降兵卡, a.team, a.player_index, land)     // 直接实例化（不走 spawn_queue——空投即到场）
            world.units.append(u)                                        // 进地面世界：一命制/R-18/受击全部地面语义（D017）
            inject_suppression_area(world, land, strafe_suppression_radius_cm, 0)  // 0 威力占位——无落地伤害（B-17 拍板预登记：空降兵无落地损
                                                                        // 失，散布是唯一风险——GDD 未授权落地伤害）
        a.paratroop_cargo = NULL
        player.air_points -= airdrop_fee(template)                       // D017 投放费（不回收——模板数据，仅空降作业收）
    ELSE:                                                                // 补给（R-21：落地实体补给箱）
        rounds = a.ammo_left[SupplyRounds]; medical = a.ammo_left[SupplyMedical]
        land = 投放点 + (rng.sym(R), rng.sym(R))                         // 单点集中投（一箱——补给按架次整箱投）
        spawn_airdrop_crate(world, a.team, land, rounds, medical)        // 契约④：地面冻结接口逐字调用（hasSupply/8000 半径在其模板规格）
        a.ammo_left[SupplyRounds] = 0; a.ammo_left[SupplyMedical] = 0
    // 空投箱敌不可拾取可摧毁：由 crate=CARGO 单位的地面语义承载（补-12/契约④）——航空侧零额外逻辑
```

## §F7. 击落结算与主循环挂点

```
FUNCTION air_check_downed(world)                                  // 每 tick（被防空/自卫/追尾扣血后的统一口径）
    FOR a IN list(world.aircraft):
        IF a.hp_current <= 0: air_downed(world, a)                 // 契约③："击落判定归航空系统"——resolve_hit_aa 只扣血
FUNCTION air_shot_down_in_dogfight(world, victim, killer)
    air_downed(world, victim)                                     // 缠斗击落同口径（本函数仅为 killer 归因留日志钩——无击杀返分 D001）
FUNCTION remove_aircraft(world, a)
    world.aircraft.remove(a)                                      // 在途地面弹丸（hit_target==a）由 resolve_hit_aa 前置守卫兜底（§D.2 尾注）

FUNCTION aircraft_tick(world)                                     // world_tick 航空段（挂地面 §F8 主循环 ④交战 之后、⑤弹丸 之前）
    FOR a IN list(world.aircraft): aircraft_move_step(world, a)    // ① 飞行（含高度过渡/strike 推进/RTB 回收）
    dogfight_check(world)                                         // ② 缠斗触发（节流同 sensing）
    FOR a IN world.aircraft WHERE dogfight != NULL AND id 为对内较小者: dogfight_step(world, a)   // ③ 缠斗回合（单侧驱动）
    air_check_downed(world)                                       // ④ 击落统一处置
    IF world.tick % air_recon_period_ticks == 0: air_recon_step(world)   // ⑤ 侦察标记节流
    IF world.tick % sensing_period_ticks == 0: dogfight_check 已含（②节流口径同 sensing——实现取其一，成文以②为准）
    // 相位交叉：AirCallCmd 无 phase 门（D001 任何时候）；投放/扫射/缠斗掷骰/空投均有实战门（§F3/§F6——禁火期入场盘旋待命，
    // 实战开始即生效）；结算 phase 一切飞行推进停止（aircraft_tick 头部 IF world.phase == 结算: RETURN）。
```

---

## §A. 逐卡验收对照（GDD-02 §6 每卡 × 功能点 × 承载位置）

| 卡 | 卡面功能点 | 承载（§节） |
|---|---|---|
| 苏① Po-2 侦察机 20分 | 超低空慢速侦察 | AirAltCmd→LOW（alt_ceiling 数据：Po-2 上限 LOW）＋§F5 radius/mark_p（speed 慢→×ref÷speed≥1 易标；tier=LOW→观察小标记高） |
| | 便宜消耗品损失不心疼 | cost_body=20＋air_downed 本体不退但冷却短（hp 小→冷却短） |
| | 夜间骚扰槽位（夜战首版后置） | template.flags.isNightHarass 零消费登记（D026 夜战槽位保留） |
| 苏② Pe-2 战术轰炸机 85分 | 快速水平轰炸 | has_dive=FALSE→bomb_scatter_alt_bp 按 alt_tier（水平）；speed 高→投弹前暴露时间短=进场快（speed_cm_tick 高＋INGRESS 段距离固定） |
| 苏③ Il-2M 攻击机 90分 | 重装甲飞行坦克抗高炮 | armor_aa 高值（resolve_hit_aa r² 曲线分母大→mult 降） |
| | 扫射火力凶 | STRAFE 武器档案 damage/salvo 高 |
| | 机动笨 | maneuver 低值（缠斗 p 分母小→被击落概率高、追尾概率高） |
| | 炸弹+扫射+转对空丢弹全职能 | weapons=[BOMB,STRAFE]（§D.3 硬要求①）＋can_engage_air=TRUE（§F4 engage→dump_bombs） |
| 苏④ Yak-9 战斗机 70分 | 灵活便宜对空中上 | maneuver 高/dogfight_power 中上；缠斗触发 FIGHTER 恒发起（§F4） |
| | 扫射攻顶 | STRAFE 档＋top_attack=TRUE（契约⑥；§D.3 硬要求②） |
| 苏⑤ Li-2 运输机 40分 | 空投空降兵/落地补给箱 | role=TRANSPORT＋paratroop_seats＋payload supply（§F6 两分支） |
| 苏⑥ 空降近卫步枪排 60分（占预备队池） | 仅 Li-2 投送；落地即地面一命单位 | D017：deck 预备队扣份（§F1）＋instantiate 直接入 units[]（§F6）——空降兵卡为地面卡（非 AircraftTemplate） |
| 德① Fw 189 侦察机 30分 | 稳定中高空大半径观察 | alt_ceiling=HIGH＋optics_air_cm 大＋recon_mark_base_bp 高（"标记概率靠机体性能"）；探测半径外安全=高空仅重防空+战机可及（R-23） |
| 德② Ju 88 战术轰炸机 95分 | 载弹多精度略高但慢 | payload_max_bombs 大＋dispersion_cm 略小＋speed 低（防区停留长=INGRESS+RUN 段时间长、易被防空盯上——aa 链时间窗自然承载） |
| | 防区停留长易被防空盯上 | 同上（速度低→走廊暴露时间长；无专属槽——能算出来的不存） |
| 德③ Ju 87D 斯图卡 75分 | 俯冲投弹垂直精度全场最高 | has_dive=TRUE→低空系数×dive_scatter_mult_bp=×0.5×0.6=×0.3（全场最低散布——锚点测试断言） |
| | 机体脆被37mm咬住即危 | hp_max 低＋armor_aa 低（Flak 43 37mm 对空武器数值配平——地面侧） |
| 德④ Fw 190A 战斗机 80分 | 对空战力与扫射火力双强 | dogfight_power 高＋STRAFE 档 damage 高（贵于 Yak-9 的 10 分在数据——两枚模板值） |
| 德⑤ Ju 52 运输机 40分 | 同 Li-2 | 同苏⑤（镜像数据） |
| 德⑥ 空降猎兵排 65分（占预备队池） | 仅 Ju 52 投送 | 同苏⑥ |
| R-20 自动缠斗制（全部战机） | 同空域自动缠斗/数秒互掷/脱离追尾/缠斗期禁对地/双层对空 | §F4 dogfight_check（同空域=dogfight_engage_cm）/dogfight_step（interval 互掷）/AirDisengageCmd（tail）/enter_dogfight 清 strike（禁对地）/防空+战机双层（地面 aa 链冻结+§F4） |
| R-21 空投落地箱 | 实体箱/友军自动拾取/敌不可拾取可摧毁/散布冒险 | §F6 补给分支→spawn_airdrop_crate（契约④：拾取/摧毁全地面语义）；散布=airdrop_scatter 式 |
| R-22 对地范围分武器形态 | 扫射带状走廊/炸弹圆椭圆散布/丢弹按航向椭圆敌我通吃 | §F3 resolve_strafe（走廊半宽）/resolve_bomb_release（DIR8 椭圆）/dump_bombs（航向椭圆+resolve_blast 不分敌我） |
| R-23 高度三层 | 低：目视可见+高炮威胁最大+扫射精度最高+标记概率高/中：轻中防空上限重防空可及+水平轰炸中等/高：仅重防空+战机+散布大侦察半径大标记低/云层叠加 | 低空目视（地面 sense_air 冻结）+strafe_acc_alt_bp[LOW]=13000+mark_alt 高+对空武器掩码（地面）；bomb_scatter_alt_bp=[6000,10000,15000]；高空重防空=air_ceiling 数据（88/52-K=HIGH）+战机全层（§F4 互在可及层）；云层=cloud_air_recon_mult_bp（B-11 收窄登记） |
| D015 租借经济 | 本体+弹药价/飞离回收本体/弹药不回收/冷却随受损/击落损失/飞入时间/自卫火力 | §F1 cmd_air_call/air_recovery/air_downed；飞入=入场点位置化（§D.0 air_entry_offset）；自卫=§F4 turret |
| D017 空降咬合 | 空降兵走预备队/运输机走空军/投放费不回收/落地即地面一命 | §F1 deck 扣份＋§F6 投放费＋instantiate 入 units[] |
| D026 云层 | 低云削弱高空探测 | cloud_air_recon_mult_bp（B-11：低空突防掩护的地面目视分支无法航空侧承载——登记负面+GDD-03 AI 云层修正消费） |
| D059 低空目视 | 低空飞机对地面单位可见/中高空仅防空探测 | 地面 sense_air 冻结（契约②零实现）；航空侧保证 alt_tier 语义 |
| 渗透班引导空投（第2轮） | 标定落点散布-50% | §F6 beacon 分支（契约⑤：beacon_by_unit 键读取+×5000bp） |
| GDD-03 空军调度（契约⑦） | AI 同一命令接口/走廊检查/预算冷却可查 | §D.5 九命令全命令驱动；air_cooldowns/air_points/ammo_left 可查询量 |

---

## §B. 拍板预登记表（阶段 4 拍板清单底稿；每条已按推荐执行，推翻通道="N 改B"）

| # | 决策点 | 推荐（本文执行） | 理由 | 负面影响 | 推翻通道 |
|---|---|---|---|---|---|
| B-01 | 航空结构：独立 AircraftTemplate vs 扩展 UnitTemplate | 独立模板（分账并行） | 差异下沉到数据；地面 20+ 字段对飞机无意义；地面 78 槽账目零扰动 | 航空/地面卡未来若共用效果（如空降兵）需桥接（instantiate 已桥） | B-01 改B |
| B-02 | 空射武器：复用 WeaponTemplate | 复用（0 新子字段） | 27 子字段全覆盖；空射特有语义调用侧承载 | 无 | B-02 改B |
| B-03 | 扫射敌我语义 | 仅敌方（"不分敌我"明文仅炸弹） | D015/R-22 字面：机炮有瞄准 | 扫射误伤友军不可表达 | B-03 改B |
| B-04 | 击落后冷却 | 击落也进冷却（×3 倍于满损返场） | 防无限炮灰机刷屏（AIR-00 §一.6 参照梯度）；D015 未明文击落免冷却 | 连续出击节奏更慢 | B-04 改B |
| B-05 | 弹药耗尽自动返场 | 全弹药耗尽即自动 RTB | D015"弹药打完回场外重装再出击"字面 | 扫射弹未尽但炸弹尽时玩家可能想留场——须手动留（自动门只看 ALL） | B-05 改B |
| B-06 | 运输机载空降班随机毁 | 装机即扣 deck 份、机毁班亡不返还 | 一命制纪律（D001/D017 落地成地面一命——空中损失同理） | 空投前被击落=最贵损失（设计意图：护航需求） | B-06 改B |
| B-07 | 缠斗回合上限 | 40 回合（120s）强制无追尾脱离 | 防两架低战力机永久锁死（系统活性） | 龟缩拖时间战术可用上限逃逸 | B-07 改B |
| B-08 | 高度变更过渡 | 30 tick 过渡、期间按原层判定 | 高度切换零成本会破坏 R-23 层博弈（切层躲探测无代价） | 多 1 任务槽（alt_pending） | B-08 改B（改即时切换零槽） |
| B-09 | 俯冲投弹高度语义 | has_dive 一律按低空系数+×0.5 乘区（无视巡航层） | 俯冲=降到低空投放的物理过程；斯图卡"垂直精度全场最高"锚点成立 | 斯图卡高空巡航时投弹判定与视觉层不符（判定层=低空） | B-09 改B（强制 has_dive 机须 LOW 层才可投弹） |
| B-10 | 冷却公式 | base+损失HP×per_hp（返场）；击落=×3 倍 | D015 字面"冷却随受损程度增长" | 数值待章节定标（占位已给） | B-10 改B |
| B-11 | 低云效果收窄 | 仅削高空侦察半径/概率+AI 参数；低空地面目视不受云影响 | 地面 sense_air 冻结只读——航空侧无写入口（探测由地面唯一承载，契约②） | R-23"低云掩护低空突防"的地面目视分支未承载（登记负面；翻案=地面 sensing 增量批次） | B-11 改B |
| B-12 | 空降兵装载时点 | 呼叫时扣 deck 份（机毁即亡） | 同 B-06 | 同 B-06 | B-12 改B（改为投出瞬间扣份——机毁班可回池） |
| B-13 | 扫射结算时相 | RUN 段开始一次性全走廊结算（非逐 tick 采样） | 确定性优先（与移动解耦、可单测） | 扫射视觉即时全部发生（表现层插值自理） | B-13 改B |
| B-14 | 炸弹走地面弹丸管线 | Projectile BALLISTIC→resolve_blast | 复用不分敌我/压制/伤楼；契约⑥ | 下落时间由 speed 表达（快弹）——fuse 视觉自理 | B-14 改B（立即落点结算） |
| B-15 | 侦察机标记档位 | SPOTTED（不 CALIBRATED） | R-01 校准为地面侦察类专属；航空类属 §6 | 侦察机不能引导精确打击（犀牛门不吃）——引导走地面侦察 | B-15 改B |
| B-16 | 信标生效判据 | 最近己方 beacon 且 ≤2500cm 吸附半径→×0.5 | 契约⑤"按键读取"+多信标需确定选择规则 | 超半径信标无效（渗透班标太远不受益） | B-16 改B（全局最近无半径门） |
| B-17 | 空降兵落地伤害 | 无（散布为唯一风险） | GDD 未授权落地伤害；D017"落地即地面一命单位"字面 | 空投人海无额外惩罚 | B-17 改B |
| B-18 | 呼叫 phase 门 | 无（任何时候——D001 字面）；投放/掷骰有实战门 | D001"任何时候可呼叫（不占部署时间线）"；禁火期全场禁火与地面 M4 同构 | 盲部署期可预置飞机到场盘旋（先手侦察优势——与渗透④A 同类时序问题，接受） | B-18 改B（禁部署期呼叫） |
| B-19 | RTB 豁免被咬 | RTB 态敌机不发起缠斗 | 脱离已付追尾代价（R-20 语义）；防无限追杀 | RTB 可安全穿越敌战机空域（被追尾一次即豁免） | B-19 改B |
| B-20 | CAP 词汇不入 GDD | 巡逻指令=GDD 未明文的操作增量，伪代码承载、GDD v1.9 补一句"战斗机/攻击机可下令巡逻盘旋" | R-20 自动缠斗已隐含 CAP 语义；操作入口需要成文 | GDD 正文新增一句（阶段 5 执行） | B-20 改B |

**假设清单（材料缺失按最佳判断——终检报告汇总）**：
- H-1：D038 空军预算未拍板→按方案 A（750）占位（§D.0 air_budget_base，一处可改）。
- H-2：航空数值（速度/HP/armor_aa/战力机动/散布基数）GDD 无卡面数值→公式链+占位默认，数值章节定标（与地面"待定"项同待遇）。
- H-3：弹药价/投放费具体值未定→payload_price/airdrop_fee 走模板数据表（公式链完整，值待定）。
- H-4：GDD 无燃油条目→不设燃油槽（在空时限=弹药+冷却承载；AIR-00 §三.5）。
- H-5：云层 tier 与地图参数格式（Tiled 属性名）未定→cloud_tier 0/1/2 默认 0（D026 后置项对齐）。
- H-6：多队制（>2 队）下缠斗/beacon 的队遍历——按插入序列表遍历（地面 §T 同纪律），语义两队制（现有全部对战口径两队）。

---

## 变更记录

- 2026-09-29：v1 初版（阶段 1 产物：§T/§D.0~D.7/§F1~F7/§A 逐卡对照/§B 拍板预登记 20 项+假设 6 项；单一权威版，不建双文档）。
