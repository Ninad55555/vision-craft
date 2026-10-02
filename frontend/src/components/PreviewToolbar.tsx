import { useRef } from 'react'
import type { ActiveTab, PreviewMode } from '../types'
import Icon from './Icon'

interface Props {
  tab: ActiveTab
  setTab: (t: ActiveTab) => void
  mode: PreviewMode
  setMode: (m: PreviewMode) => void
}

const TABS: { id: ActiveTab; label: string; icon: 'eye' | 'code' }[] = [
  { id: 'preview', label: 'Preview', icon: 'eye' },
  { id: 'code', label: 'Code', icon: 'code' },
]

export default function PreviewToolbar({ tab, setTab, mode, setMode }: Props) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  const onTabKey = (e: React.KeyboardEvent, i: number) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const next = (i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length
    tabRefs.current[next]?.focus()
    setTab(TABS[next].id)
  }

  return (
    <div className="tabbar">
      <div role="tablist" aria-label="Output views" className="tabs">
        {TABS.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => { tabRefs.current[i] = el }}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onTabKey(e, i)}
          >
            <Icon name={t.icon} size={15} />
            {t.label}
          </button>
        ))}
        <button type="button" role="tab" aria-selected={false} disabled title="Compare view is coming soon (P1)">
          Compare · soon
        </button>
      </div>
      <div className="device-toggle" role="group" aria-label="Preview width">
        {(['fit', 'tablet', 'mobile'] as PreviewMode[]).map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={mode === m}
            title={m === 'fit' ? 'Fit to panel' : m === 'tablet' ? 'Tablet · 768px' : 'Mobile · 390px'}
            onClick={() => setMode(m)}
          >
            {m === 'fit' ? 'Fit' : m === 'tablet' ? '768' : '390'}
          </button>
        ))}
      </div>
    </div>
  )
}
