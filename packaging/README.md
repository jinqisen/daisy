# Daisy 桌面版打包

把 Daisy 从「5 进程 + 2 远程服务」的 server 架构,坍缩为**单进程零外部服务**的本地
桌面应用,并打包为 macOS `.dmg`(Windows 脚本已预留)。

## 架构对比

| | Server 部署 | 桌面版(EMBEDDED_MODE) |
|---|---|---|
| Redis | 独立进程 | 进程内 fakeredis |
| Qdrant | 独立进程 | 本地嵌入路径 |
| ARQ Worker | 独立进程 | 并入后端(asyncio 进程内分发) |
| 前端 | Vite 独立端口 | 后端同源托管(StaticFiles + SPA 回退) |
| 进程数 | 5 | **1** |

代码里由 `EMBEDDED_MODE` 一个开关控制,server 部署行为完全不变。

## 一键打包(macOS)

```bash
./packaging/build_macos.sh
```

> **国内网络注意**:Electron 二进制默认从 GitHub 下载,常见 `ETIMEDOUT` 失败。
> 构建脚本已内置 npmmirror 镜像;若手动执行 `npm install`,请先设置:
> ```bash
> export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
> export ELECTRON_BUILDER_BINARIES_MIRROR="https://npmmirror.com/mirrors/electron-builder-binaries/"
> ```
>
> **npm postinstall 拦截**:较新版本 npm 默认阻止依赖的 postinstall 脚本,而 Electron
> 靠 postinstall 下载真实二进制。表现为 `node_modules/electron/dist` 只有几百 KB、
> 缺少 `path.txt`,运行时报 "Electron failed to install correctly"。解决:
> ```bash
> cd desktop && npm approve-scripts electron && npm install
> ```
>
> **解压不完整**:若 `dist` 仍只有几百 KB(完整应约 248MB)、运行报
> `Library not loaded: @rpath/Electron Framework.framework`,说明 zip 下载完整但解压
> 失败。手动解压缓存里的 zip 即可:
> ```bash
> cd desktop
> ZIP=$(find ~/Library/Caches/electron -name "electron-v*darwin-arm64.zip" | head -1)
> rm -rf node_modules/electron/dist && mkdir -p node_modules/electron/dist
> unzip -q "$ZIP" -d node_modules/electron/dist
> printf 'Electron.app/Contents/MacOS/Electron' > node_modules/electron/path.txt
> ```
> 注意 `path.txt` **不能有结尾换行**(用 `printf` 而非 `echo`),否则 npm wrapper
> 报 `spawn ... ENOENT`。

流程:前端构建 → PyInstaller 打包后端 → Electron 打 `.dmg`
产物:`desktop/release/Daisy-<version>-arm64.dmg`

## 密钥策略:用户自填,包内不含任何 API Key

- 随包 `server_config.json` 的密钥字段为空(真实密钥只在 `.env`,不入包)
- 首次运行复制到 `~/Library/Application Support/Daisy/`
- 用户在应用内填入自己的 Key → `POST /api/config/llm_keys`,该接口会:
  1. 注入进程 `os.environ`
  2. 同步更新 `settings` 单例(部分模块读的是启动快照)
  3. 持久化到用户目录配置
  4. **热重载所有 provider** —— 流水线里 6+ 个内部 agent 立即生效,无需重启
- 因此分发包可公开发布;用户需自备 LLM API Key

## 用户数据位置(macOS)

`~/Library/Application Support/Daisy/`
- `daisy.db` — SQLite 主库
- `server_config.json` — 用户配置(含自填密钥)
- `qdrant_embedded/` — 本地向量记忆库

卸载应用不会删除此目录;需要重置时手动删除即可。

## 组件说明

| 文件 | 作用 |
|---|---|
| `daisy_backend.spec` | PyInstaller 配置。注意顶部把 `Daisy_server` 加进 `sys.path` —— 否则 `collect_submodules("app")` 返回空,app 包不会进包 |
| `../Daisy_server/desktop_main.py` | 桌面入口:强制 EMBEDDED_MODE、解析冻结环境资源路径、把可写数据指向用户目录 |
| `../desktop/main.js` | Electron 主进程:拉起后端 sidecar → 等 `/health` → 加载 UI |
| `build_macos.sh` | macOS 全流程 |
| `build_windows.ps1` | Windows 骨架(**未验证**,移植注意事项见文件内注释) |

## 已知事项

- **包体积约 1.4GB**,主因是 torch(397MB)+ 情绪模型 + transformers。若要显著瘦身,
  需评估把情绪分析改为轻量实现或远程调用。
- **首次启动约 15-30 秒**(加载 torch 与情绪模型),之后对话 DEEP 路径约 30 秒。
- 应用图标未提供,当前用 Electron 默认图标;放置 `desktop/build/icon.icns` 并在
  `desktop/package.json` 重新引用即可自定义。
- 代码签名/公证未做,首次打开需右键→打开(或 `xattr -dr com.apple.quarantine`)。
