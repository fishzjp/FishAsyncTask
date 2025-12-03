"""
任务状态管理模块

负责任务状态的更新、查询和清理。
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

from .types import TaskStatus, TaskStatusDict


class TaskStatusManager:
    """
    任务状态管理器
    
    负责任务状态的存储、更新和查询。
    所有操作都是线程安全的，使用status_lock保护共享状态。
    
    线程安全说明：
    - 所有对task_status字典的操作都在status_lock保护下进行
    - 支持并发查询和更新，不会出现数据竞争
    - 清理操作也在锁保护下执行，确保一致性
    """
    
    def __init__(
        self,
        logger: logging.Logger,
        status_lock: threading.Lock,
        task_status: Dict[str, TaskStatusDict],
        task_status_ttl: int,
        max_task_status_count: int,
    ):
        """
        初始化任务状态管理器
        
        Args:
            logger: 日志记录器
            status_lock: 状态锁
            task_status: 任务状态字典
            task_status_ttl: 任务状态TTL（秒）
            max_task_status_count: 最大任务状态数量
        """
        self.logger = logger
        self.status_lock = status_lock
        self.task_status = task_status
        self.task_status_ttl = task_status_ttl
        self.max_task_status_count = max_task_status_count
    
    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        result: Any = None,
        error: Optional[str] = None,
        submit_time: Optional[float] = None,
    ) -> None:
        """
        更新任务状态（线程安全）
        
        Args:
            task_id: 任务ID
            status: 任务状态（pending, running, completed, failed）
            start_time: 任务开始时间（可选）
            end_time: 任务结束时间（可选）
            result: 任务执行结果（可选）
            error: 错误信息（可选）
            submit_time: 任务提交时间（可选，仅用于pending状态）
            
        Note:
            此方法会保留已存在的 start_time，除非明确提供新的 start_time。
        """
        with self.status_lock:
            current_status = self.task_status.get(task_id, {})
            new_status: TaskStatusDict = {"status": status}
            
            # 保留或设置时间字段
            if submit_time is not None:
                new_status["submit_time"] = submit_time
            elif "submit_time" in current_status:
                new_status["submit_time"] = current_status["submit_time"]
            
            # start_time 处理逻辑：
            # 1. 如果提供了新的 start_time，使用新的
            # 2. 如果没有提供但已存在 start_time，保留旧的
            # 3. 如果提供了但为 None，不设置（保持原值或使用默认）
            if start_time is not None:
                new_status["start_time"] = start_time
            elif "start_time" in current_status:
                new_status["start_time"] = current_status["start_time"]
            
            if end_time is not None:
                new_status["end_time"] = end_time
            elif "end_time" in current_status:
                new_status["end_time"] = current_status["end_time"]
            
            if result is not None:
                new_status["result"] = result
            elif "result" in current_status:
                new_status["result"] = current_status["result"]
            
            if error is not None:
                new_status["error"] = error
            elif "error" in current_status:
                new_status["error"] = current_status["error"]
            
            self.task_status[task_id] = new_status
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatusDict]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[TaskStatusDict]: 任务状态字典，如果任务不存在则返回None
        """
        with self.status_lock:
            status = self.task_status.get(task_id)
            # 返回类型转换，确保类型一致性
            return status if status is not None else None
    
    def clear_task_status(self, task_id: Optional[str] = None) -> None:
        """
        清除指定任务状态或所有任务状态
        
        Args:
            task_id: 要清除的任务ID。如果为None，则清除所有任务状态。
        """
        with self.status_lock:
            if task_id:
                self.task_status.pop(task_id, None)
                self.logger.info(f"已清除任务状态: {task_id}")
            else:
                count = len(self.task_status)
                self.task_status.clear()
                self.logger.info(f"已清除所有任务状态记录（共 {count} 条）")
    
    def cleanup_old_task_status(self) -> int:
        """
        清理过期的任务状态
        
        清理策略：
        1. 清理已完成或失败且超过TTL的任务
        2. 如果任务状态数量超过限制，清理最旧的任务
        
        Returns:
            int: 清理的任务数量
        """
        now = self._get_current_time()
        cleaned_count = 0
        
        with self.status_lock:
            # 清理已完成或失败且超过TTL的任务
            cleaned_count += self._remove_expired_tasks(now)
            
            # 如果任务状态数量超过限制，清理最旧的任务
            cleaned_count += self._enforce_max_status_count()
        
        if cleaned_count > 0:
            self.logger.info(
                f"清理了 {cleaned_count} 个过期任务状态，"
                f"当前任务状态数: {len(self.task_status)}"
            )
        
        return cleaned_count
    
    def _get_current_time(self) -> float:
        """
        获取当前时间戳
        
        此方法独立出来是为了方便测试时mock时间。
        在生产环境中，直接返回 time.time()。
        
        Returns:
            float: 当前时间戳（Unix时间戳，秒）
        """
        return time.time()
    
    def _remove_expired_tasks(self, current_time: float) -> int:
        """
        移除过期的任务状态
        
        Args:
            current_time: 当前时间戳
            
        Returns:
            int: 清理的任务数量
        """
        expired_tasks = [
            task_id
            for task_id, status in self.task_status.items()
            if self._is_task_expired(status, current_time)
        ]
        
        for task_id in expired_tasks:
            self.task_status.pop(task_id, None)
        
        return len(expired_tasks)
    
    def _is_task_expired(self, status: TaskStatusDict, current_time: float) -> bool:
        """
        判断任务是否已过期
        
        Args:
            status: 任务状态字典
            current_time: 当前时间戳
            
        Returns:
            bool: 如果任务已过期返回True，否则返回False
        """
        if status.get("status") not in ("completed", "failed"):
            return False
        
        end_time = status.get("end_time")
        return end_time is not None and (current_time - end_time) > self.task_status_ttl
    
    def _enforce_max_status_count(self) -> int:
        """
        强制执行最大任务状态数量限制
        
        当任务状态数量超过限制时，按时间顺序清理最旧的任务。
        排序策略：
        1. 优先使用 submit_time（提交时间）
        2. 如果 submit_time 不存在，使用 start_time（开始时间）
        3. 如果两者都不存在，使用 0（最旧的任务）
        
        保留最新的 max_task_status_count 个任务，删除其余任务。
        
        Returns:
            int: 清理的任务数量
        """
        if len(self.task_status) <= self.max_task_status_count:
            return 0
        
        # 按时间排序，保留最新的任务
        # 排序键：优先使用 submit_time，其次使用 start_time，都不存在则使用 0
        sorted_tasks = sorted(
            self.task_status.items(),
            key=lambda x: x[1].get("submit_time", x[1].get("start_time", 0)),
            reverse=True,  # 降序排列，最新的在前
        )
        
        # 只保留最新的 max_task_status_count 个任务
        old_count = len(self.task_status)
        self.task_status = dict(sorted_tasks[:self.max_task_status_count])
        return old_count - self.max_task_status_count

