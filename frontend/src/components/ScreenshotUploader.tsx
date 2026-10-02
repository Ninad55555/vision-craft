import { useEffect, useRef, useState } from 'react'
import type { BackendConfig } from '../types'
import Icon from './Icon'

interface Props {
  config: BackendConfig | null
  file: File | null
  onFile: (f: File | null, err?: string) => void
}

export default function ScreenshotUploader({ config, file, onFile }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const [url, setUrl] = useState('')

  useEffect(() => {
    if (!file) { setUrl(''); return }
    const u = URL.createObjectURL(file)
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [file])

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = [...(e.clipboardData?.items ?? [])].find((i) => i.type.startsWith('image/'))
      const f = item?.getAsFile()
      if (f) accept(f)
    }
    document.addEventListener('paste', onPaste)
    return () => document.removeEventListener('paste', onPaste)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config])

  const accept = (f: File) => {
    const okType = (config?.accepted_types ?? ['image/png', 'image/jpeg', 'image/webp']).includes(f.type)
    if (!okType) return onFile(null, `Unsupported type "${f.type || 'unknown'}". Use PNG, JPEG, or WebP.`)
    const maxBytes = (config?.max_upload_mb ?? 10) * 1024 * 1024
    if (f.size > maxBytes) return onFile(null, `File is ${(f.size / 1048576).toFixed(1)} MB; the limit is ${config?.max_upload_mb} MB.`)
    onFile(f)
  }

  if (file && url) {
    return (
      <div className="thumb-card">
        <img src={url} alt="Uploaded screenshot thumbnail" />
        <div className="thumb-body">
          <p className="thumb-name">{file.name}</p>
          <p className="thumb-meta">{(file.size / 1024).toFixed(0)} KB</p>
        </div>
        <button type="button" className="icon-btn" onClick={() => onFile(null)} aria-label="Remove screenshot">
          <Icon name="x" size={16} />
        </button>
      </div>
    )
  }

  return (
    <div
      className={`dropzone${drag ? ' drag' : ''}`}
      tabIndex={0}
      role="button"
      aria-label="Upload a screenshot: activate to choose a file, or drag and drop, or paste from clipboard"
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click() } }}
      onDragEnter={(e) => { e.preventDefault(); setDrag(true) }}
      onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
      onDragLeave={(e) => { e.preventDefault(); setDrag(false) }}
      onDrop={(e) => {
        e.preventDefault(); setDrag(false)
        const f = [...(e.dataTransfer?.files ?? [])].find((x) => x.type.startsWith('image/'))
        if (f) accept(f)
      }}
    >
      <span className="dz-icon" aria-hidden="true"><Icon name="image" size={28} /></span>
      <p className="dz-title">Drop a screenshot here</p>
      <p className="dz-sub">or <span className="dz-link">choose a file</span>, or paste with <kbd>Ctrl</kbd>+<kbd>V</kbd></p>
      <p className="dz-formats">PNG · JPG · WebP{config ? ` · up to ${config.max_upload_mb} MB` : ''}</p>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        onChange={(e) => {
          if (e.target.files?.[0]) accept(e.target.files[0])
          e.target.value = ''
        }}
      />
    </div>
  )
}
