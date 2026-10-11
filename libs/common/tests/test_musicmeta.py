import urllib.error

from listens_common.musicmeta import MusicMeta, split_credit


def _meta(responses, sleeps=None):
    calls = []

    def fetch(url):
        calls.append(url)
        r = responses(url) if callable(responses) else responses
        if isinstance(r, Exception):
            raise r
        return r

    return MusicMeta(fetch=fetch, sleep=(sleeps.append if sleeps is not None else (lambda _s: None))), calls


def artist(mbid, name, score=100, country=None, aliases=()):
    out = {"id": mbid, "name": name, "score": score, "aliases": [{"name": a} for a in aliases]}
    if country:
        out["country"] = country
    return out


# ------------------------------------------------------------------ splitting

def test_split_credit_handles_slashes_commas_ampersands_and_feat():
    assert split_credit("A.R. Rahman/Hariharan/Mahalakshmi Iyer/Vairamuthu") == ["A.R. Rahman", "Hariharan", "Mahalakshmi Iyer", "Vairamuthu"]
    assert split_credit("Mano, S. Janaki") == ["Mano", "S. Janaki"]
    assert split_credit("Anirudh Ravichander feat. Jonita Gandhi & Vijay") == ["Anirudh Ravichander", "Jonita Gandhi", "Vijay"]
    assert split_credit("Alex") == ["Alex"]  # an x inside a name is not a separator
    assert split_credit("Mano/mano / Mano") == ["Mano"]  # no repeats


# ------------------------------------------------------------------ matching

def test_find_artist_requires_the_name_or_an_alias_to_match_not_just_a_high_score():
    meta, _ = _meta({"artists": [artist("c", "S.P.B. Charan", 100)]})
    assert meta.find_artist("SPB") is None  # a loose top hit is refused
    meta, _ = _meta({"artists": [artist("b", "S. P. Balasubrahmanyam", 100, aliases=["SPB"])]})
    assert meta.find_artist("SPB") == {"mbid": "b", "name": "S. P. Balasubrahmanyam"}


def test_find_artist_ignores_case_dots_and_spacing():
    meta, _ = _meta({"artists": [artist("a", "A. R. Rahman")]})
    assert meta.find_artist("a.r.rahman") == {"mbid": "a", "name": "A. R. Rahman"}


def test_namesakes_prefer_the_indian_artist_and_unresolvable_ambiguity_is_refused():
    hits = {"artists": [artist("us", "Karthik", 100, country="US"), artist("in", "Karthik", 100, country="IN")]}
    meta, _ = _meta(hits)
    assert meta.find_artist("Karthik")["mbid"] == "in"
    meta, _ = _meta({"artists": [artist("us", "Karthik", 100, country="US"), artist("gb", "Karthik", 100, country="GB")]})
    assert meta.find_artist("Karthik") is None


def test_weak_or_missing_matches_are_rejected():
    meta, _ = _meta({"artists": [artist("z", "Sid Sriram", 62)]})
    assert meta.find_artist("Sid Sriram") is None
    meta, _ = _meta({"artists": []})
    assert meta.find_artist("Sid Sriram") is None


# --------------------------------------------------------------- tags/similar

def test_tags_merge_tags_and_genres_lowercased_keeping_highest_count():
    meta, _ = _meta({"tags": [{"name": "Filmi", "count": 3}], "genres": [{"name": "filmi", "count": 5}, {"name": "indian pop", "count": 2}]})
    assert meta.tags("a1") == {"filmi": 5, "indian pop": 2}


def test_similar_sorted_strongest_first_and_drops_junk():
    rows = [
        {"artist_mbid": "b", "name": "Dhanush", "score": 69},
        {"artist_mbid": "a", "name": "Sid Sriram", "score": 103},
        {"artist_mbid": "", "name": "no id", "score": 99},
        {"artist_mbid": "c", "name": "zero", "score": 0},
    ]
    meta, _ = _meta(rows)
    assert [r["name"] for r in meta.similar("a1")] == ["Sid Sriram", "Dhanush"]


def test_retries_when_busy_then_succeeds_and_gives_up_on_other_errors():
    busy = urllib.error.HTTPError("u", 503, "busy", {}, None)
    state = {"n": 0}

    def responses(_url):
        state["n"] += 1
        return busy if state["n"] < 3 else {"artists": []}

    sleeps = []
    meta, calls = _meta(responses, sleeps)
    assert meta.find_artist("x") is None
    assert len(calls) == 3 and any(s >= 2 for s in sleeps)

    meta, calls = _meta(urllib.error.HTTPError("u", 404, "nope", {}, None))
    try:
        meta.find_artist("x")
        raise AssertionError("expected HTTPError")
    except urllib.error.HTTPError:
        pass
    assert len(calls) == 1


# ------------------------------------------------------------------- credits

def _world(url):
    """A tiny fake MusicBrainz + ListenBrainz."""
    people = {"A. R. Rahman": "mb-rahman", "Hariharan": "mb-hari", "Karthik": "mb-karthik"}
    if "/artist/?query=" in url:
        for name, mbid in people.items():
            if f"%22{name.replace(' ', '%20')}%22" in url:
                return {"artists": [artist(mbid, name, country="IN")]}
        return {"artists": []}
    if "inc=tags" in url:
        return {"tags": [{"name": "filmi", "count": 3}]}
    if "similar-artists" in url:
        if "mb-rahman" in url:
            return [{"artist_mbid": "mb-hari", "name": "Hariharan", "score": 300}, {"artist_mbid": "mb-x", "name": "X", "score": 150}]
        if "mb-hari" in url:
            return [{"artist_mbid": "mb-rahman", "name": "A. R. Rahman", "score": 40}, {"artist_mbid": "mb-y", "name": "Y", "score": 40}]
        return []
    raise AssertionError("unexpected url " + url)


def test_a_film_credit_is_resolved_person_by_person_skipping_unknown_lyricists():
    meta, _ = _meta(_world)
    found = meta.resolve("A.R. Rahman/Hariharan/Vairamuthu")  # "A.R." is searched as the canonical "A. R. Rahman"
    assert [p["name"] for p in found["parts"]] == ["A. R. Rahman", "Hariharan"]  # Vairamuthu is not on MusicBrainz
    assert found["mbid"] == "mb-rahman"
    assert found["tags"] == {"filmi": 3}
    # the credit's own people are never listed as neighbours; scores are scaled per person, best kept
    names = {r["name"]: r["score"] for r in found["similar"]}
    assert set(names) == {"X", "Y"} and names["X"] == 500 and names["Y"] == 1000


def test_nothing_found_returns_none_and_people_are_looked_up_only_once():
    meta, calls = _meta(_world)
    assert meta.resolve("Vairamuthu/Na.Muthukumar") is None
    meta.resolve("A.R. Rahman, Hariharan")
    before = len(calls)
    meta.resolve("Hariharan/A.R. Rahman")  # same two people again: served from the cache
    assert len(calls) == before


def test_an_act_with_an_ampersand_is_tried_whole_first():
    def responses(url):
        if "Simon%20%26%20Garfunkel" in url and "/artist/?query=" in url:
            return {"artists": [artist("sg", "Simon & Garfunkel")]}
        if "inc=tags" in url:
            return {"tags": []}
        return []

    meta, _ = _meta(responses)
    found = meta.resolve("Simon & Garfunkel")
    assert [p["name"] for p in found["parts"]] == ["Simon & Garfunkel"]
