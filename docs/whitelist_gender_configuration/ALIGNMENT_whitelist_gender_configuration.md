# ALIGNMENT_whitelist_gender_configuration

## 1. 项目上下文分析

### 现有架构
- **白名单机制**: `whitelist.json` 包含允许注册的用户名列表 (`users`) 和管理员列表 (`admins`)。
- **配置加载**: `load_whitelist` 函数读取此文件。
- **注册流程**: 用户注册时检查用户名是否在 `users` 列表中。
- **性别与模板**: 之前的修改中，性别通过注册接口的 `gender` 参数传入。

### 需求理解
- **目标**: 将用户性别定义移至白名单 (`whitelist.json`)，而不是在注册时由用户填写。
- **意图**: 管理员预先定义好每个允许注册用户的性别，系统根据此信息自动匹配 AI 模板。

## 2. 疑问与决策

### 关键决策点
1.  **白名单结构变更**:
    - 原结构: `"users": ["user1", "user2"]`
    - 新结构: 需支持性别关联。
    - **方案**: 将 `users` 字段改为对象列表或字典。考虑到向后兼容性和易读性，字典可能更好？或者对象列表。
    - **决策**: 使用对象列表，每个对象包含 `username` 和 `gender`。
    - 示例: `{"username": "jinqisen", "gender": "male"}`。
    - 同时为了兼容旧的简单字符串列表，代码需做类型检查。

2.  **默认性别**:
    - 如果白名单中只定义了用户名（旧格式），或新格式中未指定性别，默认为 `male`。

3.  **注册接口变更**:
    - 移除 `UserCreate` 中的 `gender` 字段（或者将其设为可选但不使用，但最好是移除以符合需求“不要在注册中填写”）。
    - 注册逻辑改为：从白名单中查找该用户名的对应性别。

## 3. 规范定义

### 白名单文件变更 (`whitelist.json`)
```json
{
  "users": [
    {"username": "jinqisen", "gender": "male"},
    {"username": "luyi", "gender": "female"},
    "old_user_string_format" 
  ],
  "admins": [...]
}
```
*注：为了简化，也可以让 `users` 既支持字符串也支持对象。*

### 接口变更 (`auth.py`)
- `UserCreate`: 移除 `gender` 字段。
- `register`:
  1. 加载白名单。
  2. 验证用户名是否在白名单中。
  3. 获取该用户名的预设性别（如果白名单项是字符串，默认为 "male"；如果是对象，取 `gender` 字段）。
  4. 调用 `ensure_user_settings(..., user_gender=found_gender)`。

### 配置逻辑变更 (`config.py`)
- `load_whitelist`: 逻辑保持不变（直接返回 JSON 数据），但在使用处需要处理复杂结构。或者，更新 `load_whitelist` 以标准化输出结构（但这可能影响其他使用白名单的地方）。
- **策略**: 保持 `load_whitelist` 简单，只负责加载。在 `auth.py` 中处理查找逻辑。

### 验证标准
- 注册时不传 `gender`。
- 根据 `whitelist.json` 中的定义，不同用户注册后获得不同的 AI 角色。
