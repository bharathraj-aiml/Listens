"""catalogue + streaming columns, full-text search indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# 'simple' config: no stemming/stop-words, which would mangle song titles in any language.
# The app must use the *same expressions* for the planner to pick these indexes
# (see services/catalogue/app/search.py).
FTS_INDEXES = {
    "ix_fts_tracks": "tracks USING GIN (to_tsvector('simple', title || ' ' || coalesce(genre, '')))",
    "ix_fts_artists": "artists USING GIN (to_tsvector('simple', name))",
    "ix_fts_albums": "albums USING GIN (to_tsvector('simple', title))",
    "ix_fts_playlists": "playlists USING GIN (to_tsvector('simple', name || ' ' || coalesce(description, '')))",
}


def upgrade() -> None:
    with op.batch_alter_table("tracks") as batch:
        batch.add_column(sa.Column("cover_key", sa.String(255)))
        batch.add_column(sa.Column("content_sha256", sa.String(64)))
        batch.add_column(sa.Column("error", sa.Text()))
        batch.add_column(sa.Column("processing_started_at", sa.DateTime(timezone=True)))
    op.create_index("uq_tracks_uploader_sha", "tracks", ["uploader_id", "content_sha256"], unique=True)

    if op.get_bind().dialect.name == "postgresql":
        for name, target in FTS_INDEXES.items():
            op.execute(f"CREATE INDEX {name} ON {target}")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for name in FTS_INDEXES:
            op.execute(f"DROP INDEX {name}")
    op.drop_index("uq_tracks_uploader_sha", table_name="tracks")
    with op.batch_alter_table("tracks") as batch:
        batch.drop_column("processing_started_at")
        batch.drop_column("error")
        batch.drop_column("content_sha256")
        batch.drop_column("cover_key")
