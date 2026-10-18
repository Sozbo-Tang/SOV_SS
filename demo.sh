#!/usr/bin/env bash
# SOV_SS Bagration demo launcher
# 用法：./demo.sh                    （1600x900，进主菜单）
#       ./demo.sh --size 1280x800
#       ./demo.sh --smoke            （无头自动跑一局到结算）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PY="${SOV_PYTHON:-}"
if [ -z "$PY" ]; then
  for c in "$(command -v python3 || true)" "$(command -v python || true)"; do
    [ -n "$c" ] || continue
    if "$c" -c "import arcade, yaml, PIL" >/dev/null 2>&1; then
      PY="$c"; break
    fi
  done
fi

if [ -z "$PY" ]; then
  cat >&2 <<'EOF'
✗ 没找到带 arcade + yaml + PIL 的 Python。

  首次准备（Python 3.13）：
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[fe]"

  或指定解释器：
    SOV_PYTHON=/path/to/python ./demo.sh
EOF
  exit 1
fi

if [ "$#" -eq 0 ]; then
  set -- --size 1600x900
fi

echo "python: $PY"
exec "$PY" tools/skirmish_shell.py "$@"
