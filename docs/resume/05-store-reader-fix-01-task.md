# 05 / Task5.3.1 / 05-QA-001 定向修复

2026-11-14，主Agent退回原Implementer。必读docs/question/05-store-reader-qa-report.md，保留原FAIL报告及两份原QA探针，不覆盖历史。当前阻塞05-QA-001/P2：真实[] JSONB在已安装Store3.2.0 _row_to_item默认JSONloader阶段抛orjson.JSONDecodeError，Manager的object guard来不及执行，编译订单图可选读异常打断。其余54项独立定向通过，原208全量通过不能替代该风险修复。

只修实际Store解码/Manager分类边界，不泛化吞所有ValueError/编程错误、不改第三方源码/依赖版本、不弱化QA断言或直接绕Store读取。准确转换已证实的JSON解码损坏为failed/memory_profile_invalid，经同Executor可选memory_read_status unavailable继续正常核心业务；取消仍传播、unknownschema/partial/scope/预算原语义保持，Manager/Reader不得绕Policy。

新增或扩展已有真实PG回归：仅自己的唯一profile改为非objectJSON，跑实际编译订单准备路径，验证默认呈现继续、工具明确failed/memory_profile_invalid、无原始损坏值/异常泄露。其他三个Reader/资源生命周期/隔离保持，在线身份/全部迁移checksum及全public行集列定义保护、精确清理。不得开发库写/SSH/PG重启/.env/006变更。必要受影响测试、最终完整真实PG门禁、Ruff/格式，若直接依赖清单变化同步并pipcheck，不盲升级。

修复记录必须写docs/resume/record/05-store-reader-fix-01-report.md，关联阶段05、Task5.3.1、05-QA-001及本提示词，列修改位置/根因/实际测试和未闭环；开发交付可追加修复链接不得删旧失败。完成停止交主Agent原QA独立复测，不自行标已关闭，不进入5.3.2，不Git/Bridge/另派Agent。
