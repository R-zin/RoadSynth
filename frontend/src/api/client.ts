import type {
  ConversionRequest,
  HealthResponse,
  JobFilesResponse,
  JobLogsResponse,
  JobStatus,
} from './types';

const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) || 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = '';
    try {
      const j = await res.json();
      detail = j.detail ?? JSON.stringify(j);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface CreateJobResult {
  job_id: string;
  message: string;
  config_snapshot: ConversionRequest;
}

export const api = {
  base: API_BASE,

  listJobs: () => request<JobStatus[]>('/jobs'),
  getJob: (id: string) => request<JobStatus>(`/jobs/${id}`),
  getJobFiles: (id: string) =>
    request<JobFilesResponse>(`/jobs/${id}/files`),
  getJobLogs: (id: string) => request<JobLogsResponse>(`/jobs/${id}/logs`),
  getJobConfig: (id: string) =>
    request<ConversionRequest>(`/jobs/${id}/config`),
  deleteJob: (id: string) =>
    request<void>(`/jobs/${id}`, { method: 'DELETE' }),
  getHealth: () => request<HealthResponse>('/health'),
  getDefaults: () => request<ConversionRequest>('/defaults'),
  getSchema: () => request<unknown>('/schema'),

  createJob: async (
    osmFile: File,
    config: ConversionRequest,
  ): Promise<CreateJobResult> => {
    const fd = new FormData();
    fd.append('osm_file', osmFile);
    fd.append('config', JSON.stringify(config));
    const res = await fetch(`${API_BASE}/jobs`, { method: 'POST', body: fd });
    if (!res.ok) {
      let detail = '';
      try {
        const j = await res.json();
        detail = j.detail ?? JSON.stringify(j);
      } catch {
        detail = await res.text();
      }
      throw new Error(detail || `Upload failed: ${res.status}`);
    }
    return (await res.json()) as CreateJobResult;
  },
};
