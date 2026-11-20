# V2 03 Gemini交付接管与独立QA

2026-11-20，用户明确授权接管六Task初步实现，独立QA、最小修复、真实隔离模型/PG验收及前序回归。不重新设计冻结V2 03，不写正式数据库，不Git提交推送，技术QA全部通过后停止等待人工验收。

最新：六Task均VERIFIED，[最终独立QA](qa/v2-03-final-qa-report.md) PASS，主Agent据此关闭QA-001～008；r2完整回归322 passed/0 failed/0 skipped，保护比较、真实Qwen及启停通过。技术工作已停止，等待人工验收和Git授权，未ACCEPTED、未暂存/提交/推送。完整实现/证据/局限见[阶段交付报告](v2-03-stage-delivery-report.md)。以下过程状态保留历史语境。

## 接管与实际配置

- 分支v2、HEAD 1f3d73643af84fdc55f7f314d6c0db6f0c34560a。接管时16个tracked修改、新Selector和单测试模块；另有四个原有无关文件，见[基线](evidence/v2-03-takeover-baseline.json)。原Gemini tracked diff保存在.git私有文件，原未跟踪源码hash已记录。
- 只发现根AGENTS.md。已读用户级/项目级config.toml及已有implementer/qa角色。两角色及项目子Agent默认Terra/high，主模型不随之改变；原生派发显式指定角色、gpt-6.1-terra、high、fork_turns=none，不修改配置或使用Bridge。
- 首轮独立QA为/root/v203_takeover_qa，原生会话01a1f886-f895-7a02-944b-b61446544762，实际qa/Terra/high及继承权限已核对，见[运行元数据](evidence/v2-03-native-qa-metadata.json)。QA只读为行为约束，并非额外只读沙盒。
- 冻结设计hash 847c4387bd24a0f8b64d4dd1d233ddf9daf5338b1c20781bf282e6b7bc3bbfe5，正文不改。

## 六Task接管时审查（历史状态）

| Task | 冻结交付 | 当前状态 |
| --- | --- | --- |
| 3.1.1 | 目录视图与版本契约 | BLOCKED：等待依赖修复与完整版本/回归验证 |
| 3.1.2 | Agent/权限/用途筛选 | BLOCKED：等待真实权限/业务回归 |
| 3.2.1 | 结构化选择与预算 | REQUIRES_FIX：预算/中断门禁修复中 |
| 3.2.2 | Schema解析与执行一致性 | BLOCKED：待绑定/Policy/执行一致性及真实链路 |
| 3.3.1 | 复用、重发现与恢复 | REQUIRES_FIX：待调用/失败次数/中断门禁修复中 |
| 3.3.2 | 真实选择与V1兼容验收 | REQUIRES_FIX：付费入口安全、唯一夹具与真实完整证据未交付 |

## 环境与首轮证据

原本轮专用Windows PG56422和Linux PG56431在线，四个Linux隔离库身份/PG17.12/comment只读guard通过；复用专用容器与独立卷，不接触正式容器/库。DeepSeek已配置flash，认证只读GET /models返回200且列出该模型，见[连通性回执](evidence/v2-03-provider-connectivity.json)。这不证明Chat或完整链路成功，也不足以将历史EOF归因于环境或代码。

首轮受控定向9 passed/2 deselected；真实opt-in用例未执行，非PASS。审查发现Gemini的真实PG用例缺独立付费opt-in门禁和唯一数据/事实核验，未直接投入完整默认回归。独立QA已复现：无旧记录但pending时仍Selector；摘要抢占最后业务调用额度；失败重发现未留下消耗计数。完整编号、修复与复测以后续独立报告为准，不以本记录替代QA结论。

## 首轮修复与边界裁决

[独立初审](qa/v2-03-initial-qa-report.md)六项编号均保持开放，含五项P1门禁缺口和一项P2，真实完整验收尚未运行。原生implementer /root/v203_fix01_impl（01a1f88c-2bd4-7200-ad25-3964e54c09bf）已接[fix01](fixes/v2-03-fix01.md)，实际Terra/high及原QA多轮参数见[原生运行元数据](evidence/v2-03-native-runtime-metadata.json)。

真实PG/Saver复现节点异常导致尝试少计，不把它称进程终止；[裁决001](v2-03-main-decision-001.md)允许同thread下Task专属Checkpoint消费/未决记录，仅用现有Saver公共API，不新增业务表、Graph节点、通用journal或Store替代。原独立QA只读审查认为方向与冻结相容，要求实际提交关联、预留非预消费、去重单调下限和unknown/fail-closed；这不是修复验收。

后续另取得真实独立进程os._exit(71)及新进程读回证据，记录实际选择/重发现后attempt下限2、rediscovery1和inflight，而主checkpoint仅见1；thread均精确清理。完成确认及实际Runtime/旧审批/重试/新Run接线仍在开发验证，不能用基础namespace读写替代完整门禁。

专用SSH通道曾中断，确认专用容器running、原启动时间及RestartCount0；仅重启本轮helper，第一轮guard超时，随后四库guard与容器内pg_isready通过。失败记录保留，未切换正式环境或提高超时来制造通过。

本轮五题[独立选择质量夹具](evidence/v2-03-selector-quality-fixtures.json)与[hash回执](evidence/v2-03-selector-quality-fixture-receipt.json)已在接管后真实模型调用前固定；不声称早于未知Gemini尝试。真实模型测试改为显式手动入口，与默认零付费/零skip的旧完整门禁分开，尚未实际执行，不报PASS。

## fix01 后续验证与第二轮修复

开发者已取得真实模型手动组2 passed（五题独立选择、get/list两条真实PG链路，共9次调用），原始记录见 `evidence/v2-03-fix01-manual-real-guarded.txt`。该记录中文need存在终端编码损坏，不能补造还原为线上捕获；独立QA将在fix02稳定后执行一次ASCII安全证据复验。该组不替代独立QA或默认完整门禁。

原QA的[fix01第一阶段复测](qa/v2-03-fix01-retest-report.md)仍FAIL，新增007/P1（持久写入耗时侵占业务预留期限）、008/P2（业务context_view覆盖Selector用量）。原Implementer按[fix02](fixes/v2-03-fix02.md)修复，原001～006尚未正式关闭。

完整默认回归首轮在216项后继续8项通过、2项失败，随后停在审批恢复重复提交测试的无界Event等待；原始[日志](evidence/v2-03-full-regression.log)保留，执行会话已中断，PID38988已退出。没有完整pytest汇总和finally保护比较报告，严格记为 `INTERRUPTED_NOT_PASS`。另存[中断后只读指纹](evidence/v2-03-full-regression-interruption.json)，它不证明前后相等。原测试Graph未提供新持久化所需Saver契约是待独立trace确认的原因；由原Implementer定位，不以删除测试或生产静默降级处理。修复后须重新运行完整门禁取得真正的before/after比较。

fix02已稳定交付，见[开发记录](fixes/records/v2-03-fix02-report.md)：121项受控组合通过，随后补充测试诊断导入、退款模块10项通过，相关Ruff/format通过。首次选择与重新发现均在首个持久写前固定期限，逐provider调用后置复核；Selector独立回执、unknown与恢复映射已实现。三个退款测试替身补Saver契约并保留原断言，生产安全检查不降级。上述仍是开发自测；原QA已接独立实测窗口，源码暂停修改，PG写测试及真实模型严格串行，主Agent完整回归等待QA结束。

原QA已完成串行实测并释放数据库窗口：42项纯受控、2项真实PG定向通过；真实Saver的异常、完整提交确认、新Run和独立子进程强退采用独立probe，另复核运行现有重发现/新Run及旧审批probe，证据性质分别记录。无损真实手动组2 passed，共9次调用4345 known tokens，固定五题5/5、两条SQL/归属/分页/配对ToolMessage通过，新增行清理0。真实成本对照HEAD旧Order builder和当前图各2次业务调用、Selector0，同一单工具Schema约83估算tokens/相同SHA；已知tokens1173→1192，单次耗时2.509→2.349秒，样本不足以归因收益，且旧builder共享当前其他依赖。

主Agent在QA确认全部PG/模型进程结束后启动完整默认门禁r2，付费opt-in清空，原门禁脚本未修改；私有驱动在原始snapshot返回时立即保存只读指纹，并输出逐node进度。等待实际结束及原QA复核后才裁决阶段状态。
