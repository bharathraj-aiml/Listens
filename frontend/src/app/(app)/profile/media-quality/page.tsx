"use client";

import { SettingsPage, SettingsSection } from "@/components/SettingsPage";
import { usePlayer, type Quality } from "@/store/player";

const OPTIONS: { value: Quality; label: string; description: string }[] = [
  { value: "auto", label: "Automatic", description: "Adjusts to your connection." },
  { value: 96, label: "Low", description: "96 kbps - smallest data usage." },
  { value: 160, label: "Normal", description: "160 kbps." },
  { value: 320, label: "Very high", description: "320 kbps - best available quality." },
];

export default function MediaQualityPage() {
  const quality = usePlayer((s) => s.quality);
  const setQuality = usePlayer((s) => s.setQuality);
  const dataSaver = usePlayer((s) => s.dataSaver);

  return (
    <SettingsPage title="Media quality">
      <SettingsSection
        title="Streaming quality"
        description={dataSaver ? "Data Saver is on, which overrides this to Low." : "Not every track has every quality available."}
      >
        {OPTIONS.map((o) => (
          <label key={String(o.value)} className="flex cursor-pointer items-start gap-3 px-4 py-3">
            <input
              type="radio" name="quality" className="mt-1"
              checked={quality === o.value} onChange={() => setQuality(o.value)}
            />
            <span>
              <span className="block text-sm">{o.label}</span>
              <span className="block text-xs text-muted">{o.description}</span>
            </span>
          </label>
        ))}
      </SettingsSection>
    </SettingsPage>
  );
}
