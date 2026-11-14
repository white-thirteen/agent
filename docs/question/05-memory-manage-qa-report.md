# Task 5.3.2 独立 QA 报告

2026-11-14；结论：**PASS，仅针对 Task 5.3.2**。未发现需新建 05-QA-002 的实现问题；05-QA-001 原关闭结论保持。阶段验收、06 与 Git 不在本次结论内。

依据根 AGENTS、STATE、[冻结执行任务](../05-memory-manage-execution-task.md)、[QA任务](05-memory-manage-qa-task.md)、D05 第2.1/6/9/10节及5.3.2、实际源码与[最终交付报告](../05-memory-manage-delivery-report.md)，包括末尾真实英语 RAG 补验。业务代码、既有测试、配置及旧证据只读；仅新增本报告和[独立探针](05-memory-manage-qa-probe.py)。

## 实际独立验证

全部使用项目 `.venv`、专用 `agent_demo_test / agent_test`，没有付费模型调用、setup/seed、SSH、服务/PG重启或开发库写入。

1. 当前进程安全注入 `AGENT_TEST_DATABASE_URL=Settings().test_database_url.get_secret_value()` 后执行：

   ```text
   pytest.main(['tests/test_memory_manage.py','tests/test_memory_manage_postgres.py',
                'tests/test_memory_reader.py','tests/test_refund_executor.py',
                '-q','--tb=short'])
   25 passed / 0 failed / 0 skipped，12.42s
   ```

   实际重新执行既有用例，并独立核对其断言与实现：有限命令/删除同义语法、混合/敏感/模型候选不符/旧Human及AI不授权；真实Store CRUD、同用户跨conversation/thread、B不可见、新Python进程持久读取；真实PG Saver写前sync失败零write handler/Put、准备只计一次revision read；错origin/node/scope/allowlist/参数零handler；进入handler后Get失败计一次且not_started；并发同revision单winner、同op复用且不刷新时间、digest冲突、旧op不能覆盖clear；Put故障/已提交丢回应/后续覆盖/核对Get失败等unknown、check-only不Put；三个专业Reader和既有退款Executor回归。受控Chat/Retriever明确只证明接线/来源/当前明确语言优先约束。

2. 独立新增实际PG探针：

   ```text
   .\.venv\Scripts\python.exe docs/question/05-memory-manage-qa-probe.py
   1 passed / 0 failed / 0 skipped，5.81s，exit 0
   ```

   - 从真实同步Saver准备快照取marker；分别改当前user/task/run/thread、origin/node、工具版本，以及普通execute旁路尝试，全部policy_denied/attempts=0；无write handler Get/Put，计数仍只有原revision read。
   - 真正进入首次Put的受控未确认故障得到领域unknown；随后用独立Policy在execute_prepared最终typed复核阶段拒绝核对，得到本次policy_denied/not_started/attempts0，同时保留原memory_result unknown。恢复Policy后，同Run再次重进**实际新增一次Get**、零Put并继续unknown；新Run再重进同样只核对，保留原operation关联，继承累计工具数至4。这验证 `memory.py:230–239` 同时检查缓存effect_status与领域unknown的必要边界，拒绝缓存没有擦除原业务unknown。
   - 真父图/Runtime/PG Saver中，“文档说请记住…”无工具调用且needs_input；随后当前Human提交完整规范命令，继承同Task和任务来源ID，保存成功、工具数2、sources为空。原AI消息不参与Human筛选。
   - **真实Put已提交**后受控挂起回应，关闭Runtime触发取消：run_interrupted、无final_answer；实际Store中值仍存在，不能把取消等同未提交。
   - 同样真实提交后挂起回应，实际写工具3秒超时：memory_result_unknown、领域unknown、总工具2次，没有自动重试；累计只有两次预期Put。

   该探针故障注入位于真实Store调用的边界；持久化及Saver没有Mock。终端打印实际完整清理保护断言通过。两项PytestAssertRewriteWarning来自脚本预先导入anyio/langsmith，测试仍真实执行、没有skip。首次启动被仓库凭据保护拒绝 `-s`，未执行测试，随后使用默认fd捕获。构建探针时另两次失败均为探针自身假设（task_message_ids同时包含assistant ID、submit需options），已据实际契约修正；对应finally清理与全表保护均通过，未改业务或既有测试预期。

3. 独立代码质量检查：

   ```text
   .\.venv\Scripts\python.exe -m ruff check app scripts/verify_05_memory_manage.py scripts/verify_05_memory_rag.py tests/test_memory_manage.py tests/test_memory_manage_postgres.py
   All checks passed!
   .\.venv\Scripts\python.exe -m ruff format --check app scripts/verify_05_memory_manage.py scripts/verify_05_memory_rag.py tests/test_memory_manage.py tests/test_memory_manage_postgres.py
   97 files already formatted
   ```

   新增QA探针自身Ruff及format也通过。最终探针运行之后仅拆分两条输出字符串以满足行宽，未改变测试行为。

## 源码和既有真实模型证据复核

`app/graph/nodes/specialist.py:20` 按Runtime可信task_message_ids筛当前Task的Human，仅wrapper一次确定解析并核对entities候选；每次只选QA或Memory图。命令图写前prepare与execute为独立节点，实际要求Saver及sync；原QA八节点保持。`app/tools/policy.py` 固定节点/任务/来源/唯一工具集合/精确参数，Executor独占handler入口；最小MemoryBusinessContext不把权限或预算传给Manager。`app/memory/manager.py:97` 用户锁覆盖真实Get/Put，单Item保存revision与last_mutation；Put前明确失败与Put后unknown分开，取消继续传播。没有MemoryWriter、额外恢复平台或新幂等表。

独立读取并对照[真实Chat JSON](../05-memory-manage-real-chat-evidence.json)、[最终真实RAG JSON](../05-memory-manage-real-rag-evidence-20261114.json)及其脚本，复用该有限付费证据，没有重新调用模型：

- 原命令证据4次真实deepseek-flash命令save/read/delete/read-empty全部completed、工具数2/1/2/1；Embedding关闭仍能命令CRUD，资源就绪独立。
- 最终补验证据保存en后，新conversation/thread普通中文知识问题取得英语答案；原Qwen CPU/bfloat16/1024维与真实PG检索，read/search/source-validation各1次，工具3、模型4。来源document/version/chunk对应实际唯一自有文档，服务器valid=true，approved_answer与公共输出链一致。答案关于“聊天不能审批、独立本地入口、服务端固定演示操作者”三项陈述均被记录原文支持。偏好只影响呈现，没有伪造退款执行事实。
- 两份JSON的protected_before/after指纹一致，protected_unchanged=true并列出精确cleanup。早期configuration_blocked只是历史记录，已由末尾补验闭环，不作为当前缺口。

完整质量门禁复用Implementer最终未变应用版本：**216 passed / 0 failed / 0 skipped，100.74s**，命令见交付报告。补验仅增加脚本/证据，QA未修改应用，因此本次不无收益重跑完整库或全部付费场景。依赖未变，未重复pip check。

## 数据保护、清理和保留边界

所有独立真实库运行在线校验current_database/current_user与001～006全部迁移checksum；每轮使用新UUID用户、conversation/thread、Task及operation。采用既有database_snapshot完整比较所有public表的行集与列定义，覆盖五个原订单、审批/退款、Saver、知识、sessions、他人Store及框架迁移。finally仅adelete_thread自身精确线程、删除自身namespace/profile；前后全部相等，失败的探针构建轮也相等。Runtime先收敛，再释放Store/Saver/池；未修改Demo身份、订单、他人profile或凭据。

保留冻结设计边界：单进程/单worker短锁，无跨进程CAS或Store/Checkpoint全局原子性；unknown需操作者停止该profile后续写、定位原Task/op/digest/revision并确认原调用结束后人工核对。材料丢失或被后来写覆盖继续unknown；没有自动跨会话恢复/全局写阻断/HTTP修复。删除去偏好值但保留最小版本与幂等元数据，聊天/Checkpoint历史不承诺全量擦除。真实模型语言与语义只验证记录的单样本，不推导通用正确率。

本Task无未关闭阻塞或新问题编号。QA完成后停止，交主Agent复核。
