#!/bin/bash
# macOS 桌面 App 打包全流程:前端构建 → 后端 PyInstaller → Electron 打 .dmg
#
# 产物:desktop/release/Daisy-<version>-arm64.dmg
# 依赖:python3(含项目依赖 + pyinstaller)、node/npm、Apple Silicon
#
# 【密钥策略:用户自填,包内不含任何 API Key】
#   - 随包的 server_config.json 密钥字段为空(项目约定,真实密钥只在 .env,不入包)
#   - 首次运行时该文件被复制到 ~/Library/Application Support/Daisy/
#   - 用户在应用内填入自己的 API Key → POST /api/config/llm_keys
#     → 注入进程 env + 持久化到用户目录 + 热重载 provider(全链路 agent 立即生效)
#   - 因此分发包可公开发布,不泄露密钥;用户需自备 LLM API Key
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

resolve_python() {
  if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
    echo "$PYTHON_BIN"
    return
  fi
  if command -v python >/dev/null 2>&1 && python -m PyInstaller --version >/dev/null 2>&1; then
    echo python
    return
  fi
  if command -v python3 >/dev/null 2>&1 && python3 -m PyInstaller --version >/dev/null 2>&1; then
    echo python3
    return
  fi
  echo "未找到可用的 PyInstaller Python 解释器。可通过 PYTHON_BIN=/path/to/python 指定。" >&2
  exit 1
}

PYTHON_BIN="$(resolve_python)"
echo "==> 使用 Python: $PYTHON_BIN"

echo "==> [1/5] 拉取本地模型(构建期完成,避免用户使用时才下载)"
# 模型原先用 HF Hub ID 在运行时按需下载:开发机有缓存所以从未暴露,
# 而用户拿到的安装包是干净的 —— 第一次用到长期记忆要联网拉 1.3GB,断网直接失败。
"$PYTHON_BIN" packaging/fetch_models.py

echo "==> [2/5] 构建前端(相对同源 API base)"
( cd Daisy_front && VITE_API_BASE_URL="" npx vite build )
# 清理 macOS 元数据,避免打包报错
find Daisy_front/dist -name "._*" -delete 2>/dev/null || true

echo "==> [3/5] PyInstaller 打包后端"
( cd packaging && "$PYTHON_BIN" -m PyInstaller daisy_backend.spec \
    --distpath ./dist --workpath ./build --noconfirm )

echo "==> [4/5] 安装 Electron 依赖"
# Electron 二进制默认从 GitHub 下载,国内常 ETIMEDOUT,故默认走 npmmirror 镜像。
# 如在境外网络或希望用官方源,设置 DAISY_NO_MIRROR=1 跳过。
if [ -z "$DAISY_NO_MIRROR" ]; then
  export ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}"
  export ELECTRON_BUILDER_BINARIES_MIRROR="${ELECTRON_BUILDER_BINARIES_MIRROR:-https://npmmirror.com/mirrors/electron-builder-binaries/}"
  ( cd desktop && npm install --registry=https://registry.npmmirror.com )
else
  ( cd desktop && npm install )
fi

echo "==> [5/5] electron-builder 打 .dmg"
( cd desktop && npm run dist:mac )

echo ""
echo "完成。产物:"
ls -lh "$ROOT/desktop/release/"*.dmg 2>/dev/null || echo "  (未找到 .dmg,检查上面的 electron-builder 输出)"
