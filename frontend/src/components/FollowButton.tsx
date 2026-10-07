"use client";

import { useState } from "react";
import { api, post } from "@/lib/api";

export default function FollowButton({ artistId, initialFollowed }: { artistId: string; initialFollowed: boolean }) {
  const [followed, setFollowed] = useState(initialFollowed);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    setBusy(true);
    const next = !followed;
    try {
      if (next) await post(`/api/catalogue/follows/artists/${artistId}`);
      else await api(`/api/catalogue/follows/artists/${artistId}`, { method: "DELETE" });
      setFollowed(next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={busy}
      data-testid="follow-toggle"
      data-followed={followed}
      className={`rounded-full border px-4 py-1.5 text-sm font-medium disabled:opacity-50 ${
        followed ? "border-line text-fg hover:border-danger hover:text-danger" : "border-accent bg-accent text-ink"
      }`}
    >
      {followed ? "Following" : "Follow"}
    </button>
  );
}
