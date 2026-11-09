const PRISMA_SAMPLE_RATE = 16000;
export async function convertToWav(source: Blob): Promise<Blob> {
  const AudioContextConstructor = window.AudioContext
    ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextConstructor) throw new Error("This browser cannot prepare audio for Prisma.");

  const context = new AudioContextConstructor();
  try {
    const decoded = await context.decodeAudioData(await source.arrayBuffer());
    const sampleCount = Math.ceil(decoded.length * PRISMA_SAMPLE_RATE / decoded.sampleRate);
    const samples = new Float32Array(sampleCount);
    const channels = Array.from({ length: decoded.numberOfChannels }, (_, index) => decoded.getChannelData(index));

    for (let index = 0; index < sampleCount; index += 1) {
      const sourcePosition = index * decoded.sampleRate / PRISMA_SAMPLE_RATE;
      const leftIndex = Math.floor(sourcePosition);
      const rightIndex = Math.min(leftIndex + 1, decoded.length - 1);
      const fraction = sourcePosition - leftIndex;
      let sample = 0;
      for (const channel of channels) {
        sample += channel[leftIndex] * (1 - fraction) + channel[rightIndex] * fraction;
      }
      samples[index] = sample / channels.length;
    }

    const wav = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(wav);
    const writeText = (offset: number, value: string) => {
      for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
    };
    writeText(0, "RIFF");
    view.setUint32(4, wav.byteLength - 8, true);
    writeText(8, "WAVE");
    writeText(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, PRISMA_SAMPLE_RATE, true);
    view.setUint32(28, PRISMA_SAMPLE_RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeText(36, "data");
    view.setUint32(40, samples.length * 2, true);
    for (let index = 0; index < samples.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, samples[index]));
      view.setInt16(44 + index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    }
    return new Blob([wav], { type: "audio/wav" });
  } finally {
    await context.close();
  }
}
