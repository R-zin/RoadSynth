import { Link } from 'react-router-dom';
import type { JobStatus } from '../api/types';
import { StatusTag } from './ui/StatusTag';
import { StageTicks } from './StageTicks';
import { formatDate, truncateId } from '../lib/format';

export function JobTable({ jobs }: { jobs: JobStatus[] }) {
  if (jobs.length === 0) {
    return (
      <div className="border border-line py-16 text-center font-mono text-[12px] uppercase tracking-[0.2em] text-muted">
        NO JOBS YET
      </div>
    );
  }
  return (
    <div className="border-t border-line">
      {jobs.map((job) => (
        <div
          key={job.job_id}
          className="grid grid-cols-12 items-center gap-4 py-4 border-b border-line hover:bg-surface transition-colors"
        >
          <div className="col-span-3 font-mono text-[13px] text-ink">
            {truncateId(job.job_id, 12)}
          </div>
          <div className="col-span-2">
            <StatusTag status={job.status} />
          </div>
          <div className="col-span-2 font-mono text-[12px] text-muted">
            {formatDate(job.created_at)}
          </div>
          <div className="col-span-3">
            <StageTicks stages={job.stages} />
          </div>
          <div className="col-span-2 flex items-center justify-end">
            <Link
              to={`/jobs/${job.job_id}`}
              className="font-mono text-[11px] uppercase tracking-[0.15em] text-accent hover:text-ink"
            >
              View
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}
