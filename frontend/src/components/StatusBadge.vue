<script setup lang="ts">
import { ACTIVE_STATUSES, type JobStatus } from '@/api'
import { STATUS_CLASS, STATUS_LABEL } from '@/format'

defineProps<{ status: JobStatus }>()
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1"
    :class="STATUS_CLASS[status]"
  >
    <span
      class="h-1.5 w-1.5 rounded-full bg-current"
      :class="{ 'animate-pulse': ACTIVE_STATUSES.includes(status) }"
    />
    {{ STATUS_LABEL[status] }}
  </span>
</template>
