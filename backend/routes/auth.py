"""Autentikasi: register, login, JWT, dan pembatasan akses.

Konsep:
- Password disimpan sebagai hash (bcrypt via Werkzeug), tidak pernah teks biasa.
- Setelah login berhasil, server memberi JWT (token), bukan session cookie.
- Setiap request berikutnya menyertakan header Authorization: Bearer <token>.
  Server memverifikasi token itu untuk tahu siapa yang sedang 요청.
- Role menentukan boleh akses apa: student hanya datanya sendiri,
  admin boleh melihat semua.
"""

import re
from datetime import timedelta
from functools import wraps

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import func, or_

from backend.extensions import db, limiter
from backend.services.security import body, log
from backend.models import User, utcnow

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

USERNAME_RULE = re.compile(r'^[a-zA-Z0-9_]{3,30}$')
EMAIL_RULE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

MIN_PASSWORD = 8


def error(message, code=400, **extra):
    body = {'error': message}
    body.update(extra)
    return jsonify(body), code


def _clean_username(value):
    return (value or '').strip().lower()


@auth_bp.route('/register', methods=['POST'])
def register():
    data = body()
    username = _clean_username(data.get('username'))
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    full_name = (data.get('full_name') or '').strip() or None

    if not USERNAME_RULE.match(username):
        return error(
            'Username harus 3-30 karakter: huruf, angka, atau underscore',
            details={'field': 'username'},
        )
    if not EMAIL_RULE.match(email):
        return error('Format email tidak valid', details={'field': 'email'})
    if len(password) < MIN_PASSWORD:
        return error(
            f'Password minimal {MIN_PASSWORD} karakter',
            details={'field': 'password'},
        )

    # Cek duplikat lebih dulu supaya tidak sampai jadi error database
    # yang pesannya kurang jelas.
    if User.query.filter(
        or_(User.username == username, User.email == email)
    ).first():
        return error('Username atau email sudah dipakai', code=409)

    user = User(
        username=username,
        email=email,
        full_name=full_name,
        role='student',
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    token = create_access_token(
        identity=str(user.id), additional_claims={'role': user.role}
    )
    return jsonify({'token': token, 'user': user.to_dict()}), 201


@auth_bp.route('/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    data = body()
    identifier = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''

    if not identifier or not password:
        return error('Username dan password wajib diisi')

    # Satu query saja, bukan dua. Kalau cek username dulu baru
    # cek password, itu dua kali ke database untuk satu login.
    user = User.query.filter(
        or_(User.username == identifier, User.email == identifier)
    ).first()

    # Pesan error sengaja sama untuk "user tidak ada" dan "password
    # salah". Kalau dibedakan, penyerang bisa menebak username mana
    # yang terdaftar.
    if user is None or not user.check_password(password):
        return error('Username atau password salah', code=401)

    user.last_login_at = utcnow()
    db.session.commit()

    token = create_access_token(
        identity=str(user.id), additional_claims={'role': user.role}
    )
    return jsonify({'token': token, 'user': user.to_dict()}), 200


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return error('User tidak ditemukan', code=404)
    return jsonify(user.to_dict()), 200


def roles_required(*allowed):
    """Decorator: hanya user dengan role tertentu yang boleh lewat.

    Contoh:
        @roles_required('admin')
        def list_all_users(): ...
    """

    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = jwt_claims()
            if claims.get('role') not in allowed:
                return error('Kamu tidak punya akses ke bagian ini', code=403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def jwt_claims():
    """Ambil claim dari token JWT yang sedang dipakai."""
    from flask_jwt_extended import get_jwt

    return get_jwt()


def current_user():
    """User yang sedang request, atau None kalau tidak login."""
    from flask_jwt_extended import get_jwt_identity

    try:
        identity = get_jwt_identity()
    except Exception:
        return None
    if identity is None:
        return None
    return db.session.get(User, int(identity))


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Catat waktu logout.

    JWT yang sudah terbit tetap valid sampai kedaluwarsa, jadi logout
    di sisi server tidak bisa mencabut token yang sudah keluar.
    Cara yang benar di production adalah menyimpan daftar token yang
    dicabut (token denylist) atau memakai access token berumur pendek.
    Catatan ini sengaja ditulis supaya tidak menyesatkan.
    """
    return jsonify({'message': 'Logged out'}), 200
