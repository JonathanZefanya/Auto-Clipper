<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { useAppStore } from '@/stores/app'

const app = useAppStore()

const nav = [
  { to: '/', label: 'Proses baru' },
  { to: '/jobs', label: 'Riwayat' },
  { to: '/templates', label: 'Template' },
  { to: '/settings', label: 'Pengaturan' },
]

const toastClass = {
  error: 'border-red-800 bg-red-950/90 text-red-200',
  info: 'border-zinc-700 bg-zinc-900/95 text-zinc-200',
  success: 'border-emerald-800 bg-emerald-950/90 text-emerald-200',
}
</script>

<template>
  <div class="min-h-screen">
    <header class="sticky top-0 z-20 border-b border-zinc-800/80 bg-zinc-950/85 backdrop-blur">
      <div class="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
        <RouterLink to="/" class="flex items-center gap-2 font-semibold tracking-tight">
          <span class="grid h-7 w-7 place-items-center rounded-lg bg-accent-600 text-sm">✂</span>
          Auto Clipper
        </RouterLink>
        <nav class="flex gap-1 text-sm">
          <RouterLink
            v-for="n in nav"
            :key="n.to"
            :to="n.to"
            class="rounded-md px-3 py-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            :exact-active-class="'bg-zinc-800 text-zinc-100'"
          >
            {{ n.label }}
          </RouterLink>
        </nav>
      </div>
    </header>

    <main class="mx-auto max-w-7xl px-4 py-6">
      <RouterView />
    </main>

    <div class="fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2">
      <TransitionGroup name="toast">
        <div
          v-for="t in app.toasts"
          :key="t.id"
          class="rounded-lg border px-3 py-2 text-sm shadow-lg"
          :class="toastClass[t.kind]"
        >
          {{ t.text }}
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
