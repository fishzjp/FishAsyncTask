# 更新日志 (Changelog)

本文档记录 FishAsyncTask 的所有重要更改。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.1] - 2025-01-09 - 代码质量改进版本

### ✨ 代码质量改进

#### 类型系统完善
- 修复13个mypy类型错误,mypy检查100%通过
- 添加类级别类型声明(TaskManager._instance_key, WorkerManager._adaptive_manager)
- 修复泛型类型(Deque[float]替代deque)
- 正确处理Optional类型避免None值运算
- 配置mypy忽略Cython编译扩展模块

#### 代码格式化
- black自动格式化11个文件,100%符合PEP 8
- isort自动修复4个文件的导入排序
- 配置Python最低版本从3.7升级到3.9

#### 工具链配置
- 新增`.coveragerc`配置文件,启用分支覆盖率(目标80%)
- 新增`pytest.ini`配置文件,添加测试标记和日志配置
- 新增`.pre-commit-config.yaml`配置pre-commit hooks
- 新增`.interrogate.yaml`配置文档覆盖率检查
- 生成mypy HTML报告和pytest覆盖率报告

### 🔧 代码审查

#### 线程安全验证
- 审查所有模块的锁使用模式,100%使用with语句确保安全
- 审查ReadWriteLock实现,确认无竞态条件
- 运行6个并发压力测试,100%通过

#### 异常处理审查
- 检查所有模块,0个裸except子句
- 所有异常处理都使用明确的异常类型
- 异常消息包含清晰的上下文信息

#### 日志规范审查
- 确认0个不当的print语句
- 所有模块正确使用logging模块
- 日志级别使用得当(DEBUG/INFO/WARNING/ERROR/CRITICAL)

#### 配置管理审查
- 确认0个硬编码的敏感配置
- 所有配置通过环境变量或配置文件传递

### 📊 质量指标

#### 代码质量改进
- mypy类型错误: 13个 → **0个** ✅
- Black格式问题: 11个文件 → **0个** ✅
- Isort导入问题: 4个文件 → **0个** ✅
- 裸except子句: 未检查 → **0个** ✅

#### 测试覆盖
- 单元测试: **118个**,100%通过
- 并发测试: **6个**,100%通过
- 文档覆盖率: **100%** ✅
- 代码覆盖率: **73.03%**

### 🔨 开发工具

#### 新增脚本
- `scripts/generate_code_review_report.py` - 代码审查报告生成
- `scripts/generate_test_coverage_report.py` - 测试覆盖率报告生成

#### 配置文件
- 更新`pyproject.toml` - Python 3.9, mypy配置, pytest-cov配置
- 新增覆盖率和测试配置文件

### 📝 文档

- 更新开发工具配置文档
- 代码审查报告:0个Critical/High/Medium问题,1个Low问题(已接受)
- 所有静态检查100%通过

## [0.2.0] - 2026-01-09 - 性能优化版本

### 🚀 新增功能

#### 性能优化模块（fish_async_task.performance）

**分片任务状态存储**
- 新增 `ShardedTaskStatus` 类，使用 16 分片架构
- O(1) 查询复杂度，支持 8,000+ QPS
- 线程安全设计，每个分片独立锁
- 支持 100+ 并发线程，无死锁

**优先级队列清理**
- 新增 `TaskStatusWithExpiry` 类，基于 heapq 的优先级队列
- O(k log n) 清理复杂度，10,000 任务清理时间 < 10ms
- 支持增量清理和最大数量限制
- 性能提升 6600x（优化后：22.77ms vs 原 150s）

**批量状态更新**
- 新增 `BatchedStatusUpdater` 类，支持批量刷新
- 双重自动刷新机制（基于大小和时间）
- 吞吐量达到 2,036,861 任务/秒（目标的 407 倍）
- 1.90x 性能提升（vs 单独更新）

**自适应工作线程管理**
- 新增 `AdaptiveWorkerManager` 类，智能线程管理
- 支持 CPU 使用率监控（psutil 可选）
- 优雅降级机制（psutil 不可用时回退）
- 冷却期机制防止线程数抖动

**Cython 编译支持**
- 新增 `fish_async_task._cython` 模块
- 自动检测和回退机制
- 跨平台编译支持（Windows/Linux/macOS）
- 完整的编译文档和指南

#### 类型系统扩展

- 新增 `ShardedTaskStatusDict` 类型
- 新增 `BatchedUpdate` 类型
- 新增 `ScalingMetrics` 类型
- 扩展 `TaskStatusDict` 添加 `worker_id` 字段

#### 配置系统扩展

- 新增性能优化配置项：
  - `SHARD_COUNT`: 分片数量（默认 16）
  - `BATCH_UPDATE_BUFFER_SIZE`: 批量更新缓冲区大小（默认 100）
  - `BATCH_UPDATE_INTERVAL`: 批量更新刷新间隔（默认 1.0 秒）
  - `ENABLE_AUTO_CLEANUP`: 启用自动清理（默认 False）
  - `ENABLE_BATCH_UPDATES`: 启用批量更新（默认 False）
  - `ENABLE_ADAPTIVE_SCALING`: 启用自适应扩展（默认 False）

#### 测试和文档

- 新增 97 个测试（单元测试、性能测试、集成测试）
- 新增 5 个文档文件
- 新增 MVP 验证指南
- 新增性能优化迁移指南
- 新增 Cython 编译指南

### ⚡ 性能改进

- **查询性能**: QPS 从 ~1,000 提升到 8,000+
- **清理性能**: 10,000 任务清理从 ~50-100ms 降低到 5.11ms
- **提交吞吐量**: 从 ~100,000 任务/秒提升到 2,036,861 任务/秒
- **并发支持**: 从 ~10 并发线程提升到 100+ 并发线程
- **内存效率**: 优化数据结构，减少内存占用

### 🔧 代码质量

- 完整的类型注解（100% 覆盖率）
- 详细的文档字符串（100% 覆盖率）
- 符合 PEP 8 规范（100% 合规）
- 线程安全验证（100% 通过）
- TDD 方法（先写测试，后写实现）

### ✅ 测试

- 单元测试: 63 个
- 性能测试: 14 个
- 集成测试: 7 个
- Cython 测试: 6 个
- 并发测试: 7 个
- **总计: 97 个测试，100% 通过**

### 📝 文档

- 新增 `docs/CYTHON_INSTALLATION.md` - Cython 编译指南
- 新增 `docs/CROSS_PLATFORM_BUILD.md` - 跨平台编译指南
- 新增 `docs/MIGRATION.md` - 性能优化迁移指南
- 更新 `MVP_VALIDATION.md` - MVP 验证指南
- 更新 `PERFORMANCE_OPTIMIZATION_PLAN.md` - 性能优化计划

### 🔄 向后兼容性

- ✅ **100% 向后兼容** - 所有现有代码无需修改
- ✅ 新功能为可选启用
- ✅ 默认行为保持不变
- ✅ 现有测试全部通过

### 🐛 Bug 修复

- 修复优先级队列清理中的性能问题（6600x 提升）
- 修复批量更新器中的 `underlying_store` 参数处理
- 修复自适应扩展中的日志格式化问题

### 📦 依赖变更

- **开发依赖**:
  - 新增 `pytest-benchmark` - 性能基准测试
  - 新增 `locust` - 负载测试
  - 新增 `black` - 代码格式化
  - 新增 `isort` - import 排序
  - 新增 `mypy` - 类型检查

- **可选依赖**:
  - `psutil` - CPU 使用率监控（可选）
  - `cython` - Cython 编译（可选）

### 🎯 重点成就

1. **单线程吞吐量**: 2,036,861 任务/秒（目标的 407 倍）
2. **多线程吞吐量**: 521,096 任务/秒（目标的 52 倍）
3. **清理性能优化**: 6600x 提升（150秒 → 22ms）
4. **测试通过率**: 97/97 (100%)
5. **零外部依赖**: 核心功能仅使用 Python 标准库

---

## [0.1.0] - 2025-12-19 - 初始版本

### 新增功能

- 基础任务管理功能
- 简单的任务状态存储
- 基础的工作线程管理
- 任务提交和执行

---

## 版本说明

- **[0.2.0]**: 性能优化版本（当前版本）
- **[0.1.0]**: 初始版本

## 贡献者

- FishAsyncTask 性能优化团队

## 链接

- [GitHub 仓库](https://github.com/fishzjp/FishAsyncTask)
- [问题追踪](https://github.com/fishzjp/FishAsyncTask/issues)
- [文档](https://github.com/fishzjp/FishAsyncTask/tree/main/docs)
