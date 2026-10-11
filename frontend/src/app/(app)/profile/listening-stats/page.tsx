"use client";

import { useEffect, useState } from "react";
import Cover from "@/components/Cover";
import { SettingsPage } from "@/components/SettingsPage";
import { get } from "@/lib/api";
import type { ListeningStats } from "@/lib/types";

function StatsCard({ stats }: { stats: ListeningStats | null }) {
  if (!stats) return <p className="text-sm text-muted">Loading…</p>;
  if (!stats.top_artist && !stats.top_track) {
    return <p className="text-sm text-muted">Nothing played in this range yet.</p>;
  }
  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-xl border border-line p-4">
        <p className="text-xs text-muted">Top artist</p>
        {stats.top_artist ? (
          <>
            <p className="mt-2 font-semibold">{stats.top_artist.artist.name}</p>
            <p className="text-xs text-muted">{stats.top_artist.play_count} plays</p>
          </>
        ) : <p className="mt-2 text-sm text-muted">—</p>}
      </div>
      <div className="rounded-xl border border-line p-4">
        <p className="text-xs text-muted">Top song</p>
        {stats.top_track ? (
          <div className="mt-2 flex items-center gap-2">
            <Cover id={stats.top_track.track.id} url={stats.top_track.track.cover_url} size={40} />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{stats.top_track.track.title}</p>
              <p className="truncate text-xs text-muted">{stats.top_track.stream_count} streams</p>
            </div>
          </div>
        ) : <p className="mt-2 text-sm text-muted">—</p>}
      </div>
    </div>
  );
}

export default function ListeningStatsPage() {
  const [thisWeek, setThisWeek] = useState<ListeningStats | null>(null);
  const [lastWeek, setLastWeek] = useState<ListeningStats | null>(null);

  useEffect(() => {
    get<ListeningStats>("/api/catalogue/analytics/listening-stats?range=this_week").then(setThisWeek).catch(() => {});
    get<ListeningStats>("/api/catalogue/analytics/listening-stats?range=last_week").then(setLastWeek).catch(() => {});
  }, []);

  return (
    <SettingsPage title="Listening stats">
      <section>
        <h2 className="mb-2 text-lg font-medium">This week</h2>
        {thisWeek && <p className="mb-3 text-xs text-muted">{thisWeek.start} – {thisWeek.end}</p>}
        <StatsCard stats={thisWeek} />
      </section>
      <section>
        <h2 className="mb-2 text-lg font-medium">Last week</h2>
        {lastWeek && <p className="mb-3 text-xs text-muted">{lastWeek.start} – {lastWeek.end}</p>}
        <StatsCard stats={lastWeek} />
      </section>
    </SettingsPage>
  );
}
