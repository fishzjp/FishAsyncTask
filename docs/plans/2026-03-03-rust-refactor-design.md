# FishAsyncTask Rust 重构技术方案

**版本**: 2.0
**日期**: 2026-03-03
**作者**: AI 协作设计
**状态**: 设计阶段（已修正）

---

## 一、项目概述

### 1.1 目标

将 FishAsyncTask 的**核心底层模块**用 Rust 重构，保持 Python API 完全兼容，在可控复杂度下提升性能。

### 1.2 重构范围（优化后）

| 模块 | 重构 | 理由 |
|------|------|------|
| task_status.py | ✅ Rust | 状态存储是热点，Rust 化收益高 |
| priority_queue.py | ✅ Rust | 优先级操作频繁，Rust 加速明显 |
| worker.py | ❌ 保留 Python | 涉及 Python 函数调用，Rust 化收益有限 |
| task_manager.py | ❌ 保留 Python | 作为胶水层，无需改动 |

**关键决策**：worker 保留 Python 实现的原因：
- Python 函数调用必须在 GIL 下执行
- 跨语言调用开销会抵消 Rust 带来的收益
- 可通过优化算法和并发参数提升性能

### 1.3 技术栈（更新至最新稳定版）

| 组件 | 技术选型 | 版本 | 说明 |
|------|----------|------|------|
| **Python 绑定** | PyO3 | 0.23 | 最新稳定版，改进的 GIL 处理 |
| **构建工具** | Maturin | 1.7+ | PyO3 官方推荐 |
| **线程池** | rayon | 1.10 | 工作窃取线程池，替代 Tokio |
| **通道** | crossbeam-channel | 0.5 | 无锁多生产者多消费者通道 |
| **并发原语** | parking_lot | 0.12 | 比 std 更快的锁 |
| **哈希表** | DashMap | 6.1 | 无锁并发哈希表 |
| **优先级队列** | binary-heap-plus | 0.5 | 替代维护不活跃的 priority_queue |
| **图算法** | petgraph | 0.6 | 任务依赖管理 |
| **序列化** | serde | 1.0 | 结构体序列化 |

---

## 二、核心设计原则（修正）

1. **API 兼容性**：Python API 保持不变，用户代码无需修改
2. **最小拷贝**：承认存在序列化开销，通过批量 API 最小化
3. **有锁并发**：使用高效锁（parking_lot）而非复杂的无锁结构
4. **渐进式迁移**：模块化设计，支持独立测试和验证
5. **性能可观测**：内置性能指标，便于对比验证
6. **务实主义**：在复杂度和性能间取得平衡

---

## 三、模块重构设计（修正）

### 3.1 状态存储引擎

#### 当前 Python 实现问题

- 读写锁在高并发下竞争激烈
- 分片存储的锁开销较大
- 批量更新的队列有额外内存开销

#### Rust 重构方案

```
fish_async_task_core/
├── src/
│   ├── status/
│   │   ├── mod.rs
│   │   ├── store.rs        # DashMap 分片存储
│   │   ├── sharded.rs      # 分片管理
│   │   └── expiry.rs       # 过期清理
```

#### 核心技术

- **DashMap 6.1**：无锁并发哈希表
- **parking_lot::RwLock**：fallback 场景下的高效读写锁
- **crossbeam::queue::SegQueue**：无锁批量更新队列

#### 批量 API（新增）

```rust
#[pyclass]
pub struct TaskStore {
    inner: Arc<ShardedTaskStore>,
}

#[pymethods]
impl TaskStore {
    // 单个操作
    fn set_status(&self, task_id: &str, status: TaskStatus) -> PyResult<()> {
        self.inner.set(task_id, status);
        Ok(())
    }

    // 批量操作 - 减少 80% 跨语言调用
    fn set_status_batch(&self, items: Vec<(String, TaskStatus)>) -> PyResult<usize> {
        Ok(self.inner.set_batch(items))
    }

    fn get_status_batch(&self, task_ids: Vec<String>) -> PyResult<Vec<Option<TaskStatus>>> {
        Ok(self.inner.get_batch(task_ids))
    }
}
```

#### 预期收益（保守估计）

状态读写性能提升 **2-4x**（原 3-5x 过于乐观）

---

### 3.2 优先级队列

#### 当前 Python 实现问题

- heapq 非线程安全，需要额外锁
- 依赖管理使用图遍历，性能较差

#### Rust 重构方案

```
fish_async_task_core/
├── src/
│   ├── queue/
│   │   ├── mod.rs
│   │   ├── priority.rs     # 基于 BinaryHeap 的优先级队列
│   │   └── dependency.rs   # 任务依赖管理
```

#### 核心技术

- **std::collections::BinaryHeap**：标准库二叉堆，零依赖
- **parking_lot::Mutex**：细粒度锁保护
- **petgraph**：图算法库，用于依赖解析

#### 批量 API（新增）

```rust
#[pyclass]
pub struct PriorityTaskQueue {
    inner: Mutex<TaskQueue>,
}

#[pymethods]
impl PriorityTaskQueue {
    fn push(&self, task_id: String, priority: i32) -> PyResult<()> {
        let mut queue = self.inner.lock();
        queue.push(task_id, priority);
        Ok(())
    }

    // 批量入队 - 减少锁获取次数
    fn push_batch(&self, items: Vec<(String, i32)>) -> PyResult<usize> {
        let mut queue = self.inner.lock();
        let count = queue.push_batch(items);
        Ok(count)
    }

    fn pop_batch(&self, max_count: usize) -> PyResult<Vec<String>> {
        let mut queue = self.inner.lock();
        Ok(queue.pop_batch(max_count))
    }
}
```

#### 预期收益（保守估计）

- 入队/出队性能提升 **1.5-2.5x**（原 2-3x 略高）
- 依赖解析速度提升 **3-4x**（原 5x 过于乐观）

---

### 3.3 Python 绑定层（修正）

#### 架构设计

```
fish_async_task/
├── __init__.py           # 公开 API（保持不变）
├── task_manager.py       # 保留，优化算法
├── worker.py             # 保留，调整参数
├── _core/                # PyO3 绑定层
│   ├── __init__.py
│   └── bindings.py       # Rust 扩展入口
└── _rt/                  # Rust 扩展模块
    └── fish_async_task_core.so  # 编译产物
```

#### PyO3 绑定代码结构（修正）

```rust
// fish_async_task_core/src/lib.rs
use pyo3::prelude::*;

/// 任务状态存储
#[pyclass]
pub struct TaskStore {
    inner: status::ShardedTaskStore,
}

#[pymethods]
impl TaskStore {
    #[new]
    fn new(shard_count: Option<usize>) -> PyResult<Self> {
        Ok(Self {
            inner: status::ShardedTaskStore::new(shard_count.unwrap_or(16)),
        })
    }

    fn set(&self, task_id: &str, status: TaskStatus) -> PyResult<()> {
        self.inner.set(task_id, status);
        Ok(())
    }

    fn get(&self, task_id: &str) -> PyResult<Option<TaskStatus>> {
        Ok(self.inner.get(task_id))
    }

    // 批量 API
    fn set_batch(&self, items: Vec<(String, TaskStatus)>) -> PyResult<usize> {
        Ok(self.inner.set_batch(items))
    }
}

/// 优先级任务队列
#[pyclass]
pub struct PriorityTaskQueue {
    inner: queue::TaskQueue,
}

#[pymethods]
impl PriorityTaskQueue {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(Self {
            inner: queue::TaskQueue::new(),
        })
    }

    fn push(&self, task_id: String, priority: i32) -> PyResult<()> {
        self.inner.push(task_id, priority);
        Ok(())
    }

    fn pop(&self) -> PyResult<Option<String>> {
        Ok(self.inner.pop())
    }

    // 批量 API
    fn push_batch(&self, items: Vec<(String, i32)>) -> PyResult<usize> {
        Ok(self.inner.push_batch(items))
    }

    fn pop_batch(&self, max_count: usize) -> PyResult<Vec<String>> {
        Ok(self.inner.pop_batch(max_count))
    }
}

// Python 模块定义
#[pymodule]
fn fish_async_task_core(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<TaskStore>()?;
    m.add_class::<PriorityTaskQueue>()?;
    Ok(())
}
```

---

## 四、项目结构（修正）

```
FishAsyncTask/
├── fish_async_task/              # Python 包
│   ├── __init__.py
│   ├── task_manager.py           # 保留并优化
│   ├── worker.py                 # 保留，调整参数
│   ├── config.py                 # 保留
│   ├── types.py                  # 保留
│   └── _core/                    # PyO3 绑定
│       ├── __init__.py
│       └── bindings.py
│
├── fish_async_task_core/         # Rust 核心库
│   ├── Cargo.toml
│   ├── src/
│   │   ├── lib.rs                # PyO3 绑定入口
│   │   ├── status/               # 状态存储
│   │   │   ├── mod.rs
│   │   │   ├── store.rs
│   │   │   ├── sharded.rs
│   │   │   └── expiry.rs
│   │   ├── queue/                # 优先级队列
│   │   │   ├── mod.rs
│   │   │   ├── priority.rs
│   │   │   └── dependency.rs
│   │   └── types/                # 共享类型
│   │       └── mod.rs
│   └── python/                   # Python 模块源码
│       └── fish_async_task_core/
│           └── __init__.py
│
├── tests/
│   ├── test_integration.py       # 集成测试
│   ├── test_api_compatibility.py # API 兼容性测试
│   └── benchmark/                # 性能基准测试
│       ├── status_bench.py
│       ├── queue_bench.py
│       ├── batch_vs_single.py    # 批量 vs 单独对比
│       └── comparison.py         # Python vs Rust 对比
│
├── pyproject.toml
├── Cargo.toml                    # Workspace 配置
└── README.md
```

---

## 五、实现计划（修正）

### 5.1 开发阶段

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| **阶段 0** | 性能基线建立 | 3-5 天 |
| **阶段 1** | 基础设施搭建 | 1 周 |
| **阶段 2** | 状态存储引擎 | 1-2 周 |
| **阶段 3** | 优先级队列 | 1 周 |
| **阶段 4** | Python 集成 | 1 周 |
| **阶段 5** | 性能调优 | 1 周 |
| **总计** | | **6-8 周** |

### 5.2 阶段详情

#### 阶段 0：性能基线建立（3-5 天）⚠️ 新增

在重构前必须完成的评估：

```bash
# 使用 py-sprofile 定位热点
pip install py-spy
python -m pyspy record -o profile.svg -- python your_workload.py

# 使用 py-sinstrument 测量函数耗时
pip import pyinstrument
python -m pyinstrument your_workload.py
```

**验证清单**：
- [ ] 确认当前瓶颈确实在 task_status 和 priority_queue
- [ ] 测量跨语言调用实际开销
- [ ] 评估批量操作的潜在收益
- [ ] 确认是否有更简单的 Python 优化方案

#### 阶段 1：基础设施（1 周）

- [ ] 搭建 Rust 项目结构
- [ ] 配置 PyO3 + Maturin 构建环境
- [ ] 建立基础测试框架
- [ ] 设置 CI/CD 流程

#### 阶段 2：状态存储引擎（1-2 周）

- [ ] 实现 `ShardedTaskStore` 基于 `DashMap`
- [ ] 实现过期清理机制
- [ ] 实现 PyO3 绑定（含批量 API）
- [ ] 单元测试 + 基准测试
- [ ] 性能对比验证

#### 阶段 3：优先级队列（1 周）

- [ ] 实现高效优先级队列
- [ ] 实现任务依赖管理
- [ ] PyO3 绑定（含批量 API）
- [ ] 单元测试

#### 阶段 4：Python 集成（1 周）

- [ ] 修改 Python 胶水层使用 Rust 模块
- [ ] 保持 API 完全兼容
- [ ] 端到端集成测试

#### 阶段 5：性能调优（1 周）

- [ ] 基于基准测试结果优化
- [ ] 调整分片数量、批量大小等参数
- [ ] 文档更新

---

### 5.3 依赖库（更新版本）

```toml
# Cargo.toml
[workspace]
members = ["fish_async_task_core"]

[dependencies]
# Python 绑定
pyo3 = { version = "0.23", features = ["extension-module", "abi3-py39"] }

# 线程池（替代 Tokio）
rayon = "1.10"

# 并发原语
parking_lot = "0.12"

# 无锁数据结构
dashmap = "6.1"
crossbeam-channel = "0.5"

# 图算法（依赖管理）
petgraph = "0.6"

# 序列化
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"

# 工具库
uuid = { version = "1.11", features = ["v4", "serde"] }
thiserror = "2.0"
tracing = "0.1"
tracing-subscriber = "0.3"

[dev-dependencies]
criterion = "0.5"
pprof = { version = "0.14", features = ["flamegraph", "criterion"] }
```

---

## 六、性能验证方案（修正）

### 6.1 基准测试设计

```python
# tests/benchmark/comparison.py
import pytest
import fish_async_task
import time
import statistics

class PerformanceBenchmark:
    """性能基准测试"""

    @pytest.fixture
    def manager(self):
        return fish_async_task.TaskManager()

    def test_status_write_throughput(self, manager):
        """状态写入吞吐量测试"""
        n_tasks = 100_000
        start = time.time()

        for i in range(n_tasks):
            manager.submit_task(lambda: i)

        elapsed = time.time() - start
        throughput = n_tasks / elapsed
        print(f"写入吞吐量: {throughput:,} ops/sec")
        assert throughput > 30_000  # 目标: 3万+ ops/sec（修正）

    def test_status_read_latency(self, manager):
        """状态读取延迟测试（P99）"""
        latencies = []
        task_id = manager.submit_task(lambda: "test")

        for _ in range(10_000):
            start = time.perf_counter()
            manager.get_task_status(task_id)
            latencies.append(time.perf_counter() - start)

        p99 = statistics.quantiles(latencies, n=100)[98]
        print(f"P99 延迟: {p99*1000:.2f} μs")
        assert p99 < 0.002  # 目标: P99 < 2ms（修正）

    def test_batch_vs_single(self, manager):
        """批量 vs 单独操作对比"""
        # 单独操作
        start = time.time()
        for i in range(10_000):
            manager.submit_task(lambda: i)
        single_time = time.time() - start

        # 批量操作
        start = time.time()
        manager.submit_tasks_batch([lambda: i for i in range(10_000)])
        batch_time = time.time() - start

        speedup = single_time / batch_time
        print(f"批量操作加速: {speedup:.2f}x")
        assert speedup > 2  # 至少 2x 加速
```

### 6.2 性能对比矩阵（修正）

| 指标 | Python 版本 | Rust 版本 | 提升倍数 |
|------|-------------|-----------|----------|
| 状态写入吞吐 | ~10k ops/s | ~30k ops/s | **2-3x** |
| 状态读取延迟 (P99) | ~5ms | ~2ms | **2-2.5x** |
| 队列入队/出队 | ~5k ops/s | ~10k ops/s | **1.5-2x** |
| 依赖解析 | 基准 | 3-4x 更快 | **3-4x** |
| 内存占用 | 基准 | -35% | **~1.5x** |
| 启动时间 | 基准 | +15ms | 可接受 |

### 6.3 回归测试

```python
# tests/test_regression.py
"""确保 API 兼容性"""

def test_api_compatibility():
    """验证所有公开 API 保持兼容"""
    manager = TaskManager()

    # 原有 API 应该都能正常工作
    task_id = manager.submit_task(func, arg1, arg2, kwarg=value)
    status = manager.get_task_status(task_id)
    manager.clear_task_status(task_id)
    manager.shutdown()

    # 新增批量 API（可选）
    task_ids = manager.submit_tasks_batch([func1, func2, func3])
    statuses = manager.get_statuses_batch(task_ids)
```

---

## 七、构建与发布（保持不变）

### 7.1 构建配置

```toml
# pyproject.toml
[build-system]
requires = ["maturin>=1.7,<2.0"]
build-backend = "maturin"

[project]
name = "fish-async-task"
version = "1.0.0"  # 重大版本升级
description = "高性能异步任务管理器（Rust 核心）"
requires-python = ">=3.9"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "pytest-benchmark>=4.0",
    "maturin>=1.7",
    "py-spy>=0.3",      # 性能分析
    "pyinstrument>=4.0", # 函数耗时分析
]

[tool.maturin]
python-source = "python"
module-name = "fish_async_task_core._core"
features = ["pyo3/extension-module"]
strip = true
```

```toml
# fish_async_task_core/Cargo.toml
[package]
name = "fish-async-task-core"
version = "1.0.0"
edition = "2021"

[lib]
name = "fish_async_task_core"
crate-type = ["cdylib"]

[profile.release]
lto = true
codegen-units = 1
strip = true
opt-level = 3
panic = "abort"
```

### 7.2 本地构建

```bash
# 开发模式（快速编译）
maturin develop

# 释放模式（优化编译）
maturin develop --release

# 构建发布包
maturin build --release --strip
```

### 7.3 CI/CD 流程

```yaml
# .github/workflows/build.yml
name: Build and Test

on: [push, pull_request]

jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.9", "3.10", "3.11", "3.12"]

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python }}

      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Install Maturin
        run: pip install maturin[patchelf]

      - name: Build
        run: maturin build --release

      - name: Run tests
        run: |
          pip install .[dev]
          pytest -v --cov=fish_async_task
```

### 7.4 发布流程

```bash
# 1. 更新版本号
# 编辑 pyproject.toml 和 Cargo.toml

# 2. 构建多平台 wheels
# macOS (arm64 + x64)
maturin build --release --target aarch64-apple-darwin
maturin build --release --target x86_64-apple-darwin

# Linux (manylinux)
maturin build --release --target x86_64-unknown-linux-gnu
maturin build --release --target aarch64-unknown-linux-gnu

# Windows
maturin build --release --target x86_64-pc-windows-msvc

# 3. 发布到 PyPI
maturin publish --username __token__ --password $PYPI_TOKEN
```

---

## 八、风险与缓解（更新）

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| PyO3 类型转换开销 | 高 | 高 | 使用批量 API 减少 80% 跨语言调用 |
| 编译产物体积大 | 中 | 高 | 启用 `lto = true` 和 `strip = true`，预期 ~15MB |
| 跨平台兼容性 | 中 | 中 | 使用 GitHub Actions 多平台测试 |
| 调试困难 | 高 | 高 | 使用 `tracing` 日志 + Python 侧回退机制 |
| 性能不达预期 | 高 | 中 | 阶段 0 性能基线 + 迭代优化 |
| Worker 保留 Python 的性能瓶颈 | 中 | 高 | 通过调整并发参数和算法优化补偿 |

---

## 九、迁移指南

### 9.1 用户迁移

**好消息**：用户代码无需修改！

```python
# 原有代码继续工作
from fish_async_task import TaskManager

manager = TaskManager()
task_id = manager.submit_task(my_func, arg1, arg2)
status = manager.get_task_status(task_id)
manager.shutdown()

# 可选：使用批量 API 获得更好性能
task_ids = manager.submit_tasks_batch([my_func] * 100)
statuses = manager.get_statuses_batch(task_ids)
```

### 9.2 性能对比

用户可以验证性能提升：

```python
# tests/benchmark/show_performance.py
import time
from fish_async_task import TaskManager

manager = TaskManager()

# 提交 10,000 个任务
start = time.time()
for i in range(10_000):
    manager.submit_task(lambda x: x * x, i)

# 等待完成并统计
while manager.get_pending_count() > 0:
    time.sleep(0.1)

print(f"完成时间: {time.time() - start:.2f}秒")
# 预期输出: 完成时间: 30-40秒 (Rust) vs 60-80秒 (Python)
```

---

## 十、总结（修正）

### 核心收益

| 方面 | 收益 |
|------|------|
| **性能** | 2-4x 状态操作提升，1.5-2x 队列操作提升 |
| **资源** | ~35% 内存占用降低 |
| **兼容性** | 100% API 兼容 |
| **稳定性** | Rust 内存安全保证 |
| **复杂度** | 显著低于全异步方案 |

### 技术亮点

- 高效线程池（rayon 工作窃取）
- 批量 API 最小化跨语言开销
- DashMap 无锁并发哈希表
- 务实的混合架构

### 关键决策

1. **放弃 Tokio 异步运行时**：与 Python GIL 模型不匹配，改用 rayon 线程池
2. **Worker 保留 Python**：Python 函数调用必须在 GIL 下执行，跨语言调用开销大
3. **添加批量 API**：显著减少跨语言调用次数，是性能关键
4. **保守的收益预期**：基于实际情况调整，避免过度承诺

---

## 附录

### A. 性能验证清单（新增）

**重构前必须完成**：

```bash
# 1. 定位性能热点
pip install py-spy pyinstrument
python -m pyspy record -o profile.svg -- python workload.py
python -m pyinstrument workload.py

# 2. 回答关键问题
- [ ] 当前瓶颈在哪里？（具体到函数级别）
- [ ] task_status 操作占比多少？
- [ ] priority_queue 操作占比多少？
- [ ] PyO3 绑定开销实际多少？（原型测试）
- [ ] 批量操作的理论收益是多少？
- [ ] 是否有更简单的 Python 优化方案？

# 3. 建立性能基线
- [ ] 记录当前吞吐量（ops/s）
- [ ] 记录当前延迟分布（P50, P99）
- [ ] 记录当前内存占用
```

### B. 参考项目

- [PyO3](https://github.com/PyO3/pyo3) - Rust 与 Python 的绑定
- [Rayon](https://github.com/rayon-rs/rayon) - Rust 数据并行库
- [DashMap](https://github.com/xacrimon/dashmap) - 无锁并发哈希表
- [Maturin](https://github.com/PyO3/maturin) - Rust Python 扩展构建工具

### C. 相关文档

- [PyO3 用户指南](https://pyo3.rs/)
- [Rayon 官方文档](https://docs.rs/rayon/)
- [Maturin 指南](https://maturin.rs/)

### D. 修订历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| 1.0 | 2026-03-03 | 初始版本 |
| 2.0 | 2026-03-03 | 重大修正：改用 rayon，优化重构范围，添加批量 API，修正收益预期 |

---

**文档版本**: 2.0
**最后更新**: 2026-03-03
