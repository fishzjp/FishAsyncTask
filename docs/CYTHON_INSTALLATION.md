# FishAsyncTask 性能优化 - Cython 编译指南

本指南说明如何编译和使用 FishAsyncTask 的 Cython 性能优化扩展。

## 概述

FishAsyncTask 的性能优化功能提供两种实现：

1. **纯 Python 实现**（默认）：使用 Python 标准库，零外部依赖
2. **Cython 实现**（可选）：编译为 C 扩展，提供极致性能

## 性能对比

| 实现方式 | 查询 QPS | 吞吐量（任务/秒） | 依赖 |
|---------|---------|-----------------|------|
| 纯 Python | 8,000+ | 2,000,000+ | Python 标准库 |
| Cython | 20,000-50,000 | 5,000,000+ | Cython |

## 安装

### 方式 1：使用纯 Python 实现（推荐）

```bash
# 直接安装，无需编译
pip install fish-async-task
```

这将使用纯 Python 实现，性能已经非常出色（2M+ 任务/秒）。

### 方式 2：编译 Cython 扩展（极致性能）

如果需要极致性能，可以编译 Cython 扩展：

#### 步骤 1：安装 Cython

```bash
pip install cython
```

#### 步骤 2：编译扩展

```bash
# 克隆仓库
git clone https://github.com/fishzjp/FishAsyncTask.git
cd FishAsyncTask

# 编译 Cython 扩展
python setup_cython.py build_ext --inplace
```

#### 步骤 3：安装

```bash
pip install -e .
```

## 使用方法

### 自动检测

代码会自动检测 Cython 扩展是否可用，如果可用则使用 Cython 实现，否则回退到纯 Python 实现：

```python
from fish_async_task.performance import ShardedTaskStatus

# 自动使用最佳实现（Cython 或纯 Python）
store = ShardedTaskStatus(shard_count=16)
```

### 显式使用

如果需要显式使用特定实现：

```python
# 使用纯 Python 实现
from fish_async_task.performance import ShardedTaskStatus as PythonStore
store = PythonStore()

# 使用 Cython 实现（需要先编译）
from fish_async_task._cython import ShardedTaskStatus as CythonStore
store = CythonStore()
```

## 验证安装

验证使用的是哪种实现：

```python
from fish_async_task._cython import CYTHON_AVAILABLE

if CYTHON_AVAILABLE:
    print("使用 Cython 实现")
else:
    print("使用纯 Python 实现")
```

## 跨平台编译

Cython 扩展支持 Windows、Linux 和 macOS。

### Linux/macOS

```bash
python setup_cython.py build_ext --inplace
```

### Windows

```bash
python setup_cython.py build_ext --inplace
```

可能需要安装 Visual C++ 编译工具。

## CI/CD 集成

在 CI/CD 环境中，可以选择性编译 Cython 扩展：

```yaml
# .github/workflows/build.yml
- name: Install Cython
  run: pip install cython

- name: Build Cython extensions
  run: python setup_cython.py build_ext --inplace

- name: Run tests
  run: pytest tests/
```

## 故障排除

### 问题：编译失败

**解决方案**：确保安装了必要的编译工具

- **Ubuntu/Debian**: `sudo apt-get install build-essential python3-dev`
- **macOS**: `xcode-select --install`
- **Windows**: 安装 Visual C++ Build Tools

### 问题：导入 Cython 模块失败

**解决方案**：确认 Cython 扩展已正确编译

```bash
# 检查编译文件是否存在
ls -la fish_async_task/_cython/_sharded_status*.so
ls -la fish_async_task/_cython/_priority_queue*.so
```

### 问题：性能提升不明显

**解决方案**：

1. 确认确实使用了 Cython 实现：
   ```python
   from fish_async_task._cython import CYTHON_AVAILABLE
   print(CYTHON_AVAILABLE)  # 应该是 True
   ```

2. 纯 Python 实现已经很快了，Cython 主要在极端高并发场景下有明显优势

## 开发指南

### 编写 Cython 代码

Cython 文件使用 `.pyx` 扩展名：

```cython
# fish_async_task/_cython/_sharded_status.pyx

def example_function(str task_id):
    """示例函数"""
    return f"Task: {task_id}"
```

### 重新编译

修改 `.pyx` 文件后，需要重新编译：

```bash
python setup_cython.py build_ext --inplace
```

## 性能测试

运行性能测试来验证性能提升：

```bash
# 测试纯 Python 实现
pytest tests/performance/test_sharded_perf.py -v

# 测试 Cython 实现（如果已编译）
pytest tests/performance/test_cython_perf.py -v
```

## 最佳实践

1. **开发阶段**：使用纯 Python 实现（快速迭代）
2. **生产环境**：根据需求选择
   - 大多数场景：纯 Python 实现（2M+ 任务/秒已经足够）
   - 极致性能需求：编译 Cython 扩展
3. **CI/CD**：同时测试两种实现

## 相关文档

- [性能优化规格说明](../specs/001-performance-optimization/spec.md)
- [性能优化实施计划](../specs/001-performance-optimization/plan.md)
- [MVP 验证指南](../MVP_VALIDATION.md)

## 支持

如有问题，请提交 Issue 或 Pull Request。
