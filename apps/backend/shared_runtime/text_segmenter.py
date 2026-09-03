"""句子级文本分段器 —— 流式 TTS 管线的切句基础设施（路线图 8.1 PR-1）。

把原先散落在 ``voice_layer/providers/realtime/local_realtime.py`` 与
``cloud_realtime.py`` 中重复的 ``_SENTENCE_END`` 正则收敛为单一事实来源，
并提供一个带缓冲的 ``SentenceSegmenter`` 供后续流式语音聚合器
（``StreamingVoiceAggregator``，PR-3）复用。

切句规则：

- 硬边界：``。！？!?`` 与换行，命中即切；
- 软边界：``, ，、;；`` 仅当其后还有 ≥6 个字符时才切（避免把短停顿切成碎句）。

设计稿：``docs/streaming-tts-pipeline-design.md``。
"""

from __future__ import annotations

import re

# 与 voice_layer 原有 _SENTENCE_END 完全一致的正则，行为不变。
SENTENCE_END_RE = re.compile(r"[。！？!?\n]|[，、,;；](?=.{6,})")


class SentenceSegmenter:
    """增量喂入 token，按句切出的流式分段器。

    用法::

        seg = SentenceSegmenter(min_chars=8, max_chars=80)
        for token in llm_stream:
            for sentence in seg.feed(token):
                ...  # 完整句子，可直接送 TTS
        tail = seg.flush()  # 流结束后的尾句（可能为 None）

    参数：

    - ``min_chars``：切出的句子最小长度（strip 后）。短于此长度的候选
      边界会被跳过、继续缓冲，避免「嗯。」这类碎片句单独合成。
    - ``max_chars``：缓冲区强制切分长度。超过此长度仍无合适边界时
      硬切，防止某句 TTS 成为长尾。``None`` 表示不强制切分。
    """

    def __init__(self, *, min_chars: int = 1, max_chars: int | None = None) -> None:
        if min_chars < 1:
            raise ValueError("min_chars must be >= 1")
        if max_chars is not None and max_chars < min_chars:
            raise ValueError("max_chars must be >= min_chars")
        self._min = min_chars
        self._max = max_chars
        self._buf: list[str] = []

    def feed(self, token: str) -> list[str]:
        """喂入一段 token，返回本轮切出的完整句子（可能为空列表）。"""
        if token:
            self._buf.append(token)
        return self._drain()

    def flush(self) -> str | None:
        """流结束：返回缓冲区剩余文本（strip 后），空则返回 ``None``。"""
        tail = "".join(self._buf).strip()
        self._buf.clear()
        return tail or None

    @property
    def pending(self) -> str:
        """当前缓冲区内容（未切出的部分），用于调试与测试。"""
        return "".join(self._buf)

    def _drain(self) -> list[str]:
        out: list[str] = []
        text = "".join(self._buf)
        while text:
            cut_at: int | None = None
            for m in SENTENCE_END_RE.finditer(text):
                if len(text[: m.end()].strip()) >= self._min:
                    cut_at = m.end()
                    break
            if cut_at is None:
                if self._max is not None and len(text) > self._max:
                    cut_at = self._max
                else:
                    break
            sentence, text = text[:cut_at].strip(), text[cut_at:]
            if sentence:
                out.append(sentence)
        self._buf = [text] if text else []
        return out


__all__ = ["SENTENCE_END_RE", "SentenceSegmenter"]
