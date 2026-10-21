import type { JsonSchema } from './schema';
import type {
  ConversionRequest,
  JobFilesResponse,
  JobLogsResponse,
  JobStatus,
  ReadyResponse,
} from './types';

/** Same-origin by default (Docker serving); dev sets VITE_API_BASE. */
const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

// ── API key (opt-in; server enforces only when OSM2NS3_API_KEY is set) ──

const KEY_STORAGE = 'osm2ns3.apiKey';

let apiKey: string = localStorage.getItem(KEY_STORAGE) ?? '';

export function getApiKey(): string {
  return apiKey;
}

export function setApiKey(key: string): void {
  apiKey = key;
  if (key) localStorage.setItem(KEY_STORAGE, key);
  else localStorage.removeItem(KEY_STORAGE);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = '';
    try {
      const j = await res.json();
      detail = j.detail ?? JSON.stringify(j);
    } catch {
      detail = await res.text();
    }
    if (res.status === 401) {
      detail = `Unauthorized — set a valid API key in the nav bar. ${detail}`.trim();
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
  cancelJob: (id: string) =>
    request<JobStatus>(`/jobs/${id}/cancel`, { method: 'POST' }),
  deleteJob: (id: string) =>
    request<void>(`/jobs/${id}`, { method: 'DELETE' }),
  /**
   * Readiness is *conveyed* by HTTP status (200 = ready, 503 = degraded), so a
   * 503 is a valid answer, not a request failure — fetch directly, never throw.
   */
  getReady: async (): Promise<ReadyResponse | null> => {
    try {
      const res = await fetch(`${API_BASE}/ready`);
      return (await res.json()) as ReadyResponse;
    } catch {
      return null; // server unreachable entirely
    }
  },
  getDefaults: () => request<ConversionRequest>('/defaults'),
  getSchema: () => request<JsonSchema>('/schema'),

  createJob: (osmFile: File, config: ConversionRequest) => {
    const fd = new FormData();
    fd.append('osm_file', osmFile);
    fd.append('config', JSON.stringify(config));
    return request<CreateJobResult>('/jobs', { method: 'POST', body: fd });
  },

  /** Authenticated blob download (X-API-Key cannot ride on a plain <a href>). */
  downloadFile: async (id: string, filename: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/jobs/${id}/download/${filename}`, {
      headers: apiKey ? { 'X-API-Key': apiKey } : {},
    });
    if (!res.ok) {
      let detail = '';
      try {
        const j = await res.json();
        detail = j.detail ?? JSON.stringify(j);
      } catch {
        detail = await res.text();
      }
      throw new Error(detail || `Download failed: ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
