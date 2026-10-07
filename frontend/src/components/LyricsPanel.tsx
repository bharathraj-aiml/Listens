"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CloseIcon } from "@/components/icons";
import { get } from "@/lib/api";
import type { Lyrics } from "@/lib/types";
import { currentTrack, usePlayer } from "@/store/player";

interface LrcLine { time: number; text: string }

const LRC_LINE = /^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/;

function parseLrc(raw: string): LrcLine[] {
  const lines: LrcLine[] = [];
  for (const line of raw.split("\n")) {
    const m = LRC_LINE.exec(line.trim());
    if (!m) continue;
    const text = m[3].trim();
    if (text) lines.push({ time: Number(m[1]) * 60 + Number(m[2]), text });
  }
  return lines.sort((a, b) => a.time - b.time);
}

export default function LyricsPanel() {
  const track = usePlayer(currentTrack);
  const open = usePlayer((s) => s.lyricsOpen);
  const setOpen = usePlayer((s) => s.setLyricsOpen);
  const currentTime = usePlayer((s) => s.currentTime);
  const [data, setData] = useState<Lyrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (!open || !track) return;
    let stale = false;
    setData(null);
    setError(null);
    get<Lyrics>(`/api/catalogue/tracks/${track.id}/lyrics`)
      .then((d) => !stale && setData(d))
      .catch((e) => !stale && setError(e.message));
    return () => {
      stale = true;
    };
  }, [open, track?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const synced = useMemo(() => (data?.lyrics_synced ? parseLrc(data.lyrics_synced) : null), [data]);
  const activeIndex = useMemo(() => {
    if (!synced) return -1;
    let idx = -1;
    for (let i = 0; i < synced.length; i++) {
      if (synced[i].time <= currentTime) idx = i;
      else break;
    }
    return idx;
  }, [synced, currentTime]);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeIndex]);

  if (!open) return null;

  return (
    <aside
      data-testid="lyrics-panel"
      aria-label="Lyrics"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-sm flex-col border-l border-line bg-panel shadow-2xl"
    >
      <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <h2 className="font-semibold">Lyrics</h2>
          {track && <p className="truncate text-xs text-muted">{track.title}</p>}
        </div>
        <button aria-label="Close lyrics" onClick={() => setOpen(false)} className="flex size-11 shrink-0 items-center justify-center rounded-full text-muted hover:text-fg">
          <CloseIcon />
        </button>
      </header>
      <div className="flex-1 overflow-y-auto px-5 py-6 pb-40">
        {!track && <p className="text-sm text-muted">Nothing playing.</p>}
        {track && error && <p role="alert" className="text-sm text-danger">{error}</p>}
        {track && !error && !data && <p className="text-sm text-muted">Loading…</p>}
        {track && data && synced && (
          <div className="space-y-3" data-testid="lyrics-synced">
            {synced.map((line, i) => (
              <p
                key={i}
                ref={i === activeIndex ? activeRef : undefined}
                data-testid={i === activeIndex ? "lyrics-active-line" : undefined}
                className={`text-lg leading-relaxed transition-colors ${i === activeIndex ? "font-semibold text-accent" : "text-muted"}`}
              >
                {line.text}
              </p>
            ))}
          </div>
        )}
        {track && data && !synced && data.lyrics && (
          <p data-testid="lyrics-plain" className="whitespace-pre-line text-base leading-relaxed text-fg">
            {data.lyrics}
          </p>
        )}
        {track && data && !synced && !data.lyrics && (
          <p data-testid="lyrics-empty" className="text-sm text-muted">No lyrics available for this track.</p>
        )}
      </div>
    </aside>
  );
}
