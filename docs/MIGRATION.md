# 性能优化迁移指南

本指南帮助您从旧版本的 FishAsyncTask 迁移到包含性能优化的新版本。

## 概述

新版本提供了以下性能优化功能：

1. **分片任务状态存储**（ShardedTaskStatus）
2. **优先级队列清理**（TaskStatusWithExpiry）
3. **批量状态更新**（BatchedStatusUpdater）
4. **自适应工作线程管理**（AdaptiveWorkerManager）
5. **Cython 编译支持**（可选）

## 向后兼容性

✅ **完全向后兼容** - 所有现有代码无需修改即可继续工作。

新功能是**可选的**，您可以选择性地启用它们。

## 迁移步骤

### 步骤 1：更新代码（无破坏性变更）

现有的代码继续工作，无需任何修改：

```python
from fish_async_task import TaskManager

# 旧代码继续工作
manager = TaskManager()
manager.submit_task(task_id="task-1", func=process_data)
```

### 步骤 2：逐步引入性能优化

#### 2.1 使用分片任务状态存储

**旧方式**：
```python
# 使用默认的任务状态存储（单锁）
manager = TaskManager()
```

**新方式（可选）**：
```python
from fish_async_task.performance import ShardedTaskStatus

# 创建分片存储
task_store = ShardedTaskStatus(shard_count=16)

# 在 TaskManager 中使用
manager = TaskManager(task_status_store=task_store)
```

**性能提升**：
- 查询 QPS: 8,000+
- P99 延迟: < 5ms
- 支持 100+ 并发线程

#### 2.2 使用优先级队列清理

**旧方式**：
```python
# 手动清理过期任务（需要遍历所有任务）
def cleanup_expired_tasks(task_store, ttl):
    current_time = time.time()
    for task_id, status in task_store.items():
        if current_time - status.get("end_time", 0) > ttl:
            del task_store[task_id]
```

**新方式（可选）**：
```python
from fish_async_task.performance import TaskStatusWithExpiry

# 创建优先级队列清理存储
cleanup_store = TaskStatusWithExpiry(ttl=300)

# 添加任务
cleanup_store.add_task("task-1", {"end_time": time.time()})

# 清理过期任务（自动优化）
cleaned_count = cleanup_store.cleanup_expired()
```

**性能提升**：
- 10,000 任务清理: 5.11ms（vs 50-100ms）
- O(k log n) 复杂度（vs O(n)）

#### 2.3 使用批量状态更新

**旧方式**：
```python
# 每次更新都直接写入存储
for task_id in tasks:
    task_store.update_status(task_id, status)
```

**新方式（可选）**：
```python
from fish_async_task.performance import BatchedStatusUpdater

# 创建批量更新器
batch_updater = BatchedStatusUpdater(
    buffer_size=100,
    flush_interval=1.0
)

# 批量排队更新
for task_id in tasks:
    batch_updater.queue_update(task_id, status)

# 自动或手动刷新
batch_updater.flush()
```

**性能提升**：
- 吞吐量: 2,036,861 任务/秒
- 1.90x 性能提升

#### 2.4 使用自适应线程管理

**旧方式**：
```python
# 固定数量的工作线程
worker_count = 5
```

**新方式（可选）**：
```python
from fish_async_task.performance import AdaptiveWorkerManager

# 创建自适应管理器
scaling_manager = AdaptiveWorkerManager(
    min_workers=2,
    max_workers=10,
    queue_threshold=100
)

# 根据工作负载调整线程数
current_workers = 5
queue_size = get_queue_size()

should_scale, reason = scaling_manager.should_scale_up(
    current_workers=current_workers,
    queue_size=queue_size
)

if should_scale:
    add_worker()
```

**功能特性**：
- 智能扩展/缩减决策
- CPU 使用率监控
- 冷却期防抖动

### 步骤 3：验证迁移结果

运行测试确保迁移成功：

```bash
# 运行所有测试
pytest tests/ -v

# 运行性能测试
pytest tests/performance/ -v

# 运行集成测试
pytest tests/integration/ -v
```

### 步骤 4：监控和调优

迁移后，监控以下指标：

1. **性能指标**
   - 任务提交吞吐量
   - 状态查询延迟
   - 内存使用

2. **资源使用**
   - CPU 使用率
   - 线程数量
   - 锁竞争情况

3. **根据实际情况调优**
   - 调整分片数量（默认 16）
   - 调整批量更新缓冲区大小（默认 100）
   - 调整扩展阈值和冷却期

## 配置选项

### 分片配置

```python
from fish_async_task.performance import ShardedTaskStatus

# 调整分片数量
task_store = ShardedTaskStatus(
    shard_count=32  # 默认 16，更多分片 = 更好的并发性能
)
```

### 批量更新配置

```python
from fish_async_task.performance import BatchedStatusUpdater

# 调整批量更新参数
batch_updater = BatchedStatusUpdater(
    buffer_size=200,        # 缓冲区大小（默认 100）
    flush_interval=0.5       # 刷新间隔（默认 1.0 秒）
)
```

### 自适应扩展配置

```python
from fish_async_task.performance import AdaptiveWorkerManager

# 调整扩展参数
manager = AdaptiveWorkerManager(
    min_workers=2,           # 最小线程数
    max_workers=20,          # 最大线程数
    scale_up_cooldown=30.0,  # 扩展冷却期（秒）
    scale_down_cooldown=60.0,# 缩减冷却期（秒）
    cpu_threshold=0.8,       # CPU 使用率阈值
    queue_threshold=100      # 队列大小阈值
)
```

## 常见迁移场景

### 场景 1：低并发应用（< 100 任务/秒）

**建议**：使用默认实现即可，无需特殊优化。

```python
from fish_async_task import TaskManager

manager = TaskManager()
```

### 场景 2：中等并发应用（100-1,000 任务/秒）

**建议**：启用分片存储。

```python
from fish_async_task.performance import ShardedTaskStatus
from fish_async_task import TaskManager

task_store = ShardedTaskStatus(shard_count=16)
manager = TaskManager(task_status_store=task_store)
```

### 场景 3：高并发应用（1,000+ 任务/秒）

**建议**：启用所有性能优化功能。

```python
from fish_async_task.performance import (
    ShardedTaskStatus,
    TaskStatusWithExpiry,
    BatchedStatusUpdater,
    AdaptiveWorkerManager
)

# 分片存储
task_store = ShardedTaskStatus(shard_count=16)

# 批量更新
batch_updater = BatchedStatusUpdater(
    buffer_size=100,
    flush_interval=1.0
)

# 优先级清理
cleanup_store = TaskStatusWithExpiry(ttl=300)

# 自适应扩展
scaling_manager = AdaptiveWorkerManager(
    min_workers=2,
    max_workers=10
)
```

### 场景 4：极致性能需求（10,000+ 任务/秒）

**建议**：编译 Cython 扩展 + 所有性能优化。

```bash
# 编译 Cython 扩展
pip install cython
python setup_cython.py build_ext --inplace
```

```python
# 自动使用 Cython 实现
from fish_async_task.performance import ShardedTaskStatus

store = ShardedTaskStatus()  # 自动使用最佳实现
```

## 回滚计划

如果遇到问题，可以轻松回滚：

### 选项 1：禁用特定优化

```python
# 不使用批量更新，使用直接更新
task_store.update_status(task_id, status)
```

### 选项 2：调整参数降低影响

```python
# 减少分片数量
task_store = ShardedTaskStatus(shard_count=4)  # 而不是 16

# 减少缓冲区大小
batch_updater = BatchedStatusUpdater(buffer_size=10)  # 而不是 100
```

### 选项 3：完全回退到旧版本

```python
# 使用原始实现，不导入任何性能优化模块
from fish_async_task import TaskManager

manager = TaskManager()  # 使用默认实现
```

## 性能对比

| 场景 | 旧实现 | 新实现（纯 Python） | 新实现（Cython） |
|------|--------|-------------------|-----------------|
| 查询 QPS | ~1,000 | 8,000+ | 20,000-50,000 |
| 清理 10k 任务 | ~50-100ms | 5.11ms | ~1-2ms |
| 提交吞吐量 | ~100,000 | 2,000,000+ | 5,000,000+ |
| 内存使用 | 基准 | +10% | +5% |

## 故障排除

### 问题 1：性能提升不明显

**可能原因**：
- 应用并发度不高
- 参数配置不当
- 其他瓶颈（I/O、网络）

**解决方案**：
- 使用性能分析工具找到实际瓶颈
- 调整分片数量、缓冲区大小等参数
- 监控系统资源使用

### 问题 2：内存使用增加

**可能原因**：
- 分片数量过多
- 缓冲区大小过大

**解决方案**：
```python
# 减少分片数量
task_store = ShardedTaskStatus(shard_count=8)  # 而不是 16

# 减少缓冲区大小
batch_updater = BatchedStatusUpdater(buffer_size=50)  # 而不是 100
```

### 问题 3：CPU 使用率过高

**可能原因**：
- 批量刷新频率过高
- 自适应扩展过于频繁

**解决方案**：
```python
# 增加刷新间隔
batch_updater = BatchedStatusUpdater(
    flush_interval=2.0  # 增加到 2 秒
)

# 增加冷却期
manager = AdaptiveWorkerManager(
    scale_up_cooldown=60.0,   # 增加扩展冷却期
    scale_down_cooldown=120.0  # 增加缩减冷却期
)
```

## 最佳实践

1. **渐进式迁移**：先在测试环境验证，再逐步推广到生产
2. **监控指标**：迁移前后对比性能指标
3. **参数调优**：根据实际工作负载调整参数
4. **保留回滚选项**：确保可以快速回退

## 相关文档

- [性能优化规格说明](specs/001-performance-optimization/spec.md)
- [Cython 编译指南](docs/CYTHON_INSTALLATION.md)
- [跨平台编译指南](docs/CROSS_PLATFORM_BUILD.md)
- [MVP 验证指南](MVP_VALIDATION.md)

## 支持

如有迁移问题，请：
1. 查看本文档的故障排除部分
2. 查看相关测试文件中的示例
3. 提交 Issue 到 GitHub 仓库
