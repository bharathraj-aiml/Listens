from datetime import UTC, datetime

import pytest

from listens_common import testing
from listens_common.models import Artist, Like, PlayEvent, Playlist, PlaylistTrack, Track, User


@pytest.fixture
def env():
    sessions = testing.sqlite_sessionmaker()

    class Env:
        sessions_ = sessions

        def user(self):
            with self.sessions_() as db:
                u = User(email=f"{next(_seq)}@x.io", username=f"u{next(_seq)}", password_hash="x", display_name="U")
                db.add(u)
                db.commit()
                return u.id

        def track(self, artist_id=None, duration_ms=180_000):
            with self.sessions_() as db:
                a_id = artist_id
                if a_id is None:
                    a = Artist(name=f"artist-{next(_seq)}")
                    db.add(a)
                    db.flush()
                    a_id = a.id
                t = Track(artist_id=a_id, title=f"track-{next(_seq)}", status="ready", duration_ms=duration_ms)
                db.add(t)
                db.commit()
                return t.id

        def artist(self):
            with self.sessions_() as db:
                a = Artist(name=f"artist-{next(_seq)}")
                db.add(a)
                db.commit()
                return a.id

        def play(self, user_id, track_id, event_type, *, ms_played=None, position_ms=None):
            with self.sessions_() as db:
                db.add(PlayEvent(
                    user_id=user_id, track_id=track_id, event_type=event_type,
                    ms_played=ms_played, position_ms=position_ms, occurred_at=datetime.now(UTC),
                ))
                db.commit()

        def like(self, user_id, track_id):
            with self.sessions_() as db:
                db.add(Like(user_id=user_id, track_id=track_id))
                db.commit()

        def add_to_playlist(self, user_id, track_id):
            with self.sessions_() as db:
                p = Playlist(owner_id=user_id, name="p")
                db.add(p)
                db.flush()
                db.add(PlaylistTrack(playlist_id=p.id, track_id=track_id, position=0, added_by=user_id))
                db.commit()

    return Env()


def _counter():
    n = 0
    while True:
        n += 1
        yield n


_seq = _counter()
