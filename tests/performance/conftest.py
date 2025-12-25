"""
性能测试共享配置和 fixture

提供性能测试所需的通用配置、fixture 和工具函数。
"""

import pytest
import time
import os
from typing import Any, Dict, Optional


# 测试配置常量
class TestConfig:
    """性能测试配置"""
    
    # 任务数量配置
    TASK_COUNT_SMALL = 1000      # 小规模测试
    TASK_COUNT_MEDIUM = 5000     # 中等规模测试
    TASK_COUNT_LARGE = 10000     # 大规模测试
    
    # 并发配置
    CONCURRENT_THREADS_SMALL = 50
    CONCURRENT_THREADS_MEDIUM = 100
    CONCURRENT_THREADS_LARGE = 200
    
    # 任务执行时间（秒）
    TASK_EXECUTION_TIME_FAST = 0.001    # 1ms 快速任务
    TASK_EXECUTION_TIME_NORMAL = 0.01   # 10ms 正常任务
    TASK_EXECUTION_TIME_SLOW = 0.1      # 100ms 慢速任务
    
    # TTL 配置（秒）
    SHORT_TTL = 1      # 短 TTL 用于测试清理
    NORMAL_TTL = 3600  # 正常 TTL
    
    # 批量更新配置
    BATCH_SIZE = 100
    BATCH_FLUSH_INTERVAL = 0.1
    
    # 超时配置（秒）
    TEST_TIMEOUT = 120
    TASK_WAIT_TIMEOUT = 60


@pytest.fixture
def fast_task():
    """快速测试任务（1ms）"""
    def task(value: int) -> int:
        time.sleep(0.001)
        return value * 2
    return task


@pytest.fixture
def normal_task():
    """正常测试任务（10ms）"""
    def task(value: int) -> int:
        time.sleep(0.01)
        return value * 2
    return task


@pytest.fixture
def slow_task():
    """慢速测试任务（100ms）"""
    def task(value: int) -> int:
        time.sleep(0.1)
        return value * 2
    return task


def wait_for_task_completion(task_manager, task_id: str, timeout: float = 30) -> Optional[Dict[str, Any]]:
    """
    等待任务完成
    
    Args:
        task_manager: 任务管理器实例
        task_id: 任务ID
        timeout: 超时时间（秒）
    
    Returns:
        任务状态字典，如果超时则返回 None
    """
    waited = 0
    while waited < timeout:
        status = task_manager.get_task_status(task_id)
        if status and status["status"] in ("completed", "failed"):
            return status
        time.sleep(0.01)
        waited += 0.01
    return None


def wait_for_all_tasks(task_manager, task_ids: list, timeout: float = 60) -> bool:
    """
    等待所有任务完成
    
    Args:
        task_manager: 任务管理器实例
        task_ids: 任务ID列表
        timeout: 超时时间（秒）
    
    Returns:
        如果所有任务在超时前完成返回 True，否则返回 False
    """
    waited = 0
    while waited < timeout:
        all_completed = True
        for task_id in task_ids:
            status = task_manager.get_task_status(task_id)
            if not status or status["status"] not in ("completed", "failed"):
                all_completed = False
                break
        if all_completed:
            return True
        time.sleep(0.05)
        waited += 0.05
    return False


def create_test_tasks(
    task_manager, 
    count: int, 
    task_func, 
    block: bool = True,
    timeout: float = 1.0
) -> list:
    """
    创建测试任务
    
    Args:
        task_manager: 任务管理器实例
        count: 任务数量
        task_func: 任务函数
        block: 是否使用阻塞模式提交
        timeout: 阻塞超时时间
    
    Returns:
        任务ID列表
    """
    task_ids = []
    for i in range(count):
        try:
            if block:
                task_id = task_manager.submit_task(task_func, i, block=True, timeout=timeout)
            else:
                task_id = task_manager.submit_task(task_func, i)
            task_ids.append(task_id)
        except Exception as e:
            # 如果队列满，等待一下再尝试
            if block:
                time.sleep(0.01)
                task_id = task_manager.submit_task(task_func, i, block=True, timeout=timeout)
                task_ids.append(task_id)
            else:
                raise
    return task_ids


def cleanup_task_manager_instances():
    """清理任务管理器单例实例"""
    from fish_async_task.task_manager import TaskManager as TaskManagerClass
    TaskManagerClass._instances.clear()


def get_version_info() -> Dict[str, str]:
    """获取当前版本信息"""
    import fish_async_task
    
    return {
        "version": getattr(fish_async_task, "__version__", "unknown"),
        "file": fish_async_task.__file__,
    }


def print_test_header(test_name: str, task_count: int = 0, concurrent: int = 0):
    """打印测试头部信息"""
    print("\n" + "=" * 80)
    print(f"测试: {test_name}")
    print("-" * 80)
    if task_count > 0:
        print(f"任务数量: {task_count}")
    if concurrent > 0:
        print(f"并发线程数: {concurrent}")
    print("-" * 80)


def print_test_footer(elapsed_time: float):
    """打印测试底部信息"""
    print("-" * 80)
    print(f"总耗时: {elapsed_time:.3f}秒")
    print("=" * 80 + "\n")

