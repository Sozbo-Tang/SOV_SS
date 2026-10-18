"""FE-05 贴图资产接线基建（F0）：asset_index 消费 + 九宫格皮肤绘制原语。

结论先行：本模块是 sovs/ui 唯一的贴图加载面——data/gen/asset_index.json
（tools/build_asset_index.py 产物）为数据源，按需懒加载 arcade.Texture；
缺图/缺索引一律返回 None 回退矢量绘制（glyphs.py 原行为），不打印不抛
（截图门禁零扰动纪律）。分层：只 import arcade＋stdlib（禁 PIL——视觉
QA 工具面在 tools/qa_visual.py；禁 sovs.sim/sovs.ai——AST 守卫②）。

九宫格口径：arcade.gui.NinePatchTexture(corner,corner,corner,corner, tex)
.draw_rect(rect=arcade.LRBT(*rect))；对象按 (tex.cache_name, corner) 缓存
（同贴图同角复用——避免每帧重建）；rect 任一边 < 2*corner 时退化为
draw_texture_rect 整图拉伸（小矩形九宫格无意义）；tex=None 直接 return。
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from types import MappingProxyType

import arcade
import arcade.gui                                   # noqa: F401（NinePatchTexture）

_ROOT = Path(__file__).resolve().parents[2]
_INDEX_PATH = _ROOT / "data" / "gen" / "asset_index.json"

# 空结构（缺索引文件/坏 JSON 兜底——消费面全部 .get 回退 None）
_EMPTY_INDEX = {"schema": 0, "units": {}, "air": {}, "orders": {}, "ui": {},
                "settle": {}, "cursor": {}, "terrain": {}, "bg": {},
                "objectives": {}, "unit_mark": {}, "missing": []}

_index_cache = None
_units_by_card_key = None          # card_key → entry（unit_tex 反查缓存）


def index():
    """资产索引（懒加载一次；只读 MappingProxyType——外层只读纪律）。"""
    global _index_cache
    if _index_cache is None:
        try:
            data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        merged = dict(_EMPTY_INDEX)
        for k in _EMPTY_INDEX:
            if k in data:
                merged[k] = data[k]
        _index_cache = MappingProxyType(merged)
    return _index_cache


@functools.lru_cache(maxsize=1024)
def load(path: str):
    """加载贴图（相对路径按仓库根解析；缺文件/异常 → None，不打印不抛）。"""
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = _ROOT / p
    if not p.is_file():
        return None
    try:
        return arcade.load_texture(str(p))
    except Exception:                              # noqa: BLE001（缺图回退纪律）
        return None


def unit_tex(card_key: str):
    """地面单位贴图（card_key 反查——呼援轨/部署卡/编辑器缩略图消费面）。"""
    global _units_by_card_key
    if _units_by_card_key is None:
        _units_by_card_key = {e.get("card_key"): e
                              for e in index()["units"].values()}
    entry = _units_by_card_key.get(card_key)
    return load(entry["path"]) if entry else None


def unit_tex_by_id(template_id):
    """地面单位贴图（template_id 直查——战场单位帧渲染消费面）。"""
    entry = index()["units"].get(str(template_id))
    return load(entry["path"]) if entry else None


def air_tex(template_id):
    """航空器贴图（template_id 直查——苏 1~5 / 德 11~15）。"""
    entry = index()["air"].get(str(template_id))
    return load(entry["path"]) if entry else None


def order_tex(key: str):
    """命令图标贴图（order_icons.ICON_FUNCS 键域）。"""
    return load(index()["orders"].get(key))


def ui_tex(name: str):
    """九宫格皮肤/控件贴图（panel_topbar/btn_generic_36/…）。"""
    return load(index()["ui"].get(name))


def settle_tex(name: str):
    """结算面贴图（badge_*/banner_*/row_*）。"""
    return load(index()["settle"].get(name))


def cursor_tex(name: str):
    """光标贴图（cur_default/…）。"""
    return load(index()["cursor"].get(name))


def terrain_tex(name: str):
    """地形/小地图底图贴图（minimap_terrain/tile_*/map_border）。"""
    return load(index()["terrain"].get(name))


def terrain_map_tex(map_key: str):
    """R6 地形底图（assets/fe/terrain/<map_key>_base.png；缺图 None）。"""
    return load("assets/fe/terrain/%s_base.png" % map_key
                if map_key else None)


def terrain_minimap_tex(map_key: str):
    """R6 小地图底图（<map_key>_minimap.png；缺图 None）。"""
    return load("assets/fe/terrain/%s_minimap.png" % map_key
                if map_key else None)


def map_meta(map_key: str) -> dict:
    """R6 地图元数据（stdlib json——buildings/extent；缺文件空 dict 不抛）。
    sovs/ui 禁 sim import：地图 gen JSON 是纯数据，直读不触仿真规则。"""
    import os
    if not map_key:
        return {}
    path = os.path.join(_ROOT, "data", "gen", "%s.v1.json" % map_key)
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return {}
    return {"buildings": list(doc.get("buildings", ())),
            "extent": (doc.get("extent_x_cm"), doc.get("extent_y_cm")),
            "tile_cm": doc.get("tile_cm")}


def bg_tex(name: str):
    """整页背景贴图（bg_mainmenu/bg_config/…）。"""
    return load(index()["bg"].get(name))


def objective_tex(name: str):
    """占点贴图（obj_flag_red/blue/neutral、obj_ring_glow）。"""
    return load(index()["objectives"].get(name))


def overlay_tex(name: str):
    """单位标记件贴图（overlay_selected/moving/suppressed/facing、hp_bar）。"""
    return load(index()["unit_mark"].get(name))


def skin_fill(rect, name: str, fallback_color) -> bool:
    """面板皮肤填充（F8 统一入口）：ui_tex(name) 有图→九宫格铺 rect；
    缺图→纯色回填（fallback_color）返回 False。描边/文字由调用方原样叠加
    ——几何零变纪律的换皮收口点。"""
    tex = ui_tex(name)
    if tex is None:
        x0, y0, x1, y1 = rect
        arcade.draw_lrbt_rectangle_filled(x0, x1, y0, y1, fallback_color)
        return False
    draw_nine_patch(rect, tex)
    return True


def button_skin(btn, *, armed: bool = False):
    """按钮皮肤名（F8）：tone/armed → 状态态名（Btn.tone 映射沿用——
    disabled→disabled、focus/armed→selected、余 normal）；家族按键前缀与
    钮高选 btn_rail/btn_lane/btn_primary/btn_generic_36/30。返回完整皮肤名
    或 None（无该态资产时调用方回退纯色）。"""
    h = btn.yt - btn.yb
    if btn.key.startswith(("railtab_", "air:", "buy:")):
        fam = "btn_rail"
    elif btn.key.startswith("lane"):
        fam = "btn_lane"
    elif h >= 32:
        fam = "btn_generic_36"
    else:
        fam = "btn_generic_30"
    state = ("disabled" if btn.tone == "disabled"
             else "selected" if (armed or btn.tone == "focus") else "normal")
    name = fam if state == "normal" else "%s_%s" % (fam, state)
    return name if ui_tex(name) is not None else None


# ── 九宫格绘制原语（F8 皮肤统一的全局面；corner 缺省 16=皮肤资产口径）──

_nine_cache: dict = {}


def _cur_window_id() -> int:
    """当前活动窗口身份（跨窗测试/多窗场景下 NinePatchTexture 绑定创建时
    的 GL 上下文——缓存键必须带窗口维度，旧窗对象的 GL 资源随窗失效）。"""
    try:
        return id(arcade.get_window())
    except Exception:                                # noqa: BLE001（无窗环境）
        return 0


def draw_nine_patch(rect, tex, corner: int = 16) -> None:
    """九宫格铺矩形（rect=(x0,y0,x1,y1) 屏幕系，lrbt 语义）。

    tex=None 直接 return（回退纯色由调用方先判）；任一边 < 2*corner 退化
    整图拉伸（小矩形九宫格无意义）；对象按 (cache_name, corner, 窗口身份)
    复用（NinePatchTexture 持创建窗的 GL 上下文对象——跨窗缓存会撞
    GL_INVALID_VALUE，多测试类开关窗场景实证）。
    """
    if tex is None:
        return
    x0, y0, x1, y1 = rect
    if min(x1 - x0, y1 - y0) < 2 * corner:
        # LRBT 参数序是 (left, right, bottom, top)——输入 rect 是 (x0,y0,x1,y1)，
        # 必须重排；直接展开会把 y0 当 right、x1 当 bottom（负宽高整屏错位）。
        arcade.draw_texture_rect(tex, arcade.LRBT(x0, x1, y0, y1))
        return
    key = (tex.cache_name, corner, _cur_window_id())
    np9 = _nine_cache.get(key)
    if np9 is None:
        np9 = arcade.gui.NinePatchTexture(corner, corner, corner, corner, tex)
        _nine_cache[key] = np9
    np9.draw_rect(rect=arcade.LRBT(x0, x1, y0, y1))
