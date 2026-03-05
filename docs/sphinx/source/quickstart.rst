快速开始
========

安装
----

从 PyPI 安装（推荐）::

    pip install fish-async-task

或从源码安装::

    git clone https://github.com/fishzjp/FishAsyncTask.git
    cd FishAsyncTask
    pip install .

基础用法
--------

创建任务管理器
~~~~~~~~~~~~~~

.. code-block:: python

    from fish_async_task import TaskManager

    # 使用默认配置创建
    manager = TaskManager()

    # 使用自定义配置创建
    manager = TaskManager(
        min_workers=2,           # 最小工作线程数
        max_workers=8,           # 最大工作线程数
        queue_size=100,          # 任务队列大小
        idle_timeout=60,         # 空闲超时（秒）
    )

提交任务
~~~~~~~~

同步函数
^^^^^^^^

.. code-block:: python

    def process_data(data):
        # 处理数据
        return result

    task_id = manager.submit_task(process_data, args=(data,))

异步函数
^^^^^^^^

.. code-block:: python

    async def async_process(data):
        # 异步处理
        return await some_async_operation()

    task_id = manager.submit_task(async_process, args=(data,))

带参数的任务
^^^^^^^^^^^^^^^^

.. code-block:: python

    task_id = manager.submit_task(
        func=process_file,
        args=("input.txt",),
        kwargs={"output": "output.txt", "encoding": "utf-8"},
        priority=5,  # 可选：优先级（1-10，10最高）
        timeout=30,  # 可选：超时时间（秒）
    )

获取结果
~~~~~~~~

阻塞等待结果
^^^^^^^^^^^^

.. code-block:: python

    # 等待任务完成并获取结果
    result = manager.get_task_result(task_id)

    # 带超时的等待
    try:
        result = manager.get_task_result(task_id, timeout=10)
    except TimeoutError:
        print("任务超时")

非阻塞查询
^^^^^^^^^^

.. code-block:: python

    # 查询任务状态
    status = manager.get_task_status(task_id)
    if status["status"] == "completed":
        result = status["result"]
    elif status["status"] == "pending":
        print("任务等待中")
    elif status["status"] == "failed":
        error = status["error"]

批量操作
--------

批量提交任务
~~~~~~~~~~~~

.. code-block:: python

    task_ids = []
    for i in range(100):
        task_id = manager.submit_task(process_item, args=(i,))
        task_ids.append(task_id)

    # 等待所有任务完成
    results = []
    for task_id in task_ids:
        result = manager.get_task_result(task_id)
        results.append(result)

批量查询状态
~~~~~~~~~~~~

.. code-block:: python

    # 获取所有任务状态
    all_status = manager.get_all_task_status()

    # 获取特定状态的任务
    pending_tasks = manager.get_tasks_by_status("pending")
    completed_tasks = manager.get_tasks_by_status("completed")

任务取消
--------

.. code-block:: python

    # 取消单个任务
    success = manager.cancel_task(task_id)

    # 批量取消
    for task_id in task_ids:
        manager.cancel_task(task_id)

资源清理
--------

优雅关闭
~~~~~~~~

.. code-block:: python

    # 等待所有任务完成
    manager.shutdown(wait=True)

    # 强制关闭（不等待）
    manager.shutdown(wait=False)

    # 使用上下文管理器（推荐）
    with TaskManager() as manager:
        task_id = manager.submit_task(some_task)
        result = manager.get_task_result(task_id)
    # 自动清理资源

完整示例
--------

Web 后台任务
~~~~~~~~~~~~

.. code-block:: python

    from fish_async_task import TaskManager
    import time

    # 全局任务管理器
    task_manager = TaskManager(min_workers=4, max_workers=16)

    def process_order(order_id):
        """处理订单"""
        time.sleep(2)  # 模拟耗时操作
        return {"order_id": order_id, "status": "completed"}

    # 提交任务
    task_id = task_manager.submit_task(
        process_order,
        args=("ORDER-12345",),
    )

    # 在其他地方查询结果
    status = task_manager.get_task_status(task_id)
    print(f"任务状态: {status['status']}")

数据批量处理
~~~~~~~~~~~~

.. code-block:: python

    from fish_async_task import TaskManager

    def process_row(row):
        """处理单行数据"""
        # 数据处理逻辑
        return processed_row

    # 创建管理器
    with TaskManager(min_workers=8) as manager:
        # 批量提交任务
        task_ids = []
        for row in data_rows:
            task_id = manager.submit_task(process_row, args=(row,))
            task_ids.append(task_id)

        # 收集结果
        results = []
        for task_id in task_ids:
            result = manager.get_task_result(task_id)
            results.append(result)

    print(f"处理完成，共 {len(results)} 条记录")
