#!/usr/bin/env bash
# dbmanager 停止 / 释放端口占用 (Linux / macOS)
# 仅终止命令行含 app.py 的 dbmanager 进程, 不会误杀其他程序。
# 优先级: PID 文件(dbmanager.pid) -> 端口占用扫描(fuser)
set -euo pipefail
cd "$(dirname "$0")"

PORT="${DBM_PORT:-8770}"
PID_FILE="dbmanager.pid"

if [ "${DBM_NO_KILL:-0}" = "1" ]; then
  echo "[跳过] DBM_NO_KILL=1 已设置, 不执行停止。"
  exit 0
fi

stop_pid() {
  local pid="$1"
  if ! kill -0 "$pid" 2>/dev/null; then return 0; fi
  local cmd
  cmd="$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null || ps -p "$pid" -o command= 2>/dev/null || true)"
  if echo "$cmd" | grep -q "app.py"; then
    echo "  [终止] PID=$pid : $cmd"
    kill -9 "$pid" 2>/dev/null || true
  else
    echo "  [跳过] PID=$pid 不是 dbmanager (命令行: $cmd)"
  fi
}

echo "正在停止 dbmanager (端口 $PORT)..."

# 1) PID 文件优先
if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  stop_pid "$PID"
  rm -f "$PID_FILE"
fi

# 2) 端口占用兜底扫描
if command -v fuser >/dev/null 2>&1; then
  PIDS="$(fuser "$PORT/tcp" 2>/dev/null || true | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true)"
  for p in $PIDS; do
    stop_pid "$p"
  done
fi

echo "[完成] 若端口此前被 dbmanager 占用, 现已释放。"
