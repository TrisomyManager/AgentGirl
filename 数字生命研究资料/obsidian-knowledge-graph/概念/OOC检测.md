---
tags: [concept, 人格系统, 安全]
aliases: [Out-of-Character, 角色越界检测]
---

# OOC检测

## 定义

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

