import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ACTIVE_STATUSES, api, type Candidate, type Job, type JobDetail, type RenderOptions, type Scores } from '@/api'

export const useJobsStore = defineStore('jobs', () => {
  const list = ref<Job[]>([])
  const current = ref<JobDetail | null>(null)
  const scores = ref<Scores | null>(null)
  let source: EventSource | null = null
  let watchedId: string | null = null

  async function fetchList() {
    list.value = await api.listJobs()
  }

  async function loadScores(id: string) {
    try {
      scores.value = await api.scores(id)
    } catch {
      scores.value = null
    }
  }

  async function load(id: string) {
    const detail = await api.getJob(id)
    current.value = detail
    if (detail.candidate_count > 0) await loadScores(id)
    else scores.value = null
    if (ACTIVE_STATUSES.includes(detail.status)) subscribe(id)
    return detail
  }

  /** SSE: perbarui status/progres job secara real-time; muat ulang detail saat selesai. */
  function subscribe(id: string) {
    if (source && watchedId === id) return
    unsubscribe()
    watchedId = id
    source = new EventSource(api.eventsUrl(id))
    source.addEventListener('job', (ev) => {
      const data = JSON.parse((ev as MessageEvent).data) as Job
      if (current.value?.id === data.id) Object.assign(current.value, data)
      const idx = list.value.findIndex((j) => j.id === data.id)
      if (idx >= 0) list.value[idx] = { ...list.value[idx], ...data }
    })
    source.addEventListener('end', () => {
      unsubscribe()
      if (current.value?.id === id) void load(id)
    })
    source.addEventListener('deleted', () => unsubscribe())
  }

  function unsubscribe() {
    source?.close()
    source = null
    watchedId = null
  }

  function replaceCandidate(c: Candidate) {
    if (!current.value) return
    const idx = current.value.candidates.findIndex((x) => x.id === c.id)
    if (idx >= 0) current.value.candidates[idx] = c
    current.value.selected_count = current.value.candidates.filter((x) => x.selected).length
    const sc = scores.value?.candidates.find((x) => x.id === c.id)
    if (sc) Object.assign(sc, { start: c.start, end: c.end, selected: c.selected })
  }

  async function patchCandidate(id: number, body: Parameters<typeof api.patchCandidate>[1]) {
    const c = await api.patchCandidate(id, body)
    replaceCandidate(c)
    return c
  }

  async function setSelection(selected: boolean) {
    if (!current.value) return
    const detail = await api.setSelection(current.value.id, { selected })
    current.value.candidates = detail.candidates
    current.value.selected_count = detail.selected_count
    if (scores.value) for (const c of scores.value.candidates) c.selected = selected
  }

  async function render(options: Partial<RenderOptions> & { template?: string }) {
    if (!current.value) return
    const job = await api.render(current.value.id, options)
    Object.assign(current.value, job)
    subscribe(job.id)
  }

  /** F-16: transkripsi kandidat terpilih tanpa render. */
  async function transcribe() {
    if (!current.value) return
    const job = await api.transcribe(current.value.id)
    Object.assign(current.value, job)
    subscribe(job.id)
  }

  async function setTemplate(template: string) {
    if (!current.value) return
    const job = await api.updateJob(current.value.id, { template })
    current.value.template = job.template
  }

  /** Batalkan job antre/berjalan; status akhir datang lewat SSE (atau langsung bila masih antre). */
  async function cancel(id: string) {
    const job = await api.cancelJob(id)
    if (current.value?.id === id) Object.assign(current.value, job)
    const idx = list.value.findIndex((j) => j.id === id)
    if (idx >= 0) list.value[idx] = { ...list.value[idx], ...job }
    if (ACTIVE_STATUSES.includes(job.status)) subscribe(id)
    else if (current.value?.id === id) await load(id)
    return job
  }

  async function remove(id: string) {
    await api.deleteJob(id)
    list.value = list.value.filter((j) => j.id !== id)
    if (current.value?.id === id) current.value = null
  }

  return {
    list, current, scores,
    fetchList, load, subscribe, unsubscribe, patchCandidate, setSelection, render, transcribe, setTemplate,
    cancel, remove,
  }
})
