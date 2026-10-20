"""Opt-in live comparison using synthetic text and the host's configured services.

Runs both negotiated segmented playback and legacy full-utterance TTS. Outputs
timings and aggregate statistics, never configuration/credentials or chat text.
"""

import argparse
import asyncio
import json
import statistics
import time
import uuid
from pathlib import Path

import httpx

TEXT = (
    "忙碌结束以后可以轻轻伸展肩膀和颈部让长时间紧绷的肌肉获得充分休息。"
    "也可以选择一条安静的小路慢慢散步留心身旁的树木和天空逐渐变化的颜色。"
    "回到家以后喝一杯温水再认真听一段自己喜欢的音乐给今天留下温柔的收尾。"
)


async def measure(client, base_url, segmented):
    marker = "voice-benchmark-" + uuid.uuid4().hex
    request = {
        "session_id": marker,
        "user": {"user_id": marker, "display_name": "合成验收"},
        "platform": "app",
        "user_message": "只原样朗读下面三句话，不要加介绍、不用列表或表情：" + TEXT,
        "request_voice_reply": True,
        "supports_segmented_voice": segmented,
    }
    first_audio = None
    first_token = None
    last_token = None
    count, errors, text_chars = 0, 0, 0
    started = time.monotonic()
    async with client.stream("POST", base_url + "/orchestrator/turn/stream", json=request) as response:
        response.raise_for_status()
        name = ""
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                payload = json.loads(line[5:])
                elapsed = time.monotonic() - started
                if name == "token":
                    first_token = first_token if first_token is not None else elapsed
                    last_token = elapsed
                    text_chars += len(payload.get("text", ""))
                elif name == "voice_segment":
                    first_audio = first_audio if first_audio is not None else elapsed
                    count += 1
                elif name == "voice_segment_error":
                    errors += 1
                elif name == "done" and payload.get("voice_url"):
                    first_audio = elapsed
                    count = 1
                elif name == "error":
                    errors += 1
    return {
        "mode": "segmented" if segmented else "single",
        "first_audio_seconds": first_audio,
        "first_token_seconds": first_token,
        "last_token_seconds": last_token,
        "complete_seconds": time.monotonic() - started,
        "segments": count,
        "errors": errors,
        "text_chars": text_chars,
    }


async def main(args):
    rows = []
    async with httpx.AsyncClient(timeout=120) as client:
        for index in range(args.samples):
            # Alternate the first arm to reduce warm-up/order effects.
            for segmented in [True, False] if index % 2 else [False, True]:
                rows.append({"sample": index + 1, **await measure(client, args.base_url.rstrip("/"), segmented)})
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps({"samples": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"completed_pairs": index + 1, "samples": rows[-2:]}, ensure_ascii=False), flush=True)
    summary = {}
    for mode in ("single", "segmented"):
        successful = [
            row["first_audio_seconds"] for row in rows if row["mode"] == mode and row["first_audio_seconds"] is not None
        ]
        summary[mode] = {
            "successful": len(successful),
            "median_first_audio_seconds": statistics.median(successful) if successful else None,
            "mean_first_audio_seconds": statistics.mean(successful) if successful else None,
        }
    Path(args.output).write_text(
        json.dumps({"summary": summary, "samples": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--output", required=True)
    asyncio.run(main(parser.parse_args()))
