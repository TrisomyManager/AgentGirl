"""`python -m safety_guard <text>` — smoke-test the default guard."""

from __future__ import annotations

import json
import sys

from safety_guard import default_guard


def main() -> None:
    text = " ".join(sys.argv[1:]) or "你好，今天的天气真不错。"
    verdict = default_guard.check_input(text)
    print(json.dumps(
        {
            "input": text,
            "allowed": verdict.allowed,
            "reason": verdict.reason,
            "matched_terms": list(verdict.matched_terms),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
