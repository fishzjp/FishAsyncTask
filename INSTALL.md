# 安装说明

## 系统要求

- Python 3.7 或更高版本
- pip（Python包管理器）

## 安装方式

### 方式一：从 PyPI 安装（推荐）

```bash
pip install fish-async-task
```

### 方式二：从 GitHub 安装

直接从 GitHub 仓库安装最新版本：

```bash
pip install git+https://github.com/fishzjp/FishAsyncTask.git
```

### 方式三：本地安装

#### 1. 克隆仓库

```bash
git clone https://github.com/fishzjp/FishAsyncTask.git
cd FishAsyncTask
```

#### 2. 安装方式选择

**标准安装：**
```bash
pip install .
```

**开发模式安装（推荐用于开发）：**
```bash
pip install -e .
```

开发模式安装的优势：
- 代码修改后立即生效，无需重新安装
- 适合开发和调试
- 可以编辑源代码

## 依赖说明

FishAsyncTask 是一个纯 Python 实现的项目，**无需额外依赖**，仅使用 Python 标准库：

- `threading` - 线程管理
- `queue` - 任务队列
- `uuid` - 任务ID生成
- `time` - 时间处理
- `logging` - 日志记录
- `os` - 环境变量读取
- `typing` - 类型提示（Python 3.5+）

## 验证安装

安装完成后，可以通过以下方式验证：

```python
from fish_async_task import TaskManager

# 创建任务管理器实例
task_manager = TaskManager()
print("安装成功！")

# 关闭任务管理器
task_manager.shutdown()
```

## 构建分发包

如果需要构建分发包用于分发：

### 安装构建工具

```bash
pip install build
```

### 构建源码分发包（sdist）

```bash
python -m build
```

构建完成后，分发包位于 `dist/` 目录下：
- `fish-async-task-0.1.0.tar.gz` - 源码分发包

### 构建 wheel 包

```bash
python -m build --wheel
```

构建完成后，wheel 包位于 `dist/` 目录下：
- `fish_async_task-0.1.0-py3-none-any.whl` - wheel 包

### 同时构建两种格式

```bash
python -m build
```

## 开发环境设置

### 1. 克隆仓库

```bash
git clone https://github.com/fishzjp/FishAsyncTask.git
cd FishAsyncTask
```

### 2. 安装开发依赖

```bash
pip install -e ".[dev]"
```

### 3. 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行测试并显示覆盖率
pytest tests/ --cov=fish_async_task --cov-report=html

# 运行特定测试文件
pytest tests/test_task_manager.py
```

### 4. 代码格式化

```bash
# 使用 black 格式化代码
black fish_async_task/ tests/

# 使用 isort 整理导入
isort fish_async_task/ tests/
```

### 5. 类型检查

```bash
# 使用 mypy 进行类型检查
mypy fish_async_task/
```

## 运行示例

项目提供了示例代码，展示如何使用任务管理器：

```bash
# 基本使用示例
python examples/basic_usage.py
```

示例代码位于 `examples/` 目录下，可以参考这些示例了解如何使用。

## 卸载

如果需要卸载包：

```bash
pip uninstall fish-async-task
```

## 常见问题

### Q: 安装失败怎么办？

A: 请检查：
1. Python 版本是否 >= 3.7：`python --version`
2. pip 是否是最新版本：`pip install --upgrade pip`
3. 网络连接是否正常（如果从 PyPI 或 GitHub 安装）

### Q: 如何安装特定版本？

A: 如果包已发布到 PyPI：
```bash
pip install fish-async-task==0.1.0
```

### Q: 开发模式下如何更新代码？

A: 开发模式下安装后，直接修改代码即可生效，无需重新安装。

## 相关链接

- 📦 PyPI 包（如果已发布）: https://pypi.org/project/fish-async-task/
- 📚 GitHub 仓库: https://github.com/fishzjp/FishAsyncTask
- 🐛 问题反馈: https://github.com/fishzjp/FishAsyncTask/issues
- 📖 文档: https://github.com/fishzjp/FishAsyncTask#readme

