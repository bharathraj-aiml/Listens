"use client";

import { SettingsPage, SettingsSection, SettingsRow } from "@/components/SettingsPage";
import Toggle from "@/components/Toggle";
import { usePlayer } from "@/store/player";

export default function ContentDisplayPage() {
  const compactRows = usePlayer((s) => s.compactRows);
  const setCompactRows = usePlayer((s) => s.setCompactRows);
  const followSystem = usePlayer((s) => s.followSystemTransparency);
  const setFollowSystem = usePlayer((s) => s.setFollowSystemTransparency);

  return (
    <SettingsPage title="Content and display">
      <SettingsSection title="Track lists">
        <SettingsRow
          label="Compact rows"
          description="Tighter spacing in track lists, so more fits on screen."
          action={<Toggle checked={compactRows} onChange={setCompactRows} label="Compact rows" />}
        />
      </SettingsSection>

      <SettingsSection title="Appearance">
        <SettingsRow
          label="Follow system transparency setting"
          description="Off: the frosted-glass look always shows. On: it switches to solid panels when your device is set to reduce transparency (Windows: Settings, Accessibility, Visual effects, Transparency effects)."
          action={<Toggle checked={followSystem} onChange={setFollowSystem} label="Follow system transparency setting" />}
        />
      </SettingsSection>
    </SettingsPage>
  );
}
