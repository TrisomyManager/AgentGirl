"""运行时协议 (Protocols) —— 宿主可注入的接口.

虽然命名为 contracts, 但 Protocol 是"形状定义"而非具体实现, 仍属契约层范畴.
具体实现在 ``shared_runtime`` 包.

ADR-006 硬约束 2: 业务模块禁止直连 LLM 厂商 SDK, 必须通过本 Protocol 调用.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """LLM 客户端抽象接口.

    第三方宿主可实现本 Protocol, 注入到任意业务模块,
    业务模块代码不需要知道底层是 OpenAI / Anthropic / 自研网关 / Mock.
    """

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """同步式对话, 返回完整文本."""
        ...

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式对话, 异步 yield token 文本片段."""
        ...


@runtime_checkable
class ASRProvider(Protocol):
    """语音识别 Provider 抽象."""

    async def transcribe(self, audio_bytes: bytes, *, sample_rate: int = 16000, **kwargs: Any) -> str:
        ...


@runtime_checkable
class TTSProvider(Protocol):
    """文本转语音 Provider 抽象."""

    async def synthesize(self, text: str, *, voice: str | None = None, **kwargs: Any) -> bytes:
        ...


@runtime_checkable
class RealtimeVoiceProvider(Protocol):
    """实时全双工语音 Provider 抽象.

    实现本 Protocol 的 Provider 负责管理一条实时语音会话的完整生命周期:
    鉴权、音频上行、ASR、LLM、TTS 以及事件下行。

    子类只需实现 ``run()`` 协程, 接收前端 WebSocket 帧, 产出统一事件。
    """

    async def run(
        self,
        ws_send_json,
        ws_send_bytes,
        ws_receive,
        *,
        memory_user_id: str = "anonymous",
        memory_session_id: str | None = None,
    ) -> None:
        """运行实时语音会话。

        Parameters
        ----------
        ws_send_json : callable
            向前端发送 JSON 事件的异步函数 ``async def fn(data: dict)``.
        ws_send_bytes : callable
            向前端发送二进制音频块的异步函数 ``async def fn(data: bytes)``.
        ws_receive : callable
            从前端接收消息的异步函数, 返回 ``dict`` 格式:
            ``{"type": "binary", "data": bytes}``
            ``{"type": "text", "data": str}``
            ``{"type": "disconnect"}``
        memory_user_id : str
            可选：用于异步写入记忆链路的用户 ID（query / start 消息传入）。
        memory_session_id : str | None
            可选：会话 ID；省略时由具体 Provider 生成稳定默认值。
        """
        ...

    @property
    def supports_interrupt(self) -> bool:
        """是否支持用户打断 (barge-in)."""
        ...

    @property
    def supports_text_delta(self) -> bool:
        """是否支持助手回复文本增量推送."""
        ...

    @property
    def provider_name(self) -> str:
        """Provider 标识名称, 用于注册和日志."""
        ...


__all__ = ["LLMClient", "ASRProvider", "TTSProvider", "RealtimeVoiceProvider"]
