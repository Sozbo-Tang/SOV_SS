#!/usr/bin/env python3
"""FE-05 资产索引构建器：卡面数据 × assets/fe 贴图 → data/gen/asset_index.json。

结论先行（FE-05 F0 资产基建）：本工具是贴图接线的数据面唯一事实源——
sovs/ui/assets.py 按索引懒加载（ui 层不 import yaml/pydantic，卡面解析
收敛在此 tools 层）。输入三源：地面卡 JSON、两份航空卡 YAML、assets/fe
目录扫描。命名口径：units=卡键小写.png；air=阵营前缀_卡键小写.png
（SOVIET→su / GERMAN→ger）；orders=cmd_键.png（键以 order_icons.ICON_FUNCS
实际注册为准）；其余目录文件名去 .png 与 @2x 后缀即键。
路径纪律：数据源键先经 _SAFE_TOKEN 白名单校验（仅字母数字下划线——
杜绝任何穿越成分），全部文件操作经 pathlib 且根=本文件上两级仓库根。
确定性：sort_keys、ensure_ascii=False、末尾单 LF——两次生成字节一致。
任何单位/航空/命令缺图 → missing 非空并 exit 1（CI 防线：美术漏件即红）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_]+$")

# 航空阵营前缀（文件名口径——IL2M → su_il2m.png）
_AIR_PREFIX = {"SOVIET": "su", "GERMAN": "ger"}


def _tok(value) -> str:
    """数据源键白名单校验（仅字母数字下划线；违规即 raise——防穿越门）。"""
    s = str(value)
    if not _SAFE_TOKEN.match(s):
        raise ValueError("数据源键含非法字符：%r" % s)
    return s


def _scan_dir(name: str) -> dict:
    """目录扫描 → {键: 相对路径}（跳过 @2x；键=去 .png 文件名，排序确定）。"""
    d = _ROOT / "assets" / "fe" / _tok(name)
    out: dict = {}
    if not d.is_dir():
        return out
    for fn in sorted(d.iterdir()):
        if fn.suffix != ".png" or "@2x" in fn.name:
            continue
        out[fn.stem] = "assets/fe/%s/%s" % (name, fn.name)
    return out


def build_index() -> dict:
    """构造索引 dict（纯函数——不落盘；main 消费后写 data/gen/asset_index.json）。"""
    import yaml

    from sovs.ui.order_icons import ICON_FUNCS

    missing: list[str] = []

    cards = json.loads(
        (_ROOT / "data" / "gen" / "cards_ground.v1.json").read_text(
            encoding="utf-8"))["cards"]
    units: dict = {}
    for c in cards:
        path = "assets/fe/units/%s.png" % _tok(c["card_key"]).lower()
        if not (_ROOT / path).is_file():
            missing.append(path)
        units[str(c["template_id"])] = {"card_key": c["card_key"],
                                        "path": path}

    air: dict = {}
    for rel in ("data/yaml/units/air_su.yaml", "data/yaml/units/air_ger.yaml"):
        doc = yaml.safe_load(
            (_ROOT / rel).read_text(encoding="utf-8"))
        for c in doc["cards"]:
            prefix = _AIR_PREFIX.get(_tok(c["faction"]), "")
            path = "assets/fe/air/%s_%s.png" % (prefix,
                                                _tok(c["card_key"]).lower())
            if not (_ROOT / path).is_file():
                missing.append(path)
            air[str(c["template_id"])] = {"card_key": c["card_key"],
                                          "faction": c["faction"],
                                          "path": path}

    orders: dict = {}
    for key in sorted(ICON_FUNCS):
        path = "assets/fe/orders/cmd_%s.png" % _tok(key)
        if not (_ROOT / path).is_file():
            missing.append(path)
        orders[key] = path

    # ui 区并入 orders 目录里的控件贴图（cmd_tile 四态底砖＋trail_* 痕迹件
    # ——F4 底砖/F1 痕迹经 ui_tex("cmd_tile") 取；逐命令 cmd_<key> 不并入，
    # 留在 orders 区防键冲突）
    ui = _scan_dir("ui")
    for k, v in _scan_dir("orders").items():
        if k.startswith(("cmd_tile", "trail_")):
            ui[k] = v
    # 单位标记件（overlay_selected/moving/suppressed/facing＋hp_bar——
    # units 目录里非卡面的通用件，F1 战场渲染消费面）
    unit_mark = {k: v for k, v in _scan_dir("units").items()
                 if k.startswith(("overlay_", "hp_bar"))}

    return {
        "schema": 1,
        "units": units,
        "air": air,
        "orders": orders,
        "ui": ui,
        "unit_mark": unit_mark,
        "settle": _scan_dir("settle"),
        "cursor": _scan_dir("cursor"),
        "terrain": _scan_dir("terrain"),
        "bg": _scan_dir("bg"),
        "objectives": _scan_dir("objectives"),
        "missing": sorted(missing),
    }


def main(argv=None) -> int:
    index = build_index()
    text = json.dumps(index, sort_keys=True, ensure_ascii=False,
                      indent=1) + "\n"
    out = _ROOT / "data" / "gen" / "asset_index.json"
    out.write_text(text, encoding="utf-8", newline="\n")
    if index["missing"]:
        print("✗ 缺图 %d 张：" % len(index["missing"]))
        for p in index["missing"]:
            print("  - %s" % p)
        return 1
    print("units=%d air=%d orders=%d ui=%d missing=0"
          % (len(index["units"]), len(index["air"]), len(index["orders"]),
             len(index["ui"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
