<script setup lang="ts">
import {
  Chart,
  Decimation,
  Filler,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  type Plugin,
} from 'chart.js'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Scores } from '@/api'
import { fmtTime } from '@/format'

Chart.register(LineController, LineElement, PointElement, LinearScale, Filler, Tooltip, Decimation)

const props = defineProps<{ scores: Scores; activeId: number | null; playhead: number | null }>()
const emit = defineEmits<{ select: [id: number]; seek: [t: number] }>()

const canvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null

/** Gambar rentang kandidat (bayangan), nomor rank, dan playhead di belakang/depan garis. */
const overlay: Plugin<'line'> = {
  id: 'candidates',
  beforeDatasetsDraw(c) {
    const { ctx, chartArea: a, scales } = c
    const x = scales.x
    ctx.save()
    for (const cand of props.scores.candidates) {
      const x0 = Math.max(a.left, x.getPixelForValue(cand.start))
      const x1 = Math.min(a.right, x.getPixelForValue(cand.end))
      const active = cand.id === props.activeId
      ctx.fillStyle = active
        ? 'rgba(167,139,250,0.30)'
        : cand.selected
          ? 'rgba(52,211,153,0.16)'
          : 'rgba(161,161,170,0.10)'
      ctx.fillRect(x0, a.top, Math.max(2, x1 - x0), a.bottom - a.top)
      ctx.fillStyle = active ? '#c4b5fd' : cand.selected ? '#6ee7b7' : '#a1a1aa'
      ctx.font = '600 11px Inter, system-ui, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(`#${cand.rank}`, (x0 + x1) / 2, a.top + 12)
    }
    ctx.restore()
  },
  afterDatasetsDraw(c) {
    if (props.playhead == null) return
    const { ctx, chartArea: a, scales } = c
    const px = scales.x.getPixelForValue(props.playhead)
    if (px < a.left || px > a.right) return
    ctx.save()
    ctx.strokeStyle = '#f472b6'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.moveTo(px, a.top)
    ctx.lineTo(px, a.bottom)
    ctx.stroke()
    ctx.restore()
  },
}

function build() {
  if (!canvas.value) return
  chart?.destroy()
  const s = props.scores
  const points = s.smoothed.map((y, i) => ({ x: i, y }))
  chart = new Chart(canvas.value, {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'Skor',
          data: points,
          borderColor: '#a78bfa',
          backgroundColor: 'rgba(139,92,246,0.15)',
          borderWidth: 1.25,
          pointRadius: 0,
          fill: true,
          tension: 0,
        },
        {
          label: 'Ambang',
          data: [
            { x: 0, y: s.threshold },
            { x: Math.max(1, s.duration - 1), y: s.threshold },
          ],
          borderColor: 'rgba(251,191,36,0.6)',
          borderDash: [5, 4],
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      animation: false,
      parsing: false,
      normalized: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      scales: {
        x: {
          type: 'linear',
          min: 0,
          max: Math.max(1, s.duration - 1),
          grid: { color: 'rgba(63,63,70,0.4)' },
          ticks: { color: '#71717a', maxTicksLimit: 12, callback: (v) => fmtTime(Number(v)) },
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(63,63,70,0.4)' },
          ticks: { color: '#71717a', maxTicksLimit: 5 },
        },
      },
      plugins: {
        decimation: { enabled: true, algorithm: 'lttb', samples: 1200 },
        tooltip: {
          callbacks: {
            title: (items) => fmtTime(items[0]?.parsed.x ?? 0),
            label: (item) => `${item.dataset.label}: ${(item.parsed.y ?? 0).toFixed(2)}`,
          },
        },
      },
      onClick(_e, _els, c) {
        const native = _e.native as MouseEvent | null
        if (!native) return
        const t = c.scales.x.getValueForPixel(native.offsetX)
        if (t == null) return
        const hit = props.scores.candidates.find((cand) => t >= cand.start && t <= cand.end)
        if (hit) emit('select', hit.id)
        else emit('seek', Math.max(0, t))
      },
    },
    plugins: [overlay],
  })
}

onMounted(build)
onBeforeUnmount(() => chart?.destroy())
watch(() => props.scores.smoothed, build)
watch(
  () => [props.activeId, props.playhead, props.scores.candidates.map((c) => `${c.start}-${c.end}-${c.selected}`).join()],
  () => chart?.draw(),
)
</script>

<template>
  <div class="card">
    <div class="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
      <span class="font-medium text-zinc-300">Skor momen sepanjang video</span>
      <span class="flex gap-3">
        <span><span class="mr-1 inline-block h-2 w-3 rounded-sm bg-violet-400/50" />aktif</span>
        <span><span class="mr-1 inline-block h-2 w-3 rounded-sm bg-emerald-400/30" />dipilih</span>
        <span><span class="mr-1 inline-block h-0 w-3 border-t border-dashed border-amber-400" />ambang</span>
        <span v-if="!scores.has_chat" class="text-zinc-500">tanpa live chat (audio saja)</span>
      </span>
    </div>
    <div class="h-56">
      <canvas ref="canvas" class="cursor-crosshair" />
    </div>
  </div>
</template>
