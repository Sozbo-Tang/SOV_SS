"""命令格三态过滤矩阵（B3 修复块 2026-10-13）——纯逻辑，无 arcade/GL，可无头单测。

结论先行：右下命令格不再全量常显——按**当前选区能力**三态过滤（手册
manual.txt:344-346「A menu of icons shows all possible orders a unit can be
given. It is located at the bottom right of the gameplay screen.」——菜单列
选区单位**可被下达**的命令；manual.txt:482-485「Certain units have specialist
training and equipment…They can be found in the orders menu」——专项命令出自
特定单位；basics.txt:62「7) Action panel: give commands to your units with
this panel.」——〔2026-10-15 B3 勘注：原推读「无选区即无此面板」被用户拍板
推翻——命令面板**空选区常驻**（满配 6×8 足印＋提示文案，hud_bottom.
order_panel_rect）；本模块**三态过滤行为保留不动**（空选区全键 hide=无钮
可下达，「只列框选单位可用的命令」半边即此），tests/test_order_filter.py
在册回归面零改动〕）。

三态语义：
- "show"：布局常色（选区任一单位满足）；
- "grey"：布局灰显 tone=disabled（能力在而余量/前置缺失——诱饵发数尽
  manual.txt:505-509「ammo limited」、烟幕余 0、精密打击无激光位
  manual.txt:530-532——「可再补给/可恢复」语义推定为灰显不隐藏，manual_silent）；
- "hide"：不布局（选区无该能力/空选区——空选区全键 hide）。

边界纪律（本模块与热键/引擎门的三权分立）：
- 按钮=过滤**呈现面**（本模块）；热键=**全量通道**（shell_fsm.key 不经此过滤
  ——手册 manual.txt:544-545「These are the default values…」无「菜单过滤则热键
  失效」语义，热键宽容拍板留痕 manual_silent）；引擎资格门=**唯一权威**
  （rejections→toast 事后反馈链既有）。
- 数据面=帧 caps/can_decoy 等能力位（state_frame._caps_summary——判据与引擎
  真实门同源：sprint/mount 取 SQUAD 元素判据〔CAN_SPRINT/HAS_MOUNT 67 卡零
  配属实测、引擎 sprint 无旗标门——门按手册「Sprint (infantry)」manual.txt:577
  元素级承载，数据配属后置可切换旗标判据〕）。

本模块不 import sovs.sim/arcade（tests/test_arch_constraints.py ② 守卫）——
只消费 dict 帧与 id 元组。
"""
from __future__ import annotations

_ALL_KEYS = ("air_alt", "air_rtb", "air_engage", "air_disengage", "air_ab",
             "decoy", "attack", "fm", "strike", "drop", "smoke_x", "laser",
             "precision", "radar", "stop", "cancel", "reverse", "sprint",
             "march", "stance_h", "smoke_sprint", "unload", "sniper",
             "supply", "mount", "ambush", "deploy_gun", "pack_gun", "tow",
             "untow", "formation", "fm_cancel")


def _caps(u: dict) -> dict:
    return u.get("caps") or {}


def eligible_orders(frame: dict, selected, selected_air=()) -> dict[str, str]:
    """选区 → 命令键三态映射 {key: "show"|"grey"|"hide"}（纯函数）。

    frame=FE-T02 状态帧（消费面：units[].caps/mounted/towed/smoke_left、
    aircraft[].alt_ceiling/can_afterburner/can_decoy/decoy_left/engage_air/
    state/ammo/paratroop、lasers）；selected/selected_air=fsm 双通道选区 id。
    显示=选区任一满足；空选区全键 hide（basics.txt:62）。
    """
    out: dict[str, str] = {k: "hide" for k in _ALL_KEYS}
    sel = set(selected)
    air_sel = set(selected_air)
    units = [u for u in frame.get("units", ()) if u["id"] in sel]
    own_air = [a for a in frame.get("aircraft", ()) if a["id"] in air_sel]
    has_ground = bool(units)
    has_air = bool(own_air)
    has_any = has_ground or has_air

    # ── 航空行（selected_air 非空才浮出——GP-01 §4 ③段行序）──
    # air_alt：有换层余量=alt_ceiling 高于 LOW（V 两态 toggle manual.txt:421-428；
    # 单层机（basics.txt:316-318）无余量→hide）
    out["air_alt"] = ("show" if has_air and any(
        (a.get("alt_ceiling") or "mid") != "low" for a in own_air) else "hide")
    out["air_rtb"] = "show" if has_air else "hide"
    out["air_engage"] = ("show" if has_air and any(
        a.get("engage_air") is not None for a in own_air) else "hide")
    out["air_disengage"] = ("show" if has_air and any(
        a.get("state") == "dogfight" for a in own_air) else "hide")
    out["air_ab"] = ("show" if any(a.get("can_afterburner")
                                   for a in own_air) else "hide")
    decoy_cands = [a for a in own_air if a.get("can_decoy")]
    if decoy_cands:
        out["decoy"] = ("show" if any(a.get("decoy_left", 0) > 0
                                      for a in decoy_cands) else "grey")
    # else 恒 "hide"（缺省）

    # ── 帧全域事实（strike/drop/mount 的选区外前置——空呼后代选口径同源）──
    view = frame.get("view")
    all_own_units = [u for u in frame.get("units", ())
                     if view is None or u.get("team") == view]
    all_own_air = [a for a in frame.get("aircraft", ())
                   if view is None or a.get("team") == view]
    bomber_ready = any((a.get("ammo") or {}).get("BOMB", 0) > 0
                       or (a.get("ammo") or {}).get("STRAFE", 0) > 0
                       for a in all_own_air)
    dropper_ready = any(a.get("paratroop") is not None for a in all_own_air)
    seats_on_field = any(_caps(u).get("seats", 0) > 0 for u in all_own_units)
    lasers = frame.get("lasers") or ()

    # ── 作战行 ──
    out["attack"] = "show" if has_ground else "hide"      # 通用令（manual.txt:351-355）
    indirect = [u for u in units if _caps(u).get("indirect")]
    out["fm"] = "show" if indirect else "hide"            # 曲射位（tick cmd_fire_mission）
    out["strike"] = "show" if has_any and bomber_ready else "hide"
    out["drop"] = "show" if has_any and dropper_ready else "hide"
    smoke_caps = [u for u in units if _caps(u).get("smoke")]
    if smoke_caps:
        out["smoke_x"] = ("show" if any(u.get("smoke_left", 0) > 0
                                        for u in smoke_caps) else "grey")
    out["laser"] = ("show" if any(_caps(u).get("sniper")
                                  for u in units) else "hide")
    if indirect:
        out["precision"] = "show" if lasers else "grey"   # manual.txt:530-532 近激光位
    # else 恒 "hide"
    # radar（终审第四批 2026-10-13 漏一处收口）：ABILITIES Radar（manual.txt:
    # 534-539）经命令菜单下达——manual.txt:482-485「They can be found in the
    # orders menu at the bottom right」；原仅热键 Z＋F1 帮助面，纯高炮选区
    # （非班单位——sprint 门 SQUAD 元素）连冲刺(Z)钮都 hide→菜单对雷达不可达。
    # 判据 caps.radar=引擎 _aa_eligible 同源（state_frame._caps_summary）；
    # 按钮镜像 Z 同门同令（shell_fsm._ground_z_dispatch 雷达优先口径不变）。
    out["radar"] = ("show" if has_ground and any(
        _caps(u).get("radar") for u in units) else "hide")

    # ── 机动行 ──
    out["stop"] = out["cancel"] = out["march"] = "show" if has_ground else "hide"
    out["reverse"] = ("show" if has_ground and any(_caps(u).get("reverse")
                                                   for u in units) else "hide")
    # sprint：SQUAD 元素判据（手册「Sprint (infantry)」manual.txt:577——CAN_SPRINT
    # 零卡配属+引擎无旗标门，元素级承载；载具 Z 冲刺经热键宽容通道保留）
    out["sprint"] = ("show" if has_ground and any(_caps(u).get("squad")
                                                  for u in units) else "hide")

    # ── 支援行 ──
    out["stance_h"] = "show" if has_ground else "hide"
    out["smoke_sprint"] = "show" if smoke_caps else "hide"
    out["unload"] = ("show" if has_ground and (any(
        u.get("mounted") for u in units)
        or any(_caps(u).get("seats", 0) > 0 for u in units)) else "hide")
    out["sniper"] = ("show" if any(_caps(u).get("sniper")
                                   for u in units) else "hide")
    out["supply"] = "show" if has_ground else "hide"      # cmd_bus 无资格门（点卡车）
    # mount：SQUAD 且未 mounted 且场上存在己方座位载具（引擎真实门①=非 SQUAD
    # CONTINUE tick cmd_mount；HAS_MOUNT 零卡配属不作门——数据配属后置）
    out["mount"] = ("show" if has_ground and seats_on_field and any(
        _caps(u).get("squad") and not u.get("mounted") for u in units)
        else "hide")

    # ── 杂项行 ──
    out["ambush"] = ("show" if has_ground and any(_caps(u).get("ambush")
                                                  for u in units) else "hide")
    out["deploy_gun"] = out["pack_gun"] = (
        "show" if has_ground and any(_caps(u).get("deploy_gun")
                                     for u in units) else "hide")
    out["tow"] = ("show" if has_ground and (any(_caps(u).get("tow")
                                                for u in units)
                                            or any(u.get("towed")
                                                   for u in units)) else "hide")
    out["untow"] = ("show" if has_ground and any(u.get("towed")
                                                 for u in units) else "hide")
    out["formation"] = "show" if has_ground else "hide"
    out["fm_cancel"] = out["fm"]
    return out
