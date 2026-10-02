export type GenerationStatus = 'idle' | 'loading' | 'success' | 'error'
export type PreviewMode = 'fit' | 'tablet' | 'mobile'
export type ActiveTab = 'preview' | 'code' | 'compare'

export interface BackendConfig {
  max_upload_mb: number
  image_max_side: number
  accepted_types: string[]
  requires_access_key: boolean
  model: string
}

export interface GenerationResult {
  html: string
  model: string
  truncated: boolean
  warnings: string[]
  elapsed_ms: number
  usage?: { prompt_tokens?: number; completion_tokens?: number } | null
}

export interface ApiErrorShape {
  code: string
  message: string
  retryable: boolean
}

export interface StatusEvent {
  stage: 'preparing' | 'calling_model' | 'generating' | 'postprocessing'
  note?: string | null
  model?: string | null
}
