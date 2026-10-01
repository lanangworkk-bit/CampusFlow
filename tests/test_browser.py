"""Uji browser dengan Playwright.

Test lain membalas endpoint dengan requests/curl dan memeriksa JSON-nya.
Itu belum membuktikan apa pun soal halaman yang benar-benar dibuka user:
salah satu id di template, satu handler yang tidak terpasang, atau satu
error JavaScript akan lolos semua test itu tapi_application_ masih
hancur saat dibuka di browser.

Test di sini menjalankan Chromium sungguhan, membuka halaman, mengklik
tombol, dan memeriksa apa yang muncul di layar. Setiap error console dan
setiap request gagal dianggap kegagalan, supaya error frontend tidak
bisa lolos diam-diam.

Test otomatis dilewati kalau Playwright atau Chromium belum terpasang:

    pip install playwright
    python -m playwright install chromium
"""

import os
import re
import socket
import subprocess
import sys
import time
from contextlib import closing

import pytest

playwright_api = pytest.importorskip(
    'playwright.sync_api', reason='playwright belum terpasang'
)

# Pola error console yang memang muncul karena belum login. Filter ini
# dipakai hanya di test yang memb purposefully visiting halaman tanpa token.
PROYEK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pesan yang wajar muncul saat tab pertama kali dibuka tanpa login.
ERROR_BOLEH = (
    'Failed to load resource',
    '401',
    'Failed to fetch',
    'net::ERR_',
    'ResizeObserver',
)

pytestmark = pytest.mark.browser


# ------------------------------------------------------------------ server

def _pakai_port():
    """Cari port bebas supaya tidak bentrok dengan server yang jalan."""
    with closing(socket.socket()) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture(scope='session')
def server():
    """Jalankan aplikasi sungguhan di port bebas.

    Server di dalam proses pytest akan bentrok dengan port dan database
    milik test yang sedang jalan, jadi aplikasi dijalankan sebagai proses
    terpisah dengan database sendiri.
    """
    port = _pakai_port()
    instance_dir = os.path.join(PROYEK, 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    db_path = os.path.join(instance_dir, f'browser_{port}.db')
    # FLASK_ENV sengaja 'development', bukan 'testing'.
    #
    # TestingConfig memaksa database in-memory dan mengabaikan
    # DATABASE_URL. Karena seed dan server berjalan sebagai dua proses
    # terpisah, masing-masing akan punya database memory sendiri yang
    # hilang saat proses mati. Login selalu gagal karena user demo tidak
    # pernah ada di server.
    env = {
        **os.environ,
        'PORT': str(port),
        'DATABASE_URL': f'sqlite:///{db_path}',
        'SECRET_KEY': 'kunci-browser-test-yang-panjang-123',
        'JWT_SECRET_KEY': 'kunci-browser-jwt-yang-panjang-123',
        'FLASK_ENV': 'development',
        'FLASK_DEBUG': '0',
    }
    # Seed harus selesai sebelum server start.
    #
    # Keduanya membuat tabel sendiri (AUTO_CREATE_TABLES aktif di mode
    # development). Kalau server start lebih dulu, keduanya berlomba
    # create_all() pada file yang sama dan salah satunya gagal dengan
    # "table users already exists".
    seed = subprocess.run(
        [sys.executable, '-m', 'flask', '--app', 'backend.app', 'seed'],
        cwd=PROYEK,
        env=env,
        capture_output=True,
        text=True,
    )
    if seed.returncode != 0:
        raise RuntimeError(f'seed gagal: {seed.stdout}{seed.stderr}')

    # Buang data contoh dari seed, sisakan akunnya saja.
    #
    # Seed membuat 12 tugas. Daftar tugas di halaman diurutkan berdasarkan
    # tenggat dan dibatasi 10 per halaman, jadi tugas yang dibuat test
    # bisa mendarat di halaman 2 dan tidak pernah terlihat. Mengosongkan
    # tabel membuat tiap test hanya bergantung pada apa yang dibuatnya
    # sendiri, bukan urutan data seed.
    kosongkan = subprocess.run(
        [
            sys.executable, '-c',
            'from backend.app import create_app;'
            'from backend.extensions import db;'
            'from backend.models import Task, Note, Course;'
            "app = create_app();"
            'ctx = app.app_context();'
            'ctx.push();'
            'Task.query.delete(); Note.query.delete(); Course.query.delete();'
            'db.session.commit()',
        ],
        cwd=PROYEK,
        env=env,
        capture_output=True,
        text=True,
    )
    if kosongkan.returncode != 0:
        raise RuntimeError(
            f'pengosongan gagal: {kosongkan.stdout}{kosongkan.stderr}'
        )

    proses = subprocess.Popen(
        [sys.executable, '-m', 'backend.app'],
        cwd=PROYEK,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    dasar = f'http://127.0.0.1:{port}'
    for _ in range(100):
        if proses.poll() is not None:
            raise RuntimeError(
                f'server mati: {proses.stdout.read()[:2000]}'
            )
        try:
            with closing(socket.create_connection(('127.0.0.1', port), 0.2)):
                break
        except OSError:
            time.sleep(0.2)
    else:
        proses.kill()
        raise RuntimeError('server tidak pernah siap')

    yield dasar

    proses.terminate()
    try:
        proses.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proses.kill()
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture(scope='session')
def browser():
    try:
        with playwright_api.sync_playwright() as p:
            try:
                b = p.chromium.launch()
            except Exception as exc:  # noqa: BLE001
                pytest.skip(f'Chromium belum terpasang: {exc}')
            yield b
            b.close()
    except Exception as exc:  # noqa: BLE001
        if 'playwright install' in str(exc):
            pytest.skip('jalankan: python -m playwright install chromium')
        raise


@pytest.fixture
def halaman(browser, server):
    """Tab Chromium baru yang mencatat error console dan request gagal."""
    konteks = browser.new_context(viewport={'width': 1280, 'height': 900})
    page = konteks.new_page()

    console = []
    gagal = []

    page.on('console', lambda m: console.append(m.text))
    page.on('pageerror', lambda e: console.append(f'pageerror: {e}'))
    page.on('requestfailed', lambda r: gagal.append(
        f'{r.method} {r.url}: {r.failure}'
    ))
    page.on('response', lambda r: gagal.append(
        f'{r.request.method} {r.url}: HTTP {r.status}'
    ) if r.status >= 400 and '/api/' in r.url else None)

    page.goto(server, wait_until='networkidle')

    page.bersih_error = lambda: [
        e for e in console + gagal
        if not any(boleh in e for boleh in ERROR_BOLEH)
    ]
    yield page
    konteks.close()


# ------------------------------------------------------------------ helper

def login(page, username='demo', password='demo1234'):
    """Isi form login dan tekan tombolnya."""
    page.fill('#loginUsername', username)
    page.fill('#loginPassword', password)
    page.click('#loginForm button[type="submit"]')
    page.wait_for_selector('#app:not(.hidden)', timeout=10000)
    # Panel dashboard baru terisi setelah beberapa request paralel selesai.
    page.wait_for_selector('#statsGrid .stat', timeout=10000)


# ------------------------------------------------------------------- test

class TestLogin:
    def test_halaman_muat_dan_tidak_ada_error_console(self, halaman, server):
        assert halaman.title(), 'judul halaman kosong'
        assert halaman.is_visible('#auth'), 'panel login tidak terlihat'
        # Halaman awal memang memanggil API yang butuh token, jadi error
        # 401 saat itu wajar dan tidak dihitung.
        assert halaman.bersih_error() == [], (
            'error di halaman awal: '
            f'{halaman.bersih_error()[:3]}'
        )

    def test_form_login_bisa_dikirim(self, halaman):
        login(halaman)
        assert halaman.is_visible('#logoutBtn')

    def test_kredensial_salah_menampilkan_pesan(self, halaman):
        halaman.fill('#loginUsername', 'demo')
        halaman.fill('#loginPassword', 'salah-sekali')
        halaman.click('#loginForm button[type="submit"]')
        halaman.wait_for_selector('#authError:not(:empty)', timeout=10000)
        assert halaman.is_visible('#auth')
        assert not halaman.is_visible('#app')

    def test_token_disimpan_di_localstorage(self, halaman):
        login(halaman)
        token = halaman.evaluate('localStorage.getItem("campusflow.token")')
        assert token, 'token tidak disimpan di localStorage'
        assert len(token) > 20

    def test_halaman_lama_tetap_terbuka_setelah_refresh(self, halaman):
        login(halaman)
        halaman.reload(wait_until='networkidle')
        halaman.wait_for_selector('#app:not(.hidden)', timeout=10000)
        assert halaman.is_visible('#currentUser')


class TestRegistrasi:
    def test_registrasi_membuat_akun_baru(self, halaman):
        halaman.click('[data-auth-tab="register"]')
        halaman.wait_for_selector('#registerPanel:not(.hidden)')

        nama = 'browseruser'
        halaman.fill('#regName', 'Browser User')
        halaman.fill('#regUsername', nama)
        halaman.fill('#regPassword', 'sandi12345')
        halaman.fill('#regEmail', 'browser@test.local')
        halaman.click('#registerForm button[type="submit"]')

        halaman.wait_for_selector('#app:not(.hidden)', timeout=10000)
        teks = halaman.inner_text('#currentUser')
        assert 'Browser' in teks


class TestDashboard:
    def test_kartu_statistik_terisi_angka(self, halaman):
        login(halaman)
        halaman.wait_for_selector('#statsGrid .stat', timeout=10000)

        nilai = halaman.eval_on_selector_all(
            '#statsGrid .stat-value',
            'els => els.map(e => e.textContent.trim())',
        )
        assert len(nilai) == 6, f'dapat {len(nilai)} kartu, harusnya 6'
        assert all(nilai), f'salah satu kartu kosong: {nilai}'
        # Empat pertama jumlah tugas, dua terakhir persentase.
        for teks in nilai[:4]:
            assert re.fullmatch(r'\d+', teks), f'bukan angka bulat: {teks!r}'
        for teks in nilai[4:]:
            assert re.fullmatch(r'\d+(\.\d+)?%', teks), (
                f'bukan persentase: {teks!r}'
            )

    def test_panel_wawasan_terisi(self, halaman):
        login(halaman)
        halaman.wait_for_selector('#insightPanel', timeout=10000)
        isi = halaman.inner_text('#insightPanel').strip()
        assert isi, 'panelorrh insights kosong'


class TestTugas:
    def test_membuat_tugas_baru_muncul_di_daftar(self, halaman):
        login(halaman)
        halaman.fill('#taskTitle', 'Tugas dari browser')
        halaman.select_option('#taskPriority', 'HIGH')
        halaman.fill('#taskDeadline', '2026-12-31')
        halaman.click('#taskSubmit')

        halaman.wait_for_selector(
            '#taskList .task-card:has-text("Tugas dari browser")',
            timeout=10000,
        )
        assert 'HIGH' in halaman.inner_text('#taskList')

    def test_menandai_selesai_memperbarui_daftar(self, halaman):
        login(halaman)
        halaman.fill('#taskTitle', 'Tugas untuk diselesaikan')
        halaman.click('#taskSubmit')
        halaman.wait_for_selector(
            '#taskList .task-card:has-text("Tugas untuk diselesaikan")',
            timeout=10000,
        )

        # wait_for_selector mengembalikan ElementHandle, yang tidak punya
        # .locator(). locator() hanya ada pada Locator.
        halaman.locator(
            '#taskList .task-card:has-text("Tugas untuk diselesaikan") '
            '[data-action="toggle"]'
        ).click()

        # Setelah toggle, badge harus berubah menjadi COMPLETED.
        halaman.wait_for_selector(
            '#taskList .task-card:has-text("Tugas untuk diselesaikan") '
            '.badge:text("COMPLETED")',
            timeout=10000,
        )

    def test_menghapus_tugas_menghilangkan_dari_daftar(self, halaman):
        login(halaman)
        halaman.fill('#taskTitle', 'Tugas untuk dihapus')
        halaman.click('#taskSubmit')
        halaman.wait_for_selector(
            '#taskList .task-card:has-text("Tugas untuk dihapus")',
            timeout=10000,
        )
        # confirm() memblokir klik sampai dialog ditangani, jadi
        # penanganannya harus dipasang sebelum tombol ditekan. Kalau
        # dipasang sesudah, halaman sudah diam dan dialog membekukan
        # thread browser sampai timeout.
        halaman.once('dialog', lambda d: d.accept())

        halaman.locator(
            '#taskList .task-card:has-text("Tugas untuk dihapus") '
            '[data-action="delete"]'
        ).click()
        halaman.wait_for_selector(
            '#taskList .task-card:has-text("Tugas untuk dihapus")',
            state='detached',
            timeout=10000,
        )

    def test_filter_status_menampilkan_hanya_yang_dipilih(self, halaman):
        login(halaman)
        halaman.fill('#taskTitle', 'Tugas untuk difilter')
        halaman.click('#taskSubmit')
        halaman.wait_for_selector(
            '#taskList .task-card:has-text("Tugas untuk difilter")',
            timeout=10000,
        )

        halaman.click('[data-filter="COMPLETED"]')
        halaman.wait_for_timeout(700)

        badge_di_daftar = halaman.eval_on_selector_all(
            '#taskList .task-card .badge',
            'els => els.map(e => e.textContent.trim())',
        )
        # Badge pertama tiap kartu adalah statusnya.
        status = [
            b for b in badge_di_daftar
            if b in ('COMPLETED', 'IN PROGRESS', 'OVERDUE', 'TODO')
        ]
        assert status, 'tidak ada tugas yang tampil saat filter COMPLETED'
        assert set(status) == {'COMPLETED'}, (
            f'filter COMPLETED bocor status lain: {set(status)}'
        )

    def test_pencarian_mencocokkan_judul(self, halaman):
        login(halaman)
        halaman.fill('#taskTitle', 'Cari aku yukuni')
        halaman.click('#taskSubmit')
        halaman.wait_for_selector(
            '#taskList .task-card:has-text("Cari aku yukuni")',
            timeout=10000,
        )

        halaman.fill('#searchInput', 'yukuni')
        halaman.wait_for_timeout(800)

        isi = halaman.inner_text('#taskList')
        assert 'Cari aku yukuni' in isi

        halaman.fill('#searchInput', 'zzztidakadazzz')
        halaman.wait_for_timeout(800)
        assert 'zzztidakadazzz' not in halaman.inner_text('#taskList')


class TestCatatan:
    def test_menulis_dan_membaca_catatan(self, halaman):
        login(halaman)
        halaman.fill('#noteInput', 'Catatan dari browser')
        halaman.click('#noteForm button[type="submit"]')
        halaman.wait_for_selector(
            '#noteList:has-text("Catatan dari browser")', timeout=10000
        )


class TestKeamanan:
    def test_judul_berbahaya_disanitasi_di_layar(self, halaman):
        """Script di judul tidak boleh dieksekusi atau tampil mentah."""
        login(halaman)
        judul = '<script>window.__xss=1</script>Judul'
        halaman.fill('#taskTitle', judul)
        halaman.click('#taskSubmit')
        halaman.wait_for_selector(
            '#taskList .task-card:has-text("window.__xss=1Judul")',
            timeout=10000,
        )

        # Script tidak boleh dijalankan.
        assert halaman.evaluate('window.__xss') is None, (
            'script dari judul dieksekusi di browser'
        )
        # Dan tidak boleh tampil sebagai teks mentah.
        teks = halaman.inner_text('#taskList')
        assert '<script>' not in teks

    def test_tanda_kutip_dan_ampersand_utuh(self, halaman):
        """Sanitasi harusmenyaring bukan membakar karakter."""
        login(halaman)
        halaman.fill('#taskTitle', 'Nilai 5 < 10 & "kutip"')
        halaman.click('#taskSubmit')
        # Tunggu kartu milik test ini sendiri. Daftar tugas dipakai
        # bersama antar test, jadi '#taskList .task-card' saja bisa sudah
        # terpenuhi oleh tugas milik test sebelumnya.
        halaman.wait_for_selector(
            '#taskList .task-card:has-text("kutip")', timeout=10000
        )

        teks = halaman.inner_text('#taskList')
        assert '<' in teks, f'tanda < hilang: {teks!r}'
        assert '&' in teks, f'tanda & hilang: {teks!r}'


class TestNavigasi:
    def test_tema_berganti_dan_tersimpan(self, halaman):
        login(halaman)
        awal = halaman.evaluate(
            'document.documentElement.dataset.theme || ""'
        )
        halaman.click('#themeToggle')
        halaman.wait_for_timeout(300)
        akhir = halaman.evaluate(
            'document.documentElement.dataset.theme || ""'
        )
        assert awal != akhir, 'tema tidak berubah setelah diklik'
        assert halaman.evaluate(
            'localStorage.getItem("campusflow.theme")'
        ) is not None, 'tema tidak disimpan'

    def test_logout_mengembalikan_ke_halaman_login(self, halaman):
        login(halaman)
        halaman.click('#logoutBtn')
        halaman.wait_for_selector('#auth:not(.hidden)', timeout=10000)

        assert halaman.evaluate('localStorage.getItem("campusflow.token")') is None
        assert not halaman.is_visible('#app')

    def test_tidak_bisa_buka_dashboard_tanpa_login(self, halaman):
        """Harus minta login, bukan menampilkan dashboard kosong."""
        halaman.evaluate('localStorage.clear()')
        halaman.reload(wait_until='networkidle')
        halaman.wait_for_selector('#auth:not(.hidden)', timeout=10000)
        assert not halaman.is_visible('#app')


class TestTanpaErrorConsole:
    def test_alur_lengkap_tanpa_error_console(self, halaman):
        """Gabungan semua aksi dalam satu halaman.

        Kalau ada handler yang tidak terpasang atau salah nama id,
        error console akan muncul di sini meski tiap langkah sendirian
        lolos test.
        """
        login(halaman)

        halaman.fill('#taskTitle', 'Tugas akhir')
        halaman.click('#taskSubmit')
        halaman.wait_for_selector(
            '#taskList .task-card:has-text("Tugas akhir")', timeout=10000
        )

        halaman.fill('#noteInput', 'Catatan akhir')
        halaman.click('#noteForm button[type="submit"]')
        halaman.wait_for_selector(
            '#noteList:has-text("Catatan akhir")', timeout=10000
        )

        halaman.click('[data-filter="all"]')
        halaman.click('[data-filter="COMPLETED"]')
        halaman.click('[data-filter="TODO"]')
        halaman.click('#themeToggle')
        halaman.click('#logoutBtn')

        halaman.wait_for_selector('#auth:not(.hidden)', timeout=10000)

        bersih = halaman.bersih_error()
        assert bersih == [], f'error console/fetch: {bersih[:5]}'