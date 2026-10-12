# TECH-00 技术选型与实现方案 v3（评审稿）

> 依据：GDD-00 核心机制（D001~D054）、GDD-01 兵种表、GDD-02 单位细则、GDD-03 人机 AI 系统。
> **v2 变更：应用户拍板，技术栈改选 Python 全栈方案。** v1 的 Unity/C# 结论降级为备选记录（§3.3）。核心架构决策（引擎无关确定性仿真核心）不变且价值更高。
> **v3 变更（2026-10-10）：前端主路线拍板＝方案 B 桌面壳、载体 Arcade 3.3（pyglet+OpenGL）**——v2 的 pygame-ce 起步结论修订为回退备选（用户 FE-T01 拍板，逐分歧点对照表与登记见 §12）。仿真核心 stdlib-only 等架构不变量一字不动。
> 本文只做决策与论证，不含代码。对外调研来源见文末。

---

## 1. 结论先行

| 决策项 | 结论 | 一句话理由 |
|---|---|---|
| 语言 | **Python 3.12+** | 用户拍板；且 AI 结对语料量全场最大（AI 生成代码可靠性最高），数据管线/批量模拟/日志分析天然强项 |
| 仿真核心 | 纯 Python 类库（零渲染依赖），固定步长 10Hz，整型定标，确定性 PRNG | 本作全部难点（联机/回放/批量测试）吃确定性；Python 也在该层被性能隔离 |
| 渲染壳 | **Arcade 3.3**（pyglet+OpenGL，SpriteList GPU 批渲染）——前端主路线（2026-10-10 用户拍板，FE-T01）；**pygame-ce 降为回退备选**（macOS OpenGL 敞口触发时壳层整体替换，§10/§12） | 观战器/可玩壳吃内建 Camera2D/Tiled/GPU 批渲染地基件＋双端纯 wheel 零编译；v2「pygame-ce 起步」结论反转留痕见 §3.1 尾、逐分歧点对照见 §12.2 |
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
| C4 | 90 秒同步盲部署 + 45 秒开局禁火〔**v3 勘正（2026-10-10 评审指正）**：实现现值＝盲部署 **600t（60s）**、开局禁火相位**已取消**（D007/D008 废止——tables.py:266 `phase_ticks=(600,13200)`＋tick.py 头注 2026-10-03 拍板）；与 FE-T03 wire/回放文件头 phase_ticks 同值，登记见 §12.11〕 | D007/D008 | phase 状态机：部署/禁火/实战/结算（现值：部署/实战/结算） |
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

> **〔v3 反转留痕（2026-10-10）〕** 上表与本结论（pygame-ce 起步）为 v2 决策现场，原样存档不改写。应用户 FE-T01 拍板，前端主路线改为 **Arcade 3.3**（pyglet+OpenGL），pygame-ce 降为 macOS OpenGL 敞口触发时的**回退备选**——升级方向由「pygame-ce→Arcade」反转为「Arcade→pygame-ce（回退）」。逐分歧点对照表见 §12.2，理由与代价见 §12.3，依赖例外登记见 §12.5。

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
5. **phase 状态机**：盲部署(90s)→禁火(45s)→实战(22min)→结算，命令合法性按 phase 校验〔**v3 勘正（2026-10-10）**：实现现值＝盲部署(600t=60s)→实战(13200t=22min)→结算，**禁火相位已取消**（D007/D008 废止，2026-10-03 拍板；tables.py:266＋tick.py 头注）；与 §2 C4 勘正及 FE-T03 wire/回放文件头 phase_ticks 同值，登记见 §12.11〕。

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
| macOS OpenGL 4.1「弃而未删」长期敞口（**v3 主路线新增**：Arcade/pyglet 稳定版全链押 Apple GL，渲染报告 §5.1） | 中 | Apple Silicon 冻结 GL 4.1；macOS 26 官方发布说明仍「OpenGL remains in the SDK」、macOS 27 未见移除条目——今天能跑、短期无虞，但时间线不受本作控制。对策三件套：版本锁定 `arcade>=3.3,<4`＋尖兵基准留档（§12.10 已回填：≈580fps，门 30fps 全 PASS）＋离屏渲染冒烟；在途出路=pyglet 3.0 多渲染后端（Arcade dev 分支已跟进）；**回退路径=壳层整体替换 pygame-ce**（其 CPU blit/SDL_Renderer 路径不经 OpenGL，渲染报告 §2.1） |

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

## 12. v3 前端主路线拍板与表现层登记（2026-10-10）

> 依据：用户 2026-10-10 拍板（FE-T01）；out/2d-game-frontend-report.md（2026-10-01 四方向调查＋独立核查修订版，下称「渲染报告」）；docs/FE-01-断箭界面调研与前端工作任务-v1.md（下称 FE-01）。本节为 v2（2026-09-25 pygame-ce 拍板）的决策修订记录：**只动渲染壳选型与表现层登记，v2 其余结论（确定性仿真核心/命令驱动/数据管线/联机方案）全部不变。**

### §12.1 拍板结论

- **前端主路线＝方案 B 桌面壳（FE-01 §4.2），载体＝Arcade 3.3（pyglet+OpenGL）**。2026-10-10 用户拍板。
- **档位＝一般档**：公共地基（FE-T02 状态帧＋FE-T03 wire/回放格式 v1）＋FE-T06 观战器 v1＋FE-T07 四页可玩壳闭环（配置→盲部署→实战→结算）。
- **TECH-00 v2 的 pygame-ce 拍板就此修订**（§1 渲染壳行已改写、§3.1 原结论留痕）；**pygame-ce vs Arcade 悬案关闭**——FE-01 :174「渲染选型已有调研但成悬案」与 :361（§6.1）就此销案。
- **pygame-ce 降级为回退备选**：仅当 macOS OpenGL 敞口实际发作（尖兵/冒烟不及格，§12.10）时触发壳层整体替换复议——壳层无判定逻辑（v2 §3.1 原文承诺），替换成本受控。
- **FE-T06（观战器）/FE-T07（可玩壳）/FE-T08（卡组编辑器）载体＝Arcade，均追溯到本拍板**（FE-T01 验收条款「FE-T06/07/08 载体可追溯到同一拍板」，FE-01 :263；三任务的「载体随 FE-T01」依赖栏 :304/:312/:320 就此落定）。
- 留痕口径：v2 旧文散在的 pygame-ce 壳提及（§4 架构图「表现壳（pygame-ce）」、§3.2 部署模板编辑器行、§8 同、§9 M0「pygame-ce 壳工程」、§10 性能行「壳层可换 Arcade」）**v3 起一律读作 Arcade 3.3 壳（pygame-ce 为回退备选）**，不逐处改写，以本节为准。

### §12.2 分歧点对照表（FE-T01 验收硬性要求）

两份相左文本逐分歧点对照（FE-01 :263 要求「两份报告逐分歧点列原文主张与拍板结论」）。文本锚点——TECH-00 v2：§1 渲染壳行与 §3.1 结论段「**结论：pygame-ce 起步。**理由同 v1 的 C8 逻辑——单人+AI 结对，语料量决定速度」；渲染报告：§结论速览及 §1/§2/§5。

| # | 分歧点 | TECH-00 v2 主张（原文口径） | 渲染报告主张（原文口径） | v3 拍板（2026-10-10） |
|---|---|---|---|---|
| 1 | 起步壳 | 「pygame-ce 起步」；§1 行「备选 Arcade（OpenGL，精灵多时快 2~3 倍）」 | 「**首选 Arcade 3.3**（pyglet+OpenGL，SpriteList GPU 批渲染）」（§结论速览） | **Arcade 3.3 主路线**；v2 结论反转（§3.1 留痕） |
| 2 | 决定性理由 | 语料量：「单人+AI 结对，语料量决定速度」（C8 逻辑）；「pygame-ce 语料与生态最简」 | 三个地基件：SpriteList **全 GPU 批渲染**（§1.1）；**内建 Camera2D/grips/Tiled 加载**（§1.2，pygame-ce 无内建相机与 tilemap）；**纯 wheel 零编译**（§1.3） | 采纳报告侧：观战器/可玩壳 v1 第一天就要相机平移缩放、批量精灵重绘、迷雾/烟区叠加——内建地基件省的是自研工作量；语料量缺口由尖兵实测＋AI 结对消化 |
| 3 | 性能观 | 「本作 ≤600 实体、10Hz 慢节奏战术，两者性能都富余」 | pygame-ce＝SDL2+CPU blit 无批渲染、「数千同屏精灵是 CPU 瓶颈」（§2.1）；Arcade 官方称数千运动精灵（§1.1） | 维持 v2 判断：本作规模两者都够——性能**不是**反转的决定性理由，仅作 Arcade 加分（图块＋面板＋特效＋迷雾层叠加后余量更大） |
| 4 | 升级/回退方向 | 「若 M2 实测吃紧，仅替换壳层为 Arcade」——pygame-ce→Arcade 单向预留 | Arcade dev 分支已迁 pyglet 3.0 多后端（§1.4/§5.1）；pygame-ce GPU 排在未发布 3.0（§2.1） | 方向反转：**Arcade→pygame-ce 为回退方向**（macOS GL 敞口触发，§12.1）；前向演进押 pyglet 3.0 多后端成熟 |
| 5 | macOS OpenGL 敞口 | 未列（v2 风险表无此条） | Arcade 跑在「弃而未删」的 GL 4.1 上——确定事实链＋「时间线不可控，这是选 Arcade 的主要对价」（§1.5/§5.1） | **如实入账**：登记 §10 风险行＋缓解三件套（§12.3）＋尖兵门（§12.10）。 pygame-ce 侧无此敞口（CPU blit/SDL_Renderer 不经 OpenGL，§2.1）——这正是它被保留为回退备选的原因 |
| 6 | pygame-ce 侧已知问题 | 未列 | Retina/HiDPI 模糊 issue #1456（2021-11 开启至今未修）＋无内建相机/tilemap（§2.1） | 计入回退切换成本：回退不是免费的，HiDPI 模糊＋地基件自研两笔账预先认下 |
| 7 | 双端部署 | 未展开（打包走 §1 PyInstaller） | 四候选双端 wheel 全就绪零编译（§4.1）；「OpenGL 的平台风险完全集中在 macOS 一侧」（§1.3，Windows GL 3.3≪驱动 4.6） | 采纳：敞口收敛为 macOS 单侧；Windows+NVIDIA 零风险 |

### §12.3 选 Arcade 的理由与代价（两份报告论据的消化）

**理由（按权重排序）**：

1. **内建地基件直接命中 FE-T06/FE-T07 第一批需求**：Camera2D＋grips（观战器平移/缩放/跟随/屏震）、Tiled 经 pytiled-parser 直载（对齐 §8 已拍板的 Tiled 管线）、SpriteList GPU 批渲染（≤600 实体＋图块＋迷雾层＋UI 重绘同屏）——pygame-ce 这些全要自建（渲染报告 §1.2/§2.1）。
2. **双端纯 wheel 零编译**（渲染报告 §1.3/§4.1）：对单人+AI 结对工作流，环境摩擦小即速度。
3. **维护活跃**：3.3.3 发布 2025-10、仓库 2026-09-30 仍有推送（渲染报告 §1.4 独立核查值）。
4. v2 的语料量论据（C8）**仍被承认但降级**：判为「可由 AI 结对消化、随时间收敛」的软劣势，非硬约束——pygame-ce 语料优势主要兑现在教程/SO 答案数量（渲染报告 §1.5 如实注明 Arcade 社区声量小于 pygame 系）。

**代价（诚实清单）**：

1. **信息密集 UI 自绘成本**：卡组编辑器/单位详细卡/结算面板等信息密集界面无现成控件层，逐个自绘效率显著低于 Web（这正是 FE-01 §4.1 给方案 A 的最大加分项）。缓解：本档位 UI 面收在四页闭环（配置/盲部署/实战 HUD/结算）；FE-T08 卡组编辑器本阶段后置（§12.6），立项时再评自绘深度 vs 简化形态。
2. **macOS OpenGL 长期敞口**（渲染报告 §1.5/§5.1，已入 §10 风险行）。缓解三件套：**版本锁定 `arcade>=3.3,<4`**（大版本内不漂移；Arcade/pyglet 大版本迁移属破坏性变更）＋**尖兵基准留档**（本机 macOS GL 4.1 实测 fps，§12.10）＋**离屏渲染冒烟**（无窗口渲染自检，防驱动/环境静默劣化）；终极回退＝壳层整体替换 pygame-ce。
3. **社区声量小于 pygame 系**：教程/SO 答案少（渲染报告 §1.5）——由 AI 结对＋官方文档对冲。

### §12.4 架构不变量（v3 重申，一字不动）

- **sovs/sim 保持 stdlib-only**：运行时零第三方 import；pydantic 仅构建期 `card_schema.py:40` 一处（文件级白名单不变）——FE-T02 新增 `state_frame.py`、FE-T03 新增 `wire.py` 两文件同样 stdlib-only。
- **渲染层只经 FE-T02 状态帧与 FE-T03 wire 消费仿真，绝不直读 World**——防「前端直读 World 看全图」作弊面（FE-01 §2.7 迷雾不对称陷阱；迷雾口径复用见 §12.7）。
- v2「表现壳可整体替换、不参与判定」承诺不变——本次 pygame-ce→Arcade 主备互换本身即该承诺的一次兑现演习。

### §12.5 表现层依赖例外登记（FE-01 §3.2.8 条款）

- pyproject **新增可选依赖组 `fe = ["arcade>=3.3,<4"]`**（`[project.optional-dependencies]`；**由尖兵任务同步落盘，本节只作登记与口径冻结**）。
- 隔离纪律：arcade 只允许出现在 **sovs/ui/ 包（新建）与 tools/ 入口脚本**；sovs/sim、sovs/ai 不得 import arcade；安装面=`pip install -e ".[fe]"`，纯仿真/测试环境不装。
- sim 运行时 stdlib-only 不动——FE-01 §3.2.8（:208）：「桥接层如需…须作为表现层例外在 TECH-00 v3 显式登记并隔离在 sovs/sim 之外」，本节即该登记。
- 登记时点依赖盘面：运行依赖仅 `pydantic>=2.13`（构建期校验层，pyproject.toml:12）＋可选组 `xlsx`（openpyxl 备用前端留位）；`fe` 为第三个可选组、第一个渲染依赖。FE-T02/03 同批连带 pyproject 补注册 `sovs.ui` 包。〔**落地留痕（2026-10-11 回填）**：两件均已落盘——`fe` 组＝pyproject.toml:22（尖兵落盘，`pip install --dry-run ".[fe]"` 解析通过，尖兵报告 §7）；`sovs.ui` 注册＝pyproject.toml:33，现 packages=sovs/sovs.sim/sovs.ai/sovs.ui。原文「现 packages=sovs/sovs.sim/sovs.ai」系登记时点盘面，随补记作废。〕

### §12.6 本阶段范围与任务载体

- **范围（一般档）**：尖兵（out/arcade_spike）＋FE-T02（状态帧）＋FE-T03（wire/回放 v1）＋FE-T06 观战器 v1＋FE-T07 四页可玩壳（配置→盲部署→实战→结算）。
- **后置**：FE-T05（数值拍板＋铺量）、FE-T08（卡组编辑器）本阶段不做；壳内卡组直接用 `data/gen/decks/{su_min,ger_min}.json` 现成产物（data/decks/ CSV 经 §8.1 管线的落盘件，本会话实核两文件在位）。
- **FE-T04 按降级条款执行**（FE-01 :287）：无远端＝工作流文件落库＋本地同命令校验。pytest 1019 绿基线已复跑确认（2026-10-10 本会话实跑 `python3 -m pytest tests -q --no-header` → **1019 passed**，12.23s；与 FE-01 §2 :144 记载一致）。〔**现值前向补记（2026-10-11）**：FE-T02/03/黄金回放/观战器等测试落地后同命令复跑 → **1085 passed**（29.10s）；FE-T06/T07 测试并入后 1136 collected。〔**现值前向补记（2026-10-11·二次）**：GL 窗口/截图 11 项的跳过探针由 `import arcade` 升级为「arcade 可导入＋pyglet 屏幕枚举非空」后，无显示会话环境（合盖/无头）自动跳过而非报错 → 同命令现值 **1125 passed + 11 skipped**；显示可用环境的全量实跑数待环境恢复后回填。基线随任务推进前向滚动。〕〕
- FE-T09 教学局/FE-T10 联机等维持 FE-01 §5 依赖序，不因 v3 提前。

### §12.7 模块边界三条铁律（实现期守卫）

1. **sim 零渲染且新增两文件保持 stdlib-only**：`sovs/sim/state_frame.py`（FE-T02）与 `sovs/sim/wire.py`（FE-T03）不 import arcade/pydantic（pydantic 例外仅 card_schema.py:40 白名单不变；本会话实核 sovs/sim 内 pydantic import 唯此一处）。
2. **渲染全部落 sovs/ui＋tools 新壳层**：绘制代码不 import sovs/sim、取数只经状态帧。**Replayer/world_tick/KevPlayer 等仿真驱动只存在于 tools 两入口的 session 胶水层**——此句明写进文件头注，防实现者把仿真驱动放进 sovs/ui 触发自家守卫（渲染层不得反向驱动仿真）。
3. **命令唯一通道＝cmd_bus→queue_command（tick.py:2038）**，人机同管线——壳层按钮与 AI 决策走同一入队口，无旁路。

与既有代码的接缝（全部有先例）：

- **迷雾口径**：复用 state_view 的 spotted_mask 位过滤口径（`(u.spotted_mask >> my_team) & 1`，sensing.py 唯一写者——sovs/ai/state_view.py:4-5；FE-T02 收拢为 sim 公共 API，不重复实现）。〔**落地留痕（2026-10-11 FE-T02）**：收拢点已落地＝sovs/sim/state_frame.py:133 `(u.spotted_mask >> view) & 1`（迷雾唯一事实源 types.py spotted_mask、唯一写者 sensing.py 口径不变）；state_view 重构为本帧之上的 AI 摘要档，原引旧行号 :89 随重构失效。〕
- **回放世界构造**：复用 kev_game_demo——golden 合成卡 template_id＝**301/302/303/305/306/307**（kev_game_demo.py:61-108 实测集，304 未用）**不在任何数据文件**（实卡=101-107/201-203，data/gen/cards_ground.v1.json 本会话实核 10 张、id 集恰为 [101..107,201..203]），故 Replayer 走 **scenario→构造器显式注册表＋dotted path 惰性导入**；deck 清单仅作重建后一致性断言。
- **tools 导入**：按 PEP 420 namespace package 即可导入——tools/ 无 `__init__.py`（本会话实核），tests/ 四处 `from tools import` 先例同证（test_card_pipeline.py:29/test_morale_effects.py:39/test_card_data_first_batch.py:25/test_map_pipeline.py:32）。
- **KEV 接入**：复用 `KevPlayer(client=None)` 规则兜底（sovs/ai/kev_player.py:49 签名默认）与 LocalKevEngine 进程内推理降级链（sovs/ai/kev_local.py:74；MPS/CUDA 失败自动回退规则兜底，AI-01 §1）。

### §12.8 实施顺序（依赖理由）

**尖兵先行**（实测 Arcade 在本机 macOS GL 4.1 的 fps；不及格线触发壳层回退复议，§12.10）→ **TECH-00 v3 收口**（本节：pygame-ce vs Arcade 分歧点对照表＋arcade 依赖例外＋TECH-00 旧计时勘正＋FE-01 两处批注）→ **FE-T02/FE-T03 同批**（互不依赖、互同构；连带 pyproject 补 sovs.ui 包注册）→ **arch 测试＋CI 文件＋黄金回放**（九令显式编排注入——构造行口径＝sovs/ai/actions.py:137/144/151/157/161/164/169/265/268（AirCallCmd/AirStrikeCmd/AirAirdropCmd/AirPatrolCmd/AirEngageAirCmd/AirRTBCmd/AirAltCmd/AirMoveCmd/AirDisengageCmd 九行实测锚点）＋录后覆盖核对，双保险）→ **FE-T06 观战器 v1** → **FE-T07 四页可玩壳** → **美术需求文档**（指挥班组识别位缺口立项时钉死）。

### §12.9 风险登记（四处）

1. **macOS OpenGL 长期敞口**（渲染报告 §5.1）——已入 §10 风险行；对策=版本锁定＋尖兵基准留档＋离屏渲染冒烟；**壳层可整体替换至 pygame-ce**。
2. **wire 命令解引用七类引用面**：命令对象携带活引用，wire 编码必须解引用、解码必须重建。拍板点名三处：AirCallCmd 的 AircraftTemplate 活引用→**AIR_CARDS 注册表**（air_data.py:397）解引用；`payload["PARATROOP"]` 的 UnitTemplate 活引用→**deck 槽位**重建（构造先例 actions.py:131-137——:136 `payload["PARATROOP"] = slot.template` 执行期换装、:137 AirCallCmd 构造；本表 2026-10-11 行号复核，原引 :132-135 系护栏段不含赋值行）；GarrisonCmd.building 活引用→**building_id** 重建（tick.py:1680-1682，字段即活对象）。其余引用面由 FE-T03 wire schema 设计时逐类枚举，七类全清单在 FE-T03 交付物落定。〔**落地留痕（2026-10-11 FE-T03）**：七类全清单已落 sovs/sim/wire.py 文件头——unit/element/player/aircraft/PurchaseCmd.template（deck_slots 身份解析）/AirCallCmd.template（AIR_CARDS）＋payload PARATROOP（deck_slots，None 保持 None）/GarrisonCmd.building（building_id）；另 AttackCmd.target 建筑位分立 `target_building_id` 键（cmd_attack 建筑资格门＝tick.py:3100 `isinstance(target, Building)`，本会话行号复核）；encode 侧出现七类外引用即报错、decode 侧 fail-fast；35 支/35 类闭合清单 AST 守卫＝tests/test_wire.py。〕
3. **LocalKevEngine 与渲染同进程 GPU 争用**：1Hz 决策节拍预期无碍（AI-01 §7 真机前向 p50 88ms 记载）；登记**子进程回退**——FE-T07「内嵌推理与渲染同进程还是子进程隔离，开工时写死」（FE-01 :310），若实测争用即选子进程。
4. **describe_command 等价回归**：AI 决策日志命令描述符改由 wire schema 生成（FE-T03），断言口径＝**「AI 已发出命令子集的旧键等价、允许新增键」**——不要求键集冻结，防格式演进锁死。

### §12.10 尖兵基准回填（2026-10-11 回填，实测值出处＝out/arcade_spike.md＋本会话复跑）

- 载体：`out/arcade_spike/bench.py`（尖兵任务已落盘，2026-10-11 本会话实核在位）。回填纪律不变：**以下数值全部出自尖兵报告与实跑，无估算值。**
- 环境实测（尖兵报告 §1）：arcade **3.3.3**＋pyglet **2.1.16**（`pip install "arcade>=3.3,<4"` 一次成功）；GL 上下文 **(4,1)**，GL_VERSION 串 `4.1 Metal - 90.5`，渲染器/厂商＝`Apple M5`/`Apple`（Apple Silicon 经 Metal 转译层，macOS 常态上限）。
- **离屏基准（1500 精灵×300 帧，隐藏窗 1280×720，含每帧位置重传）**：尖兵 3 连跑 **579.8 / 584.5 / 583.0 fps**（exit 全 0）；**2026-10-11 本会话复跑同门 584.3 fps、PASS、exit=0**——即 ≈**580 fps**，为判定门（fps≥30，bench.py:25/:74）的 **19 倍余量**。
- 诚实登记（档位口径）：尖兵按「1500 精灵单层 SpriteList」一档交付（1500＞本作 ≤600 实体上限，属上限档），**未含图块层/迷雾层/UI 面板合成**——原计划「本作量级/压力」两档收敛为单档上界覆盖，实景合成负载留 FE-T06 观战器再验。
- **离屏渲染冒烟**：`offscreen_png.py` 2 连跑 OK（5 精灵中心像素＋背景色逐像素复核正确）；`window_smoke.py` 可见窗 60 帧开-关干净退出 exit=0（产物 window_smoke.png/offscreen_png.png 在位）。
- 判定门结论：**全部 PASS，不触发壳层回退复议（§12.1）**。
- 副作用登记（尖兵报告 §6）：arcade 拖入 pillow 11.3.0（自 12.3.0 降级，与 pdfplumber 0.11.10 的 Pillow>=12.2 约束冲突）——本仓运行依赖未含 pillow 主版本承诺，CI/前端环境独立 `pip install -e ".[fe]"` 即隔离；待观察项不阻塞。

### §12.11 勘正登记（文档间一致性收口，2026-10-10）

1. **TECH-00 §2 C4 与 §4 规则 5 旧计时口径**（评审指正）：原文「90 秒同步盲部署+45 秒开局禁火」「盲部署(90s)→禁火(45s)→实战(22min)」已按实现现值就地批注——**盲部署 600t（60s）、禁火相位已取消**（tables.py:266 `phase_ticks=(600,13200)`＋tick.py 头注 2026-10-03 拍板：盲部署 90s→60s、取消开局禁火相位，D007/D008 废止）；与 FE-T03 wire/回放文件头 phase_ticks 同值。FE-01 §6.4 待拍板项只覆盖 GDD-00 批注，TECH-00 这两处此前无主，随 v3 一并收口。
2. **FE-01 :278-279「38 个分派支/35 类命令」勘正为 AST 实测 35 支/35 类**（2026-10-10 本会话 AST 复核证实：`_dispatch_command`（tick.py:2052）内 Cmd 型 isinstance 分派支 **35 个**、去重命令类 **35 个**）。差异成因〔**推测**〕：38 或系另计入三处单位级队列 isinstance 位（tick.py:2278 cmd_cancel 队列清写／:2413／:2415 consume_unit_commands 消费位，三处实核在位），**FE-01 原文未记载计数方式，无从确证**。复核注：tick.py 全文 Cmd 型 isinstance 在 `_dispatch_command` 之外实有四处（上述三处＋:2419 SprintCmd elif 位），35+3=38 仅在取三处口径下成立——益证「无从确证」。FE-T03 roundtrip 覆盖口径以 **35 支/35 类** 为准。
3. **FE-01 :270「整米化」收敛为 AI 摘要档行为**：整米化（`// 100`，pos_m/dist_m）是 situation_brief/compact_brief 的 **AI 摘要档**行为（sovs/ai/state_view.py:48/:70 实核〔FE-T02 落地 2026-10-11 行号复核更新——原引 :51/:73 系重构前旧行号〕）；**FE-T02 公共状态帧坐标保持 int cm（原始整型厘米），不复用整米化**——FE-T02 契约句「复用…spotted_mask>>my_team 口径与整米化」读作「复用 spotted_mask 口径；整米化不进公共帧」。**落地留痕（2026-10-11 FE-T02）**：公共帧 sovs/sim/state_frame.py 落地（帧头 schema_version/tick/phase/view；player_index=None 裁判全知/队号迷雾裁剪；无 max_units 截断），state_view 重构为在本帧之上做 AI 摘要档（截断+整米化+中文字段名，迷雾口径单实现）；双档对照机器断言＝tests/test_state_frame.py::TestFieldSpot::test_unit_pos_keeps_cm_precision_vs_ai_brief（帧 pos_cm==cm 原值、brief pos_m==//100）。

---

## 变更记录

- 2026-10-11：v3 补记三件＋勘正一处——①§12.10 尖兵基准回填：arcade 3.3.3＋pyglet 2.1.16（GL 4.1 Metal，Apple M5）离屏 1500 精灵×300 帧，尖兵 3 连跑 579.8/584.5/583.0fps＋本会话复跑 584.3fps，判定门 fps≥30 全 PASS（≈19 倍余量），**不触发壳层回退复议**；单档交付口径（未含图块/迷雾/UI 合成）诚实登记；pillow 11.3 降级副作用入账。②落地留痕前向补记：§12.5 pyproject `fe` 组（:22）与 `sovs.ui` 包注册（:33）已落盘；§12.7 迷雾收拢点＝sovs/sim/state_frame.py:133（state_view 旧行号 :89 失效）；§12.9.2 wire 七类引用面全清单＝sovs/sim/wire.py 头注（AttackCmd 建筑位分立 target_building_id 键、资格门 tick.py:3100）。③§12.6 测试基线现值：同命令复跑 **1085 passed**（29.10s）。勘正：§12.9.2 PARATROOP 构造先例行号 :132-135→:131-137（赋值实为 :136，本会话行号复核）。④（2026-10-11 终审收口）GL 测试探针升级＋勘正两处——tests 三文件（test_shell_window/test_viewer_window/test_skirmish_shell::TestScreenshotGate）跳过探针由 `import arcade` 升级为「arcade 可导入＋pyglet 屏幕枚举非空」，修复无显示会话下 1 failed＋10 errors 的假红（根因=WindowServer 不可达，非代码）；sovs/sim/wire.py:26 头注 cmd_attack 建筑资格门行号 :3044→:3100（isinstance(target, Building) 实位）；§12.6 现值改记 1125 passed＋11 skipped（无显示环境，见 :285 二次补记）。
- 2026-10-10：v3——应用户 FE-T01 拍板，前端主路线＝方案 B 桌面壳、载体 **Arcade 3.3**（pyglet+OpenGL）；v2 的 pygame-ce 起步结论就此修订、pygame-ce vs Arcade 悬案关闭（pygame-ce 降为 macOS OpenGL 敞口触发的回退备选）。新增 §12：拍板结论（档位＝一般档：FE-T02+FE-T03+尖兵+FE-T06 观战器 v1+FE-T07 四页可玩壳；FE-T05/FE-T08 后置）、逐分歧点对照表（v2 :51 vs 渲染报告 vs 拍板，FE-T01 验收件）、选 Arcade 理由与代价（信息密集 UI 自绘成本、macOS GL 敞口及缓解三件套）、架构不变量重申（sim stdlib-only、渲染只经状态帧/wire 不直读 World）、表现层依赖例外登记（pyproject 可选组 fe=["arcade>=3.3,<4"]，由尖兵同步落盘；渲染代码隔离在 sovs/ui+tools）、模块边界三铁律与接缝先例、实施顺序、风险四处（macOS GL 敞口/wire 七类解引用面/GPU 争用子进程回退/describe_command 等价口径）、尖兵基准回填位（未回填）、勘正登记（§2 C4 与 §4 规则 5 旧计时批注：盲部署 600t、禁火取消；FE-01 38→35 计数勘正与整米化收敛）。§1 渲染壳行改写；§3.1 结论反转留痕；§10 补 macOS OpenGL 4.1 敞口行。仿真核心 stdlib-only 等不变量不动；pytest 1019 绿基线复跑确认。
- 2026-10-02：§1/§8 数据卡管线标记**已落地（首批）**：交换格式拍板 CSV（弃 pandas/openpyxl 读取，改 stdlib csv——逐行可 diff＋严格 int 纪律；Excel/Sheets 仍作编辑前端，pydantic 校验与 JSON 产物两端不变）；新增 §8.1 落地登记（schema 版本入口 card_schema.py、构建 CLI tools/build_cards.py、首批数据 data/ground_*.csv 与产物 data/gen/、仿真侧加载入口 card_loader.py、余欠登记）。决策级架构不变。
- 2026-09-25：v2——应用户拍板改 Python 全栈：Python 3.12+ / 仿真核心纯 Python / pygame-ce 壳（备选 Arcade）/ asyncio 中继联机 / pandas+pydantic 数据管线 / PyInstaller 发行。新增 §3.2 代价清单与 §6 性能预算表。v1 Unity/C# 结论降级为 §3.3 备选记录。
- 2026-09-25：v1——初版（Unity 6 LTS + C# 确定性仿真核心 + lockstep/Steam 中继）。
