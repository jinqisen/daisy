import logging
import logging.handlers
import os
import sys
import queue
import json
import structlog
import time
import functools
from typing import Any, Dict
from .config import settings, get_writable_data_dir

# 常量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 冻结环境下包内只读,日志必须落在可写数据目录
LOG_DIR = os.path.join(get_writable_data_dir(), "log")
LOG_FILE = os.path.join(LOG_DIR, "system.log")

_listener = None

class ConsoleFormatter(logging.Formatter):
    """
    自定义控制台输出格式化器。
    解析 structlog 生成的 JSON 字符串并输出简化的易读字符串。
    """
    def format(self, record):
        msg = record.msg
        if isinstance(msg, str) and msg.strip().startswith('{'):
            try:
                log_dict = json.loads(msg)
                # 提取所需信息
                timestamp = log_dict.get('timestamp', '')
                level = log_dict.get('level', record.levelname).upper()
                event = log_dict.get('event', '')
                
                # 异常信息（如果存在）
                exc_info = log_dict.get('exception', '')
                
                # 构建简化消息
                # 格式: [Timestamp] [LEVEL] Event Message key=value key=value
                formatted_msg = f"[{timestamp}] [{level}] {event}"
                
                # 添加其他字段
                ignored_keys = {'timestamp', 'level', 'event', 'exception'}
                extra_keys = [k for k in log_dict.keys() if k not in ignored_keys]
                
                if extra_keys:
                    extra_str = " ".join(f"{k}={log_dict[k]}" for k in extra_keys)
                    formatted_msg += f" {extra_str}"
                
                if exc_info:
                    formatted_msg += f"\n{exc_info}"
                    
                return formatted_msg
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # 回退到默认行为
        return super().format(record)

def configure_logging(log_filename: str = "system.log"):
    global _listener
    
    # 1. 创建日志目录
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    log_file_path = os.path.join(LOG_DIR, log_filename)

    # 2. 设置带 QueueHandler 的标准日志记录 (异步)
    log_queue = queue.Queue(-1)  # 无大小限制
    queue_handler = logging.handlers.QueueHandler(log_queue)

    # 文件处理器 (实际写入者)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)

    # 格式化器
    # 对于文件：Structlog 将渲染为 JSON 字符串，所以我们只输出消息
    json_formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(json_formatter)
    
    # 对于控制台：使用我们自定义的格式化器简化输出
    console_formatter = ConsoleFormatter('%(message)s')
    console_handler.setFormatter(console_formatter)

    # 在单独线程中运行的监听器
    _listener = logging.handlers.QueueListener(
        log_queue, 
        console_handler, 
        file_handler, 
        respect_handler_level=True
    )
    _listener.start()

    # 3. 配置 Structlog
    # 我们希望使用标准日志记录进行过滤/处理，但使用 structlog 进行格式化
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars, # 合并异步上下文变量 (user_id 等)
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(ensure_ascii=False) # 渲染为 JSON 字符串
        ],
        logger_factory=structlog.stdlib.LoggerFactory(), # 委托给标准日志记录
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 配置根日志记录器
    root_logger = logging.getLogger()
    # 移除现有处理器以避免重复
    if root_logger.handlers:
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)
            
    root_logger.addHandler(queue_handler)
    
    # 从配置设置日志级别
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(level)

    return _listener

def shutdown_logging():
    global _listener
    if _listener:
        _listener.stop()

# 获取logger实例
logger = structlog.get_logger()

def monitor_execution_time(func):
    """
    Decorator to monitor the execution time of a function.
    Logs 'CHARACTER_PERFORMANCE' events with duration.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = func.__name__
        try:
            result = await func(*args, **kwargs)
            end_time = time.time()
            duration = end_time - start_time
            
            # 使用 structlog 记录结构化日志
            logger.info("CHARACTER_PERFORMANCE", 
                        function=func_name, 
                        duration_seconds=round(duration, 4),
                        status="success")
            return result
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error("CHARACTER_PERFORMANCE", 
                         function=func_name, 
                         duration_seconds=round(duration, 4),
                         status="error",
                         error=str(e))
            raise
    return wrapper
