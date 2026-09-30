"""CRUD task, mata kuliah, dan catatan memakai SQLAlchemy ORM.

Bedanya dengan versi raw SQL: filter, sort, dan paginasi dirangkai dengan
query builder, jadi tidak ada lagi string SQL yang digabung manual.
Parameterized query tetap dijamin karena SQLAlchemy memakai bind parameter.
"""

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import String, cast, or_, func

from backend.extensions import db, limiter
from backend.models import Course, Note, Task, TASK_PRIORITIES, TASK_STATUSES, utcnow
from backend.routes.auth import current_user, roles_required
from backend.services.security import body, clean_text, log, validate_body


def body_text(value, max_length):
    """ Bersihkan satu nilai yang punya batas panjang khusus.

    body() sudah membersihkan tag dan karakter berbahaya, ini cuma
    menambahkan batas panjang per-field (judul 200 karakter, dsb).
    """
    return clean_text(value, max_length) if value is not None else None

resources_bp = Blueprint('resources', __name__, url_prefix='/api')

MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 20

# Nama kolom yang boleh dipesan user. Kalau tidak ada di sini,
# input user diabaikan dan diganti default. Ini yang mencegah
# SQL injection lewat parameter sort.
TASK_SORTS = {
    'deadline': lambda: func.coalesce(Task.deadline, '9999-12-31'),
    'title': lambda: Task.title,
    'priority': lambda: Task.priority,
    'status': lambda: Task.status,
    'progress': lambda: Task.progress,
    'created_at': lambda: Task.created_at,
    'updated_at': lambda: Task.updated_at,
}

COURSE_SORTS = {
    'name': lambda: Course.name,
    'code': lambda: Course.code,
    'sks': lambda: Course.sks,
}


def _paginate(query, model, default_sort):
    """Bikin respons berpaginasi dari sebuah query."""
    page = request.args.get('page', 1, type=int) or 1
    per_page = request.args.get('per_page', DEFAULT_PER_PAGE, type=int) or DEFAULT_PER_PAGE
    per_page = max(1, min(per_page, MAX_PER_PAGE))

    sort_key = request.args.get('sort', default_sort)
    order = request.args.get('order', 'asc').lower()

    # Sort hanya boleh memakai nama yang ada di whitelist. Kalau tidak
    # ketemu, pakai default. Nama kolom dari user TIDAK PERNAH
    # diteruskan apa adanya ke query, itu yang mencegah SQL injection
    # lewat parameter sort.
    sorts = TASK_SORTS if model is Task else COURSE_SORTS
    factory = sorts.get(sort_key)
    if factory is None:
        factory = lambda: model.__table__.columns[default_sort]

    sort_expr = factory()
    if order == 'desc':
        sort_expr = sort_expr.desc()
    query = query.order_by(sort_expr)

    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
    if page < 1:
        page = 1

    items = query.limit(per_page).offset((page - 1) * per_page).all()
    return {
        'items': [i.to_dict() for i in items],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'has_next': page < total_pages,
        'has_prev': page > 1,
    }


def _error(message, code=400, **extra):
    body = {'error': message}
    body.update(extra)
    return jsonify(body), code


def _owner_filter(query):
    """Batasi hasil ke milik user yang sedang login.

    Admin melihat semua data, student hanya miliknya sendiri.
    """
    user = current_user()
    if user and user.role == 'admin':
        return query
    if user:
        return query.filter(Task.user_id == user.id)
    return query


# ------------------------------------------------------------------- TASK

@resources_bp.route('/tasks', methods=['GET'])
@jwt_required()
def list_tasks():
    query = _owner_filter(Task.query)

    search = (request.args.get('search') or '').strip()
    if search:
        pattern = f'%{search}%'
        query = query.filter(
            or_(Task.title.ilike(pattern), Task.description.ilike(pattern))
        )

    status = (request.args.get('status') or '').strip()
    if status == 'OVERDUE':
        query = query.filter(
            Task.status != 'COMPLETED',
            Task.deadline.isnot(None),
            Task.deadline < date.today().isoformat(),
        )
    elif status in TASK_STATUSES:
        # Penting: filter harus memakai STATUS YANG SAMA dengan yang
        # ditampilkan. Kolom status di database menyimpan nilai mentah,
        # sedangkan yang tampil ke user adalah effective_status() yang
        # mengubah TODO jadi OVERDUE kalau tenggatnya sudah lewat.
        #
        # Kalau filter ini cuma mencocokkan kolom mentah, task yang
        # tampilannya OVERDUE akan ikut muncul di filter "TODO".
        # Dua-duanya harus memakai aturan yang sama.
        query = query.filter(Task.status == status)
        if status != 'COMPLETED':
            query = query.filter(
                or_(
                    Task.deadline.is_(None),
                    Task.deadline >= date.today().isoformat(),
                )
            )

    priority = (request.args.get('priority') or '').strip()
    if priority in TASK_PRIORITIES:
        query = query.filter_by(priority=priority)

    course_id = request.args.get('course_id', type=int)
    if course_id:
        query = query.filter_by(course_id=course_id)

    return jsonify(_paginate(query, Task, 'deadline')), 200


@resources_bp.route('/tasks', methods=['POST'])
@jwt_required()
@validate_body()
def create_task():
    data = body()
    title = body_text(data.get('title'), 200)
    if not title:
        return _error('Title is required', details={'field': 'title'})

    priority = data.get('priority')
    if priority is not None and priority not in TASK_PRIORITIES:
        return _error(
            'Priority harus salah satu dari: ' + ', '.join(TASK_PRIORITIES),
            details={'field': 'priority'},
        )

    status = data.get('status')
    if status is not None and status not in TASK_STATUSES:
        return _error(
            'Status harus salah satu dari: ' + ', '.join(TASK_STATUSES),
            details={'field': 'status'},
        )

    deadline, error = _valid_deadline(data.get('deadline'))
    if error:
        return _error(error, details={'field': 'deadline'})

    user = current_user()
    course_id = _valid_course(data.get('course_id'))
    if course_id is False:
        return _error('Mata kuliah tidak ditemukan', details={'field': 'course_id'})

    task = Task(
        title=title,
        description=body_text(data.get('description'), 5000) or '',
        status=status or 'TODO',
        priority=priority or 'MEDIUM',
        deadline=deadline,
        course_id=course_id,
        user_id=user.id if user else None,
    )

    # Progress boleh dikirim saat create, tapi tetap harus berupa angka
    # dan berada di rentang 0-100.
    if 'progress' in data:
        try:
            progress = int(data['progress'])
        except (TypeError, ValueError):
            return _error('Progress harus angka', details={'field': 'progress'})
        if not 0 <= progress <= 100:
            return _error(
                'Progress harus antara 0 dan 100', details={'field': 'progress'}
            )
        task.progress = progress

    # Aturan bisnis: status COMPLETED selalu berarti progress 100.
    if task.status == 'COMPLETED':
        task.progress = 100
        task.completed_at = utcnow()

    db.session.add(task)
    db.session.commit()

    log('create', 'task', task.id, user)
    return jsonify(task.to_dict()), 201


@resources_bp.route('/tasks/<int:task_id>', methods=['GET'])
@jwt_required()
def get_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None:
        return _error('Task not found', code=404)
    user = current_user()
    if user and task.user_id and task.user_id != user.id and user.role != 'admin':
        return _error('Task not found', code=404)
    return jsonify(task.to_dict()), 200


@resources_bp.route('/tasks/<int:task_id>', methods=['PUT', 'PATCH'])
@jwt_required()
@validate_body()
def update_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None:
        return _error('Task not found', code=404)

    user = current_user()
    if user and task.user_id and task.user_id != user.id and user.role != 'admin':
        return _error('Task not found', code=404)

    data = body()

    if 'title' in data:
        title = body_text(data.get('title'), 200)
        if not title:
            return _error('Title cannot be empty')
        task.title = title

    if 'description' in data:
        task.description = body_text(data.get('description'), 5000) or ''

    if 'deadline' in data:
        deadline, error = _valid_deadline(data['deadline'])
        if error:
            return _error(error, details={'field': 'deadline'})
        task.deadline = deadline

    if data.get('priority') in TASK_PRIORITIES:
        task.priority = data['priority']

    if 'status' in data:
        status = data['status']
        if status not in TASK_STATUSES:
            return _error(
                'Status harus salah satu dari: '
                + ', '.join(TASK_STATUSES),
                details={'field': 'status'},
            )
        was_done = task.status == 'COMPLETED'
        task.status = status
        # Aturan bisnis di server supaya tidak bisa dilewati dari browser.
        if status == 'COMPLETED':
            task.progress = 100
            task.completed_at = utcnow()
        elif was_done:
            task.progress = 0
            task.completed_at = None

    if 'progress' in data and task.status != 'COMPLETED':
        try:
            progress = int(data['progress'])
        except (TypeError, ValueError):
            return _error('Progress harus angka', details={'field': 'progress'})
        if not 0 <= progress <= 100:
            return _error(
                'Progress harus antara 0 dan 100',
                details={'field': 'progress'},
            )
        task.progress = progress

    if 'course_id' in data:
        course_id = _valid_course(data['course_id'])
        if course_id is False:
            return _error('Mata kuliah tidak ditemukan', details={'field': 'course_id'})
        task.course_id = course_id

    task.updated_at = utcnow()
    db.session.commit()

    log('update', 'task', task.id, user)
    return jsonify(task.to_dict()), 200


@resources_bp.route('/tasks/<int:task_id>', methods=['DELETE'])
@jwt_required()
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None:
        return _error('Task not found', code=404)
    user = current_user()
    if user and task.user_id and task.user_id != user.id and user.role != 'admin':
        return _error('Task not found', code=404)

    db.session.delete(task)
    db.session.commit()

    log('delete', 'task', task_id, user)
    return jsonify({'message': 'Task deleted'}), 200


def _valid_deadline(value):
    """Coba ubah input jadi YYYY-MM-DD."""
    if value is None or str(value).strip() == '':
        return None, None
    text = str(value).strip()
    try:
        return date.fromisoformat(text).isoformat(), None
    except ValueError:
        return None, 'Format tanggal harus YYYY-MM-DD'


def _valid_course(value):
    """Balik id course yang valid, atau None, atau False kalau tidak ada."""
    if value in (None, '', 0):
        return None
    try:
        course_id = int(value)
    except (TypeError, ValueError):
        return False
    if course_id <= 0:
        return False
    return course_id if db.session.get(Course, course_id) else False


# ----------------------------------------------------------------- COURSE

@resources_bp.route('/courses', methods=['GET'])
@jwt_required()
def list_courses():
    query = Course.query
    search = (request.args.get('search') or '').strip()
    if search:
        pattern = f'%{search}%'
        query = query.filter(
            or_(
                Course.name.ilike(pattern),
                Course.code.ilike(pattern),
                Course.lecturer.ilike(pattern),
            )
        )

    result = _paginate(query, Course, 'name')

    # Tambahkan jumlah task per course. Kalau dihitung satu per course
    # di loop, itu berarti N query. Sekalian dikelompokkan jadi 2 query.
    counts = dict(
        db.session.query(Task.course_id, func.count(Task.id))
        .group_by(Task.course_id)
        .all()
    )
    done = dict(
        db.session.query(Task.course_id, func.count(Task.id))
        .filter(Task.status == 'COMPLETED')
        .group_by(Task.course_id)
        .all()
    )
    for item in result['items']:
        item['task_count'] = counts.get(item['id'], 0)
        item['task_done'] = done.get(item['id'], 0)
    return jsonify(result), 200


@resources_bp.route('/courses/options', methods=['GET'])
@jwt_required()
def course_options():
    rows = Course.query.order_by(Course.name).all()
    return jsonify(
        [{'id': c.id, 'name': c.name, 'code': c.code} for c in rows]
    ), 200


@resources_bp.route('/courses', methods=['POST'])
@jwt_required()
@validate_body()
def create_course():
    data = body()
    name = body_text(data.get('name'), 120)
    code = body_text(data.get('code'), 20)
    if not name or not code:
        return _error('Name dan code wajib diisi')

    if Course.query.filter_by(code=code).first():
        return _error('Kode mata kuliah sudah ada', code=409)

    # SKS dibatasi 0-12. Nilai di luar itu ditolak, bukan dipotong diam-diam,
    # supaya user tahu kalau input-nya salah.
    try:
        sks = int(data.get('sks', 3))
    except (TypeError, ValueError):
        return _error('SKS harus angka', details={'field': 'sks'})
    if not 0 <= sks <= 12:
        return _error('SKS harus antara 0 dan 12', details={'field': 'sks'})

    course = Course(
        name=name,
        code=code.upper(),
        lecturer=body_text(data.get('lecturer'), 120),
        sks=sks,
        room=body_text(data.get('room'), 80),
        day=body_text(data.get('day'), 20),
        time=body_text(data.get('time'), 40),
        color=body_text(data.get('color'), 20),
    )

    db.session.add(course)
    db.session.commit()

    user = current_user()
    log('create', 'course', course.id, user)
    return jsonify(course.to_dict(include_stats=True)), 201


@resources_bp.route('/courses/<int:course_id>', methods=['PUT'])
@jwt_required()
@validate_body()
def update_course(course_id):
    course = db.session.get(Course, course_id)
    if course is None:
        return _error('Course not found', code=404)
    data = body()

    if 'name' in data:
        name = body_text(data['name'], 120)
        if not name:
            return _error('Name tidak boleh kosong')
        course.name = name
    if 'code' in data:
        code = body_text(data['code'], 20)
        if not code:
            return _error('Code tidak boleh kosong')
        if Course.query.filter(Course.code == code.upper(), Course.id != course_id).first():
            return _error('Kode sudah dipakai', code=409)
        course.code = code.upper()
    for field in ('lecturer', 'room', 'day', 'time', 'color'):
        if field in data:
            setattr(course, field, clean_text(data[field], 120))
    if 'sks' in data:
        try:
            course.sks = max(0, min(int(data['sks']), 12))
        except (TypeError, ValueError):
            return _error('SKS harus angka')

    db.session.commit()
    log('update', 'course', course.id, current_user())
    return jsonify(course.to_dict(include_stats=True)), 200


@resources_bp.route('/courses/<int:course_id>', methods=['DELETE'])
@jwt_required()
@roles_required('admin')
def delete_course(course_id):
    course = db.session.get(Course, course_id)
    if course is None:
        return _error('Course not found', code=404)

    count = course.tasks.count()
    if count and request.args.get('force') != 'true':
        return _error(
            f'Mata kuliah ini masih dipakai {count} task. '
            'Kirim ?force=true untuk melepas task dari mata kuliah ini.',
            code=409,
            task_count=count,
        )

    db.session.delete(course)
    db.session.commit()
    log('delete', 'course', course_id, current_user())
    return jsonify({'message': 'Course deleted', 'detached_tasks': count}), 200


# ------------------------------------------------------------------- NOTE

@resources_bp.route('/notes', methods=['GET'])
@jwt_required()
def list_notes():
    query = Note.query
    if current_user() and current_user().role != 'admin':
        query = query.filter_by(user_id=current_user().id)
    rows = query.order_by(Note.pinned.desc(), Note.created_at.desc()).all()
    return jsonify([n.to_dict() for n in rows]), 200


@resources_bp.route('/notes', methods=['POST'])
@jwt_required()
@validate_body()
@limiter.limit('20 per minute')
def create_note():
    data = body()
    text = body_text(data.get('text'), 5000)
    if not text:
        return _error('Text is required', details={'field': 'text'})

    user = current_user()
    note = Note(
        text=text,
        color=body_text(data.get('color'), 20) or 'yellow',
        pinned=bool(data.get('pinned')),
        user_id=user.id if user else None,
    )
    db.session.add(note)
    db.session.commit()
    return jsonify(note.to_dict()), 201


@resources_bp.route('/notes/<int:note_id>', methods=['PUT'])
@jwt_required()
@validate_body()
def update_note(note_id):
    note = db.session.get(Note, note_id)
    if note is None:
        return _error('Note not found', code=404)
    data = body()

    if 'text' in data:
        text = body_text(data['text'], 5000)
        if not text:
            return _error('Text tidak boleh kosong')
        note.text = text
    if 'color' in data:
        note.color = body_text(data['color'], 20) or 'yellow'
    if 'pinned' in data:
        note.pinned = bool(data['pinned'])
    note.updated_at = utcnow()
    db.session.commit()
    return jsonify(note.to_dict()), 200


@resources_bp.route('/notes/<int:note_id>', methods=['DELETE'])
@jwt_required()
def delete_note(note_id):
    note = db.session.get(Note, note_id)
    if note is None:
        return _error('Note not found', code=404)
    db.session.delete(note)
    db.session.commit()
    return jsonify({'message': 'Note deleted'}), 200
