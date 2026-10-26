<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, errorMessage, type Box, type Template } from '@/api'
import Icon from '@/components/Icon.vue'
import { fmtTime } from '@/format'
import { coverStyle as coverStyleOf } from '@/layout'
import { useAppStore } from '@/stores/app'
import { useJobsStore } from '@/stores/jobs'

const app = useAppStore()
const jobs = useJobsStore()

const NAME_RE = /^[A-Za-z0-9_-]{1,64}$/

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
  edit.name = tpl.name
  edit.layout_type = tpl.layout_type
  edit.facecam_box = tpl.facecam_box ? { ...tpl.facecam_box } : null
  edit.gameplay_box = tpl.gameplay_box ? { ...tpl.gameplay_box } : null
  edit.top_ratio = tpl.top_ratio
  mode.value = edit.layout_type === 'split' ? 'facecam' : 'gameplay'
}

function newTemplate() {
  load({ name: 'template-baru', layout_type: 'split', facecam_box: null, gameplay_box: null, top_ratio: 0.4 })
}

// ---------- menggambar kotak di atas frame
function rel(e: PointerEvent) {
  const el = frameEl.value
  if (!el) return { x: 0, y: 0 }
  const r = el.getBoundingClientRect()
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
  if (e.target instanceof HTMLElement) e.target.setPointerCapture(e.pointerId)
}
function onFrameLoad(e: Event) {
  if (e.target instanceof HTMLImageElement) {
    natural.w = e.target.naturalWidth
    natural.h = e.target.naturalHeight
  }
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
  return coverStyleOf(frameUrl.value, natural, b, tw, th)
}
const topH = computed(() => Math.round(PH * edit.top_ratio))

// ---------- F-17: auto-deteksi facecam
const detecting = ref(false)
async function autoDetect() {
  if (!jobId.value) return
  detecting.value = true
  try {
    const r = await api.detectFacecam(jobId.value, edit.top_ratio)
    edit.layout_type = 'split'
    edit.facecam_box = r.facecam_box
    mode.value = 'facecam'
    t.value = Math.round(r.time)
    app.notify(`Facecam terdeteksi di ${r.hits}/${r.frames} frame — periksa & sesuaikan bila perlu`, 'success', 6000)
  } catch (e) {
    app.notify(errorMessage(e), 'error', 8000)
  } finally {
    detecting.value = false
  }
}

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
  <div class="flex flex-col lg:h-screen lg:flex-row">
    <!-- daftar template -->
    <aside class="flex shrink-0 flex-col border-b border-line bg-panel lg:w-56 lg:border-r lg:border-b-0">
      <div class="flex h-12 items-center justify-between border-b border-line px-3">
        <h1 class="text-sm font-semibold">Template</h1>
        <button class="btn btn-ghost btn-sm" @click="newTemplate"><Icon name="plus" :size="12" /> Baru</button>
      </div>
      <div class="flex flex-col gap-0.5 overflow-y-auto p-2">
        <button
          v-for="tpl in app.templates"
          :key="tpl.name"
          class="group flex items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm"
          :class="tpl.name === edit.name ? 'bg-panel-3 text-zinc-50' : 'text-zinc-300 hover:bg-panel-2'"
          @click="load(tpl)"
        >
          <Icon name="layout" :size="14" class="text-zinc-500" />
          <span class="min-w-0 flex-1">
            <span class="block truncate">{{ tpl.name }}</span>
            <span class="block text-[11px] text-zinc-500">{{ tpl.layout_type === 'split' ? 'facecam + gameplay' : 'center crop' }}</span>
          </span>
          <span
            v-if="!tpl.builtin"
            class="text-zinc-600 opacity-0 group-hover:opacity-100 hover:text-red-400"
            title="Hapus template"
            @click.stop="remove(tpl.name)"
          ><Icon name="trash" :size="13" /></span>
        </button>
      </div>
    </aside>

    <!-- kanvas -->
    <section class="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
      <div class="panel flex flex-wrap items-end gap-3 p-3">
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
        <button
          type="button"
          class="btn btn-ghost"
          :disabled="!jobId || detecting"
          title="Cari facecam dari beberapa frame video (MediaPipe)"
          @click="autoDetect"
        >
          <Icon :name="detecting ? 'loader' : 'sparkles'" :size="14" /> {{ detecting ? 'Mendeteksi…' : 'Deteksi facecam' }}
        </button>
      </div>

      <div class="panel flex flex-col overflow-hidden">
        <div class="flex items-center gap-1 border-b border-line px-2 py-1.5">
          <span class="px-1 text-[11px] text-zinc-500 uppercase">Gambar kotak:</span>
          <button
            v-if="edit.layout_type === 'split'"
            type="button"
            class="btn btn-sm"
            :class="mode === 'facecam' ? 'bg-pink-500/20 text-pink-200 ring-1 ring-pink-500/50' : 'btn-quiet'"
            @click="mode = 'facecam'"
          >facecam</button>
          <button
            type="button"
            class="btn btn-sm"
            :class="mode === 'gameplay' ? 'bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-500/50' : 'btn-quiet'"
            @click="mode = 'gameplay'"
          >gameplay</button>
          <span class="flex-1" />
          <button type="button" class="btn btn-quiet btn-sm" @click="mode === 'facecam' ? (edit.facecam_box = null) : (edit.gameplay_box = null)">
            <Icon name="refresh" :size="12" /> Reset {{ mode }}
          </button>
        </div>
        <div
          v-if="frameUrl"
          ref="frameEl"
          class="relative cursor-crosshair touch-none overflow-hidden bg-black select-none"
          @pointerdown="onDown"
          @pointermove="onMove"
          @pointerup="onUp"
        >
          <img
            :src="frameUrl"
            class="pointer-events-none block w-full"
            alt="frame sumber"
            draggable="false"
            @load="onFrameLoad"
          />
          <div v-if="edit.layout_type === 'split'" class="pointer-events-none absolute border-2 border-pink-400 bg-pink-400/15" :style="boxStyle(edit.facecam_box)">
            <span class="absolute -top-0.5 left-0 bg-pink-500 px-1 text-[10px] text-white">facecam</span>
          </div>
          <div class="pointer-events-none absolute border-2 border-cyan-400 bg-cyan-400/10" :style="boxStyle(edit.gameplay_box)">
            <span class="absolute -top-0.5 left-0 bg-cyan-500 px-1 text-[10px] text-white">gameplay</span>
          </div>
        </div>
        <p v-else class="py-16 text-center text-sm text-zinc-500">Proses minimal satu video untuk mengambil frame.</p>
        <p class="border-t border-line px-3 py-2 text-xs text-zinc-500">
          Seret di atas frame untuk menggambar kotak <b class="text-zinc-300">{{ mode }}</b>. Kotak gameplay kosong = seluruh frame.
        </p>
      </div>
    </section>

    <!-- inspector -->
    <aside class="flex shrink-0 flex-col border-t border-line bg-panel lg:w-72 lg:border-t-0 lg:border-l">
      <div class="panel-header">Properti</div>
      <div class="flex flex-col gap-3 p-3">
        <div>
          <label class="label" for="tn">Nama</label>
          <input id="tn" v-model="edit.name" class="input" :class="{ 'border-red-700': !nameValid }" />
          <p v-if="!nameValid" class="mt-1 text-[11px] text-red-400">Huruf, angka, - atau _ saja.</p>
        </div>
        <div>
          <label class="label" for="tl">Layout</label>
          <select id="tl" v-model="edit.layout_type" class="input">
            <option value="split">Split (facecam atas, gameplay bawah)</option>
            <option value="center_crop">Center crop</option>
          </select>
        </div>
        <div v-if="edit.layout_type === 'split'">
          <div class="flex justify-between"><label class="label" for="tr">Tinggi facecam</label><span class="tabnum text-xs">{{ Math.round(edit.top_ratio * 100) }}%</span></div>
          <input id="tr" v-model.number="edit.top_ratio" type="range" min="0.2" max="0.6" step="0.01" class="w-full accent-violet-500" />
        </div>
      </div>
      <div class="panel-header border-t">Preview 9:16</div>
      <div class="flex flex-col items-center gap-3 p-3">
        <div class="overflow-hidden rounded-md bg-black ring-1 ring-line-strong" :style="{ width: `${PW}px`, height: `${PH}px` }">
          <template v-if="edit.layout_type === 'split'">
            <div class="bg-panel-2 bg-no-repeat" :style="coverStyle(edit.facecam_box, PW, topH)" />
            <div class="bg-panel-2 bg-no-repeat" :style="coverStyle(edit.gameplay_box, PW, PH - topH)" />
          </template>
          <div v-else class="bg-panel-2 bg-no-repeat" :style="coverStyle(edit.gameplay_box, PW, PH)" />
        </div>
        <p v-if="edit.layout_type === 'split' && !edit.facecam_box" class="flex items-center gap-1.5 text-xs text-amber-400">
          <Icon name="alert" :size="12" /> Gambar kotak facecam dulu.
        </p>
        <button class="btn btn-primary w-full" :disabled="!canSave || saving" @click="save">
          <Icon :name="saving ? 'loader' : 'check'" :size="14" /> {{ saving ? 'Menyimpan…' : 'Simpan template' }}
        </button>
      </div>
    </aside>
  </div>
</template>
