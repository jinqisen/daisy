# 后端架构约定

写这份文档的直接起因:用户反馈「总是修一个问题引入另一个,是不是架构本身有问题」。
量化之后发现确实如此 —— 项目当时有 **7 个循环依赖**,`core` 本该是最底层却反过来
依赖 `services` / `tasks` / `prompts` / `models`。没有真正的分层,改动就会从意想不到的
方向回弹。

现已全部消除,并用测试固化(`tests/test_module_boundaries.py`)。

---

## 分层与依赖方向

**依赖只能向下。** 数字越小越底层。

| 层 | 包 | 职责 | 判断标准 |
|---|---|---|---|
| L0 | `core` | 基础设施 | 不含任何业务概念,换个产品也能用 |
| L1 | `agents` | 领域实体与词汇 | `CharacterCard` / `CommonSettings` / `RoleProfile` / 枚举 |
| L1 | `models` | 持久化实体 | SQLAlchemy 表定义 |
| L2 | `prompts` | 提示词渲染 | 消费领域实体,产出文本 |
| L3 | `services` | 用例 | 一个业务动作:生成角色卡、检索记忆、评估反思 |
| L3 | `multi_agent` | 多人格协商 | 同上 |
| L4 | `workflow` | 编排 | LangGraph 图与节点 |
| L4 | `tasks` | 后台任务 | 异步执行入口 |
| L5 | `api` | 接口 | HTTP 路由、请求校验 |

当前实际依赖边(由测试实时生成,全部向下):

```
L1 agents      → core
L1 models      → core
L2 prompts     → agents, core
L3 multi_agent → agents, core, models, prompts
L3 services    → agents, core, models, multi_agent, prompts
L4 tasks       → core, models, services, workflow
L4 workflow    → core, models, prompts, services
L5 api         → core, models, prompts, services, workflow
```

## services 内部:按业务域再分一层

L3 曾是平铺的 22 个文件、5000+ 行 —— 层次对了,但**层内没有结构**:
记忆、人格、对话、主动关心全堆在同一个目录,既看不出谁属于哪块业务,
也拦不住任何跨业务的随手调用。现按域拆为 6 个子包:

| 域 | 职责 | 主要模块 |
|---|---|---|
| `memory` | 对话内容的存与取 | `store` / `chat_history` / `topic_agent` |
| `persona` | Daisy「是谁、此刻什么状态」 | `character_card` / `fusion` / `strategy` / `emotion` |
| `dialogue` | 这一轮「说什么、走哪条路径」 | `generation` / `router` / `tools` |
| `proactive` | 无用户输入时主动开口 | `service` / `state` / `holidays` |
| `learning` | 从已发生的对话回捞改进信号 | `reflexion/` / `reflexion_system` / `rl_agent` / `rl_dataset` |
| `system` | 启动装配与横切关注点 | `init_data` / `schema_bootstrap` / `session` / `key_verification` / `local_lock` / `trace_store` / `metrics_store` |

域间依赖实测**无环**,方向天然分层(由 `test_service_domains.py` 持续校验):

```
memory      ← 叶子,不依赖任何域
  ↑ learning ← persona
  ↑ dialogue (← memory, persona)
  ↑ proactive (← memory)
  ↑ system   (← memory, dialogue)
```

两条约定:

1. **`__init__.py` 只写职责说明,不做重导出。** 调用方直接导入具体模块。
   `tasks/__init__.py` 曾用 `from .chat_task import chat_task` 把子模块变成函数,
   调用方拿到的东西悄悄换了类型 —— 这个坑不重复踩。
2. **services 内部统一用绝对导入**(`from app.core.config import ...`)。
   相对导入的层级会随目录深度变化,这次拆分正是被它拖慢的;
   断言导入的测试也应只校验**目标**,不锁定相对/绝对写法。

## 判断某个文件该放哪层

问一句话就够:**"这段代码知道业务吗?"**

- 不知道(重试、连接池、序列化、日志)→ `core`
- 知道领域概念但不做决策(数据类、枚举)→ `agents` / `models`
- 做一件业务事(生成、检索、评分)→ `services`
- 编排多件事 → `workflow`
- 只负责收发 HTTP → `api`

已经踩过的错位(都造成了真实故障):

| 曾经放错 | 为什么错 | 现在 |
|---|---|---|
| `api/sse.py` | 纯协议编解码、无路由,却被 tasks/services 共用 | `core/sse.py` |
| `core/fusion.py` | 人格融合引擎是业务逻辑 | `services/persona/fusion.py` |
| `core/reflexion.py` | 反思系统是业务逻辑 | `services/learning/reflexion_system.py` |
| `core/init_data.py` | 种子数据装载不是基础设施 | `services/system/init_data.py` |
| `services/llm.py` | provider 配置/重试/埋点是基础设施 | `core/llm.py` |
| `core/{router,tools,holidays}.py` | 路由决策、搜索工具、节日都是业务 | `services/dialogue/`、`services/proactive/` |
| `core/{rubrics,strategies}.py` | 纯枚举,是领域词汇表 | `agents/` |

## 反转依赖的两个手法

底层需要上层能力时,**不要 import 上层**,用这两种方式之一:

**注册表**(`core/job_registry.py`)
分发器住在 core 却要找到 tasks 里的任务函数。改为 core 只持一张表,
tasks 在导入时自行登记。

**可插拔接口**(`core/trace_sink.py`、`core/metrics_sink.py`)
LLM 客户端要写调用轨迹与指标,但"存到哪张表"是持久化关注点。
core 只声明 sink,services 启动时注入实现。

这层间接不是为了"可扩展",而是为了**依赖方向**:core 直接 import 模型会让最底层
反过来依赖持久化层,循环随之而来。同时它顺带给出一条好性质 ——
未注入实现时静默丢弃,所以脚本和测试里不装 sink 也能正常跑。

## 护栏

`tests/test_module_boundaries.py` 用 AST 解析真实依赖边,强制:

1. **不得新增循环** —— `KNOWN_CYCLES` 是棘轮,只减不增;消除一个就删一行
2. **低层不得引用高层**

两个细节值得知道:

- `if TYPE_CHECKING:` 内的导入**不计入** —— 运行期不存在,不可能造成循环,
  是类型解耦的正当手法。
- **函数内的延迟导入仍然计入** —— 那只是把循环藏起来,不是消除。
  (重构时我自己先走了这条捷径,被护栏逼回了真正的解耦。)

## 能力分级契约

`app/workflow/capability.py`。起因是一次真实事故:用户没配**可选**的搜索密钥,
`tool_check` 抛异常打死整个 chat_task,消息永久卡在 pending,之后每次发送都重放它 ——
一个锦上添花的功能让用户完全说不了话。

根因不是某处 `try/except` 写漏,而是**没有契约**:没人规定过哪些节点是对话的必要
条件。缺了契约,错误处理靠每个作者当时的判断,迟早会漏。

```python
@essential                                   # 失败向上传播
async def generate_response(state): ...

@enhancement(fallback={"tool_results": {}})  # 失败自动降级,绝不中断对话
async def tool_check(state): ...
```

`fallback` 必须显式给出:下游汇聚可能在等那个键,悄悄不写会让它一直等 ——
那是另一种形式的中断。测试强制每个进图的节点都声明等级。

## 两套认证,不要混

| | `api/auth.py` register/login | 本地隐私锁 |
|---|---|---|
| 回答 | 谁有资格用这个服务 | 能开这台电脑的人是否都能翻我的对话 |
| 场景 | server 部署、多用户、白名单 | 桌面单机 |
| 守卫 | `require_server_mode` | `require_embedded_mode` |

混淆的代价已经付过一次:嵌入模式下 register/login 返回 404,而前端把 `local_session`
的**任何**失败都当成"这是 server 部署",落到那个被禁用的登录页 —— 死路。
后端冷启动要 30~45 秒(加载 torch/transformers),用户打开得快一点就必然命中。

现在状态机严格区分:

```
404       → 确实是 server 部署 → 登录界面
401       → 已设隐私锁         → 解锁界面(可重试)
连接失败/5xx → 后端仍在启动     → "正在启动",持续重试,超时才报错
```

**硬约束:隐私锁是可选的,未设置时绝不拦人。** 可选的安全措施一旦成为无法绕过的
障碍,就是事故。锁文件损坏时也按"未设锁"处理 —— 数据仍在本机,把用户挡在外面
只会逼他删掉整个数据目录。


## 一条贯穿本轮的判断标准

重构过程中反复用到同一个问题,值得单独写下来:

> **这个东西丢了会怎样?**

按答案分类,归属就清楚了:

| 丢了会怎样 | 归属 | 例子 |
|---|---|---|
| 只是变慢,能自动重建 | 缓存(必须带 TTL) | 情绪分类结果、话题摘要、Provider 配置 |
| 无所谓,本来就该随进程消失 | 进程内状态 | SSE 通道、并发锁、在线标记、单次执行的预算账本 |
| **功能会静默失效** | **SQLite** | 每日配额、冷却时间、作息统计、累计指标 |

最后一类是所有麻烦的来源 —— 它们曾经全都待在"看起来像数据库"的内存缓存里。
判断错的代价不是报错,而是**功能悄悄不工作而没人发现**:

- 主动关心的作息统计需累计 ≥10 样本才可信,而重启归零 → 从未生效过;
- 每日配额重启即清零 → 上限可被绕过;
- SLO 面板只反映本次运行 → 成本统计没有意义。

同一个判断也适用于**别的东西**,不只是存储:

- 两条情绪链路读的键从来没有写入方 → 生成侧持续注入「Neutral (强度: 0)」;
- 记忆检索查询没做 JSON 清洗 → 5% 的检索用一串 markdown 去做向量匹配。

它们的共同点是:**失败时不报错**。所以这类问题的护栏只能靠测试主动去问
"它真的在工作吗",而不能等报警。本轮新增的护栏基本都属于这一类。
