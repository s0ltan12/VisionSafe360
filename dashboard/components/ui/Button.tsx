import React from 'react';
import { a11yClasses } from '../../utils/accessibility';
import { cn } from './designSystem';

type ButtonVariant = 'primary' | 'secondary' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
  isLoading?: boolean;
};

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-vs-orange text-black shadow-glow hover:bg-vs-lightOrange disabled:shadow-none',
  secondary: 'bg-zinc-900 border border-zinc-800 text-zinc-300 hover:bg-zinc-800 hover:text-white',
  ghost: 'text-zinc-500 hover:text-white hover:bg-zinc-900',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-[10px] rounded-md',
  md: 'px-4 py-2 text-xs rounded-lg',
  lg: 'px-5 py-3.5 text-xs rounded-xl',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'secondary',
      size = 'md',
      icon,
      trailingIcon,
      isLoading = false,
      disabled,
      className,
      children,
      ...props
    },
    ref,
  ) => (
    <button
      ref={ref}
      disabled={disabled || isLoading}
      className={cn(
        'inline-flex items-center justify-center gap-2 font-bold uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        variantClasses[variant],
        sizeClasses[size],
        a11yClasses.focusRing,
        className,
      )}
      {...props}
    >
      {isLoading ? (
        <span className="h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden="true" />
      ) : icon ? (
        <span aria-hidden="true">{icon}</span>
      ) : null}
      {children}
      {!isLoading && trailingIcon ? <span aria-hidden="true">{trailingIcon}</span> : null}
    </button>
  ),
);

Button.displayName = 'Button';
