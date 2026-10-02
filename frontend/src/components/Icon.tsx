// Inline stroke icons (currentColor, aria-hidden). No emoji, no icon font.
export type IconName =
  | 'spark'
  | 'image'
  | 'copy'
  | 'download'
  | 'refresh'
  | 'alert'
  | 'check'
  | 'eye'
  | 'code'
  | 'x'
  | 'clock'

const PATHS: Record<IconName, React.ReactNode> = {
  spark: <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />,
  image: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="m5 18 5-5 3 3 2-2 4 4" />
    </>
  ),
  copy: (
    <>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </>
  ),
  download: <path d="M12 4v11m0 0 4-4m-4 4-4-4M4 19h16" />,
  refresh: <path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5" />,
  alert: (
    <>
      <path d="M12 4 2.5 20h19L12 4Z" />
      <path d="M12 10v4m0 3v.5" />
    </>
  ),
  check: <path d="m4.5 12.5 5 5 10-11" />,
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  code: <path d="m8 8-4.5 4L8 16m8-8 4.5 4L16 16M13.5 5l-3 14" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
}

export default function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className="icon"
    >
      {PATHS[name]}
    </svg>
  )
}
