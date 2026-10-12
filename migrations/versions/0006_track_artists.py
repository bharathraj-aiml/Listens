"""track_artists: a song can credit several artists

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12

Additive only. tracks.artist_id stays as the primary artist, so code that predates this table keeps working;
scripts/split_artist_credits.py fills the table from the existing "A, B, C" credit rows.
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "track_artists",
        sa.Column("track_id", sa.Uuid(), sa.ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("artist_id", sa.Uuid(), sa.ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_track_artists_artist_id", "track_artists", ["artist_id"])


def downgrade() -> None:
    op.drop_index("ix_track_artists_artist_id", table_name="track_artists")
    op.drop_table("track_artists")
