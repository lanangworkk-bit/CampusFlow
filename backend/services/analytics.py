"""Mesin analitik dan rekomendasi.

Tidak pakai library berat. Semua dihitung dengan SQL dan operasi
matematika dasar, supaya jelas dari mana angkanya datang.

Yang tersedia:
- statistik agregat (total, status, prioritas, per mata kuliah)
- analisis produktivitas (jam login, hari paling sibuk, streak)
- prediksi beban kerja (forecast) dan skor prioritas
- skor prioritas (heuristic, bukan machine learning sungguhan)
"""

from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, func

from backend.extensions import db
from backend.models import Course, Note, Task, parse_deadline, utcnow


# ---------------------------------------------------------------- statistik

TANPA_MATA_KULIAH = 'Tanpa Mata Kuliah'


def _pct(numerator, denominator):
    """Persentase, aman dari pembagian dengan nol."""
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def effective_status_sql():
    """Versi SQL dari Task.effective_status().

    OVERDUE tidak pernah tersimpan di database; dia dihitung dari
    perbandingan deadline dengan tanggal sekarang. CASE di sini
    meniru aturan yang sama supaya agregasi di database dan perhitungan
    per-objek di Python selalu memberi angka yang sama.
    """
    return case(
        (
            and_(
                Task.status != 'COMPLETED',
                Task.deadline.isnot(None),
                Task.deadline < date.today(),
            ),
            'OVERDUE',
        ),
        (Task.status == 'COMPLETED', 'COMPLETED'),
        else_=Task.status,
    )


def summary(user_id=None):
    # Agregasi dikerjakan database, bukan Python.
    #
    # Dulu semua baris dimuat dulu dengan query.all() lalu dihitung di
    # sini. Itu benar, tapi memuat 40.000 objek ORM hanya untuk
    # menjumlahkannya boros: yang diperlukan sebenarnya enam angka.
    # Dengan SUM(CASE ...) database hanya mengirim enam angka itu, jadi
    # tidak ada ribuan objek yang melewati jaringan.
    #
    # Keempat status tetap saling lepas karenaeffective_status_sql()
    # memakai aturan yang sama persis dengan effective_status(): tugas
    # yang lewat tenggat masuk OVERDUE, bukan juga IN PROGRESS, sehingga
    # jumlah status selalu sama dengan total.
    status_sql = effective_status_sql()

    query = db.select(
        func.count(Task.id),
        func.coalesce(func.sum(Task.progress), 0),
        # SUM(CASE) mengembalikan NULL kalau tidak ada baris sama sekali,
        # jadi setiap SUM dibungkus coalesce agar hasilnya 0, bukan None.
        func.coalesce(func.sum(case((status_sql == 'COMPLETED', 1), else_=0)), 0),
        func.coalesce(func.sum(case((status_sql == 'OVERDUE', 1), else_=0)), 0),
        func.coalesce(func.sum(case((status_sql == 'IN PROGRESS', 1), else_=0)), 0),
        func.coalesce(func.sum(case((status_sql == 'TODO', 1), else_=0)), 0),
    )
    if user_id is not None:
        query = query.where(Task.user_id == user_id)

    (total, progress_total, done, overdue, in_progress, todo) = (
        db.session.execute(query).one()
    )

    # Status di luar empat nilai di atas dianggap TODO, sama seperti
    # perhitungan per-objek yang sebelumnya dipakai.
    tak_dihitung = total - (done + overdue + in_progress + todo)
    if tak_dihitung:
        todo += tak_dihitung

    # Catatan bersifat pribadi, jadi jumlahnya ikut dibatasi ke user
    # yang sedang melihat. Mata kuliah boleh dipakai bersama, jadi
    # jumlahnya memang global.
    notes_query = Note.query
    if user_id is not None:
        notes_query = notes_query.filter_by(user_id=user_id)

    return {
        'total': total,
        'completed': done,
        'overdue': overdue,
        'in_progress': in_progress,
        'todo': todo,
        'completion_rate': _pct(done, total),
        'average_progress': round(progress_total / total, 1) if total else 0,
        'total_courses': Course.query.count(),
        'total_notes': notes_query.count(),
    }


def by_status(user_id=None):
    status_sql = effective_status_sql()

    query = db.select(
        status_sql.label('status'),
        func.count(Task.id).label('jumlah'),
    )
    if user_id is not None:
        query = query.where(Task.user_id == user_id)

    # Dikelompokkan di database, bukan dengan Counter di Python.
    #
    # GROUP BY memakai ekspresinya sendiri, bukan nama alias 'status'.
    # PostgreSQL ikut/group by membaca nama 'status' sebagai kolom
    # tasks.status, bukan hasil CASE, lalu menolak karena deadline tidak
    # ada di GROUP BY. Mengulang ekspresinya membuat pengelompokan jelas.
    counts = dict(db.session.execute(query.group_by(status_sql)).all())

    hasil = []
    for key in ('TODO', 'IN PROGRESS', 'COMPLETED', 'OVERDUE'):
        hasil.append({'status': key, 'count': counts.get(key, 0)})

    # Status lain yang tidak termasuk empat nilai di atas masuk TODO,
    # sama seperti perilaku sebelumnya.
    tak_dihitung = sum(counts.values()) - sum(r['count'] for r in hasil)
    if tak_dihitung:
        hasil[0]['count'] += tak_dihitung

    return hasil


def by_priority(user_id=None):
    query = db.select(Task.priority, func.count(Task.id))
    if user_id is not None:
        query = query.where(Task.user_id == user_id)

    # GROUP BY di database, bukan Counter di Python, supaya tidak perlu
    # memuat seluruh baris ke memori.
    counts = dict(db.session.execute(query.group_by(Task.priority)).all())

    return [
        {'priority': key, 'count': counts.get(key, 0)}
        for key in ('URGENT', 'HIGH', 'MEDIUM', 'LOW')
    ]


def by_course(user_id=None):
    query = db.select(
        Course.name.label('course'),
        func.count(Task.id).label('total'),
        func.sum(case((Task.status == 'COMPLETED', 1), else_=0)).label('completed'),
        func.coalesce(func.sum(Task.progress), 0).label('progress'),
    ).select_from(Task).outerjoin(Course, Task.course_id == Course.id)
    if user_id is not None:
        query = query.where(Task.user_id == user_id)

    rows = []
    # Dikelompokkan per courses.name, nama kosong diganti di Python.
    #
    # Menulis coalesce(courses.name, 'Tanpa Mata Kuliah') sekaligus di
    # SELECT dan GROUP BY tidak bisa dipakai: SQLAlchemy mengirim teks
    # fallback-nya sebagai parameter terpisah, jadi PostgreSQL melihat
    # dua ekspresi berbeda dan menolak karena courses.name tidak ada
    # di GROUP BY.
    for name, total, completed, progress in db.session.execute(
        query.group_by(Course.name)
    ):
        rows.append({
            'course': name or TANPA_MATA_KULIAH,
            'total': total,
            'completed': completed,
            'progress': progress,
            'completion_rate': _pct(completed, total),
            'average_progress': round(progress / total, 1) if total else 0,
        })

    return sorted(rows, key=lambda r: r['total'], reverse=True)


def busiest_courses(user_id=None, limit=5):
    return by_course(user_id)[:limit]


# --------------------------------------------------------- produktivitas

def productivity(user_id=None):
    """Dari kapan user pakai aplikasi, dan kapan paling sibuk."""
    query = Task.query
    if user_id:
        query = query.filter_by(user_id=user_id)

    tasks = query.all()
    by_day = Counter()
    by_created = Counter()

    for task in tasks:
        if task.created_at:
            by_day[task.created_at.strftime('%A')] += 1
            by_created[task.created_at.date().isoformat()] += 1

    ordered_days = [
        'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
        'Saturday', 'Sunday',
    ]

    # Streak: berapa hari berturut-turut ada task yang dibuat,
    # dihitung dari hari ini mundur.
    streak = 0
    cursor = date.today()
    if not by_created.get(cursor.isoformat()):
        cursor -= timedelta(days=1)
    while by_created.get(cursor.isoformat()):
        streak += 1
        cursor -= timedelta(days=1)

    return {
        'by_day_of_week': [
            {'day': day, 'count': by_day.get(day, 0)} for day in ordered_days
        ],
        'busiest_day': max(by_day, key=by_day.get) if by_day else None,
        'current_streak_days': streak,
        'tasks_created_per_day': dict(
            sorted(by_created.items())[-30:]
        ),
    }


def stuck_tasks(user_id=None, days=7):
    """Task yang sudah lama tidak disentuh tapi belum selesai.

    Threshold 7 hari dipilih karena satu minggu adalah waktu yang
    cukup untuk mengukur "lupa" versus "sengaja ditunda".
    """
    cutoff = utcnow() - timedelta(days=days)
    query = Task.query.filter(Task.status != 'COMPLETED').filter(
        Task.updated_at < cutoff
    )
    if user_id:
        query = query.filter_by(user_id=user_id)

    return [t.to_dict() for t in query.order_by(Task.updated_at).all()]


def upcoming(user_id=None, days=14):
    """Task yang akan jatuh tempo dalam N hari ke depan."""
    query = Task.query.filter(Task.status != 'COMPLETED').filter(
        Task.deadline.isnot(None)
    )
    if user_id:
        query = query.filter_by(user_id=user_id)

    # Bandingkan dengan date, bukan teks: kolomnya DATE, jadi
    # perbandingannya harus ikut bertipe date.
    limit_date = date.today() + timedelta(days=days)
    rows = query.filter(Task.deadline <= limit_date).all()
    return [
        dict(t.to_dict(), days_left=_days_left(t.deadline)) for t in rows
    ]


def _days_left(deadline):
    """Sisa hari sampai tenggat. Negatif berarti sudah lewat.

    Menerima date maupun string YYYY-MM-DD lewat parse_deadline,
    supaya pemanggil yang kebetulan memegang string tidak ikut
    gagal diam-diam.
    """
    target = parse_deadline(deadline)
    if target is None:
        return None
    return (target - date.today()).days


# ------------------------------------------------------------- prediksi

def forecast(user_id=None, horizon_days=7):
    """Perkiraan beban kerja tujuh hari ke depan.

    Ini bukan machine learning. Sederhananya: dijumlahkan semua task
    yang jatuh tempo dalam rentang waktu, lalu dibandingkan dengan
    kapasitas mingguan.
    """
    tasks = upcoming(user_id, days=horizon_days)
    total = len(tasks)
    per_day = round(total / horizon_days, 2) if horizon_days else 0

    # Kapasitas yang dipakai sebagai patokan: 5 task per hari.
    # Angkanya bisa diubah sesuai beban nyata masing-masing orang.
    capacity = 5 * horizon_days
    load = round((total / capacity) * 100, 1) if capacity else 0

    if load >= 100:
        verdict = 'OVERLOADED'
        message = f'Beban kerja {horizon_days} hari ke depan penuh. Pertimbangkan menunda.'
    elif load >= 70:
        verdict = 'TIGHT'
        message = 'Beban kerja cukup berat. Fokuskan yang prioritas tinggi dulu.'
    elif total == 0:
        verdict = 'LIGHT'
        message = 'Tidak ada task yang jatuh tempo. Bagus, bisa kerjakan yang lain.'
    else:
        verdict = 'COMFORTABLE'
        message = 'Beban kerja masih aman.'

    return {
        'horizon_days': horizon_days,
        'tasks_due': total,
        'avg_per_day': per_day,
        'capacity': capacity,
        'load_percent': load,
        'verdict': verdict,
        'message': message,
    }


# --------------------------------------------------- skor prioritas (AI-ish)

PRIORITY_WEIGHT = {'URGENT': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}


def urgency_score(task):
    """Seberapa mendesak satu task. Angka lebih besar = lebih mendesak.

    Komponen:
    - bobot prioritas (1-4)
    - jarak ke deadline (0-5, makin dekat makin tinggi)
    - status belum selesai (1)
    - belum ada progres (1)
    """
    score = PRIORITY_WEIGHT.get(task.priority, 2)

    if task.status == 'COMPLETED':
        return 0

    if task.deadline:
        left = _days_left(task.deadline)
        if left is not None:
            if left < 0:
                score += 5
            elif left == 0:
                score += 5
            elif left <= 3:
                score += 4
            elif left <= 7:
                score += 3
            elif left <= 14:
                score += 2
            else:
                score += 1

    if task.status == 'TODO':
        score += 1
    if task.progress == 0:
        score += 1

    return score


def suggest(user_id=None, limit=5):
    """Task yang paling perlu dikerjakan berikutnya."""
    query = Task.query.filter(Task.status != 'COMPLETED')
    if user_id:
        query = query.filter_by(user_id=user_id)

    scored = []
    for task in query.all():
        scored.append((urgency_score(task), task))

    # Deadline None diletakkan paling akhir dengan date.max, bukan
    # teks '9999': sekarang kolomnya bertipe DATE, jadi sentinel
    # harus satu tipe agar urutannya benar.
    scored.sort(key=lambda pair: (-pair[0], pair[1].deadline or date.max))

    results = []
    for score, task in scored[:limit]:
        reasons = []
        if task.deadline:
            left = _days_left(task.deadline)
            if left is not None and left < 0:
                reasons.append(f'Terlambat {-left} hari')
            elif left == 0:
                reasons.append('Jatuh tempo hari ini')
            elif left is not None and left <= 3:
                reasons.append(f'{left} hari lagi')
        if task.priority == 'URGENT':
            reasons.append('Prioritas urgent')
        if task.progress == 0:
            reasons.append('Belum mulai')
        if not reasons:
            reasons.append('Prio tinggi')

        results.append(
            dict(
                task.to_dict(),
                urgency_score=score,
                reasons=reasons,
            )
        )

    return results


def full_report(user_id=None):
    """Gabungkan semua analisis jadi satu laporan."""
    return {
        'generated_at': utcnow().isoformat(),
        'summary': summary(user_id),
        'by_status': by_status(user_id),
        'by_priority': by_priority(user_id),
        'by_course': by_course(user_id),
        'productivity': productivity(user_id),
        'stuck': stuck_tasks(user_id),
        'upcoming': upcoming(user_id),
        'forecast': forecast(user_id),
        'suggestions': suggest(user_id),
    }
