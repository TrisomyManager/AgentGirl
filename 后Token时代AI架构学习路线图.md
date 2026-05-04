---

# 后Token时代AI架构学习路线图

## 文档信息

| 项目 | 内容 |
|------|------|
| **文档版本** | v1.0 |
| **制定日期** | 2026-04-20 |
| **总学习时长** | 240小时（约3-4个月） |
| **目标人群** | 有Unity/MR开发经验，希望深入AI底层架构的开发者 |
| **核心目标** | 构建非Token化、低算力、持续运行的数字生命系统 |
| **前置要求** | Python基础、Unity/C#开发经验、线性代数与概率论入门 |

---

## 学习路径总览

```mermaid
graph LR
    A[第一阶段: 本地LLM替代<br/>80小时] --> B[第二阶段: 液态神经网络<br/>60小时]
    B --> C[第三阶段: 主动推理架构<br/>100小时]
    
    A -->|产出| A1[Unity离线NPC对话系统]
    B -->|产出| B1[情感驱动NPC原型]
    C -->|产出| C1[自驱动数字生命"汐"]
```

| 阶段 | 时长 | 核心技术 | 产出物 |
|------|------|---------|--------|
| **第一阶段** | 80小时 | RWKV/Mamba + Unity Sentis + ONNX | 离线运行的Unity NPC对话系统 |
| **第二阶段** | 60小时 | Liquid Neural Networks + PAD情感模型 | 6-10神经元实时情感控制NPC |
| **第三阶段** | 100小时 | Active Inference (pymdp) + 记忆整合 | 自驱动数字生命"汐"完整系统 |

---

## 第一阶段：本地LLM替代与Unity集成（80小时）

**阶段目标**：在Unity中运行无需GPU、内存占用<1GB的本地语言模型，完全替代云端LLM API。

| 小时 | 任务模块 | 具体任务 | 产出物 | 核心信息源 |
|------|---------|---------|--------|-----------|
| **1-2** | 环境准备 | 安装Python 3.10、CUDA Toolkit（可选）、Unity 2022.3 LTS | 配置完成的开发环境 | [RWKV README](https://github.com/BlinkDL/RWKV-LM#quick-start) 的 `pip install rwkv` 部分 |
| **3-4** | 理论速通 | 理解RNN vs Transformer复杂度差异（O(n) vs O(n²)） | 手绘计算复杂度对比图 | 知乎[苏剑林：Transformer升级之路](https://spaces.ac.cn/archives/9661) 第1-3节 |
| **5-8** | 模型部署 | 下载并运行RWKV-4-Raven-3B（最小可用模型） | 本地成功生成文本的截图 | [RWKV pip文档](https://pypi.org/project/rwkv/) 示例代码块 |
| **9-12** | 模型量化 | 使用INT8/INT4量化减少显存占用 | 量化后的`.pth`文件（<500MB） | [RWKV-CUDA量化指南](https://github.com/BlinkDL/RWKV-LM/blob/main/RWKV-v4/cuda/) `quant.py` 文件注释 |
| **13-16** | 格式转换 | 将RWKV转为ONNX格式 | `rwkv.onnx` 文件 | [RWKV-ONNX项目](https://github.com/RWKV/RWKV-onnx) 的 `export.py` |
| **17-24** | Unity集成 | 使用Unity Sentis（原Barracuda）加载ONNX模型 | Unity场景中能输出文本的UI | [Unity Sentis文档](https://docs.unity3d.com/Packages/com.unity.sentis@1.2/manual/index.html) "Load a model" 章节 + [RWKV-Unity示例](https://github.com/RWKV/RWKV-unity) |
| **25-32** | 状态管理 | 实现RWKV的隐藏状态（State）持久化 | 可保存/加载对话上下文的系统 | [RWKV-Runner源码](https://github.com/RWKV/RWKV-Runner) 中 `rwkv_cpp_model.py` 的 `save/load state` 方法 |
| **33-40** | 流式优化 | 实现分块生成（Chunked Generation） | 无卡顿的流式文本输出 | [RWKV-Stable源码](https://github.com/AtamanC13/rwkv-stable) 的 `generate` 函数 |
| **41-48** | 多模态闭环 | 接入Whisper（语音转文本）→RWKV→Piper TTS（文本转语音） | 语音对话闭环 | [Whisper.cpp](https://github.com/ggerganov/whisper.cpp) Unity绑定 + [Piper TTS](https://github.com/rhasspy/piper) |
| **49-56** | 性能压测 | 在Android/iOS真机测试 | 移动端性能报告（FPS/内存/耗电） | Unity Profiler + [Unity ML Agents性能指南](https://unity.com/products/machine-learning-agents) |
| **57-64** | 替代方案 | 对比测试Mamba-370M与RWKV-3B | 速度/质量对比表格 | [Mamba GitHub](https://github.com/state-spaces/mamba) `eval.py` + [mamba.py简化实现](https://github.com/johnma2006/mamba-minimal) |
| **65-72** | 技术选型 | 根据移动端表现选择主架构 | 技术选型文档 | 自行对比测试数据 |
| **73-80** | 阶段项目 | 整合为**离线运行的Unity NPC对话系统** | 可演示的Unity工程文件 | 整合前述所有代码 |

**阶段检查点**：第80小时必须能在Unity中离线运行RWKV并生成连贯对话文本。

---

## 第二阶段：Liquid Neural Networks实时控制（60小时）

**阶段目标**：用6-10个神经元实现NPC的实时情感状态机，替代传统行为树。

| 小时 | 任务模块 | 具体任务 | 产出物 | 核心信息源 |
|------|---------|---------|--------|-----------|
| **81-88** | 数学基础 | 学习常微分方程（ODE）与欧拉法数值解 | 手写LNN前向传播公式 | [LNN论文](https://arxiv.org/abs/2006.04439) 第3.1节 "Liquid Time-Constant Networks" + 3Blue1Brown[微分方程系列](https://www.youtube.com/watch?v=p_di4Zn4wz4) |
| **89-96** | 代码实现 | 用PyTorch从零实现LNN Cell（Liquid Time-Constant Cell） | 可运行的`liquid_cell.py` | [ncps库教程](https://github.com/mlech26l/ncps) `examples/` 目录下的 `simple_ltc.py` |
| **97-104** | 训练入门 | 用LNN预测正弦波（时序预测入门任务） | 训练好的模型文件 | [ncps README](https://github.com/mlech26l/ncps#usage) Quick Start 代码 |
| **105-112** | Unity移植 | 将LNN权重导出为JSON，用C#实现前向传播 | Unity中的`LiquidNetwork.cs` | [Unity ML Agents神经网络C#实现](https://github.com/Unity-Technologies/ml-agents/blob/develop/com.unity.ml-agents/Runtime/Inference/Brain.cs) 参考其矩阵运算 |
| **113-120** | 情感建模 | 设计三维情感空间（愉悦/唤醒/支配） | 情感状态机代码 | [PAD情感模型论文](https://en.wikipedia.org/wiki/PAD_emotional_state_model) + [Russell's Circumplex Model](https://en.wikipedia.org/wiki/Emotion_classification) |
| **121-128** | 实时控制 | LNN输出驱动NPC移动/动画参数 | NPC能对环境变化做出连续情感反应 | [Unity ML Agents Actuator](https://docs.unity3d.com/Packages/com.unity.ml-agents@2.0/manual/Actuators.html) 文档 |
| **129-136** | 闭环系统 | 传感器输入（玩家距离/语音情绪）→LNN→行为输出 | 完整的感知-情感-行为闭环 | 自行设计状态机，参考[Active Inference简单版](https://pymdp-rtd.readthedocs.io/en/latest/) |
| **137-140** | 阶段项目 | 整合为**情感驱动的NPC**（无LLM，纯LNN） | 可演示的Unity场景 | 整合LNN控制代码 |

**阶段检查点**：第140小时必须实现LNN驱动的情感变化可视化（如NPC在玩家靠近时表现出"紧张"的连续过渡动画）。

---

## 第三阶段：Active Inference自驱动架构（100小时）

**阶段目标**：构建无需外部训练数据、具备自我驱动能力的数字生命原型"汐"。

| 小时 | 任务模块 | 具体任务 | 产出物 | 核心信息源 |
|------|---------|---------|--------|-----------|
| **141-148** | 理论奠基 | 学习自由能原理（Free Energy Principle）入门 | 手写生成模型（Generative Model）框图 | [Friston教程](https://www.fil.ion.ucl.ac.uk/~karl/A%20free%20energy%20principle%20for%20the%20brain.pdf) 第1-2节 + [Active Inference极简教程](https://medium.com/@solopchuk/tutorial-on-active-inference-1762971333c) |
| **149-156** | 数学工具 | 掌握变分推断（VI）与KL散度计算 | Python实现VI | [pymdp教程](https://pymdp-rtd.readthedocs.io/en/latest/notebooks/active_inference_from_scratch.html) 前3节 |
| **157-168** | 框架学习 | 掌握pymdp核心类（Agent、Control、Inference） | 跑通pymdp的"Grid World"示例 | [pymdp官方文档](https://pymdp-rtd.readthedocs.io/en/latest/) Tutorials 1-3 |
| **169-176** | 感知设计 | 为"汐"设计生成模型（观察→隐藏状态→情感） | 针对水母娘的A矩阵（似然矩阵） | [Designing Agent](https://pymdp-rtd.readthedocs.io/en/latest/notebooks/designing_an_agent.html) 章节 |
| **177-184** | 偏好设计 | 定义"汐"的偏好（C矩阵），即她"想要什么" | 偏好矩阵代码 | [C矩阵设计指南](https://pymdp-rtd.readthedocs.io/en/latest/notebooks/pymdp_basics.html) |
| **185-192** | 行动选择 | 实现策略推断（Policy Inference）选择行为 | 能主动寻找玩家的NPC | [Action Perception Loop](https://pymdp-rtd.readthedocs.io/en/latest/notebooks/active_inference_from_scratch.html) 代码段 |
| **193-200** | 记忆整合 | 结合RWKV（陈述性记忆）+ LNN（情感状态）+ pymdp（决策层） | 三层架构图与接口代码 | 自行设计架构，参考[Memory in AI综述](https://arxiv.org/abs/2309.02427) |
| **201-208** | 睡眠机制 | 实现"梦境"模式（离线参数更新与记忆巩固） | 夜间自动运行的记忆巩固脚本 | [Memory Consolidation论文](https://www.nature.com/articles/nn1106) 简化实现 |
| **209-220** | 涌现测试 | 观察长期运行后的自发行为 | 24小时运行日志与行为分析报告 | 自行记录数据 |
| **221-240** | 最终项目 | 整合为**"汐"的完整数字生命系统** | 开源GitHub仓库 + 技术博客 | 整合所有阶段代码 |

**阶段检查点**：第200小时必须实现pymdp的主动决策（NPC在没有玩家输入时主动探索环境）；第240小时完成可演示的完整系统。

---

## 核心资源索引

### 一、GitHub仓库（按阶段分类）

**第一阶段：本地LLM**
```bash
# 必须克隆的仓库
git clone https://github.com/BlinkDL/RWKV-LM.git           # RWKV主仓库
git clone https://github.com/RWKV/RWKV-Runner.git          # 部署参考与状态管理
git clone https://github.com/johnma2006/mamba-minimal.git   # 简化版Mamba（学习用）
git clone https://github.com/state-spaces/mamba.git         # Mamba官方实现
git clone https://github.com/RWKV/RWKV-onnx.git             # ONNX导出工具
git clone https://github.com/RWKV/RWKV-unity.git            # Unity集成参考
git clone https://github.com/ggerganov/whisper.cpp.git      # 语音转文本
git clone https://github.com/rhasspy/piper.git              # 本地TTS
```

**第二阶段：液态神经网络**
```bash
pip install ncps  # 官方库
# 学习代码：https://github.com/mlech26l/ncps/tree/master/tutorials
git clone https://github.com/mlech26l/ncps.git              # LNN官方实现
```

**第三阶段：主动推理**
```bash
pip install inferactively-pymdp  # 官方库
# 教程：https://pymdp-rtd.readthedocs.io/en/latest/notebooks/
```

### 二、关键论文清单

| 论文 | 作者 | 年份 | 学习阶段 | 获取链接 |
|------|------|------|---------|---------|
| RWKV: Reinventing RNNs for the Transformer Era | Peng et al. | 2023 | 第一阶段 | arXiv:2305.13048 |
| Mamba: Linear-Time Sequence Modeling with Selective State Spaces | Gu & Dao | 2023 | 第一阶段 | arXiv:2312.00752 |
| Liquid Time-Constant Networks | Hasani et al. | 2021 | 第二阶段 | arXiv:2006.04439 |
| A Path Towards Autonomous Machine Intelligence | LeCun | 2022 | 第三阶段 | Meta AI白皮书 |
| Active Inference: The Free Energy Principle in Mind, Brain, and Behavior | Parr et al. | 2022 | 第三阶段 | MIT Press |
| Memory Consolidation and the Organization of Remote Episodic Memories | Nadel et al. | 2006 | 第三阶段 | Nature Neuroscience |

### 三、视频教程

| 频道/视频 | 内容 | 时长 | 对应阶段 |
|-----------|------|------|---------|
| **Artem Kirsanov** - [Active Inference](https://www.youtube.com/watch?v=0bylw29V_DQ) | 可视化自由能原理 | 1.5小时 | 第三阶段 |
| **Bycloud** - [Mamba Architecture](https://www.youtube.com/watch?v=8Qf-G1xBqYc) | 状态空间模型详解 | 1小时 | 第一阶段 |
| **AI Explained** - RWKV系列 | RWKV概念理解 | 2小时 | 第一阶段 |
| **3Blue1Brown** - [微分方程](https://www.youtube.com/watch?v=p_di4Zn4wz4) | ODE与欧拉法 | 1小时 | 第二阶段 |
| **李宏毅** - [RNN与LSTM](https://www.youtube.com/watch?v=xCGidAeyS4M) | 理解RWKV基础 | 2小时 | 第一阶段 |

### 四、中文关键博客

| 作者 | 文章/系列 | 对应阶段 | 预计阅读时间 |
|------|---------|---------|-------------|
| **苏剑林** | [《RWKV：在Transformer时代重塑RNN》](https://spaces.ac.cn/archives/9708) | 第一阶段 | 4小时 |
| **苏剑林** | [《Mamba：线性时间序列建模》](https://spaces.ac.cn/archives/9172) | 第一阶段 | 3小时 |
| **苏剑林** | Transformer升级之路系列 | 第一阶段 | 累计8小时 |

---

## 执行指南

### 每日学习节奏

**工作日（2小时/天）**
- 0.5小时：阅读论文/文档（理论输入）
- 1小时：Coding实践（模型部署/架构实现）
- 0.5小时：记录技术博客或笔记（复盘输出）

**周末（6小时/天）**
- 上午3小时：攻克本周难点（如ONNX导出调试、C#矩阵运算移植）
- 下午3小时：阶段项目整合与测试

### 关键检查点（Checkpoint）

| 时间节点 | 必须完成的验证标准 | 未通过补救措施 |
|---------|-------------------|--------------|
| **第80小时** | Unity中离线运行RWKV生成10轮连贯对话 | 回退至ONNX导出环节，检查Sentis版本兼容性 |
| **第140小时** | LNN驱动的NPC展现3种以上连续情感过渡 | 检查LNN时间常数参数（tau）设置，参考ncps示例调参 |
| **第200小时** | NPC在无输入时主动移动/探索（非随机） | 检查pymdp的C矩阵（偏好）是否正确定义 |
| **第240小时** | 系统连续运行24小时无内存泄漏 | 使用Unity Memory Profiler检查RWKV State释放逻辑 |

### 推荐工具链

| 用途 | 工具 | 版本/说明 |
|------|------|----------|
| Python环境 | Anaconda/Miniconda | Python 3.10 |
| Unity版本 | Unity 2022.3 LTS | 必须包含Sentis包 |
| 模型转换 | ONNX Runtime + Unity Sentis | Sentis 1.2+ |
| 代码编辑 | VS Code + Python/Jupyter插件 | 用于算法原型 |
| 性能分析 | Unity Profiler + Memory Profiler | 移动端必需 |
| 笔记管理 | Notion/Obsidian | 记录每日学习日志 |
| 论文管理 | Zotero | 管理arXiv论文PDF |

---

## 附录：术语速查表

| 术语 | 解释 | 首次出现阶段 |
|------|------|-------------|
| **Token** | 大模型的最小处理单元（如一个汉字或子词） | 第一阶段 |
| **RWKV** | Receptance Weighted Key Value，线性复杂度的RNN架构 | 第一阶段 |
| **Mamba** | 基于状态空间模型（SSM）的线性序列模型 | 第一阶段 |
| **ONNX** | 开放神经网络交换格式，跨平台部署标准 | 第一阶段 |
| **LNN** | Liquid Neural Network，连续时间动态神经网络 | 第二阶段 |
| **ODE** | Ordinary Differential Equation，常微分方程 | 第二阶段 |
| **PAD** | Pleasure-Arousal-Dominance，三维情感模型 | 第二阶段 |
| **Active Inference** | 主动推理，基于自由能原理的自驱动智能框架 | 第三阶段 |
| **FEP** | Free Energy Principle，自由能原理（Karl Friston提出） | 第三阶段 |
| **pymdp** | Python库，实现主动推理的马尔可夫决策过程 | 第三阶段 |
| **A矩阵** | 似然矩阵（Likelihood），观察与隐藏状态的映射 | 第三阶段 |
| **C矩阵** | 偏好矩阵（Preference），定义Agent的目标 | 第三阶段 |

---