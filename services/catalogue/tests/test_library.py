import uuid
from datetime import UTC, datetime, timedelta

from listens_common.models import Artist, PlayEvent, Track

from .test_catalogue import seed


def h(env):
    return env.headers


def record_play(env, user_id, track_id, occurred_at=None):
    """Play events now arrive via POST /events -> Redis Stream -> the events service (tested
    separately in services/events/), not a direct write here - so these tests insert the row
    the consumer would have written, to exercise the read side (recently-played, made-for-you)
    in isolation. Takes an explicit `occurred_at` so ordering tests aren't at the mercy of
    how many microseconds apart two real `datetime.now()` calls land."""
    with env.sessions() as db:
        db.add(PlayEvent(user_id=user_id, track_id=uuid.UUID(str(track_id)), event_type="play_start",
                         occurred_at=occurred_at or datetime.now(UTC)))
        db.commit()


def test_playlist_crud_and_visibility(env):
    r = env.client.post("/playlists", json={"name": "Road Trip", "description": "Hits", "is_public": False}, headers=h(env))
    assert r.status_code == 201, r.text
    pl = r.json()
    assert pl["track_count"] == 0 and pl["is_public"] is False and pl["is_collaborative"] is False

    # private: invisible to others
    assert env.client.get(f"/playlists/{pl['id']}", headers=env.other_headers).status_code == 404
    assert env.client.get(f"/playlists/{pl['id']}", headers=h(env)).status_code == 200

    # owner can rename; non-owner cannot
    r = env.client.patch(f"/playlists/{pl['id']}", json={"name": "Renamed"}, headers=h(env))
    assert r.status_code == 200 and r.json()["name"] == "Renamed"
    assert env.client.patch(f"/playlists/{pl['id']}", json={"name": "Nope"}, headers=env.other_headers).status_code == 403

    # make public: now visible (read-only) to others
    env.client.patch(f"/playlists/{pl['id']}", json={"is_public": True}, headers=h(env))
    assert env.client.get(f"/playlists/{pl['id']}", headers=env.other_headers).status_code == 200

    assert env.client.delete(f"/playlists/{pl['id']}", headers=env.other_headers).status_code == 403
    assert env.client.delete(f"/playlists/{pl['id']}", headers=h(env)).status_code == 204
    assert env.client.get(f"/playlists/{pl['id']}", headers=h(env)).status_code == 404


def test_add_remove_and_track_count_and_cover(env):
    tid, *_ = seed(env, "Song A", cover=True)
    r = env.client.post("/playlists", json={"name": "P"}, headers=h(env))
    pl_id = r.json()["id"]

    r = env.client.post(f"/playlists/{pl_id}/tracks", json={"track_id": tid}, headers=h(env))
    assert r.status_code == 201
    pt = r.json()
    assert pt["position"] == 0 and pt["track"]["title"] == "Song A"

    detail = env.client.get(f"/playlists/{pl_id}", headers=h(env)).json()
    assert detail["track_count"] == 1 and detail["cover_url"] is not None
    assert len(detail["tracks"]) == 1

    # non-ready tracks can't be added
    processing_id, *_ = seed(env, "Not ready", status="processing")
    assert env.client.post(f"/playlists/{pl_id}/tracks", json={"track_id": processing_id}, headers=h(env)).status_code == 404

    assert env.client.delete(f"/playlists/{pl_id}/tracks/{pt['id']}", headers=h(env)).status_code == 204
    assert env.client.get(f"/playlists/{pl_id}", headers=h(env)).json()["track_count"] == 0


def test_same_track_can_appear_twice(env):
    tid, *_ = seed(env, "Repeat")
    pl_id = env.client.post("/playlists", json={"name": "P"}, headers=h(env)).json()["id"]
    env.client.post(f"/playlists/{pl_id}/tracks", json={"track_id": tid}, headers=h(env))
    env.client.post(f"/playlists/{pl_id}/tracks", json={"track_id": tid}, headers=h(env))
    detail = env.client.get(f"/playlists/{pl_id}", headers=h(env)).json()
    assert detail["track_count"] == 2
    assert [t["position"] for t in detail["tracks"]] == [0, 1]


def test_reorder_moves_and_renumbers(env):
    ids = [seed(env, f"T{i}")[0] for i in range(4)]
    pl_id = env.client.post("/playlists", json={"name": "P"}, headers=h(env)).json()["id"]
    pt_ids = []
    for tid in ids:
        r = env.client.post(f"/playlists/{pl_id}/tracks", json={"track_id": tid}, headers=h(env))
        pt_ids.append(r.json()["id"])

    # move the first track (T0) to index 2: expect order T1, T2, T0, T3
    r = env.client.post(f"/playlists/{pl_id}/tracks/{pt_ids[0]}/move", json={"to_index": 2}, headers=h(env))
    assert r.status_code == 200
    titles = [t["track"]["title"] for t in r.json()]
    assert titles == ["T1", "T2", "T0", "T3"]
    assert [t["position"] for t in r.json()] == [0, 1, 2, 3]

    # out-of-range index clamps to the end
    r = env.client.post(f"/playlists/{pl_id}/tracks/{pt_ids[0]}/move", json={"to_index": 999}, headers=h(env))
    assert [t["track"]["title"] for t in r.json()][-1] == "T0"


def test_collaborative_allows_others_to_edit_but_not_delete(env):
    tid, *_ = seed(env, "Shared")
    pl = env.client.post("/playlists", json={"name": "P", "is_public": True, "is_collaborative": True}, headers=h(env)).json()
    r = env.client.post(f"/playlists/{pl['id']}/tracks", json={"track_id": tid}, headers=env.other_headers)
    assert r.status_code == 201, r.text
    assert r.json()["added_by"] is not None
    assert env.client.delete(f"/playlists/{pl['id']}", headers=env.other_headers).status_code == 403

    # non-collaborative, public: visible but not editable by others
    pl2 = env.client.post("/playlists", json={"name": "P2", "is_public": True, "is_collaborative": False}, headers=h(env)).json()
    assert env.client.post(f"/playlists/{pl2['id']}/tracks", json={"track_id": tid}, headers=env.other_headers).status_code == 403


def test_playlist_requires_auth_and_404_on_missing(env):
    assert env.client.post("/playlists", json={"name": "x"}).status_code == 401
    assert env.client.get(f"/playlists/{uuid.uuid4()}", headers=h(env)).status_code == 404


def test_likes_toggle_idempotent_and_listed(env):
    tid, *_ = seed(env, "Liked One")
    assert env.client.post(f"/likes/{tid}", headers=h(env)).status_code == 204
    assert env.client.post(f"/likes/{tid}", headers=h(env)).status_code == 204  # liking twice: fine
    ids = env.client.get("/likes/ids", headers=h(env)).json()
    assert ids == [tid]
    titles = [t["title"] for t in env.client.get("/likes", headers=h(env)).json()]
    assert titles == ["Liked One"]

    assert env.client.delete(f"/likes/{tid}", headers=h(env)).status_code == 204
    assert env.client.delete(f"/likes/{tid}", headers=h(env)).status_code == 204  # unliking twice: fine
    assert env.client.get("/likes/ids", headers=h(env)).json() == []

    assert env.client.post(f"/likes/{uuid.uuid4()}", headers=h(env)).status_code == 404


def test_likes_are_per_user(env):
    tid, *_ = seed(env, "Mine")
    env.client.post(f"/likes/{tid}", headers=h(env))
    assert env.client.get("/likes/ids", headers=env.other_headers).json() == []
    assert env.client.get("/likes/ids", headers=h(env)).json() == [tid]


def test_follow_artist_toggle_and_reflected_on_artist_page(env):
    tid, art_id, _ = seed(env, "Song", artist="Band X")
    a = env.client.get(f"/artists/{art_id}", headers=h(env)).json()
    assert a["followed"] is False

    assert env.client.post(f"/follows/artists/{art_id}", headers=h(env)).status_code == 204
    a = env.client.get(f"/artists/{art_id}", headers=h(env)).json()
    assert a["followed"] is True
    assert [x["name"] for x in env.client.get("/follows/artists", headers=h(env)).json()] == ["Band X"]

    # not reflected for another user
    assert env.client.get(f"/artists/{art_id}", headers=env.other_headers).json()["followed"] is False

    assert env.client.delete(f"/follows/artists/{art_id}", headers=h(env)).status_code == 204
    assert env.client.get(f"/artists/{art_id}", headers=h(env)).json()["followed"] is False
    assert env.client.post(f"/follows/artists/{uuid.uuid4()}", headers=h(env)).status_code == 404


def test_follow_user_cannot_follow_self(env):
    assert env.client.post(f"/follows/users/{env.user_id}", headers=h(env)).status_code == 400
    assert env.client.post(f"/follows/users/{env.other_id}", headers=h(env)).status_code == 204
    names = [u["username"] for u in env.client.get("/follows/users", headers=h(env)).json()]
    assert names == ["b"]
    assert env.client.delete(f"/follows/users/{env.other_id}", headers=h(env)).status_code == 204
    assert env.client.get("/follows/users", headers=h(env)).json() == []


def test_recently_played_ordering(env):
    t1, *_ = seed(env, "Old play")
    t2, *_ = seed(env, "New play")
    base = datetime.now(UTC)
    record_play(env, env.user_id, t1, base)
    record_play(env, env.user_id, t2, base + timedelta(seconds=1))
    # replaying t1 should bump it to the front (most-recent wins, not first-played)
    record_play(env, env.user_id, t1, base + timedelta(seconds=2))

    titles = [t["title"] for t in env.client.get("/home/recently-played", headers=h(env)).json()]
    assert titles == ["Old play", "New play"]

    # another user's plays don't show up for this user
    assert env.client.get("/home/recently-played", headers=env.other_headers).json() == []


def record_event(env, user_id, track_id, kind, at, position_ms=None):
    with env.sessions() as db:
        db.add(PlayEvent(user_id=user_id, track_id=uuid.UUID(str(track_id)), event_type=kind, position_ms=position_ms, occurred_at=at))
        db.commit()


def recent(env):
    return env.client.get("/home/recently-played", headers=h(env)).json()


def test_recently_played_ignores_songs_skipped_within_seconds(env):
    heard, *_ = seed(env, "Listened to")
    tapped, *_ = seed(env, "Tapped through")
    base = datetime.now(UTC)
    record_event(env, env.user_id, heard, "play_start", base)
    record_event(env, env.user_id, heard, "skip", base + timedelta(seconds=40), position_ms=40_000)
    record_event(env, env.user_id, tapped, "play_start", base + timedelta(seconds=41))
    record_event(env, env.user_id, tapped, "skip", base + timedelta(seconds=43), position_ms=2_000)
    assert [t["title"] for t in recent(env)] == ["Listened to"]


def test_a_quick_skip_does_not_erase_an_earlier_real_listen_of_the_same_song(env):
    song, *_ = seed(env, "Replayed")
    base = datetime.now(UTC)
    record_event(env, env.user_id, song, "play_start", base)
    record_event(env, env.user_id, song, "play_end", base + timedelta(minutes=3))
    record_event(env, env.user_id, song, "play_start", base + timedelta(minutes=5))
    record_event(env, env.user_id, song, "skip", base + timedelta(minutes=5, seconds=1), position_ms=900)
    out = recent(env)
    assert [t["title"] for t in out] == ["Replayed"]
    assert out[0]["played_at"].startswith(base.strftime("%Y-%m-%dT%H:%M"))  # the real listen, not the tap-through


def test_the_song_playing_right_now_counts_and_carries_when_it_was_played(env):
    song, *_ = seed(env, "Now playing")
    record_event(env, env.user_id, song, "play_start", datetime.now(UTC))  # no end event yet
    out = recent(env)
    assert [t["title"] for t in out] == ["Now playing"] and out[0]["played_at"]


def test_a_skip_without_a_position_still_counts_as_a_listen(env):
    song, *_ = seed(env, "Unknown position")
    base = datetime.now(UTC)
    record_event(env, env.user_id, song, "play_start", base)
    record_event(env, env.user_id, song, "skip", base + timedelta(seconds=1))
    assert [t["title"] for t in recent(env)] == ["Unknown position"]


def test_recently_played_hides_songs_that_are_not_ready(env):
    ready, *_ = seed(env, "Ready one")
    broken, *_ = seed(env, "Broken one", status="failed")
    base = datetime.now(UTC)
    record_play(env, env.user_id, ready, base)
    record_play(env, env.user_id, broken, base + timedelta(seconds=1))
    assert [t["title"] for t in recent(env)] == ["Ready one"]


def test_made_for_you_prefers_liked_and_played_artists_and_excludes_already_played(env):
    liked_track, liked_artist, _ = seed(env, "Liked artist song", artist="Liked Co")
    other_track, _, _ = seed(env, "Other song", artist="Liked Co")  # same artist, not yet played
    unrelated, *_ = seed(env, "Unrelated", artist="Stranger Co")

    env.client.post(f"/likes/{liked_track}", headers=h(env))
    record_play(env, env.user_id, liked_track)  # already played -> excluded

    picks = env.client.get("/home/made-for-you", headers=h(env)).json()
    titles = {p["title"] for p in picks}
    assert "Other song" in titles  # from a liked artist, not yet played
    assert "Liked artist song" not in titles  # already played, excluded


def test_made_for_you_falls_back_to_new_releases_for_fresh_user(env):
    seed(env, "Fresh A")
    seed(env, "Fresh B")
    picks = env.client.get("/home/made-for-you", headers=h(env)).json()
    assert len(picks) == 2  # no listening history at all -> falls back, never empty
