"""
新增性能模块测试

测试所有新增的性能优化功能。
"""

import queue
import threading
import time

from fish_async_task.performance import (
    PerformanceMetrics,
    PriorityTaskManager,
    PriorityTaskQueue,
    SystemHealthMonitor,
    TaskDependencyManager,
    TaskResourceManager,
)
from fish_async_task.performance.task_cancellation import (
    CancelEvent,
    CancellableTask,
    TaskCancellationManager,
)


def test_performance_metrics():
    """测试性能指标收集器"""
    print("\n=== 测试 PerformanceMetrics ===")

    metrics = PerformanceMetrics(max_history=100)

    # 测试基本记录
    metrics.record_task_submitted()
    metrics.record_task_completed(0.5, 0.1)
    metrics.record_task_submitted()
    metrics.record_task_completed(0.3, 0.05)
    metrics.record_task_submitted()
    metrics.record_task_failed(0.8, 0.2)

    result = metrics.get_metrics()

    assert result["tasks_submitted"] == 3, "任务提交数错误"
    assert result["tasks_completed"] == 2, "任务完成数错误"
    assert result["tasks_failed"] == 1, "任务失败数错误"
    assert result["success_rate"] == 2 / 3, "成功率错误"
    assert result["tasks_in_progress"] == 0, "进行中任务数错误"

    # 测试百分位数
    percentiles = metrics.get_percentiles([50, 90, 99])
    assert "p50" in percentiles, "缺少 p50"
    assert "p90" in percentiles, "缺少 p90"

    # 测试重置
    metrics.reset()
    result = metrics.get_metrics()
    assert result["tasks_submitted"] == 0, "重置失败"

    print(f"✅ PerformanceMetrics 测试通过")
    print(f"   - 任务数: {result['tasks_submitted']}")
    print(f"   - 成功率: {result['success_rate']:.2%}")


def test_system_health_monitor():
    """测试系统健康监控器"""
    print("\n=== 测试 SystemHealthMonitor ===")

    import logging

    logger = logging.getLogger(__name__)
    monitor = SystemHealthMonitor(logger)

    # 模拟指标数据
    metrics = {
        "tasks_in_progress": 500,
        "failure_rate": 0.02,
        "avg_execution_time_seconds": 10.0,
    }

    # 更新健康状态
    health = monitor.update_health_status(metrics)

    assert health["overall_status"] in ["green", "yellow", "red"], "健康状态无效"

    # 获取健康状态
    status = monitor.get_health_status()
    assert "queue_size" in status, "缺少队列检查"

    print(f"✅ SystemHealthMonitor 测试通过")
    print(f"   - 系统状态: {health['overall_status']}")


def test_task_resource_manager():
    """测试任务资源管理器"""
    print("\n=== 测试 TaskResourceManager ===")

    import logging

    logger = logging.getLogger(__name__)
    manager = TaskResourceManager(logger, max_tracked=100)

    # 测试资源注册
    manager.register_resource("task_1", "resource_1", "file_handle_1")
    manager.register_resource("task_1", "resource_2", "connection_1")
    manager.register_resource("task_2", "resource_3", "file_handle_2")

    assert manager.get_resource_count() == 3, "资源数量错误"
    assert manager.get_task_resource_count("task_1") == 2, "任务资源数错误"

    # 测试任务清理
    cleaned = manager.force_cleanup_task("task_1")
    assert cleaned == 2, "清理数量错误"
    assert manager.get_task_resource_count("task_1") == 0, "清理后资源数错误"

    # 测试统计
    stats = manager.get_stats()
    assert stats["total_resources"] == 1, "统计错误"

    print(f"✅ TaskResourceManager 测试通过")
    print(f"   - 跟踪资源数: {stats['total_resources']}")
    print(f"   - 跟踪任务数: {stats['tracked_tasks']}")


def test_priority_task_queue():
    """测试优先级任务队列"""
    print("\n=== 测试 PriorityTaskQueue ===")

    from fish_async_task.performance.priority_queue import PrioritizedTask

    pq = PriorityTaskQueue(maxsize=100)

    # 测试优先级排序
    results = []

    def task_func(priority, task_id):
        results.append((priority, task_id))
        return f"Task {task_id}"

    # 逆序提交
    for i in range(5):
        task_id = f"task_{5-i}"
        priority = 5 - i

        task = PrioritizedTask(
            priority=priority,
            task_id=task_id,
            func=lambda p, t: task_func(p, t),
            args=(priority, task_id),
            kwargs={},
            submit_time=time.time(),
        )
        pq.put(task)

    # 按优先级取出
    retrieved = []
    while not pq.empty():
        task = pq.get()
        retrieved.append(task.priority)

    # 验证排序正确（优先级数字越小越先出队）
    assert retrieved == [1, 2, 3, 4, 5], f"优先级排序错误: {retrieved}"

    print(f"✅ PriorityTaskQueue 测试通过")
    print(f"   - 队列大小: {pq.qsize()}")
    print(f"   - 取出顺序: {retrieved}")


def test_task_dependency_manager():
    """测试任务依赖管理器"""
    print("\n=== 测试 TaskDependencyManager ===")

    dep_manager = TaskDependencyManager()

    # 添加依赖（task_A 没有依赖，所以应该是就绪的）
    dep_manager.add_dependency("task_C", ["task_A", "task_B"])
    dep_manager.add_dependency("task_B", ["task_A"])

    # task_A 没有依赖，应该就绪
    assert dep_manager.is_ready("task_A"), "task_A 没有依赖应该就绪"
    assert not dep_manager.is_ready("task_B"), "task_B 依赖 task_A，不应就绪"
    assert not dep_manager.is_ready("task_C"), "task_C 依赖 task_A 和 task_B，不应就绪"

    # 标记 task_A 完成
    dep_manager.mark_completed("task_A")

    assert dep_manager.is_ready("task_B"), "task_B 依赖 task_A 已完成，应该就绪"
    assert not dep_manager.is_ready("task_C"), "task_C 还依赖 task_B，不应就绪"

    # 标记 task_B 完成
    dep_manager.mark_completed("task_B")

    assert dep_manager.is_ready("task_C"), "task_C 的所有依赖都已完成，应该就绪"

    # 获取可执行任务
    ready = dep_manager.get_ready_tasks()
    assert "task_C" in ready, "task_C 应该在就绪列表中"

    # 测试循环依赖检测（A→C→A 构成环）
    # 历史注：此测试曾因 get_ready_tasks 死锁从未执行到这里；
    # 旧断言只加了 A→C 单向依赖（无环）却期望检测到环，属断言错误
    dep_manager2 = TaskDependencyManager()
    dep_manager2.add_dependency("task_A", ["task_C"])
    dep_manager2.add_dependency("task_C", ["task_A"])
    has_cycle = dep_manager2.has_circular_dependency("task_A")
    assert has_cycle, "应该检测到循环依赖"

    # 测试统计
    stats = dep_manager.get_stats()
    assert stats["completed_tasks"] == 2, "完成任务数错误"

    print(f"✅ TaskDependencyManager 测试通过")
    print(f"   - 完成任务: {stats['completed_tasks']}")
    print(f"   - 等待任务: {stats['pending_tasks']}")


def test_task_cancellation_manager():
    """测试任务取消管理器"""
    print("\n=== 测试 TaskCancellationManager ===")

    import logging

    logger = logging.getLogger(__name__)
    cancel_manager = TaskCancellationManager(logger)

    # 测试取消事件
    cancel_event = CancelEvent()
    assert not cancel_event.is_cancelled(), "初始状态不应取消"

    cancel_event.cancel()
    assert cancel_event.is_cancelled(), "取消后状态错误"

    # 测试取消管理器
    def sample_task(cancel_event=None):
        for i in range(100):
            if cancel_event and cancel_event.is_cancelled():
                return "cancelled"
            time.sleep(0.01)
        return "completed"

    # 注册任务
    event = cancel_manager.register_task("task_1", sample_task)

    # 启动任务
    task_thread = threading.Thread(target=lambda: sample_task(cancel_event=event))
    task_thread.start()

    # 等待任务开始
    time.sleep(0.1)

    # 取消任务
    result = cancel_manager.cancel_task("task_1", timeout=1.0)
    task_thread.join(timeout=1.0)

    assert result, "取消应该成功"

    # 测试统计
    stats = cancel_manager.get_stats()
    print(f"✅ TaskCancellationManager 测试通过")
    print(f"   - 跟踪任务: {stats['total_tracked']}")
    print(f"   - 活跃任务: {stats['active']}")


def test_incremental_cleanup():
    """测试增量清理优化"""
    print("\n=== 测试增量清理优化 ===")

    from fish_async_task.task_status import ShardedTaskStatusWithExpiry

    # 创建分片存储
    storage = ShardedTaskStatusWithExpiry(shard_count=4, ttl=1)

    # 添加大量任务
    for i in range(100):
        storage.update_status(f"task_{i}", {"status": "completed", "end_time": time.time() - 10})

    # 测试增量清理
    initial_count = storage.get_total_count()
    assert initial_count == 100, f"初始数量错误: {initial_count}"

    # 强制执行最大数量限制（使用增量清理）
    cleaned = storage.enforce_max_count(50)
    final_count = storage.get_total_count()

    assert final_count <= 50, f"清理后数量错误: {final_count}"
    assert cleaned == 50, f"清理数量错误: {cleaned}"

    print(f"✅ 增量清理测试通过")
    print(f"   - 初始数量: {initial_count}")
    print(f"   - 清理数量: {cleaned}")
    print(f"   - 最终数量: {final_count}")


def test_config_hot_reload():
    """测试配置热重载"""
    print("\n=== 测试配置热重载 ===")

    import logging
    import os

    # 设置测试环境变量
    os.environ["TEST_MAX_WORKERS"] = "20"

    from fish_async_task.config import HotReloadConfig

    logger = logging.getLogger(__name__)
    config = HotReloadConfig(logger, reload_interval=60)

    # 注册配置
    config.register_config(
        key="MAX_WORKERS", parser=lambda: int(os.getenv("TEST_MAX_WORKERS", "10")), default=10
    )

    # 获取配置
    value = config.get("MAX_WORKERS")
    assert value == 20, f"配置值错误: {value}"

    # 修改环境变量
    os.environ["TEST_MAX_WORKERS"] = "30"

    # 手动重载
    reloaded = config.reload()
    assert reloaded == 1, "重载数量错误"

    # 获取新值
    value = config.get("MAX_WORKERS", use_cache=False)
    assert value == 30, f"热重载值错误: {value}"

    # 清理
    del os.environ["TEST_MAX_WORKERS"]

    print(f"✅ 配置热重载测试通过")
    print(f"   - 重载后值: {value}")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始全面测试新增性能模块")
    print("=" * 60)

    try:
        test_performance_metrics()
        test_system_health_monitor()
        test_task_resource_manager()
        test_priority_task_queue()
        test_task_dependency_manager()
        test_task_cancellation_manager()
        test_incremental_cleanup()
        test_config_hot_reload()

        print("\n" + "=" * 60)
        print("🎉 所有测试通过！")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
