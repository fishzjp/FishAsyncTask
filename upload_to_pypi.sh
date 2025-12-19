#!/bin/bash
# PyPI 上传脚本
# 使用方法：
#   1. 设置环境变量：
#      export TWINE_USERNAME=__token__
#      export TWINE_PASSWORD=pypi-你的API令牌
#   2. 运行脚本：
#      bash upload_to_pypi.sh

set -e

echo "=== FishAsyncTask PyPI 上传脚本 ==="
echo ""

# 检查环境变量
if [ -z "$TWINE_USERNAME" ] || [ -z "$TWINE_PASSWORD" ]; then
    echo "❌ 错误: 请先设置环境变量"
    echo ""
    echo "请运行以下命令设置凭据："
    echo "  export TWINE_USERNAME=__token__"
    echo "  export TWINE_PASSWORD=pypi-你的API令牌"
    echo ""
    echo "获取 PyPI API 令牌："
    echo "  1. 登录 https://pypi.org"
    echo "  2. 进入 Account settings > API tokens"
    echo "  3. 创建新的 API token"
    echo "  4. 复制令牌（格式：pypi-xxxxxxxxxxxx）"
    exit 1
fi

# 检查文件是否存在
if [ ! -f "dist/fish_async_task-0.2.0-py3-none-any.whl" ] || [ ! -f "dist/fish_async_task-0.2.0.tar.gz" ]; then
    echo "❌ 错误: 构建文件不存在，请先运行构建："
    echo "  python -m build"
    exit 1
fi

# 验证包
echo "✓ 验证包..."
python -m twine check dist/* || {
    echo "❌ 包验证失败"
    exit 1
}

echo ""
echo "准备上传以下文件："
ls -lh dist/*.{whl,tar.gz} 2>/dev/null
echo ""

# 确认上传
read -p "确认上传到 PyPI? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消上传"
    exit 0
fi

# 上传
echo ""
echo "正在上传到 PyPI..."
python -m twine upload dist/*

echo ""
echo "✅ 上传完成！"
echo ""
echo "包已发布到: https://pypi.org/project/fish-async-task/"
echo ""
echo "安装命令："
echo "  pip install fish-async-task"

