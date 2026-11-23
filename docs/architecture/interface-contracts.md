# 接口契约 v0.2

状态：待批准。新增持久数据使用UTF-8 JSON，schema_version=1.0；时间必须为带时区ISO 8601并转UTC；金额使用十进制定点字符串或整数微美元，禁止浮点累计。未知值为null，不伪造零。

| 对象 | 必填内容与约束 |
|---|---|
| RunManifest | run_id、revision≥1、ticker、as_of_utc≤启动时刻、analysts、baseline/candidate SHA、model_id、prompt_version、policy_version、budget、dataset_hash；不含密钥，保存后不可修改 |
| Evidence | evidence_id、run_id、kind、source_uri、retrieved_at、published_at/available_at、content_hash、excerpt、eligibility、exclusion_reason；原始内容另存并校验hash |
| ClaimCard | 程序生成claim_id，kind=fact/inference、text、evidence_ids、parent_claim_ids、uncertainty；引用必须同run，禁止悬空或环；fact至少一个合资格证据 |
| DebateTurn | cards、reply_to、conflicts、stop_reason；角色为bull/bear/risky/neutral/safe，冲突引用已存在卡片；stop_reason明确completed/limit/no_evidence/invalid_output |
| DecisionArtifact | run/revision、manifest、evidence和claims引用、报告正文、上游五档rating、limitations、gate_results、四轴状态、artifact_hash；没有完整检查不能released |
| UsageEvent | event_id、attempt_id、parent_attempt_id、role、phase、reserved_tokens/usd、actual_tokens/usd或unknown、provider请求ID、开始/结束、失败原因；幂等结算 |
| Review | reviewer_id、真实时间、run/revision、artifact_hash、approve/reject、reason、授权来源；agent不自行产生真实人工批准 |
| EvaluationRecord | task/arm/repeat、所有版本、snapshot_hash、execution/validation状态、全部usage、耗时、事实标签、rubric、failure_reason；失败也必须完整留档 |

`artifact_hash = SHA256(canonical_json(payload))`。payload仅包括schema_version、业务配置、合资格/排除证据及原文hash、claims、报告和策略版本；键排序、UTF-8、固定分隔符、禁止NaN/Infinity，数组保持业务顺序，不做有歧义的Unicode归一化。排除hash自身、审批事件、发布状态、运行ID以外的非业务测量时间和耗时。明确列出投影字段，不按任意字段名递归删除。

Evidence ID由run、来源、资格时间、内容hash的规范化值派生；同源同内容重复可合并并保留来源指针，不同来源不因文字相同被抹掉。market用available_at，news用published_at；retrieved_at不能冒充二者。

CLI能力：`run`创建草稿，`inspect`显示引用/用量/失败，`replay`使用记录响应不调用模型，`evaluate`冻结成对运行，`review show/approve/reject/publish`控制审阅发布。不得提供agent可调用的自动批准工具。实验产物只需draft，无须对12次实验逐次批准。

发布门禁检查当前磁盘投影并重算hash；批准后文件内容变化必须拒绝。所有目录采用run隔离和原子写入；不接受用户输入路径逃逸项目运行目录。

## 待审测试使用的公共Python接口

这些公开接口已用于首批模块和独立测试；当前实现与验证范围见docs/progress.md。实现不得为绕过测试另加一套行为。

- `contracts.create_manifest(config: dict, *, now: datetime) -> RunManifest`：无I/O纯校验；无效输入抛`ValueError`。manifest冻结，提供`to_dict()`深复制和`manifest_hash`。`budget`字段为`token_limit`、`attempt_limit`、`deadline_seconds`、`input_upper_per_call`、`output_upper_per_call`，均为正整数且禁止bool。model_id必须为已配置课程ID；analysts为market/news的非空无重复子集。
- `evidence.EvidenceLedger(manifest)`：`add(record: dict) -> Evidence`、`get(evidence_id) -> Evidence`、`entries`只读快照。记录run必须匹配，原文hash须正确；schema或hash非法抛`ValueError`。未来/未知资格时间保留为`eligibility='excluded'`，合法项为`eligible`；重复同源项返回同ID。
- `claims.validate_debate_turn(payload: dict, *, role: str, manifest, ledger, existing_claims: list) -> DebateTurn`：非法抛`ValueError`；程序赋卡片ID；`to_dict()`返回规范化卡片。role采用bull/bear/risky/neutral/safe。重复与无界循环在runner的轮次/预算限制内停止。
- `gate.validate_artifact(artifact: dict, *, manifest, ledger, claims: list) -> GateResult`：不调用模型；返回`passed: bool`、`violations: tuple[str,...]`；本函数只能给出待审判定，不能赋予released。
- `review.artifact_hash(payload: dict) -> str`：规范化投影的SHA256；`review.ReviewStore(root)`的`record(artifact, *, reviewer_id, decision, reason, authorization_source, now)`记录审批；测试必须明确`authorization_source='test_fixture'`且存储与真实审批隔离。`review.publish(artifact, *, store, now) -> dict`重新验证hash和门禁，非法抛`ValueError`。
- `budget.BudgetLedger(path, *, token_limit, attempt_limit, usd_limit, deadline, clock)`：`reserve(attempt_id, *, input_upper, output_upper, usd_upper)`返回Reservation；`settle(attempt_id, *, input_tokens, output_tokens, actual_usd)`结算，任何usage字段为None保留预留并停止；`stop(reason)`、`snapshot()`。超额或停止后reserve抛`BudgetExceeded`（ValueError子类）。相同ID不得重复预留；同一结算重放幂等，冲突结算抛错。snapshot字段为reserved_tokens、settled_tokens、attempts、stopped、reserved_usd、settled_usd。

`Evidence.to_dict()`与`RunManifest.to_dict()`不得暴露可修改的内部引用；`record`输入content为原始UTF-8文本，content_hash是该文本SHA256。Evidence的kind为market/news，market判断available_at，news判断published_at；retrieved_at晚于as_of不改变来源已公布时间资格，但必须如实记录。所有时间字段非法格式或缺少时区视为schema错误。

## 首批实现的产物字段

DecisionArtifact固定业务投影字段为schema_version、run_id、revision、manifest、evidence、claims、report、rating、limitations、policy_version。evidence列表包含原文content及台账公开字段；claims采用程序生成的完整卡片；report为带`[cl-<sha256>]`引用的文本，rating沿用Buy/Overweight/Hold/Underweight/Sell。运行状态分别保存execution_status、validation_status、review_status、publication_status，门禁结果和measurement均不进入业务hash。独立门禁重建证据资格和引用图，并核对提供的权威manifest/ledger/claims，不信任文件中自报的passed。文本的语义支持仍由人工评估，结构门禁不能证明每句事实正确。

ReviewStore(root, *, test_mode=False)默认保存真实审阅。test_fixture授权来源仅能写入显式test_mode存储，真实存储不能接受这类批准。测试存储不作为交付中的人工批准证据。review.publish必须从当前产物重建并重新门禁，再匹配本次hash的最后一个真实决定。

## 上游图与冻结快照

`integration.IntegrationContext(manifest, ledger)`通过`wrap(llm, role)`和`wrap_tools(tools)`作为GraphSetup可选boundary；具体压缩与基线差异见ADR-003。五角色接受的规范卡片仍沿用claims接口，经理仍走上游结构化schema及一次普通文本回退。所有HTTP请求由CourseTransport/AsyncCourseTransport在SDK下层分别预留、结算run和项目台账。

`snapshot.freeze_snapshot(ticker, *, clock, source=None)`保存Yahoo当前报价响应与最多三条新闻标题/摘要。market的available_at来自同一报价响应regularMarketTime；news的published_at只取pubDate。源时间未知或未来，EvidenceLedger保留并排除，不以retrieval代替。snapshot_hash绑定整个冻结JSON；`records_for_run(snapshot, run_id)`深复制原文并绑定run。此快照不是历史归档回测数据。

`upstream_runner.run_upstream(config, records, *, llm, run_ledger, project_ledger, now, arm='candidate')`执行真实上游图，返回带独立门禁、原始论点响应、用量与错误的draft产物。baseline只替换冻结工具并保持上游提示；它不伪造候选卡片，因此候选专用结构门禁失败不能解释为基线语义质量失败。

## 成对评估接口

`evaluation.prepare_plan(snapshots, *, baseline_sha, candidate_sha)`要求AAPL/MSFT/NVDA三个不重复快照，冻结12行的task/arm/repeat顺序与快照hash。计划顶层包含schema_version、baseline_sha、candidate_sha、model_id、snapshots、rows和plan_hash；`validate_plan(plan)`校验后返回None。

`execute_plan(plan, *, run_one, output_dir)`串行调用`run_one(row, snapshot)`，输出目录必须是新目录。记录顶层execution_status、validation_status、artifact_hash来自实际产物顶层；run_budget/error是从measurement投影的字段。不得以测量字段覆盖业务状态，缺失执行状态按failed处理。预算或传输停止保留后续not_run行；所有semantic_labels/rubric初始为None。该API不生成真实人工标签。

CLI `evaluate`仅准备计划，不调用模型；完整执行当前通过Python callback接入，尚无一键正式实验命令。所有live实验仍受检查点2真实审阅约束。

## v0.3 候选增量契约（当前hash待人审）

见ADR-006与`docs/verification/v0.3/task-contract.md`。DecisionArtifact和ClaimCard仍为1.0，不增加必填字段。manifest的prompt_version=evidenceguard-v0.3与policy_version=v0.3共同启用新候选策略；旧版本和baseline保持旧行为。

`research_context.build_research_context(manifest, ledger, *, source_status=None)`返回所选证据ID、context_text、coverage、截点后第1—7个UTC日期与context_hash。最多1行情+3新闻，资格时间倒序/ID升序，excerpt≤160；完整ledger不变。基本面/历史指标/多周新闻明确缺失。source_status仅来自实际冻结采集状态，未知不猜测；无新闻、全部排除、明确源故障区分。该确定性包在运行measurement/transcript中保存。

最终经理现有调用输出中文一句executive_summary和含五个固定三级标题的investment_thesis。缺章或无效现有Claim引用可使候选失败，不自动补写；无依据写信息不足；未来窗口为推断，price_target为空。保留现有独立门禁和上游结构化失败后的既有回退上限，不新增总结调用。

Web仅管理手动导入的本会话报告。身份保留ticker/run/revision/hash；不同修订不覆盖。正文缺结构显示简报不完整及原文，不推测观点。日报Markdown保留身份、截点、四轴状态、引用与缺口；所有本地操作产生0次模型请求。

实际接线（2026-11-20）：CLI `run --policy-version {v0.2,v0.3}`默认v0.3；旧程序调用缺该字段时保留v0.2，baseline强制v0.2，批量运行显式传v0.3。source_status仅根据冻结快照的`records[].kind`及`news retrieval raised `限制前缀推导；它不是新增证据字段或通用源健康接口，无法证明没有该标记的外来快照采集成功。

当前兼容缺陷：上游`render_pm_decision`的`**Investment Thesis**: ### 利好因素`与行首标题解析冲突，导致`section_headings_invalid`；未修，v0.3尚未验收。完整当前范围及测试缺口见`docs/verification/v0.3/final-review.md`。本补充定义目标契约，不宣称当前结构化链路已通过。
