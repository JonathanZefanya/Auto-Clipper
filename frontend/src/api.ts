// Client tipis untuk backend FastAPI (lihat Feature.md "Rancangan API").

export type JobStatus =
  | 'queued'
  | 'downloading'
  | 'analyzing'
  | 'ready_for_review'
  | 'transcribing'
  | 'rendering'
  | 'done'
  | 'failed'

export const ACTIVE_STATUSES: JobStatus[] = ['queued', 'downloading', 'analyzing', 'transcribing', 'rendering']

export interface Job {
  id: string
  url: string
  video_id: string
  title: string
  channel: string
  duration: number
  thumbnail: string | null
  has_chat: boolean
  template: string
  status: JobStatus
  progress: number
  message: string | null
  error: string | null
  task: 'detect' | 'transcribe' | 'render'
  created_at: string
  updated_at: string
  queue_position: number | null
  candidate_count: number
  selected_count: number
  clip_count: number
}

export interface Candidate {
  id: number
  job_id: string
  rank: number
  peak_time: number
  start: number
  end: number
  duration: number
  score: number
  selected: boolean
  clip_path: string | null
  thumb_path: string | null
  thumb_landscape_path: string | null
  thumb_text: string | null
  credit_path: string | null
  subs_path: string | null
  title: string | null
  suggestions: TitleSuggestions | null
  clip_url: string | null
  thumb_url: string | null
  thumb_landscape_url: string | null
}

export interface RenderOptions {
  subtitle: boolean
  thumbnail: boolean
  landscape: boolean
  intro_frame: boolean
  only_thumbs: boolean
}

export interface JobDetail extends Job {
  candidates: Candidate[]
  render_options: RenderOptions | null
}

export interface Preview {
  video_id: string
  url: string
  title: string
  channel: string
  duration: number
  thumbnail: string | null
  live_status: string | null
  chat_available: boolean
}

export interface Scores {
  duration: number
  has_chat: boolean
  has_reaction: boolean
  threshold: number
  used_fallback: boolean
  excluded: [number, number][]
  smoothed: number[]
  audio: number[] | null
  chat: number[] | null
  reaction: number[] | null
  has_face: boolean
  face: number[] | null
  face_info: { box?: Box; detect_frac?: number; skipped?: string } | null
  candidates: Pick<Candidate, 'id' | 'rank' | 'peak_time' | 'start' | 'end' | 'score' | 'selected'>[]
}

export interface Box {
  x: number
  y: number
  w: number
  h: number
}

export interface Template {
  name: string
  layout_type: 'split' | 'center_crop'
  facecam_box: Box | null
  gameplay_box: Box | null
  top_ratio: number
  builtin?: boolean
}

export interface TitleSuggestions {
  titles: string[]
  description: string
  hashtags: string[]
  model: string
  note?: string   // mis. "Ollama tidak jalan … Saran sederhana tanpa LLM"
}

export interface LlmStatus {
  enabled: boolean
  url: string
  model: string
  available: boolean
  models: string[]
  model_ready: boolean
  error: string | null
}

export interface SubLine {
  start: number
  end: number
  text: string
}

export interface Subtitles {
  candidate_id: number
  duration: number
  edited: boolean
  stale: boolean
  outdated: boolean
  clip_start: number
  clip_end: number
  lines: SubLine[]
}

export interface FacecamResult {
  facecam_box: Box
  face_box: Box
  hits: number
  frames: number
  confidence: number
  time: number
}

export interface Settings {
  data_dir: string
  data_dir_configured: string
  restart_required: boolean
  config_file: string
  detect: Record<string, number | boolean>
  render: Record<string, string | number>
  subtitle: Record<string, string | number | boolean>
  thumbnail: Record<string, string | number | boolean>
  title: Record<string, string | number | boolean>
  options: {
    whisper_models: string[]
    download_heights: number[]
    devices: string[]
    encoders: string[]
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: unknown) => (isRecord(d) && 'msg' in d ? String(d.msg) : String(d)))
      .join('; ')
  }
  return fallback
}

async function sendRequest(method: string, path: string, body?: unknown): Promise<Response> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const parsed: unknown = await res.json()
      if (isRecord(parsed) && 'detail' in parsed) {
        msg = detailMessage(parsed.detail, msg)
      }
    } catch {
      /* respons bukan JSON */
    }
    throw new ApiError(res.status, msg)
  }
  return res
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await sendRequest(method, path, body)
  return await res.json()
}

async function requestVoid(method: string, path: string, body?: unknown): Promise<void> {
  await sendRequest(method, path, body)
}

export const api = {
  preview: (url: string) => request<Preview>('POST', '/api/jobs/preview', { url }),
  createJob: (body: { url: string; template: string } & Partial<Preview>) =>
    request<Job>('POST', '/api/jobs', body),
  listJobs: () => request<Job[]>('GET', '/api/jobs'),
  getJob: (id: string) => request<JobDetail>('GET', `/api/jobs/${id}`),
  updateJob: (id: string, body: { template: string }) => request<Job>('PATCH', `/api/jobs/${id}`, body),
  deleteJob: (id: string) => requestVoid('DELETE', `/api/jobs/${id}`),
  scores: (id: string) => request<Scores>('GET', `/api/jobs/${id}/scores`),
  setSelection: (id: string, body: { selected?: boolean; ids?: number[] }) =>
    request<JobDetail>('POST', `/api/jobs/${id}/selection`, body),
  patchCandidate: (
    id: number,
    body: Partial<Pick<Candidate, 'selected' | 'start' | 'end'>> & { thumb_text?: string; title?: string },
  ) => request<Candidate>('PATCH', `/api/candidates/${id}`, body),
  suggestTitles: (id: number) => request<Candidate>('POST', `/api/candidates/${id}/titles`),
  llmStatus: () => request<LlmStatus>('GET', '/api/llm/status'),
  render: (id: string, body: Partial<RenderOptions> & { template?: string }) =>
    request<Job>('POST', `/api/jobs/${id}/render`, body),
  cancelJob: (id: string) => request<Job>('POST', `/api/jobs/${id}/cancel`),
  transcribe: (id: string) => request<Job>('POST', `/api/jobs/${id}/transcribe`),
  getSubtitles: (candidateId: number) => request<Subtitles>('GET', `/api/candidates/${candidateId}/subtitles`),
  saveSubtitles: (candidateId: number, lines: SubLine[]) =>
    request<Subtitles>('PUT', `/api/candidates/${candidateId}/subtitles`, { lines }),
  resetSubtitles: (candidateId: number) => requestVoid('DELETE', `/api/candidates/${candidateId}/subtitles`),
  detectFacecam: (id: string, top_ratio: number) =>
    request<FacecamResult>('POST', `/api/jobs/${id}/detect-facecam`, { top_ratio }),
  openFolder: (id: string) => request<{ path: string; opened: boolean }>('POST', `/api/jobs/${id}/open-folder`),
  templates: () => request<Template[]>('GET', '/api/templates'),
  saveTemplate: (t: Template) => request<Template>('POST', '/api/templates', t),
  deleteTemplate: (name: string) => requestVoid('DELETE', `/api/templates/${name}`),
  settings: () => request<Settings>('GET', '/api/settings'),
  saveSettings: (body: Record<string, unknown>) => request<Settings>('PUT', '/api/settings', body),

  sourceUrl: (id: string) => `/api/jobs/${id}/source`,
  frameUrl: (id: string, t: number, width = 1280) => `/api/jobs/${id}/frame?t=${t.toFixed(2)}&width=${width}`,
  zipUrl: (id: string) => `/api/jobs/${id}/download`,
  eventsUrl: (id: string) => `/api/jobs/${id}/events`,
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
