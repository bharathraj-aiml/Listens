"""Open music data used to relate artists to each other: MusicBrainz (ids, tags) and ListenBrainz
Labs "similar artists", which is collaborative filtering over millions of real listening sessions.
Neither needs an API key. MusicBrainz asks for a descriptive User-Agent and at most ~1 request per
second, and both services answer 429/503 when busy, so every call is throttled and retried.

Tamil film credits put the composer, the singers and the lyricist in one string
("A.R. Rahman/Hariharan/Mahalakshmi Iyer/Vairamuthu"), so `resolve` splits a credit into people,
looks each one up once (cached), skips the ones MusicBrainz does not know (most lyricists) and
merges what it finds into one record for the credit.

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

from . import tamil_seed

USER_AGENT = "ShadowListens/0.1 (self-hosted music app; shadow2306m@gmail.com)"
MB_BASE = "https://musicbrainz.org/ws/2"
LB_SIMILAR = (
    "https://labs.api.listenbrainz.org/similar-artists/json"
    "?algorithm=session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30&artist_mbids="
)
MIN_INTERVAL_S = 1.2
RETRY_WAITS_S = (2, 5, 12, 25)
PREFERRED_COUNTRY = "IN"  # several artists share a name ("Karthik", "Mano"); this library is Indian music

_SEPARATORS = re.compile(r"\s*(?:/|,|;|&|\bfeat\b\.?|\bft\b\.?|\bx\b| and )\s*", re.I)
_DOT_BEFORE_LETTER = re.compile(r"\.(?=[A-Za-z])")


def split_credit(credit: str) -> list[str]:
    """"A.R. Rahman/Hariharan, Vairamuthu" -> ["A.R. Rahman", "Hariharan", "Vairamuthu"] (order kept, no repeats)."""
    seen: dict[str, str] = {}
    for part in _SEPARATORS.split(credit):
        part = part.strip()
        if part:
            seen.setdefault(part.casefold(), part)
    return list(seen.values())


def _plain(name: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", name.casefold())


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
        self._people: dict[str, dict | None] = {}
        self._tags: dict[str, dict[str, int]] = {}
        self._similar: dict[str, list[dict]] = {}

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
        """The MusicBrainz artist whose name or alias IS `name` (ignoring case, dots and spaces), or
        None. Loose matches are refused on purpose: searching "SPB" returns "S.P.B. Charan" first.
        When several artists share the name, the Indian one is taken; if none is Indian and there
        are several, it is ambiguous, so None."""
        query = urllib.parse.quote(f'artist:"{name}"')
        hits = self._get(f"{MB_BASE}/artist/?query={query}&fmt=json&limit=10").get("artists", [])
        wanted = _plain(name)
        exact = [
            h for h in hits
            if h.get("score", 0) >= 85
            and (_plain(h.get("name", "")) == wanted or any(_plain(a.get("name", "")) == wanted for a in h.get("aliases", [])))
        ]
        if not exact:
            return None
        indian = [h for h in exact if h.get("country") == PREFERRED_COUNTRY or (h.get("area") or {}).get("name") == "India"]
        chosen = indian[0] if indian else (exact[0] if len(exact) == 1 else None)
        return {"mbid": chosen["id"], "name": chosen["name"]} if chosen else None

    def tags(self, mbid: str) -> dict[str, int]:
        """MusicBrainz folksonomy tags and curated genres, merged: {"filmi": 3, "indian pop": 3}."""
        if mbid not in self._tags:
            info = self._get(f"{MB_BASE}/artist/{mbid}?inc=tags+genres&fmt=json")
            out: dict[str, int] = {}
            for item in (*info.get("tags", []), *info.get("genres", [])):
                name = str(item.get("name", "")).strip().casefold()
                if name:
                    out[name] = max(out.get(name, 0), int(item.get("count", 1)))
            self._tags[mbid] = out
        return self._tags[mbid]

    def similar(self, mbid: str, limit: int = 50) -> list[dict]:
        """ListenBrainz's most co-listened artists: [{"mbid", "name", "score"}], strongest first."""
        if mbid not in self._similar:
            rows = self._get(LB_SIMILAR + mbid)
            rows = rows if isinstance(rows, list) else []
            out = [{"mbid": r["artist_mbid"], "name": r.get("name", ""), "score": int(r.get("score", 0))}
                   for r in rows if r.get("artist_mbid") and r.get("score", 0) > 0]
            self._similar[mbid] = sorted(out, key=lambda r: -r["score"])
        return self._similar[mbid][:limit]

    def person(self, name: str) -> dict | None:
        """One named artist, cached. Known Tamil artists are searched under their canonical MusicBrainz
        spelling ("A.R. Rahman" -> "A. R. Rahman"); otherwise dotted initials are spaced out as a retry."""
        key = _plain(name)
        if key not in self._people:
            canonical = tamil_seed.lookup(name)
            tries = [canonical.name] if canonical else []
            tries += [name, _DOT_BEFORE_LETTER.sub(". ", name)]
            hit = None
            for attempt in dict.fromkeys(tries):
                hit = self.find_artist(attempt)
                if hit:
                    break
            self._people[key] = hit
        return self._people[key]

    def resolve(self, credit: str) -> dict | None:
        """Everything known about an artist credit, or None if no named person is found.

        {"mbid": first person's id, "parts": [{"mbid", "name"}...], "tags": {...}, "similar": [...]}
        `similar` merges each person's list (each scaled so its strongest is 1000) keeping the best
        score per artist, and leaves out the credit's own people."""
        parts = split_credit(credit)
        joint = len(parts) > 1 and ("/" in credit or "," in credit or ";" in credit)
        people: list[dict] = []
        if not joint:
            whole = self.person(credit)  # "Simon & Garfunkel" is one act, not two people
            if whole:
                people = [whole]
        if not people:
            people = [p for part in parts if (p := self.person(part))]
        people = list({p["mbid"]: p for p in people}.values())
        if not people:
            return None

        own = {p["mbid"] for p in people}
        tags: dict[str, int] = {}
        merged: dict[str, dict] = {}
        for p in people:
            for t, c in self.tags(p["mbid"]).items():
                tags[t] = max(tags.get(t, 0), c)
            rows = self.similar(p["mbid"])
            top = max((r["score"] for r in rows), default=0)
            for r in rows:
                if r["mbid"] in own or not top:
                    continue
                score = round(1000 * r["score"] / top)
                if score > merged.get(r["mbid"], {}).get("score", 0):
                    merged[r["mbid"]] = {"mbid": r["mbid"], "name": r["name"], "score": score}
        similar = sorted(merged.values(), key=lambda r: -r["score"])[:100]
        return {"mbid": people[0]["mbid"], "parts": people, "tags": tags, "similar": similar}
