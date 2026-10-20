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
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { Scores } from '@/api'
import { fmtTime } from '@/format'

Chart.register(LineController, LineElement, PointElement, LinearScale, Filler, Tooltip, Decimation)

const props = defineProps<{ scores: Scores; activeId: number | null; playhead: number | null }>()
const emit = defineEmits<{ select: [id: number]; seek: [t: number] }>()

const canvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null

/** Sinyal tambahan yang bisa ditampilkan sebagai garis tipis di atas skor gabungan. */
const EXTRAS = [
  { key: 'reaction', label: 'Tawa/teriak', color: 'rgba(244,114,182,0.6)', css: 'border-pink-400', text: 'text-pink-300' },
  { key: 'face', label: 'Ekspresi wajah', color: 'rgba(34,211,238,0.6)', css: 'border-cyan-400', text: 'text-cyan-300' },
] as const
type ExtraKey = (typeof EXTRAS)[number]['key']
const shown = reactive<Record<ExtraKey, boolean>>({ reaction: false, face: false })
const available = computed(() => EXTRAS.filter((e) => props.scores[`has_${e.key}`] && props.scores[e.key]))

function toggle(key: ExtraKey) {
  shown[key] = !shown[key]
  const label = EXTRAS.find((e) => e.key === key)!.label
  const ds = chart?.data.datasets.find((d) => d.label === label)
  if (ds) {
    ds.hidden = !shown[key]
    chart?.update('none')
  }
}

const signalText = computed(() => {
  const s = props.scores
  return ['audio', s.has_chat && 'chat', s.has_reaction && 'tawa/teriak', s.has_face && 'ekspresi wajah']
    .filter(Boolean).join(' + ')
})

/** Gambar rentang kandidat (bayangan), nomor rank, dan playhead di belakang/depan garis. */
const overlay: Plugin<'line'> = {
  id: 'candidates',
  beforeDatasetsDraw(c) {
    const { ctx, chartArea: a, scales } = c
    const x = scales.x
    ctx.save()
    // zona intro/outro yang tidak dijadikan kandidat
    for (const [s0, s1] of props.scores.excluded ?? []) {
      const x0 = Math.max(a.left, x.getPixelForValue(s0))
      const x1 = Math.min(a.right, x.getPixelForValue(s1))
      ctx.fillStyle = 'rgba(9,9,11,0.55)'
      ctx.fillRect(x0, a.top, Math.max(1, x1 - x0), a.bottom - a.top)
      ctx.fillStyle = '#52525b'
      ctx.font = '10px Inter, system-ui, sans-serif'
      ctx.textAlign = 'center'
      if (x1 - x0 > 30) ctx.fillText(s0 === 0 ? 'intro' : 'outro', (x0 + x1) / 2, a.bottom - 6)
    }
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
        ...available.value.map((e) => ({
          label: e.label,
          data: (s[e.key] ?? []).map((y, i) => ({ x: i, y })),
          borderColor: e.color,
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
          tension: 0,
          hidden: !shown[e.key],
        })),
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
        <button
          v-for="e in available"
          :key="e.key"
          type="button"
          class="hover:text-zinc-200"
          :class="shown[e.key] ? e.text : ''"
          @click="toggle(e.key)"
        >
          <span class="mr-1 inline-block h-0 w-3 border-t" :class="e.css" />{{ e.label.toLowerCase() }}
          {{ shown[e.key] ? '✓' : '' }}
        </button>
        <span class="text-zinc-500" :title="scores.face_info?.skipped ? `ekspresi wajah: ${scores.face_info.skipped}` : undefined">
          sinyal: {{ signalText }}
        </span>
      </span>
    </div>
    <div class="h-56">
      <canvas ref="canvas" class="cursor-crosshair" />
    </div>
  </div>
</template>
