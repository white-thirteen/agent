# V2 02 建议归档范围

仅为待人工授权的归档方案，未执行Git提交、推送或暂存。当前分支v2、接管HEAD为1ff92e082c5a348b715b221fbc0b687d8acf02e8。

| 分组 | 建议核对范围 |
| --- | --- |
| V2 02实现 | app/context、偏好API/Service、Runtime/Gateway、原Graph及专业Agent显式上下文接线、原Memory/Policy/Executor必要适配、模型资源及集中配置 |
| 迁移与依赖 | 新增008～011、schema版本检查、requirements.in/txt的LangMem及解析依赖、.env.example与运行归档忽略规则 |
| 验证与客户端 | 本阶段新增测试及原测试必要适配、当前Apifox/OpenAPI/环境模板与静态校验；不重写旧V1客户端归档 |
| 交付文档 | 本目录设计/执行/实施/QA/修复/原始证据、STATE和当前协议/导航的必要更新 |
| 接管前已有改动 | 大量docs旧路径删除和docs/v1、docs/v2迁移、AGENTS/角色与Codex配置、已有PG升级脚本、其他历史改动，先独立确认归档安排，不自动混入本阶段 |

原工作区文档重排尚未Git归档。当前V2 02导航依赖新docs/v1、docs/v2结构，因此正式归档前须一并核实文档重排的前置安排，不能只提交新链接却遗漏其目标，也不能以此推导整个dirty工作区已获归档授权。以[接管基线](evidence/takeover-workspace-baseline.json)及[保护复核](evidence/workspace-safety-audit.json)区分原有与本轮变更。

不归档.git中的私有凭据/连接助手、原生会话原文、.env、.venv、临时PG二进制/数据、运行期Archive、缓存及模型权重。公开证据须保留真实失败和复测，不只挑选PASS；当前客户端UI未测、估算Token和实际供应商用量等限制保持明确。

用户正式ACCEPTED与Git归档授权是两个需明确确认的决定。技术VERIFIED不自动产生上述授权，不进入V2 03。
