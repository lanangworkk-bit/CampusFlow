# CampusFlow

**One Place for Your College Life.**

Aplikasi web untuk membantu mahasiswa mengelola kehidupan akademik dan aktivitas kampus dalam satu platform. Dibangun secara bertahap dari Semester 1 hingga Semester 8 sebagai portfolio utama studi Informatika.

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

## Tech Stack

```
HTML5          - Struktur halaman
Tailwind CSS   - Styling (via CDN)
JavaScript     - Logika aplikasi (vanilla, tanpa framework)
LocalStorage   - Penyimpanan data di browser
Git & GitHub   - Version control
```

**Tidak ada backend, tidak ada database, tidak ada framework.** Ini murni frontend.

---

## Project Structure

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

## Installation

Tidak ada yang perlu di-install.

**Clone repository:**

```bash
git clone https://github.com/USERNAME/CampusFlow.git
cd CampusFlow
```

---

## How to Run

**Cara termudah:**

Klik dua kali `index.html`. Selesai.

**Alternatif dengan Live Server (VS Code):**

1. Install extension "Live Server"
2. Klik kanan `index.html` → "Open with Live Server"

---

## Fitur Bonus: Lihat Data LocalStorage

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
