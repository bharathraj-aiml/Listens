#!/usr/bin/env python3
"""Remove extra copies of songs whose title or credit differs only by a spelling change, and their files in B2.

scripts/dedupe_library.py catches the same song uploaded twice with the SAME title and credit. Real libraries also
have "Veettu Thottathil" / "Veetu Thotathil", "Aaruyire" / "Aaruyire (From "Guru")", a credit with or without a
featured name, and one song on two albums. This groups songs that are probably the same recording
(listens_common.dedupe.likely_same_song: similar title once spelling noise is stripped, the same version so a slowed
or live edit is never merged, compatible length, and a shared artist or album), keeps the best copy of each group and
deletes the rest, including their files in B2 (originals, streaming copies, cover). Likes, playlist entries and play
history move to the kept copy. Albums and artists left with nothing are removed too.

Keeper: a processed ('ready') copy over a waiting one, then the highest source bitrate, then the fullest credit
(most artists), then the oldest upload. Dry run by default: prints each group and what would be deleted.

    set -a; source .env.prod; set +a
    .venv/Scripts/python scripts/dedupe_similar.py            # dry run
    .venv/Scripts/python scripts/dedupe_similar.py --apply

Deleting from B2 cannot be undone. Do not run it while the transcode queue is processing the same songs.
"""
import argparse
import sys

from sqlalchemy import func, select

from listens_common import dedupe
from listens_common.config import get_settings
from listens_common.db import get_sessionmaker
from listens_common.models import Album, Artist, ArtistMeta, Follow, Track, TrackArtist
from listens_common.storage import get_s3


def size_of(s3, bucket: str, prefix: str) -> int:
    total, token = 0, None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        page = s3.list_objects_v2(**kw)
        total += sum(o["Size"] for o in page.get("Contents", []))
        if not page.get("IsTruncated"):
            return total
        token = page["NextContinuationToken"]


def keeper_of(group: list[Track]) -> Track:
    return min(group, key=lambda t: (t.status != "ready", -(t.source_bitrate_kbps or 0), -len(t.artists or [t.artist]), t.created_at, str(t.id)))


def describe(t: Track) -> str:
    dur = f"{t.duration_ms / 1000:.0f}s" if t.duration_ms else "?s"
    album = t.album.title if t.album else "-"
    return f"{t.status[:5]:5s} {dur:>5s} {str(t.source_bitrate_kbps or '?'):>4s}k  {t.title[:44]:44s} | {dedupe_credit(t)[:42]:42s} | {album[:28]}"


def dedupe_credit(t: Track) -> str:
    return ", ".join(a.name for a in (t.artists or [t.artist]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="delete the extra copies (default: dry run)")
    args = ap.parse_args()

    settings, s3, sessions = get_settings(), get_s3(), get_sessionmaker()
    db = sessions()
    tracks = list(db.scalars(select(Track).where(Track.status.in_(["uploaded", "processing", "ready"])).order_by(Track.created_at)).unique())
    groups = dedupe.similar_groups([dedupe.SongInfo.of(t) for t in tracks])
    print(f"{len(tracks)} songs; {len(groups)} groups of the same song\n")

    plan = []  # (keeper, [losers])
    for g in groups:
        members = [tracks[i] for i in g]
        if any(t.status == "processing" for t in members):
            print("skip (a copy is being processed right now):", members[0].title)
            continue
        keep = keeper_of(members)
        losers = [t for t in members if t.id != keep.id]
        plan.append((keep, losers))
        print("---")
        print("  KEEP  " + describe(keep))
        for t in losers:
            print("  drop  " + describe(t))

    losers_all = [t for _, ls in plan for t in ls]
    freed = sum(size_of(s3, settings.s3_bucket_audio, f"originals/{t.id}/") + size_of(s3, settings.s3_bucket_audio, f"hls/{t.id}/") for t in losers_all)
    print(f"\n{len(losers_all)} copies would be deleted, freeing about {freed / 1e6:.0f} MB in B2")
    if not args.apply:
        print("dry run - nothing deleted (use --apply)")
        return

    for keep, losers in plan:
        for t in losers:
            print(f"deleting {t.title[:50]} ({str(t.id)[:8]})", flush=True)
            dedupe.remove_track(db, s3, settings, t, keep=keep)

    # albums and artists nothing refers to any more
    empty_albums = db.scalars(select(Album).where(~select(Track.id).where(Track.album_id == Album.id).exists())).unique().all()
    for al in empty_albums:
        db.delete(al)
    db.flush()
    gone = 0
    for a in db.scalars(select(Artist)).all():
        used = db.scalar(select(func.count()).select_from(Track).where(Track.artist_id == a.id)) or db.scalar(
            select(func.count()).select_from(TrackArtist).where(TrackArtist.artist_id == a.id)
        ) or db.scalar(select(func.count()).select_from(Album).where(Album.artist_id == a.id)) or db.scalar(
            select(func.count()).select_from(Follow).where(Follow.target_type == "artist", Follow.target_id == a.id)
        )
        if not used and not a.bio and not a.image_key:
            db.query(ArtistMeta).filter(ArtistMeta.artist_id == a.id).delete()
            db.delete(a)
            gone += 1
    db.commit()
    print(f"\ndone: {len(losers_all)} copies deleted, {len(empty_albums)} empty albums and {gone} unused artists removed")


if __name__ == "__main__":
    sys.exit(main())
