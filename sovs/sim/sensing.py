"""§F3 侦察函数族（伪代码 v1.7 §F3——终检 GAP-22/27 修复版）。

检测距离 = 光学 × optics_factor（SEN 暴击，GAP-22）× 移动/伏击修正 × 隐蔽查表
（目标林内状态传入，GAP-27）− 穿林/穿烟逐米衰减；
隐蔽加成（驻楼/林地）后置于乘区（v1.4 口径统一）；
mark_level 每扫描重算（v1.4：无接触回落 NONE）。
穿林/穿烟/林内三通道数据源=terrain_sensing_channels（2026-10-07 感知接线块——
PB-53 留待项②收口：world_tick ③ 与 fire_at 校射调用点均已喂）。
"""
from __future__ import annotations

from .combat import optics_factor_bp
from .geom import dist_cm, isqrt_exact
from .tables import BalanceConfig, CONFIG
from .types import AltTier, MarkLevel, UnitFlag, UnitType


def effective_stealth_x10(cfg: BalanceConfig, unit, in_forest: bool = False) -> int:
    """有效隐蔽（0..100，内部×10）。乘区先行，地形/驻楼加成后置。"""
    s = unit.template.stealth_base * 10
    m = 10000
    if unit.moving():
        m = m * cfg.stealth_move_mult_bp // 10000
        if (unit.template.flags & UnitFlag.FOREST_WALK_SILENT) and in_forest:
            m = m * cfg.forest_walk_silent_mult_bp // 10000  # 静默行军豁免
    if unit.infiltration_timer > 0:
        m = m * cfg.infiltration_mult_bp // 10000
    if unit.ambush_active:
        m = m * cfg.ambush_mult_bp // 10000
    if any(e.reveal_timer > 0 for e in unit.elements):
        m = m * cfg.reveal_mult_bp // 10000
    s = s * m // 10000
    if ((unit.template.flags & UnitFlag.CAN_GARRISON)          # AMB-02 拍板：模板前置（方案5 合取式）
            and any(getattr(e, "garrison_in", None) is not None for e in unit.elements)):
        s += cfg.garrison_stealth_add_x10
    if in_forest:
        s += cfg.forest_stealth_add_x10
    return max(0, min(100, s))


def stealth_factor_bp(cfg: BalanceConfig, stealth_x10: int) -> int:
    idx = max(0, min(10, stealth_x10 // 10))
    return cfg.stealth_factor_bp[idx]


def detection_range_cm(cfg: BalanceConfig, obs, tgt, *,
                       forest_m: int = 0, smoke_m: int = 0,
                       tgt_in_forest: bool = False) -> int:
    r = obs.template.optics_ground_cm * optics_factor_bp(obs.elements[0]) // 10000  # GAP-22：SEN 暴击消费点
    if obs.moving() and not (obs.template.flags & UnitFlag.NO_MOVE_VISION_PENALTY):
        r = r * cfg.move_vision_mult_bp // 10000   # 5000 ≡ //2（r 恒非负——位级一致）
    if obs.ambush_active:
        r = r // 2
    r = r * stealth_factor_bp(
        cfg, effective_stealth_x10(cfg, tgt, in_forest=tgt_in_forest)) // 10000  # GAP-27：目标林内+2 生效
    r -= cfg.detect_atten_per_m * (forest_m + smoke_m)
    return max(0, r)


def keep_range_cm(cfg: BalanceConfig, obs, tgt) -> int:
    """保持跟踪：未衰减距离（已发现目标更难甩）。GAP-22：乘 SEN 暴击因子（链式 //10000）。"""
    return (obs.template.optics_ground_cm
            * optics_factor_bp(obs.elements[0]) // 10000
            * stealth_factor_bp(cfg, tgt.template.stealth_base * 10)) // 10000


# ── 地形遮蔽几何通道（2026-10-07 感知接线块——PB-53 留待项②收口＋GAP-27/§2.12
#    「森林只喂 sensing 两侧」的实装侧；world_tick ③ system_sensing 与 fire_at
#    校射两调用点共用 terrain_sensing_channels 单点装配）。全整型零掷骰：
#    整型开方经 geom 单点取用（dist_cm/isqrt_exact——math.isqrt 精确整数运算，
#    geom.py 纪律；本模块不直接引入 math 模块——导入基线扫描裁定），除法一律 floor──


def in_forest_at(forest_tiles: frozenset, tile_cm: int, pos) -> bool:
    """pos 落格是否森林（GAP-27 目标林内通道：+2 隐蔽档/FOREST_WALK_SILENT 豁免）。"""
    return (pos[0] // tile_cm, pos[1] // tile_cm) in forest_tiles


def forest_m_between(forest_tiles, tile_cm: int, a, b) -> int:
    """线段 a→b 穿林米数：沿线每 tile_cm 步进取样（i/n 整型插值——寻路栅格化/
    tests 侧 _route_tile_kinds 同族先例；不含起点、含第 n 点），命中森林格数
    ×tile_cm//100。同点或不足一步 → 0：目标自身林内状态走 in_forest 通道
    （+2 隐蔽档），与路径逐米衰减分立不双算。"""
    if not forest_tiles:
        return 0
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dist_cm(a, b) // tile_cm
    if n <= 0:
        return 0
    hits = 0
    for i in range(1, n + 1):
        if ((a[0] + dx * i // n) // tile_cm,
                (a[1] + dy * i // n) // tile_cm) in forest_tiles:
            hits += 1
    return hits * tile_cm // 100


def smoke_m_between(zones, a, b) -> int:
    """线段 a→b 穿烟米数：逐 SmokeZone 求线段×圆弦长（投影＋geom.isqrt_exact
    整型开方——combat falloff 同族纯整数运算），区间夹逼 [0, 线段长] 后累计 //100。
    同点线段弦长 0；r≤0 烟区跳过；相切（垂距==r）不计——边界含等号跳过。"""
    total_cm = 0
    for z in zones:
        r = z.radius_cm
        if r <= 0:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg2 = dx * dx + dy * dy                           # |ab|²
        if seg2 == 0:
            continue
        vx, vy = z.center[0] - a[0], z.center[1] - a[1]
        dot = vx * dx + vy * dy                            # v·u（投影分子）
        cross2 = (vx * vx + vy * vy) * seg2 - dot * dot    # 叉积²=|v|²|u|²−(v·u)²
        rr_seg2 = r * r * seg2
        if cross2 >= rr_seg2:                              # 垂距≥r（精确整数判定）
            continue
        seg = dist_cm(a, b)
        s = dot // seg                                     # 圆心投影沿线位置（可为负）
        half = isqrt_exact(rr_seg2 - cross2) // seg        # 半弦长（整型近似）
        lo = s - half
        if lo < 0:
            lo = 0
        hi = s + half
        if hi > seg:
            hi = seg
        if hi > lo:
            total_cm += hi - lo
    return total_cm // 100


def terrain_sensing_channels(world):
    """感知地形通道装配（单点——两调用点共用）：→ (forest_m_fn, smoke_m_fn,
    in_forest_fn)。terrain None（stub 场景）或 forest_tiles 空 → 森林两通道
    None（sensing 调用面 None→0/False 恒等分支，lean/stub 场景逐位不变）；
    烟通道恒为读 world.smoke_zones 的闭包（空表自然 0——烟区运行时增减由闭包
    实时承载）。零掷骰。"""
    def smoke_fn(a, b):
        return smoke_m_between(world.smoke_zones, a, b)
    layer = getattr(world, "terrain", None)
    tiles = getattr(world, "forest_tiles", None) or frozenset()
    if layer is None or not tiles:
        return None, smoke_fn, None

    def forest_fn(a, b):
        return forest_m_between(tiles, layer.tile_cm, a, b)

    def in_forest_fn(pos):
        return in_forest_at(tiles, layer.tile_cm, pos)

    return forest_fn, smoke_fn, in_forest_fn


def system_sensing(cfg: BalanceConfig, world, *,
                   forest_m_fn=None, smoke_m_fn=None,
                   in_forest_fn=None) -> None:
    """每 sensing_period_ticks 一次：配对扫描 + mark_level 重算（v1.4 语义）。
    in_forest_fn(pos)→bool：目标林内状态通道（GAP-27；None=无林，侦测端 +2 档不生效）。"""
    for tgt in world.units:
        tgt.mark_level = MarkLevel.NONE
    alive = [u for u in world.units if u.alive]
    for obs in alive:
        for tgt in alive:
            if tgt.team == obs.team:
                continue
            d = dist_cm(obs.pos, tgt.pos)
            forest_m = forest_m_fn(obs.pos, tgt.pos) if forest_m_fn else 0
            smoke_m = smoke_m_fn(obs.pos, tgt.pos) if smoke_m_fn else 0
            tgt_forest = in_forest_fn(tgt.pos) if in_forest_fn else False
            if d <= detection_range_cm(cfg, obs, tgt, forest_m=forest_m,
                                       smoke_m=smoke_m, tgt_in_forest=tgt_forest):
                tgt.spotted_mask |= 1 << obs.team
                if obs.template.category == 0:  # 侦察类 → 校准（R-01）
                    tgt.mark_level = MarkLevel.CALIBRATED
                elif tgt.mark_level < MarkLevel.SPOTTED:
                    tgt.mark_level = MarkLevel.SPOTTED
            elif d > keep_range_cm(cfg, obs, tgt):
                if not any(o is not obs and o.team == obs.team and o.alive
                           and dist_cm(o.pos, tgt.pos) <= keep_range_cm(cfg, o, tgt)
                           for o in alive):
                    tgt.spotted_mask &= ~(1 << obs.team)
    sense_air(cfg, world)   # R-17/R-23（AA 分支名单化，方案2——§F3 :599）


def sense_air(cfg: BalanceConfig, world) -> None:
    """§F3 :613-627 对空探测（R-17；方案2 名单化 + M17 对偶清位）。
    三分支：①防空体系探测（仅 aa_roster 名单——置位判据乘 SEN 暴击因子，GAP-22 :617）；
    ②低空目视分支（全体敌军，alt_tier==LOW——B-11 收窄口径）；③对偶清位（与地面
    keep_range 同构——超出该队全部探测者范围即清 spotted_mask 对应位，:622-627
    原文清位判据不带暴击因子）。air_ceiling=None（§D.1#8 不可及）视为探测不到。
    spotted_mask 唯一写者（air.py AircraftInstance 注释约定）。"""
    roster = getattr(world, "aa_roster", ())
    for a in world.aircraft:
        # ① 防空体系探测——仅名单（方案2）
        for g in world.units:
            if not g.alive or g.team == a.team or g not in roster:
                continue
            ceiling = g.template.air_ceiling
            if ceiling is None or a.alt_tier > ceiling or not g.elements:
                continue
            r = g.template.optics_air_cm * optics_factor_bp(g.elements[0]) // 10000
            if dist_cm(g.pos, a.pos) <= r:
                a.spotted_mask |= 1 << g.team
        # ② 低空目视分支保留不动（方案2）
        if a.alt_tier is AltTier.LOW:
            for g in world.units:
                if not g.alive or g.team == a.team:
                    continue
                if dist_cm(g.pos, a.pos) <= g.template.optics_ground_cm:
                    a.spotted_mask |= 1 << g.team
        # ③ M17/A23 对偶清位——超该队全部探测者（名单支+低空目视支）范围即清位
        team = 0
        m = a.spotted_mask
        while m:
            if m & 1:
                keep = False
                for g in world.units:
                    if not g.alive or g.team != team:
                        continue
                    ceiling = g.template.air_ceiling
                    if ((g in roster and ceiling is not None and a.alt_tier <= ceiling
                         and dist_cm(g.pos, a.pos) <= g.template.optics_air_cm)
                            or (a.alt_tier is AltTier.LOW
                                and dist_cm(g.pos, a.pos) <= g.template.optics_ground_cm)):
                        keep = True
                        break
                if not keep:
                    a.spotted_mask &= ~(1 << team)
            m >>= 1
            team += 1


def point_in_friendly_vision(cfg: BalanceConfig, world, team: int,
                             pt: tuple[int, int], *,
                             forest_m_fn=None, smoke_m_fn=None) -> bool:
    """校射视线判定（v1.3 §F3 定义体；点目标按隐蔽中位档(5)近似）。"""
    for obs in world.units:
        if not obs.alive or obs.team != team:
            continue
        r = (obs.template.optics_ground_cm * optics_factor_bp(obs.elements[0]) // 10000
             * cfg.stealth_factor_bp[5]) // 10000  # GAP-22：SEN 暴击消费点（链式 //10000）
        forest_m = forest_m_fn(obs.pos, pt) if forest_m_fn else 0
        smoke_m = smoke_m_fn(obs.pos, pt) if smoke_m_fn else 0
        r -= cfg.detect_atten_per_m * (forest_m + smoke_m)
        if dist_cm(obs.pos, pt) <= max(0, r):
            return True
    return False
