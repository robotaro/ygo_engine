// Preset UI themes. Each recolours the app's primary accent (buttons, highlights,
// LP, the phase capsule, the DP chip…) plus a secondary accent, and is remembered
// in the browser. Presets only — no custom pickers.
import { writable } from 'svelte/store'

export const THEMES = [
  { id: 'amber', name: 'Amber', primary: '#f0b429', ink: '#1a1400', hover: '#ffc340', secondary: '#6b8afd' },
  { id: 'blue', name: 'Dark Blue', primary: '#4f7dff', ink: '#f6f9ff', hover: '#6f95ff', secondary: '#f0b429' },
  { id: 'emerald', name: 'Emerald', primary: '#12b886', ink: '#04231a', hover: '#1ed69b', secondary: '#f0b429' },
  { id: 'crimson', name: 'Crimson', primary: '#e5484d', ink: '#ffffff', hover: '#f36a6e', secondary: '#f0b429' },
]

const KEY = 'ygo-theme'
const DEFAULT = 'amber'

function rgba(hex, a) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}

export function applyTheme(id) {
  if (typeof document === 'undefined') return
  const t = THEMES.find((x) => x.id === id) || THEMES[0]
  const r = document.documentElement.style
  r.setProperty('--accent', t.primary)
  r.setProperty('--accent-hover', t.hover)
  r.setProperty('--accent-ink', t.ink)
  r.setProperty('--warn', t.primary)
  r.setProperty('--warn-dim', rgba(t.primary, 0.12))
  r.setProperty('--focus', `0 0 0 2px ${rgba(t.primary, 0.4)}`)
  r.setProperty('--secondary', t.secondary)
}

function load() {
  try {
    return localStorage.getItem(KEY) || DEFAULT
  } catch {
    return DEFAULT
  }
}

export const themeId = writable(load())

themeId.subscribe((id) => {
  try {
    localStorage.setItem(KEY, id)
  } catch {
    /* ignore */
  }
  applyTheme(id)
})
