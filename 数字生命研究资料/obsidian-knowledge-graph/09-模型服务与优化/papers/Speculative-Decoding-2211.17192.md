---
tags: [paper]
arxiv: "2211.17192"
year: 2023
authors: "Yaniv Leviathan et al. (Google)"
venue: "ICML 2023"
---

# Fast Inference from Transformers via Speculative Decoding

> **arXiv**: [2211.17192](https://arxiv.org/abs/2211.17192)
> **年份**: 2023 | **作者**: Yaniv Leviathan et al. (Google) | **收录**: ICML 2023

## 核心贡献

提出投机解码方法：小模型快速生成草稿，大模型并行验证。在保持分布一致性的情况下实现2-3x加速。后续Medusa、Eagle等延续此方向。

## 对项目的适用性

中高——若使用本地模型部署且有延迟要求，投机解码可显著改善TTFT。

## 相关链接

- 所属领域: [[09-模型服务与优化]]
- 返回首页: [[Home]]
