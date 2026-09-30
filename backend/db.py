"""Koneksi database dan pembuatan schema.

File ini adalah satu-satunya tempat yang tahu di mana file
database berada dan apa saja tabelnya. Semua modul lain
cuma panggil get_db() tanpa perlu tahu detail path-nya.

Analogi: file ini adalah "pintu masuk" ke gudang. Modul lain
minta barang lewat pintu, bukan masuk gudang sendiri.
"""

import os
import sqlite3
from datetime import date

DB_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'database', 'campusflow.db'
)

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


def get_db():
    """Buka koneksi ke database.

    row_factory = sqlite3.Row supaya hasil query bisa diakses
    dengan nama kolom ('title') dan juga dengan indeks (row[0]).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
