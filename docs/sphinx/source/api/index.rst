API 参考
========

核心模块
---------

.. automodule:: fish_async_task
    :members:
    :undoc-members:
    :show-inheritance:

TaskManager
-----------

.. autoclass:: fish_async_task.TaskManager
    :members:
    :undoc-members:
    :show-inheritance:

异常
----

.. autoexception:: fish_async_task.TaskQueueFullError

配置模块
---------

.. automodule:: fish_async_task.config
    :members:
    :undoc-members:
    :show-inheritance:

任务状态
--------

.. automodule:: fish_async_task.task_status
    :members:
    :undoc-members:
    :show-inheritance:

类型定义
--------

.. automodule:: fish_async_task.types
    :members:
    :undoc-members:
    :show-inheritance:

工作线程
--------

.. automodule:: fish_async_task.worker
    :members:
    :undoc-members:
    :show-inheritance:

高性能扩展
----------

.. automodule:: fish_async_task.performance
    :members:
    :undoc-members:
    :show-inheritance:

优先级队列
^^^^^^^^^^

.. autoclass:: fish_async_task.performance.PriorityTaskManager
    :members:
    :undoc-members:
    :show-inheritance:

自适应伸缩
^^^^^^^^^^

.. autoclass:: fish_async_task.performance.AdaptiveScalingManager
    :members:
    :undoc-members:
    :show-inheritance:

资源监控
^^^^^^^^^^

.. autoclass:: fish_async_task.performance.ResourceMonitor
    :members:
    :undoc-members:
    :show-inheritance:

分片状态管理
^^^^^^^^^^^^

.. autoclass:: fish_async_task.performance.ShardedStatusManager
    :members:
    :undoc-members:
    :show-inheritance:

批量更新
^^^^^^^^

.. autoclass:: fish_async_task.performance.BatchStatusUpdater
    :members:
    :undoc-members:
    :show-inheritance:
