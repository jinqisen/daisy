from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List, Union, Dict, Any
import os
import sys
import json
import logging
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 配置来源与优先级
#
#   真实环境变量  >  server_config.json  >  .env  >  Python 字段默认值
#
# `server_config.json` 压过 `.env` 是**刻意的**:前者是用户在界面上改出来的,
# 后者只是开发者本地的文件。反过来的话,开发机上的 .env 会静默压掉用户设置 ——
# 换嵌入模型那次事故正是如此:只改了 Python 默认值,而 .env 与 json 还指向旧模型,
# 三处不一致且没有任何地方能看出「当前生效的是哪一份」。
#
# 难点在于 load_dotenv 会把 .env 灌进 os.environ,之后就与真实环境变量无从区分。
# 所以在加载任何文件**之前**先记下真实环境变量的键集合,它才是最高优先级。
# ---------------------------------------------------------------------------
_REAL_ENV_KEYS = frozenset(os.environ.keys())

# 每个配置项最终来自哪里,启动时打印一行,排查"三处不一致"用
CONFIG_PROVENANCE: Dict[str, str] = {k: "环境变量" for k in _REAL_ENV_KEYS}

# 显式加载 .env 文件到环境变量中，以便 os.environ.get 能获取到
# 使用绝对路径确保在任何工作目录下都能找到 .env
_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_path = os.path.join(_base_dir, ".env")

# 如果项目根目录下没有 .env，尝试上级目录 (Docker 容器中常见结构 /app/.env vs /app/Daisy_server/...)
if not os.path.exists(_env_path):
    _parent_env_path = os.path.join(os.path.dirname(_base_dir), ".env")
    if os.path.exists(_parent_env_path):
        _env_path = _parent_env_path

def load_config_sources(
    env_path: str,
    config_path: Optional[str],
    real_env_keys: frozenset,
    provenance: Dict[str, str],
    environ: Optional[Dict[str, str]] = None,
) -> None:
    """
    按优先级把各来源灌进环境变量:真实环境变量 > server_config.json > .env。

    做成独立函数而不是模块顶层的一段代码,是因为**优先级是这里最容易错、
    也最难发现错了的东西** —— 写在顶层就只能靠"再实现一遍"来测,
    而模仿实现本身就会引入偏差(第一版测试正是这样自己骗了自己)。

    environ 可注入,便于在不污染当前进程的情况下验证优先级。
    """
    env = os.environ if environ is None else environ

    load_dotenv(env_path)
    if environ is not None and env is not os.environ:
        # 注入模式:load_dotenv 只会写 os.environ,这里手工搬运
        from dotenv import dotenv_values
        for k, v in dotenv_values(env_path).items():
            if v is not None and k not in env:
                env[k] = v
    for k in list(env.keys()):
        provenance.setdefault(k, ".env")

    if not config_path or not os.path.exists(config_path):
        return
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        for k, v in file_config.items():
            # 空值表示"用户还没填这一项",不是"用户要求置空"。
            # 设置界面对未填字段写的就是 "",若把它当成有效值,就会**覆盖掉**
            # .env 里的真实配置。实测踩到过:server_config.json 里
            # MAAS_API_KEY 是 "",而 .env 里是真实密钥,启动后报
            # "no usable LLM provider is configured" —— 报错信息完全指向别处,
            # 排查时根本想不到是配置来源的优先级。
            #
            # 改优先级之前不会有这个问题:那时的规则是"键已在环境中就跳过",
            # .env 的值恰好受到保护。提高 json 的优先级就必须同时定义清楚
            # "什么算作已配置"。
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            key = k.upper()

            # 只让位于**真实环境变量**(Docker/CI/命令行显式指定)。
            # .env 带进来的值要被覆盖 —— 用户在界面上的设置优先于开发者本地文件。
            if key in real_env_keys:
                continue

            env[key] = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            provenance[key] = "server_config.json"
        # logging isn't configured yet, using print
        print(f"Loaded configuration from {config_path}")
    except Exception as e:
        print(f"Warning: Failed to load server_config.json: {e}")


# 桌面打包(冻结)环境下 __file__ 在 PYZ 内、_base_dir 无此文件,
# 故优先用 DAISY_CONFIG_PATH(由 desktop_main 指向用户数据目录的配置副本)。
_config_path = os.environ.get("DAISY_CONFIG_PATH") or os.path.join(_base_dir, "server_config.json")
load_config_sources(_env_path, _config_path, _REAL_ENV_KEYS, CONFIG_PROVENANCE)


def describe_config_sources(keys: List[str]) -> List[str]:
    """
    给出若干关键配置项「当前值来自哪里」。启动时打一行,
    上次那类"三处配置不一致、排查很久"的问题有这行日志就是 10 秒的事。
    """
    lines = []
    for k in keys:
        key = k.upper()
        src = CONFIG_PROVENANCE.get(key, "字段默认值")
        # 取**实际生效值**,而不是 os.environ —— 走字段默认值的项在环境里根本不存在,
        # 而那恰恰是最需要看清的情况(排查时最容易误判成"没配置")。
        val = getattr(settings, key, None)
        if val is None:
            val = os.environ.get(key)
        if isinstance(val, str) and val and any(
            s in key for s in ("KEY", "SECRET", "PASSWORD", "TOKEN")
        ):
            val = f"<已设置 {len(val)} 字符>"
        lines.append(f"{k}={val} (来自 {src})")
    return lines

from pydantic import Field, model_validator, ConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

    PROJECT_NAME: str = "AI Companion Emotion Engine"
    API_V1_STR: str = "/api"
    
    # OpenAI / SiliconFlow
    # Removed unused configs
    
    # Embedding Configuration
    EMBEDDING_PROVIDER: str = Field("openai_compatible")
    EMBEDDING_MODEL_NAME: str = Field("text-embedding-3-small")

    # 嵌入向量维度。必须与 EMBEDDING_MODEL_NAME 实际输出一致 ——
    # 不一致时 Qdrant 会拒绝写入,长期记忆静默失效。
    # bge-small-zh-v1.5 = 512;bge-large-zh-v1.5 / bge-m3 = 1024。
    # 换模型时**务必同步改这里**,并清空已有向量库(旧向量维度不兼容)。
    EMBEDDING_DIMS: int = Field(1536)
    
    # LLM Default Configuration
    DEFAULT_LLM_PROVIDER: str = Field("openai_compatible")
    DEFAULT_LLM_BASE_URL: str = Field("https://api.openai.com/v1")
    DEFAULT_LLM_MODEL_NAME: str = Field("gpt-4o")
    
    # Lightweight Model Configuration (For Router/ReAct)
    LIGHTWEIGHT_LLM_MODEL_NAME: str = Field("gpt-4o-mini")
    STANDARD_LLM_MODEL_NAME: Optional[str] = Field(None)
    DEEP_LLM_MODEL_NAME: Optional[str] = Field(None)
    DEEP_FINAL_TIMEOUT_SEC: int = Field(25)
    DEEP_TOOL_MAX_STEPS: int = Field(3)
    DEEP_TOOL_STEP_TIMEOUT_SEC: int = Field(10)
    TOOL_RESULT_MAX_CHARS: int = Field(1200)
    DEEP_ALLOWED_TOOLS: List[str] = Field(default_factory=lambda: ["search", "calculator"])
    TOKEN_EST_CHARS_PER_TOKEN: int = Field(4)
    EST_COST_PER_1K_INPUT_USD: Optional[float] = Field(None)
    EST_COST_PER_1K_OUTPUT_USD: Optional[float] = Field(None)
    # 工作流级预算上限(core/budget.py)。None = 不启用检查,行为与无预算时一致
    # 单次执行的预算上限。原先默认 None(不限),而桌面版用户是自付 token ——
    # 一次 DEEP 对话实测 11 次 LLM 调用,任何异常循环都直接烧在用户账上。
    # 取值依据:实测 DEEP 峰值 11 次 / 约 2 万 tokens,留约 2 倍余量。
    # 超限只在工具循环等控制点早退,不会中断已在进行的最终生成。
    EXEC_BUDGET_MAX_TOKENS: Optional[int] = Field(40000)
    EXEC_BUDGET_MAX_LLM_CALLS: Optional[int] = Field(25)

    # 深度角色卡生成的超时上限。该生成是一次大 Prompt 的慢 LLM 调用,原实现无超时,
    # 挂住会让后台任务永久悬空。超时后保留默认角色卡,用户不受影响。
    # ---- 主动关心 ----
    # 这些值原先硬编码在 ProactiveService 里,且被一路调激进过
    # (每日 3→5、冷却 4h→2h、忙碌保护 5m→2m),每次改动都没留下依据。
    # 移到配置有两个目的:可调,以及让"当前用的是什么值"一目了然。
    #
    # 取值原则:陪伴产品最大的翻车方式不是"不够热情",而是变成打扰 ——
    # 打扰的代价不可逆(用户觉得烦就卸载,不会回来)。宁可偏保守。
    PROACTIVE_MAX_DAILY: int = Field(3)            # 真人朋友不会一天主动找你五次
    PROACTIVE_COOLDOWN_HOURS: float = Field(4)
    # 情绪场景**不加频**:负面情绪下说错话的代价远高于不说话。
    # override 的意义是换语气(更克制),不是提高打扰频率。
    PROACTIVE_EMOTION_COOLDOWN_HOURS: float = Field(4)
    # 忙碌保护:刚聊完两分钟又主动开口不像陪伴,像没话找话。
    PROACTIVE_BUSY_GUARD_MINUTES: int = Field(90)
    # 静默时段(本地时间,含头不含尾)。原先只靠"活跃概率<5%"判断,
    # 而冷启动默认返回 0.05,`0.05 < 0.05` 为假 —— 新用户毫无静默保护,
    # 半夜也会被打扰。这里加一道硬性兜底。
    PROACTIVE_QUIET_START_HOUR: int = Field(23)
    PROACTIVE_QUIET_END_HOUR: int = Field(8)

    DEEP_CARD_TIMEOUT_SEC: int = Field(150)

    # 深度卡单次 LLM 请求的超时。必须**小于** DEEP_CARD_TIMEOUT_SEC,否则外层保护
    # 形同虚设:原先内层沿用通用 60s 且重试 1 次 = 122s 才失败,已超过外层 90s。
    DEEP_CARD_LLM_TIMEOUT_SEC: int = Field(120)

    # 单进程嵌入模式(本地 C 端桌面 App):缓存用进程内实现、Qdrant 走本地路径、
    # ARQ worker 并入后端(chat 走进程内异步任务,不再需要独立 worker 与消息 broker)。
    # 关闭时为标准 server 部署形态(真实 Redis + 独立 worker),行为不变。
    EMBEDDED_MODE: bool = Field(False)

    # 关闭 Qwen3 系列的内置 thinking 模式(services/llm.py)。
    # 实测(2026-07-21,qwen3-32b):默认会额外生成 ~600 字符不可见的 reasoning_content,
    # 白白消耗 45% 的 completion_tokens。关闭后提速 27-48%,而 prompt 中显式要求的
    # CoT(Step 1-3)仍完整保留在可见输出中,策略判断分歧落在 temperature 随机性范围内
    # (分歧用例重复采样:开 thinking 自身即 Ludus/Storge 各半)。
    # 置 False 可回退到模型默认行为。
    DISABLE_QWEN_THINKING: bool = Field(True)

    # Reflexion 演化触发阈值(services/reflexion/service.py)。
    # 默认值按 2026-07 实测 S 分布校准(n=82: min 0.49 / p50 0.77 / max 0.86,
    # 其中 D_R 尚为桩数据恒 0.98,给每个 S 固定托底约 +0.20):
    # - 补丁触发 S<=0.65 ≈ 底部 2-5% 差轮次(原 0.40 在该分布下不可达,补丁从未生成过)
    # - exemplar 触发 S>=0.82 ≈ 顶部 5% 优质轮次(原 0.85 仅 1% 可达)
    # D_R 接入真实数据后需重新校准。
    REFLEXION_PATCH_THRESHOLD: float = Field(0.65)
    REFLEXION_EXEMPLAR_THRESHOLD: float = Field(0.82)
    DEFAULT_CHARACTER_CARD_PATH: str = Field("./Daisy_server/assets/character_cards/default_character_card.json")

    # 存储
    # 这是 **Qdrant** 的本地数据目录(未设置 QDRANT_HOST 时使用)。
    # 默认值原先叫 ./chroma_db —— 早期用过 Chroma 的残留,名字与实际用途不符,
    # 排查向量库问题时会把人引到错误的方向。项目中已无 Chroma(依赖里也没有)。
    # 嵌入模式下由 sidecar 覆盖为 <数据目录>/qdrant_embedded,故此默认值只影响本地开发。
    VECTOR_DB_PATH: str = Field("./qdrant_db")
    QDRANT_HOST: Optional[str] = Field(None)
    QDRANT_PORT: int = Field(6333)
    
    # 模型配置
    _backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _model_dir = os.getenv("TARGET_MODEL_DIR")
    
    if not _model_dir:
        # Strict default: Project Root / model
        _model_dir = os.path.join(_backend_dir, "model")
        
    EMOTION_MODEL_NAME: str = Field(os.path.join(_model_dir, "bert-base-cased-goemotions-original"))
    
    # 情感上下文窗口配置
    EMOTION_CONTEXT_TURNS: int = Field(2)
    EMOTION_CONTEXT_MAX_CHARS: int = Field(300)

    # 策略配置
    PERSONALITY_SELECTION_MODE: str = Field("llm")
    
    # 话题总结配置
    TOPIC_SUMMARY_HISTORY_LIMIT: int = Field(20)

    # 日志
    LOG_LEVEL: str = Field("INFO")

    # 安全
    SECRET_KEY: str = Field(""  # 首次启动时自动生成随机密钥;生产环境请通过环境变量 SECRET_KEY 设置)
    ALGORITHM: str = Field("HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30)
    
    # 注册白名单原先以 ALLOWED_USERS / SUPERUSERS 两个字段出现在这里,
    # 在**类定义时**就调用 load_whitelist() 固化了内容。两个问题:全库零使用者,
    # 且即便有人用,管理接口改完白名单后它们也不会更新。已移至
    # services/system/whitelist.py —— 那是业务规则,不是基础设施。

    # Redis 配置
    REDIS_HOST: str = Field("localhost")
    REDIS_PORT: int = Field(6379)
    REDIS_DB: int = Field(0)
    REDIS_PASSWORD: Optional[str] = Field(None)

    # ARQ 配置
    ARQ_REDIS_SETTINGS: Optional[Dict[str, Any]] = None

    # Search Tools
    # HUAWEI_SEARCH_API_KEY: Optional[str] = Field(None) # Use MAAS_API_KEY as default env
    # HUAWEI_SEARCH_ENDPOINT: Optional[str] = Field(None)
    
    # API Keys (Loaded from environment)
    SILICONFLOW_API_KEY: Optional[str] = Field(None)
    MAAS_API_KEY: Optional[str] = Field(None)
    OPENAI_API_KEY: Optional[str] = Field(None)
    
    # OpenAI 兼容接口配置（用户可自定义任意第三方服务）
    OPENAI_BASE_URL: Optional[str] = Field(None)
    LLM_MODEL_NAME: Optional[str] = Field(None)
    
    # 直接在 Settings 中添加字段，不强制绑定到环境变量，通过 __init__ 逻辑处理
    HUAWEI_SEARCH_API_KEY: Optional[str] = Field(None)
    HUAWEI_SEARCH_ENDPOINT: Optional[str] = Field(None)
    
    def model_post_init(self, __context: Any) -> None:
        """
        Pydantic V2 post init hook
        """
        # 嵌入模式:强制清空远程服务地址,让所有消费方走本地路径/进程内实现。
        # 必须在此覆盖——.env 里可能设了远程 QDRANT_HOST/REDIS_HOST,会盖过环境变量。
        if self.EMBEDDED_MODE:
            self.QDRANT_HOST = None  # memory 服务据此改用本地嵌入 Qdrant 路径
            self.REDIS_HOST = "embedded"  # 仅占位;实际由进程内缓存接管(core/local_kv.py)

    def get_redis_settings(self):
        """
        获取 ARQ RedisSettings 对象
        """
        from arq.connections import RedisSettings
        return RedisSettings(
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            database=self.REDIS_DB,
            password=self.REDIS_PASSWORD
        )

    # CORS Configuration
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    # 注意:这里**不要**再写第二个 model_config。
    # 类体里的后一次赋值会直接覆盖前一次 —— 本文件曾在类尾多写了一个
    # `ConfigDict(env_file=".env", ...)`,把类首那个 SettingsConfigDict 顶掉了,结果:
    #   - env_file 从绝对路径变成相对 cwd(打包后 cwd 不确定,那一路读不到);
    #   - env_file_encoding="utf-8" 丢失(Windows 默认编码非 UTF-8,
    #     含中文注释的 .env 会解析失败);
    #   - 用的还是 ConfigDict 而非 SettingsConfigDict,env_file 语义不受保证。
    # 当时没出故障纯属巧合:模块顶部的 load_dotenv 已用绝对路径把 .env 灌进了环境。
    # 配置项统一加在类首的 model_config 里。

settings = Settings()
