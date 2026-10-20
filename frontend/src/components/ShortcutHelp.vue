<script setup lang="ts">
import Icon from '@/components/Icon.vue'

defineEmits<{ close: [] }>()

const rows = [
  [['↑', '↓'], 'Klip sebelumnya / berikutnya'],
  [['Spasi'], 'Putar / jeda preview'],
  [['X'], 'Centang / batal centang klip'],
  [['Q', 'W'], 'Geser awal −1 / +1 detik'],
  [['E', 'R'], 'Geser akhir −1 / +1 detik'],
  [['Shift'], '+ Q/W/E/R → langkah 5 detik'],
  [['1', '2', '3'], 'Tab Klip / Subtitle / Output'],
  [['Ctrl', 'Enter'], 'Render klip terpilih'],
  [['?'], 'Tampilkan bantuan ini'],
] as const
</script>

<template>
  <div class="fixed inset-0 z-40 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" @click.self="$emit('close')">
    <div class="panel w-full max-w-sm shadow-2xl shadow-black/60">
      <div class="panel-header">
        <span class="flex items-center gap-2"><Icon name="keyboard" :size="14" /> Shortcut keyboard</span>
        <button class="btn btn-quiet btn-sm btn-icon" @click="$emit('close')"><Icon name="x" :size="14" /></button>
      </div>
      <ul class="flex flex-col gap-2 p-3 text-sm">
        <li v-for="[keys, desc] in rows" :key="desc" class="flex items-center justify-between gap-3">
          <span class="text-zinc-300">{{ desc }}</span>
          <span class="flex gap-1"><kbd v-for="k in keys" :key="k" class="kbd">{{ k }}</kbd></span>
        </li>
      </ul>
    </div>
  </div>
</template>
