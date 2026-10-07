"""§F8 world_tick 主循环接线（GROUND_UNITS_PSEUDOCODE_IMPL_v1.7 §F8 :1423-1440 管线，
v1.7 原文行序）+ 地面防空链（sense_air 消费端 / §F4 aa_try_engage / §F9 fire_aa·resolve_hit_aa）
+ 航空两行挂点（AIR_UNITS_PSEUDOCODE_IMPL_v1.4 头部增量登记清单①）：
  - air_recon_step(world) 挂 ③system_sensing 与 ④system_combat 之间（GAP2-01）；
  - aircraft_tick(world) 挂 ④system_combat 与 ⑤system_projectiles 之间。

已接线（凡已有实现真接）：
  - update_phase（§F8 :1413-1421：按 phase_ticks 盲部署 600→实战 13200→
    结算推进。2026-10-03 发起人拍板：盲部署 90s→60s、取消开局禁火相位（D007/D008
    废止）、实战时长不变；迁入实战拍对在场存活 canInfiltrate 单位 infiltration_timer=600——渗透
    60s 从实战期起算（v1.6 ④A 拍板）。相位起点 phase_start_tick 为 §D.6
    未列的实现记账槽：注入 phase 自构造 tick 起满时长，不被绝对 tick 推导改写）；
  - consume_commands（§F8 :1425-1426 命令驱动：World.command_queue FIFO、本 tick
    命令全部落地、零掷骰；§D.7 :256-268 全集 22 类命令分派骨架已接——cmd_purchase
    （§F7 :1374）/MoveCmd/StopCmd/SprintCmd（MOVEMENT v1.2 §2.2，2026-10-04 命令层块）
    /PivotCmd（PB-51，2026-10-04 原地转向块）/SmokeCmd（PB-53 自卫烟幕路径，
    2026-10-04 自卫烟幕块——武器烟弹路径仍 TODO）/AttackCmd（PB-56 批① 作战链
    命令块，2026-10-06——§F4 :848 cmd_attack 直射指定目标含建筑）/
    SetModeCmd/ToggleAmbushCmd/SetStanceCmd（PB-56 批① 作战链命令块·余三命令，
    2026-10-06——§F6 :1193 cmd_set_element_mode/§F4 :874 cmd_toggle_ambush/
    §D.7 :261 SetStance 最小写点，批① 就此收口）/MountCmd/DismountCmd
    （PB-56 批② 机动链命令块·上下车，2026-10-06——§F6 :1137/:1131
    cmd_mount/cmd_dismount）/TowCmd/UntowCmd/DeployCmd/PackCmd（PB-56 批②
    机动链命令块·拖曳展开，2026-10-06——§F6 :1228/:1242 cmd_tow/cmd_untow+
    :1072/:1116 cmd_deploy/cmd_pack_or_move；start_tow §F2 :494-516 随块落
    combat.py）/SetSniperCoverCmd/BuySuppliesCmd（PB-56 批③ 支援链命令块，
    2026-10-06——§F6 :1258 cmd_set_sniper_cover/:1215 buy_supplies；Garrison/
    UnGarrison 已随 PB-57 落地转回归验证）/FormationCmd（MOVEMENT v1.2 §2.2
    队形选择——§D.7 22 类外命令，2026-10-06 PB-56 批③ Formation 族块：
    cmd_formation 逐单位写槽；同块 issue_group_move（tick.py §2.9 组下令入口
    直调）+move_speed_cm_tick §2.3 增量① cap 钳制消费者接线）
    已落地（含 SetAirdropBeaconCmd→cmd_set_airdrop_beacon :1269——2026-10-06
    补落后 §D.7 22 类分派支**全部真调用**，速度链评审#1 滞文勘正），未知类型抛
    TypeError；queue_command=AI/测试虚拟玩家入队口）；
  - system_timers（§F8 :1442-1462 最小集：渗透计时/reveal/压制衰减/展开收装计时/
    武器 AIMING·RELOADING 状态机 timer + RELOADING→READY|EMPTY 迁移（落 EMPTY 即
    登记 await_resupply——:1458-1459 方案19，⑥块接写点）/烟区 ttl 递减+PB-53
    自卫烟幕到拍落烟（2026-10-04——pop_tick 到拍以元素当前位置为心 append
    SmokeZone，详见 cmd_smoke））；
  - system_move_dispatch（2026-10-04 命令层块起替换 movement.system_move 直调——
    MOVEMENT v1.2 §2.4/§9 :576：dispatch 包装器集中承载模式感知：ATTACK 接敌保持
    （attack_move_engage_hold §2.5——遇已发现敌停住交战、非边走边打）、MARCH 道路门
    （on_road=MARCH∧road_at——MV-B-17 普通机动在路不吃）、瓦片注入
    （terrain_speed_tile_bp）、队形接线（make_formation_fn §2.8——NONE=None 现状
    逐位保持）、到达模式复位；冻结函数 system_move 本体零改动仍承载拖曳随动与
    随动班）；
  - §2.2 移动命令层（2026-10-04 命令层块；PB-32/PB-12 双层口径）：MoveCmd 分派支
    →issue_move（外部通道：门1 展开/收起互锁+门3 整班车载拒令+门4 倒车资格
    FOOT/HORSE 拒令——门2 PINNED 士气槽未落地恒假；queue 位分派=Shift 排队入
    UnitInstance.command_queue 链尾 / 非排队新令四件一体覆盖 move_path+move_mode
    +清链+清 group_speed_cap——GAP-05/18；handoff 内部移交通道只装不清——BLK-1，
    分支次序冻结 AMB-11；命令航点逐段经 world.find_path 展开=⑦块登记的移动侧接线，
    prefer_road=MARCH）；StopCmd 分派支→cmd_halt（HaltCmd 语义 MV-B-18：清航点+
    复位模式+清队列移动令保动作令；~~CancelCmd 全清变体未落地——TODO~~〔2026-10-07
    命令族收口块：已落地 cmd_cancel——全清变体（队列+动作令+任务体+pivot），见
    §2.2 命令层处理体段〕）；SprintCmd
    分派支→cmd_sprint（sprint_until 唯一写点=now+sprint_duration_ticks；2026-10-07
    命令族收口块增冷却门 now<sprint_until+sprint_cooldown_ticks→REJECT——发起人
    拍板采纳，初值 0 哨兵豁免首冲）；新增
    consume_unit_commands（单位级队列消费，挂 world_tick ①前——队列头执行条件=
    无进行中移动令、handoff=TRUE 安装、REJECTED 令丢弃不回队首、非 NORMAL 移动令
    安装后 BREAK 交还控制）；D072 疾跑禁射两门（system_timers AIMING 递减冻结+
    fire_permitted ⑦ 索敌门——§2.10-8）；类型/槽位增量=MoveMode/FormationShape
    两枚举+UnitInstance +4 槽（move_mode/command_queue/group_speed_cap/
    formation_shape，types.py §2.1）；BalanceConfig 移动段 +3 字段
    （reverse_speed_bp/formation_line_spacing_cm/formation_column_spacing_cm——
    §4 其余 crippled×2/auto_approach_standoff 随各自消费块出表）；
  - system_sensing（sensing.system_sensing 周期门 + sense_air 对空分支；2026-10-07
    感知接线块：经 sensing.terrain_sensing_channels 喂穿林/穿烟/林内三通道——
    PB-53 留待项②收口/GAP-27 实装，fire_at 校射同步）；
  - fire_arc<360 元素 rotating 每 tick 复位（v1.7 GAP-25 :1430-1433）；
  - system_combat（§F4 :674-691：① AIMING 到期 finish_aim——对空出口 fire_aa +
    地面出口 fire_permitted 复核→fire_direct（M4/G32）；② aa_roster 名单对空自动
    交战链 aa_try_engage；③ 对地分流——e.mode==DIRECT→ground_direct（select_target
    评分选取+射界门 rotate_step R-09+begin_aim）/ INDIRECT 且模板 INDIRECT 位→
    indirect_role（方案3 静态门；R-15 自卫直射仅已发现敌 M20、模板判空短路）；
    尾部 process_fire_mission（方案3 静态门+fire_mission 非 NULL+任一 INDIRECT 元素
    ——R-14 半轮前 ⌈N/2⌉ 门 AMB-09 → fire_at：R-13 三形式落点/盲射声测圈叠加/
    R-16 校射仅 POINT ⑩A 按批 AMB-06/曲射档案 M8/弹药任务计数按 salvo/声测痕迹
    upsert_sound_track ㉗A 不写 reveal_timer/shots_left<=0 销毁任务体方案10）；
    fire_permitted 六门（:693-706）、select_target（:708-725，⑲A 狙击剔 MECH、
    M10 车载班排除、并列取列表序首）、threat_value、select_profile（:790-804，
    R-11 alt_profile + 钨芯 restricted_left 实例副本 M16）、fire_direct（:806-846，
    acc 乘区书写序 //10000、渗透清零仅 MELEE/SNIPER ⑦A、AMB-14 不喂声测、
    jitter_small 零幅实现+accuracy_ratio 17 段表 §D.0 未列恒等——均见
    discrepancies）、cmd_fire_mission/cmd_cancel_fire_mission（:960/:972，R-13
    任务创建 REJECT 两门）已接；rotate_step（§F5 :1051-1058 + AMB-5 换算
    MAX(1,turn_rate_deg//10)）落地 movement.py、approach_deg_of（v1.7 零定义体，
    frm→to 方位——:744/:870 按语义换实参序）落地 geom.py、aura_bonus_bp（§F1
    :425-427）/mark_resupply_if_needed（§F2 :447-449——fire_direct :811/fire_at
    :951 弹药缺口登记已接）落地 combat.py；FireMission
    任务体+fire_mission 槽（§D.6 :233-236/§D.4#10）落地 types.py、IntelCircle/
    SoundTrack（§D.6 :223-227）与 Projectile.pen_bonus（:790 档案位）落地本文件；
    make_unit 增 restricted_left 深拷贝（§D.5#11 M16）；掷骰通道纪律：直射=HIT+
    SCATTER、曲射=SCATTER only——AIR/CRIT/SNIPER/SPOT/SONAR/ECONOMY 不触碰）；
  - aircraft_tick / air_recon_step（air.py 行为层直调）；
  - system_projectiles（§F8 :1464-1474：step_toward 推进 + 到达分派——四支全接：
    BALLISTIC→resolve_blast（含空投炸弹 AirProjectile 鸭子兼容）/ 对空
    resolve_hit_aa / 地面 will_hit→resolve_hit / 近失压制 ELSE 支）；
  - §F1 落点结算组 + §F2 生命周期完整体（2026-10-02 ⑤块，combat.py）：
    resolve_hit（:321-346——建筑支 ×vs_fort 无装甲曲线/失的守卫 B9/方案1
    combat_style 分支/装甲面链 compute_hit_facing（v1.7 覆盖序：驻楼→转向→
    顶攻→角度）/MECH 暴击掷 CRIT/面压制）、resolve_sniper_hit（:348-371——
    R-02 概率掷 SNIPER 通道（首消费者）、掩护查 cover_by_target 旁表（键=
    unit.id）、singleSquadCard 概率灭排、tally≥3 灭最低血班（存活元素空集
    防御跳过——见 discrepancies））、resolve_melee_hit（:373-380——AMB-05
    绕装甲曲线、政委 MELEE 光环乘区 GAP-13 改锚）、resolve_blast（:402-412
    ——SMOKE→SmokeZone 三字段口径（radius/ttl 出 cfg）、溅射 AMB-01 衰减式
    与乘区书写序、MECH 暴击掷 CRIT、建筑 weapon vs_fort 直扣）、
    compute_direct_damage（:315-319）/falloff_bp（AMB-01 定义式——
    inject_suppression_area 同源改用）/alive_elements_within（快照语义）、
    apply_damage 完整体（:435-440——hp<=0 走 destroy_element；存活缺口
    带伤登记 :439-440，原登记"⑥块补"因本块重写主体一并落地）+
    destroy_element（:451-484——R-07 车毁连带按元素去重只结一次、dmg=
    (hp*(1000−permille)+999)//1000 向上取整式、旁落位=车毁同点位（偏移
    未定标——见 discrepancies）、hasSupply 物资清零、驻楼引用清理、
    release_tow_if_involved GAP-24 元素级、装载请求撤销 v1.5 M12/㉑A 谓词、
    全灭 unregister_unit_refs+alive=False）+ unregister_unit_refs（:487-492
    ——信标/掩护旁表按 unit.id 键注销）+ hit_building/collapse_building
    （§F5 :533-541——Building 实体/world.buildings/cfg.building_collapse_dmg
    随块落地，§D.0 :76 默认 0；写侧【2026-10-06 更新：apply_map 装配（建筑实体块）
    + GarrisonCmd/cmd_garrison（驻楼命令块）已接——world.buildings 不再恒空】）；
    stop_tow 自本文件迁 combat.py（destroy_element 消费需要——顶部 import
    再出口保既有路径）、SmokeZone 迁 types.py 增 radius_cm 字段（§D.6 :222
    三字段口径；字段序第三兼容既有 (center, ttl) 位置构造——resolve_blast
    关键字传参）、World 增 cover_by_target/buildings 两容器；掷骰通道纪律：
    暴击=CRIT、狙击=SNIPER（首消费者）——直射链 HIT+SCATTER 口径不变）；
  - system_supply（§F6 :1308-1341 ⑥ 后勤：R-18 await_resupply 扫描集补弹
    （2026-10-03 拍板重设计：一池通用补给按重量计——补弹 take=MIN(缺口,
    剩余重量//每发重量, ammo_resupply_per_tick)、EMPTY 有弹转 READY）
    + 医疗（仅 INFANTRY 带伤，heal=MIN(缺口hp, 剩余重量//med_weight_per_hp_g)）
    + 尾部 needs_resupply 自清理 + R-19 维修分支（repair_radius 同队门、修满清 crit、
    stop_tow(REPAIRED)）；needs_resupply（§F2 :442-445）随 ⑥ 块落地 combat.py、
    stop_tow（§F6 :518-522）⑤块迁 combat.py（本文件再出口）——start_tow（§F2
    :494-516）/cmd_tow 随 PB-56 批② 拖曳展开块 2026-10-06 落地〔原「仍未实现」
    留痕就此闭环〕）；
  - mount_requests_step（§F6 :1169-1190 ⑦ 上车进度：方案12 惰性表 None 早退；
    到期复核撤销（不在编/切出可载 CARGO|TOW/座位超占）+ 逐班挂 mounted_in（㉑A）、
    跨卡入 cargo_units（单位级去重）；载具占用数/在途请求数助手与 MountRequest
    记录（types.py，eq=False 引用身份）随块落地；cmd_mount/cmd_dismount 处理体
    【2026-10-06 批② 上下车块已接——见下方 PB-56 批② 条目】）；
  - system_economy（§F8 :1476-1479 ⑧ 按秒（world_tick :1438 字面 %10 门）：
    2026-10-03 拍板：收入机制整体删除（发起人裁定"没有收入机制"——
    income_per_second 字段与每秒加成一并去除，GDD-00 :22「无持续经济」胜出）→
    spawn_step（§F7 :1381-1401 出牌节流：内部 spawn_interval_
    ticks 门 + 逐玩家 pop(0) FIFO + 渗透卡地图边缘（2026-10-03 拍板：随机选边
    沿边随机取点）/其余**直接落己方部署区锚点**（2026-10-03 拍板：地面单位抽象
    为无宽度点单位、可叠放——出牌序偏移与步长常数随之删除，原"排到图外"问题
    不复存在；部署区地图数据缺失——锚点=己方底边中点，见 discrepancies）
    + R-07 开局车载默认形态 + 渗透计时按相位置 + aa_roster 登记
    （add_unit 承载））→ system_objectives（§F7 :1403-1405 占点半径内仅一队存活
    则改 owner；2026-10-03 拍板：补给箱不算占点单位——cost=0 模板过滤）。
    零掷骰（不触 ECONOMY 通道——该通道现仅渗透出生点消费）；
  - D031 结算裁决（update_phase 迁入结算拍触发，§F8 :1415 仅写"→结算"无函数体；
    2026-10-03 发起人拍板重设计（取代 GDD-00 :137/:196 三级推定）：占点数多者胜
    →同比剩余地面单位分值（Σ template.cost）→再同比剩余总血量→再同判队 0 胜
    （无平局，winner 恒非 None；战区五占点为场景数据侧约定）；存 world.result
    （§D.6 未列记账槽，Settlement 记录三级证据）；
  - 尸体清扫（:1439）与烟雾 ttl 过滤（:1440）；
  - system_timers 的 EMPTY→await_resupply 登记（§F8 :1458-1459 方案19——RELOADING
    迁移落 EMPTY 且 u 未登记才 append；2026-10-02 ⑥块补写点，与 apply_damage 带伤
    登记（:439-440 ⑤块）/ fire_direct·fire_at 弹耗登记（mark_resupply_if_needed）
    构成登记三写点，system_supply 尾部统一自清理）；
  - World.spawn_paratroop / spawn_airdrop_crate 真实现（2026-10-02 ⑥块自记录桩转正；
    原 paratroop_log/crate_log 桩记账字段一并移除——§D.6 World 无此二表、全仓零消费者）：
    前者=make_unit+add_unit+渗透计时按相位置（AIR §F6 :610-619 回调——D017 落地即
    地面一命单位、deck 份装机时已扣勿重扣、卡源=data/gen/cards_ground.v1.json 经
    card_loader.load_library 的 CardRecord.unit_template）；后者=§F6 :1343-1354 一次性
    CARGO 补给单位（airdrop_crate_template 机制层内置模板——非卡组卡面：speed_tier=0/
    装甲 0/HP=cfg.airdrop_crate_hp（"小"未定标占位 1）/hasSupply 位必配（GAP-21）/
    supply_radius_cm=8000；mode=CARGO+物资预填；stealth_base/template_id/category/cost
    等未定标结构位取值见登记表 discrepancies）。零掷骰（两 spawn 与 AIR 通道无涉）；
  - §2.14 寻路层（MOVEMENT_PSEUDOCODE_v1.2 §2.14 :404-417 / §9 :576 登记，2026-10-02
    ⑦块落地）：新模块 sovs/sim/pathfind.py——TerrainLayer/TerrainTile 地图载体挂
    World.terrain（§D.6 未列槽，None=未接入）+ World 三谓词 road_at/
    terrain_speed_tile_bp/find_path（§2.14 字面签名；from→frm 形参名适配）。
    §2.14 已定标照写：tile_cost=bp==0→不可通行 / round_div(100000000,bp)（bp=10000
    →基准 10000）/ prefer_road 减半 MAX(1,·//2)；DIR8 固定序（octant 环）展开；
    输出共线段合并航点；堆 (f, 插入序号) 决胜。发起人裁定的补充定标（均记
    discrepancies）：瓦片边长=layer.tile_cm（默认 2500）、对角步 ×cfg.
    pathfind_diag_cost_bp(14142)//10000（tables.py 出表）、启发式 h=octile 按
    代价模型自身取整折算=(M−k)×min_cost+k×(min_cost×diag_bp//10000)（min_cost
    数据推导；对角乘子与真实步代价同式 floor ⇒ admissible+consistent——评审修复
    2026-10-02：原 round_div(4142·k) 半舍入版本两性质俱失、实测可返回次优路径，
    修复后独立 Dijkstra 交叉验证 5112 查询零次优）、终点格不可通行或全图不可达→兜底
    RETURN [to]（同 AMB-8 stub 口径）、禁切角、末点=精确 to 不含起点、图界=
    map_extent 图内（终止性闭合）、起点格豁免通行检查。零掷骰（契约⑰——不触碰
    任何 PCG32 通道）。terrain=None stub 三口径不丢：road_at=False /
    terrain_speed_tile_bp=None / find_path=[to]。性能特征（2026-10-02 实测）：稀有
    便宜瓦片（路）拉低 min_cost → 启发式变弱，1km 图 1000cm 网格（1e6 格）对角
    单查询实测 ~8.4s（近 Dijkstra 退化）；默认 2500cm 瓦片（160k 格）同规模
    实测 ~1.1s。路径缓存已落地（2026-10-04 寻路接线块，PB-10「随消费侧接线再落」
    收口——PB-34 关闭）：find_path 结果按（起点格, 终点格, 精确 to, class,
    prefer_road, 对角 bp, 展开上限, terrain_fingerprint）键存 World.path_cache
    （§D.6 未列实现记账槽），LRU 有界=cfg.pathfind_cache_entries（tables.py 出表，
    0=禁用）；键含地形内容指纹（tiles 逐块内容+tile_cm+layer 身份+map_extent）——
    地形/图界任何突变天然换键失效（零行为差），不可达/超限兜底（最贵分支）同键
    缓存；frm 仅经
    起点格入键（体内 frm 唯一消费=_tile_index——同格不同点输出恒等）。移动侧
    接线（命令层块 2026-10-04 落地、本块复核）：三谓词运行时调用方=issue_move
    （find_path 逐段展开、prefer_road=MARCH）与
    system_move_dispatch（road_at/terrain_speed_tile_bp——§2.4 增量⑥⑦）——
    PB-36 随之关闭；正式地图/地形数据：CSV 示范图数据管线已落地（2026-10-06
    PB-58 块②，见下方专项条目——Tiled 编辑器管线仍留作将来策划制图层）；
    World.terrain 缺省 None=stub 直线直填保持（make_world 不自动挂图——挂点=
    map_loader.apply_map 显式挂载，块③整局接入消费），最小数据层=TerrainLayer/
    TerrainTile（sparse 旁表）。性能债留档（2026-10-04 拍板=登记
    收口+留档）：缓存只救重复查询，首查实测 ~1.1s（默认 2500cm 瓦片 160k 格）、
    最劣 ~8.4s（1000cm 网格近 Dijkstra 退化）——正式地形层接入前必须先做预算
    限幅或分层寻路（拍板清单性能待办 PB-50），现役对局 terrain=None 零影响。
    预算限幅已落地（2026-10-06 PB-58 块①，PB-50 前置门关闭）：find_path 展开循环
    真实展开数（done 集增量）超 cfg.pathfind_max_expansions（tables.py 出表——
    PB-58 拍板「max-expand 常数入 BalanceConfig、超限直线兜底」；0=不限幅，区别于
    cache_entries 的 0=禁用）即熔断→直线兜底 RETURN [to]（同 AMB-8/不可达口径），
    最坏单查询耗时上界=cap×单展开成本（仅覆盖 A* 循环项——缓存未命中查询另有
    terrain_fingerprint/_min_step_cost 前置费用随瓦片数线性、不在 cap 内，PB-58
    评审留痕）；默认 500,000=占位（黑盒二分实测基准全部
    10 查询展开包络 max=327,342[S3 角到角]——bench/pathfind_bench.py cap 模式可
    复跑，S1 12,204/S2 51,072——取同量级 1.53× 余量整洁上界，已测档位零行为差
    [位级一致验证]；勘察 5 万~10 万紧案会熔断 S3 角对角改变已测行为、1e6 跨量级
    近失效，均未采——性能常数待发起人复核）；cap 入缓存键（cap 变更=全量换键，
    与 diag_bp 同款机制——cap 调大后旧「超限兜底」条目天然失效不冒充真路径，
    零特判）；熔断判定纯计数零掷骰（契约⑰）；PB-50 备选（分层寻路/指纹缓存/
    惰性指纹）当前档位不需要——限幅已覆盖（2km 示范图档限幅是保险丝而非现痛，
    PB-50 的 61ms 指纹担忧系百万格量级）。测试 TestExpansionCap 7 锚；
  - 正式示范地形图数据管线（PB-58 块②，2026-10-06；拍板清单 PB-58 行留痕）：
    CSV 手写 2km 示范图走数据管线接入（照 ground_cards/PB-52 五步全链先例）——
    data/map_demo_2km.csv（声明式：一行一声明、kind∈{map,rect,polyline,building}
    分派、未用列留空门；区域矩形+道路折线，不逐格手写）→ tools/build_map.py
    （utf-8-sig+stdlib csv+int 白名单+公式注入拦截+未知列拒——build_cards 骨架，
    零 pydantic；确定性栅格化=矩形直填+折线整型 Bresenham+方形笔刷膨胀+文件序
    画家后绘覆盖先绘）→ data/gen/map_demo_2km.v1.json（瓦片类型 int 表示
    0/1/2、(ix,iy) 排序字节稳定、源 sha256）→ sovs/sim/map_loader.py（stdlib-only
    严格 int——card_loader 纪律）→ MapData（layer/extent/tile_cm/forest_tiles/
    buildings）＋挂点 apply_map（构造后赋 w.terrain+对齐图界/中心，make_world
    不动）。图幅=B 案 200000×100000（80×40 瓦片）与现整局 MAP_SIZE 同幅可原位
    接入——2026-10-05 发起人默认裁决（未即时作答，可推翻；格式图幅无关：map 行
    声明 extent，换 2×2km 方形图零格式改动）。瓦片语义：ROAD=on_road 零速度注入
    （MARCH 道路地板+prefer_road 减半既有机制承载）；FOREST=旁挂 forest_tiles
    集合、不入 layer.tiles（§2.12 拍板：森林不减速——寻路侧与缺席瓦片恒等；
    sensing 侧 in_forest_fn 通道待接：sensing.py:66-69 形参已备、world_tick 调用
    点未喂——本块划界=不接线不冒充，林区当前为纯格式示范数据，见登记表
    discrepancies〔**2026-10-07 感知接线块：已收口**——World 增 forest_tiles
    旁挂槽（smoke_zones 邻位）+apply_map 挂 md.forest_tiles；sensing.
    terrain_sensing_channels 单点装配三 fn，world_tick ③ system_sensing 与
    fire_at 校射（point_in_friendly_vision）两调用点均已喂；林区自此真实喂
    探测衰减（示范图 4 林区生效），纯地形用户（无挂图/空集）逐位不变；
    测试 tests/test_sensing_terrain.py+校射烟阻断锚（test_ground_combat）〕）；
    RUIN=TerrainTile 四类同值 speed_bp=cfg.ruin_speed_bp（tables.py
    出表 4000——无据占位待数值章节定标，PB-58 ask「可通行减速率占位」裁定勘察
    decisionPoint 三选一；loader 侧注入非烘焙，调值无需重建 gen JSON；bp==0
    即不可通行——数值章节可选废墟=实体屏障）；building 行=PB-57 建筑锚数据位
    占位（拍板清单 PB-57 行「正式建筑布局随 PB-58 地图数据格式后接」——格式留位，
    footprint/hp 占位待定标，loader 透传 BuildingSpec 非实体）。图内容：横贯
    干道+4 支线路网、4 片成片林区（648 瓦片）、3 村庄废墟区块（256 瓦片）、
    5 建筑锚；路网后绘=穿林成道/穿村成街。格式规格权威=docs/DATA-02-地形图数据
    格式冻结-v1.md。测试 tests/test_map_pipeline.py 56 锚（栅格化手推/构建门/
    工件确定性[提交 JSON==重构建]/loader 门/三类瓦片×三谓词/真实绕障[三类别
    绕 V2 横带+独立 Dijkstra 最优仲裁；WHEEL 直穿 vs FOOT 绕 V1 对比]/prefer_road
    真上路/SOUTH 锚点护栏/零掷骰）。零掷骰（全管线纯整数确定性，不触任何
    PCG32 通道）；
  - 正式示范图整局验收（PB-58 块③·收口，2026-10-06；**sim 零行为改动**——
    apply_map 挂点即块②预定的接入面，本块只增 tests/test_fullgame_acceptance.py
    场景与锚）：build_map_world 场景工厂（lean 卡组＋apply_map 挂示范图——图幅
    200000×100000 与整局 MAP_SIZE 同幅原位接入）＋HeadlessAI 增 keyword 参数
    anchors/move_mode（缺省=既有行为逐位不变；地图场景=MARCH 令＋图内侧翼敌
    锚点——勘察③「AI 加一档 MARCH 令」：prefer_road 与道路地板均只走 MARCH）。
    移动令链路整局实证：MoveCmd→issue_move→_resolve_move_path→真 A*——首受令拍
    双方 move_path 10/8 航点（逐点定锚+结构断言：航路零废墟格=绕 V2 横带、
    大半程路面=prefer_road 上路）；专用机动场景锚 MARCH 道路地板（TRACK tier2
    越野 31→路瓦 170 两档逐拍可观测，NORMAL 对照同瓦恒 31=MV-B-17 整局锚）与
    实走绕障（V2 东西横穿全程贴 y=37 走廊）。整局 seed 42 三相位全程无异常、
    结算产出、队1 首单位完成侧翼横穿整图；同 seed 双 world 逐 tick 指纹位级
    一致——**指纹面核对留痕**：full_fingerprint 不含 path_cache（§D.6 未列
    记账槽、键含地形内容指纹的纯派生 memo——值确定性由键构造保证），双跑
    缓存一致性由测试侧剥层身份（terrain_fingerprint 首分量 id(layer)——换层
    天然换键）后有序条目比对单独补面。性能观测（量级留档，工具侧计时照 bench
    先例）：整局 12 查询/总 ~63ms/单查询峰值 ~12ms（80×40=3200 瓦片档）——
    限幅界内为结构论证：图面瓦片总数 3200 << pathfind_max_expansions=500,000
    ⇒ 保险丝在本图不可能触发 ⇒ 全部查询真 A*（勘察①「限幅是保险丝而非现痛」
    整局实证）。边界语义登记（discrepancies 同款）：北部署锚点 (100000,100000)
    恰落图界线（tile (40,40)=图外，图内域 iy≤39）——立位瓦片缺席=类级缺省三
    谓词、移动起点格豁免可正常寻出（pathfind.py 实现闭合规则）、以它为终点
    的令走直线兜底（§2.14 既定口径）——示范图 AI 锚点全图内（勘察③护栏锚），
    _deploy_anchor 不动（改锚点=全 seed 重锚 churn，正式部署区数据接入后随
    PB-35 一并换锚）。整局未暴露块①②缺陷（修复清单为空，如实报告）。测试
    TestDemoMapFullGame 5 锚；
  - 整局验收（⑧块·最终门，2026-10-02；本块零仿真核心改动，只增测试
    tests/test_fullgame_acceptance.py）：无头 AI 对 AI 打完整一局——盲部署 600→
    实战 13200→结算三相位全程（2026-10-03 拍板：禁火段取消、部署 60s）+ D031 胜负输出 + 全程无异常；AI 驱动器
    （HeadlessAI，tests 侧、零渲染依赖）只经 queue_command/consume_commands 发令
    （部署相位按卡组序购卡、实战期发移动/攻击/炮击任务/取消任务令——2026-10-04
    命令层块起移动令经 issue_move 真落地（双方首单位真实机动、结局锚随之重锚）；
    攻击令按本表 TODO 丢弃、炮击任务令因元素初始 mode=DIRECT 且 SetModeCmd 未
    落地被 cmd_fire_mission 双门 REJECT，整局无任务体建立；实际交战由 §F4 自动
    交战链承载〔**2026-10-06 更新：AttackCmd/SetModeCmd 已随后续块落地——
    本段为⑧块成文时点状态留痕；攻击令转活后既有锚逐位不变的机理注见下方
    PB-56 批① 条目，炮击任务链整局转活（AI 补发 SetModeCmd）见 PB-56 批①
    余三命令条目④**〕）；同 seed 双 world 整局（含结算尾段）逐 tick 全状态指纹位级相等
    ——指纹面为八块后完整容器（fire_mission 弹药计数/物资槽/挂载/await_resupply/
    mount_requests/objectives/玩家经济/声测痕迹/建筑/拖曳对/裁决 + 八通道 PCG32
    内部 state），已做敏感度负对照（hp/通道 state/待补给集单字段扰动必被捕获）；
    多 seed 冒烟覆盖混编卡开局车载/渗透计时/狙击 R-02/烟弹 SmokeZone 生命周期/
    窄射界 R-09 转车体/磨耗耗弹 EMPTY 迁移/多玩家/52 单位大编队——合计 25+ 整局
    零异常；通道纪律整局锚定：地面侧消费面={HIT,SCATTER,CRIT(,SNIPER)}，
    SPOT/SONAR/ECONOMY/AIR 全程零消费。整局跑通未暴露前块缺陷（修复清单为空，
    如实报告）；
  - 断箭设定数值块（2026-10-04；docs/断箭移动机制映射_v1.md §三 gapFills+§四
    conflicts）：BalanceConfig 移动段 +2 占位字段——sprint_cooldown_ticks=600
    （断箭社区 60s 低置信、官方仅 recharge 定性=核证 v1 N22+未确证#6；冷却门
    是否建模待发起人拍板，零消费者不接线）、water_speed_bp=5000（两栖水上瓦片
    注入值=类级越野 bp×此值//10000≈50%——步兵水上 9/越野 18 折算、两栖载具数值
    未公布=未确证#10；条件性条目仅随 MV-B-02 改B 生效，零消费者不接线）；
    侦察段 +3 字段 stealth_move_mult_bp/forest_walk_silent_mult_bp/
    move_vision_mult_bp——映射冲突3（移动×感知三乘区 vs 断箭官方 Detection 无
    移动项）发起人**默认裁决 B（可推翻）**：行为/数值不变仅出表（原 sensing.py
    硬编码 5000/20000/÷2），sensing.py 改读 cfg、r×5000//10000 ≡ r//2 位级一致
    （r 恒非负——combat.optics_factor_bp ∈ {3000,6000,10000}〔**2026-10-07 D071
    全拆批注**：现恒 10000（口子②重启后恢复三值域）——r 恒非负论证不受影响〕），
    全量回归 487 绿
    护栏；冲突1（森林减速 N14/分歧 D1）发起人**默认裁决 A（可推翻）**=维持
    MOVEMENT v1.2 §2.12 森林瓦片不注入速度 bp（零代码零常数；GDD-06 G6 结论
    降级"留痕待复核"随 GDD 侧版本执行——映射档 §四.1/§六.5 已标注裁决）；
    冲突2（PINNED 可移动性 N24/MV-B-03/04）2026-10-04 发起人拍板=**断箭式（双改B）**：
    PINNED 不再拒令、速度×pinned_move_mult_bp（5000=减半，判据缝 movement.pinned
    待 GDD-05 士气槽、暂恒假零行为差）+ 冲刺开跑拍压制×sprint_suppress_cut_bp
    （5000=减半，cmd_sprint 已承载）——§2.2 门2/§2.4 门注释同步改锚、映射档 §四.2
    已标注；movement.py 消费端逐条
    对齐复核（速度档 speed_table/类级地形 bp 四值/道路 170 取 max/疾跑升档钳 5/
    拖曳锁档/队形间距/倒车门 4/MOB 现行=速度链块拆除待办）全部 cfg 出表零漂移；
    tests/test_movement_settings.py +9 锚（四类地形 bp 行为锚+表 pin/
    reverse_speed_bp 数据 pin/两占位 pin/三乘区 cfg 覆盖生效+5000≡//2 等价
    穷举+NO_MOVE_VISION_PENALTY 豁免）；零掷骰（本块零随机——不触任何 PCG32 通道）；
  - PB-51 原地转向（2026-10-04 拍板纳入·本块落地——断箭 N17 neutral steering/
    映射 §五.9；**推翻 MOVEMENT_PSEUDOCODE_v1.2 §2.13 reject 的静止分支**：静止车体
    改朝向不再即时，耗时=|角差|÷类分档速率整数推导——移动中 facing 仍即时 8 扇区，
    两口径成文分立，§2.13/映射 §五.9 已加日期批注）：新命令三件套 PivotCmd
    （§D.7 命令类+分派支+cmd_pivot 处理体——三前置门与 issue_move 同款：展开收起
    互锁/整班车载/全被拖；接受=停车（HaltCmd 语义）后写 unit.pivot_to，%360 归一）；
    UnitInstance +1 槽 pivot_to（21→22 槽，-1 哨兵）；消费点=system_move_dispatch
    头部 pivot_step（movement.py——独占移动拍、步进式同 rotate_step、M3/B04 按
    当前角差重算不锁存、GAP-03 谓词排除车载/被拖元素、全员到位自清）；速率=
    cfg.pivot_rate_deg_per_tick（tables.py——FOOT/WHEEL/TRACK/HORSE=(10,6,8,10)，
    履带快于轮式按拍板方向；量级锚 N15 两档 60/80 疑占位对调指派、FOOT/HORSE 无据
    占位，全部待数值章节定标）；互斥不变式 pivot_to>=0 ⇒ move_path 恒空（双写点：
    cmd_pivot 清链 / issue_move 外部非排队新令清 pivot；StopCmd=cmd_halt 一并中止
    pivot；consume_unit_commands 队列头执行条件 +pivot_to<0——排队移动令等 pivot
    完成）；期间禁射=fire_permitted ⑧ 门（新 AIMING 与 finish_aim 在途复核双拦，
    对空链不受约束=⑦ 疾跑门同款 R-17 最小许可集口径）；SIDE 暴露=GAP-25 复位环
    改锚（world_tick ：1710 一带——fire_arc<360 元素 pivot 期间维持 rotating=TRUE，
    转向慢=暴露窗口 R-09 同语义；360° 炮塔载具不受影响=方案6 现状口径保持，断箭
    无此细节证据不扩）。tests/test_pivot.py +19 锚（表 pin/耗时随角度差 TRACK 23t
    WHEEL 30t/到位拍即完/负角归一/被拖不随动/⑧ 门+ground_direct 集成禁射-转完
    复射/GAP-25 维持-复位/互斥四向/三前置门）。零掷骰（不触任何 PCG32 通道）；
  - PB-52 单位级地形数值（2026-10-04 拍板纳入·本块落地——断箭 N10/映射 §五.6；
    **推翻 MOVEMENT_PSEUDOCODE_v1.2 MV-B-01 defer 的类级系数口径**，改「单位级
    覆盖、类级缺省回退」；水域仍随 MV-B-02 延期不设列——MV-B-01/MV-B-13 §7 表
    已加 2026-10-04 批注）：数据管线五步全链（ammo_weight 先例）——ground_cards.csv
    +3 列（terrain_speed_override_bp/reverse_speed_override_bp/road_bonus_override_cm，
    空=回退类级）、card_schema UnitCardModel +3 StrictInt 字段（33→36；SCHEMA_VERSION
    1.0→1.1 minor——DATA-01 §2.3-1 加可选字段、§4.3 字段清单同步）、build_cards
    CARDS_COLUMNS +3、card_loader +3 映射、UnitTemplate +3 槽；movement 消费端三处
    ——野=cfg.terrain_speed_bp(cls, tile_bp, unit_bp) 三级回退（瓦片注入>单位级>类级，
    GAP-19 瓦片优先语义保持、pathfind 侧类级读法不变）、路=下限单位级覆盖（契约⑦
    max 形态不动、仅下限常数可覆盖——FOOT 不吃路谓词保持）、倒=movement.reverse_speed_bp
    求值函数（issue_move 门4 资格与未来 §2.3 增量② REVERSE 速度乘区两消费点同读，
    单一求值点防双轨漂移；单位级>0 即数据侧显式开口——FOOT/HORSE 类级恒 0 硬规则
    不另立铁律，由缺省值+数据纪律承载）。数据：现役 10 卡中 SU_T3485（三值全示例
    6500/2500/55——T-34 慢倒车名例 MV-B-01 表/N11 履带路 1.1~1.3×/N12 履带区间
    下沿外推）+SU_TRUCK（单值 5500）两张示例占位（P-120 待定登记+provenance 留痕），
    其余 8 卡留空回退（N11 步兵路=野 → FOOT 卡天然无需覆盖）——全量定标归数值章节；
    gen JSON 已重建（schema 1.1）。tests/test_movement_settings.py +7 锚（覆盖生效/
    空值回退/三级回退 pin/瓦片压单位级/路下限三态+FOOT 恒不吃/倒档求值七组/门4
    单位级开口活行为）+tests/test_card_data_first_batch.py +1 锚（schema 1.1/示例值/
    空值批量回退/P-120+provenance 留痕）。零掷骰（不触任何 PCG32 通道）；
  - PB-53 载具自卫烟幕（2026-10-04 拍板纳入·本块落地——断箭 N32/映射 §五.19；复用
    §D.7 既有 SmokeCmd 命令类+§F6 :1274 cmd_smoke TODO 锚，**不另立新命令类型**；
    与迫击炮烟弹体系并存——原「本作烟幕=迫击炮定量烟弹（D044）」口径扩为两者并存，
    映射 §五.19/拍板清单 PB-53 已留痕）：数据位=ElementTemplate.self_smoke_charges
    （0=无能力，哪些车配属归数据卡配置侧——〔2026-10-07 收口轮配属 SU_TRUCK/SU_T34 各 2，P-121 已更新——原「0 卡」表述过时〕；管线五步：ground_
    elements.csv +列/schema ElementModel +字段 16→17（SCHEMA_VERSION 1.1→1.2 minor、
    SUPPORTED {1:2}——DATA-01 §2.3-1/§4.4 同步）/build_cards ELEMENTS_COLUMNS/
    card_loader 映射/types 槽）；ElementInstance +3 运行时槽（self_smoke_left←
    make_unit 初始化、self_smoke_ready_tick、self_smoke_pop_tick）；BalanceConfig
    烟雾段 +3 占位（self_smoke_default_charges=2 零消费者定标锚——sprint_cooldown_
    ticks 同款先例；self_smoke_cooldown_ticks=300/self_smoke_delay_ticks=20——N32
    仅定性「固有部署延迟」无秒数=未确证#13，全部无据占位待定标；半径/时长复用
    smoke_radius_cm/smoke_ttl_ticks 不另立轨）；cmd_smoke 处理体=发数门→冷却门
    （含在途守卫）→受令耗发+落延迟（system_timers 烟 ttl 环**后**到拍以元素当前
    位置为心 append SmokeZone——当拍满额 ttl/次拍起递减，与 resolve_blast 炮烟同
    生命周期；载具延迟窗内被毁烟幕取消发数不退）；落点=以车为心圆（勘察两案取
    简化案，车尾/侧向偏移无断箭证据 defer）、SmokeCmd.point 本路径不消费（保留给
    武器烟弹路径）、不占武器弹药/补给轨（mark_resupply_if_needed 不调）。
    tests/test_self_smoke.py 13 锚 + test_card_data_first_batch.py +1 锚（schema 1.2/
    全元素默认 0/P-121）。零掷骰（不触任何 PCG32 通道）；
  - 士气状态机（2026-10-04 士气块；GDD-00 D014 四态/D025 阈值制/GDD-05 下篇 B0~B4，
    拍板清单 PB-54）：system_morale 挂 world_tick ⑤后⑥前（B2 步序 suppression(8)→
    morale(9)→logi(10) 字面——当拍 ④交战/⑤弹丸 注入的压制即拍判态）；UnitInstance
    +2 槽 morale/routed_until（B1:100 morale 独立槽口径——B3:137 把 pinned/routed 列
    姿态集作废；压制本体保持元素级 0..100 不动=「能算出来的不存」，B1:99 单位级
    0..150+ 规格口径未采——留痕=tables.py 士气段注释/拍板清单 PB-54）；迁移=存活元素压制聚合 **max** 对三档整数阈值
    确定性判定零掷骰（阈值 40/70/100+重整 300t 出 BalanceConfig 士气段——D025「数值
    待配」全占位）；PINNED=PB-49 可动减速——movement.pinned 判据缝本块激活读真槽
    （TestPinnedAndSprintBreak 休眠锚不动仍绿）；ROUTED=计时失控态——进入拍清玩家令
    （command_queue/move_path/pivot_to）+ issue_move handoff 内部通道装向己方部署区
    锚点 _deploy_anchor（spawn 同款「己方底边中点」拍板口径=近似方向）的溃逃航点，
    routed_until 到拍原地重整回 SUPPRESSED（B4:182 默认=D014 待定①②处置留痕；仍
    ≥rout_th 再溃逃）；失控门族五处=issue_move 门0（含 queue 入队）/cmd_halt/
    cmd_pivot/cmd_sprint/consume_unit_commands；衰减回落降档=既有 ①system_timers 环
    不动。tests/test_morale.py 新锚；
  - 士气效果接线（2026-10-04 士气效果接线块；GDD-00 D014「受压=命中/性能下降、
    钉住=火力大减、溃逃=失控后撤」+D023 命中率式「×士气惩罚」项+GDD-05 下篇
    B4:149 moraleFactor 按态乘区，拍板清单 PB-55——PB-54 状态机的消费端）：
    ①命中乘区 combat.morale_acc_factor_bp（受压×0.7/钉住×0.3 出
    cfg.morale_acc_factor_{sup,pin}_bp——B4:149 字面值低置信占位；断箭参考杠杆
    「瞄准时间×2/×3」未采，二选一取命中 bp 档=D023/B4 双锚侧）接 fire_direct
    acc 链（aim_factor 元素级连续项之后单位级乘区叠乘=双粒度记账非双算）；
    ②溃逃禁射=fire_permitted ⑨ 门（新 AIMING 与 finish_aim 在途复核双拦转
    READY 不耗弹；SUPPRESSED/PINNED 不走许可门=乘区承载非禁射；炮击任务不清但
    逐炮拦（process_fire_mission 统一许可）——PB-54 留待项⑤收口）；③D027:174
    卡级士气阈值三列落地（PB-52 五步先例零新范式：ground_cards.csv +3 列
    morale_{sup,pin,rout}_th（0=回退哨兵，列间独立回退，rout_th>100=永不溃逃
    差异化位）→card_schema 1.2→**1.3** minor·SUPPORTED {1:3}（card_loader 同值
    双写同步）+构建期严格递增交叉校验→build_cards 列注册→card_loader 映射→
    UnitTemplate +3 槽→system_morale 三级回退单点裁决——PB-54 留待项①收口
    【2026-10-04 评审遗留⑤补运行期防御：system_morale 拼出有效阈值后断言严格
    递增、违例抛错——单侧显式+单侧回退的非单调组合构建期不判（0 哨兵跨列），
    违例时 elif 阶梯产生不可达档；现役全空数据恒单调零行为差】；
    现役 10 卡全空=全回退 cfg 40/70/100，数值定标归数值章节）；④受压移动惩罚
    无据不落（D014:97 受压=命中/性能下降无移动项、B2:122「×士气」括注=溃逃
    强制移动——行为锚 test_morale.py test_stable_suppressed_no_slowdown=56
    全速）。tests/test_morale_effects.py 21 锚。零掷骰（不触任何 PCG32 通道）；
  - 士气整局验收（2026-10-04 士气整局验收块——验收留痕收口）：整局 AI 对 AI
    火力自然过阈（tests/test_fullgame_acceptance.py build_suppression_world：
    恒命中压制炮 4 发×55 vs 衰减 1/tick——命中拍序列零 seed 依赖可全手推）
    锚定生命周期四类拍（受压 610/衰减回落 626【两发空窗跌破 40 回 STABLE】/
    钉住 645/溃逃 715→重整 1015→回落 1016）+ 位移轨迹（钉住 10/tick→衰减降档
    受压 20/tick→溃逃全速南逃抵锚停驻→失控期三次 AI 令全拒→重整后恢复受令）
    + 指纹面 +morale/routed_until（full_fingerprint U 段；元素压制值本在 E 段）
    双跑位级一致。**sim 零行为改动**（仅本登记表补注释句；整局未暴露 PB-54/55
    缺陷——观测与规格逐拍吻合）；PB-49 拍板清单行标注判据缝闭环。3 新锚，
    全量 576 绿（追认清理轮 +1 哨兵单测后 577）。零掷骰。
  - PB-57 建筑实体块（2026-10-06；拍板清单 PB-57 行「机制先行、数据后接」）：
    消费侧大半为早前块预置（Building types.py §D.6 :229 / world.buildings 槽 /
    hit_building·collapse_building·resolve_hit 建筑支 ×vs_fort·resolve_blast 伤楼
    快照 combat.py ⑤块 / compute_hit_facing 驻楼 REAR / destroy_element 驻楼清理 /
    移动自动出楼 movement.py GAP-02 / 隐蔽+3 sensing.py AMB-02 合取式）。本块落
    四处真缺口：①apply_map 装配（map_loader）——md.buildings 文件序 → Building
    入 world.buildings：id=1 起文件序（确定性：整局指纹 B 段消费 b.id；元素 id
    单位内 enumerate 同款先例）、hp=CSV building 行（PB-58 数据位占位）、
    garrison_slots=cfg.building_garrison_slots 出表占位（tables.py——DATA-02 无列
    [冻结]/§D.0 无常数/GDD 无容量表述三缺；勘察 decisionPoint#1 常数案采、
    footprint 派生式无文档锚未采；占位值 1 无据待数值章节定标；当前零消费者
    ——cmd_garrison 未落地不冒充【2026-10-06 驻楼命令块更新：cmd_garrison ② 容量
    门已消费本常数，见下方驻楼命令块条目】）；建筑不入瓦片层=pathfind/sensing 零扰动。
    ②map_loader 字符串门补齐（PB-58 评审遗留）：map_key/building_key 拒空串/
    公式前缀(=,+,-,@)/含 ';'/':'——build_map._to_str 同款（构建期拦截可被手改
    gen JSON 绕过，加载期消费 building_key 前收口——DATA-02 §2 :56 规格的加载期
    复检）。③finish_aim 失的守卫 Building 支（§F4 :768-769，v1.5 M4/G06/G29
    补支——PB-53 轮评审预告复核项）：活 Building（hp>0）过守卫续走
    fire_permitted+fire_direct（纯射手侧九门无目标参天然兼容；fire_direct 建筑
    支 HE 默认档/pen_bonus=0 与 R-01 标记豁免既有 :1562-1566/:1589-1591）；
    hp<=0 楼塌失的转 READY 不耗弹——原码无 .unit 恒判失的、Building 支经
    finish_aim 不可达（docstring 自认+登记表在案），本块与「目标已除名」（B9
    元素除名）判据分离。④入口 AttackCmd 分派仍 TODO（PB-56 批① §F4 :848——含
    vs_fort>1000 建筑资格门）：直射拆楼链玩家令可达性待批① 闭环（时序依赖非
    本块缺陷；测试经 begin_aim 直挂 ws.target 验证链体）〔**已闭环——2026-10-06
    PB-56 批① cmd_attack 落地，见下方作战链命令块条目**〕。测试
    test_map_pipeline.py（装配 5 锚/字符串门）+test_ground_combat.py（守卫放行/
    塌楼失的/弹丸到达掉血）。零掷骰（装配/守卫纯整数确定性，不触 PCG32 通道）。
  - PB-57 驻楼命令块（2026-10-06；§F6 :1248-1255 cmd_garrison/cmd_un_garrison +
    D003 建筑进驻——拍板清单 PB-57 行「机制先行、数据后接」的命令侧收口）：
    ①处理体+分派支（GarrisonCmd/UnGarrisonCmd 由丢弃改真调用——本块前分派支
    TODO 锚定在案）：cmd_garrison 门序照伪代码字面两门——canGarrison 模板位
    ① + garrison_slots<=LEN(garrisoned) ②（:1249 按单位整体判一次后全量
    append——多元素单位可超容=伪代码缺口照字面落地并登记，勘察 decisionPoint#2
    字面忠实档）；+③塌楼建筑 hp<=0 REJECT（伪代码 :1248 未列——§F4 :768-771
    失的守卫同款判据的进驻侧完整性收口：塌楼已出 world.buildings，驻入产生
    永不可达引用且白吃隐蔽加成；留痕可推翻）。无距离门：伪代码 :1248-1250 仅
    兵种+容量两门，ask 序言「距离门」与伪代码不符——按伪代码口径不补门
    （全场遥控驻楼可达、命令即挂引用无贴近校验），留痕待发起人确认是否补门
    （补门=无锚造门）。接受=逐元素双向引用写入（:1250 字面；不写 e.pos——
    伪代码无此写点，驻楼射击照常直射弹丸起点不变）；换楼驻入旧楼 garrisoned
    条目同步移除（双向不变式 e.garrison_in=b ⇔ e∈b.garrisoned——伪代码直覆盖
    未及，登记）。cmd_un_garrison 无资格门（:1253 字面——未驻楼=无操作）：
    逐元素清双向引用+e.pos=楼旁落位（偏移未定标取楼锚同点位——destroy_element
    车毁旁落位同款登记；不写 unit.pos——伪代码只写 e.pos）；garrisoned 移除
    按身份 is 过滤（防御性改写——2026-10-06 评审实验复核：伪代码字面 .remove(e)
    在世界 id 纪律下行为正确（元素 id 首字段失配+list.remove 身份短路优先），
    ElementInstance 无 eq=False 手动构造重复 id 仍可触雷故保留防御式——
    combat.destroy_element ⑤块「按身份除名」同款）。②效果面既有接线复核（本块零新效果代码）：
    隐蔽+3=sensing.effective_stealth_x10 AMB-02 合取式（CAN_GARRISON 位 AND
    任一元素驻楼→+garrison_stealth_add_x10=30）；命中面=compute_hit_facing
    驻楼 REAR（覆盖序首位）；楼内射击无修正=fire_permitted 九门无驻楼门
    （伪代码无此门）；楼内可被直射选定=select_target 无驻楼排除（伪代码无
    此门）；楼内可受移动令=issue_move 无驻楼门+GAP-02 移动自动出楼
    （movement.py 出楼清理本块改按身份移除——防御性改写非行为变更：
    2026-10-06 评审实验复核字面 .remove(e) 在 id 纪律下正确，ElementInstance
    无 eq=False 保留防御式）。③双向清理三向验证：楼塌（collapse_building 既有）/
    元素毁（destroy_element 既有）/移动出楼（movement 既有）——挂载即出楼
    随 PB-56 批② MountCmd（伪代码 :1150，时序依赖非本块缺陷）。④数据侧
    脱节登记：CAN_GARRISON 位与 card_schema.py:79 令牌已备但 ground_cards.csv
    现役 10 卡全无置位——cmd_garrison ① 门对现役全卡恒 REJECT；GDD-02 v1.9:50
    侦察班「可进驻建筑」卡面承诺无数据承载，补位随数值章节/数据侧（机制先行
    纯合成模板测试——勘察 decisionPoint#3）。测试 tests/test_garrison.py
    25 锚（门逐项/无距离门锚/容量行为/换楼完整性/分派链/隐蔽合取式/
    REAR/楼内射击照常/被直射选定/出楼落位/双向清理三向/示范楼 cfg 槽消费/
    零掷骰）。零掷骰（命令处理纯整数确定性，不触任何 PCG32 通道）。
  - PB-57 塌楼验收块（2026-10-06 收口；拍板清单 PB-57 行批三）：**sim 零行为
    改动**——塌楼链体（hit_building 扣血→hp<=0 转 collapse_building：逐驻军
    清引用→cfg.building_collapse_dmg>0 才 apply_damage→garrisoned.clear→
    world.buildings 按身份除名）随 ⑤块/combat.py 既有，本块为带建筑集成验收：
    ①驻军处置分级锚（tests/test_garrison.py TestCollapseCasualties +3）：恰死档
    （hp<=0→destroy_element 完整连带→全灭 unregister+alive=False→world_tick
    :1439 尾部尸体清扫出 world.units——引用三向清理之尸体清扫侧）/同楼双班
    混合处置（快照迭代安全：班0 恰死、班1 带伤进 await_resupply 医疗链——
    D012 口径楼塌伤步兵由医疗链承接（引注勘正 2026-10-06：带伤→医疗=R-18/D012/§D.0 :74，D016 系车辆维修边界）；逐驻军先清 garrison_in 再结算 ⇒
    死亡路径 destroy_element 驻楼清理分支见 None 跳过、clear() 兜底）/默认
    cfg 档（building_collapse_dmg=0=塌楼无伤害——§D.0 :76 数值章节定标前既定
    缺省，引用照清驻军无伤）。驻军处置=伪代码 §F5 :537-541 口径：无「弹出
    落位」写点（驻楼/塌楼均不写 e.pos，元素保持原位）、无额外「受罚」常数
    （伤害外无士气/压制惩罚写点）——如实留痕。②真实锚整链验收
    （tests/test_fullgame_acceptance.py TestGarrisonCollapseFullGame +3）：
    示范图 5 锚（apply_map 真实装配 B1=V1_HOUSE_A (93750,43750)/hp=100）×
    GarrisonCmd 命令链驻楼（隐蔽 50→80=+3.0 级）× 恒命中拆楼炮（acc 10000
    ——PIN_W 先例零 seed 依赖）× finish_aim→fire_direct 建筑支 HE 档→
    system_projectiles→resolve_hit ×vs_fort→hit_building 扣血→楼塌驻军分级
    处置全链手推定锚（aim5+reload10=15 拍周期、发射拍 6/21/36/51/66、命中拍
    7/22/37/52/67、hp 100→80→60→40→20→0 塌；通道纪律={HIT,SCATTER}——
    建筑支无暴击掷、塌楼链零掷骰）；全灭尸体清扫整链锚；同 seed 双 world
    逐 tick full_fingerprint 位级一致（驻楼 gref/楼 B 段逐发掉血与出表/
    八通道 state 同步推进均在指纹面内，跑过塌楼拍+稳态 5 拍）。③集成暴露并
    修复前块缺陷一处（如实报告）：full_fingerprint（⑧块成文）W 段 ws.target/
    P 段 hit_target 引用走 elem_ref 需 .unit——Building 目标无 .unit 直崩
    AttributeError；⑧块时 world.buildings 恒空无 Building 瞄准/弹丸为盲区，
    本块驻楼-拆楼整链首次产生在飞 Building 弹丸而暴露——增 tgt_ref 三分支
    （航空器→楼 B%d[与 E 段 gref 同编号域]→元素），既有元素/航空器引用输出
    位级不变（全量 687 绿护栏）。④AttackCmd 分派支仍 TODO（PB-56 批① §F4
    :848 含 vs_fort>1000 建筑资格门）——玩家令直射拆楼入口待批① 闭环，
    本块 begin_aim 直挂验证链体（TestFinishAimBuildingGuard 同款留痕口径）
    〔**已闭环——2026-10-06 PB-56 批① cmd_attack 落地，见下方作战链命令块条目**〕。
    测试 +6 锚（test_garrison 3+fullgame 3），全量 687 绿。零掷骰（塌楼伤害
    =cfg.building_collapse_dmg 固定整数——§D.0 :76 无掷骰要求，零掷骰档成立、
    未新开 PCG32 通道）。
  - PB-56 批① 作战链命令块·AttackCmd（2026-10-06；§F4 :848-872 cmd_attack
    处理体+AttackCmd 分派支由丢弃改真调用——批① 首块，SetMode/ToggleAmbush/
    SetStance 三命令随各自块落地）：①武器选择口径=**循环案默认裁决（可推翻）**
    ——§F4 :848 签名带单 ws 形参与 §D.7 :265 命令类 {element,target} 无武器字段
    的规格空洞（勘察 decisionPoint#1）：遍历 e.weapon_states 逐武器过①-⑪ 全门序、
    过门者各自 begin_aim（ground_direct :736-747 同构；多武器元素全上、非攻坚
    武器对建筑被 ① 自然滤除；test_economy_phase drain 用例 target=None×无武器
    元素=循环体零执行自然无操作存活——单主武器 weapon_states[0] 案该用例
    IndexError 不采）。②门序照伪代码字面逐条（①Building×vs_fort<=1000 建筑资格
    门/②GROUND 位/③⑲A 狙击×MECH/④M5/B01 发现门/⑤犀牛门 Building 豁免/
    ⑥M10/G23 车载班/⑦READY+弹药/⑧fire_permitted 九门/⑨max_range——**无
    min_range 门**：:868 字面仅上限，宽于 select_target 的 min≤d≤max，照字面
    落地留痕/⑩R-09 射界外 rotate_step+RETURN——:870 实参序按语义换
    approach_deg_of(e.pos,target.pos)（geom.py 登记表笔误勘正、ground_direct
    :744 修正序先例），循环形下 RETURN=函数退出=每令至多转一步（逐武器各转
    将倍速转向不采）/⑪begin_aim）。无 mode 门（伪代码未列——INDIRECT 模式元素
    可被手动指火直射，fire_permitted ⑥ 仅拦 TOW/CARGO/TRANSPORT，手动入口照
    字面宽于自动链留痕）；目标存活门亦未列——死亡目标由 finish_aim 失的守卫
    （B9/hp<=0）收口。③后继链既有接线复核（本块零后继链改动）：begin_aim→
    system_timers ① 递减→system_combat ① finish_aim（PB-57 建筑支守卫：活楼
    放行/fire_permitted 出口复核）→fire_direct（建筑支 HE 默认档/pen_bonus=0/
    R-01 豁免）→system_projectiles ⑤→resolve_hit ×vs_fort→hit_building→
    collapse_building——玩家令直射拆楼链闭环（PB-57 建筑实体块④/塌楼验收块④
    两处留待项就此收口）。④数据侧脱节照登：ground_weapons.csv vs_fort 列现役
    全缺省 1000 → ① 门对现役武器恒 REJECT（攻坚数值随数值章节，测试用合成
    SIEGE_CMD_W vs_fort=2000）〔**2026-10-07 数据定标块：脱节收口**——四攻坚
    武器口径递进配值（D-5T 5000/ZiS-3 直+曲 4000/PaK40 3000，P-122），① 门对
    真卡攻坚武器放行、真卡端到端锚落地（test_data_calibration_v1）；步兵武器
    含铁拳维持 1000=无攻坚资格〕。⑤整局影响实证（勘察 decisionPoint#3 担忧面）：
    AttackCmd 转活后既有整局锚**逐位不变无需重锚**——探针复核 seed 42/3/11
    全部命令零武器状态迁移（lean42 12 令/rich3 22 令/rich11 14 令）；机理=
    consume_commands 位于 world_tick 首、① RELOADING→READY 迁移后 ④ 自动
    交战链同拍重新占位，consume 时点武器在有效目标存在期间恒非 READY，目标对
    超程/未发现亦被 ⑨/④ 拒——test_fullgame_acceptance 17/17 原锚全绿（模块
    docstring 机理注+HeadlessAI 现状注释已更新）；炮击任务链转活（GUN_TPL
    mode_set 扩位+AI 补发 SetModeCmd）仍待 SetModeCmd 块（非本块范围）。
    测试 test_ground_combat.py TestCmdAttack 19 锚（门序逐项含边界/多武器滤除/
    射界内外/RETURN 单步/建筑拆楼全链手推节拍 t3 命中 t26 塌/元素目标链回归/
    分派链/零掷骰双证/target=None 无武器存活），全量 709 绿（690+19）。
    零掷骰（门序+begin_aim+rotate_step 纯整数，不触任何 PCG32 通道——发射段
    掷骰属 fire_direct 既有 HIT/SCATTER 通道纪律，无新用途）。
  - PB-56 批① 作战链命令块·余三命令 SetMode/ToggleAmbush/SetStance（2026-10-06，
    批① 就此收口）：①SetModeCmd→cmd_set_element_mode（§F6 :1193-1213 写点序
    ①-⑦ 照伪代码字面：mode_set 资格门→TOW 解挂 release_tow_if_involved（GAP-24
    元素级，因由 DESTROYED 无行为差）→CARGO 卸货〔**规格字段勘误**：:1196-1197
    写 e.supply_rounds/e.supply_medical——两字段代码不存在，2026-10-03 弹药/医疗
    一池按重量拍板后唯一槽=supply_weight_g，按 destroy_element 先例换写清零；
    None=未分配条件槽不触碰（方案12）〕→TRANSPORT 逐班卸客（班元素 mounted_in
    双向清+旁落位同点位——偏移未定标登记，destroy_element/出楼落位同款）→
    m≠TRANSPORT 清 mount_requests 挂起条目（I-19，按身份过滤）→写 e.mode→
    M21/A24 半清除（e.mode 先行赋值故判据自然排除刚切元素——仅本单位已无任何
    INDIRECT 元素才清 fire_mission，任务体销毁校射随之失效）。②cmd_fire_mission
    双门就此解锁：元素初始 mode=DIRECT（types.py）→ 本命令=炮击任务令唯一解锁
    钥匙（⑧块「任务令恒 REJECT」留痕就此闭环）。③ToggleAmbushCmd→
    cmd_toggle_ambush（§F4 :874-883：canAmbush 资格门→手动退出 active=FALSE+
    shot_bonus=TRUE（携首击加成）→ELIF 静止开启；「静止 AND move_path==[]」两
    谓词同源折叠为 not moving()〔IMPL :27 成文〕；移动中受令=过门无操作留痕）
    ——R-12 整链（原 ambush_active 全文无 TRUE 写点不可达）就此可达，消费端
    sensing ×20000/观察者 r//2/fire_direct 首击 ×13000+打完清/移动自动退出
    （movement.py:215-218 含 M19）全部既有接线零新效果代码；开火不自动退出
    （R-12 已确认）。④数据侧脱节照登：CAN_AMBUSH 现役 0 卡置位（⑮A 拍板 4 卡
    均不在 ground_cards.csv 现役 10 卡集〔实测〕→ 资格门对现役恒 REJECT——
    CAN_GARRISON 追认补卡先例在，补位随数值章节/数据侧，测试用合成模板）。
    ⑤SetStanceCmd→cmd_set_stance=**最小写点案**（勘察处置建议 a 默认裁决可推翻：
    v1.7 仅字段定义无处理体、GDD 侧无姿态细则锚〔GDD-00/GDD-02 v1.9 grep 无
    条目；GDD-05 B3:137 宽姿态集口径已作废 types.py:93 留痕〕→ 单写点
    unit.stance=stance+Stance 枚举合法性校验〔枚举外值 REJECT〕，无资格门——
    全部行为门已在消费侧 fire_permitted ②（HOLD_FIRE 禁新 AIMING+finish_aim
    出口复核）、ROUTED 本就禁射⑨切姿态无行为危害；无锚造门不采补门案 b。
    对空豁免=对空链不调 fire_permitted 天然豁免〔§F4 :695「不约束对空」〕；
    GDD 侧回写落点（何种文档承载开火纪律）随 GDD 版本执行留痕。先例=SprintCmd
    行内注释即写点/cmd_set_airdrop_beacon v1.4 补最小体。⑥整局验收扩展
    （勘察 decisionPoint#3 整局面单列验收块口径——既有场景锚逐位不动，转活
    链以新场景承载）：HeadlessAI 增 keyword artillery/send_attack（缺省=既有
    行为逐位不变——PB-58 块③ anchors/move_mode 同款先例）+ GUN_TPL mode_set
    扩 DIRECT|INDIRECT（SU_ZIS3 现役唯一双位卡先例；无 SetModeCmd 时任务令
    仍被双门第二门 REJECT→既有 lean/rich/map 场景锚位级不变）；新场景三组——
    炮击任务整链（AI SetMode+FireMission→任务建立→process_fire_mission 逐拍
    推进→R-16 校射按批累积→耗尽销毁方案10→EMPTY/待补给，通道=SCATTER only）、
    攻击令主动交战×自动链对照（min_range 内自动链结构性不接战〔select_target
    min≤d≤max〕vs cmd_attack 无 min 门〔:868 字面〕→手动令唯一交战入口+
    无攻击令对照组零弹丸）、三命令合链指纹双跑（stance/ambush 写点入 U 段
    指纹面）。测试 test_ground_combat.py TestCmdSetMode/TestCmdToggleAmbush/
    TestCmdSetStance + test_fullgame_acceptance.py TestArtilleryMissionFullGame/
    TestManualEngageFullGame/TestCommandChainFullGame；零掷骰（三处理体全纯整数
    不触 PCG32 通道——发射段掷骰属既有通道纪律，无新用途、未新开通道）。
  - PB-56 批② 机动链命令块·上下车（2026-10-06；§F6 :1137-1168 cmd_mount+
    :1131-1136 cmd_dismount 处理体+MountCmd/DismountCmd 分派支由丢弃改真调用；
    消费端 seat_usage/pending_mount_count/mount_requests_step ⑦块既有，本块零
    消费端改动）：①cmd_mount 门序照伪代码字面①-⑪（㉑A 班元素粒度逐班 CONTINUE
    ——部分成功为逐班语义、ok==0 整体 REJECT；③ 挂载即出楼无条件先行=伪代码
    次序字面：即便该班后续被 ⑥-⑨ 跳过出楼也已发生；⑩ 惰性建表置于 ⑪ 前=过 ⑨
    即建、⑪ 不中亦已建空表）。**规格字段勘误一处**：:1160 carrier.template.
    mode_set——ElementTemplate 无 mode_set 槽（照写即 AttributeError），按
    cmd_set_element_mode ①/cmd_tow :1239 先例换写 carrier.unit.template.mode_set
    （批① supply_rounds→supply_weight_g 换写同类别）。**「旁」定标=同点位判
    （勘察 decisionPoint#2 推荐案 i 采纳，可推翻拍板项）**：dist_cm(s.unit.pos,
    carrier.unit.pos)==0——「旁」全仓无距离常数（tables.py 各 radius 均有 GDD 锚，
    GDD-02 v1.9:111 仅「在静止车辆处」），点单位可叠放（PB-16）+spawn 锚点全员
    同点→零新常数；跨卡场景步兵须先走到载具单位锚点才可上（vs 全场遥控驻楼
    先例的无门案）——玩法可达性差异留痕待发起人裁；「静止」=not moving() 单位
    级粒度（元素无移动状态槽）。**字面缺口照字面落地并登记（可推翻）**：已挂载
    班无再挂防护（去重仅查挂起请求 :1147——已 mounted_in 班可再获新请求，窗口
    内座位双记、seat_usage 事后自纠，低危）。②cmd_dismount 极简：WHERE
    mounted_in≠NULL AND SQUAD（VEHICLE 元素挂载引用不清——㉑A 口径）；旁落位
    同点位（偏移未定标——destroy_element 车毁/cmd_un_garrison 出楼/
    cmd_set_element_mode ④ 卸客三处同款登记先例）；跨卡 cargo_units 移除**按
    身份过滤改写**（:1136 字面 .remove(squad_unit)——防御性改写：cargo_units 装载
    UnitInstance（id 首字段短路等值），原注「ElementInstance 递归风险」类型标注
    失准已勘正（批②评审#2）——movement.py GAP-02/PB-57 驻楼块/
    combat.destroy_element「按身份除名」同款口径）；不写 squad_unit.pos（伪代码
    只写 e.pos）。③跨链联动复核（零新效果代码）：挂载即出楼↔GAP-02 移动自动
    出楼双向齐（PB-57 驻楼块③「挂载即出楼随批② MountCmd」留待项就此闭环）；
    Mount×SetMode（载具 ⑧ 三模式门×SetMode ⑤ 清挂起请求批① 已落）；Mount×
    spawn 预挂（v1.3 审查#4：squads[i]↔carriers[i] 1:1 即时挂 vs cmd_mount 200
    拍倒计时——口径差异照字面[预挂=开局形态非命令链]一致无冲突；下车后再上车
    经 ⑤ 逐班最少挂载重选=1:1 形态可重建，㉑A 主诺 :1139-1143「开局形态一旦
    下车即劣化」就此闭环）。④整局影响：lean/rich/map 场景 AI 不发 Mount/
    Dismount（批① AttackCmd 同机理）——既有整局锚逐位不变；test_economy_phase
    drain 冒烟用例 MountCmd carrier_unit=None 照 :1153 字面直崩 AttributeError
    ——随批改传真实单位 u（seats=0 → ⑥ CONTINUE → REJECT，无冒充副作用）。
    测试 tests/test_supply_mount.py TestCmdMount 14 锚（分派链全链 200 拍/门
    ①②③⑦⑧⑨⑩⑪ 逐项/③ 无条件先行/⑧ 勘误后位门+无位载具对照/㉑A 3班→3车
    1:1/部分成功/已挂再挂字面锚）+TestCmdDismount 6 锚（同卡/跨卡按身份一次
    移除/VEHICLE WHERE 谓词/无操作/分派链/全链闭环），全量 756 绿（736+20）。
    零掷骰（门序+指针计数纯整数，不触任何 PCG32 通道）。
  - PB-56 批② 机动链命令块·拖曳展开（2026-10-06；§F6 :1228-1245 cmd_tow/
    cmd_untow + :1072-1118 cmd_deploy/cmd_pack_or_move 四处理体+分派支由丢弃
    改真调用，**批② 六命令就此收口**；start_tow §F2 :494-516 随块落 combat.py
    ——TowPair 建立唯一入口，解挂侧 stop_tow/release_tow_if_involved ⑤块既有）：
    ①start_tow 门序/写点照伪代码字面：C1 双态守卫+空列表 FALSE→GAP-10 函数级
    同队硬门（命令门之外兜底）→吨位贪心（tow_tonnage 降序**稳定排序**并列取
    原序——sorted(reverse=True) 稳定序承载，45t=2×30t 并拖可表达，不足 FALSE）
    →TowPair 入表/牵引 TOWING/被拖 TOWED/redeploy_needed=TRUE（C3）/清
    towed.unit.fire_mission（方案10 单位级整清——与 SetModeCmd ⑦ M21 半清除
    粒度不同构照字面）；C5：不写 unit.deploy_state/deploy_timer。**规格字段
    勘误一处**：:500-505/:515 写 t.template.tow_tonnage/own_weight_tons——两槽
    在 UnitTemplate（types.py），ElementTemplate 无此槽（照写即 AttributeError），
    按批① supply_rounds→supply_weight_g/批② 上车块 mode_set 换写先例改
    t.unit.template.*。②cmd_tow 门序照伪代码字面①-③（GAP-10 同队门/合法被拖
    对象门〔GUN OR MECH×TOW 位——「卡车拖卡车」own 0 吨位恒满足退化合法照字面
    登记可推翻〕/逐 tower 三门〔C1 双态、D065 互斥须先 SetModeCmd(TOW)、
    牵引资格=TOW 位〕）→start_tow 失败静默（:1241 字面，返回值透传供测试）。
    ③cmd_untow 极简：涉本元素拖曳对（按身份判——release_tow_if_involved
    GAP-24 同构）逐一 stop_tow(VOLUNTARY)；无资格门（伪代码无 REJECT）；
    stop_tow 不清 redeploy_needed（C3——解挂后须 cmd_deploy 重展开=重展开链
    起点）。④cmd_deploy 写点照 v1.6 终审修复 1b 元素粒度（授权链
    dwfrun-23ebdd22 FIX5 在库可核，可推翻）：MOBILE→DEPLOYING+timer=deploy_
    time_ticks（分支内写入——M18/A20 重复下达不重置/PACKING 期不覆盖）；
    ELIF DEPLOYED×ANY(redeploy_needed WHERE towed≠TOWED)（GAP-09 留守门不
    空走）→重走 300 拍（v1.5 终审修 1a 时长承载——AMB-11 重展开窗口全连禁射
    已拍板接受）；清旗循环排除 TOWED（TOWING 牵引元素正常清，其禁射由
    fire_permitted ⑤ 另拦）。〔条件槽〕代码 redeploy_needed 恒有槽（types.py
    默认 False）——「仅 GUN/可被拖 MECH 分配」以 towed≠TOWED 谓词承载（写
    False→False 无害）。⑤cmd_pack_or_move 两 IF 字面（DEPLOYED→PACKING+
    pack_time_ticks〔:1117 pack_time 换名写——types.py 先例〕/DEPLOYING→
    MOBILE+0 作废/PACKING 期两 IF 均不中无操作）。**MoveCmd 触发面已接线
    （2026-10-07 发起人拍板=采 IMPL 字面，真两难闭账——原留痕见登记表 PB-56
    批② 留待项① 2026-10-06 复核段）**：落点=movement.issue_move 效果点
    （DEPLOYING×外部=作废放行/DEPLOYED×两通道=转收装再走/PACKING 拒维持），
    两锚已随拍板翻转（test_move_commands/test_tow_deploy）。⑥跨链联动
    复核（零新效果代码）：Tow×FireMission（:515 单位级整清）→Tow×Movement
    （锁速 tow_speed_tier 双态 movement.py 既有+GAP-14 随动偏移 300 被拖 pos
    唯一写点+全被拖单位早退）→Tow×SetMode（④ 切出 TOW 解挂批① 已落）→
    Tow×Repair（修满 stop_tow REPAIRED ⑥块既有）→Deploy×FireMission（③
    needs_deployed=DEPLOYED×非 redeploy 门 fire_permitted/process_fire_
    mission 既有）→Deploy×Movement（门1 双侧既有——本批经命令链复合锚定）；
    G17 旁路闭合整链（拖走→旗置位禁射→解挂旗保持→重展开 300 拍→DEPLOYED
    恢复开火）单测+整局面双锚。⑦整局面扩展（HeadlessAI 增 keyword
    motorized/tractor——缺省=既有行为逐位不变，anchors/move_mode 先例）：
    车载机动画像（真购卡→spawn R-07 预挂→车载机动→下车→再上车 200 拍双班
    重挂=㉑A 形态重建整局面复证，MIXED 卡）+拖曳展开画像（SetMode(TOW)→
    TowCmd→锁速机动随动→Untow 被拖侧→DeployCmd 首展分支（拖曳不写 deploy_state，自始 MOBILE——批②评审#3 勘正：原注「ELIF 重展开」分支名失实）300 拍 fire
    恢复→PackCmd 收装 300 拍→MOBILE，新合成 TRACTOR_FG_TPL/AT_GUN_FG_TPL
    ——现役 fullgame 模板集无 TOW 位卡，GUN_TPL 扩位先例仿）；两场景同
    seed 双 world 逐 tick full_fingerprint 位级一致+零掷骰。test_economy_
    phase drain 冒烟随批更新：DeployCmd+PackCmd FIFO 净抵消（MOBILE/0→
    DEPLOYING/0→MOBILE/0 state0 存活）、TowCmd SQUAD 元素被 ② 门 REJECT、
    直调用例 unit=None 占位改真实 DEPLOYING 态单位（StopCmd 先例）。测试
    tests/test_tow_deploy.py 44 锚（start_tow 函数级门序/贪心降序并列原序/
    恰满足边界/不足静默/四写点/fire_mission 清；cmd_tow 门①②③逐项/退化
    合法/重挂/分派链；cmd_untow 双侧入口/无涉无操作/C3 旗保持禁射；cmd_deploy
    计时/ELIF/GAP-09 留守/M18/PACKING 不覆盖/清旗排除；cmd_pack 两 IF/整环/
    门1 互锁+行为洞锚；跨链 G17 整链/留守门整锚/锁速随动/SetMode 解挂；真卡
    SU_TRUCK×SU_ZIS3/GER_PAK40 链+真卡 300 拍；双跑位级一致零掷骰）+
    test_fullgame_acceptance.py TestMotorizedFullGame/TestTowDeployFullGame
    各 2 锚，全量 804 绿（756+48）。零掷骰（四处理体+start_tow 稳定排序全
    纯整数，不触任何 PCG32 通道）。
  - PB-56 批③ 支援链命令块·SetSniperCover/BuySupplies（2026-10-06；§F6
    :1258-1267 cmd_set_sniper_cover+:1215-1225 buy_supplies 两处理体+分派支
    由丢弃改真调用。批③ Garrison/UnGarrison 随 PB-57 已落转回归验证不重复
    落地——命令层端到端锚既有在案：test_garrison.py 分派链三锚
    〔test_garrison_cmd_via_command_queue/test_garrison_cmd_rejected_still_
    consumed/test_un_garrison_cmd_via_command_queue〕+零掷骰锚，全量绿即回归
    基线；批③ Formation 族不在本块〔勘察 decisionPoints「落地面切法」待裁，
    MOVEMENT 余量条目在册〕；SetAirdropBeaconCmd 仍丢弃=§D.7 22 类总收口后
    唯一缺口）：
    ①cmd_set_sniper_cover 门序照伪代码字面四门（CAN_SNIPER_COVER 资格/⑳A
    同队/目标存活〔alive+elements 两支〕/非自身——④ 恒等判 is：UnitInstance
    dataclass eq 按 id 首字段短路、id 唯一 ⇒ 与伪代码 == 等价）+1:1 替换语义
    （遍历 cover_by_target 按插入序把该狙击从旧 protectors 移除，新令顶掉旧
    目标）。**空键删除收口（可推翻留痕）**：伪代码 :1265-1266 未删空键——
    消费=键存在性布尔（combat.py resolve_sniper_hit covered 判 tgt_unit.id
    in cover_by_target），留洞则换目标后旧目标零掩护者仍恒享减半保护；IMPL
    :492 unregister 侧 v1.3 已修同款洞（「空键不删→掩护者全灭后目标恒判
    covered〔终审遗留〕」）——同款收口〔空键 del〕，移除按身份过滤改写
    〔is 过滤——unregister/驻楼按身份除名同款，伪代码 .remove 字段相等有
    跨单位误删风险〕+快照 list(keys()) 迭代〔迭代期删键纪律〕。末写
    setdefault(target_unit.id).append(sniper)：键=unit.id（v1.7 键型 unit 的
    已登记实现适配——旁表注释/消费端 combat.py 同口径，与 ask 序言「PB-45」
    编号出处待发起人指认〔拍板清单 PB-45 行实为 indirect_role 无弹药过滤，
    键口径事实以代码登记为准核验〕）；值=掩护者 unit 对象列表配 identity
    清理；同目标多狙击并存〔§D.8#5：消费存在性布尔不叠加〕；重挂同目标=
    移除后重插净状态同（插入序移尾=「按插入序 map」字面）。消费端零新效果
    代码核实：resolve_sniper_hit covered×sniper_cover_mult_bp=5000 乘区
    〔combat.py:457-459/tables.py，§D.0 :69〕+unregister 双向清理〔combat.py:
    257-263〕+test_ground_combat 掩护锚既有〔手写旁表 :1982/:2096/:2388-
    2399〕——本块仅补旁表唯一写者，R-02 掩护链写侧就此全通。
    ②buy_supplies 门序照伪代码字面五门（hasSupply 补给载具门/仅 CARGO 门
    〔v1.3 审查#8〕/弹药舱位/医疗舱位/D012 混装载重闸——M1 勘误 truck_
    element.template 直达无换写需求）+**负值输入纪律防御门（可推翻）**：
    rounds/medical<0 REJECT——伪代码未列，门序③④⑤为 > 比较对负数恒放行、
    直写将产生负池〔system_supply weight<=0 早退=惰性腐化〕，cmd_set_
    element_mode 裸 int 拒令〔批①评审#3「显式拒令可测」〕同款口径。
    **规格三处脱节的处置（勘察 discrepancies「buy_supplies 规格三处脱节」/
    decisionPoints「负载与换算锚」案 c）**：(i) 写点 :1225 supply_rounds/
    supply_medical 字段不存在——2026-10-03 拍板「弹药/医疗一池按重量计」后
    唯一槽=ElementInstance.supply_weight_g〔types.py:362；该拍板在库留痕=
    types.py/tick.py system_supply docstring/combat.py destroy_element 三处，
    ask 序言「PB-54 行」编号与拍板清单 PB-54〔士气状态机〕不符待发起人指认，
    决策事实以代码登记为准〕，按批① cmd_set_element_mode ③ 换写先例改
    supply_weight_g=weight **直赋值**（伪代码对两槽直赋值的等价换写=换装
    而非补装；条件槽首次写入即分配——cargo_units 惰性分配 mount_requests_
    step 同款，方案12）；(ii) cfg.supply_round_weight/med_weight_per_unit
    不存在——§D.0 :73-74 出表入 BalanceConfig〔tables.py 后勤段〕：
    med_weight_per_unit_g=5（D.0 :73 定值，D065 混装载重核算）、supply_
    round_weight_g=1 **占位**〔D.0 :74 标「待定」——D012 满额互算
    cargo_weight_max 600÷cargo_rounds_max 600 且与 per-weapon ammo_weight
    数据占位 1g〔types.py:238〕同值，数值章节定标〕；(iii) 门①「有
    hasSupply 槽」实现判据=UnitFlag.HAS_SUPPLY〔types.py:190，airdrop_
    crate_template GAP-21「漏配则物资槽不分配」同一位〕——supply_weight_g
    None 判不可用〔make_unit 未承载 §D.5#16/17 分配、BuySupplies 本身即
    首写者，None 判自锁门①〕；现役 SU_TRUCK flags 空（ground_cards.csv
    第 8 行）→ 现役恒 REJECT，数据侧补位另裁〔勘察 decisionPoints「数据侧
    承载」待发起人裁：SU_TRUCK 补 HAS_SUPPLY 玩法链现役可达 vs 机制先行
    合成卡数据冻结——CAN_GARRISON 追认先例在；狙击组卡+CAN_SNIPER_COVER
    现役全缺同一口径可一并裁〕。
    ③消费端零新效果代码核实：system_supply ⑥ CARGO 元素×await_resupply
    同队半径补弹/医疗〔tick.py 既有〕+cmd_set_element_mode ③ 切出 CARGO
    卸货清零〔批① 既有〕+destroy_element 车毁清零〔combat.py 既有〕——
    SetMode(CARGO)〔批①〕→BuySupplies〔本块〕→system_supply 装货整链
    首次全通〔R-18 消费侧 test_supply_mount 既有锚不扰〕。
    ④整局影响：现役模板集无 CAN_SNIPER_COVER/HAS_SUPPLY 置位卡（python
    csv 全卡核验）——lean/rich/map 场景 AI 不发此二令（无资格门恒
    REJECT=与丢弃位级同效），既有整局锚逐位不变无需重锚；test_economy_
    phase drain 冒烟：SetSniperCoverCmd(u,u) 被 ① 资格门〔兼 ④ 非自身〕
    REJECT、BuySuppliesCmd(LINE_TPL SQUAD 元素) 被 ① hasSupply 门 REJECT
    ——22 命令清空/零掷骰/state0 断言无扰，冒烟注释随批更新（批①② 先例）。
    测试 tests/test_support_commands.py +32 锚（cmd_set_sniper_cover：门序
    逐项含 ③ 两支/受理写点〔键=unit.id 值=unit 列表〕/换目标旧键清/重挂
    同目标/双狙击并存/部分替换留他护者/与 unregister 合成/分派链含拒令
    仍消费/零掷骰/消费端 covered 乘区经真命令驱动〔同 seed 双世界
    cover_mult=0 分离锚——test_cover_table_consulted 命令侧对偶〕；
    buy_supplies：门序逐项含 D012 混装边界 600 恰满/605 超/负值防御/三种
    满载互算〔600发=120份=300发+60份=600g〕/部分负载/换装赋值非累加/
    (0,0) 字面写零/cfg 覆写常数接线/分派链/零掷骰；跨链：SetMode→Buy→
    system_supply 补弹〔池 600→598、EMPTY 转 READY〕+医疗〔hp7→10、池
    600→597〕+切出 CARGO 卸货清零），全量 836 绿（804+32）。零掷骰（两
    处理体纯整数/指针写，不触任何 PCG32 通道——消费端乘区掷 SNIPER 属
    既有通道纪律，无新用途、未新开通道）。
  - PB-56 批③ Formation 族命令块（2026-10-06；MOVEMENT_PSEUDOCODE_v1.2
    §2.2 :121/:151-152 FormationCmd + §2.9 issue_group_move + §2.3 :197 增量①
    三件）。①FormationCmd 命令类（§D.7 22 类外 MOVEMENT 侧命令——登记表
    MOVEMENT 余量条目退役）+cmd_formation 处理体+分派支：组下令=逐单位写
    u.formation_shape（§2.2 :151-152 独立入口**无 REJECT 门**——门序属移动令
    族，队形选择无资格/状态门）；伪代码签名 unit(s) 实现为 units 列表字段
    （多单位一字段承载=「组下令=逐单位写」字面）；NONE 显式复位=现状同点堆叠
    （MV-B-19）；消费端 make_formation_fn 三表/dispatch 接线既有零新效果代码。
    ②issue_group_move 落 tick.py §2.2 命令层处理体段（§2.9 组下令入口——
    **UI 层聚合直调非命令流**；cap=MIN(speed_tier) 下令一次定型、逐单位
    issue_move 外部通道〔四件一体含清 cap——组令**随后**写 cap，次序即语义〕后
    len>1 写 cap、单位级队列 handoff 通道不清=编组同步跨排队令保持〔BLK-1
    既有〕；门拒单位仍写字面 cap=伪代码无条件写〔可推翻留痕，测试锚定字面〕；
    MoveCmd/issue_move 同模块零新导入边。**评审退回修复 2026-10-06**：原落
    movement.py 经函数体延迟反向导入 tick 构造 MoveCmd 命令对象=该模块
    历史基线之外的新导入边（tick 本体 import movement 的反向边），评审指认后
    移位本模块、movement.py 导入面回基线，并补导入面守卫锚〔tests/test_move_
    commands.py TestSimImportHygiene——子进程净导入 movement 断言 tick 不入
    sys.modules+源码零 `.tick` 引用〕）。
    ③§2.3 增量① 消费者随本块接线（move_speed_cm_tick tier 求值后、疾跑升档
    前插 `IF group_speed_cap>0: tier=MIN(tier,cap)`——档位层钳制不钳最终 v
    〔MV-B-15〕、疾跑升档在钳制后=个体冲刺破格〔契约⑧〕、拖曳锁档硬覆盖
    既有行不动）。**落地面切法默认裁决（2026-10-06，可推翻）**：批③ 支援链
    块曾留痕「增量① 随速度链块」两案待裁——本块采**案 a 连带增量①**（勘察
    decisionPoints「Formation 族落地面切法」案 a）：不连带则 issue_group_move
    写 cap 无任何行为效果=空写、T-queue-2 v 相等断言与编队行军整局速度可观测
    面均不可落（任务面「编组速度钳制接既有」+勘察测试面「v 相等断言」前置）；
    切面最小化——增量② REVERSE 乘区/增量③ 重伤乘区/MOB 拆除/§2.11 超射程
    进位仍随速度链块（登记表余量条目维持，未落地不冒装）。④分派支面：24 支
    （§D.7 22 类+PivotCmd+FormationCmd）——SetAirdropBeaconCmd 唯一剩余丢弃。
    ⑤整局影响：默认 AI 不发 FormationCmd/组令=既有 lean/rich/map 场景逐位
    不变无需重锚；HeadlessAI 增 formation keyword（缺省=既有行为逐位不变，
    motorized/tractor 先例）——编队行军画像（FormationCmd 命令流+issue_group_
    move 直调+脱离分离）tests/test_fullgame_acceptance.py TestFormationMarch
    FullGame；full_fingerprint U 段扩面 +3（formation_shape/group_speed_cap/
    command_queue 长——仅加严既有双跑锚）。⑥测试：test_move_commands.py
    TestFormationCmd/TestIssueGroupMove/TestGroupSpeedCapConsumer +11 锚
    （写槽逐单位/NONE 复位/命令流全链楔形锚/零掷骰；cap=MIN 后写/单单位不写/
    门拒字面/组令零掷骰；钳制逐档/cap 高于自档无效/疾跑破格 cap+1/拖曳硬
    覆盖）+T-queue-2 全规格重锚 1 处（原 test_cap_kept… 系增量① 未落地时的
    时序假设〔101 拍到位〕，消费者接线后 v 70→22 失效——重写为 §2.2 :184
    双单位同类编组版：逐拍 v 相等/链未清/cap 跨段保持/脱离恢复 70，原
    handoff-不清-cap 语义断言保留）+整局 2 锚〔TestFormationMarchFullGame〕
    +导入面守卫 1 锚〔TestSimImportHygiene——评审退回修复轮补〕，全量 850 绿
    （836+14）。零掷骰（cmd_
    formation 纯槽位写、issue_group_move 纯通道调用、钳制行纯整数——不触
    任何 PCG32 通道，无新用途、未新开通道）。
  - PB-56 批③ 速度链块·MOVEMENT §9 余量收口（2026-10-06；唯一实现规格=
    docs/MOVEMENT_PSEUDOCODE_v1.2.md——§2.3 求值链 v2 增量②③+MOB 拆除、§2.4
    增量④、§2.11 超射程进位；勘察「顺序分块建议」块1+块2 一次落）：
    ①§2.3 速度链本体（movement.move_speed_cm_tick）：**MOB 拆除**（GAP-14/契约⑩
    ——CritSlot.MOB MAJOR 早退+MINOR 乘区一并删除：重伤≠瘫痪，HP≤25% 仅减速
    不减停；趴窝语义由拖曳承载）+**增量② REVERSE 倒车乘区**（v×reverse_speed_bp
    (cfg,template)//10000——读 PB-52 求值函数，与门4 同一求值点：单位级倒车值
    接线即自动生效，PB-52 留待项①就此收口）+**增量③ 重伤乘区**（ANY(e.hp×10000
    ≤hp_max×crippled_threshold_bp)→×crippled_speed_mult_bp——原位替换 MOB MINOR
    乘区；边界含等号=16HP 车 4HP 恰触发）。乘区串接次序冻结（§2.3 v2 位级确定）：
    编组钳制→疾跑升档→拖曳锁档→地形 bp→**倒车→重伤**→PINNED（PB-49 后加乘区
    居历史原位=道路 max 前，规格 v2 未列 PINNED 的插入位留痕）→道路取 max。
    ②§2.4 增量④（movement.system_move 冻结体唯一例外一行）：facing 三分支求值前
    增 REVERSE 短路——lead_facing=elements[0].facing（倒车期间车头朝向不随位移
    翻转；后继队形循环写同值=无操作、零新槽）。
    ③D071 连锁·MOB 范围（combat.roll_crit）：掷骰域 below(4)→below(3)——MOB(=3)
    不再产出（移动侧消费已拆，留下生产支=零消费死支）；FC/SEN/RLD 产出与消费
    维持（aim/reload/optics 乘区仍在读）。**全拆范围未动不冒装**：roll_crit/
    upgrade_crit 整体拆除+crit_per_hp_bp 删除+CritSlot 枚举处置（FC/SEN/RLD 是否
    随 D068 一并裁）属 §8 D071「拆除范围须逐槽清点后拍板」未决项——TODO 在册。
    掷骰通道/次序不变（每次命中 chance_bp 一次+成功 below 一次——CRIT 纪律不动）。
    〔**滞文勘正 2026-10-07（D071 全拆块轮复核）**：未决项已拍板执行——发起人
    2026-10-07 拍板「全拆+留口子」：roll_crit/upgrade_crit 整删、crit_per_hp_bp
    删除、CritSlot 枚举四值保留标预留（口子四件见下方「D071 暴击全拆块」条目）；
    本段为速度链块成文时点状态留痕〕
    ④tables：crit_mob_minor_mult_bp **删除**（§4 删除登记——GAP-14 拆除后零消费）；
    crippled_threshold_bp=2500/crippled_speed_mult_bp=5000/auto_approach_standoff_cm
    =2000 出表（§4 全 6 字段齐——占位值随规格 §4，定标归数值章节）。
    ⑤§2.11 超射程自动进位（GAP-13 adopt/MV-B-21 炮击任务语境）：movement.
    auto_approach_waypoint（d≤max_range 返 None；否则 DIR8 方位退 stand=MAX(
    max_range−standoff, max_range//2)——AMB-4 半射程下界）+nearest_on_segment
    （LINE/CREEP 判距基准=线段最近点——规格仅定义点目标的定标延伸，可推翻）；
    消费点=cmd_fire_mission 双门通过后安装任务时，经 issue_move **外部通道**
    （MoveCmd queue=FALSE 四件一体：下达炮击任务即重置移动链/退编组——§2.11
    :384-385「外部直令场景」+AMB-3 修复表「queue=FALSE 外部直令 / handoff=TRUE
    排队消费」映射：世界级命令流=UI/AI 外部入口（§2.2 词汇），单位级队列排队
    消费现不可达〔FireMissionCmd 不入 command_queue〕——handoff 形态留待该未来
    通道不冒装）；射程内零行为差；移动令被门拒时任务照常建立不插航点（规格无
    「拒移动则拒任务」写点，留痕）；到位后展开门/射击门照常接管（进位≠开火
    许可——process_fire_mission/fire_at 本无射程门，进位=位置 QoL 非发射门）。
    ⑥整局影响与重锚（2026-10-06 速度链块重锚——先例=2026-10-04 命令层块 MoveCmd
    落地后重锚）：MOB 拆除+重伤减速+暴击域收窄（MOB 掷改 FC/SEN/RLD）三因改变
    交战节奏——lean/map seed42 队0 全灭 1227→1098 拍、弹丸 450→397；grind seed7
    结局翻转（队1 胜 50:380→队0 胜 380:0）；rich seed3 队1 幸存分值 180→480
    （狙击/烟幕/混编卡存活面变化）；five-objective hp_totals 微移（36→42）；
    逐 tick 双跑指纹位级一致全部维持（确定性无损——全部为定值锚重锚）。
    TestArtilleryMissionFullGame 意外免重锚：场景炮位距目标 116619>110000=超射程
    ——炮车现边进位边逐批复射（§2.11 新行为整局实证），采样拍锚（弹形/校射/
    弹药/到着扣血）恰全部不敏感于 ±31cm/拍漂移，原锚逐位保持（实测通过，非
    改锚）。测试：tests/test_movement.py MOB 两锚改写重伤阈值版+倒车/叠加/facing
    锁 +6 锚（§9 tests 行预告执行）；test_move_commands.py TestReverseDispatch/
    TestAutoApproach +6 锚；test_ground_combat.py TestAutoApproachConsumption +4 锚；
    fullgame 定值锚重锚 7 处。零掷骰（速度链/进位/暴击域收窄全纯整数确定性——
    CRIT 通道 draw 结构不变，不触任何 PCG32 通道，无新用途、未新开通道）。
  - 速度链收尾轮·增量⑨/MV-B-22（2026-10-07；PB-60 拍板「随 PB-59 同块落地
    一次闭包落完不留半块」的补齐执行——速度链块 2026-10-06 落主体时本项漏带，
    本轮还清拍板债；原登记表「随拖曳行为块落地」归属口径与本拍板冲突，以
    PB-60 为准勘正）：movement.system_move 拖曳随动段偏移基向改按
    elements[0].facing 反向——恒取车尾正后方 −scale(DIR8[facing//45],
    tow_follow_offset_cm)（§2.3 边界①/AMB-6 修复：原按「本 tick 位移向量反向」
    归一取偏移，倒车×拖曳叠加时被拖元素落牵引车车头侧——拖挂点物理上恒在
    车尾；REVERSE 期 facing 由增量④ 保持现值，本行取到即车头朝向，前进/倒车
    两态恒正确）。「有位移才随动」门（AMB-10）与被拖 pos 唯一写点不动（契约⑨）；
    函数内历史 math 导入（isqrt 归一）随改写移除——movement.py 新代码零 math
    新增（DIR8/scale=air.py 冻结族）。前进态偏移位级不变（位移向量与 facing 反向
    一致）——既有锚 test_tow_follow_moves_towed_element 逐位保持；新增倒车×拖曳
    车尾侧锚 test_tow_follow_reverse_keeps_towed_at_rear（truck_x−300 非车头侧
    truck_x+300）+MOB 生产面负锚 test_roll_crit_domain_excludes_mob（below(3)
    域扫 200 掷 ⊆{FC,SEN,RLD}——D071 全拆未决不冒装，负锚只证 MOB 拆除）。
    〔**滞文勘正 2026-10-07（D071 全拆块轮复核）**：全拆已拍板执行——本负锚被锚
    对象 roll_crit 已整删、锚随拆退役删除（「CRIT 零消费」负锚面由 fullgame
    channels_used 断言承载），见下方「D071 暴击全拆块」条目〕
    滞文勘正 3 处：test_ground_combat below(4)→below(3)/「FC/SEN/RLD/MOB 之一」
    →「FC/SEN/RLD 之一」、test_movement_settings 头注 test_mob_minor_halves
    引注→test_crippled_threshold_replaces_mob、movement.py 增量② 注释「增量⑨
    另册未落地」→已随批落地。全量 871 绿（869+2）。零掷骰（纯整数取向比较，
    不触任何 PCG32 通道）。
  - D071 暴击全拆块（2026-10-07 发起人拍板「全拆+留口子」——上方速度链块③/
    收尾轮/余量②三处「未决」滞文同日勘正闭账；FC/SEN/RLD 三槽随 MOB 一并
    拆除=暴击掷骰整体退役，与 D068「纯血条到底」字面全一致）：
    ①生产端：combat.roll_crit/upgrade_crit 整删（原位留拆除留痕注释）+
    resolve_hit/resolve_blast 两 MECH 暴击块删；②消费面：三乘区族留结构
    （aim/reload_factor_bp 的 crit.get 分支+optics_factor_bp 查表原样——空
    dict 恒 miss=暴击项恒等，aim/reload 退化为纯压制连续项、optics 恒 10000；
    本文件 6 调用点+sensing 4 调用点零改动）；③tables crit_per_hp_bp 删除
    （roll_crit 唯一消费者——§4 删除登记再+1）；④crit_mod_permille 字段保留
    标预留（勘察案 b：schema 冻结 D.3#20/空射硬要求⑥=0 契约/CSV 全空默认
    1000——零数据改动，与枚举预留对称）。**口子四件=一步可回**：枚举
    （types.CritSlot 四值保留标预留——含 MOB 值位）/乘区函数结构（分支保留，
    test_curves 三锚手写槽位即生效恰证口子活着）/CRIT 通道（通道号 3 冻结
    不回收+crit() accessor 保留——SPOT/SONAR 零消费占号先例；channels_used
    名单留 CRIT 即零消费自证）/恢复路径（system_supply 维修门 crit 判空+
    修满 crit.clear() 原位——恒空 dict 下门恒走 hp 判、clear 无操作，D016
    语义零改动；ElementInstance.crit 槽+指纹 E 段保留为物理载体，
    test_supply_mount 两锚在库）。重启步骤（唯一写点四处）：恢复 roll_crit
    （below(3) 域）+upgrade_crit+crit_per_hp_bp 出表+两生产块回贴——消费端
    零改动即活。测试：暴击消费测试随拆重锚——test_ground_combat
    test_mech_crit_on_crit_channel_only 改写负锚 test_mech_hit_zero_crit_
    zero_crit_draw（len(crit)==0/CRIT 通道不动）、TestResolveBlast
    test_falloff_anchors 同改负锚、test_roll_crit_domain_excludes_mob 退役
    删除（被锚对象已拆——「CRIT 零消费」负锚面由 fullgame channels_used 断言
    承载）、通道纪律断言 4 处去 CRIT（:856/:939/:978/:1097 定值）；整局
    定值锚重锚 9 处（暴击后效消失改瞄准/装填/探测节奏→轨迹漂移——多数恰回
    2026-10-06 速度链块前值：lean/map 全灭 1098→1227、弹耗 397→450、幸存者
    弹耗 15→18/10→12；grind seed7 380:0→380:50 胜方不变+first_empty 1291→
    1290；rich seed3 分值 480→180/hp 79→48、seed11 hp 82→71；five-objective
    seed3 hp 42→36；map 幸存者终位 (51980,2996)→(52377,3346)+受令窗 8→12
    次/缓存 4→6 键）；test_movement 冻结次序锚判别力修复（原组合 50/2500/
    5000 两序同值 6=空转，换 v=23/5900/2600 判别组合正序 3≠反序 2——python
    实算双验）；双跑位级指纹锚全套不动（确定性无损——掷骰面变化=CRIT 从
    有消费者变零消费者，通道 state/draw 结构/指纹面零改）。全量 870 绿
    （871−1：退役删除的 MOB 域负锚）。零掷骰面变化（拆除本身=掷骰退役，
    不新增任何掷骰）。GDD-00 D071 条拍板记录追加+GDD-02 细则三处「状态伤」
    残文勘误（D068 字面就此全一致）+拍板清单口子④条目（四口子+一步恢复）
    +MOVEMENT 升 v1.3 勘误档（同拍班子句——docs/MOVEMENT_PSEUDOCODE_v1.3.md
    新档整档升版：三勘误〔§2.3 求值顺序 v2 冻结链补列 PINNED 乘区/§2.2 门2+
    §2.4 拒动门旧文改 ROUTED 拒令+PINNED 减速放行/§2.3 六处行号锚按函数名
    指称〕+同档附带滞后勘正 7 处+§R 第三轮+变更记录，行为规格零变更）。
  - 勘误档收口轮（2026-10-07；MOVEMENT v1.3 三件小件收口——D071 同拍板
    「MOVEMENT 升 v1.3 勘误档」的遗漏面补齐，零码行为改动）：①勘误③补齐=
    拖曳锁档层级表述改 base 层（v1.2 伪代码作 tier 层改写「tier=tow_speed_tier
    后随 base 查表」，实码 movement.move_speed_cm_tick :115-117 为查表后直写
    base——纯查表无逐级舍入两式逐位等价，链位与算术结果不变；v1.3 六面同步：
    §2.3 伪代码行+块头快照收口轮复核刷新〔base 查表 :114/拖曳锁档 :115-117/
    倒车 :125-131/重伤 :132-138/PINNED :139-145/道路 max :146-153〕+§2.10-4
    悬空锚 :29-31 同款勘正+§R 第三轮行扩+头注+变更记录）；②引用处自查
    （v1.2→v1.3）=movement.py 速度链块注「唯一实现规格」行单行原位批注
    （movement.py 531 行数不变——快照锚不失效）+GDD-00 D070/D071 实现承载
    两行加〔2026-10-07 v1.3 现行版——行为规格零变更，同名节承载〕批注；
    历史块注/调研档/审查档照旧保留（成文时点快照不追改）；③复核在案（已随
    D071 全拆块落地，本块独立复验）：冻结次序锚判别组合 v=23（tier2
    45×5200//10000）×倒车 5900×重伤 2600——正序 3≠反序 2 本块 python 实算
    复验成立（旧组合 50/2500/5000 两序同值 6 不判别已弃用；次序互换即红）、
    combat.stop_tow docstring「被拖者 MOB 暴击保留」死语已改「暴击槽保留
    〔D071 全拆批注——四槽皆无产出者=预留空槽；REPAIRED 时 system_supply
    crit.clear() 仍先行〕」。测试计数不变=全量 870 绿（miniconda 解释器
    实跑复核——本块注释/文档改动零行为差）。零掷骰（零行为改动）。
  - 数据定标 v1 块（2026-10-07；数值总账 v1 §一/§二定标行同步——ask 四项：vs_fort
    攻坚值/turn_rate_deg/自卫烟幕配属/压制衰减裁处+能力旗标零配属留痕；CSV=唯一
    编辑面、provenance 全标『v1定标(推算占位)』档、gen JSON 经 tools/build_cards.py
    重建）：①vs_fort（P-122）：现役攻坚类四武器口径递进配值——W_T34_D5T（85mm）
    =5000/W_ZIS3_DIRECT+W_ZIS3_INDIRECT（76mm 同炮两档同值）=4000/W_PAK40（75mm）
    =3000（ask 字面 85/76/75mm≈3000-5000‰；勘察曾建议 ZIS3 曲射 2000 未采——ask
    量级字面优先，provenance 留痕）；步兵武器含铁拳维持缺省 1000=无攻坚资格。
    cmd_attack ① 建筑资格门对真卡攻坚武器就此放行（PB-56 批① 条目④ 数据侧脱节
    收口）；fire_direct 建筑支 w.damage×vs_fort（基础 damage 非 alt_profile）——
    D-5T 50/发（hp100 楼 2 发 160t）/ZiS-3 32/发/PaK40 30/发，推算注记入
    provenance 三行。②turn_rate_deg（P-123）：SU_ZIS3/GER_PAK40=50、SU_T3485=100
    （deg/s；AMB-5 //10 换算→5/10°/tick、180°=36/18 拍=ask 可用量级窗内，人力
    转炮慢于履带档）；SU_T3485 arc=360 现为死值=窄弧 profile 留位；步兵 6 卡+
    SU_TRUCK 留空（arc360 豁免+无车体语义=死槽不冒充）。PB-51 留待项①「填 CSV
    逐卡值」半边落地（双轨维持——统轨案不采留痕同条目）。③自卫烟幕配属（P-121
    更新）：SU_TRUCK/SU_T3485 self_smoke_charges=2（ask 字面点名 SU_TRUCK+勘察
    默认 T34——史实 BDSh 发烟罐锚、后者可撤销；cfg.self_smoke_default_charges=2
    同值）；PB-53 留待项④「现役 0 卡配属」收口（余 8 卡维持 0）；cmd_smoke 玩家令
    入口、HeadlessAI 不发 SmokeCmd=整局零扰动。④压制衰减裁处（士气块留待项④ 收口
    ——发起人默认裁决=案 A 维持 10/s 转正、可推翻；tables.py:159 注释成轨+数值
    总账 v1 §一补行，5/s 字面不采三理由链留痕同处）。⑤能力旗标零配属留痕：
    CAN_AIRDROP_BEACON 现役 0 卡（cmd_set_airdrop_beacon ① 资格门对现役恒
    REJECT——docstring 批注在案）=无卡可配非缺陷，配属留待真渗透/侦察卡批次
    （GDD-01 规划面）；狙击组卡不存在（CAN_SNIPER_COVER 零卡既有登记）同留痕。
    测试：tests/test_data_calibration_v1.py +14 锚（真卡拆楼三武器端到端+步兵负锚/
    rotate_step 真卡换算/自卫烟幕真卡链/衰减裁处 pin）+test_card_data_first_batch
    test_pb53 数据锚随定标重锚（「全默认 0」→「两卡配属 2」——数据先行锚随数据
    转正翻转，docstring 如实标注）。全量 919 绿（905+14；905=870 基线+命令族收口
    块/感知接线块新增）。零掷骰（数据值/provenance/重建纯确定性——build_cards
    同输入字节相等锚在库；新测试不新增 PCG32 通道断言面，发射段掷骰属 fire_direct
    既有通道纪律、真卡 accuracy 缺省 10000 必中）。
  - 空中仿真闭环·块1 航空命令层（2026-10-07；AIR_UNITS_PSEUDOCODE_IMPL_v1.4
    §D.5 九命令——命令驱动契约⑦「AI 虚拟玩家走同一接口」）：九命令类
    （AirCallCmd/AirMoveCmd/AirPatrolCmd/AirAltCmd/AirStrikeCmd/AirAirdropCmd/
    AirEngageAirCmd/AirDisengageCmd/AirRTBCmd——tick.py 命令类区 BuySuppliesCmd
    后新增，地面命令类同位先例）+_dispatch_command 九分派支真调用（处理体
    air.py cmd_air_* 族 2026-10-01 行为层既有，本块只通命令流——块零新处理体）。
    payload 键口径={BOMB,SUPPLY,PARATROOP}：§D.5 的 supply_rounds/supply_medical
    双键已随 2026-10-03「一池按重量计」拍板并轨 SUPPLY 单键（地面 buy_supplies
    :1225 换写同族先例，air.py cmd_air_call 既有口径照读——留痕可推翻）。
    **连带规格对齐一处**：air.py resolve_strafe 命中支切 combat.resolve_hit
    （§F3 字面 resolve_hit(world,p)——契约⑥ TOP 分支即时结算 B-13；air.py 头注
    预留「地面完整体落地后可切换」切换点执行）：补齐命中面压制注入
    （resolve_hit 尾行 inject_suppression_area——原直扣实现零压制）+
    compute_hit_facing 覆盖序（驻楼 REAR/转向 SIDE/顶攻 TOP——原恒 TOP）；
    AirProjectile 补 pen_bonus=0 档案位（对齐地面 Projectile §F4 :790）；
    air.py 顶部 combat 三导入（apply_damage/damage_mult_permille/armor_lookup）
    与 Facing 导入随切换清除（局部导入 resolve_hit/inject_suppression_area——
    combat 无 air 反向导入边，局部沿用原式）。行为变更=扫射命中新增面压制注入
    （如 VYa23 命中即 40 压制@falloff(d)——与地面直射命中同构），旧锚
    test_air_behavior 全绿（kill/弹药锚不敏感于压制面）。测试
    tests/test_air_commands.py +13 锚（九命令分派链逐支/空降 deck 扣份经命令流/
    命令层零掷骰〔八命令批量八通道 state 不动〕/disengage 命令流全链〔world_tick
    含 dogfight_check 不重咬〕/strafe 切换双锚〔命中=hp 20-6+suppression 恰 80
    手推、未命中=jitter 压制+零伤〕）。全量 932 绿（919+13）。零掷骰（分派纯
    路由——AirDisengageCmd 的 tail 掷骰属 §F4 处理体既有 AIR 通道纪律，无新
    用途、未新开通道）。〔独立评审 2026-10-07：通过+6 非阻塞——修复三条：
    resolve_hit 补 cfg 传参（air.py，一词——§F3 字面无参但作用域 cfg 不应丢）、
    combat.compute_hit_facing「top_attack 无生产者」滞文日期批注（本块扫射
    即首个生产者）、test_air_commands helper 注释口径收窄；留档两条：③air.py
    行为层 cmd_air_alt/strike/airdrop 处理体直读全局 CONFIG（cfg 形参缺失=
    2026-10-01 既有设计，cfg 覆写测试对这三支静默用全局值——是否统一补 cfg
    形参**待发起人裁**，登记在案）；⑥AirStrikeCmd 字段名 target 沿处理体/
    地面 AttackCmd 先例（§D.5 :359 作 target_point——措辞级不改）〕。
  - 空中仿真闭环·块2 纯航空无头整局（2026-10-07；**sim 零行为改动**——只增
    tests/test_fullgame_acceptance.py 场景与锚）：HeadlessAI 增 air keyword 画像
    （缺省=既有行为逐位不变——anchors/move_mode/formation 先例；固定拍呼叫脚本
    AIR_CALL_SCRIPTS 队0 Il-2M(BOMB2)+Yak-9/队1 Pe-2(BOMB4)+Fw 190A+实战期
    节拍令：带弹攻击令/战斗机爬升 AirAltCmd(HIGH)/每 150t CAP AirPatrolCmd 图
    中心（B-20——同空域自动缠斗 R-20）/攻击机投完弹手动 RTB（B-29——纯航空
    场景 STRAFE 弹无从消耗，弃权判据=BOMB 耗尽）/每 100t 经济轮转（冷却到期+
    不在空+点数够→重呼——D015 闭环））+build_air_world 场景工厂（无地面单位/
    无占点——D031 第四链队0 胜）+run_full_game 航空生命周期逐拍观测（air_calls/
    arrivals/recoveries/downed/first_{strike,rtb,dogfight,projectile}/
    dogfight_ticks——消失分类 prev RTB=回收、DOGFIGHT/hp<=0=击落）+
    **full_fingerprint A 段全字段扩面**（spotted_mask/facing/flight_plan/
    patrol_loop/task 判别联合/ammo/alt_pending/dogfight/engage_air/
    paratroop_cargo/no_engage_until——前 6 字段序保持、无航空器场景零贡献=
    既有指纹位级不变，扩面仅加严双跑锚）。锚（seed 42 定值+手推成分逐条注明）：
    呼叫拍 101/121（命令驱动首拍）；进场完成 359/372/378/475（GAP-04 位置化
    手推 spawn+⌈60000÷speed⌉−1——Il-2M 160×375=60000 恰整除）；首攻击令 651
    （实战首 %50 拍）；首 RTB 1188=Pe-2 两轮出击 BOMB 耗尽自动 RTB（GAP3-02）；
    缠斗 851/击落 3 架/冷却公式精确锚（击落=(600+hp_max×30)×3 三架逐架核算、
    回收=600+损血×0）；经济恒等式 750−Σ呼叫+Σ回收=终值（队0 560/队1 422，
    实现无关不变量+定值双锚）；通道纪律={'AIR'}（纯航空零地面消费）；同 seed
    双 world 13801+25 拍逐 tick 指纹位级一致。tests/test_fullgame_acceptance.py
    +2 锚（TestAirFullGame），全量 934 绿（932+2）。零掷骰面变化（纯验收块——
    观测/指纹/AI 均只读 world 确定性状态，不触 PCG32 通道）。
  - PB-56 总收口盘点（2026-10-06；§D.7 :256-268 全集 22 类逐支机械核点
    ——python 正则对 _dispatch_command 分派支，line 号为本日快照）：
    **21 类已落真调用**（实现锚=分派支，测试锚=首要文件）：MoveCmd
    〔tick.py:1577→issue_move §2.2；test_move_commands〕StopCmd〔:1579→
    cmd_halt MV-B-18；test_move_commands〕DeployCmd〔:1589→cmd_deploy §F6
    :1072 批②；test_tow_deploy〕PackCmd〔:1598→cmd_pack_or_move §F6 :1116
    批②；test_tow_deploy〕SetModeCmd〔:1604→cmd_set_element_mode §F6 :1193
    批①；test_ground_combat/test_support_commands〕PurchaseCmd〔:1613→
    cmd_purchase §F7；test_economy_phase〕FireMissionCmd〔:1615→cmd_fire_
    mission §F4 :960；test_ground_combat〕CancelFireMissionCmd〔:1619→
    cmd_cancel_fire_mission §F4 :972；test_ground_combat〕SmokeCmd〔:1621→
    cmd_smoke PB-53 自卫路径〔武器烟弹路径仍 TODO 见 PB-53 留待项〕；
    test_self_smoke〕SetStanceCmd〔:1624→最小写点 批①；test_ground_combat〕
    ToggleAmbushCmd〔:1632→cmd_toggle_ambush §F4 :874 批①；test_ground_
    combat〕SprintCmd〔:1639→cmd_sprint §D.0 :48；test_move_commands〕
    GarrisonCmd〔:1641→cmd_garrison PB-57；test_garrison〕UnGarrisonCmd
    〔:1645→cmd_un_garrison PB-57；test_garrison〕MountCmd〔:1647→cmd_mount
    §F6 :1137 批②；test_supply_mount〕DismountCmd〔:1659→cmd_dismount §F6
    :1131 批②；test_supply_mount〕TowCmd〔:1665→cmd_tow §F6 :1228 批②；
    test_tow_deploy〕UntowCmd〔:1674→cmd_untow §F6 :1242 批②；test_tow_
    deploy〕AttackCmd〔:1679→cmd_attack §F4 :848 批①；test_ground_combat〕
    SetSniperCoverCmd〔:1684→cmd_set_sniper_cover §F6 :1258 批③；test_
    support_commands〕BuySuppliesCmd〔:1698→buy_supplies §F6 :1215 批③；
    test_support_commands〕。SetAirdropBeaconCmd〔:1696→cmd_set_airdrop_
    beacon §F6 :1269，2026-10-06 收口补落——§D.7 22 类 22/22 全落地（键型
    unit.id/(team,pos) 三口同形适配同日同修，见下方 TODO 段勘正）。§D.7 外
    已落：PivotCmd〔:1581 PB-51；test_pivot〕FormationCmd〔:1583
    批③ 本块；test_move_commands〕ReverseCmd〔types.py 定义+tick 再出口，2026-10-07
    命令族收口块；issue_move 归一化 movement.py；test_move_commands〕CancelCmd
    〔2026-10-07 命令族收口块；cmd_cancel 全清变体（MV-B-18 另半）；test_move_
    commands〕——MOVEMENT §2.2 命令族余量就此清零。**口径**：「§D.7 22 类分派支」
    以 §D.7 :256-268 枚举为准收口=22/22 落地，
    PB-56「分批命令处理体」三批枚举面就此全落（批①②③ 各支真调用+测试锚
    在案）；「命令层全集」=§D.7 22 类+§D.7 外 MOVEMENT 族（PivotCmd/
    FormationCmd/ReverseCmd/CancelCmd）全落地（2026-10-07 命令族收口块闭账）。

TODO 挂点登记（未实现系统——不冒充通过；落地时按 §F8 :1424-1438 行序插入）：
  - §D.7 :256-268 命令集的 cmd_* 处理体（PurchaseCmd/FireMissionCmd/
    CancelFireMissionCmd/MoveCmd/StopCmd/SprintCmd/PivotCmd/SmokeCmd（自卫烟幕路径）
    /GarrisonCmd/UnGarrisonCmd（PB-57 驻楼命令块 2026-10-06 接——cmd_garrison/
    cmd_un_garrison）/AttackCmd（PB-56 批① 作战链命令块 2026-10-06 接——
    cmd_attack §F4 :848）/SetModeCmd/ToggleAmbushCmd/SetStanceCmd（PB-56 批①
    作战链命令块·余三命令 2026-10-06 接——cmd_set_element_mode §F6 :1193/
    cmd_toggle_ambush §F4 :874/cmd_set_stance §D.7 :261 最小写点，批① 收口）/
    MountCmd/DismountCmd（PB-56 批② 机动链命令块·上下车 2026-10-06 接——
    cmd_mount §F6 :1137/cmd_dismount §F6 :1131）/
    TowCmd/UntowCmd/DeployCmd/PackCmd（PB-56 批② 机动链命令块·拖曳展开
    2026-10-06 接——cmd_tow §F6 :1228/cmd_untow §F6 :1242/cmd_deploy
    §F6 :1072/cmd_pack_or_move §F6 :1116，start_tow §F2 :494-516 随块落
    combat.py——批② 六命令就此收口）/
    SetSniperCoverCmd/BuySuppliesCmd（PB-56 批③ 支援链命令块 2026-10-06 接——
    cmd_set_sniper_cover §F6 :1258/buy_supplies §F6 :1215；批③ 的 Garrison/
    UnGarrison 随 PB-57 已接转回归验证〔分派链锚 test_garrison.py 既有〕；
    批③ Formation 族随 Formation 族块 2026-10-06 接——上方块条目+总收口
    盘点条目在册）
    已接）——consume_commands 分派支
    现丢弃（SetAirdropBeaconCmd→§F6 :1269——**§D.7 22 类总收口后唯一剩余丢弃支**，
    不在 PB-56 三批枚举〔拍板清单 PB-56 行批③ 列无此项〕，收口归属待发起人裁；
    连带 latent：beacon_by_unit 键型读写分叉——注销侧 unregister_unit_refs 按
    unit.id pop（combat.py）/读侧 nearest_friendly_beacon 遍历 items() 读
    key.team（air.py，docstring 自称 {unit: pos}），任一口径落地都使另一侧崩或
    静默失效，落地时须同修）——cmd_* 处理体由调用方直调的
    旧口径随之退役〔**滞文勘正 2026-10-06（速度链块轮复核）**：SetAirdropBeaconCmd
    处理体**已落地**——cmd_set_airdrop_beacon（本文件 §F6 :1269 段，2026-10-06
    发起人指令「剩四类事全部完成」收口补落）+分派支真调用+键型=unit.id/值=
    (team,pos) 三口同形适配（air.nearest_friendly_beacon 同日同修）；本 TODO 段
    与 _dispatch_command docstring「仅余 SetAirdropBeaconCmd 未落地」/上方 PB-56
    总收口盘点「1 类仍丢弃」两处滞文以本勘正为准——代码面 22/22 全落地〕；
  - MOVEMENT v1.2 §2.2 命令族余量（2026-10-06 速度链块后更新，2026-10-07 命令族
    收口块闭账）：FormationCmd/issue_group_move 已落（2026-10-06 PB-56 批③
    Formation 族块——上方块条目；§2.3 增量① 消费者随块接线）；增量②③④/MOB
    拆除/§2.11 进位已落（2026-10-06 速度链块——上方块条目）。ReverseCmd/CancelCmd
    **已落地（2026-10-07 命令族收口块）**：ReverseCmd=types.py 定义（tick 再出口）
    +issue_move 归一化 `cmd ← MoveCmd{path=[dest], mode=REVERSE, queue=FALSE}`
    （movement.py 门3 后门4 前——构造 MoveCmd 须命令类下沉共享叶模块，movement→tick
    反向导入边 2026-10-06 评审明令禁止，MoveCmd 同批迁 types.py+tick 再出口=导入面
    不变）+分派支+cmd_halt 过滤并入+consume_unit_commands 消费支并入；CancelCmd=
    cmd_cancel 全清变体（清航点+复位模式+清整个队列+清 pivot+清任务体 fire_mission
    ——任务体清为发起人任务块口径，超 v1.3 :160 字面半步，MOVEMENT v1.3 变更记录
    留痕；stance 不动=与 SetStanceCmd/ToggleAmbushCmd 区隔 MV-B-18 边界；ROUTED 拒
    =cmd_halt 先例对齐）。命令族余量就此清零，本条退役留痕不删行；
  - MOVEMENT v1.2 速度链块后余量（2026-10-07 收尾轮更新，均不冒充）：①**增量⑨/
    MV-B-22 拖曳随动偏移基向**——**已落地（2026-10-07 PB-60 随批，见上方收尾轮
    条目）**〔本条 2026-10-06 补册：速度链块前本登记表漏列此项（勘察指认），规格
    明载而账面无条目=登记表漏项；原写「随拖曳行为块/命令族扩容块落地」的归属
    口径与 PB-60 拍板「随 PB-59 同块落地」冲突，2026-10-07 按拍板勘正并执行：
    偏移基向按 `elements[0].facing` 反向（车尾正后方 `−scale(DIR8[facing//45],
    tow_follow_offset_cm)`——原按「本 tick 位移向量反向」归一取偏移，倒车×
    拖曳叠加时被拖元素落牵引车**车头侧**（物理拖挂点恒在车尾）；「有位移才随动」
    门（AMB-10）与被拖 pos 唯一写点不动（契约⑨）〕；
    ②D071 全拆范围（roll_crit/upgrade_crit 整体拆除+crit_per_hp_bp 删除+CritSlot
    枚举处置——FC/SEN/RLD 是否随 D068 一并裁）：§8 D071「逐槽清点后拍板」未决，
    速度链块仅落 MOB 范围（below(3)，见上方块条目③）〔**滞文勘正 2026-10-07
    （D071 全拆块轮复核）**：已拍板执行——全拆+口子四件（枚举预留/乘区留结构/
    CRIT 通道预留/恢复路径登记），见下方「D071 暴击全拆块」条目，本项就此闭账〕；
    ③GDD 回写 D070-D075/
    R-24-R-27——**已执行（2026-10-07 PB-61 收口统一回写）**：GDD-00 决策日志
    追加 D070-D075 六条+D026 补注（D073 森林不减速）；GDD-02-单位功能细则-v1.9
    §0 追加 R-24~R-27 四条+R-13 补句（D075 超射程进位）+头注回写行；GDD-05 A7
    Sprint 行补句（D072 疾跑禁射）；D071 条内如实登记连锁未决项（roll_crit/
    upgrade_crit 全拆+crit_per_hp_bp+CritSlot 枚举——见②）〔GDD 回写块复核轮
    2026-10-07 补全：D070-D075 六条补代码实现锚（file:line——收尾轮版本仅文档
    节引）；R-24 停止/取消两句按 cmd_halt 实况改写+CancelCmd/ReverseCmd 未落
    余量注〕；
  - §2.11 超射程自动进位与 §2.3 速度求值链 v2 余量：**已随速度链块 2026-10-06
    落地**（上方块条目⑤——auto_approach_waypoint/nearest_on_segment/
    auto_approach_standoff_cm 出表/cmd_fire_mission 消费点；增量②③+MOB 拆除+
    test_movement MOB 两锚改写）；本条原「随各自消费块落地，未落地不冒装」就此
    退役，留痕不删行。
  - 断箭设定数值块留待项（2026-10-04，映射 §三 gapFills 占位）：SprintCmd 冷却门
    （cfg.sprint_cooldown_ticks=600 已出表——若发起人拍板采纳：cmd_sprint 增
    now<sprint_until+cooldown→REJECT，sprint_until 语义不变、契约⑧速度式不动）
    【2026-10-07 命令族收口块：**发起人拍板采纳已接线**——cmd_sprint ROUTED 门后
    增冷却门（登记形态字面；sprint_until 初值 0=从未冲刺哨兵豁免首冲——无哨兵则
    tick<600 首冲恒拒）；tables.py:17 注释成轨；test_move_commands 重锚 1+新增
    冷却窗锚；纯接线零新常数、整局面零影响（HeadlessAI 不发 SprintCmd）】与
    water_speed_bp 接线（随 MV-B-02 改B：MovementClass 扩枚举/两栖旗标+水域瓦片
    speed_bp 注入——契约②不许旁路）——后者未实现，不冒充。
  - PB-56 批② 拖曳展开块留待项（2026-10-06 登记，均不冒充）：①cmd_pack_or_move
    的 **MoveCmd 触发面**（真两难待发起人裁——勘察 decisionPoints#1）：IMPL
    :1116 注「PackCmd / MoveCmd 触发」×机制版 :1098「移动令即回 MOBILE 作废进度」
    与 MOVEMENT v1.2 §2.2 门1（冻结契约㉑ DEPLOYING/PACKING 拒移动令——锚
    tests/test_move_commands.py test_gate1_deploying_rejects）两文档对立；按勘察
    推荐案 b 只落 PackCmd 分派支，「DEPLOYED 单位收移动令不收起直接可走」现状
    行为洞留痕（tests/test_tow_deploy.py TestDeployMoveInterlock 锚定现状，
    接线即须改锚+改文档）〔**2026-10-06 速度链块轮复核：维持挂起不新裁**——三文档
    对立原文重核（IMPL v1.7 :1116『PackCmd / MoveCmd 触发』/机制版 v1.7 :1098
    『移动令即回 MOBILE 作废进度』/MOVEMENT v1.2 §2.2 门1 契约㉑），无新据可裁；
    默认裁决（案 b）经批② 评审收尾『发起人未推翻视为维持』在库、可推翻窗口仍开
    ——关闭须发起人显式追认（追认即关行为洞：issue_move 门1 特例+两测试锚+
    两文档口径三处同改）〕〔**2026-10-07 命令族收口块：发起人显式拍板追认=采
    IMPL 字面（移动令触发收装），行为洞就此关闭**——接线落点 movement.issue_move：
    DEPLOYING×外部移动令=作废回 MOBILE 同拍放行（机制版 :1098 字面）；DEPLOYED×
    移动令（外部非排队+handoff 两通道）=转 PACKING+本令照常安装，收装完成前
    system_move 同名门拦位移、收装毕自动续走「先收装再走」；PACKING 拒令维持
    （三文档均无打断语）；效果点后置=门2/3/4 拒令零副作用；queue=TRUE 排队令
    入链尾不触（执行拍经 handoff 到 DEPLOYED 分支照样收装）。改面=movement.py
    issue_move+MOVEMENT v1.3 契约㉑（DEPLOYED 半边特例化批注+变更记录）+GROUND
    IMPL v1.7 :1116 日期批注+两锚翻转（test_gate1_deploying_rejects→作废放行/
    test_deployed_move_order_walks_without_packing→收装 300t 后开走）+cmd_pack_
    or_move docstring 收口〕；②cmd_tow ② 门「MECH×TOW 位」被拖=卡车拖卡车
    （SU_TRUCK own_weight_tons 空=0 → 吨位门恒满足退化合法）——伪代码字面行为
    登记；补「自重>0 才可被拖」门或数据侧补卡车自重随数值章节；③GAP-23（声测
    班 DEPLOYED×Mount 无互锁——行驶中机动声测站持续定位）伪代码承载缺陷已
    登记、sonar_step 未实现零现役影响，照登记不修（修改建议两案在案）。
  - PB-51 留待项（2026-10-04 原地转向块登记，均不冒充）：①转向速率双轨分叉——
    射击侧 R-09 rotate_step 仍读逐卡 turn_rate_deg（AMB-5 换算；现役 10 卡全默认 1
    →窄射界炮转车体 180°=180t 慢到不可用=既有数据欠账），命令侧 pivot 走
    cfg.pivot_rate_deg_per_tick 类分档——同一物理过程两轨并存，统一轨待数值章节
    拍板（填 CSV 逐卡值，或 rotate_step 改读 cfg 表——后者触 TestRotateStep 锚与
    live 交战节奏，须随数值定标一并裁）〔**2026-10-07 数据定标块：「填 CSV 逐卡值」
    半边落地**——SU_ZIS3/GER_PAK40=50、SU_T3485=100（deg/s；AMB-5 //10 换算→
    5/10°/tick、180°=36/18 拍可用量级，P-123；T3485 arc=360 为死值占位/窄弧
    profile 留位，步兵+SU_TRUCK 留空=死槽不冒充）；双轨维持（pivot 与 rotate
    语义分立=勘察默认），统轨案维持不采仅留痕——「欠账」句就此失效，双轨分叉
    本体仍留档〕；②MV-B-05「到达朝向指定令」仍 defer
    （MoveCmd 增 facing 参数——与 PivotCmd 近亲不同机制；现可用「移动令+到位后
    手动 PivotCmd」两段表达，自动衔接待 MV-B-05 改B）；③PivotCmd 不入单位级
    command_queue（现仅 MoveCmd 可入——「排队转向」随命令族扩容另议）。
  - PB-52 留待项（2026-10-04 单位级地形数值块登记，均不冒充）：①REVERSE 速度
    乘区消费者（§2.3 增量②）【2026-10-06 速度链块收口：乘区已接线
    （movement.move_speed_cm_tick 读 reverse_speed_bp 求值函数——单位级倒车值
    自动生效），门4 与乘区两消费点同读单点如拍板】；②全量 10 卡定标归数值章节（现役示例 SU_T3485/SU_TRUCK 两卡占位 P-120）；
    ③水域列不设（MV-B-02 延期——water_speed_bp 占位常数零消费者口径维持）；
    ④pathfind 侧 tile_cost 仍按类级 bp（find_path 无单位上下文——寻路预估与
    实速的单位级偏差为已知近似，随寻路单位级化另议）。
  - PB-53 留待项（2026-10-04 自卫烟幕块登记，均不冒充）：①§F6 武器烟弹路径未
    落地（查 SMOKE 武器档+射程门③A+SCATTER 散布+耗弹装填+声测喂入 AMB-14/17②
    ——cmd_smoke 现仅自卫路径；相邻缺口维持登记：现役唯一 SMOKE 武器
    W_RECON_SMOKE 为 DIRECT 弹道，走进失压制支且 suppression_power=0——
    resolve_blast 仅 system_projectiles 的 BALLISTIC 支可达，数据侧烟罐无生产链，
    与「侦察排须配 SMOKE 档」的战术意图存疑，随武器路径/数据侧另议）；②sensing
    遮蔽接线未接（smoke_m 衰减通道存在但 system_sensing 调用未传 smoke_m_fn、
    全仓零调用方——烟区对探测/命中零影响；自卫烟幕遮蔽实效必须先补该接线，
    随感知块另议——勘察已知缺口，本块未含）〔**2026-10-07 感知接线块：已收口**
    ——sensing.py 增 smoke_m_between（线段×圆弦长，投影+整型开方）
    /forest_m_between（tile 步进采样）/in_forest_at 三几何函数+
    terrain_sensing_channels 单点装配（整型开方经 geom.isqrt_exact 单点取用
    ——sensing.py 不直接引入 math 模块〔导入基线扫描裁定，geom.py 先例内
    math.isqrt 精确整数运算不受影响〕，2 万随机样位级等价复算+全量回归）；
    world_tick ③ system_sensing 三 fn 与
    fire_at 校射 point_in_friendly_vision 两 fn 均已喂——自卫烟幕/炮烟烟区即刻
    有探测与校射实效（w.smoke_zones 数据源，闭包实时读）；命中侧（resolve_hit
    命中式）不涉烟幕维持原面；测试=穿烟探测缩+ttl 尽恢复/自卫烟幕遮蔽整链/
    校射烟阻断（test_sensing_terrain.py+test_ground_combat）〕；③烟幕方向语义 defer（勘察两案取
    「以车为心圆」简化落地；车尾/侧向整数偏移圆心无断箭证据，待新证或数值章节
    再议）；④发数/冷却/延迟三常数无据占位（N32 仅定性）+现役 0 卡配属
    （self_smoke_charges 缺省 0，P-121）——定标归数值章节〔**2026-10-07 数据定标
    块：配属半边收口**——SU_TRUCK/SU_T34 self_smoke_charges=2（P-121 更新：ask
    字面点名 SU_TRUCK+勘察默认 T34 史实 BDSh 锚、后者可撤销；cfg.self_smoke_
    default_charges=2 同值），余 8 卡维持 0=无能力；三常数维持无据占位（数值
    总账 v1 §一在册）〕；⑤冷却自受令拍起算
    （非落烟拍）为最简实现取舍，delay<cooldown 默认配置下无行为差。
  - 士气块留待项（2026-10-04 士气状态机块登记，均不冒充；①③⑤ 已由同日士气
    效果接线块收口、⑥ 经其再确认维持，编号保持稳定供交叉引用）：①D027:174 卡级士气阈值
    三列（受压/钉住/溃逃，空=回退 cfg 缺省）未落数据管线（PB-52 五步先例在，随数据
    侧另接）——现役全卡走 BalanceConfig 缺省 40/70/100
    【2026-10-04 效果接线块收口：三列已落地（schema 1.3+system_morale 三级回退），
    现役 10 卡全空回退缺省=数据侧如实留空，定标归数值章节】；②GDD-05 B2:128 修正项乘区
    （近卫+20%/国民−20%/光环+15%）无数据位（近卫/国民无卡级旗标、AuraKind 无士气
    类）——D014 待定③军官/政委加速重整与 D034 督战随指挥单位块一并拍板实现形态
    （扩 AuraKind 走 aura_bonus_bp 连乘先例 vs 督战独立主动命令【现零主动技先例】；
    morale_rally_ticks/三阈值均为可乘基数无架构锁死）；③命中侧消费口径未拍板：
    B4:149 moraleFactor 按态乘区（受压×0.7/钉住×0.3）vs 现码连续线性
    （aim/reload_factor_bp 随元素压制线性）——本块维持连续式，士气态不进命中链
    【2026-10-04 效果接线块收口： moraleFactor 按态乘区已落地 fire_direct acc 链
    （morale_acc_factor_bp，与元素级连续项叠乘=双粒度记账）——aim 时间/装填士气态
    杠杆仍无 GDD 锚不采】；④压制衰减速率两档差一倍（GDD-05 B2:127/B4:177 均写 5/s vs 现码
    sup_decay_per_tick=1@10Hz=10/s，SUPP_DECAY_X2 旗标再×2）——维持现码 10/s 未裁，
    待数值章节显式定标〔**2026-10-07 数据定标块：已裁**——发起人默认裁决=案 A
    维持 10/s 转正（可推翻）：GDD-05 5/s 字面不采=整型纪律（0.5/tick 非整须隔拍
    复杂化）+同源标尺不采自洽（同页 B4 0..150/50/100/150 已随 PB-54 不采）+士气
    整局验收手推链全建立在 1/tick；数值总账 v1 §一行+tables.py 成轨注在册〕；⑤ROUTED 期火任务（fire_mission）不清、不禁射（D014/B4 均
    无此句未发明——仅连续压制消费口径），随交战侧另议
    【2026-10-04 效果接线块收口：禁射已落（fire_permitted ⑨ 门=发起人指令
    「溃逃态禁射」）；火任务仍不清（任务体跨溃逃期保留、逐炮被 ⑨ 拦、重整后
    恢复逐炮——「不清+拦射」组合口径）】；⑥车载 50% 压制转移（核证
    v1:139/映射 §四.2「随士气系统数值章节另议」）维持现状驳回先行：载具与车内步兵
    各自独立全额吃面压制（inject_suppression_area 无 mounted 分支）
    【2026-10-04 效果接线块再确认维持：规格明示「随士气系统数值章节另议」，效果
    接线块非该数值章节；转移需 mounted 通道改写+口径取舍（转移量按载体实收还是
    名义剂量、下车时刻语义），随数值章节一并裁】；⑦受压自动匍匐
    （核证 v1:142 新证）未纳入首版（无 GDD 锚、涉 stance 写侧）；⑧溃逃目的地=己方
    底边中点近似（PB-35 部署区地图数据缺失同款口径），正式部署区数据接入后随
    _deploy_anchor 一并换锚；⑨主循环拍内序差：B2 把压制注入列步8（damage 后）——
    现码衰减在 ①system_timers、注入在 ④combat/⑤projectiles，同拍内先衰减后注入
    （当拍注入值存活至下拍衰减，净效应近似）；
    ⑩受压态移动惩罚（2026-10-04 效果接线块登记）：D014:97 受压=「命中/性能下降」
    无移动项、GDD-05 B2/B4 无受压减速值——无据不落（钉住减速=pinned_move_mult_bp
    既有、溃逃=全速强制移动），若未来采纳核证 v1:142 受压自动匍匐将带来间接移动
    效应，随该条一并议；⑪士气态瞄准时间/装填杠杆（2026-10-04 效果接线块登记）：
    断箭参考「瞄准×2/×3」为 aim 时间档、GDD-05 无此式（B4:149 仅命中乘区）——
    二选一取命中 bp 档落地，aim 时间/装填态乘区未采（现由元素级连续项
    aim/reload_factor_bp 承载），数值章节若需离散化再议；⑫对空链士气态消费
    （2026-10-04 效果接线块登记）：morale_acc_factor_bp 仅乘 fire_direct（依据=
    代码先例：fire_aa acc 链本就窄于 fire_direct 不乘 ambush/aura/self_defense +
    ⑦⑧ R-17 最小许可集先例——2026-10-04 评审遗留④改准，fire_aa docstring 留痕）、
    ⑨ 溃逃禁射门亦仅地面链（⑦⑧ R-17 最小许可集口径同款）——对空链士气语义
    （因子/禁射/衰减可视）随对空侧数值章节另议；
    ⑬溃逃航点拒装边角（2026-10-04 评审遗留①登记——留痕非待办，_enter_routed
    docstring「登记表留痕」指针落点）：_enter_routed 经 handoff 内部通道装溃逃
    航点，issue_move 门1（展开/收起互锁）/门3（整班车载）对 handoff 不豁免——
    展开中牵引炮/整班车载单位溃逃态照常成立（计时/清令照走）但航点拒装
    （move_path 已清恒空），=原地站满重整时长才重整（routed_until 到拍正常重整，
    计时不因航点缺席改变）；车内班随载具移动、载具自身士气独立判。

World 为最小容器组装（air.py 头注 world 消费面 + tests/test_air_behavior.py mock
惯例），零渲染依赖。整型确定性：坐标 cm、时长 tick（10Hz）、概率 bp；随机只走
PCG32 分通道（防空/地面直射命中=HIT、散布/曲射落点=SCATTER、暴击=CRIT、狙击
R-02=SNIPER、航空=AIR——⑤块起 CRIT/SNIPER 有了首批消费者；rng.py :56-64
〔**2026-10-07 D071 全拆批注**：暴击掷骰退役——CRIT 通道零消费者（通道号 3
冻结不回收=口子③，恢复 roll_crit 即用）；SNIPER 仍消费〕）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from .air import (PHASE_COMBAT, PHASE_DEPLOY, PHASE_SETTLE, AircraftInstance,
                  aircraft_tick, air_recon_step, cmd_air_airdrop, cmd_air_alt,
                  cmd_air_call, cmd_air_disengage, cmd_air_engage_air,
                  cmd_air_move, cmd_air_patrol, cmd_air_rtb, cmd_air_strike,
                  is_aircraft_alive)
from .combat import (COMBAT_STYLE_MELEE, COMBAT_STYLE_SNIPER, aim_factor_bp,
                     aura_bonus_bp, damage_mult_permille, inject_suppression_area,
                     mark_resupply_if_needed, morale_acc_factor_bp, needs_resupply,
                     penetration_at, release_tow_if_involved, reload_factor_bp,
                     resolve_blast, resolve_hit, start_tow, stop_tow)
from .geom import approach_deg_of, angle_diff, dist_cm, step_toward
from .movement import (auto_approach_waypoint, issue_move, nearest_on_segment,
                       rotate_step, system_move_dispatch)
from .pathfind import find_path, road_at, terrain_speed_tile_bp
from .rng import Channels
from .sensing import (point_in_friendly_vision, system_sensing,
                      terrain_sensing_channels)
from .tables import BalanceConfig, CONFIG
from .types import (Armor, AuraKind, Building, DeployState, DamageType,
                    ElementInstance,
                    ElementTemplate, ElementType, FireMission, FireMissionForm,
                    FormationShape, MarkLevel, Mode, MoraleState, MovementClass,
                    MoveCmd, MoveMode,
                    MountRequest, ReverseCmd, SalvoMode, SmokeZone, Stance,
                    TargetDomain,
                    TowState, TowStopReason, Trajectory, UnitFlag, UnitInstance,
                    UnitTemplate, UnitType, WeaponState, WState)


# ── §D.6 WORLD 最小组装（aa_roster/beacon_by_unit 等承载）──

@dataclass
class PlayerState:
    """§D.4 玩家态最小集（航空消费面：air_points/air_cooldowns/deck_slots）。"""
    index: int
    team: int
    points: int = 1000
    air_points: int = field(default_factory=lambda: CONFIG.air_budget_base)  # D038 方案A占位
    air_cooldowns: dict = field(default_factory=dict)
    deck_slots: list = field(default_factory=list)
    spawn_queue: list = field(default_factory=list)
    spawn_serial: int = 0         # 出牌序记账（§D.6 未列；只增不减。2026-10-03 拍板：
                                  # 出生点不再随序偏移——纯计账槽保留）


@dataclass
class DeckSlot:
    """§D.6 :238 DeckSlot {template, copies_left}——卡组一命制余量（air.py 装机扣份/
    回收退份按 .template/.copies_left 鸭子消费，本类与 SimpleNamespace 槽互通）。"""
    template: object
    copies_left: int


@dataclass
class Objective:
    """§D.6 :231 Objective {id, pos, radius_cm, owner}——owner None=无主。"""
    id: int
    pos: tuple[int, int]
    radius_cm: int
    owner: int | None = None


@dataclass(frozen=True)
class Settlement:
    """D031 结算裁决记录（挂 update_phase 迁入结算拍，存 world.result；§D.6 未列的
    实现记账载体）。2026-10-03 拍板：无平局四链——winner 恒非 None。"""
    winner: int
    obj_counts: tuple      # 各队占点分（按 players 队序去重）
    unit_scores: tuple     # 各队剩余地面单位分值（Σ template.cost）
    hp_totals: tuple       # 各队剩余地面单位总血量（兜底链第三级证据；cost=0 箱不计）


# SmokeZone 2026-10-02 ⑤块迁 types.py（§D.6 :222 三字段口径 +radius_cm；上方
# import 再出口——test_integration 等 `from sovs.sim.tick import SmokeZone` 不变）。


@dataclass
class Projectile:
    """地面弹丸（字段名对齐 air.AirProjectile 冻结语义——§F4 :843-845 Projectile 元组；
    pen_bonus=§F4 :790 select_profile 档案位（v1.7 :219 Projectile 携 profile+pen_bonus——
    本仓内联进既有 damage_type/damage/blast_cm 三字段 + 本默认位，弹丸口径见登记表））。"""
    shooter: object
    weapon: object
    damage_type: object
    damage: int
    blast_cm: int
    pos: tuple[int, int]
    dest: tuple[int, int]
    speed_cm_tick: int
    trajectory: object
    hit_target: object
    will_hit: bool
    top_attack: bool = False
    pen_bonus: int = 0


@dataclass(slots=True, eq=False)
class IntelCircle:
    """§D.6 :223-224 R-03 声测定位圈（冻结精度，不撤销）。键=(team, source_unit)
    upsert（v1.5 C4：同炮更新其圈、多炮多圈共存）；圈粒度=开火单位（连级）。
    写者=sonar_step（§F3，未实现）；读者=fire_at 盲射声测圈叠加（:928-929）。"""
    team: int
    source_unit: object
    center: tuple[int, int]
    radius_cm: int


@dataclass(slots=True, eq=False)
class SoundTrack:
    """§D.6 :226-227 声测痕迹（v1.5 C4：每 (侦听队, 开火单位) 一条；
    last_fire_tick=最近开火 tick——sonar_hold_ticks 增长窗口判据）。
    写者=upsert_sound_track（§F3 :651-659）；读者=sonar_step（未实现）。"""
    listening_team: int
    unit: object
    pos: tuple[int, int]
    accum: int
    last_fire_tick: int


# ── §D.7 命令集（命令驱动；回放 = 种子 + 命令流）──
# 〔2026-10-07 命令族收口块：MoveCmd 定义迁 types.py（ReverseCmd 归一化须在
#    movement.issue_move 构造 MoveCmd——movement→tick 反向导入边 2026-10-06 评审
#    明令禁止；本模块顶部 import 再出口，`from sovs.sim.tick import MoveCmd`
#    导入面不变），ReverseCmd 同址 types.py；CancelCmd 本节新增（处理体/分派支
#    tick 侧自足）。〕

@dataclass(frozen=True)
class StopCmd:
    """§D.7 停止令——MOVEMENT_PSEUDOCODE_v1.2 §2.2 HaltCmd 语义（MV-B-18 已定）：
    清航点+复位模式+移出 command_queue 中全部移动令条目（MoveCmd/ReverseCmd——
    保动作令），stance 不动。
    （CancelCmd 全清变体已落地——2026-10-07 命令族收口块，见下方。）"""
    unit: object


@dataclass(frozen=True)
class CancelCmd:
    """MOVEMENT_PSEUDOCODE_v1.2 §2.2 :121 取消令（2026-10-07 命令族收口块落地——
    MV-B-18 另半"cancel=全清"）：清航点+复位模式+清**整个** command_queue（动作令
    一并清，v1.3 :160 字面）+清进行中 pivot（PB-51「停止令停整个移动族」超集语义
    对齐 cmd_halt）+清炮击任务体 fire_mission（发起人任务块口径「队列+动作令+
    任务体」全清——超出 v1.3 :160 字面半步，MOVEMENT v1.3 变更记录留痕）；stance
    不动（与 SetStanceCmd/ToggleAmbushCmd 区隔——MV-B-18 边界）；ROUTED 拒（对齐
    cmd_halt 先例：溃逃期清链等效失控干预，溃逃航点唯一清写点=system_morale
    重整拍）。"""
    unit: object


@dataclass(frozen=True)
class PivotCmd:
    """PB-51 原地转向令（2026-10-04 拍板纳入——断箭 N17 neutral steering/映射 §五.9；
    推翻 MOVEMENT_PSEUDOCODE_v1.2 §2.13 reject 的静止分支：「静止车体改朝向」不再即时，
    耗时=角度差÷类分档速率 cfg.pivot_rate_deg_per_tick——履带快于轮式，数值占位
    N17/N15 低置信来源标注见 tables.py）。处理体 cmd_pivot：停车（HaltCmd 语义）后
    写 unit.pivot_to；期间禁射（fire_permitted ⑧）/SIDE 暴露（GAP-25 rotating 维持，
    仅 fire_arc<360 模板生效——方案6 现状口径）。MV-B-05「到达朝向指定令」仍 defer
    （近亲不同机制：那是 MoveCmd 增参、本令是独立动作令——登记表 TODO）。"""
    unit: object
    facing_deg: int


@dataclass(frozen=True)
class FormationCmd:
    """MOVEMENT_PSEUDOCODE_v1.2 §2.2 :121 FormationCmd{unit(s), shape}——队形选择
    （GAP-15 adopt 半；2026-10-06 PB-56 批③ Formation 族块落地）。§D.7 22 类之外
    的 MOVEMENT 侧命令（登记表 MOVEMENT 余量条目退役）；units=组下令列表（§2.2
    :151-152「组下令=逐单位写」——多单位一字段承载）。无 REJECT 门（独立入口）；
    NONE=复位现状同点堆叠（MV-B-19）。消费端 make_formation_fn（movement.py §2.8
    三表）既有。编组速度同步（§2.9）不属本令——issue_group_move 为 UI 层聚合直调
    入口非命令类型。"""
    units: list
    shape: object


@dataclass(frozen=True)
class DeployCmd:
    unit: object


@dataclass(frozen=True)
class PackCmd:
    unit: object


@dataclass(frozen=True)
class SetModeCmd:
    """D065 三模式/火炮双职（element 粒度）。"""
    element: object
    mode: object


@dataclass(frozen=True)
class PurchaseCmd:
    """仅盲部署 phase（cmd_purchase 门，§F7 :1374）。"""
    player: object
    template: object


@dataclass(frozen=True)
class FireMissionCmd:
    """§D.7 曲射任务令（form: POINT|LINE|CREEP；point 与 line 二选一按 form）。"""
    unit: object
    form: object
    point: object = None        # (cm, cm)——form=POINT
    line: object = None         # [(cm,cm), (cm,cm)]——form=LINE
    ammo_mult: int = 1          # 1..3
    salvo_mode: object = None   # FULL|HALF
    creep_speed: int = 0


@dataclass(frozen=True)
class CancelFireMissionCmd:
    unit: object


@dataclass(frozen=True)
class SmokeCmd:
    """烟弹发射入口（§F6 cmd_smoke :1274）。PB-53（2026-10-04 拍板纳入——断箭 N32/
    映射 §五.19；复用本命令类不另立新类型）：分派支落**自卫烟幕路径**（cmd_smoke——
    发数门→冷却门→受令耗发+N32 部署延迟后以元素当前位置为心落 SmokeZone，point
    不消费）。§F6 武器烟弹路径（查 SMOKE 武器档+射程门③A+SCATTER 散布+耗弹装填+
    声测喂入）未落地——两体系并存（原「烟幕=迫击炮定量烟弹 D044」口径之扩充，
    映射 §五.19/登记表留痕）。"""
    element: object
    point: object


@dataclass(frozen=True)
class SetStanceCmd:
    unit: object
    stance: object


@dataclass(frozen=True)
class ToggleAmbushCmd:
    unit: object


@dataclass(frozen=True)
class SprintCmd:
    """写 unit.sprint_until = now + sprint_duration_ticks（方案14；types.py 唯一写点——
    cmd_sprint 处理体已落地，2026-10-04 命令层块）。禁射联动=system_timers AIMING
    冻结门 + fire_permitted 索敌门（§2.10-8/D072）。机制层无兵种门（哪些卡配冲刺=
    数据卡配置侧）；**冷却门已接线（2026-10-07 发起人拍板采纳）**——cmd_sprint 增
    `now < sprint_until + cfg.sprint_cooldown_ticks → REJECT`（sprint_until 语义
    不变、契约⑧速度式不动；初值 0=从未冲刺哨兵豁免首冲）；破压制已落地（2026-10-04
    拍板 MV-B-04 改B：开跑拍压制×sprint_suppress_cut_bp=5000 减半——断箭式「冲刺
    脱离压制」，cmd_sprint 承载）。"""
    unit: object


@dataclass(frozen=True)
class GarrisonCmd:
    unit: object
    building: object


@dataclass(frozen=True)
class UnGarrisonCmd:
    unit: object


@dataclass(frozen=True)
class MountCmd:
    """v1.6 ㉑A：请求体=班元素列表——逐班选最少挂载载具并逐班占座。"""
    squad_elements: list
    carrier_unit: object


@dataclass(frozen=True)
class DismountCmd:
    squad_unit: object


@dataclass(frozen=True)
class TowCmd:
    """v1.3：元素级（审查#12）——单卡 2 车并拖/拖单门炮可表达。"""
    tower_elements: list
    towed_element: object


@dataclass(frozen=True)
class UntowCmd:
    element: object


@dataclass(frozen=True)
class AttackCmd:
    """直射指定目标（含建筑——审查#5；cmd_attack 见 §F4）。"""
    element: object
    target: object


@dataclass(frozen=True)
class SetSniperCoverCmd:
    """写 world.cover_by_target（方案9）。"""
    sniper_unit: object
    target_unit: object


@dataclass(frozen=True)
class SetAirdropBeaconCmd:
    """写 world.beacon_by_unit（方案9）。"""
    unit: object
    pos: object


@dataclass(frozen=True)
class BuySuppliesCmd:
    truck_element: object
    rounds: int
    medical: int


# ── AIR_UNITS_PSEUDOCODE_IMPL_v1.4 §D.5 航空命令集（9；命令驱动——AI 虚拟玩家
#    走同一接口，契约⑦。2026-10-07 空中闭环·块1：命令类+分派支落地——处理体
#    air.py cmd_air_* 族 2026-10-01 行为层既有，本块只通命令流。payload 键口径
#    ={BOMB,SUPPLY,PARATROOP}：§D.5 的 supply_rounds/supply_medical 双键已随
#    2026-10-03「弹药/医疗一池按重量计」拍板并轨为 SUPPLY 重量单键——地面
#    buy_supplies :1225 换写同族先例，air.py cmd_air_call 既有口径照读）──

@dataclass(frozen=True)
class AirCallCmd:
    """呼叫航空器（§F1 cmd_air_call：租借经济五门+弹药初始化+INBOUND 进场）。"""
    player: object
    template: object
    payload: dict


@dataclass(frozen=True)
class AirMoveCmd:
    """航路改航（§F2 cmd_air_move：非 DOGFIGHT/RTB、RUN/EGRESS 不可转向）。"""
    aircraft: object
    path: list


@dataclass(frozen=True)
class AirPatrolCmd:
    """绕点盘旋（§F2 cmd_air_patrol——GDD-02 v1.9 B-20 CAP 操作入口）。"""
    aircraft: object
    center: tuple[int, int]
    radius: int


@dataclass(frozen=True)
class AirAltCmd:
    """高度层变更（§F2 cmd_air_alt——B-29：不入任务令门族，RTB 亦允许）。"""
    aircraft: object
    tier: int


@dataclass(frozen=True)
class AirStrikeCmd:
    """对地攻击（§F3 cmd_air_strike：BOMB|STRAFE 两档，attack run 状态机）。"""
    aircraft: object
    target: tuple[int, int]
    weapon: str


@dataclass(frozen=True)
class AirAirdropCmd:
    """空投（§F3 cmd_air_airdrop：TRANSPORT 补给/空降兵）。"""
    aircraft: object
    drop_point: tuple[int, int]


@dataclass(frozen=True)
class AirEngageAirCmd:
    """转对空开关（§F4 cmd_air_engage_air：开拨实战门+带弹丢弹 D015）。"""
    aircraft: object
    engage: bool


@dataclass(frozen=True)
class AirDisengageCmd:
    """缠斗脱离（§F4 cmd_air_disengage：tail 掷骰，R-20）。"""
    aircraft: object


@dataclass(frozen=True)
class AirRTBCmd:
    """返场（§F2 cmd_air_rtb——B-22 不可逆、B-29 弃权特许）。"""
    aircraft: object


@dataclass
class World:
    """§D.6 WORLD 最小容器（零渲染依赖；回调默认实现=记录桩/场外点，见 TODO 登记表）。"""
    tick: int = 0
    phase: int = PHASE_COMBAT
    phase_start_tick: int = 0    # 相位起点记账（§D.6 未列槽——时长制状态机实现记账；
                                 # 注入 phase 自构造 tick 起满时长，不被绝对 tick 改写）
    units: list = field(default_factory=list)
    aircraft: list = field(default_factory=list)
    projectiles: list = field(default_factory=list)
    players: list = field(default_factory=list)
    command_queue: list = field(default_factory=list)    # §D.7 命令流（consume_commands 清空）
    aa_roster: list = field(default_factory=list)          # §D.6 对空名单（方案2，运行时不重建）
    beacon_by_unit: dict = field(default_factory=dict)     # §D.6 空投信标旁表（方案9）
    smoke_zones: list = field(default_factory=list)
    forest_tiles: frozenset = frozenset()   # §2.12 森林瓦片旁挂集 {(ix,iy)}——sensing
                                 # 遮蔽通道数据源（in_forest/forest_m——PB-53 留待项②
                                 # 收口/GAP-27，2026-10-07 感知接线块）；写侧=
                                 # map_loader.apply_map（挂图单点）；缺省空=无林
                                 # （森林两通道 None，lean/stub 场景逐位不变）
    tow_pairs: list = field(default_factory=list)
    cloud_tier: int = 0
    next_aircraft_id: int = 1
    next_unit_id: int = 1
    rng: Channels = None
    map_center: tuple[int, int] = (500000, 500000)
    map_extent: tuple[int, int] = (1000000, 1000000)
    terrain: object = None    # §2.14 地图层（TerrainLayer|None——None=未接入→三谓词 stub 口径；
                              # MOVEMENT v1.2 §2.14/§9:576 登记，⑦块落地：算法本体 pathfind.py）
    path_cache: dict = field(default_factory=dict)   # §2.14 find_path 结果 LRU 缓存（§D.6 未列
                              # 实现记账槽——PB-10 随消费侧落地，2026-10-04 寻路接线块：键含
                              # 地形内容指纹（terrain_fingerprint）与展开上限
                              # （pathfind_max_expansions——PB-58 限幅，cap 变更=全量换键）
                              # →地形/图界突变天然换键失效；上界=cfg.pathfind_cache_entries；
                              # 零行为差——详见 pathfind.py）
    await_resupply: list = field(default_factory=list)   # §D.6 方案19 待补给集合（system_supply 尾部自清理）
    intel_circles: list = field(default_factory=list)  # §D.6 :223 R-03 声测圈（写者 sonar_step 未实现）
    sound_tracks: list = field(default_factory=list)   # §D.6 :226 声测痕迹（写者 upsert_sound_track）
    mount_requests: list = None   # §D.6 ⑦ 上车请求表（方案12 惰性：首条请求才建，None=无请求非异常）
    objectives: list = field(default_factory=list)  # §D.6 :231 占点列表（system_objectives 写 owner）
    buildings: list = field(default_factory=list)   # §D.6 :243 建筑表（⑤块：hit_building/collapse_building 消费；写侧=PB-57 地图装配
                              # map_loader.apply_map 已接[2026-10-06]、cmd_garrison 驻楼引用已接[2026-10-06
                              # 驻楼命令块]——合成建筑并存供单测）
    cover_by_target: dict = field(default_factory=dict)  # §D.6 :246 反狙击掩护旁表（方案9 插入序 map——
                                   # 键型=unit.id：UnitInstance mutable dataclass 不可哈希，v1.7 键型 unit 的
                                   # 实现适配；值=掩护者 unit 列表，消费=键存在性布尔；写侧 cmd_set_sniper_
                                   # cover 已接〔2026-10-06 PB-56 批③〕，注销 unregister_unit_refs 既有）
    result: object = None    # D031 结算裁决（§D.6 未列记账槽：迁入结算拍由 update_phase 写入）

    def air_entry_point(self, team: int) -> tuple[int, int]:
        """己方底边场外点（tests/test_air_behavior.py mkworld 惯例；air_map_margin_cm 缓冲带）。"""
        h = self.map_extent[1]
        return (self.map_center[0],
                -CONFIG.air_map_margin_cm if team == 0 else h + CONFIG.air_map_margin_cm)

    def rtb_exit_point(self, team: int) -> tuple[int, int]:
        return self.air_entry_point(team)

    # ── §2.14 地图层三谓词（MOVEMENT_PSEUDOCODE_v1.2 §2.14——算法本体 pathfind.py，
    #    ⑦块落地；terrain=None 时走 stub 口径：road_at=False / tile_bp=None /
    #    find_path=直线直填 RETURN [to]——AMB-8）──

    def road_at(self, pos) -> bool:
        """TERRAIN[tile].on_road（§2.6 强行军消费——system_move_dispatch 增量⑥
        调用方已接，2026-10-04 命令层块）。"""
        return road_at(self, pos)

    def terrain_speed_tile_bp(self, pos, movement_class):
        """TERRAIN[tile].speed_bp[class]（§2.4 增量⑦消费——dispatch 调用方已接，
        2026-10-04 命令层块）；None=类级缺省（tables.terrain_speed_bp(cls, None)）。"""
        return terrain_speed_tile_bp(self, pos, movement_class)

    def find_path(self, frm, to, movement_class, prefer_road: bool):
        """§2.14 寻路（from 为 Python 关键字——形参名 frm）：terrain 未接入→[to]；
        接入→整型 A*（堆 (f, 插入序号) 决胜/DIR8 固定序/禁切角/共线化简——详见
        pathfind.py docstring 与登记表 discrepancies）；展开数超
        cfg.pathfind_max_expansions（PB-58 限幅，2026-10-06——0=不限幅）同款
        直线兜底。A* 结果经 self.path_cache LRU 缓存（PB-10——2026-10-04 寻路
        接线块随消费侧落地；键含地形内容指纹与展开上限，零行为差）。零掷骰。"""
        return find_path(self, frm, to, movement_class, prefer_road)

    def spawn_paratroop(self, tpl, team: int, player_index: int, pos) -> None:
        """AIR §F6 :610-619 空降兵落地回调（air.py resolve_airdrop——D017 落地即地面
        一命单位；2026-10-02 ⑥块自记录桩转真实现）。instantiate=make_unit+add_unit
        （AMB3-06：构造+入 world.units 与地面 spawn_step/spawn_airdrop_crate 冻结用法
        同构；aa_roster 名单登记由 add_unit 承载——方案2）；渗透计时 spawn_step :1393
        同款按相位置（canInfiltrate 卡：实战 infiltration_ticks、否则 0——空投门
        实战才放行，盲部署分支为不可达兜底）。deck 份装机时已扣（B-06/B-12
        air.py 装机即扣份）——此处不重复扣。零掷骰。"""
        unit = add_unit(self, make_unit(self, tpl, team, player_index, pos))
        if tpl.flags & UnitFlag.CAN_INFILTRATE:
            unit.infiltration_timer = (CONFIG.infiltration_ticks
                                       if self.phase == PHASE_COMBAT else 0)

    def spawn_airdrop_crate(self, team: int, pos, supply_weight_g: int) -> None:
        """§F6 :1343-1354 一次性补给箱落地（air.py resolve_airdrop 契约④调用；方案16：
        R-21 航空侧调用接口；2026-10-02 ⑥块自记录桩转真实现；2026-10-03 拍板：载荷
        一池化——弹药/医疗并成一个补给重量）。instantiate=
        make_unit+add_unit（aa_roster 天然不入——无 AIR 武器且 optics_air_cm=0，:1353）；
        elements[0].mode=CARGO、supply_weight_g 预填；不可移动
        （speed_tier=0——§D.0 速度表 [0]=0）；被摧毁走 destroy_element 常规级联
        （物资随毁清零）。crate 无归属玩家（player_index 不入 UnitInstance——R-21
        同队拾取门按 team 判）。零掷骰。"""
        unit = add_unit(self, make_unit(self, airdrop_crate_template(CONFIG),
                                        team, 0, pos))
        e = unit.elements[0]
        e.mode = Mode.CARGO
        e.supply_weight_g = supply_weight_g


def make_world(seed: int, *, phase: int = PHASE_COMBAT, tick: int = 0,
               size_cm: tuple[int, int] = (1000000, 1000000),
               players_per_team: int = 1) -> World:
    """最小 World 工厂（两队制；PCG32 分通道 seed）。"""
    w = World(rng=Channels(seed), tick=tick, phase=phase, phase_start_tick=tick,
              map_extent=size_cm,
              map_center=(size_cm[0] // 2, size_cm[1] // 2))
    for _t in (0, 1):
        for _i in range(players_per_team):
            w.players.append(PlayerState(index=len(w.players), team=_t))
    return w


def make_unit(world: World, template: UnitTemplate, team: int, player_index: int,
              pos: tuple[int, int]) -> UnitInstance:
    """§F7 spawn_step instantiate 最小集：元素/武器弹药满编（weapon_states ← 模板序）+
    受限弹药档实例计数深拷贝（§D.5#11 M16：restricted_left ← template.restricted_profiles，
    每门独立——select_profile 读/减此副本）。未承载：开局车载默认形态（:1389-1392）/
    渗透计时起算（:1393-1399）/队形偏移。PB-53（2026-10-04）：+self_smoke_left ←
    template.self_smoke_charges（自卫烟幕运行时余量初始化——ammo_left 满编同口径；
    ready/pop 两槽走 dataclass 缺省）。"""
    unit = UnitInstance(id=world.next_unit_id, team=team, template=template, pos=pos)
    world.next_unit_id += 1
    for i, et in enumerate(template.element_templates, start=1):
        e = ElementInstance(id=i, unit=unit, template=et, pos=pos, hp_current=et.hp_max,
                            self_smoke_left=et.self_smoke_charges)
        for wt in et.weapons:
            e.weapon_states.append(WeaponState(
                template=wt, ammo_left=wt.ammo_base,
                restricted_left=tuple(rp[0] for rp in wt.restricted_profiles)))
            # ↑ §D.5#11 M16：受限弹药档实例计数深拷贝（每门独立——select_profile 读/减此副本）
        unit.elements.append(e)
    return unit


def _aa_eligible(template: UnitTemplate) -> bool:
    """§F7 :1400-1401 名单登记条件：任一武器 target_mask&AIR 或 optics_air_cm>0。"""
    if template.optics_air_cm > 0:
        return True
    for et in template.element_templates:
        for wt in et.weapons:
            if wt.target_mask & TargetDomain.AIR:
                return True
        for wt in (et.mounted_armament or ()):
            if wt.target_mask & TargetDomain.AIR:
                return True
    return False


def add_unit(world: World, unit: UnitInstance) -> UnitInstance:
    """world.units 注册 + aa_roster 登记（部署初始化=首批 spawn，运行时不重建——方案2）。
    返回注册后的 unit（组装惯例：u = add_unit(w, make_unit(w, tpl, ...))）。"""
    world.units.append(unit)
    if _aa_eligible(unit.template):
        world.aa_roster.append(unit)
    return unit


def airdrop_crate_template(cfg: BalanceConfig) -> UnitTemplate:
    """§F6 :1343-1354 一次性补给箱模板（非卡组卡面——机制层内置、不入卡库/不占
    template_id 唯一性域；spawn_airdrop_crate 消费）。数据硬要求照 :1344-1349 逐条：
    speed_tier=0（§D.0 速度表 [0]=0——不可移动）、装甲 0、HP 小可摧毁（=cfg.
    airdrop_crate_hp，"小"未定标——数值占位见登记表）、无行为 flags 且 hasSupply
    位必配（GAP-21/Z-6：漏配则物资槽不分配、拾取链静默失效）、supply_radius_cm
    =8000（:1349/:1350，D.1#20 默认同值）。结构派生位：MECH/VEHICLE（装备物
    HARD——⑲A 狙击剔 MECH，箱子不被狙击）；category=4 防空后勤（非侦察——R-01
    校准不触发）；cost=0（非购入单位——D031 剩余单位分值不计箱子）；mode_set=
    CARGO 位（fire_permitted ⑥ 载货不作战；无武器恒哑火）。"""
    return UnitTemplate(
        template_id=0,                       # 内部记账位（非卡库卡面）
        name="空投补给箱",
        category=4,                          # AA_LOGISTICS
        cost=0,
        element_templates=(ElementTemplate(
            element_type=ElementType.VEHICLE,
            unit_type=UnitType.MECH,
            hp_max=cfg.airdrop_crate_hp,
            armor_ke=Armor(0, 0, 0, 0),      # 装甲 0（:1344；armor<=0 → 1000‰ 全伤）
            armor_he=Armor(0, 0, 0, 0),
        ),),                                 # weapons=()——无行为（:1344）
        optics_ground_cm=0,                  # 不可观察（无行为）
        stealth_base=0,                      # 开阔地箱体最易发现档（未定标占位）
        speed_tier=0,                        # §D.0 速度表 [0]=0（:1344 不可移动）
        movement_class=MovementClass.WHEEL,
        flags=UnitFlag.HAS_SUPPLY,           # GAP-21 必配（:1345-1347）
        supply_radius_cm=8000,               # :1349/:1350 数据硬要求
        mode_set=1 << Mode.CARGO,
    )


# ── §F8 update_phase（:1413-1421）+ consume_commands（:1425-1426 命令驱动）──

def update_phase(world: World, cfg: BalanceConfig = CONFIG) -> None:
    """§F8 :1413-1421：按 phase_ticks 推进相位——盲部署(600)→实战(13200)→
    结算（2026-10-03 发起人拍板：部署 90s→60s、取消开局禁火（D007/D008 废止）、
    实战时长不变；10Hz 换算 60s/22min）。相位占据整数拍：
    自迁入拍起第 duration 拍仍属原相位、第 duration+1 拍迁出（盲部署恰占 tick 1..600）。
    本 tick 迁入实战时：在场存活 canInfiltrate 单位 infiltration_timer=infiltration_ticks
    （600——渗透 60s 从实战期起算，v1.6 ④A 拍板；spawn 侧配合见 §F7 :1393-1399）。
    本 tick 迁入结算时：D031 裁决（v1.7 :1415 仅写"→结算"无函数体——按 GDD-00 :137/:196
    推定：占点数多者胜 → 平局比剩余地面单位分值 → 仍同则平局；见 resolve_settlement）。"""
    while world.phase != PHASE_SETTLE:
        duration = cfg.phase_ticks[world.phase]
        if world.tick - world.phase_start_tick <= duration:
            break
        world.phase_start_tick += duration
        world.phase += 1
        if world.phase == PHASE_COMBAT:                       # 本 tick 迁入实战
            for u in world.units:
                if u.alive and (u.template.flags & UnitFlag.CAN_INFILTRATE):
                    u.infiltration_timer = cfg.infiltration_ticks
        elif world.phase == PHASE_SETTLE:                     # 本 tick 迁入结算（D031）
            world.result = resolve_settlement(world)


def queue_command(world: World, cmd) -> None:
    """§D.7 命令流入口（AI/测试虚拟玩家接口；回放=种子+命令流）：入队后由本 tick
    （若在 world_tick 外入队则下一拍）consume_commands 全部落地。"""
    world.command_queue.append(cmd)


def consume_commands(world: World, cfg: BalanceConfig = CONFIG) -> None:
    """§F8 :1425-1426：命令驱动——本 tick 入队命令全部落地（FIFO 插入序，旁表 dict 同款
    确定性口径）。零掷骰：命令层不触碰任何 PCG32 通道。"""
    while world.command_queue:
        cmd = world.command_queue.pop(0)
        _dispatch_command(world, cmd, cfg)


def _dispatch_command(world: World, cmd, cfg: BalanceConfig) -> None:
    """§D.7 分派骨架（:256-268 全集 22 类）：命令类型 → cmd_* 处理体。已落地：
    PurchaseCmd→§F7 cmd_purchase；MoveCmd/StopCmd/SprintCmd→MOVEMENT_PSEUDOCODE_v1.2
    §2.2 命令层（2026-10-04 命令层块——issue_move 外部通道/HaltCmd 语义/sprint_until
    写点）；PivotCmd→PB-51 cmd_pivot（2026-10-04 原地转向块——停车+写 pivot_to）；
    SmokeCmd→§F6 cmd_smoke 自卫烟幕路径（2026-10-04 PB-53——发数门→冷却门→部署延迟
    落烟；§F6 武器烟弹路径仍未落地）；
    AttackCmd→§F4 cmd_attack（2026-10-06 PB-56 批① 作战链命令块——门序①-⑪ 逐条，
    玩家令直射指定目标含建筑）；SetModeCmd→§F6 cmd_set_element_mode/
    ToggleAmbushCmd→§F4 cmd_toggle_ambush/SetStanceCmd→§D.7 最小写点
    （2026-10-06 PB-56 批① 作战链命令块·余三命令——SetMode 写点序①-⑦ 含
    M21 半清除、ToggleAmbush=R-12 伏击开关唯一写点、SetStance 勘察处置案 a）；
    SetSniperCoverCmd/BuySuppliesCmd（2026-10-06 PB-56 批③ 支援链命令块）；
    FormationCmd（MOVEMENT v1.2 §2.2——§D.7 外命令，2026-10-06 PB-56 批③
    Formation 族块，cmd_formation 逐单位写槽）；SetAirdropBeaconCmd→cmd_set_
    airdrop_beacon（2026-10-06 收口补落——§D.7 22 类 22/22 全落地，登记表勘正在案）；
    ReverseCmd→issue_move 外部通道+CancelCmd→cmd_cancel（2026-10-07 命令族收口块
    ——MOVEMENT §2.2 命令族余量就此清零：ReverseCmd 归一化在 issue_move 门3 后门4 前
    `cmd ← MoveCmd{path=[dest], mode=REVERSE, queue=FALSE}`，CancelCmd=MV-B-18 另半
    全清变体）；未知类型抛
    TypeError（命令流完整性保护——已登记命令集之外的类型不得静默入流）。"""
    if isinstance(cmd, MoveCmd):
        issue_move(world, cfg, cmd, handoff=False)   # §2.2 外部通道（queue 位在此内分派）
    elif isinstance(cmd, ReverseCmd):
        issue_move(world, cfg, cmd, handoff=False)   # §2.2 :142 特化归一在 issue_move 内
                                                     # （门3 后门4 前——归一化先于门4）；
                                                     # 门4/增量②④ 消费端速度链块已活
    elif isinstance(cmd, StopCmd):
        cmd_halt(cmd.unit)                           # §2.2 HaltCmd 语义（MV-B-18）
    elif isinstance(cmd, CancelCmd):
        cmd_cancel(cmd.unit)                         # §2.2 :160 全清变体（MV-B-18 另半
                                                     # ——清航点+复位模式+清整个队列+清
                                                     # pivot+清任务体；stance 不动）
    elif isinstance(cmd, PivotCmd):
        cmd_pivot(cmd.unit, cmd.facing_deg)          # PB-51 原地转向（2026-10-04——停车+写 pivot_to）
    elif isinstance(cmd, FormationCmd):
        cmd_formation(cmd.units, cmd.shape)          # MOVEMENT v1.2 §2.2 :151-152（PB-56
                                                     # 批③ Formation 族块，2026-10-06——
                                                     # 组下令逐单位写 formation_shape
                                                     # 槽、无 REJECT 门；消费端
                                                     # make_formation_fn 三表既有）
    elif isinstance(cmd, DeployCmd):
        cmd_deploy(world, cmd.unit)                     # §F6 :1072（PB-56 批②
                                                        # 机动链命令块·拖曳展开，
                                                        # 2026-10-06——MOBILE→
                                                        # DEPLOYING 计时/GAP-09
                                                        # ELIF 重展开/清旗排除
                                                        # TOWED；消费端
                                                        # system_timers ① 展开
                                                        # 收装计时既有）
    elif isinstance(cmd, PackCmd):
        cmd_pack_or_move(world, cmd.unit)               # §F6 :1116（PB-56 批②——
                                                        # DEPLOYED→PACKING 计时/
                                                        # DEPLOYING→MOBILE 作废；
                                                        # MoveCmd 触发面已接线
                                                        # 2026-10-07 拍板=采 IMPL
                                                        # 字面，落点 movement.
                                                        # issue_move 效果点，见
                                                        # docstring）
    elif isinstance(cmd, SetModeCmd):
        cmd_set_element_mode(world, cmd.element, cmd.mode)      # §F6 :1193（PB-56 批①
                                                               # 作战链命令块·SetMode，
                                                               # 2026-10-06——写点序
                                                               # ①-⑦：资格门+TOW 解挂
                                                               # +CARGO 卸货+TRANSPORT
                                                               # 卸客+清挂起请求+M21
                                                               # 半清除；炮击任务令
                                                               # 双门的解锁钥匙）
    elif isinstance(cmd, PurchaseCmd):
        cmd_purchase(world, cmd.player, cmd.template, cfg)          # §F7 :1374（仅盲部署 phase）
    elif isinstance(cmd, FireMissionCmd):
        cmd_fire_mission(world, cmd.unit, cmd.form,
                         cmd.point if cmd.form is FireMissionForm.POINT else cmd.line,
                         cmd.ammo_mult, cmd.salvo_mode, cmd.creep_speed, cfg)  # §F4 :960
    elif isinstance(cmd, CancelFireMissionCmd):
        cmd_cancel_fire_mission(world, cmd.unit)                # §F4 :972
    elif isinstance(cmd, SmokeCmd):
        cmd_smoke(world, cmd.element, cmd.point, cfg)      # §F6 :1274（PB-53 自卫烟幕路径，
                                                           # 2026-10-04——武器烟弹路径未落地见 TODO）
    elif isinstance(cmd, SetStanceCmd):
        cmd_set_stance(cmd.unit, cmd.stance)                     # §D.7 :261 最小写点
                                                               # （PB-56 批①，2026-10-06
                                                               # ——v1.7 仅字段定义无
                                                               # 处理体，勘察处置案 a：
                                                               # 单写点+枚举校验无门，
                                                               # 行为门全在消费侧
                                                               # fire_permitted ②）
    elif isinstance(cmd, ToggleAmbushCmd):
        cmd_toggle_ambush(cmd.unit)                              # §F4 :874（PB-56 批①
                                                               # 作战链命令块·
                                                               # ToggleAmbush，2026-10-06
                                                               # ——R-12 伏击开关唯一
                                                               # 写点：资格门+手动退出
                                                               # 携首击加成+开启需静止）
    elif isinstance(cmd, SprintCmd):
        cmd_sprint(world, cmd.unit, cfg)                         # §D.0 :48/方案14（MOVEMENT §2.2）
    elif isinstance(cmd, GarrisonCmd):
        cmd_garrison(world, cmd.unit, cmd.building)    # §F6 :1248（PB-57 驻楼命令块，
                                                       # 2026-10-06——兵种/容量两门+塌楼收口，
                                                       # 接受=双向引用写入）
    elif isinstance(cmd, UnGarrisonCmd):
        cmd_un_garrison(world, cmd.unit)               # §F6 :1253（PB-57——双向清理+楼旁落位）
    elif isinstance(cmd, MountCmd):
        cmd_mount(world, cmd.squad_elements, cmd.carrier_unit, cfg)   # §F6 :1137（PB-56
                                                               # 批② 机动链命令块·
                                                               # 上车，2026-10-06——
                                                               # ㉑A 逐班门序①-⑪，
                                                               # 建 MountRequest 入
                                                               # world.mount_requests，
                                                               # 消费端 ⑦
                                                               # mount_requests_step
                                                               # 既有；「旁」=同点位
                                                               # 可推翻拍板项见
                                                               # cmd_mount docstring）
    elif isinstance(cmd, DismountCmd):
        cmd_dismount(world, cmd.squad_unit)               # §F6 :1131（PB-56 批②
                                                          # 机动链命令块·下车，
                                                          # 2026-10-06——旁落位
                                                          # 同点位+跨卡 cargo_units
                                                          # 按身份移除）
    elif isinstance(cmd, TowCmd):
        cmd_tow(world, cmd.tower_elements, cmd.towed_element)   # §F6 :1228（PB-56
                                                        # 批② 机动链命令块·拖曳展开，
                                                        # 2026-10-06——GAP-10 同队门+
                                                        # 合法被拖对象门+D065 互斥门
                                                        # （载具须先 SetMode(TOW)）→
                                                        # start_tow 失败静默；建立
                                                        # TowPair/置 TOWING·TOWED/
                                                        # redeploy_needed/清炮击任务）
    elif isinstance(cmd, UntowCmd):
        cmd_untow(world, cmd.element)                   # §F6 :1242（PB-56 批②——
                                                        # 涉本元素拖曳对逐一
                                                        # stop_tow(VOLUNTARY)，
                                                        # GAP-24 元素级同构；无资格门）
    elif isinstance(cmd, AttackCmd):
        cmd_attack(world, cmd.element, cmd.target, cfg)    # §F4 :848（PB-56 批① 作战链
                                                           # 命令块，2026-10-06——门序①-⑪
                                                           # 逐条+建筑资格门，玩家令直射
                                                           # 拆楼链可达性闭环）
    elif isinstance(cmd, SetSniperCoverCmd):
        cmd_set_sniper_cover(world, cmd.sniper_unit, cmd.target_unit)   # §F6 :1258（PB-56
                                                        # 批③ 支援链命令块，
                                                        # 2026-10-06——资格/
                                                        # ⑳A 同队/存活/非自身
                                                        # 四门+1:1 替换语义，
                                                        # 写 cover_by_target
                                                        # 〔键=unit.id〕——
                                                        # 消费端 resolve_
                                                        # sniper_hit 减半乘区
                                                        # 既有，旁表唯一写者
                                                        # 就此补通）
    elif isinstance(cmd, SetAirdropBeaconCmd):
        cmd_set_airdrop_beacon(world, cmd.unit, cmd.pos)   # §F6 :1269（2026-10-06
                                                          # 收口补落——22 类最后一支）
    elif isinstance(cmd, BuySuppliesCmd):
        buy_supplies(world, cmd.truck_element, cmd.rounds, cmd.medical, cfg)   # §F6 :1215
                                                        # （PB-56 批③ 支援链
                                                        # 命令块，2026-10-06
                                                        #——hasSupply 载具门+
                                                        # 仅 CARGO 门+舱位/
                                                        # 载重三门，写 supply_
                                                        # weight_g〔2026-10-03
                                                        # 一池拍板换写〕——
                                                        # SetMode(CARGO)→
                                                        # BuySupplies→
                                                        # system_supply 装货
                                                        # 整链首次全通）
    elif isinstance(cmd, AirCallCmd):
        cmd_air_call(world, cmd.player, cmd.template, cmd.payload, cfg)   # AIR §F1
                                                        # （2026-10-07 空中
                                                        # 闭环·块1——九命令
                                                        # 分派支：§D.5 契约⑦
                                                        # 命令驱动，处理体
                                                        # air.py 行为层既有；
                                                        # B-18 无 phase 门）
    elif isinstance(cmd, AirMoveCmd):
        cmd_air_move(world, cmd.aircraft, cmd.path)    # AIR §F2（同上——RUN/EGRESS
                                                        # 直线段不可转向 GAP-28）
    elif isinstance(cmd, AirPatrolCmd):
        cmd_air_patrol(world, cmd.aircraft, cmd.center, cmd.radius)   # AIR §F2
                                                        # （B-20 CAP 操作入口）
    elif isinstance(cmd, AirAltCmd):
        cmd_air_alt(world, cmd.aircraft, cmd.tier)     # AIR §F2（B-29 微操特许）
    elif isinstance(cmd, AirStrikeCmd):
        cmd_air_strike(world, cmd.aircraft, cmd.target, cmd.weapon)   # AIR §F3
                                                        # （attack run 状态机）
    elif isinstance(cmd, AirAirdropCmd):
        cmd_air_airdrop(world, cmd.aircraft, cmd.drop_point)          # AIR §F3
                                                        # （空投两分支 §F6）
    elif isinstance(cmd, AirEngageAirCmd):
        cmd_air_engage_air(world, cmd.aircraft, cmd.engage)           # AIR §F4
                                                        # （D015 转对空丢弹）
    elif isinstance(cmd, AirDisengageCmd):
        cmd_air_disengage(world, cmd.aircraft, cfg)   # AIR §F4（tail 掷骰——
                                                        # 处理体掷 AIR 通道，
                                                        # 命令层自身零掷骰）
    elif isinstance(cmd, AirRTBCmd):
        cmd_air_rtb(world, cmd.aircraft)              # AIR §F2（B-22 不可逆）
    else:
        raise TypeError("unknown command type: %s" % type(cmd).__name__)


# ── MOVEMENT_PSEUDOCODE_v1.2 §2.2 命令层处理体（2026-10-04 命令层块；PB-12 双层：
#    世界级收件箱=consume_commands（§F8 :1425-1426，既有）→ 分派支真调用；
#    单位级队列=UnitInstance.command_queue（内部实现），consume_unit_commands 消费）──

def cmd_halt(unit) -> None:
    """§2.2 HaltCmd 处理体（StopCmd 分派支承载——MV-B-18 已定）：清航点 + 复位
    move_mode + 移出 command_queue 中全部移动令条目（MoveCmd/ReverseCmd——
    v1.3 :159 字面；ReverseCmd 并入过滤 2026-10-07 命令族收口块：归一化
    queue=FALSE 使 ReverseCmd 常规不入队，过滤为规格字面的防御位）；保动作令、
    stance 不动。
    PB-51（2026-10-04）：增清 unit.pivot_to——停止令停的是整个移动族动作，
    进行中原地转向一并中止（不转完即停）。halt 必须实际停住：若保留排队移动令
    则下一拍自动续走=halt 失效。士气块（2026-10-04）：ROUTED 期拒停——溃逃失控
    （D014 字面「失控」；溃逃航点唯一清写点=system_morale 重整拍，玩家不得截停）。
    零掷骰。"""
    if unit.morale is MoraleState.ROUTED:
        return
    unit.move_path = []
    unit.move_mode = MoveMode.NORMAL
    unit.pivot_to = -1
    unit.command_queue = [c for c in unit.command_queue
                          if not isinstance(c, (MoveCmd, ReverseCmd))]


def cmd_cancel(unit) -> None:
    """§2.2 :160 CancelCmd 处理体（CancelCmd 分派支承载——2026-10-07 命令族收口块；
    MV-B-18 另半「cancel=全清」）：清航点 + 复位 move_mode + 清**整个**
    command_queue（动作令一并清——与 halt「保动作令」的分界即 MV-B-18 边界）+
    清 pivot_to（PB-51「停止令停整个移动族」超集语义，cmd_halt 对齐）+ 清炮击
    任务体 fire_mission（发起人任务块口径「队列+动作令+任务体」全清——超出
    v1.3 :160 字面半步、MOVEMENT v1.3 变更记录留痕；与 CancelFireMissionCmd
    的分工=本令移动族全清连带任务体、彼令仅任务体）。stance 不动（两命令均不
    动——v1.3 :160 括注）。士气块对齐 cmd_halt 先例：ROUTED 期拒——清链等效
    失控干预（溃逃航点唯一清写点=system_morale 重整拍）。零掷骰。"""
    if unit.morale is MoraleState.ROUTED:
        return
    unit.move_path = []
    unit.move_mode = MoveMode.NORMAL
    unit.pivot_to = -1
    unit.command_queue = []
    unit.fire_mission = None


def cmd_pivot(unit, facing_deg: int, cfg: BalanceConfig = CONFIG) -> bool:
    """PB-51 原地转向令处理体（2026-10-04 拍板纳入——断箭 N17 neutral steering；
    PivotCmd 分派支承载）。门（与 issue_move 同款三前置）：DEPLOYING/PACKING 展开
    收起互锁（契约㉑）/ 整班车载拒令（GAP-2 双保险）/ 全被拖拒令（被拖元素由牵引方
    带动——system_move 同款早退条件）。接受则**停车后转向**（原地转向语义=静止动作：
    cmd_halt 清航点/复位模式/清队列移动令）再写 pivot_to（%360 归一）。消费=
    system_move_dispatch 头部 pivot_step（每拍推进、到位自清）。机制层无兵种门
    （SprintCmd 先例——步兵/骡马按类分档速率照转）。士气块（2026-10-04）：ROUTED
    期拒令——溃逃失控（issue_move 门0 同语义，机动族令一并拒）。零掷骰。"""
    if unit.morale is MoraleState.ROUTED:
        return False
    if unit.deploy_state in (DeployState.DEPLOYING, DeployState.PACKING):
        return False
    if unit.elements and all(e.mounted_in is not None for e in unit.elements):
        return False
    if unit.elements and all(e.towed is TowState.TOWED for e in unit.elements):
        return False
    cmd_halt(unit)                      # 停车语义（移动族互斥：pivot_to>=0 ⇒ move_path 恒空）
    unit.pivot_to = facing_deg % 360
    return True


def cmd_formation(units, shape) -> None:
    """MOVEMENT_PSEUDOCODE_v1.2 §2.2 :151-152 FormationCmd 处理体（独立入口；
    2026-10-06 PB-56 批③ Formation 族块）：组下令=逐单位写 u.formation_shape=shape，
    无 REJECT 门（§2.2 字面——门序属移动令族，队形选择无资格/状态门）。槽跨令持续
    （§2.1 生命周期：move_path 耗尽不清、外部新令不清——NONE 需显式下令复位）；
    消费=system_move_dispatch 每拍 make_formation_fn 重建闭包（NONE→None 现状
    同点堆叠，MV-B-19——本命令未达=既有行为逐位不变）。零掷骰（纯槽位写，
    不触任何 PCG32 通道）。
    输入纪律（2026-10-06 批③评审#4）：shape 归一为 FormationShape 枚举——
    裸 int 原样写入会与消费端 is 判据失配、静默落入 else=WEDGE 几何；无门
    字面下非法值处置=跳过不写不抛（SetMode 拒令先例的 void 函数变体）。"""
    try:
        shape = (shape if isinstance(shape, FormationShape)
                 else FormationShape(shape))
    except ValueError:
        return                                              # 非成员值：跳过不写（留痕）
    for u in units:
        u.formation_shape = shape


def issue_group_move(world: World, cfg: BalanceConfig, units, path,
                     mode=MoveMode.NORMAL) -> None:
    """§2.9 编组速度同步（GAP-16 adopt；2026-10-06 PB-56 批③ Formation 族块）：
    组下令入口（框选/编组——**UI 层聚合，非新命令类型**，UI/AI 直调不经命令流；
    签名 mode 缺省 NORMAL=§2.9 伪代码 path/mode 字面）。cap=MIN(u.template.
    speed_tier)（下令时一次定型——确定性、无逐 tick 抖动）；逐单位（插入序）
    issue_move 外部新令（覆盖规则逐单位生效——§2.2 四件一体含清 cap=先脱离旧
    编组）后、len(units)>1 时写 u.group_speed_cap=cap（**组令随后写 cap**——次序
    即语义：issue_move 的清 0 不吃掉本组写入；门拒单位仍写字面 cap=伪代码无条件
    写，可推翻留痕——测试锚定字面）；单独外部新令时 issue_move 清 0=脱离同步；
    队列消费（handoff 通道）不清 cap——编组同步跨排队令保持（BLK-1）。消费点=
    move_speed_cm_tick §2.3 增量①（本块接线）。钳制在档位层不钳最终 v
    （MV-B-15 已否决逐 tick 钳 v 式）。**落点=tick.py §2.2 命令层处理体段**
    （MoveCmd/issue_move 同模块零新导入边；评审退回修复 2026-10-06：原落
    movement.py 经函数体延迟反向导入 tick 构造 MoveCmd 命令对象=该模块
    历史基线之外的新导入边，已移位并补导入面守卫测试）。零掷骰。"""
    cap = min(u.template.speed_tier for u in units)
    for u in units:
        issue_move(world, cfg, MoveCmd(unit=u, path=path, mode=mode))
        if len(units) > 1:
            u.group_speed_cap = cap


def cmd_sprint(world: World, unit, cfg: BalanceConfig = CONFIG) -> None:
    """§D.0 :48/方案14：unit.sprint_until = now + sprint_duration_ticks——sprint_until
    唯一写点（types.py 槽注释口径；MOVEMENT §2.2 动作令冻结入口）。速度式不动
    （契约⑧：升 1 档钳 5——movement.move_speed_cm_tick 既有行）；禁射=D072 两门
    （system_timers AIMING 冻结 + fire_permitted 索敌门）。
    2026-10-04 发起人拍板（MV-B-04 改B，断箭式）：冲刺破压制——开跑拍对全体元素
    suppression 乘 cfg.sprint_suppress_cut_bp（5000=减半；断箭官方「Sprint can be
    used defensively to break suppression and go back to cover」）。士气块
    （2026-10-04）：ROUTED 期拒冲刺自救（断箭 Panicked 无可令证据——勘察建议；
    对 SUPPRESSED/PINNED 冲刺破压全程有效，压制减半→次拍 system_morale 随衰减
    阈值降档=PB-49 全链）。**冷却门（2026-10-07 发起人拍板采纳，登记表留待项就此
    收口）**：`now < sprint_until + cfg.sprint_cooldown_ticks → REJECT`（登记形态
    字面）——冷却窗=上次开跑拍起 duration(100)+cooldown(600)=700t，窗内再令
    sprint_until 不变；sprint_until 初值 0=「从未冲刺」哨兵豁免首冲（无哨兵则
    tick<600 首冲恒拒=登记表述「首冲不受扰」失效）；速度式/写点语义均不动。零掷骰。"""
    if unit.morale is MoraleState.ROUTED:
        return
    if (unit.sprint_until > 0
            and world.tick < unit.sprint_until + cfg.sprint_cooldown_ticks):
        return
    unit.sprint_until = world.tick + cfg.sprint_duration_ticks
    if cfg.sprint_suppress_cut_bp < 10000:               # ≥10000 短路零效（可调回）
        for e in unit.elements:
            e.suppression = e.suppression * cfg.sprint_suppress_cut_bp // 10000


def consume_unit_commands(world: World, cfg: BalanceConfig = CONFIG) -> None:
    """§2.2 consume_commands 单位级落地骨架（伪代码原文登记落点 tick.py:363——挂
    world_tick ① system_timers 前；与既有世界级 consume_commands（§F8 :1425-1426
    收件箱）构成 PB-12 双层）：逐单位（插入序）消费 command_queue——队列头执行
    条件=无进行中移动令（PB-51 +1：无进行中 pivot——原地转向独占，进行中 pivot 期间
    到达的排队移动令等 pivot 完成后安装；反向「到达后转向」=MV-B-05 近亲，仍 defer——
    单位级队列现仅 MoveCmd 可入，PivotCmd 不入队）；
    移动令经 issue_move(handoff=TRUE) 内部通道安装（只装 move_path+换 mode——
    不清链/不清 cap，BLK-1；安装后 move_path≠[] 天然阻塞后续队列头）；队列头令被门
    REJECTED（如 DEPLOYING 期的排队移动令）：该令丢弃、循环继续（拒令不回队首防
    死锁）。士气块（2026-10-04）：ROUTED 期不消费单位级队列——溃逃失控（纵深防御：
    进入拍已清 command_queue、issue_move 门0 拒 queue=TRUE 入队，此处再拦经
    world 级收件箱绕入的边角）。〔2026-10-07 命令族收口块：消费支并入 ReverseCmd
    （v1.3 :166 字面）——ReverseCmd 经 issue_move 归一化 queue=FALSE 常规不入队
    （测试手挂除外），安装后 BREAK 判据对 ReverseCmd 恒 REVERSE（≠NORMAL——
    原生无 mode 字段故按类型判，归一化后同为 MoveCmd(mode=REVERSE) 语义）。〕
    零掷骰。"""
    for u in world.units:
        while (u.command_queue and not u.move_path and u.pivot_to < 0
               and u.morale is not MoraleState.ROUTED):
            cmd = u.command_queue[0]
            u.command_queue.pop(0)
            if isinstance(cmd, (MoveCmd, ReverseCmd)):
                issue_move(world, cfg, cmd, handoff=True)
                if (not isinstance(cmd, MoveCmd)
                        or cmd.mode is not MoveMode.NORMAL):
                    break          # 移动令安装后交还控制（下一令须等到位——§2.2 字面；
                                    # ReverseCmd 恒倒车令=恒交还控制）
            elif isinstance(cmd, SprintCmd):
                cmd_sprint(world, cmd.unit, cfg)   # 动作令冻结入口（§2.2 ELSE 支示例）
            # 其余动作令（DeployCmd/MountCmd/…）入队路径随各自 cmd_* 处理体落地；
            # 当前单位级队列仅 MoveCmd 可入（issue_move 排队支）——不冒充


# ── §F8 system_timers（:1442-1462 最小集）──

def system_timers(world: World, cfg: BalanceConfig = CONFIG) -> None:
    for u in world.units:
        if not u.alive:
            continue
        if u.template.flags & UnitFlag.CAN_INFILTRATE:                 # 方案8 门控
            u.infiltration_timer = max(0, u.infiltration_timer - 1)
        for e in u.elements:
            e.reveal_timer = max(0, e.reveal_timer - 1)
            decay = cfg.sup_decay_per_tick
            if u.template.flags & UnitFlag.SUPP_DECAY_X2:              # 方案18
                decay *= 2
            e.suppression = max(0, e.suppression - decay)
        if u.deploy_state is DeployState.DEPLOYING:
            u.deploy_timer -= 1
            if u.deploy_timer <= 0:
                u.deploy_state = DeployState.DEPLOYED
        elif u.deploy_state is DeployState.PACKING:
            u.deploy_timer -= 1
            if u.deploy_timer <= 0:
                u.deploy_state = DeployState.MOBILE
        for e in u.elements:
            for ws in e.weapon_states:
                if ws.state is WState.AIMING and world.tick < u.sprint_until:
                    continue   # D072（MOVEMENT v1.2 §2.10-8/GAP-3 挂点）：冲刺期 AIMING
                                # timer 递减冻结——不发射不耗弹由 timer 永不归零天然保证；
                                # RELOADING 不冻结（装填照常）；索敌门见 fire_permitted ⑦
                if ws.state in (WState.AIMING, WState.RELOADING):
                    ws.timer = max(0, ws.timer - 1)
                    if ws.state is WState.RELOADING and ws.timer <= 0:  # 方案19 迁移
                        ws.state = WState.READY if ws.ammo_left > 0 else WState.EMPTY
                        if ws.state is WState.EMPTY and u not in world.await_resupply:
                            world.await_resupply.append(u)   # 方案19（:1458-1459）：EMPTY 即登记"等水名单"
    for z in world.smoke_zones:                                        # M6/G27 ttl 递减
        z.ttl_ticks -= 1
    for u in world.units:                                              # PB-53 自卫烟幕到拍落烟
        if not u.alive:                                                # （置于 ttl 环后：本拍
            continue                                                   #  新落烟区不递减——与
        for e in u.elements:                                           #  resolve_blast 炮烟同
            if e.self_smoke_pop_tick >= 0 and world.tick >= e.self_smoke_pop_tick:
                e.self_smoke_pop_tick = -1                             #  生命周期：当拍满额
                world.smoke_zones.append(SmokeZone(                    #  ttl、次拍起递减、
                    center=e.pos, radius_cm=cfg.smoke_radius_cm,       #  尾部过滤同环；
                    ttl_ticks=cfg.smoke_ttl_ticks))                    #  dead 单位跳过=延迟
                                                                       #  窗内被毁烟幕取消）


# ── §F4 交战链（对空分支 + ③ 对地分流 + §F4.1 炮击任务）──
# combat_style 档位常量（§D.3#26：0=NORMAL 1=MELEE 2=SNIPER）2026-10-02 ⑤块迁
# combat.py（resolve_hit 结算分支消费——本模块经顶部 import 再出口，同名引用不变）。


def begin_aim(e, ws, target, cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :731-734。"""
    ws.state = WState.AIMING
    ws.timer = max(1, ws.template.aim_time_ticks * aim_factor_bp(e, cfg) // 10000)
    ws.target = target


def aa_try_engage(world: World, e, ws, cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :885-902 对空自动交战（进入条件由 system_combat ② 名单化——方案2）。
    候选门：敌方 + spotted_mask 含我队位 + alt_tier<=air_ceiling + 射程内；
    目标=最近（MIN by dist_cm——清单⑰A 拍板，并列取列表序首个）。"""
    if e.towed in (TowState.TOWING, TowState.TOWED):                   # GAP-20 拖曳门（R-19）
        return
    ceiling = e.unit.template.air_ceiling
    if ceiling is None:                                                # §D.1#8 不可及
        return
    team_bit = 1 << e.unit.team
    cands = [a for a in world.aircraft
             if a.team != e.unit.team and (a.spotted_mask & team_bit)
             and a.alt_tier <= ceiling
             and dist_cm(e.pos, a.pos) <= ws.template.max_range_cm]
    if not cands:
        return
    best, best_d = cands[0], dist_cm(e.pos, cands[0].pos)
    for a in cands[1:]:
        d = dist_cm(e.pos, a.pos)
        if d < best_d:
            best, best_d = a, d
    begin_aim(e, ws, best, cfg)


def fire_permitted(world: World, unit: UnitInstance, e, ws,
                   cfg: BalanceConfig = CONFIG) -> bool:
    """§F4 :693-706 开火许可九门（逐条；①-⑥ v1.7 原文、⑦ D072、⑧ PB-51、⑨ PB-55 增量）：
    ① phase 门（实战外禁射）；② stance 门（HOLD_FIRE——不约束对空，对空走②分支）；
    ③ needs_deployed 展开门（R-05；v1.5 C3 元素粒度——被拖过的元素须 cmd_deploy 清
    redeploy_needed 才恢复开火）；④ 车载门（mounted_in 且武器非 mounted_armament）；
    ⑤ TOW 双态门（R-19 拖曳双方禁射——C1 双态判；方案13：模板无 TOW 位不问）；
    ⑥ D065 三模式门（mode_set 含 TOW|CARGO|TRANSPORT 任一位且 e.mode 处三态之一
    ——载货状态不作战）。⑦ D072 疾跑禁射门（MOVEMENT v1.2 §2.10-8 索敌门——
    sprint_until 期间不开新 AIMING；与 system_timers AIMING 冻结门配套）。
    ⑧ PB-51 原地转向禁射门（2026-10-04：pivot_to 期间不开新 AIMING、finish_aim
    出口复核拦截在途 AIMING 发射——转 READY 不耗弹；与 D072 同款仅地面链）。
    ⑨ PB-55 溃逃禁射门（2026-10-04 士气效果接线：morale==ROUTED 期间不开新
    AIMING、finish_aim 出口复核拦截在途发射——D014「向后方失控移动」语义下溃逃
    单位不作战；对空链豁免=⑦⑧ 同款 R-17 最小许可集口径，aa_try_engage/对空出口
    不调本函数；炮击任务不清但逐炮走本门（process_fire_mission :1491 统一许可）
    ——PB-54 留待项⑤「不禁射」随之收口为「任务不清、射击拦」）。
    mounted_armament 身份判等（AMB-07：车载 MG 须同时配入
    weapons[] 并以本字段标记）。"""
    if world.phase != PHASE_COMBAT:                                    # ①
        return False
    if unit.stance is Stance.HOLD_FIRE:                                # ②
        return False
    if ws.template.needs_deployed and not (                           # ③ R-05 + C3
            unit.deploy_state is DeployState.DEPLOYED and not e.redeploy_needed):
        return False
    if e.mounted_in is not None:                                       # ④ R-07 车载门
        mounted = e.template.mounted_armament or ()
        if not any(wt is ws.template for wt in mounted):
            return False
    ms = unit.template.mode_set
    if (ms & (1 << Mode.TOW)) and e.towed in (TowState.TOWING, TowState.TOWED):
        return False                                                   # ⑤ R-19 双态
    if (ms & ((1 << Mode.TOW) | (1 << Mode.CARGO) | (1 << Mode.TRANSPORT))) \
            and e.mode in (Mode.TOW, Mode.CARGO, Mode.TRANSPORT):
        return False                                                   # ⑥ D065
    if world.tick < unit.sprint_until:                                 # ⑦ D072 疾跑禁射
        return False
    if unit.pivot_to >= 0:                                             # ⑧ PB-51 原地转向禁射
        return False                                                   # （2026-10-04：转向期间不射——
                                                                       # R-09「射界门外先转车体」同款
                                                                       # 暴露窗口语义的命令侧推广；对空
                                                                       # 链不受本门约束=⑦ 同款 R-17 最小
                                                                       # 许可集口径，aa_try_engage/对空
                                                                       # 出口不调本函数）
    if unit.morale is MoraleState.ROUTED:                              # ⑨ PB-55 溃逃禁射
        return False                                                   # （2026-10-04 士气效果接线：
                                                                       # 溃逃=失控后撤不作战——新
                                                                       # AIMING 与 finish_aim 在途
                                                                       # 复核双拦，转 READY 不耗弹；
                                                                       # SUPPRESSED/PINNED 不走许可门
                                                                       # （受压/钉住=命中乘区
                                                                       # morale_acc_factor_bp 承载，
                                                                       # 非禁射））
    return True


def threat_value(x) -> int:
    """§F4 :727-729 目标对我方 DPS 近似（威胁值=可计算量，无新变量——g-修复）。
    空武器表 MAX 无定义 → 0（无武装元素零威胁——空集下界，实现记账）。"""
    best = 0
    for ws in x.weapon_states:
        dps = (ws.template.damage * ws.template.salvo * 10000
               // max(1, ws.template.reload_time_ticks))
        if dps > best:
            best = dps
    return best


def select_target(world: World, e, ws):
    """§F4 :708-725 直射目标选取：候选门（我发现 / 非车载班 / 狙击剔 MECH（⑲A）/
    GROUND 位 / min≤dist≤max / 犀牛 requiresMark 门（第8轮））+
    评分 w.damage*w.salvo + threat_value − dist//100（并列取列表序首个——确定性；
    方案17：军官射程项已裁剪，本函数不读 aura）。"""
    w = ws.template
    if not (w.target_mask & TargetDomain.GROUND):
        return None
    team_bit = 1 << e.unit.team
    requires_mark = bool(e.unit.template.flags & UnitFlag.REQUIRES_MARK)
    cands = []
    for u in world.units:
        if not u.alive or u.team == e.unit.team:
            continue
        for x in u.elements:
            if not (x.unit.spotted_mask & team_bit):          # 单位被我发现
                continue
            if x.mounted_in is not None:                      # M10/G23：车载班不可直射
                continue
            if w.combat_style == COMBAT_STYLE_SNIPER \
                    and x.template.unit_type is UnitType.MECH:    # ⑲A
                continue
            d = dist_cm(e.pos, x.pos)
            if not (w.min_range_cm <= d <= w.max_range_cm):
                continue
            if requires_mark and x.unit.mark_level < MarkLevel.SPOTTED:
                continue                                      # 犀牛（第8轮）
            cands.append(x)
    if not cands:
        return None
    best, best_score = cands[0], None
    for x in cands:
        score = w.damage * w.salvo + threat_value(x) - dist_cm(e.pos, x.pos) // 100
        if best_score is None or score > best_score:
            best, best_score = x, score
    return best


def ground_direct(world: World, unit: UnitInstance, e,
                  cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :736-747 直射主链（方案1：近战/狙击档案化，无专路——统一 select_target
    射程过滤 → 射界门 → begin_aim）。射界外先转车体（R-09 rotate_step——360° 模板
    恒不进此分支，方案6）。"""
    for ws in e.weapon_states:
        if not (ws.template.target_mask & TargetDomain.GROUND):
            continue
        if ws.state is not WState.READY or ws.ammo_left <= 0:
            continue
        if not fire_permitted(world, unit, e, ws, cfg):
            continue
        tgt = select_target(world, e, ws)
        if tgt is None:
            continue
        want = approach_deg_of(e.pos, tgt.pos)     # 指向目标方位（:744 实参序按语义换——登记表）
        if abs(angle_diff(e.facing, want)) > e.template.fire_arc_deg:
            rotate_step(e, want)                                # R-09 射界外先转车体
            continue
        begin_aim(e, ws, tgt, cfg)


def indirect_role(world: World, unit: UnitInstance, e,
                  cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :749-764 曲射自卫直射（g-R15）：主武器 self_defense 档（模板判空短路——
    方案3）+ READY + 开火许可 + 已发现敌在自卫射程内（M20：仅 teamSpotted——曲射炮
    不是免费近距探测器）→ 最近者（MIN by dist_cm，并列取列表序首个）自卫瞄准
    （use_self_defense=TRUE，惩罚乘区在 fire_direct 消费）。与炮击任务经
    weapon_states 忙碌互斥（AIMING/RELOADING 即非 READY）；炮击任务在 system_combat
    尾部统一推进。"""
    if not e.weapon_states:
        return
    w_main = e.weapon_states[0]
    if w_main.template.self_defense is None:                    # 方案3：判空一行短路
        return
    if w_main.state is not WState.READY:
        return
    if not fire_permitted(world, unit, e, w_main, cfg):
        return
    team_bit = 1 << unit.team
    near, near_d = None, None
    for u in world.units:
        if not u.alive or u.team == unit.team:
            continue
        for x in u.elements:                                    # M20：仅已发现敌元素
            if not (x.unit.spotted_mask & team_bit):
                continue
            d = dist_cm(e.pos, x.pos)
            if d > w_main.template.self_defense.max_range_cm:
                continue
            if near is None or d < near_d:
                near, near_d = x, d
    if near is None:
        return
    w_main.use_self_defense = True
    begin_aim(e, w_main, near, cfg)


def finish_aim(world: World, e, ws, cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :766-788：失的守卫（Building 支 PB-57 建筑实体块 2026-10-06 修正：
    判据=tgt.hp<=0——塌楼失的转 READY 不耗弹、活楼放行续走发射链；原码无 .unit
    恒判失的致 Building 支不可达，登记表在案）+
    对空出口（M4 最小许可集：phase 门与展开门，stance/mode 豁免——R-17）+
    地面出口（M4/G32：fire_permitted 复核——AIMING 中被拖/禁射/收装/切模到期不再
    发射（转 READY 不耗弹）→ fire_direct）。"""
    tgt = ws.target
    if tgt is None:
        ws.state = WState.READY
        return
    if isinstance(tgt, AircraftInstance):
        if not is_aircraft_alive(tgt, world):                          # 失的（对空版 B9）
            ws.state = WState.READY
            return
        if world.phase != PHASE_COMBAT or (ws.template.needs_deployed
                and not (e.unit.deploy_state is DeployState.DEPLOYED
                         and not e.redeploy_needed)):
            ws.state = WState.READY                                    # 不发射、不耗弹
            return
        fire_aa(world, e, ws, tgt, cfg)
        return
    # 失的守卫地面支（§F4 :768-769，v1.5 M4/G06/G29 补支——PB-57 建筑实体块 2026-10-06
    # 修正：原码无 .unit 恒判失的、Building 支不可达）：建筑失的判据=hp<=0（塌楼已
    # 出表+扣血在案）；元素失的判据=已除名（B9）——两判据分离。
    if isinstance(tgt, Building):
        if tgt.hp <= 0:
            ws.state = WState.READY                                    # 建筑失的（楼塌）
            return
    elif getattr(tgt, "unit", None) is None or tgt not in tgt.unit.elements:
        ws.state = WState.READY                                        # 地面失的（B9）
        return
    if not fire_permitted(world, e.unit, e, ws, cfg):                  # M4/G32 出口复核
        ws.state = WState.READY                                        # 不发射、不耗弹
        return
    fire_direct(world, e, ws, tgt, cfg)


def fire_aa(world: World, e, ws, aircraft, cfg: BalanceConfig = CONFIG) -> None:
    """§F9 :1488-1494 对空发射（finish_aim 分支）。
    acc 链同 fire_direct 但无 markLevel/校射项（§F9 原文）：accuracy_base × aim_factor
    × squad_quality（accuracy_ratio 17 段表/ambush/aura 未承载，视为 10000 恒等——登记）。
    PB-55 士气乘区不乘（morale_acc_factor_bp 仅地面链）——依据=代码先例而非「§F9 因子集
    字面无 moraleFactor」：fire_aa 本就窄于 fire_direct（不乘 ambush/aura/self_defense，
    见下方 acc_bp 三项式）+⑦⑧（疾跑/转向禁射）最小许可集先例（R-17——对空链不调
    fire_permitted，⑨ 溃逃禁射同款豁免）；行为=溃逃高炮仍对空开火（对空链士气态
    消费=登记表士气留待项⑫在册，2026-10-04 评审遗留④留痕改准）。
    v1.7 AMB-14 拍板：直射链不喂声测——声事件不写。掷骰通道=HIT（命中）/SCATTER（散布）。"""
    w = ws.template
    if not is_aircraft_alive(aircraft, world) or dist_cm(e.pos, aircraft.pos) > w.max_range_cm:
        ws.state = WState.READY                                        # dist 检查（§F9 原文）
        return
    acc_bp = (w.accuracy_base_bp
              * aim_factor_bp(e, cfg) // 10000
              * e.template.squad_quality_bp // 10000)
    ws.ammo_left -= 1
    ws.state = WState.RELOADING
    ws.timer = max(1, w.reload_time_ticks * reload_factor_bp(e, cfg) // 10000)
    e.reveal_timer = max(e.reveal_timer, w.reveal_time_ticks)          # 开火暴露
    rng_hit, rng_scatter = world.rng.hit(), world.rng.scatter()
    for _i in range(w.salvo):
        will_hit = rng_hit.chance_bp(acc_bp)
        aim = (aircraft.pos[0] + rng_scatter.sym(w.dispersion_cm),
               aircraft.pos[1] + rng_scatter.sym(w.dispersion_cm))
        world.projectiles.append(Projectile(
            shooter=e, weapon=w, damage_type=w.damage_type, damage=w.damage,
            blast_cm=w.blast_radius_cm, pos=e.pos, dest=aim,
            speed_cm_tick=w.projectile_speed_cm_tick, trajectory=w.trajectory,
            hit_target=aircraft, will_hit=will_hit))


def resolve_hit_aa(world: World, p, cfg: BalanceConfig = CONFIG) -> None:
    """§F9 :1495-1499 对空命中结算：对空一律 HE 曲线（armor_aa 单值、无分面——契约③）；
    击落判定归航空系统（§F7 air_check_downed 在下一 tick aircraft_tick 收尾，本函数只扣血）。
    will_hit=False 的近失弹走地面近失压制（§F8 :1472-1473——与 air.remove_aircraft :448
    "晚到弹按冻结分派近失压制"同语义）。伤害倍率锚点：pen=armor_aa → 500‰、pen=2×armor_aa
    → 800‰（combat HE 曲线三锚点族）。"""
    a = p.hit_target
    if not p.will_hit or not isinstance(a, AircraftInstance) \
            or not is_aircraft_alive(a, world):
        inject_suppression_area(world, p.dest, p.weapon.blast_radius_cm,
                                p.weapon.suppression_power)
        return
    pen = penetration_at(p.weapon, dist_cm(p.shooter.pos, p.dest))    # dist_flew≈发射点→落点
    armor = max(1, a.armor_aa)                                        # B10 除零守卫族
    mult = damage_mult_permille(UnitType.MECH, DamageType.HE, pen, armor)
    a.hp_current -= p.damage * mult // 1000


def select_profile(world: World, e, ws, tgt):
    """§F4 :790-804 R-11 自动选弹：软目标（INFANTRY）优先 alt_profile HE 档；
    受限弹药档（钨芯）——常规 AP 打不动 MECH 正面（pen_max < armor_ke.front）且
    档内有存货 → 自动救场（M16：读/减 weapon_states.restricted_left 实例副本，
    实例化深拷贝——make_unit 承载）；默认返回武器默认档案。
    返回 (damage_type, damage, blast_cm, pen_bonus)——内联进 Projectile 既有字段
    （§D.6 :219 profile 载体的本仓口径，见登记表 discrepancies）。"""
    w = ws.template
    if w.alt_profile is not None and tgt.template.unit_type is UnitType.INFANTRY:
        return (DamageType.HE, w.alt_profile.damage, w.alt_profile.blast_radius_cm, 0)
    for i, rp in enumerate(w.restricted_profiles):
        front = tgt.template.armor_ke.front if tgt.template.armor_ke is not None else 0
        if (i < len(ws.restricted_left) and ws.restricted_left[i] > 0
                and tgt.template.unit_type is UnitType.MECH
                and w.pen_max < front):
            ws.restricted_left = (ws.restricted_left[:i]
                                  + (ws.restricted_left[i] - 1,)
                                  + ws.restricted_left[i + 1:])
            return (w.damage_type, w.damage, w.blast_radius_cm, rp[1])   # 默认AP+pen_bonus
    return (w.damage_type, w.damage, w.blast_radius_cm, 0)


def _jitter_small(pos, rng):
    """§F4 :839 jitter_small（命中点贴目标）——v1.7 零定义体/§D.0 无幅度常数：
    零幅实现（sym(0)=0，各消费一次 SCATTER 抽签保留字面通道消费），幅度待数值
    章节定标（见登记表 discrepancies；同 fire_aa"accuracy_ratio 未承载视为恒等"先例）。"""
    return (pos[0] + rng.sym(0), pos[1] + rng.sym(0))


def fire_direct(world: World, e, ws, tgt, cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :806-846 直射发射（finish_aim 地面出口唯一后继；方案1：狙击/近战统一直射链）。
    acc 乘区逐项 //10000 按原文书写序（fire_aa 同款口径）；accuracy_ratio_bp 17 段表
    §D.0 未列——默认全 10000 恒等（fire_aa 先例，登记）；ambush_shot_bonus 打完清
    （R-12 首击）；校射收束仅活跃任务期（方案10：unit.fire_mission 非 NULL 才读
    fm.calib_progress）；渗透身份清零仅 MELEE/SNIPER（清单⑦A）；AMB-14：直射链
    不喂声测（声事件不写）。掷骰通道=HIT（命中）/SCATTER（散布）。"""
    unit = e.unit
    w = ws.template
    if getattr(tgt, "unit", None) is None and getattr(tgt, "hp", None) is not None:
        # Building 目标（:808）：HE 默认档、pen_bonus=0（建筑无 unit_type，跳过自动选弹）
        prof = (DamageType.HE, w.damage, w.blast_radius_cm, 0)
    else:
        prof = select_profile(world, e, ws, tgt)
    ws.ammo_left -= 1
    mark_resupply_if_needed(world, unit)                     # :811 弹药缺口即登记
    ws.state = WState.RELOADING
    ws.timer = max(1, w.reload_time_ticks * reload_factor_bp(e, cfg) // 10000)
    e.reveal_timer = max(e.reveal_timer, w.reveal_time_ticks)          # 开火暴露
    if (w.combat_style in (COMBAT_STYLE_MELEE, COMBAT_STYLE_SNIPER)
            and unit.infiltration_timer > 0):
        unit.infiltration_timer = 0                          # 清单⑦A：仅狙击/近战清身份
    dist = dist_cm(e.pos, tgt.pos)
    acc_bp = w.accuracy_base_bp                              # :821-829 乘区（书写序）
    # accuracy_ratio_bp(dist // MAX(1, w.max_range_cm))——17 段查表 §D.0 未列、
    # 默认全 10000（:822 字面）→ 恒等项不乘（fire_aa 同款登记）
    acc_bp = acc_bp * aim_factor_bp(e, cfg) // 10000
    acc_bp = acc_bp * morale_acc_factor_bp(unit, cfg) // 10000  # PB-55 士气态命中乘区
    # （2026-10-04：D023「×士气惩罚」+GDD-05 B4:149 moraleFactor 受压×0.7/钉住×0.3
    #  ——单位级乘区紧随元素级连续项；对空 fire_aa 不乘——依据=代码先例（fire_aa 本就
    #  窄于 fire_direct：不乘 ambush/aura/self_defense）+⑦⑧ R-17 最小许可集先例，
    #  详见 fire_aa docstring；登记表士气留待项⑫在册）；aim 时间/装填杠杆未采
    #  （断箭参考，无 GDD 锚——登记表留待项⑪））
    acc_bp = acc_bp * (cfg.ambush_acc_bonus_bp if unit.ambush_shot_bonus else 10000) // 10000
    acc_bp = acc_bp * aura_bonus_bp(world, unit.team, AuraKind.PRECISION, e.pos) // 10000
    acc_bp = acc_bp * e.template.squad_quality_bp // 10000
    if getattr(tgt, "unit", None) is not None:               # R-01（建筑无标记——v1.3）
        acc_bp = acc_bp * (cfg.calib_acc_bonus_bp
                           if tgt.unit.mark_level is MarkLevel.CALIBRATED else 10000) // 10000
    if ws.use_self_defense and w.self_defense is not None:   # R-15 惩罚
        acc_bp = acc_bp * w.self_defense.accuracy_mult_bp // 10000
    unit.ambush_shot_bonus = False
    calib_reduction_bp = 10000                               # :833-835 方案10：仅活跃任务期
    if unit.fire_mission is not None:
        calib_reduction_bp = (10000 - unit.fire_mission.calib_progress
                              * cfg.calib_max_reduction_bp // 100)
    rng_hit, rng_scatter = world.rng.hit(), world.rng.scatter()
    for _i in range(w.salvo):
        will_hit = rng_hit.chance_bp(acc_bp)
        if will_hit:
            aim = _jitter_small(tgt.pos, rng_scatter)        # 命中点贴目标
        else:
            r = w.dispersion_cm * calib_reduction_bp // 10000
            aim = (tgt.pos[0] + rng_scatter.sym(r), tgt.pos[1] + rng_scatter.sym(r))
        world.projectiles.append(Projectile(
            shooter=e, weapon=w, damage_type=prof[0], damage=prof[1], blast_cm=prof[2],
            pos=e.pos, dest=aim, speed_cm_tick=w.projectile_speed_cm_tick,
            trajectory=w.trajectory, hit_target=tgt, will_hit=will_hit,
            pen_bonus=prof[3]))
    ws.use_self_defense = False                              # 自卫档一次性，发射即复位


def upsert_sound_track(world: World, firing_unit, new_pos,
                       cfg: BalanceConfig = CONFIG) -> None:
    """§F3 :651-659 声测痕迹 upsert（fire_at 写侧——保留清单#3；读侧 sonar_step 未实现）：
    每 (侦听队, 开火单位) 一条（队集=players 队序去重——resolve_settlement 同口径）；
    新开火位置距 track.pos > sonar_move_reset_cm → accum 清零（换阵地重定位，C4②）；
    pos/last_fire_tick 每次开火刷新。"""
    teams = []
    for p in world.players:
        if p.team != firing_unit.team and p.team not in teams:
            teams.append(p.team)
    for t in teams:
        track = next((s for s in world.sound_tracks
                      if s.listening_team == t and s.unit is firing_unit), None)
        if track is None:
            track = SoundTrack(listening_team=t, unit=firing_unit, pos=new_pos,
                               accum=0, last_fire_tick=world.tick)
            world.sound_tracks.append(track)
        if dist_cm(new_pos, track.pos) > cfg.sonar_move_reset_cm:
            track.accum = 0                                  # 换阵地重定位
        track.pos = new_pos
        track.last_fire_tick = world.tick


def process_fire_mission(world: World, unit: UnitInstance,
                         cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :908-917 炮击任务推进（system_combat 尾部——方案3 静态门在调用侧）。
    R-14 半轮=前 ⌈N/2⌉ 门 INDIRECT 元素（AMB-09 向上取整——3 门连半轮=2 门）；
    逐炮 READY + 开火许可（未展开/被拖/载货不打——v1.1 修复统一走许可）才 fire_at。"""
    fm = unit.fire_mission
    if fm is None:
        return
    guns = [g for g in unit.elements if g.mode is Mode.INDIRECT]
    if fm.salvo_mode is SalvoMode.HALF:
        guns = guns[:(len(guns) + 1) // 2]                    # R-14 前 ⌈N/2⌉ 门
    for gun in guns:
        if not gun.weapon_states:
            continue
        ws = gun.weapon_states[0]                            # 主武器
        if ws.state is not WState.READY:
            continue
        if not fire_permitted(world, unit, gun, ws, cfg):
            continue
        fire_at(world, gun, ws, fm, cfg)


def _lerp_pt(a, b, num: int, den: int):
    """LERP(a, b, num/den) 整型实现（den>0；num>=den → b——t=MIN(1,·) 封顶）。"""
    if num >= den:
        return b
    return (a[0] + (b[0] - a[0]) * num // den, a[1] + (b[1] - a[1]) * num // den)


def fire_at(world: World, gun, ws, fm, cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :919-958 无目标弹丸（B：fireAt 定义体；R-13/R-16/R-03 盲射）。
    落点：POINT=目标点 / LINE=沿线均匀取样（第 k=shots_fired 份，分母=任务总发数
    shots_fired+shots_left——原文未定分母，实现记账见登记表；MAX(1,·) 防零除）/
    CREEP=LERP(a,b,经过距离/线长)；盲射声测圈叠加（intel_circles 圈内取 MAX 半径）；
    校射仅 POINT+友军视野内（⑩A：LINE/CREEP 短路；AMB-06 按批 +calib_per_shot）+
    换点重置；曲射档案=alt_profile 否则默认档案（M8/A14：双职炮曲射吃 HE 数值——
    纯榴弹炮两者同一）；每次 fire_at 发 salvo 发（M8/G11：同批共用取样点、各吃独立
    散布）；弹药/任务计数按 salvo 增减；曲射只留声测痕迹不写 reveal_timer（㉗A）；
    shots_left<=0 任务体销毁（方案10：校射进度随之失效）。掷骰通道=SCATTER only。"""
    w = ws.template
    if fm.form is FireMissionForm.POINT:
        pt = fm.target_point
    elif fm.form is FireMissionForm.LINE:
        pt = _lerp_pt(fm.target_line[0], fm.target_line[1], fm.shots_fired,
                      max(1, fm.shots_fired + fm.shots_left))
    else:                                                    # CREEP
        line_len = max(1, dist_cm(fm.target_line[0], fm.target_line[1]))
        pt = _lerp_pt(fm.target_line[0], fm.target_line[1],
                      (world.tick - fm.started_tick) * fm.creep_speed_cm_tick, line_len)
    extra = 0                                                # 盲射声测圈叠加（:927-929）
    for c in world.intel_circles:
        if c.team == gun.unit.team and dist_cm(c.center, pt) <= c.radius_cm:
            extra = max(extra, c.radius_cm)
    if fm.form is FireMissionForm.POINT:                      # R-16 连内共享校射（⑩A：仅 POINT）
        _ffn, _sfn, _ = terrain_sensing_channels(world)       # 感知接线块 2026-10-07：
        if point_in_friendly_vision(cfg, world, gun.unit.team, fm.target_point,  # 校射视线同
                                     forest_m_fn=_ffn, smoke_m_fn=_sfn):        # 吃穿林/穿烟衰减
            fm.calib_progress = min(100, fm.calib_progress + cfg.calib_per_shot)
        if fm.target_point != fm.calib_target:                # 换点重置
            fm.calib_target = fm.target_point
            fm.calib_progress = 0
    scatter_cm = (w.dispersion_cm
                  * (10000 - fm.calib_progress * cfg.calib_max_reduction_bp // 100) // 10000
                  + extra)
    if w.alt_profile is not None:                            # M8/A14：曲射档案
        prof = (DamageType.HE, w.alt_profile.damage, w.alt_profile.blast_radius_cm, 0)
    else:
        prof = (w.damage_type, w.damage, w.blast_radius_cm, 0)
    rng_scatter = world.rng.scatter()
    for _i in range(w.salvo):
        aim = (pt[0] + rng_scatter.sym(scatter_cm), pt[1] + rng_scatter.sym(scatter_cm))
        world.projectiles.append(Projectile(
            shooter=gun, weapon=w, damage_type=prof[0], damage=prof[1], blast_cm=prof[2],
            pos=gun.pos, dest=aim, speed_cm_tick=w.projectile_speed_cm_tick,
            trajectory=Trajectory.BALLISTIC, hit_target=None, will_hit=False,
            pen_bonus=prof[3]))
    ws.ammo_left -= w.salvo
    ws.state = WState.RELOADING
    ws.timer = max(1, w.reload_time_ticks * reload_factor_bp(gun, cfg) // 10000)
    mark_resupply_if_needed(world, gun.unit)                  # :951
    fm.shots_left -= w.salvo
    fm.shots_fired += w.salvo
    upsert_sound_track(world, gun.unit, gun.pos, cfg)         # 火箭炮 acoustic 最高→最快被定位
    if fm.shots_left <= 0:
        gun.unit.fire_mission = None                          # 任务体销毁（方案10）


def cmd_fire_mission(world: World, unit: UnitInstance, form, point_or_line,
                     ammo_mult: int, salvo_mode, creep_speed: int,
                     cfg: BalanceConfig = CONFIG) -> bool:
    """§F4 :960-971 任务创建入口（REJECT：无 INDIRECT 位 / 无 INDIRECT 元素）。
    R-13 弹量基数：shots=（HALF ? ⌈N/2⌉ : N）× 主武器 ammo_base × ammo_mult
    （M9/G03：HALF 与 process_fire_mission 同规则——AMB-09 ⌈N/2⌉ 口径）。
    §2.11 超射程自动进位（2026-10-06 速度链块；GAP-13 adopt/MV-B-21 炮击任务
    语境）：双门通过后、任务体安装时——目标在 INDIRECT 主武器最大射程（MAX）外
    → movement.auto_approach_waypoint 插"射程内侧 standoff 航点"（下界半射程
    AMB-4），经 issue_move **外部通道**安装（MoveCmd queue=FALSE 四件一体：下达
    炮击任务即重置移动链/退编组——§2.11 :384-385「外部直令场景」，世界级命令流
    =UI/AI 外部入口（§2.2 词汇「UI/AI 一律不传（外部恒 FALSE）」）；handoff=TRUE
    排队消费形态（§2.11 :379 主登记）留待 FireMissionCmd 入单位级队列的未来通道
    ——现不可达不冒装）；进位移动恒 NORMAL 模式；射程内返 None=零行为差。判距
    基准：POINT=目标点；LINE/CREEP=采样线段最近点（movement.nearest_on_segment
    ——规格 §2.11 仅定义点目标的定标延伸，可推翻）。移动令被门拒（收装中/整班
    车载/溃逃等）时任务照常建立、不插航点（规格无"拒移动则拒任务"写点——留痕）。
    到位后既有展开门（needs_deployed）与射击门照常接管。〔2026-10-07 命令族
    收口块批注：DEPLOYED 单位的进位移动令随 pack_or_move 接线（发起人拍板采
    IMPL 字面）先转 PACKING 再走——收装期+行军期 needs_deployed 门拦射、到位后
    须重下 DeployCmd 展开方续任务 firing（原「DEPLOYED 行军中照射」行为洞闭账；
    锚=test_ground_combat TestAutoApproachConsumption PACKING 断言）。〕零掷骰（本
    增量不触 PCG32 通道——发射段掷骰属既有 SCATTER 纪律）。"""
    if not (unit.template.mode_set & (1 << Mode.INDIRECT)):
        return False
    guns = [g for g in unit.elements if g.mode is Mode.INDIRECT]
    if not guns:
        return False
    guns_max_range = 0                              # §2.11：任务炮 INDIRECT 主武器射程 MAX
    for g in guns:
        if g.weapon_states:
            guns_max_range = max(guns_max_range,
                                 g.weapon_states[0].template.max_range_cm)
    if guns_max_range > 0:
        is_pt = form is FireMissionForm.POINT
        ref = point_or_line if is_pt else nearest_on_segment(
            unit.elements[0].pos, point_or_line[0], point_or_line[1])
        wp = auto_approach_waypoint(unit, ref, guns_max_range, cfg)
        if wp is not None:
            issue_move(world, cfg,
                       MoveCmd(unit=unit, path=[wp], mode=MoveMode.NORMAL))
    n = (len(guns) + 1) // 2 if salvo_mode is SalvoMode.HALF else len(guns)
    main_ws = guns[0].weapon_states[0]
    shots = n * main_ws.template.ammo_base * ammo_mult
    is_point = form is FireMissionForm.POINT
    unit.fire_mission = FireMission(
        form=form,
        target_point=point_or_line if is_point else None,
        target_line=(tuple(point_or_line) if not is_point else None),
        creep_speed_cm_tick=creep_speed, ammo_mult=ammo_mult, salvo_mode=salvo_mode,
        shots_left=shots, shots_fired=0, started_tick=world.tick,
        calib_target=(point_or_line if is_point else None), calib_progress=0)
    return True


def cmd_cancel_fire_mission(world: World, unit: UnitInstance) -> None:
    """§F4 :972-973：任务体销毁，校射随之失效（方案10）。零掷骰。"""
    unit.fire_mission = None


def cmd_set_airdrop_beacon(world: World, unit: UnitInstance, pos) -> bool:
    """§F6 :1269-1271 空投信标处理体（PB-56 批③收口补落——2026-10-06 发起人
    指令「剩四类事全部完成」，22 类总收口最后缺口就此闭环）。
    门序照字面：① NOT CAN_AIRDROP_BEACON → REJECT（资格门——渗透班/勃兰登堡；
    现役 0 卡置位，数据侧随数值章节/后续卡批次〔2026-10-07 数据定标块裁定=零卡
    配属如实留痕：无卡可配非缺陷——空降兵（CAN_INFILTRATE，PB-31）职能为渗透
    计时非布信标；信标链单测锚在库不缺可测性；配属留待真渗透/侦察卡批次
    （GDD-01 规划面）——① 门对现役全卡恒 REJECT 即为如实态〕）；② 写 beacon_by_unit——
    键型适配（air.nearest_friendly_beacon 同日同修）：键=unit.id、值=(team,pos)
    （PB-45 cover_by_target 键=unit.id 先例同款——UnitInstance mutable 不可哈希；
    队属随值携带免读侧回查，注销侧 combat.unregister pop(unit.id) 三口同形）。
    不算暴露、不清渗透身份（§F9 接口约定不变——字面无此写点）。零掷骰。"""
    if not (unit.template.flags & UnitFlag.CAN_AIRDROP_BEACON):    # ① 资格门
        return False
    world.beacon_by_unit[unit.id] = (unit.team, (pos[0], pos[1]))
    return True


# ── §F4 cmd_attack（:848-872——PB-56 批① 作战链命令块，2026-10-06）──

def cmd_attack(world: World, e, target, cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :848-872 AttackCmd 处理体——直射指定目标（含建筑；PB-56 批① 2026-10-06）。
    玩家令入口补齐 §D.7 :265 声明「cmd_attack 见 §F4」而处理体缺失的缺口——
    直射拆楼链（AttackCmd→begin_aim→finish_aim 建筑支→fire_direct HE 档→
    resolve_hit ×vs_fort→hit_building→塌楼）玩家令可达性就此闭环（PB-57 建筑实体
    块④ 留待项收口）。

    武器选择口径（勘察 decisionPoint#1，默认裁决可推翻）：§F4 :848 签名带单 ws
    形参而 §D.7 :265 命令类只有 {element,target}——采**循环案**：遍历
    e.weapon_states 逐武器过全门序，过门者各自 begin_aim（与 ground_direct
    :736-747 同构；多武器元素全上、非攻坚武器对建筑被 ① vs_fort 门自然滤除；
    test_economy_phase drain 用例 target=None×无武器元素=循环体零执行自然无操作
    存活——单主武器 weapon_states[0] 案在该用例 IndexError，不采）。

    门序照伪代码字面（①-⑪ 逐条；REJECT=跳过该武器）：
      ① Building 目标 × vs_fort_mult_permille<=1000 REJECT——建筑资格门（攻坚
        武器专属；2026-10-07 数据定标块：现役四攻坚武器已配值 3000-5000‰——
        D-5T/ZiS-3 直+曲/PaK40 过门（P-122），步兵武器维持缺省 1000 恒 REJECT=
        无攻坚资格；真卡端到端锚 tests/test_data_calibration_v1.py）；
      ② Element 目标 × target_mask 无 GROUND 位 REJECT；
      ③ 狙击（combat_style==SNIPER）指火 MECH 元素 REJECT（⑲A——与 select_target
        候选剔除同谓词，手动入口同受约束 A08）；
      ④ Element 目标未发现（spotted_mask 不含我队位）REJECT（M5/B01——战争
        迷雾侧门通用存在）；
      ⑤ shooter 单位 requiresMark 且 target.mark_level<SPOTTED REJECT（犀牛门；
        Building 豁免——建筑无标记）；
      ⑥ 车载班目标（mounted_in 非空）REJECT（M10/G23）；
      ⑦ 非 READY 或 ammo<=0 REJECT；
      ⑧ fire_permitted 九门 REJECT（§F4 :693-706——phase/stance/展开/车载/拖曳/
        载货/疾跑/转向/溃逃；与自动链同谓词）；
      ⑨ 超 max_range REJECT（无 min_range 门——伪代码 :868 字面仅上限，比
        select_target 的 min≤d≤max 宽：近距手动指火不放行自动链的 min 拦截，
        照字面落地留痕）；
      ⑩ Element 目标在射界外 → rotate_step 转车体 + RETURN（R-09 射界门外先
        转车体；Building 无朝向不进此分支）。实参序 approach_deg_of(e.pos,
        target.pos)——:870 字面反序系登记笔误，geom.py :53-58 登记表成文按语义
        换序（ground_direct :744 同款修正序先例）。循环形下 RETURN=函数退出
        （伪代码字面；多武器元素每令至多转一步——逐武器各调一次 rotate_step
        将倍速转向，不采）；
      ⑪ begin_aim（零掷骰——aim_time×aim_factor 整数运算）。
    敌我队判伪代码门序未列（§F4 :848-871 无 team 检查）：单位侧友军误击被
    ④ 发现门事实拦截（sensing 己队观察者 continue=spotted_mask 己队位永不
    置位）；建筑侧 Building 无归属字段（§D.6 :229 冻结数据面）——任意
    vs_fort 达标射手可指火任意建筑、含己方部队驻守的楼（塌楼伤己方驻军
    链路可达）。**2026-10-06 发起人拍板：保留该玩法口径（可拆自家驻军楼）
    ——照伪代码字面不补归属门**（补门=新机制未采，登记可推翻；批①评审#2）。
    无 mode 门（伪代码 :848-871 未列——INDIRECT 模式元素可被手动指火直射，
    fire_permitted ⑥ 仅拦 TOW/CARGO/TRANSPORT 三态；与 ground_direct 仅
    DIRECT 模式自动交战不同=手动入口照字面宽于自动链，留痕）。目标存活门
    伪代码亦未列——死亡目标由 finish_aim 失的守卫（B9 除名/hp<=0）收口。
    target=None 超 §D.7 契约（Element|Building）：无武器元素循环零执行自然
    无操作（drain 用例）；有武器元素将在 ④ 触 AttributeError=契约外输入，
    与未知命令类型抛 TypeError 同款程序员错误口径。零掷骰（不触任何 PCG32
    通道——门序+begin_aim+rotate_step 全纯整数）。"""
    for ws in e.weapon_states:
        w = ws.template
        is_building = isinstance(target, Building)
        if is_building and w.vs_fort_mult_permille <= 1000:             # ① 建筑资格门
            continue
        if not is_building:
            if not (w.target_mask & TargetDomain.GROUND):               # ② GROUND 位
                continue
            if (w.combat_style == COMBAT_STYLE_SNIPER
                    and target.template.unit_type is UnitType.MECH):    # ③ ⑲A 狙击×MECH
                continue
            if not (target.unit.spotted_mask & (1 << e.unit.team)):     # ④ M5/B01 发现门
                continue
            if (bool(e.unit.template.flags & UnitFlag.REQUIRES_MARK)
                    and target.unit.mark_level < MarkLevel.SPOTTED):    # ⑤ 犀牛门
                continue                                               #   （Building 豁免——无标记）
            if target.mounted_in is not None:                           # ⑥ M10/G23 车载班
                continue
        if not (ws.state is WState.READY and ws.ammo_left > 0):         # ⑦ READY+弹药
            continue
        if not fire_permitted(world, e.unit, e, ws, cfg):               # ⑧ 九门
            continue
        if dist_cm(e.pos, target.pos) > w.max_range_cm:                 # ⑨ 射程上限
            continue
        if not is_building:                                             # ⑩ R-09 射界门
            want = approach_deg_of(e.pos, target.pos)   # :870 实参序按语义换（geom 登记表）
            if abs(angle_diff(e.facing, want)) > e.template.fire_arc_deg:
                rotate_step(e, want)
                return                              # 伪代码 RETURN——循环形=函数退出
        begin_aim(e, ws, target, cfg)                                   # ⑪ 零掷骰


# ── §F6 cmd_set_element_mode（:1193-1213——PB-56 批① 作战链命令块·SetMode，
#    2026-10-06）+ §F4 cmd_toggle_ambush（:874-883）+ §D.7 SetStance 最小写点（:261）──

def cmd_set_element_mode(world: World, e, m) -> bool:
    """§F6 :1193-1213 SetModeCmd 处理体（元素粒度——D065 三模式/火炮双职）。
    输入纪律（2026-10-06 批①评审#3）：m 归一为 Mode 枚举——裸 int 可过 ①
    位掩码门但与 ②-④/⑦ 身份比较分支失配（CARGO 卸货/TRANSPORT 卸客被
    静默跳过）；归一失败（非单一 Mode 成员值，含位组合）=REJECT（与 ① 位集外
    值掩码滤除同款拒令口径，静默程序员错误不如显式拒令可测）。
    写点序照伪代码字面①-⑦：
      ① m ∉ e.unit.template.mode_set → REJECT（mode_set 缺省=1<<DIRECT——
        types.py；位集外值（含越界 int）同被掩码滤除）；
      ② e.mode==TOW → release_tow_if_involved(world, e)——切模式先解挂
        （v1.7 GAP-24 元素级：仅解除本元素牵涉的拖曳对，同单位其他健康拖曳
        不误杀；因由经 stop_tow 不分支=DESTROYED 无行为差，勘察留痕口径）；
      ③ e.mode==CARGO 且有 hasSupply 槽 → 卸货清零——伪代码 :1196-1197 写
        e.supply_rounds/e.supply_medical 两字段在代码不存在（2026-10-03 弹药/
        医疗一池按重量拍板后唯一槽=supply_weight_g），按勘察 discrepancies#3
        换写 supply_weight_g=0（destroy_element combat.py 同款先例；None=未
        分配条件槽不触碰——方案12）；
      ④ e.mode==TRANSPORT 且 cargo_units 非空 → 逐班卸客：班元素 mounted_in==e
        者双向清引用+旁落位（v1.3 审查#3——偏移未定标取载具同点位，destroy_element
        同款登记），班单位锚 s.pos 同旁落位；e.cargo_units=[]（:1203 字面）；
      ⑤ m≠TRANSPORT 且 mount_requests 表非 None → 清 carrier==e 挂起条目
        （v1.4 I-19——切出运载状态原到期仍挂上；按身份过滤，MountRequest
        eq=False 口径；表惰性 None 早退——方案12）；
      ⑥ e.mode=m；
      ⑦ m≠INDIRECT 且本单位已无任何 INDIRECT 元素 → 清 unit.fire_mission
        （M21/A24 元素级半清除——e.mode 已先行赋值故判据自然排除刚切元素；
        任务体销毁校射随之失效，方案10）。
    cmd_fire_mission 双门（:961-962 mode_set&INDIRECT 位+存在 mode==INDIRECT
    元素）的消费端关系：元素初始 mode=DIRECT（types.py）→ 本命令是炮击任务令
    的唯一解锁钥匙。零掷骰（解挂/清表/写槽全纯整数，不触任何 PCG32 通道）。"""
    try:
        m = m if isinstance(m, Mode) else Mode(m)                        # 输入纪律归一
    except ValueError:                                                   # 非成员值（含位组合）
        return False                                                    # =拒令（掩码滤除同款）
    if not (e.unit.template.mode_set & (1 << m)):                        # ① 资格门
        return False
    if e.mode is Mode.TOW:                                               # ② 切模式先解挂
        release_tow_if_involved(world, e)                                #   （GAP-24 元素级）
    if e.mode is Mode.CARGO and e.supply_weight_g is not None:           # ③ CARGO 卸货
        e.supply_weight_g = 0                                            #   （:1196-1197 字段
                                                                         #    按 2026-10-03 一池
                                                                         #    拍板换 supply_weight_g）
    if e.mode is Mode.TRANSPORT and e.cargo_units is not None:           # ④ TRANSPORT 卸客
        for s in e.cargo_units:
            for se in s.elements:
                if se.mounted_in is e:                                   #   v1.3 审查#3 双向清
                    se.pos = e.pos                                       #   旁落位（同点位——
                                                                         #    偏移未定标登记）
                    se.mounted_in = None
            s.pos = e.pos                                                #   班锚旁落位
        e.cargo_units = []                                               #   :1203 字面
    if m is not Mode.TRANSPORT and world.mount_requests is not None:     # ⑤ 清挂起请求（I-19）
        world.mount_requests = [r for r in world.mount_requests
                                if r.carrier is not e]                   #   按身份过滤
    e.mode = m                                                           # ⑥ 写点（M21 判据先行）
    if m is not Mode.INDIRECT and not any(x.mode is Mode.INDIRECT
                                          for x in e.unit.elements):     # ⑦ M21/A24 半清除
        e.unit.fire_mission = None                                       #   （任务体销毁——
                                                                         #    校射随之失效，方案10）
    return True


def cmd_toggle_ambush(unit) -> bool:
    """§F4 :874-883 ToggleAmbushCmd 处理体（单位粒度）——R-12 伏击开关的唯一
    写点（原 ambush_active 全文无 TRUE 写点=R-12 整链不可达，v1.4 审查 high#2
    补体；消费端 sensing.effective_stealth_x10 ×ambush_mult_bp=20000/
    detection_range_cm 观察者 r//2/fire_direct 首击 ×ambush_acc_bonus_bp=13000+
    打完清均已接线，零新效果代码）：
      ① NOT flags.canAmbush → REJECT（资格门——位已定义 types.py UnitFlag，
        现役 0 卡置位：⑮A 拍板 4 卡 SU-85/三突G/四号歼击车/追猎者均不在
        ground_cards.csv 现役 10 卡集、flags 列零置位〔实测〕→ 对现役恒 REJECT，
        数据侧脱节登记〔CAN_GARRISON 追认补卡先例在——补位随数值章节/数据侧〕，
        测试用合成模板）；
      ② ambush_active → 手动退出：active=FALSE + ambush_shot_bonus=TRUE
        （:879-880——退出携首击加成，消费点 fire_direct 首击；GAP-28 移动仍清
        加成由 system_move 承载 movement.py:217-218）；
      ③ ELIF 静止（move_path==[]）→ 开启：ambush_active=TRUE（§F3 两消费点
        生效——视野减半+隐蔽乘成）。伪代码「静止 AND move_path==[]」两谓词
        同源（moving()=bool(move_path)，IMPL :27 成文）——折叠为单判 not
        unit.moving()；移动中受令=过资格门但不满足 ELIF=无操作（伪代码无第二
        REJECT 字面，返回 True 留痕）。移动自动退出（无加成）由 system_move
        承载（movement.py:215-218 已落，含 M19 加成随移动清除）；开火不自动
        退出（R-12 已确认——GDD-02 v1.9:166-170）。与地形荫蔽叠加（同拍板）。
    零掷骰。"""
    if not (unit.template.flags & UnitFlag.CAN_AMBUSH):                  # ① 资格门
        return False
    if unit.ambush_active:                                               # ② 手动退出携首击加成
        unit.ambush_active = False
        unit.ambush_shot_bonus = True
    elif not unit.moving():                                              # ③ 开启需静止
        unit.ambush_active = True
    return True


def cmd_set_stance(unit, stance) -> bool:
    """§D.7 :261 SetStanceCmd 处理体——**最小写点案**（勘察处置建议 a，2026-10-06
    默认裁决可推翻）：v1.7 全文仅字段定义（UnitInstance.stance 缺省
    WEAPONS_FREE，types.py:392）无处理体（stance 写点），GDD 侧无任何姿态细则锚
    （GDD-00/GDD-02 v1.9 grep 无条目；GDD-05 B3:137 宽姿态集口径已作废——
    types.py:93 留痕）。先例：SprintCmd（§D.7 :261 行内注释即写点说明）→cmd_sprint
    最小实现、cmd_set_airdrop_beacon v1.4 对「仅签名无体」补最小处理体——本函数
    同款：单写点 unit.stance=stance + Stance 枚举合法性校验，**无资格门**（全部
    行为门已在消费侧：fire_permitted ② HOLD_FIRE 禁新 AIMING+finish_aim 出口
    复核；ROUTED 单位本就禁射⑨、切姿态无行为危害——无锚造门不采勘察处置案 b）。
    枚举外值 → REJECT（False，与门序 REJECT 同口径不冒充通过；Stance 两值
    {WEAPONS_FREE, HOLD_FIRE}，types.py:84-86——「不约束对空」由对空链不调
    fire_permitted 天然豁免，§F4 :695）。GDD 侧回写落点（何种文档承载开火纪律）
    随 GDD 版本执行，登记表留痕。零掷骰。"""
    if not isinstance(stance, Stance):
        return False
    unit.stance = stance
    return True


# ── §F6 cmd_smoke（:1274-1299——PB-53 载具自卫烟幕路径，2026-10-04 拍板纳入）──

def cmd_smoke(world: World, element, point, cfg: BalanceConfig = CONFIG) -> bool:
    """§F6 :1274 SmokeCmd 处理体——**自卫烟幕路径**（PB-53，断箭 N32/映射 §五.19；
    与迫击炮烟弹体系并存：§F6 武器烟弹路径——查 SMOKE 武器档+射程门③A+SCATTER
    散布+耗弹装填+声测喂入 AMB-14/17②——未落地不冒充，见登记表 TODO）。
    门序（拍板文本「发数门→冷却门」）：① self_smoke_left<=0 拒令（含模板 0 发=
    无能力——哪些车配属=数据卡配置侧，现役 0 卡配属 P-121）；② world.tick<
    self_smoke_ready_tick 拒令（冷却自受令拍起算；并含在途守卫 pop_tick>=0——
    上一发未落烟不开第二发，默认 delay<cooldown 下被①②覆盖不可达，防退化配置
    受令覆盖 pop_tick 丢发）。受令即耗 1 发+落 N32「固有部署延迟」：pop_tick=
    now+cfg.self_smoke_delay_ticks，system_timers 到拍以**元素当前位置**为心
    append SmokeZone（半径/时长复用 cfg.smoke_radius_cm/smoke_ttl_ticks——勘察
    两案取「以车为心圆」简化案，车尾/侧向偏移无断箭证据 defer；落点车锚定 ⇒
    本路径不消费 point，该形参保留给武器烟弹路径）；不占武器弹药/补给轨（抽象
    发数与 D044 炮弹两轨并存，mark_resupply_if_needed 不调）。载具延迟窗内被毁
    →烟幕取消发数不退（system_timers 跳过 dead 单位）。零掷骰（不触任何 PCG32
    通道）。"""
    if element.self_smoke_left <= 0:                                     # ① 发数门
        return False
    if world.tick < element.self_smoke_ready_tick \
            or element.self_smoke_pop_tick >= 0:                         # ② 冷却门（含在途守卫）
        return False
    element.self_smoke_left -= 1
    element.self_smoke_pop_tick = world.tick + cfg.self_smoke_delay_ticks
    element.self_smoke_ready_tick = world.tick + cfg.self_smoke_cooldown_ticks
    return True


# ── §F6 cmd_garrison / cmd_un_garrison（:1248-1255——PB-57 驻楼命令块，2026-10-06）──

def cmd_garrison(world: World, unit, building) -> bool:
    """§F6 :1248-1251 进驻处理体（GarrisonCmd 分派支承载；v1.6 清单⑨A 拍板「最小
    实现」：驻楼=隐蔽+3 + 受击按尾甲——两效果由消费端既有接线承载
    （sensing.effective_stealth_x10 AMB-02 合取式 / compute_hit_facing 驻楼 REAR），
    本函数只写引用）。门照伪代码字面两门 + 一处完整性收口：
      ① NOT canGarrison（§D.1 模板 flags 位）→ REJECT——现役 0 卡置位
        （ground_cards.csv flags 列无 CAN_GARRISON，GDD-02 v1.9:50 侦察班卡面
        承诺无数据承载——数据侧脱节登记见登记表 discrepancies）；
      ② 容量按排（单位数）计：garrison_slots <= 楼内不同单位 id 数 → REJECT
        （2026-10-06 发起人拍板「小/中/大楼=1/2/3 排、按单位整体判一次再全体
        塞入」——多元素单位=1 排，原元素计数超容缺口随拍板消解；garrisoned 仍按
        元素记=§D.6 :229 字面+三清理路径不变）；
      ③ 塌楼建筑（hp<=0）REJECT——伪代码 :1248 未列此门；§F4 :768-771 失的守卫
        同款判据的进驻侧收口（塌楼已出 world.buildings，驻入将产生永不可达引用
        且白吃隐蔽加成），留痕可推翻。
    无距离门（伪代码 :1248-1250 仅兵种+容量两门——全场遥控驻楼可达，命令即挂
    引用无贴近校验；ask 序言「距离门」与伪代码不符，按伪代码口径不补门，留痕
    待发起人确认）。接受=逐元素 e.garrison_in=building + building.garrisoned.
    append(e)（:1250 字面）；不写 e.pos（伪代码无此写点——楼内单位保持原位，
    弹丸起点/索敌位置不变，驻楼射击照常直射无修正）；已驻楼元素换楼驻入时旧楼
    garrisoned 条目随引用改写同步移除（双向不变式 e.garrison_in=b ⇔ e ∈
    b.garrisoned——destroy_element/collapse_building/移动出楼三清理路径共守；
    伪代码 :1250 直覆盖未及，登记）。零掷骰（不触任何 PCG32 通道）。"""
    if not (unit.template.flags & UnitFlag.CAN_GARRISON):                 # ① 兵种门
        return False
    occupied_platoons = len({e.unit.id for e in building.garrisoned})    # ② 容量门：按排
    #    （单位数）计——2026-10-06 发起人拍板（garrisoned 按元素记、门数不同单位 id）
    if building.garrison_slots <= occupied_platoons:
        return False
    if building.hp <= 0:                                                  # ③ 塌楼完整性收口
        return False
    for e in unit.elements:
        old = e.garrison_in
        if old is not None and any(x is e for x in old.garrisoned):
            old.garrisoned = [x for x in old.garrisoned if x is not e]    # 换楼：旧楼条目同步移除
        e.garrison_in = building
        building.garrisoned.append(e)
    return True


def cmd_un_garrison(world: World, unit) -> None:
    """§F6 :1253-1255 出楼处理体（UnGarrisonCmd 分派支承载）：无资格门（伪代码
    :1253 无——未驻楼单位出楼为无操作零副作用）。逐元素（WHERE garrison_in !=
    NULL）：清双向引用 + e.pos=楼旁落位——落位偏移 v1.7 未定标，取楼锚同点位
    （destroy_element 车毁旁落位 combat.py「同点位——偏移未定标」同款登记；
    驻楼本不写 e.pos，同点位=元素贴楼锚）。garrisoned 移除按身份（is 过滤——
    防御性改写：2026-10-06 评审实验复核伪代码字面 .remove(e) 在 id 纪律下行为
    正确，ElementInstance 无 eq=False 保留防御式；combat.py destroy_element
    ⑤块「按身份除名」同款口径）。不写 unit.pos（伪代码只写 e.pos——单位锚
    随下次移动令重锚）。零掷骰。"""
    for e in unit.elements:
        b = e.garrison_in
        if b is None:
            continue
        if any(x is e for x in b.garrisoned):
            b.garrisoned = [x for x in b.garrisoned if x is not e]
        e.garrison_in = None
        e.pos = b.pos                                                   # 楼旁落位（同点位——偏移未定标）


# ── §F6 cmd_set_sniper_cover / buy_supplies（:1258-1267/:1215-1225——PB-56 批③
#    支援链命令块，2026-10-06）──

def cmd_set_sniper_cover(world: World, sniper_unit, target_unit) -> bool:
    """§F6 :1258-1267 反狙击掩护处理体（SetSniperCoverCmd 分派支承载；方案9 旁表
    唯一写者——落地前消费端 resolve_sniper_hit covered 乘区/unregister 双向清理
    均既有零改动）。门序照伪代码字面四门：
      ① NOT canSniperCover（§D.1 模板 flags 位）→ REJECT——现役 0 卡置位
        （ground_cards.csv flags 列无 CAN_SNIPER_COVER，且无狙击组卡——R-02 链
        数据侧双缺位照登，CAN_GARRISON 追认补卡先例在，补位随数值章节/数据侧，
        测试用合成模板）；
      ② target.team != sniper.team → REJECT（v1.6 ⑳A 同队门：「友军」限定落门——
        原可对敌挂掩护同时压低我方狙击对敌概率=自伤型误操作）；
      ③ NOT target.alive OR target.elements==[] → REJECT（目标存活）；
      ④ target==sniper → REJECT（非自身；恒等判 is——UnitInstance dataclass eq
        按 id 首字段短路，id 唯一 ⇒ 与 == 等价）。
    替换语义（1:1 约束——每狙击同时只掩护一个友军）：遍历 cover_by_target 按插入序
    把该狙击从旧 protectors 移除（**空键删除收口**：伪代码 :1265-1266 未删空键——
    消费=键存在性布尔（combat.py:457），留洞则换目标后旧目标零掩护者仍恒享减半
    保护；IMPL :492 unregister 侧 v1.3 已修同款洞（「空键不删→掩护者全灭后目标恒判
    covered（终审遗留）」），本处同款收口，留痕可推翻）；移除**按身份过滤改写**
    （is 过滤——unregister combat.py:261/驻楼按身份除名同款口径；伪代码 .remove
    字段相等语义有跨单位误删风险）。Python dict 迭代期删键=快照 list(keys()) 迭代
    （unregister :259 同款）。末写 cover_by_target[target_unit.id].append(sniper_unit)
    （键不存在则建——setdefault；键型=unit.id：v1.7 键型 unit 的已登记实现适配
    〔UnitInstance mutable 不可哈希，tick.py 旁表注释/消费端 combat.py:457 同口径〕，
    值=掩护者 unit 对象列表配 identity 清理）。重挂同目标=移除后重插（插入序移尾
    ——「按插入序 map」字面行为，无净状态差）。零掷骰（纯指针/整数写）。"""
    if not (sniper_unit.template.flags & UnitFlag.CAN_SNIPER_COVER):     # ① 资格门
        return False
    if target_unit.team != sniper_unit.team:                             # ② ⑳A 同队门
        return False
    if not target_unit.alive or not target_unit.elements:                # ③ 目标存活门
        return False
    if target_unit is sniper_unit:                                       # ④ 非自身门
        return False
    for tgt_id in list(world.cover_by_target):                          # 替换：快照迭代
        protectors = world.cover_by_target[tgt_id]
        if any(p is sniper_unit for p in protectors):
            world.cover_by_target[tgt_id] = [p for p in protectors
                                             if p is not sniper_unit]
            if not world.cover_by_target[tgt_id]:
                del world.cover_by_target[tgt_id]     # 空键删（:492 unregister 同款收口）
    world.cover_by_target.setdefault(target_unit.id, []).append(sniper_unit)
    return True


def buy_supplies(world: World, truck_element, rounds: int, medical: int,
                 cfg: BalanceConfig = CONFIG) -> bool:
    """§F6 :1215-1225 补给购买/装填处理体（BuySuppliesCmd 分派支承载；CARGO 载具
    物资池除 spawn_airdrop_crate 预填外的第二个写者——SetMode(CARGO)〔批①〕→
    BuySupplies〔本块〕→system_supply ⑥ 补弹/医疗〔既有〕装货整链首次全通）。
    门序照伪代码字面五门：
      ① NOT 有 hasSupply 槽 → REJECT（方案12：非补给载具直接拒绝）——实现判据=
        UnitFlag.HAS_SUPPLY（types.py:190，airdrop_crate_template GAP-21「漏配则
        物资槽不分配」同一位；supply_weight_g None 判不可用=make_unit 未承载
        §D.5#16/17 分配、BuySupplies 本身即首写者，None 判将自锁门①）。现役
        SU_TRUCK flags 空（ground_cards.csv 第 8 行）→ 现役恒 REJECT——数据侧
        补位另裁（勘察 decisionPoints 登记，CAN_GARRISON 追认先例在）；
      ② mode != CARGO → REJECT（v1.3 审查#8：仅物资模式可装货——运兵/拖曳/直射
        模式不可预装，与 cmd_set_element_mode ③ 切出 CARGO 卸货清零共守互斥）；
      重量式（M15/G21）：weight = rounds×cfg.supply_round_weight_g
        + medical×cfg.med_weight_per_unit_g——两常数 §D.0 :73-74 出表
        （med=5 定值 / round 标「待定」→占位 1g，D012 满额互算+per-weapon
        ammo_weight 占位同值，tables.py 段注）；
      ③ rounds > template.cargo_rounds_max → REJECT（M1 勘误：truck_element.template
        直达——ElementTemplate 槽 types.py:273，无换写需求）；
      ④ medical > template.cargo_medical_max → REJECT；
      ⑤ weight > template.cargo_weight_max → REJECT（D012 混装载重闸）。
    **写点换写（规格字段勘误，批① cmd_set_element_mode ③ 同类别先例）**：:1225 写
    truck_element.supply_rounds/supply_medical 两字段代码不存在——2026-10-03 拍板
    「弹药/医疗一池按重量计」后唯一槽=ElementInstance.supply_weight_g（types.py:362），
    换写 supply_weight_g=weight（赋值语义：伪代码对两槽直赋值，一池化等价换写=换装
    而非补装；条件槽首次写入即分配——cargo_units 惰性分配 mount_requests_step 同款，
    方案12）。**负值防御门（输入纪律，可推翻）**：rounds/medical<0 → REJECT——伪代码
    未列，门序③④⑤为 > 比较对负数恒放行、直写将产生负池（system_supply weight<=0
    早退=惰性腐化）；cmd_set_element_mode 裸 int 归一拒令（批①评审#3「显式拒令
    可测」）同款口径。零掷骰（门序+乘加整数运算，不触任何 PCG32 通道）。"""
    if rounds < 0 or medical < 0:                                        # 输入纪律（防御门）
        return False
    if not (truck_element.unit.template.flags & UnitFlag.HAS_SUPPLY):    # ① 补给载具门
        return False
    if truck_element.mode is not Mode.CARGO:                             # ② 仅物资模式
        return False
    weight = (rounds * cfg.supply_round_weight_g
              + medical * cfg.med_weight_per_unit_g)                     # M15/G21 重量式
    if rounds > truck_element.template.cargo_rounds_max:                 # ③ 弹药舱位
        return False
    if medical > truck_element.template.cargo_medical_max:               # ④ 医疗舱位
        return False
    if weight > truck_element.template.cargo_weight_max:                 # ⑤ D012 载重闸
        return False
    truck_element.supply_weight_g = weight                               # 一池换写（直赋值）
    return True


def system_combat(world: World, unit: UnitInstance, cfg: BalanceConfig = CONFIG) -> None:
    """§F4 :674-691：① AIMING 到期结算（finish_aim——对空/地面出口全承载）+
    ② 对空自动交战（aa_roster 名单，恒自动/并行/不受 stance·mode 影响——R-17）+
    ③ 对地按元素 mode 分流（DIRECT→ground_direct / INDIRECT 且模板 INDIRECT 位→
    indirect_role——方案3 静态门；TOW/CARGO/TRANSPORT 不开火，开火许可亦拦截）+
    尾部炮击任务推进（方案3：无 INDIRECT 位模板不问 + fire_mission 非 NULL +
    任一 INDIRECT 元素 → process_fire_mission）。"""
    air_mask = TargetDomain.AIR
    for e in list(unit.elements):
        for ws in e.weapon_states:                                     # ① AIMING 到期
            if ws.state is WState.AIMING and ws.timer <= 0:
                finish_aim(world, e, ws, cfg)
        if unit.alive and unit in world.aa_roster:                     # ② 对空（B5 修复核心）
            for ws in e.weapon_states:
                if (ws.template.target_mask & air_mask) and ws.state is WState.READY \
                        and ws.ammo_left > 0:
                    aa_try_engage(world, e, ws, cfg)
        if e.mode is Mode.DIRECT:                                      # ③ 对地分流（:685-687）
            ground_direct(world, unit, e, cfg)
        elif e.mode is Mode.INDIRECT and (unit.template.mode_set & (1 << Mode.INDIRECT)):
            indirect_role(world, unit, e, cfg)
    if ((unit.template.mode_set & (1 << Mode.INDIRECT))                # :689-691 方案3 静态门
            and unit.fire_mission is not None
            and any(e.mode is Mode.INDIRECT for e in unit.elements)):
        process_fire_mission(world, unit, cfg)


# ── §F8 system_projectiles（:1464-1474）──

def system_projectiles(world: World, cfg: BalanceConfig = CONFIG) -> None:
    """弹丸推进（step_toward）+ 到达分派（照 §F8 :1468-1473 行序）：
    BALLISTIC → resolve_blast（§F1 爆破/烟弹落点——含空投炸弹 AirProjectile
    鸭子兼容支）；hit_target=航空器 → resolve_hit_aa；will_hit → resolve_hit
    （§F1 地面命中——狙击/近战分支在内）；ELSE → 近失压制。"""
    keep = []
    for p in world.projectiles:
        p.pos, arrived = step_toward(p.pos, p.dest, p.speed_cm_tick)
        if not arrived:
            keep.append(p)
            continue
        if p.trajectory is Trajectory.BALLISTIC:
            resolve_blast(world, p, cfg)          # §F1 :1468（含烟弹落点）
        elif isinstance(p.hit_target, AircraftInstance):
            resolve_hit_aa(world, p, cfg)
        elif p.will_hit:
            resolve_hit(world, p, cfg)            # §F1 :1471（B9/方案1 分支在内）
        else:
            inject_suppression_area(world, p.dest, p.weapon.blast_radius_cm,
                                    p.weapon.suppression_power)        # 近失：仅压制
    world.projectiles = keep


# ── 士气状态机（GDD-00 D014 四态/D025 阈值制；GDD-05 下篇 B2 步9/B4 updateMorale
#    同构——2026-10-04 士气块。挂 world_tick ⑤后⑥前＝B2 字面序 suppression(8)→morale(9)
#    →logi(10)：本拍 ④交战/⑤弹丸 注入后的压制当拍即判态）──


def _enter_routed(world: World, cfg: BalanceConfig, u: UnitInstance) -> None:
    """溃逃进入/再进入拍（system_morale 唯一写点）：计时 + 清玩家令 + 内部通道装
    溃逃航点。issue_move 门1（收起中/展开中×handoff 拒）/门3（整班车载）拒装时=
    溃逃态成立但本段不动（展开中牵引炮/车内班随载具——载具自身士气独立判，登记表
    留痕）。DEPLOYED 单位溃逃=移动令触发收装同款（2026-10-07 拍板接线面）：handoff
    效果点转 PACKING+照装溃逃航点——收装完成前 system_move 同名门拦位移、收装毕
    自动溃逃走（「先收装再走」对失控移动同构成立）。零掷骰。"""
    u.morale = MoraleState.ROUTED
    u.routed_until = world.tick + cfg.morale_rally_ticks
    u.command_queue = []   # 清玩家令（D014「失控移动」——queue 内令一并失效）
    u.pivot_to = -1        # 互斥不变式 pivot_to>=0 ⇒ move_path 恒空（cmd_pivot 停车同款）
    u.move_path = []
    issue_move(world, cfg, MoveCmd(unit=u, path=[_deploy_anchor(world, u.team)],
                                   mode=MoveMode.NORMAL), handoff=True)
    # ↑ handoff 内部通道（BLK-1 同款）：只装 move_path+换 mode 不清 cap；prefer_road=
    # （mode is MARCH）=False（勘察口径）。目的地=己方部署区锚点 _deploy_anchor
    # （spawn 同款「己方底边中点」拍板口径——PB-35 正式部署区数据缺失=近似方向，
    # 接入后随 _deploy_anchor 一并换锚，零新地图数据）


def system_morale(world: World, cfg: BalanceConfig = CONFIG) -> None:
    """GDD-00 D014/D025 士气四态阈值状态机（确定性判定零掷骰——不触任何 PCG32 通道）。

    层级（勘察最简整数方案）：压制保持元素级不动（ElementInstance.suppression，
    inject_suppression 封顶 100——GDD-05 B1:99 单位级 0..150+ 为规格侧口径未随本块
    改标，留痕=tables.py BalanceConfig 士气段注释/拍板清单 PB-54）；士气=单位级由存活元素压制聚合派生——聚合=**max**
    （最差元素；PB-49 语义自洽：最差元素钉住即单位钉住）。「能算出来的不存」：
    morale 槽每拍重写，不另存聚合值。

    迁移（D025 阈值制；衰减回落降档——衰减本体=既有 ①system_timers 环不动）：
    - 非 ROUTED：sup_agg≥rout_th→ROUTED；≥pin_th→PINNED；≥sup_th→SUPPRESSED；
      否则 STABLE。三档阈值出 BalanceConfig 士气段占位（D025「数值待配」；标尺维持
      现 0..100——B4 50/100/150 需抬 inject 封顶并重标 sup_penalty_bp 连续消费链未采）。
    - 阈值三级回退（2026-10-04 士气效果接线块——D027:174 卡级「士气阈值（受压/钉住/
      溃逃）」三列落地消费）：单位级覆盖（template.morale_{sup,pin,rout}_th>0，
      card 管线列，0=回退哨兵——PB-52 三级回退范式）> cfg 缺省；列间独立回退（可只
      覆盖单档——如 rout_th 抬到 >100=该卡不溃逃的差异化配置位）。拼出后的**有效阈值
      须严格递增 sup<pin<rout**——运行期防御断言（2026-10-04 评审遗留⑤：单侧显式+
      单侧回退 cfg 的非单调组合构建期不判（card_schema 只拦双双侧显式），此处抛错
      暴露数据问题——非单调在下方 elif 阶梯下产生不可达档；现役全空数据恒单调
      =零行为差）。
    - ROUTED=计时态：routed_until 前不随压制衰减降档（溃逃持续整段——B4:182「30s
      后原地重整」字面）；到拍重整：sup_agg 仍≥rout_th→再溃逃（新计时+重装溃逃航点
      ——仍在碾压火力下）；否则回 SUPPRESSED（B4:182 默认=D014 待定②处置留痕；次拍
      起按当前压制正常降档，衰减已尽即回 STABLE）、清溃逃航点=原地重整、复位 -1。

    溃逃失控门族（D014「失控」语义）：issue_move 门0（含 queue 入队）/cmd_halt/
    cmd_pivot/cmd_sprint/consume_unit_commands 五处拒外部机动族令——溃逃航点唯一
    清写点=本函数重整拍。命中侧消费维持连续线性（aim/reload_factor_bp 随元素压制）
    ——B4:149 moraleFactor 按态乘区未拍板不替（登记表留待项③）。

    D014 三待定项处置（2026-10-04 士气块，占位可推翻）：①重整时长=morale_rally_ticks
    =300t（B4:182「30s」默认）；②重整后回到=SUPPRESSED（同上）；③军官/政委加速重整
    =D034 已规划、实现形态（扩 AuraKind 士气类 vs 督战独立主动命令）随指挥单位块
    拍板——rally_ticks 出表为可乘基数（aura_bonus_bp 连乘先例可直套）无架构锁死。"""
    for u in world.units:
        if not u.alive:
            continue
        tpl = u.template                                  # D027:174 单位级阈值三级回退
        sup_th = tpl.morale_sup_th if tpl.morale_sup_th > 0 else cfg.morale_sup_th
        pin_th = tpl.morale_pin_th if tpl.morale_pin_th > 0 else cfg.morale_pin_th
        rout_th = tpl.morale_rout_th if tpl.morale_rout_th > 0 else cfg.morale_rout_th
        if not sup_th < pin_th < rout_th:   # 运行期防御断言（评审遗留⑤）：单侧显式+
            raise ValueError(               # 单侧回退可拼出非单调有效阈值（构建期只拦
                # 双双侧显式），elif 阶梯下产生不可达档——抛错暴露数据问题
                f"unit {u.template.template_id} 士气有效阈值须严格递增 "
                f"sup<pin<rout（得 {sup_th}/{pin_th}/{rout_th}）")
        sup_agg = 0
        for e in u.elements:
            if e.suppression > sup_agg:
                sup_agg = e.suppression      # 聚合=max 存活单位内元素压制（含车载班）
        if u.morale is MoraleState.ROUTED:
            if world.tick < u.routed_until:
                continue                      # 计时态：整段失控，不随衰减降档
            if sup_agg >= rout_th:
                _enter_routed(world, cfg, u)  # 重整拍仍在碾压火力下：再溃逃（新计时+重装）
            else:
                u.morale = MoraleState.SUPPRESSED   # B4:182 默认回受压态（待定②留痕）
                u.routed_until = -1
                u.move_path = []              # 原地重整：清溃逃航点（下一拍起恢复受令）
                u.move_mode = MoveMode.NORMAL
            continue
        if sup_agg >= rout_th:
            _enter_routed(world, cfg, u)
        elif sup_agg >= pin_th:
            u.morale = MoraleState.PINNED
        elif sup_agg >= sup_th:
            u.morale = MoraleState.SUPPRESSED
        else:
            u.morale = MoraleState.STABLE


# ── §F6 cmd_mount/cmd_dismount（:1131-1168——PB-56 批② 机动链命令块·上下车，
#    2026-10-06；消费端 seat_usage/pending_mount_count/mount_requests_step 既有）──


def cmd_mount(world: World, squad_elements, carrier_unit,
              cfg: BalanceConfig = CONFIG) -> bool:
    """§F6 :1137-1168 上车处理体（MountCmd 分派支承载；v1.6 ㉑A【按推荐拍板·
    可推翻】班元素粒度——逐班选最少挂载载具并逐班占座）。门序照伪代码字面
    ①-⑪（FOR s IN squad_elements 按列表序；逐班 CONTINUE=该班跳过、其余班继续
    分配——部分成功为逐班语义，ok==0 才整体 REJECT）：
      ① s 非 SQUAD 元素 → CONTINUE（只挂班元素）；
      ② 按班元素去重：ANY(r.squad_element is s) → CONTINUE（挂起请求在途不重发；
        按身份判——ElementInstance 无 eq=False，字段相等有 unit 互指递归风险，
        cmd_set_element_mode ⑤ is 过滤同款口径）；
      ③ 挂载即出楼（v1.5 M11/G24）：ANY(e.garrison_in≠NULL FOR e IN s.unit.elements)
        → cmd_un_garrison(world, s.unit)（无条件先行——伪代码次序字面：即便该班
        后续被 ⑥-⑨ 跳过出楼也已发生，侧置留痕）；
      ④ carriers=[carrier_unit.elements 中 seats>0]；⑤ 最少挂载逐班重选
        (seat_usage+pending_mount_count) 最小者（v1.4/v1.6 ㉑A——前班占座后次班
        自然落到次空闲车，3班→3车形态可重建；并列取列表序首=确定性；本命令内
        逐班 append 的在途请求即时入账）；⑥ carrier==NULL → CONTINUE；
      ⑦ carrier.mode ∈ {CARGO, TOW} → CONTINUE（v1.4：载货/拖曳不载人）；
      ⑧ mode_set 含 TRANSPORT 位且 mode≠TRANSPORT → CONTINUE（v1.5 M13/G18：
        卡车三模式须处 TRANSPORT 才可载人；251 等无位载具不受限）
        〔**规格字段勘误**：:1160 写 carrier.template.mode_set——carrier 为
        ElementInstance，ElementTemplate 无 mode_set 槽（照写即 AttributeError），
        mode_set 在 UnitTemplate（types.py），按 cmd_set_element_mode ①/cmd_tow
        :1239 同款先例换写 carrier.unit.template.mode_set——批① supply_rounds→
        supply_weight_g 换写先例同类别〕；
      ⑨ seat_usage+pending+1 > seats → CONTINUE（上限含在途——逐班判）；
      ⑩ 惰性建表（方案12：过 ⑨ 即建——伪代码置于 ⑪ 前，⑪ 不中亦已建空表，
        字面落地）；
      ⑪ 「s 静止于 carrier 旁 AND carrier 静止」→ append MountRequest
        {squad_element=s, carrier, ticks_left=cfg.mount_time_ticks}（R-07 上车
        20s=200 拍）。
    **「旁」定标=同点位判（可推翻拍板项，勘察 decisionPoint#2 推荐案 i）**：
    dist_cm(s.unit.pos, carrier.unit.pos)==0——「旁」全仓无距离常数（tables.py
    各 radius 均有 GDD 锚，此处 GDD-02 v1.9:111 仅「在静止车辆处」），点单位
    可叠放（PB-16 拍板）+ spawn 锚点全员同点 → 零新常数同点位判；跨卡场景
    步兵须先走到载具单位锚点才可上（vs 全场遥控驻楼先例的无门案）——玩法
    可达性差异留痕待发起人裁。「静止」=not s.unit.moving() and not
    carrier.unit.moving()（moving()=bool(move_path)，元素级无移动状态——单位级
    粒度登记）。已挂载班无再挂防护=伪代码字面缺口（去重仅查挂起请求：已
    mounted_in 的班可再获新请求，到期覆写 mounted_in——窗口内座位双记、
    seat_usage 事后自纠，低危照字面登记）。零掷骰（纯整数指针计数，不触任何
    PCG32 通道）。"""
    ok = 0
    for s in squad_elements:                                              # 按列表序
        if s.template.element_type is not ElementType.SQUAD:              # ① 只挂班元素
            continue
        if world.mount_requests is not None and any(
                r.squad_element is s for r in world.mount_requests):      # ② 按班元素去重
            continue                                                     #   （挂起在途不重发）
        if any(e.garrison_in is not None for e in s.unit.elements):       # ③ 挂载即出楼
            cmd_un_garrison(world, s.unit)                               #   （M11/G24——无条件先行）
        carriers = [e for e in carrier_unit.elements
                    if e.template.seats > 0]                             # ④ seats>0 载具
        carrier = None                                                   # ⑤ 最少挂载逐班重选
        best = None                                                      #   （并列取列表序首）
        for c in carriers:
            load = seat_usage(c) + pending_mount_count(world, c)
            if best is None or load < best:
                best, carrier = load, c
        if carrier is None:                                              # ⑥ 无载具可用
            continue
        if carrier.mode in (Mode.CARGO, Mode.TOW):                       # ⑦ 载货/拖曳不载人
            continue
        if ((carrier.unit.template.mode_set & (1 << Mode.TRANSPORT))
                and carrier.mode is not Mode.TRANSPORT):                 # ⑧ M13/G18 三模式门
            continue
        if (seat_usage(carrier) + pending_mount_count(world, carrier) + 1
                > carrier.template.seats):                               # ⑨ seats 上限（含在途）
            continue
        if world.mount_requests is None:                                 # ⑩ 惰性建表（方案12）
            world.mount_requests = []
        if (dist_cm(s.unit.pos, carrier.unit.pos) == 0                   # ⑪ 「旁」=同点位
                and not s.unit.moving() and not carrier.unit.moving()):  #    （可推翻拍板项）
            world.mount_requests.append(MountRequest(
                squad_element=s, carrier=carrier, ticks_left=cfg.mount_time_ticks))
            ok += 1
    return ok > 0                                                        # ok==0 整体 REJECT


def cmd_dismount(world: World, squad_unit) -> None:
    """§F6 :1131-1136 下车处理体（DismountCmd 分派支承载）：无资格门/无 REJECT
    （伪代码无返回值——未挂载单位下车=无操作零副作用）。逐元素（WHERE
    mounted_in≠NULL AND element_type==SQUAD——v1.6 ㉑A 口径，VEHICLE 元素等
    非 SQUAD 挂载引用不在此清）：carrier=e.mounted_in；e.pos=carrier.pos 旁落位
    （偏移未定标取载具同点位——destroy_element 车毁旁落位 combat.py/cmd_un_garrison
    出楼旁落位/cmd_set_element_mode ④ TRANSPORT 卸客三处同款登记先例）；清
    e.mounted_in；跨卡（squad_unit is not carrier.unit）且 cargo_units 非 None →
    cargo_units 移除本班单位。**按身份过滤改写**（防御性改写——2026-10-06 批②
    评审#2 勘正：cargo_units 装载 UnitInstance（types.py，id 首字段短路等值），
    原注「ElementInstance 字段相等有递归风险」类型标注失准；按身份过滤与
    cmd_set_element_mode ⑤/PB-57 驻楼块「防御性改写非正确性必需」同口径）。不写 squad_unit.pos（伪代码
    只写 e.pos——单位锚随下次移动令重锚）。零掷骰。"""
    for e in squad_unit.elements:
        if (e.mounted_in is None
                or e.template.element_type is not ElementType.SQUAD):    # WHERE 双谓词
            continue
        carrier = e.mounted_in
        e.pos = carrier.pos                        # 旁落位（同点位——偏移未定标登记）
        e.mounted_in = None
        if (squad_unit is not carrier.unit                                 # 跨卡：双向引用同步清
                and carrier.cargo_units is not None                        # （v1.3——原漏清→
                and any(x is squad_unit for x in carrier.cargo_units)):   #  下车班被拴回卡车死锁）
            carrier.cargo_units = [x for x in carrier.cargo_units
                                   if x is not squad_unit]                 # 按身份移除


# ── §F6 cmd_deploy/cmd_pack_or_move/cmd_tow/cmd_untow（:1072/:1116/:1228/:1242——
#    PB-56 批② 机动链命令块·拖曳展开，2026-10-06；消费端 system_timers 展开收装
#    计时/fire_permitted ③⑤ 门/拖曳锁速与随动 movement.py/stop_tow·release_
#    tow_if_involved combat.py 全部既有）──


def cmd_deploy(world: World, unit) -> None:
    """§F6 :1072-1115 展开令处理体（DeployCmd 分派支承载；v1.6 终审修复 1b 元素
    粒度【可推翻】——授权链 docs/.zcode/workflow-runs/dwfrun-23ebdd22-…mjs FIX5
    第 1 条第二分句「禁止边拖边展开门改元素粒度（仅被拖门不可展开，留守门可）」，
    伪代码 :1073-1082 在库可核）。写点照伪代码字面：
      ① IF MOBILE → DEPLOYING + deploy_timer=template.deploy_time_ticks（timer
        写入在分支内——M18/A20：DEPLOYING 期重复下达不重置进度、PACKING 期下达
        状态不迁移不覆盖计时器）；
      ② ELIF DEPLOYED AND ANY(e.redeploy_needed WHERE e.towed≠TOWED)（GAP-09
        作用域过滤——「拖走 1 门留守 3 门」时被拖门的旗被 WHERE 排除、ELIF 不中，
        全连不空走 30 秒留守门保持可开火）→ DEPLOYING + deploy_timer=
        deploy_time_ticks（v1.5 终审修 1a：解挂重展开须有时长承载——原实现对该
        状态只清旗零成本、被拖门解挂后下 cmd_deploy 即时恢复开火与 C3 自身注释
        直接矛盾；本分支即 v1.4「被拖单位须 MOBILE」门删除后的替代闸：含旗元素
        的 DEPLOYED 单位回 DEPLOYING 重走展开时长，期间 needs_deployed 门
        （deploy_state≠DEPLOYED）自然禁射全连〔AMB-11 拍板：重展开窗口全连禁射
        为连级展开制固有代价、正式接受〕）；
      ③ FOR e WHERE 有 redeploy_needed 槽 AND e.towed≠TOWED → redeploy_needed=
        FALSE（C3 清旗范围限非拖曳中元素——被拖元素保持 TRUE 不进本次展开作用域；
        TOWING 牵引元素正常清〔其禁射由 fire_permitted ⑤ 拖曳门另拦〕。〔条件槽〕
        代码 ElementInstance.redeploy_needed 恒有槽（types.py 默认 False），「仅
        GUN/可被拖 MECH 分配」的槽语义照字面以 towed≠TOWED 谓词承载——对无条件
        槽元素写 False→False 无害）。
    G17 旁路由元素旗闭合：被拖元素 redeploy_needed 于 start_tow 置位且拖曳中
    不清（③ 排除 TOWED）——解挂后仍须再下本命令走 ② 重展 30 秒方可开火，
    「到位后展开 30 秒」不可旁路。无 REJECT（伪代码无返回值——DEPLOYING/PACKING
    期下达=两分支均不中无操作）。零掷骰（纯整数状态写点，不触任何 PCG32 通道）。"""
    if unit.deploy_state is DeployState.MOBILE:                     # ① 首展开
        unit.deploy_state = DeployState.DEPLOYING
        unit.deploy_timer = unit.template.deploy_time_ticks
    elif (unit.deploy_state is DeployState.DEPLOYED                  # ② GAP-09 重展开
          and any(e.redeploy_needed and e.towed is not TowState.TOWED
                  for e in unit.elements)):
        unit.deploy_state = DeployState.DEPLOYING
        unit.deploy_timer = unit.template.deploy_time_ticks
    for e in unit.elements:                                          # ③ C3 清旗
        if e.towed is not TowState.TOWED:
            e.redeploy_needed = False


def cmd_pack_or_move(world: World, unit) -> None:
    """§F6 :1116-1118 收装/进度作废处理体（PackCmd 分派支承载——复合入口
    「PackCmd / MoveCmd 触发」的 PackCmd 半边；**MoveCmd 半边已接线（2026-10-07
    发起人拍板：pack_or_move 移动触发面=采 IMPL 字面——真两难就此闭账，登记表
    PB-56 批② 留待项① 收口）**：接线落点=movement.issue_move 效果点（门2/3/4 后
    ——拒令零副作用）：DEPLOYING×外部移动令=作废回 MOBILE 同拍放行（=本函数 ②
    同款作废）；DEPLOYED（外部非排队/内部 handoff 两通道）=转 PACKING+本令照常
    安装、收装完成前 system_move 同名门拦位移、收装毕自动续走（=本函数 ① 同款
    收装——「先收装再走」）；PACKING 拒令维持）。两 IF 字面（独立 IF 非
    elif——PACKING 期下达=两 IF 均不中=无操作，照字面）：
      ① IF DEPLOYED → PACKING + deploy_timer=pack_time；
      ② IF DEPLOYING → MOBILE + deploy_timer=0（进度作废）。
    〔规格字段勘误〕:1117 写 pack_time——代码字段=UnitTemplate.pack_time_ticks
    （types.py，card_loader 同名映射），照 deploy_time_ticks 先例换名写。
    零掷骰。"""
    if unit.deploy_state is DeployState.DEPLOYED:                    # ① 收起需时长
        unit.deploy_state = DeployState.PACKING
        unit.deploy_timer = unit.template.pack_time_ticks
    if unit.deploy_state is DeployState.DEPLOYING:                   # ② 展开进度作废
        unit.deploy_state = DeployState.MOBILE
        unit.deploy_timer = 0


def cmd_tow(world: World, tower_elements, towed_element) -> bool:
    """§F6 :1228-1241 拖曳令处理体（TowCmd 分派支承载；v1.3 元素级审查#12+v1.4
    互斥门+v1.7 GAP-10 三资格门）。门序照伪代码字面：
      ① 同队门：ANY(t.unit.team≠towed.unit.team) → REJECT（GAP-10——R-19「保车」
        体系锚定己方，原无校验可拖走敌方火炮变相控制）；
      ② 合法被拖对象门：GUN 元素 OR（MECH 元素×unit.template.mode_set 含 TOW 位）
        → 否则 REJECT（GAP-10——排除 SQUAD 班/空投箱 CARGO 元素/一切无 TOW 位卡；
        「MECH×TOW 位」被拖=卡车可拖卡车字面行为〔现役 SU_TRUCK own_weight_tons
        空=0，吨位门恒满足退化合法〕——伪代码字面登记，补「自重>0 才可被拖」或
        数据侧补卡车自重随数值章节）；
      ③ 逐 tower 三门（任一不中整体 REJECT）：t.towed≠NONE → REJECT（C1 双态——
        已在拖〔TOWING/TOWED〕的元素不可再挂）；mode_set 含 TOW|CARGO|TRANSPORT
        任一位且 t.mode≠TOW → REJECT（D065 互斥——载具须先 SetModeCmd(TOW)，
        cmd_set_element_mode 批① 已落）；mode_set 无 TOW 位 → REJECT（牵引资格
        =TOW 位，§D.1#15 数据硬要求）；
      ④ start_tow(world, tower_elements, towed_element)——失败静默拒绝（:1241
        字面；返回值透传供测试/调用方观测：三门外吨位不足/函数级兜底门不中均为
        False）。零掷骰（门序+start_tow 稳定排序纯整数，不触任何 PCG32 通道）。"""
    if any(t.unit.team != towed_element.unit.team for t in tower_elements):
        return False                                                # ① GAP-10 同队门
    if not (towed_element.template.element_type is ElementType.GUN
            or (towed_element.template.unit_type is UnitType.MECH
                and (towed_element.unit.template.mode_set & (1 << Mode.TOW)))):
        return False                                                # ② 合法被拖对象门
    for t in tower_elements:                                        # ③ 逐 tower 三门
        if t.towed is not TowState.NONE:                            #   C1 双态
            return False
        if ((t.unit.template.mode_set
             & ((1 << Mode.TOW) | (1 << Mode.CARGO) | (1 << Mode.TRANSPORT)))
                and t.mode is not Mode.TOW):                        #   D065 互斥
            return False
        if not (t.unit.template.mode_set & (1 << Mode.TOW)):        #   牵引资格=TOW 位
            return False
    return start_tow(world, tower_elements, towed_element)          # ④ 失败静默拒绝


def cmd_untow(world: World, element) -> None:
    """§F6 :1242-1245 解拖令处理体（UntowCmd 分派支承载）：无资格门/无 REJECT
    （伪代码无返回值——无涉元素=无操作零副作用）。涉本元素的拖曳对
    （tower_elements 含之或 towed_element 即之——**按身份判**，release_tow_
    if_involved GAP-24 元素级同构；快照列表迭代：stop_tow 原位过滤 world.tow_pairs）
    逐一 stop_tow(VOLUNTARY)。stop_tow 不清 redeploy_needed（C3）——解挂后须
    cmd_deploy 重展开（旗保持 TRUE 期间 fire_permitted ③ needs_deployed 门仍
    禁射=重展开链起点）。零掷骰。"""
    for pair in [p for p in world.tow_pairs
                 if any(t is element for t in p.tower_elements)
                 or p.towed_element is element]:
        stop_tow(world, pair, TowStopReason.VOLUNTARY)


# ── §F6 ⑥ 后勤 system_supply（:1308-1341）+ ⑦ 上车 mount_requests_step（:1169-1190）──
# stop_tow 2026-10-02 ⑤块迁 combat.py（destroy_element/release_tow_if_involved 消费
# 需要；顶部 import 再出口——tests `from sovs.sim.tick import stop_tow` 不变）。


def seat_usage(carrier) -> int:
    """§F6 :1121-1128 载具占用数（v1.6 ㉑A 元素粒度）：按 mounted_in 班元素指针计座
    （1 班=1 座）——同卡班元素 + 跨卡 cargo_units 内班元素统一账。"""
    n = sum(1 for s in carrier.unit.elements if s.mounted_in is carrier)
    if carrier.cargo_units is not None:                    # 跨卡：班元素挂载点亦为 mounted_in
        for squad in carrier.cargo_units:
            n += sum(1 for se in squad.elements if se.mounted_in is carrier)
    return n


def pending_mount_count(world: World, carrier) -> int:
    """§F6 :1129-1130 在途请求数：挂起装载请求占座（v1.4 I-19；方案12 惰性表
    None 视为空表）。"""
    if world.mount_requests is None:
        return 0
    return sum(1 for r in world.mount_requests if r.carrier is carrier)


def system_supply(world: World, cfg: BalanceConfig = CONFIG) -> None:
    """§F6 :1308-1341 ⑥ 后勤（R-18 自动补给 + R-19 维修；零掷骰）。
    2026-10-03 发起人拍板重设计：弹药/医疗两槽合并为一池按重量计的通用补给
    （supply_weight_g 克；None=未分配——原「双槽 None 半容错」崩溃面随合并消失）：
      - 主扫描 = 在场 CARGO 元素（supply_weight_g>0）× world.await_resupply（方案19
        扫描集）；R-21 同队门（GDD-02 为准修正：敌方不可拾取）+ supply_radius_cm
        半径门（含等号）不变；
      - 补弹（烟弹同轨原样——保留清单#10）：每发重量=ws.template.ammo_weight
        （占位 1，不同弹药不同重量，数值章节定标）——take = MIN(缺口,
        剩余重量//每发重量, cfg.ammo_resupply_per_tick)（发数限速、重量管池耗
        ⇒重弹吃池快）；扣重 take×每发重量；ws 为 EMPTY 且补后有弹即转 READY（方案19）；
      - 医疗仅 INFANTRY 且 0<hp<max（保留清单#9）：heal = MIN(缺口hp,
        剩余重量//cfg.med_weight_per_hp_g)，扣重 heal×med_weight_per_hp_g；
    尾部 await_resupply 自清理（u.alive AND needs_resupply——车毁/全灭/补满注销）；
    维修分支：repair_power_hp_per_tick>0 的元素 × 半径内（cfg.repair_radius_cm，M24）
    同队（GAP-10）受损 MECH（hp<max 或 crit 非空）——逐 tick 回血 repair_power；
    修满清 crit（D016）并解除其牵涉的拖曳对（stop_tow REPAIRED——R-19 修好即归队；
    GAP-24 元素级，仅涉本元素）。"""
    for u in world.units:
        for t in u.elements:
            if t.mode is not Mode.CARGO:
                continue
            weight = t.supply_weight_g or 0
            if weight <= 0:
                continue                                # 方案12：未分配恒 None / 已耗尽
            radius = u.template.supply_radius_cm
            for wu in world.await_resupply:
                if not wu.alive or wu.team != u.team:       # R-21 敌方不可拾取
                    continue
                if dist_cm(wu.pos, t.pos) > radius:
                    continue
                for e in wu.elements:
                    for ws in e.weapon_states:
                        if ws.ammo_left >= ws.template.ammo_base:
                            continue
                        per_round = ws.template.ammo_weight or 1   # 数据未填按 1g 占位
                        take = min(ws.template.ammo_base - ws.ammo_left,
                                   weight // per_round,
                                   cfg.ammo_resupply_per_tick)
                        ws.ammo_left += take
                        weight -= take * per_round
                        t.supply_weight_g = weight       # 烟弹同轨自动补（速率按重量）
                        if ws.state is WState.EMPTY and ws.ammo_left > 0:
                            ws.state = WState.READY         # 方案19：EMPTY 补给转 READY
                    if (e.template.unit_type is UnitType.INFANTRY
                            and 0 < e.hp_current < e.template.hp_max):
                        deficit = e.template.hp_max - e.hp_current
                        heal = min(deficit,
                                   weight // cfg.med_weight_per_hp_g)
                        e.hp_current += heal
                        weight -= heal * cfg.med_weight_per_hp_g
                        t.supply_weight_g = weight
    world.await_resupply = [u for u in world.await_resupply
                            if u.alive and needs_resupply(u)]   # 方案19 集合自清理
    for rep_u in world.units:
        power = rep_u.template.repair_power_hp_per_tick
        if power <= 0:
            continue
        for rep in rep_u.elements:
            for tgt_u in world.units:
                if tgt_u.team != rep_u.team:                # GAP-10 同队门（R-19 锚定己方）
                    continue
                for e in tgt_u.elements:
                    if e.template.unit_type is not UnitType.MECH:
                        continue
                    if dist_cm(e.pos, rep.pos) > cfg.repair_radius_cm:
                        continue
                    if not (e.hp_current < e.template.hp_max or e.crit):
                        continue                            # 方案7：crit 判空〔D071 口子④·恢复路径登记
                        # 2026-10-07：crit 槽无生产者恒空=门恒走 hp 判（零行为差）；重启暴击时本门
                        # 与下行 clear 原位即活——D016 修满清状态伤语义零改动〕
                    e.hp_current = min(e.template.hp_max, e.hp_current + power)
                    if e.hp_current >= e.template.hp_max:
                        e.crit.clear()                      # D016 修满清状态伤（D071 全拆后恒空 dict=
                        # 无操作——原位保留=恢复路径登记，口子④；tests/test_supply_mount 两锚在库）
                        for pair in [p for p in world.tow_pairs
                                     if any(x is e for x in p.tower_elements)
                                     or p.towed_element is e]:
                            stop_tow(world, pair, TowStopReason.REPAIRED)


def mount_requests_step(world: World) -> None:
    """§F6 :1169-1190 ⑦ 上车进度（R-07；零掷骰；每 tick）。方案12：无表即无请求
    （None 早退非异常）。逐条复核（v1.4 I-19 + v1.6 ㉑A 元素粒度）：载具/申请班
    任一方不在编、载具切出可载状态（mode ∈ {CARGO, TOW}）、座位超占
    （载具占用数+在途请求数 > seats）→ 撤销请求（不递减）。复核通过才递减
    ticks_left；到期逐班挂 mounted_in（㉑A），跨卡才入 cargo_units（单位级登记
    去重——座位实账走 mounted_in 指针，同单位多班挂同车不重复入表）。"""
    if world.mount_requests is None:
        return                                              # 方案12：惰性表
    for r in list(world.mount_requests):
        if (r.carrier not in r.carrier.unit.elements
                or r.squad_element not in r.squad_element.unit.elements
                or r.carrier.mode in (Mode.CARGO, Mode.TOW)
                or seat_usage(r.carrier) + pending_mount_count(world, r.carrier)
                > r.carrier.template.seats):
            world.mount_requests.remove(r)                  # 按身份（MountRequest eq=False）
            continue
        r.ticks_left -= 1
        if r.ticks_left <= 0:
            r.squad_element.mounted_in = r.carrier          # ㉑A：逐班挂载
            if r.squad_element.unit is not r.carrier.unit:  # 跨卡：cargo_units 单位级登记
                if r.carrier.cargo_units is None:
                    r.carrier.cargo_units = []
                if r.squad_element.unit not in r.carrier.cargo_units:
                    r.carrier.cargo_units.append(r.squad_element.unit)
            world.mount_requests.remove(r)


# ── §F7 经济与部署（:1374-1405）+ §F8 ⑧ system_economy（:1476-1479）+ D031 裁决 ──

def cmd_purchase(world: World, player, template, cfg: BalanceConfig = CONFIG) -> bool:
    """§F7 :1374-1379 出牌命令（仅盲部署 phase；零掷骰）。REJECT 三门：非盲部署相位 /
    卡组无此卡或余量尽（一命制：卡组余量不回补）/ 点数不足。接受则扣点、扣 DeckSlot
    份、卡入 spawn_queue（逐个间隔出牌）。deck_slots 查找按 template 身份（air.py
    装机扣份同口径）。"""
    if world.phase != PHASE_DEPLOY:                    # 仅盲部署 phase
        return False
    slot = next((s for s in player.deck_slots if s.template is template), None)
    if slot is None or slot.copies_left <= 0:          # 一命制
        return False
    if player.points < template.cost:
        return False
    player.points -= template.cost
    slot.copies_left -= 1
    player.spawn_queue.append(template)
    return True


def _deploy_anchor(world: World, team: int) -> tuple[int, int]:
    """己方部署区锚点（§F7 :1386）——部署区地图数据本仓库缺失：取己方底边中点
    （map_extent 推导；air_entry_point 同向约定：team0=南底边 y=0、team1=北底边
    y=h。见登记表 discrepancies）。"""
    return (world.map_center[0], 0 if team == 0 else world.map_extent[1])


def _infiltrator_spawn_pos(world: World, team: int) -> tuple[int, int]:
    """渗透卡出生点：任意地图边缘（敌方部署区除外，§F7 :1385 R-04）。"任意"无选取
    规则——2026-10-03 发起人拍板：随机选边（己方底边/西边/东边三选一，敌方底边除外）
    + 沿边均匀随机取点（含端点全长），ECONOMY 通道两掷（先选边 below(3)、后取点
    below(边长+1)，顺序冻结）；同种子完全可复现、不可背板（替代原"3 边中点按出牌
    序轮转"零掷骰实现——见登记表 discrepancies 拍板留痕）。"""
    width, height = world.map_extent
    eco = world.rng.economy()
    edge = eco.below(3)                                # 0=己方底边 1=西边 2=东边
    if edge == 0:
        return (eco.below(width + 1), 0 if team == 0 else height)
    if edge == 1:
        return (0, eco.below(height + 1))
    return (width, eco.below(height + 1))


def spawn_step(world: World, cfg: BalanceConfig = CONFIG) -> None:
    """§F7 :1381-1401 出牌（每 spawn_interval_ticks 一个；内部再按 interval 判——
    §F8 :1478 注）。逐玩家 pop(0)（FIFO）：出生点=渗透卡地图边缘（敌方部署区除外，
    2026-10-03 拍板沿边随机）/ 其余**直落己方部署区锚点**（2026-10-03 拍板：地面
    单位抽象为无宽度点单位、可叠放——原"锚点+出牌序偏移"与步长常数删除，
    排到图外问题不复存在）；instantiate=make_unit+add_unit（元素/武器弹药
    满编 + aa_roster 名单登记）；v1.3 审查#4 开局车载默认形态（squads[i]↔carriers[i]
    预挂 mounted_in，同卡只写 mounted_in）；渗透计时按相位置（:1393-1399：实战
    spawn 补置 600，盲部署期置 0）。渗透卡出生点 2026-10-03 拍板改沿边随机
    （ECONOMY 通道两掷，见 _infiltrator_spawn_pos）；其余零掷骰。"""
    if world.tick % cfg.spawn_interval_ticks != 0:     # 内部节流门（§D.0 :80）
        return
    for p in world.players:
        if not p.spawn_queue:
            continue
        card = p.spawn_queue.pop(0)
        p.spawn_serial += 1                            # 出牌序计账（只增不减）
        if card.flags & UnitFlag.CAN_INFILTRATE:
            spawn_pos = _infiltrator_spawn_pos(world, p.team)
        else:
            spawn_pos = _deploy_anchor(world, p.team)  # 点单位可叠放（PB-16 拍板）
        unit = add_unit(world, make_unit(world, card, p.team, p.index, spawn_pos))
        carriers = [e for e in unit.elements if e.template.seats > 0]      # :1390
        squads = [e for e in unit.elements
                  if e.template.element_type is ElementType.SQUAD]         # :1391
        for i, s in enumerate(squads):                                     # :1392
            if i < len(carriers):                                          # 车少班多：溢出班不挂
                s.mounted_in = carriers[i]
        if card.flags & UnitFlag.CAN_INFILTRATE:                           # :1393
            unit.infiltration_timer = (cfg.infiltration_ticks
                                      if world.phase == PHASE_COMBAT else 0)


def system_objectives(world: World) -> None:
    """§F7 :1403-1405 占点（每秒，由 system_economy 节流调用；零掷骰）：占点半径内
    存活单位按队归并——仅一方在场时 obj.owner=该队（双方争夺/空场不写，owner 保持）。
    2026-10-03 拍板：补给箱不算占点单位——cost=0 模板（空投箱）过滤，占点只看
    战斗单位。"""
    for obj in world.objectives:
        teams = []
        for u in world.units:
            if u.template.cost <= 0:                    # 补给箱（PB-17 拍板）
                continue
            if u.alive and dist_cm(u.pos, obj.pos) <= obj.radius_cm:
                if u.team not in teams:
                    teams.append(u.team)
        if len(teams) == 1:
            obj.owner = teams[0]


def system_economy(world: World, cfg: BalanceConfig = CONFIG) -> None:
    """§F8 :1476-1479 ⑧ 按秒（world_tick %10 门内调用；零掷骰）：出牌节流
    （spawn_step）→ 占点（system_objectives）。2026-10-03 拍板：收入机制整体
    删除（"没有收入机制"——每秒 points 加成与 income_per_second 字段一并去除）。
    D038 池子挂钩点（原文注记）。"""
    spawn_step(world, cfg)
    system_objectives(world)


def ground_unit_score(world: World, team: int) -> int:
    """D031「剩余地面单位分值」——v1.7 无公式体：取 Σ template.cost（模板唯一分值
    字段 §D.1#4 部署点；见登记表 discrepancies）。"""
    return sum(u.template.cost for u in world.units if u.alive and u.team == team)


def ground_unit_hp(world: World, team: int) -> int:
    """无平局兜底链第三级「剩余地面单位总血量」——Σ 存活元素 hp_current；与分值
    同款排除 cost=0 的补给箱（占位模板不计入）。"""
    return sum(e.hp_current for u in world.units
               if u.alive and u.team == team and u.template.cost > 0
               for e in u.elements)


def resolve_settlement(world: World) -> Settlement:
    """D031 结算裁决（2026-10-03 发起人拍板重设计，取代 v1.7 无函数体下 GDD-00
    :137/:196 的三级推定）：占点数多者胜 → 相同比剩余地面单位分值 → 再相比剩余
    地面单位总血量 → 再同判队 0 胜——必出胜者、无平局（winner 恒非 None）。
    队序=players 队序去重（插入序确定性）。整体零掷骰。"""
    teams = []
    for p in world.players:
        if p.team not in teams:
            teams.append(p.team)
    obj_counts = tuple(sum(1 for o in world.objectives if o.owner == t) for t in teams)
    unit_scores = tuple(ground_unit_score(world, t) for t in teams)
    hp_totals = tuple(ground_unit_hp(world, t) for t in teams)
    winner = 0
    if len(teams) == 2:                                # 两队制（make_world 口径）
        if obj_counts[0] != obj_counts[1]:
            winner = 0 if obj_counts[0] > obj_counts[1] else 1
        elif unit_scores[0] != unit_scores[1]:
            winner = 0 if unit_scores[0] > unit_scores[1] else 1
        else:
            winner = 0 if hp_totals[0] >= hp_totals[1] else 1
    return Settlement(winner=winner, obj_counts=obj_counts,
                      unit_scores=unit_scores, hp_totals=hp_totals)


# ── §F8 world_tick（:1423-1440，固定步长 10Hz）──

def world_tick(world: World, cfg: BalanceConfig = CONFIG) -> None:
    world.tick += 1
    update_phase(world, cfg)                                           # 相位推进（§F8 :1424）
    consume_commands(world, cfg)                    # 命令驱动：本 tick 命令全部落地（:1425-1426）
    consume_unit_commands(world, cfg)               # 单位级排队令链消费（MOVEMENT v1.2 §2.2，
                                                     # 挂 ① 前——世界级收件箱先落地再消费队列）
    system_timers(world, cfg)                                          # ①
    for unit in world.units:
        system_move_dispatch(world, cfg, unit)       # ② 移动（含随动）——§2.4 dispatch 包装器
                                                     # （§9 :576：system_move 直调已替换；ATTACK
                                                     # 保持门/MARCH 道路门/瓦片注入/队形/复位）
    if world.tick % cfg.sensing_period_ticks == 0:                     # ③ 节流扫描
        _ffn, _sfn, _ifn = terrain_sensing_channels(world)            #    感知接线块
        system_sensing(cfg, world, forest_m_fn=_ffn,                   #    （2026-10-07：
                       smoke_m_fn=_sfn, in_forest_fn=_ifn)             #    PB-53②/GAP-27
                                                                       #    穿林/穿烟/林内
                                                                       #    三通道喂入；含
                                                                       #    sense_air 对空分支）
    air_recon_step(world, cfg)   # 航空挂点①（③与④之间——AIR IMPL v1.4 增量清单①/GAP2-01）
    for unit in world.units:                                           # v1.7 GAP-25 rotating 复位
        for e in unit.elements:                                        # （PB-51 改锚 2026-10-04：原地
            if e.template.fire_arc_deg < 360:                          #  转向进行中维持 TRUE——转向慢
                e.rotating = unit.pivot_to >= 0                        #  =暴露窗口吃 SIDE 命中面
                                                                       #  （combat.compute_hit_facing
                                                                       #  仅 fire_arc<360 生效=方案6 现状
                                                                       #  口径，360° 炮塔载具不因 pivot
                                                                       #  改命中面）；非 pivot 拍清零、
                                                                       #  由 ④ ground_direct 的 rotate_step
                                                                       #  重设——GAP-25 原语义保持）
    for unit in world.units:
        system_combat(world, unit, cfg)                                # ④ 交战（含对空链）
    aircraft_tick(world, cfg)   # 航空挂点②（④与⑤之间——AIR IMPL v1.4 增量清单①）
    system_projectiles(world, cfg)                                     # ⑤ 弹丸推进与命中
    system_morale(world, cfg)      # ⑤.5 士气阈值状态机（GDD-05 B2 步序 suppression(8)→
                                   # morale(9)→logi(10) 字面：当拍 ④/⑤ 注入的压制即拍判态；
                                   # D014 四态/D025 阈值制，2026-10-04 士气块）
    system_supply(world, cfg)                                          # ⑥ 后勤（R-18/R-19）
    mount_requests_step(world)                                         # ⑦ 上车进度（R-07）
    if world.tick % 10 == 0:                                           # ⑧ 按秒（:1438 字面 %10）
        system_economy(world, cfg)                                     #    收入/出牌/占点
    world.units = [u for u in world.units if u.alive]                  # 尸体清扫（:1439）
    world.smoke_zones = [z for z in world.smoke_zones if z.ttl_ticks > 0]  # 烟雾 ttl（:1440）
