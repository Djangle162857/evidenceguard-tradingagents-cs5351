# TradingAgents 候选基线检查记录

检查日期：2026-11-19。方法：从公开 GitHub 仓库获取浅克隆，读取 README、配置、调用、输出、图结构、测试与 CI 文件；**未安装或执行上游程序，未运行其测试，未调用任何模型 API**。

- 仓库：https://github.com/TauricResearch/TradingAgents
- 固定提交：`9fa1196fffbcfd9de5146d2dd2869df84ab99838`
- 提交时间：2026-11-04T02:13:55-08:00
- 提交说明：`announce Trading-R1 official release`
- 许可证：仓库 `LICENSE` 为 Apache License 2.0；后续派生实现应保留相应许可与归属。
- 该提交为需求研究时的候选，不代表已采用为小组最终基线。

## 1. 已验证的静态事实

| 来源 ID | 文件 / 固定版本链接 | 观察 | 需求影响 |
| --- | --- | --- | --- |
| SRC-UP-README | [README.md](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/README.md) | 已有多角色研究、CLI、多个市场与模型、MD/HTML 报告说明 | 不将已有 CLI、报告、多市场或多模型本身算新增功能 |
| SRC-UP-CONFIG | [default_config.py#L117](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/tradingagents/default_config.py#L117) | 已有 llm_max_retries、max_tokens、checkpoint_enabled、辩论轮数和工具轮数配置 | FR-005 面向整次运行的累计预算和失败处置，不能只添加已有参数 |
| SRC-UP-STRUCT | [structured.py#L59](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/tradingagents/agents/structured.py#L59) | structured invoke 失败返回 None，调用方可改用自由文本；共用 helper 的第 95 行直接调用 plain_llm | FR-004 必须在最终发布边界独立复验，不能把框架返回文本当作通过验证 |
| SRC-UP-PM | [portfolio_manager.py](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/tradingagents/agents/managers/portfolio_manager.py) | 类型化 PortfolioDecision 成功时使用 rating，失败时调用普通 llm 并 parse_rating | 保留五档观点语义，新增独立 valid/blocked 与人工审阅状态 |
| SRC-UP-SCHEMA | [schemas.py](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/tradingagents/agents/schemas.py) | 上游已对 ResearchPlan、TraderProposal、PortfolioDecision 定义结构；可选价格字段做清洗 | 本项目新增证据关联与发布契约；不能声称首次引入结构化决策 |
| SRC-UP-GRAPH | [trading_graph.py#L54](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/tradingagents/graph/trading_graph.py#L54) | 已接收 callbacks，创建 quick/deep 模型；后续方法提供 checkpoint lifecycle 和 save_reports | 可评估复用这些接口；最终模块分解由后续 ADR 决定 |
| SRC-UP-PARALLEL | [setup.py#L157](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/tradingagents/graph/setup.py#L157) | 所选分析师及 memory 节点已并行，研究辩论等待其全部完成 | 不把并行化当本组新增；预算预留需要处理并发 |
| SRC-UP-STATS | [stats_handler.py](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/cli/stats_handler.py) | CLI callback 已维护 tokens_in / tokens_out 和调用统计 | 计数不等于跨入口、跨重试的原子预算；新增方案需验证完整性 |
| SRC-UP-DATE | [date_window.py](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/tradingagents/dataflows/date_window.py) | 已有日期截断、历史数据资格与未知时间保护函数 | 保留并回归现有保护；新增台账不得移除或绕过它 |
| SRC-UP-NODATA | [test_no_data_handling.py](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/tests/test_no_data_handling.py) | 已有无数据 sentinel 与 vendor 不可用相关测试 | 不能声称现有系统对所有缺数据场景都会造假；新增端到端状态须验证 |
| SRC-UP-CI | [ci.yml](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/.github/workflows/ci.yml) | 已有多 Python 版本 tests、安装 smoke 和全仓库 ruff | 这与课程六类门禁并非一一等价；需增补项目特定批准、Schema、语义、日志等检查 |
| SRC-UP-LAYOUT | [pyproject.toml](https://github.com/TauricResearch/TradingAgents/blob/9fa1196fffbcfd9de5146d2dd2869df84ab99838/pyproject.toml) | Python ≥3.11，包为 tradingagents/ 和 cli/，测试目录 tests/ | 后续明确课程示例目录映射；避免未经评审移动整个基线 |

## 2. 观察与提案的分界

已验证的是指定文件的代码结构和文档陈述。没有执行证据可以说明该版本所有路径正确、课程端点兼容、运行耗时或费用水平。

证据 ID 台账、结构化论点卡片、全局原子预算、独立发布门禁、绑定哈希的人工批准和成对评估是本次提案的改进范围；未声称穷尽检查整个仓库后证明上游绝对没有类似机制。后续若发现重复能力，应更新需求增量分析与实际贡献说明。

## 3. 进入实现前的基线冻结

1. 小组确认其实际仓库与 commit；若不同，重新核对本表。
2. 记录保留与修改的文件和接口，并保留原有测试、许可证与归属。
3. 对比实验的 baseline / candidate 都固定 SHA、输入与模型配置，不能用漂移的 main 分支。
4. 当前项目工作区只包含需求与课程资料；本次未把整个上游克隆纳入提交，也未修改其源码。
