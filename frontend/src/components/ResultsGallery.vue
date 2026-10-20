<script setup lang="ts">
import { computed } from 'vue'
import { api, type Candidate, type JobDetail } from '@/api'
import Icon from '@/components/Icon.vue'
import { fmtTime } from '@/format'

const props = defineProps<{ job: JobDetail; locked: boolean }>()
const emit = defineEmits<{
  saveText: [id: number, text: string]
  regenerateThumbs: []
  openFolder: []
  review: []
}>()

const results = computed(() => props.job.candidates.filter((c) => c.clip_url || c.thumb_url))
const outdated = computed(() => props.job.candidates.filter((c) => c.selected && !c.clip_url).length)
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
  <div class="flex flex-col gap-4 p-4">
    <div class="flex flex-wrap items-center gap-2">
      <h2 class="text-base font-semibold">{{ results.length }} klip</h2>
      <span v-if="outdated" class="chip border-amber-900 text-amber-300">
        <Icon name="alert" :size="12" /> {{ outdated }} klip terpilih belum dirender ulang
      </span>
      <span class="flex-1" />
      <button class="btn btn-ghost btn-sm" :disabled="locked" title="Pakai teks thumbnail yang baru" @click="emit('regenerateThumbs')">
        <Icon name="refresh" :size="14" /> Buat ulang thumbnail
      </button>
      <button class="btn btn-ghost btn-sm" @click="emit('openFolder')"><Icon name="folder" :size="14" /> Buka folder</button>
      <a class="btn btn-primary btn-sm" :href="api.zipUrl(job.id)"><Icon name="download" :size="14" /> Unduh semua (ZIP)</a>
    </div>

    <div v-if="!results.length" class="panel flex flex-col items-center gap-3 py-16 text-center">
      <Icon name="film" :size="28" class="text-zinc-600" />
      <p class="text-sm text-zinc-400">Belum ada klip. Pilih kandidat di Review lalu klik Render.</p>
      <button class="btn btn-ghost" @click="emit('review')">Ke Review</button>
    </div>

    <div class="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(250px,1fr))]">
      <article v-for="c in results" :key="c.id" class="panel flex flex-col overflow-hidden">
        <div class="relative bg-black">
          <video
            v-if="c.clip_url"
            :src="withV(c.clip_url)"
            :poster="withV(c.thumb_url)"
            class="aspect-[9/16] w-full object-contain"
            controls
            preload="none"
          />
          <img v-else-if="c.thumb_url" :src="withV(c.thumb_url)" class="aspect-[9/16] w-full object-contain" alt="thumbnail" />
          <span class="pointer-events-none absolute top-2 left-2 rounded bg-black/75 px-1.5 py-0.5 text-xs font-semibold">#{{ c.rank }}</span>
          <span v-if="!c.clip_url" class="absolute inset-x-2 bottom-2 rounded bg-amber-950/90 px-2 py-1 text-[11px] text-amber-200">
            Rentang diubah — render ulang
          </span>
        </div>

        <div class="flex flex-col gap-2.5 p-3">
          <div class="flex items-center justify-between text-xs text-zinc-400 tabnum">
            <span>{{ fmtTime(c.start) }} – {{ fmtTime(c.end) }} · {{ Math.round(c.duration) }}s</span>
            <span class="text-zinc-300">skor {{ c.score }}</span>
          </div>

          <div v-if="c.thumb_landscape_url" class="flex gap-1.5">
            <a :href="withV(c.thumb_landscape_url)" target="_blank" class="flex-1" title="Thumbnail 16:9">
              <img :src="withV(c.thumb_landscape_url)" class="aspect-video w-full rounded object-cover ring-1 ring-line" alt="thumbnail 16:9" />
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

          <div class="flex flex-wrap gap-1">
            <a v-if="c.clip_url" class="btn btn-ghost btn-sm" :href="c.clip_url" :download="fileName(c.clip_path)"><Icon name="download" :size="12" /> MP4</a>
            <a v-if="c.thumb_url" class="btn btn-ghost btn-sm" :href="c.thumb_url" :download="fileName(c.thumb_path)">PNG 9:16</a>
            <a v-if="c.thumb_landscape_url" class="btn btn-ghost btn-sm" :href="c.thumb_landscape_url" :download="fileName(c.thumb_landscape_path)">16:9</a>
            <a v-if="creditUrl(c)" class="btn btn-ghost btn-sm" :href="creditUrl(c)!" :download="fileName(c.credit_path)" title="Judul, channel & link sumber untuk kredit">Kredit</a>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>
