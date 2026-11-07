# quant-task-orchestrator

[English](README.md) · [交互演示](https://runchengxie.github.io/quant-task-orchestrator/)

跨仓库协调投研工作流，通过 CLI、终端界面和本地 JSON API 查看依赖、批准、任务分配、恢复状态与证据。

协调器负责工作流；**Runtime 负责执行，Research 负责研究准入、证据和晋升**。回测成功不代表策略获准晋升。

## 当前范围

- SQLite 持久化工作流、DAG 依赖、绑定计划摘要的批准和事件记录。
- Runtime CLI 适配：绑定计划后提交、按原幂等键恢复、校验结果、取消任务。
- Research CLI 适配：协调**已获批准的既有 Campaign 提案**。本版本不创建模型会话、不发起新提案、不生成研究结论。
- 跨仓 Skill 目录：固定 Git commit 与内容摘要，旧任务保留原版本。
- 共用证据与恢复视图的本地实时只读 GUI、TUI 与回环地址 JSON API。
- 数据/报告 Owner 校验、历史原生会话检查与固定范围的发布事件触发。
- 显式证据门槛，以及工作流耗时、Owner 调用与操作者动作统计。
- GitHub Pages 响应式中英文演示，全部使用虚构数据，按钮只模拟状态变化。

适用于 Linux、Python 3.12 以上，无运行时第三方依赖。初版为单机、单协调器架构，各领域 Owner 保持独立可运行；本次不修改生产定时任务。

## 开始使用

```sh
python -m pip install .
quant-task --help
quant-task --database "$TASK_DATABASE" tui --once
quant-task --database "$TASK_DATABASE" serve-api --port 8787
```

读取操作要求 `TASK_DATABASE` 已存在。创建合成验证环境见[安装与快速开始](docs/setup.md)。

- [实时工作台](docs/live-workbench.md)与 [Owner 适配器](docs/owner-adapters.md)
- [本轮验收与限制](docs/workbench-validation.md)
- [架构与职责边界](docs/architecture.md)
- [工作流、API 与 Skill 契约](docs/contracts.md)
- [运行、取消与恢复](docs/operations.md)
- [验证记录与限制](docs/validation.md)

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

真实 Runtime 验收为显式启用；普通测试使用合成 CLI 与隔离的临时数据库。[MIT 许可证](LICENSE)。代码独立实现，QuantStudio 与 DeepSeek Super-agent 仅作架构参考。
