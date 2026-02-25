"""
FishAsyncTask 基本使用示例

演示 FishAsyncTask 的核心功能使用方法。
"""

import time
import logging
from fish_async_task import TaskManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def process_order(order_id: int, priority: str = "normal"):
    """处理订单任务"""
    logger.info(f"开始处理订单 {order_id}, 优先级: {priority}")
    time.sleep(0.5)
    result = f"订单 {order_id} 处理完成"
    logger.info(result)
    return result


def process_payment(payment_id: int, amount: float):
    """处理支付任务"""
    logger.info(f"开始处理支付 {payment_id}, 金额: {amount}")
    time.sleep(0.3)
    return f"支付 {payment_id} 成功"


def main():
    logger.info("=== FishAsyncTask 基本使用示例 ===\n")

    # 示例1: 使用默认实例
    logger.info("【示例1】使用默认实例提交任务")
    task_manager = TaskManager()

    task_ids = []
    for i in range(3):
        task_id = task_manager.submit_task(
            process_order,
            order_id=i + 1,
            priority="high"
        )
        task_ids.append(task_id)
        logger.info(f"已提交任务，ID: {task_id}")

    # 查询任务状态
    for task_id in task_ids:
        status = task_manager.get_task_status(task_id)
        if status:
            logger.info(f"任务 {task_id}: {status['status']}")

    # 等待任务完成
    time.sleep(2)
    for task_id in task_ids:
        status = task_manager.get_task_status(task_id)
        if status and status["status"] == "completed":
            logger.info(f"任务 {task_id} 结果: {status.get('result')}")

    # 清理已完成任务的状态
    task_manager.clear_task_status()
    logger.info("已清理所有任务状态")

    # 示例2: 多实例管理
    logger.info("\n【示例2】多实例管理")

    order_manager = TaskManager(instance_key="order")
    payment_manager = TaskManager(instance_key="payment")

    order_task_id = order_manager.submit_task(process_order, 1001)
    payment_task_id = payment_manager.submit_task(process_payment, 2001, 99.9)

    logger.info(f"订单实例任务 ID: {order_task_id}")
    logger.info(f"支付实例任务 ID: {payment_task_id}")

    time.sleep(1)
    order_status = order_manager.get_task_status(order_task_id)
    payment_status = payment_manager.get_task_status(payment_task_id)

    if order_status:
        logger.info(f"订单任务状态: {order_status['status']}")
    if payment_status:
        logger.info(f"支付任务状态: {payment_status['status']}")

    # 关闭所有实例
    logger.info("\n【关闭】关闭任务管理器")
    order_manager.shutdown()
    payment_manager.shutdown()
    task_manager.shutdown()

    logger.info("\n=== 示例执行完成 ===")


if __name__ == "__main__":
    main()
