# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-12-25

### Added

- 支持任务状态分片存储，优化高并发场景下的性能
- 新增 `TASK_STATUS_SHARD_COUNT` 环境变量配置
- 新增批量状态更新机制，减少锁竞争

### Changed

- 优化任务状态管理器的性能
- 改进自适应线程管理的响应速度

### Fixed

- 修复线程退出时的竞态条件问题
- 修复关闭时的资源清理问题

## [0.1.0] - 2025-12-19

### Added

- 初始版本发布
- 支持基本的任务提交和状态查询
- 支持动态线程池和自动伸缩
- 支持任务状态自动清理
- 支持单例模式和多实例管理
- 支持任务超时配置
- 支持阻塞和非阻塞两种提交模式

[0.2.0]: https://github.com/fishzjp/FishAsyncTask/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/fishzjp/FishAsyncTask/releases/tag/v0.1.0

