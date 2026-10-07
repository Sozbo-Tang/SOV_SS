# AIR-00 航空机制调研锚点（v1）

> 任务阶段 0 产物：参照游戏航空机制锚点调研——**只锚机制与官方数值，不锚实现**。
> 用途：为 AIR_UNITS_PSEUDOCODE_IMPL 的设计决策提供参照系；GDD-02 v1.8 §6（R-20~R-23）与 GDD-00 D015/D017/D026/D059 为功能基准，本调研只做印证与差异登记，不引入 GDD 未授权机制。
> 调研日期：2026-09-29（联网检索，来源见文末）。

---

## 一、六大调研主题锚点

### 1. 高度层与探测/拦截关系

**参照（Broken Arrow，社区共识）**：
- 飞机可切换高/低两档高度（本作为低/中/高三层，更细）。
- **低飞**：大幅缩短地面雷达与大部分 SAM 的探测距离，与隐身性能（本作=隐蔽/慢速）叠加可穿透防空网；但低飞**不躲**高空战机的"下视雷达"（本作对应：高空仅重防空**与战斗机**可及——R-23 明文战斗机不受高度限制）；低飞暴露于近程红外防空/高炮（本作对应：低空高炮威胁最大）。
- 探测结果是"探测半径的乘算关系"而非开关——机型（本作机体侦察能力）×高度×传感器类型三方共同决定。

**对本作的印证**：R-23 三层矩阵（低空=目视可见+高炮威胁最大+扫射精度最高；中空=轻/中防空上限、重防空可及；高空=仅重防空+战斗机可及）与 D059（低空目视/中高空仅防空探测）和参照游戏机制同构，方向正确、无需改写。**云层**（D026：低云削弱高空探测、掩护低空突防）在参照游戏中无直接对应物，属本作自有机理——实现按"乘算系数挂在对应探测分支"处理（见伪代码 §D.0 cloud 段）。

### 2. 进出场航线（attack run：进场-投放-脱离）

**参照（Wargame: Red Dragon，社区指南共识）**：
- 飞机呼叫后沿**固定进场走廊（air corridor）**直线进入；attack run 中**不可自由转向**——投弹/扫射在直线上完成，随后沿走廊直线离场。
- 走廊沿线（进/离场双向）部署的防空会持续撕咬飞机——**航线规划本身是博弈**（选进场方向=选穿哪片防空区）。
- 冲过头（错过投放线）= 本次进袭作废，应立即撤离。

**对本作的印证**：GDD §6 阵营差异备注"空袭永远是手术刀而非按钮"与 R-22（扫射=沿飞行方向带状走廊）已隐含 attack run 语义；本作伪代码按「进场建立航向 → 投放线结算 → 直线脱离 → 脱离后恢复受令」状态机承载（§F），投放线之前/之后不可中途转向（与参照一致）。进场方向由玩家标定目标点与飞机当前位置推导（连线方向），不设独立走廊编辑。

### 3. 载荷（炸弹/火箭/机炮）

**参照（WRD 武器分类 + WWII 轰炸方法史实）**：
- 载荷类型决定对地形态：无制导炸弹=区域散布；集束/凝固汽油=大半径低伤害；机炮/火箭=直射点目标。
- **水平轰炸极不准、俯冲轰炸精准**（WWII 史实共识：Ju 87 俯冲投弹命中率数倍于水平轰炸）——WRD 把它做成"激光制导 vs 普通炸弹"的精度差，本作 GDD 直接锚了史实口径（斯图卡"俯冲投弹垂直精度全场最高"、Ju 88"载弹多精度略高但慢"、R-23 中空水平散布中等/高空大）。
- 受损中止投弹（WRD：轰炸机被重创/panic 时丢弃载荷中止轰炸）——**本作不引入**：GDD D015 仅授权"转对空丢弹"一种强制丢弹；受损中止无 GDD 依据，登记为差异（见 §四-6），如需要须另立拍板。

**对本作的印证**：卡面机型差异（Pe-2 快速水平轰炸投弹前暴露时间短 / Ju 88 载弹多精度略高但慢 / 斯图卡俯冲垂直精度最高 / Il-2 炸弹+扫射+转对空全职能）全部可由「模板数值（散布乘区、载弹量、速度）×R-22 双形态」承载，零新机制。

### 4. 战斗空中巡逻（CAP）

**参照（WRD）**：战斗机在站盘旋待命，敌机进入拦截半径自动接战；CAP 机须远离长程防空圈（在站时间越长吃防空越久）。
**对本作**：GDD R-20"敌对战机同空域相遇→自动进入缠斗"已隐含 CAP 语义（有战斗机在场=自动威慑），但**GDD 未明文巡逻指令**。伪代码按「AirPatrolCmd（绕标定点盘旋）+ 同空域自动缠斗」承载（巡逻=航点环路，不新增状态机）；CAP 一词不写入 GDD 正文（阶段 5 拍板确认）。

### 5. 被防空打击的命中模型

**参照（WRD/Broken Arrow 共识）**：
- 防空命中=概率掷骰（命中率×ECM 对抗），伤害落库扣血，血尽坠落；非"一击必杀"。
- 高炮（gun AAA）对低空目标命中率显著更高（本作对应：R-23 低空高炮威胁最大 + R-17 对空探测半径门）。
- 本作地面定稿已冻结：`fire_aa`（掷骰散布）→ `resolve_hit_aa`（对空一律 HE 曲线 r²×1000÷(r²+1000)，armor_aa 单值）→ "击落判定归航空系统"（hp≤0 处置）。航空侧只欠击落处置与经济后果，命中模型契约已闭环。

### 6. 呼叫制经济（点数召唤 vs 常驻单位）

**参照（WRD）**：飞机=点数呼叫的临时单位；完成任务自动返场→回场重装（冷却计时）→可再呼叫；**被击落=数分钟级冷却**（远长于安全返场）。
**对本作**：D015 租借制（出动=本体价+弹药价；安全飞离退本体价、弹药价不退；冷却随受损增长；击落=本体价损失）在参照基础上多了"租借返还"层——本作经济更精细，实现按 D015 逐句承载（§F economy 段）。方向与参照一致：**击落惩罚 > 受损返场惩罚 > 满血返场**，三档梯度成立。

---

## 二、航空接口契约对表（地面定稿冻结的航空消费端；航空生产端逐条满足，不得改动地面文件）

> 依据：GROUND_UNITS_PSEUDOCODE_IMPL_v1.7.md（定稿只读）。"消费端位置"=地面侧已冻结的读取点；航空侧必须保证字段/语义逐条成立。

| # | 契约 | 地面消费端位置（v1.7 冻结） | 航空侧义务 |
|---|---|---|---|
| ① | `world.aircraft[]` 列表 + `AircraftRef{id, team, pos, alt_tier, hp_current, hp_max, armor_aa, spotted_mask}` | §D.6（:230）、§F9 头注"航空系统提供（pos/alt_tier/hp/armor_aa/spotted_mask），地面侧不推进其运动" | AircraftInstance 结构**逐字段包含 AircraftRef 八字段**（超集允许）；pos/alt_tier 由航空侧唯一推进；spotted_mask 由地面 sense_air 读写、航空侧只读（含被摧毁时的消费安全） |
| ② | `sense_air` 读 `a.alt_tier`、`g.air_ceiling`（`a.alt_tier <= g.air_ceiling` 有序比较）、`g.optics_air_cm`、`aa_roster` 名单、低空目视分支、M17 对偶清位 | §F3 sense_air（:614-627）、§F7 spawn_step 登记 | AltTier 三层有序枚举 LOW<MID<HIGH 与地面一致（types.py AltTier 0/1/2）；航空单位不进 units[]/aa_roster（它不是地面单位）；对空探测/清位全部由地面侧承载，航空侧不重复实现——航空侧只保证 a.pos/a.alt_tier 每 tick 就绪 |
| ③ | `aa_try_engage` 候选谓词：`(a.spotted_mask & 我队位) AND (a.alt_tier <= air_ceiling) AND dist <= max_range`；目标选择=最近 | §F4（:885-903） | 航空侧维持 spotted_mask 位语义（队伍位掩码）；不改变地面选择逻辑；被防空命中走 `fire_aa`→Projectile(hit_target=AircraftRef)→`resolve_hit_aa` 扣 hp——**击落判定归航空侧**（hp≤0 → 击落处置：移出 world.aircraft、经济结算、冷却） |
| ④ | `spawn_airdrop_crate(world, team, pos, rounds, medical)`：一次性 CARGO 单位、hasSupply 位必配、supply_radius_cm=8000、敌方不可拾取可摧毁 | §F6（:1343-1354）、补-12 | 航空侧空投补给落地时**逐字调用**该接口；不绕开自建补给箱实体 |
| ⑤ | 渗透班信标：`SetAirdropBeaconCmd 写 world.beacon_by_unit[unit] = pos`（方案9 旁表）；"航空系统投散时按键读取该标记 → **散布 ×0.5**（接口约定，**公式在航空侧**）"；标定单位全灭由 unregister_unit_refs 按键注销 | §D.6/§D.7/§F9（:1501-1504）、§F6 cmd_set_airdrop_beacon | 航空侧空投散布公式读 world.beacon_by_unit（己方键、取距投放点最近且在吸附半径内者）→ 散布 ×5000bp；信标不算暴露、不清渗透身份（§F6 口径维持） |
| ⑥ | 顶攻：`resolve_hit` 中 `facing = TOP IF p.top_attack`；`compute_hit_facing(top_attack)` 分支；armor_ke/he `{F,S,R,T}` 的 **T 槽"仅空袭读取"** | §F1（:335-336）、D.2#4-5、combat.py compute_hit_facing | 航空对地武器（扫射/炸弹直击）结算时**带 top_attack=TRUE** 调用地面 resolve_hit 通路；机炮扫射弹丸按攻顶结算（D015/R-22）；炸弹走 resolve_blast（落点溅射不分敌我，无攻顶面概念——R-22 椭圆散布） |
| ⑦ | GDD-03 空军调度：AI 作为虚拟玩家走同一条命令接口（L2 空军出击调度器每 5 秒打分、走廊检查=绕开 R-17 探测圈、预算=本体+弹药价、冷却与受损挂钩） | GDD-03 §4.3、TECH-00 §4 命令层 | 航空命令集全部走 §D.7 命令驱动形态（AI 可发同一命令）；航空状态对 AI 暴露为可查询量（冷却表、弹药余量、在空状态）；不设"仅人类可发"的命令 |

**通道纪律**（TECH-00/任务硬纪律）：航空随机数新增独立 **AIR 通道**（rng.Channels 空闲槽位 7，`_COUNT=8` 已覆盖），不复用地面 HIT/SCATTER/SPOT/CRIT/SNIPER/SONAR/ECONOMY 任何通道序列。航空对地武器若复用地面弹丸管线（Projectile→resolve_blast），其掷骰显式传 rng[AIR]。

---

## 三、本作 GDD 已定 vs 参照差异登记（不引入，仅存照）

| # | 参照机制 | 本作 GDD 状态 | 处置 |
|---|---|---|---|
| 1 | 雷达开关反制（SEAD） | 无雷达/SEAD 体系（1944 年口径：目视+听音探测） | 不引入；R-17 对空探测即"传感器" |
| 2 | ECM/隐身数值对抗 | 隐蔽值体系（D003）不延伸到空中（飞机被探测走 R-17/D059 分支，无 stealth 槽） | 不引入；armor_aa 是飞机唯一防护参数（契约①） |
| 3 | 低飞不躲下视雷达 | 已由 R-23"高空仅重防空+**战斗机**可及"承载（战斗机全高度可及） | 承载在位 |
| 4 | 受损中止投弹（damage threshold abort） | D015 仅授权"转对空丢弹" | 不引入；翻案须另立拍板（登记于伪代码假设清单） |
| 5 | 燃油/在空时限 | GDD 无燃油条目（D015 出击循环=弹药+冷却承载） | 不设燃油槽；在空时间由弹药耗尽自动返场承载（伪代码拍板项） |
| 6 | 弹幕盲射防空 | 已废止（D018/R-17 修正） | 维持废止 |

---

## 四、来源

1. [How does low flight jet mechanic work (r/BrokenArrowTheGame)](https://www.reddit.com/r/BrokenArrowTheGame/comments/1mzzzlr/how_does_low_flight_jet_mechanic_work_and_how)
2. [How do you guys deal with F-35's bombing your stuff (r/BrokenArrowTheGame)](https://www.reddit.com/r/BrokenArrowTheGame/comments/1njlzym/how_do_you_guys_deal_with_f35s_bombing_ur_stuff)
3. [Q: How to protect your PACS? (高空战机雷达对低空目标)](https://www.reddit.com/r/BrokenArrowTheGame/comments/1mptqw3/q_how_do_you_protect_your_pacs)
4. [Should you send in air tax at high or low altitude at the start?](https://www.reddit.com/r/BrokenArrowTheGame/comments/1m1c1fu/should_you_send_in_air_tax_at_high_or_low)
5. [SandyGunfox: Wargame Red Dragon Guide（air corridor/attack run 章节）](https://docs.google.com/document/d/1kcGXLvyyHf7Ux_oU7vvuvkAFOufTLioSW6rpd-_j6ec/mobilebasic)
6. [honhonhonhon: Red Dragon aircraft guide（载荷分类/SEAD 时机）](https://honhonhonhon.wordpress.com)
7. [GameFAQs Red Dragon Strategy Guide（attack run 冲过头即撤离）](https://gamefaqs.gamespot.com)
8. [Reddit r/wargame: SEAD 反制=雷达关机](https://www.reddit.com/r/wargame/comments/58f6uf/really_need_tips_for_taking_out_aa)
9. [ww2aircraft.net: 水平轰炸极不准 vs 俯冲轰炸精准（史实共识）](https://ww2aircraft.net)
10. [BoardGameGeek: Declassified US Army WW2 tank casualties 讨论（战术级空袭效率）](https://boardgamegeek.com)

---

## 变更记录

- 2026-09-29：v1 初版（阶段 0 调研产物：六大主题锚点 + 七条航空接口契约对表 + 六项参照差异登记）。
