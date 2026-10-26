<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ACTIVE_STATUSES, errorMessage, type Job } from '@/api'
import Icon from '@/components/Icon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { fmtDate, fmtTime } from '@/format'
import { useAppStore } from '@/stores/app'
import { useJobsStore } from '@/stores/jobs'

const jobs = useJobsStore()
const app = useAppStore()
let timer: ReturnType<typeof setInterval> | undefined

const query = ref('')
const filter = ref<'all' | 'active' | 'review' | 'done' | 'failed'>('all')
const FILTERS = [
  { key: 'all', label: 'Semua', match: () => true },
  { key: 'active', label: 'Berjalan', match: (j: Job) => ACTIVE_STATUSES.includes(j.status) },
  { key: 'review', label: 'Siap review', match: (j: Job) => j.status === 'ready_for_review' },
  { key: 'done', label: 'Selesai', match: (j: Job) => j.status === 'done' },
  { key: 'failed', label: 'Gagal', match: (j: Job) => j.status === 'failed' },
] as const

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  const f = FILTERS.find((x) => x.key === filter.value) ?? FILTERS[0]
  return jobs.list.filter((j) => f.match(j) && (!q || `${j.title} ${j.channel} ${j.url}`.toLowerCase().includes(q)))
})
const count = (key: (typeof FILTERS)[number]['key']) => {
  const f = FILTERS.find((x) => x.key === key) ?? FILTERS[0]
  return jobs.list.filter(f.match).length
}
const anyActive = computed(() => jobs.list.some((j) => ACTIVE_STATUSES.includes(j.status)))

async function refresh() {
  try {
    await jobs.fetchList()
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}

onMounted(async () => {
  await refresh()
  timer = setInterval(() => anyActive.value && refresh(), 2000)
})
onBeforeUnmount(() => clearInterval(timer))

async function cancel(j: Job) {
  if (!confirm(`Batalkan job "${j.title || j.id}"?`)) return
  try {
    await jobs.cancel(j.id)
    app.notify('Job dibatalkan', 'info')
    await refresh()
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}

async function remove(j: Job) {
  if (!confirm(`Hapus job "${j.title || j.id}" beserta semua filenya?`)) return
  try {
    await jobs.remove(j.id)
    app.notify('Job dihapus', 'success')
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}
</script>

<template>
  <div class="mx-auto flex max-w-5xl flex-col gap-4 px-6 py-8">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-xl font-semibold tracking-tight">Riwayat</h1>
      <span class="flex-1" />
      <div class="relative w-64">
        <Icon name="search" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-zinc-500" :size="14" />
        <input v-model="query" class="input pl-8" placeholder="Cari judul / channel…" />
      </div>
      <button class="btn btn-ghost btn-icon" title="Muat ulang" @click="refresh"><Icon name="refresh" :size="14" /></button>
    </div>

    <div class="flex flex-wrap gap-1">
      <button
        v-for="f in FILTERS"
        :key="f.key"
        class="btn btn-sm"
        :class="filter === f.key ? 'bg-panel-3 text-zinc-50' : 'btn-quiet'"
        @click="filter = f.key"
      >
        {{ f.label }} <span class="text-zinc-500">{{ count(f.key) }}</span>
      </button>
    </div>

    <div v-if="!jobs.list.length" class="panel flex flex-col items-center gap-3 py-16 text-center">
      <Icon name="film" :size="28" class="text-zinc-600" />
      <p class="text-sm text-zinc-400">Belum ada job.</p>
      <RouterLink to="/" class="btn btn-primary"><Icon name="plus" :size="14" /> Proses video</RouterLink>
    </div>
    <p v-else-if="!visible.length" class="py-10 text-center text-sm text-zinc-500">Tidak ada job yang cocok.</p>

    <ul v-else class="panel divide-y divide-line overflow-hidden">
      <li v-for="j in visible" :key="j.id" class="group flex items-center gap-4 px-3 py-2.5 hover:bg-panel-2">
        <RouterLink :to="{ name: 'job', params: { id: j.id } }" class="relative hidden shrink-0 sm:block">
          <img v-if="j.thumbnail" :src="j.thumbnail" class="aspect-video w-28 rounded object-cover" alt="" />
          <div v-else class="aspect-video w-28 rounded bg-panel-3" />
          <span class="absolute right-1 bottom-1 rounded bg-black/80 px-1 text-[10px] tabnum">{{ fmtTime(j.duration) }}</span>
        </RouterLink>
        <div class="min-w-0 flex-1">
          <RouterLink :to="{ name: 'job', params: { id: j.id } }" class="block truncate text-sm font-medium hover:underline">
            {{ j.title || j.url }}
          </RouterLink>
          <div class="mt-0.5 truncate text-xs text-zinc-500">{{ j.channel || '—' }} · {{ fmtDate(j.created_at) }}</div>
          <div class="mt-1.5 flex items-center gap-2 text-xs text-zinc-400">
            <StatusBadge :status="j.status" />
            <template v-if="ACTIVE_STATUSES.includes(j.status)">
              <div class="h-1 w-24 overflow-hidden rounded bg-panel-3">
                <div class="h-full bg-accent-500 transition-[width]" :style="{ width: `${j.progress}%` }" />
              </div>
              <span class="truncate">{{ j.message }}</span>
            </template>
            <span v-else-if="j.status === 'failed'" class="truncate text-red-400">{{ j.error }}</span>
            <span v-else>{{ j.candidate_count }} kandidat · {{ j.clip_count }} klip</span>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <RouterLink :to="{ name: 'job', params: { id: j.id } }" class="btn btn-ghost btn-sm">Buka</RouterLink>
          <button
            v-if="ACTIVE_STATUSES.includes(j.status)"
            class="btn btn-danger btn-sm"
            :disabled="j.message === 'membatalkan…'"
            @click="cancel(j)"
          >
            {{ j.message === 'membatalkan…' ? 'Membatalkan…' : 'Batalkan' }}
          </button>
          <button v-else class="btn btn-quiet btn-sm btn-icon opacity-0 group-hover:opacity-100 hover:text-red-300" title="Hapus" @click="remove(j)">
            <Icon name="trash" :size="14" />
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>
