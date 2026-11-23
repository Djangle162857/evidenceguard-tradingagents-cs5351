# Verification constraints

每条需求均有正负验收；每条不变量有能检测其违反的测试。测试关联需求ID，不共享实现私有oracle，不以mock通过宣称真实API兼容。

结构层：需求Schema、唯一ID、交叉引用、权限/接口契约、AI-use和批准时序。
回归层：全部历史离线测试与新增测试；live独立运行且版本绑定。
行为层：语义支持、实用性、可用率、完整用量、性能和零安全逃逸。

六类GitHub必需状态：test-approval、static-analysis、requirements-schema、semantic-evaluation、regression、ai-use-log。为每类留真实拒绝与修复通过链接。主分支保护要求PR和全部检查，无单人无法满足的他人review要求；用户人审证据仍须对具体hash核验。

测试批准对象包括测试计划、具体场景、fixture与测试源码hash；应用实现开始前冻结。若准备阶段尚未生成测试源码，检查点1不得声称该源码已审过；先补齐具体测试再请求批准。

语义门禁对prompt/model变更要求新运行证据；文档变更可由规则判为不适用，但必须有可审计的变更分类。CI无课程密钥，不因存在workflow而宣称保护已生效。
