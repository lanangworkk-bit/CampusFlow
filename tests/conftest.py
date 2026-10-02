"""Konfigurasi pytest dan fixture bersama.

Pola yang dipakai: satu database SQLite in-memory untuk seluruh test.
Walaupun in-memory, setiap test tetap dapat database baru,
jadi test tidak saling mengganggu.
"""

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-bukan-untuk-production'
os.environ['ADMIN_API_KEY'] = 'test-admin-key'
os.environ['RATELIMIT_ENABLED'] = '0'

from backend.app import create_app  # noqa: E402
from backend.extensions import db as _db  # noqa: E402
from backend.models import Course, Note, Task, User  # noqa: E402


@pytest.fixture(scope='function')
def app():
    """Aplikasi Flask dengan database bersih untuk tiap test."""
    application = create_app('testing')

    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def user(db):
    u = User(username='testuser', email='test@test.id', role='student')
    u.set_password('testpass123')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def admin(db):
    a = User(username='admin', email='admin@test.id', role='admin')
    a.set_password('adminpass123')
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def course(db):
    c = Course(name='Basis Data', code='BD101', sks=4,
                lecturer='Andi Wijaya, S.Kom.', room='Lab Data',
                day='Kamis', time='13:00 - 16:00')
    db.session.add(c)
    db.session.commit()
    return c


class AuthClient:
    """Test client yang selalu menyertakan token JWT.

    Dipakai supaya test tidak perlu menulis header Authorization
    di setiap request. Method tetap sama seperti Flask test client.
    """

    def __init__(self, flask_client, token):
        self._client = flask_client
        self.token = token

    def _headers(self, extra=None):
        headers = {'Authorization': f'Bearer {self.token}'}
        headers.update(extra or {})
        return headers

    def get(self, url, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers'] = self._headers(kwargs['headers'])
        return self._client.get(url, **kwargs)

    def post(self, url, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers'] = self._headers(kwargs['headers'])
        return self._client.post(url, **kwargs)

    def put(self, url, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers'] = self._headers(kwargs['headers'])
        return self._client.put(url, **kwargs)

    def delete(self, url, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers'] = self._headers(kwargs['headers'])
        return self._client.delete(url, **kwargs)

    def open(self, url, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers'] = self._headers(kwargs['headers'])
        return self._client.open(url, **kwargs)


@pytest.fixture
def auth_client(client, user):
    """Client yang sudah login sebagai user biasa."""
    response = client.post(
        '/api/auth/login',
        json={'username': 'testuser', 'password': 'testpass123'},
    )
    assert response.status_code == 200
    return AuthClient(client, response.get_json()['token'])


@pytest.fixture
def admin_client(client, admin):
    """Client yang sudah login sebagai admin."""
    response = client.post(
        '/api/auth/login',
        json={'username': 'admin', 'password': 'adminpass123'},
    )
    assert response.status_code == 200
    return AuthClient(client, response.get_json()['token'])


@pytest.fixture
def auth_header(client):
    """Helper untuk header Authorization."""
    def _header(token):
        return {'Authorization': f'Bearer {token}'}
    return _header


@pytest.fixture
def seeded(db, user, course):
    """User dengan beberapa task untuk menguji filter, sort, dan analitik.

    Tenggat dihitung relatif terhadap hari ini, bukan tanggal yang
    ditulis mati. Kalau用的是 tanggal keras, test ini akan basi
    sendiri begitu tanggal aslinya terlewati: tugas yang أمس masih
    'belum overdue' tiba-tiba jadi OVERDUE dan jumlahannya berubah
    tanpa ada yang mengubah kode.
    """
    hari_ini = date.today()

    def dalam(hari):
        """Tenggat relatif: -30 berarti 30 hari lalu, +60 berarti 60 hari ke depan."""
        return hari_ini + timedelta(days=hari)

    tasks = [
        # Masih di depan, jadi belum OVERDUE.
        Task(title='Tugas Alpha', description='Belajar SQL', status='TODO',
             priority='HIGH', deadline=dalam(30), user_id=user.id,
             course_id=course.id, progress=0),
        # 10 hari lalu, jadi sudah lewat.
        Task(title='Tugas Beta', description='Belajar Flask', status='IN PROGRESS',
             priority='MEDIUM', deadline=dalam(-10), user_id=user.id,
             progress=50),
        # Jauh-jauh lalu, juga lewat.
        Task(title='Tugas Gamma', description='Tugas lama', status='TODO',
             priority='URGENT', deadline=dalam(-200), user_id=user.id,
             progress=0),
        # Sudah selesai, jadi status COMPLETED mengalah apa pun
        #-deadline-nya.
        Task(title='Tugas Delta', description='Sudah beres', status='COMPLETED',
             priority='LOW', deadline=dalam(-40), user_id=user.id,
             progress=100),
        # Tanpa tenggat sama sekali: tidak pernah OVERDUE.
        Task(title='Tugas Epsilon', status='TODO', priority='LOW',
             deadline=None, user_id=user.id),
    ]
    for t in tasks:
        db.session.add(t)
    db.session.add(Note(text='Catatan uji', user_id=user.id))
    db.session.commit()
    return tasks
