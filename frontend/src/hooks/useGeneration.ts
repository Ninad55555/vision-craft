import { useCallback, useRef, useState } from 'react'
import { generateUI } from '../services/api'
import type { GenerationResult, GenerationStatus } from '../types'

export const ERROR_MESSAGES: Record<string, string> = {
  ACCESS_DENIED: 'This server requires an access key. Enter it above and try again.',
  AUTH_MISSING: 'No inference provider is configured. Add a provider key to the server environment and restart it.',
  AUTH_FAILED: 'The configured inference provider rejected its credentials.',
  CREDITS_EXHAUSTED: 'Inference credits are exhausted for the configured providers.',
  RATE_LIMITED: 'Too many requests. Wait a moment and retry.',
  IMAGE_INVALID: 'That file is not a valid PNG, JPEG, or WebP image.',
  IMAGE_TOO_LARGE: 'That image exceeds the server size limit.',
  MODEL_UNAVAILABLE: 'The configured model is not available right now.',
  UPSTREAM_TIMEOUT: 'The model took too long. Try a smaller screenshot.',
  UPSTREAM_ERROR: 'The model provider returned an error. Retry later.',
  OUTPUT_NOT_HTML: 'The model did not return an HTML document. Retry.',
  REFINE_DISABLED: 'Visual refinement is disabled on this server.',
  REFINE_UNAVAILABLE: 'Visual refinement is unavailable. Install Playwright and scikit-image on the server.',
  REFINE_FAILED: 'Refinement failed. The current HTML was kept.',
  INVALID_HTML: 'The current HTML is empty or invalid, so it cannot be refined.',
  INTERNAL: 'Unexpected server error. Check server logs.',
}

export function useGeneration() {
  const [status, setStatus] = useState<GenerationStatus>('idle')
  const [stage, setStage] = useState('Pick a screenshot to begin.')
  const [activeProvider, setActiveProvider] = useState<string | null>(null)
  const [activeModel, setActiveModel] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<GenerationResult | null>(null)
  const [tokens, setTokens] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const aborter = useRef<AbortController | null>(null)
  const timer = useRef<number | null>(null)
  const startRef = useRef(0)
  const chars = useRef(0)

  const start = useCallback(async (file: File, instructions: string) => {
    aborter.current?.abort()
    const ac = new AbortController()
    aborter.current = ac
    chars.current = 0
    setTokens(0)
    setError(null)
    setResult(null)
    setActiveProvider(null)
    setActiveModel(null)
    setStatus('loading')
    setStage('Preparing image…')
    startRef.current = performance.now()
    timer.current = window.setInterval(() => setElapsed((performance.now() - startRef.current) / 1000), 250)

    try {
      const r = await generateUI(file, instructions, {
        signal: ac.signal,
        onStatus: (s) => {
          if (s.provider) setActiveProvider(s.provider)
          if (s.model) setActiveModel(s.model)
          const labels: Record<string, string> = {
            preparing: 'Preparing image…',
            calling_model: s.note ? `Calling model… (${s.note})` : 'Calling model…',
            generating: 'Generating…',
            postprocessing: 'Post-processing…',
          }
          setStage(labels[s.stage] ?? s.stage)
        },
        onDelta: (n) => {
          chars.current += n
          setTokens(Math.round(chars.current / 4))
        },
      })
      setResult(r)
      setStatus('success')
      setStage('Done. Review the preview, then copy or download.')
    } catch (e) {
      if ((e as Error).name === 'AbortError' || ac.signal.aborted) {
        setStatus('idle')
        setStage('Cancelled. Adjust the instructions and regenerate when ready.')
        return
      }
      const code = (e as { code?: string }).code ?? 'INTERNAL'
      setError(ERROR_MESSAGES[code] ?? (e as Error).message)
      setStatus('error')
      setStage('Generation failed — see the error below.')
    } finally {
      if (timer.current) window.clearInterval(timer.current)
    }
  }, [])

  const cancel = useCallback(() => aborter.current?.abort(), [])

  const adopt = useCallback((next: GenerationResult, label = 'Restored a recent draft from this browser.') => {
    setTokens(0)
    setError(null)
    setResult(next)
    setActiveProvider(next.provider ?? null)
    setActiveModel(next.model)
    setElapsed(next.elapsed_ms / 1000)
    setStatus('success')
    setStage(label)
  }, [])

  return {
    status,
    stage,
    error,
    result,
    tokens,
    elapsed,
    activeProvider,
    activeModel,
    start,
    cancel,
    adopt,
    generating: status === 'loading',
  }
}
