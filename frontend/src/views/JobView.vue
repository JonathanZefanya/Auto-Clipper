<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ACTIVE_STATUSES, api, errorMessage, type RenderOptions } from '@/api'
import CandidateList from '@/components/CandidateList.vue'
import PreviewPlayer from '@/components/PreviewPlayer.vue'
import ProgressCard from '@/components/ProgressCard.vue'
import RenderPanel from '@/components/RenderPanel.vue'
import ResultsGallery from '@/components/ResultsGallery.vue'
import ScoreChart from '@/components/ScoreChart.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import SubtitleEditor from '@/components/SubtitleEditor.vue'
import { fmtDate, fmtTime } from '@/format'
import { useAppStore } from '@/stores/app'
import { useJobsStore } from '@/stores/jobs'

const props = defineProps<{ id: string }>()
const jobs = useJobsStore()
const app = useAppStore()
const router = useRouter()

const loading = ref(true)
const notFound = ref(false)
const activeId = ref<number | null>(null)
const playhead = ref<number | null>(null)
const seekTo = ref<number | null>(null)

const job = computed(() => (jobs.current?.id === props.id ? jobs.current : null))
const locked = computed(() => !!job.value && ACTIVE_STATUSES.includes(job.value.status))
const showProgress = computed(() => !!job.value && (locked.value || job.value.status === 'failed'))
const active = computed(() => job.value?.candidates.find((c) => c.id === activeId.value) ?? null)
const maxClip = computed(() => Number(app.settings?.detect.max_clip_s ?? 60))

const renderDefaults = computed<RenderOptions>(() => {
  const saved = job.value?.render_options
  const s = app.settings
  return {
    subtitle: saved?.subtitle ?? Boolean(s?.subtitle.enabled ?? true),
    thumbnail: saved?.thumbnail ?? Boolean(s?.thumbnail.enabled ?? true),
    landscape: saved?.landscape ?? Boolean(s?.thumbnail.landscape ?? false),
    intro_frame: saved?.intro_frame ?? Boolean(s?.thumbnail.intro_frame ?? false),
    only_thumbs: false,
  }
})

async function init() {
  loading.value = true
  notFound.value = false
  activeId.value = null
  try {
    await Promise.all([
      app.templates.length ? Promise.resolve() : app.loadTemplates(),
      app.settings ? Promise.resolve() : app.loadSettings(),
    ])
    const detail = await jobs.load(props.id)
    activeId.value = detail.candidates[0]?.id ?? null
  } catch (e) {
    notFound.value = true
    app.notify(errorMessage(e), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(init)
watch(() => props.id, init)
onBeforeUnmount(() => jobs.unsubscribe())
// kandidat baru muncul setelah analisis selesai (via SSE 'end')
watch(() => job.value?.candidates.length, (n) => {
  if (n && activeId.value == null) activeId.value = job.value!.candidates[0].id
})

async function run<T>(fn: () => Promise<T>, ok?: string) {
  try {
    const r = await fn()
    if (ok) app.notify(ok, 'success')
    return r
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}

const onToggle = (id: number, selected: boolean) => run(() => jobs.patchCandidate(id, { selected }))
const onTrim = (id: number, r: { start: number; end: number }) => run(() => jobs.patchCandidate(id, r))
const onTemplate = (name: string) => run(() => jobs.setTemplate(name))
const onSaveText = (id: number, text: string) => run(() => jobs.patchCandidate(id, { thumb_text: text }), 'Teks thumbnail disimpan')

// reset dulu agar klik ke waktu yang sama tetap memicu seek
function seek(t: number) {
  seekTo.value = null
  void nextTick(() => (seekTo.value = t))
}

const onTranscribe = () => run(() => jobs.transcribe(), 'Transkripsi masuk antrean')

function onRender(opts: RenderOptions) {
  void run(() => jobs.render({ ...opts, template: job.value?.template }), 'Render masuk antrean')
}

function regenerateThumbs() {
  void run(
    () => jobs.render({ ...renderDefaults.value, thumbnail: true, intro_frame: false, only_thumbs: true }),
    'Membuat ulang thumbnail',
  )
}

async function openFolder() {
  const r = await run(() => api.openFolder(props.id))
  if (r) app.notify(r.opened ? `Folder dibuka: ${r.path}` : `Folder output: ${r.path}`, 'info', 8000)
}

const cancelling = ref(false)
async function cancel() {
  if (!job.value) return
  const what = { render: 'render', transcribe: 'transkripsi', detect: 'unduh & analisis' }[job.value.task]
  if (!confirm(`Batalkan ${what} job ini?`)) return
  cancelling.value = true
  try {
    await jobs.cancel(props.id)
    app.notify('Job dibatalkan', 'info')
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  } finally {
    cancelling.value = false
  }
}

async function remove() {
  if (!job.value || !confirm(`Hapus job "${job.value.title || job.value.id}" beserta semua filenya?`)) return
  try {
    await jobs.remove(props.id)
    app.notify('Job dihapus', 'success')
    await router.push({ name: 'history' })
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}
</script>

<template>
  <div v-if="loading" class="py-20 text-center text-zinc-500">Memuat…</div>
  <div v-else-if="notFound || !job" class="py-20 text-center text-zinc-400">Job tidak ditemukan.</div>

  <div v-else class="flex flex-col gap-5">
    <section class="card flex flex-col gap-4 sm:flex-row sm:items-center">
      <img v-if="job.thumbnail" :src="job.thumbnail" class="aspect-video w-full rounded-lg object-cover sm:w-40" alt="" />
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <StatusBadge :status="job.status" />
          <span class="text-xs text-zinc-500">{{ fmtDate(job.created_at) }}</span>
        </div>
        <h1 class="mt-1 truncate text-lg font-semibold">
          <a :href="job.url" target="_blank" rel="noopener" class="hover:underline">{{ job.title || job.url }}</a>
        </h1>
        <p class="text-sm text-zinc-400">
          {{ job.channel || '—' }} · {{ fmtTime(job.duration) }} ·
          {{ job.has_chat ? 'dengan live chat' : 'audio saja' }} · template <b class="text-zinc-300">{{ job.template }}</b>
        </p>
      </div>
      <button class="btn btn-danger self-start" :disabled="locked" @click="remove">Hapus job</button>
    </section>

    <ProgressCard v-if="showProgress" :job="job" :cancelling="cancelling" @cancel="cancel" />

    <template v-if="job.candidates.length && jobs.scores">
      <ScoreChart
        :scores="jobs.scores"
        :active-id="activeId"
        :playhead="playhead"
        @select="activeId = $event"
        @seek="seek"
      />

      <div class="grid gap-5 lg:grid-cols-5">
        <section class="lg:col-span-3">
          <div class="mb-2 flex items-baseline justify-between">
            <h2 class="text-lg font-semibold">Kandidat ({{ job.candidates.length }})</h2>
            <span class="text-sm text-zinc-400">{{ job.selected_count }} dipilih</span>
          </div>
          <CandidateList
            :candidates="job.candidates"
            :active-id="activeId"
            :max-clip="maxClip"
            :video-duration="job.duration"
            :locked="locked"
            @activate="activeId = $event"
            @toggle="onToggle"
            @trim="onTrim"
          />
        </section>

        <aside class="flex flex-col gap-4 lg:sticky lg:top-20 lg:col-span-2 lg:self-start">
          <PreviewPlayer
            :src="api.sourceUrl(job.id)"
            :start="active?.start ?? null"
            :end="active?.end ?? null"
            :seek-to="seekTo"
            @time="playhead = $event"
          />
          <SubtitleEditor
            v-if="active"
            :candidate="active"
            :locked="locked"
            :selected-count="job.selected_count"
            @seek="seek"
            @transcribe="onTranscribe"
            @changed="(has) => active && (active.subs_path = has ? `subs/clip_${String(active.rank).padStart(2, '0')}.json` : null)"
          />
          <RenderPanel
            :templates="app.templates"
            :template="job.template"
            :selected-count="job.selected_count"
            :locked="locked"
            :defaults="renderDefaults"
            :job-id="job.id"
            :video-id="job.video_id"
            :channel="job.channel"
            :preview-time="active?.peak_time ?? null"
            @update:template="onTemplate"
            @render="onRender"
            @select-all="run(() => jobs.setSelection(true))"
            @clear-all="run(() => jobs.setSelection(false))"
          />
        </aside>
      </div>
    </template>

    <ResultsGallery
      :job="job"
      :locked="locked"
      @save-text="onSaveText"
      @regenerate-thumbs="regenerateThumbs"
      @open-folder="openFolder"
    />
  </div>
</template>
