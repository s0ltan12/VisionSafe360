import React from 'react';
import { cn, toneClasses, type Tone } from './designSystem';

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  tone?: Tone;
};

export const Badge = ({ tone = 'neutral', className, children, ...props }: BadgeProps) => (
  <span
    className={cn('inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider', toneClasses[tone], className)}
    {...props}
  >
    {children}
  </span>
);
