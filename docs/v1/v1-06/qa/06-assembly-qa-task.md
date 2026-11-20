# Task6.1.1 独立QA

仅主Agent在Implementer完成停止后派发才开始；当前为验收工作单元准备。依据根AGENTS、STATE、docs/v1/v1-06/06-assembly-execution-task.md、D06第2～4/6节及6.1.1、实际交付/前置05Handoff。默认只读业务/既有测试/配置/旧证据，仅独立报告/临时复现，不代修、不Git/Bridge/SSH/DB重启/另派Agent/进入下一Task。

独立核资源图：同一正式factory共享ChatGateway/CPUQwen/Registry/Policy/Executor/Runtime，rootSaver/子图默认继承，无测试Stub或memorycheckpointer冒充持久运行。仅已有approvals Router一次，Actor来自服务端dev/test审计，production无管理Router。Graph启动编译一次，用户状态显式State/context不放单例成员。普通startup不DDL/setup/seed/自动导入，Store独立Embedding就绪。

检查正常/缺资源/部分初始化失败/运行中故障及关闭：安全health与实际受理相符，Model/session/Saver缺失正确503或失败；KB/Profile错不假empty/ready；Store可选降级/denied及显式操作失败/unknown；资源反序释放、Runtime先5秒收敛/取消再Store批处理await、模型/Embedding排空/Saver/业务池，无残留Task/连接；取消不等于写未提交。不要只检查构造函数调用次数，执行必要实际行为和真PG验证。

针对同一应用完整HTTP装配证据独立验证必要真实路径，区分受控/真实PG/真实Chat+Qwen；三专业和显式Memory都经正式Route/Service/Runtime/同治理，退款是本地模拟且实际Gate等待，不用重发自然语言当恢复。本Task重启故障矩阵留6.2，不无收益重跑旧完整矩阵或全部付费请求；若可信未变实时证据充分，标明复用来源，自己做必要独立核心验证。

只专用agent_demo_test/agent_test，在线身份/完整迁移checksum/Store版本；全部public行集和列定义保护，原五订单不可seed/改状态，使用唯一自己的订单、profile、知识文档、session、Task/op/thread并FK精确清理。若真实资源未可用如实BLOCKED不得skip冒通过。允许验收进程Settings选择test/UUID名单/EmbeddingTrue（原Qwen路径、预算），禁止改用户.env/Codex账户模型provider配置或原006/前置证据。

输出docs/v1/v1-06/qa/06-assembly-qa-report.md：PASS/FAIL仅6.1.1，问题从06-QA-001续号/严重度/文件位置复现、自己实测命令/通过失败跳过/清理/复用来源、未验风险。完整门禁来自最终实现，未变不重复全量；FAIL交主Agent退原Implementer，独立复测后才裁决。完成停止不自行进6.1.2或宣布阶段通过。
