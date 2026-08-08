#!/bin/sh
# run_worker.sh
# 启动 ARQ Worker
# 依赖环境变量配置

# 设置 Python 路径
export PYTHONPATH=/app:/app/Daisy_server

# 启动 worker
# arq app.tasks.worker.WorkerSettings
arq app.tasks.worker.WorkerSettings
