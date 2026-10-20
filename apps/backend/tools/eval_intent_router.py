"""Evaluate curated intent cases using rules or the configured provider.

Run from apps/backend: python tools/eval_intent_router.py --mode rules|model.
The report contains synthetic case IDs and decisions, never provider secrets.
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import structlog

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from core_orchestrator.intent_router import IntentRouter  # noqa: E402


async def evaluate(mode, case_file):
    cases = json.loads(case_file.read_text(encoding="utf-8"))
    router = IntentRouter()
    if mode == "model":
        router.settings.intent_router_use_llm = True
        if not router._can_use_llm():
            return {"status": "unavailable", "reason": "No configured provider"}
    semaphore = asyncio.Semaphore(3)

    async def classify(case):
        async with semaphore:
            result = (
                (await router.classify(case["message"], case.get("context")))
                if mode == "model"
                else (router._heuristic_classify(case["message"], case.get("context")))
            )
            return {
                "id": case["id"],
                "expected": case["expected"],
                "predicted": result.intent.value,
                "source": result.source,
                "correct": result.intent.value == case["expected"],
            }

    try:
        decisions = await asyncio.gather(*(classify(case) for case in cases))
    finally:
        client = getattr(router._llm, "root_async_client", None)
        if client:
            await client.close()
    correct = sum(case["correct"] for case in decisions)
    return {
        "status": "complete",
        "mode": mode,
        "total": len(cases),
        "correct": correct,
        "accuracy": round(correct / len(cases), 4),
        "decision_sources": dict(Counter(case["source"] for case in decisions)),
        "failures": [case for case in decisions if not case["correct"]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["rules", "model"], default="rules")
    parser.add_argument("--cases", type=Path, default=BACKEND / "core_orchestrator/tests/data/intent_cases.json")
    arguments = parser.parse_args()
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    report = asyncio.run(evaluate(arguments.mode, arguments.cases))
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report.get("accuracy") == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
