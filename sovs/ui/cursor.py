"""FE-05 F8 上下文光标：cur_default/select/attack/target/move 按上下文切换，
热点读 assets/fe/cursor/hotspots.json。

结论先行：arcade 3.3 无公开光标 API（pyglet ImageMouseCursor 直构在无显示
会话段错误——实测定档），按 F8 规格「无光标 API 时用绘制替代并留痕」执行：
**绘制光标**——render_page 末段以 cur_<kind> 贴图在鼠标位（减热点偏移）
叠加绘制，并置系统光标不可见（set_mouse_visible——pyglet 继承面，失败不
致命）。kind 判据=纯逻辑 context_kind（待令族/待放卡/悬停己方单位）。
本模块只 import arcade＋stdlib＋本包 assets（禁 sovs.sim/sovs.ai/PIL）。
"""
from __future__ import annotations

import json

import arcade

from . import assets

_DEFAULT_HOTSPOT = (12, 12)           # 缺省热点（24px 图居中）
_hotspots = None
_last_kind: dict = {}                 # id(win) → kind（避免每帧重设）


def hotspots() -> dict:
    """光标热点表（{"cur_default": [x, y], ...}——懒加载一次，缺文件空表）。"""
    global _hotspots
    if _hotspots is None:
        try:
            import os
            path = os.path.join(assets._ROOT, "assets", "fe", "cursor",
                                "hotspots.json")
            with open(path, encoding="utf-8") as f:
                _hotspots = json.load(f)
        except (OSError, ValueError):
            _hotspots = {}
    return _hotspots


# 待令族 → 光标型（attack=攻击族；target=目标指定族；move=机动族）
_ATTACK_ORDERS = {"attack"}
_TARGET_ORDERS = {"fire_mission", "strike", "drop", "laser", "precision",
                  "sniper", "supply", "mount", "unload"}
_MOVE_ORDERS = {"reverse", "march"}


def context_kind(win) -> str:
    """光标型判据（纯逻辑）：default/select/attack/target/move。"""
    fsm = getattr(win, "fsm", None)
    if fsm is None or getattr(fsm, "page", None) not in ("deploy", "battle"):
        return "default"
    armed = getattr(fsm, "armed_order", None)
    if armed in _ATTACK_ORDERS:
        return "attack"
    if armed in _TARGET_ORDERS or getattr(fsm, "armed_purchase", None):
        return "target"
    if armed in _MOVE_ORDERS:
        return "move"
    mouse = getattr(win, "_mouse_xy", None)
    if mouse is not None:
        from . import scene
        try:
            if scene.hit_unit(win, mouse[0], mouse[1], team="own") \
                    or scene.hit_aircraft(win, mouse[0], mouse[1]):
                return "select"
        except Exception:                          # noqa: BLE001（鸭子窗兜底）
            return "default"
    return "default"


def _tex(kind: str):
    return assets.cursor_tex("cur_%s" % kind)


def draw_cursor(win) -> None:
    """绘制光标（render_page 末段调用——系统光标隐藏的替代面）。

    无鼠标位（截图/无头）不画；缺贴图不画（系统光标兜底）；系统光标隐藏
    失败（无 API/无窗）留痕不致命。
    """
    mouse = getattr(win, "_mouse_xy", None)
    if mouse is None:
        return
    kind = context_kind(win)
    tex = _tex(kind) or _tex("default")
    if tex is None:
        return                                     # 资产缺——系统光标兜底
    if _last_kind.get(id(win)) != kind:
        _last_kind[id(win)] = kind
        try:
            win.set_mouse_visible(False)           # 隐藏系统箭头（pyglet 继承面）
        except Exception:                          # noqa: BLE001（留痕不致命）
            pass
    hs = hotspots().get("cur_%s" % kind, _DEFAULT_HOTSPOT)
    size = max(tex.size)
    arcade.draw_texture_rect(tex, arcade.XYWH(mouse[0] - hs[0] + size / 2,
                                              mouse[1] - hs[1] + size / 2,
                                              size, size))
