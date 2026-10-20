# 当前工程交接

更新时间：2026-10-20。

最新V2.27：6.3实际远端CI/容器已验收，累计36/38（95%）。当前可执行功能已完成；两项按用户明确要求保留：6.2真实平台账号验收暂缓（收发/绑定/SQL/本地协议及官方SDK已实现），8.6先不开发（其他功能完成后讨论并确认方案，不能自动开工）。草稿PR10：https://github.com/TrisomyManager/AgentGirl/pull/10；通过的远端运行：https://github.com/TrisomyManager/AgentGirl/actions/runs/39377276774。Linux后端839（67.24秒，严格线程/无法回收异常警告）、桌面工具16、Web86、双端测试/审计/构建、6导入契约、wheel、实际PostgreSQL/pgvector+Redis7+Neo4j迁移/图证据/清理/重启门禁及非root Docker登录/重启/持久/删除均通过。修复SQLAlchemy异步依赖、PC干净环境SDK类型解析、FFmpeg CI依赖及FastAPI0.150惰性路由所有权参数；旧广播不再假报成功。发布快照保留原master工作区、暂存和所有既有改动；.codex/config.toml中的密钥曾进入远端历史，快照移除但本机保留，已告知用户轮换，不自动重写历史。没有部署或发布镜像，没有真实平台消息，未安装/开发3D。详见apps/backend/docs/deployment.md及platform-conversations.md。

最新V2.26：35/38（92%），多平台实现已落地，真实账号验收按用户要求暂缓；用户明确3D先不开发，完成其他功能后讨论并确认技术方案，勿开始8.6。继续6.3实际容器/远端CI。平台有宿主私有配置、精确身份/目标绑定、独立会话、SQL收件/游标/回执、Telegram轮询、Discord Gateway、QQ签名loopback回调、分片/限流/未知结果不重放、撤销及隐私导出删除；群聊不读取私有记忆/工具。旧token不会启动新接收。删除保留最小绑定哈希撤销回执，重授权须审阅并更换绑定id；主API不增加公共鉴权豁免。官方Discord SDK本地真实HTTP/WS发现并修复READY任务残留。后端836（55.22秒，严格线程/无法回收异常警告）、Web86、双端构建和6导入契约通过；新wheel包含全部平台代码/依赖元数据。没有向真实平台账号发消息。GitHub连接器可访问本人公开仓库；本机无Docker/WSL，继续远端CI。详见apps/backend/docs/platform-conversations.md。保留所有既有改动与原生O2默认值，不新建子代理。

最新V2.25：2.3已验收，35/38（92%），继续6.2/6.3/8.6。每条SQL记忆独立证据/事实，召回带来源到最终核对；旧迁移/无来源/其他账号/被删或淡化事实不恢复回复。恢复与精确线索再激活保留，修复召回恢复中的提前提交/重复计分。单删持久记录、来源删除标记、按用户锁及5秒轮转清理（批4用户/每用户32来源）通过；实际无需重启恢复和新进程恢复均通过。图服务器拒绝旧代次写入，重复旧清理保护新内容；完整清理保留仅含摘要账号键/代次的最小删除回执，不含正文。真实冲突值/账号/淡化/恢复/单删/迁移、方舟3条事实与干净wheel实际SQL/Neo4j通过。后端778（42.86s）、Web85/双构建、6导入契约通过；远端CI仍未运行。详见apps/backend/docs/neo4j-ownership.md。私有PG/Garnet/Neo暂留，元数据output/qa/production-context.json，凭据只在其临时目录。下一项平台：原Telegram仅发送且HTML、Discord仅webhook无可靠ID、QQ无接收；会话映射内存且跨渠道共享，应做宿主绑定及显式接收/回复开关。旧token不能自动启用新接收器，真实收发需专用测试目标授权，当前没有外部账号。goal保持active，保留所有既有改动。

最新V2.24：仍34/38（89%），2.3继续开发，不提前验收。真实Neo4j5.26.32/Temurin21、共享节点审阅迁移、嵌套/账号隔离、1/2跳、导出/删除重试与新进程启动恢复通过。实际方舟提取/向量产生3条图事实，融合检索与整库清理通过。单条记忆删除后外部图事实仍残留，下一步补每条记忆的不可变来源、按SQL证据过滤的召回及持久解绑，保护其他记忆/账号。现graph_lifecycle含按事件循环/用户的锁、SQL代次和memory_graph_cleanup记录，启动最多重试4个，容量/公平性边界保留。后端773（46.04s，严格线程警告）、Web83/双端构建、6导入契约、干净wheel实际宿主/ASR/记忆/扩展通过。连接日志只保留协议/主机/端口，临时QA凭据已轮换并脱敏日志。详见apps/backend/docs/neo4j-ownership.md。私有PG/Garnet/Neo暂保留供后续联调，元数据output/qa/production-context.json，凭据只在其临时目录；8044/5197关闭。继续2.3来源解绑及6.2/6.3/8.6，goal保持active。

最新V2.23：2.1生产SQL已验收，34/38（89%），持续其余四项。真实PostgreSQL17.11/pgvector0.8.7非超级用户，宿主两进程重启、原文/摘要、18次并发去重、JSON标签、失败回滚、用户隔离、图谱/导出删除与旧写入屏障通过。实际方舟1024维向量/三轮批次压缩/重启后新会话回忆通过；临时缓存为真实Garnet v2.2.3，不冒充Redis7。向量列改为保留值转换；历史迁移默认预览，--apply同事务转换，非法值回滚/旧维度拒绝；wheel支持模块命令。后端765（40.47s）、存储/人格/隐私133（4.52s）、6导入契约通过；前端无变动沿用81/双构建。CI新增PostgreSQL/Redis7门禁，远端未运行。详见apps/backend/docs/production-storage.md。继续Neo4j/旧图归属、多平台、实际Docker/CI和3D；临时PG/Garnet保留用于下一项图联调，元数据在忽略output/qa/production-context.json。

最新 V2.22：额外模块边界收敛已验收，仍 33/38（87%），继续全部剩余计划。后端 765 passed（43.05s，严格线程警告）、6 个导入契约通过；前端无变动，沿用 V2.21 的 Web81/双端构建。旧 shared/action_layer 已归档并移出源码/wheel，保留 action_layer 运行时能力键。记忆读取改为宿主注入并检查会话归属，旧 HTTP 回退保留；ASR 支持 app 独立工厂和按请求/连接关闭，重复取消等待清理。WAV 用实际帧算时长，未知编码返回0；原生 O2 仍为1.2.1.1，TTS HTTP 仍是宿主单例。实际隔离上传 ASR/SQL/O2 与干净 wheel 注入通过。AST 反向/SDK/横向导入为零，角色文本基线仍有差异。详见 apps/backend/docs/module-injection.md。继续生产 SQL、Neo4j/迁移、多平台、实际 Docker/CI 和3D。

最新 V2.21：8.5 音频协议已验收，33/38（87%），继续全部剩余计划，goal 保持 active。后端 758（42.34s，严格线程警告）、Web 81、双端构建通过。实际 O2 新旧协议、打断后下一轮与浏览器文件合成麦克风的 VAD/25 上行帧/6 下行帧/6 次播放/挂断清理通过；没有读取真实麦克风。详见 backend/docs/audio-transport.md、packages/audio-transport/README.md。保留协商后开麦、旧 ready 回退、双向序号、段归属、取消后发送完成、致命错误清理与串行重拨。访问中间件必须选择公开子协议名，不回显凭据。离线 Protobuf 编码评估没有引入运行时依赖，不宣称端到端提速。干净 wheel 新协议/宿主/目录调用通过；架构扫描排除生成 build/dist，反向编排/SDK 为零，历史横向/角色文本差异仍未清零。QA 8044/5197 与浏览器已关闭。剩余五项：2.1 生产 SQL、2.3 Neo4j/迁移、6.2 多平台、6.3 Docker/CI、8.6 3D；额外兼容层物理清理和 ASR Protocol 注入也保留。

下一实现建议：先收敛额外架构项。当前 Python 实际旧入口还在 device_coordination/registry.py、memory_system/db.py 与 working.py、user_profile、persona_store 和 integration_minimal 示例；动作/共享测试仍在旧目录，物理删除前迁移到新包并更新打包/导入契约。action_executor/handlers.py 仍直接导入 memory_system 的 recall/list/working 三处，应改宿主注入端口（runtime_hooks 组装），不要把跨模块测试放回业务测试目录。ASRProvider 当前返回 str，而 ASRClient 上传接口返回 VoiceTranscriptionResult、PCM 接口返回 str；设计注入时需明确格式/元数据/生命周期，不应伪造识别置信度或压缩音频时长。外部平台现仅有 Telegram 发送和 Discord Webhook 旧骨架，QQ/真实收发/身份绑定尚未验收；账号真实测试与实现分开记录。当前本机无已知 Docker/Java/PostgreSQL 服务，生产实例可继续查找隔离便携运行时，不能把 Lite/模拟代替联调。

最新 V2.20：6.4 设置与管理已验收，32/38（84%），持续全部剩余计划，goal 保持 active。后端 750（44.58s，严格线程警告）、Web 75、双端构建通过。真实隔离浏览器验证分类/角色、模型保存/方舟连接、语音保存/TTS、陪伴刷新保留、内置扩展安装停用和普通账号/390px；宿主授权后真实方舟任务调用文本工具。干净来源 wheel 独立宿主/目录安装/授权调用通过。详见 apps/backend/docs/administration.md；保留安装默认关闭、固定打包目录/摘要、禁止覆盖/链接/预授权冲突、宿主单独授权、取消后磁盘 worker 完成。旧 build 缓存不作为分发来源，未递归删除。跨模块事项测试已移至 core_orchestrator/tests/test_user_state.py，统一 async 生命周期。继续 8.5 协议评估/升级、生产存储、多平台、部署与 3D；旧检查点为历史。

最新 V2.19：仍 31/38（82%），继续全部剩余计划。后端严格回归 745（63.84s），桌面工具 16、Web 67、PC 实际打包代理与双端构建通过；双端 npm audit 为零。使用 Node 24，系统 Node 25 不支持当前 Vitest。真实 Windows win-unpacked 验证 app://companion 自有来源、资料目录、Python 桥、方舟聊天与匹配的本地 VAD WASM（合成麦克风），页面错误为零；签名安装器、Docker/远端 CI 和其他 OS 仍未验收。保留 PC 依赖去重、packages/web-runtime-assets 与 gh-pages/global-agent 覆盖；自定义 CORS 显式保留 app 来源，禁止通用 null。详情见 PC README 和 backend/docs/deployment.md。下一步继续管理面板与其他剩余项。

当前继续点：7.1 与 5.4 已验收，31/38（82%），持续开发，goal 保持 active。设备私有桥、能力/根目录/确认与 CAS 已落地，见 apps/backend/docs/desktop-execution-boundaries.md。实际隔离 Electron/Python/SQL/文件读写/确认期间取消，以及 Windows 真实 show、提醒 SSE 和刷新去重通过。自动化选择本机对话框，不宣称人工视觉确认。后端 742（58.02s）、桌面工具 16、Web 67、双端构建通过。下一步治理旧 Vue/Vite/打包依赖的已知审计告警，再继续部署与剩余计划。Electron 已升级 44.9.0，ws 8.22.0，官方 binary 经 SHA256 核验后安装。6.3 尚缺 Docker/远端 workflow 实测，本机仍无 Docker。QA 8044/5197 与 Electron 全部关闭。

最新 V2.17：普通/SSE/工具/任务/TTS 在发出前检查；任务补充合并后重查，主动拒绝不推送。原生无 caption 音频暂存上限 30 秒，尾文字最多等 2 秒；未知策略/自定义 BLOCK 需要完整输出，拒绝时单独合成替代。真实预防讨论、6 段 TTS、O2 519108 字节音频与连续性通过。规则边界见 apps/backend/docs/content-safety.md。记忆网络从用户 SQL 索引展示原文依据，默认不显示自动关键词；查看不激活淡化，切换/删除屏蔽旧响应。浏览器点选、筛选、清空后刷新及 390px 通过，见 memory-visualization.md。严格后端 729（58.61s）、Web 66，双端构建通过。QA 8044/5197 和 graph-qa 已关闭。下方为历史记录。

最新 V2.16：默认单进程参考宿主的 7.3 已验收，27/38（71%），继续剩余全部工作。账号隔离/可撤销会话、导出/删除、用户工作代次与持久待重试清理、浏览器清理 receipt 核对已落地；真实聊天/TTS/原生通话鉴权/登出及浏览器切换/导出/删除/丢失响应后刷新通过。后端 689（65.63s，线程警告视为错误）、Web 63、Web/PC 构建通过。详见 apps/backend/docs/access-and-privacy.md。生产 SQL/Neo4j/Redis 与多 worker/独立模块部署仍保留，继续 CI/部署等计划。

最新 V2.15：6.1 插件基础已验收，26/38（68%），继续全部剩余工作。宿主私有授权控制默认禁用的目录插件，同工作任务管理资源、摘要热更和撤销；实际方舟任务调用旧/新代码版本通过。后端 666 passed（55.04s）、插件/协议子集另 24 passed；Web 53、Web/PC 构建通过。详见 apps/backend/plugins/README.md；下方 V2.14 及更旧计数为历史。

最新 V2.14：5.2/5.3/8.4 已验收，25/38（66%），继续插件与生态及其余全部计划。独立 avatar_runtime / TS 实际音频时钟已落地，真实播放/停止/7 段刷新重播及原生 O2 时间轴验证通过，656 后端 / 53 Web 测试通过，Web/PC 构建及 avatar 导入契约通过。原生缺少句子文字时必须在首个音频前宣布格式/时间轴；默认模型仍为 1.2.1.1。下方 23/38 也是历史快照，以此段和执行表为准。

用户最新指令：**继续，直到计划全部完成**。5.2 图片理解已完成真实方舟与浏览器验证，累计 23/38 项（约 61%）。继续 5.3/8.4 表情与音频同步，全部其他未完成计划保留。图片边界见 apps/backend/docs/image-understanding.md。最新完整后端回归 646 passed，Web 46 passed，Web/PC 构建通过；新增 SQL 图片记录用例另行回归。下方较早轮次的暂停及旧完成数均为历史记录。

## 项目与边界

- 后端 apps/backend，Web apps/web，PC apps/pc-client，协议 packages/contracts，联调 integration。
- 最终定位：宿主无关、可独立集成的陪伴 AI 模块库与小暖参考应用。现有 Electron 外壳可构建；HTTP PC 设备模拟器继续存在。
- 不搜索或引入已删除的外部工程。默认火山方舟 + 豆包语音。密钥与运行时 JSON 保持忽略，不输出密钥。
- 进入时已有大量火山引擎和 Live2D 未提交改动，均须保留；勿用 reset、clean 或批量覆盖还原。

## 当前已实现

- 主动陪伴：持久化用户开关、四类规则、时区、免打扰、冷却和日上限；真实用户活动独立记录。每个用户有独立评估任务，关停会取消并等待。
- 提醒和关怀消息：push_events 数据库 outbox，提醒状态与消息原子提交；重启后可分页补收；前端按事件/发生次数去重，避免循环提醒只响一次。
- 关怀生成先产生候选，只有入库后才观察助手消息；不会把 AI 自己的问候当成用户活跃，也不把被取消的候选写进对话记忆。
- Lite 记忆：conversation_turns、session_digests 持久化；滚动原文窗口之外保留摘要与姓名/偏好等结构事实；模型摘要异常有摘录回退；清空同时删除原文和摘要。
- core_orchestrator/runtime_hooks.py 负责宿主适配。主动关怀和语音记忆写回均不再反向导入编排器。
- Web 主动陪伴设置可保存；修复隐藏能力面板首次打开不加载的问题；后台消息接 Electron 通知桥。
- PC 构建修复项目引用、Electron 类型与共享静态资源；依赖更新至 Electron 33 分支最新补丁。
- pytest 临时数据库隔离；Lite 应用默认数据库固定到后端目录；persona Lite 启动不连接 Redis/PostgreSQL。

## 验证

- 后端基线 361 passed；加入可靠性与记忆连续性用例后回归 377 passed，仍忽略 voice_layer/tests/test_voice.py 和 memory_system/tests/test_memory.py。
- 最新完整回归 379 passed（53.20 秒），动作模块 67 passed；注入适配、Lite 启动优化、关怀优先级与动态日上限均已包括在最终验证中。
- Web 15 tests passed，Web 和 PC build passed；原生桌面通知尚未打包实测。
- Playwright 隔离实例已验证设置保存并刷新保留；后端停止期间到期的提醒在重启后成功补收，刷新后不重复。截图位于 output/playwright/（忽略输出）。
- 架构扫描还有历史横向依赖及角色硬编码，不能称全绿；已清除主动关怀/语音写回的反向编排依赖，尚需继续按最终模块边界收敛。

## 后续必做

以 DEVELOPMENT_EXECUTION.md 的原计划编号继续。5.1、8.1/8.2 已验收；图片与同步呈现仍待完成。记忆生产 PostgreSQL/Neo4j 联调与旧节点所有权迁移、插件平台、完整数据控制和 avatar_runtime 继续保留。外部服务适配与真实联调分开记录，不能用占位符冒充完成。

## 本轮临时进程

本轮 QA 后端端口 8019、Web 端口 5189、Playwright 会话 care-qa 均已关闭。QA 数据库保留在系统临时目录 companion-qa-20261019.db，与用户数据库隔离；截图保留供审阅。用户原有服务未改动。


## 第二轮更新 · V2.7

- 重要性规则、可恢复淡化、真实访问频率、本地实体关系 PageRank/向量融合、旧索引补建均已实现。
- 旧对话默认每 3 轮批次摘要；SQL 在两种模式中都是原文主存。Redis 只保留临时用户上下文，旧 Redis 对话缓存不再作为恢复来源。
- Dream 在用户当地凌晨 2–6 点且 30 分钟无互动时，追赶最近 7 天。指纹与短租约避免并发重复生成，取消释放租约，模型请求失败保留摘录。
- 用户明确陈述决定偏好变化；历史日总结不能覆盖更新偏好。离线关系指标复核仍待在 C 中完成，不能将 2.5 整体标为完成。
- 记忆库、原文存档、索引和日总结原子清空；版本锁/来源锁防止旧后台结果重新写回。前端请求代次阻止迟到的搜索结果覆盖清空状态。
- SQLite 使用 WAL 与分批元数据维护；已验证读取期间仍能提交新记忆。
- 最新完整回归 407 passed（49.19 秒），Web 19 tests passed，Web/PC build passed；新增模块 lint 通过；反向编排依赖 0，直连 SDK 0。
- 真实方舟日总结与旧对话压缩已在隔离数据中成功。浏览器验证淡化恢复、日总结、跨会话读取、用户隔离、UTC 显示及清空后归零。桌面和 390px 移动布局截图在 output/playwright/，已忽略。
- 本轮隔离 QA：端口 8020/5190，会话 memory-qa；现已关闭。数据库为系统临时目录 companion-memory-qa-20261019.db；其中仅有合成测试数据，user_001 的记忆库/回顾已由 UI 清空，另外的压缩验收用户保留在隔离数据库。用户原有服务未改动。


## 第三轮更新 · V2.8

- 2.5、3.1、3.2、3.3、8.3 已验收；累计 14/38 项（37%）。长期目标继续 active，不要标为全部完成或请求常规开发授权。
- 新增 persona_engine/state_store.py、reaction.py、reaction_service.py、relationship_review.py，及 shared_runtime/response_behavior.py。情绪/关系完成事务按用户/turn_id 去重，里程碑也在同一用户锁下更新，避免覆盖并发聊天。
- EmotionEngine 改为确定性连续坐标；负 valence 保留，过渡有界、按时间平复。离散标签仅兼容呈现。生成前独立分类，生成文字不能反向给自己打标；主流程不再保留旧的回复关键词推断器。
- 独立分类默认 3 秒超时，可配置独立小模型。仅接收用户输入；缺字段、越界、非有限数、低置信度回退，取消不吞掉。默认火山配置未改变。
- 普通/流式生成共用情绪参数；严肃场景抑制 emoji，任务保留足够预算。可空 expression_emoji 由服务端语境策略决定，前端避免重复表情；刷新会加载持久化情绪，迟到结果不覆盖新一轮状态。
- Dream 通过宿主注入 relationship_observer，不产生模块横向依赖。新版原文带 persona_observation_version=1 与 reaction；复核用在线相同 turn 事件补记遗漏事务，旧档案不重复计分。补记不更改当前情绪/今日活跃时间。重试不重新总结。
- Memory followup 和 graph_facts 的淡化绕过已修复；组件卸载后的异步 Live2D 加载会释放过期模型，避免访问旧画布。
- 最终完整后端回归 433 passed（52.50 秒）；Web 19 tests passed，Web/PC build passed；新增模块 lint 通过。架构反向编排依赖 0，直连 SDK 0，历史横向依赖 2、硬编码 78 仍待清理。
- 真实方舟分类返回 source=model；真实聊天产生 concerned/负 valence，重启后保留；模型日总结和复核重试后互动数仍为 1。浏览器验证开心回复、语音播报、刷新后保持开心；截图 output/playwright/emotion-positive-chat.png。
- 隔离 QA：端口 8021/5191，会话 emotion-qa，数据库位于系统临时目录 companion-emotion-qa-20261019.db，只有合成数据。浏览器与上述 QA 服务现已关闭。用户原有服务未改动。
- 后续继续：3.4 自然发言的按用户开关/概率/前端静默展示，然后 D 工具编排。生产 PostgreSQL/Neo4j、原生通知、完整数据控制、实时语音独立反应同步仍需完成。


## 第四轮更新 · V2.9

- 3.4 自然发言与 4.4 路由优化已验收，累计 16/38 项（42%）。长期目标继续 active，下一步为 4.1–4.3 分工编排、MCP 和受控多步任务；同会话并行输入的统一调度在 4.1 中处理。
- 新增 persona_engine/conversation_preferences.py、reply_policy.py、前端 ConversationSettings.vue。默认逐条回复；开关/概率按用户保存，缺失上下文或设置不可读时也回复。语音/图片/任务/问题/待确认/低落上下文和连续安静受保护。
- 普通与 SSE 回复均有 reply_suppressed/talk_value/reply_reason。安静轮次仍保存历史、活动和关系，跳过文字/语音/动作；前端只给原用户消息加“已收到”，无空白回复或语音错误。自动语音开关刷新后保留。
- 新增 /persona/observe_turn，独立服务可记录安静轮次且按用户/turn_id 去重。SSE done 已补齐 expression_emoji 与 error。活动记录失败不再连带阻止人格事务。
- 新增 core_orchestrator/routing_rules.py 与 tests/data/intent_cases.json，独立证据只来自当前输入。少样本模型有 3 秒超时、格式/有限数/低置信度校验；明确否定、设备和回忆请求有规则复核。pytest 禁止真实意图调用，合约测试需明确开启 mock。
- tools/eval_intent_router.py --mode rules/model：45 条合成用例均通过；真实模型组合管线采用 32 条模型、13 条规则，含一次超时回退。此前真实模型将“我叫什么”误判 chat，现有明确自我事实查询规则防回归。不要把此用例集准确率描述成泛化准确率。
- shared_runtime/reminder_language.py 供宿主和动作模块共用。“不用再提醒我喝水了”会取消当前用户唯一匹配提醒；歧义要求选择，明确所有才批量取消。取消入口要求 user_id，不会误入新建工具。
- 浏览器实际验证：设置保存/刷新、关闭自动语音后保持、安静的“已收到”、下一条恢复回复、插入主动问候问题时不静默；390px 设置无溢出。真实 API 取消提醒后 pending=0。合成数据库 user_001 与 qa-route-user，不含真实用户数据。
- 验证截图 output/playwright/natural-reply-settings.png、natural-reply-quiet.png、natural-reply-settings-mobile.png，已忽略。
- Web 25 tests passed，Web/PC build passed。架构扫描反向编排 0、直连 SDK 0，历史横向依赖 2、硬编码 78；严格基线还未全绿。
- 回归发现后台记忆提取任务未被宿主等待，测试事件循环关闭后仍有 SQLite 回调。新增 core_orchestrator/memory_tasks.py 托管任务，宿主关闭前等待/取消并完成异步清理；直接 SDK 测试也在事件循环关闭前清理。完整回归将线程警告视为错误，537 passed（43.91 秒），仅余三条既有弃用提示；Web 25 tests passed，Web/PC build passed，新文件 lint 与空白检查通过。

## 第五轮更新 · V2.10

- 4.1–4.3 已验收，累计 19/38（50%）。目标继续 active，直接推进语音/多模态波次，不请求重复授权。
- 新增 `core_orchestrator/specialists.py`、`turn_coordinator.py`；Chat/Task/Memory/Device 共享普通/SSE 委派。同用户同会话串行，不同会话可并行。Memory 固定使用记忆工具，修复普通路径吞掉记忆结果的问题。
- 新增 `action_executor/tool_schema.py`、`tool_catalog.py`、`mcp_client.py`、`task_agent.py`、`task_policy.py`、`task_store.py`，以及顶层 `mcp_actions_server.py`。MCP 使用官方 SDK（1.30），由 worker 同任务进入/退出传输域，支持 stdio/Streamable HTTP；配置来自 `COMPANION_MCP_CONFIG_FILE`，含密钥的 companion_mcp_config.json 忽略。
- SQL 保存 task_runs/task_steps。默认 6 步/60 秒、规划 12 秒/调用 15 秒；按同轮唯一约束返回原记录，拒绝相同工具参数重做。未知结果不重放；只有 awaiting_input 可补充续办，已完成步骤保持。任务 API 与 TaskHistory UI 已接通，续办刷新待办，用户切换拒绝旧响应。
- 本地 MCP 真实 stdio/HTTP、内置桥、参数校验/身份绑定、取消/超时/重启、任务接口隔离均通过。真实方舟两步任务成功；真实补充信息续办只新建提醒、不重做查时。浏览器刷新保留与 390px 布局通过。
- 最终完整后端 573 passed（47.41 秒，线程警告视为错误）；Web 29 tests passed；Web/PC build passed。新模块 lint/空白检查通过；架构反向依赖 0、直连 SDK 0、历史横向依赖 2、硬编码 78 未清理。
- 参考宿主为单进程：会话锁与启动时任务恢复不支持多个独立 worker 同库竞用。MCP 配置按明确用户开放，不代表已完成插件权限/设备沙箱。原计划生产数据库、原生通知、完整隐私、多模态/语音与 avatar_runtime 仍继续。
- 本轮合成数据库：系统临时目录 companion-task-qa-20261019.db。QA 后端 8023、Web 5193、Playwright task-qa；结束时关闭这些临时进程，保留隔离数据库与 output/playwright 截图。用户原服务/数据未改。

## 第六轮首步历史记录（由下方 V2.11 更新覆盖）

- D 后继续 E：新增 `voice_layer/streaming_pipeline.py`，有界句子队列把 LLM 消费与 TTS 输出分开；本地/云端 realtime 会话接入。尚未完成 TTS 下一句并行预合成或 SSE voice_segment，不验收 8.1。
- 流取消等待 token/tts 两个子任务退出，显式关闭嵌套迭代器；TTS 无音频/错误向上报告。session start 先取消旧轮；用户/session 变化清空旧历史，避免旧输出写到新上下文。
- `local_tts.py` 原线程忽略 run_coroutine_threadsafe 的结果，实际队列无背压且会跨循环投递。现使用有界 queue.Queue、threading.Event、引擎锁、有限等待 join；取消后不再接触事件循环。原生当前批次可能继续计算，但输出丢弃。
- `SentenceSegmenter` 修复有标点的超长 token 绕过最大长度；增加 pipeline / session / local worker 生命周期回归。语音模块+分段器 151 passed，线程警告视为错误。
- 下一步：按设计实现两个有界合成工作单元和有序 PCM 下发，接 SSE voice_segment；处理前端异步解码在打断后复活、奇数字节 PCM、队列/播放时间轴、实时分类/情绪/口型同步。默认 volc_realtime/O2 保持，须实际服务音频联调后验收，不靠 mocks 标完成。
- QA 8023/5193 与 Playwright task-qa 已关闭；无本轮遗留运行服务。MCP 配置原子校验最后追加的真实协议回归 14 passed；D 完整基线 573 passed，后续语音变更的最新完整结果见执行记录。
- 最新完整后端 587 passed（44.06 秒，线程警告视为错误），语音+分段器 151 passed；Web 29 tests passed，Web/PC 构建通过。新模块与本次改动的两个 realtime provider lint 通过。目标保持 active，原计划仍验收 19/38。

## 第六轮完成 · V2.11（暂停开发）

- 8.1/8.2 已验收，21/38（55%）。按用户最新要求暂停，不启动下一项；完整计划尚未完成。
- `core_orchestrator/streaming_voice.py` 注入合成回调，有界并发、按序交付；客户端以 `supports_segmented_voice=true` 协商 SSE 分段。事件为 voice_segment/voice_segment_error/voice_done；最终响应保存 voice_mode/voice_segments。失败只影响单段；老客户端保留全文语音。
- cloud/local realtime 使用 `stream_pcm_speech`；本地并发 1、云端 2，PCM 队列与 4 KiB 帧有界，取消等子任务/迭代器退出。录音上限 60 秒，超限可恢复；reset 清除溢出状态。本地 Piper 用有界线程桥，TTS wrapper 的 aclosing 缺失导入已修复。
- Web/PC 支持实时分段播放、停止/重听和刷新保留。实时播放代次丢弃迟到解码，压缩块按序，PCM 奇数字节衔接；结束事件等待真正播放结束。自适应启动缓冲 40–250ms、待播含新块最多 30s、待解码 16、单帧 2 MiB；挂断后的迟到麦克风授权会释放。
- 原生豆包打断后屏蔽旧输出直到下一次 ASR 结束。实际 O2 验证确认后 2 秒残留音频 0 字节，下一轮重新收到语音。默认 volc_realtime/O2 保持。
- SQLite 取消建连可能让 aiosqlite 工作线程回调已关闭循环；`shared_runtime/database/sqlite_lifecycle.py` 等建连/关闭/线程退出后再传播取消，测试覆盖真实连接和二次取消，禁止以忽略线程警告掩盖。
- 最终后端 603 passed（49.76 秒，线程警告视为错误，3 条既有弃用提示），Web 42 passed，Web/PC builds passed。本轮新增模块与实时管线 lint 通过；tts.py 有 7 条既有样式告警，架构/全仓 lint 仍有历史欠项。
- 真实 7 段聊天语音成功，首段先于末 token；前两段下载并经豆包 ASR 回识别通过。20 组相同 101 字/三句文本、交替顺序真实对比，40/40 成功，首音中位 6.703s → 4.234s（36.8%）；该固定样例不等于所有网络/文本收益，未宣称 50% 提升。
- 浏览器自动播报、停止/重听、刷新保存和 390×844 布局已验。忽略目录 output/playwright/ 下保留 streaming-latency.json、streaming-voice-stopped.png、streaming-voice-mobile.png。隔离数据库在系统临时目录 companion-streaming-qa-20261019.db；后端 8024、Web 5194、浏览器 streaming-qa 已关闭。
- 5.1 完整实时人格链路、5.2 图片理解、5.3/8.4 表情/口型同步、生产数据库、原生桌面通知及其他计划继续保留。恢复后先读 DEVELOPMENT_EXECUTION.md，再选择未验收项。
- 本轮 QA 端口 8022/5192、Playwright natural-qa；均已关闭。系统临时目录 companion-natural-qa-20261019.db 保留合成数据，未改动用户原有服务。
- 生产 PostgreSQL/Neo4j、旧图节点迁移、实时语音独立反应、原生通知、数据控制、插件与形象等全部未完成项目继续有效，不要将目标标为完成。
