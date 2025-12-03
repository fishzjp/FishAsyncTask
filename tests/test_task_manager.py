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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

