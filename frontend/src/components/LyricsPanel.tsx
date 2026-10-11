"use client";

import LyricsView from "@/components/LyricsView";
import SidePanel from "@/components/SidePanel";
import { currentTrack, usePlayer } from "@/store/player";

export default function LyricsPanel() {
  const track = usePlayer(currentTrack);
  const open = usePlayer((s) => s.lyricsOpen);
  const setOpen = usePlayer((s) => s.setLyricsOpen);

  return (
    <SidePanel
      open={open}
      onClose={() => setOpen(false)}
      title="Lyrics"
      subtitle={track?.title}
      testId="lyrics-panel"
      ariaLabel="Lyrics"
    >
      <div className="px-5 py-6">
        <LyricsView trackId={track?.id} active={open} />
      </div>
    </SidePanel>
  );
}
