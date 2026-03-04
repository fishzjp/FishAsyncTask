#!/bin/bash
# 多平台构建和发布脚本
# 用于构建 FishAsyncTask 的多平台 wheels 并发布到 PyPI

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置
PACKAGE_NAME="fish-async-task"
VERSION=$(grep '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')
RUST_VERSION=$(grep '^version = ' fish_async_task_core/Cargo.toml | head -1 | sed 's/version = "\(.*\)"/\1/')

echo -e "${GREEN}=== FishAsyncTask 多平台构建和发布脚本 ===${NC}"
echo "版本: ${VERSION}"
echo "Rust 版本: ${RUST_VERSION}"

# 检查版本一致性
if [ "$VERSION" != "$RUST_VERSION" ]; then
    echo -e "${RED}错误: pyproject.toml 和 Cargo.toml 版本不一致！${NC}"
    echo "pyproject.toml: $VERSION"
    echo "Cargo.toml: $RUST_VERSION"
    exit 1
fi

# 检查必要工具
check_tool() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}错误: $1 未安装${NC}"
        exit 1
    fi
}

check_tool maturin
check_tool python3

# 解析命令行参数
BUILD_ONLY=false
PUBLISH_ONLY=false
SKIP_TESTS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --publish-only)
            PUBLISH_ONLY=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --help)
            echo "用法: $0 [选项]"
            echo "选项:"
            echo "  --build-only    仅构建，不发布"
            echo "  --publish-only  仅发布，不构建"
            echo "  --skip-tests    跳过测试"
            echo "  --help          显示此帮助信息"
            exit 0
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            exit 1
            ;;
    esac
done

# 运行测试
run_tests() {
    if [ "$SKIP_TESTS" = true ]; then
        echo -e "${YELLOW}跳过测试${NC}"
        return
    fi

    echo -e "${GREEN}=== 运行测试 ===${NC}"
    python3 -m pytest tests/ -v --tb=short
    echo -e "${GREEN}测试通过${NC}"
}

# 构建 Rust 扩展
build_rust() {
    echo -e "${GREEN}=== 构建 Rust 扩展 ===${NC}"
    cd fish_async_task_core
    maturin build --release --strip
    cd ..
    echo -e "${GREEN}Rust 扩展构建完成${NC}"
}

# 构建 wheels
build_wheels() {
    echo -e "${GREEN}=== 构建 Python Wheels ===${NC}"

    # 创建 dist 目录
    mkdir -p dist

    # 目标平台
    TARGETS=(
        "x86_64-unknown-linux-gnu"
        "aarch64-unknown-linux-gnu"
        "x86_64-apple-darwin"
        "aarch64-apple-darwin"
        "x86_64-pc-windows-msvc"
    )

    # 检查当前平台
    CURRENT_OS=$(uname -s)
    CURRENT_ARCH=$(uname -m)

    echo "当前平台: $CURRENT_OS $CURRENT_ARCH"

    # 根据当前平台构建
    case "$CURRENT_OS" in
        Darwin)
            echo "为 macOS 构建..."
            if [ "$CURRENT_ARCH" = "arm64" ]; then
                echo -e "${GREEN}构建 aarch64-apple-darwin (Apple Silicon)${NC}"
                cd fish_async_task_core
                maturin build --release --target aarch64-apple-darwin --strip
                mv target/aarch64-apple-darwin/release/*.whl ../../dist/ 2>/dev/null || true
                cd ..
            else
                echo -e "${GREEN}构建 x86_64-apple-darwin (Intel)${NC}"
                cd fish_async_task_core
                maturin build --release --target x86_64-apple-darwin --strip
                mv target/x86_64-apple-darwin/release/*.whl ../../dist/ 2>/dev/null || true
                cd ..
            fi
            ;;
        Linux)
            echo "为 Linux 构建..."
            if [ "$CURRENT_ARCH" = "aarch64" ]; then
                echo -e "${GREEN}构建 aarch64-unknown-linux-gnu${NC}"
                cd fish_async_task_core
                maturin build --release --target aarch64-unknown-linux-gnu --strip
                mv target/aarch64-unknown-linux-gnu/release/*.whl ../../dist/ 2>/dev/null || true
                cd ..
            else
                echo -e "${GREEN}构建 x86_64-unknown-linux-gnu${NC}"
                cd fish_async_task_core
                maturin build --release --target x86_64-unknown-linux-gnu --strip
                mv target/x86_64-unknown-linux-gnu/release/*.whl ../../dist/ 2>/dev/null || true
                cd ..
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            echo "为 Windows 构建..."
            echo -e "${GREEN}构建 x86_64-pc-windows-msvc${NC}"
            cd fish_async_task_core
            maturin build --release --target x86_64-pc-windows-msvc --strip
            mv target/x86_64-pc-windows-msvc/release/*.whl ../../dist/ 2>/dev/null || true
            cd ..
            ;;
        *)
            echo -e "${YELLOW}未知平台，使用通用构建${NC}"
            cd fish_async_task_core
            maturin build --release --strip
            mv target/wheels/*.whl ../../dist/ 2>/dev/null || true
            cd ..
            ;;
    esac

    # 同时构建通用 wheel
    cd fish_async_task_core
    maturin build --release --strip
    mv target/wheels/*.whl ../../dist/ 2>/dev/null || true
    cd ..

    echo -e "${GREEN}Wheels 构建完成${NC}"
    ls -lh dist/
}

# 发布到 PyPI
publish_pypi() {
    echo -e "${GREEN}=== 发布到 PyPI ===${NC}"

    # 检查 TWINE_USERNAME
    if [ -z "$TWINE_USERNAME" ] && [ -z "$TWINE_TOKEN" ]; then
        echo -e "${YELLOW}警告: 未设置 TWINE_USERNAME 或 TWINE_TOKEN${NC}"
        echo "请设置环境变量:"
        echo "  export TWINE_USERNAME=__token__"
        echo "  export TWINE_TOKEN=<your-pypi-token>"
        read -p "是否继续? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "取消发布"
            exit 1
        fi
    fi

    # 先发布到 TestPyPI 进行验证
    echo -e "${YELLOW}是否先发布到 TestPyPI 进行验证? (y/N)${NC}"
    read -r -n 1 REPLY
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "发布到 TestPyPI..."
        python3 -m twine upload --repository testpypi dist/*
        echo -e "${GREEN}已发布到 TestPyPI${NC}"
        echo "请验证后按回车继续发布到正式 PyPI..."
        read
    fi

    # 发布到正式 PyPI
    echo "发布到 PyPI..."
    python3 -m twine upload dist/*
    echo -e "${GREEN}发布完成${NC}"
}

# 清理
clean() {
    echo -e "${GREEN}=== 清理构建产物 ===${NC}"
    rm -rf fish_async_task_core/target/
    rm -rf dist/
    echo -e "${GREEN}清理完成${NC}"
}

# 主流程
main() {
    if [ "$PUBLISH_ONLY" = false ]; then
        run_tests
        build_wheels
    fi

    if [ "$BUILD_ONLY" = false ]; then
        publish_pypi
    fi

    echo -e "${GREEN}=== 完成 ===${NC}"
}

# 执行主流程
main
