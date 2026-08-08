# ALIGNMENT_Whitelist_Management

## 1. 项目上下文分析
- **现状**: 
  - `Daisy_server` 使用 `whitelist.json` 存储允许注册的用户列表和管理员列表。
  - `whitelist.json` 目前需要手动修改文件来添加新用户。
  - 前端 `Daisy_front` 只有基本的登录/注册/聊天功能，管理员功能仅限于系统设置 (`UserLLMConfig`)。
  - `Daisy_server/app/core/config.py` 中的 `load_whitelist` 函数负责读取白名单。
  - `Daisy_server/app/api/auth.py` 在注册时会检查用户是否在白名单中。

- **需求**: 
  - 修改前后端，增加功能。
  - 管理员具备增加账号白名单的能力。
  - 先设计方案再实施。

- **约束**:
  - 必须使用中文回答和注释。
  - 保持现有代码风格。
  - 使用 React (Frontend) 和 FastAPI (Backend)。

## 2. 需求理解确认
- **核心目标**: 提供一个图形化界面，允许管理员查看和添加白名单用户。
- **功能点**:
  1.  **后端 API**:
      -   `GET /api/admin/whitelist`: 获取当前白名单（仅管理员可访问）。
      -   `POST /api/admin/whitelist`: 添加新用户到白名单（仅管理员可访问）。
  2.  **前端 UI**:
      -   在管理员视图中添加“白名单管理”标签页。
      -   展示当前白名单列表。
      -   提供表单输入用户名（和可选的性别）并提交。

- **边界**:
  - 仅管理员 (`is_superuser`) 可以操作。
  - 白名单存储在 `whitelist.json` 文件中，操作需持久化到该文件。
  - 不需要实现删除功能（用户未明确要求，且为了简化 MVP，但最好预留接口或简单实现）。
  - 不需要复杂的权限管理，仅区分管理员和普通用户。

## 3. 智能决策策略

### 问题 1: 白名单数据结构
- **现状**: `whitelist.json` 的 `users` 字段支持字符串列表或对象列表 `{"username": "name", "gender": "male"}`。
- **决策**: 新增接口应支持添加带有性别的用户对象，以保持数据结构的完整性。默认性别可设为 "male" 或 "female"。

### 问题 2: 并发写问题
- **现状**: `whitelist.json` 是一个文件。
- **决策**: 由于是低频操作（管理员添加用户），简单的文件读写覆盖即可，不需要复杂的数据库锁。但在代码层面应加个简单的内存锁防止瞬间并发写入导致文件损坏。

### 问题 3: 前端展示位置
- **现状**: 管理员登录后可以看到 "系统设置" (`UserLLMConfig`)。
- **决策**: 新增一个 "白名单管理" (`WhitelistManager`) 组件，并在 `App.tsx` 的 Tabs 中添加一个新的 Tab。

## 4. 最终共识 (预判)
- **后端**: 新增 `app/api/admin.py`，包含白名单管理的 CRUD 接口。
- **前端**: 新增 `src/components/WhitelistManager.tsx`，集成到 `App.tsx`。
- **数据**: 直接操作 `Daisy_server/whitelist.json`。

## 5. 待确认事项
- 是否需要删除白名单功能？(建议一并实现，方便管理) -> **决定实现删除功能**，因为只加不删不符合管理闭环。
