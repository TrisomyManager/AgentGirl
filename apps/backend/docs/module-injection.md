# 模块迁移与宿主注入

2026-10-20 · V2.22。旧 `shared`、`action_layer` Python 包已移出源码及 wheel，业务模块只能使用实际契约/运行时包。

| 旧导入 | 现导入 |
| --- | --- |
| shared.models / events | shared_contracts.models / events |
| shared.config / database / llm_client / prompt_engine / voice_runtime_config | shared_runtime 下同名模块 |
| action_layer | action_executor.action2d |

宿主的运行时能力键 `action_layer` 保留兼容，实际挂载新 action2d 实现。它不是可重新导入的 Python 包。

## 记忆工具

`shared_contracts.MemoryReader` 是行动工具的读取端口。宿主通过 `action_executor.memory_port.set_memory_reader()` 注册实现，参考宿主由 `core_orchestrator.runtime_hooks.ReferenceMemoryReader` 读取实际 SQL，包含会话归属校验。业务工具不再导入 memory_system 内部函数。未注入时仍可使用原 HTTP 适配器。

注入端口故障返回 `memory_unavailable`，不暴露异常正文；旧 HTTP 适配器仍沿用历史空结果回退，未声称所有远端错误均已区分。关闭宿主时撤销自己持有的 reader，不能撤销后注册的其他实例。

## ASR 工厂

工厂返回 `shared_contracts.SpeechRecognizer`。其高层形状是：

- `transcribe(encoded_upload, language, model, upload_filename, upload_content_type)` 返回 `VoiceTranscriptionResult`。
- `transcribe_pcm(pcm_int16, sample_rate)` 返回字符串。
- `close()` 异步释放资源。

`voice_layer.main.create_app(asr_factory=...)` 和参考宿主 `main.create_app(asr_factory=...)` 接受工厂。每个 app 独立存储工厂；REST 每次操作创建/关闭，旧 WebSocket 和 cloud provider 每连接创建/关闭。`CloudRealtimeProvider(asr_factory=...)` 可直接接入。宿主给出的真实置信度/时长和上传元数据原样保留，不从字符串补造指标。

默认 `ASRClient` 仍按配置选择供应商。独立 SDK 调用若需要磁盘配置，应先调用 `load_voice_config_from_disk()`。原生 `volc_realtime` 使用厂商端到端识别，模型仍为 `1.2.1.1`，不经过 cloud ASR 工厂。TTS HTTP 客户端仍是参考宿主单例，未实现全面注入或多 app 隔离。

清理在独立任务中等待，重复取消仍等待资源退出；合作式关闭有十秒超时。默认 ASR 的 WAV 时长来自实际可读帧、采样率、声道和位宽；其他无法解析的编码返回 0（未知），不按压缩字节大小推测。

## 验证

后端完整 Lite 回归 765 passed（43.05 秒，线程异常视为错误）；6 个 import-linter 契约通过。AST 反向编排、直连 SDK、横向业务依赖均为 0，角色文本基线仍有差异，未声称扫描全绿。真实隔离 SQL 记忆读取、两次豆包上传 ASR（各 2606ms）、默认 O2 新旧协议与打断恢复，以及干净 wheel 独立宿主/注入/目录工具通过。前端本轮无变动，沿用 V2.21 的 Web 81 和双端构建结果。
