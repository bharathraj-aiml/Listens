"use client";

import Cover from "@/components/Cover";
import { CloseIcon } from "@/components/icons";
import QualitySelect from "@/components/QualitySelect";
import { formatDuration } from "@/lib/format";
import { usePlayer } from "@/store/player";

export default function QueuePanel() {
  const { queue, index, queueOpen, setQueueOpen, jumpTo, removeAt } = usePlayer();
  if (!queueOpen) return null;
  return (
    <aside
      data-testid="queue-panel"
      aria-label="Play queue"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-sm flex-col border-l border-line bg-panel shadow-2xl"
    >
      <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h2 className="font-semibold">Queue</h2>
        <div className="flex items-center gap-2">
          <QualitySelect />
          <button aria-label="Close queue" onClick={() => setQueueOpen(false)} className="rounded-full p-1.5 text-muted hover:text-fg">
            <CloseIcon />
          </button>
        </div>
      </header>
      <ol className="flex-1 overflow-y-auto pb-40">
        {queue.map((t, i) => (
          <li
            key={`${t.id}-${i}`}
            data-testid="queue-item"
            data-current={i === index}
            className={`group flex items-center gap-3 px-4 py-2 ${i === index ? "bg-raise" : "hover:bg-raise/60"}`}
          >
            <button onClick={() => jumpTo(i)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
              <Cover id={t.id} url={t.cover_url} size={40} />
              <span className="min-w-0">
                <span className={`block truncate text-sm ${i === index ? "text-accent" : ""}`}>{t.title}</span>
                <span className="block truncate text-xs text-muted">{t.artist.name}</span>
              </span>
            </button>
            <span className="text-xs tabular-nums text-muted">{formatDuration(t.duration_ms)}</span>
            <button aria-label={`Remove ${t.title} from queue`} onClick={() => removeAt(i)} className="rounded-full p-1 text-muted opacity-60 hover:text-danger group-hover:opacity-100">
              <CloseIcon width={16} height={16} />
            </button>
          </li>
        ))}
        {!queue.length && <li className="px-4 py-8 text-center text-sm text-muted">Nothing queued. Play a track to start.</li>}
      </ol>
    </aside>
  );
}
