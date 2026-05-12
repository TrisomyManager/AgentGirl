# JSON Schema 草案

与 **Device Operation Gateway**（`/device/*`）对齐的草案，用于文档与跨端代码生成。字段命名与类型以后端 Pydantic 模型为准；若有出入，以 `apps/backend/device_coordination/api.py` 为准并修正本目录。

| 文件 | 说明 |
|------|------|
| `device-info.schema.json` | 设备公开信息（列表/注册响应中的 device 对象） |
| `device-command.schema.json` | 指令对象（send_command / claim_next 等） |
| `device-audit-record.schema.json` | 审计行 |
| `register-request.schema.json` / `register-response.schema.json` | 注册 |
| `send-command-request.schema.json` / `send-command-response.schema.json` | 用户侧下发指令 |
| `claim-next-request.schema.json` / `claim-next-response.schema.json` | 设备领取下一条 |
| `command-result-request.schema.json` / `command-result-response.schema.json` | 设备上报结果 |
