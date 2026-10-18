#!/usr/bin/env python3
"""FE-05 视觉 QA 工具（F0）：截图区域像素统计与基线差分（PIL）。

结论先行：本模块仅供 tools/ 与 tests/ 消费（sovs/ui 禁 PIL——AST 守卫），
为 FE-05 逐块 diff 门禁（单位区/命令格/面板区阈值判据）提供共用实现。
坐标口径：box=(x0, y0, x1, y1)，PIL 像素系（原点左上、y 向下）——与
out/qa/*.png 截图同系；越界自动钳回图内，空区返回 0/[]。
"""
from __future__ import annotations

from PIL import Image


def _crop(img: Image.Image, box):
    x0, y0, x1, y1 = box
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(img.width, int(x1)), min(img.height, int(y1))
    return img.crop((x0, y0, max(x0, x1), max(y0, y1)))


def colors_in_region(png: str, box) -> list:
    """区域内去重色列表（RGB 元组；空区 → []）。"""
    with Image.open(png) as im:
        return sorted({p for p in _crop(im.convert("RGB"), box).getdata()})


def count_pixels(png: str, box, pred) -> int:
    """区域内满足谓词 pred(rgb_tuple) 的像素数。"""
    with Image.open(png) as im:
        return sum(1 for p in _crop(im.convert("RGB"), box).getdata() if pred(p))


def non_bg_ratio(png: str, box, bg=(26, 30, 26)) -> float:
    """区域内非底色像素占比（bg=palette.BACKGROUND RGB）。"""
    with Image.open(png) as im:
        region = _crop(im.convert("RGB"), box)
        total = region.width * region.height
        if total == 0:
            return 0.0
        hits = sum(1 for p in region.getdata() if p != tuple(bg))
        return hits / total


def diff_ratio(a: str, b: str, box, tol: int = 8) -> float:
    """两图同区域差异像素占比（任一通道差 > tol 即差异；尺寸不同按小区裁）。"""
    with Image.open(a) as ia, Image.open(b) as ib:
        ra = _crop(ia.convert("RGB"), box)
        rb = _crop(ib.convert("RGB"), box)
        w, h = min(ra.width, rb.width), min(ra.height, rb.height)
        total = w * h
        if total == 0:
            return 0.0
        pa, pb = ra.load(), rb.load()
        diff = 0
        for y in range(h):
            for x in range(w):
                ca, cb = pa[x, y], pb[x, y]
                if (abs(ca[0] - cb[0]) > tol or abs(ca[1] - cb[1]) > tol
                        or abs(ca[2] - cb[2]) > tol):
                    diff += 1
        return diff / total
