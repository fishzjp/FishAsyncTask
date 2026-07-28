# 优先级队列接入主流程 + 文档诚实化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 README 承诺的 `submit_task(func, priority=N)` 真正生效（接入 Rust/Python 优先级队列），并修正 README/基准中与事实不符的性能与内存表述。

**Architecture:** 引入 `TaskChannel` 内部通道类包装 `PriorityTaskQueueAdapter` + `task_id → TaskTuple` 旁路表 + 关闭哨兵，向 worker 暴露与 `queue.Queue` 兼容的 `get/put_nowait/put/qsize/task_done` 接口，使 `worker/core.py` 主循环零改动。Rust 侧把 `put` 改为真阻塞（双 Condvar）、`get` 改为返回 `Option`，适配器统一映射为标准库 `queue.Full/queue.Empty`。

**Tech Stack:** Python 3.9+（本地 3.11 venv）、PyO3 0.23 + parking_lot、maturin、pytest + pytest-timeout。

---

## 背景：侦察发现的缺陷清单（本计划的依据）

| # | 位置 | 缺陷 |
|---|------|------|
| D1 | `fish_async_task/performance/priority_queue.py:416-419` | `get_ready_tasks()` 持 `self._lock` 时调用同样拿锁的 `is_ready()`，非重入锁 → **死锁**（测试套件挂死的元凶） |
| D2 | `fish_async_task_core/src/queue/priority.rs:62-90` | `put(block=true)` 满时不等待直接 push，`maxsize` 形同虚设；`_timeout` 被忽略 |
| D3 | `fish_async_task_core/src/queue/priority.rs` | 空/满抛通用 `PyException`，worker 循环依赖 `queue.Empty` 语义 |
| D4 | `fish_async_task/_adapters.py:250-259` | `_RustPriorityTaskQueueAdapter._tasks` 只增不减 → 内存泄漏 |
| D5 | `fish_async_task/performance/priority_queue.py:67-79` | 纯 Python `put()` 的等待循环写在 `if not block:` 分支内 → `block=True` 时无容量检查；`get()` 单次 wait 后直接 raise，`timeout=None` 语义错误 |
| D6 | `fish_async_task/task_manager.py:309-374` | `submit_task` 无 `priority` 参数，README 示例中 `priority=1` 被透传给用户函数 |
| D7 | README/CHANGELOG | "性能提升 2-4x"、"内存 ~100% 节省"（tracemalloc 看不见 Rust 侧分配）与自家基线报告矛盾；CHANGELOG 0.3.1 有重复段落 |
| D8 | `pyproject.toml` | `--strict-markers` 但 `slow` marker 未注册 → `test_memory_leaks.py` 收集失败 |

## 文件结构

- Create: `fish_async_task/task_channel.py` — TaskChannel（唯一新增运行时文件）
- Create: `tests/test_task_channel.py`、`tests/test_priority_scheduling.py`、`tests/test_queue_blocking.py`
- Modify: `fish_async_task_core/src/queue/priority.rs`、`fish_async_task/_adapters.py`、`fish_async_task/performance/priority_queue.py`、`fish_async_task/task_manager.py`、`fish_async_task/worker/core.py`（仅类型注解）、`pyproject.toml`、`README.md`、`CHANGELOG.md`、`tests/performance/rust_baseline/baseline_summary.md`、`tests/performance/rust_comparison/test_rust_vs_python.py`

---

### Task 0: 分支 + 测试基线解阻（D1、D8）

**Files:** Modify: `pyproject.toml`, `fish_async_task/performance/priority_queue.py:392-421`; Test: `tests/test_priority_queue.py`

- [ ] Step 1: `git checkout -b feat/priority-scheduling`
- [ ] Step 2: `pyproject.toml` 注册 marker `"slow: 长时间运行的测试"`，dev 依赖加 `pytest-timeout>=2.0.0`；随后同步环境：`uv pip install pytest-timeout psutil --index-url https://pypi.org/simple`（psutil 供 Task 2 使用；镜像源不稳时用官方源）
- [ ] Step 3: 给 `tests/test_priority_queue.py::test_get_ready_tasks` 所在类补 `@pytest.mark.timeout(20)`；运行确认 FAIL（Timeout 而非挂死）
- [ ] Step 4: 修死锁 —— 提取无锁内部判断，`get_ready_tasks` 不再重入：

```python
def _is_ready_locked(self, task_id: str) -> bool:
    if task_id not in self._dependencies:
        return True
    return self._dependencies[task_id].issubset(self._completed_tasks)

def is_ready(self, task_id: str) -> bool:
    with self._lock:
        return self._is_ready_locked(task_id)

def get_ready_tasks(self) -> List[str]:
    with self._lock:
        return [tid for tid in self._dependencies if self._is_ready_locked(tid)]
```

- [ ] Step 5: 运行 `python -m pytest tests/test_priority_queue.py tests/test_adapters.py tests/test_task_manager.py -q --timeout=60` → 全绿
- [ ] Step 6: Commit `fix: 修复 TaskDependencyManager.get_ready_tasks 持锁重入死锁；注册 slow marker`

### Task 1: README / CHANGELOG / 基线报告诚实化（D7，目标②a）

**Files:** Modify: `README.md`, `CHANGELOG.md`, `tests/performance/rust_baseline/baseline_summary.md`

- [ ] Step 1: README 特性行 "性能提升 2-4x" → "并发场景提升 1.2-2.2x（见基线报告）"；性能表内存行改为注明测量口径：tracemalloc 仅统计 Python 堆，Rust 侧常驻内存不在其视野内，绝对数字不可比；表下加"测量方法与局限"小节
- [ ] Step 2: README 快速开始的优先级示例保持不变（本计划将使其真正生效），补一句"数字越小优先级越高，默认 5"
- [ ] Step 3: CHANGELOG 去重 0.3.1 重复"新增"段；新增 `[Unreleased]` 段，预记 D1-D6 修复与 `priority` 参数（含行为变更说明：`priority` 关键字不再透传给任务函数）
- [ ] Step 4: `baseline_summary.md` 内存小节加同样口径警告
- [ ] Step 5: Commit `docs: 修正性能与内存表述，使其与基线数据和测量方法一致`

### Task 2: RSS 口径的内存对比（目标②b）

**Files:** Modify: `tests/performance/rust_comparison/test_rust_vs_python.py:241-266`

- [ ] Step 1: `test_status_storage_memory` 改为双口径输出：保留 tracemalloc（标注"Python 堆"），新增 psutil RSS 差值（gc.collect 后取 `Process().memory_info().rss` 前后差）；断言仅作 sanity（`rss_delta_rust > 0`）
- [ ] Step 2: 运行该测试确认两种口径都有输出
- [ ] Step 3: Commit `test: 内存对比增加 RSS 口径，标注 tracemalloc 局限`

### Task 3: Rust 队列语义修复（D2、D3）

**Files:** Modify: `fish_async_task_core/src/queue/priority.rs`; Test: `tests/test_queue_blocking.py`（先写，红）

- [ ] Step 1: 写失败测试 `tests/test_queue_blocking.py`（对 Rust 适配器；`pytest.mark.timeout(20)`）：
  - 满 + `block=False` → `queue.Full`
  - 满 + `block=True, timeout=0.5` → 0.5s 后 `queue.Full`（当前实现会立即成功 → 红）
  - 满 + `block=True` + 后台线程 0.3s 后 `get` → put 成功且 `qsize()==maxsize`
  - 空 + `block=False` → `queue.Empty`；空 + `block=True, timeout=0.3` → `queue.Empty`
  - 满 + `block=True` + 后台线程 0.3s 后 `get_batch(1)`（直接调 `adapter._rust.get_batch(1)`）→ 阻塞的 put 被唤醒
- [ ] Step 2: 运行确认 FAIL
- [ ] Step 3: 改 Rust：状态改为 `Arc<(Mutex<QueueState>, Condvar /*not_empty*/, Condvar /*not_full*/)>`；`put → PyResult<bool>`（满时 block=false 返回 `Ok(false)`；block=true 在 not_full 上带 deadline 等待，超时 `Ok(false)`；成功 push 后 notify not_empty）；`get → PyResult<Option<String>>`（空时非阻塞/超时返回 `Ok(None)`；成功 pop 后 notify not_full）；`remove` 成功后 notify not_full，`clear` 必须 **notify_all** not_full（一次释放全部容量，notify_one 会让其余阻塞 putter 睡死）；**`put_batch` 成功后 notify_all not_empty，`get_batch` 弹出 ≥1 项后 notify_all not_full**（漏掉会让阻塞中的 put 睡死到下一次单个 get）。核心 put 等待循环：

```rust
if self.maxsize > 0 {
    let deadline = timeout.map(|t| std::time::Instant::now() + Duration::from_secs_f64(t));
    while state.task_ids.len() >= self.maxsize {
        if !block { return Ok(false); }
        match deadline {
            Some(dl) => {
                let now = std::time::Instant::now();
                if now >= dl { return Ok(false); }
                not_full.wait_for(&mut state, dl - now);
            }
            None => { not_full.wait(&mut state); }
        }
    }
}
```

- [ ] Step 4: `maturin develop --release` 重建
- [ ] Step 5: 同步改适配器（与 Task 4 的 D4 一并）：`put` 返回 False → `raise queue.Full`；`get` 返回 None → `raise queue.Empty`；删除 `_tasks` 字典；**基类与两个实现新增 `clear() -> None`**（Rust 转发 `self._rust.clear()`，Python 转发 `self._inner.clear()`——两个底层实现均已有 clear，只是适配器没暴露）
- [ ] Step 6: 运行 Step 1 测试 → 绿；跑 `tests/test_adapters.py tests/test_rust_compat.py` 回归
- [ ] Step 7: Commit `fix(rust): 优先级队列 put 实现真阻塞与超时，get 空队列返回 None；适配器映射标准 queue 异常并移除泄漏映射`

### Task 4: 纯 Python 队列阻塞语义修复（D5）+ FIFO tie-break

**Files:** Modify: `fish_async_task/performance/priority_queue.py`; Test: `tests/test_queue_blocking.py`（参数化覆盖 Python 适配器）

- [ ] Step 1: 把 Task 3 的测试参数化为 `[rust, python]` 双实现（python 侧直接构造 `_PythonPriorityTaskQueueAdapter`；get_batch 唤醒用例是 rust-only，python 参数下 skip），运行确认 python 侧 FAIL
- [ ] Step 2: 重写 `put/get` 为 deadline 循环（monotonic 时钟），修正 `block=True` 分支；`PrioritizedTask.submit_time` 改 `compare=True` 使同优先级 FIFO（与 Rust 语义一致）
- [ ] Step 3: 测试全绿；跑 `tests/test_priority_queue.py` 回归
- [ ] Step 4: Commit `fix: 纯 Python 优先级队列阻塞语义与 FIFO tie-break`

### Task 5: TaskChannel + TaskManager 接入（D6，目标①主体）

**Files:** Create: `fish_async_task/task_channel.py`, `tests/test_task_channel.py`, `tests/test_priority_scheduling.py`; Modify: `fish_async_task/task_manager.py`, `fish_async_task/worker/core.py`（类型注解）

- [ ] Step 1: 写失败测试 `tests/test_task_channel.py`：put_task/get 往返、优先级顺序、`get(timeout)` 空 → `queue.Empty`、`put_nowait(None)` 哨兵 → `get` 返回 `None`、满时 `put_task` → `queue.Full`（且旁路表回滚不残留）、`qsize/empty/full/task_done`、`clear()` 后 `qsize()==0` 且 get 不返回孤儿、孤儿场景下 `get(timeout=0.5)` 总耗时 ≤~0.6s（超时折算）
- [ ] Step 1b: 运行 `python -m pytest tests/test_task_channel.py -q --timeout=30` → 确认 FAIL（ModuleNotFoundError）
- [ ] Step 2: 实现 `task_channel.py`：

```python
"""任务通道：优先级队列 + 任务载荷旁路表，对 worker 提供 queue.Queue 兼容接口。"""
import queue
import threading
import time
import uuid
from typing import Dict, Optional

from ._adapters import PriorityTaskQueueAdapter, get_priority_queue
from .types import TaskTuple

_SENTINEL_PREFIX = "__fish_shutdown__:"


class TaskChannel:
    """包装优先级队列，worker 侧接口与 queue.Queue 兼容
    （get/put_nowait/put/qsize/empty/full/task_done）。"""

    def __init__(self, maxsize: int = 1000, default_priority: int = 5,
                 shutdown_priority: int = 2**31 - 1) -> None:
        self._queue: PriorityTaskQueueAdapter = get_priority_queue(maxsize=maxsize)
        self._default_priority = default_priority
        self._shutdown_priority = shutdown_priority  # 最低优先级：先清存量任务再退出
        self._payloads: Dict[str, TaskTuple] = {}
        self._payload_lock = threading.Lock()

    def put_task(self, task: TaskTuple, priority: Optional[int] = None,
                 block: bool = False, timeout: Optional[float] = None) -> None:
        task_id = task[0]
        with self._payload_lock:
            self._payloads[task_id] = task
        try:
            self._queue.put(task_id, priority if priority is not None else self._default_priority,
                            block=block, timeout=timeout)
        except queue.Full:
            with self._payload_lock:
                self._payloads.pop(task_id, None)
            raise

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[TaskTuple]:
        # 孤儿 id（clear/取消竞态遗留）重试时折算剩余超时，总等待不超过调用者给定的 timeout
        deadline = None if timeout is None else time.monotonic() + timeout
        remaining = timeout
        while True:
            task_id = self._queue.get(block=block, timeout=remaining)  # 空 → queue.Empty
            if task_id.startswith(_SENTINEL_PREFIX):
                return None  # 关闭哨兵，与旧 queue.Queue 的 None 语义一致
            with self._payload_lock:
                payload = self._payloads.pop(task_id, None)
            if payload is not None:
                return payload
            if not block:
                raise queue.Empty()
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty()

    def put_nowait(self, item: Optional[TaskTuple]) -> None:
        if item is None:
            self._queue.put(_SENTINEL_PREFIX + uuid.uuid4().hex,
                            self._shutdown_priority, block=False)
        else:
            self.put_task(item, block=False)

    def put(self, item: Optional[TaskTuple], block: bool = True,
            timeout: Optional[float] = None) -> None:
        if item is None:
            self._queue.put(_SENTINEL_PREFIX + uuid.uuid4().hex,
                            self._shutdown_priority, block=block, timeout=timeout)
        else:
            self.put_task(item, block=block, timeout=timeout)

    def qsize(self) -> int:
        return self._queue.qsize()

    def empty(self) -> bool:
        return self._queue.empty()

    def full(self) -> bool:
        return self._queue.full()

    def task_done(self) -> None:  # queue.Queue 兼容占位；本项目未使用 join()
        pass

    def clear(self) -> None:
        # 先清底层队列再清旁路表：并发 get 最多拿到孤儿 id 后按剩余超时重试，
        # 不会拿到已清除任务的载荷
        self._queue.clear()
        with self._payload_lock:
            self._payloads.clear()
```

（注意：哨兵 id 必须唯一 —— Rust 侧 `task_ids` 是 HashSet，重复 id 会导致 qsize 少计。`empty()`/`full()` 必须转发：`tests/test_task_manager.py:187` 断言 `task_queue.full()`，`tests/performance/workload_baseline.py:41` 使用 `task_queue.empty()`。）

- [ ] Step 3: 运行 `python -m pytest tests/test_task_channel.py -q --timeout=30` → 全绿（TaskChannel 单元层完成）
- [ ] Step 4: 写失败测试 `tests/test_priority_scheduling.py`（TaskManager 尚未接入，此时必红）：
  - `submit_task` 接受 `priority` 且不透传给任务函数（任务函数无 priority 形参也不报 TypeError）——当前实现会 TypeError → 红
  - 单 worker + Event 闸门：先提交一个占住 worker 的任务，再乱序提交 priority 10/1/5 三个任务，放闸后按 1→5→10 完成（用完成时间戳或记录列表断言）——当前 FIFO → 红
  - 队列满：`TaskManager` 子类把 `DEFAULT_QUEUE_SIZE` 调小 → `TaskQueueFullError`
  - `shutdown()` 后 worker 全部退出（复用现有测试的 `_instances.clear()` 清理模式）
- [ ] Step 5: 运行 `python -m pytest tests/test_priority_scheduling.py -q --timeout=60` → 确认 FAIL
- [ ] Step 6: `task_manager.py`：`_init_basic_structures` 用 `TaskChannel(maxsize=self.DEFAULT_QUEUE_SIZE)` 替换 `queue.Queue`；新增类常量 `DEFAULT_TASK_PRIORITY = 5`；`submit_task` 增加关键字参数 `priority: Optional[int] = None`，校验范围（非 None 时须为 int 且 `0 <= priority < 2**31 - 1`，越界抛 ValueError——上界排除哨兵优先级，也避免 Rust i32 OverflowError），提交走 `self.task_queue.put_task((task_id, func, args, kwargs), priority=priority, block=block, timeout=timeout)`；docstring 说明优先级语义、有效范围与行为变更；`shutdown()` 在线程退出后调用 `self.task_queue.clear()`
- [ ] Step 7: `worker/core.py` 类型注解 `"queue.Queue[TaskTuple]"` → `"TaskChannel"`（TYPE_CHECKING 导入），主循环逻辑零改动（`test_worker.py` 直接传 `queue.Queue` 的用例靠 duck-typing 不受影响）
- [ ] Step 8: 全部转绿；跑 `tests/test_task_manager.py tests/test_worker.py tests/test_task_cancellation.py -q --timeout=120` 回归
- [ ] Step 9: Commit `feat: submit_task 支持 priority，任务队列切换为优先级通道（TaskChannel）`

### Task 6: 全量回归 + 收尾

- [ ] Step 1: `python -m pytest tests/ -q --ignore=tests/performance --timeout=120`（含 test_memory_leaks，marker 已注册）→ 全绿；失败则修复后重跑
- [ ] Step 2: `python examples/basic_usage.py` 冒烟
- [ ] Step 3: `grep -rn "task_queue\.\|_core\|PyPriorityTaskQueue" tests/performance/ scripts/` 核对直接触碰内部 API 的脚本（已知 `workload_baseline.py:41` 用 `task_queue.empty()`——TaskChannel 已转发，应无需改；如有直接调用 `_core` put/get 的脚本需随新签名调整），并运行 `python -m pytest tests/performance/rust_comparison/ -q --timeout=120` 验证
- [ ] Step 4: CHANGELOG `[Unreleased]` 核对；README 优先级示例与实际行为核对
- [ ] Step 5: Commit `docs: 更新 CHANGELOG 与 README 优先级说明`

## 风险与决策记录

- **行为变更**：`submit_task(..., priority=N)` 不再把 `priority` 透传给任务函数——这是把 README 长期承诺的 API 落地，透传行为本就是缺陷；CHANGELOG 明示。
- **`task_queue` 属性类型变更**：`TaskManager.task_queue` 是无下划线公开属性，类型从 `queue.Queue` 变为 `TaskChannel`。接口兼容（get/put/put_nowait/qsize/empty/full/task_done 均转发），但依赖 `isinstance(tm.task_queue, queue.Queue)` 或 `queue.Queue` 私有属性的外部代码会破坏；CHANGELOG 明示。
- **FIFO 弱化为"近似 FIFO"**：默认优先级统一为 5；同优先级按 `submit_time` 排序，但同一时钟刻度内提交的任务在二叉堆（不稳定）中顺序不确定——旧 `queue.Queue` 是严格 FIFO，高频提交场景可观测差异。如需严格 FIFO 需引入单调递增序号第三键（本计划不做，如实记录）。
- **哨兵优先级取最低**：保持旧 FIFO"先清存量任务再退出"的关闭语义。
- **Rust `_core` 私有 API 签名变更**（put→bool，get→Option，新增 clear 转发）：`_core` 是内部模块，外部经由适配器，风险受控；直接调用方在 Task 6 Step 3 grep 核对。
- **不做**：任务依赖接入主流程、进程池、free-threading（另立计划）。
