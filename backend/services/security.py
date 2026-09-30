"""Lapisan keamanan: audit log, security headers, sanitasi input."""

import re
import secrets
from functools import wraps

from flask import current_app, g, jsonify, request
from sqlalchemy import func

from backend.extensions import db
from backend.models import AuditLog, utcnow

CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Tag dan atribut berbahaya yang harus hilang sebelum teks disimpan.
# Frontend merender lewat textContent, bukan innerHTML, jadi lapis
# ini adalah cadangan terakhir kalau suatu saat template berubah.
SCRIPT_TAG = re.compile(r'<\s*/?\s*(script|iframe|object|embed|style)[^>]*>',
                        re.IGNORECASE)
EVENT_HANDLER = re.compile(
    r'(?:^|[\s"\'<(])on\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)',
    re.IGNORECASE,
)
# Hanya skema yang benar-benar bisa mengeksekusi kode. 'data:'
# polos sengaja tidak masuk daftar: dalam teks biasa kata 'Data:'
# atau 'Note:' sangat umum dan sering terpotong tanpa alasan.
# Yang berbahaya hanya data: yang membawa HTML.
DANGEROUS_URL = re.compile(
    r'(javascript|vbscript)\s*:|data\s*:\s*text/html',
    re.IGNORECASE,
)
# Sisanya dibuang tag-nya tapi teksnya dipertahankan, supaya
# "5 < 10" tetap terbaca sebagai teks biasa.
# Hanya tag sungguhan yang dihapus, bukan tanda '<' biasa.
# '< 10' harus tetap terbaca sebagai teks perbandingan.
ANY_TAG = re.compile(r'<[a-zA-Z/!?][^>]*>')
WHITESPACE = re.compile(r'[ \t\r\n\f\v]+')


def clean_text(value, max_length=2000, allow_tags=False):
    """Bersihkan teks dari user sebelum disimpan.

    Yang dilakukan:
    1. Buang karakter kontrol (null byte, newline tersembunyi, dll).
       Karakter ini bisa menyamarkan isi atau merusak filter.
    2. Buang tag berbahaya, event handler, dan URL javascript:.
    3. Kalau allow_tags=False, buang semua tag HTML. Tanpa ini,
       judul tugas seperti "<script>alert(1)</script>" akan tersimpan
       utuh dan berbahaya begitu dirender.
    4. Normalisasi spasi berlebih lalu potong panjangnya, supaya satu
       request tidak bisa mengisi database dengan teks raksasa.
    """
    if value is None:
        return None

    text = CONTROL_CHARS.sub('', str(value))
    text = SCRIPT_TAG.sub('', text)
    text = EVENT_HANDLER.sub('', text)
    text = DANGEROUS_URL.sub('', text)
    if not allow_tags:
        text = ANY_TAG.sub('', text)
    text = WHITESPACE.sub(' ', text).strip()
    return text[:max_length]


# Batas atas global.<Longgar di sini, karena batas per-field (judul 200,
# deskripsi 5000) yang ebooks. Kalau batas global ikut 2000, deskripsi
# akan terpotong sebelum batas 5000 sempat berlaku.
BODY_MAX = 20000


def body(max_length=BODY_MAX):
    """Ambil JSON body dengan setiap nilai teksnya sudah dibersihkan.

    Dipakai di semua endpoint yang menerima input. Dengan begitu tidak
    ada satu pun field yang bisa menyimpan HTML mentah karena lupa
    dipanggil manual.
    """
    from flask import request as _request

    data = _request.get_json(silent=True)
    if not isinstance(data, dict):
        return {}

    cleaned = {}
    for key, value in data.items():
        if isinstance(value, str):
            cleaned[key] = clean_text(value, max_length)
        elif isinstance(value, list):
            cleaned[key] = [
                clean_text(v, 200) if isinstance(v, str) else v for v in value
            ][:100]
        else:
            cleaned[key] = value
    return cleaned


def log(action, resource=None, resource_id=None, user=None, detail=None):
    """Catat sebuah aksi ke audit log.

    Sengaja tidak memakai db.session yang sama dengan request, supaya
    kalau request gagal dan di-rollback, catatan audit tetap aman.
    """
    try:
        entry = AuditLog(
            user_id=getattr(user, 'id', None),
            username=getattr(user, 'username', None),
            action=action,
            resource=resource,
            resource_id=resource_id,
            ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
            detail=clean_text(detail, 500) if detail else None,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        # Audit log tidak boleh menjatuhkan request utama.
        db.session.rollback()
        current_app.logger.warning('Gagal menulis audit log: %s', action)


def security_headers(response):
    """Tambah header keamanan ke setiap respons.

    Ini adalah pertahanan lapisan luar (defense in depth). Mencegah
    browser melakukan hal berbahaya, bukan menggantikan validasi di server.
    """
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-XSS-Protection'] = '0'
    response.headers['Permissions-Policy'] = (
        'geolocation=(), microphone=(), camera=()'
    )

    # HSTS hanya berguna di HTTPS. Kalau dipasang di http://localhost,
    # browser akan mengingat dan menolak koneksi http berikutnya,
    # termasuk ke server lokal. Jadi hanya nyalakan di production,
    # dan dimatikan juga saat testing.
    if current_app.config.get('DEBUG') is False and not current_app.config.get('TESTING'):
        response.headers['Strict-Transport-Security'] = (
            'max-age=31536000; includeSubDomains'
        )

    # Content-Security-Policy: izinkan sumber yang memang dipakai halaman.
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        # Tidak ada 'unsafe-inline' di sini. Semua script dan style
        # dilayani dari file sendiri, jadi tidak perlu pengecualian.
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    return response


def api_key_required(fn):
    """Decorator: wajib menyertakan X-API-Key.

    Dipakai untuk endpoint admin tambahan, misalnya sinkronisasi data.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        provided = request.headers.get('X-API-Key', '')
        expected = current_app.config.get('ADMIN_API_KEY', '')
        if not expected or not secrets.compare_digest(provided, expected):
            return jsonify({'error': 'API key tidak valid'}), 401
        return fn(*args, **kwargs)

    return wrapper


def validate_body(content_type='application/json'):
    """Decorator: pastikan body adalah JSON dengan ukuran wajar."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify(
                    {'error': f'Body harus {content_type}'}
                ), 415
            length = request.content_length or 0
            if length > 1_000_000:
                return jsonify({'error': 'Body terlalu besar'}), 413
            return fn(*args, **kwargs)

        return wrapper

    return decorator
