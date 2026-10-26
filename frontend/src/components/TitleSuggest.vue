<script setup lang="ts">
import { ref, watch } from 'vue'
import { errorMessage, type Candidate } from '@/api'
import Icon from '@/components/Icon.vue'
import { useAppStore } from '@/stores/app'
import { useJobsStore } from '@/stores/jobs'

/** F-19: judul klip + saran dari LLM lokal (Ollama). Dipakai di kartu Hasil & tab Subtitle. */
const props = defineProps<{ candidate: Candidate; locked?: boolean; compact?: boolean }>()

const jobs = useJobsStore()
const app = useAppStore()
const draft = ref(props.candidate.title ?? '')
const busy = ref(false)
const copied = ref('')

watch(() => props.candidate.title, (t) => (draft.value = t ?? ''))

async function suggest() {
  busy.value = true
  try {
    await jobs.suggestTitles(props.candidate.id)
  } catch (e) {
    app.notify(errorMessage(e), 'error', 9000)
  } finally {
    busy.value = false
  }
}

async function save(title: string) {
  const t = title.trim()
  if (t === (props.candidate.title ?? '')) return
  try {
    await jobs.patchCandidate(props.candidate.id, { title: t })
    draft.value = t
  } catch (e) {
    app.notify(errorMessage(e), 'error')
  }
}

async function copy(text: string, key: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = key
    setTimeout(() => copied.value === key && (copied.value = ''), 1500)
  } catch {
    app.notify('Tidak bisa menyalin ke clipboard', 'info')
  }
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <label class="label mb-0" :for="`title-${candidate.id}`">Judul klip</label>
      <button
        class="btn btn-quiet btn-sm text-accent-300"
        :disabled="busy || locked"
        title="Sarankan judul dari transkrip (LLM lokal, Ollama)"
        @click="suggest"
      >
        <Icon :name="busy ? 'loader' : 'sparkles'" :size="13" />
        {{ busy ? 'Memikirkan…' : candidate.suggestions ? 'Saran lain' : 'Sarankan' }}
      </button>
    </div>
    <div class="flex gap-1">
      <input
        :id="`title-${candidate.id}`"
        v-model="draft"
        class="input"
        maxlength="150"
        :disabled="locked"
        placeholder="Pilih saran atau tulis sendiri"
        @change="save(draft)"
        @keydown.enter="save(draft)"
      />
      <button v-if="draft" class="btn btn-ghost btn-icon shrink-0" :title="copied === 'title' ? 'Tersalin' : 'Salin judul'" @click="copy(draft, 'title')">
        <Icon :name="copied === 'title' ? 'check' : 'clipboard'" :size="14" />
      </button>
    </div>
    <div v-if="busy && !candidate.suggestions" class="text-[11px] text-zinc-500">Memuat model ke GPU… percobaan pertama bisa ±10–30 detik.</div>

    <template v-if="candidate.suggestions">
      <ul class="flex flex-col gap-1">
        <li v-for="t in candidate.suggestions.titles" :key="t">
          <button
            class="w-full rounded-md border px-2 py-1.5 text-left text-xs transition-colors"
            :class="t === candidate.title ? 'border-accent-500 bg-accent-600/15 text-zinc-50' : 'border-line bg-panel-2 text-zinc-300 hover:border-line-strong'"
            :disabled="locked"
            title="Pakai judul ini"
            @click="save(t)"
          >
            <Icon v-if="t === candidate.title" name="check" :size="11" class="mr-1 inline text-accent-300" />{{ t }}
            <span class="float-right text-[10px] text-zinc-600 tabnum">{{ t.length }}</span>
          </button>
        </li>
      </ul>
      <div v-if="!compact && (candidate.suggestions.description || candidate.suggestions.hashtags.length)" class="flex flex-col gap-1 text-xs">
        <div v-if="candidate.suggestions.description" class="flex items-start gap-1">
          <p class="flex-1 text-zinc-400">{{ candidate.suggestions.description }}</p>
          <button class="btn btn-quiet btn-sm btn-icon h-6 w-6" title="Salin deskripsi" @click="copy(candidate.suggestions.description, 'desc')">
            <Icon :name="copied === 'desc' ? 'check' : 'clipboard'" :size="12" />
          </button>
        </div>
        <div v-if="candidate.suggestions.hashtags.length" class="flex items-start gap-1">
          <p class="flex-1 text-accent-300">{{ candidate.suggestions.hashtags.join(' ') }}</p>
          <button class="btn btn-quiet btn-sm btn-icon h-6 w-6" title="Salin hashtag" @click="copy(candidate.suggestions.hashtags.join(' '), 'tags')">
            <Icon :name="copied === 'tags' ? 'check' : 'clipboard'" :size="12" />
          </button>
        </div>
      </div>
      <p class="text-[10px] text-zinc-600">oleh {{ candidate.suggestions.model }} · ikut tersimpan di file kredit .txt</p>
    </template>
  </div>
</template>
