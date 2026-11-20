# Resume validation 本地证据

- 修复脚本 SHA256：`6306184aa8c389ba2428b607f940c64fd3ffdf64f6b8c8d116a6dc3861e29857`。
- Windows保留回执 SHA256：`01fee08ea6f0dc93460c76fedd2cb6be8ba78851da1382a4ed8144a09b97ce90`，token `6b522e463c2b`。
- 项目 `.venv` 的 Ruff check、format --check 与 Python AST parse 均通过。
- 本地受控小自检：回执摘要/token、摘要不匹配时在任何Docker命令前拒绝、inspect数组取首项及Cmd切片均通过。
- 未运行远端、Docker、数据库、业务或模型测试；资源状态与恢复成功尚待主Agent实际验证。
