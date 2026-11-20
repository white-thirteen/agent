# V2 03 接管与技术交付报告

Git授权附记：用户在技术交付后明确指示“提交并push git”，现按本阶段范围归档到`origin/v2`；下文未提交/等待Git授权为技术交付时快照。技术状态仍为VERIFIED，不从Git授权推导额外人工ACCEPTED。最终提交及远端核验见后续归档回执。

日期：2026-11-20。主Agent复核[最终独立QA](qa/v2-03-final-qa-report.md)及原始门禁后，裁决六Task均为 **VERIFIED**，V203-QA-001～008全部关闭，无未关闭技术阻塞。本阶段技术开发及QA已停止，等待人工正式验收与Git归档授权；未ACCEPTED、未提交或推送。

## 接管结论与范围

Gemini已留下六Task的初步代码，但缺少阶段交付和完整真实门禁，不能据此判断API EOF发生前已完成验收。接管时保存了HEAD、22项脏文件及hash（含4项无关遗留），并在私有`.git`保存原始tracked diff。独立QA复现了预算、恢复、重发现计数和状态映射问题；原实现经两轮最小修复后完成定向独立复验。历史EOF没有足够原始材料归因；本次真实模型复验未出现EOF。

冻结依据仍为[设计原文](v2-03-tool-registry-progressive-disclosure-detailed-design.md)，SHA-256 `847c4387bd24a0f8b64d4dd1d233ddf9daf5338b1c20781bf282e6b7bc3bbfe5`，未修改冻结指标。协调、所有失败及裁决分别见[接管记录](v2-03-takeover-ledger.md)、[初审FAIL](qa/v2-03-initial-qa-report.md)、[fix01/fix02独立复测](qa/v2-03-fix01-retest-report.md)和[Checkpoint边界裁决](v2-03-main-decision-001.md)。

## 六Task及契约映射

| Task | 实现与关键位置 | 当前技术状态 |
| --- | --- | --- |
| 3.1.1 目录视图与版本 | `app/tools/models.py`、`registry.py`：brief/full Schema分离、冻结目录版本、所选工具版本及Schema摘要 | VERIFIED |
| 3.1.2 三层筛选 | `app/tools/discovery.py`、工具metadata：Agent、权限、可信用途筛选；控制/内部工具不进入业务目录 | VERIFIED |
| 3.2.1 结构化选择与预算 | `app/tools/selector.py`、Runtime Scope/Gateway及compactor：确定性/单候选短路、结构化输出、B次业务保留、绝对期限及回执 | VERIFIED |
| 3.2.2 绑定与执行一致 | 三个专业builder及Registry/Gateway：选择后解析完整Schema，执行集合不大于绑定；Policy/Executor和参数约束继续逐次复核 | VERIFIED |
| 3.3.1 复用与恢复 | 主/子State白名单、`selection_reservation.py`、Runtime：同Task复用、最多一次重发现，原调用/审批/unknown不重选，旧Checkpoint不伪造选择 | VERIFIED |
| 3.3.2 真实业务及回归 | 显式手动模型入口、测试专用多候选Node、独立真实Saver及成本probe；完整回归322项、数据保护及最终独立复核通过 | VERIFIED |

没有新增生产Agent、业务Graph节点或Loop，没有扩大生产单工具用途或权限；业务事实仍来自正式Domain/SQL调用，摘要不是订单或审批权威。现有Saver公共API在同thread的Task namespace保存调用消费下限和未决关联，不新增业务表或改Saver底层表。Graph完成快照与未决预留分开确认；无法证明已完成时拒绝继续，不承诺外部调用与Checkpoint全局ExactlyOnce。Selector回执是内部数据，与02业务context_view及维护预算分离，不输出到公共facts/SSE。

## 问题闭环

| 编号 | 原问题 | 定向修复及复验依据 |
| --- | --- | --- |
| QA-001/P1 | 压缩占用业务模型预算 | compactor为当前及已知后续业务调用保留次数与时间，B=1/B=2及真实PG运行内压缩受控模型验证 |
| QA-002/P1 | pending无记录仍重新选择 | 缺记录锁定拒绝；旧审批样本Selector零调用，原调用/参数/版本/主体不变，副作用一次 |
| QA-003/P1 | 失败重发现不计数 | 发起即消费、失败携带记录，真实Saver强退后rediscovery下限仍为1 |
| QA-004/P1 | 节点重放丢失外部消费 | 调用前Saver持久下限，真实异常/独立进程强退、完整提交确认和新Run验证 |
| QA-005/P2 | Order绑定与输出选择记录不一致 | 更新记录、派生投影和绑定同时返回，可信目标变化及历史变化分别验证 |
| QA-006/P1 | 付费入口及真实验收不完整 | 默认测试不收集付费入口，显式opt-in、在线隔离guard、唯一数据和SQL/分页/归属核验 |
| QA-007/P1 | 慢持久写侵占预留期限 | 首次及重发现写入前固定总期限，逐次写后调用前重核；不足时真实provider零调用 |
| QA-008/P2 | Selector用量被业务上下文覆盖 | 独立Task/Run回执，成功/失败及known/unknown分开，父子/新Run映射和按ID去重 |

原独立QA定向复测、r2完整门禁及最终独立只读复核通过，主Agent据此正式关闭八项技术问题。原FAIL、开发失败、通道故障和乱码输出都保留，未改写为PASS。完整回归首次中断时暴露的退款Graph测试替身缺Saver契约，经实际失败trace确认后补足受控契约，保留业务断言；异步等待可有界报告失败，生产路径不降级。

## 实际验证与资源

- 开发fix02受控组合121 passed；随后仅补测试诊断导入，退款模块10 passed。独立受控42 passed，真实隔离PG定向2 passed。详细命令、记录性质及原始输出见[开发记录](fixes/records/v2-03-fix02-report.md)与独立复测报告。
- 独立真实Saver覆盖节点异常、完整提交确认、新Run及独立子进程`os._exit(71)`；唯一thread及namespace均清理。独立自编probe与复跑已审查开发probe分别注明，不把替身业务称真实模型或生产副作用。
- 独立[真实模型手动组](evidence/v2-03-independent-real-manual.log)2 passed：固定五题合法/适合均5/5，5次Selector共2466 known tokens；两个测试专用多候选Node各两工具候选，经真实Selector→Registry→Gateway→原生ToolCall→Policy→Executor→真实PG，4次调用1879 known tokens。单单1行及列表分页2行同SQL一致、外用户排除、ToolMessage配对，新增数据清理0。
- 五题fixture SHA-256 `1a3e596e1b7d684a64a25f08b26203c95a8d6209d07093875e967e12b6430725`保持。独立原始字节日志无U+FFFD，ASCII JSON还原需求与fixture逐字一致；开发早期乱码捕获另存，未以fixture回填冒充线路证据。
- [真实生产单工具对照](evidence/v2-03-independent-real-cost.log)：HEAD旧Order builder与当前各2次业务模型、1次工具、Selector零调用，Schema同SHA且约83/83估算tokens；已知tokens1173→1192，单次耗时2.509→2.349秒。旧builder共享当前其他依赖、最小Registry无可用偏好工具，不能称完整旧环境或归因收益；没有虚构全目录基线。该组SQL匹配布尔值有原始记录，比较逻辑见独立probe，新增行清理0。
- 独立真实模型合计13次、6710 known tokens、0 unknown，禁用自动模型重试。开发先前一次手动组9次/4340 known tokens单列，不与独立样本混为一轮。
- 完整默认回归首轮为[INTERRUPTED_NOT_PASS](evidence/v2-03-full-regression-interruption.json)，仅after-only不能证明前后相等。修复后的[r2原始日志](evidence/v2-03-full-regression-r2.log)为 **322 passed / 0 failed / 0 skipped**，3条依赖/pytest警告；[门禁汇总](evidence/v2-03-full-regression-r2.json)正常退出0，总435.796秒，pytest400.08秒。付费opt-in为空、默认范围不收集手动付费用例；汇总paid_chat_calls=0是原verifier静态声明，非独立网络计数。原固定订单seed窄例外原样运行、恢复原值，protected_unchanged=true，知识watermark58→69恰为11次已审计发布增量（共享库9次及task131同库2次）。真实Qwen、Uvicorn健康检查、连接池关闭及无残余执行任务/Embedding线程通过，V1/V2 01/V2 02默认回归均包含。
- r2实际私有包装器/原始字节捕获驱动的源码已逐字保存为[wrapper文本](evidence/v2-03-full-regression-r2-wrapper-source.txt)、[capture文本](evidence/v2-03-full-regression-r2-capture-source.txt)及[SHA回执](evidence/v2-03-full-regression-r2-driver-source-receipt.json)，供归档复核；这是已执行源码的文本副本，不是另一次运行。原始驱动不含凭据，私有环境文件不归档。
- 受影响文件Ruff/format通过。全范围`ruff check app tests`有3项HEAD既存E501，非本轮新增且相关文件无diff；见[范围说明](evidence/v2-03-main-ruff-scope.md)，不宣称全范围Ruff通过。依赖LangGraph弃用及旧样本反序列化警告如实保留。

真实数据库仅使用已标记隔离环境：Linux PG17.12/vector0.8.7及专用测试四库（SSH本地56431），Archive组件使用另行guard的Windows scratch PG56422；未连接或修改正式数据库。SSH通道曾故障，仅恢复已核对本轮helper，容器无重启/切库。真实模型沿配置deepseek-flash，测试窗口/输出16384/512为测试显式值，不修改`.env`。

## 原生Subagent与工作区

主Agent负责冻结依赖、接口裁决、串行窗口、主复核和交付。原生`implementer` `/root/v203_fix01_impl`负责fix01/fix02；原生`qa` `/root/v203_takeover_qa`独立审查、复现与复测。均为 **gpt-6.1-terra / high**，来源为项目`.codex/config.toml`和角色TOML，实际`session_meta`/`turn_context`见[运行元数据](evidence/v2-03-native-runtime-metadata.json)，不以自述代替。用户级默认配置不用于替代角色要求；未修改角色或模型配置，未使用Bridge。

分支`v2`，HEAD `1f3d73643af84fdc55f7f314d6c0db6f0c34560a`。本轮代码、测试、导航及V2 03交付/QA证据均未暂存、提交或推送。[工作区清单](evidence/v2-03-git-workspace.json)和[建议归档范围](v2-03-git-archive-proposal.md)供后续人工授权使用；原4个无关untracked文件继续排除，私有`.git`凭据/helper不得归档。[保护复核](evidence/v2-03-protection-audit.json)核对4文件hash、649份前序文档及冻结设计保持，已知凭据值扫描无命中。

## 未覆盖及停止边界

仅覆盖所列真实/受控场景，不推断任意故障组合、真实旧生产Checkpoint或跨进程旧审批全链路均已验证。真实模型样本规模有限，不证明总体选择质量或资源收益；Schema tokens为估算，未知请求结果仍按unknown处理。V1既有客户端脚本/变量回填/SSE界面未实测等历史暂缓项不因本轮测试改成通过。

六Task技术VERIFIED，独立QA PASS，主Agent复核完成。技术QA工作已停止，等待用户人工验收与Git归档授权，不自动ACCEPTED、提交、推送或进入后续开发。
