"use client";

import { SettingsPage, SettingsSection, SettingsRow } from "@/components/SettingsPage";

export default function AboutPage() {
  return (
    <SettingsPage title="About and support">
      <SettingsSection title="Version">
        <SettingsRow label="Version" description="0.5.0" />
      </SettingsSection>
    </SettingsPage>
  );
}
