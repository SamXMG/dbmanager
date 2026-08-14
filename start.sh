#!/usr/bin/env bash
# dbmanager 一键部署启动 (Linux / macOS)
# 用法: ./start.sh          正常启动(前端已构建则跳过构建)
#       DBM_FORCE_FE=1 ./start.sh   强制重建前端
#       DBM_PORT=9000 ./start.sh    指定端口
set -euo pipefail
cd "$(dirname "$0")"

PORT="${DBM_PORT:-8770}"
PY="${PYTHON:-python3}"
LOG_DIR="logs"
PID_FILE="dbmanager.pid"

echo "== dbmanager 一键部署启动 (端口 $PORT) =="

# 1) 后端依赖(幂等)
echo "[1/3] 安装后端依赖..."
"$PY" -m pip install -r requirements.txt

# 2) 前端构建: 仅当 dist 缺失 或 DBM_FORCE_FE=1
if [ "${DBM_FORCE_FE:-0}" = "1" ] || [ ! -f frontend/dist/index.html ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "[2/3] 构建前端 (Vue3)..."
    ( cd frontend && npm ci && npm run build )
  else
    echo "[2/3] 未找到 node/npm, 跳过前端构建 (将使用已有 dist, 若不存在则访问无 UI)"
  fi
else
  echo "[2/3] 前端已构建, 跳过 (设 DBM_FORCE_FE=1 可强制重建)"
fi

# 3) 后台启动: PID 文件 + 日志
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/dbmanager.log"
echo "[3/3] 后台启动 dbmanager, 日志: $LOG"
nohup "$PY" app.py >"$LOG" 2>&1 &
echo $! > "$PID_FILE"
echo "已启动 PID $(cat "$PID_FILE")."
echo "  访问: http://127.0.0.1:$PORT"
echo "  停止: ./stop.sh"
