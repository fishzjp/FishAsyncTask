# FishAsyncTask v0.3.1 Release Notes

## 跨平台发布版本

FishAsyncTask v0.3.1 提供 CI/CD 自动化发布流程和跨平台 wheel 支持。

## 主要变更

- 📦 **跨平台 wheel**：支持 Linux, macOS, Windows 自动构建
- 🔄 **CI/CD 自动化**：GitHub Actions 自动构建和发布
- ✅ **冒烟测试**：新增快速验证核心功能的测试套件

## 安装

```bash
pip install fish-async-task
```

## 完整变更

- 优化 CI/CD 流程，只运行冒烟测试以加快构建速度
- 更新文档链接到 GitHub Pages
- 修复 CI 工作流中的路径配置问题
- 修复 Windows 平台 patchelf 安装问题
- 修复 README.md 中的导入示例错误

## 文档

完整文档：https://fishzjp.github.io/FishAsyncTask/
