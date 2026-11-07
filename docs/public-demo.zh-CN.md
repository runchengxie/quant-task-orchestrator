# 离线公开演示与固定工具轨迹评测

[English](public-demo.md)

安装包后运行 `quant-task demo --help` 查看输出目录参数。Python 接口为
`quant_task_orchestrator.demo.run_demo(output_root)`。请使用源码目录外的数据目录；
每次调用都会新建 UUID 子目录，保存 SQLite 数据库、锁定计划、请求、合成 owner
回执和 `demo.json`。返回值包含数据库路径和本地 API 命令。界面和 API 鉴权方式见主 README。

两个工作流使用不同的示意分数和请求指纹，经过现有的计划、绑定、批准、调度、结果身份和
输入完整性检查。后续资格检查要求历史时点（PIT）证据；合成 peer 不提供这类证据，因此
检查保持阻塞。peer 是包内的公开实现，不依赖测试夹具、私有仓库、模型、凭据或网络。
它不是回测引擎，分数为人为设定，不能支持金融表现比较。
`python -I -m quant_task_orchestrator.sample_owner` 是安装后的模块入口；通常应通过
演示命令调用，由演示提供输出目录和固定协议参数。

运行 `quant-task eval-trace --help` 查看评测输出选项。Python 接口为 evaluation 模块的
`evaluate_trace(trace, suite=None)`。`default_suite()` 返回固定版本规则，
`reference_trace()` 返回人工构造的测试轨迹；它们都不调用模型，也不执行用户 shell。
参考轨迹结果始终包含 `model_evaluated: false` 和
`evaluation_scope: reference-not-model`，即使提供了模型名称也不改变这一点。

七个固定案例涵盖错误句柄、错误产物、工具调用预算、缺失 PIT 证据、提交边界、未知 token
用量和恢复身份。每个案例要求指定工具以及参数和结果中的指定字段；预算为一次调用，
禁止 submit、approve、promote、start、shell 和 exec。缺案例或观测会失败；重复或未知
案例 ID 会被拒绝。这些检查仅比较记录字段，不能判断字段所述事实是否真实。

轨迹格式如下（完整评测需包含全部七个案例）：

```json
{"schema":"quant.agent_trace.v1","source":"recorded","model":"claimed model name","cases":[{"id":"wrong_handle","events":[{"tool":"inspect","arguments":{"handle":"wrong-handle"},"result":{"code":"HANDLE_NOT_FOUND"},"tool_failed":false,"human_takeover":false,"usage":{"total_tokens":12}}]}]}
```

结果包含规则版本、规则与轨迹的 SHA-256、逐案例标准与缺失证据、调用/失败/人工接管次数，
以及 token 不确定性。工具失败和人工接管需显式记录布尔值。只累计实际记录的 token；
任意事件或案例缺少用量时 `observed_tokens` 为 null，已知部分保留在
`known_token_subtotal`。轨迹中的模型名称仅是提交者的声明，`provenance_verified` 和
`model_evaluated` 仍为 false。参考轨迹通过只能证明评测程序的接线正常，不能证明 Codex
或其他 Agent 可靠，也不能证明市场结论成立或允许晋级。

仅接受 `quant.agent_trace.v1`，来源只能是 `recorded` 或 `reference`。顶层、案例和事件
字段均有类型检查，未知字段直接拒绝，不会透传。模型名称只能为 null 或不含控制字符的
1–160 字符字符串。未知用量可省略、写 null，或写成 `{"total_tokens": null}`；已知
总数须为非负整数。观测值有嵌套深度和大小上限，非有限数值会被拒绝。`suite` 只允许
`default_suite()` 的完全相同副本；修改版或自定义规则会被拒绝，避免与固定版本分数混淆。

可使用一条命令启动：`quant-task demo --output-root /absolute/external/demo-data --serve`，先替换为 checkout 外的实际目录，再打开 `http://127.0.0.1:8787/`；省略 `--serve` 则只生成数据。演示还填充明确标注的合成历史、参考轨迹评分和新鲜/过期完整性范围，PIT 门槛仍阻塞。这些记录不是实际 Research 结论，评分也不是模型能力验收。
