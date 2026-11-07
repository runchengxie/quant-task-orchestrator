# 证据适用性

[English](evidence-applicability.md)

已记录的 `verified` 不代表通用许可。新步骤可在 `requires_evidence` 旁增加 `evidence_context`，要求六个字段：`data_sha256`、`strategy_sha256`、`universe_sha256`、`as_of`、`sample_start`、`sample_end`。前三项为 64 位十六进制摘要，市场时点为 UTC 时间，样本日期为 ISO 格式。

Owner 检查在原有 `status`、`source`、`evidence_sha256` 之外，提供包含同样六字段的 `scope`，以及 UTC `assessed_at`、`valid_until`。范围复用要求完整字段和证据身份。只投影摘要，不展示私有路径或研究范围中的证券名单。

资料、策略、研究范围指纹和市场 `as_of` 必须匹配，Owner 样本区间须覆盖请求。审查有效期满足 `assessed_at <= 当前时间 < valid_until`。审查时间与市场历史时点分开：事后可以核验早期时点的证据，但协调器不会据此推断历史可用性，必须由对应 Owner 实际验证。

范围证明的来源须与导出适配器的 Owner 一致，Runtime 不能通过填写来源字符串冒充 Research。PIT 由数据/Research 声明，执行语义由 Runtime/Research 声明，独立审查和经济结论归 Research。晋升始终保持未知。代理其他 Owner 的证明需要额外校验的契约，不能只靠来源名称。

视图保留原始 Owner 状态，增加 `applicability.code` 与 `usable`，只保留类型正确的范围和时间。明确提供但损坏的检查会拒绝使用，不回退到 Runtime 的通用完整性成功。有效期每次读取重新计算，不信任缓存中的适用性结果。

新任务分发前核对范围和有效期，缺字段、指纹不符、样本不足、过期或未来审查均阻塞。已完成步骤不被重写，独立运行任务不因证据过期被取消。要解除分发前阻塞，应提交新证据和经审查的新计划。

未声明上下文的旧工作流保持兼容。`LEGACY_UNSCOPED` 只说明没有范围认证，不保证新鲜度；旧检查若主动声明有效期，损坏或过期仍会阻止复用。需要保证的新研究必须显式请求范围，原有 Owner 协议不会被自动补造范围元数据。

离线演示提供明确标注的合成新鲜/过期检查，只展示功能，不证明 PIT 或金融研究有效。
