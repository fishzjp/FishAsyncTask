//! 共享类型定义
//!
//! 定义 Python 和 Rust 之间共享的类型。

use pyo3::prelude::*;

/// 任务状态枚举
#[derive(Debug, Clone, PartialEq)]
#[pyclass(eq, eq_int)]
pub enum TaskStatus {
    Pending,
    Running,
    Completed,
    Failed,
}

impl TaskStatus {
    /// 获取状态的字符串表示
    pub fn as_str(&self) -> &'static str {
        match self {
            TaskStatus::Pending => "pending",
            TaskStatus::Running => "running",
            TaskStatus::Completed => "completed",
            TaskStatus::Failed => "failed",
        }
    }

    /// 从字符串创建状态（避免与 std::str::FromStr 冲突）
    pub fn parse_str(s: &str) -> Option<Self> {
        match s {
            "pending" => Some(TaskStatus::Pending),
            "running" => Some(TaskStatus::Running),
            "completed" => Some(TaskStatus::Completed),
            "failed" => Some(TaskStatus::Failed),
            _ => None,
        }
    }
}

/// 任务状态字典
///
/// 对应 Python 的 TaskStatusDict TypedDict
///
/// 优化说明：
/// - 保留 PyObject 用于 result 字段
/// - 添加批量 API 减少跨语言调用
/// - 添加日志记录
#[derive(Debug, FromPyObject)]
pub struct TaskStatusDict {
    pub status: Option<String>,
    pub submit_time: Option<f64>,
    pub start_time: Option<f64>,
    pub end_time: Option<f64>,
    pub result: Option<PyObject>,
    pub error: Option<String>,
    pub worker_id: Option<String>,
}

// PyO3 0.23 中 Py<T> 不实现 Clone，需通过 clone_ref 在 GIL 下递增引用计数
impl Clone for TaskStatusDict {
    fn clone(&self) -> Self {
        Self {
            status: self.status.clone(),
            submit_time: self.submit_time,
            start_time: self.start_time,
            end_time: self.end_time,
            result: self.result.as_ref().map(|py_obj| {
                Python::with_gil(|py| py_obj.clone_ref(py))
            }),
            error: self.error.clone(),
            worker_id: self.worker_id.clone(),
        }
    }
}

/// 优先级任务
///
/// 用于优先级队列的任务包装（不存储 PyObject，避免 Clone 问题）
#[derive(Debug, Clone)]
#[pyclass]
pub struct PrioritizedTask {
    pub priority: i32,
    pub task_id: String,
    pub submit_time: f64,
}

#[pymethods]
impl PrioritizedTask {
    #[new]
    #[pyo3(signature = (priority, task_id, submit_time))]
    fn new(priority: i32, task_id: String, submit_time: f64) -> Self {
        Self {
            priority,
            task_id,
            submit_time,
        }
    }
}

// 实现 Ord 用于 BinaryHeap（反转比较以实现最小堆行为）
impl PartialEq for PrioritizedTask {
    fn eq(&self, other: &Self) -> bool {
        self.priority == other.priority && self.task_id == other.task_id
    }
}

impl Eq for PrioritizedTask {}

impl PartialOrd for PrioritizedTask {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for PrioritizedTask {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        // BinaryHeap 是最大堆，要实现最小堆需要反转比较
        // 先按优先级比较（越小优先级越高，所以反转）
        match self.priority.cmp(&other.priority) {
            std::cmp::Ordering::Equal => {
                // 优先级相同时，按提交时间比较（FIFO - 先提交的先出）
                // 较早的任务先出，所以让较早的时间"更大"
                match self.submit_time.partial_cmp(&other.submit_time) {
                    Some(std::cmp::Ordering::Less) => std::cmp::Ordering::Greater,
                    Some(std::cmp::Ordering::Greater) => std::cmp::Ordering::Less,
                    None | Some(std::cmp::Ordering::Equal) => std::cmp::Ordering::Equal,
                }
            }
            other => other.reverse(),
        }
    }
}
