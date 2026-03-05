FishAsyncTask 文档
==================

.. image:: ../../logo.png
   :alt: FishAsyncTask Logo
   :align: center
   :width: 200px

**在线文档**: https://fishzjp.github.io/FishAsyncTask/

**FishAsyncTask** 是一个高性能异步任务管理器，支持线程池和动态伸缩。

**默认采用 Rust 核心实现**，提供卓越性能。安装即用，无需额外配置。

特性
----

* **Rust 核心实现（默认）** - 状态存储和优先级队列使用 Rust 实现，性能提升 2-4x
* **Python 友好 API** - 完整的 Python 接口，易于使用
* **动态伸缩** - 根据负载自动调整工作线程数量
* **状态跟踪** - 完整的任务状态管理和查询功能
* **线程安全** - 使用无锁数据结构保证并发安全
* **多种队列支持** - 内置队列、Redis、Huey、Dramatiq
* **优先级支持** - 支持任务优先级调度
* **任务依赖** - 支持任务依赖管理，自动处理执行顺序

快速开始
--------

安装::

    pip install fish-async-task

基础用法::

    from fish_async_task import TaskManager

    # 创建任务管理器
    manager = TaskManager()

    # 提交任务
    task_id = manager.submit_task(lambda: "Hello, World!")

    # 获取结果
    result = manager.get_task_result(task_id)
    print(result)  # 输出: "Hello, World!"

    # 关闭管理器
    manager.shutdown()

文档目录
--------

.. toctree::
   :maxdepth: 2
   :caption: 用户指南:

   quickstart
   advanced
   best_practices
   faq

.. toctree::
   :maxdepth: 2
   :caption: API 参考:

   api/index

.. toctree::
   :maxdepth: 1
   :caption: 其他:

   changelog
   config

索引和表格
----------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
