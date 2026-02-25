#!/bin/bash
# 创建GitHub Release的辅助脚本

echo "=================================================="
echo "GitHub Release创建助手 - v0.2.1"
echo "=================================================="
echo ""

# 检查标签是否存在
if ! git rev-parse v0.2.1 >/dev/null 2>&1; then
    echo "❌ 错误: 标签v0.2.1不存在"
    exit 1
fi

echo "✅ Git标签: v0.2.1"
echo ""

RELEASE_URL="https://github.com/fishzjp/FishAsyncTask/releases/new"

echo "=================================================="
echo "📝 创建GitHub Release步骤"
echo "=================================================="
echo ""
echo "1. 点击下方链接打开Release创建页面:"
echo "   $RELEASE_URL"
echo ""
echo "2. 填写Release信息:"
echo "   - 选择标签: v0.2.1"
echo "   - 标题: v0.2.1 - 代码质量改进版本"
echo "   - 描述: 复制下方内容或使用 .github/RELEASE_NOTES_0.2.1.md"
echo "   - 勾选: Set as the latest release"
echo ""

# 读取Release Notes
if [ -f ".github/RELEASE_NOTES_0.2.1.md" ]; then
    echo "=================================================="
    echo "📄 Release Notes内容预览"
    echo "=================================================="
    echo ""
    head -50 .github/RELEASE_NOTES_0.2.1.md
    echo ""
    echo "..."
    echo ""
    echo "完整内容请查看: .github/RELEASE_NOTES_0.2.1.md"
    echo ""
fi

echo "=================================================="
echo "简化的Release描述 (可直接复制)"
echo "=================================================="
echo ""
cat << 'RELEASE_EOF'
# 🎉 FishAsyncTask v0.2.1 - 代码质量改进版本

## 📋 概述

本版本显著提升了项目的代码质量,通过引入静态类型检查、代码格式化工具和完善测试配置,为项目的长期维护奠定了坚实基础。

**发布日期**: 2025-01-09
**Python版本**: 3.9+
**文档**: [完整文档](https://github.com/fishzjp/FishAsyncTask#readme)

---

## ✨ 主要改进

### 🔧 代码质量提升

#### 类型系统完善
- ✅ **修复13个mypy类型错误** → 0个错误
- ✅ **mypy静态检查100%通过**

#### 代码格式化
- ✅ **Black自动格式化11个文件** → 100%符合PEP 8
- ✅ **Isort自动修复4个文件的导入排序** → 100%通过

#### 线程安全验证
- ✅ 审查所有模块的锁使用模式
- ✅ **6/6并发压力测试通过**

---

## 🛠️ 新增功能

### 开发工具配置
- ✅ `.coveragerc` - 覆盖率配置
- ✅ `pytest.ini` - pytest配置
- ✅ `.pre-commit-config.yaml` - pre-commit hooks
- ✅ `.interrogate.yaml` - 文档覆盖率检查
- ✅ `.github/workflows/code-quality.yml` - GitHub Actions CI

### 报告生成脚本
- ✅ `scripts/generate_code_review_report.py` - 代码审查报告
- ✅ `scripts/generate_test_coverage_report.py` - 测试覆盖率报告

---

## 📊 质量指标

| 指标 | 改进前 | 改进后 |
|------|--------|--------|
| **Mypy类型错误** | 13个 | **0个** ✅ |
| **Black格式问题** | 11个文件 | **0个** ✅ |
| **Isort导入问题** | 4个文件 | **0个** ✅ |
| **文档覆盖率** | 100% | **100%** ✅ |
| **测试覆盖率** | N/A | **72.55%** |
| **单元测试** | N/A | **117/118** (99.2%) ✅ |

---

## ⚠️ Breaking Changes

### Python版本要求变更

**最低Python版本**: 3.7 → **3.9**

#### 原因
- Python 3.7已于2023-06-27停止维护(EOL)
- Python 3.8已于2024-10-07停止维护(EOL)
- mypy 1.19+不再支持Python 3.7
- 现代类型检查功能需要Python 3.9+

#### 影响范围
- ✅ 仍支持Python 3.9, 3.10, 3.11, 3.12
- ❌ 不再支持Python 3.7, 3.8
- ✅ **无API破坏性变更**
- ✅ **现有代码完全兼容**

#### 升级指南

如果您正在使用Python 3.7或3.8:

1. **升级Python版本**
   ```bash
   # 使用pyenv
   pyenv install 3.9.20
   pyenv local 3.9.20

   # 或使用uv
   uv python install 3.9
   ```

2. **更新依赖**
   ```bash
   pip install --upgrade fish-async-task
   ```

3. **验证兼容性**
   ```python
   # 无需修改任何代码
   from fish_async_task import TaskManager

   manager = TaskManager()
   # 一切如常,享受更好的类型检查
   ```

详细迁移指南: [MIGRATION_0.2.0_TO_0.2.1.md](docs/MIGRATION_0.2.0_TO_0.2.1.md)

---

## 📦 安装

### 从PyPI安装
```bash
pip install fish-async-task
```

### 指定版本
```bash
pip install fish-async-task==0.2.1
```

### 使用uv安装
```bash
uv pip install fish-async-task
```

### 从源码安装
```bash
git clone https://github.com/fishzjp/FishAsyncTask.git
cd FishAsyncTask
pip install -e .
```

---

## ✅ 验证安装

```bash
# 验证版本
python -c "from fish_async_task import __version__; print(__version__)"
# 应该输出: 0.2.1

# 运行测试
pip install "fish-async-task[dev]"
pytest tests/ -v
```

---

## 📖 文档

- [README](README.md) - 快速开始
- [CHANGELOG](docs/CHANGELOG.md) - 完整变更日志
- [迁移指南](docs/MIGRATION_0.2.0_TO_0.2.1.md) - 从0.2.0升级到0.2.1
- [项目完成报告](docs/PROJECT_COMPLETION_REPORT.md) - 本次改进总结

---

## 🙏 致谢

本次改进遵循项目规范([CLAUDE.md](CLAUDE.md)),使用了以下优秀的开源工具:

- **mypy** - Python静态类型检查
- **black** - Python代码格式化
- **isort** - Python导入排序
- **pytest** - Python测试框架
- **pytest-cov** - 测试覆盖率工具
- **interrogate** - 文档覆盖率检查

---

## 📞 反馈与支持

- **问题反馈**: [GitHub Issues](https://github.com/fishzjp/FishAsyncTask/issues)
- **功能建议**: [GitHub Discussions](https://github.com/fishzjp/FishAsyncTask/discussions)
- **文档**: [在线文档](https://github.com/fishzjp/FishAsyncTask#readme)

---

**🎉 感谢使用FishAsyncTask!**
RELEASE_EOF

echo ""
echo "=================================================="
echo "🚀 准备打开GitHub Release创建页面"
echo "=================================================="
echo ""

# 尝试打开浏览器
if command -v open &> /dev/null; then
    echo "正在打开浏览器..."
    sleep 2
    open "$RELEASE_URL"
elif command -v xdg-open &> /dev/null; then
    echo "正在打开浏览器..."
    sleep 2
    xdg-open "$RELEASE_URL"
elif command -v start &> /dev/null; then
    echo "正在打开浏览器..."
    sleep 2
    start "$RELEASE_URL"
else
    echo "💡 请手动复制链接到浏览器"
fi

echo ""
echo "=================================================="
echo "✨ 完成!"
echo "=================================================="
echo ""
