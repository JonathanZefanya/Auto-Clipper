<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ACTIVE_STATUSES, api, errorMessage, type RenderOptions } from '@/api'
import CandidateList from '@/components/CandidateList.vue'
import Icon from '@/components/Icon.vue'
import PreviewPlayer from '@/components/PreviewPlayer.vue'
import ProgressCard from '@/components/ProgressCard.vue'
import RenderPanel from '@/components/RenderPanel.vue'
import ResultsGallery from '@/components/ResultsGallery.vue'
import ScoreChart from '@/components/ScoreChart.vue'
import ShortcutHelp from '@/components/ShortcutHelp.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import SubtitleEditor from '@/components/SubtitleEditor.vue'
import { fmtTime } from '@/format'
import { nextRange, rangeValid } from '@/trim'
import { useAppStore } from '@/stores/app'
import { useJobsStore } from '@/stores/jobs'

const props = defineProps<{ id: string }>()
const jobs = useJobsStore()
const app = useAppStore()
const router = useRouter()
const route = useRoute()

const loading = ref(true)
const notFound = ref(false)
const activeId = ref<number | null>(null)
const playhead = ref<number | null>(null)
const seekTo = ref<number | null>(null)
const view = ref<'review' | 'results'>('review')
const tab = ref<'clips' | 'subs' | 'output'>('clips')
const showHelp = ref(false)
const player = ref<InstanceType<typeof PreviewPlayer> | null>(null)

const job = computed(() => (jobs.current?.id === props.id ? jobs.current : null))
const locked = computed(() => !!job.value && ACTIVE_STATUSES.includes(job.value.status))
const active = computed(() => job.value?.candidates.find((c) => c.id === activeId.value) ?? null)
const maxClip = computed(() => Number(app.settings?.detect.max_clip_s ?? 60))
const hasCandidates = computed(() => !!job.value?.candidates.length)
/** Unduh/analisis berjalan, atau gagal sebelum ada kandidat → layar progres penuh. */
const analysisScreen = computed(() => {
  const j = job.value
  if (!j) return false
  if (j.status === 'failed') return !hasCandidates.value
  return ACTIVE_STATUSES.includes(j.status) && j.task === 'detect'
})
/** Transkripsi/render berjalan → strip progres di atas workspace. */
const taskBusy = computed(() => !!job.value && locked.value && job.value.task !== 'detect')

// ---------- opsi render (default dari render terakhir job atau pengaturan)
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
const renderOpts = ref<RenderOptions>({ ...renderDefaults.value })
watch(renderDefaults, (d) => (renderOpts.value = { ...d }))

// ---------- stepper
const steps = computed(() => {
  const j = job.value
  const clips = j?.clip_count ?? 0
  const rendering = !!j && locked.value && j.task === 'render'
  return [
    { key: 'analysis', label: 'Analisis', state: analysisScreen.value ? 'current' : hasCandidates.value ? 'done' : 'todo' },
    { key: 'review', label: 'Review', state: view.value === 'review' && !analysisScreen.value ? 'current' : hasCandidates.value ? 'done' : 'todo' },
    { key: 'render', label: 'Render', state: rendering ? 'current' : clips ? 'done' : 'todo' },
    { key: 'results', label: 'Hasil', state: view.value === 'results' ? 'current' : clips ? 'done' : 'todo' },
  ] as const
})
function goStep(key: string) {
  if (!hasCandidates.value) return
  if (key === 'review') view.value = 'review'
  if (key === 'results') view.value = 'results'
}

// ---------- muat data
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
    const q = route.query.view
    view.value = q === 'review' || q === 'results' ? q : detail.status === 'done' && detail.clip_count > 0 ? 'results' : 'review'
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
// kandidat muncul setelah analisis selesai (SSE 'end' → muat ulang)
watch(() => job.value?.candidates.length, (n) => {
  const first = job.value?.candidates[0]
  if (n && activeId.value == null && first) activeId.value = first.id
})
// render selesai → langsung tampilkan hasil
watch(() => job.value?.status, (now, before) => {
  if (before === 'rendering' && now === 'done') view.value = 'results'
})

// ---------- aksi
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
const onTranscribe = () => run(() => jobs.transcribe(), 'Transkripsi masuk antrean')

// reset dulu agar klik ke waktu yang sama tetap memicu seek
function seek(t: number) {
  seekTo.value = null
  void nextTick(() => (seekTo.value = t))
}

function onRender() {
  if (!job.value?.selected_count || locked.value) return
  void run(() => jobs.render({ ...renderOpts.value, only_thumbs: false, template: job.value?.template }), 'Render masuk antrean')
}

function regenerateThumbs() {
  void run(
    () => jobs.render({ ...renderOpts.value, thumbnail: true, intro_frame: false, only_thumbs: true }),
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

// ---------- shortcut keyboard
function moveActive(delta: number) {
  const list = job.value?.candidates ?? []
  if (!list.length) return
  const i = Math.max(0, list.findIndex((c) => c.id === activeId.value))
  activeId.value = list[Math.min(list.length - 1, Math.max(0, i + delta))].id
}

function trimActive(edge: 'start' | 'end', delta: number) {
  const c = active.value
  if (!c || locked.value) return
  const r = nextRange(c, edge, delta)
  if (rangeValid(r, { maxClip: maxClip.value, videoDuration: job.value?.duration ?? 0 })) void onTrim(c.id, r)
}

function onKey(e: KeyboardEvent) {
  const el = e.target instanceof HTMLElement ? e.target : null
  if (el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))) return
  if (!job.value || analysisScreen.value) return
  if (e.key === '?') return void (showHelp.value = !showHelp.value)
  if (e.key === 'Escape') return void (showHelp.value = false)
  if (e.ctrlKey && e.key === 'Enter') return void onRender()
  if (view.value !== 'review' || e.ctrlKey || e.metaKey || e.altKey) return
  const step = e.shiftKey ? 5 : 1
  const actions: Record<string, () => void> = {
    ArrowDown: () => moveActive(1),
    ArrowUp: () => moveActive(-1),
    ' ': () => player.value?.toggle(),
    x: () => active.value && !locked.value && void onToggle(active.value.id, !active.value.selected),
    q: () => trimActive('start', -step),
    w: () => trimActive('start', step),
    e: () => trimActive('end', -step),
    r: () => trimActive('end', step),
    '1': () => (tab.value = 'clips'),
    '2': () => (tab.value = 'subs'),
    '3': () => (tab.value = 'output'),
  }
  const fn = actions[e.key.length === 1 ? e.key.toLowerCase() : e.key]
  if (fn) {
    e.preventDefault()
    fn()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

const tabs = computed(() => [
  { key: 'clips', label: 'Klip', count: job.value?.candidates.length ?? 0 },
  { key: 'subs', label: 'Subtitle', count: null },
  { key: 'output', label: 'Output', count: null },
] as const)
</script>

<template>
  <div v-if="loading" class="grid h-screen place-items-center text-zinc-500"><Icon name="loader" :size="20" /></div>
  <div v-else-if="notFound || !job" class="grid h-screen place-items-center text-zinc-400">
    <div class="flex flex-col items-center gap-3">
      Job tidak ditemukan.
      <RouterLink to="/jobs" class="btn btn-ghost">Ke riwayat</RouterLink>
    </div>
  </div>

  <div v-else class="flex flex-col lg:h-screen">
    <!-- top bar -->
    <header class="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-panel px-3">
      <RouterLink to="/jobs" class="btn btn-quiet btn-sm btn-icon" title="Riwayat"><Icon name="chevronLeft" /></RouterLink>
      <img v-if="job.thumbnail" :src="job.thumbnail" class="hidden h-7 w-12 rounded object-cover sm:block" alt="" />
      <div class="min-w-0 flex-1 lg:max-w-md">
        <div class="truncate text-sm font-medium" :title="job.title">{{ job.title || job.url }}</div>
        <div class="truncate text-[11px] text-zinc-500">
          {{ job.channel || '—' }} · {{ fmtTime(job.duration) }} · template {{ job.template }}
        </div>
      </div>

      <nav class="mx-auto hidden items-center gap-1 md:flex">
        <template v-for="(s, i) in steps" :key="s.key">
          <Icon v-if="i" name="chevronRight" :size="14" class="text-zinc-700" />
          <button
            class="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors"
            :class="[
              s.state === 'current' ? 'bg-panel-3 text-zinc-50' : s.state === 'done' ? 'text-zinc-300 hover:bg-panel-2' : 'text-zinc-600',
              ['review', 'results'].includes(s.key) && hasCandidates ? 'cursor-pointer' : 'cursor-default',
            ]"
            @click="goStep(s.key)"
          >
            <span
              class="grid h-4 w-4 place-items-center rounded-full text-[10px]"
              :class="s.state === 'current' ? 'bg-accent-600 text-white' : s.state === 'done' ? 'bg-accent-600/25 text-accent-300' : 'bg-panel-3'"
            >
              <Icon v-if="s.state === 'done'" name="check" :size="10" />
              <template v-else>{{ i + 1 }}</template>
            </span>
            {{ s.label }}
          </button>
        </template>
      </nav>

      <div class="flex items-center gap-1">
        <StatusBadge :status="job.status" class="hidden sm:inline-flex" />
        <button class="btn btn-quiet btn-sm btn-icon" title="Shortcut keyboard (?)" @click="showHelp = true"><Icon name="keyboard" /></button>
        <a :href="job.url" target="_blank" rel="noopener" class="btn btn-quiet btn-sm btn-icon" title="Buka di YouTube"><Icon name="external" /></a>
        <button class="btn btn-quiet btn-sm btn-icon hover:text-red-300" :disabled="locked" title="Hapus job" @click="remove"><Icon name="trash" /></button>
      </div>
    </header>

    <!-- unduh / analisis / gagal -->
    <ProgressCard v-if="analysisScreen" :job="job" :cancelling="cancelling" @cancel="cancel" />

    <!-- hasil -->
    <div v-else-if="view === 'results'" class="min-h-0 flex-1 overflow-y-auto">
      <div v-if="taskBusy" class="p-4 pb-0"><ProgressCard :job="job" :cancelling="cancelling" compact @cancel="cancel" /></div>
      <ResultsGallery
        :job="job"
        :locked="locked"
        @save-text="onSaveText"
        @regenerate-thumbs="regenerateThumbs"
        @open-folder="openFolder"
        @review="view = 'review'"
      />
    </div>

    <!-- workspace review -->
    <div v-else-if="jobs.scores" class="flex min-h-0 flex-1 flex-col lg:flex-row">
      <section class="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
        <ProgressCard v-if="taskBusy" :job="job" :cancelling="cancelling" compact @cancel="cancel" />
        <PreviewPlayer
          ref="player"
          :src="api.sourceUrl(job.id)"
          :start="active?.start ?? null"
          :end="active?.end ?? null"
          :seek-to="seekTo"
          :label="active ? `Klip #${active.rank}` : undefined"
          @time="playhead = $event"
        />
        <ScoreChart :scores="jobs.scores" :active-id="activeId" :playhead="playhead" @select="activeId = $event" @seek="seek" />
      </section>

      <aside class="flex w-full shrink-0 flex-col border-t border-line bg-panel lg:w-[380px] lg:border-t-0 lg:border-l xl:w-[420px]">
        <div class="flex h-10 shrink-0 border-b border-line">
          <button
            v-for="(t, i) in tabs"
            :key="t.key"
            class="relative flex flex-1 items-center justify-center gap-1.5 text-xs font-medium transition-colors"
            :class="tab === t.key ? 'text-zinc-50' : 'text-zinc-500 hover:text-zinc-200'"
            :title="`${t.label} (${i + 1})`"
            @click="tab = t.key"
          >
            {{ t.label }}
            <span v-if="t.count != null" class="rounded bg-panel-3 px-1 text-[10px] text-zinc-400">{{ t.count }}</span>
            <span v-if="tab === t.key" class="absolute inset-x-3 bottom-0 h-0.5 rounded bg-accent-500" />
          </button>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto">
          <template v-if="tab === 'clips'">
            <div class="flex items-center gap-1 border-b border-line px-3 py-1.5 text-xs text-zinc-500">
              <span class="flex-1">Klik untuk preview · centang untuk dirender</span>
              <button class="btn btn-quiet btn-sm" :disabled="locked" @click="run(() => jobs.setSelection(true))">Pilih semua</button>
              <button class="btn btn-quiet btn-sm" :disabled="locked" @click="run(() => jobs.setSelection(false))">Kosongkan</button>
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
          </template>
          <template v-else-if="tab === 'subs'">
            <SubtitleEditor
              v-if="active"
              :candidate="active"
              :locked="locked"
              :selected-count="job.selected_count"
              @seek="seek"
              @transcribe="onTranscribe"
              @changed="(has) => active && (active.subs_path = has ? `subs/clip_${String(active.rank).padStart(2, '0')}.json` : null)"
            />
            <p v-else class="p-4 text-sm text-zinc-500">Pilih klip di tab Klip.</p>
          </template>
          <RenderPanel
            v-else
            v-model:options="renderOpts"
            :templates="app.templates"
            :template="job.template"
            :locked="locked"
            :job-id="job.id"
            :video-id="job.video_id"
            :channel="job.channel"
            :preview-time="active?.peak_time ?? null"
            @update:template="onTemplate"
          />
        </div>

        <footer class="flex shrink-0 items-center gap-3 border-t border-line p-3">
          <div class="min-w-0 flex-1 text-xs">
            <div class="text-zinc-200"><b>{{ job.selected_count }}</b> dari {{ job.candidates.length }} klip dipilih</div>
            <div class="truncate text-zinc-500">
              {{ [renderOpts.subtitle && 'subtitle', renderOpts.thumbnail && 'thumbnail', renderOpts.intro_frame && 'frame pembuka'].filter(Boolean).join(' · ') || 'tanpa subtitle & thumbnail' }}
            </div>
          </div>
          <button class="btn btn-primary btn-lg" :disabled="locked || !job.selected_count" title="Render (Ctrl+Enter)" @click="onRender">
            <Icon name="film" /> Render
          </button>
        </footer>
      </aside>
    </div>

    <ShortcutHelp v-if="showHelp" @close="showHelp = false" />
  </div>
</template>
