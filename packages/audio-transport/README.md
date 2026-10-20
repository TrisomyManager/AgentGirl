# Audio transport v1

The reference Web/PC client requests `/voice/realtime?audio_protocol=framed-v1`. The server responds with JSON `transport_ready` before the provider starts. A server that only sends the older `ready` event selects raw binary compatibility. Clients that omit the parameter retain raw binary audio.

Control events remain JSON, limited to 64 KiB UTF-8. One binary WebSocket message contains one 20-byte network-order header followed by 1–2,097,152 bytes of audio:

| Offset | Size | Value |
| --- | --- | --- |
| 0 | 4 | ASCII `CNAV` |
| 4 | 1 | Version `1` |
| 5 | 1 | Audio kind `1` |
| 6 | 2 | Reserved `0` |
| 8 | 4 | Stream ID, uint32 |
| 12 | 4 | Connection-wide sequence, uint32, starting at 0 |
| 16 | 4 | Exact payload length, uint32 |

Uplink stream ID is 0; input is still mono 16 kHz PCM16 as required by the provider. Downlink streams start at 1 and increase for each `assistant_sentence_start`/`tts_start`; the same JSON event declares `audio_stream_id`, `audio_protocol`, format and sample rate. The stream ID is independent of avatar timeline/turn identifiers. Sequence numbers continue across sentence changes and interruption, independently in each direction.

Unknown version/kind/reserved bits, invalid length, overflow and out-of-order/replayed packet sequences are protocol errors. Audio for an inactive stream is discarded. Interruption stops accepting audio until a new announced stream. Provider cancellation still owns the upstream vendor boundary; the frame cannot identify vendor audio that was mislabeled before framing. Production remote access continues to require the host's HTTPS/WSS and authentication.

The pure TypeScript codec has no dependencies. Python's matching codec lives in `shared_contracts/audio_transport.py`; tests compare a shared fixed byte fixture. The backend serializes sends and settles cancellation before advancing sequence numbers. A blocked send has a five-second bound. This preserves sequence continuity when interruption arrives during an in-progress send.
