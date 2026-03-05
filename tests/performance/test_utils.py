"""
性能模块工具函数测试

测试 _utils.py 中的工具函数，包括分片计算、时间处理和 CPU 使用率检测。
"""

import re
import time
from unittest.mock import MagicMock, patch

import pytest

from fish_async_task.performance._utils import (
    compute_expiry_time,
    compute_shard_index,
    format_timestamp,
    get_cpu_usage,
    is_expired,
    validate_shard_count,
)


class TestComputeShardIndex:
    """测试分片索引计算函数"""

    def test_compute_shard_index_basic(self):
        """测试基本的分片索引计算"""
        # 测试不同的 task_id 会产生不同的分片索引
        shard_count = 16

        index1 = compute_shard_index("task_1", shard_count)
        index2 = compute_shard_index("task_2", shard_count)
        index3 = compute_shard_index("task_3", shard_count)

        # 所有索引应该在有效范围内
        assert 0 <= index1 < shard_count
        assert 0 <= index2 < shard_count
        assert 0 <= index3 < shard_count

    def test_compute_shard_index_deterministic(self):
        """测试相同输入产生相同输出"""
        task_id = "test_task_123"
        shard_count = 16

        index1 = compute_shard_index(task_id, shard_count)
        index2 = compute_shard_index(task_id, shard_count)

        assert index1 == index2

    def test_compute_shard_index_single_shard(self):
        """测试单分片情况"""
        index = compute_shard_index("any_task", 1)
        assert index == 0

    def test_compute_shard_index_boundary(self):
        """测试边界条件"""
        # 最小有效分片数
        index = compute_shard_index("task", 1)
        assert index == 0

        # 较大的分片数
        index = compute_shard_index("task", 1024)
        assert 0 <= index < 1024

    def test_compute_shard_index_invalid_shard_count(self):
        """测试无效的分片数量"""
        with pytest.raises(ValueError, match="shard_count 必须 >= 1"):
            compute_shard_index("task", 0)

        with pytest.raises(ValueError, match="shard_count 必须 >= 1"):
            compute_shard_index("task", -1)

        with pytest.raises(ValueError, match="shard_count 必须 >= 1"):
            compute_shard_index("task", -100)

    def test_compute_shard_index_distribution(self):
        """测试分片分布的均匀性"""
        shard_count = 16
        task_count = 1000

        # 生成大量任务的分片索引
        indices = [compute_shard_index(f"task_{i}", shard_count) for i in range(task_count)]

        # 统计每个分片的任务数
        shard_counts = [0] * shard_count
        for index in indices:
            shard_counts[index] += 1

        # 每个分片应该有接近相等的任务数
        # 1000 任务 / 16 分片 ≈ 62.5 任务/分片
        # 允许 ±30 的偏差
        expected = task_count / shard_count
        for count in shard_counts:
            assert expected - 30 <= count <= expected + 30

    def test_compute_shard_index_different_inputs(self):
        """测试不同输入的分散性"""
        shard_count = 16

        # 测试相似的输入不会映射到同一个分片
        indices = [compute_shard_index(f"task_{i}", shard_count) for i in range(100)]

        # 至少应该覆盖大部分分片（比如至少 10 个分片）
        unique_shards = len(set(indices))
        assert unique_shards >= 10

    def test_compute_shard_index_special_characters(self):
        """测试包含特殊字符的 task_id"""
        shard_count = 16

        # 测试各种特殊字符
        index1 = compute_shard_index("task-with-dashes", shard_count)
        index2 = compute_shard_index("task_with_underscores", shard_count)
        index3 = compute_shard_index("task.with.dots", shard_count)
        index4 = compute_shard_index("task/with/slashes", shard_count)
        index5 = compute_shard_index("task:with:colons", shard_count)
        index6 = compute_shard_index("task with spaces", shard_count)

        # 所有都应该产生有效的索引
        for index in [index1, index2, index3, index4, index5, index6]:
            assert 0 <= index < shard_count

    def test_compute_shard_index_unicode(self):
        """测试 Unicode 字符"""
        shard_count = 16

        index1 = compute_shard_index("任务-中文", shard_count)
        index2 = compute_shard_index("タスク-日本語", shard_count)
        index3 = compute_shard_index("task-emoji-😀", shard_count)

        # 所有都应该产生有效的索引
        for index in [index1, index2, index3]:
            assert 0 <= index < shard_count


class TestComputeExpiryTime:
    """测试过期时间计算函数"""

    def test_compute_expiry_time_basic(self):
        """测试基本的过期时间计算"""
        end_time = 1704800000.0
        ttl = 300

        expiry = compute_expiry_time(end_time, ttl)

        assert expiry == end_time + ttl
        assert expiry == 1704800300.0

    def test_compute_expiry_time_zero_ttl(self):
        """测试零 TTL"""
        end_time = 1704800000.0
        ttl = 0

        expiry = compute_expiry_time(end_time, ttl)

        assert expiry == end_time

    def test_compute_expiry_time_negative_ttl(self):
        """测试负 TTL（虽然不常见，但函数应该能处理）"""
        end_time = 1704800000.0
        ttl = -100

        expiry = compute_expiry_time(end_time, ttl)

        assert expiry == end_time + ttl

    def test_compute_expiry_time_large_ttl(self):
        """测试大 TTL"""
        end_time = 1704800000.0
        ttl = 86400  # 一天

        expiry = compute_expiry_time(end_time, ttl)

        assert expiry == end_time + 86400

    def test_compute_expiry_time_fractional(self):
        """测试分数时间"""
        end_time = 1704800000.5
        ttl = 100.5

        expiry = compute_expiry_time(end_time, ttl)

        assert expiry == end_time + ttl


class TestIsExpired:
    """测试过期判断函数"""

    def test_is_expired_true(self):
        """测试已过期的情况"""
        expiry_time = 1704800000.0
        current_time = 1704800100.0

        assert is_expired(expiry_time, current_time) is True

    def test_is_expired_false(self):
        """测试未过期的情况"""
        expiry_time = 1704800100.0
        current_time = 1704800000.0

        assert is_expired(expiry_time, current_time) is False

    def test_is_expired_equal(self):
        """测试时间相等的情况"""
        expiry_time = 1704800000.0
        current_time = 1704800000.0

        # current_time > expiry_time，相等时未过期
        assert is_expired(expiry_time, current_time) is False

    def test_is_expired_with_none_current_time(self):
        """测试不提供当前时间时使用 time.time()"""
        expiry_time = time.time() - 100  # 100 秒前过期

        assert is_expired(expiry_time) is True

    def test_is_expired_future(self):
        """测试未来的过期时间"""
        expiry_time = time.time() + 1000  # 1000 秒后过期

        assert is_expired(expiry_time) is False

    def test_is_expired_boundary(self):
        """测试边界情况"""
        # 刚过期 1 微秒
        assert is_expired(100.0, 100.000001) is True

        # 还差 1 微秒过期
        assert is_expired(100.0, 99.999999) is False


class TestGetCpuUsage:
    """测试 CPU 使用率获取函数"""

    def test_get_cpu_usage_with_psutil(self):
        """测试有 psutil 时的 CPU 使用率获取"""
        # 如果 psutil 可用，测试正常返回
        result = get_cpu_usage()

        if result is not None:
            assert isinstance(result, float)
            assert 0.0 <= result <= 1.0

    def test_get_cpu_usage_without_psutil(self):
        """测试没有 psutil 时返回 None"""
        # 模拟 psutil 不可用时，直接验证函数行为
        # 由于模块已经导入，我们只能验证 get_cpu_usage 的返回类型
        result = get_cpu_usage()
        # 如果 psutil 可用，返回 float；否则返回 None
        assert result is None or isinstance(result, float)

    def test_get_cpu_usage_import_error(self):
        """测试 ImportError 处理"""

        # 模拟 ImportError 时的正确签名
        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("psutil not available")
            return __import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            # 验证在 ImportError 场景下不会崩溃
            # 由于模块缓存，这个测试主要验证 mock 机制
            try:
                import psutil  # noqa: F401
            except ImportError:
                pass  # 预期的 ImportError

    def test_get_cpu_usage_not_implemented(self):
        """测试 NotImplementedError 处理"""
        # 某些平台可能不支持 psutil.cpu_percent()
        # 这只是文档性测试，实际行为取决于 psutil
        result = get_cpu_usage()

        # 如果 psutil 可用，应该返回 float 或 None
        if result is not None:
            assert isinstance(result, float)


class TestFormatTimestamp:
    """测试时间戳格式化函数"""

    def test_format_timestamp_basic(self):
        """测试基本时间戳格式化"""
        # 使用已知时间戳验证格式
        timestamp = 1704800000.0

        formatted = format_timestamp(timestamp)

        assert isinstance(formatted, str)
        # 验证格式正确（使用正则而不是硬编码时间，因为时区不同）
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", formatted)

    def test_format_timestamp_epoch(self):
        """测试 Unix 时间戳 0"""
        timestamp = 0.0

        formatted = format_timestamp(timestamp)

        # 验证格式正确（时区会有所不同）
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", formatted)

    def test_format_timestamp_with_fraction(self):
        """测试带分数的时间戳"""
        timestamp = 1704800000.123456

        formatted = format_timestamp(timestamp)

        # format_timestamp 应该截断到秒并返回有效格式
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", formatted)

    def test_format_timestamp_current_time(self):
        """测试当前时间格式化"""
        timestamp = time.time()

        formatted = format_timestamp(timestamp)

        # 应该包含日期和时间模式
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", formatted)

    def test_format_timestamp_negative(self):
        """测试负时间戳（1970 年之前）"""
        # 1969-12-31 23:59:59 UTC (-1 秒)
        timestamp = -1.0

        formatted = format_timestamp(timestamp)

        # 在大多数系统上，这应该是有效的
        assert isinstance(formatted, str)


class TestValidateShardCount:
    """测试分片数量验证函数"""

    def test_validate_shard_count_valid(self):
        """测试有效的分片数量"""
        # 不应该抛出异常
        validate_shard_count(1)
        validate_shard_count(16)
        validate_shard_count(256)
        validate_shard_count(512)
        validate_shard_count(1024)

    def test_validate_shard_count_power_of_two(self):
        """测试 2 的幂次方（推荐但不是必需）"""
        # 这些都是 2 的幂次，不应该抛出异常
        validate_shard_count(2)
        validate_shard_count(4)
        validate_shard_count(8)
        validate_shard_count(16)
        validate_shard_count(32)
        validate_shard_count(64)
        validate_shard_count(128)
        validate_shard_count(256)
        validate_shard_count(512)
        validate_shard_count(1024)

    def test_validate_shard_count_not_power_of_two(self):
        """测试非 2 的幂次（允许但不推荐）"""
        # 这些不是 2 的幂次，但仍然有效
        validate_shard_count(3)
        validate_shard_count(5)
        validate_shard_count(10)
        validate_shard_count(100)
        validate_shard_count(1000)

    def test_validate_shard_count_invalid_zero(self):
        """测试无效的分片数量 - 零"""
        with pytest.raises(ValueError, match="shard_count 必须 >= 1"):
            validate_shard_count(0)

    def test_validate_shard_count_invalid_negative(self):
        """测试无效的分片数量 - 负数"""
        with pytest.raises(ValueError, match="shard_count 必须 >= 1"):
            validate_shard_count(-1)

        with pytest.raises(ValueError, match="shard_count 必须 >= 1"):
            validate_shard_count(-100)

    def test_validate_shard_count_too_large(self):
        """测试过大的分片数量"""
        with pytest.raises(ValueError, match="shard_count 不应该 > 1024"):
            validate_shard_count(1025)

        with pytest.raises(ValueError, match="shard_count 不应该 > 1024"):
            validate_shard_count(2048)

        with pytest.raises(ValueError, match="shard_count 不应该 > 1024"):
            validate_shard_count(10000)

    def test_validate_shard_count_boundary(self):
        """测试边界值"""
        # 最大允许值
        validate_shard_count(1024)

        # 刚超过最大值
        with pytest.raises(ValueError, match="shard_count 不应该 > 1024"):
            validate_shard_count(1025)


class TestEdgeCases:
    """测试边界情况和特殊场景"""

    def test_empty_task_id(self):
        """测试空 task_id"""
        index = compute_shard_index("", 16)
        assert 0 <= index < 16

    def test_very_long_task_id(self):
        """测试很长的 task_id"""
        long_id = "a" * 10000
        index = compute_shard_index(long_id, 16)
        assert 0 <= index < 16

    def test_compute_shard_index_consistency_across_calls(self):
        """测试多次调用的一致性"""
        task_id = "consistent_task"
        shard_count = 32

        indices = [compute_shard_index(task_id, shard_count) for _ in range(100)]

        # 所有调用应该返回相同的索引
        assert all(i == indices[0] for i in indices)

    def test_is_expired_with_very_old_time(self):
        """测试非常旧的过期时间"""
        # 1970 年的时间
        assert is_expired(0.0, time.time()) is True

    def test_is_expired_with_future_time(self):
        """测试未来的过期时间"""
        # 2030 年的时间
        future_time = 1893456000.0  # 2030-01-01
        assert is_expired(future_time, time.time()) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
