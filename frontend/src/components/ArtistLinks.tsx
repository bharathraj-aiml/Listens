"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment } from "react";
import { creditOf } from "@/lib/credit";
import type { Track } from "@/lib/types";

interface Props {
  track: Pick<Track, "artist" | "artists">;
  /** Called before leaving the page, for links inside an overlay. The overlay is closed first and the page opens once
   *  that has finished: closing a phone overlay steps browser history back (see NavHistory), which would otherwise
   *  undo the navigation the link has just started. */
  closeFirst?: () => void;
}

/** The track's credit with every artist a link to their own page: "Yuvan Shankar Raja, Na.Muthukumar". Only for
 *  places that are not themselves a button or link (rows that play on tap show the credit as plain text). */
export default function ArtistLinks({ track, closeFirst }: Props) {
  const router = useRouter();

  function open(e: React.MouseEvent, href: string) {
    if (!closeFirst || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // new-tab clicks stay native
    e.preventDefault();
    let done = false;
    const go = () => {
      if (done) return;
      done = true;
      window.removeEventListener("popstate", go);
      router.push(href);
    };
    window.addEventListener("popstate", go); // the history step that closing the overlay takes has finished
    window.setTimeout(go, 400); // nothing to wait for (no history entry was pushed): go anyway
    closeFirst();
  }

  return (
    <>
      {creditOf(track).map((a, i) => {
        const href = `/artist/${a.id}`;
        return (
          <Fragment key={a.id}>
            {i > 0 && ", "}
            <Link href={href} onClick={(e) => open(e, href)} className="hover:text-fg hover:underline">{a.name}</Link>
          </Fragment>
        );
      })}
    </>
  );
}
