# TASK_Whitelist_Management

## 1. 任务列表

### Task 1: Backend - 核心逻辑实现
- **目标**: 实现白名单的读取和写入逻辑。
- **文件**: `Daisy_server/app/core/config.py`
- **内容**:
  - 增加 `save_whitelist(data)` 函数。
  - 确保写入 `whitelist.json` 时的格式正确。

### Task 2: Backend - API 实现
- **目标**: 创建管理接口。
- **文件**: `Daisy_server/app/api/admin.py`
- **内容**:
  - 定义 `WhitelistUserAdd` 模型。
  - 实现 `GET /whitelist`。
  - 实现 `POST /whitelist/user`。
  - 实现 `DELETE /whitelist/user/{username}`。
  - 增加权限验证 `get_current_user` 和 `is_superuser` 检查。

### Task 3: Backend - 路由注册
- **目标**: 暴露管理接口。
- **文件**: `Daisy_server/app/main.py` (或 `server.py`，需确认 router 注册位置)
- **内容**:
  - 引入 `admin.router`。
  - 注册路由 `/api/admin`。

### Task 4: Frontend - 组件开发
- **目标**: 开发白名单管理界面。
- **文件**: `Daisy_front/src/components/WhitelistManager.tsx`
- **内容**:
  - 使用 Ant Design `Table`, `Form`, `Input`, `Select`, `Button`。
  - 实现数据获取和展示。
  - 实现添加和删除的交互逻辑。

### Task 5: Frontend - 集成
- **目标**: 在主界面显示管理入口。
- **文件**: `Daisy_front/src/App.tsx`
- **内容**:
  - 引入 `WhitelistManager`。
  - 在 Tabs 中根据 `isSuperUser` 添加 "白名单管理" Tab。

### Task 6: 验证与验收
- **目标**: 确保功能正常。
- **内容**:
  - 手动测试添加、删除流程。
  - 验证权限控制。
  - 检查 `whitelist.json` 文件变化。

## 2. 依赖关系
Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5 -> Task 6
