# FishAsyncTask

一个纯Python实现的异步任务管理器，支持线程池和动态伸缩。

[![GitHub](https://img.shields.io/github/stars/fishzjp/FishAsyncTask?style=social)](https://github.com/fishzjp/FishAsyncTask)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/)

## 目录

- [特性](#特性)
- [安装](#安装)
- [快速开始](#快速开始)
- [API文档](#api文档)
- [配置](#配置)
- [任务状态](#任务状态)
- [线程管理](#线程管理)
- [最佳实践](#最佳实践)
- [注意事项](#注意事项)
- [使用场景](#使用场景)
- [常见问题](#常见问题)
- [更新日志](#更新日志)
- [许可证](#许可证)
- [贡献](#贡献)

## 特性

- 🚀 **纯Python实现**：无需额外依赖，使用标准库实现
- 🔄 **动态伸缩**：根据任务队列大小自动调整工作线程数量
- 📊 **任务状态追踪**：实时查询任务执行状态和结果
- 🧹 **自动清理**：自动清理过期的任务状态记录
- 🔒 **线程安全**：使用锁机制保证线程安全
- 🎯 **单例模式**：支持多实例管理，不同业务模块可使用独立实例
- ⏱️ **任务超时**：支持配置任务执行超时时间
- 🚦 **队列控制**：支持阻塞和非阻塞两种任务提交模式

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install fish-async-task
```

### 从 GitHub 安装

```bash
pip install git+https://github.com/fishzjp/FishAsyncTask.git
```

### 开发模式安装

```bash
git clone https://github.com/fishzjp/FishAsyncTask.git
cd FishAsyncTask
pip install -e .
```


## 快速开始

### 基本使用

```python
from fish_async_task import TaskManager
import time

# 创建任务管理器实例（单例模式）
task_manager = TaskManager()

# 定义一个任务函数
def my_task(name: str, value: int):
    print(f"执行任务: {name}, 值: {value}")
    time.sleep(1)  # 模拟耗时操作
    return f"任务完成: {name}"

# 提交任务（非阻塞模式）
task_id = task_manager.submit_task(my_task, "任务1", value=100)
print(f"任务ID: {task_id}")

# 等待任务完成并查询状态
while True:
    status = task_manager.get_task_status(task_id)
    if status:
        if status["status"] == "completed":
            print(f"任务完成，结果: {status.get('result')}")
            break
        elif status["status"] == "failed":
            print(f"任务失败: {status.get('error')}")
            break
    time.sleep(0.1)

# 关闭任务管理器
task_manager.shutdown()
```

### 阻塞模式提交任务

当队列已满时，可以使用阻塞模式等待队列有空间：

```python
# 阻塞模式提交任务（等待队列有空间）
task_id = task_manager.submit_task(
    my_task, 
    "任务2", 
    value=200,
    block=True,        # 启用阻塞模式
    timeout=10.0      # 最多等待10秒
)
```

### 多实例管理

不同业务模块可以使用独立的任务管理器实例：

```python
# 默认实例
default_manager = TaskManager()

# 订单模块的独立实例
order_manager = TaskManager(instance_key="order")

# 支付模块的独立实例
payment_manager = TaskManager(instance_key="payment")
```


## API文档

### TaskManager

#### 初始化

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

#### 方法

##### submit_task(func, *args, block=False, timeout=None, **kwargs) -> str

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

##### get_task_status(task_id: str) -> Optional[Dict[str, Any]]

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

##### clear_task_status(task_id: Optional[str] = None) -> None

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

##### shutdown() -> None

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

### TaskQueueFullError

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

## 配置

### 环境变量配置

可以通过环境变量配置任务管理器：

| 环境变量 | 说明 | 默认值 | 示例 |
|---------|------|--------|------|
| `TASK_STATUS_TTL` | 任务状态TTL（秒），超过此时间的任务状态会被自动清理 | 3600（1小时） | `export TASK_STATUS_TTL=7200` |
| `MAX_TASK_STATUS_COUNT` | 最大任务状态数量，超过此数量会触发清理 | 10000 | `export MAX_TASK_STATUS_COUNT=20000` |
| `TASK_CLEANUP_INTERVAL` | 清理间隔（秒），定期清理过期任务状态 | 300（5分钟） | `export TASK_CLEANUP_INTERVAL=600` |
| `TASK_TIMEOUT` | 任务执行超时时间（秒），超过此时间任务会被标记为失败 | 无限制 | `export TASK_TIMEOUT=300` |

**示例：**
```bash
# 设置任务状态保留2小时
export TASK_STATUS_TTL=7200

# 设置任务超时为5分钟
export TASK_TIMEOUT=300

# 运行程序
python your_app.py
```

### 默认配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEFAULT_QUEUE_SIZE` | 1000 | 任务队列大小 |
| `DEFAULT_MIN_WORKERS` | 1 | 最小工作线程数 |
| `DEFAULT_MAX_WORKERS` | `max(4, CPU核心数 * 4)` | 最大工作线程数 |
| `DEFAULT_IDLE_TIMEOUT` | 60秒 | 空闲线程超时时间 |
| `DEFAULT_TASK_STATUS_TTL` | 3600秒 | 任务状态TTL |
| `DEFAULT_MAX_TASK_STATUS_COUNT` | 10000 | 最大任务状态数量 |
| `DEFAULT_CLEANUP_INTERVAL` | 300秒 | 清理间隔 |
| `DEFAULT_THREAD_JOIN_TIMEOUT` | 2秒 | 线程join超时时间 |
| `DEFAULT_TASK_TIMEOUT` | `None`（无限制） | 任务执行超时时间 |

## 任务状态

任务状态有以下几种：

| 状态 | 说明 | 可获取字段 |
|------|------|-----------|
| `pending` | 任务已提交，等待执行 | `status`, `submit_time` |
| `running` | 任务正在执行 | `status`, `submit_time`, `start_time` |
| `completed` | 任务执行完成 | `status`, `submit_time`, `start_time`, `end_time`, `result` |
| `failed` | 任务执行失败 | `status`, `submit_time`, `start_time`, `end_time`, `error` |

**状态流转：**
```
pending → running → completed
                  ↘ failed
```

**示例：**
```python
status = task_manager.get_task_status(task_id)
if status:
    print(f"状态: {status['status']}")
    if status['status'] == 'completed':
        print(f"结果: {status.get('result')}")
    elif status['status'] == 'failed':
        print(f"错误: {status.get('error')}")
```

## 线程管理

任务管理器使用动态线程池：

- **初始启动**：启动最小工作线程数（默认1个）
- **动态扩展**：当队列中的任务数量超过当前线程数时，自动创建新线程
- **自动回收**：空闲线程在超过空闲超时时间（默认60秒）后自动退出
- **数量限制**：线程数量在最小和最大工作线程数之间动态调整
- **守护线程**：所有工作线程都是守护线程，程序退出时会自动清理

**线程数量计算：**
- 最小线程数：`DEFAULT_MIN_WORKERS`（默认1）
- 最大线程数：`max(4, CPU核心数 * 4)`
- 实际线程数：根据队列大小动态调整，在最小和最大之间

## 最佳实践

### 1. 任务函数设计

- ✅ **线程安全**：确保任务函数是线程安全的，避免共享可变状态
- ✅ **异常处理**：在任务函数内部处理异常，或让异常自然抛出（会被捕获并记录）
- ✅ **幂等性**：如果可能，设计幂等任务，支持重试

```python
def safe_task(data: dict):
    """线程安全的任务函数示例"""
    try:
        # 处理数据（使用局部变量，避免共享状态）
        result = process_data(data.copy())
        return result
    except Exception as e:
        # 记录错误或重新抛出
        logger.error(f"任务执行失败: {e}")
        raise
```

### 2. 错误处理

```python
# 检查任务状态并处理错误
status = task_manager.get_task_status(task_id)
if status:
    if status['status'] == 'failed':
        error = status.get('error', '未知错误')
        # 根据错误类型进行处理
        handle_error(task_id, error)
```

### 3. 资源清理

```python
import atexit

# 注册退出处理函数
def cleanup():
    task_manager.shutdown()

atexit.register(cleanup)
```

### 4. 多实例使用场景

```python
# 不同业务模块使用独立实例，避免相互影响
order_manager = TaskManager(instance_key="order")
payment_manager = TaskManager(instance_key="payment")
notification_manager = TaskManager(instance_key="notification")
```

### 5. 性能优化

- 根据实际负载调整 `TASK_STATUS_TTL` 和 `MAX_TASK_STATUS_COUNT`
- 对于长时间运行的任务，考虑设置 `TASK_TIMEOUT`
- 监控队列大小，避免队列积压

## 注意事项

1. **线程安全**：任务函数应该是线程安全的，避免共享可变状态
2. **异常处理**：任务函数中的异常会被捕获并记录，不会影响其他任务
3. **守护线程**：任务管理器使用守护线程，程序退出时会自动清理
4. **优雅关闭**：建议在程序退出前调用 `shutdown()` 方法优雅关闭
5. **队列大小**：注意队列大小限制（默认1000），避免任务提交失败
6. **状态清理**：任务状态会自动清理，不要依赖长期存在的状态
7. **单例模式**：相同 `instance_key` 的 `TaskManager` 是同一个实例，修改会影响所有引用

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

- GitHub 仓库: https://github.com/fishzjp/FishAsyncTask
- 问题反馈: https://github.com/fishzjp/FishAsyncTask/issues

## 使用场景

- 📦 **后台任务处理**：异步处理耗时操作，不阻塞主流程
- 🔄 **批量数据处理**：并发处理大量数据，提高处理效率
- 📧 **消息队列**：作为轻量级消息队列使用
- 🎯 **任务调度**：配合定时任务实现任务调度
- 🔌 **API异步处理**：Web API中异步处理请求

## 常见问题

### Q: 任务提交失败怎么办？

A: 如果队列已满，可以：
1. 使用阻塞模式：`submit_task(func, *args, block=True, timeout=10.0)`
2. 增加队列大小（需要修改代码）
3. 检查是否有任务积压，优化任务执行速度

### Q: 如何监控任务执行情况？

A: 可以定期查询任务状态：
```python
status = task_manager.get_task_status(task_id)
# 根据状态进行监控和告警
```

### Q: 任务状态会被保留多久？

A: 默认保留1小时（3600秒），可以通过 `TASK_STATUS_TTL` 环境变量配置。

### Q: 如何设置任务超时？

A: 通过 `TASK_TIMEOUT` 环境变量设置，例如：`export TASK_TIMEOUT=300`（5分钟超时）。

## 更新日志

### 0.1.0 (2025-12-03)

- ✨ 初始版本发布
- ✨ 支持基本的任务提交和状态查询
- ✨ 支持动态线程池和自动伸缩
- ✨ 支持任务状态自动清理
- ✨ 支持单例模式和多实例管理
- ✨ 支持任务超时配置
- ✨ 支持阻塞和非阻塞两种提交模式

