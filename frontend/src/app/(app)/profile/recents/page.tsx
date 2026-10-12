"use client";

import { useEffect, useState } from "react";
import { TrackRowsSkeleton } from "@/components/Loaders";
import Cover from "@/components/Cover";
import { SettingsPage } from "@/components/SettingsPage";
import { get } from "@/lib/api";
import type { RecentsDay } from "@/lib/types";

function formatDay(iso: string): string {
  const day = new Date(`${iso}T00:00:00Z`);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setUTCDate(today.getUTCDate() - 1);
  const todayStr = today.toISOString().slice(0, 10);
  const yesterdayStr = yesterday.toISOString().slice(0, 10);
  if (iso === todayStr) return "Today";
  if (iso === yesterdayStr) return "Yesterday";
  return day.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

export default function RecentsPage() {
  const [days, setDays] = useState<RecentsDay[] | null>(null);

  useEffect(() => {
    get<RecentsDay[]>("/api/catalogue/analytics/recents").then(setDays).catch(() => {});
  }, []);

  return (
    <SettingsPage title="Recents">
      {days === null && <TrackRowsSkeleton rows={5} />}
      {days && days.length === 0 && <p className="text-sm text-muted">Nothing played in the last 14 days.</p>}
      {days && days.length > 0 && (
        <ul className="divide-y divide-line/60 rounded-xl border border-line">
          {days.map((d) => (
            <li key={d.day} className="flex items-center gap-3 px-4 py-3">
              {d.cover_track && <Cover id={d.cover_track.id} url={d.cover_track.cover_url} size={44} />}
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{formatDay(d.day)}</div>
                <div className="text-xs text-muted">{d.play_count} song{d.play_count === 1 ? "" : "s"} played</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SettingsPage>
  );
}
