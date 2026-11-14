# Task5.3.1 Store资源与共享Reader

后继准备任务：只在5.2.2验收闭环后由主Agent单独派发，当前不启动。用户2026-11-14授权继续05，按D05第6/9/11节及Task5.3.1、根AGENTS与STATE实现。当前只做Store资源/Manager.snapshot/Reader和三个专业可选读取，显式命令与Manager.apply留5.3.2，不提前写闭环。不得创建MemoryWriter/额外Graph/新服务。

1. 安装版langgraph-checkpoint-postgres3.2.0，先实际签名/源码确认AsyncPostgresStore(conn=ownedpool,index=None,ttl=None)、aget/公开abatch/GetOp/PutOp/setup/context和后台_task关闭。infrastructure/store是唯一私有版本适配点；自有独立小池min1/max3、autocommit、dict_row、prepare_threshold0。Runtime收敛→停止并await Store后台_task→Store退出→池关闭；初始化失败反序释放，无内存fallback或通用队列框架。普通startup只验资源，不自动setup或写用户Item。
2. scripts/setup_store.py显式目标验证，test可由Implementer执行公开setup；仅新增Store库自管schema/tables，不改现有迁移006/知识/业务表。development由主Agent在实现后显式执行schema setup并前后保护数据。已只读核实原agent_app/agent_test各自public CREATE和DB CREATE有效，无需SSH或增权。若需其他权限如实报告，不改pg_hba或密码。setup之外不要业务启动DDL。
3. MemoryManager.snapshot经Infrastructure的aget精确读preference_namespace(trusteduser)->('users',user,'preferences')/profile，Reader只委托Manager，无直接Store/全局asearch/namespace列表。一个profile、schema1/revision/白名单preferences，完整Item<=2KiB、模型偏好<=128tokens；无自由文本/工具消息/last_mutation暴露给模型。未知schema/revision损坏失败，非法单字段partial只采用合法枚举，拒绝非法原值日志。
4. read_preferences空args经原Registry/Policy/Executor，固定node-origin/Agent/task/node白名单为D05第6.1，scope缺失零handler/零Store访问。三个专业准备节点共享读取每Task至多一次，记忆不会改变原业务事实、审批参数、归属、金额或工具权限；退款恢复不重跑准备。技术unavailable可默认呈现，Policy denied保持denied而非成功empty；预算耗尽/Runtime取消不能降级继续。当前本轮用户语言风格高于偏好。
5. 正确持久Saver序列化/累计工具预算/稳定nodeID/call_records，读取节点记录不伪造AI/ToolMessage。新增safe状态available/empty/partial/unavailable/denied，偏好只有zh-CN/en及concise/detailed。Order/Refund确定性回复不重写事实；不用个性化借机重构业务。Memory显式查看和写入不提前称可用。
6. 真PG Store测试必须证明A跨两个conversation/thread读取、B不可见、完整新Python进程仍可读取，实际资源正常/异常关闭和取消分类；缺scope零访问、技术降级/partial/坏schema、消息及预算。fixture可直接经Store适配写唯一测试profile，不称已支持用户保存；配置测试用户使用独立唯一名单，原真实Demo用户profile绝不能覆盖。显式清理仅本轮namespace/key（底层adelete仅隔离fixture清理），原业务/Saver/知识/他人Store完整行集保护。只agent_demo_test/agent_test，在线身份与完整schema/checksum核对；不seed或删固定订单。
7. 依赖尽量复用已有package不盲升级；受影响测试、实际完整真实库门禁（公共节点变化）、Ruff/格式。只报告真实运行，无环境标BLOCKED，不能skip当验收。配置集中config/.env.example，不覆盖真实.env。

交付docs/05-store-reader-delivery-report.md、必要脱敏证据/显式脚本及README导航。不得改STATE/AGENTS/旧证据，主Agent负责状态/QA/开发库setup。不Git/SSH/Bridge/派其他Agent，不自动做5.3.2或06。QA修复需记录docs/resume/record关联原Task/编号/提示词。完成后停止。
