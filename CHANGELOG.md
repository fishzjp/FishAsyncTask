# 更新日志

所有值得注意的项目变更都将记录在此文件中。

## [Unreleased]

### 新增
- `submit_task` 新增 `priority` 关键字参数，优先级队列正式接入主流程
  （此前 README 已宣传该用法，但 `priority` 实际会被透传给任务函数，
  不产生任何调度效果）

### 行为变更
- `priority` 成为 `submit_task` 的保留关键字参数，不再透传给任务函数；
  任务函数如需同名参数请改名
- `TaskManager.task_queue` 属性类型由 `queue.Queue` 变为 `TaskChannel`
  （接口兼容：get/put/put_nowait/qsize/empty/full/task_done 均可用）；
  依赖 `isinstance(tm.task_queue, queue.Queue)` 的代码需调整
- 任务出队顺序由严格 FIFO 变为优先级排序；同优先级按提交时间近似 FIFO
  （同一时钟刻度内提交的任务顺序不保证）

### 修复
- 修复 `TaskDependencyManager.get_ready_tasks()` 持锁重入导致的死锁
- 修复 Rust 优先级队列 `put(block=True)` 在队列满时不阻塞、
  直接超容入队的缺陷（`maxsize` 此前形同虚设），并支持 `timeout`
- 修复纯 Python 优先级队列 `put/get` 阻塞与超时语义错误
- 修复 Rust 优先级队列适配器 `_tasks` 字典只增不减的内存泄漏
- 队列空/满异常统一为标准库 `queue.Empty` / `queue.Full`

### 文档
- 修正 README 性能表述与自家基线数据不符的问题（"2-4x" → 实测 1.08-2.16x）
- 澄清内存对比的测量口径：tracemalloc 只统计 Python 堆，
  不能得出"~100% 节省"的结论

## [0.3.1] - 2026-03-05

### 新增
- 完整的跨平台 wheel 支持（Linux, macOS, Windows）
- CI/CD 自动化发布流程
- 冒烟测试套件，快速验证核心功能

### 优化
- CI/CD 流程优化，只运行冒烟测试以加快构建速度
- 文档链接更新到 GitHub Pages

### 修复
- 修复 CI 工作流中的路径配置问题
- 修复 Windows 平台 patchelf 安装问题
- 修复 README.md 中的导入示例错误

## [0.3.0] - 2026-03-05

### 重大变更
- 🚀 **默认 Rust 实现**：Rust 核心实现作为默认选项
- 🏗️ **架构重构**：将核心功能模块化
- 📊 **优先级队列**：新增 PriorityTaskManager

### 性能提升
| 操作 | Python | Rust | 加速比 |
|------|--------|------|--------|
| 并发状态写入 | 1.47M ops/s | 1.79M ops/s | 1.22x |
| 并发状态读取 | 1.07M QPS | 1.38M QPS | 1.29x |
| 队列入队 | 603K ops/s | 1.30M ops/s | 2.16x |
| 队列出队 | 705K ops/s | 1.30M ops/s | 1.85x |
| 内存占用 | 1,432 KB | 0.3 KB | ~100% 节省 |

## [0.2.3] - 2026-03-04

### 修复
- 修复 PriorityTaskManager 的 submit_task 签名问题
- 修复任务结果传播问题
- 修复 args 和 kwargs 参数处理
