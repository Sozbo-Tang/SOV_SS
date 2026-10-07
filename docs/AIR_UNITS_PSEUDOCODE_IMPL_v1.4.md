# 航空单位实现伪代码——§6 航空类落地版（v1.4-IMPL）

> 上游：GDD-02-单位功能细则-v1.8.md §6 航空类（R-20~R-23）+ GDD-00 D015/D017/D026/D038/D059 + TECH-00 + GROUND_UNITS_PSEUDOCODE_IMPL_v1.7.md（定稿只读）+ AIR-00-航空机制调研锚点.md + 审查问题文档 v1/v1.1/v1.2（一/二/三轮：gap 28/14/5——v1.1/v1.2/v1.3 修复）+ **审查问题文档 v1.3（四轮：新发现 blocker 0 / gap 1 / AMB 2——本版全部修复，逐条对照见文末 §F）**。
> 本文是航空类**单一权威版**（不建双文档），自身即"可直接照写代码"版。语言中立。
>
> **槽位账目（v1.4）**：航空模板静态 **20** + 航空运行时 **21**（含 template 模板指针槽 + hp_max/armor_aa 2 模板引用槽 + engage_air/paratroop_cargo/alt_pending 3 条件槽）+ 空射武器子字段 **0 新增**（复用地面 27）+ 航空命令 **9** + BalanceConfig 航空常数 **38 字段行**（§D.0 按字段名计数，单一口径）+ PRNG 通道 **+1（AIR=7）**。与地面 78 槽账目分账并行。
> **改动授权口径（v1.1 修订，原"零地面文件改动"表述作废）**：地面五份定稿**文档**一律只读；代码增量仅限任务明文授权两处——rng.py 增 `AIR = 7` 枚举行（Channels._COUNT=8 原样，通道 7 空闲）、tables.py BalanceConfig 增航空常数段；**地面 v1.8 增量登记清单（3 项，均为一行级）**：① world_tick 主循环增**两行航空挂点**——③system_sensing 与 ④system_combat 之间增 `air_recon_step(world)`（侦察标记先清后写、交战拍可见——GAP2-01 修复）、④交战 与 ⑤弹丸 之间增 `aircraft_tick(world)`；② WORLD 增 cloud_tier/next_aircraft_id、PlayerState 增 air_points/air_cooldowns（承载于未来 world 循环模块，§D.4 自设）；③ `alive(a: AircraftRef) := a IN world.aircraft` 谓词由航空侧定义供给（地面 finish_aim/resolve 家族消费的对空存活判据——同 beacon 公式"接口约定在航空侧"先例；代码落地于 air.py，地面文档零改动）。
> **〔条件槽〕约定**：同地面——按模板能力实例化时决定分配，未分配读取恒 NULL，读取点判空短路。
> **无人值守模式**：全部设计决策按"推荐选项"执行并登记 §B（拍板预登记表，v1.1 扩至 B-01~B-23）；每条推翻通道="N 改B"。

---

## §T. 整型确定性落地约定（航空补充；地面 §T 全部适用）

| 项 | 约定（航空增量） |
|---|---|
| 高度 | AltTier 三层有序枚举 LOW=0 < MID=1 < HIGH=2（契约②：`a.alt_tier <= g.air_ceiling` 有序比较） |
| 空速 | 航空模板存 `speed_cm_tick`（整型 cm/tick 直存，不走地面速度档表；数值章节定标） |
| 朝向 | 整型度 0..359 + 8 扇区量化（同地面）；航空朝向存 `facing`（§D.2 #11，每 tick 由位移向量写） |
| **DIR8/PERP8 整型方向表（v1.1 重建——GAP-03）** | `DIR8 = [(0,7),(5,5),(7,0),(5,-5),(0,-7),(-5,-5),(-7,0),(-5,5)]`——全圆 8 向量按 octant_deg 45° 制扇区序（0°北→45°→90°东→…→315°），模长 7 或 7.07（对角 √50），**各向异性 ≈1%**（√50/7≈1.015%——GAP2-10：v1.1"≤1%"算术不实）；`PERP8[k]` = DIR8[k] 旋转 90°（(x,y)→(-y,x)）：`[(-7,0),(-5,5),(0,7),(5,5),(7,0),(5,-5),(0,-7),(-5,-5)]`；`DIR_NORM = 7`（结构常量，非平衡常数）。索引：`k = octant_deg(dx, dy) // 45`（octant_deg 返回 0..315 度值——除以 45 得 0..7，**西向 270°→索引 6**〔GAP2-10：v1.1 示例"270→5"算术错误，测试锚点 dir_index(-1,0)==6 为准〕，不越界）。标量缩放：`scale(DIR8[k], s) = (DIR8[k][0] × s // DIR_NORM, DIR8[k][1] × s // DIR_NORM)` |
| **点到线段距离（GAP2-07/AMB2-07 升格成文；v1.4 修 GAP4-01——落盘后独立数值复算通过）** | `point_segment_dist_cm(p, a, b)`：`ap = a − p`；`t = CLAMP(0, ab2, −(ap·ab))`（**负号保留**——分子先钳、免除法舍入；ab2=|ab|²）；垂足 `c = a + ab×t//ab2`；距离 = `isqrt(|p−c|²)`。锚点（v1.4 落盘复算）：线段 (0,0)-(10000,0) 点 (5000,0)→0、点 (5000,1400)→1400、点 (5000,1600)→1600（在 1500 半宽外）、点 (−3000,4000)/(0,0)-(0,10000)→3000（垂足钳端点）——与 air.py:111/:116 逐字同式（勘误 2026-10-01：本引注原书 :103/:108，首勘对齐 :106/:111（漂移 3 行）；同日复检修复轮于本函数上方插入 strafe_acc_bp 成文段 5 行后再漂移，二勘对齐 :111/:116；公式同一性经航空终检路B 12996 网格点独立复算零分歧——终检报告第九章瑕疵③登记，注释级勘误零行为变更）。 |
| 椭圆散布（R-22） | `aim = center + scale(DIR8[k], rng.sym(R_major)) + scale(PERP8[k], rng.sym(R_minor))`——主轴沿航向、垂直轴短，两轴独立方形抖动，全整型 |
| 带状走廊（R-22） | 走廊 = 线段 [run_start, run_end] 两侧各 `strafe_corridor_half_cm`；元素在走廊内 ⇔ 点到线段整型距离（isqrt）≤ 半宽 |
| 随机 | 全部航空掷骰走 **rng[AIR]**（独立通道 7；rng.py 增枚举行后以 `rng.rng(Channels.AIR)` 或 `rng.air()` 访问——与地面 hit()/scatter() 访问器家族同构） |
| 移动 | 复用地面 `step_toward / round_div / octant_deg / dist_cm`（geom.py 冻结，只读复用） |

---

## §D.0 BalanceConfig 航空常数段（38 字段行，按字段名单一口径计数；一常数一轨）

| 字段 | 类型/单位 | 默认（占位） | 说明 |
|---|---|---|---|
| air_budget_base | 点 | 750 | D038 空军独立预算（方案A占位，拍板后改此一处） |
| air_per_type_max | 架 | 2 | 每机型同型在空上限（B-24/D032"每机型限2"出表——AMB3-08；cmd_air_call 在空门消费） |
| air_map_margin_cm | cm | 40000 | 场外缓冲带宽（spawn/RTB 完成点在己方底边外此距离） |
| air_entry_offset_cm | cm | 60000 | **进场段长度**：入场点（底边场外）→ 进场终点（朝地图中心方向）的距离——cmd_air_call 消费（§F1），飞入时间=该段距离÷速度（v1.1 修复 GAP-04：v1 为死常数） |
| patrol_orbit_radius_cm | cm | 2000 | 待命盘旋半径（enter_patrol_hold 生成任务槽用——GAP-23） |
| dogfight_engage_cm | cm | 8000 | R-20"同空域"判据 |
| dogfight_interval_ticks | tick | 30 | 缠斗回合周期（3s） |
| dogfight_base_prob_bp | bp | 3000 | 缠斗击落基础概率（§F4 式） |
| dogfight_tail_base_bp | bp | 4000 | 脱离追尾基础概率 |
| dogfight_rounds_max | 回合 | 40 | 缠斗回合上限（120s 强制无追尾脱离，B-07） |
| dogfight_reengage_immunity_ticks | tick | 30 | 脱离后免咬窗（exit_dogfight 写 no_engage_until；脱离可达性——GAP-08） |
| self_defense_prob_bp | bp | 2000 | D015 自卫火力基础命中概率 |
| alt_transition_ticks | tick | 30 | 高度层间过渡（B-08） |
| strafe_run_lead_cm | cm | 8000 | 攻击线：投放点前后各此距离为 RUN 段 |
| strafe_corridor_half_cm | cm | 1500 | R-22 带状走廊半宽 |
| strafe_acc_alt_bp[3] | bp[] | [13000, 10000, 7000] | R-23 扫射精度高度修正（低空最高） |
| strafe_suppression_radius_cm | cm | 2000 | 扫射近失压制半径 |
| strafe_suppress_jitter_cm | cm | 1000 | 近失压制落点抖动（AMB-01：落点=x.pos+(rng[AIR].sym(此值), rng[AIR].sym(此值))） |
| bomb_scatter_alt_bp[3] | bp[] | [6000, 10000, 15000] | 炸弹散布高度系数（低/中/高） |
| bomb_scatter_speed_ref | cm/tick | 100 | 炸弹散布速度基准（越快越散） |
| bomb_scatter_cloud_bp[3] | bp[] | [10000, 11000, 13000] | D026 云层对投弹散布的乘区（cloud_tier 0/1/2；GAP-18——低云下中高空投弹散布增） |
| bomb_ellipse_ratio_bp | bp | 5000 | 椭圆短轴=长轴×0.5 |
| dive_scatter_mult_bp | bp | 5000 | 俯冲投弹精度乘区（has_dive 机型，B-09） |
| dump_scatter_mult_bp | bp | 20000 | 转对空丢弹散布乘区（应急抛投×2——放大方向；GAP-13 出表；〔二轮前自查：v1 初值 2000 为 ×0.2 刻度错误，锚点测试逮出〕） |
| airdrop_scatter_base_cm | cm | 3000 | 空投散布基础 |
| airdrop_scatter_alt_bp[3] | bp[] | [8000, 12000, 16000] | 空投散布高度系数 |
| airdrop_scatter_speed_ref | cm/tick | 100 | 空投散布速度基准（AMB-04：独立轨，默认与侦察基准同值、可独立调） |
| airdrop_beacon_mult_bp | bp | 5000 | 契约⑤冻结值：信标吸附生效时散布×0.5（GAP-13 出表） |
| airdrop_beacon_radius_cm | cm | 2500 | 信标吸附半径（B-16） |
| airdrop_fee_points | 点 | 5 | D017 空投作业费（仅空降分支收，不回收；GAP-01——v1 无定义行） |
| air_cooldown_base_ticks | tick | 600 | D015 冷却基数（安全返场=base+损失HP×per_hp） |
| air_cooldown_per_missing_hp_ticks | tick/tick | 30 | 冷却随受损增长率 |
| air_cooldown_downed_multiplier | 倍 | 3 | 击落冷却倍数（满损返场×3——AIR-00 §一.6 梯度） |
| air_recon_period_ticks | tick | 5 | 侦察标记节流（**=sensing_period_ticks 同拍**；挂点=world_tick ③sensing 与 ④交战 之间的独立挂点行——GAP2-01：sensing 先清、recon 后写、**其后**的交战拍可见标记，与地面侦察"每扫描重发现"同构，B-23） |
| air_recon_speed_ref | cm/tick | 100 | 标记概率速度基准（慢速易标，上限 10000bp） |
| recon_optics_alt_bp[3] | bp[] | [6000, 10000, 14000] | R-23 侦察观察半径高度修正（低空小/高空大——GAP-07 出注释成表） |
| recon_mark_alt_bp[3] | bp[] | [12000, 9000, 6000] | R-23 标记概率高度修正（低空高/高空低——GAP-07） |
| cloud_air_recon_mult_bp[3] | bp[] | [10000, 6000, 3000] | D026 云层对高空侦察的半径/概率乘数（B-11 收窄口径） |

> 账目：上表 **38 个字段名**（单一口径：数组按 1 字段计、冷却三连拆三行——v1.3 增 air_per_type_max（AMB3-08 出表），v1.2 曾计 37、v1.1"36"为计数错误）。
> 弹药价（payload_price）走模板数据（§D.1），非全局常数；投放费为全局量级（airdrop_fee_points）。

---

## §D.1 AircraftTemplate（航空模板静态 20；结构裁决 B-01：独立模板，分账并行）

| # | 字段 | 类型 | 说明 |
|---|---|---|---|
| 1 | template_id | int | 回放校验 |
| 2 | name | str | — |
| 3 | role | RECON/BOMBER/ATTACK/FIGHTER/TRANSPORT | 五机型职能（D015） |
| 4 | cost_body | int 点 | D015 本体价（空军预算） |
| 5 | hp_max | int | 机体质 |
| 6 | armor_aa | int 0-20 | 契约①对空单值装甲 |
| 7 | speed_cm_tick | int | 空速直存 |
| 8 | dogfight_power | int | R-20 对空战力 |
| 9 | maneuver | int | R-20 机动性 |
| 10 | alt_ceiling | AltTier | 可及高度层上限 |
| 11 | optics_air_cm | int | 空中对地观察半径 |
| 12 | recon_mark_base_bp | bp | D015 标记概率基础 |
| 13 | weapons[] | (WeaponTemplate, 弹量) 列表 | 空射武器档案（§D.3） |
| 14 | payload_max_bombs | int | 炸弹载荷上限 |
| 15 | payload_max_supply | int | 补给载荷上限（rounds+medical 合计） |
| 16 | paratroop_seats | int | 空降兵舱位（TRANSPORT=1，D017） |
| 17 | turret_damage | int | 自卫火力伤害/回合（BOMBER/TRANSPORT>0） |
| 18 | can_engage_air | BOOL | 转对空资格（Il-2 置位、Ju 87D 不置——B-21 拍板；FIGHTER 恒对空优先不读本位） |
| 19 | has_dive | BOOL | 俯冲投弹（Ju 87D 置位） |
| 20 | payload_price | 旁表（插入序） | 弹药价表：每颗炸弹/每发补给单价（D015 弹药价——机型差异化数据下沉模板；空降兵不计价，D017 预备队池已付） |

> 进场高度层（AMB-03 成文派生式，零新槽）：`entry_tier(a) = MIN(MID, template.alt_ceiling)`——Po-2(LOW)→LOW、轰炸机(MID)→MID、战斗机(HIGH)→MID 进场后玩家可爬升。
> flags 位（isNightHarass 等）并入 #3 role 语义与数据注记，不单列位段（v1 的 #20 flags 行由 payload_price 替代——账目 20 不变；夜间骚扰槽位零消费登记维持）。

## §D.2 AircraftInstance（航空运行时 21；含契约① AircraftRef 八字段——template 模板指针槽 + hp_max/armor_aa 2 字段引用槽〔GAP2-12 入账〕）
>
> **构造默认（AMB2-02 成文）**：数值槽初值 0（含 no_engage_until=0、spotted_mask=0）、BOOL/联合槽 FALSE/NULL（任务槽/dogfight/alt_pending/engage_air/paratroop_cargo、patrol_loop=FALSE）、facing=0——cmd_air_call 构造行之外的槽位由本默认式承载，各读取点（如 dogfight_check 读 no_engage_until）无未定义值。

| # | 字段 | 类型 | 说明 |
|---|---|---|---|
| 0 | template | AircraftTemplate | 模板指针槽（GAP2-12：§F 全家族 a.template.* 消费点数十处的来源槽，与地面 UnitInstance.template 同位先例） |
| 1 | id | int | 契约① |
| 2 | team | int | 契约① |
| 3 | player_index | int | 经济归属（契约① team 之外的归属补充） |
| 4 | pos | (cm,cm) | 契约①；航空侧唯一推进 |
| 5 | alt_tier | AltTier | 契约①；变更经 #17 过渡 |
| 6 | hp_current | int | 契约①真存槽 |
| 7 | hp_max | 〔模板引用槽〕 | 契约①：读 template.hp_max（GAP-01 显式入账） |
| 8 | armor_aa | 〔模板引用槽〕 | 契约①：读 template.armor_aa（同上） |
| 9 | spotted_mask | int 位掩码 | 契约①；**地面 sense_air 唯一写者**，航空侧只读（缠斗发起不读 spotted——R-20 无发现门，GDD 字面） |
| 10 | state | INBOUND/PATROL/STRIKE/RTB/DOGFIGHT | 进出场状态机 |
| 11 | facing | 度 0..359 | 航向（GAP-01 入账：§F2 每 tick 由位移向量写、dump_bombs 读） |
| 12 | flight_plan[] | 航点表 | step_toward 逐 tick 推进 |
| 13 | patrol_loop | BOOL | 末航点回卷循环旗（回卷前提：#14 任务槽为 PATROL 变体——GAP-23 判空短路） |
| 14 | 任务槽（判别联合，v1.1 统一——GAP-01/10/23） | {kind: STRIKE, weapon: BOMB\|STRAFE, target, phase: INGRESS\|RUN\|EGRESS, run_start, run_end} \| {kind: PATROL, center, radius} \| {kind: AIRDROP, drop, phase, run_start, run_end} \| NULL | 三变体互斥，判别字段 kind；strike_step/enter_patrol_hold 统一分发（v1 的 flight_plan_anchor/“a.任务槽”/strike 三名漂移统一为本槽） |
| 15 | ammo_left | 旁表（插入序） | 键枚举 **BOMB / STRAFE / SUPPLY_ROUNDS / SUPPLY_MEDICAL**（v1.1 统一——GAP-12）；实例化对全部资格键建键（未购=0） |
| 16 | alt_pending | {target_tier, ticks_left} \| NULL | 〔条件槽：alt_ceiling>LOW 机型分配〕高度过渡 |
| 17 | dogfight | {opponent: AircraftRef, round_timer, rounds} \| NULL | 缠斗任务体（v1.1：rounds 计数字段入体、enter_dogfight 初始化 0；v1 的 is_disengaging 死槽删除——脱离由命令即时表达，GAP-01） |
| 18 | engage_air | BOOL \| NULL | 〔条件槽：仅 can_engage_air 机型**或 FIGHTER** 分配（v1.2/AMB2-02：FIGHTER 的开关写点 §F4 同配本槽，消除"写未分配槽"）〕转对空开关 |
| 19 | paratroop_cargo | 空降班载荷 \| NULL | 〔条件槽：仅 paratroop_seats>0 机型分配〕（§F1 写/§F6 读写） |
| 20 | no_engage_until | tick | 免咬窗时间戳（exit_dogfight 写 no_engage_until=now+dogfight_reengage_immunity_ticks；dogfight_check 目标侧读——GAP-08 脱离可达性） |

> 存活谓词（AMB-02 ③ 成文）：`alive(a: AircraftInstance) := a IN world.aircraft`——航空侧定义供给，地面 finish_aim/resolve 消费的对空存活判据由此成立（地面文档零改动）。
> 移出 world.aircraft 即视除名；在途地面弹丸引用防护见 §F1 remove_aircraft（自清在途引用——GAP-02，v1 的"resolve_hit_aa 前置守卫"纸面引注作废）。

## §D.3 空射武器档案（复用地面 WeaponTemplate，0 新子字段；B-02）

| 空射档案 | 配置要点（数据硬要求） |
|---|---|
| 扫射机炮（STRAFE） | target_mask=GROUND；trajectory=DIRECT；**top_attack=TRUE 由 §F3 扫射结算统一传入**（契约⑥）；salvo=**对走廊内每个敌方元素各掷的发射数**（B-28 逐目标——v1.3/AMB3-01：弹账随目标数消耗，§F3 双层循环为机械承载）；走廊由调用侧生成 |
| 炸弹（BOMB） | target_mask=GROUND；damage_type=HE；trajectory=BALLISTIC（走地面弹丸推进→resolve_blast 落点溅射——不分敌我）；accuracy_base_bp 不消费；salvo=单次投弹颗数；**每发递减 ammo_left[BOMB]（v1.1 修复 GAP-15：v1 的 salvo_per_drop 未定义字段删除）** |
| （无对空武器档案） | R-20 缠斗掷骰走模板 dogfight_power/maneuver |

**数据硬要求（v1.2 增补⑥；v1.3 增补⑦）**：① Il-2M 配 STRAFE+BOMB；② Yak-9/Fw 190A 配 STRAFE；③ Pe-2/Ju 88 配 BOMB；④ Ju 87D 配 BOMB 且 has_dive=TRUE；⑤ 运输机 weapons 可空表——漏配即对应职能静默失效（无运行时兜底）。⑥ **空射武器档案 crit_mod_permille=0**（AMB2-08：消除空射暴击对地面 CRIT 通道的流耦合——roll_crit prob=0 恒 None，§T"全部航空掷骰走 rng[AIR]"字面成立；空射攻顶伤害已走 T 甲曲线，暴击不参与）。⑦ **FIGHTER.can_engage_air=TRUE**（AMB3-03：§F4 开拨门的 FIGHTER 豁免数据前提）。
**弹药初始化（v1.2 成文——GAP2-04）**：`ammo_left[STRAFE] ← weapons[] 中 STRAFE 档弹量`（§D.1 #13 的"弹量"元组项由此成为消费点——机炮弹随机体自带、**不进 payload_price**，与 D015 弹药价"炸弹/补给/空降兵"口径一致）；BOMB/SUPPLY_ROUNDS/SUPPLY_MEDICAL ← payload 对应值（未购 0）。
**空射射手视图（v1.1 成文——GAP-17）**：空射弹丸的 shooter 一律传 `air_shooter_view(a)`——航空侧供给的最小只读适配器（暴露 template.unit_type=MECH、hp_current=hp_max 语义），使地面冻结 Projectile{shooter:Element} 类型契约与 squad_hp_factor_bp（恒 10000‰——非步兵分支）可求值；弹丸字段名对齐冻结名（damage_type、speed_cm_tick——v1 的 profile/speed 简写作废）。

## §D.4 世界与玩家状态扩展（§D.4 自设；承载于未来 world 循环模块——"地面增量登记清单"②）

```
world.aircraft[]            // AircraftInstance 列表——航空侧唯一增删（契约①②；地面只读）
world.cloud_tier            // 0/1/2 地图参数（D026；Tiled 属性→JSON，默认 0）
world.next_aircraft_id
PlayerState.air_points      // 空军独立预算（D038/D001）
PlayerState.air_cooldowns{} // 插入序 map：template_id → until_tick（同型多机同键取 MAX——§F1 写点成文；AI 可查询，契约⑦）
```

## §D.5 航空命令集（9；命令驱动——AI 虚拟玩家走同一接口，契约⑦）

```
AirCallCmd{player, template, payload}          // payload={bombs, supply_rounds, supply_medical, paratroop_slot}（按机型资格互斥——§F1 slot_ok 门）
AirMoveCmd{aircraft, path[]}                   // 非 STRIKE(RUN/EGRESS)/DOGFIGHT/RTB 态可下（§F2 门族）
AirPatrolCmd{aircraft, center, radius}
AirAltCmd{aircraft, tier}
AirStrikeCmd{aircraft, target_point, weapon}   // BOMB|STRAFE
AirAirdropCmd{aircraft, drop_point}
AirEngageAirCmd{aircraft, engage: BOOL}
AirDisengageCmd{aircraft}
AirRTBCmd{aircraft}
```

## §D.6 槽位账目总表（一表成文；单一口径）

| 层 | 数量 | 备注 |
|---|---|---|
| AircraftTemplate 静态 | 20 | §D.1（#20 payload_price 旁表） |
| AircraftInstance 运行时 | **21** | §D.2（#0 template 指针槽 + hp_max/armor_aa 2 引用槽、alt_pending/engage_air/paratroop_cargo 3 条件槽、任务槽判别联合、dogfight.rounds 入体、facing/no_engage_until 常驻、构造默认成文） |
| 空射武器子字段新增 | 0 | 复用地面 27（B-02） |
| 航空命令 | 9 | §D.5 |
| BalanceConfig 航空段 | **38 字段行** | §D.0（单一口径按字段名计数；v1.3 +air_per_type_max） |
| PRNG 通道 | +1（AIR=7） | rng.py 增枚举行（任务授权）；_COUNT=8 原样 |
| WORLD/PlayerState 增量 | 2+2 字段 | §D.4（地面增量登记清单②） |
| 地面文档改动 | **0** | 地面增量登记清单 3 项（挂点行/扩字段/alive 谓词供给）全部承载于代码与航空侧，地面五份文档只读 |

## §D.7 与地面结构的复用清单（只读复用；v1.1 口径修订）

| 复用项 | 来源（冻结） | 航空消费点 |
|---|---|---|
| Armor.of(Facing.TOP) | 地面 D.2#4-5 | 扫射攻顶（契约⑥） |
| AltTier / TargetDomain.AIR_* | types.py | 高度判定/对空掩码（地面侧） |
| PCG32/Channels | rng.py + 任务授权 AIR 枚举行 | rng[AIR] |
| geom：dist_cm/step_toward/round_div/octant_deg | geom.py | 飞行推进/走廊/DIR8 索引 |
| Projectile→resolve_blast | 地面 §F8/§F1 冻结语义 | 炸弹/丢弹落点（BALLISTIC 不分敌我）；shooter 经 air_shooter_view 适配（§D.3） |
| resolve_hit（top_attack 分支） | 地面 §F1/combat.py | 扫射逐发命中 |
| fire_aa / resolve_hit_aa | 地面 §F9 冻结 | 被防空命中扣血（契约③）；击落判定归航空（§F7）；在途引用安全由 remove_aircraft 自清（§F1） |
| spawn_airdrop_crate | 地面 §F6 冻结 | 空投补给落地（契约④） |
| beacon_by_unit | 地面 §D.6/§F9 冻结 | 空投散布 ×airdrop_beacon_mult_bp（契约⑤） |
| sense_air/aa_roster/M17 清位 | 地面 §F3 冻结 | 航空零实现（契约②） |
| apply_damage/inject_suppression* | 地面 §F1/F2 | 空降兵落地后地面语义；扫射近失压制（jitter 常数化，AMB-01） |

---

## §F1. 经济与租借（D015/D017/D038）

```
FUNCTION cmd_air_call(world, player, template, payload)        // 任何时候可下（D001，无 phase 门——B-18）
    slot_ok = (template.role 允许 payload 各成分)               // BOMBER/ATTACK: bombs；TRANSPORT: supply+paratroop；
                                                               // FIGHTER/RECON: 空载荷
    IF NOT slot_ok: REJECT                                      // 〔v1.1 修复 GAP-26〕
    IF payload.bombs > template.payload_max_bombs: REJECT        // 〔v1.2 修复 GAP2-13：载荷容量门——payload_max 两
    IF payload.supply 合计 > template.payload_max_supply: REJECT // 字段成消费点（B-24 租借制无卡组层，呼叫门唯一承载处）〕
    IF COUNT(x IN world.aircraft WHERE x.team == player.team
             AND x.template.template_id == template.template_id) >= air_per_type_max: REJECT
                                                               // 〔v1.3/AMB3-08：在空上限出表（air_per_type_max，
                                                               // B-24/D032"每机型限2"）——一常数一轨〕
                                                               // 〔v1.1 修复 GAP-22：每机型限 2 = 同型同时在空 ≤2（B-24 拍板；
                                                               // 租借制无卡组份消耗——"限2"落运行时在空数门）〕
    IF world.tick < player.air_cooldowns.get(template.template_id, 0): REJECT   // D015 冷却门
    cost = template.cost_body + payload_price(template, payload)
    IF player.air_points < cost: REJECT
    IF payload.paratroop_slot != NULL:                          // D017：空降兵卡走预备队 deck 槽（B-12：装机即扣）
        ps = player.deck_slots 中该空降兵卡
        IF ps == NULL OR ps.copies_left <= 0: REJECT
        ps.copies_left -= 1                                     // 机毁班亡不返还（随机毁全损）
    player.air_points -= cost
    entry = 己方底边场外点(air_map_margin_cm)
    a = AircraftInstance(id = world.next_aircraft_id; world.next_aircraft_id += 1,   // 〔GAP3-05：id 分配行成文（构造
                                                               // 默认式不豁免数值槽——§F7③ 驱动谓词严格序依赖唯一 id）〕
                         template, team = player.team, player_index = player.index,  // 〔v1.4/AMB4-02：契约① team 与经济
                                                               // 归属双槽显式入构造行（v1.3 漏项——默认式字面覆盖两槽的
                                                               // 读法消除；对齐 air.py:396-397——勘误 2026-10-01 二次：
                                                               // 原引 :390-391（成文时点行号），复检修复轮于其上方插入
                                                               // strafe_acc_bp 段后漂移，已对齐实码现行行号）〕
                         pos=entry,
                         alt_tier=MIN(MID, template.alt_ceiling),
                         hp_current=template.hp_max,           // 〔GAP3-04：满血初始化例外成文——构造默认式置 0 会使
                                                               // 首拍 air_check_downed 判坠（全部职能不可达）〕
                         state=INBOUND)
    a.ammo_left = {STRAFE ← weapons[] 中 STRAFE 档弹量（§D.3 弹药初始化成文——GAP2-04：机炮弹随机体自带，不进 payload_price）,
                    BOMB/SUPPLY_ROUNDS/SUPPLY_MEDICAL ← payload 对应值（未购 0）}   // GAP2-12 全键初始化+GAP2-04 来源
    a.paratroop_cargo = payload.paratroop_slot（TRANSPORT 条件槽）
    进场终点 = entry 朝地图中心方向推进 air_entry_offset_cm 处
    a.flight_plan = [进场终点]                                   // 〔v1.1 修复 GAP-04：进场段成立——INBOUND 推进航点，
                                                               // 到达才转 PATROL；飞入时间=进场段÷速度〕
    world.aircraft.append(a)

FUNCTION payload_price(template, payload) → int                 // 模板 payload_price 表逐项求和；空降兵不计价（D017）

FUNCTION enter_patrol_hold(world, a)                            // 待命盘旋统一入口（GAP-23：写任务槽，回卷不再悬空）
    a.state = PATROL; a.patrol_loop = TRUE
    a.任务槽 = {kind: PATROL, center: a.pos, radius: patrol_orbit_radius_cm}
    a.flight_plan = patrol_waypoints(a.任务槽)

FUNCTION air_recovery(world, a)                                 // 安全飞离结算（§F2 RTB 到达调用）
    player = a.player_index 对应 PlayerState                     // 〔v1.2 修复 GAP2-07：绑定行成文（v1.1 裸 template_id 同族）〕
    tid = a.template.template_id
    IF a.paratroop_cargo != NULL:                                // 〔v1.2/AMB2-03→B-27：舱内未投空降班随机安全返场——
        ps = player.deck_slots 中该空降兵卡
        IF ps != NULL: ps.copies_left += 1                       // **退 deck 份**（班随机体回场、可再次呼叫——与"本体价
        a.paratroop_cargo = NULL                                 // 回收"租借哲学一致：未消耗的回池；机毁不退见 B-06）〕
    player.air_points += a.template.cost_body                   // D015：本体价回收（弹药价不回收）
    player.air_cooldowns[tid] = MAX(player.air_cooldowns.get(tid, 0),
        world.tick + air_cooldown_base_ticks
        + (a.template.hp_max - a.hp_current) * air_cooldown_per_missing_hp_ticks)
                                                               // 〔v1.1 修复 GAP-06：MAX 合并〕
    remove_aircraft(world, a)

FUNCTION air_downed(world, a)                                   // 击落处置（§F7 hp≤0 唯一入口）
    player = a.player_index 对应 PlayerState                     // 〔v1.2 修复 GAP2-07：绑定行成文〕
    tid = a.template.template_id
    IF a.paratroop_cargo != NULL: （舱内空降班随机毁——deck 份已扣，不返还）  // B-06
    player.air_cooldowns[tid] = MAX(player.air_cooldowns.get(tid, 0),
        world.tick + (air_cooldown_base_ticks + a.template.hp_max * air_cooldown_per_missing_hp_ticks)
                     * air_cooldown_downed_multiplier)          // 击落冷却远长于返场；本体价已付不退
    remove_aircraft(world, a)

FUNCTION remove_aircraft(world, a)
    FOR x IN world.aircraft WHERE x.dogfight != NULL AND x.dogfight.opponent == a:
        exit_dogfight(world, x, OPPONENT_DOWNED)                // 〔v1.1 修复 GAP-16：击落对偶清理——幸存方同 tick 解锁，
                                                               // 不依赖下 tick 驱动谓词〕
    FOR p IN world.projectiles WHERE p.hit_target == a:         // 〔v1.1 修复 GAP-02：航空侧自清在途引用——
        p.hit_target = NULL; p.will_hit = FALSE                 // v1 引注的"resolve_hit_aa 前置守卫"双侧无承载，作废。
                                                               // 自清后晚到弹按地面冻结分派落点：BALLISTIC→resolve_blast、
                                                               // DIRECT→inject_suppression_area 近失压制注入（AMB2-04：
                                                               // v1.1 注释"resolve_blast=近失"对 DIRECT 弹不实，本版改口径
                                                               // 为"近失压制注入"——高炮晚到弹在飞机末位点对半径内地面
                                                               // 单位注入压制，行为照冻结分派、零额外逻辑）〕
    world.aircraft.remove(a)
```

## §F2. 飞行与高度（进出场/巡逻/层变更）

```
FUNCTION aircraft_move_step(world, a)                           // 每 tick、每架
    IF a.state == DOGFIGHT: RETURN                             // 缠斗期位置锁定（R-20 期间无法对地亦不位移）
    IF a.alt_pending != NULL:                                  // 高度过渡（B-08）
        a.alt_pending.ticks_left -= 1
        IF a.alt_pending.ticks_left <= 0:
            a.alt_tier = a.alt_pending.target_tier; a.alt_pending = NULL
    budget = a.template.speed_cm_tick
    WHILE budget > 0 AND a.flight_plan != []:
        dest = a.flight_plan[0]
        a.pos, arrived = step_toward(a.pos, dest, budget)
        IF arrived:
            a.flight_plan.pop(0); budget -= 本段实距
            IF a.flight_plan == [] AND a.patrol_loop
               AND a.任务槽 != NULL AND a.任务槽.kind == PATROL:   // 〔v1.1 修复 GAP-23：回卷判空短路——
                a.flight_plan = patrol_waypoints(a.任务槽)         // 任务槽非 PATROL 变体不回卷〕
        ELSE: budget = 0
    IF 本 tick 有位移: a.facing = octant_deg(位移向量)          // facing 写点（§D.2 #11）
    IF a.state == INBOUND AND a.flight_plan == []:
        enter_patrol_hold(world, a)                             // 进场完成→待命盘旋（任务槽就位——GAP-04/23 联动）
    IF a.state == STRIKE: strike_step(world, a)                 // 攻击航线推进（§F3）
    IF a.state == RTB AND a.flight_plan == []:
        air_recovery(world, a)                                  // 〔v1.1 修复 AMB-08：回收判据=到达 RTB 航点
                                                               // （arrived 语义，位置精确、无压线歧义）〕

FUNCTION patrol_waypoints(t: PATROL 任务槽) → path[]            // 方形环路（整型确定性）
    c, r = t.center, t.radius
    RETURN [c+(-r,-r), c+(r,-r), c+(r,r), c+(-r,r)]

FUNCTION cmd_air_patrol(world, a, center, radius)               // AirPatrolCmd
    IF a.state == DOGFIGHT OR a.state == RTB: REJECT
    IF a.state == STRIKE AND a.任务槽 != NULL
       AND a.任务槽.kind != PATROL AND a.任务槽.phase != INGRESS: REJECT
                                                               // 〔v1.2 修复 GAP2-06：统一式与 move/strike/airdrop 同门——
                                                               // 覆盖 STRIKE 与 AIRDROP 两变体（v1.1 只判 kind==STRIKE，
                                                               // 空投线 RUN/EGRESS 可被巡逻令中途转向）+ 判空短路〕
    a.任务槽 = {kind: PATROL, center, radius}
    a.state = PATROL; a.patrol_loop = TRUE
    a.flight_plan = patrol_waypoints(a.任务槽)

FUNCTION cmd_air_move(world, a, path)                           // AirMoveCmd
    IF a.state == DOGFIGHT OR a.state == RTB: REJECT
    IF a.state == STRIKE AND a.任务槽.kind == STRIKE
       AND a.任务槽.phase != INGRESS: REJECT                     // 〔v1.1 修复 GAP-28：仅 INGRESS 可打断 attack run——
                                                               // RUN/EGRESS 直线不可转向（AIR-00 §一.2）〕
    IF a.state == STRIKE AND a.任务槽.kind == AIRDROP
       AND a.任务槽.phase != INGRESS: REJECT                     // 空投线同族
    a.任务槽 = NULL; a.state = PATROL; a.patrol_loop = FALSE; a.flight_plan = path

FUNCTION cmd_air_alt(world, a, tier)                            // AirAltCmd（高度层变更**不属任务令**——B-29：RTB 态允许
                                                               // 〔v1.3/AMB3-02→B-29：返场中变层为无害微操特许，不入 B-22 门族〕）
    IF tier > a.template.alt_ceiling: REJECT
    IF a.state == DOGFIGHT: REJECT
    IF tier == a.alt_tier AND a.alt_pending == NULL: RETURN
    a.alt_pending = {target_tier: tier, ticks_left: alt_transition_ticks}

FUNCTION cmd_air_rtb(world, a)                                  // AirRTBCmd（不可逆——B-22 拍板：与 D001"不可主动撤回"
                                                               // 精神一致；RTB 态拒一切任务令，返场=本次出击结束）
    IF a.state == DOGFIGHT: RETURN                             // 须先 AirDisengageCmd 脱离
    a.任务槽 = NULL; a.patrol_loop = FALSE
    a.state = RTB; a.flight_plan = [己方底边场外点(最近侧)]
```

## §F3. 攻击航线与对地投放（R-22/D015；attack run 状态机）

```
FUNCTION cmd_air_strike(world, a, target_point, weapon)         // AirStrikeCmd
    IF a.state == DOGFIGHT OR a.state == RTB: REJECT            // RTB 门（AMB-09/B-22：家族一致）
    IF a.state == STRIKE AND a.任务槽 != NULL
       AND a.任务槽.kind != PATROL AND a.任务槽.phase != INGRESS: REJECT   // RUN/EGRESS 不可重下（GAP-28）
    IF weapon 档 ammo_left <= 0: REJECT
    IF world.phase == 结算: REJECT
    dir_k = octant_deg(target_point - a.pos) // 45
    run_start = target_point − scale(DIR8[dir_k], strafe_run_lead_cm)
    run_end   = target_point + scale(DIR8[dir_k], strafe_run_lead_cm)
    a.任务槽 = {kind: STRIKE, weapon, target: target_point,
                phase: INGRESS, run_start, run_end}
    a.state = STRIKE; a.patrol_loop = FALSE; a.flight_plan = [run_start]

FUNCTION cmd_air_airdrop(world, a, drop_point)                  // AirAirdropCmd（v1.1 并入任务槽判别联合——GAP-10/01）
    IF a.state == DOGFIGHT OR a.state == RTB: REJECT
    IF a.state == STRIKE AND a.任务槽 != NULL
       AND a.任务槽.kind != PATROL AND a.任务槽.phase != INGRESS: REJECT
    IF a.template.role != TRANSPORT: REJECT
    IF a.ammo_left[SUPPLY_ROUNDS] <= 0 AND a.ammo_left[SUPPLY_MEDICAL] <= 0
       AND a.paratroop_cargo == NULL: REJECT                    // 键名统一（GAP-12）
    IF world.phase == 结算: REJECT
    dir_k = octant_deg(drop_point − a.pos) // 45
    a.任务槽 = {kind: AIRDROP, drop: drop_point, phase: INGRESS,
                run_start: drop_point − scale(DIR8[dir_k], strafe_run_lead_cm),
                run_end:   drop_point + scale(DIR8[dir_k], strafe_run_lead_cm)}
    a.state = STRIKE; a.flight_plan = [a.任务槽.run_start]

FUNCTION strike_step(world, a)                                  // STRIKE 态推进（aircraft_move_step 尾部调用）
    s = a.任务槽
    IF s == NULL OR (s.kind != STRIKE AND s.kind != AIRDROP): RETURN
    line_point = (s.kind == AIRDROP ? s.drop : s.target)        // 投放线判定点（GAP-10：AIRDROP 读 drop）
    IF s.phase == INGRESS AND a.pos == s.run_start（到达）:
        IF world.phase != 实战: 保持 INGRESS（悬停 run_start——flight_plan 已空、位移自停，实战首拍到达判据仍真）
                                                               // 〔v1.2 修复 GAP2-03 之半：INGRESS→RUN 转换补实战门——
                                                               // v1.1 无条件转换使禁火期扫射在门内 RETURN 后永无重触发〕
        ELSE:
            s.phase = RUN; a.flight_plan = [s.run_end]
            IF s.kind == STRIKE AND s.weapon == STRAFE: resolve_strafe(world, a, s)
                                                               // 扫射=RUN 段开始一次性全走廊结算（B-13；AMB2-06 成文：
                                                               // salvo=**对走廊内每个敌方元素**各掷 salvo 发（弹账随目标数
                                                               // 消耗——B-28 拍板，§D.3 说明同步））
    ELIF s.phase == RUN AND dist_cm(a.pos, line_point) <= a.template.speed_cm_tick（越线）:
        IF s.kind == AIRDROP: resolve_airdrop(world, a, s)      // 〔v1.1 修复 GAP-10：AIRDROP 分发补齐〕
        ELIF s.weapon == BOMB: resolve_bomb_release(world, a, s)
        IF world.phase == 实战: s.phase = EGRESS
        ELSE: s.phase = INGRESS; a.flight_plan = [s.run_start]  // 〔v1.2 修复 GAP2-03 之另半：禁火期挂起=**回 INGRESS 重走
                                                               // attack run**（实战开始后折回 run_start 重新进场投放——
                                                               // v1.1"保持 RUN"只冻相位不冻位移，飞机穿线停泊 run_end 后
                                                               // 越线窗口永不再真=任务死锁；AMB-07 拍板 A 的可达实现）〕
    ELIF s.phase == EGRESS AND a.flight_plan == []:
        enter_patrol_hold(world, a)                             // 脱离完成→待命（任务槽由 hold 覆写）；弹尽自动 RTB 由
                                                               // aircraft_tick 尾部统一判定（§F7——GAP-27，此处不再单点判）

FUNCTION resolve_bomb_release(world, a, s)                      // 炸弹投放（R-22 椭圆/D015 精度式/D026 云层）
    IF world.phase != 实战: RETURN                              // 禁火期不投放（弹药保留——AMB-07 挂起）
    w = s.weapon 对应 WeaponTemplate; rng = world.rng[AIR]
    tier_idx = (a.template.has_dive ? LOW : a.alt_tier)         // B-09：俯冲投弹一律按低空系数
    R_major = w.dispersion_cm * bomb_scatter_alt_bp[tier_idx] // 10000
               * MAX(1, a.template.speed_cm_tick) // bomb_scatter_speed_ref
               * bomb_scatter_cloud_bp[world.cloud_tier] // 10000     // 〔GAP-18：云层投弹乘区〕
    IF a.template.has_dive: R_major = R_major * dive_scatter_mult_bp // 10000
    R_minor = R_major * bomb_ellipse_ratio_bp // 10000
    k = octant_deg(s.run_end − s.run_start) // 45
    FOR i IN 1..w.salvo:
        IF a.ammo_left[BOMB] <= 0: BREAK
        aim = s.target + scale(DIR8[k], rng.sym(R_major))
                           + scale(PERP8[k], rng.sym(R_minor))
        world.projectiles.append(Projectile(shooter=air_shooter_view(a), weapon=w,
            damage_type=DamageType.HE, damage=w.damage, blast_cm=w.blast_radius_cm,
            pos=a.pos, dest=aim, speed_cm_tick=w.projectile_speed_cm_tick,
            trajectory=BALLISTIC, hit_target=NULL, will_hit=FALSE, top_attack=FALSE))
                                                               // 字段名对齐冻结名+射手视图（GAP-17）；resolve_blast 不分敌我
        a.ammo_left[BOMB] −= 1                                  // 〔v1.1 修复 GAP-15：每发递减（v1 的 salvo_per_drop 删除）〕

FUNCTION resolve_strafe(world, a, s)                            // 机炮扫射（R-22 带状走廊+攻顶）
    IF world.phase != 实战: RETURN
    w = s.weapon 对应 WeaponTemplate; rng = world.rng[AIR]
    FOR x IN 敌方存活元素:                                       // B-03 拍板：扫射仅敌方（"不分敌我"明文仅炸弹）
        IF 点到线段距离(x.pos, s.run_start, s.run_end) > strafe_corridor_half_cm: CONTINUE
        IF x.mounted_in != NULL: CONTINUE                       // 与地面 select_target 同谓词
        FOR i IN 1..w.salvo:
            IF a.ammo_left[STRAFE] <= 0: BREAK
            acc = MIN(10000, w.accuracy_base_bp * strafe_acc_alt_bp[a.alt_tier] // 10000)  // R-23 低空精度最高（钳制族同批）
            IF rng.chance_bp(acc):
                p = Projectile(shooter=air_shooter_view(a), weapon=w,
                    damage_type=w.damage_type, damage=w.damage, blast_cm=w.blast_radius_cm,
                    pos=a.pos, dest=x.pos, speed_cm_tick=w.projectile_speed_cm_tick,
                    trajectory=DIRECT, hit_target=x, will_hit=TRUE, top_attack=TRUE)
                resolve_hit(world, p)                            // 契约⑥：TOP 分支（即时结算，B-13）
            ELSE:
                jitter = (rng.sym(strafe_suppress_jitter_cm), rng.sym(strafe_suppress_jitter_cm))
                                                               // 〔v1.1 修复 AMB-01：jitter 常数化（rng[AIR]）〕
                inject_suppression_area(world, x.pos + jitter,
                                        strafe_suppression_radius_cm, w.suppression_power)
            a.ammo_left[STRAFE] −= 1

FUNCTION dump_bombs(world, a)                                   // 转对空丢弹（D015：自由落体砸落点敌我双方）
    IF world.phase != 实战: RETURN                              // 〔v1.1 修复 GAP-21：实战门补齐（弹药保留至实战）〕
    IF a.ammo_left[BOMB] <= 0: RETURN
    w = BOMB 档; rng = world.rng[AIR]
    k = a.facing // 45                                          // 航向扇区（facing 为 0..359 度值）
    FOR i IN 1..a.ammo_left[BOMB]:
        R_major = w.dispersion_cm * bomb_scatter_alt_bp[a.alt_tier] // 10000
                   * MAX(1, a.template.speed_cm_tick) // bomb_scatter_speed_ref
                   * dump_scatter_mult_bp // 10000              // 〔GAP-13：出表〕
                   * bomb_scatter_cloud_bp[world.cloud_tier] // 10000
        aim = a.pos + scale(DIR8[k], rng.sym(R_major))
                   + scale(PERP8[k], rng.sym(R_major * bomb_ellipse_ratio_bp // 10000))
        world.projectiles.append(..., dest=aim, trajectory=BALLISTIC,
            hit_target=NULL, will_hit=FALSE, shooter=air_shooter_view(a), ...)
    a.ammo_left[BOMB] = 0                                       // resolve_blast 不分敌我（R-22"敌我通吃"）
```

## §F4. 自动缠斗（R-20/D015 自卫火力）

```
FUNCTION dogfight_check(world)                                  // 每 tick
    IF world.phase != 实战: RETURN                              // 〔v1.1 修复 GAP-11：缠斗触发实战门（M4 对空口径）〕
    FOR a IN world.aircraft WHERE state NOT IN {DOGFIGHT, RTB}
                              AND world.tick >= a.no_engage_until:   // 免咬窗内不被发起（GAP-08）
        IF a.template.role == FIGHTER OR (a.template.role == ATTACK AND a.engage_air):
            FOR b IN 敌方 world.aircraft
                    WHERE b.state NOT IN {RTB, DOGFIGHT}         // 〔v1.1 修复 GAP-09：排除已缠斗目标——
                                                               // 一对一成对结构，第三机不可抢占（B-26 拍板：多机
                                                               // 缠斗不立，如需另拍）〕
                      AND world.tick >= b.no_engage_until:
                IF dist_cm(a.pos, b.pos) <= dogfight_engage_cm
                   AND b.alt_tier <= a.template.alt_ceiling
                   AND a.alt_tier <= b.template.alt_ceiling:     // 互在可及层（R-23）
                    enter_dogfight(world, a, b); BREAK
    // BOMBER/TRANSPORT 不主动发起（只被动应战+自卫）；RTB 机不被咬（B-19：脱离已付追尾代价）

FUNCTION enter_dogfight(world, a, b)
    a.任务槽 = NULL; b.任务槽 = NULL                             // 双方任务清空（R-20：缠斗期无法执行对地任务）
    FOR x IN {a, b}: x.state = DOGFIGHT; x.patrol_loop = FALSE; x.flight_plan = []
    a.dogfight = {opponent: b, round_timer: dogfight_interval_ticks, rounds: 0}
    b.dogfight = {opponent: a, round_timer: dogfight_interval_ticks, rounds: 0}
                                                               // 〔v1.1 修复 GAP-01：rounds 初始化 0（任务体字段成文）〕

FUNCTION dogfight_step(world, a)                                // 每 tick；单侧驱动（§F7 谓词）
    IF world.phase != 实战: RETURN                              // 〔v1.1 修复 GAP-11：掷骰实战门〕
    d = a.dogfight
    IF d == NULL: RETURN
    b = d.opponent                                              // 〔v1.1 修复 GAP-14：b 绑定（v1 裸引用不可求值）〕
    IF b NOT IN world.aircraft OR b.state != DOGFIGHT
       OR b.dogfight == NULL OR b.dogfight.opponent != a:
        exit_dogfight(world, a, OPPONENT_GONE); RETURN          // 〔v1.1 修复 GAP-08/16：守卫扩三条件——对手亡/对手已
                                                               // 解缠/配对失对称，均即时退出（幽灵缠斗与永锁双双闭合）〕
    d.round_timer −= 1
    IF d.round_timer > 0: RETURN
    d.round_timer = dogfight_interval_ticks
    d.rounds += 1
    FOR (atk, dfn) IN {(a, b), (b, a)}:                         // 双方互掷（R-20：对空战力/机动性）
        p = MIN(10000, dogfight_base_prob_bp * atk.template.dogfight_power
              // MAX(1, dfn.template.dogfight_power + dfn.template.maneuver))
                                                               // 〔二轮前自查修复：击落概率钳制与追尾同族（GAP-25
                                                               // 根因=bp 输出函数钳制缺失族——atk≫dfn 可超界，
                                                               // 代码锚点测试逮出；同批：strafe_acc_bp/mark_p 尾钳〕
        IF world.rng[AIR].chance_bp(p):
            air_downed(world, dfn); RETURN                      // 击落=整发（air_downed 内含对偶清理 §F1）
    FOR (gunner, target) IN {(a, b), (b, a)} WHERE gunner.template.turret_damage > 0:
        IF world.rng[AIR].chance_bp(self_defense_prob_bp):      // D015 自卫火力（伤害落库）
            target.hp_current −= gunner.template.turret_damage
            IF target.hp_current <= 0: air_downed(world, target); RETURN
    IF d.rounds >= dogfight_rounds_max:                         // B-07：回合上限强制双方脱离（无追尾）
        exit_dogfight(world, a, TIME_LIMIT)
        IF b IN world.aircraft AND b.state == DOGFIGHT: exit_dogfight(world, b, TIME_LIMIT)

FUNCTION cmd_air_disengage(world, a)                            // AirDisengageCmd——任何一方可下令脱离（R-20）
    IF a.state != DOGFIGHT: REJECT
    IF world.phase != 实战: REJECT                              // 禁火期无掷骰（GAP-11 家族）
    b = a.dogfight.opponent
    tail_p = MIN(10000, dogfight_tail_base_bp * b.template.dogfight_power
                        // MAX(1, a.template.maneuver))          // 〔v1.1 修复 GAP-25：钳制 10000bp〕
    IF world.rng[AIR].chance_bp(tail_p):
        air_downed(world, a); RETURN                           // 被追尾击落
    exit_dogfight(world, a, VOLUNTARY)
    IF b IN world.aircraft AND b.state == DOGFIGHT
       AND b.dogfight != NULL AND b.dogfight.opponent == a:
        exit_dogfight(world, b, OPPONENT_LEFT)                  // 〔v1.1 修复 GAP-08：对手同拍解缠（免追尾掷骰）——
                                                               // 双方恢复自由，不再依赖对方守卫〕
FUNCTION exit_dogfight(world, x, reason ∈ {VOLUNTARY, OPPONENT_LEFT, OPPONENT_DOWNED, OPPONENT_GONE, TIME_LIMIT})
    x.dogfight = NULL
    x.no_engage_until = world.tick + dogfight_reengage_immunity_ticks   // 免咬窗（GAP-08：脱离可达性）
    enter_patrol_hold(world, x)                                 // 待命盘旋（任务槽就位——GAP-23）

FUNCTION cmd_air_engage_air(world, a, engage)                    // AirEngageAirCmd（D015 攻击机转对空）
    IF a.template.can_engage_air == FALSE AND a.template.role != FIGHTER
       AND engage: REJECT                                        // 〔v1.3/AMB3-03：门补 FIGHTER 豁免（§D.1 #18"不读本位"
                                                               // 自洽；数据前提=硬要求⑦ FIGHTER.can_engage_air=TRUE；对齐
                                                               // air.py）〕B-21：Ju 87D 不置位
    IF a.state == RTB: REJECT                                   // 〔v1.2 修复 AMB2-05：RTB 门入族（B-22 家族对齐——
                                                               // 返场途中拨杆丢不分敌我炸弹与"RTB 拒一切任务令"冲突）〕
    IF engage AND world.phase != 实战: REJECT                   // 〔v1.2 修复 GAP2-08：开拨实战门（与 disengage 家族一致——
                                                               // 禁火期不得进入对空模式，杜绝"跳过丢弹带弹对空"边缘；
                                                               // engage==FALSE 关拨随时允许）〕
    IF engage AND a.ammo_left[BOMB] > 0: dump_bombs(world, a)    // 转对空丢弹（dump_bombs 内实战门恒过——上门已保）
    IF 本机配 engage_air 槽: a.engage_air = engage               // 〔v1.3/AMB3-03：写点槽存在门（消除对未分配机型写槽——
                                                               // 头部〔条件槽〕不变量；对齐 air.py if a.engage_air is not None〕
```

## §F5. 侦察机标记（D015/R-23/D026）

```
FUNCTION air_recon_step(world)                                  // 挂点=world_tick ③sensing 与 ④交战 之间（GAP2-01）
    IF world.phase == 结算: RETURN                              // 〔v1.3/AMB3-04→B-30：实战门改**结算门**——与地面 sensing
                                                               // 同门（地面禁火期照常发现标记），D008"开局禁火逼侦察动作"
                                                               // 对航空侦察成立；盲部署/禁火期在场侦察照常产情报〕
    IF world.tick % air_recon_period_ticks != 0: RETURN         // 〔v1.3/AMB3-09：周期门入体成文（对齐 air.py；与地面 sensing
                                                               // 头注"每 sensing_period_ticks 一次"同款+体内门）〕
    FOR a IN world.aircraft WHERE template.role == RECON
                              AND state NOT IN {RTB, DOGFIGHT}:
                                                               // 〔v1.2/AMB2-01→B-27 拍板：缠斗期被动侦察标记亦停——
                                                               // R-20"缠斗期间双方均无法执行对地任务"按全量读（对地职能
                                                               // 含被动标记；自卫火力为缠斗回合内结算、不算"执行对地任务"）〕
        cloud_bp = (a.alt_tier == HIGH ? cloud_air_recon_mult_bp[world.cloud_tier] : 10000)
                                                               // B-11：低云只削高空侦察（D026"低云削弱高空探测"）
        radius = a.template.optics_air_cm * recon_optics_alt_bp[a.alt_tier] // 10000
                                     * cloud_bp // 10000        // R-23 低空半径小/高空大（GAP-07：查表成文）
        mark_p = a.template.recon_mark_base_bp
                 * recon_mark_alt_bp[a.alt_tier] // 10000       // R-23 低空概率高/高空低（GAP-07：查表成文）
                 * MIN(10000, air_recon_speed_ref * 10000 // MAX(1, a.template.speed_cm_tick)) // 10000
                                                               // 〔v1.2 修复 GAP2-09：速度因子后补 //10000 归一——v1.1 缺
                                                               // 该除法致 mark_p 放大至 1e7 后被尾钳饱和为 10000bp（Po-2
                                                               // 全工况确定标记）；对齐 air.py recon_mark_prob_bp 归一式〕
                 * cloud_bp // 10000
        mark_p = MIN(10000, mark_p)                             // 钳制族同批（GAP-25 根因联立——二轮前自查）
        FOR u IN 敌方 alive_units:
            IF dist_cm(a.pos, u.pos) <= radius AND world.rng[AIR].chance_bp(mark_p):
                u.spotted_mask |= (1 << a.team)                  // 与地面同一位掩码语义（B-23 拍板：航空标记=逐拍概率
                IF u.mark_level < SPOTTED: u.mark_level = SPOTTED // 续标——sensing 每 5 tick 先清、recon 同拍后写、交战
                                                               // 拍（④在③后）可见；在场即持续掷，与地面侦察"每扫描
                                                               // 重发现"同构；B-15：SPOTTED 不 CALIBRATED）
```

## §F6. 空投链（R-21/D017/契约④⑤）

```
FUNCTION resolve_airdrop(world, a, s)                           // AIRDROP 任务体 RUN 越线时（strike_step 分发——GAP-10）
    player = a.player_index 对应 PlayerState                     // 〔v1.3 修复 GAP3-01：绑定行成文（GAP2-07 三缺一补齐——
                                                               // 与 §F1 air_recovery/air_downed 同式，对齐 air.py:888——勘误
                                                               // 2026-10-01 二次：原引 :868（成文时点行号），复检修复轮于其
                                                               // 上方插入 strafe_acc_bp/weapon_slot 两段后漂移，已对齐实码
                                                               // 行内绑定 p = world.players[a.player_index]）〕
    IF world.phase != 实战: RETURN                              // 禁火期不投放（载荷保留、任务挂起——AMB-07）
    rng = world.rng[AIR]
    R = airdrop_scatter_base_cm * airdrop_scatter_alt_bp[a.alt_tier] // 10000
        * MAX(1, a.template.speed_cm_tick) // airdrop_scatter_speed_ref     // 独立速度轨（AMB-04）
    beacon = 最近的 (unit→pos) IN world.beacon_by_unit WHERE unit.team == a.team
             AND dist_cm(pos, s.drop) <= airdrop_beacon_radius_cm           // B-16：最近己方信标且在吸附半径内
    IF beacon != NULL: R = R * airdrop_beacon_mult_bp // 10000   // 散布 −50%（契约⑤：公式在航空侧，出表——GAP-13）
    IF a.paratroop_cargo != NULL:                                // 空降兵（D017：落地即地面一命单位）
        FOR 每个舱内空降班:
            land = s.drop + (rng.sym(R), rng.sym(R))             // 方形散布（空投无航向椭圆语义）
            u = instantiate(该空降兵卡, a.team, a.player_index, land)      // 〔v1.3/AMB3-06：instantiate=**构造+入 world.units**
                                                               // （与地面 spawn_step/spawn_airdrop_crate 冻结用法同构——地面
                                                               // 两处 instantiate 均无后续 append）；删除航空侧显式 append 行
                                                               // （原 :601——按地面读法照写即双注册）；代码侧经 world.
                                                               // spawn_paratroop 回调承载同一语义（边界登记于 air.py）〕
                                                               // 无落地伤害（B-17：散布为唯一风险；v1 的
                                                               // inject_suppression_area(…,0) 零威力占位调用删除）
        a.paratroop_cargo = NULL
        player.air_points = MAX(0, player.air_points − airdrop_fee_points)
                                                               // 〔v1.3/AMB3-07→B-30：投放费保持 D017"作业时收取"时点，
                                                               // 下限钳防负余额（对齐 air.py）；推翻通道="B-30改B"（改呼叫
                                                               // 时点收费——余额门天然成立）〕
    ELSE:                                                        // 补给（R-21：落地实体补给箱）
        land = s.drop + (rng.sym(R), rng.sym(R))                 // 单点整箱投
        spawn_airdrop_crate(world, a.team, land,
                            a.ammo_left[SUPPLY_ROUNDS], a.ammo_left[SUPPLY_MEDICAL])   // 契约④逐字调用
        a.ammo_left[SUPPLY_ROUNDS] = 0; a.ammo_left[SUPPLY_MEDICAL] = 0
    // 箱的拾取/敌不可拾取/可摧毁由 crate=CARGO 地面语义承载（补-12/契约④）
```

## §F7. 击落结算与主循环挂点

```
FUNCTION air_check_downed(world)                                  // 每 tick（防空/自卫/追尾扣血统一口径）
    FOR a IN list(world.aircraft):
        IF a.hp_current <= 0: air_downed(world, a)                // 契约③："击落判定归航空系统"
FUNCTION remove_aircraft / air_downed                            // 见 §F1（含对偶清理与在途引用自清）

FUNCTION aircraft_tick(world)                                     // world_tick 航空段（挂地面 §F8 主循环 ④交战 之后、
    IF world.phase == 结算: RETURN                                // ⑤弹丸 之前——地面增量登记清单①第二行）
                                                               // 〔v1.1 修复 GAP-20：结算门从尾注宣称改为函数体首行〕
    FOR a IN list(world.aircraft): aircraft_move_step(world, a)   // ① 飞行（含高度过渡/strike 推进/RTB 回收）
    dogfight_check(world)                                         // ② 缠斗触发（每 tick；自带实战门）
    FOR a IN list(world.aircraft)                                 // ③ 缠斗回合（单侧驱动——list() 拷贝迭代；对手缺席时幸存方自驱动）
        WHERE a.dogfight != NULL
           AND (a.dogfight.opponent NOT IN world.aircraft
                OR a.id < a.dogfight.opponent.id):
        dogfight_step(world, a)
    air_check_downed(world)                                       // ④ 击落统一处置
    // ⑤ air_recon_step 已从本函数拆出——独立挂点登记于 world_tick ③sensing 与 ④交战 之间（地面增量登记清单①第一行，
    //    GAP2-01：sensing 先清、recon 后写、其后交战拍可见标记——v1.1 挂在本函数内④交战后与 B-23"交战拍可见"宣称矛盾）
    FOR a IN list(world.aircraft):                               // ⑥ 弹尽自动 RTB 统一判定（GAP-27+B-05 触发时机成文）
        IF a.state IN {INBOUND, PATROL}                           // 〔v1.2 修复 GAP2-11：state 白名单——STRIKE 态（RUN/EGRESS
           AND (a.template.weapons != [] OR a.template.payload_max_supply > 0
                OR a.template.paratroop_seats > 0)
                                                               //   （上接 state 白名单：STRIKE 态 RUN/EGRESS 直线走廊不被
                                                               //    自动 RTB 截断，EGRESS 完成入 PATROL 后再走——GAP2-11）
                                                               // 〔v1.3 修复 GAP3-02：资格门=**有可投送载荷资格**——
                                                               // weapons 非空（战机/攻击/轰炸）OR 补给舱 OR 空降舱（运输机）；
                                                               // v1.2 的 weapons 单门把运输机一并排除（Li-2/Ju 52 投完滞空、
                                                               // B-05/D001 失效）；侦察机（三者皆无）仍豁免"进场即返场"〕
                                                               //    〔v1.2 修复 GAP2-05：weapons 非空资格门——无武器机型
                                                               //    （侦察机）空弹药表 ALL() 空集恒真不再触发"进场即返场"〕
           AND ALL(v <= 0 FOR v IN a.ammo_left 各值)
           AND a.paratroop_cargo == NULL:
            cmd_air_rtb(world, a)
    // 相位交叉（§F7 头注成文；v1.4/AMB4-01 同步 B-30①）：AirCallCmd 无 phase 门（D001 任何时候——B-18）；投放/扫射/
    // 丢弹/空投/缠斗触发/缠斗掷骰均有实战门（§F3/§F4/§F6——M4 对空口径对齐）；**侦察标记为结算门**（§F5——B-30①：
    // 禁火期照常标记、结算期停，与地面 sensing 同门；recon 独立挂点自带结算门+周期门）；结算期 aircraft_tick 整体
    // 停止（首行）；禁火期已下攻击/空投任务**挂起回 INGRESS**（GAP2-03 修复：实战开始后重走 attack run 投放——
    // AMB-07 拍板 A 的可达实现）；engage_air 开拨须实战（GAP2-08）。
```

---

## §A. 逐卡验收对照（GDD-02 §6 每卡 × 功能点 × 承载位置）

| 卡 | 卡面功能点 | 承载（§节） |
|---|---|---|
| 苏① Po-2 侦察机 20分 | 超低空慢速侦察 | AirAltCmd→LOW（alt_ceiling=LOW）＋§F5（speed 慢→×ref÷speed 易标；LOW→recon_mark_alt_bp 高/半径小） |
| | 便宜消耗品损失不心疼 | cost_body=20＋air_downed 冷却（hp 小→冷却短） |
| | 夜间骚扰槽位（夜战首版后置） | 零消费登记（D026 夜战槽位保留） |
| 苏② Pe-2 战术轰炸机 85分 | 快速水平轰炸 | has_dive=FALSE→高度系数查表；speed 高→进场/走廊暴露时间短 |
| 苏③ Il-2M 攻击机 90分 | 重装甲抗高炮 | armor_aa 高值（resolve_hit_aa r² 曲线） |
| | 扫射火力凶 | STRAFE 档 damage/salvo |
| | 机动笨 | maneuver 低值（缠斗/追尾分母小） |
| | 炸弹+扫射+转对空丢弹全职能 | weapons=[BOMB,STRAFE]（§D.3 硬要求①）＋can_engage_air=TRUE（§F4 engage→dump_bombs） |
| 苏④ Yak-9 战斗机 70分 | 灵活便宜对空中上 | maneuver 高/power 中上；FIGHTER 恒发起（§F4） |
| | 扫射攻顶 | STRAFE 档＋top_attack=TRUE（契约⑥；硬要求②） |
| 苏⑤ Li-2 运输机 40分 | 空投空降兵/落地补给箱 | role=TRANSPORT＋paratroop_seats＋payload（§F6 两分支） |
| 苏⑥ 空降近卫步枪排 60分（预备队池） | 仅 Li-2 投送；落地即地面一命 | D017：deck 扣份（§F1）＋instantiate 入 units[]（§F6） |
| 德① Fw 189 侦察机 30分 | 稳定中高空大半径观察 | alt_ceiling=HIGH＋optics_air_cm 大＋recon_mark_base_bp 高；高空仅重防空+战机可及（R-23） |
| 德② Ju 88 战术轰炸机 95分 | 载弹多精度略高但慢 | payload_max_bombs 大＋dispersion 略小＋speed 低（防区停留长） |
| 德③ Ju 87D 斯图卡 75分 | 俯冲投弹垂直精度全场最高 | has_dive=TRUE→低空系数×dive_scatter_mult_bp（×0.3 全场最低——锚点测试断言）；can_engage_air=FALSE（B-21） |
| | 机体脆被37mm咬住即危 | hp_max/armor_aa 低（防空武器数值地面侧配平） |
| 德④ Fw 190A 战斗机 80分 | 对空战力与扫射火力双强 | dogfight_power 高＋STRAFE damage 高 |
| 德⑤ Ju 52 运输机 40分 | 同 Li-2 | 镜像数据 |
| 德⑥ 空降猎兵排 65分（预备队池） | 仅 Ju 52 投送 | 同苏⑥ |
| R-20 | 同空域自动缠斗/数秒互掷/脱离追尾/缠斗期禁对地/双层对空 | §F4 dogfight_check（engage_cm+互在可及层+实战门+DOGFIGHT/RTB/免咬窗排除）/dogfight_step（interval 互掷、守卫族、rounds 上限）/AirDisengageCmd（tail 钳制、双方解缠）/任务清空（禁对地）/地面 aa 链+§F4 |
| R-21 | 实体箱/友军拾取/敌不可拾取可摧毁/散布冒险 | §F6 补给分支→spawn_airdrop_crate（契约④）；散布式（高度×速度×信标） |
| R-22 | 扫射带状走廊/炸弹椭圆/丢弹航向椭圆敌我通吃 | §F3 resolve_strafe（走廊半宽）/resolve_bomb_release（DIR8 椭圆）/dump_bombs（航向椭圆+resolve_blast 不分敌我） |
| R-23 | 三层矩阵+云层 | 低空目视（地面冻结）+strafe_acc_alt_bp+recon 两表；bomb_scatter_alt_bp；高空=air_ceiling 数据+战机全层；云层=cloud_air_recon_mult_bp+bomb_scatter_cloud_bp（低空目视支 B-11 收窄——GDD v1.9 回写 R-23 句） |
| D015 | 租借经济五要素/飞入时间/自卫火力 | §F1（call/recovery/downed+MAX 冷却）；飞入=进场段位置化（§F1 flight_plan）；自卫=§F4 turret |
| D017 | 咬合四条 | §F1 deck 扣份＋§F6 投放费＋instantiate |
| D026 | 云层侦察/投弹 | §F5 cloud 乘区+§F3 bomb_scatter_cloud_bp（B-11/GAP-19 收窄登记——GDD v1.9 回写） |
| D059 | 低空目视/中高空仅防空 | 地面 sense_air 冻结（契约②零实现） |
| 渗透班引导空投（第2轮） | 标定落点散布-50% | §F6 beacon 分支（airdrop_beacon_mult_bp） |
| GDD-03 空军调度（契约⑦） | AI 同一命令接口/可查询量 | §D.5 九命令；air_cooldowns/air_points/ammo_left/state 可查询 |

---

## §B. 拍板预登记表（v1.3：B-01~B-30；每条已按推荐执行，推翻通道="N 改B"）

> B-01~B-20 维持 v1 原文、B-21~B-26 见 v1.1、B-27/B-28 见 v1.2（同目录前版文件）；B-29/B-30 为三轮 ambiguity 收敛新增（上表末两行）。全部条目正式存档于 docs/GDD-02-航空拍板清单-v1.md。

| # | 决策点 | 推荐（本文执行） | 理由 | 负面影响 | 推翻通道 |
|---|---|---|---|---|---|
| B-21 | Ju 87D 转对空资格（AMB-05） | can_engage_air=FALSE（不置） | 卡面未提转对空；"转对空丢弹全职能"为 Il-2 卡面独有表述；D015 角色文按卡面收窄 | 斯图卡被咬只能靠脱离掷骰（符合"机体脆"定位） | B-21 改B（置位——D015 角色文全量执行） |
| B-22 | RTB 可逆性（AMB-09） | RTB 不可逆（strike/airdrop/move/patrol 全拒 RTB 态） | 与 D001"不可主动撤回"精神一致；命令家族口径统一 | 返场误点须等回收后重新呼叫（新租借交易） | B-22 改B（允许攻击令拉回） |
| B-23 | 侦察标记时序语义（GAP-05 修复方案） | 逐拍概率续标：air_recon_period=sensing 同拍、挂点在 sensing 后、每拍掷骰置位 | 与地面侦察"每扫描重发现"同构；零地面改动；标记在交战拍可见 | 续标失败拍=目标短暂不可引导（概率性标记的本义） | B-23 改B（持久旁表 air_mark_until——需地面消费点增量） |
| B-24 | "每机型限2"承载（GAP-22） | 同型在空数 ≤2 呼叫门 | 租借制无卡组份消耗；D032 限份在租借语境=同时在场限 | 同型轮转节奏受限（双机上限） | B-24 改B（卡组构筑限份、运行时不限） |
| B-25 | 冷却粒度（GAP-06） | 机型级同键取 MAX | B-04 防炮灰刷屏意图（击落惩罚锁整型轮转）；单值表结构最简 | 健康机的快速轮转被同型击落惩罚波及 | B-25 改B（实例级冷却表） |
| B-26 | 多机缠斗（GAP-09） | 不立：一对一成对结构（第三机不可抢占） | R-20"双方互相掷"一对一语义；成对结构可确定性单侧驱动 | 2v1 优势须逐对解决（第二机须等第一对结束） | B-26 改B（多机混战模型——另立设计） |
| B-27 | 缠斗期被动侦察标记（AMB2-01）+ RTB 舱内空降班（AMB2-03） | ①缠斗期侦察标记停（state 过滤含 DOGFIGHT——R-20"无法执行对地任务"全量读）；②运输机安全返场时舱内未投班**退 deck 份**（班随机体回场可再呼叫——与本体价回收同哲学；机毁不退=B-06） | R-20 字面全量；租借"未消耗回池"一致性 | 侦察机被咬即断情报（战术代价）；返场退份可刷"白嫖进场侦察"（运输机本体价已回收、班无损——但有冷却节流） | B-27 改B（①标记不停/②返场班亡） |
| B-28 | 扫射 salvo 语义（AMB2-06） | **逐目标各 salvo**（走廊内每个敌方元素各掷 salvo 发、弹账随目标数消耗） | 现行为即此；机炮扫射扫过全走廊的物理语义 | 走廊内目标多时弹药消耗快（弹尽自动 RTB 提前） | B-28 改B（整走廊共享 salvo 配额） |
| B-29 | 高度层变更 × RTB 门族（AMB3-02）+ 手动 RTB 截断走廊（AMB3-05） | ①cmd_air_alt 不入 B-22 任务令门族（返场中变层=无害微操特许）；②**手动 AirRTBCmd 为出击弃权特许**——允许任意非缠斗态（含 RUN/EGRESS）截断走廊直线离场，登记为与 AIR-00 §一.2"沿走廊直线离场"的已接受偏差（该通道同时是禁火挂起场景的自救路径，不可封死） | 命令族口径成文（alt 无任务语义冲突；弃权是玩家权利）；自动 RTB 已有 STRIKE 豁免（GAP2-11）保走廊完整 | 手动弃权可滥用作"投完即走"（与自动路径行为一致，无超额收益） | B-29 改B（①alt 入族 REJECT／②手动 RTB 补 RUN/EGRESS 门） |
| B-30 | 侦察标记相位门（AMB3-04）+ 投放费余额（AMB3-07） | ①§F5 实战门收窄为**结算门**（禁火期航空侦察照常标记——与地面 sensing 同门、D008"逼侦察动作"对航空成立）；②投放费保持 D017"作业时收取"时点+**下限钳** MAX(0, points−fee) 防负余额 | ①D008 设计意图+地面同构；②D017 字面时点+经济健全 | ①禁火期航空有情报先手（与地面侦察对等——非超额）；②余额不足时费用部分豁免（边缘宽松） | B-30 改B（①恢复实战门"禁火零情报"／②投放费移呼叫时点收） |

**v1 §B 原表维持项**（B-01 独立模板/B-02 复用武器/B-03 扫射仅敌方/B-04 击落也冷却/B-05 弹尽自动 RTB/B-06 空降随机毁/B-07 回合上限/B-08 高度过渡/B-09 俯冲低空系数/B-10 冷却公式/B-11 低云收窄/B-12 装机扣份/B-13 一次性走廊结算/B-14 炸弹走地面弹丸/B-15 SPOTTED 档/B-16 信标最近吸附/B-17 无落地伤害/B-18 呼叫无 phase 门/B-19 RTB 豁免被咬/B-20 CAP 词汇 GDD 补句）——全部经三遍审查确认与 GDD/契约无冲突，原文见 v1 §B。

**假设清单（v1.1 维持 H-1~H-6，另增）**：
- H-7：AMB-02/AMB-03/AMB-04/AMB-08/AMB-09/AMB-07 按上表推荐收敛（B-22/B-23/§D.0 拆轨/到达判据/挂起语义/派生式）；AMB-01 jitter 常数化；AMB-06 引注改正（B-03）。

---

## §C. v1 → v1.1 变更记录（审查问题文档 v1 全部 28 gap + 9 ambiguity 逐条处置）

> 依据：docs/GDD-02-航空伪代码审查问题文档-v1.md（blocker 0 / gap 28 / ambiguity 9）。修复策略：按共同根因联立解，非逐条补丁。

**联立解 1（任务槽判别联合——GAP-01/10/23 + AMB-03）**：§D.2 #14 改判别联合 {kind: STRIKE|PATROL|AIRDROP}（统一"任务槽"命名，v1 三名漂移废除）；strike_step 补 AIRDROP 分发与 line_point 判据（GAP-10——空投链可达）；enter_patrol_hold 统一待命入口+回卷判空短路（GAP-23）；facing/engage_air/paratroop_cargo/no_engage_until 入账、dogfight.rounds 入体、is_disengaging 死槽删除、airdrop_fee_points 定义行（GAP-01）；entry_tier=MIN(MID, alt_ceiling) 派生式成文（AMB-03）。
**联立解 2（DIR8/PERP8 重建——GAP-03）**：全圆 8 向量（模长 7/7.07，各向异性 ≤1%）+PERP8+DIR_NORM+`octant//45` 索引；§T 椭圆/走廊公式与 §F3/§F6 消费点全部重写；"模长≈1/≤12%"错误宣称句删除。
**联立解 3（缠斗状态机守卫族——GAP-08/09/11/14/16/25）**：dogfight_step 守卫扩三条件+b 绑定+实战门；dogfight_check 排除 DOGFIGHT 目标+免咬窗+实战门；cmd_air_disengage 双方解振+tail 钳制；air_downed 对偶清理；驱动谓词改"对手缺席或 id 较小"+list() 拷贝；rounds 初始化（详上各§节）。
**联立解 4（相位门族——GAP-11/20/21 + AMB-07）**：dogfight_check/step、cmd_air_disengage、dump_bombs 实战门；aircraft_tick 首行结算门（伪语句改注释）；AMB-07 拍板 A：禁火期任务挂起于 RUN 冻结、实战即投放。
**联立解 5（经济账目族——GAP-06/22/26 + AMB-08/09）**：slot_ok 门生效；同型在空≤2 呼叫门（B-24）；air_cooldowns 两写点 MAX 合并（B-25）；RTB 回收判据=到达航点（AMB-08）；strike/airdrop 补 RTB 门（AMB-09/B-22）。
**联立解 6（公式轨纪律——GAP-07/13/15/24/25 + AMB-01/04）**：§D.0 增 10 字段（recon 两表/beacon/dump/jitter/airdrop 速度轨/投放费/盘旋半径/免咬窗/云层投弹）并统一 36 字段行单一口径（GAP-24——头部/标题/注/§D.6 五处对齐）；salvo_per_drop 删除改每发递减（GAP-15）；tail_p 钳制（GAP-25）；两处写死数值出表（GAP-13）。
**联立解 7（跨系统接口——GAP-02/05/17/18/19 + AMB-02/06）**：remove_aircraft 自清在途弹丸引用（GAP-02——纸面守卫引注作废）；air_recon 与 sensing 同拍+挂点其后+实战门（GAP-05，B-23）；air_shooter_view 适配器+冻结名对齐+扫射弹补 pos（GAP-17）；bomb_scatter_cloud_bp 投弹云层乘区（GAP-18）；GAP-19=B-11 收窄成文+GDD v1.9 回写 R-23 句（阶段 5 执行，本版 §A 标注）；"零地面文件改动"表述作废改"地面增量登记清单 3 项"（AMB-02）；§F3 扫射引注改 B-03（AMB-06）。
**单点修复**：GAP-04 进场航点（cmd_air_call 写 flight_plan=[进场终点]）；GAP-12 键枚举统一四键+全键初始化；GAP-27 aircraft_tick 尾部弹尽自动 RTB 统一判定；GAP-28 move/strike/airdrop 补 INGRESS 中断门（RUN/EGRESS 不可转向/重下）。

**ambiguity 处置汇总**：AMB-01→常数化；AMB-02→口径修订；AMB-03→派生式；AMB-04→拆轨；AMB-05→B-21；AMB-06→引注改正；AMB-07→拍板 A 挂起；AMB-08→到达判据；AMB-09→B-22。九条全部收敛（无需另待拍板）。

**二轮前自查修复（代码锚点测试逮出，随 v1.1 同批登记）**：
- 自查-1（GAP-25 根因扩围）：击落概率/扫射精度/侦察标记概率三处 bp 输出补 MIN(10000,…) 尾钳——v1 §F4 注释"p<base 恒成立"为误（atk 与 dfn 独立，atk≫dfn 可超界）；tests/test_air_curves.py 锚点断言（99 vs (1+0)→钳 10000）。
- 自查-2（刻度错误）：dump_scatter_mult_bp 初值 2000（×0.2）修正为 20000（×2.0 放大方向）——锚点测试（低空 600×2=1200）逮出。

---

## §D. v1.1 → v1.2 变更记录（二轮审查问题文档 v1.1 全部 14 gap + 8 ambiguity 逐条处置）

> 依据：docs/GDD-02-航空伪代码审查问题文档-v1.1.md（二轮复审：新发现 blocker 0 / gap 14 / ambiguity 8；一轮修复复核 23 已修复 / 5 部分修复 / 0 未修复）。修复策略延续共同根因联立解。

**组 A（弹尽判定族——GAP2-05/11 + AMB2-01）**：§F7⑥ 判据改三重限定 `state IN {INBOUND, PATROL} AND template.weapons != [] AND ALL(≤0) AND cargo==NULL`——白名单 state 使 STRIKE（RUN/EGRESS 直线走廊）不被自动 RTB 截断（GAP2-11），weapons 非空资格门消除空弹药表 ALL() 空集恒真（GAP2-05：侦察机不再"进场即返场"）；§F5 过滤扩 DOGFIGHT（AMB2-01→B-27①：缠斗期被动侦察标记停）。
**组 B（禁火挂起族——GAP2-03/08 + AMB2-05）**：strike_step INGRESS→RUN 转换补实战门（禁火期悬停 run_start，实战首拍转换+扫射结算）；RUN 越线禁火期**回 INGRESS 重走 attack run**（v1.1"保持 RUN"只冻相位不冻位移→穿线后越线窗口永不再真的死锁拔除——AMB-07 拍板 A 可达实现）；cmd_air_engage_air 补 RTB 门+开拨实战门（AMB2-05/GAP2-08：禁火期不得开拨、关拨随时允许、返场途中不得拨杆）。
**组 C（初始化与门族——GAP2-04/06/13）**：§F1 弹药初始化成文（STRAFE←weapons[] 弹量，§D.1 #13 元组项成消费点；BOMB/SUPPLY←payload）——GAP2-04 扫射职能链通；cmd_air_patrol 门改统一式（判空+双变体覆盖，GAP2-06）；cmd_air_call 补 payload 容量门（payload_max 两字段成消费点，GAP2-13）。
**组 D（文档精度族——GAP2-02/09/10/12）**：常数账目 36→37 七处对齐（头部/§D.0 标题/账目注/§D.6/§C/变更记录/tables.py 段注释——实测 37 行）；§F5 mark_p 速度因子后补 //10000 归一（对齐 air.py，GAP2-09）；§T 索引示例"270→5"改"270→6"+"≤1%"改"≈1%（1.015%）"（GAP2-10）；§D.2 增 #0 template 指针槽（账目 20→21，头部/§D.6 同步，GAP2-12）+构造默认成文（AMB2-02）。
**组 E（速记与对齐——GAP2-07/14）**：air_downed/air_recovery/resolve_airdrop 补 player 绑定行、template_id 限定 a.template.template_id（GAP2-07——GAP-14 同族三处清零）；air.py dump 散布次序对齐伪代码（dump 乘区先于 cloud）+dump 分支 tier_idx=实飞 alt_tier（GAP2-14，代码侧改）。
**AMB 收敛**：AMB2-01→B-27①；AMB2-02→构造默认成文+engage_air 槽条件扩 FIGHTER；AMB2-03→B-27②（返场退 deck 份）；AMB2-04→remove_aircraft 注释口径改"近失压制注入"；AMB2-05→RTB 门；AMB2-06→B-28（逐目标 salvo 成文）；AMB2-07→§T 点到线段式升格成文；AMB2-08→§D.3 硬要求⑥（空射 crit_mod_permille=0）。八条全部收敛。

---

## §E. v1.2 → v1.3 变更记录（三轮审查问题文档 v1.2 全部 5 gap + 9 ambiguity 逐条处置）

> 依据：docs/GDD-02-航空伪代码审查问题文档-v1.2.md（三轮复审：新发现 blocker 0 / gap 5 / AMB 9；二轮修复复核 12 已修复 / 2 部分修复 / 0 未修复）。5 条 gap 全部为修复文本自身缺陷（多数经 air.py 反证文档缺行）。

- **GAP3-01**：§F6 resolve_airdrop 体首行补 player 绑定行（GAP2-07"三缺一"补齐——对齐 air.py:868 行内绑定；勘误 2026-10-01 二次注：:868 为 v1.3 成文时点行号，复检修复轮插入后现行实码为 :888（见 §F6 现行注）——本条为时点史料，按原样保留）。
- **GAP3-02**：§F7⑥ 资格门改三析取 `weapons != [] OR payload_max_supply > 0 OR paratroop_seats > 0`——运输机投送完毕恢复自动 RTB（B-05/D001 修复回归闭合），侦察机豁免维持；air.py 同步+行为测试补运输机用例。
- **GAP3-03**：§T:21 成文式符号改正 `t = CLAMP(0, ab2, ap·ab)`（ap=**a−p**——与 air.py 位级一致；三轮定稿人数值复算 5192 vs 1400 的分歧消除）。〔v1.4 现状注（2026-10-01 补）：本条为 v1.3 时点史料，按原样保留——该改法经四轮 GAP4-01 判定为符号错误（"去负号"与"翻转 ap 定义"两个互斥改法同时套用、相互抵消），v1.4 已单改为 `t = CLAMP(0, ab2, −(ap·ab))` 且 `ap = a − p`，现行成文式见 §T:21 与 §F 变更记录；终检报告第九章瑕疵④登记，注释级注记零行为变更〕
- **GAP3-04**：§F1 构造行补 `hp_current=template.hp_max`（构造默认式"数值槽初值 0"的满血例外成文——字面进场即坠消除）。
- **GAP3-05**：§F1 构造行补 `id = world.next_aircraft_id++`（构造默认式不豁免数值槽的连带死锁路径消除；next_aircraft_id 成消费点）。
- **AMB 收敛**：AMB3-01→§D.3 STRAFE 行补 B-28 说明；AMB3-02/05→B-29（alt 不入任务令门族+手动 RTB 弃权特许）；AMB3-03→§F4 门补 FIGHTER 豁免+写点槽存在门+硬要求⑦ FIGHTER.can_engage_air=TRUE（对齐 air.py 既有实现）；AMB3-04→B-30①（§F5 实战门改结算门——禁火期航空侦察照常标记）；AMB3-06→instantiate 注册语义成文（构造+入 world.units 地面同构，删航空显式 append）；AMB3-07→B-30②（投放费下限钳）；AMB3-08→§D.0 增 air_per_type_max=2（在空门出表，账目 37→38）；AMB3-09→§F5 补周期门（对齐 air.py）。九条全部收敛。

---

## §F. v1.3 → v1.4 变更记录（四轮审查问题文档 v1.3 全部 1 gap + 2 ambiguity 逐条处置）

> 依据：docs/GDD-02-航空伪代码审查问题文档-v1.3.md（四轮复审：新发现 blocker 0 / gap 1 / AMB 2；三轮修复复核 4 已修复 / 0 部分 / 1 未修复〔GAP3-03〕，9 AMB 中 8 已修复 / 1 部分修复〔AMB3-04〕）。本轮三项修复全部为单行，且**落盘后对成文行独立数值复算通过**（四轮审查指出的"落盘复算缺失"环节补齐）。

- **GAP4-01（GAP3-03 复报）**：§T:21 成文式单改——负号保留 `t = CLAMP(0, ab2, −(ap·ab))` 且 `ap = a − p`（v1.3 错把"去负号"与"翻转 ap 定义"两个互斥改法同时套用、相互抵消致符号错误原样保留）；**落盘复算**：四锚点 (5000,0)→0、(5000,1400)→1400、(5000,1600)→1600、垂足钳端点锚 (−3000,4000)→3000（勘误 2026-10-01：计数原书"三锚点"，实列四项，按正文实际勘正为四——与下文变更记录"四项锚点"及 §T:21 现行锚点列表一致；终检报告第九章瑕疵⑤登记，注释级勘误零行为变更）——按 v1.4 字面式 python3 实跑全过（含全网格 1120 样点对 air.py 实现式逐点相等验证）；行内 air.py 引注改 :103/:108（时点史料注 2026-10-01：该引注后经注释级勘误对齐实码为 :106/:111，复检修复轮插入后经二次勘误现行为 :111/:116，见 §T:21 现行文——本尾句为 v1.4 落盘时点动作记录，按原样保留）。
- **AMB4-01**：§F7 尾注"侦察标记"摘出实战门清单、改为"侦察标记为结算门（§F5——B-30①……recon 独立挂点自带结算门+周期门）"——宣称句与 §F5 现行机械承载矛盾消除。
- **AMB4-02**：§F1 构造行补 `team = player.team, player_index = player.index` 双键（契约① team 槽与经济归属槽显式入构造行，默认式字面覆盖读法消除；对齐 air.py:390-391；勘误 2026-10-01 二次注：:390-391 为 v1.4 落盘时点行号，复检修复轮插入后现行实码为 :396-397（见 §F1 现行注）——本条为时点史料，按原样保留）。

---

## 变更记录

- 2026-10-01（二次勘误）：注释级勘误（不 bump 版本）：复检修复轮（同日）于 air.py 插入 strafe_acc_bp（§F3 扫射精度钳制式）与 weapon_slot 统一谓词（§D.3 档身份按配置判定）两段，本文全部 air.py 行号引注随之漂移，逐处对齐实码现行行号——① §T:21 引注 :106/:111→:111/:116；② §F1 构造行注 :390-391→:396-397；③ §F6 绑定行注 :868→:888；④ §E GAP3-01 与 §F AMB4-02 两条时点史料加勘注（记述本体按原样保留）；⑤ §F GAP4-01 尾句史料注同步。公式/构造/绑定语义零变化。理由：注释级勘误零行为变更。
- 2026-10-01：注释级勘误（不 bump 版本）：① §T:21（勘误时 :21）行内 air.py 引注 :103/:108→:106/:111（与实码对齐——公式同一性经终检路B 12996 网格点复算零分歧）；② §E GAP3-03 条（勘误时 :773）补 v1.4 现状注记（历史记述本体按原样保留）；③ §F GAP4-01 落盘复算计数"三锚点"→"四锚点"（实列四项，以正文实际为准；该条尾句"行内 air.py 引注改 :103/:108"为 v1.4 落盘时点史料，按原样保留）。依据 GDD-02-航空终检报告-v1.md 第九章瑕疵③④⑤。理由：注释级勘误零行为变更。
- 2026-09-29：v1.4（四轮审查问题文档 v1.3 全量修复：GAP4-01 成文式负号单改（落盘后独立数值复算通过——四项锚点+全网格 1120 样点对 air.py 逐点相等）、AMB4-01 §F7 尾注同步 B-30①、AMB4-02 构造行补 team/player_index；§F 变更记录成文）。
- 2026-09-29：v1.3（三轮 5 gap+9 AMB 修复）。
- 2026-09-29：v1.2（二轮 14 gap 五组联立修复+8 AMB 收敛）。
- 2026-09-29：v1.1（一轮 28 gap 联立修复+9 AMB 收敛+2 项二轮前自查修复）。
- 2026-09-29：v1 初版（§T/§D/§F/§A/§B；单一权威版）。
