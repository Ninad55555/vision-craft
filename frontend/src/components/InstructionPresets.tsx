import { INSTRUCTION_PRESETS, isPresetActive, togglePreset } from '../utils/instructions'
import Icon from './Icon'

interface Props {
  value: string
  maxLength: number
  onChange: (next: string) => void
}

export default function InstructionPresets({ value, maxLength, onChange }: Props) {
  return (
    <div className="preset-block">
      <div className="preset-heading">
        <span>Quick additions</span>
        <small>Tap to add or remove</small>
      </div>
      <div className="preset-list" role="group" aria-label="Instruction presets">
        {INSTRUCTION_PRESETS.map((preset) => {
          const active = isPresetActive(value, preset.text)
          const wouldOverflow = !active && value.trim().length + 1 + preset.text.length > maxLength
          return (
            <button
              key={preset.id}
              type="button"
              className={`preset-chip${active ? ' is-active' : ''}`}
              aria-pressed={active}
              disabled={wouldOverflow}
              title={wouldOverflow ? 'Not enough instruction space left' : preset.description}
              onClick={() => onChange(togglePreset(value, preset.text))}
            >
              {active && <Icon name="check" size={12} />}
              {preset.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
