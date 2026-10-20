# PC 客户端与模拟器（`apps/pc-client`）

本目录同时包含 Electron 参考客户端与 Python 设备模拟器。二者通过后端 Device Operation Gateway 对接，只有白名单设备命令，不提供任意 shell 远控。

## Electron 参考客户端

使用 Node.js 24 LTS（或符合 package.json engines 的版本）、Python 3.11 和已启动的后端。`npm install` 后运行 `npm run dev`；`npm run build` 检查并构建，`npm run build:electron` 另行生成安装包。开发模式的 API 地址通过 `VITE_API_BASE_URL` 指定。

Windows 原生后台通知、真实提醒 SSE、刷新去重和内置工具执行边界已通过隔离实例验证。首次安装的开机自启默认关闭。工具服务由 Electron 私有启动，不再开放固定无认证端口。敏感能力默认关闭；宿主可通过 `XIAONUAN_TOOL_CAPABILITIES` 和专用 `XIAONUAN_SANDBOX_ROOT` 授权，并逐次确认。文件仅有界读取/新建文本，禁止覆盖、链接和任意程序/shell。详情及实际验证边界见 [桌面执行说明](../backend/docs/desktop-execution-boundaries.md)。

打包后从自有安全来源 `app://companion` 加载内置资源，不探测开发服务器。后端默认允许该来源；自定义 `COMPANION_CORS_ORIGINS` 时须显式保留 `app://companion`，不要放通通用 `null` 来源。API 地址在构建时由 `VITE_API_BASE_URL` 指定，默认 8000。宿主可设置绝对路径 `XIAONUAN_PROFILE_DIR`，使用独立客户端资料目录；不会改变后端数据库位置。

语音检测的 ONNX 脚本/WASM 随应用构建到 `ort/`，与该端实际安装的 SDK 版本匹配，不依赖运行时 CDN。PC的运行时依赖去重和tsconfig SDK类型路径须保留，以免共享Web源码误用另一端的SDK。Linux独立CI已验证只安装PC依赖即可测试、审计与构建；这不替代其他系统的实际桌面运行验收。`npm test` 还验证打包器真实下载钩子通过本机代理转发。

依赖覆盖说明：两端将 Live2D 包附带的发布工具 `gh-pages` 固定为 6.1.1，避免更新版本引入尚无修复的 braces 链；应用不调用该发布工具。PC 将 `global-agent` 升至 4.1.3，消除旧代理日志依赖风险，实际下载代理已回归。升级时重新审计，不应直接删除覆盖。

2026-10-20：两端依赖审计无已知漏洞；实际 Windows `win-unpacked` 程序已验证独立来源、资料目录、Python 桥、方舟聊天和本地 VAD WASM（合成麦克风），页面错误为零。签名安装器及其他系统仍待验证。

以下为 Python 模拟器的独立使用方式。

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

## Windows 单文件 exe（分发）

在仓库根或本目录执行（需 **uv** 或已安装 PyInstaller 的 Python；推荐 **Python 3.11**，与仓库约定一致）：

```powershell
cd apps/pc-client
.\tools\build-windows-exe.ps1 -OutputDir D:\out
```

产出 `XiaonuanPCSim.exe`（PyInstaller onefile）。逻辑与 `python -m xiaonuan_pc_client` 相同。

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
