"""Offline codec evaluation. Protobuf is optional and never a runtime dependency."""

import argparse
import base64
import json
import statistics
import sys
import timeit
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_contracts.audio_transport import decode_audio_frame, encode_audio_frame


def protobuf_codec():
    try:
        from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
    except ImportError:
        return None
    schema = descriptor_pb2.FileDescriptorProto(name="audio_benchmark.proto", package="benchmark", syntax="proto3")
    message = schema.message_type.add(name="Audio")
    for name, number, kind in [("version", 1, 13), ("stream_id", 2, 13), ("sequence", 3, 13), ("payload", 4, 12)]:
        message.field.add(name=name, number=number, type=kind, label=1)
    descriptor = descriptor_pool.DescriptorPool().Add(schema).message_types_by_name["Audio"]
    cls = message_factory.GetMessageClass(descriptor)
    return (
        lambda payload: cls(version=1, stream_id=7, sequence=1000, payload=payload).SerializeToString(),
        cls.FromString,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    codecs = {
        "raw": (lambda data: data, lambda data: data),
        "framed_v1": (lambda data: encode_audio_frame(data, stream_id=7, sequence=1000), decode_audio_frame),
        "json_base64_hypothetical": (
            lambda data: json.dumps(
                {"version": 1, "stream_id": 7, "sequence": 1000, "payload": base64.b64encode(data).decode()},
                separators=(",", ":"),
            ).encode(),
            lambda data: base64.b64decode(json.loads(data)["payload"], validate=True),
        ),
    }
    protobuf = protobuf_codec()
    if protobuf:
        codecs["protobuf_optional"] = protobuf
    rows = []
    for size in (1024, 4096, 16384):
        payload = bytes(range(256)) * (size // 256)
        for name, (encode, decode) in codecs.items():
            encoded = encode(payload)
            encode_us = statistics.median(timeit.repeat(partial(encode, payload), number=3000, repeat=5)) / 3000 * 1e6
            decode_us = statistics.median(timeit.repeat(partial(decode, encoded), number=3000, repeat=5)) / 3000 * 1e6
            rows.append(
                {
                    "codec": name,
                    "payload_bytes": size,
                    "wire_bytes": len(encoded),
                    "encode_us": round(encode_us, 3),
                    "decode_us": round(decode_us, 3),
                }
            )
    report = {
        "synthetic_offline_microbenchmark": True,
        "existing_realtime_is_raw_binary": True,
        "not_network_or_model_latency": True,
        "protobuf_available": bool(protobuf),
        "rows": rows,
    }
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
