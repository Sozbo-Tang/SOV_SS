#!/usr/bin/env python3
"""Kev 人机对局 demo：SOV_SS 无头整局，双方由 KevPlayer 驱动（盲部署→实战→结算）。

用法（SOV_SS 仓库根目录）：
  # 无服务端纯规则兜底（零模型依赖，先验证接线）：
  python tools/kev_game_demo.py
  # 一方接 kev.serve、一方规则兜底：
  python tools/kev_serve.py --start            # 另一个终端先起服
  python tools/kev_game_demo.py --url http://127.0.0.1:8011
  # 双方都接模型：
  python tools/kev_game_demo.py --url http://127.0.0.1:8011 --both-kev
  # 四角色班组驱动（实战相位 1Hz 地面→空中→预备队 轮转）：
  python tools/kev_game_demo.py --mode squad

决策日志：--log（缺省 out/kev_decisions.jsonl）逐决策 JSONL——回放=种子+命令流。
场景：200000×100000 图（tests/test_fullgame_acceptance 同幅），中央占点，
双方卡组=步枪排×2+坦克+突击炮（合成测试卡，数值非平衡档）。
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.ai import AgentSquad, KevClient, KevPlayer, LocalKevEngine  # noqa: E402
from sovs.sim.air import PHASE_DEPLOY, PHASE_SETTLE  # noqa: E402
from sovs.sim.tick import (DeckSlot, Objective, make_world,  # noqa: E402
                           world_tick)
from sovs.sim.types import (Armor, DamageType, ElementTemplate,  # noqa: E402
                            ElementType, Mode, MovementClass, TargetDomain,
                            Trajectory, UnitFlag, UnitTemplate, UnitType,
                            WeaponTemplate)

# ── 合成测试卡（照 tests/test_fullgame_acceptance 数值——锚点服务非平衡档）──

RIFLE_W = WeaponTemplate(
    name="rifle", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    damage=2, salvo=1, aim_time_ticks=5, reload_time_ticks=30, ammo_base=50,
    max_range_cm=120000, dispersion_cm=500, accuracy_base_bp=6000,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    suppression_power=3, reveal_time_ticks=10)
CANNON_W = WeaponTemplate(
    name="cannon", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    pen_min=6, pen_max=9, damage=6, salvo=1, aim_time_ticks=6,
    reload_time_ticks=50, ammo_base=30, max_range_cm=115000,
    dispersion_cm=400, accuracy_base_bp=6200,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    blast_radius_cm=500, suppression_power=5, reveal_time_ticks=10)
GUN_W = WeaponTemplate(
    name="he gun", target_mask=TargetDomain.GROUND, damage_type=DamageType.HE,
    pen_min=6, pen_max=6, damage=5, blast_radius_cm=4000, salvo=2,
    aim_time_ticks=8, reload_time_ticks=60, ammo_base=40,
    max_range_cm=110000, dispersion_cm=800, accuracy_base_bp=5500,
    projectile_speed_cm_tick=5000, trajectory=Trajectory.BALLISTIC,
    suppression_power=8, reveal_time_ticks=10)

RIFLE_TPL = UnitTemplate(
    template_id=301, name="rifle plt", category=1, cost=60,
    element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                       unit_type=UnitType.INFANTRY, hp_max=10,
                                       weapons=(RIFLE_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)
TANK_TPL = UnitTemplate(
    template_id=303, name="tank", category=2, cost=180,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=15,
        armor_ke=Armor(10, 7, 5, 3), armor_he=Armor(8, 6, 4, 3),
        weapons=(CANNON_W,)),),
    optics_ground_cm=110000, stealth_base=3, speed_tier=2,
    movement_class=MovementClass.TRACK)
GUN_TPL = UnitTemplate(
    template_id=302, name="assault gun", category=3, cost=150,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=12,
        armor_ke=Armor(8, 5, 3, 2), armor_he=Armor(6, 4, 3, 2),
        weapons=(GUN_W,)),),
    optics_ground_cm=120000, stealth_base=3, speed_tier=2,
    movement_class=MovementClass.TRACK,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.INDIRECT))

TRUCK_TPL = UnitTemplate(
    template_id=306, name="tow truck", category=4, cost=40,
    element_templates=(ElementTemplate(
        element_type=ElementType.VEHICLE, unit_type=UnitType.MECH, hp_max=12,
        self_smoke_charges=2),),
    optics_ground_cm=80000, stealth_base=4, speed_tier=3,
    movement_class=MovementClass.WHEEL,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.TOW) | (1 << Mode.TRANSPORT),
    tow_tonnage=5, own_weight_tons=3)
MIXED_TPL = UnitTemplate(
    template_id=307, name="motorized plt", category=1, cost=120,
    element_templates=(
        RIFLE_TPL.element_templates[0],
        RIFLE_TPL.element_templates[0],
        ElementTemplate(element_type=ElementType.VEHICLE,
                        unit_type=UnitType.MECH, hp_max=15, seats=2)),
    optics_ground_cm=120000, stealth_base=5, speed_tier=3,
    movement_class=MovementClass.WHEEL)

DECK = ((RIFLE_TPL, 2), (TANK_TPL, 1), (GUN_TPL, 1), (TRUCK_TPL, 2),
        (MIXED_TPL, 1))
# 预备队空降卡（空裁8 投送限定——购卡门恒拒，走运输机 PARATROOP 载荷投放）
PARA_TPL = UnitTemplate(
    template_id=305, name="paratroop plt", category=1, cost=60,
    element_templates=(RIFLE_TPL.element_templates[0],) * 3,
    optics_ground_cm=120000, stealth_base=6, speed_tier=1,
    movement_class=MovementClass.FOOT,
    flags=UnitFlag.DELIVERY_AIRDROP_ONLY)
SOUTH, NORTH = (100000, 0), (100000, 100000)
CENTER_OBJ = Objective(id=1, pos=(100000, 50000), radius_cm=5000)


def build_world(seed: int):
    """无头对局世界构造（FE-T03 回放场景构造器——sovs/sim/wire.py SCENARIO_BUILDERS
    注册 "kev_game_demo.v1" → 本函数，Replayer 重建/黄金回放复用）。

    200000×100000 图 + 中央占点 + 双方 DECK/PARA DeckSlot 挂载（原 run() 内联段
    抽出，行为不变）。内联合成卡 template_id=301~307 不在任何数据文件（实卡
    101-107/201-203，cards_ground.v1.json 实核）——回放侧必须经本构造器复建，
    deck template_id 清单由 Replayer 重建后一致性断言对照。占点逐次新造
    （Objective 可变 owner 槽防跨 world 共享实例串写）。"""
    w = make_world(seed, phase=PHASE_DEPLOY, size_cm=(200000, 100000))
    w.objectives.append(Objective(id=CENTER_OBJ.id, pos=CENTER_OBJ.pos,
                                  radius_cm=CENTER_OBJ.radius_cm))
    for p in w.players:
        p.deck_slots = [DeckSlot(tpl, n) for tpl, n in DECK]
        p.deck_slots.append(DeckSlot(PARA_TPL, 1))   # 预备队池（D017——装机扣份）
    return w


def run(seed: int, max_ticks: int, url: str | None, both_kev: bool,
        log_path: str, api_key: str | None, args_local: bool = False,
        args_run: str = 'jaredpalmer/kev-0.5b', args_kev_path: str = None,
        mode: str = 'player') -> int:
    w = build_world(seed)

    if args_local:
        client = LocalKevEngine(args_run, dtype='bf16', kev_path=args_kev_path)
    else:
        client = KevClient(url, api_key=api_key) if url else None
    # mode=player：KevPlayer 单体四节拍（缺省，行为不变）；
    # mode=squad ：AgentSquad 四角色班组（实战相位 1Hz 地面→空中→预备队 轮转）
    cls = AgentSquad if mode == 'squad' else KevPlayer
    p0 = cls(0, client, anchors=(SOUTH, NORTH), log=log_path, label="red")
    p1 = cls(1, client if both_kev else None, anchors=(SOUTH, NORTH),
             log=log_path, label="blue")
    print(f"对局开始 seed={seed}  红方={'kev' if client else '规则'}  "
          f"蓝方={'kev' if (client and both_kev) else '规则'}  日志={log_path}"
          + ("  驱动=四角色班组(AgentSquad)" if mode == 'squad' else ""))
    t0 = time.monotonic()
    ticks = 0
    try:
        while w.tick < max_ticks and w.phase != PHASE_SETTLE:
            p0.step(w)
            p1.step(w)
            world_tick(w)
            ticks += 1
            if ticks % 2000 == 0:
                print(f"  … tick={w.tick} 单位={len(w.units)} "
                      f"红kev/规则={p0.stats['kev']}/{p0.stats['fallback']} "
                      f"蓝kev/规则={p1.stats['kev']}/{p1.stats['fallback']}")
    finally:
        p0.close()
        p1.close()
    wall = time.monotonic() - t0
    print(f"对局结束 tick={w.tick} 相位={w.phase} 用时={wall:.1f}s")
    for name, pl in (("红", p0), ("蓝", p1)):
        print(f"  {name}方决策：kev={pl.stats['kev']} 规则兜底={pl.stats['fallback']}")
    if w.result is not None:
        print(f"  裁决：胜方 team{w.result.winner} 占点={w.result.obj_counts} "
              f"剩余分值={w.result.unit_scores} 剩余血量={w.result.hp_totals}")
    else:
        alive = [u.team for u in w.units if u.alive]
        print(f"  （未到结算拍——存活单位 {len(alive)} 个）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Kev 人机对局 demo（无头整局）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--ticks", type=int, default=14_500,
                    help="推进上限（缺省略超实战相全长，走到自然结算）")
    ap.add_argument("--url", default=None, help="kev.serve 地址（缺省=纯规则兜底）")
    ap.add_argument("--both-kev", action="store_true", help="双方都接模型（缺省仅红方）")
    ap.add_argument("--log", default="out/kev_decisions.jsonl")
    ap.add_argument("--api-key", default=os.environ.get("KEV_API_KEY"))
    ap.add_argument("--local", action="store_true",
                    help="进程内加载模型（不起端口服务；需 kev 依赖）")
    ap.add_argument("--run", default="jaredpalmer/kev-0.5b")
    ap.add_argument("--kev-path", default=None, help="kev 仓库路径直挂")
    ap.add_argument("--mode", choices=["player", "squad"], default="player",
                    help="决策驱动：player=KevPlayer 单体（缺省）；"
                         "squad=AgentSquad 四角色班组（1Hz 轮转）")
    args = ap.parse_args()
    return run(args.seed, args.ticks, args.url, args.both_kev, args.log,
               args.api_key, args.local, args.run, args.kev_path, args.mode)


if __name__ == "__main__":
    sys.exit(main())
