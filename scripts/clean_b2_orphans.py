#!/usr/bin/env python3
"""Delete files in the Backblaze buckets that no song refers to.

Leftovers build up when a song is removed (or an upload's database write is lost): `originals/<id>/` and `hls/<id>/`
folders whose id is not a track, and cover images no track or album points at. Nothing in the app can reach these, so
they only use storage. Dry run by default: lists each with its size.

    set -a; source .env.prod; set +a
    .venv/Scripts/python scripts/clean_b2_orphans.py            # dry run
    .venv/Scripts/python scripts/clean_b2_orphans.py --apply

Do not run it while an upload is in progress (the file reaches B2 a moment before its database row). Deleting cannot be undone.
Run scripts/register_b2_orphans.py first if a loose original might be a song you want in
the library (it adds originals that are not duplicates instead of deleting them).
"""
import argparse

from sqlalchemy import select

from listens_common.config import get_settings
from listens_common.db import get_sessionmaker
from listens_common.models import Album, Track
from listens_common.storage import delete_prefix, get_s3


def objects(s3, bucket: str, prefix: str) -> list[dict]:
    out, token = [], None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        page = s3.list_objects_v2(**kw)
        out += page.get("Contents", [])
        if not page.get("IsTruncated"):
            return out
        token = page["NextContinuationToken"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="delete them (default: dry run)")
    args = ap.parse_args()

    settings, s3 = get_settings(), get_s3()
    with get_sessionmaker()() as db:
        track_ids = {str(i) for i in db.scalars(select(Track.id))}
        cover_keys = {k for k in db.scalars(select(Track.cover_key)) if k} | {k for k in db.scalars(select(Album.cover_key)) if k}

    folders: dict[tuple[str, str], int] = {}
    for prefix in ("originals/", "hls/"):
        for o in objects(s3, settings.s3_bucket_audio, prefix):
            folder_id = o["Key"].split("/")[1]
            if folder_id not in track_ids:
                folders[(prefix, folder_id)] = folders.get((prefix, folder_id), 0) + o["Size"]
    stray_covers = [o for o in objects(s3, settings.s3_bucket_covers, "") if o["Key"] not in cover_keys]

    total = sum(folders.values()) + sum(o["Size"] for o in stray_covers)
    for (prefix, folder_id), size in sorted(folders.items()):
        print(f"{prefix}{folder_id}/  {size / 1e6:.1f} MB  (no such song)")
    for o in stray_covers:
        print(f"covers: {o['Key']}  {o['Size'] / 1e3:.0f} KB  (no song or album uses it)")
    print(f"\n{len(folders)} audio folders and {len(stray_covers)} cover files unused, {total / 1e6:.1f} MB")
    if not args.apply:
        print("dry run - nothing deleted (use --apply)")
        return
    for (prefix, folder_id) in folders:
        delete_prefix(s3, settings.s3_bucket_audio, f"{prefix}{folder_id}/")
    for o in stray_covers:
        s3.delete_object(Bucket=settings.s3_bucket_covers, Key=o["Key"])
    print("deleted")


if __name__ == "__main__":
    main()
