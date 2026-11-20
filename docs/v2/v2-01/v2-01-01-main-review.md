# V2 01 Task1.1.1 主Agent复核与停止记录

2026-11-17。主Agent接受[独立QA](qa/v2-01-01-compatibility-qa-report.md)的 **FAIL / BLOCKED**，问题V201-111-QA-001/P1保持OPEN，未通过1.1.1，不进入1.1.2。阶段V2 01仍在开发，不能标VERIFIED/ACCEPTED。

## 已完成Git部分

06交付98af9d8c4b5e86f520f45b9fc62ccf19c70dbf6d及回执232469acf7e576883e84d58c5a140fd598d9b00e已推送real-model-chat，main以fast-forward合入并推送，随后从main创建并推送v2；远端三分支均核验为232469a。见[06回执](../../v1/v1-06/06-git-archive-receipt.md)。main独立worktree干净，V2设计和开发未混入06/main，六项旧遗留及三设计字节保护核对无变化。V2增量尚未提交或推送。

## 技术复核

[真实JSON](evidence/v2-01-01-compatibility-evidence-20261117.json)证明固定PG17.6/vector0.8.7镜像构建成功，但pg_search0.26.6预加载缺少pg_mblen_cstr符号，尚未到CREATE EXTENSION/语义/快照/重启验证。结论限定为本次官方二进制组合，不泛化其他ParadeDB版本或源码构建。原两库全部public行/列摘要、原容器启动/挂载及包版本保持；不改原实例、不自动升级PG、不切换SQL。

实际执行源为[留存源](evidence/v2-01-01-compatibility-executed-20261117.py)，SHA256为8d9b8205cf52dd858b4712368f49f2bcccdffebf7a8b68c8f2a967609d749a8c。增强探针含未执行语义，不能冒充本轮结果。候选契约未接线；独立QA实际7项定向测试和Ruff通过，未重跑远端构建或完整回归，不能用本地通过关闭P1。

## 清理补记

探针JSON已记录候选容器/卷/镜像及其临时构建目录精确清理。QA后，主Agent通过已授权SSH核对外层传输绝对目录/tmp/agent-v201-compat-Fc9igj及其唯一三文件集合，逐文件删除后rmdir，实际返回transfer_directory_removed True；不使用全局prune或删除其他目录。原始JSON和执行源已经取回本地，未覆盖原证据，清理补记单独保存在本文。

## 待裁决

已请求用户选择保持PG17.6评估兼容版本/源码构建、评估PG17小版本升级后另行审批部署、或批准SQL BM25备选。未取得裁决前不推进依赖Task，不修改冻结设计。裁决后交原Implementer定向处理，再独立QA复测；02/03不开发。
