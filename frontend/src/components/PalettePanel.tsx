import { useEffect, useMemo, useRef, useState } from 'react'
import { copyText } from '../utils/clipboard'
import { paletteToCssVariables, uniquePalette } from '../utils/palette'
import Icon from './Icon'

interface Props {
  colors: string[]
}

export default function PalettePanel({ colors }: Props) {
  const swatches = useMemo(() => uniquePalette(colors), [colors])
  const css = useMemo(() => paletteToCssVariables(swatches), [swatches])
  const [copied, setCopied] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current)
  }, [])

  if (swatches.length === 0) return null

  const copy = async (value: string) => {
    if (!(await copyText(value))) return
    setCopied(value)
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setCopied(null), 1600)
  }

  return (
    <section className="palette-panel" aria-labelledby="palette-title">
      <div className="palette-head">
        <div className="palette-text">
          <p className="palette-title" id="palette-title">Source palette</p>
          <p className="palette-hint">Sampled from your screenshot. Click a swatch to copy its hex.</p>
        </div>
        <button type="button" className="btn palette-copy-btn" onClick={() => void copy(css)}>
          <Icon name={copied === css ? 'check' : 'copy'} size={14} />
          {copied === css ? 'Copied CSS' : 'Copy CSS variables'}
        </button>
      </div>
      <ul className="palette-swatches">
        {swatches.map((color) => (
          <li key={color}>
            <button
              type="button"
              className="swatch"
              onClick={() => void copy(color)}
              title={`Copy ${color}`}
              aria-label={`Copy color ${color}`}
            >
              <span className="swatch-color" style={{ backgroundColor: color }} />
              <span className="swatch-hex">{copied === color ? 'Copied' : color}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
