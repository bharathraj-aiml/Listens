import urllib.error

from listens_common.musicmeta import MusicMeta


def _meta(responses, sleeps=None):
    calls = []

    def fetch(url):
        calls.append(url)
        r = responses(url) if callable(responses) else responses
        if isinstance(r, Exception):
            raise r
        return r

    return MusicMeta(fetch=fetch, sleep=(sleeps.append if sleeps is not None else (lambda _s: None))), calls


def test_find_artist_prefers_exact_confident_match():
    hits = {"artists": [
        {"id": "x1", "name": "Anirudh", "score": 95},
        {"id": "a1", "name": "Anirudh Ravichander", "score": 100},
    ]}
    meta, _ = _meta(hits)
    assert meta.find_artist("anirudh ravichander") == {"mbid": "a1", "name": "Anirudh Ravichander"}


def test_find_artist_rejects_weak_matches():
    meta, _ = _meta({"artists": [{"id": "z", "name": "Something Else", "score": 62}]})
    assert meta.find_artist("Sid Sriram") is None
    meta, _ = _meta({"artists": []})
    assert meta.find_artist("Sid Sriram") is None


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


def test_joint_credit_falls_back_to_the_first_named_artist():
    def responses(url):
        if "Vijay" in url:  # the full joint credit finds nothing
            return {"artists": []}
        return {"artists": [{"id": "a1", "name": "Anirudh Ravichander", "score": 100}]}

    meta, calls = _meta(responses)
    assert meta.find_artist("Anirudh Ravichander, Vijay") == {"mbid": "a1", "name": "Anirudh Ravichander"}
    assert len(calls) == 2


def test_names_containing_x_are_not_split_and_plain_names_are_searched_once():
    meta, calls = _meta({"artists": []})
    assert meta.find_artist("Alex") is None
    assert len(calls) == 1  # no bogus "Ale" retry
    meta, calls = _meta({"artists": []})
    meta.find_artist("S. P. Balasubrahmanyam & S. Janaki")
    assert any("Balasubrahmanyam" in c and "Janaki" not in c for c in calls[1:])
