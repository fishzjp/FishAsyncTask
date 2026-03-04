//! 分片任务状态存储
//!
//! 使用 DashMap 实现无锁并发分片存储。

use crate::types::TaskStatusDict;
use dashmap::DashMap;
use parking_lot::RwLock;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::BinaryHeap;
use std::sync::Arc;
use std::time::{Duration, Instant};

/// 分片任务状态存储
///
/// 使用 DashMap 实现无锁并发分片存储，支持高并发读写。
#[pyclass]
pub struct PyShardedTaskStatus {
    shards: Vec<Arc<DashMap<String, TaskStatusDict>>>,
    expiry_heaps: Vec<Arc<RwLock<BinaryHeap<(Instant, String)>>>>,
    shard_count: usize,
    ttl: Duration,
}

#[pymethods]
impl PyShardedTaskStatus {
    /// 创建新的分片状态存储
    ///
    /// Args:
    ///     shard_count: 分片数量
    ///     ttl: 任务状态生存时间（秒）
    #[new]
    #[pyo3(signature = (shard_count, ttl))]
    fn new(shard_count: usize, ttl: u64) -> PyResult<Self> {
        let mut shards = Vec::with_capacity(shard_count);
        let mut expiry_heaps = Vec::with_capacity(shard_count);

        for _ in 0..shard_count {
            shards.push(Arc::new(DashMap::new()));
            expiry_heaps.push(Arc::new(RwLock::new(BinaryHeap::new())));
        }

        Ok(Self {
            shards,
            expiry_heaps,
            shard_count,
            ttl: Duration::from_secs(ttl),
        })
    }

    /// 获取任务状态
    ///
    /// Args:
    ///     task_id: 任务ID
    ///
    /// Returns:
    ///     任务状态字典，如果不存在返回 None
    fn get_status(&self, py: Python, task_id: &str) -> PyResult<PyObject> {
        let shard_idx = self._get_shard_index(task_id);
        let shard = &self.shards[shard_idx];

        if let Some(status) = shard.get(task_id) {
            // 转换为 Python 字典
            let dict = PyDict::new(py);
            if let Some(ref s) = status.status {
                dict.set_item("status", s)?;
            }
            if let Some(t) = status.submit_time {
                dict.set_item("submit_time", t)?;
            }
            if let Some(t) = status.start_time {
                dict.set_item("start_time", t)?;
            }
            if let Some(t) = status.end_time {
                dict.set_item("end_time", t)?;
            }
            if let Some(ref result) = status.result {
                dict.set_item("result", result.clone_ref(py))?;
            }
            if let Some(ref e) = status.error {
                dict.set_item("error", e)?;
            }
            if let Some(ref w) = status.worker_id {
                dict.set_item("worker_id", w)?;
            }
            Ok(dict.into())
        } else {
            Ok(py.None())
        }
    }

    /// 更新任务状态
    ///
    /// Args:
    ///     task_id: 任务ID
    ///     status: 任务状态字典
    fn update_status(&self, _py: Python, task_id: &str, status: &Bound<'_, PyDict>) -> PyResult<()> {
        let shard_idx = self._get_shard_index(task_id);
        let shard = &self.shards[shard_idx];

        // 从 Python 字典提取字段
        let task_status = TaskStatusDict {
            status: status.get_item("status")?.map(|v| v.extract::<String>().unwrap_or_default()),
            submit_time: status.get_item("submit_time")?.and_then(|v| v.extract::<f64>().ok()),
            start_time: status.get_item("start_time")?.and_then(|v| v.extract::<f64>().ok()),
            end_time: status.get_item("end_time")?.and_then(|v| v.extract::<f64>().ok()),
            result: status.get_item("result")?.map(|v| v.into()),
            error: status.get_item("error")?.map(|v| v.extract::<String>().unwrap_or_default()),
            worker_id: status.get_item("worker_id")?.map(|v| v.extract::<String>().unwrap_or_default()),
        };

        // 如果任务已完成或失败，添加到过期堆
        if task_status.status.as_deref() == Some("completed")
            || task_status.status.as_deref() == Some("failed")
        {
            if let Some(_end_time) = task_status.end_time {
                let expiry_time = Instant::now() + self.ttl;
                let mut heap = self.expiry_heaps[shard_idx].write();
                heap.push((expiry_time, task_id.to_string()));
            }
        }

        shard.insert(task_id.to_string(), task_status);
        Ok(())
    }

    /// 移除任务状态
    ///
    /// Args:
    ///     task_id: 任务ID
    fn remove_status(&self, task_id: &str) -> PyResult<bool> {
        let shard_idx = self._get_shard_index(task_id);
        let shard = &self.shards[shard_idx];
        Ok(shard.remove(task_id).is_some())
    }

    /// 清理过期任务
    ///
    /// Args:
    ///     max_cleanup: 最大清理数量，None 表示清理所有过期任务
    ///
    /// Returns:
    ///     清理的任务数量
    #[pyo3(signature = (max_cleanup=None))]
    fn cleanup_expired(&self, py: Python, max_cleanup: Option<usize>) -> PyResult<usize> {
        py.allow_threads(|| {
            let now = Instant::now();
            let mut cleaned_count = 0;

            for shard_idx in 0..self.shard_count {
                if let Some(limit) = max_cleanup {
                    if cleaned_count >= limit {
                        break;
                    }
                }

                let shard = &self.shards[shard_idx];
                let mut heap = self.expiry_heaps[shard_idx].write();

                while let Some(&(expiry_time, ref task_id)) = heap.peek() {
                    if let Some(limit) = max_cleanup {
                        if cleaned_count >= limit {
                            break;
                        }
                    }

                    if expiry_time > now {
                        break;
                    }

                    let task_id = heap.pop().unwrap().1;
                    if shard.remove(&task_id).is_some() {
                        cleaned_count += 1;
                    }
                }
            }

            Ok(cleaned_count)
        })
    }

    /// 获取总任务数量
    fn get_total_count(&self) -> PyResult<usize> {
        let mut count = 0;
        for shard in &self.shards {
            count += shard.len();
        }
        Ok(count)
    }

    /// 清空所有任务状态
    fn clear_all(&self) -> PyResult<()> {
        for shard in &self.shards {
            shard.clear();
        }
        for heap in &self.expiry_heaps {
            heap.write().clear();
        }
        Ok(())
    }

    /// 批量获取状态
    ///
    /// Args:
    ///     task_ids: 任务ID列表
    ///
    /// Returns:
    ///     任务状态列表（与输入顺序相同，不存在的任务对应位置为 None）
    fn get_status_batch(&self, py: Python, task_ids: Vec<String>) -> PyResult<PyObject> {
        let results: PyResult<Vec<PyObject>> = task_ids
            .into_iter()
            .map(|task_id| self.get_status(py, &task_id))
            .collect();

        Ok(results?.into_py(py))
    }

    /// 批量更新状态
    ///
    /// Args:
    ///     items: (task_id, status_dict) 元组列表
    ///
    /// Returns:
    ///     成功更新的数量
    fn update_status_batch(&self, py: Python, items: Vec<(String, PyObject)>) -> PyResult<usize> {
        py.allow_threads(|| {
            let mut count = 0;
            for (task_id, status_obj) in items {
                Python::with_gil(|py| {
                    if let Ok(status_dict) = status_obj.extract::<Bound<'_, PyDict>>(py) {
                        if self.update_status(py, &task_id, &status_dict).is_ok() {
                            count += 1;
                        }
                    }
                });
            }
            Ok(count)
        })
    }
}

impl PyShardedTaskStatus {
    /// 根据 task_id 计算分片索引
    fn _get_shard_index(&self, task_id: &str) -> usize {
        // 使用稳定的哈希函数
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        task_id.hash(&mut hasher);
        (hasher.finish() as usize) % self.shard_count
    }
}
