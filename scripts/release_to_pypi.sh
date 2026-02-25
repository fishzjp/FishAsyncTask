#!/bin/bash
# FishAsyncTask v0.2.1 发布到PyPI的脚本

set -e

echo "=================================================="
echo "FishAsyncTask v0.2.1 PyPI发布助手"
echo "=================================================="
echo ""

# 检查当前分支
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "❌ 错误: 必须在main分支上发布"
    echo "   当前分支: $CURRENT_BRANCH"
    exit 1
fi

echo "✅ 当前分支: $CURRENT_BRANCH"
echo ""

# 检查标签是否存在
if ! git rev-parse v0.2.1 >/dev/null 2>&1; then
    echo "❌ 错误: 标签v0.2.1不存在"
    exit 1
fi

echo "✅ Git标签: v0.2.1"
echo ""

# 检查是否推送了标签
TAG_PUSHED=$(git ls-remote --tags origin | grep v0.2.1 || echo "")
if [ -z "$TAG_PUSHED" ]; then
    echo "⚠️  警告: 标签v0.2.1未推送到远程"
    echo "   请先运行: git push origin v0.2.1"
    exit 1
fi

echo "✅ 标签已推送到远程"
echo ""

# 步骤1: 安装构建工具
echo "=================================================="
echo "步骤1: 安装构建工具"
echo "=================================================="
echo ""
echo "正在安装 build 和 twine..."
pip install --upgrade build twine
echo "✅ 构建工具安装完成"
echo ""

# 步骤2: 清理旧的构建
echo "=================================================="
echo "步骤2: 清理旧的构建文件"
echo "=================================================="
echo ""
echo "正在删除旧的构建文件..."
rm -rf dist/ build/ *.egg-info
echo "✅ 清理完成"
echo ""

# 步骤3: 构建发布包
echo "=================================================="
echo "步骤3: 构建发布包"
echo "=================================================="
echo ""
echo "正在构建..."
python -m build
echo "✅ 构建完成"
echo ""

# 步骤4: 检查构建包
echo "=================================================="
echo "步骤4: 检查构建包"
echo "=================================================="
echo ""
echo "正在检查构建包..."
twine check dist/*
echo "✅ 检查通过"
echo ""

# 显示构建结果
echo "=================================================="
echo "构建结果"
echo "=================================================="
echo ""
ls -lh dist/
echo ""

# 步骤5: 询问发布目标
echo "=================================================="
echo "步骤5: 选择发布目标"
echo "=================================================="
echo ""
echo "请选择发布目标:"
echo "  1) TestPyPI (测试发布)"
echo "  2) PyPI (正式发布)"
echo "  3) 先TestPyPI,再PyPI (推荐)"
echo "  4) 取消"
echo ""
read -p "请输入选项 (1-4): " -n 1 -r
echo ""
echo ""

case $REPLY in
    1)
        echo "=================================================="
        echo "发布到TestPyPI"
        echo "=================================================="
        echo ""
        echo "正在发布到TestPyPI..."
        twine upload --repository testpypi dist/*
        echo ""
        echo "✅ 发布到TestPyPI成功!"
        echo ""
        echo "测试安装:"
        echo "  pip install --index-url https://test.pypi.org/simple/ fish-async-task==0.2.1"
        ;;
    2)
        echo "=================================================="
        echo "发布到PyPI (正式发布)"
        echo "=================================================="
        echo ""
        echo "⚠️  警告: 此操作将发布到PyPI正式仓库!"
        echo "   这是一个不可逆的操作!"
        echo ""
        read -p "确认发布? (yes/NO) " -r
        echo ""
        if [[ $REPLY == "yes" ]]; then
            echo "正在发布到PyPI..."
            twine upload dist/*
            echo ""
            echo "✅ 发布到PyPI成功!"
            echo ""
            echo "安装命令:"
            echo "  pip install fish-async-task==0.2.1"
        else
            echo "❌ 已取消发布"
            exit 0
        fi
        ;;
    3)
        echo "=================================================="
        echo "先发布到TestPyPI,再发布到PyPI"
        echo "=================================================="
        echo ""
        echo "步骤1: 发布到TestPyPI..."
        twine upload --repository testpypi dist/*
        echo "✅ TestPyPI发布成功!"
        echo ""
        echo "测试安装:"
        echo "  pip install --index-url https://test.pypi.org/simple/ fish-async-task==0.2.1"
        echo ""
        read -p "测试完成后按回车继续发布到PyPI..." -r
        echo ""
        echo "步骤2: 发布到PyPI..."
        echo "⚠️  警告: 此操作将发布到PyPI正式仓库!"
        echo ""
        read -p "确认发布? (yes/NO) " -r
        echo ""
        if [[ $REPLY == "yes" ]]; then
            twine upload dist/*
            echo ""
            echo "✅ 发布到PyPI成功!"
            echo ""
            echo "安装命令:"
            echo "  pip install fish-async-task==0.2.1"
        else
            echo "❌ 已取消PyPI发布"
            exit 0
        fi
        ;;
    4)
        echo "❌ 已取消发布"
        exit 0
        ;;
    *)
        echo "❌ 无效选项"
        exit 1
        ;;
esac

echo ""
echo "=================================================="
echo "🎉 发布流程完成!"
echo "=================================================="
echo ""
echo "后续步骤:"
echo "  1. 访问PyPI验证发布: https://pypi.org/project/fish-async-task/"
echo "  2. 创建GitHub Release: https://github.com/fishzjp/FishAsyncTask/releases/new"
echo "     标签: v0.2.1"
echo "     标题: v0.2.1 - 代码质量改进版本"
echo "     描述: 使用 .github/RELEASE_NOTES_0.2.1.md"
echo "  3. 测试安装: pip install fish-async-task==0.2.1"
echo ""
