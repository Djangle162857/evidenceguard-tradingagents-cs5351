# EvidenceGuard 中英文对照讲稿

每段对应一页 Beamer。演示步骤见第 10 段。

## 01 · EvidenceGuard TradingAgents / 封面

**English**

Good afternoon. Today I’m presenting EvidenceGuard, an extension of TradingAgents that makes stock research reports easier to audit. I’ll walk through the evidence ledger, the links between claims and sources, and the offline replay.

**中文**

大家好。今天介绍 EvidenceGuard，一个让 TradingAgents 股票研究报告更便于审计的扩展。我会介绍证据台账、论点和来源之间的引用关系，然后演示一次离线回放。

## 02 · Stock research and evidence / 股票研究与证据

**English**

Start with a claim in a research report. To review it, we need to know which run produced it, what source it cites, and when that source became available. EvidenceGuard records the ticker, analysis cutoff and configuration for the run. Each evidence record carries a source, a timestamp and a content hash. The report includes claim references that connect back to those records. The research scope covers Apple, Microsoft and Nvidia, with market and news analysts.

**中文**

先从报告里的一条论点看起。审阅时需要知道它来自哪次运行、引用了哪个来源，以及这条资料何时可以取得。EvidenceGuard 记录每次运行的股票代码、分析截点和配置。每条证据都有来源、时间戳和内容哈希。报告中的论点引用可以一路追到对应记录。项目研究范围包括苹果、微软和英伟达，使用行情和新闻分析师。

## 03 · TradingAgents integration / 接入 TradingAgents

**English**

TradingAgents supplies the analyst graph, investment and risk debates, and the structured investment decision. EvidenceGuard connects to that graph through the optional GraphSetup boundary. The extension adds an evidence ledger and structured claim references, checks artifacts independently, and records reservations and settlement for requests. It also provides offline replay and links a review decision to the hash of the report it applies to.

**中文**

TradingAgents 提供分析师执行图、投资与风险辩论，以及结构化投资决策。EvidenceGuard 通过 GraphSetup 中的可选接口接入这张图。扩展增加证据台账和结构化论点引用，独立校验报告产物，并记录每次请求的预留和结算。它也提供离线回放，并把审阅决定绑定到对应报告的哈希。

## 04 · Report architecture / 报告架构

**English**

Read the diagram from left to right. The manifest fixes the inputs for a run. The ledger records evidence and its qualification time. The TradingAgents graph produces structured claims. The validation gate checks source eligibility and the references in the report. The request budget connects to the graph at the request boundary, where each attempt receives a reservation.

**中文**

沿图从左往右看。运行清单固定输入，证据台账记录证据及其资格时间。TradingAgents 执行图产生结构化论点。校验门禁检查来源资格和报告中的引用。请求预算在调用边界接入执行图，为每次尝试分别预留资源。

## 05 · Evidence time and context / 证据时点与上下文

**English**

Market data uses the time it became available. News uses the time it was published. EvidenceGuard checks these timestamps against the run’s analysis cutoff. The context selector takes up to one eligible market record and three eligible news records. It orders the selected records consistently by timestamp and ID. The full set stays in the ledger, where a reviewer can inspect individual records.

**中文**

行情使用可用时间，新闻使用发布时间。EvidenceGuard 把这些时间与本次运行的分析截点进行比较。上下文选择最多一条合格的行情记录和三条合格的新闻记录，并依据时间和 ID 按固定规则排序。完整记录保留在台账里，供审阅者逐条检查。

## 06 · From report text to source records / 从正文追到来源

**English**

Start at the claim ID embedded in the report. It points to a record containing the claim text and its evidence IDs. Each evidence ID leads to a source URI, a qualification timestamp and a hash of the source content. Those identifiers let a reviewer follow a reference through all three records. In the offline replay, I’ll trace one example through this chain.

**中文**

从正文里的论点 ID 出发，可以查到论点文本和对应的证据 ID。再沿着证据 ID，就能找到来源 URI、资格时间和来源内容的哈希。这些标识把报告、论点和证据串起来。离线回放时，我会沿这条路径查一条示例记录。

## 07 · Hash-bound review / 哈希绑定审阅

**English**

EvidenceGuard computes a SHA-256 hash over a defined set of business fields, including configuration, evidence, claims and report text. Each review record ties the decision to the run, revision and hash. The check recomputes the hash from the current content and compares it with the review record. A content edit produces a new hash, so review follows the specific version of the report.

**中文**

EvidenceGuard 对一组明确的业务字段计算 SHA-256，其中包括配置、证据、论点和报告正文。每条审阅记录都把决定与运行、修订号和哈希绑定。校验时，根据当前内容重算哈希，再与审阅记录比对。修改内容会产生新哈希，审阅因此对应到具体版本。

## 08 · Request budget / 请求预算

**English**

The budget is enforced when a request is reserved. Before sending a request, the program checks the attempt count and allocates a bound for input, output and cost. Each attempt has its own reservation, including a retry. The ledger applies the usage returned by the provider to that attempt. This gives the run an account of request count and resource use.

**中文**

预算在预留请求资源时执行。发出请求前，程序检查尝试次数，并为输入、输出和费用设置预留上界。每次尝试都有独立预留，包括重试。台账将返回的用量记入对应请求，因此能按次查阅运行的请求数和资源消耗。

## 09 · Research workbench / 研究工作台

**English**

In the workbench, import a report JSON file and choose the revision to inspect. The ticker, run ID, revision and artifact hash identify each imported report. Selecting a claim reference brings up the matching evidence details. The workbench can export a daily Markdown report or download the original report JSON.

**中文**

在工作台导入报告 JSON 后，可以选择要查看的修订版。系统用股票代码、运行 ID、修订号和产物哈希识别每份报告。点击论点引用，就能查看对应证据的详情。工作台可以导出 Markdown 日报，也可以下载原始报告 JSON。

## 10 · Offline replay / 离线回放

**English**

[Run the replay command in the presentation README.] The bundled example produces one evidence record and one claim. [Compare the first two lines of output.] Here is the evidence ID on the claim. It matches the ID in the ledger. The manifest gives us the analysis cutoff, and the evidence record gives us its qualification time. Finally, the validation field shows that this replay passed its artifact checks.

**中文**

［运行配套说明中的回放命令。］内置示例产生一条证据和一条论点。［比较输出的前两行。］这是论点中的证据 ID，与台账里的记录 ID 一致。运行清单给出分析截点，证据记录给出资格时间。最后看校验字段，本次回放通过了产物检查。

## 11 · Offline verification / 离线验证

**English**

The November 24 offline regression recorded 1,687 passing tests. The component tests exercise the timestamps used for market and news eligibility, the links between claims and evidence, and the hash used for report review. One review test alters the business content and verifies that the report gets a different hash. Together with the replay, these test cases show how the project checks the evidence chain.

**中文**

11 月 24 日的离线回归记录了 1,687 项通过。组件测试覆盖行情与新闻的时间资格、论点与证据的引用，以及报告审阅所用的哈希。其中一项审阅测试修改业务内容，再验证报告是否产生不同的哈希。结合刚才的回放，可以看到项目如何检查整条证据链。

## 12 · Thank you / 结束

**English**

EvidenceGuard records the source and time behind each evidence item, connects report claims to those records, and gives each reviewed report a content hash. The offline replay demonstrates that trace directly. Thank you. I’m happy to take questions.

**中文**

EvidenceGuard 记录每条证据的来源和时间，把报告论点与证据记录关联起来，并通过内容哈希定位审阅对应的报告。刚才的离线回放展示了这条引用路径。谢谢大家，欢迎提问。

## 13 · Repository references / 仓库索引

**English**

The repository contains the requirements, architecture blueprint and interface contracts. The offline example lives in the examples directory, and the component tests are under test/offline.

**中文**

仓库提供需求、架构蓝图和接口契约。离线示例在 examples 目录，组件测试在 test/offline 目录。
