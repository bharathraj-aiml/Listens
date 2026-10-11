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
export default function LyricsView({ trackId, active, glass = false }: { trackId: string | undefined; active: boolean; glass?: boolean }) {
  const currentTime = usePlayer((s) => s.currentTime);
  const requestSeek = usePlayer((s) => s.requestSeek);
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

  const note = glass ? "text-lg font-medium text-white/60" : "text-sm text-muted";
  if (!trackId) return <p className={note}>Nothing playing.</p>;
  if (error) return <p role="alert" className={glass ? "text-lg font-medium text-white/80" : "text-sm text-danger"}>{error}</p>;
  if (!data) return <p className={note}>Loading…</p>;

  if (synced && glass) {
    // Apple Music style: big bold lines, the current one bright and the rest dimmed and softly
    // blurred the further they are from it. Tapping a line seeks to it.
    return (
      <div className="space-y-6" data-testid="lyrics-synced">
        {synced.map((line, i) => {
          const dist = activeIndex < 0 ? 2 : Math.abs(i - activeIndex);
          return (
            <p
              key={i}
              ref={i === activeIndex ? activeRef : undefined}
              data-testid={i === activeIndex ? "lyrics-active-line" : undefined}
              onClick={() => requestSeek(line.time)}
              style={{ filter: dist === 0 ? "none" : `blur(${Math.min(dist, 3) * 0.6}px)` }}
              className={`origin-left cursor-pointer text-[1.75rem] font-bold leading-tight transition-all duration-500 ${
                i === activeIndex ? "scale-100 text-white opacity-100" : "scale-[0.96] text-white opacity-35"
              }`}
            >
              {line.text}
            </p>
          );
        })}
      </div>
    );
  }
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
      <p data-testid="lyrics-plain" className={`whitespace-pre-line ${glass ? "text-2xl font-bold leading-snug text-white/90" : "text-base leading-relaxed text-fg"}`}>
        {data.lyrics}
      </p>
    );
  }
  return <p data-testid="lyrics-empty" className={note}>No lyrics available for this track.</p>;
}
