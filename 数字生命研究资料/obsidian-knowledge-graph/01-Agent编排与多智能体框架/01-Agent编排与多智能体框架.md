---
tags: [domain]
papers: 5
projects: 5
---

# 01 Agent编排与多智能体框架

## 推荐方案

**LangGraph (主编排器) + CrewAI (多Agent协作场景)**

> 论文2506.04565明确建议编排中心化架构+Agent模块化组合，恰好对应项目的「契约先行+宿主无关」原则

## 论文清单

| # | 论文 | 作者 | 年份 | 详情页 |
|---|------|------|:---:|------|
| 1 | Compound AI Systems Survey 2506.04565 | Chen et al. | 2025 | [[Compound-AI-Systems-Survey-2506.04565]] |
| 2 | AI Agent Systems Architectures 2601.01743 | Xu | 2025 | [[AI-Agent-Systems-Architectures-2601.01743]] |
| 3 | Multi Agent Collaboration Survey 2501.06322 | Tran et al. | 2025 | [[Multi-Agent-Collaboration-Survey-2501.06322]] |
| 4 | Communication Centric MAS Survey 2502.14321 | Yan et al. | 2025 | [[Communication-Centric-MAS-Survey-2502.14321]] |
| 5 | LLM Agents Workflows 2406.05804 |  | 2024 | [[LLM-Agents-Workflows-2406.05804]] |


## 开源项目

| 项目 | 仓库 | Stars | License | 核心功能 | 详情页 |
|------|------|-------|---------|---------|------|
| LangGraph | langchain-ai/langgraph | ~25k | MIT | 有状态图编排，条件边，循环，Checkpointer | [[LangGraph]] |
| CrewAI | crewAIInc/crewAI | ~25k | MIT | 基于角色的多Agent协作，Role/Task/Tool三层抽象 | [[CrewAI]] |
| AutoGen | microsoft/autogen | ~40k | CC BY 4.0 | 微软出品，事件驱动多Agent架构v0.4 | [[AutoGen]] |
| Dify | langgenius/dify | ~100k | Apache-2.0 | 低代码AI应用平台，可视化编排 | [[Dify]] |
| MetaGPT | geekan/MetaGPT | ~45k | MIT | SOP驱动，模拟软件公司角色分工 | [[MetaGPT]] |


## 关联导航

- 返回: [[Home]]
- 核心概念: [[PAD情感模型]] [[OOC检测]] [[LoRA微调]] [[向量检索RAG]] [[BlendShape动画]] [[状态空间模型SSM]]
- 项目文档: [[技术选型调研与对比建议报告]]
