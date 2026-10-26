<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api, errorMessage, type RenderOptions, type Template } from '@/api'
import Icon from '@/components/Icon.vue'
import { coverStyle, previewAreas, templateNameFor } from '@/layout'
import { useAppStore } from '@/stores/app'

/** Tab "Output": template layout + preview 9:16 dari video ini + opsi render (v-model:options). */
const props = defineProps<{
  templates: Template[]
  template: string
  locked: boolean
  options: RenderOptions
  jobId: string
  videoId: string
  channel: string
  previewTime: number | null
}>()
const emit = defineEmits<{
  'update:template': [name: string]
  'update:options': [opts: RenderOptions]
}>()

const app = useAppStore()

function set<K extends keyof RenderOptions>(key: K, value: RenderOptions[K]) {
  const next = { ...props.options, [key]: value }
  if (key === 'thumbnail' && !value) next.intro_frame = next.landscape = false
  emit('update:options', next)
}

function onTemplateChange(e: Event) {
  if (e.target instanceof HTMLSelectElement) emit('update:template', e.target.value)
}

function onToggleOption(key: 'subtitle' | 'thumbnail' | 'landscape' | 'intro_frame', e: Event) {
  if (e.target instanceof HTMLInputElement) set(key, e.target.checked)
}

// ---------- preview layout 9:16 dari frame video ini (salah posisi facecam terlihat sebelum render)
const PW = 162
const PH = 288
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

const toggles = [
  { key: 'subtitle', label: 'Subtitle', hint: 'Whisper, 2–4 kata per baris', icon: 'captions' },
  { key: 'thumbnail', label: 'Thumbnail 9:16', hint: 'Frame wajah terbaik + teks', icon: 'image' },
  { key: 'landscape', label: 'Thumbnail 16:9', hint: '1280×720 tambahan', icon: 'image', needs: 'thumbnail' },
  { key: 'intro_frame', label: 'Frame pembuka', hint: 'Thumbnail di 0,1 dtk pertama', icon: 'film', needs: 'thumbnail' },
] as const
</script>

<template>
  <div class="flex flex-col gap-5 p-3">
    <section class="flex flex-col gap-3">
      <div>
        <label class="label" for="tpl">Template layout</label>
        <select
          id="tpl"
          class="input"
          :value="template"
          :disabled="locked"
          @change="onTemplateChange"
        >
          <option v-for="t in templates" :key="t.name" :value="t.name">
            {{ t.name }} — {{ t.layout_type === 'split' ? 'facecam + gameplay' : 'center crop' }}
          </option>
        </select>
      </div>

      <div class="flex gap-3">
        <figure class="shrink-0">
          <div class="overflow-hidden rounded-md bg-black ring-1 ring-line-strong" :style="{ width: `${PW}px`, height: `${PH}px` }">
            <div v-for="a in areas" :key="a.key" class="bg-no-repeat" :style="coverStyle(frameUrl, natural, a.box, a.w, a.h)" />
          </div>
          <figcaption class="mt-1 text-center text-[10px] text-zinc-500">preview 9:16 · {{ Math.round(frameTime) }} dtk</figcaption>
        </figure>
        <div class="flex min-w-0 flex-col gap-2 text-xs text-zinc-400">
          <p>Preview memakai frame dari video ini.</p>
          <p v-if="current?.layout_type === 'split'">Bagian atas harus berisi <b class="text-zinc-200">wajah streamer</b>. Kalau bukan, deteksi facecam:</p>
          <button class="btn btn-ghost btn-sm justify-start" :disabled="locked || detecting" @click="detectFacecam">
            <Icon :name="detecting ? 'loader' : 'sparkles'" :size="14" />
            {{ detecting ? 'Mendeteksi…' : 'Deteksi facecam' }}
          </button>
          <RouterLink to="/templates" class="mt-auto flex items-center gap-1 text-zinc-500 hover:text-zinc-200">
            Atur manual di Template <Icon name="chevronRight" :size="12" />
          </RouterLink>
        </div>
      </div>
    </section>

    <section class="flex flex-col gap-1">
      <span class="label">Opsi render</span>
      <label
        v-for="t in toggles"
        :key="t.key"
        class="flex cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 hover:bg-panel-2"
        :class="{ 'pointer-events-none opacity-40': ('needs' in t && !options[t.needs]) || locked }"
      >
        <Icon :name="t.icon" class="text-zinc-500" />
        <span class="flex-1">
          <span class="block text-sm text-zinc-200">{{ t.label }}</span>
          <span class="block text-[11px] text-zinc-500">{{ t.hint }}</span>
        </span>
        <input type="checkbox" class="check" :checked="options[t.key]" @change="onToggleOption(t.key, $event)" />
      </label>
    </section>
  </div>
</template>
