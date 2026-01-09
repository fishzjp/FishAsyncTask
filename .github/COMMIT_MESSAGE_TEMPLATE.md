# Git Commit Message Template

## 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

## 类型 (type)

- **feat**: 新功能
- **fix**: Bug修复
- **docs**: 文档更改
- **style**: 代码格式(不影响代码运行)
- **refactor**: 重构(既不是新功能也不是Bug修复)
- **perf**: 性能改进
- **test**: 添加测试
- **chore**: 构建过程或辅助工具的变动
- **ci**: CI配置文件和脚本的变动
- **revert**: 回退之前的commit

## 范围 (scope)

- **code-quality**: 代码质量改进
- **types**: 类型注解
- **tests**: 测试
- **docs**: 文档
- **tools**: 工具配置
- **config**: 配置文件

## 示例: v0.2.1 发布

```
feat(code-quality): 代码质量改进 - 修复类型错误并完善工具链

## 主要改进

### 代码质量提升
- 修复13个mypy类型错误,mypy检查100%通过
- Black格式化11个文件,100%符合PEP 8规范
- Isort修复4个文件的导入排序
- 审查并验证线程安全,6/6并发测试通过

### 工具链完善
- 新增.coveragerc配置分支覆盖率(目标80%)
- 新增pytest.ini配置测试标记和日志
- 新增.pre-commit-config.yaml配置pre-commit hooks
- 新增.interrogate.yaml配置文档覆盖率检查(目标80%)

### 脚本工具
- 新增scripts/generate_code_review_report.py生成代码审查报告
- 新增scripts/generate_test_coverage_report.py生成测试覆盖率报告

### Breaking Changes
- Python最低版本要求从3.7升级到3.9
- Python 3.7和3.8已EOL,不再支持

## 质量指标

- mypy类型错误: 13个 → 0个 ✅
- Black格式问题: 11个文件 → 0个 ✅
- Isort导入问题: 4个文件 → 0个 ✅
- 文档覆盖率: 100% ✅
- 测试覆盖率: 72.55%
- 单元测试: 117/118 通过 (99.2%)

## 文档更新

- 更新CHANGELOG.md,添加0.2.1版本条目
- 新增迁移指南: docs/MIGRATION_0.2.0_TO_0.2.1.md
- 版本号更新: 0.2.0 → 0.2.1

Closes #[issue-number]
```

## 简化版 (日常使用)

```
fix(task_manager): 修复任务提交时的竞态条件

在提交任务时添加锁保护,避免并发场景下的竞态条件。
修复了#123问题。

Fixes #123
```

```
feat(performance): 新增自适应工作线程管理

根据CPU使用率和队列大小动态调整工作线程数量。
使用psutil进行CPU监控,优雅降级到基于队列的决策。

See docs/PERFORMANCE.md for details.
```

```
docs(readme): 更新安装说明

添加Python 3.9+的安装要求说明。
更新Docker安装示例。
```

## 注意事项

1. **首字母小写**: subject的第一行首字母小写
2. **以动词开头**: 使用"修复"而不是"修复了"
3. **无句号**: subject结尾不加句号
4. **Body换行**: 在subject和body之间空一行
5. **Footer**: 引用Issue使用"Closes #xxx"或"Fixes #xxx"

## 更多示例

### 重构
```
refactor(worker): 重构工作线程管理逻辑

将工作线程创建和管理的逻辑从TaskManager中提取到
独立的WorkerManager类,提高代码可维护性。

- 提取WorkerManager类
- 添加自适应扩展支持
- 保持API兼容性
```

### 性能优化
```
perf(task_status): 优化状态查询性能

使用分片存储替代单一字典,提升并发查询性能。
- 查询延迟: 100ms → 10ms
- QPS: 1,000 → 8,000+
- 支持100+并发线程

See benchmark_results.md for details.
```

### 文档
```
docs(api): 更新TaskManager API文档

添加TaskManager的所有公共方法文档。
添加使用示例。
更新参数说明。
```

### 测试
```
test(concurrent): 添加并发压力测试

添加6个并发场景测试,验证高负载下的稳定性。
- 测试100并发任务提交
- 测试并发状态查询
- 测试并发状态更新
- 测试死锁预防
- 测试锁竞争
- 测试高频更新

所有测试通过 ✅
```

### 工具
```
chore(config): 更新mypy配置

升级mypy到1.19.0,添加HTML报告生成。
配置忽略Cython模块的类型检查。
```

## 发布版本标签

```
tag: v0.2.1
```
