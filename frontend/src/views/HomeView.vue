<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api, errorMessage, type Preview } from '@/api'
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

async function check() {
  error.value = ''
  preview.value = null
  if (!URL_RE.test(url.value.trim())) {
    error.value = 'Link tidak valid. Gunakan youtube.com/watch?v=…, youtu.be/…, atau youtube.com/live/…'
    return
  }
  loading.value = true
  try {
    preview.value = await api.preview(url.value.trim())
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
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
  <div class="mx-auto flex max-w-3xl flex-col gap-6">
    <section class="card p-6">
      <h1 class="text-xl font-semibold">Proses video baru</h1>
      <p class="mt-1 text-sm text-zinc-400">Tempel link VOD / bekas live YouTube. Momen seru dideteksi dari lonjakan audio dan live chat.</p>

      <form class="mt-5 flex gap-2" @submit.prevent="check">
        <input v-model="url" class="input text-base" placeholder="https://www.youtube.com/watch?v=…" autofocus />
        <button class="btn btn-ghost shrink-0 px-4" :disabled="loading || !url.trim()">
          {{ loading ? 'Memeriksa…' : 'Cek link' }}
        </button>
      </form>
      <p v-if="error" class="mt-3 text-sm text-red-400">{{ error }}</p>

      <div v-if="preview" class="mt-5 flex flex-col gap-4 rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 sm:flex-row">
        <img v-if="preview.thumbnail" :src="preview.thumbnail" class="aspect-video w-full rounded-lg object-cover sm:w-56" alt="" />
        <div class="flex min-w-0 flex-1 flex-col gap-3">
          <div>
            <h2 class="font-semibold leading-snug">{{ preview.title }}</h2>
            <p class="text-sm text-zinc-400">{{ preview.channel }} · {{ fmtTime(preview.duration) }}</p>
            <p class="mt-1 text-xs" :class="preview.chat_available ? 'text-emerald-400' : 'text-zinc-500'">
              {{ preview.chat_available ? 'Live chat replay tersedia' : 'Tanpa live chat — deteksi pakai audio saja' }}
            </p>
          </div>
          <div class="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div class="flex-1">
              <label class="label" for="tpl">Template layout</label>
              <select id="tpl" v-model="template" class="input">
                <option v-for="t in app.templates" :key="t.name" :value="t.name">
                  {{ t.name }} ({{ t.layout_type === 'split' ? 'facecam + gameplay' : 'center crop' }})
                </option>
              </select>
            </div>
            <button class="btn btn-primary px-6 py-2" :disabled="creating" @click="process">
              {{ creating ? 'Membuat job…' : 'Proses' }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <section v-if="jobs.list.length" class="flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-medium text-zinc-400">Job terbaru</h2>
        <RouterLink to="/jobs" class="text-xs text-accent-400 hover:underline">Lihat semua</RouterLink>
      </div>
      <RouterLink
        v-for="j in jobs.list.slice(0, 5)"
        :key="j.id"
        :to="{ name: 'job', params: { id: j.id } }"
        class="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2 hover:border-zinc-700"
      >
        <span class="min-w-0 flex-1 truncate text-sm">{{ j.title || j.url }}</span>
        <span class="hidden text-xs text-zinc-500 sm:inline">{{ fmtDate(j.created_at) }}</span>
        <StatusBadge :status="j.status" />
      </RouterLink>
    </section>
  </div>
</template>
