# 地面单位机制伪代码 v1.1（审查修订版）

> 基于 v1.0（冻结变量集）+ 三遍审查（GDD-02-伪代码审查问题文档，52 项）的修订。
> 本版修复全部 10 个 blocker 与主要 gap；涉及策划拍板处采用【拍板默认】并标注，可推翻。
> 变量集：单位静态 30 + 单位运行时 21 + 元素静态 15 + 元素运行时 16 = **82 槽位**；武器 **27** 子字段。
> §13 给出 审查问题 → 修复位置 对照表。

---

## 0. 修订后数据结构（82 槽位 + 27 武器子字段）

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
    closeCombatBonus                      // 近战加成：骑兵1.8，冲锋枪排高档，默认1.0
    towTonnage, ownWeightTons             // 拖曳吨位 / 自重   R-19
    repairPower                           // 维修力（0=无）
    supplyRadius                          // 自动补给半径（0/80m）R-18
    acousticSignature                     // 声响特征（被声测定位速率）
    sonarRadius, sonarRate                // 声测侦听半径/收束速率   R-03
    auraDef                               // {kind: MELEE|PRECISION, bonusPct, radius} | null
    flags                                 // canSprint canGarrison canAmbush canInfiltrate
                                          // noMoveVisionPenalty forestWalkSilent
                                          // requiresMark singleSquadCard
    pool                                  // 【v1.1】MAIN | RESERVE（主力/预备队双池）
    perCardLimit                          // 【v1.1】每卡限份数（指挥班组=1；一般2-3）
    quotaGroup                            // 【v1.1】火支子配额桶：HOWITZER/AT_GUN/ROCKET | null
    unlockBy                              // 【v1.1】特化解锁标识 | null（R-04渗透班等）

STRUCT UnitInstance:                      // 单位运行时 21
    unitId, teamId, alive
    pos, movePath[]                       // 队形基准点/航点
    deployState, deployTimer              // 行军/展开中/已展开/收起中
    stance                                // 自由开火/禁射（仅约束对地武器；对空恒自动 R-17）
    fireMission                           // {form:POINT|LINE|CREEP, ammoMult, salvoMode:FULL|HALF,
                                          //  targetPoint, targetLine, creepSpeed, shotsLeft}
    calibTargetPos, calibProgress         // 连内共享校射  R-16（按发累积，见§4）
    markLevel, spottedMask                // 无/发现/侦察校准  R-01 / 队伍发现位掩码
    infiltrationTimer                     // 渗透60s  R-04
    ambushActive, ambushShotBonus         // 伏击中 / 脱离伏击首击加成待触发  R-12
    towPair                               // {towers:[unitId...], towed:{unitId, elementId}} | null
    sniperCoverTargetId                   // 反狙击掩护对象
    airdropBeaconPos                      // 引导空投标记（渗透班指令写入，§12接口）
    r02KillTally                          // 狙击累计击杀 → 灭班计数  R-02
    elements[]                            // 车/炮/班实例【不变式：数组内元素必然存活】
    // 【v1.1】删除：mode、smokeLeft、supplyRoundsCur、supplyMedicalCur、cargoUnits（下沉元素级）

STRUCT ElementTemplate:                   // 元素静态 15
    elementType                           // VEHICLE/GUN/SQUAD
    unitType                              // INFANTRY/MECH（bodyType 派生：MECH→HARD）
    hpMax                                 // MECH:车体血；INFANTRY:编制人数(1HP=1人)
    armorKE{F,S,R,T}, armorHE{F,S,R,T}    // 四面两类，0-20 相对刻度；T仅空袭读取；0=无甲（合法）
    fireArcDeg, turretTraverse            // 射界（无炮塔±15°）/ 炮塔回转（无炮塔0）
    suppressionVuln                       // 敞篷>1（SU-76等）
    squadQuality                          // 老兵班精度+（国民掷弹兵）
    weapons[], mountedArmament            // 武器表 / 空车可射击标记（251）
    seats                                 // 【v1.1】运兵座位（卡车1班/半履带1班；0=不可载）
    cargoRoundsMax, cargoMedicalMax       // 【v1.1】每车物资上限（600发/120份；0=非卡车）
    cargoWeightMax                        // 【v1.1】每车总载重（按重量混装 D065/D012）

STRUCT ElementInstance:                   // 元素运行时 16
    elementId, pos, facing
    hpCurrent
    critSlots                             // {FC,SEN,RLD,MOB: NONE|MINOR|MAJOR} 仅MECH
    suppression                           // 0-100 连续值，无士气状态
    sprintTimer, revealTimer              // 疾跑 / 开火暴露残留
    mountedIn                             // 所载车辆元素ID | null
    weaponStates[]                        // 每武器 {state, timer, targetId, ammoLeft, specialAmmoLeft}
    rotating, towedState                  // 转向中 / 被拖·牵引中
    mode                                  // 【v1.1】元素级模式 DIRECT/INDIRECT/TOW/CARGO/TRANSPORT
                                          // 卡车每辆独立切换（D065）；火炮每门 DIRECT/INDIRECT
    cargoUnits[]                          // 【v1.1】本车载运的班元素引用（R-07车载/D065运兵同构）
    supplyRoundsCur, supplyMedicalCur     // 【v1.1】本车在途物资（CARGO模式）

STRUCT WeaponTemplate:                    // 武器 27 子字段
    targetMask                            // GROUND/AIR_LOW/AIR_MID/AIR_HIGH 四位
    damageType                            // KE / HE / SMOKE
    penMin, penMax                        // KE 远距~贴脸（HE/SMOKE 相等）
    damage, blastRadius
    maxRange, minRange, dispersion        // 【v1.1】射程上下限(m)与散布半径(m)——迫击炮250~1800、
                                          // 狙击400、犀牛1400 均由此承载；minRange 默认0
    accuracyBase, aimTime, reloadTime, salvo
    ammoBase, ammoWeightPerShot           // 基数6发/门；烟弹=SMOKE武器档案走同一弹药轨【拍板默认】
    projectileSpeed, trajectory           // DIRECT / BALLISTIC
    suppressionPower, critMod, vsFortMult
    specialAmmo{count, penMod}            // PaK38钨芯3发穿+3
    ammoProfiles[]                        // R-11 自动选弹 AP/HE 共槽
    needsDeployed, selfDefenseProfile     // R-05 须展开 / R-15 自卫直射档案
    meleeFlag, sniperFlag                 // 【v1.1】近战标记 / 狙击标记（R-02路由）
    revealTime                            // 开火声响暴露时长（联动声测）

WORLD 实体：SmokeZone{pos,radius,ttl}、IntelCircle{center,radius,teamId}（声测模糊圈，冻结精度）、
           Building{hp,garrisonSlots,garrisoned:[elementId]}、SupplyBox（空投箱，R-21）
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
            e.pos = 牵引车后方偏移(towPair.towers); CONTINUE
        IF e.mountedIn != null:                      // 【v1.1】车载班随车移动
            e.pos = carrier(e).pos + 车位偏移; CONTINUE
        e.pos = 队形偏移(新pos)
    主元素.facing = 朝向路径方向
    IF u.ambushActive: exitAmbush(u)                 // 移动自动退出伏击 R-12
    // 【v1.1】D065运兵：本车 cargoUnits 中的班（跨卡单位）pos 同步跟随
    FOR e IN u.elements WHERE e.mode == TRANSPORT:
        FOR s IN e.cargoUnits: s.pos = e.pos + 车位偏移

FUNCTION moveSpeed(u):                               // 全单位同一函数
    base = SPEED_TABLE[u.speedTier]
    m = TERRAIN[u.tile][u.movementClass].speedMod
    IF onRoad(u) AND u.movementClass != FOOT: m = MAX(m, ROAD_BONUS)
    e = 主元素(u)
    IF e.critSlots.MOB == MAJOR: RETURN 0
    IF e.critSlots.MOB == MINOR: m *= 0.5
    IF u.towPair != null OR anyElementTowed(u): base = SPEED_TABLE[1]   // 拖曳双方最低档 R-19
    IF e.sprintTimer > 0: m *= SPRINT_FACTOR
    RETURN base * m

FUNCTION 转向处理(e, 目标朝向):                       // R-09 不变
    IF |angleDiff(e.facing, 目标朝向)| > fireArcDeg(e):
        e.rotating = true; e.facing += sign × turnRate × dt
    ELSE: e.rotating = false
```

---

## 3. 侦察系统（修复：伏击视野减半）

```
FUNCTION systemSensing():
    // A. 地面互侦（不变式：elements 内均存活，死亡已在 §5 清理）
    FOR (obs, tgt) IN 敌对配对:
        IF dist(obs,tgt) <= detectionRange(obs,tgt): markSpotted(tgt, obs)
        ELIF dist > keepRange(obs,tgt): unmarkSpotted(tgt, obs)
    // B. 对空发现 R-17/R-23（不变）
    FOR aircraft a, FOR ground g:
        IF a.altTier <= g.airCeiling AND dist <= g.opticsAir: spotted(a, by=g)
        IF a.altTier == LOW AND dist <= g.opticsGround:      spotted(a, by=g)
    // C. 标记等级 R-01（不变）
    FOR tgt: tgt.markLevel = MAX(观察者等级)   // category==侦察 → CALIBRATED；其余 → SPOTTED
    // D. 声测 R-03（不变）
    FOR s IN 声测单位 WHERE s.deployState == DEPLOYED:
        FOR ev IN enemySoundEvents WHERE dist <= s.sonarRadius:
            ev.accum += s.sonarRate × ev.sig × dt
            IF ev.accum >= LOCATE_THRESHOLD:
                upsertIntelCircle(team, ev.pos, lerp(MAX_R, MIN_R, ev.accum))   // 圈冻结精度 R-03

FUNCTION detectionRange(obs, tgt):
    r = obs.opticsGround
    IF moving(obs) AND NOT obs.flags.noMoveVisionPenalty: r *= 0.5
    IF obs.ambushActive: r *= 0.5                        // 【v1.1】伏击的视野代价 R-12（原缺失）
    r *= STEALTH_FACTOR_TABLE[effectiveStealth(tgt)]
    r -= ATTEN × forestMetersOnLOS(obs,tgt)
    r -= ATTEN × smokeMetersOnLOS(obs,tgt)
    RETURN r

FUNCTION effectiveStealth(u):                            // 【v1.1】接入建筑进驻加成
    s = u.stealthBase + TERRAIN.stealthAdd
    m = 1.0
    IF moving(u):
        m *= 0.5
        IF u.flags.forestWalkSilent AND inForest(u): m *= 2      // 静默行军（第5轮）
    IF u.infiltrationTimer > 0: m *= INFIL_MULT                  // 渗透60s，开火即清 R-04
    IF u.ambushActive: m *= AMBUSH_MULT                          // 伏击隐蔽大增 R-12
    IF anyReveal(u): m *= REVEAL_MULT                            // 开火暴露
    IF garrisoned(u): s += GARRISON_STEALTH_BONUS                // 【拍板默认】进驻建筑隐蔽+3
    RETURN clamp(s*m, 0, 10)

FUNCTION keepRange(obs, tgt):  RETURN obs.opticsGround × STEALTH_FACTOR_TABLE[tgt.stealthBase]
```

---

## 4. 交战决策（修复 blocker ②③⑤、gap：狙击/近战/自卫/炮击任务/威胁值）

```
FUNCTION systemCombat(u, dt):
    FOR e IN u.elements:                              // elements 内必然存活（§0不变式）
        // ── A. 对空：恒自动、并行、不受 stance/mode 影响（R-17）——修复 blocker ⑤
        FOR w IN e.weaponStates WHERE w.template.targetMask & AIR_BITS:
            IF state==READY AND ammoLeft>0: aaAutoEngage(e, w)
        // ── B. 对地：按元素 mode 分流
        IF e.mode == DIRECT:
            FOR w IN e.weaponStates WHERE 对地位(targetMask.GROUND) AND state==READY AND ammoLeft>0:
                IF NOT 开火许可(u, e, w): CONTINUE
                // 近战分支：修复 blocker ③——近战武器在近距自动接战（走同一状态机，无弹丸）
                IF w.template.meleeFlag:
                    tgt = nearestEnemyElement(e, <= BALANCE.meleeRange)
                    IF tgt: 进入AIMING(短aimTime, target=tgt); CONTINUE
                    CONTINUE
                // 狙击分支：修复 blocker ②——sniperFlag 武器路由到 R-02 结算
                IF w.template.sniperFlag:
                    tgt = selectTarget(u, e, w)               // selectTarget 已按 maxRange=400 过滤
                    IF tgt: 进入AIMING(target=tgt, isSniper=true)
                    CONTINUE
                // 普通直射
                tgt = selectTarget(u, e, w)
                IF tgt == null: CONTINUE
                IF 需转车体(e, tgt): 转向处理(e, 朝向tgt); CONTINUE     // R-09
                进入AIMING(w, tgt)
        IF e.mode == INDIRECT:
            // 自卫直射触发：修复 gap R-15——曲射炮被近身时以惩罚档案直射
            IF 存在敌元素 dist <= w主.selfDefenseProfile.range AND w主 就绪 AND 通过开火许可:
                fire(u, e, w主, 最近敌, profile=w主.selfDefenseProfile)   // 短射程+大精度惩罚
            ELSE IF u.fireMission != null:
                processFireMission(u, dt)                     // §4.3，含开火许可门
        // e.mode ∈ {TOW, CARGO, TRANSPORT}：不开火（开火许可亦拦截）
```

```
FUNCTION 开火许可(u, e, w):
    IF u.stance == HOLD_FIRE AND NOT w.template.sniperFlag==false: RETURN false
        // 【拍板默认】stance 约束全部对地武器（含狙击；对空本就不受 stance 管）
    IF w.template.needsDeployed AND u.deployState != DEPLOYED: RETURN false   // R-05
    IF e.mountedIn != null AND w 不是 mountedArmament: RETURN false
    IF e.towedState != NONE: RETURN false                          // R-19
    IF e.mode ∈ {TOW, CARGO, TRANSPORT}: RETURN false              // D065 载货状态不作战
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

FUNCTION fire(u, e, w, tgt, profile=w默认):
    profile选弹: IF w.ammoProfiles 非空: 按 R-11 自动选弹（AP打甲/HE打软/钨芯自动救场，§4.2）
    IF w.template.sniperFlag:                                      // 修复 blocker ②
        sniperResolve(e, tgt.unit); w.state=RELOADING; ...; RETURN // 不生成弹丸，走R-02概率结算
    w.ammoLeft -= 1; w.state = RELOADING; w.timer = w.reloadTime × reloadFactor(e)
    e.revealTimer = MAX(e.revealTimer, w.revealTime)
    spawnSoundEvent(e.pos, u.acousticSignature × w.salvo)          // 喂声测 R-03
    acc = w.accuracyBase × accuracyCurve(dist/w.maxRange) × aimFactor(e)
        × ambush首击加成(u) × auraBonus(u,PRECISION) × e.squadQuality
        × (tgt.unit.markLevel == CALIBRATED ? CALIB_ACC_BONUS : 1)  // 【v1.1】R-01 校准消费（原缺失）
    FOR i IN 1..w.salvo:
        hit = random() < acc
        base = hit ? tgt.pos : tgt.pos
        scatterR = w.dispersion × (1 − u.calibProgress/100 × CALIB_MAX_REDUCTION)   // 校收割束
        aimPoint = scatter(base, scatterR × (hit ? 0.4 : 1))
        SPAWN Projectile(shooter=e, weapon=w, profile, aimPoint, hitTarget = hit ? tgt : null)
```

```
// §4.2 选弹（R-11 + 钨芯，不变）
FUNCTION 选弹(w, tgt):
    IF w.ammoProfiles 为空: RETURN w默认档案
    IF unitTypeOf(tgt) == MECH:
        IF 标准AP(w).penMax < 正面甲(tgt) AND w.specialAmmoLeft > 0:
            w.specialAmmoLeft -= 1; RETURN 钨芯档案
        RETURN AP档案
    RETURN HE档案

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
        //   散布 = w.dispersion × (1 − calib收割束) + (目标点∈IntelCircle ? circle.radius : 0)
        //   SPAWN Projectile(trajectory=BALLISTIC, aimPoint=落点, hitTarget=null)  // 无目标弹丸
        fm.shotsLeft -= 1; u.calibProgress += CALIB_PER_SHOT          // 【拍板默认】按发累积（GDD"逐发校准"）
    IF fm.targetPoint 不在友军视野: calibProgress 不增长（仍可盲射，散布大）  // R-13/R-16
    IF fm.targetPoint 变更: calibProgress = 0                         // R-16 连内共享、换点重置
    IF fm.shotsLeft <= 0: u.fireMission = null

// 模式切换/拖曳联动（修复 gap：任务悬挂）
FUNCTION setElementMode(e, m):
    校验 m ∈ e.unit.modeSet
    IF e.mode == TOW: stopTow(涉及pair)                               // 切模式先解挂
    IF e.mode == CARGO: e.supplyRoundsCur/supplyMedicalCur = 0        // 卸货
    IF e.mode == TRANSPORT: 卸下 e.cargoUnits 于原地
    e.mode = m
    IF m != INDIRECT OR e 是炮: e.unit.fireMission = null             // 任务取消
```

```
// §4.4 对空自动交战（R-17，修复 blocker ⑤：与对地并行，不再互斥）
FUNCTION aaAutoEngage(e, w):
    tgt = 已发现敌机中 威胁最高者 in range AND altTier <= e.unit.airCeiling
    //   【拍板默认】对空威胁 = 距离最近（可后续换加权表）
    IF tgt: 同 fire() 流程（aimPoint=预测机位, hitTarget=aircraft句柄, 走§12对空结算）

// §4.5 近战结算（修复 blocker ③：由 meleeFlag 武器经状态机调用，不再是孤立函数）
FUNCTION meleeResolve(att_e, def_e):
    dmg = att近战damage × att.unit.closeCombatBonus                    // 骑兵×1.8 / 冲锋枪高档
        × (1 + auraBonus(att.unit, MELEE))                             // 政委近战光环（督战）
    applyDamage(def_e, dmg, 近战档案(走HE曲线))
    injectSuppression(def_e, 近战suppressionPower)
// 【拍板默认】近战=极短距(50m)武器射击，不设专门"近战锁定"状态；双方仍可被第三方远程射击

// §4.6 狙击 R-02（修复 blocker ②⑨：接入状态机 + 走统一伤害入口）
FUNCTION sniperResolve(sniper_e, tgtUnit):
    IF dist > w.maxRange: RETURN                                      // 射程400门（原缺失）
    e = tgtUnit.任一存活班
    covered = EXISTS 友方狙击 s WHERE s.unit.sniperCoverTargetId == tgtUnit.unitId
    killProb = covered ? BASE_PROB × 0.5 : BASE_PROB                  // 反狙击掩护（第1轮）
    IF tgtUnit.flags.singleSquadCard:                                 // 指挥班组/声测班：1~2发概率灭排
        IF random() < killProb: applyDamage(e, e.hpCurrent, 狙击档案) // 【v1.1】走applyDamage→destroyElement
    ELSE:
        kills = (random()<killProb) + (random()<killProb)
        applyDamage(e, kills, 狙击档案)                               // 1HP=1人，扣血即减员
        tgtUnit.r02KillTally += kills
        IF tgtUnit.r02KillTally >= 3:
            最低血存活班.applyDamage(其全部HP)                         // 灭班走同一入口
            tgtUnit.r02KillTally -= 3
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
    facing = facingOf(e, p.approachDir)
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
    // 车载连带 R-07：车内班不消失，扣60%血，落位载具旁，解除装载
    FOR s IN allElements WHERE s.mountedIn == e.elementId:
        s.mountedIn = null; s.pos = e.pos 旁落位
        applyDamage(s, ceil(s.hpCurrent × 0.6), 车毁连带档案)
    // 运兵连带 D065：本车 cargoUnits 中的班同样落位（运兵模式被毁=按车载被毁规则）
    FOR s IN e.cargoUnits: s.pos = e.pos 旁落位                      // 班存活，仅失去载具
    e.cargoUnits.clear()
    // 物资连带：e.supplyRoundsCur/supplyMedicalCur = 0（所载物资随车毁 D065）
    // 拖曳连带：releaseTowIfInvolved(e)（§7）
    // 反狙击掩护失效：IF anyUnit.sniperCoverTargetId == u.unitId AND u.elements空: 清引用
    // 全灭：IF u.elements 为空: u.alive = false; 移出战场; （一命制，无回圈）
    //      声测圈不撤销（R-03 冻结）；光环/侦听随 elements 清空自然失效（查询期按存活过滤）
```

---

## 6. 压制与修饰器（不变，附存活门说明）

```
FUNCTION injectSuppression(e, amount):
    e.suppression = MIN(100, e.suppression + amount × e.suppressionVuln)

修饰器族（查询期计算；所有消费点只遍历存活元素，死元素已从 elements 移除）：
    aimFactor(e)     = (critFC: MINOR×0.75/MAJOR×0.5) × (1 − suppPenalty × e.suppression/100)
    reloadFactor(e)  = (critRLD: MINOR×1.3/MAJOR×1.6) × (1 + suppPenalty × e.suppression/100)
    opticsFactor(e)  = (critSEN: MINOR×0.6/MAJOR×0.3)
    squadHpFactor(e) = e.hpCurrent / e.hpMax
    auraBonus(u, kind) = Σ 存活友方指挥元素 auraDef 匹配 kind 且 dist<=radius 的 bonusPct
```

---

## 7. 展开制、运输、拖曳、驻建筑、后勤

```
// —— deployState 状态机（不变，见 §10 表）——

// —— R-07 车载 / D065 运兵（统一为 cargoUnits + mountedIn 双向引用）——
下令下车: FOR s IN carrier.cargoUnits / FOR s IN elements WHERE mountedIn==carrier:
            s.mountedIn = null; s.pos = 载具旁落位; 移出 cargoUnits
          // 空车留在原地，mountedArmament 照常开火（第5轮拍板）
下令上车: 班静止于载具旁 20s → s.mountedIn = carrier.elementId; carrier.cargoUnits += s
装载校验: Σ s.seats占用 <= carrier_template.seats

// —— D065 卡车三模式（元素级，每辆独立切换）——
setElementMode(truck_e, m ∈ {TOW, CARGO, TRANSPORT}): 见 §4 setElementMode
CARGO装货: buySupplies(truck_e, rounds, medical):
    weight = rounds×ammoWeightPerShot(均摊) + medical×MED_WEIGHT_PER_UNIT
    校验 rounds <= cargoRoundsMax AND medical <= cargoMedicalMax AND weight <= cargoWeightMax
    truck_e.supplyRoundsCur = rounds; truck_e.supplyMedicalCur = medical

// —— R-19 拖曳（修复 gap：补解除路径）——
startTow(牵引组[...], 目标):
    need = CEIL(目标.ownWeightTons / min(牵引组.towTonnage))          // 重坦45/30=2并拖；45/45=1
    IF 可用牵引车数 >= need: 建 towPair; 双方 towedState 置位
    IF 目标.unit.fireMission: 目标.fireMission = null                 // 拖曳取消炮击任务
stopTow(pair, reason ∈ {VOLUNTARY, REPAIRED, TOWER_DEAD, TOWED_DEAD}):
    FOR t IN pair.towers: 对应元素.towedState = NONE
    pair.towed元素.towedState = NONE                                  // MOB暴击保留（REPAIRED时已先修）
    清除双方 UnitInstance.towPair 引用
触发点：玩家解挂指令 / 维修完成归队（D016+R-19）/ 任一方 destroyElement（§5）

// —— 建筑进驻（修复 gap：最小实现，【拍板默认】）——
FUNCTION garrison(e, b):                                              // e=步兵班元素
    校验 e.unit.flags.canGarrison AND b.garrisonSlots 有空位
    e.garrisonedIn = b; b.garrisoned += e.elementId
效果：effectiveStealth +GARRISON_STEALTH_BONUS(默认+3)；e 视为 inCover（受击面判定用REAR参考）
     ——防御加成幅度待数值章节，先按"隐蔽+3、受击按尾甲参考"实现
FUNCTION collapseBuilding(b):                                          // 楼毁结局
    FOR eid IN b.garrisoned: e = lookup(eid); applyDamage(e, BUILDING_COLLAPSE_DMG, 塌毁档案)
    移除 Building 实体
FUNCTION unGarrison(e): 清双向引用；e.pos = 建筑旁落位

// —— 后勤（R-18 自动补给；烟弹已并入武器弹药轨，无需单独补烟）——
FUNCTION systemSupply(dt):
    FOR t IN 所有元素 WHERE t.mode == CARGO AND (supplyRoundsCur>0 OR supplyMedicalCur>0):
        FOR u IN unitsWithin(t.pos, t.unit.supplyRadius):             // 80m 自动，无指令
            FOR e IN u.elements:
                FOR ws IN e.weaponStates:                             // 弹药（含烟弹）按发补
                    IF ws.ammoLeft >= ws.template.ammoBase: CONTINUE
                    take = MIN(ammoBase−ammoLeft, t.supplyRoundsCur, rate×dt)
                    ws.ammoLeft += take; t.supplyRoundsCur −= take
                IF unitTypeOf(e)==INFANTRY AND 0 < e.hpCurrent < e.hpMax:   // 医疗=步兵回血（班灭不复活）
                    med = MIN(ceil((hpMax−hpCurrent)/MED_HP_PER_UNIT), t.supplyMedicalCur)
                    e.hpCurrent += med × MED_HP_PER_UNIT; t.supplyMedicalCur −= med
    FOR rep IN 维修车元素 WHERE repairPower > 0:
        FOR e IN 贴靠的MECH元素 WHERE hp<max OR hasCrits:
            e.hpCurrent = MIN(hpMax, e.hpCurrent + rep.repairPower × dt)
            IF e.hpCurrent >= e.hpMax: clearCrits(e); stopTow(涉及e的pair, REPAIRED)   // 修好即归队
    FOR box IN SupplyBox: 友军进入 supplyRadius → 当作临时CARGO结算（R-21）
```

---

## 8. 计时器与渗透身份

```
FUNCTION systemTimers(dt):
    FOR u IN units:
        u.infiltrationTimer = MAX(0, −dt)
        FOR e IN u.elements:
            e.revealTimer = MAX(0, −dt); e.sprintTimer = MAX(0, −dt)
            e.suppression = MAX(0, −suppDecay × dt)
        deployTimer 推进并按状态机迁移（§10）
FUNCTION 渗透身份清除():                                               // 【v1.1】正式定义触发点
    开火（fire/sniperResolve/meleeResolve）执行时:
        u.infiltrationTimer = 0                                        // R-04 身份消失（爆破作业已裁剪，见§13）
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
占点判定: 目标点半径内仅一方存活单位 → 归属切换（存活=elements 非空）
```

---

## 10. 状态机迁移表（weaponStates 增加 SNIPER/MELEE 路由注记；deployState 不变）

**weaponStates：**

| 当前 | 事件/条件 | 下一态 | 动作 |
|---|---|---|---|
| READY | 对空位武器 | （对空自动）AIMING | R-17，不受 stance/mode |
| READY | meleeFlag 且近距有敌 | AIMING(短) | target=最近近距敌 |
| READY | sniperFlag 且射程内有已标记敌 | AIMING | target=selectTarget |
| READY | 普通武器 且目标有效且开火许可 | AIMING | timer=aimTime×aimFactor |
| AIMING | timer≤0 且目标有效 | 开火→RELOADING | 狙击→sniperResolve；近战→meleeResolve；普通→弹丸 |
| AIMING | 目标死亡/失标记/禁射 | READY | 不消耗 |
| RELOADING | timer≤0 且 ammo>0 | READY | — |
| RELOADING | timer≤0 且 ammo=0 | EMPTY | 等补给 |
| EMPTY | 补给转入 | READY | — |
| 任意 | 元素被拖/车载非车载武器/mode=TOW·CARGO·TRANSPORT | 冻结 | timer 保持 |

**deployState：**（与 v1.0 相同，略——MOBILE→DEPLOYING→DEPLOYED→PACKING→MOBILE；移动令即回 MOBILE 作废进度）

---

## 11. BalanceConfig 新增/调整常数

新增：`SMOKE_RADIUS`、`SMOKE_TTL`、`CALIB_ACC_BONUS`（侦察校准命中档，如1.25）、`CALIB_PER_SHOT`（按发累积）、
`CALIB_MAX_REDUCTION`（校射最大收束比例）、`GARRISON_STEALTH_BONUS`（默认+3）、`BUILDING_COLLAPSE_DMG`、
`MED_WEIGHT_PER_UNIT`（医疗品单份重量，混装载重核算）、`SNIPER_BASE_PROB`（R-02 基础概率）。
沿用：`SPEED_TABLE[1-5]`、`STEALTH_FACTOR_TABLE[0-10]`、`meleeRange=50`、`suppPenalty/suppDecay`、
`critPerHP`、`MED_HP_PER_UNIT`、`R18半径=80`、`INFIL_MULT/AMBUSH_MULT/REVEAL_MULT`、
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
渗透班"引导空投"：airdropBeaconPos 由渗透班标定指令写入（§8 身份清除不适用——标定不算暴露）；
    航空系统投散时读取该标记 → 散布 × 0.5（接口约定，公式在航空侧）。
```

---

## 13. 审查问题 → 修复位置对照（验收清单）

| 审查问题 | 修复位置 |
|---|---|
| B1 武器缺射程/散布字段 | §0 武器27子字段 +§4 selectTarget(minRange) +§4 fire(散布) |
| B2 狙击死代码 | §0 sniperFlag + §4 狙击分支 + §4.6 射程门 |
| B3 近战死代码 | §4 近战分支 + §4.5 meleeResolve 接入状态机 |
| B4 烟雾闭环断裂 | §0 SMOKE=武器档案单轨 + §5 spawnSmokeZone 定义 + §4 烟弹发射（BALLISTIC 无目标弹丸）|
| B5 防空对空对地互斥 | §0 AA移出mode + §4 A/B 并行分流 |
| B6 卡车槽位层级错位 | §0 mode/cargo/supply 下沉元素级 + §7 CARGO装货 |
| B7 destroyElement 无定义 | §5 完整定义（车载/运兵/物资/拖曳/掩护连带） |
| B8 车载/运兵 pos 不随动 | §2 systemMove 随动分支 |
| B9 狙击0血僵尸班 | §4.6 走 applyDamage + §0 不变式（elements 内必存活） |
| B10 装甲0除零 | §5 resolveHit 无甲守卫 |
| g-R01 标记无消费 | §4 fire() CALIB_ACC_BONUS |
| g-R15 自卫直射孤立 | §4 INDIRECT 分支触发 |
| g-伏击视野减半 | §3 detectionRange × 0.5 |
| g-炮击任务 fireAt/门控 | §4.3 开火许可门 + fireAt 定义 + setElementMode/拖曳清任务 |
| g-拖曳无解除 | §7 stopTow + 触发点 |
| g-配额缺失 | §9 validateDeck + purchase 扣余量 |
| g-建筑进驻 | §7 garrison/collapseBuilding（【拍板默认】） |
| g-卡车载重混装 | §7 buySupplies 重量核算 |
| g-威胁值无来源 | §4 selectTarget 可计算定义 |
| g-对空结算悬空 | §12 接口契约 |
| g-校射口径 | §4.3 按发累积【拍板默认】 |
| g-渗透爆破/倍率 | 部分修复：§8 爆破动作触发身份清除；**目标类别倍率槽与爆破作业流程仍缺，需 v1.2**（见下） |

**遗留项闭环（用户拍板：爆破作业功能去除，不设 v1.2）**：
- 渗透破坏班/勃兰登堡：不再承担"炸后勤车/炸停止状态牵引炮"。保留职能 = 渗透进场（R-04）+ 偷占目标点 + 引导空投标定（§12 接口）；自身轻武装自卫照常。
- 工兵排：保留喷火武器与对工事/建筑的 vsFortMult×2 攻击加成；"爆破"不再是独立动作系统——对建筑的毁伤通过携带 vsFortMult 的武器攻击实现。
- R-04 表述同步：身份消失条件从"开火或爆破后"改为"开火后"。
- 政委光环"冲刺+1档/爆破+50%"维持此前裁剪（督战=单纯近战攻击）。
- **GDD-02 文档需同步清单（累积）**：①士气类效果（近卫意志/国民掷弹兵阈值/政委军官基础光环）标记作废或改锚；②渗透班卡面"爆破高倍率"表述删除；③R-04"开火或爆破"改"开火"；④工兵"爆破"改锚为攻击加成；⑤"建筑进驻加成"补充内容定义（当前伪代码按隐蔽+3、受击尾甲参考实现）。
