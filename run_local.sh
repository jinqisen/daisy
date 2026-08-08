#!/bin/bash
# 本地启动 Daisy（不使用 Docker）
# 依赖：redis-server (brew install redis)、qdrant 二进制（见 .local/bin/qdrant）、
#       Python 依赖（miniconda python3）、前端 node_modules 已安装
#
# 用法：
#   ./run_local.sh start   # 启动全部服务
#   ./run_local.sh stop    # 停止全部服务
#   ./run_local.sh status  # 查看状态
#   ./run_local.sh logs    # 跟踪日志

set -e
ROOT="/Users/anykong/Daisy_Demo"
RUN="$ROOT/.local/run"
LOGS="$RUN/logs"
QDRANT_BIN="$ROOT/.local/bin/qdrant"
PY=python3
mkdir -p "$LOGS" "$RUN/qdrant_storage"

# 本地服务端口
export REDIS_HOST=127.0.0.1 REDIS_PORT=30018
export QDRANT_HOST=127.0.0.1 QDRANT_PORT=30019
export HOST=0.0.0.0 PORT=30021
export DAISY_PROMPTS_DIR="$ROOT/Daisy_prompts"
export EMOTION_MODEL_NAME="$ROOT/Daisy_server/model/bert-base-cased-goemotions-original"
export PYTHONPATH="$ROOT/Daisy_server"

start() {
  echo "[1/5] Redis :30018"
  redis-cli -p 30018 ping >/dev/null 2>&1 || \
    redis-server --port 30018 --daemonize yes --dir "$RUN" --logfile "$LOGS/redis.log"

  echo "[2/5] Qdrant :30019"
  curl -s http://127.0.0.1:30019/healthz >/dev/null 2>&1 || \
    QDRANT__SERVICE__HTTP_PORT=30019 QDRANT__SERVICE__GRPC_PORT=30022 \
    QDRANT__STORAGE__STORAGE_PATH="$RUN/qdrant_storage" QDRANT__TELEMETRY_DISABLED=true \
    nohup "$QDRANT_BIN" > "$LOGS/qdrant.log" 2>&1 &
  sleep 3

  # 注意：后端必须从项目根目录 $ROOT 启动（等价于 Docker 里的 /app），
  # 因为 config 里的路径如 ./Daisy_server/assets/character_cards/... 是相对项目根写的。
  # 模块导入依赖 PYTHONPATH=$ROOT/Daisy_server（已在上方 export）。
  echo "[3/5] Backend :30021"
  (cd "$ROOT" && nohup $PY -m app.main > "$LOGS/server.log" 2>&1 &)
  sleep 10

  echo "[4/5] Worker (ARQ)"
  (cd "$ROOT" && nohup $PY -m arq app.tasks.worker.WorkerSettings > "$LOGS/worker.log" 2>&1 &)

  echo "[5/5] Frontend :30020"
  (cd "$ROOT/Daisy_front" && nohup npm run dev > "$LOGS/frontend.log" 2>&1 &)
  sleep 3

  echo ""
  echo "=== 完成 ==="
  echo "前端:   http://localhost:30020   (用 localhost，不要用 127.0.0.1，vite 绑定 IPv6)"
  echo "后端:   http://127.0.0.1:30021/health"
}

stop() {
  pkill -f "app.main" 2>/dev/null || true
  pkill -f "arq app.tasks.worker" 2>/dev/null || true
  pkill -f "node.*vite" 2>/dev/null || true
  pkill -f "$QDRANT_BIN" 2>/dev/null || true
  redis-cli -p 30018 shutdown nosave 2>/dev/null || true
  echo "已停止全部服务。"
}

status() {
  echo -n "Redis    :30018  "; redis-cli -p 30018 ping 2>/dev/null || echo DOWN
  echo -n "Qdrant   :30019  "; curl -s http://127.0.0.1:30019/healthz 2>/dev/null && echo || echo DOWN
  echo -n "Backend  :30021  "; curl -s http://127.0.0.1:30021/health 2>/dev/null && echo || echo DOWN
  echo -n "Frontend :30020  "; curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:30020/ 2>/dev/null || echo DOWN
}

case "${1:-start}" in
  start)  start ;;
  stop)   stop ;;
  restart) stop; sleep 2; start ;;
  status) status ;;
  logs)   tail -f "$LOGS"/*.log ;;
  *) echo "用法: $0 {start|stop|restart|status|logs}"; exit 1 ;;
esac
