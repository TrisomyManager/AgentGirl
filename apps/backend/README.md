# Companion AI 后端

通用陪伴 AI 能力库与小暖参考宿主。当前采用模块化单体：一个 FastAPI 进程组装人格、记忆、语音、受控任务、设备和平台适配器。业务模块可由其他宿主注入使用，独立启动业务模块不会自动获得参考宿主的账号与权限边界。

实际进度见仓库根目录 [DEVELOPMENT_EXECUTION.md](../../DEVELOPMENT_EXECUTION.md)。真实平台账号验收暂缓；3D由用户明确暂缓，完成其他功能后讨论确认技术方案。当前呈现仍为Live2D，`avatar_runtime`只负责独立的音频时间轴与呈现数据组装。

## 本机启动

需要Python 3.11、uv；音频格式转换需要FFmpeg/ffprobe。Windows可通过`COMPANION_FFMPEG_DIR`指定工具目录，Linux可由系统包管理器安装。Docker镜像包含相应运行依赖。

在本目录运行：

```text
uv venv --python 3.11
uv pip install -e ".[dev,arch,platforms]"
```

激活虚拟环境后，将`COMPANION_LITE_MODE`设为`true`，运行：

```text
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

Lite模式使用固定位置的`companion_lite.db`，无需Docker；用`COMPANION_LITE_DATABASE_URL`指定独立数据库。参考宿主支持单worker，用户取消、删除、任务、插件和会话的协调以当前进程为边界。

`GET /health`在数据库与启用模块全部就绪后返回200；必要模块启动失败会阻止就绪。缺少模型密钥时可以进入配置界面，实际聊天会提示配置错误。

聊天、摘要和推理默认使用火山方舟；向量使用豆包文本输入、1024维；ASR、TTS和实时通话使用豆包语音原生接口。方舟与语音密钥分开配置，见[VOLCENGINE.md](VOLCENGINE.md)和`.env.example`。实际密钥、环境、运行配置与数据库保持私有，不进入Git。

## 目录与接入

| 目录 | 职责 |
| --- | --- |
| `shared_contracts/` | 数据模型、事件、音频/呈现契约与能力协议 |
| `shared_runtime/` | 配置、模型客户端、SQL与用户工作生命周期 |
| `core_orchestrator/` | 参考宿主组装、回合协调、账号、管理与隐私入口 |
| `persona_engine/` | 人格、连续情绪、回复策略与关系状态 |
| `memory_system/` | SQL原文/摘要、遗忘与恢复、向量/图来源检索和清理 |
| `voice_layer/` | 可注入ASR、TTS、分段语音与实时通话 |
| `action_executor/` | 工具、MCP、持久任务、提醒、主动陪伴、插件与`action2d/` |
| `device_coordination/` | 设备注册、受控命令与回执 |
| `gateway_adapter/` | 平台协议、显式身份/目标绑定及持久收发回执 |
| `avatar_runtime/` | 与宿主、语音厂商和渲染器独立的呈现时间轴 |

业务模块不反向导入参考编排器，跨模块能力通过契约和宿主注入组合。旧`shared/`、`action_layer/`兼容源码已移出运行包；动作代码使用`action_executor.action2d`，运行时`action_layer`能力键保留兼容。

- [模块注入](docs/module-injection.md)、[模块契约](MODULE_CONTRACTS.md)
- [账号与隐私](docs/access-and-privacy.md)、[内容检查](docs/content-safety.md)
- [生产SQL与迁移](docs/production-storage.md)、[图来源与清理](docs/neo4j-ownership.md)
- [流式语音](docs/streaming-tts-pipeline-design.md)、[实时会话连续性](docs/realtime-conversation-continuity.md)、[音频传输](docs/audio-transport.md)
- [平台接入](docs/platform-conversations.md)、[工具和任务](action_executor/README.md)、[本地插件](plugins/README.md)
- [部署与CI](docs/deployment.md)、[管理界面](docs/administration.md)

Web在`../web/`，Electron参考客户端与设备模拟器在`../pc-client/`；二者共用参考宿主协议。前端使用Node 24 LTS，各目录分别安装依赖后运行测试和构建。

## 回归

在已激活的后端环境运行：

```text
pytest -q --ignore=voice_layer/tests/test_voice.py --ignore=memory_system/tests/test_memory.py -W error::pytest.PytestUnhandledThreadExceptionWarning -W error::pytest.PytestUnraisableExceptionWarning
lint-imports --no-cache
```

pytest自动使用临时Lite数据库，不读取本机应用数据，也不调用真实模型。真实PostgreSQL/Neo4j、平台和模型验收使用独立实例及合成用户。集成入口见[`integration/`](../../integration/README.md)。

`test_voice.py`在部分环境需要额外音频依赖；`test_memory.py`属于旧生产存储测试集合。当前生产门禁由独立宿主重启、迁移、图来源与容器冒烟脚本完成，不能用离线测试冒充真实外部服务验收。
