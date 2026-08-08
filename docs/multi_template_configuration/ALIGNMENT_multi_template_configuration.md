# ALIGNMENT_multi_template_configuration

## 1. 项目上下文分析

### 现有架构
- **用户模型**: `UserDB` 仅包含 `username`, `password`, `is_active`, `is_superuser`。无性别字段。
- **配置加载**: `default_settings.json` 存储单一的默认 AI 角色配置。
- **初始化逻辑**: `ensure_user_settings` (在 `auth.py` 中) 和 `init_personality_data` (在 `init_data.py` 中) 调用 `load_default_settings` 加载配置并写入数据库。

### 需求理解
- **目标**: 支持多模板配置，适配不同性别的用户。
- **场景**:
  - 用户注册时，根据某种规则（如性别）选择不同的 AI 角色模板。
  - 例如：男性用户 -> 匹配女性 AI；女性用户 -> 匹配男性 AI。

## 2. 疑问与决策

### 关键决策点
1.  **用户性别存储**:
    - 由于 `UserDB` 表没有性别字段，且不想进行复杂的数据库迁移。
    - **决策**: 注册接口 (`/register`) 接收可选的 `gender` 参数，但不持久化存储到 `UserDB`。仅在注册成功后的即时初始化阶段 (`ensure_user_settings`) 使用该参数来选择模板。

2.  **模板结构**:
    - **决策**: 修改 `default_settings.json` 的结构，使其包含多个模板。使用键值对形式，例如 `"male"` (针对男性用户) 和 `"female"` (针对女性用户)。

3.  **默认行为**:
    - 如果注册时未提供性别，或提供的性别无对应模板，应有回退机制（例如随机选择或使用默认）。
    - **决策**: 默认使用 `"male"` 用户对应的模板（即女性 AI），或者随机。为了稳定性，暂定默认 `"male"` (得到女性 AI，保持现有行为一致性)。

## 3. 规范定义

### 配置文件变更 (`default_settings.json`)
结构将变为：
```json
{
  "male": { ... AI settings for male user ... },
  "female": { ... AI settings for female user ... }
}
```

### 接口变更 (`auth.py`)
- `UserCreate` Pydantic 模型增加 `gender: str = "male"` (可选)。
- `register` 函数接收此参数，并传递给 `ensure_user_settings`。
- `ensure_user_settings` 接收 `user_gender` 参数，调用 `load_default_settings(user_gender)`。

### 配置逻辑变更 (`config.py`)
- `load_default_settings` 增加参数 `user_gender: str = "male"`。
- 解析 JSON，根据 `user_gender` 返回对应配置。

### 验证标准
- 注册接口能接收 `gender`。
- 传入 `gender="female"` 时，初始化的 AI 角色应为男性（根据模板定义）。
- 传入 `gender="male"` 时，初始化的 AI 角色应为女性（根据模板定义）。
