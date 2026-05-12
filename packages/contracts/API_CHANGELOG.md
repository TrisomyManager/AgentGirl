# API 变更日志（contracts）

记录影响 **Web / PC 模拟客户端 / 外部集成** 的协议变更。格式建议沿用 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased]

### 文档

- 初始化 monorepo `packages/contracts` 骨架与 Device Gateway JSON Schema 草案（与当前后端行为对齐，非代码生成）。

## 维护约定

- **PATCH**：字段可选化、文档澄清、新增仅可选字段 —— 更新本文件 **Added**。
- **MINOR**：新增端点、响应新增字段（旧客户端可忽略）— **Added**。
- **MAJOR**：删除字段、改 URL、改认证方式 —— **Breaking**，并同步 `COMPATIBILITY.md`。
