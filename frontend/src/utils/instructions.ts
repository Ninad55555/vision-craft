export interface InstructionPreset {
  id: string
  label: string
  description: string
  text: string
}

export const INSTRUCTION_PRESETS: InstructionPreset[] = [
  {
    id: 'dark',
    label: 'Dark mode',
    description: 'Deep neutral surfaces with accessible contrast',
    text: 'Use a dark color scheme with deep neutral surfaces and accessible contrast.',
  },
  {
    id: 'mobile',
    label: 'Mobile-first',
    description: 'Single column and generous touch targets on small screens',
    text: 'Lay out the page mobile-first with a single column below 640px and generous touch targets.',
  },
  {
    id: 'minimal',
    label: 'Minimal',
    description: 'Restrained palette and plenty of whitespace',
    text: 'Keep the design minimal: restrained palette, generous whitespace, and no decorative clutter.',
  },
  {
    id: 'accessible',
    label: 'Accessible',
    description: 'Semantic landmarks, focus states and AA contrast',
    text: 'Meet WCAG AA: semantic landmarks, visible focus states, and text contrast of at least 4.5:1.',
  },
  {
    id: 'hero',
    label: 'Hero only',
    description: 'Recreate just the hero section',
    text: 'Recreate only the hero section; omit the remaining sections.',
  },
  {
    id: 'system',
    label: 'No web fonts',
    description: 'Keep everything self-contained with system fonts',
    text: 'Use a system font stack and avoid external assets or web fonts.',
  },
]

export function isPresetActive(value: string, text: string): boolean {
  return value.includes(text)
}

export function togglePreset(value: string, text: string): string {
  if (isPresetActive(value, text)) {
    return value
      .replace(text, '')
      .replace(/[ \t]{2,}/g, ' ')
      .trim()
  }
  const trimmed = value.trim()
  return trimmed ? `${trimmed} ${text}` : text
}
