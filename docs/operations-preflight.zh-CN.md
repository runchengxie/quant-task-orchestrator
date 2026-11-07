# 运维预检

[English](operations-preflight.md)

这些 Python 接口只处理离线文件或本地端点，不安装服务、不改调度、不删除保留数据，也不向他人发送消息。

`ops.restore_database(source, destination, sha256)` 先核验调用方固定的备份摘要、SQLite 完整性及工作流数据库必需字段，再原子发布新文件。输入应为 `deployment.backup_database` 已完成的备份，不应直接使用带 WAL 附属文件的运行中数据库。目标必须不存在，恢复不会覆盖现有数据库。备份和独立记录的摘要应保存在项目数据目录。恢复演练与生产启用是两个独立操作。

`ops.dispatch_notification(ledger, notification_id, peer=None, dry_run=True)` 默认只预览。显式发送要求注入本地端点，提供 `local_only = True`、`lookup(notification_id)`、`send(notification_id, body)`。两方法返回的回执必须包含匹配的 `notification_id` 和非空 `receipt_id`；仅查询方法可以返回 `None`。端点必须按通知 ID 去重。发送回执与原 outbox 的用户确认分别记录。

日志在联系端点前提交 `uncertain`。响应丢失或进程崩溃后，后续调用只查询相同通知 ID，绝不自动重发。不确定状态查不到回执时，保留状态交由运维核实。该设计以停止自动重试为代价避免重复发送；本模块不提供网络传输。

`ops.scheduler_migration_plan(old_owner, new_owner, old_active=..., new_active=...)` 根据显式传入的归属观察生成建议步骤。`ready` 仅表示旧归属仍启用、新归属未启用，不代表生产安全或观察证据仍然新鲜。双方同时启用会阻塞。`cutover_executed` 始终为 false。迁移前仍须重新核对实际调度、影子运行结果和回滚条件，并单独授权；此函数本身无法切换调度。
