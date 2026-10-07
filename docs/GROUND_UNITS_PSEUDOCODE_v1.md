# 地面单位机制伪代码 v1.0（变量集冻结版）

> 依据：GDD-01 兵种表 + GDD-02 单位功能细则（R-01~R-23、第8节14轮逐卡拍板）+ 用户裁剪决策
> （无APS/ECM/雷达/激光/制导/回圈退款；无士气系统；无伤级制只掉血；医疗品=步兵版维修；
> 穿深/装甲=0-20相对值；装甲四槽F/S/R/T；督战=近战加成光环；近战阈值50m占位）。
> 变量集：单位静态30 + 单位运行时26 + 元素静态11 + 元素运行时12 = 79槽位；武器23子字段。

---

## 0. 冻结数据结构（79 槽位 + 23 武器子字段）

```
STRUCT UnitTemplate:                      // 单位静态 30（排/连卡级）
    templateId, category                  // 侦察/步兵/装甲/火支/防空后勤（UI+R-01判定）
    cost, domain                          // GROUND 恒定
    elementCount, elementTemplate[]       // 编制与元素模板
    opticsGround                          // 视野 m
    opticsAir, airCeiling                 // 对空探测 m / 可及高度层(无低中高)  R-17
    stealthBase                           // 隐蔽 0-10
    speedTier                             // 速度档 1-5
    movementClass                         // FOOT/WHEEL/TRACK/HORSE
    turnRate                              // 车体转向 °/s   R-09
    deployTime, packTime                  // 展开/收起 s（0=免展开）
    modeSet                               // DIRECT/INDIRECT/AA/TOW/CARGO/TRANSPORT 位掩码
    smokeMax                              // 烟罐/烟弹基数
    closeCombatBonus                      // 近战加成：骑兵1.8，冲锋枪排高档，默认1.0
    towTonnage, ownWeightTons             // 拖曳吨位 / 自重   R-19
    repairPower                           // 维修力（0=无）
    supplyRadius                          // 自动补给半径（0/80m）R-18
    cargoRoundsMax, cargoMedicalMax       // 物资模式：弹600/医疗120
    seats                                 // 运兵座位
    acousticSignature                     // 声响特征（被声测定位速率）
    sonarRadius, sonarRate                // 声测侦听半径/收束速率   R-03
    auraDef                               // {kind: MELEE|PRECISION, bonusPct, radius} | null
    flags                                 // canSprint canGarrison canAmbush canInfiltrate
                                          // noMoveVisionPenalty forestWalkSilent
                                          // requiresMark singleSquadCard

STRUCT UnitInstance:                      // 单位运行时 26
    unitId, teamId, alive
    pos, movePath[]                       // 队形基准点/航点
    mode                                  // modeSet 之一（卡车三模式互斥 D065）
    deployState, deployTimer              // 行军/展开中/已展开/收起中
    stance                                // 自由开火/禁射（AA模式忽略 R-17）
    fireMission                           // {form:POINT|LINE|CREEP, ammoMult, salvoMode,
                                          //  targetPoint, targetLine, creepSpeed, shotsLeft}
    calibTargetPos, calibProgress         // 连内共享校射  R-16
    smokeLeft, markLevel                  // 无/发现/侦察校准  R-01
    spottedMask, infiltrationTimer        // 队伍发现位掩码 / 渗透60s  R-04
    ambushActive, ambushShotBonus         // 伏击中 / 脱离伏击首击加成待触发  R-12
    supplyRoundsCur, supplyMedicalCur     // 卡车在途物资
    cargoUnits[]                          // 跨卡运载（运兵班）
    towPair                               // {towers:[unitId], towed:{unitId, elementId}} | null
    sniperCoverTargetId                   // 反狙击掩护对象
    airdropBeaconPos                      // 引导空投标记（航空系统读取）
    r02KillTally                          // 狙击累计击杀 → 灭班计数  R-02
    elements[]                            // 车/炮/班实例

STRUCT ElementTemplate:                   // 元素静态 10
    elementType                           // VEHICLE/GUN/SQUAD
    unitType                              // INFANTRY/MECH（bodyType 派生：MECH→HARD）
    hpMax                                 // MECH:车体血；INFANTRY:编制人数(1HP=1人)
    armorKE{F,S,R,T}, armorHE{F,S,R,T}    // 四面两类，0-20 相对刻度；T仅空袭读取
    fireArcDeg, turretTraverse            // 射界（无炮塔±15°）/ 炮塔回转（无炮塔0）
    suppressionVuln                       // 敞篷>1（SU-76等）
    squadQuality                          // 老兵班精度+（国民掷弹兵）
    weapons[], mountedArmament            // 武器表 / 空车可射击标记（251）

STRUCT ElementInstance:                   // 元素运行时 12
    elementId, pos, facing
    hpCurrent
    critSlots                             // {FC,SEN,RLD,MOB: NONE|MINOR|MAJOR} 仅MECH
    suppression                           // 0-100 连续值，无士气状态
    sprintTimer, revealTimer              // 疾跑 / 开火暴露残留
    mountedIn                             // 所载车辆元素ID（R-07）| null
    weaponStates[]                        // 每武器 {state, timer, targetId, ammoLeft, specialAmmoLeft}
    rotating, towedState                  // 转向中(受弹惩罚) / 被拖·牵引中

STRUCT WeaponTemplate:                    // 武器 23 子字段
    targetMask                            // GROUND/AIR_LOW/AIR_MID/AIR_HIGH 四位
    damageType                            // KE / HE / SMOKE
    penMin, penMax                        // KE 远距~贴脸（HE 相等）
    damage, blastRadius
    accuracyBase, aimTime, reloadTime, salvo
    ammoBase, ammoWeightPerShot           // 基数6发/门，D012重量体系
    projectileSpeed, trajectory           // DIRECT / BALLISTIC
    suppressionPower                      // 压制值/发（Maxim最高档）
    critMod, vsFortMult                   // RPG类>1；工兵×2 ISU-HE×1.5
    specialAmmo{count, penMod}            // PaK38钨芯3发穿+3
    ammoProfiles[]                        // R-11 自动选弹 AP/HE 共槽
    needsDeployed, selfDefenseProfile     // R-05 须展开 / R-15 自卫直射档案
    meleeFlag, revealTime                 // 骑枪马刀 / 开火声响暴露时长（联动声测）

WORLD 实体：SmokeZone{pos,radius,ttl}、IntelCircle{center,radius,teamId}（声测模糊圈，冻结精度）、
           Building{hp,garrisonSlots}、SupplyBox（空投箱，R-21拾取同补给半径）
```

---

## 1. 主循环

```
FUNCTION worldTick(dt):                              // 固定步长
    systemTimers(dt)                                 // ① 各计时器衰减（见 §8）
    FOR u IN units: systemMove(u, dt)                // ② 移动
    systemSensing(dt)                                // ③ 侦察/标记/对空发现/声测
    FOR u IN units: systemCombat(u, dt)              // ④ 交战决策（含炮兵任务）
    FOR p IN projectiles: systemProjectile(p, dt)    // ⑤ 弹丸推进与命中（无拦截层）
    systemSupply(dt)                                 // ⑥ 补给/医疗/维修
    systemAura()                                     // ⑦ 光环修饰（查询期生效，无状态）
    systemEconomy(dt)                                // ⑧ 购买/出牌/占点
```

---

## 2. 移动系统

```
FUNCTION systemMove(u, dt):
    IF u.deployState IN {DEPLOYING, PACKING}: RETURN            // 展开中禁止移动
    FOR e IN u.elements WHERE e.towedState == TOWED:            // 被拖元素跟随牵引车
        e.pos = 跟随(u.towPair.towers[0]);  CONTINUE
    v = moveSpeed(u)
    IF v == 0: RETURN
    新pos = pathStep(u, v*dt)
    FOR e IN u.elements (除被拖/车载): e.pos = 队形偏移(新pos)
    u.pos = 新pos
    主元素 e.facing = 朝向路径方向
    IF u.ambushActive: exitAmbush(u)                            // 移动自动退出伏击 R-12

FUNCTION moveSpeed(u):                                          // 全单位同一函数
    base = SPEED_TABLE[u.speedTier]                             // 档位→m/s
    m = TERRAIN[当前地块][u.movementClass].speedMod              // 步兵/轮/履/马 查同一张表
    IF onRoad(u) AND u.movementClass != FOOT: m = MAX(m, ROAD_BONUS)
    e = 主元素(u)
    IF e.critSlots.MOB == MAJOR: RETURN 0                       // 趴窝，等拖曳 R-19
    IF e.critSlots.MOB == MINOR: m *= 0.5
    IF u.towPair != null: base = SPEED_TABLE[1]                 // 拖曳双方最低档 R-19
    IF e.sprintTimer > 0: m *= SPRINT_FACTOR                    // 步兵疾跑
    IF e.towedState == TOWED: base = SPEED_TABLE[1]
    RETURN base * m

FUNCTION 转向处理(e, 目标朝向):                                  // R-09 无炮塔射界外→转车体
    IF |angleDiff(e.facing, 目标朝向)| > e_template.fireArcDeg:
        e.rotating = true; e.facing += sign × turnRate × dt     // 转向慢=暴露窗口
    ELSE: e.rotating = false
```

---

## 3. 侦察系统（一条公式 + 三个附加体系）

```
FUNCTION systemSensing():
    // A. 地面互侦
    FOR (obs, tgt) IN 敌对配对:
        IF dist(obs,tgt) <= detectionRange(obs,tgt):
            markSpotted(tgt, obs)
        ELIF dist > keepRange(obs,tgt): unmarkSpotted(tgt, obs)
    // B. 对空发现 R-17/R-23
    FOR aircraft a, FOR ground g:
        IF a.altTier <= g.airCeiling AND dist <= g.opticsAir: spotted(a, by=g)   // 防空体系
        IF a.altTier == LOW AND dist <= g.opticsGround:      spotted(a, by=g)    // 普通单位可见低空
    // C. 标记等级 R-01
    FOR tgt: tgt.markLevel = MAX(发现等级(observers))
             // category==侦察 的观察者 → CALIBRATED（校准）；其余 → SPOTTED
    // D. 声测 R-03（读 §4 开火时产生的 soundEvent）
    FOR s IN 声测单位 WHERE s.deployState == DEPLOYED:
        FOR ev IN enemySoundEvents WHERE dist(s,ev) <= s.sonarRadius:
            ev.accum += s.sonarRate × ev.sig × dt
            IF ev.accum >= LOCATE_THRESHOLD:
                upsertIntelCircle(team=s.teamId, center=ev.pos,
                                  radius = lerp(MAX_R, MIN_R, ev.accum))  // 圈随时长收窄

FUNCTION detectionRange(obs, tgt):
    r = obs.opticsGround
    IF moving(obs) AND NOT obs.flags.noMoveVisionPenalty: r *= 0.5   // 侦察车轮式豁免（第1轮）
    r *= STEALTH_FACTOR_TABLE[effectiveStealth(tgt)]                   // 11档查表
    r -= ATTEN × forestMetersOnLOS(obs,tgt)                           // 穿林衰减
    r -= ATTEN × smokeMetersOnLOS(obs,tgt)                            // 穿烟衰减（烟雾=真资源 R-06）
    RETURN r

FUNCTION effectiveStealth(u):
    s = u.stealthBase + TERRAIN[地块].stealthAdd                     // 如林地+2（猎兵林内+2按特化）
    m = 1.0
    IF moving(u):
        m *= 0.5
        IF u.flags.forestWalkSilent AND inForest(u): m *= 2          // 静默行军豁免（第5轮）
    IF u.infiltrationTimer > 0 AND NOT anyRevealing(u): m *= INFIL_MULT   // 渗透60s R-04
    IF u.ambushActive: m *= AMBUSH_MULT                              // 伏击隐蔽大增 R-12
    IF anyElement(u).revealTimer > 0: m *= REVEAL_MULT               // 开火暴露
    RETURN clamp(s*m, 0, 10)

FUNCTION keepRange(obs, tgt):                                        // 已发现目标更难甩
    RETURN obs.opticsGround × STEALTH_FACTOR_TABLE[tgt.stealthBase]
```

---

## 4. 交战决策（武器状态机 + 火控规则）

```
FUNCTION systemCombat(u, dt):
    IF u.mode == AA: aaAutoEngage(u); RETURN                        // R-17 全自动，忽略 stance
    FOR e IN u.elements:
        FOR w IN e.weaponStates WHERE state == READY AND ammoLeft > 0:
            IF NOT 开火许可(u, e, w): CONTINUE                      // stance / 需展开 / 车载 / 被拖
            tgt = selectTarget(u, e, w)
            IF tgt == null: CONTINUE
            IF 需转车体(e, tgt): 转向处理(e, 朝向tgt); CONTINUE      // R-09 射界外先转体
            w.state = AIMING; w.timer = w.aimTime × aimFactor(e)
            w.targetId = tgt.elementId
        FOR w WHERE state == AIMING AND timer <= 0:
            tgt = lookup(w.targetId)
            IF tgt == null OR NOT stillValid(u,w,tgt): w.state = READY; CONTINUE
            fire(u, e, w, tgt)
    IF u.mode == INDIRECT AND u.fireMission != null: processFireMission(u, dt)

FUNCTION 开火许可(u, e, w):
    IF u.stance == HOLD_FIRE: RETURN false
    IF w.needsDeployed AND u.deployState != DEPLOYED: RETURN false  // R-05
    IF e.mountedIn != null AND NOT w.允许车载射击: RETURN false      // 车载仅 mountedArmament
    IF e.towedState != NONE: RETURN false                           // 拖曳双方禁射 R-19
    IF u.towPair != null AND e ∈ 被拖炮: RETURN false
    RETURN true

FUNCTION selectTarget(u, e, w):
    cands = { x ∈ 敌方元素 ∧ teamSpotted(x)
              ∧ (x.domainMask & w.targetMask) != 0                  // 域+高度层匹配
              ∧ dist(e,x) <= w.maxRange × auraRangeBonus(u)         // 军官光环+10%
              ∧ markOK(u, x) }                                      // 犀牛 requiresMark→x.markLevel≥发现
    score(x) = 预估伤害(w,x) + 威胁值(x) − dist惩罚
    RETURN argmax(score)                                            // 空档/空/地自动分流

FUNCTION fire(u, e, w, tgt):
    profile = 选弹(w, tgt)                                          // R-11 自动选弹，见下
    w.ammoLeft -= 1; w.state = RELOADING
    w.timer = w.reloadTime × reloadFactor(e)
    e.revealTimer = MAX(e.revealTimer, w.revealTime)                // 开火暴露
    spawnSoundEvent(pos=e.pos, sig=u.acousticSignature × w.salvo)   // 喂声测 R-03（火箭炮sig最高）
    acc = w.accuracyBase × accuracyCurve(dist/maxRange) × aimFactor(e)
         × (u.ambushShotBonus? +AMBUSH_ACC : 1)                     // R-12 首击加成，用后清标记
         × auraAccBonus(u) × e.squadQuality
    FOR i IN 1..w.salvo:
        hit = random() < acc
        aimPoint = hit ? tgt.pos : scatter(tgt.pos, w.dispersion × (1 − calibProgress/200))
        SPAWN Projectile(shooter=e, weapon=w, profile, aimPoint, hitTarget = hit ? tgt : null,
                         topAttack = w.来自空袭系统? true : false)

FUNCTION 选弹(w, tgt):                                              // R-11 + 钨芯
    IF w.ammoProfiles 为空: RETURN w 默认档案
    IF unitTypeOf(tgt) == MECH:
        IF standardAP(w).penMax < tgt.armorKE.F                     // 常规弹打不动正面
           AND w.specialAmmoLeft > 0:                               // PaK38 钨芯自动救场
            w.specialAmmoLeft -= 1; RETURN {pen +penMod}
        RETURN AP 档案
    ELSE: RETURN HE 档案                                            // 软目标高爆

FUNCTION aaAutoEngage(u):                                           // R-17 纯自动
    FOR e IN u.elements, FOR w AA武器:
        tgt = 最近已发现敌机 in range AND altTier <= u.airCeiling
        IF tgt: 同 fire() 流程

FUNCTION processFireMission(u, dt):                                 // R-13 炮击任务
    fm = u.fireMission
    参与炮 = (fm.salvoMode == HALF) ? elements前一半 : elements     // R-14 半轮
    FOR 每门就绪炮: fireAt(pointIn(fm.form))                        // POINT=中心；LINE=沿线分布；
                                                                    // CREEP=线段按 creepSpeed 逐段推进
    fm.shotsLeft -= 发射数; IF fm.shotsLeft <= 0: u.fireMission = null
    // 校射 R-16/D013：
    IF fm.targetPoint 在友军视野内: u.calibProgress += CALIB_RATE × dt   // 连内共享
    u.calibProgress reset WHEN fm.targetPoint 变更
    // 盲射声测圈 R-03：targetPoint 可为 IntelCircle → 散布 += circle.radius

FUNCTION 自卫直射(e, 敌):                                            // R-15
    IF 曲射武器 AND dist <= selfDefense.range:
        用 selfDefenseProfile{短射程, accuracy −大额惩罚} 走 fire()

// —— 近战（骑兵/冲锋枪排）——
FUNCTION meleeResolve(attacker_e, defender_e):
    IF dist <= BALANCE.meleeRange (50m):
        dmg = attacker武近战damage × attacker.unit.closeCombatBonus   // 骑兵×1.8
              × (1 + 政委MELEE光环.bonusPct)                          // 督战=单纯近战攻击加成
        applyDamage(defender_e, dmg, 无穿甲=HE曲线)

// —— 狙击 R-02 ——
FUNCTION sniperResolve(sniper_e, tgtUnit):
    e = tgtUnit.任一存活班
    covered = EXISTS friendly狙击 s WHERE s.unit.sniperCoverTargetId == tgtUnit.unitId
    killProb = covered ? BASE_PROB × 0.5 : BASE_PROB                  // 反狙击掩护减半（第1轮）
    IF tgtUnit.flags.singleSquadCard:                                 // 指挥班组/声测班
        IF random() < killProb: e.hpCurrent = 0                       // 灭排
    ELSE:
        kills = (random()<killProb) + (random()<killProb)             // 1~2人
        e.hpCurrent -= kills; tgtUnit.r02KillTally += kills
        IF tgtUnit.r02KillTally >= 3:                                 // ≥3人=损失一个班
            血量最低存活班.hpCurrent = 0; tgtUnit.r02KillTally -= 3
```

---

## 5. 弹丸与命中结算（全游戏唯一伤害入口）

```
FUNCTION systemProjectile(p, dt):
    p.pos += p.vel × dt
    IF p.weapon.trajectory == BALLISTIC AND p.pos ≈ p.aimPoint: resolveBlast(p)
    ELIF p.hitTarget != null AND p.pos ≈ p.hitTarget.pos: resolveHit(p)
    // WW2 无制导弹药：飞行段无任何拦截判定，命中即结算

FUNCTION resolveHit(p):                                            // ←所有单位所有弹种同一函数
    e = p.hitTarget
    facing = facingOf(e, p.approachDir)
    armor = armorOf(e, facing, p.profile.damageType)
    pen = penetrationAt(p.weapon, distFlew(p))                     // KE 距离插值；HE/SMOKE 恒定
    r = pen / armor
    mult = damageMultiplier(unitTypeOf(e), p.profile.damageType, r)
    dmg = p.profile.damage × mult × squadHpFactor(p.shooter)       // 步兵班残员火力线性衰减
    IF 命中建筑/工事: dmg ×= p.weapon.vsFortMult                    // 工兵×2 ISU×1.5 OT-34×2
    applyDamage(e, dmg, p.weapon)
    IF mult > 0 AND unitTypeOf(e) == MECH: rollCrits(e, dmg, p.weapon.critMod)
    FOR x IN 单位近旁: injectSuppression(x, p.weapon.suppressionPower × falloff)

FUNCTION facingOf(e, approach):
    IF p.topAttack: RETURN TOP                                     // 空袭扫射攻顶 R-22（读T槽）
    IF e.rotating: RETURN SIDE                                     // R-09 转向中侧面暴露
    a = angleDiff(e.facing, approach)
    RETURN FRONT if a<=45° ; SIDE if a<=135° ; REAR

FUNCTION damageMultiplier(unitType, dmgType, r):                   // 0-20 刻度下比值无量纲
    IF dmgType == SMOKE: spawnSmokeZone(); RETURN 0
    IF unitType == INFANTRY: RETURN r*r / (1 + r*r)                // 步兵一律爆破曲线
    IF dmgType == KE:                                              // 动能阶梯：跳弹制
        IF r >= 1.0: RETURN 1.0
        IF r >= 0.5: RETURN 1.8*r - 0.8                            // 锚点：1→100%，0.5→10%
        RETURN 0.0                                                 // 反坦克枪打重甲=跳弹+轻微压制
    RETURN r*r / (1 + r*r)                                         // HE 曲线（1→50%，2→80%，0.5→20%）

FUNCTION applyDamage(e, dmg, weapon):
    e.hpCurrent -= dmg
    IF e.hpCurrent <= 0: destroyElement(e)                         // 班灭=除名不可医疗；车毁=除名
    // R-07 车载被毁连带：FOR s IN 车载班: s.hpCurrent = ceil(s.hpCurrent × 0.4)

FUNCTION resolveBlast(p):                                          // 曲射/近失/烟弹落点
    IF p.weapon.damageType == SMOKE: spawnSmokeZone(p.aimPoint); RETURN
    FOR e IN elementsWithin(p.aimPoint, p.blastRadius):
        applyDamage(e, p.damage × falloff(dist), p.weapon)
        rollCrits(e, dmg, p.weapon.critMod)
        injectSuppression(e, p.weapon.suppressionPower)
    FOR b IN buildingsWithin: b.hp -= dmg × vsFortMult

FUNCTION rollCrits(e, dmg, critMod):                               // 仅 MECH；步兵无暴击
    IF random() < MIN(1, dmg × BALANCE.critPerHP × critMod):
        slot = pick([FC, SEN, RLD, MOB])
        e.critSlots[slot] = 升一级(NONE→MINOR→MAJOR)               // 只升不降，修满才清 D016
```

---

## 6. 压制系统（连续 debuff，无士气状态）

```
FUNCTION injectSuppression(e, amount):
    e.suppression = MIN(100, e.suppression + amount × e.suppressionVuln)   // 敞篷放大（SU-76）

FUNCTION suppressionFactor(e):                                     // 挂进 aimFactor/reloadFactor
    RETURN 1 − BALANCE.suppPenalty × e.suppression / 100

修饰器族（查询期计算，不存变量）：
    aimFactor(e)     = 1 × (critFC==MINOR?0.75 : MAJOR?0.5 : 1) × suppressionFactor(e)
    reloadFactor(e)  = 1 × (critRLD==MINOR?1.3 : MAJOR?1.6 : 1) × (2−suppressionFactor(e))
    opticsFactor(e)  = 1 × (critSEN==MINOR?0.6 : MAJOR?0.3 : 1)
    squadHpFactor(e) = e.hpCurrent / e.hpMax                       // 班火力=血量比例
```

---

## 7. 展开制状态机 + 运输/拖曳 + 后勤

```
// —— deployState 状态机（机枪/迫击炮/牵引炮/声测）——
MOBILE  --下令展开且静止-->  DEPLOYING(timer=deployTime)  --满--> DEPLOYED
DEPLOYED --下令移动/收起--> PACKING(timer=packTime)      --满--> MOBILE
DEPLOYING/PACKING 期间收到移动令 → 直接回 MOBILE（进度作废）
DEPLOYED 效果：needsDeployed 武器全额射程/压制；sonarRadius 生效；射击散布享受校射

// —— R-07 车载（同卡元素间）——
下令下车: FOR 车载班 e: e.mountedIn = null; e.pos = 载具旁落位       // 空车原地，武器照打（mountedArmament）
下令上车: 静止于载具旁 20s → e.mountedIn = 载具元素ID

// —— D065 卡车三模式（互斥）——
setMode(truck, m): 校验 m ∈ modeSet; 卸空当前模式载荷; truck.mode = m
    TOW: 可建立 towPair（拖一门炮）
    CARGO: supplyRoundsCur/supplyMedicalCur 按重量混装（≤600发/≤120份）
    TRANSPORT: cargoUnits 装载 1 个步兵班卡（上下车同 R-07 规则）

// —— R-19 拖曳 ——
startTow(牵引组, 目标):
    need = CEIL(目标.ownWeightTons / 牵引组.towTonnance)            // 中坦30/30=1；重坦45/30=2并拖；45/45=1
    IF 牵引组可用数 >= need: 建 towPair{towers, towed}; 双方 towedState 置位
拖曳中：双方速度=1档、禁射、被拖者维持 MOB 暴击状态
脱离火线后：维修车 repairPower 修 HP 与 critSlots（修满清状态伤 D016）

// —— 后勤（R-18 自动 + 医疗=步兵回血）——
FUNCTION systemSupply(dt):
    FOR t IN 卡车 WHERE mode==CARGO:
        FOR u IN unitsWithin(t.pos, t.supplyRadius):               // 80m 自动，无指令
            FOR e IN u.elements:
                FOR ws IN e.weaponStates:                          // 弹药按发补
                    take = MIN(ws.ammoBase−ws.ammoLeft, t.supplyRoundsCur, rate*dt)
                    ws.ammoLeft += take; t.supplyRoundsCur −= take
                IF unitTypeOf(e)==INFANTRY AND 0 < e.hpCurrent < e.hpMax:
                    med = MIN(ceil((e.hpMax−e.hpCurrent)/MED_HP_PER_UNIT), t.supplyMedicalCur)
                    e.hpCurrent += med×MED_HP_PER_UNIT; t.supplyMedicalCur -= med
            IF u.smokeLeft < u.smokeMax AND t.supplyRoundsCur>0: 补烟（计入发数）
    FOR rep IN 维修车:
        FOR e IN 贴靠的 HARD 元素 WHERE hp<max 或 hasCrits:
            e.hpCurrent = MIN(hpMax, +rep.repairPower×dt)
            IF 满血: clear critSlots                                 // 修满清状态伤
    FOR box IN SupplyBox: 友军进入 supplyRadius → 当作临时 CARGO 卡车结算（R-21）
```

---

## 8. 计时器、光环、特则

```
FUNCTION systemTimers(dt):
    FOR u IN units:
        u.infiltrationTimer = MAX(0, −dt)                           // 渗透窗口
        FOR e IN u.elements:
            e.revealTimer = MAX(0, −dt); e.sprintTimer = MAX(0, −dt)
            e.suppression = MAX(0, −BALANCE.suppDecay × dt)         // 压制自然衰减
        deployTimer 推进并按状态机迁移
    开火即清: 开火/爆破时 infiltrationTimer = 0（身份消失 R-04）

FUNCTION systemAura():                                              // 光环无状态，查询期判定
    政委 auraDef{MELEE}:   友军元素 within radius → 近战伤害 +bonusPct
    军官 auraDef{PRECISION}: 友军元素 within radius → 射程+10%、精度+10%

FUNCTION toggleAmbush(u):                                           // R-12
    IF u.flags.canAmbush AND 静止: u.ambushActive = true            // 视野减半+隐蔽大增（§3已挂）
    退出（手动）: ambushActive=false; ambushShotBonus=true           // 下一发精度加成后清
    移动: 自动退出且不给首击加成
```

---

## 9. 经济与部署（一命制）

```
FUNCTION purchase(player, cardTemplate):
    player.points −= cost; player.spawnQueue.push(cardTemplate)     // 逐个间隔出牌
spawn: 普通卡→己方部署区；canInfiltrate 卡→任意地图边缘（敌部署区边缘除外）R-04
destroyElement → 单位全灭: alive=false，直接移出战场；无回圈、无退款（一命制 D017）
占点判定: 目标点半径内仅一方存活单位 → 该点归属切换
```

---

## 10. 两张状态机迁移表（收尾）

**weaponStates：**

| 当前 | 事件/条件 | 下一态 | 动作 |
|---|---|---|---|
| READY | 目标有效 + 开火许可 | AIMING | timer = aimTime×aimFactor |
| AIMING | timer≤0 且目标仍有效 | （开火）→ RELOADING | 消弹、暴露、声事件、生成弹丸 |
| AIMING | 目标死亡/丢失标记/stance变禁射 | READY | 不消耗弹药 |
| RELOADING | timer≤0 且 ammo>0 | READY | — |
| RELOADING | timer≤0 且 ammo=0 | EMPTY | 等补给 |
| EMPTY | 补给转入弹药 | READY | ammoLeft>0 即可 |
| 任意 | 元素被拖/拖曳中/车载(非车载武器) | 冻结 | timer 保持，恢复后续跑 |

**deployState：**

| 当前 | 事件 | 下一态 | 动作 |
|---|---|---|---|
| MOBILE | 下令展开且静止 | DEPLOYING | timer=deployTime（迫10s/HMG15s/牵引炮30s） |
| DEPLOYING | timer≤0 | DEPLOYED | needsDeployed 武器转全额；声测生效 |
| DEPLOYING | 收到移动令 | MOBILE | 进度作废 |
| DEPLOYED | 下令移动 | PACKING | timer=packTime |
| PACKING | timer≤0 | MOBILE | — |
| DEPLOYED | （静止保持） | DEPLOYED | 享受校射/全额压制输出 |

---

## 11. BalanceConfig 待定常数清单

`SPEED_TABLE[1-5]`、`STEALTH_FACTOR_TABLE[0-10]`（11档）、`meleeRange=50`、`suppPenalty/suppDecay`、
`critPerHP`、`MED_HP_PER_UNIT`、`R18半径=80`、`INFIL_MULT/AMBUSH_MULT/REVEAL_MULT`、`AMBUSH首击精度`、
`声测LOCATE阈值/收束速率/MAX_R·MIN_R`、`CALIB_RATE与散布插值端点`、`拖曳速度档=1`、
`下车20s/车载被毁扣60%`、KE线性锚点（1.8/−0.8）与HE曲线为固定公式不需配置。
