<script setup lang="ts">
import { computed } from 'vue'
import { ACTIVE_STATUSES, type Job } from '@/api'
import Icon from '@/components/Icon.vue'
import { STATUS_LABEL } from '@/format'

/** Progres job: `compact` = strip di atas workspace (transkripsi/render); default = layar analisis. */
const props = defineProps<{ job: Job; cancelling?: boolean; compact?: boolean }>()
const emit = defineEmits<{ cancel: [] }>()

const active = computed(() => ACTIVE_STATUSES.includes(props.job.status))
const isCancelling = computed(() => props.cancelling || props.job.message === 'membatalkan…')
const queued = computed(() => (props.job.queue_position ?? 0) > 0)

const steps = [
  { key: 'queued', label: 'Antre', icon: 'history' },
  { key: 'downloading', label: 'Unduh video', icon: 'download' },
  { key: 'analyzing', label: 'Analisis momen', icon: 'wave' },
  { key: 'ready_for_review', label: 'Siap direview', icon: 'check' },
] as const
const stepIndex = computed(() => steps.findIndex((s) => s.key === props.job.status))
</script>

<template>
  <!-- strip ringkas -->
  <div v-if="compact" class="panel flex items-center gap-3 px-3 py-2">
    <Icon name="loader" class="text-accent-400" />
    <div class="min-w-0 flex-1">
      <div class="flex items-center justify-between gap-2 text-sm">
        <span class="truncate">
          <b class="text-zinc-100">{{ STATUS_LABEL[job.status] }}</b>
          <span class="text-zinc-400"> · {{ queued ? `posisi antrean #${job.queue_position}` : job.message }}</span>
        </span>
        <span v-if="!queued" class="tabnum text-xs text-zinc-300">{{ job.progress.toFixed(0) }}%</span>
      </div>
      <div class="mt-1.5 h-1 overflow-hidden rounded-full bg-panel-3">
        <div class="h-full rounded-full bg-accent-500 transition-[width] duration-500" :style="{ width: `${Math.max(2, job.progress)}%` }" />
      </div>
    </div>
    <button v-if="active" class="btn btn-danger btn-sm" :disabled="isCancelling" @click="emit('cancel')">
      {{ isCancelling ? 'Membatalkan…' : 'Batalkan' }}
    </button>
  </div>

  <!-- layar analisis / gagal -->
  <div v-else class="mx-auto flex w-full max-w-lg flex-col gap-6 px-6 py-16">
    <template v-if="job.status === 'failed'">
      <div class="flex items-center gap-2 text-red-300"><Icon name="alert" :size="20" /><h2 class="text-lg font-semibold">Job gagal</h2></div>
      <p class="panel border-red-900/60 bg-red-950/30 p-3 text-sm whitespace-pre-wrap text-red-200">{{ job.error || 'Terjadi kesalahan.' }}</p>
      <p class="text-sm text-zinc-400">Buat job baru dengan link yang sama untuk mencoba lagi — video yang sudah terunduh dipakai ulang.</p>
    </template>
    <template v-else>
      <div>
        <h2 class="text-lg font-semibold">{{ queued ? 'Menunggu antrean' : 'Menyiapkan kandidat klip' }}</h2>
        <p class="mt-1 text-sm text-zinc-400">
          {{ queued ? `Posisi antrean #${job.queue_position}. Satu job diproses dalam satu waktu.` : 'Halaman ini akan berubah otomatis ke review saat selesai.' }}
        </p>
      </div>
      <ol class="flex flex-col gap-1">
        <li
          v-for="(s, i) in steps"
          :key="s.key"
          class="flex items-center gap-3 rounded-md px-3 py-2"
          :class="i === stepIndex ? 'bg-panel-2' : ''"
        >
          <span
            class="grid h-7 w-7 place-items-center rounded-full"
            :class="i < stepIndex ? 'bg-accent-600/25 text-accent-300' : i === stepIndex ? 'bg-accent-600 text-white' : 'bg-panel-3 text-zinc-600'"
          >
            <Icon :name="i < stepIndex ? 'check' : i === stepIndex ? 'loader' : s.icon" :size="14" />
          </span>
          <div class="min-w-0 flex-1">
            <div class="text-sm" :class="i <= stepIndex ? 'text-zinc-100' : 'text-zinc-500'">{{ s.label }}</div>
            <div v-if="i === stepIndex && !queued" class="truncate text-xs text-zinc-400">{{ job.message }}</div>
          </div>
          <span v-if="i === stepIndex && !queued" class="tabnum text-sm text-zinc-300">{{ job.progress.toFixed(0) }}%</span>
        </li>
      </ol>
      <div class="h-1.5 overflow-hidden rounded-full bg-panel-3">
        <div class="h-full rounded-full bg-accent-500 transition-[width] duration-500" :style="{ width: `${Math.max(2, job.progress)}%` }" />
      </div>
      <button class="btn btn-danger self-start" :disabled="isCancelling" @click="emit('cancel')">
        <Icon name="x" :size="14" /> {{ isCancelling ? 'Membatalkan…' : 'Batalkan' }}
      </button>
    </template>
  </div>
</template>
