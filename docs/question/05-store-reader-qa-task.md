# Task5.3.1 独立QA

仅主Agent在Implementer完成后显式派发才开始。依据根AGENTS/STATE、docs/05-store-reader-execution-task.md、D05第6/9节/5.3.1及实际交付报告。业务/测试/配置/旧证据默认只读，仅写独立报告或临时复现，不Git/SSH/Bridge/另派Agent/重启PG，不代修。

独立核资源：实际安装3.2.0公开API、外部自有独立池indexNone/ttlNone/不自动setup，异常反序清理、Runtime先收敛、后台任务停止await和外部池关闭，私有任务接触仅Infrastructure一处，不假aclose/CAS或取消未提交保证。

核Reader只委托Manager.snapshot，只有Manager精确namespace/profile通过适配aget，可信身份/固定枚举/2KiB/128token边界，不全局列namespace/自由文本/历史聊天/非法值进入日志。未知schema/revision明确失败，含非object JSON profile的损坏数据也应安全分类而非AttributeError打断可选业务；非法单字段partial，empty和unavailable/denied不混淆；scope拒绝零handler/Store、技术降级可继续业务、预算/Runtime取消不伪装可降级错误。三个专业同Reader节点origin/Task/node allowlist、稳定ID/私有记录/预算、每Task至多一次，退款恢复不重读、不改审批事实/金额。

自己的真实专用PG Store验证：唯一A/B固定测试用户名单，A不同conversation/thread可读同profile、B不可见、完整新Python进程仍可读；显式fixture写不是用户显式保存能力，apply/命令留5.3.2。保护原业务/Saver/知识/他人Store全行集，身份+所有checksum，精确清理自己的namespace/key不覆盖真实Demo用户，开发库不跑测试。正常/异常关闭和取消分类、缺scope/坏schema/partial/技术不可用至少必要复测。最终完整门禁可引用未变Implementer报告不无收益重跑全量，缺真实环境标BLOCKED不skip伪通过。

输出docs/question/05-store-reader-qa-report.md：PASS/FAIL仅Task、沿当前05-QA编号续号/严重程度/位置复现、自己实际命令/结果/清理、完整门禁来源和未验风险。失败交主Agent退回原Implementer不代修，完成停止不进5.3.2。
