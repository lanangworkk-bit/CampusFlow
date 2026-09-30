# CampusFlow

Pengelola tugas kuliah pribadi. Satu tempat untuk mencatat tugas,
memantau tenggat, dan melihat apakah bebannya masih masuk akal.

Berjalan dengan Flask, SQLite, dan JavaScript polos tanpa framework
di sisi klien. Tidak ada build step, tidak ada `npm install`.

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
- Rate limit pada endpoint sensitif
- Container Docker dan konfigurasi CI

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

## Struktur

```
backend/
  app.py              application factory, CLI, error handler
  config.py           konfigurasi per environment
  models/             model SQLAlchemy
  routes/             endpoint auth, resource, analytics, system
  services/           logika analytics, keamanan, optimasi
  seed_data.py        data contoh
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
