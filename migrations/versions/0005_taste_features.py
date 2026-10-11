"""audio fingerprint vector on tracks + open-data artist context table

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tracks") as batch:
        batch.add_column(sa.Column("audio_vector", sa.JSON()))

    op.create_table(
        "artist_meta",
        sa.Column("artist_id", sa.Uuid(), sa.ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mbid", sa.String(36)),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("similar", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("artist_meta")
    with op.batch_alter_table("tracks") as batch:
        batch.drop_column("audio_vector")
