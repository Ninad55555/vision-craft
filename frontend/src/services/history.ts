import type { GenerationResult, HistoryEntry } from '../types'

export const HISTORY_STORAGE_KEY = 'visioncraft:history:v1'
export const HISTORY_MAX_ENTRIES = 5
export const HISTORY_BUDGET_BYTES = 1_800_000

function makeId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function byteLength(value: string): number {
  return new TextEncoder().encode(value).length
}

function isHistoryEntry(value: unknown): value is HistoryEntry {
  if (!value || typeof value !== 'object') return false
  const entry = value as Partial<HistoryEntry>
  const result = entry.result as Partial<GenerationResult> | undefined
  return (
    typeof entry.id === 'string' &&
    typeof entry.createdAt === 'number' &&
    typeof entry.filename === 'string' &&
    typeof entry.instructions === 'string' &&
    !!result &&
    typeof result.html === 'string' &&
    typeof result.model === 'string' &&
    typeof result.elapsed_ms === 'number' &&
    Array.isArray(result.warnings)
  )
}

function trim(entries: HistoryEntry[]): HistoryEntry[] {
  const next = entries.slice(0, HISTORY_MAX_ENTRIES)
  while (next.length > 0 && byteLength(JSON.stringify(next)) > HISTORY_BUDGET_BYTES) {
    next.pop()
  }
  return next
}

export function readHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isHistoryEntry).slice(0, HISTORY_MAX_ENTRIES)
  } catch {
    return []
  }
}

export function writeHistory(entries: HistoryEntry[]): HistoryEntry[] {
  let next = trim(entries)
  if (next.length === 0) {
    try {
      localStorage.removeItem(HISTORY_STORAGE_KEY)
    } catch {
      /* storage unavailable */
    }
    return []
  }
  while (next.length > 0) {
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next))
      return next
    } catch {
      next = next.slice(0, -1)
    }
  }
  try {
    localStorage.removeItem(HISTORY_STORAGE_KEY)
  } catch {
    /* storage unavailable */
  }
  return []
}

export function createHistoryEntry(
  filename: string,
  instructions: string,
  result: GenerationResult,
): HistoryEntry {
  return {
    id: makeId(),
    createdAt: Date.now(),
    filename: filename || 'screenshot',
    instructions,
    result,
  }
}

export function addHistoryEntry(entries: HistoryEntry[], entry: HistoryEntry): HistoryEntry[] {
  return [entry, ...entries.filter((item) => item.id !== entry.id)]
}

export function describeDraftAge(timestamp: number, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - timestamp) / 1000))
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days} d ago`
  return new Date(timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
