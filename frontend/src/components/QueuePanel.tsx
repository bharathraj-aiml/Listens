"use client";

import Cover from "@/components/Cover";
import { creditText } from "@/lib/credit";
import { CloseIcon } from "@/components/icons";
import QualitySelect from "@/components/QualitySelect";
import SidePanel from "@/components/SidePanel";
import { formatDuration } from "@/lib/format";
import { usePlayer } from "@/store/player";

export default function QueuePanel() {
  const { queue, index, queueOpen, setQueueOpen, jumpTo, removeAt } = usePlayer();
  return (
    <SidePanel
      open={queueOpen}
      onClose={() => setQueueOpen(false)}
      title="Queue"
      headerExtra={<QualitySelect />}
      testId="queue-panel"
      ariaLabel="Play queue"
    >
      <ol>
        {queue.map((t, i) => (
          <li
            key={`${t.id}-${i}`}
            data-testid="queue-item"
            data-current={i === index}
            className={`group flex items-center gap-3 px-4 py-2 transition-colors ${i === index ? "bg-raise" : "hover:bg-raise/60"}`}
          >
            <button onClick={() => jumpTo(i)} className="flex min-w-0 flex-1 items-center gap-3 text-left active:scale-[0.98]">
              <Cover id={t.id} url={t.cover_url} size={40} />
              <span className="min-w-0">
                <span className={`block truncate text-sm ${i === index ? "text-accent" : ""}`}>{t.title}</span>
                <span className="block truncate text-xs text-muted">{creditText(t)}</span>
              </span>
            </button>
            <span className="font-mono text-xs tabular-nums text-muted">{formatDuration(t.duration_ms)}</span>
            <button aria-label={`Remove ${t.title} from queue`} onClick={() => removeAt(i)} className="rounded-full p-1 text-muted opacity-60 hover:text-danger group-hover:opacity-100">
              <CloseIcon width={16} height={16} />
            </button>
          </li>
        ))}
        {!queue.length && <li className="px-4 py-8 text-center text-sm text-muted">Nothing queued. Play a track to start.</li>}
      </ol>
    </SidePanel>
  );
}
