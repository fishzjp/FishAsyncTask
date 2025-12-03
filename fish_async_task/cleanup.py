"""
清理线程模块

负责定期清理过期的任务状态记录。
"""

import threading
import time
import logging
from typing import Callable, Optional


class CleanupThreadManager:
    """清理线程管理器"""
    
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
    
    def _cleanup_loop(self) -> None:
        """
        清理线程主循环
        
        使用可中断的等待机制，定期执行清理操作。
        等待期间会定期检查运行事件状态，以便及时响应shutdown信号。
        """
        thread_name = threading.current_thread().name
        self.logger.debug(f"清理线程启动: {thread_name}")
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        # 检查间隔：最多每秒检查一次运行状态，确保能及时响应shutdown
        check_interval = min(1.0, self.cleanup_interval / 10)
        
        while self._running_event.is_set():
            try:
                # 分段等待，每次等待一小段时间后检查事件状态
                # 这样可以及时响应shutdown信号，而不需要等待整个清理间隔
                waited = 0.0
                while waited < self.cleanup_interval and self._running_event.is_set():
                    sleep_chunk = min(check_interval, self.cleanup_interval - waited)
                    time.sleep(sleep_chunk)
                    waited += sleep_chunk
                
                # 如果事件被清除（shutdown），退出循环
                if not self._running_event.is_set():
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
            except Exception as e:
                # 清理操作异常，记录错误但继续运行
                # 这确保了清理失败不会导致整个任务管理器崩溃
                consecutive_errors += 1
                error_type = type(e).__name__
                self.logger.error(
                    f"任务状态清理线程异常 [{error_type}] "
                    f"[{consecutive_errors}/{max_consecutive_errors}]: {e}",
                    exc_info=True,
                )
                
                # 如果连续错误过多，记录严重警告但继续运行
                # 重置计数避免日志刷屏，但保持线程运行以尝试恢复
                if consecutive_errors >= max_consecutive_errors:
                    self.logger.critical(
                        f"清理线程连续错误过多（{max_consecutive_errors}次），"
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

