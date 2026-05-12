/**
 * Audio format conversion helpers.
 *
 * Browser MediaRecorder produces webm/opus. DashScope Paraformer requires
 * WAV 16kHz mono PCM. This module converts via Web Audio API decoding.
 */

export async function blobToWav16kMono(blob: Blob): Promise<Blob> {
  const targetRate = 16000;
  const arrayBuffer = await blob.arrayBuffer();

  const AudioCtx: typeof AudioContext =
    (window as any).AudioContext || (window as any).webkitAudioContext;
  const decodeCtx = new AudioCtx();

  let audioBuffer: AudioBuffer;
  try {
    audioBuffer = await decodeCtx.decodeAudioData(arrayBuffer);
  } finally {
    decodeCtx.close();
  }

  // Resample + downmix to mono 16kHz via OfflineAudioContext
  const length = Math.ceil(audioBuffer.duration * targetRate);
  const offline = new OfflineAudioContext(1, length, targetRate);
  const source = offline.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(offline.destination);
  source.start(0);
  const rendered = await offline.startRendering();

  const pcm = rendered.getChannelData(0);
  const wav = encodeWav(pcm, targetRate);
  return new Blob([wav], { type: 'audio/wav' });
}

function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  writeStr(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(view, 8, 'WAVE');
  writeStr(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);            // PCM
  view.setUint16(22, 1, true);            // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);            // block align
  view.setUint16(34, 16, true);           // bits per sample
  writeStr(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const v = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, v < 0 ? v * 0x8000 : v * 0x7fff, true);
    offset += 2;
  }
  return buffer;
}

function writeStr(view: DataView, offset: number, str: string): void {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}
