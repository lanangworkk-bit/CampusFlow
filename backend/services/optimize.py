"""Optimasi: index database, cache, dan pemangkasan query.

Yang ada di file ini:
- Index: membuat filter dan sort jauh lebih cepat pada data besar
- Cache: menghindari query berulang untuk data yang jarang berubah
- selectinload: mencegah masalah N+1 query
"""

import time
from functools import wraps

from flask import current_app
from sqlalchemy import event, inspect, text

from backend.extensions import db
from backend.models import Course, Task


# ------------------------------------------------------------------ CACHE

class SimpleCache:
    """Cache in-memory sederhana dengan batas waktu.

    Cukup untuk satu proses gunicorn. Kalau butuh dipakai lintas
    beberapa proses atau server, ganti dengan Redis (sudah tersedia
    di docker-compose.yml lewat RATELIMIT_STORAGE_URI).
    """

    def __init__(self, max_size=256):
        self._data = {}
        self._max_size = max_size

    def get(self, key):
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._data[key]
            return None
        return value

    def set(self, key, value, ttl=30):
        if len(self._data) >= self._max_size:
            # Buang yang paling lama, tidak pricey untuk cache kecil.
            oldest = min(self._data, key=lambda k: self._data[k][1])
            del self._data[oldest]
        self._data[key] = (value, time.time() + ttl)

    def clear(self):
        self._data.clear()


cache = SimpleCache()

# Penghitung hit dan miss, supaya efektivitas cache bisa diukur.
stats = {'hits': 0, 'misses': 0}


def cached(key, ttl=30):
    """Decorator: simpan hasil fungsi di cache selama `ttl` detik.

    Dipakai untuk analytics, karena angkanya tidak berubah setiap
    detik tapi dibaca terus setiap kali dashboard dibuka.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            full_key = f'{key}:{args}:{sorted(kwargs.items())}'
            hit = cache.get(full_key)
            if hit is not None:
                stats['hits'] += 1
                return hit
            stats['misses'] += 1
            value = fn(*args, **kwargs)
            cache.set(full_key, value, ttl)
            return value
        return wrapper
    return decorator


# ------------------------------------------------------------------ INDEX

# Index yang perlu ada. Field yang difilter, diurutkan, atau dicari
# berulang kali getting benefit dari index.
INDEXES = [
    ('ix_tasks_status', 'tasks', ['status']),
    ('ix_tasks_priority', 'tasks', ['priority']),
    ('ix_tasks_deadline', 'tasks', ['deadline']),
    ('ix_tasks_course_id', 'tasks', ['course_id']),
    ('ix_tasks_user_id', 'tasks', ['user_id']),
    ('ix_courses_code', 'courses', ['code']),
    ('ix_audit_logs_created_at', 'audit_logs', ['created_at']),
]


def create_performance_indexes(app):
    """Pastikan index majemuk benar-benar ada.

    Index-nya dideklarasikan di model (Task.__table_args__), jadi
    create_all() dan migration Alembic sudah membuatnya. Fungsi ini
    hanya untuk database lama yang dibuat sebelum index itu ada, dan
    aman dipanggil berulang karena memakai IF NOT EXISTS.

    Jangan tambahkan index lewat CREATE INDEX terpisah di file lain:
    Alembic akan mengira index itu tidak ada di skema lalu tries
    menghapusnya di migration berikutnya.
    """
    statements = [
        'CREATE INDEX IF NOT EXISTS ix_tasks_status_deadline '
        'ON tasks (status, deadline)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_user_deadline '
        'ON tasks (user_id, deadline)',
    ]
    with app.app_context():
        for statement in statements:
            try:
                db.session.execute(text(statement))
            except Exception:
                db.session.rollback()
        db.session.commit()


def analyze_database(app):
    """Minta database menghitung ulang statistik query plan.

    Tanpa ini, database bisa salah memilih index dan query jadi
    lambat padahal sebenarnya sudah ada index yang tepat.
    """
    with app.app_context():
        try:
            db.session.execute(text('ANALYZE'))
            db.session.commit()
        except Exception:
            db.session.rollback()
            # SQLite tidak punya ANALYZE, jadi diabaikan saja.


# ------------------------------------------------------ N+1 QUERY FIX

def attach_query_optimizer(app):
    """Aktifkan penghitung query dan index pendukung.

    N+1 query dicegah di sisi query (lihat load_tasks_with_courses),
    bukan lewat event listener global, supaya Behavior-nya kelihatan
    jelas di kode yang memanggilnya.
    """
    create_performance_indexes(app)
    query_stats(app)
    app.logger.info('Optimizer aktif: index dan penghitung query siap.')


def load_tasks_with_courses(query):
    """Ambil task sekaligus course-nya dalam 2 query, bukan N+1."""
    from sqlalchemy.orm import selectinload

    return query.options(selectinload(Task.course)).all()


def load_courses_with_counts():
    """Hitung jumlah task per course tanpa query per course.

    Satu query GROUP BY, bukan satu query per mata kuliah.
    """
    from sqlalchemy import func

    rows = db.session.query(
        Task.course_id,
        func.count(Task.id).label('total'),
    ).group_by(Task.course_id).all()

    done_rows = db.session.query(
        Task.course_id,
        func.count(Task.id).label('done'),
    ).filter(Task.status == 'COMPLETED').group_by(Task.course_id).all()

    totals = {course_id: total for course_id, total in rows}
    dones = {course_id: done for course_id, done in done_rows}
    return totals, dones


# ------------------------------------------------------------ DIAGNOSTIC

def query_stats(app):
    """Berapa banyak query yang jalan, untuk cek performa.

    Mengembalikan dict penghitung yang nilainya bertambah setiap
    query dieksekusi. Panggil sebelum request, baca setelahnya:
        stats = query_stats(app)
        ... jalankan request ...
        print(stats['total'])
    """
    counter = {'total': 0, 'slow': 0}
    threshold = 0.1  # 100 milidetik

    # db.engine hanya bisa diakses dari dalam app context.
    with app.app_context():
        engine = db.engine

        @event.listens_for(engine, 'before_cursor_execute')
        def before(conn, cursor, statement, parameters, context, executemany):
            context._query_start = time.perf_counter()

        @event.listens_for(engine, 'after_cursor_execute')
        def after(conn, cursor, statement, parameters, context, executemany):
            elapsed = time.perf_counter() - context._query_start
            counter['total'] += 1
            if elapsed > threshold:
                counter['slow'] += 1
                app.logger.warning(
                    'Query lambat (%.1f ms): %s', elapsed * 1000, statement[:120]
                )

    return counter


def table_stats(app):
    """Jumlah baris dan ukuran tiap tabel."""
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if uri.startswith('sqlite'):
        return _sqlite_stats()
    return _postgres_stats()


def _sqlite_stats():
    result = {}
    tables = db.session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )).fetchall()
    for (name,) in tables:
        count = db.session.execute(
            text(f'SELECT COUNT(*) FROM "{name}"')
        ).scalar()
        result[name] = count
    return result


def _postgres_stats():
    result = {}
    rows = db.session.execute(text("""
        SELECT relname AS name, n_live_tup AS rows
        FROM pg_stat_user_tables
        ORDER BY n_live_tup DESC
    """)).fetchall()
    for name, rows in rows:
        result[name] = rows
    return result


def explain(app, sql):
    """Lihat rencana eksekusi sebuah query.

    Berguna untuk memastikan index benar-benar dipakai. Kalau outputnya
    masih 'SCAN', berarti index-nya belum kepakai.
    """
    with app.app_context():
        rows = db.session.execute(text(f'EXPLAIN QUERY PLAN {sql}')).fetchall()
        return [dict(r._mapping) for r in rows]
