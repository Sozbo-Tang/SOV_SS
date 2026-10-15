"""空呼花名册装配（GP-01 §4/交互重设计 A9）：增冷却在空态。

结论先行：本模块自 tools/skirmish_shell.py 时代的 session.air_roster 装配体
迁入 sovs/app 会话胶水层（§5.3 拆包）并按 GP-01 §4 ①段扩面——roster 条目
增 cooldown_ticks（players.air_cooldowns 帧/对象面——「打完回卡池再呼入」的
冷却可视化）与 in_air（该机型当前在空架数——「呼了没」不再靠找地图）；
点数预判（affordable）沿用交互重设计 A9 口径：生成处预判，引擎门仍为最终权威。

冷却口径：cooldown_ticks>0 时 affordable=False（UI 灰显；cmd_air_call 的
cooldown 门 air.py:396 同源——预判只做呈现，不替代裁决）。
"""
from __future__ import annotations

from sovs.sim.types import UnitFlag


def build_air_roster(world, human_index: int, human_deck: str) -> list[dict]:
    """空呼按钮数据（按卡组阵营取册 air_data.CARD_OBJECTS）。

    交互重设计 A9：生成处预判点数——entry 携带 cost（本呼叫总价）与
    affordable（players[].air_points 是否够付；修旧 max(1,..) 缺陷：点数不足
    时不再虚标 1 弹，n_bomb=0 直接 affordable=False 灰显）。
    GP-01 §4：+cooldown_ticks（冷却剩余 tick，>0 灰显）+in_air（在空架数）。
    """
    from sovs.ai.actions import TEAM_AIR_KEYS      # 惰性（ai 包重，门禁路径不引）
    from sovs.sim.air_data import CARD_OBJECTS

    team = 0 if human_deck in ("su_min",) or _faction_is_soviet(human_deck) else 1
    p = world.players[human_index]
    own_in_air: dict[int, int] = {}
    for a in world.aircraft:
        if a.team == p.team:
            own_in_air[a.template.template_id] = (
                own_in_air.get(a.template.template_id, 0) + 1)
    out = []
    for key in TEAM_AIR_KEYS[team]:
        tpl = CARD_OBJECTS[key]
        tid = tpl.template_id
        cooldown = int(p.air_cooldowns.get(tid, 0))
        in_air = own_in_air.get(tid, 0)
        role = tpl.role.name
        if role in ("ATTACK", "BOMBER"):
            # 2026-10-14 空袭按用计费块：满载呼叫（弹费投放时逐发扣 air_points，
            # 不进呼叫价/点数门——payload_price["BOMB"]=单价在空中选中卡标示）
            n_bomb = tpl.payload_max_bombs
            payload = {"BOMB": n_bomb}
            cost = tpl.cost_body
            out.append({"key": "call_%s" % key.lower(),
                        "label": "呼%s×%d弹" % (tpl.name, n_bomb),
                        "template": tpl, "payload": payload,
                        "cost": cost, "cooldown_ticks": cooldown,
                        "in_air": in_air,
                        "affordable": n_bomb > 0
                        and p.air_points >= cost and cooldown <= 0})
        elif role in ("FIGHTER", "RECON"):
            out.append({"key": "call_%s" % key.lower(), "label": "呼%s" % tpl.name,
                        "template": tpl, "payload": {},
                        "cost": tpl.cost_body, "cooldown_ticks": cooldown,
                        "in_air": in_air,
                        "affordable": (p.air_points >= tpl.cost_body
                                       and cooldown <= 0)})
        else:                                   # TRANSPORT
            reserve = any(s.template.flags & UnitFlag.DELIVERY_AIRDROP_ONLY
                          and s.copies_left > 0 for s in p.deck_slots)
            if reserve:
                out.append({"key": "call_troop_%s" % key.lower(),
                            "label": "呼%s装伞兵" % tpl.name,
                            "template": tpl, "payload": {"PARATROOP": True},
                            "cost": tpl.cost_body, "cooldown_ticks": cooldown,
                            "in_air": in_air,
                            "affordable": (p.air_points >= tpl.cost_body
                                           and cooldown <= 0)})
            price = tpl.payload_price.get("SUPPLY", 0)
            max_sup = tpl.payload_max_supply if price <= 0 else min(
                tpl.payload_max_supply,
                max(0, (p.air_points - tpl.cost_body) // price))
            if max_sup > 0:
                cost = tpl.cost_body + price * max_sup
                out.append({"key": "call_supply_%s" % key.lower(),
                            "label": "呼%s补给%d" % (tpl.name, max_sup),
                            "template": tpl, "payload": {"SUPPLY": max_sup},
                            "cost": cost, "cooldown_ticks": cooldown,
                            "in_air": in_air,
                            "affordable": p.air_points >= cost and cooldown <= 0})
    return out


def _faction_is_soviet(deck_key: str) -> bool:
    """自制卡组阵营判定（读编译产物 faction 位——0=SOVIET/1=GERMAN；缺省苏）。"""
    import json
    import os

    from sovs.app.session import GEN_DECK_DIR
    path = os.path.join(GEN_DECK_DIR, "%s.json" % deck_key)
    try:
        with open(path, encoding="utf-8") as f:
            return int(json.load(f).get("faction", 0)) == 0
    except (OSError, ValueError):
        return True


def cooldown_labels(world, human_index: int, roster: list[dict]) -> list[tuple]:
    """冷却段数据（顶栏 HUD 消费面）：[(机型名, 剩余秒)]，仅未到期条目。"""
    p = world.players[human_index]
    name_by_tid = {e["template"].template_id: e["template"].name
                   for e in roster}
    out = []
    for tid, ticks in sorted(p.air_cooldowns.items()):
        if ticks > 0:
            out.append((name_by_tid.get(tid, "#%d" % tid), (ticks + 9) // 10))
    return out
