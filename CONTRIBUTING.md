# 贡献指南

感谢你对 Daisy 的关注！

## 如何贡献

### 报告 Bug

1. 在 [Issues](https://github.com/jinqisen/daisy/issues) 中搜索是否已有相同问题
2. 如果没有，新建 Issue，包含：
   - 运行环境（macOS 版本 / Docker 版本）
   - 复现步骤
   - 期望行为 vs 实际行为
   - 相关日志（`~/Library/Application Support/Daisy/log/system.log`）

### 提交代码

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 提交你的修改：`git commit -m "feat: 描述你的修改"`
4. 推送到你的 fork：`git push origin feature/your-feature`
5. 创建 Pull Request

### Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档
- `refactor:` 重构
- `test:` 测试
- `chore:` 构建/工具

### 代码风格

- Python: 遵循 PEP 8，使用 `black` 格式化
- TypeScript/React: 遵循项目已有的 ESLint 配置

### 开发环境

```bash
# 后端
cd Daisy_server
pip install -r requirements.txt
python -m app.main

# 前端
cd Daisy_front
npm install
npm run dev
```

## 项目结构约定

- `Daisy_server/app/core/` — 基础设施（配置、数据库、缓存、安全），不依赖业务模块
- `Daisy_server/app/services/` — 业务逻辑，每个子目录是一个独立服务
- `Daisy_server/app/api/` — HTTP 接口层，只做参数校验和路由，逻辑委托给 services
- `Daisy_prompts/` — YAML 格式的提示词模板，与代码分离
- `Daisy_front/src/components/` — React 组件，每个文件一个组件
