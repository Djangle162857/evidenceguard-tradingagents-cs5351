# 检查点2：后端实现与离线验证审查包

日期：2026-11-19。状态：**代码与证据已备妥，真实人工审阅待进行**。本文件是Codex的交付说明，不是学生批准。

## 实际完成

后端沿固定TradingAgents上游图工作，增加manifest、证据时间/原文hash台账、五角色claim-turn、独立门禁、原子预算、hash绑定审阅发布、冻结快照、离线回放和成对评估接口。上游Python改动仅为GraphSetup可选boundary；默认路由保留。CLI已支持snapshot、run、evaluate、replay、inspect、review；evaluate只准备计划，完整成对执行当前为Python callback接口。

应用、测试和应用提示通过本地OpenCode及课程模型`CS5351/DeepSeek-V4-Flash`生成与修正。Codex编排、审查、运行检查和编写文档。真实生成、失败和补丁来源见[源码清单](../architecture/source-provenance.json)、[六份会话](../ai-sessions/index.md)、[缺陷记录](../bug-diary.md)。会话初稿不是最终源码，原始失败没有被删除。

## 本轮验证

| 检查 | 真实结果 | 范围 |
|---|---|---|
| 完整离线回归 | 1,617 passed、100 subtests passed；1 skipped、1 deselected；10.88秒 | 上游1,412 + 新增205；SDK/行情/provider使用mock或合成数据 |
| Ruff | 通过 | 新包、离线测试、修改的上游setup.py |
| 新CLI测试 | 4 passed | 快照回调、配置、实际图草稿输出、非法快照在模型前拒绝 |
| 评估测试 | 7 passed | 12行网格/顺序、快照身份、篡改、失败权威、预算停止和记录保留 |
| CLI evaluate smoke | 输出固定12行和计划hash | 合成快照；无模型调用 |
| 需求文档 | 26需求及交叉引用通过，6种非法Schema输入被拒绝 | 文档检查；不是26项业务验收通过 |

完整回归的一个skip是可选`langchain_aws`未安装；deselected为在线integration。警告如实保留。历史输出与 hash 记录保留在本地审查包。

`checkpoint-2-manifest.json`冻结本次后端源码、测试和关键审查材料hash。`backend-diff.patch`包含相对本地导入基线4419f12的后端源码/测试改动，含新文件。前端正在另一聊天单独开发；`src/evidenceguard/web/`和ADR-004不属于本次后端审查范围。本包不覆盖随后发生的源码修改。

## 审查重点

1. [contracts/evidence/claims/gate](../../src/evidenceguard/gate.py)：来源时间未知或未来被排除；fact有合资格引用；门禁不调用模型。结构有效不保证语义支持。
2. [budget/transport](../../src/evidenceguard/transport.py)：精确课程端点与模型；每次HTTP请求双台账预留/结算；未知usage保留预留并停止。开发55美元与应用40美元的固定分配合计最高95美元；本地累计费用不是账户剩余额度查询。
3. [review](../../src/evidenceguard/review.py)：发布时重建门禁和业务hash；仅当前hash的真实批准可以发布；fixture批准只在测试存储存在。尚未创建任何真实批准或发布。
4. [integration](../../src/evidenceguard/integration.py)与[ADR-003](../architecture/adr/ADR-003-upstream-context.md)：候选会丢弃普通上游提示细节，保留tool协议；有损压缩是明确的评估混杂因素。
5. [evaluation](../../src/evidenceguard/evaluation.py)：状态/hash只采信产物顶层；失败全部留档；预算停止后未运行行仍保留；不生成真人语义标签。

## 后续实验范围与退出条件

真实审阅后先做小规模兼容性pilot，仍走课程端点和现有预算边界；不切换provider、不充值、不交易。pilot用于确认工具/结构化输出与失败留档，不能混入正式12次结果。随后冻结真实AAPL/MSFT/NVDA快照、候选commit、配置和顺序，按[测试计划](test-plan.md)执行两组各6次，失败全部保留。

候选至少5/6可用，成功数不少于baseline；共同可用标准为完成、≥1重要事实、支持率≥0.95、rubric≥4/5；候选另须gate passed。baseline不因缺少新schema自动判为语义失败。20% token节省是Should，未测或未达照实报告。唯一学生匿名化标注并间隔至少24小时复核，不制造第二位标注者。改变安全边界或正式冻结协议需另作具体审阅。

## 仍缺的真实行动与工程工作

| 项目 | 当前状态与责任 |
|---|---|
| Human-only `.opencode/rules.md` | 学生亲自建立；建议文本在`docs/code-governance/human-rules-proposal.md`，agent不代建 |
| 当前具体源码/测试审阅及实验授权 | 学生审阅本包manifest对应内容后作出真实决定；不能补造实现前逐件预批准 |
| GitHub六项检查与保护 | 尚未完成；现有上游CI不等于课程六项阻断证据 |
| 完整DS-SAFETY/DS-PERF/DS-REPLAY等协议 | 组件测试已执行，238条catalog不等于238项协议验收已完成 |
| 真实pilot、12次业务运行、标注与复核 | 尚未执行；需先完成具体审阅 |
| 正式Report.md、300–500词反思、10分钟MP4及ZIP | 未完成；写作与演示准备见`docs/delivery/`，反思及讲解需真实学生参与 |
| 展示报名 | 11月20日事项，尚无完成证据；不能由代码实现推断已报名 |

## 为什么实验仍待审阅

[AGENTS.md](../../AGENTS.md)明确要求：

> Real approvals of specific current hashes, Human-only edits and required student annotations remain human actions.

[执行计划](../execution-plan.md)检查点2要求“用户审阅实际安全diff、ADR、离线证据和实验协议，批准业务pilot及正式实验”。本包已经把该动作所需的具体内容备妥；先前“直接开始工作”记录的是启动授权，没有被改写成对未来代码的审阅或正式实验批准。此前缺失的实现前精确测试预批准也不能靠本次事后审阅补成已经发生。
