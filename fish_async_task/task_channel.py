"""
任务通道模块

包装优先级队列（Rust 或 Python 实现，经适配器自动选择）与任务载荷
旁路表，向 worker 提供与 queue.Queue 兼容的接口。

设计说明：
- 底层优先级队列只存储 task_id（Rust 侧不持有 PyObject，避免跨语言
  引用计数问题）；函数与参数存放在 Python 侧的 _payloads 旁路表。
- 关闭哨兵：put(None)/put_nowait(None) 入队一个带唯一 id 的哨兵项，
  get 取到哨兵时返回 None——与旧 queue.Queue 直接传 None 的语义一致。
  哨兵取最低优先级，保证"先清存量任务再退出"的关闭顺序。
- worker 兼容接口：get/put/put_nowait/qsize/empty/full/task_done，
  worker/core.py 主循环无需任何改动。
"""

import queue
import threading
import time
import uuid
from typing import Dict, Optional

from ._adapters import PriorityTaskQueueAdapter, get_priority_queue
from .types import TaskTuple

_SENTINEL_PREFIX = "__fish_shutdown__:"

# 哨兵优先级：i32 最大值，排在一切正常任务之后
_SHUTDOWN_PRIORITY = 2**31 - 1


class TaskChannel:
    """优先级任务通道，worker 侧接口与 queue.Queue 兼容"""

    def __init__(
        self,
        maxsize: int = 1000,
        default_priority: int = 5,
    ) -> None:
        """
        初始化任务通道

        Args:
            maxsize: 队列最大容量
            default_priority: 未指定优先级时的默认值（数字越小优先级越高）
        """
        self._queue: PriorityTaskQueueAdapter = get_priority_queue(maxsize=maxsize)
        self._default_priority = default_priority
        self._payloads: Dict[str, TaskTuple] = {}
        self._payload_lock = threading.Lock()

    def put_task(
        self,
        task: TaskTuple,
        priority: Optional[int] = None,
        block: bool = False,
        timeout: Optional[float] = None,
    ) -> None:
        """
        提交任务

        Args:
            task: 任务元组 (task_id, func, args, kwargs)
            priority: 优先级（数字越小优先级越高），None 使用默认值
            block: 队列满时是否阻塞等待
            timeout: 阻塞等待的超时时间（秒）

        Raises:
            queue.Full: 队列满（非阻塞模式，或阻塞等待超时）
        """
        task_id = task[0]
        with self._payload_lock:
            self._payloads[task_id] = task
        try:
            self._queue.put(
                task_id,
                priority if priority is not None else self._default_priority,
                block=block,
                timeout=timeout,
            )
        except queue.Full:
            # 入队失败必须回滚旁路表，否则载荷泄漏
            with self._payload_lock:
                self._payloads.pop(task_id, None)
            raise

    def get(
        self, block: bool = True, timeout: Optional[float] = None
    ) -> Optional[TaskTuple]:
        """
        获取最高优先级任务

        Returns:
            TaskTuple 任务元组；哨兵（关闭信号）返回 None

        Raises:
            queue.Empty: 队列空（非阻塞模式，或阻塞等待超时）
        """
        # 孤儿 id（clear 竞态遗留）重试时折算剩余超时，
        # 保证总等待不超过调用者给定的 timeout
        deadline = None if timeout is None else time.monotonic() + timeout
        remaining = timeout
        while True:
            task_id = self._queue.get(block=block, timeout=remaining)
            if task_id.startswith(_SENTINEL_PREFIX):
                return None
            with self._payload_lock:
                payload = self._payloads.pop(task_id, None)
            if payload is not None:
                return payload
            if not block:
                raise queue.Empty()
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty()

    def put_nowait(self, item: Optional[TaskTuple]) -> None:
        """queue.Queue 兼容接口；item 为 None 时入队关闭哨兵"""
        if item is None:
            # 哨兵 id 必须唯一：底层 task_ids 为集合，重复 id 会少计 qsize
            self._queue.put(
                _SENTINEL_PREFIX + uuid.uuid4().hex, _SHUTDOWN_PRIORITY, block=False
            )
        else:
            self.put_task(item, block=False)

    def put(
        self,
        item: Optional[TaskTuple],
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> None:
        """queue.Queue 兼容接口；item 为 None 时入队关闭哨兵"""
        if item is None:
            self._queue.put(
                _SENTINEL_PREFIX + uuid.uuid4().hex,
                _SHUTDOWN_PRIORITY,
                block=block,
                timeout=timeout,
            )
        else:
            self.put_task(item, block=block, timeout=timeout)

    def qsize(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()

    def empty(self) -> bool:
        """检查队列是否为空"""
        return self._queue.empty()

    def full(self) -> bool:
        """检查队列是否已满"""
        return self._queue.full()

    def task_done(self) -> None:
        """queue.Queue 兼容占位；本项目未使用 join() 语义"""

    def clear(self) -> None:
        """清空队列与载荷表（shutdown 时调用）"""
        # 先清队列再清旁路表：并发 get 最多拿到孤儿 id 后按剩余超时重试，
        # 不会拿到已清除任务的载荷
        self._queue.clear()
        with self._payload_lock:
            self._payloads.clear()
