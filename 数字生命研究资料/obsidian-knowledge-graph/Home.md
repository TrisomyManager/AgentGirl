---
tags: [MOC, index]
---

# 水母娘「Fensy」— 技术选型知识图谱

> 基于《技术选型调研与对比建议报告》构建的 Obsidian 知识图谱。
> 覆盖 10 大技术领域、60+ 论文、50+ 开源项目、20+ 核心概念。

## 技术领域入口

| # | 领域 | 入口笔记 | 论文 | 项目 |
|---|------|---------|:--:|:--:|
| 1 | Agent 编排与多智能体框架 | [[01-Agent编排与多智能体框架]] | 5 | 5 |
| 2 | 人格系统与情感计算 | [[02-人格系统与情感计算]] | 5 | 4 |
| 3 | 长期记忆系统 | [[03-长期记忆系统]] | 5 | 5 |
| 4 | 语音交互 (ASR/TTS) | [[04-语音交互]] | 4 | 6 |
| 5 | 角色渲染与动画同步 | [[05-角色渲染与动画同步]] | 4 | 5 |
| 6 | 动作生成 (2D/3D) | [[06-动作生成]] | 12 | 7 |
| 7 | 跨设备协同与 IoT | [[07-跨设备协同与IoT]] | 4 | 5 |
| 8 | 安全与内容审核 | [[08-安全与内容审核]] | 5 | 4 |
| 9 | 模型服务与优化 | [[09-模型服务与优化]] | 5 | 6 |
| 10 | 非Token替代架构 | [[10-非Token替代架构]] | 5 | 7 |
| 11 | 整体化AI陪伴项目(新) | [[11-整体化AI陪伴项目]] | — | 8 |

## 核心概念速览

- [[PAD情感模型]] — 三维情感空间
- [[Big Five人格模型]] — OCEAN 五大人格
- [[OOC检测]] — 角色越界检测
- [[向量检索RAG]] — 检索增强生成
- [[知识图谱GraphRAG]] — 图增强检索
- [[记忆衰减模型]] — Ebbinghaus 遗忘曲线
- [[BlendShape动画]] — 面部形变混合动画
- [[SMPL人体模型]] — 参数化3D人体
- [[LoRA微调]] — 参数高效微调
- [[Constitutional AI]] — 宪法原则AI对齐
- [[Prompt注入防御]] — LLM安全防护
- [[投机解码]] — 推理加速
- [[状态空间模型SSM]] — Mamba/RWKV 理论基础
- [[Active Inference]] — 主动推理自由能原理
- [[液态神经网络LNN]] — Liquid Neural Networks

## 选型决策矩阵

| 领域 | 推荐主线 | 备选方案 | 远期方向 |
|------|---------|---------|---------|
| Agent编排 | [[LangGraph]] | [[CrewAI]] / [[AutoGen]] | 混合编排 |
| 人格系统 | PAD + Big5 + 角色卡 | PersLLM参数嵌入 | 模型级人格内化 |
| 长期记忆 | [[Letta]] + pgvector | [[Mem0]] | Neo4j图谱 |
| ASR | [[whisper.cpp]] + faster-whisper | 商业API | 端侧流式 |
| TTS | [[ChatTTS]] + [[CosyVoice]] | [[Fish Audio S2]] | 本地VITS |
| 角色渲染 | [[pixi-live2d-display]] | Inochi2D | Unity 3D |
| 2D动作 | [[LivePortrait]] + [[MuseTalk]] | 通义万相 | 全身动画 |
| 3D动作 | [[HY-Motion-1.0]] + [[MotionLCM]] | [[DiffSHEG]] | 实时全身 |
| 跨设备 | [[Mosquitto]] → [[EMQX]] | NATS | 分布式集群 |
| 安全审核 | [[NeMo-Guardrails]] + [[LLM-Guard]] | [[Llama Guard]] | Constitutional AI |
| 模型服务 | [[LiteLLM]] + [[vLLM]] + [[Unsloth]] | [[Ollama]] | RouteLLM路由 |
| 前沿架构 | [[RWKV-LM]] / [[mamba]] | Jamba混合 | Active Inference |

## 项目文档链接

- [[技术选型调研与对比建议报告]]
- [[陪伴类AI智能体-完整项目架构]]

---

*Graph View 提示：在 Obsidian 中开启图谱视图，按 tags 筛选即可看到 论文/项目/概念 三大聚类*
