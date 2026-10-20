# voice_layer

> 语音层 · ASR + TTS + 实时语音通道，多 Provider 可热切换。

2026-10-20 · V2.21：5.1、8.1–8.5 已验收，持续全部剩余计划。实时音频增加可协商的 framed-v1 版本、长度、段号与顺序校验；旧客户端保留裸二进制。真实默认 O2 打断恢复、新旧协议与合成麦克风的浏览器收音/实际播放通过；鉴权握手选择公开子协议名，错误/挂断清理录音轨。详见 [音频协议](../docs/audio-transport.md)；8.6 3D/外部形象服务仍待完成。

此前 8.1/8.2 验收记录（2026-10-19）：默认豆包原生 ASR/TTS 与 volc_realtime/O2 不变。`streaming_pipeline.py` 将 token 消费、下一句预合成与有序 PCM 输出分开，cloud 并发 2、本地 Piper 并发 1；句子/帧队列、句长/等待有界，打断等待子任务与迭代器退出。本地线程用有界队列和停止标志，原生推理可完成当前批次，取消后丢弃输出。

主聊天的 SSE 分段适配器在宿主 `core_orchestrator/streaming_voice.py`，客户端声明 `supports_segmented_voice=true` 后启用；原客户端保持全文语音。实时录音上限 60 秒，reset/interrupt 清除溢出；原生豆包打断屏蔽旧帧直到下一次 ASR 结束。前端按播放代次丢弃迟到解码、按序播放，启动缓冲 40–250ms，待播含新块最多 30 秒、解码最多 16、单帧最多 2 MiB。音频/表情时间轴聚合（8.4）与完整实时人格链路（5.1）已在后续迭代验收，详见根目录执行表。

当时后端 603 passed（线程警告视为错误），Web 42 passed，Web/PC builds passed。真实 20 组固定文本对比首音中位 6.703s → 4.234s（36.8%），40/40 成功；真实 TTS/ASR 回识别及原生实时打断/下一轮恢复通过。该指标是固定样例测量，不代表所有环境或主观听感评分。报告见根目录忽略输出 `output/playwright/streaming-latency.json`。

回归：`pytest -q voice_layer/tests --ignore=voice_layer/tests/test_voice.py shared_runtime/tests/test_text_segmenter.py core_orchestrator/tests/test_streaming_voice.py`。可复跑真实对比：`python tools/benchmark_streaming_voice.py --base-url http://127.0.0.1:8000 --samples 20 --output ../../output/playwright/streaming-latency.json`；需要已配置服务与隔离数据库。

## 我是什么

`voice_layer` 把语音相关能力封装为统一接入层：

- **ASR 客户端**（`ASRClient`）：Whisper / Groq / SiliconFlow / DashScope-Paraformer + 本地 faster-whisper 兜底
- **TTS 客户端**（`TTSClient`）：Fish Audio S2 / ChatTTS / OpenAI TTS + 本地 Piper 兜底
- **实时语音通道**（`realtime`）：WebSocket 双向流 + Silero VAD + 边合成边播
- **音频工具**：`convert_audio_format` / `get_audio_duration` / `save_temp_audio`

## 暴露什么 API

```python
from voice_layer import (
    ASRClient, TTSClient,
    convert_audio_format, get_audio_duration, save_temp_audio,
)
from voice_layer.api import router         # FastAPI /voice
from voice_layer.main import app           # 独立 app（端口 8003）
from voice_layer.realtime import realtime_router
from voice_layer import local_asr, local_tts
```

## 依赖什么

- companion-ai 内部：`shared_contracts`（EmotionTag / VoiceSynthesisRequest / VoiceTranscriptionResult）、`shared_runtime`（语音运行时配置、LLMClient）
- 第三方：`httpx` / `tenacity` / `structlog` / `fastapi` / `uvicorn`，可选 `numpy` / `piper-tts` / `faster-whisper`

> ⚠️ 部分音频处理依赖 `ffmpeg`；离线环境需自行安装或换用本地 piper TTS。

## 怎么单独启

```bash
# 方式 1：独立 FastAPI 微服务
cd apps/backend
COMPANION_LITE_MODE=true python -m voice_layer
# → http://localhost:8003/docs

# 方式 2：在自己的脚本里 import 用
```

## 最小用法

```python
import asyncio
from voice_layer import ASRClient, TTSClient
from shared_contracts import EmotionTag, VoiceSynthesisRequest
from shared_runtime.voice_runtime_config import load_voice_config_from_disk

async def demo():
    load_voice_config_from_disk()
    asr = ASRClient(); tts = TTSClient()
    try:
        with open("clip.wav", "rb") as f:
            result = await asr.transcribe(f.read(), language="zh")
        print(result.text, result.detected_emotion)
        req = VoiceSynthesisRequest(text="你好呀", emotion=EmotionTag.HAPPY)
        audio = await tts.synthesize(req)
        print(audio["audio_url"])
    finally:
        await asr.close(); await tts.close()

# asyncio.run(demo())  # 需要 ASR/TTS provider 的 API key
```

## 第三方宿主接入提示

`ASRClient` 实现高层 `shared_contracts.SpeechRecognizer`：上传音频返回真实 `VoiceTranscriptionResult`，PCM 识别返回字符串。低层 `ASRProvider` 与 `TTSProvider` 是另一组协议；`TTSClient.synthesize()` 返回包含 `audio_url` 的字典，不是音频字节。

V2.22 支持 `voice_layer.main.create_app(asr_factory=...)` 和参考宿主 `main.create_app(asr_factory=...)`。工厂保存在各 app 的 state，REST 每次创建/关闭识别器，旧 stream/cloud 通话按连接持有。宿主负责实现高层协议，模块负责等待关闭；默认原生 O2 路径不受影响。TTS HTTP 客户端仍是参考宿主单例，尚未实现同样的多 app 注入。迁移及资源所有权见 [模块注入](../docs/module-injection.md)。

## 火山引擎实时语音接入策略

现阶段实时语音聊天优先接入火山引擎端到端实时语音大模型 API，目标是尽快获得接近豆包语音对话的体验：低延迟语音输入、实时识别文本、模型回复文本流、TTS 音频流播放和打断能力。该接入只作为 `voice_layer` 的一个 Provider，不改变本项目“模块化语音能力层”的定位。

官方参考文档：[端到端实时语音大模型 API 接入文档](https://www.volcengine.com/docs/6561/1594356?lang=zh)。

接入边界：

- 前端仍连接本项目的 `/voice/realtime` WebSocket，不直接暴露火山引擎密钥。
- 后端新增 `volc_realtime` Provider，由 `voice_layer` 负责连接火山引擎 WebSocket，并把厂商事件转换成本项目内部统一事件。
- 当前阶段可以先让火山引擎完成 ASR、LLM、TTS 的端到端链路，以优先解决实时性和角色语音质量问题。
- 角色人设、短期上下文、长期记忆摘要需要在会话启动时注入火山引擎会话配置；如果厂商上下文能力不足，后续切回本项目自己的 `core_orchestrator` 流式链路。
- 普通语音回复和实时语音回复都必须走同一套 `VoiceProfile` / `resolve_voice()` 逻辑，不能把 Azure、DashScope、Volc、Piper 的 voice id 混用。
- API Key、App ID、Access Token 等凭据只能来自环境变量、运行时配置或用户配置存储，禁止硬编码进代码、README、测试快照或前端产物。

建议统一事件模型：

```text
ready
user_transcript_delta
user_transcript_final
assistant_text_delta
assistant_sentence_start
assistant_audio_chunk
assistant_audio_done
interrupted
error
```

## 后续语音模块迭代计划

### 1. Provider 化与配置中心

- 建立 `RealtimeVoiceProvider` 抽象，至少支持 `volc_realtime`、`modular_realtime`、`local_realtime` 三类实现。
- 建立 `VoiceProfile` 配置模型，用一个角色音色 ID 映射到不同 Provider 的实际 speaker / voice / model。
- 支持用户在设置页选择语音 Provider、模型、音色、实时模式开关和普通回复模式，但 UI 不展示明文密钥。
- 增加能力声明，例如 `supports_realtime`、`supports_interrupt`、`supports_text_delta`、`supports_voice_clone`、`audio_format`。

### 2. 当前火山引擎接入

- 实现 `voice_layer/providers/realtime/volc_realtime.py`，负责鉴权、会话创建、音频分片上传、事件解析、音频流下发和异常恢复。
- 改造 `voice_layer/realtime.py`，从硬编码本地 ASR/TTS 改为 Provider Registry 选择。
- 前端 `useRealtimeVoice.ts` 尽量只消费内部统一事件，避免写入火山引擎专有字段。
- 增加最小回归测试：Provider 选择、VoiceProfile 解析、事件归一化、凭据脱敏、普通语音与实时语音音色一致性。

### 3. 角色专属音色与高度定制

- 设计角色音色素材规范：采样率、音频格式、单句长度、情绪覆盖、噪声标准、授权记录和版本号。
- 建立角色音色资产目录，不把原始录音直接混入代码目录；音色资产需要可替换、可回滚、可审计。
- 调研并接入支持声音复刻或定制音色的 Provider，优先要求稳定授权、低延迟、可商用、可导出或可迁移。
- 为每个角色维护 `voice_profile_id`，不要在业务代码里直接写具体 speaker 名称。

### 4. 自研/半自研实时语音链路

- 在火山引擎 Provider 稳定后，推进 `modular_realtime`：流式 ASR -> `core_orchestrator.stream_assistant_response()` -> 流式 TTS。
- 让实时语音真正复用 persona、memory、relationship state、safety_guard，而不是另写一份语音聊天 prompt。
- 增加端到端延迟指标：首字识别、最终识别、首个回复 token、首包音频、完整句播放、打断响应。
- 当自研链路达到可接受延迟后，火山引擎端到端模式保留为快速 Provider 和商业兜底。

### 5. 质量评测

- 建立固定测试脚本：安静环境、噪声环境、快速打断、长句、情绪语气、角色一致性、多轮记忆引用。
- 记录每次语音回复的 Provider、voice_profile_id、实际 speaker、延迟分段和失败原因。
- 对角色音色做主观评分：像不像、稳不稳、是否有机械感、情绪是否过度、是否符合角色年龄和性格。
