# 火山引擎接入

小暖默认使用火山方舟与豆包语音，Web 与 PC 客户端共用设置页。

| 用途 | 默认模型 / 资源 | 接口 |
| --- | --- | --- |
| 聊天、情绪分类、摘要 | `doubao-seed-2-0-mini-260428` | 方舟 `/api/v3/chat/completions` |
| 推理模型配置 | `doubao-seed-2-0-pro-260215` | 同上 |
| 记忆向量 | `doubao-embedding-vision-251215`，1024 维（降维） | 方舟 `/api/v3/embeddings/multimodal` |
| 录音转文字 | `volc.seedasr.sauc.duration`（流式识别 2.0） | 豆包语音 WebSocket `/api/v3/sauc/bigmodel_nostream` |
| 普通文字转语音 | `seed-tts-2.0` | 豆包语音 `/api/v3/tts/unidirectional` |
| 实时通话 | O2.0 `1.2.1.1`，资源 `volc.speech.dialog` | WebSocket `/api/v3/realtime/dialogue` |

Seed 系列支持文本生成、推理与多模态理解；当前聊天入口和记忆向量按文本调用，未新增图片/视频输入界面。日常回复和摘要关闭深度思考以减少等待；推理模型字段供业务显式选用。

实时语音直接完成语音理解和生成，支持中文/英语、流式音频、人设与打断。默认使用 O2.0 小何 `zh_female_xiaohe_jupiter_bigtts`。SC2.0 `2.2.0.0` 更侧重角色演绎，需要对应的 `saturn_` 或 `S_` 音色。普通 TTS 2.0 的音色是 `zh_female_xiaohe_uranus_bigtts`，与实时音色分开配置。

## 填写密钥

1. 在火山方舟开通聊天模型、向量模型并创建 **方舟 API Key**。
2. 在豆包语音控制台开通流式语音识别 2.0、语音合成 2.0、端到端实时语音服务，创建 **豆包语音 API Key**。确认 Key 所属项目具有服务权限。录音上传会转换为 16kHz 单声道 PCM 并通过流式识别的一句话接口返回完整文本。仍兼容已获授权的录音极速版 `volc.bigasr.auc_turbo`（HTTP），不同服务资源不能混用。
3. 在后端 `.env` 填写 `COMPANION_ARK_API_KEY`、`COMPANION_VOLC_API_KEY` 后重启后端。地址、模型和音色已经预设。新环境可复制 `.env.example` 为 `.env`。
4. 也可以通过「设置」分别填写聊天、ASR、TTS、实时通话的 Key 并保存。语音各栏可填同一个具有对应权限的豆包语音 Key。保存即时生效，新通话使用新配置。

方舟聊天支持模型 ID 或 `ep-` 开头的推理接入点 ID。向量使用专用多模态接口，默认请求 1024 维以兼容 pgvector IVFFlat 索引（模型最高 2048 维）；如使用向量接入点 ID，设置 `.env` 中的 `COMPANION_EMBEDDING_MODEL`。记忆提取与意图识别跟随已生效的方舟聊天配置。向量 Key 默认跟随方舟聊天 Key，向量地址和模型独立于聊天配置；不会因旧聊天地址残留而自动切换到其他厂商。可用 `COMPANION_EMBEDDING_API_KEY`、`COMPANION_EMBEDDING_BASE_URL` 单独覆盖。

运行时设置优先于 `.env`，旧厂商设置需切换后保存。空密钥输入表示保留同一服务商已保存的密钥；浏览器只收到是否已配置。清除聊天运行时设置后，如 `.env` 仍有 Key，将继续使用环境配置。

LLM 配置默认保存到后端目录，语音配置保存到用户配置目录，均已被 Git 忽略。可通过 `COMPANION_LLM_CONFIG_PATH`、`COMPANION_VOICE_CONFIG_PATH` 指定位置。文件包含密钥，不应提交。

## 验证与限制

- 「测试连接」真实调用聊天接口。「测试语音」只检查 ASR 配置是否完整，并调用 TTS 播放；真实识别与实时通话需要录音/发起通话验证。
- 未填 Key 时保留离线规则聊天，实时通话会提示缺少语音 Key。
- WebM 录音转换 WAV 需要项目已有的 ffmpeg 支持。实时通话上传 16kHz int16 PCM，输出 24kHz int16 PCM。
- 旧记忆内容保留。旧厂商向量不可与豆包向量直接比较，需重新生成才能获得语义检索；不同维度向量会跳过。PostgreSQL 的现有向量列需要单独备份和重建，配置变更不会自动迁移已有向量数据。
- 动作/Live2D 仍使用本地动作映射。原有外部 2D 逐帧生成是占位协议，尚无 Seedance 视频任务轮询及抽帧流程；本次未将占位接口冒充为已接入视频生成。
- 已用用户填写的 Key 完成聊天、记忆提取、向量生成和语义检索实测。语音合成 2.0 已生成并解码验证 24kHz、约 2.4 秒的 MP3。实时语音开通后已通过应用 WebSocket 完成音频输入、中文转写、文字回复及 PCM 音频输出；流式识别 2.0 已真实识别同一测试录音，替换原来未获授权的极速版资源。

## 官方资料

- [用户提供的 Doubao Realtime 控制台](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-realtime)（需登录；协议以公开文档为准）
- [模型列表](https://docs.volcengine.com/docs/ark/model-list?lang=zh)
- [聊天接口](https://docs.volcengine.com/docs/ark/chat-api?lang=zh)
- [向量化](https://docs.volcengine.com/docs/ark/vectorization?lang=zh)
- [实时语音 API](https://www.volcengine.com/docs/6561/1594356)
- [录音识别极速版](https://www.volcengine.com/docs/6561/1631584?lang=zh)
- [流式语音识别 2.0](https://docs.volcengine.com/docs/DoubaoVoice/LargemodelstreamingautomaticspeechrecognitionAPI?lang=zh)
- [语音合成流式 API](https://www.volcengine.com/docs/6561/1598757)
- [豆包语音 API Key](https://docs.volcengine.com/docs/DoubaoVoice/APIKeyUsage?lang=zh)

## 本次验证

- 相关后端测试 175 项通过（包括真实 WebSocket 库连接本地模拟服务，以及流式识别的音频归一化、结束帧和异常检查），前端测试 9 项通过，Web 构建通过。
- Lite Mode 后端启动、health、设置读取、缺少 Key 时的实时通话提示已检查。
- 已完成方舟真实 API 调用与页面流式聊天验证，测试记忆使用独立测试用户并已清理。普通 TTS、流式识别 2.0 与端到端实时语音均已通过真实 API 测试。
- 全后端检查仍有提醒调度测试失败（`test_scheduler_tick_fires_due_reminders_into_push_bus`），架构/全量 lint 基线也存在已有问题；未将这些检查标为通过。
- PC 构建受原有 `tsconfig.node.json` 项目引用配置错误 TS6306/TS6310 阻碍，未生成新安装包。
