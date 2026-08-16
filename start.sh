#!/usr/bin/env bash
# DB Manager 一键启动脚本 (Linux / macOS)
# 作用: 自动装后端依赖 + 编译前端静态产物 + 后台启动 (前端由 Python http.server 直接 serve, 无 node 服务器)
#
# 用法:
#   ./start.sh            # 一键后台启动, 自动打开浏览器
#   ./start.sh --fg       # 前台启动 (调试, 关终端即停)
#   ./start.sh stop       # 停止
#   ./start.sh restart    # 重启
#   ./start.sh status     # 状态
#   ./start.sh build      # 仅构建前端
#
# 环境变量:
#   DBM_PORT      端口 (默认 8770)
#   DBM_FORCE_FE  1 = 强制重建前端
set -euo pipefail

cd "$(dirname "$0")"

# 自动打开浏览器 (Linux / macOS)
open_browser() {
  local url="http://127.0.0.1:${DBM_PORT:-8770}"
  if command -v xdg-open >/dev/null 2>&1; then
    (xdg-open "$url" >/dev/null 2>&1 &) || true
  elif command -v open >/dev/null 2>&1; then
    (open "$url" >/dev/null 2>&1 &) || true
  fi
}

case "${1:-}" in
  stop|status|restart|build)
    exec python3 manage.py "$1" "${@:2}"
    ;;
  --fg)
    exec python3 manage.py start --fg
    ;;
  "")
    python3 manage.py start
    open_browser
    ;;
  *)
    echo "用法: ./start.sh [--fg|stop|restart|status|build]"
    exit 1
    ;;
esac
