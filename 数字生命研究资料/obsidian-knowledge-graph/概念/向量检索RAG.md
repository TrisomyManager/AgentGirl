---
tags: [concept, 记忆系统]
aliases: [RAG, Retrieval-Augmented Generation]
---

# 向量检索RAG

## 定义

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

