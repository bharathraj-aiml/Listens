"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import PlayerBar from "@/components/PlayerBar";
import PlayerEngine from "@/components/PlayerEngine";
import QueuePanel from "@/components/QueuePanel";
import Sidebar from "@/components/Sidebar";
import { get } from "@/lib/api";
import type { User } from "@/lib/types";
import { useAuth } from "@/store/auth";

/**
 * Authenticated shell. Because this layout stays mounted while you navigate between its pages,
 * the player engine, mini-player and queue keep running: that is the "persistent player".
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { ready, accessToken, user, load, setUser } = useAuth();

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (ready && !accessToken) router.replace("/login");
  }, [ready, accessToken, router]);
  useEffect(() => {
    if (accessToken && !user) get<User>("/api/auth/me").then(setUser).catch(() => {});
  }, [accessToken, user, setUser]);

  if (!ready || !accessToken) return null;

  return (
    <div className="min-h-dvh md:pl-60">
      <Sidebar />
      <main className="mx-auto max-w-6xl px-4 pb-44 pt-6 md:px-8">{children}</main>
      <PlayerBar />
      <QueuePanel />
      <PlayerEngine />
    </div>
  );
}
