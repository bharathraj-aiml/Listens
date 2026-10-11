"use client";

export default function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${checked ? "bg-ok" : "bg-raise"}`}
    >
      <span className={`absolute left-1 top-1 size-5 rounded-full bg-fg transition-transform ${checked ? "translate-x-5" : "translate-x-0"}`} />
    </button>
  );
}
