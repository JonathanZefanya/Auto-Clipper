<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { errorMessage } from '@/api'
import Icon from '@/components/Icon.vue'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const saving = ref(false)
const loaded = ref(false)

type Section = 'detect' | 'render' | 'subtitle' | 'thumbnail'
interface NumField { key: string; label: string; min: number; max: number; step: number; unit?: string; hint?: string }

/** Sinyal deteksi: satu baris per sinyal (toggle opsional + bobot). */
const signals = [
  { icon: 'wave', label: 'Lonjakan suara', hint: 'Volume relatif terhadap 60 detik sekitarnya', weight: 'w_audio' },
  { icon: 'chat', label: 'Live chat', hint: 'Hanya untuk bekas live dengan chat replay', weight: 'w_chat' },
  { icon: 'mic', label: 'Tawa / teriak', hint: 'YAMNet: tawa, teriak, sorak', weight: 'w_reaction', toggle: 'reaction_enabled' },
  { icon: 'face', label: 'Ekspresi wajah', hint: 'Kaget/tertawa di facecam · +±5% durasi analisis', weight: 'w_face', toggle: 'face_enabled' },
] as const

const clipFields: NumField[] = [
  { key: 'min_peak_gap_s', label: 'Jarak minimal antar klip', min: 10, max: 600, step: 5, unit: 'dtk' },
  { key: 'max_clip_s', label: 'Durasi klip maksimal', min: 5, max: 60, step: 1, unit: 'dtk' },
  { key: 'pad_before_s', label: 'Mulai sebelum puncak', min: 0, max: 60, step: 1, unit: 'dtk' },
  { key: 'pad_after_s', label: 'Selesai sesudah puncak', min: 0, max: 60, step: 1, unit: 'dtk' },
  { key: 'exclude_start_s', label: 'Lewati awal video', min: 0, max: 600, step: 5, unit: 'dtk', hint: 'Intro/sapaan' },
  { key: 'exclude_end_s', label: 'Lewati akhir video', min: 0, max: 600, step: 5, unit: 'dtk', hint: 'Outro "sampai jumpa"' },
  { key: 'chat_delay_s', label: 'Chat delay', min: 0, max: 30, step: 1, unit: 'dtk', hint: 'Sinyal chat digeser mundur' },
]

const SECTIONS = [
  { id: 'deteksi', label: 'Deteksi momen' },
  { id: 'klip', label: 'Klip' },
  { id: 'subtitle', label: 'Subtitle' },
  { id: 'output', label: 'Render & thumbnail' },
  { id: 'penyimpanan', label: 'Penyimpanan' },
]

const form = reactive({
  detect: {} as Record<string, number | boolean>,
  render: {} as Record<string, string | number>,
  subtitle: {} as Record<string, string | number | boolean>,
  thumbnail: {} as Record<string, string | number | boolean>,
  data_dir: '',
})
const snapshot = ref('')
const dirty = computed(() => loaded.value && JSON.stringify(form) !== snapshot.value)

function fill() {
  const s = app.settings
  if (!s) return
  for (const k of ['detect', 'render', 'subtitle', 'thumbnail'] as Section[]) form[k] = { ...s[k] } as never
  form.data_dir = s.data_dir_configured
  snapshot.value = JSON.stringify(form)
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

function pick<T extends Record<string, unknown>>(obj: T, keys: readonly string[]) {
  return Object.fromEntries(keys.map((k) => [k, obj[k]]))
}

async function save() {
  saving.value = true
  try {
    const body: Record<string, unknown> = {
      detect: pick(form.detect, [
        'sensitivity', 'download_max_height', 'reaction_enabled', 'face_enabled',
        ...signals.map((s) => s.weight), ...clipFields.map((f) => f.key),
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
  <div v-if="!loaded" class="grid h-screen place-items-center text-zinc-500"><Icon name="loader" :size="20" /></div>
  <form v-else class="mx-auto flex max-w-5xl gap-8 px-6 py-8 pb-24" @submit.prevent="save">
    <nav class="sticky top-8 hidden w-44 shrink-0 self-start md:block">
      <h1 class="mb-3 text-xl font-semibold tracking-tight">Pengaturan</h1>
      <a v-for="s in SECTIONS" :key="s.id" :href="`#${s.id}`" class="block rounded-md px-2 py-1.5 text-sm text-zinc-400 hover:bg-panel-2 hover:text-zinc-100">
        {{ s.label }}
      </a>
    </nav>

    <div class="flex min-w-0 flex-1 flex-col gap-6">
      <section id="deteksi" class="panel scroll-mt-8">
        <div class="panel-header">Deteksi momen</div>
        <div class="flex flex-col gap-4 p-4">
          <div>
            <div class="flex items-baseline justify-between">
              <label class="label" for="sens">Sensitivitas</label>
              <span class="tabnum text-sm text-zinc-200">{{ Number(form.detect.sensitivity).toFixed(2) }}</span>
            </div>
            <input id="sens" v-model.number="form.detect.sensitivity" type="range" min="0" max="1" step="0.05" class="w-full accent-violet-500" />
            <div class="flex justify-between text-[11px] text-zinc-500"><span>sedikit klip, paling seru saja</span><span>banyak klip</span></div>
          </div>

          <div class="flex flex-col divide-y divide-line rounded-md border border-line">
            <div v-for="s in signals" :key="s.weight" class="flex items-center gap-3 px-3 py-2.5">
              <Icon :name="s.icon" class="text-zinc-500" />
              <div class="min-w-0 flex-1">
                <div class="text-sm text-zinc-200">{{ s.label }}</div>
                <div class="text-[11px] text-zinc-500">{{ s.hint }}</div>
              </div>
              <label class="flex items-center gap-1.5 text-[11px] text-zinc-500" :class="{ 'opacity-40': 'toggle' in s && !form.detect[s.toggle] }">
                bobot
                <input v-model.number="form.detect[s.weight]" type="number" min="0" max="1" step="0.05" class="input h-7 w-16 px-1.5 text-xs tabnum" />
              </label>
              <input v-if="'toggle' in s" v-model="form.detect[s.toggle]" type="checkbox" class="check" :title="`Aktifkan ${s.label}`" />
              <span v-else class="w-4" />
            </div>
          </div>
        </div>
      </section>

      <section id="klip" class="panel scroll-mt-8">
        <div class="panel-header">Klip</div>
        <div class="grid gap-4 p-4 sm:grid-cols-2">
          <div v-for="f in clipFields" :key="f.key">
            <label class="label" :for="f.key">{{ f.label }}</label>
            <div class="relative">
              <input :id="f.key" v-model.number="form.detect[f.key]" class="input pr-10 tabnum" type="number" :min="f.min" :max="f.max" :step="f.step" />
              <span class="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-xs text-zinc-500">{{ f.unit }}</span>
            </div>
            <p v-if="f.hint" class="mt-1 text-[11px] text-zinc-500">{{ f.hint }}</p>
          </div>
          <div>
            <label class="label" for="res">Resolusi unduhan maksimal</label>
            <select id="res" v-model.number="form.detect.download_max_height" class="input">
              <option v-for="h in app.settings!.options.download_heights" :key="h" :value="h">{{ h }}p</option>
            </select>
          </div>
        </div>
      </section>

      <section id="subtitle" class="panel scroll-mt-8">
        <div class="panel-header">
          Subtitle (faster-whisper)
          <label class="flex items-center gap-2 normal-case tracking-normal text-zinc-300">
            <input v-model="form.subtitle.enabled" type="checkbox" class="check" /> aktif default
          </label>
        </div>
        <div class="grid gap-4 p-4 sm:grid-cols-3">
          <div>
            <label class="label" for="wm">Model</label>
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
        </div>
      </section>

      <section id="output" class="panel scroll-mt-8">
        <div class="panel-header">Render & thumbnail</div>
        <div class="grid gap-4 p-4 sm:grid-cols-2">
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
            <label class="flex items-center gap-2"><input v-model="form.thumbnail.enabled" type="checkbox" class="check" /> Buat thumbnail</label>
            <label class="flex items-center gap-2"><input v-model="form.thumbnail.landscape" type="checkbox" class="check" /> Juga buat thumbnail 1280×720</label>
            <label class="flex items-center gap-2"><input v-model="form.thumbnail.intro_frame" type="checkbox" class="check" /> Sisipkan thumbnail sebagai frame pembuka klip</label>
          </div>
        </div>
      </section>

      <section id="penyimpanan" class="panel scroll-mt-8">
        <div class="panel-header">Penyimpanan</div>
        <div class="flex flex-col gap-2 p-4">
          <label class="label" for="dd">Folder data</label>
          <input id="dd" v-model="form.data_dir" class="input font-mono text-xs" />
          <p class="text-xs text-zinc-500">
            Sedang dipakai: <span class="font-mono text-zinc-400">{{ app.settings!.data_dir }}</span> · berlaku setelah backend direstart.
            Disimpan di <span class="font-mono text-zinc-400">{{ app.settings!.config_file }}</span>.
          </p>
          <p v-if="app.settings!.restart_required" class="flex items-center gap-1.5 text-xs text-amber-400">
            <Icon name="alert" :size="12" /> Restart backend untuk memakai folder data baru.
          </p>
        </div>
      </section>
    </div>

    <Transition name="fade">
      <div v-if="dirty" class="fixed inset-x-0 bottom-4 z-30 flex justify-center px-4">
        <div class="panel flex items-center gap-3 px-3 py-2 shadow-2xl shadow-black/60">
          <span class="text-sm text-zinc-300">Ada perubahan yang belum disimpan</span>
          <button type="button" class="btn btn-quiet btn-sm" @click="fill">Batalkan</button>
          <button class="btn btn-primary btn-sm" :disabled="saving">
            <Icon :name="saving ? 'loader' : 'check'" :size="14" /> {{ saving ? 'Menyimpan…' : 'Simpan' }}
          </button>
        </div>
      </div>
    </Transition>
  </form>
</template>
