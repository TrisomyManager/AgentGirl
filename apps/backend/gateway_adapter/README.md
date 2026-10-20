# gateway_adapter

跨平台消息边界，供参考宿主或其他项目接入。当前路线图6.2仍在开发，不能将协议单测当作真实平台验收。

## 当前入口

旧`/gateway/send`、`/gateway/broadcast`、`/gateway/receive`及App WebSocket仍保留；参考宿主对外部效果和身份另有访问限制。旧receive依赖Redis消费者，Lite模式明确503。SessionManager仍是内存映射，并会跨渠道共享同一用户的会话，不能直接用作公网平台的身份绑定。

低层TelegramAdapter和DiscordAdapter的`send_message(user_id=...)`参数是平台目标ID，不是可信的内部账号。新`PlatformRuntime`使用宿主私有配置精确绑定内部所有权；默认关闭，旧token不会自动启动接收或回复。

## 已补齐的协议基础

- Telegram按纯文本发送，不把模型输出当HTML；使用当前`reply_parameters`，关闭链接预览。消息长度、返回消息ID、响应体和异常受限。
- Discord旧webhook调用增加`wait=true`并保留原thread参数，返回实际消息ID；关闭自动提及，不再使用占位消息ID。未确认投递不能返回成功。
- 发送超时/5xx/异常JSON/超大响应保留不确定结果，不自动重发。HTTP诊断脱敏Bot路径token、Webhook token、userinfo及认证query；异常不输出厂商正文或完整地址。
- `shared_contracts.PlatformMessage`只保存平台/机器人别名、外部发送者、目标、消息与事件ID、文字和私聊/公共场景。它不包含内部user_id，必须由宿主独立绑定。机器人/匿名身份、编辑/非文字和未知事件不会伪装为用户回合；转发标记保留，引用正文不混入输入。
- QQ加入平台枚举和C2C/群@事件规范化，签名实现匹配官方Go SDK的已发布测试向量。当前官方方案使用Webhook，未新增已下线的旧WebSocket接收链路。

QQ签名依赖可选扩展：在后端安装`pip install -e ".[platforms]"`。签名验证要求原始body、时间与Ed25519签名，限制体积和时间偏差；op13挑战必须在验证请求之后处理。仅有解析器或签名对象不构成已认证的内部身份。

## 新的宿主接入

`PlatformRuntime`接受宿主的配置源、SQL存储、生成回调和投递端口，不反向依赖编排器。参考宿主在`core_orchestrator/platforms.py`组装Telegram长轮询、discord.py Gateway和独立loopback QQ签名回调。私聊独立持久会话，群聊不打开私有记忆/工具；消息去重、分片回执、未知结果不重放、绑定撤销和账号导出/删除已接通。

配置模板为`platforms.example.json`，私有实际文件为忽略的`companion_platforms_config.json`。完整启用、可信绑定、回执状态、代理路径和验证边界见[平台会话说明](../docs/platform-conversations.md)。Docker镜像包含可选平台依赖，但仍默认不启用账号。不能从模型参数或入站自报user_id授予权限。

真实HTTP/QQ回调和官方Discord SDK的本地HTTP/WebSocket联调通过；SDK延迟READY任务的关闭回收已修复。真实账号验收需专用目标授权，用户已明确“暂不提供账号，先推进其他剩余项”，因此6.2保留待真实验收，不向真实账号试发。

回归：`pytest -q gateway_adapter/tests core_orchestrator/tests/test_platforms.py shared_runtime/tests/test_log_safety.py`。测试使用隔离SQL、本地协议服务和腾讯官方签名向量，不向任何真实用户发送消息。

资料：[Telegram Bot API](https://core.telegram.org/bots/api)、[Discord Gateway](https://docs.discord.com/developers/events/gateway)、[Discord Webhook](https://docs.discord.com/developers/resources/webhook)、[QQ官方Go SDK](https://github.com/tencent-connect/botgo)、[QQ签名参考](https://github.com/tencent-connect/botgo/blob/master/interaction/signature/interaction.go)。
