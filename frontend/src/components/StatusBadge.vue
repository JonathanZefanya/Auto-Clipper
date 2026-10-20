<script setup lang="ts">
import type { JobStatus } from '@/api'
import { STATUS_CLASS, STATUS_LABEL } from '@/format'

defineProps<{ status: JobStatus }>()
</script>

<template>
  <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1" :class="STATUS_CLASS[status]">
    {{ STATUS_LABEL[status] }}
  </span>
</template>
