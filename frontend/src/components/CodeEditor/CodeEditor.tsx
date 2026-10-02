import { Suspense, lazy, useState } from 'react'

// Lazy: Monaco chunk (+4 workers) loads only when the Code tab opens — never on initial screen.
const MonacoPane = lazy(() => import('./MonacoPane'))

interface Props {
  value: string
  onChange: (v: string) => void
}

export default function CodeEditor({ value, onChange }: Props) {
  const [useMonaco, setUseMonaco] = useState(true)
  const bytes = new TextEncoder().encode(value).length

  return (
    <div className="code-wrap">
      <div className="code-meta">
        {value.split('\n').length.toLocaleString()} lines · {(bytes / 1024).toFixed(1)} KB ·{' '}
        <button type="button" className="link-btn" onClick={() => setUseMonaco((v) => !v)}>
          {useMonaco ? 'Use plain editor' : 'Use Monaco'}
        </button>
      </div>
      {useMonaco ? (
        <Suspense fallback={<textarea className="code-fallback" value={value} onChange={(e) => onChange(e.target.value)} spellCheck={false} />}>
          <MonacoPane value={value} onChange={onChange} />
        </Suspense>
      ) : (
        <textarea className="code-fallback" value={value} onChange={(e) => onChange(e.target.value)} spellCheck={false} />
      )}
    </div>
  )
}
