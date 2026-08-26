import type { ReadyResponse } from '../api/types';
import { StatusTag } from './ui/StatusTag';

const TOOL_ORDER = [
  'netconvert',
  'duarouter',
  'sumo',
  'traceExporter.py',
  'randomTrips.py',
];

export function HealthStrip({ health }: { health: ReadyResponse | null }) {
  if (!health) return null;
  return (
    <div className="border border-line">
      <div className="border-b border-line px-4 py-3 flex items-center justify-between bg-surface">
        <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">
          PIPELINE HEALTH
        </span>
        <StatusTag
          status={health.pipeline_ready ? 'done' : 'failed'}
          label={health.status.toUpperCase()}
        />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 divide-x divide-line">
        {TOOL_ORDER.map((tool) => (
          <div
            key={tool}
            className="px-4 py-3 flex items-center justify-between"
          >
            <span className="font-mono text-[11px] text-ink-2">{tool}</span>
            <StatusTag
              status={health.tools[tool] ? 'done' : 'failed'}
              label={health.tools[tool] ? 'OK' : 'MISSING'}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
