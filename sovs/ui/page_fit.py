"""FE-05 R4 页面自适应：menu/config/deck_edit/settings 四页设计画布缩放。

结论先行：四页（战前/菜单族）布局坐标按 **1280×800 设计画布** 书写；窗口
更大时以 arcade.Camera2D 等比缩放居中（min 比例，letterbox 区被整页背景
cover 填满——背景画在相机外整窗坐标）。battle/deploy 的 HUD 已按锚定
布局（右对齐/左下），不经本模块。只 import arcade＋stdlib（AST 守卫②）。

量纲：scale=clamp(min(w/1280, h/800), 0.5, 2.0)——1600×900→1.125、
1280×800→1.0（恒等，渲染路径直接跳过相机保逐像素一致）。**非等比拉伸
禁止**（min 比例锁 1280:800=1.6 宽高比——任何「拉伸填满」的改法即错）。
camera(win) 按窗口实例缓存（跨窗复用旧 GL 对象会崩——NinePatch 同坑）；use
后由调用方恢复 win.default_camera。to_design=屏幕→设计（鼠标命中面转换）。
"""
from __future__ import annotations

import arcade

DESIGN_W, DESIGN_H = 1280, 800       # 设计画布（四页布局坐标的事实量纲）
_SCALE_MIN, _SCALE_MAX = 0.5, 2.0    # R4.1：下限 0.75→0.5（960×600 最小窗
                                      # 档 min(0.75,0.75)=0.75 命中；更小窗
                                      # 仍等比缩小不裁切——配合窗口最小尺寸门）


def scale(win) -> float:
    """等比缩放系数（纯算术无 GL——窗口比设计画布的 min 比例，钳 0.75..2）。"""
    return max(_SCALE_MIN,
               min(_SCALE_MAX,
                   min(win.width / DESIGN_W, win.height / DESIGN_H)))


def camera(win):
    """四页内容相机（按窗口实例缓存——Camera2D 持创建窗 GL 上下文对象，
    跨窗复用会撞 GL 错误（多测试类开关窗场景；resize 换新相机））：
    viewport=整窗、position=设计中心、zoom=scale。Camera2D 无上下文管理器
    （arcade 3.3 实证）——调用方 use() 后画完须 win.default_camera.use()。"""
    size = (win.width, win.height)
    cam = getattr(win, "_page_fit_cam", None)
    if cam is None or getattr(win, "_page_fit_cam_size", None) != size:
        cam = arcade.Camera2D(viewport=arcade.LRBT(0, size[0], 0, size[1]),
                              position=(DESIGN_W / 2, DESIGN_H / 2),
                              zoom=scale(win))
        win._page_fit_cam = cam
        win._page_fit_cam_size = size
    return cam


def to_design(win, x: float, y: float) -> tuple:
    """屏幕坐标 → 设计画布坐标（MENU_PAGES 鼠标命中面转换；Vec3 取 xy）。"""
    return tuple(camera(win).unproject((x, y)))[:2]


def content_rect(win):
    """设计画布在屏幕上的矩形 (x0,y0,x1,y1)（调试/测试锚）：
    以屏幕中心居中、边长=设计边长×scale（letterbox 外区由整页背景填）。"""
    s = scale(win)
    w, h = DESIGN_W * s, DESIGN_H * s
    cx, cy = win.width / 2, win.height / 2
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
