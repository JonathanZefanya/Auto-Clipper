<script setup lang="ts">
import { computed } from 'vue'
import { ACTIVE_STATUSES, type Job } from '@/api'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ job: Job; cancelling?: boolean }>()
const emit = defineEmits<{ cancel: [] }>()

const active = computed(() => ACTIVE_STATUSES.includes(props.job.status))

const steps = [
  { key: 'queued', label: 'Antre' },
  { key: 'downloading', label: 'Unduh' },
  { key: 'analyzing', label: 'Analisis' },
  { key: 'ready_for_review', label: 'Review' },
  { key: 'transcribing', label: 'Transkripsi' },
  { key: 'rendering', label: 'Render' },
  { key: 'done', label: 'Selesai' },
] as const

const activeIndex = computed(() => steps.findIndex((s) => s.key === props.job.status))
</script>

<template>
  <div class="card">
    <div class="mb-3 flex items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <StatusBadge :status="job.status" />
        <span class="text-sm text-zinc-300">{{ job.message || '' }}</span>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="job.queue_position && job.queue_position > 0" class="text-xs text-zinc-400">
          posisi antrean #{{ job.queue_position }}
        </span>
        <span v-else-if="job.status !== 'failed'" class="text-sm font-medium tabular-nums text-zinc-200">
          {{ job.progress.toFixed(0) }}%
        </span>
        <button
          v-if="active"
          class="btn btn-danger px-2.5 py-1 text-xs"
          :disabled="cancelling || job.message === 'membatalkan…'"
          @click="emit('cancel')"
        >
          {{ cancelling || job.message === 'membatalkan…' ? 'Membatalkan…' : 'Batalkan' }}
        </button>
      </div>
    </div>

    <div v-if="job.status !== 'failed'" class="h-2 overflow-hidden rounded-full bg-zinc-800">
      <div
        class="h-full rounded-full bg-gradient-to-r from-accent-600 to-fuchsia-500 transition-[width] duration-500"
        :style="{ width: `${Math.max(2, job.progress)}%` }"
      />
    </div>
    <p v-else class="rounded-lg border border-red-900 bg-red-950/50 p-3 text-sm whitespace-pre-wrap text-red-300">
      {{ job.error || 'Job gagal.' }}
    </p>

    <ol class="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs">
      <li
        v-for="(s, i) in steps"
        :key="s.key"
        class="flex items-center gap-1.5"
        :class="i < activeIndex ? 'text-zinc-400' : i === activeIndex ? 'font-semibold text-accent-400' : 'text-zinc-600'"
      >
        <span class="h-1.5 w-1.5 rounded-full" :class="i <= activeIndex ? 'bg-accent-500' : 'bg-zinc-700'" />
        {{ s.label }}
      </li>
    </ol>
  </div>
</template>
