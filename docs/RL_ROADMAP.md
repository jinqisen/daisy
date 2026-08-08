# 人格策略学习:评估与路线

## 结论摘要

**做 contextual bandit,不做深度 RL。** 已落地 Phase 0-1(修奖励信号 + 数据管线),
Phase 2 的离线评估结果决定是否继续。

---

## 一、为什么现有 RL 不工作

不是"没训练好",而是**训练管线被删除了**:

```python
# self.optimizer = optim.Adam(...)  # 推理模式不需要
# 移除了 store_transition 和 update (推理专用代理)
```

现状 = 随机初始化网络 + `dist.sample()` 采样。实测表现:

| 输入 | RL 权重输出 |
|---|---|
| "今天真开心" | `Pragma=0.65 Ludus=0.08 Agape=0.07` |
| "我很难过" | `Pragma=0.65 Ludus=0.08 Agape=0.07` |

权重恒定(网络未训练),而 `selected_personality` 却在变 —— 因为它来自 `dist.sample()`
的随机采样。**等于一层伪装的随机数**,比不用更糟(不可解释、不可复现)。

## 二、价值判断

### 有真实价值
个性化人格选择是 bandit 的天然场景:同样一句"今天好累",A 用户想要无条件安慰
(Agape),B 用户想要解决方案(Pragma)。LLM 策略靠通用心理学 prompt 判断,
**给不出因人而异的答案** —— 而这正是陪伴产品的核心差异点。

### 为什么不做深度 RL

| 理由 | 说明 |
|---|---|
| 动作空间只有 6 个 | 用 28→64→64→6 网络学 6 选 1,杀鸡用牛刀 |
| 数据量差 2-3 个数量级 | 策略梯度通常需数万样本,现有 221 条 AI 回复 |
| 非序列决策 | 人格选择是单步决策 + 事后反馈,是 bandit 问题不是 RL 问题 |
| 不可解释 | 陪伴产品出问题时"为什么这轮冷淡"必须能回答 |

### 根本约束(产品层面)
**单用户桌面应用没有跨用户数据汇聚**,冷启动慢。若未来考虑用户授权的云端可选同步,
bandit 效果会显著更好。这是产品决策,不是技术决策。

---

## 三、路线与进度

### ✅ Phase 0:修奖励信号(已完成)

D_R(关系深度)此前是硬编码常量:

| 指标 | 桩数据 | 真实值(user_id=1) |
|---|---|---|
| session_count_7d | 20 | **1** |
| retention_rate_7d | 0.95 | **0.14** |
| memory_updates_count | 50 | **3** |

D_R 因此恒约 0.98,在 S 中占 20% 权重 = **每轮固定加 ~0.196 偏置**。后果:
- S 分布被压缩(实测挤在 0.75±0.05)
- 补丁阈值 0.40 永不可达(这正是"Reflexion 补丁从未生成"的根因之一)
- 任何基于 S 的学习都会拟合到假信号

**已改为**:从 DB 真实统计;样本不足(`< MIN_INTERACTIONS_FOR_DR`)时标记
`is_real=False`,S 剔除 D_R 并把 Q_I/E_U 归一化(0.625:0.375),
**而不是塞估算值充数**。

测试:`tests/test_reward_signal.py`(8 项)

### ✅ Phase 1:数据管线(已完成)

**关键约束:只记录,不改变线上行为。** 线上仍走 LLM 策略,零风险积累数据。

```
strategy 节点  ──record_decision()──►  Redis 暂存 (context, action)
                                              │
下一轮 Reflexion 算出 S ──record_reward()──►  配对落库 rl_samples
```

- **context**:8 维(Ekman 6 + 投入度 + 关系阶段)。刻意不用原始 28 维 —— 
  维度须远小于样本数,否则小数据必然过拟合
- **policy 字段**:记录数据由哪个策略产生,离线评估做重要性加权时必需
- **reward_reliable**:D_R 是否可信,供筛选同质样本
- 记录失败一律吞掉,绝不影响对话

产出:`app/services/rl_dataset.py`、`app/models/rl.py`、
`scripts/export_rl_dataset.py`,测试 `tests/test_rl_dataset.py`(9 项)

### ⏸ Phase 2:离线策略评估(数据积累后进行)

```bash
python3 scripts/export_rl_dataset.py            # 查看积累进度
python3 scripts/export_rl_dataset.py --out d.jsonl
```

- 用 IPS / Doubly Robust 估计 bandit 策略的期望回报
- 与当前 LLM 策略对比
- **这是设计好的止损点**:若离线评估打不过 LLM 策略,就停手,不上线

建议样本量:**200+**(6 个臂,每臂需数十样本才能区分优劣)

### ⏸ Phase 3:小流量在线(仅当 Phase 2 通过)

- LinUCB 或 Thompson Sampling(核心不到 50 行,无需 torch)
- ε 从 0.1 起
- **保底规则**:高风险情绪(悲伤/焦虑高分)强制 Agape/Storge,不交给探索
- 一键回退 LLM 策略

### ⏸ Phase 4(可选):混合策略

LLM 策略给先验,bandit 在其上做个性化微调,兼顾冷启动质量与长期个性化。

---

## 四、风险提示

1. **单用户数据稀疏是根本约束** —— 见上文产品层面说明
2. **Phase 2 可能得出"不值得上线"** —— 这是止损设计,不是失败
3. **人格选择对满意度的贡献可能低于预期** —— 回复内容质量影响大得多,
   可能淹没人格选择的信号。Phase 2 的离线评估会暴露这一点

## 五、现有 RL 代码的处置

`app/services/rl_agent.py` 的 `PolicyNetwork` 暂时保留但**不建议启用**
(`PERSONALITY_SELECTION_MODE=rl` 会得到随机结果)。
Phase 2 结论出来后:
- 若走 bandit → 删除该文件,bandit 不需要神经网络
- 若确认要深度 RL → 恢复 optimizer/store_transition/update 并补训练管线

差距已记录在 `tests/test_spec_gaps.py` 的 xfail 中,持续可见。
