"use client";

import { useState } from "react";
import { SettingsPage, SettingsSection, SettingsRow } from "@/components/SettingsPage";
import Toggle from "@/components/Toggle";
import { usePlayer } from "@/store/player";

export default function DataSavingPage() {
  const dataSaver = usePlayer((s) => s.dataSaver);
  const setDataSaver = usePlayer((s) => s.setDataSaver);
  const [offlineMode, setOfflineMode] = useState(false);

  return (
    <SettingsPage title="Data-saving and offline">
      <SettingsSection title="Data saver">
        <SettingsRow
          label="Data Saver mode"
          description="Streams at 96 kbps."
          action={<Toggle checked={dataSaver} onChange={setDataSaver} label="Data Saver mode" />}
        />
      </SettingsSection>
      <SettingsSection title="Offline">
        <SettingsRow
          label="Offline mode"
          action={<Toggle checked={offlineMode} onChange={setOfflineMode} label="Offline mode" />}
        />
      </SettingsSection>
    </SettingsPage>
  );
}
