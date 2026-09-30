# CampusFlow

**One Place for Your College Life.**

Aplikasi web untuk membantu mahasiswa mengelola kehidupan akademik dan aktivitas kampus dalam satu platform. Dibangun secara bertahap dari Semester 1 hingga Semester 8 sebagai portfolio utama studi Informatika.

---

## 🎓 Semester 2 — Flask + Database (branch `semester-2`)

Versi ini adalah **lanjutan** dari Semester 1. Semua fitur Semester 1 tetap ada,
tapi penyimpanan datanya pindah dari LocalStorage ke **server + database**.

### Apa yang Berubah?

| | Semester 1 (`main`) | Semester 2 (`semester-2`) |
|---|---|---|
| Penyimpanan | LocalStorage (di browser) | SQLite (di server) |
| Backend | Tidak ada | Flask |
| Data | Hilang kalau cache dibersihkan | Permanen |
| Akses | Cuma 1 browser | Browser manapun |
| Dark mode | LocalStorage | Tetap LocalStorage (preferensi perangkat) |

### Tech Stack (Semester 2)

```
HTML5          - Struktur halaman
Tailwind CSS   - Styling (via CDN)
JavaScript     - Logika aplikasi + fetch() untuk API
Python         - Bahasa backend
Flask          - Web framework
SQLite         - Database
Jinja2         - Template engine Flask
```

### Project Structure (Semester 2)

```
CampusFlow/
├── templates/
│   └── index.html          # Template Jinja2
├── static/
│   ├── script.js           # Logika + API calls
│   └── style.css           # Custom CSS
├── backend/
│   └── app.py              # Server Flask + REST API
├── database/
│   └── campusflow.db       # Database SQLite (tidak di-commit)
├── requirements.txt        # Daftar dependency
└── README.md
```

### Installation (Semester 2)

Pastikan Python 3 sudah terinstall.

```bash
git clone https://github.com/lanangworkk-bit/CampusFlow.git
cd CampusFlow
git checkout semester-2

# Buat virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### How to Run (Semester 2)

```bash
source venv/bin/activate      # aktifkan venv
python backend/app.py
```

Lalu buka di browser: **http://localhost:5002**

Database akan dibuat otomatis saat pertama kali server jalan.

> **Penting:** halaman **HARUS** dibuka lewat `http://localhost:5002`,
> bukan klik dua kali `index.html`. Alasannya, `fetch()` butuh alamat server
> untuk mengambil data. Jika dibuka sebagai `file:///`, browser tidak bisa
> menghubungi database.

### REST API

| Method | URL | Fungsi |
|---|---|---|
| `GET` | `/api/tasks` | Ambil semua task |
| `POST` | `/api/tasks` | Tambah task baru |
| `PUT` | `/api/tasks/<id>` | Update task |
| `DELETE` | `/api/tasks/<id>` | Hapus task |
| `GET` | `/api/courses` | Ambil semua mata kuliah |
| `POST` | `/api/courses` | Tambah mata kuliah |
| `DELETE` | `/api/courses/<id>` | Hapus mata kuliah |
| `GET` | `/api/notes` | Ambil semua catatan |
| `POST` | `/api/notes` | Tambah catatan |
| `DELETE` | `/api/notes/<id>` | Hapus catatan |
| `POST` | `/api/reset` | Hapus semua data |

**Test API tanpa browser** — buka `http://localhost:5002/api/tasks` di browser,
atau pakai `curl` di terminal:

```bash
curl http://localhost:5002/api/tasks

curl -X POST http://localhost:5002/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Belajar Flask","deadline":"2026-10-20","priority":"HIGH"}'
```

### Konsep yang Dipelajari di Semester 2

1. **Flask** — membuat server, route, dan request handler
2. **REST API** — communicates antara frontend dan backend lewat HTTP
3. **JSON** — format pertukaran data (Python `dict` ↔ JavaScript `object`)
4. **Parameterized Query** — mencegah SQL Injection (`?` placeholder)
5. **Primary Key & AUTOINCREMENT** — identitas unik tiap baris
6. **CRUD** — Create, Read, Update, Delete
7. **Status Code** — 200 OK, 201 Created, 400 Bad Request, 404 Not Found
8. **Async/Await mental model** — `fetch()` butuh waktu, data belum tersedia
   saat pertama dipanggil
9. **Cache di memory** — hasil `fetch` disimpan sementara supaya kode
  渲染 tidak harus async di mana-mana
10. **Business Logic di server** — aturan bisnis (misal `COMPLETED` →
    `progress = 100`) ditulis di backend, bukan frontend

### Contoh Alur Request

```
User klik tombol "Tambah Task"
        ↓
JavaScript: fetch('/api/tasks', { method: 'POST', body: {...} })
        ↓
Browser mengirim HTTP request ke server
        ↓
Flask menerima di route create_task()
        ↓
app.py menjalankan INSERT INTO tasks ... ? (query aman dari SQL Injection)
        ↓
SQLite menyimpan data, db.commit()
        ↓
Flask balas JSON: { "id": 7, "title": "...", ... }
        ↓
JavaScript: .then() → masukkan ke cache → render ulang tampilan
```

---

## Fitur (Semester 1)

| Modul | Fitur |
|---|---|
| **Dashboard** | Greeting dinamis, tanggal, 4 statistik card |
| **Task Management** | Tambah, edit, hapus, ubah status, ubah progress |
| **Prioritas** | LOW, MEDIUM, HIGH, URGENT (dengan warna berbeda) |
| **Status** | TODO, IN PROGRESS, COMPLETED, OVERDUE (otomatis) |
| **Deadline** | Dihitung otomatis: Hari ini, Besok, X hari lagi, Terlambat |
| **Filter & Search** | Cari berdasarkan judul/deskripsi, filter berdasarkan status |
| **Sorting** | Otomatis diurutkan berdasarkan deadline terdekat |
| **Course List** | Nama, kode, SKS, dosen, hari, jam, ruangan |
| **Calendar** | Kalender bulanan dengan penanda deadline |
| **Notes** | Catatan sederhana tersimpan permanen |
| **Analytics** | Task completion rate + breakdown per prioritas |
| **Dark Mode** | Toggle tema, tersimpan di LocalStorage |
| **Responsive** | Layout desktop, tablet, mobile |
| **Accessibility** | Label ARIA, keyboard navigation (Esc), focus management |

---

## ⚠️ Versi Semester 1 (branch `main`)

Semua isi README di bawah ini menggambarkan **Semester 1** versi yang ada di branch `main`:
frontend murni tanpa backend.

Untuk versi **Semester 2** (Flask + database), pindah ke branch `semester-2`.

---

## Tech Stack (Semester 1)

```
HTML5          - Struktur halaman
Tailwind CSS   - Styling (via CDN)
JavaScript     - Logika aplikasi (vanilla, tanpa framework)
LocalStorage   - Penyimpanan data di browser
Git & GitHub   - Version control
```

**Tidak ada backend, tidak ada database, tidak ada framework.** Ini murni frontend.

---

## Project Structure (Semester 1)

```
CampusFlow/
├── index.html          # Struktur halaman & modal
├── assets/
│   ├── script.js       # Logika aplikasi
│   └── style.css       # Custom CSS & komponen reusable
├── .gitignore
└── README.md
```

---

## Installation (Semester 1)

Tidak ada yang perlu di-install.

**Clone repository:**

```bash
git clone https://github.com/lanangworkk-bit/CampusFlow.git
cd CampusFlow
```

---

## How to Run (Semester 1)

**Cara termudah:**

Klik dua kali `index.html`. Selesai.

**Alternatif dengan Live Server (VS Code):**

1. Install extension "Live Server"
2. Klik kanan `index.html` → "Open with Live Server"

---

## Fitur Bonus: Lihat Data LocalStorage (Semester 1)

Untuk belajar, buka Browser Console (`Cmd + Option + I` di Mac, `F12` di Windows) lalu ketik:

```javascript
localStorage.getItem('campusflow_tasks')
```

Ini akan menampilkan data tugas yang tersimpan dalam format JSON.

Untuk menghapus semua data dan mulai ulang:

```javascript
localStorage.clear()
```

Atau klik tombol **"Reset Semua Data"** di section Pengaturan.

---

## Konsep yang Dipelajari di Semester 1

### 1. DOM Manipulation
Mengubah tampilan halaman menggunakan JavaScript:

```javascript
document.getElementById('stat-total').textContent = 10;
```

### 2. Event Delegation
Satu listener untuk banyak elemen dinamis. Listener tetap bekerja walaupun elemen baru ditambahkan.

```javascript
listEl.addEventListener('click', function (event) {
    const target = event.target.closest('[data-action]');
    if (target) deleteTask(target.dataset.id);
});
```

### 3. LocalStorage
Menyimpan data di browser secara permanen. Harus diserialisasi ke JSON.

```javascript
localStorage.setItem('key', JSON.stringify(data));
const data = JSON.parse(localStorage.getItem('key'));
```

### 4. Template Literal
Membuat HTML dari string dengan menyisipkan variabel.

```javascript
const html = `<p>${task.title}</p>`;
```

### 5. XSS Prevention
Data dari user harus di-escape sebelum dimasukkan ke HTML.

```javascript
function escapeHTML(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```

### 6. Derived State
Status OVERDUE tidak disimpan, tapi dihitung ulang dari tanggal. Jadi selalu akurat tanpa perlu di-update manual.

```javascript
function getEffectiveStatus(task) {
    if (task.status === 'COMPLETED') return 'COMPLETED';
    if (task.deadline && task.deadline < todayISO()) return 'OVERDUE';
    return task.status;
}
```

---

## Roadmap

| Semester | Fokus | Status |
|---|---|---|
| **1** | HTML, Tailwind CSS, JavaScript, DOM, LocalStorage | ✅ Selesai |
| **2** | Python, Flask, SQLite, REST API dasar | 🔜 |
| **3** | REST API, PostgreSQL, Authentication | 🔜 |
| **4** | Data Analytics, AI, Machine Learning | 🔜 |
| **5** | Docker, Linux, Cloud, CI/CD | 🔜 |
| **6** | Cybersecurity, Secure Architecture | 🔜 |
| **7** | System Design, Testing, Scalability | 🔜 |
| **8** | Production, Optimization, Capstone | 🔜 |

### Catatan tentang Semester 2

 versi awal CampusFlow sudah pernah dibangun dengan **Flask + SQLite** di branch `flask-backend`.
Branch tersebut sengaja disimpan sebagai bahan pembelajaran komparasi静态 vs dynamic.

**Pembelajaran kunci:**
- Versi `main` (Semester 1): sederhana, cepat, nol konfigurasi, tapi data hanya di satu browser
- Versi `flask-backend` (Semester 2): data tersimpan permanen di server, tapi butuh setup Python + venv + server jalan

**Lihat perbedaannya:**

```bash
git checkout flask-backend
```

---

## Future Development

- Upload file lampiran pada tugas
- Relasi tugas dengan mata kuliah
- Ekspor data ke PDF/CSV
- Import data dari format lain
- Sinkronisasi antar perangkat (membutuhkan backend)

---

## Author

Dibangun sebagai portfolio proyek studi Informatika.

---

## License

MIT License - bebas digunakan untuk keperluan belajar.
