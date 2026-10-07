# 单位移动机制伪代码 v1.1（MOVEMENT_PSEUDOCODE_v1.1）

> **基于 v1 + 审查问题文档修复**（v1 原样保留为 docs/MOVEMENT_PSEUDOCODE_v1.md；本轮 15 条——blocker 1 / gap 4 / ambiguity 10——逐条修复记录见文末 §R）。
> 上游：docs/GDD-06-断箭单位移动机制调研.md（差距 37 条 MOV-GAP-01…37 + 02b + 冻结契约 22 条，本文逐条处置）
> 冻结基准（只读）：GROUND_UNITS_PSEUDOCODE_v1.7.md（§0 数据结构 78 槽、§2/§F5 移动族）、GROUND_UNITS_PSEUDOCODE_IMPL_v1.7.md（§T/§D.0/§D.4/§F5）、
> AIR_UNITS_PSEUDOCODE_IMPL_v1.4.md（§T/§D.0 航空 38 字段/§F1~§F7）、GDD-02-单位功能细则-v1.9.md（R-09/R-12/R-19 等既定规则）、GDD-00-核心机制.md（D001/D014/D023/D026/D031/D045/D047/D063/D065/D068）；
> 代码集成点基准（只读）：sovs/sim/movement.py、air.py、geom.py、types.py、tables.py、rng.py、tick.py；
> 锚点测试基线（2026-10-01 实跑）：`python3 -m pytest tests/test_movement.py tests/test_air_curves.py tests/test_air_behavior.py -q` → **66 passed**——本文全部增量不得破坏。
>
> **槽位账目（v1.1，GAP-1 勘误后口径）**：地面 UnitInstance 运行时 **+4**（move_mode / command_queue / group_speed_cap / formation_shape）→ 单位运行时 **17→21**、地面总账 **78→82**。
> 基数勘误注记：types.py UnitInstance 实有 **17** 字段（types.py:291-308，含 sprint_until；GAP-1——v1 误记 16）；GROUND_UNITS_PSEUDOCODE_IMPL_v1.7 §D.4（:176）同记 17。
> 机制版 v1.7 §0 记"单位运行时 16"系两基准 sprint_until 归口差：机制版 §0 把 sprintUntil 列在**元素级** ElementInstance（v1.2 方案14 原位）；
> IMPL v1.7/代码按 v1.7 GAP-18 把它归口 **UnitInstance.sprint_until**（types.py:308，元素级槽删除）——**本文一律按代码/IMPL 口径 17 记账**（分项差 1 行、总账 78 两版一致）。
> 航空运行时 **+0**（21 维持）；新枚举 **2**（MoveMode / FormationShape）；地面移动命令 **+5**（MoveCmd/HaltCmd/CancelCmd/ReverseCmd/FormationCmd）、航空命令 **+0**；
> BalanceConfig **移动段新常数 +6 字段**（§4，与航空 38 字段分账）+ **删除登记 1**（crit_mob_minor_mult_bp——MOV-GAP-14 连锁死常数）；
> PRNG 通道 **+0**——移动机制**零随机**（§6，契约⑰天然满足）。
> **拍板编号消歧（AMB-10）**：本文自有拍板项一律前缀 **MV-B-**（v1.1 起 MV-B-01…MV-B-23）；引用他档拍板项带档名前缀（AIR-B-22/AIR-B-29① 指 AIR_UNITS_PSEUDOCODE_IMPL_v1.4 §B）。
> **只读约定（契约⑲）**：GROUND/AIR IMPL 两份定稿与 sovs/sim 既有函数一律只读；本文只登记差距处置与**增量登记**（每条注明插入点行号与不动部分），
> 不改写任何既有契约；伪代码改动的落地以增量补丁另立，本文即登记账本。
> **整型纪律（契约⑮⑯）**：全篇 cm / tick（10Hz）/ bp 万分比，`×n // 10000`；禁浮点禁三角函数；方向表达只用 DIR8/PERP8/octant_deg/angle_diff 家族。

---

## §T. 移动侧整型补充约定

| 项 | 约定 |
|---|---|
| 速度 | cm/tick 整型；档位表 `cfg.speed_table_cm_tick=(0,25,45,70,100,140)`（tables.py:14，档 1..5——契约①，不另立速度标尺） |
| 乘区 | 一律 bp 万分比、`// 10000` 整数除法；**多条 bp 乘区串接次序冻结**（整数逐级舍入位级确定——见 §2.3 求值顺序 v2） |
| 朝向 | 整型度 0..359 + 8 扇区（octant_deg）；倒车/facing 表达不引入连续角速度（转向渐进归射击侧 rotate_step，§2.13） |
| 方向 | DIR8/PERP8/scale/dir_index（air.py:31-46）整型向量族——队形偏移/超射程进位航点推导沿用，不引入弧度 |
| 随机 | 移动零掷骰；寻路确定性（插入序列表遍历，§T 地面约定沿用）；无新 PRNG 通道（契约⑰） |
| 除法 | round_div（geom.py:53-58）——队形居中偏移用 `(2n+d)//(2d)` 半舍入，负偏移同样确定 |

---

## §1. 差距处置对照表（MOV-GAP-01…37 全量留痕；adopt=方案落点见§2/§3，defer=拍板预登记表§7，reject=本表留痕）

| # | 断箭要点 | 本作现状（已核） | 处置 | 落点 |
|---|---|---|---|---|
| MOV-GAP-01 | 五形态显式移动指令 | 无模式槽；move_path 仅航点（types.py:297）、tick.py:366 调 system_move 无模式参 | **adopt** | §2.1 MoveMode 槽 + §2.2 指令族；RTB 地面版除外（见 02b） |
| MOV-GAP-02 | FastMove=沿路+道路档+弃掩体 | 道路取 max 已实现（movement.py:36-37）但调用侧从不传 on_road | **adopt** | §2.6 强行军接线 on_road（只接线不改乘区——契约⑦） |
| MOV-GAP-02b | 地面 RTB 回出生点退款 | D001 一命制不可撤回无返还 | **reject** | 储备制经济核心分野维持；无承载 |
| MOV-GAP-03 | 倒车独立第三速度档+保持正面 | 无倒车槽；facing 随位移即时统一（movement.py:80-87） | **adopt** | §2.7 倒车 bp 乘区（不另立档位——契约①）+ facing 锁定增量 |
| MOV-GAP-04 | AttackMove 遇已发现敌停下射击 | move_path 直推无接敌暂停 | **adopt** | §2.5 attack_move_engage_hold 谓词（暂停预算、不动副作用链；保持期感知口径见 MV-B-23） |
| MOV-GAP-05 | Shift 队列令串联移动与动作 | move_path 天然承载移动队列；跨动作排队无结构；consume_commands 未实现（tick.py:363 TODO） | **adopt** | §2.2 command_queue 槽 + consume_commands 骨架（含 handoff 内部通道——BLK-1 修复） |
| MOV-GAP-06 | E 全清是痛点，社区要独立停止键 | stance 与 move_path 分槽（types.py:297/:300） | **adopt** | §2.2 HaltCmd/CancelCmd 两命令（MV-B-18） |
| MOV-GAP-07 | 每单位路/野/倒三元组 | 速度档单值+类级地形系数（tables.py:115-128；WHEEL 5000/TRACK 7000 与断箭实测同向） | **defer** | MV-B-01 |
| MOV-GAP-08 | 两栖布尔+水中极慢+水域硬边界 | MovementClass 四值无两栖位（types.py:108-113）；D026 无水域参数 | **defer** | MV-B-02（若做须扩枚举/加旗标——契约②） |
| MOV-GAP-09 | 森林不减速度（只影响隐蔽/视线） | terrain_speed_bp 瓦片注入接口已留未接线（tables.py:115-121 stub） | **adopt** | §2.12 数据口径成文：森林瓦片不注入速度 bp（零代码、零常数） |
| MOV-GAP-10 | 加速度/转向率字段（疑占位） | turn_rate_deg 死槽（types.py:234，sim 无消费者）；facing 即时统一 | **reject** | §2.13 成文：移动侧不消费 turn_rate_deg；渐进转向归射击侧 rotate_step（IMPL §F5 :1051-1058 规划内） |
| MOV-GAP-11 | Shock 仍可下令移动 vs PINNED 不可动 | D014 四态已拍板 PINNED=无法移动（GDD-05 A4 系误传） | **defer** | MV-B-03（现行拍板维持，dispatch 门引用未来士气槽） |
| MOV-GAP-12 | 冲刺完全禁射+可破压制 | 疾跑=升 1 档钳 5 已实现（movement.py:26-27），无禁射联动 | **adopt**（禁射）/ **defer**（破压制） | §2.10-8 射击侧门（挂点=system_timers——GAP-3 修复）；破压制 MV-B-04 |
| MOV-GAP-13 | 炮兵超射程自动进位到最大射程再开火 | 展开互锁已实现（movement.py:54-55）；进位 QoL 未实现 | **adopt** | §2.11（auto_approach_standoff_cm 出表；安装走 issue_move——AMB-3 修复） |
| MOV-GAP-14 | Mobility 暴击变慢/趴窝维修可除 | D068 纯血条已拍板，但 movement.py:22-24/:33-34 仍消费 CritSlot.MOB（代码漂移） | **reject**（暴击系统）+ **替换** | §2.3：拆除 MOB 读取，替换 HP≤25% 单阈值减半（契约⑩）；combat.roll_crit 连锁拆除登记 §8 |
| MOV-GAP-15 | 无队形指令（RMB 拖拽定朝向宽度） | formation_offset_fn 队形偏移已实现（movement.py:88-92）——比断箭强 | **adopt**（队形表）/ **defer**（到达朝向令） | §2.8 队形标准库；到达朝向令 MV-B-05 |
| MOV-GAP-16 | 混编不自动对齐最慢单位（社区负面） | 无编组结构；排级+队形偏移下实现成本低 | **adopt** | §2.9 group_speed_cap 槽（MV-B-15；跨队列令保持——BLK-1 修复） |
| MOV-GAP-17 | 车辆固体碰撞挤死卡死（桥梁重灾区） | 无碰撞体（仅队形偏移+拖曳固定偏移防重叠） | **reject** | §2.15 成文维持无碰撞体 |
| MOV-GAP-18 | 倒车令不覆盖旧令是真 bug；ALT 查当前令 | 命令层未实现，无当前执行令查询位 | **adopt** | §2.2 覆盖硬规则（含 handoff 例外通道）+ current_order 推导式查询位（零新槽） |
| MOV-GAP-19 | 炮塔行进开火带惩罚；冲刺绝对禁射 | D023 moveFactor 已有；D047 rotating 已承载；sprint 未联动 | **adopt**（口径成文） | §2.10-9 三句口径，零新机制 |
| MOV-GAP-20 | 载具毁自动跳车概率伤亡 15%→30% | D045/R-07 已拍板扣 60% 血存活（tables.py:57） | **reject** | BA 15%/30% 仅登记参照锚点，不改动 |
| MOV-GAP-21 | 下车部署延迟曾有后删（现行即时）；装载可排队 | 上车 20s 已拍板（tables.py:58）；下车耗时无拍板 | **defer** | MV-B-06；装载排队随 §2.2 队列承载 |
| MOV-GAP-22 | 桥不可破坏（口径冲突并存）；水域硬边界 | 无桥梁/水域地图机制条目 | **defer** | MV-B-07 |
| MOV-GAP-23 | 官方 Detection 无移动项 vs 本作已实现移动×5000bp（更严，自设） | sensing.py:20-23/:48-49 两乘区是 D066 猎兵/侦察车前提 | **defer** | MV-B-08（移动侧改动不得单侧删除——契约⑳；与 MV-B-23 连锁） |
| MOV-GAP-24 | 遇障逼近/城区错路/贴地蹭障三大寻路痛点 | 寻路整体未实现（move_path 命令直填） | **defer** | MV-B-09 + §2.14 接口预留（find_path stub 落点已登 §9——AMB-8 修复）；教训成文：接敌"逼近"策略已由攻击前进显式成文（§2.5），侧移让射界不承诺 |
| MOV-GAP-25 | L 键画线定攻击轴 | AIR-00 已拍板目标推导走廊（_run_points DIR8，air.py:561-566） | **reject** | 契约⑬维持；§3.3 成文 |
| MOV-GAP-26 | 攻击令前至少 1 航点对齐；贴目标太近炸弹落前方 | cmd_air_strike 自动生成 INGRESS 段 flight_plan=[run_start]（air.py:603）；run_start 距目标 8000cm | **adopt**（维持成文） | §3.3 设计依据注释成文，零改动 |
| MOV-GAP-27 | 全机两档高度 V 切换 | D063 三层已实现（AltTier/alt_pending/entry_tier） | **reject** | 契约⑫维持；§3.2 成文 |
| MOV-GAP-28 | 加力 ×2 速 ×2 油耗；燃油耗尽弹射 | 1944 活塞机无加力；无燃油槽（弹尽自动 RTB 承载，air.py:923-931） | **reject** | 契约⑪维持单值速度；速度档另立拍板 MV-B-20 |
| MOV-GAP-29 | 干扰弹自动抛撒+手动机动 | 1944 无干扰弹/雷达告警；规避=高度+RTB+云层 | **reject** | 时代置换；无承载 |
| MOV-GAP-30 | 真实转弯圆（圆内攻击令死循环、对齐 5-8s） | facing 即时 octant（air.py:554-556）；INGRESS 结构已防死循环 | **defer** | MV-B-10（含整数转弯率推荐方案草图与三个兼容问题清单；除零守卫已补——AMB-7 修复） |
| MOV-GAP-31 | 留空/待命行为（弹尽自动 RTB 演化） | 弹尽自动 RTB+资格门（侦察豁免）已实现（air.py:923-931） | **adopt**（维持成文） | §3.6 成文，零改动 |
| MOV-GAP-32 | RTB 折价退款+社区冷却公式 | D015 租借制已实现（air.py:420-442、tables.py:103-105） | **adopt**（维持本作模型） | §3.6 成文；BA 公式仅参照 |
| MOV-GAP-33 | 直升机常驻 RTS 单位 | 1944 无直升机（GDD-04 #29 时代置换） | **reject** | 时代置换；"射程内不前移/低空危险保人"两耦合设计登记存照（未来旋翼机类再启） |
| MOV-GAP-34 | 运输机沿划区逐个跳伞+吊运吨位 | R-21/D015 单点散布模型已定并实现（resolve_airdrop，air.py:874-898） | **reject** | 单点单轮维持；多轮逐机投送如需另拍板 |
| MOV-GAP-35 | 周年补丁火箭/空地导弹免令自动开火 | 防空/缠斗全自动（D055/D060）；对地=手动标定（D015） | **defer** | MV-B-11 |
| MOV-GAP-36 | 无 rally point（两作一致） | 亦无集结点（D001 后方部署区/D017 空投） | **reject** | 维持无 |
| MOV-GAP-37 | 队列可视化/可排队命令集属命令层 | 命令层未实现；alt_pending 条件槽不排队 | **defer** | MV-B-12；口径先成文：高度切换维持即时条件槽不进队列（§2.2/§3.2） |

---

## §2. 地面移动（A 部分）

### 2.1 数据结构增量（新枚举 2 + UnitInstance +4 槽）

```
ENUM MoveMode:            # 移动模式判别槽（GAP-01；不复用 move_path 编码——契约④）
    NORMAL  = 0           # 普通机动（默认；现状行为逐位不变）
    ATTACK  = 1           # 攻击前进（遇已发现敌停下转入射击——GAP-04）
    MARCH   = 2           # 强行军（沿路行军吃道路速度档——GAP-02）
    REVERSE = 3           # 倒车（直线倒驶、保持车头朝向——GAP-03）

ENUM FormationShape:      # 队形形状（GAP-15 adopt；NONE 默认=零行为变化）
    NONE = 0              # 未下令队形：formation_offset_fn=None（与现状 movement.py:91-92 同点堆叠一致）
    LINE = 1              # 横队（沿行进垂线展开）
    COLUMN = 2            # 纵队（沿行进反方向串列）
    WEDGE = 3             # 楔形（楔尖在前、成对左右递增纵深——§2.8 式）

STRUCT UnitInstance 增量（types.py:291-308 既有 17 槽零改动，其后追加 4 槽；GAP-1 勘误：
                          既有数按代码/IMPL §D.4（:176）口径=17 含 sprint_until——头注注记）:
    move_mode: MoveMode = MoveMode.NORMAL          # 写点=命令族（§2.2）+ dispatch 到达复位（§2.4）
    command_queue: list[Command] = []              # 排队令链（GAP-05/18；consume_commands 消费）
    group_speed_cap: int = 0                       # 编组速度钳制（0=无；GAP-16——§2.9）
    formation_shape: FormationShape = FormationShape.NONE   # 队形形状（FormationCmd 写；dispatch 读）
    # 生命周期口径：move_mode 属"当前移动令"——move_path 耗尽即由 dispatch 复位 NORMAL（§2.4 末行）；
    # command_queue/group_speed_cap/formation_shape 跨令持续（formation_shape 直至下 FormationCmd；
    # group_speed_cap 由单独外部新令清除、内部移交通道不清——§2.2/§2.9）。
```

**一句话语义**：move_mode 是单位级移动模式判别槽；四值互斥， NORMAL=现状。
**消费点/写点清单**：写=命令族 + dispatch 复位；读=move_speed_cm_tick（REVERSE 乘区）、system_move 朝向分支（REVERSE 锁定）、dispatch（ATTACK 保持门 / MARCH 道路门）、current_order 查询位。

### 2.2 指令族与命令层（+5 命令；GAP-01/04/05/06/18；BLK-1 修复后）

```
MoveCmd{unit, path: list[(cm,cm)], mode: MoveMode, queue: BOOL}   # 普通机动/攻击前进/强行军共用体（mode 区分）
ReverseCmd{unit, dest: (cm,cm)}                                   # 倒车特化：单航点直线 + REVERSE 模式
HaltCmd{unit}                                                     # 停止：清航点、保 stance（GAP-06）
CancelCmd{unit}                                                   # 取消：清航点 + 清排队令链（GAP-06）
FormationCmd{unit(s), shape: FormationShape}                      # 队形选择（GAP-15 adopt 半）

FUNCTION issue_move(world, cfg, cmd: MoveCmd|ReverseCmd, handoff: BOOL = FALSE)
                                                          # 命令入口（consume_commands 与 UI/AI 同一接口）
                                                          # handoff=内部移交通道（BLK-1 修复）：仅供 consume_commands/
                                                          # 动作令处理体内部安装航点用，UI/AI 一律不传（外部恒 FALSE）
    u = cmd.unit
    IF u.deploy_state IN {DEPLOYING, PACKING}: RETURN REJECTED   # 门1 展开/收起与移动互锁（复用门，契约㉑——
                                                                  # 命令侧前置；system_move 内同名门维持不动 movement.py:54-55）
    IF 士气态 == PINNED（未来士气槽）: RETURN REJECTED            # 门2 D014 现行拍板；语义修订走 MV-B-03
    IF u.elements ≠ [] AND ALL(e.mounted_in is not None FOR e IN u.elements):
        RETURN REJECTED                                           # 门3 整班车载无独立移动令（GAP-2 修复——§2.10-3 双保险成立）
    IF cmd 是 ReverseCmd: cmd ← MoveCmd{path=[cmd.dest], mode=REVERSE, queue=FALSE}
    IF cmd.mode is REVERSE AND cfg.reverse_speed_bp[u.template.movement_class] == 0:
        RETURN REJECTED                                           # 门4 倒车资格（AMB-9 修复）：FOOT/HORSE 类
                                                                  # reverse_bp=0 → 显式拒令（不产生"REVERSE 模式空转锁"）
    IF handoff:                                                   # ── 内部移交通道：仅安装，不清链/不清 cap（BLK-1）──
        u.move_path = list(cmd.path)
        u.move_mode = cmd.mode
    ELIF NOT cmd.queue:                                           # ── 外部非排队新令：GAP-18 硬规则，四件一体覆盖 ──
        u.move_path = list(cmd.path)                              #   （清 move_path + 换模式 + 清链 + 退编组）
        u.move_mode = cmd.mode
        u.command_queue = []
        u.group_speed_cap = 0                                     #   单独外部下令=脱离编组同步（§2.9）
    ELSE:
        u.command_queue.append(cmd)                               # ── Shift 排队：入链尾（GAP-05）──
    RETURN OK
    # FormationCmd / HaltCmd / CancelCmd 为独立入口：
    #   FormationCmd: u.formation_shape = shape（组下令=逐单位写；无 REJECT 门）
    #   HaltCmd:  u.move_path=[]; u.move_mode=NORMAL; 移出 command_queue 中全部 MoveCmd/ReverseCmd 条目（MV-B-18）
    #   CancelCmd: u.move_path=[]; u.move_mode=NORMAL; u.command_queue=[]（stance 两命令均不动）

FUNCTION consume_commands(world, cfg)                      # tick.py:363 TODO 的落地骨架（挂 world_tick ①前）
    FOR u IN world.units（插入序）:
        WHILE u.command_queue ≠ [] AND u.move_path == []:  # 队列头执行条件=无进行中移动令
            cmd = u.command_queue[0]; u.command_queue.pop(0)
            IF cmd 是 MoveCmd|ReverseCmd:
                issue_move(world, cfg, cmd, handoff=TRUE)  # BLK-1 修复：内部通道安装（只装 move_path+换 mode）——
                                                           # 不清 command_queue（后续令保留）、不清 group_speed_cap
                                                           # （编组同步跨队列令保持）；安装后 move_path≠[] 天然阻塞
                                                           # 后续队列头，无需 BREAK 清链即自洽
                IF cmd.mode ≠ NORMAL: BREAK                # 移动令安装后交还控制（下一令须等到位）
            ELSE:
                执行动作令（DeployCmd/SprintCmd/MountCmd/…——各自冻结入口，SprintCmd 仍是
                sprint_until 唯一写点 types.py:308；DeployCmd 展开互锁门复用）
                # 动作令处理体若需安装进位航点（§2.11），同样经 issue_move(..., handoff=TRUE)
        # 队列头令被门 REJECTED（如 DEPLOYING 期的排队移动令）：该令丢弃、循环继续（成文口径——
        # 拒令不回队首防死锁；丢弃事实经 current_order/队列 UI 可见）

FUNCTION current_order(u) → 只读描述                       # GAP-18 查询位（推导式，零新槽——UI/ALT 类查询）
    IF u.move_path ≠ []: RETURN {kind: MOVE, mode: u.move_mode, dest: u.move_path[-1]}
    IF u.command_queue ≠ []: RETURN {kind: QUEUED, head: u.command_queue[0]}
    RETURN {kind: IDLE, stance: u.stance}
```

**一句话语义**：命令层以"外部非排队新令无条件覆盖（四件一体）、排队令入链顺序执行、内部移交通道只装不清"为硬规则；halt 与 cancel 分离；当前执行令可查询。
**要点**：① 覆盖规则直击断箭"倒车令不覆盖旧移动令"真 bug（GDD-06 G5）；② **handoff 例外通道（BLK-1 修复）**：队列消费安装移动令不清链不清 cap——v1 以 `issue_move(queue=FALSE)` 消费队列头会连带清空 command_queue 与 group_speed_cap，Shift 排队（GAP-05）与编组同步（GAP-16）按登记伪代码落地即失效，v1.1 以内部通道消除该矛盾；
③ halt 保动作令/清移动令的清理范围是 MV-B-18 推荐项；④ 高度切换（航空 alt_pending）**不进队列**——与断箭教训一致（GAP-37 口径成文，§3.2）；
⑤ **落地锚点测试登记（BLK-1 fix 要求，本档为伪代码登记、落地期执行）**：
**T-queue-1（三令排队逐令执行）**——档 5 轮式单位（v=140×5000//10000=70cm/tick）入队三段 MoveCmd 各 7000cm：第 100/200 tick 时刻 `command_queue` 长度分别为 2/1（链未被清）、`move_path` 为当前段；300 tick 后 pos==第三段终点、command_queue==[]、move_mode==NORMAL（复位）；
**T-queue-2（cap 跨队列令保持）**——编组 [tier5 卡车, tier2 重坦]（cap=2）组下令排队两段移动：全程两单位 v 相等（tier2=45×地形 bp）、中途 command_queue 未清、group_speed_cap==2 保持；对卡车单独外部新令后其 cap==0、v 恢复 tier5 档。

### 2.3 速度求值链 v2（move_speed_cm_tick 增量登记；GAP-03/14/16）

**契约⑤签名不变**：`(cfg, unit, now, *, on_road=False, terrain_bp=None) -> int`。增量=改函数体（movement.py:17-38）：

```
FUNCTION move_speed_cm_tick(cfg, unit, now, *, on_road=False, terrain_bp=None) → int
    IF NOT unit.elements: RETURN 0
    # ── 拆除行（GAP-14/契约⑩）：删除 movement.py:22-24 的 CritSlot.MOB MAJOR 读取（趴窝语义由拖曳承载：
    #    HP≤25% 仅减速不减停；MOB MAJOR=0 的"等拖曳"语义由 D068 单阈值规则取代——重伤≠瘫痪）──
    tier = unit.template.speed_tier
    IF unit.group_speed_cap > 0: tier = MIN(tier, unit.group_speed_cap)     # 增量①（GAP-16，MV-B-15）
    IF now < unit.sprint_until: tier = MIN(5, tier + 1)                     # 冻结行（movement.py:26-27，不动）
    IF ANY(x.towed IN {TOWING, TOWED} FOR x IN unit.elements):
        tier = cfg.tow_speed_tier                                           # 冻结行（movement.py:29-31，不动——拖曳硬覆盖含钳制）
    base = cfg.speed_cm_tick(tier)
    m_bp = cfg.terrain_speed_bp(unit.template.movement_class, terrain_bp)   # 冻结行（movement.py:32，不动）
    v = base * m_bp // 10000
    IF unit.move_mode is REVERSE:
        v = v * cfg.reverse_speed_bp[unit.template.movement_class] // 10000 # 增量②（GAP-03，MV-B-13）
    IF ANY(e.hp_current * 10000 <= e.template.hp_max * cfg.crippled_threshold_bp
           FOR e IN unit.elements):                                         # 增量③（GAP-14 替换：HP≤25% 单阈值，MV-B-14；
        v = v * cfg.crippled_speed_mult_bp // 10000                         #   替换 movement.py:33-34 的 MOB MINOR 乘区位置）
    IF on_road AND unit.template.movement_class is not FOOT:
        v = MAX(v, cfg.road_bonus_cm_tick)                                  # 冻结行（movement.py:36-37，不动——契约⑦）
    RETURN v
```

**求值顺序 v2（冻结，替代契约⑤所列 v1 链）**：`编组钳制 → 疾跑升档 → 拖曳最低档 → 地形 bp 乘区 → 倒车乘区 → 重伤乘区 → 道路取 max`。
v1 的两处 MOB 步骤按契约⑩拆除（前位 MOB MAJOR 删除、后位 MOB MINOR 乘区由重伤乘区**原位替换**）；其余各行原序原式不动。
整数乘区串接次序冻结=位级确定（`(a×b//10000)×c//10000` 与 `(a×c//10000)×b//10000` 可差 1，故倒车/重伤先后亦冻结）。
**边界口径**：① 倒车与拖曳可叠加（拖曳锁 1 档后再乘倒车 bp——牵引车倒车调炮位是真实操作）；**叠加期间被拖元素随动偏移方向按 `elements[0].facing` 反向（车尾侧）取向**——登记增量⑨/MV-B-22（AMB-6 修复）：movement.py:109-114 现按"本 tick 位移向量反向"归一取偏移，倒车时位移向量指向车尾、被拖元素会被放到牵引车**车头侧**（拖挂点物理上恒在车尾）；增量⑨把偏移基向改为 `−scale(DIR8[unit.elements[0].facing // 45], tow_follow_offset_cm)`（按车体朝向恒取车尾正后方），"本 tick 有位移才随动"门（AMB-10 拍板）维持不动、被拖 pos 唯一写点仍在该段（契约⑨不破）；
② 倒车令期间 dispatch 恒传 `on_road=False`（道路档 MARCH 独占，无"倒车上路取 max"分支）；
③ 重伤阈值边界含等号（hp×10000 ≤ hp_max×2500——锚点：16HP 车辆 4HP 恰触发）；
④ 重伤判 ANY 元素（排内一辆重伤全排减速——排级同速抽象，与拖曳 ANY 双态判同构；MV-B-14 可推翻）。
**锚点验算**（默认表值）：档 4 轮式卡车 v=100×5000//10000=50；倒车 50×2500//10000=**12**；重伤再乘 5000→**6**；
重坦（档 2 履带）倒车 45×7000//10000=31 → ×3000//10000=**9**。

### 2.4 system_move 集成（dispatch 包装器 + facing 增量；GAP-02/03/04/15）

system_move 本体（movement.py:51-118）**零改动**，除一处 facing 增量：

```
增量登记④（movement.py:80-87 末段朝向块，REVERSE 分支感知——GAP-03）:
    原: lead_facing 恒由本 tick 位移向量/下一航向 octant 求出（三个既有分支）
    改: 在三分支求值前增一行——
        IF unit.move_mode is MoveMode.REVERSE: lead_facing = unit.elements[0].facing
        （保持现值不写：倒车期间车头朝向不随位移翻转；后继队形循环 e.facing = lead_facing 写同值=无操作。
         不做"下令时刻快照"（零新槽）；期间射击侧 rotate_step 转 R-09 车体属独立语义，互不干预。）

FUNCTION system_move_dispatch(world, cfg, unit)        # 新函数（movement 扩展模块）；tick.py:366 调用点替换登记
    now = world.tick
    IF 士气态 == PINNED（未来士气槽）: RETURN            # D014 现行（MV-B-03 可推翻）；sim 现无士气态——槽落地前恒假
    IF unit.move_mode is ATTACK AND unit.move_path ≠ []
       AND attack_move_engage_hold(world, unit):        # 增量⑤（GAP-04 接敌保持）
        sync_followers(unit); RETURN                    # 停住不动：不进 system_move ⇒ 出楼/退伏击副作用不触发（未位移）；
                                                       # 感知侧三乘区口径见 §2.5 口径④（MV-B-23）
    on_road = (unit.move_mode is MoveMode.MARCH) AND world.road_at(unit.pos)
                                                       # 增量⑥（GAP-02 接线——唯一写 on_road=True 的路径；
                                                       # road_at 为地图层谓词 §2.14，stub False；契约⑦：只接线不改乘区）
    terrain_bp = world.terrain_speed_tile_bp(unit.pos, unit.template.movement_class)
                                                       # 增量⑦：瓦片注入接线（tables.py:115-121 接口；stub None=类级缺省）
    fn = make_formation_fn(world, cfg, unit)            # 增量⑧（GAP-15）：队形接线；shape==NONE 时返回 None——
                                                       # tick.py 现状（不传 formation_offset_fn）行为逐位保持
    system_move(cfg, unit, now, on_road=on_road, terrain_bp=terrain_bp,
                formation_offset_fn=fn, tow_pairs=world.tow_pairs)   # 冻结函数直调（契约⑥序列不动）
    IF unit.move_path == [] AND unit.move_mode ≠ NORMAL:
        unit.move_mode = MoveMode.NORMAL                # 模式生命周期=当前移动令（到达即复位）
```

**一句话语义**：dispatch 是 system_move 的唯一调用方，集中承载模式感知的新逻辑（保持门/道路门/队形/复位），冻结函数体不感知模式（除增量④一行）。
**注意**：dispatch 不重复 DeployState/被拖/车载门——那些在 system_move 内部（movement.py:54-63）照旧生效（契约㉑）。

### 2.5 攻击前进（attack_move_engage_hold；GAP-04 adopt）

```
FUNCTION attack_move_engage_hold(world, unit) → BOOL
    R = 0
    FOR e IN unit.elements:
        FOR ws IN e.weapon_states WHERE (ws.template.target_mask & GROUND) != 0:
            R = MAX(R, ws.template.max_range_cm)        # 自身最强地面武器射程（无地面武器→R=0 永不保持）
    IF R <= 0: RETURN FALSE
    bit = 1 << unit.team
    FOR u2 IN world.units（插入序） WHERE u2.team != unit.team AND u2.alive:
        IF (u2.spotted_mask & bit) == 0: CONTINUE       # 仅"已发现"敌人（spotted_mask 位掩码 types.py:302——断箭同语义）
        FOR e2 IN u2.elements:
            IF e2.mounted_in is not None: CONTINUE      # 车载班随车结算（与扫射/对空索敌同谓词）
            IF dist_cm(unit.elements[0].pos, e2.pos) <= R: RETURN TRUE
    RETURN FALSE
```

**一句话语义**：攻击前进=发现位敌人进入自身地面武器射程即停（暂停消耗 move_path 预算），敌人消失/被毁/出界或手动新令自动恢复。
**口径**：① 判据粒度=单位首元素 pos × 敌方元素 pos × MAX 自身地面武器射程（MV-B-16 可推翻为元素级逐对/独立接敌半径常数）；
② 保持与 stance 无关（HOLD_FIRE 下照样停、只是不射——射击许可归 stance 既有门）；③ 停住≠驻楼退出/伏击退出（无位移不触发 movement.py:93-103 两条副作用——契约㉏由"真位移才进 system_move"天然满足）；
④ **保持期感知口径（AMB-1 修复，推荐选项落地并登记 MV-B-23）**：保持期间 move_path 非空 ⇒ `moving()=bool(move_path)`（types.py:310-311 冻结谓词）仍为真——移动隐蔽×5000bp（sensing.py:20-21）、FOREST_WALK_SILENT 豁免链（sensing.py:22-23）、观察者移动视野减半（sensing.py:48-49）三处乘区对已停住单位**持续生效**，且 `cmd_toggle_ambush` 静止判据（move_path 为空，movement/IMPL §F5 同源）在保持期**不可达**（不能就地转入伏击）。理由：保持=移动令生效中的战术停靠（与断箭 AttackMove 停开阔地吃暴露代价同向——停住 ≠ 转入掩体状态）；若要"停即算静止"，须改 moving() 谓词为"本 tick 有有效位移"——连锁 sensing 三乘区+伏击判据，登记为 MV-B-23 推翻通道（与 MV-B-08 连锁）；
⑤ 与断箭"非边走边打"一致——行进间开火惩罚由 D023 moveFactor 既有承载（§2.10-9）。

### 2.6 强行军（MARCH；GAP-02 adopt）

**一句话语义**：强行军=移动模式 MARCH：站在道路瓦片上时吃既有道路取 max（170 cm/tick 下限），其余一切同普通机动。
**接线细则**：① `on_road = (move_mode is MARCH) ∧ world.road_at(pos)`——普通机动在路瓦片上**不吃**道路档（对应断箭"普通移动不走公路"的路径偏好语义；瓦片即吃=MV-B-17 可推翻项）；
② 道路是**常数下限不是乘区**（movement.py:36-37 冻结式不动——契约⑦）；步兵 FOOT 不吃道路（冻结行内既有谓词）；
③ **弃掩体=寻路行为非数值惩罚**（断箭 G4 官方口径）：强行军无额外隐蔽数值乘区——移动隐蔽×5000bp（sensing.py:20-23）对一切移动已生效且受 GAP-23 defer 约束不得单侧改动（契约⑳）；
④ "沿路寻路偏好"依赖寻路层（GAP-24 defer/MV-B-09）——首版以 on_road 标志+速度档承载强行军的速度语义，路径仍由命令直填。
⑤ 断箭"双击移动=FastMove"默认映射是误触源（GDD-06 G1 社区实测）——不采纳，强行军必须显式指令。

### 2.7 倒车（REVERSE；GAP-03 adopt）

**一句话语义**：倒车令=单航点直线倒驶：速度=v×reverse_speed_bp[movement_class]（§2.3 增量②），车头朝向保持不变（§2.4 增量④）；FOOT/HORSE 类乘区为 0 ⇒ **issue_move 门 4 显式 REJECT**（AMB-9 修复：不产生"REVERSE 模式+非空 move_path+速度 0"的空转锁——v1"速度 0 自然不走"读法会使单位滞留 REVERSE 模式、永不到位、模式不复位、current_order 恒报 MOVE，与"不可倒车指令"的拒令语义两读并存，v1.1 收敛为拒令）。
**细则**：① 单航点直线（ReverseCmd 特化 path=[dest]——断箭"直线倒车"语义，不入排队链除非 Shift）；
② 无条件覆盖旧移动令（§2.2——断箭真 bug 的对症规则）；③ DeployState/车载门照旧（契约㉑、§2.2 门 1/门 3）；
④ 类级默认值 (FOOT 0, WHEEL 2500, TRACK 3000, HORSE 0)（≈倒/前进 1:4 与 1:3.3——落在断箭实测轮式 22~25%/履带 29~50% 区间下沿；
1944 语境差异化史实（T-34 倒车慢/谢尔曼倒车快）由单位级细化承载=MV-B-13/MV-B-01 拍板项）；⑤ 马队/步兵不倒退（HORSE/FOOT=0 → 门 4 拒令，调头归普通机动）。

### 2.8 队形表（formation_offset_fn 标准库；GAP-15 adopt 半）

system_move 消费签名冻结：`formation_offset_fn(unit.pos, e.id) → (cm,cm)`（movement.py:91）。标准库以**每 tick 重建的闭包**供给形状/方向/编制，不改签名：

```
FUNCTION make_formation_fn(world, cfg, unit) → closure|None
    IF unit.formation_shape is NONE: RETURN None                 # 现状同点堆叠（零行为变化）
    n = len(unit.elements); shape = unit.formation_shape
    k = (octant_deg(下一航点 − unit.pos) // 45 IF unit.move_path ≠ []
         ELSE unit.elements[0].facing // 45)                      # 行进向 DIR8 索引（到达后按末段朝向——GAP-30 既有语义）
    rank = {e.id: r FOR r, e IN enumerate(unit.elements)}        # 插入序编制位（§T 确定性；车载/被拖元素不重排）
    line_s = cfg.formation_line_spacing_cm; col_s = cfg.formation_column_spacing_cm
    DEF fn(base_pos, element_id):
        r = rank[element_id]
        IF shape is LINE:                                        # 横队：沿行进垂线对称展开
            lat = round_div(2*r − n + 1, 2) * line_s              # n=3 → −1,0,+1；n=4 → −1,0,1,2（半舍入，位级确定）
            off = scale(PERP8[k], lat)
        ELIF shape is COLUMN:                                    # 纵队：沿行进反方向串列（首车在前）
            off = scale(DIR8[(k+4) % 8], r * col_s)
        ELSE:                                                    # WEDGE 楔形（AMB-2 修正式）：楔尖=首元素在中轴 (0,0)，
                                                                 # 其后成对元素左右 ±line_s//2、纵深按对递增——V 形前锋
            IF r == 0: off = (0, 0)                              # 楔尖
            ELSE:
                depth = ((r + 1) // 2) * col_s                   # 第 1 对纵深 col_s、第 2 对 2×col_s……
                side  = (line_s // 2) IF r 奇 ELSE −(line_s // 2)  # 奇数位左、偶数位右（同对左右对称）
                off = scale(DIR8[(k+4) % 8], depth) + scale(PERP8[k], side)
        RETURN (base_pos[0] + off[0], base_pos[1] + off[1])
    RETURN fn
```

**一句话语义**：横队/纵队/楔形三表按行进 DIR8/PERP8 整型缩放生成元素偏移；NONE 默认保持现状；楔形=楔尖居中、成对左右递增纵深（AMB-2 修正——v1 式 r=0 即带 −line_s//2 横偏，展开实为交错纵队与"楔尖=首元素"注释自相矛盾，v1.1 改本式）。
**楔形锚点**（n=5，line_s=1500、col_s=1000，行进向 k）：r0=(0,0)；r1=后 1000cm+左 750cm；r2=后 1000cm+右 750cm；r3=后 2000cm+左 750cm；r4=后 2000cm+右 750cm。
**要点**：① scale/PERP8/DIR8 复用 air.py:31-46 冻结族（契约⑯）；② 谓词复用既有（车载/被拖元素跳过偏移应用——movement.py:88-89 不动）；
③ 间距数值（1500/1000cm）为占位，数值章节定标；④ 玩家指定**到达朝向令**（拖拽向量→末段朝向覆盖）defer=MV-B-05——现状到达朝向=保持末段航向（GAP-30 修复已落地，movement.py:80-86）。

### 2.9 编组速度同步（group_speed_cap；GAP-16 adopt）

```
FUNCTION issue_group_move(world, cfg, units: list, path, mode)     # 组下令入口（框选/编组——UI 层聚合，非新命令类型）
    cap = MIN(u.template.speed_tier FOR u IN units)                # 组最慢档（下令时一次定型——确定性、无逐 tick 抖动）
    FOR u IN units（插入序）:
        issue_move(world, cfg, MoveCmd{u, path, mode, queue=FALSE}) # 外部新令：覆盖规则逐单位生效（§2.2，含清 cap）
        IF len(units) > 1: u.group_speed_cap = cap                 # 组令随后写 cap；单独外部新令时 issue_move 清 0 → 脱离同步；
                                                                   # 队列消费（handoff 通道）不清 cap——编组同步跨排队令保持（BLK-1）
```

**一句话语义**：多单位同令时全组速度档钳制到组内最慢 tier（消除断箭"IFV 甩步兵狂奔"微操负担）；单单位外部下令即脱离编组；**排队链中的后续移动令不破坏同步**（handoff 通道不清 cap——BLK-1 修复）。
**口径**：钳制在**档位**层（tier MIN），不钳最终 v——类级地形 bp 差异（WHEEL 5000 vs TRACK 7000 越野）与道路下限仍可产生残余速差，
登记为已知近似（有效速度 v 逐 tick 取 MIN 的替代式=MV-B-15，抖动/整除代价更高故不推荐）；疾跑升档在钳制**之后**（个体冲刺允许破格——契约⑧升档式不动）；
拖曳锁档硬覆盖钳制（tow_speed_tier=1 已是最低，语义自洽）。零新常数。

### 2.10 互锁清单（全部复用既有门，禁止重定义）

| # | 互锁 | 承载（既有，不动） | 新模式关系 |
|---|---|---|---|
| 1 | 展开/收起禁移动 | system_move 早退（movement.py:54-55；命令侧 issue_move 门 1 前置） | 倒车/强行军/攻击前进同门（契约㉑） |
| 2 | 全被拖不自主移动 | system_move 早退（movement.py:56-57） | 同上 |
| 3 | 整班车载随动 | system_move 早退+sync_followers（movement.py:58-63、:41-48） | 车载班无独立移动令——**issue_move 门 3 对全 mounted 单位 REJECT（GAP-2 修复：v1 互锁表宣称双保险但函数体无此门，v1.1 补齐成真）**，与运行时早退双保险 |
| 4 | 拖曳锁最低档 | move_speed_cm_tick（movement.py:29-31） | 倒车可叠加（§2.3 边界①；叠加期随动偏移取向=增量⑨/MV-B-22） |
| 5 | 被拖元素 pos 唯一写点 | system_move 拖曳随动段（movement.py:104-117；AMB-10 后方 300cm） | 不得另写（契约⑨）；增量⑨只改该段内偏移**基向**（位移反向→车尾朝向反向），写点位置不动 |
| 6 | 移动自动出楼 | system_move（movement.py:93-99） | 攻击前进"停住"不触发（无位移不进门）；真位移照常（契约㉒） |
| 7 | 移动自动退伏击双清 | system_move（movement.py:100-103） | 同上 |
| 8 | **疾跑禁射（新，GAP-12）** | **增量登记（GAP-3 修复：挂点=system_timers，tick.py:202-207 weapon_states 循环）**：AIMING 状态且 `world.tick < e.unit.sprint_until` 的 tick **跳过 timer 递减**（瞄准进度冻结——不发射不耗弹由 timer 永不归零天然保证；RELOADING 不冻结，装填照常）；索敌侧配套：fire_permitted/ground_direct 索敌门同判 sprint_until 期间不开新 AIMING | 速度式不动（契约⑧：禁射细则加在射击侧）；sprint_until 唯一写点 SprintCmd 不变；破压制 defer=MV-B-04 |
| 9 | **行进间开火口径（新成文，GAP-19）** | D023 moveFactor 移动/静止修正（既有）+ D047 rotating（types.py:276——GAP-4 勘误：v1 误引 :283，该行是 supply_rounds；rotate_step 规划内消费 turn_rate_deg_per_tick，定标换算见 §2.13）+ 疾跑禁射（上条） | 三句口径：移动可射击吃 moveFactor；无炮塔转向未完成不射（rotating 谓词）；冲刺绝对禁射。零新机制 |

### 2.11 超射程自动进位（炮击任务 QoL；GAP-13 adopt）

```
FUNCTION auto_approach_waypoint(unit, target, max_range_cm, cfg) → (cm,cm)|None
    d = dist_cm(unit.elements[0].pos, target)
    IF d <= max_range_cm: RETURN None                       # 射程内：不插航点（行为不变）
    k = octant_deg(target[0] − unit.pos[0], target[1] − unit.pos[1]) // 45
    stand = MAX(max_range_cm − cfg.auto_approach_standoff_cm, max_range_cm // 2)
                                                           # AMB-4 修复：下界=半射程——max_range<standoff 常数的武器
                                                           # 不再得负 stand（v1 式航点会反向越过目标）；半射程比例余量
                                                           # 50%≫DIR8 近似误差 1.015% 恒覆盖，亦使超远程武器（MV-B-21 对象）
                                                           # 无需依赖 2000cm 固定余量
    RETURN (target[0] − scale(DIR8[k], stand)[0], target[1] − scale(DIR8[k], stand)[1])
    # 消费点（AMB-3 修复）：FireMissionCmd / 超射程直射令处理体在安装任务时，经
    # issue_move(world, cfg, MoveCmd{path=[该航点], mode=NORMAL, queue=FALSE}, handoff=TRUE)
    # 落地（不直写 move_path——单一命令入口口径 §2.2；handoff 用于排队炮击令消费时不误清后续链）。
    # 外部直令场景按 queue=FALSE 外部通道走（下达炮击任务即重置移动链/退编组——覆盖规则四件一体适用，进位移动
    # 恒 NORMAL 模式）。到位后既有展开门（needs_deployed）与射击门照常接管（进位≠自动开火许可）。
    # 误差口径：DIR8 八向近似到位误差 ≤ max_range×(√50/7−1)≈1.015%——2000cm 固定余量在 max_range≤196,000cm
    # （≈1.96km）时独立覆盖之；更大射程由 //2 下界兜底（比例余量恒覆盖——AMB-4 成文）。
```

**一句话语义**：炮兵对超射程目标下令时自动插入"最大射程内侧 standoff（下界半射程）"航点（断箭 ARTILLERY 节官方语义的 QoL 等效）；适用范围推荐仅限须展开的 INDIRECT 武器（MV-B-21）。
**互锁**：到位后仍须 cmd_deploy 走展开时长（movement.py:54-55 与 needs_deployed 门不被旁路——断箭牵引炮同语义）。

### 2.12 森林不减速（数据口径成文；GAP-09 adopt）

**口径（写死，零代码零常数）**：TERRAIN[tile] 瓦片表接入 `terrain_speed_bp` 注入时，**森林瓦片不注入速度 bp**（speed_bp 恒为类级缺省——`is_forest` 只喂 sensing 两侧：林地隐蔽加成 forest_stealth_add_x10 与穿林视线衰减 detect_atten_per_m，sensing.py:20-23/:48-49 链）。泥泞/沼泽等地面状态修正走 D026 天气轨（瓦片注入接口即为其预留通道——tables.py:115-121 注释）。**依据**：断箭官方明示履带在森林不算恶劣地形、森林只影响隐蔽/视线（GDD-06 G6；Reddit 反证现行森林≈普通越野）。

### 2.13 转向模型口径（turn_rate_deg 不消费成文；GAP-10 reject）

**口径**：移动侧 facing **维持即时 8 扇区统一**（movement.py:80-87——排级抽象不做加减速过程与车体转向率节流）；`UnitTemplate.turn_rate_deg`（types.py:234）**维持 sim 死槽不消费**（契约③），留作数据卡展示位。
渐进转向的**首个规划消费点**是射击侧 `rotate_step`（GROUND_UNITS_PSEUDOCODE_IMPL_v1.7 §F5 :1051-1058：逐步转车体、`rotating` 按当前角差重算）——该函数属射击侧 R-09/D047 规划内增量。**字段名/定标对齐（AMB-5 修复成文）**：rotate_step 引用名 `turn_rate_deg_per_tick` 与槽名 `turn_rate_deg`（types.py:234，deg/s 语义——数据卡口径）不同名，落地时按换算式
`turn_rate_deg_per_tick = MAX(1, template.turn_rate_deg // 10)`（10Hz 除 10 取整；MAX(1,·) 防默认值 turn_rate_deg=1 → 0 的零速锁死）对齐，并登记**字段名统一连锁待办**（IMPL rotate_step 引用名改对齐或 types 槽注释补"deg/s、10Hz 换算"——随射击侧落地一并执行）。在该落地发生前，本文断言修正为：turn_rate 槽的**规划内**消费者=rotate_step（经上述换算），**当前 sim 仍无消费者**；**本文移动伪代码不引用 turn_rate_deg 做任何移动节流**（写作范围预期中"facing 从 snap 改渐进转向"一项与冻结契约③冲突，按契约裁定不采纳，特此留痕）。

### 2.14 寻路层接口预留（GAP-24 defer / MV-B-09）

```
# 地图层三谓词（Tiled→JSON TERRAIN 表接入前为 stub；引擎寻路层另案——本文不实现算法）
world.road_at(pos) → BOOL                        # TERRAIN[tile].on_road（stub: False）——§2.6 强行军消费
world.terrain_speed_tile_bp(pos, class) → int|None   # TERRAIN[tile].speed_bp[class]（stub: None→类级缺省）——§2.4 增量⑦消费
world.find_path(from, to, class, prefer_road: BOOL) → list[(cm,cm)]
                                                 # 首版 stub=直线直填（RETURN [to]——AMB-8 修复：stub 落点登记于 §9 tick.py 行，
                                                 # 算法本体随 MV-B-09 另案）；引擎层若立：整型 A*，瓦片代价定标成文——
                                                 #   tile_cost = INF            IF 瓦片 speed_bp == 0     # bp=0 防护=不可通行（水域/建筑——GAP-08 边界若做同此承载）
                                                 #   tile_cost = round_div(100000000, bp)  OTHERWISE       # 基础 1e8÷bp（bp=10000→10000 基准代价；倒数取式确定）
                                                 #   IF prefer_road AND 瓦片 on_road: tile_cost = MAX(1, tile_cost // 2)   # 道路偏好=代价减半
                                                 # 输出做共线航点化简（DIR8 段合并）；全遍历插入序确定。
```
**教训登记**（GDD-06 G17）：① 遇障默认"缩短直线距离"的接敌策略若存在须显式成文——本作已由攻击前进（§2.5）显式承载；② 侧移让射界**不承诺**；③ 城区路径偏好属引擎层拍板（MV-B-09）。

### 2.15 元素间距与避让（GAP-17 reject 成文）

**口径**：不做物理碰撞与避让（断箭教训：固体碰撞+无避让=长期痛点，官方只按图修补）。防重叠由三既有机制承载：队形偏移（§2.8）、拖曳后方固定偏移（tow_follow_offset_cm=300，movement.py:104-117；取向按增量⑨/MV-B-22）、基准点同点堆叠（NONE 队形——无碰撞判定故无卡死）。桥梁重灾区问题随 GAP-22（MV-B-07）一并不存在（首版无桥梁）。

---

## §3. 空中移动（B 部分；航空侧**零代码增量**——adopt 项全部为成文维持，defer 项见 §7）

### 3.1 航线模型（成文复用）

航线=航点表 `flight_plan: list[(cm,cm)]` + `step_toward` 预算循环（air.py:533-545，与地面 system_move 同构：预算按实际距离扣减、同 tick 可推进多航点）；
高度由 `alt_tier` 三层承载、与航点正交（**无按航点独立设高**——断箭未确证点 #15 同口径）。进场衔接：cmd_air_call 构造进场航点
（entry 朝地图中心 DIR8 方向推进 air_entry_offset_cm=60000，air.py:413-415）→ INBOUND 推进 → 到达 `enter_patrol_hold`（air.py:546-547/:464-469）转方形环路待命（patrol_orbit_radius_cm=2000，air.py:459-461）。攻击走廊由 `_run_points` 按 DIR8 推导 run_start/run_end（air.py:561-566——契约⑬维持）。

### 3.2 高度转换消费细化（成文；契约⑫）

`cmd_air_alt` 写 `alt_pending=(target_tier, alt_transition_ticks=30)`（air.py:503-509）；消费在 `aircraft_move_step` 首段（air.py:525-532）：
**每 tick 先递减计数、归零才换层**——过渡期内 `alt_tier` 保持旧值（防空可及性/侦察半径/投弹散布/缠斗层判均按旧层结算直至完成）。
三条细化口径：① 换层原子性=完成时一次生效，无中间层；② 高度切换**不进 Shift 队列**（条件槽即时——与断箭"直升机低空切换不进队列"现状教训一致，GAP-37 成文）；
③ RTB 态允许变层（AIR-B-29① 无害微操特许，AIR_UNITS_PSEUDOCODE_IMPL_v1.4 §B 已拍板）。`entry_tier=MIN(MID, alt_ceiling)`（air.py:49-51）不变。

### 3.3 进场段/盘旋/攻击走廊衔接与 INGRESS 对齐（GAP-26 adopt 成文）

**设计依据注释成文**（零改动）：断箭社区铁律"攻击令前至少 1 航点对齐机头、航点贴目标太近炸弹落前方"（GDD-06 A2）在本作由结构强制——
`cmd_air_strike` 自动生成 INGRESS 段 `flight_plan=[run_start]`（air.py:603）：**飞机必须先飞到对齐点才能进入 RUN**（StrikePhase.INGRESS→RUN 的到达判据 air.py:632-638），
等价于"强制前置对齐航点"；run_start 距目标 `strafe_run_lead_cm=8000`（tables.py:86）即"航点不贴目标"的最小间距承载。RUN/EGRESS 直线段不可中断
（`_strike_busy`，air.py:472-477——契约⑭），转弯死循环问题（断箭 A6-③）由此结构性规避。

### 3.4 固定翼转弯几何（GAP-30 defer / MV-B-10；未落地方案草图）

现状：facing 即时 8 扇区（`_set_facing` 按位移向量，air.py:554-556）、无转弯半径——直线 snap。若拍板采纳渐进转弯，推荐整数模型（登记于 MV-B-10，**不在本版落地**）：
`turn_step_deg = MAX(1, air_turn_base_deg + template.maneuver × air_turn_per_maneuver_deg)`（两常数出表；maneuver 槽 air.py:259 已有；**MAX(1,·) 守卫**——AMB-7 修复：两常数线性合成在未配数据（如 base=0 且 maneuver=0 机型）时分母为 0，转弯半径式 `R_cm ≈ speed_cm_tick × 573 // (turn_step_deg × 10)` 须以非零 turn_step_deg 为前提），
facing 每 tick 朝目标 octant 逼近 turn_step_deg（angle_diff+SIGN，全整型），位置沿 facing 的 DIR8 前进而非 step_toward 直连。
**采纳前须解决三个兼容问题**：① 巡逻方形环路直角不可达——需改八边形航点或引入
航点捕获容差（≥R）；② INGRESS 对齐时间变长（对齐判据需按转弯半径前置 run_start）；③ strike_step 越线窗 `dist ≤ speed_cm_tick`（air.py:639）与转弯轨迹的
漏检风险。首版推荐：维持直线 snap（现状已防死循环，GDD-06 A6 判定）。

### 3.5 速度档（GAP-28 reject / 契约⑪ / MV-B-20）

**口径**：航空速度单值槽 `AircraftTemplate.speed_cm_tick`（air.py:257）维持——无速度档、无加力（1944 活塞机时代置换+无燃油槽，在空时间由弹尽自动 RTB 承载，air.py:923-931）。
"巡航/全速两档"若引入属新增速度状态，**须另立拍板**（契约⑪）——MV-B-20 推荐**不做**；若推翻：新增 throttle 条件槽+`air_full_speed_mult_bp` 出表，并须复核
strike_step 越线窗宽度（dist≤speed 判据随速度放大）与进场段时间（60000cm÷速度）两处时序锚点。

### 3.6 RTB 与再入场衔接、留空行为（GAP-31/32 adopt 成文；零改动）

RTB 令 `cmd_air_rtb`（air.py:512-519：不可逆 AIR-B-22，flight_plan=[rtb_exit_point]）→ 到达即 `air_recovery`（air.py:550-551/:420-432：舱内班退份→本体价回收→
冷却 MAX 合并→移除）→ 再入场=新 `cmd_air_call`（冷却门 air_cooldowns + 同型在空门 air_per_type_max，air.py:380-381/:376-379）。
留空/待命：INBOUND 到达自动盘旋待命；弹尽自动 RTB 资格门（weapons/补给舱/空降舱三析取，侦察机豁免——air.py:923-931）与断箭周年演化方向（干扰弹耗尽不再强制返场）同构且更精细。
BA 社区冷却公式（生还 4min+价/2、击落 10min+价/2）仅登记参照——本作 D015 梯度（击落×3 > 受损返场 > 满血返场）方向一致（AIR-00 §6 已印证）。

---

## §4. BalanceConfig 移动段（新常数 6 字段；与航空 38 字段分账；一常数一轨）

| 字段 | 类型/单位 | 默认（占位） | 说明 |
|---|---|---|---|
| reverse_speed_bp | bp[4]（FOOT/WHEEL/TRACK/HORSE 序） | (0, 2500, 3000, 0) | 倒车速度乘区（GAP-03/MV-B-13）：FOOT/HORSE=0 且 issue_move 门 4 据此**拒令**（§2.7——AMB-9）；轮式 2500/履带 3000 落在断箭实测倒/前比区间下沿；单位级差异化（T-34 慢/谢尔曼快）随 MV-B-01/MV-B-13 拍板 |
| crippled_threshold_bp | bp | 2500 | 重伤阈值 HP≤25%（D068 字面——GAP-14） |
| crippled_speed_mult_bp | bp | 5000 | 重伤减速×0.5（D068"HP≤25%速度减半"——GAP-14；替换 MOB MINOR 乘区原位） |
| formation_line_spacing_cm | cm | 1500 | 横队相邻元素间距/楔形横向半距×2（GAP-15；数值章节定标） |
| formation_column_spacing_cm | cm | 1000 | 纵队/楔形纵深间距（GAP-15；同上） |
| auto_approach_standoff_cm | cm | 2000 | 超射程自动进位的最大射程内侧余量（GAP-13；stand 取 MAX(max_range−此值, max_range//2)——AMB-4） |

> 删除登记 1 条：`crit_mob_minor_mult_bp=5000`（tables.py:18）——GAP-14 拆除 MOB 读取后零消费，随 combat.roll_crit 拆除（§8 连锁）一并删除。
> 复用不新增：road_bonus_cm_tick=170（tables.py:15，强行军只接线）、tow_follow_offset_cm=300、sprint_duration_ticks=100、tow_speed_tier=1、speed_table_cm_tick。

---

## §5. 变量集账目（新增槽 vs 复用冻结槽逐个登记；地面/航空分账）

**地面（UnitInstance +4 → 单位运行时 17→21；地面总账 78→82。基数 17=types.py:291-308 实有字段数/IMPL §D.4（:176）口径——GAP-1 勘误，头注注记两基准 sprint_until 归口差）**

| 新槽 | 类型/默认 | 消费点 | 写点 | 对应 |
|---|---|---|---|---|
| move_mode | MoveMode=NORMAL | move_speed_cm_tick（REVERSE 乘区）、system_move 朝向分支（增量④）、dispatch（ATTACK/MARCH 门）、current_order | 命令族（外部/内部通道两写法）；dispatch 到达复位 | GAP-01/03/04 |
| command_queue | list=[]（命令对象链） | consume_commands | issue_move（外部非排队令清空/排队令追加/**内部通道不清**）、Halt/Cancel、ReverseCmd 覆盖 | GAP-05/18 |
| group_speed_cap | int=0（0=无钳制，否则 1..5 上限） | move_speed_cm_tick 增量①（tier 预钳制） | issue_group_move 写/外部单独新令清 0/**内部通道不清（跨队列令保持——BLK-1）** | GAP-16 |
| formation_shape | FormationShape=NONE | dispatch→make_formation_fn | FormationCmd | GAP-15 |

零新槽登记：`current_order` 查询位=推导式（move_path+move_mode+queue 头——GAP-18）；道路/瓦片/寻路谓词在 world 层（§2.14 接口预留，非单位槽）。
**复用冻结槽（不改语义只读）**：move_path（队列令天然承载——契约④）、speed_tier（标尺唯一——契约①）、movement_class（契约②）、
sprint_until（唯一写点 SprintCmd——契约⑧；单位级归口=IMPL/代码口径，机制版 §0 元素级系归口差——GAP-1 注记）、deploy_state/deploy_timer（互锁）、stance、spotted_mask（攻击前进读）、
towed/mounted_in（互锁）、facing（倒车锁定=不写而非新槽）、turn_rate_deg（**维持死槽**——契约③；规划内消费者=射击侧 rotate_step，§2.13）。
**航空（+0；21 槽维持）**：无新槽——转弯几何（MV-B-10）与速度档（MV-B-20）均 defer，采纳时再登记（throttle 条件槽/两常数）。

**新枚举 2**：MoveMode（4 值）、FormationShape（4 值）。**新命令 5**：MoveCmd/HaltCmd/CancelCmd/ReverseCmd/FormationCmd（§2.2）；航空命令 0。

---

## §6. PRNG 账目

移动机制**零随机**：速度求值/倒车/编组/队形/攻击前进保持门/超射程进位/寻路接口全部确定性整型（无掷骰、无概率乘区）。
无新通道（HIT/SCATTER/SPOT/CRIT/SNIPER/SONAR/ECONOMY/AIR=0..7 维持——契约⑰天然满足）。若未来引入（如断箭式概率跳车、随机散布行军），
须显式传通道并登记，不复用现有序列。

---

## §7. 拍板预登记表（MV-B-01…MV-B-23；每条按推荐执行/登记，推翻通道="N 改B"）

> **编号消歧（AMB-10）**：本表编号带 **MV-B-** 前缀，仅指本文自有拍板项；他档拍板项引用时带档名前缀（如 AIR-B-22/AIR-B-29①=AIR IMPL v1.4 §B、GROUND IMPL 拍板清单项写全称）。
> v1 文中无前缀 B-01…B-21 与本表 MV-B-01…MV-B-21 一一对应（同条目）；MV-B-22/MV-B-23 为 v1.1 审查修复新增。

| # | 决策点 | 推荐（本文执行） | 理由 | 负面影响 | 推翻通道 |
|---|---|---|---|---|---|
| MV-B-01 | 单位级路/野/倒三元组（GAP-07） | 维持类级系数（speed_tier+terrain_speed_bp 类级+reverse_speed_bp 类级），不细化到单位级 | 类级方向已与断箭实测吻合（WHEEL 5000/TRACK 7000）；一单位三速度值×40 余卡数据成本高 | T-34 慢倒车/谢尔曼快倒车、DT-30 宽履带拖路速等史实差异无法表达 | MV-B-01 改B（数据卡增 reverse_speed_bp 单位级覆盖位——与 MV-B-13 联动） |
| MV-B-02 | 两栖/水域移动（GAP-08） | 首版不做 | D026 无水域参数、MovementClass 四值已冻结；东线涉水场属地图体系 | T-37 等两栖车无法涉水（1944 要素缺失） | MV-B-02 改B（MovementClass 扩 AMPHIB 或 UnitFlag 增两栖位+水域瓦片 speed_bp 极低值+非两栖寻路硬边界——契约②不许旁路） |
| MV-B-03 | PINNED 可移动性（GAP-11） | 维持 D014：PINNED=无法移动（dispatch/issue_move 双门） | 已拍板决策；修订须用户确认（GDD-05 A4 系当时误传但拍板有效） | 严于断箭任何状态（Shock 仍可令）；被钉死单位无脱身手段 | MV-B-03 改B（PINNED 改"降效+减速可令"对齐断箭——连锁 GDD-05 B4 updateMorale 回写） |
| MV-B-04 | 疾跑破压制（GAP-12 后半） | 不做 | 与 D014 士气链耦合，须随 MV-B-03 一并拍板 | 断箭官方点名的"冲刺脱压"战术缺失 | MV-B-04 改B（SprintCmd 开始时清/减压制值——士气链落地后实施） |
| MV-B-05 | 到达朝向指定令（GAP-15 后半） | 首版不做（到达朝向=保持末段航向，GAP-30 修复已落地） | 命令层/UI 交互属实现期；断箭该交互服从度差（GDD-06 A15） | 无法摆"到达即正面朝敌"的预设阵地 | MV-B-05 改B（MoveCmd 增 facing_deg 参数，到位后末段朝向覆盖写入） |
| MV-B-06 | 下车耗时（GAP-21） | 即时（0 tick，与断箭现行同构） | 断箭 1.1.1 已删下车延迟（社区验证的弃案方向） | 卡车急停急下无暴露窗口（上车 20s 的对称性略欠） | MV-B-06 改B（dismount_time_ticks 出表，默认 100） |
| MV-B-07 | 桥梁/渡口/可破坏桥（GAP-22） | 首版无桥无水（断箭不做即因全图断路可达性风险） | D046 首版无雷区口径同向；东线渡口属地图体系大决策 | 东线河流要素缺失 | MV-B-07 改B（桥梁瓦片+桥 HP+工兵爆破——须先解 GAP-24 寻路与全图连通性） |
| MV-B-08 | 移动隐蔽乘区去留（GAP-23） | 保留现行（移动隐蔽×5000bp+林中静默豁免+观察者移动视野减半——sensing.py:20-23/:48-49） | 是 D066 猎兵静默行军/侦察车免惩罚的前提乘区（契约㉇）；删除须连锁 | 比断箭官方口径严（自设机制），移动单位偏脆 | MV-B-08 改B（削除/仅载具适用/系数出表 stealth_move_mult_bp——须同步 GDD-00 D066 回写；与 MV-B-23 连锁） |
| MV-B-09 | 寻路层归属（GAP-24） | 首版 move_path 命令直填（直线航点）+§2.14 三谓词接口预留（find_path stub=直线直填，落点已登 §9——AMB-8） | 寻路属引擎层；断箭教训=按图修补不可持续 | 城区/障碍绕行缺失，遇障需玩家手排航点 | MV-B-09 改B（本作自带整型 A*——另立引擎文档，代价表/道路偏好/化简规则见 §2.14 草案） |
| MV-B-10 | 航空转弯几何（GAP-30） | 首版维持直线 snap（facing 即时 octant） | INGRESS 结构已防死循环；渐进转弯三个兼容问题未解（§3.4） | 无转弯圆表现（对齐即时）；甩导弹类机动不存在（1944 亦无） | MV-B-10 改B（整数转弯率模型——§3.4 草图含 MAX(1,·) 守卫（AMB-7）+两常数+巡逻环路八边形化+捕获容差） |
| MV-B-11 | 对地自动开火域（GAP-35） | 不做（对地打击保持手动标定 D015） | 对地攻击是本作空军核心博弈；防空/缠斗全自动已够 | Il-2 进走廊需逐次手动下令（微操强度高于断箭周年后） | MV-B-11 改B（STRAFE 武器进走廊自动开火——弹账/RTB 门联动须复核） |
| MV-B-12 | 队列可视化与可排队命令集（GAP-37） | 命令层实现期拍板；口径先成文：高度切换不进队列（维持即时条件槽） | UI 层事项；断箭"高度不进队列"现状教训一致 | 玩家无法预览排队链 | MV-B-12 改B（可排队命令白名单扩展/队列 UI——命令层落地时定） |
| MV-B-13 | 倒车类级默认值（GAP-03 数值） | (0, 2500, 3000, 0)（FOOT/WHEEL/TRACK/HORSE） | 断箭实测轮式 22~25%/履带 29~50% 区间下沿；1944 车辆倒车普遍慢 | 类内无差异（T-14 式 50% 倒车快车不存在） | MV-B-13 改B（数值章节重定标或单位级覆盖——随 MV-B-01） |
| MV-B-14 | 重伤阈值元素粒度（GAP-14） | ANY 元素 HP≤25% → 全单位×5000bp | 排级同速抽象（与拖曳 ANY 双态判同构）；留一辆重伤车=全排护航减速 | 单车拖慢全排（玩家或弃车——但一命制无弃车令） | MV-B-14 改B（仅首元素/编制均值/元素脱离（一命制下不可行——须先拍弃车规则）） |
| MV-B-15 | 编组钳制公式（GAP-16） | tier MIN 下令时一次定型（group_speed_cap 槽；内部通道不清——跨排队令保持） | 确定性无逐 tick 抖动；实现最廉 | 类级地形 bp 差异致残余速差（轮式越野仍慢于履带） | MV-B-15 改B（逐 tick 有效速度 v 取 MIN——代价：整除舍入与道路 max 交互复杂化） |
| MV-B-16 | 攻击前进接敌判据（GAP-04） | 单位首元素 pos × 敌方元素 pos × MAX 自身地面武器射程 × spotted_mask | 排级粒度；零新常数；与既有索敌谓词（mounted 排除）同构 | 曲射武器 max_range 极长导致远程即停（推荐配套 MV-B-21 将其限于直射/由数据配平） | MV-B-16 改B（元素级逐对判定或独立接敌半径常数 attack_hold_radius_cm 出表） |
| MV-B-17 | 强行军道路门合成式（GAP-02） | on_road = (mode=MARCH) ∧ 瓦片 on_road（普通机动在路不吃） | 对应断箭"路径偏好"语义；普通移动误上路狂奔是断箭误触源 | 普通机动穿路瓦片无速度收益（与现实直觉略悖） | MV-B-17 改B（凡在路瓦片即吃道路档——移动语义简化、强行军仅剩寻路偏好） |
| MV-B-18 | halt 对队列的清理范围（GAP-06） | halt=清航点+清队列中移动令、保留动作令；cancel=全清 | halt 必须实际停住（若保留排队移动令则下一拍自动续走=halt 失效）；cancel=断箭 E 全清等价 | 两命令语义边界须 UI 提示 | MV-B-18 改B（halt 完全不动队列=暂停键语义（须增挂起旗槽）/或 halt=cancel 合并） |
| MV-B-19 | 队形默认形状（GAP-15） | NONE 默认（零行为变化，与现状同点堆叠一致） | 向后兼容锚点测试与既有行为；显式下令才展开 | 新单位默认挤一点（无横队 aesthetics） | MV-B-19 改B（默认 LINE——tick 接线即改变现状元素布局，须过全部既有测试） |
| MV-B-20 | 航空速度档巡航/全速（契约⑪/GAP-28 关联） | 不做（speed_cm_tick 单值维持） | 无燃油槽承载全速代价；速度状态侵蚀 INGRESS/越线窗时序锚点（§3.5） | 无"赶时间冲刺进场"操作（本作进场时间已位置化承载） | MV-B-20 改B（throttle 条件槽+air_full_speed_mult_bp 出表——复核 strike_step 越线窗与进场段两时序） |
| MV-B-21 | 超射程自动进位适用范围（GAP-13） | 仅须展开的 INDIRECT/超远程武器（炮击任务语境） | 断箭官方语义即炮兵；直射自动进位会替代玩家走位微操 | 直射武器超射程令无进位 QoL（须手摆） | MV-B-21 改B（一切武器通用——须配 MV-B-16 的接敌半径防攻击前进/进位互踩） |
| MV-B-22（v1.1 新增，AMB-6） | 倒车×拖曳叠加期的被拖随动偏移取向 | 偏移基向改按 `elements[0].facing` 反向（车尾正后方 `−scale(DIR8[facing//45], tow_follow_offset_cm)`）——增量⑨登记于 movement.py:109-114；"本 tick 有位移才随动"门与 pos 唯一写点位置不动（契约⑨） | 拖挂点物理上恒在车尾：倒车时按"位移向量反向"取偏移会把被拖元素放到牵引车车头侧（v1 未审）；按车体朝向取向前进/倒车两态恒正确 | 首拍朝向突变（如 rotate_step 转车体）时被拖元素横跳一格（300cm 量级，队形语义可接受） | MV-B-22 改B（维持位移向量反向近似——登记已知偏差，随 MV-B-13 一并复核） |
| MV-B-23（v1.1 新增，AMB-1） | 攻击前进保持期的移动判定语义 | 保持期间按"移动令生效中"计：moving()=bool(move_path) 冻结谓词维持为真——移动隐蔽×5000bp、观察者视野减半、toggleAmbush 静止判据不可达三处均按"移动中"结算（§2.5 口径④） | moving() 谓词系冻结成文（IMPL §T M23/A19——"有航点即移动"读法）；停住=战术停靠而非转入掩体（与断箭 AttackMove 停开阔地代价同向）；改谓词连锁 sensing 三乘区+伏击判据，代价大 | 停住接敌的单位持续吃隐蔽惩罚、不能就地转伏击（玩家须手动 halt 后再伏击） | MV-B-23 改B（moving() 改按"本 tick 有效位移"判定——连锁 MV-B-08 与 sensing.py:20-23/:48-49、伏击静止判据，须整体拍板） |

---

## §8. GDD 回写建议清单（只列清单不改 GDD；建议新决策号 D070+、新规则号 R-24+）

| 建议号 | 内容 | 来源 |
|---|---|---|
| **D070** | 移动模式槽与地面移动指令族（攻击前进/强行军/倒车/停止/取消五令+覆盖规则含 handoff 内部通道例外+队列令+当前执行令查询位） | GAP-01/02/03/04/05/06/18 汇总（§2.1/§2.2） |
| **D071** | 移动侧纯血条落地：MOB 暴击拆除、HP≤25% 单阈值速度减半；**连锁待办**：combat.py roll_crit/upgrade_crit 拆除（combat.py:83-98）、CritSlot 枚举处置（FC/SEN/RLD 是否随 D068 一并裁——sensing optics_factor 与 reload_factor 现仍读 SEN/RLD 暴击，**拆除范围须逐槽清点后拍板**）、crit_per_hp_bp/crit_mob_minor_mult_bp 两常数删除 | GAP-14（§2.3） |
| **D072** | 疾跑禁射细则（sprint_until 期间不进入新 AIMING、已有 AIMING 冻结 timer——**挂点=system_timers AIMING 递减门+索敌门**，§2.10-8；速度式不变） | GAP-12（§2.10-8）；GDD-05 A7 补句 |
| **D073** | 森林不减速数据口径（森林瓦片不注入速度 bp，只喂隐蔽/视线） | GAP-09（§2.12）；D026 补注 |
| **D074** | 编组行军速度同步以最慢为准（group_speed_cap 槽；跨排队令保持） | GAP-16（§2.9） |
| **D075** | 炮兵超射程自动进位（最大射程内侧 standoff 航点 QoL；下界半射程；安装走 issue_move） | GAP-13（§2.11）；R-13 补句 |
| **R-24** | 地面移动指令族规则（攻击前进/强行军/倒车/停止/取消——GDD-02 §0 通用规则节） | §2.2/§2.5/§2.6/§2.7 |
| **R-25** | 队形表规则（横队/纵队/楔形+间距常数） | §2.8 |
| **R-26** | 编组行军速度同步规则 | §2.9 |
| **R-27** | 强行军（沿路行军）规则（道路档接线+弃掩体=寻路行为口径） | §2.6 |

---

## §9. 集成点总表（扩展在哪 / 复用在哪；逐文件）

| 文件 | 复用（不动） | 扩展（增量登记） |
|---|---|---|
| sovs/sim/movement.py | system_move 整体（:51-118，契约⑥序列）；move_speed_cm_tick 签名与冻结行 :26-27/:29-31/:32/:36-37；sync_followers :41-48 | ① :22-24/:33-34 MOB 拆除+重伤乘区+编组钳制+倒车乘区（§2.3）；② :80-87 朝向块 REVERSE 分支一行（§2.4 增量④）；③ :109-114 拖曳随动偏移基向改按 facing 反向（增量⑨/MV-B-22——AMB-6；写点位置与"有位移才随动"门不动）；④ 新增 dispatch/make_formation_fn/attack_move_engage_hold/auto_approach_waypoint/issue_move/consume_commands（建议新模块 movement_ext.py 或 movement.py 追加——不动既有函数体） |
| sovs/sim/types.py | UnitInstance 既有 **17** 槽（:291-308——GAP-1 勘误，v1 误记 16）、UnitTemplate 全部（speed_tier :232/turn_rate_deg :234 死槽维持）、MovementClass :108-113、TowPair、moving() :310-311 | UnitInstance 追加 4 槽 + MoveMode/FormationShape 两枚举（§2.1；slots dataclass 追加行） |
| sovs/sim/tables.py | BalanceConfig 既有移动 6 常数（:14-19） | 移动段追加 6 字段（§4）；crit_mob_minor_mult_bp 删除登记（随 D071 连锁） |
| sovs/sim/geom.py | dist_cm/octant_deg/step_toward/round_div/angle_diff 全族只读 | 无 |
| sovs/sim/air.py | §F1~§F7 全部（契约⑪~⑭）；DIR8/PERP8/scale/dir_index :31-46 被地面队形/进位复用 | 无（航空零增量——§3 全部成文维持） |
| sovs/sim/tick.py | world_tick 行序（:360-380）；system_timers 既有递减结构（:202-207） | :366 调用点替换为 system_move_dispatch（§2.4）；:363 TODO consume_commands 落地骨架（§2.2，含 handoff 通道）；**system_timers :202-207 weapon_states 循环增疾跑 AIMING 冻结门（§2.10-8——GAP-3 修复，D072 挂点）**；world 增 road_at/terrain_speed_tile_bp/find_path **三** stub 谓词（§2.14——find_path stub=直线直填 RETURN [to]，AMB-8 修复；算法本体随 MV-B-09 另案） |
| sovs/sim/sensing.py | effective_stealth_x10 :16-36 / detection_range_cm :44-55 两乘区（契约⑳） | 无（强行军不加隐蔽数值惩罚——§2.6-③；攻击前进保持期三乘区口径=MV-B-23 成文不改码） |
| sovs/sim/combat.py | —— | 连锁待办登记：roll_crit/upgrade_crit 拆除（:83-98，随 D071——本档不执行） |
| sovs/sim/rng.py | Channels 0..7 | 无（移动零随机——§6） |
| tests/test_movement.py 等 3 件 | 全部 66 锚点（2026-10-01 实跑通过基线） | 增量落地时须新增锚点：倒车乘区/重伤阈值/编组钳制/攻击前进保持（含 MV-B-23 三乘区口径）/强行军 on_road 接线/队形三表（含楔形锚点 §2.8）/到达模式复位/**T-queue-1 三令排队逐令执行、T-queue-2 cap 跨队列令保持（BLK-1 fix 指定）** 各至少一锚点；**既有断言除 MOB 暴击两例（test_mob_major_immobilized/test_mob_minor_halves）随 GAP-14 拆除改写为重伤阈值版外，其余不得变更** |
| docs/GDD-06-断箭单位移动机制调研.md | 只读 | 勘误登记（本档不执行）：:323"rotating（…types.py:283）"行号误——实为 types.py:276（:283 是 supply_rounds——GAP-4，随 GDD 侧勘误执行） |

---

## §R. v1 → v1.1 逐条修复记录（审查问题 15 条：blocker 1 / gap 4 / ambiguity 10）

| # | 类 | 问题（摘要） | 修复（落点） |
|---|---|---|---|
| BLK-1 | blocker | consume_commands 以 issue_move(queue=FALSE) 消费队列头会清空 command_queue 与 group_speed_cap——Shift 排队/编组同步落地即失效；:139 注释与代码矛盾 | §2.2：issue_move 增 `handoff: BOOL=FALSE` 内部移交通道（只装 move_path+换 move_mode，不清链/不清 cap；UI/AI 不传）；consume_commands 改 `handoff=TRUE` 安装——注释与代码一致（安装后 move_path≠[] 天然阻塞后续队列头）；§2.9/§5 同步"内部通道不清 cap=编组同步跨排队令保持"；补登记锚点测试 **T-queue-1（三令排队逐令执行）/T-queue-2（cap 跨队列令保持）**（§2.2 要点⑤+§9 tests 行——伪代码登记，落地期执行） |
| GAP-1 | gap | 槽位基数错：UnitInstance 实有 17 字段（types.py:291-308 含 sprint_until；IMPL :176 亦记 17），v1"既有 16 槽/16→20"取机制版分项口径 | 头注/§2.1/§5 三处改 **17→17+4=21**（总账 78→82 不变）；头注+§5 注记两基准 sprint_until 归口差（机制版 §0 元素级 vs IMPL/代码单位级 GAP-18 归口）；§9 types.py 行同步 |
| GAP-2 | gap | 互锁表第 3 行声称"issue_move 对全 mounted 单位 REJECT"但函数体无此门 | §2.2 issue_move 补**门 3**（全 mounted → REJECTED）；§2.10-3 双保险描述成真并注 v1 缺口 |
| GAP-3 | gap | 疾跑禁射"已有 AIMING 冻结 timer"需改 system_timers 或 finish_aim，§9 未登记任何挂点——按总表落地冻结不会发生 | 选定挂点=**system_timers**（tick.py:202-207 weapon_states 循环：AIMING 且 sprint_until 未到→跳过 timer 递减；不发射不耗弹由 timer 不归零天然保证；RELOADING 不冻结）+索敌门配套；§2.10-8 重写、§8 D072 补挂点、§9 tick.py 行登记 |
| GAP-4 | gap | rotating 引注 :283 错误（实为 types.py:276，:283 是 supply_rounds；继承自 GDD-06:323） | §2.10-9 引注改 **types.py:276**；§9 增 GDD-06 行登记 :323 同款勘误（GDD 侧执行，本档不改） |
| AMB-1 | ambiguity | 攻击前进保持期 moving() 仍真——sensing 三处乘区（移动隐蔽/静默豁免链/观察者视野减半）与 toggleAmbush 静止判据口径悬空 | §2.5 增**口径④**（推荐选项落地）：保持期按移动令生效中计、三乘区持续生效、静止判据不可达（与断箭 AttackMove 停开阔地代价同向）；登记 **MV-B-23**（推翻通道=moving() 改按有效位移，连锁 MV-B-08+sensing+伏击判据） |
| AMB-2 | ambiguity | WEDGE 公式 r=0 带 −line_s//2 横偏——交错纵队而非楔形，与"楔尖=首元素"注释自相矛盾 | §2.8 改式：**r=0 楔尖 (0,0)，成对元素 ±line_s//2、纵深按对递增**；补 5 元素锚点表；FormationShape 注释同步"楔尖在前、成对左右递增纵深" |
| AMB-3 | ambiguity | 超射程进位消费点直写 move_path，绕过 issue_move 单一入口——覆盖规则/编组钳制交互未成文 | §2.11 消费点改经 **issue_move(MoveCmd{path=[wp], mode=NORMAL}, queue=FALSE 外部直令 / handoff=TRUE 排队消费)**；成文：外部直令四件一体覆盖（清链+退编组）、进位移动恒 NORMAL |
| AMB-4 | ambiguity | stand=max_range−2000 无下界（短程武器得负 stand 航点反向越过目标）；1% 误差覆盖的射程上界未成文而 MV-B-21 对象含超远程武器 | §2.11 改 **stand = MAX(max_range−standoff, max_range//2)**；成文：2000cm 固定余量在 max_range≤196,000cm 时独立覆盖 ≤1.015% 误差、更大射程由半射程比例余量恒覆盖 |
| AMB-5 | ambiguity | turn_rate 消费链字段名（turn_rate_deg vs turn_rate_deg_per_tick）与 10Hz 定标换算未对齐，却断言"落地时即有消费者" | §2.13 补换算式 **`turn_rate_deg_per_tick = MAX(1, turn_rate_deg // 10)`**（MAX(1,·) 防默认值 1→0 零速锁死）+字段名统一连锁待办登记；断言修正为"规划内消费者（经换算），当前 sim 仍无消费者" |
| AMB-6 | ambiguity | 倒车×拖曳叠加时随动偏移按位移反方向算——被拖元素落到牵引车车头侧，位置随动方向未审 | §2.3 边界① 补取向口径并登记**增量⑨/MV-B-22**（推荐选项）：movement.py:109-114 偏移基向改按 `elements[0].facing` 反向（车尾正后方），恒定两态正确；"有位移才随动"门与 pos 唯一写点不动（契约⑨不破）；§2.10-4/5、§9 同步 |
| AMB-7 | ambiguity | 转弯半径草图 R≈speed×573//(turn_step_deg×10) 除零风险（两待出表常数线性合成可为 0） | §3.4 草图补 **turn_step_deg = MAX(1, …)** 守卫说明（随 MV-B-10 一并成文） |
| AMB-8 | ambiguity | §9 只登记两 stub 谓词、find_path 无落点；A* 草图倒数取式未定标且无 bp=0 防护 | §9 tick.py 行补 **find_path stub（直线直填 RETURN [to]，随 MV-B-09 另案）**；§2.14 草图补定标式 **tile_cost = round_div(100000000, bp)**（bp=10000→基准 10000）与 **bp==0→INF 不可通行防护**、道路偏好代价减半 MAX(1,·//2) |
| AMB-9 | ambiguity | 步兵/骑兵倒车令不 REJECT 而靠"速度 0 自然不走"——REVERSE 空转锁（永不到位/模式不复位/current_order 恒 MOVE）与拒令语义两读并存 | §2.2 issue_move 增**门 4**（mode=REVERSE ∧ reverse_speed_bp[class]==0 → REJECTED 显式拒令）；§2.7 语义句/§4 表注同步，空转锁读法删除 |
| AMB-10 | ambiguity | B 编号跨文档撞名（本文 B-01…21 vs AIR IMPL B-01…B-30）；§3.2"B-29①"/§3.6"B-22"未加命名空间 | 本文自有编号全部前缀化 **MV-B-01…MV-B-23**（§7 表头消歧注+v1 对照说明）；外档引用改 **AIR-B-29①/AIR-B-22**（§3.2/§3.6）；全文（§1/§2/§3/§4/§5/§7/§8）引用同步 |

---

## 变更记录

- 2026-10-01：v1.1（审查修复版——blocker 1 / gap 4 / ambiguity 10 全量修复，逐条见 §R：BLK-1 handoff 内部通道+两锚点测试登记、GAP-1 槽位基数 17→21 勘误、GAP-2 全 mounted 拒令门、GAP-3 疾跑 AIMING 冻结挂点=system_timers、GAP-4 rotating 引注 :276+GDD-06:323 勘误登记、AMB-1 攻击前进保持期感知口径（MV-B-23）、AMB-2 楔形公式修正、AMB-3 进位走 issue_move、AMB-4 stand 半射程下界、AMB-5 turn_rate 10Hz 换算式、AMB-6 拖曳随动按车尾取向（MV-B-22）、AMB-7 转弯率 MAX(1,·) 守卫、AMB-8 find_path stub+A* 定标/防护、AMB-9 倒车资格拒令门、AMB-10 MV-B 编号消歧；拍板预登记 21→**23** 条）。
- 2026-10-01：v1 初版（GDD-06 差距全量处置——账目行 38 条〔MOV-GAP-01…37 + 02b〕：adopt 16 / reject 12 / defer 10；另 GAP-12/15 两 adopt 各含半项 defer+adopt 内含糊 9 项，合计拍板预登记 B-01…B-21（v1.1 起更名 MV-B-01…21）；
  地面 +4 槽/+2 枚举/+5 命令/+6 常数（删除登记 1）/航空零增量/PRNG 零随机；冻结契约 22 条逐条核符——
  写作范围预期中"facing 渐进转向"与契约③/GAP-10 reject 冲突，按契约裁定不采纳并留痕（§2.13）；
  航空"转弯几何/速度档"按契约⑪与 GAP-30 defer 处置为推荐方案草图（§3.4/§3.5、MV-B-10/MV-B-20））。
