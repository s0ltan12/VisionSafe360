const SOUND_ENABLED_KEY = 'visionsafe360_notification_sound_enabled';
const DANGER_SOUND_URL = '/sounds/alart.wav';
const MIN_PLAY_INTERVAL_MS = 1400;
const MIN_DANGER_PLAY_INTERVAL_MS = 2200;

let audioContext: AudioContext | null = null;
let dangerAudio: HTMLAudioElement | null = null;
let lastPlayedAt = 0;
let lastDangerPlayedAt = 0;

export const getNotificationSoundEnabled = (): boolean => {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(SOUND_ENABLED_KEY) !== 'false';
};

export const setNotificationSoundEnabled = (enabled: boolean): void => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(SOUND_ENABLED_KEY, enabled ? 'true' : 'false');
};

export const unlockNotificationSound = (): void => {
  if (typeof window === 'undefined') return;
  const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext;
  if (!AudioContextCtor) return;

  try {
    audioContext = audioContext ?? new AudioContextCtor();
    if (audioContext.state === 'suspended') {
      void audioContext.resume();
    }
  } catch {
    audioContext = null;
  }
};

export const playNotificationSound = (): void => {
  if (!getNotificationSoundEnabled()) return;
  if (typeof window === 'undefined') return;

  const now = Date.now();
  if (now - lastPlayedAt < MIN_PLAY_INTERVAL_MS) return;

  const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext;
  if (!AudioContextCtor) return;

  try {
    audioContext = audioContext ?? new AudioContextCtor();
    if (audioContext.state === 'suspended') {
      void audioContext.resume();
    }

    const ctx = audioContext;
    const startAt = ctx.currentTime + 0.01;
    const master = ctx.createGain();
    master.gain.setValueAtTime(0.0001, startAt);
    master.gain.exponentialRampToValueAtTime(0.08, startAt + 0.02);
    master.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.42);
    master.connect(ctx.destination);

    [740, 988].forEach((frequency, index) => {
      const osc = ctx.createOscillator();
      const toneGain = ctx.createGain();
      const toneStart = startAt + index * 0.09;

      osc.type = 'sine';
      osc.frequency.setValueAtTime(frequency, toneStart);
      toneGain.gain.setValueAtTime(0.0001, toneStart);
      toneGain.gain.exponentialRampToValueAtTime(0.8, toneStart + 0.02);
      toneGain.gain.exponentialRampToValueAtTime(0.0001, toneStart + 0.22);

      osc.connect(toneGain);
      toneGain.connect(master);
      osc.start(toneStart);
      osc.stop(toneStart + 0.24);
    });

    lastPlayedAt = now;
  } catch {
    audioContext = null;
  }
};

const playGeneratedDangerFallback = (): void => {
  const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext;
  if (!AudioContextCtor) return;

  try {
    audioContext = audioContext ?? new AudioContextCtor();
    if (audioContext.state === 'suspended') {
      void audioContext.resume();
    }

    const ctx = audioContext;
    const startAt = ctx.currentTime + 0.01;
    const master = ctx.createGain();
    master.gain.setValueAtTime(0.0001, startAt);
    master.gain.exponentialRampToValueAtTime(0.095, startAt + 0.035);
    master.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.78);
    master.connect(ctx.destination);

    const createTone = (
      frequency: number,
      offset: number,
      duration: number,
      type: OscillatorType,
      gain: number,
    ) => {
      const toneStart = startAt + offset;
      const osc = ctx.createOscillator();
      const toneGain = ctx.createGain();

      osc.type = type;
      osc.frequency.setValueAtTime(frequency, toneStart);
      toneGain.gain.setValueAtTime(0.0001, toneStart);
      toneGain.gain.exponentialRampToValueAtTime(gain, toneStart + 0.03);
      toneGain.gain.exponentialRampToValueAtTime(0.0001, toneStart + duration);

      osc.connect(toneGain);
      toneGain.connect(master);
      osc.start(toneStart);
      osc.stop(toneStart + duration + 0.02);
    };

    [
      { frequency: 784, offset: 0, duration: 0.26, type: 'sine' as OscillatorType, gain: 0.72 },
      { frequency: 659, offset: 0.19, duration: 0.28, type: 'triangle' as OscillatorType, gain: 0.52 },
      { frequency: 523, offset: 0.4, duration: 0.34, type: 'sine' as OscillatorType, gain: 0.56 },
      { frequency: 196, offset: 0.02, duration: 0.62, type: 'sine' as OscillatorType, gain: 0.16 },
    ].forEach(({ frequency, offset, duration, type, gain }) => {
      createTone(frequency, offset, duration, type, gain);
    });
  } catch {
    audioContext = null;
  }
};

export const playDangerNotificationSound = (): void => {
  if (!getNotificationSoundEnabled()) return;
  if (typeof window === 'undefined') return;

  const now = Date.now();
  if (now - lastDangerPlayedAt < MIN_DANGER_PLAY_INTERVAL_MS) return;

  try {
    dangerAudio = dangerAudio ?? new Audio(DANGER_SOUND_URL);
    dangerAudio.preload = 'auto';
    dangerAudio.currentTime = 0;
    const playPromise = dangerAudio.play();
    if (playPromise) {
      playPromise.catch(() => playGeneratedDangerFallback());
    }
    lastDangerPlayedAt = now;
  } catch {
    playGeneratedDangerFallback();
  }
};
