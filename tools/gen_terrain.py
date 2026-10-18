#!/usr/bin/env python3
"""R6 地形底图生成器（构建期 PIL——禁止被 sovs/ui import）。

读 data/gen/bagration_field.v1.json（瓦片/建筑）＋ data/scenarios/
bagration_field.json（decor：溪流/麦田/残骸/战壕），输出：
  assets/fe/terrain/bagration_field_base.png    2560×1280（32px/瓦片）
  assets/fe/terrain/bagration_field_minimap.png 512×256（base 派生）

确定性：seed=int(sha256(map_key)[:8],16)，random.Random(seed) 全程驱动；
两次生成 sha256 一致。朝向：PNG 第 0 行=世界最北（瓦片 iy=ny-1 画在第 0 行
带）——接入侧 draw_texture_rect 直铺不翻转，测试锁朝向。
画法口径见 R6 工单 §2（1944 夏季白俄罗斯低饱和写实俯视；无文字/网格/UI/
单位/旗帜/建筑屋顶）。
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MAP_JSON = ROOT / "data" / "gen" / "bagration_field.v1.json"
SCENARIO_JSON = ROOT / "data" / "scenarios" / "bagration_field.json"
OUT_DIR = ROOT / "assets" / "fe" / "terrain"

TILE_PX = 32                      # base 每瓦片段长
BASE_SCALE = TILE_PX / 2500       # cm→base px（瓦片 2500cm）
MINIMAP_SIZE = (512, 256)

TYPE_ROAD, TYPE_FOREST, TYPE_RUIN = 0, 1, 2

# 调色板（R6 §2 各条）
GRASS = (0x55, 0x60, 0x3F)
GRASS_WARM = (0x5E, 0x64, 0x40)
WHEAT = ((0x9A, 0x8A, 0x4A), (0xB0, 0xA0, 0x5A))
FIELD_BORDER = (0x6A, 0x60, 0x40)
FOREST_DARK = (0x24, 0x30, 0x20)
FOREST_MID = (0x2F, 0x3D, 0x2A)
FOREST_LIGHT = (0x46, 0x58, 0x3A)
BIRCH_TRUNK = (0xC8, 0xC8, 0xB0)
RUIN_BASE = (0x5A, 0x53, 0x4A)
RUIN_BRICK = (0x7A, 0x6E, 0x5E)
RUIN_CRACK = (0x3A, 0x35, 0x2E)
YARD_FENCE = (0x6A, 0x5C, 0x46)
GARDEN = ((0x4A, 0x5A, 0x32), (0x6A, 0x6A, 0x3A))
ROAD_MAIN = (0x8A, 0x7A, 0x5A)
ROAD_CENTER = (0x9A, 0x8A, 0x6A)
ROAD_EDGE = (0x5A, 0x50, 0x40)
ROAD_RUT = (0x6A, 0x5A, 0x44)
STREAM = (0x4A, 0x5A, 0x62)
STREAM_BANK = (0x6A, 0x6A, 0x5A)
STREAM_RIPPLE = (0x6A, 0x7A, 0x82)
WRECK = (0x2E, 0x2C, 0x28)
TRENCH = (0x4A, 0x40, 0x38)
HAYSTACK = (0xB8, 0xA4, 0x60)
CRATER_DARK = (0x38, 0x34, 0x2C)
CRATER_RIM = (0x7A, 0x6E, 0x56)
BORDER_DARK = (0x1E, 0x22, 0x18)


def _cm_to_px(x_cm: float, y_cm: float, ny: int) -> tuple[float, float]:
    """世界 cm → base 像素（y 翻转：PNG 第 0 行=最北 iy=ny-1）。"""
    return x_cm * BASE_SCALE, (ny * 2500 - y_cm) * BASE_SCALE


def _tile_rect(ix: int, iy: int, nx: int, ny: int) -> tuple[int, int, int, int]:
    """瓦片 (ix,iy) 的像素矩形 (x0,y0,x1,y1)（iy=0 最南→最下行）。"""
    x0, x1 = ix * TILE_PX, (ix + 1) * TILE_PX
    py0 = (ny - 1 - iy) * TILE_PX
    return x0, py0, x1, py0 + TILE_PX


def gen_base(doc: dict, decor: dict) -> Image.Image:
    nx = doc["extent_x_cm"] // doc["tile_cm"]
    ny = doc["extent_y_cm"] // doc["tile_cm"]
    seed = int(hashlib.sha256(doc["map_key"].encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    img = Image.new("RGB", (nx * TILE_PX, ny * TILE_PX), GRASS)
    dr = ImageDraw.Draw(img)

    # ── 1) 草地基色＋确定性双色带噪声（粗 64/细 16，±14，暖偏）──
    for band in (64, 16):
        step = band
        for yy in range(0, img.height, step):
            for xx in range(0, img.width, step):
                dv = rng.randint(-14, 14)
                base = GRASS_WARM if rng.random() < 0.5 else GRASS
                col = tuple(max(0, min(255, c + dv)) for c in base)
                dr.rectangle((xx, yy, xx + step - 1, yy + step - 1), fill=col)

    tiles: dict[tuple[int, int], int] = {(t[0], t[1]): t[2] for t in doc["tiles"]}

    # ── 2) 麦田（decor.wheat 多边形：填色+羽化边+田埂+收割条纹）──
    for poly in decor.get("wheat", []):
        pts = [_cm_to_px(p[0], p[1], ny) for p in poly]
        col = WHEAT[rng.randrange(2)]
        dr.polygon(pts, fill=col)
        dr.line(pts + [pts[0]], fill=FIELD_BORDER, width=1)
        # 收割条纹 2~3 条（沿多边形首末点方向）
        (ax, ay), (bx, by) = pts[0], pts[2]
        for k in range(1, rng.randint(3, 4)):
            f = k / 3.5
            sx, sy = ax + (bx - ax) * f, ay + (by - ay) * f
            ex, ey = pts[1][0] + (pts[3][0] - pts[1][0]) * f, \
                pts[1][1] + (pts[3][1] - pts[1][1]) * f
            dr.line((sx, sy, ex, ey),
                    fill=(min(255, col[0] + 18), min(255, col[1] + 14),
                          col[2]), width=1)

    # ── 6) 溪流（先画——道路跨溪缺口在道路段处理）──
    stream = decor.get("stream", [])
    for a, b in zip(stream, stream[1:]):
        p0 = _cm_to_px(a[0], a[1], ny)
        p1 = _cm_to_px(b[0], b[1], ny)
        dr.line((p0, p1), fill=STREAM_BANK, width=15)
        dr.line((p0, p1), fill=STREAM, width=13)
        for k in range(1, 4):
            f = k / 4
            mx, my = p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f
            dr.line((mx - 6, my, mx + 6, my), fill=STREAM_RIPPLE, width=1)

    # ── 4) 废墟/村庄场院（RUIN 格）──
    ruin_cells = [(ix, iy) for (ix, iy), t in tiles.items() if t == TYPE_RUIN]
    for ix, iy in ruin_cells:
        x0, y0, x1, y1 = _tile_rect(ix, iy, nx, ny)
        dr.rectangle((x0, y0, x1 - 1, y1 - 1), fill=RUIN_BASE)
        for _ in range(rng.randint(6, 10)):        # 碎砖
            bx = rng.randint(x0 + 2, x1 - 5)
            by = rng.randint(y0 + 2, y1 - 5)
            dr.rectangle((bx, by, bx + rng.randint(2, 4),
                          by + rng.randint(2, 3)), fill=RUIN_BRICK)
        for _ in range(3):                          # 深缝
            fx = rng.randint(x0 + 3, x1 - 4)
            dr.line((fx, y0 + 3, fx + rng.randint(-4, 4), y1 - 3),
                    fill=RUIN_CRACK, width=1)
        if rng.random() < 0.5:                      # 木栅栏短线
            fy = rng.randint(y0 + 6, y1 - 8)
            dr.line((x0 + 3, fy, x1 - 4, fy), fill=YARD_FENCE, width=1)
        if rng.random() < 0.4:                      # 菜地条纹
            gx = rng.randint(x0 + 4, x1 - 12)
            gc = GARDEN[rng.randrange(2)]
            for s in range(3):
                dr.line((gx + s * 4, y0 + 6, gx + s * 4, y1 - 6), fill=gc,
                        width=1)

    # ── 5) 道路（ROAD 格圆头连接；跨溪缺口 26px）──
    road_cells = [(ix, iy) for (ix, iy), t in tiles.items() if t == TYPE_ROAD]
    for ix, iy in road_cells:
        x0, y0, x1, y1 = _tile_rect(ix, iy, nx, ny)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        # 跨溪缺口：瓦片含溪流 y 带（溪流世界 y 14000~16000 → 该行瓦片）
        tile_y_cm = iy * 2500
        crosses = tile_y_cm <= 15000 < tile_y_cm + 2500
        if crosses and abs(ix - 40) <= 1:          # 主路 x=100000（ix=40 列）
            r = 13                                  # 缺口半径≈26px（桥位）
            dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GRASS)
            continue
        for dx, dy in ((1, 0), (0, 1)):             # 与相邻 road 格圆头连接
            if (ix + dx, iy + dy) in tiles and \
                    tiles[(ix + dx, iy + dy)] == TYPE_ROAD:
                tx = cx + dx * (TILE_PX // 2 + 5)
                ty = cy + dy * (TILE_PX // 2 + 5) * (-1 if dy else 1) \
                    if False else cy - dy * (TILE_PX // 2 + 5)
                dr.ellipse((tx - 5, ty - 5, tx + 5, ty + 5), fill=ROAD_MAIN)
        dr.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=ROAD_MAIN)
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            if (ix + dx, iy + dy) in tiles and \
                    tiles[(ix + dx, iy + dy)] == TYPE_ROAD:
                ax = cx + dx * TILE_PX // 2
                ay = cy - dy * TILE_PX // 2
                dr.line((cx, cy, ax, ay), fill=ROAD_MAIN, width=9)
                dr.line((cx, cy, ax, ay), fill=ROAD_CENTER, width=2)
        dr.line((cx - 4, cy - 2, cx + 4, cy - 2), fill=ROAD_RUT, width=1)
        dr.line((cx - 4, cy + 2, cx + 4, cy + 2), fill=ROAD_RUT, width=1)

    # ── 3) 桦林（FOREST 格：树冠椭圆群＋林缘亮边；允许溢出 4px）──
    forest_cells = [(ix, iy) for (ix, iy), t in tiles.items() if t == TYPE_FOREST]
    for ix, iy in forest_cells:
        x0, y0, x1, y1 = _tile_rect(ix, iy, nx, ny)
        dr.rectangle((x0, y0, x1 - 1, y1 - 1), fill=FOREST_MID)
        for _ in range(rng.randint(3, 6)):
            tr = rng.randint(6, 14)
            tx = rng.randint(x0 - 4, x1 - 6)
            ty = rng.randint(y0 - 4, y1 - 6)
            crown = FOREST_DARK if rng.random() < 0.45 else FOREST_LIGHT
            dr.ellipse((tx, ty, tx + tr, ty + max(4, tr - 3)), fill=crown)
            if rng.random() < 0.2:                  # 桦树干白点
                dr.point((tx + tr // 2, ty + 4), fill=BIRCH_TRUNK)
        # 林缘亮边（邻格非林才画该边）
        for (dx, dy, e0, e1) in ((0, 1, 0, 1), (1, 0, 2, 3), (0, -1, 2, 3),
                                 (-1, 0, 0, 1)):
            n = tiles.get((ix + dx, iy + dy))
            if n is not TYPE_FOREST:
                if e0 == 0 and e1 == 1:             # 南/北边
                    yy = y1 - 1 if dy == 1 else y0
                    dr.line((x0, yy, x1 - 1, yy), fill=FOREST_LIGHT, width=1)
                else:                               # 东/西边
                    xx = x1 - 1 if dx == 1 else x0
                    dr.line((xx, y0, xx, y1 - 1), fill=FOREST_LIGHT, width=1)

    # ── 7) 静态装饰（残骸/战壕/干草堆/弹坑/田界小径）──
    for wx, wy, kind in decor.get("wrecks", []):
        px, py = _cm_to_px(wx, wy, ny)
        s = 16 if kind == "tank" else 12
        dr.rectangle((px - s // 2, py - s // 3, px + s // 2, py + s // 3),
                     fill=WRECK)
        dr.line((px - s // 2 + 2, py - s // 3 + 2,
                 px + s // 2 - 2, py + s // 3 - 2), fill=(0x1A, 0x19, 0x16),
                width=1)
    trench = decor.get("trenches", [])
    for a, b in zip(trench, trench[1:]):
        p0 = _cm_to_px(a[0], a[1], ny)
        p1 = _cm_to_px(b[0], b[1], ny)
        dr.line((p0, p1), fill=TRENCH, width=4)
        for k in range(1, 6):                       # 土堆点
            f = k / 6
            mx, my = p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f
            dr.point((mx + rng.randint(-5, 5), my + rng.randint(-4, 4)),
                     fill=(0x5E, 0x54, 0x48))
    for _ in range(6):                              # 干草堆（麦田带附近）
        hx = rng.randint(60, 240)
        hy = rng.randint(int(img.height * 0.72), int(img.height * 0.95))
        dr.ellipse((hx - 5, hy - 4, hx + 5, hy + 4), fill=HAYSTACK)
    for _ in range(9):                              # 弹坑
        cxx = rng.randint(20, img.width - 20)
        cyy = rng.randint(20, img.height - 20)
        r = rng.randint(3, 7)
        dr.ellipse((cxx - r, cyy - r, cxx + r, cyy + r), fill=CRATER_DARK)
        dr.ellipse((cxx - r - 1, cyy - r - 1, cxx + r + 1, cyy + r + 1),
                   outline=CRATER_RIM, width=1)
    for _ in range(5):                              # 田界小径（浅色短线）
        fx = rng.randint(10, img.width - 60)
        fy = rng.randint(10, img.height - 10)
        dr.line((fx, fy, fx + rng.randint(20, 50), fy + rng.randint(-8, 8)),
                fill=(0x6E, 0x6A, 0x50), width=1)

    # ── 8) 图幅：2px 暗边＋轻暗角＋细粒纹理（色彩多样性：种子化噪声瓦片
    #    160×160 两档 σ 经 NEAREST 放大——PIL effect_noise 是 libc rand 无
    #    种子面，进程内二次调用漂移，弃用；本式全 random.Random(seed) 驱动）──
    dr.rectangle((0, 0, img.width - 1, img.height - 1), outline=BORDER_DARK,
                 width=2)
    for band, amp, alpha in ((160, 14, 26), (64, 26, 14)):
        nt = Image.new("L", (band, band))
        np_ = nt.load()
        for yy in range(band):
            for xx in range(band):
                np_[xx, yy] = max(0, min(255, 128 + rng.randint(-amp, amp)))
        noise = nt.resize(img.size, Image.NEAREST)
        overlay = Image.merge("RGB", (noise, noise, noise))
        img = Image.blend(img, overlay, alpha / 255)
    vign = Image.new("L", img.size, 0)
    ImageDraw.Draw(vign).ellipse((-img.width * 0.25, -img.height * 0.25,
                                  img.width * 1.25, img.height * 1.25),
                                 fill=255)
    dark = Image.new("RGB", img.size, (0x22, 0x26, 0x1C))
    img = Image.composite(img, dark, vign.point(lambda v: 255 - (255 - v) // 6))
    return img


def main(argv=None) -> int:
    doc = json.loads(MAP_JSON.read_text(encoding="utf-8"))
    decor = json.loads(SCENARIO_JSON.read_text(encoding="utf-8")).get("decor", {})
    base = gen_base(doc, decor)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base_path = OUT_DIR / "bagration_field_base.png"
    base.save(base_path, format="PNG")
    mini = base.resize(MINIMAP_SIZE, Image.LANCZOS)
    mini_path = OUT_DIR / "bagration_field_minimap.png"
    mini.save(mini_path, format="PNG")
    from pathlib import Path as _P
    _P(base_path).with_name("bagration_field_base.source").write_text(
        "procedural\n", encoding="utf-8")
    for p in (base_path, mini_path):
        print("%s：size=%s sha256=%s" % (
            p.name, p.stat().st_size,
            hashlib.sha256(p.read_bytes()).hexdigest()[:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
