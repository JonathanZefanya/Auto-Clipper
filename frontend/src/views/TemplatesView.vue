<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, errorMessage, type Box, type Template } from '@/api'
import { fmtTime } from '@/format'
import { useAppStore } from '@/stores/app'
import { useJobsStore } from '@/stores/jobs'

const app = useAppStore()
const jobs = useJobsStore()

const NAME_RE = /^[A-Za-z0-9_-]{1,64}$/
const FULL: Box = { x: 0, y: 0, w: 1, h: 1 }

const edit = reactive<Template>({ name: '', layout_type: 'split', facecam_box: null, gameplay_box: null, top_ratio: 0.4 })
const mode = ref<'facecam' | 'gameplay'>('facecam')
const jobId = ref('')
const t = ref(60)
const natural = reactive({ w: 1920, h: 1080 })
const frameEl = ref<HTMLElement | null>(null)
const drag = ref<{ x0: number; y0: number } | null>(null)
const saving = ref(false)

const sourceJobs = computed(() => jobs.list.filter((j) => j.candidate_count > 0 || j.status === 'done'))
const currentJob = computed(() => sourceJobs.value.find((j) => j.id === jobId.value))
const frameUrl = computed(() => (jobId.value ? api.frameUrl(jobId.value, t.value) : ''))
const nameValid = computed(() => NAME_RE.test(edit.name))
const canSave = computed(
  () => nameValid.value && (edit.layout_type === 'center_crop' || !!edit.facecam_box),
)

onMounted(async () => {
  try {
    await Promise.all([app.loadTemplates(), jobs.fetchList()])
    jobId.value = sourceJobs.value[0]?.id ?? ''
    const first = app.templates.find((x) => x.layout_type === 'split') ?? app.templates[0]
    if (first) load(first)
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
})
watch(jobId, () => {
  const d = currentJob.value?.duration ?? 0
  if (d && t.value > d) t.value = Math.floor(d / 2)
})

function load(tpl: Template) {
  Object.assign(edit, structuredClone({ ...tpl }))
  delete (edit as Partial<Template>).builtin
  mode.value = edit.layout_type === 'split' ? 'facecam' : 'gameplay'
}

function newTemplate() {
  load({ name: 'template-baru', layout_type: 'split', facecam_box: null, gameplay_box: null, top_ratio: 0.4 })
}

// ---------- menggambar kotak di atas frame
function rel(e: PointerEvent) {
  const r = frameEl.value!.getBoundingClientRect()
  return {
    x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
    y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
  }
}
function setBox(b: Box) {
  const box = {
    x: +b.x.toFixed(4), y: +b.y.toFixed(4),
    w: +Math.min(b.w, 1 - b.x).toFixed(4), h: +Math.min(b.h, 1 - b.y).toFixed(4),
  }
  if (mode.value === 'facecam') edit.facecam_box = box
  else edit.gameplay_box = box
}
function onDown(e: PointerEvent) {
  const p = rel(e)
  drag.value = { x0: p.x, y0: p.y }
  ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
}
function onMove(e: PointerEvent) {
  if (!drag.value) return
  const p = rel(e)
  const { x0, y0 } = drag.value
  const w = Math.abs(p.x - x0)
  const h = Math.abs(p.y - y0)
  if (w > 0.01 && h > 0.01) setBox({ x: Math.min(x0, p.x), y: Math.min(y0, p.y), w, h })
}
function onUp() {
  drag.value = null
}

function boxStyle(b: Box | null) {
  if (!b) return { display: 'none' }
  return { left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }
}

// ---------- preview 9:16 (meniru scale "cover" + crop tengah di FFmpeg)
const PW = 180
const PH = 320
function coverStyle(b: Box | null, tw: number, th: number) {
  const box = b ?? FULL
  const bw = box.w * natural.w
  const bh = box.h * natural.h
  const s = Math.max(tw / bw, th / bh)
  return {
    width: `${tw}px`,
    height: `${th}px`,
    backgroundImage: frameUrl.value ? `url(${frameUrl.value})` : undefined,
    backgroundSize: `${natural.w * s}px ${natural.h * s}px`,
    backgroundPosition: `${-box.x * natural.w * s - (bw * s - tw) / 2}px ${-box.y * natural.h * s - (bh * s - th) / 2}px`,
  }
}
const topH = computed(() => Math.round(PH * edit.top_ratio))

async function save() {
  saving.value = true
  try {
    await app.saveTemplate({
      name: edit.name, layout_type: edit.layout_type, top_ratio: edit.top_ratio,
      facecam_box: edit.layout_type === 'split' ? edit.facecam_box : null,
      gameplay_box: edit.gameplay_box,
    })
    app.notify(`Template "${edit.name}" tersimpan`, 'success')
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  } finally {
    saving.value = false
  }
}

async function remove(name: string) {
  if (!confirm(`Hapus template "${name}"?`)) return
  try {
    await app.deleteTemplate(name)
    app.notify('Template dihapus', 'success')
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-[220px_1fr_auto]">
    <aside class="flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <h1 class="text-xl font-semibold">Template</h1>
        <button class="btn btn-ghost px-2 text-xs" @click="newTemplate">+ Baru</button>
      </div>
      <button
        v-for="tpl in app.templates"
        :key="tpl.name"
        class="flex items-center justify-between rounded-lg border px-3 py-2 text-left text-sm"
        :class="tpl.name === edit.name ? 'border-accent-500 bg-zinc-900' : 'border-zinc-800 bg-zinc-900/50 hover:border-zinc-700'"
        @click="load(tpl)"
      >
        <span>
          {{ tpl.name }}
          <span class="block text-xs text-zinc-500">{{ tpl.layout_type === 'split' ? 'facecam + gameplay' : 'center crop' }}</span>
        </span>
        <span v-if="!tpl.builtin" class="text-xs text-zinc-500 hover:text-red-400" @click.stop="remove(tpl.name)">hapus</span>
      </button>
    </aside>

    <section class="flex min-w-0 flex-col gap-4">
      <div class="card grid gap-3 sm:grid-cols-3">
        <div>
          <label class="label" for="tn">Nama</label>
          <input id="tn" v-model="edit.name" class="input" :class="{ 'border-red-700': !nameValid }" />
        </div>
        <div>
          <label class="label" for="tl">Layout</label>
          <select id="tl" v-model="edit.layout_type" class="input">
            <option value="split">Split (facecam atas, gameplay bawah)</option>
            <option value="center_crop">Center crop</option>
          </select>
        </div>
        <div v-if="edit.layout_type === 'split'">
          <label class="label" for="tr">Tinggi facecam · {{ Math.round(edit.top_ratio * 100) }}%</label>
          <input id="tr" v-model.number="edit.top_ratio" type="range" min="0.2" max="0.6" step="0.01" class="w-full accent-violet-500" />
        </div>
      </div>

      <div class="card flex flex-col gap-3">
        <div class="flex flex-wrap items-end gap-3">
          <div class="min-w-48 flex-1">
            <label class="label" for="src">Frame dari job</label>
            <select id="src" v-model="jobId" class="input">
              <option v-if="!sourceJobs.length" value="">(belum ada job dengan video)</option>
              <option v-for="j in sourceJobs" :key="j.id" :value="j.id">{{ j.title || j.id }}</option>
            </select>
          </div>
          <div class="min-w-48 flex-1">
            <label class="label" for="ts">Waktu · {{ fmtTime(t) }}</label>
            <input id="ts" v-model.number="t" type="range" min="0" :max="Math.max(1, (currentJob?.duration ?? 600) - 1)" step="1" class="w-full accent-violet-500" />
          </div>
          <div class="flex gap-1">
            <button
              v-if="edit.layout_type === 'split'"
              type="button"
              class="btn"
              :class="mode === 'facecam' ? 'btn-primary' : 'btn-ghost'"
              @click="mode = 'facecam'"
            >Kotak facecam</button>
            <button type="button" class="btn" :class="mode === 'gameplay' ? 'btn-primary' : 'btn-ghost'" @click="mode = 'gameplay'">
              Kotak gameplay
            </button>
          </div>
        </div>

        <div
          v-if="frameUrl"
          ref="frameEl"
          class="relative cursor-crosshair touch-none overflow-hidden rounded-lg bg-black select-none"
          @pointerdown="onDown"
          @pointermove="onMove"
          @pointerup="onUp"
        >
          <img
            :src="frameUrl"
            class="pointer-events-none block w-full"
            alt="frame sumber"
            draggable="false"
            @load="(e) => { natural.w = (e.target as HTMLImageElement).naturalWidth; natural.h = (e.target as HTMLImageElement).naturalHeight }"
          />
          <div v-if="edit.layout_type === 'split'" class="pointer-events-none absolute border-2 border-pink-400 bg-pink-400/15" :style="boxStyle(edit.facecam_box)">
            <span class="absolute -top-0.5 left-0 bg-pink-500 px-1 text-[10px] text-white">facecam</span>
          </div>
          <div class="pointer-events-none absolute border-2 border-cyan-400 bg-cyan-400/10" :style="boxStyle(edit.gameplay_box)">
            <span class="absolute -top-0.5 left-0 bg-cyan-500 px-1 text-[10px] text-white">gameplay</span>
          </div>
        </div>
        <p v-else class="py-10 text-center text-sm text-zinc-500">Proses minimal satu video untuk mengambil frame.</p>

        <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
          <span>Seret di atas frame untuk menggambar kotak <b>{{ mode }}</b>. Kotak gameplay kosong = seluruh frame.</span>
          <button type="button" class="btn btn-ghost px-2 py-1 text-xs" @click="mode === 'facecam' ? (edit.facecam_box = null) : (edit.gameplay_box = null)">
            Reset kotak {{ mode }}
          </button>
        </div>
      </div>
    </section>

    <aside class="flex flex-col items-center gap-3">
      <span class="label">Preview 9:16</span>
      <div class="overflow-hidden rounded-xl ring-1 ring-zinc-700" :style="{ width: `${PW}px`, height: `${PH}px` }">
        <template v-if="edit.layout_type === 'split'">
          <div class="bg-zinc-900 bg-no-repeat" :style="coverStyle(edit.facecam_box, PW, topH)" />
          <div class="bg-zinc-900 bg-no-repeat" :style="coverStyle(edit.gameplay_box, PW, PH - topH)" />
        </template>
        <div v-else class="bg-zinc-900 bg-no-repeat" :style="coverStyle(edit.gameplay_box, PW, PH)" />
      </div>
      <button class="btn btn-primary w-full" :disabled="!canSave || saving" @click="save">
        {{ saving ? 'Menyimpan…' : 'Simpan template' }}
      </button>
      <p v-if="edit.layout_type === 'split' && !edit.facecam_box" class="w-44 text-center text-xs text-amber-400">
        Gambar kotak facecam dulu.
      </p>
    </aside>
  </div>
</template>
