import functools
import time
import traceback
import warnings
from .log import logger

def delay(seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            time.sleep(seconds)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def run_safe_model(module_name):
    def inner_run_safe_model(func):
        try:

            @functools.wraps(func)  # 将函数的原来属性付给新函数
            def run_func(*args, **kw):
                callfunc = None
                try:
                    callfunc = func(*args, **kw)
                except Exception as e:
                    logger.error(module_name + ": " + func.__name__ + " - " + str(e))
                    traceback.print_exc()
                return callfunc

            return run_func
        except Exception as e:
            logger.error(module_name + ": " + func.__name__ + " - " + str(e))
            traceback.print_exc()
            return func

    return inner_run_safe_model


def timing(func):
    """计算函数运行时间的装饰器

    .. deprecated::
        Use `from utils.log import trace` instead.
    """
    warnings.warn(
        "utils.decorators.timing is deprecated. Use utils.log.trace instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # 记录开始时间
        start_time = time.perf_counter()  # 使用高精度计时器
        
        # 执行被装饰的函数
        result = func(*args, **kwargs)
        
        # 记录结束时间并计算耗时
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        
        # 打印耗时信息
        print(f"函数 {func.__name__} 运行耗时: {elapsed_time:.6f} 秒")
        
        return result
    
    return wrapper