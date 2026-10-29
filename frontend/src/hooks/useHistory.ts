import { useCallback, useState } from 'react'
import {
  addHistoryEntry,
  createHistoryEntry,
  readHistory,
  writeHistory,
} from '../services/history'
import type { GenerationResult, HistoryEntry } from '../types'

export function useHistory() {
  const [entries, setEntries] = useState<HistoryEntry[]>(() => readHistory())

  const add = useCallback((filename: string, instructions: string, result: GenerationResult) => {
    setEntries((current) => writeHistory(addHistoryEntry(current, createHistoryEntry(filename, instructions, result))))
  }, [])

  const remove = useCallback((id: string) => {
    setEntries((current) => writeHistory(current.filter((entry) => entry.id !== id)))
  }, [])

  const clear = useCallback(() => {
    setEntries(() => writeHistory([]))
  }, [])

  return { entries, add, remove, clear }
}
