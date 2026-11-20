# Task6.3.1 Apifox与演示脚本

2026-11-15最新执行分工：用户明确“接口文档做好，我来进行导入”。Agent停止全部桌面操作，交付当前接口OpenAPI、场景集合、无秘密环境与使用说明；Apifox实际导入/变量脚本/SSE显示由用户手动验证，结果待反馈，不自动记为PASS。下文原GUI执行条款保留验收目标，执行者以此最新分工为准。632尚未派发，不从文件交付推导631或06阶段正式验收通过。

6.2.2独立QA PASS、主Agent复核VERIFIED，现明确单独派发6.3.1，IN_PROGRESS。读AGENTS/STATE、D06 Task6.3.1/第8～10节及当前交付/实际API Schema，按现有工程制作最小可复现演示，不重构业务。D06旧OpenAI/1536/Key历史参数已被用户明确覆盖：Windows D:\AI\models\qwen3-embedding-0.6b，sentence-transformers CPU1024；PG17.6/vector0.8.7在原Ubuntu VM，Chat保持当前配置。

交Apifox实际支持的导入集合（apifox/目录）、无秘密变量模板、docs/v1/v1-06/demo-walkthrough.md及本Task交付/证据。集合base_url=127.0.0.1，健康/普通chat与Run/Task和退款查询/本地管理/RAG/Memory分组。普通JSON中的user_id是允许名单内演示选择，不是真实认证；无管理key/Header/认证变量，审批Actor服务端固定，production不注册管理入口。实际接口和返回字段为准。

动态提取或明确指导人工获取run/task/application/approval/subject_digest，不能硬编码历史关联。按说明完成本人订单→退款真实等待→完整停止自建FastAPI进程、保留PG→新进程查原审批→决定→独立原approval resume→业务事实核对；不同自有订单拒绝分支、普通聊天不能审批、重复结果复用。RAG真实Qwen检索/Chat带有效sources，资料不足与技术故障分开。Memory显式保存/新会话与重启读取、A/B隔离、修改删除/清除；保留最小last_mutation元数据，不能声称删除全部历史。

必须实际导入Apifox并核请求/变量/SSE，静态JSON合法、httpx请求或CLI测试不能冒充GUI导入。Windows已安装Apifox（cn.apifox.app）；操作GUI前按可用computer-use技能读取SKILL.md并使用规定工具，必要时报告实际环境阻塞，不自行换成未验平台。不得向集合/日志/截图/文档导出.env、模型/DB/SSH凭据。后续独立QA作为另一操作者按导出集合与说明复跑必要路径，现阶段不得自行派QA。

真实验证仅test库agent_demo_test/agent_test，UUID自有用户/订单/KB/profile/session/thread，前后身份、001～006checksum、全部public完整行集及列定义保护，按FK精确清理。新场景不得seed/修改固定五订单；演示说明引用既有seed命令时明确它是首次目标初始化，不能在本次原库上为演示重置历史数据。测试进程Settings test/UUID/EmbeddingTrue允许，不能覆盖用户.env。自有服务PID/启动命令记录并确认全部退出，单次一个Qwen实例。

不Git/Bridge/SSH/PG重启/容器重建/杀用户进程/另派Agent/提前6.3.2。保护旧证据/006/冻结设计/角色/六项暂缓差异，不改STATE/AGENTS/主协调。纯集合/文档核事实/链接及真实导入演示，不无收益重跑完整业务门禁。交docs/v1/v1-06/06-demo-delivery-report.md和脱敏实测证据，逐项分清真实/受控/复用/失败/未验/需人工，完成停止交独立QA，不能自行宣布06 ACCEPTED或V1交付。
