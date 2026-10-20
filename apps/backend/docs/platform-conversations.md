# QQ、Telegram 与 Discord

路线图6.2进行中。已实现宿主注入、三平台接收/文字回复、显式绑定、SQL收件箱/回执、撤销及隐私清理。真实本地HTTP/QQ回调和discord.py 2.7.1的HTTP登录、WebSocket心跳/Identify/消息分发已测；尚未提供真实机器人和专用测试聊天，不能把这些结果当成平台账号验收。

## 启用入口

1. 在后端安装可选扩展：`pip install -e ".[platforms]"`。Discord只接收文字，不安装或启用Discord语音扩展。2.7系列SDK的延迟READY任务需要额外回收，版本升级须重跑实际本地协议测试。
2. 复制`gateway_adapter/platforms.example.json`为后端目录下的`companion_platforms_config.json`；后者已被Git忽略。用操作系统权限将它限制为宿主账号可读，不能放进公开静态目录、日志或截图。
3. 为需要的平台填写凭据：Telegram/Discord为`token`；QQ为`app_id`、`secret`。内部用户编号应来自当前参考宿主的真实账号。填写精确的外部发送者、聊天目标、私聊/群聊和可选`thread_id`。
4. 只有在已获准向专用测试目标收发消息后，才将根`enabled`、账号的`enabled/receive/reply`及对应绑定的`enabled`设为`true`。`reply=false`不会生成或发送回复；已接收的此类消息不会在以后启用回复时补发。
5. 设置`COMPANION_PLATFORMS_CONFIG_FILE=companion_platforms_config.json`后重启参考宿主。环境变量也可指定私有文件的绝对路径。旧的Telegram token或Discord webhook配置不会自动启动新接收链路。

从未启用切换为启用、添加QQ监听或更换回调端口须重启。运行中的绑定撤销、开关、凭据更新会被重新检查；文件损坏/消失会停止新收发，生成和发送前也会核对。取消不能撤回平台已经收到的消息。

管理账号在设置→运行状态查看连接结果。这里只显示机器人别名、连接状态及回复开关，不返回凭据、外部目标或用户清单。QQ“等待平台回调”表示本地监听已启动，不表示公网地址、平台审核或真实投递已经验证。

## 平台设置

- **Telegram**：使用Bot API长轮询。需要`getMe`成功、现有webhook为空；不会擅自删除旧webhook。只确认已经持久接收或安全忽略的`update_id`。不要让其他服务同时轮询这个机器人。论坛topic的`thread_id`必须精确绑定，普通聊天保持空值。
- **Discord**：使用维护中的discord.py Gateway客户端接收；回复通过无自动重试的官方HTTP API发送到原channel。机器人需在专用服务器/DM中获准读取和发言。默认不请求Message Content特权；如业务需要，应同时在开发者门户和私有配置中明确开启`message_content`。绑定Discord线程时，`conversation_id`就是线程自身的channel ID，`thread_id`留空。
- **QQ**：只实现官方Webhook的`C2C_MESSAGE_CREATE`和`GROUP_AT_MESSAGE_CREATE`，不使用已退役的旧WebSocket方案。C2C的`actor_id/conversation_id`都是发送者`user_openid`；群聊分别为`member_openid/group_openid`。回调入口是独立的`127.0.0.1:<qq_callback_port>/qq/<account_id>`，与主API共用进程和数据库，不改主API的鉴权。宿主须将已配置的HTTPS回调路径转发到该精确入口；签名验证先于JSON解析和挑战响应。

QQ回调请求体上限1MiB、读取总时限5秒，验签包含原始字节与时间戳，允许300秒时钟偏差。队列满/数据库不可用返回503，未认证请求401；正常接收/重复/安全忽略返回op12。op13挑战同样必须先通过请求签名验证。

机器人别名代表同一个真实机器人，不能回收给另一个账号。轮询游标和消息去重键跨开关/密钥轮换保持稳定；换机器人应分配新别名并重新审阅绑定。不可用模型参数、回调自报`user_id`或机器人输出创建/更改绑定。

## 会话与隐私

绑定按平台账号、发送者、聊天、受众和线程精确匹配，无通配符。只接收正常文字，忽略机器人、webhook回声、编辑、转发和未绑定发送者；群聊还必须明确提及当前机器人。引用正文不会自动混入输入。

- 私聊使用明确绑定的内部账号及独立、持久的绑定会话，可读取该账号的私有记忆与宿主已授权能力。Web登录退出与平台凭据是不同入口；停止平台权限应撤销对应宿主绑定。
- 群聊仅根据当前消息生成简短文字，不读私聊记忆、画像、历史或工具；仍按绑定内部账号保存收件和投递记录，以便归属、导出和删除。每个绑定有独立会话ID，不沿用旧SessionManager的跨渠道内存会话。
- 导出/删除包含`platform_inbox`和`platform_bindings`。删除先停止并等待用户任务，再在同一SQL事务中撤销旧绑定并删除消息。只保留不含内部用户、外部账号、正文或密钥的绑定SHA256和撤销时间，避免旧私有配置把已经删除的数据重新带回。新授权需宿主审阅并使用新的绑定`id`。
- 平台游标仅保存机器人作用域的摘要键和数值，不存个人正文；不会因单个用户删除而回退，避免重放其他人的消息。宿主备份、平台保留记录和已投递内容不在本机删除范围内。

## 投递语义

SQL状态为`pending → processing → generated → sending → sent`；安静回复为`ignored`，撤销为`revoked`。失败/中断/不确定分别保留`failed/interrupted/unknown`；明确拒绝为`rejected`。`sent`仅表示平台返回了真实消息ID，不代表收件人阅读。

重启只继续尚未开始处理的`pending`，以及已保存但尚未尝试投递的`generated`。旧`processing`变为`interrupted`，旧`sending`变为`unknown`，不自动重跑模型/工具或重复发送。每个确认分片保存消息ID；后续分片失败不重发之前的部分。没有“自动重试未知结果”接口。

文字按UTF-16单位有界分片，最多4片；Telegram每片4000、Discord1900、QQ保守300。Discord关闭自动提及，Telegram不使用HTML解析，QQ只用普通文字和原始`msg_id/msg_seq`。同目标发出间隔至少1.1秒，分片额外有界等待；429尊重有界Retry-After（1–300秒，缺失为30秒），只约束后续新消息，不重试已经拒绝/不确定的发送。HTTP响应体有大小上限，总请求时限35秒，取消正常传播。

每个用户最多100条在途收件。Telegram/QQ在未持久入箱时不确认；Discord协议没有逐消息确认，接收缓冲100条，溢出明确记录错误。Gateway断开期间和超出resume窗口的消息也可能缺失；不宣称跨平台恰好一次或离线全量补收。

当前参考实现只支持一个宿主进程/worker。不可让两个进程共同运行recover/领取循环；分布式租约、平台历史回填及大规模负载尚未验收。

当前用户的最近50条回执：`GET /gateway/platforms/{user_id}/receipts`，受参考宿主的账号所有权检查保护。该入口不返回token，也不提供任意目标发送。

## 验证

后端：`pytest -q gateway_adapter/tests core_orchestrator/tests/test_platforms.py shared_runtime/tests/test_log_safety.py -W error::pytest.PytestUnhandledThreadExceptionWarning -W error::pytest.PytestUnraisableExceptionWarning`。

验收真实平台时，用隔离数据库、合成用户和专用聊天，逐个平台核对：正常私聊、未绑定用户拒绝、群@边界、线程、重启重复事件、撤销/删除和真实消息ID。不向未明确授权的真实账号发测试消息；密钥只通过本机私有配置提供。

资料：[Telegram Bot API](https://core.telegram.org/bots/api)、[Discord Gateway](https://docs.discord.com/developers/events/gateway)、[discord.py](https://discordpy.readthedocs.io/en/stable/)、[QQ官方SDK](https://github.com/tencent-connect/botgo)。
