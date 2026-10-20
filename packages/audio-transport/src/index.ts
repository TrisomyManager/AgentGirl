/** CNAV v1. Network byte order; payload encoding is declared in JSON metadata. */
export const AUDIO_PROTOCOL = 'framed-v1';
export const AUDIO_HEADER_BYTES = 20;
export const MAX_AUDIO_BYTES = 2 * 1024 * 1024;

export function encodeAudioFrame(payload: ArrayBuffer, streamId: number, sequence: number): ArrayBuffer {
  if (!payload.byteLength || payload.byteLength > MAX_AUDIO_BYTES ||
      ![streamId, sequence].every(value => Number.isInteger(value) && value >= 0 && value <= 0xffffffff)) {
    throw new Error('Invalid audio frame');
  }
  const frame = new ArrayBuffer(AUDIO_HEADER_BYTES + payload.byteLength);
  const bytes = new Uint8Array(frame), view = new DataView(frame);
  bytes.set([67, 78, 65, 86, 1, 1, 0, 0]);
  view.setUint32(8, streamId); view.setUint32(12, sequence); view.setUint32(16, payload.byteLength);
  bytes.set(new Uint8Array(payload), AUDIO_HEADER_BYTES);
  return frame;
}

export function decodeAudioFrame(frame: ArrayBuffer): { streamId: number; sequence: number; payload: ArrayBuffer } {
  if (frame.byteLength <= AUDIO_HEADER_BYTES || frame.byteLength > AUDIO_HEADER_BYTES + MAX_AUDIO_BYTES) {
    throw new Error('Invalid audio frame size');
  }
  const view = new DataView(frame);
  if (view.getUint32(0) !== 0x434e4156 || view.getUint8(4) !== 1 || view.getUint8(5) !== 1 ||
      view.getUint16(6) !== 0 || view.getUint32(16) !== frame.byteLength - AUDIO_HEADER_BYTES) {
    throw new Error('Invalid audio frame header');
  }
  return { streamId: view.getUint32(8), sequence: view.getUint32(12), payload: frame.slice(AUDIO_HEADER_BYTES) };
}
