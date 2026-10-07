# 地面单位实现伪代码——§13 对照表落地版（v1.7-IMPL）

> 上游：GROUND_UNITS_PSEUDOCODE_v1.4.md（机制权威；口径映射见 §D.8）+ TECH-00（整型确定性约束）+ GDD-02-函数变量调用频率与替代方案.md（19 条方案，v1.2 落实）+ 审查问题文档 v1.2（13 项，v1.3 修复）与 v1.3（29 项，v1.4 修复其中 17 项机械缺陷——见文末 §W 变更记录；其余 12 项为设计决策，见 docs/GDD-02-拍板清单-v1.4.md）+ 审查问题文档 v1.4（61 条：blocker 5 / gap 32 / ambiguity 24——v1.5 落实机械修复 M1~M28 与**拖曳-展开-队形-声测联立解 C1~C5**，见文末 §X 变更记录；设计决策类 27 项归档 docs/GDD-02-拍板清单-v1.5.md）+ **拍板清单 v1.5 全 27 项 + 附表 5 项默认——v1.6 一律按各条目「推荐」选项拍板执行（执行存档：docs/GDD-02-拍板清单-v1.6.md；逐项落点见文末 §Y）** + **审查问题文档 v1.6（定稿终检三方对照：blocker 0 / gap 30 / ambiguity 17——v1.7 落实全部 30 条 gap：伪代码侧 12 条见文末 §Z，代码对齐 18 条随 sovs/sim 同批修复；GDD 侧 2 条欠账随 GDD-02 v1.8 同批执行；17 条 ambiguity 不阻断、留待拍板）**
> 本文把 §13 对照表逐项落成**可直接照写代码的伪代码**：数据结构逐字段（类型/单位/默认值）、系统函数逐函数（签名/步骤体/边界）。
> 语言中立；不出现任何具体语言代码。
>
> **槽位账目（v1.6）**：单位静态 30 + 单位运行时 17 + 元素静态 14 + 元素运行时 15 + 工程槽 1（garrison_in，条件分配）+ 条件槽 1（**redeploy_needed**，仅 GUN/可被拖 MECH 元素分配——联立解 C3 展开闸改元素粒度）= **78 槽**（v1.4=77，**+1 条件槽**；v1.5=78、**v1.6 维持 78——拍板清单 v1.5 执行零槽位变更**：㉑A 请求体扩为班元素列表不占槽、⑧A 喷火伤害系数走 damage 数值不新增武器子字段、㉒A 不加补弹速率槽）；武器 **27** 子字段（含 name）不变，**weapon_states 运行时子字段 +1**（**ammo_profiles_left**——M16 钨芯深拷贝计数落地，实例化时自模板深拷贝，select_profile 读/减该副本；v1.6 按清单⑪确认）。mounted_in 为全体 SQUAD 元素常驻槽（v1.3 起）。（v1.4=77、v1.3=77、v1.2=78、v1.1=82+27；明细见文末各版变更记录）
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

**moving 谓词成文（v1.5 M23/A19）**：moving(u) := u.move_path 非空——有航点即视为移动（含 MOB 趴窝/被拖等速度为 0 的 tick）；停靠 = 清空航点。§F3 effective_stealth_x10 / detection_range_cm 两读取点与 §F4 cmd_toggle_ambush、§F5 system_move 的 move_path==[] 静止判据由此同源（原谓词零定义零写点，豁免窗口与隐蔽减半跨平台不确定）。

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
| tow_speed_tier | 档 | 1 | 拖曳双方最低档 R-19（GDD-02:254——拖曳中牵引车+被拖车**均**按本档；§F5 :930 读 `ANY(x.towed IN {TOWING, TOWED})`，C1 枚举扩值后含牵引侧，走查修双态判）；v1.5（M25/A18）→ **v1.6【已拍板——清单附表 M25 确认，可推翻】：维持现状仅档位值**——档位锁 1 不改；"卡车快速转场"的优势由卡车**未拖曳时**的自身高速度档承载；若要"拖曳中牵引按自身速度档"或仅牵引/被拖元素各自降档（G07③ 元素粒度），推翻路径=改 D.0 常数与 moveSpeed 消费式并回写 R-19（拖曳转场价值重估） |
| crit_mob_minor_mult_bp | bp | 5000 | 机动轻伤速度乘成 |
| stealth_factor_bp[0..10] | bp[] | [15000,13500,12000,11000,10500,10000,9500,9000,8000,6500,5000] | 隐蔽→视野倍率查表 |
| forest_stealth_add | 0.1级×10 整型 | 20 | 林地隐蔽加值（v1.4：两常数统一"×10 整型存储"口径——原两处消费写法相反，照表配置必有一处错 10 倍） |
| garrison_stealth_add | 0.1级×10 整型 | 30 | 进驻建筑隐蔽【拍板默认】（同上口径统一） |
| detect_atten_per_m | cm/米 | 150 | 每米森林/烟遮断的视野 |
| infiltration_mult_bp | bp | 15000 | R-04 渗透期隐蔽乘成 |
| ambush_mult_bp | bp | 20000 | R-12 伏击隐蔽乘成 |
| reveal_mult_bp | bp | 4000 | 开火暴露后隐蔽乘成 |
| sensing_period_ticks | tick | 5 | 侦察扫描节流 |
| melee_range_cm | cm | 5000 | 近战阈值 50m（近战档案 max_range 上限，方案1） |
| ambush_acc_bonus_bp | bp | 13000 | R-12 脱伏击首击精度 |
| calib_acc_bonus_bp | bp | 12500 | R-01 侦察校准命中档 |
| calib_per_shot | **点/批**（v1.7·AMB-06 拍板：每批 fire_at 加一次，非按发——防高 salvo 卡两批满收束；推翻通道=回"AMB-06 改B"改按发 ×salvo） | 20 | 校射累积【拍板默认】 |
| calib_max_reduction_bp | bp | 6000 | 校射最大散布收束 |
| sup_penalty_bp | bp | 6000 | 压制满值精度惩罚 |
| sup_decay_per_tick | 点/tick | 1 | 压制自然衰减（近卫旗标 ×2，方案18） |
| crit_per_hp_bp | bp/HP | 1200 | 暴击概率系数〔**已废止 2026-10-07 D071 全拆**——暴击系统退役，常数已删（代码侧权威）；恢复随口子④路径〕 |
| front_arc / side_arc | 度 | 45 / 135 | 命中面扇区 |
| sniper_base_prob_bp | bp | 3000 | R-02 基础击杀概率 |
| sniper_cover_mult_bp | bp | 5000 | 反狙击掩护减半（第1轮） |
| sniper_tally_kills | 人 | 3 | 排内累计灭班线（R-02） |
| ammo_resupply_per_tick | 发/tick | 2 | 每武器补弹速率（保留清单#10：烟弹同轨原样）；v1.6【已拍板——清单㉒A，可推翻】：接受全局速率近似（2 发/tick 维持）——火箭炮 90 秒/轮量级由弹药车配比与再补给节奏承载，不加 per-weapon 速率/轮级冷却槽（R-14 数值表述回写 GDD 侧执行） |
| med_hp_per_unit | HP/份 | 1 | 医疗品=步兵回血（拍板①） |
| med_weight_per_unit | 重量/份 | 5 | D065 混装载重核算 |
| supply_round_weight | 重量/发 | 待定 | 弹药池通用每发重量（v1.5 M15——buy_supplies 重量式，替代"Σ武器均摊"未定义求和） |
| repair_radius_cm | cm | 3000 | D016 维修贴靠半径（v1.5 M24——原"贴靠"无量纲无结构判据） |
| building_collapse_dmg | HP | 0 | 楼塌驻军伤害（数值章节定） |
| vehicle_death_crew_permille | ‰ | 400 | R-07 车载被毁：班剩 40% 血（扣 60%） |
| mount_time_ticks | tick | 200 | R-07 上车 20s |
| smoke_radius_cm / smoke_ttl_ticks | cm/tick | 3000 / 600 | 烟幕实体参数 |
| spawn_interval_ticks | tick | 10 | 逐个间隔出牌 |
| phase_ticks | tick | 900 / 450 / 13200 | 盲部署90s / 禁火45s / 实战22min |
| category_quota[类别][池] | 排 | GDD-01 配额表 | validateDeck 用 |
| fire_support_subquota[桶] | 连 | 榴3 / 反坦克2 / 火箭1 | R-13 子配额 |
| sonar_locate_threshold / min_radius_cm / max_radius_cm | 点/cm | 待定 | R-03 定位曲线 |
| sonar_move_reset_cm | cm | = max 之半 | 声测换位阈值（v1.5 C4）：新开火位置距 track.pos 超此值 → accum 清零；默认 = sonar_max_radius_cm ÷ 2 |
| sonar_hold_ticks | tick | 100 | 声测增长窗口（v1.5 C4）：距最近开火超此 tick 数 accum 冻结（停火期圈冻结） |

（v1.5 M14/G22：原 r18_radius_cm 常数行**已删**——R-18 补给半径由模板字段 supply_radius_cm（D.1#20，**默认 8000**；空投箱模板硬要求 8000）单轨承载；原 D.0 常数全文零消费、照表配置无效，双轨消除。）

地形表 `TERRAIN`（Tiled 属性 → JSON）：`TERRAIN[tile].speed_bp[movementClass]`、`.stealth_add`、`.is_forest`、`.on_road`。
（v1.6 ㉓A 处置注记【按推荐拍板·可推翻】：`TERRAIN[tile].stealth_add` 定义后全文零消费——林地荫蔽确认为**通用规则**，由全局常数 forest_stealth_add 承载（**全体单位**林内 +2——v1.7·AMB-04 拍板：车辆进林同样生效（量级小，车辆 stealth 低），GDD ㉓A 注记随 v1.8 改写"全体单位通用"；GDD-02 §2.2 删猎兵卡面字段行——GDD 侧回写）；本字段保留作地图差异化荫蔽钩子（配置为 0 即全局口径）或径直删除，处置由数值章节定。）

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
| 15 | mode_set | Mode 位掩码 | DIRECT/INDIRECT/TOW/CARGO/TRANSPORT（无 AA）；v1.2 兼作交战分流与 fire_permitted 门、拖曳/载货门的静态位源（方案3/13）；**TOW 位数据硬要求（v1.4 全量；v1.7 终检 GAP-11 补全）**——被拖侧卡（中/重坦 R-19 维修拖曳、轻防空第11/12轮卡车牵引、**中防空 61-K/Flak 43（v1.7 补：第11/12轮并入卡车牵引体系——补-16"61-K 只拖单门"的可达性依赖，漏配则被拖地面禁射门对其整段跳过、变"边拖边打"旁路）**、火支全部牵引炮与火箭炮、步兵类四门迫击炮排[GDD-01 类别口径属步兵——v1.4 补全]）与**牵引侧卡**（坦克维修班/重型拖拉机排/豹式救援车、**苏④/德④卡车队（v1.7 补：mode_set 须含 TOW\|CARGO\|TRANSPORT 三位——D065 三模式互为可达；漏配 TOW 则模式 1 整链 REJECT 且绕过 cmd_tow 互斥门）**）mode_set 均须含 TOW 位；**重防空 52-K/Flak 36 显式拍板【v1.7 拍板默认·可推翻】=不配 TOW 位（不可拖）**——GDD 仅授权轻/中防空并入卡车牵引（第11/12轮），85mm/88mm 重防空超卡车吨位口径；推翻路径=52-K/Flak 36 补 TOW 位并重估 tow_tonnage/own_weight_tons 数据，漏配即"拖曳中禁射"失效且无运行时兜底；**v1.5（M26/A02）INDIRECT 位数据硬要求——v1.6【已拍板——清单⑯A/附表 M26 确认，可推翻】**：步兵类四门迫击炮排（82/81/120mm）mode_set 须含 INDIRECT 位并可领 FireMissionCmd——120 重迫"可校射收束"乃至全部曲射 HE 的可达性依赖此位（直瞄受 min_range 250m 限制），漏配即静默失效且无报错（与 TOW 位先例同格式） |
| 16 | close_combat_bonus_permille | ‰ | 骑兵 1800；冲锋枪排高档；仅 combat_style==MELEE 武器读取（方案1） |
| 17 | tow_tonnage / 18 own_weight_tons | 吨 | R-19 |
| 19 | repair_power_hp_per_tick | int | D016 |
| 20 | supply_radius_cm | int | R-18（0/8000） |
| 21 | acoustic_signature | int | 声测定位权重（火箭炮最高） |
| 22 | sonar_radius_cm / 23 sonar_rate | int | R-03（侦听侧名单化条件，方案4） |
| 24 | aura | {kind: MELEE\|PRECISION, bonus_bp, radius_cm} \| null | 政委/军官；军官=PRECISION 精度+10%（射程项按方案17拍板移除）；政委=MELEE 近战火力+15%——**v1.6【已拍板——清单⑬A，可推翻】：政委"冲刺速度+1档（持续型）"确认裁剪**（aura 无 SPEED kind、速度链不读光环、sprint_until 唯一写点为 SprintCmd，不补承载），突击光环收敛为纯近战加成；GDD-02 功能细则 :375 删该成分（GDD 回写员执行，与爆破作业速度+50% 同批） |
| 25 | flags | 位段 | canSprint canGarrison canAmbush canInfiltrate noMoveVisionPenalty forestWalkSilent requiresMark singleSquadCard hasCargo hasMount hasSupply（方案12，由 seats/cargo 派生） suppDecayX2（方案18 近卫意志近似） **canSniperCover canAirdropBeacon（v1.4：特技资格位——掩护/信标指令校验，原任意单位可下达）**；**canAmbush 置位数据硬要求（v1.6 ⑮A 成文【按推荐拍板·可推翻】，同 TOW 位先例格式）**：置位 = 苏⑤ SU-85 / 德④ 三突G / 德⑤ 四号歼击车 / 德⑥ 追猎者（三遍审查共识伏击组，承载已核实成立）；**SU-76 / 苏⑥ ISU-152 / 德⑦ 犀牛不置位**——ISU-152 放弃伏击×2 隐蔽 + 首击 +130%（ambush_mult_bp=20000/ambush_acc_bonus_bp=13000）、犀牛放弃 1400m 伏击首击，两卡卡面按"无伏击"定价；后续翻案改置位须重估分数与反伏击手段（数值章节） |
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
| 4-5 | armor_ke{F,S,R,T} / armor_he{F,S,R,T} | 0-20 相对刻度；T 仅空袭读取；0=无甲合法；**mm→0-20 全表换算锚（v1.6 ⑤A 成文【按推荐拍板·可推翻】）**：0-20 刻度 ≈ 0-400mm RHA（90mm→约 4~5）——全部卡面 mm 值（装甲与穿深，含 D.3#4/5）按此规则折算入槽，一张卡一套刻度（美洲狮 50mm 炮穿深≈90 折约 4~5，与同卡装甲 6/3/2 同刻度；换算细则由数值章节定表） |
| 6 | fire_arc_deg | 360 或 ±15°（R-09）；==360 的模板不分配 rotating 槽（方案6） |
| 7 | suppression_vuln_permille | 敞篷 >1000 |
| 8 | squad_quality_bp | 老兵班 11500 |
| 9 | weapons[] | WeaponTemplate 列表 |
| 10 | mounted_armament | 空车可射击武器（251 车载 MG，第5轮）。**v1.7（AMB-07 拍板）数据硬要求：车载 MG 须同时配入元素 weapons[] 并以 mounted_armament 标记**——weapon_states 仅由 weapons[]（#9）派生，只配本字段不配 #9 则"空车可射击"静默失效（与 TOW 位漏配同型风险）；消费谓词见 §F4 :673 |
| 11 | seats | 运兵座位（卡车1班；0=不可载） |
| 12 | cargo_rounds_max / 13 cargo_medical_max | 每车 600 发 / 120 份（D065） |
| 14 | cargo_weight_max | 总载重（混装核算） |

（v1.1 的 #7 turret_traverse_deg_per_tick 已删——全文无消费点，方案15；"无炮塔"语义由 fire_arc_deg<360 + turn_rate_deg_per_tick 承载。）

（v1.5 M22/A22：**GUN 元素定义成文**——unit_type 按配卡归 INFANTRY（牵引炮/迫击炮之炮班：hp_max=炮班人数，1HP=1人——R-02 狙击减员、R-18 医疗回血、squad_hp_factor 火力衰减三处消费顺通）或 MECH（自行炮架：hp_max=炮架血）；全部牵引炮/迫击炮卡按 INFANTRY+炮班人数配置。）

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
| 11 | accuracy_base_bp | 基础命中 bp（近战档案=10000 **基础必中、受压制衰减**——v1.6 ⑭A 改表述不改公式，方案1） |
| 12 | aim_time_ticks / 13 reload_time_ticks | 近战档案 aim≈0；狙击档案超长 aim+极低射速（方案1） |
| 14 | salvo | 连发数（机枪点射>1） |
| 15 | ammo_base / 16 ammo_weight | 基数（烟弹=SMOKE 武器档案，同轨）；每发补给重量 |
| 17 | projectile_speed_cm_per_tick | — |
| 18 | trajectory | DIRECT/BALLISTIC |
| 19 | suppression_power | 压制值/发 |
| 20 | crit_mod_permille | RPG/集束 >1000 |
| 21 | vs_fort_mult_permille | 工兵 2000 / ISU-HE 1500 / OT-34 2000；**v1.5（M5/G19）数据硬要求**：le.IG 18（拆机枪巢/清建筑）与 ML-20（直射对建筑毁伤可观）须配 vs_fort>1000——照表默认 1000 则 cmd_attack 攻坚资格门对两卡恒 REJECT、直射拆楼不可达（与 D.1#15 TOW 位先例同格式）；OT-34"高重伤率"承载——**v1.6【已拍板——清单⑧A+⑱A，可推翻】：改锚为直接伤害系数**，喷火武器（工兵喷火器两卡 + OT-34 主武器，共三处）对 INFANTRY 目标伤害 ×1.5 **由高 damage 数值承载**（不新增 vs_infantry_mult 槽、保 27 子字段冻结账目——⑧A 双路径取数据表达侧；对 MECH 目标同值伤害由数值章节复核），"烧得快"即"高伤亡率"；GDD 卡面"高重伤率"表述回写（GDD 侧） |
| 22 | ammo_profiles[] | 受限弹药档案数组：{count_left, pen_bonus}（钨芯=3发/穿+3），**余量存档内计数**（方案11，替代 special_ammo + special_ammo_left）；烟弹仍为独立 SMOKE 档不并入。**v1.4【拍板默认】→ v1.5（M16）落地 → v1.6 按清单⑪确认【已拍板，可推翻】**：深拷贝计数落于 weapon_states 子字段 **ammo_profiles_left**（§D.5#11，冻结账目注明武器运行时子字段 +1），select_profile 读/减该实例副本、不再写模板（原 v1.4 注释宣称深拷贝而代码仍递减共享模板——G15 判"纸面闭合"；推翻路径=改共享计数"全连 3 发"更稀缺）；**钨芯换算锚（v1.6 ㉖A 成文【按推荐拍板·可推翻】）**：钨芯最终穿深=7；pen_bonus=7−基准 pen_max（PaK38 基准 pen_max=4，即 +3）——数据字典成文同式，与⑤全表换算规则衔接 |
| 23 | alt_profile | R-11 HE 档案 {damage, blast} \| null（AP 主炮共槽） |
| 24 | needs_deployed | R-05 |
| 25 | self_defense | R-15 {max_range_cm, accuracy_mult_bp} \| null（indirect_role 读取前判空，方案3）；**v1.6 ㉔A 数据要求【按推荐拍板·可推翻】**：82/81 轻迫击炮排主武器配 self_defense 自卫档（冲锋枪班自卫档，与 R-15 同族）——120 重迫既有自卫，轻迫同配使摸炮位克制链连续（原疑点⑩自 v1.2 在册闭合；推翻路径=卡面注明脆皮定位"轻迫无自卫"） |
| 26 | combat_style | NORMAL/MELEE/SNIPER 条件位（方案1，替代 melee_flag/sniper_flag 路由旗标）：MELEE→伤害读 close_combat_bonus_permille 与 MELEE 光环、绕过装甲曲线；SNIPER→弹丸命中后进 R-02 结算分支；两者均不再参与 ground_direct/finish_aim 路由 |
| 27 | reveal_time_ticks | 开火暴露时长（联动声测） |

**档案配置示例（方案1）**：近战=骑枪/刺刀档案 {min_range:0, max_range:5000, aim_time:0, accuracy_base_bp:10000, combat_style:MELEE}；狙击={max_range:400, aim_time 超长, reload_time 极长, combat_style:SNIPER}。（v1.6【已拍板——清单⑭A，可推翻】：近战"必中"表述改写为**"基础必中、受压制衰减"**、公式链零改动——accuracy_base_bp=10000 为基础值，精度乘区仍乘 aim_factor 压制惩罚（sup_penalty_bp=6000，满压制 ×4000），满压制近战可脱靶并生成近失弹（保住"压制克制近战冲锋"方向）；冲锋枪排/骑兵排两卡面与机制版成文回写（GDD 侧）；推翻路径=对 MELEE 档案短路精度乘区（近战免疫压制，机枪/近战卡定价全面重估））

### D.4 UnitInstance（单位运行时 17）

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
| 13 | infiltration_timer | R-04（600 tick）；仅 canInfiltrate 卡分配并参与衰减（方案8）；**v1.6 ④A【按推荐拍板·可推翻】：置位点改 update_phase 迁入实战时统一置 600**（§F8；spawn_step 仅在相位已为实战时补置——盲部署/禁火期 spawn 置 0，60 秒完整落进实战；原 spawn 即置 600 使窗口被禁火期吃掉，"敌后接应"不可达） |
| 14 | ambush_active / 15 ambush_shot_bonus | R-12 |
| 16 | sprint_until | 疾跑到期 tick 时间戳（方案14；机制版挂元素级主元素——§D.8） |
| 17 | r02_kill_tally / alive | 狙击计数 / 存活 |

（v1.1 的 calib_target/calib_progress 下沉 FireMission、sniper_cover_target/airdrop_beacon 迁 world 旁表，方案9/10；方案10 的"最近任务收束缓存"变体**未采纳**——机制版 v1.2 同款拍板，直射仅在活跃任务期读 fm.calib_progress，任务结束无收束。v1.3：单位级 tow_pair 槽删除——拖曳改元素级 TowPair{tower_elements, towed_element}，见 §F2 start_tow 与变更记录#12，**标题计数 18→17 随之修正（v1.4 底本漏改，v1.5 走查修——与头部账目行/§X 四的 30+17+14+15+1+1=78 一致）**；"拖曳中"判定 = ANY(e.towed IN {TOWING, TOWED})——v1.5（C1）枚举扩 TOWING 后按双态判。）

### D.5 ElementInstance（元素运行时 15 + 1 工程槽 + 1 条件槽[redeploy_needed，v1.5 C3——总账 77→78]；表内序号至 17，系含 unit/template 两个引用槽）

| # | 字段 | 说明 |
|---|---|---|
| 1 | element_id / 2 unit / 3 template | — |
| 4 | pos / 5 facing(度) | 各自占位与车体朝向 |
| 6 | hp_current | 血条即兵力（SQUAD：1HP=1人） |
| 7 | crit{FC,SEN,RLD,MOB} | NONE/MINOR/MAJOR；〔条件槽：仅 unit_type==MECH 元素分配，其余恒 NULL，方案7〕修饰器读槽前判空 |
| 8 | suppression | 0..100 |
| 9 | reveal_timer | 开火暴露残留 |
| 10 | mounted_in | 载具元素引用（R-07 同卡 / D065 跨卡）；v1.3 起为**全体 SQUAD 元素常驻槽**（原 hasMount 条件槽使无座位步兵卡派生不出槽、跨卡运兵无确定承载——审查#8）；非 SQUAD 元素恒 NULL |
| 11 | weapon_states[] | {template, state, timer, target, ammo_left, **ammo_profiles_left**, use_self_defense}；state∈READY/AIMING/RELOADING/EMPTY（方案19 显式 EMPTY 迁移；special_ammo_left 已删，方案11）；ammo_profiles_left=受限弹药档实例计数（**v1.5 M16**：实例化时深拷贝 template.ammo_profiles，每门独立——select_profile 读/减此字段，不再写模板；冻结账目注明武器运行时子字段 +1） |
| 12 | rotating | 转向中→受弹按侧面（R-09）；〔条件槽：仅 fire_arc_deg<360 模板分配，方案6〕 |
| 13 | towed | NONE/**TOWING**/TOWED（**v1.5 C1**：TOWING=牵引中 / TOWED=被拖中——start_tow 分别置位、stop_tow 双方回 NONE；禁射门读 e.towed IN {TOWING, TOWED}。原牵引/被拖同置 TOWED，队形闸把牵引元素一并排除而其坐标再无写点——牵引元素坐标冻结（B03）的根因） |
| 14 | mode | DIRECT/INDIRECT/TOW/CARGO/TRANSPORT（卡车每辆独立，D065） |
| 15 | cargo_units[] | 跨卡载运的班 UnitInstance（D065 运兵）；〔条件槽：仅 hasCargo 元素分配，方案12〕 |
| 16 | supply_rounds / 17 supply_medical | 本车在途物资（CARGO）；〔条件槽：仅 hasSupply 元素分配，方案12〕 |
| 工1 | garrison_in | 驻楼 Building 引用（§7 驻建筑）；〔条件槽：仅 flags.canGarrison 步兵卡分配，方案5〕 |
| 工2 | （上车进度不占字段） | world.mount_requests: [{squad_unit, carrier, ticks_left}]（惰性建表，方案12） |
| 工3 | redeploy_needed | 被拖后须重新展开旗（**v1.5 C3**：展开闸元素粒度）；〔条件槽：仅 GUN/可被拖 MECH 元素分配，默认 FALSE〕start_tow 对被拖元素置 TRUE；cmd_deploy 清全单位**非拖曳中（towed != TOWED）元素**——**v1.6 终审修复 1b【按终审指令落地·可推翻】：被拖元素保持 TRUE**（展开范围限于非 TOWED 元素，"禁止边拖边展开"由该旗承载而非单位级 ANY 门，留守门可展开）；stop_tow 不清（解挂后须重新展开）——**槽位账目 77→78（+1 条件槽）** |

### D.6 世界实体与寄存器

```
Projectile   {shooter:Element, weapon:WT, damage_type, damage, blast_cm, pen_bonus,
              pos, dest, speed_cm_tick, trajectory, hit_target: Element|AircraftRef|Building|None,
              will_hit: BOOL}                        // v1.3：Building 入列——工兵/ISU 直射拆楼（审查#5）
SmokeZone    {pos, radius_cm, ttl_ticks}
IntelCircle  {team, **source_unit**, center, radius_cm}   // R-03 冻结精度，不撤销；v1.5（C4）：增键字段 source_unit——
                                                            // 按 (team, source_unit) upsert：同炮更新其圈、多炮多圈共存（fire_at 按圈取 MAX 的消费前提成立）
                                                            // 圈粒度=开火单位（连级）而非单炮，R-03 按连解释（登记于 §X 变更记录）
SoundTrack   {**listening_team**, unit, pos, accum, **last_fire_tick**}
                                                            // v1.5（C4）：每 (侦听队, 开火单位) 一条；last_fire_tick=最近开火 tick
                                                            // （sonar_hold_ticks 增长窗口判据）；定义体 upsert_sound_track 见 §F3
Building     {id, pos, hp, garrison_slots, garrisoned[Element]}
AircraftRef  {id, team, pos, alt_tier, hp_current, hp_max, armor_aa, spotted_mask}   // §12 航空契约
Objective    {id, pos, radius_cm, owner}
TowPair      {tower_elements[Element], towed_element:Element}   // v1.3：元素级（审查#12）——单卡2车并拖/拖单门炮可表达
FireMission  {form: POINT|LINE|CREEP, target_point, target_line[a,b], creep_speed_cm_tick,
              ammo_mult(1..3), salvo_mode: FULL|HALF, shots_left, shots_fired, started_tick,
              calib_target, calib_progress}               // 方案10：校射两槽下沉任务体（连内共享=同任务参与者共享同一 fm）；
                                                            // 任务体销毁（耗尽/取消/拖曳/切模清任务）进度随之失效——直射仅在活跃任务期读收束（机制版同款）
                                                            // v1.4：shots_fired——LINE 取样序号承载（原"k=已发射数"无存储来源，参与炮数随毁伤不可回推）
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
MountCmd{squad_elements[], carrier_unit}（**v1.6 ㉑A【按推荐拍板·可推翻】：请求体扩为班元素列表**——逐班选最少挂载载具并逐班占座，去重按班元素）  DismountCmd{squad_unit}
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
| 5 | 近战对 MECH 曲线 | **绕过装甲曲线**（§D.3#26、§F1 :332、§C#1 三处成文） | ~~applyDamage(e, dmg, 近战档案(走HE曲线))~~ **v1.7（AMB-05 拍板）改齐 IMPL：绕过曲线** | 贴脸格斗打弱点全额（骑兵×1.8 对 SOFT 本就无甲可穿）；与 GDD"步兵无四面装甲差异"口径相容；燃烧瓶反甲由 damage 数值承载（数值章节标定）。推翻通道=回"AMB-05 改B"恢复 HE 曲线 |
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
        // 〔勘误 2026-10-07 D071 全拆〕上行两调用已随暴击退役拆除（代码侧权威——resolve_hit 现无暴击链）
    inject_suppression_area(world, tgt.pos, p.weapon.blast_radius_cm,
                            p.weapon.suppression_power)   // 目标+溅射圈内近旁

FUNCTION resolve_sniper_hit(world, p, tgt_elem)           // 方案1：原 fire_sniper 结算体原样搬入（R-02）
    tgt_unit = tgt_elem.unit
    covered = cover_by_target 含 tgt_unit 键               // 方案9：掩护改查旁表
    prob = sniper_base_prob_bp * (covered ? sniper_cover_mult_bp : 10000) // 10000
                                                             // v1.5（M2/G12）：整除外置——原置于三元分支内部：
                                                             // covered 分支 5000//10000=0（掩护=免疫）、未掩护乘 10000（无掩护=必中）
    rng = world.rng[SNIPER]
    squads = [班元素 OF tgt_unit] 或 全部元素
    // v1.6【已拍板——清单⑲A（A08），可推翻】：狙击武器排除 MECH 目标——select_target 候选剔除 MECH 元素
    //   + cmd_attack 指火门同谓词（§F4 双承载）；"全部元素"回退仅对无班元素的 INFANTRY 单位（如牵引炮班）可达，
    //   原"对无班元素车辆直扣 1~2 HP（绕过装甲曲线，tally≥3 整车击毁侦察车/卡车）"路径关闭；
    //   GDD R-02 回写"狙击目标均为人员"（GDD 侧）。推翻路径=改仅压制（B）或灭班=毁一辆（C）
    IF tgt_unit.template.flags.singleSquadCard:           // 指挥班组/声测班：概率灭排
        IF rng.chance_bp(prob): apply_damage(world, squads[0], squads[0].hp_current)
        RETURN
    kills = rng.chance_bp(prob) + rng.chance_bp(prob)     // 1~2 人（先命中[fire_direct 的 HIT 掷]再判定——方案1 已接受的方差变化）
    IF kills > 0:
        actual = MIN(kills, squads[0].hp_current)          // v1.4：tally 记实际击杀（原记掷骰值——残班吃 2 记 2 实死 1，提前灭班）
        apply_damage(world, squads[0], actual)             // 走统一伤害入口——B9
        tgt_unit.r02_kill_tally += actual
    IF tgt_unit.r02_kill_tally >= sniper_tally_kills:     // ≥3人=损失1班
        lowest = MIN(存活元素, by hp_current)
        apply_damage(world, lowest, lowest.hp_current)
        tgt_unit.r02_kill_tally −= sniper_tally_kills

FUNCTION resolve_melee_hit(world, p, tgt_elem)            // 方案1：原 fire_melee 结算体原样搬入
    bonus = p.shooter.unit.template.close_combat_bonus_permille              // 骑兵1800
    bonus = bonus * aura_bonus_bp(p.shooter.unit.team, MELEE, tgt_elem.pos) // 10000  // 政委突击光环"跟我上"（v1.7 GAP-13 改锚：督战成分随士气体系拍板①裁剪，
                                                             // GDD :387 改锚由 GDD 回写员同步——消费点随方案1挪入直射伤害链——光环会同时放大近距射击，负面影响已接受）
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

〔**勘误 2026-10-07 D071 全拆**：以上两函数已整体退役（代码侧权威——combat.py 已无
roll_crit/upgrade_crit 定义；MOB 先于三槽于 2026-10-06 below(3) 收窄、FC/SEN/RLD 于
2026-10-07 全拆；恢复路径=拍板清单 D071 口子④四步一步可回〕

FUNCTION inject_suppression(element, amount)
    element.suppression = MIN(100, element.suppression
                              + amount * element.template.suppression_vuln_permille // 1000)

FUNCTION inject_suppression_area(world, center, radius_cm, power)
    // v1.7（AMB-01 拍板·可推翻）：falloff_bp 定义式成文——衰减跨度 = 2×弹半径（随弹径插值）：
    //   falloff_bp(d) = 10000 − MIN(8000, d × 8000 ÷ (2 × radius_cm))，底线 2000bp。
    //   大口径弹压制圈大且衰减缓（152mm 跨 60m）、小口径集中（81mm 迫 15m 到底线），与 blast_radius 联动；
    //   推翻通道=回"AMB-01 改B"改回固定区间（0~160m 线性到底、与弹径无关——v1.6 代码自选式）。
    FOR e IN all_alive_elements(world) WHERE dist_cm(e.pos, center) <= MAX(radius_cm, 2000):
        inject_suppression(e, power * falloff_bp(dist, radius_cm) // 10000)

FUNCTION resolve_blast(world, p:Projectile)               // 曲射落点 / 烟弹 / 近失
    IF p.damage_type == SMOKE:
        world.smoke_zones.append(SmokeZone(p.dest, cfg.smoke_radius_cm, cfg.smoke_ttl_ticks))
        RETURN                                            // B4：spawnSmokeZone 定义体在此
    FOR e IN alive_elements_within(world, p.dest, p.weapon.blast_radius_cm):
        dmg = p.damage * falloff_bp(dist, p.weapon.blast_radius_cm) // 10000 * squad_hp_factor_bp(p.shooter) // 10000
                                                             // v1.7（AMB-01）：溅射伤害同衰减式（跨度=2×弹半径，见 inject_suppression_area 定义）
        apply_damage(world, e, dmg)
        IF e alive AND MECH: roll_crit → upgrade          // 〔勘误 2026-10-07 D071〕暴击链已拆
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
        dmg = (s.hp_current * (1000 − cfg.vehicle_death_crew_permille) + 999) // 1000
                                                             // v1.5（M14/G22）：改读 D.0 常数（向上取整）——原硬编码 60% 接线脱钩，
                                                             // 违反 §D.0 头注"禁止写死数值"纪律；permille=400 时即原 (hp*600+999)//1000
        apply_damage(world, s, dmg)                         // 每元素仅一次，"剩 1000−permille‰ 血"承诺恢复
    IF elem 有 hasSupply 槽: elem.supply_rounds = 0; elem.supply_medical = 0
    // 驻楼引用清理（garrison_in 为条件槽——方案5）
    IF elem.garrison_in != NULL: elem.garrison_in.garrisoned.remove(elem); elem.garrison_in = None
    // 拖曳连带
    release_tow_if_involved(world, elem)                   // v1.7（GAP-24）：改传元素（原传 unit——多对拖曳连带解除）
    // v1.4（I-19）：撤销涉及本元素的进行中装载请求（原 20 秒窗口内车毁仍对死元素挂载）
    // v1.5（M12/G26）：撤销谓词收窄——仅撤"本元素为载具"或"申请班已全灭"的请求
    //   （原 r.squad_unit != unit 把申请班与被毁元素同单位的在途请求一并误杀：班 A 申请上 251#2，同排 251#1 被毁 → 请求被误杀）
    // v1.6（㉑A）：谓词随元素粒度——"申请班已全灭"改判申请班元素不在编（元素除名即从 unit.elements 移除）
    IF world.mount_requests != NULL:
        world.mount_requests = [r FOR r IN world.mount_requests
                                IF r.carrier != elem AND r.squad_element IN r.squad_element.unit.elements]
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
    IF towed_element.towed != NONE OR tower_elements == []: RETURN FALSE
                                                             // v1.5（C1）：非 NONE（TOWING/TOWED）即已在拖——原仅判 TOWED
    IF ANY(t.unit.team != towed_element.unit.team FOR t IN tower_elements): RETURN FALSE
                                                             // v1.7（GAP-10）：函数级同队硬门——cmd_tow 命令门之外的兜底
                                                             //（start_tow 亦被未来脚本/AI 路径调用，门不得只设命令层）
    sorted = tower_elements 按模板 tow_tonnage 降序（稳定排序，并列取原序）   // 杜绝"30t车被指派45t任务"（原按命令序切片）
    acc = 0; chosen = []
    FOR t IN sorted:
        chosen.append(t); acc += t.template.tow_tonnage
        IF acc >= towed_element.template.own_weight_tons: BREAK
    IF acc < towed_element.template.own_weight_tons: RETURN FALSE   // 吨位不足（重坦45t=2×30t 并拖或 1×45t——单卡2车并拖可表达）
    pair = TowPair(tower_elements=chosen, towed_element=towed_element)
    world.tow_pairs.append(pair)
    FOR t IN chosen: t.towed = TOWING                       // v1.5（C1）：牵引元素置 TOWING（原与被拖同置 TOWED——
                                                             // 牵引元素被队形闸 e.towed==NONE 一并排除、坐标再无写点，拖曳转场不发生，B03 根因）
    towed_element.towed = TOWED                            // 被拖元素（如单门炮——不再整卡同拖）
    towed_element.redeploy_needed = TRUE                   // v1.5（C3）：元素级重展开旗——解挂后须 cmd_deploy 重新展开才可开火
                                                             // 〔条件槽：仅 GUN/可被拖 MECH 元素分配，合法被拖对象按分配规则必有此槽〕
    // v1.5（C5）：v1.4 的单位级重置行为删除——start_tow 不再写 unit.deploy_state / deploy_timer
    //   （原"拖走一门炮整连带收炮"：留守已展开炮被强制 MOBILE、needs_deployed 门即时禁射，须整连重走 30 秒——G04/G09）
    IF towed_element.unit.fire_mission != NULL: towed_element.unit.fire_mission = None   // 拖曳取消炮击任务（方案10）
    RETURN TRUE

FUNCTION stop_tow(world, pair, reason ∈ {VOLUNTARY, REPAIRED, DESTROYED})
    FOR t IN pair.tower_elements: t.towed = NONE           // v1.5（C1）：TOWING 回 NONE
    pair.towed_element.towed = NONE
    world.tow_pairs.remove(pair)                          // 〔勘误 2026-10-07 D071〕原注「MOB 暴击保留」已随暴击退役成死语——删；被拖者维修清 crit 链已不存在
    // v1.5（C3）：不清 towed_element.redeploy_needed——解挂后须重新展开（由 cmd_deploy 清除）；unit.pos 已在拖曳随动中同步（§F5），解挂无回跳

FUNCTION release_tow_if_involved(world, element)             // v1.7（GAP-24）：参数改元素级——一单位多对拖曳各自解除
    FOR pair IN [p FOR p IN world.tow_pairs
                 IF element ∈ p.tower_elements OR element == p.towed_element]:
        stop_tow(world, pair, DESTROYED)
                                                             // 原 unit 级签名按"涉及本单位任一元素"整批解除：卡车队 3 辆各拖 1 门时，
                                                             // 任 1 辆切出 TOW/被毁连带另 2 对健康拖曳 stop_tow（炮掉挂中途、
                                                             // redeploy_needed 保持 TRUE 须重挂+重展开）。与 v1.3#12 元素级拍板、
                                                             // 机制版 :617（pair 级）同构；三处调用点随之改传元素

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
        s += garrison_stealth_add                           // v1.4：×10 整型口径统一（存储=30，消费不再乘 10）
    IF world.in_forest(unit.pos):  s += forest_stealth_add  // 同上（存储=20）
    RETURN CLAMP(s, 0, 100)

FUNCTION detection_range_cm(world, obs, tgt) → cm
    r = obs.template.optics_ground_cm * optics_factor_bp(obs 主元素) // 10000
                                                             // v1.7（GAP-22）：SEN 暴击消费点——方案7 读链落地（观察窗碎裂视野×0.6/×0.3；
                                                             // 非 MECH 判空返回 10000——原定义后零消费，MECH crit 掷骰 25% 空转）
    IF obs.moving AND NOT flags.noMoveVisionPenalty: r = r // 2   // 侦察车轮式豁免（第1轮）
    IF obs.ambush_active: r = r // 2                              // 伏击视野减半（R-12，g-修复）
    r = r * stealth_factor_bp[CLAMP(effective_stealth_x10(tgt) // 10, 0, 10)] // 10000
    r −= detect_atten_per_m * (world.los_forest_m(obs.pos, tgt.pos)
                             + world.los_smoke_m(obs.pos, tgt.pos))   // 穿林/穿烟逐米衰减
    RETURN MAX(0, r)

FUNCTION keep_range_cm(world, obs, tgt) → cm               // 保持跟踪：无衰减距离（更难甩）
    RETURN obs.template.optics_ground_cm * optics_factor_bp(obs 主元素) // 10000   // v1.7（GAP-22）：SEN 暴击消费点（同上）
         * stealth_factor_bp[CLAMP(tgt.template.stealth_base, 0, 10)] // 10000

FUNCTION point_in_friendly_vision(world, team, pt) → BOOL  // v1.3（审查#13）：定义体补齐——校射视线判定
    // R-06"遮断校射"承载：穿林/穿烟衰减计入（烟墙后的目标点不收束）；点目标按隐蔽中位档(5)近似
    FOR obs IN 该队 alive_units:
        r = obs.template.optics_ground_cm * optics_factor_bp(obs 主元素) // 10000 * stealth_factor_bp[5] // 10000
                                                             // v1.7（GAP-22）：SEN 暴击消费点（同上）
        r −= detect_atten_per_m * (world.los_forest_m(obs.pos, pt) + world.los_smoke_m(obs.pos, pt))
        IF dist_cm(obs.pos, pt) <= MAX(0, r): RETURN TRUE
    RETURN FALSE

FUNCTION system_sensing(world)                              // 每 sensing_period_ticks 一次
    FOR tgt IN alive_units: tgt.本轮接触等级 = NONE          // v1.4：mark_level 改重算式（原棘轮式只升不降——照过一次永久校准，犀牛门/R-01 失真）
    FOR obs IN alive_units, FOR tgt IN 敌方 alive_units:
        d = dist_cm(obs.pos, tgt.pos)
        IF d <= detection_range_cm(obs, tgt):
            tgt.spotted_mask |= 1 << obs.team
            IF obs.template.category == 侦察: tgt.本轮接触等级 = MAX(本轮接触等级, CALIBRATED)   // R-01
            ELSE:                            tgt.本轮接触等级 = MAX(本轮接触等级, SPOTTED)
        ELIF d > keep_range_cm(obs, tgt):
            IF NOT ANY(同队其他观察者仍保持): tgt.spotted_mask &= ~(1 << obs.team)
    FOR tgt IN alive_units: tgt.mark_level = tgt.本轮接触等级   // 本轮无接触 → NONE（侦察撤离/目标脱视野后加成与犀牛门同步回落）
    sense_air(world)                                       // R-17/R-23（AA 分支名单化，方案2）
    sonar_listeners = [u FOR u IN alive_units
                       WHERE u.template.sonar_radius_cm > 0 AND u.deploy_state == DEPLOYED
                         AND ALL(e.mounted_in == NULL FOR e IN u.elements)]
                                                             // v1.7（GAP-23）：补 mounted_in 判据——声测班上车（D065 运兵模式）后
                                                             // 停止新增定位/收窄（R-03"静止待命侦听"）；已显示圈按 R-03 不受影响；
                                                             // 原 deploy_state 写点不进挂载链，行驶中的机动声测站持续收窄圈的旁路闭合
    IF sonar_listeners != []: sonar_step(world, sonar_listeners)   // 方案4：名单空→整段跳过，IntelCircle 不再生成（盲射圈随之不再新增——负面影响已接受）
    // fire_at / cmd_smoke（BALLISTIC 曲射侧）的 upsert_sound_track 写侧保留（保留清单#3 修订）；
    // v1.7（AMB-14/17② 拍板·可推翻）：声测喂入=**仅曲射（trajectory==BALLISTIC）**——fire_direct 直射链
    //   写点删除（坦克/AT 炮/机枪定位走视野链+直射 reveal_timer，R-03"全游戏唯一定位敌炮手段"按
    //   1.1⑤ 口径收窄为曲射炮兵/火箭炮；步兵烟罐 trajectory=DIRECT 不喂声测——"拉烟掩护撤离"无巨响）；
    //   acoustic_signature 保留为曲射声源强度参数（火箭炮最高）。推翻通道=回"AMB-14 改B"恢复直射喂入。

FUNCTION sense_air(world)                                   // R-17；方案2：探测分支名单化
    FOR a IN world.aircraft:
        FOR g IN 敌方 alive_units WHERE g IN world.aa_roster:          // 防空体系探测——仅名单（方案2）
            IF a.alt_tier <= g.air_ceiling AND dist <= g.optics_air_cm * optics_factor_bp(g) // 10000:
                                                             // v1.7（GAP-22）：SEN 暴击消费点（方案7 读链，同 detection_range_cm）
                a.spotted_mask |= 1 << g.team
        FOR g IN 敌方 alive_units:                                      // 低空目视分支保留不动（方案2）
            IF a.alt_tier == LOW AND dist <= g.optics_ground_cm:
                a.spotted_mask |= 1 << g.team
        FOR team IN a.spotted_mask 各置位队:                            // v1.5（M17/A23）：对偶清位——与地面 keep_range 同构
            IF NOT ANY(g IN 该队 alive_units WHERE                       // 超出该队全部探测者（防空名单支 + 低空目视支）范围
                       (g IN world.aa_roster AND a.alt_tier <= g.air_ceiling            // 即清 spotted_mask 对应位——原仅 |= 无清位，
                        AND dist_cm(g.pos, a.pos) <= g.optics_air_cm)                   // 敌机进过一次探测半径即永久"已发现"，
               OR (a.alt_tier == LOW AND dist_cm(g.pos, a.pos) <= g.optics_ground_cm)): // "超半径不开火"被射程≤探测半径变相架空
                a.spotted_mask &= ~(1 << team)

FUNCTION sonar_step(world, listeners_pool)                  // R-03：开火越久定位越准（读侧名单化，方案4）
    FOR track IN world.sound_tracks:                        // SoundTrack 于 fire() 时 upsert（定义体见下——v1.5 C4 补齐）
        listeners = [u FOR u IN listeners_pool
                     WHERE u.team == track.listening_team    // v1.5（C4）：键改 (侦听队, 开火单位)（原 u.team != track.unit.team——两队制等价，多队下每队各一条）
                       AND dist_cm(u.pos, track.pos) <= u.template.sonar_radius_cm]
        IF listeners == []: CONTINUE                        // 声测班移动/阵亡→圈冻结不撤销
        IF world.tick − track.last_fire_tick > cfg.sonar_hold_ticks: CONTINUE
                                                             // v1.5（C4）：停火期 accum 不增长（圈冻结在最后精度）——
                                                             // 原无条件累加：开过一炮永久留迹，"开火越久越准"漂移为"侦听越久越准（含停火期）"
        track.accum += MAX(s.template.sonar_rate FOR s IN listeners) * track.unit.template.acoustic_signature
                                                             // v1.5 终审修（中）：sonar_rate 是声测班 UnitTemplate 字段（D.1#22/23），
                                                             // 原 MAX(sonar_rate) 无作用域裸引用按字面不可求值——改对本次有效侦听者
                                                             // 取最大速率（与机制版 §3.D 同构；M1 裸引用族漏网，M28 未收录条目）
        IF track.accum >= cfg.sonar_locate_threshold:
            radius = LERP(sonar_max_radius_cm, sonar_min_radius_cm,
                          MIN(1, (accum−threshold) ÷ threshold))     // 圈随时长收窄
            c = world.intel_circles 按 (listeners[0].team, track.unit) 键 查找或新建
                                                             // v1.5（C4）：upsert 键 (team, source_unit)——同炮更新其圈、多炮多圈共存
                                                             // （原结构无键字段：按 team 覆盖则同队多敌炮圈互覆；按追加则旧大圈与新圈共存、
                                                             //  fire_at 取 MAX 恒得历史最大半径——收窄消费链失效）
            c.center = track.pos; c.radius_cm = radius      // v1.3（审查#2）：圈记侦听方队（保持——原记到被侦听敌方名下，消费链匹配不上）

FUNCTION upsert_sound_track(world, firing_unit, new_pos)    // v1.5（C4）：函数体补齐——原全文仅两处调用点、无定义（B02/G05/G16）
    // 写侧调用点：fire_direct / fire_at / cmd_smoke（v1.5 M7 并入）——保留清单#3 写侧语义原样
    FOR t IN 各队 WHERE t != firing_unit.team:              // 每 (侦听队, 开火单位) 一条（两队制即敌方一条）
        track = world.sound_tracks 按 (t, firing_unit) 键 查找或新建
                  {listening_team: t, unit: firing_unit, pos: new_pos, accum: 0, last_fire_tick: world.tick}
        IF dist_cm(new_pos, track.pos) > cfg.sonar_move_reset_cm:
            track.accum = 0                                 // 换阵地重定位（C4 语义②，阈值判定——队形偏移/同连邻炮位
                                                             // 抖动不再反复清零，多门炮连 accum 净增长恢复，B02 闭合）
        track.pos = new_pos; track.last_fire_tick = world.tick

// v1.5（C4）：v1.4 声测三语义由注释规格落地为结构（原仅②以注释存在、upsert_sound_track 无函数体、IntelCircle 无键字段——G05/G16/G31 判"纸面闭合"）——
//   **v1.6 按清单⑫确认【已拍板，可推翻】：换阵地 accum 清零重计、停火期圈冻结为定案口径（R-03 回写按此选边——"圈随开火时长增长、停火冻结"，GDD 侧同步；推翻路径=换阵地结转精度，改 upsert 分支即可）**：
//   ① IntelCircle 增 source_unit 键、按 (team, source_unit) upsert——多炮多圈共存、同炮更新其圈（fire_at 按圈遍历取 MAX 的消费前提成立）
//      圈粒度 = 开火单位（连级）而非单炮：同连多门炮分散阵位共用一圈，R-03 语义按连解释（登记于 §X 变更记录）
//   ② upsert_sound_track 补函数体：新开火位置距 track.pos > sonar_move_reset_cm（D.0 新常数，默认 = sonar_max_radius_cm 之半）→ accum = 0（换阵地重定位）
//   ③ sonar_step 增门：world.tick − track.last_fire_tick <= sonar_hold_ticks（D.0 新常数，默认 100）才增长 accum（停火期圈冻结）
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
    IF ws.template.needs_deployed
       AND NOT (unit.deploy_state == DEPLOYED AND NOT e.redeploy_needed): RETURN FALSE
                                                             // R-05；v1.5（C3）：展开闸元素粒度——被拖过的元素须 cmd_deploy 清 redeploy_needed
                                                             // 才恢复开火（原仅读单位级 deploy_state：拖走一门炮整连带收炮，留守已展开炮即时禁射）
    IF e.mounted_in != NULL AND ws.template 不是 mounted_armament: RETURN FALSE
    ms = unit.template.mode_set
    IF (ms & TOW) AND e.towed IN {TOWING, TOWED}: RETURN FALSE
                                                             // R-19 拖曳双方禁射；v1.5（C1）：枚举扩 TOWING 后按双态判（原 == TOWED 在新枚举下漏牵引侧）
                                                             // 方案13：模板无 TOW 位则不问；TOW 位数据硬要求全量清单见 D.1#15
    IF (ms & (TOW|CARGO|TRANSPORT)) AND e.mode IN {TOW, CARGO, TRANSPORT}: RETURN FALSE  // D065 载货状态不作战（方案13）
    RETURN TRUE

FUNCTION select_target(world, e, ws) → Element|NULL
    w = ws.template
    cands = [x FOR x IN 敌方存活元素
             IF 单位被我发现(x.unit)                        // spotted_mask 含我队位
             AND x.mounted_in == NULL                       // v1.5（M10/G23）：排除车载班——乘员不可被直接命中，
                                                             // 伤害只经车毁 60% 连带转移（R-07 设计前提恢复；对无武装运兵卡车尤甚）
             AND (w.combat_style != SNIPER OR x.template.unit_type != MECH)
                                                             // v1.6（⑲A）【按推荐拍板·可推翻】：狙击武器候选剔除 MECH 元素——
                                                             // 与卡面"狙击目标均为人员"一致（原可自动选中威胁较高的卡车/装甲车并对
                                                             // 首车直扣 1~2 HP 绕过装甲曲线，tally≥3 整车击毁侦察车/卡车——A08）
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
    // 方案3：模板判空一行短路（消除无自卫档案炮卡每tick裸检查风险）
    // v1.5（M1/G30）：w_main.self_defense 裸引用改 w_main.template.self_defense（self_defense 是 WeaponTemplate 字段 D.3#25；
    //   weapon_states 结构无此子字段——原 IF 与 ANY 两处同族裸引用）
    // v1.5（M20）→ v1.6【已拍板——清单附表 M20 确认，可推翻】：自卫触发候选仅限 teamSpotted 敌元素（原对未发现单位自动还手=免费近距探测器，
    //   削弱骑兵/渗透班"摸炮位留最低成本"克制链——A09；推翻路径=明文"自卫为条件反射不需发现"并接受信息泄露代价）
    IF w_main.template.self_defense != NULL
       AND w_main.state == READY AND fire_permitted(world, unit, e, w_main)
       AND ANY(敌元素 WHERE spotted_mask 含我队位
                AND dist <= w_main.template.self_defense.max_range_cm):
        near = 最近敌元素（仅上述已发现候选中）
        w_main.use_self_defense = TRUE
        begin_aim(world, e, w_main, near)
    // 否则炮击任务在 system_combat 尾部统一推进

FUNCTION finish_aim(world, e, ws)
    tgt = ws.target
    IF tgt == NULL OR (tgt 不是 Building AND NOT alive(tgt))
       OR (tgt is Building AND tgt.hp <= 0): ws.state = READY; RETURN
                                                             // 不消耗弹药；Building 失的判据=hp<=0——v1.4 审查#1 注释宣称、
                                                             // v1.5（M4/G06/G29）补上缺失分支：原第二支路对 Building 恒假，
                                                             // 瞄准窗口内楼塌照常开火、弹丸携悬空引用对已移除实体二次结算
    IF is_aircraft(tgt):
        // v1.5（M4/G02·G08）→ v1.6【已拍板——清单附表 M4 确认，可推翻】：对空出口复核采最小许可集——
        //   phase 门与（needs_deployed 时的）C3 展开门（stance/mode 豁免维持 R-17 原语义，不套用全量 fire_permitted；
        //   原对空链从不调用 fire_permitted，禁火期/未展开/拖曳解挂后的机枪排与轻防空到期照常发射；
        //   推翻路径=套用全量 fire_permitted 含 stance/mode 门——对空链也吃 HOLD_FIRE/收装等门，改 R-17"对空恒自动"承诺）
        IF world.phase != 实战
           OR (ws.template.needs_deployed
               AND NOT (e.unit.deploy_state == DEPLOYED AND NOT e.redeploy_needed)):
            ws.state = READY; RETURN                        // 不发射、不耗弹
        fire_aa(world, e, ws, tgt)
    ELSE:
        IF NOT fire_permitted(world, e.unit, e, ws):
            ws.state = READY; RETURN                        // v1.5（M4/G32）：地面出口复核——AIMING 中被拖/禁射/收装/切模
                                                             // 到期不再发射（转 READY 不耗弹；原只守入口不守出口，
                                                             // "拖着重炮开火"侧门恰是修复#6 全力封堵的荒诞画面）
        fire_direct(world, e, ws, tgt)                    // 方案1：狙击/近战不再专路，统一直射链；建筑目标走建筑档案（v1.4）

FUNCTION select_profile(world, e, ws, tgt) → {damage_type, damage, blast_cm, pen_bonus}
    w = ws.template
    // R-11 自动选弹（共槽）：软目标优先 HE 档案
    IF w.alt_profile != NULL AND tgt.template.unit_type == INFANTRY:
        RETURN HE档案(w.alt_profile)
    // 方案11：受限弹药档案（钨芯）并入 ammo_profiles——常规 AP 打不动正面且档内有存货 → 自动救场，
    // 余量在档内计数（special_ammo_left 变量已删）；"仅正面打不穿才切"条件原样保留（第11轮语义）
    // v1.5（M16/G15）：读/减 weapon_states.ammo_profiles_left 实例副本（实例化时深拷贝）——
    //   原直接在共享模板上递减 count_left，三门 PaK38 全连仅 3 发，"每门 3 发"失真（v1.4 深拷贝仅注释宣称）
    FOR prof, i IN ENUM(w.ammo_profiles):
        IF ws.ammo_profiles_left[i] > 0 AND tgt.template.unit_type == MECH
           AND w.pen_max < tgt.template.armor_ke.front:
            ws.ammo_profiles_left[i] −= 1
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
    // v1.7（AMB-14）：直射链不再喂声测（写点删除——声测=曲射专用，见 §F3 注记与保留清单#3 修订）
    IF w.combat_style IN {MELEE, SNIPER} AND unit.infiltration_timer > 0:
        unit.infiltration_timer = 0                                    // 方案1：渗透身份清零随原 fire_sniper/fire_melee
                                                                       // 迁入此处；普通自卫开火不清——v1.6【已拍板——清单⑦A，可推翻】：
                                                                       // GDD R-04 回写为"狙击/近战开火后身份消失；普通自卫开火不清"
                                                                       //（原 GDD 原文"开火或爆破后身份消失"冲突两存三轮，就此勾销；GDD 侧执行）
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

FUNCTION cmd_attack(world, e, ws, target)                  // v1.4（审查 high#1）：AttackCmd 处理体——直射指定目标（含建筑）
    // 原 §D.7 声明"cmd_attack 见 §F4"而函数体缺失，Building 永远进不了 ws.target，
    // 建筑结算分支对直射武器是死代码——工兵×2/ISU 混凝土弹/OT-34/ML-20 直射拆楼入口在此补齐
    IF target is Building AND ws.template.vs_fort_mult_permille <= 1000: REJECT   // 建筑目标仅攻坚武器可指定
    IF target is Element AND ws.template.target_mask & GROUND == 0: REJECT
    IF target is Element AND ws.template.combat_style == SNIPER
       AND target.template.unit_type == MECH: REJECT         // v1.6（⑲A）【按推荐拍板·可推翻】：狙击指火门与 select_target
                                                             // 候选剔除同谓词——手动入口亦不可对 MECH 元素指定（A08）

    IF target is Element AND NOT (target.unit.spotted_mask & (1 << e.unit.team)): REJECT
                                                             // v1.5（M5/B01）：目标资格门①——spotted_mask 含我队位
                                                             //（与 select_target 同谓词；原手动指火绕过发现门，战争迷雾侧门通用存在）
    IF target is Element AND e.unit.template.flags.requiresMark
       AND target.unit.mark_level < SPOTTED: REJECT        // v1.5（M5/B01）：目标资格门②——犀牛门
                                                             //（shooter 单位 requiresMark 置位时须 target.mark_level >= SPOTTED；Building 豁免——
                                                             //  第8轮"仍需友军标记才能开火"在玩家最常用入口下恢复生效）
    IF target is Element AND target.mounted_in != NULL: REJECT
                                                             // v1.5（M10/G23）：车载班不可被指火（与 select_target 候选排除同谓词）
    IF NOT (ws.state == READY AND ws.ammo_left > 0): REJECT
    IF NOT fire_permitted(world, e.unit, e, ws): REJECT
    IF dist_cm(e.pos, target.pos) > ws.template.max_range_cm: REJECT
    IF target is Element
       AND |angle_diff(e.facing, approach_deg_of(target.pos, e.pos))| > e.template.fire_arc_deg:
        rotate_step(world, e, 朝向 target); RETURN        // R-09 射界门外先转车体（建筑无朝向，不进此分支）
    begin_aim(world, e, ws, target)

FUNCTION cmd_toggle_ambush(world, unit)                    // v1.4（审查 high#2）：ToggleAmbushCmd 处理体——原 ambush_active 全文无 TRUE 写点，R-12 整链不可达
    IF NOT unit.template.flags.canAmbush: REJECT           // 资格门（canAmbush 恢复消费）
    // v1.6【已拍板——清单⑮A（A03），可推翻】：置位 4 卡成文（D.1#25 数据硬要求，同 TOW 位先例格式）——
    //   置位 = SU-85 / 三突G / 四号歼击车 / 追猎者（三遍审查共识伏击组）；SU-76 / ISU-152 / 犀牛不置位
    //   （ISU-152 放弃伏击×2 隐蔽+130% 首击、犀牛放弃 1400m 伏击首击，两卡按"无伏击"定价；翻案须重估分数与反伏击手段）
    IF unit.ambush_active:                                 // 手动退出：下一发精度加成待触发（消费点 fire_direct / §F3 在位）
        unit.ambush_active = FALSE; unit.ambush_shot_bonus = TRUE
    ELIF unit 静止 AND unit.move_path == []:               // 开启：视野减半 + 隐蔽乘成（§F3 两消费点生效）
        unit.ambush_active = TRUE
    // 移动自动退出（无加成）由 system_move 承载；开火不自动退出（R-12）

FUNCTION aa_try_engage(world, e, ws)                      // B5 修复的另一半（进入条件已由 system_combat ② 名单化——方案2）
    IF e.towed IN {TOWING, TOWED}: RETURN
                                                             // v1.7（GAP-20）：删 v1.3#9 的单位级 ANY 连带子句——与地面链 fire_permitted
                                                             // 同谓词（元素级单判）。原 ANY 使"卡车拖走 1 门、留守门对空自动交战整链静默"，
                                                             // 与 v1.3#12 元素级拖曳、v1.5 C2"部分被拖时留守元素照常机动/开火"联立解冲突
                                                             //（防空恰是元素级拖曳核心场景）；牵引侧 TOWING 仍被本判拦截（R-19 拖曳双方禁射）
    cands = [a FOR a IN world.aircraft
             IF a.team != e.unit.team AND (a.spotted_mask & 我队位)
             AND (a.alt_tier <= e.unit.template.air_ceiling)
                                                             // v1.5（M1/G20）：原裸引用 unit.air_ceiling——unit 不在本函数作用域
                                                             // （air_ceiling 是 UnitTemplate 字段，六张防空卡对空目标筛选唯一入口挂在必然报错的引用上）
             AND dist_cm(e.pos, a.pos) <= ws.template.max_range_cm]
    IF cands == []: RETURN
    ws.target = MIN(cands, by dist_cm)                    // 对空威胁=最近——v1.6【已拍板——清单⑰A（A05），可推翻】：
                                                             //   维持 MIN by dist_cm、实现零改动；与地面 threat_value（DPS 近似）口径差
                                                             //   以注记显式化——GDD R-17 注记"后续可换威胁加权表（对空链落地与地面同构的
                                                             //   简化威胁分）"留可翻案接口（GDD 侧回写；推翻路径=按机型/挂载加权，数值章节定表）
    begin_aim(world, e, ws, ws.target)
```

### F4.1 炮击任务（R-13/R-14/R-16/R-03 盲射）

```
FUNCTION process_fire_mission(world, unit)
    fm = unit.fire_mission
    guns  = (fm.salvo_mode == HALF) ? 前 ⌈N/2⌉ 门 INDIRECT 元素 : 全部 INDIRECT 元素   // R-14 半轮
                                                             // v1.7（AMB-09 拍板）：半轮取整口径成文=⌈N/2⌉（向上取整——
                                                             // 与 GDD 例 6→3、4→2 兼容；3 门连半轮=2 门）
    FOR gun IN guns:
        ws = gun 主武器
        IF NOT (ws.state == READY AND fire_permitted(world, unit, gun, ws)): CONTINUE
        // 【v1.1 修复】未展开/被拖/载货的炮不打——统一走开火许可
        fire_at(world, gun, ws, fm)

FUNCTION fire_at(world, gun, ws, fm)                      // 无目标弹丸（B：fireAt 定义体）
    w = ws.template
    IF fm.form == POINT:  pt = fm.target_point
    ELIF fm.form == LINE: pt = 沿 fm.target_line 均匀取样(第 k 份, k = fm.shots_fired)   // v1.4：取样序号由任务体承载（原"已发射数"不可回推）
    ELSE: /* CREEP */     t = MIN(1, (world.tick − fm.started_tick) * fm.creep_speed_cm_tick
                                       // MAX(1, 线长))
                          pt = LERP(fm.target_line.a, fm.target_line.b, t)
    // 盲射声测圈：目标点落在模糊圈内 → 叠加圈半径
    extra = 0
    FOR c IN world.intel_circles WHERE c.team == gun.unit.team
         AND dist_cm(c.center, pt) <= c.radius_cm: extra = MAX(extra, c.radius_cm)
    // 连内共享校射 R-16（方案10；校射仅 POINT 形式——v1.4 默认落地，v1.6【已拍板——清单⑩A 确认，可推翻】：
    // GDD 校射承诺锚在"点射击"，LINE/CREEP 线性/移动落点无稳定校射点，短路；target_point 对 LINE/CREEP 恒 null，
    // 换点重置分支随之不触发；推翻路径=定义线的校射点语义[线中点/逐落点]）：
    IF fm.form == POINT AND point_in_friendly_vision(world, gun.unit.team, fm.target_point):   // 定义体 §F3 含烟/林遮断（审查#13）
        fm.calib_progress = MIN(100, fm.calib_progress + cfg.calib_per_shot)     // 按发累积
    IF fm.form == POINT AND fm.target_point != fm.calib_target:
        fm.calib_target = fm.target_point; fm.calib_progress = 0              // 换点重置
    scatter_cm = w.dispersion_cm * (10000 − fm.calib_progress*calib_max_reduction_bp//100)//10000
               + extra
    // v1.5（M8/A14）：曲射档案明确为 alt_profile 若存在否则默认 HE 档——双职炮（KE 主炮）曲射吃 HE 数值
    //   （原 profile=默认HE 对 KE 主炮语义悬空：其默认档案是 KE 的，曲射压制数值会全错；纯榴弹炮两者同一）
    prof = (w.alt_profile != NULL ? HE档案(w.alt_profile) : 默认HE档案)
    // v1.5（M8/G11）：读 w.salvo——每次 fire_at 发 salvo 发（原恰 1 发/次，喀秋莎/Nebelwerfer 齐射
    //   退化为逐发隔装填滴流，"齐射压制之王"节奏失真；弹药/任务计数按 salvo 增减，LINE 取样序号随
    //   shots_fired 按批推进——同批 salvo 发共用同一取样点、各吃独立散布）
    FOR i IN 1..w.salvo:
        aim = pt + (world.rng[SCATTER].sym(scatter_cm), world.rng[SCATTER].sym(scatter_cm))
        world.projectiles.append(Projectile(shooter=gun, weapon=w, profile=prof,
            pos=gun.pos, dest=aim, speed=w.projectile_speed_cm_per_tick,
            trajectory=BALLISTIC, hit_target=NULL, will_hit=FALSE))
    ws.ammo_left −= w.salvo; ws.state = RELOADING; ws.timer = reload…
    mark_resupply_if_needed(world, gun.unit)               // v1.3（审查#11）
    fm.shots_left −= w.salvo; fm.shots_fired += w.salvo
    upsert_sound_track(world, gun.unit, gun.pos)          // 火箭炮 acoustic_signature 最高→最快被定位（写侧不动，方案4；函数体 v1.5 C4）
                                                             // v1.6【已拍板——清单㉗A（A16），可推翻】：曲射只留声测痕迹、不触发开火暴露——
                                                             // reveal_timer 仅直射链写（v1.7 GAP-26：cmd_smoke 写点撤销，本注记随之收窄），
                                                             // 曲射反炮博弈完全走声测圈，烟/位移为炮位生存手段；R-03 回写注记（GDD 侧）。
                                                             // 疑点⑨自 v1.2 在册"待另行拍板"就此认领闭户；推翻路径=fire_at 补写 reveal_timer（时长可配短）
    IF fm.shots_left <= 0: gun.unit.fire_mission = None   // 方案10：任务体销毁，校射进度随之失效

FUNCTION cmd_fire_mission(world, unit, form, point_or_line, ammo_mult, salvo_mode, creep_speed)
                                                           // v1.3（审查-原始行）：任务创建入口——原全文只有清空写点，任务永远无法下达
    IF NOT (unit.template.mode_set & INDIRECT): REJECT
    guns = [e FOR e IN unit.elements IF e.mode == INDIRECT]
    IF guns == []: REJECT
    // v1.5（M9/G03）：HALF 用半数元素计算 shots（与 process_fire_mission"前一半 INDIRECT 元素"同规则）——
    //   原总发数按全连初值、由半数炮发射：每门实际消耗翻倍、任务时长翻倍，前一半打空后 shots_left 仍剩一半、
    //   任务体悬挂不销毁、弹药车贴靠自动续打至全轮量（玩家未下令的续射），"半轮快打快跑/保留半数弹药"双双失真
    shots = (salvo_mode == HALF ? LEN(guns 前一半) : LEN(guns)) × guns[0] 主武器 ammo_base × ammo_mult      // R-13 弹量基数（一倍/两倍/三倍）
    unit.fire_mission = FireMission{form, point_or_line, creep_speed, ammo_mult, salvo_mode,
                                    shots_left = shots, shots_fired = 0, started_tick = world.tick,
                                    calib_target = (form == POINT ? 目标点 : NULL), calib_progress = 0}
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
    IF ANY(x.towed IN {TOWING, TOWED} FOR x IN unit.elements): base = speed_table[tow_speed_tier]
                                                             // 拖曳双方最低档 R-19（GDD-02:254"拖曳中：牵引车+被拖车均……速度最低档"）；
                                                             // v1.3：元素级判定（原 unit.tow_pair 已删）——单位粒度维持（G07③ 待拍板）。
                                                             // v1.5 走查修：C1 枚举扩 TOWING 后随同步为双态判——原 == TOWED 不再命中
                                                             // 牵引侧，牵引卡车拖曳中将按自身 4 档机动、违反 R-19"双方最低档"
                                                             //（与机制版 v1.5 §2 anyElementTowed 含两态、牵引侧同降档对齐）
    m_bp = world.terrain_speed_bp(unit.pos, unit.template.movement_class)   // Tiled 属性
    IF e.crit != NULL AND e.crit[MOB] == MINOR: m_bp = m_bp * crit_mob_minor_mult_bp // 10000
    v = base * m_bp // 10000
    IF world.on_road(unit.pos) AND unit.template.movement_class != FOOT:
        v = MAX(v, cfg.road_bonus_cm_tick)                 // v1.3（审查#6）：道路机动承载——原 road_bonus/on_road 全文零消费（轮式侦察卡核心身份）
    RETURN v
    //（v1.1 的 sprint_timer × sprint_mult_bp 行已删——方案14；sprint_mult_bp 常数随之删除）

FUNCTION system_move(world, unit)
    IF unit.deploy_state IN {DEPLOYING, PACKING}: RETURN   // 展开中禁移动
    IF ALL(e.towed == TOWED FOR e IN unit.elements): RETURN
                                                             // v1.5（C2/G07①/B05①）：仅全部元素都 TOWED 的单位才不自主移动（由牵引车带）——
                                                             // 删除 v1.3"任一元素被拖即整单位 RETURN"（拖走 1 辆抛锚车/挂拖一门炮，
                                                             // 同单位健康元素连带冻结、既不能开火也不能移动）
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
    FOR e IN unit.elements:                              // v1.4（审查 high#3）：队形偏移——非车载/非被拖元素随基准点更新
        IF e.mounted_in == NULL AND e.towed != TOWED:     // v1.5（C2/B03）：覆盖条件改 != TOWED——TOWING 牵引元素正常随本单位移动
                                                             //（原 == NONE 把牵引元素一并排除，而其坐标再无任何写点——拖曳转场在元素几何层面不发生）
            e.pos = 队形偏移(unit.pos, e.element_id)      //（原仅首元素随动：射程门/弹丸起点/补给半径/声测圆心全按出生坐标结算）
            e.facing = unit.elements[0].facing            // v1.5（C2/G14）：facing 两维随动——2#/3#/4# 车受弹面（resolve_hit）
                                                             // 与无炮塔射界门不再按出生朝向结算，"摆位"不再只摆正主车
    IF ANY(e.garrison_in != NULL FOR e IN unit.elements):
        cmd_un_garrison(world, unit)                     // v1.4：移动自动出楼（楼槽释放、隐蔽/尾甲加成终止——与伏击移动退出同族）
    IF unit.ambush_active: unit.ambush_active = FALSE    // v1.5（M1/G10）：unit. 前缀补齐——移动自动退出，无首击加成
                                                             //（原裸写 ambush_active = FALSE——按字面实现即写未定义局部变量，退出链失效）
    IF unit.ambush_shot_bonus: unit.ambush_shot_bonus = FALSE
                                                             // v1.5（M19）→ v1.6【已拍板——清单附表 M19 确认，可推翻】：首击加成随移动一并清除（R-12 注记）——
                                                             // 原退出伏击后携加成跨半场机动、加成与伏击位脱钩（A21；推翻路径=改时限失效或恢复"无失效条件"原状）
    FOR pair IN world.tow_pairs WHERE pair.tower_elements[0].unit == unit:
        IF unit.pos != 本 tick 起点:                        // v1.7（AMB-10 拍板·可推翻）：有位移才随动——
            dir = (unit.pos − 本 tick 起点) 归一化           // 被拖元素跟随于牵引元素**后方固定偏移**（tow_follow_offset_cm=300，
            pair.towed_element.pos = pair.tower_elements[0].pos − dir × cfg.tow_follow_offset_cm
                                                             // 消除同坐标重叠（原重叠：爆炸半径判定同时命中车炮、被拖受弹面无意义——
                                                             // 机制版 §2 :250 口径，两版同构）；推翻通道=回"AMB-10 改B"改同点重叠
        pair.towed_element.facing = unit.elements[0].facing  // v1.7（AMB-10）：被拖 facing 跟随牵引朝向（原文无写点——
                                                             // 拖曳全程炮身保持拖前旧朝向、受弹面按旧朝向结算的缺口闭合）
        IF ALL(x.towed == TOWED FOR x IN pair.towed_element.unit.elements):
            pair.towed_element.unit.pos = pair.tower_elements[0].pos
                                                             // v1.5（C2/B05②③）：全被拖单位的队形基准点随动——侦测/占点/R-18 补给半径
                                                             // 不再按拖曳前旧位置结算；解挂后队形循环不回跳抛锚点/旧阵地坐标
    sync_followers(unit)

FUNCTION sync_followers(unit)
    FOR e IN unit.elements WHERE e.mounted_in != NULL: e.pos = e.mounted_in.pos    // 条件槽：未分配恒 NULL（方案12）
    FOR e IN unit.elements WHERE e.mode == TRANSPORT AND e.cargo_units != NULL:    // 方案12：按槽存在性短路
        FOR squad IN e.cargo_units: squad.pos = e.pos               // D065 摩托化机动——B8

FUNCTION rotate_step(world, e, target_deg)                  // R-09 转车体（转向慢=暴露窗口）
    // 方案6：仅 fire_arc_deg<360 模板可达（ground_direct 射界门对 360° 模板恒假，天然豁免；
    // 此类模板不分配 rotating 槽，resolve_hit 受弹面判定亦按模板短路）
    diff = angle_diff(target_deg, e.facing)
    step = e.unit.template.turn_rate_deg_per_tick         // v1.4：未定义变量 unit 笔误修正（原七张无炮塔卡转向挂空引用）
    IF |diff| <= step: e.facing = target_deg
    ELSE: e.facing = (e.facing + SIGN(diff)*step) % 360
    e.rotating = (|angle_diff(target_deg, e.facing)| > e.template.fire_arc_deg)
    // v1.5（M3/B04）：rotating 改按当前角差重算、不锁存——|角差| <= fire_arc_deg 时 FALSE、否则 TRUE（每次调用重算）。
    //   原清除分支条件 |diff|<=step 与两调用点进入条件 |diff|>fire_arc（step < fire_arc）交集为空，
    //   rotating=FALSE 为死分支：首次转向后锁存 TRUE，该车一切被命中永久按 SIDE 结算——
    //   "转动期间侧面暴露"漂移为"转过一次永久侧面"，摆位操作核心被锁存态摧毁。
    //   新语义：炮身已能指向目标（入射界）即不再计转向中；仍差射界才计（转向慢=暴露窗口，R-09 原语义）
```

---

## §F6. 展开 / 运输 / 拖曳 / 驻楼 / 后勤（§13→B4 / B6 / g-载重 / g-拖曳解除）

```
// ── deployState 状态机（迁移表见机制版 v1.2 §10；动作函数在此）──
FUNCTION cmd_deploy(world, unit)                            // DeployCmd
    // v1.6 终审修复 1b【按终审指令落地·可推翻】：删除 v1.5 单位级 ANY 拖曳门（IF ANY(e.towed==TOWED) → REJECT）——
    //   "禁止边拖边展开"下沉为元素粒度：展开作用域限于非 TOWED 元素，被拖元素保持 redeploy_needed=TRUE
    //   待解挂后重展开（留守门可展开）。v1.5 该门使 MOBILE 炮连部分拖曳期间留守门亦不可展开（须先解挂→展开→
    //   重挂），与终审指令"仅被拖门不可展开、留守门可"相反；v1.5 注记"系 C3 规格原文、须另行拍板、本版不擅改"
    //   随之废除——C3 规格与 §X/终审登记句同步修订（§X·二.3、§X·五.1），机制版 §10/§17.2/GDD 待同步第 19 条
    //   由机制版定稿员同步。
    // 授权链（在库可核，v1.6 独立终审追补）：终审指令非仓库外口头指令——docs/.zcode/workflow-runs/
    //   dwfrun-23ebdd22-dbc0-4555-b8b1-27def7ced52a.mjs（v1.6 拍板定稿主控脚本）FIX5 第 1 条第二分句原文
    //   「且"禁止边拖边展开"门改元素粒度（仅被拖门不可展开，留守门可）」，即本变更的成文授权源；v1.5 两版
    //   "不擅改"注记正是被该指令推翻的旧决定。拍板清单 v1.6 侧补一条 FIX-1b 登记/追认条目——已登记 §Y·五。
    // G17 旁路（原 v1.4 无门时：DEPLOYED 炮被挂拖后拖运途中下 DeployCmd，30 秒拖运走完 DEPLOYING、
    //   解挂瞬间已 DEPLOYED 立即开火）由元素旗闭合：被拖元素 redeploy_needed 于 start_tow 置位（§F2）且
    //   拖曳中不清（下方清除循环排除 TOWED 元素）——解挂后仍须再下 cmd_deploy 走 ELIF 分支重展 30 秒方可开火，
    //   "到位后展开 30 秒"不可旁路。
    IF unit.deploy_state == MOBILE:
        unit.deploy_state = DEPLOYING
        unit.deploy_timer = unit.template.deploy_time_ticks
                                                             // v1.5（M18/A20）：deploy_timer 写入移入分支内——原写在函数体级：
                                                             // DEPLOYING 期重复下达重置进度；PACKING 期下达状态不迁移却把计时器
                                                             // 覆盖为展开时长（收起以展开时长完成，对时长不等的卡进度失真）
    ELIF unit.deploy_state == DEPLOYED
         AND ANY(e.redeploy_needed FOR e IN unit.elements WHERE e.towed != TOWED):
                                                             // v1.7（GAP-09）：ELIF 补 WHERE e.towed != TOWED——与下方清旗循环同作用域。
                                                             // 原无过滤 ELIF 使"拖走 1 门留守 3 门"时下 DeployCmd 全连回 DEPLOYING
                                                             // 空走 30 秒、needs_deployed 门禁射全部留守门（FIX-1b 半边落实，与机制版不同构）
        unit.deploy_state = DEPLOYING                        // v1.5 终审修 1a（高）：解挂重展开须有时长承载——
        unit.deploy_timer = unit.template.deploy_time_ticks  // C5 使"拖走 1 门"时单位保持 DEPLOYED（留守门可开火的设计前提），
                                                             // 原实现对该状态只清 redeploy_needed 旗（零成本），被拖门解挂后下
                                                             // cmd_deploy 即时恢复开火、30 秒重展开不存在——与 C3 自身注释
                                                             // "解挂后须 cmd_deploy 重新展开才可开火"（§F2 :497/§F4 :663）直接矛盾；
                                                             // v1.4 的"被拖单位须 MOBILE"门随 C5 删除后无替代闸，本分支即替代闸：
                                                             // 含 redeploy_needed 元素的 DEPLOYED 单位回 DEPLOYING 重走展开时长，
                                                             // 期间 needs_deployed 门（deploy_state != DEPLOYED）自然禁射全连
    FOR e IN unit.elements WHERE e 有 redeploy_needed 槽 AND e.towed != TOWED:
        e.redeploy_needed = FALSE
                                                             // v1.5（C3）清除全单位重展开旗 + v1.6 终审修复 1b：清除范围限非拖曳中
                                                             // 元素（towed != TOWED）——被拖元素保持 TRUE、不进本次展开作用域
                                                             //（TOWING 牵引元素正常清除：其开火另由 fire_permitted 拖曳禁射门拦）；
                                                             // 未分配槽的非 GUN/非可被拖 MECH 元素不写。旗于下达时清除——
                                                             // 上方 ELIF 分支已先行迁入 DEPLOYING，时长闸由 deploy_state 承载。
                                                             // v1.7（AMB-11 拍板）：重展开窗口（解挂→重新展开完成）内全连禁射
                                                             //   为连级展开制固有代价、正式接受——GDD 补-19 补注随 GDD v1.8 执行；
                                                             //   元素级 deploy_timer 方案（状态机大改）留作翻案通道"AMB-11 改B"
FUNCTION cmd_pack_or_move(world, unit)                      // PackCmd / MoveCmd 触发
                                                             // 〔2026-10-07 发起人拍板批注（命令族收口块）：MoveCmd 触发面已接线——
                                                             // 采本行 IMPL 字面（真两难闭账，登记表 PB-56 批② 留待项① 收口）。
                                                             // 落点=movement.issue_move 效果点（门2/3/4 后=拒令零副作用）：
                                                             // DEPLOYED×移动令（外部非排队+handoff 两通道）=下方第一 IF 同款转 PACKING+
                                                             // 本令照常安装——收装完成前 system_move 同名门拦位移、收装毕自动续走
                                                             // （「先收装再走」）；DEPLOYING×外部移动令=下方第二 IF 同款作废回 MOBILE
                                                             // 同拍放行；PACKING 拒令维持（三文档均无打断语）。两测试锚随拍板翻转
                                                             // （test_move_commands 门1 族/test_tow_deploy TestDeployMoveInterlock）〕
    IF unit.deploy_state == DEPLOYED:  unit.deploy_state = PACKING; unit.deploy_timer = pack_time
    IF unit.deploy_state == DEPLOYING: unit.deploy_state = MOBILE; unit.deploy_timer = 0  // 进度作废

// ── R-07 上/下车（同卡）与 D065 运兵（跨卡）统一（v1.3 重写；v1.4 补装载链五缺口 I-19；v1.6 ㉑A 粒度下沉班元素）──
FUNCTION 载具占用数(carrier) → int                          // v1.4：座位账目 + v1.6（㉑A）【按推荐拍板·可推翻】改元素粒度——
                                                             // 按 mounted_in 班元素指针计座（1 班=1 座；原 cargo_units 计单位不计班：
                                                             // 跨卡班分流两车时同单位在两车 cargo_units 各记 1 尚可、但同车多班只记 1——账目失真）
    n = COUNT(s IN carrier.unit.elements WHERE s.mounted_in == carrier)   // 同卡班元素
    IF carrier.cargo_units != NULL:                                       // 跨卡：班元素挂载点亦为 mounted_in
        FOR squad IN carrier.cargo_units:
            n += COUNT(se IN squad.elements WHERE se.mounted_in == carrier)
    RETURN n
FUNCTION 在途请求数(carrier) → int                          // v1.4：挂起装载请求占座（原请求在途不占座→两班挤一车）；v1.6（㉑A）：请求条目=班元素，计数即班数
    RETURN COUNT(r IN (world.mount_requests ?? []) WHERE r.carrier == carrier)
FUNCTION cmd_dismount(world, squad_unit)
    FOR e IN squad_unit.elements WHERE e.mounted_in != NULL AND e.template.element_type == SQUAD:
        carrier = e.mounted_in
        e.pos = carrier.pos 旁落位; e.mounted_in = None
        IF squad_unit != carrier.unit AND carrier.cargo_units != NULL       // v1.3：双向引用同步清（原漏清→下车班被拴回卡车死锁）
           AND squad_unit IN carrier.cargo_units: carrier.cargo_units.remove(squad_unit)
FUNCTION cmd_mount(world, squad_elements[], carrier_unit)   // v1.6（㉑A）【按推荐拍板·可推翻】重写：粒度下沉班元素——
                                                             // 请求体记录班元素列表（§D.7 MountCmd 签名同步），逐班选最少挂载载具并逐班占座，
                                                             // 去重改按班元素。原单位级一条请求把全排班元素挂上单一载具：seats=1 的 251/卡车被塞
                                                             // 3 班（D065"运兵模式载1个班"与 R-07"3班随4×251"双失守），座位账目与实际挂载数不匹配、
                                                             // 超载无闸；且同单位去重使第二条请求必然 REJECT，v1.4#9"最少挂载分配"被去重锁死，
                                                             // "3班→3车"经 cmd_mount 不可重建（开局一比一预挂形态一旦下车即劣化为全挤一车）、
                                                             // 单一 251 被毁三班同吃 60% 连带（G25/v1.3 GAP-06 闭合）
    ok = 0
    FOR s IN squad_elements 按列表序:
        IF s.template.element_type != SQUAD: CONTINUE       // 只挂班元素（v1.3#4 口径随粒度下沉）
        IF ANY(r IN (world.mount_requests ?? []) WHERE r.squad_element == s): CONTINUE
                                                             // 去重改按班元素（v1.4 同班去重语义随粒度迁移，原按 squad_unit 整队去重）
        IF ANY(e.garrison_in != NULL FOR e IN s.unit.elements):
            cmd_un_garrison(world, s.unit)                  // v1.5（M11/G24）：挂载即出楼——原 garrison×mount 状态机无互迁边：
                                                             // 驻楼班楼旁上车后 garrison_in 永久保持，骑乘期持续吃驻楼隐蔽/尾甲、
                                                             // 楼位被机动卡车远程占用（移动自动出楼位于车载早返回之后，整班上车后永不触发）
        carriers = [e FOR e IN carrier_unit.elements IF e.template.seats > 0]
        carrier = carriers 中 (载具占用数 + 在途请求数) 最小者    // v1.4：最少挂载分配（原固定首个→3 次再上车全落 251#1）
                                                             // + v1.6（㉑A）：逐班重选（前班占座后，次班自然落到次空闲车——3班→3车）
        IF carrier == NULL: CONTINUE
        IF carrier.mode IN {CARGO, TOW}: CONTINUE           // v1.4：载货/拖曳状态不可载人（替代 v1.3"须 TRANSPORT"一刀切——
                                                             //   251 等无三模式位载具恒 DIRECT 可载，R-07 车载开火不冲突）；
                                                             //   v1.6（㉑A）：REJECT 改 CONTINUE——逐班语义，该班跳过、其余班继续分配
        IF (carrier.template.mode_set & TRANSPORT) AND carrier.mode != TRANSPORT: CONTINUE
                                                             // v1.5（M13/G18）：mode_set 含 TRANSPORT 位的载具[卡车]必须处 TRANSPORT 才可载人——
                                                             //   251 等无位载具不受限。堵"卡车 DIRECT 载班 → 切 CARGO 装货/切 TOW 拖炮"的
                                                             //   三模式互斥旁路（原复现链：切模清班分支仅对 mode==TRANSPORT 起点触发，已挂班无人清理）
        IF 载具占用数(carrier) + 在途请求数(carrier) + 1 > carrier.template.seats: CONTINUE   // seats 上限（含在途占座——逐班判）
        IF world.mount_requests == NULL: world.mount_requests = []      // 方案12：惰性建表（首条请求才建）
        IF s 静止于 carrier 旁 AND carrier 静止:
            world.mount_requests.append({squad_element: s, carrier, mount_time_ticks}); ok += 1
    IF ok == 0: REJECT                                      // 无任何班获分配 → 命令整体拒绝（部分成功为逐班语义）
FUNCTION mount_requests_step(world)                          // 每 tick
    IF world.mount_requests == NULL: RETURN                 // 方案12：无表即无请求（非异常）
    FOR r IN list(world.mount_requests):
        // v1.4（I-19）：到期复核——任一方不在编 / 载具已切出可载状态 / 座位超占 → 撤销请求
        //   + v1.6（㉑A）：复核谓词随元素粒度——申请载体为班元素，"申请班已全灭"改判班元素不在编
        IF r.carrier NOT IN r.carrier.unit.elements
           OR r.squad_element NOT IN r.squad_element.unit.elements
           OR r.carrier.mode IN {CARGO, TOW}
           OR 载具占用数(r.carrier) + 在途请求数(r.carrier) > r.carrier.template.seats:
            remove r; CONTINUE
        r.ticks_left −= 1
        IF r.ticks_left <= 0:
            r.squad_element.mounted_in = r.carrier          // v1.6（㉑A）：逐班挂载（原到期把整队 SQUAD 元素全挂单一
                                                             // 载具——seats=1 载具被塞 3 班的根因；v1.3#4"只挂班元素"由
                                                             // 请求体粒度天然保证）
            IF r.squad_element.unit != r.carrier.unit:      // v1.3：cargo_units 仅跨卡（单位级登记去重——
                IF r.carrier.cargo_units == NULL: r.carrier.cargo_units = []
                IF r.squad_element.unit NOT IN r.carrier.cargo_units:
                    r.carrier.cargo_units.append(r.squad_element.unit)
                                                             // 座位实账走 mounted_in 指针[载具占用数]，本表只作
                                                             // 跨卡班单位的随动/清理登记——同单位多班挂同车不重复入表）
            remove r

// ── D065 卡车三模式：元素级互斥切换（B6 修复）──
FUNCTION cmd_set_element_mode(world, e, m)
    IF m NOT IN e.unit.template.mode_set: REJECT
    IF e.mode == TOW:      release_tow_if_involved(world, e)     // 切模式先解挂（v1.7 GAP-24：改传元素——仅解除本元素牵涉的拖曳对）
    IF e.mode == CARGO AND e 有 hasSupply 槽:                                  // 方案12 条件槽
        e.supply_rounds = 0; e.supply_medical = 0                     // 卸货
    IF e.mode == TRANSPORT AND e.cargo_units != NULL:                 // 方案12 条件槽
        FOR s IN e.cargo_units:
            FOR se IN s.elements WHERE se.mounted_in == e:            // v1.3（审查#3）：双向引用同步清（原只清 cargo→班仍随车瞬移+车载禁射）
                se.pos = e.pos 旁落位; se.mounted_in = None
            s.pos = e.pos 旁落位
        e.cargo_units = []
    IF m != TRANSPORT AND world.mount_requests != NULL:   // v1.4（I-19）：切出运载状态清挂起请求（原到期仍挂上 CARGO 卡车）
        world.mount_requests = [r FOR r IN world.mount_requests IF r.carrier != e]
    e.mode = m
    IF m != INDIRECT AND NOT ANY(x.mode == INDIRECT FOR x IN e.unit.elements):
        IF e.unit.fire_mission != NULL: e.unit.fire_mission = None
                                                             // 任务取消（方案10：任务体销毁，校射随之失效）
                                                             // v1.5（M21/A24）：元素级清除——仅当本单位已无任何 INDIRECT 元素才清任务
                                                             //（原任一元素切非 INDIRECT 即清：52-K/Flak 88 连 1 门切 DIRECT 当反坦克炮，
                                                             //  另 1 门仍在 INDIRECT 的曲射任务被连带销毁——与 system_combat 推进条件
                                                             //  ANY(e.mode==INDIRECT) 的挂点粒度正好相反；e.mode=m 已先行赋值，本判定自然排除刚切元素）

FUNCTION buy_supplies(world, truck_element, rounds, medical)         // BuySuppliesCmd
    IF NOT truck_element 有 hasSupply 槽: REJECT                     // 方案12：非补给载具直接拒绝
    IF truck_element.mode != CARGO: REJECT                 // v1.3（审查#8）：仅物资模式可装货（原运兵/拖曳模式可预装，切回即生效破坏互斥）
    weight = rounds × cfg.supply_round_weight + medical × med_weight_per_unit
                                                             // v1.5（M15/G21）：弹药池通用每发重量（D.0 新常数 supply_round_weight）——
                                                             //   原"rounds × Σ(武器 ammo_weight 均摊)"求和对象（哪张卡/哪些武器档案）两版均未定义，
                                                             //   通用弹药池的 600 发与 120 份重量互斥核算无法照写
    IF rounds  > truck_element.template.cargo_rounds_max:  REJECT   // v1.5（M1/G21）：三处原裸引用未定义变量 truck（形参为 truck_element）
    IF medical > truck_element.template.cargo_medical_max: REJECT
    IF weight  > truck_element.template.cargo_weight_max:  REJECT   // D012 混装载重闸（g-载重）
    truck_element.supply_rounds = rounds; truck_element.supply_medical = medical

// ── 拖曳指令（v1.3 元素级；v1.4 补互斥门——审查 medium；v1.7 补资格门——终检 GAP-10）──
FUNCTION cmd_tow(world, tower_elements[], towed_element)
    IF ANY(t.unit.team != towed_element.unit.team FOR t IN tower_elements): REJECT
                                                             // v1.7（GAP-10）：拖曳链同队门——R-19"保车"体系锚定己方，
                                                             // 原无校验可拖走敌方火炮/坦克（变相控制，无缴获机制承载）；与 :1252 补给
                                                             // 分支 R-21 同队门/⑳A 同队门同构
    IF NOT (towed_element 为 GUN 元素
            OR (towed_element 为 MECH 元素 AND (towed_element.unit.template.mode_set & TOW) != 0)): REJECT
                                                             // v1.7（GAP-10）：合法被拖对象门——排除 SQUAD 班/空投箱 CARGO 元素
                                                             //（机制版 :955 自注"拖走空投箱如出现需加禁止位"就此闭合）/一切无 TOW 位卡
    FOR t IN tower_elements:                              // v1.4：堵三模式互斥旁路（原载货卡车可拖炮、一车拖两门）
        IF t.towed != NONE: REJECT                       // 已在拖（TOWING/TOWED）的元素不可再挂——v1.5（C1）：随枚举扩双态
        IF (t.unit.template.mode_set & (TOW|CARGO|TRANSPORT)) AND t.mode != TOW: REJECT   // 载货/运兵状态不可牵引（D065 互斥）
        IF (t.unit.template.mode_set & TOW) == 0: REJECT  // v1.7（GAP-10）：牵引资格=TOW 位（数据硬要求见 §D.1#15）
    start_tow(world, tower_elements, towed_element)      // 失败静默拒绝
FUNCTION cmd_untow(world, element):
    FOR pair IN [p FOR p IN world.tow_pairs
                 IF element ∈ p.tower_elements OR element == p.towed_element]:
        stop_tow(world, pair, VOLUNTARY)

// ── 驻楼（最小实现，v1.6【已拍板——清单⑨A，可推翻】：驻楼=隐蔽+3；受击判定简化[按尾甲]——"建筑进驻加成"定义回写 GDD（GDD 侧）；推翻路径=加硬减伤 ×0.7 类，需新常数并与楼塌连带联动）──
FUNCTION cmd_garrison(world, unit, building)
    IF NOT flags.canGarrison OR building.garrison_slots <= LEN(building.garrisoned): REJECT
    FOR e IN unit.elements: e.garrison_in = building; building.garrisoned.append(e)
    // 效果两处（v1.3 补齐第二处，原注释宣称两处实现只落地一处）：
    // effective_stealth_x10（+garrison_stealth_add，方案5 短路）+ resolve_hit 命中面（garrison_in != NULL → REAR）
FUNCTION cmd_un_garrison(world, unit)
    FOR e IN unit.elements WHERE e.garrison_in != NULL:
        e.garrison_in.garrisoned.remove(e); e.garrison_in = None; e.pos = 楼旁落位

// ── 反狙击掩护（v1.3：1:1 约束；v1.4：资格门）──
FUNCTION cmd_set_sniper_cover(world, sniper_unit, target_unit)
    IF NOT sniper_unit.template.flags.canSniperCover: REJECT   // v1.4：资格门（原全军皆可当掩护者——特技归属失效）
    IF target_unit.team != sniper_unit.team: REJECT         // v1.6（⑳A）【按推荐拍板·可推翻】：目标侧校验①——与射手同队
                                                             //（GDD 第8节第1轮"可掩护一个友军单位"的"友军"限定落门；原可对敌方挂掩护、
                                                             // 消费端 covered 判定不分敌我，同时压低我方狙击对该敌目标的概率——自伤型误操作）
    IF NOT target_unit.alive OR target_unit.elements == []: REJECT   // ②——目标存活
    IF target_unit == sniper_unit: REJECT                   // ③——非自身
    FOR (tgt, protectors) IN world.cover_by_target 按插入序:
        IF sniper_unit IN protectors: protectors.remove(sniper_unit)   // 替换语义：新指令顶掉旧目标（"可掩护一个友军单位"——原可掩护全军）
    world.cover_by_target[target_unit].append(sniper_unit)  //（键不存在则建）

FUNCTION cmd_set_airdrop_beacon(world, unit, pos)           // v1.4：处理体补定义（原仅 §D.7 签名与 §F9 接口注释）
    IF NOT unit.template.flags.canAirdropBeacon: REJECT     // 资格门（渗透班/勃兰登堡）
    world.beacon_by_unit[unit] = pos                        // 不算暴露、不清渗透身份（§F9 接口约定不变）

// ── 烟弹发射（B4：烟=SMOKE 武器档案，唯一入口；不进自动选目标）──
FUNCTION cmd_smoke(world, element, point)
    // 数据规则（v1.3）：SMOKE 武器 target_mask 必须为 0（无 GROUND 位）——永不进 select_target 自动索敌，仅此指令入口
    ws = 首个 damage_type==SMOKE 且 READY 且 ammo_left>0 的武器
    IF ws == NULL OR NOT fire_permitted(world, element.unit, element, ws): REJECT
    IF dist_cm(element.pos, point) > ws.template.max_range_cm
       OR dist_cm(element.pos, point) < ws.template.min_range_cm: REJECT
                                                             // v1.6（③A）【按推荐拍板·可推翻】：烟弹补射程门——查 SMOKE 档
                                                             // max_range（min_range 同查），与直射武器同构（原 cmd_smoke 不查任何射程：
                                                             // Nebelwerfer 的烟火箭可对全图任意点发烟，130 分卡战术价值失衡——疑点⑧闭合；
                                                             // 推翻路径=全图发烟作设计特性保留，回写 R-06 并数值章节评估涨价）
    R = ws.template.dispersion_cm
    aim = point + (rng[SCATTER].sym(R), rng[SCATTER].sym(R))
    ws.ammo_left −= 1; ws.state = RELOADING; ws.timer = reload_time
    mark_resupply_if_needed(world, element.unit)           // v1.3（审查#11）：烟弹缺口同样登记
    // v1.7（GAP-26）：删 v1.5 M7 的 element.reveal_timer 写点——㉗A 拍板后曲射链统一"只留声测痕迹、
    //   不触发开火暴露"，烟火箭与 HE 火箭同弹道形态（BALLISTIC），"打 HE 不暴露、打烟反而隐蔽×0.4"
    //   对同一门 Nebelwerfer 自相矛盾、与 GDD v1.7 R-03 注记字面冲突。零风险烟幕 spam 由声测圈
    //   （下方 upsert_sound_track，曲射反炮博弈通道）制衡。〔拍板默认·可推翻：回"GAP-26 改B"恢复
    //   M7 reveal 写点并回写 GDD R-03/R-06 烟弹例外注记〕
    upsert_sound_track(world, element.unit, element.pos)   // v1.5（M7/G28）→v1.7（AMB-14/17②）：喂声测 R-03——
                                                             // 仅 w.trajectory==BALLISTIC 时执行（烟火箭喂、步兵烟罐 DIRECT 不喂）
    world.projectiles.append(Projectile(shooter=element, weapon=ws.template,
        profile=SMOKE, pos=element.pos, dest=aim, trajectory=ws.template.trajectory,
        hit_target=NULL, will_hit=FALSE))
                                                             // v1.7（AMB-17②）：弹道改档案读取——步兵烟罐配 DIRECT（投掷）、
                                                             // 火箭炮/迫击炮烟弹配 BALLISTIC（与声测喂入闸联动，AMB-14）。
                                                             // **数据硬要求（AMB-17① 拍板）**：步兵侦察排/斥候排须配 SMOKE 档案
                                                             //（ammo_base=2（烟罐×2/排，第8节第1轮）、近距 max_range、
                                                             // trajectory=DIRECT（投掷，不喂声测）、reveal_time_ticks=0）

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
        FOR e IN MECH 元素 WHERE dist_cm(e.pos, rep.pos) <= cfg.repair_radius_cm
                             AND e.unit.team == rep.unit.team
                             AND (hp<max OR (e.crit != NULL AND e.crit 非空)):
                                                             // v1.5（M24/A17）："贴靠"量纲成文=cfg.repair_radius_cm（D.0 新常数，默认 3000）——
                                                             //   原无量纲无结构判据，实现者无从落码；方案7：crit 判空
                                                             // v1.7（GAP-10）：补同队门——原无过滤，敌方受损坦克开进维修半径被逐 tick
                                                             //   修满血+清状态伤+自动解除拖曳对（为敌方"保车"，R-19 锚定己方）；
                                                             //   与同函数补给分支 :1252 的 R-21 同队门同构
            e.hp_current = MIN(hp_max, e.hp_current + repair_power)
            IF e.hp_current >= e.template.hp_max:
                e.crit.clear()                                    // D016 修满清状态伤
                FOR pair IN world.tow_pairs WHERE pair 涉及 e:
                    stop_tow(world, pair, REPAIRED)               // 修好即归队（R-19）——v1.7（GAP-24）：元素级（原 e.unit 级，
                                                             // 卡车队 3 对拖曳时修好 1 辆连带另 2 对解除）
    //（v1.1 尾部 world.supply_boxes 空投箱循环已删——方案16：空投箱落地即一次性 CARGO 单位，
    //  被上方 CARGO 分支自动覆盖）

FUNCTION spawn_airdrop_crate(world, team, pos, rounds, medical)      // 方案16：R-21 航空侧调用接口
    // 一次性补给箱模板（非卡组卡面）：speed_tier=0/move_path 恒空（不可移动）、装甲0、HP 小（可摧毁）、
    // 无行为 flags、**hasSupply 位必配（v1.7 终检 GAP-21）**（§D.5#16/17 物资槽为"仅 hasSupply 元素分配"
    // 的条件槽、§C#12 按模板 flags 派生——漏配则 e.supply_rounds/medical 不分配、system_supply :1250
    // 扫描条件对箱子恒假、无人能拾取，与 v1.3 crate supply_radius 漏配同族）；
    // **supply_radius_cm 必配 8000**（v1.3 审查：原规格漏配→按模板半径过滤的拾取链对箱子恒不触发，
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
        unit = instantiate(card, p.team, p.index, spawn_pos) // 元素/武器弹药全部满编；weapon_states.ammo_profiles_left
                                                             // 深拷贝模板计数（v1.5 M16——每门钨芯独立 3 发）
        // v1.3（审查#4）：R-07 开局车载默认形态——混编卡（装掷）班元素预挂随车（同卡只写 mounted_in）
        carriers = [e FOR e IN unit.elements IF e.template.seats > 0]
        squads   = [e FOR e IN unit.elements IF e.template.element_type == SQUAD]
        FOR (i, s) IN ENUM(squads): IF carriers[i] != NULL: s.mounted_in = carriers[i]
        IF flags.canInfiltrate: unit.infiltration_timer = (world.phase == 实战 ? 600 : 0)
                                                             // v1.6（④A）【按推荐拍板·可推翻】：spawn 不再一律置 600——渗透计时从
                                                             // 实战期起算（update_phase 迁入实战时对在场 canInfiltrate 卡统一置 600，§F8；
                                                             // 此处仅在出牌队列滞后到实战期 spawn 时补置同值）。原 spawn 即置 600：
                                                             // 渗透班最迟盲部署末购买、约 910 tick 边缘 spawn，1350 tick 实战开始时
                                                             // 60s 窗口被禁火期吃掉、实战内仅剩约 16 秒（早买为 0）——"敌后接应"不可达。
                                                             // 仅 canInfiltrate 卡分配此槽——方案8
        IF ANY(w.target_mask & AIR FOR w IN 全部武器) OR unit.template.optics_air_cm > 0:
            world.aa_roster.append(unit)                    // 方案2：对空名单登记（部署初始化=首批 spawn，运行时不重建）

FUNCTION system_objectives(world)                           // 每秒
    FOR obj IN world.objectives:
        占点半径内存活单位 ∩ 各队 → 仅一方存在时 obj.owner = 该队
```

---

## §F8. 主循环与计时器

```
FUNCTION update_phase(world)                                // v1.6（④A）：函数体补齐（原仅 world_tick 调用点、无定义体）——
                                                             // 相位推进 + 渗透计时实战起算
    按 phase_ticks 推进相位：盲部署(900) → 禁火(450) → 实战(13200) → 结算
    IF 本 tick 相位迁入实战:
        FOR u IN alive_units WHERE u.template.flags.canInfiltrate:
            u.infiltration_timer = 600                      // 渗透 60s 从实战期起算【按推荐拍板·可推翻——清单④A】——
                                                             // 对在场 canInfiltrate 卡统一置 600（spawn_step 侧配合：盲部署/禁火期
                                                             // spawn 置 0、实战期 spawn 补置 600），60 秒完整落进实战窗口；
                                                             // 推翻路径=放开实战期购买渗透卡或维持原状（卡面降价/删除该机制）

FUNCTION world_tick(world)                                  // 固定步长，10Hz
    world.tick += 1
    update_phase(world)                                     // 盲部署900→禁火450→实战13200→结算（定义体 v1.6 ④A 补齐于上）
    consume_commands(world)                                 // 命令驱动：本 tick 的命令全部落地
    system_timers(world)                                    // ①
    FOR unit IN world.units: system_move(world, unit)       // ② 移动（含随动）
    system_sensing(world)                                   // ③ 节流扫描
    FOR e IN 全体元素 WHERE e.template.fire_arc_deg < 360 AND e 有 rotating 槽:
        e.rotating = FALSE                                  // v1.7（GAP-25）：B04 第一条——每 tick 复位，rotate_step 当 tick
                                                             // 被调用时再置 TRUE；转向中断（目标毁/换目标/移动令）不再滞留 TRUE，
                                                             // "转过一次永久侧面"残余路径闭合（方案6 条件槽：360° 模板无此槽不扫）
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
    FOR z IN world.smoke_zones: z.ttl_ticks −= 1            // v1.5（M6/G27）：烟区 ttl 递减——原全文无递减行/无到期判定，
                                                             // world_tick 的 ttl_ticks>0 过滤恒真，Nebelwerfer 6 发烟火箭=6 个永驻
                                                             // SmokeZone，永久遮断新发现与校射收束（R-06 稀缺设计与 60 秒时限双双失真）

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
| g-建筑进驻 | §F6 cmd_garrison / collapse_building（v1.6 ⑨A 已拍板：隐蔽+3；受击判定简化[按尾甲]；§F3 canGarrison 前置短路，方案5） |
| g-载重混装 | §F6 buy_supplies 重量核算 |
| g-威胁值 | §F4 threat_value 可计算定义 |
| g-对空结算 | §F9 resolve_hit_aa 接口 |
| g-校射口径 | §F4.1 按发累积（fm.calib_progress，校射槽下沉任务体，方案10）；fire_direct 仅活跃任务期读收束（无任务=无收束，机制版同款） |
| v1.2-方案2 | 对空名单：§D.6 world.aa_roster + §F7 spawn_step 登记 + §F4 system_combat ② / §F3 sense_air 名单化 |
| v1.2-方案9 | 旁表：§D.6 beacon_by_unit/cover_by_target + §D.7 两命令写表 + §F1 掩护查表 + §F2 unregister_unit_refs 注销 |
| v1.2-方案19 | 事件补给：§F8 system_timers EMPTY 迁移登记 + §F2 needs_resupply/apply_damage 登记 + §F6 system_supply 扫描集合（速率/烟弹同轨原样）；v1.3 改缺口制（审查#11） |
| v1.3-审查修复 | 13 项问题：车载双扣血去重(#1)/声测圈阵营(#2)/上下车双向清理(#3)/装载SQUAD过滤+开局接线+sync笔误(#4)/工兵vs_fort直射+AttackCmd(#5)/道路机动(#6)/掩护1:1(#7)/卡车装载门+seats(#8)/对空拖曳门(#9)/TOW位补全(#10)/补给缺口制(#11)/拖曳元素级(#12)/校射视线定义(#13)；附属：FireMissionCmd处理体/use_self_defense复位/驻楼REAR/空投箱半径/烟mask规则/掩护空键删——详见文末 v1.3 变更记录 |
| v1.4-审查修复 | 17 项机械缺陷：**cmd_attack 处理体（high#1 半落地闭合）**、**cmd_toggle_ambush 处理体（high#2 R-12 整链复活）**、**队形偏移循环（high#3）**、rotate_step 笔误、TOW 位注记三处同步+迫击炮+牵引侧、cmd_tow 互斥门、start_tow 展开闸、装载链五缺口（I-19）、cmd_mount 最少挂载分配+在途占座+模式门改非{CARGO,TOW}、mark_level 重算式、驻楼×移动互锁、R-02 tally 实击杀、隐蔽常数×10 口径、FireMission.shots_fired+LINE 取样+POINT 专属校射、钨芯实例化深拷贝、声测生命周期三语义、特技资格两位+信标处理体；设计决策 12 项移交拍板清单 |
| v1.5-审查修复 | 机械修复 M1~M28 + **拖曳-展开-队形-声测联立解 C1~C5**（审查问题文档 v1.4 共 61 项中的机械部分；**5 条 blocker 全闭**：B01 手动指火补两道标记门（M5）、B02 声测键粒度+换位阈值（C4）、B03/B05 拖曳几何与末端断裂（C1/C2）、B04 rotating 死分支（M3））；未触及 G13/G25/A04/A07/A10/A11/A15/A16（设计决策/数据侧，待拍板清单 v1.5）——逐条对照见文末 §X 变更记录 |
| v1.6-拍板执行 | 拍板清单 v1.5 全 27 项 + 附表 5 项按推荐执行（存档 GDD-02-拍板清单-v1.6.md，逐项见文末 §Y）：**行为变更** ③ cmd_smoke 射程门（§F6）、④ 渗透计时实战起算（§F7/§F8 update_phase）、⑲ 狙击排除 MECH（§F4 select_target + cmd_attack 双门）、⑳ 掩护目标侧三门（§F6 cmd_set_sniper_cover）、㉑ 挂载粒度下沉班元素（§D.7/§F6 cmd_mount/mount_requests_step/载具占用数/§F2 撤销谓词）；**注记升级已拍板** ⑦⑨⑩⑪⑫⑬⑭⑯⑰⑱㉒㉓㉔㉕㉖㉗与附表 M4/M19/M20/M25/M26；**数据硬要求成文** ⑤（D.2 mm→0-20 换算锚）、⑧⑱（D.3#21 喷火×1.5 三处）、⑮（D.1#25 canAmbush 4 卡）、㉖（D.3#22 钨芯换算锚）、㉔（D.3#25 轻迫自卫档）；**终审修复 1b** cmd_deploy"禁止边拖边展开"门元素粒度（§F6）——公式链零改动项：⑭（表述）、㉗（曲射只留声迹） |

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
13. **方案13（三模式许可门按 mode_set 剔除，corroborated）**：fire_permitted 的 towed/mode 两道门改为先测 `unit.template.mode_set` 位，模板不含对应位则跳过该问（恒 DIRECT 卡每 tick 两问消除）。数据配置要求（v1.4 全量同步 D.1#15）：一切可作为被拖方的卡——中/重坦（R-19 维修拖曳）、轻防空（第11/12轮卡车牵引）、火支全部牵引炮与火箭炮、步兵类四门迫击炮排——以及**牵引侧卡**（坦克维修班/重型拖拉机排/豹式救援车）——mode_set 须含 TOW 位，漏配则"拖曳中禁射"失效（负面影响的荒诞画面风险已列；无运行时兜底为已接受代价）；R-19 双方禁射对称性由两门同测 mode_set 保证。
14. **方案14（疾跑改时间戳，corroborated/V9 删档）**：删 §D.5 sprint_timer 与 §D.0 sprint_mult_bp；§D.4 增 `sprint_until`（tick 时间戳）；§D.0 增 `sprint_duration_ticks`（待定）；SprintCmd 写 `sprint_until = now + sprint_duration_ticks`；move_speed 改为 `now < sprint_until` 时速度档+1（封顶 5，改挂 speed_table——sprint_mult_bp 表述随之作废）；system_timers 删 sprint 递减行（统一衰减循环多一个例外，整洁度代价已接受）。
15. **方案15（删除死字段 turret_traverse_deg_per_tick，single-pass）**：删 §D.2#7 定义行，D.2 重排为 14 字段（v1.1 全文确无消费点）；"无炮塔"语义由 fire_arc_deg<360 + turn_rate_deg_per_tick 完整承载。未来做"炮塔独立转速"需重新加字段（已接受）。
16. **方案16（空投箱改为一次性 CARGO 元素，single-pass）**：删 system_supply 尾部 `world.supply_boxes` 循环（该字段在 v1.1 即属"引用了但 §D.6 漏列"的文档缺口，删除后缺口消除）；新增 §F6 `spawn_airdrop_crate`（R-21 航空侧调用接口）：落地实例化为预填物资、不可移动、可摧毁的 CARGO 单位，进 units[]，被 system_supply 既有 CARGO 分支自动覆盖。**GDD-02 为准修正**：system_supply 补给对象补 `u.team == t.unit.team` 过滤（GDD-02 R-21"敌方不可拾取"，v1.1 内环漏队伍过滤）。一次性元素占 units 遍历槽的微增开销为已接受代价。
17. **方案17（军官"射程+10%"改拍板为纯精度加成，single-pass）**：伪代码维持仅 PRECISION 精度+10%（fire_direct 精度乘区原样），**不补** select_target 射程消费点；即 sketch 的"改拍板"档。GDD-02 第4轮"军官=精准光环：射程+10%、精度+10%"表述由本方案拍板废止为"精度+10%"——GDD-02 卡面与拍板记录需在 GDD 文档侧同步回写（本文不改 GDD，列入对齐清单）。德军军官走位站位价值下降为已接受代价。
18. **方案18（近卫"溃逃重整×2"以压制衰减近似，single-pass）**：§D.1#25 flags 增 `suppDecayX2`（近卫步枪排置位；旗标名与机制版 v1.2 同名——走查统一）；§F8 system_timers 压制衰减行按旗标 `decay×2`。卡面"溃逃重整×2"表述需在 GDD 侧改写为"压制恢复加倍"（列入对齐清单）；"溃逃→重整"两态表现丢失为已接受近似。
19. **方案19（弹药补给事件触发，single-pass）**：§D.6 WORLD 增 `await_resupply[]`；§F8 system_timers 补 RELOADING→EMPTY 显式迁移（v1.1 隐式转 READY 一并补全），EMPTY 时把单位登记入待补给集合；§F2 增 `needs_resupply`（登记/保持条件 = 任一武器 EMPTY 或任一步兵元素带伤——含带伤条件是为保住保留清单#9 的 R-18 医疗承载），apply_damage 命中带伤即登记；§F6 system_supply 主扫描由"半径内全单位"改为"在场 CARGO 卡车 × 待补给集合"，补给后自清理。**保留清单#10 原样落实**：`ammo_resupply_per_tick=2` 速率与烟弹同轨自动补逐字保留，EMPTY 补满转 READY。事件集合维护（登记/车毁清理/自清理）为已接受的逻辑分支增量。

### 对齐与保留清单记录（notApplied / GDD-02 对齐）

- **notApplied（GDD-02 为准的修正）**：system_supply 补给内环补 `u.team == t.unit.team` 队伍过滤（GDD-02 R-21"敌方不可拾取"，v1.1 遗漏）——随方案16 落地一并修正，见变更记录#16。
- **GDD-02 卡面回写清单（GDD 文档侧执行，本文不改 GDD）**：①军官光环"射程+10%"删除（方案17 拍板，GDD-02 第4轮）；②近卫"溃逃重整×2"改写为"压制恢复加倍"（方案18，GDD-02 第3轮）；③T-34/76 卡面 80 分改 70 分（第8节第5轮降价拍板、以第8节为准；数据配置以 70 入 cost 槽——v1.5 M27/A13 增补）。
- **保留清单十条全部未破坏**：start_tow/stop_tow 族、fm.target_line/creep_speed、SoundTrack 写侧、crit 的 MECH 侧、mark_level=CALIBRATED 消费链、requiresMark 门、vs_fort_mult_permille 字段、R-12 首击设计意图（置位点缺口仍为待拍板疑点，未顺手修复）、医疗 INFANTRY 分支、补弹速率与烟弹同轨。
- **方案文档 1.4 疑点清单未被 19 条方案触及者逐字保留**：疑点①（R-12 ambush_shot_bonus 无置位点）、②（vs_fort 直射不可达）、③（士气状态机，由方案18 近似处理近卫一卡，其余仍无锚）、④（use_self_defense 无复位行）、⑤（aa_try_engage 无 towed/mode 门）、⑥（军官射程光环，由方案17 拍板移除）、⑧（cmd_smoke 未查 min_range）、⑨（fire_at 不写 reveal_timer）、⑩（82mm 轻迫 self_defense 归属）、⑪（canAmbush 归属）、⑫（迫击炮可否领任务）——均维持 v1.1 口径，待另行拍板。
  - （v1.6 注：上条为 v1.2 时点状态、原文保留；其中疑点⑧已由拍板清单 v1.5 ③A 落地闭合[§F6 cmd_smoke 射程门]、疑点⑨由㉗A 闭合[§F4.1 fire_at 注记：曲射只留声迹成定案]、疑点⑩由㉔A 闭合[D.3#25 轻迫自卫档数据要求]、疑点⑪由⑮A 闭合[D.1#25 canAmbush 置位 4 卡成文]、疑点⑫由⑯A/附表 M26 闭合[D.1#15 INDIRECT 位数据硬要求]——见 §Y。）
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

---

## §W. v1.3 → v1.4 变更记录（审查问题文档-v1.3 的 29 项中 17 项机械缺陷修复；其余 12 项设计决策移交拍板清单）

> 审查产出：29 条（high 3 / medium 14 / ambiguity 12）。本版修复全部 3 条 high + 14 条 medium 中的机械部分；设计决策类（士气去留、烟遮断持续交火、烟弹射程、渗透时序、穿深换算、子配额分池、R-04 回写、喷火数值化、LINE/CREEP 校射、声测换位语义——其中后两项已按拍板默认落地）见 docs/GDD-02-拍板清单-v1.4.md。

1. **cmd_attack 处理体（high#1，v1.3 修复#5 半落地闭合）**：§F4 新增处理体（攻坚武器限建筑目标、就绪/许可/射程/射界四门 → begin_aim）；finish_aim 补 Building 失的判据——工兵×2/ISU 混凝土弹/OT-34/ML-20 直射拆楼入口可达，§V#5 闭合声明兑现。
2. **cmd_toggle_ambush 处理体（high#2，R-12 整链复活）**：§F4 新增（canAmbush 资格门；手动退出给首击加成、静止开启）——ambush_active 恢复 TRUE 写点，四张伏击卡的视野/隐蔽/首击/移动退出链全部生效。
3. **队形偏移循环（high#3）**：system_move 对非车载/非被拖元素执行 e.pos = 队形偏移(unit.pos)——射程门/弹丸起点/补给半径/声测圆心不再按出生坐标结算（对齐机制版 §2，§D.8 口径差消除）。
4. **rotate_step 笔误**：step = e.unit.template.turn_rate（原未定义变量 unit）。
5. **TOW 位注记三处同步（medium verified）**：D.1#15 / §C#13 / fire_permitted 注释统一全量枚举——被拖侧（+步兵类四门迫击炮排）+ 牵引侧（维修班/重拖/豹救）。
6. **cmd_tow 互斥门（medium）**：牵引元素须 mode==TOW 且不在拖——堵"载货卡车拖炮/一车拖两门/未切 TOW 拖曳中开火"三旁路。
7. **start_tow 展开闸（medium verified，I-20）**：拖曳将被拖单位强制回 MOBILE（作废展开进度）——解挂后须重新展开 30s，D065"到位后展开"成立。
8. **装载链五缺口（medium verified，I-19）**：mount_requests_step 到期复核（存活/模式/座位）；destroy_element 撤销进行中请求；cmd_set_element_mode 切出运载清挂起请求；同班重复申请去重；在途请求占座。
9. **cmd_mount 三修（medium）**：最少挂载元素分配（原固定首个→再上车全落 251#1）；座位账目含同卡 mounted_in 与在途请求；模式门由"须 TRANSPORT"改为"非 {CARGO, TOW}"——251 等无三模式位载具恒可载（R-07 车载开火不冲突），D065 互斥保留。
10. **mark_level 重算式（medium 新发现）**：每扫描按本轮接触观察者重算，无接触回落 NONE——侦察撤离/脱视野后校准加成与犀牛门同步失效（R-01"视野内"语义恢复）。
11. **驻楼×移动互锁（medium 新发现）**：system_move 移动自动出楼（cmd_un_garrison）——楼槽释放、加成终止。
12. **特技资格（medium 新发现）**：flags 增 canSniperCover/canAirdropBeacon 两资格位；两指令处理体补校验；cmd_set_airdrop_beacon 处理体补定义（原仅签名）。
13. **R-02 tally 实击杀（low 新发现）**：记 actual=MIN(kills, hp) 而非掷骰值。
14. **隐蔽常数 ×10 口径统一（low 新发现）**：D.0 两常数统一"×10 整型存储"（20/30），消费处统一 s += 常数（原两处写法相反，照表必错 10 倍）；机制版同步改 IMPL 式（加成后置乘区，两版隐蔽公式口径差消除）。
15. **FireMission.shots_fired（low）**：LINE 取样序号由任务体承载（原"已发射数"不可回推）；校射限 POINT 形式【拍板默认——GDD 校射锚在点射击，LINE/CREEP 落点无稳定校射点】。
16. **钨芯实例化深拷贝（low）**【拍板默认】：weapon_states 实例化时深拷贝 ammo_profiles——每门独立计数，"每门 3 发"承诺成立。
17. **声测生命周期三语义（low verified）**【拍板默认】：IntelCircle 键=声源单位（多炮多圈共存）；换阵地 accum 清零重定位；停火期 accum 不增长（圈冻结精度）。

**账目**：77 槽不变（flags 位段 +2 位、FireMission +1 任务体字段均不占槽）。武器 27 子字段不变。
**裁决记录（可推翻）**：#9 模式门改"非{CARGO,TOW}"（保 R-07 与 D065 双承诺）；#10 mark_level 重算式（R-01 字面语义）；#15/#16/#17 为拍板默认，均登记于拍板清单待确认。

---

## §X. v1.4 → v1.5 变更记录（审查问题文档 v1.4 的 61 项：机械修复 M1~M28 + 拖曳-展开-队形-声测联立解 C1~C5）

> 依据：docs/GDD-02-伪代码审查问题文档-v1.4.md（61 条 = blocker 5 / gap 32 / ambiguity 24）。本版按机械修复清单 M1~M28 逐条落实、按联立解架构规格 C1~C5 逐条实现（联立解为权威架构，未自行变体）。**5 条 blocker 全部闭合**（B01→M5、B02→C4、B03→C1/C2、B04→M3、B05→C2——与 §A v1.5 行及 C2/C3 条目引用一致：B05 三断裂点[整连冻结/unit.pos 冻结/解挂瞬移]均由 C2 闭合，与展开闸 C3 无关）。设计决策类不在机械清单内：A01/A03/A05/A08/A12/G01 按 M28 在原位加待拍板注记；G13/G25/A04/A07/A10/A11/A15/A16 未触及——已归档 docs/GDD-02-拍板清单-v1.5.md ⑬~㉗（终审修：清单已建册且全部落点，原"尚未成文"表述过时删除，M28 六处注记与 §X·四未触及项均改引实际条目号）。
> 证据行号说明：每条括注 v1.4 问题文档条目编号及其引用的 IMPL 行号（**行号为 v1.4 底本行号**，本版行号已随插入漂移）。

### 一、机械修复（M1~M28，逐条对应 v1.4 问题文档）

1. **M1 裸变量四族**：system_move 的 `ambush_active = FALSE` 改 `unit.ambush_active`（G10，:853——修复#2 复活后该行由死代码变活跃缺陷）；aa_try_engage 的 `unit.air_ceiling` 改 `e.unit.template.air_ceiling`（G20，:752——unit 不在作用域）；buy_supplies 三处 `truck.*` 改 `truck_element.template.*`（G21，:947-949）；indirect_role 的 `w_main.self_defense` 改 `w_main.template.self_defense`（含 ANY 行 max_range_cm 同族第二处，G30，:657-658）。
2. **M2 整除位置**：resolve_sniper_hit 概率式改 `sniper_base_prob_bp * (covered ? sniper_cover_mult_bp : 10000) // 10000`（整除外置——原内置三元：covered 分支 5000//10000=0 掩护=免疫、未掩护乘 10000 无掩护=必中）（G12，:335）。
3. **M3 rotate_step 死分支**：rotating 改按当前角差重算——每次调用重算 `|angle_diff(target_deg, e.facing)| > e.template.fire_arc_deg`，不锁存（原清除条件 |diff|<=step 与两调用点进入条件 |diff|>fire_arc 交集为空、rotating=FALSE 恒不可达，首次转向后锁存 TRUE→"转过一次永久侧面"）（B04，:863-869／消费 resolve_hit:321／调用点 :647-649、:734-736）。
4. **M4 finish_aim 失的判据与出口复核**：失的分支补 `(tgt is Building AND tgt.hp <= 0)`（G06/G29，:664-670——原注释宣称判据而表达式对 Building 恒假：塌楼窗口照常开火、弹丸携悬空引用二次结算）；AIMING 到期对地面武器复核 fire_permitted（拖曳/禁射/收装/切模中到期转 READY 不耗弹）（G32，:664-670——原只守入口不守出口）；对空复核 phase 门与（needs_deployed 时）C3 形式展开门（G02/G08，:593-598/:747-756——原对空链从不调用 fire_permitted，禁火期/未展开的机枪排与轻防空到期照常发射）。
5. **M5 cmd_attack 目标资格门**：Element 目标补 spotted_mask 含我队位、shooter 单位 requiresMark 置位时 target.mark_level >= SPOTTED（与 select_target 同谓词；Building 豁免——第8轮犀牛"仍需友军标记才能开火"在玩家最常用入口恢复生效，战争迷雾侧门关闭）（B01，:726-737 对 :619-623）；D.3#21 补数据硬要求 le.IG/ML-20 配 vs_fort>1000（G19，:729/D.3#21:156——照表默认 1000 则攻坚资格门对两卡恒 REJECT、直射拆楼不可达）。
6. **M6 烟雾区过期**：system_timers 增 smoke_zones ttl 递减行（G27，:1103-1120 无烟项、:1101 过滤恒真——烟区永驻、永久遮断新发现与校射收束）。
7. **M7 cmd_smoke 开火副作用**：补 e.reveal_timer 与 upsert_sound_track（与 HE 同发射器同声响——R-03/R-14"火箭炮最易被定位"对烟火箭同样成立，零风险打烟的口子关闭）（G28，:984-996，对照 fire_direct:693-694）。**〔v1.7 §Z-11 撤销 reveal_timer 写点（终检 GAP-26）：㉗A 拍板后曲射链统一"只留声测痕迹"，声测喂入保留——M7 登记理由"同发射器"被㉗A 对 HE 曲射的反转所瓦解〕**
8. **M8 fire_at salvo 与曲射档案**：读 w.salvo（每次 fire_at 发 salvo 发，弹药/任务计数按 salvo 增减、LINE 取样按批推进）（G11，:771-798——原每次恰 1 发，喀秋莎/Nebelwerfer 齐射退化为逐发隔装填滴流）；曲射 profile 明确 alt_profile 若存在否则默认 HE 档（双职炮曲射吃 HE 数值——原"默认HE"对 KE 主炮语义悬空）（A14，:795）。
9. **M9 HALF 弹量账目**：cmd_fire_mission 的 shots 对 HALF 用半数元素计算（与 process_fire_mission"前一半"同规则——原全连初值由半数炮发射：每门翻倍消耗、任务时长翻倍、打空后任务悬挂由弹药车续射）（G03，:805/:764）。
10. **M10 车载班不可直射**：select_target 候选与 cmd_attack 增 mounted_in != NULL 排除（乘员伤害只经车毁 60% 连带转移——R-07 设计前提恢复，对无武装运兵卡车尤甚）（G23，:617-628/:726-737）。
11. **M11 驻楼×上车互锁**：cmd_mount 先 cmd_un_garrison（挂载即出楼——原骑乘期持续吃驻楼隐蔽/尾甲、楼位被机动卡车远程占用）（G24，:898-907/:833-856）。
12. **M12 装载撤销谓词收窄**：destroy_element 撤销条件改 `r.carrier == elem OR NOT r.squad_unit.alive`（删 r.squad_unit != unit 过度撤销——同排他车被毁不再误杀在途请求）（G26，:446-447，修复#8 回归）。
13. **M13 卡车 DIRECT 口子收口**：cmd_mount 增门 `(carrier.template.mode_set & TRANSPORT) AND carrier.mode != TRANSPORT → REJECT`（mode_set 含 TRANSPORT 位的载具[卡车]必须处 TRANSPORT 才可载人；251 等无位载具不受限——"运兵+载货/拖炮并存"旁路关闭）（G18，:905/:932-937/:945）。
14. **M14 常数接线**：destroy_element 的 60% 改读 cfg.vehicle_death_crew_permille 公式（hp×(1000−cfg)//1000 向上取整）（G22，:438——原硬编码绕过 D.0"禁止写死数值"纪律）；D.0 删 r18_radius_cm（冗余——半径由模板 supply_radius_cm 单轨承载，注明默认 8000；原常数全文零消费、照表配置无效）（G22，:69/:1005）。
15. **M15 buy_supplies 重量式**：Σ均摊 改 `rounds × cfg.supply_round_weight + medical × med_weight_per_unit`（D.0 新常数 supply_round_weight=弹药池通用每发重量——原"Σ武器 ammo_weight 均摊"求和对象未定义、600 发与 120 份互斥核算无法照写）（G21，:946）。
16. **M16 钨芯落地**：weapon_states 增子字段 ammo_profiles_left（实例化时深拷贝计数——spawn_step 注记），select_profile 改读/减 ws.ammo_profiles_left、不再写模板（G15，§D.5#11:196/select_profile:672-684——v1.4 注释宣称深拷贝而代码仍递减共享模板，冻结账目亦无副本槽，纸面闭合）。冻结账目注明武器运行时子字段 +1。
17. **M17 飞机发现时效**：sense_air 增对偶清位（超出该队全部探测者[防空名单支+低空目视支]范围即清 spotted_mask 对应位，与地面 keep_range 同构——原仅 |= 无清位，进过一次半径永久"已发现"、"超半径不开火"被射程≤探测半径变相架空）（A23，:560/:563）。
18. **M18 cmd_deploy 计时边界**：deploy_timer 写入移入 IF MOBILE 分支内（A20，:878-880——原 DEPLOYING 期重复下达重置进度、PACKING 期下达不迁移状态却覆盖计时器为展开时长）。
19. **M19 伏击首击加成时效【v1.5 拍板默认】**：ambush_shot_bonus 在单位移动时一并清除（system_move；R-12 注记——原手动退出后携 130% 加成跨半场机动、加成与伏击位脱钩）（A21，:741-742/:702/:708/:853）。
20. **M20 自卫直射发现门【v1.5 拍板默认】**：indirect_role 自卫触发候选仅限 teamSpotted 敌元素（原对未发现单位自动还手=每门炮配免费近距探测器，削弱骑兵/渗透班"摸炮位留最低成本"克制链）（A09，:657-659）。
21. **M21 fire_mission 元素级清除**：cmd_set_element_mode 切非 INDIRECT 时仅当本单位已无任何 INDIRECT 元素才清 fire_mission（与 system_combat 推进条件 ANY(e.mode==INDIRECT) 粒度对齐——原 1 门切直射连带销毁另 1 门曲射任务）（A24，:941 对 :604）。
22. **M22 GUN 元素定义成文**：D.2 注明 GUN 元素 unit_type 按配卡归 INFANTRY（炮班：hp_max=炮班人数）或 MECH（自行炮架：hp_max=炮架血）（A22，D.2#2:122/D.2#3:123——R-02 减员/医疗过滤/squad_hp_factor 三处消费行为漂移收口）。
23. **M23 moving 谓词定义**：§T 成文 moving(u) := u.move_path 非空（有航点即视为移动；停靠=清空航点）（A19，:506/:520——原零定义零写点，BA-64/美洲狮豁免窗口与全类移动隐蔽×0.5 跨平台不确定）。
24. **M24 维修贴靠量纲**：D.0 新常数 repair_radius_cm（默认 3000），system_supply 维修分支用之（A17，:1019——原"贴靠"无量纲无结构判据，维修班/豹救 R-19 闭环无从落码）。
25. **M25 拖曳速度注记【维持现状——仅档位值】**：tow_speed_tier=1 维持（A18，D.0:49/§F5:930）。**v1.5 走查修**：C1 枚举扩 TOWING 后 :930 旧两值谓词 `ANY(x.towed == TOWED)` 不再命中牵引侧（牵引卡车拖曳中将按自身 4 档机动），违反 GDD-02 R-19:254"拖曳中：牵引车+被拖车均……速度最低档"（两版头部均载明机制语义冲突以 GDD-02 为准）——已补入 C1 同步清单并改为双态判 `ANY(x.towed IN {TOWING, TOWED})`，与机制版 v1.5 §2（anyElementTowed 含两态、牵引侧同降档）对齐；G07③"降速按元素粒度"（仅牵引/被拖元素各自降档）未采纳，判定维持单位粒度并登记 §X·四（放开须拍板并回写 R-19）。
26. **M26 迫击炮 INDIRECT 数据硬要求【v1.5 拍板默认】**：D.1#15 注记追加步兵类四门迫击炮排 mode_set 须含 INDIRECT 位并可领 FireMissionCmd（与 TOW 位先例同格式——漏配则"可校射收束"乃至全部曲射 HE 静默失效且无报错）（A02，:102/:783-788/:800-808）。
27. **M27 T-34/76 价格**：GDD 回写清单增补第 5 轮降价 80→70 以第 8 节拍板为准（§C 回写清单③；数据配置以 70 入 cost 槽——伪代码承载核验成立，非伪代码缺陷）（A13，卡面 :164 对 第8节 :386-387）。
28. **M28 待拍板注记（不改伪代码）**：canAmbush 置位清单（A03——cmd_toggle_ambush 注记，三遍共识推荐 4 卡）、近战"必中"与精度链矛盾（A01/A06——D.3 档案示例注记）、政委"冲刺速度+1档"无承载（G01——D.1#24 注记）、对空威胁=最近未经决策确认（A05——aa_try_engage 注记）、OT-34"高重伤率"（A12——D.3#21 注记，⑱ 并入⑧执行范围）、狙击对车辆语义（A08——resolve_sniper_hit 注记）——六处注记均指向拍板清单 v1.5 实际条目（A01/A06→⑭、A03→⑮、G01→⑬、A05→⑰、A12→⑱、A08→⑲；终审修：清单已建册，原"清单待编"表述删除）。

### 二、拖曳-展开-队形-声测联立解（C1~C5，v1.5 权威规格逐条实现）

> 根因：单位级/元素级作用域不一致——v1.4 的 5 条 blocker 中 B02/B03/B05 与 G04/G07/G09/G16/G17/G31/G32 同源于此族。统一方案两版伪代码必须同构实现（机制版 v1.5 同步改造）。

1. **C1 towed 枚举扩 NONE/TOWING/TOWED**：start_tow 对牵引元素置 TOWING、被拖元素置 TOWED；stop_tow 双方回 NONE；fire_permitted 的拖曳禁射门改 `e.towed IN {TOWING, TOWED}`。随枚举同步（保持既有语义不回退的必然推论，非变体）：aa_try_engage 对空拖曳门改双态判（原 == TOWED 在新枚举下漏拦牵引侧防空——v1.3#9 语义保持）；cmd_tow/start_tow 的已挂判据改 `!= NONE`（TOWING 元素不可再挂新拖）；move_speed_cm_tick 拖曳降速判定改双态判（走查修——原 == TOWED 漏牵引侧，违反 GDD-02 R-19:254"双方最低档"，见 M25 条）。D.5#13 枚举行同步（B03，:470-471/:849/:613；机制版 §2:177-183 同根）。
2. **C2 system_move 作用域修正**：删"任一元素被拖即整单位 RETURN"早退，改**仅当单位全部元素都 TOWED 时才不自主移动**；队形偏移循环更新 **pos 与 facing 两维**（facing = 主元素朝向——G14 副车受弹面/射界随动一并闭）；覆盖条件改 `towed != TOWED`（TOWING 牵引元素正常随本单位移动——B03 牵引元素坐标冻结根因拔除）；被拖元素 pos 由拖曳随动分支负责（跟随其 pair 首牵引元素）；随动分支并对全被拖单位同步 unit.pos（B05②③ 闭合：侦测/占点/R-18 补给半径不再按拖曳前旧位置结算，解挂后队形循环不回跳抛锚点坐标）（B03/B05/G07/G14，:835/:847-850/:854-855）。
3. **C3 展开闸元素粒度**：单位级 deploy_state 不再被 start_tow 重置（见 C5）；新增元素运行时条件槽 **redeploy_needed**（仅 GUN/可被拖 MECH 元素分配，默认 FALSE，§D.5 工3）：start_tow 置 towed_element.redeploy_needed = TRUE；fire_permitted 的 needs_deployed 门改 `unit.deploy_state == DEPLOYED AND NOT e.redeploy_needed`；cmd_deploy 清除本单位全部元素的旗；stop_tow 不清除（解挂后须重新展开）；cmd_deploy 增门"单位内无 TOWED 元素"（禁止边拖边展开——G17 旁路闭合）。**槽位账目 77→78（+1 条件槽）**，头部账目行注明（G04/G09/G17，:472-474/:610/:878-880）。**【v1.6 终审修复 1b 修订·可推翻】**："禁止边拖边展开"门自本版起**删除单位级 ANY 门、落地元素粒度**——展开作用域限于非 TOWED 元素、被拖元素保持 redeploy_needed=TRUE 待解挂后重展开，cmd_deploy 清旗范围随之收窄为 `towed != TOWED` 元素（留守门可展开；G17 旁路由被拖元素的 redeploy_needed 旗闭合，见 §F6 cmd_deploy 正文）——v1.5 该门维持单位级 ANY 系 C3 规格原文、当时以"不擅改"注记登记，按终审指令本版废除该注记并修订本规格（机制版 §17.2 联立解 3 与 GDD 待同步第 19 条由机制版定稿员同步）。
4. **C4 声测三语义落地为结构（不再只是注释）**：SoundTrack 增字段 last_fire_tick（及键字段 listening_team）；upsert_sound_track 补函数体——按 (侦听队, 开火单位) 键 upsert，IF 新开火位置与 track.pos 距离 > sonar_move_reset_cm（D.0 新常数，默认 = sonar_max_radius_cm 之半）：accum = 0（换阵地重定位）；每次更新 pos 与 last_fire_tick。sonar_step 增门：仅当 world.tick − track.last_fire_tick <= sonar_hold_ticks（D.0 新常数，默认 100）才增长 accum（停火期圈冻结）。IntelCircle 增键字段 source_unit；upsert 按 (team, source_unit)——多炮多圈共存、同炮更新其圈（fire_at 按圈取 MAX 的消费前提成立）。**圈粒度为开火单位（连级）而非单炮：同连多门炮分散阵位共用一圈，R-03 语义按连解释**（B02/G05/G16/G31，:213/:565-580/:694/:794/:779-781）。
5. **C5 同步删除 v1.4 已废弃的单位级重置行为**：start_tow 不再写 unit.deploy_state / deploy_timer（G04/G09，:472-474——原"拖走一门炮整连带收炮"：留守已展开炮被强制 MOBILE、needs_deployed 门即时禁射，须整连重走 30 秒；v1.4 §W#7 展开闸承诺由 C3 元素级旗重新承载）。

### 三、【v1.5 拍板默认】与维持现状清单（单列，可推翻）

> **v1.6 注**：下列五条经拍板清单 v1.5 文末附表逐条确认，注记已全部升级为"已拍板"（2026-09-28 存档，可推翻——推翻通道见清单 v1.6 附表各行）；本节为 v1.5 时点记录、原文保留。

- **M19 伏击首击加成随移动清除**（A21）：R-12 字面两读，取"加成与伏击位绑定"读法——移动即失效，防"退出后携加成跨半场机动"。
- **M20 自卫直射仅对已发现元素触发**（A09）：取"自卫遵守发现门"读法——保住骑兵/渗透班"摸炮位留最低成本"克制链。
- **M26 步兵类四门迫击炮排 mode_set 须含 INDIRECT 位并可领 FireMissionCmd**（A02）：与 TOW 位数据硬要求同格式的成文要求数据侧执行，保"可校射收束"可达。
- **M25 拖曳速度维持锁 1 档**（A18）：档位值 1 不改；拖曳中**双方**（牵引 + 被拖单位）均按 1 档——:930 双态判（TOWING/TOWED 均命中），R-19/GDD-02:254"双方最低档"语义成立；"卡车快速转场"优势由其未拖曳时的自身高速度档承载；若要牵引侧拖曳中不降档或元素粒度降档（G07③），须拍板并回写 R-19，不得以"维持现状"名义变更行为。
- **M4 对空出口复核采用"最小许可集"**（G02/G08 修改建议原样）：phase 门 + needs_deployed 时的展开门；stance/mode 豁免维持 R-17 原语义（对空恒自动），不套用全量 fire_permitted。

### 四、账目与未触及项

**账目**：**78 槽** = 单位静态 30 + 单位运行时 17 + 元素静态 14 + 元素运行时 15 + 工程槽 1（garrison_in）+ 条件槽 1（**redeploy_needed**，C3——77→78）。武器 27 子字段不变；**weapon_states 运行时子字段 +1**（ammo_profiles_left，M16）。D.0 常数：删 r18_radius_cm（M14）；增 supply_round_weight（M15）、repair_radius_cm（M24）、sonar_move_reset_cm / sonar_hold_ticks（C4）。头部账目行同步。

**未触及项（不在本轮清单，已归档拍板清单 v1.5）**：G13（狙击掩护目标侧无校验——可对敌方挂掩护）、G25（挂载粒度单位级——seats=1 载具被塞 3 班、去重锁死分流）、G07③（拖曳降速元素粒度——本版按 GDD-02 R-19"双方最低档"取单位粒度 ANY 双态判定，未采纳问题文档"仅牵引/被拖元素各自降档"建议；放开须拍板并回写 R-19）、A04（火箭炮 90 秒/轮再装填无槽）、A07（猎兵"林地荫蔽+2"专属/通用）、A10（轻迫击炮自卫档案归属）、A11（追猎者近防 MG 武器级射界槽）、A15（钨芯"穿7"绝对值 vs 相对加值 +3 的基准锚定）、A16（曲射是否触发开火暴露——M7 仅落 cmd_smoke 烟弹侧，fire_at 的曲射暴露半边维持 v1.4 现状）。（终审修：清单已建册——条目映射 G13→⑳、G25→㉑、A04→㉒、A07→㉓、A10→㉔、A11→㉕、A15→㉖、A16→㉗。）
（**v1.6 注**：上列八项已在 v1.6 按拍板清单 v1.5 对应条目推荐全部执行——⑳A 补掩护目标侧三门[§F6]、㉑A 挂载粒度下沉班元素[§D.7/§F6/§F2]、㉒A 接受全局速率近似[D.0 注记]、㉓A 林地荫蔽通用化+TERRAIN.stealth_add 处置注记[D.0]、㉔A 轻迫配自卫档[D.3#25]、㉕A 接受共 ±15° 弧[GDD 第8轮拍板处注明]、㉖A 钨芯换算锚[D.3#22]、㉗A 曲射只留声迹[§F4.1 注记]——逐项见 §Y；本段为 v1.5 时点记录、原文保留。）

### 五、终审修复（第三遍独立终审，联立解语义正确性与过度删减复核）

> 终审五条中三条为 IMPL 侧已修（下列 1~3）；另两条非本文件范围：机制版 §4.4 正文"威胁最高者"措辞与【拍板默认】最近自相矛盾（终审问题 3，mech 侧待改）；GDD-02 R-03:24 "圈随侦听时长收窄"字面与实现"随开火时长增长、停火冻结"两口径（终审问题 5，拍板清单⑫已按后者选边可推翻，GDD 回写时二选一并注明）。终审另确认：清单外过度删减未发现（IMPL v1.4→v1.5 无函数消失、章节行数不减、删除行均有 §X 在案）；联立解场景走查通过项（留守门保持 DEPLOYED 可开火、被拖门拖曳中禁射、牵引卡车 TOWING 随本队移动/禁射/降 1 档、声测四段场景行为符合 R-03/⑫）。

1. **cmd_deploy 解挂重展开时长承载（高）**：cmd_deploy 增 ELIF 分支——`deploy_state == DEPLOYED AND ANY(e.redeploy_needed)` 时回 DEPLOYING 并重置 deploy_timer。原实现对 DEPLOYED 单位只清 redeploy_needed 旗（零成本）：C5 使"拖走 1 门"时单位保持 DEPLOYED，被拖门解挂后下 DeployCmd 即时恢复开火、30 秒重展开不存在，与 C3 自身注释"解挂后须重新展开才可开火"直接矛盾；v1.4"被拖单位须 MOBILE"门随 C5 删除后无替代闸，本分支即替代闸（§F6 cmd_deploy；对照机制版 v1.5 §10 同口径待改——mech 侧）。附带同源粒度问题（TOWED 门单位级 ANY 使 MOBILE 炮连部分拖曳期间留守门不可展开）——**v1.6 已按终审指令落地元素粒度【可推翻】**：删除单位级 REJECT 门、展开范围限于非 TOWED 元素、被拖元素保持 redeploy_needed 待解挂后重展开（"仅被拖门不可展开、留守门可"；G17 旁路由元素旗闭合），v1.5"按 C3 规格原文维持、不擅改"注记废除，C3 规格与 §D.5 工3 同步修订——见 §F6 cmd_deploy 与 §Y·四 FIX-1b。
2. **sonar_step 累计式裸引用（中）**：`MAX(sonar_rate)` 改 `MAX(s.template.sonar_rate FOR s IN listeners)`——sonar_rate 是声测班模板字段（D.1#22/23），原无作用域裸引用不可求值；与机制版 §3.D 写法同构（M1 裸引用族漏网，M28 未收录）。
3. **拍板清单 v1.5 互引状态更新（低，清单 :215 已登记的文档债）**：删除"尚未成文/清单待编"过时表述——头部上游行、§X 头注、M28 条、§X·四与正文六处待拍板注记全部改引 docs/GDD-02-拍板清单-v1.5.md 实际条目号（⑬~㉗ 映射见上）。（v1.6 注：本条为 v1.5 时点记录；v1.6 进一步把全部"待拍板"注记升级为"已拍板"并指向执行存档 docs/GDD-02-拍板清单-v1.6.md——见 §Y·四 FIX-4。）

---

## §Y. v1.5 → v1.6 拍板执行记录（拍板清单 v1.5 全 27 项 + 附表 5 项 + v1.5 终审修复 5 项）

> **依据**：docs/GDD-02-拍板清单-v1.5.md（27 项设计决策 + 文末附表「v1.5 已按默认落地项」5 条）；执行存档：docs/GDD-02-拍板清单-v1.6.md（每项 ✓ 已按推荐执行，2026-09-28）。
> **执行规则**：每项按文中标注的「推荐」选项执行；推荐即"确认已落地默认"的（⑩⑪⑫⑯ 及附表 5 条）仅将注记升级为「已拍板」；清单外事项一律未动。每条标注【按推荐拍板·可推翻】与清单条目号；推翻通道见清单 v1.6 各项（回复"条目号改B"即出补丁版）。
> **本文件纪律**：GDD 正文回写由 GDD 回写员执行、机制版同步由其定稿员执行（本文不改他文件，跨文件待办登记于 §Y·五）；清单推荐与 GDD-02 正文冲突处以清单推荐为准。
> **槽位账目**：v1.6 零槽位变更——78 槽维持（㉑A 请求体扩为列表不占槽、⑧A 走 damage 数值不加武器子字段、㉒A 不加补弹速率槽）；武器 27 子字段、weapon_states 运行时子字段 +1（ammo_profiles_left）维持。
> **v1.6 独立终审处置（2026-09-28 第二轮，8 条）**：涉本文件者 5 条已修——问题 1（FIX-1b 授权链）：§F6 cmd_deploy 与 §Y·四 补引在库指令源（主控脚本 FIX5 第 1 条第二分句）并登记清单侧追认待办；问题 2（回写完成度状态）：§Y·五 头部加"待执行派发"状态口径注；问题 3（可推翻标注破缺）：登记机制版三处补标待办；问题 4（④A 与 GDD R-04 残留矛盾）：§Y·一④行登记 GDD 同步项；问题 7（⑮A 落点标签失准）：§Y·二⑮行及 §Y·五机制版⑤更正为"机制版 §2 toggleAmbush 注记"。问题 5/6/8（机制版同步第 10 条 GDD 未改写、§17.3 镜像未执行、通过项备案）不涉本文件载体，由机制版/GDD/清单写手在其名下文档处置。

### 一、清单 ①~⑫（v1.4 遗留 12 项）

| 条 | 推荐 | 本文件（IMPL）落点 | 跨文件 |
|---|---|---|---|
| ① | A 回写 GDD 删除 | 零改动——士气系统 v1.1 裁剪以来零承载（无 morale 槽/函数），无注记需升级 | GDD：删四处士气表述（近卫/国民掷弹兵/政委/军官基础光环） |
| ② | A 保持现状（首版） | 零改动——烟仅遮新发现（detection_range 穿烟衰减）与校射收束（point_in_friendly_vision），keep_range 与 fire 精度链无烟项 | GDD：R-06 补一句注记 |
| ③ | A 补 max_range 校验 | **行为变更**：§F6 cmd_smoke 增 SMOKE 档 max_range/min_range 双侧射程门（与直射武器同构；Nebelwerfer 全图任意点发烟的失衡口关闭；方案文档疑点⑧闭合） | — |
| ④ | A 渗透计时实战起算 | **行为变更**：§F7 spawn_step 不再一律置 600（盲部署/禁火期置 0、实战期 spawn 补置 600）+ §F8 新增 update_phase 函数体（迁入实战对在场 canInfiltrate 卡统一置 600）+ §D.4#13 置位点注记 | GDD：R-04 首句"进场后前 60 秒额外隐蔽加成"须随行为同步为"实战开始后前 60 秒"（清单④A 未派发回写——独立终审指认残留矛盾，登记回写员执行） |
| ⑤ | A 定全表换算规则 | 数据侧成文：§D.2#4-5 增 mm→0-20 换算锚（0-20 刻度 ≈ 0-400mm RHA，90mm→约 4~5，覆盖装甲与穿深全部卡面 mm 值） | 数值章节定细则表 |
| ⑥ | A 不分池、总和校验 | 零改动——validate_deck 对 MAIN+RESERVE 总和校验即推荐现状 | GDD：删"（主力）"标注 |
| ⑦ | A 执行回写 | 注记升级：§F4 fire_direct 渗透清零注释改"已拍板"（狙击/近战清、普通自卫不清；原"语义以 IMPL 为准"改引⑦A） | GDD：R-04 回写 |
| ⑧ | A 改锚为直接伤害系数（+⑱ 扩三处） | 数据侧成文：§D.3#21 注记——喷火武器三处（工兵喷火器两卡 + OT-34 主武器）对 INFANTRY ×1.5 **由高 damage 数值承载**（不新增 vs_infantry_mult 槽、保 27 子字段冻结账目；⑧A 双路径取"数据表达"侧——**子选择可推翻**：改加 vs_infantry_mult 槽即破武器子字段账目，须连带 ㉕B 类复核）；对 MECH 同值伤害由数值章节复核 | GDD：卡面"高重伤率"表述改写（三处） |
| ⑨ | A 现状即答案 | 注记升级：§F6 驻楼头注与 §A g-建筑进驻行——隐蔽+3；受击判定简化[按尾甲] | GDD："建筑进驻加成"定义回写、勾销同步清单⑤ |
| ⑩ | 确认落地默认 | 注记升级：§F4.1 fire_at"校射仅 POINT 形式"→已拍板（推翻须定义线的校射点语义） | — |
| ⑪ | 确认落地默认 | 注记升级：§D.3#22 与头部账目行——钨芯每门独立计数（深拷贝 ammo_profiles_left）→已拍板（推翻=改全连共享 3 发） | — |
| ⑫ | 确认落地默认 | 注记升级：§F3 C4 块——换阵地 accum 清零重计、停火期圈冻结 →已拍板（推翻=换阵地结转精度，改 upsert 分支；R-03 回写按此选边，见 §Y·四 FIX-5） | GDD：R-03 口径回写 |

### 二、清单 ⑬~㉗（v1.5 补录 15 项）

| 条 | 推荐 | 本文件（IMPL）落点 | 跨文件 |
|---|---|---|---|
| ⑬ | A 拍板裁剪+回写 | 注记升级：§D.1#24——政委"冲刺速度+1档（持续型）"确认裁剪（不补承载），突击光环收敛为纯近战+15% | GDD：功能细则 :375 删该成分（与爆破+50% 同批） |
| ⑭ | A 改表述（不改公式） | **表述变更、公式链零改动**：§D.3#11 与档案配置示例——"必中"改写"基础必中、受压制衰减"（accuracy_base_bp=10000 基础值 × aim_factor 压制惩罚维持；保"压制克制近战冲锋"方向） | GDD：冲锋枪排/骑兵排两卡面注记；机制版成文同步 |
| ⑮ | A 明文 4 卡置位清单 | **成文**：§D.1#25 flags 增 canAmbush 置位数据硬要求（置位=SU-85/三突G/四号歼击车/追猎者；SU-76/ISU-152/犀牛不置位——同 TOW 位先例格式）；§F4 cmd_toggle_ambush 待拍板注记升级。清单原文落点为"机制版 D.1#25"——IMPL 侧同步成文以保两版同构（**落点扩展可推翻**） | 机制版：实际落点为其 §2 toggleAmbush 注记（清单原文"机制版 D.1#25"系沿用 IMPL 表编号的标签误标——独立终审指认，本行更正；实质成文两版在位，仅标签不准） |
| ⑯ | A 确认数据硬要求 | 注记升级：§D.1#15 M26——四门迫击炮排 INDIRECT 位数据硬要求 →已拍板 | — |
| ⑰ | A 确认『最近』 | 注记升级：§F4 aa_try_engage——对空威胁=最近（MIN by dist_cm）维持零改动 →已拍板，口径差以注记显式化 | GDD：R-17 注记（后续可换威胁加权表，留翻案接口） |
| ⑱ | 处置（并入⑧） | 无独立落点——原⑧执行范围已扩至三处（见上） | — |
| ⑲ | A 排除 MECH | **行为变更**：§F4 select_target 候选增 `(combat_style != SNIPER OR unit_type != MECH)` 剔除 + cmd_attack 指火门同谓词双承载；§F1 resolve_sniper_hit 注记升级（"全部元素"回退仅对无班元素的 INFANTRY 单位[如牵引炮班]可达，绕甲击毁侦察车/卡车路径关闭）。清单措辞"target_mask 剔 MECH"——target_mask 为 GROUND/AIR 位掩码无 MECH 位，落为 SNIPER 武器目标过滤双门（**语义等同、落点选择可推翻**） | GDD：R-02 回写"狙击目标均为人员" |
| ⑳ | A 补目标侧校验 | **行为变更**：§F6 cmd_set_sniper_cover 增三门——与射手同队 / 目标存活 / 非自身（"友军"限定落门，自伤型误操作兜底；纯缺陷闭合零数值影响） | — |
| ㉑ | A 粒度下沉班元素 | **行为变更/结构重构**：§D.7 MountCmd 请求体扩为 squad_elements[]；§F6 cmd_mount 逐班选最少挂载载具、逐班占座、去重按班元素（单班门失败 CONTINUE 跳过、全败才整体 REJECT——**逐班跳过语义为派生子选择，可推翻**）；mount_requests_step 条目改 {squad_element, carrier, ticks_left}（到期逐班挂载）；载具占用数改按 mounted_in 班元素指针计座（同卡+跨卡统一，1 班=1 座）；§F2 destroy_element 撤销谓词随元素粒度。cargo_units 保留为单位级登记（跨卡随动/清理），座位实账走 mounted_in——同单位多班挂同车不重复入表（**子设计可推翻**）。零新槽（清单影响注明"请求体扩为列表，无新槽"）；R-07"3班随4×251"与 D065"运兵模式载1个班"双承诺恢复 | — |
| ㉒ | A 接受全局速率近似 | 注记升级：§D.0 ammo_resupply_per_tick=2 维持（火箭炮 90 秒/轮量级由弹药车配比与再补给节奏承载，不加槽） | GDD：R-14 数值表述回写 |
| ㉓ | A 通用化 | 零行为改动（全局 forest_stealth_add 全体步兵林内 +2 即现承载）；§D.0 TERRAIN.stealth_add 死字段处置注记成文（留作地图差异钩子或删，数值章节定） | GDD：§2.2 删猎兵卡面字段行 |
| ㉔ | A 轻迫配自卫档 | 数据侧成文：§D.3#25——82/81 轻迫主武器配 self_defense 冲锋枪班自卫档（与 R-15 同族；疑点⑩自 v1.2 在册闭合） | — |
| ㉕ | A 接受共 ±15° 弧 | 伪代码零改动（fire_arc_deg 元素级单值语义维持，追猎者 MG 与主炮共弧） | GDD：第8轮拍板处注明 |
| ㉖ | A 写明换算式 | 数据侧成文：§D.3#22——钨芯最终穿深=7；pen_bonus=7−基准 pen_max（PaK38 基准=4，即 +3）；与⑤换算锚衔接 | 数据字典同式成文 |
| ㉗ | A 明文『曲射只留声迹』 | 零行为改动（fire_at 不写 reveal_timer 维持）；§F4.1 注记升级成文（曲射反炮博弈走声测圈，烟/位移为炮位生存手段；疑点⑨自 v1.2 在册认领闭户） | GDD：R-03 注记回写 |

### 三、附表 5 项（M19/M20/M25/M26/M4——落地默认注记全部升级「已拍板」，2026-09-28 存档、可推翻）

| 项 | 落点（注记升级处） | 可推翻方向（附表原文） |
|---|---|---|
| M19 伏击加成随移动清除 | §F5 system_move | 改时限失效 / 恢复"无失效条件"原状 |
| M20 自卫发现门 | §F4 indirect_role | 明文"自卫为条件反射不需发现"（渗透/骑兵摸炮位变难） |
| M26 迫击炮 INDIRECT 位 | §D.1#15（同清单⑯A） | 走⑯B——删 GDD:118 特技并另定义曲射入口 |
| M25 拖曳速度锁 1 档 | §D.0 tow_speed_tier | 改拖曳速度规则（动 D.0 常数与 moveSpeed 消费式并回写 R-19） |
| M4 对空出口复核最小许可集 | §F4 finish_aim | 套用全量 fire_permitted（改 R-17"对空恒自动"承诺） |

（§X·三为 v1.5 时点单列记录、原文保留，已加 v1.6 总注指向本表。）

### 四、v1.5 终审修复 5 项（核查与补齐）

1. **FIX-1a cmd_deploy 解挂重展开时长**：核验**已落地于 v1.5**（§F6 cmd_deploy ELIF 分支——DEPLOYED 且 ANY(redeploy_needed) 回 DEPLOYING 重置 30 秒计时），本版保留无改动。
   **FIX-1b「禁止边拖边展开」门元素粒度**：核验 v1.5 **未落地**（单位级 ANY 门 + "系 C3 规格原文、不擅改"注记仍在，与终审指令"仅被拖门不可展开、留守门可"相反）——本版按终审指令选项 (i) 落地：删除单位级 REJECT 门、展开作用域限于非 TOWED 元素、被拖元素保持 redeploy_needed=TRUE 待解挂后重展开（清旗循环收窄为 `towed != TOWED`）；G17 旁路由元素旗闭合（拖运途中下 DeployCmd → 被拖元素旗不清 → 解挂后仍须走 ELIF 分支重展 30 秒方可开火）。同步修订：§F6 cmd_deploy 正文、§D.5 工3、§X·二.3（C3 规格）、§X·五.1（"不擅改"句废除）。**可推翻**：翻案即恢复单位级门（须整连先解挂再展开）。
   **授权链补引（v1.6 独立终审问题 1 处置）**：本项系 27 项清单外的行为变更，授权源**在库可核**——docs/.zcode/workflow-runs/dwfrun-23ebdd22-dbc0-4555-b8b1-27def7ced52a.mjs（v1.6 拍板定稿主控脚本）FIX5 第 1 条第二分句原文「且"禁止边拖边展开"门改元素粒度（仅被拖门不可展开，留守门可）」（先行核查员 findings 之修法(i) 经主控任务书同达）；v1.5 两版"不擅改"注记即被该指令推翻的旧决定。为闭合"越权变更"指认：拍板清单 v1.6 须补一条 FIX-1b 登记/追认条目（**跨文件待办，清单存档员执行**——见 §Y·五）。
2. **FIX-2 声测累计式**：核验**已落地于 v1.5**（§F3 sonar_step `MAX(s.template.sonar_rate FOR s IN listeners) × acoustic_signature`——v1.5 终审修[中]行内），本版无改动。
3. **FIX-3 机制版对空措辞**：非本文件范围——机制版 §4.4 正文"威胁最高者"与"最近"默认统一（mech 定稿员执行），登记于 §Y·五。
4. **FIX-4 互引状态**：v1.5 已删"尚未成文/清单待编"；本版进一步把全文"待拍板清单 v1.5 ⑬~㉗"类注记升级为"已拍板——清单 XXA"，头部上游行指向执行存档 docs/GDD-02-拍板清单-v1.6.md（§X·五.3 加 v1.6 注）。
5. **FIX-5 R-03 回写选边**：非本文件范围——GDD R-03:24 按⑫A 选边回写"圈随开火时长增长、停火冻结"（GDD 回写员执行；本文 §F3 C4 块注记已载该口径为拍板定案）。

### 五、跨文件同步待办（登记，非本文件范围——机制版定稿员 / GDD 回写员 / 清单存档员执行）

> **状态口径（v1.6 独立终审问题 2 处置）**：本节所列均为**待执行派发**，完成度以各目标文档自己的 v1.6 执行记录为准，不因本文登记而视为已执行——独立终审核实：GDD v1.6 执行记录自记机制版同步第 11~22 条为"未回写、留待下一轮"，而机制版 v1.6 将其 GDD 待同步清单全 40 条标注"已回写 v1.6"——该状态矛盾属机制版/GDD 侧收敛事项；本文按"未回写"口径维持下列派发清单原样。

- **拍板清单 v1.6（清单存档员执行）**：① 补一条 FIX-1b 登记/追认条目——"cmd_deploy『禁止边拖边展开』门元素粒度（仅被拖门不可展开、留守门可）"系 27 项清单外行为变更，授权源为 v1.6 定稿主控脚本 FIX5 第 1 条第二分句（在库：docs/.zcode/workflow-runs/dwfrun-23ebdd22-dbc0-4555-b8b1-27def7ced52a.mjs），按独立终审问题 1 的"补拍板登记"路径追认并可推翻（独立终审问题 1 处置）；② 登记口径说明②（机制版 §17.3 缺 M25/M4）随机制版执行后同步更新（独立终审问题 6）。
- **机制版（GROUND_UNITS_PSEUDOCODE_v1.5.md → v1.6）**：① §10 口径① cmd_deploy 单位级 ANY 门、§17.2 联立解 3 C3 规格（"单位内无 TOWED 元素"）、§17.4:1 终审登记句（删"不擅改"）、GDD 待同步第 19 条——随 FIX-1b 同步改元素粒度口径（本版 IMPL 侧已改，两版须同构）；**且 FIX-1b 三处注记（§10 口径/§17.2 联立解 3/§17.4:1）须补"可推翻"字样与 IMPL 侧【按终审指令落地·可推翻】同款标注**（独立终审问题 3——两版同构性破缺点）；② §4.4 对空交战正文措辞与"最近"默认一致（FIX-3）；③ M28 六处注记与 §17 未触及指引随拍板执行升级（⑬~㉗ 已按推荐拍板——A01/A06→⑭A、A03→⑮A、G01→⑬A、A05→⑰A、A12→⑱A、A08→⑲A、G13→⑳A、G25→㉑A、A04→㉒A、A07→㉓A、A10→㉔A、A11→㉕A、A15→㉖A、A16→㉗A）；④ §17.3"拍板默认单列"镜像附表全 5 条（M19/M20/M25/M26/M4）或改为引用清单附表（清单 v1.6 登记口径说明②）；⑤ ⑮A 置位 4 卡数据硬要求注记——机制版实际落点为其 §2 toggleAmbush 注记（清单原文"机制版 D.1#25"系标签误标，见 §Y·二⑮行更正）；⑥ 行为同构项：③A 烟弹射程门、④A 渗透实战起算、⑲A 狙击排除 MECH、⑳A 掩护目标三门、㉑A 挂载粒度、FIX-1b；⑦ 其 GDD 待同步清单"已回写 v1.6"标注与 GDD v1.6 执行记录（自记第 11~22 条未回写）矛盾——按 GDD 侧实际状态回改标注或补执行（独立终审问题 2）。
- **GDD-02（GDD 回写员执行，按清单 v1.5 附"文档回写清单"+本版增量）**：① 四处士气表述删除（①A）；② R-06 注记（②A）；③ 删"（主力）"（⑥A）；④ R-04 回写（⑦A）；⑤ 卡面"高重伤率"改写三处（⑧A+⑱A）；⑥ "建筑进驻加成"定义（⑨A）；⑦ 功能细则 :375 删"冲刺速度+1档"（⑬A）；⑧ 冲锋枪排/骑兵排卡面"必中"注记（⑭A）；⑨ R-17 注记留加权表接口（⑰A）；⑩ R-02"狙击目标均为人员"（⑲A）；⑪ R-14 数值表述（㉒A）；⑫ §2.2 删卡面字段行（㉓A）；⑬ 第8轮拍板处注明共 ±15° 弧（㉕A）；⑭ R-03 注记"曲射只留声迹"（㉗A）+ R-03:24 停火冻结口径（FIX-5，⑫A 选边）；⑮ GDD 待同步第 19 条 DeployCmd 表述随 FIX-1b 改元素粒度；⑯ 机制版 v1.4 §14/§16 所列 1~18 条与两版 §X/17 GDD 待同步 19~24 条合并执行。

### 六、notApplied（本版未执行事项，如实登记）

- 本版未修改任何 GDD-02 / 机制版 / 拍板清单文件（纪律：只写本份新文档 GROUND_UNITS_PSEUDOCODE_IMPL_v1.6.md）——§Y·五所列机制版与 GDD 侧待办均仅登记、未代执行。
- 纯 GDD 侧无伪代码载体的项（①②⑥⑨⑬回写⑭卡面⑰注记⑱㉒㉓㉕㉗回写部分）：本文零改动，登记待办。
- ⑤ 全表 mm→0-20 换算细则表、⑧A 对 MECH 目标伤害复核、⑮A 翻案重估——属数值章节工作，本文仅锚定规则/登记要求。
- ⑮ 清单原文落点"机制版 D.1#25"：IMPL 侧成文为**补充落点**（保两版同构），机制版侧注记待其定稿员落。
- 派生子选择（均标"可推翻"，源自推荐文本的内部自由度，未自创行为）：⑧A 取"高 damage 数值表达"路径（非加 vs_infantry_mult 槽）；⑲A 落为 SNIPER 武器目标过滤双门（target_mask 无 MECH 位）；㉑A 门失败逐班 CONTINUE、cargo_units 单位级登记与 mounted_in 计账分工；④A 实战期 spawn 补置 600（覆盖出牌队列滞后边缘）。
- 终审修复无未落地残留：FIX-1a/2 核验已落地、FIX-1b 本版补齐、FIX-3/5 非本文件范围登记、FIX-4 已执行。

---

## §Z. v1.7 变更记录（定稿终检 30 条 gap 落实——docs/GDD-02-伪代码审查问题文档-v1.6.md）

> 三方对照终检（v1.6 IMPL × v1.6 机制版 × GDD v1.7 × sovs/sim 代码，15 审查代理三遍）产出 gap 30 条。本版落实**伪代码侧 12 条**（GAP-09~13、20~26）；**代码对齐 18 条**（GAP-01~08、14~19、27~30）随 sovs/sim 同批修复（round_div 方向裁定：以 §T 字面式 `(2n+d)//(2d)` 为准，代码与测试随改）；**GDD 侧 2 条欠账**（GAP-12 R-04 回写、GAP-13 政委督战残留改锚）随 GDD-02 v1.8 同批执行。17 条 ambiguity 不阻断判定，留待拍板（AMB-01/02/05/07 建议优先）。

1. **Z-1（GAP-09）**：§F6 cmd_deploy ELIF 补 `WHERE e.towed != TOWED`——与清旗循环同作用域；"拖走 1 门留守 3 门"下 DeployCmd 不再整连空走 30 秒（FIX-1b 半边落实闭合，与机制版 §10③ 同构）。
2. **Z-2（GAP-10）**：cmd_tow 补三道门（同队 / 合法被拖对象=GUN 或含 TOW 位可被拖 MECH / 牵引侧 TOW 位）；start_tow 补函数级同队硬门；system_supply 维修分支补 `e.unit.team == rep.unit.team`——敌方装备不可被拖走/修满（R-19"保车"锚定己方；机制版 :955"拖走空投箱"自注闭合）。
3. **Z-3（GAP-11）**：§D.1#15 TOW 位数据硬要求补全——被拖侧 + 中防空 61-K/Flak 43；牵引侧 + 苏④/德④卡车队（TOW|CARGO|TRANSPORT 三位）；重防空 52-K/Flak 36 拍板默认=不配 TOW 位（不可拖，可推翻）。
4. **Z-4（GAP-13）**：§F1 :374 注释改锚"政委突击光环'跟我上'"——督战成分（D034 原案）随拍板①士气裁剪无承载，GDD :387 改锚随 GDD v1.8 执行。
5. **Z-5（GAP-20）**：§F4 aa_try_engage 删单位级 ANY 连带——与地面链 fire_permitted 同谓词（元素级单判），留守防空门被拖 1 门时对空自动交战恢复（补-16/R-19 元素粒度贯穿对空链）。
6. **Z-6（GAP-21）**：§F6 spawn_airdrop_crate 模板规格 hasSupply 位必配（与 supply_radius 并列数据硬要求）——空投箱拾取链静默失效闭合。
7. **Z-7（GAP-22）**：§F3 四个视觉函数（detection_range_cm / keep_range_cm / point_in_friendly_vision / sense_air）接 `optics_factor_bp` 乘区——SEN 暴击消费点落地（方案7 读链），MECH crit 掷骰不再 25% 空转。
8. **Z-8（GAP-23）**：§F3 声测侦听名单补 `ALL(e.mounted_in == NULL)`——声测班上车后停止新增定位/收窄（R-03×D065 互锁），已显示圈不受影响。
9. **Z-9（GAP-24）**：release_tow_if_involved 参数改元素级（pair 级解除）+ 三处调用点（destroy_element / cmd_set_element_mode / 维修归队分支）改传元素——卡车队 3 对拖曳各自解除，v1.3#12 元素级拍板彻底执行（与机制版 :617 同构）。
10. **Z-10（GAP-25）**：world_tick ③④ 之间补 fire_arc<360 元素 rotating 每 tick 复位——转向中断（目标毁/换目标/移动令）不再滞留 TRUE（B04 第一条修法补齐）。
11. **Z-11（GAP-26）**：§F6 cmd_smoke 撤销 element.reveal_timer 写点（声测喂入保留）——㉗A 后曲射链统一"只留声测痕迹"，同一发射器 HE 不暴露/烟暴露的自相矛盾消除。〔拍板默认·可推翻：回"GAP-26 改B"恢复 M7 写点并回写 GDD 烟弹例外〕
12. **Z-12（GAP-12）**：GDD 侧 R-04 首句回写"实战开始后前 60 秒"（④A 已在两版伪代码正确落地，GDD v1.8 执行回写）。

**机制版同步**：Z-1（机制版 §10③ 已先行收窄，无需改）、Z-2/Z-5/Z-6/Z-8/Z-11 随机制版 v1.7 同步；Z-9 机制版 :617 本为 pair 级（不同构点消除）；Z-3 数据硬要求与 Z-4 注记随机制版 §D 对应行同步。两版同构纪律（§X·二头注）恢复。

### §Z 补遗：17 条 ambiguity 拍板执行（2026-09-29，同批 GDD v1.8 / sovs/sim）

13. **Z-13（AMB-01~17 全量闭环）**：AMB-01 falloff 定义式=随弹径插值（跨度 2×弹半径，§F1 两处消费成文；代码同步）；AMB-02 驻楼模板前置（代码 sensing.py 补合取式）；AMB-03 声测定性=确定性累积模型（GDD R-03"概率上升"改写"精度随开火时长上升"）；AMB-04 林内 +2=全体单位（§D.0 :91 注记+GDD ㉓A 改写）；AMB-05 近战对 MECH=绕过装甲曲线（§D.8 #5 登记、机制版改齐）；AMB-06 校射累积=按批（§D.0 单位改"点/批"）；AMB-07 空车可射击数据硬要求（§D.2#10 成文）；AMB-08 徐进弹幕=缓慢连续推进（GDD R-13 回写，零改动）；AMB-09 半轮取整=⌈N/2⌉（§F4.1 :900 成文）；AMB-10 拖曳随动=后方 300cm 偏移+facing 跟随（§F5 成文+代码同步+§D.0 tow_follow_offset_cm）；AMB-11 重展开窗口全连禁射=正式接受（GDD 补-19 补注；元素级计时器留作"AMB-11 改B"）；AMB-12 解挂独立火力点=接受拉回（GDD 补-16 补注：投递仅用于转移阵地，火力点需母连驻守）；AMB-13 R-07 括注改"部分成员阵亡"（GDD）；AMB-14/17② 声测喂入=仅曲射 BALLISTIC（fire_direct 写点删除、cmd_smoke trajectory 档案化、烟罐 DIRECT 不喂——保留清单#3 修订）；AMB-15 拍板清单 M25 存档行文字修订（存档侧）；AMB-16 §F3 声测段（sonar_step/upsert_sound_track/IntelCircle）登记为**代码增量第二批**（伪代码承载已核对在位，sensing.py 实现排期——本条登记即销）；AMB-17① 侦察排 SMOKE 档案数据硬要求（cmd_smoke 段成文：ammo_base=2/DIRECT/reveal 0）。全部推翻通道=回"AMB-N 改B"。
