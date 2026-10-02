import { useEffect, useMemo, useState } from 'react'
import CodeEditor from './components/CodeEditor/CodeEditor'
import EmptyState from './components/EmptyState'
import ErrorState from './components/ErrorState'
import Header from './components/Header'
import Icon from './components/Icon'
import LoadingState from './components/LoadingState'
import Preview from './components/Preview'
import PreviewToolbar from './components/PreviewToolbar'
import ScreenshotUploader from './components/ScreenshotUploader'
import { useDebounce } from './hooks/useDebounce'
import { useGeneration } from './hooks/useGeneration'
import { getConfig } from './services/api'
import type { ActiveTab, BackendConfig, PreviewMode } from './types'
import { normalizeHtml } from './utils/html'

const MAX_INSTRUCTIONS = 1000

export default function App() {
  const [config, setConfig] = useState<BackendConfig | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [instructions, setInstructions] = useState('')
  const [generatedCode, setGeneratedCode] = useState('')
  const [tab, setTab] = useState<ActiveTab>('preview')
  const [mode, setMode] = useState<PreviewMode>('fit')
  const [copied, setCopied] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [previewLoaded, setPreviewLoaded] = useState(false)
  const gen = useGeneration()

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
    if (gen.result) setGeneratedCode(gen.result.html)
  }, [gen.result])

  const start = () => {
    if (!file || gen.generating) return
    setTab('preview')
    void gen.start(file, instructions)
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
      <Header model={config?.model ?? ''} online={!!config} />

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

      <main className="layout">
        <section className="panel input-panel" aria-label="Screenshot input">
          <div className="step">
            <p className="step-label"><span className="step-num" aria-hidden="true">1</span> Screenshot</p>
            <ScreenshotUploader
              config={config}
              file={file}
              onFile={(f, err) => { setFile(f); setFileError(err ?? null) }}
            />
            {fileError && <p className="field-error" role="alert">{fileError}</p>}
            {configError && <p className="field-error" role="alert">{configError}</p>}
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
              <button type="button" className="btn primary btn-block" disabled={!file || gen.generating} onClick={start}>
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
          <PreviewToolbar tab={tab} setTab={setTab} mode={mode} setMode={setMode} />

          <div className="toolbar">
            <button type="button" className="btn" disabled={!generatedCode} onClick={copy}>
              <Icon name={copied ? 'check' : 'copy'} size={15} />
              {copied ? 'Copied!' : 'Copy'}
            </button>
            <button type="button" className="btn" disabled={!generatedCode} onClick={download}>
              <Icon name="download" size={15} />
              Download
            </button>
            <button type="button" className="btn" disabled={!file || gen.generating} onClick={start}>
              <Icon name="refresh" size={15} />
              Regenerate
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

          {gen.result?.warnings?.length ? (
            <div className="warnings" role="note">
              {gen.result.warnings.map((w, i) => <p key={i}>{w}</p>)}
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
                ? <CodeEditor value={generatedCode} onChange={setGeneratedCode} />
                : <EmptyState hint="Generate first — the HTML source will appear here for editing." />}
            </div>
          )}

          {gen.result && (
            <div className="result-meta">
              <span className="meta-chip" title="Model used">
                <Icon name="spark" size={13} /> {gen.result.model}
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
