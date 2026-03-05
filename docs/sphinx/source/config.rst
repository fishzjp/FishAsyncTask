配置参考
========

TaskManager 配置参数
---------------------

构造函数参数
~~~~~~~~~~~~

.. code-block:: python

    TaskManager(
        instance_key: str = "default",
        min_workers: int = 1,
        max_workers: Optional[int] = None,
        queue_size: int = 1000,
        idle_timeout: int = 60,
        task_status_ttl: int = 3600,
        max_task_status_count: int = 10000,
        cleanup_interval: int = 300,
        thread_join_timeout: int = 2,
        task_timeout: Optional[int] = None,
        enable_logging: bool = True,
        log_level: int = logging.INFO,
    )

参数说明
~~~~~~~~

``instance_key`` : str
    实例键名，用于创建多个独立的单例实例。默认为 ``"default"``。

``min_workers`` : int
    最小工作线程数，即使空闲也会保持这些线程。默认为 ``1``。

``max_workers`` : int | None
    最大工作线程数，根据负载自动扩展。默认为 ``None``（自动计算为 CPU 核心数 × 4）。

``queue_size`` : int
    任务队列的最大长度。默认为 ``1000``。

``idle_timeout`` : int
    空闲线程的超时时间（秒）。超过此时间无工作的线程会退出。默认为 ``60``。

``task_status_ttl`` : int
    任务状态的生存时间（秒）。超过此时间的已完成/失败任务状态会被清理。默认为 ``3600``。

``max_task_status_count`` : int
    最多保留的任务状态数量。超过此数量时会触发清理。默认为 ``10000``。

``cleanup_interval`` : int
    清理任务的执行间隔（秒）。默认为 ``300``。

``thread_join_timeout`` : int
    关闭时等待线程结束的超时时间（秒）。默认为 ``2``。

``task_timeout`` : int | None
    任务的默认超时时间（秒）。为 ``None`` 表示无超时限制。默认为 ``None``。

``enable_logging`` : bool
    是否启用日志记录。默认为 ``True``。

``log_level`` : int
    日志级别，如 ``logging.INFO``、``logging.DEBUG``。默认为 ``logging.INFO``。

配置文件
--------

FishAsyncTask 支持通过配置文件设置默认参数。配置文件使用 YAML 或 JSON 格式。

YAML 格式
~~~~~~~~~

.. code-block:: yaml

    # fish_async_task.yaml
    task_manager:
      min_workers: 2
      max_workers: 16
      queue_size: 1000
      idle_timeout: 60
      task_status_ttl: 3600
      max_task_status_count: 10000
      cleanup_interval: 300
      task_timeout: 300
      enable_logging: true
      log_level: "INFO"

JSON 格式
~~~~~~~~~

.. code-block:: json

    {
        "task_manager": {
            "min_workers": 2,
            "max_workers": 16,
            "queue_size": 1000,
            "idle_timeout": 60,
            "task_status_ttl": 3600,
            "max_task_status_count": 10000,
            "cleanup_interval": 300,
            "task_timeout": 300,
            "enable_logging": true,
            "log_level": "INFO"
        }
    }

加载配置文件
~~~~~~~~~~~~

.. code-block:: python

    from fish_async_task import TaskManager
    from fish_async_task.config import ConfigLoader

    # 加载配置
    config = ConfigLoader.load("fish_async_task.yaml")

    # 使用配置创建管理器
    manager = TaskManager(**config)

环境变量
--------

也可以通过环境变量配置：

.. code-block:: bash

    export FISH_ASYNC_TASK_MIN_WORKERS=4
    export FISH_ASYNC_TASK_MAX_WORKERS=16
    export FISH_ASYNC_TASK_QUEUE_SIZE=1000

Python 中读取：

.. code-block:: python

    import os
    from fish_async_task import TaskManager

    manager = TaskManager(
        min_workers=int(os.getenv("FISH_ASYNC_TASK_MIN_WORKERS", 1)),
        max_workers=int(os.getenv("FISH_ASYNC_TASK_MAX_WORKERS", 16)),
        queue_size=int(os.getenv("FISH_ASYNC_TASK_QUEUE_SIZE", 1000)),
    )

PriorityTaskManager 配置
-------------------------

.. code-block:: python

    from fish_async_task.performance import PriorityTaskManager

    PriorityTaskManager(
        min_workers: int = 1,
        max_workers: Optional[int] = None,
        queue_size: int = 1000,
        idle_timeout: int = 60,
        # 优先级相关配置
        default_priority: int = 5,  # 默认优先级
        priority_levels: int = 10,  # 优先级级别数
    )

优先级说明
~~~~~~~~~~

* 优先级范围：1-10
* 10 表示最高优先级
* 1 表示最低优先级
* 默认优先级为 5

配置建议
--------

开发环境
~~~~~~~~

.. code-block:: python

    dev_manager = TaskManager(
        min_workers=1,
        max_workers=4,
        queue_size=100,
        task_status_ttl=600,  # 10 分钟
        enable_logging=True,
        log_level=logging.DEBUG,
    )

生产环境
~~~~~~~~

.. code-block:: python

    import os

    prod_manager = TaskManager(
        min_workers=max(4, os.cpu_count()),
        max_workers=os.cpu_count() * 4,
        queue_size=1000,
        idle_timeout=300,
        task_status_ttl=7200,  # 2 小时
        max_task_status_count=50000,
        cleanup_interval=600,
        enable_logging=True,
        log_level=logging.INFO,
    )

高负载环境
~~~~~~~~~~

.. code-block:: python

    high_load_manager = TaskManager(
        min_workers=os.cpu_count() * 2,
        max_workers=os.cpu_count() * 8,
        queue_size=5000,
        idle_timeout=600,
        task_status_ttl=3600,
        max_task_status_count=100000,
        cleanup_interval=300,
    )

低延迟环境
~~~~~~~~~~

.. code-block:: python

    low_latency_manager = TaskManager(
        min_workers=os.cpu_count() * 2,
        max_workers=os.cpu_count() * 4,
        queue_size=100,  # 较小的队列
        idle_timeout=30,  # 快速回收空闲线程
    )
