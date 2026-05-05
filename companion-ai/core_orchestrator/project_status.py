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
    notes: List[str] = Field(default_factory=list)


class FocusItem(BaseModel):
    """A single current focus or risk item."""

    title: str
    detail: str


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


def get_project_status() -> ProjectStatusData:
    """Return current project development status."""
    return ProjectStatusData(
        project_name="Companion AI - 小暖",
        version="0.2.0-realtime",
        current_phase="Phase 1.5 · 实时语音 MVP 收敛期",
        summary="单体 FastAPI 入口、实时语音通话链路、运行时配置面板都已落地；当前重心转向记忆模型收敛、主聊天流式输出和测试稳定性。",
        last_updated="2026-05-05",
        overall_progress=85,
        recent_highlights=[
            "单体入口 `main.py` 已成为默认开发路径，Lite Mode 可直接启动完整 Web API。",
            "实时语音链路已打通：浏览器 VAD、AudioWorklet 录音、WebSocket 双向流和边合成边播放。",
            "LLM / Voice Provider 已支持运行时切换与配置持久化，无需改代码即可调参。",
            "前端已具备聊天、记忆库、语音通话、状态面板四个核心调试入口。",
        ],
        next_focus=[
            FocusItem(
                title="收敛 Prompt Engine",
                detail="把 `state_machine.py` 中的 system prompt 硬编码抽到共享层，方便人格文件、关系摘要和调试台复用。",
            ),
            FocusItem(
                title="补齐主聊天流式输出",
                detail="语音通话链路已支持流式，主聊天 REST 路径还没有把 token streaming 接到消息区。",
            ),
            FocusItem(
                title="重构记忆双层模型",
                detail="当前记忆层仍偏向“长期库”，下一步要补 working / persistent memory 分层和更稳定的摘要策略。",
            ),
        ],
        risks=[
            FocusItem(
                title="测试基线已恢复",
                detail="2026-05-05 本地 `python -m pytest -q` 为 97 passed / 0 failed；之前的 sqlite 向量绑定与 prompt 用例漂移已修复，未安装 ffmpeg 时仍需注意 voice_layer 的真实集成测试。",
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
                status="queued",
                detail="主动提醒、外部查询和插件式动作执行还处于规划阶段，暂未接入真实闭环。",
            ),
        ],
        test_snapshot=TestSnapshot(
            command="python -m pytest -q",
            passed=97,
            failed=0,
            notes=[
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
                progress=93,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI", "LangGraph", "httpx"],
                    databases=["Redis (会话状态)"],
                    apis=["内部微服务调用"],
                ),
                key_features=[
                    "LangGraph 状态机编排 (意图→记忆→角色→语音→动作)",
                    "微服务健康检查与熔断",
                    "事件总线 (Redis pub/sub)",
                    "LLM配置管理API (GET/POST /settings/llm)",
                    "语音配置管理API (GET/POST /settings/voice)",
                    "会话状态持久化",
                ],
                dependencies=["shared"],
                blockers=[],
                last_updated="2026-05-04",
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
                description="Semantic/factual/emotional memory with vector search",
                status=ModuleStatus.IN_PROGRESS,
                progress=68,
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
                ],
                dependencies=["shared"],
                blockers=[
                    "需实现 working/persistent memory 二分模型 (参考AIRI)",
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
                description="External action execution (reminders, searches, etc.)",
                status=ModuleStatus.PLANNED,
                progress=10,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI"],
                    databases=["Redis (定时任务)"],
                    apis=["天气API", "日历API"],
                ),
                key_features=[
                    "主动提醒 (基于时间/事件触发)",
                    "外部信息查询 (天气/新闻)",
                    "日程管理集成",
                ],
                dependencies=["shared", "core_orchestrator"],
                blockers=[
                    "插件系统未设计",
                    "主动推送机制未实现 (需WebSocket)",
                ],
                last_updated="2026-04-30",
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
                    "语音输入 (长按录音 + WebM→WAV 转换)",
                    "🆕 实时语音通话面板 (豆包风格)",
                    "🆕 AudioWorklet PCM 采集 (Int16 16kHz)",
                    "🆕 浏览器内 Silero VAD (自动断句 + 打断)",
                    "🆕 WebSocket 双向流 (PCM 上行 / TTS PCM 下行)",
                    "🆕 链式音频播放队列 (无缝拼接 TTS chunks)",
                    "头像情绪显示 (EmotionBadge + 浮动动画)",
                    "Live2D 角色动画 (PixiJS 6 + pixi-live2d-display)",
                    "设置抽屉 (LLM配置 + 语音配置, 多Provider预设)",
                    "LLM 状态栏 (实时显示当前 Provider/模型)",
                    "项目状态面板 (本页)",
                    "离线检测与错误提示",
                    "自适应布局 (PC/移动端)",
                ],
                dependencies=["core_orchestrator", "voice_layer"],
                blockers=[
                    "LLM 文字流式输出尚未在主聊天接口对接 (语音通话已支持)",
                ],
                last_updated="2026-05-04",
            ),
        ],
        architecture_layers={
            "表现层": ["frontend_app"],
            "编排层": ["core_orchestrator"],
            "能力层": ["persona_engine", "memory_system", "voice_layer", "action_executor"],
            "基础层": ["shared"],
        },
    )
