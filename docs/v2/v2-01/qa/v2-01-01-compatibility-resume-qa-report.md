# V2 01 / 1.1.1 续作独立 QA

结论：**BLOCKED**。隔离环境的合成语义回执支持功能探针通过；安全构建及部署门禁未满足，不能判定本 Task PASS，也不能进入 1.1.2。

## 问题

- **V201-111-QA-002 / P1 / OPEN：安全构建来源未证明。** [续作记录](../v2-01-01-compatibility-resume-report.md)的固定旧包没有可核验的构建 headers/安全修复证明；[pg_search v0.26.6 根 Cargo.toml](https://github.com/paradedb/paradedb/blob/v0.26.6/Cargo.toml)固定 pgrx 0.19.3。[PostgreSQL 17.12 安全说明](https://www.postgresql.org/docs/release/17.12/)要求重建 C 扩展以获得 composite datum 修复的完整保护，部分扩展需要修改源码；[pgrx 0.19.4 说明](https://github.com/pgcentralfoundation/pgrx/releases/tag/v0.19.4)要求用修复版 pgrx 和修复后的 PG headers 重建，且生成物不能加载更早小版本。原依赖重编译或隔离加载成功不能证明完整保护。这是未满足安全门禁及潜在风险，并非已证实该项目业务路径可利用，也不能仅凭包发布日期断定构建不安全。
- 原 **V201-111-QA-001 / P1** 是旧 PG17.6 组合缺少 `pg_mblen_cstr` 的历史事实。本次新 PG17.12 环境成功加载同一 `.so`，并未修复或重新验证旧 PG17.6 组合；原编号状态由主 Agent 裁决。

## 独立核验与边界

- 本地 `Get-FileHash` 核对 [JSON](../evidence/v2-01-01-resume-evidence-20261117/semantic-evidence.json) 为 `125f95f5d350bbd17471ea8817b6a865992283018a12caab384b3e87119777bc`；执行入口为 `7a4f7ede10b433879479a9c4e502139a36e666a52513b99cb899c2d88099b750`，语义源为 `bc9fbc05b2b15ac1aff00da41c29f44dbf4e24e3c7825cc5e799f3bc9d9b96d1`，均与记录一致；工作区续测入口与执行源相同。
- 阅读实际执行源和回执：隔离容器无网络/端口，单独卷，实际 PG 170012、vector 0.8.7、pg_search 0.26.6，旧 `.so` 摘要一致。Jieba、英文标识、文本 ID、domain/版本过滤后 Top 1、PREPARE 参数、更新/删除回滚和提交后变更均有实际 SQL 与断言；无过滤 Top 1 为 `deny-1`。真实 REPEATABLE READ 连接先读 Dense，另一连接提交替换，再在原快照读取 Dense/Sparse 并断言旧 ID，新事务确认新 ID 和旧来源失效。隔离实例重启前后 postmaster 时间不同且两路结果保留。回执 child PASSED、cleanup_complete=true。该证据是小型合成语料和精确向量查询，不证明生产检索质量或应用集成。
- 清理仅按本次唯一标签查询并删除容器/卷，回执两次最终列表为空；未构建或删除镜像。主 Agent 实际远端命令退出 0，另观察正式容器 ID、healthy 和 StartedAt 前后一致；该观察不是全表数据摘要。本 QA 未自行远程连接、写库或重启正式实例。
- `rg` 显示新增契约仅定义于 `app/knowledge/models.py`，应用运行模块无使用，测试有引用；保持未激活。Implementer 报告的本地 7 passed 是已有受控测试，本 QA 未重复执行，不作为真实库或模型验证。
- 本 QA 本地以项目 `.venv` 直接读取 JSON 确认 status、child 和清理结果；首次使用 PowerShell 文本管道解析因编码转换失败，改为 Python UTF-8 直接读文件后成功，该失败不影响原始文件或摘要。未进行新的真实 PG、模型或全量回归。

建议优先取得厂商可追溯的安全重构建与 headers 证据；否则先单独评估构建资源和固定源码适配 pgrx 0.19.4 的可行性，再在独立环境验证修复产物及完整门禁。任何正式启用及重启均按项目既有授权与部署流程处理。
