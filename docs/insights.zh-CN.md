# 工作流对比与变更影响

[English](insights.md)

调用 `compare_workflows(store, before_id, after_id)` 查看工程差异。结果采用
`quant.workflow_comparison.v1`，以稳定的 step id 匹配步骤。每行包含 `id`、
`status`（`unchanged`、`changed`、`added` 或 `removed`）、`changed_fields`，以及
`before`/`after` 投影。步骤改名会显示为移除和新增，不猜测是否为同一步骤。

投影包括适配器类型、精确 Owner revision、Owner plan 和 request 哈希、去重的固定
输入内容哈希、所选 Skill 的 revision 和哈希、依赖、允许的预算、证据、证据上下文
及观测用量。不输出源路径、命令、提示词或原始 plan。未知或无效的负用量保留为
`null`，模型费用始终为 `null`。固定输入摘要只比较内容哈希，不暴露文件名和位置。

`economic_comparison.status` 始终为 `unavailable`：Owner 尚未导出可比较的经济
指标。工程差异、证据变化和 token 用量均不能建立经济因果关系，也不能代表投资表现。
范围上下文可以解释输入差异，但不能提供经济结果。响应会明确列出这些对比限制。仅当上下文结构完整、哈希精确、时间为 UTC，
且 ISO 样本日期有效并按先后排列时才输出上下文；无效上下文投影为空对象。

调用 `impact_preview(store, proposal)` 提交严格结构的假设变更：

```json
{
  "schema": "quant.change_proposal.v1",
  "kind": "owner_revision",
  "previous": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "next": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "target": "worker"
}
```

`kind` 只能为 `owner_revision`、`skill_revision` 或 `pinned_input`。
`previous` 和 `next` 必须不同，且为精确的小写十六进制哈希：Owner/Skill revision
为 40 位，固定输入为 64 位。可选的 `target` 在 Owner revision 或固定输入变更中
表示适配器 id，在 Skill revision 变更中表示 Skill id。省略时匹配全部引用。
未知字段或错误结构会被拒绝；格式合法但没有引用的哈希会返回空的受影响列表。

`quant.change_impact.v1` 响应逐个列出受影响 workflow 的 `direct_steps`、传递依赖的
`downstream_steps`、`required_new_plan: true` 和 `approval_review: true`。
循环或缺失依赖会使预览失败。预览不会修改审批或 plan，也不会执行或重跑步骤；
它不验证新 revision 是否存在或兼容。

扫描会分页遍历**全部已存储 workflow**，包括已完成的工作流，不限于前 100 个。
`scan` 报告范围、数量、截断与一致性。扫描使用同一个 SQLite 读取快照（`sqlite_read_snapshot`），并发提交不会造成
分页偏移，也不会使源工作流重复或遗漏。嵌套 savepoint 会保留调用方已有事务，
预览不会提交该事务。合成数据测试不依赖生产数据库或 Owner 进程。

独立的[金融结果声明比较](economic-results.zh-CN.md)接受显式锁定的结果文件；它不改变工作流比较接口，也不会推断负责系统尚未导出的字段。
