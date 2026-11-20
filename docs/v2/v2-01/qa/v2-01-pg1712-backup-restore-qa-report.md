# PG17.6备份与独立PG17.12恢复演练：独立QA

2026-11-17。**PASS，仅限本轮备份、可靠副本与独立恢复演练。** 未升级/重启原库，不关闭原PG17.6兼容P1，不批准切换或1.1.2。没有新增已证实阻塞问题。

## 范围及证据

阅读根规范、新演练报告、演练脚本完整相关备份/恢复/SDK路径、脱敏阶段JSON、退出码和最终保护回执。独立QA新增本报告及[QA实际证据](v2-01-pg1712-backup-restore-qa-evidence.json)，未修改既有报告/证据、业务代码、配置、迁移或Git。权限继承父会话，只读是行为约束，并非独立只读沙盒。

HEAD实际为232469acf7e576883e84d58c5a140fd598d9b00e，分支v2。独立重算`.git/codex-backup-restore-protected.json`的456条保护路径，全部符合预期；其中3个原已删除文档的预期值是null，按缺失值比较，没有误报为新删除。演练源码SHA256确为 `72e82a48d034d75f659ddb729fea9cde8b7e404a4aa4f1d43264d62a2d7ecd1c`，与成功阶段JSON一致。

## 独立实际结果

| 检查 | 实际结果 |
| --- | --- |
| 仓库外private-manifest字节SHA | `5ad6710a00f03f805f1479c2ac00a884e92548087249199da1d541a4cc12c46d`，与回执一致 |
| 逐一重新读取141个私有文件 | 406,442字节；全部大小/SHA匹配，0不匹配；未输出或复制私密内容到仓库 |
| 项目.venv Ruff/format/AST | check通过、1 file already formatted、UTF-8 AST解析通过 |
| 候选实际只读连接 | 127.0.0.1:15633，先确认170012及postgres comment=`restore-rehearsal:228a7f5b8d92`；SQL连接设置default_transaction_read_only=on |
| 两库原业务行 | 每库5订单完整行hash匹配备份；approvals/refund_requests/sessions/knowledge等仍为空且摘要匹配；三迁移表摘要匹配，行数6/10/4 |
| 候选唯一schema向量/BM25 | 每库2个vector(1024)，自距离0、正交距离1；真实中文退款检索命中restore-chunk |
| 候选新进程SDK读取 | 实际退出0，两库普通角色、跨库CONNECT拒绝、迁移checksum、原serializer/Checkpoint ID/pending writes及Store值均通过 |
| SDK受控读取前后比较 | 两库各13个public表完整行hash全部相同，包含Store updated_at/expires_at；TTL非NULL行数前后均0 |

当前候选每库checkpoint_blobs/checkpoint_writes/checkpoints/store分别3/1/1/1行，属于已批准SDK夹具。它们与空源基线摘要不同是预期结果，不能宣称当前候选全表仍等于空源。两库向量/BM25夹具位于唯一schema，不是源知识向量恢复证据。

## SDK强只读失败与受控复核

第一次QA运行原sdk-read入口时额外设置PGOPTIONS强制SQL只读，实际退出1，safe_error_type=ReadOnlySqlTransaction，独立失败证据保留于QA证据中的qa-sdk-read.json。定位锁定Store实现 `.venv/Lib/site-packages/langgraph/store/postgres/base.py:285`：aget查询无条件带 `WITH updated AS (UPDATE store ...)` TTL刷新CTE，即使没有TTL行也被PG只读事务拒绝。这不是备份损坏或setup调用。

主Agent随后明确授权仅候选执行这一零匹配UPDATE。QA先只读确认两库全部Store行ttl_minutes均NULL和目标版本/token，再仅对SDK子进程撤除强只读限制，运行原sdk-read，不调用sdk-write/setup/seed。该次实际退出0。之后再次用强只读连接比较全部public完整行hash，前后完全相同，Store时间字段也包含其中。因此完整SDK读取在本受控调用中未改变数据，但它不是严格SQL只读接口；不把第一次失败隐藏或解释为原项目恢复失败，也未对原库放开写入。

## 源保护及恢复方法审查

源码使用每库exported REPEATABLE READ READ ONLY快照，将pg_dump与该库基线绑定，正确区分每库一致性与集群同瞬间快照。序列另核，globals/config前后比较，所有实际原库路径为只读；挂载列表仅规范化排列而保留全部字段。恢复使用独立网络/新卷，受限初始化秘密文件，原globals仅精确跳过一条bootstrap CREATE，其他字节保留；没有setup、REASSIGN OWNED或原迁移修改。

成功备份/恢复证据记录源码一致；wrapper备份成功和恢复退出码均0。初始恢复在添加夹具前比较全表行、schema/约束/索引、owner/ACL、序列、扩展及规范化全局角色等一致。QA没有重做备份或恢复；原源容器/启动时间/配置/角色/全部行和序列保持、原3卷和新卷保留，依据留存真实前后证据核验，不冒充本轮QA新远端盘点。

首轮Mounts顺序误报、失败15632连接及final helper重启后KeyError均独立保留。final-proof-v2通过同一候选container ID的事件证明前一次重启，没有把补采集相同启动时间说成第二次重启。QA此次读取的是已重启后保留夹具，并未再重启候选。

## 风险与停止点

- 源Checkpoint/Store/知识表为空；夹具验证持久化能力，未证明非空历史Checkpoint、待审批真实Task或原知识向量已恢复。原完整业务/Qwen/BGE回归未执行。
- C扩展17.12安全构建来源未确认，不能因加载成功宣称全部安全重编译要求满足。既有Store时序观察仍保留。
- 最终记录VM根盘只余1,308,536,832字节。报告已要求维护前准备并核验磁盘；实际升级前必须重新确认新卷/最终备份/恢复临时峰值容量并作为明确门禁，不能由本PASS推导可继续创建新卷，更不能删除旧卷腾空间。
- 备份及原3卷/新恢复卷继续保留。本轮含夹具的恢复卷不能直接上线。实际维护仍须停写、排空Task、最终双库备份、恢复核验和业务门禁；新库已接受写入后不能静默切回丢弃增量。

原数据库没有被本轮QA写入。完成后停止，交主Agent复核；原库升级、配置变更、Git及后续开发均不在本结论授权内。
