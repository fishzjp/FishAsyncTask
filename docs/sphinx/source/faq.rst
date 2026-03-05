常见问题
========

安装问题
---------

Q: 安装时提示编译错误？
~~~~~~~~~~~~~~~~~~~~~~~

A: FishAsyncTask 默认包含预编译的 Rust 核心模块，支持主流平台。如果遇到编译错误，可能是你的平台不在支持列表中。解决方案::

    # 使用纯 Python 版本（性能较低）
    pip install fish-async-task --no-binary fish-async-task

Q: 如何确认 Rust 核心已启用？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A: 运行以下命令::

    python -c "from fish_async_task._rust import is_rust_available; print(f'Rust 核心: {is_rust_available()}')"

    应该输出：Rust 核心: True

Q: 如何确认安装成功？
~~~~~~~~~~~~~~~~~~~~~

A: 运行以下命令::

    python -c "import fish_async_task; print(fish_async_task.__version__)"

    应该输出当前版本号，如 0.3.0

使用问题
---------

Q: 如何选择合适的工作线程数？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A: 根据任务类型选择：

* **I/O 密集型**（网络请求、文件读写）：max_workers = CPU核心数 * 2 到 4
* **CPU 密集型**（计算密集）：max_workers = CPU核心数
* **混合型**：先从小规模测试开始，逐步调整

查看 CPU 核心数::

    import os
    print(os.cpu_count())

Q: 任务提交失败，提示队列已满？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A: 有两种解决方案：

1. **增加队列大小**::

    manager = TaskManager(queue_size=2000)  # 默认 1000

2. **阻塞等待队列有空位**::

    task_id = manager.submit_task(
        func,
        block=True,      # 等待队列有空位
        timeout=30,      # 最多等待 30 秒
    )

Q: 如何处理长时间运行的任务？
~~~~~~~~~~~~~~~~~~~~~~~~~~~

A: 有几种策略：

1. **设置任务超时**::

    task_id = manager.submit_task(
        long_running_task,
        timeout=3600,  # 1 小时超时
    )

2. **使用回调处理结果**::

    def on_complete(task_id, result):
        print(f"任务 {task_id} 完成: {result}")

    task_id = manager.submit_task(
        long_running_task,
        on_complete=on_complete,
    )

3. **定期检查状态**::

    task_id = manager.submit_task(long_running_task)
    # ...
    status = manager.get_task_status(task_id)
    if status["status"] == "completed":
        result = status["result"]

Q: 能否取消正在运行的任务？
~~~~~~~~~~~~~~~~~~~~~~~~~~~

A: 取消任务取决于任务的状态：

* **等待中**：可以立即取消
* **运行中**：无法直接取消，任务会继续执行直到完成或失败

.. code-block:: python

    success = manager.cancel_task(task_id)
    if success:
        print("任务已取消")
    else:
        print("任务无法取消（可能正在运行或已完成）")

Q: 多个 TaskManager 实例会互相影响吗？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A: 使用不同的 instance_key 创建的实例是完全独立的：

.. code-block:: python

    manager1 = TaskManager(instance_key="A")
    manager2 = TaskManager(instance_key="B")
    # 两个实例完全独立，互不影响

相同 instance_key 的实例是同一个单例。

性能问题
---------

Q: 内存占用过高怎么办？
~~~~~~~~~~~~~~~~~~~~~

A: 检查以下几点：

1. **减少任务状态缓存**::

    manager = TaskManager(
        task_status_ttl=1800,         # 30 分钟后清理
        max_task_status_count=5000,   # 最多保留 5000 条
    )

2. **减小队列大小**::

    manager = TaskManager(queue_size=500)

3. **减少工作线程数**::

    manager = TaskManager(max_workers=8)

Q: 如何提升性能？
~~~~~~~~~~~~~~~

A: 根据瓶颈选择方案：

1. **启用 Rust 扩展**（实验性）::

    pip install fish-async-task[performance]

2. **使用批量更新**::

    manager = TaskManager(
        batch_update=True,
        batch_update_interval=1,
    )

3. **启用分片状态存储**::

    from fish_async_task.performance import ShardedStatusManager
    status_manager = ShardedStatusManager(num_shards=16)

4. **调整工作线程数**::

    # 增加工作线程
    manager = TaskManager(max_workers=16)

Q: 任务执行速度很慢？
~~~~~~~~~~~~~~~~~

A: 排查步骤：

1. **检查工作线程数**::

    print(f"工作线程数: {manager.get_worker_count()}")

2. **检查任务是否真的在并行执行**::

    # 查看运行中的任务
    running = manager.get_tasks_by_status("running")
    print(f"运行中任务: {len(running)}")

3. **检查是否有 GIL 限制**（CPU 密集型任务）::

    # 考虑使用多进程替代多线程
    from multiprocessing import Pool

错误处理
---------

Q: 任务失败后如何重试？
~~~~~~~~~~~~~~~~~~~~~

A: FishAsyncTask 不内置重试机制，建议在任务函数中实现：

.. code-block:: python

    from functools import wraps
    import time

    def retry(max_attempts=3, delay=1):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_error = e
                        if attempt < max_attempts - 1:
                            time.sleep(delay * (2 ** attempt))
                raise last_error
            return wrapper
        return decorator

    @retry(max_attempts=3)
    def unreliable_task():
        # 可能失败的任务
        pass

    task_id = manager.submit_task(unreliable_task)

Q: 如何获取任务的错误信息？
~~~~~~~~~~~~~~~~~~~~~~~~~

A: 通过任务状态获取：

.. code-block:: python

    status = manager.get_task_status(task_id)
    if status["status"] == "failed":
        error = status["error"]
        print(f"任务失败: {error}")

最佳实践
----------

Q: 在 Web 应用中如何使用？
~~~~~~~~~~~~~~~~~~~~~~~~~

A: 推荐模式：

.. code-block:: python

    # app.py
    from fish_async_task import TaskManager

    # 创建全局单例
    task_manager = TaskManager(
        min_workers=4,
        max_workers=16,
    )

    # 提交后台任务
    @app.post("/process")
    def start_process():
        task_id = task_manager.submit_task(
            background_job,
            args=(data,),
        )
        return {"task_id": task_id}

    # 查询结果
    @app.get("/result/{task_id}")
    def get_result(task_id: str):
        status = task_manager.get_task_status(task_id)
        return status

    # 应用关闭时清理
    @app.on_event("shutdown")
    def shutdown():
        task_manager.shutdown(wait=True)

Q: 如何处理大量短任务？
~~~~~~~~~~~~~~~~~~~~~

A: 推荐批量处理：

.. code-block:: python

    def process_batch(items):
        # 批量处理
        return [process_item(item) for item in items]

    # 分批提交
    batch_size = 100
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        manager.submit_task(process_batch, args=(batch,))
