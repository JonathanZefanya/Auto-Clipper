<script setup lang="ts">
import type { Candidate } from '@/api'
import { fmtTime } from '@/format'

const props = defineProps<{
  candidates: Candidate[]
  activeId: number | null
  maxClip: number
  videoDuration: number
  locked: boolean
}>()
const emit = defineEmits<{
  activate: [id: number]
  toggle: [id: number, selected: boolean]
  trim: [id: number, range: { start: number; end: number }, edge: 'start' | 'end']
}>()

const STEPS = [-5, -1, 1, 5]

function nextRange(c: Candidate, edge: 'start' | 'end', delta: number) {
  return edge === 'start' ? { start: c.start + delta, end: c.end } : { start: c.start, end: c.end + delta }
}

/** Validasi sama dengan backend: start ≥ 0, end ≤ durasi video, 1 ≤ durasi ≤ maxClip. */
function valid(r: { start: number; end: number }) {
  const dur = r.end - r.start
  const maxEnd = props.videoDuration > 0 ? props.videoDuration : Infinity
  return r.start >= 0 && r.end <= maxEnd && dur >= 1 && dur <= props.maxClip
}

function step(c: Candidate, edge: 'start' | 'end', delta: number) {
  const r = nextRange(c, edge, delta)
  if (valid(r)) emit('trim', c.id, r, edge)
}
</script>

<template>
  <ul class="flex flex-col gap-2">
    <li
      v-for="c in candidates"
      :key="c.id"
      class="rounded-xl border transition-colors"
      :class="c.id === activeId ? 'border-accent-500/70 bg-zinc-900' : 'border-zinc-800 bg-zinc-900/50 hover:border-zinc-700'"
    >
      <div class="flex cursor-pointer items-center gap-3 px-3 py-2.5" @click="emit('activate', c.id)">
        <input
          type="checkbox"
          class="h-4 w-4 accent-violet-500"
          :checked="c.selected"
          :disabled="locked"
          @click.stop
          @change="emit('toggle', c.id, ($event.target as HTMLInputElement).checked)"
        />
        <span class="w-8 text-sm font-semibold text-zinc-300">#{{ c.rank }}</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline gap-2 text-sm tabular-nums">
            <span class="text-zinc-100">{{ fmtTime(c.start) }} – {{ fmtTime(c.end) }}</span>
            <span class="text-xs text-zinc-500">{{ Math.round(c.duration) }} dtk · puncak {{ fmtTime(c.peak_time) }}</span>
          </div>
          <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-zinc-800">
            <div class="h-full rounded-full bg-accent-500" :style="{ width: `${c.score}%` }" />
          </div>
        </div>
        <span class="w-10 text-right text-sm font-semibold tabular-nums text-zinc-200">{{ c.score }}</span>
        <span v-if="c.clip_url" class="rounded bg-emerald-950 px-1.5 py-0.5 text-[10px] text-emerald-300">klip</span>
      </div>

      <div v-if="c.id === activeId" class="grid gap-3 border-t border-zinc-800 px-3 py-3 sm:grid-cols-2">
        <div v-for="edge in (['start', 'end'] as const)" :key="edge">
          <span class="label">{{ edge === 'start' ? 'Awal' : 'Akhir' }} · {{ fmtTime(c[edge]) }}</span>
          <div class="flex gap-1">
            <button
              v-for="d in STEPS"
              :key="d"
              class="btn btn-ghost flex-1 px-2 tabular-nums"
              :disabled="locked || !valid(nextRange(c, edge, d))"
              @click="step(c, edge, d)"
            >
              {{ d > 0 ? `+${d}` : d }}
            </button>
          </div>
        </div>
        <p class="text-xs text-zinc-500 sm:col-span-2">
          Maks {{ maxClip }} detik. Mengubah rentang menandai klip perlu dirender ulang.
        </p>
      </div>
    </li>
  </ul>
</template>
