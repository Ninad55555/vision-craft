import Icon from './Icon'

export default function EmptyState({ hint }: { hint: string }) {
  return (
    <div className="empty-state">
      <div className="empty-art" aria-hidden="true">
        <Icon name="image" size={40} />
      </div>
      <p className="empty-title">Nothing here yet</p>
      <p className="empty-hint">{hint}</p>
    </div>
  )
}
