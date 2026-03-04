//! 工具函数模块

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

/// 计算字符串的哈希值
pub fn hash_string(s: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    s.hash(&mut hasher);
    hasher.finish()
}

/// 计算分片索引
pub fn get_shard_index(key: &str, shard_count: usize) -> usize {
    (hash_string(key) as usize) % shard_count
}
