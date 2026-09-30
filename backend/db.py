"""Koneksi database dan pembuatan schema.

File ini adalah satu-satunya tempat yang tahu di mana file
database berada dan apa saja tabelnya. Semua modul lain
cuma panggil get_db() tanpa perlu tahu detail path-nya.

Analogi: file ini adalah "pintu masuk" ke gudang. Modul lain
minta barang lewat pintu, bukan masuk gudang sendiri.
"""

import glob
import os
import sqlite3
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, '..', 'database', 'campusflow.db')
MIGRATIONS_DIR = os.path.join(BASE_DIR, 'migrations')

SCHEMA = """
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        deadline DATE,
        priority TEXT DEFAULT 'MEDIUM',
        status TEXT DEFAULT 'TODO',
        progress INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT,
        sks INTEGER DEFAULT 3,
        lecturer TEXT,
        day TEXT,
        time TEXT,
        room TEXT
    );

    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
"""


def todayISO():
    """Tanggal hari ini dalam format YYYY-MM-DD."""
    return date.today().isoformat()


def parse_date(value):
    """Validasi tanggal dari user sebelum disimpan ke database.

    Mengembalikan tuple (nilai_bersih, pesan_error).
    Cara pakai:
        value, error = parse_date(data.get('deadline'))
        if error:
            return jsonify({'error': error}), 400

    Kenapa perlu? Tanpa ini, browser bisa mengirim deadline: "abc"
    dan string itu tersimpan apa adanya di database. Efeknya:
    urutan sort salah, tanggal tampil aneh, dan status OVERDUE
    jadi tidak akurat.
    """
    if value is None:
        return None, None

    text = str(value).strip()
    if not text:
        # Deadline kosong itu valid, artinya task tanpa tenggat.
        return None, None

    try:
        # fromisoformat sekaligus memvalidasi format DAN tanggalnya
        # sungguhan: '2026-13-45' akan ditolak, bukan diterima.
        return date.fromisoformat(text).isoformat(), None
    except ValueError:
        return None, f'Invalid date: {text}. Use YYYY-MM-DD, example: 2026-10-20'


def get_db():
    """Buka koneksi ke database.

    row_factory = sqlite3.Row supaya hasil query bisa diakses
    dengan nama kolom ('title') dan juga dengan indeks (row[0]).

    PRAGMA foreign_keys = ON wajib di sini, bukan cukup di schema.
    SQLite mematikan pengecekan foreign key secara default, jadi
    tanpa baris ini, database akan menerima course_id yang ngawur
    tanpa warning.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    """Buat file database dan semua tabelnya kalau belum ada.

    Dipanggil sekali sebelum server mulai berjalan.
    CREATE TABLE IF NOT EXISTS membuat ini aman dipanggil berulang.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()
    db.close()


def run_migrations():
    """Jalankan file SQL di migrations/ yang belum pernah dijalankan.

    Setiap nama file yang sudah dijalankan dicatat di tabel
    schema_migrations, jadi menjalankan server berulang kali
    tidak akan menjalankan migration yang sama dua kali.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()

    done = {
        row['name']
        for row in db.execute('SELECT name FROM schema_migrations')
    }

    # Diurutkan berdasarkan nama file, jadi 001, 002, 003, ...
    for path in sorted(glob.glob(os.path.join(MIGRATIONS_DIR, '*.sql'))):
        name = os.path.basename(path)
        if name in done:
            continue

        with open(path, encoding='utf-8') as handle:
            sql = handle.read()

        try:
            db.executescript(sql)
            db.execute('INSERT INTO schema_migrations (name) VALUES (?)', (name,))
            db.commit()
            print(f'  migration diterapkan: {name}')
        except sqlite3.Error as error:
            db.rollback()
            db.close()
            raise RuntimeError(f'Migration gagal: {name}\n{error}') from error

    db.close()
