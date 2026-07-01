// Preset UI themes. Each recolours the app's primary accent (buttons, highlights,
// LP, the phase capsule, the DP chip…) plus a secondary accent, and is remembered
// in the browser. Presets only — no custom pickers.
import { writable } from 'svelte/store'

// Each theme is a cohesive pair — a darker primary + a lighter secondary of the
// SAME hue (dark/light amber, dark/light blue, …).
export const THEMES = [
  { id: 'amber', name: 'Amber', primary: '#f0b429', ink: '#1a1400', hover: '#ffc340', secondary: '#ffd876' },
  { id: 'blue', name: 'Blue', primary: '#3d6fd8', ink: '#ffffff', hover: '#5a86e8', secondary: '#8fb6ff' },
  { id: 'emerald', name: 'Emerald', primary: '#12a877', ink: '#ffffff', hover: '#1ac489', secondary: '#5fe0ab' },
  { id: 'crimson', name: 'Crimson', primary: '#d83a4a', ink: '#ffffff', hover: '#e85662', secondary: '#ff828c' },
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
