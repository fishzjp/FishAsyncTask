# 跨平台 Cython 编译指南

本指南说明如何在不同的操作系统上编译 FishAsyncTask 的 Cython 扩展。

## 系统要求

### 通用要求
- Python 3.9+
- Cython 3.0+
- C 编译器

### Windows

#### 1. 安装 Visual C++ Build Tools

下载并安装 [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

或安装完整的 Visual Studio Community（选择"使用 C++ 的桌面开发"工作负载）

#### 2. 安装 Python 和 Cython

```bash
pip install cython
```

#### 3. 编译

在命令提示符或 PowerShell 中：

```bash
python setup_cython.py build_ext --inplace
```

### Linux

#### Ubuntu/Debian

```bash
# 安装编译工具
sudo apt-get update
sudo apt-get install build-essential python3-dev

# 安装 Cython
pip install cython

# 编译
python setup_cython.py build_ext --inplace
```

#### CentOS/RHEL/Fedora

```bash
# 安装编译工具
sudo dnf install gcc python3-devel

# 或使用 yum（CentOS/RHEL）
# sudo yum install gcc python3-devel

# 安装 Cython
pip install cython

# 编译
python setup_cython.py build_ext --inplace
```

#### Arch Linux

```bash
# 安装编译工具
sudo pacman -S base-devel python

# 安装 Cython
pip install cython

# 编译
python setup_cython.py build_ext --inplace
```

### macOS

#### 使用 Xcode Command Line Tools

```bash
# 安装 Xcode Command Line Tools
xcode-select --install

# 安装 Cython
pip install cython

# 编译
python setup_cython.py build_ext --inplace
```

#### 使用 Homebrew

```bash
# 安装编译工具
brew install python@3.11

# 安装 Cython
pip3 install cython

# 编译
python3 setup_cython.py build_ext --inplace
```

## 验证编译

编译成功后，应该能看到以下文件：

```bash
# Linux/macOS
ls -la fish_async_task/_cython/_sharded_status*.so
ls -la fish_async_task/_cython/_priority_queue*.so

# Windows
dir fish_async_task\_cython\_sharded_status*.pyd
dir fish_async_task\_cython\_priority_queue*.pyd
```

## 常见问题

### 问题 1：找不到编译器

**错误信息**：
```
error: Microsoft Visual C++ 14.0 is required
```

**解决方案**：
- Windows：安装 Visual C++ Build Tools
- Linux：安装 `build-essential` 或 `python3-dev`
- macOS：运行 `xcode-select --install`

### 问题 2：Python.h 找不到

**错误信息**：
```
fatal error: Python.h: No such file or directory
```

**解决方案**：

**Ubuntu/Debian**：
```bash
sudo apt-get install python3-dev
```

**CentOS/RHEL**：
```bash
sudo dnf install python3-devel
```

**macOS**：
```bash
brew install python@3.11
```

### 问题 3：链接错误

**错误信息**：
```
ld: library not found for -lpython3.9
```

**解决方案**：

确保 Python 开发头文件已安装，并设置正确的包含路径：

```bash
# Linux/macOS
export CFLAGS="-I$(python3 -m sysconfig | grep INCLUDEPY | cut -d= -f2 | tr -d ' ')"

# Windows
set INCLUDE=%INCLUDE%;C:\Python39\include
```

### 问题 4：Cython 版本不兼容

**错误信息**：
```
AttributeError: 'Cython.Compiler.Main.Context' object has no attribute 'cython_compile'
```

**解决方案**：

升级 Cython 到最新版本：

```bash
pip install --upgrade cython
```

## CI/CD 配置

### GitHub Actions

```yaml
name: Build Cython Extensions

on: [push, pull_request]

jobs:
  build:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ['3.9', '3.10', '3.11', '3.12']

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install Cython
      run: pip install cython

    - name: Install build dependencies (Linux)
      if: runner.os == 'Linux'
      run: sudo apt-get install -y build-essential python3-dev

    - name: Build Cython extensions
      run: python setup_cython.py build_ext --inplace

    - name: Run tests
      run: pytest tests/ -v
```

### GitLab CI

```yaml
build:
  image: python:3.11
  script:
    - apt-get update && apt-get install -y build-essential python3-dev
    - pip install cython
    - python setup_cython.py build_ext --inplace
    - pytest tests/ -v

  artifacts:
    paths:
      - fish_async_task/_cython/*.so
```

## 性能优化选项

### 编译优化

在 `setup_cython.py` 中添加编译优化选项：

```python
ext_modules = [
    Extension(
        "fish_async_task._cython._sharded_status",
        ["fish_async_task/_cython/_sharded_status.pyx"],
        extra_compile_args=["-O3", "-march=native"],
    ),
]
```

### Cython 编译指令

在 `.pyx` 文件顶部添加：

```cython
# cython: language_level=3
# cython: embedsignature=True
# cython: cdivision=True
# cython: boundscheck=False
# cython: wraparound=False
```

## 清理编译文件

如果需要清理编译文件并重新编译：

```bash
# Linux/macOS
rm -rf build/ fish_async_task/_cython/*.so fish_async_task/_cython/*.c

# Windows
rmdir /s /q build
del fish_async_task\_cython\*.so fish_async_task\_cython\*.c
```

## 发布到 PyPI

如果要将编译好的扩展发布到 PyPI：

1. 在所有平台上编译扩展
2. 使用 `cibuildwheel` 自动构建多平台 wheels

```bash
pip install cibuildwheel

# 构建 wheels
cibuildwheel --platform linux

# 发布到 PyPI
twine upload wheelhouse/*
```

## 相关文档

- [Cython 官方文档](https://cython.readthedocs.io/)
- [Python 扩展构建指南](https://docs.python.org/3/extending/building.html)
- [Cython 编译安装指南](CYTHON_INSTALLATION.md)
