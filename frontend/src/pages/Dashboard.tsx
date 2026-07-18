import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import { JobTable } from '../components/JobTable';
import { HealthStrip } from '../components/HealthStrip';
import { Button } from '../components/ui/Button';

export default function Dashboard() {
  const navigate = useNavigate();
  const jobs = usePolling(() => api.listJobs(), 4000);
  const health = usePolling(() => api.getHealth(), 10000);

  return (
    <div className="grid grid-cols-12 gap-8">
      <div className="col-span-3">
        <div className="label-mono">JOBS</div>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight">
          Conversion Jobs
        </h1>
      </div>
      <div className="col-span-9 flex items-end justify-between">
        <span className="label-mono">POLLING /jobs</span>
        <Button onClick={() => navigate('/new')}>New Job</Button>
      </div>

      <div className="col-span-12">
        {jobs.loading && jobs.data === null ? (
          <div className="border border-line py-16 text-center font-mono text-[12px] uppercase tracking-[0.2em] text-muted">
            LOADING /jobs…
          </div>
        ) : jobs.error ? (
          <div className="border border-line py-16 text-center font-mono text-[12px] uppercase tracking-[0.2em] text-status-failed">
            {jobs.error}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-12 gap-4 pb-3 border-b-2 border-ink font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
              <div className="col-span-3">Job ID</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2">Created</div>
              <div className="col-span-3">Stages</div>
              <div className="col-span-2 text-right">Actions</div>
            </div>
            <JobTable jobs={jobs.data ?? []} />
          </>
        )}
      </div>

      <div className="col-span-12 mt-4">
        <HealthStrip health={health.data} />
      </div>
    </div>
  );
}
