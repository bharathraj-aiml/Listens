/** Shadow Listens mark: a crescent whose shadow side is a sound-wave. Original artwork. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="sl-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffb86b" />
          <stop offset="1" stopColor="#8b7bff" />
        </linearGradient>
      </defs>
      <path d="M22 4.5A12.5 12.5 0 1 0 27.5 22 10 10 0 0 1 22 4.5z" fill="url(#sl-g)" />
      <g fill="#0b0b12">
        <rect x="11" y="13" width="2" height="6" rx="1" />
        <rect x="15" y="10" width="2" height="12" rx="1" />
        <rect x="19" y="14" width="2" height="4" rx="1" />
      </g>
    </svg>
  );
}

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      <LogoMark />
      <span className="text-lg font-semibold tracking-tight">
        Shadow <span className="text-glow">Listens</span>
      </span>
    </div>
  );
}
