# 存储归位 与 配置收敛

> 状态:**配置全部完成;存储第一步完成**(2026-08-08)。
> 第二步(C4/C5)未做,第三步(mem0 去重)按结论**暂缓**。
> services 域拆分已单独完成,见 `ARCHITECTURE.md`。
>
> 实施中额外发现并修掉 3 个真缺陷,见文末「实施记录」。

---

# 一、存储层

## 1.1 先纠正问题的提法

原先我说"合并存储层",这个说法是错的 —— 现在有 4 个存储,但它们**不是冗余,是职责不同**:

| 存储 | 内容 | 持久性 |
|---|---|---|
| SQLite(8 张表) | 对话、用户、角色卡、轨迹、RL 样本 | 真持久 |
| Qdrant | 记忆向量 | 真持久 |
| fakeredis(嵌入模式) | 见下 | **进程内,重启即空** |
| mem0 自带(sqlite + 向量) | 记忆条目与历史 | 真持久 |

盲目合并会把不同生命周期的数据强行凑到一起。真正的问题是另一个:

> **fakeredis 里混着三类生命周期完全不同的数据,其中一类本该长期存在。**

实测确认(`fakeredis.FakeServer()` 重建即空):

```
写入后:      {'14': '1'}
模拟重启后:  {} <- 空
```

## 1.2 按生命周期把现有 40 个 key 分类

### A 类 · 真缓存 —— 丢了只是变慢,可自动重建 ✅ 不动

`emotion:{hash}`、`topic:summary:session:*`、`style_analysis:*`、`cache:*`(装饰器)、
`portrait_default:*`、`reflexion:patches:*`(有 `reflexion_patches.jsonl` 真源,重启自动重建)

### B 类 · 会话期状态 —— 生命周期本就 ≤ 单次运行 ✅ 不动

`chat:stream:*`(SSE 流)、`lock:user:*`(并发锁)、`user:*:online`(TTL 5min)、
`session:active_conversation`、`rl:pending:*` 与 `reflexion:pending:*`(带 TTL,已有落库路径)、
`metrics:exec:*`(单次执行的预算账本)

### C 类 · 本应长期存在,却存在内存里 —— ❌ 真缺陷

| # | key | 现状 | 后果 |
|---|---|---|---|
| C1 | `user:{u}:activity_stats` | `hincrby`,**无 TTL** | 作息统计需累计 ≥10 样本才可信,而**每次重启归零** → `get_activity_probability` 永远返回冷启动的 0.05/0.1 → 主动关心的「按作息挑时间」形同虚设 |
| C2 | `user:{u}:proactive:daily_count` | TTL 到次日零点 | **重启即可绕过每日上限**,直接破坏"打扰不可逆"的产品约束 |
| C3 | `user:{u}:proactive:last_ts` | TTL 7 天 | 重启后冷却记录消失 → 刚重启就可能立刻打扰 |
| C4 | `metrics:llm:*` / `router:*` / `e2e:*` | 无 TTL 累计 | SLO 面板只反映本次运行,成本统计不可用 |
| C5 | `system:llm:current_provider` | 无 TTL | 需确认是否有 DB 真源;若无,重启后回落默认 provider |

C1–C3 集中在主动关心上。这是**继"已知用户名单"「用户越久不联系越收不到关心」之后,同一功能上的第二批同类缺陷** —— 根因相同:把长期事实存进了会消失的地方。

## 1.3 方案:不是合并存储,是**消除派生数据的独立存储**

关键观察:**C 类里大部分根本不需要新增存储,它们都能从已有的事实表算出来。**

| 缺陷 | 方案 | 是否需要新表 |
|---|---|---|
| C1 作息统计 | 从 `chat_history.timestamp` 按小时聚合 | **不需要** |
| C2 每日配额 | `SELECT count(*) FROM chat_history WHERE is_proactive AND date=today` —— `is_proactive` 字段上一轮刚加 | **不需要** |
| C3 冷却时间 | 同表 `MAX(timestamp) WHERE is_proactive` | **不需要** |
| C4 成本/延迟统计 | `llm_traces` 表**目前没有 token/cost 字段**,需补 3 列 | 补列 |
| C5 provider | 需先确认 `common_settings` 是否已存;未存则补 | 待确认 |

于是整体规则收敛成一句可被测试校验的话:

> **SQLite 是唯一真源;Redis 降级为纯缓存 —— 任何写入 Redis 的 key 都必须带 TTL,且丢失后能从 SQLite 重建。**

配套护栏:`test_redis_is_cache_only.py` —— 扫描所有 `redis_client.set/hset/hincrby/...` 调用,
**无 TTL 即失败**(附白名单 + 棘轮,只减不增)。这样"把长期事实塞进内存"这个错误再也犯不了。

## 1.4 分三步,风险递增

| 步骤 | 内容 | 风险 | 建议 |
|---|---|---|---|
| **第一步** | C1–C3 改为从 `chat_history` 推导;加 TTL 护栏 | 低(只读已有表) | **建议做** |
| **第二步** | C4 给 `llm_traces` 补 token/cost 列;C5 确认 provider 真源 | 中(改表 + 写入路径) | 建议做 |
| **第三步** | mem0 自带 history 库与 `chat_history` 职责去重 | **高**(动 mem0 内部) | **建议暂缓**,等有真实痛点再说 |

第三步就是我上轮说的"存储重叠",现在看清楚了:它收益最小、风险最大,不该排在前面。

---

# 二、配置收敛

## 2.1 实测:现在有 5 个来源,且其中一个是 bug

| # | 来源 | 位置 |
|---|---|---|
| 1 | 真实环境变量 | 进程环境 |
| 2 | `.env` | `load_dotenv()`,模块顶部,**绝对路径** |
| 3 | `server_config.json` | 手动注入 `os.environ`,**仅当 key 不在环境中** |
| 4 | pydantic `env_file` | `Settings.model_config` |
| 5 | Python 字段默认值 | 类定义 |

## 2.2 发现的真缺陷:`model_config` 被覆盖

`Settings` 类里有**两个** `model_config` 赋值 —— L195 与 L379。Python 类体中后者直接覆盖前者。实测:

```
env_file       = '.env'      ← 相对 cwd,不是 L195 那个绝对路径
case_sensitive = True
encoding       = None        ← L195 的 env_file_encoding='utf-8' 丢了
```

三个后果:

1. **`env_file` 变成相对 cwd** —— 打包后 cwd 不确定,pydantic 那一路读不到 `.env`;
2. **UTF-8 声明丢失** —— Windows 默认编码非 UTF-8,含中文注释的 `.env` 会解析失败。
   Windows 打包本来就是未验证项,这是一颗现成的雷;
3. 用的是 `ConfigDict` 而非 `SettingsConfigDict`,`env_file` 语义不受保证。

**今天没炸纯属巧合** —— 模块顶部的 `load_dotenv()` 已用绝对路径把 `.env` 灌进了 `os.environ`,pydantic 读不到也无妨。属于"靠巧合正确"。

## 2.3 一个需要你拍板的优先级问题

当前实际优先级是:

```
真实环境变量  >  .env  >  server_config.json  >  字段默认值
```

但 **`server_config.json` 才是用户在界面上改出来的那份**,`.env` 是开发者本地的。
也就是说:**开发机上的 `.env` 会静默压掉用户在 UI 里的设置。**

这正是之前那次事故的同一个根因 —— 换嵌入模型时只改了 Python 默认值,
而 `.env` 和 `server_config.json` 还指向旧模型,排查了很久。

**建议改为:**

```
真实环境变量  >  server_config.json(用户设置)  >  .env(开发者本地)  >  字段默认值
```

⚠️ 这是**行为变更**:你的开发机上若 `.env` 与 `server_config.json` 有冲突项,生效的那一份会变。
需要你确认后再改。

## 2.4 方案

1. **删掉第二个 `model_config`**(纯 bug 修复,无争议,可立即做);
2. 收敛为单一入口 `core/config_sources.py`,把优先级**显式写成代码里的一个有序列表**,
   而不是散落在 `load_dotenv` / 手动 `os.environ` 注入 / pydantic 三处;
3. **启动时打印每个关键配置项的实际来源**(一行日志:`EMBEDDING_MODEL=bge-small-zh-v1.5 (来自 server_config.json)`)。
   上次那类"三处配置不一致"的问题,有这行日志就是 10 秒的事;
4. 加测试 `test_config_precedence.py` 断言优先级顺序,并断言 `model_config` 只有一个。

---

# 三、建议的执行顺序

| 顺序 | 内容 | 状态 |
|---|---|---|
| 1 | 配置 §2.4(修 `model_config`、收敛入口、来源日志) | ✅ 完成 |
| 2 | 配置 §2.3 优先级调整(`server_config.json` > `.env`) | ✅ 完成(已确认) |
| 3 | 存储第一步(C1–C3 + TTL 护栏) | ✅ 完成 |
| 4 | 存储第二步(C4/C5) | ✅ 完成 |
| 5 | 存储第三步(mem0 去重) | ❌ **前提不成立,无需进行**(见 §4.4) |

---

# 四、实施记录

## 4.1 落地内容

**配置**

- 删掉重复的 `model_config`;`env_file` 恢复绝对路径,`env_file_encoding="utf-8"` 恢复;
- 优先级收敛进 `load_config_sources()` 单一函数,顺序改为
  **真实环境变量 > server_config.json > .env > 字段默认值**;
- 启动打印每项配置的**实际来源**与**实际生效值**(密钥自动打码);
- `test_config_precedence.py` 11 条,锁住优先级、单一 `model_config`、来源可观测。

**存储**

- 作息统计 / 每日配额 / 冷却时间三者全部改为从 `chat_history` 推导,
  Redis 只作带 TTL 的缓存;
- `test_proactive_survives_restart.py` 19 条,含"任何 Redis 写入必须带 TTL"的护栏。

## 4.2 实施中发现的 3 个真缺陷(方案阶段未预见)

这三个都在 C1–C3 的必经路径上,不修则改造本身不成立。

**① 用户名被写进整数外键列**

`chat_history.user_id` 是指向 `users.id` 的整数外键,而主动关心链路上的
`user_id` 自始至终是**用户名字符串**。`_send_message` 直接把后者写进了前者,
SQLite 弱类型照单全收 —— 那条消息**不属于任何用户**,既不出现在对话历史里,
也无法用于统计,连带上一轮为评估效果加的 `is_proactive` 标记一起失效。

**② 主动消息写的是本地时间,同表其余行是 UTC**

表的约定是 naive UTC(`utc_now_naive`),`_send_message` 却写 `datetime.now()`。
在 UTC+8 下它比同表其他行**超前 8 小时**,排序、"今天几条"、冷却判断会一起算错。

**③ 库里的 naive UTC 被按本地时间解释(两处)**

`value.timestamp()` 对 naive datetime 会按**本地时区**解释,而库里存的是 UTC。
在 UTC+8 下算出的 epoch 比真实早 8 小时:

- `proactive/state.py` 的忙碌保护回落路径 —— 恒定判定为"很久没活跃",
  刚聊完重启就可能立刻打扰,**正是这个保护存在的意义**;
- `workflow/nodes/emotion.py` 的响应时长 —— 恒定多出 8 小时,
  参与度评分里的 M_rtl(响应时间)因此**永远饱和、退化成常量**,
  喂给 Reflexion / RL 的信号是坏的。这一处表面完全正常,没有任何报错。

统一到 `core/time_utils.naive_utc_to_epoch()` / `local_hour_of()`,并加回归测试。

## 4.3 一个方法上的教训

`test_config_precedence.py` 第一版是在子进程里**自己再实现一遍**优先级
(先 `load_dotenv` 再 import config)。结果 `.env` 的值在 `_REAL_ENV_KEYS`
采集之前就进了环境,被判成"真实环境变量",测试报了个与生产行为无关的假失败。

**模仿实现来测实现是靠不住的。** 正确做法是把优先级逻辑抽成可注入环境的
`load_config_sources()`,让测试直接驱动**真实的那一份**。
这同时也是方案 §2.4 第 2 条"收敛为单一入口"的实际收益 —— 可测性不是副产品,
而是"单一入口"这件事本身的价值。
