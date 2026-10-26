import { useCallback, useRef, useState } from 'react'
import { refineUI } from '../services/api'
import type { RefineEvent, RefineResult, StatusEvent } from '../types'
import { ERROR_MESSAGES } from './useGeneration'

const STATUS_LABELS: Record<StatusEvent['stage'], string> = {
  preparing: 'Preparing the screenshot…',
  calling_model: 'Calling the model…',
  generating: 'Generating…',
  postprocessing: 'Post-processing…',
  rendering: 'Rendering current HTML…',
  scoring: 'Comparing render with target…',
  refining: 'Asking the model to fix differences…',
}

function pct(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function useRefine() {
  const [refining, setRefining] = useState(false)
  const [stage, setStage] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<RefineResult | null>(null)
  const [live, setLive] = useState<RefineEvent | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const aborter = useRef<AbortController | null>(null)
  const timer = useRef<number | null>(null)
  const startRef = useRef(0)

  const start = useCallback(async (file: File, html: string, instructions: string) => {
    aborter.current?.abort()
    const ac = new AbortController()
    aborter.current = ac
    setRefining(true)
    setStage('Preparing refinement…')
    setError(null)
    setResult(null)
    setLive(null)
    setElapsed(0)
    startRef.current = performance.now()
    if (timer.current) window.clearInterval(timer.current)
    timer.current = window.setInterval(() => setElapsed((performance.now() - startRef.current) / 1000), 250)

    try {
      const r = await refineUI(file, html, instructions, {
        signal: ac.signal,
        onStatus: (s) => {
          if (aborter.current === ac) setStage(STATUS_LABELS[s.stage] ?? s.stage)
        },
        onRefine: (event) => {
          if (aborter.current === ac) setLive(event)
        },
      })
      if (aborter.current !== ac) return null
      setResult(r)
      setElapsed(r.elapsed_ms / 1000)
      const final = pct(r.similarity.final)
      if (r.similarity.kept) {
        setStage(`Visual similarity improved to ${final}.`)
      } else if (r.similarity.final >= r.similarity.target) {
        setStage(`Visual similarity is already ${final} (target ${pct(r.similarity.target)}).`)
      } else {
        setStage(`No improvement; the previous HTML was kept at ${final}.`)
      }
      return r
    } catch (e) {
      if (aborter.current !== ac) return null
      if ((e as Error).name === 'AbortError' || ac.signal.aborted) {
        setStage('Refinement cancelled.')
        return null
      }
      const code = (e as { code?: string }).code ?? 'INTERNAL'
      setError(ERROR_MESSAGES[code] ?? (e as Error).message)
      setStage('Refinement failed; the current HTML was kept.')
      return null
    } finally {
      if (aborter.current === ac) {
        setRefining(false)
        if (timer.current) {
          window.clearInterval(timer.current)
          timer.current = null
        }
      }
    }
  }, [])

  const cancel = useCallback(() => {
    aborter.current?.abort()
    setRefining(false)
    setStage('Refinement cancelled.')
  }, [])

  const reset = useCallback(() => {
    aborter.current?.abort()
    aborter.current = null
    if (timer.current) {
      window.clearInterval(timer.current)
      timer.current = null
    }
    setRefining(false)
    setStage('')
    setError(null)
    setResult(null)
    setLive(null)
    setElapsed(0)
  }, [])

  return { refining, stage, error, result, live, elapsed, start, cancel, reset }
}
