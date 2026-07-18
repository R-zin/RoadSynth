import type { ReactNode } from 'react';

export function Card({
  title,
  children,
  className = '',
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`border border-line bg-bg ${className}`}>
      {title && (
        <div className="border-b border-line px-4 py-3 font-mono text-[11px] uppercase tracking-[0.2em] text-muted bg-surface">
          {title}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
