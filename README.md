# FishAsyncTask

高性能异步任务管理器，支持线程池和动态伸缩。

**默认采用 Rust 核心实现**，提供卓越性能。安装即用，无需额外配置。

[![GitHub](https://img.shields.io/github/stars/fishzjp/FishAsyncTask?style=social)](https://github.com/fishzjp/FishAsyncTask)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

## 目录

- [特性](#特性)
- [性能](#性能)
- [安装](#安装)
- [快速开始](#快速开始)
- [文档](#文档)
- [使用场景](#使用场景)
- [许可证](#许可证)
- [贡献](#贡献)

## 特性

### 核心功能
- 🚀 **Rust 核心实现（默认）**：状态存储和优先级队列使用 Rust 实现，性能提升 2-4x
- 🔄 **动态伸缩**：根据任务队列大小自动调整工作线程数量
- 📊 **任务状态追踪**：实时查询任务执行状态和结果
- 🧹 **自动清理**：自动清理过期的任务状态记录
- 🔒 **线程安全**：使用无锁数据结构保证并发安全

### 高级功能
- ⏱️ **任务超时**：支持配置任务执行超时时间
- 🚦 **队列控制**：支持阻塞和非阻塞两种任务提交模式
- 📈 **性能监控**：内置性能指标收集和健康状态监控
- 🔄 **任务优先级**：支持优先级队列，高优先级任务优先执行
- ⛓️ **任务依赖**：支持任务依赖管理，自动处理任务执行顺序
- 🚫 **任务取消**：支持协作式任务取消
- 💾 **资源管理**：自动跟踪和清理任务相关资源，防止泄漏
- ⚙️ **配置热重载**：支持运行时配置动态更新

### 架构特点
- 🎯 **单例模式**：支持多实例管理，不同业务模块可使用独立实例
- 🌐 **Rust 核心 + Python API**：开箱即用的 Rust 性能，Python 友好的 API
- 📦 **批量 API**：支持批量操作，减少跨语言调用开销

## 性能

Rust 核心实现相比纯 Python 实现的性能提升：

| 操作 | Python | Rust | 加速比 |
|------|--------|------|--------|
| 并发状态写入 | 1.47M ops/s | 1.79M ops/s | **1.22x** |
| 并发状态读取 | 1.07M QPS | 1.38M QPS | **1.29x** |
| 队列入队 | 603K ops/s | 1.30M ops/s | **2.16x** |
| 队列出队 | 705K ops/s | 1.30M ops/s | **1.85x** |
| 内存占用 (5K任务) | 1,432 KB | 0.3 KB | **~100% 节省** |

详细性能数据请参考 [性能基线报告](tests/performance/rust_baseline/baseline_summary.md)

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install fish-async-task
```

**默认包含 Rust 核心实现**，提供最佳性能。支持 Python 3.9+。

### 从源码安装（开发者）

```bash
git clone https://github.com/fishzjp/FishAsyncTask.git
cd FishAsyncTask

# 安装 Python 依赖
pip install -e ".[dev,performance]"

# 构建并安装 Rust 核心
pip install maturin
maturin develop --release

# 安装 pre-commit hooks（可选）
pre-commit install
```

**开发依赖包括**：
- `pytest`、`pytest-cov`、`pytest-benchmark` - 测试框架
- `black`、`isort` - 代码格式化
- `mypy`、`interrogate` - 代码质量检查
- `maturin` - Rust 扩展构建工具
- `locust` - 负载测试
- `psutil`、`redis`、`huey`、`dramatiq` - 性能测试依赖

### 验证 Rust 核心

安装后可以验证 Rust 核心是否已启用：

```python
from fish_async_task._rust import is_rust_available
print(f"Rust 核心已启用: {is_rust_available()}")  # 应该输出 True
```

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

### 使用优先级队列

```python
# 高优先级任务会优先执行
task_manager.submit_task(high_priority_task, priority=1)
task_manager.submit_task(normal_task, priority=5)
task_manager.submit_task(low_priority_task, priority=10)
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
- 🔧 [Rust 重构技术方案](docs/plans/2026-03-03-rust-refactor-design.md) - Rust 实现的技术细节

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
