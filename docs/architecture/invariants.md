# 不变量与执行处置

状态：设计；测试和运行证据尚不存在。

| ID | 权威组件 | 必测违反 | 实际处置 |
|---|---|---|---|
| INV-001 无真实交易权限 | 工具白名单/runner | broker、buy、transfer等副作用请求 | 拒绝工具，不发请求，记录security事件 |
| INV-002 不合格/未审不能released | gate/review/publish | 未验证、验证器异常、无当前批准 | blocked/draft，非零退出，不导出有效发布标记 |
| INV-003 同run合资格证据 | evidence/claims/gate | 未来、时间未知、跨run、悬空证据 | 隔离证据，阻止受影响结论发布 |
| INV-004 预算原子约束 | budget/relay/runner | 并发超额、重复结算、usage缺失、停止后重试 | 不发新请求；未知用量保留预留；写终止原因 |
| INV-005 内容和批准不可静默覆盖 | contracts/review | 文件篡改、旧hash、配置或策略变化 | 新修订，旧批准失效，保留历史 |
| INV-006 输入不能扩大权限 | permission/context adapter | 新闻注入、工具注入、目录逃逸 | 视为数据，拒绝副作用，不改变白名单 |

所有不变量允许的违规发布/越权次数为零。监控字段包括run、attempt、requirement/invariant ID、拒绝原因、执行动作和状态；事件日志不含密钥和完整认证头。
