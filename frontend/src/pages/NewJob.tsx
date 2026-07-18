import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { ConversionRequest } from '../api/types';
import { ConfigForm } from '../components/ConfigForm';
import { Button } from '../components/ui/Button';

const emptyConfig = (): ConversionRequest => ({
  netconvert: {},
  random_trips: {},
  sumo: {},
  trace_exporter: {},
});

export default function NewJob() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [config, setConfig] = useState<ConversionRequest>(emptyConfig());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getDefaults()
      .then(setConfig)
      .catch(() => setConfig(emptyConfig()));
  }, []);

  const onField = (
    section: keyof ConversionRequest,
    key: string,
    val: unknown,
  ) => {
    setConfig((c) => ({
      ...c,
      [section]: { ...(c[section] as Record<string, unknown>), [key]: val },
    }));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError('Select an OSM file first.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.createJob(file, config);
      navigate(`/jobs/${res.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="grid grid-cols-12 gap-8">
      <div className="col-span-3">
        <div className="label-mono">NEW JOB</div>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight">
          Start Conversion
        </h1>
        <p className="mt-4 font-mono text-[11px] uppercase tracking-[0.15em] text-muted">
          POST /jobs · multipart
        </p>
      </div>

      <div className="col-span-9 flex flex-col gap-8">
        {/* Upload */}
        <section className="border border-line p-6">
          <h2 className="font-mono text-[13px] uppercase tracking-[0.15em] text-ink mb-4">
            Upload OSM File
          </h2>
          <label className="flex flex-col items-center justify-center border border-dashed border-line py-12 cursor-pointer hover:border-ink transition-colors">
            <span className="font-mono text-[12px] uppercase tracking-[0.2em] text-muted">
              DROP .osm / .osm.pbf
            </span>
            <span className="mt-3 font-mono text-[11px] uppercase tracking-[0.15em] text-accent">
              Select File
            </span>
            <input
              type="file"
              accept=".osm,.osm.pbf,.xml,.pbf"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          {file && (
            <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
              <span className="font-mono text-[13px] text-ink">{file.name}</span>
              <button
                type="button"
                onClick={() => setFile(null)}
                className="font-mono text-[11px] uppercase tracking-[0.15em] text-status-failed hover:underline"
              >
                Remove
              </button>
            </div>
          )}
        </section>

        {/* Config */}
        <section className="border border-line p-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-mono text-[13px] uppercase tracking-[0.15em] text-ink">
              Pipeline Configuration
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted">
              PRE-FILLED FROM GET /defaults
            </span>
          </div>
          <ConfigForm value={config} onChange={onField} />
        </section>

        {error && (
          <div className="border-l-2 border-status-failed bg-surface px-4 py-3 font-mono text-[12px] text-status-failed">
            {error}
          </div>
        )}

        <div className="flex items-center justify-between border-t border-line pt-6">
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Starting…' : 'Start Job'}
          </Button>
          <button
            type="button"
            onClick={() => {
              setConfig(emptyConfig());
              api.getDefaults().then(setConfig).catch(() => {});
            }}
            className="font-mono text-[11px] uppercase tracking-[0.15em] text-muted hover:text-ink"
          >
            Reset to defaults
          </button>
        </div>
      </div>
    </form>
  );
}
