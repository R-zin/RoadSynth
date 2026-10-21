import { api } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import { StatusTag } from '../components/ui/StatusTag';

const TOOLS = [
  'netconvert',
  'duarouter',
  'sumo',
  'traceExporter.py',
  'randomTrips.py',
];

const ENDPOINTS: { method: string; path: string }[] = [
  { method: 'GET', path: '/health' },
  { method: 'GET', path: '/schema' },
  { method: 'GET', path: '/defaults' },
  { method: 'POST', path: '/jobs' },
  { method: 'GET', path: '/jobs' },
  { method: 'GET', path: '/jobs/{id}' },
  { method: 'GET', path: '/jobs/{id}/files' },
  { method: 'GET', path: '/jobs/{id}/logs' },
  { method: 'GET', path: '/jobs/{id}/config' },
  { method: 'DELETE', path: '/jobs/{id}' },
];

export default function System() {
  const health = usePolling(() => api.getReady(), 10000);
  const h = health.data;

  return (
    <div className="grid grid-cols-12 gap-8">
      <div className="col-span-3">
        <div className="label-mono">SYSTEM</div>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight">
          Pipeline Health
        </h1>
        <p className="mt-4 font-mono text-[11px] uppercase tracking-[0.15em] text-muted">
          GET /health
        </p>
      </div>

      <div className="col-span-9">
        {!h ? (
          <div className="border border-line py-16 text-center font-mono text-[12px] uppercase tracking-[0.2em] text-muted">
            LOADING /health…
          </div>
        ) : (
          <div className="flex flex-col gap-8">
            <div className="border border-line p-6">
              <div className="label-mono mb-3">OVERALL STATUS</div>
              <div className="flex items-center gap-4">
                <span
                  className={`font-mono text-4xl font-bold tracking-tight ${
                    h.pipeline_ready ? 'text-status-done' : 'text-status-failed'
                  }`}
                >
                  {h.status.toUpperCase()}
                </span>
                <StatusTag
                  status={h.pipeline_ready ? 'done' : 'failed'}
                  label={h.pipeline_ready ? 'PIPELINE READY' : 'PIPELINE NOT READY'}
                />
              </div>
              <div className="mt-3 font-mono text-[12px] text-muted">
                pipeline_ready: {String(h.pipeline_ready)}
              </div>
            </div>

            <div className="border border-line">
              <div className="border-b border-line px-4 py-3 font-mono text-[11px] uppercase tracking-[0.2em] text-muted bg-surface">
                SUMO TOOL AVAILABILITY
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-line">
                {TOOLS.map((tool) => (
                  <div
                    key={tool}
                    className="px-4 py-4 flex items-center justify-between"
                  >
                    <span className="font-mono text-[13px] text-ink">{tool}</span>
                    <StatusTag
                      status={h.tools[tool] ? 'done' : 'failed'}
                      label={h.tools[tool] ? 'AVAILABLE' : 'MISSING'}
                    />
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-line">
              <div className="border-b border-line px-4 py-3 font-mono text-[11px] uppercase tracking-[0.2em] text-muted bg-surface">
                API ENDPOINTS
              </div>
              <div className="divide-y divide-line">
                {ENDPOINTS.map((e) => (
                  <div key={e.path} className="px-4 py-3 flex items-center gap-4">
                    <span
                      className={`font-mono text-[11px] uppercase tracking-[0.15em] w-16 ${
                        e.method === 'GET' ? 'text-status-done' : 'text-accent'
                      }`}
                    >
                      {e.method}
                    </span>
                    <span className="font-mono text-[13px] text-ink">{e.path}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
