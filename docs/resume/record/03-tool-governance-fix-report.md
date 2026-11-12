# 03 工具治理 QA 问题修复报告

本轮关联阶段 03、Task 3.3.1 与 3.2.1 的 03-QA-001，以及 Task 3.2.2 与 3.3.2 的 03-QA-002。执行依据为 [修复任务](../03-tool-governance-fix-task.md)、[独立 QA 报告第 7 节](../../question/03-tool-governance-qa-report.md#7-问题清单)和 [主 Agent 裁决](../../question/03-tool-governance-main-review.md#5-独立qa裁决与修复决定2026-11-12)。本报告记录开发自测，问题关闭及阶段状态由主 Agent 在独立回归后决定。

## 根因与修改

03-QA-001 的订单数据模块原来直接导入工具治理异常，间接加载 Graph/Runtime 契约，违反 D03 的数据层依赖方向。`app/domain/orders.py` 现在定义 `OrderReadTransientError` 与 `OrderReadUnavailableError`，仓储沿用原来的 psycopg 和连接池故障分类，分别抛出领域读取故障。`app/tools/implementations/orders.py` 的 get/list 适配器将这两类故障转换为现有 `ToolTransientError` 与 `ToolUnavailableError`，Executor 沿用原有只读重试、计数和公开 `order_query_unavailable` 结果。订单不存在仍走 `order_not_accessible`。取消、超时与未预期的编程错误沿既有调用链传播或由 Executor 按既定超时契约处理。

03-QA-002 的订单 `execute_query` 已保存原调用、规范参数和结果，但缺少独立的来源和 Run 关联。`app/graph/specialists/order/builder.py` 在现有私有 `call_records` 中增加 `origin` 和 `run_id`，分别取自服务端 `ToolExecutionContext.origin` 和其 `ExecutionContext.run_id`。原调用 ID/name/raw_args、规范参数、结果、execution_id、attempts 和累计用量继续保留。观察节点沿用已保存的 batch_results，不重新执行工具。

## 本轮文件

| 文件 | 职责 |
| --- | --- |
| `app/domain/orders.py` | 定义并抛出领域订单读取故障，移除工具层导入 |
| `app/tools/implementations/orders.py` | get/list 适配器转换领域故障至既有工具治理异常 |
| `app/graph/specialists/order/builder.py` | 在私有记录保存可信来源及 Run ID |
| `tests/test_tool_governance.py` | 单独进程导入边界、真实仓储到适配器/Executor 的故障分类及取消/编程错误传播回归 |
| `tests/test_order_graph.py` | 实际工具链的原调用与可信关联、不同 Run、观察重进及父图/事件隔离回归 |
| `docs/resume/README.md`、`README.md` | 修复记录导航 |
| 本报告 | 开发自测及交接记录 |

本轮基于已有工作区修改增量实施。冻结设计正文、迁移、种子、依赖、凭据、主 Agent 协调文件及用户指定的其他既有差异均未由本轮修改。未调用其他会话，未 Commit/Push。

## 开发自测

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_tool_governance.py tests/test_order_graph.py tests/test_graph_protocol.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_order_graph.py
.\.venv\Scripts\python.exe -m ruff check app/domain/orders.py app/tools/implementations/orders.py app/graph/specialists/order/builder.py tests/test_tool_governance.py tests/test_order_graph.py
.\.venv\Scripts\python.exe -m ruff format --check app/domain/orders.py app/tools/implementations/orders.py app/graph/specialists/order/builder.py tests/test_tool_governance.py tests/test_order_graph.py
```

首次定向测试因新增测试夹具错误传入非 async handler 而有 4 项失败，注册器按契约拒绝。修正测试夹具后，上述三组测试为 **57 passed**。此后补充父图隔离及观察重进记录不变断言，各次订单图定向回归均为 **6 passed**。最终 Ruff lint 通过，format 为 **5 files already formatted**。

受控故障覆盖 get/list 两条真实仓储到工具适配器及 Executor 路径。`OperationalError` 分别产生两次实际尝试和两次用量计数，`ProgrammingError` 分别只尝试一次，均返回 failed / `order_query_unavailable`、无数据。另验证订单适配器的编程错误和取消传播，既有测试覆盖超时及不再重试。隔离 Python 进程直接导入订单领域模块，断言未加载 `app.tools`、`app.graph` 或 `app.runtime`。

实际编译订单图的 get/list 成功场景检查 `origin=model`、当前 `run_id`、原调用、结果 execution_id 和 attempts。另用不同 Run 执行同一调用 ID，核对两个记录的 Run ID。观察节点重复进入时工具次数不增加，ToolMessage ID/内容、已验证事实及私有记录保持一致。主图快照没有 `call_records` 或私有 ToolMessage，公开事件没有私有调用 ID 或记录字段。

## 真实测试库与数据保护

使用项目解释器执行内联 PowerShell here-string Python harness。连接前以 `validate_test_target` 检查配置目标，随后仅连接 `agent_demo_test`，只读断言 current_database/current_user 为 `agent_demo_test` / `agent_test`，schema 版本为 1、2、3，已登记 checksum 与仓库对应迁移文件一致，订单行数为 5。获取全部订单与 Session 的排序快照后，在进程内显式设置测试 URL，调用以下受影响测试集合。

```text
pytest.main(['-q', 'tests/test_tool_governance.py', 'tests/test_order_graph.py',
             'tests/test_graph_protocol.py', 'tests/test_order_postgres.py'])
```

结果为 **58 passed，0 failed，0 skipped**。测试后只读复核身份、版本/checksum 和完整订单/Session 行集，与测试前完全一致。前后均为五条订单、零条 Session。既有真实订单测试中的非法插入在事务中回滚，退款标识按原值恢复，种子幂等检查返回零插入。未执行迁移或重建，未连接或写入应用库。连接预检/复核的失败分支只报告异常类别，测试保留项目默认脱敏插件与 fd 捕获。

## 设计偏差与交接

本轮实现采用 D03 已要求的领域故障与薄工具适配边界，私有记录来自可信执行上下文。未发现需要变更冻结设计的偏差。公开错误 code、重试策略、owner SQL、金额投影和 SSE 字段沿用原契约。

主 Agent 将安排独立完整回归，本轮没有重复执行完整测试集或付费真实模型。RISK-02-CRED 的历史凭据暴露及密码复用、P3-01 的既有格式遗留继续按已接受决定追踪。
