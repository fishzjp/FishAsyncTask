# FishAsyncTask v3.0.1 Release Notes

## 🎉 生产就绪版本

FishAsyncTask v3.0.1 是首个生产就绪版本，采用 Rust 核心实现，提供卓越性能。

## ✨ 主要特性

- 🚀 **默认 Rust 实现**：无需额外配置，安装即用
- 🌍 **跨平台支持**：支持 Linux, macOS, Windows
- 🔧 **零依赖 Rust 构建**：使用 maturin 自动构建
- 📦 **Python 友好**：保持纯 Python 的使用体验

## 📦 安装

```bash
pip install fish-async-task
```

## 🚀 快速开始

```python
from fish_async_task import TaskManager

task_manager = TaskManager()
task_id = task_manager.submit_task(lambda: "Hello, Rust!")
result = task_manager.get_task_result(task_id)
print(result)  # "Hello, Rust!"
```

## 🔄 从 0.x 升级

API 完全兼容，无需修改代码。直接升级即可：

```bash
pip install --upgrade fish-async-task
```

## 📊 性能

相比纯 Python 实现，Rust 核心提供 1.2x-2.2x 的性能提升，内存占用降低 99%。

| 操作 | Python | Rust | 加速比 |
|------|--------|------|--------|
| 并发状态写入 | 1.47M ops/s | 1.79M ops/s | 1.22x |
| 并发状态读取 | 1.07M QPS | 1.38M QPS | 1.29x |
| 队列入队 | 603K ops/s | 1.30M ops/s | 2.16x |
| 队列出队 | 705K ops/s | 1.30M ops/s | 1.85x |
| 内存占用 (5K任务) | 1,432 KB | 0.3 KB | ~100% 节省 |

## 📚 文档

完整文档：https://fishzjp.github.io/FishAsyncTask/

## 🙏 致谢

感谢所有贡献者和用户的反馈！
