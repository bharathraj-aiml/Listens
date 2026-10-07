"""cold-start audio features + ALS latent-factor vector tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tracks") as batch:
        batch.add_column(sa.Column("tempo_bpm", sa.Float()))
        batch.add_column(sa.Column("energy", sa.Float()))

    op.create_table(
        "user_vectors",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "track_vectors",
        sa.Column("track_id", sa.Uuid(), sa.ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("track_vectors")
    op.drop_table("user_vectors")
    with op.batch_alter_table("tracks") as batch:
        batch.drop_column("energy")
        batch.drop_column("tempo_bpm")
