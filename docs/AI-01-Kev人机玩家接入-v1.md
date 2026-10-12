# AI-01 Kev 人机玩家接入 v1（Kev-0.5B，CUDA / Apple Silicon 双端）

**拍板**：人机玩家用 Kev-0.5B（`jaredpalmer/kev-0.5b`，Qwen2.5 底座原型，
Apache-2.0）驱动；架构照《本地模型做人机玩家 AI 调研报告》拍板的分层方案
——**引擎管事实与合法性，模型只做选择**。2026-10-07 落地 `sovs/ai` 包。

## 1. 架构与边界

```
┌─────────────────────────────────────────────┐
│ sovs.sim（确定性整型仿真核心——stdlib-only，  │
│   本接入零改动；命令层门序=最终合法性裁决）    │
└──────────────▲──────────────────────────────┘
               │ queue_command → consume_commands（唯一发令通道）
┌──────────────┴──────────────────────────────┐
│ sovs.ai（新包，stdlib-only，零新增依赖）      │
│  KevPlayer.step(world)  ← HeadlessAI 同构    │
│   ├ state_view   态势摘要（迷雾过滤/整米化）  │
│   ├ actions      合法动作枚举+效用打分        │
│   ├ kev_local    进程内推理引擎（主路径）     │
│   ├ kev_client   /v1/systemone HTTP 客户端    │
│   │             （可选——两载体鸭子类型同口）   │
│   └ decision_log JSONL 决策日志（回放锚）     │
└──────────────┬──────────────────────────────┘
               │ 进程内 import（torch cuda/mps/cpu 自动探测）
┌──────────────┴──────────────────────────────┐
│ kev 仓库（jaredpalmer/kev，pip install -e）  │
│  LocalPredictor：CUDA→torch；Mac→MPS         │
│ （可选 kev.serve HTTP 旁路——同协议）          │
└─────────────────────────────────────────────┘
```

- **KevPlayer 与 tests 侧 HeadlessAI 同构**：每 tick `step(w)`，只经公开命令
  接口发令，零直接写 world、零掷骰（决策侧不触碰 PCG32 通道）。
- **降级链**：无 client / 服务不可达 / 超时 / 返回非法选项 → 同一候选表的
  argmax（效用分最高，确定性）——对局永不因模型侧故障中断。
- **决策节拍**（确定性 tick 门，覆盖完整游戏流程——v2）：
  - 盲部署相位：每 50 拍购卡 choice（FIFO 出生序=排兵次序）+ 错半拍（25/75…）
    排兵 choice（队形令 FormationCmd + 预置展开车道 MoveCmd——地面单位直落
    部署锚点无位置控制，排兵=购卡序+队形+部署期预置机动）；
  - 实战相位：每 100 拍地面动作 choice + 每 150 拍空军调度 choice
    （air_every=0 可禁用——纯地面场景/测试隔离）；
  - 空军节拍两相位都走（B-18 无相位门——部署期即呼侦察/战斗机），结算停。
- **预备队（D017）**：空降卡 DELIVERY_AIRDROP_ONLY 被购卡门恒拒（空裁8），
  唯一投入路径已接入——`call_troop` 候选（运输机 PARATROOP 载荷装机，B-06
  装机即扣卡组份）→ 在空后 `airdrop` 候选（AirAirdropCmd 择点投放：优先
  无主占点，否则敌纵深）。
- **可复现性**：Kev 采样不可跨机逐位复现（bf16 前向+批合并），故复现锚=
  **落盘命令流**（日志逐决策记 tick+命令描述符；回放=种子+命令流，无需模型）。

## 2. 平台兼容（用户要求：CUDA 与 Mac Silicon 都能跑）

| 层 | CUDA 机器 | Apple Silicon | 说明 |
|---|---|---|---|
| sovs.ai 播放器/日志 | ✓ | ✓ | stdlib-only，不依赖 torch/mlx |
| LocalKevEngine 进程内 | torch bf16（CUDA） | MPS（Kev-0.5B 注意力底座正路） | device 自动探测 cuda→mps→cpu |
| kev.serve HTTP（可选） | torch bf16 | MLX 缺省 | 同协议，需起端口服务时才用 |

Python 版本：仓库 ≥3.13（kev 仓库同样钉 3.13；torch 无 3.14 轮子——双仓一致）。
**主路径为进程内推理（不起端口服务）**：`LocalKevEngine` 经 kev 仓库
`LocalPredictor` 直跑，torch/kev 惰性导入——未安装时 sovs.ai 其余功能不受影响。

## 3. 安装与对局

```bash
# 0) 前置（一次性）：clone 并安装 kev 包（torch/transformers 随其依赖装入）
git clone https://github.com/jaredpalmer/kev kev
pip install -e ./kev        # 或不装、用时传 kev_path=仓库路径

# 1) 1Hz 节奏实测（进程内模型；首跑自动从 HF 拉权重缓存）
python tools/kev_bench_1hz.py --engine fallback    # 先自检测试台（零模型）
python tools/kev_bench_1hz.py                      # 真模型每秒一条指令实测

# 2) 无头对局
python tools/kev_game_demo.py                      # 纯规则兜底（零模型依赖）
python tools/kev_game_demo.py --url http://127.0.0.1:8011   # HTTP 路径（可选，
                                                   # 需 python tools/kev_serve.py --start）
```

进程内引擎嵌入：

```python
from sovs.ai import KevPlayer, LocalKevEngine
red = KevPlayer(0, LocalKevEngine("jaredpalmer/kev-0.5b"))  # 进程内，零端口
```

## 4. 嵌入自己的对局代码

```python
from sovs.ai import KevClient, KevPlayer
from sovs.sim.tick import make_world, world_tick

w = make_world(42, phase=PHASE_DEPLOY, size_cm=(200000, 100000))
red  = KevPlayer(0, KevClient("http://127.0.0.1:8011"), log="out/red.jsonl")
blue = KevPlayer(1)                                # 无 client=纯规则
while w.phase != PHASE_SETTLE:
    red.step(w); blue.step(w)
    world_tick(w)
```

构造参数：`anchors`（缺省按地图南北中点推导）、`purchase_every` /
`decide_every`（决策节拍）、`candidate_limit`（choice 选项上限 255 内）、
`log`（JSONL 路径或 DecisionLog）。`player.stats` 记 kev/兜底决策计数。

## 5. 决策日志（out/kev_decisions.jsonl）

每决策一行：`{ts, label, kind: purchase|combat, tick, phase, source:
kev|fallback, confidence, probabilities, latency_ms, candidates[{key,desc,
utility}], commands[{cmd, unit, dest, ...}]}`。审计面=source 比例与选项
概率；回放面=commands 逐条命令描述符（tick 序）。

## 6. 测试与验收

- `tests/test_ai_kev.py`（20 例）：mock kev.serve（stdlib http.server 线程）
  覆盖 wire 格式/认证/错误收敛；播放器购卡/实战全链路；迷雾过滤；候选
  确定性与 wait 恒在场；**同 seed 双跑指纹逐位一致**（规则兜底路径）；
  启动器 `--check` 与参数白名单。
- `tests/test_ai_fullflow.py`（29 例）：排兵（队形/车道/兜底轮转散开）、
  空军三门（点数/同型在空上限/弹药档）、打击集群质心、弹尽返场、
  **预备队全链路**（运输机装机扣份→在空→AirAirdropCmd 落点=无主占点）、
  **上下车**（同点位静止登车/近敌下车/行进中不可登）、**拖曳成链**
  （远敌锚挂拖 SetMode(TOW)+TowCmd→到达解拖+重展开）、**驻楼双向**
  （资格+容量门进驻/无敌情撤出）、**烟幕门**（发数/冷却/在途守卫+耗发）、
  **高度层微操**（战斗机爬升至 ceiling、已至/过渡中不重复）、**次要令**
  （冲刺破压+冷却窗/原地转向首甲迎敌/渗透禁火-见敌自由射击切换/取消族
  全清/反狙击掩护最高价值目标/HAS_SUPPLY 满载装填 D012 闸/信标旗位死
  路如实态/运输机转场空投前置/缠斗脱离战力劣势档）、态势摘要各段。
- `tests/test_ai_local_kev.py`（5 例）：进程内引擎契约（未装 kev →
  KevUnavailableError 含安装指引；鸭子类型直通 KevPlayer）+ 1Hz 测试台
  fallback 模式自检。
- 全量 1001 绿（2026-10-07）——`sovs.sim` 零改动。
- 真模型 1Hz 实测为手动步骤（`tools/kev_bench_1hz.py`，首跑下载权重）——
  不进 CI。

## 7. 1Hz 节奏测试台（tools/kev_bench_1hz.py）

每拍完整链路：态势摘要→候选枚举→模型前向（或规则 argmax）→命令构造→
queue_command→consume_commands 门序落地→推进 10 拍模拟时间（1 实秒↔
1 游戏秒@10Hz），按 --pace 补足节拍。输出整拍周期与模型前向的
min/p50/p95/max、输入 token、实际达成节拍、超预算拍数与 PASS/FAIL。
缺省 60 拍=一分钟；`--pace 0` 为裸延迟压测。

**真机实测（2026-10-08，Apple Silicon MPS + bf16，jaredpalmer/kev-0.5b）**：
- 1Hz 节奏 30 拍：kev=30/30 零兜底，模型前向 p50 88ms / p95 257ms /
  max 260ms（输入 p50 344 token），整拍 max 262ms——**预算 1000ms 富余
  近 4 倍，PASS**；
- 整局实跑（5000 拍，红=kev 蓝=规则）：红方 94 次决策全部真推理
  （购卡13/排兵4/地面43/空军34），整局墙钟 12.3s；时延 p50 101ms /
  p95 248ms；置信度均值 0.54；
- **模型自主性**：94 拍中模型最高概率选项与效用 argmax 榜首一致的仅
  50 拍（53%）——近半决策模型按态势自行判断（如开局空军待命而非急装
  预备队、中期选补给空投），即接入 LLM 的语义增量面。

**0.5B 上下文预算（384 token state）**：`situation_brief` 丰富 dict 态
（约 676 token）会被 admit 422 拒收——KevPlayer 缺省 `rich_state=False`
走 `compact_brief` 紧凑单行文本态（约 250~344 token，行式/字段裁剪/
每方截断 4 单位）；换 4B/9B（state 8k+）时传 `rich_state=True` 即回全量态。

## 8. 已知边界与后续口子

- 候选生成 v4 = **命令族全覆盖**：购卡/排兵（队形+预置车道）/推进/占点/
  攻击/急停/炮击任务/空军呼叫（全五型）/打击/预备队空投/CAP/对空/返场/
  爬升/转场前置/缠斗脱离/上下车/拖曳成链/驻楼/自卫烟幕/**冲刺破压**
  （冷却窗内不生成，期间禁射）/**原地转向**（静止装甲首甲迎敌——
  PB-51 停车转向）/**姿态切换**（渗透期禁火潜行/敌近恢复自由射击）/
  **取消族**（排队令全清 CancelCmd/撤销炮击任务省弹）/**反狙击掩护**
  （CAN_SNIPER_COVER 位掩护最高价值友军）/**买补给装填**（HAS_SUPPLY
  位卡 SetMode(CARGO)+BuySuppliesCmd 满载——D012 混装载重闸内取整）/
  **空投信标**（CAN_AIRDROP_BEACON 位——对现役全卡恒 REJECT 的规划面
  死路径，候选按旗位生成=如实态，旗位补卡后即活）。
- 数据侧旗位缺口（引擎注释明示"现役 0 卡置位"，合成卡测试已验证）：
  CAN_GARRISON/CAN_SNIPER_COVER/HAS_SUPPLY/CAN_AIRDROP_BEACON——
  补卡后候选即活，AI 侧零改动。
- 驻楼候选依赖 world.buildings（apply_map 挂图后才有建筑）；烟幕依赖
  数据卡 self_smoke_charges 配属（现役 SU_TRUCK/SU_T34 各 2）。
- 空军调度三门（冷却/同型在空上限·air_per_type_max=2/空援点数）内生成
  候选——门外的呼叫不进 choice（省一次无效决策）；点数尽时节拍静默。
- Kev-0.5B 为"kept for reference"原型档：格式合法性由协议+引擎门保证，
  决策质量弱于 4B/9B；升级只换 `--model jaredpalmer/kev-4b` 一处。
- 效用分为粗糙启发（档位差 5~55），只决定排序与兜底，不进引擎；兜底
  argmax 只会选最高效用路径（如运输机直投而非先转场），模型可依上下文
  选择低效用候选——这正是接 LLM 的语义增量所在。
- **0.5B 选项陷阱两例（2026-10-08 实测修复）**：① 角色问题里的 wait
  选项是模型躺平牌（空中 435/440、预备队 440/440 全选"待命"，p≈0.5 自信
  躺平）——AgentSquad 三角色已剥离 wait（"做不做"由节拍定，模型只选
  "怎么做"），空中一致率 2/427→50/54；② ferry 转场候选是模型锁死牌
  （273/281 永选转场不投放）——已裁撤（AirAirdropCmd 自带飞行，转场
  冗余）。另增 `min_top_prob` 置信度门控（首选概率低于阈值→argmax，
  缺省关）。修后空中/预备队链路正常，但四块模型班组 vs 规则侧仍 0/8
  （同 seed 规则侧 4/8）——**剩余差距=0.5B 域内判断力，选项工程已到
  天花板**；对外人机建议 `client=None` 规则班组，模型侧提升走蒸馏微调
  （数据管线就绪：决策日志含 state+选项）或换 kev-4b。
- 网络面：客户端仅 http/https、禁重定向、拒 URL userinfo（kev_client.py
  安全面注释）；kev.serve 缺省只绑 127.0.0.1，跨机访问走 `--host` + 
  `KEV_API_KEY`。

## 9. 四块 agent 班组（AgentSquad，2026-10-08）

`sovs/ai/agents.py` 新增 **AgentSquad**：把人机 AI 决策拆给四块专职角色，
`step(world)` 与 KevPlayer/HeadlessAI 同签名（KevPlayer 保留不动，两者并存，
工具侧 `--mode` 切换）。四个角色**共用同一个 client**（KevClient 或
LocalKevEngine），但各有独立的 choice instructions（角色化提示词——地面
指挥官看敌情与占点 / 空中管制官看空援点数与制空 / 预备队参谋看预备队
余份与投送时机），不共用泛化句：

| 角色 | 相位 | 候选面 | 日志 kind |
|---|---|---|---|
| 1 排兵布阵 | 盲部署（开始前） | purchase_candidates + deploy_candidates（购卡 %50、排兵错半拍——沿用 KevPlayer 现制，不要求 1Hz） | purchase / deploy |
| 2 地面单位操作 | 实战（开始后） | enumerate_candidates 全部地面候选 | combat |
| 3 空中单位操作 | 实战（开始后） | air_candidates 的纯航空作战子集（呼叫攻击机/轰炸机/战斗机/侦察、strike、CAP、对空、爬升、返场、缠斗脱离） | air |
| 4 预备部队出卡 | 实战（开始后） | air_candidates 的投送链子集（call_troop_*、call_supply_*、airdrop、ferry） | reserve |

- **1Hz 顺序节拍器**：PHASE_COMBAT 每 `squad_every` 拍（缺省 10=1 游戏
  秒 @10Hz）轮到下一个角色，顺序固定 **地面→空中→预备队** 循环；轮到的
  角色当拍一次 choice（或 argmax 兜底，降级链同 KevPlayer）并
  queue_command，其余拍静默；无候选的角色当拍静默、轮转照走。
  PHASE_DEPLOY 只走角色1（角色2/3/4 实战拍起才上场——班组模式无
  KevPlayer 的 B-18 部署期空军呼叫）；PHASE_SETTLE 全静默。
- **air_candidates 拆分**：`split_air_candidates()` 按 kind+key 前缀把
  混合候选表拆成（空中作战， 投送链）两份——归属映射表写成
  `sovs/ai/agents.py` 模块顶部注释；wait 兜底位丢弃，各非空子集自补
  角色化 wait。
- **工具**：`tools/kev_game_demo.py --mode squad` / `tools/kev_bench_1hz.py
  --mode squad`（缺省 player 行为逐位不变）。bench squad 模式取
  `squad_every=1` 对齐测试台"每迭代一拍"结构（warmup 逐拍推进会把 tick
  错出 %10 对齐位），判定逻辑照用，报告附分角色决策计数。
- **测试**：`tests/test_ai_squad.py`（15 用例，零模型依赖）——角色候选
  归属 / 1Hz 轮转序与每 10 拍恰一次+命令真实入队 / 分角色 kev·兜底统计
  与日志 kind·角色化提示词 / 同 seed 双跑确定性 / 工具 --mode squad 接线。
- 断网回退（2026-10-08 班组门修复）：权重已缓存而 Hub 不可达（Errno 60
  连接超时类）时，`LocalKevEngine` 装配自动置 `HF_HUB_OFFLINE=1` 离线
  重试一次——`snapshot_download` 改走纯缓存解析，LoRA 检查点与 base 快照
  均可命中加载（实测 mps/bf16 3.3s）；首次在线下载路径不受影响，
  非网络错误（缺文件等）不触发切换（kev_local.py `_load_predictor` /
  `is_hub_unreachable`，零新增网络代码）。
