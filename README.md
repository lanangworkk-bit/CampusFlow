# CampusFlow

Pengelola tugas kuliah pribadi. Satu tempat untuk mencatat tugas,
memantau tenggat, dan melihat apakah bebannya masih masuk akal.

Backend Flask dengan SQLAlchemy dan Alembic, satu basis kode untuk dua
database: SQLite untuk development (tanpa konfigurasi sama sekali) dan
PostgreSQL untuk production. JavaScript polos di sisi klien, tanpa
framework dan tanpa build step.

## Fitur

**Tugas**
- Buat, ubah, hapus tugas lengkap dengan judul, deskripsi, prioritas,
  tenggat, dan mata kuliah
- Status TODO, IN PROGRESS, dan COMPLETED dengan progres 0-100 persen
- Tampilan otomatis menandai tugas yang lewat tenggat sebagai
  `OVERDUE`, tanpa perlu disimpan ulang
- Filter gabungan, pencarian di beberapa kolom, pengurutan, dan
  paginasi
- Filter cepat: semua, belum, sedang, selesai, terlambat, hari ini,
  minggu ini

**Mata kuliah dan catatan**
- Mata kuliah dengan kode, SKS, dosen, hari, jam, dan ruang
- Catatan pribadi dengan fitur sematan

**Analitik**
- Ringkasan progres dan tingkat penyelesaian
- Beban kerja tujuh hari ke depan, dengan penilaian COMFORTABLE,
  TIGHT, atau OVERLOADED
- Saran urutan mengerjakan tugas, dihitung dari tenggat, prioritas,
  progres, dan perkiraan waktu
- Tugas yang macet: belum selesai meski tenggatnya sudah lewat
- Produktivitas: rata-rata waktu penyelesaian, tugas per minggu, hari
  paling sibuk, dan rentetan hari berurutan

**Akun**
- Registrasi dan login dengan JWT
- Dua peran: student dan admin
- Setiap pengguna hanya melihat dan mengubah datanya sendiri

**Operasional**
- Health check, versi aplikasi, dan metrik
- Audit log untuk perubahan data
- Rate limit pada endpoint sensitif, dengan Redis saat dikonfigurasi
- Container Docker, Docker Compose, dan CI dengan enam job

## Tumpukan teknologi

| Lapisan      | Teknologi                                          |
| ------------ | -------------------------------------------------- |
| Backend      | Flask 3, SQLAlchemy 2, Alembic, Flask-JWT-Extended |
| Database     | SQLite (default) atau PostgreSQL 16                |
| Rate limit   | memory (default) atau Redis                        |
| Server       | Gunicorn, 3 worker                                  |
| Klien        | JavaScript polos, tanpa framework                   |
| Pengujian    | pytest dan Playwright (Chromium)                    |
| Operasional  | Docker, Docker Compose, GitHub Actions              |

## Menjalankan

Butuh Python 3.11 atau lebih baru.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
flask --app backend.app seed --admin
python3 -m backend.app
```

Buka http://localhost:5002

Akun yang dibuat oleh perintah seed:

| Peran  | Username | Password    |
| ------ | -------- | ----------- |
| student | `demo`   | `demo1234`  |
| admin   | `admin`  | `admin1234` |

Ganti kedua password itu sebelum dipakai di lingkungan nyata.

## Perintah lain

```bash
make dev            # mode pengembangan dengan auto-reload
make test           # jalankan test
make migrate        # terapkan perubahan skema database
make check          # periksa konfigurasi dan koneksi database
make reset          # hapus semua data, isi ulang dengan data contoh
make clean          # hapus cache dan file sementara
make docker-up      # jalankan dengan PostgreSQL dan Redis
make docker-down    # hentikan semua container
```

`make help` menampilkan daftar lengkap.

## Konfigurasi

Semua opsional. Tanpa konfigurasi apa pun, aplikasi memakai SQLite di
`database/campusflow.db` dan sudah bisa langsung jalan.

Salin `.env.example` jadi `.env` untuk mengubah nilai:

| Variabel | Default | Keterangan |
| --- | --- | --- |
| `SECRET_KEY` | kunci dev | Wajib diganti di produksi |
| `JWT_SECRET_KEY` | sama dengan `SECRET_KEY` | Kunci penandatangan token |
| `DATABASE_URL` | SQLite lokal | Contoh: `postgresql://user:pass@localhost/campusflow` |
| `ADMIN_API_KEY` | kosong | Kunci untuk endpoint `/api/metrics` |
| `RATELIMIT_STORAGE_URI` | `memory://` | Pakai `redis://` di produksi |
| `CORS_ORIGINS` | tanpa CORS | origins yang diizinkan, dipisah koma |
| `LOG_LEVEL` | `INFO` | `DEBUG` saat development |

Mode `production` menolak berjalan kalau `SECRET_KEY` masih memakai
kunci bawaan. Periksa dengan `flask --app backend.app check`.

## Migrasi database

Skema dikelola dengan Alembic. Setiap perubahan model menghasilkan satu
file di `migrations/versions/`, jadi riwayat perubahan tersimpan dan
bisa di-rollback.

```bash
# Setelah mengubah model
flask --app backend.app db migrate -m "tambah kolom selesai_di"
flask --app backend.app db upgrade

# Melihat perubahan yang belum dimigrasikan
flask --app backend.app db migrate --check
```

Mode `production` sengaja tidak membuat tabel otomatis. Kalau
`create_all()` ikut dipakai di produksi, tabelnya sudah ada sebelum
Alembic sempat mencatat revision, sehingga Alembic selalu melaporkan
"no changes" dan migration yang sebenarnya mengubah skema tidak akan
tercatat.

Tabel dan index dideklarasikan di model. Jangan menambahkan index lewat
`CREATE INDEX` terpisah di file lain, karena Alembic tidak akan melihat
dan akan mencoba menghapusnya di migration berikutnya.

## Struktur

```
backend/
  app.py              application factory, CLI, error handler
  config.py           konfigurasi per environment
  models/             model SQLAlchemy
  routes/             endpoint auth, resource, analytics, system
  services/           logika analytics, keamanan, optimasi
  seed_data.py        data contoh
  version.py          nomor versi
migrations/           riwayat skema (Alembic)
templates/            halaman HTML
static/               CSS dan JavaScript
tests/                test pytest
```

## Test

```bash
source venv/bin/activate
python3 -m pytest tests/ -v
```

Test mencakup autentikasi dan peran, filter dan paginasi, nilai
batas, kepemilikan data antar pengguna, sanitasi input, dan batas
waktu respons.

### Test browser

Suite di atas membalas endpoint dan memeriksa JSON-nya. Itu belum
membuktikan apa pun soal halaman yang benar-benar dibuka user: salah
satu `id` yang salah tulis di template, satu handler yang tidak
terpasang, atau satu error JavaScript akan lolos semuanya, padahal
halamannya hancur.

`tests/test_browser.py` menutup celah itu. Chromium sungguhan
dibuka, form diisi, tombol diklik, dan yang muncul di layar diperiksa.
Setiap error console dan request gagal ke `/api/` dianggap kegagalan,
jadi error frontend tidak bisa lolos diam-diam.

```bash
source venv/bin/activate
pip install playwright
python -m playwright install chromium
python3 -m pytest tests/test_browser.py -v
```

Kalau Playwright atau Chromium belum terpasang, file ini otomatis
dilewati, bukan gagal. Jalankan hanya yang browser:

```bash
python3 -m pytest -m browser -v
```

Jadi CI punya job `Test Browser` tersendiri. Job `Build Docker Image`
menunggu job itu selesai, jadi image tidak dipromosikan kalau
halamannya rusak.

## Deployment

```bash
docker compose up -d --build
```

Compose menjalankan tiga service: aplikasi di Gunicorn, PostgreSQL,
dan Redis untuk rate limit. Data PostgreSQL disimpan di volume
`pgdata` dan tidak hilang saat container dihapus.

## Catatan

Tugas berstatus `OVERDUE` tidak disimpan di database. Status itu
dihitung saat dibaca dari perbandingan `deadline` dengan tanggal
sekarang, jadi tugas yang menua tidak perlu migrasi. Field
`status` hanya berisi tiga nilai yang benar-benar bisa dipilih user.

Progres 100 persen selalu berarti `COMPLETED`, dan `COMPLETED` selalu
memaksa progres jadi 100. Aturan ini berlaku di API maupun di form,
supaya data tidak bisa masuk ke keadaan yang saling bertentangan.
