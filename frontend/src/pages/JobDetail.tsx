import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import type { JobLogsResponse } from '../api/types';
import { StatusTag } from '../components/ui/StatusTag';
import { PipelineStepper } from '../components/PipelineStepper';
import { FileRow } from '../components/FileRow';
import { LogBlock } from '../components/LogBlock';
import { formatDate, truncateId } from '../lib/format';

type Tab = 'progress' | 'outputs' | 'logs' | 'config';

const TABS: { key: Tab; label: string }[] = [
  { key: 'progress', label: 'Progress' },
  { key: 'outputs', label: 'Outputs' },
  { key: 'logs', label: 'Logs' },
  { key: 'config', label: 'Config' },
];

export default function JobDetail() {
  const { jobId = '' } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('progress');
  const [deleting, setDeleting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);

  const jobQ = usePolling(() => api.getJob(jobId), 2000, !!jobId);
  const filesQ = usePolling(
    () => api.getJobFiles(jobId),
    5000,
    !!jobId && tab === 'outputs',
  );
  const logsQ = usePolling(
    () => api.getJobLogs(jobId),
    5000,
    !!jobId && tab === 'logs',
  );
  const configQ = usePolling(
    () => api.getJobConfig(jobId),
    60000,
    !!jobId && tab === 'config',
  );

  const job = jobQ.data;
  const running = job?.status === 'running';
  const cancellable = job?.status === 'running' || job?.status === 'pending';

  const onCancel = async () => {
    if (!window.confirm('Cancel this job? The pipeline subprocess will be killed.'))
      return;
    setCancelling(true);
    setDelError(null);
    try {
      await api.cancelJob(jobId);
      // The poller picks up the cancelled state on its next tick.
    } catch (e) {
      setDelError(e instanceof Error ? e.message : 'Cancel failed');
    } finally {
      setCancelling(false);
    }
  };

  const onDelete = async () => {
    if (!window.confirm('Delete this job and all its files?')) return;
    setDeleting(true);
    setDelError(null);
    try {
      await api.deleteJob(jobId);
      navigate('/');
    } catch (e) {
      setDelError(e instanceof Error ? e.message : 'Delete failed');
      setDeleting(false);
    }
  };

  if (jobQ.error && !job) {
    return (
      <div className="border border-line py-16 text-center font-mono text-[12px] uppercase tracking-[0.2em] text-status-failed">
        {jobQ.error}
      </div>
    );
  }
  if (!job) {
    return (
      <div className="border border-line py-16 text-center font-mono text-[12px] uppercase tracking-[0.2em] text-muted">
        LOADING /jobs/{truncateId(jobId, 8)}…
      </div>
    );
  }

  return (
    <div className="grid grid-cols-12 gap-8">
      <div className="col-span-3">
        <div className="label-mono">JOB</div>
        <div className="mt-3 font-mono text-sm text-ink break-all">
          {job.job_id}
        </div>
      </div>
      <div className="col-span-9 flex items-end justify-between">
        <div className="flex items-center gap-4">
          <StatusTag status={job.status} />
          <span className="font-mono text-[11px] text-muted">
            {formatDate(job.created_at)} → {formatDate(job.completed_at)}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {cancellable && (
            <button
              onClick={onCancel}
              disabled={cancelling}
              className="font-mono text-[11px] uppercase tracking-[0.15em] text-ink border border-accent px-3 py-2 hover:bg-accent hover:text-bg disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {cancelling ? 'Cancelling…' : 'Cancel'}
            </button>
          )}
          <button
            onClick={onDelete}
            disabled={running || deleting}
            className="font-mono text-[11px] uppercase tracking-[0.15em] text-status-failed border border-line px-3 py-2 hover:border-status-failed disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {running ? 'Running…' : 'Delete'}
          </button>
        </div>
      </div>

      <div className="col-span-12">
        <PipelineStepper stages={job.stages} currentStage={job.current_stage} />
      </div>

      {job.warnings?.length > 0 && (
        <div className="col-span-12 border-l-2 border-accent bg-surface px-4 py-3">
          <div className="label-mono mb-1">WARNINGS</div>
          {job.warnings.map((w, i) => (
            <div key={i} className="font-mono text-[12px] text-ink-2">
              {w}
            </div>
          ))}
        </div>
      )}
      {job.error && (
        <div className="col-span-12 border-l-2 border-status-failed bg-surface px-4 py-3 font-mono text-[12px] text-status-failed">
          {job.error}
        </div>
      )}
      {delError && (
        <div className="col-span-12 border-l-2 border-status-failed bg-surface px-4 py-3 font-mono text-[12px] text-status-failed">
          {delError}
        </div>
      )}

      <div className="col-span-12">
        <div className="flex gap-8 border-b-2 border-ink">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`-mb-px pb-3 font-mono text-[12px] uppercase tracking-[0.15em] ${
                tab === t.key
                  ? 'text-ink border-b-2 border-ink'
                  : 'text-muted hover:text-ink'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="py-6">
          {tab === 'progress' && (
            <div className="font-mono text-[13px] text-ink-2">
              Current stage:{' '}
              <span className="text-ink">{job.current_stage ?? '—'}</span>
            </div>
          )}

          {tab === 'outputs' && (
            <div>
              {filesQ.loading && !filesQ.data ? (
                <div className="font-mono text-[12px] uppercase tracking-[0.2em] text-muted">
                  LOADING…
                </div>
              ) : (filesQ.data?.files.length ?? 0) === 0 ? (
                <div className="font-mono text-[12px] uppercase tracking-[0.2em] text-muted">
                  NO OUTPUT FILES
                </div>
              ) : (
                filesQ.data!.files.map((f) => (
                  <FileRow key={f.filename} file={f} jobId={jobId} />
                ))
              )}
            </div>
          )}

          {tab === 'logs' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(
                (logsQ.data as JobLogsResponse | null)?.stage_logs ?? {},
              ).map(([stage, content]) => (
                <LogBlock key={stage} title={stage} content={content} />
              ))}
            </div>
          )}

          {tab === 'config' && (
            <pre className="border border-line p-4 font-mono text-[12px] text-ink-2 overflow-auto max-h-96">
              {JSON.stringify(configQ.data, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
