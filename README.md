# Daisy — AI 伴侣

> 一个开源的、可本地运行的 AI 伴侣应用，支持桌面端（macOS）和 Docker 部署。

Daisy 是一个基于大语言模型的 AI 伴侣系统，具备长期记忆、情感感知、多人格切换、反思学习等能力。她不是一个简单的聊天机器人——她记得你说过的话，理解你的情绪，并随着互动逐渐了解你。

## 特性

- **🧠 长期记忆** — 基于向量检索 + 摘要压缩，记住关键对话
- **💕 情感感知** — 28 维情绪识别，实时感知你的情绪状态
- **🎭 多角色人格** — 内置男/女两种角色，支持动态人格权重调整
- **🔄 Reflexion 反思** — 从失败对话中学习，自动生成补丁改善回复质量
- **📊 分析面板** — 可视化情绪趋势、亲密度变化、人格演变
- **🔒 隐私优先** — 所有数据存储在本地，不依赖云端
- **🖥️ 桌面应用** — 原生 macOS 应用（基于 Electron），开箱即用
- **🐳 Docker 部署** — 支持 server 模式部署，多用户访问

## 架构概览

```
Daisy_Demo/
├── Daisy_server/     # FastAPI 后端 (Python)
│   ├── app/
│   │   ├── agents/        # AI Agent 定义
│   │   ├── api/           # REST API 路由
│   │   ├── core/          # 配置、数据库、LLM、安全
│   │   ├── models/        # 数据库模型
│   │   ├── services/      # 业务逻辑层
│   │   │   ├── persona/       # 人格管理
│   │   │   ├── memory/        # 长期记忆
│   │   │   ├── emotion/       # 情感识别
│   │   │   ├── learning/      # Reflexion 反思学习
│   │   │   └── system/        # 系统服务
│   │   ├── workflow/      # 对话工作流编排
│   │   └── tasks/         # 后台任务 (ARQ)
│   ├── assets/            # 角色卡等静态资源
│   └── model/             # 本地模型 (需构建时下载)
├── Daisy_front/      # React 前端 (TypeScript + Ant Design)
├── Daisy_prompts/    # YAML 提示词模板库
├── Daisy_skills/     # 技能系统 (MCP 扩展)
├── desktop/          # Electron 桌面壳
│   └── main.js       # 启动后端 → 等待就绪 → 加载窗口
├── packaging/        # PyInstaller 打包脚本
└── docs/             # 设计文档
```

## 快速开始

### 桌面版（macOS, Apple Silicon）

1. 下载最新的 `Daisy-*.dmg` 从 [Releases](https://github.com/jinqisen/daisy/releases)
2. 双击安装，拖入 Applications
3. 首次打开时，输入你的 LLM API Key（华为云 / 硅基流动 / OpenAI）
4. 开始对话

### 从源码运行（开发模式）

**前置要求：**
- Python 3.10+
- Node.js 18+
- （可选）Redis + Qdrant（Docker 提供）

```bash
# 克隆仓库
git clone https://github.com/jinqisen/daisy.git
cd daisy

# 后端
cd Daisy_server
pip install -r requirements.txt
cp ../.env.example .env
# 编辑 .env，填入你的 LLM API Key
python -m app.main

# 前端（另一个终端）
cd Daisy_front
npm install
npm run dev
```

### Docker 部署

```bash
cp .env.example Daisy_server/.env
# 编辑 Daisy_server/.env，填入 LLM API Key
docker-compose up -d
```

访问 http://localhost:30021

## 配置 LLM

Daisy 不内置任何 API Key。你需要至少配置一个 LLM 提供商：

| 提供商 | 环境变量 | 申请地址 |
|--------|---------|---------|
| 华为云 ModelArts | `MAAS_API_KEY` | [console.huaweicloud.com](https://console.huaweicloud.com/modelarts/) |
| 硅基流动 | `SILICONFLOW_API_KEY` | [siliconflow.cn](https://cloud.siliconflow.cn/account/ak) |
| OpenAI | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |

在桌面版中，首次启动会自动弹出配置界面；server 部署请在 `.env` 中设置。

## 项目文档

- [架构设计](./docs/Project_Assessment/)
- 各模块设计文档见 `docs/` 目录

## 贡献

欢迎贡献！请先阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 许可证

[MIT](./LICENSE) — 本项目仅供非商业用途。商业使用请联系作者获取授权。

---

*Daisy 是一个 AI 伴侣，不是人类伴侣。请理性使用。*
