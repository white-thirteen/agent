# Task6.3.2 交付记录和最小回归

6.3.1独立QA PASS、06-QA-001已修复独立复测关闭，主Agent复核VERIFIED，现明确单独派发6.3.2，IN_PROGRESS。读AGENTS/STATE、D06 Task6.3.2/第11～12节、当前演示及必要前序交付。六阶段冻结设计不重写，用户最新本地Qwen/1024方案覆盖旧OpenAI参数。06阶段技术VERIFIED与用户ACCEPTED分别记录，本Task不得替用户验收或Git归档。

整理README、.env.example、实际直接依赖requirements.in与已验证锁定requirements.txt（无必要不变更）、docs/demo-walkthrough.md、docs/final-acceptance.md及简洁06 Handoff。按责任Task/实现/自动验证/真实联调/环境版本/结果/遗留建立可核查矩阵，引用旧证据原位置，不复制大段日志。Apifox及无秘密变量模板沿6.3.1实际导入版本，不硬编码历史审批关联。

明确Windows Python3.13.7/项目.venv/单worker、Qwen3-Embedding-0.6B指定本地路径/CPU/1024/单例/批量与并发、Chat实际服务商、Ubuntu原PG17.6/vector0.8.7、schema001～006/Saver/Store显式setup顺序、种子和固定语料导入、启用开关及健康状态边界。用户.env的Embedding默认关闭，演示需显式启用并导入知识；不再要求OpenAI Embedding API Key，不引入Ollama/GPU/新服务。V1本地审批无管理员认证/管理Key，production禁用，127.0.0.1与演示用户选择边界清楚。

验证干净Python环境按现有清单安装与运行，依赖检查、必要受影响回归及资源释放。新临时venv必须独立命名，不覆盖现有.venv；安装CPU依赖沿已验证版本/缓存，不无故升级全量依赖或切换Python。实际依赖/模型/网络阻塞应BLOCKED，不把已有环境当干净环境。真实Chat/Qwen/PG五能力演示明确本轮实测及未变前序复用，模型名不代表调用已验证；避免重复付费和完整回归。

检查现有compose/部署说明：原VM已安装vector包在容器可写层，重启保留、重建会丢失；不能把原vanilla postgres:17.6镜像称为已含vector。需最小可信可复现安装/固定版本说明或配方，PG17.6主版本及原卷保持。不得自行SSH、重建原容器/卷、升级PG、删除数据；若隔离验证确需VM资源，由主Agent确认具体无损操作后执行，不能静态配方冒充已重建验证。干净Python与数据库新初始化是否实际执行分别记录。

测试仅agent_demo_test/agent_test，UUID自有数据精确清理，前后全public完整行集/列定义及所有迁移checksum保持；新场景禁seed/改固定5订单，原完整seed门禁窄例外按AGENTS保留不deselect。保护.env/006/冻结设计/角色/旧证据/六项暂缓差异，不杀用户进程，不Git/Bridge/另派Agent。只管理自己创建且记录PID/命令的进程，单Qwen实例，完成核资源归零。

交docs/06-delivery-report.md及必要脱敏证据、最终验收入口和Handoff草稿，不改STATE/AGENTS/主协调（由主Agent最终同步）。列真实实测命令/耗时/内存，未测不编造；已通过/失败/阻塞/未验与人工步骤分别清楚。保留Store历史即时观测波动及其他范围限制。完成停止交独立QA，不进入新阶段，不自行提交或推送。

本轮补充：用户已确认手动导入Postman。客户端后置脚本运行/变量回填/SSE界面未实测，按631复测报告在最终材料单列，禁止重新ComputerUse或冒称已验。新增tests/test_demo_session.py含2受控+1真实回归，最终完整门禁必须进程内设置AGENT_VERIFY_DEMO_QWEN=1与AGENT_DEMO_FIX_EVIDENCE全新JSON路径，原seed窄例外原样纳入，无skip/deselect。此前225为旧门禁，仅作出处，不能替最终新完整结果。
