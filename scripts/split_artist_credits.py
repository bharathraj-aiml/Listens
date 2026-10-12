#!/usr/bin/env python3
"""Give every person in a multi-artist credit their own artist, and credit each song to all of them.

Before: a song's artist was the whole credit ("Yuvan Shankar Raja, Na.Muthukumar") as ONE artist row, so every
different line-up was a different artist and no collaborator had a page that listed their songs.
After: one artist per person, a song credited to each of them (table track_artists, migration 0006), and the first
credited person is the song's primary artist (also what albums hang off). Spelling variants of known Tamil artists
("Yuvanshankar Raja", "SPB") are one person (listens_common.tamil_seed aliases). No B2 calls: database only.

    set -a; source .env.prod; set +a; .venv/Scripts/python scripts/split_artist_credits.py            # dry run
    ... scripts/split_artist_credits.py --apply

Needs migration 0006 applied first (alembic -c migrations/alembic.ini upgrade head). Safe to re-run.
After applying, refresh the recommender's artist data: scripts/enrich_library.py --apply
"""
import argparse
import sys

from sqlalchemy import func, select

from listens_common import artists
from listens_common.db import get_sessionmaker
from listens_common.models import Artist, Track


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="commit the changes (default: dry run)")
    ap.add_argument("-v", "--verbose", action="store_true", help="print every credit that is split")
    args = ap.parse_args()

    db = get_sessionmaker()()
    n_artists = db.scalar(select(func.count()).select_from(Artist))
    n_tracks = db.scalar(select(func.count()).select_from(Track))
    report = artists.split_credits(db)
    if args.verbose:
        for line in report.details:
            print(line)
    after = db.scalar(select(func.count()).select_from(Artist))
    print(f"{n_tracks} songs. Artists: {n_artists} -> {after} "
          f"({report.credits_split} credit rows split, {report.people_created} people added, "
          f"{report.tracks_linked} single-artist songs linked, {report.albums_moved} albums moved, "
          f"{report.albums_merged} albums merged)")
    multi = sorted(
        ((len(t.artists), t.title) for t in db.scalars(select(Track)).unique()), reverse=True
    )[:3]
    print("most credited:", "; ".join(f"{t} ({n})" for n, t in multi))
    if args.apply:
        db.commit()
        print("applied")
    else:
        db.rollback()
        print("dry run - nothing changed (use --apply)", file=sys.stderr)


if __name__ == "__main__":
    main()
