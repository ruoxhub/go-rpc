import sys
import json
import threading
import datetime
import time
from copy import copy
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
from functools import wraps
from loguru import logger

from common.errors import redact_secrets, redact_value


def _redact_exception(exception):
    if exception is None:
        return None
    safe_message = redact_secrets(str(exception.value))
    if safe_message == str(exception.value):
        return exception
    try:
        safe_value = copy(exception.value)
        safe_value.args = tuple(
            redact_value(argument) for argument in exception.value.args
        )
        if str(safe_value) != safe_message:
            raise ValueError
    except Exception:
        safe_value = RuntimeError(safe_message)
    return type(exception)(type(safe_value), safe_value, exception.traceback)


def _log_patcher(record):
    """补丁函数：如果绑定了 module 属性，则覆盖 record['name'] 供格式化使用"""
    if "module" in record["extra"]:
        record["name"] = record["extra"]["module"]
    record["message"] = redact_secrets(str(record["message"]))
    record["extra"] = redact_value(record["extra"])
    record["exception"] = _redact_exception(record["exception"])

# 应用补丁后的全局 logger
logger = logger.patch(_log_patcher)

class LogLevel(str, Enum):
    TRACE = "TRACE"
    DEBUGGER = "DEBUGGER"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class LogConfig:
    logs_dir: str = "logs"
    console_level: str = "INFO"
    file_level: str = "DEBUG"
    error_level: str = "ERROR"
    rotation: str = "00:00"
    retention: str = "30 days"
    compression: str = "zip"
    enqueue: bool = True
    backtrace: bool = True
    diagnose: bool = False
    encoding: str = "utf-8"
    json_format: bool = False
    
    # 默认颜色格式
    console_format: str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    # 文件日志格式 (无颜色)
    file_format: str = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} - {message}"
    )

    def __post_init__(self):
        self.logs_dir = str(Path(self.logs_dir).resolve())
        valid_levels = {lvl.value for lvl in LogLevel}
        for level_attr in ["console_level", "file_level", "error_level"]:
            val = getattr(self, level_attr)
            if val not in valid_levels:
                raise ValueError(f"Invalid {level_attr}: {val}")

class LoggerManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(LoggerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.config = LogConfig()
        self._module_handlers: Dict[str, int] = {}
        self._setup_basic_logging()
        self._initialized = True

    def _setup_basic_logging(self):
        """初始化基础日志配置（控制台、主文件、错误文件）"""
        logger.remove()  # 移除默认处理器
        
        # 1. 控制台输出
        logger.add(
            sys.stdout,
            level=self.config.console_level,
            format=self.config.console_format,
            colorize=True,
            enqueue=self.config.enqueue,
            backtrace=self.config.backtrace,
            diagnose=False,
        )

        if not self.config.logs_dir:
            return

        logs_path = Path(self.config.logs_dir)
        logs_path.mkdir(parents=True, exist_ok=True)

        # 根据是否 JSON 格式选择 formatter
        formatter = self._json_formatter if self.config.json_format else self.config.file_format

        # 公共的文件 logger 参数
        common_file_kwargs = {
            "rotation": self.config.rotation,
            "retention": self.config.retention,
            "compression": self.config.compression,
            "encoding": self.config.encoding,
            "enqueue": self.config.enqueue,
            "backtrace": self.config.backtrace,
            "diagnose": False,
            "delay": True,
        }

        # 2. 全局主日志文件 (app.log) - 按天轮转
        logger.add(
            logs_path / "app.log",
            level=self.config.file_level,
            format=formatter,
            **common_file_kwargs
        )

        # 3. 独立错误日志文件 (error.log)
        #    不在 Windows 下做 rotation：error.log 与 app.log 同处 logs/ 目录，
        #    多 handler 同时持有句柄会导致 os.rename 失败 (WinError 32)。
        #    error 日志量级小，靠 retention 清理即可。
        logger.add(
            logs_path / "error.log",
            level=self.config.error_level,
            format=formatter,
            rotation=None,
            retention=self.config.retention,
            encoding=self.config.encoding,
            enqueue=self.config.enqueue,
            backtrace=True,
            diagnose=False,
            filter=lambda r: r["level"].no >= logger.level(self.config.error_level).no,
        )

    @staticmethod
    def _json_formatter(record: Dict[str, Any]) -> str:
        """结构化 JSON 格式化工具"""
        log_record = {
            "time": record["time"].isoformat(),
            "level": record["level"].name,
            "message": redact_secrets(str(record["message"])),
            "module": record["name"],
            "function": record["function"],
            "line": record["line"],
            "extra": redact_value(record["extra"]),
        }
        
        if record["exception"]:
            exc = record["exception"]
            log_record["exception"] = {
                "type": str(exc.type),
                "value": redact_secrets(str(exc.value)),
                "traceback": bool(exc.traceback)
            }
        
        try:
            serialize = lambda o: o.isoformat() if isinstance(o, (datetime.datetime, datetime.date)) else str(o)
            json_str = json.dumps(log_record, ensure_ascii=False, default=serialize)
        except Exception:
            return "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}\n"

        return json_str.replace("{", "{{").replace("}", "}}") + "\n"

    # --- 公共接口 ---

    def get_logger(self, name: Optional[str] = None, **kwargs):
        """获取 logger。若提供 name，则绑定 module 字段。"""
        if name:
            return logger.bind(module=name, **kwargs)
        return logger

    def add_module_logger(self, module_name: str, level: str = "INFO"):
        """为特定模块创建独立的日志文件，且该文件仅包含该模块的日志"""
        if module_name in self._module_handlers:
            return self._module_handlers[module_name]

        log_file = Path(self.config.logs_dir) / f"{module_name.lower()}.log"
        
        handler_id = logger.add(
            log_file,
            level=level,
            format=self._json_formatter if self.config.json_format else self.config.file_format,
            rotation=self.config.rotation,
            retention=self.config.retention,
            enqueue=self.config.enqueue,
            backtrace=self.config.backtrace,
            diagnose=False,
            delay=True,
            filter=lambda r: r["extra"].get("module") == module_name or r["name"] == module_name
        )
        self._module_handlers[module_name] = handler_id
        return handler_id

    def configure(self, **kwargs):
        """动态更新配置并重新生效"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self._setup_basic_logging()

    def set_global_level(self, level: str):
        """快捷设置全局日志级别"""
        self.configure(console_level=level, file_level=level)

    def intercept_exceptions(self):
        """全局未捕获异常拦截"""
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("Uncaught exception detected")
        
        sys.excepthook = handle_exception
        
        # 针对多线程异常的拦截 (Python 3.8+)
        if hasattr(threading, "excepthook"):
            def thread_exception_handler(args):
                logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).critical(
                    f"Uncaught thread exception in {args.thread.name}"
                )
            threading.excepthook = thread_exception_handler

    # --- 装饰器工具 ---

    @staticmethod
    def catch(message: str = "Unexpected error occurred"):
        """自动捕获异常并记录日志的装饰器"""
        return logger.catch(message=message, reraise=True)

    @staticmethod
    def trace(func):
        """追踪函数执行耗时的装饰器"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            logger.trace(f"Entering {func.__name__}")
            result = func(*args, **kwargs)
            duration = time.perf_counter() - start
            logger.trace(f"Exiting {func.__name__} (duration: {duration:.4f}s)")
            return result
        return wrapper

    def stats(self) -> Dict[str, Any]:
        """获取当前日志系统状态"""
        return {
            "handlers_count": len(logger._core.handlers),
            "module_handlers": list(self._module_handlers.keys()),
            "logs_dir": self.config.logs_dir,
            "levels": {
                "console": self.config.console_level,
                "file": self.config.file_level
            }
        }

# --- 单例实例导出 ---
try:
    logger.level("DEBUGGER")
except ValueError:
    logger.level("DEBUGGER", no=10, color="<blue>")

log_manager = LoggerManager()

class _PrintfAdapter:
    """Wrap a loguru logger so stdlib-style printf calls are formatted.

    Loguru does not auto-format ``%s/%d`` positional args (it only supports
    ``{}`` via ``str.format``). Calls like ``logger.info("hi %s", name)``
    would otherwise emit the literal ``hi %s``. This adapter performs the
    ``%``-formatting client-side when positional args are supplied, and
    forwards keyword-only / no-arg calls untouched.
    """

    __slots__ = ("_logger",)

    def __init__(self, loguru_logger):
        self._logger = loguru_logger

    def __getattr__(self, name):
        if name == "debugger":
            attr = None
            level = "DEBUGGER"
        else:
            attr = getattr(self._logger, name)
            level = "ERROR" if name == "exception" else name.upper()
        if name not in ("trace", "debugger", "debug", "info", "success", "warning", "error", "critical", "exception"):
            return attr
        def _log(message, *args, **kwargs):
            if args:
                try:
                    message = message % args
                except TypeError:
                    try:
                        message = message.format(*args)
                    except (IndexError, KeyError, TypeError, ValueError):
                        pass
            bound_logger = self._logger.opt(
                depth=1,
                exception=True if name == "exception" else None,
            )
            return bound_logger.log(level, message, **kwargs)
        return _log

    def bind(self, *args, **kwargs):
        return _PrintfAdapter(self._logger.bind(*args, **kwargs))

    def opt(self, *args, **kwargs):
        return _PrintfAdapter(self._logger.opt(*args, **kwargs))

    def patch(self, *args, **kwargs):
        return _PrintfAdapter(self._logger.patch(*args, **kwargs))


# 导出常用函数
get_logger_raw = log_manager.get_logger


def get_logger(name=None, **kwargs):
    """Backward-compatible logger; wraps loguru so printf-style calls work."""
    return _PrintfAdapter(get_logger_raw(name, **kwargs))


add_module_logger = log_manager.add_module_logger
configure_logging = log_manager.configure
set_global_level = log_manager.set_global_level
intercept_exceptions = log_manager.intercept_exceptions
get_logger_stats = log_manager.stats

# 导出装饰器
catch = log_manager.catch
trace = log_manager.trace

# 导出原生 logger 供直接使用
log = logger
