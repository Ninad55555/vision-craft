import { useEffect, useState } from 'react'
import type { PreviewMode } from '../types'
import Preview from './Preview'

interface Props {
  file: File | null
  document: string
  mode: PreviewMode
  reloadKey: number
  onLoad: () => void
}

export default function CompareView({ file, document, mode, reloadKey, onLoad }: Props) {
  const [imageUrl, setImageUrl] = useState('')

  useEffect(() => {
    if (!file) { setImageUrl(''); return }
    const url = URL.createObjectURL(file)
    setImageUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  return (
    <div className="compare-grid" role="tabpanel" id="panel-compare" aria-labelledby="tab-compare">
      <section className="compare-pane" aria-label="Original screenshot">
        <header className="compare-pane-heading">
          <span className="compare-index">A</span>
          <span><b>Original</b><small>{file?.name ?? 'Source screenshot'}</small></span>
          {file && <span className="compare-dimensions">{(file.size / 1024).toFixed(0)} KB</span>}
        </header>
        <div className="compare-canvas source-canvas">
          {imageUrl
            ? <img src={imageUrl} alt="Original uploaded screenshot" />
            : <p>Upload a screenshot to compare it with the generated page.</p>}
        </div>
      </section>

      <section className="compare-pane" aria-label="Generated interface">
        <header className="compare-pane-heading">
          <span className="compare-index generated-index">B</span>
          <span><b>Generated</b><small>Live HTML preview</small></span>
          <span className="compare-live"><i /> LIVE</span>
        </header>
        <div className="compare-canvas generated-canvas">
          <Preview document={document} mode={mode} reloadKey={reloadKey} onLoad={onLoad} />
        </div>
      </section>
    </div>
  )
}
