"use client";

import { usePathname, useRouter } from "next/navigation";
import { BackIcon } from "@/components/icons";
import { markBackNavigation } from "@/lib/responseCache";
import { useNav } from "@/store/nav";

/** Phone-only back arrow at the top of every page except Home (desktop has the sidebar). Goes to the previous page in the in-app trail
 *  (see store/nav), or Home when the page was opened directly. Uses replace, not push, so using
 *  the arrow never adds history entries and can't bounce between two pages. */
export default function BackButton() {
  const router = useRouter();
  const pathname = usePathname();
  const stack = useNav((s) => s.stack);
  // The trail updates in an effect, so for one render after navigating it still describes the page we
  // just left. Only trust it once it ends at the current page; Home never shows an arrow.
  if (pathname === "/") return null;
  const trailIsCurrent = stack[stack.length - 1] === pathname;
  const previous = trailIsCurrent && stack.length > 1 ? stack[stack.length - 2] : "/";

  return (
    <button
      aria-label="Back"
      data-testid="back-button"
      onClick={() => {
        markBackNavigation();
        router.replace(previous);
      }}
      className="glass-card mb-4 flex size-11 md:hidden items-center justify-center rounded-full border border-line bg-panel text-fg transition-colors hover:bg-raise active:scale-95"
    >
      <BackIcon />
    </button>
  );
}
