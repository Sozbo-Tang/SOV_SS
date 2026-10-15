"""GL 显示会话探针（共享）——屏幕枚举＋**建窗实试**双检。

结论先行：旧探针只数屏幕（`get_screens()`），在「屏幕可枚举但 WindowServer
不可达」的瞬态（macOS 合盖/锁屏/会话切换边缘）会放行测试类进 setUpClass，
再在建窗处 IndexError——整类 ERROR 而非 SKIP（2026-10-13 门禁实撞：19 errors）。
本探针在枚举通过后**实际建一座 64×48 隐藏窗并即刻关闭**：建得起来=显示会话
真可用；任何异常=按既有口径整类跳过（tests/test_shell_window.py:19-27 头注
记载的失败模式）。探针自身零残留（close 后无全局窗）。
"""
from __future__ import annotations

_CACHE: bool | None = None      # 进程内单次实试（四测试文件共享——少建探针窗）


def gl_window_available() -> bool:
    """显示会话真可用性探针：import arcade＋屏幕枚举＋隐藏窗实试三关全过才 True。
    进程内记忆化（首问实试，其后直读——显示会话中途恢复不追认，保守跳过即可）。"""
    global _CACHE
    if _CACHE is None:
        _CACHE = _probe_once()
    return _CACHE


def _probe_once() -> bool:
    try:
        import arcade
        import pyglet.display
        if len(pyglet.display.get_display().get_screens()) == 0:
            return False
        win = arcade.Window(64, 48, "gl-probe", visible=False,
                            vsync=False, antialiasing=False)
        try:
            win.close()
        except Exception:                          # noqa: BLE001（关不掉也不影响判定）
            pass
        return True
    except Exception:                              # noqa: BLE001（缺渲染栈/无显示会话=不可用）
        return False
