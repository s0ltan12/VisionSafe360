import React from 'react';
import { AlertCircle } from 'lucide-react';
import { a11yClasses } from '../../utils/accessibility';
import { cn } from './designSystem';

type FieldRootProps = {
  label: string;
  htmlFor?: string;
  error?: string;
  errorId?: string;
  helpText?: string;
  helpId?: string;
  children: React.ReactNode;
};

export const FieldRoot = ({ label, htmlFor, error, errorId, helpText, helpId, children }: FieldRootProps) => (
  <div className="space-y-2">
    <label htmlFor={htmlFor} className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
      {label}
    </label>
    {children}
    {error ? (
      <div id={errorId} role="alert" className="text-red-500 text-xs mt-1 flex items-center gap-1">
        <AlertCircle size={14} aria-hidden="true" />
        <span>{error}</span>
      </div>
    ) : helpText ? (
      <div id={helpId} className="text-xs text-zinc-600">{helpText}</div>
    ) : null}
  </div>
);

const fieldClasses =
  'w-full bg-[#050505] border border-zinc-800 rounded-lg p-3 text-sm text-white outline-none transition-colors placeholder-zinc-700 focus:border-vs-orange disabled:cursor-not-allowed disabled:opacity-50';

type TextInputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  leadingIcon?: React.ReactNode;
  error?: boolean;
};

export const TextInput = React.forwardRef<HTMLInputElement, TextInputProps>(
  ({ leadingIcon, error, className, ...props }, ref) => (
    <div className="relative">
      {leadingIcon ? (
        <span className="absolute start-3 top-1/2 -translate-y-1/2 text-zinc-600" aria-hidden="true">
          {leadingIcon}
        </span>
      ) : null}
      <input
        ref={ref}
        className={cn(fieldClasses, leadingIcon && 'ps-10', error && 'border-red-500/50', a11yClasses.focusRing, className)}
        aria-invalid={error || undefined}
        {...props}
      />
    </div>
  ),
);

TextInput.displayName = 'TextInput';

type SelectFieldProps = React.SelectHTMLAttributes<HTMLSelectElement> & {
  error?: boolean;
};

export const SelectField = React.forwardRef<HTMLSelectElement, SelectFieldProps>(
  ({ error, className, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(fieldClasses, 'text-zinc-300', error && 'border-red-500/50', a11yClasses.focusRing, className)}
      aria-invalid={error || undefined}
      {...props}
    />
  ),
);

SelectField.displayName = 'SelectField';

type TextAreaFieldProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  error?: boolean;
};

export const TextAreaField = React.forwardRef<HTMLTextAreaElement, TextAreaFieldProps>(
  ({ error, className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(fieldClasses, 'resize-none', error && 'border-red-500/50', a11yClasses.focusRing, className)}
      aria-invalid={error || undefined}
      {...props}
    />
  ),
);

TextAreaField.displayName = 'TextAreaField';
