export default function LoadingState({ stage }: { stage: string }) {
  return (
    <div className="loading-state" role="status">
      <div className="loading-art" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <p className="loading-text">{stage}</p>
    </div>
  )
}
