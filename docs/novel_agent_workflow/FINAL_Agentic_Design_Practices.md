# Daisy 项目 Agentic 设计实践沉淀(v3,基于原书全文重建)

## 0. 版本说明与方法

本版基于 Antonio Gulli《Agentic Design Patterns — A Hands-On Guide to Building Intelligent Systems》**全文**(482 页 PDF)重建:提取了全部 21 章的「At a Glance」(What / Why / Rule of thumb)与「Key Takeaways」小节——这是全书的规范性判断层——并逐章对照 `Daisy_server` / `Daisy_skills` 的实际代码验证。

与 v2 的关键差别:v2 的模式映射建立在「章节目录 + 通用模式认知」上,本版每条结论都能回答两个问题:**书中该章给出的适用判据是什么**(以各章 Rule of thumb 为准),以及**Daisy 代码里对应的事实是什么**(以文件:行号为证)。v2 中被本次全文阅读**推翻或修正的结论**集中列在第 4 节,不做掩饰。

---

## 1. 21 个模式对齐总览(修正版)

结论分三档:**采纳**(书中判据满足、代码已落地)、**强化**(判据满足但实现不完整)、**暂缓**(书中判据不满足或成本分支不成立,当前不应引入;「暂缓」不代表相关领域没有别的实现,见各行说明)。

| # | 章 | 书中适用判据(Rule of thumb 要旨) | Daisy 事实 | 结论 |
|---|-----|--------------------------------|-----------|------|
| 1 | Prompt Chaining | 任务复杂到单条 prompt 会认知过载、漏指令时,拆链 | DEEP 路径节点链;但最终生成 prompt 仍在单点聚合大量上下文(见 §4.1) | 采纳,留一个反向风险 |
| 2 | Routing | 需按输入性质在多条流程间分派时 | `route_logic()` 规则匹配 + LLM Judge 双层([router.py](../../Daisy_server/app/core/router.py)),DEEP 为默认 | 采纳 |
| 3 | Parallelization | 存在互不依赖的子任务、外部 I/O 等待是瓶颈时;**书中明确警告:并发架构在设计/调试/日志上代价显著** | `analyze` 后五路并行汇入 `generate`;但状态合并契约脆弱(§5 深改点 #1) | 采纳,书中警告已应验 |
| 4 | Reflection | 交付前需要「执行→评审→修正」迭代提质,**且能接受延迟/成本** | **Daisy 未实现此模式**(无任何在线 critic/refine),且对高频陪伴对话,判据的成本分支不成立——跳过是合理取舍。既有 Reflexion 是异步事后学习,属 ch8 程序性记忆 + ch9 学习范畴,不是本章 | **暂缓**(v2 误标「采纳」,v3 初稿误标「变体」) |
| 5 | Tool Use | 需要突破模型内部知识、与外部交互时 | 有界 ReAct([react.py](../../Daisy_server/app/workflow/nodes/react.py)),白名单 + 步数上限 | 采纳 |
| 6 | Planning | 任务需要动态分解为相互依赖的步骤序列时 | 主链固定图,不做开放规划——判据不满足(高频对话路径已知) | 暂缓(合理) |
| 7 | Multi-Agent | 任务可分解为需专业分工的子问题时;书列四种形态:顺序交接/并行/辩论/层级 | `consult_personalities_async` 属「并行工作流 + 汇聚」形态,局部使用 | 采纳(局部) |
| 8 | Memory | 需跨轮上下文、多步任务追踪、个性化时;书的分层taxonomy:**语义事实 / 情景经验 / 可更新的程序性规则** | 三层俱全:mem0+Qdrant(语义)、exemplars(情景)、patches(程序性)——与书中 LangGraph store 的三分法一一对应 | 采纳,命名对齐书中 taxonomy |
| 9 | Learning & Adaptation | 环境动态、需个性化与持续改进时;书强调需要「数据流管理 + overseer」 | RL 策略网络(推理态)+ Reflexion 异步归纳(overseer 角色由 reflexion worker 承担) | 强化 |
| 10 | MCP | 工具生态多样、需动态发现、跨模型互操作时;书明确:**固定少量工具时直接 function calling 即可** | Daisy_skills 以 MCP 形态暴露;当前工具集固定且少 | 强化(书中判据提示不必过度投入) |
| 11 | Goal Setting & Monitoring | 需自主多步执行 + 按目标持续自评纠偏时 | 主动关怀是定时轮询([proactive_task.py](../../Daisy_server/app/tasks/proactive_task.py)),**无进度评估、无纠偏反馈环**——只满足了「执行」没满足「监控」 | 强化 |
| 12 | Exception Handling | 接外部系统、可靠性是硬要求时;书的分层:检测→处理(重试/fallback/降级)→恢复(回稳/自纠/升级) | Skills 有 ErrorResult 契约;工作流节点有 skip/fallback;缺统一的恢复语义分层 | 采纳,待标准化 |
| 13 | HITL | 高风险决策需人类判断时;书:**升级策略(escalation policy)是核心构件** | 仅 Admin/白名单;无任何面向用户风险的升级路径 | 暂缓(但见 §5 危机分支 backlog) |
| 14 | RAG | 需外部事实、可溯源回答时;书区分基础 RAG 与 **Agentic RAG(对检索结果主动推理/验证/精炼)** | query rewrite + 检索([memory.py](../../Daisy_server/app/workflow/nodes/memory.py)),属基础 RAG;「检索≠必然注入」原则已有 | 采纳 |
| 15 | A2A | 跨框架、跨进程的多 Agent 协作时 | 人格协同是进程内调用,判据不满足 | 暂缓(合理) |
| 16 | Resource-Aware | 有预算/延迟硬约束、需按复杂度分配模型时;书的标准实现:**Router 分档 + Critique Agent 反馈改进路由** | 三档路由 + 全局成本计数([llm.py:98](../../Daisy_server/app/services/llm.py))——**有观测无控制,且缺 Critique→路由改进的反馈环** | 强化 |
| 17 | Reasoning | 问题需分解、多步逻辑、工具交互时;书提出「推理时间分配」(Scaling Inference Law) | 有界 ReAct 仅 DEEP 启用;轻量模型跑路由/判别,重模型只做终稿——即「按复杂度分配思考时间」 | 采纳 |
| 18 | Guardrails | 输出能影响用户/声誉的任何场景;书的分层:**输入校验 / 输出过滤 / 行为约束 prompt / 工具限制 / 外部审核 / HITL**,强调组合使用 | 行为约束 prompt **全路径都有**(core system instructions + 角色卡 addendum;DEEP 另有动态敏感话题护栏 [generation.py:271](../../Daisy_server/app/workflow/nodes/generation.py),STANDARD 另有线下见面意图的规则触发硬约束 [fast_path.py:153](../../Daisy_server/app/workflow/nodes/fast_path.py));工具白名单、准入白名单已有。**缺:系统级输入校验层、输出过滤层**;且动态护栏/patches/后验校正仅 DEEP 接入,护栏链路跨路由不统一 | 强化(缺口=缺两层+链路不统一,非「非 DEEP 裸奔」) |
| 19 | Evaluation | 生产环境、需版本对比、行为可能漂移时;书的核心手段:**轨迹评估(实际步骤 vs 理想路径)、LLM-as-Judge、A/B、漂移检测** | SLO 指标 + 语义相似度已有;**workflow_trace 已持久化到 DB**([chat_history.py:171](../../Daisy_server/app/services/chat_history.py))但从未被用于轨迹评估——数据在、评估缺 | 强化(存在低成本切入点) |
| 20 | Prioritization | 多目标冲突、资源受限、需动态排序时 | 主动检查对全用户无差别入队,无排序判据 | 暂缓(量级不足) |
| 21 | Exploration | 开放解空间、找「未知的未知」时 | 判据不满足 | 暂缓(合理) |

---

## 2. 从书中判断标准得出的核心匹配结论

只列全文阅读后**站得住**的结论,每条给出书中依据与代码事实。

### 2.1 路由:书中判据完全满足,且实现比书的示例更完整一层

书中 ch2 允许三种路由实现(LLM 判别 / 规则 / 向量相似度)。Daisy 的 [`IntelligentRouter`](../../Daisy_server/app/core/router.py) 是「规则匹配优先、LLM Judge 兜底」的两层结构,并带路由结果缓存——这符合书中 ch16 对成本敏感路由的补充要求。保持不动。

需要补的是 ch16 的另一半:书的标准形态里有一个 **Critique Agent 事后评价回复质量、反馈改进路由判据**。Daisy 的 route 决策目前无任何事后评价回灌(reflexion 模块中仅有 metadata 标注)。这是 §5 深改点 #4 的一部分。

### 2.2 并行:书自己就警告了 Daisy 正在发生的事

ch3 的 Key Takeaways 明确指出并发架构会在**设计、调试、日志**三个环节引入显著复杂度与成本。Daisy 的对应事实:`AgentState` 仅 `workflow_trace` 一个字段有 reducer,而 `analyze_style` 与 `agent_thoughts` 两个并行分支都写 `_skip_generation`([generation.py:448](../../Daisy_server/app/workflow/nodes/generation.py) / :507),该键又被 [graph.py](../../Daisy_server/app/workflow/graph.py) 用作条件分支。书中的警告在本项目已有具体样本。→ 深改点 #1。

### 2.3 记忆:Daisy 的三层与书的 taxonomy 一一对应,应直接采用书中命名

ch8 给出的长期记忆三分法:**semantic(事实)/ episodic(情景)/ procedural(可更新的程序性规则)**。Daisy 现状:

- semantic → mem0 + Qdrant 用户事实/偏好
- episodic → Reflexion exemplars([storage.py](../../Daisy_server/app/services/reflexion/storage.py))
- procedural → Reflexion patches(Global/Personal)

v2 用的是自造词「短期状态/长期记忆/过程性规则」;建议文档与代码注释统一改用书中 taxonomy,便于团队与外部资料对齐。分库存储、分策略检索、分优先级注入的原则不变。

### 2.4 Reflection 的诚实定性:Daisy 实现的不是 ch4

ch4 的 Reflection 定义是**交付前**的「执行→评审(Producer-Critic)→修正」迭代环,书同时警告其延迟/成本代价。Daisy 的生成路径**没有任何在线 critic**(已 grep 验证,generation.py 中的 "CRITICAL" 命中全是 prompt 文本);Reflexion 系统是**事后异步**的滞后结算 + 补丁归纳,按书的分类属于 ch8 procedural memory + ch9 Learning 的组合。

这不是缺陷——对高频陪伴对话,跳过在线反思是符合书中成本警告的合理取舍。据此本模式在总览表中定为**暂缓**(判据的成本分支不成立,未实现即是正确状态),而非「变体」:「变体」意味着实现了该模式的某种变形,与「未实现」矛盾。但定性必须准确,因为它决定了未来的演进方向:如果要提升单轮质量,书给的路径是「对高风险输出加**单步、有界**的 critic」(而不是无限反思环);Daisy 已有的异步链路解决的是**跨轮**质量,二者互补而非重复。

### 2.5 护栏:书的六层清单让缺口变得可枚举

ch18 列出的层:输入校验 → 输出过滤 → 行为约束 prompt → 工具限制 → 外部审核 → HITL 升级。对照 Daisy:

| 书中层 | Daisy 现状 |
|--------|-----------|
| 输入校验 | 无系统级安全校验(correction.py 是纠错);但 STANDARD 有一处雏形:`is_offline_meetup_intent()` 规则检测输入并触发硬约束注入([fast_path.py:153](../../Daisy_server/app/workflow/nodes/fast_path.py)) |
| 输出过滤 | 无 |
| 行为约束 prompt | **全路径都有**:core system instructions + 用户模板 + 角色卡 addendum(FAST/STANDARD 见 [fast_path.py:71-84](../../Daisy_server/app/workflow/nodes/fast_path.py)/150-163);DEEP 另有动态敏感话题护栏(generation.py:271) |
| 工具限制 | 有(DEEP_ALLOWED_TOOLS) |
| 外部审核 | 近似做法:Memory LLM 切换到内容安全宽松的提供商,是「规避风控」不是「审核输出」 |
| HITL 升级 | 无 |

结论:Daisy 在六层中**完整缺失的是输入校验与输出过滤两层**;行为约束层全路径覆盖,但**动态护栏、patches 注入、后验校正只有 DEEP 接入**——问题的准确定性是「护栏链路跨路由不统一」,而不是「非 DEEP 路径没有护栏」。ch18 强调「组合才稳」与 ch13 的「升级策略是核心构件」共同指向 §5 的护栏契约 + 危机分支。

### 2.6 评估:书的「轨迹评估」在 Daisy 有现成数据,是最便宜的深改点

ch19 的核心手段之一是 trajectory evaluation——把 Agent 实际执行的步骤序列与理想路径对比。Daisy 的 `workflow_trace` **已经按 execution_id 持久化到 DB**(chat_history.py:171 `persist_workflow_trace`),只是从未被消费用于评估。这意味着:不需要新增埋点,直接在既有数据上就能做「路由决策正确率」「节点耗时分布」「补丁注入命中率」的离线分析。v2 完全漏掉了这一点。

---

## 3. 对资料的吸收结论(修订)

保留 v2 中经全文验证仍成立的原则,措辞按书校准:

- **上下文工程优先于单条 Prompt**(ch1 的反面警告:单点聚合过多指令导致漏项——注意 Daisy 的最终生成 prompt 正在承受这个风险,见 §4.1)。
- **复杂任务拆为可观察阶段**(ch1/2/3),但**并行的工程代价要预算进去**(ch3 明确警告)。
- **工具调用结构化且有界**(ch5/17):契约、白名单、步数/超时上限。
- **记忆三层化**(ch8):semantic / episodic / procedural,分库分策略分优先级。
- **学习闭环异步化**(ch9 + ch4 成本警告的推论):在线路径不做无界反思。
- **规划与多 Agent 按判据引入**(ch6/7/15):判据不满足就不引入,Daisy 当前判断正确。
- **可靠性与安全是组合工程**(ch12/18/19):错误恢复分层、护栏多层组合、评估持续在线;书的收尾观点——把 Agent 当作复杂软件,沿用成熟的容错/状态管理/测试工程实践。

---

## 4. 被全文阅读修正的 v2 结论(勘误清单)

诚实记录,防止旧结论继续流传:

1. **「Reflection:采纳」→「暂缓」**(v3 初稿曾误标「变体」,经复核修正:「变体」意味着实现了该模式的变形,与「未实现」自相矛盾)。Daisy 无 ch4 意义上的在线反思,且成本判据不成立、不实现是正确状态;既有 Reflexion 属 ch8/ch9 组合。(§2.4)
2. **「路由=成本控制优先」→「质量默认 DEEP,成本是次要维度」**(v2 已改,v3 维持),并新增:ch16 要求的 Critique→路由改进反馈环缺失。
3. **「资源感知:几乎没有」→「有观测、无控制」**。全局 token/cost 计数已在 [llm.py:98](../../Daisy_server/app/services/llm.py) 落 Redis;缺的是 execution_id 级账本与超预算降级。(此项由代码复核纠正,与 ch16 的「基于实时约束做决策」定义对齐)
4. **「评估:没有 wiring」→「监控与轨迹数据已在,缺评估消费与回归门禁」**。workflow_trace 已持久化,轨迹评估是低成本切入点。(§2.6)
5. **新增遗漏项:跨路由上下文构造分叉**。STANDARD 在 [fast_path.py:120](../../Daisy_server/app/workflow/nodes/fast_path.py) 独立拼装上下文;DEEP 走 DAG 产物 + patches + COSTAR。**精确定性**(此处 v3 初稿曾写成「STANDARD 不过任何护栏层」,失真已纠):FAST/STANDARD 保有基础行为约束(core system instructions + 角色卡 addendum,STANDARD 另有线下见面硬约束),缺的是 DEEP 专属的动态护栏、patches 注入与后验校正链路。同一用户在不同 route 下的语义基座与动态安全层不一致。当前爆炸半径有限(路由默认 DEEP,STANDARD 只接平凡输入),但属潜伏型风险:一旦为降本放宽 STANDARD 准入即刻放大。
6. **MCP 投入的书中提醒**:ch10 明确「工具固定且少时,直接 function calling 足够」。Daisy_skills 的 MCP 化方向不错,但当前不必为 MCP 生态特性(动态发现、跨模型互操作)追加投入。

---

## 5. 深度改造点(复核版,含排序共识)

以下排序经过代码逐项复核(含对 v2 高估/低估的修正),每项标注书中依据。

| 优先级 | 改造点 | 书中依据 | 要点 |
|--------|--------|---------|------|
| **P0 前置** | #6-min 最小黄金对话集 + 语义 diff | ch19(版本对比判据) | 重构 generation.py 前必须有回归安全网;用现有 MetricsService 语义相似度即可起步 |
| **P0 批次** | #5→#1:汇聚层拆分,再落状态 reducer | ch1(单点过载警告)、ch3(并发复杂度警告) | 先把 [generation.py](../../Daisy_server/app/workflow/nodes/generation.py)(819 行,控制/策略/存取耦合)按「上下文装配/护栏/生成/后处理」拆开;reducer 契约落到拆好的结构上。**一个批次、批次内先 #5 后 #1**,不拆分排序 |
| **P1** | #4 工作流级预算控制器 | ch16(Router+Critique 标准形态;Graceful Degradation 列为标准手段) | 补 execution_id 级账本(观测已在,只缺归集)+ 超预算降级出口 + Critique 反馈改进路由 |
| **P1** | #3 Reflexion 存储迁移 | ch8(procedural memory 应可检索、可更新) | [patching.py:14](../../Daisy_server/app/services/reflexion/patching.py) JSONL 全量读 → Redis/DB 带索引与缓存;并发 worker 一上即紧急 |
| **P1/P2** | 跨 route 上下文构造统一 | ch18(护栏组合须全路径一致)+ ch8 | 抽出共享的上下文装配层;将 DEEP 专属的动态护栏/patches 链路收编为全路由共用(STANDARD 的 `is_offline_meetup_intent` 规则检查可作为统一输入校验层的种子) |
| **P2** | #6-full 回归门禁 + 轨迹评估 | ch19(trajectory、LLM-as-Judge、drift) | 把 #6-min 升级为 CI gate;消费已持久化的 workflow_trace 做路由正确率/节点耗时/补丁命中率分析 |
| **Backlog** | #2 危机干预分支 | ch13(escalation policy)、ch18(HITL 层) | 产品决策暂缓,但登记为有 owner 的安全项;落地时挂在「跨 route 护栏统一」工作上,成本最低 |

不建议推进(判据不满足,v2 结论维持):全量多 Agent 化、开放式 Planner 进主链、A2A、无边界反思环、无上限工具调用。

---

## 6. Daisy Agentic 架构准则(v3 微调)

1. **主路径固定图化**(ch6 判据反向应用):高频已知流程用显式 DAG。
2. **复杂度路由前置,DEEP 为质量默认**(ch2/16):路由决策可观测、可缓存,且需补评价反馈环。
3. **能力边界契约化**(ch5/10/12):schema、错误码、trace_id、步数/超时上限都是正式契约。
4. **上下文装配共享化、注入分层化**(ch1/8):三条路由共用一个装配层;semantic/episodic/procedural 分层注入。
5. **学习闭环异步化、在线反思有界化**(ch4/9):跨轮质量走异步 Reflexion;单轮质量若要提升,只加单步有界 critic。
6. **护栏组合化、全路径覆盖**(ch18/13):输入校验+输出过滤+行为约束+工具限制多层组合,任何 route 不豁免;高风险配升级策略。
7. **评估内建化、轨迹可消费**(ch19):持久化的 trace 必须有消费方;改动过回归门禁。
8. **多 Agent 局部化**(ch7):仅以「并行产出、汇聚裁决」形态局部使用。

---

## 7. 一句话结论

对照全书 21 章的适用判据,Daisy 的既有路线(路由分层 + 并行 DAG + 有界工具 + 三层记忆 + 异步学习)在书中都能找到正面依据,方向不需要改;真正的差距集中在三处:**并行状态契约没有兑现 ch3 的工程代价预算、护栏在 ch18 六层中完整缺失输入校验与输出过滤两层且动态护栏链路只覆盖 DEEP、评估数据(轨迹)已持久化却无人消费**。深改的顺序应当是:先建回归安全网,再拆汇聚层落状态契约,然后补预算控制与护栏全覆盖——每一步都有书中对应章节作为验收标准。
