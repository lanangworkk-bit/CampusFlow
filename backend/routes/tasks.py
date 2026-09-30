"""Route untuk CRUD task.

Blueprint dengan url_prefix='/api/tasks' berarti semua route di
file ini otomatis diawali /api/tasks, jadi tidak perlu menulis
prefix-nya berulang-ulang di setiap route.
"""

from flask import Blueprint, jsonify, request

from db import get_db, todayISO

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/tasks')

# OVERDUE tidak disimpan sebagai nilai di kolom status, tapi user
# tetap boleh memfilter dengannya karena itu status turunan yang
# dipakai di frontend.
VALID_STATUSES = ('TODO', 'IN PROGRESS', 'COMPLETED', 'OVERDUE')
VALID_PRIORITIES = ('LOW', 'MEDIUM', 'HIGH', 'URGENT')

VALID_ORDERS = ('ASC', 'DESC')
MAX_LIMIT = 200

SORT_EXPRESSIONS = {
    'deadline': 't.deadline',
    'title': 't.title',
    'priority': 't.priority',
    'status': 't.status',
    'created_at': 't.created_at',
}

# Kolom yang boleh difilter, dipetakan ke kolom di tabel tasks.
# Ditulis eksplisit supaya tidak ada kolom tak terduga yang bisa dipakai.
FILTERABLE = {
    'priority': 't.priority',
    'title': 't.title',
    'description': 't.description',
}


def fetch_tasks():
    """Bangun query dari parameter URL lalu jalankan.

    Contoh URL:
        /api/tasks
        /api/tasks?status=TODO
        /api/tasks?search=flutter&priority=HIGH
        /api/tasks?sort=title&order=desc
        /api/tasks?course_id=2
        /api/tasks?limit=10&offset=20
    """
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    priority = request.args.get('priority', '').strip()
    course_id = request.args.get('course_id', type=int)
    sort = request.args.get('sort', 'deadline').strip()
    order = request.args.get('order', 'asc').strip().upper()
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', type=int)

    # Validasi input user.
    # Nama kolom TIDAK bisa jadi parameter SQL (?), jadi harus
    # dicek dulu terhadap daftar yang diizinkan (whitelist).
    # Tanpa ini, user bisa menulis: ?sort=id; DROP TABLE tasks
    if sort not in SORT_EXPRESSIONS:
        sort = 'deadline'
    if order not in VALID_ORDERS:
        order = 'ASC'
    if status and status not in VALID_STATUSES:
        status = ''
    if priority and priority not in VALID_PRIORITIES:
        priority = ''

    clauses = []
    params = []

    if search:
        clauses.append('(t.title LIKE ? OR t.description LIKE ?)')
        keyword = f'%{search}%'
        params.extend([keyword, keyword])

    if status:
        if status == 'OVERDUE':
            clauses.append(
                "t.status != 'COMPLETED' "
                "AND t.deadline IS NOT NULL AND t.deadline < ?"
            )
            params.append(todayISO())
        else:
            clauses.append('t.status = ?')
            params.append(status)

    if priority:
        clauses.append('t.priority = ?')
        params.append(priority)

    if course_id is not None:
        clauses.append('t.course_id = ?')
        params.append(course_id)

    # LEFT JOIN: ambil semua task, plus nama mata kuliah kalau ada.
    # Kalau pakai JOIN (bukan LEFT JOIN), task tanpa mata kuliah
    # akan hilang dari daftar. Untuk LEFT JOIN, course_name = NULL.
    sql = (
        'SELECT t.*, c.name AS course_name, c.code AS course_code '
        'FROM tasks t '
        'LEFT JOIN courses c ON t.course_id = c.id'
    )
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)

    # sort sudah divalidasi di atas, jadi aman dipasang.
    sql += f' ORDER BY {SORT_EXPRESSIONS[sort]} {order}, t.id ASC'

    if limit is not None:
        sql += ' LIMIT ?'
        params.append(max(1, min(limit, MAX_LIMIT)))
        if offset is not None:
            sql += ' OFFSET ?'
            params.append(max(0, offset))

    db = get_db()
    rows = db.execute(sql, params).fetchall()
    result = [dict(row) for row in rows]
    db.close()
    return result


@tasks_bp.route('', methods=['GET'])
def get_tasks():
    return jsonify(fetch_tasks())


def find_task(db, task_id):
    """Ambil satu task lengkap dengan nama mata kuliahnya."""
    row = db.execute(
        'SELECT t.*, c.name AS course_name, c.code AS course_code '
        'FROM tasks t '
        'LEFT JOIN courses c ON t.course_id = c.id '
        'WHERE t.id = ?',
        (task_id,),
    ).fetchone()
    return dict(row) if row else None


def valid_course_id(db, value):
    """Pastikan course_id menunjuk ke mata kuliah yang benar-benar ada.

    Foreign key sudah menjaga integritas di level database, tapi
    pengecekan di sini memberi pesan error yang jelas untuk user
    dan menghemat request yang tidak perlu menyentuh database.
    """
    if value is None:
        return None
    try:
        course_id = int(value)
    except (TypeError, ValueError):
        return None
    if course_id <= 0:
        return None
    exists = db.execute(
        'SELECT 1 FROM courses WHERE id = ?', (course_id,)
    ).fetchone()
    return course_id if exists else None

@tasks_bp.route('', methods=['POST'])
def create_task():
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'error': 'Title is required'}), 400

    priority = data.get('priority', 'MEDIUM')
    if priority not in VALID_PRIORITIES:
        priority = 'MEDIUM'

    db = get_db()
    course_id = valid_course_id(db, data.get('course_id'))

    cursor = db.execute(
        'INSERT INTO tasks (title, description, deadline, priority, course_id)'
        ' VALUES (?, ?, ?, ?, ?)',
        (
            data['title'].strip(),
            data.get('description', '').strip(),
            data.get('deadline') or None,
            priority,
            course_id,
        ),
    )
    db.commit()
    result = find_task(db, cursor.lastrowid)
    db.close()
    return jsonify(result), 201


@tasks_bp.route('/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    db = get_db()
    existing = db.execute(
        'SELECT * FROM tasks WHERE id = ?', (task_id,)
    ).fetchone()

    if existing is None:
        db.close()
        return jsonify({'error': 'Task not found'}), 404

    # Field yang tidak dikirim pakai nilai yang sudah ada,
    # jadi update hanya mengubah bagian yang diminta saja.
    title = data.get('title', existing['title']).strip()
    if not title:
        db.close()
        return jsonify({'error': 'Title cannot be empty'}), 400

    description = data.get('description', existing['description'])
    deadline = data.get('deadline', existing['deadline'])
    priority = data.get('priority', existing['priority'])
    status = data.get('status', existing['status'])
    progress = data.get('progress', existing['progress'])

    if priority not in VALID_PRIORITIES:
        priority = existing['priority']
    # OVERDUE itu status turunan, tidak boleh disimpan sebagai nilai.
    if status not in VALID_STATUSES or status == 'OVERDUE':
        status = existing['status']
    try:
        progress = int(progress)
    except (TypeError, ValueError):
        progress = existing['progress']
    if not 0 <= progress <= 100:
        progress = existing['progress']

    # Kirim course_id = null untuk melepas tugas dari mata kuliah.
    # Kalau field-nya tidak dikirim sama sekali, biarkan yang ada.
    if 'course_id' in data:
        course_id = valid_course_id(db, data.get('course_id'))
    else:
        course_id = existing['course_id']

    # Aturan bisnis, di server supaya tidak bisa di-bypass dari browser:
    #   - status COMPLETED  -> progress dipaksa 100
    #   - dari COMPLETED    -> tidak lagi selesai, progress kembali 0
    if status == 'COMPLETED':
        progress = 100
    elif existing['status'] == 'COMPLETED' and status != 'COMPLETED':
        progress = 0

    db.execute(
        'UPDATE tasks SET title = ?, description = ?, deadline = ?,'
        ' priority = ?, status = ?, progress = ?, course_id = ? WHERE id = ?',
        (
            title,
            description,
            deadline or None,
            priority,
            status,
            progress,
            course_id,
            task_id,
        ),
    )
    db.commit()
    result = find_task(db, task_id)
    db.close()
    return jsonify(result)


@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Task deleted'})
