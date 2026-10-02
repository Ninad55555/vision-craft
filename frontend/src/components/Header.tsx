import Icon from './Icon'

export default function Header({ model, online }: { model: string; online: boolean }) {
  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <Icon name="spark" size={20} />
        </span>
        <div>
          <h1>VisionCraft</h1>
          <p className="tagline">Screenshot in, single self-contained <code>.html</code> out.</p>
        </div>
      </div>
      <div className="model-badge" title="Model configured on the server">
        <span className={`status-dot${online ? ' on' : ''}`} aria-hidden="true" />
        <span className="model-name">{model || 'Connecting…'}</span>
      </div>
    </header>
  )
}
