# FishAsyncTask 高级使用指南

本文档提供 FishAsyncTask 的高级使用示例和最佳实践。

## 目录

1. [多实例管理](#1-多实例管理)
2. [任务优先级](#2-任务优先级)
3. [任务依赖管理](#3-任务依赖管理)
4. [任务取消](#4-任务取消)
5. [性能监控](#5-性能监控)
6. [资源管理](#6-资源管理)
7. [配置热重载](#7-配置热重载)

---

## 1. 多实例管理

使用不同的 `instance_key` 创建独立的任务管理器实例：

```python
from fish_async_task import TaskManager

# 默认实例（所有调用共享）
default_manager = TaskManager()

# 订单模块独立实例
order_manager = TaskManager(instance_key="order")

# 支付模块独立实例
payment_manager = TaskManager(instance_key="payment")

# 通知模块独立实例
notification_manager = TaskManager(instance_key="notification")

# 每个实例独立配置和工作
order_manager.submit_task(process_order, order_id=123)
payment_manager.submit_task(process_payment, payment_id=456)
notification_manager.submit_task(send_notification, user_id=789)

# 关闭特定实例
order_manager.shutdown()
payment_manager.shutdown()
notification_manager.shutdown()
default_manager.shutdown()
```

---

## 2. 任务优先级

使用优先级队列让高优先级任务优先执行：

```python
from fish_async_task.performance import PriorityTaskQueue
import queue

# 创建优先级队列
pq = PriorityTaskQueue(maxsize=1000)

# 定义任务
def critical_task(data):
    return f"Critical: {data}"

def normal_task(data):
    return f"Normal: {data}"

def low_priority_task(data):
    return f"Low: {data}"

# 提交任务（priority 数字越小优先级越高）
task_id_1 = pq.submit(critical_task, priority=1, data="紧急订单")
task_id_2 = pq.submit(normal_task, priority=5, data="普通订单")
task_id_3 = pq.submit(low_priority_task, priority=10, data="后台任务")

# 获取最高优先级任务
while not pq.empty():
    task = pq.get()
    print(f"处理任务: {task.task_id}, 优先级: {task.priority}")
```

---

## 3. 任务依赖管理

管理任务之间的依赖关系：

```python
from fish_async_task.performance import TaskDependencyManager

# 创建依赖管理器
dep_manager = TaskDependencyManager()

# 添加任务依赖
dep_manager.add_dependency("task_B", ["task_A"])  # B 依赖 A
dep_manager.add_dependency("task_C", ["task_A", "task_B"])  # C 依赖 A 和 B

# 检查依赖是否满足
if dep_manager.is_ready("task_B"):
    print("Task B 可以执行")

# 标记任务完成
dep_manager.mark_completed("task_A")
dep_manager.mark_completed("task_B")

# 获取所有可执行任务
ready_tasks = dep_manager.get_ready_tasks()
print(f"可执行任务: {ready_tasks}")
```

---

## 4. 任务取消

支持协作式任务取消：

```python
import time
from fish_async_task.performance import TaskCancellationManager, CancelEvent

# 创建取消管理器
cancel_manager = TaskCancellationManager()

# 定义支持取消的任务
def long_running_task(cancel_event=None):
    result = []
    for i in range(100):
        if cancel_event and cancel_event.is_cancelled():
            return "任务已取消"
        result.append(i)
        time.sleep(0.1)
    return result

# 注册任务
cancel_event = cancel_manager.register_task(
    "long_task",
    long_running_task
)

# 启动任务
import threading
task_thread = threading.Thread(target=lambda: long_running_task(cancel_event))
task_thread.start()

# 取消任务
time.sleep(1)  # 让任务运行一会儿
cancel_manager.cancel_task("long_task")

print(f"任务状态: {cancel_manager.get_stats()}")
```

---

## 5. 性能监控

实时监控系统性能：

```python
from fish_async_task.performance import PerformanceMetrics, SystemHealthMonitor

# 创建性能指标收集器
metrics = PerformanceMetrics(max_history=1000)

# 记录任务指标
metrics.record_task_submitted()
metrics.record_task_completed(execution_time=0.5, queue_wait_time=0.1)

# 获取指标
current_metrics = metrics.get_metrics()
print(f"任务完成数: {current_metrics['tasks_completed']}")
print(f"成功率: {current_metrics['success_rate']}")
print(f"平均执行时间: {current_metrics['avg_execution_time_seconds']}")

# 获取百分位数
percentiles = metrics.get_percentiles([50, 90, 95, 99])
print(f"P50: {percentiles['p50']}")
print(f"P99: {percentiles['p99']}")

# 创建健康监控器
health_monitor = SystemHealthMonitor()

# 更新健康状态
health_status = health_monitor.update_health_status(current_metrics)
print(f"系统状态: {health_status['overall_status']}")
```

---

## 6. 资源管理

跟踪和管理任务资源：

```python
from fish_async_task.performance import TaskResourceManager

# 创建资源管理器
resource_manager = TaskResourceManager(max_tracked=1000)
resource_manager.start()

# 模拟打开文件资源
class MockFile:
    def close(self):
        print("文件已关闭")

# 注册任务资源
resource_manager.register_resource(
    task_id="task_1",
    resource_id="file_1",
    resource=MockFile(),
    cleanup_func=lambda: print("清理文件")
)

# 清理任务资源
resource_manager.cleanup_task_resources("task_1")

# 获取统计信息
stats = resource_manager.get_stats()
print(f"跟踪的资源数: {stats['total_resources']}")

# 停止资源管理器
resource_manager.stop()
```

---

## 7. 配置热重载

支持运行时配置热重载：

```python
import os
from fish_async_task.config import HotReloadConfig

# 创建热重载配置管理器
config = HotReloadConfig(reload_interval=60)

# 注册配置项
config.register_config(
    key="MAX_WORKERS",
    parser=lambda: int(os.getenv("MAX_WORKERS", "10")),
    default=10
)

config.register_config(
    key="QUEUE_SIZE",
    parser=lambda: int(os.getenv("QUEUE_SIZE", "1000")),
    default=1000
)

# 获取配置（使用缓存）
max_workers = config.get("MAX_WORKERS")
queue_size = config.get("QUEUE_SIZE")

# 手动触发重载
reloaded_count = config.reload()
print(f"重载了 {reloaded_count} 个配置项")

# 获取所有配置
all_config = config.get_all()
print(f"所有配置: {all_config}")

# 清除缓存
config.clear_cache()
```

---

## 8. 综合示例

```python
from fish_async_task import TaskManager
from fish_async_task.performance import (
    PerformanceMetrics,
    SystemHealthMonitor,
    TaskResourceManager,
)

# 创建任务管理器
manager = TaskManager()

# 创建监控组件
metrics = PerformanceMetrics()
health_monitor = SystemHealthMonitor()
resource_manager = TaskResourceManager()
resource_manager.start()

# 定义任务
def process_order(order_id, resource_manager=None):
    if resource_manager:
        resource_manager.register_task(order_id)
    # 模拟处理
    return f"订单 {order_id} 处理完成"

# 提交任务
for i in range(100):
    task_id = manager.submit_task(
        process_order,
        order_id=f"ORDER_{i}",
        resource_manager=resource_manager
    )
    metrics.record_task_submitted()

# 等待任务完成
import time
time.sleep(5)

# 获取性能指标
perf_metrics = metrics.get_metrics()
print(f"任务完成: {perf_metrics['tasks_completed']}")
print(f"成功率: {perf_metrics['success_rate']:.2%}")

# 检查健康状态
health = health_monitor.update_health_status(perf_metrics)
print(f"系统状态: {health['overall_status']}")

# 清理资源
resource_manager.stop()
manager.shutdown()
```

---

## 最佳实践

1. **使用单例模式**: 默认实例适用于大多数场景
2. **配置监控**: 生产环境建议启用性能监控
3. **资源清理**: 始终在 shutdown 时清理资源
4. **错误处理**: 使用 try-except 捕获任务异常
5. **超时控制**: 为长时间运行的任务设置超时
6. **优先级调度**: 关键任务使用高优先级

---

## 性能调优建议

| 配置项 | 默认值 | 建议值 | 说明 |
|--------|--------|--------|------|
| `max_workers` | CPU×4 | CPU×4~8 | 根据任务类型调整 |
| `queue_size` | 1000 | 1000~5000 | 队列大小 |
| `cleanup_interval` | 300s | 60~300s | 清理频率 |
| `task_timeout` | None | 300~3600s | 任务超时 |

---

如需更多信息，请参阅：
- [API 文档](API.md)
- [配置文档](CONFIG.md)
- [最佳实践](BEST_PRACTICES.md)
