export type StageStatus =
  | 'pending'
  | 'running'
  | 'done'
  | 'failed'
  | 'skipped';

export type StageKey =
  | 'netconvert'
  | 'random_trips'
  | 'duarouter'
  | 'sumo'
  | 'trace_export';

/** Ordered pipeline stages (matches the API's stage order). */
export const STAGES: StageKey[] = [
  'netconvert',
  'random_trips',
  'duarouter',
  'sumo',
  'trace_export',
];

export interface JobStatus {
  job_id: string;
  status: StageStatus;
  current_stage: StageKey | null;
  stages: Partial<Record<StageKey, StageStatus>>;
  stage_logs: Record<string, unknown>;
  error: string | null;
  outputs: string[];
  created_at: string;
  completed_at: string | null;
  warnings: string[];
}

export interface JobFile {
  filename: string;
  size_bytes: number;
  download_url: string;
}

export interface JobFilesResponse {
  job_id: string;
  files: JobFile[];
}

export interface JobLogsResponse {
  job_id: string;
  warnings: string[];
  stage_logs: Record<string, string | null>;
}

export interface HealthResponse {
  status: 'ready' | 'degraded';
  tools: Record<string, boolean>;
  pipeline_ready: boolean;
}

/** Nested pipeline configuration posted with the OSM file. */
export interface ConversionRequest {
  netconvert: Record<string, unknown>;
  random_trips: Record<string, unknown>;
  sumo: Record<string, unknown>;
  trace_exporter: Record<string, unknown>;
}
