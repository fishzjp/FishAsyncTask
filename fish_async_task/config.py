"""
配置管理模块

负责加载和验证任务管理器的配置项。

本模块提供了从环境变量加载配置的功能，支持以下配置项：
- TASK_STATUS_TTL: 任务状态TTL（秒），默认3600
- MAX_TASK_STATUS_COUNT: 最大任务状态数量，默认10000
- TASK_CLEANUP_INTERVAL: 清理间隔（秒），默认300
- TASK_TIMEOUT: 任务超时时间（秒），默认无限制
- ADAPTIVE_WORKER_ENABLED: 是否启用自适应线程管理，默认True
- WORKER_CPU_THRESHOLD: CPU使用率阈值，默认0.8
- WORKER_QUEUE_THRESHOLD_HIGH: 扩容队列积压阈值，默认100
- WORKER_QUEUE_THRESHOLD_LOW: 缩容队列空闲阈值，默认10
- WORKER_SCALE_UP_COOLDOWN: 扩容冷却期（秒），默认5.0
- WORKER_SCALE_DOWN_COOLDOWN: 缩容冷却期（秒），默认30.0

性能优化配置项：
- SHARD_COUNT: 分片数量，默认16（建议为2的幂次）
- BATCH_UPDATE_BUFFER_SIZE: 批量更新缓冲区大小，默认100
- BATCH_UPDATE_INTERVAL: 批量更新刷新间隔（秒），默认0.1
- ENABLE_AUTO_CLEANUP: 是否启用自动清理，默认True
- ENABLE_BATCH_UPDATES: 是否启用批量更新，默认False
- ENABLE_ADAPTIVE_SCALING: 是否启用自适应扩展，默认False

所有配置项都会进行验证，无效值会被拒绝并使用默认值。
"""

import logging
import os
import threading
import time
from typing import Any, Callable, Optional


class ConfigLoader:
    """配置加载器"""

    # 配置最大值限制
    MAX_TTL = 86400  # 最大TTL：1天
    MAX_TASK_STATUS_COUNT = 1000000  # 最大任务状态数：100万
    MAX_CLEANUP_INTERVAL = 3600  # 最大清理间隔：1小时
    MAX_TASK_TIMEOUT = 86400  # 最大任务超时：1天
    MAX_CPU_THRESHOLD = 1.0  # 最大CPU阈值：100%
    MAX_QUEUE_THRESHOLD = 10000  # 最大队列阈值：1万
    MAX_COOLDOWN = 3600  # 最大冷却期：1小时

    # 默认自适应配置
    DEFAULT_ADAPTIVE_WORKER_ENABLED = True
    DEFAULT_CPU_THRESHOLD = 0.8
    DEFAULT_QUEUE_THRESHOLD_HIGH = 100
    DEFAULT_QUEUE_THRESHOLD_LOW = 10
    DEFAULT_SCALE_UP_COOLDOWN = 5.0
    DEFAULT_SCALE_DOWN_COOLDOWN = 30.0

    # 性能优化配置默认值
    DEFAULT_SHARD_COUNT = 16  # 默认分片数量
    DEFAULT_BATCH_UPDATE_BUFFER_SIZE = 100  # 默认批量更新缓冲区大小
    DEFAULT_BATCH_UPDATE_INTERVAL = 0.1  # 默认批量更新刷新间隔（秒）
    DEFAULT_ENABLE_AUTO_CLEANUP = True  # 默认启用自动清理
    DEFAULT_ENABLE_BATCH_UPDATES = False  # 默认禁用批量更新
    DEFAULT_ENABLE_ADAPTIVE_SCALING = False  # 默认禁用自适应扩展

    # 性能优化配置最大值
    MAX_SHARD_COUNT = 1024  # 最大分片数量
    MAX_BATCH_UPDATE_BUFFER_SIZE = 10000  # 最大批量更新缓冲区大小
    MAX_BATCH_UPDATE_INTERVAL = 60.0  # 最大批量更新刷新间隔（秒）

    def __init__(self, logger: logging.Logger):
        """
        初始化配置加载器

        Args:
            logger: 日志记录器
        """
        self.logger = logger

    def load_int_config(
        self,
        env_key: str,
        default_value: int,
        config_name: str,
        min_value: int = 1,
        max_value: Optional[int] = None,
    ) -> int:
        """
        加载并验证整数配置项

        Args:
            env_key: 环境变量键名
            default_value: 默认值
            config_name: 配置项名称（用于日志）
            min_value: 最小值（默认为1）
            max_value: 最大值（可选）

        Returns:
            int: 验证后的配置值

        Note:
            如果环境变量不存在、不是有效整数或值超出允许范围，
            将使用默认值并记录警告日志。
        """
        env_value = os.getenv(env_key)
        if env_value is None:
            return default_value

        try:
            value = int(env_value)
            if value < min_value:
                self.logger.warning(
                    f"无效的 {config_name}: {value}（必须大于等于{min_value}），"
                    f"使用默认值 {default_value}"
                )
                return default_value

            # 如果指定了最大值，检查是否超出范围
            if max_value is not None and value > max_value:
                self.logger.warning(
                    f"无效的 {config_name}: {value}（不能超过{max_value}），"
                    f"使用最大值 {max_value}"
                )
                return max_value

            return value
        except ValueError:
            self.logger.warning(
                f"无效的 {config_name} 格式: {env_value}（必须是整数），"
                f"使用默认值 {default_value}"
            )
            return default_value

    def load_timeout_config(self, default_value: Optional[float]) -> Optional[float]:
        """
        加载并验证任务超时配置

        Args:
            default_value: 默认超时值

        Returns:
            Optional[float]: 任务超时时间（秒），如果为None则表示无超时限制
        """
        task_timeout = os.getenv("TASK_TIMEOUT")
        if not task_timeout:
            return default_value

        try:
            timeout_value = float(task_timeout)
            if timeout_value <= 0:
                self.logger.warning(f"无效的 TASK_TIMEOUT: {timeout_value}，禁用超时")
                return None

            # 检查是否超过最大值
            if timeout_value > self.MAX_TASK_TIMEOUT:
                self.logger.warning(
                    f"无效的 TASK_TIMEOUT: {timeout_value}（不能超过{self.MAX_TASK_TIMEOUT}），"
                    f"使用最大值 {self.MAX_TASK_TIMEOUT}"
                )
                return float(self.MAX_TASK_TIMEOUT)

            return timeout_value
        except ValueError:
            self.logger.warning(f"无效的 TASK_TIMEOUT 格式: {task_timeout}，禁用超时")
            return None

    def load_adaptive_worker_config(self) -> dict:
        """
        加载自适应线程管理配置

        Returns:
            dict: 自适应配置字典，包含以下键：
                - adaptive_worker_enabled: 是否启用自适应线程管理
                - cpu_threshold: CPU使用率阈值
                - queue_threshold_high: 扩容队列积压阈值
                - queue_threshold_low: 缩容队列空闲阈值
                - scale_up_cooldown: 扩容冷却期
                - scale_down_cooldown: 缩容冷却期
        """
        # 加载布尔配置（使用改进的解析方法）
        adaptive_worker_enabled = self._load_bool_config(
            "ADAPTIVE_WORKER_ENABLED", self.DEFAULT_ADAPTIVE_WORKER_ENABLED
        )

        # 加载浮点配置
        cpu_threshold = self._load_float_config(
            "WORKER_CPU_THRESHOLD",
            self.DEFAULT_CPU_THRESHOLD,
            "CPU_THRESHOLD",
            0.0,
            self.MAX_CPU_THRESHOLD,
        )

        queue_threshold_high = self.load_int_config(
            "WORKER_QUEUE_THRESHOLD_HIGH",
            self.DEFAULT_QUEUE_THRESHOLD_HIGH,
            "QUEUE_THRESHOLD_HIGH",
            1,
            self.MAX_QUEUE_THRESHOLD,
        )

        queue_threshold_low = self.load_int_config(
            "WORKER_QUEUE_THRESHOLD_LOW",
            self.DEFAULT_QUEUE_THRESHOLD_LOW,
            "QUEUE_THRESHOLD_LOW",
            0,
            self.MAX_QUEUE_THRESHOLD,
        )

        scale_up_cooldown = self._load_float_config(
            "WORKER_SCALE_UP_COOLDOWN",
            self.DEFAULT_SCALE_UP_COOLDOWN,
            "SCALE_UP_COOLDOWN",
            0.0,
            self.MAX_COOLDOWN,
        )

        scale_down_cooldown = self._load_float_config(
            "WORKER_SCALE_DOWN_COOLDOWN",
            self.DEFAULT_SCALE_DOWN_COOLDOWN,
            "SCALE_DOWN_COOLDOWN",
            0.0,
            self.MAX_COOLDOWN,
        )

        return {
            "adaptive_worker_enabled": adaptive_worker_enabled,
            "cpu_threshold": cpu_threshold,
            "queue_threshold_high": queue_threshold_high,
            "queue_threshold_low": queue_threshold_low,
            "scale_up_cooldown": scale_up_cooldown,
            "scale_down_cooldown": scale_down_cooldown,
        }

    def _load_float_config(
        self,
        env_key: str,
        default_value: float,
        config_name: str,
        min_value: float = 0.0,
        max_value: Optional[float] = None,
    ) -> float:
        """
        加载并验证浮点配置项

        Args:
            env_key: 环境变量键名
            default_value: 默认值
            config_name: 配置项名称（用于日志）
            min_value: 最小值
            max_value: 最大值（可选）

        Returns:
            float: 验证后的配置值
        """
        env_value = os.getenv(env_key)
        if env_value is None:
            return default_value

        try:
            value = float(env_value)
            if value < min_value:
                self.logger.warning(
                    f"无效的 {config_name}: {value}（必须大于等于{min_value}），"
                    f"使用默认值 {default_value}"
                )
                return default_value

            if max_value is not None and value > max_value:
                self.logger.warning(
                    f"无效的 {config_name}: {value}（不能超过{max_value}），"
                    f"使用最大值 {max_value}"
                )
                return max_value

            return value
        except ValueError:
            self.logger.warning(
                f"无效的 {config_name} 格式: {env_value}（必须是浮点数），"
                f"使用默认值 {default_value}"
            )
            return default_value

    def _load_bool_config(self, env_key: str, default: bool) -> bool:
        """
        加载布尔配置，提供宽容的解析

        Args:
            env_key: 环境变量键名
            default: 默认值

        Returns:
            bool: 解析后的布尔值

        Note:
            支持的真值：true, 1, yes, on, enabled（不区分大小写）
            支持的假值：false, 0, no, off, disabled（不区分大小写）
        """
        env_value = os.getenv(env_key)
        if env_value is None:
            return default

        normalized = env_value.strip().lower()
        if normalized in ("true", "1", "yes", "on", "enabled"):
            return True
        elif normalized in ("false", "0", "no", "off", "disabled"):
            return False
        else:
            self.logger.warning(f"无效的 {env_key}: {env_value}，使用默认值 {default}")
            return default

    def load_performance_config(self) -> dict:
        """
        加载性能优化配置

        Returns:
            dict: 性能优化配置字典，包含以下键：
                - shard_count: 分片数量
                - batch_update_buffer_size: 批量更新缓冲区大小
                - batch_update_interval: 批量更新刷新间隔（秒）
                - enable_auto_cleanup: 是否启用自动清理
                - enable_batch_updates: 是否启用批量更新
                - enable_adaptive_scaling: 是否启用自适应扩展
        """
        # 加载分片数量配置
        shard_count = self.load_int_config(
            "SHARD_COUNT",
            self.DEFAULT_SHARD_COUNT,
            "SHARD_COUNT",
            1,  # 最小值
            self.MAX_SHARD_COUNT,  # 最大值
        )

        # 加载批量更新缓冲区大小
        batch_update_buffer_size = self.load_int_config(
            "BATCH_UPDATE_BUFFER_SIZE",
            self.DEFAULT_BATCH_UPDATE_BUFFER_SIZE,
            "BATCH_UPDATE_BUFFER_SIZE",
            1,
            self.MAX_BATCH_UPDATE_BUFFER_SIZE,
        )

        # 加载批量更新刷新间隔
        batch_update_interval = self._load_float_config(
            "BATCH_UPDATE_INTERVAL",
            self.DEFAULT_BATCH_UPDATE_INTERVAL,
            "BATCH_UPDATE_INTERVAL",
            0.01,  # 最小值 10ms
            self.MAX_BATCH_UPDATE_INTERVAL,
        )

        # 加载布尔配置（使用改进的解析方法）
        enable_auto_cleanup = self._load_bool_config(
            "ENABLE_AUTO_CLEANUP", self.DEFAULT_ENABLE_AUTO_CLEANUP
        )
        enable_batch_updates = self._load_bool_config(
            "ENABLE_BATCH_UPDATES", self.DEFAULT_ENABLE_BATCH_UPDATES
        )
        enable_adaptive_scaling = self._load_bool_config(
            "ENABLE_ADAPTIVE_SCALING", self.DEFAULT_ENABLE_ADAPTIVE_SCALING
        )

        return {
            "shard_count": shard_count,
            "batch_update_buffer_size": batch_update_buffer_size,
            "batch_update_interval": batch_update_interval,
            "enable_auto_cleanup": enable_auto_cleanup,
            "enable_batch_updates": enable_batch_updates,
            "enable_adaptive_scaling": enable_adaptive_scaling,
        }


class HotReloadConfig:
    """支持热重载的配置管理器"""

    def __init__(
        self,
        logger: logging.Logger = None,
        reload_interval: int = 60,
    ):
        """
        初始化热重载配置管理器

        Args:
            logger: 日志记录器
            reload_interval: 重载间隔（秒）
        """
        self.logger = logger or logging.getLogger(__name__)
        self._reload_interval = reload_interval
        self._last_reload = 0.0
        self._config_cache: dict = {}
        self._config_parsers: dict = {}
        self._lock = threading.Lock()

    def register_config(
        self,
        key: str,
        parser: callable,
        default: Any = None,
    ) -> None:
        """
        注册配置项

        Args:
            key: 配置键名
            parser: 配置解析函数
            default: 默认值
        """
        with self._lock:
            self._config_parsers[key] = {
                "parser": parser,
                "default": default,
            }

    def get(self, key: str, use_cache: bool = True) -> Any:
        """
        获取配置值（支持热重载）

        Args:
            key: 配置键名
            use_cache: 是否使用缓存

        Returns:
            Any: 配置值
        """
        current_time = time.time()

        with self._lock:
            if key not in self._config_parsers:
                return None

            if (
                use_cache
                and key in self._config_cache
                and current_time - self._last_reload < self._reload_interval
            ):
                return self._config_cache[key]

            try:
                parser_info = self._config_parsers[key]
                value = parser_info["parser"]()

                if value is None:
                    value = parser_info["default"]

                self._config_cache[key] = value
                return value

            except Exception as e:
                self.logger.warning(f"配置加载失败 [{key}]: {e}")
                return self._config_parsers[key].get("default")

    def reload(self) -> int:
        """
        手动触发配置重载

        Returns:
            int: 重载的配置数量
        """
        with self._lock:
            reloaded = 0

            for key, parser_info in self._config_parsers.items():
                try:
                    value = parser_info["parser"]()
                    if value is None:
                        value = parser_info["default"]
                    self._config_cache[key] = value
                    reloaded += 1

                except Exception as e:
                    self.logger.warning(f"配置重载失败 [{key}]: {e}")

            self._last_reload = time.time()
            return reloaded

    def get_all(self) -> dict:
        """
        获取所有配置

        Returns:
            dict: 所有配置项
        """
        with self._lock:
            return dict(self._config_cache)

    def clear_cache(self) -> None:
        """清除配置缓存"""
        with self._lock:
            self._config_cache.clear()
            self._last_reload = 0.0


def validate_config(
    min_value: Any = None,
    max_value: Any = None,
    default: Any = None,
    allowed_values: list = None,
):
    """
    配置验证装饰器

    Args:
        min_value: 最小值
        max_value: 最大值
        default: 默认值
        allowed_values: 允许的值列表

    Returns:
        装饰器函数
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            value = func(*args, **kwargs)

            if value is None:
                return default

            if allowed_values is not None and value not in allowed_values:
                return default

            if min_value is not None and value < min_value:
                return default

            if max_value is not None and value > max_value:
                return default

            return value

        return wrapper

    return decorator
