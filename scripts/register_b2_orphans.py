#!/usr/bin/env python3
"""Add songs that exist in the Backblaze bucket but not in the app.

An "orphan" is an `originals/<id>/source.<ext>` object with no track row (an upload whose database write was
lost, or a file copied in by hand). Each one is downloaded once (the only B2 download this script makes), its tags
and lyrics are read the way the upload endpoint reads them, and it is registered as a track under its EXISTING key,
so nothing is uploaded again. A file whose bytes or song (same title + artist, compatible album) are already in the
library is skipped and reported, not added twice. Registered tracks get status 'uploaded'; transcode them with the
worker (scripts/run_local_worker.sh, or the Render worker's schedule).

Also lists streaming copies (`hls/<id>/`) that have no track row: those have no source file to read tags from, so
they cannot be registered automatically.

    set -a; source .env.prod; set +a; .venv/Scripts/python scripts/register_b2_orphans.py            # dry run
    ... scripts/register_b2_orphans.py --apply
"""
import argparse
import hashlib
import importlib.util
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "libs" / "common"))

from sqlalchemy import func, or_, select  # noqa: E402

from listens_common import artists, dedupe  # noqa: E402
from listens_common.config import get_settings  # noqa: E402
from listens_common.db import get_sessionmaker  # noqa: E402
from listens_common.models import Album, Artist, Track, User  # noqa: E402
from listens_common.storage import get_s3  # noqa: E402


def _load_tags_module():
    """services/catalogue/app/tags.py, loaded by path (the worker's package already owns the name `app`)."""
    spec = importlib.util.spec_from_file_location("catalogue_tags", ROOT / "services" / "catalogue" / "app" / "tags.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def folder_ids(s3, bucket: str, prefix: str) -> dict[str, list[dict]]:
    """{id: [objects]} for every `<prefix><id>/...` object (paginated list calls only)."""
    out: dict[str, list[dict]] = {}
    token = None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        page = s3.list_objects_v2(**kw)
        for obj in page.get("Contents", []):
            out.setdefault(obj["Key"].split("/")[1], []).append(obj)
        if not page.get("IsTruncated"):
            return out
        token = page["NextContinuationToken"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default="shadow", help="username or email that owns the registered songs")
    ap.add_argument("--license", default="Personal library")
    ap.add_argument("--apply", action="store_true", help="register the songs (default: dry run)")
    args = ap.parse_args()

    tags_mod = _load_tags_module()
    settings, s3, sessions = get_settings(), get_s3(), get_sessionmaker()
    originals = folder_ids(s3, settings.s3_bucket_audio, "originals/")
    streams = folder_ids(s3, settings.s3_bucket_audio, "hls/")

    with sessions() as db:
        user = db.scalar(select(User).where(or_(func.lower(User.username) == args.user.lower(), func.lower(User.email) == args.user.lower())))
        if user is None:
            sys.exit(f"No user '{args.user}'")
        known = {str(i) for i in db.scalars(select(Track.id))}
        orphans = sorted(k for k in originals if k not in known)
        print(f"{len(originals)} originals in B2, {len(orphans)} without a track row; registering into '{user.username}' ({'APPLY' if args.apply else 'dry run'})")

        added = skipped = 0
        downloaded = 0
        for tid in orphans:
            obj = originals[tid][0]
            key, ext = obj["Key"], Path(obj["Key"]).suffix.lower()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"source{ext}"
                s3.download_file(settings.s3_bucket_audio, key, str(path))
                downloaded += obj["Size"]
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                with open(path, "rb") as fh:
                    tags = tags_mod.read_tags(fh)
                with open(path, "rb") as fh:
                    lyrics = tags_mod.read_lyrics(fh)
            title = (tags.get("title") or "Untitled").strip()[:200]
            artist_name = (tags.get("artist") or "Unknown Artist").strip()[:200]
            album_name = (tags.get("album") or "").strip()[:200] or None
            label = f"{tid[:8]}  {artist_name} - {title}"

            if db.scalar(select(Track).where(Track.uploader_id == user.id, Track.content_sha256 == digest)):
                print(f"skip  {label}  (identical file already in the library)")
                skipped += 1
                continue
            if dedupe.find_duplicates(db, user.id, title, artist_name, album_name):
                print(f"skip  {label}  (same song already in the library)")
                skipped += 1
                continue
            print(f"add   {label}  [{album_name or 'no album'}]  {obj['Size'] / 1e6:.1f} MB")
            added += 1
            if not args.apply:
                continue
            artist_row = artists.find_artist(db, user.id, artist_name)
            if artist_row is None:
                artist_row = Artist(name=artists.canonical_credit(artist_name), owner_user_id=user.id)
                db.add(artist_row)
                db.flush()
            album_row = None
            if album_name:
                album_row = db.scalar(select(Album).where(Album.artist_id == artist_row.id, func.lower(Album.title) == album_name.lower()))
                if album_row is None:
                    album_row = Album(artist_id=artist_row.id, title=album_name)
                    db.add(album_row)
                    db.flush()
            db.add(Track(
                id=uuid.UUID(tid), artist_id=artist_row.id, album_id=album_row.id if album_row else None, uploader_id=user.id,
                title=title, genre=tags.get("genre") or None, license=args.license, status="uploaded", source_key=key,
                content_sha256=digest, lyrics=lyrics.get("lyrics"), lyrics_synced=lyrics.get("lyrics_synced"),
            ))
            db.commit()

        print(f"\n{added} {'registered' if args.apply else 'to register'}, {skipped} skipped; downloaded {downloaded / 1e6:.1f} MB from B2")
        if not args.apply:
            print("Dry run - nothing changed (use --apply)")

        stream_orphans = sorted(k for k in streams if k not in known and k not in orphans)
        if stream_orphans:
            print(f"\n{len(stream_orphans)} streaming copies (hls/) have no track row and no original, so they have no tags to register from:")
            for k in stream_orphans:
                print(f"  hls/{k}/  {len(streams[k])} files, {sum(o['Size'] for o in streams[k]) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
