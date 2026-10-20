# API 变更日志（contracts）

记录影响 **Web / PC 模拟客户端 / 外部集成** 的协议变更。格式建议沿用 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased]

### Added / Changed · 2026-10-20

- V2.25：`DELETE /memory/user/{user_id}/all`额外返回`external_graph: completed|pending`；记忆摘要额外返回`external_graph_cleanup_pending`，含单条删除的外部清理。SQL删除完成后不等待服务无限恢复；后台轮转重试，参考召回立即按SQL来源过滤。Web刷新恢复/解除待清理提示，账号切换丢弃迟到删除响应。
- 参考图投影增加不可变SQL来源、删除标记与服务器代次控制；无来源的旧图事实不直接加入回复。最低层图SDK的手工事实读取仍保留，来源过滤不对外开放原始图查询权限。

- 设备命令严格限制四种实际能力及各自参数，未知字段、过大内容、不属于设备能力或不安全 URL 会拒绝。命令存储新增必要的原子 transition 接口；认领/执行不得使用读后普通 update 代替。推送前已保存 delivered，不能覆盖已认领/完成状态。
- 参考 PC 的 Python 工具服务不再是无认证固定端口接口；由 Electron 生成私有凭据/随机端口，不提供浏览器 CORS。敏感本机能力需要宿主授权和逐次确认。renderer 增加可选 showBackgroundNotification，由原生主进程复核后台状态；旧宿主 showNotification 仍保持兼容回退。

- 普通对话/SSE done 增加可选 `content_filtered`。原生过滤后的 turn_done 同样携带该字段；表示实际发生检查替代，不表示完整语义审核。直接 `/voice/synthesize` 拒绝内容时返回 400，detail.code=content_blocked。
- 参考宿主在普通/SSE/工具/任务/语音发出前检查；原生 CHAT 文本完整检查后显示，无 caption PCM 会暂存等待完整文字，最多 30 秒 PCM，尾文字最多等 2 秒。拒绝发送 interrupted，替代音频由独立 TTS 生成；失败时错误码 safe_reply_audio_unavailable，已有文字仍可用。
- `GET /memory/user/{user_id}/graph` 返回用户 SQL 图索引的 nodes/edges/memory_count/truncated/source；支持 limit（1–80，默认 40）、query（≤120）、include_dormant/include_keywords（默认 false）。memory/entity/keyword 节点和关系 memory_ids 提供原文依据，不读取向量，查看不激活淡化。客户端必须清除账号/删除前的在途结果。

- 统一参考宿主增加 `/access/status`、`/access/login`、`/access/logout`。账号模式的 HTTP 使用 Bearer 随机会话，实时语音使用 `companion.session` WebSocket 子协议，设备使用 `companion.device`；URL 不携带凭据。退出/轮换会关闭活动流，当前通话不能切换身份。
- `/privacy/user/{user_id}/export|status|erase` 提供账号数据导出、清理状态和清理重试。erase 必须携带 `confirmation=删除我的全部数据`；全部完成为 200/completed，外部待重试为 202/pending，尚未停止的旧工作为 409。status 含 job_id/status/pending/updated_at，不含内容。
- 账号身份、请求 user_id、会话及资源归属必须一致；旧匿名或无法归属会话不可被新账号接管。当前守卫部署在统一参考宿主，独立模块与多 worker 边界由各自宿主负责。
- `/static/voice` 在账号模式按文件归属授权，未知归属的旧音频不可读取；`/voice/synthesize` 不再向客户端返回服务器 local_path。
- 统一 `/health` 在启动前/关闭后返回 503，只有必要模块成功启动才为 healthy/200；新增 startup 模块状态。必要模块启动失败会使宿主启动失败，并关闭已启动资源。

### Added · 2026-10-19

- 原生实时通话增加 `turn_done`，可携带 `turn_id`；仅在完整文本与实际音频输出结束后发送。客户端仍需等待自身播放队列排空。

- 分段语音：对话请求可选 `supports_segmented_voice`（默认 false）；SSE 在启用语音且客户端声明支持时输出 `voice_segment`（turn_id/seq/text/audio_url/duration_ms/emotion）、`voice_segment_error`（turn_id/seq/error）和 `voice_done`（turn_id/segments/successful_segments/total_duration_ms/truncated）。seq 从 0 起，成功或失败事件按序；失败段可跳过，不能阻止后续文字/音频。`voice_done.segments` 为总段数，包含失败段。
- 对话普通响应和 SSE done 增加 `voice_mode`、`voice_segments`；分段模式没有全文 voice_url，重听需按 seq 播放保存的成功段。普通非流式入口及未声明能力的客户端保持全文合成路径。停止播放/新轮需使旧异步播放结果失效。
- 实时语音 `assistant_audio_done.final=true` 表示整轮音频结束，`assistant_text_done` 表示文本结束；cloud/local 使用 `turn_done` 标记整轮生成完成。客户端仍需等待实际播放队列排空。录音超限错误可带 `code=audio_too_long`、`recoverable=true`，允许下一次讲话恢复。

- 分工编排：普通响应和 SSE done 增加 `specialist`（chat/task/memory/device）与可选 `task`；多步执行产生 `tool_status`（tool_name/status/message/task_id）。
- 持久任务：`GET/POST /actions/tasks`、`GET/DELETE /actions/tasks/{id}`、`POST /actions/tasks/{id}/resume`。状态包括 running、awaiting_input、completed、failed、cancelled、interrupted、limit_reached；步骤可为 outcome_unknown。取消不撤销已完成操作；仅待补充任务可续办，未知结果不自动重放。
- `GET /actions/mcp/tools` 输出 MCP JSON Schema 元数据；模型身份字段由宿主绑定。本地 stdio 桥与外部 stdio/Streamable HTTP 使用官方 MCP SDK。
- `/actions/user_state` 的 tasks 列表改为真实任务记录，含 request/status/message/steps；用户归属仍沿用现有 user_id 契约。

- 主动陪伴偏好：`GET/PUT /actions/proactive/preferences/{user_id}`；按用户保存规则、时区、免打扰、频率与日上限。
- 持久化推送：`/actions/push/poll` 增加 `durable`、`has_more`；消息载荷增加 `event_id`。序号跨重启保留，分页只推进到已返回消息。
- 记忆恢复：`POST /memory/user/{user_id}/restore/{memory_id}`。
- 日总结：`POST /memory/user/{user_id}/consolidate`，可选 JSON `day`；`GET /memory/user/{user_id}/daily_summaries`。
- `MemoryEntry` 增加 `memory_status`、`effective_importance`、`access_count`、`last_accessed_at`、`similarity`。旧客户端可忽略这些字段。
- `/memory/recall` 增加 `include_dormant` 请求字段；响应增加 `previous_session_digest`、`daily_summary`、`daily_summary_date`。

### Changed · 2026-10-19

- 原生实时连接绑定 query 中的 user_id/session_id；控制消息尝试切换身份时返回错误并结束连接，需以新身份重连。宿主已注入上下文而准备失败时明确报错。
- `/memory/store` 在生成向量期间发生用户清空时返回 409，旧写入不落库。普通后台提取在排队前记录数据版本，清空后不能恢复旧 SQL 记忆。

- `/memory/maintenance/decay` 自动维护改为可恢复的淡化状态，`expired_deleted` 保持返回 0；用户主动删除仍执行物理删除。
- `/memory/user/{user_id}/all` 同时清除该用户的关系索引、访问状态、持久化对话和日总结，保留个人设置。后台旧总结写入会失效。
- 记忆响应的时间统一明确 UTC，兼容旧数据库中的 UTC 无时区值；浏览器可正确换算本地时间。

### 文档

- 初始化 monorepo `packages/contracts` 骨架与 Device Gateway JSON Schema 草案（与当前后端行为对齐，非代码生成）。

## 维护约定

- **PATCH**：字段可选化、文档澄清、新增仅可选字段 —— 更新本文件 **Added**。
- **MINOR**：新增端点、响应新增字段（旧客户端可忽略）— **Added**。
- **MAJOR**：删除字段、改 URL、改认证方式 —— **Breaking**，并同步 `COMPATIBILITY.md`。
# V2.8 · 情绪与关系连续性（2026-10-19）

- `POST /persona/classify_reaction`：输入 `user_message`，返回有界反应信号、意图、关系观察与 `source=model|rules`；无写入副作用。
- `POST /persona/generate_response` 可传 `turn_id` 与已分类 `reaction`，返回 `reaction`；同一用户/轮次只累计一次关系和情绪事务。
- `GET /persona/relationship_reviews/{user_id}?limit=7`：返回按日的关系观察统计；不同用户隔离，旧档案不重复计分。
- 对话普通响应及 SSE `done` 新增可空 `expression_emoji`；严肃/任务语境抑制表情。`EmotionState.timestamp` JSON 明确标记 UTC，既有离散标签保持兼容。
- 日整理结果可包含 `relationship_review`（`updated|unchanged|pending`）；失败重试不重复调用总结模型。

# V2.9 · 自然发言与路由（2026-10-19）

- `GET/PUT /persona/conversation_preferences/{user_id}`：`natural_reply_enabled`（默认 false）和 `acknowledgement_reply_probability`（0–1，默认 0.35）。更新校验有限数与额外字段；设置按用户持久化。
- `POST /persona/observe_turn`：提交已完成轮次的情绪/关系观察，不生成回复；同一用户/turn_id 去重。独立服务中的安静轮次也会被观察。
- 对话普通响应和 SSE `done` 增加 `reply_suppressed`、`talk_value`、`reply_reason`；SSE `meta` 增加 `reply_suppressed`。安静处理时正文为空，客户端显示接收状态，勿当成传输错误或启动语音播放。
- SSE `done` 补齐 `expression_emoji` 与 `error`，与普通响应保持一致。
- 自然取消提醒可按标题解析，歧义返回 `ambiguous_reminder` 与候选；明确“所有”才批量取消当前用户的待办。显式 id 取消需要 user_id。
# 2026-10-20 · 图片理解

- `POST /orchestrator/turn` 和 `/turn/stream` 正式启用 `image_urls`（最多 3 个 JPEG/PNG/WebP base64 data URI）；`has_image` 可由有效图片推断。单图 5 MiB、合计 10 MiB、1600 万像素以内，图片校验失败时返回错误，不调用模型/工具。图片回合只走聊天。
- `POST /persona/generate_response` 支持相同 `image_urls`；无图片能力/识别失败显式报错，不伪装识别成功。无需图片字段的旧文字/语音客户端保持原行为。
- 不保存图片原件；SQL 对话元数据新增 `has_image`。多模态图像只作用于当前回合。

# 2026-10-20 · 音频/表情同步

- 普通/SSE `done` 新增可空 `avatar_timeline`；`voice_segment` 与 `voice_segments[]` 的每段均包含版本 1 时间轴。实时 `assistant_sentence_start` 可包含同一字段；没有宿主时仍可为空。
- 时间轴字段：`version=1`、`turn_id`、`segment_seq`、可空 `duration_ms`、`clock=audio_playback`、`mouth_source=audio_rms`、`cues[{offset_ms,emotion,intensity,gesture}]`。客户端用实际音频播放位置消费，接收不等于已经播放。
- 原生豆包在句子文字为空/缺失时，也会于首个实际音频前发送 `assistant_sentence_start`，保证格式与时间轴就绪。旧字段和二进制音频保持兼容。

# 2026-10-20 · 本地插件

- `GET /actions/plugins`：返回插件发现/加载/失败状态和公开版本摘要，不返回配置路径、用户授权或异常正文。默认目录仅发现，不执行代码。
- 本地工具采用 `plugin_<id>__<tool>` 命名，经宿主授权后进入 `ToolCatalog` 和现有任务接口。请求参数不能指定用户/会话/轮次/操作身份；修改类异常或中断返回 `outcome_unknown`，不自行重放。
- 授权、安装目录和启停来自可信宿主私有文件；没有增加 HTTP 代码上传、远程安装或聊天启用接口。
# 2026-10-20 · 管理与内置扩展目录

- 新增管理员 `GET /orchestrator/admin/overview`：当前进程就绪/模块启动状态、SQL 模式、访问模式，不含凭据或用户内容。
- 新增管理员 `GET /actions/plugins/catalog`、`POST /actions/plugins/catalog/{id}/install`。安装需宿主另行开启，提交目录 `sha256`；201 表示文件安装，执行仍需宿主授权。403 为权限/宿主未开启，404 未知包，409 版本/目录/预授权冲突，503 文件操作失败。现有插件工具与任务协议不变。

# 2026-10-20 · 可协商音频帧

- `/voice/realtime?audio_protocol=framed-v1` 新增 `transport_ready` 协商。音频使用 CNAV v1 二进制头，段元数据增加 `audio_stream_id`/`audio_protocol`；旧客户端省略参数仍使用原裸音频。控制 JSON 上限 64 KiB，音频 2 MiB；协议错误关闭连接。详细字段见 `packages/audio-transport/README.md`。
- 鉴权 WebSocket 握手选择公开 `companion.session`/`companion.device` 名称，绝不选择凭据值；会话撤销语义不变。
