# V2 01 Task 1.3.2 检索质量实施记录

**首次全量 BGE 质量收益未通过。** C 的 Recall@10 达目标，D 的 MRR@3 提高，但 D 的 nDCG@3 从 0.9606 降至 0.9233，低于冻结目标。下文保留首次实施及原始结果。用户已正式接受通过复验的局部策略，见[Task 1.3.2 验收归档](v2-01-task132-acceptance.md)。

## 夹具与方法

隔离 PostgreSQL 17.12/vector 0.8.7、pg_textsearch 1.5.1、zhparser 2.4；目标和 database comment 在守卫及脚本内核验。原六篇各一 Chunk，新增 12 篇相近主题背景文档（共 18 Chunk，候选竞争超过 10）。在任何排名之前冻结 Q01–Q24、全文、来源 SHA256、切分版本、完整 Chunk 身份及逐题 0–3 qrels。固定文件 SHA256 为 `404b70e8732b6c7be1eedeae97055c1763643daf12a382853d21794b4665d2df`，详见 [fixture.json](v2-01-task132-evidence/fixture.json)。Q01–Q19 各一相关 Chunk，Q20 两个部分证据，Q21–Q24 无答案；所有组使用 knowledge:read、domain=None、同语料与查询。

固定顺序 Q01→Q24；Qwen 与 BGE 分进程顺序执行，各预热一次，五轮真实请求分别 120/120 成功。各题五轮候选与 BGE 排序一致，因此以下按首轮每题一次宏平均；C/D 的 Top10 身份逐次相同。各组每个候选的原始身份、内容与分数见 [Qwen 回执](v2-01-task132-evidence/qwen.json)、[BGE 回执](v2-01-task132-evidence/bge.json)，[首轮结果](v2-01-task132-evidence/metrics-first.json)独立保留。RRF 使用现有 `fuse`，数据库使用现有同快照双路检索，D 使用真实 BGE 原始分数排序；无答案题不计入质量分母。

| 组 | K | Recall | MRR | nDCG |
| --- | ---: | ---: | ---: | ---: |
| A | 3 | 1.0000 | 0.8833 | 0.9145 |
| A | 5 | 1.0000 | 0.8833 | 0.9085 |
| A | 10 | 1.0000 | 0.8833 | 0.9142 |
| B | 3 | 0.8250 | 0.8250 | 0.7822 |
| B | 5 | 0.9000 | 0.8350 | 0.8030 |
| B | 10 | 0.9000 | 0.8350 | 0.8190 |
| C | 3 | 1.0000 | 0.9667 | 0.9606 |
| C | 5 | 1.0000 | 0.9667 | 0.9470 |
| C | 10 | 1.0000 | 0.9667 | 0.9570 |
| D | 3 | 0.9750 | 0.9750 | 0.9233 |
| D | 5 | 1.0000 | 0.9750 | 0.9335 |
| D | 10 | 1.0000 | 0.9750 | 0.9472 |

最终完整 Evidence Top5 的相关 Chunk 覆盖宏平均：A 1.000、B 0.900、C 1.000、D 1.000；采用现有 2400 token/24 KiB 完整 Chunk 规则模拟组织。D 实际 Hybrid 完整入口的证据另见端到端回执，不将内部 Top10 当作公开工具上限。D 相对 A 的 MRR@3 +0.0917、nDCG@3 +0.0088；相对 C 的 MRR@3 +0.0083、nDCG@3 −0.0373。D 只重排 C 的同一批候选，Recall@10 相等不证明 BGE 提升召回。

逐题表为四组首个等级≥2的排名；Q20 有两个部分证据，另列 C→D Recall@3/nDCG@3。各题完整排序、等级及 K3/5/10 指标见 [metrics.json](v2-01-task132-evidence/metrics.json)。

| 问题 | A | B | C | D | C→D Recall@3 | C→D nDCG@3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q01 | 1 | 2 | 1 | 2 | 1.000→1.000 | 1.000→0.644 |
| Q02 | 1 | 1 | 1 | 1 | 1.000→1.000 | 1.000→0.917 |
| Q03 | 1 | 1 | 1 | 1 | 1.000→1.000 | 1.000→1.000 |
| Q04 | 1 | 1 | 1 | 1 | 1.000→1.000 | 1.000→1.000 |
| Q05 | 1 | 1 | 1 | 1 | 1.000→1.000 | 1.000→1.000 |
| Q06 | 1 | 1 | 1 | 1 | 1.000→1.000 | 1.000→1.000 |
| Q07 | 1 | 1 | 1 | 1 | 1.000→1.000 | 1.000→1.000 |
| Q08 | 2 | 1 | 1 | 1 | 1.000→1.000 | 1.000→1.000 |
| Q09 | 1 | 1 | 1 | 1 | 1.000→1.000 | 1.000→0.939 |
| Q10 | 3 | 1 | 1 | 1 | 1.000→1.000 | 1.000→0.861 |
| Q11 | 1 | 1 | 1 | 1 | 1.000→1.000 | 1.000→0.922 |
| Q12 | 1 | 1 | 1 | 1 | 1.000→1.000 | 0.939→1.000 |
| Q13 | 3 | 1 | 1 | 1 | 1.000→1.000 | 1.000→0.939 |
| Q14 | 1 | 1 | 1 | 1 | 1.000→1.000 | 0.939→0.922 |
| Q15 | 1 | 1 | 1 | 1 | 1.000→1.000 | 0.939→0.861 |
| Q16 | 1 | — | 1 | 1 | 1.000→1.000 | 0.939→0.922 |
| Q17 | 2 | 5 | 3 | 1 | 1.000→1.000 | 0.459→0.917 |
| Q18 | 1 | — | 1 | 1 | 1.000→1.000 | 1.000→0.939 |
| Q19 | 1 | 1 | 1 | 1 | 1.000→1.000 | 1.000→0.917 |
| Q20 | 1 | 1 | 1 | 1 | 1.000→0.500 | 1.000→0.766 |

Q01 中 C 将账户证据排第 1，D 将无关的订单查询排第 1、账户排第 2；Q20 中 C 将审批和申请两条证据排第 1/2，D 将申请证据降至第 4，前 3 中两个审批背景取代部分直接证据。Q16/Q18 的 BM25 单路没有相关证据，C 由 Dense 补回。此数据集只代表本项目固定夹具，不能外推；本轮保留退化，没有调标注或更改方案。

## 实测耗时与资源

AMD Ryzen 7 8845H（8 核/16 线程），Windows，约 15.26 GiB 物理内存，CPU 两线程；固定本地 Qwen3-Embedding-0.6B（1024 维）与 BGE revision `2cfc18c9415c912f9d8155881c133215df768a70`。单模型冷加载 Qwen 14.45 秒、BGE 15.54 秒；分别在不同进程测量，不相加称端到端。单模型运行峰值工作集 Qwen 约 1.30 GiB、BGE 约 1.01 GiB。

五轮、20 个有答案问题共 100 个成功样本，最近秩 P50/P95：Embedding 271/329 ms；同事务双路数据库 343/441 ms；BGE 1621/1828 ms。数据库分段同时包含 Dense 和 BM25，不是单路成本；原轮未测 A/B/C 各自的完整端到端开销；后续补测见文末。各阶段失败/超时/输入超限均为 0/120。

另以同进程顺序初始化两个真实模型，走现有 `HybridRetriever.search` 到完整 Evidence，预热后仅一轮 Q01–Q24：24/24 成功，20 个有答案样本 P50/P95 2253/2456 ms；无超时、输入超限或其他错误。该一轮是实际计时，不是五轮端到端统计；运行中采样工作集约 1.36 GiB、可用物理内存约 341 MiB。见 [端到端回执](v2-01-task132-evidence/hybrid-end-to-end.json)。资源并发和故障以既有 Task 1.2.2 独立 QA 证据为准，本轮未重测。

Q21–Q24 作为无答案诊断单列：Dense/C/D 各题均返回 10 个候选，BM25 对 Q21/Q22/Q23/Q24 分别返回 0/6/1/0 个候选。四题均无等级≥2证据，返回候选不等于存在答案。各组具体来源和分数见回执。本实验未执行真实 LLM 答案或来源发布，不能判定证据不足、错误回答或虚构来源；冲突、过期来源、真实业务和完整 V1 兼容由主 Agent 的独立门禁处理，不能由排名结果替代。

## 命令与清理

所有模型和数据库命令通过隔离 guard，口令仅由 guard 程序读取。最终脚本拒绝覆盖既有回执；复验时通过 `TASK132_OUTPUT_DIR` 指向新目录，并复制已冻结 fixture.json 至该目录。执行 `TASK132_PHASE=freeze/qwen/bge/report/end_to_end/cleanup/audit_cleanup` 对应 PowerShell 设置环境变量后运行：

```powershell
$env:TASK132_PHASE = "<phase>"
$env:TASK132_ROUNDS = "5" # qwen；end_to_end 使用 1
.\.venv\Scripts\python.exe -B .git/task131-local-validation.py pytest -q scripts/verify_v2_01_quality.py
```

freeze、首轮 qwen/bge/report、五轮 qwen/bge/report、单轮 end_to_end、cleanup、audit_cleanup 均各 1 passed；`.\.venv\Scripts\python.exe -m ruff check scripts/verify_v2_01_quality.py` 通过。受控检查验证来源哈希、相关分母和最近秩计算。实测完成后脚本仅增加独立输出目录和禁止覆盖回执保护，已用临时文件受控验证覆盖被拒绝；模型实测未重跑此保护变更。最初守卫连接超时、一次使用 pytest `-s` 被凭据保护拒绝，均在任何写入前；转发恢复并取消 `-s` 后执行。

仅添加并经 Repository 精确删除 12 个 `task132-distractor-*` 文档，删除后原六 Chunk 与冻结内容和身份逐项一致、目标文档剩余零，见 [清理回执](v2-01-task132-evidence/cleanup.json)；索引 watermark 因正常发布和删除递增。未改正式库、设计、业务代码或 Git。

未闭环：冻结质量目标未达，等待用户裁决；无答案生成、主 Agent 的业务/V1 门禁及本 Task 独立 QA 均不由本报告声称完成。

## 证据 SHA256

- `scripts/verify_v2_01_quality.py`: `9181d6140ff46d427243eebae8cc204e0e89d46e08e94f0ec136c7662fdb380b`
- `data/v2-01-quality/manifest.json`: `77ffb959d991fdb4e185b831d73ea28989ff212c5186a250c712636c1831d3c8`
- `docs/v2-01-task132-evidence/bge-first.json`: `4ef7006c37d141ab9de1931615083254173d35cc15406b81a4d23e88984c0963`
- `docs/v2-01-task132-evidence/bge.json`: `98582c6f26c65c5e877c51ad0aa4ab1779e03d33116dcfb2590c81d06bcca403`
- `docs/v2-01-task132-evidence/cleanup.json`: `f5196622ea9edf74b009e66adbbe7238a81030d9ff695d253af3814532d049d2`
- `docs/v2-01-task132-evidence/fixture.json`: `404b70e8732b6c7be1eedeae97055c1763643daf12a382853d21794b4665d2df`
- `docs/v2-01-task132-evidence/hybrid-end-to-end.json`: `dd4112f0d7da55b27372a831a57858d971d3b19ac53813f026000071e7f9dbe9`
- `docs/v2-01-task132-evidence/metrics-first.json`: `5edb99a96918026a06fc125fae9138df4893375d3f99cdb8927bf7f975c7effd`
- `docs/v2-01-task132-evidence/metrics.json`: `2a43df06ee5264a4728dfa9a8a700e7a40909200ed65e63ab0afa675eaef99a5`
- `docs/v2-01-task132-evidence/qwen-first.json`: `55f67dffccd5917369b57b633098763300be87e327093c9ccf3c7c7c63114a79`
- `docs/v2-01-task132-evidence/qwen.json`: `7c0dfdbf0f35c2cea91f4d4bd1f2450e5d882245d16286430bf6c135fc4fdf06`

## QA-002 A/B/C 独立计时补测：未闭环

新增独立 A/B/C 入口到完整 Top5 Evidence 的计时模式，A 为 Dense-only Top10、B 为 Sparse-only Top10 且无 Query Embedding、C 调用现有双路同快照与 RRF；三组固定 18 Chunk、domain=None、相同问题和预算。A/B 单路 SQL 复用现有候选查询的投影、过滤及排序，C 使用现有 Repository；定时不通过相减或相加其他路径得到。预先核验冻结 fixture 和五轮原始回执的 SHA256，逐次对照 Top10 的完整身份与顺序；文档重新导入后及清理后校验原始内容和身份。

受控替身检查证明 B 不调用模型、A 仅走 Dense、C 调用融合并完成 Evidence 组织；六文档隔离库只读 BM25 预检通过。真实运行五轮命令在第 1 轮 Q04/B 按要求因排序漂移停止，pytest **1 failed**：冻结果 distractor-04/07 排名 3/4，此次 4/3，直接证据 refund-entry 均排第 1。不能根据现有证据推断根因，也不改标注和比较基线。停止前 A/B/C 完成尝试为 4/4/3，其中 B 1 次漂移；样本不足，不将这些请求作为正式延迟 P50/P95。回执 `abc-end-to-end.json` 记录各次尝试与实际顺序。12 篇新导入的专用文档精确删除，清理后完整行集与导入前一致；库 watermark 随事务变化。Qwen 已关闭。

```powershell
$env:TASK132_PHASE = "abc_latency"
$env:TASK132_ROUNDS = "5"
.\.venv\Scripts\python.exe -B .git/task131-local-validation.py pytest -q scripts/verify_v2_01_quality.py
```

首次补测未取得完整五轮延迟，既有 D 单轮范围不变；其后的独立补测见下。不能以分段耗时、失败前的少量样本或质量评测替代该证据。

QA-002 首次补测回执：`docs/v2-01-task132-evidence/abc-end-to-end.json`，SHA256 `b8d44dc544a8b5d40fad3a8e9c882c7d2fe9551ae60ce8b31bad1361a95820a8`。

### QA-002 五轮补测

主 Agent 裁定对完整冻结来源身份与 qrels 保持硬校验，跨重新导入后相对旧结果的排序/分数差异逐次记录，不作为无关干扰文档次序变化而终止计时；首次失败记录保留。未更改语料、标注或旧质量结果。固定执行顺序为每轮 Q01–Q24，逐题 A→B→C；各组分别预热一次，Qwen 冷加载 22.33 秒单列。A/B/C 每组各 120 次实际端到端尝试均成功，无超时、输入超限或其他错误；各取 20 个有答案问题×5 轮共 100 个成功样本，最近秩 P50/P95 如下：

| 组 | 实际路径 | P50 ms | P95 ms |
| --- | --- | ---: | ---: |
| A | 真实 Qwen、Dense Top10、完整 Evidence 组织 | 428.6 | 520.5 |
| B | BM25 Top10、完整 Evidence 组织，无 Query Embedding | 341.6 | 511.7 |
| C | 真实 Qwen、同快照双路 Top10、RRF、完整 Evidence 组织 | 652.2 | 788.5 |
| D | 真实 Qwen、双路、RRF、真实 BGE、完整 Evidence 组织 | 2253.0 | 2455.9 |

D 为前轮单独测量的 20 个成功有答案样本，其余三组各为 100 个；这些不同轮次不作为同负载的统计显著性声明。排序与旧首轮对照：A 0/120 次变化，B 40/120 次（Q04、Q05、Q06、Q09、Q10、Q13、Q14、Q22），C 30/120 次（Q04、Q05、Q06、Q10、Q13、Q14）；BM25 分数也有变化，原因未经验证。逐次身份、次序、新旧分数和完整 Evidence 身份保存在回执中，补测不重新计算或替换冻结质量分数。每题均比对冻结身份；原始 qrels 所在 fixture 与质量回执摘要均固定核验。

命令为上节 `abc_latency`，5 轮、guard 通过，**1 passed in 214.28s**。补测完成后已按主 Agent 指示保留隔离 DEV 的 18 篇/18 Chunk（含 12 篇 `task132-distractor-*`），完整身份和内容经脚本核验，Qwen 已关闭，数据库使用权移交主 Agent 进行同语料业务核验；此时尚未执行本次保留夹具的最终清理。质量收益结论仍为未通过，补测结果待独立 QA。

五轮补测原始回执：`docs/v2-01-task132-evidence/abc-end-to-end-rerun.json`，SHA256 `55be6d57ef6c7770ebe5bb8206e470ddf48f996662ffa40669318ec3e98b137a`。
