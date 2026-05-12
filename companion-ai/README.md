# companion-ai（兼容入口）

后端与 Python 模块已迁至 **`apps/backend/`**。本目录**仅保留本 README** 作为路径书签；**不要**在此目录下继续开发，也**不要**使用已废弃的 `companion-ai/frontend_app/` 或 `companion-ai/examples/device_client/`（若因迁移残留仍存在，仅为本机 `node_modules` 锁文件，已在 `.gitignore` 中忽略；请始终使用 **`apps/web`** 与 **`apps/pc-client`**）。

| 内容 | 新位置 |
|------|--------|
| 后端 / `main.py` / `pyproject.toml` | `apps/backend/` |
| Web 前端（Vue + Vite） | `apps/web/` |
| PC 设备模拟客户端 | `apps/pc-client/` |
| 跨端契约草案 | `packages/contracts/` |
| 联调脚本 | `integration/` |

仓库结构与启动方式见仓库根目录 [`README.md`](../README.md) 与 [`AGENTS.md`](../AGENTS.md)。
