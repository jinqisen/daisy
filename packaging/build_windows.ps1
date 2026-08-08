# Windows 桌面 App 打包骨架(P3 预留,未在本机验证)。
# 结构与 build_macos.sh 对称:前端 → 后端 PyInstaller → Electron 打 NSIS 安装包。
#
# 前置(需在 Windows 上准备):
#   - Python 3 + 项目依赖 + pyinstaller  (pip install -r Daisy_server/requirements.txt pyinstaller fakeredis)
#   - Node/npm
#   - 注意:Windows 上无 redis-server 依赖(嵌入模式用 fakeredis),这是本地化改造的收益之一
#
# 未验证事项(移植时需处理):
#   - torch Windows wheel 的 dylib→dll 差异,PyInstaller 可能需要额外 --add-binary
#   - 模型/prompts 路径分隔符(spec 里用 os.path.join 已兼容)
#   - 代码签名(Windows 用 signtool + 证书)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> [1/4] 构建前端"
Push-Location Daisy_front
$env:VITE_API_BASE_URL = ""
npx vite build
Pop-Location

Write-Host "==> [2/4] PyInstaller 打包后端"
Push-Location packaging
python -m PyInstaller daisy_backend.spec --distpath ./dist --workpath ./build --noconfirm
Pop-Location

Write-Host "==> [3/4] 安装 Electron 依赖"
Push-Location desktop
npm install
Pop-Location

Write-Host "==> [4/4] electron-builder 打 NSIS 安装包"
Push-Location desktop
npm run dist:win
Pop-Location

Write-Host "完成。产物在 desktop/release/"
