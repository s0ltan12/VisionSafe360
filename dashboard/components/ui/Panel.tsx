import React from 'react';
import { cn } from './designSystem';

type PanelProps = React.HTMLAttributes<HTMLDivElement> & {
  padded?: boolean;
};

export const Panel = ({ padded = true, className, children, ...props }: PanelProps) => (
  <div
    className={cn('min-w-0 rounded-xl border border-zinc-800 bg-[#0f0f11]', padded && 'p-5', className)}
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
  <div className={cn('h-full min-w-0 overflow-y-auto overflow-x-hidden bg-[#050505] p-4 sm:p-6 space-y-5 sm:space-y-6', className)} {...props}>
    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
      <div className="min-w-0">
        <h2 className="text-2xl font-bold text-white">{title}</h2>
        {description ? <p className="text-sm text-zinc-500">{description}</p> : null}
      </div>
      {actions ? <div className="flex w-full flex-wrap gap-3 rtl:space-x-reverse sm:w-auto">{actions}</div> : null}
    </div>
    {children}
  </div>
);
