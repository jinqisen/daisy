# 打包版后端 `readonly database` 根因定位与逐项修正计划

## Summary

目标：定位打包版后端 `Error processing memory action ... attempt to write a readonly database` 的真实根因，收缩当前可疑改动面，按“先证伪、后修复、再重打验证”的顺序逐项修改。

成功标准：
- 打包版后端不再出现 `attempt to write a readonly database`
- `Fusion Engine failed: No module named 'app.services.config'` 不再出现
- 长期记忆写入与跨会话检索都可稳定复现
- 最终保留的改动是最小集合，没有额外战术补丁残留

## Current State Analysis

### 已确认的现状

1. `fusion.py` 当前已从 [`Daisy_server/app/services/fusion.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/app/services/fusion.py) 读取 `..core.config`，这与历史日志中的 `No module named 'app.services.config'` 直接对应，属于高置信修复。
2. [`packaging/build_macos.sh`](file:///Users/anykong/Daisy_Demo/packaging/build_macos.sh) 当前加入了 `resolve_python()`，这是为了让本机存在 `PyInstaller` 的解释器真正被打包脚本使用，属于构建链路修复。
3. [`Daisy_server/app/services/memory.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/app/services/memory.py) 当前存在两类 mem0 相关改动：
   - `_init_mem0_home()`：通过 `MEM0_DIR` + `reload(mem0.memory.setup)` 强制迁移 `mem0_dir`
   - `Memory.from_config(...)` 之后替换 `self.memory.db` 的兜底逻辑
4. 最新日志仍显示 `Error processing memory action: {'id': '0', 'text': '备用相机叫北斗', 'event': 'ADD'}, Error: attempt to write a readonly database`，说明 `memory.py` 的当前改动**尚未形成闭环**。
5. 当前测试集中，mem0 路径回归测试位于 [`Daisy_server/tests/test_bundled_models_and_search_key.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/tests/test_bundled_models_and_search_key.py)，桌面端数据目录回归测试位于 [`Daisy_server/tests/test_sidecar_lifecycle.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/tests/test_sidecar_lifecycle.py)。

### 当前高风险点

1. [`memory.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/app/services/memory.py#L352-L370) 中“构造完成后替换 `self.memory.db`”的兜底逻辑偏战术补丁，尚未被日志或最小复现明确证明是正确方向。
2. `reload(mem0.memory.setup)` 是否足够影响打包环境中的 `mem0_dir` 常量，需要通过最小复现验证，而不是继续叠加补丁。
3. 最近几轮端到端验证混入了端口占用、Electron 单实例锁、隔离目录缺配置等噪音，需要改成稳定的“单独跑打包后端可执行文件”的验证方式。

## Proposed Changes

### 变更 1：先收缩 `memory.py` 到“证据更硬”的最小版本

文件：
- [`Daisy_server/app/services/memory.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/app/services/memory.py)

修改内容：
- 保留 `_init_mem0_home()` 和 `history_db_path` 显式传参
- 移除 `Memory.from_config(...)` 之后替换 `self.memory.db` 的兜底逻辑

为什么：
- 当前 `db` 替换块属于“猜测性修复”，它没有直接证据证明命中了真实根因
- 在未清理这段代码前，后续任何验证都无法分辨：问题是 `_init_mem0_home()` 没生效，还是 `db` 替换逻辑干扰了现象

怎么改：
- 删除 `try: from mem0.memory.storage import SQLiteManager ... self.memory.db = _ReSqliteManager(target)` 整段
- 保留 `self.memory = Memory.from_config(config)` 及其后的初始化日志

### 变更 2：为 mem0 根因建立更精准的只读回归测试

文件：
- [`Daisy_server/tests/test_bundled_models_and_search_key.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/tests/test_bundled_models_and_search_key.py)

修改内容：
- 保留已有的 `MEM0_DIR` / `history_db_path` 测试
- 新增“最小构造 + 最小写入”级别的测试，明确区分：
  - `mem0_dir` 是否迁到应用数据目录
  - `history.db` 是否可创建
  - `history` 表是否真的能写入一条记录

为什么：
- 当前测试多为源码结构断言，能证明“我们写了某段代码”，但不能证明“mem0 在真实运行时确实写进了正确的 sqlite”
- 需要一个不依赖完整聊天工作流的最小回归测试，减少噪音

怎么改：
- 用 `tmp_path + monkeypatch.setenv("DAISY_DATA_DIR", ...)`
- 在测试里导入 `app.services.memory` 触发初始化
- 直接调用 `_history_db_path()` 并用 sqlite 做建表/写探针
- 视情况引入一个仅验证 `mem0.memory.setup.mem0_dir` 与 `_history_db_path()` 同根目录的测试

### 变更 3：把打包验证收敛为“后端二进制单独验证”

文件：
- 无代码文件变更；执行时使用现有打包产物和只读/一次性验证脚本

验证对象：
- [`desktop/release/mac-arm64/Daisy.app`](file:///Users/anykong/Daisy_Demo/desktop/release/mac-arm64/Daisy.app)
- [`desktop/release/Daisy-0.1.0-arm64.dmg`](file:///Users/anykong/Daisy_Demo/desktop/release/Daisy-0.1.0-arm64.dmg)

执行方式：
- 不以 Electron 主进程为主验证入口
- 直接运行 `Daisy.app/Contents/Resources/daisy_backend/daisy_backend`
- 指定独立 `DAISY_DATA_DIR`、`DAISY_CONFIG_PATH`、`PORT`

为什么：
- Electron 单实例锁、系统 sandbox、端口冲突都不是这次 mem0 根因的一部分
- 直接验证 PyInstaller 后端二进制，能把噪音压到最低

怎么做：
- 启动打包后的后端可执行文件
- 调 `/health`、`/api/auth/local_session`、`/api/chat`、`/api/chat/history`
- 用“两轮跨会话问答”验证写入与召回
- 检查隔离数据目录下的 `mem0/history.db` 和日志是否还出现 `readonly database`

### 变更 4：只在 mem0 最小复现仍失败时，回到更精确的内部补丁

文件：
- 预期仍是 [`Daisy_server/app/services/memory.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/app/services/memory.py)
- 如有必要，再进一步看打包后 `_internal/mem0/...` 的真实行为

修改策略：
- 只在“保留 `_init_mem0_home()` + 显式 `history_db_path`”仍然失败时，才考虑二级补丁
- 二级补丁必须以**最小复现证据**为前提，例如明确记录：
  - 运行时 `mem0.memory.setup.mem0_dir`
  - `self.memory.db.db_path`
  - `history` 表是否为空

为什么：
- 现在最缺的是“真实写入失败点”的证据，而不是更多补丁
- 继续堆兜底只会让现象更模糊

怎么做：
- 若需要，再加临时诊断日志或最小内部探针
- 确认根因后再决定是否要引入替换 `db`、重建连接、或更细粒度的 mem0 适配

## Assumptions & Decisions

1. 当前计划默认：`fusion.py` 的导入修复保留，不再作为本轮主要怀疑对象。
2. 当前计划默认：`build_macos.sh` 的 `resolve_python()` 保留，因为它解决的是构建环境事实问题，不参与 `readonly database` 根因。
3. 当前计划把 `memory.py` 中“替换 `self.memory.db`”视为嫌疑补丁，优先移除后再验证。
4. 当前计划采用“后端二进制单跑”作为主验证路径，不把 Electron 外壳问题混入 mem0 根因分析。
5. 当前未发现 git 仓库根目录，因此执行阶段不依赖 git 辅助信息，而以文件对比和测试/日志为准。

## Verification Steps

### 第 1 轮：源码级验证

1. 跑 [`Daisy_server/tests/test_bundled_models_and_search_key.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/tests/test_bundled_models_and_search_key.py)
2. 跑 [`Daisy_server/tests/test_sidecar_lifecycle.py`](file:///Users/anykong/Daisy_Demo/Daisy_server/tests/test_sidecar_lifecycle.py) 中数据目录相关测试
3. 确认 `fusion.py` 相关回归测试仍通过

### 第 2 轮：打包级验证

1. 重新执行 [`packaging/build_macos.sh`](file:///Users/anykong/Daisy_Demo/packaging/build_macos.sh)
2. 确认新产物时间戳刷新：
   - [`desktop/release/mac-arm64/Daisy.app`](file:///Users/anykong/Daisy_Demo/desktop/release/mac-arm64/Daisy.app)
   - [`desktop/release/Daisy-0.1.0-arm64.dmg`](file:///Users/anykong/Daisy_Demo/desktop/release/Daisy-0.1.0-arm64.dmg)

### 第 3 轮：端到端验证

1. 用独立 `DAISY_DATA_DIR` 启动打包后端可执行文件
2. 发送“记住一件事，我的测试相机叫 X”后等待保存完成
3. 新会话追问“我的测试相机叫什么名字？”
4. 验证：
   - 日志中不再出现 `attempt to write a readonly database`
   - `mem0/history.db` 存在且 `history` 表有记录
   - 记忆检索 `retrieved_count > 0`
   - AI 回复能取回 X

### 第 4 轮：收尾

1. 若第 3 轮成功，则不再保留额外 mem0 兜底补丁
2. 若第 3 轮失败，则记录失败点并只针对失败点追加最小修复，不扩散修改面
