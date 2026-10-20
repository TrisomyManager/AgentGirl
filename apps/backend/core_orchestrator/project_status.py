"""Project development status tracking and API."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


class ModuleStatus(str, Enum):
    """Module development status."""
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    PLANNED = "planned"
    BLOCKED = "blocked"


class TechStack(BaseModel):
    """Technology stack for a module."""
    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    databases: List[str] = Field(default_factory=list)
    apis: List[str] = Field(default_factory=list)


class ModuleInfo(BaseModel):
    """Single module development info."""
    id: str
    name: str
    name_zh: str
    description: str
    status: ModuleStatus
    progress: int = Field(..., ge=0, le=100, description="Completion percentage")
    tech_stack: TechStack
    key_features: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    last_updated: str = ""


class MilestoneInfo(BaseModel):
    """Cross-module milestone snapshot for the current release."""

    title: str
    owner: str
    status: str
    detail: str


class TestSnapshot(BaseModel):
    """Verification snapshot shown in handoff docs and UI."""

    command: str
    passed: int
    failed: int
    skipped: int = 0
    notes: List[str] = Field(default_factory=list)


class FocusItem(BaseModel):
    """A single current focus or risk item."""

    title: str
    detail: str


class ReleaseNoteItem(BaseModel):
    """A single user-visible deliverable in the active release."""

    category: str = Field(
        ..., description="One of: feature, fix, docs, chore, infra"
    )
    title: str
    detail: str
    impact: str = Field(default="", description="Why this matters in human terms")
    refs: List[str] = Field(
        default_factory=list,
        description="Optional code paths / endpoints / files this change touches",
    )


class ReleaseSection(BaseModel):
    """The 本轮交付 card: what this branch / PR delivers right now."""

    title: str
    pr_branch: str = ""
    summary: str = ""
    items: List[ReleaseNoteItem] = Field(default_factory=list)


class ProjectStatusData(BaseModel):
    """Complete project status data."""
    project_name: str
    version: str
    current_phase: str
    summary: str
    last_updated: str
    overall_progress: int
    recent_highlights: List[str]
    next_focus: List[FocusItem]
    risks: List[FocusItem]
    milestones: List[MilestoneInfo]
    test_snapshot: TestSnapshot
    modules: List[ModuleInfo]
    architecture_layers: Dict[str, List[str]]
    release_notes: ReleaseSection = Field(
        default_factory=lambda: ReleaseSection(title=""),
        description="Section that lists what the active branch is delivering.",
    )


def get_project_status() -> ProjectStatusData:
    """Return current project development status."""
    return ProjectStatusData(
        project_name="Companion AI（通用陪伴 AI 模块库 · 内部技术原型）",
        version="0.2.0 · V2.26 多平台收发与绑定",
        current_phase="平台实现待账号验收 · 继续部署，3D待确认",
        summary=(
            "2026-10-20：用户要求持续至全部计划完成。5.2 图片与 5.3/8.4 表情音频同步已真实验证，继续插件与生态。主动陪伴设置、用户独立评估、原子提醒与持久化补收已接通；"
            "对话存档、批次摘要、可恢复遗忘、实体图谱融合检索和日回顾已落地；真实方舟摘要和压缩已验证。"
            "连续情绪、SQL 持久化、独立反应分类、回复行为与离线关系复核已验证。Web 与 PC 均可构建。"
            "自然发言已按用户配置，45 条路由回归经规则和真实模型组合验证。"
            "分工委派、会话排队、官方 MCP 与持久多步任务已验证。"
            "8.1/8.2 分段语音、有序播放、打断与有界自适应缓冲已通过真实语音验证。"
            "本地插件目录发现、宿主授权和热重载已通过真实任务验证。"
            "默认参考宿主的账号隔离、撤销活动流、导出/删除与待重试清理已通过真实验证。"
            "普通/SSE/任务/TTS 发出前规则检查与原生无文字音频暂存、用户 SQL 记忆网络及原文依据已验证。"
            "桌面内置工具的私有桥/能力与文件范围、逐次确认、原子命令状态和 Windows 原生通知已实际验证。"
            "当前按路线图 38 项中验收 35 项计为 92%，整体计划尚未完成；多平台真实账号验收暂缓，实际容器/CI继续；3D由用户暂缓，待讨论确认。"
            "以下为既有工程的历史能力说明："
            "内部技术原型 Demo，目标是让所有模块都可以独立拆开接入任意第三方数字生命项目。"
            "demo 形态完整：FastAPI 单体 + LangGraph 编排 + 实时语音 + 记忆双层 + 行动执行器 + Live2D 前端。"
            "V2.3 人格连续性闭环：每轮对话真实更新 emotion_state / relationship_metrics / user_profile / working_memory / long-term memory，下一轮对话真实受影响；"
            "onboarding → user_profile → persona role_id 主链路打通；调试台 /debug/state 可诊断完整人格状态。"
            "本迭代 V2.4 围绕「让 demo 在外网可稳定演示」收口：LLM 配置路径稳定化、保存设置时不丢 API key、DashScope/兼容 4xx 错误信息更人话、"
            "OpenAI/Anthropic 自动补 /v1 base URL、Vite dev server 放通 Cloudflare 隧道 Host、companion-ai 包及服务版本对齐 0.2.0、新增 .env.lite 忽略避免本地覆盖泄漏。"
            "check_arch 反向依赖=0 / 直连SDK=0 / 横向耦合=1（action_layer→action_executor 兼容 shim）/ hardcoded_persona=59（绝大多数集中在 voice_layer/tests/test_resolver.py 与 voice_layer/resolver.py 的预设别名，已记入 baseline）。"
        ),
        last_updated="2026-10-20",
        overall_progress=92,
        recent_highlights=[
            "V2.26：三平台收发/绑定/持久回执/隐私联动与本地实际SDK通过；真实账号验收暂缓，3D待用户确认。",
            "V2.25：35/38；图来源、单删/淡化/恢复、持续清理和服务器防重放通过实际数据库/方舟/安装包验证。",
            "V2.24：仍34/38；实际Neo4j审阅迁移/隔离、整库清理补偿与重启恢复通过；继续单条记忆图来源解绑。",
            "V2.23：34/38；真实生产SQL宿主/重启/隔离/导出删除、无损迁移和实际方舟向量/压缩/跨会话回忆通过。",
            "V2.22：仍33/38；旧兼容包移出源码/wheel，记忆端口和每app ASR工厂通过真实隔离验证，6个导入契约通过。",
            "V2.21：8.5 音频帧验收，33/38；真实 O2 新旧协议/打断恢复，浏览器合成麦克风经 VAD/帧协议/实际播放与挂断清理通过。",
            "V2.20：6.4 管理面板验收，32/38；真实浏览器配置保存/Ark/TTS/陪伴刷新/内置扩展安装/成员权限/390px 与宿主授权后方舟工具调用通过。",
            "V2.19：双端依赖审计零已知漏洞；实际 Windows 解包程序的自有来源/Python 桥/方舟聊天/本地 VAD 通过，仍 31/38。",
            "V2.18：7.1/5.4 验收；实际隔离 Electron/Python/文件/SQL、确认期间取消、Windows show、提醒 SSE 与刷新去重通过。",
            "V2.17：7.2/6.5 验收；真实预防讨论、6 段检查后 TTS、O2 连续性与浏览器图谱依据/筛选/删除后刷新/390px 通过。",
            "V2.16：按用户的身份/资源控制、可撤销会话、导出/删除、旧工作写入屏障及持久清理 receipt；真实接口与浏览器通过。",
            "V2.15：默认禁用的插件目录发现、用户/修改授权、摘要热重载、资源同任务清理与撤销；真实方舟任务接口通过。",
            "V2.14：独立 avatar_runtime、音频播放时钟/RMS 口型与表情轻动作；实际停止、7 段刷新重播和 O2 时间轴通过。",
            "V2.14：修复原生 O2 无句子文字时遗漏音频开始通知；默认 1.2.1.1 实测 497448 字节音频，连续性仍通过。",
            "V2.13：有界图片上传、元数据清理与普通/SSE 生成；实际方舟识别、浏览器纯图片发送、刷新收据与窄屏通过。",
            "V2.12：宿主注入语音人格/记忆/关系，原生完整回合持久化及反应提交；真实文字→通话→文字连续性验证通过。",
            "V2.12：同会话语音写回排序、身份切换保护；清空后的旧 SQL 提取/向量写入失效；保留 SQLite 取消清理并扩展到查询和关闭。",
            "V2.11：SSE 协商分段语音，有界预合成和按序播放/重听；分段失败保留文字，断流等待子任务清理。",
            "V2.11：原生豆包打断后丢弃旧帧，前端拒绝迟到解码、拼接半采样并限制队列；真实打断及下一轮恢复通过。",
            "V2.11 历史：20 组固定文本真实语音对比全部成功，首段事件中位 6.703s → 4.234s（36.8%）。",
            "V2.10：四角色共享普通/SSE 委派；同用户同会话顺序执行，独立会话可并行；记忆工具回复在两条路径一致。",
            "V2.10：官方 MCP stdio/HTTP 协议、JSON Schema 校验与宿主身份绑定；外部服务按明确用户配置，密钥配置保持忽略。",
            "V2.10：任务步骤持久化、补充续办/停止、边界与去重；重启/未知结果不自动重放。真实方舟与浏览器两步任务通过。",
            "V2.9：自然发言默认关闭，可按用户配置概率；安静处理仍保存对话/活动/关系，界面显示已收到，问题/任务/语音与确认上下文继续回应。",
            "V2.9：45 条意图用例经本地规则与方舟组合管线验证；当前请求权重、少样本示例和有限超时防止历史词/否定句误触执行。",
            "V2.9：自然语言取消提醒能匹配当前用户的实际待办；歧义会请求选择，明确所有才批量取消。",
            "V2.8：连续 valence/arousal、确定性平复与 SQL 情绪持久化；按用户/轮次原子提交情绪和关系，重试不重复增长。",
            "V2.8：独立模型在回复前分类，失败回退到规则；情绪影响生成参数，任务/严肃语境优先抑制 emoji。",
            "V2.8：日关系复核补偿新版档案中的漏记事务，旧档案不重复计分；真实模型、重启和浏览器刷新验证通过。",
            "V2.7：访问频率与时间共同决定记忆清晰度；淡化保留原文，明确检索或手动恢复可重新激活。",
            "V2.7：用户隔离的实体关系索引、PageRank 扩散与向量排序融合；实体提取只保留用户陈述支持的事实。",
            "V2.7：凌晨空闲时整理最近 7 天；每日指纹与数据库租约去重，偏好变化只基于用户原话，旧总结不能覆盖更新偏好。",
            "V2.7：真实方舟压缩和日总结通过，跨会话可读取回顾；清空使旧后台写入失效。Lite 使用 WAL 支持并发读写。",
            "2026-10-19：主动陪伴按用户保存开关、时区、免打扰、冷却与日上限；独立任务避免慢用户阻塞其他用户。",
            "2026-10-19：提醒状态与推送 outbox 原子提交；离线分页补收、SSE/轮询去重、循环提醒按发生次数去重。",
            "2026-10-19：Lite 对话历史与窗口外摘要持久化；模型摘要失败保留摘录；清空后历史和摘要一并删除。",
            "2026-10-19：PC 类型检查与共享静态资源构建恢复；前端后台推送已接桌面通知桥；原生通知尚待打包实测。",
            "🆕 V2.4 LLM 配置稳定性：保存 /settings/llm 时若未填 api_key 则保留旧值（539b65c）；config 读写路径统一不再因 cwd 漂移（9093b4b）；OpenAI/Anthropic base_url 缺 /v1 时自动补齐。",
            "🆕 V2.4 错误可读性：DashScope 配额耗尽 / 4xx 错误体直接转写成中文提示，前端不再只看到 'HTTP 400'（80a58b0）。",
            "🆕 V2.4 演示链路：Vite dev server 放通 Cloudflare 隧道 Host（deabf2e），可直接通过 trycloudflare.com 隧道把本地 demo 暴露给评审；新增 .env.lite 忽略避免本地 Lite Mode 覆盖被误提交（52d3ed0）。",
            "🆕 V2.4 版本对齐：companion-ai 包及各服务版本统一为 0.2.0（617ecb0），消除 main.py / pyproject 之间版本号不一致。",
            "🆕 V2.3 人格连续性闭环：_recall_memory_monolithic 读持久化 emotion/relationship 状态（非回合重置）；node_sync_memory 写回 emotion + relationship + user_profile 更新（含名字/偏好发现）；persona_engine/runtime.py 提供进程级 EmotionEngine/RelationshipTracker 单例。",
            "🆕 V2.3 架构 P0 收口：单角色硬编码大幅下降（state_machine / handlers / onboarding / prompt_engine / realtime production code 全部去硬编码）；voice_layer DashScope SDK 迁移至 providers/dashscope.py 封装层；check_arch 直连 SDK = 0；当前 hardcoded_persona baseline = 59（集中在 voice_layer/resolver.py 别名表与少量 tests）。",
            "🆕 V2.3 调试台升级：新增 /orchestrator/debug/state（system_prompt + emotion_state + relationship_metrics + working_memory + user_profile）；新增 /orchestrator/personas（可用角色列表）；新增 /orchestrator/onboarding/{start,answer,status} 引导流程端点。",
            "✅ P2 落地：action_layer 物理合并入 action_executor.action2d/（generator_2d / lip_sync / router / sequencer / api / main 全部物理位于新包）；action_layer/ 整体转 deprecated re-export shim；main.py 主链路改用 action_executor.action2d。",
            "✅ P1-E 落地：shared_runtime/{llm_client,database,voice_runtime_config} 物理搬迁完成；shared/{llm_client,database,voice_runtime_config} 反向变 deprecated re-export shim；全仓 59 个文件 88+ 处 `from shared.X` 改向 `from shared_runtime.X` / `from shared_contracts.X`。",
            "✅ P1-D 落地：shared_runtime/{config,lite_mode}.py 物理搬迁完成；shared/{config,lite_mode}.py 反向变 deprecated re-export shim；shared/llm_client.py 与 shared/database/ 内部 `from shared.config` 改向 `from shared_runtime.config` 以打破循环导入。",
            "✅ P1-C 落地：shared_contracts/{models,events}.py 物理搬迁完成（19 模型 + 13 事件 + 3 Protocol 全部物理位于新包）；shared/{models,events} 反向变 deprecated re-export shim。",
            "✅ P1-B 落地：safety_guard 升级（BLOCK/WARN 分级 + PII 正则 + 兜底文案）+ user_profile 接 SQLite + onboarding 增 OnboardingFlow 状态机；core_orchestrator 主链路已接入输入/输出双向安全检查与 user_profile.role_id 偏好读取。",
            "✅ P1-A 落地：9 个模块 README + 9 个 `python -m <module>` 入口 + examples/integration_minimal/ 端到端 demo 跑通。",
            "✅ 波次 0-6 全部落地：契约/运行时分层 + 反向依赖清零 + 多角色 + 三个待建模块骨架。",
            "🏗️ 项目重新定位：内部技术原型 + 模块化通用能力库；不绑定任何具体商业项目，不与任何报价挂钩。",
            "🎯 最终目标确立：每个模块都能独立拆开接入任意第三方数字生命项目（Unity / Unreal / Web / 桌面 / 第三方平台）均为合法宿主。",
            "🎨 Live2D 重新定位：仅作为渲染前端示例之一，不再以「降级兜底方案」为身份。",
            "单体入口 `main.py` 已成为默认开发路径，Lite Mode 可直接启动完整 Web API。",
            "实时语音链路已打通：浏览器 VAD、AudioWorklet 录音、WebSocket 双向流和边合成边播放。",
            "LLM / Voice Provider 已支持运行时切换与配置持久化，无需改代码即可调参。",
            "前端已具备聊天、记忆库、语音通话、状态面板四个核心调试入口。",
            "🆕 主聊天流式输出已打通：`POST /orchestrator/turn/stream` 走 SSE，前端逐 token 渲染并保留 emotion / voice_url 元数据。",
            "🆕 记忆双层模型已落地：working memory 滚动 N 轮 + 结构化用户摘要，注入到 system prompt 的【当前对话状态】/【最近几轮对话】section。",
            "🆕 行动执行器初始闭环已打通：5 个内置 handler、自然语言提醒、SQLite 持久化、Open-Meteo 天气、固定间隔重复提醒、前端 ReminderToast 通过 /actions/push SSE 接收。",
            "🆕 编排调试：`POST /orchestrator/debug/prompt_preview` 可在不发 LLM 的情况下拼装与主路径一致的 conversation system prompt（含意图分类 + 记忆召回）。",
            "🆕 working memory 可选 LLM：一次 JSON 补全精炼主题 + 一句会话摘要；TTL 按 transcript 指纹去重，减少 recall 连打。",
        ],
        next_focus=[
            FocusItem(
                title="继续实际部署与远端CI",
                detail="已验收35/38；继续实际容器与远端CI。多平台真实账号验收按用户要求暂缓，3D先讨论确认后开发。",
            ),
            FocusItem(
                title="记忆增强与数据连续性",
                detail="批次摘要、跨会话回顾、遗忘/恢复、融合检索与日总结已验证；生产SQL实测已验收，多平台身份绑定/收发已实现，真实账号待配置；继续部署，3D待确认。",
            ),
            FocusItem(
                title="语音、多模态与同步呈现",
                detail="语音、图片和音频/表情同步均已验收；3D遵用户要求暂缓，技术方案讨论确认后再实施。",
            ),
            FocusItem(
                title="模块边界与工程化",
                detail="反向编排依赖已清零；旧兼容层与动作模块横向依赖已清理，记忆与ASR已宿主注入；继续生产存储、平台与形象服务。",
            ),
        ],
        risks=[
            FocusItem(
                title="平台与部署仍待实际联调",
                detail="Lite与实时语音人格/关系已验证；生产SQL/Neo4j与图来源清理已验收；多平台真实账号、Docker/远端CI和3D仍待完成。",
            ),
            FocusItem(
                title="TTS HTTP 注入与宿主范围",
                detail="ASR 高层工厂按 app 注入并验证关闭；TTS HTTP 仍是参考宿主单例，尚未实现同样的多 app 隔离。",
            ),
            FocusItem(
                title="文档与代码的旧商业化口径需持续巡检",
                detail="历史文档曾以「小汐子集 / ¥XX万报价 / 必交付清单」为口径表述；2026-05-07 已统一切换，仍需在新增文档时持续巡检。",
            ),
        ],
        milestones=[
            MilestoneInfo(
                title="单体入口与 Lite Mode",
                owner="平台基线",
                status="done",
                detail="本地开发默认走 `uvicorn main:app --reload --port 8000`，并保留微服务模式作为后续拆分边界。",
            ),
            MilestoneInfo(
                title="实时语音通话",
                owner="voice_layer + frontend_app",
                status="done",
                detail="浏览器端已支持 VAD、PCM 采集、打断和链式 TTS 播放，是当前最成熟的用户体验模块。",
            ),
            MilestoneInfo(
                title="参考集成 demo（core_orchestrator + Web）形态完整",
                owner="core_orchestrator + frontend_app",
                status="done",
                detail="LangGraph 编排 + 流式 SSE + prompt_preview + 多 Provider + Live2D 渲染示例，作为「模块对接得多容易」的样板。",
            ),
            MilestoneInfo(
                title="波次 0 · 安全网与依赖图基线",
                owner="工具链",
                status="done",
                detail=".importlinter（4 条契约对齐 ADR-006）+ tools/check_arch.py（零依赖 stdlib AST 扫描）+ tools/arch_baseline.json 已就位。",
            ),
            MilestoneInfo(
                title="波次 1 · shared_contracts/ 抽离",
                owner="shared_contracts",
                status="done",
                detail="新增 shared_contracts/{models,events,protocols}.py；通过 re-export 不破坏现有 import；133 passed 维持。",
            ),
            MilestoneInfo(
                title="波次 2 · shared_runtime/ 抽离 + LLMClient Protocol",
                owner="shared_runtime",
                status="done",
                detail="re-export Settings / LLMClient / get_runtime_voice_config / 数据库生命周期 + 新增 is_lite_mode；133 passed 维持。",
            ),
            MilestoneInfo(
                title="波次 3 · 反向依赖清零",
                owner="全模块",
                status="done",
                detail="V2.22：6个导入契约通过，反向/SDK/横向导入均为0；角色文本仍有基线差异，未宣称AST全绿。",
            ),
            MilestoneInfo(
                title="波次 4 · PersonaRegistry 多角色化",
                owner="persona_engine",
                status="done",
                detail="data/personas/{default,xiaonuan,aria}.yaml 三套示例；list_available_personas() / get_persona_profile(role_id=...) 可按角色加载；默认 role_id='default' 仍为「小暖」。",
            ),
            MilestoneInfo(
                title="波次 5 · action_layer deprecated shim",
                owner="action_layer",
                status="done",
                detail="action_layer/__init__.py 注入 DeprecationWarning，标注未来合并入 action_executor；运行时行为不变。",
            ),
            MilestoneInfo(
                title="波次 6 · 待建模块骨架",
                owner="safety_guard / user_profile / onboarding",
                status="done",
                detail="三个独立包就位：safety_guard（关键词护栏 + Verdict）、user_profile（Snapshot + Store Protocol + InMemory 实现）、onboarding（OnboardingStep + default_steps）。",
            ),
            MilestoneInfo(
                title="P1-A · 9 模块 README + examples/integration_minimal/",
                owner="全模块",
                status="done",
                detail="9 个模块均已补 README + __main__.py（python -m 单独可启）；examples/integration_minimal/run.py 跑通端到端 6 模块组合 demo（onboarding → user_profile → persona_engine → safety_guard），全程零 LLM / 零网络 / 零 DB。",
            ),
            MilestoneInfo(
                title="P1-B · safety_guard / user_profile / onboarding 骨架 → 可用实现",
                owner="safety_guard / user_profile / onboarding",
                status="done",
                detail="safety_guard 升级为 BLOCK/WARN 分级护栏 + PII 正则 + 兜底文案；user_profile 增 SQLiteUserProfileStore（复用 shared.database）；onboarding 增 OnboardingFlow 状态机 + apply_to_profile 与 user_profile 联动；core_orchestrator 主链路 node_receive/node_send_response/_recall_memory_monolithic 已接入；新增 21 个单测全绿。",
            ),
            MilestoneInfo(
                title="P1-C · 契约层物理搬迁 (shared_contracts/{models,events})",
                owner="平台基线",
                status="done",
                detail="shared_contracts/{models,events}.py 物理化（19 模型 + 13 事件 + 3 Protocol）；shared/{models,events}.py 反向变 deprecated re-export shim；141 passed 维持，check_arch baseline 已同步刷新。",
            ),
            MilestoneInfo(
                title="P1-D · 运行时层物理搬迁 (shared_runtime/{config,lite_mode})",
                owner="平台基线",
                status="done",
                detail="shared_runtime/{config,lite_mode}.py 物理化；shared/{config,lite_mode}.py 反向变 deprecated re-export shim；同步把 shared/llm_client.py 与 shared/database/__init__.py 内部 `from shared.config` 改向 `from shared_runtime.config` 以打破循环导入；141 passed 维持。剩余 llm_client/database/voice_runtime_config 留待 P1-E。",
            ),
            MilestoneInfo(
                title="P1-E · 运行时层剩余物理搬迁 (shared_runtime/{llm_client,database,voice_runtime_config})",
                owner="平台基线",
                status="done",
                detail="shared_runtime/{llm_client,database,voice_runtime_config}.py 物理化；shared/{llm_client,database/__init__,voice_runtime_config}.py 反向变 deprecated re-export shim；全仓 59 个文件、88+ 处 `from shared.X` 批量改向 `from shared_runtime.X` / `from shared_contracts.X`；shared_runtime/__init__.py 全部使用本地相对导入并扩充 __all__；141 passed + check_arch [ok] 维持。",
            ),
            MilestoneInfo(
                title="P2 · action_layer 物理合并入 action_executor.action2d",
                owner="平台基线",
                status="done",
                detail="action_executor/action2d/ 子包新建：generator_2d / lip_sync / router / sequencer / api / main 全部物理位于新包；action_layer/{__init__,generator_2d,lip_sync,router,sequencer,api,main}.py 整体转 deprecated re-export shim 并发出 DeprecationWarning（计划 V2.2 删除）；main.py 主链路改为 `from action_executor.action2d.main import lifespan`；141 passed + check_arch [ok] + Lite Mode 烟雾 53 routes 加载成功。",
            ),
        ],
        test_snapshot=TestSnapshot(
            command=(
                "pytest -q --ignore=voice_layer/tests/test_voice.py --ignore=memory_system/tests/test_memory.py "
                "-W error::pytest.PytestUnhandledThreadExceptionWarning"
            ),
            passed=836,
            failed=0,
            skipped=0,
            notes=[
                "V2.26：836 passed（55.22s，严格线程/无法回收异常警告）、Web86/双构建/6导入契约；真实本地Discord SDK HTTP/WS与QQ监听通过。",
                "V2.25：778 passed（42.86s）、Web85/双构建、6导入契约；实际图来源/单删/淡化/恢复/防重放与干净wheel SQL/Neo4j通过。",
                "V2.24：773 passed（46.04s）、Web83/双端构建、6导入契约和干净wheel宿主/端口通过；实际图提取/迁移/整库清理通过，单条来源仍待补齐。",
                "V2.23：765 passed（40.47s）、存储/人格/隐私133、6导入契约；真实SQL/方舟向量/压缩/重启回忆和迁移回滚通过。",
                "V2.22：765 passed（43.05s），6个导入契约通过；Web无变动沿用81/双端构建，真实SQL/上传ASR/O2与干净wheel注入通过。",
                "V2.21：758 passed（42.34s，线程警告视为错误），Web 81、双端构建通过；真实新旧 O2 与浏览器收音/播放通过，架构历史差异仍保留。",
                "V2.20：750 passed（44.58s，线程警告视为错误），Web 75，双端构建通过；干净 wheel 独立宿主/目录安装调用通过。",
                "V2.19：745 passed（63.84s，线程警告视为错误），桌面工具 16、Web 67、PC 代理与双端构建通过；双端审计零已知漏洞，实际 Windows 解包程序/聊天/本地 VAD 通过。",
                "V2.18：742 passed（58.02s，线程警告视为错误），桌面工具 16，Web 67，双端构建通过；实际桌面执行与 Windows 通知/SSE 验证通过。",
                "V2.17：729 passed（58.61s，线程警告视为错误），Web 66，Web/PC 构建通过；真实内容检查/语音与浏览器记忆图谱验证通过。",
                "V2.15：后端 666 passed（55.04s，线程警告视为错误），插件/协议子集另 24 passed；Web 53 和 Web/PC 构建通过。",
                "V2.14：656 passed（55.58 秒，线程警告视为错误），Web 53 passed、Web/PC builds passed，avatar 导入契约通过。",
                "V2.13：完整后端 646 passed（52.76 秒，线程警告视为错误），新增 SQL 图片记录用例另行 6 passed；Web 46 passed，Web/PC builds passed。",
                "V2.12：624 passed（52.22 秒，线程警告视为错误），Web 42 passed、Web/PC builds passed；真实文字→原生通话→文字连续性验证通过。",
                "V2.11：603 passed（49.76 秒，线程警告视为错误），Web 42 passed、Web/PC builds passed；真实 TTS/ASR、20 组首音对比、O2 打断与下一轮恢复通过。",
                "5.1、8.1/8.2 已验收；用户已恢复开发。8.4 音频/表情聚合、图片理解等继续保留。",
                "V2.10：573 passed（47.41 秒，线程警告视为错误），Web 29 tests passed，Web/PC build passed；真实 MCP 双传输、方舟任务、补充续办及浏览器刷新/手机布局已验证。",
                "V2.9：线程警告视为错误的完整后端回归 537 passed（43.91 秒），Web 25 tests passed，Web/PC build passed；自然发言、重启、桌面/移动设置和自然取消提醒已验证。",
                "V2.8：完整后端回归 433 passed（52.50 秒），Web 19 tests passed，Web/PC build passed；真实方舟分类、回复、日复核与重启保留已验证。",
                "V2.7：后端隔离数据库完整回归 407 passed；Web 19 tests passed，Web/PC build passed。真实模型压缩/日总结、跨会话回顾、记忆恢复与移动页面已验证。",
                "架构反向/SDK/横向导入已清零，角色文本基线仍有差异；新增主动关怀及语音持久化反向编排依赖已改为宿主注入。以下为历史验证记录。",
                "全量 **141 passed**（P1-E + P2 全部落地后基线零退步；忽略需要 ffmpeg/PostgreSQL 的 13 个集成用例）。",
                "P2 双向 import 等价性：`from action_layer import Action2DGenerator/ActionRouter/LipSyncGenerator/ActionSequencer` 与 `from action_executor.action2d import ...` 指向同一对象；DeprecationWarning 不报错。",
                "P1-E 双向 import 等价性：`from shared_runtime import LLMClient/Base/get_runtime_voice_config` 与 `from shared.{llm_client,database,voice_runtime_config} import ...` 指向同一对象。",
                "P1-D 双向 import 等价性：`from shared_runtime import Settings/get_settings/InMemoryEventBus` 与 `from shared.config / shared.lite_mode` 指向同一对象。",
                "P1-C 双向 import 等价性：`from shared_contracts import UserProfile` 与 `from shared.models import UserProfile` 指向同一个物理类对象。",
                "全仓业务侧 `from shared.X` 仅剩 1 处（`shared.prompt_engine`，未规划搬迁），其余全部改向 shared_contracts / shared_runtime。",
                "Lite Mode 启动烟雾：`COMPANION_LITE_MODE=true` 加载 main.app 成功，53 routes（含 /action/* 来自 action_executor.action2d）。",
                "新增包加载验证：`import shared_contracts, shared_runtime, safety_guard, user_profile, onboarding` 全绿。",
                "PersonaRegistry：`list_available_personas() == ['aria', 'default', 'xiaonuan']` ；`get_persona_profile(role_id='aria').name == 'Aria'`。",
                "依赖图基线（tools/check_arch.py）：反向 import core_orchestrator = 0 / 横向耦合对数 = 0 / 直连厂商 SDK = 2（voice_layer/asr.py，已记入 baseline）。",
                "action_executor：含 Open-Meteo 天气 mock、重复提醒 scheduler bump、`parse_repeat_interval` / 相对延迟正则回归。",
                "新增 15 个 action_executor 用例：registry / 内置 handler / reminders store / scheduler 与 push bus / NL 文本解析；另含 push_bus `poll_since` 轮询契约测试。",
                "新增 9 个 working memory 用例覆盖 observe_turn / window 截断 / 名字 & 喜好抽取 / dominant topic / snapshot rebuild / 与 prompt 的渲染。",
                "新增 4 个 streaming 测试覆盖 chunk_text_stream、stream_assistant_response 和 /orchestrator/turn/stream SSE 端点。",
                "voice_layer 的真实集成测试仍依赖 ffmpeg；当前测试通过 monkeypatch 已避免对它的硬依赖。",
            ],
        ),
        modules=[
            ModuleInfo(
                id="shared",
                name="Shared",
                name_zh="共享运行时",
                description="配置、数据库与LLM运行时位于 shared_runtime；旧 shared 包已在V2.22移出源码与wheel",
                status=ModuleStatus.COMPLETED,
                progress=100,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["Pydantic", "structlog"],
                    databases=[],
                    apis=["OpenAI API", "Anthropic API", "DashScope API"],
                ),
                key_features=[
                    "多 Provider LLM 客户端 (OpenAI/Anthropic/兼容接口)",
                    "运行时配置热更新 (无需重启)",
                    "配置持久化 (companion_llm_config.json + companion_voice_config.json)",
                    "语音运行时配置模块 (ASR/TTS provider 热切换)",
                    "统一数据模型 (TurnContext, UserProfile, EmotionState)",
                    "结构化日志 (structlog JSON输出)",
                    "V2.22：仅保留 shared_contracts / shared_runtime 真实导入，旧 shared 已移出",
                ],
                dependencies=[],
                blockers=[],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="shared_contracts",
                name="Shared Contracts",
                name_zh="共享契约层（V2 新增）",
                description="零依赖契约层：Pydantic 模型 + 事件类型 + LLM/ASR/TTS Protocol — 业务模块只依赖本包；P1-C 起 models/events 已物理位于本包",
                status=ModuleStatus.COMPLETED,
                progress=95,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["Pydantic", "typing.Protocol"],
                    databases=[],
                    apis=[],
                ),
                key_features=[
                    "🆕 models.py：UserProfile / TurnContext / EmotionState / PersonaProfile / MemoryEntry / ActionSequence 等 12 个核心模型",
                    "🆕 events.py：7 个事件类（TurnStarted / TurnCompleted / EmotionChanged / MemoryRecalled 等）",
                    "🆕 protocols.py：LLMClient / ASRProvider / TTSProvider 三个 @runtime_checkable Protocol",
                    "零运行时副作用：纯模型 + 协议形状，可被任何宿主直接消费",
                    "ADR-006 硬约束 2 兜底：业务侧只信 Protocol，不直连厂商 SDK",
                ],
                dependencies=[],
                blockers=[
                    "当前是 re-export shim，V2.1 物理迁入后才算完成",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="shared_runtime",
                name="Shared Runtime",
                name_zh="共享运行时层（V2 新增）",
                description="宿主可注入的运行时层：LLM 客户端 / 配置 / Lite Mode / 数据库 — P1-D 起 config + lite_mode 已物理位于本包",
                status=ModuleStatus.COMPLETED,
                progress=88,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI", "SQLAlchemy", "Pydantic Settings"],
                    databases=["SQLite (Lite) / PostgreSQL"],
                    apis=["OpenAI / Anthropic / DashScope（默认实现）"],
                ),
                key_features=[
                    "🆕 Settings / get_settings：配置注入入口",
                    "🆕 LLMClient（默认实现，已实现 chat/stream Protocol 形状）",
                    "🆕 get_runtime_voice_config / update_runtime_voice_config：语音运行时配置",
                    "🆕 init_database_schema / close_database：数据库生命周期",
                    "🆕 is_lite_mode()：是否处于 Lite Mode 的统一判断函数",
                    "ADR-006 硬约束:第三方宿主可注入自家实现整体替换",
                ],
                dependencies=["shared_contracts"],
                blockers=[
                    "当前是 re-export shim，V2.1 物理迁入后才算完成",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="core_orchestrator",
                name="Core Orchestrator",
                name_zh="核心编排层",
                description="LangGraph state machine, central coordination — 参考集成 demo（不是通用模块本体）",
                status=ModuleStatus.COMPLETED,
                progress=94,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI", "LangGraph", "httpx"],
                    databases=["Redis (会话状态)"],
                    apis=["内部微服务调用"],
                ),
                key_features=[
                    "LangGraph 状态机编排 (意图→记忆→角色→语音→动作)",
                    "🆕 主聊天流式输出 (POST /orchestrator/turn/stream, SSE)",
                    "🆕 POST /orchestrator/debug/prompt_preview — 不发 LLM 预览完整 conversation system prompt",
                    "微服务健康检查与熔断",
                    "事件总线 (Redis pub/sub)",
                    "LLM配置管理API (GET/POST /settings/llm)",
                    "语音配置管理API (GET/POST /settings/voice)",
                    "会话状态持久化",
                ],
                dependencies=["shared_contracts", "shared_runtime"],
                blockers=[],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="persona_engine",
                name="Persona Engine",
                name_zh="角色引擎",
                description="Continuous emotion, durable relationship, independent reactions — 宿主可独立接入，支持多角色与受控状态更新",
                status=ModuleStatus.IN_PROGRESS,
                progress=80,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI"],
                    databases=["SQLite / PostgreSQL (情绪、关系、幂等事务与日复核)"],
                    apis=[],
                ),
                key_features=[
                    "连续二维情绪与确定性平复，离散标签兼容呈现",
                    "独立反应分类、超时回退、生成参数与表达策略",
                    "SQL 原子情绪/关系事务；日复核补偿且不重复计分",
                    "情绪衰减与时间影响 (昼夜节律)",
                    "关系追踪 (亲密度/信任度/依赖度/理解度)",
                    "语气生成器 (基于情绪+关系的中文Prompt)",
                    "本地降级响应 (无LLM时规则回复)",
                    "每日关系摘要 (daily_digest)",
                    "🆕 V2 PersonaRegistry：data/personas/{role_id}.yaml 多角色加载",
                    "🆕 三套示例：default.yaml（小暖）/ xiaonuan.yaml / aria.yaml（英语示例）",
                    "🆕 get_persona_profile(role_id=...)：第三方宿主按 role_id 切换人格",
                ],
                dependencies=["shared_contracts"],
                blockers=[
                    "⚠️ OOC 边界控制 → 已在 safety_guard/ 模块预留骨架",
                    "⚠️ 0-1 破冰机制 → 已在 onboarding/ 模块预留骨架",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="memory_system",
                name="Memory System",
                name_zh="记忆系统",
                description="Working memory + persistent vector / graph store — 通用模块（可拆），目标解除与 prompt_engine 的硬绑定",
                status=ModuleStatus.IN_PROGRESS,
                progress=82,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI", "SQLAlchemy 2.x"],
                    databases=["PostgreSQL + pgvector", "Neo4j (知识图谱)", "Redis (缓存)"],
                    apis=["OpenAI Embeddings"],
                ),
                key_features=[
                    "三层记忆架构 (语义/事实/情感)",
                    "向量检索 (pgvector + cosine similarity)",
                    "知识图谱关联 (Neo4j)",
                    "自动遗忘机制 (importance decay)",
                    "记忆情感标签 (EmotionTag)",
                    "🆕 working memory 双层模型：滚动 N 轮 + 结构化用户摘要",
                    "🆕 working memory 可选 LLM：`LLM_SUMMARY` + `LLM_DIGEST` + `SUMMARY_TTL_SECONDS`（一次 JSON：topic + digest）",
                    "🆕 prompt 【当前对话状态】可注入「本段对话摘要」及启发式主题对照行",
                    "🆕 working memory 调试端点 GET/DELETE /memory/working/{session_id}",
                ],
                dependencies=["shared_contracts"],
                blockers=[
                    "⚠️ 结构化用户画像维度 → 已在 user_profile/ 模块预留骨架",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="voice_layer",
                name="Voice Layer",
                name_zh="语音模块",
                description="Real-time voice call pipeline: ASR + LLM streaming + TTS + VAD",
                status=ModuleStatus.COMPLETED,
                progress=92,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI", "WebSocket", "asyncio"],
                    databases=[],
                    apis=[
                        "faster-whisper (本地)",
                        "piper-tts (本地神经网络)",
                        "DashScope LLM stream",
                        "OpenAI/Whisper/Groq/SiliconFlow 兼容",
                    ],
                ),
                key_features=[
                    "实时语音通话管道 (WebSocket /voice/realtime)",
                    "本地ASR (faster-whisper base int8, ~150MB)",
                    "本地TTS (piper zh_CN-huayan-medium 神经网络, ~63MB)",
                    "LLM流式输出 + 句切片 + 边合成边播",
                    "Silero VAD自动断句 (浏览器内 WASM)",
                    "Barge-in打断支持 (用户说话时自动停止AI)",
                    "情绪→语音参数映射 (speed/pitch/style)",
                    "多Provider TTS (DashScope CosyVoice / 硅基流动 / Fish Audio)",
                    "前端运行时配置 (无需改代码切换Provider)",
                    "REST降级入口 (/voice/transcribe + /voice/synthesize)",
                ],
                dependencies=["shared_contracts", "persona_engine"],
                blockers=[
                    "音频工具链依赖 ffmpeg；在未安装环境下相关自动化测试会失败。",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="action_executor",
                name="Action Executor",
                name_zh="行动执行器",
                description="Pluggable handlers (reminders + repeat / time / Open-Meteo weather) + proactive push",
                status=ModuleStatus.IN_PROGRESS,
                progress=72,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI", "asyncio", "SQLAlchemy", "httpx"],
                    databases=["SQLite (lite mode) / PostgreSQL"],
                    apis=["Open-Meteo（当前天气，无 API key）", "日历 API（待接入）"],
                ),
                key_features=[
                    "🆕 ActionRegistry：插件式 handler 注册（@register_action）",
                    "🆕 内置 5 个 handler：get_time / get_weather（Open-Meteo）/ set_reminder / list_reminders / cancel_reminder",
                    "🆕 自然语言提醒：相对延迟 +「每 N 分钟/小时/天」固定间隔重复（`repeat_interval_seconds`）",
                    "🆕 SQLite / PG 持久化 reminders 表 + 后台 ReminderScheduler；重复提醒触发后自动顺延 `fire_at`",
                    "🆕 ProactivePushBus：进程内 pub/sub，提醒触发后经 /actions/push（或 poll）推到前端",
                    "🆕 GET /actions/push SSE + `/actions/push/poll` 轮询兜底",
                    "🆕 状态机集成：Intent.TOOL_USE 经关键字路由直接走 handler，无需 LLM",
                    "🆕 V2 即将合并 action_layer/lipsync 与 action_layer/sequencer 子模块",
                ],
                dependencies=["shared_contracts"],
                blockers=[
                    "日历 / OAuth 与「每天早上八点」类自然日 cron 仍未实现",
                    "Open-Meteo 依赖公网；离线环境需降级或自建代理",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="action_layer",
                name="Action Layer",
                name_zh="动作生成层（已 deprecated）",
                description="2D photo-driven action / lipsync / sequencer — V2 波次 5 已加 DeprecationWarning，V2.1 合并入 action_executor",
                status=ModuleStatus.IN_PROGRESS,
                progress=60,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI", "asyncio"],
                    databases=[],
                    apis=[],
                ),
                key_features=[
                    "Action2DGenerator / LipSyncGenerator / ActionSequencer",
                    "ActionRouter:意图 → 动作映射",
                    "🆕 V2 波次 5：__init__.py 注入 DeprecationWarning，运行时行为保持不变",
                    "🆕 计划：lipsync → action_executor.lipsync.LipSyncProvider；sequencer → action_executor.sequencer.SequencerProvider；generator_2d → action_executor.providers.action2d.Action2DProvider",
                ],
                dependencies=["shared_contracts"],
                blockers=[
                    "V2.1 起将物理合并入 action_executor 并删除本包",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="safety_guard",
                name="Safety Guard",
                name_zh="安全护栏（V2 新增 · 骨架）",
                description="Content safety / OOC boundary — V2 波次 6 骨架，仅有关键词过滤示例",
                status=ModuleStatus.IN_PROGRESS,
                progress=25,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["dataclasses"],
                    databases=[],
                    apis=["（计划）云端 moderation API"],
                ),
                key_features=[
                    "🆕 SafetyVerdict / SafetyGuard 类骨架",
                    "🆕 check_input / check_output 双向护栏接口",
                    "🆕 默认关键词 blocklist（仅占位示例）",
                    "🆕 第三方宿主可继承覆盖接入合规审核服务",
                ],
                dependencies=[],
                blockers=[
                    "尚未跑过端到端，未接入主链路；下一步补单测 + demo",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="user_profile",
                name="User Profile",
                name_zh="用户画像（V2 新增 · 骨架）",
                description="Cross-conversation user profile — V2 波次 6 骨架，提供内存版实现 + Store Protocol",
                status=ModuleStatus.IN_PROGRESS,
                progress=25,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["dataclasses", "typing.Protocol"],
                    databases=["（计划）SQLite / PostgreSQL"],
                    apis=[],
                ),
                key_features=[
                    "🆕 UserProfileSnapshot：display_name / locale / preferences / traits / metadata",
                    "🆕 UserProfileStore Protocol：get / upsert / merge_preferences",
                    "🆕 InMemoryUserProfileStore：Demo / 单测可用的进程内实现",
                    "🆕 schema 可配置，不锁维度数",
                ],
                dependencies=[],
                blockers=[
                    "尚未接入持久化层；与 memory_system 的分工边界还需细化",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="onboarding",
                name="Onboarding",
                name_zh="新用户引导（V2 新增 · 骨架）",
                description="0-1 ice-breaking flow — V2 波次 6 骨架，提供步骤定义 + 数据模型",
                status=ModuleStatus.IN_PROGRESS,
                progress=20,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["dataclasses"],
                    databases=[],
                    apis=[],
                ),
                key_features=[
                    "🆕 OnboardingStep：key / prompt / optional",
                    "🆕 OnboardingResult：user_id / role_id / nickname / locale / completed_steps",
                    "🆕 default_steps()：role / nickname / locale / greeting 四步示例",
                    "🆕 第三方宿主可替换默认问答模板",
                ],
                dependencies=[],
                blockers=[
                    "尚未接入主链路与 UI；下一步补 core_orchestrator 引导节点 + 前端步骤组件",
                ],
                last_updated="2026-05-07",
            ),
            ModuleInfo(
                id="frontend_app",
                name="Frontend App",
                name_zh="前端应用",
                description="Vue 3 web interface with real-time voice call + Live2D 渲染前端示例（参考 UI / 验收 demo，宿主可换 Unity / Unreal / 桌面）",
                status=ModuleStatus.COMPLETED,
                progress=94,
                tech_stack=TechStack(
                    languages=["TypeScript", "HTML", "CSS"],
                    frameworks=[
                        "Vue 3",
                        "Vite",
                        "Web Audio API",
                        "AudioWorklet",
                        "@ricky0123/vad-web",
                    ],
                    databases=[],
                    apis=[
                        "Core Orchestrator REST API",
                        "WebSocket /voice/realtime",
                    ],
                ),
                key_features=[
                    "实时聊天界面 (滚动加载)",
                    "🆕 主聊天 token 流式渲染 + 闪烁光标 (SSE 端点)",
                    "🆕 「输入中」UI 去重：消息气泡圆点与全局 typing-row 不再重复显示",
                    "语音输入 (长按录音 + WebM→WAV 转换)",
                    "实时语音通话面板 (豆包风格)",
                    "AudioWorklet PCM 采集 (Int16 16kHz)",
                    "浏览器内 Silero VAD (自动断句 + 打断)",
                    "WebSocket 双向流 (PCM 上行 / TTS PCM 下行)",
                    "链式音频播放队列 (无缝拼接 TTS chunks)",
                    "头像情绪显示 (EmotionBadge + 浮动动画)",
                    "Live2D 角色动画 (PixiJS 6 + pixi-live2d-display)",
                    "设置抽屉 (LLM配置 + 语音配置, 多Provider预设)",
                    "LLM 状态栏 (实时显示当前 Provider/模型)",
                    "项目状态面板 (本页)",
                    "离线检测与错误提示",
                    "自适应布局 (PC/移动端)",
                ],
                dependencies=["core_orchestrator", "voice_layer"],
                blockers=[],
                last_updated="2026-05-07",
            ),
        ],
        architecture_layers={
            "表现层": ["frontend_app"],
            "编排层": ["core_orchestrator"],
            "能力层": [
                "persona_engine",
                "memory_system",
                "voice_layer",
                "action_executor",
                "action_layer",
                "safety_guard",
                "user_profile",
                "onboarding",
            ],
            "契约层": ["shared_contracts"],
            "运行时层": ["shared_runtime"],
            "基础层（兼容期）": ["shared"],
        },
        release_notes=ReleaseSection(
            title="本轮交付 · V2.15 本地插件（持续开发）",
            pr_branch="master",
            summary=(
                "V2.15 本地插件发现、宿主授权和热重载已完成真实任务验证；累计 26/38 项验收。继续全部剩余计划。以下保留早期交付记录。"
                "V2.4 在 V2.3 人格连续性闭环基础上，围绕「让 demo 在外网/隧道下可稳定演示」收口："
                "保存 LLM 设置时不再因 api_key 留空而清空原 key；config 读写路径统一不再随 cwd 漂移；"
                "OpenAI/Anthropic 兼容端点自动补 /v1；DashScope/兼容 4xx 错误体直接转写成中文提示；"
                "Vite dev server 放通 trycloudflare.com 隧道 Host；新增 .env.lite 忽略；"
                "companion-ai 包及服务版本对齐 0.2.0。"
            ),
            items=[
                ReleaseNoteItem(
                    category="feature",
                    title="分段语音、有序播放与可靠打断",
                    detail="SSE 协商语音分段，云端预合成按序输出；停止/重听及刷新保留，打断丢弃旧帧和迟到解码，播放队列有界。",
                    impact="回复生成时即可开始播报；20 组固定文本首音中位减少 36.8%，原生实时打断与下一轮恢复通过。",
                    refs=["core_orchestrator/streaming_voice.py", "voice_layer/streaming_pipeline.py"],
                ),
                ReleaseNoteItem(
                    category="feature",
                    title="分工、MCP 与持久任务",
                    detail="Chat/Task/Memory/Device 共享普通/SSE 入口；任务可查看步骤、补充续办和停止，重启或未知结果不盲重放；官方 MCP 支持 stdio/HTTP。",
                    impact="可以执行先查时间再设置提醒等多步请求，并查看实际执行记录。",
                    refs=["core_orchestrator/specialists.py", "action_executor/task_agent.py", "action_executor/mcp_client.py"],
                ),
                ReleaseNoteItem(
                    category="fix",
                    title="LLM 设置保存防止 api_key 被清空",
                    detail="POST /settings/llm 时若请求体未携带 api_key，则保留原磁盘值（companion_llm_config.json），仅更新其余字段。",
                    impact="前端「保存设置」按钮不再误把已配置的 OpenAI/Anthropic/DashScope key 清掉。",
                    refs=[
                        "core_orchestrator/api.py::update_llm_settings",
                        "shared_runtime/llm_client.py",
                    ],
                ),
                ReleaseNoteItem(
                    category="fix",
                    title="config 读写路径统一",
                    detail="companion_llm_config.json / companion_voice_config.json 改为相对仓库根的固定锚点路径，不再因为 uvicorn 启动 cwd 不同而读到不同文件。",
                    impact="跨终端 / 跨调试入口启动时配置一致；解决了「调试台改了配置但服务读不到」的偶发问题。",
                    refs=["shared_runtime/config.py"],
                ),
                ReleaseNoteItem(
                    category="fix",
                    title="OpenAI/Anthropic base_url 自动补 /v1",
                    detail="用户填 https://api.openai.com 这种少 /v1 的写法时，LLMClient 自动追加 /v1，避免 404。",
                    impact="兼容大多数厂商「写 base_url 忘记带 /v1」的常见错误。",
                    refs=["shared_runtime/llm_client.py"],
                ),
                ReleaseNoteItem(
                    category="fix",
                    title="DashScope/兼容 4xx 错误转中文提示",
                    detail="HTTP 4xx 时把 provider 返回的 error.message（含 quota exhausted / invalid api key 等）解析出来透传给前端，而不是只显示 'HTTP 400'。",
                    impact="前端用户能立即知道是 key 错了 / 配额没了 / 模型名不对，而不是猜。",
                    refs=["shared_runtime/llm_client.py"],
                ),
                ReleaseNoteItem(
                    category="infra",
                    title="Vite dev server 放通 Cloudflare Tunnel Host",
                    detail="apps/web/vite.config.ts 的 server.allowedHosts 增加 .trycloudflare.com，搭配 cloudflared tunnel 即可把本地 Lite Mode demo 暴露给评审。",
                    impact="不再需要部署到云上即可对外评审，演示链路成本归零。",
                    refs=["apps/web/vite.config.ts"],
                ),
                ReleaseNoteItem(
                    category="infra",
                    title=".env.lite 加入 .gitignore",
                    detail="本地为 Lite Mode 临时覆盖的 .env.lite 不再被误提交，避免本地 LLM key/隧道域名等进仓库。",
                    impact="多人协作时本地配置不互相覆盖。",
                    refs=[".gitignore"],
                ),
                ReleaseNoteItem(
                    category="infra",
                    title="版本对齐 0.2.0",
                    detail="pyproject.toml / main.py / 各服务的 version 统一为 0.2.0，消除版本号不一致，方便外部按版本回归。",
                    impact="/health、/openapi.json、CLI 输出版本一致。",
                    refs=["pyproject.toml", "main.py"],
                ),
                ReleaseNoteItem(
                    category="feature",
                    title="人格连续性闭环（继承自 V2.3）",
                    detail="_recall_memory_monolithic 从 persona_engine.runtime 读持久化 emotion/relationship 状态（不再每轮重置）；node_sync_memory 写回情绪转变 + 关系指标更新 + 用户画像名字/偏好发现。",
                    impact="连续对话中伴侣能记住之前聊了什么、关系变亲密了、情绪随着对话浮动 — 不再是每轮重新开始。",
                    refs=[
                        "core_orchestrator/state_machine.py::_recall_memory_monolithic",
                        "core_orchestrator/state_machine.py::node_sync_memory",
                        "persona_engine/runtime.py",
                    ],
                ),
                ReleaseNoteItem(
                    category="fix",
                    title="架构 P0 收口：去单角色硬编码 + DashScope 解耦（继承自 V2.3）",
                    detail="state_machine / handlers / onboarding / prompt_engine / realtime production code 全部去硬编码角色名；voice_layer DashScope SDK 迁移至 providers/dashscope.py 封装层；check_arch.py 跳过 providers/ 目录 SDK 检查。",
                    impact="第三方宿主可自由切换角色名而无需修改核心代码；voice_layer 不再有直接 vendor SDK import。",
                    refs=[
                        "core_orchestrator/state_machine.py",
                        "voice_layer/providers/dashscope.py",
                        "tools/check_arch.py",
                    ],
                ),
                ReleaseNoteItem(
                    category="feature",
                    title="onboarding → user_profile → persona role_id 主链路（继承自 V2.3）",
                    detail="新增 /orchestrator/onboarding/start | answer | status 端点；OnboardingFlow 动态读 persona_store.list_available_personas()；apply_to_profile 写入 SQLiteUserProfileStore；_recall_memory_monolithic 按 user_profile.preferences.role_id 加载对应 persona。",
                    impact="新用户首次进入可选角色→称呼→语言，后续对话自动匹配所选人格。",
                    refs=[
                        "core_orchestrator/api.py::onboarding_start/answer/status",
                        "onboarding/__init__.py",
                    ],
                ),
                ReleaseNoteItem(
                    category="feature",
                    title="调试台状态可视化（继承自 V2.3）",
                    detail="新增 /orchestrator/debug/state（返回 system_prompt + emotion_state + relationship_metrics + working_memory + user_profile）；新增 /orchestrator/personas（可用角色列表）；/orchestrator/debug/prompt_preview 增加 intent 字段。",
                    impact="人格表现问题可诊断：区分是 Prompt、记忆、状态、关系系统还是 LLM 配置问题。",
                    refs=[
                        "core_orchestrator/api.py::debug_state",
                        "core_orchestrator/api.py::list_personas",
                    ],
                ),
                ReleaseNoteItem(
                    category="infra",
                    title="check_arch baseline 当前态",
                    detail="反向依赖 = 0；直连 SDK = 0（providers 封装后）；横向耦合 = 1（action_layer→action_executor 兼容 shim，待 V2.5 物理删除）；hardcoded_persona = 59（绝大多数集中在 voice_layer/resolver.py 与 tests/test_resolver.py 的预设别名表，已记入 baseline）。",
                    impact="架构违规基线反映当前真实状态，--check 模式无回归。",
                    refs=["tools/arch_baseline.json"],
                ),
            ],
        ),
    )
