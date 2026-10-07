"use client";

import { HeartIcon } from "@/components/icons";
import { useLikes } from "@/store/likes";

export default function LikeButton({ trackId, size = 20 }: { trackId: string; size?: number }) {
  const liked = useLikes((s) => s.isLiked(trackId));
  const toggle = useLikes((s) => s.toggle);
  return (
    <button
      aria-label={liked ? "Unlike" : "Like"}
      aria-pressed={liked}
      data-testid="like-toggle"
      data-liked={liked}
      onClick={(e) => {
        e.stopPropagation();
        toggle(trackId);
      }}
      className={`flex size-9 items-center justify-center rounded-full ${liked ? "text-accent" : "text-muted hover:text-fg"}`}
    >
      <HeartIcon weight={liked ? "fill" : "regular"} width={size} height={size} />
    </button>
  );
}
