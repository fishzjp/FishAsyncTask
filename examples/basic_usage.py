"""
基本使用示例
"""

import time
import logging
from fish_async_task import TaskManager

# 配置日志
logging.basicConfig(level=logging.INFO)

# 创建任务管理器
task_manager = TaskManager()


def simple_task(name: str, delay: int = 1):
    """简单的任务函数"""
    print(f"开始执行任务: {name}")
    time.sleep(delay)
    result = f"任务 {name} 完成"
    print(result)
    return result


def main():
    # 提交多个任务
    task_ids = []
    for i in range(5):
        task_id = task_manager.submit_task(simple_task, f"任务-{i+1}", delay=2)
        if task_id:
            task_ids.append(task_id)
            print(f"已提交任务，ID: {task_id}")

    # 等待任务完成并查询状态
    while task_ids:
        for task_id in task_ids[:]:
            status = task_manager.get_task_status(task_id)
            if status:
                if status["status"] == "completed":
                    print(f"任务 {task_id} 完成，结果: {status.get('result')}")
                    task_ids.remove(task_id)
                elif status["status"] == "failed":
                    print(f"任务 {task_id} 失败: {status.get('error')}")
                    task_ids.remove(task_id)
        if task_ids:
            time.sleep(0.5)

    # 关闭任务管理器
    task_manager.shutdown()
    print("所有任务完成，任务管理器已关闭")


if __name__ == "__main__":
    main()

