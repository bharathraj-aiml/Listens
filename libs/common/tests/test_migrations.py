"""The Alembic migration must produce exactly the schema the ORM models describe."""
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from listens_common.models import Base

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
EXPECTED = {"users", "artists", "albums", "tracks", "playlists", "playlist_tracks",
            "likes", "follows", "play_events"}


def _cfg(conn) -> Config:
    cfg = Config(str(MIGRATIONS / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["connection"] = conn
    return cfg


def test_upgrade_matches_models_and_downgrade_is_clean():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        command.upgrade(_cfg(conn), "head")
        assert EXPECTED <= set(inspect(conn).get_table_names())
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], diff
        command.downgrade(_cfg(conn), "base")
        assert not (EXPECTED & set(inspect(conn).get_table_names()))
