# V2 01 Task 1.1.1 独立 QA

日期：2026-11-17。结论：**FAIL / BLOCKED**。固定候选的加载不兼容证据成立，不能进入1.1.2；本结论不代表阶段验收。

## 范围与证据

依根AGENTS.md最新授权、Task执行单、批准设计第1/3/6/7节验收；阅读候选模型、原Repository/ingest和切分输入构造、实际执行源、增强探针、交付报告及JSON。QA仅新增本报告，没有修改业务代码、测试或原证据，没有运行远端构建、数据库写入、模型或Git变更。

实际执行源 `docs/v2/v2-01/evidence/v2-01-01-compatibility-executed-20261117.py` 字节SHA256经QA独立计算为 `8d9b8205cf52dd858b4712368f49f2bcccdffebf7a8b68c8f2a967609d749a8c`，与主Agent派发和交付一致。增强版 `scripts/verify_v2_01_compatibility.py` 包含后续语义探针，不视为本轮VM执行源。

## 问题

**V201-111-QA-001 / P1 / OPEN：固定官方二进制组合无法预加载。**

位置：`docs/v2/v2-01/evidence/v2-01-01-compatibility-evidence-20261117.json:205`；实际执行源`:203`配置预加载、`:212`失败退出。候选固定PG17.6 Bookworm镜像和服务器/客户端17.6-2.pgdg12+1，vector0.8.7-1.pgdg12+1，官方pg_search0.26.6包。JSON命令序列中构建退出0，apt日志显示0 upgraded；随后的独立候选初始化日志明确报 `undefined symbol: pg_mblen_cstr` 并关闭服务器。包摘要与固定候选值一致，体积54,276,840字节。不是仅因就绪超时推测不兼容。

复现入口为交付报告中的远端命令，使用上述留存执行源及固定包；该脚本先检查原库、构建隔离镜像，在独立卷、无网络、无主机端口容器设置 `shared_preload_libraries=pg_search` 后触发失败。本次QA审阅留存真实执行记录，未重复耗时构建，不宣称独立远端重现。结论仅适用于该固定二进制组合，不证明其他版本或重新编译也失败。不授权升级PG或切换SQL BM25。交主Agent裁决后续方案；需要修复时退原Implementer再独立复测。

## 契约与探针审查

- 新模型仅定义，应用目录搜索未见运行路径引用；原来源四元组、Document/Chunk、EmbeddingProfile及V1 SearchResult未改。Hybrid结果必填版本、模式、Profile、水位和候选，原解析器通过extra=forbid拒绝V2结果。未将Sparse/BGE配置加入文档版本或向量输入。
- Sparse固定版本/字段/Jieba参数、两路独立分数及RRF/BGE含义、完整输入预算与发布/回填/锁序/回滚说明符合当前候选契约范围；BGE revision只是必填字段，没有真实下载验证。版本解析单测不能证明正式工具重放已接线。
- 实际执行源对原容器仅查询；清理目标是本轮唯一命名候选资源，不触及原卷。JSON前后容器ID、启动时间、挂载、PG/vector包及两库各13张public表行摘要/列定义摘要完全相等，QA重新比较为True。候选容器/卷/镜像删除命令均退出0，后续本token资源枚举为空。清理结论依留存执行证据，不等同QA新远端盘点。
- 增强探针包含中文/英文标识符、过滤前Top K、PREPARE参数、事务更新/删除/回滚、跨连接REPEATABLE READ、来源失效及重启检查。源码审查未发现使本次加载失败结论失效的实质问题；这些SQL、扩展API、快照断言及重启流程均尚未通过真实执行，不能据此冻结其兼容性为通过。

## QA实际检查

使用项目`.venv`：

| 检查 | 结果 |
| --- | --- |
| `python -m pytest tests/test_knowledge.py -q` | 7 passed in 7.90s，退出0，无skip |
| `python -m ruff check app/knowledge/models.py scripts/verify_v2_01_compatibility.py tests/test_knowledge.py` | All checks passed，退出0 |
| `python -m ruff format --check`（同三文件） | 3 files already formatted，退出0 |
| 留存执行源SHA与JSON保护快照比较 | SHA一致；protected_before == protected_after |

## 未验证与停止点

真实CREATE EXTENSION、Jieba语义、参数化、text Chunk ID、过滤/排名、事务/并发快照、最终来源及重启持久化均未执行；未运行真实Qwen/BGE、Hybrid质量或完整V1回归。本Task增量未激活，未发现另一个需要业务修复的已证实问题。

外层传输目录 `/tmp/agent-v201-compat-Fc9igj` 尚由主Agent保留，不属于候选资源清理完成范围。QA完成后由主Agent核对绝对目标并精确清理。旧遗留及其他V2设计不属于本Task，不回滚。当前停止，等待主Agent复核/用户裁决，不进入下一Task。
