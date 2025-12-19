# 最佳实践

## 1. 任务函数设计

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

## 2. 错误处理

```python
# 检查任务状态并处理错误
status = task_manager.get_task_status(task_id)
if status:
    if status['status'] == 'failed':
        error = status.get('error', '未知错误')
        # 根据错误类型进行处理
        handle_error(task_id, error)
```

## 3. 资源清理

```python
import atexit

# 注册退出处理函数
def cleanup():
    task_manager.shutdown()

atexit.register(cleanup)
```

## 4. 多实例使用场景

```python
# 不同业务模块使用独立实例，避免相互影响
order_manager = TaskManager(instance_key="order")
payment_manager = TaskManager(instance_key="payment")
notification_manager = TaskManager(instance_key="notification")
```

## 5. 性能优化

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
8. **任务超时限制**：由于 Python GIL 的限制，当任务超时时，虽然会抛出 `TimeoutError` 并标记任务为失败，但任务线程仍在后台运行。这可能导致资源泄漏（文件句柄、网络连接等）。建议：
   - 在任务函数中使用上下文管理器（`with` 语句）管理资源
   - 在任务函数中定期检查超时标志
   - 对于长时间运行的任务，考虑使用进程池而非线程池

