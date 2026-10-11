#!/usr/bin/env python3
"""Enrich the live library with the data the recommender uses beyond play history.

  artists  For every artist, look it up on MusicBrainz and store its tags plus ListenBrainz's
           "similar artists" (collaborative filtering over millions of real listening sessions).
           This is what lets "made for you" / "similar tracks" understand that, say, Anirudh,
           Sid Sriram and Santhosh Narayanan sit together, with no play history needed.
  audio    Re-analyse tracks that have no audio fingerprint yet (tracks uploaded before the
           fingerprint existed): downloads each original from B2 and stores tempo, loudness and
           the timbre/harmony vector. New uploads get this automatically from the worker.

Both are safe to re-run: finished items are skipped (use --refresh to redo artists). Dry run by
default; nothing is written without --apply. Needs DATABASE_URL and S3_* from the environment.

    set -a; source .env.prod; set +a; export PYTHONUTF8=1
    .venv/Scripts/python scripts/enrich_library.py                       # dry run: artists
    .venv/Scripts/python scripts/enrich_library.py --apply              # fetch + save artist data
    .venv/Scripts/python scripts/enrich_library.py --audio --apply      # also back-fill audio fingerprints

MusicBrainz allows about one request per second; an artist costs three requests, so ~4 s each.
"""
import argparse
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "worker"))  # the worker's `app` package (audio_features)

from sqlalchemy import select  # noqa: E402

from app import audio_features  # noqa: E402
from listens_common.config import get_settings  # noqa: E402
from listens_common.db import get_sessionmaker  # noqa: E402
from listens_common.models import Artist, ArtistMeta, Track  # noqa: E402
from listens_common.musicmeta import MusicMeta  # noqa: E402
from listens_common.storage import get_s3  # noqa: E402


def enrich_artists(db, apply: bool, refresh: bool, limit: int | None) -> None:
    meta = MusicMeta()
    done = {m.artist_id for m in db.scalars(select(ArtistMeta))}
    artists = [a for a in db.scalars(select(Artist).order_by(Artist.name)) if refresh or a.id not in done]
    if limit:
        artists = artists[:limit]
    print(f"{len(artists)} artist(s) to look up" + ("" if apply else "  [dry run: nothing is saved]"))

    matched = 0
    for n, artist in enumerate(artists, 1):
        try:
            found = meta.resolve(artist.name)
        except Exception as e:  # noqa: BLE001 - one bad lookup must not stop the run
            print(f"[{n}/{len(artists)}] {artist.name}: lookup failed ({e}), skipped")
            continue
        if not found:
            print(f"[{n}/{len(artists)}] {artist.name}: no named artist found on MusicBrainz, skipped")
            continue
        matched += 1
        who = ", ".join(p["name"] for p in found["parts"])
        top = ", ".join(s["name"] for s in found["similar"][:4]) or "none found"
        print(f"[{n}/{len(artists)}] {artist.name} -> {who}: {len(found['tags'])} tags, {len(found['similar'])} similar (top: {top})")
        if not apply:
            continue
        # a joint credit keeps each named person's id as a {"self": true} entry so the recommender
        # can tell that "A.R. Rahman/Hariharan" and a "Hariharan" track are the same person
        similar = [*found["similar"], *({"mbid": p["mbid"], "name": p["name"], "score": 0, "self": True} for p in found["parts"])]
        row = db.get(ArtistMeta, artist.id) or ArtistMeta(artist_id=artist.id)
        row.mbid, row.tags, row.similar, row.fetched_at = found["mbid"], found["tags"], similar, datetime.now(UTC)
        db.merge(row)
        db.commit()
    print(f"matched {matched} of {len(artists)} artist credits")


def backfill_audio(db, apply: bool, limit: int | None) -> None:
    settings = get_settings()
    s3 = get_s3()
    tracks = list(db.scalars(
        select(Track).where(Track.status == "ready", Track.audio_vector.is_(None), Track.source_key.is_not(None))
        .order_by(Track.created_at)
    ).unique())
    if limit:
        tracks = tracks[:limit]
    print(f"{len(tracks)} track(s) without an audio fingerprint" + ("" if apply else "  [dry run: nothing is saved]"))
    if not apply:
        return

    with tempfile.TemporaryDirectory() as tmp:
        for n, track in enumerate(tracks, 1):
            path = Path(tmp) / f"{track.id}{Path(track.source_key).suffix}"
            try:
                s3.download_file(settings.s3_bucket_audio, track.source_key, str(path))
            except Exception as e:  # noqa: BLE001
                print(f"[{n}/{len(tracks)}] {track.title}: original not available ({e}), skipped")
                continue
            features = audio_features.extract_features(path)
            path.unlink(missing_ok=True)
            if not features.get("vector"):
                print(f"[{n}/{len(tracks)}] {track.title}: analysis failed, skipped")
                continue
            track.tempo_bpm = features.get("tempo_bpm", track.tempo_bpm)
            track.energy = features.get("energy", track.energy)
            track.audio_vector = features["vector"]
            db.commit()
            print(f"[{n}/{len(tracks)}] {track.title}: fingerprint saved")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write to the database (default is a dry run)")
    ap.add_argument("--audio", action="store_true", help="also back-fill audio fingerprints for existing tracks")
    ap.add_argument("--refresh", action="store_true", help="re-fetch artists that already have data")
    ap.add_argument("--limit", type=int, help="process at most N artists / tracks")
    args = ap.parse_args()

    with get_sessionmaker()() as db:
        enrich_artists(db, args.apply, args.refresh, args.limit)
        if args.audio:
            backfill_audio(db, args.apply, args.limit)


if __name__ == "__main__":
    main()
