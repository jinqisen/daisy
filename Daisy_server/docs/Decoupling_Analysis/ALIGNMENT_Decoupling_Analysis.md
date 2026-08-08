# ALIGNMENT_Decoupling_Analysis

## 1. 原始需求
用户询问 `e:\Daisy\Daisy_Demo\Daisy_prompts` 和 `e:\Daisy\Daisy_Demo\Daisy_server` 这两个项目的耦合度是否过深。

## 2. 项目现状分析

### 2.1 物理结构耦合
- **相对路径依赖**: `Daisy_server/app/core/prompt_loader.py` 中硬编码了回溯三层目录查找 `Daisy_prompts` 的逻辑 (`../../../Daisy_prompts`)。
- **构建依赖**: `Daisy_server/scripts/build_remote_image.ps1` 在构建 Docker 镜像时，需要手动将 `Daisy_prompts` 复制到构建上下文，并在 Dockerfile 中通过 COPY 指令硬性注入。

### 2.2 逻辑耦合
- **隐式契约**: `Daisy_server/app/prompts/templates.py` 中通过字符串字面量（如 `"get_costar_prompt"`）引用 `Daisy_prompts` 中的 YAML 文件名。
- **缺乏类型安全**: 如果 `Daisy_prompts` 中的文件名变更或参数模板变更，Server 端在运行时才会报错（Runtime Error），编译期无法发现。

### 2.3 现有优势
- **关注点分离**: 提示词工程师可以只修改 YAML，不需要动 Python 代码。
- **热更新潜力**: 虽然目前 `PromptLoader` 是单例且在启动时加载，但这种结构允许实现不重启服务器更新 Prompt。

## 3. 耦合度评估结论
**是，存在较深的结构性耦合。**
目前的耦合主要体现在“文件系统布局”和“构建流程”上。`Daisy_server` 不能作为一个独立的、自包含的单元运行，它强依赖于兄弟目录的存在。

## 4. 改进方案建议 (可选)

### 方案 A: 配置解耦 (推荐)
- 强制要求通过环境变量 `DAISY_PROMPTS_DIR` 指定路径，移除代码中的硬编码相对路径回溯。
- 在开发环境中，通过 `.env` 文件指定该路径。

### 方案 B: 包管理解耦 (更规范)
- 将 `Daisy_prompts` 封装为一个 Python 包 (pip installable)。
- Server 通过 `import daisy_prompts` 使用资源，利用 `importlib.resources` 读取文件。

### 方案 C: 协议解耦 (最重)
- 将 Prompt 管理独立为一个微服务（Prompt Registry）。
- Server 通过 API 获取 Prompt。

## 5. 待确认问题
1. 用户是否希望进行解耦重构？
2. 如果重构，倾向于哪种程度的解耦（方案 A/B/C）？
