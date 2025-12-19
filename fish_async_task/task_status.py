"""
任务状态管理模块

负责任务状态的更新、查询和清理。
"""

import heapq
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .types import TaskStatus, TaskStatusDict


class ShardedTaskStatusWithExpiry:
    """
    分片任务状态存储（带过期时间管理）
    
    使用分片锁减少锁竞争，每个分片内部使用优先级队列管理过期时间。
    支持高并发查询和更新，以及高效的增量清理。
    
    线程安全说明：
    - 每个分片有独立的锁，不同分片的操作可以并发执行
    - 同一分片内的操作串行化，保证线程安全
    - 清理操作支持增量清理，避免长时间阻塞
    """
    
    def __init__(self, shard_count: int, ttl: int):
        """
        初始化分片状态存储
        
        Args:
            shard_count: 分片数量，建议为2的幂次（8, 16, 32, 64）
            ttl: 任务状态TTL（秒）
        """
        self.shard_count = shard_count
        self.ttl = ttl
        
        # 每个分片包含：状态字典、锁、过期时间堆
        self.shards: List[Dict[str, TaskStatusDict]] = [dict() for _ in range(shard_count)]
        self.locks: List[threading.Lock] = [threading.Lock() for _ in range(shard_count)]
        # 每个分片的过期时间堆：(expiry_time, task_id)
        self.expiry_heaps: List[List[Tuple[float, str]]] = [[] for _ in range(shard_count)]
    
    def _get_shard_index(self, task_id: str) -> int:
        """
        根据 task_id 计算分片索引
        
        Args:
            task_id: 任务ID
            
        Returns:
            int: 分片索引（0 到 shard_count-1）
        """
        # 使用稳定的哈希函数
        return hash(task_id) % self.shard_count
    
    def get_status(self, task_id: str) -> Optional[TaskStatusDict]:
        """
        获取任务状态（线程安全）
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[TaskStatusDict]: 任务状态字典，如果任务不存在则返回None
        """
        shard_idx = self._get_shard_index(task_id)
        with self.locks[shard_idx]:
            return self.shards[shard_idx].get(task_id)
    
    def update_status(
        self,
        task_id: str,
        status: TaskStatusDict,
        current_status: Optional[TaskStatusDict] = None,
    ) -> None:
        """
        更新任务状态（线程安全）
        
        Args:
            task_id: 任务ID
            status: 新的任务状态字典
            current_status: 当前状态（如果已知，避免重复查询）
        """
        shard_idx = self._get_shard_index(task_id)
        with self.locks[shard_idx]:
            # 更新状态字典
            self.shards[shard_idx][task_id] = status
            
            # 如果任务已完成或失败，添加到过期时间堆
            if status.get("status") in ("completed", "failed"):
                end_time = status.get("end_time")
                if end_time:
                    expiry_time = end_time + self.ttl
                    heapq.heappush(self.expiry_heaps[shard_idx], (expiry_time, task_id))
    
    def remove_status(self, task_id: str) -> None:
        """
        移除任务状态（线程安全）
        
        Args:
            task_id: 任务ID
        """
        shard_idx = self._get_shard_index(task_id)
        with self.locks[shard_idx]:
            self.shards[shard_idx].pop(task_id, None)
            # 注意：堆中的条目会在清理时自动处理，不需要立即移除
    
    def cleanup_expired(self, max_cleanup: Optional[int] = None) -> int:
        """
        清理过期任务（增量清理）
        
        遍历所有分片，清理过期任务。支持增量清理，避免长时间阻塞。
        
        Args:
            max_cleanup: 最大清理数量，None表示清理所有过期任务
            
        Returns:
            int: 清理的任务数量
        """
        now = time.time()
        cleaned_count = 0
        remaining_cleanup = max_cleanup
        
        # 遍历所有分片
        for shard_idx in range(self.shard_count):
            if remaining_cleanup is not None and remaining_cleanup <= 0:
                break
            
            with self.locks[shard_idx]:
                heap = self.expiry_heaps[shard_idx]
                shard_dict = self.shards[shard_idx]
                
                # 清理堆顶的过期任务
                while heap:
                    if remaining_cleanup is not None and remaining_cleanup <= 0:
                        break
                    
                    # 获取堆顶元素（while循环已确保堆非空）
                    expiry_time, task_id = heap[0]
                    
                    if expiry_time > now:
                        # 堆顶任务未过期，停止清理此分片
                        break
                    
                    # 移除堆顶
                    heapq.heappop(heap)
                    
                    # 从状态字典中移除（如果存在且确实过期）
                    if task_id in shard_dict:
                        status = shard_dict[task_id]
                        end_time = status.get("end_time")
                        if end_time and (now - end_time) > self.ttl:
                            shard_dict.pop(task_id, None)
                            cleaned_count += 1
                            if remaining_cleanup is not None:
                                remaining_cleanup -= 1
        
        return cleaned_count
    
    def _collect_all_tasks(self) -> List[Tuple[float, str, int, TaskStatusDict]]:
        """
        收集所有任务并按时间排序
        
        注意：调用此方法前必须已持有所有锁。
        
        Returns:
            List[Tuple[float, str, int, TaskStatusDict]]: 排序后的任务列表
                (sort_key, task_id, shard_idx, status)
        """
        all_tasks: List[Tuple[float, str, int, TaskStatusDict]] = []
        
        # 收集所有任务（此时已持有所有锁，数据一致）
        for shard_idx, shard_dict in enumerate(self.shards):
            for task_id, status in shard_dict.items():
                # 排序键：优先使用 submit_time，其次使用 start_time，都不存在则使用负无穷
                # 使用负无穷确保没有时间戳的任务排在最后
                sort_key = status.get("submit_time", status.get("start_time", float("-inf")))
                all_tasks.append((sort_key, task_id, shard_idx, status))
        
        # 按时间排序（降序，最新的在前）
        all_tasks.sort(key=lambda x: x[0], reverse=True)
        return all_tasks
    
    def _cleanup_old_tasks(
        self, all_tasks: List[Tuple[float, str, int, TaskStatusDict]], 
        tasks_to_keep: set, max_count: int
    ) -> int:
        """
        清理旧任务
        
        注意：调用此方法前必须已持有所有锁。
        
        Args:
            all_tasks: 所有任务列表
            tasks_to_keep: 需要保留的任务ID集合
            max_count: 最大任务数量
            
        Returns:
            int: 清理的任务数量
        """
        cleaned_count = 0
        # all_tasks[max_count:] 中的任务肯定不在 tasks_to_keep 中，无需判断
        for sort_key, task_id, shard_idx, status in all_tasks[max_count:]:
            self.shards[shard_idx].pop(task_id, None)
            cleaned_count += 1
        return cleaned_count
    
    def _rebuild_expiry_heaps(self, tasks_to_keep: set) -> None:
        """
        重建过期时间堆，只保留需要保留的任务
        
        注意：调用此方法前必须已持有所有锁。
        
        Args:
            tasks_to_keep: 需要保留的任务ID集合
        """
        for shard_idx in range(self.shard_count):
            self.expiry_heaps[shard_idx] = [
                (expiry, tid)
                for expiry, tid in self.expiry_heaps[shard_idx]
                if tid in tasks_to_keep
            ]
            heapq.heapify(self.expiry_heaps[shard_idx])
    
    def enforce_max_count(self, max_count: int) -> int:
        """
        强制执行最大任务数量限制
        
        当任务状态数量超过限制时，按时间顺序清理最旧的任务。
        需要获取所有锁，按顺序获取避免死锁。
        
        Args:
            max_count: 最大任务数量
            
        Returns:
            int: 清理的任务数量
        """
        # 按顺序获取所有锁（避免死锁）
        for lock in self.locks:
            lock.acquire()
        
        try:
            # 在持有所有锁的情况下统计总任务数，避免竞态条件
            total_count = sum(len(shard) for shard in self.shards)
            if total_count <= max_count:
                return 0
            
            # 收集所有任务并按时间排序
            all_tasks = self._collect_all_tasks()
            
            # 保留最新的 max_count 个任务
            tasks_to_keep = set()
            for _, task_id, _, _ in all_tasks[:max_count]:
                tasks_to_keep.add(task_id)
            
            # 清理旧任务
            cleaned_count = self._cleanup_old_tasks(all_tasks, tasks_to_keep, max_count)
            
            # 清理堆中对应的过期条目
            self._rebuild_expiry_heaps(tasks_to_keep)
            
            return cleaned_count
        finally:
            # 释放所有锁
            for lock in self.locks:
                lock.release()
    
    def get_all_statuses(self) -> Dict[str, TaskStatusDict]:
        """
        获取所有任务状态（需要获取所有锁）
        
        Returns:
            Dict[str, TaskStatusDict]: 所有任务状态字典
        """
        result = {}
        
        # 按顺序获取所有锁，避免死锁
        for lock in self.locks:
            lock.acquire()
        
        try:
            for shard in self.shards:
                result.update(shard)
        finally:
            # 释放所有锁
            for lock in self.locks:
                lock.release()
        
        return result
    
    def clear_all(self) -> None:
        """
        清空所有任务状态
        """
        # 按顺序获取所有锁
        for lock in self.locks:
            lock.acquire()
        
        try:
            for shard in self.shards:
                shard.clear()
            for heap in self.expiry_heaps:
                heap.clear()
        finally:
            # 释放所有锁
            for lock in self.locks:
                lock.release()
    
    def get_total_count(self) -> int:
        """
        获取总任务数量（不需要锁，仅用于统计）
        
        Returns:
            int: 总任务数量
        """
        return sum(len(shard) for shard in self.shards)


class TaskStatusManager:
    """
    任务状态管理器
    
    负责任务状态的存储、更新和查询。
    使用分片锁和优先级队列优化性能，支持高并发操作。
    
    线程安全说明：
    - 使用分片锁，不同分片的操作可以并发执行
    - 同一分片内的操作串行化，保证线程安全
    - 清理操作支持增量清理，避免长时间阻塞
    """
    
    # 配置常量
    DEFAULT_SHARD_COUNT = 16  # 默认分片数量
    DEFAULT_MAX_CLEANUP_PER_BATCH = 100  # 每次清理的最大任务数量
    
    def __init__(
        self,
        logger: logging.Logger,
        task_status_ttl: int,
        max_task_status_count: int,
        shard_count: Optional[int] = None,
    ):
        """
        初始化任务状态管理器
        
        Args:
            logger: 日志记录器
            task_status_ttl: 任务状态TTL（秒）
            max_task_status_count: 最大任务状态数量
            shard_count: 分片数量，默认从环境变量 TASK_STATUS_SHARD_COUNT 读取，或使用16
        """
        self.logger = logger
        self.task_status_ttl = task_status_ttl
        self.max_task_status_count = max_task_status_count
        
        # 从环境变量读取分片数量，默认16
        if shard_count is None:
            shard_count_env = os.getenv("TASK_STATUS_SHARD_COUNT")
            if shard_count_env:
                try:
                    shard_count = int(shard_count_env)
                    if shard_count < 1:
                        self.logger.warning(
                            f"无效的 TASK_STATUS_SHARD_COUNT: {shard_count}，使用默认值 {self.DEFAULT_SHARD_COUNT}"
                        )
                        shard_count = self.DEFAULT_SHARD_COUNT
                except ValueError:
                    self.logger.warning(
                        f"无效的 TASK_STATUS_SHARD_COUNT 格式: {shard_count_env}，使用默认值 {self.DEFAULT_SHARD_COUNT}"
                    )
                    shard_count = self.DEFAULT_SHARD_COUNT
            else:
                shard_count = self.DEFAULT_SHARD_COUNT
        
        # 使用分片存储
        self.sharded_status = ShardedTaskStatusWithExpiry(shard_count, task_status_ttl)
    
    def _merge_task_status(
        self,
        current_status: TaskStatusDict,
        status: TaskStatus,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        result: Any = None,
        error: Optional[str] = None,
        submit_time: Optional[float] = None,
    ) -> TaskStatusDict:
        """
        合并任务状态字段
        
        Args:
            current_status: 当前任务状态
            status: 新的任务状态
            start_time: 任务开始时间（可选）
            end_time: 任务结束时间（可选）
            result: 任务执行结果（可选）
            error: 错误信息（可选）
            submit_time: 任务提交时间（可选）
            
        Returns:
            TaskStatusDict: 合并后的任务状态字典
        """
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
        
        return new_status
    
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
        # 获取当前状态（如果存在）
        current_status = self.sharded_status.get_status(task_id) or {}
        
        # 合并任务状态
        new_status = self._merge_task_status(
            current_status, status, start_time, end_time, result, error, submit_time
        )
        
        # 更新分片存储
        self.sharded_status.update_status(task_id, new_status, current_status)
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatusDict]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[TaskStatusDict]: 任务状态字典，如果任务不存在则返回None
        """
        return self.sharded_status.get_status(task_id)
    
    def clear_task_status(self, task_id: Optional[str] = None) -> None:
        """
        清除指定任务状态或所有任务状态
        
        Args:
            task_id: 要清除的任务ID。如果为None，则清除所有任务状态。
        """
        if task_id:
            self.sharded_status.remove_status(task_id)
            self.logger.info(f"已清除任务状态: {task_id}")
        else:
            count = self.sharded_status.get_total_count()
            self.sharded_status.clear_all()
            self.logger.info(f"已清除所有任务状态记录（共 {count} 条）")
    
    def cleanup_old_task_status(self) -> int:
        """
        清理过期的任务状态（增量清理）
        
        清理策略：
        1. 清理已完成或失败且超过TTL的任务（增量清理，每次最多100个）
        2. 如果任务状态数量超过限制，清理最旧的任务
        
        Returns:
            int: 清理的任务数量
        """
        cleaned_count = 0
        
        # 增量清理过期任务（每次最多清理100个，避免长时间阻塞）
        cleaned_count += self.sharded_status.cleanup_expired(
            max_cleanup=self.DEFAULT_MAX_CLEANUP_PER_BATCH
        )
        
        # 强制执行最大数量限制
        cleaned_count += self.sharded_status.enforce_max_count(self.max_task_status_count)
        
        if cleaned_count > 0:
            current_count = self.sharded_status.get_total_count()
            self.logger.info(
                f"清理了 {cleaned_count} 个过期任务状态，"
                f"当前任务状态数: {current_count}"
            )
        
        return cleaned_count
    

