import { useState } from 'react';
import type { JobFile } from '../api/types';
import { api } from '../api/client';
import { formatBytes } from '../lib/format';

export function FileRow({ file, jobId }: { file: JobFile; jobId: string }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onDownload = async () => {
    setDownloading(true);
    setError(null);
    try {
      await api.downloadFile(jobId, file.filename);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="grid grid-cols-12 items-center gap-4 py-3 border-b border-line">
      <div className="col-span-6 font-mono text-[13px] text-ink">
        {file.filename}
        {error && (
          <span className="ml-3 font-mono text-[10px] text-status-failed">
            {error}
          </span>
        )}
      </div>
      <div className="col-span-3 font-mono text-[12px] text-muted">
        {formatBytes(file.size_bytes)}
      </div>
      <div className="col-span-3 flex justify-end">
        <button
          onClick={onDownload}
          disabled={downloading}
          className="font-mono text-[11px] uppercase tracking-[0.15em] text-accent hover:text-ink border border-line px-3 py-2 hover:border-ink disabled:opacity-40"
        >
          {downloading ? 'Saving…' : 'Download'}
        </button>
      </div>
    </div>
  );
}
