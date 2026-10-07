# DATA-01 地面数据卡 Schema 冻结 v1

> **冻结声明**：本文档为 69 张地面数据卡 schema 的唯一权威（对应实现＝`sovs/sim/card_schema.py`，
> pydantic v2.13.2，构建期校验层）。此后 schema 的一切变更只经本文档登记并遵守 §2.3 演进规则
> （只向后兼容：加字段可以、改语义不行）。冻结先例：`sovs/sim/air_data.py` 文件头（:1-33）、
> IMPL-地面 §D（GROUND_UNITS_PSEUDOCODE_IMPL_v1.7.md）。
>
> 依据：施工方案 out/card-schema-plan.md v1.1（已通过评审，2026-10-02）——字段清单＝其 §A、
> 版本规则＝其 §B、配额归属＝其 §C、映射表＝其 §D、表格拍板＝其 §E/F。
> 数值纪律：坐标 cm、时长 tick（10Hz）、概率 bp（万分比）、倍率 permille/bp，**一律严格 int，
> float 必须被拒**（`StrictInt` 实测拒 `1.0`/`1.5`/str/bool）；禁 math 超越函数与 random 模块
> （sovs/sim/rng.py:1、TECH-00 §3.2/§4）。
>
> 实现锚：`sovs/sim/types.py`（冻结 dataclass——UnitTemplate :223-249 / ElementTemplate :205-220 /
> WeaponTemplate :165-194 / Armor :139-148 / Aura :197-202）；`sovs/sim/tables.py`（BalanceConfig）。
> 测试：`tests/test_card_schema.py`（45 用例，2026-10-02 本轮 `python3 -m pytest
> tests/test_card_schema.py -q` → 45 passed）。

---

## §1 表格格式拍板：CSV（UTF-8 带 BOM，`\n` 行尾）

**拍板：交换格式＝CSV；编辑前端＝Excel/Sheets；管线产物＝JSON。**

1. **纯文本逐行可 diff**——数值调参是高频操作，69 卡 × 60 卡面字段（§4.1 计数）的逐值变更必须
   逐行可审计（仓库非 git，文件级 diff 是唯一审计面）。
2. **stdlib `csv` 即读**——本轮实测（2026-10-02）：`python3 -c "import pandas"` →
   `ModuleNotFoundError: No module named 'pandas'`（未装）；openpyxl 3.1.5 虽已装，但 xlsx 是
   ZIP 二进制、diff 不可读，且 pandas 的 dtype 推断会把 int 列静默升 float（与严格 int 硬约束
   直接冲突）。
3. **Excel/Sheets 仍作编辑前端**——导出 CSV 用 `utf-8-sig`（UTF-8 BOM），Excel 打开中文不乱码；
   stdlib 读取透明去 BOM。
4. **JSON 产物两端不变**——TECH-00 §8 :148 管线「（表格）→ 读取 → pydantic 校验（字段/配额
   D011/D032/限份）→ JSON」中，pydantic 校验与 JSON 产物两端保持原样；收窄的只是中间读取器
   （stdlib `csv` 替代 pandas/openpyxl），属实现选择而非架构变更。
5. 约定：列表列分隔符 `;`（如 `flags=CAN_AMBUSH;SUPP_DECAY_X2`），值内禁出现 `;`；
   公式注入（`=`,`+`,`-`,`@` 开头单元格）由读取器白名单拦截（数据文件受控，低风险——开放问题 O-10）。
   五表结构（卡级/元素级/武器级/provenance/pending＋decks/）见施工方案 §E.1。

---

## §2 schema_version 版本号语义与演进规则

### §2.1 版本号语义

`SCHEMA_VERSION = "1.3"`（major.minor，str；1.0→1.1＝2026-10-04 PB-52 单位级地形数值块
加三可选字段、1.1→1.2＝2026-10-04 PB-53 载具自卫烟幕块加元素级可选字段
self_smoke_charges、1.2→1.3＝2026-10-04 PB-55 士气效果接线块加卡级三可选字段
morale_{sup,pin,rout}_th——均 §2.3-1 minor 演进），写入 `CardLibraryModel` 根（JSON 卡库）与每个
`DeckModel`（deck JSON；deck CSV 不携带，由构建期注入——施工方案 §B.1）。

### §2.2 版本门（结构化支持表）

`SUPPORTED_CARD_SCHEMA: dict[int, int] = {1: 3}`——键＝major、值＝接受的 minor 上界（0→1
随 1.0→1.1（PB-52）、1→2 随 1.1→1.2（PB-53）、2→3 随 1.2→1.3（PB-55），均 2026-10-04）。
加载/校验接受 ⇔ `file_major in SUPPORTED_CARD_SCHEMA and file_minor ≤
SUPPORTED_CARD_SCHEMA[file_major]`；其余一律拒绝（fail-fast，杜绝静默漂移）。
判定函数：`card_schema.schema_version_supported(version) -> bool`；卡库与 deck 的模型级校验器
内嵌同一判定。回放归档的 JSON 随回放保存，旧回放按旧 schema 快照重放（§3）。

### §2.3 演进规则（只向后兼容）

1. **允许（minor+1）**：加**可选**字段（带默认值）；放宽取值域；枚举加令牌。旧数据在新加载器下
   照常通过（缺省默认值）。
2. **禁止（须 major+1 并附迁移脚本）**：改任何字段单位（如 cm→m、吨位 0.1t 刻度改整吨）、改 int
   语义、删必填字段、收窄域、重命名字段、改校验规则使旧数据非法。
3. **弃用流程**：先在 minor 版标 `deprecated`（加载器发警告），下一个 major 移除（体积系数
   size_factor_bp 若两个 minor 周期未接线即走此流程——开放问题 O-08）。
4. 弃用/新增一律同步更新 §4 字段清单、字段级分级元数据（§6.1）与本文档。

### §2.4 枚举表示口径（唯一）

- **CSV/录入层一律 str 令牌**（`SOVIET`/`KE`/`HOWITZER`/`RECON`…——pydantic `Literal` 令牌集；
  实测 `Literal[int]` 会放行 `2.0`，故整数枚举一律令牌化，float 天然被拒）。
- **JSON 一律落 int 值**——令牌→int 单点映射表 `card_schema.TOKEN_VALUE`（值取自 types.py
  IntEnum/IntFlag，不重复手写数值；`air_ceiling` 的 `NONE`→-1 由 loader 转 types 的 `None`）。
  JSON 随回放归档，数值化表示保证跨版本令牌改名不破回放。
- **构造 dataclass 时 int→IntEnum 反查**（card_loader 职责，施工方案 §D.1）。

---

## §3 三版本绑定策略

| 版本 | 载体 | 绑定规则 |
|---|---|---|
| 数据 schema 版本 | `CardLibraryModel.schema_version`／`DeckModel.schema_version` | 由 `card_schema.SCHEMA_VERSION` 单点定义；**card_schema.py 与 types.py 冻结构造器签名同批演进**——types.py 任一构造参数增删改（破坏性）⇒ card_schema 必须 major+1（schema 字段集直接镜像构造参数，§9）。deck 与卡库版本不一致即拒（`validate_deck` 首检）。 |
| 仿真构建版本 | 回放头 `sim_core_revision`（＝sovs/sim 源文件哈希清单——仓库非 git，无 commit 号可用） | 回放文件头三元组 `{replay_format_version, card_schema_version, sim_core_revision}`；重放前三者逐一比对，不符即拒绝。 |
| 回放格式版本 | 回放文件自身 | TECH-00 §9 M1「回放格式定型」:162；`template_id` 进回放校验（IMPL-地面 D.1#1），库级唯一性由加载器保证；数据 schema major 变更致 template_id 语义漂移时，旧回放按旧 schema 快照重放（JSON 随回放归档）。 |

---

## §4 字段清单（与 `sovs/sim/card_schema.py` 模型一一对应）

### §4.1 总览与单位约定

单卡层级字段总数（不含武器行展开）＝39（卡级）＋3（Aura）＋16（元素级）＋8（Armor KE/HE×四面）
＝**66**（36→39＝2026-10-04 PB-55 加三士气阈值可选字段；33→36＝2026-10-04 PB-52 加三可选覆盖字段）；武器行 29 列（27 模板字段＋2 管线键）另行展开。单位：cm＝坐标/距离厘米；tick＝10Hz
时长；bp＝万分比（0..10000）；permille＝千分比；档/刻度＝无量纲整数；**吨位两字段＝0.1t 刻度
×10 整型（§7）**。所有数值字段＝pydantic `StrictInt`（拒 float/str/bool），布尔＝`StrictBool`，
所有模型 `extra="forbid"`（未知字段拒）。来源分级六级（§6）：〔GDD〕〔数锚〕〔冻结〕〔拍板〕
〔锚点〕〔待定〕。

### §4.2 令牌集与 int 映射（TOKEN_VALUE）

| 域 | 令牌集 | int 值（types.py 权威） |
|---|---|---|
| faction | SOVIET / GERMAN | 0 / 1（卡记录层，管线自编——D004） |
| category | RECON / INFANTRY / ARMOR / FIRE_SUPPORT / AA_LOGISTICS | 0/1/2/3/4（types.py:227 注释＝D028 冻结口径） |
| pool | MAIN / RESERVE | 0 / 1 |
| quota_group | NONE / HOWITZER / AT_GUN / ROCKET | 0/1/2/3 |
| delivery | NONE / LI2 / JU52 | 0/1/2（P-13 空降投送限定） |
| air_ceiling | NONE / LOW / MID / HIGH | -1（→None）/ AltTier 0/1/2 |
| movement_class | FOOT / WHEEL / TRACK / HORSE | MovementClass 0/1/2/3 |
| element_type | VEHICLE / GUN / SQUAD | ElementType 0/1/2 |
| unit_type | INFANTRY / MECH | UnitType 0/1（GUN 按 M22 归类） |
| damage_type | KE / HE / SMOKE | DamageType 0/1/2 |
| trajectory | DIRECT / BALLISTIC | Trajectory 0/1 |
| combat_style | NORMAL / MELEE / SNIPER | 0/1/2（types.py:190 注释口径） |
| aura_kind | MELEE / PRECISION | AuraKind 0/1 |
| target_mask | GROUND / AIR_LOW / AIR_MID / AIR_HIGH | TargetDomain 位 1/2/4/8（位或后落 int） |
| mode_set | DIRECT / INDIRECT / TOW / CARGO / TRANSPORT | Mode 0/1/2/3/4（位或后落 int） |
| flags | CAN_SPRINT…SUPP_DECAY_X2 共 14 令牌 | UnitFlag 位 1<<0…1<<13（types.py:121-136，位或后落 int） |

### §4.3 卡级 UnitCardModel（39 字段，CSV 一卡一行；36→39＝2026-10-04 PB-55 加可选字段 22~24，minor 1.3）

| # | 字段 | 类型 | 单位/取值域 | 默认 | 分级〔来源〕 | 映射落点（types.py） |
|---|---|---|---|---|---|---|
| 1 | card_key | str | `^[A-Z][A-Z0-9_]*$`，全库唯一 | 必填 | 〔拍板〕air_data CARD_KWARGS 键先例 :129 | 管线主键（不映射） |
| 2 | template_id | int | >0，全库唯一；苏 101~/德 201~（避开航空 1~15） | 必填 | 〔拍板〕编号方案（O-11） | UnitTemplate.template_id :225 |
| 3 | name | str | 非空 | 必填 | 〔GDD〕GDD-01 卡名 | UnitTemplate.name :226 |
| 4 | faction | 令牌 | SOVIET/GERMAN | 必填 | 〔GDD〕D004 | 卡记录层（不映射） |
| 5 | category | 令牌 | RECON/INFANTRY/ARMOR/FIRE_SUPPORT/AA_LOGISTICS | 必填 | 〔GDD〕D028 | UnitTemplate.category :227 |
| 6 | cost | int 点 | >0 | 必填 | 〔GDD〕GDD-01 卡面价（T-34/85=100 基准，D038） | UnitTemplate.cost :228 |
| 7 | pool | 令牌 | MAIN/RESERVE | 必填 | 〔GDD〕D001 | 卡记录层（deck 校验消费） |
| 8 | per_card_limit | int \| null | ≥1；null=按类别默认（装甲2/步兵3/侦察2/火支2/防空后勤2——§8） | null | 〔GDD〕D032 :198-200 | 卡记录层（validate_deck 消费） |
| 9 | quota_group | 令牌 | 4 值；仅火支卡可非 NONE | NONE | 〔GDD〕D028；GDD-02 :201 | 卡记录层（子配额校验） |
| 10 | unlock_by | str | 空=通用 | "" | 〔GDD〕D.1#29；GDD-01 §3 | 卡记录层（§F7 :1365） |
| 11 | delivery | 令牌 | NONE/LI2/JU52；≠NONE ⇒ pool=RESERVE | NONE | 〔GDD〕P-13 | 卡记录层（spawn_paratroop 消费链） |
| 12 | optics_ground_cm | int cm | >0 | 必填 | 〔冻结〕D.1#6 | UnitTemplate.optics_ground_cm :230 |
| 13 | optics_air_cm | int cm | ≥0（0=无） | 0 | 〔冻结〕D.1#7（GAP-05） | UnitTemplate.optics_air_cm :243 |
| 14 | air_ceiling | 令牌 | NONE/LOW/MID/HIGH | NONE | 〔冻结〕D.1#8 | UnitTemplate.air_ceiling :244 |
| 15 | stealth_base | int | 0..10 | 必填 | 〔冻结〕D.1#9 | UnitTemplate.stealth_base :231 |
| 16 | speed_tier | int | 1..5 | 必填 | 〔冻结〕D.1#10（档表=tables.py:14） | UnitTemplate.speed_tier :232 |
| 17 | movement_class | 令牌 | FOOT/WHEEL/TRACK/HORSE | 必填 | 〔冻结〕D.1#11 | UnitTemplate.movement_class :233 |
| 18 | turn_rate_deg | int 度/tick | ≥1 | 1 | 〔冻结〕D.1#12（R-09） | UnitTemplate.turn_rate_deg :234 |
| 19 | terrain_speed_override_bp | int bp | 0..10000（0=回退类级 terrain_speed_bp[类]） | 0 | 〔拍板〕PB-52 2026-10-04（断箭 N10/映射 §五.6；野三级回退 瓦片>单位级>类级） | UnitTemplate.terrain_speed_override_bp |
| 20 | reverse_speed_override_bp | int bp | 0..10000（0=回退类级 reverse_speed_bp[类]） | 0 | 〔拍板〕PB-52 2026-10-04（倒车资格门4+§2.3 增量②乘区同读 movement.reverse_speed_bp 求值函数） | UnitTemplate.reverse_speed_override_bp |
| 21 | road_bonus_override_cm | int cm/tick | ≥0（0=回退 cfg.road_bonus_cm_tick） | 0 | 〔拍板〕PB-52 2026-10-04（契约⑦ max 形态不动、下限常数单位级可覆盖；FOOT 不吃路谓词保持） | UnitTemplate.road_bonus_override_cm |
| 21 | road_bonus_override_cm | int cm/tick | ≥0（0=回退 cfg.road_bonus_cm_tick） | 0 | 〔拍板〕PB-52 2026-10-04（契约⑦ max 形态不动、下限常数单位级可覆盖；FOOT 不吃路谓词保持） | UnitTemplate.road_bonus_override_cm |
| 22 | morale_sup_th | int | ≥0（0=回退 cfg.morale_sup_th；**显式设定值间须严格递增 22<23<24——构建期交叉校验**） | 0 | 〔拍板〕PB-55 2026-10-04（D027:174 生存段卡级士气阈值三列；D025「数值待配」——现役全卡留空回退全局缺省，定标归数值章节） | UnitTemplate.morale_sup_th |
| 23 | morale_pin_th | int | ≥0（0=回退 cfg.morale_pin_th） | 0 | 〔拍板〕PB-55 2026-10-04（同上；钉住=PB-49 可动减速档） | UnitTemplate.morale_pin_th |
| 24 | morale_rout_th | int | ≥0（0=回退 cfg.morale_rout_th；>100=压制封顶外永不溃逃差异化位——列间独立回退，可单档覆盖） | 0 | 〔拍板〕PB-55 2026-10-04（同上） | UnitTemplate.morale_rout_th |
| 25 | deploy_time_ticks | int tick | ≥0（0=免展开） | 0 | 〔GDD〕D027/D031 | UnitTemplate.deploy_time_ticks :235 |
| 26 | pack_time_ticks | int tick | ≥0 | 0 | 〔GDD〕同上 | UnitTemplate.pack_time_ticks :236 |
| 27 | flags | list[令牌] | 14 令牌内、无重复（位或→int） | [] | 〔冻结〕D.1#25 | UnitTemplate.flags :237 |
| 28 | mode_set | list[令牌] | 5 令牌内、无重复（位或→int） | ["DIRECT"] | 〔冻结〕D.1#15 | UnitTemplate.mode_set :242 |
| 29 | supply_radius_cm | int cm | ≥0 | 8000 | 〔冻结〕D.1#20（R-18） | UnitTemplate.supply_radius_cm :238 |
| 30 | sonar_radius_cm | int cm | ≥0 | 0 | 〔冻结〕D.1#22（R-03） | UnitTemplate.sonar_radius_cm :239 |
| 31 | sonar_rate | int | ≥0 | 0 | 〔冻结〕D.1#23 | UnitTemplate.sonar_rate :240 |
| 32 | acoustic_signature | int | ≥1 | 1 | 〔冻结〕D.1#21 | UnitTemplate.acoustic_signature :241 |
| 33 | tow_tonnage | int **0.1t 刻度** | ≥0（ZiS-5=15、Opel Blitz=30） | 0 | 〔数锚+拍板〕GDD-03 §1.7；粒度见 §7 | UnitTemplate.tow_tonnage :245 |
| 34 | own_weight_tons | int **0.1t 刻度** | ≥0（M-30=25、52-K=45、ML-20=73；**进一取整**） | 0 | 同上 | UnitTemplate.own_weight_tons :246 |
| 35 | repair_power_hp_per_tick | int HP/tick | ≥0 | 0 | 〔冻结〕D.1#19（D016） | UnitTemplate.repair_power_hp_per_tick :247 |
| 36 | close_combat_bonus_permille | int permille | ≥100（骑兵 1800） | 1000 | 〔冻结〕D.1#16（GAP-16） | UnitTemplate.close_combat_bonus_permille :248 |
| 37 | size_factor_bp | int bp | ≥1 | 10000 | 〔D027 遗留·无消费点〕G-1（§10） | **不映射**（loader 丢弃并 log） |
| 38 | aura | AuraModel \| null | 仅步兵（指挥）卡合法 | null | 〔冻结〕D.1#24 | UnitTemplate.aura :249 |
| 39 | elements | list[ElementModel] | ≥1 组 | 必填 | 〔GDD〕D006/D009；D.1#5 | UnitTemplate.element_templates :229（count 展开） |

AuraModel（3 字段）→ `types.Aura`（:197-202）：kind（令牌 MELEE/PRECISION）｜bonus_bp（int
bp，≥0）｜radius_cm（int cm，≥0）。

### §4.4 元素级 ElementModel（17 字段，CSV 一元素组一行；16→17＝2026-10-04 PB-53 加可选字段 self_smoke_charges，minor 1.2）

| # | 字段 | 类型 | 单位/取值域 | 默认 | 分级 | 映射落点（ElementTemplate :205-220） |
|---|---|---|---|---|---|---|
| 1 | element_key | str | 非空，卡内唯一 | 必填 | 〔拍板〕管线键 | 不映射（外键） |
| 2 | count | int | ≥1（编制数：车/班/门） | 必填 | 〔GDD〕D027 :169 | 加载时重复展开为扁平元组 |
| 3 | element_type | 令牌 | VEHICLE/GUN/SQUAD | 必填 | 〔冻结〕D.2#1 | element_type :207 |
| 4 | unit_type | 令牌 | INFANTRY/MECH | 必填 | 〔冻结〕D.2#2 | unit_type :208 |
| 5 | hp_max | int HP | >0；SQUAD=编制人数（1HP=1人） | 必填 | 〔数锚〕GDD-03 §1.1（D067） | hp_max :209 |
| 6 | armor_ke | ArmorModel \| null | 四面各 0..20；MECH 必填/INFANTRY null | null | 〔数锚+拍板〕⑤A mm 换算锚 | armor_ke :210 |
| 7 | armor_he | ArmorModel \| null | 同上 | null | 同上 | armor_he :211 |
| 8 | fire_arc_deg | int 度 | **仅 360 或 30**（±15°，R-09） | 360 | 〔冻结〕D.2#6 | fire_arc_deg :212 |
| 9 | suppression_vuln_permille | int permille | ≥0（敞篷>1000） | 1000 | 〔冻结〕D.2#7 | suppression_vuln_permille :213 |
| 10 | squad_quality_bp | int bp | ≥0（老兵班 11500） | 10000 | 〔冻结〕D.2#8（替代老练度 D035） | squad_quality_bp :214 |
| 11 | weapons | list[WeaponRowModel] | 见 §4.5 | [] | 〔冻结〕D.2#9 | weapons :215（→tuple） |
| 12 | seats | int | ≥0（0=不可载） | 0 | 〔冻结〕D.2#11 | seats :216 |
| 13 | mounted_armament | list[str] \| null | 键须在本元素 weapons 内（AMB-07） | null | 〔冻结〕D.2#10 | mounted_armament :217（解引用→tuple） |
| 14 | cargo_rounds_max | int 发 | ≥0（D065 600/车） | 0 | 〔冻结〕D.2#12 | cargo_rounds_max :218 |
| 15 | cargo_medical_max | int 份 | ≥0（D065 120/车） | 0 | 〔冻结〕D.2#13 | cargo_medical_max :219 |
| 16 | cargo_weight_max | int 重量 | ≥0（D012 混装） | 0 | 〔冻结〕D.2#14 | cargo_weight_max :220 |
| 17 | self_smoke_charges | int 发 | ≥0（0=无自卫烟幕能力——PB-53；哪些车配属=数据卡配置侧，冷却/延迟/半径/时长=tables.py 烟雾段非本表）。**数据纪律约束（2026-10-04 终审留痕）：非零值仅可填 VEHICLE 行**——机制层无元素类型门（tick.py cmd_smoke），SQUAD 行误填非零将静默赋予步兵烟幕且无告警；定标时若加 loader 校验以本行为准 | 0 | 〔拍板〕PB-53（断箭 N32） | self_smoke_charges（types.py ElementTemplate 尾槽） |

ArmorModel（4 子字段 ×KE/HE＝8 槽）→ `types.Armor`（:139-148）：front/side/rear/top 各 int，
0..20 相对刻度（0=无甲合法——卡车）。

### §4.5 武器行 WeaponRowModel（29 字段＝27 模板字段＋2 管线键，CSV 一武器一行）

| # | 字段 | 类型 | 单位/取值域 | 默认 | 分级 |
|---|---|---|---|---|---|
| 1 | weapon_key | str | 非空，元素内唯一 | 必填 | 〔拍板〕管线键 |
| 2 | element_key | str | 外键→§4.4#1（与所属元素一致） | 必填 | 〔拍板〕管线外键 |
| 3 | name | str | 非空 | 必填 | 〔冻结〕D.3#1 |
| 4 | target_mask | list[令牌] | ≥1 项（位或→int） | ["GROUND"] | 〔冻结〕D.3#2 |
| 5 | damage_type | 令牌 | KE/HE/SMOKE | 必填 | 〔冻结〕D.3#3 |
| 6 | pen_min | int | 0..20（远距） | 0 | 〔数锚+拍板〕⑤A mm 换算 |
| 7 | pen_max | int | 0..20（贴脸），**≥pen_min** | 0 | 同上 |
| 8 | damage | int HP/发 | ≥0 | 0 | 〔数锚〕GDD-03 通用武器表 |
| 9 | blast_radius_cm | int cm | ≥0 | 0 | 〔数锚〕GDD-03 §2.3 溅射带 |
| 10 | max_range_cm | int cm | >0 | 必填 | 〔数锚〕史实射程换算 |
| 11 | min_range_cm | int cm | ≥0，≤max_range_cm | 0 | 〔冻结〕D.3#9 |
| 12 | dispersion_cm | int cm | ≥0（方形散布半径） | 0 | 〔冻结〕D.3#10 |
| 13 | accuracy_base_bp | int bp | 0..10000 | 10000 | 〔待定〕距离衰减/精度定标（GDD-00 §2 :374） |
| 14 | aim_time_ticks | int tick | ≥0 | 0 | 〔数锚〕Enlisted 锚（D067 :350） |
| 15 | reload_time_ticks | int tick | ≥0 | 0 | 〔数锚〕同上 |
| 16 | salvo | int 发 | ≥1 | 1 | 〔数锚〕同上 |
| 17 | ammo_base | int 发 | ≥0 | 0 | 〔数锚〕史实弹容 |
| 18 | ammo_weight | int 重量/发 | ≥0 | 0 | 〔待定〕supply_round_weight 定标（tables.py:54） |
| 19 | projectile_speed_cm_tick | int cm/tick | ≥0 | 0 | 〔数锚〕史实弹速换算 |
| 20 | trajectory | 令牌 | DIRECT/BALLISTIC | DIRECT | 〔冻结〕D.3#18 |
| 21 | suppression_power | int 压制值/发 | ≥0 | 0 | 〔数锚〕GDD-03 §2.3 压制带 |
| 22 | crit_mod_permille | int permille | ≥0 | 1000 | 〔冻结〕D.3#20 |
| 23 | vs_fort_mult_permille | int permille | ≥0（M5 硬要求） | 1000 | 〔冻结〕D.3#21 |
| 24 | needs_deployed | bool | — | False | 〔冻结〕D.3#24（R-05） |
| 25 | combat_style | 令牌 | NORMAL/MELEE/SNIPER | NORMAL | 〔冻结〕D.3#26（方案1 档案化） |
| 26 | reveal_time_ticks | int tick | ≥0 | 0 | 〔冻结〕D.3#27（开火暴露） |
| 27 | restricted_profiles | list[{count≥1, pen_bonus≥0}] | 钨芯受限档 | [] | 〔拍板〕㉖A 换算锚 |
| 28 | alt_profile | {damage≥0, blast_radius_cm≥0} \| null | R-11 HE 档 | null | 〔冻结〕D.3#23 |
| 29 | self_defense | {max_range_cm>0, accuracy_mult_bp≥0} \| null | R-15 自卫档 | null | 〔冻结〕D.3#25 |

#27-#29 三子模型（RestrictedProfileModel/AltProfileModel/SelfDefenseModel）→ types.RestrictedProfile
元组 / types.AltProfile / types.SelfDefenseProfile（:151-163）。

### §4.6 DeckModel / DeckEntryModel（卡组 JSON；CSV 三列 deck_key,card_key,copies）

| 字段 | 类型 | 取值域 | 默认 | 说明 |
|---|---|---|---|---|
| schema_version | str | 须过 §2.2 版本门 | 构建期注入 | deck CSV 不携带 |
| deck_key | str | 非空 | 必填 | 管线键 |
| faction | 令牌 | SOVIET/GERMAN | 必填 | 与所含卡逐一一致（§8） |
| cards | list[{card_key, copies≥1}] | card_key 不重复 | 必填 | copies 表份数 |
| points_main_cap | int 点 | >0 | 4000 | 〔待定〕D038 方案A占位（O-06） |
| points_reserve_cap | int 点 | >0 | 2000 | 同上 |

### §4.7 CardLibraryModel（全库 JSON 根）与 PendingItemModel

CardLibraryModel：schema_version（须过版本门）｜source_sha256（str，源 CSV 拼接哈希——审计用）
｜cards（list[UnitCardModel]，≥1，card_key/template_id 全库唯一）｜pending
（list[PendingItemModel]，缺省 []）。
PendingItemModel 五元组（air_data.py:416-454 PENDING_NUMERIC_ITEMS 惯例）：pending_id（`^P-\d+$`）
｜scope｜field｜filled_value｜resolve_plan（均非空 str）。

---

## §5 跨字段校验规则清单（card_schema.py 已实现，测试镜像）

| # | 规则 | 层级 |
|---|---|---|
| V1 | MECH ⇒ armor_ke/armor_he 必填；INFANTRY ⇒ 均 null（"SOFT 为 None"） | 元素 |
| V2 | fire_arc_deg ∈ {360, 30} | 元素 |
| V3 | weapon_key 元素内唯一；weapon 行 element_key 与所属元素一致 | 元素 |
| V4 | mounted_armament 每键 ∈ 本元素 weapons 键集（AMB-07） | 元素 |
| V5 | pen_max ≥ pen_min；min_range_cm ≤ max_range_cm | 武器行 |
| V6 | aura ≠ null ⇒ category=INFANTRY（指挥班组） | 卡 |
| V7 | quota_group ≠ NONE ⇒ category=FIRE_SUPPORT | 卡 |
| V8 | delivery ≠ NONE ⇒ pool=RESERVE（D017 空降占预备队） | 卡 |
| V9 | element_key 卡内唯一；flags/mode_set 令牌无重复 | 卡 |
| V10 | card_key 全库唯一；template_id 全库唯一 | 库 |
| V11 | schema_version 须过 SUPPORTED_CARD_SCHEMA 版本门 | 库/deck |
| V12 | deck 内 card_key 不重复（份数走 copies） | deck |

deck 构筑校验（`validate_deck(deck, library)`，构建期本模块/运行期 card_loader 同规则——§8）：
版本绑定（deck.schema_version == library.schema_version）→ 引用存在 → 阵营一致 → D032 限份 →
D011 类别配额 → R-13 子配额 → D038 点数。违规一律 fail-fast 抛错，不静默截断。

---

## §6 来源分级承载机制（三层）

沿用 air_data.py 六级标注（:7-17）：〔GDD〕〔数锚〕〔冻结〕〔拍板〕〔锚点〕〔待定〕。

1. **字段级默认分级（权威）**：§4 各表「分级」列即初值；pydantic 字段经 `json_schema_extra`
   可扩展携带 grade/src 元数据（冻结文档与字段注释同源）。
2. **值级偏离 sidecar**：`data/ground_provenance.csv`（card_key, field_path, grade, source_ref,
   pending_id）——仅登记与字段级默认**不同**的条目；JSON 输出序列化为每卡 `_provenance` 旁键，
   构造 dataclass 时忽略。
3. **待定登记 sidecar**：`data/ground_pending.csv`（§4.7 五元组）。**强制闭环**：字段默认分级
   ＝〔待定〕且无值级覆盖 ⇒ 该卡该字段必须能索引到一条 pending 记录；反之已登记 pending 的字段
   不得标〔冻结〕。管线构建时对账，缺档即 ValidationError（施工方案 §A.5-3；对账器随
   tools/build_cards.py 落地——本轮未含，见 §12）。

---

## §7 吨位字段粒度拍板（tow_tonnage / own_weight_tons）

- **刻度＝0.1t（十分之一吨）×10 整型**——沿用 §T「×10 整型存储」先例（tables.py:26-27
  forest_stealth_add_x10）。字段名不变（与 types.py:245-246 构造参数同名）。
- **理由**：D067 牵引分级史实值大量非整吨（ZiS-5 1.5t、ZiS-3 1.25t、PaK40 1.43t、Flak36 5.15t）；
  整吨取整会使 ZiS-5 与 M-30 在多种舍入法下撞值，错误放行/误拒 D067 要求的组合；改字段单位属
  major 禁止项（§2.3），冻结后无法便宜修补。
- **舍入规则**：own_weight_tons（被拖侧自重）**向上取整（进一）到 0.1t**——宁重勿轻，误拒优于
  误放；tow_tonnage（牵引能力）照数锚直存（1.5/3.0/12/30/45t 天然落网格）。
- **换算对照（0.1t 刻度）**：ZiS-5=15｜Opel Blitz=30｜ZiS-3/ZiS-2=13｜PaK38=10｜PaK40=15｜
  leFH18=20｜NbW41=11｜M-30=25｜52-K=45｜ML-20=73｜sFH18=55｜Flak36=52。分级〔数锚〕GDD-03
  §1.7 :40-48；粒度规则〔拍板·施工方案 v1.1 §A.6〕。
- 刻度无关性：拖曳门为同刻度比较（可拖 ⇔ Σtow_tonnage ≥ own_weight_tons），×10 后判定不变；
  现行代码对该两字段零消费点（拖曳命令族 §F7 TODO 未落地），冻结粒度无回归面。
  推翻通道＝改单位＝major+1 并附全表换算迁移脚本。Bergepanther 三口径不一致见 O-15。

---

## §8 D011/D032 校验归属表

| 机制 | 归属 | 数值 | 依据 |
|---|---|---|---|
| D032 同型限份 | **deck 级**（`validate_deck`；卡级字段 per_card_limit 可覆盖） | 类别默认：装甲2/步兵3/侦察2/火支2/防空后勤2；指挥班组=1（卡级覆盖） | GDD-00 :198-200；GDD-01 §0.5 同值互证 |
| D011 类别配额 | **deck 级**（category×pool 分桶） | 〔待定〕占位（GDD-01 §0.5 草案）：侦察 4/2、步兵 9/5、装甲 8/4、火支 6/3、防空后勤 5/2（主力/预备队） | GDD-00 :71-75「具体配额数值待配」 |
| R-13 火支子配额 | **deck 级**（quota_group 分桶，两池**总和**校验） | 榴≤3 / 反坦克≤2 / 火箭≤1 | IMPL-地面 §D.0 :83；GDD-02 v1.9 :201 拍板⑥ |
| D038 点数上限 | **deck 级**（主力/预备队分池 Σcost×copies） | 〔待定〕方案A占位 4000/2000（航空 750 已在 tables.py:77） | GDD-00 :372；O-06 |
| 特化解锁 unlock_by | 构筑期/运行期 `unlocked()` 状态 | — | IMPL-地面 §F7 :1365 |
| 航空限份 | **不进 deck 校验**——运行时门＝同型同时在空≤2（air_per_type_max，tables.py:78） | 2 | B-24 拍板（GDD-02 :293）；推翻通道="B-24 改B"（O-09） |
| 空降两卡限份 | category=INFANTRY、pool=RESERVE、随步兵默认 3＋pending 登记 P-13-ground | 3（拟） | air_data.py:453（P-13）；O-05 |

**阈值常量归口**：施工方案 §C.2 钉死唯一权威＝`sovs/sim/tables.py`（BalanceConfig 增
category_quota/fire_support_subquota 两字段行——IMPL-地面 §D.0 :82-83 既有定义的落地欠账，
本轮尚未落地）。本轮偏离登记见 §12。**O-14**（指挥班组「不占步兵配额」与按 category 分桶
不一致）：本 schema 现与伪代码同口径（计入步兵桶）；处置选项 a) 加可选
`exempt_from_category_quota: bool=False`（minor）/ b) 独立 category=5（major），随第二批指挥卡拍板。

---

## §9 与冻结 dataclass 构造参数的逐一映射

| 目标构造器（types.py） | 构造参数数 | schema 侧来源 | 转换 |
|---|---|---|---|
| WeaponTemplate（:165-194） | 27 | WeaponRowModel #3-#29（27 字段**逐一同名**） | restricted_profiles→tuple[(count,pen_bonus),…]；alt_profile→AltProfile；self_defense→SelfDefenseProfile；令牌→IntEnum（TOKEN_VALUE 反查） |
| Armor（:139-148） | 4 | ArmorModel{front,side,rear,top}×2 | 直传 |
| ElementTemplate（:205-220） | 14 | ElementModel #3-#16（一一对应） | weapons→tuple；mounted_armament 键列表→本元素 weapons 解引用 tuple |
| Aura（:197-202） | 3 | AuraModel | kind 令牌→AuraKind |
| UnitTemplate（:223-249） | 25 | UnitCardModel #2,3,5,6,12-30,32（24 项）＋#33 elements（第 25 项） | elements 经 count 展开：`element_templates = sum(((et,)*count …), ())` 扁平元组 |

卡记录层字段（pool/per_card_limit/quota_group/unlock_by/delivery/faction/size_factor_bp/
card_key）不进 UnitTemplate（冻结 dataclass 零改动）——由 card_loader 的 CardRecord
`{unit_template, faction, pool, per_card_limit, quota_group, unlock_by, delivery, provenance}` 持有。
构造方式沿用 air_data.py 冻结构造器先例（:126-127）：逐参数显式构造，缺一键即 TypeError，
完备性由构造承担。**凡 types.py 构造参数增删改 ⇒ card_schema 同批 major+1（§3）。**

---

## §10 D027 作废/降级处置与缺口登记

| D027 原字段 | 处置 | 依据 |
|---|---|---|
| 生存组「轻/重伤适用规则」、火力组「重伤率」 | **作废**（纯血条制，D068） | GDD-00 :357-358 |
| 生存组「士气阈值」 | **作废**（士气四态 v1.1 裁剪） | IMPL-地面 :1737 |
| 机动组「道路/越野速度」 | **降级全局常数＋单位级覆盖位**（卡面存 speed_tier+movement_class 查 BalanceConfig 类级缺省；2026-10-04 PB-52 增三可选覆盖列 terrain_speed_override_bp/reverse_speed_override_bp/road_bonus_override_cm——空=回退类级，推翻 MV-B-01 defer） | tables.py:14-16/:119-132；movement.py 三处消费 |
| 侦察组「侦察值/隐蔽值」 | **合并**——侦测距离＝optics_ground_cm × stealth_factor_bp[stealth_base] 查表；三项收敛为两卡面槽＋一全局表 | sensing.py:44-62；tables.py:22-25 |
| 侦察组「侦听曲线」 | **降级全局常数**（卡面仅 sonar_radius_cm/sonar_rate） | tables.py:61-64 |
| 后勤组「弹药消耗率」「医疗需求（步兵）」 | **不设卡面列**（消耗每发-1；医疗由 cargo_medical_max 载运） | GDD-00 D065/D069 |
| 火力组「穿深±15%浮动」 | **不设**（penetration_at 距离线性插值，无浮动掷——G-2） | combat.py:33-42 |
| G-1 体积系数 | schema 收 size_factor_bp 但**不映射**（无消费点；两个 minor 周期未接线即移除——O-08） | D027 :171 |
| G-5 造价池三选 | 地面卡 pool∈{MAIN,RESERVE}；空降卡 pool=RESERVE（D017）；空军池不适用（航空冻结于 air_data.py） | D027 :169 |

**结论：D027 八组全部字段要么映射进 schema（60＋武器行29），要么有明确登记的作废/降级/缺口依据——
无未处置缺口。**

---

## §11 开放问题登记（与本 schema 相关；全文见施工方案 §I）

O-01 卡数三口径不一致（69 卡基数须首批定稿前复核）｜O-02 mm→0-20 换算细则未定表（全部
pen/armor 实为〔待定〕级，逐项挂 pending）｜O-03 D067 三段判定与冻结两段曲线不一致（数据侧
0-20 刻度不受影响）｜O-04 ZiS-3 quota_group 归桶（拟 HOWITZER）｜O-05 空降两卡 category 与
限份（拟步兵/3）｜O-06 D038 池子方案 A/B 未拍板（点数上限按 A 占位）｜O-08 体积系数长期未接线
即移除｜O-11 template_id 编号方案（苏101~/德201~）为拍板项｜O-14 指挥班组豁免分支（§8）｜
O-15 Bergepanther 牵引吨位三口径（0.1t 刻度下 400/450/250——第二批德救援车落笔前拍板）。

---

## §12 本轮施工偏离登记

| # | 偏离 | 原因与迁移路径 |
|---|---|---|
| D-1 | deck 阈值常量（PER_CARD_LIMIT_BY_CATEGORY/CATEGORY_QUOTA/FIRE_SUPPORT_SUBQUOTA/POINTS_*_CAP）暂居 card_schema.py 模块级，未归口 tables.py BalanceConfig | 施工方案 §C.2 钉死唯一权威＝tables.py，但其 category_quota/fire_support_subquota 两字段行属方案实施顺序第 1 步、尚未落地（本轮 grep tables.py 确认无此二字段）；本轮施工约束「不改任何现有文件」。**迁移路径**：tables.py 落地该两字段行后，card_schema 删除本地常量改从 tables 导入（构建期/运行期同一来源），并同步修订本节与 §8。迁移前 card_schema 为唯一权威，card_loader 不得另抄一份（无双轨）。**状态（2026-10-02 收尾复核）**：仍未迁移——grep tables.py 两字段零命中；首批数据经 card_loader 显式注入阈值加载（tests/test_card_data_first_batch.py `_quota_kwargs`），无双轨未破。 |
| D-2 | pending/provenance 对账校验器（§6.3 强制闭环）未实现 | 对账器属 tools/build_cards.py（管线 CLI，施工方案实施顺序第 3 步），不属本轮 card_schema.py 交付范围；schema 侧 PendingItemModel 与五元组结构已就位。**已消解（2026-10-02）**：tools/build_cards.py 落地引用完整性对账子集（provenance.card_key/field_path/pending_id 三向对账——其文件头自登记）；〔待定〕分级强制闭环对账仍欠（字段分级元数据未挂 Field(json_schema_extra)，§6.1 演进项——同文件头登记，未伪造）。 |
| D-3 | CSV 读取器（int() 显式转换、`;` 分隔、utf-8-sig）未实现 | 同上，属 tools/build_cards.py；本层以 StrictInt/StrictBool/extra="forbid" 承担 pydantic 侧双保险（方案 §B.1）。**已消解（2026-10-02）**：tools/build_cards.py 落地（utf-8-sig 读取、数值列 int() 白名单 `-?\d+` 拦 "7.5"/"1_000"、`;` 分隔、公式注入拦截——§1.5）。 |

---

*v1（2026-10-02）：首轮冻结。字段清单 60＋29、版本规则、配额归属、映射表、吨位 0.1t 粒度、
CSV 拍板随本版一并冻结；偏离登记 D-1~D-3 待后续施工批次消解。*

*登记更新（2026-10-02 收尾）：D-2/D-3 已由 tools/build_cards.py 落地消解（§12 表内逐条
注明）；D-1 复核仍未迁移（tables.py 无 category_quota/fire_support_subquota 两字段行，
唯一权威仍＝card_schema.py）。首批 10 卡数据与 §13 验证记录随同期在库；TECH-00 §8 已同步
标记管线落地（其 §8.1）。*

---

## §13 首批数据待定清单（v1 追加节，2026-10-02——只追加，不改 §1~§12 冻结语义）

> 首批最小卡组＝**10 卡**（P-13 空降两卡＋六类代表卡），数据源＝`data/ground_*.csv`
> ＋`data/decks/{su_min,ger_min}.csv`，产物＝`data/gen/cards_ground.v1.json`（构建期已过
> deck 全量校验）。测试＝`tests/test_card_data_first_batch.py`（本轮
> `python3 -m pytest tests/test_card_data_first_batch.py -q` → 10 passed）。
> 与施工方案 §G 12 卡主案的两点偏离（均因本批任务口径"8~10 张＋指挥班组入六类代表"）：
> ①砍 GER_PZ4H/GER_SCOUT/GER_TRUCK 三卡留第二批（德侧暂缺侦察/卡车，无头对战对称性
> 待第二批补齐——方案 §G 对称性论证仍成立，仅延后）；②指挥班组（SU_COMMISSAR 政委班组）
> 提前入首批（方案 O-13 原留第二批）——aura 通道自此有数据实例；O-14 豁免分支仍按本
> schema 现口径（政委计入步兵桶，per_card_limit=1 卡级覆盖承载 D032 指挥限 1）。

### §13.1 首批卡清单

| card_key | 卡名 | 阵营 | 类别 | 子配额 | 价 | 池 | tid |
|---|---|---|---|---|---|---|---|
| SU_RECON | 步兵侦察排 | 苏 | 侦察 | — | 30 | MAIN | 101 |
| SU_RIFLE | 步枪排 | 苏 | 步兵 | — | 45 | MAIN | 102 |
| SU_PARATROOP | 空降近卫步枪排 | 苏 | 步兵 | — | 60 | RESERVE（LI2） | 103 |
| SU_COMMISSAR | 政委班组 | 苏 | 步兵（指挥） | — | 25 | MAIN | 104 |
| SU_T3485 | T-34/85坦克排（3车） | 苏 | 装甲 | — | 100 | MAIN | 105 |
| SU_ZIS3 | ZiS-3 76mm加农炮连（4门） | 苏 | 火支 | HOWITZER（拟） | 70 | MAIN | 106 |
| SU_TRUCK | 卡车队（ZiS-5，3辆） | 苏 | 防空后勤 | — | 40 | MAIN | 107 |
| GER_GRENADIER | 掷弹兵排 | 德 | 步兵 | — | 50 | MAIN | 201 |
| GER_PARATROOP | 空降猎兵排 | 德 | 步兵 | — | 65 | RESERVE（JU52） | 202 |
| GER_PAK40 | PaK 40 75mm反坦克炮连（3门） | 德 | 火支 | AT_GUN | 65 | MAIN | 203 |

### §13.2 P-xx 待定登记（19 条，与 `data/ground_pending.csv` 逐条一致）

| 编号 | 范围 | 字段 | 本次填入 | 定标来源 |
|---|---|---|---|---|
| P-101 | 空降两卡 | category/per_card_limit | INFANTRY／随步兵默认3 | air_data P-13 拍板回填；限份待 D032 细化（O-05） |
| P-102 | 空降两卡 | 编制（班数/班人数/武器配比） | 3班×10人；苏冲锋枪为主、德 K98＋MP40 | GDD-01 逐卡评审补锚（O-12） |
| P-103 | 首批全部 SQUAD | hp_max 口径冲突 | 按编制人数（8/10/9/10/2） | GDD-03 §1.1"步兵班100" vs IMPL :131"1HP=1人"——数值章节定标 |
| P-104 | SU_ZIS3 | quota_group | HOWITZER | O-04 归桶拍板 |
| P-105 | SU_COMMISSAR | aura.radius_cm | 5000 | 与 melee_range_cm=5000 对表定标 |
| P-106 | 首批全部武器行 | damage（含 alt_profile.damage） | 保守 2~10 | 数值章节伤害曲线（GDD-00 §2 待定） |
| P-107 | 首批全部 pen/armor | mm→0-20 换算 | 首版 (mm+10)//20 | O-02 数值章节统一定表 |
| P-108 | SU_T3485 | armor_he | 暂同 KE（5;2;2;1） | §3.3 仅单一装甲行——HE 甲独立锚 |
| P-109 | 首批全部武器行 | projectile_speed_cm_tick | 史实弹速 m/s×10（3500~8000） | GDD-03 无弹速列；speed=0 弹丸永驻（tick.py:653），故必填 |
| P-110 | 首批全部武器行 | aim/reload/salvo（射速换算） | rpm 换算或装填秒×10；salvo 4~8 | Enlisted 锚（D067）→tick 换算细则 |
| P-111 | 首批全部 SQUAD 武器 | 班内武器聚合口径 | 每类武器一行 | 建模拍板：行=武器类型而非单件 |
| P-112 | ZiS-3/PaK40 炮班 | hp_max/stealth_base | 6／7 | 炮班人数与火炮隐蔽无锚 |
| P-113 | ZiS-3/PaK40 | pack_time_ticks | 300 | 收炮无锚（展开 300 有锚：GDD-02 :451 30 秒 D031） |
| P-114 | SU_TRUCK | seats 口径 | 1（以班为单位） | D065"载1个步兵班"——R-07 mount 落地拍板 |
| P-115 | 空降/掷弹兵/坦克/卡车 | stealth_base | 6/6/3/3 | 仅侦察10、步兵6、狙击10、侦察车4 有卡面锚 |
| P-116 | 首批全部武器行 | dispersion_cm/aim_time_ticks | 散布 200~500／瞄准 3~30 | 无锚保守值 |
| P-117 | SU_RECON 烟罐 | max_range/ammo | 5000cm／2发 | R-06 定量烟雾（GDD-02 :357 烟罐×2/排）；blast=3000 取 tables.smoke_radius_cm |
| P-118 | 首批全部武器行 | ammo_base 聚合/ammo_weight | 见 CSV（莫辛200/主炮24/加农基数6 有锚，余保守）；ammo_weight 暂留 0 | 后勤数值章节＋supply_round_weight 定标 |
| P-119 | SU_T3485 | own_weight_tons | 300（0.1t 刻度） | 锚=R-19"中坦~30吨级"；精确吨位随全表定标 |

> 值级偏离明细见 `data/ground_provenance.csv`（30 条，构建期经引用完整性对账）。
> 有锚不待定的关键值（备查）：卡价全部〔GDD〕GDD-01/GDD-02 卡面；视野 60000/35000/30000cm
> ＝GDD-03 §1.5 米值×100；速度档＝§1.4；T-34/85 hp 90／卡车 30＝§1.1；D-5T 射程
> 100000/装填 80/穿 6/压制 22 与 PaK40 经 KwK40 L/48 同弹种锚＝§2.2；ZiS-3 曲射帽
> 300000/压制 25/溅射 1200/基数 6＝§2.3；步兵武器弹容/射程/压制＝§2.1；吨位 15/13/15
> ＝§1.7×0.1t 刻度（§7）；政委光环 bonus_bp=1500＝GDD-02 :388；近卫班 quality 11500
> ＝§4.4#10 注；敞篷 suppression_vuln 1500＝GDD-03 §1.3"敞篷×1.5"。

### §13.3 首批验证记录（2026-10-02，本机）

- `python3 tools/build_cards.py` → library＋su_min/ger_min 三 JSON 落盘（构建期 deck
  校验 D032/D011/R-13/D038 全过，fail-fast 未触发）。
- `card_loader.load_library(data/gen/cards_ground.v1.json)` → 10 卡全构造冻结
  dataclass（UnitTemplate/ElementTemplate/WeaponTemplate/Armor/Aura），空降对表通过。
- `python3 -m pytest tests/test_card_data_first_batch.py -q` → **10 passed**；
  相邻回归 `python3 -m pytest tests/test_card_pipeline.py tests/test_card_schema.py -q`
  → **64 passed**（按任务约束未跑全量 pytest）。
