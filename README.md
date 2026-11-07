# Agent Backend

Python + FastAPI + LangChain + LangGraph 后端项目。当前完成开发环境与可运行骨架，
尚未实现模型调用、工具执行、工作流持久化或长期记忆。

## 本地运行（PowerShell）

在项目根目录执行：

```powershell
# 首次配置，已有 .env 时不要覆盖。
Copy-Item .env.example .env

# 当前 .venv 已使用 Python 3.13.7 安装依赖。
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 存活检查：<http://127.0.0.1:8000/health>
- `POST /agent/chat`：参数校验、Service/Runtime 分层、SSE 适配已接线；
  Graph 未实现时返回 HTTP 503，错误码 `agent_not_ready`。
- 工作流接口尚未注册，预留模块不会返回模拟业务结果。

`/health` 表示 HTTP 服务存活；其中 `agent_ready: false` 表示 Agent 执行能力尚未就绪。
当前启动不需要模型密钥或数据库。配置文件中的模型和数据库设置是后续开发的预留项，
仅填写这些设置不会自动开启 Agent。

开发期请求示例（可粘贴至 Apifox）：

```json
{
  "user_id": "dev-user",
  "conversation_id": "conversation-1",
  "workflow_id": "workflow-1",
  "message": "你好"
}
```

目前身份字段用于本地开发；生产接入时由可信 Java 后端提供，并补上服务间认证和授权。

## 重建环境

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.in` 记录直接依赖，`requirements.txt` 记录当前 Windows / Python 3.13
环境解析出的全部固定版本，包含测试工具。变更依赖时修改直接依赖清单、重新安装并验证，
然后更新固定版本清单；`pip freeze` 本身不会移除不再需要的包。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

测试中的 Runtime 替身只用于验证 SSE 传输与请求隔离，应用不会返回替身响应。

## 开发文档

- [开发规范](AGENTS.md)
- [当前架构与能力边界](docs/architecture.md)
- [第一步：开发环境与项目骨架（已完成）](docs/01-environment-and-scaffold.md)
- [第二步：真实模型对话闭环（待开发）](docs/02-real-model-chat.md)
