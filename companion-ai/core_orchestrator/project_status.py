"""Project development status tracking and API."""

from __future__ import annotations

from typing import Any, Dict, List
from enum import Enum
from pydantic import BaseModel, Field


class ModuleStatus(str, Enum):
    """Module development status."""
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    PLANNED = "planned"
    BLOCKED = "blocked"


class TechStack(BaseModel):
    """Technology stack for a module."""
    languages: List[str] = []
    frameworks: List[str] = []
    databases: List[str] = []
    apis: List[str] = []


class ModuleInfo(BaseModel):
    """Single module development info."""
    id: str
    name: str
    name_zh: str
    description: str
    status: ModuleStatus
    progress: int = Field(..., ge=0, le=100, description="Completion percentage")
    tech_stack: TechStack
    key_features: List[str] = []
    dependencies: List[str] = []
    blockers: List[str] = []
    last_updated: str = ""


class ProjectStatusData(BaseModel):
    """Complete project status data."""
    project_name: str
    version: str
    overall_progress: int
    modules: List[ModuleInfo]
    architecture_layers: Dict[str, List[str]]


def get_project_status() -> ProjectStatusData:
    """Return current project development status."""
    return ProjectStatusData(
        project_name="Companion AI - 小暖",
        version="0.2.0-Realtime",
        overall_progress=85,
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
                    "多Provider LLM客户端 (OpenAI/Anthropic/兼容接口)",
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
                progress=95,
                tech_stack=TechStack(
                    languages=["Python 3.11+"],
                    frameworks=["FastAPI", "LangGraph", "httpx"],
                    databases=["Redis (会话状态)"],
                    apis=["内部微服务调用"],
                ),
                key_features=[
                    "LangGraph状态机编排 (意图→记忆→角色→语音→动作)",
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
                progress=70,
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
                last_updated="2026-04-30",
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
                blockers=[],
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
                progress=92,
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
