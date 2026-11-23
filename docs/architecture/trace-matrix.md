# 需求—组件—测试—监控追踪（设计）

组件级实现与测试已经逐步完成，当前执行结果见docs/progress.md和检查点源码清单。下表仍映射完整验收协议；组件通过不代表全部DS协议或正式业务验收完成。

| 需求 | 组件 | 数据集/验收 | 运行监控 |
|---|---|---|---|
| FR-001 | contracts/runner | DS-CONTRACT | manifest_hash/input_rejected |
| FR-002 | evidence/data adapter | DS-EVIDENCE | qualified/excluded evidence |
| FR-003 | claims/claim-turn | DS-DEBATE | invalid_cards/conflicts/stop_reason |
| FR-004 | gate | DS-SAFETY | gate_status/violation_ids |
| FR-005 | budget/relay | DS-BUDGET | reserved/settled/unknown/stopped |
| FR-006 | evaluation | DS-LIVE/DS-REPLAY | paired records/failures/usage coverage |
| FR-007 | review/publish | DS-REVIEW | review_hash/publish_rejected |
| QUAL-001 | evaluation/manual rubric | DS-LIVE | support/annotation/recheck coverage |
| QUAL-002 | evaluation | DS-LIVE | usable_rate/rubric/failure denominator |
| QUAL-003 | replay | DS-REPLAY | normalized_match |
| PERF-001 | gate/perf | DS-PERF | p95/hardware/input size |
| COST-001 | budget/evaluation | DS-LIVE | all-attempt token ratio |
| SEC-001 | logging/transport/export | DS-SAFETY/DS-GOV | secret canary count |
| INV-001 | permission/runner | DS-SAFETY | rejected side effects |
| INV-002 | gate/review | DS-SAFETY/DS-REVIEW | illegal_release_count=0 |
| INV-003 | evidence/gate | DS-EVIDENCE/DS-SAFETY | invalid_reference_count |
| INV-004 | budget/relay | DS-BUDGET | overspend/after_stop_count=0 |
| INV-005 | contracts/review | DS-REVIEW/DS-REPLAY | hash_changed/approval_invalidated |
| INV-006 | permissions/context | DS-SAFETY/DS-GOV | privilege_escalation_count=0 |
| GOV-001 | registry/schema/trace | DS-GOV | completeness/valid references |
| GOV-002 | approval check | DS-GOV | approval hash and chronology |
| GOV-003 | CI/protection | DS-GOV | six required jobs and actual blocking |
| GOV-004 | AI-use/session evidence | DS-GOV | source/prompt changes with logs |
| GOV-005 | context/permission | DS-GOV | reinjection/isolation/denials |
| GOV-006 | QA records | DS-GOV | review/debt/bug record completeness |
| GOV-007 | delivery check | DS-GOV | reproducibility/D1-D9/ZIP/video |
