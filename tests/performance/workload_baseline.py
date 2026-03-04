#!/usr/bin/env python
"""
性能基线建立脚本

用于建立 FishAsyncTask 的性能基线，使用 py-spy 和 pyinstrument 分析热点。
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def create_workload_script(num_tasks: int = 10000) -> str:
    """创建工作负载脚本"""
    return f"""
import time
from fish_async_task import TaskManager

def simple_task(x):
    return x * x

def main():
    manager = TaskManager()

    # 提交任务
    print("Submitting {num_tasks} tasks...")
    start = time.time()
    for i in range({num_tasks}):
        manager.submit_task(simple_task, i)
    submit_time = time.time() - start
    throughput = {num_tasks} / submit_time
    print(f"Submit time: {{submit_time:.3f}}s ({{throughput:.0f}} tasks/s)")

    # 等待完成
    print("Waiting for completion...")
    timeout = 60  # 60秒超时
    elapsed = 0
    while elapsed < timeout:
        if manager.task_queue.empty():
            # 再等待一点时间让现有任务完成
            time.sleep(0.5)
            break
        time.sleep(0.1)
        elapsed += 0.1

    total_time = time.time() - start
    print(f"Total time: {{total_time:.3f}}s")

    # 获取结果
    for i in range(min(10, {num_tasks})):
        status = manager.get_task_status(f"task_{{i}}")
        print(f"Task {{i}}: {{status}}")

    manager.shutdown()

if __name__ == "__main__":
    main()
"""


def run_py_spy(script_path: str, output_dir: Path):
    """使用 py-spy 分析性能"""
    print("\n=== 使用 py-spy 分析性能 ===")
    output_svg = output_dir / "py-spy-flamegraph.svg"
    output_txt = output_dir / "py-spy-top.txt"

    # 生成火焰图
    cmd = [
        "py-spy", "record",
        "-o", str(output_svg),
        "--format", "flamegraph",
        "--", sys.executable, str(script_path)
    ]
    print(f"运行: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # 生成 top 输出
    cmd = [
        "py-spy", "top",
        "--", sys.executable, str(script_path)
    ]
    print(f"运行: {' '.join(cmd)}")
    with open(output_txt, "w") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
        # 非交互式运行可能会失败，忽略错误
        if result.returncode != 0:
            print("注意: py-spy top 在非交互式环境中可能无法运行")

    print(f"✓ py-spy 结果已保存到: {output_dir}")


def run_pyinstrument(script_path: str, output_dir: Path):
    """使用 pyinstrument 分析性能"""
    print("\n=== 使用 pyinstrument 分析性能 ===")
    output_html = output_dir / "pyinstrument-report.html"

    cmd = [
        sys.executable, "-m", "pyinstrument",
        "-o", str(output_html),
        str(script_path)
    ]
    print(f"运行: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    print(f"✓ pyinstrument 结果已保存到: {output_html}")


def run_baseline_measurement(script_path: str, output_dir: Path):
    """运行基线测量"""
    print("\n=== 基线性能测量 ===")

    import subprocess
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True
    )

    output_file = output_dir / "baseline-output.txt"
    with open(output_file, "w") as f:
        f.write(result.stdout)
        if result.stderr:
            f.write(f"\nSTDERR:\n{result.stderr}")

    print(result.stdout)
    print(f"✓ 基线输出已保存到: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="建立 FishAsyncTask 性能基线")
    parser.add_argument("--tasks", type=int, default=10000, help="任务数量")
    parser.add_argument("--output", type=str, default="tests/performance/rust_baseline",
                       help="输出目录")
    parser.add_argument("--py-spy", action="store_true", help="运行 py-spy 分析")
    parser.add_argument("--pyinstrument", action="store_true", help="运行 pyinstrument 分析")
    parser.add_argument("--all", action="store_true", help="运行所有分析")

    args = parser.parse_args()

    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建工作负载脚本
    script_content = create_workload_script(args.tasks)
    script_path = output_dir / f"workload_{args.tasks}_tasks.py"
    with open(script_path, "w") as f:
        f.write(script_content)
    print(f"✓ 工作负载脚本已创建: {script_path}")

    # 运行基线测量
    run_baseline_measurement(script_path, output_dir)

    # 运行性能分析
    if args.all or args.py_spy:
        run_py_spy(script_path, output_dir)

    if args.all or args.pyinstrument:
        run_pyinstrument(script_path, output_dir)

    print(f"\n=== 性能基线建立完成 ===")
    print(f"结果保存在: {output_dir}")


if __name__ == "__main__":
    main()
