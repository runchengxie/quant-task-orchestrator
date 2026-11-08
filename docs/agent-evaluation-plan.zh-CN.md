# 准备真实 agent 评估

[English](agent-evaluation-plan.md)

`quant_task_orchestrator.agent_eval_plan.build_agent_evaluation_plan()` 返回有版本号、
可序列化为 JSON 的只读计划。不需要模型名称，也不会调用模型、shell、owner 或文件系统。
计划保持 `not_run`、`model_evaluated: false`，结果未知，分数和轨迹为空。
生成计划不构成 Codex 可靠性证据，也不会续增此前的调用预算。真实评估须另行明确授权调用预算。
保守建议上限为两次模型调用、一个原始会话、五分钟，到达任一上限立即停止。

七个场景复用既有版本化 harness 用例：错误 handle、错误 artifact、调用次数上限、
缺少 PIT 证据、提交权限边界、未知用量、恢复原始会话。实际回答应解释已观察的工具结果，
引用真实获准使用的证据，并在缺少证据或权限时明确停止。不得编造轨迹，也不能把空运行判为通过。
`evaluation.py` 只检查记录下来的协议轨迹，不能判断 agent 是否理解研究证据。

独立人工或 reviewer 必须按计划中的 rubric 审核真实回答。记录准确的证据 handle、
profile 和内容哈希、命令文件 pin、证据缺项、应当拒绝的操作、原始会话身份，以及实际可测用量。
缺少 token 或费用遥测时保持未知。快照响应须符合 `research.tool-response/v1`，
handle、profile 哈希、资源种类、内容哈希均一致，且 `snapshot: true`。
字节校验只能说明输入完整性；历史 PIT、时效性、经济有效性仍需分别提供证据。
所有必要条件均有真实回答和独立审核后，才可能整体通过。

## 安全地继续观察数据

既有冻结原始数据监测提案仅检查内容完整性，仅保留本地记录，状态为
`installed: false`、`enabled: false`。它不能证明每日入库及时。
后续应核对保留的观察结果与冻结 cohort/config pin；pin 改变或缺失应保留失败状态，
不能悄悄换成新发布的数据。启用 timer 是另外一项操作。

数据 owner 已有 `scripts/operations/data_status.py --root "$DATA_PLATFORM_ROOT"
--expected-date YYYYMMDD` 只读时效概览。必须明确给出预期交易日；它不推断日历目标，
不请求供应商、不修复服务、不写 receipt。需要留存时，将 stdout 保存到新的任务数据目录。
只有需要查询服务时才添加 `--with-systemd`；它最多查询五个已知服务，每个超时五秒。
必须读取 `needs_attention` 和各组件状态：退出码零仅代表概览生成成功，不是数据验收通过。
历史证据默认六小时窗口；缺失、格式错误、未来时间或无时区的证据不能证明 readiness。
补充证据始终标为未验证。记录观察时间、预期日期、源代码版本、receipt 哈希和缺项，
与冻结完整性结果分开保存。本计划不会执行此检查或采集数据。

`marketdata contract capture` 只固定发布元数据身份，不验证 Parquet 字节或时效性；
receipt 明示 `data_content_verified: false`、`atomic_transaction: false`。
执行输入审计会写研究切片和 `readiness.json`，不是只读概览；重建 PIT 也不等于历史修订版本安全。
既有私有适配配置包含原始数据观察和研究 readiness handle，但这些名称本身不能证明时效阈值或研究资格。

Owner 说明：[数据概览](https://github.com/runchengxie/quant-market-data-platform/blob/main/docs/operations/data-status.en.md)、
[元数据快照](https://github.com/runchengxie/quant-market-data-platform/blob/main/docs/operations/published-asset-snapshot.en.md)、
[执行输入 readiness](https://github.com/runchengxie/quant-market-data-platform/blob/main/docs/operations/execution-input-readiness.en.md)。
