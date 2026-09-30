"""Isi data contoh.

Dipakai oleh `flask --app backend.app seed` dan bisa dipanggil langsung
dengan `python3 -m backend.seed_data`.
"""

import random
from datetime import date, timedelta

from backend.extensions import db
from backend.models import Course, Note, Task, User

COURSES = [
    {
        'name': 'Pemrograman Dasar', 'code': 'IF101', 'sks': 3,
        'lecturer': 'Budi Santoso, S.T.', 'room': 'Lab Informatika',
        'day': 'Senin', 'time': '08:00 - 10:30', 'color': 'blue',
    },
    {
        'name': 'Basis Data', 'code': 'IF103', 'sks': 4,
        'lecturer': 'Andi Wijaya, S.Kom.', 'room': 'Lab Data',
        'day': 'Kamis', 'time': '13:00 - 16:00', 'color': 'green',
    },
    {
        'name': 'Jaringan Komputer', 'code': 'IF201', 'sks': 3,
        'lecturer': 'Rina Kusuma, S.T.', 'room': 'Lab Jaringan',
        'day': 'Rabu', 'time': '10:00 - 12:30', 'color': 'purple',
    },
    {
        'name': 'Kalkulus', 'code': 'MA105', 'sks': 3,
        'lecturer': 'Siti Aminah, M.Pd.', 'room': 'Ruang 204',
        'day': 'Selasa', 'time': '09:00 - 11:30', 'color': 'orange',
    },
]

TASK_TEMPLATES = [
    ('Tugas 1 Kalkulator', 'Buat program kalkulator sederhana', 'HIGH', 3),
    ('Tugas 2 Array', 'Latihan array 1 dimensi', 'MEDIUM', 5),
    ('Tugas 3 Fungsi', 'Fungsi dan rekursi', 'MEDIUM', 8),
    ('Praktikum SQL', 'Buat query JOIN', 'HIGH', 2),
    ('Slide Normalisasi', 'NF1 sampai NF3', 'MEDIUM', 4),
    ('Laporan Praktikum', 'Dokumentasi praktikum', 'MEDIUM', 6),
    ('Konfigurasi Router', 'Setup routing static', 'LOW', 10),
    ('Latihan Limit', 'Limit dan kontinuitas', 'URGENT', 1),
    ('Kuis Jaringan', 'Review materi TCP/IP', 'HIGH', 0),
    ('Presentasi Kelompok', 'Slide presentasi', 'MEDIUM', 12),
    ('Tugas Pribadi', 'Latihan mandiri', 'LOW', 15),
    ('Esai Algoritma', 'Esai 2000 kata', 'URGENT', 4),
]

NOTES = [
    ('Jangan lupa backup database sebelum deploy', 'yellow'),
    ('Link dokumentasi Flask: flask.palletsprojects.com', 'blue'),
    ('Kuis: nilai harus kapital semua', 'pink'),
    ('Jadwal lab berubah mulai minggu depan', 'green'),
    ('Password WiFi kampus: Tanyakan ke admin', 'red'),
]


def run_seed(admin=False, reset=True, user=None):
    """Isi database dengan data contoh.

    Parameternya:
    - admin: True  -> buat juga akun admin
    - reset: True  -> kosongkan tabel dulu
    - user:        -> task dimiliki user ini (default: buat user demo)
    """
    if reset:
        Task.query.delete()
        Note.query.delete()
        Course.query.delete()
        db.session.commit()

    if user is None:
        user = User.query.filter_by(username='demo').first()
        if user is None:
            user = User(
                username='demo',
                email='demo@campusflow.id',
                full_name='Demo Student',
            )
            user.set_password('demo1234')
            db.session.add(user)
            db.session.commit()

    if admin and not User.query.filter_by(username='admin').first():
        admin_user = User(
            username='admin',
            email='admin@campusflow.id',
            full_name='Administrator',
            role='admin',
        )
        admin_user.set_password('admin1234')
        db.session.add(admin_user)
        db.session.commit()

    random.seed(42)

    courses = []
    for data in COURSES:
        course = Course(**data)
        db.session.add(course)
        courses.append(course)
    db.session.commit()

    today = date.today()
    statuses = ['TODO', 'TODO', 'IN PROGRESS', 'IN PROGRESS', 'COMPLETED']

    for index, (title, description, priority, due_in) in enumerate(TASK_TEMPLATES):
        status = statuses[index % len(statuses)]
        task = Task(
            title=title,
            description=description,
            status=status,
            priority=priority,
            progress=100 if status == 'COMPLETED' else (
                random.choice([25, 50, 75]) if status == 'IN PROGRESS' else 0
            ),
            deadline=(today + timedelta(days=due_in)).isoformat(),
            course_id=(
                random.choice(courses).id if index % 4 != 3 else None
            ),
            user_id=user.id,
        )
        db.session.add(task)

    for text, color in NOTES:
        db.session.add(Note(text=text, color=color, user_id=user.id))

    db.session.commit()

    return {
        'users': User.query.count(),
        'courses': Course.query.count(),
        'tasks': Task.query.count(),
        'notes': Note.query.count(),
        'demo': {'username': 'demo', 'password': 'demo1234'},
        'admin': {'username': 'admin', 'password': 'admin1234'} if admin else None,
    }


if __name__ == '__main__':
    from app import app

    with app.app_context():
        result = run_seed(admin=True)
        print(f"Data contoh dibuat: {result}")
