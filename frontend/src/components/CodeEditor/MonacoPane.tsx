import { useEffect, useRef } from 'react'
import { monaco } from './monaco'
import { installMonacoWorkers } from './workers'

installMonacoWorkers()

interface Props {
  value: string
  onChange: (v: string) => void
}

// Lazy-loaded: only imported when the Code tab opens (see CodeEditor.tsx).
export default function MonacoPane({ value, onChange }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    if (!host.current) return
    const editor = monaco.editor.create(host.current, {
      value,
      language: 'html', // generated doc is full HTML; embedded CSS/JS highlighted via html worker
      theme: 'vs',
      automaticLayout: true,
      minimap: { enabled: false },
      wordWrap: 'on',
      scrollBeyondLastLine: false,
      folding: true,
      matchBrackets: 'always',
      fontSize: 12.5,
      renderWhitespace: 'none',
      stickyScroll: { enabled: false },
      inlayHints: { enabled: 'off' },
      codeLens: false,
    })
    editorRef.current = editor
    const sub = editor.onDidChangeModelContent(() => onChangeRef.current(editor.getValue()))
    return () => { sub.dispose(); editor.dispose(); editorRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const editor = editorRef.current
    if (editor && editor.getValue() !== value) editor.setValue(value)
  }, [value])

  return <div ref={host} className="monaco-host" />
}
