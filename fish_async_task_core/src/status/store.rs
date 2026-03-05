//! 单片状态存储
//!
//! 基于 DashMap 的简单无锁存储实现。

use crate::types::TaskStatusDict;
use dashmap::DashMap;
use pyo3::prelude::*;
use pyo3::types::PyDict;

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
        Ok(Self {
            store: DashMap::new(),
        })
    }

    /// 获取任务状态
    fn get(&self, py: Python, task_id: &str) -> PyResult<PyObject> {
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
            Ok(dict.into())
        } else {
            Ok(py.None())
        }
    }

    /// 更新任务状态
    fn update(&self, _py: Python, task_id: &str, status: &Bound<'_, PyDict>) -> PyResult<()> {
        let task_status = TaskStatusDict {
            status: status
                .get_item("status")?
                .map(|v| v.extract::<String>().unwrap_or_default()),
            submit_time: status
                .get_item("submit_time")?
                .and_then(|v| v.extract::<f64>().ok()),
            start_time: status
                .get_item("start_time")?
                .and_then(|v| v.extract::<f64>().ok()),
            end_time: status
                .get_item("end_time")?
                .and_then(|v| v.extract::<f64>().ok()),
            result: status.get_item("result")?.map(|v| v.into()),
            error: status
                .get_item("error")?
                .map(|v| v.extract::<String>().unwrap_or_default()),
            worker_id: status
                .get_item("worker_id")?
                .map(|v| v.extract::<String>().unwrap_or_default()),
        };

        self.store.insert(task_id.to_string(), task_status);
        Ok(())
    }

    /// 移除任务状态
    fn remove(&self, task_id: &str) -> PyResult<bool> {
        Ok(self.store.remove(task_id).is_some())
    }

    /// 获取存储大小
    fn len(&self) -> PyResult<usize> {
        Ok(self.store.len())
    }

    /// 清空存储
    fn clear(&self) -> PyResult<()> {
        self.store.clear();
        Ok(())
    }
}
