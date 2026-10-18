"""场景配置加载（R5 场景骨架）：data/scenarios/*.json → dict（fail-fast 校验）。

结论先行：场景=「地图 + 目标点 + 出生车道 + 简报/推荐卡组 + decor（R6 视觉
专用，sim 不读）」的装配描述。本模块属 sovs/app 会话胶水层（可 import
sovs.sim——但本模块只读 JSON 做结构校验，不触仿真）。校验门：必需键、
objectives id 唯一/radius>0/坐标在图幅内（读对应 gen JSON 的 extent）、
map 产物文件存在。缺文件/坏结构一律 raise（fail-fast——card_loader
「缺一键即报错」同款纪律）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = _ROOT / "data" / "scenarios"

_REQUIRED_KEYS = ("schema_version", "scenario_key", "name", "map_key",
                  "briefing", "objectives", "spawn")
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_]+$")


class ScenarioError(ValueError):
    """场景配置加载/校验错误。"""


def _scenario_path(key: str) -> Path:
    if not isinstance(key, str) or not _SAFE_KEY.fullmatch(key):
        raise ScenarioError(f"scenario_key {key!r} 非法（空/非法字符）")
    return SCENARIO_DIR / f"{key}.json"


def _extent_of_map(map_key: str) -> tuple[int, int]:
    from sovs.sim.map_loader import load_map_by_key
    return load_map_by_key(map_key).extent


def load_scenario(key: str = "bagration_field") -> dict:
    """读+校验场景配置（返回整 dict；decor 原样透传——R6 消费面）。"""
    path = _scenario_path(key)
    if not path.is_file():
        raise ScenarioError(f"场景文件缺失：{path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ScenarioError(f"{path.name} 不是合法 JSON：{exc}") from exc
    if not isinstance(doc, dict):
        raise ScenarioError(f"{path.name} 根必须为对象")
    for k in _REQUIRED_KEYS:
        if k not in doc:
            raise ScenarioError(f"{path.name} 缺必需键 {k!r}")
    if doc.get("scenario_key") != key:
        raise ScenarioError(f"{path.name} scenario_key={doc.get('scenario_key')!r}"
                            f" 与文件名 {key!r} 不一致")
    map_key = doc["map_key"]
    if not isinstance(map_key, str) or not _SAFE_KEY.fullmatch(map_key):
        raise ScenarioError(f"{path.name} map_key={map_key!r} 非法")
    if not (_ROOT / "data" / "gen" / f"{map_key}.v1.json").is_file():
        raise ScenarioError(f"{path.name} 地图产物缺失：data/gen/{map_key}.v1.json"
                            "（先跑 python3 tools/build_map.py）")
    ex, ey = _extent_of_map(map_key)
    objs = doc["objectives"]
    if not isinstance(objs, list) or not objs:
        raise ScenarioError(f"{path.name} objectives 须为非空 list")
    ids = set()
    for i, o in enumerate(objs):
        where = f"{path.name} objectives[{i}]"
        if not isinstance(o, dict):
            raise ScenarioError(f"{where} 必须为对象")
        for k in ("id", "name", "pos_cm", "radius_cm"):
            if k not in o:
                raise ScenarioError(f"{where} 缺键 {k!r}")
        oid, radius = o["id"], o["radius_cm"]
        pos = o["pos_cm"]
        if type(oid) is not int or oid in ids:
            raise ScenarioError(f"{where} id={oid!r} 非 int 或重复")
        ids.add(oid)
        if not isinstance(pos, list) or len(pos) != 2 \
                or any(type(v) is not int for v in pos):
            raise ScenarioError(f"{where} pos_cm={pos!r} 须为 [int, int]")
        if type(radius) is not int or radius <= 0:
            raise ScenarioError(f"{where} radius_cm={radius!r} 须为正 int")
        if not (0 <= pos[0] < ex and 0 <= pos[1] < ey):
            raise ScenarioError(f"{where} 坐标 {pos} 越界（图幅 {ex}×{ey}）")
    briefing = doc["briefing"]
    if not isinstance(briefing, list) or not briefing \
            or not all(isinstance(b, str) and b for b in briefing):
        raise ScenarioError(f"{path.name} briefing 须为非空字符串列表")
    spawn = doc["spawn"]
    if not isinstance(spawn, dict) or "lane_y_cm" not in spawn:
        raise ScenarioError(f"{path.name} spawn 缺 lane_y_cm")
    return doc


def list_scenarios() -> list[str]:
    """在册场景键（扫 data/scenarios/*.json，文件名序）。"""
    if not SCENARIO_DIR.is_dir():
        return []
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.json"))
