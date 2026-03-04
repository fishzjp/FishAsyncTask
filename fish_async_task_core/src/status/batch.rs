//! 批量操作专用模块

use crate::types::TaskStatusDict;
use dashmap::DashMap;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::sync::Arc;

/// 批量状态更新器
///
/// 收集多个更新，批量提交以减少锁竞争。
#[pyclass]
pub struct PyBatchedUpdater {
    store: Arc<DashMap<String, TaskStatusDict>>,
    #[allow(dead_code)]
    batch_size: usize,
}

#[pymethods]
impl PyBatchedUpdater {
    /// 创建新的批量更新器
    #[new]
    fn new(batch_size: usize) -> PyResult<Self> {
        Ok(Self {
            store: Arc::new(DashMap::new()),
            batch_size,
        })
    }

    /// 批量更新状态
    fn update_batch(&self, py: Python, items: Vec<(String, PyObject)>) -> PyResult<usize> {
        py.allow_threads(|| {
            let mut count = 0;
            for (task_id, status_obj) in items {
                let result = Python::with_gil(|py| -> PyResult<bool> {
                    let status_dict = status_obj.extract::<Bound<'_, PyDict>>(py)?;

                    let task_status = TaskStatusDict {
                        status: status_dict
                            .get_item("status")?
                            .map(|v| v.extract::<String>().unwrap_or_default()),
                        submit_time: status_dict
                            .get_item("submit_time")?
                            .and_then(|v| v.extract::<f64>().ok()),
                        start_time: status_dict
                            .get_item("start_time")?
                            .and_then(|v| v.extract::<f64>().ok()),
                        end_time: status_dict
                            .get_item("end_time")?
                            .and_then(|v| v.extract::<f64>().ok()),
                        result: status_dict.get_item("result")?.map(|v| v.into()),
                        error: status_dict
                            .get_item("error")?
                            .map(|v| v.extract::<String>().unwrap_or_default()),
                        worker_id: status_dict
                            .get_item("worker_id")?
                            .map(|v| v.extract::<String>().unwrap_or_default()),
                    };

                    self.store.insert(task_id, task_status);
                    Ok(true)
                });

                if result.is_ok() {
                    count += 1;
                }
            }
            Ok(count)
        })
    }
}
