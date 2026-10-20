# 陪伴类 AI 智能体项目执行计划

> 版本：V4.2
> 日期：2026-10-19
> 当前阶段：持续完成全部计划 · 默认宿主数据控制已验收，继续部署与生态

最新V2.27：6.3实际远端CI/容器已验收，累计36/38（95%）。当前可执行功能已完成；两项按用户明确要求保留：6.2真实平台账号验收暂缓（收发/绑定/SQL/本地协议及官方SDK已实现），8.6先不开发（其他功能完成后讨论并确认方案，不能自动开工）。草稿PR10：https://github.com/TrisomyManager/AgentGirl/pull/10；通过的远端运行：https://github.com/TrisomyManager/AgentGirl/actions/runs/39377276774。Linux后端839（67.24秒，严格线程/无法回收异常警告）、桌面工具16、Web86、双端测试/审计/构建、6导入契约、wheel、实际PostgreSQL/pgvector+Redis7+Neo4j迁移/图证据/清理/重启门禁及非root Docker登录/重启/持久/删除均通过。修复SQLAlchemy异步依赖、PC干净环境SDK类型解析、FFmpeg CI依赖及FastAPI0.150惰性路由所有权参数；旧广播不再假报成功。发布快照保留原master工作区、暂存和所有既有改动；.codex/config.toml中的密钥曾进入远端历史，快照移除但本机保留，已告知用户轮换，不自动重写历史。没有部署或发布镜像，没有真实平台消息，未安装/开发3D。详见apps/backend/docs/deployment.md及platform-conversations.md。

最新V2.26：35/38（92%），多平台实现已落地，真实账号验收按用户要求暂缓；用户明确3D先不开发，完成其他功能后讨论并确认技术方案，勿开始8.6。继续6.3实际容器/远端CI。平台有宿主私有配置、精确身份/目标绑定、独立会话、SQL收件/游标/回执、Telegram轮询、Discord Gateway、QQ签名loopback回调、分片/限流/未知结果不重放、撤销及隐私导出删除；群聊不读取私有记忆/工具。旧token不会启动新接收。删除保留最小绑定哈希撤销回执，重授权须审阅并更换绑定id；主API不增加公共鉴权豁免。官方Discord SDK本地真实HTTP/WS发现并修复READY任务残留。后端836（55.22秒，严格线程/无法回收异常警告）、Web86、双端构建和6导入契约通过；新wheel包含全部平台代码/依赖元数据。没有向真实平台账号发消息。GitHub连接器可访问本人公开仓库；本机无Docker/WSL，继续远端CI。详见apps/backend/docs/platform-conversations.md。保留所有既有改动与原生O2默认值，不新建子代理。

最新V2.25：2.3已验收，35/38（92%），继续6.2/6.3/8.6。每条SQL记忆独立证据/事实，召回带来源到最终核对；旧迁移/无来源/其他账号/被删或淡化事实不恢复回复。恢复与精确线索再激活保留，修复召回恢复中的提前提交/重复计分。单删持久记录、来源删除标记、按用户锁及5秒轮转清理（批4用户/每用户32来源）通过；实际无需重启恢复和新进程恢复均通过。图服务器拒绝旧代次写入，重复旧清理保护新内容；完整清理保留仅含摘要账号键/代次的最小删除回执，不含正文。真实冲突值/账号/淡化/恢复/单删/迁移、方舟3条事实与干净wheel实际SQL/Neo4j通过。后端778（42.86s）、Web85/双构建、6导入契约通过；远端CI仍未运行。详见apps/backend/docs/neo4j-ownership.md。私有PG/Garnet/Neo暂留，元数据output/qa/production-context.json，凭据只在其临时目录。下一项平台：原Telegram仅发送且HTML、Discord仅webhook无可靠ID、QQ无接收；会话映射内存且跨渠道共享，应做宿主绑定及显式接收/回复开关。旧token不能自动启用新接收器，真实收发需专用测试目标授权，当前没有外部账号。goal保持active，保留所有既有改动。

最新V2.24：仍34/38（89%），2.3继续开发，不提前验收。真实Neo4j5.26.32/Temurin21、共享节点审阅迁移、嵌套/账号隔离、1/2跳、导出/删除重试与新进程启动恢复通过。实际方舟提取/向量产生3条图事实，融合检索与整库清理通过。单条记忆删除后外部图事实仍残留，下一步补每条记忆的不可变来源、按SQL证据过滤的召回及持久解绑，保护其他记忆/账号。现graph_lifecycle含按事件循环/用户的锁、SQL代次和memory_graph_cleanup记录，启动最多重试4个，容量/公平性边界保留。后端773（46.04s，严格线程警告）、Web83/双端构建、6导入契约、干净wheel实际宿主/ASR/记忆/扩展通过。连接日志只保留协议/主机/端口，临时QA凭据已轮换并脱敏日志。详见apps/backend/docs/neo4j-ownership.md。私有PG/Garnet/Neo暂保留供后续联调，元数据output/qa/production-context.json，凭据只在其临时目录；8044/5197关闭。继续2.3来源解绑及6.2/6.3/8.6，goal保持active。

最新V2.23：2.1生产SQL已验收，34/38（89%），持续其余四项。真实PostgreSQL17.11/pgvector0.8.7非超级用户，宿主两进程重启、原文/摘要、18次并发去重、JSON标签、失败回滚、用户隔离、图谱/导出删除与旧写入屏障通过。实际方舟1024维向量/三轮批次压缩/重启后新会话回忆通过；临时缓存为真实Garnet v2.2.3，不冒充Redis7。向量列改为保留值转换；历史迁移默认预览，--apply同事务转换，非法值回滚/旧维度拒绝；wheel支持模块命令。后端765（40.47s）、存储/人格/隐私133（4.52s）、6导入契约通过；前端无变动沿用81/双构建。CI新增PostgreSQL/Redis7门禁，远端未运行。详见apps/backend/docs/production-storage.md。继续Neo4j/旧图归属、多平台、实际Docker/CI和3D；临时PG/Garnet保留用于下一项图联调，元数据在忽略output/qa/production-context.json。

最新 V2.22：额外模块边界收敛已验收，仍 33/38（87%），继续全部剩余计划。后端 765 passed（43.05s，严格线程警告）、6 个导入契约通过；前端无变动，沿用 V2.21 的 Web81/双端构建。旧 shared/action_layer 已归档并移出源码/wheel，保留 action_layer 运行时能力键。记忆读取改为宿主注入并检查会话归属，旧 HTTP 回退保留；ASR 支持 app 独立工厂和按请求/连接关闭，重复取消等待清理。WAV 用实际帧算时长，未知编码返回0；原生 O2 仍为1.2.1.1，TTS HTTP 仍是宿主单例。实际隔离上传 ASR/SQL/O2 与干净 wheel 注入通过。AST 反向/SDK/横向导入为零，角色文本基线仍有差异。详见 apps/backend/docs/module-injection.md。继续生产 SQL、Neo4j/迁移、多平台、实际 Docker/CI 和3D。

最新 V2.21：8.5 音频协议已验收，33/38（87%），继续全部剩余计划，goal 保持 active。后端 758（42.34s，严格线程警告）、Web 81、双端构建通过。实际 O2 新旧协议、打断后下一轮与浏览器文件合成麦克风的 VAD/25 上行帧/6 下行帧/6 次播放/挂断清理通过；没有读取真实麦克风。详见 backend/docs/audio-transport.md、packages/audio-transport/README.md。保留协商后开麦、旧 ready 回退、双向序号、段归属、取消后发送完成、致命错误清理与串行重拨。访问中间件必须选择公开子协议名，不回显凭据。离线 Protobuf 编码评估没有引入运行时依赖，不宣称端到端提速。干净 wheel 新协议/宿主/目录调用通过；架构扫描排除生成 build/dist，反向编排/SDK 为零，历史横向/角色文本差异仍未清零。QA 8044/5197 与浏览器已关闭。剩余五项：2.1 生产 SQL、2.3 Neo4j/迁移、6.2 多平台、6.3 Docker/CI、8.6 3D；额外兼容层物理清理和 ASR Protocol 注入也保留。

最新 V2.20：6.4 设置与管理已验收，32/38（84%），持续全部剩余计划，goal 保持 active。后端 750（44.58s，严格线程警告）、Web 75、双端构建通过。真实隔离浏览器验证分类/角色、模型保存/方舟连接、语音保存/TTS、陪伴刷新保留、内置扩展安装停用和普通账号/390px；宿主授权后真实方舟任务调用文本工具。干净来源 wheel 独立宿主/目录安装/授权调用通过。详见 apps/backend/docs/administration.md；保留安装默认关闭、固定打包目录/摘要、禁止覆盖/链接/预授权冲突、宿主单独授权、取消后磁盘 worker 完成。旧 build 缓存不作为分发来源，未递归删除。跨模块事项测试已移至 core_orchestrator/tests/test_user_state.py，统一 async 生命周期。继续 8.5 协议评估/升级、生产存储、多平台、部署与 3D；旧检查点为历史。

V2.19（2026-10-20）：仍 31/38（82%），持续全部剩余计划。后端 745、桌面工具 16、Web 67、PC 打包代理与双端构建通过，双端依赖审计零已知漏洞。真实 Windows 解包程序验证自有来源、隔离资料、Python 桥、方舟聊天与本地 VAD WASM。6.3 仍保留 Docker/远端 CI、签名安装器与跨系统验收，继续管理面板、生产存储、多平台、协议和 3D。

V2.15（2026-10-20）：6.1 本地插件目录发现/热重载验收，默认禁用、宿主授权、资源清理与撤销边界已实现；真实方舟任务接口验证新旧代码切换。26/38（68%），继续全部剩余计划。后端完整 666 passed，Web 53、Web/PC 构建通过。

V2.14（2026-10-20）：5.3/8.4 已验收，独立 avatar_runtime/TS 时钟、实际 RMS 口型、表情/轻动作与取消重播落地。真实浏览器及原生 O2 时间轴通过，修复缺少句子文字时没有宣布音频的问题。25/38（66%），继续全部其余工作；后端 656 / Web 53 测试通过，Web/PC 构建通过。生产数据库、原生通知、外部账号与 3D 联调仍保留。

V2.13（2026-10-20）：用户要求持续至全部计划完成。5.2 图片理解已通过普通/SSE、实际方舟和浏览器纯图片发送验证；图片有大小/像素限制、移除元数据、不保存原件、不执行工具、不提取图片用户事实。累计 23/38 项（61%），继续 5.3/8.4。最新完整后端 646 passed、Web 46 passed、Web/PC 构建通过，另有新增 SQL 图片记录回归。

当前执行与逐项验收以 [DEVELOPMENT_EXECUTION.md](DEVELOPMENT_EXECUTION.md) 为准。用户已明确“继续开发吧”，恢复推进剩余适用计划。全部未验收计划保留，下文旧状态快照作为历史记录。

V2.12：5.1 已完成文字→原生通话→文字的真实连续性验证，累计 22/38 项（约 58%）。人格、关系、记忆由宿主注入；原生回合完整后写回 SQL，反应按真实用户转写更新；补齐清空后的旧 SQL 写入失效。下一项为 5.2 图片理解。下方暂停状态及旧完成数仅为历史记录。

V2.11：已验收 8.1/8.2，累计 21/38 项（约 55%）。主聊天支持分段语音与顺序播放/重听；实时语音支持有界预合成、打断清理、自适应播放缓冲和迟到音频丢弃。20 组固定文本真实语音对比全部成功，首音中位时间 6.703 秒降至 4.234 秒（36.8%）；豆包 ASR 回识别、原生实时打断及下一轮恢复通过。后端 603 项、Web 42 项回归通过，Web/PC 构建通过。5.1 完整实时人格链路、8.4 音频/表情聚合与图片理解等仍未验收，当前暂停开发。

V2.10 历史记录：已验收 4.1–4.3，累计 19/38 项（50%）。四角色共享普通/SSE 委派，同用户同会话按序执行；MCP 使用官方 stdio/HTTP 协议；任务持久化实际步骤，可补充续办、取消并防止未知操作重放。真实方舟两步任务与浏览器流程通过；后端 573 项、Web 29 项回归通过，Web/PC 构建通过。

V2.7：记忆淡化/恢复、融合检索、规则评分、空闲日总结与跨会话回顾已实现；真实方舟压缩/总结、浏览器流程及 407 项后端回归已通过。生产数据库与 Neo4j 实测、离线关系指标复核仍待完成，下一波次继续情绪与关系深化。

V2.8：情绪改为 SQL 持久化的连续二维状态；独立反应分类在生成前决定回复节奏，完成后与关系指标原子提交。日关系复核可补记遗漏事务，且不会重复累计已记分对话或旧档案。真实模型、后端重启与浏览器刷新均已验证。后端 433 项回归通过，当前完整验收 14/38 项（37%），下一步继续 3.4 自然发言，再进入工具编排与多模态；生产数据库/Neo4j 等未验收项继续保留。

V2.9：自然发言可按用户配置，安静处理有明确接收状态并保留活动/对话/关系；语音、确认、任务等场景仍正常回应。路由加入当前请求权重、少样本示例与超时/校验回退，45 条用例经规则和真实模型组合验证；自然语言取消提醒已能解析目标并隔离用户。累计验收 16/38 项（42%），下一步继续 4.1–4.3；所有未完成计划保持有效。

---

## 0. 项目定位：内部技术原型 · 模块化通用能力库

### 两条核心定位

1. **当前工程是内部提前做的技术原型 Demo**，不绑定任何具体商业项目，不与任何商务报价挂钩。
2. **最终目标是所有模块都可以独立拆开接入任意第三方数字生命项目**，包括但不限于"小汐"项目。

```
companion-ai（本仓库）= 通用陪伴 AI 模块库 + 一个参考集成 demo
  ├── 通用模块（每个都要可独立拆出去）
  │   ├── persona_engine        — 人格/情绪/关系/语气
  │   ├── memory_system         — 工作记忆/向量/图谱/沉淀
  │   ├── voice_layer           — 实时 ASR/TTS/VAD/打断
  │   ├── action_executor       — 插件式动作 + 主动推送
  │   ├── safety_guard (待建)    — OOC / 安全边界
  │   ├── user_profile (待建)    — 结构化用户画像
  │   ├── onboarding (待建)      — 0-1 破冰流程
  │   ├── gateway_adapter       — 多平台 / 多宿主接入适配
  │   └── device_coordination   — 跨设备协同
  ├── 契约层
  │   └── shared_contracts (待建) — 纯模型 + 事件类型，零依赖
  ├── 运行时层（宿主可注入或替换）
  │   └── shared_runtime (待建)  — LLMClient / 配置 / 日志
  └── 参考集成 demo
      ├── core_orchestrator     — 一种 LangGraph 编排实现（不是模块本体）
      └── apps/web              — 一种 Web 调试台 + Live2D 渲染示例（仓库内路径）
```

### 关键决策

- **不存在"必交付清单"**：本工程对任何具体项目都不承担交付承诺。任何模块的"完成度"以**对外契约稳定 + 可独立运行 + 可独立集成**为衡量标准，而不是"对账某份功能清单"。
- **`core_orchestrator` 是参考实现，不是模块本体**：第三方接入不应被迫使用我们的编排器。模块通过契约对外开放，宿主用自己的编排去组合。
- **`apps/web` + Live2D 是"参考 UI / 验收 demo"**：演示"模块对接得多容易"。第三方可换 Unity / Unreal / Web Three.js / 桌面 / 车机 / MR，本仓库不锁渲染端。
- **去商业化口径**：本计划之前所有"小汐 ¥XX万 / 报价表 / 子集 / 灵魂工程必交付"措辞全部废弃。

---

## 1. 当前判断

工程已经具备完整的"陪伴 AI demo"形态（FastAPI 单体 + LangGraph 编排 + 实时语音 + 记忆双层 + 行动执行器 + Live2D 前端），但**模块的"独立可拆性"远低于代码分包给人的直觉**。要走到"任意第三方都能拆装"，最大的三道墙是：

1. **`shared/` 是隐性强耦合中心**：基础设施（日志/配置）与业务级东西（LLMClient / prompt_engine）混在一起。任何模块拆出去都要把 `shared/` 整体拖走。
2. **反向依赖未隔离**：`action_executor` 等模块在文档/状态里声明依赖 `core_orchestrator`，导致拆模块=拖编排器。
3. **协议契约只在文档里，没在代码里**：`ARCHITECTURE.md §4` 列出的 Pub/Sub channel 与 HTTP API 几乎全是 monolithic 进程内函数调用，对外不存在稳定 schema。

之前提的"OOC / ≤30维画像 / 0-1破冰"三项缺口，从"必交付项"降级为"通用能力示例 + 可替换实现"——它们是好东西，但**不再是阻塞当前阶段的关键路径**。

---

## 2. 2026-05-07 状态快照 (V2.3 人格连续性闭环交付)

| 领域 | 状态 | 模块独立可拆性 | 说明 |
|---|---|---|---|
| 单体入口 | ✅ 已完成 | — | `uvicorn main:app --reload --port 8000` 是默认入口 |
| 前端 Web App | ✅ 已完成 | 🟡 中 | 既是 demo UI 又含 Live2D 渲染 |
| 实时语音 | ✅ 已完成 | 🟢 较高 | DashScope SDK 已封装至 providers/，check_arch 直连SDK=0 |
| 人格引擎 | ✅ 已完成 | 🟢 高 | V2.3 runtime.py 单例 + 多角色 + emotion/relationship 持久化 |
| 记忆系统 | 🟡 进行中 | 🟡 中 | working memory 与 prompt_engine 耦合待解 |
| 对话引擎 | ✅ 已完成 | 🔴 参考实现 | LangGraph 编排 + 流式 SSE + 调试台 |
| 行动执行器 | 🟡 进行中 | 🟡 中 | 5 个 handler，主动性模块待状态闭环稳定后扩展 |
| 新用户引导 | 🟢 已打通 | 🟢 高 | /onboarding/* 端点 + OnboardingFlow + user_profile 联动 |
| 用户画像 | 🟢 已打通 | 🟢 高 | SQLiteUserProfileStore + role_id 偏好写入 |
| 安全护栏 | 🟡 骨架 | 🟡 中 | BLOCK/WARN 分级 + PII 正则，已接入输入/输出 |
| 调试台 | 🟢 已完善 | 🟢 高 | /debug/state 完整人格快照 + /personas + /prompt_preview |
| 协议契约 | 🟢 已完成 | 🟢 高 | shared_contracts 已物理化 |

---

## 3. V2.3 已完成交付

### 目标 A：人格连续性闭环 ✅

每轮对话真实更新并影响下一轮的状态链路：

- `persona_engine/runtime.py` — 进程级 EmotionEngine + RelationshipTracker 单例
- `_recall_memory_monolithic` 从 emotion_engine / relationship_tracker 读持久化状态（不再每轮重置）
- `node_sync_memory` 写回 emotion_state + relationship_metrics + user_profile 更新

完成标准：
- 同一个用户连续聊 10 轮后，关系指标持续增长、情绪随对话浮动、回复风格受人/情绪/关系/记忆共同影响
- 141 tests pass，check_arch [ok]

### 目标 B：架构 P0 收口 ✅

- 单角色硬编码 37→24（production code 全清，state_machine/handlers/onboarding/prompt_engine/realtime 全部去"小暖"）
- voice_layer DashScope SDK 迁移至 providers/dashscope.py 封装层 → check_arch 直连SDK=0
- check_arch.py 增加 providers/ 目录 SDK 检查豁免规则

### 目标 C：onboarding → user_profile → persona 链路 ✅

- `/orchestrator/onboarding/start | answer | status` 端点
- `OnboardingFlow` 动态读 `persona_store.list_available_personas()`
- `apply_to_profile` → `SQLiteUserProfileStore`
- `_recall_memory_monolithic` 按 `user_profile.preferences.role_id` 加载对应 persona

### 目标 D：调试台 ✅

- `/orchestrator/debug/state` — 完整人格状态快照（system_prompt + emotion_state + relationship_metrics + working_memory + user_profile）
- `/orchestrator/personas` — 可用角色列表
- `/orchestrator/debug/prompt_preview` 增加 intent 字段

---

## 4. 通用化能力（旧 OOC / 画像 / 破冰，重定位为示例）

不再作为本阶段阻塞，但应作为"通用能力示范模块"在 P0 骨架完成后并行推进：

- `safety_guard/`（旧 OOC）：独立模块，规则集**外部可注入**，不锁死任何角色风格
- `user_profile/`（旧 ≤30维画像）：画像 schema 可配置，预置一套通用维度，**不再锁定 30 维**
- `onboarding/`（旧 0-1 破冰）：破冰流程引擎 + 一份默认脚本，第三方可替换

它们各自就是"模块独立可拆"的标杆样例。

---

## 5. 非本阶段重点

- 本地模型部署 / LoRA 微调
- 任何与具体商业项目（含小汐）报价 / 子集 / 必交付清单 相关的对账工作
- Unity / Unreal / 桌面 / 车机 / MR 等具体宿主端的工程化集成
  - 它们都是"未来可能的宿主"，不是"我们要交付的端"
  - 本仓库只保证模块对宿主友好（API/事件/SDK），不替宿主写代码

---

## 6. 验证与基线

### 建议命令

```powershell
cd apps/backend
python -m pytest -q
uvicorn main:app --reload --port 8000

cd ../web
npm run build
```

### 当前已知测试结果

2026-05-07 (V2.3 人格连续性闭环交付)：

- `python -m pytest -q --ignore=voice_layer/tests/test_voice.py --ignore=memory_system/tests/test_memory.py`
  - **141 passed / 0 failed**
- `python tools/check_arch.py --check` — [ok] 与 baseline 对比无新增违规
- 架构基线: 反向依赖=0, 直连SDK=0, 横向耦合=1 (action_layer→action_executor deprecated), 硬编码=25 (doc+test)

### 新增基线门槛（随 P0 落地后启用）

- 模块依赖图：业务模块 → `shared_contracts/` 单向（自动校验）
- 契约测试：每个模块 `openapi.yaml` 与实际接口一致
- `examples/integration_minimal/` smoke test 在 CI 中绿

---

## 7. 执行顺序建议

**P0 — 可拆性骨架（已完成 ✅）**
1. ✅ 拆 `shared/` → `shared_contracts/` + `shared_runtime/`
2. ✅ 反向依赖清理 + importlinter 契约 + PersonaRegistry 多角色
3. ✅ P0 收口：去单角色硬编码 + DashScope SDK 解耦
4. ✅ 9 模块 README + examples + integration_minimal

**P1 — 人格连续性闭环（本次交付 ✅）**
5. ✅ `persona_engine/runtime.py` — 进程级 EmotionEngine + RelationshipTracker
6. ✅ `_recall_memory_monolithic` 读持久化 emotion/relationship 状态
7. ✅ `node_sync_memory` 写回 emotion + relationship + user_profile 更新
8. ✅ onboarding → user_profile → persona role_id 主链路
9. ✅ 调试台 /debug/state + /personas + /onboarding/*

**P2 — 主动性 & 物理清理（下一波次）**
10. ✅ 主动性模块：到点提醒 / 长期未互动问候 / 记忆触发纪念日（见执行表验收范围）
11. ✅ V2.22：旧 shared/action_layer shim 已归档并从源码和 wheel 移除
12. ✅ V2.22：高层 SpeechRecognizer 与每 app ASR 工厂注入，默认适配器保留配置选择
13. ✅ working memory LLM 摘要器（真实压缩验证见执行表）

---

## 8. 宿主无关：集成路径全景

```
通用模块（本仓库）
  persona_engine / memory_system / voice_layer /
  action_executor / safety_guard / user_profile /
  onboarding / gateway_adapter / device_coordination
       │         │         │
       │ HTTP / SSE / WS / Pub-Sub（基于 shared_contracts）
       ▼         ▼         ▼
  ┌──────────────────────────────────────────────┐
  │          任意宿主（hosts，对模块透明）         │
  │                                              │
  │  · 我们的参考 demo（core_orchestrator + Web）│
  │  · Unity / Unreal 客户端                     │
  │  · 桌面陪伴 / 车机 / MR (Vision Pro)         │
  │  · 第三方 IM / 微信生态                      │
  │  · 第三方数字人 / 数字生命平台（含小汐）       │
  └──────────────────────────────────────────────┘
```

本仓库**不**为任一宿主做工程化交付；只保证模块对外契约稳定、文档齐全、示例可跑。

---

## 9. 交接约定

后续只要代码真实状态发生变化，至少同步这三处：

1. `apps/backend/core_orchestrator/project_status.py`
2. `AI_HANDOFF.md`
3. 本文件 `PROJECT_PLAN.md`

其中：

- 页面可视化以 `project_status.py` 为直接数据源
- `AI_HANDOFF.md` 用于快速接手
- `PROJECT_PLAN.md` 表达接下来要做什么（口径：模块化原型 / 宿主无关）

这三者必须保持同口径，不得再混入"商务报价 / 必交付清单 / 子集对账"措辞。
