import type { StageKey, StageStatus } from '../api/types';
import { STAGES } from '../api/types';

function StageDot({ status }: { status: StageStatus }) {
  const color =
    status === 'done'
      ? 'bg-status-done'
      : status === 'running'
        ? 'bg-status-running animate-pulse'
        : status === 'failed'
          ? 'bg-status-failed'
          : status === 'skipped'
            ? 'bg-status-skipped'
            : 'bg-status-pending';
  return <span className={`w-2 h-2 rounded-full ${color}`} />;
}

export function PipelineStepper({
  stages,
  currentStage,
}: {
  stages: Partial<Record<StageKey, StageStatus>>;
  currentStage?: StageKey | null;
}) {
  return (
    <div className="flex items-stretch">
      {STAGES.map((stage, i) => {
        const st = stages[stage] ?? 'pending';
        const isCurrent = currentStage === stage;
        return (
          <div key={stage} className="flex items-stretch flex-1">
            <div
              className={`flex-1 px-4 py-4 border border-line bg-surface ${
                isCurrent ? 'ring-1 ring-inset ring-accent' : ''
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-[11px] text-muted">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <StageDot status={st} />
              </div>
              <div className="font-mono text-[12px] uppercase tracking-[0.1em] text-ink">
                {stage}
              </div>
              <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted mt-1">
                {st}
              </div>
            </div>
            {i < STAGES.length - 1 && (
              <div className="w-px bg-line h-auto self-stretch" />
            )}
          </div>
        );
      })}
    </div>
  );
}
