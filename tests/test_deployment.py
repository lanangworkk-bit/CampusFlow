"""Test konfigurasi deployment: Dockerfile, entrypoint, dan compose.

Fokusnya pada satu hal yang sudah pernah merusak: mode production tidak
membuat tabel otomatis, jadi apa pun yang memulai aplikasi di produksi
harus menjalankan migrasi lebih dulu. Kalau tidak, container tetap
hidup tapi /api/health membalas 503 dan healthcheck menandainya
unhealthy.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = PROJECT_ROOT / 'Dockerfile'
ENTRYPOINT = PROJECT_ROOT / 'docker-entrypoint.sh'


@pytest.fixture(scope='module')
def dockerfile():
    return DOCKERFILE.read_text()


class TestEntrypoint:
    def test_ada(self):
        assert ENTRYPOINT.exists(), 'docker-entrypoint.sh tidak ada'

    def test_bisa_dijalankan(self):
        """Harus punya bit executable.

        Melepas file dari Git membuang bit ini kalau di-checkout di host.
        Kalau hilang, container gagal start dengan "permission denied".
        """
        mode = ENTRYPOINT.stat().st_mode
        assert mode & stat.S_IXUSR, 'docker-entrypoint.sh tidak executable'

    def test_jalankan_migrasi_sebelum_aplikasi(self):
        isi = ENTRYPOINT.read_text()
        assert 'db upgrade' in isi, 'entrypoint tidak menjalankan migrasi'
        # Migrasi harus lebih dulu, lalu aplikasi dieksekusi.
        assert isi.index('db upgrade') < isi.index('exec "$@"')

    def test_exec_app_shell_agar_sinyal_terpropagate(self):
        """Harus pakai exec.

        Tanpa exec, entrypoint tetap menjadi proses induk gunicorn.
        Kalau container dapat SIGTERM, python tidak meneruskannya dan
        gunicorn butuh 30 detik lebih lama untuk berhenti.
        """
        assert 'exec "$@"' in ENTRYPOINT.read_text()

    def test_gagal_jika_migrasi_gagal(self):
        """set -e membuat container berhenti kalau migrasi error."""
        assert 'set -e' in ENTRYPOINT.read_text()


class TestDockerfile:
    def test_pakai_entrypoint(self, dockerfile):
        assert 'ENTRYPOINT ["/app/docker-entrypoint.sh"]' in dockerfile, (
            'container tidak lewat entrypoint, jadi migrasi tidak pernah jalan'
        )

    def test_chmod_entrypoint(self, dockerfile):
        assert 'chmod +x /app/docker-entrypoint.sh' in dockerfile

    def test_ada_perintah_migrasi_di_image(self, dockerfile):
        """Entrypoint harus ikut ter-copy ke image."""
        assert 'COPY --chown=appuser:appuser . .' in dockerfile

    def test_migration_ada_di_image(self):
        """Folder migrations wajib masuk image.

        Kalau ter-exclude, `flask db upgrade` gagal dengan
        "Path doesn't exist: migrations" tepat saat container start.
        """
        ignore = (PROJECT_ROOT / '.dockerignore').read_text()
        assert 'migrations/' not in ignore, \
            'migrations/ ada di .dockerignore tapi dibutuhkan saat start'
        assert (PROJECT_ROOT / 'migrations' / 'versions').is_dir()

    def test_instance_bisa_ditulis(self, dockerfile):
        """Folder instance/ harus ada dan dimiliki appuser.

        Alembic dan SQLite relatif menulis ke sini. Kalau tidak ada,
        migrasi gagal dengan permission denied.
        """
        assert 'mkdir -p /app/database /app/instance' in dockerfile
        assert 'chown -R appuser:appuser /app/database /app/instance' in dockerfile

    def test_jalankan_non_root(self, dockerfile):
        """Directive USER harus menetap, tidak ditimpa baris setelahnya."""
        direktif = [
            baris.strip() for baris in dockerfile.split('\n')
            if baris.strip().startswith('USER ')
        ]
        assert direktif, 'tidak ada directive USER'
        assert direktif[-1] == 'USER appuser', (
            f'directive USER terakhir adalah {direktif[-1]!r}, '
            'bukan appuser'
        )

    def test_mode_produksi(self, dockerfile):
        assert 'FLASK_ENV=production' in dockerfile

    def test_secret_bawaan_tidak_dibuat(self, dockerfile):
        """Image tidak boleh menyetel SECRET_KEY ke nilai tetap.

        Nilai apa pun yang ditulis di Dockerfile ikut bocor ke registry,
        dan nilainya akan sama untuk semua orang yang memakai image ini.
        """
        for baris in dockerfile.split('\n'):
            if 'SECRET_KEY' in baris and '=' in baris:
                assert 'dev-secret' not in baris
                assert 'ganti' not in baris.lower().replace('ganti-ini', '')

    def test_healthcheck_ada(self, dockerfile):
        assert 'HEALTHCHECK' in dockerfile
        assert '/api/health' in dockerfile

    def test_user_ada_folder_home(self, dockerfile):
        """appuser harus punya folder home sendiri.

        Gunicorn membuat socket kontrol di $HOME/.gunicorn/. Tanpa -m
        pada useradd, folder home tidak dibuat, /home dimiliki root, dan
        arbiter mencatat "Control server error: [Errno 13] Permission
        denied: '/home/appuser'". Worker tetap jalan, tapi `gunicorn ctl`
        untuk graceful reload tidak bisa dipakai.
        """
        baris_useradd = [
            baris for baris in dockerfile.split('\n')
            if 'useradd' in baris and 'appuser' in baris
        ]
        assert baris_useradd, 'tidak ada perintah useradd untuk appuser'

        assert any('-m' in baris.split() for baris in baris_useradd), (
            'useradd tanpa -m: appuser tidak punya folder home, '
            'sehingga socket kontrol Gunicorn gagal dibuat'
        )


class TestKetergantunganRedis:
    """Rate limit di Compose memakai Redis, jadi kliennya harus ada."""

    @pytest.fixture(scope='class')
    def requirements(self):
        return (PROJECT_ROOT / 'requirements.txt').read_text()

    def test_paket_redis_tercantum(self, requirements):
        assert 'redis' in requirements, (
            'Flask-Limiter tidak membawa klien Redis. Tanpa paket redis, '
            'container gagal start dengan "redis prerequisite not available" '
            'karena docker-compose.yml mengisi RATELIMIT_STORAGE_URI '
            'dengan redis://'
        )


class TestCompose:
    @pytest.fixture(scope='class')
    def compose(self):
        return (PROJECT_ROOT / 'docker-compose.yml').read_text()

    def test_ada_postgresql(self, compose):
        assert 'postgres' in compose

    def test_ada_redis(self, compose):
        assert 'redis' in compose

    def test_app_lapor_ke_postgres(self, compose):
        assert 'DATABASE_URL' in compose
        assert 'postgresql' in compose

    def test_secret_diambil_dari_env(self, compose):
        """Nilai sensitif harus lewat environment, bukan ditulis mati."""
        for baris in compose.split('\n'):
            if 'SECRET_KEY:' in baris:
                nilai = baris.split(":", 1)[1]
                assert '${' in nilai or ':?' in nilai or \
                    nilai.strip().startswith('${'), \
                    f'SECRET_KEY ditulis mati: {baris.strip()}'

    def test_volume_postgres_persist(self, compose):
        assert 'pgdata' in compose


class TestEntrypointDijalankanBetulBetul:
    """Jalankan entrypoint-nya sungguhan, bukan hanya membaca teksnya."""

    def test_migrasi_lalu_masuk_ke_perintah_berikutnya(self, tmp_path):
        db = tmp_path / 'uji_entrypoint.db'
        env = {
            **os.environ,
            'PYTHONPATH': str(PROJECT_ROOT),
            'FLASK_ENV': 'production',
            'SECRET_KEY': 'kunci-produksi-yang-cukup-panjang-123',
            # Path absolut (empat garis miring). Path relatif akan
            # dipindahkan ke folder instance/ oleh config, bukan ke
            # tmp_path, jadi file yang dicek tidak akan ada.
            'DATABASE_URL': f'sqlite:///{db}',
        }
        hasil = subprocess.run(
            [str(ENTRYPOINT), 'echo', 'APLIKASI_MULAI'],
            cwd=str(PROJECT_ROOT), env=env,
            capture_output=True, text=True, timeout=120,
        )
        assert hasil.returncode == 0, hasil.stderr
        assert 'APLIKASI_MULAI' in hasil.stdout
        assert 'entrypoint' in hasil.stdout

        # Skema harus benar-benar terbentuk setelah entrypoint jalan.
        import sqlite3
        conn = sqlite3.connect(db)
        try:
            tabel = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            revision = conn.execute(
                'SELECT version_num FROM alembic_version'
            ).fetchone()
        finally:
            conn.close()
        assert {'users', 'courses', 'tasks', 'notes'} <= tabel
        assert revision and revision[0], 'tidak ada revision yang tercatat'

    def test_berhenti_kalau_migrasi_gagal(self, tmp_path):
        """Perintah berikutnya tidak boleh jalan kalau migrasi gagal.

        Kalau ada SyntaxError atau revision yang bentrok, container
        harus berhenti. Melanjutkannya berarti melayani request dengan
        skema yang tidak lengkap.
        """
        db = tmp_path / 'uji_gagal.db'
        db.write_bytes(b'bukan file database sqlite yang valid')
        env = {
            **os.environ,
            'PYTHONPATH': str(PROJECT_ROOT),
            'FLASK_ENV': 'production',
            'SECRET_KEY': 'kunci-produksi-yang-cukup-panjang-123',
            'DATABASE_URL': f'sqlite:///{db}',
        }
        hasil = subprocess.run(
            [str(ENTRYPOINT), 'echo', 'TIDAK_BOLEH_MUNCUL'],
            cwd=str(PROJECT_ROOT), env=env,
            capture_output=True, text=True, timeout=120,
        )
        assert hasil.returncode != 0, 'entrypoint lanjut meski migrasi gagal'
        assert 'TIDAK_BOLEH_MUNCUL' not in hasil.stdout
