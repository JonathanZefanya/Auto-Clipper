import type { Candidate } from './api'

export type Range = { start: number; end: number }

export function nextRange(c: Pick<Candidate, 'start' | 'end'>, edge: 'start' | 'end', delta: number): Range {
  return edge === 'start' ? { start: c.start + delta, end: c.end } : { start: c.start, end: c.end + delta }
}

/** Validasi sama dengan backend (F-07): start ≥ 0, end ≤ durasi video, 1 ≤ durasi ≤ maxClip. */
export function rangeValid(r: Range, lim: { maxClip: number; videoDuration: number }): boolean {
  const dur = r.end - r.start
  const maxEnd = lim.videoDuration > 0 ? lim.videoDuration : Infinity
  return r.start >= 0 && r.end <= maxEnd && dur >= 1 && dur <= lim.maxClip
}
