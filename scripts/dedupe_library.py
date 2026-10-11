#!/usr/bin/env python3
"""List (and optionally delete) duplicate songs already in the library.

Same rules the app applies automatically to new uploads (listens_common.dedupe): same uploader, same
normalised title + artist, compatible album, durations within 3s - keep the highest source bitrate
(oldest on a tie), delete the rest including their files in B2.

    # dry run: only prints what it WOULD delete
    set -a; source .env.prod; set +a; .venv/Scripts/python scripts/dedupe_library.py
    # actually delete
    ... scripts/dedupe_library.py --apply

Uses DATABASE_URL and S3_* from the environment, so point it at production deliberately.
"""
import argparse

from sqlalchemy import select

from listens_common import dedupe
from listens_common.config import get_settings
from listens_common.db import get_sessionmaker
from listens_common.models import Artist, Track
from listens_common.storage import get_s3


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="delete the losing copies (default: dry run)")
    args = ap.parse_args()

    db = get_sessionmaker()()
    ready = db.scalars(select(Track).where(Track.status == "ready").order_by(Track.created_at)).all()
    seen, groups = set(), []
    for t in ready:
        if t.id in seen:
            continue
        group = dedupe.duplicate_group(db, t)
        if group:
            seen.update(x.id for x in group)
            groups.append(group)

    if not groups:
        print(f"No duplicates among {len(ready)} ready tracks.")
        return
    losers = []
    for group in groups:
        keeper = dedupe.pick_keeper(group)
        artist = db.get(Artist, keeper.artist_id)
        print(f"\n{keeper.title!r} - {artist.name if artist else '?'}")
        for t in group:
            verdict = "KEEP  " if t.id == keeper.id else "DELETE"
            print(f"  {verdict} {str(t.id)[:8]}  {t.source_bitrate_kbps or '?'} kbps  {(t.duration_ms or 0) / 1000:.1f}s  uploaded {t.created_at:%Y-%m-%d %H:%M}")
            if t.id != keeper.id:
                losers.append((t, keeper))
    print(f"\n{len(groups)} duplicate group(s), {len(losers)} copy/copies to delete.")
    if not args.apply:
        print("Dry run - nothing deleted. Re-run with --apply to delete.")
        return
    s3, settings = get_s3(), get_settings()
    for t, keeper in losers:
        dedupe.remove_track(db, s3, settings, t, keep=keeper)
    print("Done.")


if __name__ == "__main__":
    main()
