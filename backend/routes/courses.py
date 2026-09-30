"""Route untuk daftar mata kuliah.

Mata kuliah bersifat data referensi yang relatif tetap, jadi
hanya tersedia operasi baca (GET), tambah (POST), dan hapus (DELETE).
"""

from flask import Blueprint, jsonify, request

from db import get_db

courses_bp = Blueprint('courses', __name__, url_prefix='/api/courses')

VALID_SKS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
VALID_ORDERS = ('ASC', 'DESC')
DEFAULT_PER_PAGE = 6
MAX_PER_PAGE = 50

# Sama seperti di tasks: nama kolom harus lewat whitelist.
SORT_EXPRESSIONS = {
    'name': 'c.name',
    'code': 'c.code',
    'sks': 'c.sks',
    'day': 'c.day',
    'time': 'c.time',
}


@courses_bp.route('', methods=['GET'])
def get_courses():
    """Daftar mata kuliah dengan pencarian, sorting, dan pagination.

    Contoh:
        /api/courses
        /api/courses?search=data&sort=sks&order=desc
        /api/courses?page=2&per_page=6

    Response-nya objek, bukan array, karena pagination butuh
    informasi jumlah total dan halaman terakhir.
    """
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'name').strip()
    order = request.args.get('order', 'asc').strip().upper()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', DEFAULT_PER_PAGE, type=int)

    if sort not in SORT_EXPRESSIONS:
        sort = 'name'
    if order not in VALID_ORDERS:
        order = 'ASC'
    page = max(1, page or 1)
    per_page = max(1, min(per_page or DEFAULT_PER_PAGE, MAX_PER_PAGE))

    clauses = []
    params = []

    if search:
        clauses.append('(c.name LIKE ? OR c.code LIKE ? OR c.lecturer LIKE ?)')
        keyword = f'%{search}%'
        params.extend([keyword, keyword, keyword])

    where = ''
    if clauses:
        where = ' WHERE ' + ' AND '.join(clauses)

    db = get_db()

    # COUNT tanpa LIMIT: berapa total data yang cocok filter.
    # Dipakai untuk tahu jumlah halaman, jadi harus dihitung
    # SEBELUM query utama dipaginasi.
    total = db.execute(
        f'SELECT COUNT(*) AS n FROM courses c{where}', params
    ).fetchone()['n']

    total_pages = max(1, (total + per_page - 1) // per_page)
    # Kalau user minta halaman di luar jangkauan, balancer ke
    # halaman terakhir supaya tidak tampil kosong melompong.
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    # LEFT JOIN tasks supaya bisa sekaligus menampilkan berapa
    # task per mata kuliah tanpa query kedua (N+1 problem).
    rows = db.execute(
        f"""
        SELECT
            c.*,
            COUNT(t.id)                AS task_count,
            SUM(t.status = 'COMPLETED') AS task_done
        FROM courses c
        LEFT JOIN tasks t ON t.course_id = c.id
        {where}
        GROUP BY c.id
        ORDER BY {SORT_EXPRESSIONS[sort]} {order}, c.name ASC
        LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    ).fetchall()

    items = [dict(row) for row in rows]
    for item in items:
        item['task_done'] = item['task_done'] or 0

    db.close()

    return jsonify({
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
    })


@courses_bp.route('/options', methods=['GET'])
def course_options():
    """Daftar ringkas semua mata kuliah untuk mengisi dropdown.

    Endpoint ini SENGAJA tidak dipaginasi dan tidak mengembalikan
    data lengkap. Alasannya: dropdown di form task harus bisa
    memilih mata kuliah dari halaman mana pun, dan isinya cuma
    id + nama. Kalau ikut pagination, user tidak bisa memilih
    mata kuliah yang ada di halaman 3.
    """
    db = get_db()
    rows = db.execute(
        'SELECT id, name, code FROM courses ORDER BY name ASC'
    ).fetchall()
    result = [dict(row) for row in rows]
    db.close()
    return jsonify(result)


@courses_bp.route('', methods=['POST'])
def create_course():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400

    sks = data.get('sks', 3)
    if sks not in VALID_SKS:
        sks = 3

    db = get_db()
    cursor = db.execute(
        'INSERT INTO courses (name, code, sks, lecturer, day, time, room)'
        ' VALUES (?, ?, ?, ?, ?, ?, ?)',
        (
            data['name'].strip(),
            data.get('code', '').strip(),
            sks,
            data.get('lecturer', '').strip(),
            data.get('day', '').strip(),
            data.get('time', '').strip(),
            data.get('room', '').strip(),
        ),
    )
    db.commit()
    row = db.execute(
        'SELECT * FROM courses WHERE id = ?', (cursor.lastrowid,)
    ).fetchone()
    result = dict(row)
    db.close()
    return jsonify(result), 201


@courses_bp.route('/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    db = get_db()
    db.execute('DELETE FROM courses WHERE id = ?', (course_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Course deleted'})
