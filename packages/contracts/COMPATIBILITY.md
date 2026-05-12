# 兼容性策略

## 版本维度

- **后端**：以 `apps/backend` 部署版本为准；Lite Mode 与完整模式在存储实现上可能不同，但 **HTTP JSON 形状** 应保持一致，除非已在 `API_CHANGELOG.md` 标明 Breaking。
- **contracts**：`packages/contracts` 中的 schema 为**文档级**草案；与后端不一致时，以后端为准并修正 schema。

## 客户端

- **Web**（`apps/web`）：通过 `VITE_API_BASE_URL` 指向后端；升级后端前请阅读 `API_CHANGELOG.md`。
- **PC 模拟客户端**（`apps/pc-client`）：通过 `XIAONUAN_API_BASE_URL` 等环境变量指向后端；不保证与历史硬编码路径兼容（路径以本仓库文档为准）。

## 禁止放入仓库的内容

- **AIRI / Hermes / OpenTalking** 等完整外部工程源码不应加入本仓库；如需参考，在仓库外对比后仅引入经评审的片段或设计说明。
