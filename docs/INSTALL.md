# 安装说明

## 系统要求

- Python 3.9 或更高版本
- pip（Python包管理器）

## 安装方式

### 方式一：从 PyPI 安装（推荐）

```bash
pip install fish-async-task
```

**默认包含 Rust 核心实现**，提供最佳性能。支持主流平台：
- Linux (x86_64, aarch64)
- macOS (x86_64, arm64)
- Windows (x86_64)

### 方式二：从 GitHub 安装

直接从 GitHub 仓库安装最新版本：

```bash
pip install git+https://github.com/fishzjp/FishAsyncTask.git
```

### 方式三：本地安装（开发者）

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
# 安装 Python 依赖
pip install -e ".[dev,performance]"

# 构建并安装 Rust 核心
pip install maturin
maturin develop --release
```

开发模式安装的优势：
- 代码修改后立即生效，无需重新安装
- 适合开发和调试
- 可以编辑源代码

## 依赖说明

### 运行时依赖

FishAsyncTask 核心功能**无需额外依赖**：
- Rust 核心模块（预编译，自动安装）
- Python 标准库：`threading`、`queue`、`uuid`、`time`、`logging`、`os`、`typing`

### 可选依赖

**性能测试依赖** (`[performance]`)：
- `psutil` - 系统资源监控
- `redis` - Redis 后端支持
- `huey` - Huey 队列支持
- `dramatiq` - Dramatiq 队列支持

**开发依赖** (`[dev]`)：
- `pytest`、`pytest-cov`、`pytest-benchmark` - 测试框架
- `black`、`isort` - 代码格式化
- `mypy`、`interrogate` - 代码质量检查
- `maturin` - Rust 扩展构建工具
- `locust` - 负载测试

## 验证安装

### 基础验证

安装完成后，可以通过以下方式验证：

```python
from fish_async_task import TaskManager

# 创建任务管理器实例
task_manager = TaskManager()
print("安装成功！")

# 关闭任务管理器
task_manager.shutdown()
```

### 验证 Rust 核心

检查 Rust 核心是否已启用：

```python
from fish_async_task._rust import is_rust_available

if is_rust_available():
    print("Rust 核心已启用，获得最佳性能")
else:
    print("使用纯 Python 实现")
```

## 构建分发包

如果需要构建分发包用于分发：

### 安装构建工具

```bash
pip install maturin
```

### 构建 wheel 包（包含 Rust 核心）

```bash
maturin build --release --out dist
```

构建完成后，wheel 包位于 `dist/` 目录下：
- `fish_async_task-0.x.x-cp39-abi3-*.whl` - 包含 Rust 核心的 wheel 包

### 构建源码分发包（sdist）

```bash
maturin build --release --sdist --out dist
```

构建完成后，源码包位于 `dist/` 目录下：
- `fish_async_task-0.x.x.tar.gz` - 源码分发包（用户需要 Rust 工具链编译）

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
1. Python 版本是否 >= 3.9：`python --version`
2. pip 是否是最新版本：`pip install --upgrade pip`
3. 网络连接是否正常（如果从 PyPI 或 GitHub 安装）

### Q: 如何安装特定版本？

A: 如果包已发布到 PyPI：
```bash
pip install fish-async-task==0.3.0
```

### Q: 开发模式下如何更新代码？

A: 开发模式下安装后，直接修改 Python 代码即可生效。如果修改了 Rust 代码，需要重新运行：
```bash
maturin develop --release
```

### Q: 我的平台不支持预编译 wheel 怎么办？

A: 可以从源码构建，需要安装 Rust 工具链：
```bash
# 安装 Rust（如果还没有）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 然后正常安装
pip install fish-async-task
```

## 相关链接

- 📦 PyPI 包（如果已发布）: https://pypi.org/project/fish-async-task/
- 📚 GitHub 仓库: https://github.com/fishzjp/FishAsyncTask
- 🐛 问题反馈: https://github.com/fishzjp/FishAsyncTask/issues
- 📖 文档: https://github.com/fishzjp/FishAsyncTask#readme

