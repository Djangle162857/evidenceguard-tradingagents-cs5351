# Structural constraints

待检查点1批准。新增代码只进入Blueprint列出的模块及三个接入点；保留上游文件、测试和许可，不整仓格式化或复制源树。

每个模块/docstring关联需求与ADR/不变量；接口以architecture/interface-contracts为准。gate不能调用LLM判断是否放行；review不能替代gate；budget必须在调用之前执行且覆盖所有调用；数据和模型输出不能修改策略或权限。

代码、测试代码、应用prompt由OpenCode+课程模型生成及修改。Codex负责读代码、运行批准命令、整理需求/架构/QA文档；修复任务交回OpenCode。操作系统配置、凭据转移和临时预检工具不冒充课程应用代码或OpenCode生成物。

安全关键范围：预算/relay、证据资格、gate、review/hash、权限、外部目标和调用工厂。修改要有ADR、负面测试和真实用户对具体diff的人审。普通文档修订不能改变已批准阈值。
