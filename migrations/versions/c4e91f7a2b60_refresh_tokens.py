"""refresh token dengan rotasi dan deteksi pakai ulang

Revision ID: c4e91f7a2b60
Revises: a7c4e2b91d35
Create Date: 2026-10-02 18:25:12.774310

Sebelum ini, logout hanya mencatat waktu keluar. Access token yang
sudah terbit tetap valid sampai kedaluwarsa, jadi sesi yang 'sudah
logout' masih bisa diperpanjang diam-diam oleh siapa pun yang
memegangnya.

Tabel ini menyimpan sesi yang sedang berjalan, supaya refresh token
bisa dicabut. Setiap token punya jti sebagai primary key: itu penanda
token, bukan tokennya sendiri, jadi kalau tabel ini bocor orang belum
bisa langsung login.

Kolom reuse_detected_at dicatat terpisah dari revoked_reason karena
keduanya berbeda arti: revoked_reason='rotated' adalah kejadian normal,
sedangkan reuse_detected_at menandai bahwa ada orang lain yang memakai
token yang sama. Saat kolom itu terisi, seluruh sesi user dicabut.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e91f7a2b60'
down_revision = 'a7c4e2b91d35'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'refresh_tokens',
        sa.Column('jti', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_reason', sa.String(length=30), nullable=True),
        sa.Column('replaced_by', sa.String(length=36), nullable=True),
        sa.Column('reuse_detected_at', sa.DateTime(), nullable=True),
        sa.Column('user_agent', sa.String(length=200), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('jti'),
    )
    op.create_index(
        'ix_refresh_tokens_expires_at',
        'refresh_tokens',
        ['expires_at'],
        unique=False,
    )
    op.create_index(
        'ix_refresh_tokens_user_id',
        'refresh_tokens',
        ['user_id'],
        unique=False,
    )
    # Query sesi aktif selalu memfilter user_id DAN revoked_at
    # sekaligus, jadi index-nya dibuat majemuk. Dua index satu kolom
    # sudah ada di atas; yang ini yang benar-benar dipakai endpoint
    # /api/auth/sessions.
    op.create_index(
        'ix_refresh_tokens_user_active',
        'refresh_tokens',
        ['user_id', 'revoked_at'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_refresh_tokens_user_active', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_expires_at', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
