import type { Box, Template } from './api'

export const FULL: Box = { x: 0, y: 0, w: 1, h: 1 }

/** Gaya CSS yang meniru scale "cover" + crop tengah FFmpeg untuk satu kotak sumber → area tw×th. */
export function coverStyle(
  url: string, natural: { w: number; h: number }, b: Box | null, tw: number, th: number,
): Record<string, string | undefined> {
  const box = b ?? FULL
  const bw = box.w * natural.w
  const bh = box.h * natural.h
  const s = Math.max(tw / bw, th / bh)
  return {
    width: `${tw}px`,
    height: `${th}px`,
    backgroundImage: url ? `url(${url})` : undefined,
    backgroundSize: `${natural.w * s}px ${natural.h * s}px`,
    backgroundPosition: `${-box.x * natural.w * s - (bw * s - tw) / 2}px ${-box.y * natural.h * s - (bh * s - th) / 2}px`,
  }
}

/** Area-area preview 9:16 untuk sebuah template (atas–bawah untuk split, satu area untuk center). */
export function previewAreas(t: Template, width: number, height: number) {
  if (t.layout_type === 'split') {
    const top = Math.round(height * t.top_ratio)
    return [
      { key: 'facecam', box: t.facecam_box, w: width, h: top },
      { key: 'gameplay', box: t.gameplay_box, w: width, h: height - top },
    ]
  }
  return [{ key: 'gameplay', box: t.gameplay_box, w: width, h: height }]
}

/** Nama template dari nama channel, sesuai aturan backend ([A-Za-z0-9_-], maks 64). */
export function templateNameFor(channel: string, fallback: string): string {
  const slug = channel
    .normalize('NFKD')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48)
  return slug || fallback
}
