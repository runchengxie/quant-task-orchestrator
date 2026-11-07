# 研究历史快照

[English](history.md)

历史检索是显式导入的 Research 记录视图，不是第二套注册库。Owner 导出器在只读事务中读取指定 SQLite 来源，摘要包含已提交 WAL；只选白名单列，限制来源大小、记录及产物数量，范围内身份冲突直接拒绝。其他记录新增时，已有记录标识不变。

`quant.research_history.v1` 包含稳定来源标识、导出版本、不透明记录标识、原机器状态/决策、分类、证据阶段和溯源摘要，不导出原始假设、结论正文、错误日志、来源路径或规格。主题、原因码和重试条件由 Owner 显式整理；缺少整理表示未知。工况失败与研究结论分开，`DISCARDED` 本身不能证明经济无效，`owner_recorded` 也不代表消费者验证过证据。

```sh
quant-task --database "$TASK_DATABASE" history-import --file "$OWNER_EXPORT" --sha256 "$EXPORT_SHA256"
quant-task --database "$TASK_DATABASE" history --classification operational_failure
quant-task --database "$TASK_DATABASE" history --q pit --limit 50 --offset 0
```

导入校验精确字节、严格 JSON、结构和摘要，重复导入幂等；消费者不打开权威来源数据库。默认检索最近一次明确导入的快照，不是机器上的全部注册库。分页使用 `--snapshot-sha256` 固定版本。API 同样支持快照固定及来源类型、状态、阶段、决策、分类、证据阶段和注解 token 的精确过滤。文本检索只覆盖已导出字段，不检索原始私有假设正文。

认证只读 GUI 提供查询、分类和下一页控件。没有结果不等于以前没人研究过：来源集合、注解覆盖和快照新鲜度都限制检索。Owner 有新记录后须重新明确导出和导入，快照仍然只是缓存。
