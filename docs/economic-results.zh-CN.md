# 金融结果比较

[English](economic-results.md)

`compare-results` 只接受显式的 `quant.economic_result.v1` 结果文件和准确的文件 SHA-256。随附例子全部是**模拟数据**；私有 Research 生产者尚未导出这个新契约。现有工作流比较仍然只比较工程信息，不会自动读取这些文件或声称投资表现有效。

```sh
quant-task compare-results \
  --before examples/economic-results/before.json --before-sha256 BEFORE_FILE_SHA256 \
  --after examples/economic-results/after.json --after-sha256 AFTER_FILE_SHA256
```

将两个 pin 替换为对应文件字节的 SHA-256。命令不需要数据库、负责系统进程、模型、网络或执行权限。每个普通文件最多 1 MiB；符号链接路径、重复 JSON 键、多余字段和非有限指标都会被拒绝。读取、校验和解析使用同一份字节。Python 接口为 `economic_results.load_result(path, expected_sha256)` 和 `compare_results(before, after)`。

## 结果声明

顶层字段严格限定为 `schema`、`owner`（`quant-research`）、`source_revision`（40 位小写十六进制）、`result_id` 与 `report_sha256`（64 位）、`evidence_class`（`synthetic/historical_mechanism/research`）、`execution_status`（`succeeded/failed/unknown`）、`admission_status`（`blocked/not_assessed/owner_declared`）、`basis` 和 `metrics`。不透明标识和摘要代替私有路径、标的、策略参数及原始报告。

`basis` 必须包含以下全部字段，未知值保留为 `null`：

- `data_sha256/universe_sha256/benchmark_sha256`：数据、可选标的范围和基准定义。
- `cost_model_sha256/execution_semantics_sha256`：成本、估值和执行口径。
- `metric_definitions_sha256`：指标算法、年化方法和单位。
- `sample_start/sample_end`：有序 ISO 日期。
- `time_zone/currency/return_frequency`：IANA 时区、三个大写字母的货币代码及 `daily/weekly/monthly`。
- `history_visibility`：`seen/holdout/prospective`，仅为负责系统声明，未经独立核实。

只有全部口径已知且完全一致、两边执行成功、证据类别一致、至少一对指标已知时，才可以计算差值。两边都缺失同一个字段仍然不可比较。假设摘要须覆盖非研究处理因素，包括初始资金、复权、交易日历、费用、税费、冲击、流动性和剩余持仓估值。摘要相同不能证明定义完整，生产者和独立审查者仍须负责。

`metrics` 严格包含 `total_return/annualized_return/max_drawdown/annualized_volatility/sharpe/turnover`。有限数值绝对值不超过 1e12，未知值为 `null`。收益使用比率，0.02 表示 2%，不得低于 -1；回撤使用 0 到 1 的正损失比例；波动率和换手率非负；Sharpe 可以为负。缺失值不补零。差值为后者减前者，回撤差值为正表示损失更大；收益差值 0.02 表示两个百分点，并不是相对收益或几何超额收益。

## 权威边界和后续工作

输出为 `quant.economic_comparison.v1`。口径缺失或不一致时返回 `not_comparable` 和原因，不输出指标差值。可比较只代表声明下的算术可比，`provenance_verified/research_validated/promotion_authorized/causal_attribution` 始终为假。

`owner` 和准入字段是声明，任何人都可以写出相同字符串。文件 pin 证明字节一致，不证明实际生产者或结论真实。`report_sha256` 是声明的报告引用，命令不会读取该报告做验证。任何输入都不能授予研究或执行权限。

下一步由 Research 显式导出标的范围、基准、假设和指标定义摘要及负责系统验证回执。已有研究内部的配对计算不能直接替代跨研究契约。真实历史机制研究即使通过产物哈希和配对算术核对，也可能继续被正式准入阻塞。
