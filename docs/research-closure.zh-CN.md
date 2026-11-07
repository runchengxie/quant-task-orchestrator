# 研究与运维闭环增量

[English](research-closure.md)

0.4 增加 Codex 回执只读关联、固定版本的 Research 工具快照、显式启用的只读 Codex 工具配置、恢复演练和调度迁移预检。领域 Owner 的职责和 GUI 只读边界保持不变。

## Agent 证据与工具

`codex_task` 的 `action: observe` 要求精确的 `session_id` 与 `receipt`。启动、查询和取消操作都只读已固定摘要的回执与事件，不调用模型。配置、执行文件、提示词和回执身份继续绑定；同一 Owner 计划、任务键和轮次的用量不会跨工作流重复累计。

新增真实验收使用一个会话、两次调用，约 45 秒完成。第二轮保留同一会话，并正确复述首轮随机生成的标记，累计用量与回执一致。这证明无工具恢复完整运行，不代表真实模型工具调用已验收。Token 限额仍用于后续准入，并非运行中的硬上限。

Research Owner 通过 JSON CLI 和 stdio MCP 提供 `research.tool-profile/v1`。四个固定工具按句柄读取证据、计划、Runtime 状态快照和产物，配置及文件均绑定摘要。调用者不能指定任意路径、shell、写入或提交操作。Runtime 状态是快照；已批准任务仍通过现有 Campaign Owner 提交。

Codex 可显式采用 `research.codex-task/v2`，在 v1 字段上增加 `tool_profile`、`tool_profile_sha256`、`tool_gateway_sha256`、`tool_python_sha256`。Owner 声明 `research-read-only`，每轮最多 32 次工具调用。v1 继续无工具。离线 MCP、配置及事件测试不能替代真实模型工具验收。

协调器的 `research_snapshot` 适配器包含 `kind`、`command`、`profile`、`expected_profile_sha256`、`handle`，可附加 `owner_revision`。它调用 gateway 的 `--handle` CLI，只投影内容身份，不展示资源正文。内容中自称 PIT 合格或获准晋升，不会让证据门槛自动通过。

## 研究就绪情况

通过既有数据 Owner 命令，四组件离线归一化得到 966,480 行并通过验证。独立的 `fina_indicator` 两字段 PIT 产物包含 254,356 个事件、6,752 个证券。抽样严格 as-of 检查拒绝了 2020 年及观察日前请求，接受观察有效期内请求，并拒绝过期请求。这些结论只覆盖该组件和验收样本，不能泛化到所有历史样本或策略。

四组件联合 PIT 仍被公司报表模板歧义阻塞，未任意选取模板。失败的部分输出没有有效发布封印，不得消费；生产别名未更新。合格研究仍需要模板选择依据、足够的有效历史、执行语义和独立审查。

新增同一 DAG 中的数据、Runtime、报告真实安装接口验收，包含协调器重启恢复。隔离的合成输入仅验证依赖顺序、Owner 恢复与报告校验，不代表合格经济研究，也不声称预先生成的报告来自该次回测。最终研究资格步骤继续因缺少证据而阻塞。

## 运维

`restore --source BACKUP --sha256 SHA --destination NEW_PATH` 校验摘要、SQLite 完整性和状态库结构，以独占方式写入新目标，不覆盖运行数据库。`storage-check --root DATA_DIRECTORY` 只读检查可用空间，不删除文件、不强制磁盘配额。

`migration-check --input REQUEST_JSON` 接受 `quant.scheduler_migration_request.v1` 及 `old_owner`、`new_owner`、`old_active`、`new_active`，识别双调度风险并生成方案，不执行切换。实际定时器与注册表盘点只保留在私有目录；尚未选定具体迁移任务、完成调度映射、影子执行和回滚验收，因此生产迁移仍阻塞。

`outbox-preview ID --ledger LEDGER` 不发送消息。本地 peer 回执协议在调用前持久化不确定状态，按原标识核对，响应丢失后不盲目重发。本轮未配置外部网络渠道或收件人。用户确认已读与消息送达回执分别保存，详见[运维预检](operations-preflight.zh-CN.md)。

## 已选影子试点

本轮选择只读数据就绪检查，通知保持本地。`shadow-check --config CONFIG --expected-config-sha256 SHA --output-root ROOT` 只允许 `data` 与 `raw_observation`，Skill 目录必须为空。同一份受限配置字节先校验摘要、再解析；每次运行创建独立 UUID 目录，保存自己的 SQLite、计划与检查结果。它只批准两类固定的只读 Owner，不调用模型或计算适配器，不启用定时器、不修改原有调度。

Owner CLI 是可信程序，不是操作系统级文件系统沙箱。实际安装验收比较输入树前后内容，生产使用仍须固定 Owner 版本。完整性成功不代表研究合格；周期调度须在影子演练成功后单独部署，本命令不会自动启用。

## 已验收接口

Research provider [PR #652](https://github.com/runchengxie/quant-research/pull/652) 合并于 `6b88a9668bcbc0edbc98142a57472302d1624047`。相关包 571 项、gateway/生命周期定向 63 项、原生辅助 35 项测试通过，独立审查、静态及文档检查通过。另行非 editable 安装的 stdlib 接口完成四类 CLI 读取、固定摘要 bootstrap 的四次 MCP 读取、v2 计划和消费者绑定预检，未调用模型。

消费者启用全部实际安装 Owner 后，108 项测试全部通过、无跳过，覆盖重启后的数据/计算/报告协议链、两次影子运行输入内容不变、回执观察、资源篡改以及备份/通知故障。静态检查、已安装浏览器行为和合成桌面/移动 Demo 验收通过。这些结果证明工程接口，不证明金融研究有效。
