/** Shadow Listens mark: a crescent whose shadow side is a sound-wave. Original artwork.
 *  Flat single amber fill, not a gradient - one accent, used consistently, not a glow effect. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <path d="M22 4.5A12.5 12.5 0 1 0 27.5 22 10 10 0 0 1 22 4.5z" fill="#ffb86b" />
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
        Shadow <span className="text-accent">Listens</span>
      </span>
    </div>
  );
}
