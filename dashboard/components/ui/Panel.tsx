import React from 'react';
import { cn } from './designSystem';

type PanelProps = React.HTMLAttributes<HTMLDivElement> & {
  padded?: boolean;
};

export const Panel = ({ padded = true, className, children, ...props }: PanelProps) => (
  <div
    className={cn('rounded-xl border border-zinc-800 bg-[#0f0f11]', padded && 'p-5', className)}
    {...props}
  >
    {children}
  </div>
);

type PageShellProps = React.HTMLAttributes<HTMLDivElement> & {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
};

export const PageShell = ({ title, description, actions, className, children, ...props }: PageShellProps) => (
  <div className={cn('p-6 space-y-6 h-full overflow-y-auto bg-[#050505]', className)} {...props}>
    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
      <div>
        <h2 className="text-2xl font-bold text-white">{title}</h2>
        {description ? <p className="text-sm text-zinc-500">{description}</p> : null}
      </div>
      {actions ? <div className="flex gap-3 rtl:space-x-reverse">{actions}</div> : null}
    </div>
    {children}
  </div>
);
