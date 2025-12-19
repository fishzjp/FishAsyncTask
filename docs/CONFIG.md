# 配置文档

## 环境变量配置

可以通过环境变量配置任务管理器：

| 环境变量 | 说明 | 默认值 | 示例 |
|---------|------|--------|------|
| `TASK_STATUS_TTL` | 任务状态TTL（秒），超过此时间的任务状态会被自动清理 | 3600（1小时） | `export TASK_STATUS_TTL=7200` |
| `MAX_TASK_STATUS_COUNT` | 最大任务状态数量，超过此数量会触发清理 | 10000 | `export MAX_TASK_STATUS_COUNT=20000` |
| `TASK_CLEANUP_INTERVAL` | 清理间隔（秒），定期清理过期任务状态 | 300（5分钟） | `export TASK_CLEANUP_INTERVAL=600` |
| `TASK_TIMEOUT` | 任务执行超时时间（秒），超过此时间任务会被标记为失败 | 无限制 | `export TASK_TIMEOUT=300` |
| `TASK_STATUS_SHARD_COUNT` | 任务状态存储的分片数量，用于优化并发性能 | 16 | `export TASK_STATUS_SHARD_COUNT=32` |

**示例：**
```bash
# 设置任务状态保留2小时
export TASK_STATUS_TTL=7200

# 设置任务超时为5分钟
export TASK_TIMEOUT=300

# 运行程序
python your_app.py
```

## 默认配置

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

