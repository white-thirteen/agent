# 06 / Task6.3.1 / 06-QA-001 定向修复记录

日期：2026-11-15。关联提示词：[06-demo-fix-01-task.md](../06-demo-fix-01-task.md)；问题来源：[独立QA FAIL](../../qa/06-demo-qa-report.md)、[原真实复现证据](../../qa/06-demo-qa-reprepare-evidence.json)。旧FAIL和复现证据原样保留，本记录不关闭问题、不代替同原QA独立复测。

## 修复

`scripts/demo_session.py:195` 将 `folder.mkdir(parents=True, exist_ok=False)` 移到当前调用的prepare异常清理作用域之前。只有目录创建成功才调用prepare及其异常清理；已有目录的FileExistsError直接传播，不进入准备、不读取旧manifest/基线、不清理或改写旧数据。`prepare`负责填充已由本次调用新建的目录；本次部分准备失败时，原manifest/baseline精确清理保持。

`tests/test_demo_session.py:25`、`:43` 增加两个受控CLI回归：已有目录（含manifest、基线、操作者文件）拒绝时完全不执行准备/清理且目录字节不变；新建目录准备中途失败仍调用本轮清理、写失败清理回执并传播原错误。`:75` 是显式启用的真实Qwen/PG回归，默认跳过真实依赖调用。`docs/v1/v1-06/demo-walkthrough.md`补充重复目录拒绝和本次调用所有权的行为。

## 实际验证

全部命令使用项目 `.venv`，无付费Chat、GUI、FastAPI服务、SSH、PG/容器重启或完整门禁重跑。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_demo_session.py -k 'not real' -q
$env:AGENT_VERIFY_DEMO_QWEN='1'
$env:AGENT_DEMO_FIX_EVIDENCE='D:/py/agent-project/agent/docs/v1/v1-06/fixes/records/06-demo-fix-01-real-evidence-20261115.json'
.\.venv\Scripts\python.exe -m pytest tests/test_demo_session.py::test_real_prepare_ownership_and_partial_publication_cleanup -q
.\.venv\Scripts\python.exe -m ruff check scripts/demo_session.py tests/test_demo_session.py
.\.venv\Scripts\python.exe -m ruff format --check scripts/demo_session.py tests/test_demo_session.py
```

结果：受控回归 **2 passed / 1 deselected**，真实定向回归 **1 passed，78.15s**，Ruff检查及两文件格式通过。首次即通过，无本轮测试失败。

真实验证使用agent_demo_test/agent_test及UUID自有目录/用户/订单/文档；在线核验001～006 checksum和全部13张public完整行集/列定义。真实Qwen CPU/1024准备成功后，额外创建该用户的session和profile，再运行同folder prepare：非零退出且FileExistsError，两个订单和真实向量维度仍在，**整个public快照及目录所有文件字节逐项完全不变**，关联session/profile保持。

随后精确清理成功场景；对另一新目录运行正式prepare，在真实Qwen向量经KnowledgeRepository提交后、最终manifest写回前注入RuntimeError，实际进入本调用失败清理。未Mock核心Embedding或数据库操作；注入点仅制造确定性的提交后失败。原错误传播，失败回执 `protected_unchanged=true`，全库最终快照与最初基线完全一致。证据：[真实回归及全表前后指纹](06-demo-fix-01-real-evidence-20261115.json)。

模型子进程顺序执行，每个subprocess.run已返回且退出；没有启动或遗留自有服务，仅单Qwen实例。所有本轮测试数据已按自身manifest精确清理，不改固定五订单，不seed；完整本地基线留在测试临时目录，证据不导出原库行集/凭据。未改.env、006、角色、冻结设计、STATE/AGENTS/主协调或其他既有工作。

## 待复核

已完成指定修复和开发自测，停止交回原QA独立复测；06-QA-001是否关闭由独立复测和主Agent裁决。未进入6.3.2或执行Git操作。用户已手动导入集合的回执沿原QA记录，本次未操作GUI、未扩展Apifox后置脚本/SSE界面验证。
