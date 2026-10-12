#!/usr/bin/env python3
"""Merge artists whose credit differs only by separator ("A/B" vs "A, B" vs "A;B"), case or spacing.

Each credit gets one spelling ("A, B"); songs, albums, followers and open-data metadata move to one surviving
artist row, albums of the same title merge, and artists with nothing attached are removed. See
listens_common.artists. No B2 calls: this only touches the database.

    # dry run: prints what it WOULD change, then rolls back
    set -a; source .env.prod; set +a; .venv/Scripts/python scripts/normalize_artists.py
    # apply
    ... scripts/normalize_artists.py --apply

Uses DATABASE_URL from the environment, so point it at production deliberately.
"""
import argparse

from listens_common import artists
from listens_common.db import get_sessionmaker


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="commit the changes (default: dry run)")
    args = ap.parse_args()

    db = get_sessionmaker()()
    report = artists.merge_artists(db)
    for line in report.details:
        print(line)
    print(f"\n{report.artists_merged} artists merged, {report.renamed} renamed, "
          f"{report.albums_merged} albums merged, {report.empty_removed} empty artists removed")
    if args.apply:
        db.commit()
        print("applied")
    else:
        db.rollback()
        print("dry run - nothing changed (use --apply)")


if __name__ == "__main__":
    main()
