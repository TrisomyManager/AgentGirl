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
        project_name="Companion AI - 小暖",
        version="0.2.0-realtime",
        current_phase="Phase 1.5 · 实时语音 MVP 收敛期",
        summary=(
            "单体 FastAPI 与 Lite Mode 已稳定；主聊天 SSE、记忆双层、行动执行器提醒链路与 "
            "项目状态面板已落地。本轮补齐 working memory 可选 LLM 主题与 digest（TTL 缓存）、"
            "Open-Meteo 天气、固定间隔重复提醒，以及「假设用户句」的 system prompt 预览 API。"
        ),
        last_updated="2026-05-06",
        overall_progress=94,
        recent_highlights=[
            "单体入口 `main.py` 已成为默认开发路径，Lite Mode 可直接启动完整 Web API。",
            "实时语音链路已打通：浏览器 VAD、AudioWorklet 录音、WebSocket 双向流和边合成边播放。",
            "LLM / Voice Provider 已支持运行时切换与配置持久化，无需改代码即可调参。",
            "前端已具备聊天、记忆库、语音通话、状态面板四个核心调试入口。",
            "🆕 主聊天流式输出已打通：`POST /orchestrator/turn/stream` 走 SSE，前端逐 token 渲染并保留 emotion / voice_url 元数据。",
            "🆕 记忆双层模型已落地：working memory 滚动 N 轮 + 结构化用户摘要，注入到 system prompt 的【当前对话状态】/【最近几轮对话】section。",
            "🆕 项目状态面板新增『本轮交付』分类卡片（feature / fix / docs / chore），交接时一眼看清当前分支改了什么。",
            "🆕 行动执行器初始闭环已打通：5 个内置 handler、自然语言『3 分钟后提醒我喝水』、SQLite 持久化、后台轮询触发，前端 ReminderToast 通过 /actions/push SSE（及轮询兜底）接收。",
            "🆕 工程收尾：`.env` 固定从 `companion-ai/.env` 解析（与 cwd 无关）、`/actions/push/poll` 轮询兜底 + 前端 2.5s 轮询、SSE 首包 padding 4KB、状态面板可加载完整 system prompt。",
            "🆕 行动执行器：Open-Meteo 无 key 实时天气；自然语言「每 N 分钟」重复提醒（SQLite `repeat_interval_seconds` + scheduler 自动顺延）；相对延迟正则收紧，避免误吞「每 5 分钟」。",
            "🆕 编排调试：`POST /orchestrator/debug/prompt_preview` 可在不发 LLM 的情况下拼装与主路径一致的 conversation system prompt（含意图分类 + 记忆召回）。",
            "🆕 working memory 可选 LLM：`COMPANION_WORKING_MEMORY_LLM_SUMMARY` / `LLM_DIGEST` 一次 JSON 补全精炼主题 + 一句会话摘要；`SUMMARY_TTL_SECONDS` 按 transcript 指纹去重，减少 recall 连打。",
        ],
        next_focus=[
            FocusItem(
                title="Prompt 拼装可测化与对比",
                detail="已有 `/debug/system_prompt`（最近一轮）与 `prompt_preview`（假设用户句）；下一步可把拼装抽到更可测的层，并视需要支持按会话 / 版本 diff。",
            ),
            FocusItem(
                title="working memory 持久化与跨进程",
                detail="LLM 摘要缓存仅在进程内；多副本 / 重启后需从 transcript 重算或外置 Redis 缓存键。",
            ),
            FocusItem(
                title="action_executor 日历与高级调度",
                detail="天气已走 Open-Meteo 公网接口；日历 / OAuth 仍待接入。重复提醒为固定间隔（每 N 分/时/天），尚未支持 cron 表达式与自然日「每天早上八点」。",
            ),
        ],
        risks=[
            FocusItem(
                title="测试基线再上一档",
                detail=(
                    "2026-05-06 `pytest -q`（`--ignore=voice_layer/tests/test_voice.py`）全量 **127 passed**（含 working memory LLM 缓存与 digest、"
                    "Open-Meteo 天气与重复提醒、prompt_preview ASGI）；Open-Meteo 依赖外网，极端网络下可能偶发失败；"
                    "启用 working memory LLM 时每新 transcript 指纹至多一次补全（TTL 内 recall 复用缓存）。"
                ),
            ),
            FocusItem(
                title="文档曾与代码漂移",
                detail="根目录 handoff / plan 长期滞后于 `companion-ai` 实现，接手时需要优先以代码和状态接口为准。",
            ),
            FocusItem(
                title="动作与设备层仍是骨架",
                detail="实时语音体验已领先，但 action / device_coordination 仍未进入真正的产品闭环。",
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
                title="记忆系统收敛",
                owner="memory_system",
                status="active",
                detail="向量检索 + working memory 已接主路径；可选 LLM 主题 + 一句 digest + TTL 去重；图谱与跨副本缓存仍待加强。",
            ),
            MilestoneInfo(
                title="动作执行器与主动能力",
                owner="action_executor",
                status="active",
                detail="提醒闭环 + 无 key 天气 + 固定间隔重复提醒已落地；日历与 cron 表达式仍为后续项。",
            ),
        ],
        test_snapshot=TestSnapshot(
            command="python -m pytest -q",
            passed=127,
            failed=0,
            skipped=0,
            notes=[
                "全量 **127 passed**（`--ignore=voice_layer/tests/test_voice.py`；含 working memory LLM 缓存与 digest、Open-Meteo、prompt_preview）。",
                "action_executor：含 Open-Meteo 天气 mock、重复提醒 scheduler bump、`parse_repeat_interval` / 相对延迟正则回归。",
                "新增 15 个 action_executor 用例：registry / 内置 handler / reminders store / scheduler 与 push bus / NL 文本解析；另含 push_bus `poll_since` 轮询契约测试。",
                "新增 9 个 working memory 用例覆盖 observe_turn / window 截断 / 名字 & 喜好抽取 / dominant topic / snapshot rebuild / 与 prompt 的渲染。",
                "新增 4 个 streaming 测试覆盖 chunk_text_stream、stream_assistant_response 和 /orchestrator/turn/stream SSE 端点。",
                "shared/tests/test_prompt_engine.py 的中英文断言已与 prompt_engine 的中文实现对齐。",
                "pyproject.toml 已显式声明 numpy 依赖，避免 voice_layer 在干净环境下因 ModuleNotFoundError 整组无法 collect。",
                "voice_layer 的真实集成测试仍依赖 ffmpeg；当前测试通过 monkeypatch 已避免对它的硬依赖。",
            ],
        ),
        modules=[
            ModuleInfo(
                id="shared",
                name="Shared",
                name_zh="共享基础库",
                description="Cross-module utilities, models, config, LLM client",
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
                ],
                dependencies=[],
                blockers=[],
                last_updated="2026-05-04",
            ),
            ModuleInfo(
                id="core_orchestrator",
                name="Core Orchestrator",
                name_zh="核心编排层",
                description="LangGraph state machine, central coordination",
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
                dependencies=["shared"],
                blockers=[],
                last_updated="2026-05-05",
            ),
            ModuleInfo(
                id="persona_engine",
                name="Persona Engine",
                name_zh="角色引擎",
                description="Emotion, relationship, tone generation",
                status=ModuleStatus.COMPLETED,
                progress=90,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI"],
                    databases=["Redis (情绪状态)", "PostgreSQL (关系指标)"],
                    apis=[],
                ),
                key_features=[
                    "情绪状态机 (7种基础情绪 + 组合状态)",
                    "情绪衰减与时间影响 (昼夜节律)",
                    "关系追踪 (亲密度/信任度/依赖度/理解度)",
                    "语气生成器 (基于情绪+关系的中文Prompt)",
                    "本地降级响应 (无LLM时规则回复)",
                    "每日关系摘要 (daily_digest)",
                ],
                dependencies=["shared"],
                blockers=[],
                last_updated="2026-04-30",
            ),
            ModuleInfo(
                id="memory_system",
                name="Memory System",
                name_zh="记忆系统",
                description="Working memory + persistent vector / graph store",
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
                dependencies=["shared"],
                blockers=[
                    "LLM 开关打开时增加延迟与费用；跨进程无共享缓存",
                ],
                last_updated="2026-05-06",
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
                dependencies=["shared", "persona_engine"],
                blockers=[
                    "音频工具链依赖 ffmpeg；在未安装环境下相关自动化测试会失败。",
                ],
                last_updated="2026-05-04",
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
                ],
                dependencies=["shared", "core_orchestrator"],
                blockers=[
                    "日历 / OAuth 与「每天早上八点」类自然日 cron 仍未实现",
                    "Open-Meteo 依赖公网；离线环境需降级或自建代理",
                ],
                last_updated="2026-05-05",
            ),
            ModuleInfo(
                id="frontend_app",
                name="Frontend App",
                name_zh="前端应用",
                description="Vue 3 web interface with real-time voice call",
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
                last_updated="2026-05-05",
            ),
        ],
        architecture_layers={
            "表现层": ["frontend_app"],
            "编排层": ["core_orchestrator"],
            "能力层": ["persona_engine", "memory_system", "voice_layer", "action_executor", "action_layer"],
            "基础层": ["shared"],
        },
        release_notes=ReleaseSection(
            title="本轮交付 · working memory 缓存 + 行动与编排",
            pr_branch="cursor/working-memory-digest-cache-03ab",
            summary=(
                "一次 JSON 补全同时产出精炼 topic 与一句 session_digest，按 transcript 指纹 + TTL 进程内缓存；"
                "行动执行器侧保持 Open-Meteo 天气与固定间隔重复提醒；编排层保留 prompt 预览调试能力。"
            ),
            items=[
                ReleaseNoteItem(
                    category="feature",
                    title="Working memory · LLM topic + digest（可选）",
                    detail="`COMPANION_WORKING_MEMORY_LLM_SUMMARY` / `LLM_DIGEST`；`COMPANION_WORKING_MEMORY_SUMMARY_TTL_SECONDS` 去重。`WorkingMemorySnapshot.session_digest` 注入 prompt「本段对话摘要」。",
                    impact="默认仍零 LLM；开启后对话状态更可读且 recall 风暴时少打模型。",
                    refs=[
                        "memory_system/working.py",
                        "shared/config.py",
                        "shared/prompt_engine.py",
                        "memory_system/recall.py",
                    ],
                ),
                ReleaseNoteItem(
                    category="feature",
                    title="Open-Meteo 实时天气（无 API key）",
                    detail="`get_weather` 通过 geocoding + forecast 拉取当前气温/湿度/风速与 WMO 天气代码中文描述；失败时返回可读错误。",
                    impact="用户问「北京天气」即可得到真实数据，无需先配置商业天气 key。",
                    refs=[
                        "action_executor/weather_open_meteo.py",
                        "action_executor/handlers.get_weather",
                    ],
                ),
                ReleaseNoteItem(
                    category="feature",
                    title="重复提醒（固定间隔）",
                    detail="解析「每 5 分钟」「every 2 hours」等短语写入 `repeat_interval_seconds`；scheduler 触发后 bump `fire_at` 而非标记 fired；SSE payload 带 `repeating`。",
                    impact="「3 分钟后每 5 分钟提醒我喝水」类需求可在 Lite Mode 下持续触发，直至用户取消。",
                    refs=[
                        "action_executor/reminders.py",
                        "action_executor/handlers.set_reminder",
                        "shared/database.init_database_schema (ALTER 迁移)",
                    ],
                ),
                ReleaseNoteItem(
                    category="feature",
                    title="POST /orchestrator/debug/prompt_preview",
                    detail="`build_prompt_preview` 复用 classify_intent + recall_memory + `build_conversation_system_prompt`，与主回复路径一致但不调用 LLM。",
                    impact="调试台 / 自动化可稳定断言完整 system prompt，无需依赖上一轮聊天的内存快照。",
                    refs=[
                        "core_orchestrator/state_machine.build_prompt_preview",
                        "core_orchestrator/api.debug_prompt_preview",
                    ],
                ),
                ReleaseNoteItem(
                    category="fix",
                    title="相对延迟正则不误匹配「每 N 分钟」",
                    detail="中文相对延迟模式要求「后/以后/之后」等后缀，避免把「每5分钟」当成「5分钟」。",
                    impact="组合「3分钟后每5分钟提醒」时 body 解析与时间计算正确。",
                    refs=["action_executor/reminders._DELAY_PATTERNS"],
                ),
                ReleaseNoteItem(
                    category="chore",
                    title="project_status / .env.example",
                    detail="同步 overall_progress、memory_system / action_executor 卡片、milestones、test_snapshot（127 passed，同上 ignore）与 `.env.example` working memory LLM 注释。",
                    impact="状态面板与运维配置、handoff 口径一致。",
                    refs=[
                        "core_orchestrator/project_status.py",
                        "companion-ai/.env.example",
                    ],
                ),
            ],
        ),
    )
