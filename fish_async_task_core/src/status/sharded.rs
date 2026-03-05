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
use std::time::Duration;

/// 过期时间戳包装器
///
/// 由于 f64 不实现 Ord（因为 NaN），我们需要一个包装器来实现 Ord。
/// BinaryHeap 是最大堆，所以我们使用 ReverseOrd 来实现最小堆行为。
#[derive(Debug, Clone, Copy)]
struct ExpiryTimestamp(f64);

impl ExpiryTimestamp {
    fn new(timestamp: f64) -> Self {
        ExpiryTimestamp(timestamp)
    }
}

impl PartialEq for ExpiryTimestamp {
    fn eq(&self, other: &Self) -> bool {
        self.0.to_bits() == other.0.to_bits()  // 使用 bits 比较 NaN
    }
}

impl Eq for ExpiryTimestamp {}

impl PartialOrd for ExpiryTimestamp {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for ExpiryTimestamp {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        // 使用 bits 比较来处理 NaN
        self.0.partial_cmp(&other.0).unwrap_or(std::cmp::Ordering::Equal)
    }
}

/// 过期堆类型别名 - 使用 ExpiryTimestamp 包装器
type ExpiryHeap = Arc<RwLock<BinaryHeap<(ExpiryTimestamp, String)>>>;

/// 批量更新项类型别名
#[allow(clippy::type_complexity)]
type BatchUpdateItem = (
    String,
    String,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<String>,
    usize,
    bool,
    bool,
);

/// 分片任务状态存储
///
/// 使用 DashMap 实现无锁并发分片存储，支持高并发读写。
#[pyclass]
pub struct PyShardedTaskStatus {
    shards: Vec<Arc<DashMap<String, TaskStatusDict>>>,
    #[allow(clippy::type_complexity)]
    expiry_heaps: Vec<ExpiryHeap>,
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
    fn update_status(&self, py: Python, task_id: &str, status: &Bound<'_, PyDict>) -> PyResult<()> {
        // 在 GIL 下提取所有 Python 数据
        let shard_idx = self._get_shard_index(task_id);

        // 提取所有字段（在 GIL 下）
        let status_opt = status
            .get_item("status")?
            .and_then(|v| v.extract::<String>().ok());
        let submit_time = status
            .get_item("submit_time")?
            .and_then(|v| v.extract::<f64>().ok());
        let start_time = status
            .get_item("start_time")?
            .and_then(|v| v.extract::<f64>().ok());
        let end_time = status
            .get_item("end_time")?
            .and_then(|v| v.extract::<f64>().ok());
        let result = status.get_item("result")?.map(|v| v.into());
        let error = status
            .get_item("error")?
            .and_then(|v| v.extract::<String>().ok());
        let worker_id = status
            .get_item("worker_id")?
            .and_then(|v| v.extract::<String>().ok());
        let task_id_owned = task_id.to_string();
        let is_completed = status_opt.as_deref() == Some("completed");
        let is_failed = status_opt.as_deref() == Some("failed");

        // 在释放 GIL 后执行 Rust 操作
        py.allow_threads(|| {
            let shard = &self.shards[shard_idx];

            let task_status = TaskStatusDict {
                status: status_opt,
                submit_time,
                start_time,
                end_time,
                result,
                error,
                worker_id,
            };

            // 如果任务已完成或失败，添加到过期堆
            // 使用 end_time + ttl 作为过期时间（Unix 时间戳）
            if is_completed || is_failed {
                if let Some(et) = end_time {
                    let expiry_time = ExpiryTimestamp::new(et + self.ttl.as_secs_f64());
                    let mut heap = self.expiry_heaps[shard_idx].write();
                    heap.push((expiry_time, task_id_owned.clone()));
                }
            }

            shard.insert(task_id_owned, task_status);
            Ok(())
        })
    }

    /// 高性能更新状态（直接传递参数，避免字典转换）
    ///
    /// Args:
    ///     task_id: 任务ID
    ///     status: 状态字符串
    ///     submit_time: 提交时间
    ///     start_time: 开始时间
    ///     end_time: 结束时间
    ///     worker_id: 工作ID
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (task_id, status, submit_time=None, start_time=None, end_time=None, worker_id=None))]
    fn update_status_fast(
        &self,
        py: Python,
        task_id: String,
        status: String,
        submit_time: Option<f64>,
        start_time: Option<f64>,
        end_time: Option<f64>,
        worker_id: Option<String>,
    ) -> PyResult<()> {
        let shard_idx = self._get_shard_index(&task_id);
        let task_id_clone = task_id.clone();
        let is_completed = status == "completed";
        let is_failed = status == "failed";

        py.allow_threads(|| {
            let shard = &self.shards[shard_idx];

            let task_status = TaskStatusDict {
                status: Some(status),
                submit_time,
                start_time,
                end_time,
                result: None,
                error: None,
                worker_id,
            };

            // 如果任务已完成或失败，添加到过期堆
            // 使用 end_time + ttl 作为过期时间（Unix 时间戳）
            if is_completed || is_failed {
                if let Some(et) = end_time {
                    let expiry_time = ExpiryTimestamp::new(et + self.ttl.as_secs_f64());
                    let mut heap = self.expiry_heaps[shard_idx].write();
                    heap.push((expiry_time, task_id_clone));
                }
            }

            shard.insert(task_id, task_status);
            Ok(())
        })
    }

    /// 高性能批量更新（直接传递参数列表）
    ///
    /// Args:
    ///     items: (task_id, status, submit_time, start_time, end_time, worker_id) 元组列表
    ///
    /// Returns:
    ///     成功更新的数量
    #[allow(clippy::type_complexity)]
    fn update_status_fast_batch(
        &self,
        py: Python,
        items: Vec<(
            String,
            String,
            Option<f64>,
            Option<f64>,
            Option<f64>,
            Option<String>,
        )>,
    ) -> PyResult<usize> {
        // 阶段 1: 计算分片索引（在 GIL 下）
        let mut extracted_items: Vec<BatchUpdateItem> = Vec::with_capacity(items.len());

        for (task_id, status, submit_time, start_time, end_time, worker_id) in items {
            let shard_idx = self._get_shard_index(&task_id);
            let is_completed = status == "completed";
            let is_failed = status == "failed";

            extracted_items.push((
                task_id,
                status,
                submit_time,
                start_time,
                end_time,
                worker_id,
                shard_idx,
                is_completed,
                is_failed,
            ));
        }

        // 阶段 2: 释放 GIL 后执行批量 Rust 操作
        py.allow_threads(|| {
            let mut count = 0;
            let ttl_secs = self.ttl.as_secs_f64();

            for (
                task_id,
                status,
                submit_time,
                start_time,
                end_time,
                worker_id,
                shard_idx,
                is_completed,
                is_failed,
            ) in extracted_items
            {
                let shard = &self.shards[shard_idx];

                let task_status = TaskStatusDict {
                    status: Some(status),
                    submit_time,
                    start_time,
                    end_time,
                    result: None,
                    error: None,
                    worker_id,
                };

                // 如果任务已完成或失败，添加到过期堆
                if is_completed || is_failed {
                    if let Some(et) = end_time {
                        let expiry_time = ExpiryTimestamp::new(et + ttl_secs);
                        let mut heap = self.expiry_heaps[shard_idx].write();
                        heap.push((expiry_time, task_id.clone()));
                    }
                }

                shard.insert(task_id, task_status);
                count += 1;
            }

            Ok(count)
        })
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
    fn cleanup_expired(&self, _py: Python, max_cleanup: Option<usize>) -> PyResult<usize> {
        // 使用 SystemTime 获取当前 Unix 时间戳
        let now_timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();

        let mut cleaned_count = 0;

        for shard_idx in 0..self.shard_count {
            if let Some(limit) = max_cleanup {
                if cleaned_count >= limit {
                    break;
                }
            }

            let shard = &self.shards[shard_idx];
            let mut heap = self.expiry_heaps[shard_idx].write();

            // BinaryHeap 是最大堆，但我们需要最小堆行为（最早过期的先处理）
            // ExpiryTimestamp 的 Ord 实现已经处理了这个问题
            while let Some((expiry_time, ref _task_id)) = heap.peek() {
                if let Some(limit) = max_cleanup {
                    if cleaned_count >= limit {
                        break;
                    }
                }

                // 如果过期时间还未到达，停止清理
                if expiry_time.0 > now_timestamp {
                    break;
                }

                let task_id = heap.pop().unwrap().1;
                if shard.remove(&task_id).is_some() {
                    cleaned_count += 1;
                }
            }
        }

        Ok(cleaned_count)
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
    #[allow(deprecated)]
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
        // 阶段 1: 在 GIL 下提取所有 Python 数据到 Rust 结构
        let mut extracted_items = Vec::with_capacity(items.len());

        for (task_id, status_obj) in items {
            let status_dict = status_obj.extract::<Bound<'_, PyDict>>(py);
            if let Ok(dict) = status_dict {
                // 提取所有字段
                let status_opt = dict
                    .get_item("status")?
                    .and_then(|v| v.extract::<String>().ok());
                let submit_time = dict
                    .get_item("submit_time")?
                    .and_then(|v| v.extract::<f64>().ok());
                let start_time = dict
                    .get_item("start_time")?
                    .and_then(|v| v.extract::<f64>().ok());
                let end_time = dict
                    .get_item("end_time")?
                    .and_then(|v| v.extract::<f64>().ok());
                let result = dict.get_item("result")?.map(|v| v.into());
                let error = dict
                    .get_item("error")?
                    .and_then(|v| v.extract::<String>().ok());
                let worker_id = dict
                    .get_item("worker_id")?
                    .and_then(|v| v.extract::<String>().ok());
                let is_completed = status_opt.as_deref() == Some("completed");
                let is_failed = status_opt.as_deref() == Some("failed");
                let shard_idx = self._get_shard_index(&task_id);

                extracted_items.push((
                    task_id,
                    TaskStatusDict {
                        status: status_opt,
                        submit_time,
                        start_time,
                        end_time,
                        result,
                        error,
                        worker_id,
                    },
                    shard_idx,
                    is_completed,
                    is_failed,
                ));
            }
        }

        // 阶段 2: 释放 GIL 后执行批量 Rust 操作
        py.allow_threads(|| {
            let mut count = 0;
            let ttl_secs = self.ttl.as_secs_f64();

            for (task_id, task_status, shard_idx, is_completed, is_failed) in extracted_items {
                let shard = &self.shards[shard_idx];

                // 如果任务已完成或失败，添加到过期堆
                if is_completed || is_failed {
                    if let Some(et) = task_status.end_time {
                        let expiry_time = ExpiryTimestamp::new(et + ttl_secs);
                        let mut heap = self.expiry_heaps[shard_idx].write();
                        heap.push((expiry_time, task_id.clone()));
                    }
                }

                shard.insert(task_id, task_status);
                count += 1;
            }

            Ok(count)
        })
    }

    /// 强制执行最大任务数量限制
    ///
    /// 当任务状态数量超过限制时，按时间顺序清理最旧的任务。
    ///
    /// Args:
    ///     max_count: 最大任务数量
    ///
    /// Returns:
    ///     清理的任务数量
    fn enforce_max_count(&self, _py: Python, max_count: usize) -> PyResult<usize> {
        let total_count = self.get_total_count()?;
        if total_count <= max_count {
            return Ok(0);
        }

        let cleanup_count = total_count - max_count;
        let mut cleaned = 0;

        // 遍历所有分片，清理最旧的任务
        for shard_idx in 0..self.shard_count {
            if cleaned >= cleanup_count {
                break;
            }

            let shard = &self.shards[shard_idx];

            // 收集所有任务并按 submit_time/end_time 排序
            let mut tasks_with_time: Vec<(f64, String)> = shard
                .iter()
                .filter_map(|entry| {
                    let (task_id, status) = entry.pair();
                    let time_key = status.end_time
                        .or(status.start_time)
                        .or(status.submit_time)
                        .unwrap_or(0.0);
                    Some((time_key, task_id.clone()))
                })
                .collect();

            // 按时间升序排序（最旧的在前）
            tasks_with_time.sort_by(|a, b| {
                a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal)
            });

            // 清理最旧的任务
            let need_cleanup = (cleanup_count - cleaned).min(tasks_with_time.len());
            for (_, task_id) in tasks_with_time.into_iter().take(need_cleanup) {
                shard.remove(&task_id);
                cleaned += 1;
            }

            if cleaned >= cleanup_count {
                break;
            }
        }

        Ok(cleaned)
    }

    /// 动态调整分片数量
    ///
    /// 注意：由于 Rust 的所有权限制，此方法返回 false 表示需要重新创建实例。
    ///
    /// Args:
    ///     new_shard_count: 新的分片数量
    ///
    /// Returns:
    ///     是否成功调整
    fn resize_shards(&self, _py: Python, _new_shard_count: usize) -> PyResult<bool> {
        // 由于 Rust 的所有权限制和 DashMap 的不可变性，
        // 无法在原实例上调整分片数量。
        // 返回 false 表示需要重新创建实例。
        Ok(false)
    }

    /// 获取分片数量
    fn get_shard_count(&self) -> PyResult<usize> {
        Ok(self.shard_count)
    }
}

impl PyShardedTaskStatus {
    /// 根据 task_id 计算分片索引
    fn _get_shard_index(&self, task_id: &str) -> usize {
        self._get_shard_index_with_count(task_id, self.shard_count)
    }

    /// 根据 task_id 和指定的分片数量计算分片索引
    fn _get_shard_index_with_count(&self, task_id: &str, count: usize) -> usize {
        // 使用稳定的哈希函数
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        task_id.hash(&mut hasher);
        (hasher.finish() as usize) % count
    }
}
