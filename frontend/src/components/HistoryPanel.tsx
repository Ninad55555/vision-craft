import { describeDraftAge, HISTORY_MAX_ENTRIES } from '../services/history'
import type { HistoryEntry } from '../types'
import Icon from './Icon'

interface Props {
  entries: HistoryEntry[]
  disabled: boolean
  onRestore: (entry: HistoryEntry) => void
  onRemove: (id: string) => void
  onClear: () => void
}

export default function HistoryPanel({ entries, disabled, onRestore, onRemove, onClear }: Props) {
  return (
    <div className="step history-block">
      <div className="history-heading">
        <p className="step-label">
          <Icon name="clock" size={14} /> Recent drafts
          <span className="opt">{entries.length}/{HISTORY_MAX_ENTRIES}</span>
        </p>
        {entries.length > 0 && (
          <button type="button" className="link-btn" onClick={onClear} disabled={disabled}>
            Clear all
          </button>
        )}
      </div>

      {entries.length === 0 ? (
        <p className="history-empty">Generated drafts are saved in this browser for quick reopening.</p>
      ) : (
        <ul className="history-list">
          {entries.map((entry) => (
            <li key={entry.id} className="history-item">
              <button
                type="button"
                className="history-restore"
                onClick={() => onRestore(entry)}
                disabled={disabled}
                title={`Restore ${entry.filename}`}
              >
                <span className="history-mark"><Icon name="code" size={14} /></span>
                <span className="history-copy">
                  <b>{entry.filename}</b>
                  <small>
                    {describeDraftAge(entry.createdAt)} · {entry.result.provider ? `${entry.result.provider} · ` : ''}
                    {entry.result.model}
                  </small>
                </span>
                <span className="history-open">Open</span>
              </button>
              <button
                type="button"
                className="icon-btn history-remove"
                onClick={() => onRemove(entry.id)}
                disabled={disabled}
                aria-label={`Remove ${entry.filename} from history`}
                title="Remove draft"
              >
                <Icon name="x" size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
