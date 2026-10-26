import { useEffect, useState } from 'react'
import type { PreviewMode, SimilarityInfo } from '../types'
import Preview from './Preview'

interface Props {
  file: File | null
  document: string
  mode: PreviewMode
  reloadKey: number
  onLoad: () => void
  similarity?: SimilarityInfo | null
}

const pct = (value: number) => `${Math.round(value * 100)}%`

export default function CompareView({ file, document, mode, reloadKey, onLoad, similarity }: Props) {
  const [imageUrl, setImageUrl] = useState('')
  const [opacity, setOpacity] = useState(50)

  useEffect(() => {
    if (!file) { setImageUrl(''); return }
    const url = URL.createObjectURL(file)
    setImageUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  return (
    <div className="compare-overlay" role="tabpanel" id="panel-compare" aria-labelledby="tab-compare">
      <header className="compare-overlay-bar">
        <div className="compare-overlay-title">
          <span className="compare-index">A</span>
          <span><b>Original</b><small>{file?.name ?? 'Source screenshot'}</small></span>
          <span className="compare-swap">↔</span>
          <span className="compare-index generated-index">B</span>
          <span><b>Generated</b><small>Live HTML overlay</small></span>
        </div>

        {similarity && (
          <div className={`compare-score${similarity.final >= similarity.target ? ' is-target' : ''}`} title="Structural similarity between the screenshot and the rendered HTML">
            <span>SSIM <b>{pct(similarity.final)}</b></span>
            <small>target {pct(similarity.target)}</small>
            {similarity.kept
              ? <span className={`compare-delta${similarity.meaningful ? ' is-meaningful' : ''}`}>{similarity.improvement < 0.01 ? 'small gain' : `+${Math.round(similarity.improvement * 100)} pts`}</span>
              : <span className="compare-delta is-neutral">kept original</span>}
          </div>
        )}

        <label className="compare-slider">
          <span>Generated opacity</span>
          <input
            type="range"
            min={0}
            max={100}
            value={opacity}
            onChange={(e) => setOpacity(Number(e.target.value))}
            aria-label="Generated preview opacity"
          />
          <output>{opacity}%</output>
        </label>
      </header>

      <div className="compare-stage">
        <div className="compare-layer source-layer" aria-label="Original screenshot">
          {imageUrl
            ? <img src={imageUrl} alt="Original uploaded screenshot" />
            : <p>Upload a screenshot to compare it with the generated page.</p>}
        </div>
        <div className="compare-layer generated-layer" style={{ opacity: opacity / 100 }} aria-label="Generated interface">
          <Preview document={document} mode={mode} reloadKey={reloadKey} onLoad={onLoad} />
        </div>
        <span className="compare-axis-label compare-axis-a">A</span>
        <span className="compare-axis-label compare-axis-b">B</span>
      </div>
    </div>
  )
}
