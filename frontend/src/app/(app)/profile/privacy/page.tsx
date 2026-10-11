"use client";

import { useState } from "react";
import { SettingsPage, SettingsSection, SettingsRow } from "@/components/SettingsPage";
import Toggle from "@/components/Toggle";
import { usePlayer } from "@/store/player";

const LOCAL_KEY = "listens.privacy";

function useLocalToggle(key: string, initial = false) {
  const [value, setValue] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(LOCAL_KEY) ?? "{}")[key] ?? initial;
    } catch {
      return initial;
    }
  });
  const set = (v: boolean) => {
    setValue(v);
    try {
      const all = JSON.parse(localStorage.getItem(LOCAL_KEY) ?? "{}");
      localStorage.setItem(LOCAL_KEY, JSON.stringify({ ...all, [key]: v }));
    } catch {
      /* ignore */
    }
  };
  return [value, set] as const;
}

export default function PrivacyPage() {
  const defaultPlaylistPublic = usePlayer((s) => s.defaultPlaylistPublic);
  const setDefaultPlaylistPublic = usePlayer((s) => s.setDefaultPlaylistPublic);
  const [privateSession, setPrivateSession] = useLocalToggle("privateSession");
  const [listeningActivity, setListeningActivity] = useLocalToggle("listeningActivity", true);
  const [recentArtists, setRecentArtists] = useLocalToggle("recentArtists");
  const [profilePlaylists, setProfilePlaylists] = useLocalToggle("profilePlaylists");

  return (
    <SettingsPage title="Privacy and social">
      <SettingsSection title="Listening visibility">
        <SettingsRow label="Private session" description="Temporarily hides your listening activity. Ends after 6 hours." action={<Toggle checked={privateSession} onChange={setPrivateSession} label="Private session" />} />
        <SettingsRow label="Listening activity" description="Followers can see what you're listening to in real time." action={<Toggle checked={listeningActivity} onChange={setListeningActivity} label="Listening activity" />} />
        <SettingsRow label="Recently played artists" description="People can see who you recently listened to on your profile." action={<Toggle checked={recentArtists} onChange={setRecentArtists} label="Recently played artists" />} />
      </SettingsSection>

      <SettingsSection title="Playlist visibility">
        <SettingsRow
          label="Public playlists"
          description="New playlists you create will be public by default (override per playlist any time)."
          action={<Toggle checked={defaultPlaylistPublic} onChange={setDefaultPlaylistPublic} label="Public playlists" />}
        />
        <SettingsRow
          label="Playlists appear on your profile"
          action={<Toggle checked={profilePlaylists} onChange={setProfilePlaylists} label="Playlists appear on your profile" />}
        />
      </SettingsSection>
    </SettingsPage>
  );
}
