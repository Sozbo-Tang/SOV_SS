#!/usr/bin/env python3
"""黄金回放录制（FE-T03）：规则对规则整局 + 航空九令显式编排注入场景。

产物落 data/gen/replays/golden_<mode>_seed<seed>.jsonl（入库测试资产——与
data/gen/ 数据产物同区；out/ 是日志临时区不放资产）。首批 3 条：
  golden_rulevrule_seed42.jsonl / golden_rulevrule_seed7.jsonl（规则 vs 规则、
  不同种子）+ golden_air_seed42.jsonl（航空覆盖场景）。

九令覆盖达成手段（双保险）：①显式编排注入——航空场景在规则 KEV 打底之上，
按 sovs/ai/actions.py 构造点同款参数形态脚本化补发九令各至少一次（构造行口径
本会话 grep 实测：AirCallCmd=actions.py:137（其前 :131-136 为 PARATROOP 载荷
换装段）/AirStrikeCmd=:144/AirAirdropCmd=:151/AirPatrolCmd=:157/
AirEngageAirCmd=:161/AirRTBCmd=:164/AirAltCmd=:169/AirMoveCmd=:265/
AirDisengageCmd=:268），含 PARATROOP 载荷换装路径（slot.template 活引用）；
②录后核对——写盘前统计 rec:cmd 命令类型集合，断言九令齐+关键地面命令族在列，
不齐即录制失败退出码非 0（验收口径=「录制后核对实际覆盖命令族清单」有可验证
达成路径，不承诺规则兜底自然覆盖——规则是否实际发出九令取决于效用打分无保证）。

录制循环=kev_game_demo.run 同款（step→step→world_tick），命令逐拍入队记录、
逐 tick 校验和随文件落盘（唯一口径）；Replayer 逐位比对见
tests/test_golden_replay.py。

用法（仓库根）：
  python3 tools/record_golden.py                 # 录全部 3 条
  python3 tools/record_golden.py --only rulevrule
  python3 tools/record_golden.py --only air
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovs.ai import KevPlayer  # noqa: E402
from sovs.sim.air import PHASE_SETTLE  # noqa: E402
from sovs.sim.air_data import CARD_OBJECTS  # noqa: E402
from sovs.sim.tick import (AirAirdropCmd, AirAltCmd, AirCallCmd,  # noqa: E402
                           AirDisengageCmd, AirEngageAirCmd, AirMoveCmd,
                           AirPatrolCmd, AirRTBCmd, AirStrikeCmd, FireMissionCmd,
                           SetModeCmd, queue_command, world_tick)
from sovs.sim.types import AltTier, FireMissionForm, Mode, UnitFlag  # noqa: E402
from sovs.sim.wire import ReplayWriter, encode_command  # noqa: E402
from tools.kev_game_demo import SOUTH, NORTH, build_world  # noqa: E402

# ── 覆盖核对清单（录制侧与 tests/test_golden_replay.py 消费同源——import 本表）──

AIR_NINE: tuple = (                  # AIR §D.5 航空命令集（9，闭合清单）
    "AirCallCmd", "AirMoveCmd", "AirPatrolCmd", "AirAltCmd", "AirStrikeCmd",
    "AirAirdropCmd", "AirEngageAirCmd", "AirDisengageCmd", "AirRTBCmd",
)
GROUND_REQUIRED: tuple = ("PurchaseCmd", "MoveCmd", "FormationCmd")  # 关键地面命令族
DEFAULT_TICKS = 14_500               # 略超实战相全长，走到自然结算


def _para_slot_template(player):
    """预备队空降卡模板（actions.py:131-136 换装段同款：deck 槽活引用）。"""
    slot = next((s for s in player.deck_slots
                 if s.template.flags & UnitFlag.DELIVERY_AIRDROP_ONLY), None)
    return None if slot is None else slot.template


def _aircraft_by_template(world, team: int, template_id: int):
    return next((a for a in world.aircraft
                 if a.team == team and a.template.template_id == template_id),
                None)


def _unit_by_template(world, team: int, template_id: int):
    return next((u for u in world.units
                 if u.team == team and u.template.template_id == template_id),
                None)


def air_inject_at(world, tick: int) -> list:
    """航空九令显式编排注入表：该拍应注入的 [(player_index, cmd)]。

    构造形态与 sovs/ai/actions.py build_commands 同款（行号见模块头注）；注入
    时点先于规则节拍（tick 0 抢占预算/在空上限，确定性）。查无对应航空器=前序
    呼叫被经济门拒——跳过该令（录后覆盖核对会红，不静默）。"""
    p0, p1 = world.players[0], world.players[1]
    out = []
    if tick == 0:
        # 三机呼叫（p0）+ 对方战斗机（p1，缠斗窗口铺垫）——B-18 无相位门
        out.append((0, AirCallCmd(player=p0, template=CARD_OBJECTS["IL2M"],
                                  payload={"BOMB": 2})))
        out.append((0, AirCallCmd(player=p0, template=CARD_OBJECTS["YAK9"],
                                  payload={})))
        para_tpl = _para_slot_template(p0)     # PARATROOP 载荷换装路径（活引用）
        out.append((0, AirCallCmd(player=p0, template=CARD_OBJECTS["LI2"],
                                  payload={"PARATROOP": para_tpl})))
        out.append((1, AirCallCmd(player=p1, template=CARD_OBJECTS["FW190A"],
                                  payload={})))
    if tick == 30:
        a = _aircraft_by_template(world, 0, CARD_OBJECTS["YAK9"].template_id)
        if a is not None:
            out.append((0, AirAltCmd(aircraft=a, tier=AltTier.HIGH)))
    if tick == 40:
        a = _aircraft_by_template(world, 0, CARD_OBJECTS["IL2M"].template_id)
        if a is not None:
            out.append((0, AirPatrolCmd(aircraft=a, center=(100000, 45000),
                                        radius=3000)))
    if tick == 60:
        a = _aircraft_by_template(world, 0, CARD_OBJECTS["LI2"].template_id)
        if a is not None:
            out.append((0, AirMoveCmd(aircraft=a, path=[(90000, 47000)])))
    if tick == 90:
        # 双战斗机对向同点汇聚（缠斗窗口铺垫——engage 开拨后 8000cm 内自动接战）
        a = _aircraft_by_template(world, 0, CARD_OBJECTS["YAK9"].template_id)
        if a is not None:
            out.append((0, AirMoveCmd(aircraft=a, path=[(100000, 52000)])))
        b = _aircraft_by_template(world, 1, CARD_OBJECTS["FW190A"].template_id)
        if b is not None:
            out.append((1, AirMoveCmd(aircraft=b, path=[(100000, 48000)])))
    if tick == 610:                            # 实战拍（601 起为 PHASE_COMBAT）
        a = _aircraft_by_template(world, 0, CARD_OBJECTS["IL2M"].template_id)
        if a is not None:
            # GP-01 §4（wire 1.1）：带 axis 画线攻击轴形态——run 轴按东西线向推导，
            # 黄金回放随录覆盖 axis 键编解码（缺省形态另由 kev 规则自然覆盖）
            out.append((0, AirStrikeCmd(aircraft=a, target=(100000, 48000),
                                        weapon="BOMB",
                                        axis=((90000, 48000), (110000, 48000)))))
    if tick == 612:
        # GP-01 §3（wire 1.1）：FireMissionCmd.ammo 键端到端随录——突击炮
        # （302，mode_set 含 INDIRECT）切 INDIRECT 后下 HE 点目标任务
        u = _unit_by_template(world, 0, 302)
        if u is not None and u.elements:
            out.append((0, SetModeCmd(element=u.elements[0], mode=Mode.INDIRECT)))
    if tick == 613:
        u = _unit_by_template(world, 0, 302)
        if u is not None and u.elements:
            out.append((0, FireMissionCmd(unit=u, form=FireMissionForm.POINT,
                                          point=(100000, 52000), ammo_mult=1,
                                          ammo="HE")))
    if tick == 615:
        a = _aircraft_by_template(world, 0, CARD_OBJECTS["LI2"].template_id)
        if a is not None:
            out.append((0, AirAirdropCmd(aircraft=a, drop_point=(90000, 46000))))
    if tick == 620:
        a = _aircraft_by_template(world, 0, CARD_OBJECTS["YAK9"].template_id)
        if a is not None:
            out.append((0, AirEngageAirCmd(aircraft=a, engage=True)))
    if tick == 700:
        a = _aircraft_by_template(world, 0, CARD_OBJECTS["YAK9"].template_id)
        if a is not None:
            # 缠斗中=真脱离（R-20 尾掷）；非缠斗=记令覆盖（cmd 侧静默 REJECT）
            out.append((0, AirDisengageCmd(aircraft=a)))
    if tick == 800:
        a = _aircraft_by_template(world, 0, CARD_OBJECTS["LI2"].template_id)
        if a is not None:
            out.append((0, AirRTBCmd(aircraft=a)))   # B-22 不可逆返场
    return out


def record(mode: str, seed: int, out_path: str, max_ticks: int = DEFAULT_TICKS):
    """录制一条黄金回放。mode：rulevrule=纯规则对规则；air=规则打底+九令注入。

    返回 (路径, 命令类型集合)；覆盖核对由调用方（不齐退出码非 0）。
    """
    world = build_world(seed)
    p0 = KevPlayer(0, None, anchors=(SOUTH, NORTH), label="red")
    p1 = KevPlayer(1, None, anchors=(SOUTH, NORTH), label="blue")
    cmd_kinds: set = set()
    with ReplayWriter(out_path, world=world, seed=seed,
                      scenario="kev_game_demo.v1") as rw:
        pending = []                           # (tick, player_index, cmd)
        while world.tick < max_ticks and world.phase != PHASE_SETTLE:
            if mode == "air":
                for pi, cmd in air_inject_at(world, world.tick):
                    queue_command(world, cmd)
                    pending.append((world.tick, pi, cmd))
            for pi, player in ((0, p0), (1, p1)):
                n = len(world.command_queue)
                player.step(world)
                pending.extend((world.tick, pi, c)
                               for c in world.command_queue[n:])
            queued_tick = world.tick
            world_tick(world)
            # 只落盘随本次 world_tick 真被消费的命令（读侧悬空 tick 即报错）
            due = [pc for pc in pending if pc[0] == queued_tick]
            for t, pi, c in due:
                rw.command(t, pi, c)
                cmd_kinds.add(encode_command(c)["cmd"])
            pending = [pc for pc in pending if pc[0] != queued_tick]
            rw.checksum(world.tick, world)
    p0.close()
    p1.close()
    return out_path, cmd_kinds


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FE-T03 黄金回放录制")
    ap.add_argument("--only", choices=["rulevrule", "air"], default=None,
                    help="只录指定模式（缺省录全部 3 条）")
    ap.add_argument("--out-dir", default=os.path.join("data", "gen", "replays"))
    args = ap.parse_args(argv)

    jobs = [] if args.only == "air" else [
        ("rulevrule", 42), ("rulevrule", 7)]
    if args.only in (None, "air"):
        jobs.append(("air", 42))

    failures = []
    for mode, seed in jobs:
        path = os.path.join(args.out_dir,
                            "golden_%s_seed%d.jsonl" % (mode, seed))
        _path, kinds = record(mode, seed, path)
        # ②录后核对：九令齐+关键地面命令族在列（不齐即录制失败）
        required = set(AIR_NINE) | set(GROUND_REQUIRED) if mode == "air" \
            else set(GROUND_REQUIRED)
        missing = required - kinds
        n_cmd = len(kinds)
        if missing:
            failures.append((path, missing))
            print("✗ %s：缺命令族 %s（已覆盖 %d 类）" % (path, sorted(missing), n_cmd))
        else:
            print("✓ %s：覆盖 %d 类命令族（含九令+关键地面族）" % (path, n_cmd))
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
