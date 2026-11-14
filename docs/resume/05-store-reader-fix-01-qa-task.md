# 05 / Task5.3.1 / 05-QA-001 独立复测

原QA在主Agent明确派发且原Implementer完成后执行，当前仅准备。必读原FAIL报告、docs/resume/05-store-reader-fix-01-task.md、docs/resume/record/05-store-reader-fix-01-report.md及实际改动。业务/原测试/配置/旧证据只读，不代修；仅独立复测报告和必要临时探针。

以真实testPG非object JSON profile重跑原编译订单路径，确认Store3.2.0解码边界错误已准确分类为failed/memory_profile_invalid、可选记忆unavailable而核心业务继续；未知schema、partial、缺scope零访问、预算/取消不被宽泛吞掉。原安全断言探针05-store-reader-qa-probe.py可以原样重跑；旧corruption观察脚本原本exit0表示缺陷复现，不能将它误当功能测试或为通过改写历史。

核修复无第三方patch/宽泛ValueError/BaseException吞异常、无Store/Policy旁路。自己必要受影响定向+真PG及精确清理，原三Agent/资源退出/隔离门禁可复用未变来源；最终完整门禁需来自修复后版本，清楚区分QA自己跑和引用。在线身份+全部迁移checksum、原public完整行集/列定义保护，只UUID自有profile/thread不seed/开发库写，不Git/Bridge/SSH/PG重启/另派Agent。

输出docs/question/05-store-reader-fix-01-regression-report.md：05-QA-001 PASS/FAIL、命令/真实结果和清理、原Task5.3.1是否可PASS/其他未闭环；不得覆盖原FAIL报告。完成停止交主Agent关闭问题及决定下一Task，不自行进入5.3.2。
