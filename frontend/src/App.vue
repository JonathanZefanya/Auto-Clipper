<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { ACTIVE_STATUSES, api, type Job } from '@/api'
import Icon from '@/components/Icon.vue'
import { STATUS_LABEL } from '@/format'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const route = useRoute()

const nav = [
  { to: '/', label: 'Proses baru', icon: 'plus', match: (p: string) => p === '/' },
  { to: '/jobs', label: 'Riwayat', icon: 'history', match: (p: string) => p.startsWith('/jobs') },
  { to: '/templates', label: 'Template', icon: 'layout', match: (p: string) => p.startsWith('/templates') },
  { to: '/settings', label: 'Pengaturan', icon: 'settings', match: (p: string) => p.startsWith('/settings') },
] as const

// indikator job berjalan (polling ringan; detail real-time ada di halaman job via SSE)
const running = ref<Job[]>([])
let timer: ReturnType<typeof setInterval> | undefined
async function poll() {
  try {
    running.value = (await api.listJobs()).filter((j) => ACTIVE_STATUSES.includes(j.status))
  } catch {
    /* backend belum siap */
  }
}
onMounted(() => {
  void poll()
  timer = setInterval(poll, 4000)
})
onBeforeUnmount(() => clearInterval(timer))
const current = computed(() => running.value.find((j) => j.queue_position === 0) ?? running.value[0])

const toastStyle = {
  error: { cls: 'border-red-900/80 bg-red-950/90 text-red-200', icon: 'alert' },
  info: { cls: 'border-line-strong bg-panel-2/95 text-zinc-200', icon: 'info' },
  success: { cls: 'border-emerald-900/80 bg-emerald-950/90 text-emerald-200', icon: 'check' },
} as const
</script>

<template>
  <div class="flex min-h-screen">
    <!-- sidebar -->
    <aside class="sticky top-0 flex h-screen w-14 shrink-0 flex-col border-r border-line bg-panel lg:w-52">
      <RouterLink to="/" class="flex h-12 items-center gap-2.5 border-b border-line px-3.5">
        <span class="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-accent-600 text-white">
          <Icon name="scissors" :size="15" />
        </span>
        <span class="hidden text-sm font-semibold tracking-tight lg:block">Auto Clipper</span>
      </RouterLink>

      <nav class="flex flex-1 flex-col gap-0.5 p-2">
        <RouterLink
          v-for="n in nav"
          :key="n.to"
          :to="n.to"
          :title="n.label"
          class="flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors"
          :class="n.match(route.path) ? 'bg-panel-3 text-zinc-50' : 'text-zinc-400 hover:bg-panel-2 hover:text-zinc-100'"
        >
          <Icon :name="n.icon" />
          <span class="hidden lg:block">{{ n.label }}</span>
        </RouterLink>
      </nav>

      <RouterLink
        v-if="current"
        :to="{ name: 'job', params: { id: current.id } }"
        class="m-2 rounded-md border border-line bg-panel-2 p-2 text-xs hover:border-line-strong"
        :title="current.title"
      >
        <div class="flex items-center gap-1.5 text-accent-300">
          <Icon name="loader" :size="13" />
          <span class="hidden truncate lg:block">{{ STATUS_LABEL[current.status] }} · {{ current.progress.toFixed(0) }}%</span>
        </div>
        <div class="mt-1 hidden truncate text-zinc-400 lg:block">{{ current.title || current.id }}</div>
        <div class="mt-1.5 hidden h-1 overflow-hidden rounded bg-panel-3 lg:block">
          <div class="h-full bg-accent-500 transition-[width] duration-500" :style="{ width: `${current.progress}%` }" />
        </div>
        <div v-if="running.length > 1" class="mt-1 hidden text-zinc-500 lg:block">+{{ running.length - 1 }} di antrean</div>
      </RouterLink>
    </aside>

    <main class="min-w-0 flex-1">
      <RouterView />
    </main>

    <div class="fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2">
      <TransitionGroup name="toast">
        <div
          v-for="t in app.toasts"
          :key="t.id"
          class="flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm shadow-xl shadow-black/40 backdrop-blur"
          :class="toastStyle[t.kind].cls"
        >
          <Icon :name="toastStyle[t.kind].icon" class="mt-0.5" />
          <span class="min-w-0 break-words">{{ t.text }}</span>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<style>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
