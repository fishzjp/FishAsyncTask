//! 优先级队列实现
//!
//! 使用 BinaryHeap 实现线程安全的优先级队列。
//! 使用 Condvar 替代 busy-wait，使用 lazy deletion 优化 remove 操作。

use crate::types::PrioritizedTask;
use parking_lot::{Condvar, Mutex};
use pyo3::exceptions::PyException;
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

/// 优先级任务队列
///
/// 线程安全的优先级队列，支持阻塞操作。
/// 使用 Condvar 替代 busy-wait 实现高效阻塞获取。
/// 使用 lazy deletion 避免重建整个堆。
#[pyclass]
pub struct PyPriorityTaskQueue {
    state: Arc<(Mutex<QueueState>, Condvar)>,
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
            state: Arc::new((Mutex::new(state), Condvar::new())),
            maxsize,
        })
    }

    /// 向队列添加任务
    ///
    /// Args:
    ///     priority: 任务优先级
    ///     task_id: 任务ID
    ///     submit_time: 提交时间
    ///     block: 是否阻塞等待队列有空间
    ///     timeout: 超时时间（秒），None 表示无限等待
    #[pyo3(signature = (priority, task_id, submit_time, block=true, _timeout=None))]
    fn put(
        &self,
        py: Python,
        priority: i32,
        task_id: String,
        submit_time: f64,
        block: bool,
        _timeout: Option<f64>,
    ) -> PyResult<()> {
        py.allow_threads(|| {
            let (lock, cvar) = &*self.state;
            let mut state = lock.lock();

            // 检查队列是否已满
            if self.maxsize > 0 && state.task_ids.len() >= self.maxsize && !block {
                return Err(PyErr::new::<PyException, _>("Queue is full".to_string()));
            }

            let task = PrioritizedTask {
                priority,
                task_id: task_id.clone(),
                submit_time,
            };
            state.queue.push(task);
            state.task_ids.insert(task_id);
            cvar.notify_one();
            Ok(())
        })
    }

    /// 从队列获取任务ID
    ///
    /// Args:
    ///     block: 是否阻塞等待队列有任务
    ///     timeout: 超时时间（秒），None 表示无限等待
    ///
    /// Returns:
    ///     获取的任务ID
    #[pyo3(signature = (block=true, timeout=None))]
    fn get(&self, py: Python, block: bool, timeout: Option<f64>) -> PyResult<String> {
        py.allow_threads(|| {
            let (lock, cvar) = &*self.state;
            let mut state = lock.lock();

            if block {
                let deadline = timeout.map(Duration::from_secs_f64).map(|d| {
                    std::time::Instant::now() + d
                });

                loop {
                    if let Some(task_id) = pop_valid_task(&mut state) {
                        return Ok(task_id);
                    }

                    match deadline {
                        Some(dl) => {
                            let now = std::time::Instant::now();
                            if now >= dl {
                                return Err(PyErr::new::<PyException, _>("Queue is empty".to_string()));
                            }
                            let remaining = dl - now;
                            cvar.wait_for(&mut state, remaining);
                        }
                        None => {
                            cvar.wait(&mut state);
                        }
                    }
                }
            } else if let Some(task_id) = pop_valid_task(&mut state) {
                Ok(task_id)
            } else {
                Err(PyErr::new::<PyException, _>("Queue is empty".to_string()))
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
        let (lock, _) = &*self.state;
        let mut state = lock.lock();

        if state.task_ids.remove(task_id) {
            state.cancelled.insert(task_id.to_string());
            Ok(true)
        } else {
            Ok(false)
        }
    }

    /// 获取队列大小
    fn qsize(&self) -> PyResult<usize> {
        let (lock, _) = &*self.state;
        let state = lock.lock();
        Ok(state.task_ids.len())
    }

    /// 检查队列是否为空
    fn empty(&self) -> PyResult<bool> {
        let (lock, _) = &*self.state;
        let state = lock.lock();
        Ok(state.task_ids.is_empty())
    }

    /// 检查队列是否已满
    fn full(&self) -> PyResult<bool> {
        if self.maxsize == 0 {
            return Ok(false);
        }
        let (lock, _) = &*self.state;
        let state = lock.lock();
        Ok(state.task_ids.len() >= self.maxsize)
    }

    /// 清空队列
    fn clear(&self) -> PyResult<()> {
        let (lock, cvar) = &*self.state;
        let mut state = lock.lock();
        state.queue.clear();
        state.task_ids.clear();
        state.cancelled.clear();
        cvar.notify_all();
        Ok(())
    }

    /// 批量向队列添加任务
    ///
    /// Args:
    ///     items: (priority, task_id, submit_time) 元组列表
    ///
    /// Returns:
    ///     成功添加的数量
    fn put_batch(&self, py: Python, items: Vec<(i32, String, f64)>) -> PyResult<usize> {
        py.allow_threads(|| {
            let (lock, cvar) = &*self.state;
            let mut state = lock.lock();
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
                cvar.notify_all();
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
            let (lock, _) = &*self.state;
            let mut state = lock.lock();
            let mut result = Vec::new();
            let limit = max_count.unwrap_or(usize::MAX);

            while result.len() < limit {
                match pop_valid_task(&mut state) {
                    Some(task_id) => result.push(task_id),
                    None => break,
                }
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
