# 4.1 订单查询领域服务与模拟数据——详细设计与执行计划（待审核）

> **历史设计方案，不再作为 V1 开发依据。** 自2026-11-08起，当前规划见[Agent Engine Demo定位与评估](../agent-engine-demo-plan.md)及[六阶段路线图](../development-roadmap.md)。下文原审核状态只适用于旧电商目标；可复用片段及新适用范围见评估清单，不能按旧任务直接开发。本轮保留原文，不删除代码或旧设计。

状态：**待审核；未开发、未迁移、未进行数据库或业务验收**。

编制日期：2026-11-08。范围仅为 4.1，保留九阶段、34 环节。初稿按用户要求单独设计，本版作为 [04 全阶段设计与执行计划](04-stage-execution-plan.md)的一部分复用，未重做项目进度调查；跨环节补充见第14节。

依据：[整体路线图](../development-roadmap.md)、[01 正式设计](01-stage-detailed-design.md)、[02 数据设计](02-stage-detailed-design.md)、[03 架构](03-stage-detailed-design.md)、[03 执行计划](03-stage-execution-plan.md)。本文新增选择均为建议，不自动成为已确认规范。

## 1. 当前工程现状与依赖

### 1.1 实际核验

| 内容 | 当前事实 | 对 4.1 的影响 |
| --- | --- | --- |
| 工程 | Python 3.13.7 基线、FastAPI、Pydantic、psycopg、LangGraph；requirements.in 已包含 psycopg[binary,pool] | 沿用，不改框架或升级依赖 |
| app/infrastructure/postgres.py | 只有职责说明 | 02.1 连接池不是现成能力 |
| infrastructure/checkpoint.py/store.py | 占位 | 不作为订单事实来源，不在本环节补齐 |
| workflows/models/repository/manager | 占位 | 不复用一个不存在的通用仓储实现 |
| Principal/SessionBinding | 02 已定义，代码中没有对应模型与验证入口 | 集成必须等 2.2 交付；不能直接相信 user_id 字符串 |
| app/domain、订单表、订单服务 | 未创建、未实现 | 4.1 需要新增其最小领域/适配模块 |
| main.py | 启动模型与内存主图，无数据库生命周期 | 复用未来 2.1 池，4.1 不另建池或在请求里建表 |
| config.py | 仅预留 database_url；无订单配置 | 仅补必要超时/模拟数据设置，集中维护 |
| core/errors.py | 只有 AgentNotReadyError | 订单领域异常另放领域层，不混成 HTTP 错误 |
| core/logging.py | 基础 logging，尚非完整结构化关联日志 | 沿用日志接口，不记录 SQL 参数、消息、凭据和完整订单 |
| 测试 | 四个既有测试文件，集中在 HTTP/类型/Graph | 没有订单或 PostgreSQL 业务验收，历史通过不等于本环节通过 |

上次4.1编制时仅阅读源码和设计、核验工作区；本轮不重复调查，仅复用该记录并补跨环节契约。未连接 PostgreSQL、运行迁移、初始化数据或重跑测试。原有修改保持不动。

### 1.2 前置依赖与可独立工作

- 4.1.1 模型和查询规则可先设计/开发并做纯单元验证。
- 真实落库和集成必须等待 2.1 的池、编号迁移、运行/迁移权限、独立测试库验收。
- 真实权限接入等待 2.2 的 Principal；独立领域测试可以构造明确测试 Principal，但不能当作认证验收。
- 不要求执行订单查询时先存在 conversation 或 workflow；订单归属属于用户业务身份，不属于聊天会话。SessionBinding 由上游管理，不进入 OrderService 查询参数。
- 03 提供未来运行预算、日志关联和模型治理；4.1 本身没有模型、Graph、任务或订阅依赖，可在 2.1/2.2 就绪后独立验收。
- 完整 Agent/工具联调等待 4.2～4.4，不能作为 4.1 当前交付物。

## 2. 目标、范围与领域边界

目标是 PostgreSQL 支撑的、可核对的用户订单事实来源。LLM 不计算金额、不选择可信用户、不编造状态或物流。OrderService 不依赖 LangChain/LangGraph、AgentType、ToolRegistry、HTTP Schema 或 WorkflowRepository。

本轮查询：订单详情、本人列表、单状态筛选、创建时间范围、游标分页、本人物流。无取消、退款、支付、状态修改 API、库存、优惠、税费、商家分账、购物车或商品主数据系统。

模拟初始化是受控开发数据管理，不是用户业务写工具；不能通过聊天调用。后续 Java 适配保留相同领域契约，不使 Agent 获得数据库连接。

## 3. 订单领域模型

### 3.1 类型与基本约束（建议）

- ID 为区分大小写的不透明字符串，去首尾空白、1～64 字符；不要求 UUID、不解析编码中的用户/状态。owner_user_id 复用可信用户 1～128 字符规则。
- 金额 Python Decimal、PostgreSQL NUMERIC(12,2)，拒绝浮点输入、非有限值、负数或超过 9999999999.99 的值。对外 JSON 统一两位十进制字符串，禁止 float 转换。
- V1 仅 CNY；订单金额、商品价格继承同一币种，未来多币种需显式扩展。
- 数量为严格整数 1～9999，布尔值不当整数接受；一单至少一个商品行，V1 最多 100 行。
- 时间为带时区 datetime/timestamptz，持久和返回统一 UTC；用户时间必须有明确时区，拒绝猜测本地时间。
- 只保存查询需要的商品名称/SKU 快照，不建立商品库存或动态价格关联。

### 3.2 模型与关系

| 模型 | 必要属性 | 说明 |
| --- | --- | --- |
| Order | order_id、owner_user_id、status、currency、order_amount、paid_amount、created_at、paid_at、completed_at、cancelled_at、data_origin | 订单归属一名用户；owner 不在公开结果中重复暴露 |
| OrderItem | order_id、line_no、sku_id、product_name、unit_price、quantity、line_amount | 一对多；名称/价格是下单快照 |
| Shipment | order_id、carrier_name、tracking_number、status、shipped_at、delivered_at | V1 一单至多一票，不支持拆单、多包裹、轨迹点 |
| OrderSummary | order_id、status、currency、order_amount、paid_amount、created_at、data_origin | 列表用最小摘要，不装配全部商品 |
| OrderDetail | 订单公开字段、items、logistics | 同一次一致读装配 |
| LogisticsView | order_id、fulfillment_status、shipment 或空、data_origin | 无发货数据返回 not_shipped，不伪造物流 |
| OrderPage | items、has_more、next_cursor、data_origin | 无强制 total_count，不多做全表计数 |

data_origin 固定 local_simulation，表示数据均为本地模拟；金额和 paid_at 仅描述模拟订单事实，不表示调用过支付系统。

### 3.3 状态语义

OrderStatus：pending_payment、paid、shipped、completed、cancelled。所有状态允许本人查基本信息与商品，不因状态隐藏归属校验。

| 订单状态 | 查询应有数据 | 本地模拟不变量 |
| --- | --- | --- |
| pending_payment | 基本/商品；物流 not_shipped | paid_amount=0，无 paid_at/发货/完成/取消时间 |
| paid | 基本/商品；物流 not_shipped | paid_amount=order_amount，有 paid_at |
| shipped | 基本/商品/一票物流 | 已付款，物流 in_transit，有 shipped_at |
| completed | 基本/商品/签收物流 | 已付款，物流 delivered，有 completed_at/delivered_at |
| cancelled | 基本/商品；物流 not_shipped | V1 样本为发货前取消；有 cancelled_at，可为未付或已付历史快照，不推断退款结果 |

ShipmentStatus：in_transit、delivered；not_shipped 是查询投影，不造一条假物流记录。暂不设计丢件/退货等状态。时间按真实顺序校验。以上是本地样本一致性，不是 05 的取消资格或 06 的退款规则。

跨表商品总额和物流/订单状态一致性由初始化事务验证、详情读取的领域一致性检查保证；不写无法跨表成立的 CHECK。未来写业务必须维持不变量，本轮不增加复杂跨表触发器。

## 4. PostgreSQL 结构与安全隔离

使用 02 已定 agent_app Schema 和编号 SQL 迁移；实际迁移编号排在当时最后已应用版本之后，不能固定抢占尚未落地的 02/03 编号。

### 4.1 orders

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| order_id | varchar(64) | 主键，非空非纯空白 |
| owner_user_id | varchar(128) | 非空，来自业务归属/固定模拟用户 |
| status | text | CHECK 五种 OrderStatus |
| currency | char(3) | CHECK = 'CNY' |
| order_amount | numeric(12,2) | BETWEEN 0 AND 9999999999.99，排除特殊非有限数 |
| paid_amount | numeric(12,2) | BETWEEN 0 AND order_amount |
| created_at | timestamptz | NOT NULL |
| paid_at/completed_at/cancelled_at | timestamptz | 可空，存在则不早于 created_at；与本行状态/付款语义一致 |
| data_origin | text | NOT NULL CHECK = 'local_simulation' |
| seed_key/seed_version | varchar(80)/integer | 仅受控种子使用；seed_key UNIQUE；二者同时为空或同时有效，版本>0 |

提供 UNIQUE(order_id,owner_user_id) 供子表复合外键。CHECK 覆盖本行的付款时间/金额关系、完成/取消时间互斥：pending_payment 无付款；paid/shipped/completed 全额已付且 paid_at 存在；completed 必须 completed_at 且不早于 paid_at；cancelled 必须 cancelled_at。取消行保留实际模拟付款历史，不能自动改 paid_amount 为零。

不将 owner 外键关联 conversations：用户可能有订单但没有会话，且同用户有多会话。当前没有用户主表，不凭空建立认证用户库。owner 与 2.2 的外部用户 ID 使用同一命名语义。

### 4.2 order_items

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| order_id/owner_user_id | varchar(64)/varchar(128) | 组合外键到 orders(order_id,owner_user_id) |
| line_no | smallint | 1～100；PRIMARY KEY(order_id,line_no) |
| sku_id | varchar(64) | 非空，商品快照标识 |
| product_name | varchar(200) | 非空，纯数据，不作为指令 |
| unit_price | numeric(12,2) | 有限非负且不超过金额上限 |
| quantity | integer | 1～9999 |
| line_amount | numeric(12,2) | 生成列 unit_price*quantity；约束不超过金额上限 |

商品重复 SKU 可以是不同快照行，不设 SKU 全局唯一，不建商品表。订单金额应等于商品行金额之和；初始化和详情领域检查明确验证，禁止声称 FK 已保证总额。

### 4.3 order_shipments

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| order_id | varchar(64) | 主键，一单至多一票 |
| owner_user_id | varchar(128) | 与 order_id 构成归属外键 |
| carrier_name | varchar(80) | 非空且标识模拟承运商 |
| tracking_number | varchar(80) | 非空，模拟单号；不因相同单号暴露他人订单 |
| status | text | CHECK in_transit/delivered |
| shipped_at | timestamptz | NOT NULL |
| delivered_at | timestamptz | delivered 必填且>=shipped_at，in_transit 为空 |

不设物流单号全局唯一业务假设，不提供按单号跨订单检索。发货不得早于付款由领域一致性检查验证。子表外键默认禁止级联删除，后续清理须显式从子到父；本环节没有删除业务接口。

### 4.4 必要索引

- orders(owner_user_id,created_at DESC,order_id DESC)：本人列表与游标。
- orders(owner_user_id,status,created_at DESC,order_id DESC)：单状态筛选。
- order_items 复合主键支持详情；order_shipments 主键支持单票。
- 不为商品名、金额、物流单号等未支持筛选建索引。真实测试用 EXPLAIN 核对用户/排序条件可利用索引，但小数据优化器选择顺序扫描不直接判失败。

### 4.5 数据库层用户隔离（待审核建议）

仅 Python 判断后按全局 ID 读取不满足安全要求。建议同时采用：可信 Principal、SQL 显式 owner 谓词、三张表的 PostgreSQL RLS。

运行角色非 superuser、非表 owner、无 BYPASSRLS，无角色切换/DDL 权限；订单三表仅授予 SELECT，ENABLE/FORCE ROW LEVEL SECURITY。每表仅对运行角色的 SELECT 策略：

```sql
USING (
  owner_user_id = NULLIF(current_setting('agent.order_user_id', true), '')
)
```

每个短只读事务中，查询前参数化执行：

```sql
SELECT set_config('agent.order_user_id', %s, true);
```

值只取 Principal.user_id。true 表示事务局部，提交或回滚后不保留当前用户。池创建时禁止配置会话级同名身份；所有订单查询必须由 read_scope 设置，不能先执行订单 SELECT 再补。未设置或空值应不可见，测试复用同一连接验证成功/异常后不串用户。若发现池连接带不应存在的会话级身份，拒绝使用并修复池配置，不默认信任。

子表重复 owner 由复合外键强制与订单一致，不能给 A 的订单插入 B 的商品/物流。缺少连接上下文、遗漏 owner 谓词时，运行角色也不能读到其他用户行。SQL 仍显式 WHERE owner_user_id=%s AND order_id=%s，不能以 RLS 为理由放弃查询范围。

RLS 是数据库防漏查条件边界，不是抵御任意已攻陷数据库凭据或任意 SQL 执行的沙箱；共享角色可以设置会话变量，服务端可信绑定和参数化 SQL 仍必要。表 owner/超级用户不能用于用户隔离验收。种子使用独立受控数据管理角色和明确写策略，不让运行角色获得写权。

这是对 02 运行/迁移权限区分的领域扩展，不重建连接池或认证系统。依据：[PostgreSQL 17 RLS](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)、[事务局部配置](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-ADMIN-SET)。

### 4.6 一致读和迁移边界

详情/物流由短期 REPEATABLE READ READ ONLY 事务装配订单、商品和物流，避免多条 SELECT 读到互相不一致版本；列表单语句也可使用相同 read_scope。RLS 设置在该事务内完成，不持事务跨模型/工具调用；返回 DTO 后关闭资源。该读取隔离不改变 02 元数据写入的锁/隔离方案。依据：[PostgreSQL 17 事务隔离](https://www.postgresql.org/docs/17/transaction-iso.html)。

迁移创建表、约束、策略及权限；种子另行显式执行，不塞进 Schema 迁移、应用启动或普通请求。未来 05/06 用新增迁移扩展规则、操作和支付记录，不改已应用迁移；没有现存订单表时不预建历史兼容层。

## 5. Repository 与 Domain Service

### 5.1 目录与职责

以下为将来开发文件，本轮不创建代码目录：

```text
app/domain/orders/
  models.py       # 领域模型、查询参数及只读 DTO
  errors.py       # 领域异常
  repository.py   # 订单专用查询端口，不做通用 CRUD 基类
  service.py      # 权限/查询规则和结果组织
app/infrastructure/orders/
  repository.py   # PostgresOrderRepository，参数化 SQL/映射
  read_scope.py   # 复用 02 池、事务局部身份和只读事务
  seed.py         # 仅开发/测试的固定种子
tests/
  test_order_service.py
  integration/test_order_queries.py
```

迁移路径复用 02 最终目录；不另建一套 migrations runner。现有 app/services 保持请求编排职责，OrderService 放 domain；工具在后续 app/tools 适配，不把数据库查询放 API/Graph。

### 5.2 核心接口

概念签名（异步，非逐行实现）：

```python
class OrderService:
    def __init__(self, read_scope): ...
    async def get_order_detail(self, principal: Principal, order_id: str) -> OrderDetail: ...
    async def list_orders(self, principal: Principal, query: OrderListQuery) -> OrderPage: ...
    async def get_order_logistics(self, principal: Principal, order_id: str) -> LogisticsView: ...

class OrderRepository:  # 领域查询端口
    async def find_order(self, owner_user_id: str, order_id: str) -> Order | None: ...
    async def list_orders(self, owner_user_id: str, criteria, limit_plus_one: int, seek) -> list[OrderSummary]: ...
    async def list_items(self, owner_user_id: str, order_id: str) -> list[OrderItem]: ...
    async def find_shipment(self, owner_user_id: str, order_id: str) -> Shipment | None: ...
```

read_scope(user_id) 是订单专用异步上下文工厂：借用 02 池连接→开启只读一致事务→设置局部 owner→提供 PostgresOrderRepository→提交/回滚并归还。领域服务通过端口调用，不 import psycopg；适配器依赖 psycopg。Repository 不提交、不决定身份、不造业务事实；模型/工具永远拿不到 Repository 或连接。

OrderService 只依赖普通 Python、Decimal/datetime、现有通用校验库和 core.identity 的 Principal，不依赖图框架。Principal 尚未实现时标前置依赖，不私造一个接受任意 user_id 的“兼容 Principal”。

### 5.3 业务入口流程

1. 校验 Principal 有 orders:read（本稿建议统一名称），不接受列表参数中的 user_id。
2. 在服务边界验证参数，构造规范化查询；内部可信 Repo 不再次逐字段复制/校验。
3. 使用 Principal.user_id 打开 read_scope。
4. 所有 SQL 限用户；详情先查本人订单，None 统一 OrderNotFound，不再发全局查询区分“他人订单”。
5. 装配 items/物流；验证必要数据不变量，不能用空商品/猜测总额静默兜底。
6. 返回不含用户身份/凭据/内部对象的只读 DTO，释放事务。

单例 OrderService 仅保存工厂，不保存当前用户、连接、查询结果或可变游标。数据库调用超时取配置和上游剩余预算允许范围；4.1 先用数据库查询超时，03/4.3 的预算接线后由工具执行入口协调，不另建 BudgetManager。

### 5.4 查询参数和结果

| 能力 | 参数 | 返回与边界 |
| --- | --- | --- |
| 详情 | order_id | 本人 OrderDetail；不存在/他人统一不可见 |
| 列表 | status 可空；created_from/to 可空；page_size；cursor 可空 | 只返回本人 OrderPage；无结果为空，不报不存在 |
| 状态 | 五枚举之一 | 单状态等值，非法拒绝；V1 不提供任意表达式/多状态组合 |
| 时间 | 带时区上下界 | 按 created_at，from 包含、to 不包含；两者都有时 from<to；单边可用 |
| 分页 | page_size 默认20，1～50；cursor 最多1024字符 | keyset，不提供任意页号跳转；多取一条判 has_more |
| 物流 | order_id | 先校验本人订单；合法未发货返回 not_shipped/shipment=null，不伪造轨迹 |

OrderListQuery 不含 owner、SQL、sort、权限或模型指令。时间不支持未解释的“昨天”等自然语言，后续工具/Agent 转成明确带时区范围后调用。

固定 ORDER BY created_at DESC, order_id DESC，后续页加 (created_at,order_id)<(cursor_time,cursor_id)，全部参数化。cursor 版本1包含 last_created_at/last_order_id/filter_hash，base64url 编码的有界 JSON。filter_hash 绑定当前用户、状态、时间范围，客户端改变筛选应重新从首页查。

cursor 非认证凭据，不需要为只读 seek 额外建设签名系统；校验版本/格式/时间/长度/筛选绑定，SQL 与 RLS 永远仍限当前用户。可构造游标最多改变本人分页位置，不获得他人访问权。不把可解码游标当加密；不放原始 user_id 或凭据。last row 已删除不要求重新存在，仍按边界继续。

page_size 可在下一页改变，排序/筛选不可变；has_more=false 时 next_cursor=null。并发插入/状态变化下各页不承诺同一个长期数据库快照，固定 keyset 避免 offset 漂移，但不宣称跨请求绝不漏项；需强快照导出是后续独立需求。

金额 JSON 使用字符串、时间 ISO 8601 UTC，data_origin 固定模拟。OrderPage 无 results_summary 模型生成字段，不让 LLM 代替查询结果。

### 5.5 错误与日志

| 错误 | 语义及处理 |
| --- | --- |
| OrderPermissionDenied | 无 orders:read，不查库；上游映射权限拒绝 |
| InvalidOrderQuery | 非法 ID/枚举/数量/时间/游标；不执行 SQL |
| OrderNotFound | 他人和不存在统一安全消息，不暴露归属 |
| OrderQueryTimedOut | 实际查询超时；无自动无限重试 |
| OrderStorageUnavailable | 已知连接/池不可用等，不能返回“订单不存在”或空列表 |
| OrderDataIntegrityError | 已读数据违反商品总额/状态物流等不变量；不编造补齐 |

数据库适配器只转换明确的连接/超时错误；SQL 语法、列缺失等编程错误正常暴露到安全执行边界，不能全部转“暂时无订单”。原异常不透传用户；日志只记安全码、耗时、数量及上游提供的关联 ID，SQL 参数/商品全文/数据库 DSN 不记录。本环节不新增 HTTP 订单路由，也不直接生成 SSE 或 SpecialistResult；后续 adapter 统一映射 01/03 的业务拒绝、缺输入或执行异常。

## 6. 本地模拟数据与初始化

### 6.1 样本集

使用固定数据而非 random/当前时间：demo-user-a、demo-user-b、demo-user-c 各5单，分别覆盖五状态，每单2个商品行；另有 demo-user-empty 无订单用于空查询。物流只为 shipped/completed 各一票，合计6票，明确模拟承运商和 DEMO 前缀单号，不含真实地址/手机号。

固定 order_id 如 demo-a-pending、demo-a-paid、demo-a-shipped、demo-a-completed、demo-a-cancelled；B/C 对应相似命名，便于 A 查询 B 的跨用户测试。示例金额如59.90和20.00*2，总额99.90，验证 Decimal 及数据库精确一致。固定 UTC 时间，并刻意有多个订单同 created_at，测试第二排序键。取消样本同时覆盖历史未付款/已付款快照，但不描述退款是否成功。

返回 data_origin=local_simulation；数据“已付/已签收”只是模拟记录，不是第三方支付或物流联调结果。不存在的商品、物流不能由 LLM 补齐。

### 6.2 初始化流程与幂等

显式开发 CLI 复用 02 配置/迁移版本检查，禁止启动自动写样本。仅 app_env=development/test 且目标为对应明确允许的数据库，production 拒绝，不提供 --force 绕过。独立种子角色可写样本，运行角色仅 SELECT；RLS 的种子策略只适用于该角色和合法 seed_key，不能向运行角色开放管理权限。

事务流程：核对环境/Schema→取得固定样本集事务互斥→按 seed_key/version 检查现存数据→验证所有已有样本符合当前版本→只插入缺失的完整订单/商品/物流→检查总额/归属/物流不变量→提交→报告插入/已存在数量。失败全部回滚。

已有相同样本内容重复初始化不变；遇到被后续取消业务修改的数据或种子版本冲突，安全报告 SeedConflict，不重置、不批量覆盖、不删库。不能用无条件 ON CONFLICT DO UPDATE 把用户测试状态刷回初始值。部分旧样本缺子记录视为不一致并报告，不静默修复；新缺失完整样本可补插。

seed_version 新版本采用显式升级方案或新的 seed_key，不能覆盖旧迁移。测试每次在专用测试数据库中事务/专用命名空间隔离，禁止清理开发库。测试结束的清理目标需验证；不提供默认 reset 全库命令。

## 7. 与后续工具和 Agent 的兼容

未来链路：OrderAgent→ToolExecutor→OrderTool→OrderService→OrderRepository→PostgreSQL。这里只固定调用契约，不实现前三层。

- get_order_detail：适合订单 ID 详情工具，参数只暴露 order_id。
- list_orders：适合本人列表工具，参数为有限筛选/分页，不暴露 owner/SQL。
- get_order_logistics：适合物流问题，避免为物流读取整个订单或泄漏无关商品。

工具 schema 从领域参数约束适配，不直接把 Principal/连接变成模型可填字段。ToolExecutor 以后注入可信 Principal，经 Policy 检查执行集合、权限、预算后调用；Domain 仍检查 orders:read 和归属。Schema 发现不授权，直接领域内部测试不构成未来运行时绕过策略的例外。

返回 typed DTO，adapter 负责 JSON 的 Decimal/时间、结果裁剪和安全错误转换；不把完整 Repo、异常或原始行暴露给模型。工具超时与 Budget 在 4.3 接，查询摘要和 SpecialistResult 在 4.4 接；本稿不设计其循环、Prompt、发现目录或执行器内部流程。

## 8. 三级开发任务及具体步骤

### 4.1.1 订单领域模型设计与落地

- 目标：冻结最小事实模型、金额时间和只读查询契约。
- 步骤：确认本稿关键决策→新增模型/枚举/DTO/错误→定义 OrderListQuery 和游标结构→定义仓储端口→记录金额字符串与 UTC 映射。
- 文件：domain/orders/models.py、errors.py、repository.py；不提前建取消/退款模块。
- 接口：OrderStatus、ShipmentStatus、OrderDetail、OrderPage、OrderListQuery、OrderRepository。
- 依赖：01 标识/错误原则；Principal 使用 2.2 契约，不假定已经有代码。
- 局部测试：查询边界、Decimal 非有限/精度、时间范围、游标格式与筛选绑定；复用参数化用例，不逐字段机械穷举。
- 完成：领域模块无 Graph/LLM/HTTP/psycopg 导入；类型、规则及序列化约定一致。
- 交付：模型、端口、异常和少量纯测试。

### 4.1.2 PostgreSQL 表结构与迁移

- 目标：真实持久表、归属约束及数据库防越权。
- 步骤：等 2.1 迁移验收→分配新编号→orders/items/shipments→金额/状态/时间 CHECK、复合 FK→索引→运行只读权限/RLS→测试角色与局部身份验证。
- 文件：02 迁移目录新增 SQL，必要角色授权说明；不修改已应用迁移或另写 runner。
- 接口：三表、两类列表索引、RLS 身份变量契约。
- 依赖：2.1 实际验收、4.1.1；RLS 与权限选择经审核确认。
- 局部测试：真实 PG 迁移重跑、非法金额/枚举/FK 拒绝；运行角色缺/错身份不可读；子表错 owner 插入失败。
- 完成：不依赖 Python WHERE 也能阻止跨用户读取，且测试非超级用户。
- 交付：编号迁移、角色/策略、真实数据库约束记录。

### 4.1.3 OrderRepository 实现

- 目标：参数化、限用户、有界且一致的查询。
- 步骤：复用池构造 read_scope→只读一致事务与局部 owner→实现四方法→固定排序/seek/limit+1→映射 Decimal/datetime→限定数据库错误转换。
- 文件：infrastructure/orders/repository.py、read_scope.py，必要 config 示例。
- 接口：PostgresOrderRepository、read_scope；无 SQL 字符串暴露给上游。
- 依赖：4.1.1/4.1.2、2.1 资源；不依赖 Runtime/ToolRegistry。
- 局部测试：真实 PG 对比返回/源行；注入样式 ID 仅当数据；同连接 A→B→无上下文/回滚后不串；同时间分页稳定。
- 完成：SQL 参数化且都含 owner，事务和连接释放，缺库/超时不伪造空列表。
- 交付：Repo、读作用域、数据库测试。

### 4.1.4 OrderService 实现

- 目标：唯一领域查询入口，集中权限、参数和结果规则。
- 步骤：检查 Principal/orders:read→参数规范化→受限 read_scope→详情/列表/物流装配→检查跨表不变量→安全领域异常和 DTO 输出。
- 文件：domain/orders/service.py、必要 models/errors，应用生命周期依赖装配（仅订单服务资源，不接 Agent 路由）。
- 接口：get_order_detail/list_orders/get_order_logistics。
- 依赖：2.2 实际身份契约、4.1.1/4.1.3。
- 局部测试：纯替身只测服务规则；真实 Repo 额外验证归属、金额和物流；无权限不借连接。
- 完成：他人/不存在统一不可见，未发货是正常结果，异常不冒充业务事实；单例无用户状态。
- 交付：Service、装配、规则测试和真实 PG 集成记录。

### 4.1.5 模拟数据初始化

- 目标：可重复、可核对、多用户固定数据。
- 步骤：建立固定样本→开发目标验证→种子角色/事务互斥→校验已存在→插入缺失完整样本→检查总额/时间/归属/物流→输出安全数量摘要。
- 文件：infrastructure/orders/seed.py、开发数据说明/CLI 入口；无真实个人数据。
- 接口：初始化命令及 SeedResult(inserted,existing,fixture_version)，冲突抛 SeedConflict。
- 依赖：4.1.1/4.1.2，配置/连接复用 2.1；可与 Repo/Service 实现并行。
- 局部测试：真实测试库首次/重复、并发初始化、冲突回滚、production/错误数据库拒绝、开发库未触及。
- 完成：重复执行不改旧数据；样本满足声明不变量；不为方便联调重置状态。
- 交付：固定种子、显式初始化、结果说明和验收记录。

### 4.1.6 订单查询能力集成验收

- 目标：以真实 PG 证明“可信用户→Service→Repo→落库事实”闭环。
- 步骤：独立测试库迁移→种子→运行只读角色→本人/越权/筛选/分页/物流→异常/资源/数据隔离→核对文档和未来工具入参样例。
- 文件：tests/test_order_service.py、tests/integration/test_order_queries.py、数据库 fixture；README/本设计的实际结果记录。
- 接口：三个 Service 方法、真实查询及种子命令。
- 依赖：前五项、2.1/2.2 实际验收；4.2～4.4 不作为前置，也不代为实现。
- 局部测试：见下一节矩阵；不依赖付费模型或内存字典替代数据库。
- 完成：数据库关键用例全部实际运行并通过，测试跳过或只有 Mock 不能计完成；无业务写 API。
- 交付：集成报告、必要代码检查结果、已知限制和后续适配交接。

## 9. 推荐执行顺序与依赖

4.1.1→4.1.2→4.1.3→4.1.4→4.1.6；4.1.5 在表结构稳定后可与 4.1.3/4.1.4 并行准备。领域校验测试与样本草拟可早做；真实迁移/权限测试必须等 02 基础设施。多个任务修改同迁移/公共模型时串行合并，不新增子 Agent 要求。

本轮只设计，以上均为未来执行步骤。业务开发前先审核关键选择，不以写完文件作为完成证据。

## 10. 集成测试与统一验收

| 场景 | 必要断言 | 验证层 |
| --- | --- | --- |
| 正常详情 | 状态/金额/商品与源行一致，Decimal 精确、UTC 正确、来源为模拟 | Service+真实 PG |
| 跨用户 | A 查 B 和未知订单得到同一不可见语义，无商品/物流泄漏 | Service+运行角色 RLS |
| 数据库防越权 | 故意省略 owner WHERE 仍不能看到其他用户；无局部身份无行 | 直接运行角色 SQL |
| 子表归属 | 错 owner 的商品/物流 FK 拒绝；未授权子表 SELECT 不泄漏 | 真实 PG 约束/策略 |
| 无权限 | orders:read 缺失时不执行查询 | 服务规则+集成 |
| 非法参数 | 空/过长 ID、非法状态、无时区或反向时间、坏游标、0/超大 page_size 拒绝 | 纯规则+调用边界 |
| 分页 | 空、恰好一页、多一条、尾页、同 created_at、筛选改变、他用户游标绑定拒绝；无稳定数据重复/漏单 | 真实 PG |
| 状态与时间 | 五状态各匹配；from 边界包含、to 边界排除；单边时间正确 | 真实 PG |
| 物流 | shipped 一票、completed 签收；未发货正常空；非法归属不泄漏 | 真实 PG |
| 一致读 | 两连接在详情多查询间修改样本时，本次读仍同一快照；不得混旧金额/新商品 | 真实 PG 同步屏障 |
| 数据损坏 | 种子/管理端构造跨表不一致，Service 报 integrity 而不编造 | 独立测试库 |
| 池复用 | 同一连接 A/B/异常回滚/无身份后无串用户，资源归还 | 真实 PG 限制池规模 |
| 数据库故障 | 实际独立测试连接失败/有界查询超时返回存储/超时错误，不是 NotFound/空列表 | 真实 PG 故障用例 |
| 种子 | 首次数量、二次不变、并发一次、冲突全回滚、非开发目标拒绝 | 真实 PG |
| 环境隔离 | 显式验证测试库标识；测试清理后开发库样本指纹不变 | 两个独立测试/开发验证目标 |

隔离验证不主动修改或清理用户实际开发库：验收使用两个专用验证库模拟 dev/test，或取得已配置开发库的只读指纹；不因测试需要破坏真实开发数据。数据库异常用专用目标，不停用户开发服务。

检查策略：纯领域少量单测；真实 PG 负责 FK、RLS、事务、分页和种子，不能用 SQLite/Mock 代替。集成测试需要独立显式配置，默认未配置可跳过但报告必须写“未验证”，不得因此宣布 4.1 完成。运行项目 .venv 测试/Ruff；没有依赖变更不重新安装环境。当前设计轮不执行这些命令。

4.1 完成条件：前置数据/身份验收、三方法可独立调用、关键 DB 用例真实通过、无凭据/跨用户泄漏、模拟属性明确、无取消退款写入口、默认运行账号订单只读、文档与实现一致。仅服务闭环完成，不标 OrderAgent/工具/Apifox 真实模型联调完成。

## 11. 与 01～03 的一致性及文档同步

| 交界 | 结论/需同步事项 |
| --- | --- |
| 01 ID/事件 | 不改变会话/workflow/run/thread 或 SSE。订单 ID 属业务资源，不充当线程/幂等标识；Decimal/时间转换只在公开 DTO 边界 |
| 02 身份 | 复用 Principal，补 orders:read；模拟 user_id 只能受控，不认证；无本地用户主表，不把订单 FK 接会话 |
| 02 数据 | 复用 pool/迁移/角色，增加本领域 RLS 与 read_scope，不改全局元数据事务；运行/种子权限需在本稿审核后同步角色说明 |
| 03 Runtime/Budget | 不重新实现 Gateway、任务、预算或 Broker；未来工具接同一治理，查询事务在返回前结束 |
| 03 数据保留 | 订单库事实不是 ExecutionTask payload 或 Checkpoint；清理任务载荷不能删除订单 |
| 后续业务 | 新迁移扩展取消/退款；读取不做资格决策，不因 cancelled 推断退款完成 |
| 4.2～4.4 | 仅交接服务参数/DTO/异常，不展开工具目录、执行策略或专业图设计 |

初稿新增本稿和导航，本轮仅在本稿补跨环节约定，并新增4.2～4.4及统一计划。以下在审核后、相关开发时同步，不提前改变已批准规范：02 权限/角色与事务作用域说明；Graph/工具交接中金额与时间 JSON 约定；测试库配置和种子运行说明。01/03 架构无须重新规划。

## 12. 待用户确认的关键设计决策

| 决策 | 本稿建议与理由 |
| --- | --- |
| 业务范围 | 五种订单状态、仅 CNY、一单最多100行/一票物流；足以查询闭环，暂不做拆包/优惠/税费/第三方轨迹 |
| 数据库隔离 | 显式 owner SQL+三表 RLS、事务局部身份、非 owner 只读角色；使遗漏 Python 条件仍受限制。需审核角色/RLS 扩展 |
| 金额 | NUMERIC(12,2)/Decimal/JSON 字符串；消除浮点误差；总额与行和在种子/详情验证，不增加跨表触发器 |
| 分页 | 固定时间+ID 的 keyset，20默认/50上限，无 total_count；稳定且有界，不支持任意页跳转或跨请求强快照 |
| 物流 | 未发货正常结果，无假物流行；只对本人订单取一票，不提供单号全局检索 |
| 种子 | 三个各5单用户+空用户，固定时间和数据，事务幂等；旧样本变化报冲突而不覆盖，开发/测试显式隔离 |
| 身份权限 | orders:read 一个查询 scope；不增加管理员代查、金额敏感扩权或生产自报用户 |

上述是待审核建议，不能将其称为既有实现或已确认业务规则。若有不同订单状态、币种或分包要求，应在此处统一后再开发，避免服务、SQL、种子各自选择。

## 13. 本轮输出和状态记录

初稿只核对文档/源码和编制设计；本轮补齐全阶段其他文档但不执行开发。本稿仍待审核，不因4.2～4.4已完成逻辑设计而标记确认。未修改业务代码、安装依赖、建表、迁移、写种子、运行测试/代码检查或调用模型。

## 14. 全阶段衔接补充（本轮仅设计）

稳定工具名：orders_get_detail→get_order_detail；orders_list→list_orders；orders_get_logistics→get_order_logistics。共同scope为orders:read，全部只读，参数无user_id/Principal。list工具的status/created_from/created_to/page_size/cursor逐一映射OrderListQuery，不改命名、时间边界或分页约束。

工具参数args_model复用/适配本领域查询约束，不手工维护放宽版Schema；工具先做结构校验，Service外部边界仍做领域校验。Order状态位于结果data中，与ToolResultEnvelope.status不同，不能扁平合并。

Decimal金额仅在工具JSON适配层转固定两位字符串，禁止float；种子/未来写入若超过两位有效小数须显式拒绝，不依赖NUMERIC隐式舍入。时间统一UTC ISO格式。订单DTO不新增ToolCall、Agent、Graph或执行器字段。

Executor负责剩余期限和取消，read_scope使用本领域配置的数据库超时并正确回滚释放；Service不读取隐藏全局Budget，不自行构造身份。资料中的商品名称不作为指令，模型看到的是有界工具投影，Agent最终事实由规范观察构造。

| 原任务 | 明确后继与交付接口 |
| --- | --- |
| 4.1.1 | 4.1.2～4.1.5、4.2.5；领域参数/DTO/错误及金额时间约束 |
| 4.1.2 | 4.1.3/4.1.5；三表、RLS、索引、运行角色 |
| 4.1.3 | 4.1.4；专用读作用域和查询端口 |
| 4.1.4 | 4.1.6、4.3.4；三Service方法，不暴露Repo |
| 4.1.5 | 4.1.6、4.3.7、4.4.6；独立库真实样本与初始化契约 |
| 4.1.6 | 4.3.7、4.4.6/4.4.7；真实PG查询/归属验收记录 |

4.1.1～4.1.6的功能、步骤、文件、接口、前置、未来测试、完成标准与交付物仍见第8节；本表补齐后继，避免再复制一套任务。RLS、CNY、单票、游标和种子选择仍待用户审核，保持原范围。
