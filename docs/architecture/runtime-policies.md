# Runtime policy catalog

| Policy | 触发条件 | 执行动作 | 输出状态/证据 |
|---|---|---|---|
| RP-INPUT | 配置、股票、未来截点或路径非法 | 外部请求前终止 | failed/input_invalid；请求数0 |
| RP-DATA | 无数据、源不可达、时间未知或未来 | 重试≤1；隔离不合格项，不编造值 | degraded/no_eligible_evidence |
| RP-OUTPUT | 卡片/结构化响应非法 | 最多1次计费修复；仍错则停止该链路 | degraded/invalid_output，草稿不可发布 |
| RP-BUDGET | 预留将超token、attempt、美元或期限 | 不启动请求；保存已得内容 | degraded/budget_exhausted |
| RP-USAGE | 服务端usage缺失、超预留或重启遗留请求 | 保留最坏预留，停止新增，人工核账 | blocked/usage_unknown |
| RP-RATE | 429或瞬时故障 | 受剩余期限约束的有界等待，最多1次显式重试 | 重试计入attempt和费用；失败仍留档 |
| RP-GATE | 引用、时点、状态或验证器异常 | 阻止有效报告发布 | blocked/draft，具体违规列表 |
| RP-REVIEW | 无批准、拒绝、旧hash或文件改变 | 拒绝publish，不覆盖既有版本 | draft/review_invalid |
| RP-SECURITY | 注入企图扩大工具、目录、端点或权限 | 拒绝操作，不跟随输入指令 | security事件，必要时cancelled |
| RP-EVAL | 缺任务/失败记录、版本或数据hash不一致 | 不生成“通过”汇总 | invalid_evaluation；失败留分母 |

本地期限到达后2秒内记录终止事件，不再发新请求。取消和超时不能证明提供方没有继续计费；最终以网关记录核对。仅打印错误而不改变运行状态/权限，不算执行了策略。
