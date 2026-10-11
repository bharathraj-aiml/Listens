"use client";

import { useRouter } from "next/navigation";
import {
  AboutIcon, AccountIcon, AnalyticsIcon, ContentDisplayIcon, DataSavingIcon, DevicesIcon, NotificationsIcon,
  PlaybackIcon, PrivacyIcon,
} from "@/components/icons";
import { SettingsPage, SettingsRow } from "@/components/SettingsPage";
import { post } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { usePlayer } from "@/store/player";

export default function SettingsListPage() {
  const router = useRouter();
  const { refreshToken, clear } = useAuth();

  async function logout() {
    try {
      if (refreshToken) await post("/api/auth/logout", { refresh_token: refreshToken }, false);
    } catch {
      /* logging out locally is enough if the server is unreachable */
    }
    usePlayer.getState().playQueue([]);
    clear();
    router.replace("/login");
  }

  return (
    <SettingsPage title="Settings">
      <nav aria-label="Settings categories" className="divide-y divide-line/60 rounded-xl border border-line">
        <SettingsRow href="/profile/account" label={<><AccountIcon /> Account</>} description="Username, email" />
        <SettingsRow href="/profile/content-display" label={<><ContentDisplayIcon /> Content and display</>} description="Track list density" />
        <SettingsRow href="/profile/privacy" label={<><PrivacyIcon /> Privacy and social</>} description="Playlist visibility" />
        <SettingsRow href="/profile/playback" label={<><PlaybackIcon /> Playback</>} description="Gapless, crossfade, autoplay, shuffle" />
        <SettingsRow href="/profile/notifications" label={<><NotificationsIcon /> Notifications</>} />
        <SettingsRow href="/profile/apps-devices" label={<><DevicesIcon /> Apps and devices</>} description="Active sessions" />
        <SettingsRow href="/profile/data-saving" label={<><DataSavingIcon /> Data-saving and offline</>} />
        <SettingsRow href="/profile/media-quality" label={<><AnalyticsIcon /> Media quality</>} description="Streaming quality" />
        <SettingsRow href="/profile/about" label={<><AboutIcon /> About and support</>} />
      </nav>

      <button
        onClick={logout}
        data-testid="logout"
        className="w-full rounded-full bg-fg py-3 text-center text-sm font-semibold text-ink hover:brightness-110"
      >
        Log out
      </button>
    </SettingsPage>
  );
}
