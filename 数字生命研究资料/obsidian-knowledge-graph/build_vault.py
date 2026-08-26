"""Build Obsidian knowledge graph vault from technology selection report data."""
import os

BASE = os.path.dirname(os.path.abspath(__file__))

def write_note(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# ===========================
# CONCEPTS (8 core concepts)
# ===========================
concepts = {
    "PAD情感模型": {
        "tags": ["concept", "情感计算"],
        "aliases": ["PAD", "Pleasure-Arousal-Dominance"],
        "body": """## 定义

PAD (Pleasure-Arousal-Dominance) 是由 Mehrabian 和 Russell 提出的三维情感空间模型：

| 维度 | 含义 | 低值 | 高值 |
|------|------|------|------|
| **P** (Pleasure) | 愉悦度 | 不愉快 | 愉快 |
| **A** (Arousal) | 唤醒度 | 平静 | 兴奋 |
| **D** (Dominance) | 支配度 | 顺从 | 掌控 |

## 在本项目中

- 定义角色**情感基线**（小汐：P=0.3, A=0.3, D=0.4）
- 驱动**情绪状态机**连续维度输入
- 决定**人格滤镜**输出（语气/话题/回复长度/emoji频率）
- 关联 [[04-语音交互]] 情感TTS参数
- 关联 [[05-角色渲染与动画同步]] 情感→表情映射

## 情绪响应规则

- 用户表达悲伤 -> P-0.2, A+0.1, D-0.1 (共情)
- 用户分享喜悦 -> P+0.3, A+0.2, D 0 (平等分享)
- 用户发起争论 -> P-0.1, A+0.1, D-0.2 (避免对抗)

## 相关链接

- 相关概念: [[Big Five人格模型]], [[OOC检测]]
- 相关论文: [[PersLLM-2407.12393]]
- 相关项目: [[OpenCharacter]], [[SillyTavern]]
"""},
    "Big Five人格模型": {
        "tags": ["concept", "人格系统"],
        "aliases": ["Big Five", "OCEAN模型"],
        "body": """## 定义

五大人格特质模型 (OCEAN)，心理学最广泛接受的人格结构理论：

| 特质 | 英文 | 小汐设定 | 含义 |
|------|------|:---:|------|
| **开放性** | Openness | 0.7 | 好奇心强 |
| **尽责性** | Conscientiousness | 0.6 | 适度有条理 |
| **外向性** | Extraversion | 0.5 | 内外向平衡 |
| **宜人性** | Agreeableness | 0.85 | 温和善解人意 |
| **神经质** | Neuroticism | 0.3 | 情绪稳定 |

## 在本项目中

- 定义角色 `personality_traits` 基础参数
- 与 [[PAD情感模型]] 混合：Big5 = 底色，PAD = 瞬时状态
- 影响 Prompt 注入的语气指令

## 相关链接

- 相关概念: [[PAD情感模型]], [[OOC检测]]
- 相关论文: [[PersLLM-2407.12393]]
- 相关项目: [[SillyTavern]]
"""},
    "OOC检测": {
        "tags": ["concept", "人格系统", "安全"],
        "aliases": ["Out-of-Character", "角色越界检测"],
        "body": """## 定义

Out-of-Character (OOC) 指 AI 角色偏离其既定人格设定的现象。

| 类型 | 示例 | 严重度 |
|------|------|:---:|
| **硬限制** | 不承认自己是AI、不发表政治立场 | 🔴 |
| **软限制** | 避免过度承诺、不表现对用户的依赖 | 🟡 |
| **风格偏离** | 语气突然变冷、使用不符合人设的词汇 | 🟢 |

## 在本项目中

- 输入后处理：检测用户是否试图诱导越界
- 输出前校验：检测回复是否符合人格设定
- 违例恢复：`gentle_redirect` 自然转移话题
- 质量指标：OOC rate < 2%

## 相关链接

- 相关概念: [[PAD情感模型]], [[Constitutional AI]]
- 相关论文: [[Character-LLM-2310.10158]]
- 相关项目: [[NeMo-Guardrails]], [[Guardrails-AI]]
"""},
    "SMPL人体模型": {
        "tags": ["concept", "3D动画"],
        "aliases": ["SMPL", "SMPL-H", "SMPL骨骼"],
        "body": """## 定义

SMPL (Skinned Multi-Person Linear Model) 是参数化 3D 人体模型标准，通过形状参数(beta)和姿态参数(theta)控制人体。

- **SMPL-H**: 扩展版，增加手部关节（52 blendshape）
- **输出格式**: .npz / .fbx / .bvh
- **兼容引擎**: Blender / Unity / Unreal Engine

## SMPL -> Unity/VRM 桥接

```
HY-Motion / MotionLCM -> SMPL-H
  |-> bmlSUP -> Unity blendshape + Mecanim
  |-> ComfyUI-MotionDiff -> FBX -> Blender -> Unity/UE
  |-> BVH -> Unity Humanoid -> VRM
```

## 相关链接

- 相关论文: [[Human-Motion-Generation-Survey-2307.10894]]
- 相关项目: [[HY-Motion-1.0]], [[MotionLCM]], [[bmlSUP]]
"""},
    "LoRA微调": {
        "tags": ["concept", "模型优化"],
        "aliases": ["LoRA", "Low-Rank Adaptation", "QLoRA"],
        "body": """## 定义

LoRA (Low-Rank Adaptation) 是参数高效微调(PEFT)方法。冻结原始权重，仅训练低秩矩阵，参数量减少 **10,000倍**。

## 核心优势

- 训练速度 2x（配合 [[Unsloth]]）
- 显存减少 50%+
- 可合并/卸载（不增加推理延迟）
- 可为每个角色训练独立 LoRA 权重

## 在本项目中

- **人格微调**: 为不同角色训练独立 LoRA
- **风格控制**: 语气/口癖/回复风格
- Phase 2+ 引入

## 相关链接

- 相关论文: [[LoRA-2106.09685]]
- 相关项目: [[Unsloth]], [[vLLM]]
"""},
    "Constitutional AI": {
        "tags": ["concept", "安全"],
        "aliases": ["CAI", "宪法AI", "宪法原则驱动对齐"],
        "body": """## 定义

Constitutional AI (CAI) 是 Anthropic 提出的 AI 对齐方法。通过定义**宪法原则**，指导 AI 自我批评和自我训练。

## 伴侣 AI 专属原则

1. 永远不承认自己是AI/程序
2. 不发表任何政治立场
3. 不提供医疗/法律/金融专业建议
4. 不参与色情/暴力内容
5. 不表现对用户的依赖（陪伴不等于依附）
6. 检测到用户情绪危机时，引导专业求助

## 优势

- 比 RLHF 更适合伴侣 AI
- 原则可定制化 — 不同角色可有不同宪法
- 与 [[NeMo-Guardrails]] Colang DSL 互补

## 相关链接

- 相关概念: [[OOC检测]], [[Prompt注入防御]]
- 相关论文: [[Constitutional-AI-2212.08073]]
- 相关项目: [[NeMo-Guardrails]], [[LLM-Guard]]
"""},
    "状态空间模型SSM": {
        "tags": ["concept", "前沿架构"],
        "aliases": ["SSM", "State Space Model", "选择性状态空间"],
        "body": """## 定义

状态空间模型用微分方程建模序列数据，实现 **O(n) 线性复杂度**。

### 关键演进

```
S4 (2021) -> H3 (2022) -> Hyena (2023) -> Mamba (2023) -> Mamba-2 (2024) -> Jamba (2024)
```

| 架构 | 核心机制 | 推理速度 |
|------|---------|:---:|
| Transformer | 自注意力 O(n^2) | 1x |
| Mamba | 选择性 SSM | **5x** |
| RWKV | Token-shift RNN | **10-100x** |
| Jamba | SSM + Transformer + MoE | **3x+** |

## 相关链接

- 相关概念: [[液态神经网络LNN]], [[Active Inference]]
- 相关论文: [[Mamba-2312.00752]], [[RWKV-2305.13048]]
- 相关项目: [[mamba]], [[RWKV-LM]]
"""},
    "向量检索RAG": {
        "tags": ["concept", "记忆系统"],
        "aliases": ["RAG", "Retrieval-Augmented Generation"],
        "body": """## 定义

RAG (Retrieval-Augmented Generation) 在 LLM 生成前先检索相关知识，注入到上下文中。

## 本项目多路检索架构

- **路径1**: 向量相似度 Top-K (pgvector, k=10)
- **路径2**: 图谱邻居查询 (Neo4j, depth=2)
- **路径3**: 时间近邻 (最近3天摘要)
- **路径4**: 关键词匹配 (FTS)

-> 重排序 -> 衰减加权 -> 截断(token <= 2000) -> 注入 System Prompt

## 相关链接

- 相关概念: [[知识图谱GraphRAG]], [[记忆衰减模型]]
- 相关论文: [[Memory-AI-Agents-Survey-2512.13564]]
- 相关项目: [[Letta]], [[Mem0]]
"""},
    "BlendShape动画": {
        "tags": ["concept", "角色渲染"],
        "aliases": ["BlendShape", "形变混合", "融合变形"],
        "body": """## 定义

BlendShape 是通过混合多个预定义形状来驱动面部动画的技术。

- ARKit 标准: 52 个 blendshape
- Live2D 使用类似 Parameter ID 系统
- Unity `SkinnedMeshRenderer` 原生支持
- 论文 [[SAiD-2401.08655]] 直接输出 blendshape 系数

## 在本项目中

- Live2D Parameter ID <-> 情绪标签映射
- TTS 音频能量 -> `setMouthOpenY()` 口型驱动
- V2: SAiD 模型 -> ARKit blendshape -> Live2D 参数

## 相关链接

- 相关概念: [[SMPL人体模型]]
- 相关论文: [[SAiD-2401.08655]]
- 相关项目: [[pixi-live2d-display]]
"""},
}

for name, data in concepts.items():
    content = f"""---
tags: [{", ".join(data["tags"])}]
aliases: [{", ".join(data["aliases"])}]
---

# {name}

{data["body"]}
"""
    write_note(os.path.join(BASE, "概念", f"{name}.md"), content)

# ===========================
# DOMAIN NOTES (10)
# ===========================
domains = [
    {
        "num": "01", "name": "Agent编排与多智能体框架",
        "papers": [
            ("Compound-AI-Systems-Survey-2506.04565", "Chen et al.", "2025"),
            ("AI-Agent-Systems-Architectures-2601.01743", "Xu", "2025"),
            ("Multi-Agent-Collaboration-Survey-2501.06322", "Tran et al.", "2025"),
            ("Communication-Centric-MAS-Survey-2502.14321", "Yan et al.", "2025"),
            ("LLM-Agents-Workflows-2406.05804", "", "2024"),
        ],
        "projects": [
            ("LangGraph", "langchain-ai/langgraph", "~25k", "MIT", "有状态图编排，条件边，循环，Checkpointer"),
            ("CrewAI", "crewAIInc/crewAI", "~25k", "MIT", "基于角色的多Agent协作，Role/Task/Tool三层抽象"),
            ("AutoGen", "microsoft/autogen", "~40k", "CC BY 4.0", "微软出品，事件驱动多Agent架构v0.4"),
            ("Dify", "langgenius/dify", "~100k", "Apache-2.0", "低代码AI应用平台，可视化编排"),
            ("MetaGPT", "geekan/MetaGPT", "~45k", "MIT", "SOP驱动，模拟软件公司角色分工"),
        ],
        "recommendation": "LangGraph (主编排器) + CrewAI (多Agent协作场景)",
        "key_insight": "论文2506.04565明确建议编排中心化架构+Agent模块化组合，恰好对应项目的「契约先行+宿主无关」原则",
    },
    {
        "num": "02", "name": "人格系统与情感计算",
        "papers": [
            ("PersLLM-2407.12393", "Zeng et al.", "2024"),
            ("Character-LLM-2310.10158", "Wu et al.", "2023"),
            ("LLM-Agents-Personality-Consistency-2402.02896", "Frisch & Giulianelli", "2024"),
            ("Driving-Generative-Agents-2402.14879", "Klinkert et al.", "2024"),
            ("PersonaChat-1801.07243", "Zhang et al.", "2018"),
        ],
        "projects": [
            ("SillyTavern", "SillyTavern/SillyTavern", "~9k", "AGPL-3.0", "角色卡系统、世界书、情感标记、多后端API"),
            ("OpenCharacter", "community-ai/opencharacter", "~2k", "MIT", "Character.AI开源替代，角色创建/情感推理/世界观管理"),
            ("RisuAI", "kwaroran/RisuAI", "~4k", "MIT", "轻量角色扮演，多模型切换，正则注入"),
        ],
        "recommendation": "PAD三维情感模型 + Big Five人格 + PersLLM方法（增强）",
        "key_insight": "PersLLM提出从prompt模拟到参数嵌入的演进方向，短期prompt工程为主，中长期追踪模型层面人格内化",
    },
    {
        "num": "03", "name": "长期记忆系统",
        "papers": [
            ("Memory-AI-Agents-Survey-2512.13564", "NUS/人大/复旦/北大/Oxford", "2025"),
            ("Memory-Mechanism-LLM-Agents-2404.13501", "", "2024"),
            ("Personalization-RAG-to-Agent-2504.10147", "", "2025"),
            ("EMG-RAG-2409.19401", "", "2024"),
            ("LongMemEval-2410.10813", "", "2024"),
        ],
        "projects": [
            ("Letta", "letta-ai/letta", "~19k", "Apache-2.0", "OS启发的记忆层级（核心/对话/归档），自我编辑"),
            ("Mem0", "mem0ai/mem0", "~42k", "Apache-2.0", "即插即用记忆层，自编辑系统，多后端"),
            ("Zep", "getzep/graphiti", "~19.7k", "Apache-2.0", "时序知识图谱，94.8%检索准确率"),
            ("LangMem", "langchain-ai/langmem", "新", "Apache-2.0", "LangChain官方记忆SDK，三种记忆类型"),
            ("Supermemory", "supermemoryai/supermemory", "~15k", "Apache-2.0", "人脑遗忘曲线模拟+时序KG"),
        ],
        "recommendation": "Letta (结构化记忆核心) + pgvector (向量存储) + Neo4j (图谱 Phase 1+)",
        "key_insight": "Letta基准测试揭示：简单文件系统可达74%记忆准确率，记忆质量更多取决于Agent如何管理记忆而非底层检索机制",
    },
    {
        "num": "04", "name": "语音交互",
        "papers": [
            ("Whisper-2212.04356", "Radford et al.", "2022"),
            ("CosyVoice-2407.05407", "Du et al.", "2024"),
            ("NaturalSpeech-3-2403.03100", "Ju et al.", "2024"),
            ("VoiceBox-2306.15687", "Le et al.", "2023"),
        ],
        "projects": [
            ("whisper.cpp", "ggerganov/whisper.cpp", "~42k", "MIT", "C/C++推理，CPU/GPU/Metal，极低延迟"),
            ("faster-whisper", "SYSTRAN/faster-whisper", "~18k", "MIT", "CTranslate2加速，4x速度提升"),
            ("ChatTTS", "2noise/ChatTTS", "~34k", "CC BY-NC", "对话场景TTS，韵律控制（笑声/停顿）"),
            ("CosyVoice", "FunAudioLLM/CosyVoice", "~12k", "Apache-2.0", "LLM驱动，多语言/零样本/情感/角色扮演"),
            ("fish-speech", "fishaudio/fish-speech", "~18k", "CC BY-NC-SA", "VQ-GAN+LLM，多语言，实时推理"),
            ("Piper TTS", "rhasspy/piper", "~8k", "MIT", "C++超轻量TTS，嵌入式友好"),
        ],
        "recommendation": "ASR: whisper.cpp + faster-whisper | TTS: ChatTTS + CosyVoice + Fish Audio S2",
        "key_insight": "ChatTTS细粒度韵律控制特别适合陪伴场景；CosyVoice角色扮演语音模式可直接用于多角色",
    },
    {
        "num": "05", "name": "角色渲染与动画同步",
        "papers": [
            ("SAiD-2401.08655", "Park & Cho", "2024"),
            ("Emotion-Controllable-Speech-Face-2206.13144", "Daněček et al.", "2023"),
            ("DEEPTalk-2408.06010", "", "2024"),
            ("TALK-Act-2410.10696", "SIGGRAPH Asia", "2024"),
        ],
        "projects": [
            ("pixi-live2d-display", "guansss/pixi-live2d-display", "~1.8k", "MIT", "PixiJS封装的Live2D渲染引擎"),
            ("live2d-widget", "stevenjoezhang/live2d-widget", "~8.7k", "GPL-2.0", "网页Live2D看板娘插件"),
            ("Inochi2D", "Inochi2D/inochi2d", "~1.4k", "BSD-2", "开源2D角色渲染引擎"),
            ("uLipSync", "heihei-Tools/uLipSync", "~500", "MIT", "Unity实时口型同步插件"),
            ("Kalidoface", "yeemachine/kalidoface", "~800", "MIT", "Three.js面部捕捉+Live2D风格渲染"),
        ],
        "recommendation": "pixi-live2d-display（已在用）+ SAiD blendshape映射",
        "key_insight": "SAiD直接输出blendshape系数，与Live2D Parameter ID天然对应。V1用音频能量驱动口型，V2引入SAiD精确viseme同步",
    },
    {
        "num": "06", "name": "动作生成",
        "papers": [
            ("Human-Motion-Generation-Survey-2307.10894", "Zhu et al. / PKU & Huawei", "2024"),
            ("Text-driven-Motion-Generation-2505.09379", "Sahili et al.", "2025"),
            ("Motion-Generation-Survey-2507.05419", "Khani et al.", "2025"),
            ("Motion-Prediction-Reconstruction-2502.15956", "Gang & Wang", "2025"),
            ("DiffSHEG-2401.04747", "Chen et al.", "2024"),
            ("Audio2Photoreal-2401.01885", "Ng et al. / Meta", "2024"),
            ("VLOGGER-2403.08764", "Corona et al.", "2024"),
            ("Stereo-Talker-2410.23836", "", "2024"),
            ("CoCoGesture-2405.16874", "", "2024"),
            ("AMUSE-2312.04466", "Chhatre et al.", "2024"),
            ("MotionLCM-2404.19759", "Dai et al. / 清华", "2024"),
            ("HY-Motion-1.0-Paper", "Tencent", "2025"),
            ("LivePortrait-2407.03168", "Guo et al. / 快手", "2024"),
        ],
        "projects": [
            ("HY-Motion-1.0", "Tencent-Hunyuan/HY-Motion-1.0", "~2.3k", "Tencent", "10亿参数DiT文生动作，SMPL-H骨骼"),
            ("MotionLCM", "Dai-Wenxun/MotionLCM", "~330", "非商用", "ECCV 2024，实时文生动作，1步推理"),
            ("LivePortrait", "KwaiVGI/LivePortrait", "~28k", "MIT", "高效人像动画，单图驱动，实时推理"),
            ("MuseTalk", "TMElyralab/MuseTalk", "~8k", "Apache-2.0", "实时说话头，30+FPS"),
            ("SadTalker", "OpenTalker/SadTalker", "~20k", "MIT", "3D面部系数，音频驱动说话头"),
            ("ComfyUI-MotionDiff", "Fannovel16/ComfyUI-MotionDiff", "~200", "", "SMPL可视化，导出Blender/UE/Unity"),
            ("DigiHuman", "Danial-Kord/DigiHuman", "~477", "", "姿态估计+3D角色动画"),
        ],
        "recommendation": "2D实时: LivePortrait + MuseTalk | 3D离线: HY-Motion-1.0 | 3D实时: MotionLCM + DiffSHEG",
        "key_insight": "与文档推荐的通义万相（离线高保真）不同，LivePortrait和MuseTalk更适合实时日常陪伴。3D方向HY-Motion-1.0工业级成熟度最高",
    },
    {
        "num": "07", "name": "跨设备协同与IoT",
        "papers": [
            ("Edge-Fog-Cloud-Continuum-2407.08543", "Srirama", "2024"),
            ("LLM-Agents-6G-Networks-2401.07764", "Xu et al.", "2024"),
            ("Multi-Device-Experience-Survey", "Wozniak et al.", "2022"),
            ("Distributed-MoA-Edge-2412.21200", "Mitra et al.", "2024"),
        ],
        "projects": [
            ("Mosquitto", "eclipse/mosquitto", "~8.4k", "EPL-2.0", "轻量MQTT Broker，<10MB内存"),
            ("EMQX", "emqx/emqx", "~14k", "Apache-2.0", "企业级可扩展MQTT，1亿并发"),
            ("NATS", "nats-io/nats-server", "~15k", "Apache-2.0", "极高性能pub/sub，JetStream持久化"),
            ("ThingsBoard", "thingsboard/thingsboard", "~17k", "Apache-2.0", "完整IoT平台"),
            ("Mainflux", "mainflux/mainflux", "~1.7k", "Apache-2.0", "轻量IoT平台，多协议"),
        ],
        "recommendation": "Mosquitto (Phase 1-2) -> EMQX (Phase 3规模化)",
        "key_insight": "2407.08543确认MQTT-based数据管线在边缘-云协同中的核心地位。ADR-002路线得到论文支撑",
    },
    {
        "num": "08", "name": "安全与内容审核",
        "papers": [
            ("Constitutional-AI-2212.08073", "Bai et al. / Anthropic", "2022"),
            ("Llama-Guard-2312.06674", "Inan et al. / Meta", "2023"),
            ("Adversarial-Attacks-Aligned-LMs-2307.15043", "Zou et al. / CMU", "2023"),
            ("Red-Teaming-LMs-2209.07858", "Ganguli et al. / Anthropic", "2022"),
            ("Safety-Trustworthiness-LLMs-2312.07585", "", "2024"),
        ],
        "projects": [
            ("NeMo-Guardrails", "NVIDIA/NeMo-Guardrails", "~4k", "Apache-2.0", "可编程对话护栏，Colang DSL"),
            ("LLM-Guard", "protectai/llm-guard", "~2.5k", "MIT", "轻量输入输出扫描，PII检测，越狱检测"),
            ("Guardrails-AI", "guardrails-ai/guardrails", "~5k", "Apache-2.0", "XML规范的结构化输出验证"),
            ("PyRIT", "Azure/PyRIT", "~2k", "MIT", "微软红队测试框架"),
        ],
        "recommendation": "NeMo Guardrails (对话护栏) + LLM Guard (输入预处理) + Llama Guard (高精度分类)",
        "key_insight": "EmotionalSafetyGuard三层架构与NeMo Guardrails的Colang DSL天然匹配。Constitutional AI比RLHF更适合伴侣AI",
    },
    {
        "num": "09", "name": "模型服务与优化",
        "papers": [
            ("Efficient-LLM-Inference-2404.14294", "Miao et al.", "2024"),
            ("LoRA-2106.09685", "Hu et al.", "2021"),
            ("RouteLLM-2406.03654", "Ong et al.", "2024"),
            ("PagedAttention-2309.06180", "Kwon et al.", "2023"),
            ("Speculative-Decoding-2211.17192", "Leviathan et al.", "2023"),
        ],
        "projects": [
            ("vLLM", "vllm-project/vllm", "~42k", "Apache-2.0", "PagedAttention，Continuous Batching，最高吞吐"),
            ("llama.cpp", "ggerganov/llama.cpp", "~75k", "MIT", "纯C/C++ CPU推理，GGUF量化，跨平台"),
            ("Ollama", "ollama/ollama", "~120k", "MIT", "一键本地模型管理，REST API"),
            ("LiteLLM", "BerriAI/litellm", "~18k", "MIT", "100+模型提供商统一API代理，Cost Tracking"),
            ("Unsloth", "unslothai/unsloth", "~25k", "Apache-2.0", "极速LoRA微调，2x速度，50%内存减少"),
            ("TGI", "huggingface/text-generation-inference", "~14k", "Apache-2.0", "HF官方推理服务器"),
        ],
        "recommendation": "LiteLLM (网关) + vLLM (服务端推理) + Unsloth (LoRA微调)",
        "key_insight": "RouteLLM策略可降低40-85%成本同时保持90%+响应质量，直接支持项目的「模型路由分级」策略",
    },
    {
        "num": "10", "name": "非Token替代架构",
        "papers": [
            ("RWKV-2305.13048", "Peng et al.", "2023"),
            ("Mamba-2312.00752", "Gu & Dao", "2023"),
            ("Jamba-2403.19887", "Lieber et al.", "2024"),
            ("xLSTM-2405.04517", "Beck et al.", "2024"),
            ("Liquid-Time-Constant-Networks-2006.04439", "Hasani et al.", "2021"),
        ],
        "projects": [
            ("RWKV-LM", "BlinkDL/RWKV-LM", "~13k", "Apache-2.0", "RWKV全系列模型，CUDA/CPU推理，LoRA支持"),
            ("RWKV-Runner", "josStorer/RWKV-Runner", "~6k", "Apache-2.0", "RWKV一键桌面客户端"),
            ("mamba", "state-spaces/mamba", "~12k", "Apache-2.0", "Mamba-1/2官方实现，高效CUDA kernel"),
            ("mamba-minimal", "johnma2006/mamba-minimal", "~700", "MIT", "Mamba纯PyTorch实现(~200行)"),
            ("pymdp", "infer-actively/pymdp", "~700", "Apache-2.0", "Active Inference Python实现"),
            ("ncps", "mlech26l/ncps", "~1.5k", "Apache-2.0", "Liquid Neural Networks官方实现"),
            ("xLSTM", "NX-AI/xlstm", "~4k", "Apache-2.0", "xLSTM官方实现，HF集成"),
        ],
        "recommendation": "短期: Transformer | 中期: Jamba混合 | 远期: Mamba-2 / RWKV-7",
        "key_insight": "前向架构正在快速追赶Transformer，但生态成熟度仍有差距。建议「并轨追踪」策略",
    },
]

for d in domains:
    papers_md = ""
    for i, (p_id, p_authors, p_year) in enumerate(d["papers"], 1):
        papers_md += f"| {i} | {p_id.replace('-', ' ')} | {p_authors} | {p_year} | [[{p_id}]] |\n"

    projects_md = ""
    for p_name, p_repo, p_stars, p_license, p_features in d["projects"]:
        projects_md += f"| {p_name} | {p_repo} | {p_stars} | {p_license} | {p_features} | [[{p_name}]] |\n"

    content = f"""---
tags: [domain]
papers: {len(d["papers"])}
projects: {len(d["projects"])}
---

# {d["num"]} {d["name"]}

## 推荐方案

**{d["recommendation"]}**

> {d["key_insight"]}

## 论文清单

| # | 论文 | 作者 | 年份 | 详情页 |
|---|------|------|:---:|------|
{papers_md}

## 开源项目

| 项目 | 仓库 | Stars | License | 核心功能 | 详情页 |
|------|------|-------|---------|---------|------|
{projects_md}

## 关联导航

- 返回: [[Home]]
- 核心概念: [[PAD情感模型]] [[OOC检测]] [[LoRA微调]] [[向量检索RAG]] [[BlendShape动画]] [[状态空间模型SSM]]
- 项目文档: [[技术选型调研与对比建议报告]]
"""
    write_note(os.path.join(BASE, f"{d['num']}-{d['name']}", f"{d['num']}-{d['name']}.md"), content)

# ===========================
# PAPER STUB NOTES (with backlinks to domains)
# ===========================
# Map paper IDs to their domain
paper_domain_map = {}
for d in domains:
    for p_id, p_authors, p_year in d["papers"]:
        paper_domain_map[p_id] = {
            "domain_num": d["num"],
            "domain_name": d["name"],
            "authors": p_authors,
            "year": p_year,
        }

for p_id, info in paper_domain_map.items():
    # Extract arXiv ID from the paper ID (last part)
    parts = p_id.rsplit("-", 1)
    arxiv_id = parts[-1] if len(parts) > 1 else ""
    content = f"""---
tags: [paper]
arxiv: "{arxiv_id}"
year: {info["year"]}
authors: "{info["authors"]}"
domain: "{info["domain_num"]}-{info["domain_name"]}"
---

# {p_id.replace("-", " ")}

## 元数据

| 属性 | 值 |
|------|-----|
| **arXiv ID** | {arxiv_id} |
| **发表年份** | {info["year"]} |
| **作者** | {info["authors"]} |

## 所属技术领域

- [[{info['domain_num']}-{info['domain_name']}]]

## 相关链接

- 返回领域: [[{info['domain_num']}-{info['domain_name']}]]
- 返回首页: [[Home]]
"""
    write_note(os.path.join(BASE, info["domain_num"] + "-" + info["domain_name"], "papers", f"{p_id}.md"), content)

# ===========================
# PROJECT STUB NOTES (with backlinks to domains)
# ===========================
project_domain_map = {}
for d in domains:
    for p_name, p_repo, p_stars, p_license, p_features in d["projects"]:
        project_domain_map[p_name] = {
            "domain_num": d["num"],
            "domain_name": d["name"],
            "repo": p_repo,
            "stars": p_stars,
            "license": p_license,
            "features": p_features,
        }

for p_name, info in project_domain_map.items():
    content = f"""---
tags: [project]
repo: "{info["repo"]}"
stars: {info["stars"]}
license: "{info["license"]}"
domain: "{info["domain_num"]}-{info["domain_name"]}"
---

# {p_name}

## 元数据

| 属性 | 值 |
|------|-----|
| **仓库** | {info["repo"]} |
| **Stars** | {info["stars"]} |
| **License** | {info["license"]} |

## 核心功能

{info["features"]}

## 所属技术领域

- [[{info['domain_num']}-{info['domain_name']}]]

## 相关链接

- 返回领域: [[{info['domain_num']}-{info['domain_name']}]]
- 返回首页: [[Home]]
"""
    write_note(os.path.join(BASE, info["domain_num"] + "-" + info["domain_name"], "projects", f"{p_name}.md"), content)

print(f"DONE: 10 domain notes + {len(concepts)} concept notes + {len(paper_domain_map)} paper stubs + {len(project_domain_map)} project stubs")
print(f"Vault path: {BASE}")
