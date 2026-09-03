# 8.1 设计稿：LLM 分段 → TTS 并行流式管线

> 来源：路线图 Phase 8.1，借鉴 [dlp3d-ai/orchestrator](https://github.com/dlp3d-ai/orchestrator) 的
> Aggregator 模式（长回复切句 → TTS/Reaction 并行 → 聚合后按序下发）。
> 状态：设计稿 v1，待评审后实施。

---

## 1. 现状摸底（2026-09-03）

项目里存在**两条语音链路**，串行点不同：

### 链路 A：文字聊天 + 语音播报（SSE）

`/orchestrator/turn/stream` → `stream_assistant_response()`
（`core_orchestrator/state_machine.py:1613`）

```
LLM token 流 ──(边流边拼)──► 全文 assistant_message
                                 │
                                 ▼   ← 串行点：全文生成完才开始 TTS
                    node_synthesize_voice()（state_machine.py:1205）
                    POST /voice/synthesize（全文一次性合成）
                                 │
                                 ▼
                    单个 mp3 → /static/voice/xxx.mp3 → 前端整段播放
```

- 首音延迟 ≈ LLM 全文生成时间 + 全文 TTS 合成时间，长回复时不可接受。
- 情绪参数来自 `_derive_emotion()`（规则法），且要全文生成完才计算。
- 语音请求契约：`VoiceSynthesisRequest`（shared_contracts），
  合成实现：`voice_layer/tts.py` 的 `TTSClient.synthesize()`。

### 链路 B：实时语音对话（WebSocket）

`/voice/stream` → `voice_layer/providers/realtime/local_realtime.py`

- **已有句子级分段**：`_SENTENCE_END = re.compile(r"[。！？!?\n]|[，、,;；](?=.{6,})")`
  （`local_realtime.py:24`），每凑够一句就发 `assistant_sentence_start` 并合成播放。
- **但分段≠并行**：`await self._speak(sentence)`（`local_realtime.py:179`）阻塞在
  token 消费循环里——句子 N 的 TTS 合成与发送没结束，就不继续读 LLM 流、
  更不预合成句子 N+1。句间静音 = 下一句的完整 TTS 延迟。
- 打断能力已有雏形（`_on_interrupt` / `_cancel_turn`），是 8.2 的现成地基。

### TTS 提供商能力矩阵（`voice_layer/tts.py`）

| Provider | `synthesize()`（全文 mp3） | `synthesize_pcm_stream()` | 真实流式？ |
|----------|--------------------------|---------------------------|-----------|
| openai / siliconflow | ✅ | ✅ 原生 PCM 流 | ✅ |
| xiaomi_mimo | ✅ | ✅（取全量再转 PCM） | ❌ 伪流式 |
| dashscope | ✅（返回托管 URL） | ✅（取全量再转 PCM） | ❌ 伪流式 |
| fish_audio | ✅ | ✅（取全量再转 PCM） | ❌ 伪流式 |
| chattts | ✅ | ❌ | ❌ |

结论：即便提供商不支持流式，**句子级分段本身就能把单段合成耗时降下来**，
分段对所有 provider 都有收益；原生 PCM 流式 provider 收益最大。

### 可复用资产

- 分句正则 `_SENTENCE_END`（local_realtime.py）→ 提升为共享分段器。
- `shared_runtime.llm_client.chunk_text_stream`（确定性回复的伪流式工具）。
- `TTSClient.synthesize_pcm_stream()`（链路 B 已在用）。
- 现成的延迟日志：`tts.synthesize.end` 带 `latency_ms`，可直接复用做分段级指标。

---

## 2. 目标与非目标

**目标**

1. 链路 A 首音延迟（TTFA）从「全文 LLM + 全文 TTS」降到「首句 LLM + 首句 TTS」，
   预计长回复场景下降 50% 以上。
2. 链路 B 消除句间静音：句子 N 播放期间并行预合成句子 N+1。
3. 不破坏现有契约：`/orchestrator/turn/stream` 的 `token`/`done` 事件保持不变，
   纯增量扩展；`node_synthesize_voice` 保留为降级路径。

**非目标（本阶段不做）**

- 打断处理与自适应缓冲（→ 8.2）。
- 逐句情绪打标（→ 8.3，先用轮次级情绪）。
- 音频/表情时间轴对齐（→ 8.4）。
- 传输协议换 Protobuf（→ 8.5）。

---

## 3. 方案设计

### 3.1 新组件：流式语音聚合器 `StreamingVoiceAggregator`

位置：`core_orchestrator/streaming_voice.py`（新文件），对应 DLP3D 的
`tts_reaction_aggregator` 角色。仅聚合，不直接持有 HTTP 客户端以外的状态。

```
LLM token 流
    │
    ▼
SentenceSegmenter（分句器，复用 _SENTENCE_END 规则）
    │  每产出一个句子 → (seq, text)
    ▼
TTS Scheduler（asyncio，有界并发，保序交付）
    │  每个句子一个 task：POST /voice/synthesize（按句）
    ▼
SSE 事件流：按 seq 顺序 emit voice_segment
```

三个部件的职责：

**① SentenceSegmenter**（纯函数式，可单测）

- 输入 token，缓冲到命中句末标点且句长 ≥ `min_sentence_chars`（默认 8）才切出，
  避免「嗯。」这种碎片句单独合成。
- 句子上限 `max_sentence_chars`（默认 80）：超长强制切分，防止某句 TTS 成为长尾。
- 流结束时 flush 尾句。
- 把 `_SENTENCE_END` 从 `local_realtime.py` 移到
  `shared_runtime/text_segmenter.py`（契约层不放逻辑，放 runtime 层），
  realtime provider 改为 import，行为不变。

**② TTS Scheduler**

- 有界并发（默认 2）：分句后立刻起跑，不等前一句完成。
- **保序交付**：task 完成顺序乱序，但 emit 按 seq 严格递增——
  内部维护 `dict[seq, result]` + `next_emit_seq` 游标（DLP3D 的 ordered
  aggregator 思路）。
- 单句失败：emit `voice_segment_error`（带 seq 和原因），**不中断后续句子**；
  前端跳过该段即可，文字流不受影响。
- 首句特殊处理：一旦首句切出立即合成，这是 TTFA 的关键路径。

**③ SSE 协议扩展（增量，向后兼容）**

`/orchestrator/turn/stream` 新增事件：

```json
{"event": "voice_segment", "seq": 0, "text": "……", "audio_url": "/static/voice/x.mp3", "duration_ms": 1230}
{"event": "voice_segment_error", "seq": 1, "error": "..."}
{"event": "voice_done", "segments": 3, "total_duration_ms": 4020}
```

- 老前端忽略未知事件即可，行为退化为现状（等 `done` 里的 `voice_url`）。
- `done` 事件继续携带整段 `voice_url` 吗？——**不携带**。开启流式语音时
  `node_synthesize_voice` 跳过（避免重复合成扣费），`done` 中
  `voice_url=None` + 新增 `voice_mode: "segmented"` 字段标记。
- 前端（`apps/web`）维护 `seq → audio` 队列顺序播放；全部段到齐后可本地拼单文件
  供「重听整段」用。

### 3.2 链路 A 改造点（`state_machine.py`）

在 `stream_assistant_response` 的 LLM 流式分支中：

1. token 除了 yield 给 SSE、append 到 accumulated，同时喂给
   `StreamingVoiceAggregator.feed(token)`。
2. 触发条件：`tc.request_voice_reply or tc.has_voice` 且 `settings.enable_voice`
   且新增配置 `settings.enable_streaming_tts`（默认 false，灰度开关）。
3. LLM 流结束后 `await aggregator.finish()`——此时大部分句子已合成完，
   只需 drain 尾部。
4. 情绪参数：用轮次级 `emotion_state`（LLM 生成前的既有情绪），
   不再等 `_derive_emotion` 的全文结果——分段场景下本来就不可能等。
5. `node_synthesize_voice` 增加短路：`state.get("voice_streamed")` 为真时直接跳过。

不改动非流式路径 `/orchestrator/turn`（全文 TTS 照旧），降低回归面。

### 3.3 链路 B 改造点（`local_realtime.py`）

把「切句 → 合成 → 发送」从串行 await 改成生产者-消费者：

```python
self._tts_queue: asyncio.Queue[str | None]  # None = 流结束哨兵

# token 循环（生产者）：切句后 put_nowait，不再 await _speak
# 新增 _tts_worker（消费者）：逐句 synthesize_pcm_chunks + 发送，
#   合成句子 N+1 与前端播放句子 N 天然重叠
```

- 打断时 `_cancel_turn` 同时清空 `_tts_queue`（8.2 会完善这块，本阶段只做安全取消）。
- `volc_realtime.py` / `cloud_realtime.py` 用同一分段器，本次只改 local，
  其余 provider 标记为后续跟进。

### 3.4 配置项（`shared_runtime/config.py`）

| 配置 | 默认 | 说明 |
|------|------|------|
| `enable_streaming_tts` | `false` | 总开关，灰度用 |
| `streaming_tts_max_concurrency` | `2` | TTS 并发上限 |
| `streaming_tts_min_sentence_chars` | `8` | 最小切句长度 |
| `streaming_tts_max_sentence_chars` | `80` | 强制切分长度 |

---

## 4. 实施步骤（建议拆 3 个 PR）

1. **PR-1 分段器下沉**：`_SENTENCE_END` → `shared_runtime/text_segmenter.py` +
   单测；`local_realtime.py` 改 import。纯重构，无行为变化。
2. **PR-2 链路 B 流水线化**：`_tts_queue` + `_tts_worker`，消除句间静音。
   风险小、收益独立可见。
3. **PR-3 链路 A 流式语音**：`StreamingVoiceAggregator` + SSE 事件扩展 +
   前端 `useChat` 分段播放队列 + 配置开关。最大头，依赖 PR-1。

---

## 5. 指标与测试

**指标**（复用 structlog 现有风格）：

- `voice_segment_synthesized`：`seq`、`latency_ms`、`text_len`
- TTFA 埋点：`stream.first_voice_segment` 相对 `stream.first_token` 的差值
- 对比基线：改动前后各跑 20 轮典型长回复（>100 字），记录首音延迟分布

**测试**：

- `tests/test_streaming.py` 增加：假 LLM token 流 + 假 TTS（可控延迟/失败），
  断言 `voice_segment` 事件 seq 严格递增、单句失败不阻断、`done` 携带
  `voice_mode="segmented"`。
- 分段器单测：中英文标点、省略号、超长句强切、尾句 flush、碎片句合并。

---

## 6. 风险与对策

| 风险 | 对策 |
|------|------|
| 按句合成增加 TTS 调用次数，成本上升 | 并发上限 + 最小句长合并；开关默认关，按 provider 灰度 |
| 按句合成丢失跨句韵律，听感断裂 | 首版接受；8.4 阶段评估把上一句文本作为 context 传给支持的 provider |
| SSE 事件乱序/丢失导致前端播放错位 | seq 严格保序 + 前端缺段时跳过并告警；`voice_done` 携带段数校验 |
| 伪流式 provider（dashscope/fish/mimo）收益打折 | 分段仍有效；文档中标注各 provider 预期收益 |
| Lite Mode 下 voice 模块为 stub | 流式路径同样尊重 `enable_voice=false`，stub 行为不变 |

---

## 7. 与 DLP3D 的对应关系

| DLP3D 概念 | 本方案落点 |
|-----------|-----------|
| DAG 节点间流式边（⇢） | token → Segmenter → Scheduler 的 async 流 |
| `tts_reaction_aggregator` | `StreamingVoiceAggregator`（Reaction 部分留给 8.3） |
| ordered delivery | `next_emit_seq` 游标保序 |
| 分段并行合成 | TTS Scheduler 有界并发 |
| interruption handling | 复用 realtime 的 `_cancel_turn`，8.2 补全 |
