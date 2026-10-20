<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api, errorMessage, type RenderOptions, type Template } from '@/api'
import { coverStyle, previewAreas, templateNameFor } from '@/layout'
import { useAppStore } from '@/stores/app'

const props = defineProps<{
  templates: Template[]
  template: string
  selectedCount: number
  locked: boolean
  defaults: RenderOptions
  jobId: string
  videoId: string
  channel: string
  previewTime: number | null
}>()
const emit = defineEmits<{
  'update:template': [name: string]
  render: [opts: RenderOptions]
  selectAll: []
  clearAll: []
}>()

const app = useAppStore()
const opts = reactive<RenderOptions>({ ...props.defaults })
watch(() => props.defaults, (d) => Object.assign(opts, d))
watch(() => opts.thumbnail, (on) => {
  if (!on) opts.intro_frame = opts.landscape = false
})

// ---------- preview layout 9:16 dari frame video ini (agar salah posisi facecam terlihat sebelum render)
const PW = 144
const PH = 256
const current = computed(() => props.templates.find((t) => t.name === props.template) ?? null)
const frameTime = ref(0)
watch(() => props.previewTime, (t) => (frameTime.value = Math.max(0, Math.round(t ?? 0))), { immediate: true })
const frameUrl = computed(() => api.frameUrl(props.jobId, frameTime.value, 640))
const natural = reactive({ w: 16, h: 9 })
watch(frameUrl, (url) => {
  const img = new Image()
  img.onload = () => Object.assign(natural, { w: img.naturalWidth, h: img.naturalHeight })
  img.src = url
}, { immediate: true })
const areas = computed(() => (current.value ? previewAreas(current.value, PW, PH) : []))

// ---------- F-17: deteksi facecam di video ini → template per channel
const detecting = ref(false)
async function detectFacecam() {
  detecting.value = true
  try {
    const top = current.value?.layout_type === 'split' ? current.value.top_ratio : 0.4
    const r = await api.detectFacecam(props.jobId, top)
    const name = templateNameFor(props.channel, `facecam-${props.videoId}`)
    await app.saveTemplate({ name, layout_type: 'split', facecam_box: r.facecam_box, gameplay_box: null, top_ratio: top })
    frameTime.value = Math.round(r.time)
    emit('update:template', name)
    app.notify(`Facecam terdeteksi (${r.hits}/${r.frames} frame) → template "${name}" dipakai. Cek preview.`, 'success', 7000)
  } catch (e) {
    app.notify(errorMessage(e), 'error', 8000)
  } finally {
    detecting.value = false
  }
}
</script>

<template>
  <div class="card flex flex-col gap-4">
    <div class="flex gap-2">
      <button class="btn btn-ghost flex-1" :disabled="locked" @click="emit('selectAll')">Pilih semua</button>
      <button class="btn btn-ghost flex-1" :disabled="locked" @click="emit('clearAll')">Hapus pilihan</button>
    </div>

    <div class="flex gap-3">
      <div class="min-w-0 flex-1 flex flex-col gap-2">
        <div>
          <label class="label" for="tpl">Template layout</label>
          <select
            id="tpl"
            class="input"
            :value="template"
            :disabled="locked"
            @change="emit('update:template', ($event.target as HTMLSelectElement).value)"
          >
            <option v-for="t in templates" :key="t.name" :value="t.name">
              {{ t.name }} ({{ t.layout_type === 'split' ? 'facecam + gameplay' : 'center crop' }})
            </option>
          </select>
        </div>
        <button class="btn btn-ghost text-xs" :disabled="locked || detecting" @click="detectFacecam">
          {{ detecting ? 'Mendeteksi facecam…' : '✨ Deteksi facecam di video ini' }}
        </button>
        <p class="text-[11px] leading-snug text-zinc-500">
          Preview memakai frame video ini. Jika bagian atas bukan wajah streamer, deteksi facecam atau atur di
          halaman Template.
        </p>
      </div>

      <figure class="shrink-0">
        <div class="overflow-hidden rounded-lg bg-black ring-1 ring-zinc-700" :style="{ width: `${PW}px`, height: `${PH}px` }">
          <div
            v-for="a in areas"
            :key="a.key"
            class="bg-no-repeat"
            :style="coverStyle(frameUrl, natural, a.box, a.w, a.h)"
          />
        </div>
        <figcaption class="mt-1 text-center text-[10px] text-zinc-500">preview 9:16</figcaption>
      </figure>
    </div>

    <div class="grid grid-cols-2 gap-2 text-sm">
      <label class="flex items-center gap-2"><input v-model="opts.subtitle" type="checkbox" class="accent-violet-500" /> Subtitle</label>
      <label class="flex items-center gap-2"><input v-model="opts.thumbnail" type="checkbox" class="accent-violet-500" /> Thumbnail</label>
      <label class="flex items-center gap-2" :class="{ 'opacity-40': !opts.thumbnail }">
        <input v-model="opts.landscape" type="checkbox" class="accent-violet-500" :disabled="!opts.thumbnail" /> Thumbnail 16:9
      </label>
      <label class="flex items-center gap-2" :class="{ 'opacity-40': !opts.thumbnail }">
        <input v-model="opts.intro_frame" type="checkbox" class="accent-violet-500" :disabled="!opts.thumbnail" /> Frame pembuka
      </label>
    </div>

    <button
      class="btn btn-primary py-2.5 text-base"
      :disabled="locked || selectedCount === 0"
      @click="emit('render', { ...opts, only_thumbs: false })"
    >
      Render {{ selectedCount }} klip
    </button>
    <p v-if="selectedCount === 0" class="-mt-2 text-center text-xs text-zinc-500">Centang minimal 1 kandidat.</p>
  </div>
</template>
