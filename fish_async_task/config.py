"""
配置管理模块

负责加载和验证任务管理器的配置项。

本模块提供了从环境变量加载配置的功能，支持以下配置项：
- TASK_STATUS_TTL: 任务状态TTL（秒），默认3600
- MAX_TASK_STATUS_COUNT: 最大任务状态数量，默认10000
- TASK_CLEANUP_INTERVAL: 清理间隔（秒），默认300
- TASK_TIMEOUT: 任务超时时间（秒），默认无限制

所有配置项都会进行验证，无效值会被拒绝并使用默认值。
"""

import os
import logging
from typing import Optional


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, logger: logging.Logger):
        """
        初始化配置加载器
        
        Args:
            logger: 日志记录器
        """
        self.logger = logger
    
    def load_int_config(
        self, env_key: str, default_value: int, config_name: str
    ) -> int:
        """
        加载并验证整数配置项
        
        Args:
            env_key: 环境变量键名
            default_value: 默认值
            config_name: 配置项名称（用于日志）
            
        Returns:
            int: 验证后的配置值
            
        Note:
            如果环境变量不存在、不是有效整数或值小于等于0，
            将使用默认值并记录警告日志。
        """
        env_value = os.getenv(env_key)
        if env_value is None:
            return default_value
        
        try:
            value = int(env_value)
            if value <= 0:
                self.logger.warning(
                    f"无效的 {config_name}: {value}（必须大于0），使用默认值 {default_value}"
                )
                return default_value
            return value
        except ValueError:
            self.logger.warning(
                f"无效的 {config_name} 格式: {env_value}（必须是整数），使用默认值 {default_value}"
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
            return timeout_value
        except ValueError:
            self.logger.warning(f"无效的 TASK_TIMEOUT 格式: {task_timeout}，禁用超时")
            return None

