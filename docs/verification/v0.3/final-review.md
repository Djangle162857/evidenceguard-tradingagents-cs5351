# EvidenceGuard v0.3 候选交接审查

记录日期：2026-11-20（Asia/Singapore）。结论：**CHANGES REQUIRED，未完成 v0.3 验收，不可作为正式冻结版本或付费实验起点**。这是 Codex 工程审查，不是学生批准。用户最新指令“先继续原有的工作”用于恢复 v0.3；HTTP 接口工作暂停，其私有草稿没有接入应用。

## 已落地范围

| 范围 | 当前行为 | 证据与限制 |
|---|---|---|
| 证据上下文 | 同 run 合资格最新一条行情、最多三条新闻；UTC 资格时间倒序、同时间 ID 升序；保留全台账、覆盖诊断、缺口和确定性 hash | `research_context.py`；18 项新增离线组件测试。基本面、历史指标、多周新闻明确未提供，不增加检索或模型调用。 |
| 研究生成 | 候选最终经理现有调用增加中文一句结论、五固定章节、七自然日推断窗口和 Claim 引用约定，目标价留空；新结构检查进入独立门禁 | `integration.py`、`research_brief.py`、`gate.py`；**存在下述结构化渲染阻断缺陷**，不能称生成链路验收通过。 |
| 版本接线 | CLI `run` 新增 `--policy-version {v0.2,v0.3}`，默认 v0.3；旧程序调用未提供该参数仍为 v0.2；批量执行显式传 v0.3，baseline 强制 v0.2 | `live_cli.py`、`batch_cli.py`；新分支的独立自动回归未补齐。旧回归通过不能证明所有新组合兼容。 |
| 工作台与报告 | 深浅主题、本会话多文件导入、ticker/run/revision/hash 去重、三股票摘要、历史修订选择及行情同步/不一致提示 | 原生 Web，无数据库；页面重载后手动导入记录丢失。四轴状态只展示，不生成批准或发布。 |
| 简报与证据 | 提取现有章节，缺失标“简报不完整”并保留全文；短引用按钮仍按完整 Claim/Evidence ID 定位；可查来源、原文、时间及排除原因 | 浏览器合成夹具检查通过；真实上游结构化输出首章仍受渲染缺陷影响。 |
| 日报与下载 | 默认各股票最新已导入报告，可手选旧修订或排除股票；Markdown 保留身份、截点、四态、引用与缺口；原 JSON 下载内容保留 | 两份实际浏览器导出样例见下；全部是合成 UI QA 数据，未经业务门禁，不是真实研究报告。 |

`DecisionArtifact.schema_version=1.0`、ClaimCard 和业务哈希投影保持原契约。预测、行情脚本和原演示 JSON 与起点 hash 一致；预测仍为明确标记的“合成演示”，没有真实预测序列导出器。报价/新闻快照不是 OHLC 历史。查看、导入、图表与导出不会调用模型；TradingView 保持独立外部行情来源。

## 阻断缺陷与未完成项

**BUG-V03-001：上游结构化渲染与章节解析不兼容。** `tradingagents/agents/schemas.py::render_pm_decision` 产生 `**Investment Thesis**: ### 利好因素`，而新校验器和前端解析器要求 `### 利好因素` 位于行首。合法结构化 thesis 的第一章因此被误判缺失；实际探针输出 `['section_headings_invalid']`，见 [原始探针结果](structured-render-probe.txt)。浏览器夹具人为提供了换行，因此其成功不能反证这个真实兼容问题。保留门禁失败，不放宽检查来掩盖问题。

仍缺合格的独立简报校验、版本/经理调用次数及工作台自动化回归。请求 200 的测试候选包含虚构导入、错误 fake/断言和截断 JS，审查后拒绝进入活动测试树；仅接受其中完整的来源状态 helper。详见 本地生成审查。现有 18 项新测试集中在上下文组件，不能代替缺失测试。

开发请求次数已达到授权上限 **200/200**，下一次被请求边界以 429 拒绝。开发与应用预算合计上限仍为 USD95。

依据 `AGENTS.md` “Application code, test code and application prompts must be generated/modified through local OpenCode using the verified CityU course model” 与本轮任务契约的累计 200 次边界，不能直接手修或再发生成请求。后续修复先需要真实用户明确调整请求次数授权并落实到原边界；美元上限仍为 USD95，不自动增加。当前源码批准不能代替修复。真人还须处理 Human-only 来源合规、具体 hash 审阅、付费业务实验授权、学生标注与 ≥24 小时复核。

轻微体验债：切换已存在报告可能出现重复导入提示；旧报告缺章提示有重复；手机沿用的窄导航仍需打磨。完整协议逐场景映射、键盘全流程审计、真实质量/成本比较尚未完成。没有新增 HTTP API 或付费/实盘端点。

## 已执行验证

| 检查 | 实际结果 | 边界 |
|---|---|---|
| `.venv/bin/python -m pytest` | **1687 passed, 1 skipped, 1 deselected, 24 warnings，11.15 秒** | 公开回归摘要见 `public-regression.txt`。可选 AWS 依赖缺失；在线 integration 被排除。该套件未覆盖 BUG-V03-001，整体绿灯不等于 v0.3 验收通过。 |
| 全仓 Ruff | 通过 | [日志](final-ruff.txt)。 |
| JS 语法 | 7 个脚本全部通过 | [逐文件结果](final-js-syntax.json)，仅语法检查。 |
| 差异检查 | 通过 | `git diff --check` 只覆盖 Git 已追踪差异；新增源码另做清单与 patch 检查，见文档收尾检查。 |
| 文档收尾与累计补丁 | 需求及AI来源检查通过，累计补丁反向只读检查通过 | 本地文档与补丁检查。额外全文空白扫描发现HTML第145行尾随空白及README两处上游既有空白，保留记录，不声称所有未追踪文本均无空白问题。 |
| 起点一致性 | 起点 21 个测试文件 hash 全部未变；原行情、预测脚本与演示数据未变 | [变化清单](changes-since-start.json)。起点只有 hash，没有全部原始字节，不声称有 v0.3 专属文本 diff。 |
| 结构化渲染探针 | **失败，复现 BUG-V03-001** | 使用请求 200 的原样生成 fixture helper，运行时绑定实际上游 schema/render；这是 QA 探针，不是已接纳回归测试。 |
| 浏览器集成 | 三股票、多修订、重复/非法导入、失败报告、长中文、主题、行情不一致、引用、两种导出、预测播放/刷新及故障保留旧内容已实际操作 | [视口](browser-metrics.json) 与截图。基于合成数据；不是正式业务评估。 |

浏览器实际观察：初始 demo 加四份夹具共五份，重复导入数量不变；随后长中文 MSFT 修订共六份。失败导入保留旧选择；NVDA failed 保持真实夹具状态。Claim 短按钮定位完整 ID，证据详情显示完整引用。恶意 HTML 显示为文本，未生成注入图片，`javascript:` 来源没有可点击 anchor。默认日报选择 AAPL revision 2、MSFT revision 1、NVDA failed；手选 AAPL revision 1 并排除 MSFT 后导出只含两份。JSON 下载解析内容与原导入夹具相等。

临时关闭自有静态服务后，预测刷新显示“刷新失败，保留上次数据”，原图及来源保留；重启后恢复。源码审查和本地服务器观察没有模型请求；没有拦截 TradingView iframe 的全部网络流量，不能声称完整网络抓包。静态服务只负责文件 GET，不连接研究后端。

CSS 视口为桌面 **1440×1000**、手机 **390×844**，记录的页面 scrollWidth 分别 1425、375，没有页面整体横向溢出。截图净内容宽度受浏览器边框/滚动条影响，手机 JPEG 为 **375×812**；桌面完整截图为 **1424×2328**，顶部截图为 **1425×990**，不是同尺寸视口截图。手机截图开始于约 135px 滚动位置，桌面为 0；临时视口最终已 reset。逐图尺寸及hash见 [截图索引](screenshot-index.json)。

- [桌面深色完整截图](screenshots/desktop-dark.jpg) / [桌面顶部](screenshots/desktop-dark-top.jpg)
- [手机深色](screenshots/phone-dark.jpg) / [手机浅色](screenshots/phone-light.jpg)
- [手机合成预测](screenshots/forecast-phone.jpg) / [刷新失败保留图表](screenshots/forecast-refresh-failure.jpg)
- [默认合成日报](daily-default-synthetic.md) / [历史修订合成日报](daily-history-synthetic.md) / [原样 JSON 下载](download-nvda-synthetic.json)

## 当前审阅对象与来源

[源码/测试清单](source-test-manifest.json) 覆盖 EvidenceGuard、上游源码/测试、课程测试及两项集成配置，共 230 个文件。它绑定本次候选，不批准任何文件。[起点变化清单](changes-since-start.json) 列出 8 个修改、6 个新增；GitHub 候选分支的累计应用和测试差异 对比导入基线 commit `4419f129e498b7a30eb9fd397cf1515552ebff04`，其上游固定 SHA 为 `9fa1196fffbcfd9de5146d2dd2869df84ab99838`。累计 diff 包含早于 v0.3 的增量，不能当作本轮专属变更。普通 Git diff 不显示未追踪的 `src/`、`test/`，所以不能单独作为审查范围。

完整来源链和本地审阅包保存在项目本地。公开的源码/测试清单绑定现有文件字节，当前材料用于审阅。

后续动作集中于 [pending-actions](../../pending-actions.md)。在 BUG-V03-001 修复、缺失测试经合规生成并通过、重新冻结和学生真实审阅之前，不执行付费 pilot 或沿用旧正式实验结果。
