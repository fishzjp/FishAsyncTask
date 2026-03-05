最佳实践
========

资源管理
--------

使用上下文管理器
~~~~~~~~~~~~~~~~

**推荐**：使用 ``with`` 语句确保资源正确释放：

.. code-block:: python

    # 推荐
    with TaskManager(min_workers=4) as manager:
        task_id = manager.submit_task(some_task)
        result = manager.get_task_result(task_id)
    # 自动清理资源

    # 不推荐
    manager = TaskManager(min_workers=4)
    task_id = manager.submit_task(some_task)
    # 如果忘记调用 shutdown()，资源可能泄漏

合理设置工作线程数
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import os

    # 根据 CPU 核心数设置
    cpu_count = os.cpu_count()

    # I/O 密集型任务：可以设置更多线程
    io_manager = TaskManager(
        min_workers=cpu_count * 2,
        max_workers=cpu_count * 4,
    )

    # CPU 密集型任务：线程数不宜过多
    cpu_manager = TaskManager(
        min_workers=cpu_count,
        max_workers=cpu_count,
    )

队列大小设置
~~~~~~~~~~~~

.. code-block:: python

    # 根据任务特性和内存限制设置队列大小
    manager = TaskManager(
        queue_size=1000,  # 适中的队列大小
        # 队列过大会占用过多内存
        # 队列过小会导致任务提交阻塞
    )

任务设计
--------

任务函数幂等性
~~~~~~~~~~~~~~

**重要**：确保任务函数可以安全地重试：

.. code-block:: python

    # 好的：幂等操作
    def process_user(user_id):
        user = get_user(user_id)
        if user.status != "processed":
            user.status = "processed"
            user.save()

    # 不好的：非幂等操作
    def process_user_bad(user_id):
        user = get_user(user_id)
        user.process_count += 1  # 重复执行会累加
        user.save()

避免共享状态
~~~~~~~~~~~~

.. code-block:: python

    # 好的：任务独立
    def process_item(item):
        result = item.value * 2
        return result

    # 不好的：共享可变状态
    counter = 0
    def process_item_bad(item):
        global counter
        counter += 1  # 线程不安全
        return item.value * counter

    # 如果需要共享状态，使用线程安全的方式
    from threading import Lock
    counter_lock = Lock()
    counter = 0

    def process_item_safe(item):
        with counter_lock:
            nonlocal counter
            counter += 1
        return item.value * counter

错误处理
--------

任务内部错误处理
~~~~~~~~~~~~~~~~

.. code-block:: python

    # 好的：任务内部处理预期错误
    def fetch_data(url):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"获取数据失败: {url}, 错误: {e}")
            return None  # 返回默认值

    # 不好的：所有错误都抛出
    def fetch_data_bad(url):
        response = requests.get(url)  # 可能超时
        return response.json()

重试策略
~~~~~~~~

.. code-block:: python

    from functools import wraps
    import time

    def retry(max_attempts=3, delay=1):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if attempt == max_attempts - 1:
                            raise
                        time.sleep(delay * (attempt + 1))
            return wrapper
        return decorator

    @retry(max_attempts=3, delay=2)
    def unstable_task():
        # 可能失败的任务
        pass

性能优化
--------

批量处理
~~~~~~~~

.. code-block:: python

    # 好的：批量处理
    def process_batch(items):
        results = []
        for item in items:
            results.append(process_item(item))
        return results

    # 提交批量任务
    batch_size = 100
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        manager.submit_task(process_batch, args=(batch,))

    # 不好的：逐个提交大量小任务
    for item in items:
        manager.submit_task(process_item, args=(item,))

避免阻塞操作
~~~~~~~~~~~~

.. code-block:: python

    # 如果任务中有长时间阻塞操作，考虑异步化
    import asyncio

    def async_task_wrapper():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(async_operation())

    task_id = manager.submit_task(async_task_wrapper)

监控与调试
----------

任务追踪
~~~~~~~~

.. code-block:: python

    def trace_task(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            start = time.time()
            try:
                result = func(*args, **kwargs)
                logger.info(f"{func.__name__} 完成，耗时: {time.time() - start:.2f}s")
                return result
            except Exception as e:
                logger.error(f"{func.__name__} 失败: {e}")
                raise
        return wrapper

    @trace_task
    def my_task(data):
        # 任务逻辑
        pass

定期清理
~~~~~~~~

.. code-block:: python

    # 启用定期清理过期的任务状态
    manager = TaskManager(
        task_status_ttl=3600,         # 1小时后清理
        max_task_status_count=10000,  # 最多保留 10000 条
        cleanup_interval=300,         # 每 5 分钟清理一次
    )

测试
----

可测试性
~~~~~~~~

.. code-block:: python

    # 设计可测试的任务函数
    def process_order(order_id, payment_service=None):
        if payment_service is None:
            payment_service = PaymentService()

        # 业务逻辑
        result = payment_service.process(order_id)
        return result

    # 测试时可以注入 mock
    def test_process_order():
        mock_service = MockPaymentService()
        result = process_order("123", payment_service=mock_service)
        assert result["status"] == "success"

部署建议
--------

生产环境配置
~~~~~~~~~~~~

.. code-block:: python

    # 生产环境推荐配置
    PROD_MANAGER = TaskManager(
        # 工作线程配置
        min_workers=max(4, os.cpu_count()),
        max_workers=os.cpu_count() * 4,

        # 队列配置
        queue_size=1000,

        # 超时配置
        idle_timeout=300,      # 5 分钟空闲超时
        task_timeout=None,     # 不设置任务超时（根据业务需求）

        # 状态管理
        task_status_ttl=7200,           # 2 小时
        max_task_status_count=50000,    # 最多保留 5 万条
        cleanup_interval=600,           # 10 分钟清理一次

        # 日志配置
        enable_logging=True,
        log_level=logging.INFO,
    )

多进程部署
~~~~~~~~~~

.. code-block:: python

    # 在多进程环境中使用不同的 instance_key
    from multiprocessing import Process

    def worker_process(worker_id):
        manager = TaskManager(instance_key=f"worker-{worker_id}")
        # 处理任务
        manager.shutdown()

    processes = []
    for i in range(4):
        p = Process(target=worker_process, args=(i,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()
