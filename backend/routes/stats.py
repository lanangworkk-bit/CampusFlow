"""Route statistik untuk dashboard.

Semua perhitungan di sini dikerjakan oleh SQLite (COUNT, SUM, AVG,
GROUP BY), bukan oleh JavaScript. Alasannya:

  - Data tidak perlu dikirim ke browser hanya untuk dihitung
  - Untuk data banyak, satu query di database jauh lebih cepat
    daripada mengirim ribuan baris ke browser lalu dihitung di sana
  - Satu sumber kebenaran, jadi frontend dan backend tidak mungkin
    menghitung angka yang berbeda
"""

from flask import Blueprint, jsonify, request

from db import get_db, todayISO

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')


@stats_bp.route('', methods=['GET'])
def get_stats():
    db = get_db()
    today = todayISO()

    # --- Ringkasan umum, semua dalam satu baris ---
    # Ada 4 tanda ? di query ini, jadi 4 nilai yang dikirim,
    # semuanya tanggal hari ini.
    summary = db.execute(
        """
        SELECT
            COUNT(*)                                          AS total,
            SUM(status = 'COMPLETED')                         AS completed,
            SUM(status = 'IN PROGRESS')                       AS in_progress,
            SUM(status = 'TODO')                              AS todo,
            SUM(
                status != 'COMPLETED'
                AND deadline IS NOT NULL
                AND deadline < ?
            )                                                 AS overdue,
            SUM(deadline = ?)                                 AS due_today,
            SUM(
                deadline IS NOT NULL
                AND deadline > ?
                AND deadline <= date(?, '+7 days')
            )                                                 AS due_this_week,
            SUM(deadline IS NULL)                             AS no_deadline
        FROM tasks
        """,
        (today, today, today, today),
    ).fetchone()

    # SUM() mengembalikan NULL kalau tidak ada baris sama sekali.
    # Di Python itu jadi None, dan None akan bikin error saat
    # dipakai di arithmetic, jadi semua diganti 0.
    stats = {key: (summary[key] or 0) for key in summary.keys()}

    completion_rate = 0
    if stats['total'] > 0:
        completion_rate = round(stats['completed'] / stats['total'] * 100)

    # --- Jumlah task per prioritas ---
    by_priority = [
        dict(row)
        for row in db.execute(
            """
            SELECT priority, COUNT(*) AS total,
                   SUM(status = 'COMPLETED') AS completed
            FROM tasks
            GROUP BY priority
            ORDER BY total DESC
            """
        )
    ]
    for row in by_priority:
        row['completed'] = row['completed'] or 0

    # --- Jumlah task per status ---
    by_status = [
        dict(row)
        for row in db.execute(
            'SELECT status, COUNT(*) AS total FROM tasks GROUP BY status'
        )
    ]

    # --- Jumlah task per mata kuliah (hasil JOIN) ---
    # LEFT JOIN supaya mata kuliah tanpa task tetap muncul dengan
    # total 0. Kalau pakai JOIN, mata kuliah sepi akan hilang.
    by_course = [
        dict(row)
        for row in db.execute(
            """
            SELECT
                c.id,
                c.name,
                c.code,
                COUNT(t.id)             AS total,
                SUM(t.status = 'COMPLETED') AS completed
            FROM courses c
            LEFT JOIN tasks t ON t.course_id = c.id
            GROUP BY c.id
            ORDER BY total DESC, c.name ASC
            """
        )
    ]
    for row in by_course:
        row['completed'] = row['completed'] or 0

    # --- Mata kuliah paling menumpuk: tempat tugas paling banyak ---
    # Hanya yang punya minimal 1 task, diurutkan dari yang paling banyak.
    busiest = [row for row in by_course if row['total'] > 0][:3]

    # --- Rata-rata progres per mata kuliah ---
    progress_by_course = [
        dict(row)
        for row in db.execute(
            """
            SELECT c.name, COUNT(t.id) AS total, AVG(t.progress) AS avg_progress
            FROM courses c
            JOIN tasks t ON t.course_id = c.id
            GROUP BY c.id
            HAVING COUNT(t.id) > 0
            ORDER BY avg_progress ASC
            """
        )
    ]
    for row in progress_by_course:
        row['avg_progress'] = round(row['avg_progress'] or 0)

    # --- Deadline terdekat yang belum selesai ---
    upcoming = [
        dict(row)
        for row in db.execute(
            """
            SELECT id, title, deadline, priority
            FROM tasks
            WHERE status != 'COMPLETED' AND deadline IS NOT NULL
            ORDER BY deadline ASC
            LIMIT ?
            """,
            (request.args.get('limit', 5, type=int),),
        )
    ]

    # --- Task terlama belum selesai ---
    stuck = [
        dict(row)
        for row in db.execute(
            """
            SELECT id, title, deadline, progress
            FROM tasks
            WHERE status != 'COMPLETED'
            ORDER BY created_at ASC
            LIMIT 3
            """
        )
    ]

    db.close()

    return jsonify({
        'summary': stats,
        'completion_rate': completion_rate,
        'by_priority': by_priority,
        'by_status': by_status,
        'by_course': by_course,
        'busiest_courses': busiest,
        'progress_by_course': progress_by_course,
        'upcoming': upcoming,
        'stuck': stuck,
    })
