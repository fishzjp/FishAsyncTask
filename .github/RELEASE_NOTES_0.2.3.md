# Release Notes - FishAsyncTask v0.2.3

**发布日期**: 2026-02-25
**版本**: 0.2.3
**类型**: 性能优化与功能增强

---

## 📋 发行概述

FishAsyncTask v0.2.3 是一个**性能优化与功能增强版本**,为项目添加了完整的性能监控、资源管理和任务调度能力。

---

## ✨ 新增功能

### 性能监控模块 (`fish_async_task.performance.monitoring`)

- **PerformanceMetrics** 类 - 收集任务执行指标
  - 支持任务提交、完成、失败、取消计数
  - 支持平均执行时间、队列等待时间统计
  - 支持百分位数统计 (P50, P90, P95, P99)
  - 支持历史数据追踪 (可配置最大历史记录数)

- **SystemHealthMonitor** 类 - 监控系统健康状态
  - 支持队列大小、失败率、平均执行时间监控
  - 支持自定义健康检查阈值
  - 支持绿色/黄色/红色三级状态告警

### 资源管理模块 (`fish_async_task.performance.resource_manager`)

- **TaskResourceManager** 类 - 跟踪和管理任务资源
  - 支持注册和注销任务资源
  - 支持任务级资源批量清理
  - 支持资源过期自动驱逐

- **TimeoutTaskTracker** 类 - 跟踪超时任务
  - 支持超时任务自动跟踪和清理

### 优先级队列模块 (`fish_async_task.performance.priority_queue`)

- **PriorityTaskQueue** 类 - 优先级任务队列
  - 支持优先级排序（数字越小优先级越高）
  - 支持队列容量限制

- **PriorityTaskManager** 类 - 优先级任务管理器
- **TaskDependencyManager** 类 - 任务依赖管理
  - 支持循环依赖检测

### 任务取消模块 (`fish_async_task.performance.task_cancellation`)

- **CancelEvent** 类 - 协作式取消事件
- **CancellableTask** 类 - 可取消任务封装
- **TaskCancellationManager** 类 - 任务取消管理器

### 配置管理

- **HotReloadConfig** 类 - 配置热重载
- **validate_config** 装饰器 - 配置验证

### 结构化日志

- **StructuredLogger** 类 - 结构化日志记录器
- **ContextLogger** 类 - 上下文日志记录器

---

## 🔧 代码优化

### 锁竞争优化 (`task_status.py`)

- 新增增量清理策略 `_enforce_max_count_incremental`
- 智能判断：超过限制 1.5 倍时使用完整清理
- 减少锁竞争，提升高并发性能

---

## 📊 测试

- 核心模块测试: 114 个全部通过 ✅
- 集成测试: 7 个全部通过 ✅

---

## 📦 安装

### 标准安装

```bash
# 从PyPI安装
pip install --upgrade fish-async-task

# 或使用uv(更快)
uv pip install fish-async-task
```

### 开发安装

```bash
# 克隆仓库
git clone https://github.com/fishzjp/FishAsyncTask.git
cd FishAsyncTask

# 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 开发模式安装
pip install -e .

# 运行测试
pytest tests/ -v
```

---

## 🔄 Breaking Changes

**无 API 破坏性变更**,所有现有代码完全兼容。

---

## 📝 变更日志

完整变更日志请参阅: [CHANGELOG.md](docs/CHANGELOG.md)

---

## 🙏 致谢

感谢以下工具和项目:

- Python 社区
- 所有测试用户

---

*发布于: 2026-02-25*
*版本: 0.2.3*
*Python: 3.9+*
