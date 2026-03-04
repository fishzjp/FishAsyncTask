//! 优先级队列实现
//!
//! 使用 BinaryHeap 实现线程安全的优先级队列。

use crate::types::PrioritizedTask;
use parking_lot::Mutex;
use pyo3::prelude::*;
use pyo3::exceptions::PyException;
use std::collections::HashSet;
use std::sync::Arc;
use std::time::Duration;

/// 优先级任务队列
///
/// 线程安全的优先级队列，支持阻塞操作。
#[pyclass]
pub struct PyPriorityTaskQueue {
    queue: Arc<Mutex<std::collections::BinaryHeap<PrioritizedTask>>>,
    task_ids: Arc<Mutex<HashSet<String>>>,
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
        let queue = Arc::new(Mutex::new(std::collections::BinaryHeap::new()));
        let task_ids = Arc::new(Mutex::new(HashSet::new()));

        Ok(Self {
            queue,
            task_ids,
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
    #[pyo3(signature = (priority, task_id, submit_time, block=true, timeout=None))]
    fn put(
        &self,
        py: Python,
        priority: i32,
        task_id: String,
        submit_time: f64,
        block: bool,
        timeout: Option<f64>,
    ) -> PyResult<()> {
        py.allow_threads(|| {
            // 检查队列是否已满
            {
                let ids = self.task_ids.lock();
                if self.maxsize > 0 && ids.len() >= self.maxsize && !block {
                    return Err(PyErr::new::<PyException, _>(
                        "Queue is full".to_string(),
                    ));
                }
            }

            // 添加到队列
            {
                let task = PrioritizedTask {
                    priority,
                    task_id: task_id.clone(),
                    submit_time,
                };
                let mut queue = self.queue.lock();
                queue.push(task);
                let mut ids = self.task_ids.lock();
                ids.insert(task_id);
            }

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
            let queue = self.queue.clone();
            let task_ids = self.task_ids.clone();

            if block {
                let duration = timeout.map(|t| Duration::from_secs_f64(t));
                let start = std::time::Instant::now();

                loop {
                    {
                        let mut q = queue.lock();
                        if let Some(task) = q.pop() {
                            let mut ids = task_ids.lock();
                            ids.remove(&task.task_id);
                            return Ok(task.task_id);
                        }
                    }

                    if let Some(d) = duration {
                        if start.elapsed() >= d {
                            return Err(PyErr::new::<PyException, _>(
                                "Queue is empty".to_string(),
                            ));
                        }
                    }

                    std::thread::sleep(Duration::from_millis(1));
                }
            } else {
                let mut q = queue.lock();
                if let Some(task) = q.pop() {
                    let mut ids = task_ids.lock();
                    ids.remove(&task.task_id);
                    Ok(task.task_id)
                } else {
                    Err(PyErr::new::<PyException, _>(
                        "Queue is empty".to_string(),
                    ))
                }
            }
        })
    }

    /// 从队列移除指定任务
    ///
    /// Args:
    ///     task_id: 要移除的任务ID
    ///
    /// Returns:
    ///     是否成功移除
    fn remove(&self, task_id: &str) -> PyResult<bool> {
        let mut queue = self.queue.lock();
        let mut ids = self.task_ids.lock();

        if ids.remove(task_id) {
            // 重建队列（不包括被移除的任务）
            let mut new_queue = std::collections::BinaryHeap::new();
            while let Some(task) = queue.pop() {
                if task.task_id != task_id {
                    new_queue.push(task);
                }
            }
            *queue = new_queue;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    /// 获取队列大小
    fn qsize(&self) -> PyResult<usize> {
        let ids = self.task_ids.lock();
        Ok(ids.len())
    }

    /// 检查队列是否为空
    fn empty(&self) -> PyResult<bool> {
        let ids = self.task_ids.lock();
        Ok(ids.is_empty())
    }

    /// 检查队列是否已满
    fn full(&self) -> PyResult<bool> {
        if self.maxsize == 0 {
            return Ok(false);
        }
        let ids = self.task_ids.lock();
        Ok(ids.len() >= self.maxsize)
    }

    /// 清空队列
    fn clear(&self) -> PyResult<()> {
        let mut queue = self.queue.lock();
        let mut ids = self.task_ids.lock();
        queue.clear();
        ids.clear();
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
            let mut count = 0;
            let mut queue = self.queue.lock();
            let mut ids = self.task_ids.lock();

            for (priority, task_id, submit_time) in items {
                // 检查队列是否已满
                if self.maxsize > 0 && ids.len() >= self.maxsize {
                    break;
                }

                let task = PrioritizedTask {
                    priority,
                    task_id: task_id.clone(),
                    submit_time,
                };
                queue.push(task);
                ids.insert(task_id);
                count += 1;
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
            let mut queue = self.queue.lock();
            let mut ids = self.task_ids.lock();
            let mut result = Vec::new();

            let limit = max_count.unwrap_or(usize::MAX);

            while result.len() < limit {
                if let Some(task) = queue.pop() {
                    ids.remove(&task.task_id);
                    result.push(task.task_id);
                } else {
                    break;
                }
            }

            Ok(result)
        })
    }
}
