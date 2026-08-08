# 共识文档 - 前端远程镜像构建

## 1. 需求描述
用户需要构建 `Daisy_front` 项目的服务器端 Docker 镜像。
使用现有的 PowerShell 脚本 `scripts/build_remote_image.ps1` 完成此任务。

## 2. 技术实现方案
- **执行脚本**: `e:\Daisy\Daisy_Demo\Daisy_front\scripts\build_remote_image.ps1`
- **构建流程**:
    1. 解析 `.env` 获取配置。
    2. `npm install` 安装依赖。
    3. `npm run build` 生成 `dist` 目录。
    4. `docker build` 创建镜像 `daisy_front_remote:[Timestamp]`。
    5. `docker save` 导出镜像到 `image\remote` 目录。

## 3. 验收标准
- 脚本执行成功，无错误退出。
- `image\remote` 目录下生成新的 `.tar` 镜像文件。
- 镜像文件大小合理 (非空)。

## 4. 约束条件
- 必须在 Windows PowerShell 环境下执行。
- 需要 Docker Desktop 正在运行。
- 需要 Node.js 和 npm 环境。
