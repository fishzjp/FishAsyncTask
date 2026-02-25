# FishAsyncTask

一个纯Python实现的异步任务管理器，支持线程池和动态伸缩。

[![GitHub](https://img.shields.io/github/stars/fishzjp/FishAsyncTask?style=social)](https://github.com/fishzjp/FishAsyncTask)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/)

## 目录

- [特性](#特性)
- [安装](#安装)
- [快速开始](#快速开始)
- [文档](#文档)
- [使用场景](#使用场景)
- [许可证](#许可证)
- [贡献](#贡献)

## 特性

- 🚀 **纯Python实现**：无需额外依赖，使用标准库实现
- 🔄 **动态伸缩**：根据任务队列大小自动调整工作线程数量
- 📊 **任务状态追踪**：实时查询任务执行状态和结果
- 🧹 **自动清理**：自动清理过期的任务状态记录
- 🔒 **线程安全**：使用锁机制保证线程安全
- 🎯 **单例模式**：支持多实例管理，不同业务模块可使用独立实例
- ⏱️ **任务超时**：支持配置任务执行超时时间
- 🚦 **队列控制**：支持阻塞和非阻塞两种任务提交模式
- 📈 **性能监控**：内置性能指标收集和健康状态监控
- 🔄 **任务优先级**：支持优先级队列，高优先级任务优先执行
- ⛓️ **任务依赖**：支持任务依赖管理，自动处理任务执行顺序
- 🚫 **任务取消**：支持协作式任务取消
- 💾 **资源管理**：自动跟踪和清理任务相关资源，防止泄漏
- ⚙️ **配置热重载**：支持运行时配置动态更新

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install fish-async-task
```

### 从 GitHub 安装

```bash
pip install git+https://github.com/fishzjp/FishAsyncTask.git
```

### 开发模式安装

```bash
git clone https://github.com/fishzjp/FishAsyncTask.git
cd FishAsyncTask
pip install -e ".[dev,performance]"
pre-commit install
```

**开发依赖包括**：
- `pytest`、`pytest-cov`、`pytest-benchmark` - 测试框架
- `black`、`isort` - 代码格式化
- `mypy`、`interrogate` - 代码质量检查
- `locust` - 负载测试
- `psutil`、`redis`、`huey`、`dramatiq` - 性能测试依赖

> 📖 详细的安装说明请参考 [安装文档](docs/INSTALL.md)

## 快速开始

### 基本使用

```python
from fish_async_task import TaskManager
import time

# 创建任务管理器实例（单例模式）
task_manager = TaskManager()

# 定义一个任务函数
def my_task(name: str, value: int):
    print(f"执行任务: {name}, 值: {value}")
    time.sleep(1)  # 模拟耗时操作
    return f"任务完成: {name}"

# 提交任务（非阻塞模式）
task_id = task_manager.submit_task(my_task, "任务1", value=100)
print(f"任务ID: {task_id}")

# 等待任务完成并查询状态
while True:
    status = task_manager.get_task_status(task_id)
    if status:
        if status["status"] == "completed":
            print(f"任务完成，结果: {status.get('result')}")
            break
        elif status["status"] == "failed":
            print(f"任务失败: {status.get('error')}")
            break
    time.sleep(0.1)

# 关闭任务管理器
task_manager.shutdown()
```

### 阻塞模式提交任务

当队列已满时，可以使用阻塞模式等待队列有空间：

```python
# 阻塞模式提交任务（等待队列有空间）
task_id = task_manager.submit_task(
    my_task, 
    "任务2", 
    value=200,
    block=True,        # 启用阻塞模式
    timeout=10.0      # 最多等待10秒
)
```

### 多实例管理

不同业务模块可以使用独立的任务管理器实例：

```python
# 默认实例
default_manager = TaskManager()

# 订单模块的独立实例
order_manager = TaskManager(instance_key="order")

# 支付模块的独立实例
payment_manager = TaskManager(instance_key="payment")
```

## 文档

详细的文档请参考以下链接：

- 📖 [安装文档](docs/INSTALL.md) - 详细的安装说明和开发环境设置
- 📚 [API 文档](docs/API.md) - 完整的 API 参考
- ⚙️ [配置文档](docs/CONFIG.md) - 环境变量和配置说明
- 💡 [最佳实践](docs/BEST_PRACTICES.md) - 使用建议和注意事项
- 🚀 [高级使用指南](docs/ADVANCED_USAGE.md) - 性能监控、资源管理、任务优先级等高级功能
- ❓ [常见问题](docs/FAQ.md) - FAQ 和问题解答
- 📝 [更新日志](docs/CHANGELOG.md) - 版本更新记录

## 使用场景

- 📦 **后台任务处理**：异步处理耗时操作，不阻塞主流程
- 🔄 **批量数据处理**：并发处理大量数据，提高处理效率
- 📧 **消息队列**：作为轻量级消息队列使用
- 🎯 **任务调度**：配合定时任务实现任务调度
- 🔌 **API异步处理**：Web API中异步处理请求

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

- GitHub 仓库: https://github.com/fishzjp/FishAsyncTask
- 问题反馈: https://github.com/fishzjp/FishAsyncTask/issues
