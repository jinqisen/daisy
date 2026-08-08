# CONSENSUS_Whitelist_Management

## 1. 最终需求描述
在 Daisy 系统中增加白名单管理功能，允许管理员通过前端界面动态查看、添加和删除白名单用户。

## 2. 技术实现方案

### 2.1 后端 (Daisy_server)
- **新增模块**: `app/api/admin.py`
- **新增接口**:
  - `GET /api/admin/whitelist`: 获取白名单列表（Users 和 Admins）。
  - `POST /api/admin/whitelist/user`: 添加用户到白名单。
  - `DELETE /api/admin/whitelist/user/{username}`: 从白名单删除用户。
- **数据持久化**:
  - 修改 `app/core/config.py`，增加 `save_whitelist(data)` 函数。
  - 确保操作 `whitelist.json` 时的原子性或加锁。
- **权限控制**:
  - 所有 Admin 接口需验证 `current_user.is_superuser`。

### 2.2 前端 (Daisy_front)
- **新增组件**: `src/components/WhitelistManager.tsx`
  - 使用 Ant Design 的 `Table` 展示用户列表。
  - 使用 `Form` 和 `Modal` (或行内输入) 添加新用户（用户名 + 性别）。
  - 提供删除按钮。
- **集成**:
  - 修改 `src/App.tsx`，在 `isSuperUser` 为 true 时，添加 "白名单管理" Tab。

## 3. 验收标准
1.  **添加用户**:
    -   管理员登录后，在“白名单管理”界面输入用户名 "new_user" 和性别 "female"，点击添加。
    -   界面刷新显示新用户。
    -   后端 `whitelist.json` 文件中新增该用户记录。
    -   新用户 "new_user" 可以成功注册。
2.  **删除用户**:
    -   管理员点击 "new_user" 旁的删除按钮。
    -   界面刷新，用户消失。
    -   后端 `whitelist.json` 文件中该用户被移除。
3.  **权限验证**:
    -   非管理员用户无法访问 `/api/admin/whitelist` 接口（返回 403 或 401）。
    -   前端对非管理员隐藏“白名单管理”入口。

## 4. 风险评估
- **并发写入**: 极低概率，但若两个管理员同时修改，可能覆盖。MVP 阶段可忽略，或简单的文件锁。
- **文件格式**: 需确保 `whitelist.json` 格式严格符合预期，避免手动修改破坏导致系统崩溃。后端增加容错。

## 5. 下一步计划
- 进入 **Architect** 阶段，设计详细 API 定义和组件结构。
