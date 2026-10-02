// normalizeHtml: preserve complete documents byte-for-byte; wrap fragments only.
// No regex-heavy parsing, no re-serialization of valid output.

const FULL_DOC = /<!doctype|<html/i

export function isFullDocument(code: string): boolean {
  return FULL_DOC.test(code.slice(0, 4096))
}

export function normalizeHtml(code: string): string {
  const src = code ?? ''
  if (!src.trim()) return ''
  if (isFullDocument(src)) return src // preserve <head>: <style>, <link>, <meta>, <script>
  return (
    '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="UTF-8">\n' +
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n</head>\n<body>\n' +
    src +
    '\n</body>\n</html>'
  )
}
