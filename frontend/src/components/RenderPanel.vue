<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { RenderOptions, Template } from '@/api'

const props = defineProps<{
  templates: Template[]
  template: string
  selectedCount: number
  locked: boolean
  defaults: RenderOptions
}>()
const emit = defineEmits<{
  'update:template': [name: string]
  render: [opts: RenderOptions]
  selectAll: []
  clearAll: []
}>()

const opts = reactive<RenderOptions>({ ...props.defaults })
watch(() => props.defaults, (d) => Object.assign(opts, d))
watch(() => opts.thumbnail, (on) => {
  if (!on) opts.intro_frame = opts.landscape = false
})
</script>

<template>
  <div class="card flex flex-col gap-4">
    <div class="flex gap-2">
      <button class="btn btn-ghost flex-1" :disabled="locked" @click="emit('selectAll')">Pilih semua</button>
      <button class="btn btn-ghost flex-1" :disabled="locked" @click="emit('clearAll')">Hapus pilihan</button>
    </div>

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
