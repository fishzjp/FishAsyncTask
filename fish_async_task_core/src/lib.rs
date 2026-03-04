//! FishAsyncTask Core - Rust 实现
//!
//! 这是 FishAsyncTask 的 Rust 核心实现，使用 PyO3 提供 Python 绑定。
//!
//! ## 模块
//!
//! - `types`: 共享类型定义
//! - `status`: 任务状态存储实现
//! - `queue`: 优先级队列和依赖管理实现

use pyo3::prelude::*;

// 导出模块
pub mod types;
pub mod status;
pub mod queue;

// 导出类型供测试使用
pub use types::PrioritizedTask;

/// FishAsyncTask Core Python 模块
#[pymodule(name = "_core")]
fn fish_async_task_core(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<status::PyShardedTaskStatus>()?;
    m.add_class::<queue::PyPriorityTaskQueue>()?;
    m.add_class::<queue::PyTaskDependencyManager>()?;
    m.add_class::<types::PrioritizedTask>()?;
    Ok(())
}
