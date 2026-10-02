import type { PreviewMode } from '../types'

interface Props {
  /** Normalized full HTML document. Passed verbatim to iframe srcDoc — no CSP injection, no re-parsing. */
  document: string
  mode: PreviewMode
  /** Bump to force a clean remount (Reload button). Never changes on typing. */
  reloadKey: number
  onLoad: () => void
}

// SOLE owner of iframe rendering. React owns the chrome; the browser owns the page.
// Single update mechanism: the srcDoc prop. (A previous version also wrote the
// .srcdoc property in an effect — two navigations per update raced and blanked
// the frame intermittently.)
export default function Preview({ document, mode, reloadKey, onLoad }: Props) {
  if (!document) {
    return (
      <div className="empty-state">
        <p className="empty-title">Preview is empty</p>
        <p className="empty-hint">Upload a screenshot and press Generate — the page renders here, sandboxed.</p>
      </div>
    )
  }

  return (
    <iframe
      key={reloadKey}
      id="preview"
      className={`preview-frame ${mode}`}
      title="Generated UI Preview"
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      srcDoc={document}
      onLoad={onLoad}
    />
  )
}
