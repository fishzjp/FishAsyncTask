"""
任务资源管理器测试
"""

import threading
import time

import pytest

from fish_async_task.performance.resource_manager import (
    TaskResource,
    TaskResourceManager,
)


class TestTaskResource:
    """测试 TaskResource 类"""

    def test_init(self):
        """测试初始化"""
        resource = TaskResource("res1", "data")
        assert resource.resource_id == "res1"
        assert resource.resource == "data"
        assert resource.cleanup_func is None
        assert resource.created_at > 0
        assert resource.last_used > 0

    def test_init_with_cleanup(self):
        """测试带清理函数的初始化"""
        cleanup_called = []

        def cleanup():
            cleanup_called.append(True)

        resource = TaskResource("res1", "data", cleanup)
        assert resource.cleanup_func == cleanup

    def test_update_last_used(self):
        """测试更新最后使用时间"""
        resource = TaskResource("res1", "data")
        original_time = resource.last_used
        time.sleep(0.01)
        resource.update_last_used()
        assert resource.last_used > original_time

    def test_cleanup_without_func(self):
        """测试没有清理函数时的清理"""
        resource = TaskResource("res1", "data")
        assert resource.cleanup() is False

    def test_cleanup_with_func(self):
        """测试带清理函数时的清理"""
        cleanup_called = []

        def cleanup():
            cleanup_called.append(True)

        resource = TaskResource("res1", "data", cleanup)
        assert resource.cleanup() is True
        assert cleanup_called == [True]

    def test_cleanup_with_exception(self):
        """测试清理函数抛出异常"""

        def cleanup():
            raise ValueError("Cleanup error")

        resource = TaskResource("res1", "data", cleanup)
        assert resource.cleanup() is False


class TestTaskResourceManager:
    """测试 TaskResourceManager 类"""

    def test_init_default(self):
        """测试默认初始化"""
        manager = TaskResourceManager()
        assert manager._max_tracked == TaskResourceManager.MAX_TRACKED_RESOURCES
        assert manager._resources == {}
        assert manager._task_resources == {}

    def test_start_stop(self):
        """测试启动和停止"""
        manager = TaskResourceManager()
        manager.start()
        assert manager._running.is_set()
        manager.stop()
        assert not manager._running.is_set()

    def test_register_resource(self):
        """测试注册资源"""
        manager = TaskResourceManager()
        manager.register_resource("task1", "res1", "data")
        assert "res1" in manager._resources
        assert "task1" in manager._task_resources
        assert "res1" in manager._task_resources["task1"]

    def test_unregister_resource(self):
        """测试注销资源"""
        manager = TaskResourceManager()
        manager.register_resource("task1", "res1", "data")
        result = manager.unregister_resource("res1")
        assert result is True
        assert "res1" not in manager._resources
        assert "res1" not in manager._task_resources["task1"]

    def test_cleanup_task_resources(self):
        """测试清理任务资源"""
        cleanup_called = []

        def cleanup():
            cleanup_called.append(True)

        manager = TaskResourceManager()
        manager.register_resource("task1", "res1", "data", cleanup)
        count = manager.cleanup_task_resources("task1")
        assert count == 1
        assert cleanup_called == [True]
        assert "res1" not in manager._resources

    def test_force_cleanup_task(self):
        """测试强制清理任务资源"""
        cleanup_called = []

        def cleanup():
            cleanup_called.append(True)

        manager = TaskResourceManager()
        manager.register_resource("task1", "res1", "data", cleanup)
        count = manager.force_cleanup_task("task1")
        assert count == 1
        assert cleanup_called == [True]

    def test_register_task(self):
        """测试注册任务"""
        manager = TaskResourceManager()
        manager.register_task("task1")
        assert "task1" in manager._task_resources
        assert manager._task_resources["task1"] == set()

    def test_concurrent_operations(self):
        """测试并发操作"""
        manager = TaskResourceManager()

        def register_resources():
            for i in range(50):
                manager.register_resource(f"task{i % 10}", f"res{i}", f"data{i}")

        threads = [threading.Thread(target=register_resources) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证资源已注册（由于驱逐可能少于总数）
        assert len(manager._resources) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
