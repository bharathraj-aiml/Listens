"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { get } from "@/lib/api";
import type { Lyrics } from "@/lib/types";
import { usePlayer } from "@/store/player";

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

/** The lyrics content itself (fetch + synced/plain/empty rendering), shown in the slide-in
 *  LyricsPanel on desktop and mobile (opened from the Lyrics button). `active` gates the fetch so
 *  a panel that isn't open yet doesn't fetch lyrics for every track in the queue up front. */
export default function LyricsView({ trackId, active }: { trackId: string | undefined; active: boolean }) {
  const currentTime = usePlayer((s) => s.currentTime);
  const [data, setData] = useState<Lyrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (!active || !trackId) return;
    let stale = false;
    setData(null);
    setError(null);
    get<Lyrics>(`/api/catalogue/tracks/${trackId}/lyrics`)
      .then((d) => !stale && setData(d))
      .catch((e) => !stale && setError(e.message));
    return () => {
      stale = true;
    };
  }, [active, trackId]);

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

  // Follow the active line, but only inside the panel's own scroll area. scrollIntoView would also
  // scroll every scrollable ancestor (the page / Now Playing sheet) and drag them along.
  useEffect(() => {
    const line = activeRef.current;
    const box = line?.closest<HTMLElement>(".overflow-y-auto");
    if (!line || !box || !active) return;
    const lineMid = line.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop + line.offsetHeight / 2;
    box.scrollTo({ top: lineMid - box.clientHeight / 2, behavior: "smooth" });
  }, [activeIndex, active]);

  if (!trackId) return <p className="text-sm text-muted">Nothing playing.</p>;
  if (error) return <p role="alert" className="text-sm text-danger">{error}</p>;
  if (!data) return <p className="text-sm text-muted">Loading…</p>;

  if (synced) {
    return (
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
    );
  }
  if (data.lyrics) {
    return (
      <p data-testid="lyrics-plain" className="whitespace-pre-line text-base leading-relaxed text-fg">
        {data.lyrics}
      </p>
    );
  }
  return <p data-testid="lyrics-empty" className="text-sm text-muted">No lyrics available for this track.</p>;
}
