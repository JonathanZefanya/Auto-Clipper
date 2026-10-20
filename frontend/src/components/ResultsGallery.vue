<script setup lang="ts">
import { computed } from 'vue'
import { api, type Candidate, type JobDetail } from '@/api'
import { fmtTime } from '@/format'

const props = defineProps<{ job: JobDetail; locked: boolean }>()
const emit = defineEmits<{
  saveText: [id: number, text: string]
  regenerateThumbs: []
  openFolder: []
}>()

const results = computed(() => props.job.candidates.filter((c) => c.clip_url || c.thumb_url))
// cache-buster agar thumbnail/klip yang dibuat ulang langsung tampil
const v = computed(() => encodeURIComponent(props.job.updated_at))

function withV(url: string | null) {
  return url ? `${url}?v=${v.value}` : undefined
}

function fileName(path: string | null) {
  return path?.split('/').pop() ?? ''
}

function creditUrl(c: Candidate) {
  return c.credit_path ? `/api/jobs/${c.job_id}/files/${c.credit_path}` : null
}
</script>

<template>
  <section v-if="results.length" class="flex flex-col gap-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 class="text-lg font-semibold">Hasil ({{ results.length }})</h2>
      <div class="flex flex-wrap gap-2">
        <button class="btn btn-ghost" :disabled="locked" @click="emit('regenerateThumbs')">
          Buat ulang thumbnail (klip terpilih)
        </button>
        <button class="btn btn-ghost" @click="emit('openFolder')">Buka folder output</button>
        <a class="btn btn-primary" :href="api.zipUrl(job.id)">Unduh semua (ZIP)</a>
      </div>
    </div>

    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <article v-for="c in results" :key="c.id" class="card flex flex-col gap-3 p-3">
        <div class="flex items-center justify-between text-sm">
          <span class="font-semibold">#{{ c.rank }}</span>
          <span class="text-xs text-zinc-400 tabular-nums">{{ fmtTime(c.start) }}–{{ fmtTime(c.end) }}</span>
        </div>

        <video
          v-if="c.clip_url"
          :src="withV(c.clip_url)"
          :poster="withV(c.thumb_url)"
          class="aspect-[9/16] w-full rounded-lg bg-black object-contain"
          controls
          preload="none"
        />
        <img
          v-else-if="c.thumb_url"
          :src="withV(c.thumb_url)"
          class="aspect-[9/16] w-full rounded-lg bg-black object-contain"
          alt="thumbnail"
        />
        <p v-else class="text-xs text-amber-400">Rentang diubah — render ulang untuk membuat klip.</p>

        <div v-if="c.thumb_url || c.thumb_landscape_url" class="flex gap-2">
          <a v-if="c.thumb_url" :href="withV(c.thumb_url)" target="_blank" class="w-1/3">
            <img :src="withV(c.thumb_url)" class="aspect-[9/16] w-full rounded object-cover ring-1 ring-zinc-700" alt="thumbnail 9:16" />
          </a>
          <a v-if="c.thumb_landscape_url" :href="withV(c.thumb_landscape_url)" target="_blank" class="flex-1">
            <img :src="withV(c.thumb_landscape_url)" class="aspect-video w-full rounded object-cover ring-1 ring-zinc-700" alt="thumbnail 16:9" />
          </a>
        </div>

        <div>
          <label class="label" :for="`tt-${c.id}`">Teks thumbnail</label>
          <input
            :id="`tt-${c.id}`"
            class="input"
            :value="c.thumb_text ?? ''"
            :disabled="locked"
            placeholder="otomatis dari transkrip"
            @change="emit('saveText', c.id, ($event.target as HTMLInputElement).value)"
          />
        </div>

        <div class="mt-auto flex flex-wrap gap-1.5 text-xs">
          <a v-if="c.clip_url" class="btn btn-ghost px-2 py-1 text-xs" :href="c.clip_url" :download="fileName(c.clip_path)">MP4</a>
          <a v-if="c.thumb_url" class="btn btn-ghost px-2 py-1 text-xs" :href="c.thumb_url" :download="fileName(c.thumb_path)">PNG 9:16</a>
          <a
            v-if="c.thumb_landscape_url"
            class="btn btn-ghost px-2 py-1 text-xs"
            :href="c.thumb_landscape_url"
            :download="fileName(c.thumb_landscape_path)"
          >PNG 16:9</a>
          <a v-if="creditUrl(c)" class="btn btn-ghost px-2 py-1 text-xs" :href="creditUrl(c)!" :download="fileName(c.credit_path)">Kredit .txt</a>
        </div>
      </article>
    </div>
  </section>
</template>
