# 全项目联调报告

2026-11-20，基线`v2 / 1c9a4b9ad071ffdef9317f7efbd912b05032f786`。结论：**支持的核心业务、控制及持久化链路通过；保留IT-001与IT-002，不作全功能无条件PASS。** 本轮只测试、编写探针及保存证据，未修改生产代码、`.env`或正式数据库，未提交推送。原4项无关文件保持。

独立结论见[QA报告](independent-qa-report.md)。下列结果是本轮新执行，未将历史结果冒充本轮实测。

## 执行与结果

| 范围 | 本轮结果 | 证据 |
| --- | --- | --- |
| 当前HEAD完整默认回归 | 322 passed / 0 failed / 0 skipped，151.26秒；真实Qwen、Uvicorn健康及资源关闭通过 | [日志](project-full-regression.log)、[汇总](project-full-regression.json) |
| 真实订单及跨用户隔离 | 本用户读取完成，另一用户请求拒绝，真实SQL核对 | [HTTP run01](project-http-run-01/report.json)及对应原始`.bin` |
| 退款/HITL与完整进程恢复 | 待批聊天不能伪造批准；旧PID6776退出，新PID32072恢复原Task/调用/参数/operation/审批关联；批准与拒绝、重复resume及SQL副作用通过 | run01的restart、退款行集及原始审批响应 |
| 真实知识问答 | 真实Qwen1024、Hybrid/RRF候选与BGE重排组件可用，实际知识HTTP回答带本轮文档来源；不宣称排序质量收益 | run01的component_hybrid、knowledge响应及SQL |
| 结构化偏好 | 写/读/更新/删除、revision、operation幂等、用户隔离、完整进程重启与跨会话读取通过；该次子图实际偏好注入缺完整观测，最终订单英文渲染见IT-002 | [run02](project-http-run-02/report.json)及偏好原始响应 |
| Context历史、摘要与Revision | 同会话4次真实合法订单任务，在默认retain=3/segment=24下自然触发维护；1次真实摘要SUCCEEDED，Revision1 APPLIED，第5次输入使用对应上下文；旧完整Checkpoint结构不变 | run02的Context表、maintenance attempts、checkpoint对比及输入view |
| 真实TCP SSE提前断开 | 收到首帧后关闭客户端流，已受理任务继续完成；未声称事件重放或客户端GUI通过 | run02的sse-disconnect-prefix.bin及最终run状态 |
| V2 03多候选专项 | 2 passed；独立5题5/5，两种受控多候选Node使用正式Selector/Registry/Gateway/Policy/Executor与真实PG，ToolCall/ToolMessage配对、归属/分页SQL核对通过 | [原始日志](project-multi-candidate-real.log) |
| 数据与资源保护 | 所有测试轮次精确清理，最终指纹链连续，原有数据和固定5订单保持；无自有联调子进程残留 | [保护审计](final-protection-audit.json) |

run01的整个脚本退出1，不能称整轮通过：它在支持业务检查之后，遇到IT-001，后续原计划未执行。run02是仅针对缺口的新唯一场景，退出0；它不重复run01的退款流程，也不把run01失败改写为成功。初次启动包装命令曾因引号产生SyntaxError，尚未进入数据库/模型调用；QA报告明确记录该探针执行问题，不认定产品缺陷。

## 本轮发现

### IT-001 / P2：非业务输入的真实路由失败，待归因

输入“请简要说明你能处理什么问题。”后，真实HTTP SSE返回`model_output_invalid`，Task为failed，并非正常unsupported或needs_input。该输入不属于明确的订单、退款或知识业务，但其实际失败仍作为联调发现保留，不能仅以探针预期不适配掩盖。

一次额外、最多1 attempt的正式Gateway结构化诊断返回合法NewSupervisorOutput，finish_reason=tool_calls、parsing_error=null；该诊断没有原HTTP完整上下文，**不足以复现或关闭原失败**。原轮没有捕获该失败的原始结构化模型输出，无法确认是供应商响应、模型输出不稳定还是上下文/契约原因。后续修复应先增加恰当的解析错误观测并取得失败输出，不直接更换模型、放宽Schema或擅自增加重试。

证据：[run01](project-http-run-01/report.json)和对应`http-45-preference-new-session.bin`；[单次诊断](project-http-it001-diagnostic.json)。

### IT-002：英文偏好与确定性订单展示之间存在能力限制

run02通过结构化入口写入answer_language=en，新会话实际订单回复仍为中文。当前Order图map_result以固定中文格式构造可信业务摘要；本轮验证了偏好存储、读取、跨会话访问，但没有取得该次子图实际偏好注入的完整观测，**不能据此宣布模型输入或最终英文展示生效**。

这是现有实现的可确认行为；冻结设计保留语言偏好及共享读取，但本轮不推导重设计确定性业务格式的授权。应明确最终展示的适用范围，再决定是否补充确定性多语言渲染；不为语言体验重新让模型裁定订单事实。本轮保持代码及既有验收记录，未将其自动归类为新回归缺陷。

## 模型与配置证据

所有真实调用使用已配置deepseek-flash，自动网络/模型重试关闭。HTTP探针显式使用隔离设置：Qwen启用、knowledge_retrieval_mode=hybrid、Context窗口16384/输出512/摘要256/归档输入4096、独立Archive目录；默认保留3轮及Segment上限24未降低。上述测试配置不代表原`.env`默认启用了这些能力。

- HTTP消费按同Task可见model_attempts取max去重：run01可见5个Task共15次是观测下限，失败输入等未取得完整run计数；run02为7个Task/21次。审批恢复不按新Run重复累加原Task总数。普通HTTP调用缺完整Token回执，保持unknown，不填零。
- 维护摘要单列：1 attempt，input221/output66/total287 known tokens，独立于当前Run预算。
- IT-001诊断单列：1 attempt，input863/output185/total1048 known tokens。
- 多候选专项：五题5次/2466 known tokens，两条完整Node链路4次/1865 known tokens，共9次/4331 known tokens，0 unknown。测试专用多候选用途没有扩展生产HTTP工具权限。
- 不能把上列局部已知Token相加称为全项目总成本；HTTP未知部分及供应商实际计费未取得。完整默认verifier的paid_chat_calls=0为原静态声明，实际依据为默认范围未收集手动付费入口、opt-in为空，不能称独立网络计量。

## 环境恢复、隔离和清理

用户说明曾关闭Ubuntu VM，重新开启后继续。首次SSH/PG超时及容器刚启动未ready的两轮失败分别留存[超时日志](project-environment-timeout-r1.log)、[就绪失败](project-environment-readiness-r2.log)，均发生在测试guard阶段，不计通过。核对专用容器镜像SHA、独立卷、回环端口后仅启动原测试容器及本轮SSH helper；没有重新初始化、seed或切换正式数据库。本地Archive scratch PG56422亦恢复原数据目录。

数据库测试严格串行，最终快照链：完整门禁69→80（预先审计的11次知识发布）；HTTP run01为80→82；缺口run02为82→84（各唯一文档发布/删除+2）；多候选结束后的全部public指纹与run02清理后相同。三阶段前后摘要逐项衔接，保护比较包含完整原始行集/列定义，固定订单和其他表保持。原seed窄例外仅在默认门禁中原样执行并恢复实际原值，未扩展授权。

所有测试用户、订单、审批、退款、Store偏好、偏好回执、Context表、Saver thread及独立Archive数据均精确清理。完整行集基线pickle仅保留在本机`.git/project-integration-private/`，公开证据仅保留指纹及本轮虚构场景响应；不得归档私有凭据或该基线。最终已知凭据值扫描0命中，4个原有无关文件hash保持。

## 协作与未覆盖范围

主Agent核对环境并执行完整门禁、多候选专项、串行窗口和最终保护审计；原生QA `/root/project_integration_qa`独立检查当前接口、编写/执行真实TCP探针、单次诊断及结果复核。角色配置与实际运行均gpt-6.1-terra/high，见[原生元数据](native-agent-metadata.json)。未使用Bridge，没有改角色配置。

本轮未操作Postman/Apifox客户端GUI，不将其脚本运行、界面变量回填或SSE显示记为通过；未测试真实支付、生产认证、多worker或分布式ExactlyOnce。全范围Ruff原有3条E501及其他阶段既有暂缓项保持；新联调探针Ruff/语法检查通过，pip check返回No broken requirements found。未进行开放域路由质量统计或语言偏好全Agent展示承诺。

联调执行已结束；IT-001待后续归因，IT-002需明确展示范围。详细原始响应、单轮失败与补证结果均保留，本轮无Git归档授权，不自动提交推送或进入新开发阶段。
