"use client";

import { SettingsPage, SettingsSection, SettingsRow } from "@/components/SettingsPage";
import Toggle from "@/components/Toggle";
import { usePlayer } from "@/store/player";

export default function NotificationsPage() {
  const notifyPush = usePlayer((s) => s.notifyPush);
  const setNotifyPush = usePlayer((s) => s.setNotifyPush);
  const notifyEmail = usePlayer((s) => s.notifyEmail);
  const setNotifyEmail = usePlayer((s) => s.setNotifyEmail);

  return (
    <SettingsPage title="Notifications">
      <SettingsSection title="Notifications">
        <SettingsRow label="Push" action={<Toggle checked={notifyPush} onChange={setNotifyPush} label="Push notifications" />} />
        <SettingsRow label="Email" action={<Toggle checked={notifyEmail} onChange={setNotifyEmail} label="Email notifications" />} />
      </SettingsSection>
    </SettingsPage>
  );
}
