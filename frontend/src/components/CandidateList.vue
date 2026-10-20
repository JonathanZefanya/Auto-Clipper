<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { Candidate } from '@/api'
import Icon from '@/components/Icon.vue'
import { fmtTime } from '@/format'
import { nextRange, rangeValid } from '@/trim'

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
  trim: [id: number, range: { start: number; end: number }]
}>()

const STEPS = [-5, -1, 1, 5]
const limits = () => ({ maxClip: props.maxClip, videoDuration: props.videoDuration })

function step(c: Candidate, edge: 'start' | 'end', delta: number) {
  const r = nextRange(c, edge, delta)
  if (rangeValid(r, limits())) emit('trim', c.id, r)
}

// gulir ke klip aktif (mis. saat pindah dengan ↑/↓)
const rows = ref<Record<number, HTMLElement | null>>({})
watch(() => props.activeId, async (id) => {
  await nextTick()
  if (id != null) rows.value[id]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})
</script>

<template>
  <ul class="flex flex-col">
    <li
      v-for="c in candidates"
      :key="c.id"
      :ref="(el) => (rows[c.id] = el as HTMLElement | null)"
      class="border-b border-line transition-colors"
      :class="c.id === activeId ? 'bg-panel-2' : 'hover:bg-panel-2/50'"
    >
      <div class="flex cursor-pointer items-center gap-2.5 px-3 py-2" @click="emit('activate', c.id)">
        <input
          type="checkbox"
          class="check"
          :checked="c.selected"
          :disabled="locked"
          :title="c.selected ? 'Batal pilih (X)' : 'Pilih untuk dirender (X)'"
          @click.stop
          @change="emit('toggle', c.id, ($event.target as HTMLInputElement).checked)"
        />
        <span
          class="grid h-6 w-6 shrink-0 place-items-center rounded text-xs font-semibold"
          :class="c.id === activeId ? 'bg-accent-600 text-white' : 'bg-panel-3 text-zinc-300'"
        >{{ c.rank }}</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline gap-2 text-sm tabnum">
            <span class="text-zinc-100">{{ fmtTime(c.start) }}–{{ fmtTime(c.end) }}</span>
            <span class="text-xs text-zinc-500">{{ Math.round(c.duration) }}s</span>
          </div>
          <div class="mt-1 h-1 overflow-hidden rounded-full bg-panel-3">
            <div class="h-full rounded-full bg-accent-500/80" :style="{ width: `${c.score}%` }" />
          </div>
        </div>
        <span class="flex items-center gap-1 text-zinc-600">
          <Icon v-if="c.subs_path" name="captions" :size="14" class="text-sky-400" title="sudah ditranskripsi" />
          <Icon v-if="c.clip_url" name="film" :size="14" class="text-emerald-400" title="sudah dirender" />
        </span>
        <span class="w-8 text-right text-sm font-semibold tabnum text-zinc-200">{{ c.score }}</span>
      </div>

      <div v-if="c.id === activeId" class="flex flex-col gap-2.5 px-3 pb-3">
        <!-- bar rentang: posisi klip relatif terhadap jendela maks -->
        <div class="relative h-1.5 rounded-full bg-panel-3" :title="`${Math.round(c.duration)} dari maks ${maxClip} detik`">
          <div class="absolute inset-y-0 left-0 rounded-full bg-accent-500" :style="{ width: `${Math.min(100, (c.duration / maxClip) * 100)}%` }" />
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div v-for="edge in (['start', 'end'] as const)" :key="edge">
            <div class="mb-1 flex items-center justify-between text-[11px] text-zinc-500">
              <span>{{ edge === 'start' ? 'AWAL' : 'AKHIR' }}</span>
              <span class="tabnum text-zinc-300">{{ fmtTime(c[edge]) }}</span>
            </div>
            <div class="flex gap-0.5">
              <button
                v-for="d in STEPS"
                :key="d"
                class="btn btn-ghost btn-sm flex-1 px-0 tabnum"
                :disabled="locked || !rangeValid(nextRange(c, edge, d), limits())"
                @click="step(c, edge, d)"
              >
                {{ d > 0 ? `+${d}` : d }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </li>
  </ul>
</template>
