import type { StageKey, StageStatus } from '../api/types';
import { STAGES } from '../api/types';

export function StageTicks({
  stages,
}: {
  stages: Partial<Record<StageKey, StageStatus>>;
}) {
  return (
    <div className="flex gap-1">
      {STAGES.map((s) => {
        const st = stages[s] ?? 'pending';
        const color =
          st === 'done'
            ? 'bg-status-done'
            : st === 'running'
              ? 'bg-status-running animate-pulse'
              : st === 'failed'
                ? 'bg-status-failed'
                : st === 'skipped'
                  ? 'bg-status-skipped'
                  : 'bg-status-pending/40';
        return (
          <span
            key={s}
            title={s}
            className={`w-3 h-3 ${color}`}
          />
        );
      })}
    </div>
  );
}
