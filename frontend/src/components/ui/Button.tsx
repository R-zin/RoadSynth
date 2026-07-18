import type { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-accent-ink hover:bg-ink',
  secondary: 'bg-ink text-bg hover:bg-accent',
  ghost: 'bg-transparent text-ink border border-line hover:bg-surface',
};

export function Button({
  variant = 'primary',
  className = '',
  ...rest
}: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center px-4 py-3 text-[13px] font-bold uppercase tracking-[0.15em] rounded-none transition-colors duration-200 disabled:opacity-40 disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...rest}
    />
  );
}
