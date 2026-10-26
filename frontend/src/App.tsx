import { useEffect, useMemo, useRef, useState } from 'react'
import CodeEditor from './components/CodeEditor/CodeEditor'
import CompareView from './components/CompareView'
import EmptyState from './components/EmptyState'
import ErrorState from './components/ErrorState'
import Icon from './components/Icon'
import LandingPage from './components/LandingPage'
import LoadingState from './components/LoadingState'
import Preview from './components/Preview'
import PreviewToolbar from './components/PreviewToolbar'
import ScreenshotUploader from './components/ScreenshotUploader'
import { useDebounce } from './hooks/useDebounce'
import { useGeneration } from './hooks/useGeneration'
import { useRefine } from './hooks/useRefine'
import { getConfig } from './services/api'
import type { ActiveTab, BackendConfig, PreviewMode } from './types'
import { normalizeHtml } from './utils/html'

const MAX_INSTRUCTIONS = 1000
const pct = (value: number) => `${Math.round(value * 100)}%`

function StudioPage({ onHome }: { onHome: () => void }) {
  const [config, setConfig] = useState<BackendConfig | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [instructions, setInstructions] = useState('')
  const [generatedCode, setGeneratedCode] = useState('')
  const [generatedFrom, setGeneratedFrom] = useState<File | null>(null)
  const [tab, setTab] = useState<ActiveTab>('preview')
  const [mode, setMode] = useState<PreviewMode>('fit')
  const [copied, setCopied] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [previewLoaded, setPreviewLoaded] = useState(false)
  const pendingFile = useRef<File | null>(null)
  const gen = useGeneration()
  const refine = useRefine()

  useEffect(() => {
    getConfig().then(setConfig).catch((e: Error) => setConfigError(`Could not reach the server (${e.message}). Is it running?`))
  }, [])

  // generatedCode -> debounce(250ms) -> normalizeHtml -> iframe srcDoc. Single pipeline.
  const debounced = useDebounce(generatedCode, 250)
  const previewDocument = useMemo(() => normalizeHtml(debounced), [debounced])

  useEffect(() => {
    setPreviewLoaded(false)
  }, [previewDocument])

  const reloadPreview = () => {
    setPreviewLoaded(false)
    setReloadKey((k) => k + 1)
  }
  const htmlKb = useMemo(() => (new TextEncoder().encode(previewDocument).length / 1024).toFixed(1), [previewDocument])

  useEffect(() => {
    if (gen.result) {
      setGeneratedCode(gen.result.html)
      setGeneratedFrom(pendingFile.current)
    }
  }, [gen.result])

  const canCompare = !!file && file === generatedFrom && !!previewDocument
  const canRefine = !!config?.refine_enabled && !!file && file === generatedFrom && !!generatedCode && !gen.generating && !refine.refining

  useEffect(() => {
    if (!canCompare && tab === 'compare') setTab('preview')
  }, [canCompare, tab])

  const start = () => {
    if (!file || gen.generating || refine.refining) return
    pendingFile.current = file
    setGeneratedFrom(null)
    setTab('preview')
    refine.reset()
    void gen.start(file, instructions)
  }

  const startRefine = async () => {
    if (!file || !generatedCode || !canRefine) return
    const r = await refine.start(file, generatedCode, instructions)
    if (r) {
      setGeneratedCode(r.html)
      setGeneratedFrom(file)
      setTab('compare')
    }
  }

  const onCodeChange = (value: string) => {
    setGeneratedCode(value)
    refine.reset()
  }

  const copy = async () => {
    if (!generatedCode) return
    try {
      await navigator.clipboard.writeText(generatedCode)
    } catch {
      const area = document.createElement('textarea')
      area.value = generatedCode
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      area.remove()
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const download = () => {
    if (!generatedCode) return
    const blob = new Blob([generatedCode], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')
    const a = document.createElement('a')
    a.href = url
    a.download = `visioncraft-${stamp}.html`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <>
      <a className="skip-link" href="#output">Skip to generated output</a>
      {config?.requires_access_key && (
        <div className="access-banner">
          <Icon name="alert" size={16} />
          <label htmlFor="access-key">This server requires an access key:</label>
          <input
            type="password"
            id="access-key"
            placeholder="Paste access key"
            autoComplete="off"
            onChange={(e) => sessionStorage.setItem('vc-access-key', e.target.value.trim())}
          />
        </div>
      )}

      <section className="workspace-intro" aria-labelledby="workspace-title">
        <div className="intro-copy">
          <button className="studio-home" type="button" onClick={onHome}><Icon name="arrow" size={14} /> Home</button>
          <p className="eyebrow"><span className="eyebrow-mark" /> Screenshot to interface</p>
          <h2 id="workspace-title">Bring your designs to life.</h2>
          <p>Turn a visual reference into clean, responsive HTML you can preview and refine.</p>
        </div>
        <div className={`provider-status${gen.generating ? ' is-active' : ''}${gen.error ? ' is-error' : ''}`} aria-live="polite" title={gen.activeModel ?? config?.model ?? 'Provider status'}>
          <span className="provider-indicator" />
          <span className="provider-status-copy">
            <b>{gen.error ? 'Generation failed' : gen.activeProvider ? (gen.generating ? `Using ${gen.activeProvider}` : gen.result ? `Generated with ${gen.result.provider ?? gen.activeProvider}` : gen.activeProvider) : configError ? 'Server unavailable' : config ? 'Ready · automatic fallback' : 'Connecting to server'}</b>
            <small>{gen.activeModel ? `${gen.error ? 'Last tried · ' : ''}${gen.activeModel}` : (config?.model || 'Checking connection')}</small>
          </span>
          {gen.activeProvider && !gen.error && <span className="provider-pill">{gen.generating ? 'LIVE' : 'ACTIVE'}</span>}
        </div>
      </section>

      <main className="layout">
        <section className="panel input-panel" aria-label="Screenshot input">
          <div className="step">
            <p className="step-label"><span className="step-num" aria-hidden="true">1</span> Screenshot</p>
            <ScreenshotUploader
              config={config}
              file={file}
              onFile={(f, err) => {
                setFile(f)
                setFileError(err ?? null)
                setGeneratedFrom(null)
                refine.reset()
              }}
            />
            {fileError && <p className="field-error" role="alert">{fileError}</p>}
            {configError && (
              <div className="connection-error" role="alert">
                <span className="connection-error-icon"><Icon name="alert" size={15} /></span>
                <span><b>Can’t reach the VisionCraft server</b><small>Check that the backend is running, then retry.</small></span>
                <button type="button" onClick={() => {
                  setConfigError(null)
                  getConfig().then(setConfig).catch((e: Error) => setConfigError(`Could not reach the server (${e.message}). Is it running?`))
                }}>Retry</button>
              </div>
            )}
          </div>

          <div className="step">
            <p className="step-label"><span className="step-num" aria-hidden="true">2</span> Instructions <span className="opt">optional</span></p>
            <textarea
              id="instructions"
              rows={3}
              maxLength={MAX_INSTRUCTIONS}
              placeholder="e.g. make it dark mode, keep only the hero section"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              aria-describedby="instructions-count"
            />
            <p className="char-count" id="instructions-count">{instructions.length}/{MAX_INSTRUCTIONS}</p>
          </div>

          <div className="step">
            <p className="step-label"><span className="step-num" aria-hidden="true">3</span> Generate</p>
            <div className="actions">
              <button type="button" className="btn primary btn-block" disabled={!file || gen.generating || refine.refining} onClick={start}>
                <Icon name="spark" size={16} />
                {gen.generating ? 'Generating…' : 'Generate'}
              </button>
              {gen.generating && (
                <button type="button" className="btn btn-block" onClick={gen.cancel}>Cancel</button>
              )}
            </div>
            <div className="status" aria-live="polite">{gen.stage}</div>
            {gen.generating && (
              <div className="progress">
                <span>{gen.elapsed.toFixed(1)} s</span><span className="dot">·</span>
                <span>≈ {gen.tokens.toLocaleString()} tokens</span>
                <div className="progress-bar" role="progressbar" aria-label="Generating UI">
                  <span />
                </div>
              </div>
            )}
          </div>
        </section>

        <section id="output" className="panel output-panel" aria-label="Generated output" aria-busy={gen.generating}>
          <PreviewToolbar tab={tab} setTab={setTab} mode={mode} setMode={setMode} canCompare={canCompare} />

          <div className="toolbar">
            <button type="button" className="btn" disabled={!generatedCode} onClick={copy}>
              <Icon name={copied ? 'check' : 'copy'} size={15} />
              {copied ? 'Copied!' : 'Copy'}
            </button>
            <button type="button" className="btn" disabled={!generatedCode} onClick={download}>
              <Icon name="download" size={15} />
              Download
            </button>
            <button type="button" className="btn" disabled={!file || gen.generating || refine.refining} onClick={start}>
              <Icon name="refresh" size={15} />
              Regenerate
            </button>
            <button
              type="button"
              className="btn refine-btn"
              disabled={!canRefine}
              onClick={() => void startRefine()}
              title={!config?.refine_enabled
                ? 'Visual refinement is disabled on this server'
                : !canCompare
                  ? 'Generate output for the current screenshot first'
                  : 'Render this HTML, compare it with the screenshot, and run one correction pass'}
            >
              <Icon name="spark" size={15} />
              {refine.refining ? 'Refining…' : refine.result ? 'Refine again' : 'Refine match'}
            </button>
            <button
              type="button"
              className="btn"
              disabled={!previewDocument}
              onClick={reloadPreview}
              title="Force the preview frame to reload (use if the preview looks blank or stale)"
            >
              <Icon name="refresh" size={15} />
              Reload preview
            </button>
          </div>

          {refine.refining && (
            <div className="refine-progress" aria-live="polite">
              <span className="refine-spinner" aria-hidden="true" />
              <span className="refine-progress-label">{refine.stage}</span>
              <span className="refine-progress-meta">{refine.elapsed.toFixed(1)} s</span>
              {refine.live && <span className="refine-progress-meta">SSIM {pct(refine.live.final)}</span>}
              <button type="button" className="link-btn" onClick={refine.cancel}>Cancel</button>
            </div>
          )}

          {refine.result && !refine.refining && (
            <div className={`refine-summary${refine.result.similarity.final >= refine.result.similarity.target ? ' is-target' : ''}`} role="status">
              <span className="score-chip" title="Structural similarity between the screenshot and the rendered HTML">
                SSIM {pct(refine.result.similarity.final)}
              </span>
              <span className="refine-summary-text">
                {refine.result.similarity.kept
                  ? refine.result.similarity.improvement < 0.01
                    ? 'Improved slightly; the new HTML was kept.'
                    : `Improved ${Math.round(refine.result.similarity.improvement * 100)} points.`
                  : refine.result.similarity.final >= refine.result.similarity.target
                    ? 'Target already met; no model call was made.'
                    : 'The correction did not beat the current render; the previous HTML was kept.'}
              </span>
              <span className="refine-target">target {pct(refine.result.similarity.target)}</span>
              <span className="refine-target">{(refine.result.elapsed_ms / 1000).toFixed(1)} s</span>
            </div>
          )}

          {refine.error && <ErrorState message={refine.error} onRetry={canRefine ? () => void startRefine() : undefined} />}

          {(refine.result ? refine.result.warnings : gen.result?.warnings)?.length ? (
            <div className="warnings" role="note">
              {(refine.result ? refine.result.warnings : gen.result?.warnings ?? []).map((w, i) => <p key={i}>{w}</p>)}
            </div>
          ) : null}

          {tab === 'preview' && (
            <div
              className="preview-wrap"
              data-device={mode}
              role="tabpanel"
              id="panel-preview"
              aria-labelledby="tab-preview"
            >
              {gen.generating && !previewDocument
                ? <LoadingState stage={gen.stage} />
                : (
                  <>
                    <Preview
                      document={previewDocument}
                      mode={mode}
                      reloadKey={reloadKey}
                      onLoad={() => setPreviewLoaded(true)}
                    />
                    {!!previewDocument && !previewLoaded && (
                      <span className="sr-only" role="status">Loading preview…</span>
                    )}
                  </>
                )}
            </div>
          )}

          {tab === 'code' && (
            <div role="tabpanel" id="panel-code" aria-labelledby="tab-code">
              {generatedCode
                ? <CodeEditor value={generatedCode} onChange={onCodeChange} />
                : <EmptyState hint="Generate first — the HTML source will appear here for editing." />}
            </div>
          )}

          {tab === 'compare' && canCompare && (
            <CompareView
              file={file}
              document={previewDocument}
              mode={mode}
              reloadKey={reloadKey}
              onLoad={() => setPreviewLoaded(true)}
              similarity={refine.result?.similarity ?? null}
            />
          )}

          {gen.result && (
            <div className="result-meta">
              <span className="meta-chip" title="Provider and model used">
                <Icon name="spark" size={13} /> {gen.result.provider ? `${gen.result.provider} · ` : ''}{gen.result.model}
              </span>
              <span className="meta-chip" title="Generation time">
                <Icon name="clock" size={13} /> {(gen.result.elapsed_ms / 1000).toFixed(1)} s
              </span>
              <span className="meta-chip" title="Preview document size">
                <Icon name="code" size={13} /> {htmlKb} KB
              </span>
              {gen.result.truncated && <span className="meta-chip warn">truncated</span>}
            </div>
          )}

          {gen.error && <ErrorState message={gen.error} onRetry={file ? start : undefined} />}
        </section>
      </main>

      <footer className="app-footer">
        <p>First-draft output — expect approximated spacing, system fonts, and placeholder graphics. Always review generated code before using it.</p>
      </footer>
    </>
  )
}

export default function App() {
  const [studio, setStudio] = useState(() => window.location.pathname.replace(/\/+$/, '') === '/studio')
  useEffect(() => {
    const syncRoute = () => setStudio(window.location.pathname.replace(/\/+$/, '') === '/studio')
    window.addEventListener('popstate', syncRoute)
    return () => window.removeEventListener('popstate', syncRoute)
  }, [])
  const navigate = (path: string) => {
    window.history.pushState({}, '', path)
    setStudio(path === '/studio')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  return studio
    ? <StudioPage onHome={() => navigate('/')} />
    : <LandingPage onOpen={() => navigate('/studio')} />
}
