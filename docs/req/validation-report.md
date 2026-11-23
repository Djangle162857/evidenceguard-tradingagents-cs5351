# 需求文档校验记录

校验日期：2026-11-19。范围：本次生成的需求文档结构、交叉引用及 Schema 拒绝规则。
**结果：文档校验通过。边界模块及离线回放已经实现；完整业务验收、在线实验、CI 和具体人工批准仍未完成。**

## 已执行检查

- requirements.yaml 通过 JSON Schema Draft 2020-12；Schema 自身也通过元校验。
- product.yaml、requirements.yaml、ai-use-log.yaml 均成功解析。
- 26 个需求 ID、18 个来源 ID、10 个协议 ID 和 52 个计划验收 ID 无重复。
- 需求来源、关联需求、协议、PRD 目标与优先级引用全部有效；Markdown 中 26 个需求编号与注册表完全对应。
- 本地文档 / PDF 链接存在；所有固定 SHA 的上游文件路径已在检查用克隆中确认存在。未声称重新在线检查所有 Canvas 页面。
- 实验数量一致：3 个任务 × 2 次重复 × 2 组 = 12 次运行；任务股票属于初期支持清单。
- 需求注册表保持 proposed/not_run/planned，完整协议未验收；已执行的组件测试另见docs/progress.md，不用局部通过冒充全协议通过。
- Must/Should 清单与注册表一致：25 Must + 1 Should。

## Schema 拒绝规则检查

以下六种仅在内存中修改的无效注册表均被 Schema 拒绝。这些是文档校验器的校验，不是应用功能测试：

- 缺失fit_criterion
- 非法MoSCoW值
- 类型与ID前缀不匹配
- 已验证却无证据
- 布尔指标使用数字阈值
- 不变量容许一次违反

## 当前需求数量

| 类型 | 数量 |
| --- | --- |
| functional | 7 |
| quality | 3 |
| performance | 1 |
| cost | 1 |
| security | 1 |
| invariant | 6 |
| governance | 7 |

## 仍待完成

- 用户已确认单人、课程API和95美元上限，基线已导入；具体测试源码和安全代码人审仍待记录。
- 完成真实数据 fixture、上游集成与协议级验收；52 个 AT 编号不等同于已全部验证。
- 运行兼容性 pilot、正式成对实验和性能测试，再据实报告目标是否达到。
- 实现并验证真实 GitHub 门禁与分支保护。Schema 本身不能验证批准真实性、测试存在或业务指标通过。
- JSON Schema 不表达 ID 全局唯一及跨文件链接真实性；本次另执行了上述集合与路径校验。后续 CI 应保留这些检查。

## 使用的工具

- Python 3.12、PyYAML 6.0.3、jsonschema 4.26.0。文档解析依赖安装于临时目录，未改变应用依赖。
- 此校验程序为Codex编写的临时文档结构检查，不属于业务源码；应用/上游测试和OpenCode调用另有实际执行记录。

## 被校验文件的 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `docs/req/requirements-analysis.md` | `55ef8c76ae576ea4efe5a4d3a281b6bcb42a36c0adf6322a761ef5cc73bd00b9` |
| `docs/req/product.yaml` | `078835b30a30d5ab5c17bbe1464a4fe5ce3e93a76a8c48e6d5edda6c0e9355ab` |
| `docs/req/requirements.yaml` | `cddb8faab2eb990dbc39f19018c7a866d5cbb437d7f91f846fe0b9ad34bd5c7b` |
| `docs/req/req-schema.json` | `47fd3af7336cc80129ae82a48099e308ee3e9412c0b8c0edfe1b2649228ebbbd` |
| `docs/req/baseline-review.md` | `fe8c9ada94c5c041cfa0513f9fc9574e5c613b828e0f23cd1f0eb7bdfda5728d` |
| `docs/ai-use-log.yaml` | `1079a2b0da85163e341ef1934b13d71fd7050cb12b65ec7d4ce4e27fca40021c` |
