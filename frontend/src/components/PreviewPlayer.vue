<script setup lang="ts">
import { ref, watch } from 'vue'
import { fmtTime } from '@/format'

/** Preview video sumber pada rentang kandidat (HTML5 + HTTP Range dari backend). */
const props = defineProps<{ src: string; start: number | null; end: number | null; seekTo: number | null }>()
const emit = defineEmits<{ time: [t: number] }>()

const video = ref<HTMLVideoElement | null>(null)
const loop = ref(true)
const now = ref(0)

function seek(t: number, play = true) {
  const v = video.value
  if (!v) return
  v.currentTime = t
  if (play) void v.play().catch(() => undefined)
}

function onTime() {
  const v = video.value
  if (!v) return
  now.value = v.currentTime
  emit('time', v.currentTime)
  if (props.start != null && props.end != null && v.currentTime >= props.end) {
    if (loop.value) v.currentTime = props.start
    else v.pause()
  }
}

watch(() => [props.start, props.end] as const, ([s], old) => {
  if (s == null) return
  const startChanged = !old || old[0] !== s
  // trim akhir: putar 3 detik terakhir agar titik potong terdengar; selain itu dari awal
  if (startChanged) seek(s)
  else if (props.end != null) seek(Math.max(s, props.end - 3))
})
watch(() => props.seekTo, (t) => t != null && seek(t))

defineExpose({ seek })
</script>

<template>
  <div class="card">
    <video
      ref="video"
      :src="src"
      class="aspect-video w-full rounded-lg bg-black"
      controls
      preload="metadata"
      @timeupdate="onTime"
    />
    <div class="mt-2 flex items-center justify-between text-xs text-zinc-400">
      <span class="tabular-nums">
        {{ fmtTime(now) }}
        <template v-if="start != null && end != null"> · rentang {{ fmtTime(start) }}–{{ fmtTime(end) }}</template>
      </span>
      <label class="flex cursor-pointer items-center gap-1.5">
        <input v-model="loop" type="checkbox" class="accent-violet-500" /> ulangi rentang
      </label>
    </div>
  </div>
</template>
