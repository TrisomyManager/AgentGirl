# OpenAPI

权威 REST 契约由 **`apps/backend`** 在运行时提供：

- 默认开发：`http://127.0.0.1:8000/openapi.json`（FastAPI 自动生成）

## 维护方式

1. 在后端确认路由与模型变更已完成并通过测试。
2. 将 `openapi.json` 导出为文件（例如 `curl -s http://127.0.0.1:8000/openapi.json -o packages/contracts/openapi/openapi.json`），再提交 PR。
3. 在 [`API_CHANGELOG.md`](../API_CHANGELOG.md) 中记录破坏性变更。

当前仓库**不强制**检入完整 `openapi.json`，以避免与开发分支频繁冲突；以变更说明 + schema 草案为最低要求。
