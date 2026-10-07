# DATA-02 地形图数据格式冻结 v1

> **冻结声明**：本文档为地形图数据管线（CSV 声明式源表 → 确定性栅格化 → gen JSON →
> 运行期加载）的格式唯一权威（对应实现＝`tools/build_map.py`（构建期）＋
> `sovs/sim/map_loader.py`（运行期，stdlib-only））。此后格式的一切变更只经本文档登记并
> 遵守 §2.3 演进规则（只向后兼容：加行型/加列可以、改语义不行）。冻结先例：DATA-01
> （地面数据卡 schema）。落地：PB-58 块②（2026-10-06；拍板清单 PB-58 行留痕）。
>
> 数值纪律：坐标一律 cm/瓦片索引双轨 int、图幅/瓦片边长 int，**一律严格 int，float/bool
> 必须被拒**（构建期 `-?\d+` 白名单；加载期 `type(v) is int` 白名单——card_loader.py 同款）；
> 禁 float 域运算/math 超越函数/random（栅格化＝纯整数 Bresenham）；随机只走 PCG32 分通道
> ——本管线全链零掷骰。
>
> 实现锚：`sovs/sim/pathfind.py`（TerrainLayer/TerrainTile/三谓词——冻结结构，本格式
> **不改其任何槽位**）；`sovs/sim/tables.py`（`ruin_speed_bp` 占位常数）。测试：
> `tests/test_map_pipeline.py`（56 锚，2026-10-06 本轮 `python3 -m pytest
> tests/test_map_pipeline.py -q` → 56 passed）。

---

## §1 数据流与表格拍板

```
data/map_demo_2km.csv ──tools/build_map.py──▶ data/gen/map_demo_2km.v1.json
        │  (utf-8-sig、stdlib csv、声明式一行一声明)        │ (键排序、瓦片类型 int 表示、
        │                                                  │  (ix,iy) 排序、源 sha256、字节稳定)
        └────────── 手写源表（评审面＝本表，不逐格）          ▼
                                              sovs/sim/map_loader.load_map → MapData
                                              （TerrainLayer＋extent＋tile_cm＋
                                                forest_tiles＋buildings；apply_map 挂点）
```

- 交换格式＝CSV（UTF-8 带 BOM、`\n` 行尾——DATA-01 §1 同拍板）；**声明式**：一行一声明
  （区域矩形/道路折线/建筑锚），**不逐格手写**（80×40＝3200 格不可评审）。
- 构建零 pydantic（地图无 schema 校验层需求——结构校验在构建期手写门+加载期结构门双层承载；
  与 build_cards 的差异系刻意：后者有 39 字段卡模型校验需求）。
- 同输入两次构建字节相等（`dump_stable_json`：键排序＋ensure_ascii=False＋indent=2＋尾换行
  ——build_cards 同式双写，测试锁死）。

## §2 行类型（kind 列分派）与列集

**表头＝17 列固定并集**（乱序可，缺列/未知列拒）：

```
kind,map_key,extent_x_cm,extent_y_cm,tile_cm,type,x0,y0,x1,y1,width,verts,
building_key,x_cm,y_cm,footprint_cm,hp
```

各行型必填列分派（**未用列必须留空**——防错位手写，构建期报错）：

| kind | 必填列 | 语义 |
|------|--------|------|
| `map` | map_key, extent_x_cm, extent_y_cm, tile_cm | 全文件**唯一**必备行；图幅/瓦片边长须为正且**图幅被 tile_cm 整除**（瓦片覆盖无半格——与 pathfind.tile_cost 图界 `(ext+t-1)//t` 口径闭合） |
| `rect` | type, x0, y0, x1, y1 | 瓦片坐标矩形**含端点**（x0≤x1、y0≤y1、图内域） |
| `polyline` | type, width, verts | 道路折线：width＝笔刷宽≥1（瓦片）；verts＝`x:y;x:y;...`（≥2 顶点、图内、无连续重复；**顶点内 `:` 对、顶点间 `;`**——build_cards restricted_profiles 同款结构化列先例） |
| `building` | building_key, x_cm, y_cm, footprint_cm, hp | **PB-57 建筑锚数据位占位**（拍板清单:229「正式建筑布局随 PB-58 地图数据格式后接」）；坐标 cm 图内、footprint≥1、hp≥1（`combat.hit_building` hp≤0 即塌——0 非法）；building_key 全文件唯一、禁 `;`/`:`/公式前缀 |

`type` 令牌集＝`{ROAD, FOREST, RUIN}`（rect/polyline 通用）；缺席瓦片＝旷野（类级缺省）。

### §2.1 瓦片类型语义（三值编码：ROAD=0 / FOREST=1 / RUIN=2）

| 令牌 | TerrainLayer 装配（map_loader） | 依据 |
|------|--------------------------------|------|
| ROAD | `TerrainTile(on_road=True)`，**零 speed_bp 注入** | 速度吃既有机制：MARCH 道路地板（movement.py 取 max，契约⑦）＋prefer_road 代价减半（pathfind.py §2.14）——零造数 |
| FOREST | **不入 layer.tiles**，旁挂 `MapData.forest_tiles` 集合 | §2.12 拍板：森林不减速只喂 sensing——寻路侧与缺席瓦片恒等（三谓词 None/False）。sensing 侧 forest 衰减**已接通**（2026-10-07 感知接线块——terrain_sensing_channels 装配+world_tick ③喂入，林区真实喂探测衰减；原「待接/纯格式示范」表述已过时勘正） |
| RUIN | `TerrainTile(speed_bp=四类同值 cfg.ruin_speed_bp)` | PB-58 ask「废墟/村庄＝可通行减速率占位（标注数值章节定标）」——勘察三选一 (a)屏障/(b)纯标记/(c)减速占位 由 ask 文本裁定为 (c)。`ruin_speed_bp=4000`（tables.py）＝**无据占位待数值章节定标**（选值依据＝使 FOOT/TRACK 对成片废墟产生可观测绕行、全四类受抑——演示取向非平衡定标）；**loader 侧注入非构建期烘焙**：gen JSON 只携带类型标记，调值无需重建数据（单一权威＝BalanceConfig）；置 0 即 bp==0 不可通行（pathfind.py §2.14 口径天然承载——数值章节可选「废墟=实体屏障」档） |

### §2.2 重叠语义（画家算法）

**文件序、后绘覆盖先绘**（跨类型抹除：FOREST 后绘抹掉瓦片表条目；ROAD/RUIN 后绘抹掉
forest 旁挂）。示范图约定行序＝林区→废墟→路网：道路**穿林成道、穿村成街**（后绘路覆盖
林/废墟瓦片）。声明的栅格化序（含折线顶点行进向）即冻结序——同表重构建字节稳定。

### §2.3 演进规则（只向后兼容）

- 加行型/加列＝minor +1（`SUPPORTED_MAP_SCHEMA` 上界抬升；map_loader 双写表同步、
  tests 锁死互检）；改语义（类型重定义/画家序/编码值）＝major +1。
- gen JSON `schema_version` 当前＝`"1.0"`（build_map.SCHEMA_VERSION 单点、
  map_loader.SUPPORTED_MAP_SCHEMA 双写互检）。
- **图幅无关**：图幅是 map 行数据不是格式常数——换 2×2km 方形图零格式改动。

### §2.4 图幅裁决留痕

**示范图图幅＝B 案 200000×100000cm（tile 2500 → 80×40 瓦片，长边 2km）——2026-10-06
发起人默认裁决=B 图幅（未即时作答，可推翻；初记 10-05 系笔误同日勘正）**。依据：PB-58 拍板字面「接入并整局验收」，
B 与现整局验收 `MAP_SIZE`（test_fullgame_acceptance.py）完全同幅、原位替换接入零场景
重建；A 案（方形 2×2km）本轮无具体消费者。附带：①本留痕同步记于拍板清单 PB-58 行；
②格式保持图幅无关（§2.3）；③三要素（路网+林区+村庄废墟）照常齐备。

## §3 gen JSON 结构（map_demo_2km.v1.json）

```json
{
  "schema_version": "1.0",
  "map_key": "demo_2km",
  "source_sha256": "<源 CSV 字节 sha256（审计可复算；测试锁死==实际文件哈希）>",
  "extent_x_cm": 200000, "extent_y_cm": 100000, "tile_cm": 2500,
  "tiles": [[ix, iy, type], ...],        // 全量瓦片、(ix,iy) 升序唯一、type∈{0,1,2}、全 int
  "buildings": [{"building_key","x_cm","y_cm","footprint_cm","hp"}, ...]   // 文件序
}
```

加载期门（map_loader，fail-fast）：版本门（major/minor 支持表）/根对象/`type(v) is int`
白名单（拒 float/bool/str）/瓦片图内域/瓦片坐标不重复/类型 int 域 {0,1,2}/建筑键唯一/
字符串键门（map_key/building_key 拒空串/公式前缀/含 `;`/`:`——§2 :56 规格的加载期复检，
PB-57 建筑实体块 2026-10-06 补齐：构建期拦截可被手改 gen JSON 绕过）/坐标图内/
footprint·hp≥1。构建期门（build_map）见 §2 各行型＋公式注入拦截（`=`,`+`,`-`,
`@` 前缀）＋int 文本白名单（拒 `7.5`/`1_000`）。

## §4 运行期消费面（挂点）

- `load_map(path, cfg=CONFIG) -> MapData`（map_key/extent/tile_cm/layer/forest_tiles/
  buildings——BuildingSpec 透传记录**非 Building 实体**：id 分配/驻楼槽归 PB-57 集成侧）。
- `load_demo_map(cfg=CONFIG)`：正式示范图便捷入口（块③整局接入挂点）。
- `apply_map(world, md, cfg=CONFIG)`：构造后挂载——`world.terrain=md.layer`＋对齐 map_extent/
  map_center（make_world **不动**、缺省 terrain=None stub 口径保持——勘察③先例
  test_pathfinding.world_with_layer / bench/pathfind_bench.py）；PB-57 建筑实体块
  （2026-10-06）增 buildings 装配：md.buildings → Building 入 world.buildings
  （id=1 起文件序、garrison_slots=楼型派生——2026-10-06 拍板小/中/大楼=1/2/3 排，阈值占位见 tables.py）。

## §5 占位与待办登记

| 项 | 状态 | 去向 |
|----|------|------|
| `ruin_speed_bp=4000` | 无据占位（选值依据见 §2.1） | 数值章节定标；置 0 可切「废墟=实体屏障」档 |
| building 行 footprint_cm=2500 / hp=100 | 格式占位示例值（5 锚＝村庄内可评审布点） | PB-57 正式建筑布局（拍板清单:229 单向依赖本格式——格式已留位，PB-57 收尾不改格式） |
| FOREST 消费链 | sensing forest 衰减已接通（2026-10-07 感知接线块） | 探测距离按林格衰减即刻生效 |
| Tiled 编辑器管线 | 未建 | 将来策划制图层（PB-58 拍板原文；本 CSV 格式为其手写前置档） |

## §6 本轮施工留痕

- 块①（限幅保险丝）先行落地：`pathfind_max_expansions=500000`（tables.py）——与本格式
  无耦合；2km 示范图档（3200 格）限幅是保险丝而非现痛。
- 测试 56 锚全绿（含「提交 JSON==重构建字节」防手改漂移锚、瓦片类型计数指纹
  {ROAD:213, FOREST:648, RUIN:256}、三类别绕 V2 横带+独立 Dijkstra 最优仲裁、
  WHEEL 直穿 vs FOOT 绕行 V1 对比、prefer_road 真上路、SOUTH 部署锚点护栏、零掷骰）。
- 登记表：sovs/sim/tick.py 模块 docstring「正式示范地形图数据管线」条目（2026-10-06）。
- PB-57 建筑实体块（2026-10-06）：§3 加载期门补字符串键门（map_key/building_key——
  构建期拦截可被手改 gen JSON 绕过，消费 building_key 前收口）；`apply_map(world, md, cfg)`
  增装配——md.buildings（BuildingSpec 文件序）→ Building 实体入 world.buildings
  （id=1 起文件序、hp=building 行、garrison_slots=楼型派生（2026-10-06 拍板小/中/大楼=1/2/3 排
  ——§5 表 building 行「PB-57 正式建筑布局」去向的实体侧收口；格式零改动：无新列、
  schema_version 不升，garrison_slots 权威=tables.py 楼型档+阈值，调值免重建）。
