# DESIGN_rebuild_frontend

## 1. 执行流程设计

```mermaid
graph TD
    A[开始] --> B[读取 .env 配置]
    B --> C[执行 npm install]
    C --> D[执行 npm run build]
    D --> E[执行 docker build]
    E --> F[执行 docker save]
    F --> G[生成 .tar 镜像包]
    G --> H[结束]
```

## 2. 关键组件
- **PowerShell 脚本**: 自动化构建流程的核心控制器。
- **Node.js/npm**: 前端构建工具。
- **Docker**: 容器化和镜像打包工具。

## 3. 验证策略
- 检查脚本退出代码 (Exit Code)。
- 检查 `image/remote` 目录下是否生成了新的文件。
