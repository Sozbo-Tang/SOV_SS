"""§F5 移动函数族（伪代码 v1.7 §F5——定稿终检 GAP-01/02/03/14/18/28/30 修复版）。

- GAP-01：到达航点按实际距离扣预算，同 tick 可推进多航点（原固定扣 1000 的简化已撤销）
- GAP-03：队形偏移谓词对齐 §F5 :988-993（排除车载/被拖，含首元素；默认零偏移=基准点，
  队形表经 formation_offset_fn 注入）
- GAP-14：随动三分支（整班车载早退 / 拖曳随动 / sync_followers）
- GAP-18：疾跑读单位级 unit.sprint_until（§D.4#16 归口）
- GAP-30：路径耗尽保持末段航向（本 tick 实际位移向量求 octant）
- rotate_step（§F5 :1051-1058 R-09 转车体——射击侧消费：ground_direct/cmd_attack
  射界门外先转车体；AMB-5 换算 turn_rate_deg(deg/s)→MAX(1,·//10)/tick；M3/B04
  rotating 按当前角差重算不锁存；随 §F4 对地分流块落地 2026-10-02）

MOVEMENT_PSEUDOCODE_v1.2 命令层追加（2026-10-04 命令层块；§9 :571 增量④——既有
函数体零改动，以下全部为本块追加）：
- issue_move（§2.2 命令入口；handoff 内部移交通道——BLK-1 修复，分支次序冻结
  AMB-11：handoff 判定先于 queue 判定）；_resolve_move_path=命令航点逐段经
  world.find_path 展开（⑦块登记的"find_path 消费端=命令层 move_path 写入"接线；
  terrain=None stub 直线直填 ⇒ 与 list(cmd.path) 逐位一致）
- attack_move_engage_hold（§2.5 攻击前进接敌保持谓词——GAP-04）
- make_formation_fn（§2.8 队形三表闭包——GAP-15；DIR8/PERP8/scale 复用 air.py
  冻结族，round_div 半舍入；NONE=None 现状零行为变化——MV-B-19）
- system_move_dispatch（§2.4 dispatch 包装器——system_move 唯一调用方：ATTACK
  保持门/MARCH 道路门/瓦片注入/队形接线/到达模式复位；world_tick ② 移动位调用点
  已换本函数〔原文记 :1550 系当时快照——行号随上游增行漂移，按函数名 world_tick
  ② 移动位指称，2026-10-06 速度链块勘正〕）
- pivot_step（PB-51 原地转向推进，2026-10-04 拍板纳入——断箭 N17 neutral steering/
  映射 §五.9；推翻 MOVEMENT v1.2 §2.13 reject 的**静止分支**：静止车体改朝向耗时=
  |角差|÷cfg.pivot_rate_deg_per_tick[类] 整数推导（履带快于轮式，数值占位待定标），
  移动中 facing 仍即时 8 扇区——两口径成文分立。system_move_dispatch 头部唯一消费
  （独占移动拍，互斥不变式 pivot_to>=0 ⇒ move_path 恒空）；期间禁射=fire_permitted
  ⑧ 门（tick.py）、SIDE 暴露=GAP-25 rotating 维持——R-09「转向慢=暴露窗口」同语义）
- PB-52 单位级地形数值（2026-10-04 拍板纳入——断箭 N10/映射 §五.6；推翻 MV-B-01
  defer 的类级系数口径，改「单位级覆盖、类级缺省回退」；水域仍随 MV-B-02 延期）：
  move_speed_cm_tick 三处消费——野=cfg.terrain_speed_bp(cls, tile_bp, unit_bp)
  三级回退（瓦片注入>单位级>类级，GAP-19 瓦片优先语义保持）、路=max(v, 单位级
  road_bonus_override_cm→cfg.road_bonus_cm_tick 回退)（契约⑦ max 形态不动、下限常数
  单位级可覆盖）、倒=reverse_speed_bp(cfg, template) 求值函数（issue_move 门4 与未来
  §2.3 增量② REVERSE 速度乘区两消费点同读——单一求值点防漂移）。

PB-56 批③ Formation 族块追加（2026-10-06；§2.9+§2.3 增量①——既有函数体零改动
除下述一处）：
- move_speed_cm_tick 增量①（§2.3 :197）：tier 求值后、疾跑升档前插
  `IF unit.group_speed_cap>0: tier=MIN(tier, unit.group_speed_cap)`——编组钳制在
  档位层（MV-B-15）；速度链块余量（增量② REVERSE 乘区/增量③ 重伤乘区/MOB 拆除/
  §2.11 超射程进位）不随本块，未落地不冒装。
- issue_group_move（§2.9 组下令入口）落 **tick.py** §2.2 命令层处理体段
  （MoveCmd/issue_move 同模块=零新导入边；评审退回修复 2026-10-06——原落本模块
  经函数体延迟反向导入 tick 构造 MoveCmd 命令对象，属本模块历史基线之外的新
  导入边（tick 本体 import movement 的反向边），已移除；本模块导入面回基线）

速度链块追加（2026-10-06；MOVEMENT v1.2 §2.3 求值链 v2+§2.4 增量④+§2.11——
速度链余量就此收口，唯一实现规格=MOVEMENT_PSEUDOCODE_v1.2.md〔2026-10-07 勘误档收口轮批注：现行版=v1.3（docs/MOVEMENT_PSEUDOCODE_v1.3.md，行为规格零变更）〕）：
- move_speed_cm_tick：**MOB 拆除**（GAP-14/契约⑩——CritSlot.MOB MAJOR 早退
  「趴窝等拖曳」与 MINOR 乘区一并删除：重伤≠瘫痪，HP≤25% 仅减速不减停，
  MOB MAJOR=0 的"等拖曳"语义由 D068 单阈值规则取代）+**增量② REVERSE 倒车
  乘区**（v×reverse_speed_bp(cfg, template)//10000——读 PB-52 求值函数：
  单位级覆盖>类级缺省，与 issue_move 门4 同一求值点）+**增量③ 重伤乘区**
  （ANY(e.hp×10000 ≤ hp_max×crippled_threshold_bp) → ×crippled_speed_mult_bp
  ——原位替换 MOB MINOR 乘区；边界含等号=恰 25% 触发）。乘区串接次序冻结
  （§2.3 v2：整数逐级舍入位级确定）：编组钳制→疾跑升档→拖曳锁档→地形 bp→
  **倒车→重伤**→PINNED（PB-49 后加乘区，居原位=道路 max 前）→道路取 max。
- system_move **增量④**（§2.4）：facing 三分支求值前增 REVERSE 短路行——
  `lead_facing = elements[0].facing`（保持现值不写：倒车期间车头朝向不随位移
  翻转；后继队形循环写同值=无操作；零新槽）。
- **auto_approach_waypoint**（§2.11 超射程自动进位，GAP-13）：d≤max_range 返
  None；否则沿 DIR8 目标方位退 stand=MAX(max_range−auto_approach_standoff_cm,
  max_range//2)（AMB-4 半射程下界）。消费点=tick.cmd_fire_mission（外部通道
  issue_move 安装——§2.11 :384-385 外部直令场景四件一体）；nearest_on_segment
  =LINE/CREEP 判距基准的定标延伸（规格仅定义点目标——占位可推翻）。
- 连锁：combat.roll_crit 掷骰域 below(4)→below(3)（MOB 不再产出——D071 连锁
  的 MOB 范围；FC/SEN/RLD 全拆待逐槽拍板不冒充）〔**2026-10-07 D071 全拆批注**：
  逐槽拍板已落——roll_crit/upgrade_crit 整删、FC/SEN/RLD 随 MOB 一并拆除=暴击
  掷骰整体退役，见 combat.py 拆除留痕〕；tables crit_mob_minor_mult_bp
  删除+crippled_threshold_bp/crippled_speed_mult_bp/auto_approach_standoff_cm 出表。
"""
from __future__ import annotations

from .air import DIR8, PERP8, scale
from .geom import angle_diff, dist_cm, octant_deg, round_div, step_toward
from .tables import BalanceConfig
from .types import (CritLevel, CritSlot, DeployState, FormationShape,
                    MoraleState, MovementClass, Mode, MoveCmd, MoveMode,
                    ReverseCmd, TargetDomain, TowState)


def pinned(unit) -> bool:
    """PB-49 判据缝接线（2026-10-04 士气块激活）：unit.morale==PINNED——GDD-05 士气槽
    已落地（types.MoraleState，tick.system_morale 每拍按存活元素压制聚合 max 对三档
    阈值确定性迁移）。PINNED 可动但减速（move_speed_cm_tick ×pinned_move_mult_bp
    ——PB-49 拍板语义，取代 D014 旧文「钉住=无法移动」）；ROUTED 不走本缝（溃逃=
    全速强制移动，失控语义走 issue_move 门0 门族，非减速可动）。"""
    return unit.morale is MoraleState.PINNED


def move_speed_cm_tick(cfg: BalanceConfig, unit, now: int, *,
                       on_road: bool = False, terrain_bp: int | None = None) -> int:
    if not unit.elements:
        return 0
    # ── 〔2026-10-13 终审恢复〕MOB 暴击乘区回贴（basics:229-230 Mobility「moves
    #    slower and can even be totally stuck」——2026-10-06 速度链块拆除行
    #    （GAP-14/契约⑩「重伤≠瘫痪」）被终审按手册推翻：MAJOR=趴窝 0 速（等拖曳
    #    语义复活）、MINOR=×crit_mob_minor_mult_bp；D068 HP≤25% 重伤减速单阈值
    #    （增量③ crippled_*）保留并存——两乘区叠乘（重伤+MOB 轻伤可同车并存）。
    #    消费位在 v 求值后（§2.3 v2 冻结序：地形→倒车→重伤→**MOB**→PINNED）──
    mob = max((e.crit.get(CritSlot.MOB, CritLevel.NONE) for e in unit.elements),
              default=CritLevel.NONE)
    if mob is CritLevel.MAJOR:
        return 0                       # 趴窝：0 速（拖曳承载锁 1 档+随动不动）
    tier = unit.template.speed_tier
    if unit.group_speed_cap > 0:
        tier = min(tier, unit.group_speed_cap)   # §2.3 增量①（GAP-16/MV-B-15）：编组
        #                                          钳制在档位层（tier MIN，不钳最终 v——
        #                                          类级地形 bp 残余速差=已知近似）；位
        #                                          序=钳制后疾跑升档（个体冲刺允许破格，
        #                                          契约⑧升档式不动）。2026-10-06 PB-56
        #                                          批③ Formation 族块随 issue_group_move
        #                                          接线
    if now < unit.sprint_until:
        tier = min(5, tier + 1)  # 疾跑 = 升 1 档（方案14；GAP-18：单位级时间戳）
    base = cfg.speed_cm_tick(tier)
    if any(x.towed is TowState.TOWED or x.towed is TowState.TOWING
           for x in unit.elements):
        base = cfg.speed_cm_tick(cfg.tow_speed_tier)  # 拖曳双方最低档（v1.5 双态）
    m_bp = cfg.terrain_speed_bp(unit.template.movement_class, terrain_bp,
                                unit.template.terrain_speed_override_bp)
    # PB-52（2026-10-04）：三级回退 瓦片注入>单位级覆盖>类级缺省（tables.terrain_speed_bp
    # 单点裁决——GAP-19 瓦片优先语义保持，单位级仅顶替 stub 缺省位）；
    # 原 MINOR 乘区位（m_bp 上乘区）由增量③重伤乘区**原位替换**至 v 求值后（§2.3 v2
    # 冻结序：地形→倒车→重伤——整数逐级舍入位级确定，2026-10-06 速度链块）
    v = base * m_bp // 10000
    if unit.move_mode is MoveMode.REVERSE:
        v = v * reverse_speed_bp(cfg, unit.template) // 10000
        # §2.3 增量②（GAP-03/MV-B-13；2026-10-06 速度链块）：PB-52 批注——读
        # reverse_speed_bp 求值函数（单位级覆盖>类级缺省），与 issue_move 门4
        # 倒车资格同一求值点（单一求值点防双轨漂移）；叠加边界见 §2.3 边界①
        # （倒车×拖曳：锁 1 档后再乘倒车 bp）；增量⑨ 随动偏移基向已随批落地
        # （2026-10-07 PB-60——拖曳随动段按 elements[0].facing 反向取向，本速度式不含）
    if any(e.hp_current * 10000 <= e.template.hp_max * cfg.crippled_threshold_bp
           for e in unit.elements):
        v = v * cfg.crippled_speed_mult_bp // 10000
    if mob is CritLevel.MINOR:
        v = v * cfg.crit_mob_minor_mult_bp // 10000   # MOB 轻伤减速（终审恢复）
        # §2.3 增量③（GAP-14 替换：HP≤25% 单阈值，MV-B-14；2026-10-06 速度链块）：
        # 原位替换 movement.py:33-34 的 MOB MINOR 乘区（该乘区随拆除行删除）；
        # 边界含等号（hp×10000 ≤ hp_max×2500——16HP 车 4HP 恰触发）；判 ANY
        # 元素（排级同速抽象，与拖曳 ANY 双态判同构——MV-B-14 可推翻）
    if pinned(unit):
        v = v * cfg.pinned_move_mult_bp // 10000   # 2026-10-04 拍板：断箭式——PINNED
        #                                           可动但减速（判据缝 2026-10-04 士气块
        #                                           起读 unit.morale==PINNED 真槽）；
        #                                           居 v2 冻结序重伤之后、道路 max 之前
        #                                           （§2.3 v2 未列 PINNED——后加乘区
        #                                           保持历史原位，2026-10-06 留痕）
    if on_road and unit.template.movement_class is not MovementClass.FOOT:
        road_floor = (unit.template.road_bonus_override_cm
                      if unit.template.road_bonus_override_cm > 0
                      else cfg.road_bonus_cm_tick)  # PB-52：单位级覆盖→类级缺省
        v = max(v, road_floor)  # v1.4：道路取 max 作用于最终速度（契约⑦——形态不动，
                                # 仅下限常数可单位级覆盖，PB-52 2026-10-04 批注）；
                                # 倒车令期间 dispatch 恒传 on_road=False（§2.3 边界②
                                # ——道路档 MARCH 独占，无"倒车上路取 max"分支）
    return v


def reverse_speed_bp(cfg: BalanceConfig, template) -> int:
    """PB-52 单位级倒车 bp 求值（2026-10-04 拍板纳入——断箭 N12/MV-B-13 单位级细化）：
    单位级覆盖>0 → 覆盖值；否则类级缺省 cfg.reverse_speed_bp[类]。
    消费点两处同读本函数（单一求值点防双轨漂移）：issue_move 门4 倒车资格
    （有效 bp==0 → 拒令，AMB-9）与 §2.3 增量② REVERSE 速度乘区（速度链块落地后接线，
    未落地不冒装）。FOOT/HORSE 类级恒 0=不可倒——单位级覆盖>0 即数据侧显式开口
    （1944 语境差异化史实承载位，现役数据未用）。"""
    if template.reverse_speed_override_bp > 0:
        return template.reverse_speed_override_bp
    return cfg.reverse_speed_bp[template.movement_class]


def sync_followers(unit) -> None:
    """§F5 :1009-1012：车载班随载具、运兵舱内班随车（条件槽 None 短路——GAP-14）。"""
    for e in unit.elements:
        if e.mounted_in is not None:
            e.pos = e.mounted_in.pos
        if e.mode is Mode.TRANSPORT and e.cargo_units is not None:
            for squad in e.cargo_units:
                squad.pos = e.pos


def rotate_step(e, target_deg: int) -> None:
    """§F5 :1051-1058 R-09 转车体（转向慢=暴露窗口）——射击侧消费（ground_direct/
    cmd_attack 射界门外先转车体）。方案6：仅 fire_arc_deg<360 模板可达（射界门对
    360° 模板恒假，天然豁免；此类模板不分配 rotating 槽）。
    AMB-5（MOVEMENT v1.2 §2.13）：引用名 turn_rate_deg_per_tick 与槽名 turn_rate_deg
    （types.py，deg/s 数据卡口径）经换算式 turn_rate_deg_per_tick = MAX(1, turn_rate_deg
    // 10) 对齐（MAX(1,·) 防默认值 1→0 零速锁死）。
    M3/B04：rotating 按当前角差重算不锁存——|角差| <= fire_arc_deg 即 FALSE。"""
    diff = angle_diff(target_deg, e.facing)
    step = max(1, e.unit.template.turn_rate_deg // 10)     # AMB-5 换算
    if abs(diff) <= step:
        e.facing = target_deg
    else:
        e.facing = (e.facing + (1 if diff > 0 else -1) * step) % 360
    e.rotating = abs(angle_diff(target_deg, e.facing)) > e.template.fire_arc_deg


def pivot_step(cfg: BalanceConfig, unit) -> None:
    """PB-51 原地转向推进（2026-10-04 拍板纳入——断箭 N17 neutral steering，映射 §五.9；
    推翻 MOVEMENT_PSEUDOCODE_v1.2 §2.13 reject 的**静止分支**：「无位移写 facing」不再即时，
    由角度差 × 类分档转向速率整数推导耗时；移动中 facing 仍即时 8 扇区（§2.13 移动分支
    维持——原地转向与行进转向两口径成文分立）。system_move_dispatch 头部唯一消费点
    （独占本拍移动槽——互斥不变式：pivot_to>=0 ⇒ move_path 恒空，由 cmd_pivot 清链/
    issue_move 外部新令清 pivot 双写点保证）。速率=cfg.pivot_rate_deg_per_tick[类]
    （履带快于轮式；R-09 rotate_step 的逐卡 turn_rate_deg 轨**不在此消费**——两轨分叉
    登记见 tables.py/tick.py）。步进式同 rotate_step（M3/B04：按当前角差重算不锁存，
    |diff|<=step 直接到位）；期间禁射走 fire_permitted ⑧ 门、SIDE 暴露走 GAP-25
    rotating 维持（转向慢=暴露窗口，R-09 同语义）。零掷骰。"""
    target = unit.pivot_to
    if target < 0:
        return
    step = cfg.pivot_rate_deg_per_tick[unit.template.movement_class]
    done = True
    for e in unit.elements:
        if e.mounted_in is not None or e.towed is TowState.TOWED:
            continue          # GAP-03 同谓词：车载/被拖元素不随本单位原地转向
        diff = angle_diff(target, e.facing)
        if abs(diff) <= step:
            e.facing = target
        else:
            e.facing = (e.facing + (1 if diff > 0 else -1) * step) % 360
            done = False
    if done:
        unit.pivot_to = -1    # 全员到位：pivot 结束（下一拍起 GAP-25 复位、⑧ 门放行）


def system_move(cfg: BalanceConfig, unit, now: int, *,
                on_road: bool = False, terrain_bp: int | None = None,
                formation_offset_fn=None, tow_pairs=()) -> None:
    if unit.deploy_state in (DeployState.DEPLOYING, DeployState.PACKING):
        return  # 展开中禁移动
    if unit.elements and all(x.towed is TowState.TOWED for x in unit.elements):
        return  # 全部被拖：由牵引方带动
    if unit.elements and all(e.mounted_in is not None for e in unit.elements):
        # GAP-14（§F5 :976-978）：整班随车——单位基准点随载具，早退
        carrier = unit.elements[0].mounted_in
        unit.pos = carrier.pos
        sync_followers(unit)
        return
    v = move_speed_cm_tick(cfg, unit, now, on_road=on_road, terrain_bp=terrain_bp)
    if v <= 0 or not unit.move_path:
        sync_followers(unit)
        return
    start = unit.pos
    budget = v
    while budget > 0 and unit.move_path:
        dest = unit.move_path[0]
        prev = unit.pos
        unit.pos, arrived = step_toward(unit.pos, dest, budget)
        if arrived:
            unit.move_path.pop(0)
            budget -= dist_cm(prev, dest)  # GAP-01：按实际距离扣减（原固定扣 1000）
        else:
            budget = 0
    # GAP-30：路径耗尽保持末段航向（用本 tick 实际位移向量），不再重置 0°；
    # 增量④（§2.4；2026-10-06 速度链块）：三分支求值前增 REVERSE 短路行——
    # 倒车期间车头朝向不随位移翻转（保持现值不写：下方 unit.elements[0].facing =
    # lead_facing 与队形循环 e.facing = lead_facing 写同值=无操作；不做"下令时刻
    # 快照"（零新槽）；期间射击侧 rotate_step 转 R-09 车体属独立语义，互不干预）
    if unit.move_mode is MoveMode.REVERSE:
        lead_facing = unit.elements[0].facing
    elif unit.move_path:
        nxt = unit.move_path[0]
        lead_facing = octant_deg(nxt[0] - unit.pos[0], nxt[1] - unit.pos[1])
    elif unit.pos != start:
        lead_facing = octant_deg(unit.pos[0] - start[0], unit.pos[1] - start[1])
    else:
        lead_facing = unit.elements[0].facing  # 无位移不写朝向
    unit.elements[0].facing = lead_facing
    for e in unit.elements:  # GAP-03：§F5 :988-993 谓词——排除车载/被拖，含首元素
        if e.mounted_in is None and e.towed is not TowState.TOWED:
            e.facing = lead_facing  # facing 双维随动（v1.5 C2/G14）
            e.pos = (formation_offset_fn(unit.pos, e.id)
                     if formation_offset_fn is not None else unit.pos)
    for e in unit.elements:  # GAP-02（§F5 :994-995）：移动自动出楼——楼位释放、隐蔽/尾甲加成终止
        b = getattr(e, "garrison_in", None)
        if b is not None:
            g = getattr(b, "garrisoned", None)
            # PB-57 驻楼命令块（2026-10-06）：改按身份移除（combat.destroy_element
            # 「按身份除名」同款）——原 `e in g`/`g.remove(e)` 走 ElementInstance
            # dataclass 字段相等（unit 互指等值有递归风险、跨单位同字段有误删风险），
            # 防御性身份判（2026-10-06 评审实验复核：字面相等在 id 纪律下行为正确；
            # ElementInstance 无 eq=False 保留防御式）。
            if g is not None and any(x is e for x in g):
                b.garrisoned = [x for x in g if x is not e]
            e.garrison_in = None
    if unit.ambush_active:
        unit.ambush_active = False        # 移动自动退出伏击（无首击加成）
    if unit.ambush_shot_bonus:            # GAP-28：独立第二 IF（§F5 :998）——手动退出后移动仍清加成（M19）
        unit.ambush_shot_bonus = False
    for pair in tow_pairs:  # GAP-14（§F5 :1001-1006）：拖曳随动（被拖元素 pos 唯一写点）
        if pair.tower_elements and pair.tower_elements[0].unit is unit:
            towed = pair.towed_element
            if unit.pos != start:  # AMB-10 拍板：本 tick 有位移才随动——后方固定偏移，消除同点重叠
                # 增量⑨/MV-B-22（§2.3 边界①；AMB-6 修复，2026-10-07 PB-60 随批落地）：
                # 偏移基向改按车体朝向 elements[0].facing 反向——恒取车尾正后方
                # −scale(DIR8[facing//45], tow_follow_offset_cm)（拖挂点物理上恒在
                # 车尾；原按「本 tick 位移向量反向」归一取偏移，倒车×拖曳叠加时位移
                # 向量指向车尾、被拖元素反落牵引车车头侧）；「有位移才随动」门与被拖
                # pos 唯一写点不动（契约⑨/AMB-10）；REVERSE 期 facing 由增量④ 保持
                # 现值不翻转，本行取到的即车头朝向。DIR8/scale=air.py 冻结族（契约⑯）
                bx, by = scale(DIR8[unit.elements[0].facing // 45],
                               cfg.tow_follow_offset_cm)
                towed.pos = (pair.tower_elements[0].pos[0] - bx,
                             pair.tower_elements[0].pos[1] - by)
            towed.facing = unit.elements[0].facing  # AMB-10：被拖 facing 跟随牵引朝向（原文无写点）
            if all(x.towed is TowState.TOWED for x in towed.unit.elements):
                towed.unit.pos = pair.tower_elements[0].pos  # 全被拖单位基准点随动
    sync_followers(unit)


# ── MOVEMENT_PSEUDOCODE_v1.2 命令层（§2.2/§2.4/§2.5/§2.8——2026-10-04 命令层块追加；
#    既有函数体零改动。MoveCmd{unit, path, mode, queue} 定义在 tick.py §D.7 命令集
#    〔2026-10-07 命令族收口块勘正：MoveCmd/ReverseCmd 已迁 types.py 定义+tick 再出口
#    ——issue_move 门3 后门4 前归一化 `cmd ← MoveCmd{…}` 须在本模块构造 MoveCmd，
#    movement→tick 反向导入边系 2026-10-06 评审明令禁止（issue_group_move 退回先例）〕）──

def _resolve_move_path(world, unit, path, mode) -> list:
    """§2.2 命令航点 → move_path（⑦块登记接线："find_path 消费端=命令层 move_path
    写入"）：逐段 world.find_path(frm→wp) 展开；prefer_road=（mode is MARCH）——
    §2.6-① 沿路寻路偏好属强行军（普通机动不偏好路，MV-B-17 同语义）。
    terrain 未接入（World.terrain=None）时 find_path stub=直线直填 RETURN [to]
    （AMB-8）⇒ 输出与 list(cmd.path) 逐位一致。零掷骰。"""
    frm = unit.pos
    out = []
    for wp in path:
        leg = world.find_path(frm, (wp[0], wp[1]),
                              unit.template.movement_class,
                              mode is MoveMode.MARCH)
        out.extend(leg)
        frm = (wp[0], wp[1])
    return out


def issue_move(world, cfg: BalanceConfig, cmd, handoff: bool = False) -> bool:
    """§2.2 命令入口（consume_unit_commands 与 UI/AI 同一接口）→ OK=True/REJECTED=False。

    handoff=内部移交通道（BLK-1 修复）：仅供 consume_unit_commands/动作令处理体内部
    安装航点用（§2.11 进位同口），UI/AI 一律不传（外部恒 FALSE）。
    【分支次序冻结（AMB-11 成文）】：handoff 判定必须先于 queue 判定——落地时若先判
    queue，内部安装会走"非排队覆盖"分支清链清 cap，BLK-1 即经此复活；下方分支序即
    实现序。ReverseCmd 特化归一（cmd ← MoveCmd{path=[dest], mode=REVERSE,
    queue=FALSE}）已落地（2026-10-07 命令族收口块——§2.2 :142 字面，插位门3 后
    门4 前：门4 读 cmd.mode，原生 ReverseCmd 无该字段）。
    【门1 接线收口（2026-10-07 发起人拍板：pack_or_move 移动触发面=采 IMPL 字面，
    登记 PB-56 批② 留待项① 就此闭账——契约㉑ DEPLOYED 半边特例化）】：PACKING
    拒令维持（三文档均无「打断收装」写点）；DEPLOYING×handoff 拒令维持（排队令
    丢弃不回队首成文口径）；DEPLOYING×外部移动令=作废展开进度回 MOBILE 同拍放行
    本令（机制版 v1.7 :1098「移动令即回 MOBILE 作废进度」=cmd_pack_or_move ②
    同款作废）；DEPLOYED=效果点转 PACKING 再走（IMPL v1.7 :1116『PackCmd /
    MoveCmd 触发』① 半边——本令照常安装，收装完成前 system_move 同名门拦位移、
    收装毕自动续走「先收装再走」；效果点后置=门2/3/4 拒令零副作用）。queue=TRUE
    排队令不经效果点（入链尾待执行——执行拍经 handoff 到 DEPLOYED 分支照样收装）。
    零掷骰。"""
    u = cmd.unit
    if u.deploy_state is DeployState.PACKING:
        return False   # 门1 收起中拒移动令（契约㉑——三文档均无「打断收装」写点；
                       #     system_move 内同名门维持不动 movement.py 顶部）
    if u.deploy_state is DeployState.DEPLOYING and handoff:
        return False   # 门1 展开中×内部通道拒（排队令丢弃不回队首——§2.2 成文口径；
                       #     system_morale 溃逃航点对 DEPLOYING 单位同拒=既有行为）
    if u.morale is MoraleState.ROUTED and not handoff:
        return False   # 门2 槽位再启用（2026-10-04 士气块）：士气门改为 **ROUTED 溃逃
                       #     失控拒令**（D014「失控移动」——外部移动令一律 REJECTED，
                       #     含 queue=TRUE 入队支；PINNED 按 PB-49 不拒令只减速）。
                       #     内部 handoff 通道豁免——system_morale 溃逃航点经此安装
    if u.elements and all(e.mounted_in is not None for e in u.elements):
        return False   # 门3 整班车载无独立移动令（GAP-2 修复——§2.10-3 双保险成立）
    if isinstance(cmd, ReverseCmd):
        cmd = MoveCmd(unit=u, path=[(cmd.dest[0], cmd.dest[1])],
                      mode=MoveMode.REVERSE, queue=False)
                       # ── ReverseCmd 特化归一（§2.2 :142 字面）：门3 后门4 前——
                       #    门4 读 cmd.mode（原生 ReverseCmd 无该字段即 AttributeError）
    if cmd.mode is MoveMode.REVERSE \
            and reverse_speed_bp(cfg, u.template) == 0:
        return False   # 门4 倒车资格（AMB-9 修复）：有效倒车 bp=0 →显式拒令（不产生
                       #     "REVERSE 模式空转锁"）。PB-52（2026-10-04）：改读
                       #     reverse_speed_bp 求值函数——单位级覆盖>类级缺省回退
    if handoff or not cmd.queue:
        # ── pack_or_move 移动触发面（2026-10-07 发起人拍板=采 IMPL 字面；效果点
        #    后置=拒令零副作用。handoff 忽略 queue 位（AMB-11 签名注记）故两通道
        #    同至此；DEPLOYING 仅外部可达（handoff 已在门1 拒）：
        if u.deploy_state is DeployState.DEPLOYING:
            u.deploy_state = DeployState.MOBILE   # ② 展开进度作废回 MOBILE，同拍
            u.deploy_timer = 0                     #   放行本令（机制版 v1.7 :1098——
                                                  #   cmd_pack_or_move ② 同款作废）
        if u.deploy_state is DeployState.DEPLOYED:
            u.deploy_state = DeployState.PACKING   # ① 移动令触发收装（IMPL v1.7 :1116
            u.deploy_timer = u.template.pack_time_ticks
                                                  #   『PackCmd / MoveCmd 触发』① 半边
                                                  #   ——本令照常安装，收装完成前
                                                  #   system_move 同名门拦位移、收装毕
                                                  #   自动续走「先收装再走」）
    if handoff:
        # ── 内部移交通道：仅安装，不清链/不清 cap（BLK-1）──
        u.move_path = _resolve_move_path(world, u, cmd.path, cmd.mode)
        u.move_mode = cmd.mode
    elif not cmd.queue:
        # ── 外部非排队新令：GAP-18 硬规则，四件一体覆盖（PB-51 +1：清原地转向）──
        u.move_path = _resolve_move_path(world, u, cmd.path, cmd.mode)
        u.move_mode = cmd.mode
        u.command_queue = []
        u.group_speed_cap = 0     # 单独外部下令=脱离编组同步（§2.9）
        u.pivot_to = -1           # PB-51：新移动令取消进行中 pivot（移动 facing 即时 8 扇区
                                  # 接管朝向——后令胜出；与移动自动出楼/退伏击同款「移动
                                  # 压过静止态」语义）
    else:
        u.command_queue.append(cmd)   # ── Shift 排队：入链尾（GAP-05）──
    return True


def current_order(u):
    """§2.2 current_order 查询位（GAP-18 adopt；推导式零新槽——UI/ALT 类查询）：
    有进行中移动令报 MOVE（含模式与末航点），否则报队列头 QUEUED，否则 IDLE。"""
    if u.move_path:
        return {"kind": "MOVE", "mode": u.move_mode, "dest": u.move_path[-1]}
    if u.command_queue:
        return {"kind": "QUEUED", "head": u.command_queue[0]}
    return {"kind": "IDLE", "stance": u.stance}


def attack_move_engage_hold(world, unit) -> bool:
    """§2.5 攻击前进接敌保持（GAP-04 adopt）：发现位敌人进入自身地面武器射程即停
    （暂停消耗 move_path 预算）；敌人消失/被毁/出界或手动新令自动恢复。
    判据粒度=单位首元素 pos × 敌方元素 pos × MAX 自身地面武器射程 × spotted_mask
    位掩码「已发现」（MV-B-16）；车载班随车结算（mounted 排除——与扫射/对空索敌
    同谓词）。纯谓词零副作用。"""
    r_max = 0
    for e in unit.elements:
        for ws in e.weapon_states:
            if ws.template.target_mask & TargetDomain.GROUND:
                r_max = max(r_max, ws.template.max_range_cm)  # 自身最强地面武器射程
    if r_max <= 0:
        return False              # 无地面武器→永不保持
    bit = 1 << unit.team
    for u2 in world.units:        # 插入序（确定性）
        if u2.team == unit.team or not u2.alive:
            continue
        if not (u2.spotted_mask & bit):
            continue              # 仅"已发现"敌人（断箭同语义）
        for e2 in u2.elements:
            if e2.mounted_in is not None:
                continue          # 车载班随车结算
            if dist_cm(unit.elements[0].pos, e2.pos) <= r_max:
                return True
    return False


def make_formation_fn(world, cfg: BalanceConfig, unit):
    """§2.8 队形三表（GAP-15 adopt 半）：每 tick 重建的闭包，不改 system_move 消费
    签名 formation_offset_fn(unit.pos, e.id)（movement.py system_move 内）。
    shape==NONE → None（现状同点堆叠，零行为变化——MV-B-19）；k=行进向 DIR8 索引
    （有航点按下一航点，到达后按末段朝向——GAP-30 既有语义）；rank=插入序编制位
    （§T 确定性）。WEDGE=AMB-2 修正式：楔尖=首元素 (0,0)、成对 ±line_s//2、纵深
    按对递增。DIR8/PERP8/scale 复用 air.py 冻结族（契约⑯）；round_div 半舍入。"""
    if unit.formation_shape is FormationShape.NONE:
        return None
    n = len(unit.elements)
    shape = unit.formation_shape
    if unit.move_path:
        nxt = unit.move_path[0]
        k = octant_deg(nxt[0] - unit.pos[0], nxt[1] - unit.pos[1]) // 45
    else:
        k = unit.elements[0].facing // 45
    rank = {e.id: r for r, e in enumerate(unit.elements)}
    line_s = cfg.formation_line_spacing_cm
    col_s = cfg.formation_column_spacing_cm

    def fn(base_pos, element_id):
        r = rank[element_id]
        if shape is FormationShape.LINE:
            # 横队：沿行进垂线对称展开（n=3 → −1,0,+1；n=4 → −1,0,1,2 半舍入位级确定）
            lat = round_div(2 * r - n + 1, 2) * line_s
            off = scale(PERP8[k], lat)
        elif shape is FormationShape.COLUMN:
            # 纵队：沿行进反方向串列（首车在前）
            off = scale(DIR8[(k + 4) % 8], r * col_s)
        else:
            # WEDGE 楔形（AMB-2 修正式）：楔尖=首元素在中轴 (0,0)，其后成对左右
            # ±line_s//2、纵深按对递增（第 1 对 col_s、第 2 对 2×col_s……）
            if r == 0:
                off = (0, 0)
            else:
                depth = ((r + 1) // 2) * col_s
                side = (line_s // 2) if r % 2 else -(line_s // 2)  # 奇左偶右
                back = scale(DIR8[(k + 4) % 8], depth)
                lateral = scale(PERP8[k], side)
                off = (back[0] + lateral[0], back[1] + lateral[1])
        return (base_pos[0] + off[0], base_pos[1] + off[1])

    return fn


def system_move_dispatch(world, cfg: BalanceConfig, unit) -> None:
    """§2.4 dispatch 包装器——system_move 的唯一调用方（world_tick :1550 调用点已
    替换）：集中承载模式感知（ATTACK 保持门/MARCH 道路门/瓦片注入/队形接线/到达
    模式复位），冻结函数体 system_move 不感知模式。不重复 DeployState/被拖/车载门
    ——那些在 system_move 内部照旧生效（契约㉑）。零掷骰。"""
    now = world.tick
    # ── PB-51 原地转向：独占本拍移动槽（2026-10-04）。转向中不位移（move_path 恒空——
    #    cmd_pivot 停车写入/新移动令清 pivot 双写点构成互斥不变式）；不进 system_move ⇒
    #    出楼/退伏击等移动副作用不触发（未位移）。期间禁射=fire_permitted ⑧ 门（tick.py）、
    #    SIDE 暴露=GAP-25 rotating 维持。HANDOFF 通道不达：consume_unit_commands 队列头
    #    执行条件含 pivot_to<0（排队移动令等 pivot 完成后续走）。──
    if unit.pivot_to >= 0:
        pivot_step(cfg, unit)
        return
    # 门：原 D014「士气态==PINNED→RETURN」——2026-10-04 拍板（MV-B-03 改B，断箭式）
    # 移除拒动门：PINNED 照常走 system_move，减速在 move_speed_cm_tick 乘区
    # （pinned() 判据缝恒假直至 GDD-05 士气槽落地——拍板语义已就位、零行为差）
    if unit.move_mode is MoveMode.ATTACK and unit.move_path \
            and attack_move_engage_hold(world, unit):
        sync_followers(unit)      # 停住不动：不进 system_move ⇒ 出楼/退伏击副作用不
        return                    # 触发（未位移）；感知侧三乘区口径=MV-B-23（§2.5④）
    on_road = unit.move_mode is MoveMode.MARCH and world.road_at(unit.pos)
    # 增量⑥（GAP-02 接线——唯一写 on_road=True 的路径；普通机动在路瓦片不吃道路档
    # ——MV-B-17；契约⑦：只接线不改乘区）
    terrain_bp = world.terrain_speed_tile_bp(unit.pos, unit.template.movement_class)
    # 增量⑦：瓦片注入接线（§2.14 谓词；terrain=None stub → None=类级缺省）
    fn = make_formation_fn(world, cfg, unit)   # 增量⑧（GAP-15）：NONE → None 现状逐位保持
    system_move(cfg, unit, now, on_road=on_road, terrain_bp=terrain_bp,
                formation_offset_fn=fn, tow_pairs=world.tow_pairs)  # 冻结函数直调（契约⑥）
    if not unit.move_path and unit.move_mode is not MoveMode.NORMAL:
        unit.move_mode = MoveMode.NORMAL        # 模式生命周期=当前移动令（到达即复位）


def nearest_on_segment(p, a, b):
    """§2.11 定标辅助（2026-10-06 速度链块）：点 p 到线段 ab 的最近点——LINE/CREEP
    炮击任务的超射程判距基准（规格 §2.11 仅定义点目标函数，线目标取采样线最近点
    为自然整数延伸——占位定标可推翻）。纯整数：点积投影+两端夹持；退化零长线段
    返回 a。零掷骰。"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    dd = dx * dx + dy * dy
    if dd == 0:
        return (a[0], a[1])
    t = (p[0] - a[0]) * dx + (p[1] - a[1]) * dy
    if t <= 0:
        return (a[0], a[1])
    if t >= dd:
        return (b[0], b[1])
    return (a[0] + dx * t // dd, a[1] + dy * t // dd)


def auto_approach_waypoint(unit, target, max_range_cm: int,
                           cfg: BalanceConfig):
    """§2.11 超射程自动进位（GAP-13 adopt；2026-10-06 速度链块）：炮兵对超射程
    目标下令时自动插入"最大射程内侧 standoff"航点（断箭 ARTILLERY 节官方语义的
    QoL 等效；P0 键位纠偏块 2026-10-13 复核留痕：manual.txt:471-474「Artillery
    units out of range will move into range (at maximum distance) and then
    fire」——standoff=2000cm 即「最大射程内侧 20m」量化余量（DIR8 近似误差
    ≤1.015% 恒覆盖；现役最短曲射武器 82mm 迫击炮 max_range=32000cm≫4000cm，
    AMB-4 半射程下界对真实曲射武器恒失活——行为即手册「前移至最大射程再打」）。d=单位首元素 pos×目标 ≤ max_range → None（射程内不插航点，行为
    不变）；否则 k=目标方位 DIR8 索引（octant_deg//45），stand=MAX(max_range−
    cfg.auto_approach_standoff_cm, max_range//2)（AMB-4 修复：半射程下界——
    max_range<standoff 常数的短程武器不再得负 stand 反向越过目标；比例余量
    50%≫DIR8 近似误差 1.015% 恒覆盖），航点=target−scale(DIR8[k], stand)。

    消费点（AMB-3 修复：不直写 move_path——单一命令入口口径 §2.2）=
    tick.cmd_fire_mission：世界级命令流=UI/AI 外部入口（§2.2 词汇「UI/AI 一律
    不传（外部恒 FALSE）」）→ §2.11 :384-385「外部直令场景」走 issue_move 外部
    通道（MoveCmd{path=[航点], mode=NORMAL, queue=FALSE}——四件一体：下达炮击
    任务即重置移动链/退编组；进位移动恒 NORMAL 模式）；handoff=TRUE 排队消费
    形态（§2.11 :379 主登记）留待 FireMissionCmd 入单位级 command_queue 的未来
    通道——现不可达（单位级队列仅 MoveCmd 可入），不冒装。到位后既有展开门
    （needs_deployed）与射击门照常接管（进位≠自动开火许可）。适用范围推荐=
    仅 INDIRECT 炮击任务语境（MV-B-21——超射程直射令不接，防替代玩家走位微操）。
    零掷骰。"""
    d = dist_cm(unit.elements[0].pos, target)
    if d <= max_range_cm:
        return None                       # 射程内：不插航点（行为不变）
    k = octant_deg(target[0] - unit.pos[0], target[1] - unit.pos[1]) // 45
    stand = max(max_range_cm - cfg.auto_approach_standoff_cm, max_range_cm // 2)
    step = scale(DIR8[k], stand)
    return (target[0] - step[0], target[1] - step[1])
