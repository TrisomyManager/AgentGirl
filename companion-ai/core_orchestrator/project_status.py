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
            "项目状态面板已落地。本轮补齐「假设用户句」的 system prompt 预览 API，便于工程调试。"
        ),
        last_updated="2026-05-05",
        overall_progress=93,
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
            "🆕 编排调试：`POST /orchestrator/debug/prompt_preview` 可在不发 LLM 的情况下拼装与主路径一致的 conversation system prompt（意图分类 + 记忆召回）。",
        ],
        next_focus=[
            FocusItem(
                title="状态面板深度联动",
                detail="后端已提供 `prompt_preview`；前端可在面板内直接输入用户句并展示结果，或做与「最近一轮」快照的并排 diff。",
            ),
            FocusItem(
                title="working memory 摘要 LLM 化",
                detail="当前 working memory 的 dominant_topic / 摘要是 bag-of-words 启发式，等成本/延迟可控后再切换到 LLM 摘要器。",
            ),
            FocusItem(
                title="action_executor 真实接入",
                detail="天气仍为 stub（保留接入形状）；日历与 OAuth 未接。提醒为单次触发，循环 / cron 风格调度尚未实现。",
            ),
        ],
        risks=[
            FocusItem(
                title="测试基线再上一档",
                detail="2026-05-05 `pytest -q` 全量 **127 passed**（新增 `prompt_preview` ASGI 用例）；voice_layer 在无 ffmpeg 环境下历史上有 skip，以本机 pytest 输出为准。",
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
                detail="向量检索和情感标签已在，但工作记忆 / 长期记忆分层、摘要质量和 sqlite 测试兼容还需继续补。",
            ),
            MilestoneInfo(
                title="动作执行器与主动能力",
                owner="action_executor",
                status="active",
                detail="提醒 + 时间 + SSE/轮询推送已闭环；天气 stub、日历与重复调度仍为后续项。",
            ),
        ],
        test_snapshot=TestSnapshot(
            command="python -m pytest -q",
            passed=127,
            failed=0,
            skipped=0,
            notes=[
                "全量 **127 passed**（含 `POST /orchestrator/debug/prompt_preview` 集成测试）。",
                "15+ action_executor 用例：registry / handler / reminders / scheduler / push_bus / NL 解析 / `poll_since`。",
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
                progress=78,
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
                    "🆕 working memory 调试端点 GET/DELETE /memory/working/{session_id}",
                ],
                dependencies=["shared"],
                blockers=[
                    "记忆摘要质量依赖LLM",
                ],
                last_updated="2026-05-05",
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
                description="Pluggable handlers (reminders / time / weather stub) + proactive push (SSE + poll)",
                status=ModuleStatus.IN_PROGRESS,
                progress=62,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI", "asyncio", "SQLAlchemy"],
                    databases=["SQLite (lite mode) / PostgreSQL"],
                    apis=["天气 stub（待真实 API）", "日历 API（待接入）", "GET /actions/push/poll"],
                ),
                key_features=[
                    "🆕 ActionRegistry：插件式 handler 注册（@register_action）",
                    "🆕 内置 5 个 handler：get_time / get_weather (stub) / set_reminder / list_reminders / cancel_reminder",
                    "🆕 自然语言提醒解析（'3 分钟后提醒我喝水'）",
                    "🆕 SQLite 持久化 reminders 表 + 后台 ReminderScheduler 轮询触发",
                    "🆕 ProactivePushBus：进程内 pub/sub；GET /actions/push SSE + `/actions/push/poll` 轮询兜底（Cloudflare 友好）",
                    "🆕 GET /actions/push SSE 端点 + 前端 ReminderToast 浮窗",
                    "🆕 状态机集成：Intent.TOOL_USE 经关键字路由直接走 handler，无需 LLM",
                ],
                dependencies=["shared", "core_orchestrator"],
                blockers=[
                    "天气 / 日历 API 真实接入待外部 key 或选型",
                    "提醒目前只是一次触发，循环 / cron 风格调度尚未实现",
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
                    "🆕 项目状态面板：整体进度 / 测试快照 / Prompt 调试（最近 system prompt + 可扩展预览）",
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
            title="本轮交付 · 进度面板与 Prompt 预览",
            pr_branch="cursor/project-status-viz-03ab",
            summary=(
                "同步 `project_status` 与当前测试基线；新增 "
                "`POST /orchestrator/debug/prompt_preview`；前端状态面板增强 Prompt 调试区。"
            ),
            items=[
                ReleaseNoteItem(
                    category="feature",
                    title="POST /orchestrator/debug/prompt_preview",
                    detail="对任意 `TurnRequest` 走意图分类 + 记忆召回后拼装 `build_conversation_system_prompt`，不调 LLM，便于对照主路径 prompt。",
                    impact="工程可在不聊天的情况下验证 prompt 注入是否正确。",
                    refs=[
                        "core_orchestrator/state_machine.build_prompt_preview",
                        "POST /orchestrator/debug/prompt_preview",
                        "core_orchestrator/tests/test_prompt_preview.py",
                    ],
                ),
                ReleaseNoteItem(
                    category="feature",
                    title="项目状态面板 · Prompt 调试增强",
                    detail="保留「最近 system prompt」加载；增加示例用户句、一键预览（调用 prompt_preview）、复制与下载 .txt。",
                    impact="交接与联调时更少切终端 / Postman。",
                    refs=["frontend_app/src/components/ProjectStatusPanel.vue"],
                ),
                ReleaseNoteItem(
                    category="docs",
                    title="project_status 数据刷新",
                    detail="overall_progress、highlights、next_focus、milestones、test_snapshot、模块卡片与 master 能力对齐（含 push poll、prompt 预览）。",
                    impact="`/orchestrator/project_status` 与面板展示一致。",
                    refs=["companion-ai/core_orchestrator/project_status.py"],
                ),
            ],
        ),
    )
