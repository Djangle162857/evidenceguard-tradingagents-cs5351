# ADR-006: v0.3 证据上下文、结构化简报与本地研究工作台

日期：2026-11-19。状态：用户按本聊天交接计划授权候选实施；当前具体 hash 人审待完成。

OPT-01—06 本轮必做；OPT-05/06不再可选。沿用七项FR、schema_version=1.0、ClaimCard、五档rating、TradingAgents固定基线和原12次成对协议。保留已有预测及图表交互。功能冻结建议为2026-11-22 18:00 Asia/Singapore。

候选仅在 manifest 同时为 prompt_version=evidenceguard-v0.3、policy_version=v0.3 时启用新策略。旧版本保持原行为；baseline无候选提示，冻结工具行为保持旧实现。上下文只选择同run eligible证据，market按available_at、news按published_at的UTC瞬时倒序，平时按evidence_id字典升序；取1行情和最多3新闻，仍为160字符摘录、10条100字符论点。完整台账不截断、不重新赋资格。哈希覆盖确定性上下文投影（版本、run、as_of、所选IDs、文本与coverage），不含测量时间或hash自身；诊断落measurement/transcript。

基本面、历史指标、多周新闻始终标记未提供。单凭空ledger无法证明源成功或故障：news coverage区分 eligible、all_excluded、not_supplied；不将not_supplied冒充源故障。现有snapshot limitations中的明确源故障另保留并传递至运行限制；可选source_status诊断只接收冻结快照实际记录，不发起新检索。无记录且无来源状态时显示unknown。新增诊断不是业务证据，不能改变资格或门禁。

现有portfolio_manager调用增加固定中文输出约定；executive_summary一句中文，investment_thesis依次使用### 利好因素、风险因素、关键分歧、未来一周观察、数据缺口。观察窗口为UTC截点日期后第1日至第7日（含），提示明确推断、上行/下行情景和观察条件，所有业务判断引用现有Claim；不足填写信息不足，price_target=null。不额外总结或修复模型调用，不伪造缺失正文；结构不全通过确定性候选检查记录失败。独立既有门禁继续检查引用，语义支持仍需学生标注。

报告身份为ticker/run/revision/完整hash；无hash的旧报告用规范JSON内容作本地去重身份且显示hash缺失。浏览器内存保存本次会话，不增加数据库或持久账户。默认各ticker按as_of倒序、同截点按revision倒序及身份字典排序选最新，可手选历史；失败草稿也可查看，保持四轴状态。正文只解析已存在的标题和引用；缺章节标简报不完整并保留全文。日报包含身份、截点、状态、原文引用、Claim/Evidence索引及数据缺口；所有导入数据使用textContent，URL仅http/https。

权限精确清单见docs/verification/v0.3/task-contract.md。代码、测试、应用prompt由原本地OpenCode+课程模型生成和返修；Codex只编排、审查、验证与文档。不得改既有测试oracle、Human-only规则、预算边界或调用上限。新增冻结候选使旧审阅/正式结果不适用，不自动批准或发布。

2026-11-20实施审查补充：CLI的`run --policy-version`默认v0.3；旧程序调用缺参数时为v0.2，baseline始终v0.2，批量执行显式传v0.3。source_status helper只从真实快照`records[].kind`及既有`news retrieval raised ` limitation推导新闻error/empty，未更改快照及hash；无此故障标记的外来快照不能证明来源健康，不能泛化为新采集状态协议。

候选暂未验收：实际上游renderer把首个三级标题渲染在`**Investment Thesis**:`同行，新gate及UI要求行首，探针失败（BUG-V03-001）。1687项回归通过未覆盖此缺陷；独立简报、版本接线/调用次数、工作台测试仍缺。共享开发请求200/200，用尽次数边界后停止生成，未手改修复或提高额度。当前具体审查见`docs/verification/v0.3/final-review.md`；本ADR是设计选择，不记录实现已经满足所有条件。
