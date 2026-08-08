# Feature 全量盘点(实测核验)

盘点日期:2026-08-02
核验对象:`/Applications/Daisy.app`(打包版,全新安装 + 清空用户数据)
证据来源:运行时日志、接口探活、数据库落库、真实对话轨迹。**代码存在不算落盘,跑到才算。**

判定口径:

| 标记 | 含义 |
|---|---|
| ✅ 已落盘 | 有运行时证据(日志/接口/落库)证明真实执行 |
| ⚠️ 有条件 | 代码完整,但需额外前提才生效,当前配置下不可用 |
| 🔶 存在未达 | 代码在,但当前无触发路径 |
| ❌ 死代码 | 注册了但不可达 |

---

## A. 对话工作流(LangGraph)

单次真实对话(DEEP 路由)的节点执行序列全部来自 `audit.log`:

| Feature | 状态 | 证据 |
|---|---|---|
| 三档路由(FAST/STANDARD/DEEP) | ✅ | `Router decision: DEEP (Judge)` / `STANDARD (Judge)`;实测 DEEP 28~38s、STANDARD 3.8s |
| 路由结果缓存 | ✅ | `@cache_node(key_prefix="router", ttl=600)` |
| 线下见面意图强制走 DEEP | ✅ | `is_offline_meetup_intent` 前置短路 |
| 情感分析(Ekman + 上下文) | ✅ | `START_NODE: analyze_emotion` → `情感与投入度分析 (Ekman + 上下文)`,4.4s |
| 情感翻译(中→英再做情感识别) | ✅ | `LLM Request [EmotionTranslator]` |
| 沟通风格分析 | ✅ | `START_NODE: analyze_communication_style`,10.2s |
| 人格选择策略(LLM 模式) | ✅ | `执行沟通策略: LLM` → `LLM Request [StrategyAgent]` |
| 风格分析(六人格权重) | ✅ | `Task 2: 开始风格分析`,`Storge 45%, Pragma 40%, Eros 5%` |
| 角色内心独白(多人格并行) | ✅ | `角色内心独白 (Async Lite - 并行) participants=['Storge','Pragma']`,17.6s |
| 人格融合引擎 | ✅ | `Personality Fusion Result fusion_strategy=以Pragma的『问题解决框架』为骨架…` |
| 话题总结 | ✅ | `START_NODE: summarize_topic` |
| 角色画像维护 | ✅ | `Task 1: Using existing portrait from DB` |
| ReAct 工具检查 | ✅ | `START_NODE: tool_check`,5.6s |
| 联网搜索工具 | ✅ | `Executing SearchTool (Huawei Cloud) with query: 武汉今天天气` |
| CO-STAR 提示词组装 | ✅ | 日志中完整 `# CO-STAR PROMPT TEMPLATE` 五段 |
| 汇聚等待(依赖未齐则跳过) | ✅ | `Generate Node: Waiting for dependencies ['style_analysis','agent_thoughts']` |
| 保存与落库 | ✅ | `START_NODE: save_memory_and_log`,`chat_history` 4 行 |
| 多段回复(response_parts) | ✅ | 前端按段渲染,替代流式 |
| 轻量模型走 FAST | 🔶 | `LIGHTWEIGHT_LLM_MODEL_NAME=qwen3-32b` 已配置,但两轮测试未被判为 FAST;路径完整,只是没触发 |
| `select_persona` / `consult` 图节点 | ✅ 早已移除 | `graph.py:115/121` 两行 `add_node` **本来就是注释状态**,不是死代码。底层能力仍在:`select_personality` 由 `analyze_communication_style` 调用,`multi_agent_service` 是融合引擎的兜底(`generation.py:351`) |

## B. 记忆系统

| Feature | 状态 | 证据 |
|---|---|---|
| 短期记忆(会话内上下文) | ✅ | `Context & Topic Summary` 注入 prompt |
| 会话摘要 | ✅ | `New session …, skipping summary`(逻辑在,新会话跳过属正常) |
| 记忆检索查询优化 | ✅ | `LLM Request [MemoryAgent]` → `优化后的搜索查询: …` |
| Qdrant 嵌入式向量库 | ✅ | `使用本地路径: ~/Library/Application Support/Daisy/qdrant_embedded` |
| **长期记忆(mem0 写入 + 检索)** | ⚠️ | **当前不可用**。`MemoryService: Required provider 'siliconflow' is not configured` —— 检索和保存**两端都失败**。见下方「重要缺口 1」 |

## C. 角色卡 / 人格

| Feature | 状态 | 证据 |
|---|---|---|
| 深度角色卡生成 | ✅ | `Successfully generated and saved Deep Character Card` |
| 生成失败兜底默认卡 | ✅ | `Applied default character card (unblocks chat now)` |
| 角色卡 JSON 容错解析 | ✅ | `Repaired malformed JSON from LLM`(**每次生成都命中**,无此功能则永远拿不到深度卡) |
| 深度生成超时保护 | ✅ | 内层 120s / 外层 150s,失败保留默认卡 |
| 六人格档案(Eros/Ludus/Storge/Pragma/Mania/Agape) | ✅ | `/api/config/profiles` 返回全部六个 |
| 人格档案增删改 | ✅ | `GET/POST /api/config/profiles`、`DELETE /{name}` |
| 人格权重配置 | ✅ | `POST /api/config/weights` |
| 核心人格禁止删除 | ✅ | 前端 `protectedProfiles` 拦截 |
| 提示词生成器 | ✅ | `POST /api/config/generate_prompt` |

## D. 主动对话

| Feature | 状态 | 证据 |
|---|---|---|
| 定时主动检查(15 分钟) | ✅ | `Job added: proactive_check_cron`;`Dispatched 'trigger_proactive_checks' in-process` |
| 主动消息生成 | ✅ | 会话中实际收到 `下午好呀,今天有安排什么有趣的事吗?` |
| 在线/活跃状态跟踪 | ✅ | `StateService.mark_user_online/active` |
| 调度器回主循环派发 | ✅ | 修复后不再报 `bound to a different event loop` |

## E. 反思与自进化

| Feature | 状态 | 证据 |
|---|---|---|
| Reflexion 评分(Q_I / E_U / D_R) | ✅ | `Reflexion: Q_I calculated q_i=0.769`;`reflexion_logs` 2 行 |
| 首轮无 E_U 时优雅降级 | ✅ | `No previous AI message found for Reflexion E_U calculation` |
| D_R 真实关系数据 + 不可靠标记 | ✅ | RL 样本 `reward_reliable=0`,如实标记而非伪造 |
| 补丁存储(Redis) | ✅ | `ReflexionPatcher: migrated 3 JSONL patch entries to Redis` |
| **补丁回灌到 prompt** | ✅ | `generation.py:169 get_active_patches(user_id)` → 拼进 `patches_text` |
| 异步反思 worker | ✅ | `Starting AsyncReflexionSystem worker...` |

## F. 强化学习数据管线

| Feature | 状态 | 证据 |
|---|---|---|
| 上下文向量构造(8 维) | ✅ | `build_context_vector` |
| 决策暂存(context + action) | ✅ | 存 Redis 待配对 |
| 奖励配对落库 | ✅ | **第二轮后** `rl_samples` 1 行:`action=Storge, reward=0.724, policy=llm` |
| 记录不改变线上决策 | ✅ | 只观测,策略仍走 LLM |
| 策略来源标记(离线评估需要) | ✅ | `policy=llm` 字段已落库 |

> 注:单轮对话后 `rl_samples=0` 是**设计如此** —— 奖励要等下一轮用户反应才算得出。第二轮后正常配对。

## G. 配置与密钥

| Feature | 状态 | 证据 |
|---|---|---|
| 首次运行配置引导 | ✅ | `configured=False` → 前端显示 `LLMSetupGuide` |
| 多服务商(华为云/硅基流动/OpenAI) | ✅ | `/api/config/providers` |
| **密钥保存前探活** | ✅ | 填错槽位当场 400「可能填错了服务」,**未落盘**;填对返回 `status: valid` |
| 只拒明确认证失败 | ✅ | 429/5xx/断网一律放行并提示「未能校验,已按有效保存」 |
| 密钥失效标记 | ✅ | 401 后 `has_invalid_key=true`,引导语改为「需要更新 API Key」 |
| 热重载 provider(免重启) | ✅ | `LLM keys updated and providers reloaded` |
| 密钥持久化到用户目录 | ✅ | `~/Library/Application Support/Daisy/server_config.json` |
| 安装包不含密钥 | ✅ | 打包时生成脱敏副本,已核验安装包内密钥字段为空 |

## H. 前端界面

| Feature | 状态 | 证据 |
|---|---|---|
| 对话界面(微信式气泡) | ✅ | 截图确认,用户消息右侧绿气泡 |
| 用户消息显示 | ✅ | 截图确认 |
| AI 角色头像自定义 | ✅ | 人格编辑器「角色头像」上传位 |
| **用户头像自定义** | ✅ | 本轮新增「我的头像」,与角色头像互不干扰(实测) |
| 更换聊天背景 | ✅ | `...` 菜单,上传 200 + 静态回读 200 |
| 新建会话 / 结束会话 | ✅ | `/api/session/start`、`/end`、`/current` |
| 下载对话记录(Markdown) | ✅ | 菜单项 `handleDownloadMarkdown` |
| 环境/动作描述折叠 | ✅ | 截图中「查看环境/动作描述」 |
| 分析面板 | ✅ | `AnalysisDashboard` 挂载于顶栏 |
| 情绪趋势图 | ✅ | `EmotionTrendChart`,2 处引用 |
| 人格趋势图 | ✅ | `PersonalityTrendChart`,2 处引用 |
| 投入度图 | ✅ | `EngagementChart`,2 处引用 |
| AI 回复评估图 | ✅ | `AiResponseEvaluationChart` |
| 沟通分析卡片 | ✅ | `/api/chat/message/{id}/analysis` 返回真实数据 |
| 状态可视化 | ✅ | `StateVisualizer` |
| 工作流编排可视化 | ✅ | `/api/workflow` 返回节点图 |
| 运行日志查看 | ✅ | `LogViewer` 页签 |
| 人格编辑器 | ✅ | 截图确认 |
| 系统设置 | ✅ | `UserLLMConfig` 页签 |
| 消息发送失败重试 | ✅ | `item.status === 'error'` 分支 |
| 智能滚动 + 新消息提示 | ✅ | `isAtBottomRef` / `showNewMessageTip` |

## I. 桌面化 / 打包

| Feature | 状态 | 证据 |
|---|---|---|
| 零外部依赖(无 Docker/Redis/独立 worker) | ✅ | fakeredis 进程内 + Qdrant 本地路径 + ARQ 并入后端 |
| 单进程后端 sidecar | ✅ | 实测后端进程数 = 1 |
| 免登录本地会话 | ✅ | `POST /api/auth/local_session`,365 天令牌 |
| 401 自愈(换令牌重放) | ✅ | 前端拦截器,每请求最多换一次 |
| 动态端口 + 单实例锁 | ✅ | 实测 Electron 1 个、后端 1 个 |
| 前端由后端托管 | ✅ | `Serving frontend SPA from …/_internal/frontend` |
| 可写数据目录隔离 | ✅ | 只读 App 包内不写任何东西 |
| **老库自动补列** | ✅ | 真实库上执行 `已为表 common_settings 补充列 user_avatar_path` |
| **后端随外壳退出** | ✅ | SIGKILL Electron → 2s 退出;SIGTERM + 活跃 SSE → 2s 退出;零残留 |
| .dmg 打包 | ✅ | 808M |
| Windows 打包脚本 | 🔶 | `build_windows.ps1` 存在,**未在 Windows 上验证过** |

## J. 可观测性

| Feature | 状态 | 证据 |
|---|---|---|
| 节点级耗时埋点 | ✅ | `CHARACTER_PERFORMANCE node=… duration_seconds=…` |
| 端到端延迟 SLO | ✅ | `SLO_E2E_LATENCY duration_ms=38048 route=DEEP` |
| 路由指标(计数/分位) | ✅ | `/api/metrics/slo` |
| 工作流轨迹落库 | ✅ | `workflow_traces` 10 行 |
| LLM 调用轨迹落库 | ✅ | `llm_traces` 11 行 |
| 反思日志落库 | ✅ | `reflexion_logs` 2 行 |
| 执行预算账本 | 🔶 | 代码在,`EXEC_BUDGET_MAX_TOKENS/CALLS` **未设置** → 无上限,不会触发 |

## K. 已按设计移除 / 禁用

| Feature | 状态 | 说明 |
|---|---|---|
| 白名单管理 | ✅ 已禁用 | 路由仍注册但嵌入模式返回 **404**(实测);前端页签在桌面模式隐藏 |
| 登录 / 注册 | ✅ 已绕过 | 端点保留供 server 部署;桌面版走 `local_session` |
| 流式响应 | ✅ 已移除 | 与真人回复习惯不符,改用 `response_parts` 多段发送 |
| Docker 编排 | ✅ 已移除 | 5 进程 → 1 进程 |

---

## 重要缺口

### 1. ~~长期记忆完全不可用~~ —— 已修复 ✅

根因不是嵌入器,而是 mem0 的 **LLM 被硬编码成 siliconflow**:

```python
# 强制使用 SiliconFlow 作为 Memory LLM (规避 ModelArts 风控)
target_provider = "siliconflow"
...
raise ValueError(...)   # 没配就直接废掉整个功能
```

「规避风控」这个理由没有证据支撑,代价却是实打实的:用户选了华为云,记忆却要另一把
密钥、另一份账单;没有就 raise,检索与写入两端全废,而用户收不到任何提示。

**修法:记忆抽取跟随用户选定的对话 provider**(读 `common_settings.llm_provider` ——
那才是对话实际使用的,`llm.py:341/433` 读的就是它;`get_current_provider()` 只是静态
默认值,用它会造成"对话走硅基流动、记忆走华为云"的分裂)。没有可用的才回落,
且回落时跳过已被标记失效的密钥。

连带修复:`MemoryService` 是 `@lru_cache` 单例,provider 在首次构造时定死 ——
热重载密钥或切换服务商时一并清缓存,否则要重启才生效。

**实测(只配华为云一把密钥)**:

```
MemoryService: 跟随对话 provider 'huaweicloud'。
[会话 5a048ad8] 用户:"我养了只叫芝麻的黑猫" → 记忆保存成功
[会话 25bd24c8] 用户:"你还记得我家宠物的名字吗?"
              → 记忆检索 retrieved_count=1「养了一只叫芝麻的黑猫,已经七年了」
              → AI:"(微笑着放下手中的书) 芝麻呀,那只小黑猫。"
```

跨会话记忆(两个不同 session_id)已跑通。

嵌入器方面无需改动:它本就走本地 HuggingFace(`BAAI/bge-large-zh-v1.5`),不依赖
硅基流动。注意该模型不在打包内,首次使用会联网下载。

### 2. ~~两个图节点是死代码~~ —— 误报,已订正

初版盘点称 `select_persona` / `consult` 是死代码。**这是错的**:那两行 `add_node`
本来就处于注释状态。提取节点清单时用 `sed 's/.*add_node(//'` 把行首 `#` 一起吃掉了,
注释行看起来像活的注册。

教训:从代码里"提取清单"必须保留注释标记,否则被注释掉的东西会以活的形态混进结论。

### 3. 执行预算账本 —— 已修复,但要如实说清它能拦什么 ✅⚠️

原状:`EXEC_BUDGET_MAX_*` 默认 None(不限),**而且记账只覆盖了极少数调用点** ——
18 个对话内 LLM 调用点里只有 1 个带 `execution_id`。在这种状态下设上限是**假保护**:
计数器永远到不了阈值。

做了两件事:

1. **补齐记账**:`StrategyAgent` / `StyleAgent` / `TopicAgent` / `ProfileAgent` /
   `MemoryAgent` / `EmotionTranslator` / `Thought_*` 全部串上 `execution_id`
   (要一路穿过 `topic_agent` 的三个内部方法、`emotion` 的翻译链、`multi_agent`)。
   覆盖率 **1/18 → 18/18**。加了 AST 静态守卫,新增 agent 漏记账会直接测试失败。
2. **打开默认上限**:`MAX_LLM_CALLS=25`、`MAX_TOKENS=40000`
   (实测 DEEP 峰值 11 次 / 约 2 万 tokens,留约 2 倍余量)。

**账本机制已验证**:记 33 次后 `Execution budget exceeded reason='llm_calls 33 >= 25'`。

**但要说清边界**:全项目只有**一个**执行点做超预算早退 —— ReAct 工具循环
(`react.py:46`)。而 `tool_check` 在图里跑得很早、与其他节点并行,那时才累积 1~2 次
调用,所以正常对话中这个检查基本不会触发。实测把上限压到 2 也没拦住,原因就在这里。

结论:**它是给病态循环兜底的保险,不是逐节点的成本闸门**。好在整个图是有界 DAG
(固定 7~11 次调用),唯一可能失控的就是工具循环,而那里既有 `DEEP_TOOL_MAX_STEPS=3`
也有预算检查。补齐记账的真实价值是:检查触发时能看到**真实总成本**,而不是原来
1/18 的残缺数字。

若要更强的成本控制,需要在 `agent_thoughts`(最贵的节点,多人格并行)前加检查点并做
降级 —— 这是独立的设计决策,本次未做。

### 4. Windows 打包未经验证 🔶

脚本骨架在,但没有 Windows 机器验证过。当前只应宣称支持 macOS(Apple Silicon)。
