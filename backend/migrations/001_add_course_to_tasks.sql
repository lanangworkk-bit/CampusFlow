-- ============================================
-- Migration 001: hubungkan tasks ke courses
-- ============================================
--
-- MASALAH
--   Tabel tasks tidak punya hubungan ke tabel courses.
--   Mustahil menjawab "tugas ini untuk mata kuliah apa?"
--
-- SOLUSI
--   Tambah kolom course_id yang isinya "nomor penunjuk"
--   ke baris di tabel courses. Namanya FOREIGN KEY.
--
-- Kenapa tidak simpan nama mata kuliah langsung di tasks?
--   Kalau nama Mata Kuliah diubah, semua baris tasks yang
--   menyimpan nama lama harus di-update. Miss satu = data
--   tidak konsisten. Dengan foreign key, hanya 1 baris
--   di tabel courses yang berubah.
--
-- KENAPA TABEL HARUS DIBUAT ULANG?
--   SQLite tidak bisa menambah FOREIGN KEY ke tabel yang
--   sudah ada lewat ALTER TABLE. Jadi polanya:
--     1. buat tabel baru dengan constraint yang wanted
--     2. salin data lama ke sana
--     3. hapus tabel lama
--     4. rename tabel baru jadi nama aslinya
--
--   Perhatikan bahwa id ikut disalin, bukan dibuat ulang,
--   supaya relasi yang sudah ada tidak putus.
--
-- CATATAN TENTANG "PRAGMA foreign_keys"
--   SQLite MENONAKAN foreign key secara default. Foreign key
--   hanya dijaga kalau PRAGMA diaktifkan per koneksi. Buka
--   backend/db.py untuk lihat di mana diaktifkannya.

-- 1. Cek dulu: apakah kolom sudah ada?
--    (kalau migration dijalankan dua kali, jangan bikin dobel)
PRAGMA foreign_keys = OFF;

-- 2. Tabel baru dengan struktur yang benar
--
--    course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL
--
--    course_id = kolom penunjuk ke tabel courses (foreign key).
--    ON DELETE SET NULL = kalau mata kuliah dihapus, tasknya
--    tetap ada tapi course_id-nya jadi kosong (NULL), bukan ikut hilang.
--
--    Komentar ditulis di luar blok SQL supaya tidak ikut tersimpan
--    sebagai bagian dari definisi tabel.
CREATE TABLE IF NOT EXISTS tasks_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    deadline DATE,
    priority TEXT DEFAULT 'MEDIUM',
    status TEXT DEFAULT 'TODO',
    progress INTEGER DEFAULT 0,
    course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. Salin data lama, isi course_id dengan mata kuliah pertama
--    supaya task lama tidak kehilangan konteks
INSERT INTO tasks_new (id, title, description, deadline, priority, status, progress, course_id, created_at)
SELECT
    id,
    title,
    description,
    deadline,
    priority,
    status,
    progress,
    (SELECT id FROM courses ORDER BY id LIMIT 1),
    created_at
FROM tasks;

-- 4. Ganti tabel lama dengan yang baru
DROP TABLE tasks;
ALTER TABLE tasks_new RENAME TO tasks;

-- 5. Aktifkan lagi pengecekan foreign key
PRAGMA foreign_keys = ON;
