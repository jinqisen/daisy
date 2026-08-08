#!/bin/bash

# Daisy Agent Local Deployment Script
# 
# 功能：
# 1. 清理 macOS 生成的 ._ 垃圾文件 (解决 Docker 构建权限问题)
# 2. 清理 Python 缓存文件 (__pycache__, .pyc)
# 3. 检查基础镜像是否存在，不存在则构建
# 4. 增量构建业务镜像 (daisy_server, daisy_worker)
# 5. 更新并重启服务

set -e # 遇到错误立即退出

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Starting Daisy Agent Local Deployment ===${NC}"

# 1. 清理垃圾文件 (Moved before pre-flight check to avoid syntax errors on metadata files)
echo -e "\n${YELLOW}[1/6] Cleaning up system garbage files...${NC}"
find . -type f -name "._*" -print -delete
echo "Cleaned macOS ._ metadata files."

# 0. 本地验证性编译 (Pre-flight Check)
echo -e "\n${YELLOW}[0/6] Running local pre-flight check...${NC}"

if [ -f "Daisy_server/server_config.json" ]; then
    if ! python3 - <<'PY'
import json
from pathlib import Path

cfg_path = Path("Daisy_server/server_config.json")
data = json.loads(cfg_path.read_text(encoding="utf-8"))
keys = ["MAAS_API_KEY", "HUAWEI_SEARCH_API_KEY", "SECRET_KEY"]
bad = {k: v for k, v in ((k, data.get(k)) for k in keys) if isinstance(v, str) and v.strip()}
if bad:
    print("server_config.json contains non-empty secrets:", ", ".join(sorted(bad.keys())))
    raise SystemExit(1)
PY
    then
        echo -e "${RED}Error: server_config.json contains plaintext secrets. Aborting deployment.${NC}"
        exit 1
    fi
fi

# 检查 Python 语法错误
if ! python3 -m compileall Daisy_server/app -q > /dev/null; then
    echo -e "${RED}Error: Syntax error detected in Python code! Aborting deployment.${NC}"
    exit 1
fi
echo "Python syntax check passed."

if python3 -c "import pytest" > /dev/null 2>&1; then
    echo "Running pytest..."
    python3 -m pytest Daisy_server -q
else
    echo -e "${YELLOW}Warning: pytest not installed. Skipping test run.${NC}"
fi

echo -e "\n${YELLOW}[2/6] Cleaning up Python cache files...${NC}"
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
echo "Cleaned Python cache files."

# 2. 检查基础镜像
echo -e "\n${YELLOW}[3/6] Checking base image (daisy_server:base)...${NC}"
if [[ "$(docker images -q daisy_server:base 2> /dev/null)" == "" ]]; then
    echo "Base image not found. Building it now..."
    echo "Note: This may take a while as it copies model files."
    docker build -f Daisy_server/Dockerfile.base -t daisy_server:base Daisy_server
    echo -e "${GREEN}Base image built successfully.${NC}"
else
    echo -e "${GREEN}Base image exists. Skipping build.${NC}"
fi

# 3.5 构建前端
echo -e "\n${YELLOW}[3.5/6] Building frontend...${NC}"
if command -v npm &> /dev/null; then
    cd Daisy_front
    if [ ! -d "node_modules" ]; then
        echo "Installing frontend dependencies..."
        npm install
    fi
    echo "Building frontend assets..."
    # Use environment variables from .env.local (automatically loaded by Vite)
    # VITE_API_BASE_URL should be defined in Daisy_front/.env.local for local development
    echo "Using configuration from .env files (priority: .env.local > .env)"
    npm run build
    cd ..
    # Cleanup dist metadata to avoid Docker build errors
    find Daisy_front/dist -type f -name "._*" -print -delete
    echo -e "${GREEN}Frontend built successfully.${NC}"
else
    echo -e "${RED}Warning: npm not found. Skipping frontend build.${NC}"
fi

# 3. 增量构建与服务更新
echo -e "\n${YELLOW}[4/6] Building application images...${NC}"
# 只重新构建变更的业务层，基础层会复用
docker-compose build daisy_server daisy_worker daisy_front

echo -e "\n${YELLOW}[5/6] Updating services...${NC}"
# -d 后台运行, --remove-orphans 清理未定义的容器
docker-compose up -d --remove-orphans daisy_server daisy_worker daisy_front

echo -e "\n${GREEN}=== Deployment Completed Successfully! ===${NC}"
echo "Frontend:   http://localhost:10000"
echo "API Server: http://localhost:30021"
echo "Check logs with: docker-compose logs -f daisy_server daisy_worker daisy_front"
