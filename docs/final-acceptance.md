# V1 最终验收入口

## 用户正式验收与归档授权（2026-11-17）

用户明确要求提交并push06、并入main，再建v2分支开发V2 01；据此记录06正式ACCEPTED及Git集成授权。技术依据沿用下列独立QA和主复核记录，不新增或改写实测结果。Postman客户端脚本/变量回填/SSE界面未实测、Store旧时序观察及原六项暂缓差异保持；接受这些已披露限制不表示它们已经验证通过。Git交付与远端核验以归档回执为准。下文等待用户验收为原2026-11-15历史状态。

更新：2026-11-15。01～05已由用户ACCEPTED并归档；06六Task已独立QA PASS及主Agent技术复核，阶段VERIFIED，06-QA-001已关闭。见[最终交付报告](06-delivery-report.md)、[632独立QA](question/06-delivery-qa-report.md)及[主复核](question/06-integration-main-review.md)。**等待用户正式验收，尚未ACCEPTED；客户端剩余项如下准确保留**。本文不是用户验收结论，不授权Git归档。

## 能力与证据矩阵

全部运行环境为Windows Python3.13.7、单worker、本地Qwen CPU/1024及原Ubuntu PG17.6/vector0.8.7；Chat实际服务商DeepSeek、deepseek-flash、兼容ChatOpenAI/function_calling/reasoning_effort=none。各证据包含自己的实际调用和资源条件，受控故障与真实调用分别归因。

| 能力 / 责任Task | 实现 | 自动/受控验证 | 真实联调出处 | 技术结果与遗留 |
| --- | --- | --- | --- | --- |
| ToolRegistry / Policy / Executor，03、6.1.1 | implemented；发现后执行复核权限、归属和预算 | [03验收](question/03-tool-governance-stage-acceptance.md)、本轮完整门禁见交付报告 | [631首段](06-demo-before-restart-evidence-20261115-r1.json)本人订单，[631重启后](06-demo-after-restart-evidence-20261115-r1.json)模拟退款数据库结果 | 前序verified；user_id为演示选择，非生产认证 |
| HITL审批，04、6.2.1 | implemented；原task/call/args/digest绑定、独立decision与resume | [持久故障独立QA](question/06-persistence-fault-qa-report.md) | [631恢复](06-demo-after-restart-evidence-20261115-r1.json)批准/拒绝与原Actor、实际订单状态 | verified；仅回环development/test、30分钟有效期，无管理员认证 |
| Checkpoint / Interrupt / Resume，04、6.1.2、6.2.1 | implemented；原Task/用量/operation持久恢复，成功只读复用 | [状态事件QA](question/06-state-events-qa-report.md)、[故障QA](question/06-persistence-fault-qa-report.md) | [631两次完整进程重启](06-demo-delivery-report.md)、[04重启矩阵](04-hitl-checkpoint-refund-restart-report.md) | verified；不承诺全局Exactly Once、任意位置恢复或持久事件重放 |
| 真实RAG与来源，05、6.1.1、6.2.2 | implemented；Qwen1024→PG精确余弦→充分性→生成→来源核验 | [隔离退化QA](question/06-isolation-degradation-qa-report.md)，本轮真实prepare回归见交付报告 | [631重启后真实Chat/RAG](06-demo-after-restart-evidence-20261115-r1.json)、[611英语偏好问答](06-assembly-real-evidence-20261114-r5.json)、[05语义评估](rag-validation.md) | verified；不足rejected，技术故障failed；不含ES/Hybrid |
| 用户隔离跨会话Store，05、6.1.1、6.2.2 | implemented；共享Reader/Manager、两偏好、revision/operation幂等 | [隔离退化QA](question/06-isolation-degradation-qa-report.md)、[05验收](question/05-rag-memory-stage-acceptance.md) | [631Memory完整重启/CRUD/A-B隔离](06-demo-memory-restart-evidence-20261115-r1.json) | verified；unknown必须人工核对；关闭即时观测波动保留 |
| 公共接口与演示，6.3.1 | implemented；11端点/26请求/12变量 | [631独立合同与修复复测](question/06-demo-fix-01-regression-report.md)；3项含真实Qwen/PG | 用户截图确认Postman导入；三段真实HTTP及业务核对见[631报告](06-demo-delivery-report.md) | verified；客户端脚本运行、实际回填和SSE界面未实测 |
| 交付复现，6.3.2 | README/配置/固定依赖/数据库配方/证据入口 | [新venv完整门禁](06-delivery-clean-gate-evidence-20261115.json)228/0/0，[安装锁版本](06-delivery-install-evidence-20261115.json) | [隔离镜像实际构建](06-database-reproduction-evidence-20261115-r2.json)、[空双库初始化/幂等/应用就绪](06-delivery-fresh-database-evidence-20261115.json)，原test真实Qwen/Uvicorn启动 | 独立QA PASS/主复核VERIFIED；新空库未seed/重复五能力，前序真实五能力复用单独归因 |

本轮没有机械重复真实付费Chat；上述真实模型/五能力明确复用未变代码的前序证据。模型名称、health initialized、静态集合或受控Node运行均不等于新的真实调用。

## 阶段门禁与用户检查

| 门禁 | 证据状态 |
| --- | --- |
| G0 前置 | 01～05 ACCEPTED，原跨阶段协议差异有明确责任和验收记录 |
| G1 装配 | 6.1.1/6.1.2独立PASS并主复核VERIFIED |
| G2 持久风险 | 6.2.1独立PASS并主复核VERIFIED，实际PG/完整进程重启/提交后快照故障 |
| G3 隔离退化 | 6.2.2独立PASS并主复核VERIFIED，受控Chat/故障注入与真实SQL/Qwen/HTTP明确分开 |
| G4 复现 | 用户确认实际导入；独立Python安装/228全门禁/Qwen服务启动关闭、隔离PG/vector构建和新空双库setup已实测；新空库未seed/重演业务，客户端交互剩余项保留；632独立QA PASS并主复核VERIFIED |
| G5 用户验收 | **尚未给出06正式验收结论；等待用户** |

用户可按[演示操作](demo-walkthrough.md)在新UUID场景中查看本人订单、申请模拟退款、完整退出自有服务后批准原审批并独立resume、核对唯一业务事实、知识来源、Memory跨会话/重启/隔离与CRUD。客户端剩余三项请分别记录实际后置脚本运行、环境变量回填及SSE界面结果。演示结束先关闭自有服务再精确清理，须protected_unchanged=true；不要重发未知副作用。

## 保留限制

- 本地演示身份和审批Actor不构成生产认证；无真实支付、企业多租户、订单取消、分布式调度、持久事件重放、自动unknown恢复或Memory V2候选写入。
- SSE断开不取消执行、重订阅不重放旧token，Run缓存重启丢失。恢复依赖可信安全窗口及原持久关联；未知Checkpoint/原操作结果先核对，不盲目重放。
- [Store历史观察记录](06-state-events-delivery-report.md)曾见关闭后即时查询波动；后续清理/独立QA完整行集通过，原因未定，不由本轮正常关闭结果宣告彻底定因。
- Qwen必须相同本地权重/profile，单实例CPU；用户原.env默认Embedding关闭。资源不足/缺权重/模型不可用须如实失败或标未验证，不用假结果替代。
- 凭据历史暴露/三角色密码复用及六份旧Markdown格式问题沿用户既有决定暂缓，不在交付中自动整改。六项工作区暂缓差异保持：general.py未跟踪、三份旧docs删除、01详细设计原改动、Bridge设计未跟踪。
- 数据库新镜像构建/新空库初始化与已有PG持续运行分别记录；只接受交付报告中的实际结果，不能从配方本身认定全部重建成功。

## 用户验收回执（待用户填写）

验收日期：未填写。06阶段结论：未批准。客户端剩余项：未实测。遗留处理决定：待确认。Git归档/推送授权：未授予。主Agent已完成技术复核并记录VERIFIED，用户明确确认后才能记录ACCEPTED。
