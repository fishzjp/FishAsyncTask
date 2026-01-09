"""Cython 优先级队列清理实现

这是一个示例 Cython 实现，展示如何将核心路径编译为 C 扩展。
注意：这是一个简化版本，完整实现需要更多工作。

编译方法：
    python setup_cython.py build_ext --inplace
"""

# cython: language_level=3
# cython: embedsignature=True

import heapq
import threading
import time
from typing import Dict, Optional


cdef class TaskStatusWithExpiry:
    """Cython 实现的优先级队列清理

    这是一个示例实现，展示 Cython 优化的可能性。
    完整实现需要将所有核心方法移植到 Cython。
    """

    cdef float ttl
    cdef dict status_dict
    cdef list expiry_heap
    cdef object heap_lock

    def __init__(self, ttl: int = 300):
        """初始化优先级队列清理存储"""
        if ttl <= 0:
            raise ValueError(f"ttl 必须 > 0，当前值: {ttl}")

        self.ttl = ttl
        self.status_dict = {}
        self.expiry_heap = []
        self.heap_lock = threading.Lock()

    def add_task(self, str task_id, dict status):
        """添加任务到存储"""
        with self.heap_lock:
            self.status_dict[task_id] = status

            # 计算过期时间
            if "end_time" in status:
                expiry_time = status["end_time"] + self.ttl
            else:
                expiry_time = time.time() + self.ttl

            heapq.heappush(self.expiry_heap, (expiry_time, task_id))

    def cleanup_expired(self) -> int:
        """清理过期任务"""
        with self.heap_lock:
            cleaned_count = 0
            current_time = time.time()

            while self.expiry_heap:
                expiry_time, task_id = self.expiry_heap[0]

                if expiry_time > current_time:
                    break

                heapq.heappop(self.expiry_heap)

                if task_id in self.status_dict:
                    del self.status_dict[task_id]
                    cleaned_count += 1

            return cleaned_count

    def get_task_count(self) -> int:
        """获取任务数量"""
        with self.heap_lock:
            return len(self.status_dict)
