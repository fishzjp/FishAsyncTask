# API 文档

## TaskManager

### 初始化

```python
TaskManager(instance_key: str = "default")
```

创建任务管理器实例。使用单例模式，相同的 `instance_key` 会返回同一个实例。

**参数：**
- `instance_key` (可选): 实例键名，默认为 `"default"`。不同的 key 对应不同的单例实例。

**示例：**
```python
# 获取默认实例
manager1 = TaskManager()
manager2 = TaskManager()  # manager1 和 manager2 是同一个实例

# 获取不同业务模块的独立实例
order_manager = TaskManager(instance_key="order")
payment_manager = TaskManager(instance_key="payment")  # 独立的实例
```

### 方法

#### submit_task(func, *args, block=False, timeout=None, **kwargs) -> str

提交任务到任务队列。

**参数：**
- `func`: 要执行的任务函数
- `*args`: 任务函数的位置参数
- `block` (可选): 如果队列已满，是否阻塞等待。默认为 `False`
- `timeout` (可选): 阻塞等待的超时时间（秒）。仅在 `block=True` 时有效。如果为 `None`，则无限等待。默认为 `None`
- `**kwargs`: 任务函数的关键字参数

**返回：**
- `str`: 任务ID

**异常：**
- `TaskQueueFullError`: 当队列已满且 `block=False` 时抛出

**示例：**
```python
# 非阻塞模式（默认）
task_id = task_manager.submit_task(my_func, arg1, arg2, kwarg1=value1)

# 阻塞模式，最多等待10秒
task_id = task_manager.submit_task(
    my_func, 
    arg1, 
    block=True, 
    timeout=10.0,
    kwarg1=value1
)
```

#### get_task_status(task_id: str) -> Optional[Dict[str, Any]]

获取任务状态。

**参数：**
- `task_id`: 任务ID

**返回：**
- `Optional[Dict[str, Any]]`: 任务状态字典，包含以下字段：
  - `status`: 任务状态（`"pending"`、`"running"`、`"completed"`、`"failed"`）
  - `submit_time`: 提交时间（时间戳，可选）
  - `start_time`: 开始执行时间（时间戳，可选）
  - `end_time`: 结束时间（时间戳，可选）
  - `result`: 任务结果（仅当 `status` 为 `"completed"` 时存在）
  - `error`: 错误信息（仅当 `status` 为 `"failed"` 时存在）
  
  如果任务不存在或已被清理，则返回 `None`

**示例：**
```python
status = task_manager.get_task_status(task_id)
if status:
    print(f"任务状态: {status['status']}")
    if status['status'] == 'completed':
        print(f"结果: {status.get('result')}")
```

#### clear_task_status(task_id: Optional[str] = None) -> None

清除指定任务状态或所有任务状态。

**参数：**
- `task_id` (可选): 要清除的任务ID。如果为 `None`，则清除所有任务状态。

**注意：**
- 清除任务状态不会影响正在执行的任务
- 清除后，`get_task_status` 将返回 `None`

**示例：**
```python
# 清除指定任务状态
task_manager.clear_task_status(task_id)

# 清除所有任务状态
task_manager.clear_task_status()
```

#### shutdown() -> None

关闭任务管理器，停止所有工作线程，清空任务队列和任务状态。

优雅关闭流程：
1. 清除运行标志，停止接受新任务
2. 发送退出信号给所有工作线程
3. 等待所有工作线程退出
4. 等待清理线程退出
5. 清理所有资源（线程列表、任务状态等）

**注意：**
- 如果多次调用，只有第一次调用会生效
- 建议在程序退出前调用此方法进行优雅关闭

**示例：**
```python
# 程序退出前关闭
task_manager.shutdown()
```

## TaskQueueFullError

任务队列已满异常，当队列已满且使用非阻塞模式提交任务时抛出。

**示例：**
```python
from fish_async_task import TaskManager, TaskQueueFullError

try:
    task_id = task_manager.submit_task(my_func, arg1)
except TaskQueueFullError as e:
    print(f"队列已满: {e}")
    # 可以尝试使用阻塞模式
    task_id = task_manager.submit_task(my_func, arg1, block=True, timeout=10.0)
```

---

## 性能优化模块 (fish_async_task.performance)

### PerformanceMetrics

性能指标收集器，用于收集任务执行指标。

```python
from fish_async_task.performance import PerformanceMetrics

metrics = PerformanceMetrics(max_history=1000)
```

**方法：**

- `record_task_submitted()` - 记录任务提交
- `record_task_completed(execution_time, queue_wait_time)` - 记录任务完成
- `record_task_failed(execution_time, queue_wait_time)` - 记录任务失败
- `record_task_cancelled()` - 记录任务取消
- `get_metrics()` - 获取性能指标
- `get_percentiles([50, 90, 95, 99])` - 获取百分位数

### SystemHealthMonitor

系统健康状态监控器。

```python
from fish_async_task.performance import SystemHealthMonitor

monitor = SystemHealthMonitor()
health = monitor.update_health_status(metrics)
```

### TaskResourceManager

任务资源管理器，用于跟踪和管理任务资源。

```python
from fish_async_task.performance import TaskResourceManager

manager = TaskResourceManager(max_tracked=1000)
manager.start()
```

### PriorityTaskQueue

优先级任务队列，支持优先级排序。

```python
from fish_async_task.performance import PriorityTaskQueue
from fish_async_task.performance.priority_queue import PrioritizedTask

pq = PriorityTaskQueue(maxsize=100)
task = PrioritizedTask(priority=1, task_id="task_1", func=my_func, args=(), kwargs={})
pq.put(task)
```

### TaskDependencyManager

任务依赖管理器。

```python
from fish_async_task.performance import TaskDependencyManager

dep_manager = TaskDependencyManager()
dep_manager.add_dependency("task_B", ["task_A"])
dep_manager.mark_completed("task_A")
print(dep_manager.is_ready("task_B"))  # True
```

### TaskCancellationManager

任务取消管理器。

```python
from fish_async_task.performance import TaskCancellationManager

cancel_manager = TaskCancellationManager()
event = cancel_manager.register_task("task_1", my_func)
# 在任务中检查 cancel_event.is_cancelled()
cancel_manager.cancel_task("task_1")
```

---

## 配置管理 (fish_async_task.config)

### HotReloadConfig

支持热重载的配置管理器。

```python
from fish_async_task.config import HotReloadConfig
import os

config = HotReloadConfig(reload_interval=60)
config.register_config("MAX_WORKERS", lambda: int(os.getenv("MAX_WORKERS", "10")), 10)
value = config.get("MAX_WORKERS")
```

### validate_config

配置验证装饰器。

```python
from fish_async_task.config import validate_config

@validate_config(min_value=1, max_value=100, default=10)
def get_queue_size():
    return int(os.getenv("QUEUE_SIZE", "10"))

