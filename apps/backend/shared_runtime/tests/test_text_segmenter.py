"""Tests for shared_runtime.text_segmenter (路线图 8.1 PR-1)."""

from __future__ import annotations

import pytest

from shared_runtime.text_segmenter import SENTENCE_END_RE, SentenceSegmenter


class TestSentenceEndRegex:
    """切句正则行为：与 voice_layer 原有 _SENTENCE_END 保持一致。"""

    @pytest.mark.parametrize("text", ["你好。", "太好了！", "真的吗？", "wow!", "ok?", "换行\n"])
    def test_hard_boundaries_match(self, text: str) -> None:
        assert SENTENCE_END_RE.search(text) is not None

    @pytest.mark.parametrize("text", ["你好世界这是一段话", "no punctuation here"])
    def test_no_boundary(self, text: str) -> None:
        assert SENTENCE_END_RE.search(text) is None

    def test_comma_only_splits_with_six_chars_following(self) -> None:
        # 逗号后不足 6 字符 → 不切
        assert SENTENCE_END_RE.search("你好，世界") is None
        # 逗号后有 ≥6 字符 → 切
        assert SENTENCE_END_RE.search("你好，世界今天天气真不错") is not None

    def test_chinese_pause_marks_behave_like_comma(self) -> None:
        assert SENTENCE_END_RE.search("苹果、香蕉") is None
        assert SENTENCE_END_RE.search("苹果、香蕉和橙子都很好吃呢") is not None


class TestSentenceSegmenter:
    def test_single_sentence(self) -> None:
        seg = SentenceSegmenter()
        assert seg.feed("今天天气") == []
        assert seg.feed("真好。") == ["今天天气真好。"]
        assert seg.flush() is None

    def test_token_split_across_boundary(self) -> None:
        seg = SentenceSegmenter()
        out = seg.feed("第一句。第二")
        assert out == ["第一句。"]
        assert seg.pending == "第二"
        assert seg.flush() == "第二"

    def test_multiple_sentences_in_one_token(self) -> None:
        seg = SentenceSegmenter()
        assert seg.feed("其一。其二！其三？") == ["其一。", "其二！", "其三？"]

    def test_flush_returns_tail(self) -> None:
        seg = SentenceSegmenter()
        assert seg.feed("没有标点的尾巴") == []
        assert seg.flush() == "没有标点的尾巴"
        assert seg.flush() is None  # 二次 flush 返回 None

    def test_min_chars_merges_short_fragments(self) -> None:
        seg = SentenceSegmenter(min_chars=8)
        # 「嗯。」只有 2 字符，不单独切出
        assert seg.feed("嗯。") == []
        # 继续累积后一起切出
        assert seg.feed("我在听你说。") == ["嗯。我在听你说。"]

    def test_max_chars_forces_cut(self) -> None:
        seg = SentenceSegmenter(max_chars=10)
        out = seg.feed("这是一段没有任何标点符号的超长文本内容")
        assert out == ["这是一段没有任何标点"]
        assert seg.pending == "符号的超长文本内容"

    def test_max_chars_none_disables_force_cut(self) -> None:
        seg = SentenceSegmenter(max_chars=None)
        long_text = "没" * 200
        assert seg.feed(long_text) == []
        assert seg.flush() == long_text

    def test_empty_and_whitespace_tokens(self) -> None:
        seg = SentenceSegmenter()
        assert seg.feed("") == []
        assert seg.flush() is None

    def test_punctuation_only_fragment_passthrough(self) -> None:
        """纯标点碎片会原样切出（与 legacy 行为一致）；碎片过滤交给
        min_chars（PR-3 默认 8）在上层保证。"""
        seg = SentenceSegmenter()
        assert seg.feed("。") == ["。"]
        seg2 = SentenceSegmenter(min_chars=8)
        assert seg2.feed("。") == []
        assert seg2.flush() == "。"

    def test_comma_soft_boundary_in_stream(self) -> None:
        seg = SentenceSegmenter()
        # 逗号后不足 6 字符时不切
        assert seg.feed("好的，") == []
        # 后续 token 补足 6 字符后切出
        assert seg.feed("我马上去帮你查一下") == ["好的，"]

    def test_invalid_params(self) -> None:
        with pytest.raises(ValueError):
            SentenceSegmenter(min_chars=0)
        with pytest.raises(ValueError):
            SentenceSegmenter(min_chars=10, max_chars=5)

    def test_realistic_llm_stream(self) -> None:
        """模拟真实 LLM token 流：碎片 token 逐步拼句。

        逗号是软边界：其后满 6 字符（含句末标点）即切，所以
        「听到你这么说，」会单独成句——与 legacy `_SENTENCE_END` 行为一致。
        """
        tokens = ["听", "到你", "这么", "说", "，", "我有", "点开", "心", "。",
                  "要不", "我们", "一起", "想想", "办法", "？"]
        seg = SentenceSegmenter()
        sentences: list[str] = []
        for tok in tokens:
            sentences.extend(seg.feed(tok))
        tail = seg.flush()
        assert sentences == ["听到你这么说，", "我有点开心。", "要不我们一起想想办法？"]
        assert tail is None  # 尾句以硬边界「？」结尾，已被切出
