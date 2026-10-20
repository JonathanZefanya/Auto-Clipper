<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, ApiError, errorMessage, type Candidate, type SubLine, type Subtitles } from '@/api'
import { useAppStore } from '@/stores/app'

/** F-16: edit baris subtitle per klip sebelum render. Waktu relatif terhadap awal klip. */
const props = defineProps<{ candidate: Candidate; locked: boolean; selectedCount: number }>()
const emit = defineEmits<{ seek: [sourceTime: number]; transcribe: []; changed: [hasSubs: boolean] }>()

const app = useAppStore()
const subs = ref<Subtitles | null>(null)
const draft = ref<SubLine[]>([])
const loading = ref(false)
const saving = ref(false)

const dirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(subs.value?.lines ?? []))
const duration = computed(() => props.candidate.end - props.candidate.start)

function fmt(t: number) {
  const m = Math.floor(t / 60)
  return `${m}:${(t - m * 60).toFixed(1).padStart(4, '0')}`
}

async function load() {
  subs.value = null
  draft.value = []
  if (!props.candidate.subs_path) return
  loading.value = true
  try {
    subs.value = await api.getSubtitles(props.candidate.id)
    draft.value = subs.value.lines.map((l) => ({ ...l }))
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 404)) app.notify(errorMessage(e), 'error')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.candidate.id, props.candidate.subs_path, props.candidate.start, props.candidate.end],
  load,
  { immediate: true },
)

function addLine() {
  const last = draft.value[draft.value.length - 1]
  const start = Math.min(last ? last.end + 0.1 : 0, Math.max(0, duration.value - 1))
  draft.value.push({ start: +start.toFixed(2), end: +Math.min(duration.value, start + 1.5).toFixed(2), text: '' })
}

async function save() {
  saving.value = true
  try {
    const lines = draft.value.filter((l) => l.text.trim())
    subs.value = await api.saveSubtitles(props.candidate.id, lines)
    draft.value = subs.value.lines.map((l) => ({ ...l }))
    emit('changed', true)
    app.notify('Subtitle disimpan — dipakai saat render', 'success')
  } catch (e) {
    app.notify(errorMessage(e), 'error', 7000)
  } finally {
    saving.value = false
  }
}

async function reset() {
  if (!confirm('Hapus subtitle hasil edit dan kembali ke subtitle otomatis?')) return
  try {
    await api.resetSubtitles(props.candidate.id)
    subs.value = null
    draft.value = []
    emit('changed', false)
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}
</script>

<template>
  <div class="card flex flex-col gap-3">
    <div class="flex items-center justify-between gap-2">
      <h3 class="text-sm font-semibold">Subtitle klip #{{ candidate.rank }}</h3>
      <span
        v-if="subs"
        class="rounded px-1.5 py-0.5 text-[10px]"
        :class="subs.edited ? 'bg-accent-600/30 text-violet-200' : 'bg-zinc-800 text-zinc-400'"
      >{{ subs.edited ? 'diedit' : 'otomatis' }}</span>
    </div>

    <p v-if="loading" class="text-xs text-zinc-500">Memuat…</p>

    <template v-else-if="!subs">
      <p class="text-xs text-zinc-400">
        Belum ditranskripsi. Subtitle tetap dibuat otomatis saat render, atau transkripsi dulu untuk mengeditnya.
      </p>
      <button
        class="btn btn-ghost"
        :disabled="locked || selectedCount === 0"
        @click="emit('transcribe')"
      >
        Transkripsi klip terpilih ({{ selectedCount }})
      </button>
      <p v-if="!candidate.selected" class="-mt-1 text-xs text-zinc-500">Centang klip ini agar ikut ditranskripsi.</p>
    </template>

    <template v-else>
      <p v-if="subs.stale" class="rounded border border-amber-900 bg-amber-950/40 p-2 text-xs text-amber-300">
        Rentang klip berubah sejak transkripsi. Waktu sudah disesuaikan, tapi bagian baru belum bersubtitle —
        transkripsi ulang bila perlu.
      </p>

      <ul class="flex max-h-80 flex-col gap-1.5 overflow-y-auto pr-1">
        <li v-for="(ln, i) in draft" :key="i" class="flex items-center gap-1.5">
          <button
            type="button"
            class="w-14 shrink-0 rounded bg-zinc-800 px-1 py-1 text-[11px] tabular-nums text-zinc-300 hover:bg-zinc-700"
            title="Putar dari sini"
            @click="emit('seek', candidate.start + ln.start)"
          >
            {{ fmt(ln.start) }}
          </button>
          <input v-model.number="ln.start" type="number" step="0.1" min="0" :max="duration" :disabled="locked"
                 class="input w-16 px-1.5 py-1 text-xs tabular-nums" aria-label="mulai" />
          <input v-model.number="ln.end" type="number" step="0.1" min="0" :max="duration" :disabled="locked"
                 class="input w-16 px-1.5 py-1 text-xs tabular-nums" aria-label="selesai" />
          <input v-model="ln.text" :disabled="locked" class="input min-w-0 flex-1 px-2 py-1 text-xs" aria-label="teks" />
          <button type="button" class="px-1 text-zinc-500 hover:text-red-400" :disabled="locked"
                  title="Hapus baris" @click="draft.splice(i, 1)">×</button>
        </li>
        <li v-if="!draft.length" class="text-xs text-zinc-500">Tidak ada baris (klip tanpa ucapan).</li>
      </ul>

      <div class="flex flex-wrap gap-1.5">
        <button class="btn btn-ghost px-2 py-1 text-xs" :disabled="locked" @click="addLine">+ Baris</button>
        <button class="btn btn-primary px-2.5 py-1 text-xs" :disabled="locked || !dirty || saving" @click="save">
          {{ saving ? 'Menyimpan…' : 'Simpan' }}
        </button>
        <button v-if="dirty" class="btn btn-ghost px-2 py-1 text-xs" @click="draft = subs.lines.map((l) => ({ ...l }))">
          Batalkan perubahan
        </button>
        <span class="flex-1" />
        <button class="btn btn-ghost px-2 py-1 text-xs" :disabled="locked || selectedCount === 0"
                title="Transkripsi ulang klip terpilih" @click="emit('transcribe')">Transkripsi ulang</button>
        <button class="btn btn-danger px-2 py-1 text-xs" :disabled="locked" @click="reset">Reset</button>
      </div>
      <p class="text-[11px] text-zinc-500">Waktu dalam detik relatif terhadap awal klip (durasi {{ duration.toFixed(0) }} dtk).</p>
    </template>
  </div>
</template>
