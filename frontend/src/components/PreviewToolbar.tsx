import { useRef } from 'react'
import type { ActiveTab, PreviewMode } from '../types'
import Icon from './Icon'

interface Props {
  tab: ActiveTab
  setTab: (t: ActiveTab) => void
  mode: PreviewMode
  setMode: (m: PreviewMode) => void
  canCompare: boolean
}

const TABS: { id: ActiveTab; label: string; icon: 'eye' | 'code' | 'compare' }[] = [
  { id: 'preview', label: 'Preview', icon: 'eye' },
  { id: 'compare', label: 'Compare', icon: 'compare' },
  { id: 'code', label: 'Code', icon: 'code' },
]

export default function PreviewToolbar({ tab, setTab, mode, setMode, canCompare }: Props) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  const onTabKey = (e: React.KeyboardEvent, i: number) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const step = e.key === 'ArrowRight' ? 1 : -1
    let next = (i + step + TABS.length) % TABS.length
    while (TABS[next].id === 'compare' && !canCompare) next = (next + step + TABS.length) % TABS.length
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
            aria-disabled={t.id === 'compare' && !canCompare}
            tabIndex={tab === t.id ? 0 : -1}
            disabled={t.id === 'compare' && !canCompare}
            title={t.id === 'compare' && !canCompare ? 'Generate output for the current screenshot to enable comparison' : undefined}
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onTabKey(e, i)}
          >
            <Icon name={t.icon} size={15} />
            {t.label}
          </button>
        ))}
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
