//! 任务依赖管理
//!
//! 使用 petgraph 管理任务之间的依赖关系。

use dashmap::DashMap;
use parking_lot::RwLock;
use petgraph::graph::DiGraph;
use petgraph::algo::is_cyclic_directed;
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};
use std::sync::Arc;

/// 任务依赖管理器
///
/// 管理任务之间的依赖关系，支持循环检测。
#[pyclass]
pub struct PyTaskDependencyManager {
    dependencies: Arc<DashMap<String, HashSet<String>>>,
    dependents: Arc<DashMap<String, HashSet<String>>>,
    completed_tasks: Arc<RwLock<HashSet<String>>>,
}

#[pymethods]
impl PyTaskDependencyManager {
    /// 创建新的依赖管理器
    #[new]
    fn new() -> PyResult<Self> {
        Ok(Self {
            dependencies: Arc::new(DashMap::new()),
            dependents: Arc::new(DashMap::new()),
            completed_tasks: Arc::new(RwLock::new(HashSet::new())),
        })
    }

    /// 添加依赖关系
    ///
    /// Args:
    ///     task_id: 任务ID
    ///     dep_id: 依赖的任务ID
    fn add_dependency(&self, task_id: &str, dep_id: &str) -> PyResult<()> {
        // 添加到依赖映射
        self.dependencies
            .entry(task_id.to_string())
            .or_insert_with(HashSet::new)
            .insert(dep_id.to_string());

        // 添加到反向映射
        self.dependents
            .entry(dep_id.to_string())
            .or_insert_with(HashSet::new)
            .insert(task_id.to_string());

        Ok(())
    }

    /// 检查任务是否就绪（所有依赖都已完成）
    ///
    /// Args:
    ///     task_id: 任务ID
    ///
    /// Returns:
    ///     是否就绪
    fn is_ready(&self, task_id: &str) -> PyResult<bool> {
        if let Some(deps) = self.dependencies.get(task_id) {
            let completed = self.completed_tasks.read();
            for dep in deps.iter() {
                if !completed.contains(dep) {
                    return Ok(false);
                }
            }
        }
        Ok(true)
    }

    /// 标记任务为已完成
    ///
    /// Args:
    ///     task_id: 任务ID
    fn mark_completed(&self, task_id: &str) -> PyResult<()> {
        let mut completed = self.completed_tasks.write();
        completed.insert(task_id.to_string());
        Ok(())
    }

    /// 检查是否存在循环依赖
    ///
    /// Returns:
    ///     是否存在循环依赖
    fn has_circular_dependency(&self) -> PyResult<bool> {
        // 构建依赖图
        let mut graph = DiGraph::<String, ()>::new();
        let mut node_map: HashMap<String, petgraph::graph::NodeIndex> = HashMap::new();

        // 添加所有节点
        for entry in self.dependencies.iter() {
            let task_id = entry.key();
            if !node_map.contains_key(task_id) {
                node_map.insert(task_id.clone(), graph.add_node(task_id.clone()));
            }
            for dep in entry.value().iter() {
                if !node_map.contains_key(dep) {
                    node_map.insert(dep.clone(), graph.add_node(dep.clone()));
                }
            }
        }

        // 添加边
        for entry in self.dependencies.iter() {
            let task_idx = node_map.get(entry.key()).unwrap();
            for dep in entry.value().iter() {
                let dep_idx = node_map.get(dep).unwrap();
                graph.add_edge(*dep_idx, *task_idx, ());
            }
        }

        Ok(is_cyclic_directed(&graph))
    }

    /// 获取任务的依赖列表
    ///
    /// Args:
    ///     task_id: 任务ID
    ///
    /// Returns:
    ///     依赖的任务ID列表
    fn get_dependencies(&self, task_id: &str) -> PyResult<Vec<String>> {
        if let Some(deps) = self.dependencies.get(task_id) {
            Ok(deps.iter().cloned().collect())
        } else {
            Ok(Vec::new())
        }
    }

    /// 获取依赖于指定任务的任务列表
    ///
    /// Args:
    ///     task_id: 任务ID
    ///
    /// Returns:
    ///     依赖于该任务的任务ID列表
    fn get_dependents(&self, task_id: &str) -> PyResult<Vec<String>> {
        if let Some(deps) = self.dependents.get(task_id) {
            Ok(deps.iter().cloned().collect())
        } else {
            Ok(Vec::new())
        }
    }

    /// 移除任务的依赖关系
    ///
    /// Args:
    ///     task_id: 任务ID
    ///     dep_id: 要移除的依赖任务ID
    fn remove_dependency(&self, task_id: &str, dep_id: &str) -> PyResult<bool> {
        // 从依赖映射中移除
        if let Some(mut deps) = self.dependencies.get_mut(task_id) {
            let removed = deps.remove(dep_id);
            if deps.is_empty() {
                self.dependencies.remove(task_id);
            }

            // 从反向映射中移除
            if let Some(mut dep_list) = self.dependents.get_mut(dep_id) {
                dep_list.remove(task_id);
                if dep_list.is_empty() {
                    self.dependents.remove(dep_id);
                }
            }

            Ok(removed)
        } else {
            Ok(false)
        }
    }

    /// 批量添加依赖关系
    ///
    /// Args:
    ///     deps: (task_id, dep_id) 元组列表
    fn add_dependencies_batch(&self, deps: Vec<(String, String)>) -> PyResult<()> {
        for (task_id, dep_id) in deps {
            self.add_dependency(&task_id, &dep_id)?;
        }
        Ok(())
    }

    /// 批量检查任务是否就绪
    ///
    /// Args:
    ///     task_ids: 任务ID列表
    ///
    /// Returns:
    ///     对应的就绪状态列表
    fn get_ready_tasks(&self, task_ids: Vec<String>) -> PyResult<Vec<bool>> {
        task_ids
            .into_iter()
            .map(|task_id| self.is_ready(&task_id))
            .collect()
    }

    /// 清除所有依赖关系
    fn clear(&self) -> PyResult<()> {
        self.dependencies.clear();
        self.dependents.clear();
        self.completed_tasks.write().clear();
        Ok(())
    }

    /// 重置已完成状态
    fn reset_completed(&self) -> PyResult<()> {
        self.completed_tasks.write().clear();
        Ok(())
    }
}
