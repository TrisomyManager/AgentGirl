import { expect, it } from 'vitest';
import { decodeAudioFrame, encodeAudioFrame } from '../../../../packages/audio-transport/src';

it('matches the cross-language CNAV fixture including byte order', () => {
  const payload = new Uint8Array([0, 128, 255, 127]).buffer;
  const frame = encodeAudioFrame(payload, 0x01020304, 5);
  expect(Array.from(new Uint8Array(frame))).toEqual([
    67, 78, 65, 86, 1, 1, 0, 0, 1, 2, 3, 4, 0, 0, 0, 5, 0, 0, 0, 4, 0, 128, 255, 127,
  ]);
  const decoded = decodeAudioFrame(frame);
  expect(decoded.streamId).toBe(0x01020304);
  expect(decoded.sequence).toBe(5);
  expect(Array.from(new Uint8Array(decoded.payload))).toEqual([0, 128, 255, 127]);
});

it('rejects truncated, oversized, unknown version and incorrect-length frames', () => {
  const valid = encodeAudioFrame(new ArrayBuffer(4), 1, 0);
  expect(() => decodeAudioFrame(valid.slice(0, 21))).toThrow();
  expect(() => decodeAudioFrame(new ArrayBuffer(20))).toThrow();
  expect(() => decodeAudioFrame(new ArrayBuffer(2 * 1024 * 1024 + 21))).toThrow();
  new Uint8Array(valid)[4] = 2;
  expect(() => decodeAudioFrame(valid)).toThrow();
  expect(() => encodeAudioFrame(new ArrayBuffer(4), 1, 0x100000000)).toThrow();
});
