---
tags: [concept, 安全]
aliases: [CAI, 宪法AI, 宪法原则驱动对齐]
---

# Constitutional AI

## 定义

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

