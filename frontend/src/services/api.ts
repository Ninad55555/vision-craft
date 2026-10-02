import type { BackendConfig, GenerationResult, StatusEvent } from '../types'

// Centralized backend base URL. Empty = same origin (FastAPI serves dist).
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined ?? '').replace(/\/$/, '')

const url = (p: string) => `${API_BASE}${p}`

export function accessHeaders(): Record<string, string> {
  const key = sessionStorage.getItem('vc-access-key')
  return key ? { 'X-Access-Key': key } : {}
}

export async function healthCheck(): Promise<{ ok: boolean; model?: string }> {
  const res = await fetch(url('/health'))
  if (!res.ok) return { ok: false }
  const data = await res.json()
  return { ok: data?.status === 'ok', model: data?.model }
}

export async function getConfig(): Promise<BackendConfig> {
  const res = await fetch(url('/api/config'))
  if (!res.ok) throw new Error(`config HTTP ${res.status}`)
  return res.json()
}

export interface GenerateCallbacks {
  signal: AbortSignal
  onStatus: (s: StatusEvent) => void
  onDelta: (chars: number) => void
}

function parseErrorCode(payload: unknown): string | null {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const d = (payload as { detail?: { code?: string } }).detail
    return d?.code ?? null
  }
  return null
}

/** POST /api/generate with stream=true (existing contract). Resolves with the `result` SSE payload. */
export async function generateUI(
  image: File,
  instructions: string,
  cb: GenerateCallbacks,
): Promise<GenerationResult> {
  const form = new FormData()
  form.append('image', image, image.name || 'screenshot.png')
  form.append('instructions', instructions)
  form.append('stream', 'true')

  const response = await fetch(url('/api/generate'), {
    method: 'POST',
    body: form,
    headers: accessHeaders(),
    signal: cb.signal,
  })

  if (!response.ok || !response.body) {
    let code: string | null = null
    try {
      code = parseErrorCode(await response.json())
    } catch {
      /* fall through */
    }
    throw Object.assign(new Error(code ?? `http-${response.status}`), { code })
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let name: string | null = null
      let data: string | null = null
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) name = line.slice(6).trim()
        else if (line.startsWith('data:')) data = (data === null ? '' : data) + line.slice(5).trim()
        else if (line.startsWith(':')) continue // ping
      }
      if (!name) continue
      const payload = data ? JSON.parse(data) : null
      if (name === 'status') cb.onStatus(payload as StatusEvent)
      else if (name === 'delta') cb.onDelta((payload?.text ?? '').length)
      else if (name === 'result') return payload as GenerationResult
      else if (name === 'error') throw Object.assign(new Error(payload?.code ?? 'UPSTREAM_ERROR'), { code: payload?.code })
    }
  }
  throw Object.assign(new Error('INTERNAL'), { code: 'INTERNAL' })
}
