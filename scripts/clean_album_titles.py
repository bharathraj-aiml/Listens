#!/usr/bin/env python3
"""Remove store boilerplate from album titles and fold albums that then repeat into one.

"Guru (Original Motion Picture Soundtrack)", "Guru [Original Motion Picture Soundtrack]" and "Guru" become one album
"Guru"; "(Deluxe Edition)", "- Single", "[Extended Edition]" and misspelt variants go too. What a listener may want
stays: "(From "Cobra")", "(Tamil)", "[Slowed + Reverb]". Albums merge only when they share an artist (their own, or
anyone credited on their songs), so two unrelated records both called "Greatest Hits" stay apart. Database only.

    set -a; source .env.prod; set +a
    .venv/Scripts/python scripts/clean_album_titles.py            # dry run
    .venv/Scripts/python scripts/clean_album_titles.py --apply
"""
import argparse

from sqlalchemy import func, select

from listens_common import albums
from listens_common.db import get_sessionmaker
from listens_common.models import Album


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="save the changes (default: dry run)")
    ap.add_argument("-v", "--verbose", action="store_true", help="print every rename and merge")
    args = ap.parse_args()

    db = get_sessionmaker()()
    before = db.scalar(select(func.count()).select_from(Album))
    report = albums.normalize_albums(db)
    if args.verbose:
        for line in report.details:
            print(line)
    after = db.scalar(select(func.count()).select_from(Album))
    print(f"albums: {before} -> {after} ({report.renamed} titles cleaned, {report.merged} duplicate albums merged)")
    if args.apply:
        db.commit()
        print("applied")
    else:
        db.rollback()
        print("dry run - nothing changed (use --apply)")


if __name__ == "__main__":
    main()
