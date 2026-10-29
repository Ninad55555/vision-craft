export type GenerationStatus = 'idle' | 'loading' | 'success' | 'error'
export type PreviewMode = 'fit' | 'tablet' | 'mobile'
export type ActiveTab = 'preview' | 'code' | 'compare'

export interface BackendConfig {
  max_upload_mb: number
  image_max_side: number
  accepted_types: string[]
  requires_access_key: boolean
  model: string
  refine_enabled: boolean
}

export interface GenerationResult {
  html: string
  model: string
  provider?: string | null
  truncated: boolean
  warnings: string[]
  elapsed_ms: number
  palette?: string[]
  usage?: { prompt_tokens?: number; completion_tokens?: number } | null
}

export interface HistoryEntry {
  id: string
  createdAt: number
  filename: string
  instructions: string
  result: GenerationResult
}

export interface ApiErrorShape {
  code: string
  message: string
  retryable: boolean
}

export interface StatusEvent {
  stage: 'preparing' | 'calling_model' | 'generating' | 'postprocessing' | 'rendering' | 'scoring' | 'refining'
  note?: string | null
  model?: string | null
  provider?: string | null
}

export interface SimilarityInfo {
  initial: number
  candidate: number
  final: number
  kept: boolean
  improvement: number
  meaningful: boolean
  target: number
}

export interface RefineEvent {
  initial: number
  candidate: number
  final: number
  kept: boolean
  improvement: number
  meaningful: boolean
}

export interface RefineResult {
  html: string
  similarity: SimilarityInfo
  warnings: string[]
  model?: string | null
  provider?: string | null
  finish_reason?: string | null
  truncated: boolean
  usage?: { prompt_tokens?: number; completion_tokens?: number } | null
  elapsed_ms: number
}
