"""命令 wire schema + 回放文件格式 v1（FE-T03）：网络包格式=回放文件格式，一次定死。

结论先行：本模块是全命令族的唯一 wire 权威——encode_command/decode_command 双向
互逆（41 类命令，闭合清单以 tick.py `_dispatch_command` 分派支枚举为准，AST 守卫
见 tests/test_wire.py）；describe_command（AI 决策日志描述符）改由本 schema 生成
（sovs/ai/decision_log.py 原实现退役、再出口本函数——消灭单向半覆盖）；回放文件
v1=JSONL 三类记录（header/cmd/cksum），纯文本逐行 diff 是唯一审计面。

命令族闭合清单（41 支/41 类，本会话 AST 实测 tick.py 分派支逐支列出；35 支为
2026-10-12 现值，+6=P1 机制块 2026-10-13：GroundRTBCmd/LaserDesignateCmd/RadarCmd/
SupplySwitchCmd/AirAfterburnerCmd/AirDecoyCmd。FE-01
:278-279 原文「38 个分派支」系计数笔误——差异成因**推测**为另计入
consume_unit_commands 三处单位级队列 isinstance 位（tick.py 溯逃过滤/队列分派，
逐行核对；FE-01 原文未记载 38 的计数方式，无从确证），勘正结论
不依赖成因成立）。

引用解析七类全覆盖（encode 侧出现七类外引用即报错、decode 侧解析失败 fail-fast）：
  unit→unit_id；element→(unit_id, element_id) 复合键（ElementInstance.id 单位内
  编号，唯一键须复合）；player→player_index；aircraft→aircraft_id；
  PurchaseCmd.template→template_id 经 world.players[i].deck_slots 身份解析；
  AirCallCmd.template→air_template_id 经 air_data.AIR_CARDS 注册表解析
  （AircraftTemplate 不在 deck_slots——cmd_air_call 签名 air.py:374）；
  AirCallCmd.payload["PARATROOP"] 为地面 UnitTemplate 活引用（actions.py:131-137
  执行期换装 slot.template、:137 构造）→ wire 记 paratroop_template_id 经
  deck_slots 解析、None 保持 None；GarrisonCmd.building→building_id
  （world.buildings，map_loader.apply_map id=1 起文件序）。
  另 AttackCmd.target 可为 Building（cmd_attack 建筑资格门 tick.py:3100）→
  target_building_id 分立键。

枚举存 name 字符串、坐标存 int cm（与状态帧口径一致——整米化是 AI 摘要档行为）。

回放文件 v1（JSONL 逐行）：
  首行 rec:header{schema_version:"1.0", seed, phase_ticks(按实现现值 tables.py:266
    =（600,13200），勿抄 GDD-00 D007/D008 旧值), players_per_team, map_key,
    decks(双方 deck template_id 清单，含 PARATROOP 预备队卡——重建后一致性断言
    的对照面), checksum_fn:"fnv1a64-v1", scenario}；
  命令流 rec:cmd{tick, player_index, wire{...}}——tick=入队拍（该拍命令由下一
    world_tick 落地，与录制循环「step→step→world_tick」对齐）；
  校验和流 rec:cksum{tick, sum}——逐 tick 计算随文件落盘，唯一口径不做可配间隔
    （FE-T04 跨平台比对/FE-T10 desync 上报消费同一条流）。

state_checksum＝整型 FNV-1a 64 全状态指纹——抽取自 tests/test_integration.py
fingerprint（同源同粒度：该测试的 fingerprint() 现委托本模块
state_fingerprint_text，抽取为公共函数）。

Replayer 世界重建：header.scenario→SCENARIO_BUILDERS 显式注册表（scenario 名→
"模块:函数" dotted path，importlib 惰性导入；tools 为 PEP 420 namespace package
无需 __init__.py，仓库根直接 import）。未知 scenario 名 fail-fast 报错不静默；
decks/players_per_team/phase_ticks/map_key 在重建后做一致性断言（对不上即报错）。
重建后逐 tick 施放命令→world_tick→核对 cksum 流，错位即抛（格式不符明确报错
不静默错播）。FE-T06 观战器增量消费：Replayer.open/advance/seek 现场逐拍推导
（不预存帧序列），seek 靠每 600 拍 deepcopy 检查点加速（可丢弃重建——恢复段
照常逐拍核对，见 CHECKPOINT_EVERY）。

stdlib-only（sovs/sim 纪律；pydantic 例外仅 card_schema.py——见
tests/test_arch_constraints.py 文件级白名单）。
"""
from __future__ import annotations

import copy
import importlib
import json
import os

from .air import AircraftInstance
from .air_data import AIR_CARDS
from .tables import CONFIG
from .tick import (AirAirdropCmd, AirAfterburnerCmd, AirAltCmd, AirCallCmd,
                   AirDecoyCmd, AirDisengageCmd, AirEngageAirCmd, AirMoveCmd,
                   AirPatrolCmd, AirRTBCmd, AirStrikeCmd, AttackCmd,
                   BuySuppliesCmd, CancelCmd, CancelFireMissionCmd, CreateDumpCmd,
                   DeployCmd,
                   DismountCmd, FireMissionCmd, FormationCmd, GarrisonCmd,
                   GroundRTBCmd, LaserDesignateCmd, MountCmd, MoveCmd, PackCmd,
                   PivotCmd, PurchaseCmd, RadarCmd, ReverseCmd,
                   SetAirdropBeaconCmd, SetModeCmd, SetSniperCoverCmd,
                   SetStanceCmd, SmokeCmd, SprintCmd, StopCmd, SupplySwitchCmd,
                   ToggleAmbushCmd, TowCmd, UnGarrisonCmd, UntowCmd,
                   queue_command, world_tick)
from .types import (AltTier, Building, FireMissionForm, FormationShape, Mode,
                    MoveMode, SalvoMode, Stance, UnitTemplate)

# ── 版本与校验和标识（文件头契约）──

SCHEMA_VERSION = "1.4"          # wire/回放文件头 schema 版本（非向后兼容变更时 bump）
# 1.3→1.4＝2026-10-13 终审修复块：+CreateDumpCmd（卸货成堆——basics:202-204
# 「Order your truck to unload somewhere to create a supply dump」）；新命令族入
# 流＝非向后兼容，旧 1.3 回放文件在 load_replay schema_version 门 fail-fast 拒绝
# （预期行为），黄金回放三条随本版重录（tools/record_golden.py）。
# 1.2→1.3＝2026-10-13 P1 机制块（GP-01 断箭手册 P1 补建）：+6 新命令族
# （GroundRTBCmd/LaserDesignateCmd/RadarCmd/SupplySwitchCmd/AirAfterburnerCmd/
# AirDecoyCmd）+FireMissionCmd.ammo 值域扩 "PRECISION"（第三弹药位——键面不变、
# 值域变更按非向后兼容处理随版本升）；旧 1.2 回放文件在 load_replay
# schema_version 门 fail-fast 拒绝（预期行为），黄金回放三条随本版重录
# （tools/record_golden.py）。
# 1.1→1.2＝2026-10-12 垂足出动拍板：PurchaseCmd +可选 dest_x/dest_y（缺省=1.1
# 行为逐位不变——AI 购卡不带 dest）；旧 1.1 回放文件在 load_replay
# schema_version 门 fail-fast 拒绝（预期行为），黄金回放随本版重录。
# 1.0→1.1＝2026-10-12 GP-01 §3/§4 同批一次升版（防为单域分叉多版）：FireMissionCmd
# +ammo（曲射弹药位 HE|SMOKE——炮击模式块）、AirStrikeCmd +axis（画线攻击轴——
# 空中可控块）；两键均带缺省（缺省=1.0 行为逐位不变），旧 1.0 回放文件在
# load_replay schema_version 门 fail-fast 拒绝（预期行为，DATA-03/GP-01 登记），
# 黄金回放三条随本版重录（tools/record_golden.py）。
CHECKSUM_FN_ID = "fnv1a64-v1"   # 校验和函数标识（文件头记名——读侧不符即 fail-fast）
# 增量重放检查点间隔（FE-T06 观战器 seek 加速；快照可随时从命令流重建——
# 恢复段照常逐拍核对校验和，正确性不依赖快照）。600 拍=一分钟对局时长。
CHECKPOINT_EVERY = 600

# ── FNV-1a 64 + 全状态指纹（与 test_integration.fingerprint 同源同粒度）──

_FNV_OFFSET = 0xcbf29ce484222325
_FNV_PRIME = 0x100000001b3
_U64 = (1 << 64) - 1


def fnv1a64(data: bytes) -> int:
    """整型 FNV-1a 64（回放校验和唯一哈希——无第三方依赖、全平台逐位一致）。"""
    h = _FNV_OFFSET
    for b in data:
        h ^= b
        h = (h * _FNV_PRIME) & _U64
    return h


def state_fingerprint_text(world) -> str:
    """全状态指纹文本：单位/元素/武器态/弹丸/航空器/玩家/八通道 PCG32 内部 state。

    原 tests/test_integration.py fingerprint 本体抽取为公共函数（FE-T03——回放
    校验和与之同源同粒度；该测试现委托本函数，抽取前字段面不变：
    单位段 +deploy_state/deploy_timer/infiltration_timer、元素段 +garrison_in/
    mounted_in 引用、烟区逐区 center/ttl）。
    """
    parts = ["t%d:p%d:r%s" % (world.tick, world.phase,
                              ",".join(str(r.state) for r in world.rng._rngs))]
    for u in world.units:
        parts.append("U%d,%d,%s,%d,%d,%d,%d,%d,%d,%d" % (
            u.id, u.team, u.pos, int(u.alive), u.spotted_mask,
            int(u.mark_level), len(u.move_path),
            int(u.deploy_state), u.deploy_timer, u.infiltration_timer))
        for e in u.elements:
            gref = "-" if e.garrison_in is None else \
                "G%d" % getattr(e.garrison_in, "id", -1)
            mref = "-" if e.mounted_in is None else "M%d" % e.mounted_in.id
            parts.append("E%d,%s,%d,%d,%d,%d,%d,%s,%s" % (
                e.id, e.pos, e.hp_current, e.facing, e.suppression,
                e.reveal_timer, int(e.rotating), gref, mref))
            for ws in e.weapon_states:
                t = ws.target
                tref = "-" if t is None else (
                    "A%d" % t.id if isinstance(t, AircraftInstance) else "E%d" % t.id)
                parts.append("W%d,%d,%d,%s" % (int(ws.state), ws.timer,
                                               ws.ammo_left, tref))
    for a in world.aircraft:
        d = a.dogfight
        parts.append("A%d,%d,%s,%d,%d,%d,%d,%d,%d,%s,%r,%s,%d,%d,%d,%s" % (
            a.id, a.team, a.pos, int(a.alt_tier), a.hp_current, a.spotted_mask,
            int(a.state), a.facing, a.no_engage_until, a.flight_plan, a.task,
            sorted(a.ammo_left.items()), a.alt_pending is not None,
            int(a.patrol_loop), a.paratroop_cargo is not None,
            ("%d/%d/%d" % (d.opponent.id, d.round_timer, d.rounds)) if d else "-"))
    for p in world.projectiles:
        ht = p.hit_target
        parts.append("P%s,%s,%d,%d,%s" % (
            p.pos, p.dest, p.will_hit, p.speed_cm_tick,
            ("A%d" % ht.id) if isinstance(ht, AircraftInstance) else "-"))
    for pl in world.players:
        parts.append("PL%d,%d,%s,%d" % (pl.index, pl.air_points,
                                        sorted(pl.air_cooldowns.items()),
                                        len(pl.deck_slots)))
    for z in world.smoke_zones:                                          # 逐区 center/ttl
        parts.append("S%s,%d" % (z.center, z.ttl_ticks))
    return "|".join(parts)


def state_checksum(world) -> int:
    """整型 FNV-1a 64 全状态指纹（逐 tick 落盘；粒度=state_fingerprint_text）。"""
    return fnv1a64(state_fingerprint_text(world).encode("utf-8"))


# ── 引用解析助手（七类；encode 侧七类外引用报错、decode 侧查无 fail-fast）──


def _pos(p) -> list:
    return [int(p[0]), int(p[1])]


def _path(path) -> list:
    return [[int(x), int(y)] for x, y in path]


def _ref(obj, what: str) -> int:
    """引用对象 → 实例 ID（七类外对象缺 int id 即报错——fail-fast，不静默）。"""
    oid = getattr(obj, "id", None)
    if not isinstance(oid, int):
        raise ValueError("wire：无法解析 %s 引用（%r 不在七类引用面）" % (what, obj))
    return oid


def _unit(world, uid: int):
    u = next((u for u in world.units if u.id == uid), None)
    if u is None:
        raise ValueError("wire：unit_id=%r 不存在（解析失败 fail-fast）" % (uid,))
    return u


def _element(world, uid: int, eid: int):
    u = _unit(world, uid)
    e = next((e for e in u.elements if e.id == eid), None)
    if e is None:
        raise ValueError("wire：element (unit_id=%r, element_id=%r) 不存在" % (uid, eid))
    return e


def _elem_key(e) -> list:
    return [_ref(e.unit, "element.unit"), _ref(e, "element")]


def _aircraft(world, aid: int):
    a = next((a for a in world.aircraft if a.id == aid), None)
    if a is None:
        raise ValueError("wire：aircraft_id=%r 不存在（解析失败 fail-fast）" % (aid,))
    return a


def _building(world, bid: int):
    b = next((b for b in world.buildings if b.id == bid), None)
    if b is None:
        raise ValueError("wire：building_id=%r 不存在（解析失败 fail-fast）" % (bid,))
    return b


def _deck_template(world, player_index: int, template_id: int):
    """deck_slots 身份解析（PurchaseCmd/PARATROOP 载荷共用）：按 template_id 在
    该玩家卡组槽内找模板对象——返回槽内活模板（扣份/换装语义依赖此身份）。"""
    if not (0 <= player_index < len(world.players)):
        raise ValueError("wire：player_index=%r 越界" % (player_index,))
    slots = world.players[player_index].deck_slots
    for s in slots:
        if getattr(s.template, "template_id", None) == template_id:
            return s.template
    raise ValueError("wire：template_id=%r 不在 player %d 的 deck_slots（解析失败 "
                     "fail-fast）" % (template_id, player_index))


def _player(world, player_index: int):
    if not (0 <= player_index < len(world.players)):
        raise ValueError("wire：player_index=%r 越界" % (player_index,))
    return world.players[player_index]


# ── 35 类命令编码/解析（每类一对；注册表 WIRE_CODECS=闭合清单唯一事实源）──


def _enc_move(c):
    return {"cmd": "MoveCmd", "unit_id": _ref(c.unit, "unit"), "path": _path(c.path),
            "mode": MoveMode(c.mode).name, "queue": bool(c.queue)}


def _dec_move(w, d):
    return MoveCmd(unit=_unit(w, d["unit_id"]),
                   path=[(p[0], p[1]) for p in d["path"]],
                   mode=MoveMode[d["mode"]], queue=bool(d["queue"]))


def _enc_reverse(c):
    return {"cmd": "ReverseCmd", "unit_id": _ref(c.unit, "unit"),
            "dest": _pos(c.dest)}


def _dec_reverse(w, d):
    return ReverseCmd(unit=_unit(w, d["unit_id"]), dest=(d["dest"][0], d["dest"][1]))


def _unit_only(name, cls, field: str = "unit"):
    """单 unit 字段命令族（Stop/Cancel/Deploy/Pack/ToggleAmbush/CancelFireMission/
    Sprint/UnGarrison/Dismount——Dismount 字段名 squad_unit 同为 unit 引用）。"""
    def enc(c):
        return {"cmd": name, "unit_id": _ref(getattr(c, field), "unit")}

    def dec(w, d):
        return cls(**{field: _unit(w, d["unit_id"])})
    return enc, dec


def _enc_pivot(c):
    return {"cmd": "PivotCmd", "unit_id": _ref(c.unit, "unit"),
            "facing_deg": int(c.facing_deg)}


def _dec_pivot(w, d):
    return PivotCmd(unit=_unit(w, d["unit_id"]), facing_deg=int(d["facing_deg"]))


def _enc_formation(c):
    return {"cmd": "FormationCmd", "units": [_ref(u, "unit") for u in c.units],
            "shape": FormationShape(c.shape).name}


def _dec_formation(w, d):
    return FormationCmd(units=[_unit(w, uid) for uid in d["units"]],
                        shape=FormationShape[d["shape"]])


def _enc_set_mode(c):
    return {"cmd": "SetModeCmd", "element": _elem_key(c.element),
            "mode": Mode(c.mode).name}


def _dec_set_mode(w, d):
    uid, eid = d["element"]
    return SetModeCmd(element=_element(w, uid, eid), mode=Mode[d["mode"]])


def _enc_purchase(c):
    d = {"cmd": "PurchaseCmd", "player_index": int(c.player.index),
         "template_id": int(c.template.template_id)}
    if c.dest is not None:                             # v1.2 可选目的地（垂足出动）
        d["dest_x"], d["dest_y"] = int(c.dest[0]), int(c.dest[1])
    return d


def _dec_purchase(w, d):
    pi, tid = int(d["player_index"]), int(d["template_id"])
    dest = ((int(d["dest_x"]), int(d["dest_y"]))
            if "dest_x" in d else None)
    return PurchaseCmd(player=_player(w, pi),
                       template=_deck_template(w, pi, tid), dest=dest)


def _enc_fire_mission(c):
    return {"cmd": "FireMissionCmd", "unit_id": _ref(c.unit, "unit"),
            "form": FireMissionForm(c.form).name,
            "point": _pos(c.point) if c.point is not None else None,
            "line": [_pos(p) for p in c.line] if c.line is not None else None,
            "ammo_mult": int(c.ammo_mult),
            "ammo": str(c.ammo),               # GP-01 §3（wire 1.1）：曲射弹药位 HE|SMOKE
            "salvo_mode": SalvoMode(c.salvo_mode).name if c.salvo_mode is not None else None,
            "creep_speed": int(c.creep_speed)}


def _dec_fire_mission(w, d):
    return FireMissionCmd(
        unit=_unit(w, d["unit_id"]), form=FireMissionForm[d["form"]],
        point=tuple(d["point"]) if d["point"] is not None else None,
        line=[tuple(p) for p in d["line"]] if d["line"] is not None else None,
        ammo_mult=int(d["ammo_mult"]),
        ammo=d.get("ammo", "HE"),              # 带缺省读（缺省=1.0 行为——cmd 侧值域门收口）
        salvo_mode=SalvoMode[d["salvo_mode"]] if d["salvo_mode"] is not None else None,
        creep_speed=int(d["creep_speed"]))


def _enc_smoke(c):
    return {"cmd": "SmokeCmd", "element": _elem_key(c.element),
            "point": _pos(c.point) if c.point is not None else None}


def _dec_smoke(w, d):
    uid, eid = d["element"]
    return SmokeCmd(element=_element(w, uid, eid),
                    point=tuple(d["point"]) if d["point"] is not None else None)


def _enc_set_stance(c):
    return {"cmd": "SetStanceCmd", "unit_id": _ref(c.unit, "unit"),
            "stance": Stance(c.stance).name}


def _dec_set_stance(w, d):
    return SetStanceCmd(unit=_unit(w, d["unit_id"]), stance=Stance[d["stance"]])


def _enc_garrison(c):
    return {"cmd": "GarrisonCmd", "unit_id": _ref(c.unit, "unit"),
            "building_id": _ref(c.building, "building")}


def _dec_garrison(w, d):
    return GarrisonCmd(unit=_unit(w, d["unit_id"]),
                       building=_building(w, int(d["building_id"])))


def _enc_mount(c):
    return {"cmd": "MountCmd", "squads": [_elem_key(e) for e in c.squad_elements],
            "carrier_unit_id": _ref(c.carrier_unit, "unit")}


def _dec_mount(w, d):
    return MountCmd(squad_elements=[_element(w, u, e) for u, e in d["squads"]],
                    carrier_unit=_unit(w, d["carrier_unit_id"]))


def _enc_tow(c):
    return {"cmd": "TowCmd", "towers": [_elem_key(e) for e in c.tower_elements],
            "towed": _elem_key(c.towed_element)}


def _dec_tow(w, d):
    return TowCmd(tower_elements=[_element(w, u, e) for u, e in d["towers"]],
                  towed_element=_element(w, *d["towed"]))


def _enc_untow(c):
    return {"cmd": "UntowCmd", "element": _elem_key(c.element)}


def _dec_untow(w, d):
    uid, eid = d["element"]
    return UntowCmd(element=_element(w, uid, eid))


def _enc_attack(c):
    d = {"cmd": "AttackCmd", "element": _elem_key(c.element)}
    if isinstance(c.target, Building):
        d["target_building_id"] = _ref(c.target, "building")   # 建筑目标分立键
    else:
        d["target"] = _elem_key(c.target)
    return d


def _dec_attack(w, d):
    uid, eid = d["element"]
    if "target_building_id" in d and "target" not in d:
        target = _building(w, int(d["target_building_id"]))
    elif "target" in d and "target_building_id" not in d:
        target = _element(w, *d["target"])
    else:
        raise ValueError("wire：AttackCmd 需 target 与 target_building_id 恰一")
    return AttackCmd(element=_element(w, uid, eid), target=target)


def _enc_set_sniper_cover(c):
    return {"cmd": "SetSniperCoverCmd", "sniper_unit_id": _ref(c.sniper_unit, "unit"),
            "target_unit_id": _ref(c.target_unit, "unit")}


def _dec_set_sniper_cover(w, d):
    return SetSniperCoverCmd(sniper_unit=_unit(w, d["sniper_unit_id"]),
                             target_unit=_unit(w, d["target_unit_id"]))


def _enc_set_beacon(c):
    return {"cmd": "SetAirdropBeaconCmd", "unit_id": _ref(c.unit, "unit"),
            "pos": _pos(c.pos) if c.pos is not None else None}


def _dec_set_beacon(w, d):
    return SetAirdropBeaconCmd(unit=_unit(w, d["unit_id"]),
                               pos=tuple(d["pos"]) if d["pos"] is not None else None)


def _enc_buy_supplies(c):
    return {"cmd": "BuySuppliesCmd", "element": _elem_key(c.truck_element),
            "rounds": int(c.rounds), "medical": int(c.medical)}


def _dec_buy_supplies(w, d):
    uid, eid = d["element"]
    return BuySuppliesCmd(truck_element=_element(w, uid, eid),
                          rounds=int(d["rounds"]), medical=int(d["medical"]))


# ── P1 机制块 6 命令（2026-10-13，wire 1.3——编解码互逆；schema 与理由见命令类注）──

def _enc_ground_rtb(c):
    return {"cmd": "GroundRTBCmd", "unit_id": _ref(c.unit, "unit")}


def _dec_ground_rtb(w, d):
    return GroundRTBCmd(unit=_unit(w, d["unit_id"]))


def _enc_laser_designate(c):
    return {"cmd": "LaserDesignateCmd",
            "designator_unit_id": _ref(c.designator_unit, "unit"),
            "target_unit_id": _ref(c.target_unit, "unit")}


def _dec_laser_designate(w, d):
    return LaserDesignateCmd(designator_unit=_unit(w, d["designator_unit_id"]),
                             target_unit=_unit(w, d["target_unit_id"]))


def _enc_radar(c):
    return {"cmd": "RadarCmd", "unit_id": _ref(c.unit, "unit"),
            "engage": bool(c.engage)}


def _dec_radar(w, d):
    return RadarCmd(unit=_unit(w, d["unit_id"]), engage=bool(d["engage"]))


def _enc_supply_switch(c):
    return {"cmd": "SupplySwitchCmd", "unit_id": _ref(c.unit, "unit"),
            "switch": str(c.switch), "on": bool(c.on)}


def _dec_supply_switch(w, d):
    return SupplySwitchCmd(unit=_unit(w, d["unit_id"]),
                           switch=str(d["switch"]), on=bool(d["on"]))


def _enc_air_afterburner(c):
    return {"cmd": "AirAfterburnerCmd", "aircraft_id": _ref(c.aircraft, "aircraft"),
            "engage": bool(c.engage)}


# ── 终审修复块命令（2026-10-13，wire 1.4——编解码互逆；schema 与理由见命令类注）──

def _enc_create_dump(c):
    return {"cmd": "CreateDumpCmd", "unit_id": _ref(c.unit, "unit"),
            "pos": _pos(c.pos), "queue": bool(c.queue)}


def _dec_create_dump(w, d):
    return CreateDumpCmd(unit=_unit(w, d["unit_id"]),
                         pos=tuple(d["pos"]), queue=bool(d["queue"]))


def _dec_air_afterburner(w, d):
    return AirAfterburnerCmd(aircraft=_aircraft(w, d["aircraft_id"]),
                             engage=bool(d["engage"]))


def _enc_air_decoy(c):
    return {"cmd": "AirDecoyCmd", "aircraft_id": _ref(c.aircraft, "aircraft"),
            "action": str(c.action)}


def _dec_air_decoy(w, d):
    return AirDecoyCmd(aircraft=_aircraft(w, d["aircraft_id"]),
                       action=str(d["action"]))


def _enc_air_call(c):
    payload = dict(c.payload or {})
    wire_payload = {}
    if "BOMB" in payload:
        wire_payload["BOMB"] = int(payload["BOMB"])
    if "SUPPLY" in payload:
        wire_payload["SUPPLY"] = int(payload["SUPPLY"])
    if "PARATROOP" in payload:
        v = payload["PARATROOP"]
        if v is None:
            wire_payload["paratroop_template_id"] = None
        elif isinstance(v, UnitTemplate):
            wire_payload["paratroop_template_id"] = int(v.template_id)
        else:
            raise ValueError("wire：AirCallCmd.payload['PARATROOP'] 须为地面 "
                             "UnitTemplate 活引用或 None（actions.py:131-137 执行期"
                             "换装后的形态），得到 %r" % (v,))
    unknown = set(payload) - {"BOMB", "SUPPLY", "PARATROOP"}
    if unknown:
        # payload 键域闭合 {BOMB,SUPPLY,PARATROOP}（cmd_air_call 消费面）——
        # 未知键不得静默丢字段（丢=重放行为漂移）
        raise ValueError("wire：AirCallCmd.payload 未知键 %s（键域闭合）"
                         % sorted(unknown))
    return {"cmd": "AirCallCmd", "player_index": int(c.player.index),
            "air_template_id": int(c.template.template_id),
            "payload": wire_payload}


def _dec_air_call(w, d):
    pi = int(d["player_index"])
    template = AIR_CARDS.get(int(d["air_template_id"]))
    if template is None:
        raise ValueError("wire：air_template_id=%r 不在 air_data.AIR_CARDS 注册表"
                         % (d["air_template_id"],))
    wp = d["payload"]
    payload = {}
    if "BOMB" in wp:
        payload["BOMB"] = int(wp["BOMB"])
    if "SUPPLY" in wp:
        payload["SUPPLY"] = int(wp["SUPPLY"])
    if "paratroop_template_id" in wp:
        tid = wp["paratroop_template_id"]
        payload["PARATROOP"] = (None if tid is None
                                else _deck_template(w, pi, int(tid)))
    return AirCallCmd(player=_player(w, pi), template=template, payload=payload)


def _enc_air_move(c):
    return {"cmd": "AirMoveCmd", "aircraft_id": _ref(c.aircraft, "aircraft"),
            "path": _path(c.path)}


def _dec_air_move(w, d):
    return AirMoveCmd(aircraft=_aircraft(w, d["aircraft_id"]),
                      path=[(p[0], p[1]) for p in d["path"]])


def _enc_air_patrol(c):
    return {"cmd": "AirPatrolCmd", "aircraft_id": _ref(c.aircraft, "aircraft"),
            "center": _pos(c.center), "radius": int(c.radius)}


def _dec_air_patrol(w, d):
    return AirPatrolCmd(aircraft=_aircraft(w, d["aircraft_id"]),
                        center=(d["center"][0], d["center"][1]),
                        radius=int(d["radius"]))


def _enc_air_alt(c):
    return {"cmd": "AirAltCmd", "aircraft_id": _ref(c.aircraft, "aircraft"),
            "tier": AltTier(c.tier).name}


def _dec_air_alt(w, d):
    return AirAltCmd(aircraft=_aircraft(w, d["aircraft_id"]),
                     tier=AltTier[d["tier"]])


def _enc_air_strike(c):
    return {"cmd": "AirStrikeCmd", "aircraft_id": _ref(c.aircraft, "aircraft"),
            "target": _pos(c.target), "weapon": str(c.weapon),
            "axis": ([_pos(c.axis[0]), _pos(c.axis[1])]
                     if c.axis is not None else None)}   # GP-01 §4（wire 1.1）：画线攻击轴


def _dec_air_strike(w, d):
    ax = d.get("axis")
    return AirStrikeCmd(aircraft=_aircraft(w, d["aircraft_id"]),
                        target=(d["target"][0], d["target"][1]),
                        weapon=d["weapon"],
                        axis=None if ax is None
                        else ((ax[0][0], ax[0][1]), (ax[1][0], ax[1][1])))


def _enc_air_airdrop(c):
    return {"cmd": "AirAirdropCmd", "aircraft_id": _ref(c.aircraft, "aircraft"),
            "drop_point": _pos(c.drop_point)}


def _dec_air_airdrop(w, d):
    return AirAirdropCmd(aircraft=_aircraft(w, d["aircraft_id"]),
                         drop_point=(d["drop_point"][0], d["drop_point"][1]))


def _enc_air_engage(c):
    return {"cmd": "AirEngageAirCmd", "aircraft_id": _ref(c.aircraft, "aircraft"),
            "engage": bool(c.engage)}


def _dec_air_engage(w, d):
    return AirEngageAirCmd(aircraft=_aircraft(w, d["aircraft_id"]),
                           engage=bool(d["engage"]))


def _aircraft_only(name, cls):
    """单 aircraft 字段命令族（AirDisengageCmd/AirRTBCmd）。"""
    def enc(c):
        return {"cmd": name, "aircraft_id": _ref(c.aircraft, "aircraft")}

    def dec(w, d):
        return cls(aircraft=_aircraft(w, d["aircraft_id"]))
    return enc, dec


_stop_enc, _stop_dec = _unit_only("StopCmd", StopCmd)
_cancel_enc, _cancel_dec = _unit_only("CancelCmd", CancelCmd)
_deploy_enc, _deploy_dec = _unit_only("DeployCmd", DeployCmd)
_pack_enc, _pack_dec = _unit_only("PackCmd", PackCmd)
_ambush_enc, _ambush_dec = _unit_only("ToggleAmbushCmd", ToggleAmbushCmd)
_cfm_enc, _cfm_dec = _unit_only("CancelFireMissionCmd", CancelFireMissionCmd)
_sprint_enc, _sprint_dec = _unit_only("SprintCmd", SprintCmd)
_ungarrison_enc, _ungarrison_dec = _unit_only("UnGarrisonCmd", UnGarrisonCmd)
_dismount_enc, _dismount_dec = _unit_only("DismountCmd", DismountCmd,
                                          field="squad_unit")
_adisengage_enc, _adisengage_dec = _aircraft_only("AirDisengageCmd", AirDisengageCmd)
_artb_enc, _artb_dec = _aircraft_only("AirRTBCmd", AirRTBCmd)

# 闭合清单唯一事实源：类名 → (encode, decode)。AST 守卫（tests/test_wire.py）断言
# 其键集 == tick.py `_dispatch_command` 分派支类名集（35 支/35 类，AST 实测为准）。
WIRE_CODECS: dict = {
    "MoveCmd": (_enc_move, _dec_move),
    "ReverseCmd": (_enc_reverse, _dec_reverse),
    "StopCmd": (_stop_enc, _stop_dec),
    "CancelCmd": (_cancel_enc, _cancel_dec),
    "PivotCmd": (_enc_pivot, _dec_pivot),
    "FormationCmd": (_enc_formation, _dec_formation),
    "DeployCmd": (_deploy_enc, _deploy_dec),
    "PackCmd": (_pack_enc, _pack_dec),
    "SetModeCmd": (_enc_set_mode, _dec_set_mode),
    "PurchaseCmd": (_enc_purchase, _dec_purchase),
    "FireMissionCmd": (_enc_fire_mission, _dec_fire_mission),
    "CancelFireMissionCmd": (_cfm_enc, _cfm_dec),
    "SmokeCmd": (_enc_smoke, _dec_smoke),
    "SetStanceCmd": (_enc_set_stance, _dec_set_stance),
    "ToggleAmbushCmd": (_ambush_enc, _ambush_dec),
    "SprintCmd": (_sprint_enc, _sprint_dec),
    "GarrisonCmd": (_enc_garrison, _dec_garrison),
    "UnGarrisonCmd": (_ungarrison_enc, _ungarrison_dec),
    "MountCmd": (_enc_mount, _dec_mount),
    "DismountCmd": (_dismount_enc, _dismount_dec),
    "TowCmd": (_enc_tow, _dec_tow),
    "UntowCmd": (_enc_untow, _dec_untow),
    "AttackCmd": (_enc_attack, _dec_attack),
    "SetSniperCoverCmd": (_enc_set_sniper_cover, _dec_set_sniper_cover),
    "SetAirdropBeaconCmd": (_enc_set_beacon, _dec_set_beacon),
    "BuySuppliesCmd": (_enc_buy_supplies, _dec_buy_supplies),
    "AirCallCmd": (_enc_air_call, _dec_air_call),
    "AirMoveCmd": (_enc_air_move, _dec_air_move),
    "AirPatrolCmd": (_enc_air_patrol, _dec_air_patrol),
    "AirAltCmd": (_enc_air_alt, _dec_air_alt),
    "AirStrikeCmd": (_enc_air_strike, _dec_air_strike),
    "AirAirdropCmd": (_enc_air_airdrop, _dec_air_airdrop),
    "AirEngageAirCmd": (_enc_air_engage, _dec_air_engage),
    "AirDisengageCmd": (_adisengage_enc, _adisengage_dec),
    "AirRTBCmd": (_artb_enc, _artb_dec),
    "GroundRTBCmd": (_enc_ground_rtb, _dec_ground_rtb),
    "LaserDesignateCmd": (_enc_laser_designate, _dec_laser_designate),
    "RadarCmd": (_enc_radar, _dec_radar),
    "SupplySwitchCmd": (_enc_supply_switch, _dec_supply_switch),
    "AirAfterburnerCmd": (_enc_air_afterburner, _dec_air_afterburner),
    "AirDecoyCmd": (_enc_air_decoy, _dec_air_decoy),
    "CreateDumpCmd": (_enc_create_dump, _dec_create_dump),
}

WIRE_COMMANDS = frozenset(WIRE_CODECS)


def encode_command(cmd) -> dict:
    """命令对象 → wire dict（stdlib json 直序列化；枚举 name/坐标 int cm）。

    引用面七类外出现即 ValueError（fail-fast——闭合清单之外的形态不得静默入流）。
    """
    name = type(cmd).__name__
    codec = WIRE_CODECS.get(name)
    if codec is None:
        raise ValueError("wire：未知命令类型 %r（闭合清单 35 类之外）" % (name,))
    return codec[0](cmd)


def decode_command(world, wire: dict):
    """wire dict → 命令对象（解析失败 fail-fast——查无实例/未知类型即 ValueError）。"""
    if not isinstance(wire, dict) or "cmd" not in wire:
        raise ValueError("wire：命令记录缺 cmd 键（%r）" % (wire,))
    codec = WIRE_CODECS.get(wire["cmd"])
    if codec is None:
        raise ValueError("wire：未知命令类型 %r（闭合清单 35 类之外）" % (wire["cmd"],))
    return codec[1](world, wire)


# ── describe_command：AI 决策日志命令描述符（改由 wire schema 生成）──
# 等价回归口径（评审指正后定义）：对 describe_command 旧覆盖族**旧键逐键等价、
# 允许新增键**——如 FireMissionCmd 旧版只记 cmd/unit/form/point，wire 版必含
# line/ammo_mult/salvo_mode/creep_speed（消费面 tick.py:2123-2125 实证），逐字节
# 等价必红故不取。等价断言落 tests/test_wire.py（对旧实现冻结快照逐键比对）。


def describe_command(cmd) -> dict:
    """命令对象 → 可 JSON 描述符（AI 决策日志/审计面；wire schema 生成）。

    未知命令/引用面外兜底只记类名（不抛——日志永不阻断对局，旧契约保持）。
    """
    name = type(cmd).__name__
    try:
        d = encode_command(cmd)
    except Exception:
        return {"cmd": name}
    if name == "MoveCmd":
        return {"cmd": name, "unit": d["unit_id"],
                "dest": d["path"][-1] if d["path"] else None,
                "mode": d["mode"], "queue": d["queue"], "path": d["path"]}
    if name == "ReverseCmd":
        return {"cmd": name, "unit": d["unit_id"], "dest": d["dest"]}
    if name in ("StopCmd", "CancelCmd", "DeployCmd", "PackCmd", "ToggleAmbushCmd",
                "CancelFireMissionCmd", "SprintCmd", "UnGarrisonCmd", "DismountCmd"):
        return {"cmd": name, "unit": d["unit_id"]}
    if name == "PivotCmd":
        return {"cmd": name, "unit": d["unit_id"], "facing": d["facing_deg"]}
    if name == "FormationCmd":
        return {"cmd": name, "units": d["units"], "shape": d["shape"]}
    if name == "SetModeCmd":
        return {"cmd": name, "element": d["element"][1], "unit": d["element"][0],
                "mode": d["mode"]}
    if name == "PurchaseCmd":
        t = cmd.template
        out = {"cmd": name, "player_index": d["player_index"],
               "template_id": d["template_id"], "template": t.name, "cost": t.cost}
        if cmd.dest is not None:                       # v1.2 垂足出动目的地
            out["dest"] = [int(cmd.dest[0]), int(cmd.dest[1])]
        return out
    if name == "FireMissionCmd":
        return {"cmd": name, "unit": d["unit_id"], "form": d["form"],
                "point": d["point"], "line": d["line"],
                "ammo_mult": d["ammo_mult"], "ammo": d["ammo"],
                "salvo_mode": d["salvo_mode"],
                "creep_speed": d["creep_speed"]}
    if name == "SmokeCmd":
        return {"cmd": name, "element": d["element"][1], "unit": d["element"][0],
                "pos": d["point"]}
    if name == "SetStanceCmd":
        return {"cmd": name, "unit": d["unit_id"], "stance": d["stance"]}
    if name == "GarrisonCmd":
        return {"cmd": name, "unit": d["unit_id"], "building": d["building_id"]}
    if name == "MountCmd":
        return {"cmd": name, "squads": [uid_e[1] for uid_e in d["squads"]],
                "carrier_unit": d["carrier_unit_id"]}
    if name == "TowCmd":
        return {"cmd": name, "towers": [uid_e[1] for uid_e in d["towers"]],
                "towed": d["towed"][1], "towed_unit": d["towed"][0]}
    if name == "UntowCmd":
        return {"cmd": name, "element": d["element"][1], "unit": d["element"][0]}
    if name == "AttackCmd":
        out = {"cmd": name, "element": d["element"][1], "unit": d["element"][0],
               "target_unit": None, "target_element": None}
        if "target" in d:
            out["target_unit"], out["target_element"] = d["target"]
        else:
            out["target_building_id"] = d["target_building_id"]
        return out
    if name == "SetSniperCoverCmd":
        return {"cmd": name, "sniper": d["sniper_unit_id"],
                "target": d["target_unit_id"]}
    if name == "SetAirdropBeaconCmd":
        return {"cmd": name, "unit": d["unit_id"], "pos": d["pos"]}
    if name == "BuySuppliesCmd":
        return {"cmd": name, "element": d["element"][1], "unit": d["element"][0],
                "rounds": d["rounds"], "medical": d["medical"]}
    if name == "AirCallCmd":
        # 旧 payload 键（BOMB/SUPPLY 整值、PARATROOP=模板名）逐键保持 + 新增
        # paratroop_template_id/air_template_id（允许新增键口径）。
        payload = {}
        wp = d["payload"]
        if "BOMB" in wp:
            payload["BOMB"] = wp["BOMB"]
        if "SUPPLY" in wp:
            payload["SUPPLY"] = wp["SUPPLY"]
        if "paratroop_template_id" in wp:
            v = cmd.payload.get("PARATROOP")
            payload["PARATROOP"] = getattr(v, "name", str(v)) if v is not None else None
        return {"cmd": name, "player_index": d["player_index"],
                "aircraft": cmd.template.name, "payload": payload,
                "air_template_id": d["air_template_id"]}
    if name == "AirMoveCmd":
        return {"cmd": name, "aircraft": d["aircraft_id"],
                "dest": d["path"][-1] if d["path"] else None, "path": d["path"]}
    if name == "AirPatrolCmd":
        return {"cmd": name, "aircraft": d["aircraft_id"], "center": d["center"],
                "radius": d["radius"]}
    if name == "AirAltCmd":
        return {"cmd": name, "aircraft": d["aircraft_id"], "tier": d["tier"]}
    if name == "AirStrikeCmd":
        return {"cmd": name, "aircraft": d["aircraft_id"], "target": d["target"],
                "weapon": d["weapon"], "axis": d["axis"]}
    if name == "AirAirdropCmd":
        return {"cmd": name, "aircraft": d["aircraft_id"], "point": d["drop_point"]}
    if name == "AirEngageAirCmd":
        return {"cmd": name, "aircraft": d["aircraft_id"], "engage": d["engage"]}
    if name in ("AirDisengageCmd", "AirRTBCmd"):
        return {"cmd": name, "aircraft": d["aircraft_id"]}
    if name == "GroundRTBCmd":                                # P1 机制块（wire 1.3）
        return {"cmd": name, "unit": d["unit_id"]}
    if name == "LaserDesignateCmd":
        return {"cmd": name, "designator": d["designator_unit_id"],
                "target": d["target_unit_id"]}
    if name == "RadarCmd":
        return {"cmd": name, "unit": d["unit_id"], "engage": d["engage"]}
    if name == "SupplySwitchCmd":
        return {"cmd": name, "unit": d["unit_id"], "switch": d["switch"],
                "on": d["on"]}
    if name == "AirAfterburnerCmd":
        return {"cmd": name, "aircraft": d["aircraft_id"], "engage": d["engage"]}
    if name == "AirDecoyCmd":
        return {"cmd": name, "aircraft": d["aircraft_id"], "action": d["action"]}
    return {"cmd": name}


# ── 回放文件 v1（JSONL：header / rec:cmd / rec:cksum）──


class ReplayWriter:
    """回放文件写侧：构造即写 header，逐 tick 落 cmd/cksum 记录。

    命令记录口径：tick=入队拍（该拍命令由下一 world_tick 落地）；只记录随
    world_tick 真被消费的命令（录制循环在 world_tick 后回写当拍命令+校验和，
    尾部悬空令不落盘——读侧 tick 悬空即报错，两侧对齐）。
    """

    def __init__(self, path, *, world, seed: int, scenario: str,
                 map_key: str = "none"):
        self.path = str(path)
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        self._fh = open(self.path, "w", encoding="utf-8")
        header = {
            "rec": "header",
            "schema_version": SCHEMA_VERSION,
            "seed": int(seed),
            "phase_ticks": [int(x) for x in CONFIG.phase_ticks],  # 实现现值（tables.py 出表）
            "players_per_team": len(world.players) // 2,
            "map_key": map_key,
            "decks": [[s.template.template_id for s in p.deck_slots]
                      for p in world.players],   # 含 PARATROOP 预备队卡——重建后断言对照面
            "checksum_fn": CHECKSUM_FN_ID,
            "scenario": scenario,
        }
        self._write(header)

    def command(self, tick: int, player_index: int, cmd) -> None:
        self._write({"rec": "cmd", "tick": int(tick),
                     "player_index": int(player_index),
                     "wire": encode_command(cmd)})

    def checksum(self, tick: int, world) -> None:
        self._write({"rec": "cksum", "tick": int(tick),
                     "sum": state_checksum(world)})

    def _write(self, obj: dict) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False,
                                  separators=(",", ":")) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "ReplayWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def load_replay(path) -> tuple[dict, list]:
    """读回放文件 → (header, 记录列表)。fail-fast：未知 schema_version/未知 rec
    类型/校验和函数标识不符/坏 JSON 均带行号报错（格式不符明确报错不静默）。"""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if not lines:
        raise ValueError("回放文件为空：%s" % (path,))
    header = json.loads(lines[0])
    if not isinstance(header, dict) or header.get("rec") != "header":
        raise ValueError("回放首行不是 rec:header：%s" % (path,))
    if header.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("未知 schema_version %r（期望 %r）：%s"
                         % (header.get("schema_version"), SCHEMA_VERSION, path))
    if header.get("checksum_fn") != CHECKSUM_FN_ID:
        raise ValueError("校验和函数标识不符 %r（期望 %r）：%s"
                         % (header.get("checksum_fn"), CHECKSUM_FN_ID, path))
    records = []
    for lineno, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue                                    # 容忍尾空行（JSONL 惯例）
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("回放第 %d 行坏 JSON：%s" % (lineno, exc)) from exc
        rec = obj.get("rec")
        if rec == "cmd":
            if not (isinstance(obj.get("tick"), int)
                    and isinstance(obj.get("player_index"), int)
                    and isinstance(obj.get("wire"), dict)):
                raise ValueError("rec:cmd 字段不全（第 %d 行）：%s" % (lineno, path))
        elif rec == "cksum":
            if not (isinstance(obj.get("tick"), int)
                    and isinstance(obj.get("sum"), int)):
                raise ValueError("rec:cksum 字段不全（第 %d 行）：%s" % (lineno, path))
        else:
            raise ValueError("未知 rec 类型 %r（第 %d 行）：%s" % (rec, lineno, path))
        records.append(obj)
    return header, records


# ── 场景构造器注册表（scenario 名 → "模块:函数" dotted path，importlib 惰性导入）──
# 内联合成卡 template_id=301~307 不在任何数据文件（实卡 101-107/201-203，
# cards_ground.v1.json 实核）——回放世界必须经场景构造器复建；tools 按 PEP 420
# namespace package 从仓库根直接 import（无需 __init__.py，tests/ 四处
# `from tools import` 先例同证）。

SCENARIO_BUILDERS: dict[str, str] = {
    "kev_game_demo.v1": "tools.kev_game_demo:build_world",
}


def resolve_scenario_builder(name: str):
    """scenario 名 → 构造器函数（build_world(seed)→World）。未知名 fail-fast。"""
    dotted = SCENARIO_BUILDERS.get(name)
    if dotted is None:
        raise ValueError("未知 scenario %r（注册表：%s）"
                         % (name, sorted(SCENARIO_BUILDERS)))
    mod_name, _, func_name = dotted.partition(":")
    module = importlib.import_module(mod_name)
    return getattr(module, func_name)


class Replayer:
    """回放器：header 校验→场景重建→一致性断言→逐 tick 施令→world_tick→cksum 核对。

    错位即抛（格式不符明确报错不静默错播）：校验和流必须逐 tick 连续（唯一口径）、
    命令 tick 不得悬空超出校验和窗、逐 tick 指纹不符即报「回放损坏或仿真非确定」。

    增量会话 API（FE-T06 观战器消费）：open() 重建世界并归零游标；advance(target)
    现场逐 tick 推进到目标拍（逐拍核对校验和，不预存全量帧序列——单一事实源=
    命令流）；seek(target) 任意方向定位——回退取 ≤target 的最近检查点（每 600 拍
    deepcopy 快照，CHECKPOINT_EVERY）重放推导至目标，检查点可随时从命令流重建
    （丢弃即重建，正确性不依赖快照——恢复段照常逐拍核对校验和）。
    """

    def __init__(self, path):
        self.path = str(path)
        self.header, self.records = load_replay(self.path)
        self.commands: dict[int, list] = {}     # tick → [(player_index, wire)]
        self.checksums: dict[int, int] = {}     # tick → sum
        for obj in self.records:
            if obj["rec"] == "cmd":
                self.commands.setdefault(obj["tick"], []).append(
                    (obj["player_index"], obj["wire"]))
            else:
                if obj["tick"] in self.checksums:
                    raise ValueError("tick %d 重复校验和记录：%s"
                                     % (obj["tick"], self.path))
                self.checksums[obj["tick"]] = obj["sum"]
        self.ticks = sorted(self.checksums)
        # 逐 tick 唯一口径：cksum 流必须恰为 1..N 连续（杜绝抽稀流冒充逐 tick）
        if self.ticks != list(range(1, len(self.ticks) + 1)):
            raise ValueError("校验和流非逐 tick 连续 1..%d（首末 %r..%r）：%s"
                             % (len(self.ticks),
                                self.ticks[:1], self.ticks[-1:], self.path))
        # 尾令悬空（入队拍 ≥ 校验和窗末拍=永不被施放）即报错
        if self.commands:
            max_cmd_tick = max(self.commands)
            if max_cmd_tick >= self.ticks[-1]:
                raise ValueError("命令 tick %d 悬空超出校验和窗（末拍 %d）：%s"
                                 % (max_cmd_tick, self.ticks[-1], self.path))
        # 增量会话态（open() 后有效；run() 每次自建会话不共享）
        self.world = None
        self.cursor = 0
        self._checkpoints: dict[int, object] = {}

    def build(self):
        """按 header.scenario 重建世界 + 一致性断言（对不上即报错）。"""
        builder = resolve_scenario_builder(self.header["scenario"])
        world = builder(int(self.header["seed"]))
        if tuple(self.header["phase_ticks"]) != tuple(CONFIG.phase_ticks):
            raise ValueError("phase_ticks 不符：文件 %r vs 现值 %r（配置漂移）"
                             % (self.header["phase_ticks"], CONFIG.phase_ticks))
        if len(world.players) != 2 * int(self.header["players_per_team"]):
            raise ValueError("players 数不符：重建 %d vs 文头 %d"
                             % (len(world.players), 2 * self.header["players_per_team"]))
        if self.header["map_key"] != "none":
            raise ValueError("v1 仅支持 map_key='none'（挂图场景待后续版本）")
        if world.terrain is not None:
            raise ValueError("map_key='none' 但场景带地形层（对不上即报错）")
        decks = [[s.template.template_id for s in p.deck_slots]
                 for p in world.players]
        if decks != self.header["decks"]:
            raise ValueError("deck template_id 清单不一致：重建 %r vs 文头 %r"
                             % (decks, self.header["decks"]))
        return world

    # ── 增量会话 API（FE-T06 观战器：seek=重放推导，检查点仅加速）──

    def open(self):
        """打开增量会话：重建世界、游标归零、清空检查点。"""
        self.world = self.build()
        self.cursor = 0
        self._checkpoints = {0: None}       # tick → world 快照（0=None 占位=重建即得）
        return self.world

    def _require_session(self):
        if self.world is None:
            raise ValueError("Replayer 会话未 open（先 open()/run()）")

    def _step_one(self):
        """游标拍 → 下一拍：施放入队令→world_tick→核对校验和→记检查点。"""
        for _pi, wire_dict in self.commands.get(self.cursor, ()):
            queue_command(self.world, decode_command(self.world, wire_dict))
        world_tick(self.world)
        self.cursor += 1
        if self.world.tick != self.cursor:
            raise ValueError("tick 错位：重放 %d vs 记录 %d"
                             % (self.world.tick, self.cursor))
        got = state_checksum(self.world)
        want = self.checksums[self.cursor]
        if got != want:
            raise ValueError("tick %d 校验和不一致：重放 %d ≠ 记录 %d"
                             "（回放损坏或仿真非确定）" % (self.cursor, got, want))
        if (self.cursor % CHECKPOINT_EVERY == 0
                and self.cursor not in self._checkpoints):
            # deepcopy 快照：模板/元素/武器态/弹丸/PCG32 内部 state 全图拷贝
            self._checkpoints[self.cursor] = copy.deepcopy(self.world)

    def advance(self, target: int, *, on_tick=None) -> int:
        """现场逐 tick 推进到目标拍（含端点；夹取 [0, 末拍]），返回到达拍。

        推进即校验：途经每拍都核对校验和（增量与会话=同一确定性重放，不因
        分段而放宽）。on_tick(world) 每拍回调（观战器逐拍产状态帧的钩子位）。
        """
        self._require_session()
        target = max(0, min(int(target), self.ticks[-1]))
        while self.cursor < target:
            self._step_one()
            if on_tick is not None:
                on_tick(self.world)
        return self.cursor

    def seek(self, target: int, *, on_tick=None) -> int:
        """任意方向定位到目标拍（回退=最近检查点重放推导；前进=advance）。"""
        self._require_session()
        target = max(0, min(int(target), self.ticks[-1]))
        if target >= self.cursor:
            return self.advance(target, on_tick=on_tick)
        # 回退：取 ≤target 的最近检查点恢复（快照可丢弃重建——恢复段逐拍校验）
        base = max(t for t in self._checkpoints if t <= target)
        snap = self._checkpoints[base]
        self.world = self.build() if snap is None else copy.deepcopy(snap)
        self.cursor = base
        if snap is not None and self.world.tick != base:      # 快照自证（防错存）
            raise ValueError("检查点 tick 自证失败：快照 %d vs 键 %d"
                             % (self.world.tick, base))
        return self.advance(target, on_tick=on_tick)

    def run(self, *, on_tick=None):
        """全量重放：逐 tick 施令→world_tick→核对校验和（与原局逐 tick 一致）。

        每次调用自建增量会话（open→advance 末拍），重复调用互不串态。
        """
        self.open()
        self.advance(self.ticks[-1], on_tick=on_tick)
        return self.world
