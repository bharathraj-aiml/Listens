"use client";

import { useState } from "react";
import { SettingsPage, SettingsSection } from "@/components/SettingsPage";
import { patch } from "@/lib/api";
import { useAuth } from "@/store/auth";

export default function AccountPage() {
  const { user, setUser } = useAuth();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [bio, setBio] = useState(user?.bio ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const updated = await patch("/api/auth/me", { display_name: displayName, bio: bio || null });
      setUser(updated as typeof user);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save - try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <SettingsPage title="Account">
      <SettingsSection title="Account details">
        <div className="space-y-4 px-4 py-4">
          <div>
            <label className="block text-xs text-muted">Username</label>
            <p className="text-sm">@{user?.username} <span className="text-xs text-muted">(can&apos;t be changed)</span></p>
          </div>
          <div>
            <label className="block text-xs text-muted">Email</label>
            <p className="text-sm">{user?.email} <span className="text-xs text-muted">(can&apos;t be changed)</span></p>
          </div>
          <div>
            <label htmlFor="display-name" className="block text-xs text-muted">Display name</label>
            <input
              id="display-name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-line bg-raise px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label htmlFor="bio" className="block text-xs text-muted">Bio</label>
            <textarea
              id="bio"
              value={bio ?? ""}
              onChange={(e) => setBio(e.target.value)}
              rows={3}
              className="mt-1 w-full rounded-lg border border-line bg-raise px-3 py-2 text-sm"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={save}
              disabled={saving || !displayName.trim()}
              className="rounded-full bg-accent px-5 py-2 text-sm font-semibold text-ink hover:brightness-110 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            {saved && <span className="text-sm text-ok">Saved</span>}
            {error && <span role="alert" className="text-sm text-danger">{error}</span>}
          </div>
        </div>
      </SettingsSection>
    </SettingsPage>
  );
}
