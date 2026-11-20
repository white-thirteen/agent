# V2 01 · Task 1.1.2 实现记录

本记录交独立 QA 与主 Agent 复核，不代表 Task 或阶段验收。正式数据库未执行本 Task 的迁移、回填、建索引或激活。

## 实现

- 追加 `007_knowledge_sparse.sql`：允许历史 Chunk 的派生字段为空，建立单行索引状态和正整数水位，不安装任何扩展；应用预期 schema 版本同步至 7。先迁移再启动新版应用。
- `search_text` 固定为 `title + "\n" + (section or "") + "\n" + content`，不改变正文、来源哈希或向量。发布写入与文档版本、Chunk 和向量同事务；删除同事务推进水位。所有发布、删除、回填和激活先取得全局知识发布事务锁，发布和删除随后取得原文档锁；推理仍在事务外。
- `prepare_sparse_knowledge.py` 提供显式 `backfill`、`activate`、`check`。回填仅修改派生输入；激活前校验全量当前 Chunk 数量和派生内容、固定 PG/扩展版本、中文配置和映射，再建立并核验单字段 BM25 索引，最后同事务更新 Profile、索引身份、就绪状态和水位。重复回填无变更，已就绪的重复激活不推进水位；索引丢失后重建是一次新激活。就绪检查重新校验上述条件，拒绝失效、同名错误或部分索引。写操作禁止 `app_env=production`。
- 无 Hybrid、RRF、BGE 或 Graph 接线；V1 Dense 检索及来源校验沿用原路径。

## 操作边界

维护窗口中按 `python -m scripts.prepare_sparse_knowledge --target development backfill`、`activate`、`check` 分别执行，使用项目 `.venv`；测试目标可用 `--target test`。这只是操作说明，不构成本轮对任何数据库的执行授权。扩展与 `public.chinese` 必须预先按 1.1.1 固定镜像及映射配置；命令不会安装扩展或修改配置。SQL 可检查已安装扩展版本、解析器和映射，无法直接证明 SCWS 共享库及词典文件版本与字节，操作者须在激活前对照 [1.1.1 验收和产物 SHA256 清单](v2-01-task111-acceptance.md)核实运行镜像、库和词典；中文查询验证不代替该检查。

回滚时先停止新 Hybrid 知识任务并等待活动任务结束，恢复 Dense 装配和旧工具契约，再在维护窗口处理不再使用的派生索引、字段和状态；保留权威文档、原向量、来源身份及旧迁移，不使用 `DROP EXTENSION CASCADE`。水位不是正文历史备份。

## 实际验证

- `.\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py tests/test_sparse_task112_postgres.py -q`：7 passed，1 skipped；当时未设置专用隔离库变量，数据库测试按预期跳过。
- 设置 `AGENT_SPARSE_TASK112_DATABASE_URL` 指向专用隔离库后，`.\.venv\Scripts\python.exe -m pytest tests/test_sparse_task112_postgres.py -q --tb=short`：1 passed。测试在线核验数据库名 `agent_sparse_task112_test`、用户 `agent_sparse_task112`、数据库注释 `codex-task112-7c41`，只在空库创建并精确删除自己的知识表。环境为隔离 PG17.12/vector0.8.7/pg_textsearch1.5.1/zhparser2.4，测试在 006 写入历史行后执行 007，检查派生回填及重试、向量与来源身份不变、未完整拒绝激活、中文 BM25 命中、失效及部分索引拒绝、重复激活、替换事务失败回滚、发布锁并发阻塞、替换和删除水位及词项可见性。向量为受控测试数据，未调用真实 Qwen。
- `.\.venv\Scripts\python.exe -m ruff check app/knowledge/sparse.py app/knowledge/repository.py app/infrastructure/postgres.py scripts/prepare_sparse_knowledge.py tests/test_sparse_task112_postgres.py`：通过。
- `.\.venv\Scripts\python.exe -m ruff format --check app/knowledge/sparse.py app/knowledge/repository.py app/infrastructure/postgres.py scripts/prepare_sparse_knowledge.py tests/test_sparse_task112_postgres.py`：5 files already formatted。

隔离实例上的无 pg_textsearch 环境迁移和 V1 回归由主 Agent 执行，结果以其独立记录为准；本记录不将其计作实现者已完成的验证。正式应用级 Dense 回退、Hybrid 同快照检索、质量和阶段完整回归不在本 Task 内。独立 QA 待执行。
