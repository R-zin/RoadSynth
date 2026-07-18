import type { JobFile } from '../api/types';
import { api } from '../api/client';
import { formatBytes } from '../lib/format';

export function FileRow({ file }: { file: JobFile }) {
  return (
    <div className="grid grid-cols-12 items-center gap-4 py-3 border-b border-line">
      <div className="col-span-6 font-mono text-[13px] text-ink">
        {file.filename}
      </div>
      <div className="col-span-3 font-mono text-[12px] text-muted">
        {formatBytes(file.size_bytes)}
      </div>
      <div className="col-span-3 flex justify-end">
        <a
          href={`${api.base}${file.download_url}`}
          download
          className="font-mono text-[11px] uppercase tracking-[0.15em] text-accent hover:text-ink border border-line px-3 py-2 hover:border-ink"
        >
          Download
        </a>
      </div>
    </div>
  );
}
