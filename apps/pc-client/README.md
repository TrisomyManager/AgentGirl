# PC Sim Client（`apps/pc-client`）

模拟 PC 设备端，与后端 **Device Operation Gateway**（HTTP 轮询 + `claim_next` + `device_token`）对接。不是真实 Windows 常驻客户端，不包含远控能力。

## 依赖

```bash
pip install httpx
```

或在本目录安装可编辑包（便于 `python -m xiaonuan_pc_client`）：

```bash
cd apps/pc-client
pip install -e .
```

## 环境变量（可选）

| 变量 | 默认 | 说明 |
|------|------|------|
| `XIAONUAN_API_BASE_URL` | `http://127.0.0.1:8000` | 后端基址 |
| `XIAONUAN_USER_ID` | `user_001` | 归属用户 |
| `XIAONUAN_DEVICE_ID` | `pc-sim-001` | 设备 ID |
| `XIAONUAN_DEVICE_NAME` | `我的电脑` | 展示名 |

## 启动后端（Lite Mode）

```bash
cd apps/backend
COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000
```

## 运行模拟客户端

```bash
cd apps/pc-client
python sim_client.py
# 或
python -m xiaonuan_pc_client
python sim_client.py --help   # 仅显示参数说明（当前无额外参数）
```

## 行为说明

1. **注册** `POST /device/register`，保存 `device_token`。
2. **心跳** 约每 10 秒 `POST /device/heartbeat`。
3. **领取** `POST /device/commands/claim_next`。
4. **执行** 先 `POST /device/commands/{id}/mark_running`，再本地执行，最后 `POST /device/command_result`。
5. 支持：`ping`、`show_notification`、`open_url`（仅 http/https）、`get_device_status`。

## 手测建议

1. 启动本客户端后，打开 Web「我的设备」或：

   ```bash
   curl -s -X POST http://127.0.0.1:8000/device/send_command \
     -H "Content-Type: application/json" \
     -d "{\"user_id\":\"user_001\",\"device_id\":\"pc-sim-001\",\"command\":\"ping\",\"payload\":{}}"
   ```

2. 期望日志：`[register]` → `[heartbeat]` → `[claimed]` → `[running]` → `[result]` → `[done]`。

3. 审计：`GET http://127.0.0.1:8000/device/audit?user_id=user_001`

## 契约

对外 JSON 形状以 `packages/contracts/schemas/` 草案与后端 `device_coordination` 为准。
