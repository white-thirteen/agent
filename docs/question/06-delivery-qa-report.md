# Task6.3.2 独立QA：PASS

2026-11-15。仅验收当前Task的最终材料、固定复现配方与验证证据，交主Agent技术复核。**本结论不代表06正式ACCEPTED、G5完成或Git归档授权。** 未发现需要新增06-QA-002的问题；06-QA-001/P2沿原QA复测和主Agent关闭结论，不重新编号或覆盖旧FAIL。

## 独立检查与实际运行

读AGENTS/STATE、冻结D06 Task6.3.2及第11～12节、执行/QA任务、交付报告、最终验收入口、Handoff、README、.env.example、数据库配方、Compose、Dockerfile、实际初始化/应用生命周期/交付验证脚本，以及前五Task主复核和原修复记录。未修改业务代码、既有测试、配置、旧证据或冻结设计。

独立探针：[源文件](06-delivery-qa-probe.py)，[本轮新证据](06-delivery-qa-evidence-20261115.json)。实际使用`.venv-delivery632-20261115/Scripts/python.exe`，未安装或复制包、未覆盖原.venv。

| 检查 | 实际结果 |
| --- | --- |
| Python环境身份 | Python3.13.7；独立prefix与base_prefix分开；include-system-site-packages=false；sys.path未引入原.venv的site-packages |
| requirements.txt逐项比对 | 90个锁定分发版本全部匹配；CPU torch版本包含+cpu |
| pip check | No broken requirements found，exit0 |
| 定向回归 | `pytest -q tests/test_config.py tests/test_resources.py`，**19 passed / 0 failed / 0 skipped，12.77秒**；包含配置边界、部分启动失败及Runtime/Store/模型/池关闭顺序的受控测试；不冒称这些替身为真实PG验证 |
| Ruff | `ruff check app scripts tests`通过；`ruff format --check app scripts tests`，155文件已格式化 |
| 原test真实PG只读保护 | 连接身份agent_demo_test/agent_test；在线001～006 checksum与原SQL逐一一致；13张public表完整行集/列定义前后相等，指纹亦等于228完整门禁的结束指纹 |
| 正式create_app实际lifespan | 原test库，Embedding显式关闭，不调用Chat；database/checkpoint/store ready、model initialized、agent_service ready；退出后应用两个池closed、审计池closed、其余async tasks=[] |
| 配方与证据对应 | 当前Dockerfile SHA256等于实际构建证据；保留在独立venv的verify_fresh.py SHA256等于最终审计所记执行源；交付材料相对链接均存在 |
| 秘密检查 | 对新增交付材料/配方/验证脚本及六份核心JSON，内存读取原Chat密钥、数据库URL/口令做精确扫描，零匹配，不打印值；临时新库秘密已删除，其扫描结果按实施/主Agent审计复用 |

另查8632无监听；PowerShell `Get-NetTCPConnection -ErrorAction SilentlyContinue`无输出/exit1表示没有匹配监听，并非重跑服务失败。未杀进程或操作用户服务。本次没有创建业务数据、seed、DDL或清理既有数据，因此没有需要删除的UUID记录。两次全public快照及在线checksum核对均通过。

## 明确复用的证据

独立QA没有机械重跑下列已完成检查；阅读原JSON并在新QA证据中记录六份核心文件SHA256，明确来源：

- [安装证据](../06-delivery-install-evidence-20261115.json)：从requirements独立安装成功、90版本一致；网络timeout/TLS EOF经pip恢复后成功，原日志SHA256保留。QA实际重验环境和pip check，不把原.venv视为新安装。
- [最终完整门禁](../06-delivery-clean-gate-evidence-20261115.json)：新解释器**228 passed/0 failed/0 skipped**、pytest参数仅`-q`、real_qwen_enabled=true；原seed幂等唯一窄例外完整纳入，无deselect。新[Qwen真实回归](../06-delivery-qwen-regression-evidence-20261115.json)PASS，含重复prepare拒绝保持原数据及本次调用提交后故障精确清理，paid_chat_calls=0。
- 同完整门禁的正式Uvicorn/Qwen实际HTTP就绪25.111秒、knowledge_ready=true、正常关闭池/任务/Qwen线程归零；独立QA本轮只实际重验无Embedding的lifespan，不冒称再次加载Qwen或HTTP启动。
- [实际新镜像构建](../06-database-reproduction-evidence-20261115-r2.json)：原固定PG17.6 digest、PGDG vector0.8.7-1及server/client17.6精确包，144.412秒；当前Dockerfile内容与执行摘要相同。vanilla Compose不含vector、原容器可写层重建丢包风险及历史包未来可获取性限制已准确说明。
- [新空双库应用初始化](../06-delivery-fresh-database-evidence-20261115.json)：11.613秒，两库public初始空、001～006首次应用/重跑[]、Saver/Store连续setup幂等、正式应用就绪、订单0和池关闭。新空库没有seed/语料导入/五能力重演；QA不将其视为这些业务已在新库重演。
- [主Agent独立SQL及清理](../06-database-reproduction-cleanup-evidence-20261115.json)：两库13表/checksum/控制行6、10、4/业务0/vector1024/其他连接0；新容器/卷/镜像及临时秘密删除，原ID/镜像/挂载结构不变且未重启。首轮可选Mount.Name失败、清理首轮列表顺序断言失败原JSON保留，最终规范化结构相等。QA没有SSH或访问已经删除的资源。
- 五核心能力真实业务与六Task链按[能力矩阵](../final-acceptance.md)及[主协调](06-integration-main-review.md)核对：6.1.1、6.1.2、6.2.1、6.2.2、6.3.1均独立PASS/主VERIFIED；631真实三段HTTP/完整重启/退款唯一事实/RAG来源/Memory隔离CRUD、611真实英语偏好问答及621独立恢复证据各自保留，不将本轮health或Node受控脚本替代真实业务证据。

README的新目标bootstrap→管理员预建vector→001～006→Saver→Store→首次seed→固定语料导入顺序，与实际脚本权限和Web无DDL/seed约束一致；管理URL仅bootstrap读取，普通身份与回环固定审批Actor边界、原关联恢复、unknown先核对、SSE断开不取消及不重放均清楚。新Qwen路径/revision、CPU/1024/单实例和Chat兼容SDK的职责分开，health initialized不被当作网络调用成功。

## 遗留与停止边界

用户已确认Postman导入；客户端后置脚本实际执行、变量实际回填、SSE界面仍未实测。G4各组成证据分开，不能由导入确认推导这三项通过；G5用户正式验收仍待明确结论。没有重新ComputerUse或付费Chat。

Store历史即时关闭观测波动原因未定；本次正常关闭、无残留任务和完整行集一致不宣称已定因。unknown原operation/revision/可信Checkpoint人工核对边界、单worker、演示身份无生产认证、无真实支付、无全局Exactly Once/持久事件重放及六项暂缓差异继续保留。

本QA只新增本报告、独立探针与新JSON；未Git提交/推送/重置、Bridge、SSH、重启PG、重建资源或派生Agent。已停止，交主Agent复核及用户阶段验收。
