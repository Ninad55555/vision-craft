const HEX = /^#[0-9a-f]{6}$/i

export function uniquePalette(colors: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of colors) {
    const color = raw.trim().toLowerCase()
    if (!HEX.test(color) || seen.has(color)) continue
    seen.add(color)
    out.push(color)
  }
  return out
}

export function paletteToCssVariables(colors: string[]): string {
  const swatches = uniquePalette(colors)
  return `:root {\n${swatches.map((color, index) => `  --color-${index + 1}: ${color};`).join('\n')}\n}`
}
