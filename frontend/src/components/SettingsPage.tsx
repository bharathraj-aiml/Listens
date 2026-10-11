"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { CaretRightIcon } from "@/components/icons";

/** Shared shell for every /profile/* settings page: a back link + title header, consistent
 *  spacing, and section/row helpers so the ~10 settings pages don't each hand-roll this. */
export function SettingsPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-8 pb-12">
      <header className="flex items-center gap-3">
        <Link href="/profile" aria-label="Back to profile" className="flex size-9 items-center justify-center rounded-full text-muted hover:text-fg">
          <CaretRightIcon className="rotate-180" />
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      </header>
      {children}
    </div>
  );
}

export function SettingsSection({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-medium">{title}</h2>
      {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      <div className="mt-3 divide-y divide-line/60 rounded-xl border border-line">{children}</div>
    </section>
  );
}

export function SettingsRow({
  label, description, action, href,
}: { label: ReactNode; description?: string; action?: ReactNode; href?: string }) {
  const content = (
    <>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3 text-sm">{label}</div>
        {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      </div>
      {action ?? (href && <CaretRightIcon className="shrink-0 text-muted" />)}
    </>
  );
  const className = "flex items-center gap-3 px-4 py-3";
  return href ? (
    <Link href={href} className={`${className} hover:bg-raise/40`}>{content}</Link>
  ) : (
    <div className={className}>{content}</div>
  );
}
