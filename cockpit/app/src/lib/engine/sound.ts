/**
 * Sound Engine — Web Audio API ambient + interaction sounds.
 * Pure engine module (no React dependency).
 *
 * All sounds are procedurally generated (no audio files needed).
 * Sound is OFF by default and respects prefers-reduced-motion.
 */

let ctx: AudioContext | null = null;
let masterGain: GainNode | null = null;
let enabled = false;

// Category gains
const categories = {
  ambient: null as GainNode | null,
  ui: null as GainNode | null,
  effects: null as GainNode | null,
};

function getContext(): AudioContext | null {
  if (!ctx) {
    try {
      ctx = new AudioContext();
      masterGain = ctx.createGain();
      masterGain.gain.value = 0.3;
      masterGain.connect(ctx.destination);

      // Create category channels
      for (const key of Object.keys(categories) as (keyof typeof categories)[]) {
        const gain = ctx.createGain();
        gain.gain.value = 0.5;
        gain.connect(masterGain);
        categories[key] = gain;
      }
    } catch {
      return null;
    }
  }
  if (ctx.state === "suspended") {
    ctx.resume().catch(() => {});
  }
  return ctx;
}

/** Check if user prefers reduced motion */
function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Enable sound engine (must be called after user interaction) */
export function enableSound() {
  if (prefersReducedMotion()) return;
  enabled = true;
  getContext();
}

/** Disable sound engine */
export function disableSound() {
  enabled = false;
}

/** Dispose sound engine — release AudioContext and all nodes */
export function disposeSound() {
  enabled = false;
  if (ctx) {
    ctx.close().catch(() => {});
    ctx = null;
  }
  masterGain = null;
  categories.ambient = null;
  categories.ui = null;
  categories.effects = null;
}

/** Check if sound is enabled */
export function isSoundEnabled(): boolean {
  return enabled;
}

/** Set master volume (0-1) */
export function setMasterVolume(volume: number) {
  if (masterGain) {
    masterGain.gain.value = Math.max(0, Math.min(1, volume));
  }
}

/** Set category volume (0-1) */
export function setCategoryVolume(
  category: keyof typeof categories,
  volume: number,
) {
  const gain = categories[category];
  if (gain) {
    gain.gain.value = Math.max(0, Math.min(1, volume));
  }
}

/** Play a short ping — node selection */
export function playSelectPing(nodeSize = 1.0) {
  if (!enabled) return;
  const audio = getContext();
  if (!audio || !categories.ui) return;

  const osc = audio.createOscillator();
  const gain = audio.createGain();

  // Bigger nodes = lower pitch
  const freq = 800 - nodeSize * 200;
  osc.frequency.setValueAtTime(Math.max(300, freq), audio.currentTime);
  osc.type = "sine";

  gain.gain.setValueAtTime(0.15, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.15);

  osc.connect(gain);
  gain.connect(categories.ui);
  osc.start(audio.currentTime);
  osc.stop(audio.currentTime + 0.15);
}

/** Play drill-down swoosh */
export function playDrillDown() {
  if (!enabled) return;
  const audio = getContext();
  if (!audio || !categories.effects) return;

  const osc = audio.createOscillator();
  const gain = audio.createGain();

  osc.type = "sine";
  osc.frequency.setValueAtTime(600, audio.currentTime);
  osc.frequency.exponentialRampToValueAtTime(200, audio.currentTime + 0.3);

  gain.gain.setValueAtTime(0.1, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.3);

  osc.connect(gain);
  gain.connect(categories.effects);
  osc.start(audio.currentTime);
  osc.stop(audio.currentTime + 0.35);
}

/** Play drill-up whoosh */
export function playDrillUp() {
  if (!enabled) return;
  const audio = getContext();
  if (!audio || !categories.effects) return;

  const osc = audio.createOscillator();
  const gain = audio.createGain();

  osc.type = "sine";
  osc.frequency.setValueAtTime(200, audio.currentTime);
  osc.frequency.exponentialRampToValueAtTime(600, audio.currentTime + 0.25);

  gain.gain.setValueAtTime(0.1, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.25);

  osc.connect(gain);
  gain.connect(categories.effects);
  osc.start(audio.currentTime);
  osc.stop(audio.currentTime + 0.3);
}

/** Play earthquake rumble — intensity 0-1 */
export function playEarthquakeRumble(intensity = 0.5) {
  if (!enabled) return;
  const audio = getContext();
  if (!audio || !categories.effects) return;

  // Low-frequency rumble using noise
  const duration = 1.0 + intensity;
  const bufferSize = audio.sampleRate * duration;
  const buffer = audio.createBuffer(1, bufferSize, audio.sampleRate);
  const data = buffer.getChannelData(0);

  // Brown noise (low frequency rumble)
  let last = 0;
  for (let i = 0; i < bufferSize; i++) {
    const white = Math.random() * 2 - 1;
    last = (last + 0.02 * white) / 1.02;
    data[i] = last * 3.5;
  }

  const source = audio.createBufferSource();
  source.buffer = buffer;

  const gain = audio.createGain();
  const scaledIntensity = 0.08 * intensity;
  gain.gain.setValueAtTime(scaledIntensity, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(
    0.001,
    audio.currentTime + duration,
  );

  // Low pass for rumble feel
  const filter = audio.createBiquadFilter();
  filter.type = "lowpass";
  filter.frequency.value = 150;

  source.connect(filter);
  filter.connect(gain);
  gain.connect(categories.effects);
  source.start(audio.currentTime);
  source.stop(audio.currentTime + duration);
}

/** Play UI click */
export function playClick() {
  if (!enabled) return;
  const audio = getContext();
  if (!audio || !categories.ui) return;

  const osc = audio.createOscillator();
  const gain = audio.createGain();

  osc.type = "sine";
  osc.frequency.value = 1000;
  gain.gain.setValueAtTime(0.08, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.05);

  osc.connect(gain);
  gain.connect(categories.ui);
  osc.start(audio.currentTime);
  osc.stop(audio.currentTime + 0.05);
}
