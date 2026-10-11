"""Open music data used to relate artists to each other: MusicBrainz (ids, tags) and ListenBrainz
Labs "similar artists", which is collaborative filtering over millions of real listening sessions.
Neither needs an API key. MusicBrainz asks for a descriptive User-Agent and at most ~1 request per
second, and both services answer 429/503 when busy, so every call is throttled and retried.

Standard library only (urllib), so the enrichment script needs nothing beyond the project venv.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

USER_AGENT = "ShadowListens/0.1 (self-hosted music app; shadow2306m@gmail.com)"
MB_BASE = "https://musicbrainz.org/ws/2"
LB_SIMILAR = (
    "https://labs.api.listenbrainz.org/similar-artists/json"
    "?algorithm=session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30&artist_mbids="
)
MIN_INTERVAL_S = 1.2
RETRY_WAITS_S = (2, 5, 12, 25)


def _http_get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


class MusicMeta:
    """`fetch` is injectable so tests never touch the network."""

    def __init__(self, fetch: Callable[[str], object] = _http_get_json, sleep: Callable[[float], None] = time.sleep):
        self._fetch = fetch
        self._sleep = sleep
        self._last_call = 0.0

    def _get(self, url: str):
        for wait in (*RETRY_WAITS_S, None):
            gap = MIN_INTERVAL_S - (time.monotonic() - self._last_call)
            if gap > 0:
                self._sleep(gap)
            self._last_call = time.monotonic()
            try:
                return self._fetch(url)
            except urllib.error.HTTPError as e:
                if e.code not in (429, 503) or wait is None:
                    raise
                self._sleep(wait)

    def find_artist(self, name: str) -> dict | None:
        """Best MusicBrainz match for an artist name, or None if there is no confident one. A joint
        credit ("Anirudh Ravichander, Vijay", "A. R. Rahman feat. Shweta Mohan") that matches
        nothing is retried with its first-named artist."""
        found = self._search(name)
        first = re.split(r"\s*(?:,|&|;|\bfeat\.?|\bft\.?|\bx\b| and )\s*", name, maxsplit=1, flags=re.I)[0].strip()
        return found or (self._search(first) if first and first.casefold() != name.casefold() else None)

    def _search(self, name: str) -> dict | None:
        query = urllib.parse.quote(f'artist:"{name}"')
        hits = self._get(f"{MB_BASE}/artist/?query={query}&fmt=json&limit=5").get("artists", [])
        wanted = name.casefold().strip()
        for hit in hits:
            if hit.get("score", 0) >= 90 and hit.get("name", "").casefold().strip() == wanted:
                return {"mbid": hit["id"], "name": hit["name"]}
        return {"mbid": hits[0]["id"], "name": hits[0]["name"]} if hits and hits[0].get("score", 0) == 100 else None

    def tags(self, mbid: str) -> dict[str, int]:
        """MusicBrainz folksonomy tags and curated genres, merged: {"filmi": 3, "indian pop": 3}."""
        info = self._get(f"{MB_BASE}/artist/{mbid}?inc=tags+genres&fmt=json")
        out: dict[str, int] = {}
        for item in (*info.get("tags", []), *info.get("genres", [])):
            name = str(item.get("name", "")).strip().casefold()
            if name:
                out[name] = max(out.get(name, 0), int(item.get("count", 1)))
        return out

    def similar(self, mbid: str, limit: int = 50) -> list[dict]:
        """ListenBrainz's most co-listened artists: [{"mbid", "name", "score"}], strongest first."""
        rows = self._get(LB_SIMILAR + mbid)
        rows = rows if isinstance(rows, list) else []
        out = [{"mbid": r["artist_mbid"], "name": r.get("name", ""), "score": int(r.get("score", 0))}
               for r in rows if r.get("artist_mbid") and r.get("score", 0) > 0]
        return sorted(out, key=lambda r: -r["score"])[:limit]
