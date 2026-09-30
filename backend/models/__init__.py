"""Model database.

Semua tabel didefinisikan di sini sebagai kelas SQLAlchemy. Dengan ORM,
satu kode bisa jalan di SQLite (untuk belajar di laptop) maupun PostgreSQL
(untuk production) tanpa perubahan kode.
"""

from datetime import date, datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from backend.extensions import db

# Nilai enum disimpan sebagai string, bukan integer, supaya mudah dibaca
# langsung di database dan tidak mysterious saat debugging.
TASK_STATUSES = ('TODO', 'IN PROGRESS', 'COMPLETED')
TASK_PRIORITIES = ('LOW', 'MEDIUM', 'HIGH', 'URGENT')
USER_ROLES = ('student', 'admin')


def utcnow():
    """Waktu sekarang dalam UTC, tanpa timezone info.

    Disimpan tanpa timezone supaya konsisten di SQLite dan PostgreSQL.
    SQLite menyimpan string, PostgreSQL jadi timestamp.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today():
    return date.today().isoformat()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120))
    role = db.Column(db.String(20), nullable=False, default='student')
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)

    tasks = db.relationship(
        'Task', backref='owner', lazy='dynamic', cascade='all, delete-orphan'
    )

    def set_password(self, raw):
        """Simpan password dalam bentuk hash, bukan teks biasa.

        Penting: password asli tidak pernah ditulis ke database.
        generate_password_hash memakai bcrypt-like algorithm yang
        lambat dan di-saltab, jadi mustahil dibalik.
        """
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    lecturer = db.Column(db.String(120))
    sks = db.Column(db.Integer, default=3)
    room = db.Column(db.String(80))
    day = db.Column(db.String(20))
    time = db.Column(db.String(40))
    color = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    # ON DELETE SET NULL: hapus mata kuliah, task-nya tetap ada
    # tapi course_id-nya jadi NULL. Task tidak ikut hilang.
    tasks = db.relationship('Task', backref='course', lazy='dynamic')

    def to_dict(self, include_stats=False):
        data = {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'lecturer': self.lecturer or '',
            'sks': self.sks or 0,
            'room': self.room or '',
            'day': self.day or '',
            'time': self.time or '',
            'color': self.color or '',
        }
        if include_stats:
            total = self.tasks.filter_by(status='COMPLETED').count()
            data['task_count'] = self.tasks.count()
            data['task_done'] = total
        return data


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, default='')
    status = db.Column(
        db.String(20), nullable=False, default='TODO', index=True
    )
    priority = db.Column(
        db.String(20), nullable=False, default='MEDIUM', index=True
    )
    progress = db.Column(db.Integer, nullable=False, default=0)
    deadline = db.Column(db.String(10), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    completed_at = db.Column(db.DateTime)

    def effective_status(self):
        """Status yang ditampilkan ke user.

        OVERDUE tidak disimpan di database. Kalau disimpan, dia akan
        basi begitu deadline task diperbarui. Jadi dihitung ulang
        setiap kali ditampilkan: selalu akurat tanpa perlu di-update.
        """
        if self.status == 'COMPLETED':
            return 'COMPLETED'
        if self.deadline and self.deadline < today():
            return 'OVERDUE'
        return self.status

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description or '',
            'status': self.effective_status(),
            'raw_status': self.status,
            'priority': self.priority,
            'progress': self.progress,
            'deadline': self.deadline,
            'course_id': self.course_id,
            'course_name': self.course.name if self.course else None,
            'course_code': self.course.code if self.course else None,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Note(db.Model):
    __tablename__ = 'notes'

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    color = db.Column(db.String(20), default='yellow')
    pinned = db.Column(db.Boolean, default=False, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    def to_dict(self):
        return {
            'id': self.id,
            'text': self.text,
            'color': self.color or 'yellow',
            'pinned': bool(self.pinned),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    """Catatan siapa mengubah apa.

    Dipakai di Semester 6 untuk 요구 jejak audit. Baris di sini
    hanya ditulis, tidak pernah di-update atau di-delete.
    """

    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    username = db.Column(db.String(50))
    action = db.Column(db.String(40), nullable=False, index=True)
    resource = db.Column(db.String(40), index=True)
    resource_id = db.Column(db.Integer)
    ip_address = db.Column(db.String(45))
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'action': self.action,
            'resource': self.resource,
            'resource_id': self.resource_id,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
