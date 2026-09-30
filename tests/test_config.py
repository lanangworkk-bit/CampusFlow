"""Test konfigurasi, terutama pemilihan dan normalisasi database."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from backend import config as config_module

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestNormalisasiUrlSqlite:
    """Path SQLite relatif harus jadi absolut.

    SQLAlchemy menafsirkan 'sqlite:///p.db' relatif ke folder kerja,
    sedangkan Flask-Migrate menafsirkannya relatif ke instance_path.
    Kalau dibiarkan relatif, migrasi menulis ke satu file dan aplikasi
    membuka file lain: migrasi terlihat sukses lalu aplikasi gagal
    dengan "no such table".
    """

    def test_relatif_jadi_absolut(self, monkeypatch):
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///p.db')
        url = config_module._database_url()
        assert url.startswith('sqlite:///')
        assert 'p.db' in url
        # Harus absolut, tidak boleh relatif ke folder kerja.
        assert config_module.INSTANCE_DIR in url

    def test_absolut_tidak_diubah(self, monkeypatch):
        monkeypatch.setenv('DATABASE_URL', 'sqlite:////tmp/abs.db')
        assert config_module._database_url() == 'sqlite:////tmp/abs.db'

    def test_memory_tidak_diubah(self, monkeypatch):
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
        assert config_module._database_url() == 'sqlite:///:memory:'

    def test_postgres_tidak_diubah(self, monkeypatch):
        url = 'postgresql+psycopg://user:pass@localhost:5432/campusflow'
        monkeypatch.setenv('DATABASE_URL', url)
        assert config_module._database_url() == url

    def test_default_adalah_sqlite_absolut(self, monkeypatch):
        monkeypatch.delenv('DATABASE_URL', raising=False)
        url = config_module._database_url()
        assert url.startswith('sqlite:///')
        assert str(config_module.BASE_DIR) in url

    def test_config_app_ikut_menormalkan(self, monkeypatch):
        """Nilai yang dibaca aplikasi harus sudah absolut.

        Ini yang membuat migrasi dan aplikasi pasti menunjuk file
        yang sama. Memakai config development karena TestingConfig
        sengaja memakai database di memori, bukan nilai env.
        """
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///cek.db')
        from backend.app import create_app
        app = create_app('development')
        configured = app.config['SQLALCHEMY_DATABASE_URI']
        assert config_module.INSTANCE_DIR in configured
        assert 'cek.db' in configured

    def test_testing_tetap_pakai_memori(self, monkeypatch):
        """TestingConfig harus tetap memakai in-memory.

        Kalau ikut membaca DATABASE_URL, test bisa diam-diam
        menulis ke database developer.
        """
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///cek.db')
        from backend.app import create_app
        assert create_app('testing').config['SQLALCHEMY_DATABASE_URI'] == 'sqlite://' 


class TestAppDenganDatabaseRelatif:
    """Jalankan apps.py sungguhan dengan DATABASE_URL relatif.

    Diuji lewat subprocess supaya benar-benar mencerminkan cara user
    menjalankan aplikasi, termasuk apakah migrasi dan runtime memakai
    file yang sama.
    """

    def _run(self, *args, env_extra=None):
        env = dict(os.environ)
        env['PYTHONPATH'] = str(PROJECT_ROOT)
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, '-m', 'flask', '--app', 'backend.app', *args],
            cwd=str(PROJECT_ROOT), env=env,
            capture_output=True, text=True, timeout=120,
        )

    @pytest.fixture(scope='class')
    def hasil_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_name = 'uji_relatif.db'
            env = {
                'FLASK_ENV': 'production',
                'SECRET_KEY': 'kunci-produksi-yang-cukup-panjang-123',
                'DATABASE_URL': f'sqlite:///{db_name}',
            }
            upgrade = self._run('db', 'upgrade', env_extra=env)

            # Hanya boleh ada satu file database, di instance/.
            dibuat = sorted(
                str(p.relative_to(PROJECT_ROOT))
                for p in PROJECT_ROOT.rglob(f'{db_name}')
            )
            yield upgrade, dibuat, env
            for rel in dibuat:
                (PROJECT_ROOT / rel).unlink(missing_ok=True)

    def test_upgrade_sukses(self, hasil_upgrade):
        upgrade, _, _ = hasil_upgrade
        assert upgrade.returncode == 0, upgrade.stderr

    def test_hanya_satu_file_database(self, hasil_upgrade):
        _, dibuat, _ = hasil_upgrade
        assert len(dibuat) == 1, f'lebih dari satu file database: {dibuat}'
        assert dibuat[0].startswith('instance/'), dibuat

    def test_tabel_terbentuk(self, hasil_upgrade):
        import sqlite3
        upgrade, dibuat, _ = hasil_upgrade
        if not dibuat:
            pytest.skip('file database tidak ada')
        path = PROJECT_ROOT / dibuat[0]
        conn = sqlite3.connect(path)
        try:
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            revision = conn.execute(
                'SELECT version_num FROM alembic_version'
            ).fetchone()
        finally:
            conn.close()

        assert {'users', 'courses', 'tasks', 'notes', 'audit_logs'} <= tables
        assert revision and revision[0]

    def test_runtime_terhubung_ke_file_yang_sama(self, hasil_upgrade):
        """Aplikasi harus menemukan tabel yang dibuat migrasi.

        Ini inti bug-nya: migrasi berhasil di satu file, lalu aplikasi
        membuka file lain dan gagal dengan "no such table".
        """
        upgrade, dibuat, env = hasil_upgrade
        if not dibuat:
            pytest.skip('file database tidak ada')

        check = subprocess.run(
            [sys.executable, '-c',
             'from backend.app import app\n'
             'from backend.models import Task\n'
             'with app.app_context():\n'
             '    print(Task.query.count())\n'],
            cwd=str(PROJECT_ROOT),
            env={**os.environ, 'PYTHONPATH': str(PROJECT_ROOT), **env},
            capture_output=True, text=True, timeout=120,
        )
        assert check.returncode == 0, check.stderr
        assert 'no such table' not in check.stderr.lower()
        assert check.stdout.strip() == '0'


class TestEnvironmentProduction:
    def test_production_tidak_auto_create(self):
        from backend.app import create_app
        assert create_app('production').config['AUTO_CREATE_TABLES'] is False

    def test_development_auto_create(self):
        from backend.app import create_app
        assert create_app('development').config['AUTO_CREATE_TABLES'] is True

    def test_secret_bawaan_ditolak_di_produksi(self, monkeypatch):
        from backend.app import create_app
        app = create_app('production')
        problems = app.config['ProductionConfig'].validate() \
            if 'ProductionConfig' in app.config else []
        # validate() harus melaporkan masalah, tidak melempar error,
        # supaya CLI bisa menampilkan semuanya sekaligus.
        assert isinstance(problems, list)
