"""Endpoint analitik, rekomendasi, dan informasi sistem."""

import os
import platform
import time

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func, text

from backend.extensions import db
from backend.version import SEMESTER, __version__
from backend.models import AuditLog, Course, Note, Task, User, utcnow
from backend.routes.auth import current_user, roles_required
from backend.services import analytics
from backend.services.optimize import cached
from backend.services.security import api_key_required

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api')

START_TIME = time.time()


def _scope():
    """ID user untuk membatasi analytics, atau None untuk semua data."""
    if request.args.get('scope') == 'all':
        user = current_user()
        return None if user and user.role == 'admin' else _own_id()
    return _own_id()


def _own_id():
    user = current_user()
    return user.id if user else None


@analytics_bp.route('/stats', methods=['GET'])
@jwt_required()
@cached('stats', ttl=15)
def stats():
    """Ringkasan angka-angka utama untuk dashboard.

    Hasilnya di-cache 15 detik. Angkanya memang tidak berubah
    setiap detik, tapi dashboard membacanya tiap kali dibuka.
    """
    return jsonify(analytics.summary(_scope())), 200


@analytics_bp.route('/analytics/full', methods=['GET'])
@jwt_required()
def full_analytics():
    """Semua analisis sekaligus, untuk laporan."""
    return jsonify(analytics.full_report(_scope())), 200


@analytics_bp.route('/analytics/productivity', methods=['GET'])
@jwt_required()
def productivity():
    return jsonify(analytics.productivity(_scope())), 200


@analytics_bp.route('/analytics/forecast', methods=['GET'])
@jwt_required()
def forecast():
    days = min(max(request.args.get('days', 7, type=int) or 7, 1), 90)
    return jsonify(analytics.forecast(_scope(), days)), 200


@analytics_bp.route('/analytics/cache-stats', methods=['GET'])
@jwt_required()
def cache_stats():
    """Lihat apakah cache sedang bekerja.

    Berguna saat mengukur: kalau hit naik terus, query berulang
    berhasil dihindari.
    """
    from flask import g

    hits = getattr(g, 'cache_hits', 0)
    return jsonify({'cache_hits_this_request': hits}), 200


@analytics_bp.route('/analytics/suggestions', methods=['GET'])
@jwt_required()
def suggestions():
    limit = min(max(request.args.get('limit', 5, type=int) or 5, 1), 20)
    return jsonify({'items': analytics.suggest(_scope(), limit)}), 200


@analytics_bp.route('/analytics/stuck', methods=['GET'])
@jwt_required()
def stuck():
    days = min(max(request.args.get('days', 7, type=int) or 7, 1), 365)
    return jsonify({'items': analytics.stuck_tasks(_scope(), days)}), 200


@analytics_bp.route('/analytics/upcoming', methods=['GET'])
@jwt_required()
def upcoming():
    days = min(max(request.args.get('days', 14, type=int) or 14, 1), 365)
    return jsonify({'items': analytics.upcoming(_scope(), days)}), 200


@analytics_bp.route('/analytics/by-course', methods=['GET'])
@jwt_required()
def by_course():
    return jsonify({'items': analytics.by_course(_scope())}), 200


# ---------------------------------------------------------------- SYSTEM

system_bp = Blueprint('system', __name__, url_prefix='/api')


@system_bp.route('/health', methods=['GET'])
def health():
    """Cek kesehatan aplikasi dan koneksi database.

    Tidak butuh token, supaya bisa dipanggil oleh load balancer
    atau monitoring tanpa perlu kredensial.
    """
    checks = {}

    try:
        db.session.execute(text('SELECT 1'))
        checks['database'] = 'ok'
    except Exception as error:
        checks['database'] = f'error: {error}'

    try:
        Task.query.count()
        checks['orm'] = 'ok'
    except Exception as error:
        checks['orm'] = f'error: {error}'

    healthy = all(v == 'ok' for v in checks.values())
    return jsonify({
        'status': 'healthy' if healthy else 'unhealthy',
        'checks': checks,
        'uptime_seconds': round(time.time() - START_TIME, 1),
        'timestamp': utcnow().isoformat(),
    }), (200 if healthy else 503)


@system_bp.route('/version', methods=['GET'])
def version():
    return jsonify({
        'app': 'CampusFlow',
        'version': __version__,
        'semester': SEMESTER,
        'python': platform.python_version(),
        'environment': os.environ.get('FLASK_ENV', 'development'),
    }), 200


@system_bp.route('/metrics', methods=['GET'])
@api_key_required
def metrics():
    """Jumlah baris di setiap tabel, untuk monitoring.

    Endpoint ini butuh X-API-Key, bukan token user, karena hasilnya
    bersifat sistem, bukan data milik satu orang.
    """
    counts = {
        'users': db.session.query(func.count(User.id)).scalar(),
        'tasks': Task.query.count(),
        'courses': Course.query.count(),
        'notes': Note.query.count(),
        'audit_logs': AuditLog.query.count(),
    }
    uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    return jsonify({
        'counts': counts,
        'database': 'postgresql' if 'postgres' in uri else 'sqlite',
        'uptime_seconds': round(time.time() - START_TIME, 1),
    }), 200


@system_bp.route('/audit-logs', methods=['GET'])
@roles_required('admin')
def audit_logs():
    limit = min(max(request.args.get('limit', 50, type=int) or 50, 1), 200)
    action = request.args.get('action')
    query = AuditLog.query
    if action:
        query = query.filter_by(action=action)
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return jsonify({
        'items': [r.to_dict() for r in rows],
        'total': query.count(),
    }), 200
