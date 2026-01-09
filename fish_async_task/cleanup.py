"""
清理线程模块

负责定期清理过期的任务状态记录。
"""

import logging
import threading
import time
from typing import Callable, Optional


class CleanupThreadManager:
    """清理线程管理器"""

    # 配置常量
    MAX_CONSECUTIVE_ERRORS = 10  # 最大连续错误次数
    MIN_CHECK_INTERVAL = 1.0  # 最小检查间隔（秒）
    CLEANUP_INTERVAL_DIVISOR = 10  # 清理间隔除数，用于计算检查间隔

    def __init__(
        self,
        logger: logging.Logger,
        running_event: threading.Event,
        cleanup_interval: int,
        cleanup_func: Callable[[], int],
    ):
        """
        初始化清理线程管理器

        Args:
            logger: 日志记录器
            running_event: 运行事件
            cleanup_interval: 清理间隔（秒）
            cleanup_func: 清理函数
        """
        self.logger = logger
        self._running_event = running_event
        self.cleanup_interval = cleanup_interval
        self._cleanup_func = cleanup_func
        self.cleanup_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动清理线程"""
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="TaskStatusCleanup",
            daemon=True,
        )
        self.cleanup_thread.start()
        self.logger.debug("任务状态清理线程已启动")

    def _wait_with_interrupt_check(self, check_interval: float) -> bool:
        """
        等待清理间隔，期间定期检查运行事件状态

        这样可以及时响应shutdown信号，而不需要等待整个清理间隔。

        Args:
            check_interval: 检查间隔（秒）

        Returns:
            bool: 如果应该继续运行则返回True，如果应该退出则返回False
        """
        waited = 0.0
        while waited < self.cleanup_interval and self._running_event.is_set():
            sleep_chunk = min(check_interval, self.cleanup_interval - waited)
            time.sleep(sleep_chunk)
            waited += sleep_chunk

        # 如果事件被清除（shutdown），返回False表示应该退出
        return self._running_event.is_set()

    def _cleanup_loop(self) -> None:
        """
        清理线程主循环

        使用可中断的等待机制，定期执行清理操作。
        等待期间会定期检查运行事件状态，以便及时响应shutdown信号。
        """
        thread_name = threading.current_thread().name
        self.logger.debug(f"清理线程启动: {thread_name}")
        consecutive_errors = 0

        # 检查间隔：最多每秒检查一次运行状态，确保能及时响应shutdown
        check_interval = min(
            self.MIN_CHECK_INTERVAL, self.cleanup_interval / self.CLEANUP_INTERVAL_DIVISOR
        )

        while self._running_event.is_set():
            try:
                # 分段等待，每次等待一小段时间后检查事件状态
                if not self._wait_with_interrupt_check(check_interval):
                    break

                # 执行清理操作
                self._cleanup_func()
                consecutive_errors = 0  # 重置错误计数

            except KeyboardInterrupt:
                # 键盘中断，正常退出
                self.logger.info(f"清理线程收到中断信号: {thread_name}")
                break
            except SystemExit:
                # 系统退出，重新抛出，不捕获
                raise
            except (IOError, OSError, ConnectionError) as e:
                # I/O 相关异常，可能是临时性问题
                consecutive_errors += 1
                self.logger.warning(f"清理线程遇到 I/O 异常 [{type(e).__name__}]: {e}")
            except (AttributeError, TypeError, ValueError) as e:
                # 编程错误，记录严重错误
                consecutive_errors += 1
                self.logger.critical(
                    f"清理线程遇到编程错误 [{type(e).__name__}]: {e}，建议修复代码", exc_info=True
                )
            except Exception as e:
                # 其他未预期的异常
                consecutive_errors += 1
                error_type = type(e).__name__
                self.logger.error(
                    f"任务状态清理线程异常 [{error_type}] "
                    f"[{consecutive_errors}/{self.MAX_CONSECUTIVE_ERRORS}]: {e}",
                    exc_info=True,
                )

                # 如果连续错误过多，记录严重警告但继续运行
                # 重置计数避免日志刷屏，但保持线程运行以尝试恢复
                if consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                    self.logger.critical(
                        f"清理线程连续错误过多（{self.MAX_CONSECUTIVE_ERRORS}次），"
                        f"但继续运行以尝试恢复: {thread_name}"
                    )
                    consecutive_errors = 0  # 重置计数，避免日志刷屏

        self.logger.debug(f"清理线程退出: {thread_name}")

    def join(self, timeout: float) -> None:
        """
        等待清理线程退出

        Args:
            timeout: 超时时间（秒）
        """
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=timeout)
            if self.cleanup_thread.is_alive():
                self.logger.warning("清理线程在超时后仍未退出")
