<script setup lang="ts">
import { ref, watch } from 'vue'
import Icon from '@/components/Icon.vue'
import { fmtTime } from '@/format'

/** Preview video sumber pada rentang kandidat (HTML5 + HTTP Range dari backend). */
const props = defineProps<{ src: string; start: number | null; end: number | null; seekTo: number | null; label?: string }>()
const emit = defineEmits<{ time: [t: number] }>()

const video = ref<HTMLVideoElement | null>(null)
const loop = ref(true)
const now = ref(0)
const playing = ref(false)

function seek(t: number, play = true) {
  const v = video.value
  if (!v) return
  v.currentTime = t
  if (play) void v.play().catch(() => undefined)
}

function toggle() {
  const v = video.value
  if (!v) return
  if (v.paused) {
    if (props.start != null && props.end != null && (v.currentTime < props.start || v.currentTime >= props.end)) {
      v.currentTime = props.start
    }
    void v.play().catch(() => undefined)
  } else v.pause()
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

defineExpose({ seek, toggle })
</script>

<template>
  <div class="panel overflow-hidden">
    <div class="relative bg-black">
      <video
        ref="video"
        :src="src"
        class="aspect-video max-h-[58vh] w-full"
        controls
        preload="metadata"
        @timeupdate="onTime"
        @play="playing = true"
        @pause="playing = false"
      />
      <span v-if="label" class="pointer-events-none absolute top-2 left-2 rounded bg-black/70 px-1.5 py-0.5 text-xs font-semibold">
        {{ label }}
      </span>
    </div>
    <div class="flex h-9 items-center gap-3 border-t border-line px-3 text-xs text-zinc-400">
      <button class="btn btn-quiet btn-sm btn-icon" :title="playing ? 'Jeda (Spasi)' : 'Putar (Spasi)'" @click="toggle">
        <Icon :name="playing ? 'pause' : 'play'" :size="14" />
      </button>
      <span class="tabnum text-zinc-200">{{ fmtTime(now) }}</span>
      <span v-if="start != null && end != null" class="tabnum">rentang {{ fmtTime(start) }} – {{ fmtTime(end) }}</span>
      <span class="flex-1" />
      <label class="flex cursor-pointer items-center gap-1.5">
        <input v-model="loop" type="checkbox" class="check h-3.5 w-3.5" /> ulangi rentang
      </label>
    </div>
  </div>
</template>
