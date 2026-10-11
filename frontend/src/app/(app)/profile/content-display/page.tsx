"use client";

import { SettingsPage, SettingsSection, SettingsRow } from "@/components/SettingsPage";
import Toggle from "@/components/Toggle";
import { usePlayer } from "@/store/player";

export default function ContentDisplayPage() {
  const compactRows = usePlayer((s) => s.compactRows);
  const setCompactRows = usePlayer((s) => s.setCompactRows);

  return (
    <SettingsPage title="Content and display">
      <SettingsSection title="Track lists">
        <SettingsRow
          label="Compact rows"
          description="Tighter spacing in track lists, so more fits on screen."
          action={<Toggle checked={compactRows} onChange={setCompactRows} label="Compact rows" />}
        />
      </SettingsSection>
    </SettingsPage>
  );
}
