"""FE-05 F1 单位贴图渲染：战场逐卡俯视图 + 字形矢量回退。

结论先行：本模块是战场单位/飞机的**贴图呈现面**——ground=48px 逐卡俯视图
（index.units[template_id]）＋队色 1.12 倍底衬＋overlay 三态＋hp_bar 裁宽；
air=40px（index.air[template_id]，facing 旋转）。缺任何图 → glyphs 字形
原行为回退（零图片纪律的兜底面，截图门禁不因缺图崩）。本模块只 import
arcade＋本包 assets/glyphs/palette（禁 sovs.sim/sovs.ai——AST 守卫②），
画法参数全部由调用方自 dict 状态帧取值传入。

旋转口径：facing 0°=北、顺时针（帧口径）；贴图机头朝北起步，arcade 角度
逆时针 → angle = -(facing + 视图旋转角)；视图旋转由 win.cam_rot 惰性取值
（无槽窗口=0，与旧链一致）。
"""
from __future__ import annotations

import arcade

from . import assets
from .glyphs import draw_aircraft_glyph, draw_unit_glyph
from .nameplate import draw_nameplate
from .palette import TEAM_COLORS, UNOWNED_COLOR

_UNIT_PX = 48          # 地面单位贴图边长（px）
_UNIT_EDGE_PX = 54     # 队色底衬边长（48×1.12≈54——四舍入整）
_AIR_PX = 40           # 航空器贴图边长（px）
_HP_BAR_H = 3          # 血条高（px——hp_bar.png 原比例 20×3）

_hp_crop_cache: dict = {}


def _team_rgb(team):
    c = TEAM_COLORS.get(int(team), UNOWNED_COLOR)
    return arcade.types.Color(c[0], c[1], c[2])


def _cam_rot(win) -> float:
    return float(getattr(win, "cam_rot", 0.0) % 360.0)


def _hp_bar_pair(pct: int):
    """(底条, 裁宽填充条) 贴图对；pct 夹 0..100；缺图 → (None, None)。

    裁宽缓存键=(cache_name, 宽px)——hp 连续变化按整像素档复用，不逐帧建。
    """
    base = assets.overlay_tex("hp_bar")
    if base is None:
        return None, None
    pct = max(0, min(100, int(pct)))
    w = max(1, round(base.size[0] * pct / 100))
    key = (base.cache_name, w)
    fill = _hp_crop_cache.get(key)
    if fill is None:
        fill = base.crop(0, 0, w, base.size[1])
        _hp_crop_cache[key] = fill
    return base, fill


def draw_ground_unit(win, u: dict, px: float, py: float) -> None:
    """地面单位：逐卡贴图＋队色底衬＋overlay 态＋hp_bar；缺图回退字形。

    地面无 facing（帧档不含），不旋转；selected 判据=win.fsm.selected 成员
    （观战窗无 fsm 槽时 getattr 兜底空元组=恒 False，回退字形路径同口径）。
    """
    tex = assets.unit_tex_by_id(u.get("template_id"))
    hp, hp_max = u.get("hp", 0), u.get("hp_max", 0)
    pct = (hp * 100 // hp_max) if hp_max > 0 else 0
    selected = u.get("id") in getattr(getattr(win, "fsm", None), "selected", ())
    if tex is None:                       # 缺图回退：glyphs 原行为逐位一致
        draw_unit_glyph(px, py, category=u["category"], team=u["team"],
                        hp_pct=pct, suppressed=u["suppressed"],
                        moving=u["moving"], selected=selected)
    else:
        # 队色描边（1.12 倍同图 tinted 半透明）＋本体 48px
        arcade.draw_texture_rect(tex, arcade.XYWH(px, py, _UNIT_EDGE_PX,
                                                  _UNIT_EDGE_PX),
                                 color=_team_rgb(u["team"]), alpha=180)
        arcade.draw_texture_rect(tex, arcade.XYWH(px, py, _UNIT_PX, _UNIT_PX))
        # overlay 三态：资产是**小尺寸角标/箭头**（12×12/12×8/8×8），不得拉满
        # 48px——拉伸会变成盖住单位的白块。selected=四角 12px 角标；
        # moving=底中箭头原尺寸；suppressed=左上原尺寸。
        if selected:
            ov = assets.overlay_tex("overlay_selected")
            if ov is not None:
                s = ov.size[0]
                off = _UNIT_PX / 2 - s / 2
                for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    arcade.draw_texture_rect(
                        ov, arcade.XYWH(px + sx * off, py + sy * off, s, s))
        if u.get("moving"):
            ov = assets.overlay_tex("overlay_moving")
            if ov is not None:
                ow, oh = ov.size
                arcade.draw_texture_rect(
                    ov, arcade.XYWH(px, py - _UNIT_PX / 2 - oh / 2 - 1,
                                    ow, oh))
        if u.get("suppressed"):
            ov = assets.overlay_tex("overlay_suppressed")
            if ov is not None:
                ow, oh = ov.size
                arcade.draw_texture_rect(
                    ov, arcade.XYWH(px - _UNIT_PX / 2 + ow / 2 + 1,
                                    py + _UNIT_PX / 2 - oh / 2 - 1, ow, oh))
        # 血条：单位上缘 +5px，底条半透明、填充按 hp/hp_max 左锚裁宽
        bar_bg, bar_fill = _hp_bar_pair(pct)
        if bar_bg is not None:
            bw = bar_bg.size[0]
            y = py + _UNIT_PX / 2 + 5
            arcade.draw_texture_rect(bar_bg, arcade.XYWH(px, y, bw,
                                                         _HP_BAR_H),
                                     alpha=110)
            if pct > 0:
                fw = bar_fill.size[0]
                arcade.draw_texture_rect(
                    bar_fill,
                    arcade.XYWH(px - bw / 2 + fw / 2, y, fw, _HP_BAR_H))
    # F2 断箭铭牌（两路同锚——贴图/字形回退都在单位下方挂铭牌；
    # R3 1-1：+category——人数「30/30」仅步兵挂、载具只血条）
    draw_nameplate(px, py, getattr(win, "cam_scale", 1.0), {
        "hp": hp, "hp_max": hp_max, "team": u["team"],
        "category": u.get("category", 1),
        "selected": selected,
        "suppressed": u.get("suppressed"), "stance": u.get("stance"),
        "radar_on": u.get("radar_on"), "rtb": u.get("rtb"),
        "garrisoned": u.get("garrisoned"), "towed": u.get("towed")})


def draw_air_unit(win, a: dict, px: float, py: float) -> None:
    """航空器：40px 逐卡贴图（facing 旋转）；缺图回退 glyphs 字形（含
    高度层虚线圈/spotted 白点等原信息面）。"""
    tex = assets.air_tex(a.get("template_id"))
    facing = a.get("facing")
    rot = _cam_rot(win)
    selected = a.get("id") in getattr(getattr(win, "fsm", None),
                                      "selected_air", ())
    if tex is None:
        draw_aircraft_glyph(px, py, team=a["team"], alt_tier=a["alt_tier"],
                            spotted=a["spotted"],
                            facing_deg=None if facing is None
                            else facing + rot,
                            selected=selected)
        return
    angle = 0.0
    if facing is not None:
        angle = -(float(facing) + rot) % 360.0
    arcade.draw_texture_rect(tex, arcade.XYWH(px, py, _AIR_PX, _AIR_PX),
                             angle=angle)
