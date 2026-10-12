"""态势摘要：World → Kev 决策服务的结构化 state（AI 视角裁剪 + 迷雾过滤）。

设计口径（照调研报告拍板的分层架构：引擎管事实，模型管选择）：
- **只给模型看它该看的**：己方全量、敌方仅经 spotted_mask 过滤后的可见单位、
  占点归属全图可见（占点是公开信息）——**迷雾过滤不自实现**：2026-10-11
  FE-T02 起统一收拢为 sim 公共状态帧（sovs/sim/state_frame.py state_frame，
  迷雾唯一事实源 types.py spotted_mask 的唯一裁剪点），本模块在本帧之上做
  **AI 摘要档**：截断（max_units/飞机/建筑上限——state 过长只会白付前向
  算力，SERVE_MAX_STATE 上限服务端 422 拒收）+整米化（cm//100 截断不四舍
  五入——模型不做小数算术；整米化是本档行为，公共帧保持 int cm，见
  state_frame.py 头注）+中文字段名。
- **整数纪律在边界保持**：坐标转米、距离 math.isqrt 欧氏整根、弹药/血量
  取整数百分比。

输出为纯 dict/list/str/int（kev.api.render 会展平成带标签文本喂模型）。
"""
from __future__ import annotations

import math

from sovs.sim.state_frame import state_frame

# 兵种类别码 → 中文（帧 units[].category 为 int 码；0 侦察/1 步兵/2 装甲/
# 3 火支/4 防空后勤——中文名是 AI 摘要档行为）
_CATEGORY_NAME = {0: "侦察", 1: "步兵", 2: "装甲", 3: "火力支援", 4: "防空/后勤"}

# 姿态码 → 中文（帧 stance 为枚举名小写；中文是 AI 摘要档行为）
_STANCE_NAME = {"weapons_free": "自由射击", "hold_fire": "禁火"}


def _dist_cm(a, b) -> int:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.isqrt(dx * dx + dy * dy)


def _my_player(frame, player_index: int) -> dict:
    """帧 players 段中取指定玩家条目（队视角帧恒含本队全部玩家）。"""
    return next(p for p in frame["players"] if p["index"] == player_index)


def _unit_entry(u: dict) -> dict:
    """己方单位条目（紧凑；hp=元素血量和/满值和，ammo=最紧武器弹量百分比）。"""
    return {
        "id": u["id"],
        "name": u["name"],
        "category": _CATEGORY_NAME.get(u["category"], "?"),
        "pos_m": [u["pos_cm"][0] // 100, u["pos_cm"][1] // 100],
        "hp": u["hp"],
        "hp_max": u["hp_max"],
        "ammo_pct": u["ammo_pct"],
        "moving": u["moving"],
        "stance": _STANCE_NAME.get(u["stance"], u["stance"]),
        "morale": u["morale"],
        "suppressed": u["suppressed"],
        "mounted": u["mounted"],
        "garrisoned": u["garrisoned"],
        "towed": u["towed"],
        "smoke_left": u["smoke_left"],
    }


def _enemy_entry(u: dict, my_units) -> dict:
    """可见敌单位条目（dist_m=距我最近单位的整米距离；未知量不上报）。"""
    dist = min((_dist_cm(u["pos_cm"], m["pos_cm"]) for m in my_units), default=0)
    return {
        "id": u["id"],
        "name": u["name"],
        "category": _CATEGORY_NAME.get(u["category"], "?"),
        "pos_m": [u["pos_cm"][0] // 100, u["pos_cm"][1] // 100],
        "dist_m": dist // 100,
    }


def compact_brief(world, player_index: int, *, max_units: int = 4) -> str:
    """紧凑单行文本态势（Kev-0.5B 档 384 token state 预算内——约 250 token）。

    行式纯文本（kev.api.render 对字符串原样透传）：数字走 ASCII 便宜token、
    中文词密压缩、每方单位截断 max_units、空段不出现。丰富结构面（dict
    全字段）用 situation_brief——大上下文模型（4B/9B，state 8k+）适用。
    迷雾/占点/空军取数一律经 state_frame 帧（见头注）。
    """
    frame = state_frame(world, player_index)
    my_team = frame["view"]
    p = _my_player(frame, player_index)
    mine = [u for u in frame["units"] if u["team"] == my_team][:max_units]
    foes = [u for u in frame["units"] if u["team"] != my_team][:max_units]
    parts = [f"t{frame['tick']} {frame['phase']}"]
    parts.append("我方" + (";".join(
        f"{u['id']}{u['name']}({u['pos_cm'][0] // 100},{u['pos_cm'][1] // 100}m)"
        f"hp{u['hp']}"
        f"/{u['hp_max']}"
        f"{'动' if u['moving'] else '静'}"
        f"{'压' if u['suppressed'] else ''}"
        for u in mine) or "无"))
    if foes:
        parts.append("敌见" + ";".join(
            f"{u['id']}{u['name']}({u['pos_cm'][0] // 100},{u['pos_cm'][1] // 100}m)"
            f"距{min((_dist_cm(u['pos_cm'], m['pos_cm']) for m in mine), default=0) // 100}m"
            for u in foes))
    if frame["objectives"]:
        parts.append("占点" + ";".join(
            f"{o['id']}号({o['pos_cm'][0] // 100},{o['pos_cm'][1] // 100}m)"
            + ("无主" if o["owner"] is None else f"队{o['owner']}")
            for o in frame["objectives"][:3]))
    mine_air = [a for a in frame["aircraft"] if a["team"] == my_team][:3]
    parts.append(f"空援{p['air_points']}在空{len(mine_air)}"
                 + ("".join(
                     f";{a['id']}{a['name']}{a['state'][0]}"
                     f"弹{a['ammo'].get('BOMB', 0)}"
                     + ("载伞" if a["paratroop"] is not None else "")
                     for a in mine_air)))
    para = sum(s["copies_left"] for s in p["deck"] if s["airdrop"])
    if para:
        parts.append(f"预备队{para}份")
    return " | ".join(parts)


def situation_brief(world, player_index: int, *, max_units: int = 16) -> dict:
    """构造给定玩家视角的态势 state（纯数据，可直接 json.dumps）。

    全量字段与迷雾裁剪经 state_frame 公共帧（唯一实现）；本函数只做 AI
    摘要档三件事：截断（每方 max_units、飞机 8、建筑 4）、整米化、中文
    字段名。max_units 是 AI 档行为——公共契约不截断（FE-T02 契约②）。
    """
    frame = state_frame(world, player_index)
    my_team = frame["view"]
    p = _my_player(frame, player_index)
    # 帧内 units 已含迷雾过滤（己方全量+敌方 spotted）；此处按队切片再截断
    my_units = [u for u in frame["units"] if u["team"] == my_team][:max_units]
    foes = [u for u in frame["units"] if u["team"] != my_team]
    foe_units = foes[:max_units]
    objectives = [{
        "id": o["id"],
        "pos_m": [o["pos_cm"][0] // 100, o["pos_cm"][1] // 100],
        "owner": "none" if o["owner"] is None else f"team{o['owner']}",
    } for o in frame["objectives"]]
    mine_air = [a for a in frame["aircraft"] if a["team"] == my_team][:8]
    foe_air_n = sum(1 for a in frame["aircraft"] if a["team"] != my_team)
    return {
        "局面": {
            "tick": frame["tick"],
            "phase": frame["phase"],
            "地图宽m": frame["map_cm"][0] // 100,
            "地图高m": frame["map_cm"][1] // 100,
        },
        "我方": {
            "player": player_index,
            "team": my_team,
            "购卡点数": p["points"],
            "空援点数": p["air_points"],
            "单位数": len(my_units),
            "单位列表": [_unit_entry(u) for u in my_units],
        },
        "空军": {
            "空援点数": p["air_points"],
            "在空架数": len(mine_air),
            "飞机": [{"id": a["id"], "name": a["name"],
                      "状态": a["state"],
                      "高度": a["alt_tier"],
                      "炸弹": a["ammo"].get("BOMB", 0),
                      "扫射弹": a["ammo"].get("STRAFE", 0),
                      "补给": a["ammo"].get("SUPPLY", 0),
                      "载预备队": a["paratroop"] is not None}
                     for a in mine_air],
            "可见敌机": foe_air_n,
        },
        "预备队": {
            "空降卡余份": sum(s["copies_left"] for s in p["deck"]
                             if s["airdrop"]),
        },
        "建筑": [{"id": b["id"], "pos_m": [b["pos_cm"][0] // 100,
                                           b["pos_cm"][1] // 100],
                  "余位": b["slots_free"]}
                 for b in frame["buildings"][:4]],
        "可见敌军": {
            "数量": len(foe_units),
            "单位列表": [_enemy_entry(u, my_units) for u in foe_units],
        },
        "占点": objectives,
    }
