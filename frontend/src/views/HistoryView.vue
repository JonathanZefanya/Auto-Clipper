<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { ACTIVE_STATUSES, errorMessage } from '@/api'
import StatusBadge from '@/components/StatusBadge.vue'
import { fmtDate, fmtTime } from '@/format'
import { useAppStore } from '@/stores/app'
import { useJobsStore } from '@/stores/jobs'

const jobs = useJobsStore()
const app = useAppStore()
let timer: ReturnType<typeof setInterval> | undefined

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
  // progres tiap job aktif diperbarui berkala; detail real-time via SSE di halaman job
  timer = setInterval(() => anyActive.value && refresh(), 2000)
})
onBeforeUnmount(() => clearInterval(timer))

async function cancel(id: string, title: string) {
  if (!confirm(`Batalkan job "${title || id}"?`)) return
  try {
    await jobs.cancel(id)
    app.notify('Job dibatalkan', 'info')
    await refresh()
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}

async function remove(id: string, title: string) {
  if (!confirm(`Hapus job "${title || id}" beserta semua filenya?`)) return
  try {
    await jobs.remove(id)
    app.notify('Job dihapus', 'success')
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-semibold">Riwayat job</h1>
      <button class="btn btn-ghost" @click="refresh">Muat ulang</button>
    </div>

    <p v-if="!jobs.list.length" class="card py-10 text-center text-zinc-400">
      Belum ada job. <RouterLink to="/" class="text-accent-400 hover:underline">Proses video baru</RouterLink>
    </p>

    <ul v-else class="flex flex-col gap-2">
      <li v-for="j in jobs.list" :key="j.id" class="card flex items-center gap-4 p-3">
        <img v-if="j.thumbnail" :src="j.thumbnail" class="hidden aspect-video w-32 rounded object-cover sm:block" alt="" />
        <div v-else class="hidden aspect-video w-32 rounded bg-zinc-800 sm:block" />
        <div class="min-w-0 flex-1">
          <RouterLink :to="{ name: 'job', params: { id: j.id } }" class="block truncate font-medium hover:underline">
            {{ j.title || j.url }}
          </RouterLink>
          <p class="truncate text-xs text-zinc-400">
            {{ j.channel || '—' }} · {{ fmtTime(j.duration) }} · {{ fmtDate(j.created_at) }}
          </p>
          <div class="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
            <StatusBadge :status="j.status" />
            <template v-if="ACTIVE_STATUSES.includes(j.status)">
              <span class="tabular-nums">{{ j.progress.toFixed(0) }}%</span>
              <span class="truncate">{{ j.message }}</span>
            </template>
            <span v-else-if="j.status === 'failed'" class="truncate text-red-400">{{ j.error }}</span>
            <span v-else>{{ j.candidate_count }} kandidat · {{ j.clip_count }} klip</span>
          </div>
        </div>
        <div class="flex shrink-0 gap-2">
          <RouterLink :to="{ name: 'job', params: { id: j.id } }" class="btn btn-ghost">Buka</RouterLink>
          <button
            v-if="ACTIVE_STATUSES.includes(j.status)"
            class="btn btn-danger"
            :disabled="j.message === 'membatalkan…'"
            @click="cancel(j.id, j.title)"
          >
            {{ j.message === 'membatalkan…' ? 'Membatalkan…' : 'Batalkan' }}
          </button>
          <button v-else class="btn btn-danger" @click="remove(j.id, j.title)">Hapus</button>
        </div>
      </li>
    </ul>
  </div>
</template>
