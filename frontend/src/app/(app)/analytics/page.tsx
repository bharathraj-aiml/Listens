"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Cover from "@/components/Cover";
import { get } from "@/lib/api";
import type { HourBucket, SkipRateEntry, TopTrack } from "@/lib/types";

const HOUR_LABELS: Record<number, string> = { 0: "12am", 6: "6am", 12: "12pm", 18: "6pm" };

function TopTracksSection({ tracks }: { tracks: TopTrack[] }) {
  if (!tracks.length) {
    return <p className="text-sm text-muted">Nothing yet. Streams count once a track has played for at least 30 seconds.</p>;
  }
  return (
    <ol data-testid="top-tracks-list" className="divide-y divide-line/60">
      {tracks.map((t, i) => (
        <li key={t.track.id} data-testid="top-tracks-row" className="flex items-center gap-3 px-2 py-2">
          <span className="w-5 shrink-0 text-right font-mono text-sm text-muted">{i + 1}</span>
          <Cover id={t.track.id} url={t.track.cover_url} size={40} />
          <div className="min-w-0 flex-1">
            <Link href={`/artist/${t.track.artist.id}`} className="block truncate text-sm hover:underline">{t.track.title}</Link>
            <div className="truncate text-xs text-muted">{t.track.artist.name}</div>
          </div>
          <span className="shrink-0 font-mono text-xs tabular-nums text-muted">
            {t.stream_count} stream{t.stream_count === 1 ? "" : "s"}
          </span>
        </li>
      ))}
    </ol>
  );
}

function SkipRateSection({ rows }: { rows: SkipRateEntry[] }) {
  if (!rows.length) {
    return <p className="text-sm text-muted">Nothing yet. A track needs at least 2 plays before its skip rate means anything.</p>;
  }
  return (
    <ul data-testid="skip-rate-list" className="space-y-3">
      {rows.map((r) => (
        <li key={r.track.id} data-testid="skip-rate-row" className="flex items-center gap-3">
          <Cover id={r.track.id} url={r.track.cover_url} size={36} />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-sm">{r.track.title}</span>
              <span className="shrink-0 font-mono text-xs tabular-nums text-muted">
                {Math.round(r.skip_rate * 100)}% ({r.skip_count}/{r.play_count})
              </span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-line">
              <div className="h-1.5 rounded-full bg-danger" style={{ width: `${Math.round(r.skip_rate * 100)}%` }} />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function ListeningByHourSection({ hours }: { hours: HourBucket[] }) {
  const max = Math.max(1, ...hours.map((h) => h.count));
  if (hours.every((h) => h.count === 0)) {
    return <p className="text-sm text-muted">Nothing yet. Play something to see when you listen.</p>;
  }
  // Pixel heights, not CSS percentages: each column is sized by its content (items-end means
  // the flex container doesn't stretch children to a shared height), so a child using
  // `height: X%` has no definite-height ancestor to resolve against and silently renders at 0.
  const CHART_PX = 128; // matches h-32
  return (
    <div data-testid="listening-by-hour" className="flex items-end gap-0.5" style={{ height: CHART_PX }}>
      {hours.map((h) => (
        <div key={h.hour} className="group relative flex-1" title={`${h.hour}:00 - ${h.count} play${h.count === 1 ? "" : "s"}`}>
          <div
            data-testid="hour-bar"
            data-hour={h.hour}
            data-count={h.count}
            className="rounded-t bg-accent/70 transition-colors group-hover:bg-accent"
            style={{ height: Math.max(2, (h.count / max) * CHART_PX) }}
          />
          {HOUR_LABELS[h.hour] && <div className="mt-1 text-center text-[10px] text-muted">{HOUR_LABELS[h.hour]}</div>}
        </div>
      ))}
    </div>
  );
}

export default function AnalyticsPage() {
  const [topTracks, setTopTracks] = useState<TopTrack[] | null>(null);
  const [skipRate, setSkipRate] = useState<SkipRateEntry[] | null>(null);
  const [hours, setHours] = useState<HourBucket[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<TopTrack[]>("/api/catalogue/analytics/top-tracks").then(setTopTracks).catch((e) => setError(e.message));
    get<SkipRateEntry[]>("/api/catalogue/analytics/skip-rate").then(setSkipRate).catch(() => {});
    get<HourBucket[]>("/api/catalogue/analytics/listening-by-hour").then(setHours).catch(() => {});
  }, []);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Your listening</h1>
        <p className="text-sm text-muted">Based on what you've actually played, not just clicked.</p>
      </header>
      {error && <p role="alert" className="text-danger">{error}</p>}

      <section aria-labelledby="top-tracks">
        <h2 id="top-tracks" className="mb-2 text-lg font-medium">Top tracks</h2>
        {topTracks === null ? <p className="text-sm text-muted">Loading…</p> : <TopTracksSection tracks={topTracks} />}
      </section>

      <section aria-labelledby="skip-rate">
        <h2 id="skip-rate" className="mb-2 text-lg font-medium">Skip rate</h2>
        {skipRate === null ? <p className="text-sm text-muted">Loading…</p> : <SkipRateSection rows={skipRate} />}
      </section>

      <section aria-labelledby="by-hour">
        <h2 id="by-hour" className="mb-2 text-lg font-medium">Listening by hour</h2>
        {hours === null ? <p className="text-sm text-muted">Loading…</p> : <ListeningByHourSection hours={hours} />}
      </section>
    </div>
  );
}
