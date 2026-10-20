"""Offline text statistics; no files, network, model calls or extra dependencies."""

import re
import unicodedata

from action_executor.registry import ActionResult


async def setup(api):
    async def statistics(arguments, context):
        text = arguments["text"]
        return ActionResult(
            ok=True,
            message="文本统计完成。",
            data={
                "characters": len(text),
                "non_whitespace": sum(not char.isspace() for char in text),
                "lines": len(text.splitlines()),
                "latin_words": len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", text)),
                "han_characters": sum("CJK UNIFIED IDEOGRAPH" in unicodedata.name(char, "") for char in text),
            },
        )

    api.add_tool(
        "statistics",
        "统计用户提供文本的字符、非空白字符、行、拉丁单词和汉字数量；纯本地计算。",
        {
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 10000}},
            "required": ["text"],
            "additionalProperties": False,
        },
        statistics,
        read_only=True,
    )
