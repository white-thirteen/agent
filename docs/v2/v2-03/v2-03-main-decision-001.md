# QA-004：Task专属Checkpoint预留边界裁决

主Agent，2026-11-20。依据[冻结设计](v2-03-tool-registry-progressive-disclosure-detailed-design.md)4.3、7、8、12节及[真实Saver探针](evidence/v2-03-fix01-saver-probe.json)：内存已消费1，但节点失败后的完整checkpoint仍为0；重放后实际调用2次而快照只见1。不能以sync节点提交替代调用前持久预留。

冻结要求“预留和调用用量不得因新Run、澄清或Checkpoint重放清零”“记录和计数属于内部Task状态”“首版不新增业务数据库表，记录随现有Checkpoint保存”，并禁止新增生产Graph节点、改前序治理边界。冻结没有要求将预留当作节点完成，也没有承诺模型/Checkpoint全局Exactly Once。

## 允许的最小实现

使用已注入的现有Saver公共API，在同一thread的Task专属namespace内保存**本阶段专用的消费/重新发现预留及未决标记**。不建新业务表、不用Store替代、不改Saver底表、不新增Graph节点或通用journal服务。这是上述冻结持久要求的实现方式，不改变Task、Run、业务审批及模型预算的权威归属。

实施前提：

1. 生命周期复用现有Checkpointer和会话互斥；namespace由可信thread/task派生，所有者及来源checkpoint关联明确，不由模型或请求指定。
2. 外部调用前先提交预留，失败/超时/进程终止不退还；计数为Task单调下限，并与已提交主快照核对，不凭新Run清零。业务预留及压缩仍不得绕过原Scope/Gateway上限。
3. 正常选择记录及selected_tools仍按现有Graph显式映射保存，后者是派生投影。专属预留不伪造Selector结果、不将部分pending writes当完整节点，也不在旧Checkpoint中注入未来选择/工具版本。
4. 主Graph结果尚未提交而进程中断时，明确保留in-flight/unknown并fail closed，不能盲目免费重选。只有证明主Graph实际提交对应结果后才确认相应未决标记；不能靠内存成功或叠加视图证明提交。
5. 仅支持现有Runtime公开的正常最新Task恢复；旧审批/待执行调用走原版本/Policy、零Selector。来源不匹配或不确定则明确拒绝，不能宣称支持任意时间旅行。
6. 测试与清理使用公共Saver API，thread清理覆盖专属namespace；保存实际中断/新进程、失败重发现、成功提交、旧记录及新Run不重置的证据。异常存储不能静默降级到内存预留。

原Implementer按此最小范围执行，并交原独立QA重点复验。若实现必须扩大为通用平台、跨业务持久层、改写旧Checkpoint或突破以上约束，停止该部分并报告具体裁决点，不自行扩张。本裁决不授权正式库迁移、Git或新的阶段。
