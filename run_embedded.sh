#!/bin/bash
# Daisy 单进程嵌入模式启动脚本(本地 C 端形态)
#
# 与 run_local.sh 的区别:零外部服务。
#   - Redis   → 进程内 fakeredis(EMBEDDED_MODE)
#   - Qdrant  → 本地嵌入路径(不设 QDRANT_HOST)
#   - Worker  → 并入后端(ARQ 任务走进程内 asyncio 分发)
# 只有一个 Python 进程,断网也能启动(仅对话时需要访问云端 LLM)。

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
RUN="$ROOT/.local/run"
LOGS="$RUN/logs"
mkdir -p "$LOGS"

export EMBEDDED_MODE=1
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-30021}"
export DAISY_PROMPTS_DIR="$ROOT/Daisy_prompts"
export EMOTION_MODEL_NAME="${EMOTION_MODEL_NAME:-$ROOT/Daisy_server/model/bert-base-cased-goemotions-original}"
export VECTOR_DB_PATH="${VECTOR_DB_PATH:-$RUN/qdrant_embedded}"
export PYTHONPATH="$ROOT/Daisy_server"
# 显式取消远程服务地址,避免 shell 环境残留(.env 里的值由 EMBEDDED_MODE 在代码内清空)
unset QDRANT_HOST REDIS_HOST

cmd="${1:-start}"
PIDFILE="$RUN/embedded.pid"

case "$cmd" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "已在运行 (pid $(cat "$PIDFILE"))"; exit 0
    fi
    echo "启动单进程后端 (EMBEDDED_MODE) :$PORT ..."
    (cd "$ROOT" && nohup python3 -m app.main > "$LOGS/embedded.log" 2>&1 &)
    sleep 1
    pgrep -f "app.main" | head -1 > "$PIDFILE"
    echo "日志: $LOGS/embedded.log"
    echo "健康检查: curl http://$HOST:$PORT/health"
    ;;
  stop)
    pkill -f "app.main" 2>/dev/null && echo "已停止" || echo "未在运行"
    rm -f "$PIDFILE"
    ;;
  status)
    if curl -s -m 3 "http://$HOST:$PORT/health" >/dev/null 2>&1; then
      echo "后端 :$PORT  $(curl -s http://$HOST:$PORT/health)"
    else
      echo "后端 :$PORT  DOWN"
    fi
    ;;
  *)
    echo "用法: $0 {start|stop|status}"; exit 1
    ;;
esac
