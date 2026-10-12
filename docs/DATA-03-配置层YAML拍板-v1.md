# DATA-03 配置层 YAML 拍板 v1

> **拍板声明**：本文档是「配置面交换格式由 CSV 改为 YAML」这一拍板变更的唯一权威
> （GP-01 §1/§2 的数据层落点）。拍板依据：用户 2026-10-12 六件需求之⑥——「所有单位
> 参数变量放入一个配置文件夹的 YAML 文件」；评审⑥要求本变更说明在 GP-01 通过前成文
> 落档（此前仅有 GP-01 §2 的五点骨架）。
> **对 DATA-01 的影响**：DATA-01《地面数据卡 schema 冻结 v1》**降级为「schema 字段
> 权威」**——其 §4 字段清单、§2 版本门、§9 映射表、§6 分级与 sidecar 语义**继续有效**；
> 其 **§1「表格格式拍板：CSV」与施工方案 §E 五表结构（ground_cards/ground_elements/
> ground_weapons 三外键表）自本文档生效之日起废止**，由本文档接管。DATA-01 §1 头部的
> 「唯一权威」冻结声明（:1-5）按本条修正。
> 冻结先例对齐：sovs/sim/air_data.py 头注式声明（:1-33）。

---

## §1 拍板内容

**交换格式＝YAML；编辑前端＝任意文本编辑器/编辑器页（GP-01 §7）；管线产物＝JSON
（两端不变）。**

- 唯一配置目录＝`data/yaml/`（units/＋decks/＋sidecar/ 三段；文件划分见 GP-01 §1.1，
  此处不重复）。
- YAML 读入＝**pyyaml safe_load，仅构建期发生**（tools/build_yaml.py 与 sovs/app/
  deck_editor.py）；**sovs/sim 永不 import yaml**——sim 运行时 stdlib-only 纪律由
  tests/test_arch_constraints.py ① AST 守卫持续保证，本拍板不触碰该面。
- 构建入口＝`tools/build_yaml.py`（取代 tools/build_cards.py；后者退役留档不删行，
  头注加「被 GP-01 §1.2 / DATA-03 取代」）。CLI：`python3 tools/build_yaml.py
  [--src data/yaml] [--out data/gen]`。

## §2 不变面（CSV 时代的全部硬纪律平移）

1. **pydantic 校验层**＝sovs/sim/card_schema.py 原样复用（UnitCardModel 39 字段/
   ElementModel 17/WeaponRowModel 29/DeckModel）；pydantic import 文件白名单
   `{card_schema.py}`（tests/test_arch_constraints.py:30）**零改动**——航空卡新模型
   AirCardModel 落在同一文件内，白名单不动。
2. **严格 int 纪律**：数值一律 StrictInt（拒 float/str/bool）。YAML 载体的已知行为：
   手写 `1.0` 会被 YAML 解析为 float 再被 StrictInt 拒——与 CSV 时代「拒 "7.5"」
   同强度，实测面平移。
3. **令牌→int 单点映射**：TOKEN_VALUE（card_schema.py:87-108）原样；JSON 产物枚举
   一律 int 表示（DATA-01 §2.4 口径不变）。
4. **JSON 产物两端不变**：data/gen/cards_ground.v1.json / decks/*.json 的结构、键排序、
   加载器（card_loader.load_library/load_deck，stdlib-only）零改动；新增
   data/gen/cards_air.v1.json（航空）走同一模式（新 air_loader.py，仿 card_loader）。
5. **字节稳定重建**：同输入两次构建产物逐字节相等（承 build_cards.py §E.2-4 先例，
   测试锚平移至 tests/test_yaml_pipeline.py）。
6. **版本门语义**：major.minor 与 SUPPORTED_CARD_SCHEMA 支持表不变；本次航空入库＝
   加可选域 minor 演进 **1.3→1.4**（card_schema.py:46-48 与 card_loader.py:43 双写
   同步，tests/test_card_pipeline 互检锁死）。
7. **sidecar 语义**（DATA-01 §6）：provenance（值级偏离）/pending（P-xx 待定）两表
   YAML 化（data/yaml/sidecar/），字段语义与对账范围不变；YAML 注释可就地留痕是
   格式增益。

## §3 变更面

| 项 | CSV 时代 | YAML 时代 |
|---|---|---|
| 单位参数源 | data/ground_{cards,elements,weapons}.csv 三外键表 | data/yaml/units/*.yaml 嵌套结构（elements/weapons 内联，39 字段集不变） |
| 卡组源 | data/decks/*.csv 三列 | data/yaml/decks/*.yaml（DeckModel 字段，schema_version 显式携带） |
| 航空卡 | air_data.py 代码冻结（12 卡冻结声明 :1-33） | data/yaml/units/air_{su,ger}.yaml＋air_weapons.yaml；schema 1.4 增 AirCardModel；air_data.py 薄壳化再出口（wire.py:64 导入面零改） |
| 构建入口 | tools/build_cards.py | tools/build_yaml.py |
| source_sha256 | 源 CSV 拼接哈希 | 拼接 YAML 源文本哈希（审计口径平移） |
| 结构化列编码 | `;` 分隔约定（DATA-01 §1.5） | 废止（YAML 原生列表/嵌套，无分隔符歧义；公式注入白名单随之退役——YAML 标量无 `=` 前缀注入面） |

## §4 迁移与验收

1. **迁移步骤**（GP-01 M1 执行）：建 data/yaml/ 全量 → build_yaml.py 上线 →
   **逐字节相等锚**（现存 10 张地面卡的 YAML 编译产物 cards/pending 数组与现行 CSV
   产物逐字节相等，仅 source_sha256 允许异）→ CSV 移入 `data/legacy_csv/` 归档
   （不删文件，保审计面）→ 全量 pytest 绿。
   〔**M1 执行批注 2026-10-12**〕上述步骤已落地：data/yaml/ 全量（地面 67 卡＝苏 33/
   德 34 表格行数全录＋空降两卡＋航空十卡/七武器档＋decks＋sidecar）；tools/build_yaml.py
   上线（序列化复用 build_cards 纯函数单点）；逐字节相等锚＝tests/test_yaml_pipeline.py
   MigrationByteAnchor（10 卡 cards 子数组＋pending 旧 23 条子序列对
   data/legacy_csv/gen/ 归档产物逐字节相等——根层差异＝source_sha256＋本轮拍板的
   minor 升版 1.3→1.4〔§2.6/GP-01 §1.3〕，归档产物冻结 1.3）；CSV 五表＋deck CSV＋
   旧产物归档 data/legacy_csv/；全量 pytest **1201 passed**（基线 1184＋新锚 17）。
   落库差额不代拟：P-201/202/203＋新卡插值 P-301~P-314 登记
   data/yaml/sidecar/pending.yaml（CAN_AIRDROP_BEACON 侦察卡配属因与 10 卡迁移锚
   互斥登记 P-311 挂 M2——GP-01 §6 落地面拍板）。
2. **回滚**：迁移独立成单提交；回滚＝恢复 CSV 原位＋build_cards.py（依赖未删、
   schema 未动 1.3 面，回滚零阻碍）。
3. **旧回放兼容**：本拍板不改 wire/replay schema；GP-01 M2 的 wire 1.1（ammo/axis）
   与本拍板解耦（先 M1 数据搬家、后 M2 仿真扩面，提交切分）。

## §5 与 GDD-01 落库账目的关系

落库完成度验收＝「表格行数全录＋表外空降两卡在库」（苏 33/德 34 地面管线卡＋航空
十卡）；与「合计 40 卡」的差额（苏-2/德-1）与 DATA-01 头注「69 张」的口径出入，以
pending P-201/P-202/P-203 登记待策划补齐（GP-01 §1.4），**本管线不代拟卡面数值**。

## §6 依赖口径（评审⑦补）

pyproject `[project.dependencies]` 增 `pyyaml>=6`，与 pydantic 同段——**该段定位＝
构建期校验链依赖**。现注「运行依赖仅 pydantic」中「运行」指 sovs/sim 运行时面：
sim 运行时 stdlib-only 由 AST 守卫独立保证，与本段不矛盾；注释文字随本拍板更新为
「构建期校验层依赖：pydantic＋pyyaml；仿真核心运行时 stdlib-only（TECH-00 §3.2/§4）」。
可选组 `xlsx`（openpyxl）与 `fe`（arcade）维持不变。

---

（本文件由 GP-01 v1.1 评审修订随轮创建；后续演进规则沿用 DATA-01 §2——只向后兼容，
改语义须 major。）
