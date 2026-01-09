# Migration Guide: 从 v0.2.0 升级到 v0.2.1

**版本**: 0.2.0 → 0.2.1
**变更类型**: Python版本要求升级 (3.7 → 3.9)
**影响**: ⚠️ Breaking Change (仅Python版本要求)
**难度**: 简单 (5-10分钟)

---

## 📋 概述

FishAsyncTask v0.2.1 将最低Python版本要求从**3.7**提升至**3.9**。本指南将帮助您顺利完成升级。

**好消息**:
- ✅ **无需修改任何应用代码**
- ✅ 所有API保持100%兼容
- ✅ 只需升级Python运行环境

**为什么需要升级**:
- Python 3.7已于2023-06-27停止维护(EOL)
- Python 3.8已于2024-10-07停止维护(EOL)
- mypy 1.19+不再支持Python 3.7
- 更好的类型检查和IDE支持

---

## 🎯 升级前检查

### 当前Python版本检查

```bash
# 检查当前Python版本
python --version

# 检查fish-async-task版本
pip show fish-async-task
```

**预期输出** (v0.2.0):
```
Python 3.7.x 或 3.8.x
Name: fish-async-task
Version: 0.2.0
```

### 受影响的用户

**需要升级**:
- ✅ 使用Python 3.7的用户
- ✅ 使用Python 3.8的用户

**无需升级**:
- ✅ 使用Python 3.9+的用户
- ✅ 通过Docker/container部署的用户(如果镜像已更新)

---

## 🚀 升级步骤

### 方法1: 使用pyenv (推荐,最简单)

#### 步骤1: 安装pyenv (如果未安装)

**macOS**:
```bash
# 使用Homebrew安装
brew install pyenv

# 添加到shell配置
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc

# 重新加载shell
source ~/.zshrc
```

**Linux**:
```bash
# 使用安装脚本
curl https://pyenv.run | bash

# 添加到PATH
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc

# 重新加载shell
source ~/.bashrc
```

#### 步骤2: 安装Python 3.9

```bash
# 查看可用的Python版本
pyenv install --list | grep "3.9"

# 安装Python 3.9.20 (推荐)
pyenv install 3.9.20
```

#### 步骤3: 设置项目Python版本

```bash
cd /path/to/your/project

# 设置本地Python版本
pyenv local 3.9.20

# 验证
python --version
# 应该输出: Python 3.9.20
```

#### 步骤4: 重新创建虚拟环境

```bash
# 删除旧虚拟环境
rm -rf venv/

# 创建新虚拟环境
python -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Windows: venv\Scripts\activate

# 升级pip
pip install --upgrade pip setuptools wheel
```

#### 步骤5: 升级fish-async-task

```bash
# 升级到v0.2.1
pip install --upgrade fish-async-task

# 如果使用[dev]可选依赖
pip install --upgrade "fish-async-task[dev]"

# 验证版本
pip show fish-async-task
# 应该输出: Version: 0.2.1
```

#### 步骤6: 运行应用

```bash
# 运行您的应用
python your_app.py

# 或者运行测试
pytest tests/ -v
```

**预期**: 一切正常运行! ✅

---

### 方法2: 使用uv (最新,最快)

#### 步骤1: 安装uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### 步骤2: 设置Python版本

```bash
cd /path/to/your/project

# 固定Python版本
uv python pin 3.9.20

# 验证
uv python --version
# 应该输出: Python 3.9.20
```

#### 步骤3: 同步依赖

```bash
# 同步项目依赖
uv sync

# 或者直接安装
uv pip install fish-async-task --upgrade
```

#### 步骤4: 运行应用

```bash
# 使用uv运行Python
uv run python your_app.py

# 或运行测试
uv run pytest tests/ -v
```

**预期**: 一切正常运行! ✅

---

### 方法3: 使用官方安装包

#### 步骤1: 下载Python 3.9

访问 https://www.python.org/downloads/ 并下载:
- **Windows**: Python 3.9.x Windows installer (64-bit)
- **macOS**: Python 3.9.x macOS 64-bit universal2 installer
- **Linux**: 从源码编译或使用发行版包管理器

#### 步骤2: 安装Python 3.9

**Windows**:
1. 运行下载的`.exe`安装程序
2. ⚠️ **重要**: 勾选"Add Python to PATH"
3. 点击"Install Now"

**macOS**:
1. 运行下载的`.pkg`安装程序
2. 按照安装向导完成安装

**Linux** (Ubuntu/Debian):
```bash
# 更新包列表
sudo apt update

# 安装依赖
sudo apt install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev wget

# 下载Python 3.9.20
wget https://www.python.org/ftp/python/3.9.20/Python-3.9.20.tgz

# 解压
tar -xf Python-3.9.20.tgz
cd Python-3.9.20

# 配置
./configure --enable-optimizations

# 编译并安装
make -j$(nproc)
sudo make altinstall

# 验证
python3.9 --version
```

#### 步骤3: 重新创建虚拟环境

```bash
cd /path/to/your/project

# 删除旧虚拟环境
rm -rf venv/

# 创建新虚拟环境
python3.9 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Windows: venv\Scripts\activate

# 升级pip
pip install --upgrade pip setuptools wheel
```

#### 步骤4: 升级fish-async-task

```bash
# 升级到v0.2.1
pip install --upgrade fish-async-task

# 验证版本
pip show fish-async-task
# 应该输出: Version: 0.2.1
```

#### 步骤5: 运行应用

```bash
# 运行您的应用
python your_app.py

# 或者运行测试
pytest tests/ -v
```

**预期**: 一切正常运行! ✅

---

### 方法4: Docker部署

如果您使用Docker,只需更新基础镜像:

#### Dockerfile更新

**之前** (Python 3.7):
```dockerfile
FROM python:3.7-slim

WORKDIR /app
COPY . .
RUN pip install fish-async-task

CMD ["python", "your_app.py"]
```

**现在** (Python 3.9):
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY . .
RUN pip install fish-async-task==0.2.1

CMD ["python", "your_app.py"]
```

#### docker-compose.yml更新

```yaml
services:
  app:
    image: your-docker-image
    build:
      context: .
      dockerfile: Dockerfile
    # 无需其他更改 ✅
```

#### 重新构建镜像

```bash
# 重新构建镜像
docker-compose build

# 启动服务
docker-compose up -d
```

**预期**: 一切正常运行! ✅

---

## ✅ 升级验证

### 验证Python版本

```bash
python --version
# 应该输出: Python 3.9.x 或更高
```

### 验证fish-async-task版本

```bash
pip show fish-async-task
# 应该输出: Version: 0.2.1
```

### 运行测试脚本

创建`test_upgrade.py`:

```python
#!/usr/bin/env python
"""测试升级是否成功"""

from fish_async_task import TaskManager

def simple_task():
    return "Hello from v0.2.1!"

# 创建任务管理器
manager = TaskManager()

# 提交任务
task_id = manager.submit_task(simple_task, (), {})

# 等待结果
import time
time.sleep(0.5)

# 获取结果
status = manager.get_task_status(task_id)
print(f"任务状态: {status['status']}")
print(f"任务结果: {status.get('result')}")

# 清理
manager.shutdown()

print("✅ 升级成功!")
```

运行测试:
```bash
python test_upgrade.py
```

**预期输出**:
```
任务状态: completed
任务结果: Hello from v0.2.1!
✅ 升级成功!
```

---

## 🐛 常见问题

### Q1: 我无法升级Python版本怎么办?

**A**: 如果您必须使用Python 3.7或3.8:

1. **继续使用v0.2.0**: v0.2.0仍然是稳定版本
2. **使用Docker**: Docker镜像可以继续使用Python 3.7
3. **联系支持**: 在GitHub Issues中说明您的特殊情况

```dockerfile
# Dockerfile示例 (锁定在Python 3.7和v0.2.0)
FROM python:3.7-slim

WORKDIR /app
RUN pip install fish-async-task==0.2.0

COPY . .
CMD ["python", "your_app.py"]
```

---

### Q2: 升级后导入失败怎么办?

**错误**: `ModuleNotFoundError: No module named 'fish_async_task'`

**解决方案**:
```bash
# 确认使用正确的Python环境
which python

# 应该指向新安装的Python 3.9

# 重新安装fish-async-task
pip install fish-async-task==0.2.1

# 验证安装
python -c "from fish_async_task import TaskManager; print('OK')"
```

---

### Q3: 类型检查错误怎么办?

**错误**: mypy显示类型错误

**解决方案**:
```bash
# 确认mypy版本
mypy --version
# 应该是1.0.0或更高

# 清除缓存重新检查
mypy fish_async_task/ --no-error-summary
```

如果仍有问题,请在GitHub Issues报告。

---

### Q4: 虚拟环境激活失败怎么办?

**错误**: `command not found: activate`

**解决方案**:

**macOS/Linux**:
```bash
# 确保使用正确的激活脚本
source venv/bin/activate
```

**Windows (Command Prompt)**:
```cmd
venv\Scripts\activate.bat
```

**Windows (PowerShell)**:
```powershell
venv\Scripts\Activate.ps1
```

---

### Q5: Windows上Python安装失败怎么办?

**解决方案**:

1. **以管理员身份运行安装程序**
2. **禁用杀毒软件** (临时)
3. **勾选"Add Python to PATH"**
4. **选择"Install for all users"**

---

## 📊 升级后的好处

升级到v0.2.1后,您将获得:

✅ **更好的类型检查**: mypy 0错误,IDE自动补全更准确
✅ **统一的代码风格**: black和isort自动格式化
✅ **更可靠的并发**: 线程安全验证通过
✅ **更好的日志**: 统一的logging规范
✅ **更安全的配置**: 无硬编码敏感信息
✅ **长期支持**: Python 3.9将持续支持到2025年10月

---

## 🎓 学习资源

### Python 3.9新特性

如果您想了解Python 3.9的新特性:

- [What's New in Python 3.9](https://docs.python.org/3.9/whatsnew/3.9.html)
- [Python 3.9 Release Notes](https://www.python.org/downloads/release/python-3920/)

### 开发工具

- [mypy文档](https://mypy.readthedocs.io/)
- [black文档](https://black.readthedocs.io/)
- [pytest文档](https://docs.pytest.org/)

---

## 💬 需要帮助?

如果在升级过程中遇到任何问题:

1. **查阅文档**: [docs/](../blob/main/docs/)
2. **搜索Issues**: [GitHub Issues](https://github.com/fishzjp/FishAsyncTask/issues)
3. **提交新Issue**: [创建Issue](https://github.com/fishzjp/FishAsyncTask/issues/new)
4. **查看Discussions**: [GitHub Discussions](https://github.com/fishzjp/FishAsyncTask/discussions)

---

## ✅ 升级检查清单

完成升级后,请确认:

- [ ] Python版本 >= 3.9
- [ ] fish-async-task版本 = 0.2.1
- [ ] 虚拟环境已重建
- [ ] 所有依赖已重新安装
- [ ] 应用正常运行
- [ ] 测试全部通过
- [ ] mypy检查通过

**全部通过? 恭喜您升级成功!** 🎉

---

*最后更新: 2025-01-09*
*migration guide for v0.2.1*
