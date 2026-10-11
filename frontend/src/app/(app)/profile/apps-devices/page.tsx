"use client";

import { useEffect, useState } from "react";
import { SettingsPage, SettingsSection, SettingsRow } from "@/components/SettingsPage";
import { get, post } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { usePlayer } from "@/store/player";

export default function AppsDevicesPage() {
  const [count, setCount] = useState<number | null>(null);
  const [revoking, setRevoking] = useState(false);
  const { clear } = useAuth();

  useEffect(() => {
    get<{ count: number }>("/api/auth/me/sessions").then((d) => setCount(d.count)).catch(() => setCount(null));
  }, []);

  async function revokeAll() {
    setRevoking(true);
    try {
      await post("/api/auth/me/sessions/revoke-all");
    } finally {
      // this device's own session was just revoked too - there's no partial "other devices only"
      usePlayer.getState().playQueue([]);
      clear();
      window.location.href = "/login";
    }
  }

  return (
    <SettingsPage title="Apps and devices">
      <SettingsSection title="Active sessions">
        <SettingsRow label="Signed in" description={count === null ? "Loading…" : `${count} active session${count === 1 ? "" : "s"}`} />
        <SettingsRow
          label="Sign out everywhere"
          description="Signs out this device too."
          action={
            <button onClick={revokeAll} disabled={revoking} className="rounded-full bg-danger px-4 py-1.5 text-sm font-semibold text-ink hover:brightness-110 disabled:opacity-50">
              {revoking ? "Signing out…" : "Sign out everywhere"}
            </button>
          }
        />
      </SettingsSection>
    </SettingsPage>
  );
}
