<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { errorMessage } from '@/api'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const saving = ref(false)
const loaded = ref(false)

type Section = 'detect' | 'render' | 'subtitle' | 'thumbnail'
interface NumField { key: string; label: string; min: number; max: number; step: number; hint?: string }

const detectFields: NumField[] = [
  { key: 'min_peak_gap_s', label: 'Jarak minimal antar klip (detik)', min: 10, max: 600, step: 5 },
  { key: 'pad_before_s', label: 'Padding sebelum puncak (detik)', min: 0, max: 60, step: 1 },
  { key: 'pad_after_s', label: 'Padding sesudah puncak (detik)', min: 0, max: 60, step: 1 },
  { key: 'max_clip_s', label: 'Durasi klip maksimal (detik)', min: 5, max: 60, step: 1 },
  { key: 'w_audio', label: 'Bobot audio', min: 0, max: 1, step: 0.05 },
  { key: 'w_chat', label: 'Bobot chat', min: 0, max: 1, step: 0.05 },
  { key: 'w_reaction', label: 'Bobot tawa/teriak', min: 0, max: 1, step: 0.05, hint: 'Sinyal YAMNet (tawa, teriak, sorak).' },
  { key: 'chat_delay_s', label: 'Chat delay (detik)', min: 0, max: 30, step: 1, hint: 'Sinyal chat digeser mundur sebesar ini.' },
]

const form = reactive({
  detect: {} as Record<string, number | boolean>,
  render: {} as Record<string, string | number>,
  subtitle: {} as Record<string, string | number | boolean>,
  thumbnail: {} as Record<string, string | number | boolean>,
  data_dir: '',
})

function fill() {
  const s = app.settings
  if (!s) return
  for (const k of ['detect', 'render', 'subtitle', 'thumbnail'] as Section[]) form[k] = { ...s[k] } as never
  form.data_dir = s.data_dir_configured
}

onMounted(async () => {
  try {
    await Promise.all([app.loadSettings(), app.loadTemplates()])
    fill()
    loaded.value = true
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
})

function pick<T extends Record<string, unknown>>(obj: T, keys: string[]) {
  return Object.fromEntries(keys.map((k) => [k, obj[k]]))
}

async function save() {
  saving.value = true
  try {
    const body: Record<string, unknown> = {
      detect: pick(form.detect, [
        'sensitivity', 'download_max_height', 'reaction_enabled', ...detectFields.map((f) => f.key),
      ]),
      subtitle: pick(form.subtitle, ['enabled', 'model', 'device', 'language']),
      thumbnail: pick(form.thumbnail, ['enabled', 'landscape', 'intro_frame']),
      render: pick(form.render, ['video_encoder', 'default_template']),
    }
    if (form.data_dir.trim() !== app.settings?.data_dir_configured) body.data_dir = form.data_dir.trim()
    await app.saveSettings(body)
    fill()
    app.notify(
      app.settings?.restart_required ? 'Tersimpan. Restart backend agar folder data baru dipakai.' : 'Pengaturan tersimpan',
      'success',
    )
  } catch (e) {
    app.notify(errorMessage(e), 'error', 7000)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="!loaded" class="py-20 text-center text-zinc-500">Memuat…</div>
  <form v-else class="mx-auto flex max-w-3xl flex-col gap-5" @submit.prevent="save">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-semibold">Pengaturan</h1>
      <button class="btn btn-primary px-5" :disabled="saving">{{ saving ? 'Menyimpan…' : 'Simpan' }}</button>
    </div>

    <section class="card flex flex-col gap-4">
      <h2 class="font-semibold">Deteksi momen</h2>
      <div>
        <label class="label" for="sens">Sensitivitas · {{ Number(form.detect.sensitivity).toFixed(2) }}</label>
        <input id="sens" v-model.number="form.detect.sensitivity" type="range" min="0" max="1" step="0.05" class="w-full accent-violet-500" />
        <p class="text-xs text-zinc-500">Makin tinggi makin banyak kandidat (ambang z-score lebih rendah).</p>
      </div>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="form.detect.reaction_enabled" type="checkbox" class="accent-violet-500" />
        Deteksi tawa/teriak (YAMNet) sebagai sinyal tambahan
      </label>
      <div class="grid gap-4 sm:grid-cols-2">
        <div v-for="f in detectFields" :key="f.key">
          <label class="label" :for="f.key">{{ f.label }}</label>
          <input :id="f.key" v-model.number="form.detect[f.key]" class="input" type="number" :min="f.min" :max="f.max" :step="f.step" />
          <p v-if="f.hint" class="mt-1 text-xs text-zinc-500">{{ f.hint }}</p>
        </div>
        <div>
          <label class="label" for="res">Resolusi unduhan maksimal</label>
          <select id="res" v-model.number="form.detect.download_max_height" class="input">
            <option v-for="h in app.settings!.options.download_heights" :key="h" :value="h">{{ h }}p</option>
          </select>
        </div>
      </div>
    </section>

    <section class="card grid gap-4 sm:grid-cols-2">
      <h2 class="font-semibold sm:col-span-2">Subtitle (faster-whisper)</h2>
      <label class="flex items-center gap-2 text-sm sm:col-span-2">
        <input v-model="form.subtitle.enabled" type="checkbox" class="accent-violet-500" /> Subtitle aktif secara default
      </label>
      <div>
        <label class="label" for="wm">Model Whisper</label>
        <select id="wm" v-model="form.subtitle.model" class="input">
          <option v-for="m in app.settings!.options.whisper_models" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
      <div>
        <label class="label" for="dev">Perangkat</label>
        <select id="dev" v-model="form.subtitle.device" class="input">
          <option v-for="d in app.settings!.options.devices" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
      <div>
        <label class="label" for="lang">Bahasa</label>
        <input id="lang" v-model="form.subtitle.language" class="input" placeholder="id" />
      </div>
    </section>

    <section class="card grid gap-4 sm:grid-cols-2">
      <h2 class="font-semibold sm:col-span-2">Render & thumbnail</h2>
      <div>
        <label class="label" for="enc">Encoder video</label>
        <select id="enc" v-model="form.render.video_encoder" class="input">
          <option v-for="e in app.settings!.options.encoders" :key="e" :value="e">{{ e }}</option>
        </select>
      </div>
      <div>
        <label class="label" for="dt">Template default</label>
        <select id="dt" v-model="form.render.default_template" class="input">
          <option v-for="t in app.templates" :key="t.name" :value="t.name">{{ t.name }}</option>
        </select>
      </div>
      <div class="flex flex-col gap-2 text-sm sm:col-span-2">
        <label class="flex items-center gap-2"><input v-model="form.thumbnail.enabled" type="checkbox" class="accent-violet-500" /> Buat thumbnail</label>
        <label class="flex items-center gap-2"><input v-model="form.thumbnail.landscape" type="checkbox" class="accent-violet-500" /> Juga buat thumbnail 1280×720</label>
        <label class="flex items-center gap-2"><input v-model="form.thumbnail.intro_frame" type="checkbox" class="accent-violet-500" /> Sisipkan thumbnail sebagai frame pembuka klip</label>
      </div>
    </section>

    <section class="card flex flex-col gap-2">
      <h2 class="font-semibold">Penyimpanan</h2>
      <label class="label" for="dd">Folder data</label>
      <input id="dd" v-model="form.data_dir" class="input font-mono text-xs" />
      <p class="text-xs text-zinc-500">
        Sedang dipakai: <span class="font-mono">{{ app.settings!.data_dir }}</span>. Perubahan folder data berlaku setelah backend direstart.
        Pengaturan disimpan di <span class="font-mono">{{ app.settings!.config_file }}</span>.
      </p>
      <p v-if="app.settings!.restart_required" class="text-xs text-amber-400">Restart backend untuk memakai folder data baru.</p>
    </section>
  </form>
</template>
