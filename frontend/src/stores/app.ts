import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type Settings, type Template } from '@/api'

export interface Toast {
  id: number
  kind: 'error' | 'info' | 'success'
  text: string
}

/** Pengaturan, template layout, dan notifikasi. */
export const useAppStore = defineStore('app', () => {
  const settings = ref<Settings | null>(null)
  const templates = ref<Template[]>([])
  const toasts = ref<Toast[]>([])
  let seq = 0

  function notify(text: string, kind: Toast['kind'] = 'info', ms = 4500) {
    const id = ++seq
    toasts.value.push({ id, kind, text })
    setTimeout(() => (toasts.value = toasts.value.filter((t) => t.id !== id)), ms)
  }

  async function loadSettings() {
    settings.value = await api.settings()
    return settings.value
  }

  async function saveSettings(body: Record<string, unknown>) {
    settings.value = await api.saveSettings(body)
    return settings.value
  }

  async function loadTemplates() {
    templates.value = await api.templates()
    return templates.value
  }

  async function saveTemplate(t: Template) {
    await api.saveTemplate(t)
    await loadTemplates()
  }

  async function deleteTemplate(name: string) {
    await api.deleteTemplate(name)
    templates.value = templates.value.filter((t) => t.name !== name)
  }

  return { settings, templates, toasts, notify, loadSettings, saveSettings, loadTemplates, saveTemplate, deleteTemplate }
})
