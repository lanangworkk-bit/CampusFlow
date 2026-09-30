"""Route untuk CRUD task.

Blueprint dengan url_prefix='/api/tasks' berarti semua route di
file ini otomatis diawali /api/tasks, jadi tidak perlu menulis
prefix-nya berulang-ulang di setiap route.
"""

from flask import Blueprint, jsonify, request

from db import get_db, todayISO

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/tasks')

SORTABLE_COLUMNS = ('deadline', 'title', 'priority', 'status', 'created_at')

# OVERDUE tidak disimpan sebagai nilai di kolom status, tapi user
# tetap boleh memfilter dengannya karena itu status turunan yang
# dipakai di frontend.
VALID_STATUSES = ('TODO', 'IN PROGRESS', 'COMPLETED', 'OVERDUE')
VALID_PRIORITIES = ('LOW', 'MEDIUM', 'HIGH', 'URGENT')

VALID_ORDERS = ('ASC', 'DESC')
MAX_LIMIT = 200


def fetch_tasks():
    """Bangun query dari parameter URL lalu jalankan.

    Contoh URL:
        /api/tasks
        /api/tasks?status=TODO
        /api/tasks?search=flutter&priority=HIGH
        /api/tasks?sort=title&order=desc
        /api/tasks?limit=10&offset=20
    """
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    priority = request.args.get('priority', '').strip()
    sort = request.args.get('sort', 'deadline').strip()
    order = request.args.get('order', 'asc').strip().upper()
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', type=int)

    # Validasi input user.
    # Nama kolom TIDAK bisa jadi parameter SQL (?), jadi harus
    # dicek dulu terhadap daftar yang diizinkan (whitelist).
    # Tanpa ini, user bisa menulis: ?sort=id; DROP TABLE tasks
    if sort not in SORTABLE_COLUMNS:
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
        clauses.append('(title LIKE ? OR description LIKE ?)')
        keyword = f'%{search}%'
        params.extend([keyword, keyword])

    if status:
        if status == 'OVERDUE':
            clauses.append(
                "status != 'COMPLETED' "
                "AND deadline IS NOT NULL AND deadline < ?"
            )
            params.append(todayISO())
        else:
            clauses.append('status = ?')
            params.append(status)

    if priority:
        clauses.append('priority = ?')
        params.append(priority)

    sql = 'SELECT * FROM tasks'
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)

    # sort dan order sudah divalidasi di atas, jadi aman dipasang.
    sql += f' ORDER BY {sort} {order}, id ASC'

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


@tasks_bp.route('', methods=['POST'])
def create_task():
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'error': 'Title is required'}), 400

    priority = data.get('priority', 'MEDIUM')
    if priority not in VALID_PRIORITIES:
        priority = 'MEDIUM'

    db = get_db()
    cursor = db.execute(
        'INSERT INTO tasks (title, description, deadline, priority)'
        ' VALUES (?, ?, ?, ?)',
        (
            data['title'].strip(),
            data.get('description', '').strip(),
            data.get('deadline') or None,
            priority,
        ),
    )
    db.commit()
    row = db.execute(
        'SELECT * FROM tasks WHERE id = ?', (cursor.lastrowid,)
    ).fetchone()
    result = dict(row)
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

    # Aturan bisnis, di server supaya tidak bisa di-bypass dari browser:
    #   - status COMPLETED  -> progress dipaksa 100
    #   - dari COMPLEMENTED  -> tidak lagi selesai, progress kembali 0
    if status == 'COMPLETED':
        progress = 100
    elif existing['status'] == 'COMPLETED' and status != 'COMPLETED':
        progress = 0

    db.execute(
        'UPDATE tasks SET title = ?, description = ?, deadline = ?,'
        ' priority = ?, status = ?, progress = ? WHERE id = ?',
        (
            title,
            description,
            deadline or None,
            priority,
            status,
            progress,
            task_id,
        ),
    )
    db.commit()
    row = db.execute(
        'SELECT * FROM tasks WHERE id = ?', (task_id,)
    ).fetchone()
    result = dict(row)
    db.close()
    return jsonify(result)


@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Task deleted'})
