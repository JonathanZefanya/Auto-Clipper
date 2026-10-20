<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api, errorMessage, type Preview } from '@/api'
import Icon from '@/components/Icon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { fmtDate, fmtTime } from '@/format'
import { useAppStore } from '@/stores/app'
import { useJobsStore } from '@/stores/jobs'

const app = useAppStore()
const jobs = useJobsStore()
const router = useRouter()

const url = ref('')
const preview = ref<Preview | null>(null)
const template = ref('center')
const loading = ref(false)
const creating = ref(false)
const error = ref('')

const URL_RE = /^https?:\/\/((www|m|music)\.)?(youtube\.com\/(watch\?|live\/)|youtu\.be\/)/i

onMounted(async () => {
  try {
    const [, s] = await Promise.all([app.loadTemplates(), app.loadSettings(), jobs.fetchList()])
    template.value = String(s.render.default_template ?? 'center')
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
})

let lastChecked = ''
async function check() {
  const u = url.value.trim()
  if (!u || u === lastChecked) return
  error.value = ''
  preview.value = null
  if (!URL_RE.test(u)) {
    error.value = 'Link tidak valid. Gunakan youtube.com/watch?v=…, youtu.be/…, atau youtube.com/live/…'
    return
  }
  lastChecked = u
  loading.value = true
  try {
    preview.value = await api.preview(u)
  } catch (e) {
    error.value = errorMessage(e)
    lastChecked = ''
  } finally {
    loading.value = false
  }
}

// cek otomatis saat link valid ditempel/diketik
let debounce: ReturnType<typeof setTimeout> | undefined
watch(url, (u) => {
  clearTimeout(debounce)
  if (URL_RE.test(u.trim())) debounce = setTimeout(check, 400)
  else {
    preview.value = null
    lastChecked = ''
  }
})

async function pasteFromClipboard() {
  try {
    url.value = (await navigator.clipboard.readText()).trim()
  } catch {
    app.notify('Tidak bisa membaca clipboard — tempel manual dengan Ctrl+V', 'info')
  }
}

async function process() {
  if (!preview.value) return
  creating.value = true
  try {
    const p = preview.value
    const job = await api.createJob({
      url: p.url, template: template.value,
      title: p.title, channel: p.channel, duration: p.duration, thumbnail: p.thumbnail,
    })
    await router.push({ name: 'job', params: { id: job.id } })
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="mx-auto flex max-w-4xl flex-col gap-10 px-6 py-12">
    <section class="flex flex-col gap-5">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Buat klip dari VOD</h1>
        <p class="mt-1 text-sm text-zinc-400">
          Tempel link YouTube. Momen seru dicari dari lonjakan suara, tawa/teriak, ekspresi wajah, dan live chat.
        </p>
      </div>

      <form class="flex gap-2" @submit.prevent="check">
        <div class="relative flex-1">
          <Icon name="link" class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-zinc-500" />
          <input
            v-model="url"
            class="input h-12 pl-9 text-base"
            placeholder="https://www.youtube.com/watch?v=…"
            autofocus
            spellcheck="false"
          />
          <Icon v-if="loading" name="loader" class="absolute top-1/2 right-3 -translate-y-1/2 text-accent-400" />
        </div>
        <button type="button" class="btn btn-ghost h-12 px-4" title="Tempel dari clipboard" @click="pasteFromClipboard">
          <Icon name="clipboard" /> Tempel
        </button>
      </form>
      <p v-if="error" class="-mt-2 flex items-center gap-1.5 text-sm text-red-400"><Icon name="alert" /> {{ error }}</p>

      <Transition name="fade">
        <div v-if="preview" class="panel flex flex-col overflow-hidden sm:flex-row">
          <div class="relative sm:w-80">
            <img v-if="preview.thumbnail" :src="preview.thumbnail" class="aspect-video w-full object-cover" alt="" />
            <span class="absolute right-2 bottom-2 rounded bg-black/80 px-1.5 py-0.5 text-xs tabnum">
              {{ fmtTime(preview.duration) }}
            </span>
          </div>
          <div class="flex min-w-0 flex-1 flex-col gap-4 p-4">
            <div>
              <h2 class="line-clamp-2 font-semibold leading-snug">{{ preview.title }}</h2>
              <p class="mt-0.5 text-sm text-zinc-400">{{ preview.channel }}</p>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <span class="chip"><Icon name="wave" :size="12" /> audio</span>
                <span class="chip"><Icon name="mic" :size="12" /> tawa/teriak</span>
                <span class="chip"><Icon name="face" :size="12" /> ekspresi (jika ada facecam)</span>
                <span class="chip" :class="preview.chat_available ? 'border-emerald-900 text-emerald-300' : 'opacity-50'">
                  <Icon name="chat" :size="12" /> {{ preview.chat_available ? 'live chat' : 'tanpa live chat' }}
                </span>
              </div>
            </div>
            <div class="mt-auto flex flex-col gap-2 sm:flex-row sm:items-end">
              <div class="flex-1">
                <label class="label" for="tpl">Template layout</label>
                <select id="tpl" v-model="template" class="input">
                  <option v-for="t in app.templates" :key="t.name" :value="t.name">
                    {{ t.name }} — {{ t.layout_type === 'split' ? 'facecam + gameplay' : 'center crop' }}
                  </option>
                </select>
              </div>
              <button class="btn btn-primary btn-lg" :disabled="creating" @click="process">
                <Icon :name="creating ? 'loader' : 'sparkles'" /> {{ creating ? 'Membuat job…' : 'Proses video' }}
              </button>
            </div>
            <p class="-mt-2 text-xs text-zinc-500">Template bisa diganti & facecam dideteksi otomatis di halaman review.</p>
          </div>
        </div>
      </Transition>
    </section>

    <section v-if="jobs.list.length" class="flex flex-col gap-3">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-zinc-300">Terbaru</h2>
        <RouterLink to="/jobs" class="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-100">
          Semua riwayat <Icon name="chevronRight" :size="14" />
        </RouterLink>
      </div>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <RouterLink
          v-for="j in jobs.list.slice(0, 6)"
          :key="j.id"
          :to="{ name: 'job', params: { id: j.id } }"
          class="panel group overflow-hidden transition-colors hover:border-line-strong"
        >
          <div class="relative aspect-video bg-panel-2">
            <img v-if="j.thumbnail" :src="j.thumbnail" class="h-full w-full object-cover opacity-80 transition-opacity group-hover:opacity-100" alt="" />
            <span class="absolute top-2 left-2"><StatusBadge :status="j.status" /></span>
          </div>
          <div class="p-3">
            <div class="truncate text-sm font-medium">{{ j.title || j.url }}</div>
            <div class="mt-0.5 flex justify-between text-xs text-zinc-500">
              <span>{{ j.channel || '—' }}</span>
              <span>{{ fmtDate(j.created_at) }}</span>
            </div>
          </div>
        </RouterLink>
      </div>
    </section>
  </div>
</template>
