高级用法
========

多实例管理
-----------

FishAsyncTask 支持通过 ``instance_key`` 创建多个独立的任务管理器实例：

.. code-block:: python

    from fish_async_task import TaskManager

    # 创建不同业务模块的独立管理器
    order_manager = TaskManager(instance_key="order", min_workers=4)
    payment_manager = TaskManager(instance_key="payment", min_workers=2)
    notification_manager = TaskManager(instance_key="notification", min_workers=8)

    # 每个管理器独立运行，互不干扰
    order_task = order_manager.submit_task(process_order)
    payment_task = payment_manager.submit_task(process_payment)
    notify_task = notification_manager.submit_task(send_notification)

    # 分别关闭
    order_manager.shutdown()
    payment_manager.shutdown()
    notification_manager.shutdown()

任务优先级
-----------

使用 PriorityTaskManager 实现基于优先级的任务调度：

.. code-block:: python

    from fish_async_task.performance import PriorityTaskManager

    # 创建优先级队列管理器
    manager = PriorityTaskManager(
        min_workers=4,
        max_workers=16,
    )

    # 提交不同优先级的任务（1-10，10最高）
    manager.submit_task(
        critical_task,
        priority=10,  # 紧急任务
    )

    manager.submit_task(
        normal_task,
        priority=5,  # 普通任务
    )

    manager.submit_task(
        background_task,
        priority=1,  # 后台任务
    )

动态伸缩
--------

TaskManager 会根据负载自动调整工作线程数量：

.. code-block:: python

    from fish_async_task import TaskManager

    manager = TaskManager(
        min_workers=2,      # 最小保持 2 个线程
        max_workers=16,     # 最大扩展到 16 个线程
        idle_timeout=60,    # 空闲线程 60 秒后退出
    )

    # 查看当前工作线程数
    print(f"当前工作线程: {manager.get_worker_count()}")

    # 批量提交任务，管理器会自动扩展
    for i in range(100):
        manager.submit_task(some_task)
    # 此时工作线程数会自动增加

    # 任务完成后，空闲线程会自动退出
    # 等待 60 秒后，线程数会回到 min_workers

任务状态管理
-----------

获取任务详情
~~~~~~~~~~~~

.. code-block:: python

    status = manager.get_task_status(task_id)

    # 状态包含以下信息：
    {
        "task_id": "...",
        "status": "completed",  # pending, running, completed, failed, cancelled
        "result": ...,           # 完成时的结果
        "error": None,           # 失败时的错误信息
        "created_time": 1234567890.0,
        "started_time": 1234567891.0,
        "completed_time": 1234567892.0,
        "worker_id": "worker-1",
    }

按状态查询
~~~~~~~~~~

.. code-block:: python

    # 获取所有等待中的任务
    pending_tasks = manager.get_tasks_by_status("pending")

    # 获取所有运行中的任务
    running_tasks = manager.get_tasks_by_status("running")

    # 获取所有已完成的任务
    completed_tasks = manager.get_tasks_by_status("completed")

    # 获取所有失败的任务
    failed_tasks = manager.get_tasks_by_status("failed")

状态历史
~~~~~~~~

.. code-block:: python

    # 获取所有任务状态
    all_status = manager.get_all_task_status()

    # 统计各状态任务数量
    from collections import Counter
    status_counts = Counter(s["status"] for s in all_status.values())
    print(status_counts)

Rust 核心实现
--------------

FishAsyncTask 默认使用 Rust 核心实现，提供卓越性能：

.. code-block:: python

    from fish_async_task._rust import is_rust_available

    # 检查 Rust 核心是否已启用
    if is_rust_available():
        print("Rust 核心已启用，获得最佳性能")
    else:
        print("使用纯 Python 实现")

性能优势：

* **状态存储** - 使用 Rust 的 DashMap 实现并发安全的状态存储
* **优先级队列** - 基于 Rust 的二叉堆实现，支持高效的入队出队
* **任务依赖** - 使用 Petgraph 图库处理复杂的任务依赖关系
* **批量 API** - 减少跨语言调用开销，提升批量操作性能

性能优化
--------

批量更新
~~~~~~~~

.. code-block:: python

    from fish_async_task.performance import BatchStatusUpdater

    # 使用批量更新减少锁竞争
    manager = TaskManager(
        batch_update=True,        # 启用批量更新
        batch_update_interval=1,  # 每 1 秒批量更新一次
    )

分片状态存储
~~~~~~~~~~~~

.. code-block:: python

    from fish_async_task.performance import ShardedStatusManager

    # 使用分片存储提高并发性能
    status_manager = ShardedStatusManager(num_shards=16)

资源监控
--------

.. code-block:: python

    from fish_async_task.performance import ResourceMonitor

    # 创建资源监控器
    monitor = ResourceMonitor(
        max_memory_mb=1024,      # 最大内存 1GB
        max_cpu_percent=80,      # 最大 CPU 使用率 80%
        check_interval=5,        # 每 5 秒检查一次
    )

    # 启动监控
    monitor.start()

    # 获取当前资源使用情况
    usage = monitor.get_current_usage()
    print(f"内存使用: {usage['memory_mb']} MB")
    print(f"CPU 使用率: {usage['cpu_percent']}%")

    # 停止监控
    monitor.stop()

自适应伸缩
----------

.. code-block:: python

    from fish_async_task.performance import AdaptiveScalingManager

    # 创建自适应伸缩管理器
    scaling_manager = AdaptiveScalingManager(
        base_manager=manager,
        scale_up_threshold=0.8,   # 队列 80% 满时扩容
        scale_down_threshold=0.2, # 队列 20% 满时缩容
        scale_up_step=2,          # 每次增加 2 个线程
        scale_down_step=1,        # 每次减少 1 个线程
    )

    # 启动自适应伸缩
    scaling_manager.start()

    # 根据负载自动调整工作线程数

任务取消
--------

取消等待中的任务
~~~~~~~~~~~~~~~~

.. code-block:: python

    task_id = manager.submit_task(long_running_task)

    # 取消任务
    if manager.cancel_task(task_id):
        print("任务已取消")
    else:
        print("任务无法取消（可能已完成或正在运行）")

取消回调
~~~~~~~~

.. code-block:: python

    def on_cancel(task_id):
        print(f"任务 {task_id} 被取消")

    manager.submit_task(
        long_running_task,
        on_cancel=on_cancel,
    )

监控与日志
----------

获取统计信息
~~~~~~~~~~~~

.. code-block:: python

    stats = manager.get_stats()
    print(f"总任务数: {stats['total_tasks']}")
    print(f"等待中: {stats['pending_count']}")
    print(f"运行中: {stats['running_count']}")
    print(f"已完成: {stats['completed_count']}")
    print(f"失败: {stats['failed_count']}")
    print(f"当前工作线程: {stats['worker_count']}")

自定义日志
~~~~~~~~~~

.. code-block:: python

    import logging

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # TaskManager 会自动使用配置的日志
    manager = TaskManager()

    # 也可以为特定模块配置日志
    task_logger = logging.getLogger("fish_async_task.task_manager")
    task_logger.setLevel(logging.DEBUG)
