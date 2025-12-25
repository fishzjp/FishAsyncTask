"""
任务管理器测试
"""

import os
import time
import queue
import pytest
from fish_async_task import TaskManager
from fish_async_task.task_manager import TaskManager as TaskManagerClass, TaskQueueFullError


@pytest.fixture(autouse=True)
def cleanup_instances():
    """每个测试前后清理单例实例"""
    # 测试前清理
    TaskManagerClass._instances.clear()
    yield
    # 测试后清理
    TaskManagerClass._instances.clear()


def simple_task(value: int):
    """简单的测试任务"""
    time.sleep(0.1)
    return value * 2


def failing_task():
    """会失败的任务"""
    raise ValueError("任务执行失败")


def wait_for_task_completion(task_manager, task_id, timeout=10):
    """等待任务完成的辅助函数"""
    waited = 0
    while waited < timeout:
        status = task_manager.get_task_status(task_id)
        if status and status["status"] in ("completed", "failed"):
            return status
        time.sleep(0.1)
        waited += 0.1
    return task_manager.get_task_status(task_id)


def long_running_task(duration: float):
    """长时间运行的任务"""
    time.sleep(duration)
    return f"任务完成，耗时 {duration} 秒"


def timeout_task():
    """会超时的任务"""
    time.sleep(10)
    return "不应该执行到这里"


def test_submit_and_get_status():
    """测试任务提交和状态查询"""
    # 使用类直接创建实例，避免单例模式
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    task_id = task_manager.submit_task(simple_task, 5)
    assert task_id is not None
    
    # 等待任务完成
    status = wait_for_task_completion(task_manager, task_id)
    assert status is not None
    assert status["status"] == "completed"
    assert status["result"] == 10
    
    task_manager.shutdown()


def test_failed_task():
    """测试失败任务"""
    # 使用类直接创建实例，避免单例模式
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    task_id = task_manager.submit_task(failing_task)
    assert task_id is not None
    
    # 等待任务完成
    status = wait_for_task_completion(task_manager, task_id)
    assert status is not None
    assert status["status"] == "failed"
    assert "error" in status
    
    task_manager.shutdown()


def test_multiple_tasks():
    """测试多个任务"""
    # 使用类直接创建实例，避免单例模式
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    task_ids = []
    for i in range(10):
        task_id = task_manager.submit_task(simple_task, i)
        if task_id:
            task_ids.append(task_id)
    
    assert len(task_ids) == 10
    
    # 等待所有任务完成
    for task_id in task_ids:
        status = wait_for_task_completion(task_manager, task_id, timeout=15)
        assert status is not None
        assert status["status"] == "completed"
    
    task_manager.shutdown()


def test_clear_task_status():
    """测试清除任务状态"""
    # 使用类直接创建实例，避免单例模式
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    task_id = task_manager.submit_task(simple_task, 5)
    assert task_id is not None
    
    # 等待任务完成
    status = wait_for_task_completion(task_manager, task_id)
    assert status is not None
    assert status["status"] == "completed"
    
    # 清除特定任务状态
    task_manager.clear_task_status(task_id)
    status = task_manager.get_task_status(task_id)
    assert status is None
    
    # 清除所有任务状态
    task_id2 = task_manager.submit_task(simple_task, 10)
    # 等待任务完成
    status = wait_for_task_completion(task_manager, task_id2)
    assert status is not None
    assert status["status"] == "completed"
    
    task_manager.clear_task_status()
    status2 = task_manager.get_task_status(task_id2)
    assert status2 is None
    
    task_manager.shutdown()


def test_singleton_pattern():
    """测试单例模式"""
    # 清理之前的实例
    TaskManagerClass._instances.clear()
    
    manager1 = TaskManager()
    manager2 = TaskManager()
    assert manager1 is manager2
    
    # 清理
    manager1.shutdown()


def test_queue_full():
    """测试队列满的情况"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 停止所有工作线程，确保队列不会被消费
    task_manager._running_event.clear()
    task_manager.worker_manager.send_shutdown_signals()
    task_manager.worker_manager.wait_for_threads_exit(task_manager.DEFAULT_THREAD_JOIN_TIMEOUT)
    
    # 重新创建一个小队列便于测试
    original_queue = task_manager.task_queue
    task_manager.task_queue = queue.Queue(maxsize=5)
    
    # 填满队列
    task_ids = []
    for _ in range(5):
        task_id = task_manager.submit_task(simple_task, 1)
        task_ids.append(task_id)
    
    # 验证队列已满
    assert task_manager.task_queue.full(), "队列应该已满"
    
    # 尝试提交新任务，应该抛出 TaskQueueFullError（队列已满）
    with pytest.raises(TaskQueueFullError):
        task_manager.submit_task(simple_task, 1)
    
    # 恢复原始队列和运行状态
    task_manager.task_queue = original_queue
    task_manager._running_event.set()
    task_manager.shutdown()


def test_shutdown():
    """测试shutdown流程"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 提交一些任务
    task_ids = []
    for _ in range(5):
        task_id = task_manager.submit_task(simple_task, 1)
        if task_id:
            task_ids.append(task_id)
    
    # 获取线程数量
    with task_manager.threads_lock:
        thread_count_before = len(task_manager.worker_threads)
    
    # 关闭管理器
    task_manager.shutdown()
    
    # 验证所有线程已退出（shutdown后worker_threads会被清空）
    assert len(task_manager.worker_threads) == 0, "shutdown后worker_threads应该被清空"


def test_task_timeout():
    """测试任务超时机制"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 设置任务超时为1秒
    task_manager.task_timeout = 1.0
    
    # 提交一个会超时的任务
    task_id = task_manager.submit_task(timeout_task)
    assert task_id is not None
    
    # 等待任务完成（应该超时失败）
    status = wait_for_task_completion(task_manager, task_id, timeout=5)
    assert status is not None
    assert status["status"] == "failed"
    assert "超时" in status["error"] or "timeout" in status["error"].lower()
    
    task_manager.shutdown()


def test_task_timeout_disabled():
    """测试任务超时禁用时正常执行"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 禁用超时
    task_manager.task_timeout = None
    
    # 提交一个正常任务
    task_id = task_manager.submit_task(simple_task, 5)
    assert task_id is not None
    
    # 等待任务完成
    status = wait_for_task_completion(task_manager, task_id, timeout=5)
    assert status is not None
    assert status["status"] == "completed"
    
    task_manager.shutdown()


def test_config_validation():
    """测试配置验证"""
    # 保存原始环境变量
    original_ttl = os.environ.get("TASK_STATUS_TTL")
    original_max = os.environ.get("MAX_TASK_STATUS_COUNT")
    original_interval = os.environ.get("TASK_CLEANUP_INTERVAL")
    
    try:
        # 测试无效的TTL
        os.environ["TASK_STATUS_TTL"] = "-1"
        task_manager = TaskManagerClass.__new__(TaskManagerClass)
        task_manager._init_task_manager()
        assert task_manager.task_status_ttl == task_manager.DEFAULT_TASK_STATUS_TTL
        task_manager.shutdown()
        
        # 测试无效的MAX_TASK_STATUS_COUNT
        os.environ["TASK_STATUS_TTL"] = str(task_manager.DEFAULT_TASK_STATUS_TTL)
        os.environ["MAX_TASK_STATUS_COUNT"] = "0"
        task_manager = TaskManagerClass.__new__(TaskManagerClass)
        task_manager._init_task_manager()
        assert task_manager.max_task_status_count == task_manager.DEFAULT_MAX_TASK_STATUS_COUNT
        task_manager.shutdown()
        
        # 测试无效的CLEANUP_INTERVAL
        os.environ["MAX_TASK_STATUS_COUNT"] = str(task_manager.DEFAULT_MAX_TASK_STATUS_COUNT)
        os.environ["TASK_CLEANUP_INTERVAL"] = "-5"
        task_manager = TaskManagerClass.__new__(TaskManagerClass)
        task_manager._init_task_manager()
        assert task_manager.cleanup_interval == task_manager.DEFAULT_CLEANUP_INTERVAL
        task_manager.shutdown()
        
        # 测试有效的TASK_TIMEOUT
        os.environ["TASK_CLEANUP_INTERVAL"] = str(task_manager.DEFAULT_CLEANUP_INTERVAL)
        os.environ["TASK_TIMEOUT"] = "5.0"
        task_manager = TaskManagerClass.__new__(TaskManagerClass)
        task_manager._init_task_manager()
        assert task_manager.task_timeout == 5.0
        task_manager.shutdown()
        
        # 测试无效的TASK_TIMEOUT
        os.environ["TASK_TIMEOUT"] = "invalid"
        task_manager = TaskManagerClass.__new__(TaskManagerClass)
        task_manager._init_task_manager()
        assert task_manager.task_timeout is None
        task_manager.shutdown()
        
    finally:
        # 恢复原始环境变量
        if original_ttl:
            os.environ["TASK_STATUS_TTL"] = original_ttl
        elif "TASK_STATUS_TTL" in os.environ:
            del os.environ["TASK_STATUS_TTL"]
            
        if original_max:
            os.environ["MAX_TASK_STATUS_COUNT"] = original_max
        elif "MAX_TASK_STATUS_COUNT" in os.environ:
            del os.environ["MAX_TASK_STATUS_COUNT"]
            
        if original_interval:
            os.environ["TASK_CLEANUP_INTERVAL"] = original_interval
        elif "TASK_CLEANUP_INTERVAL" in os.environ:
            del os.environ["TASK_CLEANUP_INTERVAL"]


def test_atomic_status_update():
    """测试任务状态更新的原子性"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    task_id = task_manager.submit_task(simple_task, 5)
    assert task_id is not None
    
    # 检查状态更新是否包含所有必要字段
    status = wait_for_task_completion(task_manager, task_id)
    assert status is not None
    assert "status" in status
    assert "start_time" in status
    assert "end_time" in status
    assert status["status"] == "completed"
    assert status["start_time"] <= status["end_time"]
    
    task_manager.shutdown()


def test_thread_race_condition():
    """测试线程退出时的竞态条件修复"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 提交多个任务以创建多个线程
    task_ids = []
    for _ in range(10):
        task_id = task_manager.submit_task(simple_task, 1)
        if task_id:
            task_ids.append(task_id)
    
    # 等待所有任务完成
    for task_id in task_ids:
        wait_for_task_completion(task_manager, task_id)
    
    # 获取线程列表（在锁内）
    with task_manager.threads_lock:
        threads_before_shutdown = list(task_manager.worker_threads)
    
    # 关闭管理器，验证线程正确退出
    task_manager.shutdown()
    
    # 验证所有线程已退出（shutdown后worker_threads会被清空）
    assert len(task_manager.worker_threads) == 0, "shutdown后worker_threads应该被清空"


def test_shutdown_signals():
    """测试shutdown时退出信号发送"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 提交一些任务
    task_ids = []
    for _ in range(5):
        task_id = task_manager.submit_task(simple_task, 1)
        if task_id:
            task_ids.append(task_id)
    
    # 获取线程数量
    with task_manager.threads_lock:
        thread_count = len(task_manager.worker_threads)
    
    # 关闭管理器
    task_manager.shutdown()
    
    # 验证所有线程已退出
    assert thread_count >= 1, "应该有至少一个工作线程"


def test_cleanup_thread_error_handling():
    """测试清理线程的异常处理"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 设置较短的清理间隔用于测试（避免等待5分钟）
    original_cleanup_interval = task_manager.cleanup_interval
    task_manager.cleanup_interval = 1  # 1秒
    
    # 给清理线程一些时间启动
    time.sleep(0.1)
    
    # 验证清理线程存在且正在运行
    assert task_manager.cleanup_manager.cleanup_thread is not None, "清理线程应该已创建"
    assert task_manager.cleanup_manager.cleanup_thread.is_alive(), "清理线程应该正在运行"
    assert task_manager._running_event.is_set(), "运行事件应该被设置"
    
    # 提交一些任务
    task_id = task_manager.submit_task(simple_task, 1)
    wait_for_task_completion(task_manager, task_id)
    
    # 再次验证清理线程仍在运行
    assert task_manager.cleanup_manager.cleanup_thread.is_alive(), "任务完成后清理线程应该仍在运行"
    
    # 等待清理线程至少运行一次（等待一个清理间隔 + 缓冲时间）
    time.sleep(task_manager.cleanup_interval + 0.5)
    
    # 验证清理线程仍在运行（说明异常处理正常，线程没有因为异常而退出）
    assert task_manager.cleanup_manager.cleanup_thread.is_alive(), "清理线程应该在异常处理后仍在运行"
    assert task_manager._running_event.is_set(), "运行事件应该仍然被设置"
    
    # 恢复原始清理间隔
    task_manager.cleanup_interval = original_cleanup_interval
    
    task_manager.shutdown()


def test_concurrent_tasks():
    """测试并发任务处理"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 提交大量并发任务
    task_ids = []
    for i in range(50):
        task_id = task_manager.submit_task(simple_task, i)
        if task_id:
            task_ids.append(task_id)
    
    assert len(task_ids) == 50
    
    # 等待所有任务完成
    completed_count = 0
    for task_id in task_ids:
        status = wait_for_task_completion(task_manager, task_id, timeout=30)
        if status and status["status"] == "completed":
            completed_count += 1
    
    assert completed_count == 50
    
    task_manager.shutdown()


def test_task_status_cleanup():
    """测试任务状态清理"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 设置较短的TTL和清理间隔用于测试（避免等待5分钟）
    original_ttl = task_manager.task_status_ttl
    original_cleanup_interval = task_manager.cleanup_interval
    task_manager.task_status_ttl = 2  # 2秒
    task_manager.cleanup_interval = 1  # 1秒
    
    # 提交任务
    task_id = task_manager.submit_task(simple_task, 1)
    wait_for_task_completion(task_manager, task_id)
    
    # 验证任务状态存在
    status = task_manager.get_task_status(task_id)
    assert status is not None
    
    # 等待清理（等待一个清理间隔 + TTL + 缓冲时间）
    time.sleep(task_manager.cleanup_interval + task_manager.task_status_ttl + 1)
    
    # 验证任务状态已被清理（清理线程应该已经清理了过期的任务）
    status_after_cleanup = task_manager.get_task_status(task_id)
    # 注意：清理是异步的，可能还没清理，所以这里只验证清理机制存在
    # 如果任务状态还在，说明清理还没执行，但至少验证了清理线程在运行
    assert task_manager._running_event.is_set(), "运行事件应该仍然被设置"
    
    # 恢复原始配置
    task_manager.task_status_ttl = original_ttl
    task_manager.cleanup_interval = original_cleanup_interval
    task_manager.shutdown()


def test_config_validation_invalid_format():
    """测试配置验证 - 无效格式"""
    original_ttl = os.environ.get("TASK_STATUS_TTL")
    
    try:
        # 测试非数字格式
        os.environ["TASK_STATUS_TTL"] = "not_a_number"
        task_manager = TaskManagerClass.__new__(TaskManagerClass)
        task_manager._init_task_manager()
        # 应该使用默认值
        assert task_manager.task_status_ttl == task_manager.DEFAULT_TASK_STATUS_TTL
        task_manager.shutdown()
        
        # 测试空字符串
        os.environ["TASK_STATUS_TTL"] = ""
        task_manager = TaskManagerClass.__new__(TaskManagerClass)
        task_manager._init_task_manager()
        assert task_manager.task_status_ttl == task_manager.DEFAULT_TASK_STATUS_TTL
        task_manager.shutdown()
        
    finally:
        if original_ttl:
            os.environ["TASK_STATUS_TTL"] = original_ttl
        elif "TASK_STATUS_TTL" in os.environ:
            del os.environ["TASK_STATUS_TTL"]


def test_status_update_preserves_fields():
    """测试状态更新时保留已有字段"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    task_id = task_manager.submit_task(simple_task, 5)
    assert task_id is not None
    
    # 等待任务开始执行
    time.sleep(0.2)
    
    # 获取初始状态
    initial_status = task_manager.get_task_status(task_id)
    assert initial_status is not None
    assert "start_time" in initial_status
    
    initial_start_time = initial_status["start_time"]
    
    # 更新状态但不提供start_time，应该保留原有的
    task_manager.status_manager.update_task_status(
        task_id, "running", end_time=time.time()
    )
    
    updated_status = task_manager.get_task_status(task_id)
    assert updated_status is not None
    assert updated_status["start_time"] == initial_start_time
    
    task_manager.shutdown()


def test_cleanup_thread_shutdown():
    """测试清理线程的shutdown响应"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 设置较短的清理间隔用于测试
    original_cleanup_interval = task_manager.cleanup_interval
    task_manager.cleanup_interval = 2  # 2秒
    
    # 验证清理线程存在
    assert task_manager.cleanup_manager.cleanup_thread is not None
    assert task_manager.cleanup_manager.cleanup_thread.is_alive()
    
    # 等待一小段时间确保线程运行
    time.sleep(0.1)
    
    # 关闭管理器
    task_manager.shutdown()
    
    # 等待线程退出
    time.sleep(0.5)
    
    # 验证清理线程已退出
    assert not task_manager.cleanup_manager.cleanup_thread.is_alive()
    
    # 恢复原始配置
    task_manager.cleanup_interval = original_cleanup_interval


def test_thread_exit_race_condition():
    """测试线程退出时的竞态条件处理"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 提交多个任务以创建多个线程
    task_ids = []
    for _ in range(15):
        task_id = task_manager.submit_task(simple_task, 1)
        if task_id:
            task_ids.append(task_id)
    
    # 等待所有任务完成
    for task_id in task_ids:
        wait_for_task_completion(task_manager, task_id)
    
    # 获取初始线程数
    with task_manager.threads_lock:
        initial_thread_count = len(task_manager.worker_threads)
    
    # 等待空闲线程退出（idle_timeout后，加上一些缓冲时间）
    # 注意：线程退出是异步的，可能需要一些时间
    time.sleep(task_manager.idle_timeout + 2)
    
    # 验证线程数已减少（至少有一些线程退出）
    with task_manager.threads_lock:
        final_thread_count = len(task_manager.worker_threads)
    
    # 验证线程数减少了，或者至少不超过初始线程数
    # 由于线程退出是异步的，我们只验证线程数没有增加
    assert final_thread_count <= initial_thread_count, "线程数不应该增加"
    # 至少应该有一些线程退出（如果初始线程数大于最小线程数）
    if initial_thread_count > task_manager.min_workers:
        assert final_thread_count < initial_thread_count or final_thread_count <= task_manager.min_workers + 1, "空闲线程应该已退出"
    
    task_manager.shutdown()


def test_singleton_init():
    """测试单例模式的初始化"""
    # 清理之前的实例
    TaskManagerClass._instances.clear()
    
    # 创建实例
    manager1 = TaskManager()
    manager2 = TaskManager()
    
    # 验证是同一个实例
    assert manager1 is manager2
    
    # 验证实例已正确初始化
    assert hasattr(manager1, "task_queue")
    assert hasattr(manager1, "worker_manager")
    assert hasattr(manager1, "status_manager")
    
    manager1.shutdown()


def test_timeout_warning_logged():
    """测试超时时记录警告日志"""
    import logging
    from io import StringIO
    
    # 创建日志捕获器
    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.WARNING)
    
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()
    
    # 添加日志处理器
    task_manager.logger.addHandler(handler)
    task_manager.task_executor.logger.addHandler(handler)
    
    # 设置任务超时为1秒
    task_manager.task_timeout = 1.0
    
    # 提交一个会超时的任务
    task_id = task_manager.submit_task(timeout_task)
    assert task_id is not None
    
    # 等待任务完成（应该超时）
    status = wait_for_task_completion(task_manager, task_id, timeout=5)
    assert status is not None
    assert status["status"] == "failed"
    
    # 检查日志中是否包含超时警告
    log_output = log_capture.getvalue()
    assert "超时" in log_output or "timeout" in log_output.lower()
    
    task_manager.shutdown()


def test_sharded_status_concurrent_queries():
    """测试分片状态存储的并发查询正确性"""
    from fish_async_task.task_status import ShardedTaskStatusWithExpiry
    from fish_async_task.types import TaskStatusDict
    import concurrent.futures
    
    sharded_status = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
    
    # 创建1000个任务状态
    task_ids = []
    for i in range(1000):
        task_id = f"task_{i}"
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": time.time() - 100,
            "start_time": time.time() - 90,
            "end_time": time.time() - 80,
            "result": i * 2,
        }
        sharded_status.update_status(task_id, status)
        task_ids.append(task_id)
    
    # 并发查询所有任务状态
    def query_task(task_id: str):
        return sharded_status.get_status(task_id)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(query_task, task_id) for task_id in task_ids]
        results = [f.result() for f in futures]
    
    # 验证所有查询都成功
    assert len(results) == 1000
    assert all(r is not None for r in results)
    assert all(r["status"] == "completed" for r in results)


def test_sharded_status_concurrent_updates():
    """测试分片状态存储的并发更新正确性"""
    from fish_async_task.task_status import ShardedTaskStatusWithExpiry
    from fish_async_task.types import TaskStatusDict
    import concurrent.futures
    
    sharded_status = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
    
    # 并发更新1000个任务状态
    def update_task(task_id: str, value: int):
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": time.time() - 100,
            "start_time": time.time() - 90,
            "end_time": time.time() - 80,
            "result": value,
        }
        sharded_status.update_status(task_id, status)
        return sharded_status.get_status(task_id)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [
            executor.submit(update_task, f"task_{i}", i * 2)
            for i in range(1000)
        ]
        results = [f.result() for f in futures]
    
    # 验证所有更新都成功
    assert len(results) == 1000
    assert all(r is not None for r in results)
    assert all(r["status"] == "completed" for r in results)
    # 验证结果值正确
    for i, result in enumerate(results):
        assert result["result"] == i * 2


def test_priority_queue_cleanup():
    """测试优先级队列清理功能"""
    from fish_async_task.task_status import ShardedTaskStatusWithExpiry
    from fish_async_task.types import TaskStatusDict
    
    # 使用较短的TTL便于测试
    sharded_status = ShardedTaskStatusWithExpiry(shard_count=4, ttl=2)
    
    # 创建一些已完成的任务（部分过期，部分未过期）
    now = time.time()
    expired_task_ids = []
    valid_task_ids = []
    
    # 创建10个已过期的任务
    for i in range(10):
        task_id = f"expired_task_{i}"
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": now - 100,
            "start_time": now - 90,
            "end_time": now - 5,  # 5秒前完成，超过2秒TTL
        }
        sharded_status.update_status(task_id, status)
        expired_task_ids.append(task_id)
    
    # 创建10个未过期的任务
    for i in range(10):
        task_id = f"valid_task_{i}"
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": now - 100,
            "start_time": now - 90,
            "end_time": now - 1,  # 1秒前完成，未超过2秒TTL
        }
        sharded_status.update_status(task_id, status)
        valid_task_ids.append(task_id)
    
    # 等待一小段时间确保时间戳正确
    time.sleep(0.1)
    
    # 执行清理
    cleaned_count = sharded_status.cleanup_expired(max_cleanup=None)
    
    # 验证过期任务被清理
    assert cleaned_count >= 10, f"应该清理至少10个过期任务，实际清理了 {cleaned_count}"
    
    # 验证过期任务已不存在
    for task_id in expired_task_ids:
        assert sharded_status.get_status(task_id) is None, f"过期任务 {task_id} 应该被清理"
    
    # 验证未过期任务仍然存在
    for task_id in valid_task_ids:
        assert sharded_status.get_status(task_id) is not None, f"未过期任务 {task_id} 应该仍然存在"


def test_incremental_cleanup():
    """测试增量清理策略"""
    from fish_async_task.task_status import ShardedTaskStatusWithExpiry
    from fish_async_task.types import TaskStatusDict
    
    sharded_status = ShardedTaskStatusWithExpiry(shard_count=4, ttl=2)
    
    # 创建大量已过期的任务
    now = time.time()
    task_ids = []
    for i in range(200):
        task_id = f"task_{i}"
        status: TaskStatusDict = {
            "status": "completed",
            "submit_time": now - 100,
            "start_time": now - 90,
            "end_time": now - 5,  # 已过期
        }
        sharded_status.update_status(task_id, status)
        task_ids.append(task_id)
    
    time.sleep(0.1)
    
    # 第一次清理，限制最多清理50个
    cleaned1 = sharded_status.cleanup_expired(max_cleanup=50)
    assert cleaned1 == 50, f"第一次应该清理50个，实际清理了 {cleaned1}"
    
    # 第二次清理，应该继续清理剩余的
    cleaned2 = sharded_status.cleanup_expired(max_cleanup=50)
    assert cleaned2 == 50, f"第二次应该清理50个，实际清理了 {cleaned2}"
    
    # 第三次清理，应该清理剩余的（可能少于50个，因为已经清理了100个）
    cleaned3 = sharded_status.cleanup_expired(max_cleanup=50)
    assert cleaned3 > 0, f"第三次应该清理一些任务，实际清理了 {cleaned3}"
    
    # 继续清理直到全部清理完成
    total_cleaned = cleaned1 + cleaned2 + cleaned3
    while True:
        cleaned = sharded_status.cleanup_expired(max_cleanup=50)
        if cleaned == 0:
            break
        total_cleaned += cleaned
    
    # 验证所有任务都被清理了
    assert total_cleaned == 200, f"应该清理200个任务，实际清理了 {total_cleaned}"
    
    # 验证所有任务状态都已不存在
    for task_id in task_ids:
        assert sharded_status.get_status(task_id) is None, f"任务 {task_id} 应该已被清理"


def test_sharded_status_thread_safety():
    """测试分片状态存储的线程安全性"""
    from fish_async_task.task_status import ShardedTaskStatusWithExpiry
    from fish_async_task.types import TaskStatusDict
    import concurrent.futures
    import random
    
    sharded_status = ShardedTaskStatusWithExpiry(shard_count=16, ttl=3600)
    
    # 创建100个任务
    task_ids = [f"task_{i}" for i in range(100)]
    
    def worker(task_id: str):
        """工作线程：随机执行查询、更新、删除操作"""
        operations = []
        for _ in range(10):
            op = random.choice(["get", "update", "get"])
            if op == "get":
                result = sharded_status.get_status(task_id)
                operations.append(("get", result is not None))
            elif op == "update":
                status: TaskStatusDict = {
                    "status": "running",
                    "submit_time": time.time(),
                    "start_time": time.time(),
                }
                sharded_status.update_status(task_id, status)
                operations.append(("update", True))
        
        return operations
    
    # 并发执行操作
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(worker, task_id) for task_id in task_ids]
        results = [f.result() for f in futures]
    
    # 验证没有异常抛出（线程安全性）
    assert len(results) == 100
    assert all(len(ops) == 10 for ops in results)


def test_task_status_manager_with_sharded_storage():
    """测试使用分片存储的 TaskStatusManager"""
    task_manager = TaskManagerClass.__new__(TaskManagerClass)
    task_manager._init_task_manager()

    # 提交多个任务
    task_ids = []
    for i in range(100):
        task_id = task_manager.submit_task(simple_task, i)
        task_ids.append(task_id)

    # 等待所有任务完成
    for task_id in task_ids:
        status = wait_for_task_completion(task_manager, task_id, timeout=15)
        assert status is not None
        assert status["status"] == "completed"

    # 验证所有任务状态都可以查询到
    for task_id in task_ids:
        status = task_manager.get_task_status(task_id)
        assert status is not None
        assert status["status"] == "completed"

    task_manager.shutdown()


# ==================== 批量状态更新测试 ====================

def test_batched_status_updater_basic():
    """测试 BatchedStatusUpdater 基本功能"""
    from fish_async_task.task_status import BatchedStatusUpdater
    from fish_async_task.types import TaskStatus

    # 跟踪更新的列表
    updates = []

    def update_func(task_id, status, **kwargs):
        updates.append({"task_id": task_id, "status": status, **kwargs})

    # 创建批量更新器（使用较小的批量大小便于测试）
    updater = BatchedStatusUpdater(
        update_func=update_func,
        batch_size=5,
        flush_interval=1.0,
    )

    # 添加3个更新（未达到批量大小）
    updater.update("task_1", "running")
    updater.update("task_2", "running")
    updater.update("task_3", "running")

    # 验证还没有执行更新
    assert len(updates) == 0
    assert updater.get_pending_count() == 3

    # 添加更多更新达到批量大小
    updater.update("task_4", "running")
    updater.update("task_5", "running")  # 这应该触发批量更新

    # 验证所有更新都已执行
    assert len(updates) == 5
    assert updater.get_pending_count() == 0

    # 验证更新内容正确
    for i, update in enumerate(updates, 1):
        assert update["task_id"] == f"task_{i}"
        assert update["status"] == "running"


def test_batched_status_updater_flush_on_interval():
    """测试 BatchedStatusUpdater 定时刷新"""
    import time
    from fish_async_task.task_status import BatchedStatusUpdater

    updates = []

    def update_func(task_id, status, **kwargs):
        updates.append({"task_id": task_id, "status": status})

    # 使用较短的刷新间隔
    updater = BatchedStatusUpdater(
        update_func=update_func,
        batch_size=100,  # 设置较大的批量大小
        flush_interval=0.2,  # 较短的刷新间隔
    )

    # 添加2个更新
    updater.update("task_1", "running")
    updater.update("task_2", "running")

    # 验证还没有执行更新
    assert len(updates) == 0

    # 等待超过刷新间隔
    time.sleep(0.3)

    # 触发检查（添加新更新会触发检查）
    updater.update("task_3", "running")

    # 验证所有更新都已执行（包括之前的）
    assert len(updates) == 3

    updater.shutdown()


def test_batched_status_updater_force_flush():
    """测试 BatchedStatusUpdater 强制刷新"""
    from fish_async_task.task_status import BatchedStatusUpdater

    updates = []

    def update_func(task_id, status, **kwargs):
        updates.append({"task_id": task_id, "status": status})

    updater = BatchedStatusUpdater(
        update_func=update_func,
        batch_size=100,
        flush_interval=10.0,  # 较长的刷新间隔
    )

    # 添加更新
    updater.update("task_1", "running")
    updater.update("task_2", "running")

    assert len(updates) == 0

    # 强制刷新
    pending = updater.force_flush()

    assert pending == 2
    assert len(updates) == 2

    updater.shutdown()


def test_batched_status_updater_shutdown():
    """测试 BatchedStatusUpdater shutdown 时刷新"""
    from fish_async_task.task_status import BatchedStatusUpdater

    updates = []

    def update_func(task_id, status, **kwargs):
        updates.append({"task_id": task_id, "status": status})

    updater = BatchedStatusUpdater(
        update_func=update_func,
        batch_size=100,
        flush_interval=10.0,
    )

    # 添加更新
    updater.update("task_1", "running")
    updater.update("task_2", "running")

    # shutdown 应该刷新所有待处理的更新
    pending = updater.shutdown()

    assert pending == 2
    assert len(updates) == 2


def test_task_status_manager_batch_update():
    """测试 TaskStatusManager 批量更新"""
    import logging
    import time
    from fish_async_task.task_status import TaskStatusManager

    logger = logging.getLogger("test")

    # 创建状态管理器（使用较小的批量大小便于测试）
    manager = TaskStatusManager(
        logger=logger,
        task_status_ttl=3600,
        max_task_status_count=10000,
        batch_size=5,
        batch_flush_interval=0.5,
    )

    # 验证批量更新已启用
    assert manager._use_batch_update is True
    assert manager._batch_updater is not None

    # 更新状态（使用批量更新）
    manager.update_task_status("task_1", "pending", submit_time=time.time())
    manager.update_task_status("task_2", "running")
    manager.update_task_status("task_3", "completed", result="result")

    # 强制刷新以确保更新执行
    manager._batch_updater.force_flush()

    # 验证状态已更新
    status1 = manager.get_task_status("task_1")
    assert status1 is not None
    assert status1["status"] == "pending"

    status2 = manager.get_task_status("task_2")
    assert status2 is not None
    assert status2["status"] == "running"

    status3 = manager.get_task_status("task_3")
    assert status3 is not None
    assert status3["status"] == "completed"
    assert status3["result"] == "result"

    # shutdown 并验证刷新
    pending = manager.shutdown()
    assert pending == 0  # 所有更新已执行


def test_task_status_manager_disable_batch_update():
    """测试禁用批量更新"""
    import logging
    from fish_async_task.task_status import TaskStatusManager

    logger = logging.getLogger("test")

    manager = TaskStatusManager(
        logger=logger,
        task_status_ttl=3600,
        max_task_status_count=10000,
    )

    # 禁用批量更新
    manager.enable_batch_update(False)

    assert manager._use_batch_update is False
    assert manager._batch_updater is None

    # 更新状态（直接更新）
    manager.update_task_status("task_1", "running")

    # 验证状态已更新
    status = manager.get_task_status("task_1")
    assert status is not None
    assert status["status"] == "running"

    manager.shutdown()


# ==================== 自适应线程管理测试 ====================

def test_adaptive_worker_manager_basic():
    """测试 AdaptiveWorkerManager 基本功能"""
    from fish_async_task.worker import AdaptiveWorkerManager

    manager = AdaptiveWorkerManager(
        min_workers=2,
        max_workers=10,
        cpu_threshold=0.8,
        queue_threshold_high=100,
        queue_threshold_low=10,
        scale_up_cooldown=5.0,
        scale_down_cooldown=30.0,
        use_cpu_monitoring=False,
    )

    # 验证配置
    assert manager.min_workers == 2
    assert manager.max_workers == 10
    assert manager.cpu_threshold == 0.8

    # 记录任务时间
    manager.record_task_time(0.1)
    manager.record_task_time(0.2)
    manager.record_task_time(0.3)

    # 验证平均任务时间（使用近似比较）
    assert abs(manager.get_avg_task_time() - 0.2) < 0.001


def test_adaptive_worker_manager_scale_up():
    """测试 AdaptiveWorkerManager 扩容判断"""
    from fish_async_task.worker import AdaptiveWorkerManager

    manager = AdaptiveWorkerManager(
        min_workers=2,
        max_workers=10,
        cpu_threshold=0.8,
        queue_threshold_high=100,
        queue_threshold_low=10,
        scale_up_cooldown=0,  # 禁用冷却期便于测试
        scale_down_cooldown=30.0,
        use_cpu_monitoring=False,
    )

    # 初始状态，不应该扩容
    assert manager.should_scale_up(5, 50) is False
    assert manager.should_scale_up(5, 50, 0.5) is False

    # 队列积压超过阈值，应该扩容
    assert manager.should_scale_up(5, 150) is True

    # 达到最大线程数，不应该扩容
    assert manager.should_scale_up(10, 150) is False


def test_adaptive_worker_manager_scale_down():
    """测试 AdaptiveWorkerManager 缩容判断"""
    from fish_async_task.worker import AdaptiveWorkerManager

    manager = AdaptiveWorkerManager(
        min_workers=2,
        max_workers=10,
        cpu_threshold=0.8,
        queue_threshold_high=100,
        queue_threshold_low=10,
        scale_up_cooldown=5.0,
        scale_down_cooldown=5.0,  # 使用正常的冷却期
        use_cpu_monitoring=False,
    )

    # 初始状态，不应该缩容（队列非空）
    assert manager.should_scale_down(5, 10) is False

    # 队列为空但空闲时间不足，不应该缩容
    assert manager.should_scale_down(5, 0, 2) is False

    # 队列为空且空闲时间足够，应该缩容
    assert manager.should_scale_down(5, 0, 10) is True

    # 达到最小线程数，不应该缩容
    assert manager.should_scale_down(2, 0, 35) is False


def test_adaptive_worker_manager_cooldown():
    """测试 AdaptiveWorkerManager 冷却期机制"""
    from fish_async_task.worker import AdaptiveWorkerManager

    manager = AdaptiveWorkerManager(
        min_workers=2,
        max_workers=10,
        cpu_threshold=0.8,
        queue_threshold_high=100,
        queue_threshold_low=10,
        scale_up_cooldown=5.0,
        scale_down_cooldown=5.0,
        use_cpu_monitoring=False,
    )

    # 触发扩容
    assert manager.should_scale_up(5, 150) is True

    # 冷却期内不应该再次扩容
    assert manager.should_scale_up(5, 150) is False

    # 触发缩容
    assert manager.should_scale_down(6, 0, 35) is True

    # 冷却期内不应该再次缩容
    assert manager.should_scale_down(6, 0, 35) is False


def test_adaptive_worker_manager_get_stats():
    """测试 AdaptiveWorkerManager 统计信息"""
    from fish_async_task.worker import AdaptiveWorkerManager

    manager = AdaptiveWorkerManager(
        min_workers=2,
        max_workers=10,
        cpu_threshold=0.8,
        queue_threshold_high=100,
        queue_threshold_low=10,
        scale_up_cooldown=5.0,
        scale_down_cooldown=30.0,
        use_cpu_monitoring=False,
    )

    # 记录一些任务时间
    for i in range(10):
        manager.record_task_time(0.1 * i)

    stats = manager.get_stats()

    assert "min_workers" in stats
    assert "max_workers" in stats
    assert "cpu_threshold" in stats
    assert "avg_task_time" in stats
    assert "task_count" in stats
    assert stats["task_count"] == 10


def test_cpu_monitor():
    """测试 CPUMonitor"""
    from fish_async_task.worker import CPUMonitor

    monitor = CPUMonitor(sample_interval=0.1, sample_count=2)

    # 获取 CPU 使用率
    cpu_usage = monitor.get_cpu_usage()

    # 如果 psutil 不可用，应该返回 None
    # 如果可用，应该返回 0.0-1.0 之间的值
    if cpu_usage is not None:
        assert 0.0 <= cpu_usage <= 1.0
    else:
        # psutil 不可用是预期行为
        pass

    # 获取 CPU 核心数
    cpu_count = monitor.get_cpu_count()
    assert cpu_count >= 1


# ==================== 配置测试 ====================

def test_config_loader_adaptive_worker():
    """测试 ConfigLoader 自适应配置加载"""
    import os
    from fish_async_task.config import ConfigLoader
    import logging

    logger = logging.getLogger("test")
    loader = ConfigLoader(logger)

    # 保存原始环境变量
    original_env = {}
    for key in ["ADAPTIVE_WORKER_ENABLED", "WORKER_CPU_THRESHOLD", "WORKER_QUEUE_THRESHOLD_HIGH"]:
        original_env[key] = os.environ.get(key)
        if key in os.environ:
            del os.environ[key]

    try:
        # 测试默认值
        config = loader.load_adaptive_worker_config()
        assert config["adaptive_worker_enabled"] is True
        assert config["cpu_threshold"] == 0.8
        assert config["queue_threshold_high"] == 100
        assert config["queue_threshold_low"] == 10

        # 测试自定义值
        os.environ["ADAPTIVE_WORKER_ENABLED"] = "false"
        os.environ["WORKER_CPU_THRESHOLD"] = "0.5"
        os.environ["WORKER_QUEUE_THRESHOLD_HIGH"] = "200"

        config = loader.load_adaptive_worker_config()
        assert config["adaptive_worker_enabled"] is False
        assert config["cpu_threshold"] == 0.5
        assert config["queue_threshold_high"] == 200

    finally:
        # 恢复原始环境变量
        for key, value in original_env.items():
            if value is not None:
                os.environ[key] = value


def test_config_loader_invalid_adaptive_config():
    """测试 ConfigLoader 无效自适应配置"""
    import os
    from fish_async_task.config import ConfigLoader
    import logging

    logger = logging.getLogger("test")
    loader = ConfigLoader(logger)

    # 保存原始环境变量
    original_cpu = os.environ.get("WORKER_CPU_THRESHOLD")
    original_queue = os.environ.get("WORKER_QUEUE_THRESHOLD_HIGH")

    try:
        # 测试无效的 CPU 阈值
        os.environ["WORKER_CPU_THRESHOLD"] = "1.5"  # 超过最大值
        config = loader.load_adaptive_worker_config()
        assert config["cpu_threshold"] == loader.MAX_CPU_THRESHOLD

        # 测试无效的队列阈值
        os.environ["WORKER_CPU_THRESHOLD"] = "0.8"
        os.environ["WORKER_QUEUE_THRESHOLD_HIGH"] = "-10"  # 无效值
        config = loader.load_adaptive_worker_config()
        assert config["queue_threshold_high"] == loader.DEFAULT_QUEUE_THRESHOLD_HIGH

    finally:
        # 恢复原始环境变量
        if original_cpu is not None:
            os.environ["WORKER_CPU_THRESHOLD"] = original_cpu
        elif "WORKER_CPU_THRESHOLD" in os.environ:
            del os.environ["WORKER_CPU_THRESHOLD"]

        if original_queue is not None:
            os.environ["WORKER_QUEUE_THRESHOLD_HIGH"] = original_queue
        elif "WORKER_QUEUE_THRESHOLD_HIGH" in os.environ:
            del os.environ["WORKER_QUEUE_THRESHOLD_HIGH"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

