# EvidenceGuard 中英文对照讲稿

按 PDF 页码对应。每页提供完整英文口播和对应中文口播，排练时任选一种语言。主讲约 17 分 50 秒，含第 11 页约 90 秒的离线演示。第 18–20 页留作问答。工程证据截点为 2026 年 11 月 20 日。

## 01 · EvidenceGuard TradingAgents / 封面 · 0:00–0:25

**English**

Good afternoon. Today I’m presenting EvidenceGuard, an extension of TradingAgents for auditable stock research. I’ll show how evidence gets into a report, what the checks can verify, and what still has to happen before a report can be published.

**中文**

大家好。今天介绍的是 EvidenceGuard，一个让 TradingAgents 股票研究报告更容易审计的扩展。我会讲一条证据怎样进入报告，程序可以核验哪些事项，以及一份报告正式发布前还需要什么。

## 02 · Research problem and scope / 研究问题与范围 · 0:25–1:20

**English**

Suppose a report cites a news article and recommends a position. As a reviewer, I want to know when the article became available, which claim relies on it, how much the run consumed, and which revision was reviewed. The project makes those answers inspectable. The initial scope is Apple, Microsoft and Nvidia, with market and news analysts, one investment debate, and one risk debate. The system produces local research drafts. It has no broker connection or order execution. I’ll start with what TradingAgents already provides.

**中文**

假设报告引用了一篇新闻，并给出一个投资判断。作为审阅者，我需要知道新闻什么时候公开、哪条论点引用了它、这次运行消耗了多少资源，以及人审对应的是哪一个修订版。项目把这些问题变成可以直接检查的记录。初版覆盖苹果、微软和英伟达，只使用行情和新闻分析师，投资辩论和风险辩论各一轮。系统生成本地研究草稿，没有券商连接或下单功能。先看 TradingAgents 已有的能力。

## 03 · Upstream reuse and extension / 上游复用与扩展 · 1:20–2:20

**English**

TradingAgents already provides the analyst graph, investment and risk debates, structured decisions, plain-text fallback, and usage reporting. We reuse that graph at a pinned commit, which gives the candidate and future baseline comparison a stable reference. EvidenceGuard adds an evidence ledger, structured claim references, request-level budget control, deterministic replay, and a publication check bound to the report hash. Most of that work sits in the EvidenceGuard package. An optional boundary connects it to the upstream graph, which keeps the integration small and preserves the original project layout.

**中文**

TradingAgents 已有分析师执行图、投资与风险辩论、结构化决策、普通文本回退和用量统计。本项目在一个固定提交上复用这张图，为候选方案和之后的基线比较提供稳定参照。EvidenceGuard 新增证据台账、结构化论点引用、逐请求预算控制、确定性回放，以及绑定报告哈希的发布检查。大部分新增逻辑位于 EvidenceGuard 包，通过一个可选边界接入上游执行图，保留原来的项目结构。

## 04 · Seven functional requirements / 七项功能需求 · 2:20–3:30

**English**

The seven requirements follow the life of a report. The run contract freezes the inputs. The ledger records evidence and decides whether it is eligible. The debate records claims and conflicts. The final gate independently checks the artifact. The budget applies to model requests throughout the run. Replay and evaluation preserve the information needed to reproduce or compare runs. Human review then controls publication. Each requirement has an observable outcome. For example, the ledger retains excluded records, the budget records when a request stops, and the review command checks the exact report hash. Component tests cover part of this chain. Full protocol acceptance is still pending.

**中文**

七项功能需求对应一份报告的生命周期。运行契约固定输入，台账记录证据并判断资格，辩论记录论点与冲突，最终门禁独立检查产物。预算贯穿每次模型请求，回放与评估保存复现及比较所需的信息，最后由人工审阅控制发布。每项需求都有可观察的结果。例如，台账会保留被排除的记录，预算会留下请求停止的记录，审阅命令会检查报告的具体哈希。组件测试覆盖了这条链路的一部分，完整协议仍待验收。

## 05 · Architecture and decision authority / 架构与决策权限 · 3:30–4:50

**English**

Follow the diagram from left to right. The run contract fixes the analysis cutoff and configuration. The evidence ledger records inputs and their qualification times. The upstream graph proposes factual claims, inferences and disagreements. Five debate roles share one claim adapter, so extracting their structure does not need a separate request per role. The independent gate checks the final output, which starts as a draft. Before publication, the code checks the current artifact against the human decision that applies to it. The dashed connection shows where the request budget constrains calls across the graph. The model proposes the content. Code checks time, references, usage and state. A student reviewer assesses whether a claim is actually supported.

**中文**

沿图从左往右看。运行契约固定分析截点和配置。证据台账记录输入及其资格时间。上游执行图提出事实论点、推断和分歧。五个辩论角色共用一个论点适配器，无须为每个角色再发一次结构提取请求。独立门禁检查最终输出，产物首先保存为草稿。发布前，程序会核对当前产物及其对应的人工决定。虚线表示预算约束贯穿执行图的模型调用。模型提出内容，代码检查时间、引用、用量和状态，学生审阅者判断论点是否真的有原文支持。

## 06 · Evidence time and context / 证据时点与上下文 · 4:50–5:50

**English**

There are two different clocks. For a quote, eligibility uses its availability time. For news, it uses publication time. Retrieval time records when the program fetched the item. A record with an unknown or future eligibility time stays in the ledger with an exclusion reason. The v0.3 context selects at most one eligible quote and three news items in a stable order while retaining the full ledger. It expressly reports missing fundamentals, historical indicators and multi-week news. That selection also changes what the model sees, which matters when interpreting a future comparison with the baseline.

**中文**

这里涉及两类时间。行情看可用时间，新闻看发布时间，抓取时间只记录程序何时取得资料。资格时间未知或晚于截点的记录仍留在台账里，并写明排除原因。v0.3 以固定顺序最多选一条合格行情和三条新闻放入上下文，同时保留完整台账。基本面、历史指标和多周新闻的缺口也会明确显示。这种筛选改变了模型实际看到的内容，之后解释与基线的比较时需要考虑这个因素。

## 07 · Artifact state and human review / 产物四轴状态与人工审阅 · 5:50–7:00

**English**

The table separates execution, validation, review and publication. A run can finish and still fail validation. A draft that passes validation can remain pending review. To publish, it must be completed, pass the gate, and have a human approval for the current artifact hash. The hash covers a defined business projection that includes configuration, evidence, claims and the report. When publication is requested, the program rechecks the current content and recomputes the hash. Editing the report changes that hash, so a previous approval cannot carry over. The demonstration will show the pending-review case.

**中文**

表格把执行、验证、审阅和发布分开记录。一次运行可以已经完成，但验证仍然失败。通过验证的草稿也可以继续等待审阅。发布要求执行完成、门禁通过，而且当前产物哈希已有真人批准。哈希基于明确的业务字段，包括配置、证据、论点和报告。请求发布时，程序会重新检查当前内容并重算哈希。修改报告会得到不同的哈希，旧批准无法沿用。稍后的演示会展示等待审阅的情况。

## 08 · Request budgets / 请求预算 · 7:00–7:55

**English**

The budget applies at the HTTP request boundary. The program reserves a conservative amount before sending each request and settles it when usage is known. If usage is unknown, the reservation stays in place and generation stops. Retries, format repair and auxiliary calls are included. The project sets a 95-US-dollar ceiling, with 55 for development and 40 for application use and reserve. At the evidence cutoff, all 200 authorized development requests had been used. The request-count limit and the dollar limit are enforced separately.

**中文**

预算控制放在 HTTP 请求边界。每次发出请求前，程序先按保守上界预留资源，用量明确后再结算。用量未知时保留预留并停止生成。重试、格式修复和辅助请求都要计数。项目设置 95 美元上限，其中开发 55 美元，应用及预留 40 美元。到证据截点，获授权的 200 次开发请求已全部用完。请求次数和美元上限分别执行。

## 09 · FR-007 traceability / FR-007 需求追踪 · 7:55–9:05

**English**

Here is one requirement traced end to end. FR-007 says a changed report cannot reuse a previous approval. The design uses SHA-256 over the canonical business projection. The review component computes the hash, and the publication path recomputes it from the current content. The negative case changes business content after review and attempts publication. The expected result follows directly from the requirement. The old decision can no longer authorize the current bytes of business content, and the publish request is rejected. The gate and review tests give evidence for this behavior. The complete safety protocol still contains scenarios to run.

**中文**

这里以 FR-007 为例，从需求一路追到验证。它要求内容改变后不能沿用旧批准。设计上对规范化业务字段计算 SHA-256。审阅组件计算哈希，发布时根据当前内容重算。负面案例是在审阅后修改业务内容，再尝试发布。预期结果直接来自需求。旧决定无法授权当前这份修改后的内容，因此发布请求被拒绝。门禁和审阅测试为这个行为提供证据。完整安全协议还有其他场景待执行。

## 10 · Research workbench / 研究工作台 · 9:05–10:05

**English**

This screenshot comes from the browser check with synthetic inputs. The workbench can import several report files, keep different revisions separate, follow claim and evidence references, and export Markdown or the original JSON. Imports stay in the current page session. Viewing, switching and exporting require zero model calls. The market chart has its own data source, and the forecast preview uses synthetic values. In the terminal demonstration, I’ll focus on the report lifecycle with a fixed fixture.

**中文**

这张截图来自使用合成数据的实际浏览器检查。工作台可以导入多份报告，保留各个修订版，跟踪论点与证据的引用，并导出 Markdown 或原始 JSON。导入记录只保留在当前页面会话。查看、切换和导出都产生零次模型调用。行情图有独立的数据来源，预测预览使用合成数值。接下来的终端演示会用一个固定夹具展示报告生命周期。

## 11 · Offline demonstration / 离线演示 · 10:05–11:35

**English**

[Replay the fixture.] This creates a draft from synthetic data and uses zero model requests. [Run inspect and open the JSON.] Here is an evidence timestamp and the claim reference that leads back to it. The four states are completed, passed, pending and draft. [Run publish with an empty review store.] The command returns exit code two and reports that no review exists for this artifact. It leaves no published file. The fixture uses a placeholder version ID. The paths in the demo belong under the local results directory.

**中文**

［回放夹具。］这一步使用合成数据创建草稿，模型请求数为零。［执行 inspect 后打开 JSON。］这里能看到证据时间戳，以及指回它的论点引用。四项状态分别是执行完成、验证通过、等待审阅和草稿。［使用空审阅存储执行 publish。］命令返回退出码 2，提示当前产物没有审阅记录，且没有生成发布文件。夹具的版本标识是占位值。演示输出统一放在本地 results 目录下。

## 12 · Verification evidence and its limits / 验证证据与边界 · 11:35–12:50

**English**

The full offline regression recorded 1,687 passing tests, one skip for an optional AWS dependency and one online integration test deselected. The archived Ruff and syntax checks also passed. Desktop and phone interaction checks used synthetic fixtures. The gate benchmark measured a p95 of about 1.069 milliseconds for a fixture with 100 claims and 25 evidence records. That figure measures only the gate at that workload. Report quality and token savings still require the paired business evaluation. One specific gap in the offline suite is the subject of the next slide.

**中文**

完整离线回归记录了 1,687 项通过、1 项因可选 AWS 依赖跳过、1 项在线集成测试被排除。归档中的 Ruff 和语法检查也通过。桌面与手机交互检查使用的是合成夹具。门禁基准在 100 条论点、25 条证据的夹具下测得约 1.069 毫秒的 p95。这个数字只对应该负载下的门禁耗时。报告质量和 token 节省仍需成对业务评估。下一页看离线套件漏掉的一条具体路径。

## 13 · Renderer compatibility defect / 渲染兼容缺陷 · 12:50–14:25

**English**

The upstream renderer puts the first Markdown heading on the same line as the Investment Thesis label. Both the new gate parser and the workbench parser look for a heading at the beginning of a line. In the probe using the actual upstream renderer, the gate returned section headings invalid. The browser fixture already had a newline after the label, so it never exercised this boundary. This defect blocks v0.3 acceptance. The repair needs a test that sends actual upstream output through the gate and the workbench parser, including malformed examples that must still fail. It also needs a fresh offline regression and review of the updated candidate. At the evidence cutoff, the development request limit prevented another generation round.

**中文**

上游渲染器把第一个 Markdown 标题接在 Investment Thesis 标签同一行。新门禁和工作台的解析器都要求标题出现在行首。实际调用上游渲染器的探针返回了章节标题无效。浏览器夹具已在标签后换行，因此没有经过这个接口边界。该缺陷阻碍 v0.3 验收。修复时应让实际的上游输出经过门禁和工作台解析器，还要加入应继续失败的错误格式，再执行完整离线回归并审阅新候选。到证据截点，开发请求次数上限阻止了下一轮生成。

## 14 · AI supervision and course gates / AI 监督与课程检查 · 14:25–15:25

**English**

Each generation task specifies allowed files, interfaces and exit conditions. Local OpenCode with the CityU model generates and repairs project code and tests. Codex coordinates the tasks, reviews changes, runs checks and documents the evidence. The student provides the human approvals. The workflow defines six checks, including test approval, regression, semantic evaluation and the AI-use record. The public candidate branch gives the workflow a concrete commit to check. Required-check enforcement and branch-protection evidence remain pending.

**中文**

每个生成任务都会写明允许修改的文件、接口和退出条件。本地 OpenCode 使用 CityU 模型生成和修正项目代码及测试。Codex 负责编排、审查变更、运行检查和记录证据。真人批准由学生给出。工作流定义了六项检查，包括测试批准、回归、语义评估和 AI 使用记录。公开候选分支为这些检查提供具体提交。必需检查的强制执行和分支保护证据仍待落实。

## 15 · Quality and cost evaluation / 质量与成本评估 · 15:25–16:35

**English**

The plan has three stocks, two repeats and two arms, for twelve runs. Both arms use the same frozen inputs and model, with a recorded run order. The records retain failures, repeat attempts and unknown usage. The student labels factual support, applies the rubric and checks the labels again at least 24 hours later. The candidate targets are at least 0.95 support, at least four out of five on the rubric, and at least five usable runs out of six, with at least as many usable runs as the baseline. Token use at or below 80 percent of baseline is a target. The formal experiment is pending.

**中文**

计划覆盖三个股票、每组重复两次、基线和候选两组，共十二次运行。两组使用相同的冻结输入和模型，并记录运行顺序。失败、重复尝试和未知用量都保留。学生标注事实支持情况、按评分标准打分，并至少间隔 24 小时复核。候选目标是支持率至少 0.95、评分至少 4 分（满分 5 分）、六次中至少五次可用，而且可用次数不少于基线。token 用量不超过基线的 80% 也是一个目标。正式实验仍待执行。

## 16 · Contribution and remaining work / 工程贡献与剩余工作 · 16:35–17:30

**English**

The engineering contribution is an auditable path inside the existing graph. A reviewer can trace a factual claim to a time-qualified record, inspect how requests were accounted for, and identify the report revision that requires approval. The next engineering work is renderer compatibility and the missing regression coverage. After the updated candidate is frozen and reviewed, the formal comparison, student labels and delayed recheck can provide evidence about quality and cost.

**中文**

这项工程贡献是在现有执行图中建立一条可以审计的路径。审阅者能从事实论点追到满足时间资格的记录，检查模型请求怎样计量，并找到需要批准的具体报告修订版。接下来的工程工作是修复渲染兼容性并补齐回归覆盖。新候选冻结和审阅后，才能用正式对比、学生标注和延后复核取得质量与成本证据。

## 17 · Thank you / 结束 · 17:30–17:50

**English**

The offline demonstration shows how a draft exposes its evidence and why an unreviewed revision stays a draft. The candidate still has an integration defect, and formal quality and cost results are pending. Thank you. I’m happy to take questions.

**中文**

离线演示展示了草稿怎样公开其证据，以及为什么未经审阅的修订版仍是草稿。当前候选还有一项集成缺陷，正式质量和成本结果仍待取得。谢谢大家，欢迎提问。

## 18 · Backup: rejection cases / 备查：拒绝场景 · 问答

**English**

These are expected responses from the contract. For example, an item with an unknown or future source time is retained as excluded, and a changed report must obtain review for the new hash. The demo exercised the missing-approval case. Each other row has its own verification scope.

**中文**

这些是契约规定的预期行为。例如，来源时间未知或晚于截点的记录会保留，但标记为排除。报告内容修改后，需要审阅新的哈希。演示执行的是缺少批准这一例。其他各行都有各自的验证范围。

## 19 · Backup: mobile inspection / 备查：手机端查证 · 问答

**English**

This browser check used a 390 CSS-pixel viewport and a synthetic report. The evidence details and artifact states remained available, and the page showed no horizontal overflow in that check. Navigation is still tight on a narrow screen.

**中文**

这次浏览器检查使用 390 CSS 像素宽的视口和一份合成报告。证据详情及产物状态可以查看，本次检查未观察到页面整体横向溢出。窄屏导航仍有些拥挤。

## 20 · Backup: evidence index / 备查：证据索引 · 问答

**English**

The repository contains the requirements, the candidate review and the recorded renderer probe. The review gives the regression results and the remaining work. The candidate branch and GitHub Actions provide the commit and check results for the uploaded workspace snapshot.

**中文**

仓库中可查需求、候选审查和已记录的渲染探针。审查文档给出了回归结果和剩余工作。候选分支及 GitHub Actions 提供这次上传对应的提交和检查结果。
