"""改键设置存取（2026-10-14 设置改键块——manual.txt:91,544-545「键位可在设置
菜单中修改」的运行时承载；原 deviated #38 翻面 done）。

数据文件=SETTINGS_PATH（data/gen/keybinds.json：语义名→arcade 物理键码，仅存
被改动项）；默认表=shell_window._build_key_names 字面表（手册 HOTKEYS 锚的源码
解析锚，不在此复制——加载时叠加覆盖）。可改键面=COMBAT_KEYS 22 命令槽；保留
物理键（相机 WASD/方向键/TAB/数字编组/ESC/F1 帮助/SPACE 暂停/±调速）不得改绑；
目标键仅限字母；已被其他命令占用→拒绝（先改开占用者）。路径面=ALLOWED_DIR
containment 单点校验（Mimosa 路径穿越防线）；本模块不 import sovs.sim（AST
守卫②）。
"""
from __future__ import annotations

import json
from pathlib import Path

import arcade

from .shell_fsm import COMBAT_KEYS

ALLOWED_DIR = Path("data") / "gen"
SETTINGS_PATH = ALLOWED_DIR / "keybinds.json"

# 保留物理键（改键目标黑名单——既有系统键位面：相机/页面/帮助/暂停/调速/编组）
_RESERVED = frozenset(
    [arcade.key.ESCAPE, arcade.key.F1, arcade.key.SPACE, arcade.key.TAB,
     arcade.key.EQUAL, arcade.key.MINUS, arcade.key.NUM_ADD,
     arcade.key.NUM_SUBTRACT, arcade.key.UP, arcade.key.DOWN,
     arcade.key.LEFT, arcade.key.RIGHT, arcade.key.W, arcade.key.A,
     arcade.key.S, arcade.key.D]
    + [getattr(arcade.key, "KEY_%d" % d) for d in range(10)])


def _settings_path() -> Path:
    """containment 校验（Mimosa 路径穿越防线）：解析后必须仍位于 ALLOWED_DIR
    （字面 data/gen）之内，越界即拒。测试注入 tmp 时须同步 monkeypatch
    ALLOWED_DIR 与 SETTINGS_PATH 两常量。"""
    p = SETTINGS_PATH.resolve()
    if p.parent != ALLOWED_DIR.resolve():
        raise ValueError("settings 文件越出允许目录 %s：%s"
                         % (ALLOWED_DIR, SETTINGS_PATH))
    return p


def load_overrides() -> dict[str, int]:
    """读改键覆盖（语义名→物理键码）；文件缺失/损坏=无覆盖（默认表裸跑）。
    containment 越界的 ValueError 不吞（显式拒——只吞文件级缺失/坏 JSON）。"""
    try:
        p = _settings_path()
    except ValueError:
        raise
    try:
        with p.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for name, code in raw.items():
        if name in COMBAT_KEYS and isinstance(code, int):
            out[name] = code
    return out


def save_overrides(mapping: dict[str, int]) -> None:
    """写改键覆盖（仅被改动项；空表=恢复默认不留文件残骸）。"""
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(dict(sorted(mapping.items())), fh, ensure_ascii=False,
                  indent=1)


def reset_all() -> None:
    """清空全部改键（恢复默认表——文件删除而非写空，留痕面最干净）。"""
    try:
        _settings_path().unlink()
    except OSError:
        pass


def assign(slot: str, key_code: int) -> tuple[bool, str]:
    """把 slot（COMBAT_KEYS 语义名）改绑到 key_code：校验→合并覆盖→落盘。
    返回 (是否成功, 人读消息)——失败不落盘。"""
    if slot not in COMBAT_KEYS:
        return False, "未知命令槽 %s" % slot
    if key_code in _RESERVED:
        return False, "保留键（相机/编组/系统）不可改绑"
    if not (65 <= key_code <= 90):
        return False, "改键目标仅支持字母键"
    overrides = load_overrides()
    key_code = int(key_code)
    if overrides.get(slot) == key_code:
        return True, "未变化"
    for other, code in overrides.items():
        if other != slot and code == key_code:
            return False, "%s 已被 %s 占用——先改开它再绑" % (chr(key_code),
                                                            other)
    # 该槽原覆盖键（若有）自然被替换；默认键码不主动释放（双触发面由
    # shell_window._build_key_names 覆盖层删除——以覆盖表为唯一事实源）
    overrides[slot] = key_code
    save_overrides(overrides)
    return True, "%s → %s（已保存）" % (slot, chr(key_code))


def display_map(overrides: dict[str, int] | None = None) -> dict[str, str]:
    """命令槽→当前显示字符（未改绑=槽位名本身；改绑=新键字母）。"""
    ov = load_overrides() if overrides is None else overrides
    out = {slot: slot for slot in COMBAT_KEYS}
    for slot, code in ov.items():
        if 65 <= code <= 90:
            out[slot] = chr(code)
    return out


def sub(text: str, overrides: dict[str, int] | None = None) -> str:
    """键位速查文案渲染：{Q}/{S}… 槽位 token → 当前显示字符（改键动态面）。"""
    return text.format(**display_map(overrides))
