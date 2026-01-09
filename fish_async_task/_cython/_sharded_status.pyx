"""Cython 分片任务状态存储实现

这是一个示例 Cython 实现，展示如何将核心路径编译为 C 扩展。
注意：这是一个简化版本，完整实现需要更多工作。

编译方法：
    python setup_cython.py build_ext --inplace
"""

# cython: language_level=3
# cython: embedsignature=True

import threading
from typing import Dict, Optional


cdef class ShardedTaskStatus:
    """Cython 实现的分片任务状态存储

    这是一个示例实现，展示 Cython 优化的可能性。
    完整实现需要将所有核心方法移植到 Cython。
    """

    cdef int shard_count
    cdef list _shards
    cdef list _shard_locks

    def __init__(self, shard_count: int = 16):
        """初始化分片任务状态存储"""
        if shard_count < 1:
            raise ValueError(f"shard_count 必须 >= 1，当前值: {shard_count}")

        self.shard_count = shard_count
        self._shards = [{} for _ in range(shard_count)]
        self._shard_locks = [threading.Lock() for _ in range(shard_count)]

    def get_status(self, str task_id) -> Optional[Dict]:
        """获取任务状态"""
        shard_index = self._compute_shard_index(task_id)

        with self._shard_locks[shard_index]:
            return self._shards[shard_index].get(task_id)

    def update_status(self, str task_id, dict status):
        """更新任务状态"""
        shard_index = self._compute_shard_index(task_id)

        with self._shard_locks[shard_index]:
            self._shards[shard_index][task_id] = status

    def remove_status(self, str task_id):
        """删除任务状态"""
        shard_index = self._compute_shard_index(task_id)

        with self._shard_locks[shard_index]:
            if task_id in self._shards[shard_index]:
                del self._shards[shard_index][task_id]

    cdef int _compute_shard_index(self, str task_id) except *:
        """计算任务应该存储在哪个分片"""
        import hashlib

        hash_bytes = hashlib.md5(task_id.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:4], byteorder="big")
        return hash_int % self.shard_count

    def get_task_count(self) -> int:
        """获取任务总数"""
        total = 0
        for shard in self._shards:
            total += len(shard)
        return total
