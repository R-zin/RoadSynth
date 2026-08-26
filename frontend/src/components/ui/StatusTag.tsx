const STATUS_MAP: Record<
  string,
  { label: string; color: string; pulse?: boolean }
> = {
  pending: { label: 'PENDING', color: 'text-status-pending' },
  running: { label: 'RUNNING', color: 'text-status-running', pulse: true },
  done: { label: 'DONE', color: 'text-status-done' },
  failed: { label: 'FAILED', color: 'text-status-failed' },
  cancelled: { label: 'CANCELLED', color: 'text-status-skipped' },
  skipped: { label: 'SKIPPED', color: 'text-status-skipped' },
};

export function StatusTag({
  status,
  label,
}: {
  status: string;
  label?: string;
}) {
  const s = STATUS_MAP[status] ?? STATUS_MAP.pending;
  return (
    <span
      className={`inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.15em] ${s.color}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full bg-current ${s.pulse ? 'animate-pulse' : ''}`}
      />
      {label ?? s.label}
    </span>
  );
}
