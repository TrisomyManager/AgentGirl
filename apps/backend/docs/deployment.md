# 参考宿主部署与自动检查

当前部署单元是一个 `main:app` 进程。Web 和 PC 共享该协议。会话撤销、提醒、插件资源与用户删除锁由此进程管理；不要启动多个 worker 指向同一 Lite 数据库。业务模块仍可由其他宿主接入，但独立模块应用没有自动获得参考宿主的账号边界。

## 本机运行

后端使用 Python 3.11，安装 `.[dev]` 后按根目录说明启动。没有配置访问密钥时仅允许本机访问；反向代理及容器网络应使用账号模式。详见 [账号与隐私](access-and-privacy.md)。

`GET /health` 只有在数据库和启用模块全部初始化成功后才返回 `200/healthy`，响应 `startup` 列出模块状态。启动前/关闭后返回 503；必要模块启动错误会使启动失败，并关闭此前已启动的资源。缺少模型密钥不阻止配置界面启动，实际模型调用会报告配置错误。

## Docker Compose

先在 `apps/backend` 生成管理员账号：

```powershell
.venv/Scripts/python.exe tools/manage_access.py --user-id operator --role admin --output companion_access_credentials_operator.json
docker compose up --build -d
```

保管凭据输出文件，不将其加入 Git。Compose 的初始化任务只复制并验证哈希配置到应用卷，解决宿主私有文件与容器非 root 用户的读取权限差异；不会向镜像写入密钥。应用默认绑定本机 `8000`，使用持久化卷 `/data` 保存 SQL、运行配置和临时语音，根文件系统只读、应用用户为 UID 10001。

配置界面或进程环境可提供方舟与豆包语音的独立密钥。镜像默认仍使用火山引擎/豆包原生能力；不打包可选本地 ASR/TTS 模型。远程访问应由宿主管理的 HTTPS/WSS 反向代理提供，并设置明确的 `COMPANION_CORS_ORIGINS`。

宿主哈希文件变化后，运行 `docker compose run --rm initialize` 将新版配置复制到卷；运行进程会按配置内容撤销旧会话。修改容器环境需要重建相应容器。普通 `docker compose down` 保留命名数据卷；删除数据卷会永久移除用户数据，不是日常重启步骤。

`storage` profile 提供 PostgreSQL/pgvector、Neo4j、Redis、MQTT，仅在容器内部网络开放。使用生产存储前必须明确设置 `POSTGRES_PASSWORD`、`NEO4J_PASSWORD`、包含正确数据库凭据的 `COMPANION_POSTGRES_URL` 和 `COMPANION_LITE_MODE=false`，并等待存储就绪。没有默认生产密码；实例行为仍需按执行表 2.1/2.3 验收。

旧 Compose 将各模块拆到不同容器、仍使用 localhost 调用且部分模块没有访问守卫，已由当前单体部署替换。外部图库、独立微服务和多进程协调不能用 Lite 冒烟替代验证。

## CI 与验证

`.github/workflows/ci.yml` 为 PR、默认分支提交及手动触发准备：

1. Python 3.11 的离线 Lite 回归，包含将 SQLite worker 线程错误视为失败的检查，并构建运行模块 wheel。
2. Node 24 LTS 下 Web/PC 测试、依赖审计与双端构建。系统安装的 Node 25 不在当前测试工具支持范围内，应使用 package.json engines 所列版本。
3. Linux 镜像构建及 `integration/scripts/smoke_container.py`：独立密钥/数据卷、真实登录、重启撤销会话、SQL 持久化、导出和删除；最后只清理自己创建的容器/卷，不发布镜像。

镜像先构建 wheel，再在非 root 运行层安装完整依赖；打包明确包含 persona YAML，排除测试与本地运行文件。`.dockerignore` 排除环境、配置、数据库、凭据、开发虚拟环境和可选模型。

V2.26镜像包含平台可选依赖，但多平台仍默认关闭，启用条件见[平台会话](platform-conversations.md)。发布前扫描排除本机`.codex/config.toml`；该文件曾被Git跟踪且含明文服务凭据，新快照移除其跟踪但保留本机文件。历史记录中的凭据需要账号所有者轮换，当前文件删除不等于历史清除。

V2.27已通过[实际Linux CI](https://github.com/TrisomyManager/AgentGirl/actions/runs/39377276774)：后端839、桌面工具16、Web86、双端审计/测试/构建、6导入契约、wheel，以及真实PostgreSQL/Redis7/Neo4j门禁。Docker实际构建并通过非root就绪、登录、重启撤销、卷持久化、导出与删除；6.3验收。本机仍没有Docker引擎，该证据来自隔离的GitHub runner，未部署或推送注册表。

干净安装使用`sqlalchemy[asyncio]`显式带入greenlet；音频回归安装FFmpeg/ffprobe。FastAPI0.150使用公开`iter_route_contexts`提取有效路由及前缀，旧版本保留平铺路由兼容，不能因为框架升级而丢失账号所有权判断。PC类型解析明确使用其自身已安装的SDK，独立CI不再借用Web的node_modules。

本地干净wheel独立宿主和真实Windows解包程序此前已验。签名安装器、其他OS实际运行、多worker与负载测试仍保留原边界，不能由Linux构建或容器冒烟推定。

## 桌面打包来源与语音资源

Electron 打包程序从 `app://companion` 加载内置页面。后端默认 CORS 包含该来源；自定义 `COMPANION_CORS_ORIGINS` 时显式加入它，不要用通用 `null` 或通配来源替代。开发模式仍使用明确的 HTTP 来源。API 地址通过构建环境 `VITE_API_BASE_URL` 指定；打包模式忽略开发服务器配置。

Web/PC 构建均从各自安装的 ONNX SDK 复制匹配的脚本/WASM 到同来源 `ort/`，无需运行时 CDN。部署时应一起发布完整 dist，包括 `ort/`、VAD 模型和 Live2D 资产；不要跨版本替换 WASM。宿主可用绝对路径 `XIAONUAN_PROFILE_DIR` 隔离桌面资料目录，后端 SQL 仍由其独立配置决定。

Windows 解包程序已实际验证自有来源、路径越界拒绝、私有 Python 桥、方舟聊天和本地 VAD 初始化；此结果不代表签名安装器、跨系统或远端 CI 验收。依赖覆盖及代理回归说明见 [PC README](../../pc-client/README.md)。
