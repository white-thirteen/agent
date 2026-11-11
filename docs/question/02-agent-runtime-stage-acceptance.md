# 02 AgentRuntime 与 Supervisor 技术验收报告

验收日期为2026-11-11。主Agent已完成执行交付审核、独立QA裁决、两轮输出脱敏修复审核及独立回归，技术验收通过，用户已正式批准验收，阶段状态为 **ACCEPTED**。用户授权完成02 Git归档后推进03，03结束后再次提交用户验收。

## 1. 六Task完成情况

| Task | 验收交付 | 结果 |
| --- | --- | --- |
| 2.1.1 | Demo类型/State、可信Task及同值workflow、显式new/continue、消息范围和预算快照 | 通过 |
| 2.1.2 | Gateway路由、两类澄清、具体目标保持、有限上下文、unsupported及一次结构纠正 | 通过 |
| 2.2.1 | 三专业真实编译骨架、外部注入Gateway/Saver、父子白名单和关联核验 | 通过 |
| 2.2.2 | 单一公开回复、结构化结果、图内run_finish结算、同步提交后收敛 | 通过 |
| 2.3.1 | 独立Runtime任务、同thread互斥/容量、request_id、累计预算、结果保留和shutdown | 通过 |
| 2.3.2 | 三POST入口、单订阅/ASGI所有权、安全SSE、状态查询及无重放附流 | 通过 |

执行及接口细节见[开发交付报告](../02-agent-runtime-delivery-report.md)。冻结六阶段、36Task和D02需求保留，主Agent没有以Bridge实现代替业务开发。

## 2. D02验收矩阵

原独立QA逐项证据见[QA报告第5节](02-agent-runtime-qa-report.md)，最新脱敏及阶段回归见[独立回归报告](02-agent-runtime-redaction-regression-report.md)。

| D02第11.2节门禁 | 主Agent复核结论 |
| --- | --- |
| 通用澄清到具体业务 | 同Task/不同Run及预算继承通过 |
| 具体缺参与显式换目标 | 原目标保持、合法new_task和新目标隔离通过 |
| 不支持取消及非法模型输出 | 安全拒绝、有限纠正及额度约束通过 |
| 三专业骨架 | 实际编译并返回capability_unavailable，后续业务边界清楚 |
| 父子图隔离 | owner/task/run/目标关联、消息及用量白名单通过 |
| 预算 | 模型尝试、工具种子、主动时间累计及用户等待排除通过 |
| 普通结算与中断边界 | run_finish图内结算、sync提交、END后无第二次普通写回通过 |
| 互斥与容量 | 同thread立即冲突、不同thread并发、容量拒绝通过 |
| 重复请求 | 同指纹复用、异指纹拒绝、进程内窗口及索引清理通过 |
| 断开与慢队列 | 首迭代前/响应失败/实际TCP断开、解绑后执行继续、晚清理隔离通过 |
| 重订阅与结束 | 首快照、未来事件、done语义及Last-Event-ID拒绝通过 |
| 异常与结算失败 | 实际最终Saver提交失败、incomplete及TTL后uncertain阻塞通过 |
| 关闭与身份隔离 | 有界shutdown、资源关闭顺序、跨用户/会话404及production禁用通过 |

## 3. QA、修复及回归证据

- 原独立QA完整真实库109项通过，独立外部补测3项通过，新增产品缺陷为0。原QA Turn报告落盘后失败，经单独正常completed收尾确认报告完整及测试来源。
- QA-EXEC-01曾在临时PG探针失败回溯中回显真实凭据。首轮输出插件覆盖测试/收集异常及捕获stdout/stderr/log；主Agent用虚构凭据补查发现warnings及文件日志遗漏，再交修复会话第二轮补齐。
- 最新独立回归为 **119 passed、0 failed、0 skipped，35.51秒**。定向10项包含在119项中，分别记数。原独立外部补测为 **3 passed，14.53秒**，临时fixture的3条弃用warning保留。
- 独立合成验证实际测试失败退出1、收集失败退出2，异常类别/文件/行号保留；明文/常见编码凭据、kwargs、捕获输出和warnings均脱敏。12种命令行或ini拒绝检查在收集前退出4，日志/XML和收集标记未创建。
- 最新全仓lint通过，90个执行Python文件format通过。独立测试前后90个Python文件及pyproject摘要相同，确认被测实现保持原样。无依赖新增。
- 专用库预检确认agent_demo_test/agent_test、迁移001/002版本/checksum；119项前后schema及完整Session行集相同，Session为0。原补测的真实PG/正式lifespan/TCP、池和客户端释放也通过。

报告链包括[首轮修复](../resume/record/02-qa-credential-output-fix-report.md)、[第二轮修复](../resume/record/02-qa-credential-output-round2-report.md)及[独立回归](02-agent-runtime-redaction-regression-report.md)。提示词和各轮报告独立保留，个人Thread/Turn关联在本机Bridge协调记录中持久化。

## 4. 问题决定与已接受遗留

| 项目 | 决定及阶段影响 |
| --- | --- |
| QA-EXEC-01未来输出回显 | 已验证pytest标准入口的实现问题关闭，独立回归通过 |
| RISK-02-CRED | 用户明确接受历史工具输出凭据暴露及agent_app/agent_test/agent_bootstrap配置密码复用为本Demo遗留，暂缓换密 |
| P3-01 | 六份既有设计示例format遗留继续保留，当前执行代码检查通过 |
| ENV-02-01 | 既有容器启动绑定失败和网络端点缺失已恢复，真实库复测通过，关闭。固定IP开机时序仍属环境维护关注项 |
| QA-TURN-01 | 报告落盘后的会话失败原因不可见，报告完整性经正常收尾确认，产品测试证据有效 |

当前无未关闭的阶段阻塞实现问题。旧凭据及审计内容仍存在，用户接受的遗留按原事实保留。

保护限项目插件加载后的已配置数据库连接值及已验证表示。正常使用默认fd捕获；无捕获、实时日志、JUnit及pytest文件日志在收集前明确拒绝。插件启用前输出、未知临时秘密、第三方输出后端、进程外输出和测试自行写文件仍须各自验证。后续报告继续只输出脱敏摘要。

## 5. 数据库访问范围与下一阶段边界

Docker发布192.168.150.101:5432，未对能路由到该地址的来源额外限源。HBA仅允许192.168.150.1/32分别以agent_app访问agent_demo、agent_test访问agent_demo_test、agent_bootstrap访问postgres，采用scram-sha-256；其余TCP组合拒绝，容器内Unix socket为local trust。网络层和数据库登录层分开记录。Windows实际测试连接通过，其他客户端及公网路径未额外实测。详细检查见[协调记录第10.1节](02-agent-runtime-main-review.md)。

02仍使用内存Saver及进程内Run/去重/uncertain窗口，三专业当前为不可用骨架。03接工具治理与模拟订单事实，04接持久Checkpoint/HITL/退款，05接真实RAG/Store。额外真实模型网络联调未作为本轮证据。现有证据支持按冻结规划进入03，阶段切换由用户确认。

当前HEAD仍为01 Delivery cf3e763，暂存区为空。本轮代码、测试与文档在共享工作区，包含已有用户修改和暂缓路径。正式Git归档按既有授权及归属检查流程另行执行。
