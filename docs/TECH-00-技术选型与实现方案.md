# TECH-00 技术选型与实现方案 v2（评审稿）

> 依据：GDD-00 核心机制（D001~D054）、GDD-01 兵种表、GDD-02 单位细则、GDD-03 人机 AI 系统。
> **v2 变更：应用户拍板，技术栈改选 Python 全栈方案。** v1 的 Unity/C# 结论降级为备选记录（§3.3）。核心架构决策（引擎无关确定性仿真核心）不变且价值更高。
> 本文只做决策与论证，不含代码。对外调研来源见文末。

---

## 1. 结论先行

| 决策项 | 结论 | 一句话理由 |
|---|---|---|
| 语言 | **Python 3.12+** | 用户拍板；且 AI 结对语料量全场最大（AI 生成代码可靠性最高），数据管线/批量模拟/日志分析天然强项 |
| 仿真核心 | 纯 Python 类库（零渲染依赖），固定步长 10Hz，整型定标，确定性 PRNG | 本作全部难点（联机/回放/批量测试）吃确定性；Python 也在该层被性能隔离 |
| 渲染壳 | **pygame-ce**（社区版，legacy pygame 已停更）；备选 Arcade（OpenGL，精灵多时快 2~3 倍） | 本作 ≤600 实体、10Hz 慢节奏战术，两者性能都富余；pygame-ce 语料与生态最简 |
| 联机 | 确定性 lockstep + asyncio 中继服务器；M4 评估接 Steam 网络绑定 | 只传指令不传状态；Python 写中继服务器是强项；Steam 绑定为非官方库（风险已列） |
| AI | GDD-03 方案不变；AI 作为"虚拟玩家"走同一条命令接口 | 人机/人人/机机共用管线；机机批量对战=免费平衡工具 |
| 并行模型 | 仿真单线程（GIL 无碍），批量机机对战用多进程 | 10Hz×600 实体单线程绰绰有余；批跑天然多进程 |
| 数据 | CSV（Excel/Sheets 编辑前端）→ stdlib csv 读取 → pydantic 校验 → JSON（数据卡管线**已落地首批**，格式拍板见 §8） | D027 字段终表直接映射；AI 效用表/部署模板/难度参数同管线 |
| 发布 | PyInstaller（onedir）打包 Steam 发行 | Python 游戏 Steam 发行成熟路径；备选 Nuitka（更快+更强保护） |

---

## 2. 从 GDD 推导出的技术硬约束（v1 §2 原样有效）

| # | 约束 | 出处 | 技术含义 |
|---|---|---|---|
| C1 | 2D 纯顶视角 | D033 | 渲染层轻；视线/迷雾用 2D 多边形与纹理方案 |
| C2 | 排级粒度，每方 20~40 排（排内 2~4 计数单位） | D006/D009 | 实体总量 ≈150~300/方，**性能不是瓶颈**，架构简单优先 |
| C3 | 对战优先：遭遇战(AI)+多人对战 | D022 | **确定性仿真**是硬需求（lockstep） |
| C4 | 90 秒同步盲部署 + 45 秒开局禁火 | D007/D008 | phase 状态机：部署/禁火/实战/结算 |
| C5 | 视野=侦察÷隐蔽、荫蔽、烟雾、声测圈 | D003/D021/R-03/R-06 | 情报系统是核心玩法：视线计算与信念黑板首日架构 |
| C6 | 25 分钟标准局 | D019 | 仿真 tick 10Hz（15000 tick/局），AI 决策预算充足 |
| C7 | 命中/穿深逐发掷骰 | D023/D024 | 随机数必须确定性可控（分通道 PRNG） |
| C8 | 单人开发 + AI 结对工作流 | 现状 | **Python 在 C8 上是所有候选里最强的**——这是本次选型的决定性加分项 |

---

## 3. 引擎/渲染壳选型论证

### 3.1 Python 栈内部对比

| 维度 | pygame-ce（推荐） | Arcade（备选） |
|---|---|---|
| 维护状态 | **活跃维护**（社区版；legacy pygame 自 2024.9 后停更，社区官方建议迁移） | 活跃 |
| 渲染方式 | SDL 光栅/批量 blit（正演进 SDL3） | OpenGL GPU 加速，精灵密集时快 2~3 倍 |
| API/语料 | 最简、教程语料最大（C8 加分） | 现代 API、类型标注好 |
| 适配本作 | ✅ 600 实体+大量 UI 面板，绰绰有余 | ✅ 烟雾/炮火特效更轻松 |
| 升级路径 | — | 壳层可整体替换，仿真核心不动 |

**结论：pygame-ce 起步。** 理由同 v1 的 C8 逻辑——单人+AI 结对，语料量决定速度。若 M2 实测特效/重绘吃紧，仅替换壳层为 Arcade（架构上壳层无判定逻辑，替换成本受控）。

### 3.2 Python 路线的代价与对策（诚实清单）

| 代价 | 严重度 | 对策 |
|---|---|---|
| 运行时性能比 C#/C++ 慢 10~100 倍 | **中**（本作规模下可控） | ① 性能预算表（§6）：10Hz tick 预算 100ms，实体量级实测富余 10 倍以上；② 热点隔离：视线多边形/A* 集中在独立模块，预留加速接口；③ 若实测不足，按"单模块"逐个换 Numba/Cython/Rust(PyO3)——仿真核心对上层接口不变 |
| GIL 限制并行 | 低 | 仿真单线程即可（C2/C6）；批量机机对战用 multiprocessing（每进程一局，天然隔离） |
| 跨平台确定性陷阱 | **高（必须根治）** | 与 C#/Unity 同款纪律+Python 特有两条：仿真核心**禁用 float 与 math 库超越函数**（sin/cos 跨平台实现有差异——用整型三角表/预计算表）；**不用 random 模块**，自研整型 PRNG（PCG32）按事件流分通道，杜绝解释器版本差异 |
| 打包体积大（80~200MB）+ 杀软误报 | 低 | PyInstaller onedir+SteamPipe 发行；误报走 Steam 签名解决；Nuitka 可同时优化体积/性能/保护 |
| 编辑器工具链比 Unity 弱 | 中 | **地图用 Tiled**（免费开源，TMX/JSON 导出，通行代价/目标点/部署区用自定义属性表达）；部署模板编辑器写为 pygame-ce 独立小工具（复用渲染壳代码） |
| Python Steam 网络绑定为非官方库（现代 P2P API 覆盖不齐） | 中 | 联机主方案=自研 asyncio 中继服务器（Python 强项、部署一个轻量 VPS 即可）；Steam 大厅/好友邀请经绑定库（py_steam_net/SteamworksPy）打通，绑不动则降级为"房间码直连" |

### 3.3 已否决/降级备选（记录在案）

- **v1 方案（Unity 6 LTS + C#）**：C8 之外全面不劣于 Python，但用户已拍板 Python。注意：v1 的全部架构决策（确定性仿真核心/命令驱动/AI 虚拟玩家）在 Python 方案中原样保留——**若未来性能或发行受阻，仿真核心可平移回 C#/Unity**，这是本架构的保险。
- **Godot 4 C#**：同 v1 结论（可行备选，语料一档小）。
- **Photon Quantum 3**：仅适用于 Unity/Unreal/C#，Python 栈下出局。

---

## 4. 核心架构：确定性仿真核心（v1 §4 原样保留，语言改 Python）

```
┌──────────────────────────────────────────────┐
│ 表现壳（pygame-ce）：sprite/特效/音频/UI/相机     │  可整体替换，不参与判定
├──────────────────────────────────────────────┤
│ 外壳层：输入采集→命令 / Tiled 地图加载 / 工具应用  │
├──────────────────────────────────────────────┤
│ 命令层：玩家命令 & AI 命令，同一条队列/同一接口     │  ← AI 是虚拟玩家
├──────────────────────────────────────────────┤
│ 仿真核心（纯 Python 包，零渲染依赖）：            │
│   固定步长 10Hz · 整型厘米坐标 · PCG32 分通道     │
│   战斗判定 D023/D024 · 士气 D014 · 视野 D003     │
│   后勤 R-18/R-19 · 空军 D015 · 胜负 D002        │
├──────────────────────────────────────────────┤
│ 数据层：JSON 数据卡/效用表/模板（pandas 管线产出） │
└──────────────────────────────────────────────┘
```

确定性规则（从第一行代码起执行）：

1. **固定步长**：仿真 10Hz，渲染自由帧率插值。
2. **整型定标**：世界坐标整型厘米，时长= tick 数；仿真核心禁 float、禁 math 超越函数（整型三角表/查表替代）。
3. **确定性 PRNG**：自研 PCG32（整型实现，跨解释器版本稳定），全局种子派生按事件流分通道的子流（命中/侦察/散布各一条）。
4. **命令驱动**：仿真只消费命令；回放文件=种子+全部命令。
5. **phase 状态机**：盲部署(90s)→禁火(45s)→实战(22min)→结算，命令合法性按 phase 校验。

---

## 5. 联机方案（v2 修订）

- **模式**：确定性 lockstep，命令经中继广播；RTS 玩家对输入延迟容忍度高（行业共识）。
- **中继（主方案）**：**自研 asyncio 中继服务器**——Python 异步生态最成熟的一块，一台轻量 VPS 即可服务本作规模（命令包小、10Hz）；协议=帧号+命令广播+掉线等待。
- **Steam 集成（M4 评估）**：大厅/邀请/好友经社区绑定库（py_steam_net、SteamworksPy）接入；绑定库对现代 ISteamNetworkingSockets 覆盖不全（非官方维护），**网络传输本体不押注在绑定库上**，降级路径=房间码直连。
- **掉线处理**：lockstep 下等待/断线重放（种子+命令流即可续），首版不做预测回滚。
- **时间线**：M1 起按确定性写，联机本体 M4（对齐 D022：先单人可玩，架构不后置）。

---

## 6. 性能预算表（Python 路线的定心丸）

10Hz 单 tick 预算 100ms，目标占用 <30ms：

| 每tick工作 | 量级估算（600 实体） | 预算占比 |
|---|---|---|
| 单位状态推进/命令消费 | 600 次轻量更新 | ~5% |
| 命中掷骰/伤害结算 | 接战对数量级，百次内 | ~5% |
| 视线判定（节流：每排 0.5s 一次，错峰） | ~40 排/tick 内摊薄 | ~30% |
| A* 寻路（按需+路径缓存+节流） | 每 tick 个位数次查询 | ~20% |
| 三张图重绘（敌情 2s/次，威胁/通行 5s/次） | 摊薄到每 tick | ~10% |
| AI 决策（L2 每 2~5s、L3 每 0.75s，非每 tick） | 摊薄 | ~15% |
| 余量 | — | ~15% |

超预算时的升级顺序：**先算法（节流/缓存/空间哈希）→ 再单模块 Numba/Cython → 最后 Rust PyO3**；每一步上层接口不变。

---

## 7. AI、寻路与视线的实现载体（GDD-03 设计不变，载体改 Python）

| GDD-03 组件 | 实现载体 | 说明 |
|---|---|---|
| L4 排级行为树 | 自研迷你行为树（节点=类，树=JSON） | 数百行量级；树文件数据化=策划可调 |
| L3/L2 效用系统 | JSON 权重表 + 纯函数打分器 | pydantic 校验，调平衡不重启开发流程 |
| L1 信念黑板 | 仿真核心内纯 Python 数据结构 | AI 感知走确定性接口 |
| L1 三张图 | 20~50m 网格整型数组，节流重绘 | 影响力图经典三分类 |
| 寻路 | 自研网格 A*（代价=地形+威胁权重），路径缓存 | 规模小无需 flow field |
| 视线/迷雾 | 判定=2D 阴影投射多边形（仿真核心内）；渲染=低清纹理+模糊衰减 shader/表面 | 判定与渲染分离 |
| 决策日志 | 单行 JSONL + 回放联动；**pandas/notebook 做调参分析** | Python 的独有强项 |
| 批量平衡 | multiprocessing 批跑机机对战 → CSV → notebook 出图表 | D038 池子规模等数值拍板的量化基础设施 |

---

## 8. 数据管线与工具清单

| 工具 | 形态 | 服务对象 |
|---|---|---|
| 数据卡管线 | **已落地（首批，2026-10-02）**：Excel/Sheets 编辑前端 → **CSV（UTF-8 带 BOM）**交换格式 → stdlib `csv` 读取 → pydantic 校验（字段/配额 D011/D032/限份）→ JSON（落地登记见下） | D027 兵种表 80 卡 + AI 效用表 + 难度参数包 + 部署模板 |
| 地图编辑 | **Tiled**（免费开源）+ 自定义属性规范（通行代价/目标点/部署区/声测点）→ 导出 JSON | 五点图（D020）×多张地图 |
| 部署模板编辑器 | pygame-ce 独立小工具（复用壳层代码） | GDD-03 L0 的 3 变体×特化×地图 |
| 回放器 | 种子+命令流回放，时间轴拖动+AI 日志联动 | AI 调参、bug 复现、观战/复盘 |
| 批量模拟器 | 无头跑机机对战 N 局（multiprocessing）→ CSV → notebook 图表 | 一切数值拍板 |
| 测试/CI | pytest（含跨平台确定性哈希比对用例）+ GitHub Actions | 确定性回归 |

### §8.1 数据卡管线落地登记（2026-10-02，首批）

- **格式拍板**：交换格式＝CSV（UTF-8 带 BOM，`\n` 行尾；列表列 `;` 分隔），**弃用
  pandas/openpyxl 读取**，改 stdlib `csv`。理由：① 仓库非 git，纯文本逐行 diff 是唯一
  审计面（数值调参高频，逐值变更须可审计）；② 本机实测未装 pandas，且其 dtype 推断会把
  int 列静默升 float——与「严格 int、float 必须被拒」硬约束直接冲突；xlsx 为 ZIP 二进制
  diff 不可读。Excel/Sheets 仍作编辑前端（`utf-8-sig` 导出）。**pydantic 校验与 JSON 产物
  两端不变——收窄的只是中间读取器，属实现选择而非架构变更**（拍板成文：DATA-01 §1、
  施工方案 out/card-schema-plan.md §E.4/§F）。
- **schema 版本入口**：`sovs/sim/card_schema.py`——`SCHEMA_VERSION="1.0"`＋
  `SUPPORTED_CARD_SCHEMA={1:0}` 版本门（fail-fast）；唯一权威冻结文档＝
  `docs/DATA-01-地面数据卡schema冻结-v1.md`（演进规则：只向后兼容）。
- **构建 CLI**：`tools/build_cards.py`（CSV → 类型转换/公式注入拦截 → pydantic 校验 →
  键排序稳定序列化 JSON；同输入两次构建字节相等）。
- **数据与产物（首批 10 卡，含 P-13 空降两卡）**：源＝`data/ground_{cards,elements,
  weapons,provenance,pending}.csv`＋`data/decks/{su_min,ger_min}.csv`；产物＝
  `data/gen/cards_ground.v1.json`＋`data/gen/decks/{su_min,ger_min}.json`。
- **仿真侧加载入口**：`sovs/sim/card_loader.py`——`load_library()/load_deck()/
  validate_deck()`；stdlib-only 不 import pydantic（校验在构建期完成，运行时信任 JSON＋
  冻结构造器 TypeError 兜底），deck 阈值显式注入（无双轨）。
- **余欠登记**：① 阈值常量归口 tables.py BalanceConfig 未迁（DATA-01 §12 D-1，现行唯一
  权威＝card_schema.py）；② 字段分级元数据与〔待定〕强制闭环对账部分欠（DATA-01 §6.1
  演进项、tools/build_cards.py 文件头登记）；③ 69 卡全量与 AI 效用表/部署模板/难度参数包
  仍走本管线待后续批次。

---

## 9. 里程碑映射（v2，对齐 GDD-03 §9）

| 里程碑 | GDD-03 目标 | 技术任务 |
|---|---|---|
| **M0（1周）** | — | 仿真核心骨架：tick/命令队列/phase/PCG32 通道/JSON 加载；pygame-ce 壳工程；pytest+CI 就位 |
| **M1 可打（3周）** | AI 不站着不动、不自杀 | 移动(网格A*)+接敌+判定(D023/D024)+士气(D014)+视线(D003)+盲部署模板×1特化；回放格式定型；确定性哈希自测 |
| **M2 像回事（4周）** | AI 会守C争B、会反炮 | 效用分配+预备队/空军调度+炮击任务(R-13/R-14)+后勤(R-18/R-19)+迷雾渲染+Tiled 管线；性能预算实测 |
| **M3 像人（4周）** | 中档难度五五开 | 难度参数包五档+渗透/骑兵分群+决策日志查看器+批量模拟器 nightly |
| **M4 联机（2~3周）** | D022 多人对战 | asyncio 中继+lockstep 会话+掉线等待+同步哈希校验；Steam 绑定评估（大厅/邀请） |
| **M5 发行准备** | — | PyInstaller/Nuitka 打包+SteamPipe 构建脚本+音效/UI 打磨+教学关 |

---

## 10. 风险清单（v2）

| 风险 | 等级 | 对策 |
|---|---|---|
| 确定性漂移（Python 特有：math 库跨平台差异、random 模块跨版本差异） | **高** | §4 整型定标+禁 float+禁 math 超越函数+自研 PCG32；M1 起每局状态哈希比对+跨平台 CI 用例 |
| 仿真/表现耦合回潮 | 高 | 仿真核心独立包、无渲染导入（import 约束用 CI 静态检查） |
| 性能不达标 | 中 | §6 预算表+热点隔离；升级顺序算法→Numba/Cython→Rust PyO3；壳层可换 Arcade |
| 单人范围失控 | 中 | 严格 M0→M5；D046/D026 等"槽位保留"同样适用技术侧 |
| AI 调参工作量被低估 | 中 | 决策日志+批量模拟器是 M3 交付物 |
| Steam 绑定库不可靠 | 中 | 中继自研 asyncio 为主；绑定库只做大厅/邀请；降级=房间码直连 |
| 声测/侦察手感不对导致返工 | 中 | C5 玩法假设在 M1 就做最小可玩版试玩验证 |

---

## 11. 来源

1. [pygame-ce 社区维护状态（legacy pygame 停更，官方建议迁移）](https://github.com/lordmauve/pgzero) / pygame-ce PyPI 发布记录
2. [Pygame vs Arcade 性能对比 2025](https://generalistprogrammer.com) / [Arcade 官方 pygame 对比文档](https://api.arcade.academy)
3. [Gaffer On Games: Deterministic Lockstep](https://gafferongames.com) / [snapnet.dev: Netcode Architectures](https://www.snapnet.dev) / [gamedev.net: Lockstep Protocol](https://www.gamedev.net)
4. [kaa.readthedocs: Python 游戏打包上 Steam](https://kaa.readthedocs.io) / [Arcade: Bundling with PyInstaller](https://api.arcade.academy) / [PyInstaller 官方文档](https://pyinstaller.org)
5. [HeatXD/py_steam_net](https://github.com/HeatXD/py_steam_net) / [SteamworksPy](https://philippj.github.io/SteamworksPy/) / [Steamworks 官方网络文档](https://partner.steamgames.com)（现代 P2P API 覆盖情况）
6. [Alex Champandard: The Core Mechanics of Influence Mapping](https://www.gamedev.net/tutorials/programming/artificial-intelligence/the-core-mechanics-of-influence-mapping-r2838/) —— 三张图方法论
7. Red Blob Games 视线/可见性方法论（2D 阴影投射）
8. [Wikipedia: Broken Arrow](https://en.wikipedia.org/wiki/Broken_Arrow_(video_game))（品类参照）

---

## 变更记录

- 2026-10-02：§1/§8 数据卡管线标记**已落地（首批）**：交换格式拍板 CSV（弃 pandas/openpyxl 读取，改 stdlib csv——逐行可 diff＋严格 int 纪律；Excel/Sheets 仍作编辑前端，pydantic 校验与 JSON 产物两端不变）；新增 §8.1 落地登记（schema 版本入口 card_schema.py、构建 CLI tools/build_cards.py、首批数据 data/ground_*.csv 与产物 data/gen/、仿真侧加载入口 card_loader.py、余欠登记）。决策级架构不变。
- 2026-09-25：v2——应用户拍板改 Python 全栈：Python 3.12+ / 仿真核心纯 Python / pygame-ce 壳（备选 Arcade）/ asyncio 中继联机 / pandas+pydantic 数据管线 / PyInstaller 发行。新增 §3.2 代价清单与 §6 性能预算表。v1 Unity/C# 结论降级为 §3.3 备选记录。
- 2026-09-25：v1——初版（Unity 6 LTS + C# 确定性仿真核心 + lockstep/Steam 中继）。
