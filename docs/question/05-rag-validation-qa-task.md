# Task5.2.2 独立QA

后继QA准备，只在主Agent明确派发且Implementer停止后开始。依据根AGENTS、STATE、docs/05-rag-validation-execution-task.md、D05第6～8/11节及5.2.2，审docs/rag-validation.md和脱敏机器证据。默认只读业务/测试/配置/旧证据，仅写独立报告/临时复现，不代修，不Git/Bridge/另派Agent/SSH/DB重启。

检查固定8～12样本的真实层次和预期来源/允许结果；受控合法ID错误正文不能冒充语义通过。必须有实际Qwen CPU1024+真实Chat+真pgvector完整Runtime/HTTP链的正常/无答案/冲突证据，原Call/ToolMessage配对/同Executor计数、唯一公开出口/sources、真实供应商/Profile/语料版本、低信任文档不得提升权限；逐条人工核对真实正文事实支持和概括，不以sources存在或原文匹配替代语义。无弱证据拒答、假引用/过期更新删除不公开、Embedding/DB故障失败不假empty。若真实能力无法执行标BLOCKED不写PASS。

独立复测必要受控风险和至少一条自己的真实Qwen+Chat+PG链（以报告实际可用脚本/唯一state，绝不覆盖原证据）；无需重复所有付费样本或下载模型，模型进程串行且正常关闭。失败应区分供应商网络/模型行为/产品缺陷，真实结果不能篡改断言或skip。最终完整门禁可清楚复用未变5.2.1/本Task来源，有实质代码修复需相应最终门禁。

所有真实测试仅agent_demo_test/agent_test，先核身份及完整schema/checksum、原业务/Saver/他人知识全行集；唯一测试用户/会话/Task/thread/文档，精确清理不seed，不访问开发库写业务。模型/DSN/凭据不输出，原.env/006/自编默认语料与旧证据不变。报告docs/question/05-rag-validation-qa-report.md：PASS/FAIL仅本Task、问题编号沿已分配05-QA最大值续号/严重程度/位置复现、自己的命令/真实语义判定/清理及完整门禁复用来源、未验/风险；FAIL交主Agent退回原Implementer，完成停止不进5.3。
