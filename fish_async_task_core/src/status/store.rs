//! 单片状态存储
//!
//! 基于 DashMap 的简单无锁存储实现。
//!
//! 优化说明：
//! - 使用 Py<PyAny> 代替 PyObject，减少引用计数操作
//! - 添加 tracing 日志支持
//! - 实现批量 API 减少跨语言调用

use crate::types::TaskStatusDict;
use dashmap::DashMap;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use tracing::{debug, info};

/// 单片任务状态存储
///
/// 简单的无锁存储实现，用于小规模场景。
#[pyclass]
pub struct PyTaskStatusStore {
    store: DashMap<String, TaskStatusDict>,
}

#[pymethods]
impl PyTaskStatusStore {
    /// 创建新的状态存储
    #[new]
    fn new() -> PyResult<Self> {
        info!("PyTaskStatusStore: 创建新的状态存储");
        Ok(Self {
            store: DashMap::new(),
        })
    }

    /// 获取任务状态
    fn get(&self, py: Python, task_id: &str) -> PyResult<PyObject> {
        debug!("PyTaskStatusStore::get: task_id={}", task_id);

        if let Some(status) = self.store.get(task_id) {
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
            // 优化：使用 Py<PyAny>::clone_ref 来获取对象引用
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
            debug!("PyTaskStatusStore::get: task_id={} 未找到", task_id);
            Ok(py.None())
        }
    }

    /// 更新任务状态
    fn update(&self, _py: Python, task_id: &str, status: &Bound<'_, PyDict>) -> PyResult<()> {
        debug!("PyTaskStatusStore::update: task_id={}", task_id);

        let task_status = TaskStatusDict::extract_bound(status)?;

        // 记录状态变化
        if let Some(ref s) = task_status.status {
            debug!(
                "PyTaskStatusStore::update: task_id={}, status={}",
                task_id, s
            );
        }

        self.store.insert(task_id.to_string(), task_status);
        Ok(())
    }

    /// 移除任务状态
    fn remove(&self, task_id: &str) -> PyResult<bool> {
        debug!("PyTaskStatusStore::remove: task_id={}", task_id);
        let removed = self.store.remove(task_id).is_some();
        if removed {
            info!("PyTaskStatusStore::remove: task_id={} 已移除", task_id);
        }
        Ok(removed)
    }

    /// 获取存储大小
    fn len(&self) -> PyResult<usize> {
        let size = self.store.len();
        debug!("PyTaskStatusStore::len: size={}", size);
        Ok(size)
    }

    /// 清空存储
    fn clear(&self) -> PyResult<()> {
        let size = self.store.len();
        self.store.clear();
        info!("PyTaskStatusStore::clear: 清空了 {} 个条目", size);
        Ok(())
    }

    /// 批量获取任务状态
    ///
    /// 新增的批量 API，减少跨语言调用次数
    fn batch_get(&self, py: Python, task_ids: Vec<String>) -> PyResult<PyObject> {
        debug!("PyTaskStatusStore::batch_get: count={}", task_ids.len());

        let result = PyDict::new(py);

        for task_id in &task_ids {
            if let Some(status) = self.store.get(task_id) {
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
                result.set_item(task_id, dict)?;
            }
        }

        Ok(result.into())
    }

    /// 批量更新任务状态
    ///
    /// 新增的批量 API，减少跨语言调用次数
    fn batch_update(&self, _py: Python, updates: &Bound<'_, PyDict>) -> PyResult<usize> {
        debug!("PyTaskStatusStore::batch_update: 开始批量更新");

        let mut count = 0;
        for (key, value) in updates.iter() {
            if let Ok(task_id) = key.extract::<String>() {
                if let Ok(dict) = value.downcast::<PyDict>() {
                    if let Ok(task_status) = TaskStatusDict::extract_bound(dict) {
                        self.store.insert(task_id, task_status);
                        count += 1;
                    }
                }
            }
        }

        info!("PyTaskStatusStore::batch_update: 更新了 {} 个条目", count);
        Ok(count)
    }
}
