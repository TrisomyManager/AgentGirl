"""Bounded output checks before callers publish text or schedule speech synthesis."""

import re
from contextlib import aclosing

from safety_guard import SafetyGuard, default_guard, safe_fallback_reply


class OutputGate:
    def __init__(self, guard: SafetyGuard | None = None, *, max_chars=16000, sentence_chars=240):
        self.guard = guard or default_guard
        self.pending = ""
        self.sentence_chars = sentence_chars
        self.raw = ""
        self.approved = ""
        self.blocked = False
        self.max_chars = max_chars
        # Arbitrary custom regex may depend on a future suffix: hold the response.
        self.complete_only = getattr(self.guard, "requires_complete_output", True)

    def _approve(self, text):
        try:
            verdict = self.guard.check_output(self.raw if self.complete_only else self.approved[-2000:] + text)
        except Exception:
            self.blocked = True
            text = "这段回答暂时无法完成检查，请稍后再试。"
            self.approved += text
            return [text]
        if verdict.blocked:
            self.blocked = True
            text = safe_fallback_reply(verdict)
        self.approved += text
        return [text] if text else []

    def feed(self, token):
        if self.blocked:
            return []
        if len(self.raw) + len(token) > self.max_chars:
            self.blocked = True
            replacement = "这次回答过长，已停止继续输出。我们可以分开讨论。"
            self.approved += replacement
            return [replacement]
        self.raw += token
        if self.complete_only:
            return []
        output = []
        self.pending += token
        while self.pending:
            match = re.search(r"[。！？!?\n]|\.(?=\s)", self.pending)
            cut = match.end() if match else None
            if len(self.pending) > self.sentence_chars:
                cut = min(cut or self.sentence_chars, self.sentence_chars)
            if cut is None:
                break
            sentence, self.pending = self.pending[:cut], self.pending[cut:]
            output.extend(self._approve(sentence))
            if self.blocked:
                break
        return output

    def finish(self):
        if self.blocked:
            return []
        if self.complete_only:
            return self._approve(self.raw)
        tail, self.pending = self.pending, ""
        return self._approve(tail) if tail else []


async def checked_text_stream(source, *, guard=None, on_block=None):
    gate = OutputGate(guard)
    async with aclosing(source):
        async for token in source:
            for text in gate.feed(token):
                yield text
            if gate.blocked:
                if on_block:
                    on_block()
                return
        for text in gate.finish():
            yield text
        if gate.blocked and on_block:
            on_block()
