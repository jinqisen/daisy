import os
import yaml
import structlog
from typing import Dict, Any, Optional
from jinja2 import Template, Environment, FileSystemLoader

logger = structlog.get_logger()

class PromptLoader:
    """
    单例模式的提示词加载器。
    负责从 Daisy_prompts 目录加载 YAML 文件，并使用 Jinja2 渲染提示词。
    """
    _instance = None
    
    def __init__(self):
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self.base_dir = self._find_prompts_dir()
        self.jinja_env = Environment(loader=FileSystemLoader(self.base_dir) if self.base_dir else None)
        self.reload()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PromptLoader()
        return cls._instance

    def _find_prompts_dir(self) -> Optional[str]:
        """
        查找 Daisy_prompts 目录。
        优先级:
        1. 环境变量 DAISY_PROMPTS_DIR
        2. 默认容器路径 /app/Daisy_prompts
        3. 相对路径回溯 (Legacy, with warning)
        """
        # 1. 环境变量 DAISY_PROMPTS_DIR (最高优先级)
        env_dir = os.getenv("DAISY_PROMPTS_DIR")
        if env_dir:
            if os.path.exists(env_dir):
                logger.info(f"Using prompts directory from environment variable: {env_dir}")
                return env_dir
            else:
                logger.warning(f"DAISY_PROMPTS_DIR is set to '{env_dir}' but directory does not exist.")

        # 2. 默认容器路径
        container_path = "/app/Daisy_prompts"
        if os.path.exists(container_path):
            logger.info(f"Using standard container prompts directory: {container_path}")
            return container_path

        # 3. 相对路径回溯 (Legacy Fallback) - REMOVED
        # app/core/prompt_loader.py -> app/core -> app -> Daisy_server -> Daisy_Demo
        # current_dir = os.path.dirname(os.path.abspath(__file__))
        # legacy_path = os.path.abspath(os.path.join(current_dir, "../../../Daisy_prompts"))
        
        # if os.path.exists(legacy_path):
        #    logger.warning(f"Using legacy relative path for prompts: {legacy_path}. This is deprecated. Please set DAISY_PROMPTS_DIR in .env.")
        #    return legacy_path
            
        logger.error("Could not find Daisy_prompts directory. Please set DAISY_PROMPTS_DIR environment variable.")
        return None

    def reload(self):
        """
        重新加载所有提示词文件。
        """
        if not self.base_dir:
            logger.error("Prompt directory not set. Cannot load prompts.")
            return

        self.prompts = {}
        logger.info(f"Loading prompts from {self.base_dir}...")
        
        for root, _, files in os.walk(self.base_dir):
            for file in files:
                if file.endswith(('.yaml', '.yml')):
                    try:
                        file_path = os.path.join(root, file)
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = yaml.safe_load(f)
                            
                        if not data or 'name' not in data or 'template' not in data:
                            logger.warning(f"Skipping invalid prompt file: {file}")
                            continue
                            
                        prompt_name = data['name']
                        self.prompts[prompt_name] = data
                        logger.debug(f"Loaded prompt: {prompt_name}")
                        
                    except Exception as e:
                        logger.error(f"Error loading prompt file {file}: {e}")
                        
        logger.info(f"Loaded {len(self.prompts)} prompts.")

    def render(self, prompt_name: str, **kwargs) -> str:
        """
        渲染指定的提示词。
        
        Args:
            prompt_name: YAML 文件中定义的 name 字段
            **kwargs: 传递给 Jinja2 模板的变量
            
        Returns:
            渲染后的字符串
        """
        if prompt_name not in self.prompts:
            logger.error(f"Prompt '{prompt_name}' not found.")
            return f"Error: Prompt '{prompt_name}' not found."
            
        prompt_data = self.prompts[prompt_name]
        template_str = prompt_data['template']
        
        try:
            # 使用 Jinja2 渲染
            # 注意: 这里我们每次都创建 Template 对象，对于高性能场景可以考虑缓存 Template 对象
            # 但考虑到 Prompt 主要是字符串操作，且并发量可控，目前可接受
            template = self.jinja_env.from_string(template_str)
            return template.render(**kwargs)
        except Exception as e:
            logger.error(f"Error rendering prompt '{prompt_name}': {e}")
            raise e

    def get_raw_template(self, prompt_name: str) -> Optional[str]:
        if prompt_name in self.prompts:
            return self.prompts[prompt_name]['template']
        return None
