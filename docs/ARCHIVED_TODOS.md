# 已归档的 TODO(前提不再成立)

本文件记录**因架构变更而失效**的历史 TODO。它们不是"没做完",而是"不需要做了"——
单独列出以免后来者按图索骥、浪费时间。

## 背景:架构已从 server 部署转为单机桌面应用

2026-07 完成本地化改造后:

| | 改造前 | 改造后 |
|---|---|---|
| 部署 | Docker Compose,5 个进程 | **单进程,零外部服务** |
| Redis | 独立容器 | 进程内 fakeredis |
| Qdrant | 独立容器 | 本地嵌入路径 |
| Worker | 独立 ARQ 进程 | 并入后端 |
| 前端 | Vite 独立端口 | 后端同源托管 |
| 用户体系 | 注册/登录 + 白名单 | **免登录本地单用户** |

由 `EMBEDDED_MODE` 开关控制;server 部署模式的代码仍保留可用。

---

## 归档清单

### 1. 白名单管理 —— `docs/Whitelist_Management/`
**失效原因**:白名单用于控制"谁能注册"。桌面版免登录、本地单用户,该概念不存在;
后端已在嵌入模式关闭 `/api/admin/whitelist`(返回 404),前端也隐藏了管理页。

> 若未来恢复 server 部署,该模块仍可用,届时再解冻。

### 2. Docker GPU 支持 —— `docs/docker_gpu_support/`
**失效原因**:已完全移除 Docker。本地 GPU 加速如有需要,应改为在桌面应用内直接
配置 torch device,与容器无关。

### 3. 前端远程构建 —— `docs/Frontend_Remote_Build/`
**失效原因**:前端产物现由 `packaging/build_macos.sh` 本地构建并打进安装包,
不再需要远程构建流程。

### 4. 华为云迁移 —— `docs/Huawei_Migration/`
**失效原因**:迁移已完成,且桌面版改为**用户自填 API Key**(包内不含任何密钥),
provider 可在应用内切换,不再是部署期决策。

### 5. 重建前端 / 远程部署相关 —— `docs/rebuild_frontend/`
**失效原因**:同 3,构建流程已固化进打包脚本。

---

## 仍然有效、未完成的设计项

以下**不在归档之列**,已转为可执行的差距清单,见
`Daisy_server/tests/test_spec_gaps.py`(未实现项以 `xfail` 标记,持续可见):

| 项 | 来源 | 状态 |
|---|---|---|
| Reflexion 自动优化路由规则 | 规格 §5.2 | 未实现(规格自注"长期") |
| Reflexion 回写 dialogue_examples | 规格 §5.2 | 未实现 |
| RL 策略有效训练 | — | 权重对不同输入无差异 |
| multi_agent 接入主链路 | `Refactor_Multi_Agent` | 未接入(现走 fusion 引擎) |
| 动态 Agent 加载(DB/YAML) | `Refactor_Multi_Agent` | 未实现 |
| 群聊路由 Agent | `Refactor_Multi_Agent` | 未实现 |
| Prompt 热重载 / A/B 框架 / YAML 校验 | `Prompt_Management` | 未实现 |
| 性能目标(80% 对话 3 秒内) | 规格 §4.0 | 未达成 |

**注**:性能目标原计划用流式输出改善**感知延迟**,该方案已被否决 ——
逐字流式与真人分条回复的习惯不符,项目现有的 `response_parts`(把回复拆成多条
依次发送)更贴近真实聊天。改善方向应为模型选型与链路优化。
