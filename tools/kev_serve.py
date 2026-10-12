#!/usr/bin/env python3
"""kev.serve 跨平台启动器：CUDA / Apple Silicon (MLX/MPS) / CPU 自动适配。

职责边界：kev.serve 自身已按平台选后端（Apple Silicon 缺省 MLX、其余 torch
bf16——见 kev/serve.py 模块 docstring）；本脚本不重复实现选型，只做三件事：
  1) 环境探测（--check）：python 版本 / uv / kev 仓库 / torch 后端（cuda|
     mps|cpu）/ mlx 可用性 → 打印将要执行的启动命令；
  2) 组装并启动（--start）：`uv run --extra serve python -m kev.serve`，
     subprocess **字面量参数列表 + shell=False**，不经 shell——Windows/
     Linux/macOS 同一路径；--model/--host 经字符白名单校验（纵深防御
     旗标注入），--port 恒为 int；
  3) 就绪探活：起服后轮询 /v1/systemone ping（sovs.ai.KevClient），模型
     加载完成才返回——首启要下载权重，--timeout 给足（缺省 600s）。

用法（在 SOV_SS 仓库根目录运行）：
  python tools/kev_serve.py --check                    # 只探测+打印计划
  python tools/kev_serve.py --start                    # 前台起服+探活
  python tools/kev_serve.py --start --model jaredpalmer/kev-0.5b --port 8011
  KEV_DIR=~/Developer/kev python tools/kev_serve.py --start

兼容性：stdlib-only；torch/mlx 探测为**惰性 import**（未装不影响 --check
其余项）。SOV_SS 侧（sovs.ai）永远不需要 torch——本脚本探测只为给出准确的
后端报告与环境纠偏提示。
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import time

DEFAULT_MODEL = "jaredpalmer/kev-0.5b"   # 用户拍板：0.5B 档（Qwen2.5 底座原型）
DEFAULT_PORT = 8011

# 参数白名单字符集（model 形如 jaredpalmer/kev-0.5b@rev；host 为域名/IP）——
# subprocess 恒为字面量列表 + shell=False，本校验是纵深防御：拒绝空白/元
# 字符/旗标前缀，防下游 kev.serve 把恶意值当选项解析。
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.@:/-]+$")


def _safe_token(value: str, what: str) -> str:
    if not value or not _TOKEN_RE.match(value) or value.startswith("-"):
        raise SystemExit(f"非法 {what}: {value!r}（仅允许字母数字与 _ . @ : / -，且不得以 - 开头）")
    return value


def probe_torch() -> str:
    """torch 后端报告：cuda / mps / cpu / 未安装。惰性 import，永不抛。"""
    try:
        import torch  # noqa: PLC0415（探测点局部导入——未装 torch 是合法状态）
    except Exception:
        return "未安装（服务端经 uv 环境自带，不影响本机 --check 其余项）"
    try:
        if torch.cuda.is_available():
            return f"cuda（{torch.cuda.get_device_name(0)}）"
        if getattr(torch.backends, "mps", None) is not None \
                and torch.backends.mps.is_available():
            return "mps（Apple Silicon GPU）"
    except Exception:
        pass
    return "cpu"


def probe_mlx() -> str:
    try:
        import mlx  # noqa: F401, PLC0415
        return "可用（Apple Silicon 上 kev.serve 缺省走 MLX）"
    except Exception:
        return "不可用（Apple Silicon 将回退 torch；Linux/CUDA 本就不用 MLX）"


def detect(kev_dir: str) -> dict:
    return {
        "系统": f"{platform.system()} {platform.machine()}（{platform.platform()}）",
        "Python": platform.python_version(),
        "uv": shutil.which("uv") or "未找到（安装：curl -LsSf https://astral.sh/uv/install.sh | sh）",
        "kev 仓库": (os.path.join(kev_dir, "pyproject.toml")
                     if os.path.isfile(os.path.join(kev_dir, "pyproject.toml"))
                     else f"未找到（git clone https://github.com/jaredpalmer/kev {kev_dir}）"),
        "torch 后端": probe_torch(),
        "MLX": probe_mlx(),
    }


def _plan(args) -> str:
    """启动命令的可读形式（与 Popen 字面量列表一一对应）。"""
    return (f"uv run --extra serve python -m kev.serve "
            f"--run {_safe_token(args.model, '--model')} "
            f"--host {_safe_token(args.host, '--host')} --port {args.port}")


def wait_ready(url: str, timeout_s: float, api_key: str | None) -> bool:
    """轮询 system_one ping 直到就绪/超时。返回 True=就绪。"""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sovs.ai.kev_client import KevClient, KevUnavailableError  # noqa: PLC0415
    client = KevClient(url, api_key=api_key, timeout_s=10.0)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            client.ping()
            return True
        except KevUnavailableError:
            time.sleep(2.0)
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="kev.serve 跨平台启动/探测器")
    ap.add_argument("--check", action="store_true", help="只探测环境并打印启动计划")
    ap.add_argument("--start", action="store_true", help="启动 kev.serve 并探活到就绪")
    ap.add_argument("--kev-dir", default=os.environ.get("KEV_DIR", "kev"),
                    help="kev 仓库目录（缺省 $KEV_DIR 或 ./kev）")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="就绪探活超时秒（首启含权重下载，给足）")
    ap.add_argument("--api-key", default=os.environ.get("KEV_API_KEY"),
                    help="服务端 API key（同时透传给子进程 KEV_API_KEY）")
    ap.add_argument("--dtype", choices=["bf16", "fp32"], default=None,
                    help="透传 KEV_DTYPE（缺省服务端 bf16；游戏决策可复现性锚在日志而非模型，bf16 即可）")
    args = ap.parse_args(argv)

    info = detect(args.kev_dir)
    print("── 环境探测 " + "─" * 30)
    for k, v in info.items():
        print(f"  {k:10s} {v}")
    try:
        plan = _plan(args)
    except SystemExit as e:
        print(f"!! {e}")
        return 2
    print("── 启动命令 " + "─" * 30)
    print(f"  {plan}   （cwd={args.kev_dir}）")
    ok = shutil.which("uv") is not None and info["kev 仓库"].endswith("pyproject.toml")
    if not ok:
        print("!! 环境未就绪：先安装 uv 并 clone kev 仓库（上面两行给了命令）")
        return 1
    if not (args.check or args.start):
        print("（--check 只看计划；--start 真正起服）")
        return 0
    if args.check:
        print("✓ 环境就绪，可 --start")
        return 0

    # --start：字面量列表 + shell=False；model/host 已过白名单、port 恒 int
    env = dict(os.environ)
    if args.api_key:
        env["KEV_API_KEY"] = args.api_key
    if args.dtype:
        env["KEV_DTYPE"] = args.dtype
    url = f"http://{args.host}:{args.port}"
    print(f"→ 启动中（{url}）……首启含权重下载可能数分钟")
    child = subprocess.Popen(
        ["uv", "run", "--extra", "serve", "python", "-m", "kev.serve",
         "--run", _safe_token(args.model, "--model"),
         "--host", _safe_token(args.host, "--host"),
         "--port", str(args.port)],
        cwd=args.kev_dir, env=env, shell=False)
    try:
        if wait_ready(url, args.timeout, args.api_key):
            print(f"✓ 服务就绪：{url}  （demo: python tools/kev_game_demo.py --url {url}）")
            print("  Ctrl+C 停止服务端")
            child.wait()
            return child.returncode or 0
        print(f"✗ {args.timeout:.0f}s 未就绪——查上方服务端日志（权重下载/显存不足）")
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
        return 1
    except KeyboardInterrupt:
        print("\n收到中断，停止服务端……")
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
        return 0


if __name__ == "__main__":
    sys.exit(main())
