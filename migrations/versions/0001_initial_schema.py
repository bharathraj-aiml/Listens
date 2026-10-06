"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _ts(name: str = "created_at") -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("bio", sa.Text()),
        sa.Column("avatar_key", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        _ts(),
        _ts("updated_at"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    op.create_table(
        "artists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("bio", sa.Text()),
        sa.Column("image_key", sa.String(255)),
        sa.Column("owner_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        _ts(),
    )
    op.create_index("ix_artists_name", "artists", ["name"])

    op.create_table(
        "albums",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("artist_id", sa.Uuid(), sa.ForeignKey("artists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("cover_key", sa.String(255)),
        sa.Column("release_date", sa.Date()),
        _ts(),
    )
    op.create_index("ix_albums_artist_id", "albums", ["artist_id"])

    op.create_table(
        "tracks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("artist_id", sa.Uuid(), sa.ForeignKey("artists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("album_id", sa.Uuid(), sa.ForeignKey("albums.id", ondelete="SET NULL")),
        sa.Column("uploader_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("genre", sa.String(60)),
        sa.Column("license", sa.String(100)),
        sa.Column("status", sa.String(16), nullable=False, server_default="uploaded"),
        sa.Column("source_key", sa.String(255)),
        sa.Column("hls_prefix", sa.String(255)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("source_bitrate_kbps", sa.Integer()),
        _ts(),
        sa.CheckConstraint("status IN ('uploaded','processing','ready','failed')", name="ck_tracks_status"),
    )
    op.create_index("ix_tracks_artist_id", "tracks", ["artist_id"])
    op.create_index("ix_tracks_album_id", "tracks", ["album_id"])
    op.create_index("ix_tracks_status_created", "tracks", ["status", "created_at"])

    op.create_table(
        "playlists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("cover_key", sa.String(255)),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_collaborative", sa.Boolean(), nullable=False, server_default="0"),
        _ts(),
        _ts("updated_at"),
    )
    op.create_index("ix_playlists_owner_id", "playlists", ["owner_id"])

    op.create_table(
        "playlist_tracks",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("playlist_id", sa.Uuid(), sa.ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_id", sa.Uuid(), sa.ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("added_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        _ts("added_at"),
    )
    op.create_index("ix_playlist_tracks_playlist_pos", "playlist_tracks", ["playlist_id", "position"])

    op.create_table(
        "likes",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("track_id", sa.Uuid(), sa.ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
        _ts(),
    )
    op.create_index("ix_likes_track_id", "likes", ["track_id"])

    op.create_table(
        "follows",
        sa.Column("follower_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("target_type", sa.String(8), primary_key=True),
        sa.Column("target_id", sa.Uuid(), primary_key=True),
        _ts(),
        sa.CheckConstraint("target_type IN ('user','artist')", name="ck_follows_target_type"),
    )
    op.create_index("ix_follows_target", "follows", ["target_type", "target_id"])

    op.create_table(
        "play_events",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("ms_played", sa.Integer()),
        sa.Column("position_ms", sa.Integer()),
        sa.Column("reason", sa.String(40)),
        sa.Column("session_id", sa.String(64)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        _ts(),
        sa.CheckConstraint(
            "event_type IN ('play_start','play_end','skip','like','add_to_playlist')",
            name="ck_play_events_type",
        ),
    )
    op.create_index("ix_play_events_user_time", "play_events", ["user_id", "occurred_at"])
    op.create_index("ix_play_events_track_time", "play_events", ["track_id", "occurred_at"])


def downgrade() -> None:
    for table in (
        "play_events", "follows", "likes", "playlist_tracks",
        "playlists", "tracks", "albums", "artists", "users",
    ):
        op.drop_table(table)
