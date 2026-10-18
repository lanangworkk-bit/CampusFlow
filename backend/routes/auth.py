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
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import func, or_

from backend.extensions import db, limiter
from backend.services.security import body, log
from backend.models import RefreshToken, User, utcnow

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

    access, refresh = _issue_tokens(user)
    return jsonify(
        {'token': access, 'refresh_token': refresh, 'user': user.to_dict()}
    ), 201


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

    access, refresh = _issue_tokens(user)
    return jsonify(
        {'token': access, 'refresh_token': refresh, 'user': user.to_dict()}
    ), 200


def _issue_tokens(user):
    """Buat sepasang access + refresh token, dan catat sesinya.

    Access token sengaja berumur pendek. Kalau bocor, yang hilang cuma
    beberapa menit akses. Refresh token yang berumur panjang ada supaya
    user tidak kena login ulang terus-menerus, dan karena umurnya panjang
    token itu harus bisa dicabut: itulah gunanya baris RefreshToken.
    """
    access = create_access_token(
        identity=str(user.id), additional_claims={'role': user.role}
    )
    refresh = create_refresh_token(identity=str(user.id))

    jti = decode_token(refresh)['jti']
    db.session.add(
        RefreshToken(
            jti=jti,
            user_id=user.id,
            expires_at=utcnow() + current_app.config['JWT_REFRESH_TOKEN_EXPIRES'],
            user_agent=(request.headers.get('User-Agent') or '')[:200] or None,
            ip_address=request.headers.get(
                'X-Forwarded-For', request.remote_addr
            ),
        )
    )
    db.session.commit()
    return access, refresh


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
@limiter.limit('30 per minute')
def refresh():
    """Tukar refresh token jadi access token baru, lalu rotasi.

    Rotasi berarti setiap refresh token hanya bisa dipakai sekali: begitu
    dipakai, token itu langsung dicabut dan digantikan yang baru. Jadi kalau
    ada yang mencuri refresh token, orang itu akan menang balapan dengan
    pemilik aslinya hanya sekali saja.

    Kalau yang datang adalah token yang sudah dicabut, itu berarti ada dua
    orang memakai token yang sama: pemilik aslinya dan pencuri. Kita tidak
    tahu siapa yang mana, jadi seluruh sesi milik user itu dicabut. Satu
    orang yang log out paksa bisa mengakhiri semua sesinya, dan itu harga
    yang jauh lebih murah daripada membiarkan pencuri tetap masuk.
    """
    jti = get_jwt()['jti']
    record = db.session.get(RefreshToken, jti)

    if record is None:
        # Token-nya valid secara kriptografi tapi tidak ada di database.
        # Aplikasi ini selalu membuat baris saat menerbitkan token, jadi
        # ini berarti barisnya hilang. Tolak.
        return error('Refresh token tidak dikenal', code=401)

    if record.revoked_at is not None:
        # Dipakai ulang. Tandai, lalu cabut semua sesi user ini.
        record.reuse_detected_at = utcnow()
        user = db.session.get(User, record.user_id)
        _revoke_all_for_user(record.user_id, reason='reuse_detected')
        log(
            'token_reuse_detected', 'refresh_token', None, user,
            detail=f'jti={jti} reason={record.revoked_reason}',
        )
        return error(
            'Refresh token sudah dipakai. Semua sesi dicabut, silakan login lagi.',
            code=401,
        )

    if record.is_expired:
        # Expired. Dicabut supaya tidak perlu dibersihkan manual nanti.
        record.revoked_at = utcnow()
        record.revoked_reason = 'expired'
        db.session.commit()
        return error('Refresh token kedaluwarsa, silakan login lagi', code=401)

    user = db.session.get(User, record.user_id)
    if user is None:
        return error('User tidak ditemukan', code=401)

    # Issue dulu, baru cabut yang lama dan tautkan jti penggantinya.
    # Urutan ini penting: kalau issue gagal, token lama masih berlaku
    # dan user bisa mencoba lagi. Kalau dibalik, satu kegagalan
    # refresh akan mengakhiri sesi.
    access, baru = _issue_tokens(user)
    jti_baru = decode_token(baru)['jti']

    record.revoked_at = utcnow()
    record.revoked_reason = 'rotated'
    record.replaced_by = jti_baru
    db.session.commit()

    return jsonify(
        {'token': access, 'refresh_token': baru, 'user': user.to_dict()}
    ), 200


def _revoke_all_for_user(user_id, reason):
    """Cabut semua refresh token milik satu user."""
    now = utcnow()
    aktif = RefreshToken.query.filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
    ).all()
    for row in aktif:
        row.revoked_at = now
        row.revoked_reason = reason
    db.session.commit()
    return len(aktif)


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
@jwt_required(optional=True)
def logout():
    """Cabut sesi ini, dan cabut semua sesi kalau diminta.

    Access token yang sudah terbit tidak bisa dicabut dari sisi server:
    JWT sudah ditandatangani, tidak ada yang perlu ditanyakan ke
    database. Jadi logout tidak bisa mencabut access token yang
    sudah keluar dari browser, dan itu memang sifat JWT yang jujur
    harus diakui. Yang dicabut di sini adalah refresh token: tanpa itu,
    sesi yang 'sudah logout' masih bisa diperpanjang diam-diam,
    dan itu yang membuat logout terasa tidak berfungsi.

    Karena itu access token dibuat berumur pendek. periodenya yang
    memperkecil jeda antara logout dan benar-benar tidak berlaku.

    Kirim refresh_token di body agar sesi ini saja yang ditutup. Kirim
    all_sessions=true untuk menutup semua sesi, misalnya setelah
    password diubah atau dicurigai kompromi.
    """
    data = body()
    user = current_user()
    if user is None:
        # Tidak ada token sama sekali, jadi tidak ada sesi yang bisa
        # dicabut. Tidak apa-apa, logout harus idempoten: dipanggil
        # dua kali tetap dianggap berhasil.
        return jsonify({'message': 'Logged out'}), 200

    if data.get('all_sessions'):
        jumlah = _revoke_all_for_user(user.id, reason='logout_all')
        detail = f'{jumlah} sesi dicabut'
    else:
        jumlah = _revoke_from_body(data.get('refresh_token'), user)
        detail = f'sesi dicabut: {jumlah}'

    log('logout', 'session', None, user, detail=detail)
    return jsonify({'message': 'Logged out'}), 200


def _revoke_from_body(raw_token, user):
    """Cabut satu sesi berdasarkan refresh token di body request.

    jti milik access token dan jti milik refresh token itu dua hal
    berbeda, jadi jti access token tidak akan pernah ditemukan di tabel
    refresh_tokens. Karena itu refresh token di body harus dibaca dulu
    untuk diambil jti-nya.
    """
    if not raw_token:
        return 0

    try:
        claims = decode_token(raw_token)
    except Exception:
        # Token rusak atau kedaluwarsa. Tidak ada yang bisa dicabut,
        # dan bukan alasan membalas error: pemanggil tetap sedang
        # keluar, hasilnya sama saja.
        return 0

    # Cuma refresh token yang relevan, dan cuma miliknya sendiri.
    # Tanpa ini, siapa pun yang punya access token milik user bisa
    # mencabut sesi orang lain yang juga miliknya.
    if claims.get('type') != 'refresh':
        return 0
    if claims.get('sub') != str(user.id):
        return 0

    record = db.session.get(RefreshToken, claims.get('jti'))
    if record is None or record.revoked_at is not None:
        return 0

    record.revoked_at = utcnow()
    record.revoked_reason = 'logout'
    db.session.commit()
    return 1


@auth_bp.route('/sessions', methods=['GET'])
@jwt_required()
def list_sessions():
    """Sesi aktif milik user yang sedang login.

    Membantu user melihat perangkat mana yang masih masuk, dan memberi
    angka yang bisa dipakai frontend untuk menampilkan 'sesi lain'.
    """
    user_id = current_user().id
    rows = (
        RefreshToken.query.filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
        .order_by(RefreshToken.created_at.desc())
        .all()
    )
    return jsonify({
        'sessions': [
            {
                'jti': row.jti,
                'created_at': row.created_at.isoformat() if row.created_at else None,
                'expires_at': row.expires_at.isoformat() if row.expires_at else None,
                'user_agent': row.user_agent or '',
                'ip_address': row.ip_address or '',
            }
            for row in rows
        ],
        'total': len(rows),
    }), 200
