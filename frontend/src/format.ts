import type { JobStatus } from './api'

export function fmtTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(sec).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

export function fmtDate(iso: string): string {
  return new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`).toLocaleString('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export const STATUS_LABEL: Record<JobStatus, string> = {
  queued: 'Antre',
  downloading: 'Mengunduh',
  analyzing: 'Menganalisis',
  ready_for_review: 'Siap direview',
  rendering: 'Merender',
  done: 'Selesai',
  failed: 'Gagal',
}

export const STATUS_CLASS: Record<JobStatus, string> = {
  queued: 'bg-zinc-800 text-zinc-300 ring-zinc-700',
  downloading: 'bg-sky-950 text-sky-300 ring-sky-800',
  analyzing: 'bg-amber-950 text-amber-300 ring-amber-800',
  ready_for_review: 'bg-violet-950 text-violet-300 ring-violet-800',
  rendering: 'bg-fuchsia-950 text-fuchsia-300 ring-fuchsia-800',
  done: 'bg-emerald-950 text-emerald-300 ring-emerald-800',
  failed: 'bg-red-950 text-red-300 ring-red-800',
}
