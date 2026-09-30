"""Konfigurasi aplikasi.

Semua nilai bisa diubah lewat environment variable, tanpa menyentuh kode.
Listanya ada di README. Yang paling penting:

  DATABASE_URL     SQLite (default) atau PostgreSQL
  SECRET_KEY       Kunci enkripsi JWT
  FLASK_DEBUG      1 = mode development
"""

import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _database_url():
    """Pilih database dari environment, default ke SQLite.

    Format PostgreSQL:
        postgresql+psycopg://user:password@localhost:5432/nama_db
    Format SQLite:
        sqlite:///database/campusflow.db
    """
    url = os.environ.get('DATABASE_URL')
    if url:
        return url

    # Default development: file SQLite di folder database/.
    # Path absolut dipakai supaya tidak salah relatif terhadap folder
    # kerja terminal.
    default = os.path.join(BASE_DIR, 'database', 'campusflow.db')
    os.makedirs(os.path.dirname(default), exist_ok=True)
    return f'sqlite:///{default}'


class Config:
    SECRET_KEY = os.environ.get(
        'SECRET_KEY', 'dev-secret-change-this-in-production'
    )
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.environ.get('JWT_EXPIRES_HOURS', '12'))
    )
    JWT_ERROR_MESSAGE_KEY = 'error'

    # Dipakai endpoint /api/metrics yang bersifat sistem, bukan data user.
    ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', '')

    RATELIMIT_ENABLED = os.environ.get('RATELIMIT_ENABLED', '1') == '1'
    RATELIMIT_STORAGE_URI = os.environ.get(
        'RATELIMIT_STORAGE_URI', 'memory://'
    )

    CORS_ORIGINS = os.environ.get(
        'CORS_ORIGINS', 'http://localhost:5002,http://localhost:5173'
    )

    JSON_SORT_KEYS = False

    @staticmethod
    def is_sqlite():
        return Config.SQLALCHEMY_DATABASE_URI.startswith('sqlite')


class DevelopmentConfig(Config):
    DEBUG = True

    # Development dan testing membuat tabel otomatis supaya tidak perlu
    # Migration hanya untuk menjalankan kode.
    AUTO_CREATE_TABLES = True


class TestingConfig(Config):
    TESTING = True
    AUTO_CREATE_TABLES = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    JWT_ACCESS_TOKEN_EXPIRES = False
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False

    # Produksi TIDAK membuat tabel otomatis. Skema harus dibangun lewat
    # `flask --app backend.app db upgrade` supaya ada riwayat migration
    # yang bisa diaudit dan di-rollback.
    #
    # Kalau create_all() tetap dipakai di produksi, Alembic akan selalu
    # melaporkan "no changes": tabelnya sudah ada duluan, tanpa pernah
    # tercatat di tabel alembic_version. Akibatnya migration yang
    # sesungguhnya mengubah skema tidak bisa dibuat dengan benar.
    AUTO_CREATE_TABLES = False

    @classmethod
    def validate(cls):
        """Pastikan konfigurasi produksi benar-benar aman.

        Dipanggil sekali saat aplikasi start. Lebih baik gagal
        start daripada jalan dengan secret bawaan yang dipublikasikan
        di README.
        """
        problems = []
        if cls.SECRET_KEY.startswith('dev-secret'):
            problems.append(
                'SECRET_KEY masih nilai bawaan. Buat nilai acak: '
                'python3 -c "import secrets; print(secrets.token_hex(32))"'
            )
        if cls.SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
            problems.append(
                'Produksi seharusnya tidak pakai SQLite. Set DATABASE_URL '
                'ke PostgreSQL.'
            )
        return problems


CONFIGS = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
}


def get_config():
    name = os.environ.get('FLASK_ENV', 'development').lower()
    return CONFIGS.get(name, DevelopmentConfig)
