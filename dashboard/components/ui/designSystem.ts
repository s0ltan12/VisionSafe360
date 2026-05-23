export const toneClasses = {
  neutral: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  orange: 'bg-vs-orange/10 text-vs-orange border-vs-orange/20',
  danger: 'bg-red-500/10 text-red-400 border-red-500/20',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  info: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
} as const;

export type Tone = keyof typeof toneClasses;

export const cn = (...classes: Array<string | false | null | undefined>) =>
  classes.filter(Boolean).join(' ');
