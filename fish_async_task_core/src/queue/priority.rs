//! 优先级队列实现
//!
//! 使用 BinaryHeap 实现线程安全的优先级队列。
//! 使用双 Condvar（not_empty / not_full）实现 put/get 双向阻塞，
//! 使用 lazy deletion 优化 remove 操作。

use crate::types::PrioritizedTask;
use parking_lot::{Condvar, Mutex};
use pyo3::prelude::*;
use std::collections::HashSet;
use std::sync::Arc;
use std::time::Duration;

/// 优先级任务队列内部状态
struct QueueState {
    queue: std::collections::BinaryHeap<PrioritizedTask>,
    task_ids: HashSet<String>,
    /// 已删除的任务 ID（lazy deletion）
    cancelled: HashSet<String>,
}

/// 队列同步原语：状态锁 + 双条件变量
struct QueueSync {
    state: Mutex<QueueState>,
    /// get 等待此条件（有新任务时被通知）
    not_empty: Condvar,
    /// put 等待此条件（有空间腾出时被通知）
    not_full: Condvar,
}

/// 优先级任务队列
///
/// 线程安全的优先级队列，支持双向阻塞操作：
/// - `put`：队列满时可阻塞等待空间（Condvar，支持超时）
/// - `get`：队列空时可阻塞等待任务（Condvar，支持超时）
///
/// 空/满不抛异常，而是通过返回值表达（put → bool，get → Option），
/// 由 Python 适配器统一映射为标准库 queue.Full / queue.Empty。
/// 使用 lazy deletion 避免 remove 时重建整个堆。
#[pyclass]
pub struct PyPriorityTaskQueue {
    sync: Arc<QueueSync>,
    maxsize: usize,
}

#[pymethods]
impl PyPriorityTaskQueue {
    /// 创建新的优先级队列
    ///
    /// Args:
    ///     maxsize: 最大队列大小，0 表示无限制
    #[new]
    fn new(maxsize: usize) -> PyResult<Self> {
        let state = QueueState {
            queue: std::collections::BinaryHeap::new(),
            task_ids: HashSet::new(),
            cancelled: HashSet::new(),
        };

        Ok(Self {
            sync: Arc::new(QueueSync {
                state: Mutex::new(state),
                not_empty: Condvar::new(),
                not_full: Condvar::new(),
            }),
            maxsize,
        })
    }

    /// 向队列添加任务
    ///
    /// Args:
    ///     priority: 任务优先级
    ///     task_id: 任务ID
    ///     submit_time: 提交时间
    ///     block: 队列满时是否阻塞等待空间
    ///     timeout: 阻塞等待的超时时间（秒），None 表示无限等待
    ///
    /// Returns:
    ///     true 表示入队成功；false 表示队列满（非阻塞或等待超时）
    #[pyo3(signature = (priority, task_id, submit_time, block=true, timeout=None))]
    fn put(
        &self,
        py: Python,
        priority: i32,
        task_id: String,
        submit_time: f64,
        block: bool,
        timeout: Option<f64>,
    ) -> PyResult<bool> {
        py.allow_threads(|| {
            let mut state = self.sync.state.lock();

            if self.maxsize > 0 {
                let deadline = timeout.map(|t| std::time::Instant::now() + Duration::from_secs_f64(t));
                while state.task_ids.len() >= self.maxsize {
                    if !block {
                        return Ok(false);
                    }
                    match deadline {
                        Some(dl) => {
                            let now = std::time::Instant::now();
                            if now >= dl {
                                return Ok(false);
                            }
                            self.sync.not_full.wait_for(&mut state, dl - now);
                        }
                        None => {
                            self.sync.not_full.wait(&mut state);
                        }
                    }
                }
            }

            let task = PrioritizedTask {
                priority,
                task_id: task_id.clone(),
                submit_time,
            };
            state.queue.push(task);
            state.task_ids.insert(task_id);
            self.sync.not_empty.notify_one();
            Ok(true)
        })
    }

    /// 从队列获取任务ID
    ///
    /// Args:
    ///     block: 队列空时是否阻塞等待任务
    ///     timeout: 阻塞等待的超时时间（秒），None 表示无限等待
    ///
    /// Returns:
    ///     Some(task_id) 表示获取成功；None 表示队列空（非阻塞或等待超时）
    #[pyo3(signature = (block=true, timeout=None))]
    fn get(&self, py: Python, block: bool, timeout: Option<f64>) -> PyResult<Option<String>> {
        py.allow_threads(|| {
            let mut state = self.sync.state.lock();

            if block {
                let deadline = timeout.map(|t| std::time::Instant::now() + Duration::from_secs_f64(t));

                loop {
                    if let Some(task_id) = pop_valid_task(&mut state) {
                        self.sync.not_full.notify_one();
                        return Ok(Some(task_id));
                    }

                    match deadline {
                        Some(dl) => {
                            let now = std::time::Instant::now();
                            if now >= dl {
                                return Ok(None);
                            }
                            self.sync.not_empty.wait_for(&mut state, dl - now);
                        }
                        None => {
                            self.sync.not_empty.wait(&mut state);
                        }
                    }
                }
            } else if let Some(task_id) = pop_valid_task(&mut state) {
                self.sync.not_full.notify_one();
                Ok(Some(task_id))
            } else {
                Ok(None)
            }
        })
    }

    /// 从队列移除指定任务
    ///
    /// 使用 lazy deletion，仅标记删除，在下次 get 时跳过。
    ///
    /// Args:
    ///     task_id: 要移除的任务ID
    ///
    /// Returns:
    ///     是否成功移除
    fn remove(&self, task_id: &str) -> PyResult<bool> {
        let mut state = self.sync.state.lock();

        if state.task_ids.remove(task_id) {
            state.cancelled.insert(task_id.to_string());
            // 逻辑容量已释放（task_ids 决定 full 判定），唤醒等待空间的 put
            self.sync.not_full.notify_one();
            Ok(true)
        } else {
            Ok(false)
        }
    }

    /// 获取队列大小
    fn qsize(&self) -> PyResult<usize> {
        let state = self.sync.state.lock();
        Ok(state.task_ids.len())
    }

    /// 检查队列是否为空
    fn empty(&self) -> PyResult<bool> {
        let state = self.sync.state.lock();
        Ok(state.task_ids.is_empty())
    }

    /// 检查队列是否已满
    fn full(&self) -> PyResult<bool> {
        if self.maxsize == 0 {
            return Ok(false);
        }
        let state = self.sync.state.lock();
        Ok(state.task_ids.len() >= self.maxsize)
    }

    /// 清空队列
    fn clear(&self) -> PyResult<()> {
        let mut state = self.sync.state.lock();
        state.queue.clear();
        state.task_ids.clear();
        state.cancelled.clear();
        // 一次释放全部容量，必须唤醒所有等待空间的 put
        self.sync.not_full.notify_all();
        Ok(())
    }

    /// 批量向队列添加任务
    ///
    /// Args:
    ///     items: (priority, task_id, submit_time) 元组列表
    ///
    /// Returns:
    ///     成功添加的数量（队列满时提前停止，不阻塞）
    fn put_batch(&self, py: Python, items: Vec<(i32, String, f64)>) -> PyResult<usize> {
        py.allow_threads(|| {
            let mut state = self.sync.state.lock();
            let mut count = 0;

            for (priority, task_id, submit_time) in items {
                if self.maxsize > 0 && state.task_ids.len() >= self.maxsize {
                    break;
                }

                let task = PrioritizedTask {
                    priority,
                    task_id: task_id.clone(),
                    submit_time,
                };
                state.queue.push(task);
                state.task_ids.insert(task_id);
                count += 1;
            }

            if count > 0 {
                self.sync.not_empty.notify_all();
            }

            Ok(count)
        })
    }

    /// 批量从队列获取任务ID
    ///
    /// Args:
    ///     max_count: 最大获取数量，None 表示获取所有
    ///
    /// Returns:
    ///     获取的任务ID列表（按优先级排序）
    #[pyo3(signature = (max_count=None))]
    fn get_batch(&self, py: Python, max_count: Option<usize>) -> PyResult<Vec<String>> {
        py.allow_threads(|| {
            let mut state = self.sync.state.lock();
            let mut result = Vec::new();
            let limit = max_count.unwrap_or(usize::MAX);

            while result.len() < limit {
                match pop_valid_task(&mut state) {
                    Some(task_id) => result.push(task_id),
                    None => break,
                }
            }

            if !result.is_empty() {
                // 批量腾出多个空位，唤醒所有等待空间的 put
                self.sync.not_full.notify_all();
            }

            Ok(result)
        })
    }
}

/// 从队列中弹出一个有效的（未被 lazy deletion 标记的）任务
fn pop_valid_task(state: &mut QueueState) -> Option<String> {
    while let Some(task) = state.queue.pop() {
        if state.cancelled.remove(&task.task_id) {
            // 跳过已被 lazy deletion 标记的任务
            continue;
        }
        state.task_ids.remove(&task.task_id);
        return Some(task.task_id);
    }
    None
}
