"""
性能测试工具函数

提供性能测量、统计分析和报告生成工具。
"""

import statistics
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple


class PerformanceMetrics:
    """
    性能指标收集器
    
    用于收集和统计性能测试的各项指标，包括：
    - QPS（每秒操作数）
    - 延迟分布（P50, P90, P95, P99, P99.9）
    - 成功率/错误率
    - 吞吐量
    """
    
    def __init__(self, name: str):
        """
        初始化性能指标收集器
        
        Args:
            name: 测试名称
        """
        self.name = name
        self.start_time: float = 0
        self.end_time: float = 0
        self.latencies: List[float] = []
        self.success_count: int = 0
        self.error_count: int = 0
        self.errors: List[Tuple[str, Exception]] = []
    
    def start(self) -> None:
        """开始计时"""
        self.start_time = time.perf_counter()
    
    def stop(self) -> None:
        """停止计时"""
        self.end_time = time.perf_counter()
    
    def record_latency(self, latency: float) -> None:
        """
        记录单次操作延迟
        
        Args:
            latency: 延迟时间（秒）
        """
        self.latencies.append(latency)
    
    def record_success(self) -> None:
        """记录一次成功操作"""
        self.success_count += 1
    
    def record_error(self, error: Optional[Exception] = None) -> None:
        """
        记录一次错误
        
        Args:
            error: 异常信息（可选）
        """
        self.error_count += 1
        if error:
            self.errors.append((type(error).__name__, error))
    
    def record(self, success: bool, latency: float, error: Optional[Exception] = None) -> None:
        """
        记录一次操作结果
        
        Args:
            success: 是否成功
            latency: 延迟时间（秒）
            error: 异常信息（可选）
        """
        self.record_latency(latency)
        if success:
            self.record_success()
        else:
            self.record_error(error)
    
    def get_total_time(self) -> float:
        """获取总耗时"""
        return self.end_time - self.start_time
    
    def get_total_operations(self) -> int:
        """获取总操作数"""
        return len(self.latencies)
    
    def get_qps(self) -> float:
        """获取 QPS（每秒操作数）"""
        total_time = self.get_total_time()
        if total_time <= 0:
            return 0
        return self.get_total_operations() / total_time
    
    def get_avg_latency(self) -> float:
        """获取平均延迟（秒）"""
        if not self.latencies:
            return 0
        return sum(self.latencies) / len(self.latencies)
    
    def get_percentile(self, percentile: float) -> float:
        """
        获取指定百分位延迟
        
        Args:
            percentile: 百分位（0-100），例如 99 表示 P99
        
        Returns:
            延迟时间（秒）
        """
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * percentile / 100)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]
    
    def get_latency_stats(self) -> Dict[str, float]:
        """
        获取延迟统计信息
        
        Returns:
            包含各百分位延迟的字典
        """
        return {
            "avg": self.get_avg_latency(),
            "p50": self.get_percentile(50),
            "p90": self.get_percentile(90),
            "p95": self.get_percentile(95),
            "p99": self.get_percentile(99),
            "p99.9": self.get_percentile(99.9),
            "max": max(self.latencies) if self.latencies else 0,
            "min": min(self.latencies) if self.latencies else 0,
        }
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        total = self.success_count + self.error_count
        if total == 0:
            return 0
        return self.success_count / total
    
    def get_results(self) -> Dict[str, Any]:
        """
        获取完整的测试结果
        
        Returns:
            包含所有性能指标的字典
        """
        total_time = self.get_total_time()
        total_ops = self.get_total_operations()
        qps = self.get_qps()
        avg_latency = self.get_avg_latency()
        latency_stats = self.get_latency_stats()
        
        return {
            "name": self.name,
            "total_time": total_time,
            "total_operations": total_ops,
            "qps": qps,
            "avg_latency_ms": avg_latency * 1000,
            "latency_stats_ms": {
                k: v * 1000 for k, v in latency_stats.items()
            },
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": self.get_success_rate(),
            "error_rate": 1 - self.get_success_rate(),
        }
    
    def print_results(self, verbose: bool = False) -> None:
        """
        打印测试结果
        
        Args:
            verbose: 是否打印详细信息
        """
        results = self.get_results()
        
        print(f"\n{'=' * 60}")
        print(f"  {results['name']} 性能测试结果")
        print(f"{'=' * 60}")
        print(f"  总耗时:     {results['total_time']:.3f}秒")
        print(f"  总操作数:   {results['total_operations']}")
        print(f"  QPS:        {results['qps']:.0f}")
        print(f"  平均延迟:   {results['avg_latency_ms']:.3f}ms")
        print(f"  P50 延迟:   {results['latency_stats_ms']['p50']:.3f}ms")
        print(f"  P99 延迟:   {results['latency_stats_ms']['p99']:.3f}ms")
        print(f"  成功率:     {results['success_rate'] * 100:.2f}%")
        
        if verbose:
            print(f"\n  详细延迟统计:")
            print(f"    最小值: {results['latency_stats_ms']['min']:.3f}ms")
            print(f"    P90:    {results['latency_stats_ms']['p90']:.3f}ms")
            print(f"    P95:    {results['latency_stats_ms']['p95']:.3f}ms")
            print(f"    P99.9:  {results['latency_stats_ms']['p99.9']:.3f}ms")
            print(f"    最大值: {results['latency_stats_ms']['max']:.3f}ms")
            
            if results['error_count'] > 0:
                print(f"\n  错误统计:")
                error_counts: Dict[str, int] = {}
                for error_type, _ in self.errors:
                    error_counts[error_type] = error_counts.get(error_type, 0) + 1
                for error_type, count in error_counts.items():
                    print(f"    {error_type}: {count}次")
        
        print(f"{'=' * 60}\n")
    
    def reset(self) -> None:
        """重置所有指标"""
        self.start_time = 0
        self.end_time = 0
        self.latencies.clear()
        self.success_count = 0
        self.error_count = 0
        self.errors.clear()


def measure_concurrent_performance(
    func: Callable,
    args_list: List[Any],
    max_workers: int = 100,
    description: str = "并发操作"
) -> PerformanceMetrics:
    """
    测量并发操作的性能
    
    Args:
        func: 要执行的函数
        args_list: 参数列表
        max_workers: 最大并发数
        description: 测试描述
    
    Returns:
        PerformanceMetrics: 性能指标收集器
    """
    metrics = PerformanceMetrics(description)
    metrics.start()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: List[Future] = []
        for args in args_list:
            if isinstance(args, tuple):
                future = executor.submit(func, *args)
            else:
                future = executor.submit(func, args)
            futures.append(future)
        
        for future in futures:
            try:
                future.result()
                metrics.record_success()
            except Exception as e:
                metrics.record_error(e)
    
    metrics.stop()
    return metrics


def compare_results(baseline: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """
    对比两个测试结果
    
    Args:
        baseline: 基准版本结果
        current: 当前版本结果
    
    Returns:
        对比结果字典
    """
    baseline_qps = baseline.get("qps", 0)
    current_qps = current.get("qps", 0)
    
    baseline_p99 = baseline.get("latency_stats_ms", {}).get("p99", 0)
    current_p99 = current.get("latency_stats_ms", {}).get("p99", 0)
    
    qps_improvement = ((current_qps - baseline_qps) / baseline_qps * 100) if baseline_qps > 0 else 0
    latency_improvement = ((baseline_p99 - current_p99) / baseline_p99 * 100) if baseline_p99 > 0 else 0
    
    return {
        "baseline_qps": baseline_qps,
        "current_qps": current_qps,
        "qps_improvement_percent": qps_improvement,
        "baseline_p99_ms": baseline_p99,
        "current_p99_ms": current_p99,
        "latency_improvement_percent": latency_improvement,
        "overall_assessment": get_assessment(qps_improvement, latency_improvement),
    }


def get_assessment(qps_improvement: float, latency_improvement: float) -> str:
    """
    根据性能提升获取评估结果
    
    Args:
        qps_improvement: QPS 提升百分比
        latency_improvement: 延迟降低百分比
    
    Returns:
        评估描述
    """
    if qps_improvement > 50 and latency_improvement > 50:
        return "显著提升"
    elif qps_improvement > 20 and latency_improvement > 20:
        return "明显提升"
    elif qps_improvement > 0 or latency_improvement > 0:
        return "小幅提升"
    elif qps_improvement > -10 and latency_improvement > -10:
        return "基本持平"
    else:
        return "性能下降"


def print_comparison_report(
    scenario: str,
    baseline: Dict[str, Any],
    current: Dict[str, Any],
    comparison: Dict[str, Any]
) -> None:
    """
    打印性能对比报告
    
    Args:
        scenario: 测试场景名称
        baseline: 基准版本结果
        current: 当前版本结果
        comparison: 对比结果
    """
    print(f"\n{'=' * 80}")
    print(f"  场景: {scenario}")
    print(f"{'=' * 80}")
    print(f"\n{'指标':<20} {'PyPI版本':<15} {'开发版本':<15} {'提升':<15}")
    print("-" * 65)
    print(f"{'QPS':<20} {comparison['baseline_qps']:<15.0f} {comparison['current_qps']:<15.0f} {comparison['qps_improvement_percent']:+.1f}%")
    print(f"{'P99 延迟(ms)':<20} {comparison['baseline_p99_ms']:<15.3f} {comparison['current_p99_ms']:<15.3f} {comparison['latency_improvement_percent']:+.1f}%")
    print(f"{'成功率':<20} {baseline['success_rate']*100:<14.2f}% {current['success_rate']*100:<14.2f}% {'0.0%':<15}")
    print("-" * 65)
    print(f"\n  评估: {comparison['overall_assessment']}")
    print(f"{'=' * 80}\n")


class ThroughputTracker:
    """
    吞吐量跟踪器
    
    用于实时跟踪操作的吞吐量变化。
    """
    
    def __init__(self, window_size: int = 10):
        """
        初始化吞吐量跟踪器
        
        Args:
            window_size: 滑动窗口大小（记录最近 N 次操作的时间）
        """
        self.window_size = window_size
        self.timestamps: List[float] = []
        self.total_count = 0
        self.lock = threading.Lock()
    
    def record(self) -> float:
        """
        记录一次操作，返回当前瞬时吞吐量
        
        Returns:
            瞬时吞吐量（操作/秒）
        """
        with self.lock:
            now = time.perf_counter()
            self.timestamps.append(now)
            self.total_count += 1
            
            # 清理超出窗口的操作
            while self.timestamps and now - self.timestamps[0] > 1.0:
                self.timestamps.pop(0)
            
            # 计算瞬时吞吐量
            if len(self.timestamps) >= 2:
                time_span = self.timestamps[-1] - self.timestamps[0]
                if time_span > 0:
                    return len(self.timestamps) / time_span
            
            return 0
    
    def get_throughput(self) -> float:
        """获取当前吞吐量（操作/秒）"""
        with self.lock:
            if len(self.timestamps) < 2:
                return 0
            time_span = self.timestamps[-1] - self.timestamps[0]
            if time_span > 0:
                return len(self.timestamps) / time_span
            return 0
    
    def get_total_count(self) -> int:
        """获取总操作数"""
        with self.lock:
            return self.total_count

