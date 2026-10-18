#!/usr/bin/env bash
# SOV_SS Bagration demo launcher
# 用法：./demo.sh                （1280x800 窗口，直接开菜单）
#       ./demo.sh --size 1600x900
#       ./demo.sh --smoke        （无头自动跑一局到结算）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PY="${SOV_PYTHON:-}"
if [ -z "$PY" ]; then
  for c in \
    "/Users/tianhuatang/miniconda3/envs/unified/bin/python3" \
    "/Users/tianhuatang/miniconda3/bin/python3" \
    "$(command -v python3 || true)"; do
    [ -n "$c" ] || continue
    if "$c" -c "import arcade, yaml, PIL" >/dev/null 2>&1; then
      PY="$c"; break
    fi
  done
fi

if [ -z "$PY" ]; then
  echo "✗ 没找到带 arcade+yaml+PIL 的 Python。" >&2
  echo "  请先：conda activate unified，或 export SOV_PYTHON=/path/to/python" >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  set -- --size 1600x900
fi

echo "python: $PY"
exec "$PY" tools/skirmish_shell.py "$@"
