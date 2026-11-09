# 02 数据、身份与会话生命周期基础——阶段详细执行设计

> **历史设计方案，不再作为 V1 开发依据。** 自2026-11-08起，当前规划见[Agent Engine Demo定位与评估](../agent-engine-demo-plan.md)及[六阶段路线图](../development-roadmap.md)。下文原审核状态只适用于旧电商目标；可复用片段及新适用范围见评估清单，不能按旧任务直接开发。本轮保留原文，不删除代码或旧设计。

状态：**审核通过，待开发执行**。整体方案已认可并纳入数据契约修订；03 补充明确首次 200 SSE、幂等重复 200 JSON，303 不采用。设计通过不代表实现或验收。

整理日期：2026-11-08。依据：[整体路线图](../development-roadmap.md)、[01 正式设计](01-stage-detailed-design.md)。本次固化只写文档，不代表数据库、认证、仓储、测试或联调完成。

## 1. 起点、目标与边界

实际代码：infrastructure/postgres.py、workflows/models.py、repository.py、manager.py 均为职责占位；工作流 router 为空；Settings 只有预留 database_url；Runtime 按用户/会话计算 thread 并使用内存 Saver，无可信绑定与互斥。

已有 psycopg、psycopg-pool、langgraph-checkpoint-postgres 依赖可以复用。此前只核对了本地接口，没有连接数据库。

本阶段交付数据库资源、迁移、可信身份、持久会话绑定、workflow/run 元数据、幂等受理和授权查询。不启动 Graph、不持有执行任务、不实现 Checkpoint、审批或支付。01 设计已通过但尚未实际验收；对应接口集成不能假定存在。

## 2. 2.1 PostgreSQL 开发环境与资源管理

### 2.1 方案与组件

采用 psycopg 异步池、显式 SQL 仓储和编号 SQL 迁移，不新增 ORM/迁移框架。建议 PostgreSQL 17 作为开发基线，实际执行时验证并锁定补丁与镜像摘要；不使用浮动 latest。pgvector 留到 07。

配置集中在 core/config.py，示例更新 .env.example：运行连接 SecretStr、迁移连接、池最小/最大规模、连接/获取/启动等待超时。开发库与测试库独立，凭据不提交、不打印。运行账号与迁移 DDL 权限区分。

应用元数据使用 agent_app Schema。迁移命令按编号校验摘要、取得互斥、事务执行并写版本。已应用迁移不可原地修改；失败回滚；启动只校验所需版本，不按请求建表。后续 LangGraph 自有迁移不混入应用版本表。

资源生命周期：验证配置 → 创建未打开的池 → 显式异步 open/wait → 校验 Schema → 注入服务 → 接收请求 → 关闭并释放。Manager 定义事务，Repository 使用传入连接且不提交。事务不跨模型、网络或 Graph 执行。

无数据库配置时存活检查仍可用，数据相关功能不可用；配置了但无法连接或版本不符时不得伪报就绪，不静默改用内存业务。agent_ready 原有图装配含义不等于全部依赖就绪。

### 2.2 执行任务

| 任务 | 实现内容与文件 | 依赖 | 完成标准/交付 |
| --- | --- | --- | --- |
| 2.1.1 数据环境与配置 | Compose、config、示例；锁定版本和隔离配置 | 1.1 | 干净环境启动；凭据安全；测试库独立 |
| 2.1.2 Schema 迁移入口 | 编号 SQL、版本摘要和互斥、显式迁移命令 | 2.1.1 | 重跑稳定；失败回滚；旧迁移变更可检测 |
| 2.1.3 异步资源 | postgres.py、lifespan、依赖注入 | 2.1.1 | 等待有界、连接释放、错误不泄密 |
| 2.1.4 就绪与失败边界 | 启动版本校验和安全错误 | 2.1.2、2.1.3 | 无配置和故障均不伪就绪 |
| 2.1.5 集成验收 | 独立数据库测试和运行说明 | 前四项 | 实际初始化、资源、失败测试通过 |

## 3. 2.2 可信身份与会话绑定

### 3.1 身份契约

区分调用方身份、被代理用户和权限范围。首版使用配置型服务凭据认证可信后端，由该后端声明用户及权限，与服务允许范围取交集；不在 Python 实现用户登录或令牌签发系统。

模式：

- development_mock：显式启用，仅 development/test、回环或隔离测试网络；Apifox 可声明模拟 user_id，权限来自服务端模拟配置，不构成真实认证。
- trusted_backend：Authorization Bearer 验证服务；X-Authenticated-User-ID 等可信声明提供用户。请求体 user_id 必须匹配，不可覆盖。可信后端负责剥离外部伪造头并重新声明；传输使用受保护通道。
- 未配置：需要身份的业务不开放。缺权限不默认全权；服务调用凭据不等于管理员审批权。

Principal：client_id、user_id、permission_scopes、authentication_mode，不携带凭据。后续排队执行还需授权有效性/重新核验，具体由 3.3 设计，不从旧任务复原永久权限。

组件：core/identity.py 定义不可变身份；infrastructure/identity.py 验证配置调用方；api/dependencies.py 注入 Principal；会话服务与仓储处理绑定。Graph 不认证。

### 3.2 会话表与绑定

conversations：id（内部 UUID 主键）、user_id、conversation_id、thread_id、created_at/updated_at（timestamptz）。UNIQUE(user_id,conversation_id)、UNIQUE(thread_id)，另提供 UNIQUE(id,user_id) 供归属组合外键引用。

同用户同逻辑会话只有一个绑定，不同用户可用相同 conversation_id 但 thread 不同。thread 服务端生成并持久保存，普通请求不可更换。当前内存开发快照在切换时明确重置，不自动迁移；未来有持久快照时不得静默换 thread。

流程：认证 → 校验用户一致 → 按用户/会话读绑定 → 不存在则事务创建 → 唯一竞争后读取已提交绑定 → 返回 SessionBinding。仅处理明确唯一竞争，不宽泛吞异常。

全局权限不足 403、认证失败 401；资源不存在和跨用户不可见统一 404，避免泄露存在性。

### 3.3 执行任务

| 任务 | 工作与文件 | 依赖 | 完成标准/交付 |
| --- | --- | --- | --- |
| 2.2.1 模式与 Principal | config、身份模型、有限权限 | 1.3、2.1 | 生产拒绝模拟；不保存凭据 |
| 2.2.2 可信调用验证 | 身份组件和 API 依赖 | 2.2.1 | 错凭据、错用户拒绝；权限不越界 |
| 2.2.3 会话仓储 | 编号迁移、绑定 Repository | 2.1、2.2.1 | 并发仅一绑定，不跨用户复用 |
| 2.2.4 上下文接入 | 绑定服务、应用依赖 | 2.2.2、2.2.3 | 上下文来自持久绑定，客户端不指定 thread |
| 2.2.5 隔离验收 | HTTP、并发创建、重启读取测试 | 前四项 | 认证/模拟边界、跨用户隔离及绑定稳定 |

真正使用绑定执行 Graph 留到 3.3。

## 4. 2.3 WorkflowRepository 与生命周期管理

### 4.1 权威来源与关系

用户 → 多会话；会话 → 一个稳定 thread、多个顺序 workflow；workflow → 多个 run。Principal 决定身份；conversations 决定绑定；workflows/runs 决定受理和元数据；Checkpoint 保存图快照；Domain Service 决定真实业务事实。逻辑 workflow 记录不等于订单或退款申请。

### 4.2 数据模型（含最终修订）

| 表 | 核心字段与约束 |
| --- | --- |
| workflows | workflow_id（字符串主键）、conversation_fk、user_id、status、current_run_id、version、outcome、安全 result_summary/error_code、创建/更新/结束时间 |
| runs | run_id（UUID 主键）、workflow_id、**user_id（可信 Principal 来源）**、client_id、kind、idempotency_key、request_hash、status、outcome/error_code、previous_run_id、受理/开始/结束时间 |

归属外键：workflows(conversation_fk,user_id) → conversations(id,user_id)；workflows 提供 UNIQUE(workflow_id,user_id)，runs(workflow_id,user_id) 引用它。不能通过重复 user_id 产生不一致归属。

current_run 约束：runs 提供 UNIQUE(workflow_id,run_id)；workflows(workflow_id,current_run_id) 组合外键引用它。使用可延迟关联约束或事务内先建 workflow、run 再设置引用，提交时活动 workflow 的 current_run_id 必须非空。最终约束组合需在迁移测试中验证，不能仅用两个彼此无关的单列外键。

幂等 UNIQUE(client_id,user_id,idempotency_key)。同 workflow 最多一条 queued/running/reconciling run。按活动状态建立会话的部分唯一约束，不能仅靠先查后写。

时间使用带时区类型；状态采用有限值检查，版本以条件更新递增。Repository 不接受任意身份覆盖。

### 4.3 request_hash 与 workflow_id

摘要来自规范化的**请求命令**：协议版本、命令类别、conversation_id、请求提供的 workflow 引用/新建提议（或显式 NEW 标记）及消息。不含服务端随后生成的最终 workflow_id、run_id、thread_id、时间或凭据。

当前聊天请求保持 01 的必填 workflow_id；它是调用方关联提议，不授权覆盖已有归属。内部新建命令与续接命令应明确区分：续接必须解析已授权的最终 ID；新建由服务端登记最终 ID，结果返回调用方，后续续接使用最终 ID。HTTP 如何表达新建提议须在 3.3 接线审核中明确，不能把无法解析的既有 ID 静默当成新建。不得未经协议确认将字段变成可选或增加隐式别名。

受理先按可信作用域和 key 找记录，再比原始规范化命令摘要；首次分配最终 workflow_id 不影响 hash。重复请求沿用首次原始命令和 key，不能先生成新 ID 再比较，也不能把首次原请求字段改成返回 ID 后仍当作完全相同命令。此规则消除循环依赖，不依赖具体 HTTP 新建入口形式。

### 4.4 状态与活动槽位

Workflow 活动：running、waiting_input、waiting_approval、paused、reconciling；终结：completed、rejected、failed、cancelled。所有活动状态占会话槽位。

Run：queued、running、reconciling、completed、failed、waiting_approval、paused、cancelled。

- workflow running 表示已经受理并占槽，不等于模型正在调用；run queued 表示本次尚未领取，二者可以同时成立。
- reconciling 表示旧执行结果或副作用待核对，禁止继续推进、普通聊天重试或释放槽位；不等于支付失败，也不作为 SSE 新终态。
- 03 对不确定运行保留 reconciling；后续核对才能转明确终态或通过新 run 安全重试。不得将 reconciling 原 run 直接重新变 running。创建后继 run 前在同事务终结原 run，保留核对结论。
- 等待审批的 run 已结束，workflow 仍活动；批准后新 run 恢复同 workflow/thread。

| 事件 | Workflow | Run/结果 |
| --- | --- | --- |
| 新目标受理 | running | 新 queued |
| 领取并开始 | running | running |
| 缺用户输入 | waiting_input | completed / needs_input |
| 同目标补充 | running | 新 queued |
| 完成 | completed | completed / answered |
| 业务拒绝 | rejected | completed / rejected |
| 审批等待 | waiting_approval | waiting_approval |
| 安全暂停 | paused | paused |
| 确定失败 | failed | failed |
| 崩溃/副作用结果不明 | reconciling | reconciling，撤销旧推进权 |
| 核对后安全恢复 | running | 新 queued；原 run 已有核对结论 |
| 确定安全取消 | cancelled | 对应 run 结束 |

终结 workflow 不通过普通聊天重激活。审批/暂停/核对期间普通聊天 409。waiting_input 只允许续接或经受控规则切换/放弃；不允许模型清除副作用约束。断开不改变业务状态。

### 4.5 幂等与事务

受理请求需要 Idempotency-Key；长度和字符规则在接口接线中固定。相同作用域/key/命令复用原 run，内容冲突 409；新补充、新恢复使用新 key 和新 run；网络重试沿用原 key；run 幂等不替代业务操作幂等。幂等记录随 run 保留，不单独过期。

Manager.admit_chat(principal,binding,command,key) → AdmissionResult(final_workflow_id,run_id,created|existing)，不代表 Graph 已启动。

事务：验证关联 → 查幂等 → 锁会话 → 重查幂等 → 校验 workflow/活动槽位 → 建/更新 workflow、run、current_run 和 version → 提交。唯一冲突先回滚，再读取已提交记录比较摘要。锁顺序会话→workflow→run；Manager 持事务，Repository 不提交。默认明确行锁/约束，不以全库最高隔离级别代替设计。

状态命令：mark_run_started、finish_run、get_workflow、get_run；当前 run、预期版本一起匹配；联合更新原子；相同终态重复可复用，矛盾终态拒绝，旧 run 不覆盖新状态。无通用 set_status HTTP 接口。

3.3 必须在同一受理事务写持久执行输入/任务，02 只提供共享连接事务边界。Checkpoint、网络、支付不参与此原子事务。6.3 才管理审批决定和恢复待办。

**重复受理 HTTP 响应同步 03 定稿补充**：首次 HTTP 200 text/event-stream，幂等重复 HTTP 200 application/json（ExistingRunResponse：版本、existing 标记、公开关联和查询/订阅地址），内容冲突 409 JSON；不采用 303。OpenAPI 在 200 下列出两类媒体类型，客户端按 Content-Type 分支，不重执行、不承诺重放。细节见 [03 架构](03-stage-detailed-design.md)第 7 节。

### 4.6 查询及开放门禁

GET /agent/workflows/{workflow_id} 和其 runs/{run_id} 返回授权可见的标识、各自状态、当前 run、结果、安全摘要及时间，不返回 thread、快照、消息、摘要哈希或内部异常。run 必须属于目标 workflow。

03 接入前通过内部仓储集成测试验证受理，公开执行入口不制造无人执行的 queued 记录；查询可以用真实测试记录验收。配置数据层后不能绕过元数据管理开放旧业务执行路径。

### 4.7 三级任务

| 任务 | 工作与模块 | 依赖 | 完成标准 |
| --- | --- | --- | --- |
| 2.3.1 模型与状态机 | workflows/models.py；本稿标识、状态、转换 | 01、2.2 | running/queued 与 reconciling 无歧义 |
| 2.3.2 迁移与事务仓储 | repository.py、SQL；归属/组合外键、活动唯一约束 | 2.1、2.2.3、2.3.1 | 跨 workflow 的 current_run 不能入库，部分写入回滚 |
| 2.3.3 幂等受理 | manager.py、命令/结果、摘要 | 2.3.2 | 首次生成 ID 无循环；并发只一 run；改内容冲突 |
| 2.3.4 生命周期 | 条件更新、当前 run、版本和核对状态 | 2.3.3 | 重复稳定、迟到拒绝、不盲目解除核对 |
| 2.3.5 授权查询 | routes/workflows.py、Schema、身份依赖 | 2.2、2.3.4 | 最小输出、权限隔离、关联正确 |
| 2.3.6 并发与衔接验收 | 数据库竞争/回滚测试、交接记录 | 前五项 | 活动冲突、幂等、核对门禁通过，无 Runtime/审批假实现 |

## 5. 一致性审核、顺序和总体验收

顺序 2.1→2.2→2.3。身份验证和绑定仓储可独立准备测试，迁移按编号串行。数据库约束管活动/受理，3.3 管实际执行互斥；Checkpoint 不是状态仓储。

统一验收：

- 环境、迁移、连接关闭可复现，开发与测试隔离，异常不泄密或静默降级。
- 正式身份可信，模拟限受控环境，跨用户资源不可见。
- 会话并发创建唯一、重启 thread 稳定。
- 同会话并发受理不同 workflow 仅一成功；相同 key 仅一 run；摘要与生成 ID 无循环。
- runs.user_id 与归属一致，current_run 组合关系由数据库保证。
- 缺输入可新 run 续接，审批和核对不能由聊天恢复。
- 状态联合更新、回滚、迟到防护和 reconciling 门禁经真实数据库验证。
- 查询安全；03 未接入前受理门禁有效；数据库用例未运行不可宣称阶段完成。

## 6. 审核与变更记录

整体方案已审核认可。固化补充：可信 runs.user_id；请求摘要不依赖最终 workflow_id；Run reconciling 及占槽/推进约束；current_run 组合外键；workflow running/run queued 语义。重复响应已随 03 本轮补充定为 200 JSON，首次为 SSE；新建 HTTP 命令表达仍须在公开接线前确认。

03 同步约束：排队授权仅保存最小引用和有效期，执行前按当前来源复核；03 自身迁移 executor_guard、任务 payload 版本/owner/epoch/token 和预算记录，02 不提前实现执行器。run/workflow 的 reconciling 与外部副作用未知分开记录，不因 SSE failed 变业务失败。查询需支持最小公开结果，01 信封枚举不变。

本轮只固化设计；数据库、身份和仓储代码尚未实现或验收。执行时记录实际变更及结果，不将设计状态当完成状态。
