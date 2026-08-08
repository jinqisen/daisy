# 项目总结报告 - 前端远程镜像构建

## 1. 任务概述
本任务旨在构建 `Daisy_front` 项目的 Docker 镜像，以便在远程服务器上部署。

## 2. 执行结果
- **状态**: 完成
- **产物**: `daisyFront_remote_20251231_124646.tar`
- **耗时**: 约 25 分钟 (包含多次迭代)

## 3. 问题与修复
### 3.1 Docker 未启动
- **现象**: 脚本报错 `error during connect`.
- **解决**: 启动 Docker Desktop。

### 3.2 环境变量未生效 (Critical)
- **现象**: 部署后前端请求指向 `127.0.0.1`，而不是 `.env` 配置的远程 IP。
- **原因**: PowerShell 执行 `npm run build` 时，未能自动将 `.env` 文件加载到进程环境变量中，导致 Vite 使用了 `config.ts` 中的默认值。
- **解决**: 修改 `build_remote_image.ps1`，手动解析 `.env` 中的 `VITE_API_BASE_URL` 并设置 `$env:VITE_API_BASE_URL`。

## 4. 技术细节
- 使用 Node.js/Vite 构建静态资源。
- 使用 Python 3.10-slim 作为基础镜像提供 HTTP 服务。
- 端口映射: 容器 80 -> 主机 30020 (由 .env 配置)。
