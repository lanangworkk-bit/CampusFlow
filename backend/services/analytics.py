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

from backend.extensions import db
from backend.models import Course, Note, Task, today, utcnow


# ---------------------------------------------------------------- statistik

def _pct(numerator, denominator):
    """Persentase, aman dari pembagian dengan nol."""
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def summary(user_id=None):
    query = Task.query
    if user_id:
        query = query.filter_by(user_id=user_id)

    tasks = query.all()
    total = len(tasks)

    # Hitung dari effective_status(), bukan dari kolom status mentah.
    #
    # Status OVERDUE tidak pernah tersimpan di database; dia dihitung
    # dari perbandingan deadline dengan tanggal sekarang. Kalau
    # in_progress dan todo dihitung dari kolom mentah, sebuah tugas
    # yang lewat tenggat akan terhitung di OVERDUE sekaligus di
    # IN PROGRESS, sehingga jumlah status melebihi total tugas.
    #
    # Dengan effective_status(), keempat status ini saling lepas dan
    # jumlahannya selalu sama dengan total.
    buckets = {'COMPLETED': 0, 'OVERDUE': 0, 'IN PROGRESS': 0, 'TODO': 0}
    for task in tasks:
        status = task.effective_status()
        if status in buckets:
            buckets[status] += 1
        else:
            buckets['TODO'] += 1

    done = buckets['COMPLETED']
    overdue = buckets['OVERDUE']
    in_progress = buckets['IN PROGRESS']
    todo = buckets['TODO']

    progress_total = sum(t.progress for t in tasks)

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
    query = Task.query
    if user_id:
        query = query.filter_by(user_id=user_id)

    counts = Counter(t.effective_status() for t in query.all())
    return [
        {'status': key, 'count': counts.get(key, 0)}
        for key in ('TODO', 'IN PROGRESS', 'COMPLETED', 'OVERDUE')
    ]


def by_priority(user_id=None):
    query = Task.query
    if user_id:
        query = query.filter_by(user_id=user_id)

    counts = Counter(t.priority for t in query.all())
    return [
        {'priority': key, 'count': counts.get(key, 0)}
        for key in ('URGENT', 'HIGH', 'MEDIUM', 'LOW')
    ]


def by_course(user_id=None):
    query = Task.query
    if user_id:
        query = query.filter_by(user_id=user_id)

    grouped = {}
    for task in query.all():
        name = task.course.name if task.course else 'Tanpa Mata Kuliah'
        entry = grouped.setdefault(
            name,
            {'course': name, 'total': 0, 'completed': 0, 'progress': 0},
        )
        entry['total'] += 1
        entry['progress'] += task.progress
        if task.status == 'COMPLETED':
            entry['completed'] += 1

    rows = []
    for entry in grouped.values():
        entry['completion_rate'] = _pct(entry['completed'], entry['total'])
        entry['average_progress'] = round(
            entry['progress'] / entry['total'], 1
        ) if entry['total'] else 0
        rows.append(entry)

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

    limit_date = (date.today() + timedelta(days=days)).isoformat()
    rows = query.filter(Task.deadline <= limit_date).all()
    return [
        dict(t.to_dict(), days_left=_days_left(t.deadline)) for t in rows
    ]


def _days_left(deadline):
    if not deadline:
        return None
    try:
        target = date.fromisoformat(deadline)
    except ValueError:
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

    scored.sort(key=lambda pair: (-pair[0], pair[1].deadline or '9999'))

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
