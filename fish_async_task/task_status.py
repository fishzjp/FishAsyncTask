"""
任务状态管理模块

负责任务状态的更新、查询和清理。
"""

import heapq
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple

from .types import TaskStatus, TaskStatusDict


class ReadWriteLock:
    """
    读写锁实现

    允许多个读操作并发执行，写操作独占访问。
    基于 threading.Condition 实现，支持上下文管理器。

    使用场景：
    - 读多写少的场景，读操作可以并发执行
    - 写操作需要独占访问，与所有读操作互斥

    示例：
        lock = ReadWriteLock()

        # 读操作
        with ReadWriteLockContext(lock, write=False):
            # 多个线程可以同时进入这里
            data = self._data

        # 写操作
        with ReadWriteLockContext(lock, write=True):
            # 同一时间只有一个线程可以进入这里
            self._data = new_data
    """

    def __init__(self):
        """初始化读写锁"""
        self._read_ready = threading.Condition(threading.RLock())
        self._readers = 0

    def acquire_read(self) -> None:
        """
        获取读锁

        多个线程可以同时获取读锁。
        """
        with self._read_ready:
            self._readers += 1

    def release_read(self) -> None:
        """
        释放读锁

        当所有读锁都被释放后，唤醒等待的写操作。
        """
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()

    def acquire_write(self) -> None:
        """
        获取写锁

        写锁是独占的，会等待所有读操作完成后才能获取。
        """
        self._read_ready.acquire()
        while self._readers > 0:
            self._read_ready.wait()

    def release_write(self) -> None:
        """
        释放写锁

        释放后，其他读操作或写操作可以继续执行。
        """
        self._read_ready.release()


class ReadWriteLockContext:
    """
    读写锁上下文管理器

    提供便捷的锁获取和释放方式。
    """

    def __init__(self, lock: ReadWriteLock, write: bool = False):
        """
        初始化上下文管理器

        Args:
            lock: 读写锁实例
            write: 是否为写操作（True=写锁，False=读锁）
        """
        self._lock = lock
        self._write = write

    def __enter__(self) -> "ReadWriteLockContext":
        """
        获取锁并返回上下文管理器实例

        根据 write 参数决定获取读锁或写锁。
        读锁允许并发获取，写锁独占访问。

        Returns:
            ReadWriteLockContext: 返回自身实例，用于 with 语句块
        """
        if self._write:
            self._lock.acquire_write()
        else:
            self._lock.acquire_read()
        return self

    def __exit__(self, *args) -> None:
        """
        释放锁

        释放之前获取的读锁或写锁。
        释放后，其他读操作或写操作可以继续执行。

        Args:
            *args: 接收异常信息参数（如果 with 语句中发生异常）
        """
        if self._write:
            self._lock.release_write()
        else:
            self._lock.release_read()


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

        # 每个分片包含：状态字典、读写锁、过期时间堆
        self.shards: List[Dict[str, TaskStatusDict]] = [dict() for _ in range(shard_count)]
        self.rw_locks: List[ReadWriteLock] = [ReadWriteLock() for _ in range(shard_count)]
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
        with ReadWriteLockContext(self.rw_locks[shard_idx], write=False):
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
        with ReadWriteLockContext(self.rw_locks[shard_idx], write=True):
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
        with ReadWriteLockContext(self.rw_locks[shard_idx], write=True):
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

            with ReadWriteLockContext(self.rw_locks[shard_idx], write=True):
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
                submit_time: Optional[float] = status.get("submit_time")
                start_time: Optional[float] = status.get("start_time")
                sort_key = (
                    submit_time
                    if submit_time is not None
                    else (start_time if start_time is not None else float("-inf"))
                )
                all_tasks.append((sort_key, task_id, shard_idx, status))

        # 按时间排序（降序，最新的在前）
        all_tasks.sort(key=lambda x: x[0], reverse=True)
        return all_tasks

    def _cleanup_old_tasks(
        self,
        all_tasks: List[Tuple[float, str, int, TaskStatusDict]],
        tasks_to_keep: set,
        max_count: int,
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
        acquired_locks: List[ReadWriteLock] = []

        try:
            # 按顺序获取所有写锁（避免死锁）
            for rw_lock in self.rw_locks:
                rw_lock.acquire_write()
                acquired_locks.append(rw_lock)

            # 在持有所有锁的情况下统计总任务数，避免竞态条件
            total_count = sum(len(shard) for shard in self.shards)
            if total_count <= max_count:
                return 0

            # 收集所有任务并按时间排序
            all_tasks = self._collect_all_tasks()

            # 保留最新的 max_count 个任务
            tasks_to_keep: set = set()
            for _, task_id, _, _ in all_tasks[:max_count]:
                tasks_to_keep.add(task_id)

            # 清理旧任务
            cleaned_count = self._cleanup_old_tasks(all_tasks, tasks_to_keep, max_count)

            # 清理堆中对应的过期条目
            self._rebuild_expiry_heaps(tasks_to_keep)

            return cleaned_count
        except Exception:
            # 确保即使发生异常也能释放已获取的锁
            raise
        finally:
            # 逆序释放所有已获取的锁（与获取顺序相反）
            for rw_lock in reversed(acquired_locks):
                try:
                    rw_lock.release_write()
                except RuntimeError as e:
                    # RuntimeError: 释放未持有的锁或重复释放
                    # 记录警告但不中断其他锁的释放
                    logging.getLogger(__name__).warning(
                        f"释放锁时遇到 RuntimeError: {e}，可能锁状态不一致"
                    )
                except Exception as e:
                    # 其他未预期的异常，记录错误
                    logging.getLogger(__name__).error(
                        f"释放锁时遇到未预期异常 [{type(e).__name__}]: {e}", exc_info=True
                    )

    def get_all_statuses(self) -> Dict[str, TaskStatusDict]:
        """
        获取所有任务状态（需要获取所有锁）

        Returns:
            Dict[str, TaskStatusDict]: 所有任务状态字典
        """
        result: Dict[str, TaskStatusDict] = {}
        acquired_locks: List[ReadWriteLock] = []

        try:
            # 按顺序获取所有读锁，避免死锁
            for rw_lock in self.rw_locks:
                rw_lock.acquire_read()
                acquired_locks.append(rw_lock)

            for shard in self.shards:
                result.update(shard)
        finally:
            # 逆序释放所有已获取的锁
            for rw_lock in reversed(acquired_locks):
                try:
                    rw_lock.release_read()
                except RuntimeError as e:
                    logging.getLogger(__name__).warning(f"释放读锁时遇到 RuntimeError: {e}")
                except Exception as e:
                    logging.getLogger(__name__).error(
                        f"释放读锁时遇到未预期异常 [{type(e).__name__}]: {e}", exc_info=True
                    )

        return result

    def clear_all(self) -> None:
        """
        清空所有任务状态
        """
        acquired_locks: List[ReadWriteLock] = []

        try:
            # 按顺序获取所有写锁
            for rw_lock in self.rw_locks:
                rw_lock.acquire_write()
                acquired_locks.append(rw_lock)

            for shard in self.shards:
                shard.clear()
            for heap in self.expiry_heaps:
                heap.clear()
        finally:
            # 逆序释放所有已获取的写锁
            for rw_lock in reversed(acquired_locks):
                try:
                    rw_lock.release_write()
                except RuntimeError as e:
                    logging.getLogger(__name__).warning(f"释放写锁时遇到 RuntimeError: {e}")
                except Exception as e:
                    logging.getLogger(__name__).error(
                        f"释放写锁时遇到未预期异常 [{type(e).__name__}]: {e}", exc_info=True
                    )

    def get_total_count(self) -> int:
        """
        获取总任务数量（不需要锁，仅用于统计）

        Returns:
            int: 总任务数量
        """
        return sum(len(shard) for shard in self.shards)

    def resize_shards(self, new_shard_count: int) -> bool:
        """
        动态调整分片数量

        此方法会重新分配所有任务状态到新的分片结构中。
        由于需要重建所有数据结构，这可能是一个耗时操作，
        建议在低负载时执行或在外部异步执行。

        Args:
            new_shard_count: 新的分片数量，必须为正整数

        Returns:
            bool: 如果调整成功返回True，否则返回False

        Warning:
            此操作会短暂阻塞所有状态更新和查询操作。
            建议在系统初始化时设置合适的分片数量，
            并尽量避免在生产环境中频繁调整。
        """
        if new_shard_count < 1:
            return False

        # 如果分片数量相同，无需调整
        if new_shard_count == self.shard_count:
            return True

        # 收集所有当前任务状态
        all_tasks: Dict[str, TaskStatusDict] = {}
        acquired_locks: List[ReadWriteLock] = []

        try:
            # 获取所有写锁
            for rw_lock in self.rw_locks:
                rw_lock.acquire_write()
                acquired_locks.append(rw_lock)

            # 收集所有任务
            for shard in self.shards:
                all_tasks.update(shard)

        finally:
            # 释放所有写锁
            for rw_lock in reversed(acquired_locks):
                try:
                    rw_lock.release_write()
                except Exception:
                    pass

        # 创建新的分片结构
        new_shards: List[Dict[str, TaskStatusDict]] = [dict() for _ in range(new_shard_count)]
        new_rwlocks: List[ReadWriteLock] = [ReadWriteLock() for _ in range(new_shard_count)]
        new_expiry_heaps: List[List[Tuple[float, str]]] = [[] for _ in range(new_shard_count)]

        # 重新分配任务到新的分片
        for task_id, status in all_tasks.items():
            new_shard_idx = hash(task_id) % new_shard_count
            new_shards[new_shard_idx][task_id] = status

            # 重新计算过期时间堆
            if status.get("status") in ("completed", "failed"):
                end_time = status.get("end_time")
                if end_time:
                    expiry_time = end_time + self.ttl
                    heapq.heappush(new_expiry_heaps[new_shard_idx], (expiry_time, task_id))

        # 原子性地替换旧的分片结构
        with self._resizing_lock:
            self.shards = new_shards
            self.rw_locks = new_rwlocks
            self.expiry_heaps = new_expiry_heaps
            self.shard_count = new_shard_count

        return True

    # 添加重配置锁（用于resize操作）
    _resizing_lock = threading.Lock()


class BatchedStatusUpdater:
    """
    批量状态更新器

    收集多个状态更新，批量提交到分片存储，减少锁获取次数，提升写入性能。
    支持按批量大小和刷新间隔触发批量提交。

    使用场景：
    - 高并发写入场景，减少状态更新的锁竞争
    - 需要批量处理大量状态更新的场景

    示例：
        def update_func(task_id, status, **kwargs):
            # 实际的更新逻辑
            pass

        updater = BatchedStatusUpdater(
            update_func=update_func,
            batch_size=100,
            flush_interval=0.1
        )

        # 添加更新到批量队列
        updater.update("task_1", "running")
        updater.update("task_2", "completed", result="result")

        # shutdown时自动刷新所有待处理的更新
        updater.shutdown()
    """

    def __init__(
        self,
        update_func: "Callable[..., None]",
        batch_size: int = 100,
        flush_interval: float = 0.1,
    ):
        """
        初始化批量状态更新器

        Args:
            update_func: 实际的状态更新函数，接收 task_id, status, **kwargs
            batch_size: 批量大小，达到此数量时立即刷新
            flush_interval: 刷新间隔（秒），达到此时间间隔时刷新
        """
        self._update_func = update_func
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        # 批量队列：存储 (task_id, status, kwargs)
        self._batch: deque = deque()
        self._batch_lock = threading.Lock()
        self._last_flush = time.time()

    def update(
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
        添加状态更新到批量队列

        Args:
            task_id: 任务ID
            status: 任务状态
            start_time: 任务开始时间（可选）
            end_time: 任务结束时间（可选）
            result: 任务执行结果（可选）
            error: 错误信息（可选）
            submit_time: 任务提交时间（可选）
        """
        update_item = {
            "task_id": task_id,
            "status": status,
            "start_time": start_time,
            "end_time": end_time,
            "result": result,
            "error": error,
            "submit_time": submit_time,
        }

        with self._batch_lock:
            self._batch.append(update_item)

            # 检查是否需要刷新
            current_time = time.time()
            time_since_last_flush = current_time - self._last_flush

            # 如果批量大小达到阈值或超过刷新间隔，立即刷新
            if len(self._batch) >= self.batch_size or time_since_last_flush >= self.flush_interval:
                self._last_flush = current_time
                self._flush()

    def check_and_flush(self) -> None:
        """
        手动检查并执行批量刷新

        可以在外部定期调用此方法以触发定时刷新。
        """
        self._check_and_flush()

    def _flush(self) -> None:
        """刷新批量更新（需要在 batch_lock 保护下调用）"""
        if not self._batch:
            return

        # 获取批量数据（在锁保护下）
        batch_data = list(self._batch)
        self._batch.clear()

        # 释放锁后执行更新
        # 注意：这里假设调用者已经持有锁，我们需要在finally中重新获取
        # 但由于调用者可能使用with语句，我们不使用release/acquire
        # 而是直接执行更新（锁仍在持有状态，但允许其他操作等待）
        try:
            for item in batch_data:
                try:
                    self._update_func(
                        item["task_id"],
                        item["status"],
                        start_time=item["start_time"],
                        end_time=item["end_time"],
                        result=item["result"],
                        error=item["error"],
                        submit_time=item["submit_time"],
                    )
                except Exception as e:
                    # 记录错误但不影响其他更新
                    logging.getLogger(__name__).error(
                        f"批量更新任务状态失败 [{type(e).__name__}]: {e}", exc_info=True
                    )
        except Exception:
            # 如果执行更新出错，重新将数据放回队列
            with self._batch_lock:
                self._batch.extend(batch_data)
            raise

    def _check_and_flush(self) -> None:
        """检查是否需要刷新批量更新（基于时间间隔）"""
        with self._batch_lock:
            if not self._batch:
                return

            if time.time() - self._last_flush >= self.flush_interval:
                self._flush()

    def force_flush(self) -> int:
        """
        强制刷新所有待处理的更新

        Returns:
            int: 刷新前队列中的更新数量
        """
        with self._batch_lock:
            pending_count = len(self._batch)
            if pending_count > 0:
                self._flush()
            return pending_count

    def get_pending_count(self) -> int:
        """
        获取当前待处理的更新数量

        Returns:
            int: 待处理的更新数量
        """
        with self._batch_lock:
            return len(self._batch)

    def shutdown(self) -> int:
        """
        关闭更新器，刷新所有待处理的更新

        Returns:
            int: 刷新前队列中的更新数量
        """
        return self.force_flush()


class TaskStatusManager:
    """
    任务状态管理器

    负责任务状态的存储、更新和查询。
    使用分片锁和优先级队列优化性能，支持高并发操作。
    支持批量状态更新，减少锁获取次数，提升写入性能。

    线程安全说明：
    - 使用分片锁，不同分片的操作可以并发执行
    - 同一分片内的操作串行化，保证线程安全
    - 清理操作支持增量清理，避免长时间阻塞
    - 批量更新器内部使用队列和锁，保证线程安全
    """

    # 配置常量
    DEFAULT_SHARD_COUNT = 16  # 默认分片数量
    DEFAULT_MAX_CLEANUP_PER_BATCH = 100  # 每次清理的最大任务数量

    # 批量更新配置
    DEFAULT_BATCH_SIZE = 100  # 默认批量大小
    DEFAULT_BATCH_FLUSH_INTERVAL = 0.1  # 默认批量刷新间隔（秒）

    def __init__(
        self,
        logger: logging.Logger,
        task_status_ttl: int,
        max_task_status_count: int,
        shard_count: Optional[int] = None,
        batch_size: Optional[int] = None,
        batch_flush_interval: Optional[float] = None,
    ):
        """
        初始化任务状态管理器

        Args:
            logger: 日志记录器
            task_status_ttl: 任务状态TTL（秒）
            max_task_status_count: 最大任务状态数量
            shard_count: 分片数量，默认从环境变量 TASK_STATUS_SHARD_COUNT 读取，或使用16
            batch_size: 批量更新大小（可选，默认使用类常量）
            batch_flush_interval: 批量刷新间隔（秒）（可选，默认使用类常量）
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

        # 批量更新配置
        self._batch_size = batch_size if batch_size is not None else self.DEFAULT_BATCH_SIZE
        self._batch_flush_interval = (
            batch_flush_interval
            if batch_flush_interval is not None
            else self.DEFAULT_BATCH_FLUSH_INTERVAL
        )

        # 初始化批量更新器
        self._batch_updater: Optional[BatchedStatusUpdater] = None
        self._use_batch_update = True

        # 自动初始化批量更新器
        self.enable_batch_update(True)

    def enable_batch_update(self, enabled: bool = True) -> None:
        """
        启用或禁用批量更新

        Args:
            enabled: 是否启用批量更新
        """
        self._use_batch_update = enabled

        if enabled and self._batch_updater is None:
            # 初始化批量更新器
            self._batch_updater = BatchedStatusUpdater(
                update_func=self._do_update_task_status,
                batch_size=self._batch_size,
                flush_interval=self._batch_flush_interval,
            )
        elif not enabled and self._batch_updater is not None:
            # 刷新并禁用批量更新
            self._batch_updater.shutdown()
            self._batch_updater = None

    def _do_update_task_status(
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
        实际执行状态更新（批量更新回调）

        Args:
            task_id: 任务ID
            status: 任务状态
            start_time: 任务开始时间（可选）
            end_time: 任务结束时间（可选）
            result: 任务执行结果（可选）
            error: 错误信息（可选）
            submit_time: 任务提交时间（可选）
        """
        # 获取当前状态（如果存在）
        current_status = self.sharded_status.get_status(task_id) or {}

        # 合并任务状态
        new_status = self._merge_task_status(
            current_status, status, start_time, end_time, result, error, submit_time
        )

        # 更新分片存储
        self.sharded_status.update_status(task_id, new_status, current_status)

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
        if self._use_batch_update and self._batch_updater is not None:
            # 使用批量更新
            self._batch_updater.update(
                task_id,
                status,
                start_time=start_time,
                end_time=end_time,
                result=result,
                error=error,
                submit_time=submit_time,
            )
        else:
            # 直接更新
            self._do_update_task_status(
                task_id,
                status,
                start_time=start_time,
                end_time=end_time,
                result=result,
                error=error,
                submit_time=submit_time,
            )

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
                f"清理了 {cleaned_count} 个过期任务状态，" f"当前任务状态数: {current_count}"
            )

        return cleaned_count

    def resize_shards(self, new_shard_count: int) -> bool:
        """
        动态调整分片数量

        此方法会重新分配所有任务状态到新的分片结构中。
        由于需要重建所有数据结构，这可能是一个耗时操作，
        建议在低负载时执行或在外部异步执行。

        Args:
            new_shard_count: 新的分片数量，必须为正整数

        Returns:
            bool: 如果调整成功返回True，否则返回False

        Warning:
            此操作会短暂阻塞所有状态更新和查询操作。
            建议在系统初始化时设置合适的分片数量，
            并尽量避免在生产环境中频繁调整。
        """
        if new_shard_count < 1:
            self.logger.warning(f"无效的分片数量: {new_shard_count}，必须大于0")
            return False

        if new_shard_count == self.sharded_status.shard_count:
            self.logger.info(f"分片数量无需调整，当前已是 {new_shard_count}")
            return True

        self.logger.info(
            f"正在调整分片数量从 {self.sharded_status.shard_count} 到 {new_shard_count}"
        )

        success = self.sharded_status.resize_shards(new_shard_count)

        if success:
            self.logger.info(f"分片数量调整成功，当前分片数: {new_shard_count}")
        else:
            self.logger.error(f"分片数量调整失败")

        return success

    def shutdown(self) -> int:
        """
        关闭状态管理器，刷新所有待处理的批量更新

        Returns:
            int: 刷新前待处理的更新数量
        """
        pending_count = 0
        if self._batch_updater is not None:
            pending_count = self._batch_updater.shutdown()
            self._batch_updater = None
        return pending_count

    def get_pending_update_count(self) -> int:
        """
        获取当前待处理的更新数量

        Returns:
            int: 待处理的更新数量
        """
        if self._batch_updater is not None:
            return self._batch_updater.get_pending_count()
        return 0
