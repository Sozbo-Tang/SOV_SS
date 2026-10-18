#!/usr/bin/env python3
"""R7 地形美术 v2 · Phase A 风格板生成器（构建期 PIL——禁止被 sovs/ui import）。

路线换血（R6 逐 tile 填色路线废弃）：**矢量几何路线**——读
data/map_bagration_field.csv 的 polyline/rect/building 矢量行＋scenario
decor，全部按世界 cm 坐标经仿射到画布；2× 超采样（2048² 风格板）→
LANCZOS 降采样 1024²；放大一律 BICUBIC、羽化一律 GaussianBlur、
禁用 NEAREST（树冠/碎砖散点除外——散点本身在 2× 画布上画满分辨率）。

风格板：中心=村庄 (108000,64000)，裁 2048×2048 世界窗（1024px 输出×2
超采样＝1px 对应 1000cm），含村庄场院＋主南北路＋东西路西段＋村环路＋
废墟带＋森林 (52,28)-(70,37) 西缘＋农庄土路西端；三版同几何只变画法：
  A 写实柔和：低饱和、Gaussian 模糊多、暖干草调；
  B 清晰图形：边缘利、对比高、路面明显（描边硬、无柔光）；
  C 细节丰富：树冠/田垄/碎石密度 ×1.6、整体偏深、噪点细。
输出 out/art/terrain_style/{A,B,C}.png（各 1024×1024）。Phase A 不出全图。
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "map_bagration_field.csv"
SCEN_PATH = ROOT / "data" / "scenarios" / "bagration_field.json"
OUT_DIR = ROOT / "out" / "art" / "terrain_style"

SS = 2                                   # 超采样倍数
BOARD_OUT = 1024
BOARD_SS = BOARD_OUT * SS                # 2048
# 风格板世界窗：中心 (108000,64000)，1024px ↔ 102400cm（1px=1000cm）
WIN_CX, WIN_CY = 108000, 64000
WIN_CM = 102400
CM_PER_PX = WIN_CM / BOARD_SS            # 世界 cm / 超采样 px

SEED = int(hashlib.sha256("bagration_field".encode()).hexdigest()[:8], 16)


# ── 几何装载（矢量行 → 世界 cm 折线/矩形/建筑）──

def load_geometry():
    roads, rects, buildings = [], [], []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = row["kind"]
            if k == "rect":
                t = 2500
                rects.append({"type": row["type"],
                              "poly": [(int(row["x0"]) * t, int(row["y0"]) * t),
                                       (int(row["x1"]) * t, int(row["y0"]) * t),
                                       (int(row["x1"]) * t, int(row["y1"]) * t),
                                       (int(row["x0"]) * t, int(row["y1"]) * t)]})
            elif k == "polyline":
                w = int(row["width"])
                verts = [tuple(int(v) * 2500 for v in p.split(":"))
                         for p in row["verts"].split(";")]
                roads.append({"width": w, "verts": verts})
            elif k == "building":
                buildings.append({"key": row["building_key"],
                                  "x": int(row["x_cm"]), "y": int(row["y_cm"]),
                                  "foot": int(row["footprint_cm"])})
    decor = json.loads(SCEN_PATH.read_text(encoding="utf-8"))["decor"]
    return roads, rects, buildings, decor


def mk_affine():
    """世界 cm → 超采样 px（窗口裁切 + y 翻转北=第 0 行）。"""
    def w2p(x_cm, y_cm):
        px = (x_cm - (WIN_CX - WIN_CM / 2)) / CM_PER_PX
        py = ((WIN_CY + WIN_CM / 2) - y_cm) / CM_PER_PX
        return px, py
    return w2p


def catmull_rom(pts, samples=24):
    """Catmull-Rom 平滑（世界坐标 → 平滑折线；端点复制补位）。"""
    if len(pts) < 3:
        return list(pts)
    p = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for j in range(samples):
            t = j / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(pts[-1])
    return out


def jitter_poly(poly, rng, amp):
    return [(x + rng.randint(-amp, amp), y + rng.randint(-amp, amp))
            for x, y in poly]


# ── 三风格画法（同几何、只变参数/后处理）──

STYLES = {
    "A": dict(          # 写实柔和
        sat=(0.82, 0.86), blur=3.2, edge_soft=14, warm=0.10,
        crown_density=1.0, crown_r=(7, 13), detail=0.7, contrast=0.92,
        grass=((0x56, 0x62, 0x40), (0x66, 0x6E, 0x46)),
        road=((0x8A, 0x7C, 0x5E), (0x9C, 0x8E, 0x6C)),
        forest=((0x2C, 0x3A, 0x27), (0x43, 0x55, 0x37), (0x25, 0x30, 0x20)),
        ruin=((0x59, 0x53, 0x4A), (0x77, 0x6C, 0x5C)),
        yard=(0x7C, 0x70, 0x58), wheat=((0x9C, 0x8C, 0x50), (0xAE, 0x9E, 0x5C)),
        stream=((0x4E, 0x5C, 0x64), (0x6C, 0x7C, 0x84)),
        grain=6),
    "B": dict(          # 清晰图形
        sat=(1.0, 1.0), blur=0.6, edge_soft=5, warm=0.05,
        crown_density=0.8, crown_r=(6, 11), detail=0.55, contrast=1.12,
        grass=((0x5A, 0x66, 0x42), (0x6C, 0x74, 0x48)),
        road=((0x96, 0x82, 0x5E), (0xAA, 0x96, 0x70)),
        forest=((0x2A, 0x3C, 0x26), (0x4A, 0x5E, 0x38), (0x22, 0x30, 0x1E)),
        ruin=((0x5C, 0x55, 0x4B), (0x7E, 0x72, 0x60)),
        yard=(0x82, 0x76, 0x5C), wheat=((0xA2, 0x90, 0x4E), (0xB4, 0xA2, 0x58)),
        stream=((0x4A, 0x5E, 0x6A), (0x72, 0x84, 0x8C)),
        grain=2),
    "C": dict(          # 细节丰富
        sat=(0.9, 0.9), blur=1.4, edge_soft=8, warm=0.07,
        crown_density=1.6, crown_r=(5, 12), detail=1.6, contrast=1.02,
        grass=((0x4E, 0x5A, 0x38), (0x5E, 0x66, 0x40)),
        road=((0x84, 0x74, 0x56), (0x94, 0x86, 0x64)),
        forest=((0x26, 0x34, 0x21), (0x3E, 0x50, 0x32), (0x1F, 0x2A, 0x1B)),
        ruin=((0x55, 0x4E, 0x45), (0x73, 0x68, 0x58)),
        yard=(0x76, 0x6A, 0x52), wheat=((0x96, 0x86, 0x4A), (0xA8, 0x98, 0x56)),
        stream=((0x4A, 0x58, 0x60), (0x68, 0x78, 0x80)),
        grain=10),
}


def _sat_adj(px, k):
    r, g, b = px
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return tuple(max(0, min(255, int(lum + (c - lum) * k))) for c in (r, g, b))


def render_board(style: str) -> Image.Image:
    st = STYLES[style]
    roads, rects, buildings, decor = load_geometry()
    rng = random.Random(SEED)
    w2p = mk_affine()
    img = Image.new("RGB", (BOARD_SS, BOARD_SS), st["grass"][0])
    dr = ImageDraw.Draw(img)

    # ── 草地基底：大 blob 混合（双色调大椭圆 + 细纹理在降采样后自然）──
    for _ in range(240):
        cx = rng.uniform(0, BOARD_SS)
        cy = rng.uniform(0, BOARD_SS)
        r = rng.uniform(90, 300) * SS
        col = st["grass"][rng.randrange(2)]
        blob = Image.new("RGBA", (int(r * 2), int(r * 2)), (0, 0, 0, 0))
        ImageDraw.Draw(blob).ellipse((0, 0, r * 2, r * 2),
                                     fill=col + (rng.randint(28, 60),))
        img.paste(Image.alpha_composite(Image.new("RGBA", blob.size),
                                        blob).convert("RGB"),
                  (int(cx - r), int(cy - r)), blob)

    # ── 麦田（decor.wheat 第二块东南角在本窗内西北留一块；窗口内裁剪绘制）──
    for poly in decor["wheat"]:
        pts = [w2p(x, y) for x, y in poly]
        if max(p[0] for p in pts) < -50 or min(p[0] for p in pts) > BOARD_SS + 50:
            continue
        jitter = [(x + rng.uniform(-8, 8) * SS, y + rng.uniform(-8, 8) * SS)
                  for x, y in pts]
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon(jitter, fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(6 * SS))
        wcol = st["wheat"][rng.randrange(2)]
        field = Image.new("RGB", img.size, wcol)
        img.paste(field, (0, 0), mask)
        dr.polygon(jitter, outline=(0x6A, 0x60, 0x40))       # 田埂
        for k in range(1, 4):                                 # 收割条纹
            f = k / 3.8
            sx = jitter[0][0] + (jitter[3][0] - jitter[0][0]) * f
            sy = jitter[0][1] + (jitter[3][1] - jitter[0][1]) * f
            ex = jitter[1][0] + (jitter[2][0] - jitter[1][0]) * f
            ey = jitter[1][1] + (jitter[2][1] - jitter[1][1]) * f
            dr.line((sx, sy, ex, ey),
                    fill=(min(255, wcol[0] + 16), min(255, wcol[1] + 12),
                          wcol[2]), width=max(1, int(1.2 * SS)))

    # ── 村庄场院：建筑周围模糊土色 blob + 连接土径 + 菜地条纹 ──
    yard_pts = [(b["x"], b["y"]) for b in buildings
                if 56000 < b["x"] < 128000 and 44000 < b["y"] < 80000]
    for bx, by in yard_pts:
        px, py = w2p(bx, by)
        if not (-100 < px < BOARD_SS + 100 and -100 < py < BOARD_SS + 100):
            continue
        r = rng.uniform(90, 150) * SS
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse(
            (px - r, py - r * 0.8, px + r, py + r * 0.8),
            fill=200)
        mask = mask.filter(ImageFilter.GaussianBlur(18 * SS))
        img.paste(Image.new("RGB", img.size, st["yard"]), (0, 0), mask)
    for a, b in zip(yard_pts, yard_pts[1:]):                # 连接土径
        p0, p1 = w2p(*a), w2p(*b)
        dr.line((p0, p1), fill=st["yard"], width=int(10 * SS))
        dr.line((p0, p1), fill=(0x6A, 0x5E, 0x46), width=int(1.4 * SS))
        for k in range(1, 6):                               # 菜地条纹
            f = k / 6
            mx, my = p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f
            dr.line((mx - 8 * SS, my - 5 * SS, mx + 8 * SS, my + 5 * SS),
                    fill=(0x4E, 0x5C, 0x34) if k % 2 else (0x6A, 0x6A, 0x3C),
                    width=max(1, SS))

    # ── 森林/废墟：矩形 → 抖动多边形掩膜 → 高斯羽化 → 内容散点 ──
    for rc in rects:
        poly = [w2p(x, y) for x, y in rc["poly"]]
        if max(p[0] for p in poly) < -60 or min(p[0] for p in poly) > BOARD_SS + 60:
            continue
        if max(p[1] for p in poly) < -60 or min(p[1] for p in poly) > BOARD_SS + 60:
            continue
        amp = 2 * 2500 / CM_PER_PX                          # ±2 tile
        jitter = [(x + rng.uniform(-amp, amp), y + rng.uniform(-amp, amp))
                  for x, y in poly]
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon(jitter, fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(
            st["edge_soft"] / 2 * SS))
        base_col = st["forest"][0] if rc["type"] == "FOREST" else st["ruin"][0]
        img.paste(Image.new("RGB", img.size, base_col), (0, 0), mask)
        # 掩膜内散点（树冠/碎砖）
        content = Image.new("RGBA", img.size, (0, 0, 0, 0))
        cdr = ImageDraw.Draw(content)
        xs = [p[0] for p in jitter]
        ys = [p[1] for p in jitter]
        n = int((max(xs) - min(xs)) * (max(ys) - min(ys))
                / (1400 * 1400) * st["crown_density"] * 60)
        for _ in range(max(8, n)):
            cx = rng.uniform(min(xs), max(xs))
            cy = rng.uniform(min(ys), max(ys))
            if rc["type"] == "FOREST":
                r = rng.uniform(*st["crown_r"]) * SS
                col = st["forest"][rng.choice((1, 1, 2))]
                cdr.ellipse((cx - r, cy - r * 0.8, cx + r, cy + r * 0.8),
                            fill=col + (rng.randint(140, 210),))
                if rng.random() < 0.14 * st["detail"]:
                    cdr.ellipse((cx - r * 0.2, cy + r * 0.5,
                                 cx + r * 0.2, cy + r * 0.8),
                                fill=(0xC6, 0xC6, 0xAE, 200))   # 桦干
            else:
                s = rng.uniform(3, 7) * SS * (0.7 + st["detail"] * 0.3)
                col = st["ruin"][1] if rng.random() < 0.6 \
                    else (0x3C, 0x36, 0x2E)
                cdr.rectangle((cx - s, cy - s * 0.7, cx + s, cy + s * 0.7),
                              fill=col + (rng.randint(150, 220),))
        img = Image.alpha_composite(img.convert("RGBA"), content).convert("RGB")
        dr = ImageDraw.Draw(img)

    # ── 溪流（decor.stream 平滑曲线；窗内南缘）──
    spts = [w2p(x, y) for x, y in decor["stream"]]
    smooth = catmull_rom([(x / 1.0, y / 1.0) for x, y in
                          [(p[0], p[1]) for p in spts]], 32)
    if smooth:
        bank_w, water_w = int(8 * SS), int(6 * SS)
        dr.line(smooth, fill=(0x6C, 0x6C, 0x5C), width=bank_w + 2)   # 岸
        dr.line(smooth, fill=st["stream"][0], width=water_w)          # 水
        for k in range(1, 9):                                          # 高光
            f = k / 9
            idx = int(f * (len(smooth) - 1))
            mx, my = smooth[idx]
            dr.line((mx - 5 * SS, my, mx + 5 * SS, my),
                    fill=st["stream"][1], width=max(1, SS))

    # ── 道路：连续 Catmull-Rom 折线 + 圆头 + 分层描边（禁止逐 tile）──
    for road in roads:
        pts = [w2p(x, y) for x, y in road["verts"]]
        if max(p[0] for p in pts) < -80 or min(p[0] for p in pts) > BOARD_SS + 80:
            continue
        smooth = catmull_rom(pts, 28)
        w_main = road["width"] * 5 * SS                    # w2→10px 输出
        dr.line(smooth, fill=(0x5A, 0x52, 0x42), width=int(w_main + 3 * SS),
                joint="curve")
        dr.line(smooth, fill=st["road"][0], width=int(w_main), joint="curve")
        dr.line(smooth, fill=st["road"][1], width=int(w_main * 0.4),
                joint="curve")
        for off in (-w_main * 0.24, w_main * 0.24):        # 车辙
            rut = [(x + off, y) for x, y in smooth]
            dr.line(rut, fill=(0x6C, 0x5E, 0x48), width=max(1, int(1.2 * SS)))
        r0 = smooth[0]
        dr.ellipse((r0[0] - w_main / 2, r0[1] - w_main / 2,
                    r0[0] + w_main / 2, r0[1] + w_main / 2), fill=st["road"][0])
        rn = smooth[-1]
        dr.ellipse((rn[0] - w_main / 2, rn[1] - w_main / 2,
                    rn[0] + w_main / 2, rn[1] + w_main / 2), fill=st["road"][0])
        # 溪流跨线检测：主南北路 (x=100000) 与溪（y≈15000）交点——窗内不可见，
        # 跳过桥缺口（全图阶段处理）

    # ── 全局后处理：暖色 overlay + 细噪 + 对比 + 模糊风格档 ──
    warm = Image.new("RGB", img.size, (0xB8, 0x9C, 0x6C))
    img = Image.blend(img, warm, st["warm"])
    if st["grain"]:
        grain = Image.new("L", (BOARD_SS // 8, BOARD_SS // 8))
        gp = grain.load()
        rr = random.Random(SEED + 7)
        for yy in range(grain.height):
            for xx in range(grain.width):
                gp[xx, yy] = 128 + rr.randint(-st["grain"], st["grain"])
        grain = grain.resize((BOARD_SS, BOARD_SS), Image.BICUBIC)
        img = Image.blend(img, Image.merge("RGB", (grain, grain, grain)), 0.10)
    if st["blur"]:
        img = img.filter(ImageFilter.GaussianBlur(st["blur"] * SS / 2))
    if st["contrast"] != 1.0:
        img = Image.eval(img, lambda v: max(0, min(
            255, int(128 + (v - 128) * st["contrast"]))))
    sat = sum(st["sat"]) / 2
    if sat != 1.0:
        px = img.load()
        for yy in range(0, img.height, 2):
            for xx in range(0, img.width, 2):
                px[xx, yy] = _sat_adj(px[xx, yy], sat)

    return img.resize((BOARD_OUT, BOARD_OUT), Image.LANCZOS)


def main(argv=None) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for tag in ("A", "B", "C"):
        board = render_board(tag)
        path = OUT_DIR / ("%s.png" % tag)
        board.save(path, format="PNG")
        print("%s：%s sha256=%s" % (
            tag, path.relative_to(ROOT),
            hashlib.sha256(path.read_bytes()).hexdigest()[:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
