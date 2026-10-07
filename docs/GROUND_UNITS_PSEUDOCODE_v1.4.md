# 地面单位机制伪代码 v1.4（审查修复版二）

> 基于 v1.3（审查修复版）+ GDD-02-伪代码审查问题文档 v1.3（29 项：17 项机械缺陷本版修复，12 项设计决策移交 docs/GDD-02-拍板清单-v1.4.md）。
> 落地纪律：v1.2 各方案 sketch 为落地方法、negativeImpacts 为**已接受的代价**——不修复已接受的代价；v1.3/v1.4 修复方案落实缺陷与两版口径冲突（裁决原则：机制语义冲突以 GDD-02 为准）。
> 变量集：单位静态 30 + 单位运行时 16 + 元素静态 14 + 元素运行时 17 = **77 槽位**（v1.4 与 v1.3 持平——flags 位段 +2 位、FireMission 任务体 +1 字段不占槽）；武器 **26** 子字段。
> §13 审查对照表；§14 v1.1→v1.2 变更记录与 GDD 待同步清单；§15 v1.2→v1.3 变更记录；§16 v1.3→v1.4 变更记录。

---

## 0. 冻结数据结构（78 槽位 + 26 武器子字段）

```
STRUCT UnitTemplate:                      // 单位静态 30（排/连卡级）
    templateId, category                  // 侦察/步兵/装甲/火支/防空后勤（UI+R-01判定）
    cost, domain                          // GROUND 恒定
    elementCount, elementTemplate[]       // 编制与元素模板
    opticsGround                          // 视野 m
    opticsAir, airCeiling                 // 对空探测 m / 可及高度层  R-17
    stealthBase                           // 隐蔽 0-10
    speedTier                             // 速度档 1-5
    movementClass                         // FOOT/WHEEL/TRACK/HORSE
    turnRate                              // 车体转向 °/s   R-09
    deployTime, packTime                  // 展开/收起 s（0=免展开）
    modeSet                               // DIRECT/INDIRECT/TOW/CARGO/TRANSPORT 位掩码
                                          // 【v1.1】AA 从 mode 枚举移除——对空由武器 targetMask 驱动
                                          // 【v1.2】同时是 §4 开火许可门的剔除依据（方案13）
    closeCombatBonus                      // 近战加成：骑兵1.8，冲锋枪排高档，默认1.0
                                          // 【v1.2】消费点移入伤害修饰器族 meleeFlag 条件位（方案1）
    towTonnage, ownWeightTons             // 拖曳吨位 / 自重   R-19
    repairPower                           // 维修力（0=无）
    supplyRadius                          // 自动补给半径（0/80m）R-18
    acousticSignature                     // 声响特征（被声测定位速率）
    sonarRadius, sonarRate                // 声测侦听半径/收束速率   R-03
                                          // 【v1.2】sonarRadius>0 同时是声测侦听名单的入表条件（方案4）
    auraDef                               // {kind: MELEE|PRECISION, bonusPct, radius} | null
                                          // 【v1.2】PRECISION 仅精度+10%——"射程+10%"项已删除（方案17）
    flags                                 // canSprint canGarrison canAmbush canInfiltrate
                                          // noMoveVisionPenalty forestWalkSilent
                                          // requiresMark singleSquadCard
                                          // suppDecayX2   // 【v1.2】近卫意志锚点：压制衰减×2（方案18）
                                          // hasCargo hasMount hasSupply   // 【v1.2】载运/物资附页分配旗（方案12）
                                          // canSniperCover canAirdropBeacon   // 【v1.4】特技资格位（掩护/信标指令校验）
    pool                                  // 【v1.1】MAIN | RESERVE（主力/预备队双池）
    perCardLimit                          // 【v1.1】每卡限份数（指挥班组=1；一般2-3）
    quotaGroup                            // 【v1.1】火支子配额桶：HOWITZER/AT_GUN/ROCKET | null
    unlockBy                              // 【v1.1】特化解锁标识 | null（R-04渗透班等）

STRUCT UnitInstance:                      // 单位运行时 17
    unitId, teamId, alive
    pos, movePath[]                       // 队形基准点/航点
    deployState, deployTimer              // 行军/展开中/已展开/收起中
    stance                                // 自由开火/禁射（仅约束对地武器；对空恒自动 R-17）
    fireMission                           // 【v1.2】任务句柄；校射进度/校射点随任务体走（方案10）
                                          //   FireMission{form:POINT|LINE|CREEP, ammoMult, salvoMode:FULL|HALF,
                                          //   targetPoint, targetLine, creepSpeed, shotsLeft, shotsFired,
                                          //   calibProgress, calibTargetPos}
                                          //   R-16 连内共享 = 同任务参与者共享同一任务体
                                          //   【v1.4】shotsFired：LINE 取样序号承载（原"第k份"无存储来源）
    markLevel, spottedMask                // 无/发现/侦察校准  R-01 / 队伍发现位掩码
    infiltrationTimer                     // 渗透60s  R-04
    ambushActive, ambushShotBonus         // 伏击中 / 脱离伏击首击加成待触发  R-12
    // 【v1.3】删除单位级 towPair 槽：拖曳改元素级 TowPair{towerElements, towedElement}（§7），
    //   "拖曳中"判定 = ANY(e.towedState==TOWED)；单位运行时随之 17→16（审查#12）
    r02KillTally                          // 狙击累计击杀 → 灭班计数  R-02
    elements[]                            // 车/炮/班实例【不变式：数组内元素必然存活】
    // 【v1.1】删除：mode、smokeLeft、supplyRoundsCur、supplyMedicalCur、cargoUnits（下沉元素级）
    // 【v1.2】删除：calibTargetPos/calibProgress（下沉炮击任务体，方案10）、
    //          sniperCoverTargetId/airdropBeaconPos（改 world 旁表 coverByTarget/beaconByUnit，方案9）

STRUCT ElementTemplate:                   // 元素静态 14
    elementType                           // VEHICLE/GUN/SQUAD
    unitType                              // INFANTRY/MECH（bodyType 派生：MECH→HARD）
    hpMax                                 // MECH:车体血；INFANTRY:编制人数(1HP=1人)
    armorKE{F,S,R,T}, armorHE{F,S,R,T}    // 四面两类，0-20 相对刻度；T仅空袭读取；0=无甲（合法）
    fireArcDeg                            // 射界（无炮塔±15°；==360 炮塔车/全向基座）
                                          // 【v1.2】删除 turretTraverse 死字段（方案15）——
                                          //   "无炮塔"语义由 fireArcDeg<360 + 车体 turnRate 完整承载
    suppressionVuln                       // 敞篷>1（SU-76等）
    squadQuality                          // 老兵班精度+（国民掷弹兵）
    weapons[], mountedArmament            // 武器表 / 空车可射击标记（251）
    seats                                 // 【v1.1】运兵座位（卡车1班/半履带1班；0=不可载）
    cargoRoundsMax, cargoMedicalMax       // 【v1.1】每车物资上限（600发/120份；0=非卡车）
    cargoWeightMax                        // 【v1.1】每车总载重（按重量混装 D065/D012）

STRUCT ElementInstance:                   // 元素运行时 17
    elementId, pos, facing
    hpCurrent
    critSlots                             // {FC,SEN,RLD,MOB: NONE|MINOR|MAJOR}
                                          // 【v1.2】仅 unitType==MECH 分配，非MECH 为 null（方案7）；
                                          //   修饰器读槽前判 null 返回默认。轮式侦察车/卡车/维修车/火箭炮
                                          //   牵引车（无甲MECH）保留四槽
    suppression                           // 0-100 连续值，无士气状态
    revealTimer                           // 开火暴露残留
    sprintUntil                           // 【v1.2】疾跑到期时间戳（SprintCmd 写 now+时长），替代
                                          //   sprintTimer 常驻逐tick递减（方案14）
    mountedIn                             // 所载车辆元素ID | null
                                          // 【v1.3】全体 SQUAD 元素常驻槽（原附页条件槽使无座位步兵卡无承载——审查#8）
    weaponStates[]                        // 每武器 {state, timer, targetId, ammoLeft}
                                          // 【v1.2】删除 specialAmmoLeft：钨芯计数并入受限弹药档（方案11）
    rotating, towedState                  // 转向中 / 被拖·牵引中
                                          // 【v1.2】rotating 仅 fireArcDeg<360 的元素分配（方案6）：
                                          //   炮塔车/全向基座不分配不读，受弹面判定按模板短路
    mode                                  // 【v1.1】元素级模式 DIRECT/INDIRECT/TOW/CARGO/TRANSPORT
                                          // 卡车每辆独立切换（D065）；火炮每门 DIRECT/INDIRECT
    cargoUnits[]                          // 【v1.1】本车载运的班元素引用（R-07车载/D065运兵同构）
                                          // 【v1.2】载运附页槽：仅 hasCargo/hasMount 模板分配（方案12）
    supplyRoundsCur, supplyMedicalCur     // 【v1.1】本车在途物资（CARGO模式）
                                          // 【v1.2】物资附页槽：仅 hasSupply 模板分配（方案12）
    garrisonedIn                          // 【v1.2】进驻建筑引用 | null；仅 canGarrison 模板分配（方案5）

STRUCT WeaponTemplate:                    // 武器 26 子字段
    targetMask                            // GROUND/AIR_LOW/AIR_MID/AIR_HIGH 四位
                                          // 【v1.2】AIR 位同时是对空名单 aaRoster 的入表条件（方案2）
    damageType                            // KE / HE / SMOKE
                                          // 【v1.3】数据规则：SMOKE 武器 targetMask 必须为 0——
                                          //   永不进自动索敌，仅烟弹发射指令入口（审查附属修复）
    penMin, penMax                        // KE 远距~贴脸（HE/SMOKE 相等）
    damage, blastRadius
    maxRange, minRange, dispersion        // 【v1.1】射程上下限(m)与散布半径(m)
                                          // 【v1.2】近战档案=0~50/aim≈0/必中、狙击档案=超长aimTime/极低射速/
                                          //   maxRange400 均由本组字段承载（方案1 档案化）
    accuracyBase, aimTime, reloadTime, salvo
    ammoBase, ammoWeightPerShot           // 基数6发/门；烟弹=SMOKE武器档案走同一弹药轨【拍板默认】
    projectileSpeed, trajectory           // DIRECT / BALLISTIC
    suppressionPower, critMod, vsFortMult
    ammoProfiles[]                        // R-11 自动选弹档案集（AP/HE 共槽）
                                          // 【v1.2】钨芯并入为受限档{count:3, penBonus:+3}，档内自计数；
                                          //   删除独立 specialAmmo{count,penMod} 字段（方案11）
                                          // 【v1.4·拍板默认】weaponStates 实例化时深拷贝 ammoProfiles
                                          //   （每门独立计数——否则三门 PaK38 共享模板全连仅 3 发，"每门3发"失真）
    needsDeployed, selfDefenseProfile     // R-05 须展开 / R-15 自卫直射档案
    meleeFlag, sniperFlag                 // 【v1.2】语义改为结算条件位（不再是路由分支）：
                                          //   meleeFlag=伤害吃 closeCombatBonus×政委MELEE光环 的唯一条件位；
                                          //   sniperFlag=弹丸命中后进入 R-02 结算分支的开关（方案1）
    revealTime                            // 开火声响暴露时长（联动声测）

WORLD 实体：SmokeZone{pos,radius,ttl}、IntelCircle{center,radius,teamId}（声测模糊圈，冻结精度）、
           Building{hp,garrisonSlots,garrisoned:[elementId]}、
           beaconByUnit{unitId→pos}（空投信标旁表，方案9）、
           coverByTarget{被掩护unitId→掩护狙击unitId}（反狙击掩护旁表，方案9；
           【v1.3】SetSniperCover 指令带 1:1 校验：同一狙击已掩护他人时先删旧条目再挂新目标——
           "可掩护一个友军单位"可执行，原单个狙击可掩护全军，审查#7）、
           pendingResupply{unitId…}（待补给集合，方案19；【v1.3】登记条件=任一弹药缺口或步兵带伤——
           审查#11 弃"仅EMPTY"收窄，保 R-18"补满缺口"语义）
           // 【v1.2】删除 SupplyBox 独立实体：空投落地=R-21 实例化一次性 CARGO 单位（方案16）
PLAYER 结构：{points, deckSlots:[{cardTemplate, copiesLeft}], spawnQueue, objectivesHeld}
```

---

## 1. 主循环

```
FUNCTION worldTick(dt):                              // 固定步长
    systemTimers(dt)                                 // ① 计时器衰减
    systemDeathSweep()                               // ② 【v1.1】毁伤传播与引用清理（§5 destroyElement）
    FOR u IN units: systemMove(u, dt)                // ③ 移动（含车载/被拖/运兵 pos 随动）
    systemSensing(dt)                                // ④ 侦察/标记/对空发现/声测
    FOR u IN units: systemCombat(u, dt)              // ⑤ 交战（对空并行 + 对地按元素mode分流）
    FOR p IN projectiles: systemProjectile(p, dt)    // ⑥ 弹丸推进与命中
    systemSupply(dt)                                 // ⑦ 补给/医疗/维修
    systemEconomy(dt)                                // ⑧ 购买/出牌/占点
// 光环（systemAura）取消独立阶段：改为查询期函数 auraBonus(u, kind)，各消费点直接调用
```

---

## 2. 移动系统（含 pos 随动，修复 blocker ⑧）

```
FUNCTION systemMove(u, dt):
    IF u.deployState IN {DEPLOYING, PACKING}: RETURN
    v = moveSpeed(u)
    IF v == 0: RETURN
    新pos = pathStep(u, v*dt)
    u.pos = 新pos
    FOR e IN u.elements:
        IF e.towedState == TOWED:                    // 被拖：跟随牵引车，不自主移动
            e.pos = 牵引车后方偏移(所属 pair.towerElements); CONTINUE   // 【v1.3】元素级 pair
        IF e.mountedIn != null:                      // 【v1.1】车载班随车移动
            e.pos = carrier(e).pos + 车位偏移; CONTINUE
        e.pos = 队形偏移(新pos)
    主元素.facing = 朝向路径方向
    IF u.ambushActive: exitAmbush(u)                 // 移动自动退出伏击 R-12
    IF anyGarrisoned(u): unGarrisonAll(u)            // 【v1.4】移动自动出楼（楼槽释放、加成终止——与伏击退出同族；原驻楼状态下移动加成/占槽滞留）
    // 【v1.1】D065运兵：本车 cargoUnits 中的班（跨卡单位）pos 同步跟随
    FOR e IN u.elements WHERE e.mode == TRANSPORT:
        FOR s IN e.cargoUnits: s.pos = e.pos + 车位偏移

FUNCTION moveSpeed(u):                               // 全单位同一函数
    tier = u.speedTier
    IF now < 主元素(u).sprintUntil: tier = MIN(5, tier + 1)   // 【v1.2】疾跑=升1档，时间戳承载（方案14）
    base = SPEED_TABLE[tier]
    m = TERRAIN[u.tile][u.movementClass].speedMod
    IF onRoad(u) AND u.movementClass != FOOT: m = MAX(m, ROAD_BONUS)
    e = 主元素(u)
    IF e.critSlots != null AND e.critSlots.MOB == MAJOR: RETURN 0     // 【v1.2】判空（方案7）
    IF e.critSlots != null AND e.critSlots.MOB == MINOR: m *= 0.5     // 【v1.2】判空（方案7）
    IF anyElementTowed(u): base = SPEED_TABLE[1]     // 拖曳双方最低档 R-19【v1.3】元素级判定（单位级 towPair 已删）
    RETURN base * m

FUNCTION 转向处理(e, 目标朝向):                       // R-09 不变
    IF fireArcDeg(e) == 360: RETURN                   // 【v1.2】炮塔车/全向基座豁免（方案6）：
                                                      //   不分配 rotating、无转向期侧露
    IF |angleDiff(e.facing, 目标朝向)| > fireArcDeg(e):
        e.rotating = true; e.facing += sign × turnRate × dt
    ELSE: e.rotating = false

FUNCTION toggleAmbush(u):                                   // 【v1.4·审查 high#2】处理体补定义——原 ambushActive 全文无 TRUE 写点，R-12 整链不可达
    IF NOT u.flags.canAmbush: REJECT                       // 资格门（canAmbush 恢复消费）
    IF u.ambushActive:
        u.ambushActive = false; u.ambushShotBonus = true   // 手动退出：下一发首击加成待触发
    ELIF u 静止 AND u.movePath 为空:
        u.ambushActive = true                              // 开启：视野减半+隐蔽乘成（§3 两消费点生效）
    // 移动自动退出（无加成）由 exitAmbush 于 §2 承载；开火不自动退出（R-12）
```

---

## 3. 侦察系统（修复：伏击视野减半）

```
FUNCTION systemSensing():
    // A. 地面互侦（不变式：elements 内均存活，死亡已在 §5 清理）
    FOR (obs, tgt) IN 敌对配对:
        IF dist(obs,tgt) <= detectionRange(obs,tgt): markSpotted(tgt, obs)
        ELIF dist > keepRange(obs,tgt): unmarkSpotted(tgt, obs)
    // B. 对空发现 R-17/R-23
    //    【v1.2】airCeiling/opticsAir 探测分支只遍历 aaRoster 名单（方案2）；
    //    低空目视分支保留全体单位不动（方案2 承载约定）
    FOR aircraft a:
        FOR g IN aaRoster:                            // 部署初始化名单，见 §9
            IF a.altTier <= g.airCeiling AND dist <= g.opticsAir: spotted(a, by=g)
        FOR g IN 全体地面单位:
            IF a.altTier == LOW AND dist <= g.opticsGround:      spotted(a, by=g)
    // C. 标记等级 R-01（【v1.4】重算式——原 MAX(观察者等级) 空集行为未定义、IMPL 侧棘轮式只升不降；
    //    统一为"本轮接触观察者的最高等级，无接触 → NONE"：侦察撤离/脱视野后校准加成与犀牛门同步回落）
    FOR tgt: tgt.markLevel = (本轮接触观察者非空 ? MAX(本轮接触观察者等级) : NONE)
    //   category==侦察 → CALIBRATED；其余 → SPOTTED
    // D. 声测 R-03
    //    【v1.2】侦听侧名单化（方案4）：声测名单为空或全灭 → 整段跳过，不再产生/收窄
    //    IntelCircle；已有圈按 R-03 冻结保留。盲射配合以声测班存活为界（已接受代价）。
    //    声源侧（开火 upsert SoundTrack）完整保留，勿误伤。
    listeners = { s ∈ 声测名单 WHERE s.deployState == DEPLOYED }
    IF listeners 非空:
        FOR ev IN enemySoundEvents:
            FOR s IN listeners WHERE dist <= s.sonarRadius:
                ev.accum += s.sonarRate × ev.sig × dt
                IF ev.accum >= LOCATE_THRESHOLD:
                    upsertIntelCircle(s.teamId, ev.pos, lerp(MAX_R, MIN_R, ev.accum))   // 【v1.3·审查#2】圈记侦听方队（原 team 未定归属、消费链对不上）；圈冻结精度 R-03
    // 【v1.4·拍板默认】声测生命周期三语义：
    //   ① IntelCircle 键 = 声源单位（每敌开火炮位一圈；多炮多圈共存，fireAt 按圈遍历取 MAX 语义成立）
    //   ② SoundTrack.upsert（开火时）：位置变更 → pos=新位, accum=0（换阵地重新定位——结转会让新炮位瞬间精确）
    //   ③ accum 仅在侦听者接触的扫描周期增长，停火期不增长（圈冻结在最后精度——R-03 冻结语义）

FUNCTION detectionRange(obs, tgt):
    r = obs.opticsGround
    IF moving(obs) AND NOT obs.flags.noMoveVisionPenalty: r *= 0.5
    IF obs.ambushActive: r *= 0.5                        // 【v1.1】伏击的视野代价 R-12（原缺失）
    r *= STEALTH_FACTOR_TABLE[effectiveStealth(tgt)]
    r -= ATTEN × forestMetersOnLOS(obs,tgt)
    r -= ATTEN × smokeMetersOnLOS(obs,tgt)
    RETURN r

FUNCTION effectiveStealth(u):                            // 【v1.4】与 IMPL 口径统一：地形/驻楼加成置于乘区之后（不随移动/渗透/暴露缩放）
    s = u.stealthBase
    m = 1.0
    IF moving(u):
        m *= 0.5
        IF u.flags.forestWalkSilent AND inForest(u): m *= 2      // 静默行军（第5轮）
    IF u.infiltrationTimer > 0: m *= INFIL_MULT                  // 渗透60s，开火即清 R-04
    IF u.ambushActive: m *= AMBUSH_MULT                          // 伏击隐蔽大增 R-12
    IF anyReveal(u): m *= REVEAL_MULT                            // 开火暴露
    s = s * m                                                    // 【v1.4】乘区先行（原 v1.3 地形加值在乘区前、驻楼在后——两处口径互斥）
    IF u.flags.canGarrison AND garrisoned(u):                    // 【v1.2】canGarrison 前置门票（方案5）：
        s += GARRISON_STEALTH_BONUS                              //   加成后置；×10 整型存储（30），与 IMPL §D.0 口径统一
    IF inForest(u): s += FOREST_STEALTH_ADD                      // 同上（存储=20）
    RETURN clamp(s, 0, 10)

FUNCTION keepRange(obs, tgt):  RETURN obs.opticsGround × STEALTH_FACTOR_TABLE[tgt.stealthBase]

FUNCTION pointInFriendlyVision(team, pt):               // 【v1.3·审查#13】定义体补齐——校射视线判定
    // R-06"遮断校射"承载：穿林/穿烟衰减计入（烟墙后的目标点不收束）；点目标按隐蔽中位档(5)近似
    FOR obs IN 该队存活单位:
        r = obs.opticsGround × STEALTH_FACTOR_TABLE[5]
          − ATTEN × (forestMetersOnLOS(obs,pt) + smokeMetersOnLOS(obs,pt))
        IF dist(obs, pt) <= MAX(0, r): RETURN true
    RETURN false
```

---

## 4. 交战决策（修复 blocker ②③⑤、gap：狙击/近战/自卫/炮击任务/威胁值；
##   【v1.2】方案1 狙击/近战档案化、方案2 对空名单、方案3 曲射分流、方案10 校射下沉、方案13 模式门剔除）

```
// 【v1.2】部署初始化派生名单（构建见 §9）：
//   aaRoster         对空交战/对空探测只遍历名单（方案2）
//   indirectDispatch 含 INDIRECT 位元素的分发表；无位模板不进曲射链（方案3）；
//                    setElementMode 切入/切出 INDIRECT 时动态刷新（方案3 边界）
//   声测名单         sonarRadius>0 候选（方案4，§3.D 消费）

FUNCTION systemCombat(u, dt):
    FOR e IN u.elements:                              // elements 内必然存活（§0不变式）
        // ── A. 对空：恒自动、并行、不受 stance/mode 影响（R-17）——修复 blocker ⑤
        //       【v1.2】仅 aaRoster 内元素参与（方案2）；名单外单位连问都不问
        IF e IN aaRoster:
            FOR w IN e.weaponStates WHERE w.template.targetMask & AIR_BITS:
                IF state==READY AND ammoLeft>0: aaAutoEngage(e, w)
        // ── B. 对地：按元素 mode 分流（【v1.2】无 INDIRECT 位模板不进曲射分支，方案3）
        IF e.mode == DIRECT:
            FOR w IN e.weaponStates WHERE 对地位(targetMask.GROUND) AND state==READY AND ammoLeft>0:
                IF NOT 开火许可(u, e, w): CONTINUE
                // 【v1.2】近战/狙击不再单独分流（方案1）：两者都是直射武器档案，
                //   走同一条 selectTarget→AIMING→fire 高速公路；
                //   近战档案 range 0~50/aim≈0/必中；狙击档案命中后走 §5 R-02 分支
                tgt = selectTarget(u, e, w)
                IF tgt == null: CONTINUE
                IF 需转车体(e, tgt): 转向处理(e, 朝向tgt); CONTINUE     // R-09
                进入AIMING(w, tgt)
        IF e.mode == INDIRECT AND e IN indirectDispatch:
            // 自卫直射触发：修复 gap R-15——曲射炮被近身时以惩罚档案直射
            // 【v1.2】selfDefenseProfile==null 一行短路（方案3），封掉无档案卡每tick裸检查
            IF w主.selfDefenseProfile != null
               AND 存在敌元素 dist <= w主.selfDefenseProfile.range AND w主 就绪 AND 通过开火许可:
                fire(u, e, w主, 最近敌, profile=w主.selfDefenseProfile)   // 短射程+大精度惩罚
            ELSE IF u.fireMission != null:
                processFireMission(u, dt)                     // §4.3，含开火许可门
        // e.mode ∈ {TOW, CARGO, TRANSPORT}：不开火（开火许可亦拦截）
```

```
FUNCTION 开火许可(u, e, w):
    IF u.stance == HOLD_FIRE: RETURN false
        // 【拍板默认】stance 约束全部对地武器（含狙击；对空本就不受 stance 管）
    IF w.template.needsDeployed AND u.deployState != DEPLOYED: RETURN false   // R-05
    IF e.mountedIn != null AND w 不是 mountedArmament: RETURN false
        // 【v1.2】mountedIn 仅被载班持有（方案12），其余单位此门天然短路
    IF u.modeSet & TOW位:                                        // 【v1.2】模板无 TOW 位则跳过此问（方案13）
        IF e.towedState != NONE: RETURN false                    // R-19 被拖禁射
    IF u.modeSet & (TOW|CARGO|TRANSPORT)位:                      // 【v1.2】模板无对应位则跳过此问（方案13）
        IF e.mode ∈ {TOW, CARGO, TRANSPORT}: RETURN false        // D065 载货状态不作战
        // 【v1.2→v1.4】数据配置硬要求（全量）：一切可作为被拖方的卡——中/重坦（R-19 主场景：
        //   维修车拖中坦、重坦45吨需2辆并拖）、轻防空（第11/12轮卡车牵引）、
        //   火支全部牵引炮与火箭炮、步兵类四门迫击炮排（v1.4 补全——GDD-01 类别口径属步兵）——
        //   以及牵引侧卡（坦克维修班/重型拖拉机排/豹式救援车，v1.4 补全）——
        //   mode_set 必须含 TOW 位；漏配即第一问被整段跳过、"拖曳中禁射"失效（拖着重坦/防空/火炮开火）
        //   ——方案13 已登记的数据正确性依赖，不做运行时兜底。
    RETURN true

FUNCTION selectTarget(u, e, w):
    cands = { x ∈ 敌方存活元素 ∧ teamSpotted(x)
              ∧ (x.targetDomain & w.targetMask) != 0
              ∧ w.minRange <= dist(e,x) <= w.maxRange              // 【v1.1】含最小射程（迫击炮250m）
              ∧ markOK(u, x) }                                     // 犀牛 requiresMark 门
    score(x) = 预估伤害(w,x) + 威胁值(x) − dist惩罚
    // 【v1.1】威胁值定义为可计算量（无新变量）：
    //   威胁值(x) = MAX over x的武器 ( w.damage × w.salvo / w.reloadTime )   // 对我方 DPS 近似
    RETURN argmax(score)
    // 【v1.2】注：射程过滤不读任何光环——军官"射程+10%"项已随方案17删除，勿在此补挂

FUNCTION fire(u, e, w, tgt, profile=w默认):
    profile选弹: IF w.ammoProfiles 非空: 按 R-11 自动选弹（§4.2；钨芯=受限档，方案11）
    w.ammoLeft -= 1; w.state = RELOADING; w.timer = w.reloadTime × reloadFactor(e)
    e.revealTimer = MAX(e.revealTimer, w.revealTime)
    spawnSoundEvent(e.pos, u.acousticSignature × w.salvo)          // 喂声测 R-03（声源侧，方案4保留）
    acc = w.accuracyBase × accuracyCurve(dist/w.maxRange) × aimFactor(e)
        × ambush首击加成(u) × auraBonus(u,PRECISION) × e.squadQuality
        //   【v1.2】PRECISION 光环仅精度项（射程项已删，方案17）
        × (tgt 是建筑 ? 1 : tgt.unit.markLevel == CALIBRATED ? CALIB_ACC_BONUS : 1)  // 【v1.1】R-01 校准消费；【v1.3·审查#5】建筑无标记
        //   近战档案 acc≡1（必中），由武器数据承载，无分支（方案1）
    FOR i IN 1..w.salvo:
        hit = random() < acc
        base = tgt.pos
        // 【v1.2】校射收束改读任务体（方案10）：仅存在活跃炮击任务时直射吃到收束；
        //   任务已结束/无任务 = 无收束（方案10 已接受代价：ZiS-3/52-K 双职炮直射不再吃历史校射）
        calib = u.fireMission != null ? u.fireMission.calibProgress : 0
        scatterR = w.dispersion × (1 − calib/100 × CALIB_MAX_REDUCTION)   // 校收割束
        aimPoint = scatter(base, scatterR × (hit ? 0.4 : 1))
        SPAWN Projectile(shooter=e, weapon=w, profile, aimPoint, hitTarget = hit ? tgt : null)
        //   狙击档案同样生成弹丸：先命中再判定，命中后 §5 resolveHit 走 R-02 分支（方案1）
```

```
// §4.2 选弹（R-11 + 钨芯；【v1.2】钨芯并入受限弹药档，方案11）
FUNCTION 选弹(w, tgt):
    IF w.ammoProfiles 为空: RETURN w默认档案
    IF unitTypeOf(tgt) == MECH:
        钨芯档 = w.ammoProfiles 中的受限档
        IF 标准AP(w).penMax < 正面甲(tgt) AND 钨芯档存在 AND 钨芯档.count > 0:
            钨芯档.count -= 1; RETURN 钨芯档案
            // 【v1.2】"仅正面打不穿才切、档内计数"显式保留（方案11 负面代价条款）：
            //   防止"见坦克就喷钨芯"，保住第11轮"每门3发、用完即止"的稀缺感
        RETURN AP档案
    RETURN HE档案
    // 烟弹不并入：SMOKE 维持独立武器档案（方案11 明确只并钨芯）

// §4.3 炮击任务（修复 gap：fireAt 定义 + 开火许可门 + 模式/拖曳联动）
FUNCTION processFireMission(u, dt):
    fm = u.fireMission
    参与炮 = fm.salvoMode == HALF ? 前一半元素 : 全部元素             // R-14 半轮
    FOR gun IN 参与炮:
        w = gun 主武器
        IF NOT (w就绪 AND 开火许可(u, gun, w)): CONTINUE             // 【v1.1】未展开/被拖不打
        fireAt(gun, w, fm)                                          // 【v1.1】正式定义：
        //   落点 = pointIn(fm)：
        //     POINT → fm.targetPoint
        //     LINE  → 沿 fm.targetLine 均匀取样第k份
        //     CREEP → 线段起点起按 creepSpeed × elapsed 推进的当前段
        //   散布 = w.dispersion × (1 − fm.calibProgress收束) + (目标点∈IntelCircle ? circle.radius : 0)
        //   SPAWN Projectile(trajectory=BALLISTIC, aimPoint=落点, hitTarget=null)  // 无目标弹丸
        fm.shotsLeft -= 1; fm.shotsFired += 1
        // 【v1.3·审查#13】先判后加（原"循环内先加、循环外又判不增长"自相矛盾）；
        //   视线定义 pointInFriendlyVision 见 §3（含烟/林遮断——R-06"遮断校射"承载）
        // 【v1.4·拍板默认】校射仅 POINT 形式（GDD 校射锚在"点射击"；LINE/CREEP 落点无稳定校射点，短路）
        IF fm.form == POINT AND pointInFriendlyVision(u.teamId, fm.targetPoint):
            fm.calibProgress += CALIB_PER_SHOT                        // 【拍板默认】按发累积；【v1.2】记在任务体（方案10）
    IF fm.targetPoint 变更: fm.calibProgress = 0                       // R-16 连内共享、换点重置
    IF fm.shotsLeft <= 0: u.fireMission = null                         // 【v1.2】任务体销毁，校射进度随之失效（方案10）

// 【v1.3】任务创建/取消入口（原全文只有清空写点，任务永远无法下达——审查-原始行修复）：
//   FireMissionCmd(u, form, point|line, ammoMult, salvoMode, creepSpeed):
//       校验 modeSet 含 INDIRECT 且存在 INDIRECT 元素；
//       shotsLeft = INDIRECT元素数 × 主武器 ammoBase × ammoMult；创建即 calibProgress = 0
//   CancelFireMissionCmd(u): u.fireMission = null（任务体销毁，校射随之失效）

// 模式切换/拖曳联动（修复 gap：任务悬挂）
FUNCTION setElementMode(e, m):
    校验 m ∈ e.unit.modeSet
    IF e.mode == TOW: stopTow(涉及pair)                               // 切模式先解挂
    IF e.mode == CARGO AND e 有物资附页: e.supplyRoundsCur/supplyMedicalCur = 0   // 卸货【v1.2】按槽存在性（方案12）
    IF e.mode == TRANSPORT AND e 有载运附页: 卸下 e.cargoUnits 于原地             // 【v1.2】同上
    e.mode = m
    IF m == INDIRECT: indirectDispatch += e ELSE: indirectDispatch −= e
        // 【v1.2】分发表动态刷新（方案3 边界）：漏刷新则 52-K 切曲射静默失效
    IF m != INDIRECT: e.unit.fireMission = null         // 任务取消（任务体销毁）【v1.3】对齐 GDD 表A4/IMPL 拍板：
                                                        //   切进 INDIRECT 保留任务（原"或 e 是炮"分支删除——审查终审#5）
```

```
// §4.4 对空自动交战（R-17，修复 blocker ⑤：与对地并行，不再互斥）
FUNCTION aaAutoEngage(e, w):
    IF e.towedState == TOWED OR anyElementTowed(e.unit): RETURN   // 【v1.3·审查#9】R-19 拖曳双方禁射扩展至对空链（疑点⑤闭合）
    tgt = 已发现敌机中 威胁最高者 in range AND altTier <= e.unit.airCeiling
    //   【拍板默认】对空威胁 = 距离最近（可后续换加权表）
    IF tgt: 同 fire() 流程（aimPoint=预测机位, hitTarget=aircraft句柄, 走§12对空结算）

// §4.5 近战结算（【v1.2】方案1：原独立 meleeResolve 取消——
//   近战档案走直射链，结算并入 §5 resolveHit 的 meleeFlag 分支。
//   已接受代价：近战经瞄准/装填周期，骑兵抓炮兵/渗透班猎杀卡车的"一拍即死"节奏变慢；
//   政委 MELEE 光环消费点移入直射伤害链，会同时放大近距射击（语义漂移，GDD 待同步）。
//   【拍板默认】维持：近战=极短距武器射击，不设专门"近战锁定"状态；双方仍可被第三方远程射击）

// §4.6 狙击 R-02（【v1.2】方案1：原独立 sniperResolve 取消——
//   狙击档案走直射链+弹丸，命中后按 sniperFlag 进入 §5 sniperSettleOnHit。
//   语义从"先判定概率再看命中"改为"先命中再判定"：期望击杀率由 SNIPER_BASE_PROB
//   重新标定保持（§11），方差改变、"一枪定生死"手感变化为已接受代价）
```

---

## 5. 弹丸、命中与死亡结算（修复 blocker ⑦⑨⑩、烟雾闭环 ④）

```
FUNCTION systemProjectile(p, dt):
    p.pos += p.vel × dt
    IF p.weapon.trajectory == BALLISTIC AND p.pos ≈ p.aimPoint: resolveBlast(p)
    ELIF p.hitTarget != null AND p.pos ≈ targetPos(p.hitTarget): resolveHit(p)
    // 对空弹（hitTarget 为航空句柄）：走 §12 对空结算接口

FUNCTION resolveHit(p):
    e = p.hitTarget
    IF fireArcDeg(e) == 360: facing = e.facing            // 【v1.2】全向基座/炮塔车短路（方案6）
    ELSE: facing = facingOf(e, p.approachDir)
    IF e.garrisonedIn != null: facing = REAR              // 【v1.3】驻楼受击参考尾甲（§7 效果声明落地——原注释宣称未实现）
    // ── 【v1.2】狙击命中分支（方案1：先命中再判定，R-02 逻辑原样搬入）──
    IF p.weapon.sniperFlag:
        sniperSettleOnHit(p.shooter, e.unit)
        RETURN                                            // 不走常规装甲/伤害结算
    // ── 【v1.2】近战命中分支（方案1：meleeFlag 为唯一条件位，防污染普通射击）──
    IF p.weapon.meleeFlag:
        dmg = p.profile.damage × p.shooter.unit.closeCombatBonus
            × (1 + auraBonus(p.shooter.unit, MELEE))      // 政委近战光环（督战）
        applyDamage(e, dmg, 近战档案(走HE曲线))
        injectSuppression(e, p.weapon.suppressionPower)
        RETURN
    armor = armorOf(e, facing, p.profile.damageType)
    IF armor <= 0:                                                  // 【v1.1】无甲守卫（卡车装甲0）
        mult = 1.0                                                  // 无甲全吃，不做除法
    ELSE:
        r = penetrationAt(p.weapon, distFlew) / armor
        mult = damageMultiplier(unitTypeOf(e), p.profile.damageType, r)
    dmg = p.profile.damage × mult × squadHpFactor(p.shooter)
    IF 命中建筑: dmg ×= p.weapon.vsFortMult                          // 工兵×2 ISU-HE×1.5 OT-34×2
    applyDamage(e, dmg, p.weapon)
    IF mult > 0 AND unitTypeOf(e) == MECH: rollCrits(e, dmg, p.weapon.critMod)
    FOR x IN blast圈近旁: injectSuppression(x, p.weapon.suppressionPower × falloff)

// 【v1.2】R-02 结算（方案1：由 resolveHit 的 sniperFlag 分支调用；原 §4.6 射程距离门取消，
//   射程400 由武器 maxRange 经 selectTarget 承载）
FUNCTION sniperSettleOnHit(sniper_e, tgtUnit):
    e = tgtUnit.任一存活班
    covered = world.coverByTarget[tgtUnit.unitId] 存在 AND 掩护狙击存活(elements 非空)
                                                              // 【v1.2】反狙击掩护改旁表（方案9）
    killProb = covered ? BASE_PROB × 0.5 : BASE_PROB                  // 反狙击掩护（第1轮）
    IF tgtUnit.flags.singleSquadCard:                                 // 指挥班组/声测班：1~2发概率灭排
        IF random() < killProb: applyDamage(e, e.hpCurrent, 狙击档案) // 走applyDamage→destroyElement
    ELSE:
        kills = (random()<killProb) + (random()<killProb)
        actual = MIN(kills, e.hpCurrent)                   // 【v1.4】tally 记实际击杀（原记掷骰值——残班吃 2 记 2 实死 1，提前灭班）
        applyDamage(e, actual, 狙击档案)                    // 1HP=1人，扣血即减员
        tgtUnit.r02KillTally += actual
        IF tgtUnit.r02KillTally >= 3:
            最低血存活班.applyDamage(其全部HP)                         // 灭班走同一入口
            tgtUnit.r02KillTally -= 3

FUNCTION damageMultiplier(unitType, dmgType, r):                     // 不变
    IF dmgType == SMOKE: RETURN 0                                    // 烟雾走 resolveBlast 生烟
    IF unitType == INFANTRY: RETURN r*r/(1+r*r)
    IF dmgType == KE:
        IF r >= 1.0: RETURN 1.0
        IF r >= 0.5: RETURN 1.8*r - 0.8
        RETURN 0.0
    RETURN r*r/(1+r*r)

FUNCTION resolveBlast(p):                                            // 【v1.1】烟弹落点正式定义
    IF p.weapon.damageType == SMOKE:
        spawnSmokeZone(p.aimPoint)                                   // 定义体补上：
        // spawnSmokeZone(pos): WORLD.SmokeZones += SmokeZone{pos, radius=SMOKE_RADIUS,
        //                                   ttl=SMOKE_TTL}          // 每发独立入列，到期移除
        RETURN
    FOR e IN elementsWithin(p.aimPoint, p.weapon.blastRadius):
        dmg = p.weapon.damage × falloff(dist)
        applyDamage(e, dmg, p.weapon)
        IF unitTypeOf(e)==MECH: rollCrits(e, dmg, p.weapon.critMod)
        injectSuppression(e, p.weapon.suppressionPower)
    FOR b IN buildingsWithin(p.aimPoint, blastRadius):               // 建筑：直接伤+驻军连带
        b.hp -= p.weapon.damage × vsFortMult
        IF b.hp <= 0: collapseBuilding(b)                            // 见 §7 驻军结局

FUNCTION applyDamage(e, dmg, weapon):
    e.hpCurrent -= dmg
    IF e.hpCurrent <= 0: destroyElement(e)                           // 唯一除名入口

// ── 修复 blocker ⑦：destroyElement 完整定义 ──
FUNCTION destroyElement(e):
    u = e.unit
    u.elements.remove(e)                                             // 物理移除，保住 §0 不变式
    // 车载/运兵连带（【v1.3·审查#1】按元素去重只扣一次 60%——统一装载对同卡/跨卡都写双向引用，
    //   原两环串联连扣两次；且跨卡运兵连带补齐扣血——GDD"车毁连带扣60%"，原仅落位不扣）：
    受影响 = {s ∈ allElements | s.mountedIn == e.elementId} ∪ {s ∈ e.cargoUnits}   // 元素并集去重
    FOR s IN 受影响:
        s.mountedIn = null; s.pos = e.pos 旁落位
        applyDamage(s, ceil(s.hpCurrent × 0.6), 车毁连带档案)
    e.cargoUnits.clear()
    // 物资连带：e.supplyRoundsCur/supplyMedicalCur = 0（所载物资随车毁 D065）
    // 【v1.2】旁表按键注销（方案9，替代 v1.1 的全单位遍历清理；所有销毁路径收口本函数）：
    //   world.coverByTarget.注销(u.unitId)；world.beaconByUnit.注销(u.unitId)
    //   【v1.3】掩护者死亡另删"值为 u.unitId"的条目（单值旁表——防被掩护对象恒判 covered）
    //   ——漏注销即悬空引用（航空侧对已死单位投弹）为方案9 已登记风险
    // 【v1.2】待补给集合注销（方案19）：IF u ∈ world.pendingResupply: 移除
    // 拖曳连带：releaseTowIfInvolved(e)（§7）
    // 全灭：IF u.elements 为空: u.alive = false; 移出战场; （一命制，无回圈）
    //      声测圈不撤销（R-03 冻结；【v1.2】声测班全灭仅停止产生/收窄新圈，方案4）；
    //      光环/侦听随 elements 清空自然失效（查询期按存活过滤）
```

---

## 6. 压制与修饰器（【v1.2】crit 判空与近战伤害修饰器并入；其余不变）

```
FUNCTION injectSuppression(e, amount):
    e.suppression = MIN(100, e.suppression + amount × e.suppressionVuln)

修饰器族（查询期计算；所有消费点只遍历存活元素，死元素已从 elements 移除）：
    aimFactor(e)     = critFactor(critFC: MINOR×0.75/MAJOR×0.5) × (1 − suppPenalty × e.suppression/100)
    reloadFactor(e)  = critFactor(critRLD: MINOR×1.3/MAJOR×1.6) × (1 + suppPenalty × e.suppression/100)
    opticsFactor(e)  = critFactor(critSEN: MINOR×0.6/MAJOR×0.3)
    critFactor(x)    = e.critSlots == null ? 1.0 : x      // 【v1.2】非MECH crit槽为null（方案7）
    squadHpFactor(e) = e.hpCurrent / e.hpMax
    meleeDmgMod(w, u) = w.meleeFlag ? u.closeCombatBonus × (1 + auraBonus(u, MELEE)) : 1.0
                      // 【v1.2】closeCombatBonus 并入伤害修饰器族，meleeFlag 为唯一条件位（方案1）；
                      //   已接受代价：失去"仅近战读取"的函数边界，靠条件位防守
    auraBonus(u, kind) = Σ 存活友方指挥元素 auraDef 匹配 kind 且 dist<=radius 的 bonusPct
```

---

## 7. 展开制、运输、拖曳、驻建筑、后勤

```
// —— deployState 状态机（不变，见 §10 表）——

// —— R-07 车载 / D065 运兵（统一为 cargoUnits + mountedIn 双向引用；
//      【v1.2】载运附页仅 hasCargo/hasMount 模板分配，本段各分支按槽存在性短路，方案12）——
下令下车: FOR s IN carrier.cargoUnits / FOR s IN elements WHERE mountedIn==carrier:
            s.mountedIn = null; s.pos = 载具旁落位; 移出 cargoUnits
          // 空车留在原地，mountedArmament 照常开火（第5轮拍板）
          // 【v1.3】本段双向清理本就正确（IMPL 侧的漏清缺陷不适用于机制版口径）
下令上车: 班(SQUAD)元素静止于载具旁 20s → s.mountedIn = carrier.elementId; carrier.cargoUnits += s
          // 【v1.3·审查#4】仅 SQUAD 元素可挂载（混编卡再上车不把载具挂上载具）；
          // 【v1.4】载具模式门改"mode ∉ {CARGO, TOW}"可载（替代 v1.3"须 TRANSPORT"一刀切——
          //   251 等无三模式位载具恒 DIRECT 可载、R-07 车载开火不冲突；D065 载货/拖曳状态仍不可载人）
          // 【v1.4】多载具分配 = 当前挂载（含同卡 mountedIn）最少的 seats>0 元素（原固定首个→再上车全落 251#1）
装载校验: Σ 占用（跨卡 cargoUnits + 同卡 mountedIn 指向该元素的班元素）<= carrier_template.seats
          // 【v1.3】seats 消费点成文；【v1.4】账目含同卡挂载（原只数 cargo_units——同卡班对座位不可见，1 座 251 可塞 3 班）
          // 【v1.4】机制版上下车为直接指令（无请求队列），20s 窗口内的存活/模式复核义务由指令时点承担；
          //   实现侧挂起请求队列的到期复核（存活/模式/座位/去重）见 IMPL v1.4 §F6——两版语义同向

// —— D065 卡车三模式（元素级，每辆独立切换）——
setElementMode(truck_e, m ∈ {TOW, CARGO, TRANSPORT}): 见 §4 setElementMode
CARGO装货: buySupplies(truck_e, rounds, medical):
    IF truck_e.mode != CARGO: 拒绝                           // 【v1.3·审查#8】仅物资模式可装货（原运兵/拖曳模式可预装）
    weight = rounds×ammoWeightPerShot(均摊) + medical×MED_WEIGHT_PER_UNIT
    校验 rounds <= cargoRoundsMax AND medical <= cargoMedicalMax AND weight <= cargoWeightMax
    truck_e.supplyRoundsCur = rounds; truck_e.supplyMedicalCur = medical

// —— R-19 拖曳（【v1.3·审查#12】改元素级：TowPair{towerElements, towedElement}——
//      单卡 2 车并拖可表达（苏军重坦不再需购两张卡）、61-K 可只拖一门、混合牵引组按吨位降序贪心选车）——
startTow(towerElements[...], towedElement):
    FOR t IN towerElements:                               // 【v1.4】互斥门：堵"载货卡车拖炮/一车拖两门/未切TOW拖曳中开火"
        IF t.towedState == TOWED: RETURN 失败
        IF (t.unit.modeSet & (TOW|CARGO|TRANSPORT)) AND t.mode != TOW: RETURN 失败
    sorted = towerElements 按模板 towTonnage 降序（稳定排序，并列取原序）
    acc = 0; chosen = []
    FOR t IN sorted: chosen += t; acc += t.towTonnage
                   IF acc >= towedElement.ownWeightTons: BREAK       // 累计吨位制（重坦45t=2×30t 或 1×45t）
    IF acc < towedElement.ownWeightTons: RETURN 失败
    pair = TowPair(chosen, towedElement); world.towPairs += pair
    FOR t IN chosen: t.towedState = TOWED                            // 仅牵引元素（不整队置位）
    towedElement.towedState = TOWED
    IF towedElement.unit.deployState != MOBILE:            // 【v1.4】30 秒展开闸承载（审查 medium——原 DEPLOYED 炮拖完立刻开火）
        towedElement.unit.deployState = MOBILE; towedElement.unit.deployTimer = 0   // 拖曳作废展开进度；解挂后须重新展开
    IF towedElement.unit.fireMission: 清空                           // 拖曳取消炮击任务（任务体销毁）
stopTow(pair, reason ∈ {VOLUNTARY, REPAIRED, TOWER_DEAD, TOWED_DEAD}):
    FOR t IN pair.towerElements: t.towedState = NONE
    pair.towedElement.towedState = NONE                              // MOB暴击保留（REPAIRED时已先修）
触发点：玩家解挂指令 / 维修完成归队（D016+R-19）/ 任一方 destroyElement（§5）

// —— 建筑进驻（修复 gap：最小实现，【拍板默认】；【v1.2】方案5 前置门票）——
FUNCTION garrison(e, b):                                              // e=步兵班元素
    校验 e.unit.flags.canGarrison AND b.garrisonSlots 有空位
        // 【v1.2】"能不能进楼"是进门时查一次的门票（方案5）；garrisonedIn 槽仅对
        //   canGarrison 模板分配（§0），高炮组进楼等后门需求须先拍板再扩旗标
    e.garrisonedIn = b; b.garrisoned += e.elementId
效果：effectiveStealth +GARRISON_STEALTH_BONUS(默认+3)；e 视为 inCover（受击面判定用REAR参考）
     ——防御加成幅度待数值章节，先按"隐蔽+3、受击按尾甲参考"实现
FUNCTION collapseBuilding(b):                                          // 楼毁结局
    FOR eid IN b.garrisoned: e = lookup(eid); applyDamage(e, BUILDING_COLLAPSE_DMG, 塌毁档案)
    移除 Building 实体
FUNCTION unGarrison(e): 清双向引用；e.pos = 建筑旁落位

// —— 后勤（R-18 自动补给；烟弹已并入武器弹药轨，无需单独补烟）
//    【v1.2】补弹改事件触发（方案19）；空投箱并入 CARGO 单位（方案16）——
FUNCTION systemSupply(dt):
    FOR t IN 所有元素 WHERE t.mode == CARGO AND (supplyRoundsCur>0 OR supplyMedicalCur>0):
        // —— 补弹（含烟弹同轨）：只扫待补给集合 × 半径（方案19；【v1.3】登记条件=任一弹药缺口或步兵带伤、
        //    登记点=弹药消耗/受伤事件——审查#11 弃"仅EMPTY"收窄，R-18"补满缺口"语义恢复）——
        //    【v1.2·走查修】补队伍过滤：敌方不得贴我方卡车抽弹药（GDD-02 R-21 同源语义，与 IMPL 对齐；
        //    空投箱结算走本分支，故同样受此过滤）
        FOR u IN unitsWithin(t.pos, t.unit.supplyRadius) ∩ world.pendingResupply
                 WHERE u.teamId == t.unit.teamId:
            FOR e IN u.elements:
                FOR ws IN e.weaponStates:
                    IF ws.ammoLeft >= ws.template.ammoBase: CONTINUE
                    take = MIN(ammoBase−ammoLeft, t.supplyRoundsCur, rate×dt)
                    ws.ammoLeft += take; t.supplyRoundsCur −= take
            // 【v1.2·走查修】注销判据=单位级：该单位全部武器补满才移出集合——
            //   多武器单位（坦克炮+机枪、防空对地+对空）先补满的一件不得注销整单位，
            //   否则仍有 EMPTY 弹药的武器此后永久断补，违背 R-18"自动补满其弹药/医疗缺口"。
            //   （集合仅由 EMPTY 迁移登记、按本判据每 tick 重评注销；医疗不依赖本集合，带伤不影响注销）
            IF u 的全部武器 ws.ammoLeft == ws.template.ammoBase:
                world.pendingResupply.移除(u)
            // 补弹速率与烟弹同轨语义原样保留（保留清单#10，B4 单轨闭环根基）
        // —— 医疗（保持原扫描：卡车贴靠才生效；第12轮拍板后步兵回血唯一承载，保留清单#9）——
        //    【v1.2·走查修】补队伍过滤：敌方不得贴我方卡车吃医疗（与 IMPL 对齐）
        FOR u IN unitsWithin(t.pos, t.unit.supplyRadius) WHERE u.teamId == t.unit.teamId:
            FOR e IN u.elements WHERE unitTypeOf(e)==INFANTRY AND 0 < e.hpCurrent < e.hpMax:
                med = MIN(ceil((hpMax−hpCurrent)/MED_HP_PER_UNIT), t.supplyMedicalCur)
                e.hpCurrent += med × MED_HP_PER_UNIT; t.supplyMedicalCur −= med   // 班灭不复活
    FOR rep IN 维修车元素 WHERE repairPower > 0:
        FOR e IN 贴靠的MECH元素 WHERE hp<max OR hasCrits:
            e.hpCurrent = MIN(hpMax, e.hpCurrent + rep.repairPower × dt)
            IF e.hpCurrent >= e.hpMax: clearCrits(e); stopTow(涉及e的pair, REPAIRED)   // 修好即归队
    // 【v1.2】删除 SupplyBox 遍历（方案16）：空投落地=R-21 实例化一次性 CARGO 单位
    //   （预填 supplyRounds/supplyMedicalCur、不可移动、可摧毁）；"敌方不可拾取"由上方
    //   CARGO 分支的队伍过滤承载（空投箱结算走同一分支，见本函数【v1.2·走查修】注）；
    //   落地后按 R-18 半径自动结算；
    //   已接受代价：一次性元素占用 units 遍历槽微增；"拖走空投箱"玩法如出现需加禁止位
```

---

## 8. 计时器与渗透身份

```
FUNCTION systemTimers(dt):
    FOR u IN units:
        IF u.flags.canInfiltrate:                          // 【v1.2】渗透旗标门控（方案8）：
            u.infiltrationTimer = MAX(0, −dt)              //   非渗透卡不再每tick空写；
        FOR e IN u.elements:                               //   读取点（§3 effectiveStealth）不动；
                                                           //   §8 身份清除口径另按方案8 守则对齐 IMPL（见下与§14 方案8行）
            e.revealTimer = MAX(0, −dt)
            e.suppression = MAX(0, −suppDecay × dt × (u.flags.suppDecayX2 ? 2 : 1))
                // 【v1.2】近卫意志锚点 = 压制衰减×2（方案18）；"溃逃→重整"两态表现
                //   丢失为已接受代价，GDD 卡面表述待同步（§14）
            // 【v1.2】sprintTimer 递减行删除：疾跑由 sprintUntil 时间戳承载（方案14），
            //   统一衰减循环为此多一个例外（已接受代价）
        deployTimer 推进并按状态机迁移（§10）
FUNCTION 渗透身份清除():                                               // 【v1.1】正式定义触发点
    开火（fire 直射链）执行时:
        IF w.sniperFlag OR w.meleeFlag:                                // 【v1.2·走查修】仅狙击/近战条件位开火清零
            u.infiltrationTimer = 0                                    //   ——按方案8 守则"以 IMPL 为准"对齐，
                                                                       //   普通直射（含自卫）不清：渗透班还手不暴露；
                                                                       //   爆破作业已裁剪（见§13/§14清单③）
```

---

## 9. 经济、卡组配额与部署（修复 gap：配额体系）

```
// 卡组构筑期（战斗外）——配额全部在此校验，战斗内不再重复
FUNCTION validateDeck(deckSlots):
    FOR c BY 类别: Σ(主力池) <= 类别主力配额 AND Σ(预备队池) <= 类别预备队配额   // GDD-01配额表
    FOR slot: slot.copies <= slot.card.perCardLimit                    // 每卡限份数（指挥班组=1）
    火支子配额: Σ copies by quotaGroup <= {HOWITZER:3, AT_GUN:2, ROCKET:1}
    FOR slot: slot.card.unlockBy 已解锁，否则拒绝                       // 渗透班等特化解锁
    空降卡占预备队池：pool==RESERVE 强制归池

// 战斗内购买——从卡组余量扣
FUNCTION purchase(player, card):
    slot = player.deckSlots.find(card); IF slot == null OR slot.copiesLeft <= 0: 拒绝
    IF player.points < card.cost: 拒绝
    player.points -= card.cost; slot.copiesLeft -= 1; player.spawnQueue.push(card)  // 一命制不回补
spawn: 普通卡→己方部署区；canInfiltrate 卡→任意地图边缘（敌部署区边缘除外）R-04
       【v1.3·审查#4】混编卡（装掷）开局默认车载：班元素按 seats 预挂 carriers（写 mountedIn；同卡不写 cargoUnits）
占点判定: 目标点半径内仅一方存活单位 → 归属切换（存活=elements 非空）

// 【v1.2】部署初始化派生名单（方案2/3/4）——每次部署/单位入场时重建：
//   aaRoster         = { e ∈ 存活元素 | e.weapon.targetMask & AIR_BITS 或 e.unit.opticsAir > 0 }
//                      消费点：§3.B 对空探测、§4.A 对空交战。
//                      重机枪（AIR_LOW 位，GDD 第3轮拍板）必须在列；52-K/Flak 88（D029 三模式）
//                      必须进 indirectDispatch，漏配即曲射静默失效（方案3 已登记依赖）
//   indirectDispatch = { e | e.unit.modeSet & INDIRECT }（§4.B 曲射分流；setElementMode 动态刷新）
//   声测名单         = { e | e.unit.sonarRadius > 0 }（§3.D 侦听侧；DEPLOYED 按扫描时判定）
//   已接受代价：名单为部署期静态推导——未来"临时获得对空/曲射能力"的运行时兜底需刷新逻辑，
//   否则出现"有能力不打"（方案2/3）
```

---

## 10. 状态机迁移表（【v1.2】狙击/近战路由行并入普通直射（方案1）；EMPTY 挂待补给登记（方案19））

**weaponStates：**

| 当前 | 事件/条件 | 下一态 | 动作 |
|---|---|---|---|
| READY | 对空位武器（【v1.2】仅 aaRoster 内元素，方案2） | （对空自动）AIMING | R-17，不受 stance/mode |
| READY | 对地位武器（含近战/狙击档案）且目标有效且开火许可 | AIMING | timer=aimTime×aimFactor；近战档案 aim≈0，狙击档案超长 |
| AIMING | timer≤0 且目标有效 | 开火→RELOADING | 普通/近战→弹丸（近战必中档）；狙击→弹丸，命中后走 §5 R-02 分支 |
| AIMING | 目标死亡/失标记/禁射 | READY | 不消耗 |
| RELOADING | timer≤0 且 ammo>0 | READY | — |
| RELOADING | timer≤0 且 ammo=0 | EMPTY | 【v1.2】登记 world.pendingResupply（方案19）；【v1.3】弹药缺口/受伤事件亦登记（审查#11 缺口制） |
| EMPTY | 补给转满 | READY | 【v1.2】从 world.pendingResupply 注销 |
| 任意 | 元素被拖/车载非车载武器/mode=TOW·CARGO·TRANSPORT（【v1.2】仅模板 modeSet 含对应位者，方案13） | 冻结 | timer 保持 |

**deployState：**（与 v1.0 相同，略——MOBILE→DEPLOYING→DEPLOYED→PACKING→MOBILE；移动令即回 MOBILE 作废进度）

---

## 11. BalanceConfig 新增/调整常数（【v1.2】更新）

新增：`SMOKE_RADIUS`、`SMOKE_TTL`、`CALIB_ACC_BONUS`（侦察校准命中档，如1.25）、`CALIB_PER_SHOT`（按发累积）、
`CALIB_MAX_REDUCTION`（校射最大收束比例）、`GARRISON_STEALTH_BONUS`（默认+3）、`BUILDING_COLLAPSE_DMG`、
`MED_WEIGHT_PER_UNIT`（医疗品单份重量，混装载重核算）、
`SNIPER_BASE_PROB`（R-02 基础概率；【v1.2】先命中再判定后须重新标定以保持期望击杀率，方案1）、
`SUPP_DECAY_MULT_GUARD`（近卫压制衰减倍率，=2，方案18）。
调整：疾跑不再用速度乘数，改为 `SPEED_TABLE` 升 1 档（方案14）；待补给登记/注销无新常数（方案19）。
沿用：`SPEED_TABLE[1-5]`、`STEALTH_FACTOR_TABLE[0-10]`、`meleeRange=50`（近战档案 maxRange 承载）、
`suppPenalty/suppDecay`、`critPerHP`、`MED_HP_PER_UNIT`、`R18半径=80`、`INFIL_MULT/AMBUSH_MULT/REVEAL_MULT`、
`AMBUSH首击精度`、`声测LOCATE阈值/MAX_R·MIN_R`、`下车20s/车载被毁扣60%`、KE锚点(1.8/−0.8)与HE曲线为固定公式。

---

## 12. 对空结算接口约定（边界：地面侧 ↔ 航空系统）

```
地面侧可见的飞机对象（航空系统提供，只读契约）：
    AircraftRef { pos, altTier: LOW|MID|HIGH, hpCurrent, hpMax, armorAA }
对空命中结算 resolveHitAA(p, aircraft):
    r = p.pen / max(aircraft.armorAA, 1)        // 飞机无分面装甲，单值
    mult = r*r/(1+r*r)                          // 对空一律 HE 曲线（对软目标规则一致）
    aircraft.hpCurrent -= p.damage × mult       // 击落判定、坠毁表现归航空系统（hp<=0）
Flak 38"对空伤害更高" = 武器数值配平，无机制分支。
渗透班"引导空投"：标定指令写入 world.beaconByUnit[渗透班unitId]
    （【v1.2】信标改全局旁表，方案9；§8 身份清除不适用——标定不算暴露）；
    航空系统投散时按键读取该表 → 散布 × 0.5（接口约定，公式在航空侧）。
    【v1.2】空投落地承载（方案16）：R-21 落地事件实例化一次性 CARGO 单位
    （预填物资、不可移动、可摧毁、敌方不可拾取；【v1.3】crate 模板 supplyRadius 必配 80——
     原规格漏配则按半径过滤的拾取链对箱子恒不触发，审查修复），补给结算全部走 §7 CARGO 分支；
    航空侧 R-21 写入口不在本五类范围，落地时需与本承载方式对表核对（方案16 已登记）。
```

---

## 13. 审查问题 → 修复位置对照（验收清单）

> 【v1.2】"修复位置"列按方案1（狙击/近战档案化）与方案9（旁表化）更新指向；审查问题本体与结论不变。

| 审查问题 | 修复位置 |
|---|---|
| B1 武器缺射程/散布字段 | §0 武器子字段 +§4 selectTarget(minRange) +§4 fire(散布) |
| B2 狙击死代码 | §0 sniperFlag（结算条件位）+ §4 直射链 + §5 resolveHit R-02 分支【v1.2 方案1】 |
| B3 近战死代码 | §4 直射链 + §5 resolveHit meleeFlag 分支【v1.2 方案1】 |
| B4 烟雾闭环断裂 | §0 SMOKE=武器档案单轨 + §5 spawnSmokeZone 定义 + §4 烟弹发射（BALLISTIC 无目标弹丸）|
| B5 防空对空对地互斥 | §0 AA移出mode + §4 A/B 并行分流（【v1.2】对空循环限 aaRoster，方案2）|
| B6 卡车槽位层级错位 | §0 mode/cargo/supply 下沉元素级 + §7 CARGO装货（【v1.2】附页化，方案12）|
| B7 destroyElement 无定义 | §5 完整定义（车载/运兵/物资/拖曳/掩护连带；【v1.2】旁表按键注销，方案9）|
| B8 车载/运兵 pos 不随动 | §2 systemMove 随动分支 |
| B9 狙击0血僵尸班 | §5 sniperSettleOnHit 走 applyDamage + §0 不变式（elements 内必存活）|
| B10 装甲0除零 | §5 resolveHit 无甲守卫 |
| g-R01 标记无消费 | §4 fire() CALIB_ACC_BONUS |
| g-R15 自卫直射孤立 | §4 INDIRECT 分支触发（【v1.2】selfDefenseProfile 判空短路，方案3）|
| g-伏击视野减半 | §3 detectionRange × 0.5 |
| g-炮击任务 fireAt/门控 | §4.3 开火许可门 + fireAt 定义 + setElementMode/拖曳清任务 |
| g-拖曳无解除 | §7 stopTow + 触发点 |
| g-配额缺失 | §9 validateDeck + purchase 扣余量 |
| g-建筑进驻 | §7 garrison/collapseBuilding（【拍板默认】；【v1.2】canGarrison 前置，方案5）|
| g-卡车载重混装 | §7 buySupplies 重量核算 |
| g-威胁值无来源 | §4 selectTarget 可计算定义 |
| g-对空结算悬空 | §12 接口契约 |
| g-校射口径 | §4.3 按发累积【拍板默认】（【v1.2】进度随任务体，方案10）|
| g-渗透爆破/倍率 | 部分修复：§8 爆破动作触发身份清除；爆破作业功能已拍板去除（见下）|

**遗留项闭环（用户拍板：爆破作业功能去除，不设 v1.2）**：
- 渗透破坏班/勃兰登堡：不再承担"炸后勤车/炸停止状态牵引炮"。保留职能 = 渗透进场（R-04）+ 偷占目标点 + 引导空投标定（§12 接口）；自身轻武装自卫照常。
- 工兵排：保留喷火武器与对工事/建筑的 vsFortMult×2 攻击加成；"爆破"不再是独立动作系统——对建筑的毁伤通过携带 vsFortMult 的武器攻击实现。
- R-04 表述同步：身份消失条件由"开火或爆破后"改为"狙击/近战开火后"（【v1.2·走查修】按方案8 守则以 IMPL 口径对齐：普通自卫开火不清身份，详见 §14 清单③）。
- 政委光环"冲刺+1档/爆破+50%"维持此前裁剪（督战=单纯近战攻击）。
- GDD 文档同步清单（累积版，含 v1.2 新增项）见 §14 末尾。

---

## 14. v1.1 → v1.2 变更记录（19 条替代方案逐条）

> 依据：docs/GDD-02-函数变量调用频率与替代方案.md（三遍纸面推演合并稿，方案1–19 全部拍板采纳）。
> 落地纪律：sketch=落地方法，negativeImpacts=已接受代价，本文不修复这些代价。
> 槽位账目：单位静态 30（不变，flags/auraDef 注记更新）+ 单位运行时 21→**17**（删校射两槽、旁表化两槽）+
> 元素静态 15→**14**（删 turretTraverse）+ 元素运行时 16→**17**（sprintTimer→sprintUntil，增 garrisonedIn）= **78 槽位**；
> 武器 27→**26** 子字段（删 specialAmmo）。条件分配槽：critSlots（仅MECH）、rotating（仅 fireArcDeg<360）、
> 载运/物资附页（hasCargo/hasMount/hasSupply）、garrisonedIn（仅 canGarrison）——总数按满配计。

| # | 方案 | 落地位置与承载 | 关键语义变化 / 已接受代价 |
|---|---|---|---|
| 1 | 狙击/近战路由档案化 | §0 meleeFlag/sniperFlag 改结算条件位；§4 取消两 flag 路由分支；§4.5/§4.6 独立函数取消；§5 resolveHit 新增 melee/sniper 命中分支 + sniperSettleOnHit；§10 状态表路由行并入 | 狙击"先判定概率"→"先命中再判定"（期望靠 SNIPER_BASE_PROB 重标定保持，方差变化）；近战走 aim/装填周期，"一拍即死"节奏变慢，反炮兵/反后勤克制变弱；政委 MELEE 光环消费点移入直射伤害链（会放大近距射击）；closeCombatBonus 失去函数边界，由 meleeFlag 条件位防守 |
| 2 | 对空链点名表 | §9 aaRoster（targetMask&AIR 或 opticsAir>0）；§3.B 探测分支、§4.A 交战循环只遍历名单；低空目视分支保留全体 | 重机枪（AIR_LOW）必须在名单；失去"临时获得对空能力"的运行时兜底，需名单刷新逻辑；低空目视共享情报路径与名单分开维护 |
| 3 | 曲射链按模板分流 | §9 indirectDispatch（modeSet&INDIRECT）；§4.B 分流加名单门；indirectRole 入口加 selfDefenseProfile!=null 短路；setElementMode 动态刷新分发表 | 静态分发表失去"战场改装"兜底，切模式必须同步刷新；52-K/Flak 88 漏配即曲射静默失效；R-15 自卫直射链不得影响直射-only 卡的原路径 |
| 4 | 声测侦听侧名单化 | §9 声测名单；§3.D 名单空/全灭即整段跳过；声源侧（开火 upsert SoundTrack + acousticSignature）完整保留 | 声测班全灭后不再产生/收窄 IntelCircle，盲射配合玩法止步于已有冻结圈（"规则内正确"，设计确认接受）；"模糊圈折算 markLevel 第四档"变体未采纳；砍读侧勿误伤声源侧 |
| 5 | 驻楼槽前置短路 | §0 garrisonedIn 仅 canGarrison 分配；§3 effectiveStealth、§7 garrison 加 canGarrison 前置门票 | 高炮组进楼等后门需求被旗标挡住，需先拍板扩旗；只对非步兵卡短路，步兵驻楼链完整保留；"驻楼受击尾甲减伤"缺口本就不在伪代码，维持待数值章节 |
| 6 | 炮塔车转向豁免 | §0 rotating 条件槽（仅 fireArcDeg<360 分配）；§2 转向处理 360° 早退；§5 resolveHit 受弹面按模板短路 | 语义从运行时判断变模板断言：未来"炮塔卡死"类状态伤需把"炮塔可用"做成可变位；高炮"基座全向 360°"为推断值，逐卡核对责任在卡面；R-09 克制链收窄到无炮塔 7 卡 |
| 7 | crit 四槽按 unit_type 短路 | §0 critSlots 非 MECH 为 null；§2 moveSpeed、§6 三 factor 读槽判空返回默认 | 白名单须精确（火箭炮牵引车等无甲 MECH 保留四槽）；未来精英步兵"装填手阵亡"类状态伤无现成槽；D.5 自注口径需同步改写（文档漂移项） |
| 8 | 渗透计时器门控 | §8 systemTimers 渗透衰减行加 flags.canInfiltrate 门；读取点（§3/§8）不动；【v1.2·走查修】身份清零对齐为仅 sniperFlag/meleeFlag 条件位开火触发 | 非渗透卡不再每tick空写13200次；清零口径由 v1.1 遗留的"任意开火清"改为 IMPL 同款"仅狙击/近战清、普通自卫开火不清"（方案8 守则，GDD 同步清单③）——渗透班自卫还手不再暴露身份 |
| 9 | 空投信标/狙击掩护改全局旁表 | §0 删 UnitInstance.airdropBeaconPos/sniperCoverTargetId，WORLD 增 beaconByUnit/coverByTarget；§12 标定写旁表、航空侧按键读；§5 destroyElement 遍历清理改按键注销；r02KillTally 保留在单位 | 注销遗漏即悬空引用（航空侧对已死单位投弹），所有销毁路径收口 destroyElement；跨系统契约从"字段在单位上"变"全局表"；r02_kill_tally 不随迁，多班排累计制归属不变 |
| 10 | 校射三槽下沉任务体 | §0 删 calibTargetPos/calibProgress，FireMission 内嵌 calibProgress/calibTargetPos；§4.3 读写走 fm.*，任务销毁进度失效；§4 fire() 直射收束改读 u.fireMission（无任务=无收束）；systemCombat 尾部 fireMission 判空保留 | ZiS-3/52-K 双职炮直射在任务结束后读不到收束值（"保留最近任务收束缓存"变体未采纳，直射不吃历史校射）；拖曳/切模式清任务级联改为销毁任务体，漏改即"拖走还打"；R-16"两连打同点互不叠加"由各连各任务体天然保留 |
| 11 | 钨芯并入弹药档案 | §0 删 WeaponTemplate.specialAmmo 与 ws.specialAmmoLeft；ammoProfiles 增受限档{count:3, penBonus:+3}档内自计数；§4.2 切档条件显式保留 | "仅正面打不穿才切、档内计数"必须显式保留，防"见坦克就喷钨芯"稀释第11轮稀缺感；烟弹/医疗品不并入，SMOKE 维持独立档案 |
| 12 | 载运/物资槽子结构化 | §0 flags 增 hasCargo/hasMount/hasSupply，mountedIn/cargoUnits/supplyRoundsCur/supplyMedicalCur 改附页条件槽；§2 随动、§4 许可门、§5 连带、§7 上下车/装货各分支按槽存在性短路；world.mount_requests 惰性建表为实现侧结构——机制版无此队列（上下车为直接指令），不适用 | 装掷 251 车毁"扣60%血"连带必须只对有附页单位执行，漏判即"车毁人全安"、克制链失效；结构注记化而非物理分组（机制版不做 §D.5 整体改版）；上车20s 进度在无附页单位上的查询语义须为"无请求" |
| 13 | 三模式许可门按 mode_set 剔除 | §4 开火许可 towed/mode 两道门改查 modeSet 位掩码；§10 冻结行同步注记 | 失去"载货状态不作战"运行时兜底，战地改装/缴获需 mode_set 支持运行时扩位；【v1.2·走查修】数据配置硬要求扩为"一切可被拖卡（至少中/重坦与轻防空）mode_set 必须含 TOW 位"——被拖方主体是中/重坦（R-19），不止轻防空，漏配即拖曳中禁射失效；未加 towedState==TOWED 无条件短路兜底（与方案13 已接受代价相抵，如需兜底须拍板）；R-19"双方禁射"对称性依赖两门同开 |
| 14 | 疾跑改时间戳 | §0 sprintTimer→sprintUntil；§2 moveSpeed 升1档；§8 删递减行；§11 删速度乘数常量 | systemTimers"统一衰减"多一个例外；单场约24万次空写消除；疾跑"速度+X%"表述改挂 SPEED_TABLE（GDD 同步） |
| 15 | 删除死字段 turret_traverse | §0 ElementTemplate 删 turretTraverse（15→14）；"无炮塔"语义由 fireArcDeg<360 + turnRate 承载 | 未来做"炮塔独立转速"机制需重新加字段，删除后短期无回退路径 |
| 16 | 空投箱改为一次性 CARGO 元素 | §0 删 WORLD.SupplyBox（机制版字段清单即 §0 WORLD 行，已同步）；§12 空投落地实例化一次性 CARGO 单位（预填物资/不可移动/可摧毁/敌方不可拾取）；§7 删 SupplyBox 遍历，CARGO 分支自动覆盖（含队伍过滤）；§D.6 清单缺口补列属实现侧文档 | 一次性元素占用 units 遍历槽微增；"拖走空投箱"玩法需禁止位；航空侧 R-21 写入口需与地面承载对表（§12 已登记核对项） |
| 17 | 军官"射程+10%"砍除 | §0 auraDef 注记 PRECISION 仅精度；§4 fire()/selectTarget 注记确认不补射程消费点；GDD 卡面待同步 | 德军军官走位站位价值下降（射程诱惑消失）；未选"反向补实现"档（避免 selectTarget 每 tick 光环遍历） |
| 18 | 近卫意志改锚压制衰减×2 | §0 flags 增 suppDecayX2；§8 压制衰减行按旗标 ×2；§11 新增 SUPP_DECAY_MULT_GUARD=2 | 是近似不是还原：丢失"溃逃→重整"两态表现；卡面"溃逃重整×2"改写为"压制恢复加倍"；未来若加溃逃/追击机制本近似不复用 |
| 19 | 弹药补给事件触发 | §0 WORLD 增 pendingResupply；§10 EMPTY 迁移登记；§7 补弹扫描改 待补给集合×在场CARGO×同队过滤，注销=单位级判据（全部武器补满，【v1.2·走查修】）；destroyElement 挂注销；速率与烟弹同轨原样保留；医疗/维修分支扫描不变（含队伍过滤） | 必须保留补弹速率与烟弹同轨，否则丢 B4 单轨闭环（第10轮烟弹体系）；事件集合需维护（EMPTY 登记、单位级补满/车毁注销——多武器单位先满的武器不得注销整单位，否则其余 EMPTY 武器永久断补）；【v1.2·走查修】已接受语义如实修正：仅 EMPTY 登记单位受补，未打空的缺口（<基数未空）不入集合不受补——非"仍走原速率补" |

### GDD-02 文档待同步清单（供策划侧修 GDD，累积）

> v1.1 遗留 5 项 + v1.2 新增项。改完一条勾一条；机制语义冲突时以本文档（机制权威伪代码 v1.2）为准。

1. 【v1.1遗留】士气类效果作废：政委/军官"共通基础光环（士气阈值+15%、重整加速，D034）"、近卫"士气阈值+"、国民掷弹兵"士气阈值低"——伪代码无溃逃/重整/士气条锚，标记作废或另行拍板。
2. 【v1.1遗留】渗透班卡面"爆破高倍率/炸后勤车/炸停止状态牵引炮"表述删除；保留职能 = 渗透进场（R-04）+ 偷占目标点 + 引导空投 + 轻武装自卫。
3. 【v1.1遗留·v1.2走查对齐】R-04 身份消失条件改为"狙击/近战开火后"：普通自卫开火不清身份，与 IMPL 实现同口径（方案8 守则"以 IMPL 为准"，两份 v1.2 不再两存）；"爆破"部分维持裁剪。
4. 【v1.1遗留】工兵"爆破"改锚为对工事/建筑的 vsFortMult×2 攻击加成（喷火高压制/高重伤率维持数值承载）。
5. 【v1.1遗留】"建筑进驻加成"补充内容定义：当前伪代码按"隐蔽+3、受击按尾甲参考"实现，幅度待数值章节。
6. 【v1.2】军官"精准光环"删除"射程+10%"项，仅保留"精度+10%"（方案17；D034 补充拍板第4轮表述同步）。
7. 【v1.2】近卫意志新表述：由"溃逃后重整速度×2"改为"压制恢复加倍（压制衰减×2）"；"近卫不散"卡面语保留但机制注脚更换（方案18）。
8. 【v1.2】医疗品语义统一：医疗补给班两阵营取消（第12轮拍板）后，GDD-01/02 残留条目删除；医疗品=卡车物资模式载运（120份/车，按重量混装）+ 步兵回血（MED_HP_PER_UNIT，班灭不复活）。
9. 【v1.2】狙击语义注记：R-02 结算改"先命中再判定"（方案1），卡面如有击杀率表述需注明期望经 SNIPER_BASE_PROB 重标定保持、方差变大、"一枪定生死"手感变化。
10. 【v1.2】近战语义注记：近战=0~50m 必中直射武器档案、走瞄准/装填周期（方案1）；骑兵/冲锋枪排"一拍即死"节奏变慢；冲锋枪排卡面"近战火力全场最强"改为档位化表述；政委 MELEE 光环（近战+15%）消费点移入直射伤害链、会同时放大近距射击，卡面需注明。
11. 【v1.2】R-03 补充边界：声测班全灭后不再产生/收窄定位圈（已有圈按冻结精度保留），"火炮盲射声测圈"配合以声测班存活为界（方案4）。
12. 【v1.2】R-21 承载表述：空投落地箱=一次性 CARGO 单位（不可移动、可摧毁、敌方不可拾取），拾取/补给结算同 R-18 半径规则（方案16）。
13. 【v1.2】疾跑表述：如卡面/数据全集存在"疾跑速度+X%"乘数表述，改挂 SPEED_TABLE 升1档（方案14）。
14. 【v1.2】"炮塔回转"类字段表述删除（turret_traverse 死字段已删，方案15）；"无炮塔"表述统一指向"射界<360°+车体转向期侧露（R-09）"。
15. 【v1.2】钨芯弹表述并入选弹档案（R-11 体系内受限档）：PaK38 钨芯=每门3发受限弹药档、正面打不穿才自动切换、用完即止，不再描述为独立弹种槽（方案11）。

---

## 15. v1.2 → v1.3 变更记录（审查问题文档-v1.2 的 13 项修复；与 IMPL v1.3 同步）

> 编号对应问题文档；#1~#5 单遍发现（high），#6~#13 双遍以上命中（medium）。裁决原则：机制语义冲突以 GDD-02 为准。

1. **车载/运兵连带去重（#1）**：destroyElement 连带改元素并集去重、只扣一次 60%；跨卡运兵连带补齐扣血（原仅落位，GDD"车毁连带扣60%"）。
2. **声测圈阵营（#2）**：upsertIntelCircle 记 s.teamId（侦听方）——原 team 未定归属、盲射消费链对不上。
3. **上下车循环（#3）**：机制版下车双向清理本就正确（注记确认）；切出 TRANSPORT 的清理由"卸下 cargoUnits 于原地"语义覆盖（元素级 cargoUnits 使然）。
4. **装载过滤与开局接线（#4）**：上车仅 SQUAD 元素 + 载具须 TRANSPORT 模式；spawn 补混编卡开局默认车载（班元素预挂 carriers）。
5. **工兵 vs_fort 直射（#5，疑点②闭合）**：§5 resolveHit"命中建筑 ×vsFortMult"行的目标可达性补齐（fire() 对建筑跳过标记项；实现侧增 AttackCmd 与 hit_target 类型扩展，见 IMPL v1.3 §V#5）。
6. **道路机动（#6）**：机制版本有 onRoad 分支（§2 moveSpeed），注记确认保留——本项为 IMPL 侧缺陷，v1.3 IMPL 已补齐，两版同向。
7. **反狙击掩护 1:1（#7）**：SetSniperCover 指令带替换语义校验（同一狙击先删旧条目再挂新目标）——"可掩护一个友军单位"可执行。
8. **卡车装载门（#8）**：上车加 TRANSPORT 校验、buySupplies 加 CARGO 校验、seats 消费点成文；mountedIn 改全体 SQUAD 元素常驻槽（原附页条件槽使无座位步兵卡无承载）。
9. **对空拖曳门（#9，疑点⑤闭合）**：aaAutoEngage 加拖曳短路——被拖防空不再自动对空开火（R-19 扩展至对空链）。
10. **TOW 位数据要求（#10）**：被拖侧枚举补全火支全部牵引炮与火箭炮；维持"无运行时兜底"拍板。
11. **R-18 补给缺口制（#11）**：登记条件=任一弹药缺口或步兵带伤（弹药消耗/受伤事件登记），注销=单位级补满——弃"仅EMPTY"收窄，GDD:247"补满缺口"语义恢复（GDD 无需回写）。
12. **拖曳元素级（#12）**：TowPair 改 {towerElements, towedElement}；startTow 按吨位降序贪心累计制（重坦45t=2×30t 或 1×45t；杜绝 30t 车被指派 45t 任务）；删单位级 towPair 槽，账目 78→77。
13. **校射视线定义（#13）**：新增 pointInFriendlyVision（含穿林/穿烟衰减）；§4.3 改先判后加（原"循环内先加、循环外又判不增长"自相矛盾——终审#7 同源修复）。

**附属修复**：FireMissionCmd/CancelFireMissionCmd 创建入口成文（原任务只有清空写点）；setElementMode 切进 INDIRECT 保留任务（对齐 GDD 表A4/IMPL，删"或 e 是炮"分支）；驻楼受击 REAR 分支落地（§7 效果声明兑现）；crate 模板 supplyRadius=80 硬要求；SMOKE 武器 targetMask=0 数据规则；掩护者死亡删值为该 unitId 的旁表条目。机制版不适用项：use_self_defense 复位（机制版按调用传 profile，无常驻标志，无污染路径——IMPL 侧已修）。

**账目**：77 槽位 = 30 + 16 + 14 + 17（单位运行时 −1：towPair）；武器 26 子字段不变。与 IMPL v1.3 总账同向（77），分项归口差仍按 IMPL §D.8 口径表（sprint 单位/元素级等既有登记不变）。

**GDD-02 待同步清单新增（第 16 条）**：拖曳指令粒度改元素级（TowCmd 指定牵引元素与被拖元素；R-19"两辆并拖"可在单卡内表达）——GDD-02:253-256 若有"整卡同拖"表述需同步。

---

## 16. v1.3 → v1.4 变更记录（审查问题文档-v1.3 的 17 项机械缺陷修复；与 IMPL v1.4 同步）

1. **toggleAmbush 处理体（high#2）**：§2 补定义——ambushActive 恢复 TRUE 写点，R-12 四张伏击卡整链可达。
2. **驻楼×移动互锁（medium 新发现）**：systemMove 移动自动出楼（unGarrisonAll）——楼槽释放、加成终止。
3. **TOW 位数据要求全量（medium verified ×2）**：被拖侧补迫击炮排、牵引侧补维修班/重拖/豹救（与 IMPL D.1#15 同口径）。
4. **startTow 互斥门 + 展开闸（medium ×2）**：牵引元素须未在拖且 mode==TOW；被拖单位强制回 MOBILE（拖完须重新展开 30s）。
5. **markLevel 重算式（medium 新发现）**：本轮接触最高等级、无接触 NONE（空集行为补定义；与 IMPL 统一——侦察撤离后加成回落）。
6. **R-02 tally 实击杀（low 新发现）**：记 actual=MIN(kills, hp)。
7. **隐蔽口径统一（low 新发现）**：effectiveStealth 改 IMPL 式（乘区先行、地形/驻楼加成后置、×10 整型存储 20/30）——两版隐蔽公式口径差消除。
8. **FireMission.shotsFired + POINT 专属校射（low）**【拍板默认】：LINE 取样序号由任务体承载；LINE/CREEP 不参与校射（GDD 校射锚在点射击）。
9. **钨芯实例化深拷贝（low）**【拍板默认】：weaponStates 深拷贝 ammoProfiles——每门独立计数。
10. **声测生命周期三语义（low verified）**【拍板默认】：圈键=声源单位；换阵地 accum 清零；停火期不增长。
11. **上车模式门 + 账目（medium ×2）**：模式门改"mode ∉ {CARGO, TOW}"可载（保 R-07 与 D065 双承诺）；多载具最少挂载分配；seats 账目含同卡 mountedIn。机制版无请求队列，到期复核义务注记由指令时点承担（IMPL 侧已修）。
12. **flags 特技资格位（medium 新发现）**：canSniperCover/canAirdropBeacon——两指令校验归属（原全军可下达）。

**账目**：77 槽位不变（flags 位段 +2 位、FireMission +1 字段不占槽）；武器 26 子字段不变。
**GDD 待同步清单新增**：第 17 条——"对建筑直射"经指定目标指令（AttackCmd）下达（工兵/ISU/OT-34/ML-20 直射拆楼入口）；第 18 条——驻楼单位移动即自动出楼。
